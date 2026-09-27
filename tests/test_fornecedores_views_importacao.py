"""Testes das views de importação de fornecedores (T011), via `Client`.

Cobre `contracts/rotas-e-autorizacao.md` (seções "Envio", "Prévia",
"Efetivação" e "Cancelamento") e `research.md` R4 (upload em memória,
`csrf_exempt`/`csrf_protect`). Autorização em si é
`tests/test_fornecedores_permissoes.py` (T012); aqui o usuário é sempre
`chefe_almoxarifado` (`ROLE-WAREHOUSE-HEAD`), e o foco é o comportamento e
os efeitos observáveis de cada rota.

TDD: escrito antes das views, formulário e rotas existirem
(`fornecedores/urls.py` tem `urlpatterns = []`) — todo teste que chama
`reverse("fornecedores:...")` falha agora com `NoReverseMatch`.

Decisão de interface fixada por este arquivo, a pedido do coordenador
(rodada de 2026-09-25): o campo do formulário de envio se chama `arquivo`
(mesmo nome de `ArquivoImportacaoForm` do catálogo, `catalogo/forms.py`) —
ver `_enviar` abaixo. A seção de recusas ("exceções") segue o MESMO padrão
que a 001 usa para a dela: só `id="excecoes"`, paginação por
`?pagina_excecoes=` — SEM `data-secao` (a 001 só passou a usar
`data-secao` a partir de US4, para divergências/alterações; a seção de
exceções continua sem esse marcador até hoje, ver
`catalogo/templates/catalogo/execucao_detalhe.html`). `data-secao=
"alteracoes"`/`pagina_alteracoes` (US4 desta feature) NÃO são testados
aqui — entram em T028/T030, por instrução explícita do coordenador.

Não cobre a projeção mínima/sentinelas (`tests/test_fornecedores_dados_
minimos.py`, T009), nem atomicidade/concorrência/desempenho
(`tests/test_fornecedores_atomicidade.py`, T010).
"""

import re
import uuid
from urllib.parse import urlsplit

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import resolve, reverse

from fornecedores.models import (
    AlteracaoFornecedor,
    ExcecaoImportacaoFornecedores,
    ExecucaoImportacaoFornecedores,
    Fornecedor,
)

pytestmark = pytest.mark.django_db

_CABECALHO = "CODIF;NOME;NOM_FANT;INSMF;CODTIP;BLOQ_OPCAO;MSG_BLOQ;TIPO_BLOQ;"


def _cliente_autenticado(usuario, **kwargs):
    client = Client(**kwargs)
    client.force_login(usuario)
    return client


def _enviar(client, conteudo, nome="arquivo.csv"):
    """O campo do form é `arquivo` — mesmo nome do `ArquivoImportacaoForm`
    do catálogo (decisão de interface fixada por este arquivo, ver
    docstring do módulo)."""
    arquivo = SimpleUploadedFile(nome, conteudo, content_type="text/csv")
    return client.post(reverse("fornecedores:importacao_envio"), {"arquivo": arquivo})


def _pedido_e_plano_da_sessao(client):
    from fornecedores import importacao

    pedido = importacao.obter_pedido(client.session)
    assert pedido is not None, "esperava um pedido de prévia salvo na sessão após envio válido"
    plano = importacao.calcular_plano(pedido.leitura, pedido.sha256)
    return pedido, plano


def _contagem_das_quatro_tabelas():
    return (
        Fornecedor.objects.count()
        + ExecucaoImportacaoFornecedores.objects.count()
        + ExcecaoImportacaoFornecedores.objects.count()
        + AlteracaoFornecedor.objects.count()
    )


def _confirmar_diretamente(conteudo, usuario, nome_arquivo="arquivo.csv"):
    """Confirma uma importação direto pela camada de domínio (sem
    `Client`), para preparar um cadastro pré-existente sem repetir
    envio+confirmação por upload — mesma técnica de
    `tests/test_catalogo_views_importacao.py`."""
    import hashlib

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


def _linha(codif, nome="FORNECEDOR"):
    return f"{codif};{nome};;;01;S;;;"


def _arquivo(*linhas):
    texto = "\r\n".join([_CABECALHO, *linhas]) + "\r\n"
    return ("﻿" + texto).encode("utf-8")


