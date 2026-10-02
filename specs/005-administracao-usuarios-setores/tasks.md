---

description: "Task list for implementing 005-administracao-usuarios-setores"
---

# Tasks: Administração de Usuários, Papéis e Setores

**Input**: Design documents from `specs/005-administracao-usuarios-setores/` (`spec.md`, `plan.md`,
`research.md`, `data-model.md`, `contracts/rotas-e-autorizacao.md`,
`contracts/operacoes-organizacionais.md`, `contracts/credenciais.md`, `quickstart.md`)

**Prerequisites**: `plan.md` (Constitution Check PASS), `spec.md` (7 user stories, P1–P7;
`clarify` concluído), `research.md` (R1–R19). Dependência obrigatória do roadmap satisfeita: `002`
(Autenticação e acesso inicial).

**Tests**: obrigatórios (Constitution VII). A feature toca permissões, autenticação, invariantes
CRÍTICAS (`INV-ORG-*`, `INV-AUTH-001`), transações e concorrência, e substitui o mecanismo das
salvaguardas da 002. Em cada story, os testes vêm antes da implementação e devem falhar primeiro.

**Organization**: por user story, na ordem de prioridade da spec. O modelo de dados, os triggers, a
barreira de escrita, a validação do estado final e a API de provisionamento ficam na fase
Foundational, porque toda a suíte (`tests/conftest.py`) e o `seed_dev` dependem deles. A ficha
básica do usuário fica na US1 (destino da senha entregue); listas, filtros, histórico e Home ficam na
US2. Designação, retirada e substituição de chefia ficam juntas na US4; a US7 usa a designação para
ativar setores.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: paralelizável (arquivo diferente, sem dependência de task incompleta)
- **[Story]**: US1–US7; ausente em Setup, Foundational e Polish
- **Executor**: sem marca → `task-implementer`; **(test-engineer)** → só testes;
  **(frontend-implementer)** → frontend significativo com `frontend-design`, dentro do `DESIGN.md`;
  **(coordenador)** → etapa do Claude principal
- **Aplica / Preserva**: IDs canônicos das matrizes

## Path Conventions

Django monolítico, apps na raiz; tudo desta feature em `contas/`; testes em `tests/` com prefixo
`test_contas_`; primitivos CSS em `static/css/components.css`. Sem migrations: depois de mudar
models ou o handler de triggers, `make resetdb`.

## Escopo — limite para todas as tasks (ROADMAP, linha ORG, "Não inclui")

Nenhuma task pode introduzir: criação, renomeação ou redefinição de papéis, ou mudança no que cada
papel concede; capability nova em `docs/domain/permissions-matrix.md`; poder operacional implícito
para o administrador ou por entrada no Almoxarifado; gestão de estoque ou escrita em model de outro
app; mudança no login da 002 além da etapa de definição obrigatória e da recusa por vencimento com a
mesma mensagem; recuperação de senha sem o administrador, e-mail, notificações ou SSO; chefe
substituto com prazo ou retorno automático; acesso do auditor ao histórico organizacional; exclusão
física de usuário ou setor; transferência em massa; a trava de desativação de setor por
requisições, estados de requisição ou `INV-REQ-001` (são de `REQ`); registro genérico de condições
externas (research R17); exibir nome do autor nas telas de entradas. Se uma task parecer exigir
isso, o implementador **para e reporta** ao coordenador.

---

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 (coordenador) Confirmar com o dono do produto a criação da branch da feature antes de
  qualquer código (a spec e o plano estão em `main`, sem commit; nenhuma troca de branch sem pedido
  explícito)
- [x] T002 [P] Em `config/settings/base.py`: acrescentar o logger `contas.organizacao` (INFO) em
  `LOGGING`, no formato de `estoque.entradas`; configurar
  `UserAttributeSimilarityValidator` com `"OPTIONS": {"user_attributes": ("matricula", "nome")}`
  (research R12), mantendo os outros três validadores

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: nenhuma story começa antes desta fase. Ao fim dela, a suíte inteira volta a passar
com a organização criada pela API de provisionamento.

- [x] T003 (coordenador) Acionar o `test-engineer` com `plan.md` → "Testes", `research.md` R19,
  `data-model.md`, os três contratos, `docs/domain/permissions-matrix.md` e
  `docs/domain/invariants-matrix.md`, para revisar e completar os cenários críticos antes da
  implementação. Prioridade: `INV-ORG-002`, `INV-ORG-004`, `INV-ORG-005`, `INV-ORG-006`,
  `INV-AUTH-001` e a regressão integral de FR-016a e FR-019 a FR-023 da 002
- [x] T004 [P] (test-engineer) Reescrever `tests/test_contas_models.py` para o modelo novo: cada
  constraint de `data-model.md` com `IntegrityError` — `setor_nome_unico_normalizado`
  (`UNIQUE (lower(trim(nome)))`), `setor_nome_nao_vazio` (`CHECK trim(nome) <> ''`),
  `setor_um_unico_almoxarifado` (`UNIQUE (almoxarifado) WHERE almoxarifado`),
  `setor_ativo_tem_ativacao` (`CHECK NOT ativo OR ativado_em IS NOT NULL`),
  `setor_almoxarifado_nao_desativado` (`CHECK NOT almoxarifado OR ativado_em IS NULL OR ativo`),
  `CHECK nome <> ''` e `CHECK matricula <> ''` em `User`, `CHECK usuario_id IS NOT NULL OR setor_id
  IS NOT NULL` em `EventoOrganizacional`; e a **barreira de escrita** (research R4): fora de uma
  operação, `save()`/`delete()` de `Setor` e `PapelUsuario`, `save()` de identidade de negócio que
  altere `matricula`, `nome`, `setor`, `is_active`, `is_superuser` ou `senha_provisoria_em`,
  `delete()` de `User` e `create`/`bulk_create`/`update`/`bulk_update`/`delete` de `QuerySet` sobre
  esses campos levantam `ValidationError`; continuam funcionando `create_superuser`,
  `save(update_fields=["last_login"])` e `save(update_fields=["password"])` (rehash do login).
  Preserva: `INV-ORG-001`, `INV-ORG-004`
