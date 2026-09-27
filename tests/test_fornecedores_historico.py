"""Testes do histórico de importações de fornecedores (T025 — US3).

TDD: escrito antes de `fornecedores:historico`/`HistoricoImportacoesView`
existirem — toda chamada de `reverse()` fica dentro do corpo dos testes,
para que a ausência da rota derrube só o teste que a usa (`NoReverseMatch`),
não a coleta do arquivo inteiro (mesma convenção de
`tests/test_catalogo_historico.py`, T036).

`fornecedores:execucao_detalhe` (`ExecucaoDetalheView`) já existe (US1) —
os testes de detalhe abaixo exercitam código real, mas a seção de
alterações (`alteracoes_pagina`, `data-secao="alteracoes"`) ainda não foi
acrescentada à view/template: os testes dessa seção falham agora por
contexto/HTML ausente, não por rota inexistente.

Cobre `contracts/rotas-e-autorizacao.md` → "GET /fornecedores/importacoes/"
e "GET /fornecedores/importacoes/<pk>/". Autorização em si é
`tests/test_fornecedores_permissoes.py` (seção `ROTAS_HISTORICO`); aqui o
usuário é sempre `chefe_almoxarifado`.

Decisão de interface fixada por este arquivo (nenhum contrato fixa colunas
ordenáveis do histórico de fornecedores) — o implementador de T026 precisa
seguir, por analogia direta a `HistoricoImportacoesView` do catálogo, sem
`divergencias` (fornecedores não tem esse conceito):
- **Parâmetro de página**: `pagina` (mesmo da consulta e de
  `catalogo/_paginacao.html`).
- **Colunas ordenáveis**: `concluida` (`concluida_em`, padrão, decrescente),
  `executor` (`executada_por__matricula`), `recebidos` (`total_recebidos`),
  `rejeitados` (`total_rejeitados`). Desempate: `-pk` (execução mais
  recente primeiro), como no catálogo.
- **Seção de alterações no detalhe**: `data-secao="alteracoes"`, paginação
  `?pagina_alteracoes=` (decisão do coordenador, rodada de 2026-09-25) —
  colunas campo, valor anterior, valor novo, e o fornecedor identificado
  pelo `codif` (e `nome`, dado mínimo). O rótulo exibido para `bloqueado`
  (`"S"`/`"B"` na trilha) é decisão do frontend — os testes abaixo
  verificam só que o VALOR aparece, nunca um rótulo específico.
"""

import hashlib
import re
import uuid
from datetime import timedelta

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from fornecedores.models import ExcecaoImportacaoFornecedores, ExecucaoImportacaoFornecedores

pytestmark = pytest.mark.django_db

SHA256_FAKE = "0" * 64
_CABECALHO = "CODIF;NOME;NOM_FANT;INSMF;CODTIP;BLOQ_OPCAO;MSG_BLOQ;TIPO_BLOQ;"


def _cliente_autenticado(usuario):
    client = Client()
    client.force_login(usuario)
    return client


def _linha(codif, nome, bloq="S"):
    return f"{codif};{nome};;;01;{bloq};;;"


def _arquivo(*linhas):
    texto = "\r\n".join([_CABECALHO, *linhas]) + "\r\n"
    return ("﻿" + texto).encode("utf-8")


def _importar_diretamente(conteudo, usuario, nome_arquivo="arquivo.csv"):
    """Confirma uma importação direto pela camada de domínio (sem
    `Client`), no molde de `tests/test_catalogo_historico.py`."""
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


def _criar_execucao(*, executada_por, concluida_em=None, nome_arquivo="carga.csv", **totais):
    valores_totais = {
        "total_recebidos": 1,
        "total_inseridos": 1,
        "total_atualizados": 0,
        "total_atualizados_com_alteracao": 0,
        "total_rejeitados": 0,
        "total_ausentes_no_arquivo": 0,
        **totais,
    }
    return ExecucaoImportacaoFornecedores.objects.create(
        token_previa=uuid.uuid4(),
        executada_por=executada_por,
        concluida_em=concluida_em or timezone.now(),
        nome_arquivo=nome_arquivo,
        tamanho_arquivo=10,
        sha256_arquivo=SHA256_FAKE,
        **valores_totais,
    )


