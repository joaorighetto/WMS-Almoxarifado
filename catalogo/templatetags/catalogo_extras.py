"""Template tags de apresentação do app `catalogo` — sem regra de domínio.

Só a tag `querystring_pagina`, usada por `catalogo/templates/catalogo/_paginacao.html`
para montar os links de página vizinha sem descartar os demais parâmetros da
URL atual (revisão T051, achado P3: uma página com mais de uma seção
paginada — ex.: `execucao_detalhe.html`, com `pagina_excecoes`,
`pagina_divergencias` e `pagina_alteracoes` — zerava as outras ao avançar
uma delas; o mesmo valia para os filtros `codigo`/`descricao` da consulta).
"""

from django import template

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
