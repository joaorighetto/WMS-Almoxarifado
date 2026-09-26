"""Testes do parser de fornecedores (T007, sem banco).

Escrito antes de `fornecedores/leitura_fornecedores.py` existir. O módulo é
importado dentro do fixture `lf` (nunca no topo do arquivo — mesmo padrão
de `tests/test_catalogo_importacao.py`), para que a ausência dele vire erro
de *setup* por teste, não falha de COLETA do arquivo inteiro. Um import de
nível de arquivo quebraria a coleta de `pytest tests/` por inteiro (não só
deste arquivo), porque o pytest agrega a coleta de todos os módulos antes
de rodar qualquer teste.

Cobre `contracts/arquivo-fornecedores.md` (leitura, recusas §1/§3, projeção
§4, os 10 exemplos normativos §5) e `contracts/interface-importacao.md`
(assinaturas fixas). Não cobre banco, sessão nem views — isso é
`test_fornecedores_importacao.py`, `test_fornecedores_dados_minimos.py` e
`test_fornecedores_views_importacao.py`.

Tamanho de arquivo (`ARQUIVO_TAMANHO_EXCEDIDO`) NÃO é testado aqui: como na
001 (`catalogo.leitura_scpi.ler_registros` não verifica tamanho —
`ArquivoImportacaoForm.clean_arquivo` verifica antes de chamar o parser), o
limite de `contracts/arquivo-fornecedores.md` §1 é responsabilidade do
`ArquivoFornecedoresForm` (T016), testado em
`test_fornecedores_views_importacao.py`.
"""

import pytest

from catalogo.leitura_scpi import ArquivoRecusado

# ---------------------------------------------------------------------------
# Helpers de bytes inline — para os casos que não precisam de arquivo de
# fixture inteiro (mesma decisão que tests/fixtures/catalogo/README.md e
# tests/fixtures/fornecedores/README.md documentam para os respectivos
# parsers: mais legível isolado do que como mais um arquivo em disco).
# ---------------------------------------------------------------------------

CABECALHO = "CODIF;NOME;NOM_FANT;INSMF;CODTIP;BLOQ_OPCAO;MSG_BLOQ;TIPO_BLOQ;"


@pytest.fixture
def lf():
    """Módulo `fornecedores.leitura_fornecedores`, importado dentro do
    fixture (ver docstring do módulo) — ainda não existe até T013."""
    import fornecedores.leitura_fornecedores as modulo

    return modulo


def _registro(codif="1", nome="FORNECEDOR", nom_fant="", insmf="", codtip="",
              bloq="S", msg="", tipo=""):
    return f"{codif};{nome};{nom_fant};{insmf};{codtip};{bloq};{msg};{tipo};"


def _arquivo(*linhas, bom=True, terminador="\r\n", terminador_final=True):
    texto = terminador.join(linhas)
    if terminador_final:
        texto += terminador
    prefixo = "﻿" if bom else ""
    return (prefixo + texto).encode("utf-8")


# ---------------------------------------------------------------------------
# Os 10 exemplos normativos de `arquivo-fornecedores.md` §5.
# ---------------------------------------------------------------------------


def test_exemplo_1_tres_registros_validos_um_com_lf_em_coluna_descartada(lf, csv_fornecedores):
    conteudo = csv_fornecedores("tres_registros_validos_com_lf_em_coluna_descartada.csv")

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.total_recebidos == 3
    assert leitura.recusas == ()
    codigos = {aceito.codif for aceito in leitura.aceitos}
    assert codigos == {"500001", "500002", "500003"}
    dois = next(a for a in leitura.aceitos if a.codif == "500002")
    assert dois.nome == "FORNECEDOR DOIS EIRELI"
    assert dois.documento == "98.765.432/0001-10"
    assert dois.bloqueado is False


