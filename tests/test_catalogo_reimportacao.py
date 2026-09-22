"""Testes de reconciliação/reimportação do catálogo (T041, US4 — Fase 6 de
`specs/001-importacao-catalogo-materiais/`).

Escritos ANTES de `T044`/`T045` (extensão de `calcular_plano`/`aplicar_plano`
em `catalogo/importacao.py`). Hoje `Atualizacao.alteracoes` e
`plano.divergencias` ficam sempre vazios e `total_atualizados_com_alteracao`/
`total_divergencias`/`total_ausentes_no_arquivo` ficam em zero (ver docstring
de `catalogo/importacao.py`) — por isso a maioria destes testes deve FALHAR
até `T044`/`T045` existirem, não por erro de teste.

Cobre US4 cenários 1–5 de `spec.md`, sempre chamando `calcular_plano`/
`aplicar_plano` diretamente (como `tests/test_catalogo_importacao.py`), nunca
via `Client`/views. Não cobre:
- atomicidade/concorrência/rollback da reimportação:
  `tests/test_catalogo_atomicidade.py` (T042);
- views (prévia/detalhe): `tests/test_catalogo_views_importacao.py` (T043).

Invariantes/requisitos protegidos: `INV-STOCK-002` (saldo nunca sobrescrito
por reimportação), `INV-STOCK-003` (divergência é informativa),
`INV-CATALOG-004` (autoridade cadastral do SCPI), `INV-MOV-002` (saldo
inicial/execução de origem imutáveis).

`tests/fixtures/catalogo/reimportacao.csv` (ver README da pasta) reimporta os
9 códigos de `carga_inicial_valida.csv` com variações deliberadas por
código — cada teste abaixo referencia o `CADPRO` exato descrito no README
para não duplicar a tabela aqui. Totais esperados da reimportação:
`recebidos=9`, `inseridos=1` (`070.080.090`, novo), `atualizados=8`,
`atualizados_com_alteracao=4`, `rejeitados=0`, `divergencias=1`
(`010.020.031`), `total_ausentes_no_arquivo=1` (`010.020.032`),
`AlteracaoCadastralMaterial` = 10 no total.
"""

import uuid
from decimal import Decimal

import pytest
from django.db import transaction

from catalogo.leitura_scpi import normalizar_para_busca
from catalogo.models import (
    CAMPOS_CADASTRAIS_ATUALIZAVEIS,
    AlteracaoCadastralMaterial,
    DivergenciaSaldo,
    ExcecaoImportacao,
    Material,
    MotivoRecusa,
)

# ---------------------------------------------------------------------------
# Helpers de montagem de arquivo — mesma abordagem de
# tests/test_catalogo_importacao.py, duplicada deliberadamente (cada arquivo
# de teste fica independente dos demais).
# ---------------------------------------------------------------------------

BOM = "﻿"
CABECALHO_MINIMO = "CADPRO;DISC1;UNID1;QUAN3;DISCR1;GRUPO;SUBGRUPO;NOMEGRUPO;NOMESUBGRUPO;"


def _linha(cadpro="", disc1="", unid1="", quan3="", discr1="", grupo="", subgrupo="",
           nomegrupo="", nomesubgrupo=""):
    valores = [cadpro, disc1, unid1, quan3, discr1, grupo, subgrupo, nomegrupo, nomesubgrupo]
    return ";".join(valores) + ";"


def _arquivo(*linhas_dados, cabecalho=CABECALHO_MINIMO, bom=True, quebra="\r\n"):
    texto = quebra.join([cabecalho, *linhas_dados])
    if bom:
        texto = BOM + texto
    return texto.encode("utf-8")


@pytest.fixture
def importacao():
    """Módulo `catalogo.importacao`, importado dentro do fixture — os campos
    de US4 (`T044`/`T045`) ainda não existem em `calcular_plano`/
    `aplicar_plano`."""
    import catalogo.importacao as modulo

    return modulo


