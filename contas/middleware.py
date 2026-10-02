from django.conf import settings
from django.contrib.auth import logout
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect, resolve_url
from django.urls import reverse

from contas.credenciais import provisoria_vencida


class CredencialProvisoriaMiddleware:
    """Mantém quem tem credencial provisória na definição da própria senha (FR-032, research
    R10, `contracts/credenciais.md`).

    Para usuário autenticado com `senha_provisoria_em`: provisória vencida encerra a sessão e
    leva ao login; fora isso, só `definir_senha`, `logout` e os arquivos estáticos seguem — toda
    outra rota (GET ou POST, inclusive o Admin) é redirecionada a `definir_senha`, com
    `HX-Redirect` quando a requisição é HTMX. Anônimo, inativo e quem já definiu a senha passam
    sem custo extra. Fica logo depois da autenticação e antes do `RetornoPosLoginMiddleware`,
    para que o marcador de retorno não seja gasto por uma requisição que a restrição barrou.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = request.user
        if usuario.is_authenticated and usuario.senha_provisoria_em is not None:
            if provisoria_vencida(usuario):
                logout(request)
                return self._redirecionar(request, resolve_url(settings.LOGIN_URL))
            if not self._liberada(request):
                return self._redirecionar(request, reverse("definir_senha"))
        return self.get_response(request)

    @staticmethod
    def _liberada(request):
        return request.path in {reverse("definir_senha"), reverse("logout")} or (
            request.path.startswith(settings.STATIC_URL)
        )

    @staticmethod
    def _redirecionar(request, destino):
        if request.headers.get("HX-Request") == "true":
            resposta = HttpResponse()
            resposta["HX-Redirect"] = destino
            return resposta
        return redirect(destino)


class RetornoPosLoginMiddleware:
    """Fallback de autorização — marcador de sessão de uso único, vinculado
    ao destino exato (User Story 2).

    `process_view` reconhece (e consome) a tentativa de retorno pós-login,
    marcando só o objeto `request` desta requisição. `process_exception` só
    converte `PermissionDenied` em redirect para a Home quando essa marca
    existe NESTA requisição. Qualquer outro `PermissionDenied` vira o 403
    padrão do Django, inalterado.

    Ver `contracts/protecao-e-redirecionamento.md` e `research.md` R8.
    """

    MARCADOR_SESSAO = "_retorno_pos_login_destino"
    ATRIBUTO_REQUEST = "_retorno_pos_login"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        destino_pendente = request.session.get(self.MARCADOR_SESSAO)
        if destino_pendente is not None and request.get_full_path() == destino_pendente:
            del request.session[self.MARCADOR_SESSAO]
            setattr(request, self.ATRIBUTO_REQUEST, True)
        return None

    def process_exception(self, request, exception):
        if isinstance(exception, PermissionDenied) and getattr(
            request, self.ATRIBUTO_REQUEST, False
        ):
            return redirect("home")
        return None
