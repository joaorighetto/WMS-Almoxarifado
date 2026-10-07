"""Testes do app shell autenticado (sidebar contextual, ADR 0002).

Substitui `tests/test_barra_trabalho.py`, que fixava a barra de trabalho antiga. Fontes:
`docs/redesign-observatory/plano.md` (seção 3, "Ganchos de markup" e "Contratos que não podem
mudar"), contrato visual §3 e §10, ADR 0002.

O que este arquivo protege, em ordem de consequência:

- logout continua exclusivamente POST + CSRF, em exatamente um formulário por página, em toda
  tela autenticada (Constitution IX): um `<a href="/logout/">` ou um segundo formulário seriam
  regressões de segurança;
- a sidebar só espelha o que a rota permite (`INV-AUTH-001`): conjunto exato de destinos por
  papel no HTML, grupos só com itens, e item atual correto e único — o conjunto de dados vem de
  `tests/test_navegacao.py` (contrato de servidor), aqui se verifica o que chega ao markup;
- credencial provisória não oferece navegação nem destino algum, só a marca (texto) e sair;
- respostas parciais HTMX nunca carregam o shell (senão cada busca o duplicaria na página);
- tema aplicado antes da primeira pintura e `shell.js` carregado uma única vez, no `<head>`:
  no `<body>` seria re-executado quando o HTMX troca o corpo na restauração de histórico.

O parsing é estrutural (`tests/html_helpers.py`), nunca regex de atributo. As telas ainda não
recompostas (propagação P1 a P5) trazem o próprio `<main>` sem `id`: o alvo do skip link nelas é
resolvido por fallback em JavaScript (`static/js/shell.js`), que um teste de servidor não
exercita. Só as telas recompostas (Home, consulta do catálogo, `/senha/`, as cinco do lote P2:
consulta de fornecedores e histórico/execução de importação de catálogo e fornecedores, e as
quatro do lote P3: envio e prévia de importação de catálogo e de fornecedores) têm `id="main"`
verificado aqui; o markup do login e de `/senha/` está em
`tests/test_contas_credenciais_markup.py`.
"""

import uuid
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from catalogo.models import ExecucaoImportacao
from contas.models import Papel
from fornecedores.models import ExecucaoImportacaoFornecedores
from tests.contas_helpers import PAPEIS_CHEFE_ALMOXARIFADO, membro_provisorio, rota
from tests.html_helpers import analisar, hrefs_de
from tests.test_navegacao import ITENS, PERSONAS

pytestmark = pytest.mark.django_db

HX = {"HTTP_HX_REQUEST": "true"}


def _login(client, usuario, senha_valida):
    assert client.login(username=usuario.matricula, password=senha_valida), (
        "pré-condição do teste: login direto via client deveria funcionar"
    )


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
# Telas autenticadas representativas: (id, fixture do usuário, recomposta?, como obter a resposta)
# ---------------------------------------------------------------------------


def _get(url_ou_nome, *args):
    def obter(client, usuario, csv_fixture):
        url = rota(url_ou_nome, *args)
        return client.get(url)

    return obter


def _execucao(client, usuario, csv_fixture):
    execucao = _criar_execucao(usuario)
    return client.get(reverse("catalogo:execucao_detalhe", args=[execucao.pk]))


def _execucao_fornecedores(client, usuario, csv_fixture):
    execucao = ExecucaoImportacaoFornecedores.objects.create(
        token_previa=uuid.uuid4(),
        executada_por=usuario,
        concluida_em=timezone.now(),
        nome_arquivo="cadastro.csv",
        tamanho_arquivo=10,
        sha256_arquivo="0" * 64,
        total_recebidos=1,
        total_inseridos=1,
        total_atualizados=0,
        total_atualizados_com_alteracao=0,
        total_rejeitados=0,
        total_ausentes_no_arquivo=0,
    )
    return client.get(reverse("fornecedores:execucao_detalhe", args=[execucao.pk]))


