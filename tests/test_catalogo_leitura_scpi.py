"""Testes do parser SCPI (T015, US1 — Fase 3 de
`specs/001-importacao-catalogo-materiais/`).

Escritos ANTES da implementação de `catalogo/leitura_scpi.py` (T020/T021):
hoje o módulo só tem `normalizar_para_busca` (T012). Este arquivo deve
FALHAR agora — por `AttributeError` ao acessar `leitura_scpi.ler_registros`,
`leitura_scpi.ArquivoRecusado` etc. dentro de cada teste — e passar quando
T020/T021 estiverem prontas.

Cobre exclusivamente `catalogo/leitura_scpi.py`, sem banco: decodificação,
cabeçalho, recomposição de linhas físicas, validação por registro e
interpretação de quantidade, conforme `contracts/arquivo-scpi.md` e
`research.md` R2–R6. Não cobre `calcular_plano`/`aplicar_plano`
(`tests/test_catalogo_importacao.py`, T016), atomicidade
(`tests/test_catalogo_atomicidade.py`, T017), views
(`tests/test_catalogo_views_importacao.py`, T018) nem permissões
(`tests/test_catalogo_permissoes.py`, T019).

Invariantes/requisitos protegidos:
- `INV-CATALOG-001`: `cadpro` só é aceito em `XXX.YYY.ZZZ`, com dígitos
  ASCII (nunca `\\d`, que aceitaria dígito Unicode — research.md R3), sem
  trim e sem reformatação.
- `INV-CATALOG-005`: unidade preservada como recebida; nenhum valor
  textual aceito é aparado, normalizado ou alterado.
- `INV-STOCK-001`: quantidade negativa é sempre recusada, nunca zerada
  nem arredondada para positiva.

Nota sobre importação (requisito da task — "Verificação"): o módulo
`catalogo.leitura_scpi` já existe (com `normalizar_para_busca`, T012), então
`import catalogo.leitura_scpi as leitura_scpi` no topo deste arquivo não
falha, e `pytest --collect-only` funciona normalmente. Os símbolos ainda
inexistentes (`ler_registros`, `ArquivoRecusado`, `QuantidadeInvalida`,
`interpretar_quantidade`, `verificar_arquivo`, `decodificar`,
`PADRAO_CADPRO`, `COLUNAS_OBRIGATORIAS`, `LIMITE_TAMANHO_ARQUIVO`) só são
referenciados dentro do corpo de cada teste (`leitura_scpi.ler_registros`
etc.), então a ausência vira `AttributeError` na chamada — uma falha por
teste, nunca um erro de coleta do arquivo inteiro.
"""

import time
from decimal import Decimal

import pytest

import catalogo.leitura_scpi as leitura_scpi
from catalogo.models import MotivoRecusa

# ---------------------------------------------------------------------------
# Helpers de montagem de arquivo (bytes exatos, sem `csv` — mesma abordagem
# do parser: `;` sem tratamento de aspas, quebra de linha explícita).
# ---------------------------------------------------------------------------

BOM = "﻿"

# Cabeçalho mínimo com só as 9 colunas obrigatórias, `CADPRO` na 1ª posição,
# terminado em `;` (delimitador final, igual ao arquivo real).
CABECALHO_MINIMO = "CADPRO;DISC1;UNID1;QUAN3;DISCR1;GRUPO;SUBGRUPO;NOMEGRUPO;NOMESUBGRUPO;"


def _linha(cadpro="", disc1="", unid1="", quan3="", discr1="", grupo="", subgrupo="",
           nomegrupo="", nomesubgrupo=""):
    """Uma linha física completa para `CABECALHO_MINIMO`: os 9 valores na
    ordem do cabeçalho, com o delimitador final."""
    valores = [cadpro, disc1, unid1, quan3, discr1, grupo, subgrupo, nomegrupo, nomesubgrupo]
    return ";".join(valores) + ";"


def _montar(cabecalho, linhas, *, bom=True, quebra="\r\n"):
    """Monta bytes UTF-8 a partir de um cabeçalho e linhas de dados já
    prontas (texto de cada linha física, sem a quebra de linha final)."""
    texto = quebra.join([cabecalho, *linhas])
    if bom:
        texto = BOM + texto
    return texto.encode("utf-8")


def _arquivo(*linhas_dados, cabecalho=CABECALHO_MINIMO, bom=True, quebra="\r\n"):
    """Atalho de `_montar` para o cabeçalho mínimo de 9 colunas."""
    return _montar(cabecalho, linhas_dados, bom=bom, quebra=quebra)


