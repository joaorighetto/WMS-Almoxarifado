"""Contrato de navegação de servidor da sidebar (L1 do redesign).

Fontes: `docs/redesign-observatory/plano.md` seção 3 e ADR 0002.

O que este arquivo protege, em ordem de consequência:

- a sidebar nunca oferece um destino que a rota recusa (403) e nunca esconde um destino que a rota
  permite: a coerência navegação x autorização é verificada contra as rotas reais, sem duplicar a
  regra de autorização (`INV-AUTH-001`; `PERM-MATERIAL-VIEW`, `PERM-SCPI-IMPORT-EXECUTE`,
  `PERM-SCPI-IMPORT-HISTORY-VIEW`, `PERM-SUPPLIER-VIEW`, `PERM-SUPPLIER-IMPORT-EXECUTE`,
  `PERM-SUPPLIER-IMPORT-HISTORY-VIEW`, `PERM-STOCK-ENTRY-CREATE`, `PERM-STOCK-HISTORY-VIEW`,
  `PERM-USER-MANAGE`, `PERM-SECTOR-MANAGE`);
- a navegação deriva só de papel explícito: sem herança, sem `is_staff`/superusuário, e nada com
  credencial provisória;
- o conjunto exato de destinos por papel e a ordem dos grupos;
- o item "atual" a partir da rota resolvida, inclusive nas telas internas dos fluxos;
- custo: o contexto de navegação é preguiçoso (nenhuma query até alguém usá-lo) e a consulta de
  papéis é uma só por requisição, compartilhada com a `HomeView` (sem N+1 por item de menu).

Escrito antes da implementação (L2): `contas.context_processors.navegacao` ainda não existe e deve
ser registrado em `TEMPLATES[...]["OPTIONS"]["context_processors"]`. Os testes leem a navegação por
`response.context["navegacao"]` (o contexto avaliado no processador, sem depender do template da
sidebar, que é a L5) ou chamando o processador diretamente com uma `HttpRequest` montada.

Convenções de acesso: o contrato fala em "atributo" (`navegacao.grupos`, `grupo.itens`,
`item.chave`...). `_campo` aceita atributo ou chave de mapeamento, porque o template acessa os dois
do mesmo jeito; a implementação escolhe a forma.
"""

import uuid
from collections.abc import Mapping
from urllib.parse import urlsplit

import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from django.utils import timezone

from catalogo.models import ExecucaoImportacao
from contas.models import Papel, PapelUsuario, User
from tests.contas_helpers import PAPEIS_CHEFE_ALMOXARIFADO, membro_provisorio, rota

pytestmark = pytest.mark.django_db

# ---------------------------------------------------------------------------
# Tabela de referência do contrato (chave -> rótulo, rota, título e descrição da Home)
# ---------------------------------------------------------------------------
#
# `titulo` e `descricao` são os textos atuais de `contas/templates/contas/home.html`, com os
# espaços colapsados (a descrição de "Importar fornecedores" quebra linha no template).

