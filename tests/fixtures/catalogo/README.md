# Fixtures do catálogo SCPI (`tests/fixtures/catalogo/`)

Todos os arquivos abaixo são **sintéticos**: nenhum dado vem do export real do SCPI
(`docs/domain-legacy/`, fora do Git). Os únicos valores citados literalmente pela spec/contrato
(`specs/001-importacao-catalogo-materiais/contracts/arquivo-scpi.md`, `research.md`) são os códigos
`000.000.002`, `004.001.002`, `000.029.742` e a descrição `COTOVELO GALVANIZADO ¾" X 90º`; todo o
resto (descrições, demais códigos, `USUARIO`/`USUALT`, datas, códigos de barra) é fictício.

Bytes de todos os arquivos (exceto `vazio.csv`): UTF-8 com BOM (`EF BB BF`), fim de linha CRLF,
cabeçalho real de 21 colunas + campo vazio final (22 campos), na ordem observada no arquivo real
(`research.md` → "Evidência usada"):

```text
CADPRO;DISC1;UNID1;QUAN3;VAUN1;PRECOMEDIO;GRUPO;SUBGRUPO;NOMEGRUPO;NOMESUBGRUPO;DISCR1;QUANMIN;
QUANMAX;CODREDUZ;CODBARRA;NOCULTAR;USUARIO;DTAINSERE;USUALT;DTAALT;LOCALFISICO;
```

As 9 colunas obrigatórias são `CADPRO`, `DISC1`, `UNID1`, `QUAN3`, `DISCR1`, `GRUPO`, `SUBGRUPO`,
`NOMEGRUPO`, `NOMESUBGRUPO`. As demais são fora de escopo (nunca armazenadas).

Numeração de linha física: a linha 1 é sempre o cabeçalho (contrato §2).

Os arquivos foram gerados por um script Python descartável (bytes explícitos, não versionado) e
verificados byte a byte (BOM, CRLF, contagem de `;` por linha física, decodificação) antes de serem
gravados — ver seção "Como os bytes foram verificados" no relatório desta task.

---

## `carga_inicial_valida.csv`

9 registros, todos aceitos. Sobre catálogo vazio: `recebidos = inseridos = 9`, `atualizados = 0`,
`rejeitados = 0`.

| Linha(s) | `CADPRO` | Caso coberto | Resultado esperado |
|---|---|---|---|
| 2 | `000.000.002` | código citado pela spec; saldo `0,000`; `DISCR1` vazio; classificação preenchida (`GRUPO=010`, `SUBGRUPO=020`, `NOMEGRUPO=FERRAGENS`, `NOMESUBGRUPO=PARAFUSOS`) | `saldo = saldo_inicial = 0.000`; `cadpro` gravado byte a byte |
| 3 | `010.020.030` | unidade `UND`; classificação vazia (`GRUPO`/`SUBGRUPO`/`NOMEGRUPO`/`NOMESUBGRUPO` = `""`) | `saldo = 25.000` |
| 4 | `010.020.031` | mesma descrição do registro da linha 3 (`ARRUELA LISA 1/4`), código distinto; unidade `M` | `saldo = 10.000`; dois materiais distintos com `descricao` igual |
| 5 | `010.020.032` | unidade `MT`; `QUAN3` com separador de milhar `1.234,5` | `saldo = 1234.500` |
| 6 | `010.020.033` | unidade `MTS` | `saldo = 8.000` |
| 7 | `000.029.742` | código citado pela spec; `QUAN3 = 53,4000000000001` (ruído de ponto flutuante do SCPI) | `saldo = 53.400` (`ROUND_HALF_UP`, 3 casas) |
| 8 | `010.020.034` | descrição com aspas literais e caracteres especiais: `COTOVELO GALVANIZADO ¾" X 90º` (FR-007a, sem tratamento de aspas) | `descricao` gravada exatamente como está, aspas incluídas; colunas seguintes alinhadas (`UNID1=UN`, `saldo=4.000`) |
| 9–11 | `010.020.035` | `DISCR1` recomposto de **3 linhas físicas**, com uma linha vazia no meio (`"Observação técnica" / "" / "linha adicional"`) — mesmo padrão de continuação usado pela decisão D-1, aqui dentro de um registro que fecha corretamente | `detalhamento = "Observação técnica\n\nlinha adicional"`; `saldo = 12.000` |
| 12–14 | `004.001.002` | código citado pela spec; `DISC1` recomposto de **3 linhas físicas** (`"TUBO DE ACO CARBONO" / "SCHEDULE 40" / "GALVANIZADO"`) | `descricao = "TUBO DE ACO CARBONO\nSCHEDULE 40\nGALVANIZADO"`; `saldo = 6.000` |

