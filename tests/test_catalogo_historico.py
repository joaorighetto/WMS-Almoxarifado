"""Testes do histórico de importações do catálogo (T036 — US3, FR-033–FR-037).

TDD: escrito antes de `catalogo:historico`/`HistoricoImportacoesView` (T038) e do
template `catalogo/historico.html` (T040) existirem. Toda chamada de `reverse()`
fica dentro do corpo dos testes, para que a ausência da rota derrube só o teste
que a usa (`NoReverseMatch`), não a coleta do arquivo inteiro — mesma convenção de
`tests/test_catalogo_permissoes.py`.

Cobre `contracts/rotas-e-autorizacao.md` → "GET /catalogo/importacoes/" e
"GET /catalogo/importacoes/<pk>/". Autorização em si é T037
(`tests/test_catalogo_permissoes.py`, seção `ROTAS_HISTORICO`); aqui o usuário é
sempre `chefe_almoxarifado`, e o foco é o comportamento observável.

Decisões documentadas para os implementadores de T038/T040:

- **Parâmetro de página**: `pagina`, o mesmo da consulta (`contracts/rotas-e-autorizacao.md`)
  e o que `catalogo/_paginacao.html` recebe como `parametro`. Decisão do
  coordenador: T038 declara `page_kwarg = "pagina"` no `ListView`.
- **Estado vazio**: sem nenhuma execução, o template (T040) DEVE emitir um
  elemento com `data-estado="vazio"` na região da lista, seguindo o mesmo
  padrão já adotado pela consulta do catálogo (partial `resultados_consulta`,
  `catalogo/templates/catalogo/consulta.html`; `tests/test_catalogo_consulta.py`).
- **Colunas exibidas**: matrícula de quem executou (`executada_por.matricula`),
  momento (`concluida_em`), nome do arquivo, e os totais (recebidos, inseridos,
  atualizados, rejeitados, divergências) — conforme
  `contracts/rotas-e-autorizacao.md` → "GET /catalogo/importacoes/". Os testes
  abaixo verificam a presença desses valores no HTML, nunca a estrutura de
  markup.
- Cada linha do histórico leva ao detalhe da execução
  (`catalogo:execucao_detalhe`, pk): os testes verificam que o `href` de cada
  execução aparece na página.
"""

import re
import uuid
from datetime import timedelta
from urllib.parse import urlsplit

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from django.utils import timezone

from catalogo.models import ExcecaoImportacao, ExecucaoImportacao, MotivoRecusa

pytestmark = pytest.mark.django_db

SHA256_FAKE = "0" * 64


def _cliente_autenticado(usuario):
    client = Client()
    client.force_login(usuario)
    return client


def _enviar(client, conteudo, nome="arquivo.csv"):
    arquivo = SimpleUploadedFile(nome, conteudo, content_type="text/csv")
    return client.post(reverse("catalogo:importacao_envio"), {"arquivo": arquivo})


def _importar_via_http(client, conteudo, nome="arquivo.csv"):
    """Executa o fluxo real de importação (envio → confirmação) e devolve a
    `ExecucaoImportacao` criada, usando só a interface interna fixada em
    `contracts/interface-importacao.md` (mesma técnica de
    `tests/test_catalogo_views_importacao.py`)."""
    from catalogo import importacao

    resposta_envio = _enviar(client, conteudo, nome)
    assert resposta_envio.status_code == 302

    pedido = importacao.obter_pedido(client.session)
    assert pedido is not None
    plano = importacao.calcular_plano(pedido.conteudo)

    resposta_confirmar = client.post(
        reverse("catalogo:importacao_confirmar"),
        {"token": pedido.token, "impressao_digital": plano.impressao_digital},
    )
    assert resposta_confirmar.status_code == 302
    destino = resolve(urlsplit(resposta_confirmar.url).path)
    assert destino.view_name == "catalogo:execucao_detalhe"
    return ExecucaoImportacao.objects.get(pk=destino.kwargs["pk"])