@pytest.fixture
def importar(importacao):
    """`importar(conteudo, usuario, nome_arquivo=...) -> (plano, execucao)` —
    `calcular_plano` seguido de `aplicar_plano`, dentro de uma transação
    aberta pelo próprio teste (contrato de `aplicar_plano`)."""

    def _importar(conteudo, usuario, nome_arquivo="carga.csv"):
        with transaction.atomic():
            plano = importacao.calcular_plano(conteudo)
            execucao = importacao.aplicar_plano(
                plano,
                usuario=usuario,
                token_previa=str(uuid.uuid4()),
                nome_arquivo=nome_arquivo,
                tamanho_arquivo=len(conteudo),
            )
        return plano, execucao

    return _importar


@pytest.fixture
def catalogo_reimportado(chefe_almoxarifado, csv_fixture, importar):
    """Catálogo criado por `carga_inicial_valida.csv` e reimportado por
    `reimportacao.csv` (README de `tests/fixtures/catalogo/`). Usado pelos
    testes que exercitam a mesma reimportação de ângulos diferentes, para não
    repetir os dois `importar()` em cada teste."""
    conteudo_inicial = csv_fixture("carga_inicial_valida.csv")
    _, execucao_inicial = importar(conteudo_inicial, chefe_almoxarifado, nome_arquivo="inicial.csv")

    conteudo_reimportacao = csv_fixture("reimportacao.csv")
    plano, execucao = importar(
        conteudo_reimportacao, chefe_almoxarifado, nome_arquivo="reimportacao.csv"
    )
    return {
        "execucao_inicial": execucao_inicial,
        "plano": plano,
        "execucao": execucao,
    }


# ---------------------------------------------------------------------------
# US4 cenários 1–5 e totais da reimportação completa.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_reimportacao_produz_os_totais_documentados_no_readme_da_fixture(catalogo_reimportado):
    """US4 cenários 1, 3, 4, 5: totais da reimportação batem com o README de
    `tests/fixtures/catalogo/` — 1 inserido, 8 atualizados (4 com alteração),
    0 rejeitados, 1 divergência, 1 ausente."""
    execucao = catalogo_reimportado["execucao"]

    assert execucao.total_recebidos == 9
    assert execucao.total_inseridos == 1
    assert execucao.total_atualizados == 8
    assert execucao.total_atualizados_com_alteracao == 4
    assert execucao.total_rejeitados == 0
    assert execucao.total_divergencias == 1
    assert execucao.total_ausentes_no_arquivo == 1

    assert AlteracaoCadastralMaterial.objects.filter(execucao=execucao).count() == 10
    assert DivergenciaSaldo.objects.filter(execucao=execucao).count() == 1


@pytest.mark.django_db
def test_material_novo_e_inserido_com_saldo_do_arquivo_sem_divergencia(catalogo_reimportado):
    """US4 cenário 4: `070.080.090` não existia — é inserido normalmente e
    não gera divergência nem alteração cadastral (não é reimportação para
    ele)."""
    execucao = catalogo_reimportado["execucao"]
    novo = Material.objects.get(cadpro="070.080.090")

    assert novo.saldo == novo.saldo_inicial == Decimal("20.000")
    assert novo.execucao_origem_id == execucao.pk
    assert not DivergenciaSaldo.objects.filter(material=novo).exists()
    assert not AlteracaoCadastralMaterial.objects.filter(material=novo).exists()


@pytest.mark.django_db
def test_cadpro_saldo_inicial_e_execucao_origem_de_existentes_nunca_mudam(catalogo_reimportado):
    """`INV-MOV-002`: para todo material já existente antes da reimportação,
    `cadpro`, `saldo_inicial` e `execucao_origem` continuam apontando para a
    execução original, mesmo quando o cadastro foi atualizado."""
    execucao_inicial = catalogo_reimportado["execucao_inicial"]
    codigos_preexistentes = [
        "000.000.002", "010.020.030", "010.020.031", "010.020.032",
        "010.020.033", "000.029.742", "010.020.034", "010.020.035", "004.001.002",
    ]
    for cadpro in codigos_preexistentes:
        material = Material.objects.get(cadpro=cadpro)
        assert material.cadpro == cadpro
        assert material.execucao_origem_id == execucao_inicial.pk, cadpro