---

## `carga_inicial_casos_spec.csv`

Os 9 registros válidos acima (linhas 3–15, mesmo conteúdo e mesma ordem) **mais** um registro para
cada um dos 11 motivos de recusa do contrato §3, incluindo `CADPRO` duplicado (2 linhas) e uma
continuação inacabada no fim do arquivo. Sobre catálogo vazio: `recebidos = 22`, `inseridos = 9`,
`atualizados = 0`, `rejeitados = 13` (`recebidos = inseridos + atualizados + rejeitados`, FR-034).

| Linha(s) | `CADPRO` na exceção | Motivo | Detalhe do caso |
|---|---|---|---|
| 2 | `""` (vazio) | `LINHA_NAO_ASSOCIAVEL` | primeira linha de dados do arquivo já é uma "continuação" (`CONTINUACAO PERDIDA SEM REGISTRO ANTERIOR;ABC;DEF`), sem registro corrente. `CADPRO` fica vazio por definição deste motivo (o 1º campo é fragmento de texto, não código) |
| 3–15 | — | (aceitos) | os 9 registros válidos de `carga_inicial_valida.csv`, na mesma ordem |
| 16 | `020.030.040` | `ESTRUTURA_INCONSISTENTE` | uma linha física completa, mas com uma coluna (`CODBARRA`) omitida: 21 campos em vez de 22 |
| 17 | `""` (vazio) | `CADPRO_AUSENTE` | `CADPRO` vazio, mas a linha tem a contagem completa de separadores (rule 2 do contrato: início de registro com código ausente) |
| 18 | `2` | `CADPRO_FORMATO_INVALIDO` | primeiro campo `2` (exemplo normativo do contrato §5), linha estruturalmente completa |
| 19 | `090.090.090` | `CADPRO_DUPLICADO_NO_ARQUIVO` | 1ª ocorrência do código duplicado |
| 20 | `090.090.090` | `CADPRO_DUPLICADO_NO_ARQUIVO` | 2ª ocorrência do mesmo código — **ambas** as linhas são recusadas |
| 21 | `030.040.050` | `DESCRICAO_AUSENTE` | `DISC1 = "   "` (só espaços — conta como vazio para a checagem de obrigatoriedade) |
| 22 | `030.040.051` | `UNIDADE_AUSENTE` | `UNID1` vazio |
| 23 | `030.040.052` | `QUANTIDADE_AUSENTE` | `QUAN3` vazio (nunca vira zero) |
| 24 | `030.040.053` | `QUANTIDADE_NAO_NUMERICA` | `QUAN3 = "1.5"` (exemplo normativo do contrato §5: um único ponto com 1 dígito decimal não casa a gramática) |
| 25 | `030.040.054` | `QUANTIDADE_NEGATIVA` | `QUAN3 = "-5"` |
| 26 | `030.040.055` | `QUANTIDADE_FORA_DO_LIMITE` | `QUAN3` com 13 dígitos inteiros (`1234567890123`), acima do limite de 12 |
| 27–28 | `099.099.099` | `ESTRUTURA_INCONSISTENTE` | registro começa (`099.099.099;PRODUTO TRUNCADO`), continua (`CONTINUACAO SEM FIM`) e o **arquivo termina** no meio do detalhamento — menos de 22 campos ao final |

