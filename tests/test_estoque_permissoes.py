"""Testes de autorização das rotas de `estoque` (T013 — registro/detalhe;
T021 — consulta/lista; T027 — estorno), cada task ACRESCENTANDO uma seção
própria a este arquivo.

Cobre `PERM-STOCK-ENTRY-CREATE`, `PERM-STOCK-ENTRY-REVERSE` e o recorte de
`PERM-STOCK-HISTORY-VIEW` fixado por FR-021 para a entrada (só
`ROLE-WAREHOUSE-STAFF` e `ROLE-AUDITOR` veem; os demais, nada — não o recorte
geral da matriz, que também inclui auxiliar/chefe de setor por objeto
próprio/setor, inaplicável aqui). `INV-AUTH-001`. Conforme
`contracts/rotas-e-autorizacao.md`, "Matriz de teste de permissão".

Mesmo padrão de `tests/test_fornecedores_permissoes.py`/`tests/
test_catalogo_permissoes.py`: tabelas `ROTAS_<CONTEXTO>` de (nome da rota,
método, kwargs de `reverse`) e testes genéricos parametrizados (anônimo,
desativado após login, sem o papel exigido, com o papel exigido). Todas as
chamadas de `reverse()` ficam dentro do corpo dos testes, para que a ausência
da rota derrube só o teste que a usa, não a coleta do arquivo inteiro.

`chefe_almoxarifado` (`tests/conftest.py`) tem `ROLE-WAREHOUSE-STAFF` além de
`ROLE-WAREHOUSE-HEAD`/`ROLE-SECTOR-HEAD` — por isso ele também satisfaz
`PERM-STOCK-ENTRY-CREATE` e o recorte de `PERM-STOCK-HISTORY-VIEW`, ao lado de
`PERM-STOCK-ENTRY-REVERSE`.
"""

from urllib.parse import urlsplit

import pytest
from django.urls import reverse

from estoque.models import Entrada
from tests.contas_helpers import operacao

pytestmark = pytest.mark.django_db


def _login_url_esperada():
    return reverse("login")


def _total_entradas():
    return Entrada.objects.count()


# ---------------------------------------------------------------------------
# T013 — Registro (composição, confirmação) e detalhe.
# `PERM-STOCK-ENTRY-CREATE`: só ROLE-WAREHOUSE-STAFF.
# ---------------------------------------------------------------------------

ROTAS_REGISTRO = [
    pytest.param("estoque:entrada_nova", "get", {}, id="entrada_nova-get"),
    pytest.param("estoque:entrada_nova", "post", {}, id="entrada_nova-post"),
    pytest.param("estoque:entrada_confirmar", "post", {}, id="entrada_confirmar-post"),
]

USUARIOS_SEM_PAPEL_DE_REGISTRO = [
    "superusuario_tecnico",
    "requisitante",
    "chefe_setor",
    "auditor",
    "admin_sistema",
]

USUARIOS_COM_PAPEL_DE_REGISTRO = [
    "funcionario_almoxarifado",
    "chefe_almoxarifado",
]


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_REGISTRO)
def test_registro_anonimo_e_redirecionado_ao_login(client, nome_rota, metodo, kwargs):
    url = reverse(nome_rota, **kwargs)

    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 302
    assert resposta.content == b""
    assert urlsplit(resposta.url).path == _login_url_esperada()


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_REGISTRO)
def test_funcionario_desativado_apos_login_no_registro_e_tratado_como_anonimo(
    client, funcionario_almoxarifado, nome_rota, metodo, kwargs
):
    client.force_login(funcionario_almoxarifado)
    with operacao():
        funcionario_almoxarifado.is_active = False
        funcionario_almoxarifado.save(update_fields=["is_active"])

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 302
    assert urlsplit(resposta.url).path == _login_url_esperada()


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_REGISTRO)
@pytest.mark.parametrize("nome_fixture_usuario", USUARIOS_SEM_PAPEL_DE_REGISTRO)
def test_usuario_sem_role_warehouse_staff_recebe_403_no_registro(
    client, request, nome_fixture_usuario, nome_rota, metodo, kwargs
):
    usuario = request.getfixturevalue(nome_fixture_usuario)
    client.force_login(usuario)

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 403, (
        f"{nome_fixture_usuario} não tem PERM-STOCK-ENTRY-CREATE e deveria receber 403 em "
        f"{nome_rota}"
    )


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_REGISTRO)
@pytest.mark.parametrize("nome_fixture_usuario", USUARIOS_SEM_PAPEL_DE_REGISTRO)
def test_negado_no_registro_nao_grava_nenhuma_entrada(
    client, request, nome_fixture_usuario, nome_rota, metodo, kwargs
):
    usuario = request.getfixturevalue(nome_fixture_usuario)
    client.force_login(usuario)
    total_antes = _total_entradas()

    url = reverse(nome_rota, **kwargs)
    getattr(client, metodo)(url)

    assert _total_entradas() == total_antes


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_REGISTRO)
@pytest.mark.parametrize("nome_fixture_usuario", USUARIOS_COM_PAPEL_DE_REGISTRO)
def test_usuario_com_role_warehouse_staff_acessa_as_rotas_de_registro(
    client, request, nome_fixture_usuario, nome_rota, metodo, kwargs
):
    """GET de `entrada_nova` sempre 200; POSTs sem dados válidos podem
    re-renderizar (200) ou recusar com 400 (chave malformada) — nunca 403 nem
    redirect para login, que é o que este teste de AUTORIZAÇÃO prova."""
    usuario = request.getfixturevalue(nome_fixture_usuario)
    client.force_login(usuario)

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code not in (302, 403), (
        f"{nome_fixture_usuario} tem PERM-STOCK-ENTRY-CREATE e não deveria ser barrado em "
        f"{nome_rota} (recebeu {resposta.status_code})"
    )
    if resposta.status_code in (301, 302):  # pragma: no cover - defensivo
        assert urlsplit(resposta.url).path != _login_url_esperada()


