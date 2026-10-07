"""Contrato de markup do lote P3 do redesign (telas de importação), `docs/redesign-observatory/`.

Superfícies cobertas: envio e prévia da importação do catálogo (S9, S10) e envio e prévia da
importação de fornecedores (S13, S14). Mesmo molde de `tests/test_consultas_historicos_markup.py`
(P2): parsing estrutural por `tests/html_helpers.py`, nunca regex de espaçamento; o usuário é
sempre o chefe do almoxarifado (`PERM-SCPI-IMPORT-EXECUTE`).

O que este arquivo protege, em ordem de consequência:

- a barra de confirmação, que dispara a gravação irreversível: um único form para confirmar e um
  único para cancelar, `token`/`impressao_digital`/CSRF presentes, Confirmar antes de Cancelar,
  barra como último elemento da página e o rótulo longo do botão com os totais certos (o usuário
  confirma lendo esse rótulo);
- CADPRO e CODIF exibidos exatamente como lidos do arquivo (`INV-CATALOG-001`);
- a situação de bloqueio de fornecedores em destaque antes de confirmar (`INV-SUPPLIER-005`):
  `tile-warning` só quando há fornecedores passando a bloqueado ou chegando bloqueados, sempre com
  rótulo e total em texto (ênfase nunca só por cor);
- o aviso de que nada foi gravado ainda e a leitura de cada total ao lado do rótulo certo;
- ganchos que `static/js/envio.js` e os leitores de tela usam: `data-processing-*`,
  `data-file-upload-*`, `aria-describedby` do campo de arquivo apontando para o erro, regiões de
  tabela nomeadas, IDs e `data-secao` das seções;
- nenhum markup da fundação anterior e um único `<main>`, com mensagens não duplicadas.

Não duplica: efeitos de domínio da prévia (nada gravado, sessão, confirmação, recusas) em
`test_catalogo_views_importacao.py` e `test_fornecedores_views_importacao.py`; regras de
reimportação em `test_fornecedores_reimportacao.py`; o shell em `tests/test_shell.py`.
"""

import hashlib
import uuid
from types import SimpleNamespace

import pytest
from django.contrib.messages import constants as niveis
from django.contrib.messages.storage.cookie import CookieStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpRequest, HttpResponse
from django.urls import reverse

from catalogo.models import MotivoRecusa
from tests.html_helpers import analisar

pytestmark = pytest.mark.django_db

APPS = ["catalogo", "fornecedores"]
PREFIXOS_LEGADOS = ("page-header", "section-marker")
CLASSES_LEGADAS = frozenset(
    {
        "page",
        "page-container",
        "back-link",
        "table-sticky-header",
        "summary",
        "summary-item",
        "form-frame",
        "table-row-error",
    }
)

_CABECALHO_FORNECEDORES = "CODIF;NOME;NOM_FANT;INSMF;CODTIP;BLOQ_OPCAO;MSG_BLOQ;TIPO_BLOQ;"


# ---------------------------------------------------------------------------
# Montagem: envio de arquivo, plano de prévia e importações já confirmadas.
# ---------------------------------------------------------------------------


@pytest.fixture
def chefe(client, chefe_almoxarifado, senha_valida):
    """Cliente autenticado como chefe do almoxarifado."""
    assert client.login(username=chefe_almoxarifado.matricula, password=senha_valida)
    return SimpleNamespace(client=client, usuario=chefe_almoxarifado)


def _enviar(client, app, conteudo, nome="arquivo.csv"):
    arquivo = SimpleUploadedFile(nome, conteudo, content_type="text/csv")
    return client.post(reverse(f"{app}:importacao_envio"), {"arquivo": arquivo})


def _linha_fornecedor(codif, nome, *, bloq="S", motivo="", tipo_bloq="", tipo="01"):
    return f"{codif};{nome};;;{tipo};{bloq};{motivo};{tipo_bloq};"


def _arquivo_fornecedores(*linhas):
    return ("﻿" + "\r\n".join([_CABECALHO_FORNECEDORES, *linhas]) + "\r\n").encode()


def _bloqueado(codif, nome, **extras):
    return _linha_fornecedor(
        codif, nome, bloq="B", motivo="NAO PODE SER UTILIZADO", tipo_bloq="CNPJ", **extras
    )


def _plano_e_pedido(client, app):
    """O pedido de prévia da sessão e o plano recalculado a partir dele (a verdade do domínio,
    contra a qual os totais exibidos são conferidos)."""
    if app == "catalogo":
        from catalogo import importacao

        pedido = importacao.obter_pedido(client.session)
        return pedido, importacao.calcular_plano(pedido.conteudo)
    from fornecedores import importacao

    pedido = importacao.obter_pedido(client.session)
    return pedido, importacao.calcular_plano(pedido.leitura, pedido.sha256)


def _confirmar_diretamente(app, conteudo, usuario):
    """Prepara um cadastro pré-existente pela camada de domínio, sem repetir o fluxo HTTP."""
    if app == "catalogo":
        from catalogo import importacao

        plano = importacao.calcular_plano(conteudo)
        pedido = importacao.PedidoPrevia(
            token=str(uuid.uuid4()), nome_arquivo="base.csv", tamanho=len(conteudo),
            sha256=plano.sha256_arquivo, conteudo=conteudo,
        )
    else:
        from fornecedores import importacao
        from fornecedores import leitura_fornecedores as lf

        leitura = lf.ler_fornecedores(conteudo)
        sha256 = hashlib.sha256(conteudo).hexdigest()
        plano = importacao.calcular_plano(leitura, sha256)
        pedido = importacao.PedidoPrevia(
            token=str(uuid.uuid4()), nome_arquivo="base.csv", tamanho=len(conteudo),
            sha256=sha256, leitura=leitura,
        )
    return importacao.confirmar_importacao(pedido, plano.impressao_digital, usuario)


def _abrir_previa(chefe, app, conteudo, nome="carga.csv"):
    resposta = _enviar(chefe.client, app, conteudo, nome)
    assert resposta.status_code == 302, "o envio deveria seguir para a prévia"
    pedido, plano = _plano_e_pedido(chefe.client, app)
    resposta = chefe.client.get(reverse(f"{app}:importacao_previa"))
    assert resposta.status_code == 200
    return SimpleNamespace(
        app=app,
        pedido=pedido,
        plano=plano,
        conteudo=resposta.content.decode(),
        documento=analisar(resposta.content),
    )


def _abrir_envio(chefe, app):
    resposta = chefe.client.get(reverse(f"{app}:importacao_envio"))
    assert resposta.status_code == 200
    return analisar(resposta.content)


# Cenários de prévia. O CATÁLOGO usa as fixtures do domínio: "com rejeitados" é uma carga inicial
# (9 inseridos, 13 rejeitados) e "limpa" é a reimportação sobre a carga válida (1 inserido, 8
# atualizados, 4 com alteração, 0 rejeitados, 1 divergência de saldo, 1 ausente).


@pytest.fixture
def previa_catalogo_com_rejeitados(chefe, csv_fixture):
    return _abrir_previa(chefe, "catalogo", csv_fixture("carga_inicial_casos_spec.csv"))


@pytest.fixture
def previa_catalogo_limpa(chefe, csv_fixture):
    _confirmar_diretamente("catalogo", csv_fixture("carga_inicial_valida.csv"), chefe.usuario)
    return _abrir_previa(chefe, "catalogo", csv_fixture("reimportacao.csv"))


