"""Testes da consulta de fornecedores (T020 — US2, `PERM-SUPPLIER-VIEW`).

TDD: escrito antes de `ConsultaFornecedoresForm`, `ConsultaFornecedoresView`,
da rota `fornecedores:consulta` e do template `fornecedores/consulta.html`
(T022–T024) existirem — `reverse()` fica dentro do corpo de cada teste, para
que a ausência da rota derrube só o teste que a usa (`NoReverseMatch`), não
a coleta do arquivo inteiro (mesma convenção de
`tests/test_fornecedores_permissoes.py`).

Cobre FR-027–FR-029 e `contracts/rotas-e-autorizacao.md` → "Consulta". A
matriz completa de autorização (`PERM-SUPPLIER-VIEW`, `INV-AUTH-001`) é
`tests/test_fornecedores_permissoes.py` (T021, seção `ROTAS_CONSULTA`); aqui
a rota é sempre exercitada já autenticada com `funcionario_almoxarifado`.

Fornecedores são criados diretamente pelo ORM (`criar_fornecedor` abaixo),
nunca por `fornecedores.importacao.aplicar_plano` fora de teste — não é o
caminho de produto (`INV-SUPPLIER-003`, ver
`tests/test_fornecedores_sem_criacao_manual.py`, T031); serve só para popular
o cadastro para os cenários de busca.

Interfaces fixadas por este arquivo (nenhum contrato as fixa) — o
implementador de T022–T024 precisa seguir:
- **Fragmento HTMX**: mesmo padrão da 001 — partial `resultados_consulta`
  dentro de `fornecedores/consulta.html` (`resposta.templates` inclui um
  template cujo `.name == "resultados_consulta"`; a página inteira NÃO
  aparece nessa lista quando `HX-Request` está presente).
- **Estado vazio**: elemento com `data-estado="vazio"` na região de
  resultados — mesmo marcador da consulta do catálogo.
- **`codigo` fora de `[0-9]+`**: elemento com `data-estado="codigo-invalido"`,
  sem nenhuma consulta a `fornecedores_fornecedor` (`_contar_queries_
  fornecedor`, abaixo). Contexto: `codigo_invalido=True`.
- **`documento` com menos de 3 dígitos**: elemento com
  `data-estado="documento-invalido"`, sem consulta. Contexto:
  `documento_invalido=True`. O contrato não fixa o texto da mensagem — este
  arquivo verifica só que HÁ um erro no campo (`data-estado`/contexto), nunca
  um texto inventado.

Seções acrescentadas pelo `test-engineer` (alinhamento de UX, Fase B), no
molde de `tests/test_catalogo_consulta.py`: "Falha de uma troca HTMX"
(`interface/templates/interface/_consulta_falha.html`, hooks `hx-on`, meta
`htmx-config`), "Validação via HTMX" (OOB dos campos `campo-codigo`/
`campo-documento`, `HX-Reswap`/`HX-Push-Url`) e "Preservação de query
params" (ordenação volta à página 1 preservando filtros; paginação preserva
filtro e ordem).
"""

import json
import re
import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from catalogo.leitura_scpi import normalizar_para_busca
from fornecedores.models import ExecucaoImportacaoFornecedores, Fornecedor

pytestmark = pytest.mark.django_db

SHA256_FAKE = "0" * 64


def _contar_queries_fornecedor(queries_capturadas):
    return sum(1 for query in queries_capturadas if "fornecedores_fornecedor" in query["sql"])


@pytest.fixture
def execucao(chefe_almoxarifado):
    """`ExecucaoImportacaoFornecedores` mínima só para satisfazer o FK
    obrigatório de `Fornecedor.execucao_origem` — não é caminho de produto
    (só `aplicar_plano` cria `Fornecedor`/`ExecucaoImportacaoFornecedores`,
    ver docstring do módulo)."""
    return ExecucaoImportacaoFornecedores.objects.create(
        token_previa=uuid.uuid4(),
        executada_por=chefe_almoxarifado,
        concluida_em=timezone.now(),
        nome_arquivo="fornecedores.csv",
        tamanho_arquivo=1024,
        sha256_arquivo=SHA256_FAKE,
        total_recebidos=1,
        total_inseridos=1,
        total_atualizados=0,
        total_atualizados_com_alteracao=0,
        total_rejeitados=0,
        total_ausentes_no_arquivo=0,
    )


@pytest.fixture
def criar_fornecedor(execucao):
    contador = {"valor": 0}

    def _criar_fornecedor(
        *,
        codif=None,
        nome="Fornecedor Padrão",
        nome_fantasia="",
        documento="",
        tipo="01",
        bloqueado=False,
        motivo_bloqueio="",
        tipo_bloqueio="",
    ):
        contador["valor"] += 1
        if codif is None:
            codif = str(900_000 + contador["valor"])
        from fornecedores.leitura_fornecedores import somente_digitos

        return Fornecedor.objects.create(
            codif=codif,
            nome=nome,
            nome_fantasia=nome_fantasia,
            documento=documento,
            documento_digitos=somente_digitos(documento),
            tipo=tipo,
            bloqueado=bloqueado,
            motivo_bloqueio=motivo_bloqueio,
            tipo_bloqueio=tipo_bloqueio,
            nome_busca=normalizar_para_busca(f"{nome} {nome_fantasia}"),
            execucao_origem=execucao,
        )

    return _criar_fornecedor


