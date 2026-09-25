"""Testes da barra de trabalho (app bar) fora da Home.

TDD para a propagação de `contas/templates/contas/_barra_trabalho.html` a
`contas/templates/contas/base.html` (bloco `appbar`, renderizado só para
usuário autenticado) e para a remoção dos links "← Início" das telas do
catálogo — a marca da barra passa a ser o único caminho de volta à Home
fora dela. Nenhuma rota, view ou regra de autorização muda; a barra em si
(`_barra_trabalho.html`) já garante logout como POST + CSRF (Constitution
IX) e nunca um link — isso não é reverificado aqui.

Escrito antes da mudança de template (frontend-implementer): os cenários
que exercitam telas do catálogo (consulta, envio, prévia, histórico,
detalhe de execução) e o fragmento HTMX da consulta devem falhar agora —
hoje só `contas/home.html` inclui o parcial. O cenário da página de login
(anônima) e o da Home (marca não é link nela, form de logout único) já
valem hoje e não devem quebrar.

`tests/test_contas_home_papeis.py` já trava os hrefs de negócio da Home
(a marca não vira link lá) — não duplicado aqui.
"""

import re
import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from catalogo.models import ExecucaoImportacao

pytestmark = pytest.mark.django_db

SHA256_FAKE = "0" * 64


def _login(client, usuario, senha_valida):
    logou = client.login(username=usuario.matricula, password=senha_valida)
    assert logou, "pré-condição do teste: login direto via client deveria funcionar"


def _enviar(client, conteudo, nome="arquivo.csv"):
    arquivo = SimpleUploadedFile(nome, conteudo, content_type="text/csv")
    return client.post(reverse("catalogo:importacao_envio"), {"arquivo": arquivo})


def _criar_execucao(*, executada_por, nome_arquivo="carga.csv"):
    """Execução mínima e válida (mesmos totais de
    `tests/test_catalogo_historico.py::_criar_execucao`), só para ter uma
    `pk` existente a visitar em `catalogo:execucao_detalhe`."""
    return ExecucaoImportacao.objects.create(
        token_previa=uuid.uuid4(),
        executada_por=executada_por,
        concluida_em=timezone.now(),
        nome_arquivo=nome_arquivo,
        tamanho_arquivo=10,
        sha256_arquivo=SHA256_FAKE,
        total_recebidos=1,
        total_inseridos=1,
        total_atualizados=0,
        total_atualizados_com_alteracao=0,
        total_rejeitados=0,
        total_divergencias=0,
        total_ausentes_no_arquivo=0,
    )


def _assert_barra_de_trabalho_presente(conteudo, usuario):
    """Barra completa fora da Home: exatamente um form de logout POST com
    CSRF, a marca como link para a Home, e a matrícula do usuário."""
    url_logout = reverse("logout")
    url_home = reverse("home")

    ocorrencias_logout = conteudo.count(f'action="{url_logout}"')
    assert ocorrencias_logout == 1, (
        f"esperava exatamente um form de logout, achou {ocorrencias_logout}"
    )
    assert re.search(
        rf'<form[^>]*method="post"[^>]*action="{re.escape(url_logout)}"', conteudo
    ) or re.search(
        rf'<form[^>]*action="{re.escape(url_logout)}"[^>]*method="post"', conteudo
    ), "o form de logout deveria ser POST"
    assert "csrfmiddlewaretoken" in conteudo

    assert re.search(rf'<a\s+href="{re.escape(url_home)}"', conteudo), (
        "esperava a marca da barra como link para a Home (fora da Home)"
    )

    assert usuario.matricula in conteudo


# ---------------------------------------------------------------------------
# 1. A barra aparece em toda tela autenticada do catálogo (chefe do
#    almoxarifado, que alcança todas as rotas).
# ---------------------------------------------------------------------------

ROTAS_CATALOGO_SEM_ESTADO = ["catalogo:consulta", "catalogo:importacao_envio", "catalogo:historico"]