def _previa(client, usuario, csv_fixture):
    arquivo = SimpleUploadedFile(
        "arquivo.csv", csv_fixture("carga_inicial_valida.csv"), content_type="text/csv"
    )
    envio = client.post(reverse("catalogo:importacao_envio"), {"arquivo": arquivo})
    assert envio.status_code == 302, "pré-condição: envio válido deveria redirecionar à prévia"
    return client.get(reverse("catalogo:importacao_previa"))


def _previa_fornecedores(client, usuario, csv_fixture):
    conteudo = (
        "﻿CODIF;NOME;NOM_FANT;INSMF;CODTIP;BLOQ_OPCAO;MSG_BLOQ;TIPO_BLOQ;\r\n"
        "900001;FORNECEDOR SHELL;;;01;S;;;\r\n"
    ).encode()
    arquivo = SimpleUploadedFile("arquivo.csv", conteudo, content_type="text/csv")
    envio = client.post(reverse("fornecedores:importacao_envio"), {"arquivo": arquivo})
    assert envio.status_code == 302, "pré-condição: envio válido deveria redirecionar à prévia"
    return client.get(reverse("fornecedores:importacao_previa"))


def _ficha_do_proprio_usuario(client, usuario, csv_fixture):
    return client.get(rota("usuario", usuario.pk))


TELAS = [
    ("home", "requisitante", True, _get("home")),
    ("catalogo-consulta", "requisitante", True, _get("catalogo:consulta")),
    ("catalogo-envio", "chefe_almoxarifado", True, _get("catalogo:importacao_envio")),
    ("catalogo-previa", "chefe_almoxarifado", True, _previa),
    ("catalogo-historico", "chefe_almoxarifado", True, _get("catalogo:historico")),
    ("catalogo-execucao", "chefe_almoxarifado", True, _execucao),
    ("fornecedores-envio", "chefe_almoxarifado", True, _get("fornecedores:importacao_envio")),
    ("fornecedores-previa", "chefe_almoxarifado", True, _previa_fornecedores),
    ("fornecedores-historico", "chefe_almoxarifado", True, _get("fornecedores:historico")),
    ("fornecedores-execucao", "chefe_almoxarifado", True, _execucao_fornecedores),
    ("fornecedores-consulta", "funcionario_almoxarifado", True, _get("fornecedores:consulta")),
    ("entradas", "funcionario_almoxarifado", False, _get("estoque:entradas")),
    ("entrada-nova", "funcionario_almoxarifado", False, _get("estoque:entrada_nova")),
    ("usuarios", "admin_sistema", False, _get("usuarios")),
    ("usuario-ficha", "admin_sistema", False, _ficha_do_proprio_usuario),
    ("senha", "requisitante", True, _get("definir_senha")),
]

# Cada tela vira o `request.param` da fixture `pagina` (parametrização indireta).
PAGINAS = pytest.mark.parametrize(
    "pagina",
    [
        pytest.param((fixture, recomposta, obter), id=nome)
        for nome, fixture, recomposta, obter in TELAS
    ],
    indirect=True,
)


@pytest.fixture
def pagina(request, client, senha_valida, csv_fixture):
    """A tela parametrizada já obtida e parseada, com o usuário que a usa logado."""
    fixture_usuario, recomposta, obter = request.param
    usuario = request.getfixturevalue(fixture_usuario)
    _login(client, usuario, senha_valida)
    resposta = obter(client, usuario, csv_fixture)
    assert resposta.status_code == 200
    return SimpleNamespace(
        usuario=usuario,
        recomposta=recomposta,
        documento=analisar(resposta.content),
    )


# ---------------------------------------------------------------------------
# 1. Estrutura do shell em cada tela autenticada
# ---------------------------------------------------------------------------


@PAGINAS
def test_tela_autenticada_tem_um_main_uma_sidebar_e_um_unico_logout_post_com_csrf(pagina):
    documento = pagina.documento
    url_logout = reverse("logout")

    assert len(documento.buscar("main")) == 1
    assert len(documento.buscar("aside", classe="side")) == 1

    formularios_de_logout = [
        form
        for form in documento.buscar("form")
        if form.get("action") == url_logout
    ]
    assert len(formularios_de_logout) == 1
    formulario = formularios_de_logout[0]
    assert formulario.get("method", "").lower() == "post"
    tokens = formulario.buscar("input", name="csrfmiddlewaretoken")
    assert len(tokens) == 1 and tokens[0].get("value")
    assert formulario.esta_dentro_de("aside")

    # Logout nunca é um link navegável (GET).
    assert [a for a in documento.buscar("a", href=True) if a.attrs["href"] == url_logout] == []


