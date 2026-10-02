"""Operações de escrita da organização — usuários, papéis e setores (feature 005).

Só este módulo escreve dados organizacionais (`Setor`, `PapelUsuario` e os campos
organizacionais de `User`): a barreira de `contas.models` recusa qualquer escrita fora de
`_operacao()` (research R4). Cada operação:

1. abre `transaction.atomic()`, toma o advisory lock único de organização e liga a
   barreira (R2) — `_operacao()`;
2. relê o estado atual e verifica as regras próprias da operação;
3. escreve;
4. chama `validar_organizacao` sobre o estado final (R3);
5. grava o `EventoOrganizacional` (R7).

Recusa é `OperacaoRecusada(motivo, caminho)`, sem escrita. Nenhum import de model de
outro app (FR-051): a escrita fica toda em `contas`. O logger `contas.organizacao` nunca
registra senha nem o conteúdo de `dados` (R18).

Traz a base comum, a API de provisionamento técnico (autor nulo, R15) e as operações das
stories: cadastro, manutenção e transferência de usuário, chefia de setor, situação do usuário,
redefinição de senha e administração de setores.
"""

import logging
import os
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, transaction
from django.db.models import Value
from django.db.models.functions import Lower, Trim
from django.utils import timezone

from contas.credenciais import gerar_senha_provisoria
from contas.models import (
    _OPERACAO_EM_CURSO,
    EventoOrganizacional,
    Papel,
    PapelUsuario,
    Setor,
    TipoEvento,
    User,
    chefes_ativos,
)

logger = logging.getLogger("contas.organizacao")

# Advisory lock único das operações de organização (R2); distinto das chaves de
# importação do catálogo e de fornecedores. O trigger adiado de R5 toma a mesma chave.
CHAVE_LOCK_ORGANIZACAO = 331_502_873

# Só nestes ambientes o provisionamento aceita uma senha conhecida (`senha=`, D-23, FR-031).
AMBIENTES_COM_SENHA_CONHECIDA = frozenset({"config.settings.development", "config.settings.test"})

PAPEIS_ALMOXARIFADO = frozenset({Papel.FUNCIONARIO_ALMOXARIFADO, Papel.CHEFE_ALMOXARIFADO})

# Papéis presos ao setor de origem: a transferência os remove (FR-013). `ROLE-REQUESTER`,
# `ROLE-AUDITOR` e `ROLE-SYSTEM-ADMIN` não dependem do setor e ficam.
PAPEIS_PRESOS_AO_SETOR = frozenset(
    {
        Papel.AUXILIAR_SETOR,
        Papel.CHEFE_SETOR,
        Papel.FUNCIONARIO_ALMOXARIFADO,
        Papel.CHEFE_ALMOXARIFADO,
    }
)

# Códigos de regra de `OperacaoRecusada.codigo`: as telas escolhem o destino do caminho por eles.
RECUSA_CHEFE_DE_SETOR_ATIVO = "chefe_de_setor_ativo"
RECUSA_PROPRIA_CONTA = "propria_conta"
RECUSA_ULTIMO_ADMINISTRADOR = "ultimo_administrador"
RECUSA_MEMBROS_ATIVOS = "membros_ativos"
RECUSA_ALMOXARIFADO_PERMANENTE = "almoxarifado_permanente"
RECUSA_SETOR_SEM_CHEFE = "setor_sem_chefe"
RECUSA_SETOR_JA_TEM_CHEFE = "setor_ja_tem_chefe"
RECUSA_CHEFIA_DE_ESTOQUE_INCOMPLETA = "chefia_de_estoque_incompleta"
RECUSA_MATRICULA_EM_USO = "matricula_em_uso"
RECUSA_PAPEL_DE_ALMOXARIFADO_FORA_DO_ALMOXARIFADO = "papel_de_almoxarifado_fora_do_almoxarifado"

# `ROLE-SECTOR-HEAD` no cadastro do Almoxarifado leva junto a chefia de estoque (`INV-ORG-006`).
PAPEIS_QUE_ACOMPANHAM_O_CHEFE_DO_ALMOXARIFADO = frozenset(
    {Papel.CHEFE_ALMOXARIFADO, Papel.FUNCIONARIO_ALMOXARIFADO}
)


class OperacaoRecusada(Exception):
    """A operação violaria uma regra do domínio. Nada foi escrito.

    `motivo` é a regra violada e `caminho`, quando há, o que o administrador faz em
    seguida; as views mostram ambos como estão (FR-048). `codigo`, quando há, identifica a regra
    para a tela escolher o destino do caminho sem ler o texto (constantes `RECUSA_*`); `membros`
    são os usuários que a regra aponta (`RECUSA_MEMBROS_ATIVOS`), para a tela listá-los.
    """

    def __init__(self, motivo, caminho=None, *, codigo=None, membros=()):
        super().__init__(motivo)
        self.motivo = motivo
        self.caminho = caminho
        self.codigo = codigo
        self.membros = tuple(membros)


class OperacaoJaExecutada(Exception):
    """A mesma `chave_confirmacao` já gerou este evento (idempotência, R8)."""

    def __init__(self, evento):
        super().__init__("Operação já executada.")
        self.evento = evento


class PreviaDesatualizada(Exception):
    """Os efeitos calculados sob o lock diferem dos que a prévia mostrou (FR-049)."""

    def __init__(self, previa):
        super().__init__("O estado mudou desde que a prévia foi calculada.")
        self.previa = previa


@dataclass(frozen=True)
class PreviaTransferencia:
    """Efeitos da transferência: `papeis_removidos` na ordem do catálogo de papéis."""

    usuario: User
    setor_destino: Setor
    papeis_removidos: tuple


@dataclass(frozen=True)
class PreviaSubstituicao:
    """Efeitos da substituição de chefia: só o que MUDA para cada pessoa (`novo_ganha` não lista
    o `ROLE-WAREHOUSE-STAFF` que o novo chefe já tem), na ordem do catálogo de papéis."""

    setor: Setor
    chefe_atual: User
    novo_chefe: User
    novo_ganha: tuple
    anterior_perde: tuple


@dataclass(frozen=True)
class PreviaReativacao:
    """Papéis preservados que a reativação devolveria (`papeis_preservados`, na ordem do
    catálogo de papéis) e, entre eles, os que violariam uma regra se mantidos: `recusas` mapeia
    `Papel` para a `OperacaoRecusada` que `reativar_usuario` levantaria por esse papel."""

    usuario: User
    papeis_preservados: tuple
    recusas: dict

    @property
    def recusa_sem_requisitante(self):
        """A recusa de reativar uma conta que perdeu `ROLE-REQUESTER` enquanto inativa (exige
        concedê-lo antes, na tela de papéis), ou `None` se ela ainda o tem."""
        if Papel.REQUISITANTE in self.papeis_preservados:
            return None
        return OperacaoRecusada(*_RECUSA_REATIVACAO_SEM_REQUISITANTE)


@contextmanager
def _operacao():
    """Contexto de toda escrita organizacional: transação, lock único e barreira ligada.

    Não valida ao sair: cada operação chama `validar_organizacao` sobre o estado final.
    O marcador é restaurado mesmo quando o bloco falha (não vaza).
    """
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [CHAVE_LOCK_ORGANIZACAO])
        token = _OPERACAO_EM_CURSO.set(True)
        try:
            yield
        finally:
            _OPERACAO_EM_CURSO.reset(token)


def _recusar(motivo, caminho=None, **extras):
    """Registra a recusa (INFO, sem dados) e devolve a exceção a levantar."""
    return _levantar(OperacaoRecusada(motivo, caminho, **extras))


def _levantar(recusa):
    """Registra uma recusa já montada por uma checagem de leitura (INFO, sem dados) e a devolve
    para a operação levantá-la."""
    logger.info("Operação organizacional recusada: %s", recusa.motivo)
    return recusa


