"""Ordenação genérica por coluna para views de lista do app `catalogo`
(FR-042a, FR-037a).

Extraído de `ConsultaCatalogoView` (`catalogo/views.py`) para ser reutilizado
por outras telas de lista do app — também usado por
`HistoricoImportacoesView` (FR-037a, emenda de 2026-09-22).

`OrdenacaoMixin` resolve o parâmetro `ordem` (GET) sempre por lista branca:
o valor bruto do usuário NUNCA é repassado a `order_by` — só os campos
declarados em `colunas_ordenacao` chegam lá.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ColunaOrdenacao:
    """Uma coluna ordenável declarada por uma view concreta.

    `campos`: campos reais do model, na ordem em que entram em `order_by`.
    Mais de um campo representa uma ordenação composta (ex. classificação =
    `nome_grupo` + `nome_subgrupo`): em decrescente, os dois invertem juntos,
    por comporem uma única ordenação lógica — nunca cada um isoladamente.

    `rotulo`: texto em pt-BR, minúsculo, usado por `rotulo_ordenacao`
    (`catalogo/templatetags/catalogo_extras.py`) numa frase corrida (ex.
    "ordenado por saldo, decrescente").
    """

    campos: tuple[str, ...]
    rotulo: str


class OrdenacaoMixin:
    """Mixin de ordenação por coluna para views de lista (`View`/`ListView`).

    Cada view concreta declara:
    - `colunas_ordenacao`: `dict[str, ColunaOrdenacao]` — a lista branca de
      nomes lógicos aceitos em `?ordem=`, cada um com os campos reais do
      model e o rótulo em pt-BR.
    - `ordem_padrao`: nome lógico usado quando `?ordem=` está ausente ou é
      desconhecido (ex. `"cadpro"`), opcionalmente prefixado com `-` para uma
      ordem padrão decrescente (ex. `"-concluida"`, do histórico). Precisa ser uma
      chave de `colunas_ordenacao`.
    - `campo_desempate` (opcional, `None` por padrão): campo real sempre
      acrescentado ao final de `order_by`, na MESMA direção declarada aqui —
      nunca invertendo junto com a coluna escolhida —, quando ainda não faz
      parte dos campos da coluna escolhida — garante paginação estável mesmo
      com muitos empates na coluna ordenada (ex. `"cadpro"` crescente na
      consulta do catálogo; `"-pk"` decrescente no histórico de importações,
      para desfazer empates de `concluida_em` pela execução mais recente,
      qualquer que seja a coluna/direção escolhida pelo usuário).

    `resolver_ordenacao(valor_bruto)` traduz o parâmetro `ordem` (GET) num
    argumento seguro para `order_by`, devolvendo `(ordem_efetiva,
    campos_order_by)`:
    - `ordem_efetiva`: valor normalizado para expor no contexto (`ordem`) e
      para `querystring_ordenacao` comparar, ex. `"cadpro"`, `"-saldo"`;
    - `campos_order_by`: campos reais para `queryset.order_by(*campos)`.

    Qualquer `?ordem=` ausente, desconhecido, o nome real de um campo do
    model, ou uma tentativa de injeção (ex. `--saldo`) cai silenciosamente na
    ordem padrão, sem erro.

    `ordenacao_rotulos` expõe `{nome_lógico: rotulo}` para o contexto do
    template — `rotulo_ordenacao` usa esse dicionário para montar a frase da
    ordem vigente, em vez de um dicionário fixo por tela.
    """

    colunas_ordenacao: dict[str, ColunaOrdenacao] = {}
    ordem_padrao: str = ""
    campo_desempate: str | None = None

    def resolver_ordenacao(self, valor_bruto: str) -> tuple[str, tuple[str, ...]]:
        nome, decrescente = self._nome_e_direcao(valor_bruto)
        coluna = self.colunas_ordenacao.get(nome)
        if coluna is None:
            nome, decrescente = self._nome_e_direcao(self.ordem_padrao)
            coluna = self.colunas_ordenacao[nome]

        campos_order_by = tuple(
            f"-{campo}" if decrescente else campo for campo in coluna.campos
        )
        if self.campo_desempate:
            campo_desempate_base, _ = self._nome_e_direcao(self.campo_desempate)
            if campo_desempate_base not in {
                campo.removeprefix("-") for campo in campos_order_by
            }:
                campos_order_by = campos_order_by + (self.campo_desempate,)

        ordem_efetiva = f"-{nome}" if decrescente else nome
        return ordem_efetiva, campos_order_by

    @staticmethod
    def _nome_e_direcao(valor: str) -> tuple[str, bool]:
        decrescente = valor.startswith("-")
        return (valor[1:] if decrescente else valor), decrescente

    @property
    def ordenacao_rotulos(self) -> dict[str, str]:
        return {nome: coluna.rotulo for nome, coluna in self.colunas_ordenacao.items()}
