---

description: "Task list for implementing 002-autenticacao-login"
---

# Tasks: Fundação de Autenticação e Login

**Input**: Design documents from `specs/002-autenticacao-login/` (`spec.md`, `plan.md`, `research.md`,
`data-model.md`, `contracts/protecao-e-redirecionamento.md`, `quickstart.md`)

**Prerequisites**: `plan.md` (aprovado, duas rodadas de correção técnica), `spec.md` (4 user
stories priorizadas), `research.md` (16 decisões técnicas fechadas — nenhuma reaberta aqui),
`data-model.md`, `contracts/protecao-e-redirecionamento.md`.

**Tests**: incluídos em todas as fases aplicáveis — a Constitution (Princípio VII) exige testes
como parte da implementação; não são opcionais nesta feature.

**Organização**: 8 fases, conforme estrutura definida para esta feature — Fundação técnica →
Fundação de dados/autenticação → US1 (Login) → US2 (Proteção e retorno seguro) → US3 (Identidade,
setor e papéis) → US4 (Logout) → UI e integração final → Validação e hardening. Esta organização
substitui, para esta feature, o padrão genérico de 5 fases do template do Spec Kit — segue a
divisão explicitamente definida no `plan.md`/pedido do usuário, sem alterar nenhuma decisão de
`research.md`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tasks incompletas)
- **[Story]**: US1/US2/US3/US4 — só em tasks de fase de story; ausente em Setup/Foundational/Polish
- Caminho de arquivo exato incluído em cada task

## Path Conventions

Projeto Django monolítico, apps na raiz do repositório (primeiro app do projeto — sem `apps/`
aninhado). Testes em `tests/` (diretório único já existente, convenção do projeto — sem
`contas/tests/`).

---

## Phase 1: Fundação técnica (Setup)

**Purpose**: infraestrutura de projeto que precisa existir antes de qualquer modelo/view desta
feature — sem nenhuma funcionalidade de user story aqui.

- [X] T001 Criar o app Django `contas` na raiz do repositório (`contas/__init__.py`,
  `contas/apps.py` com `ContasConfig`) — sem models/views ainda.
- [X] T002 Registrar `"contas"` em `INSTALLED_APPS` em `config/settings/base.py`.
- [X] T003 Configurar `AUTH_USER_MODEL = "contas.User"` em `config/settings/base.py` — precisa
  estar em vigor antes da primeira migration (T013), mas pode ser escrito agora mesmo antes de
  `contas.models.User` existir (Django resolve a referência de forma tardia).
- [X] T004 Configurar `LOGIN_URL = "login"`, `LOGIN_REDIRECT_URL = "home"`,
  `LOGOUT_REDIRECT_URL = "login"` em `config/settings/base.py`.
- [X] T005 Adicionar `STATICFILES_DIRS = [BASE_DIR / "static"]` em `config/settings/base.py`
  (ausente hoje; necessário para os tokens CSS de projeto em `static/css/`).
- [X] T006 [P] Criar `static/css/tokens.css` com os tokens de `DESIGN.md` → Colors/Typography
  (ex.: `--color-primary: #2F5D8A`, `--color-background: #F7F8FA`, `--color-surface: #FFFFFF`,
  `--color-border: #D7DBE0`, `--color-danger: #B3261E`, `--color-focus`, escala tipográfica e de
  espaçamento base 4px) — valores marcados em `DESIGN.md` como *initial design value*.
- [X] T007 [P] Criar `static/css/base.css` com reset mínimo e estilos globais compartilhados
  (fonte de sistema conforme `DESIGN.md` → Typography, `box-sizing`, anel de foco visível em todo
  controle interativo — nunca removido).

**Checkpoint**: infraestrutura de projeto pronta. Nenhum código de domínio ainda existe.

---

## Phase 2: Fundação de dados/autenticação (Foundational — bloqueia todas as user stories)

**Purpose**: base estrutural compartilhada (`User`, `Setor`, `Papel`, `PapelUsuario`) exigida por
todas as histórias seguintes.

**⚠️ CRÍTICO**: nenhuma user story pode começar antes desta fase estar completa.

