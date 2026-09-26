"""Validação contra o arquivo real do SCPI (T032, Fase 7 — Polish).

Aceite pendente de SC-001 a SC-003 e SC-006. O export real não é versionado
— existe só localmente (`docs/CSVs/fornecedores.csv`, ignorado pelo Git por
conter CPF, conta bancária e PIS). Este teste lê **só o caminho** da
variável de ambiente `FORNECEDORES_CSV_REAL`; sem ela, é *skipped* (mesmo
padrão de `tests/test_catalogo_arquivo_real.py`, `SCPI_CSV_REAL`).

Sem marcador de "lento": o projeto não define nenhum em
`pyproject.toml`/`pytest.ini` (o mesmo já vale para `test_catalogo_arquivo_
real.py`).

**Regras críticas de segurança de dados (o arquivo tem CPF, conta bancária,
PIS) — todas obrigatórias, e o motivo de cada técnica abaixo:**

1. Este arquivo NUNCA foi executado com o arquivo real por quem o escreveu
   (`test-engineer`) — só a partir dos contratos (`contracts/arquivo-
   fornecedores.md`, `spec.md` §"análise do arquivo real",
   `research.md`). Quem tem o arquivo local roda e confere.
2. NENHUMA asserção compara diretamente strings/dicts/listas vindos do
   arquivo (`assert fornecedor.nome == campos[...]`) — pytest reescreve
   `assert` e mostra os dois operandos no diff de falha, o que vazaria o
   dado pessoal na saída do teste. Em vez disso, toda comparação de CAMPO
   acontece dentro de um `if`/loop comum (nunca dentro de uma expressão de
   `assert`) e só CONTADORES (nunca os valores) alimentam a mensagem do
   `assert` final. O único dado do arquivo que pode aparecer numa mensagem
   é `codif` (== linha/identificador, não dado pessoal, já permitido
   explicitamente).
3. A checagem "nenhum dado de coluna descartada no banco/sessão" (SC-003)
   deriva, em memória, o CONJUNTO dos valores das colunas descartadas com
   ≥ 6 caracteres, excluindo os que também aparecem em alguma coluna
   mínima (`_valores_exclusivos_de_colunas_descartadas`) — e depois
   verifica só PERTINÊNCIA A CONJUNTO (`valor in conjunto`, O(1), nunca
   substring/regex sobre texto livre) entre esse conjunto e os valores
   efetivamente gravados (banco) ou projetados (sessão). Novamente, só a
   CONTAGEM de interseções entra na mensagem de falha.
4. A conferência de campo a campo (SC-001) usa uma leitura PRÓPRIA e
   mínima deste arquivo de teste (`_ler_arquivo_independente`, abaixo:
   decodificação, split por `\\r\\n` e por `;`, cabeçalho por nome) —
   nunca `fornecedores.leitura_fornecedores.ler_fornecedores` — para não
   comparar o parser real contra si mesmo (um bug de leitura passaria
   despercebido se os dois lados usassem o mesmo código).
"""

import base64
import hashlib
import json
import os
import pathlib
import re
import time
import uuid
import zlib

import pytest
from django.apps import apps
from django.contrib.sessions.backends.db import SessionStore
from django.db import models as djmodels
from django.db import transaction

from fornecedores.models import Fornecedor

MOTIVO_SKIP = (
    "arquivo real de fornecedores do SCPI não disponível (defina "
    "FORNECEDORES_CSV_REAL para rodar este teste localmente)"
)

# As 8 colunas mínimas mantidas (FR-012, `contracts/interface-importacao.md`
# `COLUNAS_OBRIGATORIAS`) — usadas só para SABER quais índices do cabeçalho
# excluir da varredura de "colunas descartadas" (regra 3 acima); nenhuma
# delas, por si só, é um dado sensível.
_COLUNAS_MINIMAS = (
    "CODIF", "NOME", "NOM_FANT", "INSMF", "CODTIP",
    "BLOQ_OPCAO", "MSG_BLOQ", "TIPO_BLOQ",
)

_LIMITE_MINIMO_VALOR_SENSIVEL = 6