- [x] T005 [P] (test-engineer) Escrever `tests/test_contas_banco.py` com
  `django_db(transaction=True)` e SQL direto (`connection.cursor()`), sem passar pelas operações:
  no commit, o trigger adiado recusa setor ativo sem chefe ativo, setor ativo com dois chefes
  ativos, `ROLE-WAREHOUSE-STAFF`/`ROLE-WAREHOUSE-HEAD` em usuário fora do Almoxarifado, usuário
  ativo com `ROLE-WAREHOUSE-HEAD` sem ser o chefe do Almoxarifado, chefe ativo do Almoxarifado ativo
  sem `ROLE-WAREHOUSE-HEAD` ou sem `ROLE-WAREHOUSE-STAFF`, identidade de negócio ativa sem
  `ROLE-REQUESTER` e conta técnica com papel; aceita um estado intermediário inválido corrigido
  antes do commit (base da substituição); recusa `UPDATE` de `Setor.almoxarifado`, `UPDATE` de
  `Setor.ativado_em` já preenchido e `UPDATE`/`DELETE` de `EventoOrganizacional`; o `flush` dos
  testes transacionais reemite o `post_migrate` sem erro (idempotência); um login com atualização
  de `last_login` não espera por uma operação de organização em andamento (com o lock tomado em
  outra conexão, o login conclui). Preserva: `INV-ORG-002`, `INV-ORG-004`, `INV-ORG-005`,
  `INV-ORG-006`
- [x] T006 [P] (test-engineer) Reescrever `tests/test_contas_organizacao.py` e
  `tests/test_contas_revisao_integridade.py` sobre `contas.organizacao.validar_organizacao` e a API
  de provisionamento (T011), mantendo cada caso hoje coberto de FR-016a e FR-019 a FR-023 da 002:
  setor nasce inativo; ativação exige exatamente um chefe ativo; chefe de outro setor não habilita;
  setor inativo admite as operações que o ativo recusa; conta técnica sem papéis; identidade ativa
  sem `ROLE-REQUESTER` recusada; chefia estruturalmente única (`INV-ORG-003`). Os casos de operação
  (desativar o chefe, transferir o chefe, remover o papel do chefe, segundo chefe) ficam marcados
  com o nome da operação e são completados nas stories US3, US4 e US5. Preserva: `INV-ORG-001` a
  `INV-ORG-003`
- [x] T007 [P] (test-engineer) Escrever `tests/test_contas_provisionamento.py`: a API de
  provisionamento cria setor (com e sem designação de Almoxarifado) e usuários com papéis, valida o
  estado final e registra eventos com `autor` nulo; recusa um segundo Almoxarifado; o comando
  `provisionar_organizacao --setor-almoxarifado NOME --matricula M --nome N` em banco vazio cria o
  Almoxarifado ativo e uma conta com `ROLE-REQUESTER`, `ROLE-SYSTEM-ADMIN`, `ROLE-SECTOR-HEAD`,
  `ROLE-WAREHOUSE-HEAD` e `ROLE-WAREHOUSE-STAFF`, imprime a senha provisória uma vez, deixa
  `senha_provisoria_em` preenchido e não registra a senha em evento; rodar de novo, ou com qualquer
  setor ou identidade de negócio existente, é recusado sem gravar nada (FR-050); com settings de
  produção simuladas, `provisionar_usuario(..., senha=...)` é recusado sem gravar nada (FR-031).
  Aplica: D-23.
  Preserva: `INV-ORG-004`, `INV-ORG-006`
- [x] T008 Alterar `contas/models.py` conforme `data-model.md`:
  - `User`: `nome = CharField(max_length=150)` ("obrigatório; gravado sem espaços nas pontas;
    `CHECK nome <> ''`"); `nome_busca = CharField(max_length=150)` (`normalizar_para_busca(nome)`,
    gravado junto com `nome`); `senha_provisoria_em = DateTimeField(null=True, blank=True)`;
    `REQUIRED_FIELDS = ["setor", "nome"]`; constraints `CHECK nome <> ''` e `CHECK matricula <> ''`;
  - `Setor`: `nome = CharField(max_length=100)` gravado sem espaços nas pontas;
    `almoxarifado = BooleanField(default=False)`; `ativado_em = DateTimeField(null=True,
    blank=True)`; as cinco constraints de T004 com os nomes de `data-model.md`;
  - `EventoOrganizacional` e `TipoEvento` (lista fechada de `data-model.md`), com `momento`,
    `autor`, `tipo`, `usuario`, `usuario_relacionado`, `setor`, `setor_relacionado` (FKs `PROTECT`,
    nulas), `dados` (`JSONField`), `justificativa` (`TextField(blank=True)`), `chave_confirmacao`
    (`UUIDField(null=True, unique=True)`), o `CHECK` de alvo e os quatro índices por alvo e momento;
  - **remover** `_exigir_chefia_preservada`, `_exigir_chefia_nao_duplicada`, a lógica
    organizacional de `User.save()`/`delete()`, a de `PapelUsuario.save()`/`delete()`/`clean()`,
    `Setor.save()` com a checagem de chefe e `_bloquear_atribuicao` (research R3);
  - acrescentar a barreira de escrita de T004 (research R4), consultando o marcador de operação de
    `contas.organizacao` sem import circular (o `ContextVar` pode morar em `contas/models.py` e ser
    ligado só por `contas.organizacao`).
  Manter `chefes_ativos()` como consulta. Aplica: research R3, R4, R13. Preserva: `INV-ORG-001`,
  `INV-ORG-003`, `INV-ORG-004`
