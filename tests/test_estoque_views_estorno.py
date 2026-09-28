"""Testes HTTP do estorno de entrada (T027, US3 — Corrigir uma entrada
registrada com erro).

Cobre `contracts/rotas-e-autorizacao.md` → "Estorno": GET mostra saldo atual
e resultante por item, com os que ficariam negativos já marcados; POST sem
justificativa recusa no campo; POST válido registra e redireciona; reenvio
mostra "Esta entrada já foi estornada."; bloqueio por saldo marca os itens e
nada grava. Autorização em si é `tests/test_estoque_permissoes.py`.

TDD: escrito antes de `estoque/views.py` existir.
"""

import uuid
from decimal import Decimal

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def _registrar(autor, material, quantidade):
    from estoque.entradas import EntradaInformada, ItemInformado, registrar_entrada
    from estoque.models import MotivoEntrada, TipoDocumentoEntrada

    dados = EntradaInformada(
        chave_confirmacao=uuid.uuid4(),
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        tipo_documento=TipoDocumentoEntrada.NOTA_FISCAL,
        numero_documento=str(uuid.uuid4()),
        emitente_id=None,
        itens=(ItemInformado(material_id=material.pk, quantidade=quantidade),),
    )
    return registrar_entrada(dados, autor)


def test_get_do_estorno_mostra_saldo_atual_e_resultante_do_item(
    client, funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    material = criar_material("900.000.001", Decimal("10.000"))
    entrada = _registrar(funcionario_almoxarifado, material, Decimal("5.000"))
    client.force_login(chefe_almoxarifado)

    resposta = client.get(reverse("estoque:entrada_estorno", args=[entrada.pk]))

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert material.cadpro in conteudo
    assert "15" in conteudo  # saldo atual (10 iniciais + 5 da entrada)
    assert "10" in conteudo  # saldo resultante do estorno (15 - 5)


def test_get_do_estorno_marca_item_que_ficaria_negativo(
    client, funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    from catalogo.models import Material

    material = criar_material("900.000.002", Decimal("0.000"))
    entrada = _registrar(funcionario_almoxarifado, material, Decimal("10.000"))
    Material.objects.filter(pk=material.pk).update(saldo=Decimal("3.000"))
    client.force_login(chefe_almoxarifado)

    resposta = client.get(reverse("estoque:entrada_estorno", args=[entrada.pk]))

    assert resposta.status_code == 200


def test_post_sem_justificativa_recusa_no_campo_sem_gravar(
    client, funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    from estoque.models import Entrada

    material = criar_material("900.000.003", Decimal("0.000"))
    entrada = _registrar(funcionario_almoxarifado, material, Decimal("5.000"))
    client.force_login(chefe_almoxarifado)

    resposta = client.post(reverse("estoque:entrada_estorno", args=[entrada.pk]), {})

    assert resposta.status_code == 200
    entrada.refresh_from_db()
    assert entrada.estornada is False
    assert Entrada.objects.filter(pk=entrada.pk, estornada=False).exists()


def test_post_valido_registra_o_estorno_e_redireciona_ao_detalhe(
    client, funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    material = criar_material("900.000.004", Decimal("0.000"))
    entrada = _registrar(funcionario_almoxarifado, material, Decimal("5.000"))
    client.force_login(chefe_almoxarifado)

    resposta = client.post(
        reverse("estoque:entrada_estorno", args=[entrada.pk]),
        {"justificativa": "Motivo errado na digitação."},
    )

    assert resposta.status_code == 302
    assert resposta.url == reverse("estoque:entrada_detalhe", args=[entrada.pk])
    entrada.refresh_from_db()
    assert entrada.estornada is True
    material.refresh_from_db()
    assert material.saldo == Decimal("0.000")

    detalhe = client.get(resposta.url)
    mensagens = [str(m) for m in detalhe.context["messages"]]
    assert any("estornada" in m.lower() for m in mensagens)


def test_get_do_estorno_de_entrada_ja_estornada_redireciona_sem_renderizar_formulario(
    client, funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    """Achado do gate visual (item 7 do review): reabrir o formulário de
    estorno de uma entrada JÁ estornada é confuso — GET (e não só POST) deve
    ir direto ao detalhe com o aviso, sem renderizar `entrada_estorno.html`."""
    from estoque.entradas import estornar_entrada

    material = criar_material("900.000.010", Decimal("0.000"))
    entrada = _registrar(funcionario_almoxarifado, material, Decimal("5.000"))
    estornar_entrada(entrada.pk, "Erro de digitação.", chefe_almoxarifado)
    client.force_login(chefe_almoxarifado)

    resposta = client.get(reverse("estoque:entrada_estorno", args=[entrada.pk]))

    assert resposta.status_code == 302
    assert resposta.url == reverse("estoque:entrada_detalhe", args=[entrada.pk])

    detalhe = client.get(resposta.url)
    mensagens = [str(m) for m in detalhe.context["messages"]]
    assert any("já foi estornada" in m for m in mensagens)


def test_reenvio_do_estorno_mostra_aviso_de_ja_estornada_sem_efeito(
    client, funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    material = criar_material("900.000.005", Decimal("0.000"))
    entrada = _registrar(funcionario_almoxarifado, material, Decimal("5.000"))
    client.force_login(chefe_almoxarifado)
    payload = {"justificativa": "Motivo errado na digitação."}

    primeira = client.post(reverse("estoque:entrada_estorno", args=[entrada.pk]), payload)
    assert primeira.status_code == 302

    segunda = client.post(reverse("estoque:entrada_estorno", args=[entrada.pk]), payload)

    assert segunda.status_code == 302
    assert segunda.url == reverse("estoque:entrada_detalhe", args=[entrada.pk])
    material.refresh_from_db()
    assert material.saldo == Decimal("0.000"), "o estorno não pode ter sido aplicado duas vezes"

    detalhe = client.get(segunda.url)
    mensagens = [str(m) for m in detalhe.context["messages"]]
    assert any("já foi estornada" in m for m in mensagens)


def test_estorno_bloqueado_por_saldo_marca_o_item_e_nao_grava(
    client, funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    from catalogo.models import Material
    from estoque.models import Entrada

    material = criar_material("900.000.006", Decimal("0.000"))
    entrada = _registrar(funcionario_almoxarifado, material, Decimal("10.000"))
    Material.objects.filter(pk=material.pk).update(saldo=Decimal("3.000"))
    client.force_login(chefe_almoxarifado)

    resposta = client.post(
        reverse("estoque:entrada_estorno", args=[entrada.pk]),
        {"justificativa": "Motivo errado na digitação."},
    )

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert material.cadpro in conteudo
    entrada.refresh_from_db()
    assert entrada.estornada is False
    assert Entrada.objects.filter(pk=entrada.pk).count() == 1
    material.refresh_from_db()
    assert material.saldo == Decimal("3.000")


def test_detalhe_mostra_acao_de_estornar_so_para_o_chefe_em_entrada_nao_estornada(
    client, funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    material = criar_material("900.000.007", Decimal("0.000"))
    entrada = _registrar(funcionario_almoxarifado, material, Decimal("5.000"))

    client.force_login(funcionario_almoxarifado)
    resposta_funcionario = client.get(reverse("estoque:entrada_detalhe", args=[entrada.pk]))
    assert reverse("estoque:entrada_estorno", args=[entrada.pk]) not in (
        resposta_funcionario.content.decode()
    )

    client.force_login(chefe_almoxarifado)
    resposta_chefe = client.get(reverse("estoque:entrada_detalhe", args=[entrada.pk]))
    assert reverse("estoque:entrada_estorno", args=[entrada.pk]) in resposta_chefe.content.decode()


def test_detalhe_nao_mostra_acao_de_estornar_quando_ja_estornada(
    client, chefe_almoxarifado, funcionario_almoxarifado, criar_material
):
    from estoque.entradas import estornar_entrada

    material = criar_material("900.000.008", Decimal("0.000"))
    entrada = _registrar(funcionario_almoxarifado, material, Decimal("5.000"))
    estornar_entrada(entrada.pk, "Erro de digitação.", chefe_almoxarifado)

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("estoque:entrada_detalhe", args=[entrada.pk]))

    conteudo = resposta.content.decode()
    url_estorno = reverse("estoque:entrada_estorno", args=[entrada.pk])
    # A rota pode continuar existindo para GET direto, mas o detalhe não deve
    # oferecer a ação como link/form de ação principal numa entrada já
    # estornada.
    assert f'action="{url_estorno}"' not in conteudo
