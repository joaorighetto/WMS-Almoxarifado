"""Garantia mínima do leitor de HTML dos testes de markup (`tests/html_helpers.py`).

Os testes de shell, navegação e Home dependem dele para afirmar "exatamente um", "dentro de" e
"antes de". Se o leitor errasse a árvore (tags void, scripts, atributos booleanos, ordem), esses
testes poderiam passar sem proteger nada; aqui ficam as propriedades de que dependem.
"""

import pytest

from tests.html_helpers import analisar, hrefs_de, secao_por_rotulo, totais_do_resumo

HTML = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<script>var a = "<b>não é tag</b>"; try { x() } catch (e) {}</script>
<link rel="stylesheet" href="/a.css">
<script src="/js/shell.js" defer></script>
</head>
<body>
<aside class="side brand-x"><nav aria-label="Seções">
  <a href="/">Início</a><h3>Grupo</h3>
  <a href="/x/" aria-current="page">Item   <b>x</b></a>
  <img src="/i.png"><br>
</nav><form method="POST" action="/logout/"><input type="hidden" name="t" value="v"/></form></aside>
<main id="main"><section aria-labelledby="s1"><h2 id="s1">T</h2><a href="/y/">y</a></section></main>
</body></html>"""


@pytest.fixture
def documento():
    return analisar(HTML)


def test_tags_void_e_autofechadas_nao_engolem_os_irmaos(documento):
    nav = documento.unico("nav", aria_label="Seções")
    assert [no.tag for no in nav.filhos] == ["a", "h3", "a", "img", "br"]
    # O formulário depois da nav continua irmão dela, dentro do aside.
    assert documento.unico("form").pai is documento.unico("aside")
    assert documento.unico("main").pai is documento.unico("body")


def test_script_inline_e_um_unico_no_de_texto_sem_virar_marcacao(documento):
    cabeca = documento.unico("head")
    inline = [s for s in cabeca.buscar("script") if "src" not in s.attrs]
    assert len(inline) == 1
    assert "catch" in inline[0].texto
    assert inline[0].buscar("b") == []


def test_ordem_de_documento_permite_comparar_posicoes(documento):
    ordem = list(documento.unico("head").descendentes())
    script = documento.buscar("script")[0]
    folha = documento.unico("link")
    assert ordem.index(script) < ordem.index(folha)


def test_atributos_classes_e_presenca(documento):
    assert documento.unico("aside").tem_classe("side")
    assert documento.unico("aside").tem_classe("brand-x")
    assert not documento.unico("aside").tem_classe("brand")
    assert len(documento.buscar("a", aria_current=True)) == 1
    assert documento.unico("script", src="/js/shell.js").attrs["defer"] == ""
    assert documento.unico("form").get("method").lower() == "post"


def test_texto_colapsa_espacos_e_inclui_descendentes(documento):
    assert documento.unico("a", href="/x/").texto == "Item x"


def test_unico_falha_com_zero_ou_mais_de_um(documento):
    with pytest.raises(AssertionError):
        documento.unico("a")
    with pytest.raises(AssertionError):
        documento.unico("table")


def test_totais_do_resumo_associa_cada_rotulo_ao_seu_valor():
    resumo = analisar(
        '<dl class="grid tiles">'
        '<div class="tile"><dt class="k">Inseridos</dt><dd class="v">9</dd></div>'
        '<div class="tile tile-warning"><dt class="k">Rejeitados</dt><dd class="v">1.234</dd>'
        '<dd class="d">fora da soma</dd></div></dl>'
    )

    assert totais_do_resumo(resumo) == {"Inseridos": "9", "Rejeitados": "1.234"}


def test_hrefs_e_secao_por_rotulo(documento):
    assert hrefs_de(documento.unico("nav")) == {"/", "/x/"}
    assert hrefs_de(secao_por_rotulo(documento, "s1")) == {"/y/"}
