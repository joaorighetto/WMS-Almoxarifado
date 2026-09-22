# Contrato — Arquivo de carga do catálogo SCPI

Contrato de entrada da importação: o que o WMS aceita, como lê e como recusa. É a referência
normativa para `catalogo/leitura_scpi.py` e para os testes do parser. As justificativas estão em
[research.md](../research.md) (R2–R6).

## 1. Recusa do arquivo inteiro (sem prévia, nada é calculado)

| Código | Condição |
|---|---|
| `ARQUIVO_NAO_ENVIADO` | nenhum arquivo no envio |
| `ARQUIVO_TAMANHO_EXCEDIDO` | mais de 10 MB |
| `ARQUIVO_CODIFICACAO_INVALIDA` | bytes que não são UTF-8 válido (BOM opcional) |
| `ARQUIVO_COLUNA_OBRIGATORIA_AUSENTE` | cabeçalho sem alguma de `CADPRO`, `DISC1`, `UNID1`, `QUAN3`, `DISCR1`, `GRUPO`, `SUBGRUPO`, `NOMEGRUPO`, `NOMESUBGRUPO` (FR-008). A mensagem lista quais faltam |
| `ARQUIVO_COLUNA_DUPLICADA` | coluna obrigatória repetida no cabeçalho (coluna fora de escopo repetida não tem efeito: é contada na estrutura e ignorada) |
| `ARQUIVO_CADPRO_NAO_E_PRIMEIRA_COLUNA` | `CADPRO` existe, mas não é a primeira coluna (I-1) |

Exceção: arquivo de 0 bytes, só com espaços/quebras de linha, ou só com cabeçalho válido produz
prévia com **zero recebidos**, sem erro (I-2).

## 2. Leitura

1. Decodificar com `utf-8-sig` estrito (remove a BOM, FR-007).
2. Separar linhas físicas **somente** em `\n`, removendo um `\r` final (CRLF e LF aceitos). A
   linha 1 é o cabeçalho. Um `\n` final do arquivo não cria linha extra.
3. Cabeçalho: `linha.split(";")`. O campo vazio final, gerado pelo delimitador de fim de linha, é
   parte da contagem esperada de campos (`N`). Nomes comparados exatamente.
4. Linhas de dados, classificadas em ordem (R3):
   - **início** — texto antes do 1º `;` casa `^[0-9]{3}\.[0-9]{3}\.[0-9]{3}$`;
   - **início com código inválido/ausente** — a linha tem exatamente `N − 1` separadores;
   - **continuação** — senão; é anexada ao registro corrente com `\n`;
   - **não associável** — continuação sem registro corrente.

   Antes da regra de continuação: linha vazia ou só com espaços é **ignorada** (não conta como
   registro nem gera exceção) quando não há registro corrente ou quando ele já está completo (`N`
   campos, último vazio). Dentro de registro incompleto, é continuação normal (D-1).
5. Cada registro recomposto é separado com `split(";")`. **Aspas não têm significado** (FR-007a).
6. Registro com `len(campos) ≠ N`, ou com o último campo não vazio → `ESTRUTURA_INCONSISTENTE`.

## 3. Validação por registro

Um motivo por registro recusado, o primeiro desta ordem: `LINHA_NAO_ASSOCIAVEL` →
`ESTRUTURA_INCONSISTENTE` → `CADPRO_AUSENTE` → `CADPRO_FORMATO_INVALIDO` →
`CADPRO_DUPLICADO_NO_ARQUIVO` → `DESCRICAO_AUSENTE` → `UNIDADE_AUSENTE` → `QUANTIDADE_AUSENTE` →
`QUANTIDADE_NAO_NUMERICA` → `QUANTIDADE_NEGATIVA` → `QUANTIDADE_FORA_DO_LIMITE`.

- `CADPRO`: comparado **sem trim**. Qualquer espaço torna o código inválido.
- `CADPRO` registrado na exceção: o 1º campo como recebido, quando não vazio; vazio em
  `LINHA_NAO_ASSOCIAVEL`, porque ali o 1º campo é fragmento de texto.
- Duplicidade: apurada entre todos os registros com `CADPRO` bem formado. Todas as ocorrências são
  recusadas.
- Obrigatórios `DISC1`, `UNID1`, `QUAN3`: vazio ou só espaços → recusa.
- `QUAN3`, depois de aparar espaços: `-?([0-9]+|[0-9]{1,3}(\.[0-9]{3})+)(,[0-9]+)?`. Convertido
  para `Decimal` sem `float`, negativo avaliado antes de arredondar, quantizado para `0.001` com
  `ROUND_HALF_UP`, no máximo 12 dígitos inteiros.
- `DISCR1`, `GRUPO`, `SUBGRUPO`, `NOMEGRUPO`, `NOMESUBGRUPO`: nunca causam recusa.
- Valores textuais aceitos são gravados **exatamente** como lidos, inclusive `\n` interno e aspas.

## 4. Totais

`recebidos` = registros lógicos, incluindo linhas não associáveis e registros estruturalmente
inconsistentes. Sempre vale `recebidos = inseridos + atualizados + rejeitados` (FR-034, SC-003).

## 5. Exemplos normativos (viram casos de teste)

| Entrada (trecho) | Resultado |
|---|---|
| `000.000.002;...` | `cadpro` = `000.000.002`, byte a byte |
| `QUAN3` = `0,000` | saldo `0.000`, aceito |
| `QUAN3` vazio | `QUANTIDADE_AUSENTE`, nunca zero |
| `QUAN3` = `53,4000000000001` | `53.400` |
| `QUAN3` = `1.234,5` | `1234.500` |
| `QUAN3` = `-1` | `QUANTIDADE_NEGATIVA` |
| `QUAN3` = `1.5` | `QUANTIDADE_NAO_NUMERICA` |
| `COTOVELO GALVANIZADO ¾" X 90º` em `DISC1` | gravado com a aspa; colunas seguintes alinhadas |
| `004.001.002` com `DISC1` em 3 linhas físicas | uma descrição recomposta com `\n`; demais campos corretos |
| linha `2;...` com `N − 1` separadores | `CADPRO_FORMATO_INVALIDO`; registro anterior intacto |
| linha `;...` com `N − 1` separadores | `CADPRO_AUSENTE` |
| mesmo `CADPRO` em duas linhas | ambas `CADPRO_DUPLICADO_NO_ARQUIVO` |
| arquivo termina no meio de um detalhamento multilinha | registro com campos < `N` → `ESTRUTURA_INCONSISTENTE` |
| unidades `UN`, `UND`, `M`, `MT`, `MTS` | cada uma gravada como veio |
| linha vazia entre dois registros completos, ou antes do fim do arquivo | ignorada; registros intactos; não conta como recebido |
| linha vazia no meio de um `DISCR1` multilinha ainda incompleto | preservada como `\n\n` no campo |
