"""Testes de atomicidade, idempotência, concorrência e desempenho da
importação de fornecedores (T010, US1, CRÍTICO).

Cobre `INV-STOCK-004` (aplicada por analogia à carga do cadastro, FR-017:
nenhuma operação composta pode concluir parcialmente) e `INV-SUPPLIER-002`
(nunca dois fornecedores com o mesmo `codif`), conforme `research.md`
R5/R10 e `contracts/interface-importacao.md`.

TDD: escrito antes de `fornecedores/importacao.py` existir. Todo teste deste
arquivo importa `fornecedores.importacao`/`fornecedores.leitura_fornecedores`
**localmente**, dentro da própria função, para que a ausência do módulo
derrube só aquele teste (não a coleta do arquivo inteiro nem da suíte) —
mesmo padrão de `tests/test_catalogo_atomicidade.py` (T017).

Padrão de concorrência: chamada direta da função de domínio (sem `Client`),
threads reais, `connection.close()` em `finally`, `join(timeout=10)` +
`assert not thread.is_alive()`, exceções coletadas por thread num
dicionário em vez de propagadas (`tests/test_contas_organizacao.py`,
`tests/test_catalogo_atomicidade.py`).
"""

import hashlib
import threading
import time
import uuid
from unittest import mock

import pytest
from django.db import connection, transaction

from fornecedores.models import (
    AlteracaoFornecedor,
    ExcecaoImportacaoFornecedores,
    ExecucaoImportacaoFornecedores,
    Fornecedor,
)


def _nova_sessao():
    """Sessão real (backend `db`), usada só como o contêiner esperado por
    `guardar_pedido`/`obter_pedido` — sem precisar de `Client`/HTTP."""
    from django.contrib.sessions.backends.db import SessionStore

    return SessionStore()


def _contagem_das_quatro_tabelas():
    return {
        "Fornecedor": Fornecedor.objects.count(),
        "ExecucaoImportacaoFornecedores": ExecucaoImportacaoFornecedores.objects.count(),
        "ExcecaoImportacaoFornecedores": ExcecaoImportacaoFornecedores.objects.count(),
        "AlteracaoFornecedor": AlteracaoFornecedor.objects.count(),
    }


def _ler_e_calcular_plano(conteudo, *, bloquear=False):
    from fornecedores import importacao
    from fornecedores import leitura_fornecedores as lf

    leitura = lf.ler_fornecedores(conteudo)
    sha256_arquivo = hashlib.sha256(conteudo).hexdigest()
    return importacao.calcular_plano(leitura, sha256_arquivo, bloquear=bloquear), leitura


def _pedido(conteudo, leitura, sha256_arquivo, nome_arquivo="fornecedores.csv"):
    from fornecedores import importacao

    return importacao.PedidoPrevia(
        token=str(uuid.uuid4()),
        nome_arquivo=nome_arquivo,
        tamanho=len(conteudo),
        sha256=sha256_arquivo,
        leitura=leitura,
    )


# ---------------------------------------------------------------------------
# Fixtures de conteúdo mínimas, montadas inline (sem depender de arquivo em
# disco) — um lote de inserções simples e, à parte, uma reimportação com
# atualização cadastral, para exercitar `bulk_update` também.
# ---------------------------------------------------------------------------

_CABECALHO = "CODIF;NOME;NOM_FANT;INSMF;CODTIP;BLOQ_OPCAO;MSG_BLOQ;TIPO_BLOQ;"


def _linha(codif, nome, bloq="S", msg="", tipo=""):
    return f"{codif};{nome};;;01;{bloq};{msg};{tipo};"


def _arquivo(*linhas):
    texto = "\r\n".join([_CABECALHO, *linhas]) + "\r\n"
    return ("\ufeff" + texto).encode("utf-8")


CONTEUDO_INICIAL = _arquivo(
    _linha("800001", "FORNECEDOR ATOMICIDADE UM"),
    _linha("800002", "FORNECEDOR ATOMICIDADE DOIS"),
)
CONTEUDO_REIMPORTACAO_COM_ALTERACAO = _arquivo(
    _linha("800001", "FORNECEDOR ATOMICIDADE UM REVISADO"),
    _linha("800002", "FORNECEDOR ATOMICIDADE DOIS"),
)


