"""Testes de `catalogo/ordenacao.py` (`OrdenacaoMixin`), extraído de
`ConsultaCatalogoView` (`catalogo/views.py`) para ser reutilizado por outras
telas de lista do app `catalogo` — a próxima é o histórico de importações,
numa task futura, não coberta aqui.

Unitários, com uma declaração fictícia (`_ViewFicticia`), sem nenhuma ligação
com a consulta do catálogo (já coberta por
`tests/test_catalogo_templatetags.py::test_resolver_ordenacao_descricao_usa_campo_normalizado`
e por `tests/test_catalogo_consulta.py`) nem com o histórico de importações.
Cobrem especificamente o que a consulta não exercita: ordem padrão
decrescente e a regra de desempate ("não duplica quando o campo de desempate
já faz parte da coluna escolhida").
"""

from catalogo.ordenacao import ColunaOrdenacao, OrdenacaoMixin


class _ViewFicticia(OrdenacaoMixin):
    colunas_ordenacao = {
        "nome": ColunaOrdenacao(("nome",), "nome"),
        "criado_em": ColunaOrdenacao(("criado_em",), "criado em"),
    }
    ordem_padrao = "-criado_em"
    campo_desempate = "id"


def test_ordem_ausente_cai_na_ordem_padrao_decrescente():
    view = _ViewFicticia()

    assert view.resolver_ordenacao("") == ("-criado_em", ("-criado_em", "id"))


def test_ordem_desconhecida_cai_na_ordem_padrao_sem_erro():
    view = _ViewFicticia()

    assert view.resolver_ordenacao("--injecao") == ("-criado_em", ("-criado_em", "id"))


def test_ordem_crescente_aplica_desempate():
    view = _ViewFicticia()

    assert view.resolver_ordenacao("nome") == ("nome", ("nome", "id"))


def test_ordem_decrescente_aplica_desempate_sempre_crescente():
    """O campo de desempate nunca inverte junto com a coluna escolhida —
    garante paginação estável independente da direção da coluna ordenada."""
    view = _ViewFicticia()

    assert view.resolver_ordenacao("-nome") == ("-nome", ("-nome", "id"))


def test_coluna_igual_ao_campo_de_desempate_nao_duplica():
    """Quando o campo real da coluna escolhida já é o próprio campo de
    desempate, ele não é acrescentado de novo a `order_by`."""

    class _ViewDesempateNaPropriaColuna(OrdenacaoMixin):
        colunas_ordenacao = {
            "nome": ColunaOrdenacao(("nome",), "nome"),
            "criado_em": ColunaOrdenacao(("criado_em",), "criado em"),
        }
        ordem_padrao = "criado_em"
        campo_desempate = "criado_em"

    view = _ViewDesempateNaPropriaColuna()

    assert view.resolver_ordenacao("criado_em") == ("criado_em", ("criado_em",))
    assert view.resolver_ordenacao("-criado_em") == ("-criado_em", ("-criado_em",))
    # coluna diferente: o desempate continua sendo acrescentado normalmente
    assert view.resolver_ordenacao("nome") == ("nome", ("nome", "criado_em"))


def test_sem_campo_de_desempate_declarado_nao_acrescenta_nada():
    class _ViewSemDesempate(OrdenacaoMixin):
        colunas_ordenacao = {"nome": ColunaOrdenacao(("nome",), "nome")}
        ordem_padrao = "nome"

    view = _ViewSemDesempate()

    assert view.resolver_ordenacao("nome") == ("nome", ("nome",))


def test_ordenacao_rotulos_expoe_dicionario_de_rotulos_declarado():
    view = _ViewFicticia()

    assert view.ordenacao_rotulos == {"nome": "nome", "criado_em": "criado em"}
