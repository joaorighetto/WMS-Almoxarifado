---

description: "Task list for implementing 004-importacao-fornecedores"
---

# Tasks: Importação do Cadastro de Fornecedores do SCPI

**Input**: Design documents from `specs/004-importacao-fornecedores/` (`spec.md`, `plan.md`,
`research.md`, `data-model.md`, `contracts/arquivo-fornecedores.md`,
`contracts/rotas-e-autorizacao.md`, `contracts/interface-importacao.md`, `quickstart.md`)

**Prerequisites**: `plan.md` (Constitution Check PASS), `spec.md` (4 user stories, P1–P4),
`research.md` (R1–R12).

**Tests**: obrigatórios (Constitution VII). A feature toca dados pessoais, permissões, transações e
concorrência. Em cada story, os testes vêm antes da implementação e devem falhar primeiro.

**Organization**: por user story, na ordem de prioridade da spec. O modelo de dados inteiro fica na
fase Foundational, porque US1, US3 e US4 compartilham as mesmas tabelas.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: paralelizável (arquivo diferente, sem dependência de task incompleta)
- **[Story]**: US1–US4; ausente em Setup, Foundational e Polish
- **Executor**: sem marca → `task-implementer`; **(test-engineer)** → só testes;
  **(frontend-implementer)** → frontend significativo com `frontend-design`, dentro do
  `DESIGN.md`; **(coordenador)** → etapa do Claude principal
- **Aplica / Preserva**: IDs canônicos das matrizes

## Path Conventions

Django monolítico, apps na raiz (`contas/`, `catalogo/`, novo `fornecedores/`), testes em `tests/`,
primitivos CSS em `static/css/components.css`. Sem migrations: depois de mudar models,
`make resetdb`.

## Escopo — limite para todas as tasks (ROADMAP, linha FOR, "Não inclui")

Nenhuma task pode introduzir: criação, edição ou exclusão manual de fornecedor; compras,
licitações, contratos ou pagamentos; armazenamento de qualquer coluna do arquivo fora de `CODIF`,
`NOME`, `NOM_FANT`, `INSMF`, `CODTIP`, `BLOQ_OPCAO`, `MSG_BLOQ` e `TIPO_BLOQ` — nem em banco, nem
em sessão, nem em log, nem em disco temporário; integração automática com o SCPI; registro de
entradas ou escolha de emitente (spec 003); refactor de `catalogo` (só importar dele). Se uma task
parecer exigir isso, o implementador **para e reporta** ao coordenador.

---

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 Criar o app `fornecedores` na raiz (`fornecedores/__init__.py`, `fornecedores/apps.py`
  com `FornecedoresConfig`, `default_auto_field` igual ao de `catalogo`), incluí-lo em
  `INSTALLED_APPS` de `config/settings/base.py` **depois** de `"catalogo"` (o `pg_trgm` é criado no
  `pre_migrate` de `catalogo`) e acrescentar `path("fornecedores/", include("fornecedores.urls"))`
  em `config/urls.py`, com `fornecedores/urls.py` vazio (`app_name = "fornecedores"`)
- [ ] T002 [P] Acrescentar o logger `fornecedores.importacao` em `LOGGING` de
  `config/settings/base.py`, no mesmo formato do logger `catalogo.importacao`
- [ ] T003 [P] (test-engineer) Criar fixtures sintéticas em bytes exatos em
  `tests/fixtures/fornecedores/`, cobrindo os 10 exemplos normativos de
  `contracts/arquivo-fornecedores.md` §5, mais: `valido_basico.csv` (UTF-8 com BOM, CRLF, cabeçalho
  com as 8 colunas obrigatórias e colunas descartadas `BANCO;AGENC;CONTA;PISPASEP;ENDER;CONTATO`,
  delimitador final); `sentinelas.csv`, com valores-sentinela únicos (ex. `SENTINELA-CONTA-9137`)
  em todas as colunas descartadas, inclusive um LF dentro de `CONTATO`; `sem_coluna_bloq.csv`;
  `somente_lf.csv`; `reimportacao_*.csv` para US4. Somente dados fictícios (CNPJ/CPF inventados).
  Acrescentar em `tests/conftest.py` `FIXTURES_FORNECEDORES_DIR` e a fixture
  `csv_fornecedores(nome) -> bytes`