# FORNECEDORES: sobre uma base de 5 cadastros (700003 já bloqueado e 000123 com zeros à esquerda),
# o arquivo "com bloqueios" traz um fornecedor com 2 campos alterados (700001), um que passa a
# bloqueado (700002), um que volta a liberado (700003), um novo já bloqueado (000777), um
# rejeitado (000789, sem BLOQ_OPCAO) e um ausente (700004). "limpa" repete a base.

_BASE_FORNECEDORES = (
    _linha_fornecedor("700001", "FORNECEDOR ALFA"),
    _linha_fornecedor("700002", "FORNECEDOR BETA"),
    _bloqueado("700003", "FORNECEDOR GAMA"),
    _linha_fornecedor("700004", "FORNECEDOR DELTA"),
    _linha_fornecedor("000123", "FORNECEDOR ZEROS"),
)


@pytest.fixture
def previa_fornecedores_com_bloqueios(chefe):
    base = _arquivo_fornecedores(*_BASE_FORNECEDORES)
    _confirmar_diretamente("fornecedores", base, chefe.usuario)
    novo = _arquivo_fornecedores(
        _linha_fornecedor("700001", "FORNECEDOR ALFA REVISADO", tipo="02"),
        _bloqueado("700002", "FORNECEDOR BETA"),
        _linha_fornecedor("700003", "FORNECEDOR GAMA"),
        _linha_fornecedor("000123", "FORNECEDOR ZEROS REVISADO"),
        _bloqueado("000777", "FORNECEDOR NOVO BLOQUEADO"),
        "000789;FORNECEDOR RECUSADO;;;01;;;;",
    )
    return _abrir_previa(chefe, "fornecedores", novo)


@pytest.fixture
def previa_fornecedores_limpa(chefe):
    conteudo = _arquivo_fornecedores(*_BASE_FORNECEDORES)
    _confirmar_diretamente("fornecedores", conteudo, chefe.usuario)
    return _abrir_previa(chefe, "fornecedores", conteudo)


@pytest.fixture
def previa_fornecedores_plural(chefe):
    """Todos os totais de situação e os rejeitados em 2: exercita o plural do rótulo do botão e
    da linha de resumo da barra (duas cópias da mesma pluralização no template)."""
    base = _arquivo_fornecedores(
        _linha_fornecedor("700001", "FORNECEDOR ALFA"),
        _linha_fornecedor("700002", "FORNECEDOR BETA"),
        _bloqueado("700003", "FORNECEDOR GAMA"),
        _bloqueado("700004", "FORNECEDOR DELTA"),
        _linha_fornecedor("000123", "FORNECEDOR ZEROS"),
    )
    _confirmar_diretamente("fornecedores", base, chefe.usuario)
    novo = _arquivo_fornecedores(
        _bloqueado("700001", "FORNECEDOR ALFA"),
        _bloqueado("700002", "FORNECEDOR BETA"),
        _linha_fornecedor("700003", "FORNECEDOR GAMA"),
        _linha_fornecedor("700004", "FORNECEDOR DELTA"),
        _linha_fornecedor("000123", "FORNECEDOR ZEROS"),
        _bloqueado("000777", "FORNECEDOR NOVO UM"),
        _bloqueado("000778", "FORNECEDOR NOVO DOIS"),
        "000789;FORNECEDOR RECUSADO UM;;;01;;;;",
        "000790;FORNECEDOR RECUSADO DOIS;;;01;;;;",
    )
    return _abrir_previa(chefe, "fornecedores", novo)


@pytest.fixture
def previa_com_rejeitados(request):
    return request.getfixturevalue(
        {
            "catalogo": "previa_catalogo_com_rejeitados",
            "fornecedores": "previa_fornecedores_com_bloqueios",
        }[request.param]
    )


@pytest.fixture
def previa_limpa(request):
    """A prévia do mesmo app sem rejeitados (e, em fornecedores, sem mudança de situação)."""
    return request.getfixturevalue(
        {"catalogo": "previa_catalogo_limpa", "fornecedores": "previa_fornecedores_limpa"}[
            request.param
        ]
    )


def _por_app(*apps):
    return pytest.mark.parametrize("previa_com_rejeitados", apps, indirect=True, ids=apps)


def _tile(documento, rotulo):
    (tile,) = [
        t for t in documento.buscar(classe="tile") if t.unico("dt", classe="k").texto == rotulo
    ]
    return tile


def _totais_da_previa(documento):
    """`{rótulo: valor}` de todos os tiles do resumo, em ordem, venham de um `dl` ou de vários
    (a prévia de fornecedores tem dois grupos). Falha se um rótulo se repetir."""
    totais = {}
    for tile in documento.unico("section", aria_labelledby="resumo-titulo").buscar(classe="tile"):
        rotulo = tile.unico("dt", classe="k").texto
        assert rotulo not in totais, f"rótulo duplicado no resumo: {rotulo!r}"
        totais[rotulo] = tile.unico("dd", classe="v").texto
    return totais


def _notas(tile):
    return [dd.texto for dd in tile.buscar("dd", classe="d")]


def _notas_do_tile(documento, rotulo):
    return _notas(_tile(documento, rotulo))


def _texto_das_celulas(linha):
    return [celula.texto for celula in linha.buscar("td")]


# ---------------------------------------------------------------------------
# 1. Todas as telas: shell único, sem fundação anterior, mensagens uma única vez.
# ---------------------------------------------------------------------------

TELAS = {
    "catalogo-envio": lambda c: (
        reverse("catalogo:importacao_envio"),
        "Importar catálogo",
    ),
    "fornecedores-envio": lambda c: (
        reverse("fornecedores:importacao_envio"),
        "Importar fornecedores",
    ),
    "catalogo-previa": lambda c: (
        reverse("catalogo:importacao_previa"),
        "Prévia da importação do catálogo Não gravada",
    ),
    "fornecedores-previa": lambda c: (
        reverse("fornecedores:importacao_previa"),
        "Prévia da importação de fornecedores Não gravada",
    ),
}


@pytest.fixture
def tela(request, chefe, csv_fixture):
    """A tela parametrizada já preparada (uma prévia exige um arquivo enviado antes)."""
    app = request.param.split("-")[0]
    if request.param.endswith("-previa"):
        conteudo = (
            csv_fixture("carga_inicial_valida.csv")
            if app == "catalogo"
            else _arquivo_fornecedores(*_BASE_FORNECEDORES)
        )
        assert _enviar(chefe.client, app, conteudo).status_code == 302
    url, h1 = TELAS[request.param](chefe)
    return SimpleNamespace(client=chefe.client, url=url, h1=h1, app=app)


def _telas(*nomes):
    return pytest.mark.parametrize(
        "tela", [pytest.param(nome, id=nome) for nome in nomes], indirect=True
    )


@_telas(*TELAS)
def test_tela_tem_um_unico_main_e_o_h1_no_cabecalho(tela):
    resposta = tela.client.get(tela.url)

    assert resposta.status_code == 200
    documento = analisar(resposta.content)
    principal = documento.unico("main", id="main")
    assert len(documento.buscar("main")) == 1
    (titulo,) = documento.buscar("h1")
    assert titulo.texto == tela.h1
    assert titulo.esta_dentro_de("main")
    assert any(a.tem_classe("top") and a.pai is principal for a in titulo.ancestrais())