# ---------------------------------------------------------------------------
# decodificar / verificar_arquivo — recusas de arquivo inteiro (§1)
# ---------------------------------------------------------------------------


def test_decodificar_remove_bom_e_aceita_arquivo_sem_bom():
    assert leitura_scpi.decodificar((BOM + "abc").encode("utf-8")) == "abc"
    assert leitura_scpi.decodificar(b"abc") == "abc"


def test_decodificar_bytes_invalidos_recusa_arquivo_inteiro():
    conteudo = b"cabecalho\n" + b"\xff"
    with pytest.raises(leitura_scpi.ArquivoRecusado) as exc_info:
        leitura_scpi.decodificar(conteudo)
    assert exc_info.value.codigo == "ARQUIVO_CODIFICACAO_INVALIDA"


def test_bom_nao_contamina_cabecalho_nem_o_primeiro_cadpro():
    """Edge case da spec: a marca BOM não pode contaminar o nome da 1ª
    coluna nem o primeiro código lido."""
    conteudo = _arquivo(_linha(cadpro="000.000.002", disc1="A", unid1="UN", quan3="1"))

    leitura_scpi.verificar_arquivo(conteudo)  # não levanta
    resultado = leitura_scpi.ler_registros(conteudo)

    assert resultado.aceitos[0].cadpro == "000.000.002"


@pytest.mark.parametrize(
    "nome_fixture, codigo_esperado",
    [
        ("sem_coluna_obrigatoria.csv", "ARQUIVO_COLUNA_OBRIGATORIA_AUSENTE"),
        ("cadpro_nao_primeira_coluna.csv", "ARQUIVO_CADPRO_NAO_E_PRIMEIRA_COLUNA"),
        ("codificacao_invalida.csv", "ARQUIVO_CODIFICACAO_INVALIDA"),
    ],
)
def test_arquivo_recusado_por_estrutura_do_cabecalho(csv_fixture, nome_fixture, codigo_esperado):
    conteudo = csv_fixture(nome_fixture)

    with pytest.raises(leitura_scpi.ArquivoRecusado) as exc_info:
        leitura_scpi.ler_registros(conteudo)
    assert exc_info.value.codigo == codigo_esperado

    # `verificar_arquivo` recusa pelo mesmo motivo, sem processar registros.
    with pytest.raises(leitura_scpi.ArquivoRecusado) as exc_info_verificar:
        leitura_scpi.verificar_arquivo(conteudo)
    assert exc_info_verificar.value.codigo == codigo_esperado


def test_mensagem_de_coluna_ausente_lista_todas_as_que_faltam():
    cabecalho = "CADPRO;DISC1;UNID1;QUAN3;DISCR1;GRUPO;SUBGRUPO;"  # faltam NOMEGRUPO e NOMESUBGRUPO
    conteudo = _montar(cabecalho, ["000.000.002;A;UN;1;;;;"])

    with pytest.raises(leitura_scpi.ArquivoRecusado) as exc_info:
        leitura_scpi.ler_registros(conteudo)

    assert exc_info.value.codigo == "ARQUIVO_COLUNA_OBRIGATORIA_AUSENTE"
    assert "NOMEGRUPO" in exc_info.value.mensagem
    assert "NOMESUBGRUPO" in exc_info.value.mensagem


def test_coluna_obrigatoria_duplicada_recusa_arquivo_inteiro():
    cabecalho = "CADPRO;DISC1;DISC1;UNID1;QUAN3;DISCR1;GRUPO;SUBGRUPO;NOMEGRUPO;NOMESUBGRUPO;"
    conteudo = _montar(cabecalho, ["000.000.002;A;A2;UN;1;;;;;"])

    with pytest.raises(leitura_scpi.ArquivoRecusado) as exc_info:
        leitura_scpi.ler_registros(conteudo)

    assert exc_info.value.codigo == "ARQUIVO_COLUNA_DUPLICADA"


def test_coluna_fora_de_escopo_duplicada_no_cabecalho_nao_tem_efeito():
    cabecalho = CABECALHO_MINIMO + "VAUN1;VAUN1;"
    linha = "000.000.002;PARAFUSO;UN;10;;;;;;1,00;2,00;"
    conteudo = _montar(cabecalho, [linha])

    resultado = leitura_scpi.ler_registros(conteudo)

    assert len(resultado.aceitos) == 1
    assert resultado.aceitos[0].cadpro == "000.000.002"


