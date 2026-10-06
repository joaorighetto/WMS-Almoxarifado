"""Contrato de markup do lote P2 do redesign (consultas e históricos), `docs/redesign-observatory/`.

Superfícies cobertas: consulta de fornecedores (S6), histórico e execução de importação do
catálogo (S11, S12) e histórico e execução de importação de fornecedores (S15, S16). Fontes:
`plano.md` seção 3 ("Contratos que não podem mudar" e "Ganchos de markup compartilhados por
testes e implementação") e `contrato.md`.

O que este arquivo protege, em ordem de consequência:

- os dados exibidos continuam exatamente os do banco, sem transformação: CADPRO, CODIF e documento
  como gravados (`INV-CATALOG-001`) e o total ao lado do rótulo certo no resumo;
- shell único por página (um `<main id="main">`, uma sidebar) com o item atual certo — o
  "Histórico de importações" do catálogo e o de fornecedores são itens de mesmo rótulo em grupos
  diferentes, e a execução marca o do seu grupo;
- nenhum markup da fundação anterior (`page-header`, `back-link`, `section-marker`,
  `table-sticky-header`): o scroll interno de 60vh das tabelas herdadas não pode voltar;
- ganchos que o JavaScript e os leitores de tela usam: `data-linha-clicavel`/`data-linha-link` com
  o script carregado uma vez, IDs e `data-secao` das seções, âncoras e parâmetros da paginação,
  `data-estado="vazio"`, cópias OOB de `campo-codigo`/`campo-documento` no fragmento HTMX;
- ênfase nunca só por cor: `.tile-warning` só quando há rejeitados (ou fornecedores que passam a
  bloqueado) e, em todo caso, rótulo e total em texto;
- mensagens do `django.contrib.messages` aparecem uma única vez (o `base.html` já inclui o partial).

Não duplica: ordenação, paginação por tamanho, N+1, truncamento do nome do arquivo e atributos
`hx-on` da consulta já têm testes em `test_catalogo_historico.py`, `test_fornecedores_historico.py`
e `test_fornecedores_consulta.py`; a estrutura do shell em si, em `tests/test_shell.py`. Aqui o
parsing é estrutural (`tests/html_helpers.py`), nunca regex de espaçamento.
"""

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.messages import constants as niveis
from django.contrib.messages.storage.cookie import CookieStorage
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.utils import timezone

from catalogo.models import (
    AlteracaoCadastralMaterial,
    CampoCadastral,
    DivergenciaSaldo,
    ExcecaoImportacao,
    ExecucaoImportacao,
    MotivoRecusa,
)
from fornecedores.models import (
    AlteracaoFornecedor,
    ExcecaoImportacaoFornecedores,
    ExecucaoImportacaoFornecedores,
    MotivoRecusaFornecedor,
)
from tests.html_helpers import analisar, hrefs_de, totais_do_resumo

pytestmark = pytest.mark.django_db

HX = {"HTTP_HX_REQUEST": "true"}
SHA256 = "ab" * 32
MARCAS_LEGADAS = (
    "page-header",
    "page-container",
    "back-link",
    "section-marker",
    "table-sticky-header",
    "appbar",
)


# ---------------------------------------------------------------------------
# Dados: uma execução "completa" (todas as seções com linhas e rejeitados > 0) e uma "limpa"
# (nenhuma rejeição, nenhuma alteração), para cada app.
# ---------------------------------------------------------------------------


def _execucao_catalogo(
    usuario, *, nome="carga.csv", inseridos=1, atualizados=0, alterados=0, rejeitados=0,
    divergencias=0, ausentes=0,
):
    return ExecucaoImportacao.objects.create(
        token_previa=uuid.uuid4(),
        executada_por=usuario,
        concluida_em=timezone.now(),
        nome_arquivo=nome,
        tamanho_arquivo=2048,
        sha256_arquivo=SHA256,
        total_recebidos=inseridos + atualizados + rejeitados,
        total_inseridos=inseridos,
        total_atualizados=atualizados,
        total_atualizados_com_alteracao=alterados,
        total_rejeitados=rejeitados,
        total_divergencias=divergencias,
        total_ausentes_no_arquivo=ausentes,
    )


def _execucao_fornecedores(
    usuario, *, nome="cadastro.csv", inseridos=1, atualizados=0, alterados=0, rejeitados=0,
    ausentes=0,
):
    return ExecucaoImportacaoFornecedores.objects.create(
        token_previa=uuid.uuid4(),
        executada_por=usuario,
        concluida_em=timezone.now(),
        nome_arquivo=nome,
        tamanho_arquivo=2048,
        sha256_arquivo=SHA256,
        total_recebidos=inseridos + atualizados + rejeitados,
        total_inseridos=inseridos,
        total_atualizados=atualizados,
        total_atualizados_com_alteracao=alterados,
        total_rejeitados=rejeitados,
        total_ausentes_no_arquivo=ausentes,
    )


@pytest.fixture
def cenario_catalogo(chefe_almoxarifado, criar_material):
    usuario = chefe_almoxarifado
    completa = _execucao_catalogo(
        usuario, nome="carga-completa.csv", inseridos=1, atualizados=1, alterados=1,
        rejeitados=1, divergencias=1, ausentes=2,
    )
    # CADPRO com zeros à esquerda: qualquer "normalização" na exibição seria visível.
    com_divergencia = criar_material("001.000.010", "10.000")
    com_alteracao = criar_material("001.000.020", "5.000")
    DivergenciaSaldo.objects.create(
        execucao=completa, material=com_divergencia, saldo_wms=Decimal("10.000"),
        saldo_arquivo=Decimal("12.000"), diferenca=Decimal("2.000"),
    )
    AlteracaoCadastralMaterial.objects.create(
        execucao=completa, material=com_alteracao, campo=CampoCadastral.DESCRICAO,
        valor_anterior="Descrição antiga", valor_novo="Descrição nova",
    )
    ExcecaoImportacao.objects.create(
        execucao=completa, linha_inicial=7, linha_final=7, cadpro="2",
        motivo=MotivoRecusa.CADPRO_FORMATO_INVALIDO, detalhe="detalhe da recusa",
    )
    limpa = _execucao_catalogo(usuario, nome="carga-limpa.csv", inseridos=2)
    return SimpleNamespace(usuario=usuario, completa=completa, limpa=limpa)


@pytest.fixture
def cenario_fornecedores(chefe_almoxarifado, criar_fornecedor):
    usuario = chefe_almoxarifado
    completa = _execucao_fornecedores(
        usuario, nome="cadastro-completo.csv", inseridos=1, atualizados=2, alterados=2,
        rejeitados=1, ausentes=2,
    )
    # CODIF com zeros à esquerda: qualquer "normalização" na exibição seria visível.
    passa_a_bloqueado = criar_fornecedor("000123", "Fornecedor Um")
    renomeado = criar_fornecedor("000456", "Fornecedor Dois")
    AlteracaoFornecedor.objects.create(
        execucao=completa, fornecedor=passa_a_bloqueado, campo="bloqueado",
        valor_anterior="S", valor_novo="B",
    )
    AlteracaoFornecedor.objects.create(
        execucao=completa, fornecedor=renomeado, campo="nome",
        valor_anterior="Fornecedor Antigo", valor_novo="Fornecedor Dois",
    )
    ExcecaoImportacaoFornecedores.objects.create(
        execucao=completa, linha=9, codif="000789",
        motivo=MotivoRecusaFornecedor.SITUACAO_BLOQUEIO_INVALIDA, detalhe="detalhe da recusa",
    )
    limpa = _execucao_fornecedores(usuario, nome="cadastro-limpo.csv", inseridos=3)
    return SimpleNamespace(usuario=usuario, completa=completa, limpa=limpa)


@pytest.fixture
def cenario_consulta(funcionario_almoxarifado, criar_fornecedor):
    criar_fornecedor("000123", "Fornecedor Um", documento="12.345.678/0001-90")
    criar_fornecedor("000456", "Fornecedor Dois", bloqueado=True)
    return SimpleNamespace(usuario=funcionario_almoxarifado)


# ---------------------------------------------------------------------------
# As cinco telas: quem as usa, a URL, o h1, o item atual da sidebar e a ação de página.
# ---------------------------------------------------------------------------