def _papeis(usuario):
    """Conjunto de `Papel` atribuídos hoje ao usuário (lido do banco)."""
    papeis = PapelUsuario.objects.filter(usuario=usuario).values_list("papel", flat=True)
    return {Papel(papel) for papel in papeis}


def _administradores_ativos():
    """Identidades de negócio ativas com `ROLE-SYSTEM-ADMIN` (D-15)."""
    return User.objects.filter(
        is_active=True,
        is_superuser=False,
        papeis__papel=Papel.ADMINISTRADOR_SISTEMA,
    )


def _registrar_evento(
    autor,
    tipo,
    *,
    usuario=None,
    usuario_relacionado=None,
    setor=None,
    setor_relacionado=None,
    dados=None,
    justificativa="",
    chave_confirmacao=None,
):
    """Grava o evento na transação da operação. `dados` nunca leva senha (FR-031)."""
    evento = EventoOrganizacional.objects.create(
        autor=autor,
        tipo=tipo,
        usuario=usuario,
        usuario_relacionado=usuario_relacionado,
        setor=setor,
        setor_relacionado=setor_relacionado,
        dados=dados or {},
        justificativa=justificativa,
        chave_confirmacao=chave_confirmacao,
    )
    logger.info(
        "Evento organizacional %s: autor=%s usuario=%s setor=%s",
        tipo,
        autor.pk if autor else None,
        usuario.pk if usuario else None,
        setor.pk if setor else None,
    )
    return evento


# ---------------------------------------------------------------------------
# Validação do estado final (research R3; data-model.md, "Verificação de estado final")
# ---------------------------------------------------------------------------


def validar_organizacao(setores, usuarios):
    """Verifica `INV-ORG-001` a `INV-ORG-006` e o papel mínimo (FR-016a da 002) no
    estado atual do banco, para os `setores` e `usuarios` tocados e para os membros
    dos setores tocados. Levanta `OperacaoRecusada` com a regra violada.

    Regras: (1) setor ativo tem exatamente um chefe ativo próprio e nenhum setor tem mais
    de um; (2) papéis de almoxarifado só no Almoxarifado; (3) quem tem a chefia do
    almoxarifado a tem com os papéis de chefe do setor e de funcionário, e o chefe do
    Almoxarifado ativo tem a chefia de estoque; (4) identidade de negócio ativa tem
    `ROLE-REQUESTER` e a conta técnica não tem papel nenhum.
    """
    campos_usuario = ("pk", "matricula", "is_active", "is_superuser", "setor_id")
    usuario_ids = {usuario.pk for usuario in usuarios}
    setor_ids = {setor.pk for setor in setores}
    if usuario_ids:
        setor_ids |= set(User.objects.filter(pk__in=usuario_ids).values_list("setor_id", flat=True))
    usuario_ids |= set(User.objects.filter(setor_id__in=setor_ids).values_list("pk", flat=True))
    dados_usuarios = {
        u["pk"]: u for u in User.objects.filter(pk__in=usuario_ids).values(*campos_usuario)
    }
    setor_ids |= {u["setor_id"] for u in dados_usuarios.values()}
    dados_setores = {
        s["pk"]: s
        for s in Setor.objects.filter(pk__in=setor_ids).values(
            "pk", "nome", "ativo", "almoxarifado"
        )
    }
    papeis = defaultdict(set)
    for usuario_id, papel in PapelUsuario.objects.filter(usuario_id__in=usuario_ids).values_list(
        "usuario_id", "papel"
    ):
        papeis[usuario_id].add(Papel(papel))

    for u in dados_usuarios.values():
        _validar_usuario(u, papeis[u["pk"]], dados_setores.get(u["setor_id"]))
    for setor in dados_setores.values():
        membros = [u for u in dados_usuarios.values() if u["setor_id"] == setor["pk"]]
        _validar_setor(setor, membros, papeis)


def _validar_usuario(u, papeis, setor):
    quem = f"A conta {u['matricula']}"
    if u["is_superuser"]:
        if papeis:
            raise _recusar(
                f"{quem} é uma conta técnica e não pode ter papel de negócio.",
                "Remova os papéis da conta técnica.",
            )
        return
    if u["is_active"] and Papel.REQUISITANTE not in papeis:
        raise _recusar(
            f"{quem} está ativa e precisa do papel de requisitante.",
            "Toda conta ativa é requisitante.",
        )
    if papeis & PAPEIS_ALMOXARIFADO and not (setor and setor["almoxarifado"]):
        raise _recusar(
            f"{quem} tem papel de almoxarifado fora do setor Almoxarifado.",
            "Cadastre ou transfira a conta para o Almoxarifado.",
            codigo=RECUSA_PAPEL_DE_ALMOXARIFADO_FORA_DO_ALMOXARIFADO,
        )
    if (
        u["is_active"]
        and Papel.CHEFE_ALMOXARIFADO in papeis
        and not {Papel.CHEFE_SETOR, Papel.FUNCIONARIO_ALMOXARIFADO} <= papeis
    ):
        raise _recusar(
            f"{quem} é chefe do almoxarifado sem ser chefe do setor Almoxarifado e "
            "funcionário do almoxarifado.",
            "Designe a chefia do Almoxarifado.",
        )


def _recusa_de_chefe_duplicado(nome):
    return OperacaoRecusada(
        f"O setor {nome} já tem chefe.",
        "Use a substituição de chefia na ficha do setor.",
        codigo=RECUSA_SETOR_JA_TEM_CHEFE,
    )


def _requisitos_de_setor_ativo(nome, almoxarifado, chefes, papeis):
    """Os requisitos para o setor estar ATIVO, na ordem em que são verificados: lista de
    `(rotulo, OperacaoRecusada | None)` — `None` quando o requisito está atendido. `chefes` são os
    chefes ativos do próprio setor (`{"pk", "matricula"}`) e `papeis` mapeia `pk` para os papéis.
    É a única fonte da regra: `validar_organizacao` a aplica ao estado final e a prontidão e o
    impedimento de ativar, só de leitura, a aplicam ao estado atual."""
    sem_chefe_unico = len(chefes) != 1
    requisitos = [
        (
            "Chefe ativo designado",
            OperacaoRecusada(
                f"O setor ativo {nome} precisa ter exatamente um chefe ativo.",
                "Designe a chefia antes.",
                codigo=RECUSA_SETOR_SEM_CHEFE,
            )
            if sem_chefe_unico
            else None,
        )
    ]
    if almoxarifado:
        completa = not sem_chefe_unico and (
            PAPEIS_QUE_ACOMPANHAM_O_CHEFE_DO_ALMOXARIFADO <= papeis[chefes[0]["pk"]]
        )
        recusa = None
        if not completa:
            falta_em = "" if sem_chefe_unico else f"; falta em {chefes[0]['matricula']}"
            recusa = OperacaoRecusada(
                "O chefe do Almoxarifado ativo precisa ser chefe do almoxarifado e funcionário "
                f"do almoxarifado{falta_em}.",
                "Designe a chefia do Almoxarifado.",
                codigo=RECUSA_CHEFIA_DE_ESTOQUE_INCOMPLETA,
            )
        requisitos.append(("Chefia de estoque completa", recusa))
    return requisitos


def _validar_setor(setor, membros, papeis):
    chefes = [u for u in membros if u["is_active"] and Papel.CHEFE_SETOR in papeis[u["pk"]]]
    if len(chefes) > 1:
        raise _levantar(_recusa_de_chefe_duplicado(setor["nome"]))
    if setor["ativo"]:
        for _, recusa in _requisitos_de_setor_ativo(
            setor["nome"], setor["almoxarifado"], chefes, papeis
        ):
            if recusa is not None:
                raise _levantar(recusa)


