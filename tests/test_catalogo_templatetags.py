"""Testes das template tags de `interface/templatetags/interface_extras.py`
(FR-042a, FR-042b — emenda de 2026-09-22, `spec.md`, Clarifications; e a
revisão do gate visual de 2026-09-22 sobre a mesma superfície: total/plural
do resumo, ordem em texto, lista compacta de paginação).

Movidas de `catalogo/templatetags/catalogo_extras.py` para `interface`
(consolidação de UX, Fase A) — mesmo comportamento, import atualizado.

Unitários: exercitam as funções das tags diretamente, sem view nem
renderização de template — o contrato de marcação (`_paginacao.html` e o
cabeçalho ordenável da consulta) é coberto por `tests/test_catalogo_consulta.py`
e é responsabilidade do `frontend-implementer`.

`querystring_pagina` ganhou um teste direto (`test-engineer`, alinhamento de
UX, Fase B): a consolidação (Fase A) passou a compartilhar `_paginacao.html`
entre `catalogo`, `fornecedores` e `estoque`, e páginas com mais de uma seção
paginada (`catalogo/fornecedores execucao_detalhe.html`, com
`pagina_excecoes`/`pagina_divergencias`/`pagina_alteracoes`) dependem desta
tag para não zerar as demais seções ao avançar uma delas (revisão T051,
achado P3) — vale travar o contrato na própria tag, não só via integração.
"""

import re
from decimal import Decimal

import pytest
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.test import RequestFactory

from interface.templatetags.interface_extras import (
    intervalo_paginas,
    quantidade,
    querystring_ordenacao,
    querystring_pagina,
    rotulo_ordenacao,
    separador_milhar,
    truncar_meio,
)

_rf = RequestFactory()


def _contexto(get_params, ordem=""):
    """Contexto mínimo aceito por uma tag `takes_context=True`: um dict com
    `request` (GET com os parâmetros dados) e `ordem` (a ordem efetiva já
    resolvida pela view, como `ConsultaCatalogoView` a expõe)."""
    request = _rf.get("/catalogo/", get_params)
    return {"request": request, "ordem": ordem}


# ---------------------------------------------------------------------------
# querystring_pagina (revisão T051, achado P3; contrato reforçado pela
# consolidação de UX, Fase A — `interface/_paginacao.html` compartilhado)
# ---------------------------------------------------------------------------


def test_querystring_pagina_substitui_so_o_proprio_parametro():
    request = _rf.get("/qualquer/", {"pagina": "1"})
    contexto = {"request": request}

    href = querystring_pagina(contexto, "pagina", 3)

    assert "pagina=3" in href
    assert "pagina=1" not in href


def test_querystring_pagina_preserva_parametros_de_outras_secoes_paginadas():
    """Uma página com mais de uma seção paginada (ex.
    `execucao_detalhe.html`, com `pagina_excecoes`/`pagina_divergencias`/
    `pagina_alteracoes`) não pode zerar as demais ao avançar uma delas."""
    request = _rf.get(
        "/qualquer/",
        {"pagina_excecoes": "1", "pagina_divergencias": "2", "pagina_alteracoes": "4"},
    )
    contexto = {"request": request}

    href = querystring_pagina(contexto, "pagina_excecoes", 3)

    assert "pagina_excecoes=3" in href
    assert "pagina_divergencias=2" in href
    assert "pagina_alteracoes=4" in href


def test_querystring_pagina_preserva_filtros_de_busca():
    request = _rf.get("/qualquer/", {"codigo": "000.000.001", "descricao": "parafuso"})
    contexto = {"request": request}

    href = querystring_pagina(contexto, "pagina", 2)

    assert "codigo=000.000.001" in href
    assert "descricao=parafuso" in href
    assert "pagina=2" in href


# ---------------------------------------------------------------------------
# querystring_ordenacao (FR-042a)
# ---------------------------------------------------------------------------


def test_querystring_ordenacao_alterna_para_decrescente_quando_coluna_ja_e_a_ordem_atual():
    contexto = _contexto({}, ordem="saldo")

    href = querystring_ordenacao(contexto, "saldo")

    assert "ordem=-saldo" in href


