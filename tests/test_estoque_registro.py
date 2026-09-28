"""Testes de `estoque.entradas.validar_entrada`/`registrar_entrada` (T009,
US1 — Registrar a entrada de materiais recebidos).

Cobre os cenários de aceitação 1, 2, 4 a 7 da spec, cada regra de
`EntradaInvalida` listada em `contracts/interface-estoque.md`, a
rastreabilidade (FR-016, FR-017, FR-019, `INV-MOV-002`), a conservação de
saldo (SC-001/SC-002) e a regressão de `INV-STOCK-002`/`INV-STOCK-003` contra
a reimportação do catálogo. Atomicidade e concorrência têm arquivos próprios
(`tests/test_estoque_atomicidade.py`, `tests/test_estoque_concorrencia.py`);
o estorno tem o seu (`tests/test_estoque_estorno.py`).

TDD: escrito antes de `estoque/entradas.py` existir — falha inteiro por
`ImportError` até lá.
"""

import uuid
from decimal import Decimal

import pytest
from django.utils import timezone

from estoque.entradas import (
    EmitenteIndisponivel,
    EntradaInformada,
    EntradaInvalida,
    EntradaJaRegistrada,
    ItemInformado,
    ReferenciaJaUsada,
    SaldoAcimaDoLimite,
    registrar_entrada,
    validar_entrada,
)
from estoque.models import (
    Entrada,
    ItemEntrada,
    MotivoEntrada,
    MovimentacaoEstoque,
    TipoDocumentoEntrada,
    TipoMovimentacao,
)

pytestmark = pytest.mark.django_db

SALDO_MAXIMO = Decimal("999999999999.999")


def _entrada_informada(
    *,
    motivo=MotivoEntrada.COMPRA,
    tipo_documento=TipoDocumentoEntrada.NOTA_FISCAL,
    numero_documento="NF-0001",
    emitente_id=None,
    itens=(),
    chave_confirmacao=None,
    tem_item_com_erro_de_formato=False,
):
    return EntradaInformada(
        chave_confirmacao=chave_confirmacao or uuid.uuid4(),
        motivo=motivo,
        tipo_documento=tipo_documento,
        numero_documento=numero_documento,
        emitente_id=emitente_id,
        itens=tuple(itens),
        tem_item_com_erro_de_formato=tem_item_com_erro_de_formato,
    )


# ---------------------------------------------------------------------------
# US1 — cenário 1: um item, saldo aumenta exatamente na quantidade informada,
# rastreabilidade completa.
# ---------------------------------------------------------------------------


def test_entrada_de_um_item_aumenta_o_saldo_e_registra_a_operacao(
    funcionario_almoxarifado, criar_material, criar_fornecedor
):
    material = criar_material("200.000.001", Decimal("10.000"))
    fornecedor = criar_fornecedor("2001", "Fornecedor Compra")
    dados = _entrada_informada(
        motivo=MotivoEntrada.COMPRA,
        numero_documento="12345",
        emitente_id=fornecedor.pk,
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("5.000"))],
    )

    antes = timezone.now()
    entrada = registrar_entrada(dados, funcionario_almoxarifado)
    depois = timezone.now()

    material.refresh_from_db()
    assert material.saldo == Decimal("15.000")

    assert entrada.motivo == MotivoEntrada.COMPRA
    assert entrada.numero_documento == "12345"
    assert entrada.emitente_id == fornecedor.pk
    assert entrada.registrada_por_id == funcionario_almoxarifado.pk
    assert antes <= entrada.registrada_em <= depois
    assert entrada.estornada is False

    item = ItemEntrada.objects.get(entrada=entrada, material=material)
    assert item.quantidade == Decimal("5.000")

    movimentacao = MovimentacaoEstoque.objects.get(item_entrada=item)
    assert movimentacao.tipo == TipoMovimentacao.ENTRADA
    assert movimentacao.variacao == Decimal("5.000")
    assert movimentacao.saldo_anterior == Decimal("10.000")
    assert movimentacao.saldo_posterior == Decimal("15.000")
    assert movimentacao.registrada_por_id == funcionario_almoxarifado.pk
    assert movimentacao.registrada_em == entrada.registrada_em


# ---------------------------------------------------------------------------
# US1 — cenário 2: uma única entrada com dois itens sob o mesmo motivo e a
# mesma referência.
# ---------------------------------------------------------------------------