@pytest.mark.django_db
def test_saldo_nunca_e_sobrescrito_mesmo_havendo_divergencia(catalogo_reimportado):
    """SC-009, `INV-STOCK-002`: `010.020.031` tinha saldo 10 e o arquivo de
    reimportação traz 15 — o saldo no WMS permanece 10."""
    material = Material.objects.get(cadpro="010.020.031")
    assert material.saldo == Decimal("10.000")
    assert material.saldo_inicial == Decimal("10.000")


@pytest.mark.django_db
def test_divergencia_registrada_com_saldo_wms_arquivo_e_diferenca_corretos(catalogo_reimportado):
    """US4 cenário 3, FR-029: a divergência de `010.020.031` traz os dois
    valores e `diferenca = saldo_arquivo - saldo_wms` com o sinal certo."""
    execucao = catalogo_reimportado["execucao"]
    material = Material.objects.get(cadpro="010.020.031")

    divergencia = DivergenciaSaldo.objects.get(execucao=execucao, material=material)
    assert divergencia.saldo_wms == Decimal("10.000")
    assert divergencia.saldo_arquivo == Decimal("15.000")
    assert divergencia.diferenca == Decimal("5.000")

    # Mesma divergência também aparece no plano (contrato interno).
    divergencia_plano = next(
        d for d in catalogo_reimportado["plano"].divergencias if d.cadpro == "010.020.031"
    )
    assert divergencia_plano.saldo_wms == Decimal("10.000")
    assert divergencia_plano.saldo_arquivo == Decimal("15.000")
    assert divergencia_plano.diferenca == Decimal("5.000")


@pytest.mark.django_db
def test_material_sem_mudanca_nao_gera_alteracao_nem_conta_em_atualizados_com_alteracao(
    catalogo_reimportado,
):
    """US4 cenário 2 (saldo igual → sem divergência) e edge case "nada
    muda": `010.020.030`, `010.020.034` e `004.001.002` são recontados em
    `atualizados`, mas não em `atualizados_com_alteracao`, sem nenhuma
    `AlteracaoCadastralMaterial` nem `DivergenciaSaldo`."""
    execucao = catalogo_reimportado["execucao"]
    codigos_sem_mudanca = ["010.020.030", "010.020.034", "004.001.002"]

    for cadpro in codigos_sem_mudanca:
        material = Material.objects.get(cadpro=cadpro)
        assert not AlteracaoCadastralMaterial.objects.filter(
            execucao=execucao, material=material
        ).exists(), cadpro
        assert not DivergenciaSaldo.objects.filter(
            execucao=execucao, material=material
        ).exists(), cadpro


@pytest.mark.django_db
def test_alteracao_cadastral_por_campo_com_valor_anterior_e_novo_exatos(catalogo_reimportado):
    """FR-032: cada campo cadastral alterado vira uma linha própria, com o
    valor anterior e o novo exatos (byte a byte, inclusive multilinha)."""
    execucao = catalogo_reimportado["execucao"]

    parafuso = Material.objects.get(cadpro="000.000.002")
    alteracao_descricao = AlteracaoCadastralMaterial.objects.get(
        execucao=execucao, material=parafuso, campo="descricao"
    )
    assert alteracao_descricao.valor_anterior == "PARAFUSO SEXTAVADO M8"
    assert alteracao_descricao.valor_novo == "PARAFUSO SEXTAVADO M8 ZINCADO"
    assert not DivergenciaSaldo.objects.filter(execucao=execucao, material=parafuso).exists()

    cabo = Material.objects.get(cadpro="010.020.033")
    alteracao_unidade = AlteracaoCadastralMaterial.objects.get(
        execucao=execucao, material=cabo, campo="unidade"
    )
    assert alteracao_unidade.valor_anterior == "MTS"
    assert alteracao_unidade.valor_novo == "M"

    valvula = Material.objects.get(cadpro="010.020.035")
    alteracao_detalhamento = AlteracaoCadastralMaterial.objects.get(
        execucao=execucao, material=valvula, campo="detalhamento"
    )
    assert alteracao_detalhamento.valor_anterior == "Observação técnica\n\nlinha adicional"
    assert alteracao_detalhamento.valor_novo == "Revisado"