- [x] T009 Implementar em `contas/apps.py` um handler `post_migrate` (`sender=self`, idempotente:
  `CREATE OR REPLACE FUNCTION`, `DROP TRIGGER IF EXISTS`, nomes de tabela por `_meta.db_table`), no
  molde de `estoque/apps.py`: trigger `BEFORE UPDATE` em `Setor` que recusa mudar `almoxarifado` e
  mudar `ativado_em` já preenchido; trigger `BEFORE UPDATE OR DELETE` em `EventoOrganizacional` que
  recusa tudo; `CONSTRAINT TRIGGER ... DEFERRABLE INITIALLY DEFERRED`, `AFTER INSERT OR DELETE OR
  UPDATE OF setor_id, is_active, is_superuser` em `contas_user` e `AFTER INSERT OR UPDATE OR DELETE`
  em `contas_papelusuario` e `contas_setor` (o login e o rehash de senha não disparam), que, no commit, toma
  `pg_advisory_xact_lock(CHAVE_LOCK_ORGANIZACAO)` e verifica as quatro regras de
  "Verificação de estado final" de `data-model.md` nos setores e usuários tocados. Comentar o SQL
  como futura `RunSQL` (Constitution XIII). Aplica: research R5. Preserva: `INV-ORG-002`,
  `INV-ORG-004`, `INV-ORG-005`, `INV-ORG-006`, FR-016a (002)
- [x] T010 Criar `contas/organizacao.py` com a base comum (research R1–R3, R18;
  `contracts/operacoes-organizacionais.md`): `CHAVE_LOCK_ORGANIZACAO` (constante própria, distinta
  das chaves de importação); exceções `OperacaoRecusada(motivo, caminho=None)`,
  `OperacaoJaExecutada(evento)` e `PreviaDesatualizada(previa)`; um context manager interno de
  operação que abre `transaction.atomic()`, toma o advisory lock e liga a barreira; 
  `validar_organizacao(setores, usuarios)` com as quatro regras de `data-model.md`, levantando
  `OperacaoRecusada` com a regra violada; `_registrar_evento(...)`; `_papeis(usuario)`;
  `_administradores_ativos()`; logger `contas.organizacao` sem senha nem `dados`. Nenhum import de
  model de outro app (FR-051). Preserva: `INV-ORG-001` a `INV-ORG-006`
- [x] T011 Implementar em `contas/organizacao.py` a API de provisionamento técnico, autor nulo
  (research R15): `provisionar_setor(nome, *, almoxarifado=False, ativo=False)`,
  `provisionar_usuario(matricula, nome, setor, papeis, *, senha=None, is_active=True)` — sem `senha`,
  gera provisória por `contas.credenciais.gerar_senha_provisoria` (criar `contas/credenciais.py` só
  com `gerar_senha_provisoria` e `VALIDADE_SENHA_PROVISORIA = timedelta(days=7)` nesta task:
  12 caracteres de `secrets`, alfabeto sem `0 O 1 l I`, ao menos uma letra e um dígito) e devolve
  `(usuario, senha)`; com `senha` (só desenvolvimento e testes — recusada com
  `ImproperlyConfigured` quando `settings.SETTINGS_MODULE` não for `config.settings.development`
  nem `config.settings.test`), grava definitiva e registra `SENHA_DEFINIDA` —, e `provisionar_ativacao(setor)`. Todas validam o estado final e registram os
  eventos de `data-model.md`. Recusam segundo Almoxarifado. Aplica: D-23, FR-050. Preserva:
  `INV-ORG-004` a `INV-ORG-006`, FR-016a (002)
- [x] T012 Criar `contas/management/commands/provisionar_organizacao.py` (`--setor-almoxarifado`,
  `--matricula`, `--nome`): recusa se existir qualquer `Setor` ou identidade de negócio; numa
  transação, pela API de T011, cria o Almoxarifado, a conta com os cinco papéis e ativa o setor;
  imprime a senha provisória uma única vez. Faz T007 passar
- [x] T013 Reescrever as fábricas de `tests/conftest.py` sobre a API de provisionamento (T011):
  `setor` vira o setor designado como Almoxarifado ("Almoxarifado Central", inativo);
  `criar_usuario` passa `nome` (padrão derivado da matrícula) e `senha=SENHA_VALIDA`;
  `criar_usuario_com_papeis` concede os papéis pela mesma API; `chefe_setor` continua em
  "Setor Outro"; `superusuario_tecnico` inalterado. Procurar nos testes de outros apps
  (`tests/test_catalogo_*`, `test_fornecedores_*`, `test_estoque_*`, `test_contas_home*`,
  `test_contas_auth.py`, `test_contas_login_simulado.py`, `test_contas_logout.py`,
  `test_contas_protected_access.py`) criações diretas de `User`, `Setor` ou `PapelUsuario` e
  trocá-las pelas fábricas, sem mudar o que cada teste verifica
- [x] T014 [P] Alterar `contas/dev_seed/dados.py` (nome fictício por conta, setor `almox` como
  Almoxarifado) e `contas/management/commands/seed_dev.py` (organização pela API de T011, com
  `senha=SEED_DEV_PASSWORD`; `almox` com `almoxarifado=True`; ativação pela API; conta técnica
  `admin` por `create_superuser`); atualizar `tests/test_seed_dev.py` para conferir o Almoxarifado
  designado e `validar_organizacao` sem recusa sobre todo o banco
- [x] T015 [P] Tornar somente leitura em `contas/admin.py` `UserAdmin`, `SetorAdmin` e
  `PapelUsuarioAdmin` (`has_add_permission`, `has_change_permission`, `has_delete_permission` →
  `False`; listas com `nome`, `almoxarifado`, `ativado_em`) e registrar `EventoOrganizacional` só
  para consulta; remover `ContaCriacaoForm`, `ContaAlteracaoForm` e o inline editável; reescrever
  `tests/test_contas_admin.py` para provar que o superusuário técnico consulta e não adiciona, não
  altera e não exclui (POST direto incluído). Aplica: research R6
- [x] T016 (coordenador) `make resetdb` e `make test`: a suíte inteira verde, incluindo T004–T007,
  T014 e T015. Checkpoint da fase

**Checkpoint**: modelo, banco, barreira, validação final, provisionamento e fixtures prontos.

---

## Phase 3: User Story 1 - Cadastrar usuário e entregar a credencial (Priority: P1) 🎯 MVP

**Goal**: o administrador cadastra um usuário, recebe a senha provisória uma vez, e o usuário só
consegue definir a própria senha no primeiro acesso.