# ---------------------------------------------------------------------------
# Falha injetada — nenhuma das quatro tabelas de `fornecedores` pode ficar
# com escrita parcial (INV-STOCK-004 por analogia).
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_falha_cedo_no_bulk_create_de_fornecedor_desfaz_as_quatro_tabelas(chefe_almoxarifado):
    """Falha no PRIMEIRO `bulk_create` (inserções) não pode deixar a
    `ExecucaoImportacaoFornecedores` já criada nem nenhuma exceção
    gravada."""
    from fornecedores import importacao

    conteudo = _arquivo(
        _linha("800011", "FORNECEDOR UM"),
        _linha("800012", "FORNECEDOR SITUACAO INVALIDA", bloq="X"),
    )
    plano, _leitura = _ler_e_calcular_plano(conteudo)
    assert plano.insercoes, "pré-condição: o plano precisa ter inserções"
    assert plano.recusas, "pré-condição: o plano precisa ter recusas também"

    estado_antes = _contagem_das_quatro_tabelas()

    with mock.patch.object(
        Fornecedor.objects, "bulk_create", side_effect=RuntimeError("falha cedo")
    ):
        with pytest.raises(RuntimeError, match="falha cedo"):
            with transaction.atomic():
                importacao.aplicar_plano(
                    plano,
                    usuario=chefe_almoxarifado,
                    token_previa=str(uuid.uuid4()),
                    nome_arquivo="carga.csv",
                    tamanho_arquivo=len(conteudo),
                )

    assert _contagem_das_quatro_tabelas() == estado_antes == {
        "Fornecedor": 0,
        "ExecucaoImportacaoFornecedores": 0,
        "ExcecaoImportacaoFornecedores": 0,
        "AlteracaoFornecedor": 0,
    }


@pytest.mark.django_db
def test_falha_tarde_no_bulk_create_de_excecao_desfaz_as_quatro_tabelas(chefe_almoxarifado):
    """Falha no ÚLTIMO `bulk_create` do plano (exceções) precisa desfazer
    também os fornecedores e a execução já gravados mais cedo na mesma
    transação — não só os efeitos posteriores ao ponto de falha."""
    from fornecedores import importacao

    conteudo = _arquivo(
        _linha("800021", "FORNECEDOR UM"),
        _linha("800022", "FORNECEDOR SITUACAO INVALIDA", bloq="X"),
    )
    plano, _leitura = _ler_e_calcular_plano(conteudo)
    assert plano.insercoes
    assert plano.recusas

    with mock.patch.object(
        ExcecaoImportacaoFornecedores.objects,
        "bulk_create",
        side_effect=RuntimeError("falha tarde"),
    ):
        with pytest.raises(RuntimeError, match="falha tarde"):
            with transaction.atomic():
                importacao.aplicar_plano(
                    plano,
                    usuario=chefe_almoxarifado,
                    token_previa=str(uuid.uuid4()),
                    nome_arquivo="carga.csv",
                    tamanho_arquivo=len(conteudo),
                )

    assert _contagem_das_quatro_tabelas() == {
        "Fornecedor": 0,
        "ExecucaoImportacaoFornecedores": 0,
        "ExcecaoImportacaoFornecedores": 0,
        "AlteracaoFornecedor": 0,
    }, "o bulk_create de Fornecedor já tinha sido efetivado (na transação) quando a exceção falhou"