# ---------------------------------------------------------------------------
# Listagem: ordem, dados essenciais, estado vazio, link para o detalhe.
# ---------------------------------------------------------------------------


def test_historico_lista_da_mais_recente_para_a_mais_antiga_com_dados_essenciais(
    client, chefe_almoxarifado, criar_usuario
):
    usuario_antiga = criar_usuario()
    usuario_recente = criar_usuario()
    agora = timezone.now()

    _criar_execucao(
        executada_por=usuario_antiga,
        concluida_em=agora - timedelta(days=1),
        nome_arquivo="carga-antiga.csv",
        total_recebidos=5,
        total_inseridos=5,
    )
    _criar_execucao(
        executada_por=usuario_recente,
        concluida_em=agora,
        nome_arquivo="carga-recente.csv",
        total_recebidos=22,
        total_inseridos=9,
        total_rejeitados=13,
    )

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("fornecedores:historico"))

    assert resposta.status_code == 200
    execucoes_por_arquivo = {e.nome_arquivo: e for e in resposta.context["object_list"]}
    recente = execucoes_por_arquivo["carga-recente.csv"]
    assert (recente.total_recebidos, recente.total_inseridos, recente.total_rejeitados) == (
        22, 9, 13,
    )

    conteudo = resposta.content.decode("utf-8")
    for esperado in (
        usuario_antiga.matricula, usuario_recente.matricula,
        "carga-antiga.csv", "carga-recente.csv",
    ):
        assert esperado in conteudo

    assert conteudo.index("carga-recente.csv") < conteudo.index("carga-antiga.csv")


def test_historico_sem_execucoes_mostra_estado_vazio_explicito(client, chefe_almoxarifado):
    client.force_login(chefe_almoxarifado)

    resposta = client.get(reverse("fornecedores:historico"))

    assert resposta.status_code == 200
    assert len(resposta.context["object_list"]) == 0
    assert 'data-estado="vazio"' in resposta.content.decode("utf-8")


def test_cada_execucao_do_historico_leva_ao_detalhe(client, chefe_almoxarifado, criar_usuario):
    usuario = criar_usuario()
    execucao = _criar_execucao(executada_por=usuario)

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("fornecedores:historico"))

    href_esperado = reverse("fornecedores:execucao_detalhe", args=[execucao.pk])
    assert href_esperado in resposta.content.decode("utf-8")


# ---------------------------------------------------------------------------
# Ordenação por coluna e paginação (`pagina`, 20/página — mesmo padrão do
# catálogo).
# ---------------------------------------------------------------------------


def test_historico_ordem_padrao_e_por_data_de_conclusao_decrescente(
    client, chefe_almoxarifado, criar_usuario
):
    usuario = criar_usuario()
    agora = timezone.now()
    _criar_execucao(
        executada_por=usuario, concluida_em=agora - timedelta(days=1), nome_arquivo="antiga.csv"
    )
    _criar_execucao(executada_por=usuario, concluida_em=agora, nome_arquivo="recente.csv")

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("fornecedores:historico"))

    assert resposta.status_code == 200
    assert resposta.context["ordem"] == "-concluida"
    conteudo = resposta.content.decode("utf-8")
    assert conteudo.index("recente.csv") < conteudo.index("antiga.csv")


@pytest.mark.parametrize("ordem_param, decrescente", [("concluida", False), ("-concluida", True)])
def test_historico_ordenacao_por_concluida_em(
    client, chefe_almoxarifado, criar_usuario, ordem_param, decrescente
):
    usuario = criar_usuario()
    agora = timezone.now()
    _criar_execucao(
        executada_por=usuario, concluida_em=agora - timedelta(days=2), nome_arquivo="c.csv"
    )
    _criar_execucao(
        executada_por=usuario, concluida_em=agora - timedelta(days=1), nome_arquivo="b.csv"
    )
    _criar_execucao(executada_por=usuario, concluida_em=agora, nome_arquivo="a.csv")

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("fornecedores:historico"), {"ordem": ordem_param})

    assert resposta.context["ordem"] == ordem_param
    arquivos = ["c.csv", "b.csv", "a.csv"]
    if decrescente:
        arquivos = list(reversed(arquivos))
    conteudo = resposta.content.decode("utf-8")
    posicoes = [conteudo.index(a) for a in arquivos]
    assert posicoes == sorted(posicoes)