@PAGINAS
def test_skip_link_aponta_para_o_conteudo_principal(pagina):
    documento = pagina.documento

    skip = documento.unico("a", classe="skip")
    assert skip.get("href") == "#main"

    if pagina.recomposta:
        principal = documento.unico("main")
        # O alvo existe, é único e é o próprio <main>.
        assert documento.unico(id="main") is principal
    # Telas legadas: o <main> não tem id e o desvio é feito por JavaScript (`shell.js`); não há o
    # que verificar no servidor.


@PAGINAS
def test_a_marca_e_o_rodape_da_conta_mostram_matricula_e_setor_do_usuario(pagina):
    lateral = pagina.documento.unico("aside", classe="side")

    marca = lateral.unico(classe="brand")
    assert "Almoxarifado SAEP" in marca.texto
    rodape = lateral.unico(classe="meta-env")
    assert pagina.usuario.matricula in rodape.texto
    assert pagina.usuario.setor.nome in rodape.texto


# ---------------------------------------------------------------------------
# 6. Tema e scripts do shell no <head>
# ---------------------------------------------------------------------------


@PAGINAS
def test_tema_inline_e_shell_js_ficam_no_head_uma_unica_vez(pagina):
    documento = pagina.documento
    cabeca = documento.unico("head")
    corpo = documento.unico("body")

    # Exatamente um script inline (sem src) no <head>, e é o do tema: lê `wms-tema`, em try/catch.
    inline = [s for s in cabeca.buscar("script") if "src" not in s.attrs]
    assert len(inline) == 1
    codigo = inline[0].texto
    assert "wms-tema" in codigo
    assert "try" in codigo and "catch" in codigo

    # ... antes da primeira folha de estilo (senão haveria um flash do tema errado).
    ordem = list(cabeca.descendentes())
    folhas = [no for no in cabeca.buscar("link") if no.get("rel") == "stylesheet"]
    assert folhas, "pré-condição: o <head> carrega folhas de estilo"
    assert ordem.index(inline[0]) < ordem.index(folhas[0])

    # shell.js: um único <script src=".../js/shell.js" defer> e no <head>.
    todos_shell = [
        s for s in documento.buscar("script", src=True) if s.attrs["src"].endswith("/js/shell.js")
    ]
    assert len(todos_shell) == 1
    assert todos_shell[0] in cabeca.buscar("script")
    assert "defer" in todos_shell[0].attrs

    # Nada disso no <body>: o HTMX re-executa scripts do corpo na restauração de histórico.
    for script in corpo.buscar("script"):
        assert not script.get("src", "").endswith("/js/shell.js")
        assert "wms-tema" not in script.texto

    # Controles do shell presentes.
    assert len(documento.buscar("button", data_theme_toggle=True)) == 1
    menu = documento.unico("button", data_menu_toggle=True)
    assert menu.get("aria-expanded") == "false"
    painel = documento.unico(id=menu.get("aria-controls"))
    assert painel.esta_dentro_de("aside")


# ---------------------------------------------------------------------------
# 2. Sidebar por papel, no HTML
# ---------------------------------------------------------------------------

PAPEIS_DA_SIDEBAR = [
    "requisitante",
    "auditor",
    "funcionario_almoxarifado",
    "chefe_almoxarifado",
    "admin_sistema",
    "superusuario_tecnico",
]


def _nav(documento):
    return documento.unico("nav", aria_label="Seções")


def _esperado_da_sidebar(persona):
    """Sequência esperada de filhos da `<nav>`: `("a", rótulo, url)` e `("h3", título, None)`."""
    esperado = [("a", "Início", reverse("home"))]
    for titulo, chaves in PERSONAS[persona]:
        esperado.append(("h3", titulo, None))
        for chave in chaves:
            item = ITENS[chave]
            esperado.append(("a", item["rotulo"], reverse(item["rota"])))
    return esperado


