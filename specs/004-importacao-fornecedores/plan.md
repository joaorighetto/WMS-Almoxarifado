# Implementation Plan: Importação do Cadastro de Fornecedores do SCPI

**Branch**: `004-importacao-fornecedores` | **Date**: 2026-09-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/004-importacao-fornecedores/spec.md`

## Summary

Trazer o cadastro de fornecedores do SCPI para o WMS por CSV, com prévia sem persistência e
confirmação explícita com efetivação atômica. A partir daí, os funcionários do almoxarifado
consultam fornecedores por código, nome ou CNPJ/CPF, e a entrada de materiais (spec 003) os usa
como emitente. O chefe do almoxarifado importa, reimporta e audita as execuções.

Abordagem técnica: novo app `fornecedores`, no molde de `catalogo`. As diferenças são: parser
próprio, em que o registro termina em CRLF; prévia que guarda na sessão só a **projeção mínima**
dos dados, nunca o arquivo; e upload mantido em memória, para que CPF, conta bancária e PIS não
passem por disco nem banco. O plano, a impressão digital, o advisory lock e a idempotência por
token repetem o desenho validado da 001. Reusa o mixin de papel, a ordenação, a paginação, a
normalização de busca e os componentes visuais da 001. Nenhuma dependência nova. Decisões em
[research.md](./research.md).

## Situação no roadmap e prontidão

- **Linha do ROADMAP**: `FOR` — Inclui: carga por CSV com prévia e confirmação; consulta;
  reimportação; resultado auditável. **Não inclui**: cadastro manual; compras/licitações;
  contratos; dados financeiros ou fiscais além da identificação; integração automática. Este plano
  não atravessa nenhuma dessas exclusões.
- **Dependência obrigatória `002`**: satisfeita. `FOR` é dependência obrigatória da `ENT`
  (spec 003), que só vai à implementação depois desta entrega.
- **Clarificações**: decisões de origem, permissões, dados mínimos e bloqueio tomadas com o dono
  do produto em 2026-09-25 e canonizadas antes da spec (`PERM-SUPPLIER-*`, `INV-SUPPLIER-*`). O
  formato vem do arquivo real. Nenhum `[NEEDS CLARIFICATION]`.
- **Artefato**: o CSV real existe só localmente (`docs/CSVs/`, ignorado pelo Git). A
  implementação usa fixtures sintéticas; o aceite de SC-001 a SC-003 roda com
  `FORNECEDORES_CSV_REAL`.

## Technical Context

**Language/Version**: Python 3.13; Django 6.1.1.

**Primary Dependencies**: `django` (com `django.contrib.postgres`), `psycopg`. HTMX já versionado em
`static/vendor/htmx/`. Nenhum pacote novo.

**Storage**: PostgreSQL 16; `pg_trgm` já criado por `catalogo/apps.py`. Esquema efêmero, sem
migrations. A prévia fica na sessão em banco, só com a projeção mínima.

**Testing**: pytest + pytest-django; `django_db(transaction=True)` para concorrência; fixtures CSV em
bytes exatos em `tests/fixtures/fornecedores/`, com dados fictícios.

**Target Platform**: servidor Linux; navegador desktop/tablet do almoxarifado.

**Project Type**: aplicação Django monolítica server-rendered.

**Performance Goals**: prévia e confirmação de 10.035 registros (4,6 MB) em menos de 30 s cada
(SC-006); consulta por nome via índice GIN trigram e por documento via índice btree.

**Constraints**: nenhuma escrita de domínio antes da confirmação; efetivação atômica; nenhum dado
fora de FR-012 persistido em lugar algum — banco, sessão, log ou disco temporário; upload limitado
a 10 MB.

**Scale/Scope**: cerca de 10 mil fornecedores, crescendo devagar; um chefe importando
ocasionalmente; consulta pela equipe do almoxarifado.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Princípio | Status | Justificativa |
|---|---|---|
| I. Simplicidade | PASS, com uma justificativa | Models, forms, CBVs e mixins nativos. O módulo de domínio `fornecedores/importacao.py` repete a justificativa da 001 (Complexity Tracking). Nenhum framework genérico de importação: dois casos não justificam a abstração (research R1). |
| II. Server-Driven | PASS | Django Templates; HTMX só no fragmento da consulta. |
| III. Integridade de Dados | PASS | Transação única; advisory lock próprio; `select_for_update` ordenado; `UNIQUE(codif)`, `CHECK` de formato de `codif`, de nome não vazio e dos totais. |
| IV. Rastreabilidade | PASS | Execução com responsável, momento, nome, tamanho e SHA-256 do arquivo; recusas por linha; `AlteracaoFornecedor` com valor anterior e novo; sem exclusão física. |
| V. Regras no Backend | PASS | Parser, validação, plano e autorização no servidor. |
| VI. Segurança | PASS | Papel explícito em toda rota; CSRF mantido com o padrão `csrf_exempt` + `csrf_protect` para trocar os handlers de upload (research R4); dados pessoais descartados na leitura, fora de sessão, log e disco (R3, R4, R8); mensagens genéricas em falha. |
| VII. Testes | PASS | Por risco: parser, projeção mínima (nenhuma coluna descartada em banco ou sessão), constraints, carga, reimportação, atomicidade com falha injetada, concorrência, idempotência, permissões e UI. |
| VIII. Design System | PASS, com gate pendente | Reusa os componentes da 001 (Table, Pagination, Filter Bar, File Upload, Page Header, Badge, Empty State). `frontend-implementer` com `frontend-design`; `impeccable critique` obrigatório depois do `code-reviewer`. |
| IX. Progressive Enhancement | PASS | Consulta por GET sem JS; importação por POST/redirect/GET; `envio.js` só como aprimoramento. |
| X. Performance | PASS | Lotes de 500; índices; paginação em todas as listas; `select_related` no histórico. |
| XI. Dependências | PASS | Nenhuma nova. |
| XII. Manutenibilidade | PASS | Nomes em pt-BR (`Fornecedor`, `leitura_fornecedores`); nomes do SCPI (`CODIF`, `INSMF`...) só na camada de leitura. |
| XIII. Migrações | PASS | Esquema efêmero (v1.2.0): só models, `make resetdb`. |
| XIV. Observabilidade | PASS | Logger `fornecedores.importacao`, sem conteúdo do arquivo nem dados pessoais. |

**Re-check pós-design**: `data-model.md` e os contratos mantêm todos os itens. Nenhuma violação
nova.

## Project Structure

### Documentation (this feature)

```text
specs/004-importacao-fornecedores/
├── spec.md
├── plan.md                         # este arquivo
├── research.md                     # R1–R12
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── arquivo-fornecedores.md     # leitura, recusas, projeção, exemplos normativos
│   ├── rotas-e-autorizacao.md      # rotas, papel/capability, respostas
│   └── interface-importacao.md     # assinaturas internas (testes e implementação)
├── checklists/requirements.md
└── tasks.md                        # /speckit-tasks
```

### Source Code (repository root)

```text
config/settings/base.py            # ALTERADO: INSTALLED_APPS += "fornecedores" (depois de
                                   #   "catalogo"); LOGGING do logger "fornecedores.importacao"