---

## Phase 2: Foundational (Blocking Prerequisites)

- [ ] T004 (coordenador) Acionar o `test-engineer` com `plan.md` → "Testes",
  `contracts/arquivo-fornecedores.md` e `contracts/interface-importacao.md` para revisar e completar
  os cenários críticos antes da implementação, com prioridade para `INV-SUPPLIER-004` (dados
  mínimos) e `INV-STOCK-004` (atomicidade)
- [ ] T005 Criar em `fornecedores/models.py`, conforme `data-model.md`: `MotivoRecusaFornecedor`
  (`COLUNAS_DESLOCADAS`, `CODIF_AUSENTE`, `CODIF_INVALIDO`, `CODIF_DUPLICADO`, `NOME_AUSENTE`,
  `SITUACAO_BLOQUEIO_INVALIDA`, com rótulos em pt-BR); `CampoFornecedor` (os 7
  `CAMPOS_ATUALIZAVEIS`); `ExecucaoImportacaoFornecedores` (`token_previa` UUID `UNIQUE`;
  `executada_por` FK `contas.User` `PROTECT`; `concluida_em`; `nome_arquivo` max 255;
  `tamanho_arquivo`; `sha256_arquivo` max 64; totais com `CHECK total_recebidos = inseridos +
  atualizados + rejeitados` e `CHECK total_atualizados_com_alteracao <= total_atualizados`;
  ordering `-concluida_em`, `-pk`); `Fornecedor` (`codif` texto `UNIQUE`, `editable=False`,
  `CHECK codif ~ '^[0-9]+$'`; `nome` com `CHECK` "trim(nome) <> ''"; `nome_fantasia`,
  `documento`, `tipo`, `motivo_bloqueio`, `tipo_bloqueio` texto `blank=True`; `bloqueado`
  booleano; derivados `documento_digitos` (índice btree) e `nome_busca` (`GinIndex` com
  `gin_trgm_ops`); `execucao_origem` FK `PROTECT`); `ExcecaoImportacaoFornecedores` (`execucao`
  FK `PROTECT` `related_name="excecoes"`, `linha` ≥ 1, `codif` blank, `motivo`, `detalhe`;
  ordering `linha`); `AlteracaoFornecedor` (`execucao` e `fornecedor` FK `PROTECT`, `campo`,
  `valor_anterior`, `valor_novo`). Nada registrado no admin. Rodar `make resetdb`.
  Aplica: —. Preserva: `INV-SUPPLIER-001`, `INV-SUPPLIER-002`, `INV-SUPPLIER-004`
- [ ] T006 [P] (test-engineer) Escrever `tests/test_fornecedores_modelos.py`: `IntegrityError` para
  `codif` duplicado, com não dígito (`"12A"`, `"٣"`), nome vazio ou só espaços, e totais
  inconsistentes; `Fornecedor` não registrado no admin

**Checkpoint**: modelos criados, constraints testadas.

---

## Phase 3: User Story 1 - Carregar o cadastro de fornecedores (Priority: P1) 🎯 MVP

**Goal**: o chefe envia o CSV, vê a prévia sem gravação, confirma e o cadastro é gravado de forma
atômica, sem nenhum dado fora dos mínimos.

**Independent Test**: com banco vazio, enviar `valido_basico.csv`, conferir a prévia, confirmar e
verificar fornecedores, totais e recusas; nenhum sentinela de `sentinelas.csv` em banco, sessão ou
log.

### Tests for User Story 1 ⚠️ (escrever primeiro; devem falhar)

- [ ] T007 [P] [US1] (test-engineer) Escrever `tests/test_fornecedores_leitura.py` (sem banco):
  todos os exemplos de `contracts/arquivo-fornecedores.md` §5; recusas de arquivo do §1, com o
  código; BOM e coluna vazia final não contaminam valores; `\n` dentro de campo não quebra
  registro; último registro sem CRLF aceito; ordem dos motivos do §3; `CODIF_DUPLICADO` em todas as
  ocorrências; valores preservados sem `strip`; `detalhe` e `codif` de recusa nunca contêm valor de
  outra coluna; `para_json`/`de_json` fazem ida e volta sem perda; `somente_digitos`
