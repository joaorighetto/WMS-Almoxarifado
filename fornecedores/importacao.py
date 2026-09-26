"""Plano de importação de fornecedores, prévia em sessão e efetivação
atômica.

Módulo de domínio que calcula o **plano de importação** (`calcular_plano`, só
leituras) e o aplica (`aplicar_plano`, dentro de uma transação aberta pelo
chamador). `confirmar_importacao` é o único ponto de entrada que combina os
dois sob o advisory lock, com a comparação de impressão digital que garante
que a confirmação efetiva exatamente o que a prévia mostrou (`research.md`
R5). Assinaturas fixadas em `contracts/interface-importacao.md`, no molde de
`catalogo/importacao.py` (research R1).

Diferente da 001: sem saldo, sem divergências; `bloqueado` entra nas
alterações e na impressão digital como `"S"`/`"B"` (o texto do arquivo), não
como booleano.
"""

import base64
import hashlib
import json
import logging
import uuid
import zlib
from dataclasses import dataclass

from django.db import connection, transaction
from django.utils import timezone

from catalogo.leitura_scpi import normalizar_para_busca
from fornecedores import leitura_fornecedores
from fornecedores.leitura_fornecedores import (
    PADRAO_CODIF,
    FornecedorLido,
    LeituraFornecedores,
)
from fornecedores.models import (
    CAMPOS_ATUALIZAVEIS,
    AlteracaoFornecedor,
    ExcecaoImportacaoFornecedores,
    ExecucaoImportacaoFornecedores,
    Fornecedor,
)

logger = logging.getLogger("fornecedores.importacao")

# Constante arbitrária, dedicada à importação de fornecedores — chave do
# `pg_advisory_xact_lock` que serializa confirmações concorrentes
# (`research.md` R5). Distinta de `catalogo.importacao.CHAVE_LOCK_IMPORTACAO_SCPI`
# — importar o catálogo e importar fornecedores não se bloqueiam mutuamente.
CHAVE_LOCK_IMPORTACAO_FORNECEDORES = 331_502_871

CHAVE_SESSAO_PREVIA = "fornecedores_importacao_previa"

# Tamanho de lote para consultas `codif__in` e para `bulk_create`/
# `bulk_update` (research.md R10).
TAMANHO_LOTE = 500


@dataclass(frozen=True)
class Atualizacao:
    fornecedor_id: int
    codif: str
    lido: FornecedorLido
    # (campo, valor_anterior, valor_novo), ordenado por campo; vazio quando o
    # fornecedor existente não teve nenhuma mudança. `bloqueado` entra como
    # "S"/"B" (research R5).
    alteracoes: tuple[tuple[str, str, str], ...] = ()


@dataclass(frozen=True)
class PlanoImportacao:
    sha256_arquivo: str
    insercoes: tuple[FornecedorLido, ...]
    atualizacoes: tuple[Atualizacao, ...]
    recusas: tuple[leitura_fornecedores.RecusaFornecedor, ...]
    total_recebidos: int
    total_inseridos: int
    total_atualizados: int
    total_atualizados_com_alteracao: int
    total_rejeitados: int
    total_ausentes_no_arquivo: int
    impressao_digital: str


@dataclass(frozen=True)
class PedidoPrevia:
    token: str
    nome_arquivo: str
    tamanho: int
    sha256: str
    leitura: LeituraFornecedores  # nunca os bytes do arquivo (research R3)


class PreviaDesatualizada(Exception):
    """A impressão digital recalculada sob lock difere da enviada: o
    cadastro de fornecedores mudou entre a prévia e a confirmação."""

    def __init__(self, plano_atual: PlanoImportacao):
        super().__init__("A prévia ficou desatualizada.")
        self.plano_atual = plano_atual


class PreviaJaConfirmada(Exception):
    """Já existe uma `ExecucaoImportacaoFornecedores` com este
    `token_previa` (idempotência da confirmação)."""

    def __init__(self, execucao: ExecucaoImportacaoFornecedores):
        super().__init__("Esta prévia já foi confirmada.")
        self.execucao = execucao


