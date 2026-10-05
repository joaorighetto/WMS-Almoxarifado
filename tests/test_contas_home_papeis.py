"""Testes de visibilidade por papel na Home autenticada (redesign visual).

Cobre o contrato de contexto planejado para `contas.views.HomeView` junto do
redesign de `contas/templates/contas/home.html`: os atalhos reais continuam
condicionados às mesmas flags de sempre (`pode_consultar_catalogo`,
`pode_importar_catalogo`), mas a Home passa também a expor `setor`, `papeis`
e uma lista de capacidades futuras do ROADMAP (`capacidades_planejadas`),
filtrada por papel — nunca como link, e nunca incluindo os itens ainda "Requer
clarificação" do roadmap (Painel de Gestão / Relatórios).

Fontes: `docs/domain/permissions-matrix.md` (PERM-MATERIAL-VIEW,
PERM-SCPI-IMPORT-EXECUTE, PERM-SCPI-IMPORT-HISTORY-VIEW),
`specs/001-importacao-catalogo-materiais/contracts/rotas-e-autorizacao.md`
("Home"), spec 002 (FR-005a, FR-016, FR-017), `ROADMAP.md`.
"""

import re

import pytest
from django.urls import reverse

from contas.models import Papel
from tests.contas_helpers import rota
from tests.html_helpers import analisar, hrefs_de, secao_por_rotulo

# Títulos das capacidades planejadas, na ordem canônica definida para a Home.
TITULO_SOLICITAR_MATERIAL = "Solicitar material"
TITULO_AUTORIZAR_REQUISICOES = "Autorizar requisições do setor"
TITULO_REGISTRAR_ENTRADA = "Registrar entrada de materiais"
TITULO_ATENDER_REQUISICOES = "Atender requisições autorizadas"
TITULO_HISTORICO_MOVIMENTACOES = "Histórico de movimentações"
TITULO_SAIDAS_EXCEPCIONAIS = "Saídas excepcionais"
TITULO_DEVOLUCOES = "Devoluções"
TITULO_AJUSTE_INVENTARIO = "Ajuste de saldo por inventário"
TITULO_OBSERVACOES_INTERNAS = "Observações internas de materiais"
TITULO_ADMINISTRACAO = "Administração de usuários e setores"

TITULOS_CHEFE_ALMOXARIFADO = [
    TITULO_SOLICITAR_MATERIAL,
    TITULO_AUTORIZAR_REQUISICOES,
    TITULO_ATENDER_REQUISICOES,
    TITULO_HISTORICO_MOVIMENTACOES,
    TITULO_SAIDAS_EXCEPCIONAIS,
    TITULO_DEVOLUCOES,
    TITULO_AJUSTE_INVENTARIO,
    TITULO_OBSERVACOES_INTERNAS,
]

TITULOS_FUNCIONARIO_ALMOXARIFADO = [
    TITULO_SOLICITAR_MATERIAL,
    TITULO_ATENDER_REQUISICOES,
    TITULO_HISTORICO_MOVIMENTACOES,
    TITULO_SAIDAS_EXCEPCIONAIS,
    TITULO_OBSERVACOES_INTERNAS,
]

TITULOS_AUDITOR = [
    TITULO_SOLICITAR_MATERIAL,
    TITULO_HISTORICO_MOVIMENTACOES,
]

TITULOS_REQUISITANTE = [TITULO_SOLICITAR_MATERIAL]

TITULOS_CHEFE_SETOR = [
    TITULO_SOLICITAR_MATERIAL,
    TITULO_AUTORIZAR_REQUISICOES,
    TITULO_HISTORICO_MOVIMENTACOES,
]

# ORG deixou de ser "em preparação" (feature 005, T027/T029): o administrador agora tem os
# atalhos reais Usuários e Setores, e `TITULO_ADMINISTRACAO` não aparece mais em lista alguma.
TITULOS_ADMIN_SISTEMA = [
    TITULO_SOLICITAR_MATERIAL,
]

TITULOS_AUXILIAR_SETOR = [
    TITULO_SOLICITAR_MATERIAL,
    TITULO_HISTORICO_MOVIMENTACOES,
]

