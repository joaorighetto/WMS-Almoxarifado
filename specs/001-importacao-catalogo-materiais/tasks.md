---

description: "Task list for implementing 001-importacao-catalogo-materiais"
---

# Tasks: Importação Inicial e Consulta do Catálogo de Materiais

**Input**: Design documents from `specs/001-importacao-catalogo-materiais/` (`spec.md`, `plan.md`,
`research.md`, `data-model.md`, `contracts/arquivo-scpi.md`, `contracts/rotas-e-autorizacao.md`,
`contracts/interface-importacao.md`, `quickstart.md`)

**Interface interna**: testes e implementação de `leitura_scpi`/`importacao` seguem as assinaturas
fixadas em `contracts/interface-importacao.md` (acrescentado antes da US1, para os testes escritos
primeiro não dependerem de nomes inventados).

**Prerequisites**: `plan.md` (Constitution Check PASS), `spec.md` (4 user stories, P1–P4),
`research.md` (R1–R16; interpretações I-1..I-6 confirmadas em 2026-09-21).

**Tests**: obrigatórios. A Constitution (Princípio VII) exige testes proporcionais ao risco, e esta
feature toca estoque, permissões, transações e concorrência. Em cada story, os testes vêm antes
da implementação e devem falhar primeiro.

**Organization**: por user story, na ordem de prioridade da spec. O modelo de dados inteiro fica
na fase Foundational: é uma única migração aditiva e US1, US3 e US4 compartilham as mesmas tabelas.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: paralelizável (arquivo diferente, sem dependência de task incompleta)
- **[Story]**: US1–US4; ausente em Setup, Foundational e Polish
- **Executor** (orquestração, `.claude/rules/agent-orchestration.md`): sem marca → `task-implementer`;
  **(test-engineer)** → tarefa só de testes; **(frontend-implementer)** → frontend significativo
  com a skill `frontend-design`, dentro do `DESIGN.md`; **(coordenador)** → etapa do Claude
  principal (gates, skills, roadmap)
- **Aplica / Preserva**: IDs canônicos de `docs/domain/permissions-matrix.md` e
  `docs/domain/invariants-matrix.md` que a task implementa ou não pode quebrar

## Path Conventions

Projeto Django monolítico, apps na raiz (`contas/`, novo `catalogo/`), testes em `tests/` (sem
subpasta por app), primitivos CSS em `static/css/components.css`.

## Escopo — limite para todas as tasks (ROADMAP, linha 001, "Não inclui")

Nenhuma task pode introduzir: criação, edição ou exclusão manual de material; observação interna ou
inativação (`MAT`); ajuste ou correção de saldo (`INV`); movimentações, entrada, saída ou histórico
de movimentos (`ENT`/`HIS`); integração automática com o SCPI; normalização de unidade;
classificação local; locais de estoque; armazenamento de colunas fora de escopo (`VAUN1`,
`PRECOMEDIO`, `QUANMIN`, `QUANMAX`, `CODREDUZ`, `CODBARRA`, `NOCULTAR`, `USUARIO`, `DTAINSERE`,
`USUALT`, `DTAALT`, `LOCALFISICO`). Se uma task parecer exigir isso, o implementador **para e
reporta** ao coordenador.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: esqueleto do app, configuração e insumos de teste. Sem regra de domínio.

- [X] T001 Criar o app `catalogo` na raiz (`catalogo/__init__.py`, `catalogo/apps.py` com
  `CatalogoConfig`, `catalogo/urls.py` com `app_name = "catalogo"` e `urlpatterns = []`,
  `catalogo/migrations/__init__.py`); em `config/settings/base.py` acrescentar
  `"django.contrib.postgres"` e `"catalogo"` a `INSTALLED_APPS`; em `config/urls.py` acrescentar
  `path("catalogo/", include("catalogo.urls"))`.
- [X] T002 [P] Configurar `LOGGING` em `config/settings/base.py` com o logger `catalogo.importacao`
  em nível `INFO` para `console` (handler `StreamHandler`), sem alterar o comportamento dos demais
  loggers do Django (`disable_existing_loggers: False`) — research R13.
- [X] T003 [P] Versionar HTMX 2.x em `static/vendor/htmx/htmx-<versão>.min.js` com o arquivo
  `static/vendor/htmx/LICENSE`. Baixar a versão estável mais recente da linha 2.x, conferir a
  integridade do arquivo contra a publicação oficial e registrar a versão no nome do arquivo.
  Nenhum CDN e nenhum pacote Python (research R16).
- [X] T004 [P] (test-engineer) Criar fixtures sintéticas em bytes exatos em
  `tests/fixtures/catalogo/`, com UTF-8 com BOM, CRLF, `;` final e o cabeçalho real de 21 colunas
  na ordem de `research.md` ("Evidência usada"), sem copiar nenhum dado do arquivo real:
  `carga_inicial_valida.csv` (registros íntegros, incluindo `000.000.002`, saldo `0,000`,
  `DISCR1` vazio, descrições iguais com códigos distintos, unidades `UN`/`UND`/`M`/`MT`/`MTS`,
  classificação preenchida e vazia, `004.001.002` com `DISC1` em três linhas físicas, continuação
  em `DISCR1`, `COTOVELO GALVANIZADO ¾" X 90º`, `000.029.742` com `53,4000000000001`, `1.234,5`);
  `carga_inicial_casos_spec.csv` (os válidos acima, mais um registro para cada motivo de recusa de
  `contracts/arquivo-scpi.md` §3, incluindo `CADPRO` duplicado em duas linhas e continuação no fim
  do arquivo); `reimportacao.csv` (mesmos códigos, com descrição alterada, saldo diferente, um
  código novo e um código omitido); `sem_coluna_obrigatoria.csv`; `cadpro_nao_primeira_coluna.csv`;
  `codificacao_invalida.csv`; `somente_cabecalho.csv`; `vazio.csv` (0 bytes). Documentar em
  `tests/fixtures/catalogo/README.md` o caso coberto por cada linha.
- [X] T005 [P] (test-engineer) Em `tests/conftest.py`, acrescentar: a factory `criar_usuario_com_papeis(*papeis)`,
  que cria o usuário por `create_user` (já com `ROLE-REQUESTER`) e concede cada papel extra por
  `PapelUsuario.objects.create`; os fixtures `chefe_almoxarifado` (`ROLE-WAREHOUSE-STAFF`,
  `ROLE-SECTOR-HEAD`, `ROLE-WAREHOUSE-HEAD`), `funcionario_almoxarifado`, `requisitante`,
  `auditor`, `admin_sistema` e `superusuario_tecnico` (`create_superuser`, sem papéis); e o fixture
  `csv_fixture(nome) -> bytes`, que lê `tests/fixtures/catalogo/`. Não alterar os fixtures
  existentes.