- [ ] T008 [P] [US1] (test-engineer) Escrever `tests/test_fornecedores_importacao.py`: carga
  inicial via `calcular_plano` + `confirmar_importacao`; totais (recebidos = inseridos +
  atualizados + rejeitados); recusas gravadas com linha, motivo e `codif`; `bloqueado` e motivo
  gravados; `nome_busca` e `documento_digitos` derivados; `execucao_origem`
- [ ] T009 [P] [US1] (test-engineer) Escrever `tests/test_fornecedores_dados_minimos.py`
  (`INV-SUPPLIER-004`, crítico): com `sentinelas.csv`, após envio, prévia e confirmação, nenhum
  sentinela aparece em nenhuma coluna de texto de nenhuma tabela de `fornecedores`, nem na sessão
  decodificada (`zlib` + base64 + JSON), nem nos logs capturados (`caplog`); o POST de envio não
  cria `TemporaryUploadedFile` (verificar `request.upload_handlers` ou interceptar o handler) e a
  sessão não contém os bytes do arquivo
- [ ] T010 [P] [US1] (test-engineer) Escrever `tests/test_fornecedores_atomicidade.py`
  (`transaction=True`): falha injetada em `aplicar_plano` → nenhum fornecedor, execução, recusa ou
  alteração; duas confirmações concorrentes do mesmo arquivo sobre banco vazio → uma efetiva, a
  outra `PreviaDesatualizada`, sem duplicata; mesmo token duas vezes → uma execução
  (`PreviaJaConfirmada`); importação de fornecedores e do catálogo não compartilham a chave de lock; desempenho (SC-006):
  arquivo sintético de 10.035 registros gerado em memória, com prévia (`guardar_pedido` +
  `calcular_plano`) e confirmação em menos de 30 s cada
- [ ] T011 [P] [US1] (test-engineer) Escrever `tests/test_fornecedores_views_importacao.py`: `GET`
  e `POST` de envio; recusa de arquivo re-renderiza com erro e não grava sessão; envio e prévia não
  alteram nenhuma tabela de `fornecedores` (contagem antes/depois); prévia mostra totais e recusas
  paginadas; confirmação redireciona ao detalhe com mensagem de totais; confirmação repetida →
  detalhe com "já confirmada"; token diferente → envio; cancelamento limpa a sessão; erro
  inesperado → mensagem genérica e sessão mantida
- [ ] T012 [P] [US1] (test-engineer) Escrever a parte de importação de
  `tests/test_fornecedores_permissoes.py`: envio, prévia, confirmação e cancelamento para
  {anônimo → login, inativo → login, superusuário técnico → 403, requisitante → 403, funcionário do
  almoxarifado → 403, chefe de setor → 403, auditor → 403, admin de sistema → 403, chefe do
  almoxarifado → 200/302}; POST de envio sem papel não grava sessão

### Implementation for User Story 1

- [ ] T013 [US1] Implementar `fornecedores/leitura_fornecedores.py` conforme
  `contracts/interface-importacao.md` e `contracts/arquivo-fornecedores.md`: reusar
  `catalogo.leitura_scpi.decodificar` e `ArquivoRecusado`; recusar arquivo com `\n` sem nenhum
  `\r\n` (`ARQUIVO_TERMINADOR_INVALIDO`); separar registros só por `\r\n`, ignorando registros
  vazios; validar o cabeçalho (8 colunas obrigatórias; ausente → `ARQUIVO_COLUNA_OBRIGATORIA_AUSENTE`;
  duplicada → `ARQUIVO_COLUNA_DUPLICADA`); validar cada registro na ordem do §3, com `[0-9]+`
  (nunca `\d`); projetar os aceitos para `FornecedorLido`, descartando as demais colunas já na
  leitura; `para_json`/`de_json`; `somente_digitos`.
  Preserva: `INV-SUPPLIER-001`, `INV-SUPPLIER-004`
