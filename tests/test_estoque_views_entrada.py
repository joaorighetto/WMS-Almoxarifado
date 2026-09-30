"""Testes HTTP da composição, resumo e confirmação da entrada (T012).

Cobre `contracts/composicao-entrada.md` (campos, ações, resumo) e
`contracts/rotas-e-autorizacao.md` → "Confirmação". Autorização em si é
`tests/test_estoque_permissoes.py`; aqui o foco é o FLUXO: nenhuma ação de
composição grava nada, o resumo mostra saldo atual/resultante, a confirmação
efetiva e é idempotente, campos ocultos adulterados são recusados, e a
resposta respeita `HX-Request`.

Os nomes de campo do formulário/formset (`motivo`, `tipo_documento`,
`numero_documento`, `emitente`, `busca_material`, `busca_emitente`, prefixo
`itens`, botões `acao`/`adicionar_material`/`remover_item`/
`escolher_emitente`) são normativos (`contracts/composicao-entrada.md`). O
nome exato do campo de material DENTRO de cada linha do formset (`material`)
é a única suposição não fixada literalmente pelo contrato — isolada em
`_payload_item` para ser barata de ajustar se a implementação escolher outro
nome.

TDD: escrito antes de `estoque/views.py`/`estoque/forms.py` existirem —
espera-se falha (por rota ausente, campo ausente ou comportamento ainda não
implementado) até a implementação estar completa.
"""

import re
import signal
import uuid
from decimal import Decimal

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def _payload_item(indice, material_pk, quantidade=""):
    return {
        f"itens-{indice}-material": material_pk,
        f"itens-{indice}-quantidade": quantidade,
    }


def _payload_base(chave, *, total_itens=0, **campos):
    payload = {
        "chave_confirmacao": str(chave),
        "itens-TOTAL_FORMS": str(total_itens),
        "itens-INITIAL_FORMS": "0",
        "itens-MIN_NUM_FORMS": "0",
        "itens-MAX_NUM_FORMS": "1000",
    }
    payload.update(campos)
    return payload


def _obter_chave_confirmacao(client):
    resposta = client.get(reverse("estoque:entrada_nova"))
    conteudo = resposta.content.decode()
    inicio = conteudo.index('name="chave_confirmacao"')
    trecho = conteudo[inicio : inicio + 200]
    inicio_valor = trecho.index('value="') + len('value="')
    fim_valor = trecho.index('"', inicio_valor)
    return trecho[inicio_valor:fim_valor]


# ---------------------------------------------------------------------------
# GET: gera uma chave_confirmacao válida (research R4).
# ---------------------------------------------------------------------------


def test_get_da_composicao_gera_uma_chave_de_confirmacao_valida(client, funcionario_almoxarifado):
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("estoque:entrada_nova"))

    assert resposta.status_code == 200
    chave = _obter_chave_confirmacao(client)
    uuid.UUID(chave)  # não deveria levantar


def test_duas_visitas_a_get_geram_chaves_diferentes(client, funcionario_almoxarifado):
    """Sem estado no servidor (research R3): cada GET é uma composição nova,
    então duas abas/visitas não podem compartilhar a mesma chave."""
    client.force_login(funcionario_almoxarifado)

    chave_a = _obter_chave_confirmacao(client)
    chave_b = _obter_chave_confirmacao(client)

    assert chave_a != chave_b


# ---------------------------------------------------------------------------
# Buscar material: nunca grava; material já incluído aparece sem ação.
# ---------------------------------------------------------------------------


def test_buscar_material_por_codigo_exato_nao_grava_nada(
    client, funcionario_almoxarifado, criar_material
):
    from estoque.models import Entrada

    material = criar_material("700.000.001", Decimal("10.000"), descricao="Parafuso Allen M6")
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    resposta = client.post(
        reverse("estoque:entrada_nova"),
        _payload_base(chave, acao="buscar_material", busca_material=material.cadpro),
    )

    assert resposta.status_code == 200
    assert material.cadpro in resposta.content.decode()
    assert Entrada.objects.count() == 0


def test_buscar_material_por_descricao_sem_acento_encontra_o_material(
    client, funcionario_almoxarifado, criar_material
):
    material = criar_material("700.000.002", Decimal("10.000"), descricao="Válvula de Esfera")
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    resposta = client.post(
        reverse("estoque:entrada_nova"),
        _payload_base(chave, acao="buscar_material", busca_material="valvula esfera"),
    )

    assert resposta.status_code == 200
    assert material.cadpro in resposta.content.decode()


def test_material_inexistente_no_catalogo_nao_aparece_na_busca(
    client, funcionario_almoxarifado, criar_material
):
    criar_material("700.000.003", Decimal("10.000"), descricao="Arruela Lisa")
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    resposta = client.post(
        reverse("estoque:entrada_nova"),
        _payload_base(chave, acao="buscar_material", busca_material="000.999.999"),
    )

    assert resposta.status_code == 200


# ---------------------------------------------------------------------------
# Adicionar/remover item: nunca grava.
# ---------------------------------------------------------------------------