@_telas(*TELAS)
def test_tela_nao_traz_markup_da_fundacao_anterior(tela):
    documento = analisar(tela.client.get(tela.url).content)

    for no in documento.descendentes():
        classes = no.get("class", "").split()
        legadas = [
            c for c in classes
            if c in CLASSES_LEGADAS or c.startswith(PREFIXOS_LEGADOS)
        ]
        assert legadas == [], f"<{no.tag}> com classe da fundação anterior: {legadas}"


def _deixar_mensagem_pendente(client, nivel, texto):
    """Enfileira uma mensagem como o `messages.add_message` de uma view anterior."""
    armazenamento = CookieStorage(HttpRequest())
    armazenamento.add(nivel, texto)
    resposta = HttpResponse()
    armazenamento.update(resposta)
    client.cookies["messages"] = resposta.cookies["messages"].value


@pytest.mark.parametrize(
    "nivel, classe, papel",
    [
        pytest.param(niveis.SUCCESS, "alert-success", "status", id="sucesso"),
        pytest.param(niveis.ERROR, "error-box", "alert", id="erro"),
    ],
)
@_telas(*TELAS)
def test_mensagem_pendente_aparece_uma_unica_vez_no_main(tela, nivel, classe, papel):
    texto = "Mensagem-de-teste-unica-7c1e"
    _deixar_mensagem_pendente(tela.client, nivel, texto)

    resposta = tela.client.get(tela.url)

    documento = analisar(resposta.content)
    (container,) = documento.buscar(classe="messages")
    assert container.pai is documento.unico("main")
    (mensagem,) = container.buscar(classe=classe)
    assert (mensagem.get("role"), mensagem.texto) == (papel, texto)
    assert resposta.content.decode().count(texto) == 1


# ---------------------------------------------------------------------------
# 2. Envio: card de formulário e contratos de `static/js/envio.js`.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("app", APPS)
def test_envio_traz_o_formulario_dentro_do_card_com_os_ganchos_do_javascript(chefe, app):
    documento = _abrir_envio(chefe, app)

    card = documento.unico("main").unico(classe="card-form")
    assert card.tem_classe("card")
    formulario = card.unico("form")
    assert (formulario.get("method"), formulario.get("enctype")) == ("post", "multipart/form-data")
    assert "action" not in formulario.attrs  # volta para a própria rota
    assert "data-processing-form" in formulario.attrs
    assert formulario.get("data-processing-label") == "Enviando…"
    assert formulario.buscar("input", type="hidden", name="csrfmiddlewaretoken")
    # O seletor de arquivo: o input do widget, o rótulo do botão e o texto de metadados.
    entrada = formulario.unico("input", type="file", name="arquivo")
    assert "data-file-upload-input" in entrada.attrs
    assert "aria-describedby" not in entrada.attrs and formulario.buscar(classe="field-error") == []
    assert formulario.unico(classe="file-upload-meta").get("data-file-upload-meta") == ""
    assert formulario.unico("label", classe="file-upload-trigger").get("for") == entrada.get("id")
    # O botão que o JavaScript troca por "Enviando…" e o rótulo dentro dele.
    (botao,) = formulario.buscar("button", type="submit")
    assert "data-processing-submit" in botao.attrs
    assert botao.unico("span").get("data-processing-submit-label") == ""
    assert botao.texto == "Enviar arquivo"


@pytest.mark.parametrize("app", APPS)
def test_envio_leva_ao_historico_pelas_ferramentas_do_cabecalho(chefe, app):
    documento = _abrir_envio(chefe, app)

    ferramentas = documento.unico("main").unico(classe="tools")
    (link,) = ferramentas.buscar("a")
    assert link.get("href") == reverse(f"{app}:historico")
    assert link.texto == "Histórico de importações"
    assert link.tem_classe("btn") and link.tem_classe("btn-secondary")


def _conteudo_invalido(app, csv_fixture, csv_fornecedores):
    if app == "catalogo":
        return csv_fixture("sem_coluna_obrigatoria.csv"), "NOMESUBGRUPO"
    return csv_fornecedores("sem_coluna_bloq.csv"), "BLOQ_OPCAO"


@pytest.mark.parametrize("motivo", ["sem-arquivo", "arquivo-invalido"])
@pytest.mark.parametrize("app", APPS)
def test_erro_de_arquivo_e_ligado_ao_campo_por_aria_describedby(
    chefe, csv_fixture, csv_fornecedores, app, motivo
):
    """O leitor de tela lê o erro ao focar o campo: o `aria-describedby` do input precisa apontar
    para um elemento que existe e carrega o próprio texto do erro."""
    if motivo == "sem-arquivo":
        resposta = chefe.client.post(reverse(f"{app}:importacao_envio"), {})
        esperado = None
    else:
        conteudo, esperado = _conteudo_invalido(app, csv_fixture, csv_fornecedores)
        resposta = _enviar(chefe.client, app, conteudo)

    assert resposta.status_code == 200
    documento = analisar(resposta.content)
    entrada = documento.unico("input", type="file", name="arquivo")
    ids_descritores = entrada.get("aria-describedby", "").split()
    assert ids_descritores, "o campo com erro precisa de aria-describedby"
    (erro,) = documento.buscar(classe="field-error")
    assert erro.get("id") in ids_descritores
    for id_descritor in ids_descritores:
        assert documento.unico(id=id_descritor)  # nenhum id pendurado
    assert erro.texto
    if esperado:
        assert esperado in erro.texto
    assert erro.esta_dentro_de("form") and documento.buscar(classe="error-box") == []
    campo = next(a for a in erro.ancestrais() if a.tem_classe("field"))
    assert campo.tem_classe("field-has-error")
    # O envio recusado não gera prévia: nada ficou pendente na sessão.
    assert documento.buscar(classe="alert-info") == []


@pytest.mark.parametrize("app", APPS)
def test_previa_pendente_aparece_como_aviso_informativo_com_link_para_continuar(
    chefe, csv_fixture, app
):
    sem_pendencia = _abrir_envio(chefe, app)
    assert sem_pendencia.buscar(classe="alert-info") == []
    if app == "catalogo":
        conteudo = csv_fixture("carga_inicial_valida.csv")
    else:
        conteudo = _arquivo_fornecedores(_linha_fornecedor("700001", "FORNECEDOR ALFA"))
    assert _enviar(chefe.client, app, conteudo, nome="pendente-9e2.csv").status_code == 302

    documento = _abrir_envio(chefe, app)

    (aviso,) = documento.buscar(classe="alert-info")
    assert aviso.get("role") == "status"
    assert aviso.unico("strong").texto == "pendente-9e2.csv"
    (link,) = aviso.buscar("a")
    assert link.get("href") == reverse(f"{app}:importacao_previa")
    assert link.texto == "Continuar para a prévia"
    assert "Enviar outro arquivo substitui a prévia pendente." in aviso.texto
    # O aviso vem antes do card do formulário.
    ordem = list(documento.unico("main").descendentes())
    assert ordem.index(aviso) < ordem.index(documento.unico(classe="card-form"))
    # A promessa do aviso é verdadeira: um novo envio válido troca a prévia pendente.
    assert _enviar(chefe.client, app, conteudo, nome="substituta-4b7.csv").status_code == 302
    assert _plano_e_pedido(chefe.client, app)[0].nome_arquivo == "substituta-4b7.csv"
    (aviso_novo,) = _abrir_envio(chefe, app).buscar(classe="alert-info")
    assert aviso_novo.unico("strong").texto == "substituta-4b7.csv"


# ---------------------------------------------------------------------------
# 3. Prévia: cabeçalho, aviso e resumo (comum às duas).
# ---------------------------------------------------------------------------