- [X] T008 Criar `Setor` em `contas/models.py`: `nome = models.CharField(blank=False)` — **sem
  `max_length`** (nenhuma fonte normativa define limite de tamanho para nome de setor; o backend é
  exclusivamente PostgreSQL, que suporta `CharField` sem `max_length` — `supports_unlimited_charfield`
  — então nenhum limite arbitrário é inventado só para satisfazer o campo) e **obrigatório, sem
  `unique=True`** (nenhuma fonte normativa exige nome de setor único — `research.md`, R4/correção);
  `ativo = models.BooleanField(default=True)`. Sem campo `chefe` (chefia é derivada de
  `PapelUsuario`, não uma coluna própria). Sem código/identificador de setor inventado.
- [X] T009 Criar `UserManager(BaseUserManager)` em `contas/models.py` com `create_user(matricula,
  password=None, setor=None, **extra_fields)` e `create_superuser(matricula, password=None,
  setor=None, **extra_fields)` (forçando `is_staff=True`, `is_superuser=True`), seguindo o padrão
  documentado do Django para modelo de usuário customizado. Depende de T008 (referencia `Setor`).
- [X] T010 Criar `User(AbstractBaseUser, PermissionsMixin)` em `contas/models.py`:
  `matricula = models.CharField(max_length=32, unique=True, verbose_name="matrícula")` como
  `USERNAME_FIELD` (texto opaco — nunca numérico, sem máscara/regex, `max_length=32` é limite
  técnico de sanidade, não regra de formato); `is_active = models.BooleanField(default=True)`;
  `is_staff = models.BooleanField(default=False)`;
  `setor = models.ForeignKey("contas.Setor", on_delete=models.PROTECT)` **obrigatório**
  (`INV-ORG-001`); `REQUIRED_FIELDS = ["setor"]`; `objects = UserManager()`; método
  `tem_papel(self, *codigos: str) -> bool` retornando
  `self.papeis.filter(papel__in=codigos).exists()`. Depende de T009 (mesmo arquivo — sequencial).
- [X] T011 Criar `Papel(models.TextChoices)` em `contas/models.py` com os 7 membros e `value`
  idêntico ao ID canônico de `docs/domain/permissions-matrix.md`: `REQUISITANTE = "ROLE-REQUESTER"`,
  `AUXILIAR_SETOR = "ROLE-SECTOR-ASSISTANT"`, `CHEFE_SETOR = "ROLE-SECTOR-HEAD"`,
  `FUNCIONARIO_ALMOXARIFADO = "ROLE-WAREHOUSE-STAFF"`,
  `CHEFE_ALMOXARIFADO = "ROLE-WAREHOUSE-HEAD"`, `AUDITOR = "ROLE-AUDITOR"`,
  `ADMINISTRADOR_SISTEMA = "ROLE-SYSTEM-ADMIN"` — catálogo fechado, não redefinido, não é tabela.
  Depende de T010 (mesmo arquivo — sequencial).
- [X] T012 Criar `PapelUsuario` em `contas/models.py`:
  `usuario = models.ForeignKey("contas.User", related_name="papeis", on_delete=models.CASCADE)`;
  `papel = models.CharField(max_length=32, choices=Papel.choices)`; `Meta.constraints =
  [models.UniqueConstraint(fields=["usuario", "papel"], name="papelusuario_unico_usuario_papel")]`
  (forma moderna — **não** `unique_together`). Depende de T011 (mesmo arquivo — sequencial).
- [X] T013 Gerar a migration inicial: `python manage.py makemigrations contas`, produzindo
  `contas/migrations/0001_initial.py` (User, Setor, PapelUsuario numa única migration — momento
  mais seguro do projeto, zero migrations preexistentes). Depende de T003, T008–T012.
