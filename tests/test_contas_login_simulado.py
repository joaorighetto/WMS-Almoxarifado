"""Login simulado por papel (`contas/login_simulado.py`, só em desenvolvimento).

Protege as duas metades do contrato: (1) o middleware nunca age fora de
`DEBUG` + `WMS_LOGIN_SIMULADO` e nunca é carregado pelas settings de test ou
production; (2) quando age, autentica uma conta REAL — a autorização das rotas
continua a da conta (403 permanece 403), nada é simulado além do formulário.
"""

import importlib

import pytest
from django.conf import settings as django_settings
from django.urls import reverse

from contas.login_simulado import COOKIE, PARAMETRO
from contas.models import Papel

MIDDLEWARE_SIMULADO = "contas.login_simulado.LoginSimuladoMiddleware"


@pytest.fixture
def login_simulado(settings):
    """Liga o middleware como `config/settings/development.py` faz."""
    settings.DEBUG = True
    settings.WMS_LOGIN_SIMULADO = True
    settings.WMS_LOGIN_SIMULADO_PADRAO = "funcionario-almoxarifado"
    posicao = settings.MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware")
    settings.MIDDLEWARE = [
        *settings.MIDDLEWARE[: posicao + 1],
        MIDDLEWARE_SIMULADO,
        *settings.MIDDLEWARE[posicao + 1 :],
    ]
    return settings


@pytest.fixture
def contas_seed(criar_usuario_com_papeis):
    """Subconjunto das matrículas de `CONTA_POR_PAPEL`, com os mesmos papéis do seed."""
    return {
        "funcionario": criar_usuario_com_papeis(
            Papel.FUNCIONARIO_ALMOXARIFADO, matricula="funcionario"
        ),
        "requisitante": criar_usuario_com_papeis(matricula="requisitante"),
        "auditor": criar_usuario_com_papeis(Papel.AUDITOR, matricula="auditor"),
    }


def _usuario_da_sessao(client):
    return client.session.get("_auth_user_id")


# --- Guardas de ambiente ---------------------------------------------------


def test_settings_de_teste_nao_carregam_o_middleware():
    assert MIDDLEWARE_SIMULADO not in django_settings.MIDDLEWARE


def test_settings_de_producao_nao_carregam_o_middleware(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "x" * 50)
    producao = importlib.import_module("config.settings.production")
    assert MIDDLEWARE_SIMULADO not in producao.MIDDLEWARE
    assert not getattr(producao, "WMS_LOGIN_SIMULADO", False)


def test_settings_de_desenvolvimento_nao_contaminam_a_base(monkeypatch):
    """`development.py` monta uma lista nova: o `MIDDLEWARE` de `base.py`, compartilhado por
    `from .base import *` com production/test, não pode ganhar o middleware."""
    monkeypatch.setenv("DJANGO_DEBUG", "True")
    monkeypatch.setenv("WMS_LOGIN_SIMULADO", "True")
    base = importlib.import_module("config.settings.base")
    desenvolvimento = importlib.reload(importlib.import_module("config.settings.development"))
    assert MIDDLEWARE_SIMULADO in desenvolvimento.MIDDLEWARE
    assert MIDDLEWARE_SIMULADO not in base.MIDDLEWARE


def test_desenvolvimento_sem_debug_nao_carrega(monkeypatch):
    monkeypatch.setenv("DJANGO_DEBUG", "False")
    monkeypatch.setenv("WMS_LOGIN_SIMULADO", "True")
    desenvolvimento = importlib.reload(importlib.import_module("config.settings.development"))
    assert MIDDLEWARE_SIMULADO not in desenvolvimento.MIDDLEWARE


@pytest.mark.parametrize("debug, ligado", [(False, True), (True, False)])
def test_middleware_se_desliga_sem_debug_ou_sem_flag(
    login_simulado, contas_seed, client, debug, ligado
):
    login_simulado.DEBUG = debug
    login_simulado.WMS_LOGIN_SIMULADO = ligado

    resposta = client.get(reverse("home"))

    assert resposta.status_code == 302
    assert resposta.url.startswith(reverse("login"))
    assert _usuario_da_sessao(client) is None


# --- Comportamento ---------------------------------------------------------


def test_visitante_anonimo_entra_com_a_identidade_padrao(login_simulado, contas_seed, client):
    resposta = client.get(reverse("home"))

    assert resposta.status_code == 200
    assert resposta.context["user"] == contas_seed["funcionario"]