def _bulk_criar_fornecedores(execucao, quantidade, *, prefixo):
    fornecedores = [
        Fornecedor(
            codif=f"{prefixo}{indice:04d}",
            nome=f"Fornecedor em lote {indice}",
            nome_fantasia="",
            documento="",
            documento_digitos="",
            tipo="01",
            bloqueado=False,
            motivo_bloqueio="",
            tipo_bloqueio="",
            nome_busca=normalizar_para_busca(f"Fornecedor em lote {indice}"),
            execucao_origem=execucao,
        )
        for indice in range(quantidade)
    ]
    Fornecedor.objects.bulk_create(fornecedores)


# ---------------------------------------------------------------------------
# Código exato (FR-027, INV-SUPPLIER-001).
# ---------------------------------------------------------------------------


def test_codigo_exato_retorna_o_fornecedor(client, funcionario_almoxarifado, criar_fornecedor):
    criar_fornecedor(codif="123456", nome="Fornecedor Alvo")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"), {"codigo": "123456"})

    assert resposta.status_code == 200
    assert "Fornecedor Alvo" in resposta.content.decode("utf-8")


def test_codigo_nao_completa_zeros_a_esquerda(client, funcionario_almoxarifado, criar_fornecedor):
    """`INV-SUPPLIER-001`: `codigo=7` não pode encontrar `codif="007"`, nem
    o contrário — cada um é um fornecedor distinto."""
    criar_fornecedor(codif="007", nome="Fornecedor Com Zeros")
    criar_fornecedor(codif="7", nome="Fornecedor Sem Zeros")

    client.force_login(funcionario_almoxarifado)

    resposta_com_zeros = client.get(reverse("fornecedores:consulta"), {"codigo": "007"})
    conteudo_com_zeros = resposta_com_zeros.content.decode("utf-8")
    assert "Fornecedor Com Zeros" in conteudo_com_zeros
    assert "Fornecedor Sem Zeros" not in conteudo_com_zeros

    resposta_sem_zeros = client.get(reverse("fornecedores:consulta"), {"codigo": "7"})
    conteudo_sem_zeros = resposta_sem_zeros.content.decode("utf-8")
    assert "Fornecedor Sem Zeros" in conteudo_sem_zeros
    assert "Fornecedor Com Zeros" not in conteudo_sem_zeros


def test_codigo_com_espacos_nas_bordas_e_aparado(
    client, funcionario_almoxarifado, criar_fornecedor
):
    criar_fornecedor(codif="555", nome="Fornecedor Aparado")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"), {"codigo": "  555  "})

    assert resposta.status_code == 200
    conteudo = resposta.content.decode("utf-8")
    assert "Fornecedor Aparado" in conteudo
    assert 'data-estado="codigo-invalido"' not in conteudo


@pytest.mark.parametrize("codigo_invalido", ["12A", "٣", "12.3", "-5"])
def test_codigo_fora_do_formato_nao_executa_consulta_e_mostra_estado_de_validacao(
    client, funcionario_almoxarifado, codigo_invalido
):
    client.force_login(funcionario_almoxarifado)

    with CaptureQueriesContext(connection) as capturadas:
        resposta = client.get(reverse("fornecedores:consulta"), {"codigo": codigo_invalido})

    assert resposta.status_code == 200
    assert _contar_queries_fornecedor(capturadas.captured_queries) == 0
    conteudo = resposta.content.decode("utf-8")
    assert 'data-estado="codigo-invalido"' in conteudo
    assert resposta.context["codigo_invalido"] is True


# ---------------------------------------------------------------------------
# Nome/nome fantasia (FR-027).
# ---------------------------------------------------------------------------


def test_busca_por_nome_sem_acento_e_caixa_encontra_o_fornecedor(
    client, funcionario_almoxarifado, criar_fornecedor
):
    criar_fornecedor(codif="200001", nome="Fornecedor Válvulas e Conexões")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"), {"nome": "valvulas conexoes"})

    assert resposta.status_code == 200
    assert "200001" in resposta.content.decode("utf-8")


@pytest.mark.parametrize(
    "termo", ["valvulas conexoes", "conexoes valvulas", "valv conex"],
    ids=["ordem_normal", "ordem_invertida", "parcial"],
)
def test_busca_por_nome_em_qualquer_ordem_e_parcial(
    client, funcionario_almoxarifado, criar_fornecedor, termo
):
    criar_fornecedor(codif="200002", nome="Fornecedor Válvulas e Conexões")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"), {"nome": termo})

    assert "200002" in resposta.content.decode("utf-8")


def test_busca_por_nome_exige_todas_as_palavras(client, funcionario_almoxarifado, criar_fornecedor):
    criar_fornecedor(codif="200003", nome="Fornecedor Válvulas")
    criar_fornecedor(codif="200004", nome="Fornecedor Conexões")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"), {"nome": "valvulas conexoes"})

    conteudo = resposta.content.decode("utf-8")
    assert "200003" not in conteudo
    assert "200004" not in conteudo


def test_busca_por_nome_encontra_palavra_que_so_existe_no_nome_fantasia(
    client, funcionario_almoxarifado, criar_fornecedor
):
    criar_fornecedor(codif="200005", nome="Fornecedor Comercio Ltda", nome_fantasia="Casa Do Cano")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"), {"nome": "cano"})

    assert "200005" in resposta.content.decode("utf-8")


def test_nomes_iguais_aparecem_como_dois_fornecedores_distintos(
    client, funcionario_almoxarifado, criar_fornecedor
):
    criar_fornecedor(codif="200006", nome="Fornecedor Padrão")
    criar_fornecedor(codif="200007", nome="Fornecedor Padrão")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"), {"nome": "Fornecedor Padrão"})

    conteudo = resposta.content.decode("utf-8")
    assert "200006" in conteudo
    assert "200007" in conteudo