def _criar_execucao(*, executada_por, concluida_em=None, nome_arquivo="carga.csv", **totais):
    valores_totais = {
        "total_recebidos": 1,
        "total_inseridos": 1,
        "total_atualizados": 0,
        "total_atualizados_com_alteracao": 0,
        "total_rejeitados": 0,
        "total_divergencias": 0,
        "total_ausentes_no_arquivo": 0,
        **totais,
    }
    return ExecucaoImportacao.objects.create(
        token_previa=uuid.uuid4(),
        executada_por=executada_por,
        concluida_em=concluida_em or timezone.now(),
        nome_arquivo=nome_arquivo,
        tamanho_arquivo=10,
        sha256_arquivo=SHA256_FAKE,
        **valores_totais,
    )


def _totais_da_execucao(pk):
    execucao = ExecucaoImportacao.objects.get(pk=pk)
    return (
        execucao.total_recebidos,
        execucao.total_inseridos,
        execucao.total_atualizados,
        execucao.total_atualizados_com_alteracao,
        execucao.total_rejeitados,
        execucao.total_divergencias,
        execucao.total_ausentes_no_arquivo,
    )


def _excecoes_da_execucao(pk):
    return frozenset(
        (
            excecao.linha_inicial,
            excecao.linha_final,
            excecao.cadpro,
            excecao.motivo,
            excecao.detalhe,
        )
        for excecao in ExcecaoImportacao.objects.filter(execucao_id=pk)
    )


# ---------------------------------------------------------------------------
# Listagem: ordem, dados essenciais, estado vazio, link para o detalhe.
# ---------------------------------------------------------------------------


def test_historico_lista_da_mais_recente_para_a_mais_antiga_com_dados_essenciais(
    client, chefe_almoxarifado, criar_usuario
):
    usuario_antiga = criar_usuario()
    usuario_recente = criar_usuario()
    agora = timezone.now()

    _criar_execucao(
        executada_por=usuario_antiga,
        concluida_em=agora - timedelta(days=1),
        nome_arquivo="carga-antiga.csv",
        total_recebidos=5,
        total_inseridos=5,
    )
    _criar_execucao(
        executada_por=usuario_recente,
        concluida_em=agora,
        nome_arquivo="carga-recente.csv",
        total_recebidos=22,
        total_inseridos=9,
        total_rejeitados=13,
    )

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("catalogo:historico"))

    assert resposta.status_code == 200

    # Contexto primeiro: confirma que a view passou a execução recente com
    # os totais esperados (fonte de verdade do que o template deve exibir).
    execucoes_por_arquivo = {e.nome_arquivo: e for e in resposta.context["object_list"]}
    recente = execucoes_por_arquivo["carga-recente.csv"]
    assert (recente.total_recebidos, recente.total_inseridos, recente.total_rejeitados) == (
        22,
        9,
        13,
    )

    conteudo = resposta.content.decode("utf-8")
    for esperado in (
        usuario_antiga.matricula,
        usuario_recente.matricula,
        "carga-antiga.csv",
        "carga-recente.csv",
    ):
        assert esperado in conteudo, f"{esperado!r} deveria aparecer no histórico"

    posicao_recente = conteudo.index("carga-recente.csv")
    posicao_antiga = conteudo.index("carga-antiga.csv")
    assert posicao_recente < posicao_antiga, (
        "a execução mais recente (-concluida_em) deve aparecer antes da mais antiga"
    )

    # Os totais precisam aparecer nas células numéricas da LINHA da execução
    # recente (`catalogo/templates/catalogo/historico.html`), não em
    # qualquer trecho do HTML — "22"/"9"/"13" soltos poderiam coincidir com
    # data ou matrícula. A fatia [posicao_recente:posicao_antiga] cobre
    # exatamente o restante da linha "carga-recente.csv" (arquivo vem antes
    # dos totais na mesma `<tr>`) até o início da linha seguinte.
    linha_recente = conteudo[posicao_recente:posicao_antiga]
    for total_esperado in ("22", "9", "13"):
        # `class="table-cell-numeric"` pode vir seguida de um modificador
        # (ex.: `catalogo-rejeitados-emphasis`, quando o total for
        # "Rejeitados" e diferente de zero — revisão do gate visual, achado
        # P1, 2026-09-22) — o teste verifica a classe base, não a ausência de
        # outras.
        assert re.search(
            rf'<td class="table-cell-numeric[^"]*">\s*{total_esperado}\s*</td>', linha_recente
        ), f"total {total_esperado!r} não encontrado numa célula numérica da linha recente"