TELAS = {
    "catalogo-historico": SimpleNamespace(
        cenario="cenario_catalogo",
        url=lambda c: reverse("catalogo:historico"),
        h1=lambda c: "Histórico de importações do catálogo",
        atual=("Catálogo", "Histórico de importações", "catalogo:historico"),
        acao=("Importar catálogo", "catalogo:importacao_envio"),
    ),
    "catalogo-execucao": SimpleNamespace(
        cenario="cenario_catalogo",
        url=lambda c: reverse("catalogo:execucao_detalhe", args=[c.completa.pk]),
        h1=lambda c: f"Resultado da importação do catálogo #{c.completa.pk} Com rejeições",
        atual=("Catálogo", "Histórico de importações", "catalogo:historico"),
        acao=("Nova importação", "catalogo:importacao_envio"),
    ),
    "fornecedores-historico": SimpleNamespace(
        cenario="cenario_fornecedores",
        url=lambda c: reverse("fornecedores:historico"),
        h1=lambda c: "Histórico de importações de fornecedores",
        atual=("Fornecedores", "Histórico de importações", "fornecedores:historico"),
        acao=("Importar fornecedores", "fornecedores:importacao_envio"),
    ),
    "fornecedores-execucao": SimpleNamespace(
        cenario="cenario_fornecedores",
        url=lambda c: reverse("fornecedores:execucao_detalhe", args=[c.completa.pk]),
        h1=lambda c: f"Resultado da importação de fornecedores #{c.completa.pk} Com rejeições",
        atual=("Fornecedores", "Histórico de importações", "fornecedores:historico"),
        acao=("Nova importação", "fornecedores:importacao_envio"),
    ),
    "fornecedores-consulta": SimpleNamespace(
        cenario="cenario_consulta",
        url=lambda c: reverse("fornecedores:consulta"),
        h1=lambda c: "Consulta de fornecedores",
        atual=("Fornecedores", "Fornecedores", "fornecedores:consulta"),
        acao=None,
    ),
}

NOMES = list(TELAS)
HISTORICOS = ["catalogo-historico", "fornecedores-historico"]
EXECUCOES = ["catalogo-execucao", "fornecedores-execucao"]


@pytest.fixture
def pagina(request, client, senha_valida):
    """A tela parametrizada já obtida e parseada, com o usuário que a usa logado."""
    tela = TELAS[request.param]
    cenario = request.getfixturevalue(tela.cenario)
    assert client.login(username=cenario.usuario.matricula, password=senha_valida)
    url = tela.url(cenario)
    resposta = client.get(url)
    assert resposta.status_code == 200
    return SimpleNamespace(
        tela=tela,
        cenario=cenario,
        url=url,
        conteudo=resposta.content.decode(),
        documento=analisar(resposta.content),
    )


def _telas(*nomes):
    return pytest.mark.parametrize(
        "pagina", [pytest.param(nome, id=nome) for nome in nomes], indirect=True
    )


def _dentro_de_classe(no, classe):
    return any(ancestral.tem_classe(classe) for ancestral in no.ancestrais())


def _texto_das_celulas(linha):
    return [celula.texto for celula in linha.buscar("td")]


# ---------------------------------------------------------------------------
# 1. Shell, cabeçalho e item atual da sidebar
# ---------------------------------------------------------------------------


@_telas(*NOMES)
def test_pagina_tem_um_main_uma_sidebar_e_o_h1_esperado_no_cabecalho(pagina):
    documento = pagina.documento

    principal = documento.unico("main", id="main")
    assert len(documento.buscar("main")) == 1
    assert len(documento.buscar("aside", classe="side")) == 1
    assert not principal.tem_classe("page")

    titulos = documento.buscar("h1")
    assert len(titulos) == 1
    assert titulos[0].texto == pagina.tela.h1(pagina.cenario)
    assert _dentro_de_classe(titulos[0], "top") and titulos[0].esta_dentro_de("main")


@_telas(*NOMES)
def test_item_atual_da_sidebar_e_unico_e_do_grupo_e_destino_certos(pagina):
    grupo_esperado, rotulo_esperado, rota = pagina.tela.atual
    nav = pagina.documento.unico("nav", aria_label="Seções")

    grupo = None
    atuais = []
    for no in nav.filhos:
        if no.tag == "h3":
            grupo = no.texto
        elif no.tag == "a" and "aria-current" in no.attrs:
            atuais.append((grupo, no))

    assert len(atuais) == 1
    grupo_obtido, item = atuais[0]
    assert item.get("aria-current") == "page"
    assert (grupo_obtido, item.texto, item.get("href")) == (
        grupo_esperado,
        rotulo_esperado,
        reverse(rota),
    )


@_telas(*NOMES)
def test_pagina_nao_traz_markup_da_fundacao_anterior(pagina):
    for marca in MARCAS_LEGADAS:
        assert pagina.documento.buscar(classe=marca) == [], marca


@_telas(*NOMES)
def test_ids_da_pagina_sao_unicos(pagina):
    ids = [no.attrs["id"] for no in pagina.documento.buscar(id=True)]

    repetidos = sorted({valor for valor in ids if ids.count(valor) > 1})
    assert repetidos == []


@_telas(*NOMES)
def test_acao_de_pagina_fica_nas_ferramentas_como_botao_secundario(pagina):
    ferramentas = pagina.documento.unico("main").unico(classe="tools")

    if pagina.tela.acao is None:
        assert ferramentas.buscar("a") == [] and ferramentas.buscar("button") == []
        return
    texto, rota = pagina.tela.acao
    (link,) = ferramentas.buscar("a")
    assert (link.texto, link.get("href")) == (texto, reverse(rota))
    assert link.tem_classe("btn") and link.tem_classe("btn-secondary")
    assert not link.tem_classe("btn-primary")
    assert ferramentas.buscar("button") == []


# ---------------------------------------------------------------------------
# 2. Mensagens: o `base.html` já inclui o partial; uma única vez, só quando há mensagem
# ---------------------------------------------------------------------------


def _deixar_mensagem_pendente(client, nivel, texto):
    """Enfileira uma mensagem na sessão do cliente, como o `messages.add_message` de uma view
    anterior (por exemplo o redirecionamento depois de confirmar uma importação)."""
    armazenamento = CookieStorage(HttpRequest())
    armazenamento.add(nivel, texto)
    resposta = HttpResponse()
    armazenamento.update(resposta)
    client.cookies["messages"] = resposta.cookies["messages"].value


@_telas(*NOMES)
def test_sem_mensagem_pendente_nao_ha_container_de_mensagens(pagina):
    assert pagina.documento.buscar(classe="messages") == []


@pytest.mark.parametrize(
    "nivel, classe, papel",
    [
        pytest.param(niveis.SUCCESS, "alert-success", "status", id="sucesso"),
        pytest.param(niveis.ERROR, "error-box", "alert", id="erro"),
    ],
)
@_telas(*NOMES)
def test_mensagem_pendente_aparece_uma_unica_vez_no_main(client, pagina, nivel, classe, papel):
    texto = "Mensagem-de-teste-unica-4f9a"
    _deixar_mensagem_pendente(client, nivel, texto)

    resposta = client.get(pagina.url)

    assert resposta.status_code == 200
    documento = analisar(resposta.content)
    (container,) = documento.buscar(classe="messages")
    assert container.pai is documento.unico("main")
    (mensagem,) = container.buscar(classe=classe)
    assert mensagem.get("role") == papel
    assert mensagem.texto == texto
    assert resposta.content.decode().count(texto) == 1


# ---------------------------------------------------------------------------
# 3. Execução: trilha, metadados, resumo, seções
# ---------------------------------------------------------------------------


@_telas(*EXECUCOES)
def test_trilha_da_execucao_leva_ao_historico_do_proprio_app(pagina):
    sub = pagina.documento.unico("main").unico(classe="sub")

    trilha = sub.unico("nav", aria_label="Trilha de navegação")
    (link,) = trilha.buscar("a")
    rota_historico = pagina.tela.atual[2]
    assert link.get("href") == reverse(rota_historico)
    assert link.texto.startswith("Histórico de importações")
    # `texto` junta o texto próprio antes do dos filhos: aqui só importa estar na trilha.
    assert f"Execução #{pagina.cenario.completa.pk}" in trilha.texto