@_por_app(*APPS)
def test_previa_se_declara_nao_gravada_no_titulo_e_leva_de_volta_ao_envio(previa_com_rejeitados):
    documento = previa_com_rejeitados.documento
    app = previa_com_rejeitados.app

    (selo,) = documento.unico("h1").buscar(classe="badge")
    assert selo.texto == "Não gravada" and selo.tem_classe("badge-info")
    sub = documento.unico("main").unico(classe="sub")
    trilha = sub.unico("nav", aria_label="Trilha de navegação")
    (link,) = trilha.buscar("a")
    assert link.get("href") == reverse(f"{app}:importacao_envio")
    assert "Prévia" in trilha.texto  # o destino atual, sem link
    # A ação primária fica só na barra de confirmação: o `.tools` do cabeçalho fica vazio.
    ferramentas = documento.unico("main").unico(classe="tools")
    assert ferramentas.buscar("a") == [] and ferramentas.buscar("button") == []


@_por_app(*APPS)
def test_aviso_diz_que_nada_foi_gravado_e_nomeia_o_arquivo(previa_com_rejeitados):
    documento = previa_com_rejeitados.documento

    (aviso,) = documento.unico("main").buscar(classe="alert-info")
    assert aviso.get("role") == "status"
    assert "nada foi gravado ainda" in aviso.texto
    assert aviso.unico("strong").texto == "carga.csv"
    # O aviso abre a página: vem antes do resumo.
    ordem = list(documento.unico("main").descendentes())
    assert ordem.index(aviso) < ordem.index(documento.buscar(classe="tiles")[0])


def test_aviso_da_previa_de_fornecedores_cita_as_mudancas_de_situacao(
    previa_fornecedores_com_bloqueios,
):
    (aviso,) = previa_fornecedores_com_bloqueios.documento.unico("main").buscar(classe="alert-info")

    assert "as mudanças de situação" in aviso.texto


@pytest.mark.parametrize(
    "fixture, rotulos",
    [
        pytest.param(
            "previa_catalogo_com_rejeitados",
            ["Recebidos", "Serão inseridos", "Serão atualizados", "Rejeitados",
             "Ausentes do arquivo"],
            id="catalogo",
        ),
        pytest.param(
            "previa_fornecedores_com_bloqueios",
            ["Recebidos", "Serão inseridos", "Serão atualizados", "Rejeitados",
             "Passam a bloqueado", "Voltam a liberado", "Chegam bloqueados", "Ausentes do arquivo"],
            id="fornecedores",
        ),
    ],
)
def test_resumo_usa_rotulos_no_futuro_com_cada_total_ao_lado_do_seu_rotulo(
    request, fixture, rotulos
):
    previa = request.getfixturevalue(fixture)

    totais = _totais_da_previa(previa.documento)

    assert list(totais) == rotulos
    plano = previa.plano
    assert totais["Recebidos"] == str(plano.total_recebidos)
    assert totais["Serão inseridos"] == str(plano.total_inseridos)
    assert totais["Serão atualizados"] == str(plano.total_atualizados)
    assert totais["Rejeitados"] == str(plano.total_rejeitados)
    assert totais["Ausentes do arquivo"] == str(plano.total_ausentes_no_arquivo)
    # Os atualizados dizem em texto quantos têm alteração.
    assert _notas_do_tile(previa.documento, "Serão atualizados") == [
        f"{plano.total_atualizados_com_alteracao} com alteração"
    ]
    # Na prévia nada aconteceu ainda: nenhum rótulo no passado.
    assert not {"Inseridos", "Atualizados"} & set(totais)


@pytest.mark.parametrize(
    "previa_com_rejeitados, previa_limpa",
    [(app, app) for app in APPS],
    indirect=True,
    ids=APPS,
)
def test_rejeitados_em_destaque_com_atalho_para_as_excecoes_so_quando_ha_rejeitados(
    previa_com_rejeitados, previa_limpa
):
    com = previa_com_rejeitados.documento
    sem = previa_limpa.documento
    assert previa_com_rejeitados.plano.total_rejeitados > 0
    assert previa_limpa.plano.total_rejeitados == 0

    tile = _tile(com, "Rejeitados")
    assert tile.tem_classe("tile-warning")
    assert [(a.get("href"), a.texto) for a in tile.buscar("a")] == [("#excecoes", "ver exceções")]
    assert com.unico("section", id="excecoes")  # o atalho aponta para uma seção que existe
    # Sem rejeitados: nem destaque nem atalho, e o total "0" segue em texto.
    assert not _tile(sem, "Rejeitados").tem_classe("tile-warning")
    assert _tile(sem, "Rejeitados").buscar("a") == []
    assert _totais_da_previa(sem)["Rejeitados"] == "0"


@_por_app(*APPS)
def test_ausentes_ficam_fora_da_soma_e_nao_sao_destacados(previa_com_rejeitados):
    documento = previa_com_rejeitados.documento
    tile = _tile(documento, "Ausentes do arquivo")

    assert tile.tem_classe("tile-aside") and not tile.tem_classe("tile-warning")
    if previa_com_rejeitados.app == "catalogo":
        # Um só `dl`: o próprio tile diz em texto que fica fora da soma.
        assert _notas(tile) == ["fora da soma"]
    else:
        # Fornecedores: quem diz é o rótulo do grupo em que o tile está.
        assert _grupo_do_tile(documento, tile).unico(classe="tiles-grupo-rotulo").texto == (
            "Fora da soma"
        )


def _grupo_do_tile(documento, tile):
    (grupo,) = [a for a in tile.ancestrais() if a.tem_classe("tiles-grupo")]
    return grupo


def test_resumo_do_catalogo_e_um_unico_grupo_de_tiles_sem_rotulo_de_grupo(
    previa_catalogo_com_rejeitados,
):
    resumo = previa_catalogo_com_rejeitados.documento.unico(
        "section", aria_labelledby="resumo-titulo"
    )

    assert resumo.buscar(classe="tiles-grupo") == []
    assert len(resumo.buscar(classe="tiles")) == 1
    assert len(resumo.unico(classe="tiles").buscar(classe="tile")) == 5


@pytest.mark.parametrize(
    "fixture", ["previa_fornecedores_com_bloqueios", "previa_fornecedores_limpa"]
)
def test_resumo_de_fornecedores_tem_dois_grupos_nomeados_com_os_tiles_certos_em_cada_um(
    request, fixture
):
    documento = request.getfixturevalue(fixture).documento
    resumo = documento.unico("section", aria_labelledby="resumo-titulo")

    grupos = resumo.buscar(classe="tiles-grupo")

    assert len(grupos) == 2
    esperado = [
        ("Composição da carga",
         ["Recebidos", "Serão inseridos", "Serão atualizados", "Rejeitados"]),
        ("Fora da soma",
         ["Passam a bloqueado", "Voltam a liberado", "Chegam bloqueados", "Ausentes do arquivo"]),
    ]
    obtido = []
    for grupo in grupos:
        assert grupo.get("role") == "group"
        # O nome do grupo é o rótulo visível (um `<p>` dentro do próprio grupo), não texto oculto.
        rotulo = documento.unico(id=grupo.get("aria-labelledby"))
        assert rotulo.tag == "p" and rotulo.tem_classe("tiles-grupo-rotulo")
        assert rotulo.esta_dentro_de("div") and rotulo in grupo.descendentes()
        assert not rotulo.tem_classe("visually-hidden") and rotulo.get("aria-hidden") is None
        (lista,) = grupo.buscar("dl", classe="tiles")
        assert lista.tem_classe("grid") and lista.tem_classe("tiles-metricas")
        obtido.append(
            (rotulo.texto, [t.unico("dt", classe="k").texto for t in lista.buscar(classe="tile")])
        )
    assert obtido == esperado
    # Os dois grupos têm ids distintos e todos os tiles do resumo estão em algum grupo.
    assert len({g.get("aria-labelledby") for g in grupos}) == 2
    assert len(resumo.buscar(classe="tile")) == 8
    # O rótulo do grupo assume o "fora da soma": nenhum tile repete a nota.
    assert all("fora da soma" not in _notas(t) for t in resumo.buscar(classe="tile"))


