"""Testes da consulta do catálogo (T030 — US2, `PERM-MATERIAL-VIEW`).

TDD: escrito antes de `ConsultaCatalogoForm`, `ConsultaCatalogoView`, da rota
`catalogo:consulta` e do template `catalogo/consulta.html` (T032–T035,
`tasks.md`; o fragmento HTMX era originalmente um template próprio,
`catalogo/_resultados_consulta.html` — desde o refactor de partials, Django
6, é o partial `resultados_consulta`, declarado dentro do próprio
`consulta.html`). Este arquivo falha por inteiro até essas peças existirem
(`NoReverseMatch`/`ImportError`, conforme a chamada) — esperado.

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


def _bulk_criar_muitos_materiais(execucao, quantidade, *, grupo_inicial):
    """Como `_bulk_criar_materiais`, mas varia os dois primeiros segmentos do
    CADPRO (formato fixo `XXX.YYY.ZZZ`, no máximo 999 por segmento) — só
    `_bulk_criar_materiais` (um segmento fixo em "000") não alcança mais de
    1000 materiais sem estourar `varchar(11)`. Usada só pelo teste do
    separador de milhar (revisão do gate visual, achado "Mundo real",
    2026-09-22), que precisa de mais de 999 materiais para exercitar
    "1.234" em vez de "1234"."""
    materiais = []
    grupo = grupo_inicial
    indice = 0
    while indice < quantidade:
        subgrupo = 0
        while subgrupo < 1000 and indice < quantidade:
            materiais.append(
                Material(
                    cadpro=f"{grupo:03d}.{subgrupo:03d}.001",
                    descricao=f"Material milhar {indice}",
                    descricao_busca=normalizar_para_busca(f"Material milhar {indice}"),
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
            )
            subgrupo += 1
            indice += 1
        grupo += 1
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
# Ordenação (FR-042a, emenda de 2026-09-22)
# ---------------------------------------------------------------------------


def _posicoes(conteudo, codigos):
    return [conteudo.index(codigo) for codigo in codigos]


@pytest.mark.parametrize("ordem_param, decrescente", [("cadpro", False), ("-cadpro", True)])
def test_ordenacao_por_cadpro(client, requisitante, criar_material, ordem_param, decrescente):
    criar_material(cadpro="000.009.001", descricao="A")
    criar_material(cadpro="000.009.003", descricao="B")
    criar_material(cadpro="000.009.002", descricao="C")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"ordem": ordem_param})

    assert resposta.status_code == 200
    assert resposta.context["ordem"] == ordem_param
    codigos = ["000.009.001", "000.009.002", "000.009.003"]
    if decrescente:
        codigos = list(reversed(codigos))
    posicoes = _posicoes(resposta.content.decode("utf-8"), codigos)
    assert posicoes == sorted(posicoes)


@pytest.mark.parametrize("ordem_param, decrescente", [("descricao", False), ("-descricao", True)])
def test_ordenacao_por_descricao(client, requisitante, criar_material, ordem_param, decrescente):
    criar_material(cadpro="000.010.001", descricao="Zebra")
    criar_material(cadpro="000.010.002", descricao="Abacate")
    criar_material(cadpro="000.010.003", descricao="Manga")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"ordem": ordem_param})

    codigos = ["000.010.002", "000.010.003", "000.010.001"]  # Abacate, Manga, Zebra
    if decrescente:
        codigos = list(reversed(codigos))
    posicoes = _posicoes(resposta.content.decode("utf-8"), codigos)
    assert posicoes == sorted(posicoes)


def test_ordenacao_por_descricao_ignora_acento_e_maiuscula(client, requisitante, criar_material):
    """A ordenação por descrição usa `descricao_busca` (normalizado, sem
    acento e em minúsculas): uma descrição acentuada/maiúscula ordena como se
    já estivesse normalizada."""
    criar_material(cadpro="000.011.001", descricao="Árvore")
    criar_material(cadpro="000.011.002", descricao="banana")
    criar_material(cadpro="000.011.003", descricao="Cachorro")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"ordem": "descricao"})

    posicoes = _posicoes(
        resposta.content.decode("utf-8"),
        ["000.011.001", "000.011.002", "000.011.003"],
    )
    assert posicoes == sorted(posicoes)


@pytest.mark.parametrize("ordem_param, decrescente", [("unidade", False), ("-unidade", True)])
def test_ordenacao_por_unidade(client, requisitante, criar_material, ordem_param, decrescente):
    criar_material(cadpro="000.012.001", descricao="X", unidade="UN")
    criar_material(cadpro="000.012.002", descricao="Y", unidade="KG")
    criar_material(cadpro="000.012.003", descricao="Z", unidade="MT")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"ordem": ordem_param})

    codigos = ["000.012.002", "000.012.003", "000.012.001"]  # KG, MT, UN
    if decrescente:
        codigos = list(reversed(codigos))
    posicoes = _posicoes(resposta.content.decode("utf-8"), codigos)
    assert posicoes == sorted(posicoes)


@pytest.mark.parametrize(
    "ordem_param, decrescente", [("classificacao", False), ("-classificacao", True)]
)
def test_ordenacao_por_classificacao(
    client, requisitante, criar_material, ordem_param, decrescente
):
    """Classificação ordena por (nome do grupo, nome do subgrupo) juntos; em
    decrescente os dois campos invertem como uma única ordenação lógica."""
    criar_material(
        cadpro="000.013.001", descricao="X", nome_grupo="Eletrico", nome_subgrupo="Fios"
    )
    criar_material(
        cadpro="000.013.002", descricao="Y", nome_grupo="Eletrico", nome_subgrupo="Cabos"
    )
    criar_material(
        cadpro="000.013.003", descricao="Z", nome_grupo="Hidraulico", nome_subgrupo="Canos"
    )

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"ordem": ordem_param})

    # Eletrico/Cabos, Eletrico/Fios, Hidraulico/Canos
    codigos = ["000.013.002", "000.013.001", "000.013.003"]
    if decrescente:
        codigos = list(reversed(codigos))
    posicoes = _posicoes(resposta.content.decode("utf-8"), codigos)
    assert posicoes == sorted(posicoes)


@pytest.mark.parametrize("ordem_param, decrescente", [("saldo", False), ("-saldo", True)])
def test_ordenacao_por_saldo(client, requisitante, criar_material, ordem_param, decrescente):
    criar_material(cadpro="000.014.001", descricao="X", saldo=Decimal("30.000"))
    criar_material(cadpro="000.014.002", descricao="Y", saldo=Decimal("10.000"))
    criar_material(cadpro="000.014.003", descricao="Z", saldo=Decimal("20.000"))

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"ordem": ordem_param})

    codigos = ["000.014.002", "000.014.003", "000.014.001"]  # 10, 20, 30
    if decrescente:
        codigos = list(reversed(codigos))
    posicoes = _posicoes(resposta.content.decode("utf-8"), codigos)
    assert posicoes == sorted(posicoes)


def test_ordenacao_desempata_por_cadpro_estavel_entre_paginas(client, requisitante, execucao):
    """Materiais empatados na coluna ordenada (mesma `unidade` para todos)
    precisam ficar em ordem de `cadpro` — sem desempate estável, a paginação
    de um campo com muitos empates poderia repetir ou pular registros entre
    páginas (FR-042a)."""
    materiais = [
        Material(
            cadpro=f"600.000.{indice:03d}",
            descricao=f"Empate {indice}",
            descricao_busca=normalizar_para_busca(f"Empate {indice}"),
            unidade="UN",  # mesmo valor para todos: força o desempate
            detalhamento="",
            grupo="",
            subgrupo="",
            nome_grupo="",
            nome_subgrupo="",
            saldo=Decimal("1.000"),
            saldo_inicial=Decimal("1.000"),
            execucao_origem=execucao,
        )
        for indice in range(60)
    ]
    Material.objects.bulk_create(materiais)

    client.force_login(requisitante)
    url = reverse("catalogo:consulta")
    resposta_pagina_1 = client.get(url, {"ordem": "unidade"})
    resposta_pagina_2 = client.get(url, {"ordem": "unidade", "pagina": "2"})

    cadpros_pagina_1 = [material.cadpro for material in resposta_pagina_1.context["pagina"]]
    cadpros_pagina_2 = [material.cadpro for material in resposta_pagina_2.context["pagina"]]

    esperados = [f"600.000.{indice:03d}" for indice in range(60)]
    assert cadpros_pagina_1 == esperados[:50]
    assert cadpros_pagina_2 == esperados[50:]


@pytest.mark.parametrize("ordem_invalida", ["senha", "--saldo", "descricao_busca"])
def test_ordem_desconhecida_ou_injecao_cai_no_padrao_sem_erro(
    client, requisitante, criar_material, ordem_invalida
):
    """FR-042a: valor de ordenação desconhecido é ignorado e a ordem padrão
    (`cadpro` crescente) é usada, sem erro — nem o nome real de um campo
    (`descricao_busca`) nem uma tentativa de injeção (`--saldo`) chegam a
    `order_by`."""
    criar_material(cadpro="000.015.003", descricao="C")
    criar_material(cadpro="000.015.001", descricao="A")
    criar_material(cadpro="000.015.002", descricao="B")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"ordem": ordem_invalida})

    assert resposta.status_code == 200
    assert resposta.context["ordem"] == "cadpro"
    posicoes = _posicoes(
        resposta.content.decode("utf-8"),
        ["000.015.001", "000.015.002", "000.015.003"],
    )
    assert posicoes == sorted(posicoes)


def test_ordem_ausente_expoe_ordem_padrao_no_contexto(client, requisitante, criar_material):
    criar_material(cadpro="000.016.001", descricao="Sem ordenação explícita")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"))

    assert resposta.context["ordem"] == "cadpro"


def test_ordem_efetiva_exposta_mesmo_com_codigo_invalido(client, requisitante):
    """FR-042a: mesmo sem nenhuma query (`codigo_invalido`), a ordem efetiva
    continua no contexto, para o cabeçalho da tabela permanecer coerente."""
    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"codigo": "abc", "ordem": "-saldo"})

    assert resposta.status_code == 200
    assert resposta.context["ordem"] == "-saldo"
    assert resposta.context["pagina"] is None


def test_ordenacao_combina_com_filtro_de_descricao(client, requisitante, criar_material):
    """FR-042a: a ordenação se combina com os filtros — só os materiais
    filtrados aparecem, na ordem escolhida."""
    criar_material(cadpro="000.017.001", descricao="Válvula Grande", saldo=Decimal("30.000"))
    criar_material(cadpro="000.017.002", descricao="Válvula Pequena", saldo=Decimal("10.000"))
    criar_material(cadpro="000.017.003", descricao="Parafuso", saldo=Decimal("5.000"))

    client.force_login(requisitante)
    resposta = client.get(
        reverse("catalogo:consulta"), {"descricao": "valvula", "ordem": "-saldo"}
    )

    conteudo = resposta.content.decode("utf-8")
    assert "000.017.003" not in conteudo
    posicoes = _posicoes(conteudo, ["000.017.001", "000.017.002"])
    assert posicoes == sorted(posicoes)


def test_fragmento_htmx_respeita_a_ordem(client, requisitante, criar_material):
    criar_material(cadpro="000.018.002", descricao="B", saldo=Decimal("20.000"))
    criar_material(cadpro="000.018.001", descricao="A", saldo=Decimal("10.000"))

    client.force_login(requisitante)
    resposta = client.get(
        reverse("catalogo:consulta"), {"ordem": "-saldo"}, HTTP_HX_REQUEST="true"
    )

    assert resposta.status_code == 200
    nomes_templates = [template.name for template in resposta.templates if template.name]
    assert "resultados_consulta" in nomes_templates
    posicoes = _posicoes(
        resposta.content.decode("utf-8"), ["000.018.002", "000.018.001"]
    )
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
    assert "resultados_consulta" in nomes_templates
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
    `consulta.html`: a cópia OOB de `campo_codigo`, emitida pelo partial
    `resultados_consulta`, não pode ser emitida de novo, ou
    `id="campo-codigo"` apareceria duplicado."""
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


