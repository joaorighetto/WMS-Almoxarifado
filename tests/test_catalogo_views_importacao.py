"""Testes das views de importação do catálogo (T018), via `Client`.

Cobre FR-044/FR-044a e `contracts/rotas-e-autorizacao.md` (seção "Envio",
"Prévia", "Efetivação" e "Cancelamento"). Autorização em si é `test_catalogo_
permissoes.py` (T019); aqui o usuário é sempre `chefe_almoxarifado`
(`ROLE-WAREHOUSE-HEAD`), e o foco é o comportamento e os efeitos observáveis
de cada rota.

TDD: escrito antes das views, rotas e templates existirem (T026-T029). Os
imports de `catalogo.importacao` ficam dentro das funções de teste (o módulo
ainda não existe); `catalogo.models` já existe (T008-T011) e pode ser
importado no topo do arquivo.

Convenção adotada para evitar depender de nomes de variável de template
(ainda não escritos por `frontend-implementer`, T029): sempre que o teste
precisa do `token`/impressão digital para confirmar ou cancelar, ele os
obtém de volta da PRÓPRIA sessão via `catalogo.importacao.obter_pedido` e
recalcula o plano com `calcular_plano`, em vez de tentar extrair um campo
oculto do HTML renderizado. Isso usa só a interface interna fixada em
`contracts/interface-importacao.md`, nunca detalhe de markup. Para as
asserções sobre o CONTEÚDO da prévia/detalhe, verificamos dados (totais,
`CADPRO`, o aviso textual que o próprio contrato cita), nunca estrutura HTML.
"""

import re
import uuid
from urllib.parse import urlsplit

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

from catalogo.models import (
    AlteracaoCadastralMaterial,
    DivergenciaSaldo,
    ExcecaoImportacao,
    ExecucaoImportacao,
    Material,
)

pytestmark = pytest.mark.django_db


def _enviar(client, conteudo, nome="arquivo.csv"):
    arquivo = SimpleUploadedFile(nome, conteudo, content_type="text/csv")
    return client.post(reverse("catalogo:importacao_envio"), {"arquivo": arquivo})


def _pedido_e_plano_da_sessao(client):
    from catalogo import importacao

    pedido = importacao.obter_pedido(client.session)
    assert pedido is not None, "esperava um pedido de prévia salvo na sessão após envio válido"
    plano = importacao.calcular_plano(pedido.conteudo)
    return pedido, plano


def _contagem_das_cinco_tabelas():
    return (
        Material.objects.count()
        + ExecucaoImportacao.objects.count()
        + ExcecaoImportacao.objects.count()
        + DivergenciaSaldo.objects.count()
        + AlteracaoCadastralMaterial.objects.count()
    )


def _confirmar_diretamente(conteudo, usuario, nome_arquivo="arquivo.csv"):
    """Confirma uma importação direto pela camada de domínio (sem `Client`),
    para preparar o catálogo pré-existente que os testes de REIMPORTAÇÃO
    (T043) precisam antes de exercitar a rota de prévia/detalhe via HTTP —
    o efeito observável é o mesmo de uma confirmação real, sem repetir
    envio+confirmação por upload para montar a pré-condição."""
    from catalogo import importacao

    plano = importacao.calcular_plano(conteudo)
    pedido = importacao.PedidoPrevia(
        token=str(uuid.uuid4()),
        nome_arquivo=nome_arquivo,
        tamanho=len(conteudo),
        sha256=plano.sha256_arquivo,
        conteudo=conteudo,
    )
    return importacao.confirmar_importacao(pedido, plano.impressao_digital, usuario)


def _secao_html(conteudo_html, nome_secao):
    """Recorta o HTML de uma `<section data-secao="...">` até seu `</section>`
    de fechamento, para escopar asserções (ex.: `data-estado="vazio"`) dentro
    da seção correta em vez de checar a página inteira — duas seções
    poderiam ter o mesmo marcador de estado vazio independentemente."""
    correspondencia = re.search(
        rf'<section[^>]*data-secao="{nome_secao}"[^>]*>(.*?)</section>',
        conteudo_html,
        re.DOTALL,
    )
    assert correspondencia, f'seção data-secao="{nome_secao}" não encontrada no HTML'
    return correspondencia.group(1)