def test_colunas_lidas_pelo_nome_com_cabecalho_reordenado_e_colunas_extras():
    """T006: as demais colunas obrigatórias fora de ordem, com colunas
    extras entre elas — os valores são lidos pelo **nome**, nunca pela
    posição."""
    cabecalho = (
        "CADPRO;GRUPO;EXTRA1;DISC1;SUBGRUPO;UNID1;EXTRA2;NOMEGRUPO;QUAN3;NOMESUBGRUPO;DISCR1;"
    )
    linha = "000.000.002;010;ignorado;PARAFUSO;020;UN;ignorado2;FERRAGENS;10;PARAFUSOS;detalhe;"
    conteudo = _montar(cabecalho, [linha])

    resultado = leitura_scpi.ler_registros(conteudo)

    assert len(resultado.aceitos) == 1
    aceito = resultado.aceitos[0]
    assert aceito.cadpro == "000.000.002"
    assert aceito.descricao == "PARAFUSO"
    assert aceito.unidade == "UN"
    assert aceito.quantidade == Decimal("10.000")
    assert aceito.grupo == "010"
    assert aceito.subgrupo == "020"
    assert aceito.nome_grupo == "FERRAGENS"
    assert aceito.nome_subgrupo == "PARAFUSOS"
    assert aceito.detalhamento == "detalhe"


def test_arquivo_vazio_e_somente_cabecalho_dao_zero_registros_sem_erro(csv_fixture):
    for nome in ("vazio.csv", "somente_cabecalho.csv"):
        resultado = leitura_scpi.ler_registros(csv_fixture(nome))
        assert resultado.total_recebidos == 0
        assert resultado.aceitos == ()
        assert resultado.recusas == ()


def test_constantes_do_contrato():
    assert leitura_scpi.LIMITE_TAMANHO_ARQUIVO == 10 * 1024 * 1024
    assert set(leitura_scpi.COLUNAS_OBRIGATORIAS) == {
        "CADPRO", "DISC1", "UNID1", "QUAN3", "DISCR1",
        "GRUPO", "SUBGRUPO", "NOMEGRUPO", "NOMESUBGRUPO",
    }
    assert leitura_scpi.PADRAO_CADPRO.fullmatch("000.000.002")
    assert not leitura_scpi.PADRAO_CADPRO.fullmatch("2")


# ---------------------------------------------------------------------------
# Recomposição de linhas físicas e classificação (§2, research.md R3)
# ---------------------------------------------------------------------------


def test_crlf_e_lf_misturados_sao_equivalentes():
    linha1 = _linha(cadpro="000.000.002", disc1="A", unid1="UN", quan3="1")
    linha2 = _linha(cadpro="000.000.003", disc1="B", unid1="UN", quan3="2")
    texto = CABECALHO_MINIMO + "\r\n" + linha1 + "\n" + linha2
    conteudo = (BOM + texto).encode("utf-8")

    resultado = leitura_scpi.ler_registros(conteudo)

    assert [r.cadpro for r in resultado.aceitos] == ["000.000.002", "000.000.003"]
    assert resultado.total_recebidos == 2


def test_caracteres_especiais_dentro_do_texto_nao_quebram_registro():
    """`\\u2028` (separador de parágrafo) e `\\x0c` (form feed) não são fim
    de linha para o parser — `str.splitlines()` os trataria como tal, mas o
    parser só quebra em `\\n` (research.md R2)."""
    detalhe = "linha com separador de paragrafo e \x0c form feed"
    linha = _linha(cadpro="000.000.002", disc1="A", unid1="UN", quan3="1", discr1=detalhe)
    conteudo = _arquivo(linha)

    resultado = leitura_scpi.ler_registros(conteudo)

    assert len(resultado.aceitos) == 1
    assert resultado.aceitos[0].detalhamento == detalhe


def test_continuacao_antes_do_primeiro_registro_e_nao_associavel():
    linha1 = "continuacao perdida sem registro anterior;abc;def"
    linha2 = _linha(cadpro="000.000.002", disc1="A", unid1="UN", quan3="1")
    conteudo = _arquivo(linha1, linha2)

    resultado = leitura_scpi.ler_registros(conteudo)

    assert resultado.total_recebidos == 2
    assert len(resultado.aceitos) == 1
    recusa = resultado.recusas[0]
    assert recusa.motivo == MotivoRecusa.LINHA_NAO_ASSOCIAVEL
    assert recusa.cadpro == ""


