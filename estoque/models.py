from django.db import models
from django.db.models import F, Q, Value
from django.db.models.functions import Trim
from django.db.models.lookups import GreaterThan


class MotivoEntrada(models.TextChoices):
    """Motivos de entrada aceitos (`data-model.md` → Listas fechadas, FR-006)."""

    COMPRA = "COMPRA", "Compra"
    DOACAO_RECEBIDA = "DOACAO_RECEBIDA", "Doação recebida"
    DEVOLUCAO_FORNECEDOR_GARANTIA = (
        "DEVOLUCAO_FORNECEDOR_GARANTIA",
        "Devolução de fornecedor/garantia",
    )
    EMPRESTIMO_DEVOLVIDO = "EMPRESTIMO_DEVOLVIDO", "Empréstimo devolvido"


# Motivos para os quais o emitente é opcional (`data-model.md` → Entrada,
# `CHECK estoque_entrada_emitente_por_motivo`).
MOTIVOS_SEM_EMITENTE_OBRIGATORIO = (
    MotivoEntrada.DOACAO_RECEBIDA,
    MotivoEntrada.EMPRESTIMO_DEVOLVIDO,
)


class TipoDocumentoEntrada(models.TextChoices):
    """Tipos de documento de referência aceitos (FR-007), independentes do
    motivo."""

    NOTA_FISCAL = "NOTA_FISCAL", "Nota fiscal"
    TERMO_DOACAO = "TERMO_DOACAO", "Termo de doação"
    TERMO_RECIBO_DEVOLUCAO = "TERMO_RECIBO_DEVOLUCAO", "Termo/recibo de devolução"


class TipoMovimentacao(models.TextChoices):
    """Tipos de movimentação de estoque.

    Lista de código extensível pelas próximas operações (`SAE`, `ATE`, `DEV`,
    `INV`), não um vocabulário de domínio fechado (research R2)."""

    ENTRADA = "ENTRADA", "Entrada"
    ESTORNO_ENTRADA = "ESTORNO_ENTRADA", "Estorno de entrada"


class Entrada(models.Model):
    """Entrada de materiais recebidos pelo almoxarifado (`data-model.md` →
    Entrada).

    Sem rota de edição, sem admin. A única mudança aceita depois de
    registrada é `estornada` de `False` para `True`, junto de um
    `EstornoEntrada` (`INV-ENT-001`). Um trigger de banco
    (`estoque.apps.criar_triggers_imutabilidade`) recusa qualquer `DELETE` e
    qualquer outro `UPDATE` (`INV-MOV-001`).
    """

    chave_confirmacao = models.UUIDField(unique=True, editable=False)
    motivo = models.CharField(choices=MotivoEntrada.choices)
    tipo_documento = models.CharField(choices=TipoDocumentoEntrada.choices)
    numero_documento = models.TextField()
    emitente = models.ForeignKey(
        "fornecedores.Fornecedor",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="entradas",
    )
    registrada_por = models.ForeignKey(
        "contas.User",
        on_delete=models.PROTECT,
        related_name="entradas_registradas",
    )
    registrada_em = models.DateTimeField(editable=False)
    estornada = models.BooleanField(default=False)

    class Meta:
        ordering = ["-registrada_em", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(motivo__in=MotivoEntrada.values),
                name="estoque_entrada_motivo_valido",
            ),
            models.CheckConstraint(
                condition=Q(tipo_documento__in=TipoDocumentoEntrada.values),
                name="estoque_entrada_tipo_documento_valido",
            ),
            models.CheckConstraint(
                condition=GreaterThan(Trim(F("numero_documento")), Value("")),
                name="estoque_entrada_numero_documento_nao_vazio",
            ),
            models.CheckConstraint(
                condition=Q(emitente__isnull=False)
                | Q(motivo__in=MOTIVOS_SEM_EMITENTE_OBRIGATORIO),
                name="estoque_entrada_emitente_por_motivo",
            ),
            models.UniqueConstraint(
                fields=["tipo_documento", "numero_documento", "emitente"],
                condition=Q(estornada=False),
                nulls_distinct=False,
                name="estoque_entrada_referencia_unica",
            ),
        ]

    def __str__(self):
        return f"Entrada {self.pk} — {self.tipo_documento} {self.numero_documento}"


