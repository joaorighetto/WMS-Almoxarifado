"""Gerador (e verificador) das fixtures sintéticas de
`tests/fixtures/fornecedores/` (T003).

Fonte única da verdade para os bytes exatos exigidos por
`contracts/arquivo-fornecedores.md` (BOM opcional, `;` como separador, CRLF
como terminador de registro, LF isolado dentro de campo, byte inválido,
caractere nulo, delimitador final). Escrito em bytes explícitos — nunca via
editor de texto — porque um editor pode normalizar quebras de linha ou
remover o BOM sem avisar; é a mesma preocupação registrada em
`tests/fixtures/catalogo/README.md` ("Os arquivos foram gerados por um
script Python descartável... e verificados byte a byte").

Este módulo NÃO é descoberto por um `pytest` comum: `pyproject.toml` limita
`python_files` a `test_*.py`/`*_test.py`, e `gerar_fixtures.py` não casa
nenhum dos dois — mesmo apontando a suíte inteira para este diretório, a
coleta implícita ignora o arquivo. `test_gerar_e_conferir_fixtures_de_
fornecedores`, abaixo, só roda quando o próprio arquivo é o alvo explícito
(pytest coleta um caminho de arquivo passado explicitamente independente do
`python_files`, com `python_functions` decidindo o que dentro dele é teste):

    pytest tests/fixtures/fornecedores/gerar_fixtures.py -q

Rodar o comando acima grava (ou regrava, deterministicamente) todas as
entradas de `FIXTURES` em disco e confere, byte a byte, que o resultado
bate com o que este módulo gerou — é como as fixtures foram efetivamente
criadas e verificadas nesta task. Não há necessidade de rodar de novo, a
não ser que as fixtures precisem ser regeneradas.

Todos os dados são fictícios: nomes, CNPJ/CPF, códigos e endereços
inventados. Nenhum valor vem de `docs/CSVs/fornecedores.csv` (dado real,
fora do Git, nunca lido por este módulo).
"""

from pathlib import Path

DESTINO = Path(__file__).parent

# As 8 colunas obrigatórias (`contracts/interface-importacao.md`,
# `COLUNAS_OBRIGATORIAS`) intercaladas com as 6 descartadas citadas pela
# task (`BANCO`, `AGENC`, `CONTA`, `PISPASEP`, `ENDER`, `CONTATO`).
# Nenhuma obrigatória fica na primeira posição, de propósito: a leitura de
# fornecedores usa o CABEÇALHO para localizar colunas, nunca a posição
# (research.md R2 — diferente da 001, que exige CADPRO na 1ª coluna).
CAMPOS_PADRAO = [
    "BANCO", "CODIF", "AGENC", "NOME", "CONTA", "NOM_FANT", "PISPASEP",
    "INSMF", "ENDER", "CODTIP", "CONTATO", "BLOQ_OPCAO", "MSG_BLOQ", "TIPO_BLOQ",
]

CABECALHO_PADRAO = ";".join(CAMPOS_PADRAO) + ";"


def _descartaveis(tag):
    """Preenchimento plausível e neutro das 6 colunas descartadas, só para
    realismo — nenhum teste depende destes valores por definição (são
    descartados já na leitura, `contracts/arquivo-fornecedores.md` §4)."""
    return {
        "BANCO": "341",
        "AGENC": f"000{tag}",
        "CONTA": f"1234{tag}-6",
        "PISPASEP": "123.45678.90-1",
        "ENDER": f"RUA TESTE {tag}, 100",
        "CONTATO": f"contato{tag}@teste.invalido",
    }


def _campos(**valores):
    """Lista de 15 campos (14 nomeados + o vazio final do delimitador),
    na ordem de `CAMPOS_PADRAO`. Valor ausente vira string vazia."""
    return [valores.get(nome, "") for nome in CAMPOS_PADRAO] + [""]


def _linha(**valores):
    return ";".join(_campos(**valores))


def _linha_com_campo_extra(indice, **valores):
    """Mesma linha de `_linha`, com um campo vazio extra inserido no
    índice informado — simula um `;` a mais no arquivo real (exemplo
    normativo §5.2, `COLUNAS_DESLOCADAS`)."""
    campos = _campos(**valores)
    campos.insert(indice, "")
    return ";".join(campos)