# ---------------------------------------------------------------------------
# Documento (FR-027, SC-007) — formatado e só dígitos encontram o mesmo
# resultado; menos de 3 dígitos é erro de validação.
# ---------------------------------------------------------------------------


def test_documento_formatado_e_so_digitos_encontram_o_mesmo_fornecedor(
    client, funcionario_almoxarifado, criar_fornecedor
):
    criar_fornecedor(codif="300001", nome="Fornecedor Documentado", documento="62.011.929/0001-73")

    client.force_login(funcionario_almoxarifado)

    resposta_formatado = client.get(
        reverse("fornecedores:consulta"), {"documento": "62.011.929/0001-73"}
    )
    resposta_so_digitos = client.get(
        reverse("fornecedores:consulta"), {"documento": "62011929000173"}
    )

    assert "300001" in resposta_formatado.content.decode("utf-8")
    assert "300001" in resposta_so_digitos.content.decode("utf-8")


def test_documento_com_menos_de_3_digitos_e_erro_de_validacao_sem_consulta(
    client, funcionario_almoxarifado, criar_fornecedor
):
    criar_fornecedor(codif="300002", nome="Fornecedor Qualquer", documento="12")

    client.force_login(funcionario_almoxarifado)
    with CaptureQueriesContext(connection) as capturadas:
        resposta = client.get(reverse("fornecedores:consulta"), {"documento": "12"})

    assert resposta.status_code == 200
    assert _contar_queries_fornecedor(capturadas.captured_queries) == 0
    conteudo = resposta.content.decode("utf-8")
    assert 'data-estado="documento-invalido"' in conteudo
    assert resposta.context["documento_invalido"] is True


def test_documento_vazio_nao_e_erro_e_nao_filtra(
    client, funcionario_almoxarifado, criar_fornecedor
):
    """Campo vazio não é "menos de 3 dígitos" — é ausência de filtro."""
    criar_fornecedor(codif="300003", nome="Fornecedor Sem Filtro De Documento")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"), {"documento": ""})

    assert resposta.status_code == 200
    conteudo = resposta.content.decode("utf-8")
    assert 'data-estado="documento-invalido"' not in conteudo
    assert "300003" in conteudo


# ---------------------------------------------------------------------------
# Interseção de filtros (E).
# ---------------------------------------------------------------------------


def test_intersecao_de_codigo_e_nome_restringe_ao_fornecedor_correspondente(
    client, funcionario_almoxarifado, criar_fornecedor
):
    criar_fornecedor(codif="400001", nome="Fornecedor Hidráulico")
    criar_fornecedor(codif="400002", nome="Fornecedor Hidráulico")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(
        reverse("fornecedores:consulta"), {"codigo": "400001", "nome": "hidraulico"}
    )

    conteudo = resposta.content.decode("utf-8")
    assert "400001" in conteudo
    assert "400002" not in conteudo


# ---------------------------------------------------------------------------
# Bloqueado: situação e motivo visíveis (FR-028).
# ---------------------------------------------------------------------------


def test_fornecedor_bloqueado_mostra_situacao_e_motivo(
    client, funcionario_almoxarifado, criar_fornecedor
):
    criar_fornecedor(
        codif="500001",
        nome="Fornecedor Bloqueado",
        bloqueado=True,
        motivo_bloqueio="FORNECEDOR NAO PODE SER UTILIZADO",
        tipo_bloqueio="MUDANCA DE CNPJ",
    )

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"), {"codigo": "500001"})

    conteudo = resposta.content.decode("utf-8")
    assert "500001" in conteudo
    assert "FORNECEDOR NAO PODE SER UTILIZADO" in conteudo


# ---------------------------------------------------------------------------
# Ausência de resultados (FR-029).
# ---------------------------------------------------------------------------


def test_ausencia_de_resultados_mostra_estado_explicito(
    client, funcionario_almoxarifado, criar_fornecedor
):
    criar_fornecedor(codif="600001", nome="Existe No Cadastro")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"), {"nome": "NaoExisteNoCadastro"})

    assert resposta.status_code == 200
    conteudo = resposta.content.decode("utf-8")
    assert 'data-estado="vazio"' in conteudo
    assert "600001" not in conteudo


def test_sem_filtro_lista_todo_o_cadastro(client, funcionario_almoxarifado, criar_fornecedor):
    criar_fornecedor(codif="700001", nome="A")
    criar_fornecedor(codif="700002", nome="B")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"))

    conteudo = resposta.content.decode("utf-8")
    assert "700001" in conteudo
    assert "700002" in conteudo


# ---------------------------------------------------------------------------
# Ordenação (contrato: codigo, nome, documento; padrão nome, desempate
# codif) e paginação (50/página).
# ---------------------------------------------------------------------------


def test_ordem_padrao_e_por_nome_com_desempate_por_codigo(
    client, funcionario_almoxarifado, criar_fornecedor
):
    criar_fornecedor(codif="800003", nome="Zebra")
    criar_fornecedor(codif="800001", nome="Abacate")
    criar_fornecedor(codif="800002", nome="Abacate")  # empata em nome com 800001

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"))

    conteudo = resposta.content.decode("utf-8")
    posicoes = [conteudo.index(codigo) for codigo in ("800001", "800002", "800003")]
    assert posicoes == sorted(posicoes)