def test_exemplo_2_registro_com_colunas_deslocadas_e_recusado_vizinhos_aceitos(
    lf, csv_fornecedores
):
    conteudo = csv_fornecedores("registro_com_colunas_deslocadas.csv")

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.total_recebidos == 3
    assert len(leitura.recusas) == 1
    recusa = leitura.recusas[0]
    assert recusa.motivo == "COLUNAS_DESLOCADAS"
    assert recusa.codif == "", "COLUNAS_DESLOCADAS nunca identifica o codif (§3)"
    codigos_aceitos = {aceito.codif for aceito in leitura.aceitos}
    assert codigos_aceitos == {"500011", "500013"}


def test_exemplo_3_codif_invalido_digito_nao_numerico_e_unicode_ambos_recusados(
    lf, csv_fornecedores
):
    conteudo = csv_fornecedores("codif_invalido_digito_nao_numerico_e_unicode.csv")

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.total_recebidos == 2
    assert leitura.aceitos == ()
    assert len(leitura.recusas) == 2
    for recusa in leitura.recusas:
        assert recusa.motivo == "CODIF_INVALIDO"
        assert recusa.codif == "", "CODIF_INVALIDO nunca ecoa o valor recebido (§3)"


def test_exemplo_4_codif_duplicado_ambas_ocorrencias_recusadas(lf, csv_fornecedores):
    conteudo = csv_fornecedores("codif_duplicado_ambos_recusados.csv")

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.total_recebidos == 2
    assert leitura.aceitos == ()
    assert len(leitura.recusas) == 2
    for recusa in leitura.recusas:
        assert recusa.motivo == "CODIF_DUPLICADO"
        assert recusa.codif == "7"
    linhas = {recusa.linha for recusa in leitura.recusas}
    assert len(linhas) == 2, "as duas ocorrências recusadas são linhas distintas"


def test_exemplo_5_bloq_opcao_vazio_e_recusado_vizinho_aceito(lf, csv_fornecedores):
    conteudo = csv_fornecedores("bloq_opcao_vazio_situacao_invalida.csv")

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.total_recebidos == 2
    assert len(leitura.aceitos) == 1
    assert leitura.aceitos[0].codif == "500021"
    assert len(leitura.recusas) == 1
    recusa = leitura.recusas[0]
    assert recusa.motivo == "SITUACAO_BLOQUEIO_INVALIDA"
    assert recusa.codif == "500022", "SITUACAO_BLOQUEIO_INVALIDA identifica o codif (§3)"


def test_exemplo_6_bloqueado_com_motivo_e_aceito_registrado_como_bloqueado(lf, csv_fornecedores):
    conteudo = csv_fornecedores("bloqueado_com_motivo_registrado.csv")

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.total_recebidos == 1
    assert leitura.recusas == ()
    fornecedor = leitura.aceitos[0]
    assert fornecedor.bloqueado is True
    assert fornecedor.motivo_bloqueio == "FORNECEDOR NAO PODE SER UTILIZADO"
    assert fornecedor.tipo_bloqueio == "MUDANCA DE CNPJ"


def test_exemplo_7_insmf_com_caracteres_especiais_e_preservado_como_recebido(lf, csv_fornecedores):
    conteudo = csv_fornecedores("insmf_com_caracteres_especiais.csv")

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.aceitos[0].documento == "../-"


def test_exemplo_8_nomes_iguais_em_codigos_distintos_sao_dois_fornecedores(lf, csv_fornecedores):
    conteudo = csv_fornecedores("nomes_iguais_codigos_distintos.csv")

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.total_recebidos == 2
    assert leitura.recusas == ()
    codigos = {aceito.codif for aceito in leitura.aceitos}
    assert codigos == {"500051", "500052"}
    nomes = {aceito.nome for aceito in leitura.aceitos}
    assert nomes == {"FORNECEDOR PADRAO REPETIDO LTDA"}


def test_exemplo_9_arquivo_so_com_lf_e_recusado_por_terminador_invalido(lf, csv_fornecedores):
    conteudo = csv_fornecedores("somente_lf.csv")

    with pytest.raises(ArquivoRecusado) as excinfo:
        lf.ler_fornecedores(conteudo)

    assert excinfo.value.codigo == "ARQUIVO_TERMINADOR_INVALIDO"