- [X] T014 Configurar `contas/admin.py` para o Admin nativo do Django operar sobre `contas.User`
  (que deriva de `AbstractBaseUser + PermissionsMixin`, com `matricula` como `USERNAME_FIELD` —
  **não** é o `User` padrão do Django, então `UserCreationForm`/`UserChangeForm` de
  `django.contrib.auth.forms` **não podem ser usados diretamente**, pois pressupõem os campos do
  `User` padrão). Definir, junto da própria configuração administrativa em `contas/admin.py` (sem
  criar `contas/forms.py` nem qualquer camada de forms de produto — isto é forms exclusivos do
  Admin, para bootstrap/manutenção técnica):
  - um form de criação e um form de alteração compatíveis com `contas.User` (por exemplo,
    subclasses mínimas de `UserCreationForm`/`UserChangeForm` com `Meta.model = get_user_model()`
    e `Meta.fields` ajustados a `matricula`, ou solução igualmente mínima e correta), garantindo
    que a criação via Admin define a senha usando `set_password()`/os mecanismos próprios do
    Django — **nunca** salvando senha crua;
  - um `UserAdmin` (`admin.ModelAdmin` ou subclasse mínima do `UserAdmin` nativo) usando esses
    forms, com `fieldsets`/`add_fieldsets` mostrando matrícula, senha, setor, `is_active`,
    `is_staff`, `is_superuser` — sem conceder nenhum `Papel` (`ROLE-*`) automaticamente nessa
    tela;
  - `SetorAdmin` simples (`list_display=["nome", "ativo"]`);
  - `PapelUsuario` como inline do `UserAdmin` (ou admin próprio) — atribuição explícita, nunca
    implícita.
  Ferramenta técnica de bootstrap/manutenção — não é tela de administração de produto nem uma nova
  specification implícita; `is_staff`/`is_superuser` continuam técnicos e distintos de
  `ROLE-SYSTEM-ADMIN`. Depende de T010–T012.
- [X] T015 [P] Criar `tests/test_contas_models.py` cobrindo: matrícula preservada exatamente como
  fornecida, incluindo zeros à esquerda, nunca convertida para número; matrícula duplicada rejeitada
  no banco (`IntegrityError`, `unique=True`); usuário sem `setor` não pode ser criado; usuário pode
  ter múltiplos `PapelUsuario` distintos simultaneamente; atribuição duplicada do mesmo papel ao
  mesmo usuário é rejeitada pela `UniqueConstraint`; `tem_papel()` retorna somente os papéis
  explicitamente atribuídos, sem herança implícita entre eles. Depende de T013 (precisa de
  migrations aplicadas). Paralelizável com T014 (arquivo distinto, sem dependência semântica).

**Checkpoint**: fundação de dados pronta e testada. Nenhuma user story ainda entrega valor
observável (não há login/rota alguma).

---

## Phase 3: User Story 1 — Entrar no sistema com credenciais válidas (Priority: P1) 🎯 MVP

**Goal**: matrícula + senha → autenticação → sessão → Home autenticada mínima.

**Independent Test**: com um usuário ativo já cadastrado (via fixture/ORM), acessar `/login/`,
enviar credenciais válidas e verificar acesso à Home; credenciais inválidas (senha errada,
matrícula inexistente, conta inativa) recebem a mesma mensagem genérica.

> Nesta fase, a rota `login` usa o `LoginView` **nativo** do Django (sem subclasse) — a resolução
> segura de `next` (checagem de existência via `resolve()`, marcador de sessão, fallback via
> middleware) é introduzida na Phase 4 (US2), que é onde `WMSLoginView` passa a existir. O
> `LoginView` nativo já resolve corretamente o caso comum de `next` interno (checagem de host já é
> nativa), então parte do comportamento de US2 já aparece "de graça" aqui — isso é esperado e não é
> uma antecipação de escopo.

### Testes (User Story 1)

- [X] T016 [P] [US1] Criar `tests/test_contas_auth.py` cobrindo: matrícula + senha válidas
  autentica; senha inválida recusa com mensagem genérica; matrícula inexistente recusa com a mesma
  mensagem; usuário inativo recusa com a mesma mensagem; as três recusas produzem exatamente a
  mesma string de erro (comparação direta); sessão persiste entre requisições subsequentes; usuário
  já autenticado que acessa `GET /login/` é redirecionado para a Home. Depende de T010 (modelo);
  espera-se que falhe até a Implementação desta fase existir.
- [X] T017 [P] [US1] Criar `tests/test_contas_home.py` cobrindo: visitante anônimo que acessa `/`
  é redirecionado ao login (não recebe o conteúdo); renderização básica da Home para usuário
  autenticado (200, template correto); renderização básica do login (200, campos de matrícula e
  senha presentes); mensagem de erro genérica aparece no HTML de uma tentativa de login inválida.
  Depende de T010; paralelizável com T016 (arquivo distinto).

### Implementação (User Story 1)

