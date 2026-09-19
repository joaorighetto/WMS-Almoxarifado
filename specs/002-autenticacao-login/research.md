# Phase 0 — Research: Fundação de Autenticação e Login

Todas as decisões abaixo foram avaliadas contra: `.specify/memory/constitution.md`,
`docs/domain/permissions-matrix.md`, `docs/domain/invariants-matrix.md`, `PRODUCT.md`, `DESIGN.md`
e `specs/002-autenticacao-login/spec.md`. Nenhum item abaixo introduz regra de negócio nova — todos
respondem "como implementar", nunca "o que o produto deveria fazer".

Estado real do repositório no momento do planejamento (verificado, não presumido): projeto Django +
PostgreSQL, sem nenhum app próprio, sem nenhuma migration de negócio, sem `AUTH_USER_MODEL`
customizado. `config/settings/base.py` só tem os apps `contrib` padrão. `tests/` é um único
diretório na raiz (pytest-django, `testpaths=["tests"]`), sem subpastas por app. Esta é, portanto, a
primeira feature a introduzir código de produção no projeto.

**Correção desta revisão**: `pyproject.toml` fixa apenas um piso (`django>=5.2`); a versão
efetivamente resolvida e travada em `uv.lock` é **Django 6.1.1**, não 5.2. Todas as afirmações de
comportamento de framework abaixo (R3, R7, R9) foram reverificadas diretamente contra o
código-fonte instalado dessa versão (`.venv/lib/python3.13/site-packages/django/...`), não contra
suposição de versão nem contra documentação genérica.

## R1. Modelo de usuário: custom User desde o início

- **Decision**: introduzir um `User` customizado agora, via `AbstractBaseUser` + `PermissionsMixin`
  + `UserManager` próprio (padrão documentado oficialmente pelo Django para trocar o campo de
  identificação), com `USERNAME_FIELD = "matricula"`.
- **Rationale**: não existe nenhuma migration de negócio no projeto ainda — é o único momento em
  que trocar `AUTH_USER_MODEL` é seguro e barato. Adiar essa decisão para depois que outras
  features criarem FKs para o usuário exigiria uma migração destrutiva ou reconstrução de banco.
- **Alternatives considered**:
  - Manter `django.contrib.auth.models.User` com `username` como matrícula: rejeitado — o campo
    `username` do Django não expressa a semântica de "matrícula funcional" e manteria confusão de
    nomenclatura/documentação permanente.
  - Estender `AbstractUser`: rejeitado — manteria o campo `username` como coluna morta e duplicada
    (Django exige um `USERNAME_FIELD`, mas `AbstractUser` já vem com `username` fixo além dele),
    mais confuso que partir de `AbstractBaseUser`.
  - App externo de autenticação (`django-allauth` etc.): rejeitado — nenhuma necessidade concreta
    (Princípio XI, dependências com parcimônia); o próprio Django resolve o problema.

## R2. Matrícula como identificador opaco

- **Decision**: `matricula = models.CharField(max_length=32, unique=True)`. Nenhuma conversão
  numérica, nenhuma máscara ou regex de formato; a representação cadastrada é preservada.
- **Ressalva (revisão 3) — "nunca normalizada" não era literalmente verdadeiro.** Verificado no
  código-fonte instalado (`django/contrib/auth/forms.py`, `UsernameField.to_python()`): o campo de
  login do `AuthenticationForm` nativo é um `UsernameField` que aplica `unicodedata.normalize(
  "NFKC", value)` sobre um `CharField` com `strip=True`. O mesmo NFKC é aplicado por
  `AbstractBaseUser.clean()` ao salvar pelo Admin. Já `UserManager.create_user()` (ORM, bootstrap,
  testes) grava o valor exatamente como recebido.
  Ou seja, a **entrada submetida no login** passa por canonicalização técnica do framework; o
  **valor cadastrado** não é reformulado. Para matrículas ASCII — o caso real do SAEP — o efeito é
  nulo. Existe apenas para uma matrícula gravada via ORM com espaços nas pontas ou caracteres fora
  da forma NFKC, que ficaria impossível de usar no login.
  `FR-001b` foi reescrito para descrever isso com honestidade, em vez de afirmar "nunca
  normalizada". **Não** foi introduzido campo próprio para suprimir o NFKC: o comportamento nativo
  é o mais seguro na prática (evita duas representações Unicode distintas colidirem como
  identidades diferentes), e suprimi-lo seria complexidade sem problema concreto. Há teste que
  documenta o strip/NFKC para impedir nova divergência entre documento e código.
- **Rationale**: `FR-001b` exige tratamento como identificador opaco, preservando a representação
  cadastrada. `max_length=32` é um limite técnico de sanidade de entrada (evita valores
  patologicamente grandes na coluna/índice), não uma regra de formato do produto — não há evidência
  de qual seja o tamanho real da matrícula do SAEP, então o limite é deliberadamente generoso e
  documentado como não normativo.