**Independent Test**: cadastrar, anotar a senha, autenticar com ela, ver só a definição de senha,
definir e acessar normalmente (spec, US1).

### Tests for User Story 1

- [x] T017 [P] [US1] (test-engineer) Escrever `tests/test_contas_operacoes_usuario.py` (parte de
  cadastro): `cadastrar_usuario` cria conta ativa com `ROLE-REQUESTER` e os adicionais, `nome`
  sem espaços nas pontas, `nome_busca`, `senha_provisoria_em`, eventos `USUARIO_CADASTRADO` (com a
  chave) e `SENHA_PROVISORIA_GERADA` sem senha; cada recusa da linha `cadastrar_usuario` de
  `contracts/operacoes-organizacionais.md` (matrícula repetida, nome vazio, setor ausente,
  `ROLE-SECTOR-HEAD` em setor com chefe ou ativo, papel de almoxarifado fora dele,
  `ROLE-WAREHOUSE-HEAD` sem a chefia) sem escrita nem evento; cadastro de chefe num setor inativo
  sem chefe é designação, e no Almoxarifado inclui os três papéis; mesma `chave_confirmacao` →
  `OperacaoJaExecutada` sem nova conta. Aplica: `PERM-USER-MANAGE`. Preserva: `INV-ORG-001`,
  `INV-ORG-002`, `INV-ORG-005`, `INV-ORG-006`, FR-016a (002)
- [x] T018 [P] [US1] (test-engineer) Escrever `tests/test_contas_credenciais.py` (parte de US1):
  a senha gerada satisfaz os validadores de R12, tem 12 caracteres do alfabeto e ao menos uma
  letra e um dígito; login com provisória válida autentica; com provisória vencida (relógio por
  `monkeypatch` de `timezone.now`, 7 dias) é recusado com exatamente a mesma mensagem de senha
  errada; sessão aberta com provisória que vence → logout e login na interação seguinte; com
  provisória, toda rota existente (incluindo `catalogo`, `estoque`, `fornecedores` e `/organizacao/`)
  redireciona a `/senha/`, exceto `/senha/` e o logout; requisição HTMX recebe `HX-Redirect`;
  definição obrigatória recusa senha igual à provisória e senha fora da política; sucesso limpa
  `senha_provisoria_em`, registra `SENHA_DEFINIDA` sem senha, mantém a sessão em uso, encerra as
  demais e redireciona ao destino do marcador `_retorno_pos_login_destino` (proibido → Home pelo
  `RetornoPosLoginMiddleware`) ou à Home sem marcador (FR-034); nenhuma senha aparece em log
  (`caplog`), sessão ou evento. Preserva: `INV-AUTH-001`; FR-003, FR-010, FR-011 da 002
- [x] T019 [P] [US1] (test-engineer) Escrever `tests/test_contas_views_organizacao.py` (parte de
  US1): GET do formulário traz `chave_confirmacao`; POST válido → 200 com a senha e
  `Cache-Control: no-store`, nunca redirect; repetir o POST → aviso "operação já executada" e 302
  para a ficha, sem senha; recusa → 200 com motivo e caminho e dados preservados; a ficha mostra
  dados, papéis e "Provisória — vence em …" / "Provisória vencida em …", nunca a senha; conta
  técnica na ficha → 404; e `tests/test_contas_permissoes_organizacao.py` com `usuario_novo` (GET e
  POST) e `usuario` para todos os papéis da matriz de `contracts/rotas-e-autorizacao.md`,
  confirmando que nenhum 403 grava `User`, `PapelUsuario` ou `EventoOrganizacional`. Aplica:
  `PERM-USER-MANAGE`

### Implementation for User Story 1

- [x] T020 [US1] Implementar `cadastrar_usuario(autor, *, matricula, nome, setor_id,
  papeis_adicionais, chave_confirmacao)` em `contas/organizacao.py` conforme
  `contracts/operacoes-organizacionais.md` (recusas, efeitos, eventos), reusando a criação interna
  de T011. Aplica: `PERM-USER-MANAGE`. Preserva: `INV-ORG-001`, `INV-ORG-002`, `INV-ORG-005`,
  `INV-ORG-006`, FR-016a (002)
- [x] T021 [US1] Criar `contas/backends.py` com `WMSModelBackend(ModelBackend)` cujo
  `user_can_authenticate` também recusa provisória vencida (`VALIDADE_SENHA_PROVISORIA`) e apontar
  `AUTHENTICATION_BACKENDS` para ele em `config/settings/base.py`; conferir que
  `contas/login_simulado.py` (que usa `AUTHENTICATION_BACKENDS[0]`) continua funcionando. Aplica:
  research R9
- [x] T022 [US1] Implementar `CredencialProvisoriaMiddleware` em `contas/middleware.py` conforme
  `contracts/credenciais.md` (vencida → logout + login; `definir_senha`, `logout` e estáticos
  seguem; resto → 302 ou `HX-Redirect` para `definir_senha`) e registrá-lo em `MIDDLEWARE` de
  `config/settings/base.py` logo depois de `AuthenticationMiddleware`. Aplica: research R10.
  Preserva: `INV-AUTH-001`
- [x] T023 [US1] Implementar em `contas/credenciais.py` `definir_propria_senha(request, usuario,
  nova)` (sob a operação de organização: política de R12, diferente da provisória, `set_password`,
  `senha_provisoria_em = None`, `update_session_auth_hash`, evento `SENHA_DEFINIDA` com
  `motivo=definicao_obrigatoria`); `DefinirSenhaForm` em `contas/forms.py`; `SenhaView` em
  `contas/views.py` com rota `definir_senha` (`/senha/`) em `contas/urls.py`, por ora só no estado
  provisório, redirecionando ao destino do marcador ou à Home (FR-034). Aplica: D-27, FR-039