def test_historico_sem_execucoes_mostra_estado_vazio_explicito(client, chefe_almoxarifado):
    """Documenta o marcador estável exigido do template (T040): um elemento
    com `data-estado="vazio"`, mesmo padrão do partial `resultados_consulta`
    da consulta do catálogo (`tests/test_catalogo_consulta.py`)."""
    client.force_login(chefe_almoxarifado)

    resposta = client.get(reverse("catalogo:historico"))

    assert resposta.status_code == 200
    assert len(resposta.context["object_list"]) == 0
    assert 'data-estado="vazio"' in resposta.content.decode("utf-8")


def test_cada_execucao_do_historico_leva_ao_detalhe(client, chefe_almoxarifado, criar_usuario):
    usuario = criar_usuario()
    execucao = _criar_execucao(executada_por=usuario)

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("catalogo:historico"))

    href_esperado = reverse("catalogo:execucao_detalhe", args=[execucao.pk])
    assert href_esperado in resposta.content.decode("utf-8")


# ---------------------------------------------------------------------------
# Ordenação por coluna (FR-037a, emenda de 2026-09-22, `OrdenacaoMixin`,
# `catalogo/ordenacao.py`) — mesma infraestrutura e mesmo padrão de teste da
# consulta do catálogo (`tests/test_catalogo_consulta.py`, seção "Cabeçalho
# ordenável"/"Ordenação").
# ---------------------------------------------------------------------------


def _th(conteudo, texto_visivel):
    """Extrai o bloco `<th ...>...</th>` que contém `texto_visivel` (mesma
    técnica de `tests/test_catalogo_consulta.py::_th`) — os `<th>` da tabela
    não são aninhados, então cada correspondência não gulosa já para no
    próprio fechamento."""
    for bloco in re.findall(r"<th\b.*?</th>", conteudo, re.S):
        if texto_visivel in bloco:
            return bloco
    raise AssertionError(f"cabeçalho com {texto_visivel!r} não encontrado")


def test_historico_ordem_padrao_e_por_data_de_conclusao_decrescente(
    client, chefe_almoxarifado, criar_usuario
):
    usuario = criar_usuario()
    agora = timezone.now()
    _criar_execucao(
        executada_por=usuario, concluida_em=agora - timedelta(days=1), nome_arquivo="antiga.csv"
    )
    _criar_execucao(executada_por=usuario, concluida_em=agora, nome_arquivo="recente.csv")

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("catalogo:historico"))

    assert resposta.status_code == 200
    assert resposta.context["ordem"] == "-concluida"
    conteudo = resposta.content.decode("utf-8")
    assert conteudo.index("recente.csv") < conteudo.index("antiga.csv")
    assert "2 execuções no total" in conteudo
    assert "· ordenado por data de conclusão, decrescente" in conteudo


@pytest.mark.parametrize("ordem_param, decrescente", [("concluida", False), ("-concluida", True)])
def test_historico_ordenacao_por_concluida_em(
    client, chefe_almoxarifado, criar_usuario, ordem_param, decrescente
):
    usuario = criar_usuario()
    agora = timezone.now()
    _criar_execucao(
        executada_por=usuario, concluida_em=agora - timedelta(days=2), nome_arquivo="c.csv"
    )
    _criar_execucao(
        executada_por=usuario, concluida_em=agora - timedelta(days=1), nome_arquivo="b.csv"
    )
    _criar_execucao(executada_por=usuario, concluida_em=agora, nome_arquivo="a.csv")

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("catalogo:historico"), {"ordem": ordem_param})

    assert resposta.context["ordem"] == ordem_param
    arquivos = ["c.csv", "b.csv", "a.csv"]  # da mais antiga para a mais recente
    if decrescente:
        arquivos = list(reversed(arquivos))
    conteudo = resposta.content.decode("utf-8")
    posicoes = [conteudo.index(a) for a in arquivos]
    assert posicoes == sorted(posicoes)


