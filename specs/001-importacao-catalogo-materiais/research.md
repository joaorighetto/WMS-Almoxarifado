# Research — 001 Importação e Consulta do Catálogo de Materiais

**Data**: 2026-09-21 | **Plano**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

Decisões técnicas da Fase 0. Nenhuma delas cria requisito, permissão ou invariante nova: cada uma
escolhe **como** cumprir um FR/SC da spec ou uma `PERM-*`/`INV-*` canônica. Onde uma decisão
interpreta um ponto que a spec deixa aberto, isso está marcado como **Interpretação** e listado no
fim; todas foram confirmadas pelo dono do produto em 2026-09-21.

Versões verificadas no ambiente instalado (não presumidas): Python 3.13, Django 6.1.1
(`uv.lock`), PostgreSQL 16 (`compose.yml` e CI).

## Evidência usada — arquivo real

O export real `relacao-de-todos-produtos-importados-do-SCPI.csv` **existe localmente** em
`docs/domain-legacy/`, mas o diretório é ignorado pelo Git (`.gitignore:47`, `domain-legacy/`,
com a nota "contém credenciais e arquivos grandes"). Portanto não faz parte da árvore versionada e
não pode ser usado pela suíte de testes nem pela CI. Nesta fase foram lidas **apenas propriedades
estruturais** do arquivo, sem copiar conteúdo para o repositório:

| Propriedade | Valor observado |
|---|---|
| Tamanho | 385.671 bytes |
| BOM UTF-8 | presente |
| Fim de linha | CRLF em todas as 1606 linhas físicas (nenhum CR isolado) |
| Cabeçalho | 21 nomes + campo vazio final (22 campos); `CADPRO` é a **primeira** coluna |
| Colunas do cabeçalho | `CADPRO;DISC1;UNID1;QUAN3;VAUN1;PRECOMEDIO;GRUPO;SUBGRUPO;NOMEGRUPO;NOMESUBGRUPO;DISCR1;QUANMIN;QUANMAX;CODREDUZ;CODBARRA;NOCULTAR;USUARIO;DTAINSERE;USUALT;DTAALT;LOCALFISICO;` |
| Registros lógicos (heurística da spec) | 1588, todos com exatamente 22 campos |
| Linhas de continuação | 17; nenhuma delas tem, sozinha, a contagem completa de separadores |
| Último campo preenchido | 0 registros |
| Espaços em volta de `CADPRO`/`DISC1`/`UNID1` | 0 |
| `QUAN3` | sem separador de milhar; até 13 casas decimais (o caso de ruído já citado na spec) |

Esses números confirmam a análise registrada na spec (Clarifications, "análise do arquivo real") e
sustentam R2–R5. A validação final de aceite contra o arquivo continua pendente de ele estar
disponível para o ambiente de validação (ver R14).

---

## R1 — Onde vive a feature: novo app `catalogo`

**Decision**: criar o app Django `catalogo` na raiz do repositório, ao lado de `contas`.

**Rationale**: material, execução de importação, exceção e divergência são um contexto de domínio
próprio, consumido por futuras features (`ENT`, `REQ`, `INV`, `MAT`). Misturá-lo em `contas`
acoplaria catálogo a identidade. Segue a convenção já estabelecida pela 002 (apps na raiz, testes em
`tests/` único).

**Alternatives considered**: colocar em `contas` (rejeitado: responsabilidade não enunciável); criar
`estoque` separado para o saldo (rejeitado: nesta feature o saldo só nasce e é preservado; separar
agora seria generalização especulativa — Constitution I).

## R2 — Leitura do arquivo: parser próprio, sem o módulo `csv`

**Decision**: parser em Python puro (`catalogo/leitura_scpi.py`), em duas fases:

1. **Decodificação**: `bytes.decode("utf-8-sig")` estrito. Remove a BOM se presente (FR-007) e
   aceita também arquivo sem BOM. Byte inválido em UTF-8 recusa o **arquivo inteiro** antes de
   qualquer registro.
2. **Linhas físicas**: `texto.split("\n")`, removendo um `\r` final de cada linha. **Não** se usa
   `str.splitlines()`, que também quebra em `\x0b`, `\x0c`, `\x1c`–`\x1e`, `\x85`, `\u2028` e
   `\u2029` — caracteres que podem aparecer em texto livre e que não são fim de linha no arquivo.
   Um único `\n` final do arquivo não gera linha vazia extra.
3. **Recomposição antes da separação** (FR-009) — ver R3.
4. **Separação de campos**: `registro.split(";")`, sem nenhum tratamento de aspas (FR-007a).