# ---------------------------------------------------------------------------
# Cabeçalho ordenável (frontend, FR-042a, emenda de 2026-09-22)
# ---------------------------------------------------------------------------


def _th(conteudo, texto_visivel):
    """Extrai o bloco `<th ...>...</th>` que contém `texto_visivel`, para
    inspecionar seus atributos (`aria-sort`) sem depender de posição/índice
    na string. Os blocos `<th>` da tabela não são aninhados, então cada
    correspondência não-gulosa de `<th\\b.*?</th>` já para no próprio
    fechamento — filtrar pelo texto depois evita capturar vários cabeçalhos
    de uma vez (o que aconteceria se o texto fosse exigido dentro do próprio
    padrão de busca)."""
    for bloco in re.findall(r"<th\b.*?</th>", conteudo, re.S):
        if texto_visivel in bloco:
            return bloco
    raise AssertionError(f"cabeçalho com {texto_visivel!r} não encontrado")


def test_cabecalho_saldo_com_ordem_padrao_nao_tem_aria_sort(
    client, requisitante, criar_material
):
    criar_material(cadpro="000.020.001", descricao="X")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"))

    th_saldo = _th(resposta.content.decode("utf-8"), "Saldo")
    assert "aria-sort" not in th_saldo


def test_cabecalho_saldo_crescente_marca_aria_sort_ascending(
    client, requisitante, criar_material
):
    criar_material(cadpro="000.020.002", descricao="X")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"ordem": "saldo"})

    th_saldo = _th(resposta.content.decode("utf-8"), "Saldo")
    assert 'aria-sort="ascending"' in th_saldo


