"""Testes de atomicidade, idempotência e concorrência da importação (T017,
T042).

Cobre `INV-STOCK-004` (nenhuma operação composta pode concluir parcialmente)
e `INV-CATALOG-002` (nunca dois materiais com o mesmo `CADPRO`), conforme
`research.md` R9 e `contracts/interface-importacao.md`. T042 (US4) estende
este arquivo com os mesmos cenários aplicados à REIMPORTAÇÃO: prévia
desatualizada quando o saldo referenciado pelo plano muda antes da
confirmação (`INV-STOCK-004`), e rollback completo — inclusive do
`bulk_update` cadastral já aplicado mais cedo na mesma transação — numa falha
tardia no `bulk_create` de `DivergenciaSaldo`. O comportamento funcional da
reconciliação em si (totais, divergência, alteração cadastral, ausentes) é
`tests/test_catalogo_reimportacao.py` (T041); aqui o foco é só
atomicidade/concorrência.

TDD: escrito antes de `catalogo/importacao.py` existir (T020-T024) e antes
da extensão de US4 (T044/T045). Todo teste deste arquivo importa
`catalogo.importacao` **localmente**, dentro da própria função, para que a
ausência do módulo ou dos campos de US4 derrube só aquele teste (não a
coleta do arquivo inteiro nem da suíte).

Padrão de concorrência: `tests/test_contas_organizacao.py` — chamada direta
da função de domínio (sem `Client`), threads reais, `connection.close()` em
`finally`, `join(timeout=10)` + `assert not thread.is_alive()`, exceções
coletadas por thread num dicionário em vez de propagadas.
"""

import threading
import uuid
from decimal import Decimal
from unittest import mock

import pytest
from django.db import connection, transaction

from catalogo.models import (
    AlteracaoCadastralMaterial,
    DivergenciaSaldo,
    ExcecaoImportacao,
    ExecucaoImportacao,
    Material,
)


def _nova_sessao():
    """Sessão real (backend `db`), usada só como o contêiner esperado por
    `guardar_pedido`/`obter_pedido` — sem precisar de `Client`/HTTP."""
    from django.contrib.sessions.backends.db import SessionStore

    return SessionStore()


def _contagem_das_cinco_tabelas():
    return {
        "Material": Material.objects.count(),
        "ExecucaoImportacao": ExecucaoImportacao.objects.count(),
        "ExcecaoImportacao": ExcecaoImportacao.objects.count(),
        "DivergenciaSaldo": DivergenciaSaldo.objects.count(),
        "AlteracaoCadastralMaterial": AlteracaoCadastralMaterial.objects.count(),
    }


# ---------------------------------------------------------------------------
# Falha injetada em dois pontos de aplicar_plano: nenhuma das cinco tabelas
# de `catalogo` pode ficar com escrita parcial (INV-STOCK-004).
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_falha_cedo_no_bulk_create_de_material_desfaz_as_cinco_tabelas(
    chefe_almoxarifado, csv_fixture
):
    """Falha no PRIMEIRO `bulk_create` (materiais novos) não pode deixar a
    `ExecucaoImportacao` já criada nem nenhuma exceção gravada."""
    from catalogo import importacao

    conteudo = csv_fixture("carga_inicial_casos_spec.csv")
    plano = importacao.calcular_plano(conteudo)
    assert plano.insercoes, "pré-condição: o plano precisa ter inserções para exercitar a falha"
    assert plano.recusas, "pré-condição: o plano precisa ter recusas (segunda tabela) também"

    estado_antes = _contagem_das_cinco_tabelas()

    with mock.patch.object(Material.objects, "bulk_create", side_effect=RuntimeError("falha cedo")):
        with pytest.raises(RuntimeError, match="falha cedo"):
            with transaction.atomic():
                importacao.aplicar_plano(
                    plano,
                    usuario=chefe_almoxarifado,
                    token_previa=str(uuid.uuid4()),
                    nome_arquivo="carga.csv",
                    tamanho_arquivo=len(conteudo),
                )

    assert _contagem_das_cinco_tabelas() == estado_antes == {
        "Material": 0,
        "ExecucaoImportacao": 0,
        "ExcecaoImportacao": 0,
        "DivergenciaSaldo": 0,
        "AlteracaoCadastralMaterial": 0,
    }


