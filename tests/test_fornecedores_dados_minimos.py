"""`INV-SUPPLIER-004` — dados mínimos (T009, US1, CRÍTICO).

Prova que nenhuma coluna descartada do arquivo (conta bancária, PIS,
endereço, contato, e as demais fora das 8 mantidas por FR-012) chega a
banco, sessão ou log, em nenhum momento do fluxo envio → prévia →
confirmação — inclusive numa reimportação, para que `AlteracaoFornecedor`
também seja exercitada pela varredura.

Usa `tests/fixtures/fornecedores/sentinelas.csv` (`tests/fixtures/
fornecedores/README.md`): valor-sentinela único (`SENTINELA-<COLUNA>-9137`)
em todas as 6 colunas descartadas do arquivo real, com um `\\n` isolado
embutido em `CONTATO`.

Escrito antes de `fornecedores.views`/`fornecedores.urls` (rotas) e
`fornecedores.importacao` existirem — as rotas de
`contracts/rotas-e-autorizacao.md` ainda não estão registradas
(`fornecedores/urls.py` tem `urlpatterns = []`), então todo teste que chama
`reverse("fornecedores:...")` falha agora com `NoReverseMatch`. Isso é
esperado (T017).

Não varre `tests/fixtures/fornecedores/valido_basico.csv` nem faz
asserções de comportamento de importação (totais, campos) — isso é
`tests/test_fornecedores_importacao.py` (T008). Aqui o foco é
exclusivamente a ausência de vazamento.
"""

import base64
import logging
import zlib
from unittest import mock

import pytest
from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.uploadhandler import TemporaryFileUploadHandler
from django.db import models as djmodels
from django.urls import reverse

pytestmark = pytest.mark.django_db

# Chave de sessão do pedido de prévia — valor fixado literalmente em
# `contracts/interface-importacao.md` (`CHAVE_SESSAO_PREVIA`). Usada como
# string, sem importar `fornecedores.importacao`, para não acoplar este
# teste de dados mínimos à existência do módulo de domínio (mesmo padrão de
# `tests/test_catalogo_permissoes.py`).
CHAVE_SESSAO_PREVIA = "fornecedores_importacao_previa"

MARCADOR_SENTINELA = "SENTINELA-"


def _enviar(client, conteudo, nome="arquivo.csv"):
    arquivo = SimpleUploadedFile(nome, conteudo, content_type="text/csv")
    return client.post(reverse("fornecedores:importacao_envio"), {"arquivo": arquivo})


def _confirmar(client):
    """Obtém `token`/`impressao_digital` de volta da PRÓPRIA sessão (mesma
    convenção de `tests/test_catalogo_views_importacao.py`, para não
    depender de nomes de campo do template) e confirma."""
    from fornecedores import importacao

    pedido = importacao.obter_pedido(client.session)
    assert pedido is not None, "esperava um pedido de prévia salvo na sessão após envio válido"
    plano = importacao.calcular_plano(pedido.leitura, pedido.sha256)
    return client.post(
        reverse("fornecedores:importacao_confirmar"),
        {"token": pedido.token, "impressao_digital": plano.impressao_digital},
    )


def _texto_leitura_da_sessao(dados_sessao):
    """Decodifica o valor bruto de `dados_sessao["leitura"]` — o mesmo
    pipeline `zlib` + base64 + JSON que `guardar_pedido` usa
    (`contracts/interface-importacao.md`) — SEM passar por `obter_pedido`,
    para provar o que está de fato PERSISTIDO, não o que a função de
    leitura escolhe exibir."""
    return zlib.decompress(base64.b64decode(dados_sessao["leitura"])).decode("utf-8")


def _nenhuma_coluna_de_texto_de_fornecedores_contem(substring):
    """Varredura genérica via introspecção do app `fornecedores`: para cada
    model e cada `CharField`/`TextField`, nenhuma linha pode conter
    `substring`. Genérica de propósito — uma coluna nova que algum dia
    vazasse dado teria que ser adicionada ao código de produção, e este
    teste já a pegaria sem precisar ser editado."""
    violacoes = []
    for model in apps.get_app_config("fornecedores").get_models():
        for field in model._meta.get_fields():
            if isinstance(field, (djmodels.CharField, djmodels.TextField)):
                if model.objects.filter(**{f"{field.name}__contains": substring}).exists():
                    violacoes.append(f"{model.__name__}.{field.name}")
    return violacoes


# ---------------------------------------------------------------------------
# Fluxo completo: envio -> prévia -> confirmação -> reimportação (para
# popular AlteracaoFornecedor também), com banco, sessão e log verificados
# em cada etapa relevante.
# ---------------------------------------------------------------------------