def _conteudo_do_arquivo_real() -> bytes:
    caminho = os.environ.get("FORNECEDORES_CSV_REAL")
    if not caminho:
        pytest.skip(MOTIVO_SKIP)
    return pathlib.Path(caminho).read_bytes()


# ---------------------------------------------------------------------------
# Leitura independente mínima (regra 4) — nunca usa
# fornecedores.leitura_fornecedores.
# ---------------------------------------------------------------------------


def _ler_arquivo_independente(conteudo: bytes):
    """Retorna `(cabecalho, indices_minimos, registros)`, em que
    `registros` é uma lista de `(numero_da_linha, campos)`. Não aplica
    NENHUMA das regras de recusa de `contracts/arquivo-fornecedores.md`
    §1/§3 — só separa o arquivo em campos, para servir de base de
    comparação independente do parser real."""
    texto = conteudo.decode("utf-8-sig")
    linhas = texto.split("\r\n")
    if linhas and linhas[-1] == "":
        linhas.pop()

    cabecalho = linhas[0].split(";")
    indices_minimos = {nome: cabecalho.index(nome) for nome in _COLUNAS_MINIMAS}

    registros = []
    for numero, linha in enumerate(linhas[1:], start=2):
        if linha == "":
            continue
        registros.append((numero, linha.split(";")))

    return cabecalho, indices_minimos, registros


def _valores_exclusivos_de_colunas_descartadas(cabecalho, indices_minimos, registros):
    """Conjunto dos valores (≥ 6 caracteres) que aparecem em alguma coluna
    DESCARTADA (fora das 8 mínimas) e NUNCA aparecem em nenhuma coluna
    mínima — candidatos a "vazamento" para a checagem de SC-003 (regra 3).
    Construído inteiramente em memória, sem nenhuma escrita em disco/log."""
    indices_descartados = [
        indice for indice in range(len(cabecalho)) if indice not in indices_minimos.values()
    ]

    valores_em_colunas_minimas = set()
    valores_em_colunas_descartadas = set()
    for _numero, campos in registros:
        for indice in indices_minimos.values():
            if indice < len(campos) and campos[indice]:
                valores_em_colunas_minimas.add(campos[indice])
                # Derivado legítimo de coluna mínima (`documento_digitos` =
                # só os dígitos de INSMF): uma coluna descartada pode trazer o
                # mesmo documento sem formatação, e isso não é vazamento.
                valores_em_colunas_minimas.add(re.sub(r"[^0-9]", "", campos[indice]))
        for indice in indices_descartados:
            if indice < len(campos):
                valor = campos[indice]
                if len(valor) >= _LIMITE_MINIMO_VALOR_SENSIVEL:
                    valores_em_colunas_descartadas.add(valor)

    return valores_em_colunas_descartadas - valores_em_colunas_minimas


# ---------------------------------------------------------------------------
# Contadores de vazamento (regras 2 e 3) — nunca retornam os valores em si.
# ---------------------------------------------------------------------------


def _vazamentos_por_campo_de_modelo(valores_sensiveis: set) -> dict:
    """Para cada model/campo de texto de `fornecedores`, conta quantos
    valores GRAVADOS coincidem, byte a byte, com algum valor sensível —
    nunca expõe qual valor é. Genérico por introspecção (como
    `tests/test_fornecedores_dados_minimos.py`): um campo novo que algum
    dia vazasse dado seria pego sem precisar editar este teste."""
    if not valores_sensiveis:
        return {}
    resultado = {}
    for model in apps.get_app_config("fornecedores").get_models():
        for field in model._meta.get_fields():
            if isinstance(field, (djmodels.CharField, djmodels.TextField)):
                valores_gravados = set(model.objects.values_list(field.name, flat=True))
                interseccao = valores_gravados & valores_sensiveis
                if interseccao:
                    resultado[f"{model.__name__}.{field.name}"] = len(interseccao)
    return resultado