@_telas(*EXECUCOES)
def test_metadados_da_execucao_ficam_numa_lista_de_definicao_com_os_valores_gravados(pagina):
    execucao = pagina.cenario.completa

    metadados = pagina.documento.unico("main").unico("dl", classe="kv")

    assert [dt.texto for dt in metadados.buscar("dt")] == [
        "Executada por",
        "Concluída em",
        "Arquivo",
        "SHA-256 do arquivo",
    ]
    valores = [dd.texto for dd in metadados.buscar("dd")]
    assert valores[0] == execucao.executada_por.matricula
    assert valores[2].startswith(execucao.nome_arquivo)
    assert metadados.unico("dd", classe="data-hash").texto == SHA256


@pytest.mark.parametrize(
    "cenario, rota",
    [
        pytest.param("cenario_catalogo", "catalogo:execucao_detalhe", id="catalogo"),
        pytest.param("cenario_fornecedores", "fornecedores:execucao_detalhe", id="fornecedores"),
    ],
)
def test_selo_do_titulo_da_execucao_diz_com_ou_sem_rejeicoes_em_texto(
    request, client, senha_valida, cenario, rota
):
    """O selo do `h1` é o mesmo par dos históricos: depende só de `total_rejeitados`."""
    dados = request.getfixturevalue(cenario)
    client.login(username=dados.usuario.matricula, password=senha_valida)

    com = analisar(client.get(reverse(rota, args=[dados.completa.pk])).content)
    sem = analisar(client.get(reverse(rota, args=[dados.limpa.pk])).content)

    (selo_com,) = com.unico("h1").buscar(classe="badge")
    (selo_sem,) = sem.unico("h1").buscar(classe="badge")
    assert (selo_com.texto, selo_com.tem_classe("badge-warning")) == ("Com rejeições", True)
    assert (selo_sem.texto, selo_sem.tem_classe("badge-success")) == ("Sem rejeições", True)
    assert not selo_sem.tem_classe("badge-warning") and not selo_com.tem_classe("badge-success")


@_telas(*EXECUCOES)
def test_resumo_vem_antes_dos_metadados_e_das_secoes_de_detalhe(pagina):
    principal = pagina.documento.unico("main")

    secoes = [no.get("aria-labelledby") for no in principal.filhos if no.tag == "section"]

    esperado = ["resumo-titulo", "execucao-titulo"]
    if "catalogo" in pagina.url:
        esperado += ["divergencias-titulo"]
    esperado += ["alteracoes-titulo", "excecoes-titulo"]
    assert secoes == esperado
    # O resumo tem título próprio (oculto) e traz os tiles antes das notas.
    resumo = principal.unico("section", aria_labelledby="resumo-titulo")
    titulo = resumo.unico("h2", id="resumo-titulo")
    assert titulo.texto == "Resumo" and titulo.tem_classe("visually-hidden")
    posicao = {no: i for i, no in enumerate(resumo.descendentes())}
    tiles = resumo.unico(classe="tiles")
    assert all(posicao[nota] > posicao[tiles] for nota in resumo.buscar("p", classe="text-note"))
    # O card de metadados (`dl.kv`) vem depois do resumo.
    ordem = list(principal.descendentes())
    assert ordem.index(tiles) < ordem.index(principal.unico("dl", classe="kv"))


def _atalhos(documento):
    """`{rótulo do tile: [(href, texto do atalho)]}` dos links dentro dos tiles do resumo."""
    atalhos = {}
    for tile in documento.unico(classe="tiles").buscar(classe="tile"):
        links = [(a.get("href"), a.texto) for a in tile.buscar("a")]
        if links:
            atalhos[tile.unico("dt", classe="k").texto] = links
    return atalhos


@pytest.mark.parametrize(
    "cenario, rota, esperado",
    [
        pytest.param(
            "cenario_catalogo", "catalogo:execucao_detalhe",
            {"Rejeitados": [("#excecoes", "ver exceções")]}, id="catalogo",
        ),
        pytest.param(
            "cenario_fornecedores", "fornecedores:execucao_detalhe",
            {
                "Rejeitados": [("#excecoes", "ver exceções")],
                "Passam a bloqueado": [("#alteracoes", "ver alterações")],
            },
            id="fornecedores",
        ),
    ],
)
def test_atalhos_dos_tiles_so_existem_com_total_maior_que_zero_e_apontam_para_secao_existente(
    request, client, senha_valida, cenario, rota, esperado
):
    dados = request.getfixturevalue(cenario)
    client.login(username=dados.usuario.matricula, password=senha_valida)

    com = analisar(client.get(reverse(rota, args=[dados.completa.pk])).content)
    sem = analisar(client.get(reverse(rota, args=[dados.limpa.pk])).content)

    assert _atalhos(com) == esperado
    for href, _ in (par for links in esperado.values() for par in links):
        assert com.unico("section", id=href.removeprefix("#"))
    assert _atalhos(sem) == {}
    # Cada atalho fica em `dd.d` próprio; "Passam a bloqueado" continua dizendo "fora da soma".
    def notas(documento, rotulo):
        (tile,) = [
            t for t in documento.buscar(classe="tile")
            if t.unico("dt", classe="k").texto == rotulo
        ]
        return [dd.texto for dd in tile.buscar("dd", classe="d")]

    assert notas(com, "Rejeitados") == ["ver exceções"]
    assert notas(sem, "Rejeitados") == []
    if "Passam a bloqueado" in esperado:
        assert notas(com, "Passam a bloqueado") == ["fora da soma", "ver alterações"]
        assert notas(sem, "Passam a bloqueado") == ["fora da soma"]
    # Resumo na variante de métricas (grade própria do resumo da execução).
    assert com.unico(classe="tiles").tem_classe("tiles-metricas")


def test_nota_sobre_fornecedor_bloqueado_so_aparece_quando_algum_passa_a_bloqueado(
    client, senha_valida, cenario_fornecedores
):
    client.login(username=cenario_fornecedores.usuario.matricula, password=senha_valida)
    rota = "fornecedores:execucao_detalhe"

    com = analisar(client.get(reverse(rota, args=[cenario_fornecedores.completa.pk])).content)
    sem = analisar(client.get(reverse(rota, args=[cenario_fornecedores.limpa.pk])).content)

    def nota_de_bloqueio(documento):
        return [
            p for p in documento.buscar("p", classe="text-note")
            if "não pode ser emitente" in p.texto
        ]

    assert len(nota_de_bloqueio(com)) == 1
    assert nota_de_bloqueio(sem) == []
    # A outra nota (soma e ausentes) continua nas duas.
    for documento in (com, sem):
        notas = documento.buscar("p", classe="text-note")
        assert any("não entra na soma" in p.texto for p in notas)


def test_resumo_da_execucao_do_catalogo_mostra_cada_total_ao_lado_do_seu_rotulo(
    client, senha_valida, cenario_catalogo
):
    client.login(username=cenario_catalogo.usuario.matricula, password=senha_valida)

    resposta = client.get(
        reverse("catalogo:execucao_detalhe", args=[cenario_catalogo.completa.pk])
    )

    assert totais_do_resumo(analisar(resposta.content)) == {
        "Recebidos": "3",
        "Inseridos": "1",
        "Atualizados": "1",
        "Rejeitados": "1",
        "Ausentes do arquivo": "2",
    }


def test_resumo_da_execucao_de_fornecedores_mostra_cada_total_ao_lado_do_seu_rotulo(
    client, senha_valida, cenario_fornecedores
):
    client.login(username=cenario_fornecedores.usuario.matricula, password=senha_valida)

    resposta = client.get(
        reverse("fornecedores:execucao_detalhe", args=[cenario_fornecedores.completa.pk])
    )

    assert totais_do_resumo(analisar(resposta.content)) == {
        "Recebidos": "4",
        "Inseridos": "1",
        "Atualizados": "2",
        "Rejeitados": "1",
        "Passam a bloqueado": "1",
        "Voltam a liberado": "0",
        "Ausentes do arquivo": "2",
    }


def _rotulos_dos_tiles(documento, classe):
    return {tile.unico("dt", classe="k").texto for tile in documento.buscar(classe=classe)}