@pytest.mark.parametrize("ordem_param, decrescente", [("executor", False), ("-executor", True)])
def test_historico_ordenacao_por_executor(
    client, chefe_almoxarifado, criar_usuario, ordem_param, decrescente
):
    usuario_a = criar_usuario(matricula="0000001")
    usuario_b = criar_usuario(matricula="0000002")
    usuario_c = criar_usuario(matricula="0000003")
    _criar_execucao(executada_por=usuario_c, nome_arquivo="exec-c.csv")
    _criar_execucao(executada_por=usuario_a, nome_arquivo="exec-a.csv")
    _criar_execucao(executada_por=usuario_b, nome_arquivo="exec-b.csv")

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("catalogo:historico"), {"ordem": ordem_param})

    arquivos = ["exec-a.csv", "exec-b.csv", "exec-c.csv"]
    if decrescente:
        arquivos = list(reversed(arquivos))
    conteudo = resposta.content.decode("utf-8")
    posicoes = [conteudo.index(a) for a in arquivos]
    assert posicoes == sorted(posicoes)


@pytest.mark.parametrize("ordem_param, decrescente", [("recebidos", False), ("-recebidos", True)])
def test_historico_ordenacao_por_recebidos(
    client, chefe_almoxarifado, criar_usuario, ordem_param, decrescente
):
    usuario = criar_usuario()
    _criar_execucao(
        executada_por=usuario, nome_arquivo="r-baixo.csv", total_recebidos=1, total_inseridos=1
    )
    _criar_execucao(
        executada_por=usuario, nome_arquivo="r-medio.csv", total_recebidos=5, total_inseridos=5
    )
    _criar_execucao(
        executada_por=usuario, nome_arquivo="r-alto.csv", total_recebidos=10, total_inseridos=10
    )

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("catalogo:historico"), {"ordem": ordem_param})

    arquivos = ["r-baixo.csv", "r-medio.csv", "r-alto.csv"]
    if decrescente:
        arquivos = list(reversed(arquivos))
    conteudo = resposta.content.decode("utf-8")
    posicoes = [conteudo.index(a) for a in arquivos]
    assert posicoes == sorted(posicoes)


@pytest.mark.parametrize(
    "ordem_param, decrescente", [("rejeitados", False), ("-rejeitados", True)]
)
def test_historico_ordenacao_por_rejeitados(
    client, chefe_almoxarifado, criar_usuario, ordem_param, decrescente
):
    usuario = criar_usuario()
    # `total_recebidos` precisa igualar `inseridos + atualizados + rejeitados`
    # (constraint de banco `catalogo_execucaoimportacao_totais_ok`).
    _criar_execucao(
        executada_por=usuario,
        nome_arquivo="rj-baixo.csv",
        total_recebidos=0,
        total_inseridos=0,
        total_rejeitados=0,
    )
    _criar_execucao(
        executada_por=usuario,
        nome_arquivo="rj-medio.csv",
        total_recebidos=3,
        total_inseridos=0,
        total_rejeitados=3,
    )
    _criar_execucao(
        executada_por=usuario,
        nome_arquivo="rj-alto.csv",
        total_recebidos=9,
        total_inseridos=0,
        total_rejeitados=9,
    )

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("catalogo:historico"), {"ordem": ordem_param})

    arquivos = ["rj-baixo.csv", "rj-medio.csv", "rj-alto.csv"]
    if decrescente:
        arquivos = list(reversed(arquivos))
    conteudo = resposta.content.decode("utf-8")
    posicoes = [conteudo.index(a) for a in arquivos]
    assert posicoes == sorted(posicoes)


@pytest.mark.parametrize(
    "ordem_param, decrescente", [("divergencias", False), ("-divergencias", True)]
)
def test_historico_ordenacao_por_divergencias(
    client, chefe_almoxarifado, criar_usuario, ordem_param, decrescente
):
    usuario = criar_usuario()
    _criar_execucao(executada_por=usuario, nome_arquivo="dv-baixo.csv", total_divergencias=0)
    _criar_execucao(executada_por=usuario, nome_arquivo="dv-medio.csv", total_divergencias=4)
    _criar_execucao(executada_por=usuario, nome_arquivo="dv-alto.csv", total_divergencias=8)

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("catalogo:historico"), {"ordem": ordem_param})

    arquivos = ["dv-baixo.csv", "dv-medio.csv", "dv-alto.csv"]
    if decrescente:
        arquivos = list(reversed(arquivos))
    conteudo = resposta.content.decode("utf-8")
    posicoes = [conteudo.index(a) for a in arquivos]
    assert posicoes == sorted(posicoes)


