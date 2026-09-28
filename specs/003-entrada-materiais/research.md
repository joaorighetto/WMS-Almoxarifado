# Research — Entrada de Materiais

Decisões técnicas da feature `003-entrada-materiais`. Base: [spec.md](./spec.md), o código entregue
da 001 (`catalogo/`), da 002 (`contas/`) e da 004 (`fornecedores/`), e as matrizes canônicas
(`docs/domain/permissions-matrix.md` v1.1, `docs/domain/invariants-matrix.md`).

## R1 — App novo `estoque`, com módulo de domínio para as operações

**Decisão**: novo app `estoque`, que guarda a movimentação de estoque e a primeira operação que a
produz, a entrada. As duas operações que alteram saldo — `registrar_entrada` e `estornar_entrada` —
ficam em `estoque/entradas.py`, chamadas pelas views e pelos testes. `catalogo` continua dono de
`Material` e do saldo inicial. Nenhuma view de `estoque` escreve em `Material` diretamente.

**Rationale**: `MovimentacaoEstoque` é o fato transversal que `SAE`, `ATE`, `DEV`, `INV` e `HIS` vão
usar. Não pertence a `catalogo`, que é o cadastro, nem a um app `entradas`, que amarraria o fato
comum a uma única operação. Cada operação afeta quatro modelos (`Entrada`, `ItemEntrada`,
`MovimentacaoEstoque`, `Material`) sob locks numa só transação, e a mesma regra precisa ser chamada
pela view de confirmação e pelos testes de concorrência. Na view, ela ficaria misturada com HTTP e
formulário; num manager, atravessaria quatro modelos. É o mesmo argumento de
`catalogo/importacao.py` (Complexity Tracking).

**Alternativas**: app `entradas` (rejeitado: a movimentação ficaria num app de operação); lógica em
`Material.aumentar_saldo()` (rejeitado: o saldo sozinho não cobre a movimentação, a referência nem
o estorno, que são a parte difícil); camada genérica de "operação de estoque" (rejeitado: com uma
operação só, seria especulativa, Constitution I).

## R2 — Movimentação de estoque genérica, com origem por chave estrangeira

**Decisão**: `MovimentacaoEstoque` guarda o que qualquer operação futura também terá: material,
tipo, variação com sinal, saldo anterior, saldo posterior, autor e momento. A origem é uma FK
anulável por tipo de operação: hoje `item_entrada` e `estorno_entrada`. Um `CHECK` amarra cada
tipo à sua origem e ao sinal da variação. Tipos atuais: `ENTRADA` e `ESTORNO_ENTRADA`.

- `CHECK saldo_posterior = saldo_anterior + variacao`, `CHECK variacao <> 0`,
  `CHECK saldo_posterior >= 0`.
- `UNIQUE (item_entrada, tipo)`: um movimento de entrada e no máximo um de estorno por item.

**Rationale**: `INV-MOV-002` pede origem, ator, quantidade e momento. Os saldos anterior e posterior
tornam cada movimento auditável sem reconstrução (Constitution XIV) e são o que `HIS` vai mostrar.
Uma FK por tipo de origem mantém a integridade referencial no banco. Uma operação futura acrescenta
a própria FK e um ramo no `CHECK`. O schema é efêmero (Constitution XIII), então isso não custa
migration. A matriz registra que "não há enum canônico" de origens (seção 4). Por isso o tipo é uma
lista de código extensível, não um vocabulário de domínio fechado.

**Alternativas**: `GenericForeignKey` (rejeitado: sem FK real nem `PROTECT` no banco); tabela de
movimentação por operação (rejeitado: `HIS` teria de unir N tabelas, e o fato comum se dividiria);
quantidade sempre positiva mais direção pelo tipo (rejeitado: a variação com sinal torna a soma e o
`CHECK` de saldo diretos).

## R3 — Composição sem rascunho: o estado viaja no próprio formulário

**Decisão**: a entrada em composição não é guardada em lugar algum do servidor. Cada ação da tela —
buscar material, adicionar, remover, buscar e escolher emitente, revisar, voltar — é um `POST` para
a mesma rota, com o formulário inteiro, e a resposta devolve o formulário re-renderizado. Com HTMX,
só a região do formulário é trocada; sem JS, a página inteira é recarregada. "Revisar" valida tudo
e devolve o resumo (FR-008) com os dados em campos ocultos. "Confirmar" reenvia esses dados, que o
servidor **valida de novo por inteiro** antes de gravar.

