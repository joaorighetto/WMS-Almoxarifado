"""Interpretação da quantidade recebida digitada na composição da entrada
(`contracts/interface-estoque.md`, research R8).

Módulo puro, sem banco: gramática brasileira (ponto como separador de
milhar, vírgula como separador decimal), sem sinal, sem arredondamento. É
deliberadamente independente de `catalogo.leitura_scpi.interpretar_quantidade`
— aquele aceita sinal e arredonda em silêncio (`ROUND_HALF_UP`), comportamento
certo para o arquivo do SCPI e errado aqui (research R8): a quantidade
recebida numa entrada nunca é negativa e nunca deve ser corrigida sem o
usuário perceber.
"""

import re
from decimal import Decimal

# Parte inteira simples (dígitos corridos) ou agrupada de 3 em 3 por ponto,
# começando por um dígito não-zero (um grupo como "0.750" não é milhar
# válido — ver `contracts/composicao-entrada.md`, tabela de exemplos
# normativos). Parte decimal opcional, separada por vírgula, sem limite de
# dígitos aqui — o limite de três casas é checado à parte, para distinguir a
# mensagem de "fora da gramática" da de "mais de três casas decimais".
_PADRAO_QUANTIDADE = re.compile(
    r"^(?P<inteira>[0-9]+|[1-9][0-9]{0,2}(?:\.[0-9]{3})+)(?:,(?P<decimal>[0-9]+))?$"
)

_LIMITE_DIGITOS_INTEIROS = 12


class QuantidadeInvalida(ValueError):
    """Quantidade recebida não interpretável ou fora dos limites aceitos.

    `mensagem` é o texto pronto para o usuário (research R8).
    """

    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


def interpretar_quantidade_recebida(texto: str) -> Decimal:
    """`texto` (como digitado no campo de quantidade) -> `Decimal` com três
    casas, estritamente positivo, com no máximo 12 dígitos inteiros. Nunca
    arredonda: mais de três casas decimais é recusado, não truncado nem
    arredondado.
    """
    texto_aparado = texto.strip()
    if texto_aparado == "":
        raise QuantidadeInvalida("Informe a quantidade.")

    casamento = _PADRAO_QUANTIDADE.fullmatch(texto_aparado)
    if not casamento:
        raise QuantidadeInvalida(
            "Use números, com vírgula para decimais (ex.: 1.250,5)."
        )

    parte_inteira = casamento.group("inteira").replace(".", "")
    parte_decimal = casamento.group("decimal") or ""

    if len(parte_decimal) > 3:
        raise QuantidadeInvalida("Informe no máximo três casas decimais.")

    # Conta os dígitos sem passar por `int()`: para uma parte inteira com
    # milhares de dígitos, `int(texto)` esbarra no limite de conversão do
    # próprio Python (`sys.int_info.default_max_str_digits`) e levanta um
    # `ValueError` genérico — não a subclasse `QuantidadeInvalida` que o
    # restante do fluxo espera. Contar os dígitos direto na string (sem
    # zeros à esquerda) recusa cedo, sem nunca precisar converter.
    digitos_inteiros = len(parte_inteira.lstrip("0") or "0")
    if digitos_inteiros > _LIMITE_DIGITOS_INTEIROS:
        raise QuantidadeInvalida(
            "A quantidade informada está acima do limite aceito."
        )

    texto_decimal = f"{parte_inteira}.{parte_decimal.ljust(3, '0')}"
    valor = Decimal(texto_decimal)

    if valor == 0:
        raise QuantidadeInvalida("A quantidade deve ser maior que zero.")

    return valor