def _hrefs_de_negocio(conteudo_html):
    """Destinos de negócio que o CONTEÚDO da Home expõe como link: os `<a href>` da seção de
    tarefas (`aria-labelledby="home-tasks-heading"`). Fora dela ficam a marca, o skip link, a
    sidebar e o rodapé da conta (Senha, Sair) — shell, não capability (D-27/FR-039 da 005); a
    sidebar tem verificação própria em `_hrefs_da_sidebar`. A igualdade exata é o que prova que
    a Home não expõe destino a mais nem a menos."""
    secao = secao_por_rotulo(analisar(conteudo_html), "home-tasks-heading")
    return hrefs_de(secao)


def _hrefs_da_sidebar(conteudo_html):
    """`href` da `<nav aria-label="Seções">` da sidebar: Início (`/`) mais os mesmos destinos."""
    nav = analisar(conteudo_html).unico("nav", aria_label="Seções")
    return hrefs_de(nav)


def _login(client, usuario, senha_valida):
    logou = client.login(username=usuario.matricula, password=senha_valida)
    assert logou, "pré-condição do teste: login direto via client deveria funcionar"


# ---------------------------------------------------------------------------
# 1. Visibilidade dos links reais por papel
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_so_requisitante_ve_apenas_o_link_de_consulta_do_catalogo(
    client, requisitante, senha_valida
):
    _login(client, requisitante, senha_valida)

    response = client.get(reverse("home"))
    conteudo = response.content.decode()

    hrefs = _hrefs_de_negocio(conteudo)
    assert hrefs == {reverse("catalogo:consulta")}


@pytest.mark.django_db
def test_chefe_almoxarifado_ve_os_tres_links_de_catalogo(
    client, chefe_almoxarifado, senha_valida
):
    _login(client, chefe_almoxarifado, senha_valida)

    response = client.get(reverse("home"))
    conteudo = response.content.decode()

    hrefs = _hrefs_de_negocio(conteudo)
    # `chefe_almoxarifado` também tem `ROLE-WAREHOUSE-HEAD` e `ROLE-WAREHOUSE-
    # STAFF` (`pode_importar_fornecedores` e `pode_consultar_fornecedores`,
    # feature 004/T019 e T024/T027): além dos três links de catálogo, vê os
    # três de fornecedores (consulta, importação e histórico) e os dois de
    # estoque (registrar entrada e consultar entradas, feature 003/T019/T024).
    assert hrefs == {
        reverse("catalogo:consulta"),
        reverse("catalogo:importacao_envio"),
        reverse("catalogo:historico"),
        reverse("fornecedores:consulta"),
        reverse("fornecedores:importacao_envio"),
        reverse("fornecedores:historico"),
        reverse("estoque:entrada_nova"),
        reverse("estoque:entradas"),
    }


@pytest.mark.django_db
def test_usuario_sem_requester_e_sem_warehouse_head_nao_ve_nenhum_link_de_catalogo(
    client, superusuario_tecnico, senha_valida
):
    """Conta técnica (`create_superuser`): nenhum `ROLE-*` de negócio
    (`permissions-matrix.md`, regras 7-8) — não pode ter `ROLE-REQUESTER` nem
    `ROLE-WAREHOUSE-HEAD`, então nenhum dos três atalhos de catálogo aparece.
    Uma identidade de negócio ativa comum não serve para este cenário: o
    invariante de `contas/models.py` (`User.save()`) exige `ROLE-REQUESTER`
    em toda identidade ativa não-superusuário, então "sem nenhum dos dois
    papéis" só é alcançável por uma conta técnica."""
    _login(client, superusuario_tecnico, senha_valida)

    response = client.get(reverse("home"))
    conteudo = response.content.decode()

    hrefs = _hrefs_de_negocio(conteudo)
    assert hrefs == set()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "fixture_usuario",
    [
        "requisitante",
        "auditor",
        "funcionario_almoxarifado",
        "chefe_almoxarifado",
        "admin_sistema",
        "superusuario_tecnico",
    ],
)
def test_sidebar_e_conteudo_da_home_oferecem_exatamente_os_mesmos_destinos(
    client, senha_valida, fixture_usuario, request
):
    """A sidebar e a seção de tarefas da Home saem da mesma fonte: os destinos de negócio são
    idênticos, e a sidebar acrescenta apenas o Início (`/`)."""
    usuario = request.getfixturevalue(fixture_usuario)
    _login(client, usuario, senha_valida)

    conteudo = client.get(reverse("home")).content.decode()

    assert _hrefs_da_sidebar(conteudo) == _hrefs_de_negocio(conteudo) | {reverse("home")}