@pytest.mark.django_db
def test_falha_tarde_no_bulk_create_de_excecao_desfaz_as_cinco_tabelas(
    chefe_almoxarifado, csv_fixture
):
    """Falha no ÚLTIMO `bulk_create` (exceções) precisa desfazer também os
    materiais e a execução já gravados no mesmo plano, mais cedo na mesma
    transação — não só os efeitos posteriores ao ponto de falha."""
    from catalogo import importacao

    conteudo = csv_fixture("carga_inicial_casos_spec.csv")
    plano = importacao.calcular_plano(conteudo)
    assert plano.insercoes
    assert plano.recusas

    with mock.patch.object(
        ExcecaoImportacao.objects, "bulk_create", side_effect=RuntimeError("falha tarde")
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

    assert _contagem_das_cinco_tabelas() == {
        "Material": 0,
        "ExecucaoImportacao": 0,
        "ExcecaoImportacao": 0,
        "DivergenciaSaldo": 0,
        "AlteracaoCadastralMaterial": 0,
    }, "o bulk_create de Material já tinha sido efetivado (na transação) quando a exceção falhou"


# ---------------------------------------------------------------------------
# Outra execução confirmada entre a prévia e a confirmação: a impressão
# digital recalculada tem que divergir (sequencial, sem threads).
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_outra_execucao_confirmada_entre_previa_e_confirmacao_torna_previa_desatualizada(
    chefe_almoxarifado, csv_fixture
):
    conteudo = csv_fixture("carga_inicial_valida.csv")

    sessao_original = _nova_sessao()
    from catalogo import importacao

    pedido_original = importacao.guardar_pedido(
        sessao_original, nome_arquivo="original.csv", conteudo=conteudo
    )
    plano_original = importacao.calcular_plano(conteudo)

    # Outra sessão/usuário confirma, ANTES desta, uma importação que insere
    # pelo menos um dos CADPRO do arquivo desta prévia (aqui, o mesmo arquivo
    # inteiro — basta um único código em comum para invalidar a prévia).
    sessao_concorrente = _nova_sessao()
    pedido_concorrente = importacao.guardar_pedido(
        sessao_concorrente, nome_arquivo="concorrente.csv", conteudo=conteudo
    )
    plano_concorrente = importacao.calcular_plano(conteudo)
    importacao.confirmar_importacao(
        pedido_concorrente, plano_concorrente.impressao_digital, chefe_almoxarifado
    )
    assert Material.objects.filter(cadpro="000.000.002").exists()

    with pytest.raises(importacao.PreviaDesatualizada):
        importacao.confirmar_importacao(
            pedido_original, plano_original.impressao_digital, chefe_almoxarifado
        )

    # A prévia desatualizada não duplicou nem alterou o que a outra execução
    # já havia gravado.
    assert ExecucaoImportacao.objects.count() == 1
    assert Material.objects.filter(cadpro="000.000.002").count() == 1


# ---------------------------------------------------------------------------
# Saldo de um material FORA do arquivo, alterado entre prévia e confirmação:
# a impressão digital não depende do catálogo inteiro (só do que o arquivo
# referencia), então a confirmação continua bem-sucedida.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_saldo_de_material_fora_do_arquivo_alterado_nao_invalida_a_previa(
    chefe_almoxarifado, csv_fixture
):
    from catalogo import importacao

    # Carga inicial: estabelece um catálogo com materiais que NÃO estarão
    # no arquivo da reimportação (README de `tests/fixtures/catalogo/`:
    # `010.020.032` some de `reimportacao.csv`).
    conteudo_inicial = csv_fixture("carga_inicial_valida.csv")
    plano_inicial = importacao.calcular_plano(conteudo_inicial)
    sessao_inicial = _nova_sessao()
    pedido_inicial = importacao.guardar_pedido(
        sessao_inicial, nome_arquivo="inicial.csv", conteudo=conteudo_inicial
    )
    importacao.confirmar_importacao(
        pedido_inicial, plano_inicial.impressao_digital, chefe_almoxarifado
    )

    conteudo_reimportacao = csv_fixture("reimportacao.csv")
    plano = importacao.calcular_plano(conteudo_reimportacao)
    sessao = _nova_sessao()
    pedido = importacao.guardar_pedido(
        sessao, nome_arquivo="reimportacao.csv", conteudo=conteudo_reimportacao
    )

    material_fora_do_arquivo = Material.objects.get(cadpro="010.020.032")
    novo_saldo = Decimal("999.000")
    Material.objects.filter(pk=material_fora_do_arquivo.pk).update(saldo=novo_saldo)

    # Não deve levantar PreviaDesatualizada: o material alterado não integra
    # nenhuma lista do plano (não é inserção, atualização nem divergência).
    importacao.confirmar_importacao(pedido, plano.impressao_digital, chefe_almoxarifado)

    material_fora_do_arquivo.refresh_from_db()
    assert material_fora_do_arquivo.saldo == novo_saldo, (
        "a confirmação bem-sucedida não deveria ter tocado o saldo de um material "
        "que nem está no arquivo reimportado"
    )


