"""Testes de `calcular_plano`/`aplicar_plano`/`confirmar_importacao` — carga
inicial (T008, US1).

Escrito ANTES de `fornecedores/importacao.py` existir: o import de
`fornecedores.importacao` vive dentro do fixture `importacao` (nunca no
topo do arquivo), para que a ausência do módulo vire erro de *setup* por
teste, não falha de coleta do arquivo inteiro (mesmo padrão de
`tests/test_catalogo_importacao.py`, T016).

Cobre a carga inicial sobre cadastro vazio (US1): totais, recusas gravadas
com linha/motivo/codif, campos projetados fielmente gravados, `bloqueado` e
motivo, `nome_busca`/`documento_digitos` derivados, `execucao_origem`. Não
cobre:
- atomicidade/concorrência/idempotência/desempenho:
  `tests/test_fornecedores_atomicidade.py` (T010);
- projeção mínima/sessão/log/upload em memória:
  `tests/test_fornecedores_dados_minimos.py` (T009);
- views e sessão da prévia: `tests/test_fornecedores_views_importacao.py`
  (T011);
- permissões: `tests/test_fornecedores_permissoes.py` (T012);
- reimportação (atualização, alterações, ausentes, bloqueio trocado — US4):
  `tests/test_fornecedores_reimportacao.py` (T028, rodada futura) — todo
  `codif` usado aqui é sempre novo, sobre cadastro vazio.

Invariantes/requisitos protegidos: `INV-SUPPLIER-001/002/003/004/005`,
`INV-STOCK-004` (aplicada por analogia à carga do cadastro, FR-017).
"""

import hashlib

import pytest
from django.db import transaction

from catalogo.leitura_scpi import normalizar_para_busca
from fornecedores.models import ExcecaoImportacaoFornecedores, Fornecedor

pytestmark = pytest.mark.django_db


@pytest.fixture
def importacao():
    """Módulo `fornecedores.importacao`, importado dentro do fixture (ver
    docstring do módulo) — ainda não existe até T014."""
    import fornecedores.importacao as modulo

    return modulo


@pytest.fixture
def leitura_fornecedores():
    import fornecedores.leitura_fornecedores as modulo

    return modulo


@pytest.fixture
def importar(importacao, leitura_fornecedores):
    """`importar(conteudo, usuario, nome_arquivo=...) -> (plano, execucao)`.

    Encapsula o par que `contracts/interface-importacao.md` exige do
    chamador: `ler_fornecedores` (fora do módulo de importação — a leitura
    é responsabilidade de `leitura_fornecedores`, nunca de `importacao`),
    `calcular_plano` (que recebe a leitura + o SHA-256 do arquivo original,
    calculados separadamente porque a prévia nunca guarda os bytes) e
    `aplicar_plano`, dentro da transação que o contrato exige do chamador.
    """

    def _importar(conteudo, usuario, nome_arquivo="fornecedores.csv"):
        leitura = leitura_fornecedores.ler_fornecedores(conteudo)
        sha256_arquivo = hashlib.sha256(conteudo).hexdigest()
        with transaction.atomic():
            plano = importacao.calcular_plano(leitura, sha256_arquivo)
            execucao = importacao.aplicar_plano(
                plano,
                usuario=usuario,
                token_previa="00000000-0000-0000-0000-000000000000",
                nome_arquivo=nome_arquivo,
                tamanho_arquivo=len(conteudo),
            )
        return plano, execucao

    return _importar


# ---------------------------------------------------------------------------
# Carga inicial válida (valido_basico.csv) — campos fielmente gravados,
# totais, bloqueio e motivo.
# ---------------------------------------------------------------------------


def test_carga_inicial_valida_cria_fornecedores_fieis_ao_arquivo(
    importar, chefe_almoxarifado, csv_fornecedores
):
    conteudo = csv_fornecedores("valido_basico.csv")

    plano, execucao = importar(conteudo, chefe_almoxarifado)

    assert Fornecedor.objects.count() == 4
    assert execucao.total_recebidos == 4
    assert execucao.total_inseridos == 4
    assert execucao.total_atualizados == 0
    assert execucao.total_rejeitados == 0
    assert plano.total_recebidos == plano.total_inseridos == 4

    por_codif = {f.codif: f for f in Fornecedor.objects.all()}

    alfa = por_codif["600001"]
    assert alfa.nome == "FORNECEDOR ALFA COMERCIO LTDA"
    assert alfa.nome_fantasia == "ALFA COM"
    assert alfa.documento == "11.111.111/0001-11"
    assert alfa.tipo == "01"
    assert alfa.bloqueado is False
    assert alfa.motivo_bloqueio == ""
    assert alfa.tipo_bloqueio == ""
    assert alfa.execucao_origem_id == execucao.pk

    delta = por_codif["600004"]
    assert delta.bloqueado is True
    assert delta.motivo_bloqueio == "FORNECEDOR NAO PODE SER UTILIZADO"
    assert delta.tipo_bloqueio == "MUDANCA DE CNPJ"

    gama_sem_documento = por_codif["600003"]
    assert gama_sem_documento.documento == ""
    assert gama_sem_documento.documento_digitos == ""