**Checkpoint**: `./scripts/verify.sh` passa com o app vazio registrado.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: modelo de dados completo, constraints de banco, normalização de busca e o mixin de
autorização. Tudo que as quatro stories usam.

**⚠️ CRITICAL**: nenhuma story começa antes desta fase.

- [X] T006 (coordenador) Antes de implementar, acionar o `test-engineer` com `plan.md` → "Testes",
  `contracts/` e as invariantes CRÍTICAS aplicáveis (`INV-CATALOG-001/002/003`,
  `INV-STOCK-001/002/004`, `INV-MOV-002`, `INV-AUTH-001`) para revisar e completar os cenários das
  fases seguintes. Achados que mudem requisito voltam ao coordenador; não são incorporados em
  silêncio.
- [X] T007 Criar a migração `catalogo/migrations/0001_pg_trgm.py` só com
  `django.contrib.postgres.operations.TrigramExtension()` (research R15).
- [X] T008 Criar `Material` em `catalogo/models.py` conforme `data-model.md`:
  `cadpro = CharField(max_length=11, editable=False)` com `UniqueConstraint` e `CheckConstraint`
  `cadpro ~ '^[0-9]{3}\.[0-9]{3}\.[0-9]{3}$'` (usar `Q(cadpro__regex=...)`); `descricao`,
  `descricao_busca`, `unidade` como `TextField()`; `detalhamento`, `grupo`, `subgrupo`,
  `nome_grupo`, `nome_subgrupo` como `TextField(blank=True)`; `saldo` e `saldo_inicial` como
  `DecimalField(max_digits=15, decimal_places=3)`, cada um com `CHECK >= 0` e `saldo_inicial`
  `editable=False`; `execucao_origem = ForeignKey("catalogo.ExecucaoImportacao",
  on_delete=PROTECT, editable=False)`; `GinIndex(fields=["descricao_busca"],
  opclasses=["gin_trgm_ops"])`; `Meta.ordering = ["cadpro"]`; e a constante
  `CAMPOS_CADASTRAIS_ATUALIZAVEIS = ("descricao", "unidade", "detalhamento", "grupo", "subgrupo",
  "nome_grupo", "nome_subgrupo")`. **Nenhum** método de criação manual. Aplica/Preserva:
  `INV-CATALOG-001`, `INV-CATALOG-002`, `INV-STOCK-001`, `INV-MOV-002`.
- [X] T009 Criar em `catalogo/models.py`: `MotivoRecusa(TextChoices)`, com os 11 códigos de
  `data-model.md` e rótulos em pt-BR; `ExecucaoImportacao` (`token_previa = UUIDField(unique=True)`;
  `executada_por` FK `contas.User` `PROTECT`; `concluida_em = DateTimeField()`;
  `nome_arquivo = CharField(max_length=255)`; `tamanho_arquivo = PositiveBigIntegerField()`;
  `sha256_arquivo = CharField(max_length=64)`; `total_recebidos`, `total_inseridos`,
  `total_atualizados`, `total_atualizados_com_alteracao`, `total_rejeitados`, `total_divergencias`,
  `total_ausentes_no_arquivo` como `PositiveIntegerField()`; `CHECK total_recebidos =
  total_inseridos + total_atualizados + total_rejeitados`; `CHECK total_atualizados_com_alteracao
  <= total_atualizados`; `ordering = ["-concluida_em"]`); e `ExcecaoImportacao` (FK `execucao`
  `PROTECT`, `related_name="excecoes"`; `linha_inicial`, `linha_final` `PositiveIntegerField` com
  `CHECK linha_final >= linha_inicial`; `cadpro = TextField(blank=True)`; `motivo =
  CharField(choices=MotivoRecusa)`; `detalhe = TextField(blank=True)`; `ordering =
  ["linha_inicial"]`). Preserva: FR-033–FR-037.
- [X] T010 Criar em `catalogo/models.py`: `CampoCadastral(TextChoices)` com os 7 campos de
  `CAMPOS_CADASTRAIS_ATUALIZAVEIS`; `DivergenciaSaldo` (FK `execucao` `PROTECT`,
  `related_name="divergencias"`; FK `material` `PROTECT`; `saldo_wms`, `saldo_arquivo`
  `DecimalField(15, 3)`; `diferenca = DecimalField(max_digits=16, decimal_places=3)`;
  `CHECK diferenca = saldo_arquivo - saldo_wms`; `CHECK diferenca <> 0`;
  `UNIQUE(execucao, material)`; `ordering = ["material__cadpro"]`); e
  `AlteracaoCadastralMaterial` (FK `execucao` `PROTECT`, `related_name="alteracoes"`; FK `material`
  `PROTECT`; `campo = CharField(choices=CampoCadastral)`; `valor_anterior`, `valor_novo`
  `TextField(blank=True)`; `UNIQUE(execucao, material, campo)`; `CHECK valor_anterior <>
  valor_novo`). Preserva: `INV-STOCK-003`, FR-032.
- [X] T011 Gerar `catalogo/migrations/0002_initial.py` (dependente de `0001_pg_trgm`) com
  `makemigrations`, revisar que ela é só aditiva (Constitution XIII) e aplicar localmente. Não
  registrar nenhum modelo em `catalogo/admin.py`: o arquivo não é criado.
- [X] T012 [P] Implementar `normalizar_para_busca(texto: str) -> str` em `catalogo/leitura_scpi.py`:
  `unicodedata.normalize("NFKD")`, remoção dos caracteres de categoria `Mn` e `casefold()`. Mesma
  função para gravar `descricao_busca` e para o termo digitado (research R15).
- [X] T013 [P] Implementar `ExigePapelMixin(LoginRequiredMixin, UserPassesTestMixin)` em
  `catalogo/views.py`, com o atributo de classe `papel_exigido` e `test_func` retornando
  `self.request.user.tem_papel(self.papel_exigido)`. Sem herança de papéis e sem exceção para
  superusuário (research R12). Aplica: base de `PERM-MATERIAL-VIEW`, `PERM-SCPI-IMPORT-EXECUTE` e
  `PERM-SCPI-IMPORT-HISTORY-VIEW`.
- [X] T014 [P] (test-engineer) Escrever `tests/test_catalogo_modelos.py`: `IntegrityError` para
  `cadpro` duplicado; `cadpro` fora do formato (`2`, `000.000.2`, ` 000.000.002`, com dígito
  Unicode); `saldo < 0`; `saldo_inicial < 0`; totais em que `recebidos ≠ inseridos + atualizados +
  rejeitados`; `diferenca ≠ saldo_arquivo − saldo_wms`; `diferenca = 0`; `linha_final <
  linha_inicial`. Também: `cadpro` `000.000.002` relido idêntico, e `normalizar_para_busca("Ação
  ÇÃO")` igual a `normalizar_para_busca("acao cao")`. Preserva: `INV-CATALOG-001/002`,
  `INV-STOCK-001`.

