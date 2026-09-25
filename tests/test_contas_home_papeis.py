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
    TITULO_REGISTRAR_ENTRADA,
    TITULO_ATENDER_REQUISICOES,
    TITULO_HISTORICO_MOVIMENTACOES,
    TITULO_SAIDAS_EXCEPCIONAIS,
    TITULO_DEVOLUCOES,
    TITULO_AJUSTE_INVENTARIO,
    TITULO_OBSERVACOES_INTERNAS,
]

TITULOS_FUNCIONARIO_ALMOXARIFADO = [
    TITULO_SOLICITAR_MATERIAL,
    TITULO_REGISTRAR_ENTRADA,
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

TITULOS_ADMIN_SISTEMA = [
    TITULO_SOLICITAR_MATERIAL,
    TITULO_ADMINISTRACAO,
]

TITULOS_AUXILIAR_SETOR = [
    TITULO_SOLICITAR_MATERIAL,
    TITULO_HISTORICO_MOVIMENTACOES,
]

HREF_RE = re.compile(r'href="([^"]+)"')


def _hrefs_de_negocio(conteudo_html):
    """Extrai todos os `href="..."` do HTML, descartando assets estáticos
    (`/static/...`), para comparar exatamente quais rotas de negócio a Home
    expôs como link."""
    return {
        href
        for href in HREF_RE.findall(conteudo_html)
        if not href.startswith("/static/")
    }


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
    assert hrefs == {
        reverse("catalogo:consulta"),
        reverse("catalogo:importacao_envio"),
        reverse("catalogo:historico"),
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
    # Os únicos hrefs de negócio permitidos continuam sendo os três atalhos
    # reais — nenhum placeholder amplia esse conjunto.
    assert hrefs_de_negocio == {
        reverse("catalogo:consulta"),
        reverse("catalogo:importacao_envio"),
        reverse("catalogo:historico"),
    }

    for tag_abertura in re.finditer(r"<a\b[^>]*>(.*?)</a>", conteudo, re.DOTALL):
        texto_do_link = tag_abertura.group(1)
        for titulo in titulos:
            assert titulo not in texto_do_link, (
                f"placeholder {titulo!r} não deveria aparecer dentro de um <a>...</a>"
            )

    for titulo in titulos:
        assert titulo in conteudo


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
    """`admin_sistema` (REQUESTER + SYSTEM-ADMIN): único papel testado aqui
    que alcança o item 10 ("Administração de usuários e setores")."""
    _login(client, admin_sistema, senha_valida)

    response = client.get(reverse("home"))

    titulos = [item["titulo"] for item in response.context["capacidades_planejadas"]]
    assert titulos == TITULOS_ADMIN_SISTEMA


@pytest.mark.django_db
def test_capacidades_planejadas_auxiliar_setor(client, criar_usuario_com_papeis, senha_valida):
    """Auxiliar de setor (REQUESTER + SECTOR-ASSISTANT): sem fixture própria
    em `conftest.py`, criado aqui via `criar_usuario_com_papeis`, que já
    concede `ROLE-REQUESTER` por `create_user()` e preserva as invariantes de
    `contas/models.py`."""
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
    conteudo = response.content.decode()

    assert chefe_almoxarifado.matricula in conteudo
    assert response.context["setor"].nome in conteudo
    assert response.context["setor"] == chefe_almoxarifado.setor

    papeis_esperados = [
        "Requisitante",
        "Chefe de setor",
        "Funcionário do almoxarifado",
        "Chefe do almoxarifado",
    ]
    assert response.context["papeis"] == papeis_esperados
    for rotulo in papeis_esperados:
        assert rotulo in conteudo


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
