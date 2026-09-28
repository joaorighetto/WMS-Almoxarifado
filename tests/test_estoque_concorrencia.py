"""Testes de concorrência real do registro e do estorno de entrada (T011,
T026).

Mesmo padrão de `tests/test_catalogo_atomicidade.py`
(`test_contas_organizacao.py`): chamada direta da função de domínio (sem
`Client`), threads reais, `django_db(transaction=True)`, `SET lock_timeout`
por conexão, `connection.close()` em `finally`, `join(timeout=10)` +
`assert not thread.is_alive()`, exceções coletadas por thread num
dicionário em vez de propagadas — nunca dois requests sequenciais como
substituto de concorrência real.

Cobre FR-012/SC-004 (soma sem perda de atualização), FR-013/SC-005
(idempotência da chave sob corrida), FR-007a (referência única sob corrida),
`INV-SUPPLIER-005` (emitente bloqueado), ausência de deadlock com
`catalogo.importacao` e com a própria entrada (ordem de lock fixa por `pk`,
research R5), FR-027/SC-009 (estorno único) e `INV-STOCK-001` sob concorrência
de estorno (lost update).

TDD: escrito antes de `estoque/entradas.py` existir — falha inteiro por
`ImportError` até lá.
"""

import threading
import uuid
from decimal import Decimal
from unittest import mock

import pytest
from django.db import IntegrityError, connection, transaction

from estoque import entradas as entradas_module
from estoque.entradas import (
    LIMITE_SALDO,
    EmitenteIndisponivel,
    EntradaInformada,
    EntradaInvalida,
    EntradaJaEstornada,
    EntradaJaRegistrada,
    EstornoBloqueadoPorSaldo,
    ItemInformado,
    ReferenciaJaUsada,
    SaldoAcimaDoLimite,
    estornar_entrada,
    registrar_entrada,
    validar_entrada,
)
from estoque.models import (
    Entrada,
    ItemEntrada,
    MotivoEntrada,
    MovimentacaoEstoque,
    TipoDocumentoEntrada,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _entrada_informada(*, itens, chave_confirmacao=None, numero_documento=None, emitente_id=None):
    return EntradaInformada(
        chave_confirmacao=chave_confirmacao or uuid.uuid4(),
        motivo=MotivoEntrada.DOACAO_RECEBIDA if emitente_id is None else MotivoEntrada.COMPRA,
        tipo_documento=TipoDocumentoEntrada.NOTA_FISCAL,
        numero_documento=numero_documento or str(uuid.uuid4()),
        emitente_id=emitente_id,
        itens=tuple(itens),
    )


def _executar_em_thread(nome, funcao, resultados, barreira):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '5s'")
        barreira.wait(timeout=5)
        resultados[nome] = funcao()
    except Exception as exc:  # noqa: BLE001 — captura para asserção
        resultados[nome] = exc
    finally:
        connection.close()


def _rodar_threads(alvos_por_nome, timeout=10):
    """`alvos_por_nome`: dict `nome -> callable` (sem argumentos). Devolve o
    dicionário de resultados (valor de retorno ou exceção capturada), com
    todas as threads sincronizadas para iniciar juntas por uma `Barrier`."""
    resultados = {}
    barreira = threading.Barrier(len(alvos_por_nome))
    threads = [
        threading.Thread(target=_executar_em_thread, args=(nome, funcao, resultados, barreira))
        for nome, funcao in alvos_por_nome.items()
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=timeout)
    for thread in threads:
        assert not thread.is_alive(), f"thread {thread.name} não terminou dentro do timeout"
    return resultados


# ---------------------------------------------------------------------------
# N entradas concorrentes do mesmo material: soma exata, sem perda de
# atualização (FR-012, SC-004).
# ---------------------------------------------------------------------------


def test_entradas_concorrentes_do_mesmo_material_somam_sem_perda_de_atualizacao(
    funcionario_almoxarifado, criar_material
):
    material = criar_material("400.000.001", Decimal("0.000"))
    n_threads = 5
    quantidade_por_thread = Decimal("2.000")

    alvos = {
        f"t{i}": (
            lambda quantidade=quantidade_por_thread: registrar_entrada(
                _entrada_informada(
                    itens=[ItemInformado(material_id=material.pk, quantidade=quantidade)]
                ),
                funcionario_almoxarifado,
            )
        )
        for i in range(n_threads)
    }
    resultados = _rodar_threads(alvos)

    falhas = {nome: r for nome, r in resultados.items() if isinstance(r, Exception)}
    assert not falhas, f"nenhuma das {n_threads} entradas deveria falhar; falhas: {falhas}"

    material.refresh_from_db()
    assert material.saldo == quantidade_por_thread * n_threads
    assert MovimentacaoEstoque.objects.filter(material=material).count() == n_threads


# ---------------------------------------------------------------------------
# Mesma chave de confirmação em paralelo: uma entrada, a outra
# EntradaJaRegistrada (FR-013, SC-005).
# ---------------------------------------------------------------------------


def test_mesma_chave_de_confirmacao_concorrente_produz_uma_entrada_e_uma_ja_registrada(
    funcionario_almoxarifado, criar_material
):
    material = criar_material("400.000.002", Decimal("0.000"))
    chave = uuid.uuid4()
    dados = _entrada_informada(
        chave_confirmacao=chave,
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("3.000"))],
    )

    resultados = _rodar_threads(
        {
            "a": lambda: registrar_entrada(dados, funcionario_almoxarifado),
            "b": lambda: registrar_entrada(dados, funcionario_almoxarifado),
        }
    )

    sucessos = [r for r in resultados.values() if not isinstance(r, Exception)]
    falhas = [r for r in resultados.values() if isinstance(r, Exception)]
    assert len(sucessos) == 1, f"esperava exatamente uma confirmação vencedora; {resultados!r}"
    assert len(falhas) == 1
    (erro,) = falhas
    assert isinstance(erro, EntradaJaRegistrada), (
        f"a segunda confirmação da MESMA chave deveria falhar com EntradaJaRegistrada, "
        f"não {erro!r}"
    )
    assert Entrada.objects.filter(chave_confirmacao=chave).count() == 1
    material.refresh_from_db()
    assert material.saldo == Decimal("3.000"), "a quantidade não pode ter sido aplicada duas vezes"


