# Fixtures da importação de fornecedores (`tests/fixtures/fornecedores/`)

Todos os arquivos abaixo são **sintéticos**: nenhum dado vem do export real do SCPI
(`docs/CSVs/fornecedores.csv`, fora do Git, ignorado por conter CPF, conta bancária e PIS). Todo
nome, CNPJ/CPF, código e endereço é fictício.

Gerados e verificados byte a byte por `gerar_fixtures.py` (mesmo diretório) — ver a docstring do
módulo para o comando explícito de (re)geração. Ele não é descoberto por um `pytest` comum
(`pyproject.toml` restringe `python_files` a `test_*.py`/`*_test.py`, e o arquivo não casa nenhum
padrão), então não roda em CI nem em `make verify`; existe só para reconstruir as fixtures quando
precisarem mudar, com a mesma garantia de bytes exatos com que foram criadas.

Cabeçalho padrão usado pela maioria dos arquivos (`CABECALHO_PADRAO` no gerador), com as 8 colunas
obrigatórias intercaladas com as 6 descartadas citadas pela task, e delimitador final:

```text
BANCO;CODIF;AGENC;NOME;CONTA;NOM_FANT;PISPASEP;INSMF;ENDER;CODTIP;CONTATO;BLOQ_OPCAO;MSG_BLOQ;TIPO_BLOQ;
```

Nenhuma coluna obrigatória fica na primeira posição, de propósito: a leitura de fornecedores
localiza colunas pelo **nome** do cabeçalho, nunca pela posição (`research.md` R2 — diferente da
001, que exige `CADPRO` na 1ª coluna). Bytes de todos os arquivos (exceto `vazio.csv`): UTF-8 com
BOM (`EF BB BF`), fim de registro CRLF (exceto `somente_lf.csv`, ver abaixo).

---

## Os 10 exemplos normativos de `contracts/arquivo-fornecedores.md` §5

| Arquivo | Exemplo (§5) | Cobre |
|---|---|---|
| `tres_registros_validos_com_lf_em_coluna_descartada.csv` | 1 | 3 registros aceitos; um com `\n` isolado dentro de `CONTATO` (descartada) — não quebra o registro nem contamina os campos projetados |
| `registro_com_colunas_deslocadas.csv` | 2 | registro do meio com um `;` a mais → `COLUNAS_DESLOCADAS`; os vizinhos (linhas 1 e 3) são aceitos |
| `codif_invalido_digito_nao_numerico_e_unicode.csv` | 3 | `CODIF` `12A` e `CODIF` `٣` (dígito Unicode, U+0663) → os dois `CODIF_INVALIDO` (o padrão é `[0-9]`, nunca `\d`) |
| `codif_duplicado_ambos_recusados.csv` | 4 | dois registros com `CODIF` `7` → os dois recusados como `CODIF_DUPLICADO`, cada um com seu próprio nome |
| `bloq_opcao_vazio_situacao_invalida.csv` | 5 | `BLOQ_OPCAO` vazio → `SITUACAO_BLOQUEIO_INVALIDA`; o vizinho (`BLOQ_OPCAO=S`) é aceito |
| `bloqueado_com_motivo_registrado.csv` | 6 | `BLOQ_OPCAO=B` com `MSG_BLOQ`/`TIPO_BLOQ` preenchidos → aceito, bloqueado, com o motivo |
| `insmf_com_caracteres_especiais.csv` | 7 | `INSMF="../-"` → aceito, preservado exatamente como recebido |
| `nomes_iguais_codigos_distintos.csv` | 8 | mesmo `NOME`/`NOM_FANT` em dois `CODIF` distintos → dois fornecedores, nunca mesclados |
| `somente_lf.csv` | 9 | arquivo inteiro separado só por `\n` (nenhum `\r\n`) → `ARQUIVO_TERMINADOR_INVALIDO`. **Mesmo arquivo** exigido nominalmente por T003 sob este nome — não duplicado sob dois nomes |
| `codif_com_zeros_a_esquerda.csv` | 10 | `CODIF` `007` aceito, distinto de `CODIF` `7` no mesmo arquivo |

---

## Fixtures exigidas nominalmente por T003

### `valido_basico.csv`

4 registros, todos aceitos: `recebidos = inseridos = 4` sobre cadastro vazio. Cobre tipo com CNPJ
(`600001`), com CPF (`600002`), sem documento (`600003`) e um bloqueado com motivo (`600004`,
`BLOQ_OPCAO=B`).

### `sentinelas.csv` (`INV-SUPPLIER-004`, T009)

2 registros (um não bloqueado, um bloqueado), com o mesmo valor-sentinela único em **todas** as 6
colunas descartadas (`SENTINELA-<COLUNA>-9137`), inclusive um `\n` isolado dentro de `CONTATO`
(`SENTINELA-CONTATO-9137-LINHA1\nSENTINELA-CONTATO-9137-LINHA2`). Depois de envio, prévia e
confirmação, nenhuma ocorrência de `SENTINELA-` pode aparecer em nenhuma tabela de `fornecedores`,
na sessão decodificada, nem nos logs capturados.

