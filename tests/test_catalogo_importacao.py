"""Testes de `calcular_plano`/`aplicar_plano` (T016, US1 — Fase 3 de
`specs/001-importacao-catalogo-materiais/`).

Escritos ANTES da implementação de `catalogo/importacao.py` (T022/T023):
hoje o módulo não existe. Este arquivo deve FALHAR agora, por
`ModuleNotFoundError` ao importar `catalogo.importacao` — mas só dentro dos
fixtures `importacao`/`importar` (ver nota abaixo), nunca na coleta do
arquivo inteiro.

Cobre a carga inicial sobre catálogo vazio (US1, cenários 1–12 de
`spec.md`) e o resultado auditável dela (US3, cenários 1–2), sempre
chamando `calcular_plano`/`aplicar_plano` diretamente, dentro da transação
que o próprio contrato exige do chamador — sem `confirmar_importacao` e sem
views. Não cobre:
- atomicidade/concorrência/rollback: `tests/test_catalogo_atomicidade.py`
  (T017);
- views e sessão da prévia: `tests/test_catalogo_views_importacao.py`
  (T018);
- permissões: `tests/test_catalogo_permissoes.py` (T019);
- reimportação com atualização cadastral e divergência (US4): todo
  `CADPRO` usado aqui é sempre novo, sobre catálogo vazio —
  `tests/test_catalogo_reimportacao.py` (T041).

Invariantes/requisitos protegidos: `INV-CATALOG-001/002/003/005`,
`INV-STOCK-001/002`, `INV-MOV-002` (tasks.md, T016).

Nota sobre importação (requisito da task — "Verificação"):
`catalogo.importacao` ainda não existe como módulo. Um import de nível de
arquivo (`import catalogo.importacao`) levantaria `ModuleNotFoundError` na
fase de coleta e quebraria a coleta do arquivo inteiro. Por isso o import
vive dentro do fixture `importacao` (executado na fase de *setup* de cada
teste que o usa): a ausência do módulo vira um erro de fixture por teste,
não uma falha de coleta — `pytest --collect-only` deste arquivo funciona
normalmente.
"""

import uuid
from decimal import Decimal

import pytest
from django.db import transaction

from catalogo.leitura_scpi import normalizar_para_busca
from catalogo.models import ExcecaoImportacao, Material, MotivoRecusa

# ---------------------------------------------------------------------------
# Helpers de montagem de arquivo — mesma abordagem de
# tests/test_catalogo_leitura_scpi.py, duplicada aqui deliberadamente para
# manter os dois arquivos de teste independentes um do outro.
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
    """Módulo `catalogo.importacao`, importado dentro do fixture (ver nota
    do módulo) — ainda não existe até T022/T023."""
    import catalogo.importacao as modulo

    return modulo


@pytest.fixture
def importar(importacao):
    """`importar(conteudo, usuario, nome_arquivo=...) -> (plano, execucao)`.

    Encapsula exatamente o par que `contracts/interface-importacao.md`
    exige do chamador: `calcular_plano` seguido de `aplicar_plano`, dentro
    de uma transação aberta por quem chama.
    """

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


