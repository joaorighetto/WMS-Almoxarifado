# Implementation Plan: Fundação de Autenticação e Login

**Branch**: `002-autenticacao-login` (branch de trabalho local: `worktree-002-autenticacao-login`;
não há branch dedicada pelo Spec Kit — ver `spec.md`) | **Date**: 2026-09-19 | **Spec**:
[spec.md](./spec.md)

**Input**: Feature specification from `specs/002-autenticacao-login/spec.md`

## Summary

Entregar login por matrícula funcional + senha, proteção de superfícies autenticadas com retorno
seguro ao destino original (ou fallback para uma Home autenticada mínima), identificação de usuário
e papel(is) consultável por outras features, e logout — usando exclusivamente mecanismos nativos e
maduros do Django (modelo de usuário customizado, `ModelBackend`/`AuthenticationForm`,
`LoginView`/`LogoutView`, `login_required`/`LoginRequiredMixin`, sessões padrão), sem nenhuma
dependência nova e sem nenhuma camada de abstração própria de autenticação. É a primeira feature a
introduzir código de produção no projeto — decide agora o modelo de usuário (`AUTH_USER_MODEL`)
porque este é o único momento em que essa troca é segura e barata (nenhuma migration de negócio
existe ainda).

> **Revisão corretiva** (após verificação direta do código-fonte instalado do Django): removida a
> abstração própria de "proteção de superfícies ativas" — o framework já rejeita conta desativada
> em toda requisição subsequente, sem código nenhum. Removido o `handler403` global, substituído
> por um mecanismo restrito ao contexto do retorno pós-login. Removida a unicidade inventada de
> `Setor.nome`. Corrigido o contrato de `logout` (não exige sessão válida). Recheck de simplicidade
> também eliminou abstrações sem responsabilidade real: uma subclasse para rótulo/tamanho do
> login (esses atributos já vêm do model, verificado no código-fonte do `AuthenticationForm`) e
> `WMSLogoutView` (o `LogoutView` nativo já basta, sem nenhum override). Uma revisão posterior
> reintroduziu `contas/forms.py` como subclasse mínima, exclusivamente para corrigir e tornar
> acionável a mensagem traduzida de recusa. Ver `research.md`
> (R3, R7, R8, R9) e "Correções realizadas" no relatório desta revisão para o detalhe completo.
>
> **Segunda revisão corretiva**: o marcador de retorno pós-login deixou de viver na query string
> (`?_retorno_pos_login=1` — controlável pelo cliente, não expirava) e passou a viver em sessão,
> vinculado ao destino exato (path + query) esperado, consumido uma única vez por
> `RetornoPosLoginMiddleware.process_view()` antes da view rodar; `process_exception()` só age
> quando esse consumo aconteceu **nesta mesma requisição**. Corrigido também um bug real: `next`
> com query string (ex.: `/catalogo/?pagina=2`) quebrava `django.urls.resolve()` — confirmado
> empiricamente — e caía incorretamente na Home; agora só o `path` vai para `resolve()`, a URL
> completa (com query) é preservada como destino. `PapelUsuario` passou a usar
> `Meta.constraints`/`UniqueConstraint` em vez de `unique_together`. `quickstart.md` corrigido para
> não presumir Django Admin antes do primeiro superusuário existir. Ver "Correções realizadas" no
> relatório desta revisão.

## Technical Context

**Language/Version**: Python 3.13 (`pyproject.toml`: `requires-python = ">=3.13,<3.14"`), Django
6.1.1 (`pyproject.toml` fixa apenas o piso `django>=5.2`; a versão efetivamente resolvida e travada
em `uv.lock` — verificada nesta revisão — é 6.1.1; todas as afirmações de comportamento de
framework neste plano foram checadas contra essa versão instalada, não presumidas).

**Primary Dependencies**: `django` (apps `auth`, `sessions`, `admin`, `messages`, `contenttypes`,
`staticfiles`, já instalados), `psycopg[binary]` (driver PostgreSQL, já presente). Nenhuma
dependência nova (ver `research.md`, R15).