def test_exemplo_10_codif_com_zeros_a_esquerda_distinto_do_codif_sem_zeros(lf, csv_fornecedores):
    conteudo = csv_fornecedores("codif_com_zeros_a_esquerda.csv")

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.total_recebidos == 2
    assert leitura.recusas == ()
    codigos = {aceito.codif for aceito in leitura.aceitos}
    assert codigos == {"007", "7"}


# ---------------------------------------------------------------------------
# Recusas de arquivo do §1 além do exemplo normativo 9.
# ---------------------------------------------------------------------------


def test_arquivo_sem_coluna_obrigatoria_e_recusado_listando_a_coluna(lf, csv_fornecedores):
    conteudo = csv_fornecedores("sem_coluna_bloq.csv")

    with pytest.raises(ArquivoRecusado) as excinfo:
        lf.ler_fornecedores(conteudo)

    assert excinfo.value.codigo == "ARQUIVO_COLUNA_OBRIGATORIA_AUSENTE"
    assert "BLOQ_OPCAO" in excinfo.value.mensagem


def test_arquivo_com_coluna_obrigatoria_duplicada_e_recusado(lf, csv_fornecedores):
    conteudo = csv_fornecedores("coluna_duplicada.csv")

    with pytest.raises(ArquivoRecusado) as excinfo:
        lf.ler_fornecedores(conteudo)

    assert excinfo.value.codigo == "ARQUIVO_COLUNA_DUPLICADA"


def test_arquivo_com_byte_invalido_e_recusado(lf, csv_fornecedores):
    conteudo = csv_fornecedores("byte_invalido.csv")

    with pytest.raises(ArquivoRecusado) as excinfo:
        lf.ler_fornecedores(conteudo)

    assert excinfo.value.codigo == "ARQUIVO_CODIFICACAO_INVALIDA"


def test_arquivo_com_caractere_nulo_e_recusado_indicando_a_linha(lf, csv_fornecedores):
    conteudo = csv_fornecedores("caractere_nulo.csv")

    with pytest.raises(ArquivoRecusado) as excinfo:
        lf.ler_fornecedores(conteudo)

    assert excinfo.value.codigo == "ARQUIVO_CARACTERE_NULO"
    assert "2" in excinfo.value.mensagem, "a mensagem deveria indicar a linha 2"


@pytest.mark.parametrize("nome_fixture", ["vazio.csv", "somente_cabecalho.csv"])
def test_arquivo_vazio_ou_so_com_cabecalho_da_zero_recebidos_sem_erro(
    lf, csv_fornecedores, nome_fixture
):
    conteudo = csv_fornecedores(nome_fixture)

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura == lf.LeituraFornecedores(aceitos=(), recusas=(), total_recebidos=0)


def test_valido_basico_smoke(lf, csv_fornecedores):
    """Sanidade da carga-modelo usada por T008/T009/T011: 4 recebidos, 1
    bloqueado — o comportamento completo de gravação é testado alhures."""
    conteudo = csv_fornecedores("valido_basico.csv")

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.total_recebidos == 4
    assert leitura.recusas == ()
    bloqueados = [a for a in leitura.aceitos if a.bloqueado]
    assert len(bloqueados) == 1
    assert bloqueados[0].codif == "600004"


# ---------------------------------------------------------------------------
# Estrutura (§2): BOM, coluna vazia final, LF isolado, último registro sem
# CRLF, ordem dos motivos (§3), CODIF_DUPLICADO em todas as ocorrências,
# valores preservados sem strip.
# ---------------------------------------------------------------------------


def test_bom_nao_contamina_o_primeiro_valor(lf):
    conteudo = _arquivo(CABECALHO, _registro(codif="1", nome="FORNECEDOR BOM"))

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.aceitos[0].codif == "1", "o BOM não pode grudar no primeiro campo do cabeçalho"


