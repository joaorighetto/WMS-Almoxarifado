"""Testes de autorização das rotas de fornecedores (T012 — importação;
T021 — consulta; T025 — histórico e detalhe, cada um ACRESCENTANDO uma
seção própria a este arquivo, no mesmo padrão).

Cobre `PERM-SUPPLIER-IMPORT-EXECUTE`, `PERM-SUPPLIER-VIEW` e
`PERM-SUPPLIER-IMPORT-HISTORY-VIEW` (`docs/domain/permissions-matrix.md`) e
`INV-AUTH-001` (`docs/domain/invariants-matrix.md`), conforme
`contracts/rotas-e-autorizacao.md` e `research.md` R1 (`ExigePapelMixin`
reusado do catálogo).

Mesmo padrão de `tests/test_catalogo_permissoes.py` (T019/T031/T037): uma
tabela `ROTAS_<CONTEXTO>` de (nome da rota, método HTTP, kwargs de
`reverse`) e os quatro testes genéricos parametrizados sobre ela (anônimo,
desativado após login, sem o papel exigido, com o papel exigido). Todas as
chamadas de `reverse()` ficam dentro do corpo dos testes (nunca em
`pytest.param`/decorador), para que a ausência da rota derrube só o teste
que a usa, não a coleta do arquivo inteiro.

`chefe_almoxarifado` (`tests/conftest.py`) tem `Papel.FUNCIONARIO_
ALMOXARIFADO` além de `CHEFE_SETOR`/`CHEFE_ALMOXARIFADO` — por isso ele
também satisfaz `PERM-SUPPLIER-VIEW` (`ROLE-WAREHOUSE-STAFF`), igual ao
catálogo resolve o caso equivalente para `ROLE-REQUESTER`
(`tests/test_catalogo_permissoes.py`, `USUARIOS_COM_ROLE_REQUESTER`
incluindo `chefe_almoxarifado`).
"""

from urllib.parse import urlsplit

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db

# Chave de sessão do pedido de prévia — valor fixado literalmente em
# `contracts/interface-importacao.md` (`CHAVE_SESSAO_PREVIA`), usada como
# string para não acoplar este teste de AUTORIZAÇÃO à existência do módulo
# de domínio (mesmo padrão de `tests/test_catalogo_permissoes.py`).
_CHAVE_SESSAO_PREVIA = "fornecedores_importacao_previa"

# ---------------------------------------------------------------------------
# Rotas de importação (T012) — PERM-SUPPLIER-IMPORT-EXECUTE, papel
# ROLE-WAREHOUSE-HEAD.
# ---------------------------------------------------------------------------

ROTAS_IMPORTACAO = [
    pytest.param("fornecedores:importacao_envio", "get", {}, id="importacao_envio-get"),
    pytest.param("fornecedores:importacao_envio", "post", {}, id="importacao_envio-post"),
    pytest.param("fornecedores:importacao_previa", "get", {}, id="importacao_previa-get"),
    pytest.param(
        "fornecedores:importacao_confirmar", "post", {}, id="importacao_confirmar-post"
    ),
    pytest.param("fornecedores:importacao_cancelar", "post", {}, id="importacao_cancelar-post"),
]