@pytest.mark.django_db
def test_falha_no_bulk_create_de_alteracao_desfaz_o_bulk_update_cadastral(chefe_almoxarifado):
    """Falha no `bulk_create` de `AlteracaoFornecedor`, numa reimportação
    que também atualiza campos cadastrais, precisa desfazer TUDO da mesma
    transação — inclusive o `bulk_update` de `Fornecedor` já aplicado mais
    cedo no mesmo plano. Relido do banco, o fornecedor continua com o nome
    de antes da reimportação (mesmo padrão de
    `test_falha_no_bulk_create_de_divergencias_desfaz_atualizacao_cadastral_e_saldo`,
    da 001 — sem saldo, fornecedores não tem esse conceito)."""
    from fornecedores import importacao

    plano_inicial, _leitura_inicial = _ler_e_calcular_plano(CONTEUDO_INICIAL)
    with transaction.atomic():
        importacao.aplicar_plano(
            plano_inicial,
            usuario=chefe_almoxarifado,
            token_previa=str(uuid.uuid4()),
            nome_arquivo="inicial.csv",
            tamanho_arquivo=len(CONTEUDO_INICIAL),
        )

    nome_antes = Fornecedor.objects.get(codif="800001").nome
    estado_antes = _contagem_das_quatro_tabelas()

    plano_reimportacao, _leitura_reimp = _ler_e_calcular_plano(CONTEUDO_REIMPORTACAO_COM_ALTERACAO)
    assert any(a.alteracoes for a in plano_reimportacao.atualizacoes), (
        "pré-condição: o plano de reimportação precisa ter uma alteração cadastral real"
    )

    with mock.patch.object(
        AlteracaoFornecedor.objects, "bulk_create", side_effect=RuntimeError("falha alteracao")
    ):
        with pytest.raises(RuntimeError, match="falha alteracao"):
            with transaction.atomic():
                importacao.aplicar_plano(
                    plano_reimportacao,
                    usuario=chefe_almoxarifado,
                    token_previa=str(uuid.uuid4()),
                    nome_arquivo="reimportacao.csv",
                    tamanho_arquivo=len(CONTEUDO_REIMPORTACAO_COM_ALTERACAO),
                )

    assert _contagem_das_quatro_tabelas() == estado_antes, (
        "nenhuma execução, alteração ou fornecedor novo pode persistir da reimportação falha"
    )
    assert Fornecedor.objects.get(codif="800001").nome == nome_antes, (
        "o bulk_update do nome, já aplicado mais cedo na mesma transação, precisa ter sido "
        "desfeito junto com o restante"
    )


# ---------------------------------------------------------------------------
# Prévia desatualizada — outra execução confirmada entre a prévia e a
# confirmação (sequencial, sem threads).
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_outra_execucao_confirmada_entre_previa_e_confirmacao_torna_previa_desatualizada(
    chefe_almoxarifado,
):
    from fornecedores import importacao

    sessao_original = _nova_sessao()
    pedido_original = importacao.guardar_pedido(
        sessao_original, nome_arquivo="original.csv", conteudo=CONTEUDO_INICIAL
    )
    plano_original, _ = _ler_e_calcular_plano(CONTEUDO_INICIAL)

    # Outra sessão confirma, ANTES desta, uma importação que insere pelo
    # menos um dos codif desta prévia.
    sessao_concorrente = _nova_sessao()
    pedido_concorrente = importacao.guardar_pedido(
        sessao_concorrente, nome_arquivo="concorrente.csv", conteudo=CONTEUDO_INICIAL
    )
    plano_concorrente, _ = _ler_e_calcular_plano(CONTEUDO_INICIAL)
    importacao.confirmar_importacao(
        pedido_concorrente, plano_concorrente.impressao_digital, chefe_almoxarifado
    )
    assert Fornecedor.objects.filter(codif="800001").exists()

    with pytest.raises(importacao.PreviaDesatualizada):
        importacao.confirmar_importacao(
            pedido_original, plano_original.impressao_digital, chefe_almoxarifado
        )

    assert ExecucaoImportacaoFornecedores.objects.count() == 1
    assert Fornecedor.objects.filter(codif="800001").count() == 1


# ---------------------------------------------------------------------------
# Mesmo token_previa confirmado duas vezes — em sequência.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_confirmar_o_mesmo_token_duas_vezes_em_sequencia_recebe_ja_confirmada(chefe_almoxarifado):
    from fornecedores import importacao

    plano, leitura = _ler_e_calcular_plano(CONTEUDO_INICIAL)
    sha256_arquivo = hashlib.sha256(CONTEUDO_INICIAL).hexdigest()
    pedido = _pedido(CONTEUDO_INICIAL, leitura, sha256_arquivo)

    execucao = importacao.confirmar_importacao(pedido, plano.impressao_digital, chefe_almoxarifado)

    with pytest.raises(importacao.PreviaJaConfirmada) as excinfo:
        importacao.confirmar_importacao(pedido, plano.impressao_digital, chefe_almoxarifado)

    assert excinfo.value.execucao.pk == execucao.pk
    assert ExecucaoImportacaoFornecedores.objects.count() == 1
    assert Fornecedor.objects.filter(codif="800001").count() == 1


