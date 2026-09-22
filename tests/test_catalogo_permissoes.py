"""Testes de autorização das rotas do catálogo (T019 — parte de importação).

Cobre `PERM-SCPI-IMPORT-EXECUTE` e `PERM-SCPI-IMPORT-HISTORY-VIEW`
(`docs/domain/permissions-matrix.md`) e `INV-AUTH-001`
(`docs/domain/invariants-matrix.md`), conforme
`contracts/rotas-e-autorizacao.md` e `research.md` R12.

Este arquivo é compartilhado entre T019 (aqui: importação — envio, prévia,
confirmação, cancelamento e detalhe de execução), T031 (consulta) e T037
(histórico), que devem ACRESCENTAR seções próprias, seguindo o mesmo
padrão: uma tabela `ROTAS_<CONTEXTO>` de (nome da rota, método HTTP, kwargs
de `reverse`) e os quatro testes genéricos parametrizados sobre ela
(anônimo, desativado após login, sem o papel exigido, com o papel exigido).
Não reaproveite `ROTAS_IMPORTACAO` para outra capability — cada contexto tem
seu próprio papel exigido e sua própria tabela.

TDD: escrito antes de `catalogo/urls.py` registrar qualquer rota e antes das
views existirem (T026). Todas as chamadas de `reverse()` ficam dentro do
corpo dos testes (nunca em `pytest.param`/decorador), para que a ausência da
rota derrube só o teste que a usa, não a coleta do arquivo.
"""

from urllib.parse import urlsplit

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db

# Chave de sessão do pedido de prévia — valor fixado literalmente em
# `contracts/interface-importacao.md` (`CHAVE_SESSAO_PREVIA`). Usada aqui
# como string, sem importar `catalogo.importacao` (evita acoplar este teste
# de autorização à existência do módulo de domínio).
_CHAVE_SESSAO_PREVIA = "catalogo_importacao_previa"

# ---------------------------------------------------------------------------
# Rotas de importação (T019) — PERM-SCPI-IMPORT-EXECUTE /
# PERM-SCPI-IMPORT-HISTORY-VIEW, papel ROLE-WAREHOUSE-HEAD.
#
# `kwargs` são os argumentos de posição/nome exigidos por `reverse()`; a
# rota de detalhe usa um pk arbitrário (nenhuma execução precisa existir: a
# autorização é decidida pelo mixin, antes de qualquer busca no banco).
# ---------------------------------------------------------------------------

ROTAS_IMPORTACAO = [
    pytest.param("catalogo:importacao_envio", "get", {}, id="importacao_envio-get"),
    pytest.param("catalogo:importacao_envio", "post", {}, id="importacao_envio-post"),
    pytest.param("catalogo:importacao_previa", "get", {}, id="importacao_previa-get"),
    pytest.param("catalogo:importacao_confirmar", "post", {}, id="importacao_confirmar-post"),
    pytest.param("catalogo:importacao_cancelar", "post", {}, id="importacao_cancelar-post"),
    pytest.param(
        "catalogo:execucao_detalhe", "get", {"args": [1]}, id="execucao_detalhe-get"
    ),
]

# Identidades de negócio que NÃO têm `ROLE-WAREHOUSE-HEAD` e por isso devem
# receber 403 nas rotas de importação — nomes de fixtures de
# `tests/conftest.py`, resolvidos via `request.getfixturevalue`.
USUARIOS_SEM_PAPEL_DE_IMPORTACAO = [
    "superusuario_tecnico",
    "requisitante",
    "funcionario_almoxarifado",
    "chefe_setor",
    "auditor",
    "admin_sistema",
]


def _login_url_esperada():
    return reverse("login")


def _eh_redirect_para_login(resposta):
    return resposta.status_code == 302 and urlsplit(resposta.url).path == _login_url_esperada()


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_IMPORTACAO)
def test_anonimo_e_redirecionado_ao_login(client, nome_rota, metodo, kwargs):
    url = reverse(nome_rota, **kwargs)

    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 302
    assert resposta.content == b""
    assert urlsplit(resposta.url).path == _login_url_esperada()


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_IMPORTACAO)
def test_chefe_do_almoxarifado_desativado_apos_login_e_tratado_como_anonimo(
    client, chefe_almoxarifado, nome_rota, metodo, kwargs
):
    """`INV-AUTH-001`: sessão ativa não sobrevive à desativação da conta —
    já coberto nativamente pela 002 (`ModelBackend.get_user()`), mas
    protegido aqui contra qualquer view de `catalogo` que porventura passe a
    cachear o usuário de outra forma."""
    client.force_login(chefe_almoxarifado)
    chefe_almoxarifado.is_active = False
    chefe_almoxarifado.save(update_fields=["is_active"])

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 302
    assert urlsplit(resposta.url).path == _login_url_esperada()


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_IMPORTACAO)
@pytest.mark.parametrize("nome_fixture_usuario", USUARIOS_SEM_PAPEL_DE_IMPORTACAO)
def test_usuario_sem_role_warehouse_head_recebe_403(
    client, request, nome_fixture_usuario, nome_rota, metodo, kwargs
):
    usuario = request.getfixturevalue(nome_fixture_usuario)
    client.force_login(usuario)

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 403, (
        f"{nome_fixture_usuario!r} não tem ROLE-WAREHOUSE-HEAD e deveria receber 403 em {nome_rota}"
    )


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_IMPORTACAO)
def test_chefe_do_almoxarifado_tem_acesso(client, chefe_almoxarifado, nome_rota, metodo, kwargs):
    """"Acesso" aqui prova que a autorização foi concedida e a requisição
    chegou à lógica da view — não que toda rota responda 200 (ex.:
    `importacao_previa` sem pedido pendente redireciona para o envio, por
    regra de negócio, não por falta de permissão)."""
    client.force_login(chefe_almoxarifado)

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code != 403
    assert not _eh_redirect_para_login(resposta)