- **Alternatives considered**:
  - `IntegerField`/`BigIntegerField`: rejeitado explicitamente — perderia zeros à esquerda e
    permitiria aritmética, violando `FR-001b`.
  - Definir máscara/tamanho exato: rejeitado — nenhuma fonte normativa define o formato oficial da
    matrícula; inventar um regex seria decisão de produto não sustentada.

## R3. Autenticação via mecanismos nativos do Django

- **Decision**: usar `django.contrib.auth.authenticate()` com o `ModelBackend` padrão (já
  configurado implicitamente via `AUTHENTICATION_BACKENDS` default do Django) e o
  `AuthenticationForm` nativo (via `django.contrib.auth.views.LoginView`).
- **Rationale**: `ModelBackend.authenticate()` já chama `user_can_authenticate()`, que rejeita
  usuário com `is_active=False` **antes** de aceitar a senha — ou seja, `FR-004`/`INV-AUTH-001` já
  são satisfeitos sem nenhum código adicional. O `AuthenticationForm` nativo já unifica matrícula
  inexistente, senha incorreta e conta inativa na mesma mensagem de erro genérica
  (`get_invalid_login_error()`), satisfazendo `FR-003` sem lógica própria. O rótulo do campo de
  login é derivado automaticamente do `verbose_name` de `USERNAME_FIELD`, então basta nomear o
  campo `matricula` com o `verbose_name` correto. **Verificado no código-fonte instalado**
  (`django/contrib/auth/backends.py`, `ModelBackend.authenticate()`): a autenticação só retorna o
  usuário se `check_password_with_timing_attack_mitigation(user, password) and
  self.user_can_authenticate(user)` — ou seja, matrícula inexistente, senha errada e conta inativa
  já convergem para o mesmo `None`/mensagem genérica sem distinção observável. O mesmo
  `user_can_authenticate()` é reaproveitado por `ModelBackend.get_user()` — ver R9, que depende
  diretamente deste fato verificado.
- **Correção desta revisão (recheck de simplicidade) — nenhum `contas/forms.py` é necessário**:
  **verificado no código-fonte instalado** (`django/contrib/auth/forms.py`,
  `AuthenticationForm.__init__`): `self.fields["username"].label =
  capfirst(self.username_field.verbose_name)` e `self.fields["username"].max_length =
  self.username_field.max_length or 254` — rótulo e tamanho máximo já vêm automaticamente do
  `verbose_name`/`max_length` do campo `matricula` no model, sem precisar subclassear
  `AuthenticationForm`. A versão anterior deste plano listava um `contas/forms.py` para "ajustar o
  rótulo" — era um arquivo sem responsabilidade real; removido da estrutura.
- **Achado adicional, relevante para `/speckit-tasks`**: `AuthenticationForm.confirm_login_allowed()`
  tem uma mensagem específica de "conta inativa" (`error_messages["inactive"]`), mas ela é
  **inalcançável** com o `ModelBackend` padrão — `confirm_login_allowed()` só é chamado quando
  `authenticate()` já retornou um usuário não-`None`, e `ModelBackend.authenticate()` só retorna
  usuário quando `user_can_authenticate()` (que rejeita `is_active=False`) já passou. Ou seja, um
  usuário inativo nunca chega a `confirm_login_allowed()` — ele já cai em `get_invalid_login_error()`
  (a mensagem genérica), junto com senha errada e matrícula inexistente. **Não sobrescrever
  `confirm_login_allowed()`** na implementação — fazer isso não teria efeito com o backend padrão e
  poderia sugerir, incorretamente, que a distinção de conta inativa depende desse método.
- **REABERTURA PARCIAL (revisão 3) — `contas/forms.py` passa a existir, só para a mensagem.**
  A revisão anterior rejeitou qualquer subclasse de `AuthenticationForm` afirmando que "nenhuma
  precisa de override". Isso valia para **rótulo e tamanho** (que de fato vêm do model, como
  verificado), mas não para a **mensagem de recusa**: validada em execução real, a string traduzida
  do Django em pt-BR sai como *"Por favor, entre com um matrícula e senha corretos…"*. O
  `%(username)s` é interpolado com o `verbose_name` do `USERNAME_FIELD`, e "matrícula" é feminino —
  o artigo masculino da tradução produz desacordo de gênero visível ao usuário, em texto que a
  equipe do almoxarifado lê toda vez que erra a senha.

  Isso é evidência concreta de necessidade, que era exatamente o critério que faltava antes.
  A subclasse é mínima e sobrescreve **apenas** `error_messages["invalid_login"]`:

  - não implementa autenticação própria (continua `ModelBackend`);
  - não sobrescreve `confirm_login_allowed()` (inalcançável, ver acima);
  - não toca rótulo, `max_length` nem campo algum;
  - mantém **uma única** string genérica para as três causas de recusa — senha incorreta,
    matrícula inexistente e conta inativa —, preservando `FR-003`/`SC-003` (não-enumeração de
    usuário). O teste de igualdade direta entre as três mensagens continua valendo.

  A decisão de segurança permanece intacta; o que muda é só o texto exibido.