def test_arquivo_sem_bom_e_aceito(lf):
    conteudo = _arquivo(CABECALHO, _registro(codif="1", nome="FORNECEDOR SEM BOM"), bom=False)

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.total_recebidos == 1
    assert leitura.aceitos[0].nome == "FORNECEDOR SEM BOM"


def test_delimitador_final_gera_coluna_vazia_ignorada_no_cabecalho(lf):
    """§2: "Delimitador final gera uma coluna vazia no cabeçalho, que é
    ignorada" — a contagem de campos esperada por registro é derivada do
    cabeçalho como está (8 nomeadas + a vazia do delimitador final = 9
    campos), não hardcoded em 8; um cabeçalho SEM o `;` final (8 campos)
    também precisa funcionar, desde que os registros casem essa mesma
    contagem. `CABECALHO`/`_registro()` (usados no resto deste arquivo) já
    têm delimitador final dos dois lados — este teste cobre o caso sem."""
    cabecalho_sem_delimitador_final = CABECALHO.rstrip(";")
    registro_sem_delimitador_final = _registro(codif="1").rstrip(";")
    conteudo = _arquivo(cabecalho_sem_delimitador_final, registro_sem_delimitador_final)

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.total_recebidos == 1


def test_ultimo_registro_sem_crlf_final_e_aceito(lf):
    conteudo = _arquivo(
        CABECALHO, _registro(codif="1"), _registro(codif="2"), terminador_final=False
    )

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.total_recebidos == 2
    assert {a.codif for a in leitura.aceitos} == {"1", "2"}


def test_registro_vazio_entre_dois_registros_e_ignorado_mas_conta_na_numeracao_de_linha(lf):
    """`\\r\\n\\r\\n` no meio do arquivo produz um segmento vazio ao dividir
    por `\\r\\n` — ignorado (§2), mas a linha seguinte não "pula" um número:
    cabeçalho=1, registro 1=linha 2, vazio=linha 3 (ignorado), registro 2=
    linha 4 — mesma decisão D-1 que a 001 já usa para linha física vazia."""
    conteudo = _arquivo(CABECALHO, _registro(codif="1"), "", _registro(codif="2"))

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.total_recebidos == 2
    registro_dois = next(a for a in leitura.aceitos if a.codif == "2")
    assert registro_dois.linha == 4


def test_lf_isolado_dentro_de_campo_mantido_permanece_no_valor(lf):
    """O LF embutido não precisa estar numa coluna descartada para não
    quebrar o registro — também sobrevive num campo PROJETADO (`NOME`)."""
    conteudo = _arquivo(CABECALHO, _registro(codif="1", nome="FORNECEDOR\nCOM LF NO NOME"))

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.total_recebidos == 1
    assert leitura.aceitos[0].nome == "FORNECEDOR\nCOM LF NO NOME"


def test_ordem_dos_motivos_colunas_deslocadas_antes_de_codif_ausente(lf):
    """§3: `COLUNAS_DESLOCADAS` é o primeiro motivo avaliado — um registro
    com contagem de campos errada E `CODIF` vazio precisa ser recusado como
    `COLUNAS_DESLOCADAS`, não `CODIF_AUSENTE`."""
    linha_com_campo_a_mais = ";FORNECEDOR;;;;S;;;;"  # CODIF vazio + 1 campo extra
    conteudo = _arquivo(CABECALHO, linha_com_campo_a_mais)

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.recusas[0].motivo == "COLUNAS_DESLOCADAS"


def test_ordem_dos_motivos_codif_ausente_antes_de_codif_invalido(lf):
    """`CODIF` vazio precisa cair em `CODIF_AUSENTE`, nunca em
    `CODIF_INVALIDO` (embora `""` também não case `[0-9]+`)."""
    conteudo = _arquivo(CABECALHO, _registro(codif=""))

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.recusas[0].motivo == "CODIF_AUSENTE"