# Identidades de negócio que NÃO têm `ROLE-WAREHOUSE-HEAD` e por isso devem
# receber 403 nas rotas de importação — nomes de fixtures de
# `tests/conftest.py`, resolvidos via `request.getfixturevalue`.
#
# `funcionario_almoxarifado` está aqui deliberadamente (acréscimo do
# test-engineer, T004): `PERM-SUPPLIER-VIEW` (consulta) e
# `PERM-SUPPLIER-IMPORT-EXECUTE` (importação) exigem papéis DIFERENTES
# (`ROLE-WAREHOUSE-STAFF` vs. `ROLE-WAREHOUSE-HEAD`) — um funcionário comum
# do almoxarifado tem a primeira capability mas não a segunda, e é fácil um
# mixin mal configurado liberar a importação para qualquer
# `ROLE-WAREHOUSE-STAFF` por reaproveitar a checagem da consulta.
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
    já coberto nativamente pela 002 (`ModelBackend.get_user()`), protegido
    aqui contra qualquer view de `fornecedores` que porventura passe a
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
        f"{nome_fixture_usuario} não deveria ter PERM-SUPPLIER-IMPORT-EXECUTE em {nome_rota}"
    )


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_IMPORTACAO)
def test_chefe_do_almoxarifado_acessa_as_rotas_de_importacao(
    client, chefe_almoxarifado, nome_rota, metodo, kwargs
):
    """`ROLE-WAREHOUSE-HEAD` (`chefe_almoxarifado`) é autorizado em toda
    rota de importação — 200 (GET sem estado prévio) ou 302 (POST/GET que
    redireciona por fluxo, ex.: prévia sem pedido pendente, confirmar sem
    prévia válida), nunca 403/redirect para login."""
    client.force_login(chefe_almoxarifado)

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code in (200, 302), (
        f"{nome_rota} deveria ser acessível ao chefe do almoxarifado, recebeu "
        f"{resposta.status_code}"
    )
    if resposta.status_code == 302:
        assert urlsplit(resposta.url).path != _login_url_esperada()


# ---------------------------------------------------------------------------
# POST de envio sem papel não grava sessão (defesa em profundidade: a
# autorização por si só já barra a requisição, mas isso confirma que a
# recusa acontece ANTES de qualquer leitura/gravação de sessão).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nome_fixture_usuario", USUARIOS_SEM_PAPEL_DE_IMPORTACAO)
def test_post_de_envio_sem_papel_nao_grava_sessao(client, request, nome_fixture_usuario):
    usuario = request.getfixturevalue(nome_fixture_usuario)
    client.force_login(usuario)
    conteudo = (
        "﻿"
        "CODIF;NOME;NOM_FANT;INSMF;CODTIP;BLOQ_OPCAO;MSG_BLOQ;TIPO_BLOQ;\r\n"
        "1;FORNECEDOR;;;;S;;;\r\n"
    ).encode()
    arquivo = SimpleUploadedFile("arquivo.csv", conteudo, content_type="text/csv")

    resposta = client.post(reverse("fornecedores:importacao_envio"), {"arquivo": arquivo})

    assert resposta.status_code == 403
    assert _CHAVE_SESSAO_PREVIA not in client.session


def test_post_de_envio_anonimo_nao_grava_sessao():
    client = Client()
    conteudo = (
        "﻿"
        "CODIF;NOME;NOM_FANT;INSMF;CODTIP;BLOQ_OPCAO;MSG_BLOQ;TIPO_BLOQ;\r\n"
        "1;FORNECEDOR;;;;S;;;\r\n"
    ).encode()
    arquivo = SimpleUploadedFile("arquivo.csv", conteudo, content_type="text/csv")

    resposta = client.post(reverse("fornecedores:importacao_envio"), {"arquivo": arquivo})

    assert resposta.status_code == 302
    assert urlsplit(resposta.url).path == _login_url_esperada()
    assert _CHAVE_SESSAO_PREVIA not in client.session


# ---------------------------------------------------------------------------
# Rota de consulta (T021) — PERM-SUPPLIER-VIEW, papel ROLE-WAREHOUSE-STAFF.
#
# Diferente de `ROTAS_IMPORTACAO` (`ROLE-WAREHOUSE-HEAD` só) e diferente da
# consulta do catálogo (`PERM-MATERIAL-VIEW`, aberta a `ROLE-REQUESTER`, ou
# seja, qualquer identidade de negócio): `PERM-SUPPLIER-VIEW` exige
# especificamente `ROLE-WAREHOUSE-STAFF`. Só `funcionario_almoxarifado` e
# `chefe_almoxarifado` têm esse papel entre as fixtures de
# `tests/conftest.py`.
# ---------------------------------------------------------------------------

ROTAS_CONSULTA = [
    pytest.param("fornecedores:consulta", "get", {}, id="consulta-get"),
]

USUARIOS_SEM_PAPEL_DE_CONSULTA = [
    "superusuario_tecnico",
    "requisitante",
    "chefe_setor",
    "auditor",
    "admin_sistema",
]

