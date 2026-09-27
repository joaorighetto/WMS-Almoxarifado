# Research — Importação do Cadastro de Fornecedores do SCPI

Decisões técnicas da feature `004-importacao-fornecedores`. Base: [spec.md](./spec.md), o código
entregue da 001 (`catalogo/`) e a análise do arquivo real (`docs/CSVs/fornecedores.csv`, só local).

## R1 — App novo, reuso só das peças já genéricas da 001

**Decisão**: novo app `fornecedores`. Reusa, sem alterar, as peças da 001 que já são independentes
do catálogo:

- `catalogo.views.ExigePapelMixin` (autorização por papel explícito);
- `catalogo.ordenacao.OrdenacaoMixin`/`ColunaOrdenacao` (ordenação de listas);
- `catalogo.leitura_scpi.decodificar`, `ArquivoRecusado`, `LIMITE_TAMANHO_ARQUIVO` e
  `normalizar_para_busca`;
- templates `catalogo/_paginacao.html`, `catalogo/_th_ordenavel.html`, `catalogo/_mensagens.html`,
  a biblioteca `catalogo_extras` e `catalogo/js/envio.js`.

O fluxo de importação (plano, impressão digital, lock, prévia em sessão, efetivação) é
reescrito em `fornecedores/importacao.py`, com a mesma forma de `catalogo/importacao.py`.

**Rationale**: o fluxo difere em pontos centrais — parser (terminador CRLF, e não recomposição por
padrão de `CADPRO`), conteúdo da sessão (R3), ausência de saldo e divergências — e há só dois
casos. Uma abstração genérica de "importação SCPI" com dois consumidores seria especulativa
(Constitution I). As peças reusadas já são genéricas e estáveis.

**Alternativas**: extrair um framework de importação compartilhado (rejeitado: especulativo,
refactor da 001 fora do escopo); mover `ExigePapelMixin` para um módulo comum (desejável, mas é
refactor de outra feature — registrado como melhoria separada, não feito aqui).

## R2 — Parser: registro termina em CRLF

**Decisão**: `fornecedores/leitura_fornecedores.py`, puro, sem banco.

1. `decodificar` da 001 (UTF-8 com ou sem BOM; byte inválido e U+0000 recusam o arquivo).
2. Arquivo vazio ou só com espaços: zero recebidos, sem erro (mesma regra da 001).
3. Se o texto contém `\n` mas nenhum `\r\n`, o arquivo é recusado
   (`ARQUIVO_TERMINADOR_INVALIDO`): sem CRLF não há como separar registros sem risco de mesclar
   campos.
4. Registros = `texto.split("\r\n")`; um último elemento vazio é descartado. Um `\n` isolado fica
   dentro do campo. Linha vazia fora do fim é ignorada (mesma decisão D-1 da 001).
5. Cabeçalho = primeiro registro, separado por `;`. Colunas obrigatórias (FR-010) ausentes ou
   duplicadas recusam o arquivo. A posição das colunas não é exigida.
6. Cada registro é separado por `;`, com aspas literais. Número de campos diferente do cabeçalho →
   recusa `COLUNAS_DESLOCADAS`.
7. Validação por registro, primeiro motivo que se aplica: `CODIF` vazio → `CODIF_AUSENTE`; `CODIF`
   fora de `[0-9]+` (dígitos ASCII, nunca `\d`) → `CODIF_INVALIDO`; `NOME` vazio após `strip()` →
   `NOME_AUSENTE`; `BLOQ_OPCAO` fora de {`S`, `B`} → `SITUACAO_BLOQUEIO_INVALIDA`.
8. Depois, `CODIF` repetido entre registros ainda aceitos → todas as ocorrências recusadas com
   `CODIF_DUPLICADO`.
9. Valores aceitos são preservados como recebidos, sem `strip()`. Só o `strip()` do nome decide se
   ele está vazio.