- [X] T018 [US1] Criar `HomeView(LoginRequiredMixin, TemplateView)` em `contas/views.py`,
  `template_name="contas/home.html"` — usa `LoginRequiredMixin` nativo, sem wrapper próprio
  (`contas/auth.py` não existe).
- [X] T019 [US1] Criar `contas/urls.py` com as rotas `login`
  (`django.contrib.auth.views.LoginView.as_view(template_name="contas/login.html",
  redirect_authenticated_user=True)`, nome `"login"`) e `home` (`HomeView.as_view()`, nome
  `"home"`); incluir via `path("", include("contas.urls"))` em `config/urls.py`. **Sem
  `handler403`**. Depende de T018.
- [X] T020 [P] [US1] Criar `contas/templates/contas/base.html` (estrutura HTML mínima; `<link>`
  para os CSS globais `static/css/tokens.css` e `static/css/base.css`; um bloco
  `{% block extra_css %}{% endblock %}` logo após esses `<link>`s, para que cada página carregue
  seu próprio CSS específico sem duplicar os links globais; bloco de conteúdo) e
  `contas/templates/contas/login.html` (estende `base.html`; preenche `{% block extra_css %}` com
  `<link rel="stylesheet" href="{% static 'contas/css/login.css' %}">` para carregar o CSS criado
  em T022; formulário `POST` com `{% csrf_token %}`; campos do `AuthenticationForm` nativo —
  matrícula e senha, sem `contas/forms.py`; mensagem de erro genérica quando `form.errors`; ação
  primária "Entrar"; layout mobile-first, coluna única, conforme `DESIGN.md` → Inputs/Buttons).
- [X] T021 [P] [US1] Criar `contas/templates/contas/home.html` (estende `base.html`; preenche
  `{% block extra_css %}` com `<link rel="stylesheet" href="{% static 'contas/css/home.css' %}">`
  para carregar o CSS criado em T023, usando o mesmo mecanismo de `base.html` — sem duplicar os
  links globais; confirmação mínima de sessão ativa — ex.: matrícula autenticada; sem sidebar
  completa, sem menu de features futuras, sem KPI, sem catálogo/importação SCPI; espaço reservado
  para a ação de logout, ligada em T033/Phase 6).
- [X] T022 [P] [US1] Criar `contas/static/contas/css/login.css` (layout centralizado, coluna
  única, campos ocupando a largura do container em telas estreitas, foco sempre visível, nenhuma
  ação dependente de hover, usando os tokens de `static/css/tokens.css`).
- [X] T023 [P] [US1] Criar `contas/static/contas/css/home.css` (superfície mínima e neutra, mesma
  fundação de tokens que `login.css`).

**Checkpoint**: User Story 1 funcional e testável isoladamente — **Foundation + US1 = MVP**.

---

## Phase 4: User Story 2 — Impedir acesso não autenticado a superfícies protegidas (Priority: P2)

**Goal**: retorno seguro ao destino original pós-login (interno + existente + autorizado), com
fallback para a Home mínima em qualquer outra condição, sem marcador na URL e sem `handler403`
global.

**Independent Test**: sem sessão, acessar diretamente uma superfície protegida com destino interno
existente e autorizado → após login, retorna a esse destino, sem parâmetro técnico na URL e com o
marcador de sessão consumido; destino externo, inexistente ou não autorizado → cai na Home; um 403
comum fora desse fluxo permanece um 403 comum.

### Testes (User Story 2)

- [X] T024 [P] [US2] Criar urlconf de teste dedicado (ex.: `tests/urls_test_permission_denied.py`)
  com uma view fictícia protegida por `login_required` que sempre levanta
  `django.core.exceptions.PermissionDenied` — usado via `@pytest.mark.urls(...)` pelos testes de
  T025. Não é código de produção; vive só em `tests/`.