class ItemEntrada(models.Model):
    """Item (material e quantidade) de uma `Entrada` (`data-model.md` →
    ItemEntrada). Nem `UPDATE` nem `DELETE` são aceitos depois de gravado
    (trigger de imutabilidade)."""

    entrada = models.ForeignKey(
        "estoque.Entrada",
        on_delete=models.PROTECT,
        related_name="itens",
    )
    material = models.ForeignKey(
        "catalogo.Material",
        on_delete=models.PROTECT,
    )
    quantidade = models.DecimalField(max_digits=15, decimal_places=3)

    class Meta:
        ordering = ["material__cadpro"]
        constraints = [
            models.UniqueConstraint(
                fields=["entrada", "material"],
                name="estoque_item_entrada_material_unico",
            ),
            models.CheckConstraint(
                condition=Q(quantidade__gt=0),
                name="estoque_item_entrada_quantidade_positiva",
            ),
        ]

    def __str__(self):
        return f"Item {self.material_id} — entrada {self.entrada_id}"


class EstornoEntrada(models.Model):
    """Estorno total de uma `Entrada` (`data-model.md` → EstornoEntrada,
    FR-022 a FR-028). Sempre total, sem itens próprios: cada `ItemEntrada` da
    entrada original gera uma `MovimentacaoEstoque` de estorno na quantidade
    integral. Nem `UPDATE` nem `DELETE` são aceitos depois de gravado."""

    entrada = models.OneToOneField(
        "estoque.Entrada",
        on_delete=models.PROTECT,
        related_name="estorno",
    )
    justificativa = models.TextField()
    estornada_por = models.ForeignKey(
        "contas.User",
        on_delete=models.PROTECT,
        related_name="estornos_entrada",
    )
    estornada_em = models.DateTimeField(editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=GreaterThan(Trim(F("justificativa")), Value("")),
                name="estoque_estorno_justificativa_nao_vazia",
            ),
        ]

    def __str__(self):
        return f"Estorno da entrada {self.entrada_id}"


class MovimentacaoEstoque(models.Model):
    """Fato transversal de variação de saldo (`data-model.md` →
    MovimentacaoEstoque, research R2), que as próximas operações de estoque
    também vão gerar. A origem é uma FK anulável por tipo de operação; hoje
    `item_entrada` e `estorno_entrada`. Nem `UPDATE` nem `DELETE` são
    aceitos depois de gravado (`INV-MOV-001`)."""

    material = models.ForeignKey(
        "catalogo.Material",
        on_delete=models.PROTECT,
        related_name="movimentacoes",
    )
    tipo = models.CharField(choices=TipoMovimentacao.choices)
    variacao = models.DecimalField(max_digits=16, decimal_places=3)
    saldo_anterior = models.DecimalField(max_digits=15, decimal_places=3)
    saldo_posterior = models.DecimalField(max_digits=15, decimal_places=3)
    registrada_por = models.ForeignKey(
        "contas.User",
        on_delete=models.PROTECT,
        related_name="movimentacoes_estoque",
    )
    registrada_em = models.DateTimeField(editable=False)
    item_entrada = models.ForeignKey(
        "estoque.ItemEntrada",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movimentacoes",
    )
    estorno_entrada = models.ForeignKey(
        "estoque.EstornoEntrada",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movimentacoes",
    )

    class Meta:
        ordering = ["-registrada_em", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(tipo__in=TipoMovimentacao.values),
                name="estoque_mov_tipo_valido",
            ),
            models.CheckConstraint(
                condition=~Q(variacao=0),
                name="estoque_mov_variacao_nao_zero",
            ),
            models.CheckConstraint(
                condition=Q(saldo_posterior=F("saldo_anterior") + F("variacao")),
                name="estoque_mov_saldo_posterior_calculo",
            ),
            models.CheckConstraint(
                condition=Q(saldo_posterior__gte=0),
                name="estoque_mov_saldo_posterior_nao_negativo",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        tipo=TipoMovimentacao.ENTRADA,
                        item_entrada__isnull=False,
                        estorno_entrada__isnull=True,
                        variacao__gt=0,
                    )
                    | Q(
                        tipo=TipoMovimentacao.ESTORNO_ENTRADA,
                        item_entrada__isnull=False,
                        estorno_entrada__isnull=False,
                        variacao__lt=0,
                    )
                ),
                name="estoque_mov_origem_por_tipo",
            ),
            models.UniqueConstraint(
                fields=["item_entrada", "tipo"],
                name="estoque_mov_item_tipo_unico",
            ),
        ]
        indexes = [
            models.Index(
                fields=["material", "-registrada_em"],
                name="estoque_mov_material_data",
            ),
        ]

    def __str__(self):
        return f"Movimentação {self.tipo} — material {self.material_id}"