### `sem_coluna_bloq.csv`

Cabeçalho sem `BLOQ_OPCAO` (uma das 8 obrigatórias). O arquivo inteiro é recusado antes de qualquer
registro ser lido: `ARQUIVO_COLUNA_OBRIGATORIA_AUSENTE`. A única linha de dado existe só por
realismo; nunca chega a ser processada.

---

## Fixtures opcionais de recusa de arquivo (acrescentadas pelo test-engineer)

Completam os códigos de `contracts/arquivo-fornecedores.md` §1 que os 10 exemplos normativos não
exercitam:

- `coluna_duplicada.csv` — `NOME` aparece duas vezes no cabeçalho → `ARQUIVO_COLUNA_DUPLICADA`.
- `byte_invalido.csv` — cabeçalho e um registro válidos, seguidos de um byte `0xFF` colado ao fim
  (não é byte inicial UTF-8 válido) → `ARQUIVO_CODIFICACAO_INVALIDA`.
- `caractere_nulo.csv` — U+0000 dentro de `NOME` (`"FORNECEDOR NULO\x00LTDA"`); UTF-8 válido, mas
  recusado porque o PostgreSQL não aceita `NUL` em coluna de texto → `ARQUIVO_CARACTERE_NULO`.
- `somente_cabecalho.csv` — só o cabeçalho válido, sem registro nenhum → zero recebidos, sem erro.
- `vazio.csv` — 0 bytes, sem BOM → mesmo caso acima.

## Casos deixados fora das fixtures (decisão do test-engineer)

Por analogia com a decisão equivalente da 001 (`tests/fixtures/catalogo/README.md`, seção final),
os seguintes casos ficam como bytes montados **inline** nos testes do parser
(`tests/test_fornecedores_leitura.py`, a escrever em T007), por serem mais legíveis isolados e não
precisarem de um arquivo inteiro:

- arquivo sem BOM (`BOM opcional`, contract §2) — variação de um caso já coberto por fixture;
- último registro sem `\r\n` final aceito (contract §2);
- registro com **menos** campos que o cabeçalho (o exemplo normativo §5.2 só cobre "a mais");
- `CODIF` com espaço em branco puro (`"   "`) — não é vazio por `==`, mas fica fora de `[0-9]+`, o
  que já é `CODIF_INVALIDO`, não um caso à parte;
- `NOME` só com espaços (`"   "`) → `NOME_AUSENTE` (o `strip()` decide o vazio).

Nenhum desses casos ficou sem cobertura — apenas fora de arquivo de fixture, por legibilidade dos
testes que os exercitam.

---

## US4 — reimportação (`reimportacao_*.csv`, T003/T028)

`reimportacao_base.csv`: 5 fornecedores fictícios (`700001` a `700005`), um deles (`700003`) já
bloqueado com motivo. Uma importação inicial com este arquivo precisa rodar antes de qualquer
variação abaixo.

T003 pediu nominalmente base + 4 variações (nome alterado, bloqueio S→B, registro removido,
variação idêntica); o test-engineer acrescentou uma 5ª (bloqueio B→S), porque é a Acceptance
Scenario 3 da US4 (`spec.md`) e não tinha fixture nominal própria:

| Arquivo | O que muda em relação à base | Cobre (US4, `spec.md`) |
|---|---|---|
| `reimportacao_nome_alterado.csv` | `700001`: `NOME` → "FORNECEDOR ALFA REIMPORT REVISADO" | Acceptance Scenario 1 — alteração rastreável (campo, anterior, novo) |
| `reimportacao_bloqueio_s_para_b.csv` | `700002`: `BLOQ_OPCAO` `S`→`B`, com `MSG_BLOQ`/`TIPO_BLOQ` | Acceptance Scenario 2 — desbloqueado passa a bloqueado |
| `reimportacao_bloqueio_b_para_s.csv` | `700003`: `BLOQ_OPCAO` `B`→`S`, `MSG_BLOQ`/`TIPO_BLOQ` limpos | Acceptance Scenario 3 — bloqueado volta a desbloqueado |
| `reimportacao_registro_removido.csv` | `700004` ausente do arquivo (só 4 registros) | Acceptance Scenario 4 — ausente permanece inalterado, contado |
| `reimportacao_identica.csv` | nada — **byte-idêntico** a `reimportacao_base.csv` | "mesmo arquivo duas vezes → 0 alterações" (T028) |

Cada variação muda só o fornecedor citado; os outros 4 permanecem exatamente como na base — útil
para verificar que uma reimportação não toca fornecedores que não mudaram (nenhuma
`AlteracaoFornecedor` para eles).

A Acceptance Scenario 5 da US4 ("fornecedor já usado como emitente continua vinculado após a
reimportação") não tem fixture própria aqui: depende de uma entrada de estoque (spec 003), fora do
escopo desta feature — fica para os testes de T028 orquestrarem diretamente pelos modelos, não por
uma fixture de arquivo.