def test_coluna_vazia_final_ignorada_mas_preenchida_gera_estrutura_inconsistente():
    linha_ok = _linha(cadpro="000.000.002", disc1="A", unid1="UN", quan3="1")
    resultado_ok = leitura_scpi.ler_registros(_arquivo(linha_ok))
    assert len(resultado_ok.aceitos) == 1

    # Preenche a coluna vazia final (mesma contagem de campos, último não
    # mais vazio) -> ESTRUTURA_INCONSISTENTE, não aceito.
    linha_invalida = linha_ok + "X"
    resultado_invalido = leitura_scpi.ler_registros(_arquivo(linha_invalida))
    assert resultado_invalido.aceitos == ()
    assert resultado_invalido.recusas[0].motivo == MotivoRecusa.ESTRUTURA_INCONSISTENTE


def test_estrutura_inconsistente_diferencia_causa_na_mensagem():
    """P3 #6: `ESTRUTURA_INCONSISTENTE` tem duas causas possíveis —
    contagem de campos diferente do cabeçalho, ou último campo (delimitador
    final) preenchido com a mesma contagem — e a mensagem precisa deixar
    claro qual delas ocorreu. Sem a distinção, o último campo preenchido
    (10 campos esperados, 10 encontrados) saía como "Esperado 10 campos;
    encontrado 10.", que não aponta a causa real."""
    linha_ok = _linha(cadpro="000.000.002", disc1="A", unid1="UN", quan3="1")

    linha_ultimo_campo_preenchido = linha_ok + "X"
    resultado_ultimo_campo = leitura_scpi.ler_registros(_arquivo(linha_ultimo_campo_preenchido))
    detalhe_ultimo_campo = resultado_ultimo_campo.recusas[0].detalhe
    assert "encontrado 'X'" in detalhe_ultimo_campo
    assert "campos" not in detalhe_ultimo_campo, (
        "a mensagem do último campo preenchido não pode reaproveitar o texto de "
        "contagem de campos ('Esperado N campos; encontrado M')"
    )

    linha_campos_a_menos = "000.000.003;B;UN"
    resultado_campos = leitura_scpi.ler_registros(_arquivo(linha_campos_a_menos))
    detalhe_campos = resultado_campos.recusas[0].detalhe
    assert detalhe_campos == "Esperado 10 campos; encontrado 3."
    assert detalhe_campos != detalhe_ultimo_campo


def test_estrutura_inconsistente_multilinha_usa_primeiro_campo_do_registro_recomposto():
    linha1 = "000.000.099;Descricao"
    linha2 = "continuacao sem fechar o registro"
    conteudo = _arquivo(linha1, linha2)

    resultado = leitura_scpi.ler_registros(conteudo)

    assert resultado.aceitos == ()
    recusa = resultado.recusas[0]
    assert recusa.motivo == MotivoRecusa.ESTRUTURA_INCONSISTENTE
    assert recusa.cadpro == "000.000.099"


def test_ordem_estrutura_inconsistente_antes_de_cadpro_ausente():
    """R5: `ESTRUTURA_INCONSISTENTE` (posição 2) precede `CADPRO_AUSENTE`
    (posição 3) — um registro com `CADPRO` vazio, mas estruturalmente
    inconsistente, é reportado só pelo motivo de estrutura."""
    linha_inicio = _linha(cadpro="", disc1="A", unid1="UN", quan3="1")  # N-1 separadores
    linha_continuacao = "texto solto sem separadores suficientes"
    conteudo = _arquivo(linha_inicio, linha_continuacao)

    resultado = leitura_scpi.ler_registros(conteudo)

    assert len(resultado.recusas) == 1
    assert resultado.recusas[0].motivo == MotivoRecusa.ESTRUTURA_INCONSISTENTE


def test_continuacao_legitima_com_n_menos_1_separadores_por_acaso_recusa_os_dois_registros():
    """research.md R3: se uma continuação legítima tiver, por acaso, a
    contagem completa de separadores do cabeçalho, ela é lida como um novo
    início de registro (código inválido) — os **dois** registros envolvidos
    são recusados, nunca importados com deslocamento."""
    linha_a = "000.000.002;Produto iniciado sem fechar detalhamento"
    linha_b = (
        "fim do detalhamento;GRUPO;SUBGRUPO;NOMEGRUPO;NOMESUBGRUPO;extra1;extra2;extra3;extra4;"
    )
    texto = CABECALHO_MINIMO + "\r\n" + linha_a + "\r\n" + linha_b
    conteudo = (BOM + texto).encode("utf-8")

    resultado = leitura_scpi.ler_registros(conteudo)

    assert resultado.aceitos == ()
    assert resultado.total_recebidos == 2
    assert [r.motivo for r in resultado.recusas] == [
        MotivoRecusa.ESTRUTURA_INCONSISTENTE,
        MotivoRecusa.CADPRO_FORMATO_INVALIDO,
    ]