# ---------------------------------------------------------------------------
# Plano de importação (só leituras)
# ---------------------------------------------------------------------------


def _texto_para_alteracao(campo: str, valor):
    """`bloqueado` entra nas alterações como `"S"`/`"B"` (research R5,
    interface-importacao.md), mesmo sendo um `BooleanField` no model."""
    if campo == "bloqueado":
        return "B" if valor else "S"
    return valor


def _serializar_para_impressao_digital(
    *, sha256_arquivo, insercoes, atualizacoes, recusas, total_ausentes_no_arquivo
) -> str:
    """Serialização canônica e determinística do plano (JSON com
    `sort_keys`) — a impressão digital depende só do que o arquivo
    referencia, nunca do cadastro inteiro."""
    dados = {
        "sha256_arquivo": sha256_arquivo,
        "insercoes": [
            {
                "codif": lido.codif,
                "nome": lido.nome,
                "nome_fantasia": lido.nome_fantasia,
                "documento": lido.documento,
                "tipo": lido.tipo,
                # "B"/"S", não booleano — mesma representação textual do
                # arquivo usada nas alterações (`_texto_para_alteracao`),
                # conforme `contracts/interface-importacao.md`: "`bloqueado`
                # entra nas alterações e na impressão digital como
                # 'B'/'S'" (revisão do code-reviewer).
                "bloqueado": _texto_para_alteracao("bloqueado", lido.bloqueado),
                "motivo_bloqueio": lido.motivo_bloqueio,
                "tipo_bloqueio": lido.tipo_bloqueio,
            }
            for lido in insercoes
        ],
        "atualizacoes": [
            {
                "codif": atualizacao.codif,
                "alteracoes": [list(item) for item in atualizacao.alteracoes],
            }
            for atualizacao in atualizacoes
        ],
        "recusas": [
            {"linha": recusa.linha, "codif": recusa.codif, "motivo": recusa.motivo}
            for recusa in recusas
        ],
        "total_ausentes_no_arquivo": total_ausentes_no_arquivo,
    }
    texto = json.dumps(dados, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def calcular_plano(
    leitura: LeituraFornecedores, sha256_arquivo: str, *, bloquear: bool = False
) -> PlanoImportacao:
    """Calcula o plano de importação a partir da leitura já projetada
    (`fornecedores.leitura_fornecedores.ler_fornecedores`) e do estado atual
    do cadastro. Só leituras — `bloquear=True` usa `select_for_update()` (só
    dentro de uma transação já aberta pelo chamador, ver
    `confirmar_importacao`).

    `total_ausentes_no_arquivo` conta, só no banco, os fornecedores cujo
    `codif` não aparece entre os `CODIF` bem formados do arquivo — aceitos ou
    recusados —, sem carregar o cadastro inteiro (por analogia a
    `catalogo.importacao.calcular_plano`)."""
    codifs_aceitos = sorted({lido.codif for lido in leitura.aceitos})
    fornecedores_existentes: dict[str, Fornecedor] = {}
    for inicio in range(0, len(codifs_aceitos), TAMANHO_LOTE):
        bloco = codifs_aceitos[inicio : inicio + TAMANHO_LOTE]
        consulta = Fornecedor.objects.filter(codif__in=bloco)
        if bloquear:
            consulta = consulta.select_for_update().order_by("pk")
        for fornecedor in consulta:
            fornecedores_existentes[fornecedor.codif] = fornecedor

    insercoes: list[FornecedorLido] = []
    atualizacoes: list[Atualizacao] = []
    for lido in leitura.aceitos:
        fornecedor = fornecedores_existentes.get(lido.codif)
        if fornecedor is None:
            insercoes.append(lido)
            continue

        alteracoes = sorted(
            (
                campo,
                _texto_para_alteracao(campo, getattr(fornecedor, campo)),
                _texto_para_alteracao(campo, getattr(lido, campo)),
            )
            for campo in CAMPOS_ATUALIZAVEIS
            if getattr(fornecedor, campo) != getattr(lido, campo)
        )
        atualizacoes.append(
            Atualizacao(
                fornecedor_id=fornecedor.pk,
                codif=lido.codif,
                lido=lido,
                alteracoes=tuple(alteracoes),
            )
        )

    insercoes.sort(key=lambda lido: lido.codif)
    atualizacoes.sort(key=lambda atualizacao: atualizacao.codif)
    recusas = tuple(sorted(leitura.recusas, key=lambda recusa: recusa.linha))

    total_atualizados_com_alteracao = sum(1 for a in atualizacoes if a.alteracoes)

    codifs_bem_formados_no_arquivo = set(codifs_aceitos)
    for recusa in leitura.recusas:
        if PADRAO_CODIF.fullmatch(recusa.codif):
            codifs_bem_formados_no_arquivo.add(recusa.codif)
    total_ausentes_no_arquivo = Fornecedor.objects.exclude(
        codif__in=codifs_bem_formados_no_arquivo
    ).count()

    impressao_digital = _serializar_para_impressao_digital(
        sha256_arquivo=sha256_arquivo,
        insercoes=insercoes,
        atualizacoes=atualizacoes,
        recusas=recusas,
        total_ausentes_no_arquivo=total_ausentes_no_arquivo,
    )

    return PlanoImportacao(
        sha256_arquivo=sha256_arquivo,
        insercoes=tuple(insercoes),
        atualizacoes=tuple(atualizacoes),
        recusas=recusas,
        total_recebidos=leitura.total_recebidos,
        total_inseridos=len(insercoes),
        total_atualizados=len(atualizacoes),
        total_atualizados_com_alteracao=total_atualizados_com_alteracao,
        total_rejeitados=len(recusas),
        total_ausentes_no_arquivo=total_ausentes_no_arquivo,
        impressao_digital=impressao_digital,
    )


# ---------------------------------------------------------------------------
# Efetivação (exige transação aberta pelo chamador)
# ---------------------------------------------------------------------------


def aplicar_plano(
    plano: PlanoImportacao,
    *,
    usuario,
    token_previa: str,
    nome_arquivo: str,
    tamanho_arquivo: int,
) -> ExecucaoImportacaoFornecedores:
    """Grava o resultado do plano. Exige transação aberta pelo chamador
    (`confirmar_importacao`). Só escreve `CAMPOS_ATUALIZAVEIS` e os
    derivados (`documento_digitos`, `nome_busca`) de fornecedor existente —
    nunca `codif`/`execucao_origem` (`INV-SUPPLIER-001/002`, defesa
    explícita abaixo)."""
    execucao = ExecucaoImportacaoFornecedores.objects.create(
        token_previa=token_previa,
        executada_por=usuario,
        concluida_em=timezone.now(),
        nome_arquivo=nome_arquivo[:255],
        tamanho_arquivo=tamanho_arquivo,
        sha256_arquivo=plano.sha256_arquivo,
        total_recebidos=plano.total_recebidos,
        total_inseridos=plano.total_inseridos,
        total_atualizados=plano.total_atualizados,
        total_atualizados_com_alteracao=plano.total_atualizados_com_alteracao,
        total_rejeitados=plano.total_rejeitados,
        total_ausentes_no_arquivo=plano.total_ausentes_no_arquivo,
    )

    if plano.insercoes:
        Fornecedor.objects.bulk_create(
            [
                Fornecedor(
                    codif=lido.codif,
                    nome=lido.nome,
                    nome_fantasia=lido.nome_fantasia,
                    documento=lido.documento,
                    documento_digitos=leitura_fornecedores.somente_digitos(lido.documento),
                    tipo=lido.tipo,
                    bloqueado=lido.bloqueado,
                    motivo_bloqueio=lido.motivo_bloqueio,
                    tipo_bloqueio=lido.tipo_bloqueio,
                    nome_busca=normalizar_para_busca(f"{lido.nome} {lido.nome_fantasia}"),
                    execucao_origem=execucao,
                )
                for lido in plano.insercoes
            ],
            batch_size=TAMANHO_LOTE,
        )

    atualizacoes_com_mudanca = [a for a in plano.atualizacoes if a.alteracoes]
    if atualizacoes_com_mudanca:
        fornecedores_por_id = {
            fornecedor.pk: fornecedor
            for fornecedor in Fornecedor.objects.filter(
                pk__in=[atualizacao.fornecedor_id for atualizacao in atualizacoes_com_mudanca]
            )
        }
        campos_alterados: set[str] = set()
        alteracoes_para_criar = []
        for atualizacao in atualizacoes_com_mudanca:
            fornecedor = fornecedores_por_id[atualizacao.fornecedor_id]
            campos_desta_atualizacao = set()
            for campo, valor_anterior, valor_novo in atualizacao.alteracoes:
                setattr(fornecedor, campo, getattr(atualizacao.lido, campo))
                campos_desta_atualizacao.add(campo)
                alteracoes_para_criar.append(
                    AlteracaoFornecedor(
                        execucao=execucao,
                        fornecedor_id=fornecedor.pk,
                        campo=campo,
                        valor_anterior=valor_anterior,
                        valor_novo=valor_novo,
                    )
                )
            if "documento" in campos_desta_atualizacao:
                fornecedor.documento_digitos = leitura_fornecedores.somente_digitos(
                    fornecedor.documento
                )
                campos_desta_atualizacao.add("documento_digitos")
            if campos_desta_atualizacao & {"nome", "nome_fantasia"}:
                fornecedor.nome_busca = normalizar_para_busca(
                    f"{fornecedor.nome} {fornecedor.nome_fantasia}"
                )
                campos_desta_atualizacao.add("nome_busca")
            campos_alterados |= campos_desta_atualizacao

        campos_para_bulk_update = sorted(campos_alterados)
        # Defesa explícita (`INV-SUPPLIER-001`, `INV-SUPPLIER-002`): a
        # reimportação nunca escreve `codif` nem `execucao_origem` de
        # fornecedor existente — só campos atualizáveis e os derivados.
        # Verificação explícita, não `assert`, para não desaparecer com
        # `python -O`.
        campos_permitidos = set(CAMPOS_ATUALIZAVEIS) | {"documento_digitos", "nome_busca"}
        campos_indevidos = set(campos_para_bulk_update) - campos_permitidos
        if campos_indevidos:
            raise RuntimeError(
                "a reimportação só pode escrever campos atualizáveis; "
                f"recusados: {campos_indevidos}"
            )

        Fornecedor.objects.bulk_update(
            list(fornecedores_por_id.values()),
            fields=campos_para_bulk_update,
            batch_size=TAMANHO_LOTE,
        )
        AlteracaoFornecedor.objects.bulk_create(alteracoes_para_criar, batch_size=TAMANHO_LOTE)

    if plano.recusas:
        ExcecaoImportacaoFornecedores.objects.bulk_create(
            [
                ExcecaoImportacaoFornecedores(
                    execucao=execucao,
                    linha=recusa.linha,
                    codif=recusa.codif,
                    motivo=recusa.motivo,
                    detalhe=recusa.detalhe,
                )
                for recusa in plano.recusas
            ],
            batch_size=TAMANHO_LOTE,
        )

    return execucao


def confirmar_importacao(
    pedido: PedidoPrevia, impressao_digital_enviada: str, usuario
) -> ExecucaoImportacaoFornecedores:
    """Efetivação atômica sob advisory lock:
    1. `pg_advisory_xact_lock` serializa confirmações concorrentes;
    2. se já existir execução com este `token_previa`, nada é gravado e
       `PreviaJaConfirmada` é levantada;
    3. o plano é recalculado com `bloquear=True` e comparado por impressão
       digital; se diferente, nada é gravado e `PreviaDesatualizada` é
       levantada;
    4. senão, `aplicar_plano` grava tudo na mesma transação.

    O log nunca inclui dado de fornecedor — só ids, SHA-256 e totais
    (`research.md` R8).
    """
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [CHAVE_LOCK_IMPORTACAO_FORNECEDORES])

        execucao_existente = ExecucaoImportacaoFornecedores.objects.filter(
            token_previa=pedido.token
        ).first()
        if execucao_existente is not None:
            logger.warning(
                "Confirmação duplicada da importação de fornecedores (token=%s, execucao_id=%s).",
                pedido.token,
                execucao_existente.pk,
            )
            raise PreviaJaConfirmada(execucao_existente)

        plano = calcular_plano(pedido.leitura, pedido.sha256, bloquear=True)
        if plano.impressao_digital != impressao_digital_enviada:
            logger.warning(
                "Prévia desatualizada na confirmação da importação de fornecedores (token=%s).",
                pedido.token,
            )
            raise PreviaDesatualizada(plano)

        execucao = aplicar_plano(
            plano,
            usuario=usuario,
            token_previa=pedido.token,
            nome_arquivo=pedido.nome_arquivo,
            tamanho_arquivo=pedido.tamanho,
        )

    logger.info(
        "Importação de fornecedores confirmada (execucao_id=%s, usuario_id=%s, sha256=%s, "
        "recebidos=%s, inseridos=%s, atualizados=%s, rejeitados=%s).",
        execucao.pk,
        usuario.pk,
        execucao.sha256_arquivo,
        execucao.total_recebidos,
        execucao.total_inseridos,
        execucao.total_atualizados,
        execucao.total_rejeitados,
    )
    return execucao


