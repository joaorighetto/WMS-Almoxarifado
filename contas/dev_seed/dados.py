"""Organização fictícia e revisão SCPI simulada, sem modificar o arquivo original.

Os códigos válidos das linhas aceitas vêm exclusivamente do CSV informado.
Os códigos 999.999.* abaixo identificam apenas linhas propositalmente recusadas.
"""

from dataclasses import replace
from decimal import Decimal

from catalogo.leitura_scpi import COLUNAS_OBRIGATORIAS, RegistroAceito
from contas.models import Papel

SETORES = (
    ("almox", "Almoxarifado", True),
    ("eta", "Estação de Tratamento de Água", True),
    ("ete", "Estação de Tratamento de Esgoto", True),
    ("redes", "Operação e Manutenção de Redes", True),
    ("oficina", "Manutenção Eletromecânica", True),
    ("lab", "Laboratório de Controle de Qualidade", True),
    ("adm", "Administração e Atendimento", True),
    ("obras", "Obras e Expansão — Unidade Desativada", False),
)

# Chave, em `SETORES`, do setor designado como o Almoxarifado (`INV-ORG-004`).
SETOR_ALMOXARIFADO = "almox"

# Matrícula, nome fictício, setor, papéis adicionais ao REQUISITANTE, conta ativa.
# A conta técnica admin é criada separadamente e não recebe nenhum ROLE-*.
USUARIOS = (
    (
        "chefe",
        "Helena Duarte Moura",
        "almox",
        (
            Papel.CHEFE_SETOR,
            Papel.FUNCIONARIO_ALMOXARIFADO,
            Papel.CHEFE_ALMOXARIFADO,
        ),
        True,
    ),
    ("funcionario", "Rogério Batista Lima", "almox", (Papel.FUNCIONARIO_ALMOXARIFADO,), True),
    ("requisitante", "Cláudia Nogueira Reis", "almox", (), True),
    ("almox.conferente", "Tiago Almeida Prado", "almox", (Papel.FUNCIONARIO_ALMOXARIFADO,), True),
    ("almox.inativo", "Marcos Vinícius Teles", "almox", (Papel.FUNCIONARIO_ALMOXARIFADO,), False),
    ("eta.chefe", "Patrícia Lemos Andrade", "eta", (Papel.CHEFE_SETOR,), True),
    ("eta.auxiliar", "Fernando Aguiar Costa", "eta", (Papel.AUXILIAR_SETOR,), True),
    ("eta.operador.01", "Joana Ferraz Quintino", "eta", (), True),
    ("eta.operador.02", "Sérgio Matos Vilela", "eta", (), True),
    ("ete.chefe", "Ricardo Salgado Peixoto", "ete", (Papel.CHEFE_SETOR,), True),
    ("ete.auxiliar", "Luciana Barros Vieira", "ete", (Papel.AUXILIAR_SETOR,), True),
    ("ete.operador.01", "Anderson Pires Tavares", "ete", (), True),
    ("ete.operador.02", "Beatriz Camargo Rocha", "ete", (), True),
    ("redes.chefe", "Gilberto Farias Neves", "redes", (Papel.CHEFE_SETOR,), True),
    ("redes.auxiliar", "Débora Cardoso Azevedo", "redes", (Papel.AUXILIAR_SETOR,), True),
    ("redes.encanador.01", "Paulo Henrique Souto", "redes", (), True),
    ("redes.encanador.02", "Elisa Montenegro Dias", "redes", (), True),
    ("oficina.chefe", "Wagner Siqueira Borges", "oficina", (Papel.CHEFE_SETOR,), True),
    ("oficina.auxiliar", "Renata Furtado Leal", "oficina", (Papel.AUXILIAR_SETOR,), True),
    ("oficina.eletricista", "Caio Medeiros Barreto", "oficina", (), True),
    ("oficina.mecanico", "Vanessa Coelho Pinheiro", "oficina", (), True),
    ("lab.chefe", "Adriana Xavier Mendonça", "lab", (Papel.CHEFE_SETOR,), True),
    ("lab.auxiliar", "Leonardo Brandão Guedes", "lab", (Papel.AUXILIAR_SETOR,), True),
    ("lab.tecnico.01", "Simone Tavares Cordeiro", "lab", (), True),
    ("lab.tecnico.02", "Otávio Rangel Bastos", "lab", (), True),
    ("adm.chefe", "Marta Figueiredo Sampaio", "adm", (Papel.CHEFE_SETOR,), True),
    ("adm.auxiliar", "Daniel Ribeiro Fontes", "adm", (Papel.AUXILIAR_SETOR,), True),
    ("auditor", "Isabel Cavalcanti Duarte", "adm", (Papel.AUDITOR,), True),
    ("administrador", "Henrique Valadares Neto", "adm", (Papel.ADMINISTRADOR_SISTEMA,), True),
    ("obras.chefe.inativo", "Cássio Mourão Telles", "obras", (Papel.CHEFE_SETOR,), False),
    ("obras.tecnico.inativo", "Nádia Esteves Prates", "obras", (), False),
)