- [ ] T014 [US1] Implementar `calcular_plano`, `aplicar_plano` e `confirmar_importacao` em
  `fornecedores/importacao.py`, no molde de `catalogo/importacao.py` (research R5): existentes por
  `codif__in` em lotes de 500 (`select_for_update().order_by("pk")` quando `bloquear`); inserções
  com derivados e `execucao_origem`; atualizações só dos `CAMPOS_ATUALIZAVEIS` que mudaram, com
  derivados e uma `AlteracaoFornecedor` por campo (`bloqueado` como `"S"`/`"B"`), defesa explícita
  contra escrever `codif`/`execucao_origem`; ausentes contados no banco; impressão digital canônica
  com o SHA-256 do arquivo; `pg_advisory_xact_lock` com `CHAVE_LOCK_IMPORTACAO_FORNECEDORES`
  própria; idempotência por token; log sem dados de fornecedor.
  Aplica: `PERM-SUPPLIER-IMPORT-EXECUTE` (duas etapas). Preserva: `INV-SUPPLIER-002`,
  `INV-SUPPLIER-003`, `INV-STOCK-004`
- [ ] T015 [US1] Implementar `guardar_pedido`, `obter_pedido` e `descartar_pedido` em
  `fornecedores/importacao.py` (research R3): lê e projeta no envio, guarda na sessão só
  `{token, nome_arquivo, tamanho, sha256, leitura (para_json → zlib → base64)}`; os bytes nunca vão
  para a sessão; recusa de arquivo propaga `ArquivoRecusado` sem tocar a sessão.
  Preserva: `INV-SUPPLIER-004`
- [ ] T016 [P] [US1] Criar `ArquivoFornecedoresForm` em `fornecedores/forms.py`: `FileField`
  obrigatório, `allow_empty_file=True`, mesmo widget do `ArquivoImportacaoForm` do catálogo, limite
  de `catalogo.leitura_scpi.LIMITE_TAMANHO_ARQUIVO` com código `ARQUIVO_TAMANHO_EXCEDIDO`; expõe
  `conteudo_arquivo`
- [ ] T017 [US1] Implementar em `fornecedores/views.py` as views de importação com
  `catalogo.views.ExigePapelMixin` e `papel_exigido = Papel.CHEFE_ALMOXARIFADO`, conforme
  `contracts/rotas-e-autorizacao.md`: envio (GET/POST) com upload só em memória (research R4:
  `csrf_exempt` na view e `csrf_protect` no processamento; handler em memória limitado a 10 MB;
  a troca de handlers ocorre antes de qualquer acesso a `request.POST`/`FILES`), prévia,
  confirmação (tabela "Efetivação") e cancelamento; registrar as rotas em `fornecedores/urls.py`.
  Aplica: `PERM-SUPPLIER-IMPORT-EXECUTE`. Preserva: `INV-AUTH-001`, `INV-SUPPLIER-004`
- [ ] T018 [US1] Em `contas/views.py`, acrescentar a `HomeView.get_context_data` as flags
  `pode_importar_fornecedores` (`Papel.CHEFE_ALMOXARIFADO`) e `pode_consultar_fornecedores`
  (`Papel.FUNCIONARIO_ALMOXARIFADO`), derivadas do mesmo `codigos_papeis`, e atualizar a docstring;
  acrescentar os testes correspondentes em `tests/test_contas_home_papeis.py`
- [ ] T019 [US1] (frontend-implementer) Criar `fornecedores/templates/fornecedores/importacao_envio.html`,
  `importacao_previa.html` e `execucao_detalhe.html` (este com totais e recusas paginadas; as
  alterações entram na US4), no molde das telas equivalentes de `catalogo/templates/catalogo/`,
  com o total de existentes ausentes do arquivo na prévia e no detalhe (FR-016, FR-024),
  reusando `catalogo/_paginacao.html`, `catalogo/_mensagens.html`, `catalogo_extras` e
  `catalogo/js/envio.js`, e os primitivos de `static/css/components.css`; e os links condicionais de
  fornecedores em `contas/templates/contas/home.html`, no mesmo padrão dos links do catálogo.
  Nenhum dado de fornecedor além dos mínimos na tela