config/urls.py                     # ALTERADO: include("fornecedores.urls") em "fornecedores/"

fornecedores/                      # NOVO app
├── apps.py
├── models.py                      # Fornecedor, ExecucaoImportacaoFornecedores,
│                                  #   ExcecaoImportacaoFornecedores, AlteracaoFornecedor,
│                                  #   MotivoRecusaFornecedor, CampoFornecedor
├── leitura_fornecedores.py        # parser puro: CRLF, cabeçalho, validação, projeção mínima
├── importacao.py                  # plano, impressão digital, prévia (projeção) em sessão,
│                                  #   efetivação sob advisory lock
├── forms.py                       # ArquivoFornecedoresForm, ConsultaFornecedoresForm
├── views.py                       # consulta, envio (upload em memória), prévia, confirmação,
│                                  #   cancelamento, histórico, detalhe
├── urls.py                        # app_name = "fornecedores"
├── templates/fornecedores/
│   ├── consulta.html              # página + partial de resultados (HTMX)
│   ├── importacao_envio.html
│   ├── importacao_previa.html
│   ├── historico.html
│   └── execucao_detalhe.html
└── static/fornecedores/css/fornecedores.css   # só composição específica, se precisar

contas/views.py                    # ALTERADO: flags pode_importar_fornecedores,
                                   #   pode_consultar_fornecedores