def test_querystring_ordenacao_volta_a_crescente_quando_coluna_ja_esta_decrescente():
    contexto = _contexto({}, ordem="-saldo")

    href = querystring_ordenacao(contexto, "saldo")

    assert "ordem=saldo" in href
    assert "ordem=-saldo" not in href


def test_querystring_ordenacao_usa_crescente_para_coluna_diferente_da_atual():
    """Trocar de coluna sempre começa crescente, mesmo que a coluna anterior
    estivesse decrescente."""
    contexto = _contexto({}, ordem="-saldo")

    href = querystring_ordenacao(contexto, "descricao")

    assert "ordem=descricao" in href
    assert "ordem=-saldo" not in href


def test_querystring_ordenacao_preserva_filtros_existentes():
    contexto = _contexto({"codigo": "000.000.001", "descricao": "parafuso"}, ordem="cadpro")

    href = querystring_ordenacao(contexto, "saldo")

    assert "codigo=000.000.001" in href
    assert "descricao=parafuso" in href
    assert "ordem=saldo" in href


def test_querystring_ordenacao_remove_o_parametro_pagina():
    """Mudar a ordem volta à primeira página (FR-042a)."""
    contexto = _contexto({"pagina": "3"}, ordem="cadpro")

    href = querystring_ordenacao(contexto, "saldo")

    assert "pagina=" not in href


def test_querystring_ordenacao_sem_pagina_na_querystring_nao_quebra():
    contexto = _contexto({}, ordem="cadpro")

    href = querystring_ordenacao(contexto, "saldo")

    assert href.startswith("?")
    assert "ordem=saldo" in href


# ---------------------------------------------------------------------------
# intervalo_paginas (FR-042b)
# ---------------------------------------------------------------------------


def _pagina(numero_total_itens, por_pagina, numero_pagina):
    paginador = Paginator(range(numero_total_itens), por_pagina)
    return paginador.get_page(numero_pagina)


def test_intervalo_paginas_sem_reticencia_quando_poucas_paginas():
    pagina = _pagina(numero_total_itens=30, por_pagina=10, numero_pagina=1)  # 3 páginas

    itens = intervalo_paginas(pagina)

    assert [item["reticencia"] for item in itens] == [False, False, False]
    assert [item["numero"] for item in itens] == [1, 2, 3]


def test_intervalo_paginas_com_reticencia_quando_muitas_paginas():
    """30 páginas, na 15ª: `on_each_side=2`/`on_ends=1` mantém a 1ª, a 30ª e
    as páginas 13–17 diretamente acessíveis, com reticência preenchendo os
    dois intervalos distantes."""
    pagina = _pagina(numero_total_itens=30, por_pagina=1, numero_pagina=15)

    itens = intervalo_paginas(pagina)

    assert itens[0] == {"numero": 1, "reticencia": False}
    assert itens[-1] == {"numero": 30, "reticencia": False}
    numeros_presentes = [item["numero"] for item in itens if not item["reticencia"]]
    assert numeros_presentes == [1, 13, 14, 15, 16, 17, 30]
    assert sum(1 for item in itens if item["reticencia"]) == 2


def test_intervalo_paginas_item_de_reticencia_nao_tem_numero():
    """O template distingue reticência de página pelo booleano `reticencia`,
    nunca comparando `numero` com a string mágica `"…"` (`Paginator.ELLIPSIS`)."""
    pagina = _pagina(numero_total_itens=30, por_pagina=1, numero_pagina=15)

    itens = intervalo_paginas(pagina)
    reticencias = [item for item in itens if item["reticencia"]]

    assert reticencias, "esperava ao menos uma reticência com 30 páginas"
    assert all(item["numero"] is None for item in reticencias)