**Rationale**: FR-008 proíbe persistir antes da confirmação e exclui rascunho. Sem estado no
servidor, duas abas não se atropelam, nada fica órfão e não há expiração a tratar. O precedente de
sessão da 001/004 existe porque lá o conteúdo é um arquivo. Aqui são poucos campos. Adulterar os
campos ocultos não abre brecha: a confirmação revalida autorização, motivo, referência, emitente,
materiais e quantidades como se fosse o primeiro envio (Constitution V).

**Alternativas**: resumo guardado na sessão (rejeitado: uma chave única por usuário atropela duas
abas, e o conteúdo é pequeno demais para justificar); rascunho em banco (proibido por FR-008);
itens montados por JavaScript no cliente (rejeitado: Princípios II e IX).

## R4 — Idempotência da confirmação por chave única

**Decisão**: o `GET` da tela de composição gera um UUID, a `chave_confirmacao`, que acompanha todos
os `POST` da composição e do resumo. `Entrada.chave_confirmacao` é `UNIQUE`. `registrar_entrada`
procura a chave **antes de qualquer outra validação**. Se já existe entrada com essa chave, levanta
`EntradaJaRegistrada(entrada)` sem gravar nada. Uma corrida entre duas requisições com a mesma chave
é resolvida pelo índice: a segunda espera o commit da primeira, recebe `IntegrityError` num
savepoint e é tratada como `EntradaJaRegistrada`. A view redireciona para o detalhe da entrada
existente com o aviso "Esta entrada já foi registrada".

O estorno não precisa de chave: `EstornoEntrada.entrada` é `OneToOne` (R7), e o lock da entrada
serializa pedidos simultâneos.

**Rationale**: FR-013 e SC-005 cobrem clique duplo, reenvio e nova tentativa após falha de rede. É o
mesmo desenho validado de `token_previa`, na 001 e na 004.

**Alternativas**: desabilitar o botão por JS (só aprimoramento, não garantia); bloquear duplicata
por conteúdo (rejeitado: duas entradas legítimas podem ter o mesmo conteúdo em documentos
diferentes, e a referência já tem regra própria em R6).

## R5 — Concorrência: locks em ordem fixa e saldo calculado sob lock

**Decisão**: `registrar_entrada`, numa única `transaction.atomic()`:

1. chave já usada? → `EntradaJaRegistrada` (R4);
2. emitente, se houver: `select_for_update()` na linha do `Fornecedor` e reconferência de
   `bloqueado` (R10);
3. `Material.objects.filter(pk__in=...).select_for_update().order_by("pk")`;
4. para cada item: `saldo_posterior = saldo + quantidade`; acima do máximo representável →
   `SaldoAcimaDoLimite` (R11);
5. insere `Entrada` num savepoint: violação da referência única → `ReferenciaJaUsada`; da chave →
   `EntradaJaRegistrada`;
6. insere os `ItemEntrada`, atualiza `Material.saldo` (`save(update_fields=["saldo"])`) e insere uma
   `MovimentacaoEstoque` por item, com os saldos lidos sob lock e o mesmo `registrada_em`.

`estornar_entrada`, numa única transação: `select_for_update()` na `Entrada`; se já estornada →
`EntradaJaEstornada`; depois os materiais dos itens por `pk` crescente; se algum saldo ficaria
negativo → `EstornoBloqueadoPorSaldo(itens)`, sem efeito; senão insere `EstornoEntrada`, marca
`Entrada.estornada`, reduz os saldos e insere uma movimentação `ESTORNO_ENTRADA` por item.

Ordem de lock das operações de estoque: `Entrada` → `Fornecedor` → `Material` por `pk` crescente.
Entre entradas e estornos, não há ciclo. A de fornecedores trava só `Fornecedor`. A reimportação do
catálogo trava `Material` em lotes de 500 CADPRO, com `pk` crescente só dentro de cada lote
(`catalogo/importacao.py`, `calcular_plano(bloquear=True)`). Depois de uma importação que insira
materiais com `pk` alto e CADPRO baixo, uma entrada com materiais de lotes diferentes pode fechar
um ciclo com uma reimportação simultânea. O PostgreSQL detecta o deadlock e aborta um dos lados:
nada é gravado parcialmente (`INV-STOCK-004`), e o usuário recebe o erro genérico e tenta de novo.
Alinhar a reimportação ao `pk` global mexe em código entregue da 001 e fica fora desta feature. A
reimportação é ocasional e feita pelo chefe; a colisão exige simultaneidade e materiais em lotes
distintos.

