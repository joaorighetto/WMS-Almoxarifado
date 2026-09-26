"""Testes de reimportação de fornecedores (T028 — US4).

Usa as 5 fixtures `reimportacao_*.csv` de `tests/fixtures/fornecedores/`
(README no mesmo diretório): `reimportacao_base.csv` (5 fornecedores,
`700001`–`700005`, um já bloqueado) precisa ser importado primeiro; as
demais trazem exatamente uma mudança em relação à base.

`fornecedores.importacao.calcular_plano`/`aplicar_plano` JÁ estão
implementados (US1) e já calculam o diff/gravam `AlteracaoFornecedor` — os
testes de comportamento de domínio abaixo (US4 cenários 1–4) exercitam
código real e devem passar agora. Os que dependem da EXIBIÇÃO da seção de
alterações na PRÉVIA (`ImportacaoPreviaView`/`importacao_previa.html`)
falham: `_contexto_previa` (`fornecedores/views.py`) ainda só expõe
`excecoes_pagina`, sem nada equivalente para `plano.atualizacoes`. A
exibição no DETALHE da execução é `tests/test_fornecedores_historico.py`
(T025) — não duplicada aqui.

US4 cenário 5 (fornecedor já emitente de entrada continua vinculado após a
reimportação) depende de `Entrada`/emitente (spec 003, ainda não
implementada) — fora do alcance desta feature; não testado aqui.

Convenção da seção de alterações (decisão do coordenador, rodada de
2026-09-25, igual em prévia e detalhe): `data-secao="alteracoes"`,
paginação `?pagina_alteracoes=`, colunas campo/valor anterior/valor novo,
fornecedor identificado por `codif` e `nome`.
"""

import hashlib
import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import Client
from django.urls import reverse

from catalogo.leitura_scpi import normalizar_para_busca
from fornecedores.models import AlteracaoFornecedor, Fornecedor

pytestmark = pytest.mark.django_db


def _cliente_autenticado(usuario):
    client = Client()
    client.force_login(usuario)
    return client


def _importar_diretamente(conteudo, usuario, nome_arquivo="arquivo.csv"):
    from fornecedores import importacao
    from fornecedores import leitura_fornecedores as lf

    leitura = lf.ler_fornecedores(conteudo)
    sha256_arquivo = hashlib.sha256(conteudo).hexdigest()
    plano = importacao.calcular_plano(leitura, sha256_arquivo)
    pedido = importacao.PedidoPrevia(
        token=str(uuid.uuid4()),
        nome_arquivo=nome_arquivo,
        tamanho=len(conteudo),
        sha256=sha256_arquivo,
        leitura=leitura,
    )
    return importacao.confirmar_importacao(pedido, plano.impressao_digital, usuario)


@pytest.fixture
def base_importada(chefe_almoxarifado, csv_fornecedores):
    """Importa `reimportacao_base.csv` — 5 fornecedores (`700001`–`700005`,
    `700003` já bloqueado com motivo) — pré-condição de toda reimportação
    abaixo."""
    conteudo = csv_fornecedores("reimportacao_base.csv")
    return _importar_diretamente(conteudo, chefe_almoxarifado, "reimportacao_base.csv")


# ---------------------------------------------------------------------------
# Cenário 1 (Acceptance Scenario 1, spec.md): nome alterado, rastreável.
# ---------------------------------------------------------------------------


def test_nome_alterado_e_atualizado_e_rastreado(
    base_importada, chefe_almoxarifado, csv_fornecedores
):
    nome_antes = Fornecedor.objects.get(codif="700001").nome
    conteudo = csv_fornecedores("reimportacao_nome_alterado.csv")

    execucao = _importar_diretamente(conteudo, chefe_almoxarifado, "reimportacao_nome_alterado.csv")

    fornecedor = Fornecedor.objects.get(codif="700001")
    assert fornecedor.nome == "FORNECEDOR ALFA REIMPORT REVISADO"
    assert fornecedor.nome != nome_antes

    alteracao = AlteracaoFornecedor.objects.get(
        execucao=execucao, fornecedor=fornecedor, campo="nome"
    )
    assert alteracao.valor_anterior == nome_antes
    assert alteracao.valor_novo == "FORNECEDOR ALFA REIMPORT REVISADO"
    assert alteracao.execucao.executada_por_id == chefe_almoxarifado.pk
    assert alteracao.execucao.concluida_em is not None

    assert execucao.total_atualizados == 5, "os 5 fornecedores da base existem: todos atualizados"
    assert execucao.total_atualizados_com_alteracao == 1, "só 700001 mudou de fato"