**Checkpoint**: migrações aplicadas; `tests/test_catalogo_modelos.py` verde.

---

## Phase 3: User Story 1 - Realizar a carga inicial do catálogo (Priority: P1) 🎯 MVP

**Goal**: o chefe do almoxarifado envia o CSV, vê uma prévia sem persistência e, ao confirmar, os
materiais válidos são criados atomicamente com o saldo inicial do arquivo. Os inválidos aparecem
como exceção e o resultado é exibido na interface.

**Independent Test**: sobre catálogo vazio, enviar `carga_inicial_casos_spec.csv`, conferir que a
prévia não gravou nada, confirmar e verificar que cada material válido existe com código,
descrição, unidade, classificação, detalhamento e saldo idênticos aos do arquivo, e que cada
recusado tem exceção com linha e motivo (US1 cenários 1–12).

### Tests for User Story 1 ⚠️ (escrever primeiro; devem falhar)

- [X] T015 [P] [US1] (test-engineer) Escrever `tests/test_catalogo_leitura_scpi.py` (sem banco):
  todos os exemplos normativos de `contracts/arquivo-scpi.md` §5; BOM não contamina `CADPRO` nem o
  nome da 1ª coluna; coluna vazia final ignorada e, se preenchida, `ESTRUTURA_INCONSISTENTE`; CRLF
  e LF equivalentes; `\u2028` e `\x0c` dentro de texto não quebram registro; `CADPRO` com dígito
  Unicode → `CADPRO_FORMATO_INVALIDO`; ordem dos motivos da §3; todas as ocorrências de código
  duplicado recusadas, inclusive quando uma delas também tem outra falha; linha de continuação
  antes do 1º registro → `LINHA_NAO_ASSOCIAVEL`, com `cadpro` vazio na exceção; linhas físicas de origem corretas em registro
  multilinha; recusas de arquivo da §1 (coluna ausente, lista das faltantes, coluna duplicada,
  `CADPRO` fora da 1ª posição, UTF-8 inválido); `vazio.csv` e `somente_cabecalho.csv` → zero
  registros sem erro. Acrescentados na T006: `-0,0001` → `QUANTIDADE_NEGATIVA`, enquanto `-0` e
  `-0,000` são aceitos como zero; 12 dígitos inteiros aceitos e 13 → `QUANTIDADE_FORA_DO_LIMITE`;
  `1,2,3`, ` ,5` e `1 234` → `QUANTIDADE_NAO_NUMERICA`; cabeçalho com `CADPRO` em 1º e as demais
  colunas obrigatórias em outra ordem (e colunas extras entre elas) → valores lidos pelo **nome**,
  nunca pela posição; coluna **fora de escopo** repetida no cabeçalho → sem efeito; arquivo com
  CRLF e LF misturados; continuação legítima que por acaso tem `N − 1` separadores → os **dois**
  registros envolvidos recusados e contados como dois recebidos; `CADPRO` da exceção
  `ESTRUTURA_INCONSISTENTE` em registro multilinha = 1º campo do registro **recomposto**. Linha
  física vazia (D-1, decidida): entre registros completos e antes do fim do arquivo → ignorada,
  sem contar como recebida; dentro de `DISCR1` multilinha incompleto → preservada no campo; linha
  só com espaços segue a mesma regra; numeração de linhas físicas das exceções seguintes continua
  correta. Usar `@pytest.mark.parametrize` sobre a tabela da §5 e sobre os motivos, sem um teste por
  motivo ou por unidade. Preserva: `INV-CATALOG-001`, `INV-CATALOG-005`, `INV-STOCK-001`.
- [X] T016 [P] [US1] (test-engineer) Escrever `tests/test_catalogo_importacao.py` (banco), chamando
  `calcular_plano`/`aplicar_plano` diretamente sobre catálogo vazio: US1 cenários 1–12; cada
  material com `saldo == saldo_inicial ==` `QUAN3` arredondado e `execucao_origem` = execução
  criada; `descricao_busca` preenchida; valores textuais byte a byte iguais, inclusive `\n` e `"`;
  totais com `recebidos = inseridos + atualizados + rejeitados`; uma `ExcecaoImportacao` por
  recusado, com `linha_inicial`/`linha_final`, `motivo` e `cadpro` quando identificável (US3
  cenários 1–2); colunas fora de escopo não armazenadas; classificação gravada é a do arquivo,
  inclusive quando `GRUPO`/`SUBGRUPO` **não** coincidem com os trios do `CADPRO` e quando vêm
  vazios — nunca derivada do código (FR-022, FR-024); `calcular_plano` chamado duas vezes sobre o
  mesmo estado, com vários materiais e registros, produz `impressao_digital` idêntica (ordenação
  explícita de todas as listas). Preserva: `INV-CATALOG-001/002/003/005`,
  `INV-STOCK-001/002`, `INV-MOV-002`.
- [X] T017 [P] [US1] (test-engineer) Escrever `tests/test_catalogo_atomicidade.py` (com
  `django_db(transaction=True)` onde houver threads): falha injetada em **dois pontos** de
  `aplicar_plano`, cedo (`Material.objects.bulk_create`) e tarde (`ExcecaoImportacao.objects.bulk_create`),
  via `mock.patch.object(<Modelo>.objects, "bulk_create", side_effect=RuntimeError)` → as **cinco**
  tabelas de `catalogo` ficam no estado anterior; outra execução confirmada entre a prévia e a
  confirmação, inserindo um `CADPRO` do arquivo (cenário sequencial, sem threads) → "prévia
  desatualizada"; saldo de um material **fora** do arquivo alterado entre prévia e confirmação →
  confirmação **bem-sucedida** (a impressão digital não depende do catálogo inteiro); duas confirmações concorrentes do mesmo arquivo, com prévias
  calculadas sobre catálogo vazio → exatamente uma execução e a outra recebe "prévia
  desatualizada", sem material duplicado; mesmo `token_previa` confirmado duas vezes, em sequência
  e em duas threads concorrentes (inclusive num arquivo cuja reaplicação não mudaria nada) → uma
  execução, e a segunda recebe "já confirmada". Threads: chamar `confirmar_importacao` direto
  (sem `Client`), `threading.Barrier(2)`, `SET lock_timeout = '5s'` no início de cada thread,
  `connection.close()` em `finally`, `join(timeout=10)` + `assert not t.is_alive()`, exceções
  coletadas por thread (padrão de `tests/test_contas_organizacao.py`). Preserva: `INV-STOCK-004`,
  `INV-CATALOG-002`.
