"""Template tags de apresentação do app `catalogo` — sem regra de domínio.

- `querystring_pagina`, usada por `catalogo/templates/catalogo/_paginacao.html`
  para montar os links de página vizinha sem descartar os demais parâmetros da
  URL atual (revisão T051, achado P3: uma página com mais de uma seção
  paginada — ex.: `execucao_detalhe.html`, com `pagina_excecoes`,
  `pagina_divergencias` e `pagina_alteracoes` — zerava as outras ao avançar
  uma delas; o mesmo valia para os filtros `codigo`/`descricao` da consulta).
- `querystring_ordenacao`, usada pelo cabeçalho ordenável da consulta do
  catálogo (FR-042a) para alternar a direção de uma coluna.
- `intervalo_paginas`, usada por `_paginacao.html` para a paginação numerada
  com reticências (FR-042b), agora também para a lista compacta de celular
  (revisão do gate visual, 2026-09-22, achado P2).
- `separador_milhar`, usada por `_paginacao.html` para o total do resumo
  (revisão do gate visual, achado "3408 materials").
- `rotulo_ordenacao`, usada por telas de lista com ordenação por coluna
  (`OrdenacaoMixin`, `catalogo/ordenacao.py`) para dizer em texto a ordem
  vigente (revisão do gate visual, achado P1) — a consulta do catálogo e,
  desde FR-037a, o histórico de importações.
"""

from django import template
from django.core.paginator import Page

register = template.Library()


@register.simple_tag(takes_context=True)
def querystring_pagina(context, parametro, valor):
    """Querystring da requisição atual com `parametro` substituído por
    `valor`, preservando todos os demais parâmetros já presentes em
    `request.GET` (outras seções paginadas, filtros de busca etc.).

    Equivalente, para um único parâmetro dinamicamente nomeado, à tag
    nativa `{% querystring %}` do Django (5.1+) — que exige nomes de chave
    literais e por isso não serve diretamente aqui, já que `parametro` varia
    por seção (`pagina_excecoes`, `pagina_divergencias`, `pagina_alteracoes`,
    `pagina`).
    """
    params = context["request"].GET.copy()
    params[parametro] = valor
    return f"?{params.urlencode()}"


@register.simple_tag(takes_context=True)
def querystring_ordenacao(context, coluna):
    """Querystring da requisição atual com `ordem` definido para alternar a
    ordenação de `coluna` (FR-042a, `ConsultaCatalogoView`).

    Compara `coluna` com a ordem efetiva já resolvida pela view
    (`context["ordem"]`, ex. `"cadpro"`, `"-saldo"`): se forem iguais — ou
    seja, a coluna já está ordenada crescente —, a nova ordem vira
    decrescente (`-coluna`); em qualquer outro caso (coluna diferente, ou a
    própria coluna já decrescente), a nova ordem volta a crescente
    (`coluna`). Preserva todos os demais parâmetros de `request.GET` (como
    `querystring_pagina`) e remove `pagina`, porque mudar a ordem volta à
    primeira página (FR-042a).
    """
    ordem_atual = context.get("ordem", "")
    nova_ordem = f"-{coluna}" if ordem_atual == coluna else coluna
    params = context["request"].GET.copy()
    params["ordem"] = nova_ordem
    params.pop("pagina", None)
    return f"?{params.urlencode()}"