# ---------------------------------------------------------------------------
# 2. Placeholders de capacidades futuras nunca são links
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_titulos_de_capacidades_planejadas_nao_aparecem_como_links(
    client, chefe_almoxarifado, senha_valida
):
    _login(client, chefe_almoxarifado, senha_valida)

    response = client.get(reverse("home"))
    conteudo = response.content.decode()

    titulos = [item["titulo"] for item in response.context["capacidades_planejadas"]]
    assert titulos, "pré-condição: chefe do almoxarifado deveria ter capacidades planejadas"

    hrefs_de_negocio = _hrefs_de_negocio(conteudo)
    # Os únicos hrefs de negócio permitidos continuam sendo os atalhos reais
    # de `chefe_almoxarifado` (três de catálogo + três de fornecedores + dois
    # de estoque, ver `test_chefe_almoxarifado_ve_os_tres_links_de_catalogo`)
    # — nenhum placeholder amplia esse conjunto.
    assert hrefs_de_negocio == {
        reverse("catalogo:consulta"),
        reverse("catalogo:importacao_envio"),
        reverse("catalogo:historico"),
        reverse("fornecedores:consulta"),
        reverse("fornecedores:importacao_envio"),
        reverse("fornecedores:historico"),
        reverse("estoque:entrada_nova"),
        reverse("estoque:entradas"),
    }

    for tag_abertura in re.finditer(r"<a\b[^>]*>(.*?)</a>", conteudo, re.DOTALL):
        texto_do_link = tag_abertura.group(1)
        for titulo in titulos:
            assert titulo not in texto_do_link, (
                f"placeholder {titulo!r} não deveria aparecer dentro de um <a>...</a>"
            )

    for titulo in titulos:
        assert titulo in conteudo

    # Os títulos estão na seção "Em preparação", e a seção inteira não tem link algum.
    em_preparacao = secao_por_rotulo(analisar(conteudo), "home-planned-heading")
    assert em_preparacao.buscar("a") == []
    for titulo in titulos:
        assert titulo in em_preparacao.texto


@pytest.mark.django_db
def test_home_sem_capacidades_planejadas_nao_mostra_a_secao_em_preparacao(
    client, superusuario_tecnico, senha_valida
):
    _login(client, superusuario_tecnico, senha_valida)

    documento = analisar(client.get(reverse("home")).content.decode())

    assert documento.buscar(aria_labelledby="home-planned-heading") == []
    assert "Em preparação" not in documento.texto


@pytest.mark.django_db
def test_home_sem_tarefas_mostra_o_estado_vazio_e_nenhum_link_de_tarefa(
    client, superusuario_tecnico, senha_valida
):
    """Conta técnica: nenhum papel, nenhuma tarefa. A seção de tarefas continua existindo, com o
    texto de estado vazio e sem link algum."""
    _login(client, superusuario_tecnico, senha_valida)

    documento = analisar(client.get(reverse("home")).content.decode())

    tarefas = secao_por_rotulo(documento, "home-tasks-heading")
    assert tarefas.buscar("a") == []
    assert "Nenhuma tarefa disponível para os seus papéis atuais." in tarefas.texto


# ---------------------------------------------------------------------------
# 3. Filtro de capacidades_planejadas por papel (context, títulos, ordem)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_capacidades_planejadas_so_requisitante(client, requisitante, senha_valida):
    _login(client, requisitante, senha_valida)

    response = client.get(reverse("home"))

    titulos = [item["titulo"] for item in response.context["capacidades_planejadas"]]
    assert titulos == TITULOS_REQUISITANTE


@pytest.mark.django_db
def test_capacidades_planejadas_chefe_almoxarifado(client, chefe_almoxarifado, senha_valida):
    _login(client, chefe_almoxarifado, senha_valida)

    response = client.get(reverse("home"))

    titulos = [item["titulo"] for item in response.context["capacidades_planejadas"]]
    assert titulos == TITULOS_CHEFE_ALMOXARIFADO


@pytest.mark.django_db
def test_capacidades_planejadas_funcionario_almoxarifado(
    client, funcionario_almoxarifado, senha_valida
):
    _login(client, funcionario_almoxarifado, senha_valida)

    response = client.get(reverse("home"))

    titulos = [item["titulo"] for item in response.context["capacidades_planejadas"]]
    assert titulos == TITULOS_FUNCIONARIO_ALMOXARIFADO


