"""Contrato de markup do lote P4 do redesign (telas de estoque), `docs/redesign-observatory/`.

Superfícies cobertas: consulta de entradas, composição e revisão da entrada, detalhe da entrada e
estorno da entrada. Mesmo molde de `tests/test_importacoes_markup.py` (P3) e
`tests/test_consultas_historicos_markup.py` (P2): parsing estrutural por `tests/html_helpers.py`,
nunca regex de espaçamento.

O que este arquivo protege, em ordem de consequência:

- as duas ações de efeito real e irreversível, que a pessoa decide lendo o rótulo do botão:
  "Estornar entrada #N: X itens" (`btn-danger`, nunca o primário azul, dentro do form POST que de
  fato estorna) e "Confirmar entrada: N itens" (primário, antes de "Voltar e corrigir", com os
  hidden inputs que reconstroem a entrada inteira: `INV-ENT-001`, `INV-STOCK-001`);
- o estorno recusado não grava nada e não oferece a ação destrutiva (`INV-STOCK-004`): justificativa
  ausente com erro ligado ao campo; saldo insuficiente com as linhas bloqueadas marcadas só nelas
  e a barra reduzida a "Voltar";
- emitente bloqueado nunca é escolhível na busca (`INV-SUPPLIER-005`) e o CADPRO aparece como
  guardado, em célula própria (`INV-CATALOG-001`);
- a ação "Estornar entrada" só para quem pode (`PERM-STOCK-ENTRY-REVERSE`), "Registrar entrada" só
  para quem registra (`PERM-STOCK-ENTRY-CREATE`) e o auditor só consulta
  (`PERM-STOCK-HISTORY-VIEW`) — apresentação; a autorização real é de
  `tests/test_estoque_permissoes.py`;
- os ganchos de que HTMX e `estoque.js` dependem: `hx-*` do formulário de composição, indicador fora
  do alvo do swap, primeiro botão de envio neutro (Enter nunca aciona algo destrutivo), contrato do
  fragmento, `.error-box[role=alert]` focável e o nome do evento do HTMX 4;
- nenhum markup da fundação anterior, um único `<main>` e mensagens não duplicadas.

Não duplica: regras de domínio e efeitos de cada ação em `test_estoque_views_entrada.py`,
`test_estoque_views_estorno.py` e `test_estoque_views_consulta.py`; autorização em
`test_estoque_permissoes.py`; concorrência em `test_estoque_concorrencia.py`; o shell em
`tests/test_shell.py`.
"""

import json
import re
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.messages import constants as niveis
from django.contrib.messages.storage.cookie import CookieStorage
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.utils import timezone

from tests.html_helpers import analisar, hrefs_de

pytestmark = pytest.mark.django_db

HX = {"HTTP_HX_REQUEST": "true"}
NBSP = "\xa0"
RAIZ = Path(__file__).resolve().parents[1]

PREFIXOS_LEGADOS = (
    "page-header",
    "page-container",
    "page-section",
    "section-marker",
    "meta-grid",
    "table-wrapper-marker",
    "estoque-confirmacao",
)
CLASSES_LEGADAS = frozenset({"page", "back-link", "table-sticky-header", "alert-danger"})

# O CADPRO com zeros à esquerda e pontos: qualquer normalização o alteraria (`INV-CATALOG-001`).
CADPRO_A = "001.020.031"
CADPRO_B = "010.020.032"
NUMERO_DOCUMENTO = "NF-4821/2026"


# ---------------------------------------------------------------------------
# Montagem: materiais, emitentes, entradas e payloads da composição.
# ---------------------------------------------------------------------------


@pytest.fixture
def material_a(criar_material):
    """Saldo 10, unidade UN."""
    return criar_material(CADPRO_A, Decimal("10.000"), descricao="Parafuso sextavado M8")


@pytest.fixture
def material_b(criar_material):
    """Saldo 3, unidade UN."""
    return criar_material(CADPRO_B, Decimal("3.000"), descricao="Arruela lisa M8")


def _registrar(autor, itens, **overrides):
    """Registra uma entrada pela camada de domínio. `itens`: lista de `(material, quantidade)`."""
    from estoque.entradas import EntradaInformada, ItemInformado, registrar_entrada
    from estoque.models import MotivoEntrada, TipoDocumentoEntrada

    dados = EntradaInformada(
        chave_confirmacao=uuid.uuid4(),
        motivo=overrides.pop("motivo", MotivoEntrada.DOACAO_RECEBIDA),
        tipo_documento=overrides.pop("tipo_documento", TipoDocumentoEntrada.NOTA_FISCAL),
        numero_documento=overrides.pop("numero_documento", str(uuid.uuid4())),
        emitente_id=overrides.pop("emitente_id", None),
        itens=tuple(
            ItemInformado(material_id=material.pk, quantidade=Decimal(quantidade))
            for material, quantidade in itens
        ),
    )
    return registrar_entrada(dados, autor)


def _payload(itens=(), **campos):
    """POST da composição. `itens`: lista de `(pk do material, quantidade digitada)`."""
    payload = {
        "chave_confirmacao": str(uuid.uuid4()),
        "itens-TOTAL_FORMS": str(len(itens)),
        "itens-INITIAL_FORMS": "0",
        "itens-MIN_NUM_FORMS": "0",
        "itens-MAX_NUM_FORMS": "1000",
    }
    for indice, (material_pk, quantidade) in enumerate(itens):
        payload[f"itens-{indice}-material"] = str(material_pk)
        payload[f"itens-{indice}-quantidade"] = quantidade
    payload.update(campos)
    return payload


def _cabecalho(**campos):
    """Cabeçalho válido de uma doação recebida (sem emitente obrigatório)."""
    dados = {
        "motivo": "DOACAO_RECEBIDA",
        "tipo_documento": "NOTA_FISCAL",
        "numero_documento": NUMERO_DOCUMENTO,
    }
    dados.update(campos)
    return dados


def _compor(client, itens=(), **campos):
    return client.post(reverse("estoque:entrada_nova"), _payload(itens, **campos))


def _compor_htmx(client, itens=(), **campos):
    return client.post(reverse("estoque:entrada_nova"), _payload(itens, **campos), **HX)


def _principal(documento):
    return documento.unico("main")


def _ferramentas(documento):
    return _principal(documento).unico(classe="tools")


def _classes_legadas(documento):
    achadas = []
    for no in documento.descendentes():
        for classe in no.get("class", "").split():
            if classe in CLASSES_LEGADAS or classe.startswith(PREFIXOS_LEGADOS):
                achadas.append((no.tag, classe))
    return achadas


def _hidden(form):
    """`{nome: valor}` dos `<input type=hidden>` de um form, menos o token CSRF."""
    return {
        no.get("name"): no.get("value", "")
        for no in form.buscar("input", type="hidden")
        if no.get("name") != "csrfmiddlewaretoken"
    }


def _pares(no):
    """`{rótulo: <dd>}` do `dl.kv` dentro de `no`, na ordem do documento."""
    return dict(zip([dt.texto for dt in no.buscar("dt")], no.buscar("dd"), strict=True))


def _confere_identidade(no, nome, codigo, documento=None):
    """O fragmento `_emitente_identidade.html` dentro de `no`: nome · código · documento, na ordem.

    Código e documento são identificadores opacos (`INV-CATALOG-001`): mono e idênticos ao
    guardado (`texto_cru`, sem normalização de espaço). Os rótulos ", código"/", documento" são só
    para leitor de tela (`visually-hidden`) e os separadores só visuais (`aria-hidden`). Sem
    documento, a identidade termina no código: nada de separador ou rótulo sobrando."""
    esperado = [
        "estoque-emitente-nome", "estoque-emitente-sep", "visually-hidden", "table-cell-code",
    ]
    rotulos, mono = [", código"], [codigo]
    if documento is not None:
        esperado += ["estoque-emitente-sep", "visually-hidden", "table-cell-code"]
        rotulos.append(", documento")
        mono.append(documento)
    assert [filho.get("class") for filho in no.filhos] == esperado
    assert no.unico(classe="estoque-emitente-nome").texto == nome
    assert [c.texto_cru for c in no.buscar(classe="table-cell-code")] == mono
    assert [r.texto for r in no.buscar(classe="visually-hidden")] == rotulos
    assert all(s.get("aria-hidden") == "true" for s in no.buscar(classe="estoque-emitente-sep"))


def _dd_emitente(raiz):
    """O `<dd>` do rótulo "Emitente" (um único `dl.kv` com esse rótulo em `raiz`)."""
    (dd,) = [
        dd for dt, dd in zip(raiz.buscar("dt"), raiz.buscar("dd"), strict=True)
        if dt.texto == "Emitente"
    ]
    return dd


def _deixar_mensagem_pendente(client, nivel, texto):
    """Enfileira uma mensagem como o `messages.add_message` de uma view anterior."""
    armazenamento = CookieStorage(HttpRequest())
    armazenamento.add(nivel, texto)
    resposta = HttpResponse()
    armazenamento.update(resposta)
    client.cookies["messages"] = resposta.cookies["messages"].value


# ---------------------------------------------------------------------------
# 1. Todas as telas: shell único, sem fundação anterior, mensagens uma única vez.
# ---------------------------------------------------------------------------


@pytest.fixture
def telas(client, funcionario_almoxarifado, chefe_almoxarifado, material_a, material_b):
    """Cada tela de estoque como `(usuário, url, h1, método de obtenção)`, já com os dados."""
    registrada = _registrar(
        funcionario_almoxarifado, [(material_a, "5"), (material_b, "2.5")], numero_documento="D-1"
    )
    estornada = _registrar(
        funcionario_almoxarifado, [(material_a, "1")], numero_documento="D-2"
    )
    from estoque.entradas import estornar_entrada

    estornar_entrada(estornada.pk, "Digitação errada.", chefe_almoxarifado)

    def obter(url, h1, usuario, **extras):
        return SimpleNamespace(url=url, h1=h1, usuario=usuario, extras=extras)

    def por_pk(nome, entrada):
        return reverse(f"estoque:{nome}", args=[entrada.pk])

    revisao = _payload(
        [(material_a.pk, "5")], acao="revisar", **_cabecalho()
    )
    return {
        "entradas": obter(reverse("estoque:entradas"), "Consulta de entradas", chefe_almoxarifado),
        "entrada-nova": obter(
            reverse("estoque:entrada_nova"), "Registrar entrada de materiais", chefe_almoxarifado
        ),
        "entrada-revisao": obter(
            reverse("estoque:entrada_nova"),
            "Registrar entrada de materiais",
            chefe_almoxarifado,
            dados=revisao,
        ),
        "entrada-detalhe": obter(
            por_pk("entrada_detalhe", registrada),
            f"Entrada #{registrada.pk} Registrada",
            chefe_almoxarifado,
        ),
        "entrada-detalhe-estornada": obter(
            por_pk("entrada_detalhe", estornada),
            f"Entrada #{estornada.pk} Estornada",
            chefe_almoxarifado,
        ),
        "entrada-estorno": obter(
            por_pk("entrada_estorno", registrada),
            f"Estornar entrada #{registrada.pk}",
            chefe_almoxarifado,
        ),
        "entrada-estorno-bloqueado": obter(
            por_pk("entrada_estorno", registrada),
            f"Estornar entrada #{registrada.pk} Bloqueado",
            chefe_almoxarifado,
            reduzir_saldo=(material_b, Decimal("1.000")),
        ),
    }