@pytest.mark.parametrize(
    "fixture, entidade",
    [
        pytest.param("previa_catalogo_com_rejeitados", "materiais", id="catalogo"),
        pytest.param("previa_fornecedores_com_bloqueios", "fornecedores", id="fornecedores"),
    ],
)
def test_nota_garante_que_os_ausentes_nao_sao_alterados_nem_removidos(request, fixture, entidade):
    documento = request.getfixturevalue(fixture).documento
    resumo = documento.unico("section", aria_labelledby="resumo-titulo")

    notas = [p.texto for p in resumo.buscar("p", classe="text-note")]

    (nota,) = [n for n in notas if "não altera nem remove" in n]
    assert "já cadastrados no WMS que não vieram neste CSV" in nota and entidade in nota


# ---------------------------------------------------------------------------
# 4. Prévia do catálogo: divergências, exceções e CADPRO sem transformação.
# ---------------------------------------------------------------------------


def test_divergencias_do_catalogo_nao_alteram_saldo_e_mostram_o_cadpro_exato(
    previa_catalogo_limpa,
):
    documento = previa_catalogo_limpa.documento

    secao = documento.unico("section", id="divergencias")
    assert secao.get("data-secao") == "divergencias" and secao.tem_classe("card")
    assert secao.unico("h2").texto == "Divergências de saldo (1)"
    assert secao.get("aria-labelledby") == secao.unico("h2").get("id")
    nota = secao.unico("p", classe="text-note")
    assert "não altera o saldo do WMS" in nota.texto
    tabela = secao.unico("table")
    assert [th.texto for th in tabela.buscar("th")] == [
        "Código (CADPRO)", "Saldo no WMS", "Saldo no arquivo", "Diferença",
    ]
    (linha,) = tabela.unico("tbody").buscar("tr")
    # INV-CATALOG-001: CADPRO como lido (zeros e pontos), em célula própria; saldos 10 -> 15.
    assert _texto_das_celulas(linha) == ["010.020.031", "10", "15", "+5"]
    assert linha.unico("td", classe="table-cell-code").texto == "010.020.031"
    wrapper = secao.unico(classe="table-wrapper")
    assert (wrapper.get("role"), wrapper.get("aria-label"), wrapper.get("tabindex")) == (
        "region", "Tabela de divergências de saldo", "0",
    )


def test_previa_sem_divergencia_marca_a_secao_como_vazia_dentro_dela(
    previa_catalogo_com_rejeitados,
):
    secao = previa_catalogo_com_rejeitados.documento.unico("section", id="divergencias")

    assert secao.get("data-secao") == "divergencias"
    assert secao.buscar("table") == []
    assert secao.unico(classe="empty").get("data-estado") == "vazio"
    assert secao.unico("h2").texto == "Divergências de saldo (0)"


def test_previa_do_catalogo_nao_tem_secao_de_alteracoes(previa_catalogo_com_rejeitados):
    """Alterações cadastrais do catálogo só existem no resultado da execução, não na prévia."""
    assert previa_catalogo_com_rejeitados.documento.buscar(id="alteracoes") == []


def test_excecoes_do_catalogo_mostram_cadpro_como_lido_e_motivo_com_detalhe_numa_celula(
    previa_catalogo_com_rejeitados,
):
    previa = previa_catalogo_com_rejeitados
    secao = previa.documento.unico("section", id="excecoes")

    assert secao.get("aria-labelledby") == secao.unico("h2").get("id")
    assert secao.unico("h2").texto == f"Exceções ({previa.plano.total_rejeitados})"
    tabela = secao.unico("table")
    assert [th.texto for th in tabela.buscar("th")] == [
        "Linha", "Código (CADPRO)", "Motivo / detalhe",
    ]
    linhas = tabela.unico("tbody").buscar("tr")
    assert len(linhas) == previa.plano.total_rejeitados
    for linha, recusa in zip(linhas, previa.plano.recusas, strict=True):
        celulas = linha.buscar("td")
        assert len(celulas) == 3
        # INV-CATALOG-001: a recusa exibe o CADPRO como veio no arquivo; sem CADPRO, um travessão.
        assert celulas[1].texto == (recusa.cadpro or "—")
        assert celulas[2].texto.startswith(MotivoRecusa(recusa.motivo).label)
        # O detalhe, quando existe, é a linha secundária da mesma célula do motivo.
        secundarias = celulas[2].buscar(classe="cell-secondary")
        assert bool(secundarias) == bool(recusa.detalhe)
    assert any(recusa.cadpro for recusa in previa.plano.recusas), "pré-condição da fixture"
    assert previa.documento.buscar(classe="table-row-error") == []
    wrapper = secao.unico(classe="table-wrapper")
    assert (wrapper.get("role"), wrapper.get("aria-label"), wrapper.get("tabindex")) == (
        "region", "Tabela de exceções", "0",
    )


# ---------------------------------------------------------------------------
# 5. Prévia de fornecedores: bloqueio em destaque (INV-SUPPLIER-005) e alterações.
# ---------------------------------------------------------------------------


def test_previa_de_fornecedores_destaca_quem_passa_a_bloquear_e_quem_chega_bloqueado(
    previa_fornecedores_com_bloqueios,
):
    documento = previa_fornecedores_com_bloqueios.documento

    totais = _totais_da_previa(documento)
    situacao = ("Passam a bloqueado", "Voltam a liberado", "Chegam bloqueados")
    assert [totais[rotulo] for rotulo in situacao] == ["1", "1", "1"]
    passam = _tile(documento, "Passam a bloqueado")
    chegam = _tile(documento, "Chegam bloqueados")
    voltam = _tile(documento, "Voltam a liberado")
    assert passam.tem_classe("tile-warning") and chegam.tem_classe("tile-warning")
    # Desbloquear não tem risco: nunca é de atenção.
    assert not voltam.tem_classe("tile-warning")
    # Os três ficam fora da soma: no grupo "Fora da soma" (dito em texto, não só pela borda).
    for tile in (passam, voltam, chegam):
        assert tile.tem_classe("tile-aside")
        assert _grupo_do_tile(documento, tile).unico(classe="tiles-grupo-rotulo").texto == (
            "Fora da soma"
        )
    # O atalho existe só em "Passam a bloqueado" (os que chegam bloqueados são inserções: não
    # aparecem em Alterações) e aponta para a seção, que existe.
    assert [(a.get("href"), a.texto) for a in passam.buscar("a")] == [
        ("#alteracoes", "ver alterações")
    ]
    assert chegam.buscar("a") == [] and voltam.buscar("a") == []
    assert documento.unico("section", id="alteracoes")


