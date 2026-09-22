"""Validação contra o arquivo real do SCPI (T049, Fase 7 — Polish, de
`specs/001-importacao-catalogo-materiais/`).

Aceite pendente de SC-001, SC-002, SC-004 e SC-008 (ROADMAP, "Evidências de
importação"), documentado em `quickstart.md` §5. O export real não é
versionado — hoje existe só localmente em
`docs/domain-legacy/relacao-de-todos-produtos-importados-do-SCPI.csv`,
ignorado pelo Git. Este teste lê **só o caminho** da variável de ambiente
`SCPI_CSV_REAL`; sem ela, é *skipped*. Nenhum dado do arquivo é escrito em
fixture, snapshot ou mensagem de erro extensa — as asserções comparam
contagens e, no máximo, um código/valor já documentado publicamente em
`quickstart.md` §5.

Sem marcador de "lento": o projeto não define nenhum em
`pyproject.toml`/`pytest.ini`/`setup.cfg` (conferido antes de escrever este
arquivo) — inventar um aqui não o registraria em lugar nenhum.

Chama `calcular_plano`/`aplicar_plano` diretamente, como
`tests/test_catalogo_importacao.py` e `tests/test_catalogo_reimportacao.py`
(sem `Client`/views: o alvo aqui é o pipeline de domínio contra o arquivo
real, não a camada HTTP).
"""

import os
import pathlib
import uuid
from decimal import Decimal

import pytest
from django.db import transaction

from catalogo import importacao, leitura_scpi
from catalogo.models import Material

MOTIVO_SKIP = (
    "arquivo real do SCPI não disponível (aceite pendente — ROADMAP, Evidências de importação)"
)


def _conteudo_do_arquivo_real() -> bytes:
    caminho = os.environ.get("SCPI_CSV_REAL")
    if not caminho:
        pytest.skip(MOTIVO_SKIP)
    return pathlib.Path(caminho).read_bytes()


def _cadpros_no_inicio_das_linhas(texto: str) -> set[str]:
    """Conjunto dos `CADPRO` que iniciam uma linha física do arquivo,
    obtido por varredura estrutural independente (não usa
    `leitura_scpi.ler_registros`) — só a regex de formato, já contratada
    por `INV-CATALOG-001` e exaustivamente testada em
    `tests/test_catalogo_leitura_scpi.py`. Serve para conferir, sem
    depender do parser, que todo `CADPRO` persistido é idêntico a um
    `CADPRO` realmente presente no arquivo."""
    candidatos = set()
    for linha in texto.split("\n"):
        primeiro_campo = linha.split(";", 1)[0]
        if leitura_scpi.PADRAO_CADPRO.fullmatch(primeiro_campo):
            candidatos.add(primeiro_campo)
    return candidatos


def _importar(conteudo: bytes, usuario):
    with transaction.atomic():
        plano = importacao.calcular_plano(conteudo)
        execucao = importacao.aplicar_plano(
            plano,
            usuario=usuario,
            token_previa=str(uuid.uuid4()),
            nome_arquivo="scpi_real.csv",
            tamanho_arquivo=len(conteudo),
        )
    return plano, execucao


@pytest.mark.django_db
def test_carga_inicial_e_reimportacao_do_arquivo_real_do_scpi(chefe_almoxarifado):
    """Sobre catálogo vazio, carrega o arquivo real e confere os agregados e
    valores documentados em `quickstart.md` §5; depois reimporta o mesmo
    arquivo e confere que nada além de "atualizados" muda."""
    conteudo = _conteudo_do_arquivo_real()

    _, execucao = _importar(conteudo, chefe_almoxarifado)

    # Agregados esperados (quickstart.md §5): catálogo vazio, nada recusado.
    assert execucao.total_recebidos == 1588
    assert execucao.total_inseridos == 1588
    assert execucao.total_rejeitados == 0
    assert Material.objects.count() == 1588

    # Fidelidade de CADPRO (INV-CATALOG-001): o conjunto persistido é
    # idêntico ao conjunto identificado por uma varredura independente do
    # arquivo (a mensagem de falha mostra só a contagem divergente, nunca os
    # próprios códigos).
    texto = leitura_scpi.decodificar(conteudo)
    cadpros_no_arquivo = _cadpros_no_inicio_das_linhas(texto)
    cadpros_persistidos = set(Material.objects.values_list("cadpro", flat=True))
    diferenca = cadpros_persistidos.symmetric_difference(cadpros_no_arquivo)
    assert not diferenca, f"{len(diferenca)} código(s) CADPRO divergente(s) entre banco e arquivo"

    # `004.001.002`: descrição recomposta de várias linhas físicas — a
    # recomposição junta os fragmentos com "\n"; um registro de linha única
    # nunca teria essa quebra embutida (sem precisar conhecer o texto real).
    material_recomposto = Material.objects.get(cadpro="004.001.002")
    assert "\n" in material_recomposto.descricao, (
        "004.001.002 deveria ter descrição recomposta de mais de uma linha física"
    )

    # Saldo de um código específico, já documentado em quickstart.md §5.
    assert Material.objects.get(cadpro="000.029.742").saldo == Decimal("53.400")

    # Saldo de TODO material igual ao QUAN3 do arquivo, na escala de 3
    # casas. A correção da interpretação de QUAN3 em si já é exaustivamente
    # coberta por tests/test_catalogo_leitura_scpi.py; aqui o alvo é o
    # caminho de escrita ponta a ponta — `aplicar_plano` precisa gravar,
    # para cada um dos 1588 códigos reais, exatamente a quantidade que o
    # parser aceitou.
    quantidade_por_cadpro = {
        registro.cadpro: registro.quantidade
        for registro in leitura_scpi.ler_registros(conteudo).aceitos
    }
    for material in Material.objects.all():
        assert material.saldo == quantidade_por_cadpro[material.cadpro], (
            f"saldo do material {material.cadpro} não corresponde ao QUAN3 do arquivo"
        )
        assert material.saldo_inicial == material.saldo

    # Reimportação imediata do mesmo arquivo (US4/SC-008): só atualização,
    # sem alteração cadastral nem divergência — nada no arquivo mudou.
    _, execucao_2 = _importar(conteudo, chefe_almoxarifado)

    assert execucao_2.total_atualizados == 1588
    assert execucao_2.total_atualizados_com_alteracao == 0
    assert execucao_2.total_divergencias == 0
    assert execucao_2.total_inseridos == 0
    assert execucao_2.total_rejeitados == 0
    assert Material.objects.count() == 1588