# ---------------------------------------------------------------------------
# Mesmo token_previa confirmado duas vezes — em sequência.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_confirmar_o_mesmo_token_duas_vezes_em_sequencia_recebe_ja_confirmada(
    chefe_almoxarifado, csv_fixture
):
    from catalogo import importacao

    conteudo = csv_fixture("carga_inicial_valida.csv")
    plano = importacao.calcular_plano(conteudo)
    pedido = importacao.PedidoPrevia(
        token=str(uuid.uuid4()),
        nome_arquivo="carga.csv",
        tamanho=len(conteudo),
        sha256=plano.sha256_arquivo,
        conteudo=conteudo,
    )

    execucao = importacao.confirmar_importacao(pedido, plano.impressao_digital, chefe_almoxarifado)

    # Mesmo pedido, mesma impressão: a segunda chamada tem que ser recusada
    # pelo TOKEN já usado — antes mesmo de qualquer recálculo de plano (a
    # reclassificação de "inserção" para "atualização" já mudaria a impressão
    # digital sozinha; o teste abaixo prova que a checagem de token vem antes
    # dessa comparação, e não depende dela).
    with pytest.raises(importacao.PreviaJaConfirmada) as excinfo:
        importacao.confirmar_importacao(pedido, plano.impressao_digital, chefe_almoxarifado)

    assert excinfo.value.execucao.pk == execucao.pk
    assert ExecucaoImportacao.objects.count() == 1
    assert Material.objects.filter(cadpro="000.000.002").count() == 1


# ---------------------------------------------------------------------------
# Concorrência real: threads, barreira, lock_timeout e coleta de exceções por
# thread (padrão de tests/test_contas_organizacao.py).
# ---------------------------------------------------------------------------


def _confirmar_em_thread(nome, pedido, impressao_digital, usuario, resultados, barreira):
    from catalogo import importacao

    try:
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '5s'")
        barreira.wait(timeout=5)
        importacao.confirmar_importacao(pedido, impressao_digital, usuario)
        resultados[nome] = "ok"
    except Exception as exc:  # noqa: BLE001 — captura para asserção
        resultados[nome] = exc
    finally:
        # Conexão é thread-local: sem isso, fica aberta após a thread
        # terminar e impede o teardown do banco de teste.
        connection.close()


@pytest.mark.django_db(transaction=True)
def test_confirmar_o_mesmo_token_concorrentemente_produz_uma_execucao_e_uma_ja_confirmada(
    chefe_almoxarifado, csv_fixture
):
    from catalogo import importacao

    conteudo = csv_fixture("carga_inicial_valida.csv")
    plano = importacao.calcular_plano(conteudo)
    # Mesmo pedido (mesmo token) usado pelas duas threads.
    pedido = importacao.PedidoPrevia(
        token=str(uuid.uuid4()),
        nome_arquivo="carga.csv",
        tamanho=len(conteudo),
        sha256=plano.sha256_arquivo,
        conteudo=conteudo,
    )

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
        f"PreviaJaConfirmada, não {erro!r} — outra exceção não prova que o token "
        "foi de fato a defesa que serializou a corrida"
    )

    assert ExecucaoImportacao.objects.count() == 1
    assert Material.objects.filter(cadpro="000.000.002").count() == 1