# ---------------------------------------------------------------------------
# T021 — Consulta (lista, detalhe). Recorte de PERM-STOCK-HISTORY-VIEW
# fixado por FR-021: ROLE-WAREHOUSE-STAFF e ROLE-AUDITOR veem tudo; os
# demais, nada.
# ---------------------------------------------------------------------------

ROTAS_CONSULTA = [
    pytest.param("estoque:entradas", "get", {}, id="entradas-get"),
    pytest.param(
        "estoque:entrada_detalhe", "get", {"args": [999999]}, id="entrada_detalhe-get"
    ),
]

USUARIOS_SEM_PAPEL_DE_CONSULTA = [
    "superusuario_tecnico",
    "requisitante",
    "chefe_setor",
    "admin_sistema",
]

USUARIOS_COM_PAPEL_DE_CONSULTA = [
    "funcionario_almoxarifado",
    "chefe_almoxarifado",
    "auditor",
]


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_CONSULTA)
def test_consulta_anonimo_e_redirecionado_ao_login(client, nome_rota, metodo, kwargs):
    url = reverse(nome_rota, **kwargs)

    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 302
    assert resposta.content == b""
    assert urlsplit(resposta.url).path == _login_url_esperada()


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_CONSULTA)
def test_auditor_desativado_apos_login_na_consulta_e_tratado_como_anonimo(
    client, auditor, nome_rota, metodo, kwargs
):
    client.force_login(auditor)
    with operacao():
        auditor.is_active = False
        auditor.save(update_fields=["is_active"])

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 302
    assert urlsplit(resposta.url).path == _login_url_esperada()


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_CONSULTA)
@pytest.mark.parametrize("nome_fixture_usuario", USUARIOS_SEM_PAPEL_DE_CONSULTA)
def test_usuario_fora_do_recorte_recebe_403_na_consulta(
    client, request, nome_fixture_usuario, nome_rota, metodo, kwargs
):
    usuario = request.getfixturevalue(nome_fixture_usuario)
    client.force_login(usuario)

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 403, (
        f"{nome_fixture_usuario} está fora do recorte de PERM-STOCK-HISTORY-VIEW para "
        f"entradas (FR-021) e deveria receber 403 em {nome_rota}"
    )


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_CONSULTA)
@pytest.mark.parametrize("nome_fixture_usuario", USUARIOS_COM_PAPEL_DE_CONSULTA)
def test_usuario_do_recorte_acessa_a_consulta(
    client, request, nome_fixture_usuario, nome_rota, metodo, kwargs
):
    usuario = request.getfixturevalue(nome_fixture_usuario)
    client.force_login(usuario)

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code in (200, 404), (
        f"{nome_fixture_usuario} está no recorte de PERM-STOCK-HISTORY-VIEW e deveria "
        f"acessar {nome_rota} (200, ou 404 só para pk inexistente), recebeu "
        f"{resposta.status_code}"
    )


def test_post_na_lista_de_entradas_e_405(client, funcionario_almoxarifado):
    client.force_login(funcionario_almoxarifado)

    resposta = client.post(reverse("estoque:entradas"))

    assert resposta.status_code == 405


# ---------------------------------------------------------------------------
# T027 — Estorno. `PERM-STOCK-ENTRY-REVERSE`: só ROLE-WAREHOUSE-HEAD — nem
# mesmo o funcionário do almoxarifado comum (sem chefia) pode.
# ---------------------------------------------------------------------------