- [X] T018 [P] [US1] (test-engineer) Escrever `tests/test_catalogo_views_importacao.py`: `POST`
  de envio + `GET` de prévia não alteram a contagem de nenhuma tabela de `catalogo` **e**, sob
  `CaptureQueriesContext`, não emitem nenhum `INSERT`/`UPDATE`/`DELETE` em `catalogo_*` nem
  `SELECT ... FOR UPDATE` (FR-044a);
  prévia exibe totais, exceções paginadas e o aviso "nada foi gravado"; recusa de arquivo
  re-renderiza com erro e **não** grava pedido na sessão; arquivo > 10 MB recusado; confirmação
  válida → `302` para `catalogo:execucao_detalhe` e pedido removido da sessão; impressão digital
  adulterada → nada gravado e alerta de prévia desatualizada; cancelamento limpa a sessão; prévia
  sem pedido → `302` para envio; detalhe mostra totais e exceções (FR-044).
- [X] T019 [P] [US1] (test-engineer) Escrever a parte de importação de
  `tests/test_catalogo_permissoes.py`: para `catalogo:importacao_envio` (GET/POST),
  `importacao_previa`, `importacao_confirmar`, `importacao_cancelar` e `execucao_detalhe`,
  anônimo → login; chefe do almoxarifado com sessão ativa **desativado depois do login**
  (`force_login` → `is_active=False` → nova requisição) → login; superusuário técnico,
  requisitante, funcionário do almoxarifado, chefe de setor sem `ROLE-WAREHOUSE-HEAD`, auditor e
  admin de sistema → 403; chefe do almoxarifado → acesso. `POST` de envio negado, com arquivo que
  seria recusado por validação, → 403 **sem** mensagem de validação e sem gravar sessão (o arquivo
  não é validado nem interpretado); sem token CSRF (`Client(enforce_csrf_checks=True)`), POST em
  envio, confirmar e cancelar → 403; GET em confirmar e cancelar → 405. Aplica:
  `PERM-SCPI-IMPORT-EXECUTE`, `PERM-SCPI-IMPORT-HISTORY-VIEW`. Preserva: `INV-AUTH-001`.

### Implementation for User Story 1

- [X] T020 [US1] Implementar a leitura de arquivo em `catalogo/leitura_scpi.py`, conforme
  `contracts/arquivo-scpi.md` §1–§2: `decodificar(bytes) -> str` (`utf-8-sig` estrito); divisão em
  linhas físicas só por `\n`, com remoção de um `\r` final (**nunca** `splitlines()`); leitura e
  validação do cabeçalho (9 obrigatórias, duplicidade, `CADPRO` na 1ª posição, arquivo vazio/só
  cabeçalho); a exceção `ArquivoRecusado(codigo, mensagem)` com os códigos da §1; recomposição
  com as 4 regras de classificação de linha e a regra de linha vazia ignorada (D-1), ambas em
  research R3, e registro das linhas físicas de origem;
  separação por `;` sem tratamento de aspas. Constante `PADRAO_CADPRO =
  re.compile(r"[0-9]{3}\.[0-9]{3}\.[0-9]{3}")`, usada com `fullmatch`. Preserva:
  `INV-CATALOG-001`.
- [X] T021 [US1] Implementar a validação por registro em `catalogo/leitura_scpi.py` (§3): função
  que devolve registros aceitos (`cadpro`, campos cadastrais como lidos, `quantidade: Decimal`) e
  recusados (`linha_inicial`, `linha_final`, `cadpro` identificável — vazio em
  `LINHA_NAO_ASSOCIAVEL` —, `motivo`, `detalhe`), na
  ordem fixa de motivos; duplicidade apurada sobre todos os `CADPRO` bem formados;
  `interpretar_quantidade(texto) -> Decimal` com a gramática de research R6, sem `float`, negativo
  avaliado antes de arredondar, `quantize(Decimal("0.001"), ROUND_HALF_UP)` e limite de 12 dígitos
  inteiros. Nenhum valor textual aparado ou alterado. Preserva: `INV-CATALOG-001`,
  `INV-CATALOG-005`, `INV-STOCK-001`.
- [X] T022 [US1] Implementar `calcular_plano(conteudo: bytes, *, bloquear: bool = False)` em
  `catalogo/importacao.py`: lê e valida via `leitura_scpi`; consulta materiais existentes por
  `cadpro__in` em blocos de 500 (com `select_for_update().order_by("pk")` quando `bloquear=True`);
  classifica cada aceito como **inserção** (novo) ou **atualização** (existente; nesta story sem
  diff de campos e sem divergência — ver T044); produz totais e `impressao_digital` (SHA-256 da
  serialização JSON canônica e ordenada do plano + SHA-256 do arquivo). Só leituras. Preserva:
  FR-044a. Nota: até T044, uma reimportação conta existentes como "atualizados" sem aplicar
  mudança. O checkpoint da US1 é validado só sobre catálogo vazio, e a feature não é mergeada
  antes da US4.
- [X] T023 [US1] Implementar `aplicar_plano(plano, *, usuario, token_previa, nome_arquivo)` e
  `confirmar_importacao(pedido, impressao_digital_enviada, usuario)` em `catalogo/importacao.py`.
  `confirmar_importacao` abre `transaction.atomic()`, executa `SELECT pg_advisory_xact_lock(%s)`
  com uma constante `CHAVE_LOCK_IMPORTACAO_SCPI` e, se já existir `ExecucaoImportacao` com esse
  `token_previa`, levanta `PreviaJaConfirmada` sem gravar nada. Depois recalcula o plano com
  `bloquear=True` e, se a
  impressão digital diferir, levanta `PreviaDesatualizada` sem gravar nada. Senão, cria
  `ExecucaoImportacao` (`concluida_em = timezone.now()`), faz `bulk_create(batch_size=500)` dos
  `Material` novos com `saldo = saldo_inicial = quantidade`, `execucao_origem = execução` e
  `descricao_busca = normalizar_para_busca(descricao)`, e das `ExcecaoImportacao`.
  O `UNIQUE(token_previa)` fica como última defesa. Log `INFO`/`WARNING`/`ERROR` conforme
  research R13, sem conteúdo do arquivo. Aplica: `PERM-SCPI-IMPORT-EXECUTE` (duas etapas).
  Preserva: `INV-STOCK-004`, `INV-CATALOG-002/003`, `INV-STOCK-002`, `INV-MOV-002`,
  `INV-SCPI-001`.
- [X] T024 [US1] Implementar em `catalogo/importacao.py` o pedido de prévia em sessão, com a chave
  `catalogo_importacao_previa`: `guardar_pedido(session, *, nome_arquivo, conteudo)` (`token` UUID4, `nome_arquivo`
  truncado em 255, `tamanho`, `sha256`, conteúdo `zlib` + base64), `obter_pedido(session)` e
  `descartar_pedido(session)`. Um pedido por sessão; um novo envio substitui o anterior (research
  R8).
- [X] T025 [P] [US1] Criar `ArquivoImportacaoForm` em `catalogo/forms.py`: `FileField` obrigatório,
  `clean_arquivo` com limite de 10 MB (`ARQUIVO_TAMANHO_EXCEDIDO`) e chamada a
  `leitura_scpi.decodificar` e à validação de cabeçalho, convertendo `ArquivoRecusado` em
  `ValidationError` com mensagem legível. A extensão do arquivo não é critério.
