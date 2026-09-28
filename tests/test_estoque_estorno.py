"""Testes de `estoque.entradas.estornar_entrada` (T025, US3 — Corrigir uma
entrada registrada com erro).

Cobre os cenários de aceitação 1 a 4 da US3, `INV-ENT-001` (total, no máximo
uma vez), `INV-STOCK-001` (bloqueio por saldo insuficiente), `INV-MOV-001`
(fatos da entrada original inalterados) e `INV-MOV-002` (uma movimentação
`ESTORNO_ENTRADA` por item). Atomicidade e concorrência do estorno têm
arquivo próprio (`tests/test_estoque_atomicidade.py`,
`tests/test_estoque_concorrencia.py`).

TDD: escrito antes de `estoque/entradas.py` existir — falha inteiro por
`ImportError` até lá.
"""

import uuid
from decimal import Decimal

import pytest
from django.utils import timezone
from estoque.entradas import (
    EntradaInformada,
    EntradaJaEstornada,
    EstornoBloqueadoPorSaldo,
    ItemInformado,
    JustificativaAusente,
    estornar_entrada,
    registrar_entrada,
)

from estoque.models import (
    Entrada,
    EstornoEntrada,
    MotivoEntrada,
    MovimentacaoEstoque,
    TipoDocumentoEntrada,
    TipoMovimentacao,
)

pytestmark = pytest.mark.django_db


def _registrar(autor, material_e_quantidades, **overrides):
    itens = [
        ItemInformado(material_id=material.pk, quantidade=quantidade)
        for material, quantidade in material_e_quantidades
    ]
    dados = EntradaInformada(
        chave_confirmacao=uuid.uuid4(),
        motivo=overrides.pop("motivo", MotivoEntrada.DOACAO_RECEBIDA),
        tipo_documento=overrides.pop("tipo_documento", TipoDocumentoEntrada.NOTA_FISCAL),
        numero_documento=overrides.pop("numero_documento", str(uuid.uuid4())),
        emitente_id=overrides.pop("emitente_id", None),
        itens=tuple(itens),
    )
    return registrar_entrada(dados, autor)


# ---------------------------------------------------------------------------
# US3 — cenário 1: estorno total, saldos voltam ao que eram.
# ---------------------------------------------------------------------------