@pytest.mark.django_db(transaction=True)
def test_duas_confirmacoes_concorrentes_do_mesmo_arquivo_produzem_uma_execucao_sem_duplicar(
    chefe_almoxarifado, csv_fixture
):
    """Dois pedidos DISTINTOS (tokens diferentes), prévias calculadas sobre o
    catálogo vazio, confirmando concorrentemente o mesmo conteúdo de
    arquivo: exatamente uma execução vence; a outra é recusada porque, sob o
    lock, o catálogo já não está mais vazio (nenhum `IntegrityError` de
    `CADPRO` duplicado deveria escapar — a defesa de banco é a última linha,
    não a primeira)."""
    from catalogo import importacao

    conteudo = csv_fixture("carga_inicial_valida.csv")
    plano = importacao.calcular_plano(conteudo)  # catálogo vazio: mesma impressão para os dois

    pedido_a = importacao.PedidoPrevia(
        token=str(uuid.uuid4()),
        nome_arquivo="a.csv",
        tamanho=len(conteudo),
        sha256=plano.sha256_arquivo,
        conteudo=conteudo,
    )
    pedido_b = importacao.PedidoPrevia(
        token=str(uuid.uuid4()),
        nome_arquivo="b.csv",
        tamanho=len(conteudo),
        sha256=plano.sha256_arquivo,
        conteudo=conteudo,
    )

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
        "a confirmação perdedora deveria falhar com PreviaDesatualizada (o catálogo "
        f"deixou de estar vazio sob o lock), não {erro!r}"
    )

    assert ExecucaoImportacao.objects.count() == 1
    assert Material.objects.filter(cadpro="000.000.002").count() == 1, (
        "nenhum material pode ter sido duplicado pelas duas tentativas concorrentes"
    )


# ---------------------------------------------------------------------------
# T042 (US4) — atomicidade e concorrência da REIMPORTAÇÃO: prévia
# desatualizada quando o saldo referenciado pelo plano muda antes da
# confirmação, e rollback completo (inclusive `bulk_update` cadastral) numa
# falha tardia. Ver `tests/test_catalogo_reimportacao.py` (T041) para o
# comportamento funcional da reconciliação em si.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_saldo_alterado_entre_previa_e_confirmacao_da_reimportacao_fica_desatualizada(
    chefe_almoxarifado, csv_fixture
):
    """Prévia de reimportação calculada; antes de confirmar, o saldo de um
    material que a própria prévia aponta como divergente muda (nova
    movimentação, ou outra reimportação). A confirmação precisa recusar como
    "prévia desatualizada", sem gravar nada, e a nova prévia recalculada
    (`exc.plano_atual`) precisa refletir a divergência ATUALIZADA — não a
    congelada no momento da prévia original."""
    from catalogo import importacao

    conteudo_inicial = csv_fixture("carga_inicial_valida.csv")
    plano_inicial = importacao.calcular_plano(conteudo_inicial)
    pedido_inicial = importacao.PedidoPrevia(
        token=str(uuid.uuid4()),
        nome_arquivo="inicial.csv",
        tamanho=len(conteudo_inicial),
        sha256=plano_inicial.sha256_arquivo,
        conteudo=conteudo_inicial,
    )
    importacao.confirmar_importacao(
        pedido_inicial, plano_inicial.impressao_digital, chefe_almoxarifado
    )

    conteudo_reimportacao = csv_fixture("reimportacao.csv")
    plano_previa = importacao.calcular_plano(conteudo_reimportacao)
    pedido_reimportacao = importacao.PedidoPrevia(
        token=str(uuid.uuid4()),
        nome_arquivo="reimportacao.csv",
        tamanho=len(conteudo_reimportacao),
        sha256=plano_previa.sha256_arquivo,
        conteudo=conteudo_reimportacao,
    )

    # `010.020.031` já diverge nesta prévia (saldo 10, arquivo 15). Uma
    # movimentação (fora desta feature) muda o saldo antes da confirmação.
    material = Material.objects.get(cadpro="010.020.031")
    Material.objects.filter(pk=material.pk).update(saldo=Decimal("999.000"))

    estado_antes = _contagem_das_cinco_tabelas()
    with pytest.raises(importacao.PreviaDesatualizada) as excinfo:
        importacao.confirmar_importacao(
            pedido_reimportacao, plano_previa.impressao_digital, chefe_almoxarifado
        )

    assert _contagem_das_cinco_tabelas() == estado_antes, (
        "prévia desatualizada não pode gravar nada"
    )
    nova_divergencia = next(
        d for d in excinfo.value.plano_atual.divergencias if d.cadpro == "010.020.031"
    )
    assert nova_divergencia.saldo_wms == Decimal("999.000"), (
        "a nova prévia (plano_atual) precisa refletir o saldo já alterado, não o congelado"
    )


