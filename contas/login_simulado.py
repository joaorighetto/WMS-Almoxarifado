"""Login simulado por papel — exclusivo do ambiente de desenvolvimento.

Tira a barreira do formulário de login para quem verifica a interface (o
`impeccable critique`, capturas, navegação de agentes) sem simular permissão:
o middleware autentica, por `django.contrib.auth.login`, uma conta REAL do
`seed_dev` (`contas/dev_seed/dados.py` → `CONTA_POR_PAPEL`). Papéis, setor e
autorização das rotas são exatamente os da conta — um 403 continua 403.

Uso, em qualquer GET:

- `?dev_como=<papel>` troca a identidade (ex.: `funcionario-almoxarifado`,
  `auditor`) e redireciona para a mesma URL sem o parâmetro;
- `?dev_como=<matricula>` autentica uma conta ativa específica do banco;
- `?dev_como=anonimo` sai e deixa de autenticar automaticamente (para ver
  `/login/`, por exemplo).

A escolha fica num cookie; sem ele vale `WMS_LOGIN_SIMULADO_PADRAO`. Um
visitante anônimo é autenticado automaticamente só em GET/HEAD de rota existente — `login()`
rotaciona o token CSRF, o que invalidaria um POST em curso. Um login feito
pelo formulário normal não é sobrescrito, exceto por `?dev_como=` explícito.

Só é carregado por `config/settings/development.py`, ainda se desliga
(`MiddlewareNotUsed`) sem `DEBUG` e `WMS_LOGIN_SIMULADO` verdadeiros e só atende
requisições vindas de loopback (127.0.0.1/::1).
"""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model, login, logout
from django.core.exceptions import MiddlewareNotUsed
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect
from django.utils.http import escape_leading_slashes

from contas.dev_seed.dados import CONTA_POR_PAPEL

logger = logging.getLogger("contas.login_simulado")

PARAMETRO = "dev_como"
COOKIE = "wms_dev_como"
ANONIMO = "anonimo"
METODOS_SEGUROS = ("GET", "HEAD")
# Só quem acessa pela própria máquina: um `runserver 0.0.0.0` não abre o app sem senha à rede.
ENDERECOS_LOCAIS = ("127.0.0.1", "::1")


class LoginSimuladoMiddleware:
    def __init__(self, get_response):
        if not (settings.DEBUG and getattr(settings, "WMS_LOGIN_SIMULADO", False)):
            raise MiddlewareNotUsed
        self.get_response = get_response
        self.padrao = getattr(settings, "WMS_LOGIN_SIMULADO_PADRAO", "chefe-almoxarifado")
        logger.warning(
            "Login simulado ATIVO (identidade padrão: %s). Troque com ?%s=<papel>; "
            "papéis: %s, %s.",
            self.padrao, PARAMETRO, ", ".join(CONTA_POR_PAPEL), ANONIMO,
        )

    def __call__(self, request):
        if not _aplicavel(request):
            return self.get_response(request)

        pedido = request.GET.get(PARAMETRO)
        if pedido is not None:
            return self._trocar_identidade(request, pedido.strip())
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Em `process_view`, e não em `__call__`, para autenticar só requisições que chegam a
        # uma view: um 404 (como o `/favicon.ico` que o navegador busca sem cookies) não cria
        # sessão descartável.
        if not _aplicavel(request):
            return None
        identidade = request.COOKIES.get(COOKIE) or self.padrao
        if identidade != ANONIMO and not request.user.is_authenticated:
            usuario = _conta(identidade)
            if usuario is None:
                logger.warning(
                    "Login simulado: identidade %r sem conta ativa no banco.", identidade
                )
            else:
                self._entrar(request, usuario)
        return None

    def _trocar_identidade(self, request, identidade):
        if identidade == ANONIMO:
            logout(request)
        else:
            usuario = _conta(identidade)
            if usuario is None:
                return HttpResponseBadRequest(
                    f"Login simulado: {identidade!r} não é papel conhecido nem matrícula de "
                    f"conta ativa. Papéis: {', '.join(CONTA_POR_PAPEL)}, {ANONIMO}. "
                    "As contas vêm do seed_dev (make seed_dev).",
                    content_type="text/plain; charset=utf-8",
                )
            if request.user != usuario:
                self._entrar(request, usuario)

        restante = request.GET.copy()
        del restante[PARAMETRO]
        # `escape_leading_slashes`: um path `//outro-host/` (via `/%2Foutro-host/`) viraria
        # redirect relativo ao protocolo para outro host.
        destino = escape_leading_slashes(request.path)
        if restante:
            destino += f"?{restante.urlencode()}"
        resposta = redirect(destino)
        resposta.set_cookie(COOKIE, identidade, httponly=True, samesite="Lax")
        return resposta

    @staticmethod
    def _entrar(request, usuario):
        login(request, usuario, backend=settings.AUTHENTICATION_BACKENDS[0])
        logger.info("Login simulado: %s.", usuario.matricula)


def _aplicavel(request):
    return (
        request.method in METODOS_SEGUROS
        and request.META.get("REMOTE_ADDR") in ENDERECOS_LOCAIS
    )


def _conta(identidade):
    """Conta ativa correspondente ao papel (via `CONTA_POR_PAPEL`) ou à matrícula informada.
    Conta inativa não serve: `ModelBackend.get_user()` a descartaria na requisição seguinte."""
    matricula = CONTA_POR_PAPEL.get(identidade, identidade)
    return get_user_model().objects.filter(matricula=matricula, is_active=True).first()