@pytest.fixture
def tela(request, client, telas):
    """A tela parametrizada, já com o usuário logado e o estado preparado."""
    alvo = telas[request.param]
    client.force_login(alvo.usuario)
    if "reduzir_saldo" in alvo.extras:
        from catalogo.models import Material

        material, saldo = alvo.extras["reduzir_saldo"]
        Material.objects.filter(pk=material.pk).update(saldo=saldo)
    alvo.client = client
    alvo.obter = lambda: (
        client.post(alvo.url, alvo.extras["dados"])
        if "dados" in alvo.extras
        else client.get(alvo.url)
    )
    return alvo


def _telas(*nomes):
    return pytest.mark.parametrize(
        "tela", [pytest.param(nome, id=nome) for nome in nomes], indirect=True
    )


TODAS = (
    "entradas",
    "entrada-nova",
    "entrada-revisao",
    "entrada-detalhe",
    "entrada-detalhe-estornada",
    "entrada-estorno",
    "entrada-estorno-bloqueado",
)


@_telas(*TODAS)
def test_tela_tem_um_unico_main_e_o_h1_no_cabecalho(tela):
    resposta = tela.obter()

    assert resposta.status_code == 200
    documento = analisar(resposta.content)
    principal = documento.unico("main", id="main")
    assert len(documento.buscar("main")) == 1
    (titulo,) = documento.buscar("h1")
    assert titulo.texto == tela.h1
    assert any(a.tem_classe("top") and a.pai is principal for a in titulo.ancestrais())


@_telas(*TODAS)
def test_tela_nao_traz_markup_da_fundacao_anterior(tela):
    documento = analisar(tela.obter().content)

    assert _classes_legadas(documento) == []


def test_detector_de_classes_legadas_reconhece_cada_familia_proibida():
    """Sem isto, a verificação acima passaria em silêncio se o detector deixasse de enxergar."""
    legado = (
        '<div class="page-header"></div><div class="page-container"></div>'
        '<div class="page"></div><a class="back-link"></a><div class="section-marker"></div>'
        '<section class="page-section"></section><dl class="meta-grid"></dl>'
        '<div class="table-wrapper-marker-attached"></div>'
        '<table class="table table-sticky-header"></table>'
        '<div class="estoque-confirmacao-sticky"></div><div class="alert-danger"></div>'
    )
    moderno = '<div class="top"><div class="tools card table-row-error alert-warning"></div></div>'

    assert len(_classes_legadas(analisar(legado))) == 11
    assert _classes_legadas(analisar(moderno)) == []


@pytest.mark.parametrize(
    "nivel, classe, papel",
    [
        pytest.param(niveis.SUCCESS, "alert-success", "status", id="sucesso"),
        pytest.param(niveis.ERROR, "error-box", "alert", id="erro"),
    ],
)
@_telas("entradas", "entrada-nova", "entrada-detalhe", "entrada-estorno")
def test_mensagem_pendente_aparece_uma_unica_vez_no_main(tela, nivel, classe, papel):
    texto = "Mensagem-de-teste-unica-7c1e"
    _deixar_mensagem_pendente(tela.client, nivel, texto)

    resposta = tela.obter()

    documento = analisar(resposta.content)
    (container,) = documento.buscar(classe="messages")
    assert container.pai is _principal(documento)
    (mensagem,) = container.buscar(classe=classe)
    assert (mensagem.get("role"), mensagem.texto) == (papel, texto)
    assert resposta.content.decode().count(texto) == 1


def test_aviso_de_entrada_ja_estornada_aparece_uma_unica_vez_no_detalhe(
    client, chefe_almoxarifado, material_a
):
    from estoque.entradas import estornar_entrada

    entrada = _registrar(chefe_almoxarifado, [(material_a, "5")])
    estornar_entrada(entrada.pk, "Digitação errada.", chefe_almoxarifado)
    client.force_login(chefe_almoxarifado)
    url_estorno = reverse("estoque:entrada_estorno", args=[entrada.pk])

    for resposta in (
        client.get(url_estorno, follow=True),
        client.post(url_estorno, {"justificativa": "De novo."}, follow=True),
    ):
        detalhe = reverse("estoque:entrada_detalhe", args=[entrada.pk])
        assert resposta.redirect_chain[-1][0] == detalhe
        documento = analisar(resposta.content)
        (container,) = documento.buscar(classe="messages")
        (aviso,) = container.buscar(classe="alert")
        assert aviso.tem_classe("alert-warning") and aviso.get("role") == "status"
        assert aviso.texto == "Esta entrada já foi estornada."
        assert resposta.content.decode().count("já foi estornada") == 1


# ---------------------------------------------------------------------------
# 2. Trilha na `.sub` e selo de situação.
# ---------------------------------------------------------------------------


def _trilha(documento):
    sub = _principal(documento).unico(classe="sub")
    return sub.unico("nav", aria_label="Trilha de navegação")


@pytest.mark.parametrize(
    "nome, destinos, destino_atual",
    [
        pytest.param("entrada-nova", ["estoque:entradas"], "Registrar entrada", id="composicao"),
        pytest.param("entrada-detalhe", ["estoque:entradas"], None, id="detalhe"),
        pytest.param(
            "entrada-estorno",
            ["estoque:entradas", "estoque:entrada_detalhe"],
            "Estorno",
            id="estorno",
        ),
    ],
)
def test_trilha_leva_de_volta_a_consulta_e_nomeia_o_destino_atual(
    client, telas, nome, destinos, destino_atual
):
    alvo = telas[nome]
    client.force_login(alvo.usuario)
    pk = re.search(r"/(\d+)/", alvo.url)

    documento = analisar(client.get(alvo.url).content)

    trilha = _trilha(documento)
    esperados = [
        reverse(d, args=[pk.group(1)]) if d == "estoque:entrada_detalhe" else reverse(d)
        for d in destinos
    ]
    assert [a.get("href") for a in trilha.buscar("a")] == esperados
    assert trilha.buscar("a")[0].texto == "Consulta de entradas"
    # O destino atual é o último item, sem link.
    assert trilha.texto_corrido.endswith(destino_atual or f"Entrada #{pk.group(1)}")
    # Os separadores são decoração: fora da árvore de acessibilidade.
    assert all(s.get("aria-hidden") == "true" for s in trilha.buscar("span"))


@pytest.mark.parametrize(
    "nome, selo, classe",
    [
        pytest.param("entrada-detalhe", "Registrada", "badge-success", id="registrada"),
        pytest.param("entrada-detalhe-estornada", "Estornada", "badge-neutral", id="estornada"),
    ],
)
def test_detalhe_declara_a_situacao_no_titulo_com_o_selo_certo(client, telas, nome, selo, classe):
    """Estornada é situação encerrada, não erro: `badge-neutral`, nunca o vermelho de `danger`."""
    alvo = telas[nome]
    client.force_login(alvo.usuario)

    documento = analisar(client.get(alvo.url).content)

    (badge,) = documento.unico("h1").buscar(classe="badge")
    assert badge.texto == selo and badge.tem_classe(classe)
    assert not badge.tem_classe("badge-danger")


# ---------------------------------------------------------------------------
# 3. Detalhe: ação de estornar por papel, estorno antes dos itens, registro.
# ---------------------------------------------------------------------------


@pytest.fixture
def entrada_de_dois_itens(funcionario_almoxarifado, material_a, material_b, criar_fornecedor):
    """Entrada de 5 do A (saldo 10 -> 15) e 2,5 do B (saldo 3 -> 5,5), com emitente."""
    emitente = criar_fornecedor("007001", "Papelaria Central", documento="12.345.678/0001-95")
    return _registrar(
        funcionario_almoxarifado,
        [(material_a, "5"), (material_b, "2.5")],
        motivo="COMPRA",
        numero_documento=NUMERO_DOCUMENTO,
        emitente_id=emitente.pk,
    )


def _detalhe(client, usuario, entrada):
    client.force_login(usuario)
    resposta = client.get(reverse("estoque:entrada_detalhe", args=[entrada.pk]))
    assert resposta.status_code == 200
    return analisar(resposta.content)


def test_chefe_ve_estornar_em_ferramentas_como_convite_destrutivo_nunca_como_primario(
    client, chefe_almoxarifado, entrada_de_dois_itens
):
    """`PERM-STOCK-ENTRY-REVERSE`: a ação é um link secundário de perigo em `.tools`; o
    preenchido de perigo fica só na confirmação do estorno (`btn-danger`) e o primário azul nunca
    é de estornar."""
    entrada = entrada_de_dois_itens

    documento = _detalhe(client, chefe_almoxarifado, entrada)

    (acao,) = _ferramentas(documento).buscar("a")
    assert acao.get("href") == reverse("estoque:entrada_estorno", args=[entrada.pk])
    assert acao.texto == "Estornar entrada"
    assert acao.tem_classe("btn-secondary-danger")
    assert not acao.tem_classe("btn-primary") and not acao.tem_classe("btn-danger")
    # Só um caminho para o estorno, e é este.
    estorno = reverse("estoque:entrada_estorno", args=[entrada.pk])
    assert [a for a in documento.buscar("a", href=True) if a.attrs["href"] == estorno] == [acao]
    assert _principal(documento).buscar("form") == []


@pytest.mark.parametrize("usuario", ["funcionario_almoxarifado", "auditor"])
def test_quem_nao_estorna_ve_o_detalhe_sem_acao_nem_caminho_para_o_estorno(
    request, client, entrada_de_dois_itens, usuario
):
    """Apresentação de `PERM-STOCK-ENTRY-REVERSE`; o 403 real é de `test_estoque_permissoes`."""
    entrada = entrada_de_dois_itens

    documento = _detalhe(client, request.getfixturevalue(usuario), entrada)

    assert _ferramentas(documento).buscar("a") == []
    assert reverse("estoque:entrada_estorno", args=[entrada.pk]) not in hrefs_de(documento)
    assert "Estornar entrada" not in _principal(documento).texto
    assert documento.unico("h1").buscar(classe="badge")[0].texto == "Registrada"


def test_entrada_estornada_nao_oferece_estornar_nem_ao_chefe(
    client, chefe_almoxarifado, entrada_de_dois_itens
):
    from estoque.entradas import estornar_entrada

    estornar_entrada(entrada_de_dois_itens.pk, "Digitação errada.", chefe_almoxarifado)

    documento = _detalhe(client, chefe_almoxarifado, entrada_de_dois_itens)

    assert _ferramentas(documento).buscar("a") == []
    assert reverse("estoque:entrada_estorno", args=[entrada_de_dois_itens.pk]) not in hrefs_de(
        documento
    )


def _cards(documento):
    return [s for s in _principal(documento).buscar("section", classe="card")]


def test_detalhe_de_entrada_registrada_traz_registro_e_itens_sem_card_de_estorno(
    client, chefe_almoxarifado, entrada_de_dois_itens
):
    documento = _detalhe(client, chefe_almoxarifado, entrada_de_dois_itens)

    assert [c.unico("h2").texto for c in _cards(documento)] == ["Registro", "Itens (2)"]


def test_detalhe_de_entrada_estornada_mostra_o_estorno_antes_do_registro_e_dos_itens(
    client, chefe_almoxarifado, entrada_de_dois_itens
):
    """O estorno é o fato mais recente: por quem, quando e por quê vêm antes de tudo."""
    from estoque.entradas import estornar_entrada

    estornar_entrada(
        entrada_de_dois_itens.pk, "Nota fiscal lançada em duplicidade.", chefe_almoxarifado
    )

    documento = _detalhe(client, chefe_almoxarifado, entrada_de_dois_itens)

    cards = _cards(documento)
    assert [c.unico("h2").texto for c in cards] == ["Estorno", "Registro", "Itens (2)"]
    estorno = cards[0]
    assert estorno.get("aria-labelledby") == estorno.unico("h2").get("id")
    dados = dict(zip(
        [dt.texto for dt in estorno.buscar("dt")], estorno.buscar("dd"), strict=True
    ))
    assert list(dados) == ["Estornada por", "Estornada em", "Justificativa"]
    assert dados["Estornada por"].unico(classe="table-cell-code").texto == (
        chefe_almoxarifado.matricula
    )
    assert dados["Estornada em"].texto
    assert dados["Justificativa"].texto == "Nota fiscal lançada em duplicidade."


