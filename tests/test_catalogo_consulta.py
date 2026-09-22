"""Testes da consulta do catálogo (T030 — US2, `PERM-MATERIAL-VIEW`).

TDD: escrito antes de `ConsultaCatalogoForm`, `ConsultaCatalogoView`, da rota
`catalogo:consulta` e dos templates `catalogo/consulta.html` /
`catalogo/_resultados_consulta.html` (T032–T035, `tasks.md`). Este arquivo
falha por inteiro até essas peças existirem (`NoReverseMatch`/`ImportError`,
conforme a chamada) — esperado.

Cobre FR-023, FR-039–FR-043, SC-006, SC-007 (`spec.md`, US2) e o contrato
`GET /catalogo/` de `contracts/rotas-e-autorizacao.md`. A matriz completa de
autorização (`PERM-MATERIAL-VIEW`, `INV-AUTH-001`) está em T031
(`tests/test_catalogo_permissoes.py`); aqui a rota é sempre exercitada já
autenticada com `ROLE-REQUESTER`.

Contrato de marcadores para o frontend (T035, frontend-implementer) — os
testes abaixo dependem exclusivamente destes atributos `data-*`, nunca de
classe CSS ou texto de rótulo:
- ausência de resultados após consulta válida: um elemento com
  `data-estado="vazio"` na região de resultados;
- `codigo` fora do formato `XXX.YYY.ZZZ`: um elemento com
  `data-estado="codigo-invalido"`, sem nenhuma consulta ao banco.

Materiais são criados diretamente pelo ORM (como em
`tests/test_catalogo_modelos.py`), nunca por `Material.objects.create` fora
de teste — não é o caminho de produto (`aplicar_plano` é o único, ver T048).
`descricao_busca` é sempre gravada com `normalizar_para_busca(descricao)`,
exatamente como a produção grava (`catalogo/importacao.py`), para que a
busca por descrição exercite a mesma normalização usada em produção.
"""

import re
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from catalogo.leitura_scpi import normalizar_para_busca
from catalogo.models import ExecucaoImportacao, Material

pytestmark = pytest.mark.django_db

SHA256_FAKE = "0" * 64


def _contar_queries_material(queries_capturadas):
    """Conta, entre as queries capturadas por `CaptureQueriesContext`, só as
    que tocam `catalogo_material` — nunca as de sessão/autenticação
    (`contas_user`, `django_session`), que não são o alvo da regra "sem
    consulta"/"sem N+1"."""
    return sum(1 for query in queries_capturadas if "catalogo_material" in query["sql"])


@pytest.fixture
def execucao(chefe_almoxarifado):
    """`ExecucaoImportacao` mínima só para satisfazer o FK obrigatório de
    `Material.execucao_origem` — não é caminho de produto (só
    `aplicar_plano` cria `Material`/`ExecucaoImportacao`, ver docstring de
    `tests/test_catalogo_modelos.py`)."""
    import uuid

    return ExecucaoImportacao.objects.create(
        token_previa=uuid.uuid4(),
        executada_por=chefe_almoxarifado,
        concluida_em=timezone.now(),
        nome_arquivo="carga.csv",
        tamanho_arquivo=1024,
        sha256_arquivo=SHA256_FAKE,
        total_recebidos=1,
        total_inseridos=1,
        total_atualizados=0,
        total_atualizados_com_alteracao=0,
        total_rejeitados=0,
        total_divergencias=0,
        total_ausentes_no_arquivo=0,
    )


@pytest.fixture
def criar_material(execucao):
    """Factory de `Material` válido para os testes de consulta."""

    contador = {"valor": 0}

    def _criar_material(
        *,
        cadpro=None,
        descricao="Parafuso",
        unidade="UN",
        detalhamento="",
        grupo="",
        subgrupo="",
        nome_grupo="",
        nome_subgrupo="",
        saldo=Decimal("10.000"),
    ):
        contador["valor"] += 1
        if cadpro is None:
            cadpro = f"900.000.{contador['valor']:03d}"
        return Material.objects.create(
            cadpro=cadpro,
            descricao=descricao,
            descricao_busca=normalizar_para_busca(descricao),
            unidade=unidade,
            detalhamento=detalhamento,
            grupo=grupo,
            subgrupo=subgrupo,
            nome_grupo=nome_grupo,
            nome_subgrupo=nome_subgrupo,
            saldo=saldo,
            saldo_inicial=saldo,
            execucao_origem=execucao,
        )

    return _criar_material