@pytest.mark.parametrize("ordem_param, decrescente", [("codigo", False), ("-codigo", True)])
def test_ordenacao_por_codigo(
    client, funcionario_almoxarifado, criar_fornecedor, ordem_param, decrescente
):
    criar_fornecedor(codif="810001", nome="C")
    criar_fornecedor(codif="810003", nome="A")
    criar_fornecedor(codif="810002", nome="B")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"), {"ordem": ordem_param})

    codigos = ["810001", "810002", "810003"]
    if decrescente:
        codigos = list(reversed(codigos))
    conteudo = resposta.content.decode("utf-8")
    posicoes = [conteudo.index(c) for c in codigos]
    assert posicoes == sorted(posicoes)


@pytest.mark.parametrize("ordem_param, decrescente", [("codigo", False), ("-codigo", True)])
def test_ordenacao_por_codigo_usa_comprimento_antes_do_valor_textual(
    client, funcionario_almoxarifado, criar_fornecedor, ordem_param, decrescente
):
    """`INV-SUPPLIER-001`: `codif` nunca vira número, mas a ordenação por
    código não pode ser puramente textual — isso colocaria "100" antes de
    "49" (comparação caractere a caractere). A ordem correta é por
    (comprimento do CODIF, CODIF): primeiro os mais curtos; dentro do mesmo
    comprimento, o valor textual decide. Códigos de comprimentos 1, 2 e 3
    (decisão do dono do produto, revisão do gate visual)."""
    for codif in ("5", "49", "50", "100", "7"):
        criar_fornecedor(codif=codif, nome=f"Fornecedor {codif}")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"), {"ordem": ordem_param})

    conteudo = resposta.content.decode("utf-8")
    codigos_em_ordem_crescente = ["5", "7", "49", "50", "100"]
    codigos = (
        list(reversed(codigos_em_ordem_crescente)) if decrescente else codigos_em_ordem_crescente
    )
    # Célula exata (`<td class="table-cell-code">`), não substring: "5" é
    # substring de "50" e de "Fornecedor 5"/"Fornecedor 50" — uma checagem
    # ingênua por `in`/`index` daria falso positivo.
    posicoes = [
        re.search(rf'<td class="table-cell-code">\s*{re.escape(codigo)}\s*</td>', conteudo).start()
        for codigo in codigos
    ]
    assert posicoes == sorted(posicoes), (codigos, posicoes)


@pytest.mark.parametrize("ordem_param, decrescente", [("nome", False), ("-nome", True)])
def test_ordenacao_por_nome(
    client, funcionario_almoxarifado, criar_fornecedor, ordem_param, decrescente
):
    criar_fornecedor(codif="820001", nome="Zebra")
    criar_fornecedor(codif="820002", nome="Abacate")
    criar_fornecedor(codif="820003", nome="Manga")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"), {"ordem": ordem_param})

    codigos = ["820002", "820003", "820001"]  # Abacate, Manga, Zebra
    if decrescente:
        codigos = list(reversed(codigos))
    conteudo = resposta.content.decode("utf-8")
    posicoes = [conteudo.index(c) for c in codigos]
    assert posicoes == sorted(posicoes)


@pytest.mark.parametrize("ordem_param, decrescente", [("documento", False), ("-documento", True)])
def test_ordenacao_por_documento(
    client, funcionario_almoxarifado, criar_fornecedor, ordem_param, decrescente
):
    criar_fornecedor(codif="830001", nome="X", documento="333")
    criar_fornecedor(codif="830002", nome="Y", documento="111")
    criar_fornecedor(codif="830003", nome="Z", documento="222")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"), {"ordem": ordem_param})

    codigos = ["830002", "830003", "830001"]  # 111, 222, 333
    if decrescente:
        codigos = list(reversed(codigos))
    conteudo = resposta.content.decode("utf-8")
    posicoes = [conteudo.index(c) for c in codigos]
    assert posicoes == sorted(posicoes)


def test_ordem_desconhecida_cai_no_padrao_sem_erro(
    client, funcionario_almoxarifado, criar_fornecedor
):
    criar_fornecedor(codif="840001", nome="X")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"), {"ordem": "campo-inexistente"})

    assert resposta.status_code == 200
    assert resposta.context["ordem"] == "nome"


def test_paginacao_de_50_por_pagina(client, funcionario_almoxarifado, execucao):
    _bulk_criar_fornecedores(execucao, 60, prefixo="9")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"))

    assert resposta.status_code == 200
    assert len(resposta.context["pagina"]) == 50
    assert resposta.context["pagina"].paginator.num_pages == 2


def test_numero_de_queries_de_fornecedor_e_constante_entre_10_e_50_por_pagina(
    client, funcionario_almoxarifado, execucao
):
    client.force_login(funcionario_almoxarifado)
    url = reverse("fornecedores:consulta")

    _bulk_criar_fornecedores(execucao, 10, prefixo="91")
    with CaptureQueriesContext(connection) as com_10:
        resposta_10 = client.get(url)
    assert resposta_10.status_code == 200

    _bulk_criar_fornecedores(execucao, 40, prefixo="92")
    with CaptureQueriesContext(connection) as com_50:
        resposta_50 = client.get(url)
    assert resposta_50.status_code == 200

    queries_10 = _contar_queries_fornecedor(com_10.captured_queries)
    queries_50 = _contar_queries_fornecedor(com_50.captured_queries)
    assert queries_10 > 0
    assert queries_10 == queries_50


# ---------------------------------------------------------------------------
# Falha de uma troca HTMX (Fase B, `interface/_consulta_falha.html`) — mesmo
# molde de `tests/test_catalogo_consulta.py`. Cobre só o que é verificável no
# servidor: os hooks `hx-on`, os dois alertas ocultos por padrão e fora de
# `#resultados-consulta`, e a meta `htmx-config`. O efeito real de runtime
# (alerta aparecendo, resultados anteriores preservados na tela) só é
# verificável no browser.
# ---------------------------------------------------------------------------