CONTEUDO_VALIDO = _arquivo(_linha("900001", "FORNECEDOR VIEWS UM"))
CONTEUDO_COM_RECUSA = _arquivo(
    _linha("900011", "FORNECEDOR ACEITO"),
    # BLOQ_OPCAO vazio -> SITUACAO_BLOQUEIO_INVALIDA
    "900012;FORNECEDOR RECUSADO;;;01;;;;",
)


# ---------------------------------------------------------------------------
# Envio (GET/POST).
# ---------------------------------------------------------------------------


def test_get_envio_retorna_formulario(chefe_almoxarifado):
    client = _cliente_autenticado(chefe_almoxarifado)

    resposta = client.get(reverse("fornecedores:importacao_envio"))

    assert resposta.status_code == 200


def test_post_envio_valido_redireciona_a_previa(chefe_almoxarifado):
    client = _cliente_autenticado(chefe_almoxarifado)

    resposta = _enviar(client, CONTEUDO_VALIDO)

    assert resposta.status_code == 302
    assert resposta.url == reverse("fornecedores:importacao_previa")


def test_recusa_de_arquivo_no_envio_rerenderiza_com_erro_sem_gravar_sessao(chefe_almoxarifado):
    client = _cliente_autenticado(chefe_almoxarifado)
    conteudo_sem_coluna_obrigatoria = (
        "﻿" + "CODIF;NOME;NOM_FANT;INSMF;CODTIP;MSG_BLOQ;TIPO_BLOQ;\r\n"
        "1;FORNECEDOR;;;;;;\r\n"
    ).encode("utf-8")

    resposta = _enviar(client, conteudo_sem_coluna_obrigatoria, nome="sem_bloq.csv")

    assert resposta.status_code == 200
    assert "BLOQ_OPCAO" in resposta.content.decode("utf-8")

    from fornecedores import importacao

    assert importacao.obter_pedido(client.session) is None
    assert _contagem_das_quatro_tabelas() == 0


def test_arquivo_de_0_bytes_nao_e_recusado_e_gera_previa_com_zero_recebidos(chefe_almoxarifado):
    client = _cliente_autenticado(chefe_almoxarifado)

    resposta_envio = _enviar(client, b"", nome="vazio.csv")

    erros_do_formulario = (
        getattr(resposta_envio, "context", None) and resposta_envio.context["form"].errors
    )
    assert resposta_envio.status_code == 302, (
        f"upload de 0 bytes deveria seguir para a prévia: {erros_do_formulario}"
    )

    _, plano = _pedido_e_plano_da_sessao(client)
    assert plano.total_recebidos == 0
    assert plano.total_rejeitados == 0


def test_arquivo_maior_que_10mb_e_recusado(chefe_almoxarifado):
    """`10 MB + 1 byte` ainda cabe dentro da margem do upload handler de
    memória (`_LIMITE_HANDLER_UPLOAD_MEMORIA` = 10 MB + 64 KB, para o
    overhead do envelope multipart) — o handler aceita o corpo inteiro em
    memória, sem tocar disco, e é `ArquivoFornecedoresForm.clean_arquivo`
    quem recusa por tamanho, com precisão (`arquivo.size`, sem o overhead).
    A mensagem precisa ser a de tamanho excedido (`ARQUIVO_TAMANHO_
    EXCEDIDO`, `contracts/arquivo-fornecedores.md` §1). O caminho em que o
    PRÓPRIO handler descarta o corpo antes de chegar a `request.FILES` (body
    acima da margem) é
    `test_corpo_acima_da_margem_do_handler_tambem_e_recusado_como_tamanho_excedido`,
    abaixo."""
    client = _cliente_autenticado(chefe_almoxarifado)
    conteudo_grande = b"0" * (10 * 1024 * 1024 + 1)

    resposta = _enviar(client, conteudo_grande, nome="grande.csv")

    assert resposta.status_code == 200
    assert resposta.context["form"].errors["arquivo"] == ["O arquivo excede o limite de 10 MB."]
    assert resposta.context["form"].errors.as_data()["arquivo"][0].code == (
        "ARQUIVO_TAMANHO_EXCEDIDO"
    )
    assert "O arquivo excede o limite de 10 MB." in resposta.content.decode("utf-8")

    from fornecedores import importacao

    assert importacao.obter_pedido(client.session) is None