ITENS = {
    "catalogo_consulta": {
        "rotulo": "Materiais",
        "rota": "catalogo:consulta",
        "titulo": "Consultar catálogo de materiais",
        "descricao": "Localize materiais por CADPRO ou descrição e confira o saldo.",
    },
    "catalogo_importacao": {
        "rotulo": "Importar catálogo",
        "rota": "catalogo:importacao_envio",
        "titulo": "Importar catálogo do SCPI",
        "descricao": "Envie o CSV exportado, confira a prévia e confirme a carga.",
    },
    "catalogo_historico": {
        "rotulo": "Histórico de importações",
        "rota": "catalogo:historico",
        "titulo": "Histórico de importações",
        "descricao": (
            "Veja quem importou, quando, e as rejeições e divergências de cada carga."
        ),
    },
    "fornecedores_consulta": {
        "rotulo": "Fornecedores",
        "rota": "fornecedores:consulta",
        "titulo": "Consultar fornecedores",
        "descricao": (
            "Localize um fornecedor por código, nome ou documento e confira a situação de "
            "bloqueio."
        ),
    },
    "fornecedores_importacao": {
        "rotulo": "Importar fornecedores",
        "rota": "fornecedores:importacao_envio",
        "titulo": "Importar fornecedores",
        "descricao": (
            "Envie o cadastro de fornecedores exportado do SCPI, confira a prévia e confirme a "
            "carga."
        ),
    },
    "fornecedores_historico": {
        "rotulo": "Histórico de importações",
        "rota": "fornecedores:historico",
        "titulo": "Histórico de importações de fornecedores",
        "descricao": (
            "Veja quem importou, quando, e as rejeições e alterações cadastrais de cada carga."
        ),
    },
    "estoque_entrada_nova": {
        "rotulo": "Registrar entrada",
        "rota": "estoque:entrada_nova",
        "titulo": "Registrar entrada de materiais",
        "descricao": "Lance recebimentos com motivo e referência, com efeito no saldo.",
    },
    "estoque_entradas": {
        "rotulo": "Entradas",
        "rota": "estoque:entradas",
        "titulo": "Consultar entradas",
        "descricao": (
            "Veja as entradas registradas, da mais recente para a mais antiga, e abra o "
            "detalhe de cada uma."
        ),
    },
    "usuarios": {
        "rotulo": "Usuários",
        "rota": "usuarios",
        "titulo": "Usuários",
        "descricao": "Cadastre contas, consulte papéis, situação e o histórico de cada usuário.",
    },
    "setores": {
        "rotulo": "Setores",
        "rota": "setores",
        "titulo": "Setores",
        "descricao": "Consulte a situação, a chefia e os membros de cada setor.",
    },
}

# Grupos na ordem do contrato, com os itens na ordem em que o contrato os lista.
GRUPOS = (
    ("Catálogo", ("catalogo_consulta", "catalogo_importacao", "catalogo_historico")),
    (
        "Fornecedores",
        ("fornecedores_consulta", "fornecedores_importacao", "fornecedores_historico"),
    ),
    ("Estoque", ("estoque_entrada_nova", "estoque_entradas")),
    ("Administração", ("usuarios", "setores")),
)

# Flag da Home -> itens que ela mesma já governava (mesmo conjunto de papéis).
FLAGS_DA_HOME = {
    "pode_consultar_catalogo": ("catalogo_consulta",),
    "pode_importar_catalogo": ("catalogo_importacao", "catalogo_historico"),
    "pode_consultar_fornecedores": ("fornecedores_consulta",),
    "pode_importar_fornecedores": ("fornecedores_importacao", "fornecedores_historico"),
    "pode_registrar_entrada": ("estoque_entrada_nova",),
    "pode_consultar_entradas": ("estoque_entradas",),
    "pode_administrar_organizacao": ("usuarios", "setores"),
}

# ---------------------------------------------------------------------------
# Personas: fixture -> navegação esperada (lista de (grupo, chaves) só dos grupos não vazios).
# ---------------------------------------------------------------------------

CATALOGO_CONSULTA = ("Catálogo", ["catalogo_consulta"])
CATALOGO_COMPLETO = (
    "Catálogo",
    ["catalogo_consulta", "catalogo_importacao", "catalogo_historico"],
)
FORNECEDORES_CONSULTA = ("Fornecedores", ["fornecedores_consulta"])
FORNECEDORES_COMPLETO = (
    "Fornecedores",
    ["fornecedores_consulta", "fornecedores_importacao", "fornecedores_historico"],
)
ESTOQUE_COMPLETO = ("Estoque", ["estoque_entrada_nova", "estoque_entradas"])
ESTOQUE_SO_CONSULTA = ("Estoque", ["estoque_entradas"])
ADMINISTRACAO = ("Administração", ["usuarios", "setores"])

PERSONAS = {
    "requisitante": [CATALOGO_CONSULTA],
    "auxiliar_setor": [CATALOGO_CONSULTA],
    "chefe_setor": [CATALOGO_CONSULTA],
    "funcionario_almoxarifado": [CATALOGO_CONSULTA, FORNECEDORES_CONSULTA, ESTOQUE_COMPLETO],
    "chefe_almoxarifado": [CATALOGO_COMPLETO, FORNECEDORES_COMPLETO, ESTOQUE_COMPLETO],
    # Auditor lê entradas, mas NÃO fornecedores (PERM-SUPPLIER-VIEW é do funcionário).
    "auditor": [CATALOGO_CONSULTA, ESTOQUE_SO_CONSULTA],
    "admin_sistema": [CATALOGO_CONSULTA, ADMINISTRACAO],
    # Papéis somam, nunca se herdam: administrador + funcionário vê as duas coisas.
    "admin_operacional": [
        CATALOGO_CONSULTA,
        FORNECEDORES_CONSULTA,
        ESTOQUE_COMPLETO,
        ADMINISTRACAO,
    ],
    # Conta técnica: nenhum papel de negócio, nenhum destino (só Início).
    "superusuario_tecnico": [],
    # `is_staff` sozinho não abre nada além do que o papel já abre.
    "requisitante_staff": [CATALOGO_CONSULTA],
}