def _bloco_body(conteudo):
    match = re.search(r"<body\b[^>]*>", conteudo, re.S)
    assert match is not None, "<body> não encontrado"
    return match.group()


def _bloco_section_principal(conteudo):
    match = re.search(r"<section\b[^>]*>", conteudo, re.S)
    assert match is not None, "<section> principal não encontrada"
    return match.group()


def test_meta_htmx_config_desliga_o_settle(client, funcionario_almoxarifado):
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("fornecedores:consulta"))

    conteudo = resposta.content.decode("utf-8")
    match_meta = re.search(r'<meta name="htmx-config" content=\'([^\']*)\'>', conteudo)
    assert match_meta is not None, "meta htmx-config não encontrada"
    config = json.loads(match_meta.group(1))
    assert config["defaultSettleDelay"] == 0


def test_hx_on_usa_os_nomes_de_evento_do_htmx_4(client, funcionario_almoxarifado):
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("fornecedores:consulta"))

    conteudo = resposta.content.decode("utf-8")
    assert "hx-on::before:request=" in conteudo
    assert "hx-on::error=" in conteudo
    assert "hx-on::response:error=" in conteudo
    assert "send-error" not in conteudo
    assert "response-error" not in conteudo


def test_erro_de_rede_e_tratado_no_body_e_revela_o_alerta_de_rede(
    client, funcionario_almoxarifado
):
    """A restauração de histórico do HTMX 4 inicia o GET a partir do
    `<body>`, fora da `<section>` da consulta — por isso o erro de REDE
    precisa estar tratado ali (mesmo padrão de `catalogo/consulta.html`)."""
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("fornecedores:consulta"))

    bloco = _bloco_body(resposta.content.decode("utf-8"))
    assert "hx-on::error=" in bloco
    assert "resultados-erro-rede" in bloco


def test_hx_on_response_error_neutraliza_swap_e_revela_o_alerta_de_servidor(
    client, funcionario_almoxarifado
):
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("fornecedores:consulta"))

    bloco = _bloco_section_principal(resposta.content.decode("utf-8"))
    assert "ctx.swap = 'none'" in bloco
    assert "ctx.push = false" in bloco
    assert "ctx.text = ''" in bloco
    assert "resultados-erro-servidor" in bloco


def test_hx_on_before_request_oculta_os_dois_alertas(client, funcionario_almoxarifado):
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("fornecedores:consulta"))

    bloco = _bloco_section_principal(resposta.content.decode("utf-8"))
    assert "resultados-erro-rede" in bloco
    assert "resultados-erro-servidor" in bloco


def test_alertas_de_rede_e_servidor_ficam_ocultos_por_padrao_fora_dos_resultados(
    client, funcionario_almoxarifado
):
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("fornecedores:consulta"))

    conteudo = resposta.content.decode("utf-8")
    posicao_rede = conteudo.index('id="resultados-erro-rede"')
    posicao_servidor = conteudo.index('id="resultados-erro-servidor"')
    posicao_resultados = conteudo.index('id="resultados-consulta"')
    assert posicao_rede < posicao_resultados
    assert posicao_servidor < posicao_resultados
    bloco_rede = re.search(r'<div id="resultados-erro-rede"[^>]*>', conteudo).group()
    bloco_servidor = re.search(r'<div id="resultados-erro-servidor"[^>]*>', conteudo).group()
    assert "hidden" in bloco_rede
    assert "hidden" in bloco_servidor


# ---------------------------------------------------------------------------
# Validação via HTMX: código/documento inválidos chegam com `HX-Reswap:
# none`/`HX-Push-Url: false` e marcam só o campo por cópia OOB, sem apagar a
# tabela de resultados anterior — mesmo padrão de `ConsultaCatalogoView`
# (`tests/test_catalogo_consulta.py`).
# ---------------------------------------------------------------------------


def test_codigo_invalido_via_htmx_define_hx_reswap_none_e_push_url_false(
    client, funcionario_almoxarifado
):
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(
        reverse("fornecedores:consulta"), {"codigo": "12a"}, HTTP_HX_REQUEST="true"
    )

    assert resposta.status_code == 200
    assert resposta.headers.get("HX-Reswap") == "none"
    assert resposta.headers.get("HX-Push-Url") == "false"


def test_documento_invalido_via_htmx_define_hx_reswap_none_e_push_url_false(
    client, funcionario_almoxarifado
):
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(
        reverse("fornecedores:consulta"), {"documento": "12"}, HTTP_HX_REQUEST="true"
    )

    assert resposta.status_code == 200
    assert resposta.headers.get("HX-Reswap") == "none"
    assert resposta.headers.get("HX-Push-Url") == "false"


def test_codigo_invalido_via_htmx_marca_so_o_campo_codigo_por_oob(
    client, funcionario_almoxarifado
):
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(
        reverse("fornecedores:consulta"), {"codigo": "12a"}, HTTP_HX_REQUEST="true"
    )

    conteudo = resposta.content.decode("utf-8")
    assert 'id="campo-codigo"' in conteudo
    assert 'hx-swap-oob="true"' in conteudo
    assert 'data-estado="codigo-invalido"' in conteudo
    assert "field-has-error" in conteudo
    # a cópia OOB do campo documento também é emitida (sincronização), mas
    # sem `data-estado` — só o campo realmente inválido nesta resposta.
    assert 'data-estado="documento-invalido"' not in conteudo