def test_arquivo_maior_que_10mb_sem_csrf_token_e_recusado_com_403(chefe_almoxarifado):
    """Mesmo cenário do teste anterior (corpo dentro da margem do handler,
    recusado por `clean_arquivo`) — prova que esse caminho de recusa por
    tamanho não contorna o CSRF: o token vem de um campo comum do multipart,
    sempre lido pelo parser antes de `ArquivoFornecedoresForm` rodar, então
    `csrf_protect` em `post()` continua valendo mesmo aqui."""
    client = _cliente_autenticado(chefe_almoxarifado, enforce_csrf_checks=True)
    conteudo_grande = b"0" * (10 * 1024 * 1024 + 1)

    resposta = _enviar(client, conteudo_grande, nome="grande.csv")

    assert resposta.status_code == 403
    from fornecedores import importacao

    assert importacao.obter_pedido(client.session) is None


def test_corpo_acima_da_margem_do_handler_tambem_e_recusado_como_tamanho_excedido(
    chefe_almoxarifado,
):
    """Diferente dos dois testes acima: um corpo maior que
    `_LIMITE_HANDLER_UPLOAD_MEMORIA` (10 MB + 64 KB de margem) nem chega a
    `request.FILES` — o próprio `_HandlerUploadEmMemoria` descarta o corpo
    (`tamanho_excedido = True`), e a view (`ImportacaoEnvioView.post`)
    substitui o erro genérico de "campo obrigatório" do `FileField` pelo
    mesmo código `ARQUIVO_TAMANHO_EXCEDIDO` e mensagem de
    `clean_arquivo` — o usuário nunca vê a mensagem enganosa."""
    client = _cliente_autenticado(chefe_almoxarifado)
    conteudo_grande = b"0" * (10 * 1024 * 1024 + 128 * 1024)

    resposta = _enviar(client, conteudo_grande, nome="grande.csv")

    assert resposta.status_code == 200
    assert resposta.context["form"].errors["arquivo"] == ["O arquivo excede o limite de 10 MB."]
    assert resposta.context["form"].errors.as_data()["arquivo"][0].code == (
        "ARQUIVO_TAMANHO_EXCEDIDO"
    )

    from fornecedores import importacao

    assert importacao.obter_pedido(client.session) is None


def test_corpo_acima_da_margem_do_handler_sem_csrf_token_e_recusado_com_403(
    chefe_almoxarifado,
):
    """O caminho em que o handler já descartou o corpo (acima da margem)
    também não contorna o CSRF — o campo `csrfmiddlewaretoken` é lido pelo
    parser multipart como um campo comum, independente do handler de
    arquivo, então `csrf_protect` em `post()` roda antes de qualquer lógica
    de formulário."""
    client = _cliente_autenticado(chefe_almoxarifado, enforce_csrf_checks=True)
    conteudo_grande = b"0" * (10 * 1024 * 1024 + 128 * 1024)

    resposta = _enviar(client, conteudo_grande, nome="grande.csv")

    assert resposta.status_code == 403
    from fornecedores import importacao

    assert importacao.obter_pedido(client.session) is None


def test_upload_entre_2_5mb_e_10mb_e_aceito_de_ponta_a_ponta(chefe_almoxarifado):
    """Prova end-to-end (via `Client` real) do limite de 10 MB da feature —
    diferente do limite padrão de memória do Django (2,5 MB). Complementa
    o mock de `tests/test_fornecedores_dados_minimos.py`, que prova que o
    handler de disco nunca é acionado; aqui o conteúdo é um CSV válido, e a
    prévia resultante precisa refletir TODOS os registros recebidos, sem
    truncamento."""
    client = _cliente_autenticado(chefe_almoxarifado)
    # Preenchimento em NOM_FANT só para atingir o tamanho de arquivo alvo com
    # poucos registros (mais barato de gravar/consultar do que dezenas de
    # milhares de linhas curtas) — o conteúdo em si não importa para este
    # teste, só o tamanho total do upload.
    enchimento = "X" * 1000
    linhas = [
        f"{codigo};FORNECEDOR GRANDE {codigo};{enchimento};;01;S;;;"
        for codigo in range(1, 3001)
    ]
    conteudo = _arquivo(*linhas)
    assert 2.5 * 1024 * 1024 < len(conteudo) < 10 * 1024 * 1024, (
        f"pré-condição: {len(conteudo)} bytes precisa ficar entre 2,5 MB e 10 MB"
    )

    resposta = _enviar(client, conteudo, nome="grande_valido.csv")

    assert resposta.status_code == 302
    _, plano = _pedido_e_plano_da_sessao(client)
    assert plano.total_recebidos == 3_000


