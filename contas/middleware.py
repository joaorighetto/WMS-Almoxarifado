from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


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
