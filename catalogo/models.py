from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import F, Q


class Material(models.Model):
    """Item do catálogo oficial do SCPI (`data-model.md` → Material).

    Somente-inserção do ponto de vista da aplicação, exceto os campos
    cadastrais listados em `CAMPOS_CADASTRAIS_ATUALIZAVEIS`, que só mudam por
    reimportação (`INV-CATALOG-004`). Nenhuma view ou método deste módulo cria,
    edita ou exclui `Material` fora de `catalogo.importacao` (FR-006, SC-005,
    `INV-CATALOG-003`).
    """

    cadpro = models.CharField(max_length=11, editable=False)
    descricao = models.TextField()
    descricao_busca = models.TextField()
    unidade = models.TextField()
    detalhamento = models.TextField(blank=True)
    grupo = models.TextField(blank=True)
    subgrupo = models.TextField(blank=True)
    nome_grupo = models.TextField(blank=True)
    nome_subgrupo = models.TextField(blank=True)
    saldo = models.DecimalField(max_digits=15, decimal_places=3)
    saldo_inicial = models.DecimalField(max_digits=15, decimal_places=3, editable=False)
    execucao_origem = models.ForeignKey(
        "catalogo.ExecucaoImportacao",
        on_delete=models.PROTECT,
        editable=False,
    )

    class Meta:
        ordering = ["cadpro"]
        constraints = [
            models.UniqueConstraint(
                fields=["cadpro"],
                name="catalogo_material_cadpro_unico",
            ),
            models.CheckConstraint(
                condition=Q(cadpro__regex=r"^[0-9]{3}\.[0-9]{3}\.[0-9]{3}$"),
                name="catalogo_material_cadpro_formato",
            ),
            models.CheckConstraint(
                condition=Q(saldo__gte=0),
                name="catalogo_material_saldo_nao_negativo",
            ),
            models.CheckConstraint(
                condition=Q(saldo_inicial__gte=0),
                name="catalogo_material_saldo_inicial_nao_negativo",
            ),
        ]
        indexes = [
            GinIndex(
                fields=["descricao_busca"],
                opclasses=["gin_trgm_ops"],
                name="catalogo_material_busca_gin",
            ),
        ]

    def __str__(self):
        return self.cadpro


# Lista fechada dos campos cadastrais atualizáveis por reimportação (FR-026,
# `INV-CATALOG-004`). `descricao_busca` é derivado e reescrito junto de
# `descricao`, mas não é um campo do arquivo por si só — por isso não integra
# esta lista (ver `CampoCadastral`, que espelha exatamente estes 7 campos).
CAMPOS_CADASTRAIS_ATUALIZAVEIS = (
    "descricao",
    "unidade",
    "detalhamento",
    "grupo",
    "subgrupo",
    "nome_grupo",
    "nome_subgrupo",
)


class MotivoRecusa(models.TextChoices):
    """Motivos de recusa de registro na importação (`research.md` R5)."""

    LINHA_NAO_ASSOCIAVEL = "LINHA_NAO_ASSOCIAVEL", "Linha não associável a nenhum registro"
    ESTRUTURA_INCONSISTENTE = "ESTRUTURA_INCONSISTENTE", "Estrutura do registro inconsistente"
    CADPRO_AUSENTE = "CADPRO_AUSENTE", "Código (CADPRO) ausente"
    CADPRO_FORMATO_INVALIDO = "CADPRO_FORMATO_INVALIDO", "Código (CADPRO) em formato inválido"
    CADPRO_DUPLICADO_NO_ARQUIVO = (
        "CADPRO_DUPLICADO_NO_ARQUIVO",
        "Código (CADPRO) duplicado no arquivo",
    )
    DESCRICAO_AUSENTE = "DESCRICAO_AUSENTE", "Descrição ausente"
    UNIDADE_AUSENTE = "UNIDADE_AUSENTE", "Unidade ausente"
    QUANTIDADE_AUSENTE = "QUANTIDADE_AUSENTE", "Quantidade ausente"
    QUANTIDADE_NAO_NUMERICA = "QUANTIDADE_NAO_NUMERICA", "Quantidade não numérica"
    QUANTIDADE_NEGATIVA = "QUANTIDADE_NEGATIVA", "Quantidade negativa"
    QUANTIDADE_FORA_DO_LIMITE = "QUANTIDADE_FORA_DO_LIMITE", "Quantidade fora do limite de dígitos"