def test_entrada_com_dois_itens_atualiza_os_dois_saldos_sob_a_mesma_entrada(
    funcionario_almoxarifado, criar_material
):
    material_a = criar_material("200.000.002", Decimal("10.000"))
    material_b = criar_material("200.000.003", Decimal("0.000"))
    dados = _entrada_informada(
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        numero_documento="TD-0001",
        itens=[
            ItemInformado(material_id=material_a.pk, quantidade=Decimal("4.000")),
            ItemInformado(material_id=material_b.pk, quantidade=Decimal("6.000")),
        ],
    )

    entrada = registrar_entrada(dados, funcionario_almoxarifado)

    material_a.refresh_from_db()
    material_b.refresh_from_db()
    assert material_a.saldo == Decimal("14.000")
    assert material_b.saldo == Decimal("6.000")
    assert ItemEntrada.objects.filter(entrada=entrada).count() == 2
    assert MovimentacaoEstoque.objects.filter(item_entrada__entrada=entrada).count() == 2


# ---------------------------------------------------------------------------
# US1 — cenário 4: quantidade decimal, sem arredondamento e sem conversão de
# unidade (INV-CATALOG-005).
# ---------------------------------------------------------------------------


def test_entrada_com_quantidade_decimal_preserva_tres_casas_e_a_unidade(
    funcionario_almoxarifado, criar_material
):
    material = criar_material("200.000.004", Decimal("2.500"), unidade="KG")
    dados = _entrada_informada(
        motivo=MotivoEntrada.EMPRESTIMO_DEVOLVIDO,
        numero_documento="TR-0001",
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("0.750"))],
    )

    registrar_entrada(dados, funcionario_almoxarifado)

    material.refresh_from_db()
    assert material.saldo == Decimal("3.250")
    assert material.unidade == "KG"


# ---------------------------------------------------------------------------
# US1 — cenário 5: dados inválidos recusados por campo, nada gravado.
# ---------------------------------------------------------------------------


def test_lista_de_itens_vazia_e_recusada_sem_gravar_nada(funcionario_almoxarifado):
    dados = _entrada_informada(motivo=MotivoEntrada.DOACAO_RECEBIDA, itens=[])

    with pytest.raises(EntradaInvalida) as excinfo:
        validar_entrada(dados)
    assert any(excinfo.value.erros_campo.values()) or excinfo.value.erros_campo

    with pytest.raises(EntradaInvalida):
        registrar_entrada(dados, funcionario_almoxarifado)
    assert Entrada.objects.count() == 0


# ---------------------------------------------------------------------------
# NOVO (2ª rodada do code-reviewer, item 3): `tem_item_com_erro_de_formato`
# é uma regra de domínio, não um detalhe da view — `validar_entrada`/
# `registrar_entrada` recusam com `EntradaInvalida` sempre que a flag estiver
# ligada, mesmo chamadas diretamente (sem passar por `estoque/views.py`),
# tanto com a lista de itens vazia quanto com itens parciais (algum item
# válido presente, mas outro excluído por erro de formato em outra linha).
# Nunca pode registrar uma entrada vazia ou parcial.
# ---------------------------------------------------------------------------


def test_flag_de_erro_de_formato_e_recusada_mesmo_com_itens_vazios(funcionario_almoxarifado):
    dados = _entrada_informada(
        motivo=MotivoEntrada.DOACAO_RECEBIDA, itens=[], tem_item_com_erro_de_formato=True
    )

    with pytest.raises(EntradaInvalida):
        validar_entrada(dados)

    with pytest.raises(EntradaInvalida):
        registrar_entrada(dados, funcionario_almoxarifado)
    assert Entrada.objects.count() == 0
    assert ItemEntrada.objects.count() == 0


def test_flag_de_erro_de_formato_e_recusada_mesmo_com_itens_parciais(
    funcionario_almoxarifado, criar_material
):
    material = criar_material("200.000.004", Decimal("10.000"))
    dados = _entrada_informada(
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("5.000"))],
        tem_item_com_erro_de_formato=True,
    )

    with pytest.raises(EntradaInvalida):
        validar_entrada(dados)

    with pytest.raises(EntradaInvalida):
        registrar_entrada(dados, funcionario_almoxarifado)
    assert Entrada.objects.count() == 0
    assert ItemEntrada.objects.count() == 0
    material.refresh_from_db()
    assert material.saldo == Decimal("10.000"), "o item parcial não pode ter sido aplicado"


