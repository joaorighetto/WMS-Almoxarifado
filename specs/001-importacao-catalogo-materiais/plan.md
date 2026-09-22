# Implementation Plan: Importação Inicial e Consulta do Catálogo de Materiais

**Branch**: `main` (sem branch dedicada, ver `spec.md`; o script do Spec Kit reporta
`001-importacao-catalogo-materiais` como identificador da feature) | **Date**: 2026-09-21 |
**Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-importacao-catalogo-materiais/spec.md`

## Summary

Trazer o catálogo oficial do SCPI para o WMS por upload de CSV em duas etapas: **prévia sem
persistência**, depois **confirmação explícita**, com efetivação atômica. A partir daí, qualquer
identidade de negócio consulta o catálogo por código exato ou palavras da descrição. A importação e
seu histórico auditável (totais, exceções por linha, divergências de saldo, alterações cadastrais)
são exclusivos do chefe do almoxarifado. A reimportação atualiza só os dados cadastrais do SCPI,
nunca o saldo, e aponta divergências informativas para a futura feature `INV`.

Abordagem técnica: novo app `catalogo`. Parser próprio em Python puro que recompõe registros
multilinha **antes** de separar campos e trata aspas como literais. Um módulo de domínio calcula o
**plano de importação** de forma determinística e o aplica. O mesmo cálculo serve à prévia (só
leituras) e à confirmação (recalculado sob advisory lock, conferido por impressão digital e
aplicado em uma única transação). Constraints de banco protegem `CADPRO`, saldo e totais. Busca por
coluna normalizada com índice trigram. Django Templates, com HTMX só na consulta. Nenhuma
dependência Python nova. Decisões e alternativas em [research.md](./research.md).

## Situação no roadmap e prontidão

- **Linha do ROADMAP**: `001` — Inclui: prévia e confirmação; saldo inicial; busca; histórico de
  importações; reimportação cadastral e divergências informativas. **Não inclui**: cadastro
  manual; manutenção local; correção de saldo; movimentações; integração automática. Este plano não
  atravessa nenhuma dessas exclusões. Observação interna e inativação (`MAT`), ajuste de saldo
  (`INV`), movimentações (`ENT`/`HIS`), locais de estoque e normalização de unidade ficam fora.
- **Dependência obrigatória `002`**: satisfeita (entregue em `main`, PR #5). Reutiliza `User`,
  `PapelUsuario`/`tem_papel` e a proteção nativa de sessão.
- **Clarificações**: suficientes para planejar. Os três pontos da spec (classificação,
  reexecução, entrega do arquivo), a análise do arquivo real e a emenda da prévia (FR-044a) estão
  registrados. Nenhum `[NEEDS CLARIFICATION]` resta, e o checklist de requisitos está completo.
  Nenhuma decisão de escopo foi reaberta. Os pontos que a spec deixa em aberto foram resolvidos
  como decisões técnicas e seis **interpretações** estão listadas em
  [research.md](./research.md#interpretações-confirmadas), **confirmadas** pelo dono do
  produto em 2026-09-21.
- **Pendência de artefato**: o CSV real está hoje **só localmente**, em `docs/domain-legacy/`,
  ignorado pelo Git. A implementação usa fixtures sintéticas. O aceite de SC-001/002/004/008 contra
  o dado real depende de o arquivo estar disponível no ambiente de validação (R14;
  [quickstart.md §5](./quickstart.md)). Segundo o ROADMAP, isso bloqueia aceite, não implementação.

## Technical Context

**Language/Version**: Python 3.13; Django 6.1.1 (travado em `uv.lock`, verificado).

**Primary Dependencies**: `django` (inclui `django.contrib.postgres`, a ser adicionado a
`INSTALLED_APPS` para `TrigramExtension`/`GinIndex`); `psycopg[binary]`. HTMX 2.x como arquivo
estático versionado em `static/vendor/htmx/`. Nenhum pacote Python novo.

**Storage**: PostgreSQL 16. Extensão `pg_trgm`, criada por migração. Pedido de prévia na sessão
padrão (backend `db`, serializer JSON).

**Testing**: pytest + pytest-django (`tests/` na raiz, `config.settings.test`). Testes
transacionais (`django_db(transaction=True)`) para concorrência. Fixtures CSV em bytes exatos em
`tests/fixtures/catalogo/`.

**Target Platform**: servidor Linux; navegador desktop/tablet do almoxarifado para importação e
histórico; celular também para consulta (`DESIGN.md` → Layout).

**Project Type**: aplicação Django monolítica server-rendered.

**Performance Goals**: prévia e confirmação de ~1.600 registros (arquivo real de 385 KB) dentro do
ciclo de requisição, sem espera perceptível. Escala até dezenas de milhares com lotes
(`bulk_create`/`bulk_update`, `batch_size=500`) e consultas por `cadpro__in` em blocos. Busca por
descrição "imediata" (SC-007) por índice GIN trigram. Consulta paginada em 50.

**Constraints**: nenhuma escrita de domínio antes da confirmação (FR-044a); efetivação atômica
(FR-038); saldo existente nunca escrito pela importação (FR-028); upload limitado a 10 MB.

**Scale/Scope**: catálogo de milhares a dezenas de milhares de materiais; um chefe do almoxarifado
importando ocasionalmente; consulta por todas as identidades de negócio.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design — ver final da tabela.*

| Princípio | Status | Justificativa |
|---|---|---|
| I. Simplicidade | PASS, com uma justificativa | Models, forms, class-based views, `Paginator` e mixins de acesso nativos. Uma exceção justificada em Complexity Tracking: o módulo de domínio `catalogo/importacao.py` (plano + efetivação), usado por duas views (prévia e confirmação) que precisam produzir **exatamente** o mesmo resultado. O parser fica separado (`leitura_scpi.py`) porque é lógica pura, sem banco, testável isoladamente. Nada de repository, DTO genérico ou service layer transversal. |
| II. Server-Driven | PASS | Django Templates. HTMX só na consulta (filtro/paginação). Importação por formulário comum. |
| III. Integridade de Dados | PASS | Transação única na confirmação; advisory lock serializa importações; `select_for_update` ordenado nos materiais existentes; `UNIQUE(cadpro)`, `CHECK` de formato de `cadpro`, `CHECK saldo >= 0`, `CHECK` da soma dos totais, `CHECK` da diferença da divergência; `saldo` fora da lista de atualização. |
| IV. Rastreabilidade | PASS | `ExecucaoImportacao` (quem, quando, arquivo por nome/tamanho/SHA-256), exceções por linha, divergências e `AlteracaoCadastralMaterial` com valor anterior e novo. Sem exclusão física (FK `PROTECT`, sem admin, sem view de exclusão). Saldo inicial com execução de origem. |
| V. Regras no Backend | PASS | Parser, validação, plano, autorização e decisão "código válido?" no servidor. Templates recebem dados prontos. |
| VI. Segurança | PASS | Papel explícito checado em toda rota antes de validar ou interpretar o arquivo; CSRF; limite de upload; conteúdo do arquivo nunca executado nem logado; nome do arquivo escapado; mensagens genéricas em falha. |
| VII. Testes | PASS | Estratégia por risco (ver "Testes"): parser, validação, invariantes de saldo, atomicidade com falha injetada, concorrência, idempotência, permissões por papel e UI. |
| VIII. Design System | PASS, com gate pendente | Usa tokens e primitivos existentes; os componentes que o `DESIGN.md` especifica para esta vertical (Table, Pagination, Filter Bar, Empty State, Loading, File Upload, Page Header, Badge) nascem em `components.css`. Implementação pelo `frontend-implementer` com `frontend-design`; `impeccable critique` obrigatório depois do `code-reviewer`; `impeccable document` para registrar os novos componentes. App shell continua em aberto: só links na Home. |
| IX. Progressive Enhancement | PASS | Consulta funciona por GET sem JS. Prévia e confirmação por POST/redirect/GET. O estado de processamento dos formulários de envio e confirmação é um JS pontual (`envio.js`, padrão de `contas/js/login.js`), sem o qual o fluxo continua funcionando. |
| X. Performance | PASS | Paginação em consulta, histórico e seções de exceções/divergências/alterações; índice trigram; `bulk_*` em lotes; sem N+1 (`select_related` em histórico e divergências). |
| XI. Dependências | PASS | Nenhum pacote novo. HTMX é a tecnologia de interatividade já normativa, versionada localmente (sem CDN). `pg_trgm` e `django.contrib.postgres` vêm do próprio stack. |
| XII. Manutenibilidade | PASS | Nomes de domínio em pt-BR (`Material`, `ExecucaoImportacao`, `DivergenciaSaldo`, `leitura_scpi`); nomes do SCPI (`CADPRO`, `QUAN3`...) só na camada de leitura do arquivo. |
| XIII. Migrações Seguras | PASS | Migrações só aditivas (novo app, nova extensão). Nenhum dado existente é tocado. |
| XIV. Observabilidade | PASS | Logger `catalogo.importacao`: confirmação (ids, SHA-256, totais), prévia desatualizada/duplicada e falha com traceback. Sem conteúdo do arquivo. |

**Re-check pós-design (Fase 1)**: `data-model.md` e os contratos mantêm todos os itens acima.
Nenhuma violação nova. O único item de Complexity Tracking permanece justificado.

## Project Structure

### Documentation (this feature)

```text
specs/001-importacao-catalogo-materiais/
├── spec.md                        # Existente
├── plan.md                        # Este arquivo
├── research.md                    # Fase 0 — R1–R16 + interpretações I-1..I-6
├── data-model.md                  # Fase 1
├── quickstart.md                  # Fase 1 — roteiro de validação (inclui arquivo real)
├── contracts/
│   ├── arquivo-scpi.md            # Contrato de entrada (leitura, recusas, motivos)
│   ├── interface-importacao.md    # Assinaturas internas compartilhadas por testes e implementação
│   └── rotas-e-autorizacao.md     # Rotas, capability/papel, respostas
├── checklists/requirements.md     # Existente
└── tasks.md                       # Fase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
config/
├── settings/base.py               # ALTERADO: INSTALLED_APPS += "django.contrib.postgres", "catalogo";
│                                  #   LOGGING do logger "catalogo.importacao"
└── urls.py                        # ALTERADO: include("catalogo.urls") em "catalogo/"