# ---------------------------------------------------------------------------
# NOVO (revisão do code-reviewer, P3): quando a MESMA chave_confirmacao E a
# MESMA referência colidem sob corrida, a segunda tentativa precisa falhar
# com `EntradaJaRegistrada` — nunca `ReferenciaJaUsada` — porque a entrada
# já existente É a mesma confirmação, só reenviada. O teste acima
# (concorrência real) já EXIGE isso; mas se o Postgres relatar a violação
# da constraint `estoque_entrada_referencia_unica` antes da de
# `chave_confirmacao` (ordem interna do banco, fora do nosso controle), o
# código de produção atual (antes da correção) levanta `ReferenciaJaUsada`
# sem checar se a entrada já existente compartilha a MESMA chave — daí a
# intermitência apontada pelo reviewer.
#
# Este teste, sequencial e determinístico, força exatamente esse caminho:
# neutraliza a pré-checagem de chave (única forma de simular a janela de
# corrida em que as duas leituras "não veem" a outra transação ainda) e o
# `Entrada.objects.create()` real por uma falha sintética com a mensagem
# EXATA que o Postgres usaria para a constraint de referência — assim o
# teste não depende de qual constraint o banco relata primeiro. Antes da
# correção de produção (que deve comparar `entrada_existente.chave_
# confirmacao` com `dados.chave_confirmacao` no branch de
# `estoque_entrada_referencia_unica`), este teste FALHA (produção levanta
# `ReferenciaJaUsada`).
# ---------------------------------------------------------------------------


