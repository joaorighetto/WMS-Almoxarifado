# Contrato — Arquivo de fornecedores do SCPI

Entrada da importação. A regra de leitura está em [research.md R2](../research.md). Este contrato
fixa o que é recusado e com qual código, para testes e implementação.

## 1. Recusa do arquivo inteiro

Nada é guardado: nem sessão, nem banco.

| Código | Quando |
|---|---|
| `ARQUIVO_TAMANHO_EXCEDIDO` | acima de 10 MB |
| `ARQUIVO_CODIFICACAO_INVALIDA` | não é UTF-8 válido |
| `ARQUIVO_CARACTERE_NULO` | contém U+0000; a mensagem lista as linhas |
| `ARQUIVO_TERMINADOR_INVALIDO` | contém `\n`, mas nenhum `\r\n` |
| `ARQUIVO_COLUNA_OBRIGATORIA_AUSENTE` | falta alguma de `CODIF`, `NOME`, `NOM_FANT`, `INSMF`, `CODTIP`, `BLOQ_OPCAO`, `MSG_BLOQ`, `TIPO_BLOQ` |
| `ARQUIVO_COLUNA_DUPLICADA` | alguma coluna obrigatória aparece mais de uma vez |

Arquivo vazio, só com espaços ou só com cabeçalho válido: zero recebidos, sem erro.

## 2. Estrutura

- BOM opcional, removido. Separador `;`. Delimitador final gera uma coluna vazia no cabeçalho, que
  é ignorada.
- Registro termina em `\r\n`. `\n` isolado pertence ao campo. Um último registro sem terminador é
  aceito. Registro vazio é ignorado.
- Aspas são caracteres literais.
- Numeração: cabeçalho = linha 1; cada registro seguinte soma 1.

## 3. Recusa de registro

Primeiro motivo aplicável, nesta ordem:

| Motivo | Condição | `codif` na recusa | Detalhe |
|---|---|---|---|
| `COLUNAS_DESLOCADAS` | nº de campos ≠ cabeçalho | vazio | "N campos esperados, M encontrados" |
| `CODIF_AUSENTE` | `CODIF` vazio | vazio | fixo |
| `CODIF_INVALIDO` | `CODIF` fora de `[0-9]+` | vazio (o valor não é ecoado) | fixo |
| `NOME_AUSENTE` | `NOME.strip() == ""` | `CODIF` | fixo |
| `SITUACAO_BLOQUEIO_INVALIDA` | `BLOQ_OPCAO` ∉ {`S`, `B`} | `CODIF` | fixo; não ecoa o valor |
| `CODIF_DUPLICADO` | mesmo `CODIF` em mais de um registro não recusado antes | `CODIF` | "também na linha X" |

Nenhum detalhe contém valor de outra coluna do arquivo (`INV-SUPPLIER-004`).

## 4. Projeção do registro aceito

| Campo do arquivo | Campo projetado | Transformação |
|---|---|---|
| `CODIF` | `codif` | nenhuma |
| `NOME` | `nome` | nenhuma |
| `NOM_FANT` | `nome_fantasia` | nenhuma |
| `INSMF` | `documento` | nenhuma |
| `CODTIP` | `tipo` | nenhuma |
| `BLOQ_OPCAO` | `bloqueado` | `B` → verdadeiro; `S` → falso |
| `MSG_BLOQ` | `motivo_bloqueio` | nenhuma |
| `TIPO_BLOQ` | `tipo_bloqueio` | nenhuma |

Todas as demais colunas são descartadas na leitura.

## 5. Exemplos normativos (fixtures)

1. Arquivo com três registros válidos, um deles com `\n` no meio de uma coluna descartada → três
   aceitos, com os campos intactos.
2. Registro com um `;` a mais → `COLUNAS_DESLOCADAS`, e os vizinhos são aceitos.
3. `CODIF` `12A` → `CODIF_INVALIDO`; `CODIF` `٣` (dígito Unicode) → `CODIF_INVALIDO`.
4. Dois registros com `CODIF` `7` → os dois recusados como `CODIF_DUPLICADO`.
5. `BLOQ_OPCAO` vazio → `SITUACAO_BLOQUEIO_INVALIDA`.
6. `BLOQ_OPCAO` `B` com `MSG_BLOQ` preenchido → aceito, bloqueado, com o motivo.
7. `INSMF` `../-` → aceito, preservado como recebido.
8. Nomes iguais em códigos distintos → dois fornecedores.
9. Arquivo só com LF → `ARQUIVO_TERMINADOR_INVALIDO`.
10. `CODIF` `007` → aceito como `007`, distinto de `7`.