@pytest.mark.parametrize("ordem_param, decrescente", [("executor", False), ("-executor", True)])
def test_historico_ordenacao_por_executor(
    client, chefe_almoxarifado, criar_usuario, ordem_param, decrescente
):
    usuario_a = criar_usuario(matricula="0000001")
    usuario_b = criar_usuario(matricula="0000002")
    usuario_c = criar_usuario(matricula="0000003")
    _criar_execucao(executada_por=usuario_c, nome_arquivo="exec-c.csv")
    _criar_execucao(executada_por=usuario_a, nome_arquivo="exec-a.csv")
    _criar_execucao(executada_por=usuario_b, nome_arquivo="exec-b.csv")

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("fornecedores:historico"), {"ordem": ordem_param})

    arquivos = ["exec-a.csv", "exec-b.csv", "exec-c.csv"]
    if decrescente:
        arquivos = list(reversed(arquivos))
    conteudo = resposta.content.decode("utf-8")
    posicoes = [conteudo.index(a) for a in arquivos]
    assert posicoes == sorted(posicoes)


@pytest.mark.parametrize("ordem_param, decrescente", [("recebidos", False), ("-recebidos", True)])
def test_historico_ordenacao_por_recebidos(
    client, chefe_almoxarifado, criar_usuario, ordem_param, decrescente
):
    usuario = criar_usuario()
    _criar_execucao(
        executada_por=usuario, nome_arquivo="r-baixo.csv", total_recebidos=1, total_inseridos=1
    )
    _criar_execucao(
        executada_por=usuario, nome_arquivo="r-medio.csv", total_recebidos=5, total_inseridos=5
    )
    _criar_execucao(
        executada_por=usuario, nome_arquivo="r-alto.csv", total_recebidos=10, total_inseridos=10
    )

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("fornecedores:historico"), {"ordem": ordem_param})

    arquivos = ["r-baixo.csv", "r-medio.csv", "r-alto.csv"]
    if decrescente:
        arquivos = list(reversed(arquivos))
    conteudo = resposta.content.decode("utf-8")
    posicoes = [conteudo.index(a) for a in arquivos]
    assert posicoes == sorted(posicoes)


def test_historico_ordem_invalida_cai_na_ordem_padrao(client, chefe_almoxarifado, criar_usuario):
    usuario = criar_usuario()
    _criar_execucao(executada_por=usuario)

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("fornecedores:historico"), {"ordem": "campo-inexistente"})

    assert resposta.status_code == 200
    assert resposta.context["ordem"] == "-concluida"


def test_historico_pagina_por_20_execucoes(client, chefe_almoxarifado, criar_usuario):
    usuario = criar_usuario()
    base = timezone.now()
    for indice in range(25):
        _criar_execucao(
            executada_por=usuario,
            concluida_em=base - timedelta(minutes=indice),
            nome_arquivo=f"arquivo-{indice:02d}.csv",
        )

    client.force_login(chefe_almoxarifado)
    url = reverse("fornecedores:historico")

    resposta_pagina_1 = client.get(url)
    assert resposta_pagina_1.status_code == 200
    assert len(resposta_pagina_1.context["object_list"]) == 20
    assert resposta_pagina_1.context["object_list"][0].nome_arquivo == "arquivo-00.csv"

    resposta_pagina_2 = client.get(url, {"pagina": 2})
    assert len(resposta_pagina_2.context["object_list"]) == 5


# ---------------------------------------------------------------------------
# Sem N+1 — nem de `executada_por` na lista, nem de `fornecedor` nas
# alterações do detalhe.
# ---------------------------------------------------------------------------