def test_dev_como_troca_identidade_e_redireciona_sem_o_parametro(
    login_simulado, contas_seed, client
):
    resposta = client.get(reverse("fornecedores:consulta") + f"?pagina=2&{PARAMETRO}=auditor")

    assert resposta.status_code == 302
    assert resposta.url == reverse("fornecedores:consulta") + "?pagina=2"
    assert resposta.cookies[COOKIE].value == "auditor"
    assert _usuario_da_sessao(client) == str(contas_seed["auditor"].pk)

    # A escolha persiste nas navegações seguintes.
    assert client.get(reverse("home")).context["user"] == contas_seed["auditor"]


def test_identidade_simulada_mantem_a_autorizacao_real(login_simulado, contas_seed, client):
    """Requisitante não tem `PERM-SCPI-IMPORT-EXECUTE` nem `PERM-SUPPLIER-VIEW`: o login
    simulado não muda isso."""
    client.get(reverse("home") + f"?{PARAMETRO}=requisitante")

    assert client.get(reverse("catalogo:importacao_envio")).status_code == 403
    assert client.get(reverse("fornecedores:consulta")).status_code == 403


def test_dev_como_aceita_matricula_de_conta_ativa(login_simulado, contas_seed, client):
    client.get(reverse("home") + f"?{PARAMETRO}={contas_seed['requisitante'].matricula}")

    assert _usuario_da_sessao(client) == str(contas_seed["requisitante"].pk)


def test_anonimo_sai_e_para_de_autenticar(login_simulado, contas_seed, client):
    client.get(reverse("home"))
    assert _usuario_da_sessao(client) is not None

    resposta = client.get(reverse("login") + f"?{PARAMETRO}=anonimo")
    assert resposta.status_code == 302
    assert _usuario_da_sessao(client) is None

    assert client.get(reverse("login")).status_code == 200
    home = client.get(reverse("home"))
    assert home.status_code == 302
    assert home.url.startswith(reverse("login"))


@pytest.mark.parametrize("identidade", ["papel-inexistente", "conta.inativa"])
def test_identidade_invalida_ou_inativa_e_recusada(
    login_simulado, contas_seed, criar_usuario, client, identidade
):
    criar_usuario(matricula="conta.inativa", is_active=False)

    resposta = client.get(reverse("home") + f"?{PARAMETRO}={identidade}")

    assert resposta.status_code == 400
    assert COOKIE not in resposta.cookies
    assert _usuario_da_sessao(client) is None


def test_post_anonimo_nao_e_autenticado(login_simulado, contas_seed, client):
    """`login()` rotaciona o token CSRF; autenticar no meio de um POST o invalidaria."""
    resposta = client.post(reverse("catalogo:importacao_envio"))

    assert resposta.status_code == 302
    assert resposta.url.startswith(reverse("login"))
    assert _usuario_da_sessao(client) is None


def test_login_pelo_formulario_nao_e_sobrescrito(login_simulado, contas_seed, client):
    client.force_login(contas_seed["auditor"])

    assert client.get(reverse("home")).context["user"] == contas_seed["auditor"]


def test_rota_inexistente_nao_cria_sessao(login_simulado, contas_seed, client):
    """Um 404 (ex.: `/favicon.ico`, buscado sem cookies) não dispara o login automático."""
    resposta = client.get("/favicon.ico")

    assert resposta.status_code == 404
    assert _usuario_da_sessao(client) is None


def test_requisicao_fora_de_loopback_e_ignorada(login_simulado, contas_seed, client):
    resposta = client.get(
        reverse("home") + f"?{PARAMETRO}=auditor", REMOTE_ADDR="192.168.0.10"
    )

    assert resposta.status_code == 302
    assert resposta.url.startswith(reverse("login"))
    assert _usuario_da_sessao(client) is None


def test_redirect_da_troca_nao_sai_do_host(login_simulado, contas_seed, rf):
    """`/%2Foutro-host/` chega como path `//outro-host/`; sem escape, o `Location` seria um
    redirect relativo ao protocolo para outro host."""
    from django.contrib.auth.models import AnonymousUser
    from django.contrib.sessions.backends.db import SessionStore
    from django.http import HttpResponse

    from contas.login_simulado import LoginSimuladoMiddleware

    request = rf.get("/", {PARAMETRO: "anonimo"})
    request.path = request.path_info = "//outro-host.example/"
    request.session = SessionStore()
    request.user = AnonymousUser()

    resposta = LoginSimuladoMiddleware(lambda r: HttpResponse())(request)

    assert resposta.status_code == 302
    assert not resposta["Location"].startswith("//")


def test_sem_conta_no_banco_segue_anonimo(login_simulado, db, client):
    resposta = client.get(reverse("home"))

    assert resposta.status_code == 302
    assert resposta.url.startswith(reverse("login"))