- [X] T026 [US1] Implementar em `catalogo/views.py` as views de importação, todas com
  `ExigePapelMixin` e `papel_exigido = Papel.CHEFE_ALMOXARIFADO`, conforme
  `contracts/rotas-e-autorizacao.md`: `ImportacaoEnvioView` (GET/POST; PRG para a prévia),
  `ImportacaoPreviaView` (GET; recalcula o plano; pagina exceções por `pagina_excecoes`, 50 por
  página; entrega `token` e `impressao_digital` ao template), `ImportacaoConfirmarView` (POST;
  respostas exatamente como na tabela de `contracts/rotas-e-autorizacao.md`: token
  ausente/divergente, `PreviaJaConfirmada` → detalhe, `PreviaDesatualizada` → prévia com alerta,
  erro inesperado → 200 na prévia com alerta genérico, pedido mantido na sessão), `ImportacaoCancelarView` (POST) e
  `ExecucaoDetalheView` (GET; `get_object_or_404`; seção de exceções paginada; `select_related`
  de `executada_por`). A autorização vem **antes** de validar ou interpretar o arquivo: o
  mixin roda antes da view tocar `request.FILES`. O `CsrfViewMiddleware` pode já ter recebido o
  upload para ler o token. Registrar as rotas
  em `catalogo/urls.py`. Aplica: `PERM-SCPI-IMPORT-EXECUTE`, `PERM-SCPI-IMPORT-HISTORY-VIEW`.
  Preserva: `INV-AUTH-001`.
- [X] T027 [US1] Em `contas/views.py`, fazer `HomeView.get_context_data` incluir
  `pode_importar_catalogo = user.tem_papel(Papel.CHEFE_ALMOXARIFADO)`, e em
  `contas/templates/contas/home.html` mostrar os links "Importar catálogo" e "Histórico de
  importações" quando a flag for verdadeira. O link é conveniência, não autorização. A rota
  `catalogo:historico` só existe a partir de T038, por isso nesta task se exibe só "Importar
  catálogo"; o link de histórico entra em T039.
- [X] T028 [US1] (frontend-implementer) Criar os primitivos compartilhados em
  `static/css/components.css` segundo `DESIGN.md` → Components: **Page Header**, **File Upload**
  (mostra nome e tamanho do arquivo antes de enviar), **Table** (densidade compacta no desktop,
  números à direita com `tabular-nums`, `CADPRO` monoespaçado, empty state como linha única, linha
  de erro com `border-strong` lateral + texto), **Status/Badge** (sempre com texto),
  **Pagination** e **Empty State**. Reutilizar `Buttons`, `Alert` e `Inputs` existentes, e só
  tokens de `static/css/tokens.css`.
- [X] T029 [US1] (frontend-implementer) Criar `catalogo/templates/catalogo/importacao_envio.html`,
  `importacao_previa.html` e `execucao_detalhe.html` (estendendo `contas/base.html`), com
  composição em `catalogo/static/catalogo/css/catalogo.css`. A prévia é desktop-first e densa,
  separada por estrutura e divisores, nunca por cards empilhados: totais esperados; tabela de
  exceções com linha, `CADPRO` como recebido e motivo; aviso explícito "nada foi gravado ainda";
  botão primário que reitera o resultado ("Confirmar importação: N inseridos, M atualizados") e
  ação secundária "Cancelar". O detalhe mostra quem, quando, arquivo (nome, tamanho, SHA-256),
  totais e exceções paginadas. Erros e exceções nunca desaparecem sozinhos. O `CADPRO` é exibido
  sem nenhuma transformação. Sem regra de negócio no template: dados prontos da view. Estado de
  processamento (Constitution VIII) nos formulários de envio e confirmação via
  `catalogo/static/catalogo/js/envio.js`, seguindo o padrão de `contas/static/contas/js/login.js`
  (botão desabilitado, rótulo "Processando…", `aria-busy`, reset no `pageshow`) por atributos
  `data-*`. O fluxo funciona sem JS.

**Checkpoint**: MVP. A carga inicial funciona de ponta a ponta pela interface; T015–T019 verdes.

---

## Phase 4: User Story 2 - Consultar o catálogo de materiais (Priority: P2)

**Goal**: qualquer identidade de negócio localiza material por `CADPRO` exato ou palavras da
descrição, com paginação e estados explícitos.

**Independent Test**: com materiais criados (por `aplicar_plano` ou fixture de banco), buscar
`000.000.002` e palavras da descrição sem acento/caixa; conferir dados exibidos, paginação, estado
vazio e fragmento HTMX (US2 cenários 1–4).

### Tests for User Story 2 ⚠️

- [X] T030 [P] [US2] (test-engineer) Escrever `tests/test_catalogo_consulta.py`: código exato
  retorna um material com código, descrição, unidade, classificação (identificada como SCPI),
  saldo e detalhamento (FR-041, FR-023); código com espaços nas bordas é aparado só na entrada;
  código parcial ou fora do formato (`2`, `000.000`) → estado de validação e **nenhuma** consulta
  (`django_assert_num_queries`); descrição em minúsculas e sem acento encontra a acentuada
  (FR-040); **emenda 2026-09-21**: palavras soltas, em qualquer ordem e parciais, encontram o
  material, e basta uma palavra ausente para não encontrar; descrições iguais aparecem como materiais distintos; paginação de 50 com
  `pagina` inválida tratada; ausência de resultados com estado explícito (FR-043); com
  `HX-Request: true` a resposta é só o fragmento; sem filtro, lista ordenada por `cadpro`; número
  de queries constante por página (sem N+1).
- [X] T031 [P] [US2] (test-engineer) Acrescentar a `tests/test_catalogo_permissoes.py` a rota
  `catalogo:consulta`: anônimo → login; requisitante desativado depois do login (como em T019) →
  login; superusuário técnico → 403; requisitante,
  funcionário, chefe de setor, auditor, admin de sistema e chefe do almoxarifado (todos com
  `ROLE-REQUESTER`) → 200. Aplica: `PERM-MATERIAL-VIEW`. Preserva: `INV-AUTH-001`.

### Implementation for User Story 2

- [X] T032 [P] [US2] Criar `ConsultaCatalogoForm` em `catalogo/forms.py`, com `codigo` e `descricao`
  opcionais. `clean_codigo` apara as bordas e, se preenchido e fora de
  `PADRAO_CADPRO.fullmatch`, gera erro "Informe o código completo no formato XXX.YYY.ZZZ". Nunca
  completar, preencher zeros ou tratar como prefixo (FR-039, `INV-CATALOG-001`).