class ExecucaoImportacao(models.Model):
    """Uma importação CONFIRMADA do catálogo (FR-033, FR-037).

    Prévias não confirmadas não geram execução — nascem e vivem só na sessão
    do usuário (`catalogo.importacao`, R8).
    """

    token_previa = models.UUIDField(unique=True)
    executada_por = models.ForeignKey(
        "contas.User",
        on_delete=models.PROTECT,
    )
    concluida_em = models.DateTimeField()
    nome_arquivo = models.CharField(max_length=255)
    tamanho_arquivo = models.PositiveBigIntegerField()
    sha256_arquivo = models.CharField(max_length=64)
    total_recebidos = models.PositiveIntegerField()
    total_inseridos = models.PositiveIntegerField()
    total_atualizados = models.PositiveIntegerField()
    total_atualizados_com_alteracao = models.PositiveIntegerField()
    total_rejeitados = models.PositiveIntegerField()
    total_divergencias = models.PositiveIntegerField()
    total_ausentes_no_arquivo = models.PositiveIntegerField()

    class Meta:
        ordering = ["-concluida_em"]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    total_recebidos=F("total_inseridos")
                    + F("total_atualizados")
                    + F("total_rejeitados")
                ),
                name="catalogo_execucaoimportacao_totais_ok",
            ),
            models.CheckConstraint(
                condition=Q(total_atualizados_com_alteracao__lte=F("total_atualizados")),
                name="catalogo_execucaoimportacao_atualizados_alteracao_max",
            ),
        ]

    def __str__(self):
        return f"Importação {self.pk} — {self.nome_arquivo}"


class ExcecaoImportacao(models.Model):
    """Registro recusado dentro de uma execução (FR-036)."""

    execucao = models.ForeignKey(
        "catalogo.ExecucaoImportacao",
        on_delete=models.PROTECT,
        related_name="excecoes",
    )
    linha_inicial = models.PositiveIntegerField()
    linha_final = models.PositiveIntegerField()
    cadpro = models.TextField(blank=True)
    motivo = models.CharField(choices=MotivoRecusa.choices)
    detalhe = models.TextField(blank=True)

    class Meta:
        ordering = ["linha_inicial"]
        constraints = [
            models.CheckConstraint(
                condition=Q(linha_final__gte=F("linha_inicial")),
                name="catalogo_excecaoimportacao_linha_final_gte_inicial",
            ),
        ]

    def __str__(self):
        return f"Exceção linhas {self.linha_inicial}-{self.linha_final} — {self.motivo}"


class CampoCadastral(models.TextChoices):
    """Os 7 campos cadastrais atualizáveis por reimportação — espelha
    `CAMPOS_CADASTRAIS_ATUALIZAVEIS` (não inclui `descricao_busca`, que é
    derivado)."""

    DESCRICAO = "descricao", "Descrição"
    UNIDADE = "unidade", "Unidade"
    DETALHAMENTO = "detalhamento", "Detalhamento"
    GRUPO = "grupo", "Grupo"
    SUBGRUPO = "subgrupo", "Subgrupo"
    NOME_GRUPO = "nome_grupo", "Nome do grupo"
    NOME_SUBGRUPO = "nome_subgrupo", "Nome do subgrupo"


class DivergenciaSaldo(models.Model):
    """Diferença informativa entre o saldo do arquivo e o saldo do WMS
    (FR-029, FR-030, `INV-STOCK-003`). Nunca altera saldo."""

    execucao = models.ForeignKey(
        "catalogo.ExecucaoImportacao",
        on_delete=models.PROTECT,
        related_name="divergencias",
    )
    material = models.ForeignKey(
        "catalogo.Material",
        on_delete=models.PROTECT,
    )
    saldo_wms = models.DecimalField(max_digits=15, decimal_places=3)
    saldo_arquivo = models.DecimalField(max_digits=15, decimal_places=3)
    diferenca = models.DecimalField(max_digits=16, decimal_places=3)

    class Meta:
        ordering = ["material__cadpro"]
        constraints = [
            models.UniqueConstraint(
                fields=["execucao", "material"],
                name="catalogo_divergenciasaldo_unico_execucao_material",
            ),
            models.CheckConstraint(
                condition=Q(diferenca=F("saldo_arquivo") - F("saldo_wms")),
                name="catalogo_divergenciasaldo_diferenca_calculo",
            ),
            models.CheckConstraint(
                condition=~Q(diferenca=0),
                name="catalogo_divergenciasaldo_diferenca_nao_zero",
            ),
        ]

    def __str__(self):
        return f"Divergência {self.material_id} — execução {self.execucao_id}"


class AlteracaoCadastralMaterial(models.Model):
    """Rastro de cada campo cadastral alterado por reimportação (FR-032,
    Constitution IV)."""

    execucao = models.ForeignKey(
        "catalogo.ExecucaoImportacao",
        on_delete=models.PROTECT,
        related_name="alteracoes",
    )
    material = models.ForeignKey(
        "catalogo.Material",
        on_delete=models.PROTECT,
    )
    campo = models.CharField(choices=CampoCadastral.choices)
    valor_anterior = models.TextField(blank=True)
    valor_novo = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["execucao", "material", "campo"],
                name="catalogo_alteracaocadastral_unico_execucao_material_campo",
            ),
            models.CheckConstraint(
                condition=~Q(valor_anterior=F("valor_novo")),
                name="catalogo_alteracaocadastral_valor_alterado",
            ),
        ]

    def __str__(self):
        return f"Alteração {self.campo} — material {self.material_id}"
