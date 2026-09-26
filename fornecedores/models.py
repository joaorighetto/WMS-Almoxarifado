from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import F, Q, Value
from django.db.models.functions import Trim
from django.db.models.lookups import GreaterThan


class MotivoRecusaFornecedor(models.TextChoices):
    """Motivos de recusa de registro na importação (`research.md` R2)."""

    COLUNAS_DESLOCADAS = (
        "COLUNAS_DESLOCADAS",
        "Número de colunas do registro diferente do cabeçalho",
    )
    CODIF_AUSENTE = "CODIF_AUSENTE", "Código (CODIF) ausente"
    CODIF_INVALIDO = "CODIF_INVALIDO", "Código (CODIF) em formato inválido"
    CODIF_DUPLICADO = "CODIF_DUPLICADO", "Código (CODIF) duplicado no arquivo"
    NOME_AUSENTE = "NOME_AUSENTE", "Nome ausente"
    SITUACAO_BLOQUEIO_INVALIDA = (
        "SITUACAO_BLOQUEIO_INVALIDA",
        "Situação de bloqueio inválida",
    )


class CampoFornecedor(models.TextChoices):
    """Os 7 campos atualizáveis por reimportação — espelha
    `CAMPOS_ATUALIZAVEIS`.

    `BLOQUEADO.label` é "Situação" (decisão do dono do produto, gate visual):
    a coluna "Campo" da trilha de alterações mostra o rótulo de exibição,
    não o nome técnico, e "Situação" é como a tela já chama a condição de
    bloqueio em outros lugares (badge Bloqueado/Liberado da consulta). O
    `value` continua `"bloqueado"` — só o texto exibido muda."""

    NOME = "nome", "Nome"
    NOME_FANTASIA = "nome_fantasia", "Nome fantasia"
    DOCUMENTO = "documento", "Documento"
    TIPO = "tipo", "Tipo"
    BLOQUEADO = "bloqueado", "Situação"
    MOTIVO_BLOQUEIO = "motivo_bloqueio", "Motivo do bloqueio"
    TIPO_BLOQUEIO = "tipo_bloqueio", "Tipo de bloqueio"


# Lista fechada dos campos atualizáveis por reimportação (FR-020, FR-021,
# `INV-SUPPLIER-003`). Os derivados `documento_digitos` e `nome_busca` são
# reescritos junto do campo de origem, mas não são campos do arquivo por si
# só — por isso não integram esta lista (ver `CampoFornecedor`, que espelha
# exatamente estes 7 campos).
CAMPOS_ATUALIZAVEIS = (
    "nome",
    "nome_fantasia",
    "documento",
    "tipo",
    "bloqueado",
    "motivo_bloqueio",
    "tipo_bloqueio",
)


class ExecucaoImportacaoFornecedores(models.Model):
    """Uma importação **confirmada** do cadastro de fornecedores.

    Prévias não confirmadas não geram execução — nascem e vivem só na sessão
    do usuário (`fornecedores.importacao`, research R3).
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
    total_ausentes_no_arquivo = models.PositiveIntegerField()

    class Meta:
        ordering = ["-concluida_em", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    total_recebidos=F("total_inseridos")
                    + F("total_atualizados")
                    + F("total_rejeitados")
                ),
                name="fornecedores_execucao_totais_ok",
            ),
            models.CheckConstraint(
                condition=Q(total_atualizados_com_alteracao__lte=F("total_atualizados")),
                name="fornecedores_execucao_atualizados_alteracao_max",
            ),
        ]

    def __str__(self):
        return f"Importação {self.pk} — {self.nome_arquivo}"


class Fornecedor(models.Model):
    """Fornecedor do cadastro do SCPI (`data-model.md` → Fornecedor).

    Somente-inserção do ponto de vista da aplicação, exceto os campos
    listados em `CAMPOS_ATUALIZAVEIS`, que só mudam por reimportação
    (`INV-SUPPLIER-003`). `codif` e `execucao_origem` nunca são atualizados
    (`INV-SUPPLIER-001`, `INV-SUPPLIER-002`). Nenhuma view ou método deste
    módulo cria, edita ou exclui `Fornecedor` fora de `fornecedores.importacao`.
    Nenhum outro dado do arquivo original tem campo (`INV-SUPPLIER-004`).
    """

    codif = models.TextField(unique=True, editable=False)
    nome = models.TextField()
    nome_fantasia = models.TextField(blank=True)
    documento = models.TextField(blank=True)
    documento_digitos = models.TextField(blank=True)
    tipo = models.TextField(blank=True)
    bloqueado = models.BooleanField()
    motivo_bloqueio = models.TextField(blank=True)
    tipo_bloqueio = models.TextField(blank=True)
    nome_busca = models.TextField()
    execucao_origem = models.ForeignKey(
        "fornecedores.ExecucaoImportacaoFornecedores",
        on_delete=models.PROTECT,
        editable=False,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["codif"],
                name="fornecedores_fornecedor_codif_unico",
            ),
            models.CheckConstraint(
                condition=Q(codif__regex=r"^[0-9]+$"),
                name="fornecedores_fornecedor_codif_formato",
            ),
            models.CheckConstraint(
                condition=GreaterThan(Trim(F("nome")), Value("")),
                name="fornecedores_fornecedor_nome_nao_vazio",
            ),
        ]
        indexes = [
            models.Index(
                fields=["documento_digitos"],
                name="fornecedor_doc_digitos_idx",
            ),
            GinIndex(
                fields=["nome_busca"],
                opclasses=["gin_trgm_ops"],
                name="fornecedor_busca_gin",
            ),
        ]

    def __str__(self):
        return self.codif


class ExcecaoImportacaoFornecedores(models.Model):
    """Registro recusado dentro de uma execução."""

    execucao = models.ForeignKey(
        "fornecedores.ExecucaoImportacaoFornecedores",
        on_delete=models.PROTECT,
        related_name="excecoes",
    )
    linha = models.PositiveIntegerField()
    codif = models.TextField(blank=True)
    motivo = models.CharField(choices=MotivoRecusaFornecedor.choices)
    detalhe = models.TextField(blank=True)

    class Meta:
        ordering = ["linha"]
        constraints = [
            models.CheckConstraint(
                condition=Q(linha__gte=1),
                name="fornecedores_excecao_linha_minima",
            ),
        ]

    def __str__(self):
        return f"Exceção linha {self.linha} — {self.motivo}"


class AlteracaoFornecedor(models.Model):
    """Rastro de cada campo atualizado por reimportação (FR-020, FR-021,
    Constitution IV)."""

    execucao = models.ForeignKey(
        "fornecedores.ExecucaoImportacaoFornecedores",
        on_delete=models.PROTECT,
        related_name="alteracoes",
    )
    fornecedor = models.ForeignKey(
        "fornecedores.Fornecedor",
        on_delete=models.PROTECT,
        related_name="alteracoes",
    )
    campo = models.CharField(choices=CampoFornecedor.choices)
    valor_anterior = models.TextField(blank=True)
    valor_novo = models.TextField(blank=True)

    class Meta:
        constraints = [
            # Uma alteração por campo em cada execução, e só de campo que mudou
            # (T014), como em catalogo.AlteracaoCadastralMaterial.
            models.UniqueConstraint(
                fields=["execucao", "fornecedor", "campo"],
                name="fornecedores_alteracao_unica_por_campo",
            ),
            models.CheckConstraint(
                condition=~Q(valor_anterior=F("valor_novo")),
                name="fornecedores_alteracao_valor_alterado",
            ),
        ]

    def __str__(self):
        return f"Alteração {self.campo} — fornecedor {self.fornecedor_id}"