def _bulk_criar_materiais(execucao, quantidade, *, prefixo):
    """Cria `quantidade` materiais baratos via `bulk_create`, para os
    cenários de paginação/N+1 que exigem mais de 50 registros. `prefixo` são
    os 3 primeiros dígitos do `CADPRO` (ex.: "410"), para não colidir com
    outros materiais do mesmo teste."""
    materiais = [
        Material(
            cadpro=f"{prefixo}.000.{indice:03d}",
            descricao=f"Material em lote {indice}",
            descricao_busca=normalizar_para_busca(f"Material em lote {indice}"),
            unidade="UN",
            detalhamento="",
            grupo="",
            subgrupo="",
            nome_grupo="",
            nome_subgrupo="",
            saldo=Decimal("1.000"),
            saldo_inicial=Decimal("1.000"),
            execucao_origem=execucao,
        )
        for indice in range(quantidade)
    ]
    Material.objects.bulk_create(materiais)


# ---------------------------------------------------------------------------
# Código exato (FR-039, FR-041, FR-023)
# ---------------------------------------------------------------------------


def test_codigo_exato_retorna_material_com_todos_os_campos_exibidos(
    client, requisitante, criar_material
):
    criar_material(
        cadpro="000.000.002",
        descricao="Parafuso Sextavado M6",
        unidade="UND",
        detalhamento="Aço inox, cabeça sextavada",
        grupo="10",
        subgrupo="20",
        nome_grupo="Ferragens",
        nome_subgrupo="Parafusos",
        saldo=Decimal("53.400"),
    )

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"codigo": "000.000.002"})

    assert resposta.status_code == 200
    conteudo = resposta.content.decode("utf-8")
    assert "000.000.002" in conteudo
    assert "Parafuso Sextavado M6" in conteudo
    assert "UND" in conteudo
    assert "Aço inox, cabeça sextavada" in conteudo
    assert "Ferragens" in conteudo
    assert "Parafusos" in conteudo
    # Formato numérico exato (separador decimal) não é fixado pelo contrato;
    # aceita-se qualquer representação usual de 3 casas do valor gravado.
    assert "53,400" in conteudo or "53.400" in conteudo


def test_cadpro_e_exibido_sem_nenhuma_transformacao(client, requisitante, criar_material):
    """`INV-CATALOG-001`, agora no caminho de consulta: zeros à esquerda e
    pontuação não podem sofrer nenhuma normalização na exibição."""
    criar_material(cadpro="000.000.002", descricao="Zero à esquerda")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"codigo": "000.000.002"})

    assert "000.000.002" in resposta.content.decode("utf-8")


def test_codigo_com_espacos_nas_bordas_e_aparado_so_na_entrada(
    client, requisitante, criar_material
):
    """FR-039: o termo digitado é aparado (é entrada do usuário), mas isso
    não afeta o dado do material — só permite que a busca funcione."""
    criar_material(cadpro="000.000.002", descricao="Parafuso Sextavado")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"codigo": "  000.000.002  "})

    assert resposta.status_code == 200
    conteudo = resposta.content.decode("utf-8")
    assert "000.000.002" in conteudo
    assert 'data-estado="codigo-invalido"' not in conteudo


@pytest.mark.parametrize("codigo_invalido", ["2", "000.000", "abc", "000.000.0002"])
def test_codigo_fora_do_formato_nao_executa_consulta_e_mostra_estado_de_validacao(
    client, requisitante, codigo_invalido
):
    """FR-039/contrato: código parcial ou fora do formato não é tratado como
    prefixo nem completado — é um estado de validação, sem NENHUMA consulta
    a `catalogo_material`."""
    client.force_login(requisitante)

    with CaptureQueriesContext(connection) as capturadas:
        resposta = client.get(reverse("catalogo:consulta"), {"codigo": codigo_invalido})

    assert resposta.status_code == 200
    assert _contar_queries_material(capturadas.captured_queries) == 0
    conteudo = resposta.content.decode("utf-8")
    assert 'data-estado="codigo-invalido"' in conteudo
    assert "informe o código completo no formato xxx.yyy.zzz" in conteudo.lower()