# ---------------------------------------------------------------------------
# Provisionamento técnico (autor nulo, research R15; FR-050, D-23)
# ---------------------------------------------------------------------------


def _exigir_ambiente_de_senha_conhecida():
    # Sob `override_settings` o atributo `SETTINGS_MODULE` some do objeto de
    # configuração (vira None): cai no módulo informado ao processo.
    modulo = settings.SETTINGS_MODULE or os.environ.get("DJANGO_SETTINGS_MODULE")
    if modulo not in AMBIENTES_COM_SENHA_CONHECIDA:
        raise ImproperlyConfigured(
            "Senha conhecida só é aceita em config.settings.development ou "
            "config.settings.test: fora deles a credencial é sempre gerada e entregue "
            "uma vez (FR-031)."
        )


def _exigir_nome_de_setor_livre(nome, *, excluir_pk=None):
    """Recusa o nome já usado por outro setor, sem diferenciar caixa nem espaços nas pontas
    (FR-025; a constraint funcional cobre a corrida, R13). Só dentro de `_operacao()`."""
    repetidos = Setor.objects.annotate(nome_normalizado=Lower(Trim("nome"))).filter(
        nome_normalizado=Lower(Value(nome))
    )
    if excluir_pk is not None:
        repetidos = repetidos.exclude(pk=excluir_pk)
    if repetidos.exists():
        raise _recusar(
            f"Já existe o setor {nome}.",
            "Escolha outro nome; maiúsculas e espaços nas pontas não diferenciam setores.",
        )


def provisionar_setor(nome, *, almoxarifado=False, ativo=False):
    """Cria um setor INATIVO (FR-019 da 002), opcionalmente já designado como o
    Almoxarifado (`INV-ORG-004`). `ativo=True` é recusado: setor novo não tem chefe;
    a ativação é `provisionar_ativacao`."""
    if ativo:
        raise _recusar(
            "Um setor novo não pode nascer ativo: ainda não há chefe ativo.",
            "Crie o setor, provisione o chefe e só então ative.",
        )
    nome = (nome or "").strip()
    with _operacao():
        if not nome:
            raise _recusar("Informe o nome do setor.")
        _exigir_nome_de_setor_livre(nome)
        if almoxarifado and Setor.objects.filter(almoxarifado=True).exists():
            raise _recusar(
                "Já existe um setor designado como Almoxarifado.",
                "O Almoxarifado é único e imutável.",
            )
        setor = Setor.objects.create(nome=nome, almoxarifado=almoxarifado)
        validar_organizacao([setor], [])
        _registrar_evento(
            None,
            TipoEvento.SETOR_CRIADO,
            setor=setor,
            dados={"nome": setor.nome, "almoxarifado": almoxarifado},
        )
    return setor


def _exigir_dados_do_usuario(matricula, nome, setor_id):
    """Recusas de dados do cadastro, comuns ao provisionamento e ao cadastro pelo
    administrador. Devolve o `Setor` lido sob o lock. Só dentro de `_operacao()`."""
    if not matricula:
        raise _recusar("Informe a matrícula.")
    if not nome:
        raise _recusar("Informe o nome.")
    if len(matricula) > User._meta.get_field("matricula").max_length:
        raise _recusar("A matrícula é longa demais.")
    if len(nome) > User._meta.get_field("nome").max_length:
        raise _recusar("O nome é longo demais.")
    if setor_id is None:
        raise _recusar("Informe o setor.")
    setor = Setor.objects.filter(pk=setor_id).first()
    if setor is None:
        raise _recusar("O setor não existe.")
    if User.objects.filter(matricula=matricula).exists():
        raise _recusar("Matrícula já usada por outra conta.", codigo=RECUSA_MATRICULA_EM_USO)
    return setor


def _papeis_adicionais(papeis):
    try:
        return {Papel(papel) for papel in papeis} - {Papel.REQUISITANTE}
    except ValueError as exc:
        raise _recusar("Papel desconhecido.") from exc


def _recusa_de_papel_no_cadastro(setor, papel):
    """A `OperacaoRecusada` que dar `papel` a quem se cadastra em `setor` daria, ou `None`, no
    tempo verbal do cadastro. Só lê: serve a `cadastrar_usuario` (sob o lock) e ao formulário, que
    mostra por setor quais papéis ficam bloqueados. O estado final continua validado por
    `validar_organizacao`."""
    if papel in PAPEIS_ALMOXARIFADO and not setor.almoxarifado:
        return OperacaoRecusada(
            "Os papéis de almoxarifado só podem ser dados a quem é do setor Almoxarifado.",
            "Escolha o setor Almoxarifado ou desmarque o papel.",
            codigo=RECUSA_PAPEL_DE_ALMOXARIFADO_FORA_DO_ALMOXARIFADO,
        )
    if papel == Papel.CHEFE_SETOR and (
        setor.ativo or chefes_ativos(setor.pk).filter(is_superuser=False).exists()
    ):
        return _recusa_de_chefe_duplicado(setor.nome)
    return None


def bloqueios_de_papeis_no_cadastro(setor):
    """`{Papel: OperacaoRecusada}` dos papéis adicionais que o cadastro em `setor` recusaria
    hoje. Só lê; a decisão final é de `cadastrar_usuario`."""
    bloqueios = {}
    for papel in Papel:
        if papel == Papel.REQUISITANTE:
            continue
        recusa = _recusa_de_papel_no_cadastro(setor, papel)
        if recusa is not None:
            bloqueios[papel] = recusa
    return bloqueios


def _gravar_usuario(
    autor,
    matricula,
    nome,
    setor,
    adicionais,
    *,
    senha,
    is_active=True,
    motivo,
    chave_confirmacao=None,
):
    """Cria a identidade de negócio, valida o estado final e grava os eventos. Só dentro de
    `_operacao()`. `senha=None` gera a provisória (`senha_provisoria_em` agora); com `senha`,
    grava a credencial definitiva. Devolve `(usuario, senha)`."""
    provisoria = senha is None
    if provisoria:
        senha = gerar_senha_provisoria()
    usuario = User.objects.create_user(
        matricula,
        password=senha,
        setor=setor,
        nome=nome,
        is_active=is_active,
        senha_provisoria_em=timezone.now() if provisoria else None,
    )
    for papel in sorted(adicionais):
        PapelUsuario.objects.create(usuario=usuario, papel=papel)
    validar_organizacao([setor], [usuario])
    _registrar_evento(
        autor,
        TipoEvento.USUARIO_CADASTRADO,
        usuario=usuario,
        setor=setor,
        dados={
            "matricula": usuario.matricula,
            "nome": usuario.nome,
            "setor": setor.nome,
            "papeis": sorted({Papel.REQUISITANTE, *adicionais}),
        },
        chave_confirmacao=chave_confirmacao,
    )
    _registrar_evento(
        autor,
        TipoEvento.SENHA_PROVISORIA_GERADA if provisoria else TipoEvento.SENHA_DEFINIDA,
        usuario=usuario,
        dados={"motivo": motivo},
    )
    return usuario, senha


def provisionar_usuario(matricula, nome, setor, papeis, *, senha=None, is_active=True):
    """Cria uma identidade de negócio e devolve `(usuario, senha)`.

    `papeis` são os adicionais: `ROLE-REQUESTER` é sempre concedido (FR-016a) e nenhum
    papel de chefia é completado sozinho — o estado final é validado e a conta que o
    violaria não nasce. Sem `senha`, gera a provisória (`senha_provisoria_em`
    preenchido, 7 dias); com `senha` (só desenvolvimento e testes, recusada antes de
    gravar nos demais ambientes), grava a credencial definitiva.
    """
    if senha is not None:
        _exigir_ambiente_de_senha_conhecida()
    # Mesma normalização do cadastro: o login remove espaços nas pontas da matrícula digitada.
    matricula = (matricula or "").strip()
    nome = (nome or "").strip()
    adicionais = _papeis_adicionais(papeis)
    with _operacao():
        setor = _exigir_dados_do_usuario(matricula, nome, setor.pk)
        return _gravar_usuario(
            None,
            matricula,
            nome,
            setor,
            adicionais,
            senha=senha,
            is_active=is_active,
            motivo="provisionamento" if senha is None else "provisionamento_desenvolvimento",
        )


