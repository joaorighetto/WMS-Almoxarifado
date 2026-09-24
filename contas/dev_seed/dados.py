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

# Matrícula, setor, papéis adicionais ao REQUISITANTE, conta ativa.
# A conta técnica admin é criada separadamente e não recebe nenhum ROLE-*.
USUARIOS = (
    ("chefe", "almox", (
        Papel.CHEFE_SETOR, Papel.FUNCIONARIO_ALMOXARIFADO, Papel.CHEFE_ALMOXARIFADO,
    ), True),
    ("funcionario", "almox", (Papel.FUNCIONARIO_ALMOXARIFADO,), True),
    ("requisitante", "almox", (), True),
    ("almox.conferente", "almox", (Papel.FUNCIONARIO_ALMOXARIFADO,), True),
    ("almox.inativo", "almox", (Papel.FUNCIONARIO_ALMOXARIFADO,), False),
    ("eta.chefe", "eta", (Papel.CHEFE_SETOR,), True),
    ("eta.auxiliar", "eta", (Papel.AUXILIAR_SETOR,), True),
    ("eta.operador.01", "eta", (), True),
    ("eta.operador.02", "eta", (), True),
    ("ete.chefe", "ete", (Papel.CHEFE_SETOR,), True),
    ("ete.auxiliar", "ete", (Papel.AUXILIAR_SETOR,), True),
    ("ete.operador.01", "ete", (), True),
    ("ete.operador.02", "ete", (), True),
    ("redes.chefe", "redes", (Papel.CHEFE_SETOR,), True),
    ("redes.auxiliar", "redes", (Papel.AUXILIAR_SETOR,), True),
    ("redes.encanador.01", "redes", (), True),
    ("redes.encanador.02", "redes", (), True),
    ("oficina.chefe", "oficina", (Papel.CHEFE_SETOR,), True),
    ("oficina.auxiliar", "oficina", (Papel.AUXILIAR_SETOR,), True),
    ("oficina.eletricista", "oficina", (), True),
    ("oficina.mecanico", "oficina", (), True),
    ("lab.chefe", "lab", (Papel.CHEFE_SETOR,), True),
    ("lab.auxiliar", "lab", (Papel.AUXILIAR_SETOR,), True),
    ("lab.tecnico.01", "lab", (), True),
    ("lab.tecnico.02", "lab", (), True),
    ("adm.chefe", "adm", (Papel.CHEFE_SETOR,), True),
    ("adm.auxiliar", "adm", (Papel.AUXILIAR_SETOR,), True),
    ("auditor", "adm", (Papel.AUDITOR,), True),
    ("administrador", "adm", (Papel.ADMINISTRADOR_SISTEMA,), True),
    ("obras.chefe.inativo", "obras", (Papel.CHEFE_SETOR,), False),
    ("obras.tecnico.inativo", "obras", (), False),
)


def _linha(registro: RegistroAceito) -> str:
    return ";".join((
        registro.cadpro, registro.descricao, registro.unidade,
        str(registro.quantidade).replace(".", ","), registro.detalhamento,
        registro.grupo, registro.subgrupo, registro.nome_grupo, registro.nome_subgrupo, "",
    ))


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
    aumento = next((
        r for r in candidatos
        if r is not positivo and r.quantidade < Decimal("999999999998.999")
    ), None)
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