- [x] T024 [US1] Implementar `UsuarioCadastroForm` (matrícula, nome, setor, papéis adicionais
  exceto `ROLE-REQUESTER`, `chave_confirmacao` oculta) em `contas/forms.py`; `UsuarioNovoView`
  (POST de sucesso renderiza 200 com a senha e `never_cache`/`no-store`; `OperacaoJaExecutada` →
  mensagem e 302; `OperacaoRecusada` → alerta com motivo e caminho) e `UsuarioFichaView` (dados,
  papéis, situação da credencial calculada na view; conta técnica → 404) em `contas/views.py`, com
  `ExigePapelMixin(Papel.ADMINISTRADOR_SISTEMA)`; rotas `usuario_novo` e `usuario` em
  `contas/urls.py` sob `/organizacao/`. Aplica: `PERM-USER-MANAGE`
- [x] T025 [US1] (frontend-implementer) Criar `contas/templates/contas/organizacao/usuario_form.html`,
  `usuario_senha_entregue.html` (bloco de exibição única da senha, legível para ditar ou copiar, com
  o aviso de que não será mostrada de novo e o link para a ficha), `usuario.html` (ficha básica:
  Page Header, dados, papéis em Badge, situação da credencial; seção de histórico e ações ficam para
  as stories seguintes) e `contas/templates/contas/senha.html` no estado de definição obrigatória
  (sem navegação nem atalhos, só o logout). Reusar os componentes de `DESIGN.md`

**Checkpoint**: US1 funcional e testável sozinha (MVP).

---

## Phase 4: User Story 2 - Consultar usuários, setores e histórico organizacional (Priority: P2)

**Goal**: listas com busca e filtros, fichas de usuário e de setor com histórico, atalhos na Home.

**Independent Test**: buscar por nome sem acento, matrícula, setor, situação e papel; abrir fichas e
conferir dados e histórico (spec, US2).

### Tests for User Story 2

- [x] T026 [P] [US2] (test-engineer) Escrever `tests/test_contas_historico.py`: a ficha do usuário
  lista os eventos em que ele é `usuario` ou `usuario_relacionado`, e a do setor os em que ele é
  `setor` ou `setor_relacionado`, em ordem cronológica, com autor, momento e anterior/novo; operação
  sem efeito não gera evento; nenhum evento contém senha; evento com `autor` nulo aparece na ficha
  como "Provisionamento técnico"; histórico paginado. Aplica: FR-040 a FR-042
- [x] T027 [P] [US2] (test-engineer) Completar `tests/test_contas_views_organizacao.py` com a lista de
  usuários (busca por parte do nome com e sem acento, matrícula exata, filtros combinados de setor,
  situação e papel, paginação de 50, conta técnica nunca listada, número fixo de queries, resposta
  com `HX-Request` só com a região de resultados, estado vazio) e a lista e ficha de setores (chefe,
  membros ativos, marca de Almoxarifado, membros ativos e inativos, "já esteve ativo"); e
  `tests/test_contas_permissoes_organizacao.py` com `usuarios`, `setores` e `setor`; e
  `tests/test_contas_home_papeis.py` com os atalhos Usuários e Setores só para o administrador e o
  item ORG fora de "Em preparação". Aplica: `PERM-USER-MANAGE`, `PERM-SECTOR-MANAGE`

### Implementation for User Story 2

- [x] T028 [US2] Implementar `FiltroUsuariosForm` e `FiltroSetoresForm` (GET) em `contas/forms.py`;
  `UsuariosView` (paginação 50, `nome_busca` por `normalizar_para_busca`, matrícula exata,
  `prefetch_related` dos papéis, `is_superuser=False`), `SetoresView` (chefe e membros ativos
  anotados numa consulta; a contagem de membros exclui contas técnicas) e `SetorFichaView` em `contas/views.py`; histórico paginado nas duas
  fichas; rotas `usuarios`, `setores` e `setor` em `contas/urls.py`. Aplica: `PERM-USER-MANAGE`,
  `PERM-SECTOR-MANAGE`, FR-043 a FR-045
- [x] T029 [US2] Em `contas/views.py`, `HomeView` ganha `pode_administrar_organizacao`
  (`ADMINISTRADOR_SISTEMA`, do mesmo `set` de papéis) e o item ORG sai de `CAPACIDADES_PLANEJADAS`
- [x] T030 [US2] (frontend-implementer) Criar `contas/templates/contas/organizacao/usuarios.html`,
  `_resultados_usuarios.html`, `setores.html`, `setor.html` e `_historico.html` (Filter Bar, Table,
  Badge de situação e papéis, Pagination, Empty State, Retorno contextual); incluir `_historico.html`
  em `usuario.html`; acrescentar os atalhos Usuários e Setores em
  `contas/templates/contas/home.html`

**Checkpoint**: US1 e US2 funcionais.

---

## Phase 5: User Story 3 - Manter dados, papéis e vínculo setorial (Priority: P3)

**Goal**: editar nome e matrícula, conceder e remover papéis, transferir com prévia.

**Independent Test**: spec, US3, cenários 1 a 7.

### Tests for User Story 3

- [x] T031 [P] [US3] (test-engineer) Completar `tests/test_contas_operacoes_usuario.py` com
  `editar_usuario` (nome, correção de matrícula com anterior no evento, unicidade, sem efeito sem
  evento), `alterar_papeis` (cada recusa da tabela, incluindo o último administrador ativo e o
  `ROLE-WAREHOUSE-STAFF` do chefe do Almoxarifado; concessões permitidas por setor) e
  `transferir_usuario` (remove exatamente `ROLE-SECTOR-ASSISTANT`, `ROLE-SECTOR-HEAD`,
  `ROLE-WAREHOUSE-STAFF`, `ROLE-WAREHOUSE-HEAD`; mantém `ROLE-REQUESTER`, `ROLE-AUDITOR`,
  `ROLE-SYSTEM-ADMIN`; não concede nada no Almoxarifado; recusa chefe de setor ativo e destino
  igual; transfere chefe de setor inativo e usuário inativo; `PreviaDesatualizada` quando os papéis
  presos mudaram depois da prévia); completar os casos de transferência marcados em
  `tests/test_contas_organizacao.py` (FR-021 e FR-022 da 002); em `tests/test_contas_concorrencia.py`
  (`transaction=True`, `threading.Barrier`), alteração de papéis concorrente com transferência do
  mesmo usuário → resultado equivalente a uma ordem serial. Aplica: `PERM-USER-MANAGE`. Preserva:
  `INV-ORG-001`, `INV-ORG-002`, `INV-ORG-005`, `INV-ORG-006`, FR-016a (002)
