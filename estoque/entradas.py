"""Regras de negócio da entrada de materiais (`contracts/interface-estoque.md`,
research R1, R5, R6, R10, R11, R14).

`validar_entrada` só lê o banco: aplica as regras que não dependem de lock
(campos, itens, referência, emitente, limite de saldo) e é usada tanto pelo
"Revisar" da composição quanto, de novo, no início de `registrar_entrada`.
`registrar_entrada` e `estornar_entrada` fazem a escrita, cada uma numa única
`transaction.atomic()`, com a ordem de lock fixada em R5 (`Entrada` →
`Fornecedor` → `Material` por `pk` crescente) — nenhuma view escreve em
`Material`/`MovimentacaoEstoque`/`Entrada`/`ItemEntrada`/`EstornoEntrada`
fora daqui.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from catalogo.models import Material
from contas.models import User
from estoque.models import (
    MOTIVOS_SEM_EMITENTE_OBRIGATORIO,
    Entrada,
    EstornoEntrada,
    ItemEntrada,
    MotivoEntrada,
    MovimentacaoEstoque,
    TipoDocumentoEntrada,
    TipoMovimentacao,
)
from fornecedores.models import Fornecedor

logger = logging.getLogger("estoque.entradas")

# `DecimalField(max_digits=15, decimal_places=3)` (research R11): o maior
# valor representável é 999.999.999.999,999.
LIMITE_SALDO = Decimal("999999999999.999")

_MSG_MOTIVO_AUSENTE = "Escolha o motivo da entrada."
_MSG_TIPO_AUSENTE = "Escolha o tipo de documento."
_MSG_NUMERO_AUSENTE = "Informe o número do documento."
_MSG_EMITENTE_AUSENTE = "Informe o emitente do documento."
_MSG_EMITENTE_INEXISTENTE = "O emitente informado não foi encontrado."
_MSG_EMITENTE_BLOQUEADO = (
    "O fornecedor escolhido está bloqueado no SCPI; escolha outro emitente."
)
_MSG_ITENS_VAZIO = "Inclua ao menos um material."
_MSG_MATERIAL_INEXISTENTE = "Material inexistente no catálogo."
_MSG_MATERIAL_REPETIDO = "Este material já está na entrada."
_MSG_SALDO_ACIMA_DO_LIMITE = "O saldo resultante ultrapassa o limite máximo representável."


@dataclass(frozen=True)
class ItemInformado:
    material_id: int
    quantidade: Decimal  # já interpretada (estoque.quantidade)
    # Posição da linha no `item_formset` original (`estoque/forms.py`,
    # `montar_entrada_informada`) — `None` quando `EntradaInformada` é
    # montada diretamente (fora do HTTP, ex.: testes de domínio), caso em
    # que `validar_entrada`/`registrar_entrada` caem de volta para o índice
    # de `EntradaInformada.itens` (item 2 do review: sem isso, um item
    # excluído por erro de FORMATO de outra linha desalinha as posições
    # restantes e o erro de negócio aponta para a linha errada).
    posicao_formset: int | None = None


@dataclass(frozen=True)
class EntradaInformada:
    chave_confirmacao: UUID
    motivo: str
    tipo_documento: str
    numero_documento: str
    emitente_id: int | None
    itens: tuple[ItemInformado, ...]
    # `True` quando `montar_entrada_informada` excluiu ao menos um item de
    # `itens` por erro de FORMATO da quantidade (research/item 8 do review):
    # sem isso, `validar_entrada` não teria como distinguir "nenhum item
    # informado" de "um item foi informado, mas com quantidade malformada" —
    # o primeiro é `_MSG_ITENS_VAZIO`, o segundo já tem seu próprio erro de
    # campo anexado ao form e não deve, além disso, ganhar essa mensagem.
    tem_item_com_erro_de_formato: bool = False


class EntradaInvalida(Exception):
    """Regra de validação violada (`validar_entrada`/`registrar_entrada`).

    `erros_campo`: mensagens por campo do cabeçalho (`motivo`,
    `tipo_documento`, `numero_documento`, `emitente`) ou, sem campo
    correspondente, sob a chave `itens`. `erros_item`: mensagens por
    POSIÇÃO da linha no formset (`ItemInformado.posicao_formset`; na falta
    dela, a posição em `EntradaInformada.itens`), nunca por `material_id`,
    para apontar a linha exata mesmo com material repetido.
    """

    def __init__(self, erros_campo=None, erros_item=None):
        self.erros_campo: dict[str, list[str]] = erros_campo or {}
        self.erros_item: dict[int, list[str]] = erros_item or {}
        super().__init__("Entrada inválida.")


class EntradaJaRegistrada(Exception):
    """`chave_confirmacao` já usada por uma entrada existente (research R4)."""

    def __init__(self, entrada: Entrada):
        self.entrada = entrada
        super().__init__("Esta entrada já foi registrada.")


class ReferenciaJaUsada(EntradaInvalida):
    """Outra entrada não estornada já usa a mesma referência (FR-007a)."""

    def __init__(self, entrada: Entrada, erros_campo=None, erros_item=None):
        self.entrada = entrada
        super().__init__(erros_campo=erros_campo, erros_item=erros_item)


class EmitenteIndisponivel(EntradaInvalida):
    """Emitente inexistente ou bloqueado, conferido sob lock em
    `registrar_entrada` (research R10)."""


class SaldoAcimaDoLimite(EntradaInvalida):
    """Saldo resultante de `material_id` acima do limite representável
    (research R11)."""

    def __init__(self, material_id: int, erros_campo=None, erros_item=None):
        self.material_id = material_id
        super().__init__(erros_campo=erros_campo, erros_item=erros_item)


class EntradaJaEstornada(Exception):
    def __init__(self, entrada: Entrada):
        self.entrada = entrada
        super().__init__("Esta entrada já foi estornada.")


class JustificativaAusente(Exception):
    def __init__(self):
        super().__init__("Informe a justificativa do estorno.")


class EstornoBloqueadoPorSaldo(Exception):
    """`itens`: lista de `(ItemEntrada, saldo_atual)` que impedem o
    estorno (FR-026)."""

    def __init__(self, itens: list[tuple[ItemEntrada, Decimal]]):
        self.itens = itens
        super().__init__("Estorno bloqueado por saldo insuficiente.")


def _mensagem_referencia_ja_usada(entrada: Entrada) -> str:
    momento = timezone.localtime(entrada.registrada_em).strftime("%d/%m/%Y %H:%M")
    return (
        f"Este documento já foi lançado na entrada de {momento} "
        f"por {entrada.registrada_por.matricula}."
    )


def entrada_corresponde_ao_conteudo(entrada: Entrada, dados: EntradaInformada) -> bool:
    """`True` quando `entrada` (já registrada com a mesma `chave_confirmacao`
    de `dados`) tem o MESMO conteúdo do reenvio: mesmo motivo, tipo, número
    (aparado), emitente e o mesmo conjunto de `(material, quantidade)` dos
    itens. Usada pela view de confirmação para distinguir um reenvio
    idempotente de um formulário antigo reaproveitado por engano para outro
    documento (item 6 do review)."""
    if entrada.motivo != dados.motivo:
        return False
    if entrada.tipo_documento != dados.tipo_documento:
        return False
    if entrada.numero_documento != dados.numero_documento.strip():
        return False
    if entrada.emitente_id != dados.emitente_id:
        return False
    itens_existentes = {
        (item.material_id, item.quantidade) for item in entrada.itens.all()
    }
    itens_informados = {(item.material_id, item.quantidade) for item in dados.itens}
    return itens_existentes == itens_informados


def validar_entrada(dados: EntradaInformada) -> None:
    """Só leitura: aplica toda regra de negócio que não depende de lock.
    Levanta `EntradaInvalida` (ou a subclasse mais específica, quando o
    único problema encontrado é dela) com os erros por campo e por item.
    """
    erros_campo: dict[str, list[str]] = {}
    erros_item: dict[int, list[str]] = {}

    def _campo(nome: str, mensagem: str) -> None:
        erros_campo.setdefault(nome, []).append(mensagem)

    def _item(posicao: int, mensagem: str) -> None:
        erros_item.setdefault(posicao, []).append(mensagem)

    # Item 3 do review: um item excluído de `dados.itens` por erro de
    # FORMATO da quantidade (`montar_entrada_informada`) nunca pode deixar
    # `registrar_entrada` seguir em frente com uma entrada vazia ou
    # parcial — trata-se como o mais básico dos erros, independente da view
    # que chamou `validar_entrada`.
    tem_erro_basico = dados.tem_item_com_erro_de_formato

    motivo_valido = dados.motivo in MotivoEntrada.values
    if not motivo_valido:
        _campo("motivo", _MSG_MOTIVO_AUSENTE)
        tem_erro_basico = True

    tipo_valido = dados.tipo_documento in TipoDocumentoEntrada.values
    if not tipo_valido:
        _campo("tipo_documento", _MSG_TIPO_AUSENTE)
        tem_erro_basico = True

    numero_aparado = dados.numero_documento.strip()
    if not numero_aparado:
        _campo("numero_documento", _MSG_NUMERO_AUSENTE)
        tem_erro_basico = True

    emitente_obrigatorio = motivo_valido and dados.motivo not in MOTIVOS_SEM_EMITENTE_OBRIGATORIO
    if emitente_obrigatorio and dados.emitente_id is None:
        _campo("emitente", _MSG_EMITENTE_AUSENTE)
        tem_erro_basico = True

    tem_emitente_indisponivel = False
    if dados.emitente_id is not None:
        fornecedor = Fornecedor.objects.filter(pk=dados.emitente_id).first()
        if fornecedor is None:
            _campo("emitente", _MSG_EMITENTE_INEXISTENTE)
            tem_emitente_indisponivel = True
        elif fornecedor.bloqueado:
            _campo("emitente", _MSG_EMITENTE_BLOQUEADO)
            tem_emitente_indisponivel = True

    if not dados.itens and not dados.tem_item_com_erro_de_formato:
        _campo("itens", _MSG_ITENS_VAZIO)
        tem_erro_basico = True

    materiais_por_id: dict[int, Material] = {}
    if dados.itens:
        materiais_por_id = {
            material.pk: material
            for material in Material.objects.filter(
                pk__in=[item.material_id for item in dados.itens]
            )
        }

    materiais_vistos: set[int] = set()
    itens_validos: list[tuple[int, Material, Decimal]] = []
    for indice, item in enumerate(dados.itens):
        # A posição REAL da linha no formset (item 2 do review): quando
        # algum item foi excluído por erro de formato, o índice em
        # `dados.itens` (filtrado) já não corresponde à posição da linha na
        # tela. Sem `posicao_formset` (montagem fora do HTTP, ex.: testes de
        # domínio), cai de volta no índice de `dados.itens`, como antes.
        posicao = item.posicao_formset if item.posicao_formset is not None else indice
        material = materiais_por_id.get(item.material_id)
        if material is None:
            _item(posicao, _MSG_MATERIAL_INEXISTENTE)
            tem_erro_basico = True
            continue
        if item.material_id in materiais_vistos:
            _item(posicao, _MSG_MATERIAL_REPETIDO)
            tem_erro_basico = True
            continue
        materiais_vistos.add(item.material_id)
        itens_validos.append((posicao, material, item.quantidade))

    entrada_existente = None
    tem_referencia_duplicada = False
    if tipo_valido and numero_aparado:
        entrada_existente = Entrada.objects.filter(
            tipo_documento=dados.tipo_documento,
            numero_documento=numero_aparado,
            emitente_id=dados.emitente_id,
            estornada=False,
        ).first()
        if entrada_existente is not None:
            _campo("numero_documento", _mensagem_referencia_ja_usada(entrada_existente))
            tem_referencia_duplicada = True

    tem_saldo_acima = False
    material_saldo_acima_id = None
    for posicao, material, quantidade in itens_validos:
        if material.saldo + quantidade > LIMITE_SALDO:
            _item(posicao, _MSG_SALDO_ACIMA_DO_LIMITE)
            tem_saldo_acima = True
            material_saldo_acima_id = material.pk

    if not erros_campo and not erros_item and not tem_erro_basico:
        return

    if tem_erro_basico:
        raise EntradaInvalida(erros_campo=erros_campo, erros_item=erros_item)
    if tem_referencia_duplicada:
        # A mesma `chave_confirmacao` já usada pela entrada que também
        # detém a referência é reenvio idempotente (research R4), não uma
        # referência de OUTRA entrada em conflito (FR-007a).
        if entrada_existente.chave_confirmacao == dados.chave_confirmacao:
            raise EntradaJaRegistrada(entrada_existente)
        raise ReferenciaJaUsada(entrada_existente, erros_campo=erros_campo, erros_item=erros_item)
    if tem_emitente_indisponivel:
        raise EmitenteIndisponivel(erros_campo=erros_campo, erros_item=erros_item)
    if tem_saldo_acima:
        raise SaldoAcimaDoLimite(
            material_saldo_acima_id, erros_campo=erros_campo, erros_item=erros_item
        )
    raise EntradaInvalida(erros_campo=erros_campo, erros_item=erros_item)


def registrar_entrada(dados: EntradaInformada, autor: User) -> Entrada:
    """Sequência de research R5, numa única `transaction.atomic()`. Retorna
    a entrada criada."""
    entrada_existente = Entrada.objects.filter(
        chave_confirmacao=dados.chave_confirmacao
    ).first()
    if entrada_existente is not None:
        raise EntradaJaRegistrada(entrada_existente)

    # Todas as regras que não dependem de lock (R5): campos, itens,
    # referência (pré-checagem) e limite de saldo (leitura sem lock).
    validar_entrada(dados)

    with transaction.atomic():
        if dados.emitente_id is not None:
            fornecedor = (
                Fornecedor.objects.select_for_update().filter(pk=dados.emitente_id).first()
            )
            if fornecedor is None or fornecedor.bloqueado:
                logger.warning(
                    "Entrada recusada: emitente indisponível sob lock (emitente_id=%s).",
                    dados.emitente_id,
                )
                mensagem = (
                    _MSG_EMITENTE_BLOQUEADO if fornecedor is not None else _MSG_EMITENTE_INEXISTENTE
                )
                raise EmitenteIndisponivel(erros_campo={"emitente": [mensagem]})

        materiais_por_id = {
            material.pk: material
            for material in Material.objects.filter(
                pk__in=[item.material_id for item in dados.itens]
            )
            .select_for_update()
            .order_by("pk")
        }

        saldos_resultantes: dict[int, Decimal] = {}
        for indice, item in enumerate(dados.itens):
            # Mesma resolução de posição de `validar_entrada` (item 2 do
            # review).
            posicao = item.posicao_formset if item.posicao_formset is not None else indice
            material = materiais_por_id[item.material_id]
            saldo_resultante = material.saldo + item.quantidade
            if saldo_resultante > LIMITE_SALDO:
                logger.warning(
                    "Entrada recusada: saldo acima do limite sob lock (material_id=%s).",
                    material.pk,
                )
                raise SaldoAcimaDoLimite(
                    material.pk,
                    erros_item={posicao: [_MSG_SALDO_ACIMA_DO_LIMITE]},
                )
            saldos_resultantes[item.material_id] = saldo_resultante

        agora = timezone.now()
        numero_aparado = dados.numero_documento.strip()

        try:
            with transaction.atomic():
                entrada = Entrada.objects.create(
                    chave_confirmacao=dados.chave_confirmacao,
                    motivo=dados.motivo,
                    tipo_documento=dados.tipo_documento,
                    numero_documento=numero_aparado,
                    emitente_id=dados.emitente_id,
                    registrada_por=autor,
                    registrada_em=agora,
                )
        except IntegrityError as exc:
            mensagem_erro = str(exc)
            if "estoque_entrada_referencia_unica" in mensagem_erro:
                entrada_existente = Entrada.objects.filter(
                    tipo_documento=dados.tipo_documento,
                    numero_documento=numero_aparado,
                    emitente_id=dados.emitente_id,
                    estornada=False,
                ).first()
                if entrada_existente is not None and (
                    entrada_existente.chave_confirmacao == dados.chave_confirmacao
                ):
                    # Mesma chave e mesma referência sob corrida (research
                    # R4): reenvio idempotente, não conflito de referência.
                    logger.warning(
                        "Entrada recusada: chave já usada sob concorrência "
                        "(relatada pela constraint de referência)."
                    )
                    raise EntradaJaRegistrada(entrada_existente) from exc
                logger.warning(
                    "Entrada recusada: referência já usada sob concorrência "
                    "(tipo_documento=%s, emitente_id=%s).",
                    dados.tipo_documento,
                    dados.emitente_id,
                )
                raise ReferenciaJaUsada(
                    entrada_existente,
                    erros_campo={
                        "numero_documento": [
                            _mensagem_referencia_ja_usada(entrada_existente)
                        ]
                    },
                ) from exc
            if "chave_confirmacao" in mensagem_erro:
                entrada_existente = Entrada.objects.filter(
                    chave_confirmacao=dados.chave_confirmacao
                ).first()
                logger.warning("Entrada recusada: chave já usada sob concorrência.")
                raise EntradaJaRegistrada(entrada_existente) from exc
            raise

        for item in dados.itens:
            material = materiais_por_id[item.material_id]
            saldo_anterior = material.saldo
            saldo_posterior = saldos_resultantes[item.material_id]

            item_entrada = ItemEntrada.objects.create(
                entrada=entrada,
                material=material,
                quantidade=item.quantidade,
            )

            material.saldo = saldo_posterior
            material.save(update_fields=["saldo"])

            MovimentacaoEstoque.objects.create(
                material=material,
                tipo=TipoMovimentacao.ENTRADA,
                variacao=item.quantidade,
                saldo_anterior=saldo_anterior,
                saldo_posterior=saldo_posterior,
                registrada_por=autor,
                registrada_em=agora,
                item_entrada=item_entrada,
            )

    logger.info(
        "Entrada registrada (entrada_id=%s, autor_id=%s, motivo=%s, itens=%s).",
        entrada.pk,
        autor.pk,
        dados.motivo,
        len(dados.itens),
    )
    return entrada


def estornar_entrada(entrada_id: int, justificativa: str, autor: User) -> EstornoEntrada:
    """Sequência de estorno de research R5, numa única `transaction.atomic()`."""
    justificativa_aparada = justificativa.strip()

    with transaction.atomic():
        entrada = Entrada.objects.select_for_update().get(pk=entrada_id)

        if entrada.estornada:
            raise EntradaJaEstornada(entrada)

        if not justificativa_aparada:
            raise JustificativaAusente()

        itens = list(ItemEntrada.objects.filter(entrada=entrada))
        materiais_por_id = {
            material.pk: material
            for material in Material.objects.filter(
                pk__in=[item.material_id for item in itens]
            )
            .select_for_update()
            .order_by("pk")
        }

        itens_bloqueados: list[tuple[ItemEntrada, Decimal]] = []
        for item in itens:
            material = materiais_por_id[item.material_id]
            if material.saldo - item.quantidade < 0:
                itens_bloqueados.append((item, material.saldo))

        if itens_bloqueados:
            logger.warning(
                "Estorno bloqueado por saldo insuficiente (entrada_id=%s).", entrada.pk
            )
            raise EstornoBloqueadoPorSaldo(itens_bloqueados)

        agora = timezone.now()

        estorno = EstornoEntrada.objects.create(
            entrada=entrada,
            justificativa=justificativa_aparada,
            estornada_por=autor,
            estornada_em=agora,
        )

        entrada.estornada = True
        entrada.save(update_fields=["estornada"])

        for item in itens:
            material = materiais_por_id[item.material_id]
            saldo_anterior = material.saldo
            saldo_posterior = saldo_anterior - item.quantidade

            material.saldo = saldo_posterior
            material.save(update_fields=["saldo"])

            MovimentacaoEstoque.objects.create(
                material=material,
                tipo=TipoMovimentacao.ESTORNO_ENTRADA,
                variacao=-item.quantidade,
                saldo_anterior=saldo_anterior,
                saldo_posterior=saldo_posterior,
                registrada_por=autor,
                registrada_em=agora,
                item_entrada=item,
                estorno_entrada=estorno,
            )

    logger.info(
        "Estorno de entrada efetivado (entrada_id=%s, autor_id=%s).", entrada.pk, autor.pk
    )
    return estorno