def test_nome_alterado_reescreve_nome_busca(base_importada, chefe_almoxarifado, csv_fornecedores):
    conteudo = csv_fornecedores("reimportacao_nome_alterado.csv")

    _importar_diretamente(conteudo, chefe_almoxarifado, "reimportacao_nome_alterado.csv")

    fornecedor = Fornecedor.objects.get(codif="700001")
    nome_busca_esperado = normalizar_para_busca(f"{fornecedor.nome} {fornecedor.nome_fantasia}")
    assert fornecedor.nome_busca == nome_busca_esperado
    assert fornecedor.nome_busca != normalizar_para_busca("FORNECEDOR ALFA REIMPORT ALFA")


# ---------------------------------------------------------------------------
# Cenário 2: desbloqueado → bloqueado.
# ---------------------------------------------------------------------------


def test_desbloqueado_passa_a_bloqueado(base_importada, chefe_almoxarifado, csv_fornecedores):
    assert Fornecedor.objects.get(codif="700002").bloqueado is False, "pré-condição"
    conteudo = csv_fornecedores("reimportacao_bloqueio_s_para_b.csv")

    execucao = _importar_diretamente(
        conteudo, chefe_almoxarifado, "reimportacao_bloqueio_s_para_b.csv"
    )

    fornecedor = Fornecedor.objects.get(codif="700002")
    assert fornecedor.bloqueado is True
    assert fornecedor.motivo_bloqueio == "FORNECEDOR NAO PODE SER UTILIZADO"

    alteracao_bloqueado = AlteracaoFornecedor.objects.get(
        execucao=execucao, fornecedor=fornecedor, campo="bloqueado"
    )
    assert alteracao_bloqueado.valor_anterior == "S"
    assert alteracao_bloqueado.valor_novo == "B"


# ---------------------------------------------------------------------------
# Cenário 3: bloqueado → desbloqueado.
# ---------------------------------------------------------------------------


def test_bloqueado_volta_a_desbloqueado(base_importada, chefe_almoxarifado, csv_fornecedores):
    assert Fornecedor.objects.get(codif="700003").bloqueado is True, "pré-condição"
    conteudo = csv_fornecedores("reimportacao_bloqueio_b_para_s.csv")

    execucao = _importar_diretamente(
        conteudo, chefe_almoxarifado, "reimportacao_bloqueio_b_para_s.csv"
    )

    fornecedor = Fornecedor.objects.get(codif="700003")
    assert fornecedor.bloqueado is False

    alteracao_bloqueado = AlteracaoFornecedor.objects.get(
        execucao=execucao, fornecedor=fornecedor, campo="bloqueado"
    )
    assert alteracao_bloqueado.valor_anterior == "B"
    assert alteracao_bloqueado.valor_novo == "S"


# ---------------------------------------------------------------------------
# Cenário 4: ausente do arquivo permanece inalterado, contado.
# ---------------------------------------------------------------------------


def test_fornecedor_ausente_do_arquivo_permanece_inalterado_e_e_contado(
    base_importada, chefe_almoxarifado, csv_fornecedores
):
    antes = Fornecedor.objects.get(codif="700004")
    campos_antes = (
        antes.nome, antes.nome_fantasia, antes.documento, antes.tipo,
        antes.bloqueado, antes.motivo_bloqueio, antes.tipo_bloqueio,
    )
    conteudo = csv_fornecedores("reimportacao_registro_removido.csv")

    execucao = _importar_diretamente(
        conteudo, chefe_almoxarifado, "reimportacao_registro_removido.csv"
    )

    depois = Fornecedor.objects.get(codif="700004")
    campos_depois = (
        depois.nome, depois.nome_fantasia, depois.documento, depois.tipo,
        depois.bloqueado, depois.motivo_bloqueio, depois.tipo_bloqueio,
    )
    assert campos_antes == campos_depois
    assert not AlteracaoFornecedor.objects.filter(fornecedor=antes).exists()
    assert execucao.total_ausentes_no_arquivo == 1
    assert execucao.total_recebidos == 4, "só 4 dos 5 vêm no arquivo desta variação"


# ---------------------------------------------------------------------------
# codif/execucao_origem nunca mudam (INV-SUPPLIER-001/002).
# ---------------------------------------------------------------------------