def test_referencia_ja_usada_sob_corrida_com_a_mesma_chave_produz_entrada_ja_registrada(
    funcionario_almoxarifado, criar_material, monkeypatch
):
    material = criar_material("400.000.011", Decimal("0.000"))
    chave = uuid.uuid4()
    numero = "NF-MESMA-CHAVE-E-REFERENCIA-0001"
    dados = _entrada_informada(
        chave_confirmacao=chave,
        numero_documento=numero,
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("2.000"))],
    )

    entrada_existente = registrar_entrada(dados, funcionario_almoxarifado)

    consulta_real = entradas_module.Entrada.objects.filter
    contagem = {"chave": 0}

    def _filter_simulando_janela_de_corrida(*args, **kwargs):
        # Só a PRIMEIRA chamada (a pré-checagem por chave, antes de
        # `validar_entrada`) é enganada; qualquer outra chamada com a mesma
        # assinatura (ex.: a releitura dentro do `except IntegrityError`,
        # se o banco relatar a constraint de chave em vez da de referência)
        # continua real, para não mascarar a asserção final.
        if kwargs == {"chave_confirmacao": chave}:
            contagem["chave"] += 1
            if contagem["chave"] == 1:
                return entradas_module.Entrada.objects.none()
        return consulta_real(*args, **kwargs)

    monkeypatch.setattr(
        entradas_module.Entrada.objects, "filter", _filter_simulando_janela_de_corrida
    )
    # `validar_entrada` também faria a checagem de referência (sem lock) e
    # recusaria cedo demais para exercitar o `IntegrityError` — neutralizada
    # pelo mesmo motivo do bloco "sob lock" acima.
    monkeypatch.setattr(entradas_module, "validar_entrada", lambda dados: None)

    mensagem_constraint_de_referencia = (
        'duplicate key value violates unique constraint '
        '"estoque_entrada_referencia_unica"'
    )
    with mock.patch.object(
        entradas_module.Entrada.objects,
        "create",
        side_effect=IntegrityError(mensagem_constraint_de_referencia),
    ):
        with pytest.raises(EntradaJaRegistrada) as excinfo:
            registrar_entrada(dados, funcionario_almoxarifado)

    assert excinfo.value.entrada.pk == entrada_existente.pk
    assert Entrada.objects.count() == 1
    assert ItemEntrada.objects.filter(entrada=entrada_existente).count() == 1
    material.refresh_from_db()
    assert material.saldo == Decimal("2.000"), "a quantidade não pode ter sido aplicada duas vezes"


# ---------------------------------------------------------------------------
# Mesma referência, chaves diferentes, em paralelo: uma entrada, a outra
# ReferenciaJaUsada (FR-007a).
# ---------------------------------------------------------------------------


def test_mesma_referencia_chaves_diferentes_concorrente_produz_uma_entrada_e_uma_ja_usada(
    funcionario_almoxarifado, criar_material, criar_fornecedor
):
    material = criar_material("400.000.003", Decimal("0.000"))
    fornecedor = criar_fornecedor("4001", "Fornecedor Concorrência")
    numero = "NF-CONCORRENTE-0001"

    def _tentativa():
        dados = _entrada_informada(
            numero_documento=numero,
            emitente_id=fornecedor.pk,
            itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("1.000"))],
        )
        return registrar_entrada(dados, funcionario_almoxarifado)

    resultados = _rodar_threads({"a": _tentativa, "b": _tentativa})

    sucessos = [r for r in resultados.values() if not isinstance(r, Exception)]
    falhas = [r for r in resultados.values() if isinstance(r, Exception)]
    assert len(sucessos) == 1, f"esperava exatamente uma entrada vencedora; {resultados!r}"
    assert len(falhas) == 1
    (erro,) = falhas
    assert isinstance(erro, ReferenciaJaUsada), (
        f"a segunda confirmação da MESMA referência deveria falhar com ReferenciaJaUsada, "
        f"não {erro!r}"
    )
    assert Entrada.objects.filter(numero_documento=numero).count() == 1