@pytest.mark.parametrize(
    "app, cenario, rota, com_ressalva",
    [
        pytest.param(
            "catalogo", "cenario_catalogo", "catalogo:execucao_detalhe", {"Rejeitados"},
            id="catalogo",
        ),
        pytest.param(
            "fornecedores", "cenario_fornecedores", "fornecedores:execucao_detalhe",
            {"Rejeitados", "Passam a bloqueado"}, id="fornecedores",
        ),
    ],
)
def test_enfase_do_resumo_so_existe_com_rejeitados_ou_bloqueios_e_nunca_substitui_o_texto(
    request, client, senha_valida, app, cenario, rota, com_ressalva
):
    dados = request.getfixturevalue(cenario)
    client.login(username=dados.usuario.matricula, password=senha_valida)

    com_pendencia = analisar(client.get(reverse(rota, args=[dados.completa.pk])).content)
    sem_pendencia = analisar(client.get(reverse(rota, args=[dados.limpa.pk])).content)

    # Com pendência: o tile em destaque é exatamente o esperado, e o total segue em texto.
    assert _rotulos_dos_tiles(com_pendencia, "tile-warning") == com_ressalva
    for tile in com_pendencia.buscar(classe="tile-warning"):
        assert tile.unico("dd", classe="v").texto == "1"
    # Sem pendência: nenhum destaque, mas o rótulo e o total "0" continuam visíveis.
    assert sem_pendencia.buscar(classe="tile-warning") == []
    assert totais_do_resumo(sem_pendencia)["Rejeitados"] == "0"
    # "Ausentes do arquivo" fica à parte da soma, dito em texto e não só pela borda.
    (a_parte,) = [
        tile for tile in com_pendencia.buscar(classe="tile-aside")
        if tile.unico("dt", classe="k").texto == "Ausentes do arquivo"
    ]
    assert "fora da soma" in a_parte.texto
    assert not a_parte.tem_classe("tile-warning")
    # Qualquer tile à parte, hoje ou amanhã, também diz em texto o que o separa da soma.
    for tile in com_pendencia.buscar(classe="tile-aside"):
        assert tile.buscar(classe="d"), tile.unico("dt", classe="k").texto


@_telas(*EXECUCOES)
def test_execucao_sem_rejeicoes_diz_em_texto_que_nao_ha_excecoes(
    client, pagina, senha_valida
):
    limpa = pagina.cenario.limpa
    app = "catalogo" if "catalogo" in pagina.url else "fornecedores"
    rota = f"{app}:execucao_detalhe"

    documento = analisar(client.get(reverse(rota, args=[limpa.pk])).content)

    excecoes = documento.unico(id="excecoes")
    assert "Exceções (0)" in excecoes.unico("h2").texto
    assert excecoes.buscar("table") == []
    assert "Nenhuma exceção nesta importação." in excecoes.unico(classe="empty").texto


def test_secoes_da_execucao_do_catalogo_preservam_ids_data_secao_e_rotulos(
    client, senha_valida, cenario_catalogo
):
    client.login(username=cenario_catalogo.usuario.matricula, password=senha_valida)
    resposta = client.get(
        reverse("catalogo:execucao_detalhe", args=[cenario_catalogo.completa.pk])
    )
    documento = analisar(resposta.content)

    esperado = {
        "divergencias": ("divergencias", "Divergências de saldo (1)"),
        "alteracoes": ("alteracoes", "Alterações cadastrais — 1 campo em 1 material"),
        "excecoes": (None, "Exceções (1)"),
    }
    for id_secao, (data_secao, titulo) in esperado.items():
        secao = documento.unico("section", id=id_secao)
        assert secao.get("data-secao") == data_secao
        assert secao.tem_classe("card")
        h2 = secao.unico("h2")
        assert h2.texto == titulo
        assert secao.get("aria-labelledby") == h2.get("id")
        assert _dentro_de_classe(secao.unico("table"), "table-wrapper"), id_secao


def test_secoes_da_execucao_de_fornecedores_preservam_ids_data_secao_e_rotulos(
    client, senha_valida, cenario_fornecedores
):
    client.login(username=cenario_fornecedores.usuario.matricula, password=senha_valida)
    resposta = client.get(
        reverse("fornecedores:execucao_detalhe", args=[cenario_fornecedores.completa.pk])
    )
    documento = analisar(resposta.content)

    esperado = {
        "alteracoes": ("alteracoes", "Alterações cadastrais — 2 campos em 2 fornecedores"),
        "excecoes": (None, "Exceções (1)"),
    }
    for id_secao, (data_secao, titulo) in esperado.items():
        secao = documento.unico("section", id=id_secao)
        assert secao.get("data-secao") == data_secao
        assert secao.tem_classe("card")
        h2 = secao.unico("h2")
        assert h2.texto == titulo
        assert secao.get("aria-labelledby") == h2.get("id")
        assert _dentro_de_classe(secao.unico("table"), "table-wrapper"), id_secao
    # Fornecedores não têm divergências de saldo.
    assert documento.buscar(id="divergencias") == []


def test_catalogo_e_codif_aparecem_nas_secoes_exatamente_como_gravados(
    client, senha_valida, cenario_catalogo, cenario_fornecedores
):
    """INV-CATALOG-001: o CADPRO (e o CODIF) é exibido sem zeros removidos nem reformatação."""
    client.login(username=cenario_catalogo.usuario.matricula, password=senha_valida)

    catalogo = analisar(
        client.get(
            reverse("catalogo:execucao_detalhe", args=[cenario_catalogo.completa.pk])
        ).content
    )
    fornecedores = analisar(
        client.get(
            reverse("fornecedores:execucao_detalhe", args=[cenario_fornecedores.completa.pk])
        ).content
    )

    def codigos(documento, id_secao):
        # O código fica sozinho no seu elemento (`.table-cell-code`), sem a linha secundária.
        return [
            no.texto for no in documento.unico(id=id_secao).buscar(classe="table-cell-code")
        ]

    assert codigos(catalogo, "divergencias") == ["001.000.010"]
    assert codigos(catalogo, "alteracoes") == ["001.000.020"]
    assert codigos(catalogo, "excecoes") == ["2"]
    assert sorted(codigos(fornecedores, "alteracoes")) == ["000123", "000456"]
    assert codigos(fornecedores, "excecoes") == ["000789"]


def test_celula_de_codigo_das_alteracoes_traz_o_codigo_intacto_e_o_nome_ou_descricao_inteiros(
    client, senha_valida, cenario_catalogo, cenario_fornecedores
):
    client.login(username=cenario_catalogo.usuario.matricula, password=senha_valida)
    catalogo = analisar(
        client.get(
            reverse("catalogo:execucao_detalhe", args=[cenario_catalogo.completa.pk])
        ).content
    )
    fornecedores = analisar(
        client.get(
            reverse("fornecedores:execucao_detalhe", args=[cenario_fornecedores.completa.pk])
        ).content
    )

    # Catálogo: divergências e alterações, CADPRO + descrição atual do material.
    for id_secao, cadpro in (("divergencias", "001.000.010"), ("alteracoes", "001.000.020")):
        tabela = catalogo.unico(id=id_secao).unico("table")
        primeiro = tabela.buscar("th")[0]
        assert primeiro.texto == "Código (CADPRO) / Descrição atual"
        assert primeiro.tem_classe("th-wrap")
        (celula,) = tabela.buscar("td", classe="catalogo-codigo-cell")
        assert celula.unico(classe="table-cell-code").texto == cadpro
        assert celula.unico(classe="cell-secondary").texto == f"Material de teste {cadpro}"
    # Fornecedores: CODIF + nome atual na mesma célula; não há mais coluna "Nome atual" à parte.
    tabela = fornecedores.unico(id="alteracoes").unico("table")
    cabecalhos = tabela.buscar("th")
    assert cabecalhos[0].texto == "Código (CODIF) / Nome atual"
    assert cabecalhos[0].tem_classe("th-wrap")
    assert [th.attrs.get("scope") for th in cabecalhos] == ["col"] * 4
    assert [cabecalhos[1].texto, cabecalhos[2].texto] == ["Campo", "Valor anterior"]
    pares = {
        celula.unico(classe="table-cell-code").texto: celula.texto
        for celula in tabela.buscar("td", classe="fornecedores-codigo-cell")
    }
    assert pares == {
        "000123": "000123 Fornecedor Um",
        "000456": "000456 Fornecedor Dois",
    }