catalogo/                          # NOVO app
├── apps.py
├── models.py                      # Material, ExecucaoImportacao, ExcecaoImportacao,
│                                  #   DivergenciaSaldo, AlteracaoCadastralMaterial, MotivoRecusa,
│                                  #   CampoCadastral
├── leitura_scpi.py                # Parser puro: decodificação, cabeçalho, recomposição,
│                                  #   separação, validação por registro, normalização de busca
├── importacao.py                  # Plano (leitura do banco + impressão digital), prévia em
│                                  #   sessão, efetivação atômica sob advisory lock
├── forms.py                       # ArquivoImportacaoForm, ConsultaCatalogoForm
├── views.py                       # ExigePapelMixin + views de consulta, envio, prévia,
│                                  #   confirmação, cancelamento, histórico e detalhe
├── urls.py                        # app_name = "catalogo"
├── migrations/
│   ├── 0001_pg_trgm.py            # TrigramExtension
│   └── 0002_initial.py            # modelos, constraints e índices
├── templates/catalogo/
│   ├── consulta.html              # página
│   ├── _resultados_consulta.html  # fragmento (HTMX e página)
│   ├── importacao_envio.html
│   ├── importacao_previa.html
│   ├── historico.html
│   └── execucao_detalhe.html
└── static/catalogo/
    ├── css/catalogo.css           # só composição específica das telas
    └── js/envio.js                # estado "Processando…" nos formulários de envio/confirmação
                                   #   (aprimoramento; fluxo funciona sem JS)