def test_material_repetido_e_recusado_apontando_o_item(funcionario_almoxarifado, criar_material):
    material = criar_material("200.000.005", Decimal("10.000"))
    dados = _entrada_informada(
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        itens=[
            ItemInformado(material_id=material.pk, quantidade=Decimal("1.000")),
            ItemInformado(material_id=material.pk, quantidade=Decimal("2.000")),
        ],
    )

    with pytest.raises(EntradaInvalida) as excinfo:
        validar_entrada(dados)
    # A posição do item repetido (índice 1, a segunda ocorrência) precisa
    # estar identificada em `erros_item`.
    assert excinfo.value.erros_item

    material.refresh_from_db()
    assert material.saldo == Decimal("10.000")
    assert Entrada.objects.count() == 0


def test_material_inexistente_e_recusado(funcionario_almoxarifado):
    dados = _entrada_informada(
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        itens=[ItemInformado(material_id=999_999_999, quantidade=Decimal("1.000"))],
    )

    with pytest.raises(EntradaInvalida):
        registrar_entrada(dados, funcionario_almoxarifado)
    assert Entrada.objects.count() == 0


@pytest.mark.parametrize("motivo", ["MOTIVO_INEXISTENTE"])
def test_motivo_fora_da_lista_fechada_e_recusado(funcionario_almoxarifado, criar_material, motivo):
    material = criar_material("200.000.006", Decimal("10.000"))
    dados = _entrada_informada(
        motivo=motivo,
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("1.000"))],
    )

    with pytest.raises(EntradaInvalida):
        registrar_entrada(dados, funcionario_almoxarifado)
    assert Entrada.objects.count() == 0


def test_tipo_documento_fora_da_lista_fechada_e_recusado(funcionario_almoxarifado, criar_material):
    material = criar_material("200.000.007", Decimal("10.000"))
    dados = _entrada_informada(
        tipo_documento="TIPO_INEXISTENTE",
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("1.000"))],
        emitente_id=None,
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
    )

    with pytest.raises(EntradaInvalida):
        registrar_entrada(dados, funcionario_almoxarifado)
    assert Entrada.objects.count() == 0


def test_numero_do_documento_so_com_espacos_e_tratado_como_ausente(
    funcionario_almoxarifado, criar_material
):
    material = criar_material("200.000.008", Decimal("10.000"))
    dados = _entrada_informada(
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        numero_documento="   ",
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("1.000"))],
    )

    with pytest.raises(EntradaInvalida):
        registrar_entrada(dados, funcionario_almoxarifado)
    assert Entrada.objects.count() == 0


@pytest.mark.parametrize(
    "motivo", [MotivoEntrada.COMPRA, MotivoEntrada.DEVOLUCAO_FORNECEDOR_GARANTIA]
)
def test_emitente_ausente_e_recusado_nos_motivos_que_exigem(
    funcionario_almoxarifado, criar_material, motivo
):
    material = criar_material("200.000.009", Decimal("10.000"))
    dados = _entrada_informada(
        motivo=motivo,
        emitente_id=None,
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("1.000"))],
    )

    with pytest.raises(EntradaInvalida):
        registrar_entrada(dados, funcionario_almoxarifado)
    assert Entrada.objects.count() == 0


@pytest.mark.parametrize(
    "motivo", [MotivoEntrada.DOACAO_RECEBIDA, MotivoEntrada.EMPRESTIMO_DEVOLVIDO]
)
def test_emitente_ausente_e_aceito_nos_motivos_em_que_e_opcional(
    funcionario_almoxarifado, criar_material, motivo
):
    material = criar_material("200.000.010", Decimal("10.000"))
    dados = _entrada_informada(
        motivo=motivo,
        emitente_id=None,
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("1.000"))],
    )

    entrada = registrar_entrada(dados, funcionario_almoxarifado)

    assert entrada.emitente_id is None


def test_emitente_inexistente_e_recusado(funcionario_almoxarifado, criar_material):
    material = criar_material("200.000.011", Decimal("10.000"))
    dados = _entrada_informada(
        motivo=MotivoEntrada.COMPRA,
        emitente_id=999_999_999,
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("1.000"))],
    )

    with pytest.raises((EntradaInvalida, EmitenteIndisponivel)):
        registrar_entrada(dados, funcionario_almoxarifado)
    assert Entrada.objects.count() == 0