def test_numero_de_queries_da_listagem_e_constante_entre_1_e_20_execucoes_de_usuarios_diferentes(
    client, chefe_almoxarifado, criar_usuario
):
    client.force_login(chefe_almoxarifado)
    url = reverse("fornecedores:historico")

    _criar_execucao(executada_por=criar_usuario())
    with CaptureQueriesContext(connection) as com_uma:
        resposta_uma = client.get(url)
    assert resposta_uma.status_code == 200

    for _ in range(19):
        _criar_execucao(executada_por=criar_usuario())
    with CaptureQueriesContext(connection) as com_vinte:
        resposta_vinte = client.get(url)
    assert resposta_vinte.status_code == 200

    assert len(com_uma.captured_queries) == len(com_vinte.captured_queries), (
        "possível N+1 de executada_por na listagem"
    )


def test_numero_de_queries_do_detalhe_e_constante_entre_2_e_20_alteracoes_de_fornecedores_distintos(
    chefe_almoxarifado,
):
    """Reimporta um lote de fornecedores, todos com o nome alterado, para
    gerar uma `AlteracaoFornecedor` por fornecedor — sem `select_related
    ("fornecedor")` na queryset de alterações, exibir o `codif`/`nome` de
    cada uma no detalhe emitiria uma query por linha (N+1)."""
    client = _cliente_autenticado(chefe_almoxarifado)

    conteudo_inicial_pequeno = _arquivo(
        _linha("100001", "Fornecedor Um"), _linha("100002", "Fornecedor Dois")
    )
    _importar_diretamente(conteudo_inicial_pequeno, chefe_almoxarifado, "inicial_pequeno.csv")
    conteudo_reimport_pequeno = _arquivo(
        _linha("100001", "Fornecedor Um Revisado"), _linha("100002", "Fornecedor Dois Revisado")
    )
    execucao_pequena = _importar_diretamente(
        conteudo_reimport_pequeno, chefe_almoxarifado, "reimport_pequeno.csv"
    )

    conteudo_inicial_grande = _arquivo(
        *[_linha(str(200_000 + i), f"Fornecedor Grande {i}") for i in range(20)]
    )
    _importar_diretamente(conteudo_inicial_grande, chefe_almoxarifado, "inicial_grande.csv")
    conteudo_reimport_grande = _arquivo(
        *[_linha(str(200_000 + i), f"Fornecedor Grande {i} Revisado") for i in range(20)]
    )
    execucao_grande = _importar_diretamente(
        conteudo_reimport_grande, chefe_almoxarifado, "reimport_grande.csv"
    )

    assert execucao_pequena.total_atualizados_com_alteracao == 2, "pré-condição"
    assert execucao_grande.total_atualizados_com_alteracao == 20, "pré-condição"

    with CaptureQueriesContext(connection) as com_duas:
        resposta_pequena = client.get(
            reverse("fornecedores:execucao_detalhe", args=[execucao_pequena.pk])
        )
    assert resposta_pequena.status_code == 200

    with CaptureQueriesContext(connection) as com_vinte:
        resposta_grande = client.get(
            reverse("fornecedores:execucao_detalhe", args=[execucao_grande.pk])
        )
    assert resposta_grande.status_code == 200

    assert len(com_duas.captured_queries) == len(com_vinte.captured_queries), (
        "possível N+1 de fornecedor nas alterações do detalhe "
        f"({len(com_duas.captured_queries)} vs {len(com_vinte.captured_queries)} queries)"
    )


# ---------------------------------------------------------------------------
# Detalhe: preservação histórica, exceção com linha/motivo/codif, 404.
# ---------------------------------------------------------------------------