# ---------------------------------------------------------------------------
# Pedido de prévia em sessão (research.md R3)
# ---------------------------------------------------------------------------


def guardar_pedido(session, *, nome_arquivo: str, conteudo: bytes) -> PedidoPrevia:
    """Lê e projeta o arquivo imediatamente (`ler_fornecedores`), e guarda na
    sessão só a projeção: `{token, nome_arquivo, tamanho, sha256, leitura}`.
    Os bytes do arquivo nunca são persistidos (`INV-SUPPLIER-004`).

    Se o arquivo inteiro for recusado, `catalogo.leitura_scpi.ArquivoRecusado`
    propaga sem tocar a sessão (levantada por `ler_fornecedores` antes da
    atribuição a `session[...]`, abaixo)."""
    leitura = leitura_fornecedores.ler_fornecedores(conteudo)

    pedido = PedidoPrevia(
        token=str(uuid.uuid4()),
        nome_arquivo=nome_arquivo[:255],
        tamanho=len(conteudo),
        sha256=hashlib.sha256(conteudo).hexdigest(),
        leitura=leitura,
    )
    texto_leitura = json.dumps(leitura_fornecedores.para_json(leitura))
    session[CHAVE_SESSAO_PREVIA] = {
        "token": pedido.token,
        "nome_arquivo": pedido.nome_arquivo,
        "tamanho": pedido.tamanho,
        "sha256": pedido.sha256,
        "leitura": base64.b64encode(zlib.compress(texto_leitura.encode("utf-8"))).decode("ascii"),
    }
    return pedido


def obter_pedido(session) -> PedidoPrevia | None:
    dados = session.get(CHAVE_SESSAO_PREVIA)
    if dados is None:
        return None
    texto_leitura = zlib.decompress(base64.b64decode(dados["leitura"])).decode("utf-8")
    leitura = leitura_fornecedores.de_json(json.loads(texto_leitura))
    return PedidoPrevia(
        token=dados["token"],
        nome_arquivo=dados["nome_arquivo"],
        tamanho=dados["tamanho"],
        sha256=dados["sha256"],
        leitura=leitura,
    )


def descartar_pedido(session) -> None:
    session.pop(CHAVE_SESSAO_PREVIA, None)
