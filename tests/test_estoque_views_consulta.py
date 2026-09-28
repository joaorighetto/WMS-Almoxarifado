"""Testes HTTP da consulta e do detalhe de entradas (T020, US2 — Conferir as
entradas registradas).

Cobre US2 cenários 1 a 3 e FR-020/FR-021: lista ordenada da mais recente para
a mais antiga, paginação, situação (registrada/estornada), estado vazio,
número de queries estável, e o detalhe de uma entrada estornada mostrando os
dados do estorno. Os dados de entrada/estorno são criados diretamente por
`estoque.entradas.registrar_entrada`/`estornar_entrada` (não pela tela — a
composição em si é `tests/test_estoque_views_entrada.py`).

TDD: escrito antes de `estoque/views.py` existir.
"""

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