# ---------------------------------------------------------------------------
# Operações sobre usuários (autor = o administrador; contracts/operacoes-organizacionais.md)
# ---------------------------------------------------------------------------


def cadastrar_usuario(autor, *, matricula, nome, setor_id, papeis_adicionais, chave_confirmacao):
    """Cadastra uma identidade de negócio ativa com senha provisória e devolve
    `(usuario, senha_provisoria)` — a única vez em que a senha existe em claro (FR-031).

    `ROLE-REQUESTER` é sempre concedido (FR-016a). No Almoxarifado, `ROLE-SECTOR-HEAD` implica
    a designação completa (`ROLE-WAREHOUSE-HEAD` e `ROLE-WAREHOUSE-STAFF`, `INV-ORG-006`);
    qualquer outra combinação que violaria uma invariante é recusada pela validação do estado
    final. A mesma `chave_confirmacao` já efetivada levanta `OperacaoJaExecutada` antes de
    qualquer outra checagem (R8); recusa não consome a chave. A autorização do `autor` é da
    view.
    """
    matricula = (matricula or "").strip()
    nome = (nome or "").strip()
    adicionais = _papeis_adicionais(papeis_adicionais)
    if chave_confirmacao is None:
        raise _recusar("A operação não tem chave de confirmação.")
    with _operacao():
        anterior = EventoOrganizacional.objects.filter(chave_confirmacao=chave_confirmacao).first()
        if anterior is not None:
            logger.info("Operação organizacional repetida: chave já executada.")
            raise OperacaoJaExecutada(anterior)
        setor = _exigir_dados_do_usuario(matricula, nome, setor_id)
        for papel in _em_ordem_do_catalogo(adicionais):
            recusa = _recusa_de_papel_no_cadastro(setor, papel)
            if recusa is not None:
                raise _levantar(recusa)
        if setor.almoxarifado and Papel.CHEFE_SETOR in adicionais:
            adicionais |= PAPEIS_QUE_ACOMPANHAM_O_CHEFE_DO_ALMOXARIFADO
        return _gravar_usuario(
            autor,
            matricula,
            nome,
            setor,
            adicionais,
            senha=None,
            motivo="cadastro",
            chave_confirmacao=chave_confirmacao,
        )


def _ativar_sob_o_lock(autor, setor):
    """Ativa o setor lido sob o lock (preenche `ativado_em` na primeira vez). Exige exatamente um
    chefe ativo do próprio setor — e, no Almoxarifado, a chefia de estoque (`INV-ORG-006`): é a
    validação do estado final que recusa, sem escrita. Setor já ativo: sem efeito, sem evento."""
    if setor.ativo:
        return setor
    primeira_ativacao = setor.ativado_em is None
    if primeira_ativacao:
        setor.ativado_em = timezone.now()
    setor.ativo = True
    setor.save(update_fields=["ativo", "ativado_em"])
    validar_organizacao([setor], [])
    chefe = User.objects.filter(
        setor=setor, is_active=True, papeis__papel=Papel.CHEFE_SETOR
    ).first()
    _registrar_evento(
        autor,
        TipoEvento.SETOR_ATIVADO,
        setor=setor,
        dados={
            "chefe": chefe.matricula if chefe else None,
            "primeira_ativacao": primeira_ativacao,
        },
    )
    return setor


def provisionar_ativacao(setor):
    """Ativa o setor sem autor (provisionamento técnico)."""
    with _operacao():
        return _ativar_sob_o_lock(None, Setor.objects.get(pk=setor.pk))


# ---------------------------------------------------------------------------
# Manutenção de dados, papéis e vínculo setorial (US3)
# ---------------------------------------------------------------------------


def _em_ordem_do_catalogo(papeis):
    return tuple(papel for papel in Papel if papel in papeis)


def _codigos(papeis):
    return sorted(papel.value for papel in papeis)


def _usuario_de_negocio(usuario_id):
    """Identidade de negócio com o setor carregado; a conta técnica não é administrada (FR-004)."""
    usuario = User.objects.select_related("setor").filter(pk=usuario_id, is_superuser=False).first()
    if usuario is None:
        raise _recusar("O usuário não existe.")
    return usuario


def _setor_existente(setor_id):
    setor = Setor.objects.filter(pk=setor_id).first()
    if setor is None:
        raise _recusar("O setor não existe.")
    return setor


def _conceder(usuario, papeis):
    for papel in _em_ordem_do_catalogo(papeis):
        PapelUsuario.objects.create(usuario=usuario, papel=papel)


def _retirar(usuario, papeis):
    if papeis:
        PapelUsuario.objects.filter(usuario=usuario, papel__in=papeis).delete()


def editar_usuario(autor, usuario_id, *, nome=None, matricula=None):
    """Altera nome e/ou matrícula (correção de digitação, FR-009). `None` é "não informado";
    informar o valor atual não é mudança e não gera evento. A matrícula nova obedece à mesma
    unicidade do cadastro; o evento guarda só o que mudou, com o valor anterior."""
    nome = None if nome is None else nome.strip()
    matricula = None if matricula is None else matricula.strip()
    with _operacao():
        usuario = _usuario_de_negocio(usuario_id)
        anterior, novo = {}, {}
        if nome is not None:
            if not nome:
                raise _recusar("Informe o nome.")
            if len(nome) > User._meta.get_field("nome").max_length:
                raise _recusar("O nome é longo demais.")
            if nome != usuario.nome:
                anterior["nome"], novo["nome"] = usuario.nome, nome
        if matricula is not None:
            if not matricula:
                raise _recusar("Informe a matrícula.")
            if len(matricula) > User._meta.get_field("matricula").max_length:
                raise _recusar("A matrícula é longa demais.")
            if matricula != usuario.matricula:
                if User.objects.filter(matricula=matricula).exclude(pk=usuario.pk).exists():
                    raise _recusar(
                        "Matrícula já usada por outra conta.",
                        "Confira a matrícula; para achar a conta que a usa, busque-a na lista de "
                        "usuários.",
                    )
                anterior["matricula"], novo["matricula"] = usuario.matricula, matricula
        if not novo:
            return usuario
        for campo, valor in novo.items():
            setattr(usuario, campo, valor)
        usuario.save(update_fields=list(novo))
        validar_organizacao([usuario.setor], [usuario])
        _registrar_evento(
            autor,
            TipoEvento.USUARIO_EDITADO,
            usuario=usuario,
            dados={"anterior": anterior, "novo": novo},
        )
    return usuario


