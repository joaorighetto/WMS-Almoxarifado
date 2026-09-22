# Data Model — 001 Importação e Consulta do Catálogo de Materiais

**Plano**: [plan.md](./plan.md) | **Decisões**: [research.md](./research.md)

App `catalogo`. Todos os modelos são **somente-inserção** do ponto de vista da aplicação, exceto
os campos cadastrais de `Material`, que só mudam por reimportação (`INV-CATALOG-004`). Nenhum
modelo é registrado no Django Admin. Nenhuma view cria, edita ou exclui `Material` fora da
importação (FR-006, SC-005, `INV-CATALOG-003`). Exclusão física não é prevista (Assumptions;
Constitution IV): toda FK entre esses modelos usa `on_delete=PROTECT`.

## Diagrama

```text
contas.User ──(executada_por, PROTECT)──┐
                                        ▼
                              ExecucaoImportacao ◄──(execucao_origem, PROTECT)── Material
                               │   │   │                                          ▲  ▲
                 (execucao)    │   │   │ (execucao)                  (material)   │  │ (material)
                               ▼   │   ▼                                          │  │
                 ExcecaoImportacao │  DivergenciaSaldo ───────────────────────────┘  │
                                   ▼                                                 │
                         AlteracaoCadastralMaterial ─────────────────────────────────┘
```

## Material

Item do catálogo oficial do SCPI.

| Campo | Tipo | Regras | Origem |
|---|---|---|---|
| `id` | BigAutoField | PK técnica | — |
| `cadpro` | `CharField(max_length=11)`, `editable=False` | `UNIQUE`; `CHECK cadpro ~ '^[0-9]{3}\.[0-9]{3}\.[0-9]{3}$'`; gravado exatamente como recebido; nunca atualizado | CADPRO — FR-001–FR-004, `INV-CATALOG-001/002` |
| `descricao` | `TextField` | não vazio (validado na importação); preservado sem trim; pode conter `\n` | DISC1 — FR-017, FR-018 |
| `descricao_busca` | `TextField` | derivado técnico de `descricao` (sem acentos + `casefold`); reescrito sempre que `descricao` muda; índice GIN `gin_trgm_ops`; nunca exibido | R15 — FR-040 |
| `unidade` | `TextField` | não vazio; preservado exatamente (sem normalização) | UNID1 — FR-019, FR-020, `INV-CATALOG-005` |
| `detalhamento` | `TextField(blank=True)` | pode ser vazio; preservado; pode conter `\n` | DISCR1 — FR-021 |
| `grupo` | `TextField(blank=True)` | como recebido, sem validação | GRUPO — FR-022 |
| `subgrupo` | `TextField(blank=True)` | idem | SUBGRUPO — FR-022 |
| `nome_grupo` | `TextField(blank=True)` | idem | NOMEGRUPO — FR-022 |
| `nome_subgrupo` | `TextField(blank=True)` | idem | NOMESUBGRUPO — FR-022 |
| `saldo` | `DecimalField(15, 3)` | `CHECK saldo >= 0`; escrito **só na inserção** nesta feature; nunca incluído na atualização por reimportação | QUAN3 (inserção) — FR-012, FR-016, FR-028, `INV-STOCK-001/002` |
| `saldo_inicial` | `DecimalField(15, 3)`, `editable=False` | `CHECK saldo_inicial >= 0`; igual a `saldo` na inserção; imutável | FR-016, `INV-MOV-002` |
| `execucao_origem` | FK → `ExecucaoImportacao`, `PROTECT`, `editable=False` | execução que criou o material; imutável | FR-016, `INV-MOV-002` |

**Campos atualizáveis por reimportação** (lista fechada, FR-026): `descricao`, `descricao_busca`
(derivado), `unidade`, `detalhamento`, `grupo`, `subgrupo`, `nome_grupo`, `nome_subgrupo`.
**Nunca atualizados**: `cadpro`, `saldo`, `saldo_inicial`, `execucao_origem`.

**Índices**: único em `cadpro` (busca exata, FR-039); GIN trigram em `descricao_busca` (FR-040).
**Ordenação padrão da consulta**: `cadpro`. A ordem lexicográfica coincide com a numérica pela
largura fixa, sem converter nada.

## ExecucaoImportacao

Uma importação **confirmada** (FR-033, FR-037). Prévias não confirmadas não geram execução.

| Campo | Tipo | Regras |
|---|---|---|
| `id` | BigAutoField | PK |
| `token_previa` | `UUIDField` | `UNIQUE`: idempotência da confirmação (R8) |
| `executada_por` | FK → `contas.User`, `PROTECT` | quem confirmou (FR-033) |
| `concluida_em` | `DateTimeField` | momento do commit, definido na efetivação (FR-033) |
| `nome_arquivo` | `CharField(max_length=255)` | nome informado no envio, só para exibição |
| `tamanho_arquivo` | `PositiveBigIntegerField` | bytes |
| `sha256_arquivo` | `CharField(max_length=64)` | identifica o conteúdo processado (FR-033) |
| `total_recebidos` | `PositiveIntegerField` | registros lógicos (após recomposição) |
| `total_inseridos` | `PositiveIntegerField` | |
| `total_atualizados` | `PositiveIntegerField` | aceitos com `CADPRO` já existente, com ou sem mudança (R10) |
| `total_atualizados_com_alteracao` | `PositiveIntegerField` | subconjunto informativo de `total_atualizados` (R10) |
| `total_rejeitados` | `PositiveIntegerField` | = nº de `ExcecaoImportacao` da execução |
| `total_divergencias` | `PositiveIntegerField` | = nº de `DivergenciaSaldo` da execução (FR-035) |
| `total_ausentes_no_arquivo` | `PositiveIntegerField` | FR-031 (R11) |

