"""Testes HTTP da consulta e do detalhe de entradas (T020, US2 — Conferir as
entradas registradas).

Cobre US2 cenários 1 a 3 e FR-020/FR-021: lista ordenada da mais recente para
a mais antiga, paginação, situação (registrada/estornada), estado vazio,
número de queries estável, e o detalhe de uma entrada estornada mostrando os
dados do estorno. Os dados de entrada/estorno são criados diretamente por
`estoque.entradas.registrar_entrada`/`estornar_entrada` (não pela tela — a
composição em si é `tests/test_estoque_views_entrada.py`).

TDD: escrito antes de `estoque/views.py` existir.

Seção acrescentada pelo `test-engineer` (alinhamento de UX, Fase B):
"Ação 'Registrar entrada' no Page Header" (`PERM-STOCK-ENTRY-CREATE`,
`pode_registrar_entrada`) e "Linha clicável" (`data-linha-clicavel`/
`data-linha-link`, `static/js/linha-clicavel.js`).
"""

import re
import uuid
from decimal import Decimal

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def _registrar(autor, material, quantidade, **overrides):
    from estoque.entradas import EntradaInformada, ItemInformado, registrar_entrada
    from estoque.models import MotivoEntrada, TipoDocumentoEntrada

    dados = EntradaInformada(
        chave_confirmacao=uuid.uuid4(),
        motivo=overrides.pop("motivo", MotivoEntrada.DOACAO_RECEBIDA),
        tipo_documento=overrides.pop("tipo_documento", TipoDocumentoEntrada.NOTA_FISCAL),
        numero_documento=overrides.pop("numero_documento", str(uuid.uuid4())),
        emitente_id=overrides.pop("emitente_id", None),
        itens=(ItemInformado(material_id=material.pk, quantidade=quantidade),),
    )
    return registrar_entrada(dados, autor)


# ---------------------------------------------------------------------------
# US2 — cenário 1: lista da mais recente para a mais antiga, com situação.
# ---------------------------------------------------------------------------


def test_lista_mostra_entradas_da_mais_recente_para_a_mais_antiga(
    client, funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    material = criar_material("800.000.001", Decimal("0.000"))
    # Âncora robusta: o número do documento (único, via uuid) — o `pk`
    # sozinho ("1", "2", ...) é um dígito comum demais no HTML (ex.: a
    # própria tag `<h1>`) para servir de âncora de posição no conteúdo.
    numero_1 = f"NF-{uuid.uuid4()}"
    numero_2 = f"NF-{uuid.uuid4()}"
    _registrar(funcionario_almoxarifado, material, Decimal("1.000"), numero_documento=numero_1)
    _registrar(funcionario_almoxarifado, material, Decimal("2.000"), numero_documento=numero_2)
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("estoque:entradas"))

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    posicao_2 = conteudo.index(numero_2)
    posicao_1 = conteudo.index(numero_1)
    assert posicao_2 < posicao_1, "a entrada mais recente deveria aparecer primeiro"


def test_lista_mostra_a_situacao_registrada_ou_estornada(
    client, funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    from estoque.entradas import estornar_entrada

    material_a = criar_material("800.000.002", Decimal("0.000"))
    material_b = criar_material("800.000.003", Decimal("0.000"))
    registrada = _registrar(funcionario_almoxarifado, material_a, Decimal("1.000"))
    estornada = _registrar(funcionario_almoxarifado, material_b, Decimal("1.000"))
    estornar_entrada(estornada.pk, "Erro de digitação.", chefe_almoxarifado)

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("estoque:entradas"))
    conteudo = resposta.content.decode()

    assert "Registrada" in conteudo
    assert "Estornada" in conteudo
    assert str(registrada.pk) in conteudo
    assert str(estornada.pk) in conteudo


def test_lista_vazia_mostra_estado_vazio(client, funcionario_almoxarifado):
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("estoque:entradas"))

    assert resposta.status_code == 200


def test_auditor_ve_entradas_de_outros_funcionarios(
    client, funcionario_almoxarifado, auditor, criar_material
):
    material = criar_material("800.000.004", Decimal("0.000"))
    entrada = _registrar(funcionario_almoxarifado, material, Decimal("1.000"))

    client.force_login(auditor)
    resposta = client.get(reverse("estoque:entradas"))

    assert resposta.status_code == 200
    assert str(entrada.pk) in resposta.content.decode()