- [x] T032 [P] [US3] (test-engineer) Completar `tests/test_contas_views_organizacao.py` com edição,
  papéis (papéis não editáveis aparecem bloqueados com o motivo) e transferência em duas etapas
  (prévia lista os papéis a remover; confirmação executa; prévia desatualizada mostra nova
  prévia); e `tests/test_contas_permissoes_organizacao.py` com `usuario_editar`, `usuario_papeis` e
  `usuario_transferir`

### Implementation for User Story 3

- [x] T033 [US3] Implementar `editar_usuario`, `alterar_papeis`, `previa_transferencia` e
  `transferir_usuario` em `contas/organizacao.py` conforme o contrato. Aplica: `PERM-USER-MANAGE`.
  Preserva: `INV-ORG-001`, `INV-ORG-002`, `INV-ORG-005`, `INV-ORG-006`
- [x] T034 [US3] Implementar `UsuarioEdicaoForm`, `UsuarioPapeisForm` (sete papéis; a view informa
  quais estão bloqueados e por quê) e `TransferenciaForm` em `contas/forms.py`; views e rotas
  `usuario_editar`, `usuario_papeis` e `usuario_transferir` (POST sem `confirmar` → prévia; com
  `confirmar=1` e `papeis_removidos_previstos` → executa) em `contas/views.py` e `contas/urls.py`;
  ações correspondentes na ficha. Aplica: FR-049
- [x] T035 [US3] (frontend-implementer) Criar `usuario_editar.html`, `usuario_papeis.html` (lista de
  papéis com estado bloqueado e motivo) e `usuario_transferir.html` (escolha e prévia com
  Confirmação) em `contas/templates/contas/organizacao/`; ações na ficha

**Checkpoint**: US1 a US3 funcionais.

---

## Phase 6: User Story 4 - Substituir o chefe de um setor ativo (Priority: P4)

**Goal**: designação e retirada da chefia em setor inativo; substituição atômica em setor ativo,
movendo a chefia de estoque no Almoxarifado.

**Independent Test**: spec, US4, cenários 1 a 5, e US7, cenário 7.

### Tests for User Story 4

- [x] T036 [P] [US4] (test-engineer) Escrever `tests/test_contas_operacoes_chefia.py`:
  `designar_chefia` (setor inativo sem chefe; no Almoxarifado concede `ROLE-SECTOR-HEAD`,
  `ROLE-WAREHOUSE-HEAD` e, se faltar, `ROLE-WAREHOUSE-STAFF`; recusas do contrato); `retirar_chefia`
  (setor inativo; no Almoxarifado retira junto `ROLE-WAREHOUSE-HEAD`); `substituir_chefia` (cenários
  1 a 4 da US4; anterior continua ativo, no setor, com os demais papéis; recusas de novo chefe de
  outro setor, inativo ou igual; `chefe_esperado_id` desatualizado; setor inativo); evento
  `CHEFIA_SUBSTITUIDA` nas fichas dos dois usuários e do setor; completar os casos de chefia
  marcados em `tests/test_contas_organizacao.py`; em `tests/test_contas_concorrencia.py`, duas
  substituições do mesmo setor (uma aplicada, a outra recusada; nunca zero nem dois chefes) e
  substituição × transferência do novo chefe; em `tests/test_contas_banco.py`, nenhum commit com
  dois chefes do almoxarifado ativos durante a substituição; depois da substituição,
  `chefes_ativos(setor)` devolve só o novo chefe na consulta seguinte (FR-052). Aplica:
  `PERM-SECTOR-MANAGE`.
  Preserva: `INV-ORG-002`, `INV-ORG-003`, `INV-ORG-006`
- [x] T037 [P] [US4] (test-engineer) Completar `tests/test_contas_views_organizacao.py` com a tela de
  chefia nos três estados (designar, retirar, substituir com prévia e `chefe_esperado`) e
  `tests/test_contas_permissoes_organizacao.py` com `setor_chefia`

### Implementation for User Story 4

- [x] T038 [US4] Implementar `designar_chefia`, `retirar_chefia`, `previa_substituicao` e
  `substituir_chefia` em `contas/organizacao.py` conforme o contrato, validando o estado final só
  depois de mover os papéis (research R3). Aplica: `PERM-SECTOR-MANAGE`. Preserva: `INV-ORG-002`,
  `INV-ORG-003`, `INV-ORG-006`
- [x] T039 [US4] Implementar `ChefiaForm` em `contas/forms.py` e a view `setor_chefia` em
  `contas/views.py`/`contas/urls.py` (estado do setor decide entre designar, retirar e substituir;
  candidatos só membros ativos do setor; substituição em duas etapas com `chefe_esperado_id`)
- [x] T040 [US4] (frontend-implementer) Criar
  `contas/templates/contas/organizacao/setor_chefia.html` (três variantes; prévia da substituição
  mostrando o que cada pessoa ganha e perde, inclusive os papéis de almoxarifado) e a ação na ficha
  do setor

**Checkpoint**: US1 a US4 funcionais.

---

## Phase 7: User Story 5 - Desativar e reativar usuários (Priority: P5)

**Goal**: desativação com papéis preservados e proteções do administrador; reativação com revisão.

**Independent Test**: spec, US5, cenários 1 a 6.

### Tests for User Story 5

- [x] T041 [P] [US5] (test-engineer) Escrever `tests/test_contas_operacoes_situacao.py`:
  `desativar_usuario` (papéis preservados; justificativa no evento; sessão aberta recusada na
  interação seguinte; recusas de chefe de setor ativo, própria conta e último administrador; nunca
  bloqueada por registros de outro app); `reativar_usuario` (`previa_reativacao` lista os papéis
  preservados; resultado igual ao confirmado; `ROLE-REQUESTER` sempre mantido; recusa por papel que
  violaria `INV-ORG-002`, `INV-ORG-005` ou `INV-ORG-006`, com motivo por papel, e sucesso depois de
  desmarcar; reativação em setor inativo); completar os casos de desativação marcados em
  `tests/test_contas_organizacao.py` (FR-021 da 002); em `tests/test_contas_concorrencia.py`,
  desativação concorrente dos dois últimos administradores → um recusado, e ativação de setor ×
  desativação do chefe → nunca ambas. Aplica: `PERM-USER-MANAGE`. Preserva: `INV-AUTH-001`,
  `INV-ORG-002`, `INV-ORG-005`, `INV-ORG-006`, FR-016a (002)
