"""Testes do histórico de importações do catálogo (T036 — US3, FR-033–FR-037).

TDD: escrito antes de `catalogo:historico`/`HistoricoImportacoesView` (T038) e do
template `catalogo/historico.html` (T040) existirem. Toda chamada de `reverse()`
fica dentro do corpo dos testes, para que a ausência da rota derrube só o teste
que a usa (`NoReverseMatch`), não a coleta do arquivo inteiro — mesma convenção de
`tests/test_catalogo_permissoes.py`.

Cobre `contracts/rotas-e-autorizacao.md` → "GET /catalogo/importacoes/" e
"GET /catalogo/importacoes/<pk>/". Autorização em si é T037
(`tests/test_catalogo_permissoes.py`, seção `ROTAS_HISTORICO`); aqui o usuário é
sempre `chefe_almoxarifado`, e o foco é o comportamento observável.

Decisões documentadas para os implementadores de T038/T040:

- **Parâmetro de página**: `pagina`, o mesmo da consulta (`contracts/rotas-e-autorizacao.md`)
  e o que `catalogo/_paginacao.html` recebe como `parametro`. Decisão do
  coordenador: T038 declara `page_kwarg = "pagina"` no `ListView`.
- **Estado vazio**: sem nenhuma execução, o template (T040) DEVE emitir um
  elemento com `data-estado="vazio"` na região da lista, seguindo o mesmo
  padrão já adotado por `catalogo/_resultados_consulta.html`
  (`tests/test_catalogo_consulta.py`).
- **Colunas exibidas**: matrícula de quem executou (`executada_por.matricula`),
  momento (`concluida_em`), nome do arquivo, e os totais (recebidos, inseridos,
  atualizados, rejeitados, divergências) — conforme
  `contracts/rotas-e-autorizacao.md` → "GET /catalogo/importacoes/". Os testes
  abaixo verificam a presença desses valores no HTML, nunca a estrutura de
  markup.
- Cada linha do histórico leva ao detalhe da execução
  (`catalogo:execucao_detalhe`, pk): os testes verificam que o `href` de cada
  execução aparece na página.
"""

import re
import uuid
from datetime import timedelta
from urllib.parse import urlsplit

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from django.utils import timezone

from catalogo.models import ExcecaoImportacao, ExecucaoImportacao, MotivoRecusa

pytestmark = pytest.mark.django_db

SHA256_FAKE = "0" * 64


def _cliente_autenticado(usuario):
    client = Client()
    client.force_login(usuario)
    return client


def _enviar(client, conteudo, nome="arquivo.csv"):
    arquivo = SimpleUploadedFile(nome, conteudo, content_type="text/csv")
    return client.post(reverse("catalogo:importacao_envio"), {"arquivo": arquivo})


def _importar_via_http(client, conteudo, nome="arquivo.csv"):
    """Executa o fluxo real de importação (envio → confirmação) e devolve a
    `ExecucaoImportacao` criada, usando só a interface interna fixada em
    `contracts/interface-importacao.md` (mesma técnica de
    `tests/test_catalogo_views_importacao.py`)."""
    from catalogo import importacao

    resposta_envio = _enviar(client, conteudo, nome)
    assert resposta_envio.status_code == 302

    pedido = importacao.obter_pedido(client.session)
    assert pedido is not None
    plano = importacao.calcular_plano(pedido.conteudo)

    resposta_confirmar = client.post(
        reverse("catalogo:importacao_confirmar"),
        {"token": pedido.token, "impressao_digital": plano.impressao_digital},
    )
    assert resposta_confirmar.status_code == 302
    destino = resolve(urlsplit(resposta_confirmar.url).path)
    assert destino.view_name == "catalogo:execucao_detalhe"
    return ExecucaoImportacao.objects.get(pk=destino.kwargs["pk"])