**Storage**: PostgreSQL (`config/settings/base.py`, já configurado). Sessões via backend padrão do
Django (`django.contrib.sessions`, tabela em banco — nenhum cache/Redis introduzido).

**Testing**: pytest + pytest-django, convenção existente (`tests/` único na raiz,
`DJANGO_SETTINGS_MODULE=config.settings.test`, ver `pyproject.toml`).

**Target Platform**: servidor Linux, aplicação web server-rendered (Django Templates).

**Project Type**: aplicação Django monolítica server-rendered. Não se encaixa nas opções genéricas
do template de plano (não é biblioteca/CLI, nem "frontend separado + backend"); estrutura real
descrita em "Project Structure" abaixo.

**Performance Goals**: nenhuma meta específica definida pela spec. Login é operação pouco frequente
para uma equipe pequena (`PRODUCT.md`: um chefe e poucos funcionários no almoxarifado, demais
funcionários do SAEP como requisitantes eventuais) — sem requisito de throughput dedicado.

**Constraints**: nenhuma restrição de latência/memória específica definida pela spec, além dos
princípios gerais da Constitution (X — performance baseada em evidências: nenhuma consulta N+1 ou
carga de conjunto grande de dados está envolvida nesta feature).

**Scale/Scope**: dezenas de contas (equipe do almoxarifado + funcionários do SAEP como
requisitantes), um único almoxarifado físico (`PRODUCT.md`, Operating Context).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Status | Justificativa |
|---|---|---|
| I. Simplicidade Arquitetural | PASS | Nenhuma camada nova (sem service layer, repository, DTO). Usa `AbstractBaseUser`/`PermissionsMixin`/`LoginView`/`LogoutView`/`ModelBackend`/`login_required`/`LoginRequiredMixin` — todos recursos convencionais do Django. Um único middleware pequeno e de responsabilidade única (`RetornoPosLoginMiddleware`, usando os hooks nativos `process_view`/`process_exception`) para o caso específico de fallback pós-login — não um `handler403` global, sem nonce/model/cache extra além da sessão já existente (ver `research.md`, R8). Único app novo (`contas`), justificado por ser a primeira feature de produto do projeto. A revisão removeu `contas/auth.py` e `WMSLogoutView`; `contas/forms.py` contém somente a mensagem de recusa corrigida, sem campo ou autenticação próprios. |
| II. Arquitetura Server-Driven | PASS | Django Templates puros para login/Home; nenhuma SPA; HTMX deliberadamente não usado por não trazer ganho concreto em fluxos de request/redirect completo (ver `research.md`, R12). |
| III. Integridade de Dados | PASS | `matricula` única garantida por índice único no PostgreSQL; `setor` obrigatório com `on_delete=PROTECT` garante `INV-ORG-001` também em persistência; unicidade de papel por usuário garantida por `UniqueConstraint` (`PapelUsuario.Meta.constraints`, forma moderna equivalente a `unique_together`). Não há operação de escrita concorrente sobre saldo/estoque nesta feature (fora de escopo), então locking/atomicidade de estoque não se aplicam aqui. |
| IV. Rastreabilidade e Auditoria | PASS (mínimo aplicável) | Nenhuma exclusão física é introduzida. Login/logout não geram histórico de negócio (não é uma "operação relevante" de estoque/requisição); a spec não exige log de tentativas de autenticação. Ver Open Questions para uma nota não bloqueante sobre observabilidade. |
| V. Regras de Negócio no Backend | PASS | Toda validação (credenciais, conta ativa, destino seguro, papel) ocorre em `views.py`/`models.py`/mecanismos nativos do Django — nunca em template ou JavaScript. |
| VI. Segurança por Padrão | PASS | CSRF já ativo (`MIDDLEWARE` existente) — inclusive no `POST /logout/` sem sessão, que continua exigindo CSRF válido. Hash de senha via hashers nativos do Django (nenhuma criptografia própria). Sessão gira a chave no login (proteção nativa contra fixação). Mensagem de erro genérica não revela detalhe interno. `LogoutView` aceita só `POST` (verificado: `http_method_names = ["post", "options"]`). Redirecionamento externo bloqueado nativamente (`url_has_allowed_host_and_scheme`); fallback de autorização pós-login restrito por marcador, sem alterar o tratamento de 403 do resto do sistema. |
| VII. Testes como Parte da Implementação | PASS | Estratégia de testes cobre regras de negócio (matrícula/setor/papéis), autenticação, sessão, proteção, logout e UI mínima — ver seção Testes abaixo. |
| VIII. Design System e Interface Operacional Consistente | PASS (com itens documentados em aberto) | Login e Home seguem tokens/cores/tipografia de `DESIGN.md`. Sidebar/app-shell completo **não** é implementado agora, porque `DESIGN.md` deixa largura/colapso (desktop) e navegação (mobile) explicitamente em aberto — a Home usa apenas uma superfície mínima e neutra, sem antecipar essas decisões (ver "Home autenticada mínima" abaixo). |
| IX. Progressive Enhancement | PASS | Login/logout funcionam via `POST` tradicional, sem exigir JavaScript; o script do login apenas acrescenta estado de envio e bloqueio de duplo clique. |
| X. Performance Baseada em Evidências | PASS | Nenhuma consulta N+1 (usuário/setor/papéis são lookups simples por PK/FK); nenhuma listagem grande envolvida. |
| XI. Dependências com Parcimônia | PASS | Zero dependências novas (ver `research.md`, R15). |
| XII. Manutenibilidade | PASS | Nomes de domínio em português (`matricula`, `Setor`, `Papel`, `PapelUsuario`, `tem_papel`) para conceitos próprios do domínio; campos herdados do Django (`is_active`, `is_staff`, `password`) mantêm o nome nativo do framework — não traduzir contrato do framework, só o que é nosso. |
| XIII. Migrações Seguras | PASS | Uma única migration inicial, no momento mais seguro possível do projeto (zero migrations preexistentes) — ver `research.md`, R14. |
| XIV. Observabilidade | PASS (mínimo aplicável) | Nenhum dado sensível (senha) é logado. Nenhum log de evento de autenticação é adicionado nesta feature — não é exigido por nenhuma FR/SC; ver Open Questions. |

