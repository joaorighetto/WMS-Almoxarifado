"""Urlconf de teste dedicado à Phase 4 (User Story 2) — T024.

Não é código de produção: vive exclusivamente em `tests/`, ativado via
`@pytest.mark.urls("tests.urls_test_permission_denied")` pelos testes de
`tests/test_contas_protected_access.py` (T025).

Expõe:

- `destino_nao_autorizado`: view protegida (`login_required`) que sempre
  levanta `PermissionDenied` — representa um destino interno, existente,
  mas NÃO autorizado ao usuário autenticado (a decisão de autorização de
  negócio em si é responsabilidade de cada feature; aqui ela é simulada
  diretamente, como o contrato de `contracts/protecao-e-redirecionamento.md`
  prevê para o teste do fallback de sessão).
- `destino_autorizado`: view protegida (`login_required`) sempre autorizada,
  que ignora qualquer query string recebida e responde 200 — representa um
  destino interno, existente e autorizado, usado tanto para o retorno seguro
  simples quanto para o cenário com query string (`?pagina=2&ordenacao=...`).
- as rotas `login`/`home` de `contas.urls` (via `include`), porque
  `RetornoPosLoginMiddleware.process_exception()` redireciona para `home`, e
  o próprio fluxo de autenticação usado pelos testes precisa de `login`.
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.urls import include, path


@login_required
def destino_nao_autorizado(request):
    raise PermissionDenied


@login_required
def destino_autorizado(request):
    return HttpResponse("destino autorizado", status=200)


urlpatterns = [
    path("destino-nao-autorizado/", destino_nao_autorizado, name="destino_nao_autorizado"),
    path("destino-autorizado/", destino_autorizado, name="destino_autorizado"),
    path("", include("contas.urls")),
]