def test_cabecalho_saldo_decrescente_marca_aria_sort_descending(
    client, requisitante, criar_material
):
    criar_material(cadpro="000.020.003", descricao="X")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"ordem": "-saldo"})

    th_saldo = _th(resposta.content.decode("utf-8"), "Saldo")
    assert 'aria-sort="descending"' in th_saldo


def test_detalhamento_nao_e_ordenavel(client, requisitante, criar_material):
    """Detalhamento não está em `ConsultaCatalogoView.colunas_ordenacao`
    (`catalogo/views.py`, `OrdenacaoMixin`, `catalogo/ordenacao.py`) e
    continua um `<th>` simples, sem link nem `aria-sort`."""
    criar_material(cadpro="000.020.004", descricao="X")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"))

    th_detalhamento = _th(resposta.content.decode("utf-8"), "Detalhamento")
    assert "<a" not in th_detalhamento
    assert "aria-sort" not in th_detalhamento


def test_link_de_ordenacao_preserva_filtro_e_nao_carrega_pagina(
    client, requisitante, criar_material
):
    """`querystring_ordenacao` preserva os demais parâmetros (aqui,
    `descricao`) e remove `pagina` — mudar a ordem volta à primeira página
    (FR-042a)."""
    criar_material(cadpro="000.021.001", descricao="Válvula de Registro")

    client.force_login(requisitante)
    resposta = client.get(
        reverse("catalogo:consulta"),
        {"descricao": "valvula", "pagina": "2"},
    )

    conteudo = resposta.content.decode("utf-8")
    th_saldo = _th(conteudo, "Saldo")
    link_saldo = re.search(r'href="([^"]*)"', th_saldo).group(1)
    assert "descricao=valvula" in link_saldo
    assert "pagina=" not in link_saldo
    assert "ordem=saldo" in link_saldo