def test_previa_de_fornecedores_sem_bloqueios_mantem_os_totais_zerados_neutros(
    previa_fornecedores_limpa,
):
    documento = previa_fornecedores_limpa.documento

    assert documento.buscar(classe="tile-warning") == []
    for rotulo in ("Passam a bloqueado", "Voltam a liberado", "Chegam bloqueados"):
        tile = _tile(documento, rotulo)
        assert tile.unico("dd", classe="v").texto == "0"  # o zero continua em texto
        assert tile.tem_classe("fornecedores-situacao-neutra")
        assert tile.buscar("a") == []
        assert _grupo_do_tile(documento, tile).unico(classe="tiles-grupo-rotulo").texto == (
            "Fora da soma"
        )
    assert not _tile(documento, "Ausentes do arquivo").tem_classe("fornecedores-situacao-neutra")


@pytest.mark.parametrize(
    "fixture", ["previa_fornecedores_com_bloqueios", "previa_fornecedores_limpa"]
)
def test_nota_de_que_bloqueado_nao_emite_entrada_aparece_sempre_na_previa(request, fixture):
    resumo = request.getfixturevalue(fixture).documento.unico(
        "section", aria_labelledby="resumo-titulo"
    )

    notas = [p.texto for p in resumo.buscar("p", classe="text-note")]

    (nota,) = [n for n in notas if "não pode ser emitente de uma entrada" in n]
    assert "Um fornecedor bloqueado não pode ser emitente de uma entrada de materiais" in nota


def test_nota_explica_que_quem_chega_bloqueado_nao_aparece_nas_tabelas_e_isso_e_verdade(
    previa_fornecedores_com_bloqueios,
):
    """A nota promete: os que chegam bloqueados são fornecedores novos e não aparecem nas tabelas
    da prévia. Se um deles passasse a aparecer (ou a nota sumisse), o chefe leria o resumo errado
    antes de confirmar (INV-SUPPLIER-005)."""
    documento = previa_fornecedores_com_bloqueios.documento
    resumo = documento.unico("section", aria_labelledby="resumo-titulo")

    notas = [p.texto for p in resumo.buscar("p", classe="text-note")]

    (nota,) = [n for n in notas if "chegam bloqueados" in n]
    assert "fornecedores novos" in nota and "não aparecem nas tabelas" in nota
    assert 'em "Alterações cadastrais"' in nota
    # O fornecedor que chega bloqueado (000777) está no tile, mas em nenhuma tabela.
    assert _tile(documento, "Chegam bloqueados").unico("dd", classe="v").texto == "1"
    codigos = [c.texto for c in documento.unico("main").buscar(classe="table-cell-code")]
    assert codigos and "000777" not in codigos


def test_alteracoes_de_fornecedores_contam_campos_e_fornecedores_e_agrupam_por_codif(
    previa_fornecedores_com_bloqueios,
):
    previa = previa_fornecedores_com_bloqueios
    secao = previa.documento.unico("section", id="alteracoes")

    assert secao.get("data-secao") == "alteracoes"
    assert secao.get("aria-labelledby") == secao.unico("h2").get("id")
    tabela = secao.unico("table")
    linhas = tabela.unico("tbody").buscar("tr")
    # 700001: nome e tipo; 700002 e 700003: situação + motivo + tipo do bloqueio; 000123: nome.
    assert previa.plano.total_atualizados_com_alteracao == 4
    campos = sum(len(a.alteracoes) for a in previa.plano.atualizacoes)
    assert len(linhas) == campos == 9
    assert secao.unico("h2").texto == "Alterações cadastrais — 9 campos em 4 fornecedores"
    wrapper = secao.unico(classe="table-wrapper")
    assert (wrapper.get("role"), wrapper.get("aria-label"), wrapper.get("tabindex")) == (
        "region", "Tabela de alterações cadastrais", "0",
    )

    # A coluna é "Nome", não "Nome atual": o nome vem do arquivo sendo confirmado.
    cabecalhos = tabela.buscar("th")
    assert cabecalhos[0].texto == "Código (CODIF) / Nome"
    assert all(th.get("scope") == "col" for th in cabecalhos)

    codigos = [linha.buscar("td")[0].unico(classe="table-cell-code") for linha in linhas]
    # INV-CATALOG-001/INV-SUPPLIER: o CODIF segue exato, com zeros à esquerda.
    assert sorted(c.texto for c in codigos) == sorted(
        ["000123"] + ["700001"] * 2 + ["700002"] * 3 + ["700003"] * 3
    )
    # `{% ifchanged %}`: código e nome só na primeira linha de uma sequência do mesmo CODIF; as
    # seguintes mantêm o CODIF no DOM (leitor de tela), mas oculto. O nome exibido é o do
    # arquivo (revisado), não o do cadastro atual.
    nomes_do_arquivo = {
        "700001": "FORNECEDOR ALFA REVISADO",
        "700002": "FORNECEDOR BETA",
        "700003": "FORNECEDOR GAMA",
        "000123": "FORNECEDOR ZEROS REVISADO",
    }
    anterior = None
    repeticoes = 0
    for linha, codigo in zip(linhas, codigos, strict=True):
        secundarias = linha.buscar(classe="cell-secondary")
        if codigo.texto == anterior:
            repeticoes += 1
            assert codigo.tem_classe("visually-hidden") and secundarias == []
        else:
            assert not codigo.tem_classe("visually-hidden")
            (nome,) = secundarias
            assert nome.texto == nomes_do_arquivo[codigo.texto]
        anterior = codigo.texto
    assert repeticoes >= 2, "pré-condição: o cenário tem sequências do mesmo CODIF"


def test_so_o_valor_novo_da_mudanca_de_situacao_ganha_o_selo_bloqueado(
    previa_fornecedores_com_bloqueios,
):
    secao = previa_fornecedores_com_bloqueios.documento.unico("section", id="alteracoes")
    tabela = secao.unico("table")
    linhas = {}
    for linha in tabela.unico("tbody").buscar("tr"):
        codigo = linha.unico(classe="table-cell-code").texto
        linhas.setdefault(codigo, []).append(linha)

    def campo(codigo, rotulo):
        (linha,) = [i for i in linhas[codigo] if i.buscar("td")[1].texto == rotulo]
        return linha

    celulas = campo("700002", "Situação").buscar("td")
    (selo,) = celulas[3].buscar(classe="badge")
    assert selo.texto == "Bloqueado" and selo.tem_classe("badge-warning")
    # Só o campo de situação ganha o selo: o motivo e o tipo do bloqueio são texto comum.
    for rotulo in ("Motivo do bloqueio", "Tipo de bloqueio"):
        assert campo("700002", rotulo).buscar(classe="badge") == []
    # Quem volta a liberado não ganha selo; mudar nome ou tipo também não.
    assert campo("700003", "Situação").buscar(classe="badge") == []
    for linha in linhas["700001"] + linhas["000123"]:
        assert linha.buscar(classe="badge") == []
    # A linha inteira nunca é marcada.
    assert not any(
        linha.tem_classe("table-row-error") for grupo in linhas.values() for linha in grupo
    )


def test_alteracoes_sem_nenhuma_mantem_a_secao_marcada_com_titulo_zerado_e_vazio(
    previa_fornecedores_limpa,
):
    secao = previa_fornecedores_limpa.documento.unico("section", id="alteracoes")

    assert secao.get("data-secao") == "alteracoes"
    assert secao.unico("h2").texto == "Alterações cadastrais (0)"
    assert secao.buscar("table") == []
    assert "Nenhuma alteração cadastral" in secao.unico(classe="empty").texto