Nenhuma violação identificada. Seção "Complexity Tracking" abaixo permanece vazia por não haver
o que justificar.

## Project Structure

### Documentation (this feature)

```text
specs/002-autenticacao-login/
├── spec.md                          # Já existente
├── plan.md                          # Este arquivo
├── research.md                      # Fase 0 (decisões técnicas — ver acima)
├── data-model.md                    # Fase 1 (entidades)
├── quickstart.md                    # Fase 1 (roteiro de validação)
├── contracts/
│   └── protecao-e-redirecionamento.md   # Contrato interno de rotas/proteção/redirect (sem API REST)
├── checklists/
│   └── requirements.md              # Já existente (checklist de qualidade da spec)
└── tasks.md                         # Fase 2 — gerado por /speckit-tasks, NÃO por este plano
```

### Source Code (repository root)

Estrutura real do projeto (verificada, não hipotética) mais o que esta feature adiciona. Projeto
Django monolítico, apps na raiz do repositório (sem `apps/` aninhado — é o primeiro app):

```text
config/                              # Já existente
├── settings/
│   ├── base.py                      # ALTERADO: AUTH_USER_MODEL, LOGIN_URL, LOGIN_REDIRECT_URL,
│   │                                 #   LOGOUT_REDIRECT_URL, STATICFILES_DIRS, INSTALLED_APPS,
│   │                                 #   MIDDLEWARE += RetornoPosLoginMiddleware
│   ├── development.py               # Sem mudança
│   ├── production.py                # Sem mudança
│   └── test.py                      # Sem mudança
├── urls.py                          # ALTERADO: include("contas.urls") — SEM handler403
└── wsgi.py                          # Sem mudança

contas/                              # NOVO app
├── __init__.py
├── apps.py                          # ContasConfig
├── models.py                        # User, UserManager, Setor, Papel (TextChoices), PapelUsuario
│                                     #   (UniqueConstraint em Meta.constraints, não unique_together)
├── admin.py                         # UserAdmin customizado + SetorAdmin + PapelUsuario inline/admin
├── forms.py                         # AuthenticationForm nativo com apenas a mensagem corrigida
├── views.py                         # WMSLoginView (só override de get_redirect_url), HomeView —
│                                     #   SEM autenticação própria e SEM WMSLogoutView
├── middleware.py                    # RetornoPosLoginMiddleware (fallback pós-login, ver research.md R8)
├── urls.py                          # login/ (WMSLoginView), logout/ (LogoutView nativo), "" (home)
├── migrations/
│   ├── 0001_initial.py              # User, Setor, PapelUsuario
│   └── 0002_alter_setor_ativo.py    # Setor nasce inativo até ativação deliberada
├── templates/contas/
│   ├── base.html                    # Base local ao app (ver research.md, R12)
│   ├── login.html
│   └── home.html
└── static/contas/
    ├── css/
    │   ├── login.css
    │   └── home.css
    └── js/
        └── login.js                 # Estado de envio; fluxo funcional sem JavaScript

static/                              # NOVO diretório de projeto (exige STATICFILES_DIRS)
└── css/
    ├── tokens.css                   # Tokens de cor/tipografia/espaçamento extraídos de DESIGN.md
    └── base.css                     # Reset mínimo + estilos globais compartilhados

tests/                                # Já existente — SEM subpasta nova por app (ver research.md, R11)
├── test_infrastructure.py           # Sem mudança
├── test_settings.py                 # Sem mudança
├── test_contas_models.py            # NOVO
├── test_contas_auth.py              # NOVO
├── test_contas_protected_access.py  # NOVO
├── test_contas_logout.py            # NOVO
└── test_contas_home.py              # NOVO
```