def test_registro_mostra_a_referencia_o_emitente_e_o_autor_como_dados_opacos(
    client, auditor, funcionario_almoxarifado, entrada_de_dois_itens
):
    """O código do emitente (`INV-SUPPLIER-*`) e a matrícula saem em mono, sem formatação."""
    documento = _detalhe(client, auditor, entrada_de_dois_itens)

    registro = next(c for c in _cards(documento) if c.unico("h2").texto == "Registro")
    dados = _pares(registro)
    assert list(dados) == [
        "Motivo", "Tipo de documento", "Número do documento", "Emitente", "Registrada por",
        "Registrada em",
    ]
    assert dados["Motivo"].texto == "Compra"
    assert dados["Número do documento"].texto == NUMERO_DOCUMENTO
    # Zeros à esquerda e pontuação do documento, exatamente como guardados.
    _confere_identidade(dados["Emitente"], "Papelaria Central", "007001", "12.345.678/0001-95")
    assert dados["Registrada por"].unico(classe="table-cell-code").texto == (
        funcionario_almoxarifado.matricula
    )


def test_registro_sem_emitente_diz_sem_emitente(
    client, auditor, funcionario_almoxarifado, material_a
):
    entrada = _registrar(funcionario_almoxarifado, [(material_a, "1")])

    documento = _detalhe(client, auditor, entrada)

    registro = next(c for c in _cards(documento) if c.unico("h2").texto == "Registro")
    (emitente,) = [
        dd for dt, dd in zip(registro.buscar("dt"), registro.buscar("dd"), strict=True)
        if dt.texto == "Emitente"
    ]
    assert emitente.texto == "Sem emitente"


@pytest.mark.parametrize(
    "emitente, documento",
    [
        pytest.param("007001", "12.345.678/0001-95", id="com-documento"),
        pytest.param("007003", None, id="sem-documento"),
        pytest.param(None, None, id="sem-emitente"),
    ],
)
def test_identidade_do_emitente_e_a_mesma_no_detalhe_no_estorno_e_na_revisao(
    client, chefe_almoxarifado, material_a, criar_fornecedor, emitente, documento
):
    """Um só fragmento nas três telas: o documento só aparece quando existe (sem separador
    solto) e "Sem emitente" quando não há emitente (`INV-CATALOG-001`: valores como guardados)."""
    fornecedor = (
        criar_fornecedor(emitente, "Papelaria Central", documento=documento or "")
        if emitente
        else None
    )
    motivo = "COMPRA" if fornecedor else "DOACAO_RECEBIDA"
    entrada = _registrar(
        chefe_almoxarifado, [(material_a, "1")], motivo=motivo,
        emitente_id=fornecedor.pk if fornecedor else None,
    )
    client.force_login(chefe_almoxarifado)
    revisao = _compor_htmx(
        client, [(material_a.pk, "1")], acao="revisar",
        **_cabecalho(motivo=motivo, emitente=str(fornecedor.pk) if fornecedor else ""),
    )

    celulas = [
        _dd_emitente(analisar(client.get(reverse(f"estoque:{nome}", args=[entrada.pk])).content))
        for nome in ("entrada_detalhe", "entrada_estorno")
    ] + [_dd_emitente(analisar(revisao.content))]

    for dd in celulas:
        if fornecedor is None:
            assert dd.texto == "Sem emitente" and dd.filhos == []
        else:
            _confere_identidade(dd, "Papelaria Central", emitente, documento)


def test_itens_do_detalhe_ficam_em_regiao_nomeada_com_cadpro_e_quantidade_como_gravados(
    client, auditor, entrada_de_dois_itens
):
    documento = _detalhe(client, auditor, entrada_de_dois_itens)

    itens = next(c for c in _cards(documento) if c.unico("h2").texto.startswith("Itens"))
    regiao = itens.unico(classe="table-wrapper")
    assert (regiao.get("role"), regiao.get("aria-label"), regiao.get("tabindex")) == (
        "region", "Tabela de itens da entrada", "0",
    )
    assert [th.texto for th in regiao.buscar("th")] == [
        "Código", "Descrição", "Quantidade recebida", "Unidade",
    ]
    linhas = [[td.texto for td in tr.buscar("td")] for tr in regiao.unico("tbody").buscar("tr")]
    # INV-CATALOG-001: o CADPRO como guardado; quantidades em pt-BR, só as casas significativas.
    assert linhas == [
        [CADPRO_A, "Parafuso sextavado M8", "5", "UN"],
        [CADPRO_B, "Arruela lisa M8", "2,5", "UN"],
    ]
    assert [c.texto for c in regiao.buscar("td", classe="table-cell-code")] == [CADPRO_A, CADPRO_B]


def _data_esperada(momento):
    """O formato da lista, no fuso da aplicação (não o `str(datetime)` com segundos e fuso)."""
    return timezone.localtime(momento).strftime("%d/%m/%Y %H:%M")


def test_datas_do_detalhe_e_do_estorno_seguem_o_formato_da_lista(
    client, chefe_almoxarifado, entrada_de_dois_itens
):
    """Registro (detalhe e estorno) e card Estorno: `d/m/Y H:i`, igual à coluna da lista."""
    from estoque.entradas import estornar_entrada

    entrada = entrada_de_dois_itens
    registrada_em = _data_esperada(entrada.registrada_em)
    padrao = re.compile(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}")
    assert padrao.fullmatch(registrada_em)

    na_tela_de_estorno = _estorno(client, chefe_almoxarifado, entrada)
    assert _pares(na_tela_de_estorno)["Registrada em"].texto == registrada_em

    estornar_entrada(entrada.pk, "Nota fiscal lançada em duplicidade.", chefe_almoxarifado)
    documento = _detalhe(client, chefe_almoxarifado, entrada)

    cards = {c.unico("h2").texto: c for c in _cards(documento)}
    assert _pares(cards["Registro"])["Registrada em"].texto == registrada_em
    estorno = cards["Estorno"]
    from estoque.models import EstornoEntrada

    estornada_em = _data_esperada(EstornoEntrada.objects.get(entrada=entrada).estornada_em)
    assert _pares(estorno)["Estornada em"].texto == estornada_em
    assert padrao.fullmatch(estornada_em)
    # A nota diz o efeito do estorno no estoque, em texto do próprio card.
    assert estorno.unico(classe="estoque-nota-card").texto == (
        "As quantidades desta entrada saíram do saldo dos materiais."
    )


# ---------------------------------------------------------------------------
# 4. Estorno: a ação destrutiva e as recusas sem efeito (`INV-STOCK-004`).
# ---------------------------------------------------------------------------


# Mesma ordem na revisão e no estorno (o usuário lê a conta da esquerda para a direita:
# saldo atual, quantidade, saldo resultante); só o rótulo da quantidade muda.
COLUNAS_REVISAO = [
    "Código", "Descrição", "Saldo atual", "Quantidade", "Saldo resultante", "Unidade",
]
COLUNAS_ESTORNO = [
    "Código", "Descrição", "Saldo atual", "Quantidade a estornar", "Saldo resultante", "Unidade",
]


def _estorno(client, chefe, entrada):
    client.force_login(chefe)
    resposta = client.get(reverse("estoque:entrada_estorno", args=[entrada.pk]))
    assert resposta.status_code == 200
    return analisar(resposta.content)


def test_confirmacao_do_estorno_e_um_form_post_com_o_destrutivo_recitando_a_consequencia(
    client, chefe_almoxarifado, entrada_de_dois_itens
):
    entrada = entrada_de_dois_itens
    url_estorno = reverse("estoque:entrada_estorno", args=[entrada.pk])

    documento = _estorno(client, chefe_almoxarifado, entrada)

    principal = _principal(documento)
    (form,) = principal.buscar("form")
    assert form.get("method") == "post" and form.get("action") == url_estorno
    assert "data-processing-form" in form.attrs
    assert form.get("data-processing-label") == "Estornando…"
    assert form.buscar("input", type="hidden", name="csrfmiddlewaretoken")
    # A barra está dentro do form: o botão de submit é o do form que de fato estorna.
    barra = form.unico(classe="confirmation-bar-card")
    (botao,) = barra.buscar("button", type="submit")
    assert botao.tem_classe("btn-danger") and "data-processing-submit" in botao.attrs
    assert botao.unico("span").get("data-processing-submit-label") == ""
    # Nome acessível inteiro: a consequência, com o número e o total de itens.
    assert botao.texto_corrido == f"Estornar entrada #{entrada.pk}: 2 itens"
    assert botao.unico("small", classe="confirmation-bar-totais").texto_corrido == ": 2 itens"
    assert "aria-label" not in botao.attrs and "aria-hidden" not in botao.attrs
    # O destrutivo vem antes de "Cancelar", que leva ao detalhe sem estornar.
    controles = [c for c in barra.descendentes() if c.tag in {"button", "a"}]
    assert controles[0] is botao
    (cancelar,) = barra.buscar("a")
    assert controles[1] is cancelar and cancelar.texto == "Cancelar"
    assert cancelar.get("href") == reverse("estoque:entrada_detalhe", args=[entrada.pk])
    assert cancelar.tem_classe("btn-secondary")
    # Resumo curto (só celular), fora da árvore de acessibilidade.
    resumo = barra.unico(classe="confirmation-bar-resumo")
    assert resumo.get("aria-hidden") == "true"
    assert resumo.texto_cru.strip() == f"Entrada #{entrada.pk} · 2{NBSP}itens"
    # Estornar nunca é a ação afirmativa da página: nenhum primário azul.
    assert principal.buscar(classe="btn-primary") == []


def test_rotulo_do_estorno_vai_ao_singular_com_um_item(client, chefe_almoxarifado, material_a):
    entrada = _registrar(chefe_almoxarifado, [(material_a, "5")])

    documento = _estorno(client, chefe_almoxarifado, entrada)

    botao = _principal(documento).unico("button", classe="btn-danger")
    assert botao.texto_corrido == f"Estornar entrada #{entrada.pk}: 1 item"
    resumo = _principal(documento).unico(classe="confirmation-bar-resumo")
    assert resumo.texto_cru.strip() == f"Entrada #{entrada.pk} · 1{NBSP}item"


def test_justificativa_do_estorno_e_um_campo_rotulado_dentro_do_form_sem_titulo_proprio(
    client, chefe_almoxarifado, entrada_de_dois_itens
):
    documento = _estorno(client, chefe_almoxarifado, entrada_de_dois_itens)

    (form,) = _principal(documento).buscar("form")
    # O rótulo do campo é o título do bloco: nenhum `<h2>` repetindo o mesmo nome.
    assert form.buscar("h2") == []
    campo = form.unico("textarea", name="justificativa")
    (rotulo,) = form.buscar("label", **{"for": campo.get("id")})
    assert rotulo.texto == "Justificativa do estorno"
    # Sem erro, a dica "Obrigatória." (e nenhum texto de erro).
    assert form.unico(classe="field-hint").texto == "Obrigatória."
    assert form.buscar(classe="field-error") == []