def test_codif_e_gravado_e_relido_byte_a_byte(importar, chefe_almoxarifado, csv_fornecedores):
    """`INV-SUPPLIER-001`: nenhuma normalização, reformatação ou conversão
    numérica do `codif` — usa `codif_com_zeros_a_esquerda.csv` (`007` e `7`
    distintos, zeros preservados)."""
    conteudo = csv_fornecedores("codif_com_zeros_a_esquerda.csv")

    importar(conteudo, chefe_almoxarifado)

    assert Fornecedor.objects.filter(codif="007").exists()
    assert Fornecedor.objects.filter(codif="7").exists()
    assert Fornecedor.objects.count() == 2


# ---------------------------------------------------------------------------
# Recusas gravadas com linha, motivo e codif quando identificável (FR-025).
# ---------------------------------------------------------------------------


def test_recusa_e_gravada_com_linha_motivo_e_sem_dado_alem_do_permitido(
    importar, chefe_almoxarifado, csv_fornecedores
):
    conteudo = csv_fornecedores("registro_com_colunas_deslocadas.csv")

    plano, execucao = importar(conteudo, chefe_almoxarifado)

    assert execucao.total_recebidos == 3
    assert execucao.total_inseridos == 2
    assert execucao.total_rejeitados == 1
    assert Fornecedor.objects.count() == 2

    excecao = ExcecaoImportacaoFornecedores.objects.get(execucao=execucao)
    assert excecao.motivo == "COLUNAS_DESLOCADAS"
    assert excecao.codif == "", "COLUNAS_DESLOCADAS não identifica o codif (contrato §3)"
    assert excecao.linha >= 1


def test_recusa_codif_duplicado_gera_uma_excecao_por_ocorrencia(
    importar, chefe_almoxarifado, csv_fornecedores
):
    conteudo = csv_fornecedores("codif_duplicado_ambos_recusados.csv")

    plano, execucao = importar(conteudo, chefe_almoxarifado)

    assert execucao.total_rejeitados == 2
    assert Fornecedor.objects.filter(codif="7").count() == 0, (
        "nenhuma das duas ocorrências recusadas pode ter sido gravada como fornecedor"
    )
    excecoes = list(ExcecaoImportacaoFornecedores.objects.filter(execucao=execucao))
    assert len(excecoes) == 2
    assert all(e.motivo == "CODIF_DUPLICADO" for e in excecoes)
    assert all(e.codif == "7" for e in excecoes)
    assert len({e.linha for e in excecoes}) == 2


# ---------------------------------------------------------------------------
# Derivados: nome_busca (R6) e documento_digitos.
# ---------------------------------------------------------------------------


def test_nome_busca_combina_nome_e_nome_fantasia_normalizados(
    importar, chefe_almoxarifado, csv_fornecedores
):
    """research.md R6: `nome_busca` normaliza `nome + " " + nome_fantasia`
    — a fórmula exata, fixada pelo research."""
    conteudo = csv_fornecedores("valido_basico.csv")

    importar(conteudo, chefe_almoxarifado)

    alfa = Fornecedor.objects.get(codif="600001")
    assert alfa.nome_busca == normalizar_para_busca("FORNECEDOR ALFA COMERCIO LTDA ALFA COM")


def test_fornecedor_e_localizavel_por_palavra_do_nome_fantasia(
    importar, chefe_almoxarifado, csv_fornecedores
):
    """Prova de comportamento (FR-027), além da fórmula exata acima: uma
    palavra que só existe em `NOM_FANT` (nunca em `NOME`) ainda encontra o
    fornecedor via `nome_busca__contains` — é o que a consulta (T020) vai
    fazer de verdade."""
    conteudo = csv_fornecedores("valido_basico.csv")

    importar(conteudo, chefe_almoxarifado)

    termo = normalizar_para_busca("COM")
    encontrados = Fornecedor.objects.filter(nome_busca__contains=termo)
    assert encontrados.filter(codif="600001").exists()


def test_documento_digitos_extrai_so_os_digitos_do_documento_recebido(
    importar, chefe_almoxarifado, csv_fornecedores
):
    conteudo = csv_fornecedores("valido_basico.csv")

    importar(conteudo, chefe_almoxarifado)

    beta = Fornecedor.objects.get(codif="600002")
    assert beta.documento == "222.222.222-22"
    assert beta.documento_digitos == "22222222222"


# ---------------------------------------------------------------------------
# Nada além dos 8 campos mínimos é gravado (INV-SUPPLIER-004) — reforço em
# nível de importação; a varredura exaustiva de sentinelas é
# tests/test_fornecedores_dados_minimos.py (T009).
# ---------------------------------------------------------------------------


def test_apenas_os_campos_minimos_sao_gravados_em_fornecedor(
    importar, chefe_almoxarifado, csv_fornecedores
):
    conteudo = csv_fornecedores("valido_basico.csv")

    importar(conteudo, chefe_almoxarifado)

    campos_do_model = {campo.name for campo in Fornecedor._meta.get_fields()}
    campos_de_identificacao_e_derivados = {
        "id", "codif", "nome", "nome_fantasia", "documento", "documento_digitos",
        "tipo", "bloqueado", "motivo_bloqueio", "tipo_bloqueio", "nome_busca",
        "execucao_origem",
    }
    assert campos_do_model == campos_de_identificacao_e_derivados | {"alteracoes"}, (
        "Fornecedor não pode ganhar nenhum campo além da projeção mínima "
        "(INV-SUPPLIER-004) sem que este teste seja revisado deliberadamente"
    )