def test_documento_invalido_via_htmx_marca_so_o_campo_documento_por_oob(
    client, funcionario_almoxarifado
):
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(
        reverse("fornecedores:consulta"), {"documento": "12"}, HTTP_HX_REQUEST="true"
    )

    conteudo = resposta.content.decode("utf-8")
    assert 'id="campo-documento"' in conteudo
    assert 'hx-swap-oob="true"' in conteudo
    assert 'data-estado="documento-invalido"' in conteudo
    assert 'data-estado="codigo-invalido"' not in conteudo


def test_consulta_valida_via_htmx_nao_define_hx_reswap_e_reseta_os_dois_campos(
    client, funcionario_almoxarifado, criar_fornecedor
):
    criar_fornecedor(codif="900001", nome="Fornecedor Válido Via HTMX")
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(
        reverse("fornecedores:consulta"), {"codigo": "900001"}, HTTP_HX_REQUEST="true"
    )

    assert resposta.status_code == 200
    assert "HX-Reswap" not in resposta.headers
    conteudo = resposta.content.decode("utf-8")
    assert 'id="campo-codigo"' in conteudo
    assert 'hx-swap-oob="true"' in conteudo
    assert "field-has-error" not in conteudo
    assert 'data-estado="codigo-invalido"' not in conteudo
    assert 'data-estado="documento-invalido"' not in conteudo


def test_codigo_invalido_em_pagina_inteira_nao_emite_copia_oob(client, funcionario_almoxarifado):
    """Sem `HX-Request`, o campo já é marcado inline (`campo_codigo` sem
    `oob`, via `field-has-error`) — a cópia OOB só existe numa troca HTMX, ou
    `id="campo-codigo"` apareceria duplicado."""
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("fornecedores:consulta"), {"codigo": "12a"})

    assert resposta.status_code == 200
    assert "HX-Reswap" not in resposta.headers
    conteudo = resposta.content.decode("utf-8")
    assert conteudo.count('id="campo-codigo"') == 1
    assert "hx-swap-oob" not in conteudo
    assert 'data-estado="codigo-invalido"' in conteudo


def test_documento_invalido_em_pagina_inteira_nao_emite_copia_oob(
    client, funcionario_almoxarifado
):
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("fornecedores:consulta"), {"documento": "12"})

    assert resposta.status_code == 200
    assert "HX-Reswap" not in resposta.headers
    conteudo = resposta.content.decode("utf-8")
    assert conteudo.count('id="campo-documento"') == 1
    assert "hx-swap-oob" not in conteudo
    assert 'data-estado="documento-invalido"' in conteudo


# ---------------------------------------------------------------------------
# Preservação de query params: ordenar volta à página 1 preservando os
# filtros vigentes; paginar preserva filtro e ordem (mesmo padrão de
# `tests/test_catalogo_consulta.py`, seções "Cabeçalho ordenável"/"Campo
# oculto de ordem").
# ---------------------------------------------------------------------------


def _th(conteudo, texto_visivel):
    for bloco in re.findall(r"<th\b.*?</th>", conteudo, re.S):
        if texto_visivel in bloco:
            return bloco
    raise AssertionError(f"cabeçalho com {texto_visivel!r} não encontrado")


def test_link_de_ordenacao_preserva_filtro_e_volta_a_pagina_1(
    client, funcionario_almoxarifado, criar_fornecedor
):
    criar_fornecedor(codif="910001", nome="Fornecedor Filtro Preservado")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(
        reverse("fornecedores:consulta"), {"nome": "filtro preservado", "pagina": "1"}
    )

    conteudo = resposta.content.decode("utf-8")
    th_codigo = _th(conteudo, "Código")
    link = re.search(r'href="([^"]*)"', th_codigo).group(1)
    assert "nome=filtro" in link
    assert "pagina=" not in link
    assert "ordem=codigo" in link


def test_paginacao_preserva_filtro_e_ordem(client, funcionario_almoxarifado, execucao):
    _bulk_criar_fornecedores(execucao, 60, prefixo="93")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(
        reverse("fornecedores:consulta"), {"nome": "fornecedor em lote", "ordem": "-nome"}
    )

    conteudo = resposta.content.decode("utf-8")
    nav = re.search(r'<nav class="pagination".*?</nav>', conteudo, re.S).group()
    href_proxima = re.search(r'id="pagina-proxima-pagina"[^>]*href="([^"]*)"', nav)
    assert href_proxima is not None, "link 'Próxima' não encontrado"
    href = href_proxima.group(1)
    assert "nome=fornecedor" in href
    assert "ordem=-nome" in href
    assert "pagina=2" in href


def test_resumo_da_paginacao_informa_a_ordem_vigente(
    client, funcionario_almoxarifado, criar_fornecedor
):
    criar_fornecedor(codif="920001", nome="Fornecedor Ordem No Resumo")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"), {"ordem": "-nome"})

    conteudo = resposta.content.decode("utf-8")
    assert "· ordenado por nome, decrescente" in conteudo


def test_estado_vazio_e_uma_linha_table_empty_row(client, funcionario_almoxarifado):
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("fornecedores:consulta"), {"nome": "NadaAquiNoCadastro"})

    conteudo = resposta.content.decode("utf-8")
    assert '<tr class="table-empty-row" data-estado="vazio">' in conteudo


# ---------------------------------------------------------------------------
# Erro de campo (Fase C, C4, achado P3) — mesmo contrato da consulta do
# catálogo: o erro de `codigo`/`documento` aparece SÓ no campo.
# `data-estado="codigo-invalido"`/`"documento-invalido"` fica no wrapper
# (`#campo-codigo`/`#campo-documento`), o `<p class="field-error"
# id="id_<campo>_error">` é o alvo do `aria-describedby` do input, e
# `#resultados-consulta` mostra um estado neutro sem repetir a mensagem.
# ---------------------------------------------------------------------------