def test_estorno_avisa_da_irreversibilidade_antes_de_tudo_e_mostra_o_registro_para_conferir(
    client, chefe_almoxarifado, entrada_de_dois_itens
):
    documento = _estorno(client, chefe_almoxarifado, entrada_de_dois_itens)

    principal = _principal(documento)
    (aviso,) = principal.buscar(classe="alert-warning")
    assert "não pode ser desfeito" in aviso.texto
    assert "a quantidade recebida de cada item sai do saldo do material" in aviso.texto_corrido
    ordem = list(principal.descendentes())
    primeiro_card = principal.buscar("section", classe="card")[0]
    assert ordem.index(aviso) < ordem.index(primeiro_card)
    # O usuário decide sem abrir outra aba: NF e emitente já estão aqui.
    registro = primeiro_card
    assert registro.unico("h2").texto == "Registro"
    assert NUMERO_DOCUMENTO in registro.texto and "Papelaria Central" in registro.texto
    assert "007001" in [c.texto for c in registro.buscar(classe="table-cell-code")]  # em mono


def test_tabela_do_estorno_traz_saldo_atual_e_resultante_sem_linha_marcada_quando_tudo_cabe(
    client, chefe_almoxarifado, entrada_de_dois_itens
):
    documento = _estorno(client, chefe_almoxarifado, entrada_de_dois_itens)

    regiao = _principal(documento).unico(classe="table-wrapper")
    assert (regiao.get("role"), regiao.get("aria-label"), regiao.get("tabindex")) == (
        "region", "Tabela de itens a estornar", "0",
    )
    assert [th.texto for th in regiao.buscar("th")] == COLUNAS_ESTORNO
    linhas = regiao.unico("tbody").buscar("tr")
    # Saldos de agora (15 e 5,5) e o que sobraria depois (10 e 3).
    assert [[td.texto for td in tr.buscar("td")] for tr in linhas] == [
        [CADPRO_A, "Parafuso sextavado M8", "15", "5", "10", "UN"],
        [CADPRO_B, "Arruela lisa M8", "5,5", "2,5", "3", "UN"],
    ]
    assert regiao.buscar(classe="table-row-error") == []
    assert _principal(documento).buscar(classe="error-box") == []


@pytest.mark.parametrize(
    "justificativa", [None, "", "   \n  "], ids=["ausente", "vazia", "so-espacos"]
)
def test_justificativa_ausente_recusa_com_erro_ligado_ao_campo_e_nao_grava_nada(
    client, chefe_almoxarifado, entrada_de_dois_itens, material_a, material_b, justificativa
):
    """`INV-STOCK-004`: o estorno recusado deixa saldos e situação como estavam; o erro volta no
    campo, ligado a ele por `aria-invalid`/`aria-describedby` (o foco do leitor de tela)."""
    from estoque.models import Entrada, EstornoEntrada

    entrada = entrada_de_dois_itens
    client.force_login(chefe_almoxarifado)
    dados = {} if justificativa is None else {"justificativa": justificativa}

    resposta = client.post(reverse("estoque:entrada_estorno", args=[entrada.pk]), dados)

    assert resposta.status_code == 200
    documento = analisar(resposta.content)
    campo = documento.unico("textarea", name="justificativa")
    erro = documento.unico(classe="field-error")
    assert erro.get("id") == f"{campo.get('id')}_error"
    assert erro.texto == "Informe a justificativa do estorno."
    assert campo.get("aria-invalid") == "true"
    assert erro.get("id") in campo.get("aria-describedby", "").split()
    campo_wrapper = next(a for a in erro.ancestrais() if a.tem_classe("field"))
    assert campo_wrapper.tem_classe("field-has-error")
    # Erro OU dica, nunca as duas: com erro, "Obrigatória." sai (o erro já diz o que falta).
    assert documento.buscar(classe="field-hint") == []
    assert "Obrigatória." not in campo_wrapper.texto
    # A página segue completa e confirmável: o form, o destrutivo e "Cancelar".
    assert documento.unico("button", classe="btn-danger")
    # Nada gravado.
    assert Entrada.objects.get(pk=entrada.pk).estornada is False
    assert EstornoEntrada.objects.count() == 0
    material_a.refresh_from_db()
    material_b.refresh_from_db()
    assert (material_a.saldo, material_b.saldo) == (Decimal("15.000"), Decimal("5.500"))


def test_estorno_valido_pelo_form_grava_e_o_detalhe_diz_uma_vez_que_foi_estornada(
    client, chefe_almoxarifado, entrada_de_dois_itens, material_a, material_b
):
    """O fluxo real da tela: o form do estorno devolve os saldos e leva ao detalhe estornado."""
    entrada = entrada_de_dois_itens
    documento = _estorno(client, chefe_almoxarifado, entrada)
    (form,) = _principal(documento).buscar("form")

    resposta = client.post(form.get("action"), {"justificativa": "Nota duplicada."}, follow=True)

    assert resposta.redirect_chain[-1][0] == reverse("estoque:entrada_detalhe", args=[entrada.pk])
    detalhe = analisar(resposta.content)
    (aviso,) = detalhe.unico(classe="messages").buscar(classe="alert")
    assert aviso.tem_classe("alert-success") and aviso.texto == "Entrada estornada."
    assert detalhe.unico("h1").buscar(classe="badge")[0].texto == "Estornada"
    material_a.refresh_from_db()
    material_b.refresh_from_db()
    assert (material_a.saldo, material_b.saldo) == (Decimal("10.000"), Decimal("3.000"))


@pytest.fixture
def estorno_bloqueado(client, chefe_almoxarifado, entrada_de_dois_itens, material_b):
    """O saldo do B caiu para 1 depois da entrada de 2,5: estornar o deixaria em -1,5. O A cabe."""
    from catalogo.models import Material

    Material.objects.filter(pk=material_b.pk).update(saldo=Decimal("1.000"))
    return SimpleNamespace(
        entrada=entrada_de_dois_itens,
        documento=_estorno(client, chefe_almoxarifado, entrada_de_dois_itens),
    )


def test_estorno_bloqueado_marca_so_a_linha_que_ficaria_negativa_com_o_motivo_em_texto(
    estorno_bloqueado,
):
    documento = estorno_bloqueado.documento

    linhas = documento.unico("tbody").buscar("tr")
    cabe, bloqueada = linhas
    assert cabe.buscar("td")[0].texto == CADPRO_A and not cabe.tem_classe("table-row-error")
    assert bloqueada.buscar("td")[0].texto == CADPRO_B and bloqueada.tem_classe("table-row-error")
    # O motivo é texto, na célula do saldo resultante (a 5ª), só na linha bloqueada.
    assert "Ficaria negativo." in bloqueada.buscar("td")[4].texto
    assert "Ficaria negativo." not in cabe.texto
    assert documento.buscar(classe="table-row-error") == [bloqueada]
    assert bloqueada.buscar("td")[2].texto == "1"  # saldo atual (o de agora)


def test_estorno_bloqueado_nomeia_o_cadpro_que_ficaria_negativo_em_alerta_antes_dos_itens(
    estorno_bloqueado,
):
    documento = estorno_bloqueado.documento
    principal = _principal(documento)

    (alerta,) = principal.buscar(classe="error-box")
    assert alerta.get("role") == "alert"
    # Só o item bloqueado é nomeado (em mono), com a contagem "N dos M itens".
    assert [c.texto for c in alerta.buscar(classe="table-cell-code")] == [CADPRO_B]
    causa = alerta.buscar("p")[0]
    assert causa.texto_corrido == (
        "Não é possível estornar esta entrada: 1 dos 2 itens ficaria com saldo negativo "
        f"({CADPRO_B})."
    )
    assert "Nada foi estornado" not in alerta.texto  # nada foi tentado: é só o GET
    ordem = list(principal.descendentes())
    itens = next(
        c for c in principal.buscar("section", classe="card")
        if c.unico("h2").texto.startswith("Itens")
    )
    assert ordem.index(alerta) < ordem.index(itens)


def test_estorno_bloqueado_em_todos_os_itens_diz_que_todos_ficariam_negativos_e_os_nomeia(
    client, chefe_almoxarifado, estorno_bloqueado, material_a
):
    from catalogo.models import Material

    Material.objects.filter(pk=material_a.pk).update(saldo=Decimal("1.000"))

    documento = _estorno(client, chefe_almoxarifado, estorno_bloqueado.entrada)

    (alerta,) = _principal(documento).buscar(classe="error-box")
    assert alerta.buscar("p")[0].texto_corrido == (
        "Não é possível estornar esta entrada: os 2 itens ficariam com saldo negativo "
        f"({CADPRO_A}, {CADPRO_B})."
    )
    assert len(documento.buscar(classe="table-row-error")) == 2


def test_estorno_bloqueado_nao_oferece_a_acao_destrutiva_so_voltar(estorno_bloqueado):
    """A página bloqueada é de consulta: selo no título, o erro no lugar do aviso (antes do
    Registro), nenhuma barra de confirmação, e como única ação o link de volta ao detalhe."""
    documento = estorno_bloqueado.documento
    entrada = estorno_bloqueado.entrada
    principal = _principal(documento)

    assert principal.buscar("form") == []
    assert principal.buscar("button") == []
    assert principal.buscar(classe="btn-danger") == []
    assert principal.buscar(classe="btn-primary") == []
    # O aviso de irreversibilidade é da ação oferecida: sem ação, sem aviso.
    assert principal.buscar(classe="alert-warning") == []
    assert reverse("estoque:entrada_estorno", args=[entrada.pk]) not in {
        a.attrs["href"] for a in principal.buscar("a", href=True) if a.tem_classe("btn")
    }
    # Selo "Bloqueado" no título, com texto (não só cor): `badge-warning`, nunca o de erro.
    (selo,) = documento.unico("h1").buscar(classe="badge")
    assert selo.texto == "Bloqueado" and selo.tem_classe("badge-warning")
    # O erro ocupa a posição do aviso: antes do card Registro e dos Itens.
    ordem = list(principal.descendentes())
    alerta = principal.unico(classe="error-box")
    registro = principal.buscar("section", classe="card")[0]
    assert registro.unico("h2").texto == "Registro"
    assert ordem.index(alerta) < ordem.index(registro)
    # Sem operação a confirmar: nenhuma barra, só a fila de ações com o link de volta.
    assert principal.buscar(classe="confirmation-bar") == []
    assert principal.buscar(classe="confirmation-bar-card") == []
    acoes = principal.unico(classe="form-actions")
    (voltar,) = acoes.buscar("a")
    assert acoes.buscar("button") == []
    assert voltar.texto == f"Voltar à entrada #{entrada.pk}" and voltar.tem_classe("btn-secondary")
    assert voltar.get("href") == reverse("estoque:entrada_detalhe", args=[entrada.pk])
    assert acoes.pai is principal and principal.filhos[-1] is acoes


def test_get_de_estorno_bloqueado_nao_emite_mensagem_da_view(
    client, chefe_almoxarifado, estorno_bloqueado
):
    """No GET a causa é o `.error-box` da página; `messages` não repete o aviso nem a recusa."""
    resposta = client.get(reverse("estoque:entrada_estorno", args=[estorno_bloqueado.entrada.pk]))

    assert resposta.status_code == 200
    assert list(resposta.context["messages"]) == []
    documento = analisar(resposta.content)
    assert documento.buscar(classe="messages") == []
    assert [e.get("role") for e in documento.buscar(classe="error-box")] == ["alert"]
    assert resposta.content.decode().count("com saldo negativo") == 1