- [X] T025 [US2] Criar `tests/test_contas_protected_access.py` cobrindo: visitante não autenticado
  é enviado ao login com `next` apontando para o destino original; destino interno, existente e
  autorizado retorna corretamente após login, a URL final não contém nenhum parâmetro técnico de
  retorno, e a chave de sessão do destino pendente deixa de existir após a primeira requisição
  subsequente; destino interno, existente, mas não autorizado (view de T024) — a primeira
  requisição imediatamente pós-login para esse destino levanta `PermissionDenied` e cai na Home;
  a mesma URL não autorizada acessada de novo depois, fora do fluxo de login, mostra o 403 padrão
  do Django; adicionar manualmente `?_retorno_pos_login=1` a essa mesma URL não muda nada — continua
  403 normal; destino legítimo com query string (ex.: `/algum-destino/?pagina=2`) é reconhecido
  como existente (`resolve()` recebe só o path) e a query é preservada no redirect final; destino
  externo (`next` manipulado) continua rejeitado, cai na Home; destino inexistente (não resolve a
  nenhuma rota) continua caindo na Home; **cenário crítico** — login válido → usuário é desativado
  (`is_active=False`) → a próxima requisição a uma superfície protegida (`HomeView`, de T018) nega
  o acesso/redireciona ao login, sem exigir logout explícito antes e sem nenhum wrapper próprio
  (comportamento nativo de `ModelBackend.get_user()`/`AuthenticationMiddleware`, `research.md` R9).
  Depende de T017 (Home protegida), T018–T019 e T024.

### Implementação (User Story 2)

- [X] T026 [US2] Criar `WMSLoginView(LoginView)` em `contas/views.py`: `get_redirect_url()`
  sobrescrito para, após a checagem nativa de host/esquema, extrair `caminho =
  urlsplit(url).path` e chamar `resolve(caminho)` (**nunca** `resolve()` com a URL completa —
  quebraria com query string), retornando `""` (cai no padrão) se levantar `Resolver404`, ou a
  URL completa (path + query preservados) se existir; `get_success_url()` sobrescrito para gravar
  `self.request.session["_retorno_pos_login_destino"] = url` quando há um destino não-padrão
  válido, e retornar `self.get_default_redirect_url()` caso contrário. Nenhum
  `contas/forms.py`; usa `AuthenticationForm` nativo.
- [X] T027 [US2] Atualizar `contas/urls.py`: a rota `login` passa a usar
  `WMSLoginView.as_view(template_name="contas/login.html", redirect_authenticated_user=True)` em
  vez do `LoginView` nativo (mesmo template/kwargs de T019). Depende de T026.
- [X] T028 [US2] Criar `contas/middleware.py` com `RetornoPosLoginMiddleware`: `process_view(self,
  request, view_func, view_args, view_kwargs)` lê `request.session.get("_retorno_pos_login_destino")`
  e, se existir e for **exatamente igual** a `request.get_full_path()`, remove a chave da sessão
  (`del`) e define `request._retorno_pos_login = True`; caso não bata, não faz nada (marcador
  permanece pendente). `process_exception(self, request, exception)` retorna
  `redirect("home")` somente se `isinstance(exception, PermissionDenied)` **e**
  `getattr(request, "_retorno_pos_login", False)`; caso contrário retorna `None`. Sem nonce, sem
  model/tabela, sem cache/Redis, sem TTL próprio, sem parâmetro de URL.
- [X] T029 [US2] Registrar `"contas.middleware.RetornoPosLoginMiddleware"` em `MIDDLEWARE`
  (`config/settings/base.py`), após `"django.contrib.auth.middleware.AuthenticationMiddleware"`.
  Depende de T028.

**Checkpoint**: User Story 2 funcional e testável isoladamente, integrada a US1 sem quebrá-la.

---

## Phase 5: User Story 3 — Identificar usuário autenticado e papel aplicável (Priority: P3)

**Goal**: provar, através de uma sessão autenticada real (não só no nível de model), o contrato que
`001-importacao-catalogo-materiais` e demais features poderão consumir: `request.user`, setor
obrigatório, papéis explicitamente atribuídos, `tem_papel()`, ausência de herança implícita.

**Independent Test**: autenticar usuários com um papel único e com múltiplos papéis (cenário do
chefe do almoxarifado) e verificar, via `request.user` pós-login, que setor e papéis batem
exatamente com o que foi atribuído — nada a mais, nada a menos.

> A camada de dados (`User`/`Setor`/`Papel`/`PapelUsuario`/`tem_papel()`) já foi construída e
> testada no nível de model na Phase 2 (T008–T015). O que falta aqui é a prova de que esse contrato
> se sustenta através de uma sessão autenticada real — por isso esta fase depende de US1 (login
> funcionando), não só da Foundation. **Não implementa autorização da feature 001.**

### Testes (User Story 3)