def test_historico_ordem_invalida_cai_na_ordem_padrao(client, chefe_almoxarifado, criar_usuario):
    usuario = criar_usuario()
    _criar_execucao(executada_por=usuario)

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("catalogo:historico"), {"ordem": "campo-inexistente"})

    assert resposta.status_code == 200
    assert resposta.context["ordem"] == "-concluida"


def test_historico_desempate_estavel_entre_paginas_com_mesma_data_de_conclusao(
    client, chefe_almoxarifado, criar_usuario
):
    """Mais de 20 execuções empatadas em `concluida_em`: o desempate
    (`campo_desempate = "-pk"`, execução mais recente primeiro) precisa
    manter a paginação estável, sem repetir nem pular nenhuma (FR-037a)."""
    usuario = criar_usuario()
    mesma_data = timezone.now()
    ids_criados = [
        _criar_execucao(
            executada_por=usuario, concluida_em=mesma_data, nome_arquivo=f"empate-{indice:02d}.csv"
        ).pk
        for indice in range(25)
    ]

    client.force_login(chefe_almoxarifado)
    url = reverse("catalogo:historico")

    resposta_pagina_1 = client.get(url)
    resposta_pagina_2 = client.get(url, {"pagina": 2})

    pks_pagina_1 = [e.pk for e in resposta_pagina_1.context["object_list"]]
    pks_pagina_2 = [e.pk for e in resposta_pagina_2.context["object_list"]]

    ordem_esperada = sorted(ids_criados, reverse=True)
    assert pks_pagina_1 == ordem_esperada[:20]
    assert pks_pagina_2 == ordem_esperada[20:]


def test_cabecalho_concluida_em_com_ordem_padrao_marca_aria_sort_descending(
    client, chefe_almoxarifado, criar_usuario
):
    usuario = criar_usuario()
    _criar_execucao(executada_por=usuario)

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("catalogo:historico"))

    th_concluida = _th(resposta.content.decode("utf-8"), "Concluída em")
    assert 'aria-sort="descending"' in th_concluida


def test_cabecalho_concluida_em_primeiro_clique_a_partir_do_padrao_ordena_crescente(
    client, chefe_almoxarifado, criar_usuario
):
    """A ordem padrão do histórico já é decrescente (FR-037a); o primeiro
    clique em "Concluída em" (sem `?ordem=` na requisição) precisa alternar
    para crescente, não repetir a mesma direção (`querystring_ordenacao`,
    `catalogo/templatetags/catalogo_extras.py`)."""
    usuario = criar_usuario()
    _criar_execucao(executada_por=usuario)

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("catalogo:historico"))

    th_concluida = _th(resposta.content.decode("utf-8"), "Concluída em")
    link = re.search(r'href="([^"]*)"', th_concluida).group(1)
    assert "ordem=concluida" in link
    assert "ordem=-concluida" not in link


def test_cabecalho_executor_ordenado_crescente_marca_aria_sort_ascending(
    client, chefe_almoxarifado, criar_usuario
):
    usuario = criar_usuario()
    _criar_execucao(executada_por=usuario)

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("catalogo:historico"), {"ordem": "executor"})

    th_executor = _th(resposta.content.decode("utf-8"), "Executada por")
    assert 'aria-sort="ascending"' in th_executor


def test_colunas_nao_ordenaveis_do_historico_continuam_sem_link(
    client, chefe_almoxarifado, criar_usuario
):
    """"Execução", "Arquivo", "Inseridos" e "Atualizados" não estão em
    `HistoricoImportacoesView.colunas_ordenacao` (`catalogo/views.py`) e
    continuam `<th>` simples, sem link nem `aria-sort`."""
    usuario = criar_usuario()
    _criar_execucao(executada_por=usuario)

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("catalogo:historico"))
    conteudo = resposta.content.decode("utf-8")

    for rotulo in ("Execução", "Arquivo", "Inseridos", "Atualizados"):
        th = _th(conteudo, rotulo)
        assert "<a" not in th
        assert "aria-sort" not in th