def test_excecoes_de_fornecedores_mostram_codif_como_lido_e_motivo_sem_fundo_de_erro(
    previa_fornecedores_com_bloqueios,
):
    from fornecedores.models import MotivoRecusaFornecedor

    documento = previa_fornecedores_com_bloqueios.documento
    secao = documento.unico("section", id="excecoes")

    assert secao.unico("h2").texto == "Exceções (1)"
    tabela = secao.unico("table")
    assert [th.texto for th in tabela.buscar("th")] == [
        "Linha", "Código (CODIF)", "Motivo / detalhe",
    ]
    (linha,) = tabela.unico("tbody").buscar("tr")
    celulas = linha.buscar("td")
    assert len(celulas) == 3
    assert celulas[1].texto == "000789"  # zeros à esquerda preservados
    assert celulas[2].texto.startswith(MotivoRecusaFornecedor.SITUACAO_BLOQUEIO_INVALIDA.label)
    assert documento.buscar(classe="table-row-error") == []
    wrapper = secao.unico(classe="table-wrapper")
    assert (wrapper.get("role"), wrapper.get("aria-label"), wrapper.get("tabindex")) == (
        "region", "Tabela de exceções", "0",
    )


def test_previa_de_fornecedores_sem_rejeitados_diz_em_texto_que_nao_ha_excecoes(
    previa_fornecedores_limpa,
):
    secao = previa_fornecedores_limpa.documento.unico("section", id="excecoes")

    assert secao.unico("h2").texto == "Exceções (0)"
    assert secao.buscar("table") == []
    assert "Nenhuma exceção nesta importação." in secao.unico(classe="empty").texto


# ---------------------------------------------------------------------------
# 6. Barra de confirmação: a ação irreversível da prévia.
# ---------------------------------------------------------------------------


def _barra(previa):
    principal = previa.documento.unico("main")
    barra = principal.filhos[-1]
    return principal, barra


@_por_app(*APPS)
def test_confirmar_e_cancelar_sao_um_unico_form_cada_na_pagina(previa_com_rejeitados):
    previa = previa_com_rejeitados
    app = previa.app

    for rota in ("importacao_confirmar", "importacao_cancelar"):
        acao = reverse(f"{app}:{rota}")
        assert len(previa.documento.buscar("form", action=acao)) == 1, rota
        assert previa.conteudo.count(f'action="{acao}"') == 1, rota
    # Não há nenhum outro form de escrita na página além desses dois.
    assert len(previa.documento.unico("main").buscar("form")) == 2


@_por_app(*APPS)
def test_barra_de_confirmacao_e_o_ultimo_elemento_da_pagina_com_confirmar_antes_de_cancelar(
    previa_com_rejeitados,
):
    previa = previa_com_rejeitados
    principal, barra = _barra(previa)

    assert barra.tag == "div"
    assert barra.tem_classe("confirmation-bar") and barra.tem_classe("confirmation-bar-card")
    formularios = barra.buscar("form")
    assert [f.get("action") for f in formularios] == [
        reverse(f"{previa.app}:importacao_confirmar"),
        reverse(f"{previa.app}:importacao_cancelar"),
    ]
    # Nenhuma seção de conteúdo vem depois da barra, e as seções vêm antes dela.
    assert all(
        secao is not barra and secao in principal.filhos[: principal.filhos.index(barra)]
        for secao in principal.buscar("section") if secao.pai is principal
    )
    # Primário (confirmar) e secundário (cancelar).
    assert formularios[0].unico("button").tem_classe("btn-primary")
    assert formularios[1].unico("button").tem_classe("btn-secondary")
    assert formularios[1].unico("button").texto == "Cancelar"


@_por_app(*APPS)
def test_form_de_confirmar_leva_token_impressao_digital_csrf_e_ganchos_de_processamento(
    previa_com_rejeitados,
):
    previa = previa_com_rejeitados
    _, barra = _barra(previa)
    confirmar, cancelar = barra.buscar("form")

    assert confirmar.get("method") == "post"
    assert confirmar.unico("input", type="hidden", name="token").get("value") == previa.pedido.token
    assert (
        confirmar.unico("input", type="hidden", name="impressao_digital").get("value")
        == previa.plano.impressao_digital
    )
    assert confirmar.unico("input", type="hidden", name="csrfmiddlewaretoken").get("value")
    assert "data-processing-form" in confirmar.attrs
    assert confirmar.get("data-processing-label") == "Confirmando…"
    botao = confirmar.unico("button", type="submit")
    assert "data-processing-submit" in botao.attrs
    assert botao.unico("span").get("data-processing-submit-label") == ""
    # O cancelamento é um POST com CSRF próprio e não passa pelo estado "Confirmando…".
    assert cancelar.get("method") == "post"
    assert cancelar.unico("input", type="hidden", name="csrfmiddlewaretoken").get("value")
    assert "data-processing-form" not in cancelar.attrs
    assert cancelar.buscar("input", name="token") == []


@pytest.mark.parametrize("app", APPS)
def test_falha_inesperada_na_confirmacao_mostra_o_erro_uma_unica_vez_e_mantem_a_barra(
    chefe, csv_fixture, app
):
    """A prévia re-renderizada (200, no próprio POST) mostra a mensagem de erro só pelo
    `base.html` (as telas não incluem mais `_mensagens.html`) e segue com o par confirmar/cancelar,
    para uma nova tentativa."""
    from importlib import import_module
    from unittest import mock

    importacao = import_module(f"{app}.importacao")
    if app == "catalogo":
        conteudo = csv_fixture("carga_inicial_valida.csv")
    else:
        conteudo = _arquivo_fornecedores(_linha_fornecedor("700001", "FORNECEDOR ALFA"))
    previa = _abrir_previa(chefe, app, conteudo)

    with mock.patch.object(importacao, "aplicar_plano", side_effect=RuntimeError("falha injetada")):
        resposta = chefe.client.post(
            reverse(f"{app}:importacao_confirmar"),
            {"token": previa.pedido.token, "impressao_digital": previa.plano.impressao_digital},
        )

    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert html.count("erro inesperado") == 1
    documento = analisar(resposta.content)
    principal = documento.unico("main")
    (container,) = documento.buscar(classe="messages")
    assert container.pai is principal
    (erro,) = container.buscar(classe="error-box")
    assert erro.get("role") == "alert" and "erro inesperado" in erro.texto
    assert "falha injetada" not in html
    # A prévia segue completa e confirmável.
    assert principal.unico("h1").buscar(classe="badge")[0].texto == "Não gravada"
    ultimo = principal.filhos[-1]
    assert ultimo.tem_classe("confirmation-bar")
    assert [f.get("action") for f in ultimo.buscar("form")] == [
        reverse(f"{app}:importacao_confirmar"),
        reverse(f"{app}:importacao_cancelar"),
    ]
    assert len(documento.buscar("form", action=reverse(f"{app}:importacao_confirmar"))) == 1


def _rotulo(previa):
    """O `textContent` do rótulo do botão Confirmar (o que o nome acessível lê)."""
    _, barra = _barra(previa)
    return barra.unico("button", classe="btn-primary").unico("span").texto_corrido