def test_link_de_ordenacao_alterna_direcao_da_coluna_vigente(
    client, requisitante, criar_material
):
    criar_material(cadpro="000.021.002", descricao="X")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"ordem": "saldo"})

    th_saldo = _th(resposta.content.decode("utf-8"), "Saldo")
    link_saldo = re.search(r'href="([^"]*)"', th_saldo).group(1)
    assert "ordem=-saldo" in link_saldo
    assert 'aria-label="Ordenar por saldo, decrescente"' in th_saldo


def test_link_de_ordenacao_tem_hx_get_para_o_mesmo_alvo_dos_resultados(
    client, requisitante, criar_material
):
    """O rótulo do cabeçalho é navegação real (funciona sem JS) e também
    dispara a mesma troca parcial HTMX que filtros e paginação usam."""
    criar_material(cadpro="000.021.003", descricao="X")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"))

    th_cadpro = _th(resposta.content.decode("utf-8"), "Código (CADPRO)")
    assert 'hx-target="#resultados-consulta"' in th_cadpro
    assert 'hx-push-url="true"' in th_cadpro
    assert 'hx-indicator="#resultados-indicador"' in th_cadpro


# ---------------------------------------------------------------------------
# Campo oculto de ordem (frontend, FR-042a): preserva a ordem numa nova busca
# ---------------------------------------------------------------------------