# ---------------------------------------------------------------------------
# Descrição (FR-040)
# ---------------------------------------------------------------------------


def test_busca_por_descricao_em_minusculas_sem_acento_encontra_a_acentuada(
    client, requisitante, criar_material
):
    """FR-040: sem diferenciar maiúsculas nem acentuação."""
    criar_material(cadpro="000.002.001", descricao="Válvula de Registro")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"descricao": "valvula de reg"})

    assert resposta.status_code == 200
    assert "000.002.001" in resposta.content.decode("utf-8")


@pytest.mark.parametrize(
    "termo",
    ["valvula registro", "registro valvula", "valv reg", "  VALVULA   registro  "],
    ids=["palavras_soltas", "ordem_invertida", "palavras_parciais", "espacos_e_caixa"],
)
def test_busca_por_palavras_soltas_em_qualquer_ordem_encontra_o_material(
    client, requisitante, criar_material, termo
):
    """FR-040 (emenda de 2026-09-21): o termo é separado em palavras; o material
    aparece quando a descrição contém TODAS elas, em qualquer ordem, cada uma
    podendo ser parcial."""
    criar_material(cadpro="000.002.001", descricao="Válvula de Registro")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"descricao": termo})

    assert resposta.status_code == 200
    assert "000.002.001" in resposta.content.decode("utf-8")


def test_busca_por_palavras_exige_todas_as_palavras(client, requisitante, criar_material):
    """FR-040: combinação por E — basta uma palavra ausente para o material não
    aparecer; materiais que contêm todas aparecem."""
    criar_material(cadpro="000.002.001", descricao="Válvula de Registro")
    criar_material(cadpro="000.002.002", descricao="Válvula de Retenção")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"descricao": "valvula registro"})

    conteudo = resposta.content.decode("utf-8")
    assert "000.002.001" in conteudo
    assert "000.002.002" not in conteudo


def test_descricoes_iguais_aparecem_como_dois_materiais_distintos(
    client, requisitante, criar_material
):
    """FR-017: descrição igual não é chave de identidade — os dois materiais
    devem aparecer, cada um com seu próprio código."""
    criar_material(cadpro="000.001.001", descricao="Parafuso Padrão")
    criar_material(cadpro="000.001.002", descricao="Parafuso Padrão")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"descricao": "Parafuso Padrão"})

    assert resposta.status_code == 200
    conteudo = resposta.content.decode("utf-8")
    assert "000.001.001" in conteudo
    assert "000.001.002" in conteudo


# ---------------------------------------------------------------------------
# Interseção código + descrição
# ---------------------------------------------------------------------------


def test_intersecao_de_codigo_e_descricao_restringe_ao_material_correspondente(
    client, requisitante, criar_material
):
    alvo = criar_material(cadpro="000.003.001", descricao="Mangueira Hidráulica")
    criar_material(cadpro="000.003.002", descricao="Mangueira Hidráulica")

    client.force_login(requisitante)
    resposta = client.get(
        reverse("catalogo:consulta"),
        {"codigo": alvo.cadpro, "descricao": "Mangueira"},
    )

    assert resposta.status_code == 200
    conteudo = resposta.content.decode("utf-8")
    assert "000.003.001" in conteudo
    assert "000.003.002" not in conteudo


# ---------------------------------------------------------------------------
# Ausência de resultados (FR-043)
# ---------------------------------------------------------------------------


def test_ausencia_de_resultados_mostra_estado_explicito(client, requisitante, criar_material):
    criar_material(cadpro="000.004.001", descricao="Existe no catálogo")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"descricao": "NaoExisteNoCatalogo"})

    assert resposta.status_code == 200
    conteudo = resposta.content.decode("utf-8")
    assert 'data-estado="vazio"' in conteudo
    assert "000.004.001" not in conteudo


# ---------------------------------------------------------------------------
# Paginação (FR-042)
# ---------------------------------------------------------------------------