@pytest.mark.parametrize(
    "cenario, rota, linha_esperada",
    [
        pytest.param(
            "cenario_catalogo", "catalogo:execucao_detalhe",
            ["7", "2", MotivoRecusa.CADPRO_FORMATO_INVALIDO.label, "detalhe da recusa"],
            id="catalogo",
        ),
        pytest.param(
            "cenario_fornecedores", "fornecedores:execucao_detalhe",
            ["9", "000789", MotivoRecusaFornecedor.SITUACAO_BLOQUEIO_INVALIDA.label,
             "detalhe da recusa"],
            id="fornecedores",
        ),
    ],
)
def test_excecoes_mostram_linha_codigo_motivo_e_detalhe_em_texto_sem_fundo_de_erro_na_linha(
    request, client, senha_valida, cenario, rota, linha_esperada
):
    dados = request.getfixturevalue(cenario)
    client.login(username=dados.usuario.matricula, password=senha_valida)

    documento = analisar(client.get(reverse(rota, args=[dados.completa.pk])).content)

    tabela = documento.unico(id="excecoes").unico("table")
    cabecalhos = [th.texto for th in tabela.buscar("th")]
    assert cabecalhos[0] == "Linha" and cabecalhos[2:] == ["Motivo / detalhe"]
    (linha,) = tabela.unico("tbody").buscar("tr")
    linha_ = _texto_das_celulas(linha)
    # Três colunas: o motivo na linha principal e o detalhe em linha secundária da mesma célula.
    assert len(linha_) == 3
    assert linha_[:2] == linha_esperada[:2]
    motivo, detalhe = linha_esperada[2], linha_esperada[3]
    celula = linha.buscar("td")[2]
    assert celula.texto.startswith(motivo)
    assert celula.unico(classe="cell-secondary").texto == detalhe
    # A ênfase de rejeição fica no tile e nos textos, não num fundo de erro em toda linha.
    assert documento.buscar(classe="table-row-error") == []


def test_divergencias_e_alteracoes_do_catalogo_sem_linhas_marcam_estado_vazio(
    client, senha_valida, cenario_catalogo
):
    client.login(username=cenario_catalogo.usuario.matricula, password=senha_valida)

    documento = analisar(
        client.get(
            reverse("catalogo:execucao_detalhe", args=[cenario_catalogo.limpa.pk])
        ).content
    )

    for id_secao in ("divergencias", "alteracoes"):
        secao = documento.unico(id=id_secao)
        if id_secao == "alteracoes":
            assert secao.unico("h2").texto == "Alterações cadastrais (0)"
        assert secao.buscar("table") == []
        vazio = secao.unico(classe="empty")
        assert vazio.get("data-estado") == "vazio"
        assert vazio.unico(classe="empty-state-title").texto


def test_titulo_das_alteracoes_conta_campos_e_entidades_com_singular_e_plural_proprios(
    client, senha_valida, chefe_almoxarifado, criar_material, criar_fornecedor
):
    """Um material (fornecedor) com dois campos alterados: "2 campos em 1 material"."""
    catalogo = _execucao_catalogo(chefe_almoxarifado, inseridos=0, atualizados=1, alterados=1)
    material = criar_material("003.000.001", "1.000")
    for campo, antes, depois in (
        (CampoCadastral.UNIDADE, "UN", "CX"),
        (CampoCadastral.GRUPO, "A", "B"),
    ):
        AlteracaoCadastralMaterial.objects.create(
            execucao=catalogo, material=material, campo=campo,
            valor_anterior=antes, valor_novo=depois,
        )
    fornecedores = _execucao_fornecedores(
        chefe_almoxarifado, inseridos=0, atualizados=1, alterados=1
    )
    fornecedor = criar_fornecedor("000321", "Fornecedor Tres")
    for campo, antes, depois in (("nome", "Antigo", "Fornecedor Tres"), ("tipo", "", "01")):
        AlteracaoFornecedor.objects.create(
            execucao=fornecedores, fornecedor=fornecedor, campo=campo,
            valor_anterior=antes, valor_novo=depois,
        )
    client.login(username=chefe_almoxarifado.matricula, password=senha_valida)

    def titulo(rota, execucao):
        documento = analisar(client.get(reverse(rota, args=[execucao.pk])).content)
        return documento.unico(id="alteracoes").unico("h2").texto

    assert titulo("catalogo:execucao_detalhe", catalogo) == (
        "Alterações cadastrais — 2 campos em 1 material"
    )
    assert titulo("fornecedores:execucao_detalhe", fornecedores) == (
        "Alterações cadastrais — 2 campos em 1 fornecedor"
    )


def _criar_alteracoes_do_catalogo(execucao, criar_material):
    """Material A com 3 campos alterados e material B com 1 (ordem: CADPRO, campo)."""
    a = criar_material("004.000.001", "1.000")
    b = criar_material("004.000.002", "1.000")
    for material, campo in (
        (a, CampoCadastral.DESCRICAO), (a, CampoCadastral.GRUPO), (a, CampoCadastral.UNIDADE),
        (b, CampoCadastral.DESCRICAO),
    ):
        AlteracaoCadastralMaterial.objects.create(
            execucao=execucao, material=material, campo=campo,
            valor_anterior="antes", valor_novo="depois",
        )
    return a, b


def _criar_alteracoes_de_fornecedores(execucao, criar_fornecedor):
    """Fornecedor A com 3 campos alterados e fornecedor B com 1 (ordem: CODIF, campo)."""
    a = criar_fornecedor("000901", "Fornecedor Agrupado")
    b = criar_fornecedor("000902", "Fornecedor Isolado")
    for fornecedor, campo in (
        (a, "documento"), (a, "nome"), (a, "tipo"), (b, "nome"),
    ):
        AlteracaoFornecedor.objects.create(
            execucao=execucao, fornecedor=fornecedor, campo=campo,
            valor_anterior="antes", valor_novo="depois",
        )
    return a, b


def _linhas_de_codigo(documento):
    """`[(span do código, linha secundária ou None)]` de cada linha da tabela de alterações."""
    resultado = []
    for linha in documento.unico(id="alteracoes").unico("tbody").buscar("tr"):
        celula = linha.buscar("td")[0]
        secundarias = celula.buscar(classe="cell-secondary")
        assert len(secundarias) <= 1
        codigo = celula.unico(classe="table-cell-code")
        resultado.append((codigo, secundarias[0] if secundarias else None))
    return resultado


def _verificar_agrupamento(linhas, codigos, nomes):
    """Cada linha tem o código exato; o nome aparece só na primeira linha de cada grupo."""
    assert [codigo.texto for codigo, _ in linhas] == codigos
    anterior = None
    for (codigo, secundaria), nome in zip(linhas, nomes, strict=True):
        if codigo.texto != anterior:
            # Primeira linha do grupo: código visível e nome/descrição atual.
            assert not codigo.tem_classe("visually-hidden")
            assert secundaria is not None and secundaria.texto == nome
        else:
            # Linha seguinte do mesmo código: o código segue no DOM (leitor de tela), oculto.
            assert codigo.tem_classe("visually-hidden")
            assert secundaria is None
        anterior = codigo.texto


@pytest.mark.parametrize("tamanho_pagina", [50, 2], ids=["pagina-cheia", "pagina-de-2-linhas"])
@pytest.mark.parametrize("app", ["catalogo", "fornecedores"])
def test_alteracoes_agrupam_por_codigo_sem_perder_o_codigo_nem_repetir_o_nome(
    client, senha_valida, chefe_almoxarifado, criar_material, criar_fornecedor, monkeypatch,
    app, tamanho_pagina,
):
    monkeypatch.setattr(f"{app}.views.TAMANHO_PAGINA_EXCECOES", tamanho_pagina)
    if app == "catalogo":
        execucao = _execucao_catalogo(chefe_almoxarifado, inseridos=0, atualizados=2, alterados=2)
        _criar_alteracoes_do_catalogo(execucao, criar_material)
        codigos = ["004.000.001"] * 3 + ["004.000.002"]
        nomes = ["Material de teste 004.000.001"] * 3 + ["Material de teste 004.000.002"]
    else:
        execucao = _execucao_fornecedores(
            chefe_almoxarifado, inseridos=0, atualizados=2, alterados=2
        )
        _criar_alteracoes_de_fornecedores(execucao, criar_fornecedor)
        codigos = ["000901"] * 3 + ["000902"]
        nomes = ["Fornecedor Agrupado"] * 3 + ["Fornecedor Isolado"]
    client.login(username=chefe_almoxarifado.matricula, password=senha_valida)
    url = reverse(f"{app}:execucao_detalhe", args=[execucao.pk])

    if tamanho_pagina == 50:
        paginas = [analisar(client.get(url).content)]
        fatias = [slice(0, 4)]
    else:
        paginas = [
            analisar(client.get(url, {"pagina_alteracoes": numero}).content) for numero in (1, 2)
        ]
        fatias = [slice(0, 2), slice(2, 4)]

    for documento, fatia in zip(paginas, fatias, strict=True):
        linhas = _linhas_de_codigo(documento)
        # Em cada página a primeira linha mostra o código e o nome por inteiro, mesmo quando o
        # grupo continua da página anterior (a 2ª página começa no meio do grupo do código A).
        assert linhas[0][0].tem_classe("visually-hidden") is False and linhas[0][1] is not None
        _verificar_agrupamento(linhas, codigos[fatia], nomes[fatia])