def _arquivo(cabecalho, *linhas, bom=True):
    """Junta cabeçalho e registros com CRLF — inclusive depois do último
    registro, como o arquivo real — e prefixa o BOM UTF-8 (`\\ufeff`, que
    vira `EF BB BF` ao codificar)."""
    texto = "\r\n".join([cabecalho, *linhas]) + "\r\n"
    prefixo = "﻿" if bom else ""
    return (prefixo + texto).encode("utf-8")


def _reimport_linha(codif, nome, nom_fant, insmf, *, bloq="S", msg="", tipo="", tag):
    return _linha(
        CODIF=codif, NOME=nome, NOM_FANT=nom_fant, INSMF=insmf, CODTIP="01",
        BLOQ_OPCAO=bloq, MSG_BLOQ=msg, TIPO_BLOQ=tipo, **_descartaveis(tag),
    )


def _construir_fixtures():
    fixtures = {}

    # -----------------------------------------------------------------
    # Os 10 exemplos normativos de `arquivo-fornecedores.md` §5. O
    # exemplo 9 (arquivo só com LF) é o mesmo arquivo que T003 pede sob o
    # nome fixo `somente_lf.csv` — não duplicado sob dois nomes.
    # -----------------------------------------------------------------

    # §5.1 — três registros válidos, um com LF dentro de coluna descartada.
    fixtures["tres_registros_validos_com_lf_em_coluna_descartada.csv"] = _arquivo(
        CABECALHO_PADRAO,
        _linha(CODIF="500001", NOME="FORNECEDOR UM LTDA", NOM_FANT="FORN UM",
               INSMF="12.345.678/0001-90", CODTIP="01", BLOQ_OPCAO="S",
               **_descartaveis("01")),
        _linha(CODIF="500002", NOME="FORNECEDOR DOIS EIRELI", NOM_FANT="",
               INSMF="98.765.432/0001-10", CODTIP="01", BLOQ_OPCAO="S",
               BANCO="341", AGENC="0002", CONTA="12342-6",
               PISPASEP="123.45678.90-1", ENDER="RUA TESTE 02, 100",
               CONTATO="Tel: (11) 4000-0000\nRamal 42"),
        _linha(CODIF="500003", NOME="FORNECEDOR TRES ME", NOM_FANT="FORN TRES",
               INSMF="111.222.333-44", CODTIP="02", BLOQ_OPCAO="S",
               **_descartaveis("03")),
    )

    # §5.2 — registro com um `;` a mais → COLUNAS_DESLOCADAS; vizinhos aceitos.
    fixtures["registro_com_colunas_deslocadas.csv"] = _arquivo(
        CABECALHO_PADRAO,
        _linha(CODIF="500011", NOME="FORNECEDOR ONZE LTDA", NOM_FANT="ONZE",
               INSMF="22.333.444/0001-55", CODTIP="01", BLOQ_OPCAO="S",
               **_descartaveis("11")),
        _linha_com_campo_extra(
            6, CODIF="500012", NOME="FORNECEDOR DOZE DESLOCADO",
            NOM_FANT="DOZE", INSMF="33.444.555/0001-66", CODTIP="01",
            BLOQ_OPCAO="S", **_descartaveis("12"),
        ),
        _linha(CODIF="500013", NOME="FORNECEDOR TREZE ME", NOM_FANT="TREZE",
               INSMF="55.666.777/0001-88", CODTIP="01", BLOQ_OPCAO="S",
               **_descartaveis("13")),
    )

    # §5.3 — CODIF "12A" e CODIF "٣" (dígito Unicode) → CODIF_INVALIDO.
    # `[0-9]` nunca `\d`: "٣" (U+0663, ARABIC-INDIC DIGIT THREE) precisa
    # recusar, mesmo sendo um "dígito" para `str.isdigit()`/`\d`.
    fixtures["codif_invalido_digito_nao_numerico_e_unicode.csv"] = _arquivo(
        CABECALHO_PADRAO,
        _linha(CODIF="12A", NOME="FORNECEDOR CODIGO INVALIDO A", CODTIP="03",
               BLOQ_OPCAO="S", **_descartaveis("21")),
        _linha(CODIF="٣", NOME="FORNECEDOR CODIGO INVALIDO B", CODTIP="03",
               BLOQ_OPCAO="S", **_descartaveis("22")),
    )

    # §5.4 — dois registros com CODIF "7" → os dois recusados (CODIF_DUPLICADO).
    fixtures["codif_duplicado_ambos_recusados.csv"] = _arquivo(
        CABECALHO_PADRAO,
        _linha(CODIF="7", NOME="FORNECEDOR SETE PRIMEIRA OCORRENCIA",
               BLOQ_OPCAO="S", **_descartaveis("31")),
        _linha(CODIF="7", NOME="FORNECEDOR SETE SEGUNDA OCORRENCIA",
               BLOQ_OPCAO="S", **_descartaveis("32")),
    )

    # §5.5 — BLOQ_OPCAO vazio → SITUACAO_BLOQUEIO_INVALIDA; vizinho aceito.
    fixtures["bloq_opcao_vazio_situacao_invalida.csv"] = _arquivo(
        CABECALHO_PADRAO,
        _linha(CODIF="500021", NOME="FORNECEDOR VIZINHO ACEITO",
               BLOQ_OPCAO="S", **_descartaveis("41")),
        _linha(CODIF="500022", NOME="FORNECEDOR SITUACAO VAZIA",
               BLOQ_OPCAO="", **_descartaveis("42")),
    )

    # §5.6 — BLOQ_OPCAO "B" com MSG_BLOQ preenchido → aceito, bloqueado, com motivo.
    fixtures["bloqueado_com_motivo_registrado.csv"] = _arquivo(
        CABECALHO_PADRAO,
        _linha(CODIF="500031", NOME="FORNECEDOR BLOQUEADO COM MOTIVO",
               NOM_FANT="BLOQ MOTIVO", INSMF="66.777.888/0001-99", CODTIP="01",
               BLOQ_OPCAO="B", MSG_BLOQ="FORNECEDOR NAO PODE SER UTILIZADO",
               TIPO_BLOQ="MUDANCA DE CNPJ", **_descartaveis("51")),
    )

    # §5.7 — INSMF "../-" → aceito, preservado como recebido.
    fixtures["insmf_com_caracteres_especiais.csv"] = _arquivo(
        CABECALHO_PADRAO,
        _linha(CODIF="500041", NOME="FORNECEDOR DOCUMENTO ESPECIAL",
               INSMF="../-", CODTIP="09", BLOQ_OPCAO="S", **_descartaveis("61")),
    )

    # §5.8 — nomes iguais em códigos distintos → dois fornecedores.
    fixtures["nomes_iguais_codigos_distintos.csv"] = _arquivo(
        CABECALHO_PADRAO,
        _linha(CODIF="500051", NOME="FORNECEDOR PADRAO REPETIDO LTDA",
               NOM_FANT="PADRAO", INSMF="11.111.111/0001-01", CODTIP="01",
               BLOQ_OPCAO="S", **_descartaveis("71")),
        _linha(CODIF="500052", NOME="FORNECEDOR PADRAO REPETIDO LTDA",
               NOM_FANT="PADRAO", INSMF="22.222.222/0001-02", CODTIP="01",
               BLOQ_OPCAO="S", **_descartaveis("72")),
    )

    # §5.9 — arquivo só com LF (nenhum CRLF) → ARQUIVO_TERMINADOR_INVALIDO.
    # Também é o `somente_lf.csv` exigido nominalmente por T003 — um único
    # arquivo cobre as duas exigências, sem duplicar conteúdo sob dois nomes.
    fixtures["somente_lf.csv"] = (
        "﻿"
        + "\n".join([
            CABECALHO_PADRAO,
            _linha(CODIF="500061", NOME="FORNECEDOR SOMENTE LF",
                   BLOQ_OPCAO="S", **_descartaveis("81")),
        ])
        + "\n"
    ).encode("utf-8")

    # §5.10 — CODIF "007" aceito, distinto de "7".
    fixtures["codif_com_zeros_a_esquerda.csv"] = _arquivo(
        CABECALHO_PADRAO,
        _linha(CODIF="007", NOME="FORNECEDOR ZEROS A ESQUERDA",
               BLOQ_OPCAO="S", **_descartaveis("91")),
        _linha(CODIF="7", NOME="FORNECEDOR SETE SEM ZEROS",
               BLOQ_OPCAO="S", **_descartaveis("92")),
    )

    # -----------------------------------------------------------------
    # Fixtures adicionais exigidas nominalmente por T003.
    # -----------------------------------------------------------------

    # `valido_basico.csv` — smoke test da carga inicial (US1): 4 registros,
    # 1 bloqueado, cobrindo tipo com e sem documento.
    fixtures["valido_basico.csv"] = _arquivo(
        CABECALHO_PADRAO,
        _linha(CODIF="600001", NOME="FORNECEDOR ALFA COMERCIO LTDA",
               NOM_FANT="ALFA COM", INSMF="11.111.111/0001-11", CODTIP="01",
               BLOQ_OPCAO="S", **_descartaveis("01")),
        _linha(CODIF="600002", NOME="FORNECEDOR BETA SERVICOS ME",
               NOM_FANT="", INSMF="222.222.222-22", CODTIP="02",
               BLOQ_OPCAO="S", **_descartaveis("02")),
        _linha(CODIF="600003", NOME="FORNECEDOR GAMA SEM DOCUMENTO",
               NOM_FANT="GAMA", INSMF="", CODTIP="03",
               BLOQ_OPCAO="S", **_descartaveis("03")),
        _linha(CODIF="600004", NOME="FORNECEDOR DELTA BLOQUEADO",
               NOM_FANT="DELTA", INSMF="33.333.333/0001-33", CODTIP="01",
               BLOQ_OPCAO="B", MSG_BLOQ="FORNECEDOR NAO PODE SER UTILIZADO",
               TIPO_BLOQ="MUDANCA DE CNPJ", **_descartaveis("04")),
    )

    # `sentinelas.csv` — INV-SUPPLIER-004 (T009): valor-sentinela único por
    # coluna descartada, igual nas duas linhas, com LF embutido em CONTATO.
    _sentinelas = {
        "BANCO": "SENTINELA-BANCO-9137",
        "AGENC": "SENTINELA-AGENC-9137",
        "CONTA": "SENTINELA-CONTA-9137",
        "PISPASEP": "SENTINELA-PISPASEP-9137",
        "ENDER": "SENTINELA-ENDER-9137",
        "CONTATO": "SENTINELA-CONTATO-9137-LINHA1\nSENTINELA-CONTATO-9137-LINHA2",
    }
    fixtures["sentinelas.csv"] = _arquivo(
        CABECALHO_PADRAO,
        _linha(CODIF="600011", NOME="FORNECEDOR SENTINELA UM",
               NOM_FANT="SENT UM", INSMF="12.121.212/0001-12", CODTIP="01",
               BLOQ_OPCAO="S", **_sentinelas),
        _linha(CODIF="600012", NOME="FORNECEDOR SENTINELA DOIS",
               NOM_FANT="SENT DOIS", INSMF="34.343.434/0001-34", CODTIP="01",
               BLOQ_OPCAO="B", MSG_BLOQ="FORNECEDOR NAO PODE SER UTILIZADO",
               TIPO_BLOQ="MUDANCA DE CNPJ", **_sentinelas),
    )

    # `sem_coluna_bloq.csv` — cabeçalho sem BLOQ_OPCAO (uma das 8
    # obrigatórias) → ARQUIVO_COLUNA_OBRIGATORIA_AUSENTE.
    campos_sem_bloq = [c for c in CAMPOS_PADRAO if c != "BLOQ_OPCAO"]
    cabecalho_sem_bloq = ";".join(campos_sem_bloq) + ";"
    valores_sem_bloq = {
        "BANCO": "341", "CODIF": "600021", "AGENC": "0001",
        "NOME": "FORNECEDOR SEM COLUNA BLOQ", "CONTA": "12345-6",
        "NOM_FANT": "", "PISPASEP": "123.45678.90-1",
        "INSMF": "", "ENDER": "RUA TESTE, 100", "CODTIP": "03",
        "CONTATO": "contato@teste.invalido", "MSG_BLOQ": "", "TIPO_BLOQ": "",
    }
    linha_sem_bloq = ";".join(valores_sem_bloq.get(nome, "") for nome in campos_sem_bloq) + ";"
    fixtures["sem_coluna_bloq.csv"] = _arquivo(cabecalho_sem_bloq, linha_sem_bloq)

    # -----------------------------------------------------------------
    # Fixtures opcionais de recusa de arquivo (§1), acrescentadas por
    # decisão do test-engineer — completam os códigos do contrato que os
    # 10 exemplos normativos não cobrem.
    # -----------------------------------------------------------------

    # `coluna_duplicada.csv` — NOME aparece duas vezes → ARQUIVO_COLUNA_DUPLICADA.
    campos_duplicados = list(CAMPOS_PADRAO)
    campos_duplicados[2] = "NOME"  # substitui AGENC por um segundo NOME
    cabecalho_duplicado = ";".join(campos_duplicados) + ";"
    linha_duplicada = ";".join("" for _ in campos_duplicados) + ";"
    fixtures["coluna_duplicada.csv"] = _arquivo(cabecalho_duplicado, linha_duplicada)

    # `byte_invalido.csv` — byte inválido em UTF-8 ao final do arquivo
    # (mesma técnica de `tests/fixtures/catalogo/codificacao_invalida.csv`).
    texto_valido = (
        "﻿"
        + "\r\n".join([
            CABECALHO_PADRAO,
            _linha(CODIF="600031", NOME="FORNECEDOR BYTE INVALIDO",
                   BLOQ_OPCAO="S", **_descartaveis("31")),
        ])
        + "\r\n"
    )
    fixtures["byte_invalido.csv"] = texto_valido.encode("utf-8") + b"\xff"

    # `caractere_nulo.csv` — U+0000 dentro de NOME (UTF-8 válido, recusado
    # mesmo assim porque o PostgreSQL não aceita NUL em coluna de texto).
    fixtures["caractere_nulo.csv"] = _arquivo(
        CABECALHO_PADRAO,
        _linha(CODIF="600041", NOME="FORNECEDOR NULO\x00LTDA",
               BLOQ_OPCAO="S", **_descartaveis("41")),
    )

    # `somente_cabecalho.csv` / `vazio.csv` — zero recebidos, sem erro.
    fixtures["somente_cabecalho.csv"] = _arquivo(CABECALHO_PADRAO)
    fixtures["vazio.csv"] = b""

    # -----------------------------------------------------------------
    # US4 — reimportação (T003, T028): base + 4 variações pedidas
    # nominalmente (nome alterado, bloqueio S→B, registro removido,
    # variação idêntica) + 1 acrescentada pelo test-engineer (bloqueio
    # B→S — Acceptance Scenario 3 da US4, sem fixture nominal no T003).
    # -----------------------------------------------------------------

    base_r1 = _reimport_linha("700001", "FORNECEDOR ALFA REIMPORT", "ALFA",
                               "10.101.010/0001-01", tag="01")
    base_r2 = _reimport_linha("700002", "FORNECEDOR BETA REIMPORT", "BETA",
                               "20.202.020/0001-02", tag="02")
    base_r3 = _reimport_linha(
        "700003", "FORNECEDOR GAMA REIMPORT", "GAMA", "30.303.030/0001-03",
        bloq="B", msg="FORNECEDOR NAO PODE SER UTILIZADO",
        tipo="MUDANCA DE CNPJ", tag="03",
    )
    base_r4 = _reimport_linha("700004", "FORNECEDOR DELTA REIMPORT", "DELTA",
                               "40.404.040/0001-04", tag="04")
    base_r5 = _reimport_linha("700005", "FORNECEDOR EPSILON REIMPORT", "EPSILON",
                               "50.505.050/0001-05", tag="05")

    fixtures["reimportacao_base.csv"] = _arquivo(
        CABECALHO_PADRAO, base_r1, base_r2, base_r3, base_r4, base_r5,
    )
    # Byte-idêntico ao base — mesmo arquivo reenviado sem mudança nenhuma
    # (cenário "mesmo arquivo duas vezes → 0 alterações", T028).
    fixtures["reimportacao_identica.csv"] = fixtures["reimportacao_base.csv"]

    nome_alterado_r1 = _reimport_linha(
        "700001", "FORNECEDOR ALFA REIMPORT REVISADO", "ALFA",
        "10.101.010/0001-01", tag="01",
    )
    fixtures["reimportacao_nome_alterado.csv"] = _arquivo(
        CABECALHO_PADRAO, nome_alterado_r1, base_r2, base_r3, base_r4, base_r5,
    )

    bloqueio_s_para_b_r2 = _reimport_linha(
        "700002", "FORNECEDOR BETA REIMPORT", "BETA", "20.202.020/0001-02",
        bloq="B", msg="FORNECEDOR NAO PODE SER UTILIZADO",
        tipo="MUDANCA DE CNPJ", tag="02",
    )
    fixtures["reimportacao_bloqueio_s_para_b.csv"] = _arquivo(
        CABECALHO_PADRAO, base_r1, bloqueio_s_para_b_r2, base_r3, base_r4, base_r5,
    )

    bloqueio_b_para_s_r3 = _reimport_linha(
        "700003", "FORNECEDOR GAMA REIMPORT", "GAMA", "30.303.030/0001-03",
        bloq="S", tag="03",
    )
    fixtures["reimportacao_bloqueio_b_para_s.csv"] = _arquivo(
        CABECALHO_PADRAO, base_r1, base_r2, bloqueio_b_para_s_r3, base_r4, base_r5,
    )

    fixtures["reimportacao_registro_removido.csv"] = _arquivo(
        CABECALHO_PADRAO, base_r1, base_r2, base_r3, base_r5,
    )

    return fixtures