# Conta do seed que o login simulado (`contas/login_simulado.py`) autentica para cada papel.
# É uma conta real, com exatamente os papéis acima: a autorização continua sendo a das rotas.
CONTA_POR_PAPEL = {
    "requisitante": "requisitante",
    "auxiliar-setor": "eta.auxiliar",
    "chefe-setor": "eta.chefe",
    "funcionario-almoxarifado": "funcionario",
    "chefe-almoxarifado": "chefe",
    "auditor": "auditor",
    "administrador-sistema": "administrador",
}


def _linha(registro: RegistroAceito) -> str:
    return ";".join(
        (
            registro.cadpro,
            registro.descricao,
            registro.unidade,
            str(registro.quantidade).replace(".", ","),
            registro.detalhamento,
            registro.grupo,
            registro.subgrupo,
            registro.nome_grupo,
            registro.nome_subgrupo,
            "",
        )
    )


def revisao_simulada(registros: tuple[RegistroAceito, ...]) -> bytes:
    """Produz histórico dos 7 campos, divergências e dos 11 motivos de recusa.

    Depois desta revisão o comando reimporta o arquivo original completo,
    restaurando os campos do SCPI e preservando os saldos (INV-STOCK-002/003).
    A revisão é propositalmente parcial para demonstrar materiais ausentes.
    """
    # Evita duplicidade acidental entre amostra aceita e códigos de recusa.
    candidatos = [r for r in registros if not r.cadpro.startswith("999.999.")]
    if not candidatos:
        raise ValueError("O catálogo precisa de material fora dos códigos 999.999.*.")
    primeiro = candidatos[0]
    alterado = replace(
        primeiro,
        descricao=primeiro.descricao + " [SIMULAÇÃO DEV]",
        unidade=primeiro.unidade + "-DEV",
        detalhamento=primeiro.detalhamento + "\nRevisão simulada para desenvolvimento local.",
        grupo=primeiro.grupo + "-DEV",
        subgrupo=primeiro.subgrupo + "-DEV",
        nome_grupo=primeiro.nome_grupo + " [SIMULAÇÃO DEV]",
        nome_subgrupo=primeiro.nome_subgrupo + " [SIMULAÇÃO DEV]",
    )
    amostra = {primeiro.cadpro: alterado}
    positivo = next((r for r in candidatos if r.quantidade > 0), None)
    if positivo is not None:
        amostra[positivo.cadpro] = replace(
            amostra.get(positivo.cadpro, positivo),
            quantidade=positivo.quantidade - min(Decimal("1.000"), positivo.quantidade),
        )
    aumento = next(
        (r for r in candidatos if r is not positivo and r.quantidade < Decimal("999999999998.999")),
        None,
    )
    if aumento is not None:
        amostra[aumento.cadpro] = replace(
            amostra.get(aumento.cadpro, aumento), quantidade=aumento.quantidade + Decimal("1.250")
        )

    def recusada(codigo, *, descricao="Registro simulado inválido", unidade="UN", saldo="1"):
        return f"{codigo};{descricao};{unidade};{saldo};Simulação DEV;999;999;DEV;DEV;"

    linhas = [
        ";".join((*COLUNAS_OBRIGATORIAS, "")),
        "Continuação simulada sem registro anterior",
        *(_linha(registro) for registro in amostra.values()),
        "999.999.001;Registro simulado truncado",
        recusada(""),
        recusada("CODIGO-DEV-INVALIDO"),
        recusada("999.999.002"),
        recusada("999.999.002"),
        recusada("999.999.003", descricao=""),
        recusada("999.999.004", unidade=""),
        recusada("999.999.005", saldo=""),
        recusada("999.999.006", saldo="não informado"),
        recusada("999.999.007", saldo="-2,500"),
        recusada("999.999.008", saldo="1000000000000"),
    ]
    return ("\n".join(linhas) + "\n").encode("utf-8")