- [X] T030 [US3] Estender `tests/test_contas_auth.py` (criado em T016) com os cenários de
  identificação da User Story 3: usuário autenticado com um único papel atribuído — `tem_papel()`
  reflete exatamente esse papel, sem herança de nenhum outro; usuário autenticado com múltiplos
  papéis simultâneos (ex.: `ROLE-WAREHOUSE-STAFF` + `ROLE-SECTOR-HEAD` + `ROLE-WAREHOUSE-HEAD`,
  cenário do chefe do almoxarifado) — todos os papéis explicitamente atribuídos são identificáveis
  via `request.user.papeis.all()`/`tem_papel()`, e nenhum concede implicitamente a capacidade de
  outro; usuário autenticado expõe exatamente um `Setor` via `request.user.setor`, nunca `None`
  (`INV-ORG-001`). Depende de T010–T012 (modelo) e de T016/T018/T019 (login/sessão funcionando via
  US1) — **não depende de T026–T027 nem de nenhuma peça de US2** (middleware, retorno seguro):
  basta autenticar e ler `request.user`, o que já funciona com o `LoginView` nativo usado por US1.

**Checkpoint**: contrato de identidade/papel/setor provado ponta a ponta — pronto para ser
consumido pela feature 001 quando ela for implementada (nada disso é construído aqui).

---

## Phase 6: User Story 4 — Encerrar a sessão (Priority: P4)

**Goal**: logout explícito, `POST`-only, funcionando com ou sem sessão válida, sempre terminando em
`/login/`.

**Independent Test**: autenticado, `POST /logout/` encerra a sessão e redireciona para `/login/`;
uma nova tentativa de acessar superfície protegida exige autenticação novamente; `POST /logout/`
sem sessão válida também redireciona para `/login/`, sem erro.

### Testes (User Story 4)

- [X] T031 [P] [US4] Criar `tests/test_contas_logout.py` cobrindo: logout com sessão válida
  encerra a sessão e redireciona para `/login/`; nova tentativa de acessar superfície protegida com
  a mesma sessão exige autenticação novamente; logout **sem** sessão válida também redireciona para
  `/login/`, como no-op seguro, sem erro, sem exceção, sem revelar se havia ou não sessão. Depende
  de T018 (Home protegida).

### Implementação (User Story 4)

- [X] T032 [US4] Adicionar a rota `logout` a `contas/urls.py`:
  `path("logout/", django.contrib.auth.views.LogoutView.as_view(), name="logout")` — `LogoutView`
  **nativo, sem subclasse** (nenhum override necessário; `LOGOUT_REDIRECT_URL="login"` de T004 já
  entrega `FR-017a`).
- [X] T033 [P] [US4] Editar `contas/templates/contas/home.html` (de T021) para incluir o
  formulário de logout: `<form method="post" action="{% url 'logout' %}">{% csrf_token %}<button
  type="submit">Sair</button></form>` — `POST` obrigatório, nunca um link `GET`.

**Checkpoint**: ciclo completo login → sessão → proteção → retorno seguro → identidade → logout
fechado e testável.

---

## Phase 7: UI e integração final

**Purpose**: só refinamentos que atravessam mais de uma story — arquivos de UI já foram
distribuídos nas fases correspondentes (T006, T007, T020–T023, T033); nada de visual fica
pendente até aqui.

- [X] T034 [P] Revisar em conjunto `contas/templates/contas/{login,home}.html` e
  `contas/static/contas/css/{login,home}.css` quanto à coerência com `DESIGN.md`: tokens
  consistentes entre as duas páginas, nenhuma ação dependente de hover, comportamento responsivo
  aceitável em celular/tablet/desktop (mobile-first, conforme `DESIGN.md` → Layout). Ajustar CSS
  existente se necessário. **Não** introduzir sidebar/app-shell completo — decisões de largura de
  sidebar (desktop) e navegação (mobile) permanecem abertas em `DESIGN.md` e não são resolvidas
  aqui.

---

## Phase 8: Validação e hardening

**Purpose**: confirmar que o todo funciona e que nenhuma decisão do plano foi violada — sem
corrigir aqui nada que devesse ter sido parte de uma story anterior.