def test_post_de_envio_sem_csrf_token_e_recusado(chefe_almoxarifado):
    """`research.md` R4: a view é `csrf_exempt` (necessário para trocar os
    upload_handlers antes do CSRF ler `request.POST`) + `csrf_protect` no
    método que processa o POST. Esta é a prova de que o CSRF continua
    valendo de verdade — um `csrf_exempt` mal aplicado desligaria a
    proteção para este único endpoint sem que nenhum outro teste da
    suíte (que usa o `client` padrão, sem `enforce_csrf_checks`) percebesse."""
    client = _cliente_autenticado(chefe_almoxarifado, enforce_csrf_checks=True)

    resposta = _enviar(client, CONTEUDO_VALIDO)

    assert resposta.status_code == 403
    from fornecedores import importacao

    assert importacao.obter_pedido(client.session) is None


# ---------------------------------------------------------------------------
# Envio e prévia não alteram nenhuma tabela de fornecedores (FR-016).
# ---------------------------------------------------------------------------


def test_envio_e_previa_nao_alteram_nenhuma_tabela_de_fornecedores(chefe_almoxarifado):
    client = _cliente_autenticado(chefe_almoxarifado)

    antes = _contagem_das_quatro_tabelas()
    resposta_envio = _enviar(client, CONTEUDO_COM_RECUSA)
    assert resposta_envio.status_code == 302

    resposta_previa = client.get(reverse("fornecedores:importacao_previa"))
    assert resposta_previa.status_code == 200

    assert _contagem_das_quatro_tabelas() == antes == 0


def test_previa_exibe_totais_e_recusas_sem_gravar_nada(chefe_almoxarifado):
    client = _cliente_autenticado(chefe_almoxarifado)
    _enviar(client, CONTEUDO_COM_RECUSA)
    _, plano = _pedido_e_plano_da_sessao(client)
    assert plano.total_rejeitados == 1, "pré-condição da fixture: 1 rejeitado"

    resposta = client.get(reverse("fornecedores:importacao_previa"))

    assert resposta.status_code == 200
    conteudo_html = resposta.content.decode("utf-8")
    assert str(plano.total_recebidos) in conteudo_html
    assert str(plano.total_rejeitados) in conteudo_html
    assert "900012" in conteudo_html, "o codif identificável da recusa precisa aparecer na prévia"
    assert "nada foi gravado" in conteudo_html.lower() or "nada gravado" in conteudo_html.lower()

    # Mesma convenção da 001 (id="excecoes", sem data-secao — ver docstring
    # do módulo) e paginação por ?pagina_excecoes=.
    assert 'id="excecoes"' in conteudo_html
    resposta_paginada = client.get(
        reverse("fornecedores:importacao_previa"), {"pagina_excecoes": "1"}
    )
    assert resposta_paginada.status_code == 200

    assert _contagem_das_quatro_tabelas() == 0


# ---------------------------------------------------------------------------
# Confirmação.
# ---------------------------------------------------------------------------


def test_confirmacao_valida_redireciona_ao_detalhe_e_remove_pedido_da_sessao(chefe_almoxarifado):
    client = _cliente_autenticado(chefe_almoxarifado)
    _enviar(client, CONTEUDO_VALIDO)
    pedido, plano = _pedido_e_plano_da_sessao(client)

    resposta = client.post(
        reverse("fornecedores:importacao_confirmar"),
        {"token": pedido.token, "impressao_digital": plano.impressao_digital},
    )

    assert resposta.status_code == 302
    destino = resolve(urlsplit(resposta.url).path)
    assert destino.view_name == "fornecedores:execucao_detalhe"

    from fornecedores import importacao

    assert importacao.obter_pedido(client.session) is None
    assert Fornecedor.objects.filter(codif="900001").exists()
    assert ExecucaoImportacaoFornecedores.objects.count() == 1