- **Alternatives considered**:
  - View de login própria, validando credenciais manualmente: rejeitado — duplicaria exatamente o
    que `AuthenticationForm`/`ModelBackend` já fazem corretamente, na contramão do Princípio I
    (simplicidade) e do pedido explícito de preferir capacidades nativas do stack.
  - Subclasse de `AuthenticationForm` só para rótulo/tamanho: permanece rejeitado — ambos já vêm
    do model, verificado no código-fonte instalado.
  - Corrigir a tradução do próprio Django (`django.po`) ou trocar o `verbose_name` para um termo
    masculino: rejeitado — a primeira carrega uma tradução divergente do upstream para todo o
    projeto; a segunda distorceria o vocabulário de domínio ("matrícula") para contornar gramática.

## R4. Setor mínimo, sem gestão de setor

- **Decision**: `Setor` mínimo (`nome`, `ativo`), referenciado por `User.setor`
  (`ForeignKey(..., on_delete=models.PROTECT)`, obrigatório). Nenhuma criação/edição/inativação de
  setor é oferecida por esta feature. `nome` é obrigatório, mas **não** único — ver correção desta
  revisão abaixo.
- **Rationale**: `INV-ORG-001` ("todo usuário pertence a um único setor") exige que a FK exista e
  seja obrigatória — sem um modelo mínimo de `Setor`, não há nada para apontar. `on_delete=PROTECT`
  impede que um setor referenciado por usuários seja apagado, evitando órfãos que quebrariam a
  invariante ao nível de persistência.
- **Correção desta revisão — sem `unique=True` em `nome`**: a versão anterior deste plano propunha
  `nome` único, justificado apenas como "higiene básica de dados". Revisado contra `PRODUCT.md`,
  a constitution e as duas matrizes canônicas: nenhuma fonte normativa afirma que nomes de setor
  são únicos, nem exige um identificador/código de setor. Conveniência não é motivo suficiente para
  uma constraint de domínio/persistência (Princípio I — nenhuma complexidade, nem uma simples
  constraint, sem justificativa concreta). `nome` permanece obrigatório (`blank=False`), sem
  `unique=True`. Eventual identidade canônica de setor (nome único, código) pertence à futura
  definição da administração de setores (`PERM-SECTOR-MANAGE`), não a esta feature.
- **CORREÇÃO (revisão 3) — `INV-ORG-002` é preservada por esta feature, não adiada.** A versão
  anterior desta seção afirmava que `INV-ORG-002`/`INV-ORG-003` não precisavam ser impostas aqui
  "porque não há nesta feature nenhuma operação de escrita sobre `Setor`". **Essa premissa era
  factualmente falsa** na implementação entregue: `SetorAdmin` cria e altera setores, o Admin
  permite desativar um chefe, transferi-lo de setor e remover-lhe o papel, `Setor.ativo` nascia
  `True`, e o próprio `quickstart.md` começava criando um setor ativo sem chefe algum. O caminho de
  bootstrap desta feature é, portanto, uma superfície de escrita sujeita à invariante como qualquer
  outra.

  Escopo de feature não supera a matriz canônica nem a Constitution: uma invariante CRÍTICA não
  pode ficar violável só porque a administração de setores ainda não foi especificada. Duas saídas
  eram legítimas — (a) impor a invariante agora, ou (b) emendar `INV-ORG-002` explicitamente para
  admitir um estado transitório de provisionamento, o que seria decisão de domínio/governança, não
  correção editorial. **Decisão do dono do produto: (a)**.

  Mecanismo adotado (ver `spec.md`, FR-019 a FR-023):
  1. setor nasce **inativo** (`Setor.ativo` default `False`) — criar setor nunca produz, sozinho,
     um setor ativo sem chefe;
  2. ativação só é permitida quando existe exatamente um chefe ativo do próprio setor;
  3. desativar o chefe, transferi-lo de setor ou remover-lhe `ROLE-SECTOR-HEAD` é bloqueado quando
     deixaria um setor ativo sem chefe;
  4. atribuir um segundo chefe a setor com chefe ativo é bloqueado;
  5. todas essas mutações são transacionais e cobertas por teste.

  `INV-ORG-003` permanece garantida **estruturalmente**, sem regra nova: a chefia é derivada de
  `ROLE-SECTOR-HEAD` combinado ao setor único do próprio usuário (`INV-ORG-001`), nunca de um
  vínculo separado — logo um chefe nunca responde por mais de um setor.

  A invariante não pôde ser expressa como constraint de banco (Constitution, Princípio III): "um
  chefe ativo por setor ativo" é um predicado agregado que cruza `Setor`, `User.is_active`,
  `User.setor` e `PapelUsuario.papel`, fora do alcance de `UniqueConstraint`/`CheckConstraint` e
  exigindo trigger própria. Fica garantida na aplicação, em ponto único e coberta por testes.

  Isto **não** transforma a 002 em feature de administração de setores: `PERM-SECTOR-MANAGE`
  continua pendente e nenhuma tela de gestão é entregue. O que se garante é que o caminho de
  provisionamento que esta feature realmente possui não produz estado inválido.