def test_post_de_estorno_bloqueado_nao_grava_e_nao_oferece_o_form(
    client, chefe_almoxarifado, estorno_bloqueado, material_a, material_b
):
    """`INV-STOCK-004`: mesmo postando direto, nada muda; e a página que volta é a mesma recusa."""
    from estoque.models import Entrada, EstornoEntrada

    entrada = estorno_bloqueado.entrada

    resposta = client.post(
        reverse("estoque:entrada_estorno", args=[entrada.pk]), {"justificativa": "Nota duplicada."}
    )

    assert resposta.status_code == 200
    documento = analisar(resposta.content)
    assert _principal(documento).buscar("form") == []
    assert documento.buscar(classe="table-row-error") != []
    # No POST o texto diz que a tentativa foi recusada e que nada mudou.
    causas = [
        p.texto_corrido for e in documento.buscar(classe="error-box") for p in e.buscar("p")
    ]
    assert (
        f"O estorno foi bloqueado: 1 dos 2 itens ficaria com saldo negativo ({CADPRO_B}). "
        "Nada foi estornado."
    ) in causas
    assert not any(c.startswith("Não é possível estornar") for c in causas)
    assert Entrada.objects.get(pk=entrada.pk).estornada is False
    assert EstornoEntrada.objects.count() == 0
    material_a.refresh_from_db()
    material_b.refresh_from_db()
    assert (material_a.saldo, material_b.saldo) == (Decimal("15.000"), Decimal("1.000"))


def test_recusa_por_saldo_no_post_aparece_uma_unica_vez_e_nomeia_o_cadpro(
    client, chefe_almoxarifado, estorno_bloqueado
):
    """A recusa é o `.error-box` da página, junto da causa: nem mensagem duplicada (`messages` +
    caixa) nem dois `role=alert` para o leitor de tela anunciar a mesma coisa duas vezes."""
    entrada = estorno_bloqueado.entrada

    resposta = client.post(
        reverse("estoque:entrada_estorno", args=[entrada.pk]), {"justificativa": "Nota duplicada."}
    )

    assert list(resposta.context["messages"]) == []
    documento = analisar(resposta.content)
    assert documento.buscar(classe="messages") == []
    (alerta,) = documento.buscar(role="alert")
    assert alerta.tem_classe("error-box")
    assert alerta.texto_corrido.count("O estorno foi bloqueado") == 1
    assert resposta.content.decode().count("O estorno foi bloqueado") == 1
    # O material que ficaria negativo é nomeado; o que cabe, não.
    assert [c.texto for c in alerta.buscar(classe="table-cell-code")] == [CADPRO_B]
    assert CADPRO_A not in alerta.texto


def test_recusa_por_saldo_com_saldos_ja_cobertos_na_renderizacao_nunca_e_silenciosa(
    client, chefe_almoxarifado, entrada_de_dois_itens, material_a, material_b, monkeypatch
):
    """Corrida: o saldo estava curto sob o lock do estorno e já cobre a quantidade quando a página
    é renderizada (`algum_bloqueado` falso). Sem a mensagem genérica a recusa sumiria: a página
    voltaria como se nada tivesse acontecido. Nada é gravado (`INV-STOCK-004`)."""
    from estoque import views
    from estoque.entradas import EstornoBloqueadoPorSaldo
    from estoque.models import Entrada, EstornoEntrada

    def recusa_sob_lock(*args, **kwargs):
        raise EstornoBloqueadoPorSaldo([])

    monkeypatch.setattr(views, "estornar_entrada", recusa_sob_lock)
    entrada = entrada_de_dois_itens
    client.force_login(chefe_almoxarifado)

    resposta = client.post(
        reverse("estoque:entrada_estorno", args=[entrada.pk]), {"justificativa": "Nota duplicada."}
    )

    assert resposta.status_code == 200
    documento = analisar(resposta.content)
    (container,) = documento.buscar(classe="messages")
    (mensagem,) = container.buscar(classe="error-box")
    assert mensagem.get("role") == "alert"
    assert mensagem.texto == "O estorno foi bloqueado: algum item ficaria com saldo negativo."
    assert resposta.content.decode().count("O estorno foi bloqueado") == 1
    # Os saldos cobrem: a página segue com o formulário (o usuário pode tentar de novo).
    assert documento.buscar(classe="table-row-error") == []
    assert documento.unico("button", classe="btn-danger")
    assert Entrada.objects.get(pk=entrada.pk).estornada is False
    assert EstornoEntrada.objects.count() == 0
    material_a.refresh_from_db()
    material_b.refresh_from_db()
    assert (material_a.saldo, material_b.saldo) == (Decimal("15.000"), Decimal("5.500"))


# ---------------------------------------------------------------------------
# 5. Composição: contrato HTMX, botão neutro, barra de revisar, erros.
# ---------------------------------------------------------------------------


def _formulario_de_composicao(raiz):
    (form,) = raiz.buscar("form", action=reverse("estoque:entrada_nova"))
    return form


def _contrato_do_formulario(raiz):
    """As garantias do formulário de composição que valem para a página e para o fragmento."""
    form = _formulario_de_composicao(raiz)
    nova = reverse("estoque:entrada_nova")
    assert form.get("method") == "post"
    assert form.get("hx-post") == nova
    assert (form.get("hx-target"), form.get("hx-swap"), form.get("hx-indicator")) == (
        "#entrada-composicao", "innerHTML", "#entrada-indicador",
    )
    assert form.buscar("input", type="hidden", name="csrfmiddlewaretoken")
    assert form.buscar("input", name="chave_confirmacao", type="hidden")
    # Enter em qualquer campo aciona o PRIMEIRO botão de envio: tem de ser o neutro e oculto.
    botoes = [b for b in form.buscar("button") if b.get("type") == "submit"]
    primeiro = botoes[0]
    assert (primeiro.get("name"), primeiro.get("value")) == ("acao", "manter_dados")
    assert primeiro.tem_classe("visually-hidden") and primeiro.get("tabindex") == "-1"
    assert primeiro.get("aria-hidden") == "true"
    # "Revisar" é o único primário e o ÚLTIMO controle do mesmo form, em `.form-actions`: ainda não
    # confirma nada, então não ganha a barra grudada (essa é só da revisão e do estorno).
    (revisar,) = [b for b in botoes if b.get("value") == "revisar"]
    assert revisar.get("name") == "acao" and revisar.texto == "Revisar"
    assert revisar.tem_classe("btn-primary")
    assert form.buscar(classe="btn-primary") == [revisar]
    acoes = revisar.pai
    assert acoes.tem_classe("form-actions") and acoes.tem_classe("estoque-acao-revisar")
    assert acoes.pai is form and form.filhos[-1] is acoes
    controles = [
        no for no in form.descendentes()
        if no.tag in {"button", "select", "textarea", "a", "summary"}
        or (no.tag == "input" and no.get("type") != "hidden")
    ]
    assert controles[-1] is revisar
    assert raiz.buscar(classe="confirmation-bar") == []
    assert raiz.buscar(classe="confirmation-bar-card") == []
    # As buscas e demais ações são botões `name=acao`/`name=<ação>` do MESMO form (um único POST).
    valores_de_acao = {b.get("value") for b in botoes if b.get("name") == "acao"}
    assert {"buscar_emitente", "buscar_material", "revisar", "manter_dados"} <= valores_de_acao
    return form


def test_pagina_de_composicao_tem_o_contrato_htmx_o_botao_neutro_e_revisar_no_fim_do_form(
    client, funcionario_almoxarifado
):
    client.force_login(funcionario_almoxarifado)

    documento = analisar(client.get(reverse("estoque:entrada_nova")).content)

    form = _contrato_do_formulario(documento)
    composicao = documento.unico(id="entrada-composicao")
    assert form.esta_dentro_de("div") and form in composicao.descendentes()
    # O indicador existe uma vez e fica FORA do alvo do swap (senão o swap o apagaria).
    indicador = documento.unico(id="entrada-indicador")
    assert indicador.get("role") == "status" and indicador.tem_classe("htmx-indicator")
    assert composicao not in indicador.ancestrais() and indicador not in composicao.descendentes()
    assert indicador.pai is _principal(documento) and composicao.pai is _principal(documento)
    # Ferramentas vazias: a única ação é "Revisar", no fim do formulário.
    ferramentas = _ferramentas(documento)
    assert ferramentas.buscar("a") == [] and ferramentas.buscar("button") == []


def test_pagina_de_composicao_carrega_htmx_sem_atraso_de_settle_e_o_script_da_tela(
    client, funcionario_almoxarifado
):
    """`defaultSettleDelay: 0` evita o `.value` do nó antigo em campos recriados por `innerHTML`."""
    client.force_login(funcionario_almoxarifado)

    documento = analisar(client.get(reverse("estoque:entrada_nova")).content)

    (config,) = documento.buscar("meta", name="htmx-config")
    assert json.loads(config.get("content")) == {"defaultSettleDelay": 0}
    scripts = [s.attrs["src"] for s in documento.buscar("script", src=True)]
    assert any(src.endswith("vendor/htmx/htmx-4.0.0.min.js") for src in scripts)
    assert any(src.endswith("estoque/js/estoque.js") for src in scripts)
    assert [s for s in documento.unico("head").buscar("script", src=True)
            if s.attrs["src"].endswith("htmx-4.0.0.min.js")], "o HTMX fica no <head>"


def test_cartao_do_emitente_diz_para_quais_motivos_ele_e_obrigatorio(
    client, funcionario_almoxarifado
):
    """A regra (`MOTIVOS_SEM_EMITENTE_OBRIGATORIO`) é do domínio; a dica não pode contradizê-la."""
    from estoque.models import MOTIVOS_SEM_EMITENTE_OBRIGATORIO, MotivoEntrada

    client.force_login(funcionario_almoxarifado)

    documento = analisar(client.get(reverse("estoque:entrada_nova")).content)

    dica = documento.unico("section", aria_labelledby="emitente-titulo").unico(
        classe="estoque-emitente-dica"
    )
    opcionais = {MotivoEntrada(m).label.lower() for m in MOTIVOS_SEM_EMITENTE_OBRIGATORIO}
    obrigatorios = {m.label.lower() for m in MotivoEntrada} - opcionais
    obrigatorio, _, opcional = dica.texto.partition(";")
    assert obrigatorio.startswith("Obrigatório para")
    assert opcional.strip().startswith("opcional para")
    assert all(rotulo in obrigatorio.lower() for rotulo in obrigatorios), dica.texto
    assert all(rotulo in opcional.lower() for rotulo in opcionais), dica.texto
    assert not any(rotulo in obrigatorio.lower() for rotulo in opcionais), dica.texto


def test_motivo_recebe_o_foco_inicial_so_na_abertura_da_composicao(
    client, funcionario_almoxarifado, material_a
):
    client.force_login(funcionario_almoxarifado)

    aberta = analisar(client.get(reverse("estoque:entrada_nova")).content)
    reenviada = analisar(_compor(client, [(material_a.pk, "1")], **_cabecalho()).content)

    assert "autofocus" in aberta.unico("select", name="motivo").attrs
    assert "autofocus" not in reenviada.unico("select", name="motivo").attrs