def test_intervalo_paginas_on_each_side_1_gera_lista_mais_estreita():
    """Revisão do gate visual (achado P2, 2026-09-22): a lista compacta de
    celular usa `on_each_side=1` — só um vizinho de cada lado da página
    atual — em vez do padrão de 2 (lista larga), para caber numa linha a
    375px."""
    pagina = _pagina(numero_total_itens=30, por_pagina=1, numero_pagina=15)

    itens = intervalo_paginas(pagina, 1)

    numeros_presentes = [item["numero"] for item in itens if not item["reticencia"]]
    assert numeros_presentes == [1, 14, 15, 16, 30]
    assert sum(1 for item in itens if item["reticencia"]) == 2


# ---------------------------------------------------------------------------
# separador_milhar (revisão do gate visual, achado "Mundo real", 2026-09-22)
# ---------------------------------------------------------------------------


def test_separador_milhar_formata_milhar_com_ponto():
    assert separador_milhar(3408) == "3.408"


def test_separador_milhar_sem_milhar_nao_altera():
    assert separador_milhar(69) == "69"


def test_separador_milhar_valor_nao_numerico_e_devolvido_sem_alteracao():
    assert separador_milhar("abc") == "abc"


# ---------------------------------------------------------------------------
# rotulo_ordenacao (revisão do gate visual, achado P1, 2026-09-22; adaptado
# para a API de `OrdenacaoMixin`, `catalogo/ordenacao.py` — o filtro passa a
# receber o dicionário de rótulos da tela como argumento explícito, em vez
# de um dicionário fixo na tag).
# ---------------------------------------------------------------------------

_ROTULOS_TESTE = {
    "cadpro": "código",
    "descricao": "descrição",
    "unidade": "unidade",
    "classificacao": "classificação",
    "saldo": "saldo",
}


def test_rotulo_ordenacao_crescente():
    assert rotulo_ordenacao("cadpro", _ROTULOS_TESTE) == "código, crescente"


def test_rotulo_ordenacao_decrescente():
    assert rotulo_ordenacao("-saldo", _ROTULOS_TESTE) == "saldo, decrescente"


def test_rotulo_ordenacao_todas_as_colunas():
    assert rotulo_ordenacao("descricao", _ROTULOS_TESTE) == "descrição, crescente"
    assert rotulo_ordenacao("unidade", _ROTULOS_TESTE) == "unidade, crescente"
    assert rotulo_ordenacao("classificacao", _ROTULOS_TESTE) == "classificação, crescente"


def test_rotulo_ordenacao_coluna_fora_da_lista_de_rotulos_devolve_vazio():
    assert rotulo_ordenacao("outra_coisa", _ROTULOS_TESTE) == ""


def test_resolver_ordenacao_descricao_usa_campo_normalizado():
    """FR-042a: ordenar por descrição usa `descricao_busca` (sem acento, em
    minúsculas), nunca o campo bruto `descricao`. Verificação independente
    do collation do banco — com collation linguístico, ordenar pelo campo
    bruto produziria a mesma ordem nos dados do teste de integração, e uma
    regressão passaria despercebida.

    Adaptado para a API de `OrdenacaoMixin.resolver_ordenacao`
    (`catalogo/ordenacao.py`): `ConsultaCatalogoView` declara suas colunas
    (`colunas_ordenacao`) e o desempate (`campo_desempate = "cadpro"`); o
    teste chama o método diretamente, sem passar por `request`/view completa."""
    from catalogo.views import ConsultaCatalogoView

    view = ConsultaCatalogoView()
    assert view.resolver_ordenacao("descricao") == ("descricao", ("descricao_busca", "cadpro"))
    assert view.resolver_ordenacao("-descricao") == (
        "-descricao",
        ("-descricao_busca", "cadpro"),
    )


# ---------------------------------------------------------------------------
# interface/_th_ordenavel.html (frontend, FR-042a): cabeçalho ordenável
# independente de tela — `htmx_alvo`/`htmx_indicador` opcionais (mesmo
# padrão de `_paginacao.html`); sem eles, o `<a>` é só navegação normal.
# Testado com uma declaração fictícia, sem nenhuma ligação com a consulta do
# catálogo nem com o histórico de importações — este parcial não conhece
# nenhuma tela específica.
# ---------------------------------------------------------------------------


