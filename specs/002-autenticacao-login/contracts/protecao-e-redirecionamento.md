# Contrato interno: rotas, proteção de superfícies e redirecionamento

Esta feature não expõe API REST nem contrato externo — é uma aplicação Django server-rendered.
"Contrato", aqui, é o conjunto de rotas, mecanismos reutilizáveis e sinais que esta feature entrega
para uso próprio e para consumo por `001-importacao-catalogo-materiais` e futuras features (ver
`spec.md` → Regras canônicas aplicáveis; `research.md` R7–R9).

> **Revisão 1**: corrigiu duas imprecisões — (1) a rota `logout` não exige sessão autenticada; (2)
> o fallback de "não autorizado → Home" deixou de usar `handler403` global. O mecanismo de
> "proteção de superfícies" passou a ser o uso direto de `login_required`/`LoginRequiredMixin`
> nativos, porque o framework já rejeita conta desativada em qualquer requisição subsequente (ver
> `research.md`, R9). Eliminados `WMSLogoutView` e a antiga proposta de form customizado para
> rótulo/tamanho (sem responsabilidade real). `contas/forms.py` foi depois reintroduzido somente
> para corrigir a mensagem pt-BR de recusa, sem alterar campos nem autenticação (R3, revisão 3).
>
> **Revisão 2** (esta versão): o marcador de retorno pós-login deixou de viver na query string
> (`?_retorno_pos_login=1`) — controlável pelo cliente, sem expiração real — e passou a viver em
> **sessão**, vinculado ao destino exato (path + query), consumido uma única vez por
> `process_view()` antes da view rodar. Corrigido também: `django.urls.resolve()` recebia a URL
> completa do `next`, incluindo query string — **verificado empiricamente** que isso quebra o
> casamento de padrão (`resolve("/catalogo/?pagina=2")` levanta `Resolver404`, enquanto
> `resolve("/catalogo/")` funciona); agora só o `path` vai para `resolve()`. `PapelUsuario` passou a
> declarar sua constraint via `UniqueConstraint` (`Meta.constraints`), não `unique_together`.

## Rotas expostas pelo app `contas`

| Rota (nome) | Método(s) | View | Autenticação exigida | Comportamento |
|---|---|---|---|---|
| `login` | `GET`, `POST` | `WMSLoginView(LoginView)` | Nenhuma (mas ver "usuário já autenticado" abaixo) | `GET` renderiza o formulário (matrícula + senha); `POST` autentica e redireciona conforme "Resolução do destino pós-login" |
| `logout` | `POST` (apenas) | `LogoutView` nativo (sem subclasse — nenhum override necessário, ver `research.md`, R7) | **Não obrigatória** — `LogoutView.post()` chama `django.contrib.auth.logout()` incondicionalmente; sem sessão válida, é um no-op seguro (ver `research.md`, R7) | Com sessão válida → encerra a sessão e redireciona para `login`; sem sessão válida → redireciona para `login` do mesmo jeito, sem erro nem mensagem que revele diferença |
| `home` | `GET` | `HomeView` | Sim (via `LoginRequiredMixin` nativo) | Renderiza a Home autenticada mínima |

Usuário já autenticado que acessa `GET login` diretamente é redirecionado para `home`
(`FR-012`) — usando a opção nativa `redirect_authenticated_user` do próprio `LoginView`, não uma
checagem própria.

## Proteção de superfícies: mecanismo nativo, sem wrapper

Contrato que `001` e demais features devem seguir para proteger suas próprias views — **esta
feature não protege nada além de `home`**, apenas estabelece o padrão a reutilizar.

```python
# Function-based views:
from django.contrib.auth.decorators import login_required

@login_required
def minha_view(request): ...

# Class-based views:
from django.contrib.auth.mixins import LoginRequiredMixin

class MinhaView(LoginRequiredMixin, View): ...
```

Nenhum wrapper próprio é necessário — ambos os utilitários nativos checam
`request.user.is_authenticated`, e isso já basta porque `request.user` já é `AnonymousUser()` para
uma conta desativada (`is_active=False`), em qualquer requisição a partir da desativação, por
comportamento nativo do `AuthenticationMiddleware`/`ModelBackend` (verificado em `research.md`, R9).

**Garantias do contrato**:
- Visitante sem sessão válida → redirecionado para `login` com `?next=<destino>` (`FR-008`,
  `FR-009`).
