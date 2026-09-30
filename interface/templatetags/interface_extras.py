"""Template tags de apresentação compartilhadas entre apps — sem regra de domínio.

Movidas de `catalogo/templatetags/catalogo_extras.py` (consolidação de UX,
Fase A): nenhuma delas é específica do catálogo — todas já eram usadas por
`catalogo`, `fornecedores` e/ou `estoque`.

- `querystring_pagina`, usada por `interface/templates/interface/_paginacao.html`
  para montar os links de página vizinha sem descartar os demais parâmetros da
  URL atual (revisão T051, achado P3: uma página com mais de uma seção
  paginada — ex.: `execucao_detalhe.html`, com `pagina_excecoes`,
  `pagina_divergencias` e `pagina_alteracoes` — zerava as outras ao avançar
  uma delas; o mesmo valia para os filtros `codigo`/`descricao` da consulta).
- `querystring_ordenacao`, usada por `_th_ordenavel.html` (não diretamente
  pelas telas) para alternar a direção de uma coluna (FR-042a) — a consulta e
  o histórico de importações, tanto de `catalogo` quanto de `fornecedores`.
- `intervalo_paginas`, usada por `_paginacao.html` para a paginação numerada
  com reticências (FR-042b), também para a lista compacta de celular
  (revisão do gate visual, 2026-09-22, achado P2).
- `separador_milhar`, usada por `_paginacao.html` para o total do resumo
  (revisão do gate visual, achado "3408 materials"), e por telas de lista de
  `catalogo`, `fornecedores` e `estoque`.
- `rotulo_ordenacao`, usada por telas de lista com ordenação por coluna
  (`OrdenacaoMixin`, `catalogo/ordenacao.py`) para dizer em texto a ordem
  vigente (revisão do gate visual, achado P1) — a consulta e o histórico de
  importações, tanto de `catalogo` (desde FR-037a) quanto de `fornecedores`
  (Fase B).
- `truncar_meio` (Fase C): encurta um texto cortando no meio (começo + "…" +
  final com a extensão) — nome de arquivo do histórico de importações.
- `quantidade` (Fase C): quantidade/saldo/diferença em pt-BR ("27.000",
  "32,5"), só com as casas significativas — todas as células de exibição de
  saldo, quantidade e diferença (`catalogo`, `estoque`); nunca em `value` de
  input nem em dado enviado.

Consumidores: templates de `catalogo` e `fornecedores` usam todas as tags
acima (diretamente ou via `_paginacao.html`/`_th_ordenavel.html`);
`estoque` só consome `querystring_pagina`/`intervalo_paginas`
(via `_paginacao.html`, nas listas paginadas) e `separador_milhar`
(diretamente, nos resultados de busca de emitente/material) — não tem
coluna ordenável, então nunca usa `querystring_ordenacao`/`rotulo_ordenacao`.
Ver `{% load interface_extras %}` em cada um.
"""

from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

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
    — este filtro é genérico entre telas (consulta do catálogo, histórico de
    importações de catálogo e de fornecedores).

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


@register.filter
def truncar_meio(valor, limite):
    """Encurta `valor` para no máximo `limite` caracteres cortando NO MEIO:
    o começo, uma reticência (`…`) e o fim — com pelo menos a extensão e mais
    alguns caracteres do final —, em vez de cortar só o fim (Fase C, achado do
    gate visual: nomes de arquivo cortados por `truncatechars` ficavam todos
    "seed_dev_0…", indistinguíveis; o que diferencia um arquivo do outro está,
    em geral, no meio/fim do nome e na extensão).

    Só exibição: quem usa o filtro precisa manter o valor completo acessível
    (o histórico de importações o deixa num `<details>` — ver
    `catalogo`/`fornecedores` `historico.html`). Um valor que já cabe é
    devolvido igual, sem reticência, então `valor|truncar_meio:N == valor`
    diz "cabe, não precisa de `<details>`". Exemplo com `limite=14`:
    "seed_dev_03_restauracao_carga_inicial_valida.csv" → "seed_d…ida.csv".

    Divisão: o fim ganha o maior entre metade dos caracteres disponíveis e
    (extensão + 3), sem deixar menos de 2 para o começo; o começo fica com o
    resto. `limite` inválido ou menor que 3 devolve o valor sem alteração
    (nunca quebra a renderização, mesmo critério de `separador_milhar`).
    """
    texto = str(valor)
    try:
        limite = int(limite)
    except (TypeError, ValueError):
        return valor
    if limite < 3 or len(texto) <= limite:
        return texto
    util = limite - 1
    ponto = texto.rfind(".")
    extensao = len(texto) - ponto if ponto > 0 else 0
    cauda = max(util // 2, min(extensao + 3, util - 2))
    cabeca = util - cauda
    return f"{texto[:cabeca]}…{texto[-cauda:]}"


_CASAS_QUANTIDADE = Decimal("0.001")  # `decimal_places=3` dos models (saldo, quantidade)


@register.filter
def quantidade(valor):
    """Formata uma quantidade/saldo/diferença para EXIBIÇÃO em pt-BR: milhar
    "." e decimal ",", só com as casas significativas (até 3, o
    `decimal_places` dos models de saldo e quantidade) — Fase C, decisão do
    usuário. Antes, `floatformat:"-3"` imprimia "32,500" ao lado de "27000"
    (que parece 32 mil, não 32 e meio), e o detalhe da entrada mostrava "6,000"
    sem filtro algum.

    Exemplos: `27000` → "27.000"; `32.5` → "32,5"; `Decimal("6.000")` → "6";
    `0.125` → "0,125"; `-1234.5` → "-1.234,5" (hífen simples, o mesmo sinal
    que `diferenca` sempre usou; o "+" explícito das divergências fica no
    template, `{% if diferenca > 0 %}+{% endif %}`); `0` → "0"; `None` → "".

    Aritmética em `Decimal` (nunca `float`): um `float` de entrada é lido por
    `str()` (`0.1` → "0,1", não "0,1000000000000000055…"). Os valores
    exibidos já vêm com no máximo 3 casas dos models; por segurança a
    exibição é quantizada em 3 casas (`ROUND_HALF_EVEN`) — nunca menos: não
    há arredondamento para menos casas do que o model guarda.

    SÓ para células de exibição. Nunca aplicar ao `value` de um `<input>`, a
    `as_hidden` nem a dado enviado ao servidor: o formato de exibição não é o
    formato de entrada (`estoque.quantidade.interpretar_quantidade_recebida`).
    Um valor não numérico é devolvido sem alteração, para nunca quebrar a
    renderização.
    """
    if valor is None or valor == "":
        return ""
    try:
        numero = valor if isinstance(valor, Decimal) else Decimal(str(valor))
        if not numero.is_finite():
            return valor
        numero = numero.quantize(_CASAS_QUANTIDADE, rounding=ROUND_HALF_EVEN)
    except (InvalidOperation, ValueError, TypeError):
        return valor
    texto = f"{abs(numero):f}"
    inteira, _, fracao = texto.partition(".")
    fracao = fracao.rstrip("0")
    inteira = f"{int(inteira):,}".replace(",", ".")
    resultado = f"{inteira},{fracao}" if fracao else inteira
    negativo = numero < 0
    return f"-{resultado}" if negativo else resultado