- [X] T033 [US2] Implementar `ConsultaCatalogoView` em `catalogo/views.py` (`ExigePapelMixin`,
  `papel_exigido = Papel.REQUISITANTE`): form inválido → sem consulta; `codigo` → `cadpro=` exato;
  `descricao` → `descricao_busca__contains=normalizar_para_busca(termo)` (**emenda 2026-09-21,
  FR-040**: o termo normalizado é separado por `split()` e cada palavra vira um `__contains`
  combinado por E); os dois filtros
  combinados por interseção; `.only(...)` dos campos exibidos; `Paginator(50).get_page`; template
  de fragmento quando `request.headers.get("HX-Request")`. Registrar `catalogo:consulta` em
  `catalogo/urls.py`. Aplica: `PERM-MATERIAL-VIEW`.
- [X] T034 [US2] Em `contas/views.py`/`contas/templates/contas/home.html`, acrescentar
  `pode_consultar_catalogo = user.tem_papel(Papel.REQUISITANTE)` e o link "Catálogo de materiais".
- [X] T035 [US2] (frontend-implementer) Criar os primitivos **Filter Bar** e **Loading Indicator**
  (local à região atualizada) em `static/css/components.css`. Criar
  `catalogo/templates/catalogo/consulta.html` e `_resultados_consulta.html`, incluindo o script
  HTMX de `static/vendor/htmx/` só nesta página. O formulário GET funciona sem JS e, com HTMX,
  usa `hx-get` na região de resultados, `hx-push-url` e `hx-indicator`. Falha de rede ou 5xx aparece
  em alerta na região via `hx-on`, sem arquivo JS próprio. A tabela preserva todas as colunas, com
  scroll horizontal antes de ocultar; detalhamento longo truncado com forma previsível de ver o
  valor completo; classificação rotulada como origem SCPI; usável em celular sem virar card
  automaticamente (`DESIGN.md` → Layout, Tabelas).

**Checkpoint**: US1 e US2 funcionam de forma independente.

---

## Phase 5: User Story 3 - Auditar o resultado da importação (Priority: P3)

**Goal**: o chefe do almoxarifado consulta o histórico de execuções e o resultado de cada uma
(quem, quando, arquivo, totais, exceções), preservado entre execuções.

**Independent Test**: confirmar duas importações, uma com erros propositais; conferir no histórico
as duas execuções, na ordem correta, e que o resultado da primeira continua intacto depois da
segunda (US3 cenários 1–3).

### Tests for User Story 3 ⚠️

- [X] T036 [P] [US3] (test-engineer) Escrever `tests/test_catalogo_historico.py`: histórico lista
  execuções da mais recente para a mais antiga, com matrícula, momento, arquivo e totais;
  paginação de 20; estado vazio sem execuções; detalhe da primeira execução é idêntico antes e
  depois de uma segunda importação (FR-037); exceção com linha, motivo e `CADPRO` identificável
  (FR-036); `pk` inexistente → 404; queries constantes por página (`select_related`).
- [X] T037 [P] [US3] (test-engineer) Acrescentar a `tests/test_catalogo_permissoes.py` a rota
  `catalogo:historico`, com a mesma matriz de T019. Aplica: `PERM-SCPI-IMPORT-HISTORY-VIEW`.

### Implementation for User Story 3

- [X] T038 [US3] Implementar `HistoricoImportacoesView` (`ListView`) em `catalogo/views.py`, com
  `ExigePapelMixin(Papel.CHEFE_ALMOXARIFADO)`, `select_related("executada_por")`, `paginate_by =
  20` e ordenação `-concluida_em`. Registrar `catalogo:historico` em `catalogo/urls.py`. Aplica:
  `PERM-SCPI-IMPORT-HISTORY-VIEW`.
- [X] T039 [US3] Ativar em `contas/templates/contas/home.html` o link "Histórico de importações"
  (mesma flag `pode_importar_catalogo` de T027).
- [X] T040 [US3] (frontend-implementer) Criar `catalogo/templates/catalogo/historico.html` com
  Page Header, Table, Pagination e Empty State já existentes. Cada linha leva ao detalhe da
  execução.

**Checkpoint**: US1–US3 funcionam; o resultado de toda execução confirmada é consultável depois.

---

## Phase 6: User Story 4 - Reconciliar o catálogo com o SCPI (Priority: P4)

**Goal**: a reimportação atualiza só os dados cadastrais do SCPI, registra cada alteração,
aponta divergências de saldo sem alterar saldo e informa quantos materiais estão ausentes do
arquivo.

**Independent Test**: com o catálogo carregado e um saldo alterado (simulando movimentação),
reimportar `reimportacao.csv` e verificar cadastros atualizados, saldo intacto, divergência
listada com os dois valores e a diferença, e contagem de ausentes (US4 cenários 1–5).

### Tests for User Story 4 ⚠️

- [X] T041 [P] [US4] (test-engineer) Escrever `tests/test_catalogo_reimportacao.py`: US4 cenários
  1–5; saldo nunca alterado pela reimportação, inclusive de material nunca movimentado e com
  divergência (SC-009); `saldo_inicial`, `execucao_origem` e `cadpro` inalterados; divergência só
  para existente com diferença, com `diferenca = saldo_arquivo − saldo_wms` e sinal correto;
  material novo não gera divergência; recusado não gera divergência nem atualização; mesmo
  arquivo reimportado → `total_atualizados_com_alteracao = 0`, nenhuma `AlteracaoCadastralMaterial`,
  0 divergências e nenhum dado alterado; uma `AlteracaoCadastralMaterial` por campo alterado,
  com valor anterior e novo exatos; `descricao_busca` atualizada junto com `descricao`; ausentes =
  materiais cujo `CADPRO` bem formado não aparece no arquivo, nenhum alterado ou excluído;
  existente cuja **única** diferença é o saldo → conta em `total_atualizados`, **não** em
  `total_atualizados_com_alteracao`, sem `AlteracaoCadastralMaterial` e com a divergência
  registrada; um único teste altera os 7 campos cadastrais e confere 7 alterações; divergência
  persistente reaparece em cada execução, ligada à sua (FR-030). Preserva: `INV-STOCK-002`,
  `INV-STOCK-003`, `INV-CATALOG-004`, `INV-MOV-002`.
- [X] T042 [P] [US4] (test-engineer) Acrescentar a `tests/test_catalogo_atomicidade.py`: prévia
  calculada, saldo de um material alterado antes da confirmação → confirmação recusada como
  "prévia desatualizada", nada gravado e nova prévia com a divergência atualizada; falha injetada
  no `bulk_create` de divergências durante uma reimportação → nenhuma atualização cadastral,
  alteração, divergência ou execução persiste, e os campos cadastrais e o `saldo` dos materiais
  existentes, relidos do banco, continuam com os valores anteriores (rollback do `bulk_update`).
  Preserva: `INV-STOCK-004`.
- [X] T043 [P] [US4] (test-engineer) Acrescentar a `tests/test_catalogo_views_importacao.py`:
  prévia de reimportação mostra divergências paginadas (`pagina_divergencias`), atualizados (com e
  sem alteração) e ausentes, sem gravar nada; o detalhe da execução mostra divergências e
  alterações cadastrais paginadas.