def test_historico_com_uma_unica_pagina_mostra_so_o_resumo(
    client, chefe_almoxarifado, criar_usuario
):
    """Decisão de coerência com a consulta do catálogo e `DESIGN.md` →
    Pagination ("com uma página só, aparece apenas o resumo"): o resumo da
    paginação do histórico não fica mais condicionado a `is_paginated`."""
    usuario = criar_usuario()
    _criar_execucao(executada_por=usuario)

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("catalogo:historico"))
    conteudo = resposta.content.decode("utf-8")

    nav = re.search(r'<nav class="pagination".*?</nav>', conteudo, re.S).group()
    assert "pagination-summary" in nav
    assert "1 execução no total" in nav
    assert "pagination-list" not in nav


# ---------------------------------------------------------------------------
# Paginação (20/página) — ver decisão sobre o parâmetro `pagina` no docstring
# do módulo.
# ---------------------------------------------------------------------------


def test_historico_pagina_por_20_execucoes(client, chefe_almoxarifado, criar_usuario):
    usuario = criar_usuario()
    base = timezone.now()
    for indice in range(25):
        _criar_execucao(
            executada_por=usuario,
            concluida_em=base - timedelta(minutes=indice),
            nome_arquivo=f"arquivo-{indice:02d}.csv",
        )

    client.force_login(chefe_almoxarifado)
    url = reverse("catalogo:historico")

    resposta_pagina_1 = client.get(url)
    assert resposta_pagina_1.status_code == 200
    assert resposta_pagina_1.context["is_paginated"] is True
    assert len(resposta_pagina_1.context["object_list"]) == 20
    assert resposta_pagina_1.context["paginator"].num_pages == 2
    # índice 0 tem o `concluida_em` mais recente (base - 0 minutos).
    assert resposta_pagina_1.context["object_list"][0].nome_arquivo == "arquivo-00.csv"

    resposta_pagina_2 = client.get(url, {"pagina": 2})
    assert resposta_pagina_2.status_code == 200
    assert len(resposta_pagina_2.context["object_list"]) == 5
    assert resposta_pagina_2.context["object_list"][0].nome_arquivo == "arquivo-20.csv"


# ---------------------------------------------------------------------------
# Queries constantes por página — sem N+1 de `executada_por`
# (`select_related`, T038).
# ---------------------------------------------------------------------------


def test_numero_de_queries_e_constante_entre_1_e_muitas_execucoes_de_usuarios_diferentes(
    client, chefe_almoxarifado, criar_usuario
):
    client.force_login(chefe_almoxarifado)
    url = reverse("catalogo:historico")

    _criar_execucao(executada_por=criar_usuario())
    with CaptureQueriesContext(connection) as com_uma:
        resposta_uma = client.get(url)
    assert resposta_uma.status_code == 200

    # 19 execuções adicionais, cada uma de um usuário DIFERENTE: sem
    # `select_related("executada_por")` isso emitiria uma query extra por
    # linha ao acessar `execucao.executada_por` no template (N+1).
    for _ in range(19):
        _criar_execucao(executada_por=criar_usuario())
    with CaptureQueriesContext(connection) as com_vinte:
        resposta_vinte = client.get(url)
    assert resposta_vinte.status_code == 200

    queries_uma = len(com_uma.captured_queries)
    queries_vinte = len(com_vinte.captured_queries)
    assert queries_uma == queries_vinte, (
        f"{queries_vinte - queries_uma} query(ies) a mais com 20 execuções — "
        "possível N+1 de `executada_por`"
    )


# ---------------------------------------------------------------------------
# Detalhe: preservação histórica (FR-037), exceção com linha/motivo/CADPRO
# (FR-036), 404 para pk inexistente.
# ---------------------------------------------------------------------------