**Rationale**: FR-011, FR-012, FR-026, FR-027, FR-028 e Constitution III. O `select_for_update` é
necessário, e não só `F("saldo") + q`, porque a movimentação precisa do saldo anterior e posterior
exatos, e o estorno precisa checar o saldo antes de reduzir. O `CHECK saldo >= 0` de `Material`
continua sendo a última defesa de `INV-STOCK-001`.

**Alternativas**: `UPDATE ... SET saldo = saldo + q RETURNING` (válido para a entrada, mas cria dois
caminhos diferentes entre registro e estorno sem ganho mensurável); advisory lock global de
estoque (rejeitado: serializa entradas de materiais distintos sem necessidade).

## R6 — Referência: gravada aparada, única entre entradas não estornadas

**Decisão**:

- `numero_documento` é gravado depois de `strip()` e sem outra normalização: pontos, traços, zeros e
  caixa ficam como digitados. "Preservado como informado" (FR-007) se refere ao conteúdo; os espaços
  das pontas são descartados porque a própria spec os ignora na comparação (FR-007a).
  `CHECK trim(numero_documento) <> ''`.
- `UniqueConstraint(fields=["tipo_documento", "numero_documento", "emitente"],
  condition=Q(estornada=False), nulls_distinct=False)`. `nulls_distinct=False` (PostgreSQL 15+, já
  em uso: PostgreSQL 16) faz "ambas sem emitente" contar como a mesma referência, como exige FR-007a.
- A mesma checagem roda antes no "Revisar", para a mensagem apontar a entrada existente. O índice é
  a garantia sob concorrência: de entradas simultâneas com a mesma referência, efetiva no máximo uma.
- `CHECK` de emitente obrigatório: `emitente IS NOT NULL OR motivo IN (DOACAO_RECEBIDA,
  EMPRESTIMO_DEVOLVIDO)`.
- `CHECK motivo IN (...)` e `CHECK tipo_documento IN (...)`: as listas fechadas também valem no banco.

**Rationale**: FR-006, FR-007, FR-007a. Gravar aparado deixa o índice comparar exatamente o que a
spec manda comparar, sem índice de expressão.

**Alternativas**: índice sobre `Trim(numero_documento)` preservando os espaços (rejeitado:
complexidade sem valor, porque espaço na ponta nunca é informação); normalizar zeros e pontuação
(rejeitado: a spec proíbe outra normalização).

## R7 — Imutabilidade garantida também no banco

**Decisão**: além de não existir caminho de edição (sem admin, sem rota de alteração, sem método que
atualize), o banco recusa alteração dos fatos. Um handler de `post_migrate` em `estoque/apps.py`
cria, de forma idempotente (`CREATE OR REPLACE FUNCTION`, `DROP TRIGGER IF EXISTS`), triggers
`BEFORE UPDATE OR DELETE`:

- `ItemEntrada`, `EstornoEntrada`, `MovimentacaoEstoque`: qualquer `UPDATE` ou `DELETE` levanta erro;
- `Entrada`: `DELETE` levanta erro; `UPDATE` só é aceito quando a única mudança é
  `estornada` de `false` para `true` (comparação de `to_jsonb(OLD) - 'estornada'` com
  `to_jsonb(NEW) - 'estornada'`).

`EstornoEntrada.entrada` é `OneToOneField(PROTECT)`: o banco garante no máximo um estorno por
entrada (`INV-ENT-001`). Todas as FKs usam `PROTECT`.

**Rationale**: `INV-MOV-001` é CRÍTICA e a matriz a classifica como "domínio; banco/constraint".
Constitution III manda proteger no banco o que o banco consegue expressar. `TRUNCATE`, usado pelo
pytest-django em testes transacionais, não dispara trigger de linha, e `make resetdb` recria o
schema. Então os triggers não atrapalham testes nem desenvolvimento. Hoje o schema é criado por
`migrate --run-syncdb`. Quando as migrations voltarem (Constitution XIII), esse SQL passa para uma
`RunSQL` versionada.