# ---------------------------------------------------------------------------
# Concorrência real: threads, barreira, lock_timeout e coleta de exceções
# por thread.
# ---------------------------------------------------------------------------


def _confirmar_em_thread(nome, pedido, impressao_digital, usuario, resultados, barreira):
    from fornecedores import importacao

    try:
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '5s'")
        barreira.wait(timeout=5)
        importacao.confirmar_importacao(pedido, impressao_digital, usuario)
        resultados[nome] = "ok"
    except Exception as exc:  # noqa: BLE001 — captura para asserção
        resultados[nome] = exc
    finally:
        connection.close()


@pytest.mark.django_db(transaction=True)
def test_confirmar_o_mesmo_token_concorrentemente_produz_uma_execucao_e_uma_ja_confirmada(
    chefe_almoxarifado,
):
    from fornecedores import importacao

    plano, leitura = _ler_e_calcular_plano(CONTEUDO_INICIAL)
    sha256_arquivo = hashlib.sha256(CONTEUDO_INICIAL).hexdigest()
    # Mesmo pedido (mesmo token) usado pelas duas threads.
    pedido = _pedido(CONTEUDO_INICIAL, leitura, sha256_arquivo)

    barreira = threading.Barrier(2)
    resultados = {}
    t1 = threading.Thread(
        target=_confirmar_em_thread,
        args=("t1", pedido, plano.impressao_digital, chefe_almoxarifado, resultados, barreira),
    )
    t2 = threading.Thread(
        target=_confirmar_em_thread,
        args=("t2", pedido, plano.impressao_digital, chefe_almoxarifado, resultados, barreira),
    )

    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert not t1.is_alive(), "thread t1 não terminou dentro do timeout"
    assert not t2.is_alive(), "thread t2 não terminou dentro do timeout"

    sucessos = [nome for nome, resultado in resultados.items() if resultado == "ok"]
    falhas = {nome: resultado for nome, resultado in resultados.items() if resultado != "ok"}

    assert len(sucessos) == 1, f"esperava exatamente uma confirmação vencedora; {resultados!r}"
    assert len(falhas) == 1, f"esperava exatamente uma confirmação recusada; {resultados!r}"
    (erro,) = falhas.values()
    assert isinstance(erro, importacao.PreviaJaConfirmada), (
        "a segunda confirmação do MESMO token deveria falhar especificamente com "
        f"PreviaJaConfirmada, não {erro!r}"
    )

    assert ExecucaoImportacaoFornecedores.objects.count() == 1
    assert Fornecedor.objects.filter(codif="800001").count() == 1