@pytest.mark.django_db
def test_capacidades_planejadas_auditor(client, auditor, senha_valida):
    _login(client, auditor, senha_valida)

    response = client.get(reverse("home"))

    titulos = [item["titulo"] for item in response.context["capacidades_planejadas"]]
    assert titulos == TITULOS_AUDITOR


@pytest.mark.django_db
def test_capacidades_planejadas_chefe_de_outro_setor(client, chefe_setor, senha_valida):
    """`chefe_setor` (REQUESTER + SECTOR-HEAD, sem WAREHOUSE-HEAD): confirma
    que o item 2 ("Autorizar requisições do setor") reage a `ROLE-SECTOR-HEAD`
    isoladamente, distinto de `chefe_almoxarifado` — troca `CHEFE_SETOR` por
    `CHEFE_ALMOXARIFADO` no mapeamento de papel → capacidade."""
    _login(client, chefe_setor, senha_valida)

    response = client.get(reverse("home"))

    titulos = [item["titulo"] for item in response.context["capacidades_planejadas"]]
    assert titulos == TITULOS_CHEFE_SETOR


@pytest.mark.django_db
def test_capacidades_planejadas_admin_sistema(client, admin_sistema, senha_valida):
    """`admin_sistema` (REQUESTER + SYSTEM-ADMIN): o item de administração saiu de "Em
    preparação" (feature 005, T029) e virou os atalhos reais; só sobra o que todo
    requisitante vê."""
    _login(client, admin_sistema, senha_valida)

    response = client.get(reverse("home"))

    titulos = [item["titulo"] for item in response.context["capacidades_planejadas"]]
    assert titulos == TITULOS_ADMIN_SISTEMA


@pytest.mark.django_db
def test_capacidades_planejadas_auxiliar_setor(client, criar_usuario_com_papeis, senha_valida):
    """Auxiliar de setor (REQUESTER + SECTOR-ASSISTANT): sem fixture própria
    em `conftest.py`, criado aqui via `criar_usuario_com_papeis`, que já
    concede `ROLE-REQUESTER` pela API de provisionamento e preserva as
    invariantes de `contas/organizacao.py`."""
    usuario = criar_usuario_com_papeis(Papel.AUXILIAR_SETOR)
    _login(client, usuario, senha_valida)

    response = client.get(reverse("home"))

    titulos = [item["titulo"] for item in response.context["capacidades_planejadas"]]
    assert titulos == TITULOS_AUXILIAR_SETOR


@pytest.mark.django_db
def test_capacidades_planejadas_e_papeis_superusuario_tecnico_sao_vazios(
    client, superusuario_tecnico, senha_valida
):
    """Conta técnica: nenhum `ROLE-*` de negócio (`permissions-matrix.md`,
    regras 7-8) — nenhuma capacidade planejada e nenhum rótulo de papel."""
    _login(client, superusuario_tecnico, senha_valida)

    response = client.get(reverse("home"))

    assert response.context["capacidades_planejadas"] == []
    assert response.context["papeis"] == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    "fixture_usuario",
    [
        "requisitante",
        "chefe_almoxarifado",
        "funcionario_almoxarifado",
        "auditor",
        "admin_sistema",
    ],
)
def test_nenhuma_capacidade_planejada_e_painel_de_gestao_ou_relatorio(
    client, senha_valida, fixture_usuario, request
):
    """`PERM-ALMOX-MANAGEMENT-PANEL-VIEW` (Painel de Gestão) e os itens `REL`
    de relatórios seguem "Requer clarificação" no `ROADMAP.md` — nenhum dos
    dois pode aparecer como capacidade planejada na Home, para nenhum papel."""
    usuario = request.getfixturevalue(fixture_usuario)
    _login(client, usuario, senha_valida)

    response = client.get(reverse("home"))

    titulos = [item["titulo"] for item in response.context["capacidades_planejadas"]]
    for titulo in titulos:
        assert "Painel" not in titulo
        assert "Relatório" not in titulo
        assert "Relatorio" not in titulo


