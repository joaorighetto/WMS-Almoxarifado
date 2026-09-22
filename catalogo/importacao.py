"""Plano de importação do catálogo, prévia em sessão e efetivação atômica.

Módulo de domínio que calcula o **plano de importação** (`calcular_plano`, só
leituras) e o aplica (`aplicar_plano`, dentro de uma transação aberta pelo
chamador). `confirmar_importacao` é o único ponto de entrada que combina os
dois sob o advisory lock, com a comparação de impressão digital que garante
que a confirmação efetiva exatamente o que a prévia mostrou (`research.md`
R8, R9). Assinaturas fixadas em `contracts/interface-importacao.md`.

`calcular_plano` classifica cada aceito como inserção (CADPRO novo) ou
atualização (CADPRO já existente); para atualizações, calcula o diff exato
dos campos cadastrais e divergências de saldo (T044, US4), e
`total_ausentes_no_arquivo` conta os materiais do catálogo ausentes do
arquivo. `aplicar_plano` grava tudo isso — inserções, atualizações
cadastrais com o campo `AlteracaoCadastralMaterial` por mudança e
`DivergenciaSaldo` — sem nunca escrever `saldo`, `saldo_inicial`, `cadpro`
ou `execucao_origem` de material existente (T045, `INV-STOCK-002/003/004`,
`INV-CATALOG-004`).
"""

import base64
import hashlib
import json
import logging
import uuid
import zlib
from dataclasses import dataclass
from decimal import Decimal

from django.db import connection, transaction
from django.utils import timezone

from catalogo import leitura_scpi
from catalogo.leitura_scpi import normalizar_para_busca
from catalogo.models import (
    CAMPOS_CADASTRAIS_ATUALIZAVEIS,
    AlteracaoCadastralMaterial,
    DivergenciaSaldo,
    ExcecaoImportacao,
    ExecucaoImportacao,
    Material,
)

logger = logging.getLogger("catalogo.importacao")

# Constante arbitrária, dedicada à importação do catálogo SCPI — chave do
# `pg_advisory_xact_lock` que serializa confirmações concorrentes
# (`research.md` R9). Cabe em `bigint` com folga.
CHAVE_LOCK_IMPORTACAO_SCPI = 875_019_442

CHAVE_SESSAO_PREVIA = "catalogo_importacao_previa"

# Tamanho de lote para consultas `cadpro__in` e para `bulk_create`/
# `bulk_update` (research.md, "Performance Goals").
TAMANHO_LOTE = 500


@dataclass(frozen=True)
class Atualizacao:
    material_id: int
    cadpro: str
    registro: leitura_scpi.RegistroAceito
    # (campo, valor_anterior, valor_novo), ordenado por campo; vazio quando
    # o registro existente não teve nenhuma mudança cadastral.
    alteracoes: tuple[tuple[str, str, str], ...] = ()


@dataclass(frozen=True)
class Divergencia:
    material_id: int
    cadpro: str
    saldo_wms: Decimal
    saldo_arquivo: Decimal
    diferenca: Decimal


@dataclass(frozen=True)
class PlanoImportacao:
    sha256_arquivo: str
    insercoes: tuple[leitura_scpi.RegistroAceito, ...]
    atualizacoes: tuple[Atualizacao, ...]
    recusas: tuple[leitura_scpi.Recusa, ...]
    divergencias: tuple[Divergencia, ...]
    total_recebidos: int
    total_inseridos: int
    total_atualizados: int
    total_atualizados_com_alteracao: int
    total_rejeitados: int
    total_divergencias: int
    total_ausentes_no_arquivo: int
    impressao_digital: str


@dataclass(frozen=True)
class PedidoPrevia:
    token: str
    nome_arquivo: str
    tamanho: int
    sha256: str
    conteudo: bytes


class PreviaDesatualizada(Exception):
    """A impressão digital recalculada sob lock difere da enviada: o
    catálogo mudou entre a prévia e a confirmação (`research.md` R8/R9)."""

    def __init__(self, plano_atual: PlanoImportacao):
        super().__init__("A prévia ficou desatualizada.")
        self.plano_atual = plano_atual


class PreviaJaConfirmada(Exception):
    """Já existe uma `ExecucaoImportacao` com este `token_previa`
    (idempotência da confirmação, `research.md` R8)."""

    def __init__(self, execucao: ExecucaoImportacao):
        super().__init__("Esta prévia já foi confirmada.")
        self.execucao = execucao


# ---------------------------------------------------------------------------
# Plano de importação (só leituras)
# ---------------------------------------------------------------------------