def test_pagina_inteira_tem_campo_oculto_com_a_ordem_atual(
    client, requisitante, criar_material
):
    criar_material(cadpro="000.022.001", descricao="X")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"ordem": "-saldo"})

    conteudo = resposta.content.decode("utf-8")
    assert '<input type="hidden" name="ordem" id="campo-ordem" value="-saldo">' in conteudo


def test_fragmento_htmx_emite_copia_oob_do_campo_de_ordem(
    client, requisitante, criar_material
):
    """O formulário de filtros fica fora de `#resultados-consulta`; uma
    troca de ordem pelo cabeçalho (dentro dessa região) só chega ao campo
    oculto do formulário via out-of-band swap."""
    criar_material(cadpro="000.022.002", descricao="X")

    client.force_login(requisitante)
    resposta = client.get(
        reverse("catalogo:consulta"), {"ordem": "-saldo"}, HTTP_HX_REQUEST="true"
    )

    conteudo = resposta.content.decode("utf-8")
    assert (
        '<input type="hidden" name="ordem" id="campo-ordem" value="-saldo" '
        'hx-swap-oob="true">' in conteudo
    )


def test_buscar_depois_de_reordenar_mantem_a_ordem(client, requisitante, criar_material):
    """Como o campo oculto `ordem` viaja dentro do `<form>` de filtros
    (`hx-get` no próprio `<form>`), uma nova busca preservando `ordem` no
    GET mantém a ordenação escolhida — sem exigir JS além de HTMX."""
    criar_material(cadpro="000.022.003", descricao="Válvula A", saldo=Decimal("30.000"))
    criar_material(cadpro="000.022.004", descricao="Válvula B", saldo=Decimal("10.000"))

    client.force_login(requisitante)
    resposta = client.get(
        reverse("catalogo:consulta"), {"descricao": "valvula", "ordem": "saldo"}
    )

    assert resposta.context["ordem"] == "saldo"
    conteudo = resposta.content.decode("utf-8")
    posicoes = _posicoes(conteudo, ["000.022.004", "000.022.003"])  # 10, 30
    assert posicoes == sorted(posicoes)


# ---------------------------------------------------------------------------
# Paginação numerada com reticências (frontend, FR-042b, emenda de 2026-09-22)
# ---------------------------------------------------------------------------


def test_paginacao_mostra_numeros_de_pagina(client, requisitante, execucao):
    _bulk_criar_materiais(execucao, 60, prefixo="800")  # 2 páginas

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"))

    conteudo = resposta.content.decode("utf-8")
    nav = re.search(r'<nav class="pagination".*?</nav>', conteudo, re.S).group()
    assert 'aria-label="Página 1"' in nav
    assert 'aria-label="Página 2"' in nav


def test_pagina_atual_e_span_nao_clicavel_com_aria_current(
    client, requisitante, execucao
):
    _bulk_criar_materiais(execucao, 60, prefixo="810")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"pagina": "2"})

    conteudo = resposta.content.decode("utf-8")
    nav = re.search(r'<nav class="pagination".*?</nav>', conteudo, re.S).group()
    assert (
        '<span id="pagina-pagina-2-larga" class="pagination-link pagination-link-current" '
        'aria-current="page" aria-label="Página 2" tabindex="-1">2</span>' in nav
    )
    # a página atual não é um link, em nenhuma das duas listas
    assert not re.search(r'<a\b[^>]*href="\?pagina=2"', nav)


def test_numero_de_pagina_e_pagina_atual_compartilham_id_para_restaurar_foco(
    client, requisitante, execucao
):
    """O htmx restaura o foco pelo `id`: o link da página 3 (ativado na página
    2) precisa ter o mesmo `id` do `<span>` atual da página 3 depois do swap,
    senão o foco de quem usa teclado cai no `<body>` (re-revisão, achado P3).
    Os sufixos por lista impedem `id` duplicado entre a larga e a compacta."""
    _bulk_criar_materiais(execucao, 250, prefixo="811")  # 5 páginas de 50

    client.force_login(requisitante)
    na_pagina_2 = client.get(reverse("catalogo:consulta"), {"pagina": "2"}).content.decode()
    na_pagina_3 = client.get(
        reverse("catalogo:consulta"), {"pagina": "3"}, HTTP_HX_REQUEST="true"
    ).content.decode()

    for lista in ("larga", "compacta"):
        assert re.search(rf'<a\s+id="pagina-pagina-3-{lista}"[^>]*href="\?pagina=3"', na_pagina_2)
        assert re.search(
            rf'<span id="pagina-pagina-3-{lista}"[^>]*aria-current="page"[^>]*tabindex="-1"',
            na_pagina_3,
        )
    ids = re.findall(r'id="(pagina-pagina-[^"]+)"', na_pagina_2)
    assert len(ids) == len(set(ids))