def _vazamentos_na_sessao(dados_sessao: dict, valores_sensiveis: set) -> int:
    if not valores_sensiveis:
        return 0
    texto_leitura = zlib.decompress(base64.b64decode(dados_sessao["leitura"])).decode("utf-8")
    dados = json.loads(texto_leitura)

    contagem = 0
    campos_texto = (
        "nome", "nome_fantasia", "documento", "tipo", "motivo_bloqueio", "tipo_bloqueio",
    )
    for aceito in dados["aceitos"]:
        for campo in campos_texto:
            if aceito.get(campo) in valores_sensiveis:
                contagem += 1
    for recusa in dados["recusas"]:
        if recusa.get("codif") in valores_sensiveis or recusa.get("detalhe") in valores_sensiveis:
            contagem += 1
    return contagem


# ---------------------------------------------------------------------------
# Teste principal.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_carga_do_arquivo_real_confere_agregados_campos_e_ausencia_de_vazamento(
    chefe_almoxarifado,
):
    conteudo = _conteudo_do_arquivo_real()

    cabecalho, indices_minimos, registros = _ler_arquivo_independente(conteudo)

    # Pré-condição estrutural (sem valor nenhum na mensagem): todo registro
    # tem a mesma contagem de campos do cabeçalho — SC-001/SC-004 esperam
    # 0 rejeitados, então nenhum "deslocamento de colunas" é esperado aqui.
    numeros_com_contagem_diferente = [
        numero for numero, campos in registros if len(campos) != len(cabecalho)
    ]
    assert not numeros_com_contagem_diferente, (
        f"{len(numeros_com_contagem_diferente)} linha(s) com número de campos diferente do "
        f"cabeçalho (linhas: {numeros_com_contagem_diferente[:10]})"
    )

    campos_por_codif = {
        campos[indices_minimos["CODIF"]]: campos for _numero, campos in registros
    }
    assert len(campos_por_codif) == len(registros), (
        f"{len(registros) - len(campos_por_codif)} CODIF duplicado(s) na leitura independente "
        "— SC-001/SC-004 esperam todos únicos"
    )

    # -----------------------------------------------------------------
    # Carga (via a interface real de domínio — não a leitura independente
    # acima, que serve só de referência de comparação).
    # -----------------------------------------------------------------
    from fornecedores import importacao
    from fornecedores import leitura_fornecedores as lf

    sessao = SessionStore()
    inicio_previa = time.perf_counter()
    pedido = importacao.guardar_pedido(
        sessao, nome_arquivo="fornecedores_real.csv", conteudo=conteudo
    )
    plano = importacao.calcular_plano(pedido.leitura, pedido.sha256)
    duracao_previa = time.perf_counter() - inicio_previa
    assert duracao_previa < 30, f"prévia levou {duracao_previa:.1f}s (SC-006 exige < 30s)"

    inicio_confirmacao = time.perf_counter()
    execucao = importacao.confirmar_importacao(pedido, plano.impressao_digital, chefe_almoxarifado)
    duracao_confirmacao = time.perf_counter() - inicio_confirmacao
    assert duracao_confirmacao < 30, f"confirmação levou {duracao_confirmacao:.1f}s (SC-006)"

    # -----------------------------------------------------------------
    # SC-001/SC-004: agregados.
    # -----------------------------------------------------------------
    assert execucao.total_recebidos == 10_035
    assert execucao.total_inseridos == 10_035
    assert execucao.total_rejeitados == 0
    assert Fornecedor.objects.count() == 10_035

    # SC-002: 18 bloqueados, nenhum outro.
    assert Fornecedor.objects.filter(bloqueado=True).count() == 18

    # -----------------------------------------------------------------
    # SC-001: campos gravados conferem, caractere a caractere, com a
    # leitura independente — só contadores na mensagem (regra 2).
    # -----------------------------------------------------------------
    campos_com_divergencia: dict[str, int] = {}
    codifs_com_alguma_divergencia: list[str] = []
    codifs_ausentes_na_leitura_independente: list[str] = []

    idx = indices_minimos
    for fornecedor in Fornecedor.objects.all():
        campos_arquivo = campos_por_codif.get(fornecedor.codif)
        if campos_arquivo is None:
            codifs_ausentes_na_leitura_independente.append(fornecedor.codif)
            continue

        divergiu = False
        comparacoes = (
            ("nome", fornecedor.nome, campos_arquivo[idx["NOME"]]),
            ("nome_fantasia", fornecedor.nome_fantasia, campos_arquivo[idx["NOM_FANT"]]),
            ("documento", fornecedor.documento, campos_arquivo[idx["INSMF"]]),
            ("tipo", fornecedor.tipo, campos_arquivo[idx["CODTIP"]]),
            ("bloqueado", fornecedor.bloqueado, campos_arquivo[idx["BLOQ_OPCAO"]] == "B"),
            ("motivo_bloqueio", fornecedor.motivo_bloqueio, campos_arquivo[idx["MSG_BLOQ"]]),
            ("tipo_bloqueio", fornecedor.tipo_bloqueio, campos_arquivo[idx["TIPO_BLOQ"]]),
        )
        for nome_campo, valor_gravado, valor_esperado in comparacoes:
            if valor_gravado != valor_esperado:
                campos_com_divergencia[nome_campo] = campos_com_divergencia.get(nome_campo, 0) + 1
                divergiu = True
        if divergiu:
            codifs_com_alguma_divergencia.append(fornecedor.codif)

    assert not codifs_ausentes_na_leitura_independente, (
        f"{len(codifs_ausentes_na_leitura_independente)} fornecedor(es) gravado(s) sem "
        "correspondência na leitura independente do arquivo"
    )
    assert not campos_com_divergencia, (
        f"divergência de campo entre banco e arquivo (contagem por campo: "
        f"{campos_com_divergencia}); {len(codifs_com_alguma_divergencia)} codif(s) afetado(s), "
        f"primeiros: {codifs_com_alguma_divergencia[:10]}"
    )

    # -----------------------------------------------------------------
    # SC-003: nenhuma coluna descartada aparece em banco ou sessão (regra
    # 3) — só contagens na mensagem.
    # -----------------------------------------------------------------
    valores_sensiveis = _valores_exclusivos_de_colunas_descartadas(
        cabecalho, indices_minimos, registros
    )

    vazamentos_banco = _vazamentos_por_campo_de_modelo(valores_sensiveis)
    assert not vazamentos_banco, (
        f"valor(es) de coluna descartada encontrado(s) em banco: {vazamentos_banco} "
        "(contagem de ocorrências por model.campo, nunca o valor)"
    )

    dados_sessao = sessao[importacao.CHAVE_SESSAO_PREVIA]
    vazamentos_sessao = _vazamentos_na_sessao(dados_sessao, valores_sensiveis)
    assert vazamentos_sessao == 0, (
        f"{vazamentos_sessao} valor(es) de coluna descartada encontrado(s) na sessão decodificada"
    )

    # -----------------------------------------------------------------
    # Reimportação imediata do mesmo arquivo (US4/INV-SUPPLIER-003): só
    # atualização, sem alteração — nada no arquivo mudou.
    # -----------------------------------------------------------------
    leitura_2 = lf.ler_fornecedores(conteudo)
    sha256_2 = hashlib.sha256(conteudo).hexdigest()
    plano_2 = importacao.calcular_plano(leitura_2, sha256_2)
    pedido_2 = importacao.PedidoPrevia(
        token=str(uuid.uuid4()), nome_arquivo="fornecedores_real_2.csv",
        tamanho=len(conteudo), sha256=sha256_2, leitura=leitura_2,
    )
    with transaction.atomic():
        execucao_2 = importacao.aplicar_plano(
            plano_2,
            usuario=chefe_almoxarifado,
            token_previa=pedido_2.token,
            nome_arquivo=pedido_2.nome_arquivo,
            tamanho_arquivo=pedido_2.tamanho,
        )

    assert execucao_2.total_inseridos == 0
    assert execucao_2.total_atualizados == 10_035
    assert execucao_2.total_atualizados_com_alteracao == 0
    assert execucao_2.total_rejeitados == 0
    assert Fornecedor.objects.count() == 10_035