# ---------------------------------------------------------------------------
# FR-044a: nada é gravado antes da confirmação — nem contagem, nem escrita.
# ---------------------------------------------------------------------------


def test_envio_e_previa_nao_alteram_nenhuma_tabela_de_catalogo(chefe_almoxarifado, csv_fixture):
    client_autenticado = _cliente_autenticado(chefe_almoxarifado)

    antes = _contagem_das_cinco_tabelas()
    resposta_envio = _enviar(client_autenticado, csv_fixture("carga_inicial_casos_spec.csv"))
    assert resposta_envio.status_code == 302

    resposta_previa = client_autenticado.get(reverse("catalogo:importacao_previa"))
    assert resposta_previa.status_code == 200

    assert _contagem_das_cinco_tabelas() == antes == 0


def test_envio_e_previa_nao_emitem_escrita_nem_select_for_update_em_catalogo(
    chefe_almoxarifado, csv_fixture
):
    client_autenticado = _cliente_autenticado(chefe_almoxarifado)
    conteudo = csv_fixture("carga_inicial_casos_spec.csv")

    with CaptureQueriesContext(connection) as queries_envio:
        resposta_envio = _enviar(client_autenticado, conteudo)
    assert resposta_envio.status_code == 302

    with CaptureQueriesContext(connection) as queries_previa:
        resposta_previa = client_autenticado.get(reverse("catalogo:importacao_previa"))
    assert resposta_previa.status_code == 200

    for capturadas in (queries_envio, queries_previa):
        for query in capturadas.captured_queries:
            sql_original = query["sql"]
            sql = sql_original.upper()
            primeira_palavra = sql.split(None, 1)[0] if sql.split() else ""
            if primeira_palavra in ("INSERT", "UPDATE", "DELETE"):
                assert "CATALOGO_" not in sql, f"query de escrita em catalogo_*: {sql_original}"
            if "FOR UPDATE" in sql:
                assert "CATALOGO_" not in sql, (
                    f"SELECT ... FOR UPDATE em tabela catalogo_* na prévia: {sql_original}"
                )


def test_previa_exibe_totais_excecoes_e_aviso_de_que_nada_foi_gravado(
    chefe_almoxarifado, csv_fixture
):
    client_autenticado = _cliente_autenticado(chefe_almoxarifado)
    _enviar(client_autenticado, csv_fixture("carga_inicial_casos_spec.csv"))
    _, plano = _pedido_e_plano_da_sessao(client_autenticado)

    resposta = client_autenticado.get(reverse("catalogo:importacao_previa"))

    assert resposta.status_code == 200
    conteudo_html = resposta.content.decode("utf-8")
    # Escopado ao par <dt>/<dd> do resumo (`importacao_previa.html`) — os
    # totais soltos (22/13) coincidem por acidente com linhas físicas
    # exibidas na própria tabela de exceções abaixo.
    assert re.search(
        rf"<dt>Recebidos</dt>\s*<dd>\s*{plano.total_recebidos}\s*</dd>", conteudo_html
    ), f"total_recebidos ({plano.total_recebidos}) não encontrado no resumo"
    assert re.search(
        rf"<dt>Rejeitados</dt>\s*<dd>\s*{plano.total_rejeitados}\s*</dd>", conteudo_html
    ), f"total_rejeitados ({plano.total_rejeitados}) não encontrado no resumo"
    assert "nada foi gravado" in conteudo_html.lower(), (
        "contracts/rotas-e-autorizacao.md exige o aviso de que nada foi gravado ainda"
    )
    cadpros_de_recusas_identificaveis = [recusa.cadpro for recusa in plano.recusas if recusa.cadpro]
    assert cadpros_de_recusas_identificaveis, "pré-condição: a fixture tem exceções com CADPRO"
    for cadpro in cadpros_de_recusas_identificaveis:
        assert cadpro in conteudo_html

    assert _contagem_das_cinco_tabelas() == 0, "exibir a prévia não pode gravar nada"


# ---------------------------------------------------------------------------
# Recusa de arquivo: nada em sessão nem em banco.
# ---------------------------------------------------------------------------