def test_numero_de_queries_da_lista_e_estavel_com_mais_entradas(
    client, funcionario_almoxarifado, criar_material, django_assert_max_num_queries
):
    material = criar_material("800.000.005", Decimal("0.000"))
    for _ in range(3):
        _registrar(funcionario_almoxarifado, material, Decimal("1.000"))
    client.force_login(funcionario_almoxarifado)

    with django_assert_max_num_queries(10):
        client.get(reverse("estoque:entradas"))

    for _ in range(27):
        _registrar(funcionario_almoxarifado, material, Decimal("1.000"))

    with django_assert_max_num_queries(10):
        client.get(reverse("estoque:entradas"))


# ---------------------------------------------------------------------------
# US2 — cenário 2: detalhe com os dados confirmados; entrada estornada
# também mostra autor, momento e justificativa do estorno.
# ---------------------------------------------------------------------------


def test_detalhe_de_entrada_registrada_nao_mostra_dados_de_estorno(
    client, funcionario_almoxarifado, criar_material
):
    material = criar_material("800.000.006", Decimal("0.000"), unidade="UN")
    entrada = _registrar(funcionario_almoxarifado, material, Decimal("4.000"))
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("estoque:entrada_detalhe", args=[entrada.pk]))

    assert resposta.status_code == 200
    assert "Registrada" in resposta.content.decode()


def test_detalhe_de_entrada_estornada_mostra_autor_momento_e_justificativa(
    client, funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    from estoque.entradas import estornar_entrada

    material = criar_material("800.000.007", Decimal("0.000"))
    entrada = _registrar(funcionario_almoxarifado, material, Decimal("4.000"))
    estornar_entrada(entrada.pk, "Motivo incorreto na digitação.", chefe_almoxarifado)

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("estoque:entrada_detalhe", args=[entrada.pk]))

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "Estornada" in conteudo
    assert chefe_almoxarifado.matricula in conteudo
    assert "Motivo incorreto na digitação." in conteudo


def test_detalhe_de_pk_inexistente_e_404_para_autorizado(client, funcionario_almoxarifado):
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("estoque:entrada_detalhe", args=[999999]))

    assert resposta.status_code == 404


# ---------------------------------------------------------------------------
# Ação "Registrar entrada" no Page Header — `PERM-STOCK-ENTRY-CREATE`
# (`EntradasView.pode_registrar_entrada`, `estoque/views.py`). O auditor está
# no recorte de `PERM-STOCK-HISTORY-VIEW` (FR-021, vê a lista) mas não tem
# `PERM-STOCK-ENTRY-CREATE` — a ação não pode aparecer para ele. A
# autorização real da rota `entrada_nova` já é garantida por
# `tests/test_estoque_permissoes.py::
# test_usuario_sem_role_warehouse_staff_recebe_403_no_registro`
# (parametrizado com "auditor" em `USUARIOS_SEM_PAPEL_DE_REGISTRO`) — os
# testes abaixo cobrem só a apresentação, nunca em substituição a esse 403
# (regra 6 da matriz de permissões: ocultar botão não constitui
# autorização).
# ---------------------------------------------------------------------------


def _bloco_page_header(conteudo):
    match = re.search(r'<header class="page-header">.*?</header>', conteudo, re.S)
    assert match is not None, "page header não encontrado"
    return match.group()


def test_funcionario_almoxarifado_ve_acao_registrar_entrada(client, funcionario_almoxarifado):
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("estoque:entradas"))

    bloco = _bloco_page_header(resposta.content.decode())
    assert f'href="{reverse("estoque:entrada_nova")}"' in bloco
    assert "Registrar entrada" in bloco


def test_chefe_almoxarifado_ve_acao_registrar_entrada(client, chefe_almoxarifado):
    """`chefe_almoxarifado` acumula `ROLE-WAREHOUSE-STAFF`
    (`PERM-STOCK-ENTRY-CREATE`) além de `ROLE-WAREHOUSE-HEAD`."""
    client.force_login(chefe_almoxarifado)

    resposta = client.get(reverse("estoque:entradas"))

    bloco = _bloco_page_header(resposta.content.decode())
    assert f'href="{reverse("estoque:entrada_nova")}"' in bloco