@pytest.mark.django_db
def test_material_com_todos_os_sete_campos_alterados_gera_sete_alteracoes_ordenadas(
    catalogo_reimportado,
):
    """`000.029.742` muda os 7 campos cadastrais de uma vez — uma linha por
    campo, e `Atualizacao.alteracoes` do plano vem ordenada por campo
    (`interface-importacao.md`)."""
    execucao = catalogo_reimportado["execucao"]
    anel = Material.objects.get(cadpro="000.029.742")

    alteracoes = {
        a.campo: (a.valor_anterior, a.valor_novo)
        for a in AlteracaoCadastralMaterial.objects.filter(execucao=execucao, material=anel)
    }
    assert set(alteracoes) == set(CAMPOS_CADASTRAIS_ATUALIZAVEIS)
    assert alteracoes["descricao"] == ("ANEL DE VEDACAO VITON", "ANEL DE VEDACAO NBR")
    assert alteracoes["unidade"] == ("UN", "PC")
    assert alteracoes["grupo"] == ("050", "051")
    assert alteracoes["subgrupo"] == ("060", "061")
    assert alteracoes["nome_grupo"] == ("VEDACAO", "VEDACOES")
    assert alteracoes["nome_subgrupo"] == ("ANEIS", "ANEIS DE BORRACHA")
    assert alteracoes["detalhamento"] == ("COMPOSTO VITON", "COMPOSTO NBR")
    assert not DivergenciaSaldo.objects.filter(execucao=execucao, material=anel).exists()

    atualizacao_plano = next(
        a for a in catalogo_reimportado["plano"].atualizacoes if a.cadpro == "000.029.742"
    )
    assert len(atualizacao_plano.alteracoes) == 7
    campos_no_plano = [campo for campo, _antes, _novo in atualizacao_plano.alteracoes]
    assert campos_no_plano == sorted(campos_no_plano), (
        "Atualizacao.alteracoes precisa vir ordenada por campo (contrato fixo)"
    )


@pytest.mark.django_db
def test_descricao_busca_e_atualizada_junto_com_descricao(catalogo_reimportado):
    """`descricao_busca` é derivado técnico de `descricao` (R15) e precisa
    ser reescrito na mesma reimportação que muda `descricao`."""
    parafuso = Material.objects.get(cadpro="000.000.002")
    assert parafuso.descricao_busca == normalizar_para_busca("PARAFUSO SEXTAVADO M8 ZINCADO")


@pytest.mark.django_db
def test_material_ausente_do_arquivo_nao_e_alterado_nem_excluido(catalogo_reimportado):
    """FR-031: `010.020.032` não está em `reimportacao.csv` — continua
    existindo, com o cadastro e o saldo de `carga_inicial_valida.csv`, e
    conta como o único ausente."""
    execucao = catalogo_reimportado["execucao"]
    execucao_inicial = catalogo_reimportado["execucao_inicial"]

    material = Material.objects.get(cadpro="010.020.032")
    assert material.descricao == "MANGUEIRA HIDRAULICA 3/8"
    assert material.unidade == "MT"
    assert material.saldo == material.saldo_inicial == Decimal("1234.500")
    assert material.execucao_origem_id == execucao_inicial.pk

    assert not AlteracaoCadastralMaterial.objects.filter(material=material).exists()
    assert not DivergenciaSaldo.objects.filter(material=material).exists()
    assert execucao.total_ausentes_no_arquivo == 1