**Checkpoint**: US1 funcional e testável sozinha.

---

## Phase 4: User Story 2 - Consultar fornecedores (Priority: P2)

**Goal**: a equipe do almoxarifado localiza fornecedores por código, nome ou documento.

**Independent Test**: com fornecedores importados, cada critério encontra o fornecedor esperado, e
outros papéis recebem 403.

### Tests for User Story 2 ⚠️

- [ ] T020 [P] [US2] (test-engineer) Escrever `tests/test_fornecedores_consulta.py`: `codigo` exato
  (`7` não encontra `007`, não completa zeros); `codigo` com não dígito → erro de validação;
  palavras de `nome` sem acento e caixa, em qualquer ordem, em `nome` ou `nome_fantasia`;
  `documento` formatado e só com dígitos → mesmo resultado; menos de 3 dígitos → erro; filtros
  combinados por E; ordenação padrão por nome com desempate por código; ordem desconhecida →
  padrão; paginação de 50; estado vazio; fragmento com `HX-Request`; bloqueado com situação e
  motivo visíveis
- [ ] T021 [P] [US2] (test-engineer) Acrescentar a `tests/test_fornecedores_permissoes.py` a
  consulta: funcionário do almoxarifado e chefe do almoxarifado → 200; requisitante, chefe de
  setor, auditor, admin, superusuário técnico → 403; anônimo e inativo → login

### Implementation for User Story 2

- [ ] T022 [P] [US2] Criar `ConsultaFornecedoresForm` em `fornecedores/forms.py` (`codigo`, `nome`,
  `documento`), conforme `contracts/rotas-e-autorizacao.md` → "Consulta"
- [ ] T023 [US2] Implementar `ConsultaFornecedoresView` em `fornecedores/views.py`
  (`catalogo.ordenacao.OrdenacaoMixin` + `ExigePapelMixin`, `papel_exigido =
  Papel.FUNCIONARIO_ALMOXARIFADO`), com filtros, ordenação, paginação e fragmento HTMX no molde de
  `ConsultaCatalogoView`; registrar a rota `consulta`.
  Aplica: `PERM-SUPPLIER-VIEW`. Preserva: `INV-SUPPLIER-001`, `INV-AUTH-001`
- [ ] T024 [US2] (frontend-implementer) Criar `fornecedores/templates/fornecedores/consulta.html`
  (página + partial de resultados) no molde de `catalogo/consulta.html`, com a situação de bloqueio
  como Badge e sem nenhuma ação de criar, editar ou excluir

**Checkpoint**: US1 e US2 funcionam independentemente.

---

## Phase 5: User Story 3 - Auditar as importações (Priority: P3)

**Goal**: o chefe consulta o histórico e o detalhe de cada execução.

**Independent Test**: duas importações aparecem no histórico, da mais recente para a mais antiga,
cada uma com seus totais e recusas.

- [ ] T025 [P] [US3] (test-engineer) Escrever `tests/test_fornecedores_historico.py`: ordem padrão,
  ordenação e paginação do histórico; detalhe com recusas paginadas; execuções preservadas; sem
  N+1 (`django_assert_max_num_queries`); e acrescentar a `tests/test_fornecedores_permissoes.py`
  histórico e detalhe (só o chefe do almoxarifado)
- [ ] T026 [US3] Implementar `HistoricoImportacoesView` e `ExecucaoDetalheView` em
  `fornecedores/views.py` (`papel_exigido = Papel.CHEFE_ALMOXARIFADO`, `select_related`), no molde
  das views do catálogo; registrar as rotas `historico` e `execucao_detalhe`.
  Aplica: `PERM-SUPPLIER-IMPORT-HISTORY-VIEW`
- [ ] T027 [US3] (frontend-implementer) Criar `fornecedores/templates/fornecedores/historico.html`
  no molde de `catalogo/historico.html` e ligar o link do histórico na Home e na tela de envio

**Checkpoint**: histórico auditável.

---

## Phase 6: User Story 4 - Reimportar o cadastro (Priority: P4)