**Structure Decision**: um único app novo (`contas`), na raiz do repositório, hospedando toda a
identidade autenticável (usuário, setor, papel) e o ciclo login/sessão/logout/Home. Testes
continuam no diretório único `tests/` já convencionado pelo projeto. Nenhuma estrutura de
`backend/`+`frontend/` separados (não há frontend separado — é a mesma aplicação Django Templates).

## Fluxos

### Login

```text
GET /login/
  → usuário já autenticado? → redireciona para home (redirect_authenticated_user nativo)
  → não autenticado → renderiza AuthenticationForm (rótulo "Matrícula" + "Senha")

POST /login/
  → AuthenticationForm.is_valid()
      → chama authenticate() → ModelBackend.user_can_authenticate()
          → matrícula inexistente OU senha errada OU is_active=False
              → get_invalid_login_error() → mesma mensagem genérica (FR-003, FR-004)
          → credenciais válidas + is_active=True
              → django.contrib.auth.login() (gira a chave de sessão)
              → resolução segura do destino (ver contracts/protecao-e-redirecionamento.md)
              → redirect(destino)
```

### Acesso protegido

```text
GET <superfície protegida>
  → @login_required / LoginRequiredMixin (nativos do Django, sem wrapper — ver research.md R9)
      → request.user.is_authenticated?
          (já é False para conta desativada — AuthenticationMiddleware → get_user() →
           ModelBackend.get_user() → user_can_authenticate() retorna AnonymousUser(), verificado
           no código-fonte instalado)
          → não → redirect para login com ?next=<caminho original> (FR-008, FR-009)
          → sim → segue para a view normalmente
```

### Retorno seguro pós-login

Ver `contracts/protecao-e-redirecionamento.md` → "Resolução segura do destino pós-login" e
"Fallback de autorização". Resumo:

```text
next presente?
  não → destino = home
  sim:
    url_has_allowed_host_and_scheme(next)? [nativo]         → não → destino = home
    resolve(urlsplit(next).path) existe? [só o path, nunca a query] → não → destino = home
    → destino = next completo (path + query preservada)

login bem-sucedido com destino ≠ home:
  → grava em sessão: destino esperado = destino completo
  → redirect(destino)  — SEM parâmetro técnico na URL

próxima requisição que bater exatamente (path + query) com o destino em sessão:
  → RetornoPosLoginMiddleware.process_view() consome o valor da sessão (uso único) e marca
    o objeto request (não a URL, não a sessão a partir daí)
  → se a view responder normalmente: marcador já consumido, nada mais acontece
  → se a view levantar PermissionDenied: process_exception() vê a marca do request → Home
    (qualquer PermissionDenied sem essa marca → 403 padrão do Django, inalterado)
```