def test_emitente_bloqueado_e_recusado(funcionario_almoxarifado, criar_material, criar_fornecedor):
    material = criar_material("200.000.012", Decimal("10.000"))
    fornecedor = criar_fornecedor("2002", "Fornecedor Bloqueado", bloqueado=True)
    dados = _entrada_informada(
        motivo=MotivoEntrada.COMPRA,
        emitente_id=fornecedor.pk,
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("1.000"))],
    )

    with pytest.raises((EntradaInvalida, EmitenteIndisponivel)):
        registrar_entrada(dados, funcionario_almoxarifado)
    assert Entrada.objects.count() == 0


def test_saldo_resultante_acima_do_limite_e_recusado_sem_gravar(
    funcionario_almoxarifado, criar_material
):
    material = criar_material("200.000.013", SALDO_MAXIMO)
    dados = _entrada_informada(
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("0.001"))],
    )

    with pytest.raises((EntradaInvalida, SaldoAcimaDoLimite)):
        registrar_entrada(dados, funcionario_almoxarifado)

    material.refresh_from_db()
    assert material.saldo == SALDO_MAXIMO
    assert Entrada.objects.count() == 0


def test_saldo_resultante_exatamente_no_limite_e_aceito(funcionario_almoxarifado, criar_material):
    """Fronteira exata do limite (research R11): `999.999.999.999,999` é um
    saldo válido — a recusa é só ACIMA dele."""
    material = criar_material("200.000.014", SALDO_MAXIMO - Decimal("0.001"))
    dados = _entrada_informada(
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("0.001"))],
    )

    registrar_entrada(dados, funcionario_almoxarifado)

    material.refresh_from_db()
    assert material.saldo == SALDO_MAXIMO


def test_validar_entrada_e_somente_leitura(funcionario_almoxarifado, criar_material):
    """`validar_entrada` nunca grava, esteja a entrada válida ou não —
    Revisar" chama exatamente essa função."""
    material = criar_material("200.000.015", Decimal("10.000"))
    dados = _entrada_informada(
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("5.000"))],
    )

    validar_entrada(dados)  # não deveria levantar nem gravar

    material.refresh_from_db()
    assert material.saldo == Decimal("10.000")
    assert Entrada.objects.count() == 0
    assert ItemEntrada.objects.count() == 0
    assert MovimentacaoEstoque.objects.count() == 0


# ---------------------------------------------------------------------------
# US1 — cenário 6: referência já usada em entrada não estornada.
# ---------------------------------------------------------------------------


def test_referencia_ja_usada_e_recusada_apontando_a_entrada_existente(
    funcionario_almoxarifado, criar_material, criar_fornecedor
):
    material = criar_material("200.000.016", Decimal("10.000"))
    fornecedor = criar_fornecedor("2003", "Fornecedor Referência")
    primeira = registrar_entrada(
        _entrada_informada(
            motivo=MotivoEntrada.COMPRA,
            numero_documento="12345",
            emitente_id=fornecedor.pk,
            itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("1.000"))],
        ),
        funcionario_almoxarifado,
    )

    segunda = _entrada_informada(
        motivo=MotivoEntrada.COMPRA,
        numero_documento="12345",
        emitente_id=fornecedor.pk,
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("2.000"))],
    )

    with pytest.raises(ReferenciaJaUsada) as excinfo:
        registrar_entrada(segunda, funcionario_almoxarifado)

    assert excinfo.value.entrada.pk == primeira.pk
    material.refresh_from_db()
    assert material.saldo == Decimal("11.000"), "só a primeira entrada pode ter afetado o saldo"
    assert Entrada.objects.count() == 1


def test_referencia_e_reutilizavel_depois_de_estornada(
    funcionario_almoxarifado, criar_material, criar_fornecedor
):
    material = criar_material("200.000.017", Decimal("10.000"))
    fornecedor = criar_fornecedor("2004", "Fornecedor Referência 2")
    primeira = registrar_entrada(
        _entrada_informada(
            motivo=MotivoEntrada.COMPRA,
            numero_documento="54321",
            emitente_id=fornecedor.pk,
            itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("1.000"))],
        ),
        funcionario_almoxarifado,
    )
    Entrada.objects.filter(pk=primeira.pk).update(estornada=True)

    segunda = registrar_entrada(
        _entrada_informada(
            motivo=MotivoEntrada.COMPRA,
            numero_documento="54321",
            emitente_id=fornecedor.pk,
            itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("2.000"))],
        ),
        funcionario_almoxarifado,
    )

    assert segunda.pk != primeira.pk
    assert Entrada.objects.filter(numero_documento="54321").count() == 2