def test_paginacao_com_muitas_paginas_mostra_reticencia(client, requisitante, execucao):
    _bulk_criar_materiais(execucao, 550, prefixo="820")  # 11 páginas de 50

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"pagina": "5"})

    conteudo = resposta.content.decode("utf-8")
    nav = re.search(r'<nav class="pagination".*?</nav>', conteudo, re.S).group()
    assert '<span class="pagination-ellipsis" aria-hidden="true">…</span>' in nav
    # primeira e última página continuam acessíveis
    assert 'aria-label="Página 1"' in nav
    assert 'aria-label="Página 11"' in nav


def test_paginacao_numerada_preserva_filtros_e_ordem(client, requisitante, execucao):
    _bulk_criar_materiais(execucao, 60, prefixo="830")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"ordem": "-cadpro"})

    conteudo = resposta.content.decode("utf-8")
    nav = re.search(r'<nav class="pagination".*?</nav>', conteudo, re.S).group()
    link_pagina_2 = re.search(r'href="([^"]*pagina=2[^"]*)"', nav)
    assert link_pagina_2 is not None
    assert "ordem=-cadpro" in link_pagina_2.group(1)


# ---------------------------------------------------------------------------
# Revisão do gate visual da ordenação + paginação (2026-09-22):
# `.impeccable/critique/2026-09-22T16-05-45Z__mplates-catalogo-resultados-
# consulta-html-9b190d1c.md`, correções aprovadas pelo dono do produto.
# ---------------------------------------------------------------------------


def test_resumo_da_paginacao_usa_separador_de_milhar_e_plural_correto(
    client, requisitante, execucao
):
    """Achado "Mundo real": "3408 materials" não lia nem como número nem
    como português — separador de milhar + substantivo plural explícito
    (`rotulo_item_plural`), nunca `pluralize:"s"` sobre "material"."""
    _bulk_criar_muitos_materiais(execucao, 1234, grupo_inicial=700)

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"))

    conteudo = resposta.content.decode("utf-8")
    assert "1.234 materiais no total" in conteudo
    assert "1234 materials" not in conteudo
    assert "1234 materiais" not in conteudo


def test_resumo_da_paginacao_usa_singular_com_um_unico_resultado(
    client, requisitante, criar_material
):
    criar_material(cadpro="000.040.001", descricao="ItemUnicoDoResumo")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"descricao": "ItemUnicoDoResumo"})

    conteudo = resposta.content.decode("utf-8")
    assert "1 material no total" in conteudo
    assert "1 materiais" not in conteudo


def test_resumo_da_paginacao_diz_a_ordem_vigente(client, requisitante, criar_material):
    """Achado P1: a ordem vigente também aparece em texto no resumo — a
    coluna/seta do cabeçalho pode estar fora da tela (celular)."""
    criar_material(cadpro="000.040.002", descricao="X")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"ordem": "-saldo"})

    assert "· ordenado por saldo, decrescente" in resposta.content.decode("utf-8")


def test_resumo_da_paginacao_diz_a_ordem_padrao_sem_parametro(
    client, requisitante, criar_material
):
    criar_material(cadpro="000.040.003", descricao="X")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"))

    assert "· ordenado por código, crescente" in resposta.content.decode("utf-8")


def test_paginacao_com_pagina_unica_mostra_so_o_resumo(client, requisitante, criar_material):
    """Achado P3: com uma página só, "Anterior 1 Próxima" era ruído puro —
    o parcial passa a emitir só o resumo."""
    criar_material(cadpro="000.041.001", descricao="X")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"))

    conteudo = resposta.content.decode("utf-8")
    nav = re.search(r'<nav class="pagination".*?</nav>', conteudo, re.S).group()
    assert "pagination-list" not in nav
    assert ">Anterior<" not in nav
    assert ">Próxima<" not in nav


