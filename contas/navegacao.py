"""Contrato de navegação de servidor da sidebar (`docs/redesign-observatory/plano.md` seção 3,
ADR 0002).

Definição única dos destinos de navegação (grupos, itens, papéis que os enxergam e rotas que os
marcam como atuais). A navegação é só espelho de visibilidade: a autorização efetiva continua em
cada rota (Constitution VI, `INV-AUTH-001`). Regras de visibilidade: papel explicitamente
atribuído, sem herança, sem `is_staff`/superusuário, e nada enquanto a credencial é provisória.

Os códigos de papel do usuário são lidos do banco no máximo uma vez por requisição
(`codigos_papeis`) e compartilhados entre a navegação e a `HomeView` (Constitution X).
"""

from dataclasses import dataclass, field

from django.urls import reverse

from contas.models import Papel

# Flag `pode_*` -> papéis que a concedem (basta um). Mesmas regras que a `HomeView` sempre usou;
# cobrem PERM-MATERIAL-VIEW, PERM-SCPI-IMPORT-EXECUTE/-HISTORY-VIEW, PERM-SUPPLIER-VIEW,
# PERM-SUPPLIER-IMPORT-EXECUTE/-HISTORY-VIEW, PERM-STOCK-ENTRY-CREATE, PERM-STOCK-HISTORY-VIEW
# (recorte da entrada), PERM-USER-MANAGE e PERM-SECTOR-MANAGE.
PAPEIS_DA_FLAG = {
    "pode_consultar_catalogo": frozenset({Papel.REQUISITANTE}),
    "pode_importar_catalogo": frozenset({Papel.CHEFE_ALMOXARIFADO}),
    "pode_consultar_fornecedores": frozenset({Papel.FUNCIONARIO_ALMOXARIFADO}),
    "pode_importar_fornecedores": frozenset({Papel.CHEFE_ALMOXARIFADO}),
    "pode_registrar_entrada": frozenset({Papel.FUNCIONARIO_ALMOXARIFADO}),
    "pode_consultar_entradas": frozenset({Papel.FUNCIONARIO_ALMOXARIFADO, Papel.AUDITOR}),
    "pode_administrar_organizacao": frozenset({Papel.ADMINISTRADOR_SISTEMA}),
}


@dataclass(frozen=True)
class Destino:
    chave: str
    rotulo: str
    titulo: str
    descricao: str
    rota: str
    flag: str


# Grupos na ordem de exibição, com os itens na ordem em que aparecem.
GRUPOS = (
    (
        "Catálogo",
        (
            Destino(
                "catalogo_consulta",
                "Materiais",
                "Consultar catálogo de materiais",
                "Localize materiais por CADPRO ou descrição e confira o saldo.",
                "catalogo:consulta",
                "pode_consultar_catalogo",
            ),
            Destino(
                "catalogo_importacao",
                "Importar catálogo",
                "Importar catálogo do SCPI",
                "Envie o CSV exportado, confira a prévia e confirme a carga.",
                "catalogo:importacao_envio",
                "pode_importar_catalogo",
            ),
            Destino(
                "catalogo_historico",
                "Histórico de importações",
                "Histórico de importações",
                "Veja quem importou, quando, e as rejeições e divergências de cada carga.",
                "catalogo:historico",
                "pode_importar_catalogo",
            ),
        ),
    ),
    (
        "Fornecedores",
        (
            Destino(
                "fornecedores_consulta",
                "Fornecedores",
                "Consultar fornecedores",
                "Localize um fornecedor por código, nome ou documento e confira a situação de "
                "bloqueio.",
                "fornecedores:consulta",
                "pode_consultar_fornecedores",
            ),
            Destino(
                "fornecedores_importacao",
                "Importar fornecedores",
                "Importar fornecedores",
                "Envie o cadastro de fornecedores exportado do SCPI, confira a prévia e "
                "confirme a carga.",
                "fornecedores:importacao_envio",
                "pode_importar_fornecedores",
            ),
            Destino(
                "fornecedores_historico",
                "Histórico de importações",
                "Histórico de importações de fornecedores",
                "Veja quem importou, quando, e as rejeições e alterações cadastrais de cada carga.",
                "fornecedores:historico",
                "pode_importar_fornecedores",
            ),
        ),
    ),
    (
        "Estoque",
        (
            Destino(
                "estoque_entrada_nova",
                "Registrar entrada",
                "Registrar entrada de materiais",
                "Lance recebimentos com motivo e referência, com efeito no saldo.",
                "estoque:entrada_nova",
                "pode_registrar_entrada",
            ),
            Destino(
                "estoque_entradas",
                "Entradas",
                "Consultar entradas",
                "Veja as entradas registradas, da mais recente para a mais antiga, e abra o "
                "detalhe de cada uma.",
                "estoque:entradas",
                "pode_consultar_entradas",
            ),
        ),
    ),
    (
        "Administração",
        (
            Destino(
                "usuarios",
                "Usuários",
                "Usuários",
                "Cadastre contas, consulte papéis, situação e o histórico de cada usuário.",
                "usuarios",
                "pode_administrar_organizacao",
            ),
            Destino(
                "setores",
                "Setores",
                "Setores",
                "Consulte a situação, a chefia e os membros de cada setor.",
                "setores",
                "pode_administrar_organizacao",
            ),
        ),
    ),
)