# ---------------------------------------------------------------------------
# US1 — cenário 7: material repetido — já coberto acima
# (test_material_repetido_e_recusado_apontando_o_item).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Idempotência da confirmação (FR-013, SC-005) — em sequência; concorrência
# real fica em tests/test_estoque_concorrencia.py.
# ---------------------------------------------------------------------------


def test_confirmar_a_mesma_chave_duas_vezes_em_sequencia_recebe_ja_registrada(
    funcionario_almoxarifado, criar_material
):
    material = criar_material("200.000.018", Decimal("10.000"))
    chave = uuid.uuid4()
    dados = _entrada_informada(
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        chave_confirmacao=chave,
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("5.000"))],
    )

    entrada = registrar_entrada(dados, funcionario_almoxarifado)

    with pytest.raises(EntradaJaRegistrada) as excinfo:
        registrar_entrada(dados, funcionario_almoxarifado)

    assert excinfo.value.entrada.pk == entrada.pk
    material.refresh_from_db()
    assert material.saldo == Decimal("15.000")
    assert Entrada.objects.count() == 1


# ---------------------------------------------------------------------------
# Material com saldo zero: aceita entrada normalmente (Edge Cases).
# ---------------------------------------------------------------------------


def test_material_com_saldo_zero_aceita_entrada(funcionario_almoxarifado, criar_material):
    material = criar_material("200.000.019", Decimal("0.000"))
    dados = _entrada_informada(
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("1.000"))],
    )

    registrar_entrada(dados, funcionario_almoxarifado)

    material.refresh_from_db()
    assert material.saldo == Decimal("1.000")


# ---------------------------------------------------------------------------
# Número do documento gravado aparado, sem outra normalização (research R6).
# ---------------------------------------------------------------------------


def test_numero_do_documento_e_gravado_aparado_sem_outra_normalizacao(
    funcionario_almoxarifado, criar_material
):
    material = criar_material("200.000.020", Decimal("10.000"))
    dados = _entrada_informada(
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        numero_documento="  001.234-A  ",
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("1.000"))],
    )

    entrada = registrar_entrada(dados, funcionario_almoxarifado)

    assert entrada.numero_documento == "001.234-A"


# ---------------------------------------------------------------------------
# Preservação: campos cadastrais e outros materiais intactos (FR-015,
# INV-CATALOG-004); consistência item x movimentação (SC-002).
# ---------------------------------------------------------------------------


def test_entrada_nao_altera_dados_cadastrais_nem_outros_materiais(
    funcionario_almoxarifado, criar_material
):
    material_alvo = criar_material("200.000.021", Decimal("10.000"), descricao="Parafuso M6")
    material_intocado = criar_material("200.000.022", Decimal("7.000"), descricao="Porca M6")
    descricao_original = material_intocado.descricao
    unidade_original = material_intocado.unidade

    dados = _entrada_informada(
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        itens=[ItemInformado(material_id=material_alvo.pk, quantidade=Decimal("3.000"))],
    )
    registrar_entrada(dados, funcionario_almoxarifado)

    material_alvo.refresh_from_db()
    material_intocado.refresh_from_db()
    assert material_alvo.descricao == "Parafuso M6"  # dado cadastral, não tocado
    assert material_intocado.saldo == Decimal("7.000"), "material fora da entrada não muda"
    assert material_intocado.descricao == descricao_original
    assert material_intocado.unidade == unidade_original


def test_quantidade_do_item_e_igual_ao_modulo_da_variacao_da_movimentacao(
    funcionario_almoxarifado, criar_material
):
    material = criar_material("200.000.023", Decimal("10.000"))
    dados = _entrada_informada(
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("2.500"))],
    )

    entrada = registrar_entrada(dados, funcionario_almoxarifado)

    item = ItemEntrada.objects.get(entrada=entrada, material=material)
    movimentacao = MovimentacaoEstoque.objects.get(item_entrada=item)
    assert movimentacao.variacao == item.quantidade
    assert movimentacao.material_id == item.material_id