ROTAS_ESTORNO = [
    pytest.param("estoque:entrada_estorno", "get", {"args": [999999]}, id="entrada_estorno-get"),
    pytest.param("estoque:entrada_estorno", "post", {"args": [999999]}, id="entrada_estorno-post"),
]

USUARIOS_SEM_PAPEL_DE_ESTORNO = [
    "superusuario_tecnico",
    "requisitante",
    "chefe_setor",
    "auditor",
    "admin_sistema",
    "funcionario_almoxarifado",
]


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_ESTORNO)
def test_estorno_anonimo_e_redirecionado_ao_login(client, nome_rota, metodo, kwargs):
    url = reverse(nome_rota, **kwargs)

    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 302
    assert resposta.content == b""
    assert urlsplit(resposta.url).path == _login_url_esperada()


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_ESTORNO)
def test_chefe_almoxarifado_desativado_apos_login_no_estorno_e_tratado_como_anonimo(
    client, chefe_almoxarifado, nome_rota, metodo, kwargs
):
    client.force_login(chefe_almoxarifado)
    with operacao():
        chefe_almoxarifado.is_active = False
        chefe_almoxarifado.save(update_fields=["is_active"])

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 302
    assert urlsplit(resposta.url).path == _login_url_esperada()


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_ESTORNO)
@pytest.mark.parametrize("nome_fixture_usuario", USUARIOS_SEM_PAPEL_DE_ESTORNO)
def test_usuario_sem_role_warehouse_head_recebe_403_no_estorno(
    client, request, nome_fixture_usuario, nome_rota, metodo, kwargs
):
    """`funcionario_almoxarifado` é o caso deliberadamente incluído aqui
    (revisão do test-engineer, US3 cenário 5): tem `PERM-STOCK-ENTRY-CREATE`
    mas NÃO `PERM-STOCK-ENTRY-REVERSE` — papéis diferentes, fácil de um
    mixin mal configurado liberar o estorno para qualquer
    ROLE-WAREHOUSE-STAFF por reaproveitar a checagem do registro."""
    usuario = request.getfixturevalue(nome_fixture_usuario)
    client.force_login(usuario)

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 403, (
        f"{nome_fixture_usuario} não tem PERM-STOCK-ENTRY-REVERSE e deveria receber 403 em "
        f"{nome_rota}"
    )


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_ESTORNO)
@pytest.mark.parametrize("nome_fixture_usuario", USUARIOS_SEM_PAPEL_DE_ESTORNO)
def test_negado_no_estorno_nao_altera_nenhuma_entrada(
    client,
    request,
    nome_fixture_usuario,
    nome_rota,
    metodo,
    kwargs,
    funcionario_almoxarifado,
    criar_material,
):
    import uuid as uuid_module
    from decimal import Decimal

    from estoque.entradas import EntradaInformada, ItemInformado, registrar_entrada
    from estoque.models import MotivoEntrada, TipoDocumentoEntrada

    material = criar_material("600.000.001", Decimal("0.000"))
    entrada = registrar_entrada(
        EntradaInformada(
            chave_confirmacao=uuid_module.uuid4(),
            motivo=MotivoEntrada.DOACAO_RECEBIDA,
            tipo_documento=TipoDocumentoEntrada.NOTA_FISCAL,
            numero_documento=str(uuid_module.uuid4()),
            emitente_id=None,
            itens=(ItemInformado(material_id=material.pk, quantidade=Decimal("5.000")),),
        ),
        funcionario_almoxarifado,
    )
    usuario = request.getfixturevalue(nome_fixture_usuario)
    client.force_login(usuario)

    url = reverse("estoque:entrada_estorno", args=[entrada.pk])
    getattr(client, metodo)(url, {"justificativa": "Tentativa negada."})

    entrada.refresh_from_db()
    assert entrada.estornada is False
    material.refresh_from_db()
    assert material.saldo == Decimal("5.000")


@pytest.mark.parametrize("nome_rota, metodo, kwargs", ROTAS_ESTORNO)
def test_chefe_almoxarifado_acessa_as_rotas_de_estorno(
    client, chefe_almoxarifado, nome_rota, metodo, kwargs
):
    client.force_login(chefe_almoxarifado)

    url = reverse(nome_rota, **kwargs)
    resposta = getattr(client, metodo)(url)

    assert resposta.status_code in (200, 302, 404), (
        f"{nome_rota} deveria ser acessível ao chefe do almoxarifado (200, 302 por fluxo, ou "
        f"404 para pk inexistente), recebeu {resposta.status_code}"
    )
    if resposta.status_code == 302:
        assert urlsplit(resposta.url).path != _login_url_esperada()