def test_paginacao_lista_compacta_usa_apenas_um_vizinho_de_cada_lado(
    client, requisitante, execucao
):
    """Achado P2: a lista compacta de celular (`on_each_side=1`) mostra
    menos páginas que a larga (`on_each_side=2`) — só um vizinho de cada
    lado da atual, para caber numa linha a 375px. As duas listas convivem no
    HTML (alternadas por media query, `static/css/components.css`); este
    teste garante que a compacta de fato tem menos itens, não que uma delas
    está com `display: none` (CSS não é exercitado por este teste)."""
    _bulk_criar_materiais(execucao, 550, prefixo="850")  # 11 páginas de 50

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"pagina": "5"})

    conteudo = resposta.content.decode("utf-8")
    assert "pagination-item-wide" in conteudo
    assert "pagination-item-compact" in conteudo

    blocos_compactos = re.findall(
        r'<li class="pagination-item-compact">.*?</li>', conteudo, re.S
    )
    texto_compacto = "".join(blocos_compactos)
    # on_each_side=1: só a página 4 e a 6 ao lado da 5ª — a 3 e a 7 (que a
    # lista larga, on_each_side=2, mostra) ficam de fora da compacta.
    assert 'aria-label="Página 4"' in texto_compacto
    assert 'aria-label="Página 6"' in texto_compacto
    assert 'aria-label="Página 3"' not in texto_compacto
    assert 'aria-label="Página 7"' not in texto_compacto


def test_indicador_de_ordenacao_marca_a_direcao_vigente(client, requisitante, criar_material):
    """Achado (glifos desalinhados): o indicador passa a ser um único SVG
    com classe de estado (`table-sort-indicator-asc`/`-desc`), nunca troca
    de glifo — este teste garante que a classe de estado corresponde à
    direção vigente, e que uma coluna não vigente não recebe nenhuma delas."""
    criar_material(cadpro="000.042.001", descricao="X")
    client.force_login(requisitante)

    resposta = client.get(reverse("catalogo:consulta"), {"ordem": "saldo"})
    conteudo = resposta.content.decode("utf-8")
    th_saldo = _th(conteudo, "Saldo")
    assert "table-sort-indicator-asc" in th_saldo
    assert "table-sort-indicator-desc" not in th_saldo
    th_cadpro = _th(conteudo, "Código (CADPRO)")
    assert "table-sort-indicator-asc" not in th_cadpro
    assert "table-sort-indicator-desc" not in th_cadpro

    resposta = client.get(reverse("catalogo:consulta"), {"ordem": "-saldo"})
    th_saldo = _th(resposta.content.decode("utf-8"), "Saldo")
    assert "table-sort-indicator-desc" in th_saldo
    assert "table-sort-indicator-asc" not in th_saldo


def test_pagina_inteira_tem_anuncio_da_ordem_vigente_para_leitor_de_tela(
    client, requisitante, criar_material
):
    """Achado P1: um anúncio estável (`role="status"`), fora de
    `#resultados-consulta`, diz a ordem vigente a quem usa leitor de tela."""
    criar_material(cadpro="000.043.001", descricao="X")

    client.force_login(requisitante)
    resposta = client.get(reverse("catalogo:consulta"), {"ordem": "-saldo"})

    conteudo = resposta.content.decode("utf-8")
    assert (
        '<p id="resultados-anuncio" class="visually-hidden" role="status">'
        "Ordenado por saldo, decrescente.</p>" in conteudo
    )


def test_fragmento_htmx_emite_copia_oob_do_anuncio_de_ordem(
    client, requisitante, criar_material
):
    """O anúncio fica fora de `#resultados-consulta` (região trocada por
    inteiro via HTMX) — por isso, como `#campo-ordem`, precisa de uma cópia
    out-of-band para acompanhar uma troca de ordem pelo cabeçalho."""
    criar_material(cadpro="000.043.002", descricao="X")

    client.force_login(requisitante)
    resposta = client.get(
        reverse("catalogo:consulta"), {"ordem": "-saldo"}, HTTP_HX_REQUEST="true"
    )

    conteudo = resposta.content.decode("utf-8")
    assert (
        '<p id="resultados-anuncio" hx-swap-oob="innerHTML">'
        "Ordenado por saldo, decrescente.</p>" in conteudo
    )