def test_confirmacao_valida_emite_mensagem_de_sucesso_com_os_totais(chefe_almoxarifado):
    client = _cliente_autenticado(chefe_almoxarifado)
    _enviar(client, CONTEUDO_VALIDO)
    pedido, plano = _pedido_e_plano_da_sessao(client)

    resposta = client.post(
        reverse("fornecedores:importacao_confirmar"),
        {"token": pedido.token, "impressao_digital": plano.impressao_digital},
        follow=True,
    )

    assert resposta.status_code == 200
    execucao = ExecucaoImportacaoFornecedores.objects.get()
    mensagens = [str(m) for m in resposta.context["messages"]]
    assert any(
        str(execucao.total_inseridos) in m
        and str(execucao.total_atualizados) in m
        and str(execucao.total_rejeitados) in m
        for m in mensagens
    ), mensagens


def test_confirmacao_repetida_mostra_ja_confirmada_e_vai_ao_detalhe(chefe_almoxarifado):
    execucao = _confirmar_diretamente(CONTEUDO_VALIDO, chefe_almoxarifado)

    client = _cliente_autenticado(chefe_almoxarifado)
    resposta = client.post(
        reverse("fornecedores:importacao_confirmar"),
        {"token": str(execucao.token_previa), "impressao_digital": "0" * 64},
        follow=True,
    )

    assert resposta.status_code == 200
    destino = resolve(urlsplit(resposta.redirect_chain[-1][0]).path)
    assert destino.view_name == "fornecedores:execucao_detalhe"
    mensagens = [str(m) for m in resposta.context["messages"]]
    assert any("já foi confirmada" in m.lower() for m in mensagens), mensagens
    assert ExecucaoImportacaoFornecedores.objects.count() == 1


def test_token_diferente_no_post_de_confirmar_redireciona_ao_envio(chefe_almoxarifado):
    client = _cliente_autenticado(chefe_almoxarifado)
    _enviar(client, CONTEUDO_VALIDO)

    resposta = client.post(
        reverse("fornecedores:importacao_confirmar"),
        {"token": str(uuid.uuid4()), "impressao_digital": "0" * 64},
    )

    assert resposta.status_code == 302
    assert resposta.url == reverse("fornecedores:importacao_envio")
    assert _contagem_das_quatro_tabelas() == 0


def test_impressao_digital_adulterada_nao_grava_nada_e_mantem_pedido_para_revisao(
    chefe_almoxarifado,
):
    client = _cliente_autenticado(chefe_almoxarifado)
    _enviar(client, CONTEUDO_VALIDO)
    pedido, _plano = _pedido_e_plano_da_sessao(client)

    resposta = client.post(
        reverse("fornecedores:importacao_confirmar"),
        {"token": pedido.token, "impressao_digital": "0" * 64},
    )

    assert resposta.status_code == 302
    assert resposta.url == reverse("fornecedores:importacao_previa")
    assert _contagem_das_quatro_tabelas() == 0

    from fornecedores import importacao

    assert importacao.obter_pedido(client.session) is not None


def test_falha_inesperada_na_confirmacao_nao_grava_nada_mantem_pedido_e_nao_vaza_detalhe_interno(
    chefe_almoxarifado,
):
    """Injeta a falha em `aplicar_plano` (chamado por `confirmar_
    importacao`), mesma técnica de `tests/test_fornecedores_atomicidade.py`
    — não é alteração de código de produção, só controle de teste."""
    from unittest import mock

    from fornecedores import importacao

    client = _cliente_autenticado(chefe_almoxarifado)
    _enviar(client, CONTEUDO_VALIDO)
    pedido, plano = _pedido_e_plano_da_sessao(client)

    with mock.patch.object(importacao, "aplicar_plano", side_effect=RuntimeError("falha injetada")):
        resposta = client.post(
            reverse("fornecedores:importacao_confirmar"),
            {"token": pedido.token, "impressao_digital": plano.impressao_digital},
        )

    assert resposta.status_code == 200
    assert _contagem_das_quatro_tabelas() == 0

    pedido_mantido = importacao.obter_pedido(client.session)
    assert pedido_mantido is not None, "o pedido de prévia deve sobreviver a uma falha inesperada"
    assert pedido_mantido.token == pedido.token

    conteudo_html = resposta.content.decode("utf-8")
    assert "falha injetada" not in conteudo_html
    assert "RuntimeError" not in conteudo_html
    assert "Traceback" not in conteudo_html