Duplicidade (FR-005) é apurada sobre **todos** os `CADPRO` bem formados do arquivo — as linhas 19 e
20 devem aparecer como duas `ExcecaoImportacao` distintas, cada uma com seu próprio intervalo de
linha.

---

## `reimportacao.csv`

Usa os mesmos 9 códigos de `carga_inicial_valida.csv` como catálogo pré-existente (uma importação
inicial com esse arquivo precisa rodar antes). Cobre cada variação exigida por T004/T041:

| Linha(s) | `CADPRO` | O que muda em relação à carga inicial | Resultado esperado |
|---|---|---|---|
| 2 | `000.000.002` | `DISC1`: `PARAFUSO SEXTAVADO M8` → `PARAFUSO SEXTAVADO M8 ZINCADO`. Saldo igual (`0,000`) | 1 `AlteracaoCadastralMaterial` (`descricao`); sem divergência; conta em `atualizados` e em `atualizados_com_alteracao` |
| 3 | `010.020.030` | nada muda | conta em `atualizados`, **não** em `atualizados_com_alteracao`; sem divergência |
| 4 | `010.020.031` | **única** diferença é o saldo: arquivo original tinha `QUAN3=10` (saldo salvo 10.000), reimportação traz `QUAN3=15` | `DivergenciaSaldo(saldo_wms=10.000, saldo_arquivo=15.000, diferenca=+5.000)`; conta em `atualizados`, **não** em `atualizados_com_alteracao`; nenhuma `AlteracaoCadastralMaterial`; `saldo` do material **não muda** (continua 10.000) |
| — | `010.020.032` | **omitido** do arquivo | conta em `total_ausentes_no_arquivo`; material não é alterado nem excluído |
| 5 | `010.020.033` | `UNID1`: `MTS` → `M`. Saldo igual (`8`) | 1 `AlteracaoCadastralMaterial` (`unidade`); sem divergência |
| 6 | `000.029.742` | **todos os 7 campos cadastrais** mudam: `DISC1`, `UNID1`, `GRUPO`, `SUBGRUPO`, `NOMEGRUPO`, `NOMESUBGRUPO`, `DISCR1`. Saldo igual (`53,400`) | exatamente 7 `AlteracaoCadastralMaterial`, uma por campo, cada uma com `valor_anterior`/`valor_novo` exatos; sem divergência |
| 7 | `010.020.034` | nada muda (mantém a descrição com aspas) | confirma que a comparação byte a byte não marca falso positivo por causa das aspas |
| 8 | `010.020.035` | `DISCR1`: multilinha (`"Observação técnica\n\nlinha adicional"`) → linha única (`"Revisado"`). Saldo igual (`12`) | 1 `AlteracaoCadastralMaterial` (`detalhamento`), com `valor_anterior` igual ao texto multilinha original |
| 9–11 | `004.001.002` | nada muda (mantém `DISC1` recomposto das mesmas 3 linhas físicas) | confirma que a comparação reconhece o valor multilinha como idêntico |
| 12 | `070.080.090` | código novo, não existia no catálogo | inserção normal (`saldo = saldo_inicial = 20.000`); não entra em `atualizados` nem gera divergência |

Totais esperados desta reimportação: `recebidos=9`, `inseridos=1`, `atualizados=8`,
`atualizados_com_alteracao=4` (linhas 2, 5, 6, 8), `rejeitados=0`, `divergencias=1` (linha 4),
`total_ausentes_no_arquivo=1` (`010.020.032`), `AlteracaoCadastralMaterial` = 10 linhas no total
(1 + 1 + 7 + 1).

---

## `linhas_vazias.csv`

Cobre a decisão D-1 (linha física vazia ou só com espaços): ignorada fora de registro incompleto,
preservada como continuação dentro de um. Sobre catálogo vazio: `recebidos = 3`, `inseridos = 3`,
`rejeitados = 0`. Nenhuma linha vazia conta como recebida.