def test_paginacao_com_pagina_fora_do_intervalo_e_tratada(client, requisitante, execucao):
    _bulk_criar_materiais(execucao, 60, prefixo="500")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"pagina": "999"})

    assert resposta.status_code == 200
    # `Paginator.get_page` devolve a última página válida (2ª, com os 10
    # materiais restantes) em vez de erro.
    assert "500.000.059" in resposta.content.decode("utf-8")


def test_paginacao_com_valor_nao_numerico_nao_quebra(client, requisitante, execucao):
    _bulk_criar_materiais(execucao, 5, prefixo="510")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"pagina": "abc"})

    assert resposta.status_code == 200


def test_numero_de_queries_de_material_e_constante_entre_10_e_50_por_pagina(
    client, requisitante, execucao
):
    """Sem N+1 (FR-042): o número de queries de `catalogo_material` para
    exibir uma página não pode crescer com a quantidade de materiais nela
    exibidos."""
    client.force_login(requisitante)
    url = reverse("catalogo:consulta")

    _bulk_criar_materiais(execucao, 10, prefixo="410")
    with CaptureQueriesContext(connection) as com_10:
        resposta_10 = client.get(url)
    assert resposta_10.status_code == 200

    _bulk_criar_materiais(execucao, 40, prefixo="420")  # totaliza 50 na 1ª página
    with CaptureQueriesContext(connection) as com_50:
        resposta_50 = client.get(url)
    assert resposta_50.status_code == 200

    queries_10 = _contar_queries_material(com_10.captured_queries)
    queries_50 = _contar_queries_material(com_50.captured_queries)
    assert queries_10 > 0
    assert queries_10 == queries_50


# ---------------------------------------------------------------------------
# Sem filtro (FR-041, ordenação)
# ---------------------------------------------------------------------------


def test_sem_filtro_lista_o_catalogo_ordenado_por_cadpro(client, requisitante, criar_material):
    criar_material(cadpro="000.005.003", descricao="C")
    criar_material(cadpro="000.005.001", descricao="A")
    criar_material(cadpro="000.005.002", descricao="B")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"))

    assert resposta.status_code == 200
    conteudo = resposta.content.decode("utf-8")
    posicoes = [
        conteudo.index(codigo) for codigo in ("000.005.001", "000.005.002", "000.005.003")
    ]
    assert posicoes == sorted(posicoes)


# ---------------------------------------------------------------------------
# "Limpar" (revisão T051, achado P2): o formulário de filtros fica fora de
# `#resultados-consulta` (o `hx-target` do envio), então um "Limpar" com
# `hx-get`/`hx-target="#resultados-consulta"` trocaria só os resultados,
# deixando os campos com o texto ainda digitado — divergente do que a lista
# embaixo passa a mostrar. O link precisa ser navegação normal, sem `hx-get`.
# ---------------------------------------------------------------------------


def test_link_limpar_e_navegacao_normal_sem_hx_get(client, requisitante, criar_material):
    """O link "Limpar" não pode ter `hx-get`/`hx-target`: como o formulário
    fica fora de `#resultados-consulta`, uma troca HTMX ali só atualizaria os
    resultados, deixando os campos preenchidos com o valor antigo enquanto a
    lista já mostra o catálogo inteiro."""
    criar_material(cadpro="000.007.001", descricao="Arruela")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"codigo": "000.007.001"})

    assert resposta.status_code == 200
    conteudo = resposta.content.decode("utf-8")
    tag_limpar = re.search(r"<a[^>]*>\s*Limpar\s*</a>", conteudo)
    assert tag_limpar is not None, "link \"Limpar\" não encontrado"
    assert "hx-get" not in tag_limpar.group()
    assert "hx-target" not in tag_limpar.group()


def test_link_limpar_aponta_para_a_consulta_sem_querystring(client, requisitante, criar_material):
    """Sem parâmetro nenhum na URL, a consulta renderiza com os campos vazios
    — por isso "Limpar" só precisa apontar para lá, sem lógica adicional."""
    criar_material(cadpro="000.007.002", descricao="Porca")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"codigo": "000.007.002"})

    assert resposta.status_code == 200
    conteudo = resposta.content.decode("utf-8")
    assert f'href="{reverse("catalogo:consulta")}"' in conteudo

    resposta_limpa = client.get(reverse("catalogo:consulta"))
    assert resposta_limpa.status_code == 200
    conteudo_limpo = resposta_limpa.content.decode("utf-8")
    # Sem filtro, o campo "Código" some do valor preenchido (o material em si
    # continua na listagem — sem filtro, o catálogo inteiro é mostrado).
    assert 'value="000.007.002"' not in conteudo_limpo