def test_codif_e_execucao_origem_nunca_mudam_na_reimportacao(
    base_importada, chefe_almoxarifado, csv_fornecedores
):
    fornecedor_antes = Fornecedor.objects.get(codif="700001")
    execucao_origem_antes = fornecedor_antes.execucao_origem_id
    conteudo = csv_fornecedores("reimportacao_nome_alterado.csv")

    _importar_diretamente(conteudo, chefe_almoxarifado, "reimportacao_nome_alterado.csv")

    fornecedor_depois = Fornecedor.objects.get(pk=fornecedor_antes.pk)
    assert fornecedor_depois.codif == "700001"
    assert fornecedor_depois.execucao_origem_id == execucao_origem_antes


# ---------------------------------------------------------------------------
# Mesmo arquivo duas vezes → 0 alterações.
# ---------------------------------------------------------------------------


def test_mesmo_arquivo_reimportado_duas_vezes_produz_zero_alteracoes(
    base_importada, chefe_almoxarifado, csv_fornecedores
):
    conteudo_identico = csv_fornecedores("reimportacao_identica.csv")
    assert conteudo_identico == csv_fornecedores("reimportacao_base.csv"), (
        "pré-condição da fixture: byte-idêntico à base"
    )

    execucao = _importar_diretamente(
        conteudo_identico, chefe_almoxarifado, "reimportacao_identica.csv"
    )

    assert execucao.total_atualizados == 5
    assert execucao.total_atualizados_com_alteracao == 0
    assert not AlteracaoFornecedor.objects.filter(execucao=execucao).exists()


# ---------------------------------------------------------------------------
# Prévia desatualizada: o cadastro muda entre a prévia e a confirmação
# (mesmas fixtures de reimportação, complementando o cenário genérico já
# coberto por tests/test_fornecedores_atomicidade.py, T010).
# ---------------------------------------------------------------------------


def test_previa_de_reimportacao_fica_desatualizada_se_outra_confirmacao_muda_o_cadastro_antes(
    base_importada, chefe_almoxarifado, csv_fornecedores
):
    from fornecedores import importacao
    from fornecedores import leitura_fornecedores as lf

    conteudo = csv_fornecedores("reimportacao_nome_alterado.csv")
    leitura = lf.ler_fornecedores(conteudo)
    sha256_arquivo = hashlib.sha256(conteudo).hexdigest()
    plano_previa = importacao.calcular_plano(leitura, sha256_arquivo)
    pedido = importacao.PedidoPrevia(
        token=str(uuid.uuid4()), nome_arquivo="reimport.csv",
        tamanho=len(conteudo), sha256=sha256_arquivo, leitura=leitura,
    )

    # Outra reimportação confirmada ANTES, mudando o mesmo fornecedor
    # (700001) que a prévia acima referencia.
    conteudo_concorrente = csv_fornecedores("reimportacao_bloqueio_s_para_b.csv")
    _importar_diretamente(conteudo_concorrente, chefe_almoxarifado, "concorrente.csv")

    with pytest.raises(importacao.PreviaDesatualizada):
        importacao.confirmar_importacao(pedido, plano_previa.impressao_digital, chefe_almoxarifado)


# ---------------------------------------------------------------------------
# Prévia (fluxo HTTP): a seção de alterações precisa aparecer ANTES de
# confirmar — convenção do coordenador (data-secao="alteracoes",
# pagina_alteracoes). Falha hoje: `_contexto_previa` não expõe as
# atualizações do plano.
# ---------------------------------------------------------------------------


def test_previa_de_reimportacao_mostra_secao_de_alteracoes_sem_gravar_nada(
    base_importada, chefe_almoxarifado, csv_fornecedores
):
    client = _cliente_autenticado(chefe_almoxarifado)
    conteudo = csv_fornecedores("reimportacao_nome_alterado.csv")
    arquivo = SimpleUploadedFile("reimport.csv", conteudo, content_type="text/csv")

    resposta_envio = client.post(reverse("fornecedores:importacao_envio"), {"arquivo": arquivo})
    assert resposta_envio.status_code == 302

    antes = AlteracaoFornecedor.objects.count()
    resposta_previa = client.get(reverse("fornecedores:importacao_previa"))

    assert resposta_previa.status_code == 200
    assert AlteracaoFornecedor.objects.count() == antes == 0, "a prévia não pode gravar nada"

    conteudo_html = resposta_previa.content.decode("utf-8")
    assert 'data-secao="alteracoes"' in conteudo_html
    assert "700001" in conteudo_html
    assert "FORNECEDOR ALFA REIMPORT REVISADO" in conteudo_html

    resposta_paginada = client.get(
        reverse("fornecedores:importacao_previa"), {"pagina_alteracoes": "1"}
    )
    assert resposta_paginada.status_code == 200