def test_recusa_de_arquivo_no_envio_rerenderiza_com_erro_sem_gravar_sessao(
    chefe_almoxarifado, csv_fixture
):
    client_autenticado = _cliente_autenticado(chefe_almoxarifado)

    resposta = _enviar(client_autenticado, csv_fixture("sem_coluna_obrigatoria.csv"))

    assert resposta.status_code == 200
    assert "NOMESUBGRUPO" in resposta.content.decode("utf-8"), (
        "arquivo-scpi.md §1: a mensagem de recusa deve listar a coluna obrigatória ausente"
    )

    from catalogo import importacao

    assert importacao.obter_pedido(client_autenticado.session) is None
    assert _contagem_das_cinco_tabelas() == 0


def test_caractere_nulo_no_envio_e_recusado_com_a_linha_sem_gravar_sessao(chefe_almoxarifado):
    """FR-007b: o arquivo com U+0000 é recusado já no envio, com a linha
    na mensagem — antes, a prévia o aceitava e a confirmação falhava com
    erro genérico, desfazendo a importação inteira."""
    client_autenticado = _cliente_autenticado(chefe_almoxarifado)
    conteudo = (
        b"CADPRO;DISC1;UNID1;QUAN3;DISCR1;GRUPO;SUBGRUPO;NOMEGRUPO;NOMESUBGRUPO;\r\n"
        b"000.000.002;PARA\x00FUSO;UN;1;;;;;;\r\n"
    )

    resposta = _enviar(client_autenticado, conteudo, nome="nulo.csv")

    assert resposta.status_code == 200
    assert "caractere nulo (U+0000) na linha 2" in resposta.content.decode("utf-8")

    from catalogo import importacao

    assert importacao.obter_pedido(client_autenticado.session) is None
    assert _contagem_das_cinco_tabelas() == 0


def test_arquivo_de_0_bytes_nao_e_recusado_e_gera_previa_com_zero_recebidos(
    chefe_almoxarifado,
):
    """P2 #1: `contracts/arquivo-scpi.md` §1/I-2 — um upload de 0 bytes não
    é o caso de recusa de arquivo; é "zero recebidos, sem erro". Sem
    `allow_empty_file=True` em `ArquivoImportacaoForm`, o próprio
    `forms.FileField` recusava o upload com uma mensagem genérica antes de
    `clean_arquivo`/`verificar_arquivo` rodarem."""
    client_autenticado = _cliente_autenticado(chefe_almoxarifado)

    resposta_envio = _enviar(client_autenticado, b"", nome="vazio.csv")

    erros_do_formulario = (
        getattr(resposta_envio, "context", None) and resposta_envio.context["form"].errors
    )
    assert resposta_envio.status_code == 302, (
        "upload de 0 bytes deveria seguir para a prévia, não ser recusado pelo "
        f"formulário: {erros_do_formulario}"
    )

    resposta_previa = client_autenticado.get(reverse("catalogo:importacao_previa"))
    assert resposta_previa.status_code == 200

    _, plano = _pedido_e_plano_da_sessao(client_autenticado)
    assert plano.total_recebidos == 0
    assert plano.total_rejeitados == 0
    assert _contagem_das_cinco_tabelas() == 0


def test_arquivo_maior_que_10mb_e_recusado(chefe_almoxarifado):
    client_autenticado = _cliente_autenticado(chefe_almoxarifado)
    conteudo_grande = b"0" * (10 * 1024 * 1024 + 1)

    resposta = _enviar(client_autenticado, conteudo_grande, nome="grande.csv")

    assert resposta.status_code == 200
    from catalogo import importacao

    assert importacao.obter_pedido(client_autenticado.session) is None


# ---------------------------------------------------------------------------
# Confirmação: sucesso, impressão digital adulterada, cancelamento.
# ---------------------------------------------------------------------------