@pytest.mark.django_db
def test_falha_no_bulk_create_de_divergencias_desfaz_atualizacao_cadastral_e_saldo(
    chefe_almoxarifado, csv_fixture
):
    """Falha no `bulk_create` de `DivergenciaSaldo`, numa reimportação que
    também teria atualizações cadastrais, precisa desfazer TUDO da mesma
    transação — inclusive o `bulk_update` dos campos cadastrais já aplicado
    mais cedo no mesmo plano. Os materiais existentes, relidos do banco,
    continuam com os valores de antes da reimportação."""
    from catalogo import importacao

    conteudo_inicial = csv_fixture("carga_inicial_valida.csv")
    plano_inicial = importacao.calcular_plano(conteudo_inicial)
    with transaction.atomic():
        importacao.aplicar_plano(
            plano_inicial,
            usuario=chefe_almoxarifado,
            token_previa=str(uuid.uuid4()),
            nome_arquivo="inicial.csv",
            tamanho_arquivo=len(conteudo_inicial),
        )

    snapshot_antes = {
        m.cadpro: (m.descricao, m.unidade, m.detalhamento, m.grupo, m.subgrupo,
                   m.nome_grupo, m.nome_subgrupo, m.saldo)
        for m in Material.objects.all()
    }
    estado_antes = _contagem_das_cinco_tabelas()

    conteudo_reimportacao = csv_fixture("reimportacao.csv")
    plano_reimportacao = importacao.calcular_plano(conteudo_reimportacao)
    assert plano_reimportacao.divergencias, (
        "pré-condição: o plano precisa ter divergências para exercitar a falha"
    )
    assert any(a.alteracoes for a in plano_reimportacao.atualizacoes), (
        "pré-condição: o plano precisa ter atualizações cadastrais também"
    )

    with mock.patch.object(
        DivergenciaSaldo.objects, "bulk_create", side_effect=RuntimeError("falha divergencia")
    ):
        with pytest.raises(RuntimeError, match="falha divergencia"):
            with transaction.atomic():
                importacao.aplicar_plano(
                    plano_reimportacao,
                    usuario=chefe_almoxarifado,
                    token_previa=str(uuid.uuid4()),
                    nome_arquivo="reimportacao.csv",
                    tamanho_arquivo=len(conteudo_reimportacao),
                )

    assert _contagem_das_cinco_tabelas() == estado_antes, (
        "nenhuma execução, atualização cadastral, alteração ou divergência pode persistir"
    )
    snapshot_depois = {
        m.cadpro: (m.descricao, m.unidade, m.detalhamento, m.grupo, m.subgrupo,
                   m.nome_grupo, m.nome_subgrupo, m.saldo)
        for m in Material.objects.all()
    }
    assert snapshot_depois == snapshot_antes, (
        "o bulk_update cadastral, já aplicado mais cedo na mesma transação, precisa "
        "ter sido desfeito junto com o restante"
    )