USUARIOS_COM_PAPEL_DE_CONSULTA = [
    "funcionario_almoxarifado",
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
def test_funcionario_desativado_apos_login_na_consulta_e_tratado_como_anonimo(
    client, funcionario_almoxarifado, nome_rota, metodo, kwargs
):
    client.force_login(funcionario_almoxarifado)
    funcionario_almoxarifado.is_active = False
    funcionario_almoxarifado.save(update_fields=["is_active"])

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 302
    assert urlsplit(resposta.url).path == _login_url_esperada()


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_CONSULTA)
@pytest.mark.parametrize("nome_fixture_usuario", USUARIOS_SEM_PAPEL_DE_CONSULTA)
def test_usuario_sem_role_warehouse_staff_recebe_403_na_consulta(
    client, request, nome_fixture_usuario, nome_rota, metodo, kwargs
):
    usuario = request.getfixturevalue(nome_fixture_usuario)
    client.force_login(usuario)

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 403, (
        f"{nome_fixture_usuario} não tem PERM-SUPPLIER-VIEW e deveria receber 403 em {nome_rota}"
    )


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_CONSULTA)
@pytest.mark.parametrize("nome_fixture_usuario", USUARIOS_COM_PAPEL_DE_CONSULTA)
def test_usuario_com_role_warehouse_staff_acessa_a_consulta(
    client, request, nome_fixture_usuario, nome_rota, metodo, kwargs
):
    """`funcionario_almoxarifado` e `chefe_almoxarifado` (que também tem o
    papel mínimo) recebem 200 — a consulta sempre responde 200 sem depender
    de estado de sessão, então a asserção aqui é estrita, não apenas
    "não é 403"."""
    usuario = request.getfixturevalue(nome_fixture_usuario)
    client.force_login(usuario)

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 200, (
        f"{nome_fixture_usuario} tem PERM-SUPPLIER-VIEW e deveria acessar {nome_rota}"
    )


def test_post_na_consulta_e_405(client, funcionario_almoxarifado):
    client.force_login(funcionario_almoxarifado)

    resposta = client.post(reverse("fornecedores:consulta"))

    assert resposta.status_code == 405


# ---------------------------------------------------------------------------
# Rotas de histórico e detalhe (T025) — PERM-SUPPLIER-IMPORT-HISTORY-VIEW,
# papel ROLE-WAREHOUSE-HEAD. Mesma matriz de usuários de `ROTAS_IMPORTACAO`
# (`PERM-SUPPLIER-IMPORT-HISTORY-VIEW` é uma capability distinta de
# `PERM-SUPPLIER-IMPORT-EXECUTE`, mesmo papel na matriz atual — ganha tabela
# própria, seguindo a convenção do módulo e de `tests/test_catalogo_
# permissoes.py`).
#
# `execucao_detalhe` usa um pk arbitrário (999999, quase certamente
# inexistente): a autorização é decidida pelo mixin antes de qualquer
# `get_object()`, então mesmo um pk inexistente já prova 403/redirect para
# quem não tem o papel. Para quem tem, a asserção aceita 200 OU 404 (pk
# realmente inexistente) — nunca 403 nem redirect para login.
# ---------------------------------------------------------------------------

ROTAS_HISTORICO = [
    pytest.param("fornecedores:historico", "get", {}, id="historico-get"),
    pytest.param(
        "fornecedores:execucao_detalhe", "get", {"args": [999999]}, id="execucao_detalhe-get"
    ),
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
        f"{nome_fixture_usuario} não deveria ter PERM-SUPPLIER-IMPORT-HISTORY-VIEW em {nome_rota}"
    )


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_HISTORICO)
def test_chefe_do_almoxarifado_tem_acesso_ao_historico(
    client, chefe_almoxarifado, nome_rota, metodo, kwargs
):
    client.force_login(chefe_almoxarifado)

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code in (200, 404), (
        f"{nome_rota} deveria ser acessível ao chefe do almoxarifado (200 ou 404 para pk "
        f"inexistente), recebeu {resposta.status_code}"
    )