# ---------------------------------------------------------------------------
# US1 cenários 1–12 (spec.md) — carga sobre catálogo vazio
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_carga_inicial_valida_cria_materiais_fieis_ao_arquivo(
    importar, chefe_almoxarifado, csv_fixture
):
    """Cenários 1, 2, 3, 5, 6, 8, 9, 10, 11, 12: cada material criado com
    `cadpro`, saldo, unidade, classificação e detalhamento idênticos ao
    arquivo; `000.000.002` preserva zeros à esquerda; saldo `0,000` é
    aceito como válido; descrições iguais com códigos distintos geram
    materiais distintos; detalhamento vazio é aceito; unidades diversas
    preservadas sem normalização; classificação gravada como recebida;
    multilinha recomposta sem deslocamento de coluna; aspas literais
    preservadas; ruído de ponto flutuante arredondado para 3 casas.
    """
    conteudo = csv_fixture("carga_inicial_valida.csv")

    plano, execucao = importar(conteudo, chefe_almoxarifado)

    assert Material.objects.count() == 9
    assert execucao.total_recebidos == 9
    assert execucao.total_inseridos == 9
    assert execucao.total_atualizados == 0
    assert execucao.total_rejeitados == 0

    por_cadpro = {m.cadpro: m for m in Material.objects.all()}

    # Cenários 1/2: CADPRO byte a byte, com zeros à esquerda preservados.
    zero_dois = por_cadpro["000.000.002"]
    assert zero_dois.cadpro == "000.000.002"
    # Cenário 3: quantidade "0,000" é saldo zero válido, não erro.
    assert zero_dois.saldo == zero_dois.saldo_inicial == Decimal("0.000")
    assert zero_dois.execucao_origem_id == execucao.pk
    assert zero_dois.descricao_busca == normalizar_para_busca(zero_dois.descricao)

    # Cenário 5: descrições iguais, CADPRO distintos -> materiais distintos.
    arruela_1 = por_cadpro["010.020.030"]
    arruela_2 = por_cadpro["010.020.031"]
    assert arruela_1.descricao == arruela_2.descricao == "ARRUELA LISA 1/4"
    assert arruela_1.pk != arruela_2.pk

    # Cenário 6: detalhamento vazio é aceito normalmente.
    assert zero_dois.detalhamento == ""

    # Cenário 8: unidades preservadas sem normalização.
    assert arruela_1.unidade == "UND"
    assert arruela_2.unidade == "M"
    assert por_cadpro["010.020.032"].unidade == "MT"
    assert por_cadpro["010.020.033"].unidade == "MTS"

    # Cenário 9: classificação gravada como recebida, inclusive vazia.
    assert arruela_1.grupo == arruela_1.subgrupo == ""
    assert arruela_1.nome_grupo == arruela_1.nome_subgrupo == ""
    assert zero_dois.grupo == "010"
    assert zero_dois.subgrupo == "020"
    assert zero_dois.nome_grupo == "FERRAGENS"
    assert zero_dois.nome_subgrupo == "PARAFUSOS"

    # Cenário 10: 004.001.002 recomposto de 3 linhas físicas, sem deslocamento.
    tubo = por_cadpro["004.001.002"]
    assert tubo.descricao == "TUBO DE ACO CARBONO\nSCHEDULE 40\nGALVANIZADO"
    assert tubo.unidade == "UN"
    assert tubo.saldo == Decimal("6.000")
    assert tubo.detalhamento == "CONFORME NBR 5580"

    # Detalhamento multilinha com linha vazia no meio, preservada como \n\n.
    valvula = por_cadpro["010.020.035"]
    assert valvula.detalhamento == "Observação técnica\n\nlinha adicional"
    assert valvula.saldo == Decimal("12.000")

    # Cenário 11: aspas literais preservadas, colunas seguintes alinhadas.
    cotovelo = por_cadpro["010.020.034"]
    assert cotovelo.descricao == 'COTOVELO GALVANIZADO ¾" X 90º'
    assert cotovelo.unidade == "UN"
    assert cotovelo.saldo == Decimal("4.000")

    # Cenário 12: ruído de ponto flutuante arredondado para 3 casas.
    anel = por_cadpro["000.029.742"]
    assert anel.saldo == anel.saldo_inicial == Decimal("53.400")


@pytest.mark.django_db
def test_quantidade_ausente_e_rejeitada_e_nao_vira_saldo_zero(importar, chefe_almoxarifado):
    """Cenário 4: quantidade vazia é recusada e registrada como exceção; o
    saldo nunca é assumido como zero (`INV-STOCK-001`)."""
    linha = _linha(cadpro="030.040.052", disc1="ITEM SEM QUANTIDADE", unid1="UN", quan3="")
    conteudo = _arquivo(linha)

    plano, execucao = importar(conteudo, chefe_almoxarifado)

    assert not Material.objects.filter(cadpro="030.040.052").exists()
    assert execucao.total_rejeitados == 1
    excecao = ExcecaoImportacao.objects.get(execucao=execucao)
    assert excecao.motivo == MotivoRecusa.QUANTIDADE_AUSENTE
    assert excecao.cadpro == "030.040.052"


@pytest.mark.django_db
def test_cadpro_duplicado_nao_importa_nenhuma_ocorrencia(importar, chefe_almoxarifado):
    """Cenário 7: ambas as ocorrências do mesmo CADPRO são recusadas e
    reportadas; nenhuma delas é importada (`INV-CATALOG-002`)."""
    linha1 = _linha(cadpro="090.090.090", disc1="Item um", unid1="UN", quan3="1")
    linha2 = _linha(cadpro="090.090.090", disc1="Item dois", unid1="UN", quan3="2")
    conteudo = _arquivo(linha1, linha2)

    plano, execucao = importar(conteudo, chefe_almoxarifado)

    assert not Material.objects.filter(cadpro="090.090.090").exists()
    assert execucao.total_rejeitados == 2
    motivos = list(
        ExcecaoImportacao.objects.filter(execucao=execucao)
        .order_by("linha_inicial")
        .values_list("motivo", flat=True)
    )
    assert motivos == [
        MotivoRecusa.CADPRO_DUPLICADO_NO_ARQUIVO,
        MotivoRecusa.CADPRO_DUPLICADO_NO_ARQUIVO,
    ]