contas/templates/contas/home.html  # ALTERADO: links condicionais
contas/management/commands/seed_dev.py  # ALTERADO: importa docs/CSVs/fornecedores.csv quando
                                        #   existir; ausente → aviso, sem falhar

tests/
├── fixtures/fornecedores/*.csv                   # NOVO: sintéticas, dados fictícios
├── test_fornecedores_leitura.py                  # parser e projeção (sem banco)
├── test_fornecedores_modelos.py                  # constraints
├── test_fornecedores_importacao.py               # carga inicial, totais, recusas
├── test_fornecedores_reimportacao.py             # atualização, alterações, bloqueio, ausentes
├── test_fornecedores_atomicidade.py              # falha injetada, concorrência, idempotência
├── test_fornecedores_dados_minimos.py            # INV-SUPPLIER-004: banco, sessão, log, disco
├── test_fornecedores_views_importacao.py         # fluxo HTTP envio → prévia → confirmação
├── test_fornecedores_historico.py
├── test_fornecedores_consulta.py                 # código, nome, documento, HTMX, estados
├── test_fornecedores_permissoes.py               # papel × rota
├── test_fornecedores_sem_criacao_manual.py       # SC-008
└── test_fornecedores_arquivo_real.py             # opcional, FORNECEDORES_CSV_REAL
```

**Structure Decision**: app novo na raiz, com a convenção de `catalogo`. Testes em `tests/`.

## Fluxos

### Envio, prévia e confirmação

```text
POST /fornecedores/importacao/        [CHEFE_ALMOXARIFADO]
  upload só em memória (≤ 10 MB)
  leitura_fornecedores.ler_fornecedores(conteudo)
                                      → recusa de arquivo: re-render com erro, nada guardado
                                      → ok: LeituraFornecedores com projeção mínima
  sessão["fornecedores_importacao_previa"] = {token, nome, tamanho, sha256, projeção zlib+b64}
  bytes do arquivo descartados → 302 /previa/

GET  /fornecedores/importacao/previa/
  importacao.calcular_plano(leitura, sha256)  # só SELECTs

POST /fornecedores/importacao/confirmar/
  transaction.atomic():
    pg_advisory_xact_lock(CHAVE_LOCK_IMPORTACAO_FORNECEDORES)
    token já confirmado → PreviaJaConfirmada
    plano = calcular_plano(leitura, sha256, bloquear=True)
    impressão digital ≠ enviada → PreviaDesatualizada
    aplicar_plano(...)   # execução, inserções, updates, alterações, recusas
  descarta a prévia → 302 detalhe
```

## Autorização

Ver [rotas-e-autorizacao.md](./contracts/rotas-e-autorizacao.md). Consulta → `PERM-SUPPLIER-VIEW`
(`ROLE-WAREHOUSE-STAFF`); envio, prévia, confirmação e cancelamento →
`PERM-SUPPLIER-IMPORT-EXECUTE` (`ROLE-WAREHOUSE-HEAD`); histórico e detalhe →
`PERM-SUPPLIER-IMPORT-HISTORY-VIEW` (`ROLE-WAREHOUSE-HEAD`). Nenhuma capability é criada, ampliada
ou redefinida.

## Regras canônicas aplicadas e preservadas

| ID | Mecanismo |
|---|---|
| `PERM-SUPPLIER-VIEW` | `ExigePapelMixin(FUNCIONARIO_ALMOXARIFADO)` na consulta |
| `PERM-SUPPLIER-IMPORT-EXECUTE` | `ExigePapelMixin(CHEFE_ALMOXARIFADO)` em envio/prévia/confirmação/cancelamento; duas etapas |
| `PERM-SUPPLIER-IMPORT-HISTORY-VIEW` | `ExigePapelMixin(CHEFE_ALMOXARIFADO)` em histórico/detalhe |
| `INV-AUTH-001` | comportamento nativo da 002 + teste nas rotas novas |
| `INV-SUPPLIER-001` | `codif` texto, `editable=False`, fora dos updates, `CHECK` de dígitos; busca exata sem completar |
| `INV-SUPPLIER-002` | `UNIQUE(codif)`; duplicados do arquivo recusados; nome e documento nunca usados como chave |
| `INV-SUPPLIER-003` | inserção e update só em `aplicar_plano`; sem admin nem CRUD |
| `INV-SUPPLIER-004` | projeção na leitura; sessão só com a projeção; upload em memória; recusas sem eco; teste dedicado |
| `INV-SUPPLIER-005` | `bloqueado` fiel ao arquivo; aplicação da regra na spec 003 |
| `INV-STOCK-004` | `transaction.atomic()` único na confirmação, aplicado por analogia; teste com falha injetada |
| `INV-SCPI-001` | só upload manual; nenhuma chamada de rede |

## Testes

Priorizados por risco. O `test-engineer` revisa e completa antes da implementação.

- **Parser**: todos os exemplos de [arquivo-fornecedores.md §5](./contracts/arquivo-fornecedores.md);
  BOM; coluna vazia final; LF embutido; ordem dos motivos; duplicados; recusas de arquivo; nenhum
  detalhe de recusa com valor de coluna descartada.
- **Dados mínimos** (`INV-SUPPLIER-004`, crítico): uma fixture com valores-sentinela nas colunas
  descartadas (conta, PIS, endereço, contato) e varredura das tabelas de `fornecedores`, da sessão
  (decodificada) e dos logs capturados — nenhum sentinela pode aparecer. A view de envio não pode
  criar `TemporaryUploadedFile`.
- **Constraints**: `IntegrityError` para `codif` duplicado, com não dígito ou nome vazio, e para
  totais inconsistentes.
- **Carga e reimportação**: US1 e US4; `codif` e `execucao_origem` imutáveis; derivados
  (`nome_busca`, `documento_digitos`) atualizados junto da origem; mesmo arquivo duas vezes → 0
  alterações.
- **Atomicidade e concorrência** (transacional): falha injetada → nada gravado; duas confirmações
  concorrentes → uma efetiva, a outra desatualizada; mesmo token → uma execução.
- **Fluxo HTTP**: envio e prévia não alteram tabelas de domínio; cancelamento limpa a sessão.
- **Permissões**: matriz rota × {anônimo, inativo, superusuário técnico, requisitante,
  funcionário do almoxarifado, chefe de setor, auditor, admin de sistema, chefe do almoxarifado}.
- **Consulta**: código exato (sem completar zeros), palavras em nome e fantasia sem acento/caixa,
  documento formatado e só dígitos, paginação, ordenação, fragmento HTMX, estado vazio.
- **SC-008**: nenhum modelo no admin; nenhuma rota aceita POST fora de envio/confirmar/cancelar.

## Spec/domain check

- **Spec**: FR-001 a FR-032 têm mecanismo (`data-model.md` → rastreamento; contratos).
- **Matrizes canônicas**: consistente com `PERM-SUPPLIER-*` e `INV-SUPPLIER-*` (v1.1). FR-017 cita
  `INV-STOCK-004` por analogia: a atomicidade da carga do cadastro vem do Princípio III, e a
  referência só registra o mesmo mecanismo.
- **ROADMAP**: dentro do recorte de `FOR`. Status atualizado ao gerar plano e tarefas.
- **Nenhum conflito material.**

## Open Questions

Nenhum PLAN BLOCKER. Não bloqueantes:

1. `ExigePapelMixin` e `OrdenacaoMixin` ficam em `catalogo` e são importados por `fornecedores`.
   Movê-los para um módulo comum é refactor separado, sugerido fora desta feature.
2. O `seed_dev` passa a importar fornecedores quando o CSV local existe. Sem o arquivo, segue sem
   fornecedores, com aviso.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Módulo de domínio `fornecedores/importacao.py` fora de models/views | Prévia (GET) e confirmação (POST, sob lock) precisam calcular o mesmo plano e comparar impressões digitais; a efetivação envolve quatro modelos numa transação. | Lógica na view duplicaria o cálculo entre duas views; num manager, misturaria sessão, arquivo e quatro modelos. |
