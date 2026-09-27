# Data Model — Importação do Cadastro de Fornecedores do SCPI

App `fornecedores`. Sem migrations (Constitution XIII, v1.2.0). Nenhuma exclusão física: FKs com
`PROTECT`, nenhum modelo registrado no admin.

## Fornecedor

| Campo | Tipo | Regras |
|---|---|---|
| `codif` | texto | `UNIQUE`; `CHECK codif ~ '^[0-9]+$'`; `editable=False`; gravado como recebido; nunca atualizado (`INV-SUPPLIER-001/002`) |
| `nome` | texto | obrigatório (`CHECK` com `trim(nome) <> ''`); `NOME` como recebido |
| `nome_fantasia` | texto | pode ser vazio; `NOM_FANT` como recebido |
| `documento` | texto | pode ser vazio; `INSMF` como recebido, sem validação nem formatação |
| `documento_digitos` | texto | derivado: só os dígitos de `documento`; índice btree |
| `tipo` | texto | pode ser vazio; `CODTIP` como recebido |
| `bloqueado` | booleano | `True` se `BLOQ_OPCAO = B`, `False` se `S` |
| `motivo_bloqueio` | texto | pode ser vazio; `MSG_BLOQ` como recebido |
| `tipo_bloqueio` | texto | pode ser vazio; `TIPO_BLOQ` como recebido |
| `nome_busca` | texto | derivado: `normalizar_para_busca(nome + " " + nome_fantasia)`; índice GIN trigram |
| `execucao_origem` | FK → `ExecucaoImportacaoFornecedores` | execução que inseriu; `PROTECT`; imutável |

`CAMPOS_ATUALIZAVEIS = (nome, nome_fantasia, documento, tipo, bloqueado, motivo_bloqueio,
tipo_bloqueio)`. Os derivados `documento_digitos` e `nome_busca` são reescritos junto do campo de
origem. `codif` e `execucao_origem` nunca são atualizados.

Nenhum outro dado do arquivo tem campo (`INV-SUPPLIER-004`).

A spec 003 vai referenciar `Fornecedor` como emitente, com FK `PROTECT`. A regra de bloqueio
(`INV-SUPPLIER-005`) é aplicada lá, lendo `bloqueado`.

## ExecucaoImportacaoFornecedores

Uma importação **confirmada**. Prévias não geram execução.

| Campo | Tipo | Regras |
|---|---|---|
| `token_previa` | UUID | `UNIQUE` (idempotência) |
| `executada_por` | FK → `contas.User` | `PROTECT` |
| `concluida_em` | data/hora | atribuída na confirmação |
| `nome_arquivo` | texto (255) | |
| `tamanho_arquivo` | inteiro ≥ 0 | |
| `sha256_arquivo` | texto (64) | do arquivo original |
| `total_recebidos` | inteiro ≥ 0 | `CHECK = inseridos + atualizados + rejeitados` |
| `total_inseridos` | inteiro ≥ 0 | |
| `total_atualizados` | inteiro ≥ 0 | existentes presentes no arquivo |
| `total_atualizados_com_alteracao` | inteiro ≥ 0 | `CHECK ≤ total_atualizados` |
| `total_rejeitados` | inteiro ≥ 0 | |
| `total_ausentes_no_arquivo` | inteiro ≥ 0 | |

Ordenação padrão: `-concluida_em`, com desempate por `-pk`.

## ExcecaoImportacaoFornecedores

| Campo | Tipo | Regras |
|---|---|---|
| `execucao` | FK → execução | `PROTECT`, `related_name="excecoes"` |
| `linha` | inteiro ≥ 1 | número do registro lógico (cabeçalho = 1) |
| `codif` | texto | vazio quando não identificável; só `CODIF` válido |
| `motivo` | escolha `MotivoRecusaFornecedor` | |
| `detalhe` | texto | mensagem fixa do parser; nunca conteúdo do registro |

`MotivoRecusaFornecedor`: `COLUNAS_DESLOCADAS`, `CODIF_AUSENTE`, `CODIF_INVALIDO`,
`CODIF_DUPLICADO`, `NOME_AUSENTE`, `SITUACAO_BLOQUEIO_INVALIDA`.

## AlteracaoFornecedor

| Campo | Tipo | Regras |
|---|---|---|
| `execucao` | FK → execução | `PROTECT` |
| `fornecedor` | FK → `Fornecedor` | `PROTECT` |
| `campo` | escolha `CampoFornecedor` | um dos `CAMPOS_ATUALIZAVEIS` |
| `valor_anterior` | texto | `bloqueado` gravado como `"S"`/`"B"` |
| `valor_novo` | texto | idem |

## Rastreamento spec → modelo

| Requisito | Mecanismo |
|---|---|
| FR-001, FR-002, FR-004 | `codif` texto, `UNIQUE`, `CHECK`, `editable=False`; recusa de duplicados no parser |
| FR-005 | sem admin, sem views de CRUD; inserção só em `aplicar_plano` |
| FR-012, SC-003 | só os campos acima; exceções e alterações não guardam outras colunas; prévia com projeção mínima (research R3) |
| FR-015 | `bloqueado` a partir de `S`/`B`; outro valor recusa o registro |
| FR-017, FR-018 | transação única + lock + impressão digital (research R5) |
| FR-020, FR-021 | `bulk_update` só de `CAMPOS_ATUALIZAVEIS` + derivados; `AlteracaoFornecedor` por campo |
| FR-022 | ausentes só contados, nunca alterados |
| FR-024 a FR-026 | `ExecucaoImportacaoFornecedores`, `ExcecaoImportacaoFornecedores`, ordenação e paginação |
| FR-027 | `codif`, `nome_busca` (GIN), `documento_digitos` (btree) |