def test_linha_so_com_espacos_segue_a_mesma_regra_da_linha_vazia():
    linha1 = _linha(cadpro="000.000.002", disc1="A", unid1="UN", quan3="1")
    linha2 = "   "  # só espaços, entre dois registros completos
    linha3 = _linha(cadpro="000.000.003", disc1="B", unid1="UN", quan3="2")
    conteudo = _arquivo(linha1, linha2, linha3)

    resultado = leitura_scpi.ler_registros(conteudo)

    assert resultado.total_recebidos == 2
    assert [a.cadpro for a in resultado.aceitos] == ["000.000.002", "000.000.003"]


def test_numeracao_de_linha_continua_correta_apos_linha_vazia_ignorada():
    linha1 = _linha(cadpro="000.000.002", disc1="A", unid1="UN", quan3="1")
    linha_vazia = ""
    linha_invalida = _linha(cadpro="2", disc1="B", unid1="UN", quan3="1")
    conteudo = _arquivo(linha1, linha_vazia, linha_invalida)

    resultado = leitura_scpi.ler_registros(conteudo)

    # header=1, linha1=2, linha_vazia=3 (ignorada, não desloca a numeração), linha_invalida=4
    assert resultado.recusas[0].linha_inicial == 4
    assert resultado.recusas[0].linha_final == 4


def test_linhas_vazias_fixture(csv_fixture):
    """Decisão D-1: linha vazia ignorada fora de registro incompleto,
    preservada como continuação dentro de um (`tests/fixtures/catalogo/
    README.md` → `linhas_vazias.csv`)."""
    resultado = leitura_scpi.ler_registros(csv_fixture("linhas_vazias.csv"))

    assert resultado.total_recebidos == 3
    assert len(resultado.aceitos) == 3
    assert resultado.recusas == ()

    por_cadpro = {a.cadpro: a for a in resultado.aceitos}
    item_c = por_cadpro["010.010.012"]
    assert item_c.detalhamento == "linha 1\n\nlinha 3"
    assert item_c.linha_inicial == 5
    assert item_c.linha_final == 7


def test_recomposicao_de_registro_com_muitas_continuacoes_nao_e_quadratica():
    """P2 #2: `_recompor_registros` não pode custar quadrático no número de
    linhas de continuação. A implementação antiga (a) concatenava
    `corrente.texto += "\\n" + linha` a cada linha — cópia da string inteira
    a cada vez, já que atributo de objeto não recebe a otimização in-place
    do CPython — e (b) re-`split(";")` o texto acumulado a cada linha em
    branco para checar completude. Com dezenas de milhares de continuações,
    isso não terminava em tempo útil; a versão corrigida é linear e conclui
    em frações de segundo.

    O arquivo sintético fica na casa de poucos MB: um único registro cuja
    descrição (`DISC1`) se estende por `N_LINHAS_CONTINUACAO` linhas físicas
    (algumas vazias, para também exercitar a checagem de completude), fechado
    ao final com os demais campos.
    """
    N_LINHAS_CONTINUACAO = 30_000
    LIMITE_SEGUNDOS = 5.0

    linha_inicial = "000.000.002;"  # abre CADPRO;DISC1 (continua nas próximas linhas)
    linhas_continuacao = [
        "" if indice % 5 == 0 else f"trecho de descricao numero {indice} " * 2
        for indice in range(N_LINHAS_CONTINUACAO)
    ]
    campos_finais = ["UN", "1", "", "", "", "", ""]  # UNID1..NOMESUBGRUPO
    linha_fechamento = ";" + ";".join(campos_finais) + ";"

    conteudo = _arquivo(linha_inicial, *linhas_continuacao, linha_fechamento)

    inicio = time.perf_counter()
    resultado = leitura_scpi.ler_registros(conteudo)
    duracao = time.perf_counter() - inicio

    assert duracao < LIMITE_SEGUNDOS, (
        f"recompor {N_LINHAS_CONTINUACAO} linhas de continuação levou {duracao:.2f}s "
        f"(limite {LIMITE_SEGUNDOS}s) — indício de custo quadrático (P2 #2)"
    )
    assert len(resultado.aceitos) == 1
    aceito = resultado.aceitos[0]
    assert aceito.cadpro == "000.000.002"
    assert aceito.unidade == "UN"
    assert aceito.quantidade == Decimal("1.000")