def test_estorno_total_restaura_os_saldos_e_marca_a_entrada(
    funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    material_a = criar_material("500.000.001", Decimal("10.000"))
    material_b = criar_material("500.000.002", Decimal("0.000"))
    entrada = _registrar(
        funcionario_almoxarifado,
        [(material_a, Decimal("4.000")), (material_b, Decimal("6.000"))],
    )
    material_a.refresh_from_db()
    material_b.refresh_from_db()
    assert material_a.saldo == Decimal("14.000")
    assert material_b.saldo == Decimal("6.000")

    antes = timezone.now()
    estorno = estornar_entrada(
        entrada.pk, "Motivo/quantidade errados na digitação.", chefe_almoxarifado
    )
    depois = timezone.now()

    material_a.refresh_from_db()
    material_b.refresh_from_db()
    assert material_a.saldo == Decimal("10.000")
    assert material_b.saldo == Decimal("0.000")

    entrada.refresh_from_db()
    assert entrada.estornada is True
    assert estorno.entrada_id == entrada.pk
    assert estorno.estornada_por_id == chefe_almoxarifado.pk
    assert antes <= estorno.estornada_em <= depois
    assert estorno.justificativa == "Motivo/quantidade errados na digitação."


def test_estorno_gera_uma_movimentacao_estorno_entrada_por_item_com_sinal_negativo(
    funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    material = criar_material("500.000.003", Decimal("0.000"))
    entrada = _registrar(funcionario_almoxarifado, [(material, Decimal("7.000"))])

    estornar_entrada(entrada.pk, "Erro de digitação.", chefe_almoxarifado)

    item = entrada.itens.get(material=material)
    movimentacao = MovimentacaoEstoque.objects.get(
        item_entrada=item, tipo=TipoMovimentacao.ESTORNO_ENTRADA
    )
    assert movimentacao.variacao == Decimal("-7.000")
    assert movimentacao.saldo_anterior == Decimal("7.000")
    assert movimentacao.saldo_posterior == Decimal("0.000")
    assert movimentacao.registrada_por_id == chefe_almoxarifado.pk

    # A movimentação ENTRADA original continua intacta ao lado da nova
    # (SC-002: uma de cada tipo por item, nunca sobrescrita).
    movimentacao_entrada = MovimentacaoEstoque.objects.get(
        item_entrada=item, tipo=TipoMovimentacao.ENTRADA
    )
    assert movimentacao_entrada.variacao == Decimal("7.000")


# ---------------------------------------------------------------------------
# US3 — cenário 2: estorno bloqueado por saldo insuficiente.
# ---------------------------------------------------------------------------


def test_estorno_bloqueado_por_saldo_insuficiente_lista_o_item_e_nao_tem_efeito(
    funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    from catalogo.models import Material

    material = criar_material("500.000.004", Decimal("0.000"))
    entrada = _registrar(funcionario_almoxarifado, [(material, Decimal("10.000"))])
    # Simula que parte do material já saiu por outra via (fora do escopo
    # desta feature) entre o registro e a tentativa de estorno — saldo atual
    # 7, entrada pede estorno de 10.
    Material.objects.filter(pk=material.pk).update(saldo=Decimal("7.000"))

    with pytest.raises(EstornoBloqueadoPorSaldo) as excinfo:
        estornar_entrada(entrada.pk, "Erro de digitação.", chefe_almoxarifado)

    itens_bloqueados = excinfo.value.itens
    assert itens_bloqueados
    materiais_bloqueados = {item.material_id for item, _saldo_atual in itens_bloqueados}
    assert material.pk in materiais_bloqueados

    entrada.refresh_from_db()
    assert entrada.estornada is False
    material.refresh_from_db()
    assert material.saldo == Decimal("7.000")
    assert EstornoEntrada.objects.filter(entrada=entrada).count() == 0
    assert not MovimentacaoEstoque.objects.filter(
        item_entrada__entrada=entrada, tipo=TipoMovimentacao.ESTORNO_ENTRADA
    ).exists()


def test_estorno_bloqueado_e_recusado_por_inteiro_mesmo_com_um_so_item_problematico(
    funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    """FR-026: um único item que ficaria negativo bloqueia o estorno
    INTEIRO — nenhum outro item da mesma entrada é revertido "parcialmente"."""
    from catalogo.models import Material

    material_ok = criar_material("500.000.005", Decimal("0.000"))
    material_problema = criar_material("500.000.006", Decimal("0.000"))
    entrada = _registrar(
        funcionario_almoxarifado,
        [(material_ok, Decimal("3.000")), (material_problema, Decimal("5.000"))],
    )
    Material.objects.filter(pk=material_problema.pk).update(saldo=Decimal("2.000"))

    with pytest.raises(EstornoBloqueadoPorSaldo):
        estornar_entrada(entrada.pk, "Erro de digitação.", chefe_almoxarifado)

    material_ok.refresh_from_db()
    material_problema.refresh_from_db()
    assert material_ok.saldo == Decimal("3.000"), "nenhum item pode ter sido revertido sozinho"
    assert material_problema.saldo == Decimal("2.000")
    entrada.refresh_from_db()
    assert entrada.estornada is False


# ---------------------------------------------------------------------------
# US3 — cenário 3: estorno de estorno não existe.
# ---------------------------------------------------------------------------


def test_segunda_tentativa_de_estorno_da_mesma_entrada_e_recusada(
    funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    material = criar_material("500.000.007", Decimal("0.000"))
    entrada = _registrar(funcionario_almoxarifado, [(material, Decimal("5.000"))])
    estornar_entrada(entrada.pk, "Erro de digitação.", chefe_almoxarifado)

    with pytest.raises(EntradaJaEstornada) as excinfo:
        estornar_entrada(entrada.pk, "Segunda tentativa.", chefe_almoxarifado)

    assert excinfo.value.entrada.pk == entrada.pk
    assert EstornoEntrada.objects.filter(entrada=entrada).count() == 1
    material.refresh_from_db()
    assert material.saldo == Decimal("0.000"), "o estorno não pode ter sido aplicado duas vezes"


# ---------------------------------------------------------------------------
# US3 — cenário 4: justificativa obrigatória.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("justificativa", ["", "   "])
def test_justificativa_vazia_ou_so_espacos_e_recusada_sem_efeito(
    funcionario_almoxarifado, chefe_almoxarifado, criar_material, justificativa
):
    material = criar_material("500.000.008", Decimal("0.000"))
    entrada = _registrar(funcionario_almoxarifado, [(material, Decimal("5.000"))])

    with pytest.raises(JustificativaAusente):
        estornar_entrada(entrada.pk, justificativa, chefe_almoxarifado)

    entrada.refresh_from_db()
    assert entrada.estornada is False
    material.refresh_from_db()
    assert material.saldo == Decimal("5.000")


def test_justificativa_e_gravada_aparada(
    funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    material = criar_material("500.000.009", Decimal("0.000"))
    entrada = _registrar(funcionario_almoxarifado, [(material, Decimal("5.000"))])

    estorno = estornar_entrada(
        entrada.pk, "  Erro de digitação na quantidade.  ", chefe_almoxarifado
    )

    assert estorno.justificativa == "Erro de digitação na quantidade."


# ---------------------------------------------------------------------------
# Preservação dos fatos originais (FR-028, INV-MOV-001).
# ---------------------------------------------------------------------------


def test_estorno_nao_altera_os_fatos_da_entrada_original(
    funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    material = criar_material("500.000.010", Decimal("0.000"))
    entrada = _registrar(
        funcionario_almoxarifado,
        [(material, Decimal("5.000"))],
        numero_documento="TD-ORIGINAL",
    )
    motivo_original = entrada.motivo
    numero_original = entrada.numero_documento
    autor_original = entrada.registrada_por_id
    momento_original = entrada.registrada_em

    estornar_entrada(entrada.pk, "Erro de digitação.", chefe_almoxarifado)

    entrada.refresh_from_db()
    assert entrada.motivo == motivo_original
    assert entrada.numero_documento == numero_original
    assert entrada.registrada_por_id == autor_original
    assert entrada.registrada_em == momento_original
    assert entrada.estornada is True  # única mudança permitida


# ---------------------------------------------------------------------------
# Conservação de saldo (SC-001) numa sequência mista de entradas e estornos.
# ---------------------------------------------------------------------------


def test_conservacao_de_saldo_apos_sequencia_mista_de_entradas_e_estornos(
    funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    material = criar_material("500.000.011", Decimal("10.000"))
    saldo_inicial = material.saldo_inicial

    entrada_1 = _registrar(funcionario_almoxarifado, [(material, Decimal("5.000"))])
    _registrar(funcionario_almoxarifado, [(material, Decimal("3.000"))])
    estornar_entrada(entrada_1.pk, "Erro de digitação.", chefe_almoxarifado)
    _registrar(funcionario_almoxarifado, [(material, Decimal("2.000"))])

    material.refresh_from_db()
    # Entradas não estornadas: a segunda (3) e a terceira (2). A primeira (5)
    # foi estornada e não conta.
    itens_nao_estornados = Decimal("3.000") + Decimal("2.000")
    assert material.saldo == saldo_inicial + itens_nao_estornados
    assert material.saldo == Decimal("15.000")

    soma_variacoes = sum(
        (m.variacao for m in MovimentacaoEstoque.objects.filter(material=material)),
        Decimal("0.000"),
    )
    assert material.saldo == saldo_inicial + soma_variacoes


def test_referencia_liberada_para_nova_entrada_depois_do_estorno_via_dominio(
    funcionario_almoxarifado, chefe_almoxarifado, criar_material, criar_fornecedor
):
    """Mesma regra de `tests/test_estoque_registro.py::
    test_referencia_e_reutilizavel_depois_de_estornada`, mas exercitando o
    `estornar_entrada` de verdade (lá a marcação vinha de escrita direta)."""
    material = criar_material("500.000.012", Decimal("0.000"))
    fornecedor = criar_fornecedor("5001", "Fornecedor Reutilização")
    entrada = _registrar(
        funcionario_almoxarifado,
        [(material, Decimal("1.000"))],
        motivo=MotivoEntrada.COMPRA,
        numero_documento="NF-REUSO-0001",
        emitente_id=fornecedor.pk,
    )
    estornar_entrada(entrada.pk, "Erro de digitação.", chefe_almoxarifado)

    nova = _registrar(
        funcionario_almoxarifado,
        [(material, Decimal("2.000"))],
        motivo=MotivoEntrada.COMPRA,
        numero_documento="NF-REUSO-0001",
        emitente_id=fornecedor.pk,
    )

    assert nova.pk != entrada.pk
    assert Entrada.objects.filter(numero_documento="NF-REUSO-0001").count() == 2