@pytest.mark.parametrize("nome_rota", ROTAS_CATALOGO_SEM_ESTADO)
def test_barra_de_trabalho_aparece_em_tela_do_catalogo(
    client, chefe_almoxarifado, senha_valida, nome_rota
):
    _login(client, chefe_almoxarifado, senha_valida)

    resposta = client.get(reverse(nome_rota))

    assert resposta.status_code == 200
    _assert_barra_de_trabalho_presente(resposta.content.decode(), chefe_almoxarifado)


def test_barra_de_trabalho_aparece_no_detalhe_de_uma_execucao(
    client, chefe_almoxarifado, senha_valida
):
    _login(client, chefe_almoxarifado, senha_valida)
    execucao = _criar_execucao(executada_por=chefe_almoxarifado)

    resposta = client.get(reverse("catalogo:execucao_detalhe", args=[execucao.pk]))

    assert resposta.status_code == 200
    _assert_barra_de_trabalho_presente(resposta.content.decode(), chefe_almoxarifado)


def test_barra_de_trabalho_aparece_na_previa_de_importacao(
    client, chefe_almoxarifado, senha_valida, csv_fixture
):
    _login(client, chefe_almoxarifado, senha_valida)
    resposta_envio = _enviar(client, csv_fixture("carga_inicial_valida.csv"))
    assert resposta_envio.status_code == 302, "pré-condição: envio válido deveria redirecionar"

    resposta_previa = client.get(reverse("catalogo:importacao_previa"))

    assert resposta_previa.status_code == 200
    _assert_barra_de_trabalho_presente(resposta_previa.content.decode(), chefe_almoxarifado)


# ---------------------------------------------------------------------------
# 2. A barra também aparece para um papel sem privilégio de importação
#    (requisitante, na consulta).
# ---------------------------------------------------------------------------


def test_barra_de_trabalho_aparece_na_consulta_para_requisitante(
    client, requisitante, senha_valida
):
    _login(client, requisitante, senha_valida)

    resposta = client.get(reverse("catalogo:consulta"))

    assert resposta.status_code == 200
    _assert_barra_de_trabalho_presente(resposta.content.decode(), requisitante)


# ---------------------------------------------------------------------------
# 3. O fragmento HTMX da consulta não duplica a barra numa troca parcial.
# ---------------------------------------------------------------------------


def test_fragmento_htmx_da_consulta_nao_contem_a_barra_de_trabalho(
    client, requisitante, senha_valida
):
    _login(client, requisitante, senha_valida)

    resposta = client.get(reverse("catalogo:consulta"), HTTP_HX_REQUEST="true")

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()

    assert f'action="{reverse("logout")}"' not in conteudo
    assert "Almoxarifado SAEP" not in conteudo


# ---------------------------------------------------------------------------
# 4. A página de login (anônima) não contém a barra.
# ---------------------------------------------------------------------------


def test_pagina_de_login_anonima_nao_contem_a_barra_de_trabalho(client):
    resposta = client.get(reverse("login"))

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()

    url_logout = reverse("logout")
    url_home = reverse("home")

    assert f'action="{url_logout}"' not in conteudo
    assert not re.search(rf'<a\s+href="{re.escape(url_home)}"', conteudo), (
        "página anônima não deveria ter a marca como link para a Home"
    )


# ---------------------------------------------------------------------------
# 6. A Home mantém exatamente um form de logout (a marca não ser link lá
#    já é travado por tests/test_contas_home_papeis.py).
# ---------------------------------------------------------------------------


def test_home_tem_exatamente_um_formulario_de_logout(client, usuario_ativo, senha_valida):
    _login(client, usuario_ativo, senha_valida)

    resposta = client.get(reverse("home"))

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    ocorrencias = conteudo.count(f'action="{reverse("logout")}"')
    assert ocorrencias == 1, f"esperava exatamente um form de logout, achou {ocorrencias}"