def test_confirmacao_valida_redireciona_ao_detalhe_e_remove_pedido_da_sessao(
    chefe_almoxarifado, csv_fixture
):
    client_autenticado = _cliente_autenticado(chefe_almoxarifado)
    _enviar(client_autenticado, csv_fixture("carga_inicial_valida.csv"))
    pedido, plano = _pedido_e_plano_da_sessao(client_autenticado)

    resposta = client_autenticado.post(
        reverse("catalogo:importacao_confirmar"),
        {"token": pedido.token, "impressao_digital": plano.impressao_digital},
    )

    assert resposta.status_code == 302
    destino = resolve(urlsplit(resposta.url).path)
    assert destino.view_name == "catalogo:execucao_detalhe"

    from catalogo import importacao

    assert importacao.obter_pedido(client_autenticado.session) is None
    assert Material.objects.filter(cadpro="000.000.002").exists()
    assert ExecucaoImportacao.objects.count() == 1


def test_confirmacao_valida_emite_mensagem_de_sucesso_com_os_totais(
    chefe_almoxarifado, csv_fixture
):
    """Revisão do gate visual (achado P1): a confirmação — irreversível —
    não podia mais terminar em silêncio. A mensagem segue `django.contrib.
    messages` (`catalogo/templates/catalogo/_mensagens.html`, já testado à
    parte); aqui só o conteúdo (os totais da própria execução) importa."""
    client_autenticado = _cliente_autenticado(chefe_almoxarifado)
    _enviar(client_autenticado, csv_fixture("carga_inicial_valida.csv"))
    pedido, plano = _pedido_e_plano_da_sessao(client_autenticado)

    resposta = client_autenticado.post(
        reverse("catalogo:importacao_confirmar"),
        {"token": pedido.token, "impressao_digital": plano.impressao_digital},
        follow=True,
    )

    assert resposta.status_code == 200
    execucao = ExecucaoImportacao.objects.get()
    mensagens = [str(m) for m in resposta.context["messages"]]
    assert any(
        str(execucao.total_inseridos) in m
        and str(execucao.total_atualizados) in m
        and str(execucao.total_rejeitados) in m
        and "Importação concluída" in m
        for m in mensagens
    ), mensagens
    assert 'class="badge badge-success' in resposta.content.decode("utf-8")


def test_confirmacao_com_valores_extraidos_do_html_da_previa_grava_a_execucao(
    chefe_almoxarifado, csv_fixture
):
    """P2 #1 (revisão T051): todos os demais testes de confirmação obtêm
    `token`/`impressao_digital` recalculando o plano a partir da sessão
    (`_pedido_e_plano_da_sessao`) — nunca exercitando o caminho real em que o
    usuário confirma com os valores que a PRÓPRIA prévia devolveu. Se
    `importacao_previa.html` parasse de preencher os campos ocultos, ou se as
    chaves de `_contexto_previa` (`catalogo/views.py`) fossem renomeadas,
    toda confirmação real quebraria e o resto da suíte continuaria verde.
    """
    client_autenticado = _cliente_autenticado(chefe_almoxarifado)
    _enviar(client_autenticado, csv_fixture("carga_inicial_valida.csv"))
    pedido, plano = _pedido_e_plano_da_sessao(client_autenticado)

    resposta_previa = client_autenticado.get(reverse("catalogo:importacao_previa"))
    assert resposta_previa.status_code == 200

    # O contexto é o que o template usa para preencher os campos ocultos do
    # formulário de confirmação — verificar isso aqui é o que faz este teste
    # falhar se as chaves de `_contexto_previa` forem renomeadas.
    assert resposta_previa.context["token"] == pedido.token
    assert resposta_previa.context["impressao_digital"] == plano.impressao_digital

    conteudo_html = resposta_previa.content.decode("utf-8")
    correspondencia_token = re.search(r'name="token" value="([^"]*)"', conteudo_html)
    correspondencia_impressao = re.search(
        r'name="impressao_digital" value="([^"]*)"', conteudo_html
    )
    assert correspondencia_token, "campo oculto 'token' não encontrado no HTML da prévia"
    assert correspondencia_impressao, (
        "campo oculto 'impressao_digital' não encontrado no HTML da prévia"
    )
    assert correspondencia_token.group(1) == pedido.token
    assert correspondencia_impressao.group(1) == plano.impressao_digital

    resposta_confirmar = client_autenticado.post(
        reverse("catalogo:importacao_confirmar"),
        {
            "token": correspondencia_token.group(1),
            "impressao_digital": correspondencia_impressao.group(1),
        },
    )

    assert resposta_confirmar.status_code == 302
    destino = resolve(urlsplit(resposta_confirmar.url).path)
    assert destino.view_name == "catalogo:execucao_detalhe"

    from catalogo import importacao

    assert importacao.obter_pedido(client_autenticado.session) is None
    assert Material.objects.filter(cadpro="000.000.002").exists()
    assert ExecucaoImportacao.objects.count() == 1