# ---------------------------------------------------------------------------
# Validação por registro e ordem dos motivos (§3, research.md R5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "campo, valor, motivo_esperado",
    [
        ("cadpro", "", MotivoRecusa.CADPRO_AUSENTE),
        ("cadpro", "2", MotivoRecusa.CADPRO_FORMATO_INVALIDO),
        ("cadpro", "000.000.2", MotivoRecusa.CADPRO_FORMATO_INVALIDO),
        ("cadpro", "٠٠٠.٠٠٠.٠٠٢", MotivoRecusa.CADPRO_FORMATO_INVALIDO),  # dígito Unicode
        ("disc1", "", MotivoRecusa.DESCRICAO_AUSENTE),
        ("disc1", "   ", MotivoRecusa.DESCRICAO_AUSENTE),
        ("unid1", "", MotivoRecusa.UNIDADE_AUSENTE),
        ("quan3", "", MotivoRecusa.QUANTIDADE_AUSENTE),
        ("quan3", "   ", MotivoRecusa.QUANTIDADE_AUSENTE),
        ("quan3", "1.5", MotivoRecusa.QUANTIDADE_NAO_NUMERICA),
        ("quan3", "1,2,3", MotivoRecusa.QUANTIDADE_NAO_NUMERICA),
        ("quan3", " ,5", MotivoRecusa.QUANTIDADE_NAO_NUMERICA),
        ("quan3", "1 234", MotivoRecusa.QUANTIDADE_NAO_NUMERICA),
        ("quan3", "-1", MotivoRecusa.QUANTIDADE_NEGATIVA),
        ("quan3", "-0,0001", MotivoRecusa.QUANTIDADE_NEGATIVA),
        ("quan3", "1234567890123", MotivoRecusa.QUANTIDADE_FORA_DO_LIMITE),  # 13 dígitos
    ],
    ids=[
        "cadpro_ausente", "cadpro_muito_curto", "cadpro_ultimo_grupo_incompleto",
        "cadpro_digito_unicode", "descricao_ausente", "descricao_so_espacos",
        "unidade_ausente", "quantidade_ausente", "quantidade_so_espacos",
        "quantidade_um_ponto_decimal", "quantidade_dois_separadores_decimais",
        "quantidade_so_decimal", "quantidade_com_espaco_no_meio",
        "quantidade_negativa", "quantidade_negativa_arredondaria_a_zero",
        "quantidade_13_digitos",
    ],
)
def test_motivo_de_recusa_por_campo(campo, valor, motivo_esperado):
    """R5, tabela de ordem dos motivos: um caso isolado por motivo (nunca
    combinado com outro), num único teste parametrizado."""
    base = dict(cadpro="000.000.002", disc1="PARAFUSO", unid1="UN", quan3="10")
    base[campo] = valor
    conteudo = _arquivo(_linha(**base))

    resultado = leitura_scpi.ler_registros(conteudo)

    assert resultado.aceitos == ()
    assert len(resultado.recusas) == 1
    assert resultado.recusas[0].motivo == motivo_esperado


def test_cadpro_duplicado_recusa_todas_as_ocorrencias_mesmo_com_outra_falha():
    """FR-005: duplicidade é apurada sobre todo `CADPRO` bem formado — e
    tem prioridade (posição 5) sobre uma falha de quantidade (posição 8+)
    que uma das ocorrências também teria."""
    linha1 = _linha(cadpro="090.090.090", disc1="Item um", unid1="UN", quan3="1")
    linha2 = _linha(cadpro="090.090.090", disc1="Item dois", unid1="UN", quan3="abc")
    conteudo = _arquivo(linha1, linha2)

    resultado = leitura_scpi.ler_registros(conteudo)

    assert resultado.aceitos == ()
    assert [r.motivo for r in resultado.recusas] == [
        MotivoRecusa.CADPRO_DUPLICADO_NO_ARQUIVO,
        MotivoRecusa.CADPRO_DUPLICADO_NO_ARQUIVO,
    ]
    assert resultado.total_recebidos == 2