# ---------------------------------------------------------------------------
# HTMX: só o fragmento (contrato, `research.md` R16)
# ---------------------------------------------------------------------------


def test_com_hx_request_a_resposta_e_so_o_fragmento(client, requisitante, criar_material):
    criar_material(cadpro="000.006.001", descricao="Fragmento HTMX")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), HTTP_HX_REQUEST="true")

    assert resposta.status_code == 200
    nomes_templates = [template.name for template in resposta.templates if template.name]
    assert "catalogo/_resultados_consulta.html" in nomes_templates
    assert "catalogo/consulta.html" not in nomes_templates


# ---------------------------------------------------------------------------
# Código inválido via HTMX: não substitui os resultados anteriores (revisão
# do gate visual, achado P2).
# ---------------------------------------------------------------------------


def test_codigo_invalido_via_htmx_nao_troca_os_resultados_e_sinaliza_so_o_campo(
    client, requisitante
):
    """`HX-Reswap: none` impede o htmx de substituir `#resultados-consulta`
    pelo alerta de erro — o campo é sinalizado à parte, via out-of-band swap
    (`hx-swap-oob`) no bloco `#campo-codigo`, mesmo id usado em
    `consulta.html`."""
    client.force_login(requisitante)

    resposta = client.get(
        reverse("catalogo:consulta"), {"codigo": "abc"}, HTTP_HX_REQUEST="true"
    )

    assert resposta.status_code == 200
    assert resposta.headers.get("HX-Reswap") == "none"
    assert resposta.headers.get("HX-Push-Url") == "false", (
        "sem trocar os resultados, a URL não pode passar a mostrar o filtro inválido"
    )
    conteudo = resposta.content.decode("utf-8")
    assert 'id="campo-codigo"' in conteudo
    assert 'hx-swap-oob="true"' in conteudo
    assert "field-has-error" in conteudo
    assert 'data-estado="codigo-invalido"' in conteudo
    assert "informe o código completo no formato xxx.yyy.zzz" in conteudo.lower()


def test_codigo_invalido_em_pagina_inteira_nao_emite_bloco_oob(client, requisitante):
    """Sem `HX-Request`, a página inteira já marca o campo inline em
    `consulta.html`: o bloco `hx-swap-oob` de `_resultados_consulta.html` não
    pode ser emitido de novo, ou `id="campo-codigo"` apareceria duplicado."""
    client.force_login(requisitante)

    resposta = client.get(reverse("catalogo:consulta"), {"codigo": "abc"})

    assert resposta.status_code == 200
    assert "HX-Reswap" not in resposta.headers
    conteudo = resposta.content.decode("utf-8")
    assert conteudo.count('id="campo-codigo"') == 1
    assert "hx-swap-oob" not in conteudo
    assert 'data-estado="codigo-invalido"' in conteudo


def test_codigo_valido_via_htmx_nao_define_hx_reswap_e_reseta_o_campo(
    client, requisitante, criar_material
):
    """Uma consulta válida por HTMX segue trocando `#resultados-consulta`
    normalmente (sem `HX-Reswap`) e também sincroniza `#campo-codigo` de
    volta ao estado normal — limpando um erro deixado por uma tentativa
    anterior."""
    criar_material(cadpro="000.008.001", descricao="Consulta válida via HTMX")

    client.force_login(requisitante)
    resposta = client.get(
        reverse("catalogo:consulta"),
        {"codigo": "000.008.001"},
        HTTP_HX_REQUEST="true",
    )

    assert resposta.status_code == 200
    assert "HX-Reswap" not in resposta.headers
    conteudo = resposta.content.decode("utf-8")
    assert 'id="campo-codigo"' in conteudo
    assert 'hx-swap-oob="true"' in conteudo
    assert "field-has-error" not in conteudo
    assert "000.008.001" in conteudo