# ---------------------------------------------------------------------------
# Emitente bloqueado por uma reimportação de fornecedores entre "Revisar" e
# "Confirmar" (Edge Cases da spec, INV-SUPPLIER-005, research R10).
#
# Sequencial, sem threads — mesmo padrão de
# `tests/test_catalogo_atomicidade.py`
# (`test_saldo_de_material_fora_do_arquivo_alterado_nao_invalida_a_previa`,
# `test_outra_execucao_confirmada_entre_previa_e_confirmacao_torna_previa_
# desatualizada`): o que importa é que `registrar_entrada` NUNCA confia numa
# validação anterior (`validar_entrada`, chamada por "Revisar") e relê o
# estado atual do fornecedor na própria confirmação.
#
# IMPORTANTE (revisão do code-reviewer): este teste prova só que
# `registrar_entrada` chama `validar_entrada` de novo no início (releitura
# SEM lock, antes do `transaction.atomic()`) — o bloqueio já é aplicado
# ANTES da chamada, então é essa checagem inicial que recusa, não a
# reconferência sob `select_for_update()` mais abaixo. Os dois testes
# seguintes isolam especificamente essa reconferência sob lock (o caminho
# que só é alcançado quando `validar_entrada` não pegou o problema antes).
# ---------------------------------------------------------------------------


def test_emitente_bloqueado_entre_revisar_e_confirmar_recusa_a_confirmacao(
    funcionario_almoxarifado, criar_material, criar_fornecedor
):
    material = criar_material("400.000.004", Decimal("0.000"))
    fornecedor = criar_fornecedor("4002", "Fornecedor Revisado")
    dados = _entrada_informada(
        emitente_id=fornecedor.pk,
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("1.000"))],
    )

    validar_entrada(dados)  # "Revisar": passa, fornecedor ainda liberado

    # Reimportação concorrente de fornecedores bloqueia o emitente ANTES da
    # confirmação chegar (mesmo efeito de `fornecedores.importacao.aplicar_plano`
    # sobre `bloqueado`, sem depender do parser).
    from fornecedores.models import Fornecedor

    Fornecedor.objects.filter(pk=fornecedor.pk).update(bloqueado=True)

    with pytest.raises((EntradaInvalida, EmitenteIndisponivel)):
        registrar_entrada(dados, funcionario_almoxarifado)

    assert Entrada.objects.count() == 0
    material.refresh_from_db()
    assert material.saldo == Decimal("0.000")


# ---------------------------------------------------------------------------
# NOVO (revisão do code-reviewer): o bloco "sob lock" de `registrar_entrada`
# (reconferência de `Fornecedor.bloqueado` e de `SaldoAcimaDoLimite` dentro
# do `transaction.atomic()`, sob `select_for_update()`) nunca era exercitado
# pelo teste acima — a recusa sempre vinha da chamada de `validar_entrada`
# no início da função, SEM lock. Os dois testes a seguir neutralizam
# `validar_entrada` (`monkeypatch`, sem tocar produção) para forçar a
# execução a chegar até o bloco sob lock e provar que ELE, sozinho, recusa
# corretamente — sem gravar nada. Removendo mentalmente o bloco sob lock de
# `estoque/entradas.py`, estes dois testes passariam a falhar (a entrada
# seria criada com o emitente bloqueado, ou com saldo acima do limite).
# ---------------------------------------------------------------------------


def test_emitente_bloqueado_sob_lock_e_recusado_quando_validar_entrada_nao_pega(
    funcionario_almoxarifado, criar_material, criar_fornecedor, monkeypatch
):
    material = criar_material("400.000.009", Decimal("0.000"))
    fornecedor = criar_fornecedor("4003", "Fornecedor Bloqueado Sob Lock", bloqueado=True)
    dados = _entrada_informada(
        emitente_id=fornecedor.pk,
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("1.000"))],
    )

    # Neutraliza só `validar_entrada` (a checagem SEM lock, chamada logo no
    # início de `registrar_entrada`) para isolar a reconferência sob lock.
    monkeypatch.setattr(entradas_module, "validar_entrada", lambda dados: None)

    with pytest.raises(EmitenteIndisponivel):
        registrar_entrada(dados, funcionario_almoxarifado)

    assert Entrada.objects.count() == 0
    assert ItemEntrada.objects.count() == 0
    assert MovimentacaoEstoque.objects.count() == 0
    material.refresh_from_db()
    assert material.saldo == Decimal("0.000")