def test_codif_so_com_espacos_e_codif_invalido_nao_codif_ausente(lf):
    """`"   "` não é vazio por `==`, mas fica fora de `[0-9]+` — cai em
    `CODIF_INVALIDO`, não em `CODIF_AUSENTE` (que exige vazio de fato)."""
    conteudo = _arquivo(CABECALHO, _registro(codif="   "))

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.recusas[0].motivo == "CODIF_INVALIDO"


def test_ordem_dos_motivos_codif_invalido_antes_de_nome_ausente(lf):
    conteudo = _arquivo(CABECALHO, _registro(codif="12A", nome=""))

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.recusas[0].motivo == "CODIF_INVALIDO"


def test_ordem_dos_motivos_nome_ausente_antes_de_situacao_bloqueio_invalida(lf):
    conteudo = _arquivo(CABECALHO, _registro(codif="1", nome="", bloq=""))

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.recusas[0].motivo == "NOME_AUSENTE"


def test_nome_so_com_espacos_e_nome_ausente(lf):
    conteudo = _arquivo(CABECALHO, _registro(codif="1", nome="   "))

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.recusas[0].motivo == "NOME_AUSENTE"


def test_ordem_dos_motivos_situacao_bloqueio_antes_de_codif_duplicado(lf):
    """Um `CODIF` duplicado, mas com `BLOQ_OPCAO` inválido numa das
    ocorrências: a ocorrência com `BLOQ_OPCAO` inválido é recusada por
    `SITUACAO_BLOQUEIO_INVALIDA` (avaliada por registro, antes da apuração
    de duplicidade, que só considera registros "ainda aceitos")."""
    conteudo = _arquivo(
        CABECALHO,
        _registro(codif="9", nome="A", bloq="X"),
        _registro(codif="9", nome="B", bloq="S"),
    )

    leitura = lf.ler_fornecedores(conteudo)

    motivos = {recusa.motivo for recusa in leitura.recusas}
    assert "SITUACAO_BLOQUEIO_INVALIDA" in motivos
    # A segunda ocorrência, sozinha (a primeira já não conta como "aceita"
    # antes da recusa por bloqueio), não deveria ser recusada por
    # duplicidade — só ela permanece aceita.
    assert leitura.total_recebidos == 2
    assert len(leitura.aceitos) == 1
    assert leitura.aceitos[0].codif == "9"


def test_codif_duplicado_em_tres_ocorrencias_recusa_todas_as_tres(lf):
    conteudo = _arquivo(
        CABECALHO,
        _registro(codif="42", nome="A"),
        _registro(codif="42", nome="B"),
        _registro(codif="42", nome="C"),
    )

    leitura = lf.ler_fornecedores(conteudo)

    assert leitura.aceitos == ()
    assert len(leitura.recusas) == 3
    assert all(r.motivo == "CODIF_DUPLICADO" for r in leitura.recusas)


def test_detalhe_de_codif_duplicado_cita_a_outra_linha(lf):
    """Contrato §3: "também na linha X" (cabeçalho = linha 1)."""
    conteudo = _arquivo(
        CABECALHO, _registro(codif="42", nome="A"), _registro(codif="42", nome="B")
    )

    detalhes = {r.linha: r.detalhe for r in lf.ler_fornecedores(conteudo).recusas}

    assert detalhes == {2: "também na linha 3.", 3: "também na linha 2."}


def test_detalhe_de_codif_duplicado_cita_ate_tres_linhas_e_conta_o_resto(lf):
    conteudo = _arquivo(
        CABECALHO, *[_registro(codif="42", nome=f"F{indice}") for indice in range(5)]
    )

    detalhes = {r.linha: r.detalhe for r in lf.ler_fornecedores(conteudo).recusas}

    assert detalhes[2] == "também nas linhas 3, 4, 5 e mais 1."
    assert detalhes[6] == "também nas linhas 2, 3, 4 e mais 1."