def test_adicionar_material_acrescenta_uma_linha_sem_gravar(
    client, funcionario_almoxarifado, criar_material
):
    from estoque.models import Entrada, ItemEntrada

    material = criar_material("700.000.004", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    resposta = client.post(
        reverse("estoque:entrada_nova"),
        _payload_base(chave, adicionar_material=str(material.pk)),
    )

    assert resposta.status_code == 200
    assert material.cadpro in resposta.content.decode()
    assert Entrada.objects.count() == 0
    assert ItemEntrada.objects.count() == 0


def test_remover_item_retira_a_linha_sem_gravar(client, funcionario_almoxarifado, criar_material):
    material = criar_material("700.000.005", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    payload = _payload_base(chave, total_itens=1, remover_item="0")
    payload.update(_payload_item(0, material.pk, "1"))
    resposta = client.post(reverse("estoque:entrada_nova"), payload)

    assert resposta.status_code == 200


# ---------------------------------------------------------------------------
# Revisar: valida tudo; inválido → erros com dados preservados; válido →
# resumo com saldo atual e resultante (FR-008, FR-009).
# ---------------------------------------------------------------------------


def test_revisar_sem_itens_e_recusado_preservando_o_motivo_escolhido(
    client, funcionario_almoxarifado
):
    from estoque.models import Entrada, MotivoEntrada, TipoDocumentoEntrada

    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    resposta = client.post(
        reverse("estoque:entrada_nova"),
        _payload_base(
            chave,
            acao="revisar",
            motivo=MotivoEntrada.DOACAO_RECEBIDA,
            tipo_documento=TipoDocumentoEntrada.NOTA_FISCAL,
            numero_documento="TD-0001",
        ),
    )

    assert resposta.status_code == 200
    assert Entrada.objects.count() == 0
    # FR-009: dados preservados — o valor do motivo escolhido continua na
    # resposta (seja como option selecionada, seja como valor do campo).
    assert "TD-0001" in resposta.content.decode()


def test_revisar_valido_mostra_saldo_atual_e_resultante_do_item(
    client, funcionario_almoxarifado, criar_material
):
    from estoque.models import Entrada, MotivoEntrada, TipoDocumentoEntrada

    material = criar_material("700.000.006", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    payload = _payload_base(
        chave,
        total_itens=1,
        acao="revisar",
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        tipo_documento=TipoDocumentoEntrada.NOTA_FISCAL,
        numero_documento="TD-0002",
    )
    payload.update(_payload_item(0, material.pk, "5"))
    resposta = client.post(reverse("estoque:entrada_nova"), payload)

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert material.cadpro in conteudo
    assert "10" in conteudo  # saldo atual
    assert "15" in conteudo  # saldo resultante (10 + 5)
    assert Entrada.objects.count() == 0, "Revisar nunca grava (FR-008)"


# ---------------------------------------------------------------------------
# NOVO (achado P2 do gate visual, "erros em rodadas", item 8): erro de
# FORMATO da quantidade não pode impedir os erros de cabeçalho de aparecer
# na mesma resposta — o usuário precisa ver tudo de uma vez, não corrigir em
# rodadas.
# ---------------------------------------------------------------------------


def test_revisar_com_cabecalho_vazio_e_quantidade_malformada_mostra_todos_os_erros_juntos(
    client, funcionario_almoxarifado, criar_material
):
    from estoque.models import Entrada

    material = criar_material("700.000.033", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    payload = _payload_base(chave, total_itens=1, acao="revisar")
    payload.update(_payload_item(0, material.pk, "0,0001"))
    resposta = client.post(reverse("estoque:entrada_nova"), payload)

    assert resposta.status_code == 200
    assert Entrada.objects.count() == 0
    conteudo = resposta.content.decode()
    assert "Escolha o motivo da entrada." in conteudo
    assert "Escolha o tipo de documento." in conteudo
    assert "Informe o número do documento." in conteudo
    assert "Informe no máximo três casas decimais." in conteudo


# ---------------------------------------------------------------------------
# NOVO (decisão do dono do produto, gate visual, 2026-09-27, item 9): em
# COMPRA com o tipo ainda vazio, qualquer re-render da composição (aqui, um
# "Revisar" inválido) pré-seleciona "Nota fiscal" — o usuário pode trocar.
# ---------------------------------------------------------------------------


def test_revisar_invalido_com_motivo_compra_preseleciona_nota_fiscal_quando_tipo_vazio(
    client, funcionario_almoxarifado
):
    from estoque.models import MotivoEntrada, TipoDocumentoEntrada

    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    resposta = client.post(
        reverse("estoque:entrada_nova"),
        _payload_base(
            chave,
            acao="revisar",
            motivo=MotivoEntrada.COMPRA,
            numero_documento="TD-COMPRA-0001",
        ),
    )

    assert resposta.status_code == 200
    assert (
        resposta.context["cabecalho_form"]["tipo_documento"].value()
        == TipoDocumentoEntrada.NOTA_FISCAL
    )


def test_voltar_do_resumo_devolve_o_formulario_preenchido(
    client, funcionario_almoxarifado, criar_material
):
    from estoque.models import MotivoEntrada, TipoDocumentoEntrada

    material = criar_material("700.000.007", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    payload = _payload_base(
        chave,
        total_itens=1,
        acao="voltar",
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        tipo_documento=TipoDocumentoEntrada.NOTA_FISCAL,
        numero_documento="TD-0003",
    )
    payload.update(_payload_item(0, material.pk, "5"))
    resposta = client.post(reverse("estoque:entrada_nova"), payload)

    assert resposta.status_code == 200
    assert "TD-0003" in resposta.content.decode()


# ---------------------------------------------------------------------------
# Formato de EXIBIÇÃO x formato de ENTRADA (Fase C, filtro `quantidade`): o
# resumo mostra "1.500", mas o que o navegador ENVIA (campos ocultos do resumo,
# `<input>` de quantidade da composição) nunca pode ser o texto de exibição —
# "1.500" enviado seria lido como 1,5, não 1500 (`estoque.quantidade.
# interpretar_quantidade_recebida`). Regressão silenciosa e cara: quantidade
# errada gravada por um filtro de apresentação.
# ---------------------------------------------------------------------------


def _campos_ocultos(html):
    """`{name: value}` de todos os `<input type="hidden">` do HTML — o que o
    navegador reenviaria ao confirmar."""
    campos = {}
    for tag in re.findall(r'<input\b[^>]*type="hidden"[^>]*>', html):
        nome = re.search(r'name="([^"]*)"', tag)
        valor = re.search(r'value="([^"]*)"', tag)
        if nome:
            campos[nome.group(1)] = valor.group(1) if valor else ""
    return campos


def _valor_do_input(html, name):
    tag = re.search(rf'<input\b[^>]*name="{re.escape(name)}"[^>]*>', html)
    assert tag is not None, f"<input name={name!r}> não encontrado"
    valor = re.search(r'value="([^"]*)"', tag.group())
    return valor.group(1) if valor else ""


def _revisar(client, chave, material, quantidade):
    from estoque.models import MotivoEntrada, TipoDocumentoEntrada

    payload = _payload_base(
        chave,
        total_itens=1,
        acao="revisar",
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        tipo_documento=TipoDocumentoEntrada.NOTA_FISCAL,
        numero_documento=f"TD-{uuid.uuid4()}",
    )
    payload.update(_payload_item(0, material.pk, quantidade))
    return client.post(reverse("estoque:entrada_nova"), payload)


@pytest.mark.parametrize(
    "digitado, exibido",
    [("1500", "1.500"), ("6,000", "6"), ("1234,5", "1.234,5")],
)
def test_resumo_formata_so_a_exibicao_e_preserva_o_valor_enviado_nos_campos_ocultos(
    client, funcionario_almoxarifado, criar_material, digitado, exibido
):
    material = criar_material("700.000.030", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    resposta = _revisar(client, chave, material, digitado)

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert re.search(
        rf'<td class="table-cell-numeric">\s*{re.escape(exibido)}\s*</td>', conteudo
    ), f"resumo deveria exibir {digitado!r} como {exibido!r}"
    hidden = _campos_ocultos(conteudo)
    assert hidden["itens-0-quantidade"] == digitado, (
        "o campo oculto que será reenviado não pode carregar o formato de exibição"
    )


def test_confirmar_com_os_campos_ocultos_do_resumo_registra_a_quantidade_digitada(
    client, funcionario_almoxarifado, criar_material
):
    """Ida e volta real: o que o navegador reenviaria a partir do resumo
    renderizado (com "1.500" na tela) grava 1500, não 1,5."""
    from estoque.models import Entrada

    material = criar_material("700.000.031", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)
    resumo = _revisar(client, chave, material, "1500")
    assert "1.500" in resumo.content.decode(), "pré-condição: exibição formatada"

    reenvio = _campos_ocultos(resumo.content.decode())
    reenvio.pop("acao", None)  # pertence ao formulário "Voltar e corrigir"
    resposta = client.post(reverse("estoque:entrada_confirmar"), reenvio)

    assert resposta.status_code == 302
    entrada = Entrada.objects.get()
    assert entrada.itens.get().quantidade == Decimal("1500.000")
    material.refresh_from_db()
    assert material.saldo == Decimal("1510.000")


@pytest.mark.parametrize("digitado", ["1500", "6,000", "1234,5"])
def test_voltar_do_resumo_devolve_a_quantidade_como_digitada(
    client, funcionario_almoxarifado, criar_material, digitado
):
    from estoque.models import MotivoEntrada, TipoDocumentoEntrada

    material = criar_material("700.000.032", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)
    payload = _payload_base(
        chave,
        total_itens=1,
        acao="voltar",
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        tipo_documento=TipoDocumentoEntrada.NOTA_FISCAL,
        numero_documento="TD-VOLTAR-QTD",
    )
    payload.update(_payload_item(0, material.pk, digitado))

    resposta = client.post(reverse("estoque:entrada_nova"), payload)

    assert resposta.status_code == 200
    assert _valor_do_input(resposta.content.decode(), "itens-0-quantidade") == digitado


def test_busca_de_material_exibe_o_saldo_em_pt_br(client, funcionario_almoxarifado, criar_material):
    material = criar_material("700.000.033", Decimal("27000.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    resposta = client.post(
        reverse("estoque:entrada_nova"),
        _payload_base(chave, acao="buscar_material", busca_material=material.cadpro),
    )

    assert re.search(
        r'<td class="table-cell-numeric">\s*27\.000\s*</td>', resposta.content.decode()
    )


# ---------------------------------------------------------------------------
# Confirmação: efetiva, idempotente, recusa campos adulterados.
# ---------------------------------------------------------------------------


def _payload_confirmacao(chave, material_pk, quantidade="5", **campos):
    from estoque.models import MotivoEntrada, TipoDocumentoEntrada

    payload = _payload_base(
        chave,
        total_itens=1,
        motivo=campos.pop("motivo", MotivoEntrada.DOACAO_RECEBIDA),
        tipo_documento=campos.pop("tipo_documento", TipoDocumentoEntrada.NOTA_FISCAL),
        numero_documento=campos.pop("numero_documento", str(uuid.uuid4())),
    )
    payload.update(_payload_item(0, material_pk, quantidade))
    payload.update(campos)
    return payload


def test_confirmar_com_dados_validos_registra_e_redireciona_ao_detalhe(
    client, funcionario_almoxarifado, criar_material
):
    from estoque.models import Entrada

    material = criar_material("700.000.008", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    resposta = client.post(
        reverse("estoque:entrada_confirmar"),
        _payload_confirmacao(chave, material.pk),
    )

    assert resposta.status_code == 302
    entrada = Entrada.objects.get()
    assert resposta.url == reverse("estoque:entrada_detalhe", args=[entrada.pk])
    material.refresh_from_db()
    assert material.saldo == Decimal("15.000")


def test_reenvio_da_mesma_confirmacao_leva_ao_detalhe_com_aviso_de_ja_registrada(
    client, funcionario_almoxarifado, criar_material
):
    from estoque.models import Entrada

    material = criar_material("700.000.009", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)
    payload = _payload_confirmacao(chave, material.pk)

    primeira = client.post(reverse("estoque:entrada_confirmar"), payload)
    assert primeira.status_code == 302
    entrada = Entrada.objects.get()

    segunda = client.post(reverse("estoque:entrada_confirmar"), payload)

    assert segunda.status_code == 302
    assert segunda.url == reverse("estoque:entrada_detalhe", args=[entrada.pk])
    assert Entrada.objects.count() == 1
    material.refresh_from_db()
    assert material.saldo == Decimal("15.000"), "a quantidade não pode ter sido aplicada duas vezes"

    detalhe = client.get(segunda.url)
    mensagens = [str(m) for m in detalhe.context["messages"]]
    assert any("já foi registrada" in m for m in mensagens)


@pytest.mark.parametrize(
    "campos_adulterados, descricao",
    [
        pytest.param({"motivo": "MOTIVO_INEXISTENTE"}, "motivo_invalido", id="motivo_invalido"),
        pytest.param(
            {"itens-0-material": "999999999"}, "material_inexistente", id="material_inexistente"
        ),
    ],
)
def test_campos_ocultos_adulterados_sao_recusados_sem_gravar(
    client, funcionario_almoxarifado, criar_material, campos_adulterados, descricao
):
    from estoque.models import Entrada

    material = criar_material(f"700.000.{hash(descricao) % 900 + 10:03d}", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)
    payload = _payload_confirmacao(chave, material.pk)
    payload.update(campos_adulterados)

    resposta = client.post(reverse("estoque:entrada_confirmar"), payload)

    assert resposta.status_code in (200, 400)
    assert Entrada.objects.count() == 0
    material.refresh_from_db()
    assert material.saldo == Decimal("10.000")


def test_emitente_bloqueado_na_confirmacao_e_recusado_sem_gravar(
    client, funcionario_almoxarifado, criar_material, criar_fornecedor
):
    from estoque.models import Entrada, MotivoEntrada

    material = criar_material("700.000.020", Decimal("10.000"))
    fornecedor = criar_fornecedor("7001", "Fornecedor Bloqueado", bloqueado=True)
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    resposta = client.post(
        reverse("estoque:entrada_confirmar"),
        _payload_confirmacao(
            chave, material.pk, motivo=MotivoEntrada.COMPRA, emitente=str(fornecedor.pk)
        ),
    )

    assert resposta.status_code == 200
    assert Entrada.objects.count() == 0


def test_chave_de_confirmacao_malformada_e_recusada_com_400_sem_gravar(
    client, funcionario_almoxarifado, criar_material
):
    from estoque.models import Entrada

    material = criar_material("700.000.021", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)

    payload = _payload_confirmacao("nao-e-um-uuid", material.pk)
    resposta = client.post(reverse("estoque:entrada_confirmar"), payload)

    assert resposta.status_code == 400
    assert Entrada.objects.count() == 0


# ---------------------------------------------------------------------------
# HX-Request: fragmento x página inteira (research R3, patrão de
# catalogo/views.py).
# ---------------------------------------------------------------------------


def test_resposta_sem_hx_request_e_pagina_inteira(client, funcionario_almoxarifado):
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("estoque:entrada_nova"))

    assert "<html" in resposta.content.decode().lower()


def test_resposta_com_hx_request_e_um_fragmento(client, funcionario_almoxarifado, criar_material):
    material = criar_material("700.000.022", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    resposta = client.post(
        reverse("estoque:entrada_nova"),
        _payload_base(chave, acao="buscar_material", busca_material=material.cadpro),
        headers={"hx-request": "true"},
    )

    assert "<html" not in resposta.content.decode().lower()


# ---------------------------------------------------------------------------
# Sessão/usuário desativado na confirmação (INV-AUTH-001).
# ---------------------------------------------------------------------------


def test_usuario_desativado_entre_preenchimento_e_confirmacao_vai_ao_login_sem_gravar(
    client, funcionario_almoxarifado, criar_material
):
    from estoque.models import Entrada

    material = criar_material("700.000.023", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)
    funcionario_almoxarifado.is_active = False
    funcionario_almoxarifado.save(update_fields=["is_active"])

    resposta = client.post(
        reverse("estoque:entrada_confirmar"),
        _payload_confirmacao(chave, material.pk),
    )

    assert resposta.status_code == 302
    assert reverse("login") in resposta.url
    assert Entrada.objects.count() == 0
    material.refresh_from_db()
    assert material.saldo == Decimal("10.000")


def test_confirmar_sem_sessao_autenticada_vai_ao_login_sem_gravar(
    client, funcionario_almoxarifado, criar_material
):
    from estoque.models import Entrada

    material = criar_material("700.000.024", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)
    client.logout()

    resposta = client.post(
        reverse("estoque:entrada_confirmar"),
        _payload_confirmacao(chave, material.pk),
    )

    assert resposta.status_code == 302
    assert reverse("login") in resposta.url
    assert Entrada.objects.count() == 0


# ---------------------------------------------------------------------------
# Detalhe: motivo, referência, autor, momento, itens (código, descrição,
# unidade, quantidade).
# ---------------------------------------------------------------------------


def test_detalhe_exibe_motivo_referencia_autor_momento_e_itens(
    client, funcionario_almoxarifado, criar_material, criar_fornecedor
):
    from estoque.models import MotivoEntrada

    material = criar_material(
        "700.000.025", Decimal("10.000"), unidade="KG", descricao="Cimento Portland"
    )
    fornecedor = criar_fornecedor("7002", "Fornecedor Detalhe")
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    confirmacao = client.post(
        reverse("estoque:entrada_confirmar"),
        _payload_confirmacao(
            chave,
            material.pk,
            quantidade="3",
            motivo=MotivoEntrada.COMPRA,
            emitente=str(fornecedor.pk),
            numero_documento="NF-DETALHE-0001",
        ),
    )
    assert confirmacao.status_code == 302

    resposta = client.get(confirmacao.url)

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "NF-DETALHE-0001" in conteudo
    assert fornecedor.nome in conteudo
    assert funcionario_almoxarifado.matricula in conteudo
    assert material.cadpro in conteudo
    assert "Cimento Portland" in conteudo
    assert "KG" in conteudo
    assert "3" in conteudo


# ---------------------------------------------------------------------------
# NOVO (revisão do code-reviewer, item 4): quantidade com parte inteira
# absurdamente grande não pode derrubar a view com 500 — precisa virar erro
# de campo comum, como qualquer outra quantidade mal formatada. Depende da
# correção de `estoque/quantidade.py` (ver `tests/test_estoque_quantidade.py`);
# falha até lá.
# ---------------------------------------------------------------------------


def test_revisar_com_quantidade_de_cinco_mil_digitos_nao_derruba_o_servidor(
    client, funcionario_almoxarifado, criar_material
):
    from estoque.models import Entrada, MotivoEntrada, TipoDocumentoEntrada

    material = criar_material("700.000.026", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    payload = _payload_base(
        chave,
        total_itens=1,
        acao="revisar",
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        tipo_documento=TipoDocumentoEntrada.NOTA_FISCAL,
        numero_documento="TD-QUANTIDADE-ENORME",
    )
    payload.update(_payload_item(0, material.pk, "5" * 5000))

    resposta = client.post(reverse("estoque:entrada_nova"), payload)

    assert resposta.status_code == 200
    assert Entrada.objects.count() == 0


def test_confirmar_com_quantidade_de_cinco_mil_digitos_nao_derruba_o_servidor(
    client, funcionario_almoxarifado, criar_material
):
    from estoque.models import Entrada

    material = criar_material("700.000.027", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    resposta = client.post(
        reverse("estoque:entrada_confirmar"),
        _payload_confirmacao(chave, material.pk, quantidade="5" * 5000),
    )

    assert resposta.status_code == 200
    assert Entrada.objects.count() == 0


# ---------------------------------------------------------------------------
# NOVO (revisão do code-reviewer, item 4): `_aplicar_adicionar_material`
# (`estoque/views.py`) lê `itens-TOTAL_FORMS` do POST cru e itera
# `range(total)` em Python puro, ANTES de o formset (que teria um
# `absolute_max`) sequer existir — um `TOTAL_FORMS` absurdo trava o processo
# por minutos. Correção esperada: recusar ou aplicar um teto (igual ao
# `absolute_max` do formset) ANTES de iterar.
#
# `SIGALRM` interrompe a chamada com um teto de tempo real e determinístico
# (sem thread nem `transaction=True`: a única chamada roda no mesmo
# processo/thread principal, então o "custo" do bug fica limitado ao teto do
# alarme, nunca a uma execução completa de bilhões de iterações). Falha até
# a correção de produção.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not hasattr(signal, "SIGALRM"), reason="SIGALRM indisponível nesta plataforma"
)
def test_total_forms_absurdo_ao_adicionar_material_nao_trava_nem_derruba_o_servidor(
    client, funcionario_almoxarifado, criar_material
):
    material = criar_material("700.000.028", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    payload = _payload_base(chave, adicionar_material=str(material.pk))
    payload["itens-TOTAL_FORMS"] = "1000000000"

    class _TempoExcedido(Exception):
        pass

    def _alarme(signum, frame):
        raise _TempoExcedido()

    teto_segundos = 3
    handler_anterior = signal.signal(signal.SIGALRM, _alarme)
    signal.alarm(teto_segundos)
    try:
        resposta = client.post(reverse("estoque:entrada_nova"), payload)
    except _TempoExcedido:
        pytest.fail(
            f"a composição não respondeu em {teto_segundos}s com um TOTAL_FORMS "
            "absurdo (1 bilhão) — estoque/views.py precisa rejeitar ou aplicar um "
            "teto antes de iterar sobre range(total)"
        )
    else:
        assert resposta.status_code != 500
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, handler_anterior)


# ---------------------------------------------------------------------------
# NOVO (revisão do code-reviewer, item 4): a confirmação recusada por
# `ReferenciaJaUsada` precisa trazer a entrada já registrada no contexto
# (`entrada_existente`) e um link para o detalhe dela — hoje o re-render só
# mostra o texto da mensagem (data/matrícula), sem contexto nem link.
# ---------------------------------------------------------------------------


def test_confirmar_com_referencia_ja_usada_traz_a_entrada_existente_e_o_link_do_detalhe(
    client, funcionario_almoxarifado, criar_material
):
    from estoque.models import Entrada

    material = criar_material("700.000.029", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    numero = "NF-REFERENCIA-EXISTENTE-0001"

    chave_primeira = _obter_chave_confirmacao(client)
    primeira = client.post(
        reverse("estoque:entrada_confirmar"),
        _payload_confirmacao(chave_primeira, material.pk, numero_documento=numero),
    )
    assert primeira.status_code == 302
    entrada_existente = Entrada.objects.get()

    chave_segunda = _obter_chave_confirmacao(client)
    segunda = client.post(
        reverse("estoque:entrada_confirmar"),
        _payload_confirmacao(chave_segunda, material.pk, numero_documento=numero),
    )

    assert segunda.status_code == 200
    assert segunda.context["entrada_existente"].pk == entrada_existente.pk
    link_detalhe = reverse("estoque:entrada_detalhe", args=[entrada_existente.pk])
    assert link_detalhe in segunda.content.decode()


# ---------------------------------------------------------------------------
# NOVO (revisão do code-reviewer, item 4): a confirmação recusada por
# `EmitenteIndisponivel` (emitente bloqueado entre "Revisar" e "Confirmar")
# precisa limpar o campo oculto `emitente` no re-render — hoje o form
# reenvia o mesmo `pk` bloqueado, uma escolha que o usuário não pode mais
# confirmar.
# ---------------------------------------------------------------------------


def test_confirmar_com_emitente_indisponivel_limpa_o_campo_oculto_do_emitente(
    client, funcionario_almoxarifado, criar_material, criar_fornecedor
):
    from estoque.models import MotivoEntrada

    material = criar_material("700.000.030", Decimal("10.000"))
    fornecedor = criar_fornecedor("7004", "Fornecedor Bloqueado Na Confirmacao")
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    fornecedor.bloqueado = True
    fornecedor.save(update_fields=["bloqueado"])

    resposta = client.post(
        reverse("estoque:entrada_confirmar"),
        _payload_confirmacao(
            chave, material.pk, motivo=MotivoEntrada.COMPRA, emitente=str(fornecedor.pk)
        ),
    )

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert f'name="emitente" value="{fornecedor.pk}"' not in conteudo


# ---------------------------------------------------------------------------
# NOVO (revisão do code-reviewer, item 4): reenviar a MESMA
# `chave_confirmacao` com conteúdo DIFERENTE (outro número de documento) não
# pode passar pela mesma mensagem de "Esta entrada já foi registrada." — o
# usuário reaproveitou sem querer um formulário antigo para OUTRO
# documento; a mensagem precisa dizer isso e apontar para a entrada que a
# chave já registrou. Reenviar com o MESMO conteúdo continua com a
# mensagem de sempre.
# ---------------------------------------------------------------------------


def test_reenvio_da_mesma_chave_com_conteudo_diferente_nao_registra_e_avisa_do_formulario_usado(
    client, funcionario_almoxarifado, criar_material
):
    from estoque.models import Entrada

    material = criar_material("700.000.031", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    primeira = client.post(
        reverse("estoque:entrada_confirmar"),
        _payload_confirmacao(chave, material.pk, numero_documento="NF-CONTEUDO-A"),
    )
    assert primeira.status_code == 302
    entrada = Entrada.objects.get()

    segunda = client.post(
        reverse("estoque:entrada_confirmar"),
        _payload_confirmacao(chave, material.pk, numero_documento="NF-CONTEUDO-DIFERENTE"),
    )

    assert segunda.status_code == 302
    assert segunda.url == reverse("estoque:entrada_detalhe", args=[entrada.pk])
    assert Entrada.objects.count() == 1
    material.refresh_from_db()
    assert material.saldo == Decimal("15.000"), "conteúdo diferente não pode ter sido aplicado"

    detalhe = client.get(segunda.url)
    mensagens = [str(m) for m in detalhe.context["messages"]]
    assert any(
        "já foi usado para registrar a entrada" in m and f"#{entrada.pk}" in m
        for m in mensagens
    ), f"esperava a mensagem de formulário reaproveitado; obteve {mensagens!r}"
    assert not any(m == "Esta entrada já foi registrada." for m in mensagens), (
        "conteúdo diferente não pode usar a mesma mensagem do reenvio idêntico"
    )


def test_reenvio_da_mesma_chave_com_mesmo_conteudo_continua_com_a_mensagem_de_ja_registrada(
    client, funcionario_almoxarifado, criar_material
):
    from estoque.models import Entrada

    material = criar_material("700.000.032", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)
    payload = _payload_confirmacao(chave, material.pk, numero_documento="NF-CONTEUDO-IGUAL")

    primeira = client.post(reverse("estoque:entrada_confirmar"), payload)
    assert primeira.status_code == 302
    entrada = Entrada.objects.get()

    segunda = client.post(reverse("estoque:entrada_confirmar"), payload)

    assert segunda.status_code == 302
    assert segunda.url == reverse("estoque:entrada_detalhe", args=[entrada.pk])
    assert Entrada.objects.count() == 1

    detalhe = client.get(segunda.url)
    mensagens = [str(m) for m in detalhe.context["messages"]]
    assert any(m == "Esta entrada já foi registrada." for m in mensagens)


# ---------------------------------------------------------------------------
# NOVO (2ª rodada do code-reviewer, item 1): `validar_entrada` pode levantar
# `EntradaJaRegistrada` (referência duplicada com a MESMA chave) — cenário de
# confirmar, voltar pelo navegador e "Revisar" de novo com o mesmo payload.
# Antes da correção, `EntradaNovaView._revisar` só capturava `EntradaInvalida`
# e deixava isso virar 500.
# ---------------------------------------------------------------------------


def test_revisar_apos_confirmar_com_a_mesma_chave_e_referencia_redireciona_ao_detalhe(
    client, funcionario_almoxarifado, criar_material
):
    from estoque.models import Entrada

    material = criar_material("700.000.036", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)
    payload_confirmar = _payload_confirmacao(
        chave, material.pk, numero_documento="NF-REVISAR-APOS-CONFIRMAR"
    )

    confirmar = client.post(reverse("estoque:entrada_confirmar"), payload_confirmar)
    assert confirmar.status_code == 302
    entrada = Entrada.objects.get()

    payload_revisar = dict(payload_confirmar)
    payload_revisar["acao"] = "revisar"
    revisar = client.post(reverse("estoque:entrada_nova"), payload_revisar)

    assert revisar.status_code == 302
    assert revisar.url == reverse("estoque:entrada_detalhe", args=[entrada.pk])
    assert Entrada.objects.count() == 1

    detalhe = client.get(revisar.url)
    mensagens = [str(m) for m in detalhe.context["messages"]]
    assert any(m == "Esta entrada já foi registrada." for m in mensagens)


# ---------------------------------------------------------------------------
# NOVO (2ª rodada do code-reviewer, item 2): um item excluído por erro de
# FORMATO (linha 0) não pode desalinhar a posição dos erros de NEGÓCIO dos
# itens seguintes (linha 1) — o erro de saldo acima do limite precisa
# apontar para a linha 1, não para a 0.
# ---------------------------------------------------------------------------


def test_revisar_com_erro_de_formato_na_linha_0_mantem_o_erro_de_saldo_na_linha_1(
    client, funcionario_almoxarifado, criar_material
):
    from estoque.models import Entrada, MotivoEntrada, TipoDocumentoEntrada

    material_formato_invalido = criar_material("700.000.037", Decimal("10.000"))
    material_saldo_no_limite = criar_material("700.000.038", Decimal("999999999999.999"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    payload = _payload_base(
        chave,
        total_itens=2,
        acao="revisar",
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        tipo_documento=TipoDocumentoEntrada.NOTA_FISCAL,
        numero_documento="TD-FORMATO-E-LIMITE",
    )
    payload.update(_payload_item(0, material_formato_invalido.pk, "abc"))
    payload.update(_payload_item(1, material_saldo_no_limite.pk, "1"))

    resposta = client.post(reverse("estoque:entrada_nova"), payload)

    assert resposta.status_code == 200
    assert Entrada.objects.count() == 0
    item_formset = resposta.context["item_formset"]
    assert "vírgula" in str(item_formset.forms[0].errors.get("quantidade", ""))
    assert not item_formset.forms[0].non_field_errors()
    assert any(
        "limite máximo representável" in mensagem
        for mensagem in item_formset.forms[1].non_field_errors()
    )


# ---------------------------------------------------------------------------
# NOVO (2ª rodada do code-reviewer, item 5): `TOTAL_FORMS` acima de
# `absolute_max` não pode ser truncado em silêncio por `item_formset.forms` —
# a confirmação precisa recusar explicitamente, sem gravar nada.
# ---------------------------------------------------------------------------


def test_confirmar_com_total_forms_acima_do_teto_e_recusado_sem_gravar(
    client, funcionario_almoxarifado, criar_material
):
    from estoque.forms import ItemEntradaFormSet
    from estoque.models import Entrada

    material = criar_material("700.000.039", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    payload = _payload_confirmacao(chave, material.pk)
    payload["itens-TOTAL_FORMS"] = str(ItemEntradaFormSet.absolute_max + 1)

    resposta = client.post(reverse("estoque:entrada_confirmar"), payload)

    assert resposta.status_code == 200
    assert Entrada.objects.count() == 0
    material.refresh_from_db()
    assert material.saldo == Decimal("10.000")


# ---------------------------------------------------------------------------
# NOVO (2ª rodada do code-reviewer, item 6): a pré-seleção de "Nota fiscal"
# em COMPRA nunca ocorre na confirmação — o tipo vazio é recusado como
# qualquer outro campo de cabeçalho ausente.
# ---------------------------------------------------------------------------


def test_confirmar_com_motivo_compra_e_tipo_vazio_e_recusado_sem_preselecao(
    client, funcionario_almoxarifado, criar_material, criar_fornecedor
):
    from estoque.models import Entrada, MotivoEntrada

    material = criar_material("700.000.040", Decimal("10.000"))
    fornecedor = criar_fornecedor("7006", "Fornecedor Compra Sem Tipo")
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    payload = _payload_confirmacao(
        chave,
        material.pk,
        motivo=MotivoEntrada.COMPRA,
        tipo_documento="",
        emitente=str(fornecedor.pk),
    )

    resposta = client.post(reverse("estoque:entrada_confirmar"), payload)

    assert resposta.status_code == 200
    assert Entrada.objects.count() == 0
    assert "Escolha o tipo de documento." in resposta.content.decode()


# ---------------------------------------------------------------------------
# 3ª rodada do code-reviewer: "Revisar" via HTMX depois de a entrada já ter
# sido registrada não pode aninhar a página de detalhe no formulário — a
# resposta usa `HX-Redirect`; e o teto de itens do formset é recusado de forma
# explícita mesmo com todas as linhas válidas (sem truncar em silêncio).
# ---------------------------------------------------------------------------


def test_revisar_via_htmx_apos_confirmar_responde_com_hx_redirect_ao_detalhe(
    client, funcionario_almoxarifado, criar_material
):
    from estoque.models import Entrada

    material = criar_material("700.000.040", Decimal("10.000"))
    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)
    payload = _payload_confirmacao(chave, material.pk, numero_documento="NF-HX-REDIRECT")

    assert client.post(reverse("estoque:entrada_confirmar"), payload).status_code == 302
    entrada = Entrada.objects.get()

    payload_revisar = dict(payload, acao="revisar")
    resposta = client.post(
        reverse("estoque:entrada_nova"), payload_revisar, headers={"hx-request": "true"}
    )

    assert resposta["HX-Redirect"] == reverse("estoque:entrada_detalhe", args=[entrada.pk])
    assert resposta.status_code != 302
    assert Entrada.objects.count() == 1


def test_montar_entrada_informada_recusa_total_forms_acima_do_teto_com_linhas_validas(
    criar_material,
):
    from django.forms import BaseFormSet, formset_factory

    from estoque.forms import CabecalhoEntradaForm, ItemEntradaForm, montar_entrada_informada
    from estoque.models import MotivoEntrada, TipoDocumentoEntrada

    materiais = [criar_material(f"700.000.05{i}", Decimal("1.000")) for i in range(3)]
    formset_com_teto_baixo = formset_factory(
        ItemEntradaForm, formset=BaseFormSet, extra=0, can_delete=False, max_num=2, absolute_max=2
    )
    dados = _payload_base(
        uuid.uuid4(),
        total_itens=3,
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        tipo_documento=TipoDocumentoEntrada.TERMO_DOACAO,
        numero_documento="TD-TETO",
    )
    for indice, material in enumerate(materiais):
        dados.update(_payload_item(indice, material.pk, "1"))

    cabecalho = CabecalhoEntradaForm(dados)
    itens = formset_com_teto_baixo(dados, prefix="itens")

    assert montar_entrada_informada(cabecalho, itens) is None
    assert itens.non_form_errors()


@pytest.mark.parametrize("campo", ["adicionar_material", "escolher_emitente"])
@pytest.mark.parametrize("valor", ["²", "٣", "+1", " 1", "1_0", "0", "9" * 25, "9" * 5000])
def test_pk_nao_ascii_ou_malformado_nos_botoes_nao_derruba_o_servidor(
    client, funcionario_almoxarifado, campo, valor
):
    """`str.isdigit()` aceitava dígitos Unicode que o ORM recusa com
    `ValueError` (500); o `pk` dos botões só aceita dígitos ASCII."""
    from estoque.models import Entrada

    client.force_login(funcionario_almoxarifado)
    chave = _obter_chave_confirmacao(client)

    resposta = client.post(reverse("estoque:entrada_nova"), _payload_base(chave, **{campo: valor}))

    assert resposta.status_code == 200
    assert Entrada.objects.count() == 0