**Rationale**: `csv.reader` separa campos por linha física e trata aspas como delimitação; mesmo com
`quoting=QUOTE_NONE` ele não recompõe registros cujo texto contém quebra de linha não delimitada.
FR-009 exige recompor **antes** de separar, e FR-007a exige aspas literais. O formato real é
simples (separador fixo, sem escape) e o parser cabe em poucas funções testáveis isoladamente.
Nenhuma dependência nova (Constitution XI).

**Alternatives considered**: `csv` com `QUOTE_NONE` (não resolve FR-009); pandas (dependência pesada
sem benefício — XI); pré-processar o arquivo com regex global (menos legível e mais difícil de
reportar linha de origem — FR-036).

## R3 — Recomposição de registros e classificação de linhas

**Decision**: cada linha física de dados é classificada assim, nesta ordem:

1. **Início de registro** se o texto antes do primeiro `;` casa `^[0-9]{3}\.[0-9]{3}\.[0-9]{3}$`
   (critério da spec, Assumptions). O padrão usa `[0-9]`, nunca `\d`: em Python, `\d` aceita dígitos
   Unicode (ex.: `٣`), o que aceitaria códigos que não são do SCPI.
2. **Início de registro com código inválido ou ausente** se a linha, sozinha, tem exatamente o número
   de separadores do cabeçalho. Esse registro segue para a validação e é recusado por
   `CADPRO_FORMATO_INVALIDO` ou `CADPRO_AUSENTE` (edge cases "Código fora do formato" e "Código
   ausente"; US3 cenário 2).
3. **Continuação** do registro corrente nos demais casos. O texto é anexado ao registro corrente com
   `"\n"`, de modo que a quebra fica **dentro do campo onde ocorreu**, qualquer que seja ele
   (FR-009). Nenhum campo de destino é presumido.
4. **Linha não associável** se for continuação e não houver registro corrente (ex.: primeira linha
   de dados). Gera exceção `LINHA_NAO_ASSOCIAVEL` (FR-010) e conta como registro recebido e recusado.

**Linha vazia (decisão D-1 do dono do produto, 2026-09-21)**: uma linha física vazia ou só com
espaços é **ignorada** quando não há registro corrente ou quando o registro corrente já está
**completo** (exatamente `N` campos, com o último vazio). Ela não conta como registro recebido nem
gera exceção; a numeração das linhas físicas continua contando-a. Dentro de um registro ainda
incompleto (texto multilinha em andamento), a linha vazia continua sendo **continuação**, e a
quebra é preservada no campo (FR-009). Essa regra é avaliada antes da regra 3.

Depois da recomposição, **todo registro cujo número de campos difere do cabeçalho, ou cujo último
campo (a coluna vazia do delimitador final) está preenchido, é recusado** por
`ESTRUTURA_INCONSISTENTE` (FR-010, FR-011). Isso cobre continuação no fim do arquivo, registro
truncado e continuação mal associada. Nunca se tenta corrigir o deslocamento.

Cada registro guarda o intervalo de linhas físicas de origem (`linha_inicial`, `linha_final`, com
a linha 1 sendo o cabeçalho) para o relatório de exceções (FR-036).

**Rationale**: a regra 2 é um refinamento da heurística registrada nas Assumptions da spec.
Sem ela, uma linha como `2;PARAFUSO;UN;10;...` seria anexada ao registro anterior, que seria
recusado por estrutura, e o código inválido nunca apareceria com o motivo correto. O refinamento
é seguro (FR-011): se uma continuação legítima tivesse por acaso a contagem completa de
separadores, os dois registros envolvidos seriam **recusados**, nunca importados com deslocamento.
Contra o arquivo real, a regra 2 não se aplica a nenhuma das 17 continuações (nenhuma tem
contagem completa), então o resultado continua 1588 registros × 22 campos.

**Alternatives considered**: heurística literal da spec sem a regra 2 (rejeitado: edge cases de
código inválido/ausente ficariam sem o motivo exigido por US3); decidir continuação por contagem
de campos acumulada (rejeitado: um `;` dentro de texto livre tornaria a classificação ambígua sem
ganho de segurança).

## R4 — Cabeçalho e colunas

**Decision**:

- Colunas identificadas **pelo nome** no cabeçalho (FR-008), comparação exata e sensível a
  maiúsculas, depois da remoção da BOM. As nove obrigatórias são `CADPRO`, `DISC1`, `UNID1`,
  `QUAN3`, `DISCR1`, `GRUPO`, `SUBGRUPO`, `NOMEGRUPO`, `NOMESUBGRUPO`; faltando qualquer uma, o
  arquivo inteiro é recusado, sem prévia.
- Nome de coluna obrigatória repetido no cabeçalho recusa o arquivo (não há como saber qual usar —
  FR-011).
- Demais colunas (`VAUN1`, `PRECOMEDIO`, `QUANMIN`, `QUANMAX`, `CODREDUZ`, `CODBARRA`, `NOCULTAR`,
  `USUARIO`, `DTAINSERE`, `USUALT`, `DTAALT`, `LOCALFISICO`) são contadas para a estrutura do
  registro e **ignoradas** — fora de escopo (spec, Clarifications). Nenhum valor delas é
  armazenado. Em particular, `USUARIO`/`USUALT` não são gravados.
- `CADPRO` precisa ser a **primeira** coluna. Caso contrário, o arquivo é recusado
  (`CADPRO_NAO_E_PRIMEIRA_COLUNA`).

**Rationale** da última regra: o critério de início de registro (R3) examina o texto antes do
primeiro `;`. Com `CADPRO` em outra posição, nenhuma linha poderia ser classificada com segurança.
FR-010 e FR-011 exigem recusar, não adivinhar. O arquivo real tem `CADPRO` na primeira coluna.
**Interpretação I-1** (derivada de FR-010/FR-011 e da Assumption de recomposição; não é regra de
negócio nova).

**Arquivo sem dados**: arquivo de 0 bytes ou só com espaços/quebras de linha, e arquivo só com
cabeçalho válido, produzem uma prévia com **zero registros recebidos, sem erro** (edge case
"Arquivo vazio ou apenas com cabeçalho"). A exigência de cabeçalho completo (FR-008) vale quando há
cabeçalho. **Interpretação I-2** para o arquivo de 0 bytes, que o edge case trata como "vazio" e
não como "sem colunas".

## R5 — Validação de campos e ordem dos motivos

**Decision**: um registro recusado gera **uma** exceção, com o **primeiro** motivo encontrado nesta
ordem fixa. A ordem é determinística para que o relatório e os testes sejam estáveis:

| Ordem | Código do motivo | Regra | FR |
|---|---|---|---|
| 1 | `LINHA_NAO_ASSOCIAVEL` | continuação sem registro anterior | FR-010 |
| 2 | `ESTRUTURA_INCONSISTENTE` | nº de campos ≠ cabeçalho, ou coluna final preenchida | FR-010, FR-011 |
| 3 | `CADPRO_AUSENTE` | `CADPRO` vazio | FR-004 |
| 4 | `CADPRO_FORMATO_INVALIDO` | não casa `^[0-9]{3}\.[0-9]{3}\.[0-9]{3}$` exatamente, sem trim (ex.: `2`, `000.000.2`, `0.0.2`, com espaços) | FR-004 |
| 5 | `CADPRO_DUPLICADO_NO_ARQUIVO` | o mesmo `CADPRO` bem formado aparece em mais de um registro | FR-005 |
| 6 | `DESCRICAO_AUSENTE` | `DISC1` vazia ou só com espaços | FR-018 |
| 7 | `UNIDADE_AUSENTE` | `UNID1` vazia ou só com espaços | FR-020 |
| 8 | `QUANTIDADE_AUSENTE` | `QUAN3` vazia ou só com espaços; **nunca** vira zero | FR-014 |
| 9 | `QUANTIDADE_NAO_NUMERICA` | fora da gramática de R6 | FR-015 |
| 10 | `QUANTIDADE_NEGATIVA` | valor < 0 | FR-015, `INV-STOCK-001` |
| 11 | `QUANTIDADE_FORA_DO_LIMITE` | mais de 12 dígitos inteiros (limite do campo, R7) | FR-012 |

Regras complementares:

- **Duplicidade** (FR-005) é apurada sobre **todos** os registros com `CADPRO` bem formado e
  estrutura íntegra, mesmo os que falhariam por outro motivo (descrição, unidade ou quantidade).
  Assim, **todas** as ocorrências de um código repetido são recusadas e reportadas, e nenhuma é
  importada. Registro recusado por `ESTRUTURA_INCONSISTENTE` fica **fora** dessa apuração: suas
  colunas não são confiáveis, então o que está na primeira posição não é tratado como o `CADPRO`
  daquele registro para efeito de duplicidade — uma ocorrência íntegra do mesmo código continua
  sendo importada (decisão do dono do produto, 2026-09-22, durante a revisão final da 001; o texto
  anterior era ambíguo quanto a esse caso). A apuração de **ausentes do arquivo** (R11) é
  diferente e continua incluindo os recusados, inclusive por estrutura: ali a pergunta é só se o
  código aparece no arquivo.
- **Preservação**: nenhum valor textual é aparado, normalizado ou convertido ao ser gravado
  (FR-001, FR-017, FR-019, FR-022). "Só espaços" conta como vazio apenas para a checagem de
  obrigatoriedade.
- `DISCR1` e os campos de classificação podem vir vazios e **não** participam da aceitação
  (FR-021, FR-022, FR-024).
- `CADPRO` exibido na exceção somente quando "identificável" (FR-036): o texto do primeiro campo é
  registrado como recebido quando não vazio, mesmo se inválido, porque é o que o responsável
  precisa para corrigir o arquivo na origem. O valor não é reformatado. **Exceção**: em
  `LINHA_NAO_ASSOCIAVEL` o primeiro campo é um fragmento de texto de continuação, não um código,
  e o `CADPRO` fica vazio.

**Rationale**: um motivo por registro atende FR-036 ("o motivo") e SC-003 (uma linha de exceção por
registro recusado) sem transformar o relatório em lista de erros cruzados.

## R6 — Quantidade: gramática, escala e arredondamento

**Decision**:

- `QUAN3` é aparado de espaços **apenas para interpretação numérica** (não é texto preservado).
- Gramática aceita (convenção brasileira, FR-012): sinal `-` opcional; parte inteira `[0-9]+` **ou**
  agrupada por milhar `[0-9]{1,3}(\.[0-9]{3})+`; parte decimal opcional `,[0-9]+`. Exemplos
  válidos: `0`, `0,000`, `10`, `1.234,5`, `53,4000000000001`. Inválidos: `1.5`, `1,2,3`, `abc`,
  `1 234`, `,5`.
- Conversão para `Decimal` sem passar por `float`, quantizada para 3 casas com `ROUND_HALF_UP`
  (FR-012, SC-004). O caso da spec: `53,4000000000001` → `53.400`.
- "Negativa" é decidida sobre o valor **antes** do arredondamento: `-0,0001` é recusado. `-0` e
  `-0,000` valem zero e são aceitos.

**Rationale**: `Decimal` preserva a precisão legítima; o arredondamento só absorve o ruído de ponto
flutuante descrito na spec. `ROUND_HALF_UP` é o arredondamento comercial usual. A spec não fixa o
modo, e no arquivo real nenhum valor cai exatamente no meio entre dois milésimos. **Interpretação
I-3**.

**Alternatives considered**: `float` (reintroduziria o ruído); `ROUND_HALF_EVEN` (correto, mas menos
intuitivo para conferência manual contra o SCPI); recusar valores com mais de 3 casas
significativas (criaria regra não pedida — FR-012 manda arredondar).

## R7 — Modelo de saldo e origem do saldo inicial

**Decision**: o saldo vive no próprio `Material` (`saldo`), ao lado de `saldo_inicial` e
`execucao_origem` (FK para a execução que criou o material). Detalhes em
[data-model.md](./data-model.md).

- `saldo_inicial` e `execucao_origem` são gravados só na inserção e nunca mais alterados. Eles
  tornam o saldo inicial identificável como carga do SCPI e distinguível das movimentações futuras
  (FR-016, `INV-MOV-002`, `INV-STOCK-002`).
- `saldo` é o saldo físico corrente. Nesta feature ele só é escrito na inserção. A reimportação
  **nunca** o inclui na lista de campos atualizados (FR-028, SC-009).
- Constraints de banco: `saldo >= 0` e `saldo_inicial >= 0` (`INV-STOCK-001`, Constitution III).
- `DecimalField(max_digits=15, decimal_places=3)`, ou seja, 12 dígitos inteiros.

**Rationale**: o produto tem um único almoxarifado físico (`PRODUCT.md`, ROADMAP) e ainda não há
ledger de movimentações. Um modelo separado de saldo ou de ledger agora seria especulação
(Constitution I). As futuras operações (`ENT`, `INV`...) atualizarão `saldo` com transação e lock,
e registrarão a movimentação correspondente (`INV-MOV-002`). `saldo_inicial` + execução de origem
permitem a elas reconciliar `saldo = saldo_inicial + Σ movimentações` sem migração de dados.

**Alternatives considered**: registrar o saldo inicial como uma "movimentação de importação"
(rejeitado: o enum de origens de movimentação ainda não existe, e `INV-MOV-002` atribui à
importação uma rastreabilidade própria); tabela `SaldoMaterial` 1:1 (rejeitado: sem problema
concreto a resolver hoje).

## R8 — Prévia sem persistência e confirmação explícita (FR-044, FR-044a)

**Decision**:

1. `POST /catalogo/importacao/` recebe o arquivo, valida tamanho e decodificação, e guarda na
   **sessão do usuário** um "pedido de prévia": `token` (UUID4), nome do arquivo, tamanho,
   SHA-256 e o conteúdo comprimido (`zlib` + base64). Depois redireciona (PRG) para
   `GET /catalogo/importacao/previa/`. Nenhum `Material`, execução, exceção, divergência ou
   alteração cadastral é gravado nessa etapa.
2. `GET /catalogo/importacao/previa/` recalcula o **plano de importação** a partir do conteúdo em
   sessão e do estado atual do banco, **só com leituras**, e mostra totais, exceções e divergências
   com paginação. A página traz o formulário de confirmação com o `token` e a **impressão digital
   do plano** (SHA-256 de uma serialização canônica do plano: hash do arquivo, inserções,
   atualizações com os campos alterados, recusas com motivo e divergências com os valores).
3. `POST /catalogo/importacao/confirmar/` abre uma transação, adquire um advisory lock
   transacional do PostgreSQL (`pg_advisory_xact_lock`) dedicado à importação do catálogo,
   **recalcula** o plano dentro da transação e compara a impressão digital com a enviada:
   - iguais → aplica o plano (R9) e grava a execução com o `token` da prévia;
   - diferentes → não grava nada e mostra "a prévia ficou desatualizada", com a prévia recalculada
     para nova confirmação.
4. `POST /catalogo/importacao/cancelar/` descarta o pedido da sessão.
5. O pedido é removido da sessão só depois do commit. Um novo envio substitui o pedido anterior
   (uma prévia pendente por sessão).

**Idempotência**: logo depois de adquirir o advisory lock, e antes de recalcular o plano, a
confirmação verifica se já existe `ExecucaoImportacao` com o `token` recebido. Se existir, não grava
nada e responde "esta prévia já foi confirmada", redirecionando à execução existente. Como o lock
serializa as confirmações, essa checagem é determinística, inclusive para dois envios concorrentes
da mesma sessão. `ExecucaoImportacao.token_previa` também é único no banco, como última defesa.

**Rationale**:

- FR-044a proíbe efetivar inserção, atualização ou registro de divergência antes da confirmação.
  Guardar o arquivo recebido em estado transitório da sessão não é registro do resultado da
  importação. É o mesmo tipo de estado que a sessão já guarda. Fica vinculado ao usuário
  autenticado e expira com a sessão.
- Recalcular e comparar a impressão digital garante que o que se efetiva é **exatamente** o que o
  responsável viu e confirmou, mesmo que o catálogo ou os saldos mudem entre prévia e confirmação
  (hoje só por outra importação; no futuro, por movimentações).
- O tamanho real (385 KB, ~100 KB comprimido) torna o custo da sessão desprezível. O limite de
  envio é 10 MB (R12).

**Alternatives considered**: reenviar o arquivo na confirmação (rejeitado: atrito e risco de
confirmar arquivo diferente do previsto); tabela de staging (rejeitado: é persistência em banco
de domínio antes da confirmação e exige rotina de limpeza); arquivo temporário em disco
(rejeitado: exige diretório privado, limpeza e storage compartilhado entre processos, sem ganho no
volume real); campo oculto assinado com o conteúdo (rejeitado: esbarra em
`DATA_UPLOAD_MAX_MEMORY_SIZE` de 2,5 MB e devolve o arquivo inteiro ao navegador).

**Critério para revisitar**: se o arquivo real passar de alguns MB, trocar o armazenamento
transitório por arquivo em disco privado. O contrato da prévia não muda.

## R9 — Efetivação atômica, concorrência e rollback (FR-038, `INV-STOCK-004`)

**Decision**: a confirmação inteira roda em um único `transaction.atomic()`:

1. `pg_advisory_xact_lock(<chave constante da importação SCPI>)` serializa confirmações
   concorrentes, da mesma sessão ou de usuários diferentes.
2. Os materiais existentes cujo `CADPRO` está no arquivo são lidos com `select_for_update()`,
   **ordenados por `pk`** (ordem de lock determinística). A leitura do `saldo` para a divergência
   fica consistente dentro da transação.
3. Recalcula o plano e compara a impressão digital (R8).
4. Cria a `ExecucaoImportacao`, insere materiais novos (`bulk_create` em lotes), atualiza só os
   campos cadastrais alterados (`bulk_update` com lista explícita de campos, **sem** `saldo`,
   `saldo_inicial`, `cadpro` e `execucao_origem`), e grava `AlteracaoCadastralMaterial`,
   `ExcecaoImportacao` e `DivergenciaSaldo`.
5. Qualquer exceção desfaz tudo, inclusive a própria execução. O usuário recebe uma mensagem
   genérica (Constitution VI), o erro vai para o log (R13) e o pedido de prévia permanece na sessão
   para nova tentativa.

Defesas de banco como última linha (Constitution III): `UNIQUE(cadpro)` (`INV-CATALOG-002`), `CHECK`
de formato de `cadpro` (`INV-CATALOG-001`), `CHECK saldo >= 0` (`INV-STOCK-001`), `CHECK
recebidos = inseridos + atualizados + rejeitados` (FR-034, SC-003) e `CHECK diferenca =
saldo_arquivo - saldo_wms`.

**Rationale**: o advisory lock é o recurso mais simples para serializar uma operação global sem
travar tabelas que futuras operações de estoque vão usar. É recurso específico do PostgreSQL,
permitido pela Constitution (Restrições Tecnológicas).

**Alternatives considered**: `LOCK TABLE catalogo_material` (bloquearia leituras e futuras
movimentações além do necessário); confiar só no `UNIQUE` (garante unicidade, mas não a
correspondência prévia↔efetivação nem a contagem correta).

## R10 — Atualização cadastral, "atualizados" e rastreabilidade (FR-026, FR-032, FR-034)

**Decision**:

- Campos cadastrais atualizáveis por reimportação (FR-026, `INV-CATALOG-004`): `descricao` (DISC1),
  `unidade` (UNID1), `detalhamento` (DISCR1), `grupo`, `subgrupo`, `nome_grupo`, `nome_subgrupo`.
- **"Atualizados"** = registros aceitos cujo `CADPRO` já existe no catálogo, **com ou sem**
  mudança de valor. É a única leitura compatível com a identidade exigida por FR-034/SC-003
  (recebidos = inseridos + atualizados + rejeitados). A execução guarda também, como subtotal
  informativo, quantos desses registros **efetivamente mudaram** algum campo. Isso torna
  verificável o edge case "reexecução do mesmo arquivo sem alterações: nenhum dado alterado".
  **Interpretação I-4**.
- Só materiais com mudança real recebem escrita. Cada campo alterado gera uma linha
  `AlteracaoCadastralMaterial` (campo, valor anterior, valor novo), ligada à execução, que
  identifica quem e quando (FR-032).

**Rationale**: evita escrita e histórico ruidosos em reimportações sem mudança e mantém a soma
exigida pela spec.

## R11 — Divergências e materiais ausentes (FR-029 a FR-031, `INV-STOCK-003`)

**Decision**:

- Divergência só para registro **aceito** de `CADPRO` **já existente** cujo valor de arquivo
  (já arredondado, R6) difere do `saldo` atual, **sem tolerância** (Assumptions). Material novo
  nasce com o saldo do arquivo, então não gera divergência.
- `diferenca = saldo_arquivo − saldo_wms`. Sinal positivo: o SCPI tem mais do que o WMS. A
  convenção aparece na interface junto dos dois valores, que são sempre exibidos (FR-029).
- Cada execução grava as próprias divergências. Uma divergência persistente reaparece em cada
  reimportação, sempre ligada à execução que a detectou (FR-030). Nenhum saldo é alterado e
  nenhuma operação é bloqueada (`INV-STOCK-003`, FR-047).
- **Ausentes do arquivo** (FR-031) = materiais do catálogo cujo `CADPRO` não aparece em nenhum
  registro do arquivo com `CADPRO` bem formado, aceito ou recusado. Só a contagem é guardada na
  execução. Nenhum material é alterado ou excluído.

## R12 — Autorização e validação de entrada

**Decision**:

- Checagem por papel explícito via `User.tem_papel()` (já existente, sem herança — regra 3 da
  matriz), com os mixins nativos do Django: `LoginRequiredMixin` + `UserPassesTestMixin`.
  Verificado no Django 6.1.1 instalado: `AccessMixin.handle_no_permission()` redireciona anônimo
  ao login e levanta `PermissionDenied` (403) para autenticado sem permissão. Um mixin de uma linha
  (`ExigePapelMixin`, atributo `papel_exigido`) evita repetir o `test_func`.
  - Consulta do catálogo: `ROLE-REQUESTER` (`PERM-MATERIAL-VIEW`). O superusuário técnico, sem
    papéis, recebe 403 — coerente com as Notas de composição da matriz. Isso é mais estrito que o
    texto de FR-045 ("exigir autenticação"), e é a matriz canônica que define **quem**.
  - Envio, prévia, confirmação e cancelamento: `ROLE-WAREHOUSE-HEAD` (`PERM-SCPI-IMPORT-EXECUTE`),
    verificado a cada requisição, inclusive na confirmação. A autorização é checada **antes** de
    validar ou interpretar o arquivo. O `CsrfViewMiddleware` pode já ter recebido o upload para ler
    o token, sem efeito de domínio.
  - Histórico e detalhe de execuções: `ROLE-WAREHOUSE-HEAD` (`PERM-SCPI-IMPORT-HISTORY-VIEW`).
  - Usuário inativo: bloqueio nativo do Django, já coberto pela 002 (`INV-AUTH-001`).
- A visibilidade dos links na Home segue a mesma checagem de papel, calculada na view. Esconder o
  link não é a autorização (Constitution VI; matriz, regra 6).
- Upload: `forms.FileField` com limite de **10 MB** validado no formulário e extensão não usada como
  critério de validade (o conteúdo é validado pelo parser). O nome do arquivo é exibido escapado
  pelo template e guardado com no máximo 255 caracteres.

**Alternatives considered**: permissões do `django.contrib.auth` (`has_perm`) (rejeitado: duplicaria
a matriz em outra fonte e a 002 já estabeleceu `PapelUsuario` como a única forma de ter papel);
decorator próprio (rejeitado: os mixins nativos bastam).

## R13 — Observabilidade (Constitution XIV)

**Decision**: logger `catalogo.importacao`. Uma linha `INFO` por confirmação efetivada (id da
execução, id do usuário, SHA-256 do arquivo e totais); `WARNING` para prévia desatualizada ou
confirmação duplicada; `ERROR` com traceback para falha na efetivação. Nunca registra conteúdo do
arquivo nem descrições de material.

## R14 — Fixtures de teste e validação contra o arquivo real

**Decision**:

- Fixtures **sintéticas e versionadas** em `tests/fixtures/catalogo/`, escritas em bytes exatos
  (BOM, CRLF, `;` final, cabeçalho real de 21 colunas na ordem observada). Elas reproduzem cada
  caso documentado na spec: `000.000.002` com zeros à esquerda; saldo `0,000`; quantidade vazia;
  descrições iguais com códigos distintos; `DETALHAMENTO` vazio; `CADPRO` duplicado; unidades
  `UN`/`UND`/`M`/`MT`/`MTS`; classificação preenchida e vazia; `004.001.002` com `DISC1` partida em
  três linhas físicas; continuação em `DISCR1`; `COTOVELO GALVANIZADO ¾" X 90º`; `53,4000000000001`;
  código fora do formato; código ausente; quantidade negativa, não numérica e com milhar; descrição
  e unidade ausentes; continuação no fim do arquivo; cabeçalho sem coluna obrigatória; arquivo vazio
  e só cabeçalho. Nenhum dado do arquivo real é copiado. Descrições e códigos são fictícios, exceto
  os literais que a própria spec cita.
- Um **teste opcional de validação real** (`tests/test_catalogo_arquivo_real.py`) roda só quando a
  variável de ambiente `SCPI_CSV_REAL` aponta para o arquivo. Sem ela, o teste é *skipped* com
  motivo explícito. Com ela, verifica: 1588 recebidos, 0 rejeitados, todo `CADPRO` idêntico ao do
  arquivo (SC-001), 22 campos por registro (SC-002), quantidades na escala de 3 casas (SC-004) e
  saldo igual ao do arquivo após a carga (SC-008).
- A execução desse teste é o **aceite** de SC-001/SC-002/SC-004/SC-008 contra o dado real. Segundo
  o ROADMAP, a pendência de artefato bloqueia validação e aceite, não implementação. O arquivo está
  hoje só localmente em `docs/domain-legacy/` (fora do Git). Decidir se isso satisfaz a pendência
  "disponibilização de amostra representativa" do ROADMAP cabe ao dono do produto.

## R15 — Busca por código e por descrição (FR-039, FR-040, FR-042, SC-006, SC-007)

**Decision**:

- **Código**: igualdade exata em `cadpro` (índice único). O termo digitado é aparado de espaços nas
  bordas, porque é entrada do usuário e não dado do SCPI. Nunca é completado, preenchido com zeros
  ou tratado como prefixo. Termo fora do formato `XXX.YYY.ZZZ` não faz consulta e devolve estado de
  validação explícito ("informe o código completo").
- **Descrição**: coluna técnica derivada `descricao_busca`, mantida junto de `descricao`, com a
  descrição sem acentos (NFKD sem marcas combinantes) e `casefold()`. O termo de busca passa pela
  mesma função e é separado em palavras por espaço em branco (`str.split()`); cada palavra vira um
  filtro `descricao_busca__contains` combinado por E (todas as palavras, qualquer ordem, cada uma
  parcial; FR-040 emendado em 2026-09-21). Termo só com espaços = sem filtro. Índice GIN com
  `gin_trgm_ops` (`pg_trgm`) atende cada `LIKE '%palavra%'` e o PostgreSQL combina os resultados
  por bitmap AND (Constitution X); palavras com menos de 3 caracteres não aproveitam trigramas, mas
  continuam corretas. `descricao` original permanece intocada (FR-017).
- Formulário único de filtro com dois campos (`codigo`, `descricao`), ambos opcionais. Sem filtro,
  lista o catálogo paginado em ordem de `cadpro`.
- `Paginator` do Django, 50 por página, com `.only()` dos campos exibidos (FR-042).

**Rationale**: `unaccent` não é `IMMUTABLE` e não pode ser usado diretamente em índice de expressão
sem uma função wrapper. A coluna derivada em Python dá a mesma normalização nos dois lados, sem SQL
customizado. `pg_trgm` é extensão *trusted* no PostgreSQL ≥ 13 e é criada por migração
(`TrigramExtension`, exige `django.contrib.postgres` em `INSTALLED_APPS`).

**Alternatives considered**: `unaccent` + wrapper imutável (SQL próprio e mais frágil); busca por
`icontains` sem índice (viola Constitution X no porte esperado de dezenas de milhares); campo único
com detecção automática de código (rejeitado: dois campos explícitos são mais previsíveis e
testáveis); busca por trecho contínuo (versão original, substituída pela decisão de 2026-09-21);
full-text search do PostgreSQL (rejeitado: stemming e dicionário mudariam a correspondência parcial
de palavras e exigiriam configuração de idioma sem ganho no porte do catálogo).

## R16 — Interface: templates, HTMX e progressive enhancement

**Decision**:

- Django Templates. HTMX **somente** na consulta do catálogo (filtro e paginação atualizam a região
  de resultados com `hx-get`, `hx-push-url` e `hx-indicator` para o estado de carregamento, FR-043).
  A view detecta `HX-Request` e devolve só o fragmento. Sem JavaScript, o mesmo formulário faz `GET`
  de página inteira (Constitution IX).
- Estado de erro da consulta: erro de validação renderizado pelo servidor; falha de rede ou 5xx na
  troca HTMX aparece em um alerta na própria região, via atributo `hx-on` (sem arquivo JS próprio).
- Importação, prévia, confirmação e histórico usam formulários e páginas comuns (POST/redirect/GET),
  sem HTMX: fluxos de ação única, em que a atualização parcial não traz ganho.
- HTMX é versionado localmente em `static/vendor/htmx/` (arquivo minificado com versão fixa no nome
  e licença), sem CDN e sem pacote Python. A Constitution já estabelece HTMX como a tecnologia de
  interatividade. Nenhuma outra biblioteca é adicionada.
- Componentes do `DESIGN.md` que nascem aqui (Table, Pagination, Filter Bar, Empty State, Loading
  Indicator, File Upload, Page Header, Status/Badge e o passo de confirmação da prévia) vão para
  `static/css/components.css` como primitivos compartilhados. A confirmação é a própria página de
  prévia, com botão primário que reitera o resultado esperado. Não há modal: não precisa de
  JavaScript e cumpre o "Confirmation / Dialog" do `DESIGN.md`.
- Pontos de entrada: links condicionais na Home mínima da 002 ("Catálogo de materiais"; "Importar
  catálogo" e "Histórico de importações" para o chefe do almoxarifado). O app shell/sidebar continua
  **em aberto** no `DESIGN.md` e não é decidido aqui.

---

## Interpretações confirmadas

Nenhuma delas é conflito com fonte canônica. Todas são leituras técnicas de pontos que a spec não
fixa. **Confirmadas pelo dono do produto em 2026-09-21** (I-1 a I-6):

| ID | Interpretação | Onde |
|---|---|---|
| I-1 | Arquivo em que `CADPRO` não é a primeira coluna é recusado por inteiro | R4 |
| I-2 | Arquivo de 0 bytes = "arquivo vazio": zero recebidos, sem erro | R4 |
| I-3 | Arredondamento de `QUAN3` para 3 casas usa `ROUND_HALF_UP` | R6 |
| I-4 | "Atualizados" inclui registros existentes sem mudança; subtotal "com alteração" é informativo | R10 |
| I-5 | Linha com contagem completa de separadores e código inválido/ausente é um registro próprio (recusado com o motivo do código) | R3 |
| I-6 | "Prévia sem persistência" (FR-044a) significa nenhuma escrita em tabela de domínio. O arquivo recebido fica como estado transitório na sessão do usuário até confirmar ou cancelar | R8 |