@pytest.mark.parametrize(
    "obter",
    [
        pytest.param(lambda c, m: c.get(reverse("estoque:entrada_nova"), **HX), id="get"),
        pytest.param(
            lambda c, m: _compor_htmx(c, [(m.pk, "2")], acao="buscar_material",
                                      busca_material="parafuso", **_cabecalho()),
            id="busca",
        ),
        pytest.param(
            lambda c, m: _compor_htmx(c, acao="revisar", **_cabecalho()), id="erro-geral"
        ),
    ],
)
def test_fragmento_htmx_do_formulario_mantem_o_mesmo_contrato_sem_o_shell(
    client, funcionario_almoxarifado, material_a, obter
):
    client.force_login(funcionario_almoxarifado)

    resposta = obter(client, material_a)

    assert resposta.status_code == 200
    documento = analisar(resposta.content)
    for tag in ("main", "aside", "html", "body", "script", "head", "nav", "h1"):
        assert documento.buscar(tag) == [], tag
    assert documento.buscar(id="entrada-indicador") == [] and documento.buscar(id="main") == []
    _contrato_do_formulario(documento)
    assert _classes_legadas(documento) == []
    assert "Vary" in resposta and "HX-Request" in resposta["Vary"]


def test_erro_geral_vira_error_box_com_role_alert_no_topo_do_fragmento_e_da_pagina(
    client, funcionario_almoxarifado
):
    """O `estoque.js` foca `.error-box[role="alert"]` quando não há campo inválido: o alerta é o
    primeiro elemento do alvo do swap e vem uma única vez."""
    client.force_login(funcionario_almoxarifado)

    fragmento = analisar(_compor_htmx(client, acao="revisar", **_cabecalho()).content)
    pagina = analisar(_compor(client, acao="revisar", **_cabecalho()).content)

    for raiz in (fragmento, pagina.unico(id="entrada-composicao")):
        (alerta,) = raiz.buscar(classe="error-box")
        assert alerta.get("role") == "alert"
        assert [li.texto for li in alerta.buscar("li")] == ["Inclua ao menos um material."]
        assert raiz.filhos[0] is alerta
        assert alerta.pai is raiz


def test_erros_de_campo_do_cabecalho_ficam_ligados_ao_campo_e_nao_viram_alerta_geral(
    client, funcionario_almoxarifado, material_a
):
    client.force_login(funcionario_almoxarifado)

    documento = analisar(_compor_htmx(client, [(material_a.pk, "1")], acao="revisar").content)

    assert documento.buscar(classe="error-box") == []
    for nome in ("motivo", "tipo_documento", "numero_documento"):
        campo = documento.unico(name=nome)
        erro = documento.unico(id=f"{campo.get('id')}_error")
        assert erro.tem_classe("field-error") and erro.texto
        assert campo.get("aria-invalid") == "true"
        assert next(a for a in erro.ancestrais() if a.tem_classe("field")).tem_classe(
            "field-has-error"
        )


def _confere_bloco_de_erro_da_linha(linha, erro, cadpro):
    """O erro da linha vem num bloco próprio que diz de qual material é (só visual: o campo já é
    descrito pelo erro via `aria-describedby`), com o rótulo ANTES do texto do erro."""
    (bloco,) = linha.buscar(classe="estoque-erro-linha")
    assert erro.pai is bloco
    (material,) = bloco.buscar(classe="estoque-erro-linha-material")
    assert material.get("aria-hidden") == "true"
    assert material.texto_corrido == f"Material {cadpro}"
    assert material.unico(classe="table-cell-code").texto == cadpro
    ordem = list(bloco.descendentes())
    assert ordem.index(material) < ordem.index(erro)
    assert "aria-hidden" not in erro.attrs and not any(
        a.get("aria-hidden") == "true" for a in erro.ancestrais() if a.tag != "[documento]"
    )


def test_erro_de_linha_marca_so_a_linha_com_erro_e_deixa_as_outras(
    client, funcionario_almoxarifado, material_a, material_b
):
    """O mesmo material duas vezes: a segunda linha é a que recebe o erro e o `table-row-error`."""
    client.force_login(funcionario_almoxarifado)
    itens = [(material_a.pk, "1"), (material_b.pk, "1"), (material_a.pk, "1")]

    documento = analisar(
        _compor_htmx(client, itens, acao="revisar", **_cabecalho()).content
    )

    tabela = documento.unico("table", classe="estoque-tabela-controles")
    linhas = tabela.unico("tbody").buscar("tr")
    assert [ln.tem_classe("table-row-error") for ln in linhas] == [False, False, True]
    assert documento.buscar(classe="table-row-error") == [linhas[2]]
    (erro,) = linhas[2].buscar(classe="field-error")
    assert erro.texto
    assert linhas[0].buscar(classe="field-error") == [] == linhas[1].buscar(classe="field-error")
    assert linhas[0].buscar(classe="estoque-erro-linha") == []
    _confere_bloco_de_erro_da_linha(linhas[2], erro, CADPRO_A)


def test_erro_de_formato_da_quantidade_liga_o_erro_ao_campo_sem_marcar_a_linha_inteira(
    client, funcionario_almoxarifado, material_a
):
    client.force_login(funcionario_almoxarifado)

    documento = analisar(
        _compor_htmx(client, [(material_a.pk, "abc")], acao="revisar", **_cabecalho()).content
    )

    campo = documento.unico("input", name="itens-0-quantidade")
    erro = documento.unico(id="id_itens-0-quantidade_error")
    assert erro.tem_classe("field-error") and erro.texto
    assert campo.get("aria-invalid") == "true"
    assert erro.get("id") in campo.get("aria-describedby", "").split()
    assert campo.get("inputmode") == "decimal"
    assert documento.buscar(classe="table-row-error") == []  # é erro do campo, não da linha
    _confere_bloco_de_erro_da_linha(campo.pai.pai, erro, CADPRO_A)


def test_busca_de_material_oferece_adicionar_e_marca_o_ja_incluido_sem_botao(
    client, funcionario_almoxarifado, material_a, material_b
):
    client.force_login(funcionario_almoxarifado)

    documento = analisar(
        _compor_htmx(
            client, [(material_a.pk, "1")], acao="buscar_material", busca_material="M8"
        ).content
    )

    regiao = documento.unico("div", aria_label="Tabela de resultados da busca de material")
    assert (regiao.get("role"), regiao.get("tabindex")) == ("region", "0")
    linhas = regiao.unico("tbody").buscar("tr")
    assert [[td.texto for td in tr.buscar("td")][1] for tr in linhas] == [CADPRO_A, CADPRO_B]
    ja_incluido, disponivel = linhas
    assert ja_incluido.buscar("button") == []
    assert ja_incluido.unico(classe="badge").texto == "Já incluído"
    (adicionar,) = disponivel.buscar("button")
    assert (adicionar.get("name"), adicionar.get("value")) == (
        "adicionar_material", str(material_b.pk),
    )
    assert adicionar.get("aria-label") == f"Adicionar {CADPRO_B}"
    assert adicionar.get("type") == "submit" and adicionar.esta_dentro_de("form")


def test_material_adicionado_entra_como_linha_com_cadpro_exato_e_foco_na_quantidade(
    client, funcionario_almoxarifado, material_a
):
    client.force_login(funcionario_almoxarifado)

    documento = analisar(
        _compor_htmx(client, acao="adicionar_material", adicionar_material=str(material_a.pk),
                     **_cabecalho()).content
    )

    tabela = documento.unico("table", classe="estoque-tabela-controles")
    # A Ação (Remover) é a PRIMEIRA coluna: visível sem rolar a tabela na horizontal.
    assert [th.texto for th in tabela.buscar("th")] == [
        "Ação", "Código", "Descrição", "Quantidade recebida", "Unidade",
    ]
    (linha,) = tabela.unico("tbody").buscar("tr")
    assert [b.get("name") for b in linha.buscar("td")[0].buscar("button")] == ["remover_item"]
    assert linha.unico(classe="table-cell-code").texto == CADPRO_A
    quantidade = linha.unico("input", name="itens-0-quantidade")
    assert "autofocus" in quantidade.attrs
    assert quantidade.get("aria-label") == f"Quantidade recebida de {CADPRO_A}"
    assert linha.unico("input", name="itens-0-material").get("value") == str(material_a.pk)
    (remover,) = linha.buscar("button")
    assert (remover.get("name"), remover.get("value")) == ("remover_item", "0")
    assert remover.get("aria-label") == f"Remover {CADPRO_A}"
    # A busca foi limpa e a lista de resultados não aparece mais.
    assert documento.buscar("div", aria_label="Tabela de resultados da busca de material") == []


def test_composicao_sem_materiais_mostra_o_estado_vazio_dentro_da_tabela(
    client, funcionario_almoxarifado
):
    client.force_login(funcionario_almoxarifado)

    documento = analisar(client.get(reverse("estoque:entrada_nova")).content)

    (vazio,) = documento.buscar("tr", classe="table-empty-row")
    assert vazio.get("data-estado") == "vazio"
    assert "Nenhum material incluído." in vazio.texto


# ---------------------------------------------------------------------------
# 6. Emitente: bloqueado nunca é escolhível (`INV-SUPPLIER-005`).
# ---------------------------------------------------------------------------


@pytest.fixture
def emitentes(criar_fornecedor):
    return SimpleNamespace(
        livre=criar_fornecedor("007001", "Papelaria Central", documento="12.345.678/0001-95"),
        bloqueado=criar_fornecedor("007002", "Papelaria Bloqueada", bloqueado=True),
    )


def _buscar_emitente(client, **campos):
    resposta = _compor_htmx(
        client, acao="buscar_emitente", busca_emitente="papelaria", **_cabecalho(), **campos
    )
    return analisar(resposta.content)


def test_busca_de_emitente_so_oferece_escolher_para_o_liberado(
    client, funcionario_almoxarifado, emitentes
):
    client.force_login(funcionario_almoxarifado)

    documento = _buscar_emitente(client)

    regiao = documento.unico("div", aria_label="Tabela de resultados da busca de emitente")
    assert (regiao.get("role"), regiao.get("tabindex")) == ("region", "0")
    linhas = {
        tr.unico(classe="table-cell-code").texto: tr for tr in regiao.unico("tbody").buscar("tr")
    }
    assert set(linhas) == {"007001", "007002"}  # CODIF com zeros à esquerda, como guardado
    # Liberado: botão de escolher, no mesmo form, com o pk do fornecedor.
    (escolher,) = linhas["007001"].buscar("button")
    assert (escolher.get("name"), escolher.get("value")) == (
        "escolher_emitente", str(emitentes.livre.pk),
    )
    assert escolher.get("aria-label") == "Escolher Papelaria Central"
    assert "Liberado" in linhas["007001"].buscar("td")[-1].texto
    # Bloqueado: nenhum botão, em lugar nenhum da página, para ele; no lugar, um ÚNICO selo
    # "Bloqueado" na coluna Ação (forma e texto) e o motivo em texto na Situação.
    bloqueada = linhas["007002"]
    assert bloqueada.buscar("button") == [] and bloqueada.buscar("a") == []
    celulas = bloqueada.buscar("td")
    assert [b.texto for b in bloqueada.buscar(classe="badge")] == ["Bloqueado"]
    assert celulas[0].unico(classe="badge-warning").texto == "Bloqueado"
    assert celulas[-1].unico(classe="estoque-motivo-bloqueio").texto == (
        "Bloqueado no SCPI (fixture de teste)."
    )
    assert "Indisponível" not in documento.texto
    assert linhas["007001"].buscar(classe="badge") == []
    escolhiveis = documento.buscar("button", name="escolher_emitente")
    assert [b.get("value") for b in escolhiveis] == [str(emitentes.livre.pk)]