Numeração de linha: número do registro lógico, com o cabeçalho = linha 1. Como só CRLF separa
registros, o número coincide com a linha que um editor mostra, exceto depois do registro com LF
embutido. A recusa guarda `linha` e, para facilitar a localização, o `CODIF` quando válido.

**Rationale**: no arquivo real, os 10.035 registros têm exatamente 132 campos quando separados por
CRLF, e o único LF embutido fica no campo `CONTATO`. Recusar arquivo sem CRLF evita que um arquivo
convertido por um editor seja lido errado em silêncio.

**Alternativas**: reusar a recomposição da 001 por padrão do primeiro campo (rejeitado: `CODIF` não
tem formato distintivo, e um nome pode começar com dígitos); `csv` da stdlib (rejeitado pelo mesmo
motivo da 001: interpreta aspas).

## R3 — A prévia guarda só a projeção mínima, nunca o arquivo

**Decisão**: no envio, o arquivo é lido e **projetado** imediatamente para os campos de FR-012,
mais linha e recusas. A sessão guarda só essa projeção (JSON, `zlib` + base64, como na 001), com
token, nome, tamanho e SHA-256 do arquivo original. Os bytes do arquivo nunca são persistidos:
nem na sessão, nem em banco, nem em log.

O detalhe de uma recusa é texto fixo, gerado pelo parser, por exemplo "132 campos esperados, 131
encontrados". Nunca ecoa o conteúdo do registro. O único valor do arquivo que uma recusa pode
conter é o `CODIF`.

**Rationale**: a 001 guarda o arquivo bruto na sessão (tabela `django_session`). Com o CSV de
fornecedores, isso gravaria CPF, conta bancária, PIS e endereço no banco, violando
`INV-SUPPLIER-004` e FR-012. A projeção tem cerca de 1,2 MB de JSON para 10.035 registros e fica em
algumas centenas de KB comprimida — aceitável na sessão em banco.

**Consequência**: a confirmação recalcula o plano a partir da projeção guardada, e não do arquivo.
A impressão digital inclui o SHA-256 do arquivo original, calculado no envio. O resultado é o
mesmo: a projeção é função determinística do arquivo.

**Alternativas**: guardar o arquivo em disco temporário (rejeitado: mesma exposição, com limpeza
a gerenciar); pedir reenvio do arquivo na confirmação (rejeitado: piora o fluxo e muda o padrão da
001).

## R4 — Upload mantido em memória

**Decisão**: a view de envio usa só um handler de upload em memória, limitado a
`LIMITE_TAMANHO_ARQUIVO` (10 MB). Com o padrão do Django, arquivos acima de 2,5 MB — o real tem
4,6 MB — vão para um arquivo temporário em disco. Para trocar os handlers antes de o CSRF ler o
POST, a view segue o padrão documentado pelo Django: `csrf_exempt` na view, com `csrf_protect` no
método que processa o POST.

**Rationale**: evita que dados pessoais passem por disco temporário, coerente com
`INV-SUPPLIER-004`. O limite de 10 MB mantém a memória por requisição limitada.

**Alternativas**: aumentar `FILE_UPLOAD_MAX_MEMORY_SIZE` globalmente (rejeitado: afeta todo upload
do sistema); aceitar o temporário em disco, removido ao fim da requisição (rejeitado: exposição
desnecessária).

## R5 — Plano, impressão digital, lock e idempotência

**Decisão**: igual à 001, com os ajustes de domínio:

- `calcular_plano(leitura, *, bloquear=False)`: busca fornecedores existentes por `codif__in`, em
  lotes de 500, com `select_for_update().order_by("pk")` quando `bloquear`. Classifica cada aceito
  como inserção ou atualização e calcula o diff campo a campo de `CAMPOS_ATUALIZAVEIS`.
- Ausentes = fornecedores cujo `codif` não está entre os `CODIF` válidos do arquivo, aceitos ou
  recusados, contados no banco.