@pytest.mark.django_db
def test_classificacao_nao_e_derivada_do_cadpro(importar, chefe_almoxarifado):
    """FR-022, FR-024, `INV-CATALOG-005`: `GRUPO`/`SUBGRUPO` gravados são
    exatamente os do arquivo, mesmo quando não coincidem com os dois
    primeiros trios do `CADPRO` — nunca derivados do código."""
    linha = _linha(
        cadpro="010.020.099",
        disc1="ITEM CLASSIFICACAO DIVERGENTE",
        unid1="UN",
        quan3="1",
        grupo="999",
        subgrupo="888",
        nomegrupo="GRUPO DIVERGENTE",
        nomesubgrupo="SUBGRUPO DIVERGENTE",
    )
    conteudo = _arquivo(linha)

    importar(conteudo, chefe_almoxarifado)

    material = Material.objects.get(cadpro="010.020.099")
    assert material.grupo == "999"
    assert material.subgrupo == "888"
    assert material.nome_grupo == "GRUPO DIVERGENTE"
    assert material.nome_subgrupo == "SUBGRUPO DIVERGENTE"


@pytest.mark.django_db
def test_carga_com_erros_gera_totais_e_excecoes_auditaveis(
    importar, chefe_almoxarifado, csv_fixture
):
    """US3 cenários 1–2: totais corretos (`recebidos = inseridos +
    atualizados + rejeitados`, FR-034) e uma `ExcecaoImportacao` por
    recusado, com linha, motivo e `CADPRO` identificável (vazio só em
    `LINHA_NAO_ASSOCIAVEL`, FR-036).

    Totais do arquivo: `recebidos=22`/`inseridos=9`/`rejeitados=13`,
    conforme `tests/fixtures/catalogo/README.md`.
    """
    conteudo = csv_fixture("carga_inicial_casos_spec.csv")

    plano, execucao = importar(conteudo, chefe_almoxarifado)

    assert execucao.total_recebidos == 22
    assert execucao.total_inseridos == 9
    assert execucao.total_atualizados == 0
    assert execucao.total_rejeitados == 13
    assert execucao.total_recebidos == (
        execucao.total_inseridos + execucao.total_atualizados + execucao.total_rejeitados
    )
    assert Material.objects.count() == 9

    excecoes = list(ExcecaoImportacao.objects.filter(execucao=execucao).order_by("linha_inicial"))
    assert len(excecoes) == 13

    linha_nao_associavel = excecoes[0]
    assert linha_nao_associavel.motivo == MotivoRecusa.LINHA_NAO_ASSOCIAVEL
    assert linha_nao_associavel.cadpro == ""
    assert linha_nao_associavel.linha_inicial == linha_nao_associavel.linha_final == 2

    duplicados = [e for e in excecoes if e.motivo == MotivoRecusa.CADPRO_DUPLICADO_NO_ARQUIVO]
    assert len(duplicados) == 2
    assert {e.cadpro for e in duplicados} == {"090.090.090"}
    assert {e.linha_inicial for e in duplicados} == {19, 20}

    formato_invalido = next(
        e for e in excecoes if e.motivo == MotivoRecusa.CADPRO_FORMATO_INVALIDO
    )
    assert formato_invalido.cadpro == "2"
    assert formato_invalido.linha_inicial == formato_invalido.linha_final == 18


# ---------------------------------------------------------------------------
# calcular_plano — só leituras, determinístico
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_plano_calculado_reflete_insercoes_e_recusas_ordenadas(importacao, csv_fixture):
    """`calcular_plano` só lê o banco: nada é gravado. As listas do plano
    vêm ordenadas explicitamente (`interface-importacao.md`:
    `insercoes`/`atualizacoes` por `cadpro`, `recusas` por
    `linha_inicial`)."""
    conteudo = csv_fixture("carga_inicial_casos_spec.csv")

    plano = importacao.calcular_plano(conteudo)

    assert Material.objects.count() == 0  # só leituras, nada persistido
    assert [r.cadpro for r in plano.insercoes] == sorted(r.cadpro for r in plano.insercoes)
    assert [r.linha_inicial for r in plano.recusas] == sorted(
        r.linha_inicial for r in plano.recusas
    )
    assert plano.atualizacoes == ()
    assert plano.divergencias == ()
    assert plano.total_ausentes_no_arquivo == 0
    assert plano.total_recebidos == 22
    assert plano.total_inseridos == 9
    assert plano.total_rejeitados == 13


@pytest.mark.django_db
def test_calcular_plano_e_deterministico_sobre_o_mesmo_estado(importacao, csv_fixture):
    """`calcular_plano` chamado duas vezes sobre o mesmo estado do banco,
    com vários materiais e registros no arquivo, produz `impressao_digital`
    idêntica — condição necessária para a comparação prévia/confirmação
    (research.md R8/R9) ser determinística."""
    conteudo = csv_fixture("carga_inicial_casos_spec.csv")

    plano_1 = importacao.calcular_plano(conteudo)
    plano_2 = importacao.calcular_plano(conteudo)

    assert plano_1.impressao_digital == plano_2.impressao_digital
    assert plano_1.impressao_digital != ""
    assert Material.objects.count() == 0