FIXTURES = _construir_fixtures()


# ---------------------------------------------------------------------------
# Geração e verificação (invocação explícita — ver docstring do módulo).
# ---------------------------------------------------------------------------


def test_gerar_e_conferir_fixtures_de_fornecedores():
    """Grava cada entrada de `FIXTURES` em `tests/fixtures/fornecedores/` e
    confere, byte a byte, que o arquivo relido bate com o que este módulo
    gerou, mais um conjunto de invariantes estruturais que protegem
    especificamente os casos sensíveis a byte (BOM, CRLF, LF isolado, byte
    inválido, caractere nulo, sentinelas). Não roda num `pytest` comum —
    ver docstring do módulo para o comando explícito."""
    for nome, conteudo in FIXTURES.items():
        caminho = DESTINO / nome
        caminho.write_bytes(conteudo)
        assert caminho.read_bytes() == conteudo, (
            f"{nome}: bytes relidos do disco divergem do que este módulo gerou"
        )

    assert FIXTURES["vazio.csv"] == b""

    somente_lf = FIXTURES["somente_lf.csv"]
    assert b"\r\n" not in somente_lf, "somente_lf.csv não pode conter nenhum CRLF"
    assert b"\n" in somente_lf

    byte_invalido = FIXTURES["byte_invalido.csv"]
    try:
        byte_invalido.decode("utf-8")
    except UnicodeDecodeError:
        pass
    else:
        raise AssertionError("byte_invalido.csv deveria ter um byte UTF-8 inválido")

    caractere_nulo = FIXTURES["caractere_nulo.csv"]
    assert b"\x00" in caractere_nulo
    caractere_nulo.decode("utf-8")  # não pode levantar — U+0000 é UTF-8 válido

    lf_embutido = FIXTURES["tres_registros_validos_com_lf_em_coluna_descartada.csv"]
    assert b"Ramal 42" in lf_embutido, "LF embutido em CONTATO não sobreviveu à geração"

    sentinelas = FIXTURES["sentinelas.csv"]
    for coluna in ("BANCO", "AGENC", "CONTA", "PISPASEP", "ENDER", "CONTATO"):
        assert f"SENTINELA-{coluna}-9137".encode() in sentinelas, (
            f"sentinelas.csv sem o valor-sentinela esperado da coluna {coluna}"
        )
    assert b"SENTINELA-CONTATO-9137-LINHA1\nSENTINELA-CONTATO-9137-LINHA2" in sentinelas, (
        "sentinelas.csv precisa de um LF isolado dentro de CONTATO"
    )

    assert FIXTURES["reimportacao_identica.csv"] == FIXTURES["reimportacao_base.csv"]

    for nome, conteudo in FIXTURES.items():
        if nome == "vazio.csv":
            continue
        assert conteudo.startswith(b"\xef\xbb\xbf"), f"{nome}: sem BOM UTF-8 (EF BB BF)"

    print(f"{len(FIXTURES)} fixtures gravadas em {DESTINO}")