def test_detalhe_da_primeira_execucao_e_identico_apos_uma_segunda_importacao(chefe_almoxarifado):
    client = _cliente_autenticado(chefe_almoxarifado)
    conteudo_1 = _arquivo(_linha("300001", "Fornecedor Preservado"))
    execucao_1 = _importar_diretamente(conteudo_1, chefe_almoxarifado, "primeira.csv")
    url_detalhe_1 = reverse("fornecedores:execucao_detalhe", args=[execucao_1.pk])

    resposta_antes = client.get(url_detalhe_1)
    assert resposta_antes.status_code == 200
    totais_antes = (
        execucao_1.total_recebidos, execucao_1.total_inseridos, execucao_1.total_rejeitados,
    )

    conteudo_2 = _arquivo(_linha("300002", "Outro Fornecedor"))
    _importar_diretamente(conteudo_2, chefe_almoxarifado, "segunda.csv")

    resposta_depois = client.get(url_detalhe_1)
    assert resposta_depois.status_code == 200
    execucao_1.refresh_from_db()
    totais_depois = (
        execucao_1.total_recebidos, execucao_1.total_inseridos, execucao_1.total_rejeitados,
    )
    assert totais_antes == totais_depois


def test_excecao_no_detalhe_mostra_linha_motivo_e_codif_quando_identificavel(chefe_almoxarifado):
    client = _cliente_autenticado(chefe_almoxarifado)
    conteudo = _arquivo(
        _linha("400001", "Fornecedor Aceito"),
        "400002;Fornecedor Recusado;;;01;;;;",  # BLOQ_OPCAO vazio
    )
    execucao = _importar_diretamente(conteudo, chefe_almoxarifado, "com_recusa.csv")

    excecao = ExcecaoImportacaoFornecedores.objects.get(execucao=execucao, codif="400002")
    assert excecao.motivo == "SITUACAO_BLOQUEIO_INVALIDA"

    resposta = client.get(reverse("fornecedores:execucao_detalhe", args=[execucao.pk]))
    conteudo_html = resposta.content.decode("utf-8")

    assert str(excecao.linha) in conteudo_html
    assert re.search(r'<td class="table-cell-code">\s*400002\s*</td>', conteudo_html), (
        "codif '400002' deveria aparecer numa célula de código da tabela de exceções"
    )


def test_detalhe_de_execucao_inexistente_e_404(client, chefe_almoxarifado):
    client.force_login(chefe_almoxarifado)

    resposta = client.get(reverse("fornecedores:execucao_detalhe", args=[999999]))

    assert resposta.status_code == 404


# ---------------------------------------------------------------------------
# Seção de alterações no detalhe — convenção fixada pelo coordenador
# (rodada de 2026-09-25): `data-secao="alteracoes"`, `?pagina_alteracoes=`,
# fornecedor identificado por codif/nome, campo/valor anterior/valor novo
# visíveis.
# ---------------------------------------------------------------------------


def test_detalhe_mostra_secao_de_alteracoes_com_campo_valores_e_fornecedor(chefe_almoxarifado):
    client = _cliente_autenticado(chefe_almoxarifado)
    conteudo_inicial = _arquivo(_linha("500001", "Fornecedor Original"))
    _importar_diretamente(conteudo_inicial, chefe_almoxarifado, "inicial.csv")

    conteudo_reimport = _arquivo(_linha("500001", "Fornecedor Revisado"))
    execucao = _importar_diretamente(conteudo_reimport, chefe_almoxarifado, "reimport.csv")
    assert execucao.total_atualizados_com_alteracao == 1, "pré-condição"

    resposta = client.get(reverse("fornecedores:execucao_detalhe", args=[execucao.pk]))

    assert resposta.status_code == 200
    conteudo_html = resposta.content.decode("utf-8")
    assert 'data-secao="alteracoes"' in conteudo_html
    assert "500001" in conteudo_html, "codif do fornecedor alterado precisa aparecer"
    assert "Fornecedor Original" in conteudo_html
    assert "Fornecedor Revisado" in conteudo_html

    resposta_paginada = client.get(
        reverse("fornecedores:execucao_detalhe", args=[execucao.pk]),
        {"pagina_alteracoes": "1"},
    )
    assert resposta_paginada.status_code == 200