**Alternativas**: só ausência de caminho na aplicação, como no catálogo (rejeitado para fatos de
estoque: `QuerySet.update()` ou o shell os alterariam em silêncio); `estornada` derivada da
existência do estorno (rejeitado: o índice parcial de R6 precisa de uma coluna na própria tabela).

## R8 — Quantidade digitada: gramática brasileira, sem arredondar

**Decisão**: `estoque/quantidade.py::interpretar_quantidade_recebida(texto) -> Decimal`, com
recusas próprias:

- vazio → "Informe a quantidade.";
- gramática: parte inteira simples (`[0-9]+`) ou agrupada por ponto (`[1-9][0-9]{0,2}(\.[0-9]{3})+`),
  vírgula decimal opcional, sem sinal. Fora dela → "Use números, com vírgula para decimais
  (ex.: 1.250,5).";
- mais de três casas decimais → recusa, sem arredondar (FR-005, Edge Cases);
- zero → "A quantidade deve ser maior que zero.";
- mais de 12 dígitos inteiros → fora do limite (R11).

Um grupo iniciado por zero (`0.750`) não é milhar válido e é recusado, em vez de lido como 750. Isso
evita que quem digita ponto decimal registre mil vezes a quantidade.

**Rationale**: `catalogo.leitura_scpi.interpretar_quantidade` aceita sinal e arredonda em silêncio
(`ROUND_HALF_UP`), o que é certo para o arquivo e errado aqui. Uma função própria de ~30 linhas é
mais clara do que parametrizar a do catálogo, que já está entregue e testada (Constitution XII).

**Alternativas**: estender `interpretar_quantidade` com flags (rejeitado: mexe em código entregue
para servir a regras opostas); `forms.DecimalField` com `localize=True` (rejeitado: depende do
locale ativo e não diz por que a quantidade foi recusada).

## R9 — Busca de material e de emitente num campo único, reusando as primitivas

**Decisão**:

- **Material** (FR-003): um campo. Texto que casa com `catalogo.leitura_scpi.PADRAO_CADPRO` →
  `cadpro=` exato. Qualquer outro texto → cada palavra de `normalizar_para_busca(texto)` como
  `descricao_busca__contains`, combinadas por E. É a mesma regra da consulta do catálogo, aplicada
  ao que foi digitado. No máximo 20 resultados, ordenados por `cadpro`, com contagem do total e
  pedido para refinar quando passar disso. O material já incluído na entrada aparece como
  "Já incluído", sem ação de adicionar (FR-004).
- **Emitente** (FR-007): um campo. Só dígitos → `codif=` exato **ou** `documento_digitos=` exato.
  Texto com pontuação de CNPJ/CPF (só dígitos, `.`, `/` e `-`, com 3 dígitos ou mais) →
  `documento_digitos=`. Outro texto → palavras em `nome_busca__contains`. No máximo 20. Um
  fornecedor bloqueado aparece com o selo "Bloqueado" e o motivo, sem ação de escolher
  (`INV-SUPPLIER-005`).
- Sem extrair função comum de `catalogo`/`fornecedores`: a sobreposição são duas ou três linhas de
  filtro sobre primitivas já compartilhadas (`PADRAO_CADPRO`, `normalizar_para_busca`, os campos
  `descricao_busca`/`nome_busca`/`documento_digitos` e seus índices).

**Rationale**: SC-007 (menos de um minuto) pede um único campo, que decide sozinho entre código e
descrição. Os índices existentes (GIN trigram e btree) atendem à busca sem mudança. O limite de 20
mantém a resposta pequena (Constitution X).

**Alternativas**: reutilizar as telas de consulta num modal (rejeitado: sem modal no design system,
e escolher exige outra ação); extrair `filtrar_materiais`/`filtrar_fornecedores` (rejeitado agora:
semelhança pequena, Constitution XII; fica como candidata quando surgir um terceiro consumidor
real).

## R10 — Emitente bloqueado e inexistente