- **Alternatives considered**:
  - Adiar até a feature de administração de setores existir: rejeitado — sem `Setor`, não há como
    satisfazer `INV-ORG-001` nem testar identificação de setor (User Story 3 da spec).
  - Adicionar campo `chefe` em `Setor` agora: rejeitado — chefia é derivada de "usuário com papel
    `ROLE-SECTOR-HEAD` e `setor` igual a este setor", não uma coluna própria; adicionar agora
    antecipa estrutura organizacional sem necessidade (Princípio I).

## R5. Papéis: enum fechado + tabela de atribuição própria

- **Decision**: `Papel(models.TextChoices)` definido em código, com `value` idêntico ao ID canônico
  da matriz (`ROLE-REQUESTER`, `ROLE-SECTOR-ASSISTANT`, `ROLE-SECTOR-HEAD`,
  `ROLE-WAREHOUSE-STAFF`, `ROLE-WAREHOUSE-HEAD`, `ROLE-AUDITOR`, `ROLE-SYSTEM-ADMIN`). Atribuição
  via `PapelUsuario` (FK para `User` + campo `papel` com esses choices,
  `models.UniqueConstraint(fields=["usuario", "papel"], name="papelusuario_unico_usuario_papel")`
  em `Meta.constraints`). Método de conveniência `User.tem_papel(*codigos)` para consulta.
- **Rationale**: o catálogo é fechado e definido pela matriz canônica — representá-lo como código
  (não como linhas editáveis de tabela) impede que alguém "invente" um papel novo pela
  administração do sistema. Usar o mesmo `value` do ID canônico (`ROLE-*`) garante rastreabilidade
  1:1 exata com `docs/domain/permissions-matrix.md`, sem necessidade de tabela de tradução.
  A `UniqueConstraint` impede atribuição duplicada do mesmo papel e não introduz herança — cada
  linha é uma concessão explícita e independente (consistente com `FR-015`). Usa
  `Meta.constraints`/`UniqueConstraint` (forma moderna e explícita, com nome de constraint
  nomeado) em vez da opção legada `unique_together` — mesmo comportamento funcional, projeto novo
  em Django 6.1, sem motivo para preferir a forma antiga.
- **Alternatives considered**:
  - `django.contrib.auth` `Group`/`Permission`: avaliado e descartado. `Group` é pensado para
    conjuntos de `Permission` arbitrários e editáveis via admin como dado solto — não expressa um
    catálogo fechado e canônico, e exigiria mapear manualmente nomes de `Group` para os IDs
    `ROLE-*`, criando uma camada de tradução desnecessária e uma segunda fonte de verdade.
  - Campo `ArrayField(CharField(choices=...))` no próprio `User` (recurso nativo do Postgres):
    considerado — tecnicamente mais enxuto (sem tabela extra), mas descartado por ora em favor de
    uma tabela explícita, que é mais direta de inspecionar via admin/ORM e de testar
    (`user.papeis.filter(...)`), e mantém a porta aberta para futuras features anexarem metadados a
    uma atribuição de papel (ex.: data de concessão) sem migração destrutiva. Fica registrado como
    alternativa simples caso a tabela se mostre desnecessária na prática.
  - Replicar a `permissions-matrix.md` inteira no banco (capabilities, escopos, condições):
    explicitamente rejeitado — a spec e a orientação do usuário pedem para não fazer isso; a
    matriz continua sendo a fonte de autorização, consumida em código por cada feature de negócio.

## R6. Provisionamento para desenvolvimento/teste

- **Decision**: Django Admin nativo (registrando `User`/`Setor`/`PapelUsuario` com um `UserAdmin`
  customizado, seguindo o padrão documentado do Django para modelo de usuário customizado) +
  `createsuperuser` (com `"setor"` em `REQUIRED_FIELDS` — suporte nativo do Django para campos de
  FK em `REQUIRED_FIELDS`) para uso humano local. Testes automatizados criam usuários diretamente
  via ORM (`User.objects.create_user(...)`, `PapelUsuario.objects.create(...)`) em fixtures
  pytest, sem comando de gerência dedicado.
- **Rationale**: a spec já assume (`Assumptions`) que usuários existem "por algum meio
  administrativo fora do escopo desta spec" — o Django Admin é exatamente esse meio, sem exigir
  nenhuma tela nova. Superusuário técnico (`is_staff=True`, `is_superuser=True`) é distinto de
  papel de negócio (`docs/domain/permissions-matrix.md`, regras 7–8): `createsuperuser` nunca
  concede `ROLE-*` sozinho.
- **Alternatives considered**:
  - Management command dedicado (`criar_usuario_dev`): considerado, mas descartado por ora —
    Admin + ORM já cobrem 100% da necessidade descrita na spec (dev local via Admin, testes via
    ORM); adicionar um comando extra seria superfície de código sem consumidor real hoje. Pode ser
    adicionado depois, sem custo de migração, se o uso diário mostrar necessidade.
  - Fixtures JSON (`loaddata`): descartado como mecanismo principal — senha exigiria hash
    pré-computado nos fixtures, mais frágil que criar via ORM/`create_user()` (que já aplica
    `set_password()` corretamente).