def test_saldo_acima_do_limite_sob_lock_e_recusado_quando_validar_entrada_nao_pega(
    funcionario_almoxarifado, criar_material, monkeypatch
):
    material = criar_material("400.000.010", LIMITE_SALDO - Decimal("0.500"))
    dados = _entrada_informada(
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("1.000"))]
    )

    monkeypatch.setattr(entradas_module, "validar_entrada", lambda dados: None)

    with pytest.raises(SaldoAcimaDoLimite):
        registrar_entrada(dados, funcionario_almoxarifado)

    assert Entrada.objects.count() == 0
    assert ItemEntrada.objects.count() == 0
    assert MovimentacaoEstoque.objects.count() == 0
    material.refresh_from_db()
    assert material.saldo == LIMITE_SALDO - Decimal("0.500")


# ---------------------------------------------------------------------------
# NOVO (revisão T004 do test-engineer): duas entradas concorrentes com os
# MESMOS dois materiais, em ORDEM INVERTIDA no formulário, não podem causar
# deadlock — só é seguro porque `registrar_entrada` trava os materiais em
# ordem fixa por `pk` (research R5), nunca na ordem em que o usuário os
# adicionou à composição. Uma implementação que trave na ordem da lista
# (em vez de reordenar por `pk`) produziria um deadlock clássico A→B / B→A
# aqui, detectado pelo Postgres (ou pelo `lock_timeout`) em vez de silêncio.
# ---------------------------------------------------------------------------


def test_duas_entradas_com_os_mesmos_dois_materiais_em_ordem_invertida_nao_causam_deadlock(
    funcionario_almoxarifado, criar_material
):
    material_a = criar_material("400.000.005", Decimal("0.000"))
    material_b = criar_material("400.000.006", Decimal("0.000"))

    def _entrada_ordem_ab():
        dados = _entrada_informada(
            itens=[
                ItemInformado(material_id=material_a.pk, quantidade=Decimal("1.000")),
                ItemInformado(material_id=material_b.pk, quantidade=Decimal("2.000")),
            ]
        )
        return registrar_entrada(dados, funcionario_almoxarifado)

    def _entrada_ordem_ba():
        dados = _entrada_informada(
            itens=[
                ItemInformado(material_id=material_b.pk, quantidade=Decimal("3.000")),
                ItemInformado(material_id=material_a.pk, quantidade=Decimal("4.000")),
            ]
        )
        return registrar_entrada(dados, funcionario_almoxarifado)

    resultados = _rodar_threads({"ab": _entrada_ordem_ab, "ba": _entrada_ordem_ba})

    falhas = {nome: r for nome, r in resultados.items() if isinstance(r, Exception)}
    assert not falhas, (
        f"as duas entradas deveriam ter sido bem-sucedidas (lock ordenado por pk evita "
        f"deadlock); falhas: {falhas}"
    )

    material_a.refresh_from_db()
    material_b.refresh_from_db()
    assert material_a.saldo == Decimal("5.000")  # 1 + 4
    assert material_b.saldo == Decimal("5.000")  # 2 + 3