def _recusa_de_mudanca_de_papeis(usuario, atuais, conceder, remover):
    """Primeira regra própria de `alterar_papeis` que a mudança efetiva violaria, ou `None`.
    Só lê: serve à operação (sob o lock) e à tela, que mostra o motivo de cada papel bloqueado.
    O estado final continua validado por `validar_organizacao` depois da escrita."""
    if Papel.REQUISITANTE in remover and usuario.is_active:
        return OperacaoRecusada(
            "Toda conta ativa é requisitante.",
            "Mantenha o papel de requisitante enquanto a conta estiver ativa.",
        )
    if Papel.CHEFE_SETOR in conceder | remover:
        return OperacaoRecusada(
            "A chefia de setor não muda pela edição de papéis.",
            "Designe, retire ou substitua a chefia na ficha do setor.",
        )
    if Papel.CHEFE_ALMOXARIFADO in conceder | remover:
        return OperacaoRecusada(
            "O papel de chefe do almoxarifado acompanha a chefia do setor Almoxarifado.",
            "Designe ou substitua a chefia na ficha do setor Almoxarifado.",
        )
    if Papel.FUNCIONARIO_ALMOXARIFADO in conceder and not usuario.setor.almoxarifado:
        return OperacaoRecusada(
            "O papel de funcionário do almoxarifado só vale no setor Almoxarifado.",
            "Transfira o usuário para o Almoxarifado antes.",
        )
    if (
        Papel.FUNCIONARIO_ALMOXARIFADO in remover
        and usuario.is_active
        and Papel.CHEFE_ALMOXARIFADO in atuais
    ):
        return OperacaoRecusada(
            "O chefe do Almoxarifado precisa ser funcionário do almoxarifado.",
            "Substitua a chefia do Almoxarifado antes.",
        )
    if (
        Papel.ADMINISTRADOR_SISTEMA in remover
        and usuario.is_active
        and not _administradores_ativos().exclude(pk=usuario.pk).exists()
    ):
        return OperacaoRecusada(
            "É o último administrador de sistema ativo.", "Conceda o papel a outra pessoa antes."
        )
    return None


def bloqueios_de_papeis(usuario):
    """`{Papel: OperacaoRecusada}` dos papéis cuja alternância (conceder o que falta, remover o
    que tem) `alterar_papeis` recusaria hoje. Só lê; a decisão final é da operação."""
    atuais = _papeis(usuario)
    bloqueios = {}
    for papel in Papel:
        conceder, remover = (set(), {papel}) if papel in atuais else ({papel}, set())
        recusa = _recusa_de_mudanca_de_papeis(usuario, atuais, conceder, remover)
        if recusa is not None:
            bloqueios[papel] = recusa
    return bloqueios


def alterar_papeis(autor, usuario_id, *, conceder, remover):
    """Concede e remove papéis num só passo (FR-010, FR-011). Vale a mudança EFETIVA: conceder
    o que a conta já tem ou remover o que não tem não conta e, sem mudança, não há escrita nem
    evento. Tudo ou nada: uma recusa desfaz o pedido inteiro. `ROLE-SECTOR-HEAD` e
    `ROLE-WAREHOUSE-HEAD` nunca mudam por aqui — são designação, retirada e substituição."""
    try:
        conceder = {Papel(papel) for papel in conceder}
        remover = {Papel(papel) for papel in remover}
    except ValueError as exc:
        raise _recusar("Papel desconhecido.") from exc
    if conceder & remover:
        raise _recusar("Um papel não pode ser concedido e removido ao mesmo tempo.")
    with _operacao():
        usuario = _usuario_de_negocio(usuario_id)
        atuais = _papeis(usuario)
        conceder, remover = conceder - atuais, remover & atuais
        if not conceder and not remover:
            return usuario
        recusa = _recusa_de_mudanca_de_papeis(usuario, atuais, conceder, remover)
        if recusa is not None:
            raise _recusar(recusa.motivo, recusa.caminho)
        _conceder(usuario, conceder)
        _retirar(usuario, remover)
        validar_organizacao([usuario.setor], [usuario])
        _registrar_evento(
            autor,
            TipoEvento.PAPEIS_ALTERADOS,
            usuario=usuario,
            setor=usuario.setor,
            dados={
                "anterior": {"papeis": _codigos(atuais)},
                "novo": {"papeis": _codigos((atuais | conceder) - remover)},
            },
        )
    return usuario


def _calcular_transferencia(usuario_id, setor_destino_id):
    """Recusas e efeitos da transferência. Só lê; devolve `(usuario, destino, atuais,
    papeis_removidos)`."""
    usuario = _usuario_de_negocio(usuario_id)
    destino = _setor_existente(setor_destino_id)
    if destino.pk == usuario.setor_id:
        raise _recusar("O usuário já pertence a este setor.", "Escolha outro setor de destino.")
    atuais = _papeis(usuario)
    recusa = _recusa_de_deixar_a_chefia_do_setor_ativo(usuario, atuais)
    if recusa is not None:
        raise _levantar(recusa)
    return usuario, destino, atuais, _em_ordem_do_catalogo(atuais & PAPEIS_PRESOS_AO_SETOR)


def _recusa_de_deixar_a_chefia_do_setor_ativo(usuario, atuais):
    """A recusa de quem é o chefe ativo de um setor ATIVO sair dele (transferido ou desativado),
    ou `None`. Só lê; `usuario.setor` precisa estar carregado."""
    if usuario.is_active and Papel.CHEFE_SETOR in atuais and usuario.setor.ativo:
        return OperacaoRecusada(
            f"{usuario.nome} é o chefe do setor ativo {usuario.setor.nome}.",
            "Substitua a chefia do setor antes.",
            codigo=RECUSA_CHEFE_DE_SETOR_ATIVO,
        )
    return None


def impedimento_de_transferir_usuario(usuario):
    """A `OperacaoRecusada` que transferir `usuario` para qualquer setor daria por quem ele é —
    o chefe de um setor ativo —, ou `None`. Só lê (sem destino, sem escrita); a decisão final é de
    `transferir_usuario`, sob o lock."""
    return _recusa_de_deixar_a_chefia_do_setor_ativo(usuario, _papeis(usuario))


def previa_transferencia(usuario_id, setor_destino_id):
    """O que a transferência removeria, sem escrever (FR-049). Recusa o que ela recusaria."""
    usuario, destino, _, removidos = _calcular_transferencia(usuario_id, setor_destino_id)
    return PreviaTransferencia(usuario, destino, removidos)


def transferir_usuario(autor, usuario_id, setor_destino_id, *, papeis_removidos_previstos):
    """Muda o setor do usuário e remove, de forma explícita, os papéis presos ao setor de
    origem; não concede nada no destino (FR-013). `papeis_removidos_previstos` são os que a
    prévia mostrou: se os efeitos recalculados sob o lock forem outros, levanta
    `PreviaDesatualizada` com a prévia nova, sem escrever (FR-049)."""
    try:
        previstos = {Papel(papel) for papel in papeis_removidos_previstos}
    except ValueError as exc:
        raise _recusar("Papel desconhecido.") from exc
    with _operacao():
        usuario, destino, atuais, removidos = _calcular_transferencia(usuario_id, setor_destino_id)
        if set(removidos) != previstos:
            logger.info("Prévia de transferência desatualizada.")
            raise PreviaDesatualizada(PreviaTransferencia(usuario, destino, removidos))
        origem = usuario.setor
        _retirar(usuario, set(removidos))
        usuario.setor = destino
        usuario.save(update_fields=["setor"])
        validar_organizacao([origem, destino], [usuario])
        anterior, novo = {"setor": origem.nome}, {"setor": destino.nome}
        if removidos:
            anterior["papeis"] = _codigos(atuais)
            novo["papeis"] = _codigos(atuais - set(removidos))
        _registrar_evento(
            autor,
            TipoEvento.USUARIO_TRANSFERIDO,
            usuario=usuario,
            setor=destino,
            setor_relacionado=origem,
            dados={"anterior": anterior, "novo": novo},
        )
    return usuario


# ---------------------------------------------------------------------------
# Chefia do setor (US4): designar, retirar e substituir
# ---------------------------------------------------------------------------


def _papeis_da_chefia(setor):
    """Papéis que acompanham a chefia: o de chefe de setor e, no Almoxarifado, a chefia de
    estoque (FR-012, FR-016)."""
    papeis = {Papel.CHEFE_SETOR}
    if setor.almoxarifado:
        papeis.add(Papel.CHEFE_ALMOXARIFADO)
    return papeis