# ---------------------------------------------------------------------------
# Conservação de saldo (SC-001) sobre uma sequência de entradas.
# ---------------------------------------------------------------------------


def test_conservacao_de_saldo_apos_sequencia_de_entradas(funcionario_almoxarifado, criar_material):
    material = criar_material("200.000.024", Decimal("10.000"))
    saldo_inicial = material.saldo_inicial

    for quantidade in (Decimal("1.000"), Decimal("2.500"), Decimal("0.500")):
        registrar_entrada(
            _entrada_informada(
                motivo=MotivoEntrada.DOACAO_RECEBIDA,
                numero_documento=str(uuid.uuid4()),
                itens=[ItemInformado(material_id=material.pk, quantidade=quantidade)],
            ),
            funcionario_almoxarifado,
        )

    material.refresh_from_db()
    soma_variacoes = sum(
        (m.variacao for m in MovimentacaoEstoque.objects.filter(material=material)),
        Decimal("0.000"),
    )
    assert material.saldo == saldo_inicial + soma_variacoes
    assert material.saldo == Decimal("14.000")


# ---------------------------------------------------------------------------
# Regressão INV-STOCK-002/INV-STOCK-003: reimportar o catálogo depois de uma
# entrada preserva o saldo alterado; a diferença vira divergência
# informativa, nunca sobrescreve o saldo (Edge Cases da spec 003).
# ---------------------------------------------------------------------------


def test_reimportacao_do_catalogo_depois_de_uma_entrada_preserva_o_saldo(
    funcionario_almoxarifado, csv_fixture
):
    from catalogo import importacao as catalogo_importacao
    from catalogo.models import DivergenciaSaldo, Material

    conteudo_inicial = csv_fixture("carga_inicial_valida.csv")
    plano_inicial = catalogo_importacao.calcular_plano(conteudo_inicial)
    pedido_inicial = catalogo_importacao.PedidoPrevia(
        token=str(uuid.uuid4()),
        nome_arquivo="inicial.csv",
        tamanho=len(conteudo_inicial),
        sha256=plano_inicial.sha256_arquivo,
        conteudo=conteudo_inicial,
    )
    catalogo_importacao.confirmar_importacao(
        pedido_inicial, plano_inicial.impressao_digital, funcionario_almoxarifado
    )

    # `010.020.030` (README de tests/fixtures/catalogo/): arquivo de
    # reimportação NÃO muda nada nele (saldo do arquivo permanece 25.000).
    # Uma entrada eleva o saldo do WMS para 30.000 antes da reimportação —
    # se ela sobrescrevesse o saldo (violando INV-STOCK-002), a reimportação
    # devolveria 25.000; o correto é preservar 30.000 e registrar a diferença
    # como DivergenciaSaldo puramente informativa (INV-STOCK-003).
    material = Material.objects.get(cadpro="010.020.030")
    assert material.saldo == Decimal("25.000"), "pré-condição: saldo original da carga inicial"

    registrar_entrada(
        _entrada_informada(
            motivo=MotivoEntrada.DOACAO_RECEBIDA,
            itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("5.000"))],
        ),
        funcionario_almoxarifado,
    )
    material.refresh_from_db()
    assert material.saldo == Decimal("30.000")

    conteudo_reimportacao = csv_fixture("reimportacao.csv")
    plano_reimportacao = catalogo_importacao.calcular_plano(conteudo_reimportacao)
    pedido_reimportacao = catalogo_importacao.PedidoPrevia(
        token=str(uuid.uuid4()),
        nome_arquivo="reimportacao.csv",
        tamanho=len(conteudo_reimportacao),
        sha256=plano_reimportacao.sha256_arquivo,
        conteudo=conteudo_reimportacao,
    )
    catalogo_importacao.confirmar_importacao(
        pedido_reimportacao, plano_reimportacao.impressao_digital, funcionario_almoxarifado
    )

    material.refresh_from_db()
    assert material.saldo == Decimal("30.000"), (
        "INV-STOCK-002: a reimportação não pode sobrescrever o saldo alterado pela entrada"
    )
    divergencia = DivergenciaSaldo.objects.get(material=material)
    assert divergencia.saldo_wms == Decimal("30.000")
    assert divergencia.saldo_arquivo == Decimal("25.000")
    assert divergencia.diferenca == Decimal("-5.000")