def test_previa_de_reimportacao_sem_alteracoes_marca_secao_vazia(
    base_importada, chefe_almoxarifado, csv_fornecedores
):
    client = _cliente_autenticado(chefe_almoxarifado)
    conteudo = csv_fornecedores("reimportacao_identica.csv")
    arquivo = SimpleUploadedFile("identica.csv", conteudo, content_type="text/csv")

    client.post(reverse("fornecedores:importacao_envio"), {"arquivo": arquivo})
    resposta = client.get(reverse("fornecedores:importacao_previa"))

    assert resposta.status_code == 200
    assert 'data-secao="alteracoes"' in resposta.content.decode("utf-8")


# ---------------------------------------------------------------------------
# Situação de bloqueio em destaque na prévia (P1 do gate visual, rodada de
# revisão do dono do produto): `total_passam_a_bloqueado`,
# `total_voltam_a_liberado` (a partir de `plano.atualizacoes`) e
# `total_chegam_bloqueados` (a partir de `plano.insercoes`) no contexto de
# `ImportacaoPreviaView`.
# ---------------------------------------------------------------------------


def test_previa_mostra_total_de_fornecedores_que_passam_a_bloqueado(
    base_importada, chefe_almoxarifado, csv_fornecedores
):
    client = _cliente_autenticado(chefe_almoxarifado)
    conteudo = csv_fornecedores("reimportacao_bloqueio_s_para_b.csv")
    arquivo = SimpleUploadedFile("bloqueio_s_para_b.csv", conteudo, content_type="text/csv")

    client.post(reverse("fornecedores:importacao_envio"), {"arquivo": arquivo})
    resposta = client.get(reverse("fornecedores:importacao_previa"))

    assert resposta.status_code == 200
    assert resposta.context["total_passam_a_bloqueado"] == 1
    assert resposta.context["total_voltam_a_liberado"] == 0
    assert resposta.context["total_chegam_bloqueados"] == 0


def test_previa_mostra_total_de_fornecedores_que_voltam_a_liberado(
    base_importada, chefe_almoxarifado, csv_fornecedores
):
    client = _cliente_autenticado(chefe_almoxarifado)
    conteudo = csv_fornecedores("reimportacao_bloqueio_b_para_s.csv")
    arquivo = SimpleUploadedFile("bloqueio_b_para_s.csv", conteudo, content_type="text/csv")

    client.post(reverse("fornecedores:importacao_envio"), {"arquivo": arquivo})
    resposta = client.get(reverse("fornecedores:importacao_previa"))

    assert resposta.status_code == 200
    assert resposta.context["total_voltam_a_liberado"] == 1
    assert resposta.context["total_passam_a_bloqueado"] == 0
    assert resposta.context["total_chegam_bloqueados"] == 0


def test_previa_mostra_total_de_fornecedores_novos_que_chegam_bloqueados(
    chefe_almoxarifado, csv_fornecedores
):
    """Cadastro vazio (sem `base_importada`): `valido_basico.csv` insere 4
    fornecedores, um deles (`600004`) já bloqueado — só inserção, nenhuma
    atualização, então `total_passam_a_bloqueado`/`total_voltam_a_liberado`
    ficam em zero."""
    client = _cliente_autenticado(chefe_almoxarifado)
    conteudo = csv_fornecedores("valido_basico.csv")
    arquivo = SimpleUploadedFile("valido_basico.csv", conteudo, content_type="text/csv")

    client.post(reverse("fornecedores:importacao_envio"), {"arquivo": arquivo})
    resposta = client.get(reverse("fornecedores:importacao_previa"))

    assert resposta.status_code == 200
    assert resposta.context["total_chegam_bloqueados"] == 1
    assert resposta.context["total_passam_a_bloqueado"] == 0
    assert resposta.context["total_voltam_a_liberado"] == 0