def test_codif_duplicado_em_massa_gera_detalhe_curto_e_leitura_rapida(lf):
    """Regressão (revisão do code-reviewer, P2, feature 004): o detalhe de
    `CODIF_DUPLICADO` não pode crescer com o número de ocorrências. Antes da
    correção, cada uma das ~20.000 recusas carregava uma string com as
    ~19.999 outras linhas — O(n) por registro, O(n²) no total (~2,8 GB de
    texto para este tamanho), gravado na sessão e no banco
    (`ExcecaoImportacaoFornecedores.detalhe`). Este teste prova tempo e
    tamanho limitados, não um número exato de linhas citadas (decisão de
    formatação, não fixada pelo contrato)."""
    import time

    quantidade = 20_000
    linhas = [
        _registro(codif="500000", nome=f"FORNECEDOR {indice}") for indice in range(quantidade)
    ]
    conteudo = _arquivo(CABECALHO, *linhas)

    inicio = time.perf_counter()
    leitura = lf.ler_fornecedores(conteudo)
    duracao = time.perf_counter() - inicio

    assert duracao < 5, f"leitura de {quantidade} CODIF duplicados levou {duracao:.2f}s"
    assert leitura.aceitos == ()
    assert len(leitura.recusas) == quantidade
    assert all(recusa.motivo == "CODIF_DUPLICADO" for recusa in leitura.recusas)
    assert all(len(recusa.detalhe) <= 200 for recusa in leitura.recusas), (
        "detalhe de CODIF_DUPLICADO precisa ter tamanho limitado, independente de n"
    )


def test_valores_aceitos_sao_preservados_sem_strip(lf):
    """Só o `strip()` de `NOME` decide se ele está vazio (§2, ponto 9) — os
    valores GRAVADOS preservam espaços nas bordas, inclusive `NOME`."""
    conteudo = _arquivo(
        CABECALHO,
        _registro(codif="1", nome="  FORNECEDOR COM ESPACOS  ", nom_fant=" FANTASIA "),
    )

    leitura = lf.ler_fornecedores(conteudo)

    fornecedor = leitura.aceitos[0]
    assert fornecedor.nome == "  FORNECEDOR COM ESPACOS  "
    assert fornecedor.nome_fantasia == " FANTASIA "


def test_bloq_opcao_b_mapeia_para_bloqueado_true_e_s_para_false(lf):
    conteudo = _arquivo(
        CABECALHO,
        _registro(codif="1", bloq="B", msg="Motivo"),
        _registro(codif="2", bloq="S"),
    )

    leitura = lf.ler_fornecedores(conteudo)

    por_codif = {a.codif: a for a in leitura.aceitos}
    assert por_codif["1"].bloqueado is True
    assert por_codif["2"].bloqueado is False


def test_colunas_fora_de_escopo_sao_descartadas_ja_na_leitura(lf):
    """FR-012/`INV-SUPPLIER-004`: uma coluna descartada colocada entre as
    obrigatórias não vaza para nenhum campo do `FornecedorLido`."""
    cabecalho = "CODIF;BANCO;NOME;CONTA;NOM_FANT;INSMF;CODTIP;BLOQ_OPCAO;MSG_BLOQ;TIPO_BLOQ;"
    linha = "1;SENTINELA-BANCO;FORNECEDOR;SENTINELA-CONTA;;;;S;;;"
    conteudo = _arquivo(cabecalho, linha)

    leitura = lf.ler_fornecedores(conteudo)

    fornecedor = leitura.aceitos[0]
    valores = (
        fornecedor.codif, fornecedor.nome, fornecedor.nome_fantasia, fornecedor.documento,
        fornecedor.tipo, fornecedor.motivo_bloqueio, fornecedor.tipo_bloqueio,
    )
    assert not any("SENTINELA" in valor for valor in valores)


# ---------------------------------------------------------------------------
# Detalhe/codif de recusa nunca contêm valor de outra coluna (§3).
# ---------------------------------------------------------------------------