# ---------------------------------------------------------------------------
# Reexecução do mesmo arquivo sem alterações — edge case "reexecução do
# mesmo arquivo sem alterações: nenhuma divergência e nenhum dado alterado".
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_reimportar_o_mesmo_arquivo_sem_mudancas_zera_alteracao_e_divergencia(
    chefe_almoxarifado, csv_fixture, importar
):
    conteudo = csv_fixture("carga_inicial_valida.csv")
    _, execucao_inicial = importar(conteudo, chefe_almoxarifado, nome_arquivo="inicial.csv")

    snapshot_antes = {
        m.cadpro: (m.descricao, m.unidade, m.detalhamento, m.grupo, m.subgrupo,
                   m.nome_grupo, m.nome_subgrupo, m.saldo)
        for m in Material.objects.all()
    }

    plano, execucao_repetida = importar(conteudo, chefe_almoxarifado, nome_arquivo="repetido.csv")

    assert execucao_repetida.total_inseridos == 0
    assert execucao_repetida.total_atualizados == 9
    assert execucao_repetida.total_atualizados_com_alteracao == 0
    assert execucao_repetida.total_divergencias == 0
    assert execucao_repetida.total_ausentes_no_arquivo == 0
    assert not AlteracaoCadastralMaterial.objects.filter(execucao=execucao_repetida).exists()
    assert not DivergenciaSaldo.objects.filter(execucao=execucao_repetida).exists()

    snapshot_depois = {
        m.cadpro: (m.descricao, m.unidade, m.detalhamento, m.grupo, m.subgrupo,
                   m.nome_grupo, m.nome_subgrupo, m.saldo)
        for m in Material.objects.all()
    }
    assert snapshot_depois == snapshot_antes
    assert Material.objects.filter(execucao_origem=execucao_inicial).count() == 9


# ---------------------------------------------------------------------------
# Recusado não conta como ausente, nem gera divergência/atualização — a
# definição de "ausente" (R11) é sobre CADPRO bem formado no arquivo, aceito
# OU recusado.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_registro_recusado_na_reimportacao_nao_gera_divergencia_atualizacao_nem_ausente(
    chefe_almoxarifado, importar
):
    conteudo_inicial = _arquivo(
        _linha(cadpro="050.050.050", disc1="ITEM ORIGINAL", unid1="UN", quan3="5")
    )
    importar(conteudo_inicial, chefe_almoxarifado, nome_arquivo="inicial.csv")

    # CADPRO bem formado, mas quantidade negativa -> recusado. O registro
    # "aparece" no arquivo (R11), então o material NÃO deve contar como
    # ausente, mesmo tendo sido recusado.
    conteudo_reimportacao = _arquivo(
        _linha(cadpro="050.050.050", disc1="ITEM ORIGINAL MODIFICADO", unid1="UN", quan3="-5")
    )
    plano, execucao = importar(
        conteudo_reimportacao, chefe_almoxarifado, nome_arquivo="reimportacao.csv"
    )

    assert execucao.total_rejeitados == 1
    assert execucao.total_atualizados == 0
    assert execucao.total_ausentes_no_arquivo == 0, (
        "CADPRO bem formado, mesmo recusado, conta como presente no arquivo (R11)"
    )
    excecao = ExcecaoImportacao.objects.get(execucao=execucao)
    assert excecao.motivo == MotivoRecusa.QUANTIDADE_NEGATIVA
    assert excecao.cadpro == "050.050.050"

    material = Material.objects.get(cadpro="050.050.050")
    assert material.descricao == "ITEM ORIGINAL"
    assert material.saldo == Decimal("5.000")
    assert not AlteracaoCadastralMaterial.objects.filter(material=material).exists()
    assert not DivergenciaSaldo.objects.filter(material=material).exists()


# ---------------------------------------------------------------------------
# Sinal da diferença: caso isolado com diferença negativa (saldo do arquivo
# menor que o saldo do WMS).
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_divergencia_com_diferenca_negativa_tem_sinal_correto(chefe_almoxarifado, importar):
    conteudo_inicial = _arquivo(
        _linha(cadpro="060.070.080", disc1="ITEM SALDO ALTO", unid1="UN", quan3="20")
    )
    importar(conteudo_inicial, chefe_almoxarifado, nome_arquivo="inicial.csv")

    conteudo_reimportacao = _arquivo(
        _linha(cadpro="060.070.080", disc1="ITEM SALDO ALTO", unid1="UN", quan3="15")
    )
    plano, execucao = importar(
        conteudo_reimportacao, chefe_almoxarifado, nome_arquivo="reimportacao.csv"
    )

    material = Material.objects.get(cadpro="060.070.080")
    divergencia = DivergenciaSaldo.objects.get(execucao=execucao, material=material)
    assert divergencia.saldo_wms == Decimal("20.000")
    assert divergencia.saldo_arquivo == Decimal("15.000")
    assert divergencia.diferenca == Decimal("-5.000")
    assert material.saldo == Decimal("20.000"), "saldo nunca é sobrescrito, mesmo em queda"