def test_impressao_digital_adulterada_nao_grava_nada_e_mantem_pedido_para_revisao(
    chefe_almoxarifado, csv_fixture
):
    client_autenticado = _cliente_autenticado(chefe_almoxarifado)
    _enviar(client_autenticado, csv_fixture("carga_inicial_valida.csv"))
    pedido, _plano = _pedido_e_plano_da_sessao(client_autenticado)

    resposta = client_autenticado.post(
        reverse("catalogo:importacao_confirmar"),
        {"token": pedido.token, "impressao_digital": "0" * 64},
    )

    assert resposta.status_code == 302
    assert resposta.url == reverse("catalogo:importacao_previa")
    assert _contagem_das_cinco_tabelas() == 0

    from catalogo import importacao

    assert importacao.obter_pedido(client_autenticado.session) is not None, (
        "a prévia continua disponível na sessão para uma nova tentativa"
    )


def test_falha_inesperada_na_confirmacao_nao_grava_nada_mantem_pedido_e_nao_vaza_detalhe_interno(
    chefe_almoxarifado, csv_fixture
):
    """`rotas-e-autorizacao.md` → "falha inesperada": rollback total, pedido
    mantido para nova tentativa, 200 na própria prévia — e a mensagem ao
    usuário nunca expõe o texto da exceção nem traceback (Constitution VI).

    Injeta a falha em `aplicar_plano` (chamado por `confirmar_importacao`),
    mesma técnica de `mock.patch.object` de `test_catalogo_atomicidade.py`
    (T017) — não é alteração de código de produção, só controle de teste.
    """
    from unittest import mock

    from catalogo import importacao

    client_autenticado = _cliente_autenticado(chefe_almoxarifado)
    _enviar(client_autenticado, csv_fixture("carga_inicial_valida.csv"))
    pedido, plano = _pedido_e_plano_da_sessao(client_autenticado)

    with mock.patch.object(importacao, "aplicar_plano", side_effect=RuntimeError("falha injetada")):
        resposta = client_autenticado.post(
            reverse("catalogo:importacao_confirmar"),
            {"token": pedido.token, "impressao_digital": plano.impressao_digital},
        )

    assert resposta.status_code == 200
    assert _contagem_das_cinco_tabelas() == 0

    pedido_mantido = importacao.obter_pedido(client_autenticado.session)
    assert pedido_mantido is not None, "o pedido de prévia deve sobreviver a uma falha inesperada"
    assert pedido_mantido.token == pedido.token

    conteudo_html = resposta.content.decode("utf-8")
    assert "falha injetada" not in conteudo_html, (
        "o texto da exceção interna nunca pode vazar para o usuário (Constitution VI)"
    )
    assert "RuntimeError" not in conteudo_html
    assert "Traceback" not in conteudo_html


def test_cancelamento_limpa_a_sessao_sem_efeito_em_banco(chefe_almoxarifado, csv_fixture):
    client_autenticado = _cliente_autenticado(chefe_almoxarifado)
    _enviar(client_autenticado, csv_fixture("carga_inicial_valida.csv"))

    from catalogo import importacao

    assert importacao.obter_pedido(client_autenticado.session) is not None

    resposta = client_autenticado.post(reverse("catalogo:importacao_cancelar"))

    assert resposta.status_code == 302
    assert resposta.url == reverse("catalogo:importacao_envio")
    assert importacao.obter_pedido(client_autenticado.session) is None
    assert _contagem_das_cinco_tabelas() == 0


def test_previa_sem_pedido_na_sessao_redireciona_para_envio(chefe_almoxarifado):
    client_autenticado = _cliente_autenticado(chefe_almoxarifado)

    resposta = client_autenticado.get(reverse("catalogo:importacao_previa"))

    assert resposta.status_code == 302
    assert resposta.url == reverse("catalogo:importacao_envio")