contas/
├── views.py                       # ALTERADO: HomeView acrescenta flags de papel ao contexto
└── templates/contas/home.html     # ALTERADO: links condicionais

static/
├── css/components.css             # ALTERADO: primitivos Table, Pagination, Filter Bar, Empty
│                                  #   State, Loading, File Upload, Page Header, Badge
└── vendor/htmx/                   # NOVO: htmx-2.x.y.min.js + LICENSE

tests/
├── fixtures/catalogo/*.csv                  # NOVO: fixtures sintéticas em bytes exatos
├── conftest.py                              # ALTERADO: fixtures de usuários por papel e de CSV
├── test_catalogo_leitura_scpi.py            # parser e validação (sem banco)
├── test_catalogo_modelos.py                 # constraints de banco
├── test_catalogo_importacao.py              # plano + efetivação: carga inicial
├── test_catalogo_reimportacao.py            # atualização cadastral, saldo preservado, divergências
├── test_catalogo_atomicidade.py             # rollback com falha injetada, concorrência, idempotência
├── test_catalogo_views_importacao.py        # envio → prévia sem persistência → confirmação
├── test_catalogo_historico.py               # histórico e detalhe
├── test_catalogo_consulta.py                # busca, paginação, estados, HTMX
├── test_catalogo_permissoes.py              # matriz papel × rota, anônimo, inativo, superusuário
├── test_catalogo_sem_criacao_manual.py      # SC-005: nenhum caminho de criação/edição/exclusão
└── test_catalogo_arquivo_real.py            # opcional, via SCPI_CSV_REAL (aceite)
```

**Structure Decision**: um app novo (`catalogo`) na raiz, com a convenção da 002. Testes em
`tests/`. Primitivos visuais em `static/css/components.css`, compartilhados, e só composição de
tela em `catalogo/static/`.

## Fluxos

### Prévia e confirmação

```text
POST /catalogo/importacao/            [ROLE-WAREHOUSE-HEAD]
  form válido (≤10 MB) → leitura_scpi.decodificar/ler_cabecalho
    recusa de arquivo → re-renderiza com erro (nada gravado em lugar nenhum)
    ok → sessão["catalogo_importacao_previa"] = {token, nome, tamanho, sha256, conteúdo zlib}
       → 302 /previa/

GET /catalogo/importacao/previa/      [ROLE-WAREHOUSE-HEAD]
  importacao.calcular_plano(conteúdo)        # só SELECTs
  → totais, exceções, divergências (paginadas), impressão digital, token

POST /catalogo/importacao/confirmar/  [ROLE-WAREHOUSE-HEAD]
  token ≠ sessão → execução com esse token existe? → detalhe : envio
  transaction.atomic():
    pg_advisory_xact_lock(CHAVE_IMPORTACAO_SCPI)
    execução com esse token já existe? → nada gravado → detalhe "já confirmada"
    plano = calcular_plano(conteúdo, bloquear=True)   # select_for_update ordenado por pk
    plano.impressao_digital ≠ enviada → rollback → prévia "desatualizada"
    aplicar_plano(plano, usuario, token)              # execução, inserções, updates, rastros
  remove pedido da sessão → 302 detalhe da execução
```

### Plano de importação (determinístico)

```text
registros = leitura_scpi.ler(conteúdo)                   # recomposição + validação (R3, R5)
existentes = Material por cadpro__in(cadpros aceitos)    # em blocos
para cada registro aceito:
  cadpro novo      → inserção (saldo = saldo_inicial = QUAN3 arredondado)
  cadpro existente → atualização (campos cadastrais alterados, se houver)
                     QUAN3 ≠ saldo → divergência (saldo_wms, saldo_arquivo, diferença)
ausentes = total do catálogo − existentes citados por cadpro bem formado no arquivo
impressão digital = sha256(serialização canônica ordenada do plano + sha256 do arquivo)
```

## Autorização

Ver [rotas-e-autorizacao.md](./contracts/rotas-e-autorizacao.md). Resumo: consulta →
`PERM-MATERIAL-VIEW` (`ROLE-REQUESTER`); envio, prévia, confirmação e cancelamento →
`PERM-SCPI-IMPORT-EXECUTE` (`ROLE-WAREHOUSE-HEAD`); histórico e detalhe →
`PERM-SCPI-IMPORT-HISTORY-VIEW` (`ROLE-WAREHOUSE-HEAD`). `ExigePapelMixin` =
`LoginRequiredMixin` + `UserPassesTestMixin` com `tem_papel(papel_exigido)`. Anônimo → login;
autenticado sem papel → 403; inativo → tratado como anônimo (`INV-AUTH-001`). Nenhuma capability é
criada, ampliada ou redefinida.

## Regras canônicas aplicadas e preservadas

| ID | Mecanismo neste plano |
|---|---|
| `PERM-MATERIAL-VIEW` | `ExigePapelMixin(ROLE-REQUESTER)` na consulta |
| `PERM-SCPI-IMPORT-EXECUTE` | `ExigePapelMixin(ROLE-WAREHOUSE-HEAD)` em envio/prévia/confirmação/cancelamento; duas etapas obrigatórias (R8) |
| `PERM-SCPI-IMPORT-HISTORY-VIEW` | `ExigePapelMixin(ROLE-WAREHOUSE-HEAD)` em histórico/detalhe |
| `INV-AUTH-001` | comportamento nativo (002) + teste de regressão nas rotas novas |
| `INV-CATALOG-001` | `cadpro` texto, sem trim, `editable=False`, fora dos updates, `CHECK` de formato; exibição sem transformação |
| `INV-CATALOG-002` | `UNIQUE(cadpro)` + recusa de duplicados no arquivo + advisory lock |
| `INV-CATALOG-003` | inserção só em `importacao.aplicar_plano`; sem admin, sem views de CRUD |
| `INV-CATALOG-004` | campos cadastrais só mudam por `aplicar_plano` (reimportação) |
| `INV-CATALOG-005` | `unidade` gravada como lida; nenhum mapeamento |
| `INV-STOCK-001` | recusa de negativo + `CHECK saldo >= 0` |
| `INV-STOCK-002` | saldo só na inserção; `bulk_update` sem `saldo` |
| `INV-STOCK-003` | `DivergenciaSaldo` sem efeito em saldo |
| `INV-STOCK-004` | `transaction.atomic()` único na confirmação; teste com falha injetada |
| `INV-MOV-002` | `saldo_inicial` + `execucao_origem` imutáveis |
| `INV-SCPI-001` | só upload manual; nenhuma chamada de rede ou tarefa agendada |

## Testes

Priorizados por risco (Constitution VII). O `test-engineer` revisa e completa estes cenários antes
da implementação (ver `tasks.md`, fase de desenho de testes).

- **Parser** (`test_catalogo_leitura_scpi.py`): todos os exemplos normativos de
  [arquivo-scpi.md §5](./contracts/arquivo-scpi.md); BOM não contamina `CADPRO`; coluna vazia
  final; CRLF e LF; `\u2028` dentro do texto não quebra registro; dígito Unicode em `CADPRO` →
  inválido; ordem de motivos; todas as ocorrências de duplicado recusadas; recusas de arquivo.
- **Constraints** (`test_catalogo_modelos.py`): `IntegrityError` para `cadpro` duplicado, fora do
  formato, `saldo < 0`, totais inconsistentes e diferença inconsistente.
- **Carga inicial** (`test_catalogo_importacao.py`): US1 cenários 1–12; `saldo_inicial` e
  `execucao_origem` gravados; totais e exceções (US3 1–2).
- **Reimportação** (`test_catalogo_reimportacao.py`): US4 cenários 1–5; saldo nunca muda (SC-009),
  inclusive com divergência e material nunca movimentado; divergência com sinal; mesmo arquivo
  duas vezes → 0 alterações e 0 divergências; `AlteracaoCadastralMaterial` por campo; `cadpro`,
  `saldo_inicial` e `execucao_origem` imutáveis.
- **Atomicidade/concorrência** (`test_catalogo_atomicidade.py`, transacional): falha injetada no
  meio da efetivação → nenhum material, execução, exceção ou divergência; duas confirmações
  concorrentes do mesmo arquivo sobre catálogo vazio → uma efetiva e a outra recebe "prévia
  desatualizada", sem duplicata; confirmação repetida com o mesmo token → uma execução.
- **Fluxo HTTP** (`test_catalogo_views_importacao.py`): envio + prévia **não** alteram nenhuma
  tabela de domínio (contagem antes/depois); prévia recalculada = confirmada; cancelamento limpa a
  sessão; recusa de arquivo sem sessão.
- **Permissões** (`test_catalogo_permissoes.py`): matriz rota × {anônimo, inativo, superusuário
  técnico, requisitante, funcionário do almoxarifado, chefe de setor, auditor, admin de sistema,
  chefe do almoxarifado}; POST de envio sem papel não grava sessão.
- **Consulta** (`test_catalogo_consulta.py`): código exato; código parcial/inválido não consulta;
  descrição sem acento/caixa; paginação; estado vazio; fragmento com `HX-Request`.
- **SC-005** (`test_catalogo_sem_criacao_manual.py`): nenhum modelo do catálogo registrado no
  admin; nenhuma rota do catálogo aceita POST fora de envio/confirmar/cancelar.
- **Arquivo real** (`test_catalogo_arquivo_real.py`): opcional, ver R14.

## Spec/domain check

- **Spec**: todos os FR-001–FR-047 e FR-007a/FR-044a têm mecanismo identificado
  (`data-model.md` → rastreamento; contratos). SC-006 (uma interação) e SC-007 (imediato) são
  atendidos por busca exata indexada e índice trigram. Não há métrica automatizada de SC-007; ela é
  verificada no roteiro manual.
- **Matrizes canônicas**: nenhuma contradição. FR-045 fala em "autenticação" para consultar; a
  matriz exige `ROLE-REQUESTER`, mais estrito, e prevalece (exclui só o superusuário técnico, sem
  papéis por definição). Não há mudança de matriz.
- **ROADMAP**: dentro do recorte da 001. Dependência 002 satisfeita. Status atualizado para refletir
  plano e tarefas gerados.
- **Referência desatualizada (não normativa)**: a spec cita
  `docs/domain-legacy/reconciliation/permissions-reconciliation.md` §7.9. O arquivo vigente está em
  `docs/domain/reconciliation/permissions-reconciliation.md` (§7.9 confirmado lá). É referência
  histórica, sem efeito no plano. Corrigi-la é ajuste da spec, fora desta etapa.
- **Nenhum conflito material** entre Constitution, `PRODUCT.md`, matrizes, ROADMAP e spec.

## Open Questions

Nenhum PLAN BLOCKER. Não bloqueantes:

1. Interpretações I-1 a I-6 ([research.md](./research.md#interpretações-confirmadas)): **confirmadas**
   pelo dono do produto em 2026-09-21.
2. Disponibilidade do CSV real para o aceite (R14): hoje só local e fora do Git. Se isso satisfaz a
   pendência "disponibilização de amostra" do ROADMAP é decisão do dono do produto.
3. **D-1 — linha física vazia** (levantada na T006): **decidida pelo dono do produto em
   2026-09-21 — ignorar** linha vazia fora de registro incompleto. Regra em research R3 e
   `contracts/arquivo-scpi.md` §2.
4. A spec não pede guardar o conteúdo do arquivo importado, só identificá-lo (nome, tamanho,
   SHA-256). Se for desejável reprocessar ou auditar o arquivo original depois, é requisito novo.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Módulo de domínio `catalogo/importacao.py` fora de models/views | Prévia (GET) e confirmação (POST, sob lock) precisam calcular **o mesmo** plano e comparar impressões digitais. A efetivação envolve cinco modelos em uma transação. | Lógica na view duplicaria o cálculo entre duas views. Lógica em `Material.objects` misturaria arquivo, sessão e cinco modelos em um manager de um só modelo, sem responsabilidade enunciável. |