## R7. Login/Logout via views nativas do Django

- **Decision**: uma única subclasse fina, `WMSLoginView(LoginView)` — só para o override de
  `get_redirect_url()` (ver R8). `LOGIN_URL = "login"`, `LOGIN_REDIRECT_URL = "home"`,
  `LOGOUT_REDIRECT_URL = "login"`.
- **Correção desta revisão (recheck de simplicidade) — sem `WMSLogoutView`**: `LogoutView` nativo
  não precisa de nenhum override para este comportamento — com `LOGOUT_REDIRECT_URL = "login"`
  configurado, `LogoutView.as_view()` usado diretamente em `contas/urls.py` já entrega `FR-017a`
  integralmente. A versão anterior deste plano propunha uma subclasse `WMSLogoutView` sem nenhuma
  responsabilidade própria — removida.
- **Rationale**: `LOGOUT_REDIRECT_URL = "login"` entrega `FR-017a` (redirecionamento imediato ao
  login pós-logout) sem nenhum código customizado. `LoginView` já lida com `GET` (renderiza
  formulário), `POST` (valida, autentica, chama `django.contrib.auth.login()`, que gira a chave de
  sessão — proteção nativa contra fixação de sessão) e resolução de destino (`next`). **Verificado no
  código-fonte instalado** (`django/contrib/auth/views.py`): `LogoutView.http_method_names =
  ["post", "options"]` — só aceita `POST` (proteção nativa contra logout via link/CSRF simples,
  desde o Django 4.1, presente também na versão 6.1.1 usada neste projeto), o que também define a
  UI: o botão "Sair" deve ser um formulário `POST`, não um link `GET`.
- **Correção desta revisão — logout não exige sessão autenticada**: `LogoutView.post()` não é
  protegido por `LoginRequiredMixin` nem verifica `request.user` antes de agir — chama
  `django.contrib.auth.logout(request)` incondicionalmente. **Verificado no código-fonte instalado**
  (`django/contrib/auth/__init__.py`, função `logout()`): ela trata `request.user` ausente/anônimo
  como `user = None`, apenas dispara o sinal `user_logged_out` com `user=None` e chama
  `request.session.flush()` — sem levantar exceção nem exigir sessão prévia. Ou seja, `POST
  /logout/` sem sessão válida é um no-op seguro que ainda assim redireciona para `LOGOUT_REDIRECT_URL`
  ("login"), nunca um erro. O contrato da rota `logout` foi corrigido para refletir isso (ver
  `contracts/protecao-e-redirecionamento.md`) — a versão anterior deste plano listava
  incorretamente "autenticação exigida" para essa rota.
- **Alternatives considered**:
  - Views próprias do zero: rejeitado pelas mesmas razões de R3 (duplicaria mecanismo maduro do
    framework).

## R8. Resolução segura do destino pós-login (`next`) e fallback de autorização — REVISADO (2)

> Esta seção substitui integralmente a versão anterior. Duas falhas foram identificadas e
> corrigidas nesta revisão:
> 1. O marcador `?_retorno_pos_login=1` vivia na **query string**, controlável pelo cliente —
>    qualquer usuário podia adicioná-lo manualmente a qualquer URL para tentar influenciar o
>    comportamento, e ele não expirava (não era realmente de uso único). Substituído por um
>    marcador de servidor, em sessão, vinculado ao destino exato.
> 2. `django.urls.resolve()` recebia a URL completa (path + query string) do `next`. **Verificado
>    empiricamente** contra o Django instalado: `resolve("/catalogo/?pagina=2")` levanta
>    `Resolver404` (a query string quebra o casamento de padrão), enquanto `resolve("/catalogo/")`
>    corresponde normalmente. Isso faria qualquer `next` legítimo com query string (ex.: paginação,
>    ordenação) ser tratado incorretamente como "inexistente" e cair na Home. Corrigido separando
>    path de query antes de chamar `resolve()`.

### "Interno" e "existente" (corrigido)

```python
from urllib.parse import urlsplit
from django.urls import resolve
from django.urls.exceptions import Resolver404

def get_redirect_url(self):
    url = super().get_redirect_url()          # nativo: host/scheme (FR-011)
    if not url:
        return ""
    caminho = urlsplit(url).path              # SÓ o path vai para resolve() — query preservada em `url`
    try:
        resolve(caminho)
    except Resolver404:
        return ""
    return url                                 # devolve a URL completa (path + query), não só o path
```

- `url_has_allowed_host_and_scheme()` nativo continua cobrindo "interno"/`FR-011`.
- `resolve()` agora recebe só o `path` (via `urlsplit(url).path`) — nunca a query string. O
  fragmento (`#...`) nunca chega ao servidor em uma requisição HTTP normal, então não há nada a
  tratar quanto a ele.
- A URL **completa** (path + query) é o que se propaga como destino — tanto para o `Location` do
  redirect quanto para o marcador de sessão da seção seguinte — preservando query legítima (ex.:
  `?pagina=2&ordenacao=descricao`) no destino final.