**Constraints**:
- `CHECK total_recebidos = total_inseridos + total_atualizados + total_rejeitados` (FR-034, SC-003).
- `CHECK total_atualizados_com_alteracao <= total_atualizados`.

**Ordenação padrão do histórico**: `-concluida_em`.

## ExcecaoImportacao

Registro recusado dentro de uma execução (FR-036).

| Campo | Tipo | Regras |
|---|---|---|
| `execucao` | FK → `ExecucaoImportacao`, `PROTECT`, `related_name="excecoes"` | |
| `linha_inicial` | `PositiveIntegerField` | primeira linha física do registro (linha 1 = cabeçalho) |
| `linha_final` | `PositiveIntegerField` | `CHECK linha_final >= linha_inicial` |
| `cadpro` | `TextField(blank=True)` | texto do 1º campo **como recebido**, quando não vazio; vazio em `LINHA_NAO_ASSOCIAVEL`; nunca reformatado; não é FK |
| `motivo` | `CharField(choices=MotivoRecusa)` | códigos de [research.md → R5](./research.md) |
| `detalhe` | `TextField(blank=True)` | complemento legível (ex.: valor de `QUAN3` recebido, nº de campos encontrado) |

`MotivoRecusa` (TextChoices, rótulos em pt-BR): `LINHA_NAO_ASSOCIAVEL`, `ESTRUTURA_INCONSISTENTE`,
`CADPRO_AUSENTE`, `CADPRO_FORMATO_INVALIDO`, `CADPRO_DUPLICADO_NO_ARQUIVO`, `DESCRICAO_AUSENTE`,
`UNIDADE_AUSENTE`, `QUANTIDADE_AUSENTE`, `QUANTIDADE_NAO_NUMERICA`, `QUANTIDADE_NEGATIVA`,
`QUANTIDADE_FORA_DO_LIMITE`.

**Ordenação**: `linha_inicial`.

## DivergenciaSaldo

Diferença informativa entre arquivo e WMS (FR-029, FR-030, `INV-STOCK-003`). Não altera saldo.

| Campo | Tipo | Regras |
|---|---|---|
| `execucao` | FK → `ExecucaoImportacao`, `PROTECT`, `related_name="divergencias"` | execução que detectou |
| `material` | FK → `Material`, `PROTECT` | `CADPRO` exibido via material (imutável) |
| `saldo_wms` | `DecimalField(15, 3)` | saldo do material no momento da efetivação |
| `saldo_arquivo` | `DecimalField(15, 3)` | `QUAN3` arredondado (R6) |
| `diferenca` | `DecimalField(16, 3)` | `CHECK diferenca = saldo_arquivo - saldo_wms`; `CHECK diferenca <> 0` |

`UNIQUE(execucao, material)`. **Ordenação**: `material__cadpro`.

## AlteracaoCadastralMaterial

Rastro de cada campo cadastral alterado por reimportação (FR-032, Constitution IV).

| Campo | Tipo | Regras |
|---|---|---|
| `execucao` | FK → `ExecucaoImportacao`, `PROTECT`, `related_name="alteracoes"` | quem e quando, via execução |
| `material` | FK → `Material`, `PROTECT` | |
| `campo` | `CharField(choices=CampoCadastral)` | um dos 7 campos atualizáveis (não inclui `descricao_busca`) |
| `valor_anterior` | `TextField(blank=True)` | exatamente como estava |
| `valor_novo` | `TextField(blank=True)` | exatamente como veio do arquivo |

`UNIQUE(execucao, material, campo)`; `CHECK valor_anterior <> valor_novo`.

## Estruturas transitórias (não persistidas)

Vivem só em memória, ou na sessão no caso do pedido de prévia (R8), e não são modelos:

- **Pedido de prévia** (sessão, chave `catalogo_importacao_previa`): `token`, `nome_arquivo`,
  `tamanho`, `sha256`, `conteudo` (zlib + base64).
- **RegistroLido**: `linha_inicial`, `linha_final` e `campos: dict[str, str]`, ou o motivo
  estrutural da recusa (R3).
- **PlanoImportacao**: listas de inserções, atualizações (com campos alterados e valores
  anterior/novo), recusas, divergências, contagem de ausentes, totais e `impressao_digital`
  (SHA-256 da serialização canônica, R8).

## Rastreamento requisito → modelo

| Requisito | Onde é garantido |
|---|---|
| FR-001, FR-002, `INV-CATALOG-001` | `Material.cadpro` texto, `editable=False`, fora da lista de atualização; `CHECK` de formato; nunca aparado |
| FR-003, FR-005, `INV-CATALOG-002` | `UNIQUE(cadpro)` + recusa de duplicados no arquivo (R5) |
| FR-006, SC-005, `INV-CATALOG-003` | sem admin, sem view de criação/edição/exclusão; inserção só em `catalogo.importacao` |
| FR-016, `INV-MOV-002` | `saldo_inicial` + `execucao_origem` imutáveis |
| FR-028, SC-009, `INV-STOCK-002` | `saldo` fora da lista de campos do `bulk_update` |
| `INV-STOCK-001` | `CHECK saldo >= 0` e recusa de quantidade negativa |
| FR-029, FR-030, `INV-STOCK-003` | `DivergenciaSaldo` por execução; nenhuma escrita em `saldo` |
| FR-032 | `AlteracaoCadastralMaterial` |
| FR-033–FR-037 | `ExecucaoImportacao` + `ExcecaoImportacao`; `CHECK` de totais |
| FR-038, `INV-STOCK-004` | efetivação em um único `transaction.atomic()` (R9) |