@pytest.mark.django_db(transaction=True)
def test_duas_confirmacoes_concorrentes_do_mesmo_arquivo_produzem_uma_execucao_sem_duplicar(
    chefe_almoxarifado,
):
    """Dois pedidos DISTINTOS (tokens diferentes), prévias calculadas sobre
    o cadastro vazio, confirmando concorrentemente o mesmo conteúdo de
    arquivo: exatamente uma execução vence; a outra é recusada porque, sob
    o lock, o cadastro já não está mais vazio (nenhum `IntegrityError` de
    `codif` duplicado deveria escapar)."""
    from fornecedores import importacao

    plano, leitura = _ler_e_calcular_plano(CONTEUDO_INICIAL)  # cadastro vazio: mesma impressão
    sha256_arquivo = hashlib.sha256(CONTEUDO_INICIAL).hexdigest()

    pedido_a = _pedido(CONTEUDO_INICIAL, leitura, sha256_arquivo, nome_arquivo="a.csv")
    pedido_b = _pedido(CONTEUDO_INICIAL, leitura, sha256_arquivo, nome_arquivo="b.csv")

    barreira = threading.Barrier(2)
    resultados = {}
    t_a = threading.Thread(
        target=_confirmar_em_thread,
        args=("a", pedido_a, plano.impressao_digital, chefe_almoxarifado, resultados, barreira),
    )
    t_b = threading.Thread(
        target=_confirmar_em_thread,
        args=("b", pedido_b, plano.impressao_digital, chefe_almoxarifado, resultados, barreira),
    )

    t_a.start()
    t_b.start()
    t_a.join(timeout=10)
    t_b.join(timeout=10)

    assert not t_a.is_alive(), "thread a não terminou dentro do timeout"
    assert not t_b.is_alive(), "thread b não terminou dentro do timeout"

    sucessos = [nome for nome, resultado in resultados.items() if resultado == "ok"]
    falhas = {nome: resultado for nome, resultado in resultados.items() if resultado != "ok"}

    assert len(sucessos) == 1, f"esperava exatamente uma execução vencedora; {resultados!r}"
    assert len(falhas) == 1
    (erro,) = falhas.values()
    assert isinstance(erro, importacao.PreviaDesatualizada), (
        "a confirmação perdedora deveria falhar com PreviaDesatualizada (o cadastro deixou de "
        f"estar vazio sob o lock), não {erro!r}"
    )

    assert ExecucaoImportacaoFornecedores.objects.count() == 1
    assert Fornecedor.objects.filter(codif="800001").count() == 1, (
        "nenhum fornecedor pode ter sido duplicado pelas duas tentativas concorrentes"
    )


# ---------------------------------------------------------------------------
# Chave de lock distinta da 001 — importar fornecedores e importar o
# catálogo não podem se bloquear mutuamente.
# ---------------------------------------------------------------------------


def test_chave_de_lock_de_fornecedores_e_distinta_da_do_catalogo():
    from catalogo import importacao as importacao_catalogo
    from fornecedores import importacao as importacao_fornecedores

    assert (
        importacao_fornecedores.CHAVE_LOCK_IMPORTACAO_FORNECEDORES
        != importacao_catalogo.CHAVE_LOCK_IMPORTACAO_SCPI
    )


# ---------------------------------------------------------------------------
# Desempenho (SC-006): arquivo sintético de 10.035 registros gerado em
# memória — prévia (guardar_pedido + calcular_plano) e confirmação, cada
# uma em menos de 30 s. Roda sempre (sem marker/env var): é sintético, não
# depende do arquivo real (esse é test_fornecedores_arquivo_real.py, T032,
# pulado sem FORNECEDORES_CSV_REAL).
# ---------------------------------------------------------------------------


def _csv_sintetico_de_porte_real(n=10_035):
    linhas = [f"{i};FORNECEDOR SINTETICO {i};;;01;S;;;" for i in range(1, n + 1)]
    texto = "\r\n".join([_CABECALHO, *linhas]) + "\r\n"
    return ("\ufeff" + texto).encode("utf-8")


@pytest.mark.django_db
def test_desempenho_previa_e_confirmacao_de_10035_registros_sinteticos_abaixo_de_30s(
    chefe_almoxarifado,
):
    from fornecedores import importacao

    conteudo = _csv_sintetico_de_porte_real()
    sessao = _nova_sessao()

    inicio_previa = time.perf_counter()
    pedido = importacao.guardar_pedido(sessao, nome_arquivo="sintetico.csv", conteudo=conteudo)
    plano = importacao.calcular_plano(pedido.leitura, pedido.sha256)
    duracao_previa = time.perf_counter() - inicio_previa
    assert duracao_previa < 30, (
        f"prévia (guardar_pedido + calcular_plano) levou {duracao_previa:.1f}s"
    )

    assert plano.total_recebidos == 10_035
    assert plano.total_inseridos == 10_035

    inicio_confirmacao = time.perf_counter()
    execucao = importacao.confirmar_importacao(pedido, plano.impressao_digital, chefe_almoxarifado)
    duracao_confirmacao = time.perf_counter() - inicio_confirmacao
    assert duracao_confirmacao < 30, f"confirmação levou {duracao_confirmacao:.1f}s"

    assert execucao.total_inseridos == 10_035
    assert Fornecedor.objects.count() == 10_035