### Implementation for User Story 4

- [X] T044 [US4] Estender `calcular_plano` em `catalogo/importacao.py`: para cada atualização,
  diff dos `CAMPOS_CADASTRAIS_ATUALIZAVEIS` (comparação exata de texto) e divergência quando
  `quantidade ≠ material.saldo`; `total_atualizados_com_alteracao`; `total_ausentes_no_arquivo` =
  materiais do catálogo cujo `CADPRO` não está entre os `CADPRO` bem formados do arquivo, aceitos
  ou recusados (por contagem no banco, sem carregar o catálogo); incluir diffs, divergências e
  ausentes na serialização da impressão digital. Só leituras. Preserva: `INV-STOCK-003`.
- [X] T045 [US4] Estender `aplicar_plano` em `catalogo/importacao.py`: `bulk_update(materiais,
  fields=[*campos alterados, "descricao_busca"], batch_size=500)`, só para materiais com mudança,
  e **nunca** com `saldo`, `saldo_inicial`, `cadpro` ou `execucao_origem` na lista (garantir com
  asserção explícita contra a lista fechada de campos); `bulk_create` de
  `AlteracaoCadastralMaterial` e `DivergenciaSaldo`; gravar `total_atualizados_com_alteracao`,
  `total_divergencias` e `total_ausentes_no_arquivo` na execução. Tudo dentro da mesma transação
  de T023. Preserva: `INV-STOCK-002`, `INV-STOCK-003`, `INV-STOCK-004`, `INV-CATALOG-004`.
- [X] T046 [US4] Em `catalogo/views.py`, acrescentar à `ImportacaoPreviaView` a paginação de
  divergências (`pagina_divergencias`) e à `ExecucaoDetalheView` as seções paginadas de
  divergências e alterações cadastrais, com `select_related("material")` (FR-030, FR-032).
- [X] T047 [US4] (frontend-implementer) Em `importacao_previa.html` e `execucao_detalhe.html`,
  acrescentar: seção de divergências (`CADPRO`, saldo WMS, saldo no arquivo, diferença, com a
  convenção de sinal explicada e Badge "Divergência" com texto); totais "atualizados (N com
  alteração)" e "ausentes do arquivo"; no detalhe, seção de alterações cadastrais (`CADPRO`,
  campo, valor anterior, valor novo); cada seção com empty state próprio. Deixar explícito que a
  divergência é informativa e que o ajuste não acontece aqui (FR-047). Nenhuma ação de ajuste é
  oferecida.
  **Nota (T059, 2026-09-22):** o Badge "Divergência" por linha foi dispensado pela revisão visual
  aprovada em T052. Com toda linha da seção marcada, a ênfase se anulava e contradizia a nota de
  que a divergência é informativa; o sinal da diferença, com peso tipográfico, passou a ser o
  diferenciador, e `table-row-error` ficou reservado às exceções.

**Checkpoint**: todas as stories funcionam de forma independente; a reimportação preserva saldo.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T048 [P] (test-engineer) Escrever `tests/test_catalogo_sem_criacao_manual.py` (SC-005,
  FR-006): nenhum modelo de `catalogo` registrado em `django.contrib.admin.site`; entre as rotas
  de `catalogo`, só `importacao_envio`, `importacao_confirmar` e `importacao_cancelar` aceitam
  POST, e nenhuma rota aceita PUT, PATCH ou DELETE (o 405 das rotas só-POST está em T019); `Material` só é criado pelo caminho de
  `aplicar_plano` (busca estática por `Material(`/`Material.objects.create`/`bulk_create` fora de
  `catalogo/importacao.py` e de `tests/`). Preserva: `INV-CATALOG-003`, `INV-CATALOG-004`.
- [X] T049 [P] (test-engineer) Escrever `tests/test_catalogo_arquivo_real.py`, que roda só com a
  variável `SCPI_CSV_REAL` e, sem ela, é *skipped* com o motivo "arquivo real do SCPI não
  disponível (aceite pendente — ROADMAP, Evidências de importação)". Com o arquivo, verifica o
  resultado esperado de `quickstart.md` §5 (1588 recebidos/inseridos, 0 rejeitados, `CADPRO`
  idênticos, `004.001.002` recomposto, `000.029.742` = `53.400`, saldo = `QUAN3` na escala de 3
  casas, reimportação imediata sem alteração nem divergência). Nenhum dado real é versionado.
- [X] T050 Rodar `./scripts/verify.sh` (lock, ruff, check, check --deploy, makemigrations --check,
  pytest) e corrigir o que falhar dentro do escopo.
- [X] T051 (coordenador) Acionar o `code-reviewer` sobre o diff completo da feature com spec, plan,
  contratos, IDs `PERM-*`/`INV-*` aplicáveis e o "Não inclui" do ROADMAP. Tratar P0/P1 antes de
  seguir (ciclo de no máximo duas rodadas).
- [X] T052 (coordenador) Gate visual obrigatório: `impeccable critique` das telas de consulta,
  envio/prévia, detalhe e histórico. Encaminhar os findings aprovados ao `frontend-implementer`
  (com 3+ Priority Issues, perguntar ao usuário antes).
- [X] T053 (coordenador) `impeccable document` (modo scan) para registrar em `DESIGN.md` e em
  `.impeccable/design.json` os componentes que passaram a existir (Table, Pagination, Filter Bar,
  Empty State, Loading Indicator, File Upload, Page Header, Status/Badge). Só mudanças duráveis
  do sistema.
- [X] T054 (coordenador) Executar o roteiro manual de `quickstart.md` §3–§4 e, se o arquivo real
  estiver disponível no ambiente, §5 (aceite de SC-001, SC-002, SC-004, SC-008). Registrar o
  resultado ou a pendência.
  **Resultado (2026-09-22):** §3–§4 executados no navegador (Chromium/Playwright, login pelo
  formulário real) num banco descartável `wms_quickstart`, com os usuários de §1: 25/25 passos
  conferidos, incluindo catálogo vazio durante a prévia, reenvio do POST sem segunda execução,
  403 do requisitante, busca sem JavaScript e reimportação com saldo 8 preservado (divergência
  8 / 15 / +7). §5 com o arquivo real: `tests/test_catalogo_arquivo_real.py` passa com
  `SCPI_CSV_REAL` (1588 recebidos e inseridos, reimportação sem alteração nem divergência) —
  evidência técnica para SC-001, SC-002, SC-004 e SC-008. Achado durante o roteiro e corrigido:
  o título "Alterações cadastrais (N)" do detalhe contava materiais, não as linhas listadas.
- [X] T055 (coordenador) Executar `/speckit-converge`; encaminhar tasks restantes ao implementador
  apropriado e repetir review/converge só enquanto houver trabalho concreto.