def designar_chefia(autor, setor_id, usuario_id):
    """Designa o chefe de um setor INATIVO sem chefe ativo, entre os membros ativos do setor
    (FR-012). No Almoxarifado concede também `ROLE-WAREHOUSE-HEAD` e, se faltar,
    `ROLE-WAREHOUSE-STAFF`. Designar não ativa o setor."""
    with _operacao():
        setor = _setor_existente(setor_id)
        if setor.ativo:
            raise _recusar(
                f"O setor {setor.nome} está ativo: a chefia só muda por substituição.",
                "Use a substituição de chefia na ficha do setor.",
            )
        if chefes_ativos(setor.pk).exists():
            raise _recusar(
                f"O setor {setor.nome} já tem chefe ativo.",
                "Retire a chefia antes de designar outra pessoa.",
            )
        usuario = _usuario_de_negocio(usuario_id)
        if usuario.setor_id != setor.pk:
            raise _recusar(
                f"{usuario.nome} não é do setor {setor.nome}.",
                "Transfira o usuário para o setor antes.",
            )
        if not usuario.is_active:
            raise _recusar(f"{usuario.nome} está inativo.", "Designe um membro ativo do setor.")
        atuais = _papeis(usuario)
        alvo = _papeis_da_chefia(setor)
        if setor.almoxarifado:
            alvo.add(Papel.FUNCIONARIO_ALMOXARIFADO)
        concedidos = alvo - atuais
        _conceder(usuario, concedidos)
        validar_organizacao([setor], [usuario])
        _registrar_evento(
            autor,
            TipoEvento.CHEFIA_DESIGNADA,
            usuario=usuario,
            setor=setor,
            dados={
                "anterior": {"chefe": None},
                "novo": {"chefe": usuario.matricula},
                "papeis_concedidos": _codigos(concedidos),
            },
        )
    return usuario


def retirar_chefia(autor, setor_id):
    """Retira a chefia de um setor INATIVO; no Almoxarifado, junto com `ROLE-WAREHOUSE-HEAD`
    (FR-012). O ex-chefe continua no setor com os demais papéis."""
    with _operacao():
        setor = _setor_existente(setor_id)
        if setor.ativo:
            raise _recusar(
                f"O setor {setor.nome} está ativo: o setor não pode ficar sem chefe.",
                "Use a substituição de chefia na ficha do setor.",
            )
        chefe = chefes_ativos(setor.pk).filter(is_superuser=False).first()
        if chefe is None:
            raise _recusar(f"O setor {setor.nome} não tem chefe ativo.")
        retirados = _papeis(chefe) & _papeis_da_chefia(setor)
        _retirar(chefe, retirados)
        validar_organizacao([setor], [chefe])
        _registrar_evento(
            autor,
            TipoEvento.CHEFIA_RETIRADA,
            usuario=chefe,
            setor=setor,
            dados={
                "anterior": {"chefe": chefe.matricula},
                "novo": {"chefe": None},
                "papeis_retirados": _codigos(retirados),
            },
        )
    return chefe


def _calcular_substituicao(setor_id, novo_chefe_id, chefe_esperado_id=None):
    """Recusas e efeitos da substituição. Só lê; devolve `(setor, atual, novo, ganha, perde)`
    (conjuntos). `chefe_esperado_id` é conferido quando informado (FR-017)."""
    setor = _setor_existente(setor_id)
    if not setor.ativo:
        raise _recusar(
            f"O setor {setor.nome} está inativo: não há chefe ativo a substituir.",
            "Use a designação de chefia na ficha do setor.",
        )
    atual = chefes_ativos(setor.pk).filter(is_superuser=False).first()
    if atual is None or (chefe_esperado_id is not None and atual.pk != chefe_esperado_id):
        raise _recusar(
            "A chefia mudou desde que você abriu esta tela.", "Confira o chefe atual e repita."
        )
    novo = _usuario_de_negocio(novo_chefe_id)
    if novo.pk == atual.pk:
        raise _recusar(f"{novo.nome} já é o chefe do setor {setor.nome}.")
    if novo.setor_id != setor.pk:
        raise _recusar(
            f"{novo.nome} não é do setor {setor.nome}.",
            "Transfira o usuário para o setor antes.",
        )
    if not novo.is_active:
        raise _recusar(f"{novo.nome} está inativo.", "Escolha um membro ativo do setor.")
    chefia = _papeis_da_chefia(setor)
    ganha = chefia | {Papel.FUNCIONARIO_ALMOXARIFADO} if setor.almoxarifado else chefia
    return setor, atual, novo, ganha - _papeis(novo), chefia & _papeis(atual)


def previa_substituicao(setor_id, novo_chefe_id):
    """O que a substituição daria e tiraria de cada pessoa, sem escrever (FR-049). Recusa o que
    ela recusaria quanto ao setor e ao novo chefe."""
    setor, atual, novo, ganha, perde = _calcular_substituicao(setor_id, novo_chefe_id)
    return PreviaSubstituicao(
        setor, atual, novo, _em_ordem_do_catalogo(ganha), _em_ordem_do_catalogo(perde)
    )


def substituir_chefia(
    autor,
    setor_id,
    *,
    chefe_esperado_id,
    novo_chefe_id,
    novo_ganha_previsto=None,
    anterior_perde_previsto=None,
):
    """Troca o chefe de um setor ATIVO numa só operação (FR-014): o novo recebe a chefia, o
    anterior a perde e segue ativo no setor com os demais papéis. No Almoxarifado a chefia de
    estoque vai junto e o novo chefe recebe `ROLE-WAREHOUSE-STAFF` se faltar (FR-016). Recusada
    se o chefe esperado já não for o chefe (FR-017). O estado final só é validado depois de
    mover os papéis (R3): o intermediário tem dois chefes ou nenhum, nunca visível.

    `novo_ganha_previsto` e `anterior_perde_previsto` são os efeitos que a prévia mostrou
    (opcionais; quando informados, são conferidos): se os efeitos recalculados sob o lock forem
    outros, levanta `PreviaDesatualizada` com a prévia nova, sem escrever (FR-049)."""
    try:
        previstos = {
            nome: None if valor is None else {Papel(papel) for papel in valor}
            for nome, valor in (
                ("ganha", novo_ganha_previsto),
                ("perde", anterior_perde_previsto),
            )
        }
    except ValueError as exc:
        raise _recusar("Papel desconhecido.") from exc
    with _operacao():
        setor, atual, novo, ganha, perde = _calcular_substituicao(
            setor_id, novo_chefe_id, chefe_esperado_id
        )
        if (previstos["ganha"] is not None and previstos["ganha"] != ganha) or (
            previstos["perde"] is not None and previstos["perde"] != perde
        ):
            logger.info("Prévia de substituição de chefia desatualizada.")
            raise PreviaDesatualizada(
                PreviaSubstituicao(
                    setor,
                    atual,
                    novo,
                    _em_ordem_do_catalogo(ganha),
                    _em_ordem_do_catalogo(perde),
                )
            )
        _conceder(novo, ganha)
        _retirar(atual, perde)
        validar_organizacao([setor], [novo, atual])
        _registrar_evento(
            autor,
            TipoEvento.CHEFIA_SUBSTITUIDA,
            usuario=novo,
            usuario_relacionado=atual,
            setor=setor,
            dados={
                "anterior": {"chefe": atual.matricula},
                "novo": {"chefe": novo.matricula},
                "novo_chefe_recebeu": _codigos(ganha),
                "chefe_anterior_perdeu": _codigos(perde),
            },
        )
    return novo


# ---------------------------------------------------------------------------
# Situação do usuário (US5): desativar e reativar
# ---------------------------------------------------------------------------