@pytest.mark.parametrize(
    "app, id_secao, rotulo",
    [
        pytest.param("catalogo", "divergencias", "Tabela de divergências de saldo",
                     id="catalogo-divergencias"),
        pytest.param("catalogo", "alteracoes", "Tabela de alterações cadastrais",
                     id="catalogo-alteracoes"),
        pytest.param("catalogo", "excecoes", "Tabela de exceções", id="catalogo-excecoes"),
        pytest.param("fornecedores", "alteracoes", "Tabela de alterações cadastrais",
                     id="fornecedores-alteracoes"),
        pytest.param("fornecedores", "excecoes", "Tabela de exceções",
                     id="fornecedores-excecoes"),
    ],
)
def test_tabelas_de_detalhe_rolam_num_wrapper_regiao_nomeada_e_focavel(
    request, client, senha_valida, app, id_secao, rotulo
):
    dados = request.getfixturevalue(f"cenario_{app}")
    client.login(username=dados.usuario.matricula, password=senha_valida)
    documento = analisar(
        client.get(reverse(f"{app}:execucao_detalhe", args=[dados.completa.pk])).content
    )

    secao = documento.unico(id=id_secao)
    wrapper = secao.unico(classe="table-wrapper")

    assert wrapper.get("role") == "region" and wrapper.get("tabindex") == "0"
    # A região tem nome próprio, distinto do título da seção (que já é o marco da `<section>`).
    assert wrapper.get("aria-label") == rotulo
    assert "aria-labelledby" not in wrapper.attrs
    assert wrapper.get("aria-label") != secao.unico("h2").texto
    assert secao.get("aria-labelledby") == secao.unico("h2").get("id")


@_telas(*HISTORICOS)
def test_wrapper_da_tabela_do_historico_e_regiao_nomeada_e_focavel(pagina):
    wrapper = pagina.documento.unico(classe="table-wrapper")

    assert wrapper.get("role") == "region"
    assert wrapper.get("aria-label") == "Execuções de importação"
    assert wrapper.get("tabindex") == "0"


@_telas("fornecedores-consulta")
def test_wrapper_da_consulta_de_fornecedores_nao_e_regiao_e_a_tabela_segue_focavel_por_script(
    pagina,
):
    resultados = pagina.documento.unico(id="resultados-consulta")

    assert "role" not in resultados.unico(classe="table-wrapper").attrs
    assert resultados.unico("table").get("tabindex") == "-1"


def test_wrapper_da_consulta_do_catalogo_nao_e_regiao_e_a_tabela_segue_focavel_por_script(
    client, senha_valida, requisitante, criar_material
):
    criar_material("005.000.001", "1.000")
    client.login(username=requisitante.matricula, password=senha_valida)

    documento = analisar(client.get(reverse("catalogo:consulta")).content)

    resultados = documento.unico(id="resultados-consulta")
    assert "role" not in resultados.unico(classe="table-wrapper").attrs
    assert resultados.unico("table").get("tabindex") == "-1"


def test_valor_anterior_e_novo_das_alteracoes_de_fornecedores_existem_nas_duas_larguras(
    client, senha_valida, cenario_fornecedores
):
    client.login(username=cenario_fornecedores.usuario.matricula, password=senha_valida)
    documento = analisar(
        client.get(
            reverse("fornecedores:execucao_detalhe", args=[cenario_fornecedores.completa.pk])
        ).content
    )
    tabela = documento.unico(id="alteracoes").unico("table")

    # Cabeçalhos: "Valor anterior" só no desktop; o do novo traz os textos das duas larguras.
    cabecalhos = tabela.buscar("th")
    assert cabecalhos[2].texto == "Valor anterior" and cabecalhos[2].tem_classe("so-desktop")
    assert cabecalhos[3].unico(classe="so-desktop").texto == "Valor novo"
    # Versão estreita: "Valor anterior → novo", com a seta decorativa e "e" só para leitor de tela.
    estreito = cabecalhos[3].unico(classe="so-movel")
    assert estreito.unico("span", aria_hidden="true").texto == "→"
    assert estreito.unico(classe="visually-hidden").texto == "e"
    assert "Valor anterior" in estreito.texto and "novo" in estreito.texto

    linhas = {
        linha.unico(classe="table-cell-code").texto: linha
        for linha in tabela.unico("tbody").buscar("tr")
    }
    renomeado = linhas["000456"].buscar("td")
    # Desktop: coluna do valor anterior com o valor.
    assert renomeado[2].tem_classe("so-desktop") and renomeado[2].texto == "Fornecedor Antigo"
    # Celular: o mesmo valor anterior na célula do novo, com o rótulo só para leitor de tela,
    # e a seta decorativa escondida da árvore de acessibilidade.
    compacto = renomeado[3].unico("div", classe="so-movel")
    assert compacto.unico(classe="visually-hidden").texto == "Valor anterior:"
    # (`texto` põe o texto próprio antes do dos filhos; aqui só importa o conjunto.)
    assert "Fornecedor Antigo" in compacto.texto
    ponte = renomeado[3].unico("span", classe="so-movel")
    assert ponte.unico("span", aria_hidden="true").texto == "→"
    assert ponte.unico(classe="visually-hidden").texto == "Valor novo:"
    # O valor novo continua na célula, fora dos wrappers só-móvel.
    assert "Fornecedor Dois" in renomeado[3].texto
    # A mudança para bloqueado mantém o selo com texto e o valor anterior nas duas posições.
    bloqueado = linhas["000123"].buscar("td")
    assert bloqueado[3].unico(classe="badge").texto == "Bloqueado"
    anterior = bloqueado[2].texto
    assert anterior and anterior in bloqueado[3].unico("div", classe="so-movel").texto


@pytest.mark.parametrize("app, largo", [("catalogo", 42), ("fornecedores", 56)])
def test_nome_do_arquivo_do_historico_tem_versao_larga_e_estreita_com_nome_completo_no_dom(
    client, senha_valida, chefe_almoxarifado, app, largo
):
    from interface.templatetags.interface_extras import truncar_meio

    criar = _execucao_catalogo if app == "catalogo" else _execucao_fornecedores
    nomes = {
        "cabe-nas-duas": "a" * 28 + ".csv",  # 32 caracteres
        "so-na-larga": "m" * (largo - 4) + ".csv",  # cabe na larga, não na estreita
        "nao-cabe": "l" * (largo - 3) + ".csv",  # 1 acima do corte da larga
    }
    for nome in nomes.values():
        criar(chefe_almoxarifado, nome=nome)
    client.login(username=chefe_almoxarifado.matricula, password=senha_valida)
    documento = analisar(client.get(reverse(f"{app}:historico")).content)

    def versao(nome, classe):
        for celula in documento.buscar("td", classe="table-cell-filename"):
            bloco = celula.unico(classe=classe)
            completo = bloco.buscar(classe="table-cell-filename-completo")
            texto_simples = bloco.buscar(classe="table-cell-filename-nome")
            exibido = completo[0].texto if completo else texto_simples[0].texto
            if exibido == nome:
                return bloco
        raise AssertionError(f"{nome!r} não encontrado em {classe}")

    for nome in nomes.values():
        bloco_largo = versao(nome, "nome-arquivo-largo")
        bloco_estreito = versao(nome, "nome-arquivo-estreito")
        for bloco, limite in ((bloco_largo, largo), (bloco_estreito, 32)):
            if len(nome) <= limite:
                # Cabe: texto simples, sem `<details>`.
                assert bloco.buscar("details") == []
                assert bloco.unico(classe="table-cell-filename-nome").texto == nome
            else:
                # Não cabe: `<details>` fechado, resumo cortado no meio, nome completo no DOM.
                (detalhe,) = bloco.buscar("details")
                assert "open" not in detalhe.attrs
                resumo = detalhe.unico("summary").texto
                assert resumo == truncar_meio(nome, limite) and len(resumo) == limite
                assert detalhe.unico(classe="table-cell-filename-completo").texto == nome