@register.simple_tag
def intervalo_paginas(pagina: Page, on_each_side: int = 2):
    """Sequência de itens da paginação numerada (FR-042b), a partir de
    `Paginator.get_elided_page_range` (`on_ends=1`): páginas próximas da
    atual e a primeira/última sempre visíveis, com reticências no lugar dos
    intervalos distantes.

    `on_each_side` (padrão 2, a lista "larga" de desktop/tablet) é
    parametrizável desde a revisão do gate visual de 2026-09-22 (achado P2:
    "6+5 não cabe numa linha a 375px"): `_paginacao.html` chama esta tag uma
    segunda vez com `on_each_side=1` para a lista "compacta" (só um vizinho
    de cada lado), alternada por media query — nunca calculada escondendo
    itens da lista larga por CSS, porque os dois intervalos têm reticências
    em posições diferentes (esconder um subconjunto de itens de um único
    range geraria um buraco sem reticência).

    Retorna uma lista de dicts `{"numero": int | None, "reticencia": bool}`
    — um item por reticência (`{"numero": None, "reticencia": True}`) ou por
    página (`{"numero": N, "reticencia": False}`) — para o template
    distinguir reticência de número sem comparar com a string mágica `"…"`
    (`Paginator.ELLIPSIS`). Uso esperado no template:

        {% intervalo_paginas pagina as paginas %}
        {% for item in paginas %}
          {% if item.reticencia %}…{% else %}{{ item.numero }}{% endif %}
        {% endfor %}
    """
    paginator = pagina.paginator
    itens = []
    for item in paginator.get_elided_page_range(
        pagina.number, on_each_side=on_each_side, on_ends=1
    ):
        if item == paginator.ELLIPSIS:
            itens.append({"numero": None, "reticencia": True})
        else:
            itens.append({"numero": item, "reticencia": False})
    return itens


@register.filter
def separador_milhar(valor):
    """Formata um inteiro com "." como separador de milhar pt-BR (revisão do
    gate visual, achado "Mundo real" — 2026-09-22: "3408 materials" não lia
    como número nem como português). Implementado sem depender de locale do
    ambiente — divide em grupos de 3 dígitos a partir da direita — porque o
    projeto não usa `django.contrib.humanize` (não está em `INSTALLED_APPS`)
    nem formatação numérica locale-aware configurada (`USE_THOUSAND_SEPARATOR`).
    Usado no resumo da paginação, tanto para o total de itens quanto para o
    número de páginas.

    Um valor não numérico é devolvido sem alteração, para nunca quebrar a
    renderização por um dado inesperado — não deveria acontecer, já que a
    origem é sempre `Paginator.count`/`num_pages` (inteiro).
    """
    try:
        valor_int = int(valor)
    except (TypeError, ValueError):
        return valor
    return f"{valor_int:,}".replace(",", ".")


@register.filter
def rotulo_ordenacao(ordem, rotulos):
    """Frase em pt-BR da ordenação vigente de uma tela de lista (ex. "saldo,
    decrescente"), a partir do valor normalizado já resolvido pela view
    (`ordem` — ex. `"-saldo"`) e do dicionário `{nome_lógico: rotulo}`
    declarado por ela (`rotulos` — `OrdenacaoMixin.ordenacao_rotulos`,
    `catalogo/ordenacao.py`, exposto no contexto como `ordenacao_rotulos`).

    Cada tela expõe seus próprios rótulos em vez de um dicionário fixo aqui
    — este filtro é genérico entre telas (ex. consulta do catálogo,
    futuramente o histórico de importações).

    Uso esperado no template: `{{ ordem|rotulo_ordenacao:ordenacao_rotulos }}`.

    Revisão do gate visual (achado P1, 2026-09-22): a ordem vigente também
    precisa ficar visível em texto — no resumo da paginação, para continuar
    legível quando a coluna ordenada estiver fora da tela (celular), e num
    anúncio a leitor de tela (`#resultados-anuncio`, `consulta.html`), para
    quem usa a coluna/indicador visual do cabeçalho não percebe a mudança.

    Devolve string vazia para um valor de coluna fora da lista branca — não
    deveria acontecer, já que `ordem` sempre vem de
    `OrdenacaoMixin.resolver_ordenacao`, mas evita quebrar o texto se algum
    dia chegar algo inesperado.
    """
    decrescente = ordem.startswith("-")
    coluna = ordem[1:] if decrescente else ordem
    rotulo = rotulos.get(coluna) if rotulos else None
    if rotulo is None:
        return ""
    direcao = "decrescente" if decrescente else "crescente"
    return f"{rotulo}, {direcao}"