def test_escolher_emitente_bloqueado_postando_direto_nao_o_seleciona(
    client, funcionario_almoxarifado, emitentes
):
    client.force_login(funcionario_almoxarifado)

    documento = analisar(
        _compor_htmx(client, acao="escolher", escolher_emitente=str(emitentes.bloqueado.pk),
                     **_cabecalho()).content
    )

    assert documento.unico("input", name="emitente").get("value", "") == ""
    assert "Nenhum emitente escolhido." in documento.unico(classe="estoque-sem-emitente").texto
    assert documento.buscar(classe="estoque-emitente-escolhido") == []
    assert documento.buscar("button", value="limpar_emitente") == []  # nada a remover


def test_emitente_escolhido_aparece_com_codigo_em_mono_e_a_busca_recolhida(
    client, funcionario_almoxarifado, emitentes
):
    client.force_login(funcionario_almoxarifado)

    documento = analisar(
        _compor_htmx(client, acao="escolher", escolher_emitente=str(emitentes.livre.pk),
                     **_cabecalho(motivo="COMPRA")).content
    )

    assert documento.unico("input", name="emitente").get("value") == str(emitentes.livre.pk)
    escolhido = documento.unico(classe="estoque-emitente-escolhido")
    # Mesma identidade da revisão e do Registro: nome · código · documento, como guardados.
    _confere_identidade(escolhido, "Papelaria Central", "007001", "12.345.678/0001-95")
    assert escolhido.buscar("button") == []
    # "Trocar emitente" (a busca recolhida num `<details>` nativo, fechado sem busca feita) e
    # "Remover emitente" ficam juntos, num mesmo bloco de ações.
    acoes = documento.unico(classe="estoque-emitente-acoes")
    detalhes = acoes.unico("details", classe="estoque-busca-recolhida")
    assert detalhes.unico("summary").texto == "Trocar emitente"
    assert "open" not in detalhes.attrs
    buscar = detalhes.unico("button", name="acao", value="buscar_emitente")
    # "Remover emitente" existe duas vezes (o CSS mostra uma só): fechado, o de fora, ao lado de
    # "Trocar emitente"; aberto, o de dentro, junto de "Buscar emitente". Os dois são o MESMO envio
    # (`acao=limpar_emitente`, no mesmo form de composição): nenhum fica sem efeito.
    removers = documento.buscar("button", name="acao", value="limpar_emitente")
    assert [b.texto for b in removers] == ["Remover emitente"] * 2
    form = _formulario_de_composicao(documento)
    assert all(b in form.descendentes() for b in removers)
    (dentro,) = [b for b in removers if b in detalhes.descendentes()]
    (fora,) = [b for b in removers if b not in detalhes.descendentes()]
    assert dentro.pai is buscar.pai and dentro.get("type") == "submit"
    assert fora.pai is acoes and fora.tem_classe("estoque-remover-fechado")
    assert fora.get("type") == "submit"
    assert acoes.buscar("button") == [buscar, dentro, fora]


def test_busca_com_emitente_ja_escolhido_abre_a_busca_para_o_resultado_nao_sumir(
    client, funcionario_almoxarifado, emitentes
):
    client.force_login(funcionario_almoxarifado)

    documento = _buscar_emitente(client, emitente=str(emitentes.livre.pk))

    detalhes = documento.unico("details", classe="estoque-busca-recolhida")
    assert "open" in detalhes.attrs
    assert detalhes.buscar("button", name="escolher_emitente") != []


# ---------------------------------------------------------------------------
# 7. Revisão: a prévia antes de gravar e o par confirmar/voltar.
# ---------------------------------------------------------------------------


@pytest.fixture(params=["htmx", "pagina"])
def revisao(request, client, funcionario_almoxarifado, material_a, material_b, emitentes):
    """A revisão de uma compra de 2 itens (5 do A, 2,5 do B), como fragmento HTMX e como página
    inteira (o POST sem HTMX que o navegador faz sem JS)."""
    from estoque.models import Entrada

    client.force_login(funcionario_almoxarifado)
    dados = _payload(
        [(material_a.pk, "5"), (material_b.pk, "2,5")],
        acao="revisar",
        **_cabecalho(motivo="COMPRA", emitente=str(emitentes.livre.pk)),
    )
    extras = HX if request.param == "htmx" else {}
    resposta = client.post(reverse("estoque:entrada_nova"), dados, **extras)
    assert resposta.status_code == 200
    documento = analisar(resposta.content)
    assert Entrada.objects.count() == 0, "revisar nunca grava"
    raiz = documento if request.param == "htmx" else documento.unico(id="entrada-composicao")
    return SimpleNamespace(
        client=client, documento=documento, raiz=raiz, dados=dados, como=request.param,
        emitente=emitentes.livre,
    )


def _barra_de_revisao(revisao):
    return revisao.raiz.unico(classe="confirmation-bar-card")


def test_revisao_se_declara_nao_gravada_e_diz_que_nada_foi_gravado(revisao):
    raiz = revisao.raiz

    titulo = raiz.unico("h2", id="resumo-heading")
    assert titulo.get("tabindex") == "-1"  # alvo do foco do `estoque.js` depois do swap
    assert titulo.texto == "Revisão da entrada Não gravada"
    (selo,) = titulo.buscar(classe="badge")
    assert selo.texto == "Não gravada" and selo.tem_classe("badge-info")
    (aviso,) = raiz.buscar(classe="alert-info")
    assert aviso.get("role") == "status"
    assert "Nada foi gravado ainda" in aviso.texto
    ordem = list(raiz.descendentes())
    assert ordem.index(titulo) < ordem.index(aviso) < ordem.index(_barra_de_revisao(revisao))
    # O formulário de composição não convive com a revisão no mesmo alvo.
    assert raiz.buscar("form", action=reverse("estoque:entrada_nova"), hx_post=True) == []


def test_revisao_em_pagina_inteira_tem_um_main_e_em_fragmento_nao_tem_shell(revisao):
    documento = revisao.documento

    assert _classes_legadas(documento) == []
    if revisao.como == "pagina":
        assert len(documento.buscar("main")) == 1
        assert documento.unico("h1").texto == "Registrar entrada de materiais"
    else:
        for tag in ("main", "aside", "html", "script", "h1"):
            assert documento.buscar(tag) == [], tag


def test_revisao_mostra_a_referencia_o_emitente_e_os_itens_com_saldo_atual_e_resultante(revisao):
    raiz = revisao.raiz

    referencia = raiz.unico("section", aria_labelledby="referencia-titulo")
    dados = _pares(referencia)
    assert dados["Motivo"].texto == "Compra"
    assert dados["Tipo de documento"].texto == "Nota fiscal"
    assert dados["Número do documento"].texto == NUMERO_DOCUMENTO
    _confere_identidade(dados["Emitente"], "Papelaria Central", "007001", "12.345.678/0001-95")
    itens = raiz.unico("section", aria_labelledby="itens-resumo-titulo")
    assert itens.unico("h2").texto == "Itens (2)"
    regiao = itens.unico(classe="table-wrapper")
    assert (regiao.get("role"), regiao.get("aria-label"), regiao.get("tabindex")) == (
        "region", "Tabela de itens da entrada", "0",
    )
    assert [th.texto for th in regiao.buscar("th")] == COLUNAS_REVISAO
    linhas = [[td.texto for td in tr.buscar("td")] for tr in regiao.unico("tbody").buscar("tr")]
    # Código (como guardado), descrição, saldo atual, quantidade, saldo resultante, unidade.
    assert linhas == [
        [CADPRO_A, "Parafuso sextavado M8", "10", "5", "15", "UN"],
        [CADPRO_B, "Arruela lisa M8", "3", "2,5", "5,5", "UN"],
    ]
    assert [c.texto for c in regiao.buscar("td", classe="table-cell-code")] == [CADPRO_A, CADPRO_B]


def test_barra_da_revisao_tem_confirmar_antes_de_voltar_e_corrigir(revisao):
    barra = _barra_de_revisao(revisao)

    formularios = barra.buscar("form")
    assert [f.get("action") for f in formularios] == [
        reverse("estoque:entrada_confirmar"),
        reverse("estoque:entrada_nova"),
    ]
    confirmar, voltar = formularios
    # Confirmar: o único primário, com o nome acessível recitando a consequência.
    (botao,) = confirmar.buscar("button", type="submit")
    assert botao.tem_classe("btn-primary") and "data-processing-submit" in botao.attrs
    assert botao.texto_corrido == "Confirmar entrada: 2 itens"
    assert botao.unico("span").get("data-processing-submit-label") == ""
    assert botao.unico("small", classe="confirmation-bar-totais").texto_corrido == ": 2 itens"
    assert "aria-label" not in botao.attrs
    assert "data-processing-form" in confirmar.attrs
    assert confirmar.get("data-processing-label") == "Confirmando…"
    assert confirmar.get("method") == "post" and "hx-post" not in confirmar.attrs
    # Voltar e corrigir: secundário, depois; não passa pelo estado "Confirmando…".
    (botao_voltar,) = voltar.buscar("button", type="submit")
    assert botao_voltar.tem_classe("btn-secondary") and botao_voltar.texto == "Voltar e corrigir"
    assert "data-processing-form" not in voltar.attrs and "hx-post" not in voltar.attrs
    assert voltar.unico("input", type="hidden", name="acao").get("value") == "voltar"
    assert revisao.raiz.buscar(classe="btn-primary") == [botao]
    for form in formularios:
        assert form.unico("input", type="hidden", name="csrfmiddlewaretoken").get("value")


def test_resumo_curto_da_barra_fica_fora_da_arvore_de_acessibilidade(revisao):
    barra = _barra_de_revisao(revisao)

    resumo = barra.unico(classe="confirmation-bar-resumo")
    assert resumo.get("aria-hidden") == "true" and barra.filhos[0] is resumo
    assert resumo.texto_cru.strip() == f"{NUMERO_DOCUMENTO} · 2{NBSP}itens"
    assert resumo.buscar("a") == [] and resumo.buscar("button") == []


def test_os_dois_formularios_da_revisao_levam_o_estado_completo_da_entrada(revisao):
    """Sem estado no servidor, a confirmação só sabe o que os hidden inputs dizem: cabeçalho,
    emitente e CADA item (`INV-ENT-001`)."""
    confirmar, voltar = _barra_de_revisao(revisao).buscar("form")

    chave = revisao.dados["chave_confirmacao"]
    esperado = {
        "chave_confirmacao": chave,
        "motivo": "COMPRA",
        "tipo_documento": "NOTA_FISCAL",
        "numero_documento": NUMERO_DOCUMENTO,
        "emitente": str(revisao.emitente.pk),
        "itens-TOTAL_FORMS": "2",
        "itens-INITIAL_FORMS": "0",
        "itens-MIN_NUM_FORMS": "0",
        "itens-MAX_NUM_FORMS": "1000",
        "itens-0-material": revisao.dados["itens-0-material"],
        "itens-0-quantidade": "5",
        "itens-1-material": revisao.dados["itens-1-material"],
        "itens-1-quantidade": "2,5",
    }
    assert _hidden(confirmar) == esperado
    assert _hidden(voltar) == {**esperado, "acao": "voltar"}