- [X] T035 Rodar `uv run pytest tests/` e confirmar 100% dos testes passando, incluindo os cinco
  arquivos desta feature (`test_contas_models.py`, `test_contas_auth.py`,
  `test_contas_protected_access.py`, `test_contas_logout.py`, `test_contas_home.py`) e os testes
  pré-existentes (`test_infrastructure.py`, `test_settings.py`) sem regressão.
- [X] T036 [P] Rodar `python manage.py makemigrations --check --dry-run` e confirmar que não há
  migrations pendentes além de `contas/migrations/0001_initial.py`.
- [X] T037 [P] Rodar `python manage.py check` (system checks do Django) e confirmar ausência de
  erros/avisos relevantes.
- [X] T038 Executar manualmente o roteiro completo de `quickstart.md`: `migrate` → criar o primeiro
  `Setor` via shell → `createsuperuser` informando esse `Setor` → usar o Django Admin para demais
  setores/usuários/papéis → validar login, proteção, retorno seguro (com e sem query string),
  desativação em sessão e logout.
- [X] T039 [P] Confirmar ausência de nova dependência: `git diff -- pyproject.toml uv.lock` não
  deve apresentar nenhuma alteração introduzida por esta feature.
- [X] T040 Revisão cruzada final contra `spec.md`, `docs/domain/invariants-matrix.md` e
  `docs/domain/permissions-matrix.md`: confirmar que todo FR/SC da spec tem cobertura de teste ou
  comportamento nativo documentado (usar a tabela de rastreamento de `data-model.md`), que
  `INV-AUTH-001`/`INV-ORG-001` permanecem preservadas, que o catálogo de papéis não foi redefinido,
  e que o contrato de `contracts/protecao-e-redirecionamento.md` está pronto para
  `001-importacao-catalogo-materiais` consumir — sem implementar nada dessa feature aqui.

---

## Dependencies & Execution Order

### Dependências entre fases

- **Phase 1 (Setup)**: sem dependências — pode começar imediatamente.
- **Phase 2 (Foundational)**: depende da Phase 1 (precisa de `AUTH_USER_MODEL` configurado antes
  de gerar a migration, T003→T013) — **bloqueia todas as user stories**.
- **Phase 3 (US1)**: depende só da Phase 2. Não depende de US2/US3/US4.
- **Phase 4 (US2)**: depende da Phase 2 **e** da Phase 3 — precisa de `HomeView`/rota `login`
  já existentes (protege e estende o que US1 criou; `WMSLoginView` substitui o `LoginView` nativo
  usado por US1 na mesma rota).
- **Phase 5 (US3)**: depende da Phase 2 (dados) **e** da Phase 3 (login funcionando) — não depende
  de US2 nem de US4.
- **Phase 6 (US4)**: depende da Phase 3 (precisa de `HomeView`/template existentes). Não depende de
  US2 nem de US3.
- **Phase 7 (Polish)**: depende de US1 e US4 (revisa `login.html`+`home.html` já com o botão de
  logout).
- **Phase 8 (Validação)**: depende de todas as fases anteriores.

### Independência real entre user stories

- **US1** é a única pré-condição dura para US2, US3 e US4 (todas precisam de login/Home
  existentes). US2, US3 e US4 **não dependem umas das outras** e podem ser feitas em qualquer
  ordem entre si depois de US1 — a ordem US2→US3→US4 sugerida no pedido é conceitualmente
  conveniente (retorno seguro antes de fechar identidade e logout), mas não é uma dependência
  técnica rígida.
- Isso difere ligeiramente da suposição inicial de "toda story só depende da Foundation": aqui,
  **Phase 2 sozinha não basta** para US2/US3/US4 — todas herdam uma dependência adicional de US1
  (Phase 3), porque a rota de login e a Home protegida são o ponto de extensão que essas stories
  usam. Documentado aqui conforme pedido, sem alterar a arquitetura do `plan.md`.

### Paralelismo seguro

- T006/T007 (Phase 1): arquivos CSS distintos, paralelos entre si.
- T015 (Phase 2, teste de models) é paralelo a T014 (admin.py) — arquivos distintos, sem
  dependência semântica entre os dois.
- T016/T017 (Phase 3, testes) são paralelos entre si — arquivos distintos.
- T020/T021/T022/T023 (Phase 3, templates/CSS) são todos paralelos entre si — quatro arquivos
  distintos, nenhum edita o mesmo arquivo que outro.