- [X] T056 (coordenador) Depois do merge em `main`, atualizar o status da 001 no `ROADMAP.md`
  para concluída, com a pendência de aceite do arquivo real se ainda existir, e registrar que a
  dependência `001` de `ENT`, `REQ`, `SAE`, `INV` e `MAT` foi satisfeita. É um commit posterior à
  entrega, só por pedido explícito do usuário.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001–T005)**: sem dependências. T002–T005 em paralelo depois de T001.
- **Foundational (T006–T014)**: depois do Setup. T007 → T008–T010 → T011. T012 e T013 em paralelo a
  qualquer momento da fase. T014 depois de T011 e T012. **Bloqueia todas as stories.**
- **US1 (T015–T029)**: depois da Foundational. Testes T015–T019 em paralelo, antes da
  implementação. T020 → T021 → T022 → T023; T024 e T025 em paralelo a T022/T023; T026 depois de
  T023–T025; T027 depois de T026; T028 em paralelo ao backend; T029 depois de T026 e T028.
- **US2 (T030–T035)**: depende só da Foundational (materiais podem ser criados diretamente nos
  testes) e pode andar em paralelo à US1. Na prática, T034 e T027 editam os mesmos arquivos da
  Home e devem ser serializadas. T035 reutiliza os primitivos de T028.
- **US3 (T036–T040)**: depende de US1 (execuções só existem via confirmação; o detalhe é de T026).
- **US4 (T041–T047)**: depende de US1 (T022/T023 são estendidos por T044/T045). T046/T047 dependem
  de T026/T029. Independente de US2 e US3.
- **Polish (T048–T056)**: depois das stories desejadas. T050 → T051 → T052 → T053 → T054 → T055;
  T056 só depois do merge.

### Arquivos compartilhados (não paralelizar escritas)

`catalogo/models.py` (T008–T010), `catalogo/leitura_scpi.py` (T012, T020, T021),
`catalogo/importacao.py` (T022–T024, T044, T045), `catalogo/views.py` (T013, T026, T033, T038, T046),
`catalogo/forms.py` (T025, T032), `catalogo/urls.py`, `contas/views.py` + `home.html` (T027, T034,
T039), `static/css/components.css` (T028, T035), `tests/test_catalogo_permissoes.py` (T019, T031,
T037), `tests/test_catalogo_atomicidade.py` (T017, T042), `tests/test_catalogo_views_importacao.py`
(T018, T043).

## Parallel Example: User Story 1

```text
# Testes (test-engineer), em paralelo — arquivos distintos:
T015 tests/test_catalogo_leitura_scpi.py
T016 tests/test_catalogo_importacao.py
T017 tests/test_catalogo_atomicidade.py
T018 tests/test_catalogo_views_importacao.py
T019 tests/test_catalogo_permissoes.py

# Implementação: backend (task-implementer) e primitivos (frontend-implementer) em paralelo:
T020→T021→T022→T023 (catalogo/leitura_scpi.py, catalogo/importacao.py)
T028 static/css/components.css
```

## Parallel Example: User Story 2 (pode correr junto da US1)

```text
T030 tests/test_catalogo_consulta.py        T031 tests/test_catalogo_permissoes.py (após T019)
T032 catalogo/forms.py (após T025)           T035 templates de consulta (após T028)
```

## Implementation Strategy

### MVP First (User Story 1)

1. Setup + Foundational.
2. US1 completa: carga inicial com prévia, confirmação e resultado na interface.
3. **Parar e validar**: `quickstart.md` §3 e a suíte. O catálogo passa a existir no WMS.

### Incremental Delivery

1. US1 → base oficial carregada (MVP).
2. US2 → uso diário do catálogo.
3. US3 → histórico auditável de execuções.
4. US4 → reconciliação contínua com o SCPI.
5. Polish → review, gate visual, documentação do design system, converge.

A feature só é mergeada completa (as quatro stories). Os incrementos organizam a implementação e
a validação; não são entregas separadas em `main`.

## Rastreabilidade

| Requisito / regra | Tasks |
|---|---|
| FR-001–FR-005, `INV-CATALOG-001/002` | T008, T014, T015, T020, T021, T032 |
| FR-006, SC-005, `INV-CATALOG-003` | T011, T023, T048 |
| FR-007–FR-011, FR-007a, SC-002 | T015, T020, T021 |
| FR-012–FR-016, SC-004, SC-008, `INV-STOCK-001`, `INV-MOV-002` | T008, T016, T021, T023, T049 |
| FR-017–FR-024, `INV-CATALOG-005` | T015, T016, T021, T023, T035 |
| FR-025–FR-032, SC-009, SC-010, `INV-STOCK-002/003`, `INV-CATALOG-004` | T041–T047 |
| FR-033–FR-037, SC-003 | T009, T016, T023, T029, T036, T038, T040 |
| FR-038, `INV-STOCK-004` | T017, T023, T042, T045 |
| FR-039–FR-043, SC-006, SC-007 | T030, T032, T033, T035 |
| FR-044, FR-044a, `PERM-SCPI-IMPORT-EXECUTE` | T018, T019, T022–T026, T029 |
| FR-045, `PERM-MATERIAL-VIEW`, `PERM-SCPI-IMPORT-HISTORY-VIEW`, `INV-AUTH-001` | T013, T019, T026, T031, T033, T037, T038 |
| FR-046, FR-047, `INV-SCPI-001` | T023 (sem integração), T047 (sem ação de ajuste) |

## Notes

- Nenhuma task altera `spec.md`, as matrizes canônicas ou o recorte do ROADMAP.
- As interpretações I-1..I-6 (`research.md`) estão embutidas em T015/T020/T021 (I-1, I-2, I-5),
  T021 (I-3), T016/T022/T044 (I-4) e T018/T024 (I-6). Se o dono do produto mudar alguma, ajustar essas tasks antes
  de implementá-las.
- Commit, push, merge e troca de branch só por pedido explícito do usuário.

## Phase 8: Convergence

- [X] T057 Trocar o texto do cabeçalho de `catalogo/templates/catalogo/consulta.html` ("por um trecho da descrição") por um que descreva a busca por palavras da descrição, em qualquer ordem, per FR-040 / US2/AC2 (contradicts)
- [X] T058 Acrescentar a `tests/test_catalogo_leitura_scpi.py` um teste em que um registro `ESTRUTURA_INCONSISTENTE` repete o `CADPRO` de um registro íntegro e o íntegro continua aceito, sem `CADPRO_DUPLICADO_NO_ARQUIVO`, per research.md R5 (decisão de 2026-09-22) (partial)
- [X] T059 Registrar em `tasks.md`, junto da T047, que o Badge "Divergência" por linha foi dispensado pela revisão visual aprovada em T052 (divergência é informativa; o sinal da diferença é o diferenciador), per T047 / FR-029 / FR-030 (partial)