# ---------------------------------------------------------------------------
# Entrada concorrente com reimportação do catálogo sobre o MESMO material
# (INV-STOCK-002; ambos os fluxos travam Material por pk crescente —
# research R5).
#
# CORREÇÃO (revisão do code-reviewer, P2): a versão anterior deste teste
# esperava que NENHUMA das duas operações falhasse. Isso está errado: a
# impressão digital da prévia de reimportação inclui `divergencias[].
# saldo_wms` (`catalogo/importacao.py::_serializar_para_impressao_digital`),
# e `confirmar_importacao` recalcula o plano com `bloquear=True` sob o lock
# do material. Se a ENTRADA travar o material primeiro (e commitar antes de
# a reimportação conseguir o lock), a reimportação vê o saldo já +5 e
# levanta `PreviaDesatualizada` — comportamento CORRETO da 001, não uma
# falha de teste. Os dois desfechos legítimos:
#   (a) entrada trava depois: reimportação confirma normalmente, entrada
#       sucede depois, saldo final = saldo_antes + 5;
#   (b) entrada trava antes: reimportação recusa com `PreviaDesatualizada`
#       sem gravar nada, entrada sucede, saldo final = saldo_antes + 5.
# Em nenhum dos dois casos pode haver deadlock/`OperationalError`, e a
# entrada NUNCA pode falhar. Os dois testes sequenciais abaixo forçam cada
# ordem deterministicamente (sem sleep); o teste com threads reais, na
# sequência, prova só a ausência de deadlock sob a corrida de verdade,
# aceitando os dois desfechos.
# ---------------------------------------------------------------------------


def _preparar_reimportacao_concorrente(funcionario_almoxarifado, csv_fixture):
    """Carga inicial confirmada + plano/pedido da reimportação calculados
    ANTES de qualquer entrada rodar (mesma pré-condição dos três testes
    abaixo). Devolve `(material, saldo_antes, pedido_reimportacao,
    plano_reimportacao, catalogo_importacao)`."""
    from catalogo import importacao as catalogo_importacao
    from catalogo.models import Material

    conteudo_inicial = csv_fixture("carga_inicial_valida.csv")
    plano_inicial = catalogo_importacao.calcular_plano(conteudo_inicial)
    pedido_inicial = catalogo_importacao.PedidoPrevia(
        token=str(uuid.uuid4()),
        nome_arquivo="inicial.csv",
        tamanho=len(conteudo_inicial),
        sha256=plano_inicial.sha256_arquivo,
        conteudo=conteudo_inicial,
    )
    catalogo_importacao.confirmar_importacao(
        pedido_inicial, plano_inicial.impressao_digital, funcionario_almoxarifado
    )
    material = Material.objects.get(cadpro="000.000.002")
    saldo_antes = material.saldo

    conteudo_reimportacao = csv_fixture("reimportacao.csv")
    plano_reimportacao = catalogo_importacao.calcular_plano(conteudo_reimportacao)
    pedido_reimportacao = catalogo_importacao.PedidoPrevia(
        token=str(uuid.uuid4()),
        nome_arquivo="reimportacao.csv",
        tamanho=len(conteudo_reimportacao),
        sha256=plano_reimportacao.sha256_arquivo,
        conteudo=conteudo_reimportacao,
    )
    return material, saldo_antes, pedido_reimportacao, plano_reimportacao, catalogo_importacao


def test_entrada_antes_da_reimportacao_do_mesmo_material_torna_a_previa_desatualizada(
    funcionario_almoxarifado, csv_fixture
):
    """Ordem forçada sequencialmente: a entrada COMMITA por completo antes
    de a reimportação tentar confirmar. Como a prévia da reimportação foi
    calculada sobre o saldo ANTIGO, a impressão digital recalculada sob
    lock diverge — `PreviaDesatualizada`, sem gravar nada (desfecho (b))."""
    material, saldo_antes, pedido_reimportacao, plano_reimportacao, catalogo_importacao = (
        _preparar_reimportacao_concorrente(funcionario_almoxarifado, csv_fixture)
    )

    dados = _entrada_informada(
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("5.000"))]
    )
    registrar_entrada(dados, funcionario_almoxarifado)

    from catalogo.models import ExecucaoImportacao

    execucoes_antes = ExecucaoImportacao.objects.count()

    with pytest.raises(catalogo_importacao.PreviaDesatualizada):
        catalogo_importacao.confirmar_importacao(
            pedido_reimportacao, plano_reimportacao.impressao_digital, funcionario_almoxarifado
        )

    assert ExecucaoImportacao.objects.count() == execucoes_antes, (
        "a prévia desatualizada não pode ter gravado nenhuma execução"
    )
    material.refresh_from_db()
    assert material.saldo == saldo_antes + Decimal("5.000")