# ---------------------------------------------------------------------------
# Envio negado: o arquivo NUNCA é validado/interpretado para quem não tem
# a capability — a autorização vem antes de tocar em `request.FILES`.
# ---------------------------------------------------------------------------


def test_post_envio_negado_nao_valida_arquivo_nem_grava_sessao(client, requisitante, csv_fixture):
    client.force_login(requisitante)
    arquivo = SimpleUploadedFile(
        "invalido.csv",
        csv_fixture("sem_coluna_obrigatoria.csv"),
        content_type="text/csv",
    )

    resposta = client.post(reverse("catalogo:importacao_envio"), {"arquivo": arquivo})

    assert resposta.status_code == 403
    assert "NOMESUBGRUPO" not in resposta.content.decode("utf-8"), (
        "um 403 de autorização não pode carregar mensagem de validação do arquivo "
        "— isso provaria que o arquivo foi interpretado antes da checagem de papel"
    )
    assert _CHAVE_SESSAO_PREVIA not in client.session


# ---------------------------------------------------------------------------
# CSRF: todo POST exige token válido, mesmo para quem tem o papel.
# ---------------------------------------------------------------------------


def test_post_sem_csrf_e_recusado_em_envio_confirmar_e_cancelar(chefe_almoxarifado):
    client_com_csrf = Client(enforce_csrf_checks=True)
    client_com_csrf.force_login(chefe_almoxarifado)

    for nome_rota in (
        "catalogo:importacao_envio",
        "catalogo:importacao_confirmar",
        "catalogo:importacao_cancelar",
    ):
        resposta = client_com_csrf.post(reverse(nome_rota), {})
        assert resposta.status_code == 403, f"{nome_rota} deveria recusar POST sem CSRF"


# ---------------------------------------------------------------------------
# Método não permitido: confirmar/cancelar só aceitam POST.
# ---------------------------------------------------------------------------


def test_get_em_confirmar_e_cancelar_e_405(client, chefe_almoxarifado):
    client.force_login(chefe_almoxarifado)

    for nome_rota in ("catalogo:importacao_confirmar", "catalogo:importacao_cancelar"):
        resposta = client.get(reverse(nome_rota))
        assert resposta.status_code == 405, f"GET em {nome_rota} deveria ser 405"


# ---------------------------------------------------------------------------
# Rota de consulta do catálogo (T031) — PERM-MATERIAL-VIEW, papel
# ROLE-REQUESTER. `create_user` concede ROLE-REQUESTER a toda identidade de
# negócio (ver `tests/conftest.py`), por isso aqui a lista de "sem o papel"
# tem só a conta técnica (`create_superuser`, sem nenhum ROLE-*) — diferente
# de `ROTAS_IMPORTACAO`, que exige ROLE-WAREHOUSE-HEAD e por isso recusa a
# maioria das identidades de negócio comuns.
# ---------------------------------------------------------------------------

ROTAS_CONSULTA = [
    pytest.param("catalogo:consulta", "get", {}, id="consulta-get"),
]

USUARIOS_SEM_PAPEL_DE_CONSULTA = [
    "superusuario_tecnico",
]