Adicionar `_retorno_pos_login=1` manualmente à query string de qualquer URL não tem nenhum efeito —
nada lê a query string para essa decisão.

### Home autenticada mínima

```text
GET /
  → LoginRequiredMixin (nativo)
  → HomeView (TemplateView) renderiza contas/templates/contas/home.html
```

Conteúdo: confirmação mínima de sessão ativa (ex.: identificação da matrícula autenticada) e ação de
logout — sem sidebar completa, sem menu de features futuras, sem KPI, sem catálogo/importação.
Decisões de app-shell (largura de sidebar desktop, navegação mobile) permanecem **abertas em
`DESIGN.md`** e não são antecipadas aqui.

### Logout

```text
POST /logout/  (CSRF obrigatório; não exige sessão autenticada — ver research.md R7)
  → LogoutView nativo (sem subclasse — nenhum override necessário, ver research.md R7)
      .post() → django.contrib.auth.logout(request) incondicional
      → com sessão válida → encerra a sessão
      → sem sessão válida → no-op seguro (trata request.user como None internamente, sem erro)
  → redirect para /login/ (LOGOUT_REDIRECT_URL) — FR-017a, em ambos os casos
```

`POST /logout/` sem sessão válida: verificado no código-fonte instalado
(`django/contrib/auth/__init__.py::logout()`) que a função já trata usuário anônimo/ausente sem
levantar exceção — apenas dispara o sinal com `user=None` e limpa a sessão (vazia ou não). Nenhuma
distinção de mensagem é exposta entre "havia sessão" e "não havia sessão" (edge case da spec).

## Segurança

- **CSRF**: `CsrfViewMiddleware` já ativo; `{% csrf_token %}` nos formulários de login/logout.
- **Sessão**: backend padrão (`django.contrib.sessions`), chave de sessão renovada no login
  (proteção nativa contra fixação de sessão).
- **Senha**: hashers nativos do Django (PBKDF2 por padrão); `AUTH_PASSWORD_VALIDATORS` já
  configurados em `base.py` continuam válidos e inalterados.
- **Mensagens de erro**: única mensagem genérica para matrícula inexistente / senha incorreta /
  conta inativa (`AuthenticationForm` nativo) — nenhum detalhe interno exposto (Constitution,
  Princípio VI).
- **Redirecionamento**: `url_has_allowed_host_and_scheme` nativo bloqueia qualquer destino fora do
  próprio host; checagem adicional de `resolve()` (só sobre o `path`, nunca a query string — bug
  verificado empiricamente e corrigido nesta revisão) evita confiar em caminhos que não
  correspondem a nenhuma rota.
- **Fallback de autorização pós-login**: `RetornoPosLoginMiddleware` só intervém quando o próprio
  servidor reconheceu, via sessão, que a requisição atual é exatamente o destino esperado
  imediatamente após um login bem-sucedido (`process_view`, consumido uma única vez) — nenhum
  parâmetro de URL controla essa decisão, então não é falsificável pelo cliente. Qualquer outro
  `PermissionDenied` do sistema (hoje ou de features futuras) continua resultando no 403 padrão do
  Django, inalterado. Nenhum `handler403` global é definido.
- **Logout**: `POST`-only (verificado: `http_method_names = ["post", "options"]`), elimina logout
  via link/CSRF simples; funciona com ou sem sessão válida, sem revelar qual dos dois casos ocorreu.
- **Conta desativada em sessão ativa**: garantida por comportamento nativo do
  `AuthenticationMiddleware`/`ModelBackend` (verificado no código-fonte instalado — ver
  `research.md`, R9), não por código próprio.
- **Nenhuma criptografia própria, nenhum armazenamento próprio de senha, nenhum dado sensível em
  log** (restrição explícita do pedido, respeitada integralmente).

## Testes

Convenção: pytest-django, `tests/` (raiz), arquivos agrupados por preocupação (ver Project
Structure). Lista mínima por arquivo:

**`test_contas_models.py`** (Model/domain):
- Matrícula é preservada exatamente como fornecida (incluindo zeros à esquerda), nunca convertida.
- Matrícula duplicada é rejeitada no nível de banco (`IntegrityError` em `unique=True`).
- Usuário sem `setor` não pode ser criado (`INV-ORG-001`).
- Usuário pode ter múltiplos `PapelUsuario` distintos simultaneamente.
- Atribuição duplicada do mesmo papel ao mesmo usuário é rejeitada (`UniqueConstraint`).
- `tem_papel()` retorna apenas os papéis explicitamente atribuídos — nenhuma herança implícita.

**`test_contas_auth.py`** (Login):
- Matrícula + senha válidas → autentica.
- Senha inválida → recusa com mensagem genérica.
- Matrícula inexistente → recusa com a mesma mensagem genérica.
- Usuário inativo → recusa com a mesma mensagem genérica.
- As três recusas acima produzem exatamente a mesma mensagem (comparação direta).
- Sessão persiste entre requisições subsequentes (usuário autenticado permanece identificado).
- Usuário já autenticado que acessa `GET /login/` é redirecionado para a Home.

**`test_contas_protected_access.py`** (Proteção + retorno + fallback de autorização + edge case
crítico — lista obrigatória desta revisão):
- Visitante não autenticado não recebe conteúdo de superfície protegida e é redirecionado para
  `/login/` com `next` apontando para o destino original.
- **Destino interno, existente e autorizado**: retorna corretamente ao destino após login; a
  resposta de redirect não contém nenhum parâmetro técnico na URL (sem `_retorno_pos_login` nem
  equivalente); a chave de sessão do destino pendente deixa de existir depois da primeira
  requisição subsequente (foi consumida).
- **Destino interno, existente, mas não autorizado**: a primeira requisição imediatamente pós-login
  para esse destino levanta `PermissionDenied` e cai na Home.
- **Mesma URL não autorizada, acessada de novo depois** (fora do fluxo de login, sem marcador de
  sessão pendente): mostra o 403 padrão do Django — não cai na Home.
- **Tentativa de forjar via URL**: adicionar manualmente `?_retorno_pos_login=1` a uma URL protegida
  não autorizada não muda nada — continua sendo 403 normal (prova de que a query string não tem
  nenhum efeito sobre a decisão).
- **Destino legítimo com query string** (ex.: `/materiais/?pagina=2&ordenacao=descricao`): a rota é
  reconhecida como existente (`resolve()` recebe só o path); a query original é preservada no
  redirect final e na comparação de consumo do marcador.
- Destino externo (`next` manipulado) continua rejeitado — cai na Home.
- Destino inexistente (não resolve a nenhuma rota) continua caindo na Home.
- **Cenário crítico**: login válido → usuário é desativado (`is_active=False`) → próxima
  requisição a superfície protegida é negada/redirecionada, sem exigir logout explícito antes. Este
  teste protege o comportamento **nativo** do Django (`ModelBackend.get_user()` +
  `user_can_authenticate()`), do qual `login_required`/`LoginRequiredMixin` dependem — não código
  próprio.

**`test_contas_logout.py`**:
- Logout encerra a sessão (com sessão válida) e redireciona para `/login/`.
- Nova tentativa de acessar superfície protegida com a mesma sessão exige autenticação novamente.
- Logout **sem** sessão válida também redireciona para `/login/`, como no-op seguro — sem erro, sem
  exceção, sem revelar se havia ou não sessão.

**`test_contas_home.py`** (UI mínima):
- Renderização básica da Home para usuário autenticado (200, template correto).
- Renderização básica do login (200, campos matrícula/senha presentes).
- Mensagem de erro genérica aparece no HTML de uma tentativa de login inválida.

## Dependências

Nenhuma dependência nova. Apenas apps já instalados (`django.contrib.auth`,
`django.contrib.sessions`, `django.contrib.admin`) e o driver de banco já presente (`psycopg`).
Preferência por "nenhuma nova dependência" satisfeita integralmente (ver `research.md`, R15).

## Spec/domain check