def test_reimportacao_antes_da_entrada_do_mesmo_material_confirma_normalmente(
    funcionario_almoxarifado, csv_fixture
):
    """Ordem forçada sequencialmente (inversa da anterior): a reimportação
    COMMITA por completo antes de a entrada rodar. Nada mudou desde a
    prévia, então a impressão digital bate e a confirmação sucede
    normalmente (desfecho (a)); a entrada, depois, sucede sem qualquer
    interferência — a reimportação nunca escreve `saldo` de material
    existente (`INV-STOCK-002`)."""
    material, saldo_antes, pedido_reimportacao, plano_reimportacao, catalogo_importacao = (
        _preparar_reimportacao_concorrente(funcionario_almoxarifado, csv_fixture)
    )

    catalogo_importacao.confirmar_importacao(
        pedido_reimportacao, plano_reimportacao.impressao_digital, funcionario_almoxarifado
    )
    material.refresh_from_db()
    assert material.saldo == saldo_antes, "a reimportação não pode ter tocado o saldo"

    dados = _entrada_informada(
        itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("5.000"))]
    )
    registrar_entrada(dados, funcionario_almoxarifado)

    material.refresh_from_db()
    assert material.saldo == saldo_antes + Decimal("5.000")


def test_entrada_concorrente_com_reimportacao_do_catalogo_sem_deadlock_e_saldo_preservado(
    funcionario_almoxarifado, csv_fixture
):
    """Concorrência real (threads): a entrada NUNCA pode falhar, e a
    reimportação só pode terminar de duas formas (comentário acima) — nunca
    com `OperationalError`/deadlock. Não afirma qual das duas ordens
    venceu a corrida (os dois testes sequenciais acima já provam cada
    ordem deterministicamente); afirma só que o resultado observável é
    sempre um dos dois desfechos legítimos."""
    from django.db import OperationalError

    material, saldo_antes, pedido_reimportacao, plano_reimportacao, catalogo_importacao = (
        _preparar_reimportacao_concorrente(funcionario_almoxarifado, csv_fixture)
    )

    def _registrar():
        dados = _entrada_informada(
            itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("5.000"))]
        )
        return registrar_entrada(dados, funcionario_almoxarifado)

    def _reimportar():
        return catalogo_importacao.confirmar_importacao(
            pedido_reimportacao, plano_reimportacao.impressao_digital, funcionario_almoxarifado
        )

    resultados = _rodar_threads({"entrada": _registrar, "reimportacao": _reimportar})

    erro_entrada = resultados["entrada"] if isinstance(resultados["entrada"], Exception) else None
    assert erro_entrada is None, f"a entrada nunca pode falhar sob essa corrida: {erro_entrada!r}"

    erro_reimportacao = (
        resultados["reimportacao"] if isinstance(resultados["reimportacao"], Exception) else None
    )
    if erro_reimportacao is not None:
        assert isinstance(erro_reimportacao, catalogo_importacao.PreviaDesatualizada), (
            "se a reimportação falhou sob a corrida, só pode ser por prévia desatualizada "
            f"(saldo alterado pela entrada antes do lock) — nunca por outro erro (deadlock/"
            f"OperationalError incluído); obteve {erro_reimportacao!r}"
        )
    assert not isinstance(erro_entrada, OperationalError)
    assert not isinstance(erro_reimportacao, OperationalError)

    material.refresh_from_db()
    assert material.saldo == saldo_antes + Decimal("5.000"), (
        "INV-STOCK-002: em qualquer ordem, o saldo final é sempre saldo_antes + 5 — a "
        "reimportação nunca escreve saldo de material existente"
    )


# ---------------------------------------------------------------------------
# Dois estornos simultâneos da mesma entrada: um efetivado, o outro
# EntradaJaEstornada (FR-027, SC-009).
# ---------------------------------------------------------------------------