def test_auditor_nao_ve_acao_registrar_entrada(client, auditor):
    client.force_login(auditor)

    resposta = client.get(reverse("estoque:entradas"))

    bloco = _bloco_page_header(resposta.content.decode())
    assert reverse("estoque:entrada_nova") not in bloco
    assert "Registrar entrada" not in bloco


def test_acao_escondida_nao_dispensa_o_403_real_da_rota(client, auditor):
    """Par explícito com o teste acima: ausência do botão não é a
    autorização em si. A garantia de fundo já existe em `tests/
    test_estoque_permissoes.py`; este teste só documenta o par no mesmo
    arquivo que prova a ausência do botão para o auditor."""
    client.force_login(auditor)

    resposta = client.get(reverse("estoque:entrada_nova"))

    assert resposta.status_code == 403


def test_estado_vazio_com_permissao_convida_a_registrar(client, funcionario_almoxarifado):
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("estoque:entradas"))

    conteudo = resposta.content.decode()
    assert 'data-estado="vazio"' in conteudo
    assert "Registre a primeira entrada de materiais para vê-la aqui." in conteudo


def test_estado_vazio_sem_permissao_nao_convida_a_registrar(client, auditor):
    client.force_login(auditor)

    resposta = client.get(reverse("estoque:entradas"))

    conteudo = resposta.content.decode()
    assert 'data-estado="vazio"' in conteudo
    assert "Registre" not in conteudo
    assert "As entradas registradas pela equipe do almoxarifado aparecerão aqui." in conteudo


# ---------------------------------------------------------------------------
# Linha clicável — `<a>` real por linha, com nome acessível contextualizado
# (`static/js/linha-clicavel.js`, contrato `data-linha-clicavel`/
# `data-linha-link`). O aprimoramento em si (clique fora do link navegando)
# só é verificável no browser; aqui só o que garante o funcionamento sem JS.
# ---------------------------------------------------------------------------


def test_cada_entrada_tem_link_real_com_nome_acessivel_contextualizado(
    client, funcionario_almoxarifado, criar_material
):
    material = criar_material("800.000.010", Decimal("0.000"))
    entrada = _registrar(funcionario_almoxarifado, material, Decimal("1.000"))
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("estoque:entradas"))

    conteudo = resposta.content.decode()
    href = reverse("estoque:entrada_detalhe", args=[entrada.pk])
    link_esperado = (
        f'<a href="{href}" class="table-row-link" data-linha-link>'
        f'<span class="visually-hidden">Entrada </span>#{entrada.pk}</a>'
    )
    assert link_esperado in conteudo, "link real da linha, com nome acessível contextualizado"
    assert "<tr data-linha-clicavel>" in conteudo


def test_pagina_de_entradas_carrega_o_script_de_linha_clicavel(client, funcionario_almoxarifado):
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("estoque:entradas"))

    assert "js/linha-clicavel.js" in resposta.content.decode()


# ---------------------------------------------------------------------------
# Quantidade no detalhe da entrada (Fase C, filtro `quantidade`): antes o
# detalhe mostrava "6,000" sem filtro algum, ao lado de saldos formatados de
# outro jeito. Só exibição; o algoritmo é `tests/test_catalogo_templatetags.py`.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "quantidade, esperado",
    [
        (Decimal("6.000"), "6"),
        (Decimal("1500.500"), "1.500,5"),
        (Decimal("0.125"), "0,125"),
    ],
)
def test_detalhe_exibe_a_quantidade_em_pt_br_so_com_as_casas_significativas(
    client, funcionario_almoxarifado, criar_material, quantidade, esperado
):
    material = criar_material("800.000.020", Decimal("0.000"))
    entrada = _registrar(funcionario_almoxarifado, material, quantidade)
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("estoque:entrada_detalhe", args=[entrada.pk]))

    conteudo = resposta.content.decode()
    assert re.search(
        rf'<td class="table-cell-numeric">\s*{re.escape(esperado)}\s*</td>', conteudo
    ), f"quantidade {quantidade} deveria aparecer como {esperado!r}"


def test_detalhe_de_item_de_6_unidades_mostra_6_e_nao_6_virgula_000(
    client, funcionario_almoxarifado, criar_material
):
    material = criar_material("800.000.021", Decimal("0.000"))
    entrada = _registrar(funcionario_almoxarifado, material, Decimal("6.000"))
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("estoque:entrada_detalhe", args=[entrada.pk]))

    conteudo = resposta.content.decode()
    assert "6,000" not in conteudo
    assert "6.000" not in conteudo