- Usuário autenticado cuja conta se tornou inativa → tratado exatamente como não autenticado na
  próxima requisição que passar por `login_required`/`LoginRequiredMixin` (`FR-006`,
  `INV-AUTH-001`) — não há distinção de mensagem entre "nunca autenticou" e "foi desativado depois",
  porque ambos os casos chegam como `AnonymousUser()`.
- Qualquer feature futura que precise exigir sessão autenticada usa `login_required`/
  `LoginRequiredMixin` diretamente, sem reimplementar nem importar nada de `contas`, e **sem
  precisar cooperar manualmente** com o mecanismo de fallback pós-login descrito abaixo — ele age
  de fora, via middleware, para qualquer view.

## Resolução segura do destino pós-login (`next`)

Aplicável apenas ao `POST login` bem-sucedido.

```text
next presente?
  não → destino = home (LOGIN_REDIRECT_URL)
  sim:
    url_has_allowed_host_and_scheme(next, allowed_hosts={request.get_host()})? [nativo do LoginView]
      não → destino = home
      sim:
        caminho = urlsplit(next).path        # SÓ o path — nunca a query string
        resolve(caminho) não levanta Resolver404?
          não → destino = home
          sim → destino = next completo (path + query original preservada)
```

- Cobre `FR-010` (interno + existente) e `FR-011` (nunca externo).
- **Importante**: `django.urls.resolve()` não aceita query string — verificado empiricamente contra
  o Django instalado que `resolve("/catalogo/?pagina=2")` levanta `Resolver404` enquanto
  `resolve("/catalogo/")` corresponde normalmente. Por isso o path é separado da query
  (`urllib.parse.urlsplit(next).path`) antes de chamar `resolve()` — a query string legítima (ex.:
  `?pagina=2&ordenacao=descricao`) nunca é perdida, ela só não participa da checagem de existência.
- O fragmento (`#...`) nunca é enviado ao servidor em uma requisição HTTP; não há nada a considerar
  quanto a ele.
- A condição "autorizado" (terceira condição de `FR-010`) é resolvida pelo mecanismo da seção
  seguinte, não aqui.
- `SC-005`/`SC-006` da spec são verificados por este fluxo.

## Fallback de autorização — marcador de sessão de uso único, vinculado ao destino exato

> Não usa `handler403` global (rejeitado — ver `research.md`, R8) nem marcador na query string
> (rejeitado nesta revisão — controlável pelo cliente, não expira).

```python
# contas/views.py — WMSLoginView(LoginView)
MARCADOR_SESSAO = "_retorno_pos_login_destino"

def get_success_url(self):
    url = self.get_redirect_url()          # já validado: interno + existente (seção anterior)
    if url:
        self.request.session[self.MARCADOR_SESSAO] = url   # destino EXATO esperado
        return url                                          # redirect normal — SEM parâmetro na URL
    return self.get_default_redirect_url()
```

```python
# contas/middleware.py
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

class RetornoPosLoginMiddleware:
    """process_view: reconhece (e consome) a tentativa de retorno pós-login,
    marcando só o objeto request desta requisição. process_exception: só
    converte PermissionDenied em redirect para Home quando essa marca existe
    NESTA requisição. Qualquer outro PermissionDenied vira o 403 padrão."""

    MARCADOR_SESSAO = "_retorno_pos_login_destino"
    ATRIBUTO_REQUEST = "_retorno_pos_login"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        destino_pendente = request.session.get(self.MARCADOR_SESSAO)
        if destino_pendente is not None and request.get_full_path() == destino_pendente:
            del request.session[self.MARCADOR_SESSAO]        # consumido — uso único
            setattr(request, self.ATRIBUTO_REQUEST, True)      # flag privada só neste request
        return None                                            # nunca impede a view de rodar

    def process_exception(self, request, exception):
        if isinstance(exception, PermissionDenied) and getattr(request, self.ATRIBUTO_REQUEST, False):
            return redirect("home")
        return None
```

Registrado em `MIDDLEWARE` (`config/settings/base.py`). **Nenhum `handler403` é definido** —
`config/urls.py` não é alterado para esse fim. **Nenhum parâmetro técnico é adicionado à URL** —
o `Location` do redirect e a URL que o usuário efetivamente visita são a URL de destino pura.