def test_dois_estornos_simultaneos_da_mesma_entrada_produzem_um_efetivado_e_um_ja_estornada(
    funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    material = criar_material("400.000.007", Decimal("0.000"))
    entrada = registrar_entrada(
        _entrada_informada(
            itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("7.000"))]
        ),
        funcionario_almoxarifado,
    )

    def _estornar():
        return estornar_entrada(entrada.pk, "Erro de digitação na quantidade.", chefe_almoxarifado)

    resultados = _rodar_threads({"a": _estornar, "b": _estornar})

    sucessos = [r for r in resultados.values() if not isinstance(r, Exception)]
    falhas = [r for r in resultados.values() if isinstance(r, Exception)]
    assert len(sucessos) == 1, f"esperava exatamente um estorno vencedor; {resultados!r}"
    assert len(falhas) == 1
    (erro,) = falhas
    assert isinstance(erro, EntradaJaEstornada), (
        f"o segundo estorno da MESMA entrada deveria falhar com EntradaJaEstornada, não {erro!r}"
    )

    entrada.refresh_from_db()
    assert entrada.estornada is True
    material.refresh_from_db()
    assert material.saldo == Decimal("0.000"), "o estorno não pode ter sido aplicado duas vezes"


# ---------------------------------------------------------------------------
# Estorno concorrente com uma redução direta de saldo do MESMO material sob
# `select_for_update`: nunca deixa saldo negativo (INV-STOCK-001) — nem por
# lost update (a segunda operação a travar precisa reler o saldo já
# atualizado pela primeira, não o que leu antes de a corrida começar).
# ---------------------------------------------------------------------------


def test_estorno_concorrente_com_reducao_direta_de_saldo_nunca_deixa_saldo_negativo(
    funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    from catalogo.models import Material

    material = criar_material("400.000.008", Decimal("0.000"))
    entrada = registrar_entrada(
        _entrada_informada(
            itens=[ItemInformado(material_id=material.pk, quantidade=Decimal("10.000"))]
        ),
        funcionario_almoxarifado,
    )
    material.refresh_from_db()
    assert material.saldo == Decimal("10.000")

    def _estornar():
        return estornar_entrada(entrada.pk, "Erro de digitação na quantidade.", chefe_almoxarifado)

    def _reduzir_direto():
        """Simula outra operação de baixa de estoque (fora do escopo desta
        feature) que também trava a linha do material antes de decidir o
        novo saldo — disciplina mínima que qualquer operação de estoque
        precisa seguir para não perder atualização."""
        with transaction.atomic():
            atual = Material.objects.select_for_update().get(pk=material.pk)
            novo_saldo = atual.saldo - Decimal("8.000")
            if novo_saldo < 0:
                raise ValueError("saldo insuficiente para a redução direta")
            Material.objects.filter(pk=material.pk).update(saldo=novo_saldo)
        return novo_saldo

    resultados = _rodar_threads({"estorno": _estornar, "reducao": _reduzir_direto})

    material.refresh_from_db()
    assert material.saldo >= Decimal("0.000"), "INV-STOCK-001: saldo nunca pode ficar negativo"

    entrada.refresh_from_db()
    erro_estorno = resultados["estorno"] if isinstance(resultados["estorno"], Exception) else None
    erro_reducao = resultados["reducao"] if isinstance(resultados["reducao"], Exception) else None

    # Exatamente uma das duas operações pode ter sido efetivada por
    # completo; a outra precisa ter sido recusada (nunca as duas aplicadas
    # cegamente, o que deixaria -8 ou não refletiria a ordem real).
    if entrada.estornada:
        assert material.saldo == Decimal("0.000")
        assert isinstance(erro_reducao, ValueError), (
            "se o estorno venceu a corrida, a redução direta, ao reler sob lock, deveria "
            f"ter sido recusada por saldo insuficiente; obteve {resultados['reducao']!r}"
        )
    else:
        assert material.saldo == Decimal("2.000")
        assert isinstance(erro_estorno, EstornoBloqueadoPorSaldo), (
            "se a redução direta venceu a corrida, o estorno, ao reler sob lock, deveria "
            f"ter sido bloqueado por saldo insuficiente; obteve {resultados['estorno']!r}"
        )