def test_excecao_sem_detalhe_mostra_so_o_motivo_sem_linha_secundaria(
    client, senha_valida, chefe_almoxarifado
):
    catalogo = _execucao_catalogo(chefe_almoxarifado, inseridos=0, rejeitados=1)
    ExcecaoImportacao.objects.create(
        execucao=catalogo, linha_inicial=3, linha_final=5, cadpro="",
        motivo=MotivoRecusa.ESTRUTURA_INCONSISTENTE, detalhe="",
    )
    fornecedores = _execucao_fornecedores(chefe_almoxarifado, inseridos=0, rejeitados=1)
    ExcecaoImportacaoFornecedores.objects.create(
        execucao=fornecedores, linha=4, codif="",
        motivo=MotivoRecusaFornecedor.NOME_AUSENTE, detalhe="",
    )
    client.login(username=chefe_almoxarifado.matricula, password=senha_valida)

    for rota, execucao, motivo in (
        ("catalogo:execucao_detalhe", catalogo, MotivoRecusa.ESTRUTURA_INCONSISTENTE.label),
        ("fornecedores:execucao_detalhe", fornecedores, MotivoRecusaFornecedor.NOME_AUSENTE.label),
    ):
        documento = analisar(client.get(reverse(rota, args=[execucao.pk])).content)
        (linha,) = documento.unico(id="excecoes").unico("tbody").buscar("tr")
        celulas = linha.buscar("td")
        assert len(celulas) == 3
        assert celulas[2].texto == motivo
        assert celulas[2].buscar(classe="cell-secondary") == []


def test_alteracoes_de_fornecedores_sem_linhas_dizem_em_texto_que_nao_ha_nenhuma(
    client, senha_valida, cenario_fornecedores
):
    client.login(username=cenario_fornecedores.usuario.matricula, password=senha_valida)

    documento = analisar(
        client.get(
            reverse("fornecedores:execucao_detalhe", args=[cenario_fornecedores.limpa.pk])
        ).content
    )

    secao = documento.unico(id="alteracoes")
    assert secao.get("data-secao") == "alteracoes"
    assert secao.unico("h2").texto == "Alterações cadastrais (0)"
    assert secao.buscar("table") == []
    assert "Nenhuma alteração cadastral nesta execução." in secao.unico(classe="empty").texto


# ---------------------------------------------------------------------------
# 4. Paginação das seções da execução: âncora, parâmetro e IDs de foco
# ---------------------------------------------------------------------------

_QUANTIDADE = 51  # uma a mais que o tamanho de página (50).


def _encher_execucao_do_catalogo(usuario, criar_material):
    execucao = _execucao_catalogo(
        usuario, inseridos=0, atualizados=_QUANTIDADE, alterados=_QUANTIDADE,
        rejeitados=_QUANTIDADE, divergencias=_QUANTIDADE,
    )
    materiais = [criar_material(f"002.000.{indice:03d}", "1.000") for indice in range(_QUANTIDADE)]
    DivergenciaSaldo.objects.bulk_create(
        DivergenciaSaldo(
            execucao=execucao, material=material, saldo_wms=Decimal("1.000"),
            saldo_arquivo=Decimal("2.000"), diferenca=Decimal("1.000"),
        )
        for material in materiais
    )
    AlteracaoCadastralMaterial.objects.bulk_create(
        AlteracaoCadastralMaterial(
            execucao=execucao, material=material, campo=CampoCadastral.UNIDADE,
            valor_anterior="UN", valor_novo="CX",
        )
        for material in materiais
    )
    ExcecaoImportacao.objects.bulk_create(
        ExcecaoImportacao(
            execucao=execucao, linha_inicial=indice + 1, linha_final=indice + 1,
            cadpro=f"9{indice}", motivo=MotivoRecusa.CADPRO_FORMATO_INVALIDO,
        )
        for indice in range(_QUANTIDADE)
    )
    return execucao


def _encher_execucao_de_fornecedores(usuario, criar_fornecedor):
    execucao = _execucao_fornecedores(
        usuario, inseridos=0, atualizados=_QUANTIDADE, alterados=_QUANTIDADE,
        rejeitados=_QUANTIDADE,
    )
    fornecedores = [
        criar_fornecedor(str(100000 + indice), f"Fornecedor {indice}")
        for indice in range(_QUANTIDADE)
    ]
    AlteracaoFornecedor.objects.bulk_create(
        AlteracaoFornecedor(
            execucao=execucao, fornecedor=fornecedor, campo="tipo", valor_anterior="",
            valor_novo="01",
        )
        for fornecedor in fornecedores
    )
    ExcecaoImportacaoFornecedores.objects.bulk_create(
        ExcecaoImportacaoFornecedores(
            execucao=execucao, linha=indice + 1, codif=f"9{indice}",
            motivo=MotivoRecusaFornecedor.CODIF_AUSENTE,
        )
        for indice in range(_QUANTIDADE)
    )
    return execucao


SECOES_PAGINADAS = [
    pytest.param("catalogo", "divergencias", "pagina_divergencias", "Paginação de divergências",
                 id="catalogo-divergencias"),
    pytest.param("catalogo", "alteracoes", "pagina_alteracoes",
                 "Paginação de alterações cadastrais", id="catalogo-alteracoes"),
    pytest.param("catalogo", "excecoes", "pagina_excecoes", "Paginação de exceções",
                 id="catalogo-excecoes"),
    pytest.param("fornecedores", "alteracoes", "pagina_alteracoes",
                 "Paginação de alterações cadastrais", id="fornecedores-alteracoes"),
    pytest.param("fornecedores", "excecoes", "pagina_excecoes", "Paginação de exceções",
                 id="fornecedores-excecoes"),
]


@pytest.mark.parametrize("app, id_secao, parametro, rotulo", SECOES_PAGINADAS)
def test_paginacao_de_secao_fica_no_card_da_secao_com_ancora_parametro_e_ids_unicos(
    client, senha_valida, chefe_almoxarifado, criar_material, criar_fornecedor,
    app, id_secao, parametro, rotulo,
):
    if app == "catalogo":
        execucao = _encher_execucao_do_catalogo(chefe_almoxarifado, criar_material)
    else:
        execucao = _encher_execucao_de_fornecedores(chefe_almoxarifado, criar_fornecedor)
    url = reverse(f"{app}:execucao_detalhe", args=[execucao.pk])
    client.login(username=chefe_almoxarifado.matricula, password=senha_valida)

    documento = analisar(client.get(url).content)

    # Três (ou duas) paginações na mesma página: nenhum ID pode se repetir entre elas.
    ids = [no.attrs["id"] for no in documento.buscar(id=True)]
    assert len(ids) == len(set(ids))
    secao = documento.unico("section", id=id_secao)
    paginacao = secao.unico("nav", aria_label=rotulo)
    assert paginacao.texto.startswith("Página 1 de 2")
    if id_secao == "alteracoes":
        entidade = "materiais" if app == "catalogo" else "fornecedores"
        titulo = f"Alterações cadastrais — {_QUANTIDADE} campos em {_QUANTIDADE} {entidade}"
        assert secao.unico("h2").texto == titulo
    proxima = paginacao.unico("a", id=f"pagina-proxima-{parametro}")
    href = proxima.get("href")
    assert href.endswith(f"#{id_secao}") and f"{parametro}=2" in href
    # Navegação de página inteira (sem troca parcial): a seção volta à sua âncora.
    assert "hx-get" not in proxima.attrs
    # Seguir o link mostra a página 2 dessa seção, com o resumo coerente.
    destino = analisar(client.get(url + href.split("#")[0]).content)
    resumo = destino.unico(id=id_secao).unico("nav", aria_label=rotulo).unico(
        classe="pagination-summary"
    )
    assert resumo.texto.startswith("Página 2 de 2")


# ---------------------------------------------------------------------------
# 5. Históricos: tabela e paginação no card, linha clicável, estado vazio
# ---------------------------------------------------------------------------


@_telas(*HISTORICOS)
def test_historico_tem_um_unico_card_com_tabela_e_paginacao_dentro(pagina):
    principal = pagina.documento.unico("main")

    (card,) = principal.buscar(classe="card")
    assert _dentro_de_classe(card.unico("table"), "table-wrapper")
    assert card.unico("nav", classe="pagination")
    assert principal.buscar("table") == card.buscar("table")