**Por que isso é realmente uso único e não falsificável via URL**:
1. O marcador nunca aparece na URL — vive só em `request.session`, do lado do servidor. Adicionar
   `?_retorno_pos_login=1` manualmente a qualquer URL não tem nenhum efeito: nada no middleware lê
   a query string para essa decisão.
2. `process_view` roda antes da view em toda requisição (hook nativo, verificado no código-fonte
   instalado: `django/core/handlers/base.py`, registrado via `hasattr(mw_instance,
   "process_view")` — o mesmo padrão usado por `process_exception`) e só marca o `request` quando o
   **path + query string da requisição atual** (`request.get_full_path()`) bate exatamente com o
   destino gravado na sessão pelo login — nunca por prefixo, nunca só pelo path.
3. O valor é removido da sessão (`del request.session[...]`) no exato momento em que é reconhecido,
   antes mesmo de a view rodar — uma segunda visita à mesma URL depois não encontra mais o
   marcador, então não recebe a flag.
4. `process_exception` só age quando o **atributo do objeto `request` desta mesma requisição** foi
   definido por `process_view` — um dado interno do processo da requisição, nunca algo que trafega
   entre cliente e servidor, portanto impossível de forjar de fora.
5. Comparação por igualdade exata de string, nunca por prefixo — evita que `/materiais/123/x` seja
   tratado como o mesmo destino que `/materiais/123/`.
6. Se a requisição atual não bater com o destino pendente, `process_view` não faz nada — o
   marcador de sessão permanece aguardando a requisição correta (deliberado; ver `research.md`, R8,
   "Impacto conhecido").

**Garantias**:
1. Um `PermissionDenied` **sem** a flag de request (qualquer 403 comum, hoje ou de uma feature
   futura) continua resultando no 403 padrão do Django, inalterado.
2. A flag identifica exata e apenas a tentativa de retorno que se originou do redirecionamento de
   login, para o destino exato esperado.
3. O fallback para a Home só se aplica nesse contexto específico, nunca globalmente.
4. O login não precisa conhecer nenhuma regra de autorização de nenhuma feature — só sabe que a
   requisição real (não simulada) para aquele destino falhou por `PermissionDenied` logo depois de
   ter sido redirecionada para lá.
5. Nenhuma view de destino é executada antecipadamente — o `PermissionDenied` só é capturado quando
   o navegador de fato faz a requisição real para aquela rota, no ciclo normal de request/response.

Testável nesta feature com uma view fictícia que sempre levanta `PermissionDenied` — um teste
chegando via login (com o destino em sessão) cai na Home; o mesmo teste repetido depois, sem ter
passado pelo login (sem marcador em sessão), ou com `?_retorno_pos_login=1` adicionado manualmente
à URL, mostra o 403 padrão — provando que o mecanismo não afeta 403 genéricos do sistema nem é
manipulável via URL.

## Contrato exposto para `001-importacao-catalogo-materiais` e demais features

Após esta feature, qualquer view autenticada pode presumir, quando `request.user.is_authenticated`
(verificado via `login_required`/`LoginRequiredMixin` nativos):

| Necessidade | Como obter |
|---|---|
| Identidade do usuário autenticado | `request.user` (instância de `contas.models.User`) |
| Conta ativa | Já garantido — `request.user.is_authenticated` só é `True` para conta ativa (ver R9) |
| Setor do usuário | `request.user.setor` (sempre presente, nunca `None` — `INV-ORG-001`) |
| Papéis explicitamente atribuídos | `request.user.papeis.all()` ou `request.user.tem_papel(Papel.CHEFE_ALMOXARIFADO, ...)` |
| Exigir autenticação numa view | `@login_required` (função) ou `LoginRequiredMixin` (classe) — nativos do Django |
| Recusar por falta de autorização de negócio | `raise PermissionDenied` na própria view — mostra o 403 padrão do Django, **exceto** quando a requisição é reconhecida como o retorno imediato pós-login para esse destino exato (ver seção anterior), caso em que cai na Home |

Nenhuma feature futura precisa fazer nada especial para o fallback funcionar — basta levantar
`PermissionDenied` normalmente; o reconhecimento do contexto "veio do login" é responsabilidade
inteira do middleware desta feature.

**Fora deste contrato** (permanece responsabilidade de cada feature de negócio): decidir *quais*
papéis autorizam *qual* operação — isso é a `permissions-matrix.md`, aplicada em código por quem
consome este contrato, nunca por `contas`.