| Linha | Conteúdo | Papel |
|---|---|---|
| 2 | `010.010.010;ITEM A;...` | registro completo |
| 3 | *(vazia)* | entre dois registros completos → **ignorada**, não conta como recebida |
| 4 | `010.010.011;ITEM B;...` | registro completo |
| 5 | `010.010.012;ITEM C;...;linha 1` | início de registro, **incompleto** (para antes de fechar `DISCR1`) |
| 6 | *(vazia)* | dentro do registro incompleto de `010.010.012` → **continuação normal** (D-1): preservada no campo |
| 7 | `linha 3;...;A1-01;` | fecha o registro de `010.010.012`; `detalhamento` final = `"linha 1\n\nlinha 3"` (a linha vazia da linha 6 vira o `\n\n` do meio) |
| 8 | *(vazia)* | depois do último registro completo, antes do fim do arquivo → **ignorada** |

A numeração de linha física usada pela suíte deve considerar a linha 6 como parte do intervalo
(`linha_inicial=5`, `linha_final=7`) do registro `010.010.012`, ainda que ele não seja uma exceção.

---

## `sem_coluna_obrigatoria.csv`

Cabeçalho sem `NOMESUBGRUPO` (uma das 9 colunas obrigatórias). O arquivo inteiro é recusado antes de
qualquer registro ser lido: `ARQUIVO_COLUNA_OBRIGATORIA_AUSENTE`, mensagem lista `NOMESUBGRUPO`. A
única linha de dado existe só por realismo; nunca chega a ser processada.

## `cadpro_nao_primeira_coluna.csv`

Cabeçalho com `DISC1` antes de `CADPRO` (as 21 colunas continuam todas presentes, só a ordem muda).
Recusa: `ARQUIVO_CADPRO_NAO_E_PRIMEIRA_COLUNA` (I-1), antes de qualquer registro ser lido.

## `codificacao_invalida.csv`

Cabeçalho e uma linha válidos, seguidos do byte `0xFF` (não é um byte inicial UTF-8 válido) colado
ao fim dessa mesma linha. `bytes.decode("utf-8-sig")` falha para o arquivo inteiro:
`ARQUIVO_CODIFICACAO_INVALIDA`, antes de qualquer registro ser lido.

## `somente_cabecalho.csv`

Só o cabeçalho válido, sem nenhuma linha de dado. Edge case "arquivo vazio ou apenas com
cabeçalho" (I-2): prévia com **zero registros recebidos, sem erro**.

## `vazio.csv`

0 bytes, sem BOM. Mesmo edge case do arquivo anterior (I-2): zero registros recebidos, sem erro.

---

## Casos deixados fora das fixtures (decisão do test-engineer)

Por indicação explícita da task (T004), os seguintes casos ficam como bytes montados **inline** nos
testes do parser (`tests/test_catalogo_leitura_scpi.py`), por serem mais legíveis isolados e não
precisarem de um arquivo inteiro:

- `CADPRO` com dígito Unicode (ex.: `٣`) → `CADPRO_FORMATO_INVALIDO` (o padrão usa `[0-9]`, nunca
  `\d`);
- `-0,0001` (recusado) vs. `-0` e `-0,000` (aceitos como zero);
- 12 dígitos inteiros aceitos vs. 13 → `QUANTIDADE_FORA_DO_LIMITE` (a fixture acima já cobre o caso
  de 13 dígitos; o de 12 aceitos e a comparação lado a lado ficam mais claros inline);
- `1,2,3`, `" ,5"` e `"1 234"` → `QUANTIDADE_NAO_NUMERICA`;
- cabeçalho com `CADPRO` na 1ª posição e as demais colunas obrigatórias reordenadas, com colunas
  extras entre elas (valores lidos pelo nome, nunca pela posição);
- coluna fora de escopo duplicada no cabeçalho (sem efeito);
- arquivo com CRLF e LF misturados;
- continuação legítima que por acaso tem `N − 1` separadores (os dois registros envolvidos
  recusados).

Nenhum desses casos ficou sem cobertura — apenas fora de arquivo de fixture, por decisão de
legibilidade dos testes que os exercitam.