# ---------------------------------------------------------------------------
# Detalhe da execução: totais e exceções visíveis (FR-044).
# ---------------------------------------------------------------------------


def test_execucao_detalhe_mostra_totais_e_excecoes(chefe_almoxarifado, csv_fixture):
    client_autenticado = _cliente_autenticado(chefe_almoxarifado)
    _enviar(client_autenticado, csv_fixture("carga_inicial_casos_spec.csv"))
    pedido, plano = _pedido_e_plano_da_sessao(client_autenticado)

    resposta_confirmar = client_autenticado.post(
        reverse("catalogo:importacao_confirmar"),
        {"token": pedido.token, "impressao_digital": plano.impressao_digital},
    )
    assert resposta_confirmar.status_code == 302

    resposta_detalhe = client_autenticado.get(resposta_confirmar.url)

    assert resposta_detalhe.status_code == 200
    conteudo_html = resposta_detalhe.content.decode("utf-8")
    # Escopado ao par <dt>/<dd> do resumo (`execucao_detalhe.html`) — "9"
    # solto coincide por acidente com o CADPRO/SHA-256 exibidos na mesma
    # página.
    assert re.search(
        rf"<dt>Inseridos</dt>\s*<dd>\s*{plano.total_inseridos}\s*</dd>", conteudo_html
    ), f"total_inseridos ({plano.total_inseridos}) não encontrado no resumo"
    assert re.search(
        rf"<dt>Rejeitados</dt>\s*<dd>\s*{plano.total_rejeitados}\s*</dd>", conteudo_html
    ), f"total_rejeitados ({plano.total_rejeitados}) não encontrado no resumo"
    cadpros_de_recusas_identificaveis = [recusa.cadpro for recusa in plano.recusas if recusa.cadpro]
    for cadpro in cadpros_de_recusas_identificaveis:
        assert cadpro in conteudo_html


# ---------------------------------------------------------------------------
# T043 (US4) — prévia e detalhe da REIMPORTAÇÃO: divergências e alterações
# cadastrais visíveis, ausentes contados, nada gravado na prévia.
#
# Contrato de marcadores `data-*` proposto por este teste para o template de
# T047 (nenhuma seção de divergências/alterações existe ainda em
# `importacao_previa.html`/`execucao_detalhe.html` — só a de exceções, sem
# `data-secao`). Segue o padrão JÁ estabelecido em
# `catalogo/templates/catalogo/_resultados_consulta.html` (T035):
# `data-estado="vazio"` no elemento vazio de uma seção. Como não há
# precedente de `data-secao` no app, este arquivo FIXA a convenção que T047
# deve seguir:
#   - a seção de divergências (prévia e detalhe) é envolvida por um elemento
#     com `data-secao="divergencias"`, sempre presente;
#   - a seção de alterações cadastrais (só no detalhe) é envolvida por um
#     elemento com `data-secao="alteracoes"`, sempre presente;
#   - quando a lista da seção está vazia, algum elemento dentro dela carrega
#     `data-estado="vazio"` (mesma convenção de T035).
# `rotas-e-autorizacao.md` fixa `pagina_divergencias` para a paginação de
# divergências (prévia e detalhe). NÃO fixa o parâmetro da paginação de
# alterações cadastrais no detalhe — este arquivo propõe `pagina_alteracoes`
# por simetria com `pagina_excecoes`/`pagina_divergencias`; reportar ao
# coordenador para confirmar ou ajustar em T046/T047.
# ---------------------------------------------------------------------------