**Decisão**: o formulário guarda só o `pk` do emitente escolhido. Em "Revisar" e na confirmação, o
`pk` precisa existir e estar com `bloqueado=False`. Na confirmação, a checagem é feita com a linha
do fornecedor travada (R5). Assim, uma reimportação de fornecedores que o bloqueie ao mesmo tempo
ou vem antes, e a entrada é recusada, ou vem depois, e a entrada já foi registrada com emitente
liberado. Mensagem: "O fornecedor escolhido está bloqueado no SCPI; escolha outro emitente."

**Rationale**: `INV-SUPPLIER-005` (ALTA) e o edge case "bloqueado por uma reimportação entre o
preenchimento e a confirmação". A regra depende de outra tabela e muda com o tempo, então não cabe
num `CHECK`.

## R11 — Limites numéricos

**Decisão**: quantidade e saldo usam `DecimalField(max_digits=15, decimal_places=3)`, como
`Material.saldo`. O máximo representável é `999.999.999.999,999`. A quantidade é limitada na
leitura (R8), e o saldo resultante é checado sob lock (R5) → `SaldoAcimaDoLimite(material)`,
recusando a entrada inteira. `MovimentacaoEstoque.variacao` usa `max_digits=16` por ter sinal.

**Rationale**: FR-014. Sem a checagem prévia, o banco levantaria `DataError` genérico em vez da
mensagem pedida.

## R12 — Autorização

**Decisão**: reutiliza `catalogo.views.ExigePapelMixin`, como a 004:

- composição, resumo e confirmação da entrada → `papel_exigido = Papel.FUNCIONARIO_ALMOXARIFADO`
  (`PERM-STOCK-ENTRY-CREATE`);
- estorno → `Papel.CHEFE_ALMOXARIFADO` (`PERM-STOCK-ENTRY-REVERSE`);
- lista e detalhe → `PERM-STOCK-HISTORY-VIEW` aplicada à entrada (FR-021): um mixin local
  `ConsultaEntradasMixin(ExigePapelMixin)` sobrescreve `test_func` com
  `tem_papel(FUNCIONARIO_ALMOXARIFADO, AUDITOR)`.

Este é o recorte de `PERM-STOCK-HISTORY-VIEW` que vale para a entrada. Os escopos "o que criou" e
"setor que chefia" da matriz não se aplicam: a entrada não pertence a setor requisitante e só é
criada pelo almoxarifado. `HIS` implementará a capability inteira. O mixin local não pretende
servir de base para ela.

`INV-AUTH-001` vem da 002: `ModelBackend.get_user()` devolve anônimo para conta inativa. A view de
confirmação usa `request.user` do próprio `POST`, então um usuário desativado durante o
preenchimento cai no login sem efeito algum.

**Alternativas**: mudar `ExigePapelMixin` para aceitar vários papéis (rejeitado: altera código
entregue da 001 por um único caso; o mixin local tem três linhas).

## R13 — Interface

**Decisão**: telas do almoxarifado, desktop-first, com os componentes existentes: Page Header,
Filter Bar (buscas), Table (itens, resultados, lista), Badge (situação, bloqueado), Resumo de
totais, Confirmação com barra persistente, Alert, Empty State, Pagination, Retorno contextual. O
botão **Destrutivo** (`danger`), previsto em `DESIGN.md` e ainda sem uso, estreia no estorno. A
composição da entrada, com cabeçalho e tabela de itens editável na mesma folha, é padrão novo. Por
isso a entrega atualiza `DESIGN.md` e o sidecar por `impeccable document` (modo scan), conforme
"Manutenção incremental do DESIGN.md".

A Home passa a oferecer "Registrar entrada de materiais" (funcionário do almoxarifado) e "Consultar
entradas" (funcionário do almoxarifado e auditor), e o item ENT sai de `CAPACIDADES_PLANEJADAS`. O
item `HIS` continua planejado.

**Rationale**: Constitution VIII e o gate visual obrigatório (`impeccable critique` depois do
`code-reviewer`).

## R14 — Observabilidade

**Decisão**: logger `estoque.entradas`. `INFO` em entrada registrada (id, `pk` do autor, motivo,
número de itens) e em estorno efetivado (id da entrada, `pk` do autor). `WARNING` em recusa de
confirmação por concorrência: referência já usada, emitente bloqueado, estorno bloqueado por saldo.
`exception` em erro inesperado. Nunca o número do documento nem a justificativa, que são texto livre.

**Rationale**: Constitution XIV: identificar operação, ator e valores sem registrar texto livre em
log.