def test_confirmar_pelos_hidden_da_revisao_grava_a_entrada_inteira_e_o_detalhe_diz_uma_vez(
    revisao, material_a, material_b
):
    """O aller-retour real: o que o navegador reenviaria do form de confirmar reconstrói a entrada
    (`INV-ENT-001`), o saldo sobe pela quantidade (`INV-STOCK-001`) e o sucesso aparece uma vez."""
    from estoque.models import Entrada

    confirmar, _ = _barra_de_revisao(revisao).buscar("form")

    resposta = revisao.client.post(confirmar.get("action"), _hidden(confirmar), follow=True)

    (entrada,) = Entrada.objects.all()
    assert resposta.redirect_chain[-1][0] == reverse("estoque:entrada_detalhe", args=[entrada.pk])
    assert [(i.material_id, i.quantidade) for i in entrada.itens.order_by("pk")] == [
        (material_a.pk, Decimal("5.000")), (material_b.pk, Decimal("2.500")),
    ]
    assert entrada.emitente_id == revisao.emitente.pk
    assert entrada.numero_documento == NUMERO_DOCUMENTO
    material_a.refresh_from_db()
    material_b.refresh_from_db()
    assert (material_a.saldo, material_b.saldo) == (Decimal("15.000"), Decimal("5.500"))
    detalhe = analisar(resposta.content)
    (aviso,) = detalhe.unico(classe="messages").buscar(classe="alert")
    assert aviso.tem_classe("alert-success") and aviso.texto == "Entrada registrada: 2 itens."
    assert resposta.content.decode().count("Entrada registrada") == 1


def test_voltar_e_corrigir_devolve_o_formulario_com_tudo_preenchido_sem_gravar(revisao):
    from estoque.models import Entrada

    _, voltar = _barra_de_revisao(revisao).buscar("form")

    resposta = revisao.client.post(voltar.get("action"), _hidden(voltar), **HX)

    assert Entrada.objects.count() == 0
    documento = analisar(resposta.content)
    form = _contrato_do_formulario(documento)
    assert documento.unico("input", name="numero_documento").get("value") == NUMERO_DOCUMENTO
    assert documento.unico("select", name="motivo").unico(
        "option", selected=True
    ).get("value") == "COMPRA"
    assert [
        documento.unico("input", name=f"itens-{i}-quantidade").get("value") for i in range(2)
    ] == ["5", "2,5"]
    assert form.unico("input", name="emitente").get("value") == str(revisao.emitente.pk)


def test_revisao_sem_emitente_diz_sem_emitente_e_leva_o_campo_vazio(
    client, funcionario_almoxarifado, material_a
):
    client.force_login(funcionario_almoxarifado)

    documento = analisar(
        _compor_htmx(client, [(material_a.pk, "1")], acao="revisar", **_cabecalho()).content
    )

    referencia = documento.unico("section", aria_labelledby="referencia-titulo")
    (emitente,) = [
        dd for dt, dd in zip(referencia.buscar("dt"), referencia.buscar("dd"), strict=True)
        if dt.texto == "Emitente"
    ]
    assert emitente.texto == "Sem emitente"
    confirmar = documento.unico("form", action=reverse("estoque:entrada_confirmar"))
    assert _hidden(confirmar)["emitente"] == ""
    botao = confirmar.unico("button", classe="btn-primary")
    assert botao.texto_corrido == "Confirmar entrada: 1 item"
    resumo = documento.unico(classe="confirmation-bar-resumo")
    assert resumo.texto_cru.strip() == f"{NUMERO_DOCUMENTO} · 1{NBSP}item"


# ---------------------------------------------------------------------------
# 8. CADPRO como guardado em todas as telas que o mostram (`INV-CATALOG-001`).
# ---------------------------------------------------------------------------


def test_cadpro_aparece_sem_transformacao_em_celula_propria_em_toda_tela_de_estoque(
    client, chefe_almoxarifado, material_a
):
    entrada = _registrar(chefe_almoxarifado, [(material_a, "5")])
    client.force_login(chefe_almoxarifado)
    respostas = {
        "busca de material": _compor_htmx(
            client, acao="buscar_material", busca_material=CADPRO_A, **_cabecalho()
        ),
        "composição": _compor_htmx(
            client, acao="adicionar_material", adicionar_material=str(material_a.pk), **_cabecalho()
        ),
        "revisão": _compor_htmx(client, [(material_a.pk, "1")], acao="revisar", **_cabecalho()),
        "detalhe": client.get(reverse("estoque:entrada_detalhe", args=[entrada.pk])),
        "estorno": client.get(reverse("estoque:entrada_estorno", args=[entrada.pk])),
    }

    for tela, resposta in respostas.items():
        assert resposta.status_code == 200, tela
        celulas = analisar(resposta.content).buscar("td", classe="table-cell-code")
        assert CADPRO_A in [c.texto for c in celulas], tela


# ---------------------------------------------------------------------------
# 9. Consulta de entradas.
# ---------------------------------------------------------------------------


def test_linha_da_lista_leva_ao_detalhe_por_link_real_e_traz_o_emitente_como_secundario(
    client, funcionario_almoxarifado, material_a, material_b, criar_fornecedor
):
    emitente = criar_fornecedor("007001", "Papelaria Central")
    com = _registrar(
        funcionario_almoxarifado, [(material_a, "1"), (material_b, "1")], motivo="COMPRA",
        numero_documento="D-100", emitente_id=emitente.pk,
    )
    sem = _registrar(funcionario_almoxarifado, [(material_a, "1")], numero_documento="D-101")
    client.force_login(funcionario_almoxarifado)

    documento = analisar(client.get(reverse("estoque:entradas")).content)

    regiao = _principal(documento).unico(classe="table-wrapper")
    assert (regiao.get("role"), regiao.get("aria-label"), regiao.get("tabindex")) == (
        "region", "Entradas registradas", "0",
    )
    assert [th.texto for th in regiao.buscar("th")] == [
        "Entrada", "Situação", "Referência", "Registrada em", "Motivo", "Autor", "Itens",
    ]
    linhas = regiao.unico("tbody").buscar("tr")
    assert len(linhas) == 2
    assert all("data-linha-clicavel" in tr.attrs for tr in linhas)
    # Da mais recente para a mais antiga.
    assert [tr.unico("a").get("href") for tr in linhas] == [
        reverse("estoque:entrada_detalhe", args=[sem.pk]),
        reverse("estoque:entrada_detalhe", args=[com.pk]),
    ]
    for tr, entrada in zip(linhas, (sem, com), strict=True):
        (link,) = tr.buscar("a")
        assert link.tem_classe("table-row-link") and "data-linha-link" in link.attrs
        assert link.texto_corrido == f"Entrada #{entrada.pk}"  # nome acessível contextualizado
        assert link.unico("span").tem_classe("visually-hidden")
        assert tr.unico("td", classe="table-cell-code").texto == (
            entrada.registrada_por.matricula
        )
    cel_sem, cel_com = (tr.unico("td", classe="estoque-referencia-cell") for tr in linhas)
    assert cel_com.unico(classe="cell-secondary").texto == "Papelaria Central"
    assert cel_sem.unico(classe="cell-secondary").texto == "Sem emitente"
    assert cel_com.texto.startswith("Nota fiscal D-100")
    # O número do documento é um bloco próprio (não quebra linha), com o valor como guardado.
    assert [c.unico(classe="estoque-numero-documento").texto for c in (cel_sem, cel_com)] == [
        "D-101", "D-100",
    ]
    assert [tr.buscar("td")[-1].texto for tr in linhas] == ["1", "2"]  # itens


def test_lista_distingue_registrada_de_estornada_por_selo_com_texto(
    client, chefe_almoxarifado, material_a
):
    from estoque.entradas import estornar_entrada

    registrada = _registrar(chefe_almoxarifado, [(material_a, "1")])
    estornada = _registrar(chefe_almoxarifado, [(material_a, "1")])
    estornar_entrada(estornada.pk, "Digitação errada.", chefe_almoxarifado)
    client.force_login(chefe_almoxarifado)

    documento = analisar(client.get(reverse("estoque:entradas")).content)

    selos = {
        tr.unico("a").texto_corrido: tr.unico(classe="badge")
        for tr in documento.unico("tbody").buscar("tr")
    }
    ok = selos[f"Entrada #{registrada.pk}"]
    assert ok.texto == "Registrada" and ok.tem_classe("badge-success")
    estorno = selos[f"Entrada #{estornada.pk}"]
    assert estorno.texto == "Estornada" and estorno.tem_classe("badge-neutral")
    assert not estorno.tem_classe("badge-danger") and not ok.tem_classe("badge-neutral")


def test_lista_em_ferramentas_oferece_registrar_como_secundario_e_pagina_no_mesmo_card(
    client, funcionario_almoxarifado, material_a
):
    _registrar(funcionario_almoxarifado, [(material_a, "1")])
    client.force_login(funcionario_almoxarifado)

    documento = analisar(client.get(reverse("estoque:entradas")).content)

    (acao,) = _ferramentas(documento).buscar("a")
    assert acao.tem_classe("btn-secondary") and not acao.tem_classe("btn-primary")
    card = _principal(documento).unico(classe="card")
    assert card.unico("nav", aria_label="Paginação de entradas")
    assert card.unico(classe="table-wrapper")
    scripts = [s.attrs["src"] for s in documento.buscar("script", src=True)]
    assert any(src.endswith("js/linha-clicavel.js") for src in scripts)


def test_auditor_ve_a_lista_inteira_sem_nenhuma_acao(
    client, auditor, funcionario_almoxarifado, material_a
):
    entrada = _registrar(funcionario_almoxarifado, [(material_a, "1")])
    client.force_login(auditor)

    documento = analisar(client.get(reverse("estoque:entradas")).content)

    ferramentas = _ferramentas(documento)
    assert ferramentas.buscar("a") == [] and ferramentas.buscar("button") == []
    assert _principal(documento).buscar("form") == []
    assert _principal(documento).buscar("button") == []
    destinos = hrefs_de(_principal(documento))
    assert destinos == {reverse("estoque:entrada_detalhe", args=[entrada.pk])}


def test_lista_vazia_usa_o_estado_vazio_dentro_do_card_sem_tabela(client, funcionario_almoxarifado):
    client.force_login(funcionario_almoxarifado)

    documento = analisar(client.get(reverse("estoque:entradas")).content)

    card = _principal(documento).unico(classe="card")
    vazio = card.unico(classe="empty")
    assert vazio.get("data-estado") == "vazio"
    assert vazio.unico(classe="empty-state-title").texto == "Nenhuma entrada registrada."
    assert card.buscar("table") == []


# ---------------------------------------------------------------------------
# 10. `estoque.js`: o evento do HTMX 4 e o alvo do foco.
# ---------------------------------------------------------------------------


def _fonte_do_script():
    return (RAIZ / "estoque/static/estoque/js/estoque.js").read_text(encoding="utf-8")


def test_script_ouve_o_evento_de_settle_do_htmx_4_e_nao_o_do_2x():
    """No HTMX 4 o evento é `htmx:after:settle`; `htmx:afterSettle` (2.x) nunca dispara, e a rotina
    de foco da composição simplesmente nunca rodaria — sem erro algum no console."""
    fonte = _fonte_do_script()

    assert re.search(r'addEventListener\(\s*"htmx:after:settle"', fonte)
    assert not re.search(r'addEventListener\(\s*"htmx:afterSettle"', fonte)
    htmx = (RAIZ / "static/vendor/htmx/htmx-4.0.0.min.js").read_text(encoding="utf-8")
    assert "after:settle" in htmx, "o HTMX vendorizado não emite o evento que o script ouve"


def test_script_foca_o_alerta_geral_com_o_mesmo_seletor_que_o_template_renderiza():
    fonte = _fonte_do_script()

    assert '.error-box[role="alert"]' in fonte
    assert "#resumo-heading" in fonte  # o título da revisão que o template marca com tabindex=-1
    # o alvo do swap que o código lê (não o comentário), o mesmo `id` que o template renderiza
    assert re.search(r'getElementById\(\s*"entrada-composicao"\s*\)', fonte)