def test_detalhe_da_primeira_execucao_e_identico_antes_e_depois_de_uma_segunda_importacao(
    chefe_almoxarifado, csv_fixture
):
    """FR-037 / US3 cenário 3: o resultado de uma execução concluída não pode
    ser sobrescrito por uma execução posterior — nem os totais, nem as
    exceções, nem o HTML exibido para o usuário."""
    client_autenticado = _cliente_autenticado(chefe_almoxarifado)
    execucao_1 = _importar_via_http(client_autenticado, csv_fixture("carga_inicial_valida.csv"))
    url_detalhe_1 = reverse("catalogo:execucao_detalhe", args=[execucao_1.pk])

    resposta_antes = client_autenticado.get(url_detalhe_1)
    assert resposta_antes.status_code == 200
    totais_antes = _totais_da_execucao(execucao_1.pk)
    excecoes_antes = _excecoes_da_execucao(execucao_1.pk)
    # Escopado ao par <dt>/<dd> do resumo (`execucao_detalhe.html`) — "9"
    # solto coincide por acidente com dígitos do SHA-256 exibido na mesma
    # página.
    assert re.search(
        rf"<dt>Inseridos</dt>\s*<dd>\s*{execucao_1.total_inseridos}\s*</dd>",
        resposta_antes.content.decode("utf-8"),
    )

    # segunda importação — arquivo com registros propositalmente inválidos
    # (US3, Independent Test), sobre os mesmos 9 códigos já existentes.
    _importar_via_http(client_autenticado, csv_fixture("carga_inicial_casos_spec.csv"))

    resposta_depois = client_autenticado.get(url_detalhe_1)
    assert resposta_depois.status_code == 200
    totais_depois = _totais_da_execucao(execucao_1.pk)
    excecoes_depois = _excecoes_da_execucao(execucao_1.pk)

    assert totais_antes == totais_depois, "a segunda importação não pode alterar os totais da 1ª"
    assert excecoes_antes == excecoes_depois, (
        "a segunda importação não pode alterar as exceções da 1ª"
    )
    assert re.search(
        rf"<dt>Inseridos</dt>\s*<dd>\s*{execucao_1.total_inseridos}\s*</dd>",
        resposta_depois.content.decode("utf-8"),
    )


def test_excecao_no_detalhe_mostra_linha_motivo_e_cadpro_quando_identificavel(
    chefe_almoxarifado, csv_fixture
):
    """FR-036, usando o caso documentado em `tests/fixtures/catalogo/README.md`
    (linha 18, `CADPRO="2"`, `CADPRO_FORMATO_INVALIDO` — exemplo normativo do
    contrato §5)."""
    client_autenticado = _cliente_autenticado(chefe_almoxarifado)
    execucao = _importar_via_http(client_autenticado, csv_fixture("carga_inicial_casos_spec.csv"))

    excecao = execucao.excecoes.get(cadpro="2")
    assert excecao.motivo == MotivoRecusa.CADPRO_FORMATO_INVALIDO
    assert excecao.linha_inicial == 18

    resposta = client_autenticado.get(reverse("catalogo:execucao_detalhe", args=[execucao.pk]))
    conteudo = resposta.content.decode("utf-8")

    # Contexto: a exceção da linha 18 (CADPRO="2") está na página exibida.
    excecao_no_contexto = next(
        e for e in resposta.context["excecoes_pagina"] if e.pk == excecao.pk
    )
    assert excecao_no_contexto.cadpro == "2"
    assert excecao_no_contexto.linha_inicial == 18

    assert str(excecao.linha_inicial) in conteudo
    # Célula "Código (CADPRO)" com o valor exato
    # (`catalogo/templates/catalogo/execucao_detalhe.html`) — não uma
    # checagem tautológica de "2" solto em qualquer lugar do HTML (colidiria
    # com paginação, contagens etc.).
    assert re.search(r'<td class="table-cell-code">\s*2\s*</td>', conteudo), (
        "CADPRO '2' deveria aparecer numa célula de código da tabela de exceções"
    )
    rotulo_ou_codigo = MotivoRecusa.CADPRO_FORMATO_INVALIDO.label
    assert (
        rotulo_ou_codigo in conteudo or MotivoRecusa.CADPRO_FORMATO_INVALIDO.value in conteudo
    ), "o motivo da recusa precisa aparecer, como rótulo em pt-BR ou como código"


def test_detalhe_de_execucao_inexistente_e_404(client, chefe_almoxarifado):
    client.force_login(chefe_almoxarifado)

    resposta = client.get(reverse("catalogo:execucao_detalhe", args=[999999]))

    assert resposta.status_code == 404