- [x] T042 [P] [US5] (test-engineer) Completar `tests/test_contas_views_organizacao.py` com
  desativação (confirmação, justificativa) e reativação (revisão com `ROLE-REQUESTER` travado; papel
  recusado indicado na linha) e `tests/test_contas_permissoes_organizacao.py` com
  `usuario_desativar` e `usuario_reativar`; no mesmo arquivo, depois de retirar
  `ROLE-SYSTEM-ADMIN` de um de dois administradores, a próxima requisição dele a `/organizacao/`
  recebe 403 na mesma sessão (FR-052)

### Implementation for User Story 5

- [x] T043 [US5] Implementar `desativar_usuario`, `previa_reativacao` e `reativar_usuario` em
  `contas/organizacao.py` conforme o contrato, com as proteções de D-15 sob o lock. Aplica:
  `PERM-USER-MANAGE`. Preserva: `INV-AUTH-001`, `INV-ORG-002`, `INV-ORG-005`, `INV-ORG-006`
- [x] T044 [US5] Implementar `DesativacaoForm` e `ReativacaoForm` em `contas/forms.py`; views e rotas
  `usuario_desativar` e `usuario_reativar` em `contas/views.py`/`contas/urls.py`; flags de ação na
  ficha calculadas na view
- [x] T045 [US5] (frontend-implementer) Criar `usuario_desativar.html` e `usuario_reativar.html`
  (revisão de papéis com o motivo de recusa na linha) em `contas/templates/contas/organizacao/`;
  ações e Badge de situação na ficha

**Checkpoint**: US1 a US5 funcionais.

---

## Phase 8: User Story 6 - Redefinir a senha e trocar a própria senha (Priority: P6)

**Goal**: redefinição pelo administrador com nova provisória e sessões encerradas; troca voluntária.

**Independent Test**: spec, US6, cenários 1 a 5.

### Tests for User Story 6

- [x] T046 [P] [US6] (test-engineer) Completar `tests/test_contas_credenciais.py`:
  `redefinir_senha` gera provisória, preenche `senha_provisoria_em`, registra
  `SENHA_PROVISORIA_GERADA` com a chave e sem senha, encerra todas as sessões da conta (inclusive a
  do administrador que redefine a própria) e exige definição no próximo acesso; a mesma chave não
  gera outra senha; troca voluntária com a senha atual certa (nova vale; demais sessões encerradas;
  sessão em uso mantida; evento `SENHA_DEFINIDA` com `motivo=troca_voluntaria`) e errada (nada
  muda); política de R12 nos dois casos; vencimento depois de redefinição (cenário 5 da US6).
  Preserva: `INV-AUTH-001`
- [x] T047 [P] [US6] (test-engineer) Completar `tests/test_contas_views_organizacao.py` com a
  redefinição (200 `no-store` com a senha; repetição sem senha) e `/senha/` no estado definitivo; e
  `tests/test_contas_permissoes_organizacao.py` com `usuario_redefinir_senha` e `definir_senha`
  (todo autenticado ativo; anônimo e inativo → login)

### Implementation for User Story 6

- [x] T048 [US6] Implementar `redefinir_senha` em `contas/organizacao.py` e `trocar_propria_senha` em
  `contas/credenciais.py` conforme `contracts/credenciais.md`; `TrocarSenhaForm` em
  `contas/forms.py`; `SenhaView` passa a atender o estado definitivo (senha atual, nova,
  confirmação; sucesso → Home com "Senha alterada."); view e rota `usuario_redefinir_senha`.
  Aplica: `PERM-USER-MANAGE`, D-27
- [x] T049 [US6] (frontend-implementer) Criar `usuario_redefinir_senha.html` (confirmação; o sucesso
  reusa o bloco de senha entregue de T025), completar `senha.html` com o estado de troca voluntária
  e acrescentar o link "Senha" ao lado de "Sair" em `contas/templates/contas/_barra_trabalho.html`

**Checkpoint**: US1 a US6 funcionais.

---

## Phase 9: User Story 7 - Administrar setores (Priority: P7)

**Goal**: criar, renomear, ativar e desativar setores.

**Independent Test**: spec, US7, cenários 1 a 7 (o 3 e o 7 usam a designação da US4).

### Tests for User Story 7

- [x] T050 [P] [US7] (test-engineer) Escrever `tests/test_contas_operacoes_setor.py`: `criar_setor`
  (nasce inativo, `almoxarifado=False`, nome sem espaços nas pontas; " eta " recusado diante de
  "ETA"); `renomear_setor` (mesmo setor pode mudar só a caixa; Almoxarifado renomeado mantém a
  designação); `ativar_setor` (preenche `ativado_em` só na primeira vez; recusas de FR-020 da 002 e
  de `INV-ORG-006` no Almoxarifado); `desativar_setor` (só com o chefe como único membro ativo,
  listando os demais na recusa; membros inativos não impedem; setor cujo único outro usuário ativo é
  a conta técnica pode ser desativado; Almoxarifado ativado sempre recusado;
  reativação segue a ativação; histórico mostra que já esteve ativo); em
  `tests/test_contas_concorrencia.py`, duas criações ou renomeações concorrentes para o mesmo nome →
  uma recusada. Aplica: `PERM-SECTOR-MANAGE`. Preserva: `INV-ORG-002`, `INV-ORG-004`,
  `INV-ORG-006`
- [x] T051 [P] [US7] (test-engineer) Completar `tests/test_contas_views_organizacao.py` com
  criação, edição, ativação e desativação de setor (o Almoxarifado ativado não oferece
  desativação) e `tests/test_contas_permissoes_organizacao.py` com `setor_novo`, `setor_editar`,
  `setor_ativar` e `setor_desativar`