# Nome da rota resolvida (com namespace) -> chave do item atual, incluindo as telas internas dos
# fluxos. Rotas POST caem na tela do fluxo que re-renderiza em caso de recusa.
CHAVE_DA_ROTA = {
    "home": "inicio",
    "catalogo:consulta": "catalogo_consulta",
    "catalogo:importacao_envio": "catalogo_importacao",
    "catalogo:importacao_previa": "catalogo_importacao",
    "catalogo:importacao_confirmar": "catalogo_importacao",
    "catalogo:importacao_cancelar": "catalogo_importacao",
    "catalogo:historico": "catalogo_historico",
    "catalogo:execucao_detalhe": "catalogo_historico",
    "fornecedores:consulta": "fornecedores_consulta",
    "fornecedores:importacao_envio": "fornecedores_importacao",
    "fornecedores:importacao_previa": "fornecedores_importacao",
    "fornecedores:importacao_confirmar": "fornecedores_importacao",
    "fornecedores:importacao_cancelar": "fornecedores_importacao",
    "fornecedores:historico": "fornecedores_historico",
    "fornecedores:execucao_detalhe": "fornecedores_historico",
    "estoque:entrada_nova": "estoque_entrada_nova",
    "estoque:entrada_confirmar": "estoque_entrada_nova",
    "estoque:entradas": "estoque_entradas",
    "estoque:entrada_detalhe": "estoque_entradas",
    "estoque:entrada_estorno": "estoque_entradas",
    "usuarios": "usuarios",
    "usuario_novo": "usuarios",
    "usuario": "usuarios",
    "usuario_editar": "usuarios",
    "usuario_papeis": "usuarios",
    "usuario_transferir": "usuarios",
    "usuario_desativar": "usuarios",
    "usuario_reativar": "usuarios",
    "usuario_redefinir_senha": "usuarios",
    "setores": "setores",
    "setor_novo": "setores",
    "setor": "setores",
    "setor_editar": "setores",
    "setor_chefia": "setores",
    "setor_ativar": "setores",
    "setor_desativar": "setores",
}


@dataclass(frozen=True)
class ItemNavegacao:
    chave: str
    rotulo: str
    url: str
    atual: bool
    titulo: str = ""
    descricao: str = ""


@dataclass(frozen=True)
class GrupoNavegacao:
    titulo: str
    itens: list[ItemNavegacao] = field(default_factory=list)


@dataclass(frozen=True)
class Navegacao:
    grupos: list[GrupoNavegacao]
    inicio: ItemNavegacao | None
    atual: str | None
    provisoria: bool


def codigos_papeis(request):
    """Códigos de papel do usuário da requisição, lidos do banco uma única vez e guardados na
    própria requisição (nunca entre requisições). Só papel explicitamente atribuído."""
    if not hasattr(request, "_codigos_papeis"):
        request._codigos_papeis = set(request.user.papeis.values_list("papel", flat=True))
    return request._codigos_papeis


def flags_de_acesso(codigos):
    """Flags `pode_*` derivadas dos códigos de papel, sem herança."""
    return {flag: bool(codigos & papeis) for flag, papeis in PAPEIS_DA_FLAG.items()}


def montar_navegacao(request):
    """Monta a navegação da requisição. Com credencial provisória nada é oferecido, sem consultar
    papéis (mesma regra do `CredencialProvisoriaMiddleware`)."""
    if request.user.senha_provisoria_em is not None:
        return Navegacao(grupos=[], inicio=None, atual=None, provisoria=True)

    correspondencia = getattr(request, "resolver_match", None)
    atual = CHAVE_DA_ROTA.get(correspondencia.view_name) if correspondencia else None
    flags = flags_de_acesso(codigos_papeis(request))

    grupos = []
    for titulo, destinos in GRUPOS:
        itens = [
            ItemNavegacao(
                chave=destino.chave,
                rotulo=destino.rotulo,
                titulo=destino.titulo,
                descricao=destino.descricao,
                url=reverse(destino.rota),
                atual=destino.chave == atual,
            )
            for destino in destinos
            if flags[destino.flag]
        ]
        if itens:
            grupos.append(GrupoNavegacao(titulo=titulo, itens=itens))

    inicio = ItemNavegacao(
        chave="inicio", rotulo="Início", url=reverse("home"), atual=atual == "inicio"
    )
    return Navegacao(grupos=grupos, inicio=inicio, atual=atual, provisoria=False)