**Goal**: reimportar atualiza os existentes, registra as alterações e não toca os ausentes.

**Independent Test**: importar, reimportar com nome alterado, bloqueio trocado e um registro
removido; conferir atualizações, trilha e ausentes.

- [ ] T028 [P] [US4] (test-engineer) Escrever `tests/test_fornecedores_reimportacao.py`: US4
  cenários 1–5; `AlteracaoFornecedor` por campo, com `bloqueado` como `"S"`/`"B"`; `nome_busca` e
  `documento_digitos` reescritos quando a origem muda; `codif` e `execucao_origem` nunca mudam;
  mesmo arquivo duas vezes → 0 alterações; ausentes contados e intactos; prévia desatualizada se o
  cadastro mudar entre a prévia e a confirmação
- [ ] T029 [US4] Completar em `fornecedores/importacao.py` o que os testes de T028 exigirem além do
  feito em T014 (sem ampliar escopo). Preserva: `INV-SUPPLIER-003`, `INV-SUPPLIER-005`
- [ ] T030 [US4] (frontend-implementer) Acrescentar à prévia e ao detalhe da execução a lista
  paginada de alterações (campo, anterior, novo), no molde de
  `catalogo/execucao_detalhe.html`

**Checkpoint**: todas as stories funcionais.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T031 [P] (test-engineer) Escrever `tests/test_fornecedores_sem_criacao_manual.py` (SC-008):
  nenhum modelo de `fornecedores` no admin; nenhuma rota de `fornecedores` aceita POST fora de
  envio, confirmar e cancelar
- [ ] T032 [P] (test-engineer) Escrever `tests/test_fornecedores_arquivo_real.py`, pulado sem
  `FORNECEDORES_CSV_REAL`: 10.035 recebidos e inseridos, 0 rejeitados, 18 bloqueados, campos
  conferem com o arquivo, nenhum dado de coluna descartada no banco (SC-001 a SC-003), prévia e
  confirmação em menos de 30 s cada (SC-006)
- [ ] T033 Em `contas/management/commands/seed_dev.py`, importar `docs/CSVs/fornecedores.csv` pelo
  mesmo `confirmar_importacao` quando o arquivo existir (opção `--fornecedores CAMINHO`); se
  ausente, emitir aviso e seguir sem falhar; atualizar `tests/test_seed_dev.py` e
  `docs/development/seed-dev.md`
- [ ] T034 (coordenador) Rodar `make verify` e o roteiro de `quickstart.md`, inclusive §1 com o
  arquivo real
- [ ] T035 (coordenador) Acionar o `code-reviewer` com o escopo da feature e esta spec; tratar
  P0/P1
- [ ] T036 (coordenador) Gate visual: `impeccable critique` nas telas de `fornecedores` depois do
  `code-reviewer`; `impeccable document` só se surgir padrão novo no `DESIGN.md`
- [ ] T037 (coordenador) `/speckit-converge`; depois do merge, atualizar o status de `FOR` no
  `ROADMAP.md` para concluída e registrar que a dependência `FOR → ENT` foi satisfeita

---

## Dependencies & Execution Order

- Setup (T001–T003) → Foundational (T004–T006) → US1 (T007–T019) → US2, US3 e US4.
- US2 depende só da Foundational e de haver fornecedores (fixtures criadas por
  `confirmar_importacao`); pode andar em paralelo com a US1 depois de T014.
- US3 depende da US1 (execuções); US4 depende da US1 (plano e efetivação).
- Polish depois das stories desejadas.
- Dentro de cada story: testes → leitura/domínio → forms/views → templates.

## Parallel Opportunities

- T002 e T003; T006 com T005 pronto; na US1, T007–T012 juntos, depois T016 em paralelo com T013–T015.
- US2 (T020–T024) em paralelo com a US3 (T025–T027) depois da US1.
- T031 e T032 em paralelo.

## Implementation Strategy

1. **MVP**: Setup + Foundational + US1 — o cadastro fica importável, e a spec 003 já pode usar
   `Fornecedor`.
2. US2 (consulta), depois US3 (auditoria) e US4 (reimportação).
3. Polish, review, gate visual, converge.