@pytest.mark.parametrize("persona", PAPEIS_DA_SIDEBAR)
def test_sidebar_tem_exatamente_os_destinos_grupos_e_ordem_do_papel(
    persona, request, client, senha_valida
):
    usuario = request.getfixturevalue(persona)
    _login(client, usuario, senha_valida)

    nav = _nav(analisar(client.get(reverse("home")).content))

    obtido = [
        (no.tag, no.texto, no.get("href")) for no in nav.filhos if no.tag in {"a", "h3"}
    ]
    assert obtido == _esperado_da_sidebar(persona)
    # Nada além de links e títulos de grupo dentro da nav.
    assert [no.tag for no in nav.filhos if no.tag not in {"a", "h3"}] == []
    # O conjunto de destinos é o de navegação mais o Início, sem repetição.
    assert len(hrefs_de(nav)) == len(nav.buscar("a"))


def test_grupo_sem_item_visivel_nao_aparece_na_sidebar(client, requisitante, senha_valida):
    """O requisitante só vê Catálogo: nenhum título de grupo vazio dos demais."""
    _login(client, requisitante, senha_valida)

    nav = _nav(analisar(client.get(reverse("home")).content))

    assert [h3.texto for h3 in nav.buscar("h3")] == ["Catálogo"]


def _com_aria_current(documento):
    return [
        no
        for no in _nav(documento).buscar(aria_current=True)
    ]


def _item_atual(client, usuario, senha_valida, url):
    _login(client, usuario, senha_valida)
    resposta = client.get(url)
    assert resposta.status_code == 200
    atuais = _com_aria_current(analisar(resposta.content))
    assert len(atuais) == 1
    assert atuais[0].get("aria-current") == "page"
    return atuais[0]


def test_aria_current_na_home_marca_so_o_inicio(client, requisitante, senha_valida):
    atual = _item_atual(client, requisitante, senha_valida, reverse("home"))

    assert (atual.texto, atual.get("href")) == ("Início", reverse("home"))


def test_aria_current_na_consulta_do_catalogo_marca_materiais(client, requisitante, senha_valida):
    atual = _item_atual(client, requisitante, senha_valida, reverse("catalogo:consulta"))

    assert (atual.texto, atual.get("href")) == ("Materiais", reverse("catalogo:consulta"))


def test_aria_current_na_execucao_de_importacao_marca_o_historico_do_catalogo(
    client, chefe_almoxarifado, senha_valida
):
    """Há dois itens "Histórico de importações" (catálogo e fornecedores): o destino decide."""
    execucao = _criar_execucao(chefe_almoxarifado)

    atual = _item_atual(
        client,
        chefe_almoxarifado,
        senha_valida,
        reverse("catalogo:execucao_detalhe", args=[execucao.pk]),
    )

    assert (atual.texto, atual.get("href")) == (
        "Histórico de importações",
        reverse("catalogo:historico"),
    )


def test_aria_current_na_ficha_de_usuario_marca_usuarios(client, admin_sistema, senha_valida):
    atual = _item_atual(client, admin_sistema, senha_valida, rota("usuario", admin_sistema.pk))

    assert (atual.texto, atual.get("href")) == ("Usuários", rota("usuarios"))


def test_senha_nao_marca_item_da_nav_e_o_proprio_link_senha_fica_atual(
    client, requisitante, senha_valida
):
    _login(client, requisitante, senha_valida)

    documento = analisar(client.get(rota("definir_senha")).content)

    assert _com_aria_current(documento) == []
    rodape = documento.unico(classe="meta-env")
    link_senha = [a for a in rodape.buscar("a") if a.get("href") == rota("definir_senha")]
    assert len(link_senha) == 1
    assert link_senha[0].get("aria-current") == "page"


def test_link_senha_nao_fica_atual_fora_da_tela_de_senha(client, requisitante, senha_valida):
    _login(client, requisitante, senha_valida)

    documento = analisar(client.get(reverse("home")).content)

    link_senha = [
        a for a in documento.unico(classe="meta-env").buscar("a")
        if a.get("href") == rota("definir_senha")
    ]
    assert len(link_senha) == 1
    assert "aria-current" not in link_senha[0].attrs