def test_cadpro_malformado_repetido_nao_conta_como_duplicado():
    """Duplicidade só é apurada entre `CADPRO` bem formados — um código
    malformado repetido é recusado por formato em cada ocorrência, nunca
    por duplicidade."""
    linha1 = _linha(cadpro="2", disc1="A", unid1="UN", quan3="1")
    linha2 = _linha(cadpro="2", disc1="B", unid1="UN", quan3="2")
    conteudo = _arquivo(linha1, linha2)

    resultado = leitura_scpi.ler_registros(conteudo)

    assert [r.motivo for r in resultado.recusas] == [
        MotivoRecusa.CADPRO_FORMATO_INVALIDO,
        MotivoRecusa.CADPRO_FORMATO_INVALIDO,
    ]


# ---------------------------------------------------------------------------
# interpretar_quantidade (§3, research.md R6)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("0", Decimal("0.000")),
        ("0,000", Decimal("0.000")),
        ("10", Decimal("10.000")),
        ("1.234,5", Decimal("1234.500")),
        ("53,4000000000001", Decimal("53.400")),
        ("-0", Decimal("0.000")),
        ("-0,000", Decimal("0.000")),
        ("1" * 12, Decimal("1" * 12 + ".000")),  # 12 dígitos inteiros: aceito
        ("0" * 15 + "1", Decimal("1.000")),  # zeros à esquerda não contam (P3 #4)
    ],
    ids=[
        "zero_inteiro", "zero_com_decimal", "inteiro_simples", "milhar_com_decimal",
        "ruido_ponto_flutuante", "menos_zero_inteiro", "menos_zero_com_decimal",
        "doze_digitos_no_limite", "zeros_a_esquerda_nao_contam_para_o_limite",
    ],
)
def test_interpretar_quantidade_aceita(texto, esperado):
    assert leitura_scpi.interpretar_quantidade(texto) == esperado


@pytest.mark.parametrize("texto", ["-0", "-0,000", "-0,0000"])
def test_interpretar_quantidade_nunca_devolve_zero_negativo(texto):
    """P3 #5: `-0`/`-0,000` valem zero — nunca um `Decimal` de zero
    negativo, mesmo quando só o arredondamento produz `-0` internamente."""
    resultado = leitura_scpi.interpretar_quantidade(texto)
    assert resultado == Decimal("0.000")
    assert not resultado.is_signed(), (
        f"interpretar_quantidade({texto!r}) devolveu zero negativo: {resultado!r}"
    )


@pytest.mark.parametrize(
    "texto, motivo_esperado",
    [
        ("", MotivoRecusa.QUANTIDADE_AUSENTE),
        ("   ", MotivoRecusa.QUANTIDADE_AUSENTE),
        ("-1", MotivoRecusa.QUANTIDADE_NEGATIVA),
        ("-0,0001", MotivoRecusa.QUANTIDADE_NEGATIVA),  # negativo antes de arredondar
        ("1.5", MotivoRecusa.QUANTIDADE_NAO_NUMERICA),
        ("1,2,3", MotivoRecusa.QUANTIDADE_NAO_NUMERICA),
        (" ,5", MotivoRecusa.QUANTIDADE_NAO_NUMERICA),
        ("1 234", MotivoRecusa.QUANTIDADE_NAO_NUMERICA),
        ("abc", MotivoRecusa.QUANTIDADE_NAO_NUMERICA),
        ("1" * 13, MotivoRecusa.QUANTIDADE_FORA_DO_LIMITE),  # 13 dígitos: acima do limite
        # P2 #3: o texto tem 12 dígitos inteiros (dentro do limite), mas o
        # arredondamento ROUND_HALF_UP carrega um dígito extra:
        # 999999999999,9995 -> 1000000000000.000 (13 dígitos). O limite
        # precisa ser verificado sobre o valor já quantizado.
        ("9" * 12 + ",9995", MotivoRecusa.QUANTIDADE_FORA_DO_LIMITE),
    ],
    ids=[
        "vazio", "so_espacos", "negativa_inteira", "negativa_arredondaria_a_zero",
        "um_ponto_decimal", "dois_separadores_decimais", "so_decimal_sem_inteiro",
        "espaco_no_meio", "texto_nao_numerico", "treze_digitos",
        "carry_do_arredondamento_ultrapassa_o_limite",
    ],
)
def test_interpretar_quantidade_recusa(texto, motivo_esperado):
    with pytest.raises(leitura_scpi.QuantidadeInvalida) as exc_info:
        leitura_scpi.interpretar_quantidade(texto)
    assert exc_info.value.motivo == motivo_esperado