_CAMPOS_COM_VALIDACAO = [
    pytest.param("codigo", "12a", "campo-codigo", "codigo-invalido", id="codigo"),
    pytest.param("documento", "12", "campo-documento", "documento-invalido", id="documento"),
]


def _valor_hx_on(bloco, evento):
    """Valor do atributo `hx-on::{evento}="..."` da tag de abertura `bloco` —
    escopa a asserção ao handler certo (mesmo helper de
    `tests/test_catalogo_consulta.py`)."""
    match = re.search(rf'hx-on::{re.escape(evento)}="([^"]*)"', bloco)
    assert match is not None, f"hx-on::{evento} não encontrado no bloco"
    return match.group(1)


def _tag_input(conteudo, name):
    match = re.search(rf'<input\b[^>]*name="{re.escape(name)}"[^>]*>', conteudo)
    assert match is not None, f"<input name={name!r}> não encontrado"
    return match.group()


def _wrapper_do_campo(conteudo, id_wrapper):
    match = re.search(rf'<div\b[^>]*id="{re.escape(id_wrapper)}"[^>]*>', conteudo)
    assert match is not None, f"wrapper #{id_wrapper} não encontrado"
    return match.group()


@pytest.mark.parametrize("campo, valor_invalido, id_wrapper, estado", _CAMPOS_COM_VALIDACAO)
@pytest.mark.parametrize("via_htmx", [False, True], ids=["pagina_inteira", "copia_oob"])
def test_aria_describedby_aponta_para_o_erro_existente_do_campo(
    client, funcionario_almoxarifado, campo, valor_invalido, id_wrapper, estado, via_htmx
):
    """Na página inteira e na cópia OOB: o `id` referenciado por
    `aria-describedby` existe de fato e é o do `<p class="field-error">`."""
    client.force_login(funcionario_almoxarifado)
    extra = {"HTTP_HX_REQUEST": "true"} if via_htmx else {}

    resposta = client.get(reverse("fornecedores:consulta"), {campo: valor_invalido}, **extra)

    conteudo = resposta.content.decode("utf-8")
    tag = _tag_input(conteudo, campo)
    match = re.search(r'aria-describedby="([^"]*)"', tag)
    assert match is not None, f"aria-describedby ausente em {tag}"
    id_erro = f"id_{campo}_error"
    assert id_erro in match.group(1).split()
    assert f'<p class="field-error" id="{id_erro}">' in conteudo
    assert conteudo.count(f'id="{id_erro}"') == 1


@pytest.mark.parametrize("campo, valor_invalido, id_wrapper, estado", _CAMPOS_COM_VALIDACAO)
def test_erro_sem_htmx_marca_o_wrapper_e_nao_repete_a_mensagem_nos_resultados(
    client, funcionario_almoxarifado, campo, valor_invalido, id_wrapper, estado
):
    from django.utils.html import escape

    client.force_login(funcionario_almoxarifado)

    resposta = client.get(reverse("fornecedores:consulta"), {campo: valor_invalido})

    conteudo = resposta.content.decode("utf-8")
    mensagem = escape(resposta.context["form"].errors[campo][0])
    wrapper = _wrapper_do_campo(conteudo, id_wrapper)
    assert f'data-estado="{estado}"' in wrapper
    assert "field-has-error" in wrapper

    regiao_resultados = conteudo[conteudo.index('id="resultados-consulta"') :]
    assert mensagem not in regiao_resultados
    assert f'data-estado="{estado}"' not in regiao_resultados
    assert 'role="alert"' not in regiao_resultados
    assert conteudo.count(mensagem) == 1, "o erro deve aparecer uma única vez (só no campo)"


@pytest.mark.parametrize("campo, valor_invalido, id_wrapper, estado", _CAMPOS_COM_VALIDACAO)
def test_erro_via_htmx_marca_o_wrapper_da_copia_oob(
    client, funcionario_almoxarifado, campo, valor_invalido, id_wrapper, estado
):
    client.force_login(funcionario_almoxarifado)

    resposta = client.get(
        reverse("fornecedores:consulta"), {campo: valor_invalido}, HTTP_HX_REQUEST="true"
    )

    wrapper = _wrapper_do_campo(resposta.content.decode("utf-8"), id_wrapper)
    assert 'hx-swap-oob="true"' in wrapper
    assert f'data-estado="{estado}"' in wrapper
    assert "field-has-error" in wrapper


def test_hx_on_before_request_limpa_a_marcacao_de_erro_dos_campos(
    client, funcionario_almoxarifado, criar_fornecedor
):
    """Sem isto, uma nova busca que FALHA (500/rede) deixaria o erro antigo
    do campo junto do alerta de falha. O efeito no DOM só é verificável no
    browser; aqui, que o handler cobre classe, `data-estado`, mensagem e
    `aria-invalid`."""
    criar_fornecedor(codif="930001", nome="Limpa Marcação De Erro")

    client.force_login(funcionario_almoxarifado)
    conteudo = client.get(reverse("fornecedores:consulta")).content.decode("utf-8")

    valor = _valor_hx_on(_bloco_section_principal(conteudo), "before:request")
    assert "field-has-error" in valor
    assert "data-estado" in valor
    assert "field-error" in valor
    assert "aria-invalid" in valor