def test_previa_de_reimportacao_mostra_divergencias_atualizados_e_ausentes_sem_gravar_nada(
    chefe_almoxarifado, csv_fixture
):
    conteudo_inicial = csv_fixture("carga_inicial_valida.csv")
    _confirmar_diretamente(conteudo_inicial, chefe_almoxarifado, nome_arquivo="inicial.csv")

    client_autenticado = _cliente_autenticado(chefe_almoxarifado)
    antes = _contagem_das_cinco_tabelas()

    _enviar(client_autenticado, csv_fixture("reimportacao.csv"), nome="reimportacao.csv")
    pedido, plano = _pedido_e_plano_da_sessao(client_autenticado)
    resposta = client_autenticado.get(reverse("catalogo:importacao_previa"))

    assert resposta.status_code == 200
    assert _contagem_das_cinco_tabelas() == antes, "a prévia da reimportação não pode gravar nada"

    # Pré-condições da fixture (README de tests/fixtures/catalogo/): 1
    # inserido, 8 atualizados (4 com alteração), 1 divergência, 1 ausente.
    assert plano.total_inseridos == 1
    assert plano.total_atualizados == 8
    assert plano.total_atualizados_com_alteracao == 4
    assert plano.total_divergencias == 1
    assert plano.total_ausentes_no_arquivo == 1

    conteudo_html = resposta.content.decode("utf-8")
    assert str(plano.total_atualizados) in conteudo_html
    assert str(plano.total_atualizados_com_alteracao) in conteudo_html
    assert str(plano.total_ausentes_no_arquivo) in conteudo_html
    assert "ausente" in conteudo_html.lower(), (
        "FR-031 exige informar quantos materiais estão ausentes do arquivo"
    )

    assert 'data-secao="divergencias"' in conteudo_html
    # 010.020.031: saldo WMS 10, saldo do arquivo 15, diferença +5 — 3 casas,
    # pt-BR (floatformat:3).
    assert "010.020.031" in conteudo_html
    assert "10,000" in conteudo_html
    assert "15,000" in conteudo_html
    # "5,000" solto é substring de "15,000", já verificado acima — escopado à
    # célula de diferença (com o sinal "+", que só a diferença positiva
    # exibe), como no comentário acima. A classe da célula ganhou
    # `catalogo-diferenca` (revisão do gate visual, achado P2: peso
    # tipográfico como diferenciador não-cromático da diferença) — o regex
    # casa `class="table-cell-numeric ..."` em vez do valor exato da classe.
    assert re.search(
        r'<td class="table-cell-numeric[^"]*">\s*\+5,000\s*</td>', conteudo_html
    ), (
        "diferença +5,000 (WMS 10,000 → arquivo 15,000) deveria aparecer na célula de "
        "diferença da tabela de divergências"
    )

    # `pagina_divergencias` é o parâmetro fixo (`rotas-e-autorizacao.md`).
    # Com só 1 divergência a página única não gera link (padrão de
    # `_paginacao.html`, sem `?parametro=` quando não há próxima/anterior),
    # então o contrato é testado passando o parâmetro na querystring, não
    # procurando o nome dele no HTML.
    resposta_paginada = client_autenticado.get(
        reverse("catalogo:importacao_previa"), {"pagina_divergencias": "1"}
    )
    assert resposta_paginada.status_code == 200


def _linha_minima(cadpro="", disc1="", unid1="", quan3="", discr1="", grupo="",
                   subgrupo="", nomegrupo="", nomesubgrupo=""):
    """Mesmo helper de `tests/test_catalogo_importacao.py`/
    `tests/test_catalogo_reimportacao.py`, duplicado aqui só para este teste
    isolado — evita montar CSV com contagem manual de `;`."""
    valores = [cadpro, disc1, unid1, quan3, discr1, grupo, subgrupo, nomegrupo, nomesubgrupo]
    return ";".join(valores) + ";"


def _arquivo_minimo(*linhas_dados):
    cabecalho = "CADPRO;DISC1;UNID1;QUAN3;DISCR1;GRUPO;SUBGRUPO;NOMEGRUPO;NOMESUBGRUPO;"
    texto = "\r\n".join([cabecalho, *linhas_dados])
    return ("﻿" + texto).encode("utf-8")


def test_previa_de_reimportacao_mostra_diferenca_negativa_com_sinal(
    chefe_almoxarifado
):
    conteudo_inicial = _arquivo_minimo(
        _linha_minima(cadpro="060.070.080", disc1="ITEM SALDO ALTO", unid1="UN", quan3="20")
    )
    _confirmar_diretamente(conteudo_inicial, chefe_almoxarifado, nome_arquivo="inicial.csv")
    contagem_antes = _contagem_das_cinco_tabelas()

    conteudo_reimportacao = _arquivo_minimo(
        _linha_minima(cadpro="060.070.080", disc1="ITEM SALDO ALTO", unid1="UN", quan3="15")
    )

    client_autenticado = _cliente_autenticado(chefe_almoxarifado)
    _enviar(client_autenticado, conteudo_reimportacao, nome="reimportacao.csv")
    resposta = client_autenticado.get(reverse("catalogo:importacao_previa"))

    assert resposta.status_code == 200
    conteudo_html = resposta.content.decode("utf-8")
    assert "-5,000" in conteudo_html, (
        "diferença negativa (saldo do arquivo menor que o saldo do WMS) precisa "
        "aparecer com sinal explícito"
    )
    assert _contagem_das_cinco_tabelas() == contagem_antes, "a prévia não grava nada"