@pytest.fixture
def auxiliar_setor(criar_usuario_com_papeis):
    return criar_usuario_com_papeis(Papel.AUXILIAR_SETOR)


@pytest.fixture
def admin_operacional(criar_usuario_com_papeis):
    return criar_usuario_com_papeis(Papel.ADMINISTRADOR_SISTEMA, Papel.FUNCIONARIO_ALMOXARIFADO)


@pytest.fixture
def requisitante_staff(requisitante):
    User.objects.filter(pk=requisitante.pk).update(is_staff=True)
    requisitante.is_staff = True
    return requisitante


@pytest.fixture
def usuario_com_tudo(criar_usuario_com_papeis):
    """Todos os destinos visíveis: administrador + os três papéis do chefe do almoxarifado."""
    return criar_usuario_com_papeis(
        Papel.ADMINISTRADOR_SISTEMA,
        Papel.CHEFE_ALMOXARIFADO,
        Papel.FUNCIONARIO_ALMOXARIFADO,
        Papel.CHEFE_SETOR,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _campo(objeto, nome):
    """Atributo ou chave: o template acessa os dois do mesmo jeito."""
    if isinstance(objeto, Mapping):
        return objeto[nome]
    return getattr(objeto, nome)


def _login(client, usuario, senha_valida):
    assert client.login(username=usuario.matricula, password=senha_valida), (
        "pré-condição do teste: login direto via client deveria funcionar"
    )


def _itens(navegacao):
    """Todos os itens de grupo, na ordem da navegação (sem o Início)."""
    return [item for grupo in _campo(navegacao, "grupos") for item in _campo(grupo, "itens")]


def _resumo(navegacao):
    return [
        (_campo(grupo, "titulo"), [_campo(i, "chave") for i in _campo(grupo, "itens")])
        for grupo in _campo(navegacao, "grupos")
    ]


def _chaves_visiveis(navegacao):
    return {chave for _, chaves in _resumo(navegacao) for chave in chaves}


def _com_atual(navegacao):
    """Chaves de todos os itens (Início incluído) marcados como `atual`."""
    inicio = _campo(navegacao, "inicio")
    candidatos = ([inicio] if inicio is not None else []) + _itens(navegacao)
    return [_campo(item, "chave") for item in candidatos if _campo(item, "atual")]


def _navegacao_da_home(client, usuario, senha_valida):
    _login(client, usuario, senha_valida)
    resposta = client.get(reverse("home"))
    assert resposta.status_code == 200
    return resposta.context["navegacao"]


def _processador():
    from contas.context_processors import navegacao

    return navegacao


def _requisicao(usuario, url):
    """Requisição montada à mão, com a rota resolvida como o handler do Django faz."""
    requisicao = RequestFactory().get(url)
    requisicao.user = usuario
    requisicao.resolver_match = resolve(urlsplit(url).path)
    return requisicao


def _navegacao_direta(usuario, url):
    return _processador()(_requisicao(usuario, url))["navegacao"]


def _consultas_de_papeis(capturadas):
    tabela = PapelUsuario._meta.db_table
    return [q["sql"] for q in capturadas.captured_queries if tabela in q["sql"]]


def _percorrer_tudo(navegacao):
    """Lê tudo o que um template leria: se houver custo por item, aparece aqui."""
    _campo(navegacao, "inicio")
    _campo(navegacao, "atual")
    _campo(navegacao, "provisoria")
    for grupo in _campo(navegacao, "grupos"):
        _campo(grupo, "titulo")
        for item in _campo(grupo, "itens"):
            for nome in ("chave", "rotulo", "titulo", "descricao", "url", "atual"):
                _campo(item, nome)


def _criar_execucao(executada_por):
    return ExecucaoImportacao.objects.create(
        token_previa=uuid.uuid4(),
        executada_por=executada_por,
        concluida_em=timezone.now(),
        nome_arquivo="carga.csv",
        tamanho_arquivo=10,
        sha256_arquivo="0" * 64,
        total_recebidos=1,
        total_inseridos=1,
        total_atualizados=0,
        total_atualizados_com_alteracao=0,
        total_rejeitados=0,
        total_divergencias=0,
        total_ausentes_no_arquivo=0,
    )


# ---------------------------------------------------------------------------
# 0. Registro do context processor
# ---------------------------------------------------------------------------


def test_context_processor_de_navegacao_esta_registrado():
    processadores = settings.TEMPLATES[0]["OPTIONS"]["context_processors"]
    assert "contas.context_processors.navegacao" in processadores


# ---------------------------------------------------------------------------
# 1. Destinos por papel: conjunto exato, ordem dos grupos, rótulos e URLs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("persona", sorted(PERSONAS))
def test_navegacao_por_papel_tem_exatamente_os_destinos_do_papel(
    persona, request, client, senha_valida
):
    usuario = request.getfixturevalue(persona)

    navegacao = _navegacao_da_home(client, usuario, senha_valida)

    assert _resumo(navegacao) == PERSONAS[persona]


@pytest.mark.parametrize("persona", sorted(PERSONAS))
def test_navegacao_sempre_traz_inicio_para_usuario_comum_e_nenhum_grupo_vazio(
    persona, request, client, senha_valida
):
    usuario = request.getfixturevalue(persona)

    navegacao = _navegacao_da_home(client, usuario, senha_valida)

    inicio = _campo(navegacao, "inicio")
    assert inicio is not None
    assert _campo(inicio, "chave") == "inicio"
    assert _campo(inicio, "url") == reverse("home")
    # Só grupos com ao menos um item visível entram.
    assert all(itens for _, itens in _resumo(navegacao))


def test_itens_expoem_rotulo_titulo_descricao_e_url_resolvida(
    client, usuario_com_tudo, senha_valida
):
    navegacao = _navegacao_da_home(client, usuario_com_tudo, senha_valida)

    # Quem tem todos os papéis vê os dez destinos, agrupados e ordenados como o contrato.
    assert _resumo(navegacao) == [(titulo, list(chaves)) for titulo, chaves in GRUPOS]
    for item in _itens(navegacao):
        esperado = ITENS[_campo(item, "chave")]
        assert _campo(item, "rotulo") == esperado["rotulo"]
        assert _campo(item, "titulo") == esperado["titulo"]
        assert _campo(item, "descricao") == esperado["descricao"]
        assert _campo(item, "url") == reverse(esperado["rota"])
        assert _campo(item, "atual") is False


def test_navegacao_do_usuario_nao_vaza_para_o_proximo_usuario_do_mesmo_processo(
    client, requisitante, admin_sistema, senha_valida
):
    """Duas requisições seguidas de contas diferentes: cada uma vê só o que é seu (nada de cache
    global de papéis entre requisições)."""
    primeira = _navegacao_da_home(client, admin_sistema, senha_valida)
    assert "usuarios" in _chaves_visiveis(primeira)

    client.logout()
    segunda = _navegacao_da_home(client, requisitante, senha_valida)
    assert _chaves_visiveis(segunda) == {"catalogo_consulta"}


# ---------------------------------------------------------------------------
# 2. Invariante de coerência navegação x rota (INV-AUTH-001)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("persona", sorted(PERSONAS))
def test_sidebar_so_oferece_o_que_a_rota_permite_e_so_esconde_o_que_a_rota_recusa(
    persona, request, client, senha_valida
):
    usuario = request.getfixturevalue(persona)
    navegacao = _navegacao_da_home(client, usuario, senha_valida)
    visiveis = {_campo(i, "chave"): _campo(i, "url") for i in _itens(navegacao)}

    for chave, destino in ITENS.items():
        if chave in visiveis:
            resposta = client.get(visiveis[chave])
            assert resposta.status_code < 400, (
                f"{persona}: a navegação oferece {chave} ({visiveis[chave]}), "
                f"mas a rota respondeu {resposta.status_code}"
            )
        else:
            resposta = client.get(reverse(destino["rota"]))
            assert resposta.status_code == 403, (
                f"{persona}: a navegação esconde {chave}, mas a rota respondeu "
                f"{resposta.status_code} em vez de 403"
            )


@pytest.mark.parametrize("flag, chaves", sorted(FLAGS_DA_HOME.items()))
@pytest.mark.parametrize("persona", sorted(PERSONAS))
def test_flags_pode_da_home_e_navegacao_concordam(
    flag, chaves, persona, request, client, senha_valida
):
    """A Home e a sidebar compartilham a fonte de papéis: a flag `pode_*` da Home é verdadeira
    exatamente quando todos os itens que ela governava estão na navegação."""
    usuario = request.getfixturevalue(persona)
    _login(client, usuario, senha_valida)

    resposta = client.get(reverse("home"))

    visiveis = _chaves_visiveis(resposta.context["navegacao"])
    assert resposta.context[flag] is all(chave in visiveis for chave in chaves)
    assert resposta.context[flag] is any(chave in visiveis for chave in chaves)


def test_home_continua_expondo_papeis_setor_e_capacidades_planejadas(
    client, chefe_almoxarifado, senha_valida
):
    _login(client, chefe_almoxarifado, senha_valida)

    contexto = client.get(reverse("home")).context

    assert contexto["setor"] == chefe_almoxarifado.setor
    assert "Chefe do almoxarifado" in contexto["papeis"]
    assert contexto["capacidades_planejadas"]
    # O chefe do almoxarifado tem tudo, menos a administração (papel próprio).
    for flag in FLAGS_DA_HOME:
        assert contexto[flag] is (flag != "pode_administrar_organizacao")


# ---------------------------------------------------------------------------
# 3. Item atual a partir da rota resolvida
# ---------------------------------------------------------------------------

# (nome da rota, args, chave esperada). Telas internas dos fluxos incluídas; `pk` fictício basta
# porque só a resolução da rota importa (o processador não carrega o objeto).
ROTAS_ATUAIS_ALMOXARIFADO = [
    ("home", (), "inicio"),
    ("catalogo:consulta", (), "catalogo_consulta"),
    ("catalogo:importacao_envio", (), "catalogo_importacao"),
    ("catalogo:importacao_previa", (), "catalogo_importacao"),
    ("catalogo:historico", (), "catalogo_historico"),
    ("catalogo:execucao_detalhe", (1,), "catalogo_historico"),
    ("fornecedores:consulta", (), "fornecedores_consulta"),
    ("fornecedores:importacao_envio", (), "fornecedores_importacao"),
    ("fornecedores:importacao_previa", (), "fornecedores_importacao"),
    ("fornecedores:historico", (), "fornecedores_historico"),
    ("fornecedores:execucao_detalhe", (1,), "fornecedores_historico"),
    ("estoque:entrada_nova", (), "estoque_entrada_nova"),
    ("estoque:entradas", (), "estoque_entradas"),
    ("estoque:entrada_detalhe", (1,), "estoque_entradas"),
    ("estoque:entrada_estorno", (1,), "estoque_entradas"),
]

ROTAS_ATUAIS_ORGANIZACAO = [
    ("usuarios", (), "usuarios"),
    ("usuario_novo", (), "usuarios"),
    ("usuario", (1,), "usuarios"),
    ("usuario_editar", (1,), "usuarios"),
    ("usuario_papeis", (1,), "usuarios"),
    ("usuario_transferir", (1,), "usuarios"),
    ("usuario_desativar", (1,), "usuarios"),
    ("usuario_reativar", (1,), "usuarios"),
    ("usuario_redefinir_senha", (1,), "usuarios"),
    ("setores", (), "setores"),
    ("setor_novo", (), "setores"),
    ("setor", (1,), "setores"),
    ("setor_editar", (1,), "setores"),
    ("setor_chefia", (1,), "setores"),
    ("setor_ativar", (1,), "setores"),
    ("setor_desativar", (1,), "setores"),
]


@pytest.mark.parametrize(
    "nome, args, esperado",
    ROTAS_ATUAIS_ALMOXARIFADO + ROTAS_ATUAIS_ORGANIZACAO,
    ids=lambda v: v if isinstance(v, str) else None,
)
def test_atual_e_derivado_da_rota_resolvida_e_so_um_item_fica_marcado(
    nome, args, esperado, usuario_com_tudo
):
    url = rota(nome, *args)

    navegacao = _navegacao_direta(usuario_com_tudo, url)

    assert _campo(navegacao, "atual") == esperado
    assert _com_atual(navegacao) == [esperado]


def test_definir_senha_nao_marca_nenhum_item_como_atual(usuario_com_tudo):
    navegacao = _navegacao_direta(usuario_com_tudo, rota("definir_senha"))

    assert _campo(navegacao, "atual") is None
    assert _com_atual(navegacao) == []


def test_atual_na_consulta_do_catalogo_pela_cadeia_http(client, requisitante, senha_valida):
    _login(client, requisitante, senha_valida)

    resposta = client.get(reverse("catalogo:consulta"))

    navegacao = resposta.context["navegacao"]
    assert _campo(navegacao, "atual") == "catalogo_consulta"
    assert _com_atual(navegacao) == ["catalogo_consulta"]


def test_atual_no_inicio_pela_cadeia_http(client, requisitante, senha_valida):
    navegacao = _navegacao_da_home(client, requisitante, senha_valida)

    assert _campo(navegacao, "atual") == "inicio"
    assert _com_atual(navegacao) == ["inicio"]


def test_atual_no_detalhe_de_execucao_pela_cadeia_http(
    client, chefe_almoxarifado, senha_valida
):
    execucao = _criar_execucao(chefe_almoxarifado)
    _login(client, chefe_almoxarifado, senha_valida)

    resposta = client.get(reverse("catalogo:execucao_detalhe", args=[execucao.pk]))

    assert resposta.status_code == 200
    navegacao = resposta.context["navegacao"]
    assert _campo(navegacao, "atual") == "catalogo_historico"
    assert _com_atual(navegacao) == ["catalogo_historico"]


def test_atual_nas_fichas_de_usuario_e_setor_pela_cadeia_http(
    client, admin_sistema, setor, senha_valida
):
    _login(client, admin_sistema, senha_valida)

    ficha_usuario = client.get(reverse("usuario", args=[admin_sistema.pk]))
    ficha_setor = client.get(reverse("setor", args=[setor.pk]))

    assert ficha_usuario.status_code == 200
    assert ficha_setor.status_code == 200
    assert _campo(ficha_usuario.context["navegacao"], "atual") == "usuarios"
    assert _com_atual(ficha_usuario.context["navegacao"]) == ["usuarios"]
    assert _campo(ficha_setor.context["navegacao"], "atual") == "setores"
    assert _com_atual(ficha_setor.context["navegacao"]) == ["setores"]


def test_definir_senha_pela_cadeia_http_nao_tem_item_atual(client, requisitante, senha_valida):
    _login(client, requisitante, senha_valida)

    resposta = client.get(reverse("definir_senha"))

    assert resposta.status_code == 200
    navegacao = resposta.context["navegacao"]
    assert _campo(navegacao, "atual") is None
    assert _com_atual(navegacao) == []


# ---------------------------------------------------------------------------
# 4. Credencial provisória
# ---------------------------------------------------------------------------


def test_com_credencial_provisoria_a_navegacao_nao_oferece_destino_algum(client, setor):
    # Conta com TODOS os papéis de chefia: sem a regra, a navegação ofereceria muita coisa.
    usuario, senha = membro_provisorio(
        setor, "PROV-NAV-1", PAPEIS_CHEFE_ALMOXARIFADO | {Papel.ADMINISTRADOR_SISTEMA}
    )
    resposta = client.post(rota("login"), {"username": usuario.matricula, "password": senha})
    assert resposta.status_code == 302

    resposta = client.get(rota("definir_senha"))

    assert resposta.status_code == 200
    navegacao = resposta.context["navegacao"]
    assert _campo(navegacao, "provisoria") is True
    assert list(_campo(navegacao, "grupos")) == []
    assert _campo(navegacao, "inicio") is None
    assert _campo(navegacao, "atual") is None


def test_sem_credencial_provisoria_a_navegacao_nao_e_provisoria(client, requisitante, senha_valida):
    navegacao = _navegacao_da_home(client, requisitante, senha_valida)

    assert _campo(navegacao, "provisoria") is False


# ---------------------------------------------------------------------------
# 5. Anônimo
# ---------------------------------------------------------------------------


def test_anonimo_na_tela_de_login_nao_tem_navegacao(client):
    resposta = client.get(reverse("login"))

    assert resposta.status_code == 200
    assert not resposta.context.get("navegacao")


def test_processador_nao_expoe_navegacao_para_anonimo():
    requisicao = RequestFactory().get(reverse("login"))
    requisicao.user = AnonymousUser()
    requisicao.resolver_match = resolve(reverse("login"))

    with CaptureQueriesContext(connection) as capturadas:
        contexto = _processador()(requisicao)

    assert not contexto.get("navegacao")
    assert len(capturadas) == 0


# ---------------------------------------------------------------------------
# 6. Preguiça e custo
# ---------------------------------------------------------------------------


def test_processador_e_preguicoso_e_consulta_papeis_uma_unica_vez(chefe_almoxarifado):
    requisicao = _requisicao(chefe_almoxarifado, reverse("catalogo:consulta"))

    with CaptureQueriesContext(connection) as ao_construir:
        navegacao = _processador()(requisicao)["navegacao"]
    assert len(ao_construir) == 0, "o processador não pode consultar o banco até o uso"

    with CaptureQueriesContext(connection) as ao_usar:
        _percorrer_tudo(navegacao)
        _percorrer_tudo(navegacao)  # reler não consulta de novo
    assert len(_consultas_de_papeis(ao_usar)) == 1
    assert len(ao_usar) == 1, (
        "ler a navegação deve custar só a consulta de papéis (sem query por item de menu): "
        f"{[q['sql'] for q in ao_usar.captured_queries]}"
    )


def test_fragmento_htmx_da_consulta_nao_paga_a_consulta_de_papeis_da_navegacao(
    client, chefe_almoxarifado, senha_valida
):
    _login(client, chefe_almoxarifado, senha_valida)
    url = reverse("catalogo:consulta")

    with CaptureQueriesContext(connection) as fragmento:
        resposta_fragmento = client.get(url, headers={"HX-Request": "true"})
    with CaptureQueriesContext(connection) as pagina:
        resposta_pagina = client.get(url)

    assert resposta_fragmento.status_code == 200
    assert resposta_pagina.status_code == 200
    # A checagem de papel da própria view (`tem_papel`) é a única consulta de papéis do fragmento.
    assert len(_consultas_de_papeis(fragmento)) <= 1, [
        q for q in _consultas_de_papeis(fragmento)
    ]
    # A página inteira pode acrescentar no máximo UMA consulta de papéis, da navegação.
    assert len(_consultas_de_papeis(pagina)) <= len(_consultas_de_papeis(fragmento)) + 1


def test_pagina_com_sidebar_consulta_papeis_no_maximo_uma_vez_para_a_navegacao(
    client, chefe_almoxarifado, senha_valida
):
    _login(client, chefe_almoxarifado, senha_valida)

    with CaptureQueriesContext(connection) as capturadas:
        resposta = client.get(reverse("catalogo:consulta"))
        # Qualquer leitura pendente (a sidebar real é a L5) acontece na mesma requisição: o
        # contexto guarda a requisição e reaproveita o que já foi lido.
        _percorrer_tudo(resposta.context["navegacao"])

    # 1 da checagem de papel da view + no máximo 1 da navegação, independente do número de itens.
    assert len(_consultas_de_papeis(capturadas)) <= 2, _consultas_de_papeis(capturadas)


def test_home_consulta_papeis_no_maximo_uma_vez_somando_view_e_navegacao(
    client, chefe_almoxarifado, senha_valida
):
    _login(client, chefe_almoxarifado, senha_valida)

    with CaptureQueriesContext(connection) as capturadas:
        resposta = client.get(reverse("home"))
        _percorrer_tudo(resposta.context["navegacao"])

    assert len(_consultas_de_papeis(capturadas)) <= 1, _consultas_de_papeis(capturadas)


def test_home_mantem_o_teto_de_queries_com_a_navegacao_avaliada(
    client, chefe_almoxarifado, senha_valida, django_assert_max_num_queries
):
    _login(client, chefe_almoxarifado, senha_valida)

    with django_assert_max_num_queries(10):
        resposta = client.get(reverse("home"))
        _percorrer_tudo(resposta.context["navegacao"])