def _renderizar_th_ficticio(ordem, **extra):
    request = _rf.get("/qualquer/")
    contexto = {
        "request": request,
        "coluna": "coluna_ficticia",
        "rotulo": "Coluna Fictícia",
        "rotulo_acao": "coluna fictícia",
        "ordem": ordem,
        **extra,
    }
    return render_to_string("interface/_th_ordenavel.html", contexto)


def test_th_ordenavel_sem_htmx_alvo_e_navegacao_normal_sem_hx_get():
    html = _renderizar_th_ficticio(ordem="")

    assert "hx-get" not in html
    assert "hx-target" not in html
    assert "hx-indicator" not in html
    assert "hx-push-url" not in html


def test_th_ordenavel_com_htmx_alvo_e_indicador_dispara_troca_parcial():
    html = _renderizar_th_ficticio(
        ordem="", htmx_alvo="#alvo-ficticio", htmx_indicador="#indicador-ficticio"
    )

    assert 'hx-target="#alvo-ficticio"' in html
    assert 'hx-indicator="#indicador-ficticio"' in html
    assert 'hx-push-url="true"' in html


def test_th_ordenavel_coluna_nao_vigente_sem_aria_sort():
    html = _renderizar_th_ficticio(ordem="outra_coluna")

    assert "aria-sort" not in html


def test_th_ordenavel_ordem_crescente_indica_ascending_e_proximo_clique_alterna_para_decrescente():
    html = _renderizar_th_ficticio(ordem="coluna_ficticia")

    assert 'aria-sort="ascending"' in html
    href = re.search(r'href="([^"]*)"', html).group(1)
    assert "ordem=-coluna_ficticia" in href
    assert 'aria-label="Ordenar por coluna fictícia, decrescente"' in html


def test_th_ordenavel_ordem_padrao_decrescente_indica_descending_e_clique_volta_a_crescente():
    """Uma tela cuja ordem padrão já é decrescente (ex. o futuro histórico de
    importações, com `ordem_padrao = "-concluida_em"`) precisa continuar
    alternando corretamente a partir daí: com a coluna já decrescente, o
    próximo clique volta a crescente — o parcial não assume que a ordem
    padrão é sempre crescente."""
    html = _renderizar_th_ficticio(ordem="-coluna_ficticia")

    assert 'aria-sort="descending"' in html
    href = re.search(r'href="([^"]*)"', html).group(1)
    assert "ordem=coluna_ficticia" in href
    assert "ordem=-coluna_ficticia" not in href
    assert 'aria-label="Ordenar por coluna fictícia, crescente"' in html


# ---------------------------------------------------------------------------
# quantidade (Fase C, decisão do usuário): formato de EXIBIÇÃO de saldo/
# quantidade/diferença em pt-BR — milhar ".", decimal ",", só as casas
# significativas (até 3, o `decimal_places` dos models). Antes, "32,500" ao
# lado de "27000" lia como 32 mil. O filtro nunca vale para `value` de
# `<input>`/hidden (ver `tests/test_estoque_views_entrada.py`): "1.500" de
# exibição não é um formato de entrada aceito como 1500.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valor, esperado",
    [
        (27000, "27.000"),
        (Decimal("27000.000"), "27.000"),
        (Decimal("32.500"), "32,5"),
        (Decimal("6.000"), "6"),
        (0.125, "0,125"),
        (-1234.5, "-1.234,5"),
        (0, "0"),
        (Decimal("0.000"), "0"),
        (1234567.891, "1.234.567,891"),
        (Decimal("999.999"), "999,999"),
        (Decimal("1000"), "1.000"),
    ],
)
def test_quantidade_formata_em_pt_br_so_com_as_casas_significativas(valor, esperado):
    assert quantidade(valor) == esperado


def test_quantidade_zero_negativo_nao_vira_menos_zero():
    assert quantidade(-0.0) == "0"
    assert quantidade(Decimal("-0.000")) == "0"