def test_situacao_bloqueio_invalida_nao_ecoa_o_valor_de_bloq_opcao_no_detalhe(lf):
    conteudo = _arquivo(CABECALHO, _registro(codif="1", nome="A", bloq="XPTO_VALOR_ESTRANHO"))

    leitura = lf.ler_fornecedores(conteudo)

    recusa = leitura.recusas[0]
    assert recusa.motivo == "SITUACAO_BLOQUEIO_INVALIDA"
    assert "XPTO_VALOR_ESTRANHO" not in recusa.detalhe


def test_colunas_deslocadas_detalhe_nao_contem_valor_de_nenhum_campo(lf):
    linha_com_campo_a_mais = "1;FORNECEDOR SENTINELA NOME;;;;S;;;;"
    conteudo = _arquivo(CABECALHO, linha_com_campo_a_mais)

    leitura = lf.ler_fornecedores(conteudo)

    recusa = leitura.recusas[0]
    assert recusa.motivo == "COLUNAS_DESLOCADAS"
    assert "FORNECEDOR SENTINELA NOME" not in recusa.detalhe


# ---------------------------------------------------------------------------
# para_json / de_json — ida e volta sem perda, e whitelist de chaves
# (defesa de INV-SUPPLIER-004 na camada mais barata: sem sessão, sem HTTP).
# ---------------------------------------------------------------------------


def test_para_json_de_json_ida_e_volta_sem_perda(lf, csv_fornecedores):
    conteudo = csv_fornecedores("tres_registros_validos_com_lf_em_coluna_descartada.csv")
    leitura = lf.ler_fornecedores(conteudo)

    reconstruida = lf.de_json(lf.para_json(leitura))

    assert reconstruida == leitura


def test_para_json_de_json_ida_e_volta_com_recusas(lf, csv_fornecedores):
    conteudo = csv_fornecedores("registro_com_colunas_deslocadas.csv")
    leitura = lf.ler_fornecedores(conteudo)
    assert leitura.recusas, "pré-condição: a fixture precisa ter recusa para o teste valer algo"

    reconstruida = lf.de_json(lf.para_json(leitura))

    assert reconstruida == leitura


_CHAVES_ACEITO_ESPERADAS = {
    "linha", "codif", "nome", "nome_fantasia", "documento", "tipo",
    "bloqueado", "motivo_bloqueio", "tipo_bloqueio",
}
_CHAVES_RECUSA_ESPERADAS = {"linha", "codif", "motivo", "detalhe"}


def test_para_json_de_cada_aceito_nao_tem_nenhuma_chave_alem_da_projecao_minima(lf):
    """`INV-SUPPLIER-004`: a serialização usada na sessão (`guardar_pedido`,
    T015) só pode carregar exatamente os campos de `FornecedorLido` — uma
    chave extra aqui já seria um jeito de uma coluna descartada vazar para a
    sessão, antes mesmo de qualquer teste HTTP."""
    conteudo = _arquivo(CABECALHO, _registro(codif="1", nome="FORNECEDOR"))
    leitura = lf.ler_fornecedores(conteudo)

    dados = lf.para_json(leitura)

    assert len(dados["aceitos"]) == 1
    assert set(dados["aceitos"][0]) == _CHAVES_ACEITO_ESPERADAS


def test_para_json_de_cada_recusa_nao_tem_nenhuma_chave_alem_da_projecao_minima(lf):
    conteudo = _arquivo(CABECALHO, _registro(codif=""))
    leitura = lf.ler_fornecedores(conteudo)

    dados = lf.para_json(leitura)

    assert len(dados["recusas"]) == 1
    assert set(dados["recusas"][0]) == _CHAVES_RECUSA_ESPERADAS


# ---------------------------------------------------------------------------
# somente_digitos — usada por documento_digitos e busca.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("62.011.929/0001-73", "62011929000173"),
        ("123.456.789-01", "12345678901"),
        ("../-", ""),
        ("", ""),
        ("SEM NENHUM DIGITO", ""),
    ],
)
def test_somente_digitos(lf, entrada, esperado):
    assert lf.somente_digitos(entrada) == esperado