def test_falha_tambem_no_recalculo_da_previa_leva_ao_envio_sem_500(
    chefe_almoxarifado,
):
    """A falha que derruba a confirmação pode derrubar também o recálculo da
    prévia no re-render. A view leva à tela de envio, que não recalcula nada,
    com a mensagem genérica e o link para a prévia, que continua na sessão —
    mesmo com a falha ainda ativa ao seguir o redirect."""
    from unittest import mock

    from fornecedores import importacao

    client = _cliente_autenticado(chefe_almoxarifado)
    _enviar(client, CONTEUDO_VALIDO)
    pedido, plano = _pedido_e_plano_da_sessao(client)

    with (
        mock.patch.object(importacao, "aplicar_plano", side_effect=RuntimeError("falha injetada")),
        mock.patch(
            "fornecedores.views._contexto_previa", side_effect=RuntimeError("falha no recálculo")
        ),
    ):
        resposta = client.post(
            reverse("fornecedores:importacao_confirmar"),
            {"token": pedido.token, "impressao_digital": plano.impressao_digital},
            follow=True,
        )

    assert resposta.redirect_chain == [(reverse("fornecedores:importacao_envio"), 302)]
    assert resposta.status_code == 200
    assert _contagem_das_quatro_tabelas() == 0
    assert importacao.obter_pedido(client.session) is not None

    conteudo_html = resposta.content.decode("utf-8")
    assert "erro inesperado" in conteudo_html
    assert reverse("fornecedores:importacao_previa") in conteudo_html
    assert "falha no recálculo" not in conteudo_html


def test_cancelamento_limpa_a_sessao_sem_efeito_em_banco(chefe_almoxarifado):
    client = _cliente_autenticado(chefe_almoxarifado)
    _enviar(client, CONTEUDO_VALIDO)

    from fornecedores import importacao

    assert importacao.obter_pedido(client.session) is not None

    resposta = client.post(reverse("fornecedores:importacao_cancelar"))

    assert resposta.status_code == 302
    assert resposta.url == reverse("fornecedores:importacao_envio")
    assert importacao.obter_pedido(client.session) is None
    assert _contagem_das_quatro_tabelas() == 0


def test_previa_sem_pedido_na_sessao_redireciona_para_envio(chefe_almoxarifado):
    client = _cliente_autenticado(chefe_almoxarifado)

    resposta = client.get(reverse("fornecedores:importacao_previa"))

    assert resposta.status_code == 302
    assert resposta.url == reverse("fornecedores:importacao_envio")


# ---------------------------------------------------------------------------
# Detalhe da execução.
# ---------------------------------------------------------------------------


def test_execucao_detalhe_mostra_totais_e_recusas(chefe_almoxarifado):
    client = _cliente_autenticado(chefe_almoxarifado)
    _enviar(client, CONTEUDO_COM_RECUSA)
    pedido, plano = _pedido_e_plano_da_sessao(client)

    resposta_confirmar = client.post(
        reverse("fornecedores:importacao_confirmar"),
        {"token": pedido.token, "impressao_digital": plano.impressao_digital},
    )
    assert resposta_confirmar.status_code == 302

    resposta_detalhe = client.get(resposta_confirmar.url)

    assert resposta_detalhe.status_code == 200
    conteudo_html = resposta_detalhe.content.decode("utf-8")
    assert re.search(
        rf"<dt>Inseridos</dt>\s*<dd>{plano.total_inseridos}</dd>", conteudo_html
    ), f"total_inseridos ({plano.total_inseridos}) não encontrado no detalhe"
    assert "900012" in conteudo_html
    assert 'id="excecoes"' in conteudo_html