- T024 (Phase 4, urlconf de teste) é paralelo a qualquer task de outra fase que não dependa dele;
  T025 depende de T024 (mesma fase, não paralelo a ele).
- T031 e T034 **não são paralelas**: Phase 7 é posterior à Phase 6 (US4) por definição — T034
  revisa `login.html`/`home.html` já com o formulário de logout de T033 presente. Diferença de
  arquivo imediato entre duas tasks não é, por si só, motivo para marcá-las como paralelas quando
  uma fase inteira só faz sentido depois da outra.
- **Nunca paralelas**: T008→T009→T010→T011→T012 (todas em `contas/models.py`); T026 e qualquer
  outra edição de `contas/views.py`; T019/T027/T032 (todas em `contas/urls.py`, em momentos
  diferentes do tempo, não simultâneas).

---

## Parallel Example: Phase 3 (US1)

```bash
# Testes em paralelo:
Task: "Criar tests/test_contas_auth.py (T016)"
Task: "Criar tests/test_contas_home.py (T017)"

# Templates e CSS em paralelo, depois da implementação (T018/T019):
Task: "Criar contas/templates/contas/base.html + login.html (T020)"
Task: "Criar contas/templates/contas/home.html (T021)"
Task: "Criar contas/static/contas/css/login.css (T022)"
Task: "Criar contas/static/contas/css/home.css (T023)"
```

---

## Implementation Strategy

### MVP primeiro (Foundation + US1)

1. Completar Phase 1 (Setup).
2. Completar Phase 2 (Foundational — bloqueante).
3. Completar Phase 3 (US1).
4. **Parar e validar**: usuário existente → matrícula + senha → autenticação → sessão → Home
   mínima, testável de forma isolada (T016/T017 passando).

### Entrega incremental

1. Setup + Foundational → fundação pronta.
2. + US1 → login funcional → **MVP demonstrável**.
3. + US2 → retorno seguro/proteção robusta (URL manipulada, query string, conta desativada).
4. + US3 → contrato de identidade/papel/setor provado ponta a ponta para a feature 001 consumir.
5. + US4 → ciclo fechado com logout.
6. Phase 7 → coerência visual final. Phase 8 → validação/hardening.

Cada incremento soma valor sem quebrar o anterior.

---

## Rastreamento (FR/SC → tasks, resumo)

| Requisito | Task(s) | Mecanismo |
|---|---|---|
| FR-001, FR-001a, FR-001b | T010, T020 | `User.matricula` (`USERNAME_FIELD`, opaco, único) |
| FR-002, FR-003, FR-004, FR-007 | T016 (teste) | `ModelBackend`/`AuthenticationForm` nativos |
| FR-005 | T016 (teste) | Sessão padrão do Django |
| FR-005a | T018, T019, T021 | `HomeView` + rota `home` |
| FR-006, `INV-AUTH-001` | T025 (teste) | `ModelBackend.get_user()` nativo (`research.md` R9) |
| FR-008, FR-009 | T018 (`LoginRequiredMixin`), T017/T025 (testes) | nativo |
| FR-010, FR-010a, FR-011 | T026, T028, T029, T025 (teste) | `WMSLoginView` + `RetornoPosLoginMiddleware` |
| FR-012 | T019/T027 (`redirect_authenticated_user`) | nativo |
| FR-013, FR-014, FR-015, FR-016, `INV-ORG-001` | T010–T012, T030 (teste) | `User`/`Setor`/`Papel`/`PapelUsuario` |
| FR-017, FR-017a, FR-018 | T032, T004, T031 (teste) | `LogoutView` nativo + `LOGOUT_REDIRECT_URL` |

---

## Notes

- `[P]` = arquivos diferentes, sem dependência entre si.
- `[US#]` mapeia a task à user story correspondente para rastreabilidade.
- Nenhuma decisão de `research.md` foi reaberta: sem `contas/auth.py`, sem `contas/forms.py`, sem
  `WMSLogoutView`, sem `handler403`, sem marcador de retorno em query string, sem `unique=True` em
  `Setor.nome`, sem `Group`/`Permission` como catálogo de papéis, sem nova dependência.
- Verificar que os testes falham antes da implementação correspondente, quando escritos primeiro.
- Parar em qualquer checkpoint de fase para validar a story isoladamente.