def _recusa_de_desativar_usuario(autor, usuario, atuais):
    """A primeira regra de `desativar_usuario` que desativar a conta ativa `usuario` violaria, ou
    `None`: a própria conta do autor, o último administrador ativo e o chefe de setor ativo.
    Só lê; `usuario.setor` precisa estar carregado."""
    if usuario.pk == autor.pk:
        return OperacaoRecusada(
            "O administrador não pode desativar a própria conta.",
            "Peça a outro administrador.",
            codigo=RECUSA_PROPRIA_CONTA,
        )
    if (
        Papel.ADMINISTRADOR_SISTEMA in atuais
        and not _administradores_ativos().exclude(pk=usuario.pk).exists()
    ):
        return OperacaoRecusada(
            "É o último administrador de sistema ativo.",
            "Conceda o papel a outra pessoa antes.",
            codigo=RECUSA_ULTIMO_ADMINISTRADOR,
        )
    return _recusa_de_deixar_a_chefia_do_setor_ativo(usuario, atuais)


def impedimento_de_desativar_usuario(autor, usuario):
    """A `OperacaoRecusada` que `desativar_usuario(autor, usuario.pk)` levantaria hoje, ou `None`
    (inclusive para conta já inativa, que a operação não recusa: não faz nada). Só lê; a decisão
    final é da operação, sob o lock."""
    if not usuario.is_active:
        return None
    return _recusa_de_desativar_usuario(autor, usuario, _papeis(usuario))


def desativar_usuario(autor, usuario_id, *, justificativa=""):
    """Desativa a conta e preserva todos os papéis (FR-019); o acesso cessa na interação seguinte
    (`INV-AUTH-001`). Recusa a própria conta do autor, o último administrador ativo (D-15) e o chefe
    de setor ativo (FR-020). Nunca consulta registros de outro recorte (FR-021). Conta já inativa:
    sem efeito, sem evento. `justificativa` é opcional e tem campo próprio no evento."""
    justificativa = (justificativa or "").strip()
    with _operacao():
        usuario = _usuario_de_negocio(usuario_id)
        if not usuario.is_active:
            return usuario
        recusa = _recusa_de_desativar_usuario(autor, usuario, _papeis(usuario))
        if recusa is not None:
            raise _levantar(recusa)
        usuario.is_active = False
        usuario.save(update_fields=["is_active"])
        validar_organizacao([usuario.setor], [usuario])
        _registrar_evento(
            autor,
            TipoEvento.USUARIO_DESATIVADO,
            usuario=usuario,
            setor=usuario.setor,
            dados={"anterior": {"situacao": "ativo"}, "novo": {"situacao": "inativo"}},
            justificativa=justificativa,
        )
    return usuario


_RECUSA_REATIVACAO_SEM_REQUISITANTE = (
    "A conta não tem o papel de requisitante, e toda conta ativa é requisitante.",
    "Conceda o papel de requisitante na tela de papéis antes de reativar.",
)


def _recusa_de_papel_na_reativacao(usuario, papel):
    """A `OperacaoRecusada` que manter `papel` na reativação daria, ou `None`. Só lê. A conta
    ainda está inativa, então os chefes ativos do setor são sempre de outra pessoa."""
    desmarcar = "Desmarque o papel para prosseguir."
    setor = usuario.setor
    if papel in (Papel.CHEFE_SETOR, Papel.CHEFE_ALMOXARIFADO):
        outro = chefes_ativos(setor.pk).filter(is_superuser=False).first()
        if outro is not None:
            return OperacaoRecusada(
                f"O setor {setor.nome} já tem outro chefe ativo, {outro.nome}.",
                desmarcar,
            )
    if papel in PAPEIS_ALMOXARIFADO and not setor.almoxarifado:
        return OperacaoRecusada(
            f"{papel.label} só vale no setor Almoxarifado, e a conta é do setor {setor.nome}.",
            desmarcar,
        )
    return None


def _calcular_reativacao(usuario_id):
    """`(usuario, preservados, recusas)`: os papéis que a conta tem hoje, em ordem do catálogo, e
    a recusa de cada um que, mantido, violaria uma regra. Só lê."""
    usuario = _usuario_de_negocio(usuario_id)
    preservados = _em_ordem_do_catalogo(_papeis(usuario))
    recusas = {}
    for papel in preservados:
        recusa = _recusa_de_papel_na_reativacao(usuario, papel)
        if recusa is not None:
            recusas[papel] = recusa
    return usuario, preservados, recusas


def previa_reativacao(usuario_id):
    """Os papéis preservados que voltariam a valer e o motivo de cada um que seria recusado, sem
    escrever (FR-023, FR-049). A decisão final é de `reativar_usuario`, sob o lock."""
    usuario, preservados, recusas = _calcular_reativacao(usuario_id)
    return PreviaReativacao(usuario, preservados, recusas)


def reativar_usuario(autor, usuario_id, *, papeis_mantidos):
    """Reativa a conta com EXATAMENTE os papéis confirmados em `papeis_mantidos` (FR-023): os
    preservados desmarcados são removidos. `ROLE-REQUESTER` é sempre mantido, e um papel que a
    conta não tem nunca é concedido — nem pedido por engano nem por POST forjado. Papel mantido
    que violaria uma regra é recusado com o motivo da prévia (FR-024); o estado final é validado
    antes do evento. A credencial não muda. Conta já ativa: sem efeito, sem evento."""
    try:
        mantidos = {Papel(papel) for papel in papeis_mantidos}
    except ValueError as exc:
        raise _recusar("Papel desconhecido.") from exc
    with _operacao():
        usuario, preservados, recusas = _calcular_reativacao(usuario_id)
        if usuario.is_active:
            return usuario
        if Papel.REQUISITANTE not in preservados:
            raise _recusar(*_RECUSA_REATIVACAO_SEM_REQUISITANTE)
        if Papel.REQUISITANTE not in mantidos:
            raise _recusar(
                "Toda conta ativa é requisitante.",
                "Mantenha o papel de requisitante para reativar.",
            )
        alheios = mantidos - set(preservados)
        if alheios:
            raise _recusar(
                "Os papéis da conta mudaram desde a revisão: "
                + ", ".join(papel.label for papel in _em_ordem_do_catalogo(alheios))
                + " já não estão entre os preservados.",
                "Abra a revisão de novo.",
            )
        for papel in preservados:
            if papel in mantidos and papel in recusas:
                raise _recusar(recusas[papel].motivo, recusas[papel].caminho)
        desmarcados = set(preservados) - mantidos
        _retirar(usuario, desmarcados)
        usuario.is_active = True
        usuario.save(update_fields=["is_active"])
        validar_organizacao([usuario.setor], [usuario])
        _registrar_evento(
            autor,
            TipoEvento.USUARIO_REATIVADO,
            usuario=usuario,
            setor=usuario.setor,
            dados={
                "anterior": {"situacao": "inativo"},
                "novo": {"situacao": "ativo"},
                "papeis_preservados": _codigos(preservados),
                "papeis_confirmados": _codigos(mantidos),
                "papeis_desmarcados": _codigos(desmarcados),
            },
        )
    return usuario


# ---------------------------------------------------------------------------
# Redefinição de senha (US6)
# ---------------------------------------------------------------------------


def redefinir_senha(autor, usuario_id, *, chave_confirmacao):
    """Grava uma nova senha provisória para a conta e devolve a senha em claro — a única vez em
    que ela existe fora do hash (FR-031). O hash muda, então toda sessão da conta cai na
    interação seguinte (R11), inclusive a do administrador que redefine a própria. A mesma
    `chave_confirmacao` já efetivada levanta `OperacaoJaExecutada` antes de qualquer outra
    checagem (R8); recusa não consome a chave. O administrador nunca escolhe a senha (D-13)."""
    if chave_confirmacao is None:
        raise _recusar("A operação não tem chave de confirmação.")
    with _operacao():
        anterior = EventoOrganizacional.objects.filter(chave_confirmacao=chave_confirmacao).first()
        if anterior is not None:
            logger.info("Operação organizacional repetida: chave já executada.")
            raise OperacaoJaExecutada(anterior)
        usuario = _usuario_de_negocio(usuario_id)
        senha = gerar_senha_provisoria()
        usuario.set_password(senha)
        usuario.senha_provisoria_em = timezone.now()
        usuario.save(update_fields=["password", "senha_provisoria_em"])
        _registrar_evento(
            autor,
            TipoEvento.SENHA_PROVISORIA_GERADA,
            usuario=usuario,
            dados={"motivo": "redefinicao"},
            chave_confirmacao=chave_confirmacao,
        )
    return senha