def test_previa_ordena_alteracoes_do_campo_bloqueado_primeiro(
    base_importada, chefe_almoxarifado, csv_fornecedores
):
    """Situação de bloqueio em destaque (P1 do gate visual): reimporta
    `700001` (nome alterado) e `700002` (bloqueado S→B) na MESMA prévia — sem
    a ordenação, `700001` apareceria primeiro (codif menor); com ela, a
    alteração de `bloqueado` (`700002`) vem primeiro, mesmo com codif maior."""
    conteudo_nome = csv_fornecedores("reimportacao_nome_alterado.csv")
    conteudo_bloqueio = csv_fornecedores("reimportacao_bloqueio_s_para_b.csv")
    linhas_nome = conteudo_nome.decode("utf-8").splitlines()
    linhas_bloqueio = conteudo_bloqueio.decode("utf-8").splitlines()
    # Combina as duas variações num único arquivo: cabeçalho + linha de
    # 700001 (nome alterado, de `reimportacao_nome_alterado.csv`) + linha de
    # 700002 (bloqueio alterado, de `reimportacao_bloqueio_s_para_b.csv`) +
    # as linhas 700003–700005 inalteradas (da variação de nome, que já as
    # traz intactas).
    conteudo_combinado = "\r\n".join(
        [linhas_nome[0], linhas_nome[1], linhas_bloqueio[2], *linhas_nome[3:]]
    ).encode("utf-8")

    client = _cliente_autenticado(chefe_almoxarifado)
    arquivo = SimpleUploadedFile("combinado.csv", conteudo_combinado, content_type="text/csv")
    resposta_envio = client.post(reverse("fornecedores:importacao_envio"), {"arquivo": arquivo})
    assert resposta_envio.status_code == 302

    resposta = client.get(reverse("fornecedores:importacao_previa"))

    assert resposta.status_code == 200
    assert resposta.context["total_passam_a_bloqueado"] == 1, "pré-condição"
    linhas = list(resposta.context["alteracoes_pagina"])
    assert any(linha["campo"] == "bloqueado" for linha in linhas), "pré-condição"
    indice_bloqueado = next(i for i, linha in enumerate(linhas) if linha["campo"] == "bloqueado")
    indice_nome = next(i for i, linha in enumerate(linhas) if linha["campo"] == "nome")
    assert indice_bloqueado < indice_nome, (
        "a alteração de bloqueado (700002) deveria vir antes da de nome (700001), "
        "mesmo com codif maior"
    )


# ---------------------------------------------------------------------------
# Atomicidade adicional específica das fixtures de reimportação: falha
# injetada no PRÓPRIO `bulk_update` (ângulo diferente de
# tests/test_fornecedores_atomicidade.py, T010, que injeta nos
# `bulk_create` — aqui a falha é no passo anterior, o `bulk_update` dos
# campos cadastrais em si) não deixa nenhum dos 5 fornecedores meio
# atualizado, nem `AlteracaoFornecedor` (que só seria criada DEPOIS do
# `bulk_update`, na mesma transação).
# ---------------------------------------------------------------------------


def test_falha_no_bulk_update_desfaz_todos_os_fornecedores_da_reimportacao(
    base_importada, chefe_almoxarifado, csv_fornecedores
):
    from unittest import mock

    from fornecedores import importacao
    from fornecedores import leitura_fornecedores as lf
    from fornecedores.models import ExecucaoImportacaoFornecedores

    snapshot_antes = {
        f.codif: (f.nome, f.bloqueado) for f in Fornecedor.objects.all()
    }

    conteudo = csv_fornecedores("reimportacao_nome_alterado.csv")
    leitura = lf.ler_fornecedores(conteudo)
    sha256_arquivo = hashlib.sha256(conteudo).hexdigest()
    plano = importacao.calcular_plano(leitura, sha256_arquivo)
    assert any(a.alteracoes for a in plano.atualizacoes), (
        "pré-condição: precisa haver ao menos uma alteração real para exercitar bulk_update"
    )

    with mock.patch.object(
        Fornecedor.objects, "bulk_update", side_effect=RuntimeError("falha no bulk_update")
    ):
        with pytest.raises(RuntimeError, match="falha no bulk_update"):
            with transaction.atomic():
                importacao.aplicar_plano(
                    plano,
                    usuario=chefe_almoxarifado,
                    token_previa=str(uuid.uuid4()),
                    nome_arquivo="reimport.csv",
                    tamanho_arquivo=len(conteudo),
                )

    snapshot_depois = {
        f.codif: (f.nome, f.bloqueado) for f in Fornecedor.objects.all()
    }
    assert snapshot_antes == snapshot_depois, (
        "nenhum fornecedor pode ter ficado meio atualizado"
    )
    assert not AlteracaoFornecedor.objects.filter(fornecedor__codif="700001").exists()
    assert ExecucaoImportacaoFornecedores.objects.filter(nome_arquivo="reimport.csv").count() == 0