def test_nenhum_sentinela_em_banco_sessao_ou_log_apos_o_fluxo_completo(
    client, chefe_almoxarifado, csv_fornecedores, caplog
):
    client.force_login(chefe_almoxarifado)
    conteudo = csv_fornecedores("sentinelas.csv")
    # Segundo arquivo: mesmos sentinelas, um NOME alterado — popula
    # AlteracaoFornecedor também (senão a varredura dessa tabela é vácua:
    # sem nenhuma linha, `.filter(...).exists()` é trivialmente False).
    conteudo_reimportacao = conteudo.replace(
        b"FORNECEDOR SENTINELA UM", b"FORNECEDOR SENTINELA UM REVISADO"
    )

    with caplog.at_level(logging.DEBUG, logger="fornecedores.importacao"):
        resposta_envio = _enviar(client, conteudo, nome="sentinelas.csv")
        assert resposta_envio.status_code == 302
        resposta_previa = client.get(reverse("fornecedores:importacao_previa"))
        assert resposta_previa.status_code == 200
        resposta_confirmar = _confirmar(client)
        assert resposta_confirmar.status_code == 302

        # Antes de nada gravado, o banco varrido é vazio — passa trivialmente,
        # mas confirma que a varredura em si funciona (pré-condição do teste).
        assert not _nenhuma_coluna_de_texto_de_fornecedores_contem(MARCADOR_SENTINELA), (
            "nenhum sentinela deveria estar em banco logo após a primeira confirmação"
        )

        resposta_envio_2 = _enviar(client, conteudo_reimportacao, nome="sentinelas_v2.csv")
        assert resposta_envio_2.status_code == 302
        client.get(reverse("fornecedores:importacao_previa"))
        resposta_confirmar_2 = _confirmar(client)
        assert resposta_confirmar_2.status_code == 302

    violacoes = _nenhuma_coluna_de_texto_de_fornecedores_contem(MARCADOR_SENTINELA)
    assert not violacoes, f"sentinela encontrado em: {violacoes}"

    from fornecedores.models import AlteracaoFornecedor

    assert AlteracaoFornecedor.objects.exists(), (
        "pré-condição: a reimportação com NOME alterado precisa ter gerado ao menos "
        "uma AlteracaoFornecedor, senão a varredura dessa tabela não provou nada"
    )

    assert MARCADOR_SENTINELA not in caplog.text, (
        "nenhum log da importação pode conter um valor-sentinela de coluna descartada"
    )


# ---------------------------------------------------------------------------
# Sessão: decodificação do valor BRUTO (não via obter_pedido), whitelist de
# chaves, e ausência de bytes do arquivo original.
# ---------------------------------------------------------------------------


def test_sessao_nao_tem_nenhuma_chave_alem_da_projecao_minima(
    client, chefe_almoxarifado, csv_fornecedores
):
    """Prova direta de "sessão sem os bytes do arquivo": se um
    implementador um dia guardar `conteudo`/bytes ao lado de `leitura` (ex.
    para recalcular o SHA-256 sem reler o arquivo), esta whitelist de
    chaves falha imediatamente — sem depender de decodificar o valor para
    descobrir o vazamento."""
    client.force_login(chefe_almoxarifado)
    _enviar(client, csv_fornecedores("sentinelas.csv"), nome="sentinelas.csv")

    dados_sessao = client.session[CHAVE_SESSAO_PREVIA]

    assert set(dados_sessao) == {"token", "nome_arquivo", "tamanho", "sha256", "leitura"}


def test_sessao_decodificada_nao_contem_sentinela(client, chefe_almoxarifado, csv_fornecedores):
    client.force_login(chefe_almoxarifado)
    _enviar(client, csv_fornecedores("sentinelas.csv"), nome="sentinelas.csv")

    dados_sessao = client.session[CHAVE_SESSAO_PREVIA]
    texto_leitura = _texto_leitura_da_sessao(dados_sessao)

    assert MARCADOR_SENTINELA not in texto_leitura


# ---------------------------------------------------------------------------
# Upload sempre em memória — nunca `TemporaryFileUploadHandler` (research
# R4). Prova comportamental: um arquivo maior que o limite padrão de
# memória do Django (2,5 MB) precisa continuar em memória (o limite real é
# 10 MB, T016) — se a view trocar os handlers tarde demais, ou não trocar,
# o handler de disco seria acionado para um arquivo deste tamanho.
# ---------------------------------------------------------------------------


def test_post_de_envio_nunca_aciona_o_handler_de_upload_em_disco(client, chefe_almoxarifado):
    client.force_login(chefe_almoxarifado)
    # 3 MB: acima do limite padrão de memória do Django (2,5 MB) e abaixo do
    # limite de 10 MB da feature — não precisa ser um CSV válido: o que este
    # teste prova é só qual HANDLER processa o upload, antes de qualquer
    # validação de conteúdo.
    conteudo_grande = b"X" * (3 * 1024 * 1024)

    with mock.patch.object(
        TemporaryFileUploadHandler,
        "new_file",
        side_effect=AssertionError(
            "upload de 3 MB caiu no TemporaryFileUploadHandler (disco) — a view "
            "precisa trocar os upload_handlers para um handler em memória antes de "
            "qualquer acesso a request.POST/FILES (research.md R4)"
        ),
    ):
        resposta = _enviar(client, conteudo_grande, nome="grande.csv")

    # Se o handler de disco tivesse sido usado, o AssertionError do
    # side_effect teria propagado para fora de `_enviar` (o test client
    # relança exceções de servidor por padrão) — chegar aqui já é a prova.
    assert resposta.status_code in (200, 302)