# ---------------------------------------------------------------------------
# Alteração cadastral E divergência de saldo no MESMO material — combinação
# ausente de `reimportacao.csv` (lá quem muda cadastro tem saldo igual ao do
# arquivo, e quem diverge não muda cadastro). Sem este teste, um `saldo`
# indevido no `bulk_update` de `aplicar_plano` (`catalogo/importacao.py`)
# passaria despercebido: nenhum material do README exercita as duas
# condições ao mesmo tempo (`INV-STOCK-002`, `INV-STOCK-003`, `INV-MOV-002`,
# SC-009).
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_alteracao_cadastral_e_divergencia_de_saldo_juntas_nao_sobrescrevem_saldo(
    chefe_almoxarifado, importar
):
    """Material com mudança cadastral (`descricao`) e, ao mesmo tempo, saldo
    do arquivo diferente do saldo atual do WMS (que já havia sido movimentado
    por uma operação de estoque, fora da importação). A reimportação deve:
    atualizar só o cadastro; registrar a divergência com os valores exatos;
    manter `saldo` no valor movimentado (nem o do arquivo, nem o inicial);
    manter `saldo_inicial`/`execucao_origem` intactos (`INV-MOV-002`)."""
    conteudo_inicial = _arquivo(
        _linha(cadpro="080.090.100", disc1="ITEM MISTO", unid1="UN", quan3="20")
    )
    _, execucao_inicial = importar(conteudo_inicial, chefe_almoxarifado, nome_arquivo="inicial.csv")

    # Movimentação de estoque real, fora da importação (ex.: saída de
    # material) — simulada diretamente no banco, como no quickstart §4.
    Material.objects.filter(cadpro="080.090.100").update(saldo=Decimal("12.000"))

    # Reimportação do mesmo CADPRO: descrição diferente (mudança cadastral)
    # E quantidade diferente tanto do saldo inicial (20) quanto do saldo
    # movimentado (12) — a terceira quantidade força a divergência a ficar
    # visível independentemente de qual dos dois saldos anteriores o código
    # usasse por engano.
    conteudo_reimportacao = _arquivo(
        _linha(cadpro="080.090.100", disc1="ITEM MISTO REVISADO", unid1="UN", quan3="30")
    )
    plano, execucao = importar(
        conteudo_reimportacao, chefe_almoxarifado, nome_arquivo="reimportacao.csv"
    )

    material = Material.objects.get(cadpro="080.090.100")

    # `INV-STOCK-002`/SC-009: saldo permanece o movimentado, nunca o do
    # arquivo nem o inicial.
    assert material.saldo == Decimal("12.000")
    # `INV-MOV-002`: saldo de origem e execução de origem nunca mudam.
    assert material.saldo_inicial == Decimal("20.000")
    assert material.execucao_origem_id == execucao_inicial.pk

    # Cadastro atualizado normalmente.
    assert material.descricao == "ITEM MISTO REVISADO"
    assert material.descricao_busca == normalizar_para_busca("ITEM MISTO REVISADO")

    alteracao = AlteracaoCadastralMaterial.objects.get(
        execucao=execucao, material=material, campo="descricao"
    )
    assert alteracao.valor_anterior == "ITEM MISTO"
    assert alteracao.valor_novo == "ITEM MISTO REVISADO"

    divergencia = DivergenciaSaldo.objects.get(execucao=execucao, material=material)
    assert divergencia.saldo_wms == Decimal("12.000")
    assert divergencia.saldo_arquivo == Decimal("30.000")
    assert divergencia.diferenca == Decimal("18.000")

    assert execucao.total_atualizados == 1
    assert execucao.total_atualizados_com_alteracao == 1
    assert execucao.total_divergencias == 1
    assert plano.total_atualizados_com_alteracao == 1
    assert plano.total_divergencias == 1