- Impressão digital = SHA-256 da serialização canônica de inserções, atualizações (com diff),
  recusas, total de ausentes e SHA-256 do arquivo.
- `confirmar_importacao`: `pg_advisory_xact_lock(CHAVE_LOCK_IMPORTACAO_FORNECEDORES)`, com chave
  própria e distinta da 001; token já confirmado → `PreviaJaConfirmada`; impressão digital
  diferente → `PreviaDesatualizada`; senão `aplicar_plano` numa única transação.

**Rationale**: é o desenho validado e revisado da 001 (FR-017, FR-018). Com chave de lock
distinta, importar o catálogo e importar fornecedores não se bloqueiam.

## R6 — Consulta com três campos, como na 001

**Decisão**: formulário com `codigo`, `nome` e `documento`, combinados por E.

- `codigo`: aparado nas bordas; fora de `[0-9]+` é erro de validação; busca `codif=` exato, sem
  completar zeros (`INV-SUPPLIER-001`).
- `nome`: normalizado por `normalizar_para_busca` e separado em palavras; cada palavra é um
  `nome_busca__contains`, em que `nome_busca` normaliza `nome + " " + nome_fantasia` e tem índice
  GIN trigram.
- `documento`: só os dígitos do termo; menos de 3 dígitos é erro de validação; busca
  `documento_digitos=` exato. `documento_digitos` é derivado de `documento` e indexado.

Ordenação por código, nome ou documento; o padrão é o nome, com desempate pelo código. Paginação de
50 itens, com HTMX para o fragmento de resultados, como no catálogo.

**Rationale**: mesmo modelo de interação da consulta do catálogo; cobre FR-027 e SC-007.

**Alternativas**: campo único que adivinha o critério (rejeitado: um número pode ser código ou
documento, e um campo explícito evita ambiguidade).

## R7 — Esquema sem migrations

**Decisão**: models em `fornecedores/models.py`, sem migrations, conforme o Princípio XIII
(v1.2.0) e o `MIGRATION_MODULES` de `config/settings/base.py`. O `pg_trgm` já é criado pelo
`pre_migrate` de `catalogo/apps.py`; `fornecedores` vem depois de `catalogo` em `INSTALLED_APPS`.

## R8 — Observabilidade sem dados pessoais

**Decisão**: logger `fornecedores.importacao`. Na confirmação, loga ids, SHA-256 e totais; loga
também prévia desatualizada, confirmação duplicada e falha com traceback. Nenhum conteúdo do
arquivo, nome ou documento de fornecedor vai para o log.

## R9 — Home

**Decisão**: `HomeView` ganha `pode_importar_fornecedores` (`ROLE-WAREHOUSE-HEAD`) e
`pode_consultar_fornecedores` (`ROLE-WAREHOUSE-STAFF`), derivados do mesmo `set` de papéis. A Home
mostra os links correspondentes, como faz com o catálogo. É só conveniência: a autorização fica
nas rotas.

## R10 — Desempenho no porte real

**Decisão**: parser linear; consultas de existentes em 21 lotes; `bulk_create`/`bulk_update` em
lotes de 500. Para 10.035 registros, a prévia e a confirmação ficam bem abaixo dos 30 segundos
de SC-006. A prévia pagina as recusas em 50.

## R11 — Testes sem dado real versionado

**Decisão**: fixtures sintéticas em bytes exatos em `tests/fixtures/fornecedores/`, com nomes,
CNPJ e CPF fictícios. O teste com o arquivo real é opcional, ativado por `FORNECEDORES_CSV_REAL`
(como `SCPI_CSV_REAL` na 001) e pulado no CI.

## R12 — Frontend

**Decisão**: telas de envio, prévia, detalhe da execução, histórico e consulta seguem as telas
equivalentes do catálogo, com os mesmos componentes de `static/css/components.css`. Não há
componente novo previsto. Implementação pelo `frontend-implementer`, com gate visual por
`impeccable critique`. `DESIGN.md` só muda se surgir padrão novo.