def test_detalhe_sem_alteracoes_marca_secao_vazia(chefe_almoxarifado):
    client = _cliente_autenticado(chefe_almoxarifado)
    conteudo = _arquivo(_linha("500002", "Fornecedor Sem Reimportacao"))
    execucao = _importar_diretamente(conteudo, chefe_almoxarifado, "inicial.csv")

    resposta = client.get(reverse("fornecedores:execucao_detalhe", args=[execucao.pk]))

    assert resposta.status_code == 200
    conteudo_html = resposta.content.decode("utf-8")
    assert 'data-secao="alteracoes"' in conteudo_html


def test_alteracao_de_bloqueado_mostra_o_valor_s_ou_b_de_alguma_forma_legivel(chefe_almoxarifado):
    """A trilha grava `bloqueado` como `"S"`/`"B"` (research R5); como
    exibir é decisão do frontend — este teste só confirma que o VALOR
    aparece na página, sem fixar um rótulo específico."""
    client = _cliente_autenticado(chefe_almoxarifado)
    conteudo_inicial = _arquivo(_linha("500003", "Fornecedor Bloqueio", bloq="S"))
    _importar_diretamente(conteudo_inicial, chefe_almoxarifado, "inicial.csv")

    conteudo_reimport = _arquivo(_linha("500003", "Fornecedor Bloqueio", bloq="B"))
    execucao = _importar_diretamente(conteudo_reimport, chefe_almoxarifado, "reimport.csv")
    assert execucao.total_atualizados_com_alteracao == 1, "pré-condição"

    from fornecedores.models import AlteracaoFornecedor

    alteracao = AlteracaoFornecedor.objects.get(execucao=execucao, campo="bloqueado")
    assert alteracao.valor_anterior == "S"
    assert alteracao.valor_novo == "B"

    resposta = client.get(reverse("fornecedores:execucao_detalhe", args=[execucao.pk]))
    assert resposta.status_code == 200
    conteudo_html = resposta.content.decode("utf-8")
    secao_alteracoes = conteudo_html.split('data-secao="alteracoes"', 1)[1]
    assert "500003" in secao_alteracoes
    assert ">Bloqueado<" in secao_alteracoes


# ---------------------------------------------------------------------------
# Situação de bloqueio em destaque no detalhe (P1 do gate visual, rodada de
# revisão do dono do produto): `total_passam_a_bloqueado`/
# `total_voltam_a_liberado`, numa única query agregada, e as alterações do
# campo `bloqueado` ordenadas primeiro.
# ---------------------------------------------------------------------------


def test_detalhe_mostra_total_de_fornecedores_que_passam_a_bloqueado(
    chefe_almoxarifado, csv_fornecedores
):
    client = _cliente_autenticado(chefe_almoxarifado)
    _importar_diretamente(csv_fornecedores("reimportacao_base.csv"), chefe_almoxarifado, "base.csv")
    execucao = _importar_diretamente(
        csv_fornecedores("reimportacao_bloqueio_s_para_b.csv"), chefe_almoxarifado, "bloqueio.csv"
    )

    resposta = client.get(reverse("fornecedores:execucao_detalhe", args=[execucao.pk]))

    assert resposta.status_code == 200
    assert resposta.context["total_passam_a_bloqueado"] == 1
    assert resposta.context["total_voltam_a_liberado"] == 0


def test_detalhe_mostra_total_de_fornecedores_que_voltam_a_liberado(
    chefe_almoxarifado, csv_fornecedores
):
    client = _cliente_autenticado(chefe_almoxarifado)
    _importar_diretamente(csv_fornecedores("reimportacao_base.csv"), chefe_almoxarifado, "base.csv")
    execucao = _importar_diretamente(
        csv_fornecedores("reimportacao_bloqueio_b_para_s.csv"), chefe_almoxarifado, "bloqueio.csv"
    )

    resposta = client.get(reverse("fornecedores:execucao_detalhe", args=[execucao.pk]))

    assert resposta.status_code == 200
    assert resposta.context["total_voltam_a_liberado"] == 1
    assert resposta.context["total_passam_a_bloqueado"] == 0