def test_previa_de_reimportacao_sem_divergencia_marca_secao_vazia(chefe_almoxarifado, csv_fixture):
    """Reimportar o mesmo arquivo sem nenhuma mudança: a seção de
    divergências continua presente, mas vazia (`data-estado="vazio"`)."""
    conteudo = csv_fixture("carga_inicial_valida.csv")
    _confirmar_diretamente(conteudo, chefe_almoxarifado, nome_arquivo="inicial.csv")

    client_autenticado = _cliente_autenticado(chefe_almoxarifado)
    _enviar(client_autenticado, conteudo, nome="repetido.csv")
    resposta = client_autenticado.get(reverse("catalogo:importacao_previa"))

    assert resposta.status_code == 200
    conteudo_html = resposta.content.decode("utf-8")
    # Escopado ao conteúdo da própria seção de divergências — checar as duas
    # substrings soltas no HTML inteiro não garante que o marcador vazio
    # esteja DENTRO dessa seção (poderia vir de qualquer outra seção vazia
    # da página, ex.: exceções).
    html_da_secao = _secao_html(conteudo_html, "divergencias")
    assert 'data-estado="vazio"' in html_da_secao


def test_execucao_detalhe_de_reimportacao_mostra_divergencias_e_alteracoes_cadastrais(
    chefe_almoxarifado, csv_fixture
):
    conteudo_inicial = csv_fixture("carga_inicial_valida.csv")
    _confirmar_diretamente(conteudo_inicial, chefe_almoxarifado, nome_arquivo="inicial.csv")

    client_autenticado = _cliente_autenticado(chefe_almoxarifado)
    _enviar(client_autenticado, csv_fixture("reimportacao.csv"), nome="reimportacao.csv")
    pedido, plano = _pedido_e_plano_da_sessao(client_autenticado)

    resposta_confirmar = client_autenticado.post(
        reverse("catalogo:importacao_confirmar"),
        {"token": pedido.token, "impressao_digital": plano.impressao_digital},
    )
    assert resposta_confirmar.status_code == 302

    resposta_detalhe = client_autenticado.get(resposta_confirmar.url)
    assert resposta_detalhe.status_code == 200
    conteudo_html = resposta_detalhe.content.decode("utf-8")

    assert 'data-secao="divergencias"' in conteudo_html
    assert 'data-secao="alteracoes"' in conteudo_html

    # Divergência de 010.020.031, com os dois valores e a diferença.
    assert "010.020.031" in conteudo_html
    assert "10,000" in conteudo_html
    assert "15,000" in conteudo_html

    # Alteração cadastral de 000.000.002 (descricao): CADPRO, campo, valor
    # anterior e novo, todos visíveis — nunca só um resumo.
    assert "000.000.002" in conteudo_html
    assert "PARAFUSO SEXTAVADO M8 ZINCADO" in conteudo_html
    assert "PARAFUSO SEXTAVADO M8" in conteudo_html

    execucao = ExecucaoImportacao.objects.get(sha256_arquivo=plano.sha256_arquivo)
    resposta_paginada = client_autenticado.get(
        reverse("catalogo:execucao_detalhe", kwargs={"pk": execucao.pk}),
        {"pagina_alteracoes": "1", "pagina_divergencias": "1"},
    )
    assert resposta_paginada.status_code == 200, (
        "pagina_alteracoes/pagina_divergencias precisam ser aceitos sem erro no detalhe "
        "(nome de pagina_alteracoes proposto por este teste — não fixado no contrato)"
    )


def _cliente_autenticado(usuario):
    from django.test import Client

    client = Client()
    client.force_login(usuario)
    return client