# ---------------------------------------------------------------------------
# 3. Credencial provisória
# ---------------------------------------------------------------------------


def test_credencial_provisoria_tem_shell_minimo_sem_navegacao_nem_destino_de_negocio(
    client, setor
):
    usuario, senha = membro_provisorio(
        setor, "PROV-SHELL-1", PAPEIS_CHEFE_ALMOXARIFADO | {Papel.ADMINISTRADOR_SISTEMA}
    )
    resposta = client.post(rota("login"), {"username": usuario.matricula, "password": senha})
    assert resposta.status_code == 302

    resposta = client.get(rota("definir_senha"))

    assert resposta.status_code == 200
    documento = analisar(resposta.content)
    lateral = documento.unico("aside", classe="side")
    assert documento.buscar("nav") == []
    # A marca é só texto: nada a que se possa navegar.
    marca = lateral.unico(classe="brand")
    assert marca.tag != "a" and marca.buscar("a") == []
    assert "Almoxarifado SAEP" in marca.texto
    # Os únicos links do shell são "Senha" (a própria página) e nada de negócio.
    destinos = hrefs_de(documento)
    assert not any(
        reverse(item["rota"]) in destinos for item in ITENS.values()
    ), destinos
    assert reverse("home") not in destinos
    assert all(a.get("href") == rota("definir_senha") for a in lateral.buscar("a"))
    # Sair continua disponível: POST + CSRF, exatamente um.
    formularios = [f for f in documento.buscar("form") if f.get("action") == reverse("logout")]
    assert len(formularios) == 1
    assert formularios[0].get("method", "").lower() == "post"
    assert formularios[0].buscar("input", name="csrfmiddlewaretoken")


# ---------------------------------------------------------------------------
# 4. Fragmentos HTMX não carregam o shell
# ---------------------------------------------------------------------------

FRAGMENTOS = [
    pytest.param("requisitante", "catalogo:consulta", id="catalogo-consulta"),
    pytest.param("funcionario_almoxarifado", "fornecedores:consulta", id="fornecedores-consulta"),
    pytest.param("admin_sistema", "usuarios", id="usuarios"),
    pytest.param("funcionario_almoxarifado", "estoque:entrada_nova", id="entrada-nova"),
]


@pytest.mark.parametrize("fixture_usuario, nome_rota", FRAGMENTOS)
def test_fragmento_htmx_nao_traz_o_shell(fixture_usuario, nome_rota, request, client, senha_valida):
    usuario = request.getfixturevalue(fixture_usuario)
    _login(client, usuario, senha_valida)

    resposta = client.get(rota(nome_rota), **HX)

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert conteudo.strip(), "pré-condição: o fragmento não é vazio"
    documento = analisar(conteudo)
    assert documento.buscar(classe="side") == []
    assert documento.buscar("aside") == []
    assert documento.buscar("main") == []
    assert documento.buscar("script") == []
    assert documento.buscar("html") == [] and documento.buscar("body") == []
    assert [f for f in documento.buscar("form") if f.get("action") == reverse("logout")] == []
    assert "Almoxarifado SAEP" not in conteudo
    assert 'class="side"' not in conteudo
    assert f'action="{reverse("logout")}"' not in conteudo
    assert "<main" not in conteudo and "<script" not in conteudo


# ---------------------------------------------------------------------------
# 5. Login anônimo
# ---------------------------------------------------------------------------


def test_login_anonimo_nao_tem_sidebar_logout_nem_link_para_a_home(client):
    resposta = client.get(reverse("login"))

    assert resposta.status_code == 200
    documento = analisar(resposta.content)
    assert documento.buscar("aside") == []
    assert documento.buscar(classe="side") == []
    assert [f for f in documento.buscar("form") if f.get("action") == reverse("logout")] == []
    assert [a for a in documento.buscar("a", href=True) if a.attrs["href"] == reverse("home")] == []
    assert documento.buscar("nav") == []
    assert documento.buscar(classe="skip") == []