def test_detalhe_calcula_os_dois_totais_de_bloqueio_numa_unica_query_agregada(
    chefe_almoxarifado, csv_fornecedores
):
    """Combina as duas variações (`700002` S→B, `700003` B→S) na MESMA
    execução — prova que os dois totais vêm de uma única consulta agregada
    (`Count` com `filter=Q(...)`), não de duas consultas `.count()`
    separadas."""
    client = _cliente_autenticado(chefe_almoxarifado)
    _importar_diretamente(csv_fornecedores("reimportacao_base.csv"), chefe_almoxarifado, "base.csv")

    linhas_s_para_b = (
        csv_fornecedores("reimportacao_bloqueio_s_para_b.csv").decode("utf-8").splitlines()
    )
    linhas_b_para_s = (
        csv_fornecedores("reimportacao_bloqueio_b_para_s.csv").decode("utf-8").splitlines()
    )
    # Cabeçalho + 700001 inalterado + 700002 (S→B, do arquivo s_para_b) +
    # 700003 (B→S, do arquivo b_para_s) + 700004/700005 inalterados.
    conteudo_combinado = "\r\n".join(
        [
            linhas_s_para_b[0],
            linhas_s_para_b[1],
            linhas_s_para_b[2],
            linhas_b_para_s[3],
            *linhas_s_para_b[4:],
        ]
    ).encode("utf-8")
    execucao = _importar_diretamente(conteudo_combinado, chefe_almoxarifado, "combinado.csv")
    assert execucao.total_atualizados_com_alteracao == 2, "pré-condição"

    with CaptureQueriesContext(connection) as capturadas:
        resposta = client.get(reverse("fornecedores:execucao_detalhe", args=[execucao.pk]))

    assert resposta.status_code == 200
    assert resposta.context["total_passam_a_bloqueado"] == 1
    assert resposta.context["total_voltam_a_liberado"] == 1
    # `FILTER (WHERE ...)` (Postgres) é a marca da agregação condicional dos
    # dois totais numa única query — diferente do `SELECT COUNT(*)` sem
    # filtro que o `Paginator` das próprias alterações também dispara.
    queries_agregado = [
        query
        for query in capturadas.captured_queries
        if "fornecedores_alteracaofornecedor" in query["sql"] and "FILTER (WHERE" in query["sql"]
    ]
    assert len(queries_agregado) == 1, (
        "os dois totais de bloqueio deveriam vir de uma única query agregada, "
        f"não de {len(queries_agregado)}: {queries_agregado}"
    )


def test_detalhe_ordena_alteracoes_do_campo_bloqueado_primeiro(chefe_almoxarifado):
    """Situação de bloqueio em destaque (P1 do gate visual): a alteração de
    `bloqueado` vem primeiro na lista, mesmo pertencendo a um fornecedor de
    codif MAIOR que outro cuja alteração é de outro campo — sem a
    ordenação, a ordem natural (`fornecedor__codif`, `campo`) poria a
    alteração de nome de `600001` antes da de bloqueio de `600002`."""
    client = _cliente_autenticado(chefe_almoxarifado)
    conteudo_inicial = _arquivo(
        _linha("600001", "Fornecedor Um"), _linha("600002", "Fornecedor Dois")
    )
    _importar_diretamente(conteudo_inicial, chefe_almoxarifado, "inicial.csv")

    conteudo_reimport = _arquivo(
        _linha("600001", "Fornecedor Um Revisado"),
        _linha("600002", "Fornecedor Dois", bloq="B"),
    )
    execucao = _importar_diretamente(conteudo_reimport, chefe_almoxarifado, "reimport.csv")
    assert execucao.total_atualizados_com_alteracao == 2, "pré-condição"

    resposta = client.get(reverse("fornecedores:execucao_detalhe", args=[execucao.pk]))

    assert resposta.status_code == 200
    linhas = list(resposta.context["alteracoes_pagina"])
    indice_bloqueado = next(i for i, linha in enumerate(linhas) if linha["campo"] == "bloqueado")
    indice_nome = next(i for i, linha in enumerate(linhas) if linha["campo"] == "nome")
    assert indice_bloqueado < indice_nome, (
        "a alteração de bloqueado (600002) deveria vir antes da de nome (600001), "
        "mesmo com codif maior"
    )