def _criar_execucao(*, executada_por, concluida_em=None, nome_arquivo="carga.csv", **totais):
    valores_totais = {
        "total_recebidos": 1,
        "total_inseridos": 1,
        "total_atualizados": 0,
        "total_atualizados_com_alteracao": 0,
        "total_rejeitados": 0,
        "total_divergencias": 0,
        "total_ausentes_no_arquivo": 0,
        **totais,
    }
    return ExecucaoImportacao.objects.create(
        token_previa=uuid.uuid4(),
        executada_por=executada_por,
        concluida_em=concluida_em or timezone.now(),
        nome_arquivo=nome_arquivo,
        tamanho_arquivo=10,
        sha256_arquivo=SHA256_FAKE,
        **valores_totais,
    )


def _totais_da_execucao(pk):
    execucao = ExecucaoImportacao.objects.get(pk=pk)
    return (
        execucao.total_recebidos,
        execucao.total_inseridos,
        execucao.total_atualizados,
        execucao.total_atualizados_com_alteracao,
        execucao.total_rejeitados,
        execucao.total_divergencias,
        execucao.total_ausentes_no_arquivo,
    )


def _excecoes_da_execucao(pk):
    return frozenset(
        (
            excecao.linha_inicial,
            excecao.linha_final,
            excecao.cadpro,
            excecao.motivo,
            excecao.detalhe,
        )
        for excecao in ExcecaoImportacao.objects.filter(execucao_id=pk)
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
    resposta = client.get(reverse("catalogo:historico"))

    assert resposta.status_code == 200

    # Contexto primeiro: confirma que a view passou a execução recente com
    # os totais esperados (fonte de verdade do que o template deve exibir).
    execucoes_por_arquivo = {e.nome_arquivo: e for e in resposta.context["object_list"]}
    recente = execucoes_por_arquivo["carga-recente.csv"]
    assert (recente.total_recebidos, recente.total_inseridos, recente.total_rejeitados) == (
        22,
        9,
        13,
    )

    conteudo = resposta.content.decode("utf-8")
    for esperado in (
        usuario_antiga.matricula,
        usuario_recente.matricula,
        "carga-antiga.csv",
        "carga-recente.csv",
    ):
        assert esperado in conteudo, f"{esperado!r} deveria aparecer no histórico"

    posicao_recente = conteudo.index("carga-recente.csv")
    posicao_antiga = conteudo.index("carga-antiga.csv")
    assert posicao_recente < posicao_antiga, (
        "a execução mais recente (-concluida_em) deve aparecer antes da mais antiga"
    )

    # Os totais precisam aparecer nas células numéricas da LINHA da execução
    # recente (`catalogo/templates/catalogo/historico.html`), não em
    # qualquer trecho do HTML — "22"/"9"/"13" soltos poderiam coincidir com
    # data ou matrícula. A fatia [posicao_recente:posicao_antiga] cobre
    # exatamente o restante da linha "carga-recente.csv" (arquivo vem antes
    # dos totais na mesma `<tr>`) até o início da linha seguinte.
    linha_recente = conteudo[posicao_recente:posicao_antiga]
    for total_esperado in ("22", "9", "13"):
        assert re.search(
            rf'<td class="table-cell-numeric">\s*{total_esperado}\s*</td>', linha_recente
        ), f"total {total_esperado!r} não encontrado numa célula numérica da linha recente"


def test_historico_sem_execucoes_mostra_estado_vazio_explicito(client, chefe_almoxarifado):
    """Documenta o marcador estável exigido do template (T040): um elemento
    com `data-estado="vazio"`, mesmo padrão de
    `catalogo/_resultados_consulta.html` (`tests/test_catalogo_consulta.py`)."""
    client.force_login(chefe_almoxarifado)

    resposta = client.get(reverse("catalogo:historico"))

    assert resposta.status_code == 200
    assert len(resposta.context["object_list"]) == 0
    assert 'data-estado="vazio"' in resposta.content.decode("utf-8")


def test_cada_execucao_do_historico_leva_ao_detalhe(client, chefe_almoxarifado, criar_usuario):
    usuario = criar_usuario()
    execucao = _criar_execucao(executada_por=usuario)

    client.force_login(chefe_almoxarifado)
    resposta = client.get(reverse("catalogo:historico"))

    href_esperado = reverse("catalogo:execucao_detalhe", args=[execucao.pk])
    assert href_esperado in resposta.content.decode("utf-8")


# ---------------------------------------------------------------------------
# Paginação (20/página) — ver decisão sobre o parâmetro `pagina` no docstring
# do módulo.
# ---------------------------------------------------------------------------


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
    url = reverse("catalogo:historico")

    resposta_pagina_1 = client.get(url)
    assert resposta_pagina_1.status_code == 200
    assert resposta_pagina_1.context["is_paginated"] is True
    assert len(resposta_pagina_1.context["object_list"]) == 20
    assert resposta_pagina_1.context["paginator"].num_pages == 2
    # índice 0 tem o `concluida_em` mais recente (base - 0 minutos).
    assert resposta_pagina_1.context["object_list"][0].nome_arquivo == "arquivo-00.csv"

    resposta_pagina_2 = client.get(url, {"pagina": 2})
    assert resposta_pagina_2.status_code == 200
    assert len(resposta_pagina_2.context["object_list"]) == 5
    assert resposta_pagina_2.context["object_list"][0].nome_arquivo == "arquivo-20.csv"


# ---------------------------------------------------------------------------
# Queries constantes por página — sem N+1 de `executada_por`
# (`select_related`, T038).
# ---------------------------------------------------------------------------


def test_numero_de_queries_e_constante_entre_1_e_muitas_execucoes_de_usuarios_diferentes(
    client, chefe_almoxarifado, criar_usuario
):
    client.force_login(chefe_almoxarifado)
    url = reverse("catalogo:historico")

    _criar_execucao(executada_por=criar_usuario())
    with CaptureQueriesContext(connection) as com_uma:
        resposta_uma = client.get(url)
    assert resposta_uma.status_code == 200

    # 19 execuções adicionais, cada uma de um usuário DIFERENTE: sem
    # `select_related("executada_por")` isso emitiria uma query extra por
    # linha ao acessar `execucao.executada_por` no template (N+1).
    for _ in range(19):
        _criar_execucao(executada_por=criar_usuario())
    with CaptureQueriesContext(connection) as com_vinte:
        resposta_vinte = client.get(url)
    assert resposta_vinte.status_code == 200

    queries_uma = len(com_uma.captured_queries)
    queries_vinte = len(com_vinte.captured_queries)
    assert queries_uma == queries_vinte, (
        f"{queries_vinte - queries_uma} query(ies) a mais com 20 execuções — "
        "possível N+1 de `executada_por`"
    )


# ---------------------------------------------------------------------------
# Detalhe: preservação histórica (FR-037), exceção com linha/motivo/CADPRO
# (FR-036), 404 para pk inexistente.
# ---------------------------------------------------------------------------


def test_detalhe_da_primeira_execucao_e_identico_antes_e_depois_de_uma_segunda_importacao(
    chefe_almoxarifado, csv_fixture
):
    """FR-037 / US3 cenário 3: o resultado de uma execução concluída não pode
    ser sobrescrito por uma execução posterior — nem os totais, nem as
    exceções, nem o HTML exibido para o usuário."""
    client_autenticado = _cliente_autenticado(chefe_almoxarifado)
    execucao_1 = _importar_via_http(client_autenticado, csv_fixture("carga_inicial_valida.csv"))
    url_detalhe_1 = reverse("catalogo:execucao_detalhe", args=[execucao_1.pk])

    resposta_antes = client_autenticado.get(url_detalhe_1)
    assert resposta_antes.status_code == 200
    totais_antes = _totais_da_execucao(execucao_1.pk)
    excecoes_antes = _excecoes_da_execucao(execucao_1.pk)
    # Escopado ao par <dt>/<dd> do resumo (`execucao_detalhe.html`) — "9"
    # solto coincide por acidente com dígitos do SHA-256 exibido na mesma
    # página.
    assert re.search(
        rf"<dt>Inseridos</dt>\s*<dd>\s*{execucao_1.total_inseridos}\s*</dd>",
        resposta_antes.content.decode("utf-8"),
    )

    # segunda importação — arquivo com registros propositalmente inválidos
    # (US3, Independent Test), sobre os mesmos 9 códigos já existentes.
    _importar_via_http(client_autenticado, csv_fixture("carga_inicial_casos_spec.csv"))

    resposta_depois = client_autenticado.get(url_detalhe_1)
    assert resposta_depois.status_code == 200
    totais_depois = _totais_da_execucao(execucao_1.pk)
    excecoes_depois = _excecoes_da_execucao(execucao_1.pk)

    assert totais_antes == totais_depois, "a segunda importação não pode alterar os totais da 1ª"
    assert excecoes_antes == excecoes_depois, (
        "a segunda importação não pode alterar as exceções da 1ª"
    )
    assert re.search(
        rf"<dt>Inseridos</dt>\s*<dd>\s*{execucao_1.total_inseridos}\s*</dd>",
        resposta_depois.content.decode("utf-8"),
    )


def test_excecao_no_detalhe_mostra_linha_motivo_e_cadpro_quando_identificavel(
    chefe_almoxarifado, csv_fixture
):
    """FR-036, usando o caso documentado em `tests/fixtures/catalogo/README.md`
    (linha 18, `CADPRO="2"`, `CADPRO_FORMATO_INVALIDO` — exemplo normativo do
    contrato §5)."""
    client_autenticado = _cliente_autenticado(chefe_almoxarifado)
    execucao = _importar_via_http(client_autenticado, csv_fixture("carga_inicial_casos_spec.csv"))

    excecao = execucao.excecoes.get(cadpro="2")
    assert excecao.motivo == MotivoRecusa.CADPRO_FORMATO_INVALIDO
    assert excecao.linha_inicial == 18

    resposta = client_autenticado.get(reverse("catalogo:execucao_detalhe", args=[execucao.pk]))
    conteudo = resposta.content.decode("utf-8")

    # Contexto: a exceção da linha 18 (CADPRO="2") está na página exibida.
    excecao_no_contexto = next(
        e for e in resposta.context["excecoes_pagina"] if e.pk == excecao.pk
    )
    assert excecao_no_contexto.cadpro == "2"
    assert excecao_no_contexto.linha_inicial == 18

    assert str(excecao.linha_inicial) in conteudo
    # Célula "Código (CADPRO)" com o valor exato
    # (`catalogo/templates/catalogo/execucao_detalhe.html`) — não uma
    # checagem tautológica de "2" solto em qualquer lugar do HTML (colidiria
    # com paginação, contagens etc.).
    assert re.search(r'<td class="table-cell-code">\s*2\s*</td>', conteudo), (
        "CADPRO '2' deveria aparecer numa célula de código da tabela de exceções"
    )
    rotulo_ou_codigo = MotivoRecusa.CADPRO_FORMATO_INVALIDO.label
    assert (
        rotulo_ou_codigo in conteudo or MotivoRecusa.CADPRO_FORMATO_INVALIDO.value in conteudo
    ), "o motivo da recusa precisa aparecer, como rótulo em pt-BR ou como código"


def test_detalhe_de_execucao_inexistente_e_404(client, chefe_almoxarifado):
    client.force_login(chefe_almoxarifado)

    resposta = client.get(reverse("catalogo:execucao_detalhe", args=[999999]))

    assert resposta.status_code == 404