# ---------------------------------------------------------------------------
# 4. Identidade exibida: matrícula, setor e papéis
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_home_exibe_matricula_setor_e_rotulos_dos_papeis(
    client, chefe_almoxarifado, senha_valida
):
    _login(client, chefe_almoxarifado, senha_valida)

    response = client.get(reverse("home"))
    assert response.context["setor"] == chefe_almoxarifado.setor

    papeis_esperados = [
        "Requisitante",
        "Chefe de setor",
        "Funcionário do almoxarifado",
        "Chefe do almoxarifado",
    ]
    assert response.context["papeis"] == papeis_esperados

    # A identidade vive nos tiles do conteúdo (a sidebar repete matrícula e setor no rodapé, o
    # que não prova nada sobre a Home): matrícula e setor em seus tiles, papéis como badges.
    tiles = _tiles_de_identidade(response.content.decode())
    assert tiles["Matrícula"].texto == chefe_almoxarifado.matricula
    assert tiles["Setor"].texto == chefe_almoxarifado.setor.nome
    badges = [badge.texto for badge in tiles["Papéis"].buscar(classe="badge")]
    assert badges == papeis_esperados


@pytest.mark.django_db
def test_home_sem_papel_de_negocio_diz_que_nenhum_papel_foi_atribuido(
    client, superusuario_tecnico, senha_valida
):
    _login(client, superusuario_tecnico, senha_valida)

    tiles = _tiles_de_identidade(client.get(reverse("home")).content.decode())

    assert tiles["Papéis"].buscar(classe="badge") == []
    assert "Nenhum papel de negócio atribuído." in tiles["Papéis"].texto


def _tiles_de_identidade(conteudo_html):
    """`rótulo -> <dd>` dos tiles de identidade (`<dl aria-label="Identidade">`)."""
    lista = analisar(conteudo_html).unico("dl", aria_label="Identidade")
    tiles = {}
    for tile in lista.buscar(classe="tile"):
        rotulo = tile.unico("dt").texto
        tiles[rotulo] = tile.unico("dd")
    assert list(tiles) == ["Matrícula", "Setor", "Papéis"]
    return tiles


@pytest.mark.django_db
def test_home_papeis_do_requisitante_e_so_o_rotulo_minimo(
    client, requisitante, senha_valida
):
    _login(client, requisitante, senha_valida)

    response = client.get(reverse("home"))

    assert response.context["papeis"] == ["Requisitante"]


# ---------------------------------------------------------------------------
# 5. Logout continua POST com CSRF a partir da Home
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_home_expoe_logout_como_formulario_post_com_csrf_nao_como_link(
    client, usuario_ativo, senha_valida
):
    _login(client, usuario_ativo, senha_valida)

    response = client.get(reverse("home"))
    conteudo = response.content.decode()

    url_logout = reverse("logout")

    assert re.search(
        rf'<form[^>]*method="post"[^>]*action="{re.escape(url_logout)}"', conteudo
    ) or re.search(
        rf'<form[^>]*action="{re.escape(url_logout)}"[^>]*method="post"', conteudo
    )
    assert "csrfmiddlewaretoken" in conteudo
    assert f'<a href="{url_logout}"' not in conteudo


# ---------------------------------------------------------------------------
# 7. Número de queries da Home estável (protege contra N+1)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_home_nao_introduz_n_mais_1_ao_calcular_papeis_e_capacidades(
    client, chefe_almoxarifado, senha_valida, django_assert_max_num_queries
):
    _login(client, chefe_almoxarifado, senha_valida)

    # Teto generoso (sessão/usuário + papéis + setor, sem crescer por item de
    # `capacidades_planejadas` nem por papel): qualquer implementação que
    # dispare uma query por papel ou por capacidade planejada deve estourá-lo.
    with django_assert_max_num_queries(10):
        client.get(reverse("home"))


# ---------------------------------------------------------------------------
# 8. Flags de fornecedores (feature 004 — T018): pode_importar_fornecedores
# (ROLE-WAREHOUSE-HEAD, PERM-SUPPLIER-IMPORT-EXECUTE) e
# pode_consultar_fornecedores (ROLE-WAREHOUSE-STAFF, PERM-SUPPLIER-VIEW). O
# link real na Home é do T019 (frontend-implementer) — aqui só o contexto.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_chefe_almoxarifado_tem_as_duas_flags_de_fornecedores(
    client, chefe_almoxarifado, senha_valida
):
    """`chefe_almoxarifado` tem tanto `ROLE-WAREHOUSE-HEAD` quanto
    `ROLE-WAREHOUSE-STAFF` (ver `test_home_exibe_matricula_setor_e_rotulos_dos_papeis`),
    então as duas flags de fornecedores são verdadeiras."""
    _login(client, chefe_almoxarifado, senha_valida)

    response = client.get(reverse("home"))

    assert response.context["pode_importar_fornecedores"] is True
    assert response.context["pode_consultar_fornecedores"] is True


