"""Testes de atomicidade do registro e do estorno de entrada (T010, T026).

Cobre `INV-STOCK-004` (nenhuma operação composta pode concluir parcialmente):
falha injetada por `monkeypatch`/`unittest.mock` no MEIO da operação — depois
que o primeiro item já teria sido gravado — precisa desfazer TUDO da mesma
transação, não só o que vem depois do ponto de falha. Mesmo padrão de
`tests/test_catalogo_atomicidade.py` (T017): cada teste usa uma entrada com
pelo menos DOIS itens, para que o primeiro já esteja "gravado" (dentro da
transação ainda aberta) quando o segundo falha — só assim o teste prova
rollback de verdade, não apenas ausência do efeito que falhou.

TDD: escrito antes de `estoque/entradas.py` existir — falha inteiro por
`ImportError` até lá.
"""

import uuid
from decimal import Decimal
from unittest import mock

import pytest

from estoque.entradas import (
    EntradaInformada,
    ItemInformado,
    estornar_entrada,
    registrar_entrada,
)
from estoque.models import (
    Entrada,
    EstornoEntrada,
    ItemEntrada,
    MotivoEntrada,
    MovimentacaoEstoque,
    TipoDocumentoEntrada,
)

pytestmark = pytest.mark.django_db


def _entrada_informada(*, itens, numero_documento=None, motivo=MotivoEntrada.DOACAO_RECEBIDA):
    return EntradaInformada(
        chave_confirmacao=uuid.uuid4(),
        motivo=motivo,
        tipo_documento=TipoDocumentoEntrada.NOTA_FISCAL,
        numero_documento=numero_documento or str(uuid.uuid4()),
        emitente_id=None,
        itens=tuple(itens),
    )


def _falha_na_enesima_chamada(original, n, excecao):
    """Encapsula `original` para se comportar normalmente nas primeiras
    `n - 1` chamadas e levantar `excecao` exatamente na enésima — prova que o
    que já rodou ANTES do ponto de falha, dentro da mesma transação, também é
    desfeito (não só o efeito que falharia)."""
    estado = {"chamadas": 0}

    def _wrapper(*args, **kwargs):
        estado["chamadas"] += 1
        if estado["chamadas"] == n:
            raise excecao
        return original(*args, **kwargs)

    return _wrapper


def _contagens():
    return {
        "Entrada": Entrada.objects.count(),
        "ItemEntrada": ItemEntrada.objects.count(),
        "MovimentacaoEstoque": MovimentacaoEstoque.objects.count(),
        "EstornoEntrada": EstornoEntrada.objects.count(),
    }


# ---------------------------------------------------------------------------
# Registro: falha depois da primeira MovimentacaoEstoque.
# ---------------------------------------------------------------------------


def test_falha_apos_a_primeira_movimentacao_desfaz_o_registro_inteiro(
    funcionario_almoxarifado, criar_material
):
    material_a = criar_material("300.000.001", Decimal("10.000"))
    material_b = criar_material("300.000.002", Decimal("20.000"))
    dados = _entrada_informada(
        itens=[
            ItemInformado(material_id=material_a.pk, quantidade=Decimal("1.000")),
            ItemInformado(material_id=material_b.pk, quantidade=Decimal("2.000")),
        ]
    )

    estado_antes = _contagens()
    original_create = MovimentacaoEstoque.objects.create
    with mock.patch.object(
        MovimentacaoEstoque.objects,
        "create",
        side_effect=_falha_na_enesima_chamada(
            original_create, 2, RuntimeError("falha injetada — 2ª movimentação")
        ),
    ):
        with pytest.raises(RuntimeError, match="falha injetada"):
            registrar_entrada(dados, funcionario_almoxarifado)

    assert _contagens() == estado_antes
    material_a.refresh_from_db()
    material_b.refresh_from_db()
    assert material_a.saldo == Decimal("10.000")
    assert material_b.saldo == Decimal("20.000")


# ---------------------------------------------------------------------------
# Registro: falha depois da primeira atualização de Material.saldo.
# ---------------------------------------------------------------------------


def test_falha_apos_a_primeira_atualizacao_de_saldo_desfaz_o_registro_inteiro(
    funcionario_almoxarifado, criar_material
):
    from catalogo.models import Material

    material_a = criar_material("300.000.003", Decimal("10.000"))
    material_b = criar_material("300.000.004", Decimal("20.000"))
    dados = _entrada_informada(
        itens=[
            ItemInformado(material_id=material_a.pk, quantidade=Decimal("1.000")),
            ItemInformado(material_id=material_b.pk, quantidade=Decimal("2.000")),
        ]
    )

    estado_antes = _contagens()
    original_save = Material.save
    with mock.patch.object(
        Material,
        "save",
        side_effect=_falha_na_enesima_chamada(
            original_save, 2, RuntimeError("falha injetada — 2º saldo")
        ),
        autospec=True,
    ):
        with pytest.raises(RuntimeError, match="falha injetada"):
            registrar_entrada(dados, funcionario_almoxarifado)

    assert _contagens() == estado_antes
    material_a.refresh_from_db()
    material_b.refresh_from_db()
    assert material_a.saldo == Decimal("10.000")
    assert material_b.saldo == Decimal("20.000")


# ---------------------------------------------------------------------------
# Estorno: falha depois da primeira redução de saldo/movimentação de
# estorno — a entrada NÃO pode ficar marcada como estornada, nem parte dos
# saldos reduzida.
# ---------------------------------------------------------------------------


def test_falha_no_meio_do_estorno_desfaz_tudo_e_a_entrada_continua_nao_estornada(
    funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    material_a = criar_material("300.000.005", Decimal("10.000"))
    material_b = criar_material("300.000.006", Decimal("20.000"))
    entrada = registrar_entrada(
        _entrada_informada(
            itens=[
                ItemInformado(material_id=material_a.pk, quantidade=Decimal("4.000")),
                ItemInformado(material_id=material_b.pk, quantidade=Decimal("5.000")),
            ]
        ),
        funcionario_almoxarifado,
    )
    material_a.refresh_from_db()
    material_b.refresh_from_db()
    saldo_a_pos_entrada = material_a.saldo
    saldo_b_pos_entrada = material_b.saldo
    estado_antes = _contagens()

    original_create = MovimentacaoEstoque.objects.create
    with mock.patch.object(
        MovimentacaoEstoque.objects,
        "create",
        side_effect=_falha_na_enesima_chamada(
            original_create, 2, RuntimeError("falha injetada — 2ª movimentação de estorno")
        ),
    ):
        with pytest.raises(RuntimeError, match="falha injetada"):
            estornar_entrada(entrada.pk, "Erro de digitação na quantidade.", chefe_almoxarifado)

    assert _contagens() == estado_antes
    entrada.refresh_from_db()
    assert entrada.estornada is False
    material_a.refresh_from_db()
    material_b.refresh_from_db()
    assert material_a.saldo == saldo_a_pos_entrada
    assert material_b.saldo == saldo_b_pos_entrada