def _serializar_para_impressao_digital(
    *, sha256_arquivo, insercoes, atualizacoes, recusas, divergencias, total_ausentes_no_arquivo
) -> str:
    """Serialização canônica e determinística do plano (JSON com
    `sort_keys`, `Decimal` como string normalizada) — a impressão digital
    depende só do que o arquivo referencia, nunca do catálogo inteiro
    (`research.md` R8). `total_ausentes_no_arquivo` entra na serialização
    (T044) para que uma prévia fique desatualizada se a contagem de
    ausentes mudar entre a prévia e a confirmação; alterar o saldo de um
    material que já estava ausente não muda essa contagem."""
    dados = {
        "sha256_arquivo": sha256_arquivo,
        "insercoes": [
            {
                "cadpro": registro.cadpro,
                "descricao": registro.descricao,
                "unidade": registro.unidade,
                "detalhamento": registro.detalhamento,
                "grupo": registro.grupo,
                "subgrupo": registro.subgrupo,
                "nome_grupo": registro.nome_grupo,
                "nome_subgrupo": registro.nome_subgrupo,
                "quantidade": str(registro.quantidade),
            }
            for registro in insercoes
        ],
        "atualizacoes": [
            {
                "cadpro": atualizacao.cadpro,
                "alteracoes": [list(item) for item in atualizacao.alteracoes],
            }
            for atualizacao in atualizacoes
        ],
        "recusas": [
            {
                "linha_inicial": recusa.linha_inicial,
                "linha_final": recusa.linha_final,
                "cadpro": recusa.cadpro,
                "motivo": recusa.motivo,
            }
            for recusa in recusas
        ],
        "divergencias": [
            {
                "cadpro": divergencia.cadpro,
                "saldo_wms": str(divergencia.saldo_wms),
                "saldo_arquivo": str(divergencia.saldo_arquivo),
                "diferenca": str(divergencia.diferenca),
            }
            for divergencia in divergencias
        ],
        "total_ausentes_no_arquivo": total_ausentes_no_arquivo,
    }
    texto = json.dumps(dados, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def calcular_plano(conteudo: bytes, *, bloquear: bool = False) -> PlanoImportacao:
    """Calcula o plano de importação a partir do conteúdo do arquivo e do
    estado atual do banco. Só leituras — `bloquear=True` usa
    `select_for_update()` (só dentro de uma transação já aberta pelo
    chamador, ver `confirmar_importacao`).

    Para cada atualização (CADPRO já existente), calcula o diff exato dos
    `CAMPOS_CADASTRAIS_ATUALIZAVEIS` (comparação de texto, sem tolerância) e
    uma divergência quando a quantidade do arquivo difere do saldo atual do
    material (`INV-STOCK-003`; T044). `total_ausentes_no_arquivo` conta, só
    no banco, os materiais cujo `CADPRO` não aparece entre os `CADPRO` bem
    formados do arquivo — aceitos ou recusados (`research.md` R11) — sem
    carregar o catálogo inteiro."""
    sha256_arquivo = hashlib.sha256(conteudo).hexdigest()
    resultado = leitura_scpi.ler_registros(conteudo)

    cadpros_aceitos = sorted({registro.cadpro for registro in resultado.aceitos})
    materiais_existentes: dict[str, Material] = {}
    for inicio in range(0, len(cadpros_aceitos), TAMANHO_LOTE):
        bloco = cadpros_aceitos[inicio : inicio + TAMANHO_LOTE]
        consulta = Material.objects.filter(cadpro__in=bloco)
        if bloquear:
            consulta = consulta.select_for_update().order_by("pk")
        for material in consulta:
            materiais_existentes[material.cadpro] = material

    insercoes: list[leitura_scpi.RegistroAceito] = []
    atualizacoes: list[Atualizacao] = []
    divergencias: list[Divergencia] = []
    for registro in resultado.aceitos:
        material = materiais_existentes.get(registro.cadpro)
        if material is None:
            insercoes.append(registro)
            continue

        alteracoes = sorted(
            (campo, getattr(material, campo), getattr(registro, campo))
            for campo in CAMPOS_CADASTRAIS_ATUALIZAVEIS
            if getattr(material, campo) != getattr(registro, campo)
        )
        atualizacoes.append(
            Atualizacao(
                material_id=material.pk,
                cadpro=registro.cadpro,
                registro=registro,
                alteracoes=tuple(alteracoes),
            )
        )

        if registro.quantidade != material.saldo:
            divergencias.append(
                Divergencia(
                    material_id=material.pk,
                    cadpro=registro.cadpro,
                    saldo_wms=material.saldo,
                    saldo_arquivo=registro.quantidade,
                    diferenca=registro.quantidade - material.saldo,
                )
            )

    insercoes.sort(key=lambda registro: registro.cadpro)
    atualizacoes.sort(key=lambda atualizacao: atualizacao.cadpro)
    divergencias.sort(key=lambda divergencia: divergencia.cadpro)
    recusas = tuple(sorted(resultado.recusas, key=lambda recusa: recusa.linha_inicial))

    total_atualizados_com_alteracao = sum(1 for a in atualizacoes if a.alteracoes)

    # Ausentes (FR-031, R11): CADPRO bem formado no arquivo = todo aceito
    # (por construção) mais todo recusado cujo primeiro campo casa o padrão
    # (ex.: duplicado, ou recusado por outro motivo que não o formato).
    cadpros_bem_formados_no_arquivo = set(cadpros_aceitos)
    for recusa in resultado.recusas:
        if leitura_scpi.PADRAO_CADPRO.fullmatch(recusa.cadpro):
            cadpros_bem_formados_no_arquivo.add(recusa.cadpro)
    total_ausentes_no_arquivo = Material.objects.exclude(
        cadpro__in=cadpros_bem_formados_no_arquivo
    ).count()

    impressao_digital = _serializar_para_impressao_digital(
        sha256_arquivo=sha256_arquivo,
        insercoes=insercoes,
        atualizacoes=atualizacoes,
        recusas=recusas,
        divergencias=divergencias,
        total_ausentes_no_arquivo=total_ausentes_no_arquivo,
    )

    return PlanoImportacao(
        sha256_arquivo=sha256_arquivo,
        insercoes=tuple(insercoes),
        atualizacoes=tuple(atualizacoes),
        recusas=recusas,
        divergencias=tuple(divergencias),
        total_recebidos=resultado.total_recebidos,
        total_inseridos=len(insercoes),
        total_atualizados=len(atualizacoes),
        total_atualizados_com_alteracao=total_atualizados_com_alteracao,
        total_rejeitados=len(recusas),
        total_divergencias=len(divergencias),
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
) -> ExecucaoImportacao:
    """Grava o resultado do plano. Exige transação aberta pelo chamador
    (`confirmar_importacao`). Nunca escreve o saldo de um material
    existente (`INV-STOCK-002`, `INV-STOCK-003`, `INV-CATALOG-004`): a
    reimportação só atualiza os campos cadastrais que de fato mudaram
    (`plano.atualizacoes[].alteracoes`) e registra divergências de saldo
    (`plano.divergencias`), nunca o `saldo` em si."""
    execucao = ExecucaoImportacao.objects.create(
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
        total_divergencias=plano.total_divergencias,
        total_ausentes_no_arquivo=plano.total_ausentes_no_arquivo,
    )

    if plano.insercoes:
        Material.objects.bulk_create(
            [
                Material(
                    cadpro=registro.cadpro,
                    descricao=registro.descricao,
                    descricao_busca=normalizar_para_busca(registro.descricao),
                    unidade=registro.unidade,
                    detalhamento=registro.detalhamento,
                    grupo=registro.grupo,
                    subgrupo=registro.subgrupo,
                    nome_grupo=registro.nome_grupo,
                    nome_subgrupo=registro.nome_subgrupo,
                    saldo=registro.quantidade,
                    saldo_inicial=registro.quantidade,
                    execucao_origem=execucao,
                )
                for registro in plano.insercoes
            ],
            batch_size=TAMANHO_LOTE,
        )

    atualizacoes_com_mudanca = [
        atualizacao for atualizacao in plano.atualizacoes if atualizacao.alteracoes
    ]
    if atualizacoes_com_mudanca:
        materiais_por_id = {
            material.pk: material
            for material in Material.objects.filter(
                pk__in=[atualizacao.material_id for atualizacao in atualizacoes_com_mudanca]
            )
        }
        campos_alterados: set[str] = set()
        alteracoes_para_criar = []
        for atualizacao in atualizacoes_com_mudanca:
            material = materiais_por_id[atualizacao.material_id]
            campos_desta_atualizacao = set()
            for campo, valor_anterior, valor_novo in atualizacao.alteracoes:
                setattr(material, campo, valor_novo)
                campos_desta_atualizacao.add(campo)
                alteracoes_para_criar.append(
                    AlteracaoCadastralMaterial(
                        execucao=execucao,
                        material_id=material.pk,
                        campo=campo,
                        valor_anterior=valor_anterior,
                        valor_novo=valor_novo,
                    )
                )
            if "descricao" in campos_desta_atualizacao:
                material.descricao_busca = normalizar_para_busca(material.descricao)
                campos_desta_atualizacao.add("descricao_busca")
            campos_alterados |= campos_desta_atualizacao

        campos_para_bulk_update = sorted(campos_alterados)
        # Defesa explícita (`INV-STOCK-002`, `INV-STOCK-003`, `INV-CATALOG-004`):
        # a reimportação nunca escreve saldo, saldo_inicial, cadpro ou
        # execucao_origem de material existente — só campos cadastrais e o
        # `descricao_busca` derivado. Verificação explícita, não `assert`, para
        # não desaparecer com `python -O`.
        campos_permitidos = set(CAMPOS_CADASTRAIS_ATUALIZAVEIS) | {"descricao_busca"}
        campos_indevidos = set(campos_para_bulk_update) - campos_permitidos
        if campos_indevidos:
            raise RuntimeError(
                f"a reimportação só pode escrever campos cadastrais; recusados: {campos_indevidos}"
            )

        Material.objects.bulk_update(
            list(materiais_por_id.values()),
            fields=campos_para_bulk_update,
            batch_size=TAMANHO_LOTE,
        )
        AlteracaoCadastralMaterial.objects.bulk_create(
            alteracoes_para_criar, batch_size=TAMANHO_LOTE
        )

    if plano.divergencias:
        DivergenciaSaldo.objects.bulk_create(
            [
                DivergenciaSaldo(
                    execucao=execucao,
                    material_id=divergencia.material_id,
                    saldo_wms=divergencia.saldo_wms,
                    saldo_arquivo=divergencia.saldo_arquivo,
                    diferenca=divergencia.diferenca,
                )
                for divergencia in plano.divergencias
            ],
            batch_size=TAMANHO_LOTE,
        )

    if plano.recusas:
        ExcecaoImportacao.objects.bulk_create(
            [
                ExcecaoImportacao(
                    execucao=execucao,
                    linha_inicial=recusa.linha_inicial,
                    linha_final=recusa.linha_final,
                    cadpro=recusa.cadpro,
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
) -> ExecucaoImportacao:
    """Efetivação atômica sob advisory lock (`research.md` R8/R9):
    1. `pg_advisory_xact_lock` serializa confirmações concorrentes;
    2. se já existir execução com este `token_previa`, nada é gravado e
       `PreviaJaConfirmada` é levantada;
    3. o plano é recalculado com `bloquear=True` e comparado por impressão
       digital; se diferente, nada é gravado e `PreviaDesatualizada` é
       levantada;
    4. senão, `aplicar_plano` grava tudo na mesma transação.
    """
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [CHAVE_LOCK_IMPORTACAO_SCPI])

        execucao_existente = ExecucaoImportacao.objects.filter(
            token_previa=pedido.token
        ).first()
        if execucao_existente is not None:
            logger.warning(
                "Confirmação duplicada da importação do catálogo (token=%s, execucao_id=%s).",
                pedido.token,
                execucao_existente.pk,
            )
            raise PreviaJaConfirmada(execucao_existente)

        plano = calcular_plano(pedido.conteudo, bloquear=True)
        if plano.impressao_digital != impressao_digital_enviada:
            logger.warning(
                "Prévia desatualizada na confirmação da importação do catálogo (token=%s).",
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
        "Importação do catálogo confirmada (execucao_id=%s, usuario_id=%s, sha256=%s, "
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
# Pedido de prévia em sessão (`research.md` R8/I-6)
# ---------------------------------------------------------------------------


def guardar_pedido(session, *, nome_arquivo: str, conteudo: bytes) -> PedidoPrevia:
    """Guarda o pedido de prévia na sessão do usuário (chave
    `CHAVE_SESSAO_PREVIA`). Um pedido por sessão — um novo envio substitui
    o anterior."""
    pedido = PedidoPrevia(
        token=str(uuid.uuid4()),
        nome_arquivo=nome_arquivo[:255],
        tamanho=len(conteudo),
        sha256=hashlib.sha256(conteudo).hexdigest(),
        conteudo=conteudo,
    )
    session[CHAVE_SESSAO_PREVIA] = {
        "token": pedido.token,
        "nome_arquivo": pedido.nome_arquivo,
        "tamanho": pedido.tamanho,
        "sha256": pedido.sha256,
        "conteudo": base64.b64encode(zlib.compress(conteudo)).decode("ascii"),
    }
    return pedido


def obter_pedido(session) -> PedidoPrevia | None:
    dados = session.get(CHAVE_SESSAO_PREVIA)
    if dados is None:
        return None
    conteudo = zlib.decompress(base64.b64decode(dados["conteudo"]))
    return PedidoPrevia(
        token=dados["token"],
        nome_arquivo=dados["nome_arquivo"],
        tamanho=dados["tamanho"],
        sha256=dados["sha256"],
        conteudo=conteudo,
    )


def descartar_pedido(session) -> None:
    session.pop(CHAVE_SESSAO_PREVIA, None)