@pytest.mark.django_db
def test_funcionario_almoxarifado_so_tem_a_flag_de_consulta_de_fornecedores(
    client, funcionario_almoxarifado, senha_valida
):
    """`ROLE-WAREHOUSE-STAFF`, sem `ROLE-WAREHOUSE-HEAD`: pode consultar
    fornecedores, mas não importar."""
    _login(client, funcionario_almoxarifado, senha_valida)

    response = client.get(reverse("home"))

    assert response.context["pode_importar_fornecedores"] is False
    assert response.context["pode_consultar_fornecedores"] is True


@pytest.mark.django_db
def test_requisitante_nao_tem_nenhuma_flag_de_fornecedores(client, requisitante, senha_valida):
    _login(client, requisitante, senha_valida)

    response = client.get(reverse("home"))

    assert response.context["pode_importar_fornecedores"] is False
    assert response.context["pode_consultar_fornecedores"] is False


# ---------------------------------------------------------------------------
# 9. Atalhos de estoque (spec 003 — entrada de materiais, T019/T021/T024):
# `pode_registrar_entrada` (ROLE-WAREHOUSE-STAFF, PERM-STOCK-ENTRY-CREATE) e
# `pode_consultar_entradas` (ROLE-WAREHOUSE-STAFF ou ROLE-AUDITOR, recorte de
# PERM-STOCK-HISTORY-VIEW fixado por FR-021). Acréscimo do test-engineer
# (T004/T021) — os links reais (`estoque:entrada_nova`/`estoque:entradas`) e
# a saída do item ENT de `CAPACIDADES_PLANEJADAS` são do `task-implementer`
# (T019/T024); até lá, estes testes falham por rota inexistente
# (`NoReverseMatch`), o que é esperado (TDD).
#
# Resolvido pelo `task-implementer` (T019/T024): `TITULO_REGISTRAR_ENTRADA`
# saiu de `TITULOS_CHEFE_ALMOXARIFADO`/`TITULOS_FUNCIONARIO_ALMOXARIFADO` (a
# capacidade agora tem link real, não é mais planejada) e os testes de hrefs
# das seções 1 e 2 acima já contam `estoque:entrada_nova`/`estoque:entradas`.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_funcionario_almoxarifado_tem_as_duas_flags_de_estoque(
    client, funcionario_almoxarifado, senha_valida
):
    _login(client, funcionario_almoxarifado, senha_valida)

    response = client.get(reverse("home"))

    assert response.context["pode_registrar_entrada"] is True
    assert response.context["pode_consultar_entradas"] is True


@pytest.mark.django_db
def test_auditor_so_tem_a_flag_de_consulta_de_entradas(client, auditor, senha_valida):
    _login(client, auditor, senha_valida)

    response = client.get(reverse("home"))

    assert response.context["pode_registrar_entrada"] is False
    assert response.context["pode_consultar_entradas"] is True


@pytest.mark.django_db
def test_requisitante_nao_tem_nenhuma_flag_de_estoque(client, requisitante, senha_valida):
    _login(client, requisitante, senha_valida)

    response = client.get(reverse("home"))

    assert response.context["pode_registrar_entrada"] is False
    assert response.context["pode_consultar_entradas"] is False


@pytest.mark.django_db
def test_funcionario_almoxarifado_ve_os_links_reais_de_registrar_e_consultar_entradas(
    client, funcionario_almoxarifado, senha_valida
):
    _login(client, funcionario_almoxarifado, senha_valida)

    response = client.get(reverse("home"))
    hrefs = _hrefs_de_negocio(response.content.decode())

    assert reverse("estoque:entrada_nova") in hrefs
    assert reverse("estoque:entradas") in hrefs


@pytest.mark.django_db
def test_auditor_ve_apenas_o_link_de_consultar_entradas_nao_o_de_registrar(
    client, auditor, senha_valida
):
    _login(client, auditor, senha_valida)

    response = client.get(reverse("home"))
    hrefs = _hrefs_de_negocio(response.content.decode())

    assert reverse("estoque:entradas") in hrefs
    assert reverse("estoque:entrada_nova") not in hrefs