### "Autorizado" — marcador de sessão de uso único vinculado ao destino exato (corrigido)

Nenhum parâmetro técnico é exposto na URL. O fluxo:

```python
# contas/views.py — WMSLoginView(LoginView)
MARCADOR_SESSAO = "_retorno_pos_login_destino"

def get_success_url(self):
    url = self.get_redirect_url()
    if url:
        self.request.session[self.MARCADOR_SESSAO] = url   # guarda o destino EXATO esperado
        return url                                          # redirect normal, sem parâmetro extra
    return self.get_default_redirect_url()
```

```python
# contas/middleware.py
class RetornoPosLoginMiddleware:
    MARCADOR_SESSAO = "_retorno_pos_login_destino"
    ATRIBUTO_REQUEST = "_retorno_pos_login"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        destino_pendente = request.session.get(self.MARCADOR_SESSAO)
        if destino_pendente is not None and request.get_full_path() == destino_pendente:
            del request.session[self.MARCADOR_SESSAO]      # consumido — uso único
            setattr(request, self.ATRIBUTO_REQUEST, True)   # flag privada só neste request
        return None                                          # nunca impede a view de rodar

    def process_exception(self, request, exception):
        if isinstance(exception, PermissionDenied) and getattr(request, self.ATRIBUTO_REQUEST, False):
            return redirect("home")
        return None
```