### Implementation for User Story 7

- [x] T052 [US7] Implementar `criar_setor`, `renomear_setor`, `ativar_setor` e `desativar_setor` em
  `contas/organizacao.py` conforme o contrato; a contagem de membros ativos de `desativar_setor`
  considera só `is_superuser=False` (FR-028); em `desativar_setor`, deixar um único ponto
  comentado onde outro recorte acrescentará sua condição (FR-053, research R17), sem mecanismo
  genérico. Aplica: `PERM-SECTOR-MANAGE`. Preserva: `INV-ORG-002`, `INV-ORG-004`, `INV-ORG-006`
- [x] T053 [US7] Implementar `SetorForm` em `contas/forms.py`; views e rotas `setor_novo`,
  `setor_editar`, `setor_ativar` e `setor_desativar` em `contas/views.py`/`contas/urls.py`; flags de
  ação na ficha do setor
- [x] T054 [US7] (frontend-implementer) Criar `setor_form.html`, `setor_ativar.html` e
  `setor_desativar.html` em `contas/templates/contas/organizacao/`; ações na ficha e na lista de
  setores

**Checkpoint**: todas as stories funcionais.

---

## Phase 10: Polish & Cross-Cutting Concerns

- [x] T055 [P] (test-engineer) Acrescentar a `tests/test_contas_operacoes_usuario.py` a verificação
  de FR-051: `contas.organizacao` e `contas.credenciais` não importam models de `catalogo`,
  `fornecedores` nem `estoque`, e nenhuma operação altera linhas dessas tabelas (contagem antes e
  depois sobre um banco com entradas registradas)
- [x] T056 [P] Atualizar `docs/development/seed-dev.md` e `docs/development/login-simulado.md`
  (nomes fictícios, Almoxarifado designado, Admin somente leitura, comando
  `provisionar_organizacao`, `/senha/`)
- [x] T057 (coordenador) `make resetdb`, `make seed_dev`, `make verify` e o roteiro de
  `quickstart.md` (§1 a §4)
- [x] T058 (coordenador) Acionar o `code-reviewer` com o escopo da feature, `spec.md`, `plan.md`, os
  contratos, as matrizes canônicas, FR-016a e FR-019 a FR-023 da 002 e o "Não inclui" da linha ORG
  do roadmap; tratar P0/P1 pelo fluxo de findings
- [x] T059 (coordenador) Gate visual: `impeccable critique` nas telas de `/organizacao/` como
  `administrador-sistema` e em `/senha/` nos dois estados, depois do `code-reviewer`; encaminhar ao
  `frontend-implementer` só os findings aprovados
- [x] T060 (coordenador) Atualizar `DESIGN.md` e `.impeccable/design.json` por `impeccable document`
  (modo scan) com os padrões novos (bloco de exibição única da senha, lista de papéis com estado
  bloqueado, prévia de efeitos); conferir contra `static/css/components.css`,
  `contas/static/contas/css/` e os templates
- [x] T061 (coordenador) `/speckit-converge`; manter a anotação de ORG no `ROADMAP.md` fiel ao
  estado da implementação e, depois do merge em `main`, marcar ORG como concluída

---

## Dependencies & Execution Order

- Setup (T001–T002) → Foundational (T003–T016) → US1 (T017–T025) → US2 (T026–T030) → US3, US4, US5,
  US6, US7 → Polish (T055–T061).
- Dentro de cada story: testes → domínio (`organizacao.py`, `credenciais.py`) → forms/views/urls →
  templates.
- Foundational: T008 antes de T009–T011; T011 antes de T012–T014; T013 antes de T016.
- US1 é base de todas: as outras usam `cadastrar_usuario`, a ficha e o middleware.
- US2 vem antes de US3–US7 porque elas acrescentam ações às fichas e listas de US2.
- US7 depende da designação da US4 (cenários 3 e 7). US3, US4, US5 e US6 são independentes entre
  si no domínio, mas compartilham `contas/organizacao.py`, `contas/forms.py`, `contas/views.py`,
  `contas/urls.py`, `tests/test_contas_views_organizacao.py`,
  `tests/test_contas_permissoes_organizacao.py` e `tests/test_contas_concorrencia.py`: nesses
  arquivos as tasks são sequenciais.

## Parallel Opportunities

- Foundational: T004–T007 juntos; T014 e T015 juntos depois de T011.
- US1: T017–T019 juntos.
- US2: T026 e T027 juntos.
- Em cada uma de US3–US7, as duas tasks de teste juntas.
- Testes de uma story podem ser escritos enquanto o domínio da anterior é implementado, desde que em
  arquivos diferentes (`test_contas_operacoes_chefia.py`, `_situacao.py`, `_setor.py`).
- T055 e T056 juntos.

## Parallel Example: User Story 1

```text
Task: "(test-engineer) tests/test_contas_operacoes_usuario.py (cadastro)"
Task: "(test-engineer) tests/test_contas_credenciais.py (provisória, vencimento, middleware, definição)"
Task: "(test-engineer) tests/test_contas_views_organizacao.py e test_contas_permissoes_organizacao.py (cadastro, ficha)"
```

## Implementation Strategy

1. **MVP**: Setup + Foundational + US1. O administrador cadastra pessoas sem o caminho técnico, e
   cada uma define a própria senha. A Foundational sozinha já entrega a proteção das invariantes no
   banco e o Admin somente leitura.
2. US2 (consulta), depois US3 a US7 na ordem de prioridade; US4 antes de US7.
3. Polish: review, gate visual, `DESIGN.md`, converge.
4. Pipeline de segurança e permissões em cada etapa crítica: `test-engineer` → `task-implementer` →
   `frontend-implementer` → `code-reviewer`. Não considerar concluída uma etapa em que só o happy
   path passa.

## Phase 11: Convergence

- [x] T062 Acrescentar caminho às recusas de nome de setor repetido (`criar_setor`/`renomear_setor`) e de matrícula repetida na edição (`editar_usuario`) em `contas/organizacao.py` per FR-048 (partial)