@_telas(*HISTORICOS)
def test_linhas_do_historico_sao_clicaveis_e_cada_uma_leva_ao_proprio_detalhe(pagina):
    app = "catalogo" if "catalogo" in pagina.url else "fornecedores"
    esperado = {
        reverse(f"{app}:execucao_detalhe", args=[execucao.pk])
        for execucao in (pagina.cenario.completa, pagina.cenario.limpa)
    }

    linhas = pagina.documento.unico("tbody").buscar("tr")

    # Outras execuções (as de fixtures de apoio) também aparecem; todas seguem o contrato.
    obtido = []
    for linha in linhas:
        assert "data-linha-clicavel" in linha.attrs
        (link,) = linha.buscar("a", data_linha_link=True)
        assert hrefs_de(linha) == {link.get("href")}
        obtido.append(link.get("href"))
    assert len(obtido) == len(set(obtido))
    assert esperado <= set(obtido)


@_telas(*HISTORICOS)
def test_script_de_linha_clicavel_e_carregado_uma_unica_vez(pagina):
    scripts = [
        s for s in pagina.documento.buscar("script", src=True)
        if s.attrs["src"].endswith("/js/linha-clicavel.js")
    ]

    assert len(scripts) == 1 and "defer" in scripts[0].attrs


@_telas("catalogo-execucao", "fornecedores-execucao", "fornecedores-consulta")
def test_telas_sem_linha_clicavel_nao_carregam_o_script(pagina):
    assert pagina.documento.buscar(data_linha_clicavel=True) == []
    assert not any(
        s.attrs["src"].endswith("/js/linha-clicavel.js")
        for s in pagina.documento.buscar("script", src=True)
    )


@_telas(*HISTORICOS)
def test_situacao_e_rejeitados_do_historico_dizem_o_estado_em_texto_alem_da_enfase(pagina):
    app = "catalogo" if "catalogo" in pagina.url else "fornecedores"
    linha_de = {}
    for linha in pagina.documento.unico("tbody").buscar("tr"):
        (href,) = hrefs_de(linha)
        linha_de[href] = linha

    com = linha_de[reverse(f"{app}:execucao_detalhe", args=[pagina.cenario.completa.pk])]
    sem = linha_de[reverse(f"{app}:execucao_detalhe", args=[pagina.cenario.limpa.pk])]

    assert com.unico(classe="badge").texto == "Com rejeições"
    assert com.unico(classe="badge").tem_classe("badge-warning")
    (rejeitados,) = com.buscar("td", classe="emphasis-warning")
    assert rejeitados.texto == "1"
    assert sem.unico(classe="badge").texto == "Sem rejeições"
    assert sem.unico(classe="badge").tem_classe("badge-success")
    assert sem.buscar(classe="emphasis-warning") == []


@pytest.mark.parametrize(
    "rota", [pytest.param("catalogo:historico", id="catalogo"),
             pytest.param("fornecedores:historico", id="fornecedores")]
)
def test_historico_sem_execucoes_mostra_estado_vazio_dentro_do_card_sem_tabela(
    client, senha_valida, chefe_almoxarifado, rota
):
    client.login(username=chefe_almoxarifado.matricula, password=senha_valida)

    documento = analisar(client.get(reverse(rota)).content)

    principal = documento.unico("main")
    (card,) = principal.buscar(classe="card")
    vazio = card.unico(classe="empty")
    assert vazio.get("data-estado") == "vazio"
    assert vazio.unico(classe="empty-state-title").texto == "Nenhuma importação registrada."
    assert principal.buscar("table") == [] and principal.buscar(classe="pagination") == []
    assert len(documento.buscar(data_estado="vazio")) == 1


# ---------------------------------------------------------------------------
# 6. Consulta de fornecedores: resultados num card, dados sem transformação, HTMX
# ---------------------------------------------------------------------------


@_telas("fornecedores-consulta")
def test_resultados_da_consulta_ficam_num_unico_card_com_tabela_paginacao_e_alertas_fora(pagina):
    documento = pagina.documento

    resultados = documento.unico(id="resultados-consulta")
    assert resultados.tem_classe("card")
    assert _dentro_de_classe(resultados.unico("table"), "table-wrapper")
    assert resultados.unico("table").get("tabindex") == "-1"
    assert resultados.unico("nav", classe="pagination")
    # Indicador e alertas de falha existem fora da região trocada pelo HTMX.
    for id_fora in ("resultados-indicador", "resultados-erro-rede", "resultados-erro-servidor"):
        assert resultados not in list(documento.unico(id=id_fora).ancestrais()), id_fora
    for id_alerta in ("resultados-erro-rede", "resultados-erro-servidor"):
        assert "hidden" in documento.unico(id=id_alerta).attrs
    # Os cabeçalhos ordenáveis mantêm os IDs que o HTMX usa para devolver o foco.
    for coluna in ("codigo", "nome", "documento"):
        assert documento.unico("a", id=f"ordenar-{coluna}")
    # O HTMX com a configuração de settle fica uma vez no <head>.
    cabeca = documento.unico("head")
    scripts_htmx = [
        s for s in cabeca.buscar("script", src=True) if "htmx" in s.attrs["src"]
    ]
    assert len(scripts_htmx) == 1
    assert len(cabeca.buscar("meta", name="htmx-config")) == 1


@_telas("fornecedores-consulta")
def test_consulta_exibe_codif_e_documento_exatamente_como_gravados(pagina):
    linhas = pagina.documento.unico(id="resultados-consulta").unico("tbody").buscar("tr")

    por_codigo = {linha.buscar("td")[0].texto: linha for linha in linhas}

    assert set(por_codigo) == {"000123", "000456"}
    celulas = por_codigo["000123"].buscar("td", classe="table-cell-code")
    assert [celula.texto for celula in celulas][:2] == ["000123", "12.345.678/0001-90"]
    # Bloqueado diz "Bloqueado" em texto (selo com forma), liberado diz "Liberado".
    assert por_codigo["000456"].unico(classe="badge").texto == "Bloqueado"
    assert "Liberado" in por_codigo["000123"].texto


def test_consulta_sem_resultado_marca_estado_vazio_na_linha_de_tabela(
    client, senha_valida, cenario_consulta
):
    client.login(username=cenario_consulta.usuario.matricula, password=senha_valida)

    resposta = client.get(reverse("fornecedores:consulta"), {"nome": "inexistente"})
    documento = analisar(resposta.content)

    resultados = documento.unico(id="resultados-consulta")
    (vazio,) = documento.buscar(data_estado="vazio")
    assert vazio.tem_classe("table-empty-row") and vazio.esta_dentro_de("table")
    assert resultados in list(vazio.ancestrais())
    assert "Nenhum fornecedor encontrado." in vazio.texto
    assert documento.buscar(classe="table-sticky-header") == []


def test_fragmento_htmx_da_consulta_traz_resultados_e_copias_oob_dos_campos_sem_o_shell(
    client, senha_valida, cenario_consulta
):
    client.login(username=cenario_consulta.usuario.matricula, password=senha_valida)
    url = reverse("fornecedores:consulta")

    fragmento = client.get(url, {"codigo": "000123"}, **HX)
    pagina_inteira = analisar(client.get(url, {"codigo": "000123"}).content)

    assert fragmento.status_code == 200
    conteudo = fragmento.content.decode()
    documento = analisar(conteudo)
    # Sem shell: nem sidebar, nem logout, nem marca, nem o container que é o próprio alvo do swap.
    assert 'class="side"' not in conteudo
    assert 'action="/logout/"' not in conteudo
    assert "Almoxarifado SAEP" not in conteudo
    assert documento.buscar("main") == [] and documento.buscar(id="resultados-consulta") == []
    # Cópias OOB dos dois campos, uma de cada, e os resultados da busca.
    oob = {no.attrs["id"] for no in documento.buscar(hx_swap_oob=True)}
    assert oob == {"campo-codigo", "campo-documento"}
    assert [td.texto for td in documento.unico("tbody").buscar("td", classe="table-cell-code")][
        0
    ] == "000123"
    # Na página inteira os campos saem certos da primeira vez: nada de OOB.
    assert pagina_inteira.buscar(hx_swap_oob=True) == []
    assert len(pagina_inteira.buscar(id="campo-codigo")) == 1
    assert len(pagina_inteira.buscar(id="campo-documento")) == 1