def test_rotulo_de_confirmar_do_catalogo_pluraliza_e_avisa_dos_rejeitados(
    previa_catalogo_com_rejeitados, previa_catalogo_limpa
):
    # 9 inseridos, 0 atualizados, 13 rejeitados (README de tests/fixtures/catalogo/).
    assert _rotulo(previa_catalogo_com_rejeitados) == (
        "Confirmar importação: 9 inseridos, 0 atualizados (13 rejeitados ficam de fora)"
    )
    # 1 inserido (singular), 8 atualizados, sem a cláusula dos rejeitados.
    assert _rotulo(previa_catalogo_limpa) == "Confirmar importação: 1 inserido, 8 atualizados"


def test_rotulo_de_confirmar_de_fornecedores_traz_os_sufixos_de_bloqueio(
    previa_fornecedores_com_bloqueios, previa_fornecedores_limpa
):
    # Todos no singular: 1 inserido (000777), 4 atualizados (os 4 existentes que vieram), 1
    # rejeitado, 1 passa a bloqueado, 1 volta a liberado, 1 chega bloqueado.
    plano = previa_fornecedores_com_bloqueios.plano
    assert (plano.total_inseridos, plano.total_atualizados, plano.total_rejeitados) == (1, 4, 1)
    assert _rotulo(previa_fornecedores_com_bloqueios) == (
        "Confirmar importação: 1 inserido, 4 atualizados (1 rejeitado fica de fora), "
        "1 passa a bloqueado, 1 volta a liberado, 1 chega bloqueado"
    )
    # Sem nenhuma situação mudando, os sufixos somem.
    assert _rotulo(previa_fornecedores_limpa) == "Confirmar importação: 0 inseridos, 5 atualizados"


def test_rotulo_de_confirmar_de_fornecedores_vai_ao_plural_em_todos_os_sufixos(
    previa_fornecedores_plural,
):
    plano = previa_fornecedores_plural.plano
    assert (plano.total_inseridos, plano.total_atualizados, plano.total_rejeitados) == (2, 5, 2)

    assert _rotulo(previa_fornecedores_plural) == (
        "Confirmar importação: 2 inseridos, 5 atualizados (2 rejeitados ficam de fora), "
        "2 passam a bloqueado, 2 voltam a liberado, 2 chegam bloqueados"
    )


PREVIAS_DA_BARRA = [
    "previa_catalogo_com_rejeitados",
    "previa_catalogo_limpa",
    "previa_fornecedores_com_bloqueios",
    "previa_fornecedores_plural",
    "previa_fornecedores_limpa",
]


@pytest.mark.parametrize("fixture", PREVIAS_DA_BARRA)
def test_botao_confirmar_separa_a_acao_dos_totais_sem_perder_o_nome_acessivel(request, fixture):
    """Até 480px só "Confirmar importação" aparece; os totais ficam num `<small>` ocultado só
    visualmente. O nome acessível (conteúdo do botão) continua o rótulo longo inteiro: nada no
    caminho pode ficar `aria-hidden`/`hidden` nem ser sobrescrito por `aria-label`."""
    previa = request.getfixturevalue(fixture)
    _, barra = _barra(previa)
    botao = barra.unico("button", classe="btn-primary")
    rotulo = botao.unico("span")
    (totais,) = rotulo.buscar("small", classe="confirmation-bar-totais")

    assert rotulo.get("data-processing-submit-label") == ""
    assert totais.texto_corrido.startswith(": ")
    # `Confirmar importação` + `: totais` é o rótulo longo, sem espaço antes dos dois pontos.
    assert rotulo.texto_corrido == "Confirmar importação" + totais.texto_corrido
    assert botao.texto_corrido == rotulo.texto_corrido
    for no in (botao, rotulo, totais, *botao.ancestrais()):
        if no.tag == "[documento]":
            continue
        assert "aria-hidden" not in no.attrs and "hidden" not in no.attrs, no.tag
    assert "aria-label" not in botao.attrs and "aria-labelledby" not in botao.attrs


NBSP = "\xa0"

# Resumo telegráfico da barra (só ≤480px, `aria-hidden`): itens separados por " · ", número e
# palavra (e "a bloquear"/"chegam bloqueados") ligados por espaço não separável, e os itens
# opcionais só quando o total é maior que zero.
RESUMOS_DA_BARRA = {
    "previa_catalogo_com_rejeitados": "9 inseridos · 0 atualizados · 13 rejeitados",
    "previa_catalogo_limpa": "1 inserido · 8 atualizados",
    "previa_fornecedores_com_bloqueios": (
        "1 inserido · 4 atualizados · 1 rejeitado · 1 a bloquear · 1 a liberar "
        "· 1 chega bloqueado"
    ),
    "previa_fornecedores_plural": (
        "2 inseridos · 5 atualizados · 2 rejeitados · 2 a bloquear · 2 a liberar "
        "· 2 chegam bloqueados"
    ),
    "previa_fornecedores_limpa": "0 inseridos · 5 atualizados",
}


def _resumo_da_barra(previa):
    _, barra = _barra(previa)
    resumo = barra.filhos[0]
    assert resumo.tag == "p" and resumo.tem_classe("confirmation-bar-resumo")
    return barra, resumo


@pytest.mark.parametrize("fixture", RESUMOS_DA_BARRA)
def test_resumo_telegrafico_da_barra_pluraliza_e_omite_os_itens_zerados(request, fixture):
    previa = request.getfixturevalue(fixture)
    _, resumo = _resumo_da_barra(previa)

    # Só o separador entre número e palavra é não separável; a pontuação " · " é espaço comum.
    esperado = RESUMOS_DA_BARRA[fixture]
    itens = [item.replace(" ", NBSP) for item in esperado.split(" · ")]
    assert resumo.texto_cru.strip() == " · ".join(itens)


@pytest.mark.parametrize("fixture", RESUMOS_DA_BARRA)
def test_resumo_da_barra_nao_quebra_linha_entre_o_numero_e_a_palavra(request, fixture):
    """Na tela estreita a linha quebra entre itens, nunca no meio de "9 inseridos" ou de
    "1 a bloquear": todo espaço dentro de um item é `&nbsp;`."""
    previa = request.getfixturevalue(fixture)
    _, resumo = _resumo_da_barra(previa)

    texto = resumo.texto_cru.strip()
    itens = texto.split(" · ")
    assert len(itens) >= 2
    for item in itens:
        assert " " not in item, f"espaço comum dentro do item {item!r}"
        assert NBSP in item and item.split(NBSP)[0].isdigit()
    # E o `texto_corrido` (que colapsa `\xa0`) leria o mesmo conteúdo com espaços comuns.
    assert resumo.texto_corrido == texto.replace(NBSP, " ")


@pytest.mark.parametrize("fixture", RESUMOS_DA_BARRA)
def test_resumo_da_barra_fica_fora_da_arvore_de_acessibilidade_e_antes_dos_formularios(
    request, fixture
):
    import re

    previa = request.getfixturevalue(fixture)
    barra, resumo = _resumo_da_barra(previa)

    assert resumo.get("aria-hidden") == "true"
    assert resumo.pai is barra and not resumo.buscar("a") and not resumo.buscar("button")
    assert len(barra.buscar(classe="confirmation-bar-resumo")) == 1
    assert barra.filhos.index(resumo) == 0
    # Os números são os do botão: a pluralização vive em duas cópias no template e os totais
    # opcionais (rejeitados, situação) só aparecem em ambas quando maiores que zero. Se uma delas
    # divergir, quem lê a tela estreita confirma números diferentes dos do rótulo do botão.
    (totais,) = barra.buscar("small", classe="confirmation-bar-totais")
    assert re.findall(r"\d+", resumo.texto_cru) == re.findall(r"\d+", totais.texto_cru)