# ---------------------------------------------------------------------------
# Fixtures inteiras (§5, exemplos normativos combinados)
# ---------------------------------------------------------------------------


def test_carga_inicial_valida_todos_aceitos(csv_fixture):
    resultado = leitura_scpi.ler_registros(csv_fixture("carga_inicial_valida.csv"))

    assert resultado.total_recebidos == 9
    assert len(resultado.aceitos) == 9
    assert resultado.recusas == ()

    por_cadpro = {a.cadpro: a for a in resultado.aceitos}
    assert por_cadpro["000.000.002"].quantidade == Decimal("0.000")
    assert por_cadpro["010.020.032"].quantidade == Decimal("1234.500")
    assert por_cadpro["000.029.742"].quantidade == Decimal("53.400")
    assert por_cadpro["010.020.034"].descricao == 'COTOVELO GALVANIZADO ¾" X 90º'
    assert por_cadpro["010.020.035"].detalhamento == "Observação técnica\n\nlinha adicional"
    assert por_cadpro["004.001.002"].descricao == "TUBO DE ACO CARBONO\nSCHEDULE 40\nGALVANIZADO"
    for cadpro, unidade in [
        ("010.020.030", "UND"), ("010.020.031", "M"),
        ("010.020.032", "MT"), ("010.020.033", "MTS"),
    ]:
        assert por_cadpro[cadpro].unidade == unidade
    # Descrições iguais, códigos distintos (cenário 5 da spec).
    assert por_cadpro["010.020.030"].descricao == por_cadpro["010.020.031"].descricao


def test_carga_inicial_casos_spec_totais_e_motivos_na_ordem_do_arquivo(csv_fixture):
    """Exercita, num único arquivo, quase todos os motivos de recusa e a
    recomposição multilinha, na ordem em que aparecem no arquivo.

    O total do arquivo é `recebidos=22`/`rejeitados=13` (9 aceitos + 13
    recusas — 11 motivos distintos, com `CADPRO_DUPLICADO_NO_ARQUIVO` e
    `ESTRUTURA_INCONSISTENTE` ocorrendo 2 vezes cada), conferido contra os
    bytes do arquivo e igual ao resumo de
    `tests/fixtures/catalogo/README.md`.
    """
    resultado = leitura_scpi.ler_registros(csv_fixture("carga_inicial_casos_spec.csv"))

    assert resultado.total_recebidos == 22
    assert len(resultado.aceitos) == 9
    assert len(resultado.recusas) == 13

    esperado = [
        (2, 2, "", MotivoRecusa.LINHA_NAO_ASSOCIAVEL),
        (16, 16, "020.030.040", MotivoRecusa.ESTRUTURA_INCONSISTENTE),
        (17, 17, "", MotivoRecusa.CADPRO_AUSENTE),
        (18, 18, "2", MotivoRecusa.CADPRO_FORMATO_INVALIDO),
        (19, 19, "090.090.090", MotivoRecusa.CADPRO_DUPLICADO_NO_ARQUIVO),
        (20, 20, "090.090.090", MotivoRecusa.CADPRO_DUPLICADO_NO_ARQUIVO),
        (21, 21, "030.040.050", MotivoRecusa.DESCRICAO_AUSENTE),
        (22, 22, "030.040.051", MotivoRecusa.UNIDADE_AUSENTE),
        (23, 23, "030.040.052", MotivoRecusa.QUANTIDADE_AUSENTE),
        (24, 24, "030.040.053", MotivoRecusa.QUANTIDADE_NAO_NUMERICA),
        (25, 25, "030.040.054", MotivoRecusa.QUANTIDADE_NEGATIVA),
        (26, 26, "030.040.055", MotivoRecusa.QUANTIDADE_FORA_DO_LIMITE),
        (27, 28, "099.099.099", MotivoRecusa.ESTRUTURA_INCONSISTENTE),
    ]
    obtido = [(r.linha_inicial, r.linha_final, r.cadpro, r.motivo) for r in resultado.recusas]
    assert obtido == esperado

    # Linhas físicas de origem corretas nos registros multilinha aceitos.
    por_cadpro = {a.cadpro: a for a in resultado.aceitos}
    assert (por_cadpro["010.020.035"].linha_inicial, por_cadpro["010.020.035"].linha_final) == (
        10, 12,
    )
    assert (por_cadpro["004.001.002"].linha_inicial, por_cadpro["004.001.002"].linha_final) == (
        13, 15,
    )
