"""Testes de `estoque.quantidade.interpretar_quantidade_recebida` (T008).

Módulo puro, sem banco (`contracts/interface-estoque.md`). Cobre exatamente a
tabela normativa "Quantidade — exemplos normativos" de
`contracts/composicao-entrada.md`, mais os limites de dígitos e o
comportamento de nunca arredondar (`INV-CATALOG-005`, FR-005). Distinto de
propósito de `catalogo.leitura_scpi.interpretar_quantidade` (research R8):
aqui o sinal nunca é aceito e um grupo de milhar não pode começar com zero
(`0.750` é recusado, não lido como 750).

TDD: escrito antes de `estoque/quantidade.py` existir — falha inteiro por
`ImportError` até lá, o que é esperado.
"""

from decimal import Decimal

import pytest

from estoque.quantidade import QuantidadeInvalida, interpretar_quantidade_recebida

# ---------------------------------------------------------------------------
# Tabela normativa (contracts/composicao-entrada.md)
# ---------------------------------------------------------------------------

ACEITOS = [
    pytest.param("5", Decimal("5.000"), id="inteiro_simples"),
    pytest.param("0,750", Decimal("0.750"), id="decimal_sem_milhar"),
    pytest.param("1.250,5", Decimal("1250.500"), id="milhar_e_decimal"),
    pytest.param("1250,5", Decimal("1250.500"), id="sem_separador_de_milhar"),
    pytest.param(" 12 ", Decimal("12.000"), id="espacos_nas_bordas"),
    pytest.param("2.500", Decimal("2500.000"), id="ponto_e_milhar_sem_decimal"),
]


@pytest.mark.parametrize("texto, esperado", ACEITOS)
def test_quantidades_aceitas_da_tabela_normativa(texto, esperado):
    resultado = interpretar_quantidade_recebida(texto)

    assert resultado == esperado
    assert isinstance(resultado, Decimal)
    # Nunca arredonda: o valor devolvido tem exatamente 3 casas decimais,
    # iguais às do texto digitado (nenhum dígito descartado nem completado
    # por arredondamento).
    assert resultado.as_tuple().exponent == -3


RECUSADOS = [
    pytest.param("0", id="zero_inteiro"),
    pytest.param("0,000", id="zero_com_decimais"),
    pytest.param("-3", id="sinal_negativo"),
    pytest.param("2,5001", id="mais_de_tres_casas_decimais"),
    pytest.param("0.750", id="grupo_de_milhar_comecando_com_zero"),
    pytest.param("1.25", id="grupo_de_milhar_incompleto"),
    pytest.param(",5", id="sem_parte_inteira"),
    pytest.param("abc", id="nao_numerico"),
    pytest.param("1,2,3", id="mais_de_uma_virgula"),
    pytest.param("", id="vazio"),
    pytest.param("   ", id="somente_espacos"),
    pytest.param("1000000000000", id="treze_digitos_inteiros_fora_do_limite"),
]


@pytest.mark.parametrize("texto", RECUSADOS)
def test_quantidades_recusadas_da_tabela_normativa(texto):
    with pytest.raises(QuantidadeInvalida) as excinfo:
        interpretar_quantidade_recebida(texto)

    assert excinfo.value.mensagem, "toda recusa precisa de uma mensagem para o usuário"


# ---------------------------------------------------------------------------
# Limite de 12 dígitos inteiros (research R11/R8): fronteira exata.
# ---------------------------------------------------------------------------


def test_doze_digitos_inteiros_e_aceito():
    resultado = interpretar_quantidade_recebida("999999999999")

    assert resultado == Decimal("999999999999.000")


def test_treze_digitos_inteiros_e_recusado():
    with pytest.raises(QuantidadeInvalida):
        interpretar_quantidade_recebida("1000000000000")


# ---------------------------------------------------------------------------
# NOVO (revisão do code-reviewer, item 4): uma parte inteira absurdamente
# grande (bem acima do limite de 12 dígitos) precisa continuar recusada como
# `QuantidadeInvalida` — nunca um `ValueError` puro. `int(texto)` sobre uma
# string de milhares de dígitos esbarra no limite de conversão do próprio
# Python (`sys.int_info.default_max_str_digits`, ~4300 por padrão desde a
# 3.11) e levanta `ValueError` genérico ANTES da checagem de dígitos do
# próprio módulo — que é subclasse de `ValueError`, mas não de
# `QuantidadeInvalida`. Este teste falha até a correção de produção (checar
# o comprimento da parte inteira ANTES de converter para `int`).
# ---------------------------------------------------------------------------


def test_quantidade_com_parte_inteira_de_cinco_mil_digitos_e_recusada_como_quantidade_invalida():
    texto = "5" * 5000

    with pytest.raises(QuantidadeInvalida) as excinfo:
        interpretar_quantidade_recebida(texto)

    assert excinfo.value.mensagem, "toda recusa precisa de uma mensagem para o usuário"


# ---------------------------------------------------------------------------
# Nunca arredonda (FR-005, Edge Cases): a recusa por "mais de três casas" não
# pode silenciosamente virar um valor truncado ou arredondado.
# ---------------------------------------------------------------------------


def test_quantidade_com_quatro_casas_decimais_nao_e_arredondada_em_silencio():
    with pytest.raises(QuantidadeInvalida) as excinfo:
        interpretar_quantidade_recebida("1,2345")

    # A mensagem de recusa é sobre o número de casas decimais, não sobre
    # formato genérico — mesmo padrão de research R8 (mensagem específica).
    assert "três casas" in excinfo.value.mensagem or "3 casas" in excinfo.value.mensagem


# ---------------------------------------------------------------------------
# Mensagens específicas para os dois casos citados literalmente por
# `research.md` R8 — protege contra uma implementação que devolva sempre a
# mesma mensagem genérica de formato para vazio e para zero.
# ---------------------------------------------------------------------------


def test_mensagem_de_quantidade_vazia():
    with pytest.raises(QuantidadeInvalida) as excinfo:
        interpretar_quantidade_recebida("")

    assert excinfo.value.mensagem == "Informe a quantidade."


def test_mensagem_de_quantidade_zero():
    with pytest.raises(QuantidadeInvalida) as excinfo:
        interpretar_quantidade_recebida("0")

    assert "maior que zero" in excinfo.value.mensagem
