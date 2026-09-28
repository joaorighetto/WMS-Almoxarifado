"""Testes de model do app `estoque` (T007, Phase 2 — Foundational).

Escritos contra `data-model.md` e `research.md` R7, **antes** de
`estoque/models.py`/`estoque/apps.py` existirem (T005/T006) — até lá, este
arquivo falha inteiro por `ImportError`, o que é esperado (TDD).

Cobre exclusivamente a camada de dados: `CHECK`/`UNIQUE` de banco (incluindo a
referência única entre entradas não estornadas, `nulls_distinct=False`) e os
triggers de imutabilidade (`INV-MOV-001`). Não cobre `estoque.entradas`
(`tests/test_estoque_registro.py`/`test_estoque_estorno.py`) nem views.

As factories abaixo criam `Entrada`/`ItemEntrada`/`EstornoEntrada`/
`MovimentacaoEstoque` diretamente pelo ORM, contornando `estoque.entradas`.
Isso **não é caminho de produto** — só `registrar_entrada`/`estornar_entrada`
gravam esses fatos (FR-018, FR-025) — serve apenas para exercitar cada
constraint/trigger isoladamente, no mesmo espírito de
`tests/test_catalogo_modelos.py`.
"""

import uuid
from decimal import Decimal

import pytest
from django.contrib import admin
from django.db import DEFAULT_DB_ALIAS, Error, IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from estoque.models import (
    Entrada,
    EstornoEntrada,
    ItemEntrada,
    MotivoEntrada,
    MovimentacaoEstoque,
    TipoDocumentoEntrada,
    TipoMovimentacao,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Factories (não são caminho de produto — ver docstring do módulo)
# ---------------------------------------------------------------------------


def _criar_entrada(
    autor,
    *,
    motivo=MotivoEntrada.DOACAO_RECEBIDA,
    tipo_documento=TipoDocumentoEntrada.NOTA_FISCAL,
    numero_documento="NF-0001",
    emitente=None,
    estornada=False,
    chave_confirmacao=None,
):
    return Entrada.objects.create(
        chave_confirmacao=chave_confirmacao or uuid.uuid4(),
        motivo=motivo,
        tipo_documento=tipo_documento,
        numero_documento=numero_documento,
        emitente=emitente,
        registrada_por=autor,
        registrada_em=timezone.now(),
        estornada=estornada,
    )


def _criar_item(entrada, material, quantidade=Decimal("5.000")):
    return ItemEntrada.objects.create(entrada=entrada, material=material, quantidade=quantidade)


def _criar_movimentacao_entrada(item, autor, *, saldo_anterior, variacao):
    return MovimentacaoEstoque.objects.create(
        material=item.material,
        tipo=TipoMovimentacao.ENTRADA,
        variacao=variacao,
        saldo_anterior=saldo_anterior,
        saldo_posterior=saldo_anterior + variacao,
        registrada_por=autor,
        registrada_em=timezone.now(),
        item_entrada=item,
        estorno_entrada=None,
    )


# ---------------------------------------------------------------------------
# Entrada: listas fechadas, número, emitente por motivo (FR-006, FR-007)
# ---------------------------------------------------------------------------


def test_motivo_fora_da_lista_e_rejeitado_pelo_banco(funcionario_almoxarifado):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _criar_entrada(funcionario_almoxarifado, motivo="MOTIVO_INEXISTENTE")


def test_tipo_documento_fora_da_lista_e_rejeitado_pelo_banco(funcionario_almoxarifado):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _criar_entrada(funcionario_almoxarifado, tipo_documento="TIPO_INEXISTENTE")


def test_numero_documento_so_espacos_e_rejeitado_pelo_banco(funcionario_almoxarifado):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _criar_entrada(funcionario_almoxarifado, numero_documento="   ")


@pytest.mark.parametrize(
    "motivo",
    [MotivoEntrada.COMPRA, MotivoEntrada.DEVOLUCAO_FORNECEDOR_GARANTIA],
)
def test_emitente_ausente_e_rejeitado_pelo_banco_nos_motivos_que_exigem(
    funcionario_almoxarifado, motivo
):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _criar_entrada(funcionario_almoxarifado, motivo=motivo, emitente=None)


@pytest.mark.parametrize(
    "motivo",
    [MotivoEntrada.DOACAO_RECEBIDA, MotivoEntrada.EMPRESTIMO_DEVOLVIDO],
)
def test_emitente_ausente_e_aceito_nos_motivos_em_que_e_opcional(
    funcionario_almoxarifado, motivo
):
    entrada = _criar_entrada(funcionario_almoxarifado, motivo=motivo, emitente=None)

    assert Entrada.objects.get(pk=entrada.pk).emitente_id is None


def test_emitente_presente_e_aceito_em_compra(funcionario_almoxarifado, criar_fornecedor):
    fornecedor = criar_fornecedor("1001", "Fornecedor Teste")

    entrada = _criar_entrada(
        funcionario_almoxarifado, motivo=MotivoEntrada.COMPRA, emitente=fornecedor
    )

    assert Entrada.objects.get(pk=entrada.pk).emitente_id == fornecedor.pk


def test_chave_confirmacao_duplicada_e_rejeitada_pelo_banco(funcionario_almoxarifado):
    chave = uuid.uuid4()
    _criar_entrada(funcionario_almoxarifado, chave_confirmacao=chave)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _criar_entrada(funcionario_almoxarifado, chave_confirmacao=chave)


# ---------------------------------------------------------------------------
# Referência única entre entradas não estornadas (FR-007a) —
# UniqueConstraint(nulls_distinct=False)
# ---------------------------------------------------------------------------


def test_referencia_repetida_entre_entradas_nao_estornadas_e_rejeitada(
    funcionario_almoxarifado, criar_fornecedor
):
    fornecedor = criar_fornecedor("1002", "Fornecedor A")
    _criar_entrada(
        funcionario_almoxarifado,
        motivo=MotivoEntrada.COMPRA,
        numero_documento="NF-9999",
        emitente=fornecedor,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _criar_entrada(
                funcionario_almoxarifado,
                motivo=MotivoEntrada.COMPRA,
                numero_documento="NF-9999",
                emitente=fornecedor,
            )


def test_referencia_repetida_ambas_sem_emitente_conta_como_a_mesma_referencia(
    funcionario_almoxarifado,
):
    """`nulls_distinct=False`: duas entradas sem emitente, mesmo tipo e
    número, são a MESMA referência para fins de unicidade (FR-007a) — o
    padrão SQL default trataria `NULL <> NULL` e deixaria passar."""
    _criar_entrada(
        funcionario_almoxarifado,
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        numero_documento="TD-0001",
        emitente=None,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _criar_entrada(
                funcionario_almoxarifado,
                motivo=MotivoEntrada.DOACAO_RECEBIDA,
                numero_documento="TD-0001",
                emitente=None,
            )


def test_mesma_referencia_e_aceita_depois_que_a_entrada_original_foi_estornada(
    funcionario_almoxarifado, criar_fornecedor
):
    fornecedor = criar_fornecedor("1003", "Fornecedor B")
    original = _criar_entrada(
        funcionario_almoxarifado,
        motivo=MotivoEntrada.COMPRA,
        numero_documento="NF-1111",
        emitente=fornecedor,
    )
    # Marca como estornada por escrita direta (não é o fluxo real de
    # `estornar_entrada`, mas o suficiente para exercitar
    # `condition=Q(estornada=False)` do índice único, isoladamente).
    Entrada.objects.filter(pk=original.pk).update(estornada=True)

    nova = _criar_entrada(
        funcionario_almoxarifado,
        motivo=MotivoEntrada.COMPRA,
        numero_documento="NF-1111",
        emitente=fornecedor,
    )

    assert nova.pk != original.pk


def test_mesmo_numero_com_emitentes_diferentes_e_aceito(funcionario_almoxarifado, criar_fornecedor):
    fornecedor_a = criar_fornecedor("1004", "Fornecedor C")
    fornecedor_b = criar_fornecedor("1005", "Fornecedor D")
    _criar_entrada(
        funcionario_almoxarifado,
        motivo=MotivoEntrada.COMPRA,
        numero_documento="NF-2222",
        emitente=fornecedor_a,
    )

    outra = _criar_entrada(
        funcionario_almoxarifado,
        motivo=MotivoEntrada.COMPRA,
        numero_documento="NF-2222",
        emitente=fornecedor_b,
    )

    assert Entrada.objects.filter(numero_documento="NF-2222").count() == 2
    assert outra.emitente_id == fornecedor_b.pk


# ---------------------------------------------------------------------------
# ItemEntrada (FR-004, FR-005)
# ---------------------------------------------------------------------------


def test_quantidade_zero_ou_negativa_e_rejeitada_pelo_banco(
    funcionario_almoxarifado, criar_material
):
    entrada = _criar_entrada(funcionario_almoxarifado)
    material = criar_material("111.111.111", Decimal("10.000"))

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _criar_item(entrada, material, quantidade=Decimal("0.000"))

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _criar_item(entrada, material, quantidade=Decimal("-1.000"))


def test_material_repetido_na_mesma_entrada_e_rejeitado_pelo_banco(
    funcionario_almoxarifado, criar_material
):
    entrada = _criar_entrada(funcionario_almoxarifado)
    material = criar_material("111.111.112", Decimal("10.000"))
    _criar_item(entrada, material)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _criar_item(entrada, material, quantidade=Decimal("1.000"))


# ---------------------------------------------------------------------------
# EstornoEntrada (FR-024, FR-027, INV-ENT-001)
# ---------------------------------------------------------------------------


def test_justificativa_vazia_ou_so_espacos_e_rejeitada_pelo_banco(
    funcionario_almoxarifado, chefe_almoxarifado
):
    entrada = _criar_entrada(funcionario_almoxarifado)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EstornoEntrada.objects.create(
                entrada=entrada,
                justificativa="   ",
                estornada_por=chefe_almoxarifado,
                estornada_em=timezone.now(),
            )


def test_segundo_estorno_da_mesma_entrada_e_rejeitado_pelo_banco(
    funcionario_almoxarifado, chefe_almoxarifado
):
    """`INV-ENT-001`: `OneToOneField` garante no máximo um estorno por
    entrada também em persistência, não só pela regra de `estornar_entrada`."""
    entrada = _criar_entrada(funcionario_almoxarifado, estornada=True)
    EstornoEntrada.objects.create(
        entrada=entrada,
        justificativa="Erro de digitação na quantidade.",
        estornada_por=chefe_almoxarifado,
        estornada_em=timezone.now(),
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EstornoEntrada.objects.create(
                entrada=entrada,
                justificativa="Segunda tentativa.",
                estornada_por=chefe_almoxarifado,
                estornada_em=timezone.now(),
            )


# ---------------------------------------------------------------------------
# MovimentacaoEstoque: sinal, saldos, origem por tipo (research R2)
# ---------------------------------------------------------------------------


def test_variacao_zero_e_rejeitada_pelo_banco(funcionario_almoxarifado, criar_material):
    entrada = _criar_entrada(funcionario_almoxarifado)
    material = criar_material("111.111.113", Decimal("10.000"))
    item = _criar_item(entrada, material)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            MovimentacaoEstoque.objects.create(
                material=material,
                tipo=TipoMovimentacao.ENTRADA,
                variacao=Decimal("0.000"),
                saldo_anterior=Decimal("10.000"),
                saldo_posterior=Decimal("10.000"),
                registrada_por=funcionario_almoxarifado,
                registrada_em=timezone.now(),
                item_entrada=item,
            )


def test_saldo_posterior_inconsistente_com_saldo_anterior_mais_variacao_e_rejeitado(
    funcionario_almoxarifado, criar_material
):
    entrada = _criar_entrada(funcionario_almoxarifado)
    material = criar_material("111.111.114", Decimal("10.000"))
    item = _criar_item(entrada, material)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            MovimentacaoEstoque.objects.create(
                material=material,
                tipo=TipoMovimentacao.ENTRADA,
                variacao=Decimal("5.000"),
                saldo_anterior=Decimal("10.000"),
                saldo_posterior=Decimal("16.000"),  # deveria ser 15.000
                registrada_por=funcionario_almoxarifado,
                registrada_em=timezone.now(),
                item_entrada=item,
            )


def test_saldo_posterior_negativo_e_rejeitado_pelo_banco(funcionario_almoxarifado, criar_material):
    """`INV-STOCK-001` também garantida na própria movimentação, não só em
    `Material.saldo`."""
    entrada = _criar_entrada(funcionario_almoxarifado)
    material = criar_material("111.111.115", Decimal("10.000"))
    item = _criar_item(entrada, material, quantidade=Decimal("15.000"))

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            MovimentacaoEstoque.objects.create(
                material=material,
                tipo=TipoMovimentacao.ESTORNO_ENTRADA,
                variacao=Decimal("-15.000"),
                saldo_anterior=Decimal("10.000"),
                saldo_posterior=Decimal("-5.000"),
                registrada_por=funcionario_almoxarifado,
                registrada_em=timezone.now(),
                item_entrada=item,
                estorno_entrada=None,  # já viola a origem, mas o saldo é o alvo deste teste
            )


@pytest.mark.parametrize(
    "kwargs, descricao",
    [
        pytest.param(
            {"tipo": TipoMovimentacao.ENTRADA, "variacao": Decimal("5.000"), "com_estorno": True},
            "entrada_com_estorno_entrada_preenchido",
            id="entrada_com_estorno_entrada_preenchido",
        ),
        pytest.param(
            {"tipo": TipoMovimentacao.ENTRADA, "variacao": Decimal("-5.000"), "com_estorno": False},
            "entrada_com_variacao_negativa",
            id="entrada_com_variacao_negativa",
        ),
        pytest.param(
            {
                "tipo": TipoMovimentacao.ESTORNO_ENTRADA,
                "variacao": Decimal("-5.000"),
                "com_estorno": False,
            },
            "estorno_sem_estorno_entrada_preenchido",
            id="estorno_sem_estorno_entrada_preenchido",
        ),
        pytest.param(
            {
                "tipo": TipoMovimentacao.ESTORNO_ENTRADA,
                "variacao": Decimal("5.000"),
                "com_estorno": True,
            },
            "estorno_com_variacao_positiva",
            id="estorno_com_variacao_positiva",
        ),
    ],
)
def test_origem_incoerente_com_o_tipo_e_rejeitada_pelo_banco(
    funcionario_almoxarifado, chefe_almoxarifado, criar_material, kwargs, descricao
):
    entrada = _criar_entrada(funcionario_almoxarifado, estornada=True)
    material = criar_material(f"111.112.{abs(hash(descricao)) % 1000:03d}", Decimal("10.000"))
    item = _criar_item(entrada, material)
    estorno = EstornoEntrada.objects.create(
        entrada=entrada,
        justificativa="Erro de digitação.",
        estornada_por=chefe_almoxarifado,
        estornada_em=timezone.now(),
    )

    saldo_anterior = Decimal("10.000")
    variacao = kwargs["variacao"]
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            MovimentacaoEstoque.objects.create(
                material=material,
                tipo=kwargs["tipo"],
                variacao=variacao,
                saldo_anterior=saldo_anterior,
                saldo_posterior=saldo_anterior + variacao,
                registrada_por=funcionario_almoxarifado,
                registrada_em=timezone.now(),
                item_entrada=item,
                estorno_entrada=estorno if kwargs["com_estorno"] else None,
            )


def test_duas_movimentacoes_do_mesmo_tipo_para_o_mesmo_item_e_rejeitado(
    funcionario_almoxarifado, criar_material
):
    """`UNIQUE (item_entrada, tipo)`: no máximo uma movimentação `ENTRADA`
    por item (SC-002)."""
    entrada = _criar_entrada(funcionario_almoxarifado)
    material = criar_material("111.111.116", Decimal("10.000"))
    item = _criar_item(entrada, material, quantidade=Decimal("5.000"))
    _criar_movimentacao_entrada(
        item, funcionario_almoxarifado, saldo_anterior=Decimal("10.000"), variacao=Decimal("5.000")
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _criar_movimentacao_entrada(
                item,
                funcionario_almoxarifado,
                saldo_anterior=Decimal("15.000"),
                variacao=Decimal("5.000"),
            )


# ---------------------------------------------------------------------------
# Preservação histórica: PROTECT em toda FK (Constitution IV)
# ---------------------------------------------------------------------------


def test_entrada_referenciada_por_item_nao_pode_ser_excluida_pelo_orm(
    funcionario_almoxarifado, criar_material
):
    entrada = _criar_entrada(funcionario_almoxarifado)
    material = criar_material("111.111.117", Decimal("10.000"))
    _criar_item(entrada, material)

    with pytest.raises(ProtectedError):
        entrada.delete()

    assert Entrada.objects.filter(pk=entrada.pk).exists()


# ---------------------------------------------------------------------------
# Imutabilidade garantida pelo BANCO (research R7, INV-MOV-001) — testada com
# `QuerySet.update()`/`.delete()`, que contornam qualquer validação em
# `save()`/`delete()` do Python, e por isso são exatamente o caminho que o
# trigger precisa fechar. `django.db.Error` é a base comum de qualquer erro
# de banco (não amarra o teste a uma subclasse específica de SQLSTATE).
# ---------------------------------------------------------------------------


def test_update_de_item_entrada_e_rejeitado_pelo_trigger(funcionario_almoxarifado, criar_material):
    entrada = _criar_entrada(funcionario_almoxarifado)
    material = criar_material("111.111.118", Decimal("10.000"))
    item = _criar_item(entrada, material, quantidade=Decimal("5.000"))

    with pytest.raises(Error):
        with transaction.atomic():
            ItemEntrada.objects.filter(pk=item.pk).update(quantidade=Decimal("6.000"))

    assert ItemEntrada.objects.get(pk=item.pk).quantidade == Decimal("5.000")


def test_delete_de_item_entrada_e_rejeitado_pelo_trigger(funcionario_almoxarifado, criar_material):
    entrada = _criar_entrada(funcionario_almoxarifado)
    material = criar_material("111.111.119", Decimal("10.000"))
    item = _criar_item(entrada, material)

    with pytest.raises(Error):
        with transaction.atomic():
            ItemEntrada.objects.filter(pk=item.pk).delete()

    assert ItemEntrada.objects.filter(pk=item.pk).exists()


def test_update_de_estorno_entrada_e_rejeitado_pelo_trigger(
    funcionario_almoxarifado, chefe_almoxarifado
):
    entrada = _criar_entrada(funcionario_almoxarifado, estornada=True)
    estorno = EstornoEntrada.objects.create(
        entrada=entrada,
        justificativa="Justificativa original.",
        estornada_por=chefe_almoxarifado,
        estornada_em=timezone.now(),
    )

    with pytest.raises(Error):
        with transaction.atomic():
            EstornoEntrada.objects.filter(pk=estorno.pk).update(justificativa="Outra.")

    assert EstornoEntrada.objects.get(pk=estorno.pk).justificativa == "Justificativa original."


def test_delete_de_estorno_entrada_e_rejeitado_pelo_trigger(
    funcionario_almoxarifado, chefe_almoxarifado
):
    entrada = _criar_entrada(funcionario_almoxarifado, estornada=True)
    estorno = EstornoEntrada.objects.create(
        entrada=entrada,
        justificativa="Justificativa original.",
        estornada_por=chefe_almoxarifado,
        estornada_em=timezone.now(),
    )

    with pytest.raises(Error):
        with transaction.atomic():
            EstornoEntrada.objects.filter(pk=estorno.pk).delete()

    assert EstornoEntrada.objects.filter(pk=estorno.pk).exists()


def test_update_de_movimentacao_estoque_e_rejeitado_pelo_trigger(
    funcionario_almoxarifado, criar_material
):
    entrada = _criar_entrada(funcionario_almoxarifado)
    material = criar_material("111.111.120", Decimal("10.000"))
    item = _criar_item(entrada, material, quantidade=Decimal("5.000"))
    movimentacao = _criar_movimentacao_entrada(
        item, funcionario_almoxarifado, saldo_anterior=Decimal("10.000"), variacao=Decimal("5.000")
    )

    with pytest.raises(Error):
        with transaction.atomic():
            MovimentacaoEstoque.objects.filter(pk=movimentacao.pk).update(
                variacao=Decimal("6.000")
            )

    assert MovimentacaoEstoque.objects.get(pk=movimentacao.pk).variacao == Decimal("5.000")


def test_delete_de_movimentacao_estoque_e_rejeitado_pelo_trigger(
    funcionario_almoxarifado, criar_material
):
    entrada = _criar_entrada(funcionario_almoxarifado)
    material = criar_material("111.111.121", Decimal("10.000"))
    item = _criar_item(entrada, material, quantidade=Decimal("5.000"))
    movimentacao = _criar_movimentacao_entrada(
        item, funcionario_almoxarifado, saldo_anterior=Decimal("10.000"), variacao=Decimal("5.000")
    )

    with pytest.raises(Error):
        with transaction.atomic():
            MovimentacaoEstoque.objects.filter(pk=movimentacao.pk).delete()

    assert MovimentacaoEstoque.objects.filter(pk=movimentacao.pk).exists()


def test_delete_de_entrada_sem_itens_e_rejeitado_pelo_trigger(funcionario_almoxarifado):
    """Entrada sem nenhum item relacionado: nada de `PROTECT` do lado do ORM
    impediria a exclusão — só o trigger do banco. Prova que o trigger é uma
    defesa própria, não uma reafirmação do `on_delete=PROTECT` já testado
    acima."""
    entrada = _criar_entrada(funcionario_almoxarifado)

    with pytest.raises(Error):
        with transaction.atomic():
            Entrada.objects.filter(pk=entrada.pk).delete()

    assert Entrada.objects.filter(pk=entrada.pk).exists()


def test_update_de_numero_documento_da_entrada_e_rejeitado_pelo_trigger(funcionario_almoxarifado):
    entrada = _criar_entrada(funcionario_almoxarifado, numero_documento="NF-ORIGINAL")

    with pytest.raises(Error):
        with transaction.atomic():
            Entrada.objects.filter(pk=entrada.pk).update(numero_documento="NF-ALTERADO")

    assert Entrada.objects.get(pk=entrada.pk).numero_documento == "NF-ORIGINAL"


def test_save_da_entrada_reescrevendo_todos_os_campos_e_rejeitado_pelo_trigger(
    funcionario_almoxarifado,
):
    """`entrada.save()` sem `update_fields` reescreve a linha inteira — se o
    número do documento também mudou (mesmo que só na instância em memória),
    o trigger tem que recusar, não só o `.update()` de queryset."""
    entrada = _criar_entrada(funcionario_almoxarifado, numero_documento="NF-ORIGINAL")
    entrada.numero_documento = "NF-ALTERADO"

    with pytest.raises(Error):
        with transaction.atomic():
            entrada.save()

    assert Entrada.objects.get(pk=entrada.pk).numero_documento == "NF-ORIGINAL"


def test_update_de_estornada_de_true_para_false_e_rejeitado_pelo_trigger(
    funcionario_almoxarifado,
):
    entrada = _criar_entrada(funcionario_almoxarifado, estornada=True)

    with pytest.raises(Error):
        with transaction.atomic():
            Entrada.objects.filter(pk=entrada.pk).update(estornada=False)

    assert Entrada.objects.get(pk=entrada.pk).estornada is True


def test_update_combinando_estornada_com_outro_campo_e_rejeitado_pelo_trigger(
    funcionario_almoxarifado,
):
    """A única mudança tolerada é `estornada` de `false` para `true` — SE
    outro campo muda junto (mesmo dentro do mesmo `UPDATE`), o trigger
    recusa a linha inteira."""
    entrada = _criar_entrada(funcionario_almoxarifado, numero_documento="NF-ORIGINAL")

    with pytest.raises(Error):
        with transaction.atomic():
            Entrada.objects.filter(pk=entrada.pk).update(
                estornada=True, numero_documento="NF-ALTERADO"
            )

    recarregada = Entrada.objects.get(pk=entrada.pk)
    assert recarregada.estornada is False
    assert recarregada.numero_documento == "NF-ORIGINAL"


def test_update_de_estornada_de_false_para_true_e_aceito_pelo_trigger(funcionario_almoxarifado):
    """A única transição de `Entrada` que o trigger permite (research R7) —
    o próprio mecanismo de `estornar_entrada`."""
    entrada = _criar_entrada(funcionario_almoxarifado, estornada=False)

    Entrada.objects.filter(pk=entrada.pk).update(estornada=True)

    assert Entrada.objects.get(pk=entrada.pk).estornada is True


# ---------------------------------------------------------------------------
# Idempotência do handler de post_migrate (research R7): pode rodar duas
# vezes seguidas sem erro (`CREATE OR REPLACE FUNCTION`, `DROP TRIGGER IF
# EXISTS` antes de `CREATE TRIGGER`) — o `flush` dos testes transacionais
# reemite `post_migrate`.
# ---------------------------------------------------------------------------


def test_handler_de_triggers_e_idempotente():
    from estoque.apps import criar_triggers_imutabilidade

    criar_triggers_imutabilidade(using=DEFAULT_DB_ALIAS)
    criar_triggers_imutabilidade(using=DEFAULT_DB_ALIAS)  # não deveria levantar nada


# ---------------------------------------------------------------------------
# Nenhum modelo de estoque no admin (parte de SC-008; ver também
# tests/test_estoque_sem_alteracao.py, T031, para a checagem mais ampla)
# ---------------------------------------------------------------------------


def test_nenhum_modelo_de_estoque_esta_registrado_no_admin():
    modelos = {Entrada, ItemEntrada, EstornoEntrada, MovimentacaoEstoque}
    registrados = set(admin.site._registry.keys())

    assert not (modelos & registrados), (
        f"modelo(s) de estoque registrados indevidamente no admin: {modelos & registrados}"
    )