**Por que isso é realmente one-shot e não falsificável via URL** (ver também "Correções
realizadas" no relatório desta revisão):
- O marcador nunca aparece na URL — vive só em `request.session`, do lado do servidor. Adicionar
  `?_retorno_pos_login=1` manualmente a qualquer URL não tem nenhum efeito: nada no middleware lê a
  query string para essa decisão.
- `process_view` roda **antes** da view, em toda requisição — **verificado no código-fonte
  instalado** (`django/core/handlers/base.py`: `hasattr(mw_instance, "process_view")`, o mesmo
  padrão de registro de `process_exception`). Ele só marca o `request` quando o **path + query
  string da requisição atual** (`request.get_full_path()`) bate exatamente com o destino gravado na
  sessão pelo login — nunca por correspondência de prefixo, nunca só pelo path.
- O valor é removido da sessão (`del request.session[...]`) no exato momento em que é reconhecido —
  antes mesmo de a view rodar — então mesmo que a mesma URL seja visitada de novo depois, o
  marcador não existe mais e a flag não é definida: essa segunda visita recebe o 403 padrão.
- `process_exception` só age quando a *flag do objeto `request` atual* (não a sessão, não a URL)
  foi definida por `process_view` **nesta mesma requisição** — impossível de forjar de fora, porque
  o atributo do objeto `request` não é um dado que trafega entre cliente e servidor.
- Se a requisição atual não bater com o destino pendente, `process_view` não faz nada — o marcador
  de sessão permanece aguardando a requisição correta. Isso é deliberado (ver "Impacto conhecido"
  abaixo), não um bug.
- **Verificado no código-fonte instalado** (`django/core/handlers/base.py`,
  `process_exception_by_middleware`): se nenhum middleware devolver resposta para uma exceção, o
  Django prossegue com a conversão padrão (`response_for_exception`, 403 para `PermissionDenied`).
  Mecanismo de extensão nativo, ortogonal ao `handler403` do `ROOT_URLCONF` — `handler403` nunca é
  definido por esta feature.
- Comparação por **igualdade exata de string** (`request.get_full_path() == destino_pendente`),
  nunca por prefixo — evita que `/materiais/123/outra-coisa` seja tratado como o mesmo destino que
  `/materiais/123/`.

**Rationale**: satisfaz as cinco condições exigidas — (1) `PermissionDenied` sem a flag continua
resultando no 403 padrão, em qualquer parte do sistema; (2) a flag identifica exata e apenas a
tentativa de retorno originada do login, para o destino exato esperado; (3) o fallback só se aplica
nesse contexto; (4) o login não conhece nenhuma regra de autorização de outra feature; (5) nenhuma
view de destino é executada antecipadamente — o `PermissionDenied` só é capturado na requisição
real do navegador.

**Impacto conhecido, não bloqueante**:
- Destino cujo padrão de URL existe mas cujo objeto foi excluído entre o redirecionamento e a
  conclusão do login: resulta em 404 comum, não em fallback para a Home (mantido de revisões
  anteriores).
- O marcador de sessão fica pendente até ser consumido por uma requisição cujo `get_full_path()`
  bata exatamente com o destino gravado, **ou até a sessão expirar** (`SESSION_COOKIE_AGE` padrão
  do Django) — não há expiração antecipada dedicada. Na prática, o navegador segue o
  redirecionamento HTTP automaticamente como a requisição imediatamente seguinte, então esse
  destino é, na prática, a próxima requisição real; o cenário em que ele fica pendente por mais
  tempo exige uma interrupção deliberada desse fluxo automático (ex.: o usuário copiar a URL do
  redirect e visitá-la manualmente bem depois). Não implementado (não adicionar TTL/nonce — seria
  complexidade sem evidência de necessidade, Princípio I).

**Alternatives considered**:
- Marcador na query string (versão anterior): rejeitado explicitamente nesta revisão — controlável
  pelo cliente, não expira, falsificável.
- `handler403` global: permanece rejeitado (revisão anterior) — mudaria todo 403 do sistema.
- Marcador booleano global em sessão, sem vínculo com o destino (`session["retorno_pendente"] =
  True`): rejeitado — qualquer `PermissionDenied` em qualquer view, não só no destino esperado,
  cairia na Home enquanto a flag estivesse setada; não amarra a decisão ao destino exato.
- Nonce criptográfico assinado na URL ou em cookie separado: rejeitado — sessão já é um canal
  server-side confiável e já existente; um nonce adicional seria estado extra sem necessidade
  concreta (recheck de simplicidade).
- Model/tabela dedicada para registrar tentativas de retorno pós-login: rejeitado — a sessão já é
  exatamente o armazenamento de estado por-usuário-por-navegador que esse problema precisa; uma
  tabela seria persistência desnecessária para um dado que só importa por uma requisição.
- Pré-executar/despachar a view de destino a partir do login: permanece rejeitado — complexidade
  desproporcional, viola a restrição de não invocar antecipadamente a view de destino.
- Mixin que cada view protegida futura adotaria manualmente: permanece rejeitado — exigiria adesão
  manual de toda feature futura; o middleware cobre todas as views automaticamente, sem que
  nenhuma feature precise cooperar com o mecanismo.
- `handler404` global redirecionando qualquer 404 para a Home: permanece rejeitado — mudaria o
  comportamento de erro do sistema inteiro.

## R9. Reavaliação de conta ativa a cada request — REVISADO (comportamento 100% nativo)

> Esta seção substitui integralmente a versão anterior deste plano. A premissa anterior — de que
> `AuthenticationMiddleware`/`ModelBackend` não rejeitam `is_active=False` fora do momento do login
> — foi verificada diretamente contra o código-fonte instalado (Django 6.1.1, não presumido) e está
> **incorreta**. O Django já resolve isso nativamente.

- **Verificação feita** (código lido diretamente de
  `.venv/lib/python3.13/site-packages/django/...`, não de memória/documentação):
  - `django/contrib/auth/backends.py`, `ModelBackend.get_user(self, user_id)`:
    ```python
    def get_user(self, user_id):
        try:
            user = UserModel._default_manager.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None
    ```
    e `user_can_authenticate(self, user)`: `return getattr(user, "is_active", True)`.
  - `django/contrib/auth/__init__.py`, `get_user(request)` (chamada pelo `AuthenticationMiddleware`
    em toda requisição, via `SimpleLazyObject` em `request.user`):
    ```python
    user = backend.get_user(user_id)
    ...
    return user or AnonymousUser()
    ```
  - Conclusão direta: se `is_active=False`, `ModelBackend.get_user()` retorna `None`, e
    `django.contrib.auth.get_user(request)` retorna `AnonymousUser()` **na primeira requisição
    seguinte à desativação, e em todas as seguintes** — não só no momento do login. Nenhum código
    desta feature precisa provocar isso; é o comportamento padrão de qualquer projeto Django que
    use o backend padrão.
- **Decision**: nenhuma abstração própria. Superfícies protegidas usam diretamente
  `django.contrib.auth.decorators.login_required` (function-based views) e
  `django.contrib.auth.mixins.LoginRequiredMixin` (class-based views) — ambos checam apenas
  `request.user.is_authenticated`, o que já basta, porque `request.user` já é `AnonymousUser()`
  para uma conta desativada, pelo mecanismo acima. **Removidos do plano**: `contas/auth.py`,
  `usuario_esta_ativo`, `login_ativo_required`, `LoginAtivoRequiredMixin` — duplicavam
  comportamento que o framework já garante (Princípio I).
- **Rationale**: satisfaz exatamente a expectativa da spec — reavaliação "na próxima interação",
  não revogação distribuída instantânea, sem polling, sem JavaScript, e agora **sem nenhum código
  próprio**, só configuração/uso direto de `login_required`/`LoginRequiredMixin`.
- **Teste preservado, sentido revisado**: o cenário `login válido → is_active=False → próxima
  requisição a superfície protegida → acesso negado` continua na suíte — não porque protege código
  próprio (não há mais nenhum), mas porque protege uma premissa de framework da qual o produto
  passa a depender diretamente (`FR-006`/`INV-AUTH-001`). Se essa premissa deixar de valer numa
  versão futura do Django ou numa mudança de `AUTHENTICATION_BACKENDS`, o teste quebra e alerta.
- **Alternatives considered**:
  - Predicado/decorator/mixin próprios (versão anterior deste plano): rejeitado nesta revisão —
    baseava-se numa premissa não verificada e incorreta sobre o framework; duplicava comportamento
    já nativo.
  - Sinal/job assíncrono para invalidar sessões no momento da desativação: permanece rejeitado —
    infraestrutura distribuída desnecessária; o comportamento nativo já entrega o que a spec pede.
  - Checar `is_active` manualmente em cada view: permanece rejeitado — redundante com o que
    `request.user.is_authenticated` já reflete.

## R10. Um único app novo: `contas`

- **Decision**: criar um único app Django, `contas`, na raiz do repositório (ao lado de `config/`),
  contendo `User`, `Setor`, `PapelUsuario`, views de login/logout/home, o middleware de fallback
  pós-login (`RetornoPosLoginMiddleware`, ver R8), templates e CSS específicos.
- **Rationale**: é o primeiro app do projeto — não há convenção de `apps/` aninhado a seguir nem
  romper. `contas` já é o termo usado na própria spec ("Usuário (conta autenticável)"). A Home
  mínima pertence ao mesmo app por ser parte indissociável do ciclo login→sessão→logout, evitando
  um segundo app quase vazio.
- **Alternatives considered**:
  - App separado só para a Home (`core`/`dashboard`): rejeitado — fragmentação prematura sem
    consumidor que justifique a separação agora.

## R11. Testes no diretório único existente

- **Decision**: novos testes em `tests/`, agrupados por preocupação: modelos, autenticação/login,
  proteção de superfícies, logout, home — não em `contas/tests/`, nem um arquivo por FR.
- **Rationale**: segue a convenção já estabelecida (`pyproject.toml`: `testpaths = ["tests"]`,
  hoje com `test_infrastructure.py` e `test_settings.py` no mesmo diretório plano). Introduzir
  `contas/tests/` agora criaria duas convenções conflitantes de teste no mesmo projeto.

## R12. Templates e CSS

- **Decision**: `contas/templates/contas/base.html` (local ao app) estendido por `login.html` e
  `home.html`. Tokens/reset compartilhados em `static/css/tokens.css` e `static/css/base.css` no
  nível do projeto (exige adicionar `STATICFILES_DIRS = [BASE_DIR / "static"]`, hoje ausente de
  `config/settings/base.py`); CSS específico de página em
  `contas/static/contas/css/{login,home}.css`. Sem HTMX nesta feature.
- **Rationale**: tokens de `DESIGN.md` (cores, tipografia, espaçamento) são cross-cutting por
  definição — pertencem ao projeto, não a um app específico; como não há hoje nenhum diretório de
  estático global configurado, esta feature precisa criá-lo (Constitution, Princípio VIII exige
  tokens CSS compartilhados desde o início). Um `base.html` de projeto (fora de qualquer app) fica
  deliberadamente adiado até existir um segundo app que precise dele — hoje seria especulativo.
  HTMX não traz ganho concreto em fluxos de request/redirect completos como login/logout.

## R13. Configuração centralizada

- **Decision**: `AUTH_USER_MODEL = "contas.User"`, `LOGIN_URL = "login"`,
  `LOGIN_REDIRECT_URL = "home"`, `LOGOUT_REDIRECT_URL = "login"`,
  `STATICFILES_DIRS = [BASE_DIR / "static"]`, `INSTALLED_APPS += ["contas"]` e `MIDDLEWARE +=
  ["contas.middleware.RetornoPosLoginMiddleware"]` em `config/settings/base.py`; a rota de
  `contas.urls` incluída em `config/urls.py`. **Nenhum `handler403` é definido** (ver R8 revisado).
- **Rationale**: são mudanças de infraestrutura do projeto (não do domínio/spec), no único lugar
  onde já vivem essas configurações.

## R14. Uma única migration inicial

- **Decision**: `contas/migrations/0001_initial.py`, criando `User`, `Setor`, `PapelUsuario` numa
  única migration.
- **Rationale**: é o momento mais seguro possível para fixar o modelo de usuário — nenhuma outra
  migration do projeto ainda existe, então não há FK de outra feature apontando para o `User` a ser
  quebrada ou recriada depois.

## R15. Nenhuma nova dependência

- **Decision**: usar apenas `django` (auth, sessions, admin — já instalados como apps contrib) e
  `psycopg` (já presente). Nenhuma biblioteca nova.
- **Rationale**: nenhum problema identificado nesta feature exige recurso que o Django não resolva
  nativamente (Princípio XI).

## R16. Sem política de senha nova; sem campo de nome/exibição

- **Decision**: os `AUTH_PASSWORD_VALIDATORS` já configurados em `config/settings/base.py`
  permanecem sem alteração (não fazem parte desta mudança). Nenhum campo de nome/apelido de
  exibição é adicionado ao `User`.
- **Rationale**: a spec não pede política de senha nova nem exibição de nome amigável; adicionar
  qualquer um dos dois seria inventar requisito de produto. Registrado em Open Questions do
  `plan.md` como nota não bloqueante.

## Resumo — nenhum "NEEDS CLARIFICATION" técnico restante

Todas as incógnitas técnicas desta feature foram resolvidas acima usando exclusivamente capacidades
já maduras do Django, sem introduzir regra de negócio nova. Nenhum bloqueio técnico impede a
Fase 1 (Design & Contracts).