@pytest.mark.django_db
def test_aplicar_plano_recusa_campo_indevido_no_bulk_update(chefe_almoxarifado, importar):
    """Guarda explícita de `aplicar_plano` (`INV-STOCK-002`/`INV-STOCK-003`/
    `INV-CATALOG-004`): se, por qualquer razão, um campo fora de
    `CAMPOS_CADASTRAIS_ATUALIZAVEIS ∪ {"descricao_busca"}` chegar à lista do
    `bulk_update` (ex.: `saldo`), `aplicar_plano` levanta `RuntimeError` em
    vez de gravar. Simulado injetando um `Atualizacao` cujo campo alterado é
    `"saldo"`, o que nenhum fluxo real de `calcular_plano` produz."""
    import catalogo.importacao as modulo

    conteudo_inicial = _arquivo(
        _linha(cadpro="090.100.110", disc1="ITEM GUARDA", unid1="UN", quan3="7")
    )
    importar(conteudo_inicial, chefe_almoxarifado, nome_arquivo="inicial.csv")

    conteudo_modificado = _arquivo(
        _linha(cadpro="090.100.110", disc1="ITEM GUARDA MODIFICADO", unid1="UN", quan3="7")
    )
    plano_original = modulo.calcular_plano(conteudo_modificado)
    atualizacao_real = next(
        a for a in plano_original.atualizacoes if a.cadpro == "090.100.110"
    )
    assert atualizacao_real.alteracoes, "pré-condição: precisa haver ao menos uma alteração real"

    # Substitui o nome do campo por "saldo", mantendo o resto do contrato de
    # `Atualizacao` intacto — exercita só a guarda de `aplicar_plano`, sem
    # depender de nenhum caminho real de `calcular_plano` produzir isso.
    campo, valor_anterior, valor_novo = atualizacao_real.alteracoes[0]
    atualizacao_maliciosa = modulo.Atualizacao(
        material_id=atualizacao_real.material_id,
        cadpro=atualizacao_real.cadpro,
        registro=atualizacao_real.registro,
        alteracoes=(("saldo", valor_anterior, valor_novo),),
    )
    plano_malicioso = modulo.PlanoImportacao(
        **{**plano_original.__dict__, "atualizacoes": (atualizacao_maliciosa,)}
    )

    with transaction.atomic():
        with pytest.raises(RuntimeError, match="saldo"):
            modulo.aplicar_plano(
                plano_malicioso,
                usuario=chefe_almoxarifado,
                token_previa=str(uuid.uuid4()),
                nome_arquivo="malicioso.csv",
                tamanho_arquivo=1,
            )
        transaction.set_rollback(True)

    # Nada foi gravado: nem alteração cadastral, nem mudança de saldo.
    material = Material.objects.get(cadpro="090.100.110")
    assert material.descricao == "ITEM GUARDA"
    assert material.saldo == Decimal("7.000")
    assert not AlteracaoCadastralMaterial.objects.filter(material=material).exists()


# ---------------------------------------------------------------------------
# Divergência persistente: reaparece em cada execução, ligada à sua (FR-030).
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_divergencia_persistente_reaparece_em_cada_execucao_ligada_a_sua(
    catalogo_reimportado, chefe_almoxarifado, csv_fixture, importar
):
    """`010.020.031` continua com saldo 10 e o mesmo arquivo continua
    trazendo 15 — uma nova reimportação idêntica precisa registrar uma NOVA
    `DivergenciaSaldo`, ligada à execução que a detectou, sem sobrescrever a
    anterior (FR-030)."""
    execucao_2 = catalogo_reimportado["execucao"]
    material = Material.objects.get(cadpro="010.020.031")
    divergencia_2 = DivergenciaSaldo.objects.get(execucao=execucao_2, material=material)

    conteudo_reimportacao = csv_fixture("reimportacao.csv")
    _, execucao_3 = importar(
        conteudo_reimportacao, chefe_almoxarifado, nome_arquivo="reimportacao-de-novo.csv"
    )

    divergencia_3 = DivergenciaSaldo.objects.get(execucao=execucao_3, material=material)
    assert divergencia_3.pk != divergencia_2.pk
    assert divergencia_3.saldo_wms == Decimal("10.000")
    assert divergencia_3.saldo_arquivo == Decimal("15.000")
    assert divergencia_3.diferenca == Decimal("5.000")
    assert DivergenciaSaldo.objects.filter(material=material).count() == 2
    assert material.saldo == Decimal("10.000"), "ainda não sobrescrito pela terceira execução"