# ---------------------------------------------------------------------------
# 10. Atalhos de administração da organização (feature 005 — T027/T029/T030):
# `pode_administrar_organizacao` (ROLE-SYSTEM-ADMIN, PERM-USER-MANAGE e
# PERM-SECTOR-MANAGE) e os atalhos Usuários e Setores. O item ORG sai de
# `CAPACIDADES_PLANEJADAS` ("Em preparação"). Os links são conveniência: a
# autorização efetiva é das rotas (`test_contas_permissoes_organizacao.py`).
# ---------------------------------------------------------------------------

PAPEIS_SEM_ADMINISTRACAO = [
    "requisitante",
    "chefe_setor",
    "auditor",
    "funcionario_almoxarifado",
    "chefe_almoxarifado",
    "superusuario_tecnico",
]


def _texto_do_link(conteudo_html, url):
    """Texto do primeiro `<a href="url">...</a>` (vazio se não houver o link)."""
    achado = re.search(
        rf'<a\b[^>]*href="{re.escape(url)}"[^>]*>(.*?)</a>', conteudo_html, re.DOTALL
    )
    return re.sub(r"<[^>]+>|\s+", " ", achado.group(1)).strip() if achado else ""


@pytest.mark.django_db
def test_administrador_ve_so_os_atalhos_de_usuarios_e_setores_alem_do_catalogo(
    client, admin_sistema, senha_valida
):
    """`ROLE-SYSTEM-ADMIN` não concede poder operacional (FR-003, SC-008): além do
    atalho que todo requisitante tem, só os dois de administração — nenhum de
    importação, fornecedores ou estoque."""
    _login(client, admin_sistema, senha_valida)

    response = client.get(reverse("home"))
    conteudo = response.content.decode()

    assert response.context["pode_administrar_organizacao"] is True
    assert _hrefs_de_negocio(conteudo) == {
        reverse("catalogo:consulta"),
        rota("usuarios"),
        rota("setores"),
    }
    assert "Usuários" in _texto_do_link(conteudo, rota("usuarios"))
    assert "Setores" in _texto_do_link(conteudo, rota("setores"))


@pytest.mark.django_db
@pytest.mark.parametrize("fixture_usuario", PAPEIS_SEM_ADMINISTRACAO)
def test_so_o_administrador_tem_os_atalhos_de_usuarios_e_setores(
    client, senha_valida, fixture_usuario, request
):
    usuario = request.getfixturevalue(fixture_usuario)
    _login(client, usuario, senha_valida)

    response = client.get(reverse("home"))

    assert response.context["pode_administrar_organizacao"] is False
    hrefs = _hrefs_de_negocio(response.content.decode())
    assert rota("usuarios") not in hrefs
    assert rota("setores") not in hrefs


@pytest.mark.django_db
def test_administrador_com_papeis_operacionais_tem_os_dois_conjuntos_de_atalhos(
    client, criar_usuario_com_papeis, senha_valida
):
    usuario = criar_usuario_com_papeis(
        Papel.ADMINISTRADOR_SISTEMA, Papel.CHEFE_SETOR, Papel.CHEFE_ALMOXARIFADO,
        Papel.FUNCIONARIO_ALMOXARIFADO,
    )  # fmt: skip
    _login(client, usuario, senha_valida)

    hrefs = _hrefs_de_negocio(client.get(reverse("home")).content.decode())

    assert {rota("usuarios"), rota("setores")} <= hrefs
    assert {reverse("catalogo:importacao_envio"), reverse("estoque:entrada_nova")} <= hrefs


@pytest.mark.django_db
@pytest.mark.parametrize(
    "fixture_usuario", ["admin_sistema", *PAPEIS_SEM_ADMINISTRACAO]
)
def test_o_item_de_administracao_nao_esta_mais_em_preparacao_para_nenhum_papel(
    client, senha_valida, fixture_usuario, request
):
    usuario = request.getfixturevalue(fixture_usuario)
    _login(client, usuario, senha_valida)

    response = client.get(reverse("home"))

    titulos = [item["titulo"] for item in response.context["capacidades_planejadas"]]
    assert TITULO_ADMINISTRACAO not in titulos


@pytest.mark.django_db
def test_home_do_administrador_nao_introduz_n_mais_1(
    client, admin_sistema, senha_valida, django_assert_max_num_queries
):
    _login(client, admin_sistema, senha_valida)

    with django_assert_max_num_queries(10):
        client.get(reverse("home"))