# ---------------------------------------------------------------------------
# Paginação via HTMX (Fase C, C1, achado P1) — mesmo contrato da consulta do
# catálogo: links de página rolam o alvo ao topo (`show:top`) e o foco vai à
# tabela (`tabindex="-1"`); a ORDENAÇÃO daqui é navegação de página inteira
# (sem `hx-get`) e o formulário não rola. Rolagem/foco em si: só no browser.
# ---------------------------------------------------------------------------


def test_links_de_pagina_htmx_rolam_ao_topo_e_casam_com_o_seletor_do_handler(
    client, funcionario_almoxarifado, execucao
):
    _bulk_criar_fornecedores(execucao, 120, prefixo="94")  # 3 páginas de 50

    client.force_login(funcionario_almoxarifado)
    conteudo = client.get(reverse("fornecedores:consulta"), {"pagina": "2"}).content.decode(
        "utf-8"
    )

    valor_before = _valor_hx_on(_bloco_section_principal(conteudo), "before:request")
    assert "a.pagination-link[hx-get]" in valor_before

    nav = re.search(r'<nav class="pagination".*?</nav>', conteudo, re.S).group()
    links = re.findall(r'<a\b[^>]*class="pagination-link"[^>]*hx-get=[^>]*>', nav)
    assert len(links) >= 4, "esperava Anterior, Próxima e números de página com hx-get"
    for link in links:
        assert 'hx-swap="innerHTML show:top"' in link, link


def test_ordenacao_e_navegacao_de_pagina_inteira_sem_hx_get(
    client, funcionario_almoxarifado, criar_fornecedor
):
    """Ordenar recarrega o `<form>` inteiro (campo oculto `ordem` sempre em
    dia, sem cópia OOB) — por isso os cabeçalhos NÃO levam `hx-get`/`hx-swap`,
    ao contrário dos links de página."""
    criar_fornecedor(codif="930002", nome="Ordenação Em Página Inteira")

    client.force_login(funcionario_almoxarifado)
    conteudo = client.get(reverse("fornecedores:consulta")).content.decode("utf-8")

    ths_ordenaveis = [
        bloco
        for bloco in re.findall(r"<th\b.*?</th>", conteudo, re.S)
        if "table-sort-link" in bloco
    ]
    assert len(ths_ordenaveis) == 3, "Código, Nome e Documento são ordenáveis"
    for bloco in ths_ordenaveis:
        assert "hx-get" not in bloco
        assert "hx-swap" not in bloco


def test_formulario_de_filtros_nao_rola_ao_topo(client, funcionario_almoxarifado):
    client.force_login(funcionario_almoxarifado)

    conteudo = client.get(reverse("fornecedores:consulta")).content.decode("utf-8")

    form = re.search(r'<form\b[^>]*class="filter-bar"[^>]*>', conteudo)
    assert form is not None
    assert "hx-get" in form.group()
    assert "hx-swap" not in form.group()
    assert "show:" not in form.group()


def test_tabela_populada_de_resultados_e_focavel_por_script(
    client, funcionario_almoxarifado, criar_fornecedor
):
    """`hx-on::after:swap` foca `#resultados-consulta table`; um `<table>` sem
    `tabindex="-1"` não recebe foco por script."""
    criar_fornecedor(codif="930003", nome="Tabela Focável")

    client.force_login(funcionario_almoxarifado)
    conteudo = client.get(reverse("fornecedores:consulta")).content.decode("utf-8")

    regiao = conteudo[conteudo.index('id="resultados-consulta"') :]
    assert re.search(r'<table\b[^>]*tabindex="-1"', regiao)
    valor_after = _valor_hx_on(_bloco_section_principal(conteudo), "after:swap")
    assert "#resultados-consulta table" in valor_after


# ---------------------------------------------------------------------------
# HTMX: só o fragmento (mesma convenção da 001, fixada aqui — ver docstring).
# ---------------------------------------------------------------------------


def test_com_hx_request_a_resposta_e_so_o_fragmento(
    client, funcionario_almoxarifado, criar_fornecedor
):
    criar_fornecedor(codif="950001", nome="Fragmento HTMX")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"), HTTP_HX_REQUEST="true")

    assert resposta.status_code == 200
    nomes_templates = [template.name for template in resposta.templates if template.name]
    assert "resultados_consulta" in nomes_templates
    assert "fornecedores/consulta.html" not in nomes_templates


def test_sem_hx_request_a_resposta_e_a_pagina_inteira(
    client, funcionario_almoxarifado, criar_fornecedor
):
    criar_fornecedor(codif="950002", nome="Página Inteira")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"))

    assert resposta.status_code == 200
    nomes_templates = [template.name for template in resposta.templates if template.name]
    assert "fornecedores/consulta.html" in nomes_templates


# ---------------------------------------------------------------------------
# Nenhum caminho de criar/editar/excluir a partir da consulta (FR-005,
# scenario 6 da US2).
# ---------------------------------------------------------------------------


def test_post_na_consulta_e_405(client, funcionario_almoxarifado):
    client.force_login(funcionario_almoxarifado)

    resposta = client.post(reverse("fornecedores:consulta"))

    assert resposta.status_code == 405


def test_pagina_de_consulta_nao_tem_nenhum_link_ou_form_de_criar_editar_excluir(
    client, funcionario_almoxarifado, criar_fornecedor
):
    criar_fornecedor(codif="960001", nome="Sem Acao De Escrita")

    client.force_login(funcionario_almoxarifado)
    resposta = client.get(reverse("fornecedores:consulta"))

    conteudo_minusculo = resposta.content.decode("utf-8").lower()
    for termo_proibido in ("criar fornecedor", "editar fornecedor", "excluir fornecedor"):
        assert termo_proibido not in conteudo_minusculo