- **`spec.md`**: todos os FRs de login (FR-001 a FR-007, FR-001a, FR-001b, FR-005a), acesso
  protegido (FR-008 a FR-012, FR-010a), identificação (FR-013 a FR-016) e logout (FR-017, FR-017a,
  FR-018) têm mecanismo técnico correspondente identificado (ver `data-model.md` → tabela de
  rastreamento e `contracts/protecao-e-redirecionamento.md`). Nenhum FR ficou sem cobertura.
- **`docs/domain/invariants-matrix.md`**: `INV-AUTH-001` (usuário inativo não acessa/opera) e
  `INV-ORG-001` (um único setor por usuário) são preservadas — `INV-AUTH-001` agora explicitamente
  por comportamento nativo verificado do Django (`research.md`, R9), não por código próprio.
  `INV-ORG-002`/`INV-ORG-003` permanecem fora do escopo desta feature, por decisão já registrada em
  `spec.md`/`research.md` (R4) — não são violadas, apenas não são administradas aqui. Nenhuma fonte
  normativa exige nome de setor único; `Setor.nome` não tem `unique=True` (correção desta revisão,
  `data-model.md`) — remover essa constraint não viola nenhuma invariante, pois nenhuma a exigia.
- **`docs/domain/permissions-matrix.md`**: o catálogo de 7 papéis é reproduzido em código
  (`Papel`) com os mesmos IDs — nenhum papel novo é criado, nenhuma capability é redefinida. A
  distinção entre superusuário técnico do Django e papel de negócio (`ROLE-SYSTEM-ADMIN`) é
  respeitada explicitamente (regras 7–8 do documento).
- **`DESIGN.md`**: login e Home usam os tokens de cor/tipografia/espaçamento definidos; nenhum
  padrão visual novo é inventado. Decisões de app-shell (sidebar desktop, navegação mobile) que o
  próprio `DESIGN.md` deixa em aberto **não são resolvidas por esta feature** — a Home permanece
  deliberadamente mínima até essas decisões existirem.
- **Nenhum conflito material** foi identificado entre `spec.md`, as matrizes canônicas, `PRODUCT.md`
  e `DESIGN.md` para o que esta feature precisa implementar.

## Open Questions

Nenhum **PLAN BLOCKER** identificado, em nenhuma das revisões — todos os pontos levantados (marcador
de sessão vs. query string, `resolve()` com query string, reavaliação de conta ativa, fallback de
autorização pós-login) tinham solução simples e robusta dentro dos limites pedidos, e foram
resolvidos em `research.md` (R8, R9) sem inventar regra de negócio nova.

Notas não bloqueantes (não impedem `/speckit-tasks`, apenas registradas para o futuro):

- A spec não define nem exige campo de nome/apelido de exibição do usuário; o Django Admin e
  qualquer UI futura identificarão contas apenas pela matrícula. Se um nome amigável for
  necessário, é uma decisão de produto nova, fora desta feature.
- Esta feature não adiciona logging estruturado de tentativas de login (sucesso/falha). Não é
  exigido por nenhuma FR/SC da spec; poderia ser adicionado depois (via os signals nativos
  `user_logged_in`/`user_login_failed` do Django) se a operação real do almoxarifado mostrar
  necessidade de diagnóstico — não incluído agora para não expandir escopo sem pedido concreto.
- O race condition documentado em `research.md` (R8): destino cujo padrão de URL existe mas cujo
  objeto foi excluído entre o redirecionamento e a conclusão do login resulta em 404 comum daquela
  view, não em fallback para a Home. Sem evidência de necessidade de tratamento especial.
- O marcador de sessão do retorno pós-login (`research.md`, R8) só é consumido quando uma
  requisição bate exatamente com o destino pendente; se essa requisição nunca chegar (o usuário
  interrompe o fluxo automático de redirect do navegador), o marcador permanece em sessão até ser
  consumido mais tarde por esse mesmo destino específico ou até a sessão expirar — não há TTL
  dedicado. Deliberado (ver alternativas descartadas em R8); sem evidência de necessidade de
  tratamento adicional.

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

Nenhuma violação identificada — tabela omitida.
