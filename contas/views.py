from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.shortcuts import resolve_url
from django.urls import resolve
from django.urls.exceptions import Resolver404
from django.views.generic import TemplateView


class WMSLoginView(LoginView):
    """Login com resolução segura do destino pós-login (`next`, User Story 2).

    `get_redirect_url()` reaproveita a checagem nativa de host/esquema de
    `RedirectURLMixin` (`url_has_allowed_host_and_scheme`, cobre `FR-011`) e
    adiciona a checagem de existência de rota via `django.urls.resolve()` —
    só o `path` é passado a `resolve()` (nunca a URL completa: `query
    string` quebra o casamento de padrão, ver `research.md` R8).

    `get_success_url()` grava, em sessão, o destino exato (path + query)
    concedido, para consumo único por `RetornoPosLoginMiddleware` (ver
    `contracts/protecao-e-redirecionamento.md`). Nenhum parâmetro técnico é
    adicionado à URL de redirecionamento.
    """

    MARCADOR_SESSAO = "_retorno_pos_login_destino"

    def get_redirect_url(self, request=None):
        url = super().get_redirect_url(request)
        if not url:
            return ""
        caminho = urlsplit(url).path
        try:
            resolve(caminho)
        except Resolver404:
            return ""
        # `next` apontando para a própria página de login: o `LoginView` nativo
        # levanta ValueError ("Redirection loop for authenticated user detected")
        # quando `redirect_authenticated_user=True` e o destino é o próprio path —
        # um 500 acionável por link enviado a quem já está autenticado.
        if caminho == urlsplit(resolve_url(settings.LOGIN_URL)).path:
            return ""
        return url

    def form_valid(self, form):
        # O marcador é gravado SOMENTE aqui, depois de um login efetivamente
        # bem-sucedido. Gravá-lo em `get_success_url()` não serve: o
        # `LoginView.dispatch()` nativo também chama esse método para um usuário
        # já autenticado (`redirect_authenticated_user`), o que permitiria armar o
        # marcador por `GET /login/?next=...` — escrita de estado de sessão sem
        # autenticação e sem CSRF, mascarando como Home um 403 legítimo posterior
        # (contracts/protecao-e-redirecionamento.md → Garantias 2 e 3).
        #
        # A escrita vem depois de `super()`, porque `auth_login()` cicla a chave de
        # sessão; gravar antes perderia o valor.
        resposta = super().form_valid(form)
        destino = self.get_redirect_url()
        if destino:
            self.request.session[self.MARCADOR_SESSAO] = destino
        return resposta


class HomeView(LoginRequiredMixin, TemplateView):
    """Home autenticada mínima (User Story 1).

    Usa `LoginRequiredMixin` nativo — sem wrapper próprio. `request.user` já
    é `AnonymousUser()` para conta desativada em qualquer requisição
    subsequente (`ModelBackend.get_user()`, `research.md` R9), então nenhuma
    checagem manual de `is_active` é necessária aqui.
    """

    template_name = "contas/home.html"