USUARIOS_COM_ROLE_REQUESTER = [
    "requisitante",
    "funcionario_almoxarifado",
    "chefe_setor",
    "auditor",
    "admin_sistema",
    "chefe_almoxarifado",
]


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_CONSULTA)
def test_consulta_anonimo_e_redirecionado_ao_login(client, nome_rota, metodo, kwargs):
    url = reverse(nome_rota, **kwargs)

    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 302
    assert resposta.content == b""
    assert urlsplit(resposta.url).path == _login_url_esperada()


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_CONSULTA)
def test_requisitante_desativado_apos_login_na_consulta_e_tratado_como_anonimo(
    client, requisitante, nome_rota, metodo, kwargs
):
    """`INV-AUTH-001`, mesmo cenário de
    `test_chefe_do_almoxarifado_desativado_apos_login_e_tratado_como_anonimo`
    (acima), aqui com `ROLE-REQUESTER` — o papel exigido pela consulta."""
    client.force_login(requisitante)
    requisitante.is_active = False
    requisitante.save(update_fields=["is_active"])

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 302
    assert urlsplit(resposta.url).path == _login_url_esperada()


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_CONSULTA)
@pytest.mark.parametrize("nome_fixture_usuario", USUARIOS_SEM_PAPEL_DE_CONSULTA)
def test_usuario_sem_role_requester_recebe_403_na_consulta(
    client, request, nome_fixture_usuario, nome_rota, metodo, kwargs
):
    usuario = request.getfixturevalue(nome_fixture_usuario)
    client.force_login(usuario)

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 403, (
        f"{nome_fixture_usuario!r} não tem ROLE-REQUESTER e deveria receber 403 em {nome_rota}"
    )


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_CONSULTA)
@pytest.mark.parametrize("nome_fixture_usuario", USUARIOS_COM_ROLE_REQUESTER)
def test_usuario_com_role_requester_acessa_a_consulta(
    client, request, nome_fixture_usuario, nome_rota, metodo, kwargs
):
    """Diferente de `ROTAS_IMPORTACAO` (`ROLE-WAREHOUSE-HEAD` só), a consulta
    aceita qualquer identidade de negócio com `ROLE-REQUESTER` — inclusive
    `chefe_almoxarifado`, que também tem o papel mínimo. Sem filtro, a rota
    sempre responde 200 (não há redirecionamento condicional a estado de
    sessão como em `importacao_previa`), por isso a asserção aqui é estrita
    (200), não apenas "não é 403"."""
    usuario = request.getfixturevalue(nome_fixture_usuario)
    client.force_login(usuario)

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 200, (
        f"{nome_fixture_usuario!r} tem ROLE-REQUESTER e deveria acessar {nome_rota}"
    )


def test_post_na_consulta_e_405(client, requisitante):
    client.force_login(requisitante)

    resposta = client.post(reverse("catalogo:consulta"))

    assert resposta.status_code == 405


# ---------------------------------------------------------------------------
# Rota de histórico de importações (T037) — PERM-SCPI-IMPORT-HISTORY-VIEW,
# papel ROLE-WAREHOUSE-HEAD (`contracts/rotas-e-autorizacao.md`). Mesma matriz
# de usuários de `ROTAS_IMPORTACAO` (T019) — `PERM-SCPI-IMPORT-HISTORY-VIEW` é
# uma capability distinta de `PERM-SCPI-IMPORT-EXECUTE`, mesmo compartilhando o
# papel exigido na matriz atual; por isso ganha tabela própria em vez de
# reaproveitar `ROTAS_IMPORTACAO`, seguindo a convenção do módulo.
#
# TDD: escrito antes de `catalogo:historico`/`HistoricoImportacoesView`
# existirem (T038) — `reverse()` fica dentro do corpo de cada teste.
# ---------------------------------------------------------------------------

ROTAS_HISTORICO = [
    pytest.param("catalogo:historico", "get", {}, id="historico-get"),
]


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_HISTORICO)
def test_historico_anonimo_e_redirecionado_ao_login(client, nome_rota, metodo, kwargs):
    url = reverse(nome_rota, **kwargs)

    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 302
    assert resposta.content == b""
    assert urlsplit(resposta.url).path == _login_url_esperada()


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_HISTORICO)
def test_chefe_do_almoxarifado_desativado_apos_login_e_tratado_como_anonimo_no_historico(
    client, chefe_almoxarifado, nome_rota, metodo, kwargs
):
    """`INV-AUTH-001`, mesmo cenário de
    `test_chefe_do_almoxarifado_desativado_apos_login_e_tratado_como_anonimo`
    (`ROTAS_IMPORTACAO`), aqui para o histórico."""
    client.force_login(chefe_almoxarifado)
    chefe_almoxarifado.is_active = False
    chefe_almoxarifado.save(update_fields=["is_active"])

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 302
    assert urlsplit(resposta.url).path == _login_url_esperada()


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_HISTORICO)
@pytest.mark.parametrize("nome_fixture_usuario", USUARIOS_SEM_PAPEL_DE_IMPORTACAO)
def test_usuario_sem_role_warehouse_head_recebe_403_no_historico(
    client, request, nome_fixture_usuario, nome_rota, metodo, kwargs
):
    usuario = request.getfixturevalue(nome_fixture_usuario)
    client.force_login(usuario)

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 403, (
        f"{nome_fixture_usuario!r} não tem ROLE-WAREHOUSE-HEAD e deveria receber 403 em {nome_rota}"
    )


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_HISTORICO)
def test_chefe_do_almoxarifado_tem_acesso_ao_historico(
    client, chefe_almoxarifado, nome_rota, metodo, kwargs
):
    client.force_login(chefe_almoxarifado)

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 200, (
        "diferente de `importacao_previa`, o histórico não depende de estado de sessão "
        "pendente: chefe do almoxarifado deve sempre receber 200"
    )