def test_quantidade_nao_arredonda_para_menos_de_3_casas():
    """A exibição nunca esconde saldo: 0,001 continua 0,001 (não vira "0")."""
    assert quantidade(Decimal("0.001")) == "0,001"
    assert quantidade(Decimal("-0.001")) == "-0,001"
    assert quantidade(Decimal("12.345")) == "12,345"


def test_quantidade_float_e_lido_pela_representacao_decimal_nao_pelo_binario():
    """`0.1` como float não pode vazar "0,1000000000000000055…"."""
    assert quantidade(0.1) == "0,1"


def test_quantidade_none_e_vazio_viram_string_vazia():
    assert quantidade(None) == ""
    assert quantidade("") == ""


@pytest.mark.parametrize("valor", ["abc", "12,5x", Decimal("NaN"), Decimal("Infinity")])
def test_quantidade_valor_nao_numerico_e_devolvido_como_esta(valor):
    resultado = quantidade(valor)

    assert resultado is valor or resultado == valor


# ---------------------------------------------------------------------------
# truncar_meio (Fase C): encurta cortando NO MEIO, preservando começo e fim
# (com a extensão). Só exibição — quem usa mantém o valor completo acessível
# (histórico de importações: `<details>`).
# ---------------------------------------------------------------------------

_NOME_LONGO = "seed_dev_03_restauracao_carga_inicial_valida.csv"


def test_truncar_meio_preserva_inicio_e_fim_com_a_extensao():
    resultado = truncar_meio(_NOME_LONGO, 20)

    assert resultado.startswith(_NOME_LONGO[:4])
    assert resultado.endswith(".csv")
    assert "…" in resultado
    assert resultado != _NOME_LONGO


def test_truncar_meio_nao_corta_quando_cabe():
    assert truncar_meio("carga.csv", 20) == "carga.csv"


def test_truncar_meio_no_limite_exato_nao_corta():
    nome = "a" * 16 + ".csv"
    assert len(nome) == 20

    assert truncar_meio(nome, 20) == nome


def test_truncar_meio_um_caractere_acima_do_limite_corta():
    nome = "a" * 17 + ".csv"
    assert len(nome) == 21

    resultado = truncar_meio(nome, 20)

    assert resultado != nome
    assert "…" in resultado


@pytest.mark.parametrize(
    "nome",
    [
        _NOME_LONGO,
        "a" * 40,
        "relatorio_importacao_scpi_2026_01_carga_completa.csv",
        "sem_extensao_mas_com_nome_bem_comprido_mesmo",
        "muitos.pontos.no.nome.do.arquivo.exportado.csv",
    ],
)
@pytest.mark.parametrize("limite", [8, 12, 20, 30])
def test_truncar_meio_resultado_tem_exatamente_o_limite(nome, limite):
    assert len(nome) > limite, "pré-condição: o nome precisa exceder o limite"

    resultado = truncar_meio(nome, limite)

    assert len(resultado) == limite
    assert resultado.count("…") == 1


def test_truncar_meio_nomes_com_mesmo_prefixo_e_fim_diferente_resultam_em_cortes_diferentes():
    """O motivo de existir (achado do gate visual): `truncatechars` cortava só
    o fim e deixava vários arquivos como "seed_dev_0…", indistinguíveis. O que
    diferencia um arquivo do outro está no fim/extensão."""
    prefixo = "importacao_do_catalogo_scpi_completo_"
    a = truncar_meio(f"{prefixo}v1.csv", 20)
    b = truncar_meio(f"{prefixo}v2.csv", 20)
    c = truncar_meio(f"{prefixo}v1.txt", 20)

    assert len({a, b, c}) == 3


def test_truncar_meio_sem_extensao_ainda_preserva_o_fim_do_nome():
    nome = "a" * 30 + "final"

    resultado = truncar_meio(nome, 20)

    assert resultado.endswith("final")
    assert len(resultado) == 20


@pytest.mark.parametrize("limite", [0, 1, 2, -5, "abc", None])
def test_truncar_meio_limite_invalido_devolve_o_valor_sem_alteracao(limite):
    assert truncar_meio(_NOME_LONGO, limite) == _NOME_LONGO