# ---------------------------------------------------------------------------
# Administração de setores (US7)
# ---------------------------------------------------------------------------


def _nome_de_setor_valido(nome):
    """O nome sem espaços nas pontas, ou a recusa de domínio (nunca um erro do banco)."""
    nome = (nome or "").strip()
    if not nome:
        raise _recusar("Informe o nome do setor.")
    limite = Setor._meta.get_field("nome").max_length
    if len(nome) > limite:
        raise _recusar(f"O nome do setor é longo demais (no máximo {limite} caracteres).")
    return nome


def criar_setor(autor, *, nome):
    """Cria um setor INATIVO e nunca designado como Almoxarifado (FR-026): o nome é único sem
    diferenciar caixa nem espaços nas pontas (FR-025). A chefia vem depois (`designar_chefia`),
    e só então a ativação."""
    with _operacao():
        nome = _nome_de_setor_valido(nome)
        _exigir_nome_de_setor_livre(nome)
        setor = Setor.objects.create(nome=nome)
        validar_organizacao([setor], [])
        _registrar_evento(
            autor,
            TipoEvento.SETOR_CRIADO,
            setor=setor,
            dados={"nome": setor.nome},
        )
    return setor


def renomear_setor(autor, setor_id, *, nome):
    """Troca o nome do setor (FR-025). O próprio setor pode mudar só a caixa do nome; a designação
    de Almoxarifado, a situação e `ativado_em` não mudam. Mesmo nome: sem efeito, sem evento."""
    with _operacao():
        setor = _setor_existente(setor_id)
        nome = _nome_de_setor_valido(nome)
        if nome == setor.nome:
            return setor
        _exigir_nome_de_setor_livre(nome, excluir_pk=setor.pk)
        anterior = setor.nome
        setor.nome = nome
        setor.save(update_fields=["nome"])
        validar_organizacao([setor], [])
        _registrar_evento(
            autor,
            TipoEvento.SETOR_RENOMEADO,
            setor=setor,
            dados={"anterior": {"nome": anterior}, "novo": {"nome": nome}},
        )
    return setor


def _chefes_e_papeis_do_setor(setor):
    """`(chefes, papeis)` do estado atual, no formato de `_requisitos_de_setor_ativo`: os chefes
    ativos do próprio setor e os papéis de cada um. Só lê."""
    chefes = list(
        User.objects.filter(setor=setor, is_active=True, papeis__papel=Papel.CHEFE_SETOR).values(
            "pk", "matricula"
        )
    )
    papeis = defaultdict(set)
    for usuario_id, papel in PapelUsuario.objects.filter(
        usuario_id__in=[chefe["pk"] for chefe in chefes]
    ).values_list("usuario_id", "papel"):
        papeis[usuario_id].add(Papel(papel))
    return chefes, papeis


def _requisitos_de_ativacao(setor):
    return _requisitos_de_setor_ativo(
        setor.nome, setor.almoxarifado, *_chefes_e_papeis_do_setor(setor)
    )


def prontidao_do_setor(setor):
    """Os requisitos para ativar `setor`, para a ficha do setor inativo: lista de
    `{"rotulo", "atendido", "recusa"}` (a `OperacaoRecusada` do requisito não atendido, ou `None`),
    avaliados pela mesma regra de `ativar_setor`. Só lê; a decisão final é da operação."""
    return [
        {"rotulo": rotulo, "atendido": recusa is None, "recusa": recusa}
        for rotulo, recusa in _requisitos_de_ativacao(setor)
    ]


def impedimento_de_ativar_setor(setor):
    """A `OperacaoRecusada` que `ativar_setor` levantaria hoje, ou `None` (inclusive para setor já
    ativo, que a operação não recusa: não faz nada). Só lê; a decisão final é da operação."""
    if setor.ativo:
        return None
    return next((recusa for _, recusa in _requisitos_de_ativacao(setor) if recusa), None)


def ativar_setor(autor, setor_id):
    """Ativa o setor (FR-027, FR-030): exige exatamente um chefe ativo do próprio setor e, no
    Almoxarifado, a chefia de estoque completa (`INV-ORG-006`). `ativado_em` registra só a primeira
    ativação; reativar segue as mesmas condições. Setor já ativo: sem efeito, sem evento."""
    with _operacao():
        return _ativar_sob_o_lock(autor, _setor_existente(setor_id))


def _chefe_e_outros_membros_ativos(setor):
    """`(chefe, outros)`: o chefe ativo do setor (ou `None`) e os demais membros ativos, em ordem
    de nome — a conta técnica não conta (FR-004). Só lê."""
    chefe = chefes_ativos(setor.pk).filter(is_superuser=False).first()
    outros = User.objects.filter(setor=setor, is_active=True, is_superuser=False).order_by(
        "nome_busca", "matricula"
    )
    if chefe is not None:
        outros = outros.exclude(pk=chefe.pk)
    return chefe, list(outros)


def _recusa_de_desativar_setor(setor, outros):
    """A primeira regra de `desativar_setor` que desativar o setor ATIVO `setor` violaria, ou
    `None`: o Almoxarifado nunca, e só com o chefe como único membro ativo (`outros` são os demais
    membros ativos). Só lê. É o ponto único para condições impostas por outros recortes (FR-053,
    research R17): a especificação de requisições acrescentará aqui a sua."""
    if setor.almoxarifado:
        return OperacaoRecusada(
            f"O setor {setor.nome} é o Almoxarifado e não pode ser desativado.",
            "O Almoxarifado é único e permanece ativo.",
            codigo=RECUSA_ALMOXARIFADO_PERMANENTE,
        )
    if outros:
        membros = ", ".join(f"{u.nome} ({u.matricula})" for u in outros)
        return OperacaoRecusada(
            f"O setor {setor.nome} ainda tem membros ativos além do chefe: {membros}.",
            "Transfira ou desative esses membros antes.",
            codigo=RECUSA_MEMBROS_ATIVOS,
            membros=outros,
        )
    return None


def impedimento_de_desativar_setor(setor):
    """A `OperacaoRecusada` que `desativar_setor` levantaria hoje — com os `membros` ativos além
    do chefe, quando é o caso —, ou `None` (inclusive para setor já inativo, que a operação não
    recusa: não faz nada). Só lê; a decisão final é da operação, sob o lock."""
    if not setor.ativo:
        return None
    _, outros = _chefe_e_outros_membros_ativos(setor)
    return _recusa_de_desativar_setor(setor, outros)


def desativar_setor(autor, setor_id):
    """Desativa o setor (FR-028, FR-029): só com o chefe como único membro ativo — membros inativos
    e a conta técnica não contam (FR-004) — e nunca o Almoxarifado depois de ativado
    (`INV-ORG-004`). O chefe mantém `ROLE-SECTOR-HEAD` (D-16). Setor já inativo: sem efeito,
    sem evento."""
    with _operacao():
        setor = _setor_existente(setor_id)
        if not setor.ativo:
            return setor
        chefe, outros = _chefe_e_outros_membros_ativos(setor)
        recusa = _recusa_de_desativar_setor(setor, outros)
        if recusa is not None:
            raise _levantar(recusa)
        setor.ativo = False
        setor.save(update_fields=["ativo"])
        validar_organizacao([setor], [])
        _registrar_evento(
            autor,
            TipoEvento.SETOR_DESATIVADO,
            setor=setor,
            dados={"chefe": chefe.matricula if chefe else None},
        )
    return setor
