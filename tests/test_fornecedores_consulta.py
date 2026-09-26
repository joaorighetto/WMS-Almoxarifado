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
"""

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
