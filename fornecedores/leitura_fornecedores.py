"""Parser do arquivo de carga de fornecedores do SCPI
(`contracts/arquivo-fornecedores.md`).

Módulo puro, sem banco de dados (`research.md` R2): decodificação (reusada de
`catalogo.leitura_scpi`), validação de cabeçalho por NOME (a posição das
colunas não é exigida, diferente da 001), separação de registros só por
`\\r\\n` (nunca recomposição de linhas físicas — um `\\n` isolado já
permanece dentro do campo, porque só `\\r\\n` separa registros) e validação
por registro (§3). Assinaturas fixadas em
`contracts/interface-importacao.md`.
"""

import re
from collections import Counter
from dataclasses import dataclass

from catalogo.leitura_scpi import decodificar
from fornecedores.models import MotivoRecusaFornecedor

# ---------------------------------------------------------------------------
# Constantes do contrato (`contracts/interface-importacao.md`)
# ---------------------------------------------------------------------------

COLUNAS_OBRIGATORIAS = (
    "CODIF",
    "NOME",
    "NOM_FANT",
    "INSMF",
    "CODTIP",
    "BLOQ_OPCAO",
    "MSG_BLOQ",
    "TIPO_BLOQ",
)

# Usado sempre com `fullmatch`. `[0-9]`, nunca `\d` — em Python `\d` também
# casa dígitos Unicode (ex.: `٣`), que não são válidos no SCPI (research R2).
PADRAO_CODIF = re.compile(r"[0-9]+")

_VALORES_BLOQ_OPCAO = ("S", "B")

_PADRAO_DIGITO = re.compile(r"[0-9]")


@dataclass(frozen=True)
class FornecedorLido:
    """Projeção mínima de um registro aceito (`arquivo-fornecedores.md` §4,
    `INV-SUPPLIER-004`) — nenhuma coluna além destas sobrevive à leitura."""

    linha: int
    codif: str
    nome: str
    nome_fantasia: str
    documento: str
    tipo: str
    bloqueado: bool
    motivo_bloqueio: str
    tipo_bloqueio: str


@dataclass(frozen=True)
class RecusaFornecedor:
    linha: int
    codif: str  # "" quando não identificável (§3)
    motivo: str  # MotivoRecusaFornecedor
    detalhe: str  # texto fixo, sem valor de outra coluna do arquivo


@dataclass(frozen=True)
class LeituraFornecedores:
    aceitos: tuple[FornecedorLido, ...]
    recusas: tuple[RecusaFornecedor, ...]
    total_recebidos: int


# ---------------------------------------------------------------------------
# Cabeçalho (§2)
# ---------------------------------------------------------------------------


def _validar_cabecalho(linha_cabecalho: str) -> tuple[dict[str, int], int]:
    """Valida o cabeçalho e devolve (índice de cada coluna obrigatória, N).

    A posição das colunas não é exigida (diferente da 001): cada coluna
    obrigatória é localizada pelo nome. Ordem dos motivos: ausência antes de
    duplicidade — não dá pra checar duplicidade de uma coluna que nem
    existe."""
    campos = linha_cabecalho.split(";")
    contagem = Counter(campos)

    faltantes = [nome for nome in COLUNAS_OBRIGATORIAS if contagem[nome] == 0]
    if faltantes:
        raise _arquivo_recusado(
            "ARQUIVO_COLUNA_OBRIGATORIA_AUSENTE",
            "Coluna(s) obrigatória(s) ausente(s) no cabeçalho: " + ", ".join(faltantes) + ".",
        )

    duplicadas = [nome for nome in COLUNAS_OBRIGATORIAS if contagem[nome] > 1]
    if duplicadas:
        raise _arquivo_recusado(
            "ARQUIVO_COLUNA_DUPLICADA",
            "Coluna(s) obrigatória(s) duplicada(s) no cabeçalho: " + ", ".join(duplicadas) + ".",
        )

    indices = {nome: campos.index(nome) for nome in COLUNAS_OBRIGATORIAS}
    return indices, len(campos)


def _arquivo_recusado(codigo, mensagem):
    from catalogo.leitura_scpi import ArquivoRecusado

    return ArquivoRecusado(codigo, mensagem)


# ---------------------------------------------------------------------------
# Validação por registro (§3)
# ---------------------------------------------------------------------------


# Quantas outras linhas o detalhe de CODIF_DUPLICADO cita nominalmente
# (revisão do code-reviewer, P2): um CODIF repetido dezenas de milhares de
# vezes não pode gerar um detalhe proporcional a n por ocorrência — isso é
# O(n) de string por registro, O(n²) no total do arquivo (para n=20.000,
# ~2,8 GB de texto), e esse texto vai para a sessão e para o banco
# (`ExcecaoImportacaoFornecedores.detalhe`). O contrato
# (`arquivo-fornecedores.md` §3) só exige "também na linha X" — nunca listar
# todas as ocorrências.
_LIMITE_LINHAS_DETALHE_CODIF_DUPLICADO = 3


def _detalhe_codif_duplicado(
    *, numero_linha: int, total_ocorrencias: int, primeiras_linhas: list[int]
) -> str:
    """Detalhe de `CODIF_DUPLICADO`, custo O(K) por registro (K =
    `_LIMITE_LINHAS_DETALHE_CODIF_DUPLICADO`), nunca O(n). `primeiras_linhas`
    já vem limitada a K+1 elementos por `_validar_registros` — suficiente
    para sempre sobrar K linhas depois de excluir a própria (`numero_linha`),
    esteja ela entre as K+1 guardadas ou não."""
    outras = [linha for linha in primeiras_linhas if linha != numero_linha]
    outras = outras[:_LIMITE_LINHAS_DETALHE_CODIF_DUPLICADO]
    total_outras = total_ocorrencias - 1
    restantes = total_outras - len(outras)

    if len(outras) == 1:
        texto = f"também na linha {outras[0]}"
    else:
        texto = "também nas linhas " + ", ".join(str(linha) for linha in outras)
    if restantes > 0:
        texto += f" e mais {restantes}"
    return texto + "."


def _validar_registros(
    registros: list[str], indices: dict[str, int], n_campos: int, primeira_linha: int
) -> tuple[list[FornecedorLido], list[RecusaFornecedor]]:
    # Primeira passagem: recusas imediatas (estrutura, CODIF ausente/formato
    # inválido/nome/bloqueio) e candidatos, cuja duplicidade só pode ser
    # apurada depois de conhecer todos eles (§3).
    processados: list[tuple[str, object]] = []

    for offset, linha_texto in enumerate(registros):
        numero_linha = primeira_linha + offset

        if linha_texto.strip() == "":
            # Linha vazia fora do fim é ignorada (§2) — não conta como
            # recebida, mas a numeração de linha segue contando-a.
            continue

        campos = linha_texto.split(";")
        if len(campos) != n_campos:
            processados.append(
                (
                    "recusa",
                    RecusaFornecedor(
                        linha=numero_linha,
                        codif="",
                        motivo=MotivoRecusaFornecedor.COLUNAS_DESLOCADAS,
                        detalhe=f"{n_campos} campos esperados, {len(campos)} encontrados.",
                    ),
                )
            )
            continue

        valores = {nome: campos[indice] for nome, indice in indices.items()}
        codif_bruto = valores["CODIF"]

        if codif_bruto == "":
            processados.append(
                (
                    "recusa",
                    RecusaFornecedor(
                        linha=numero_linha,
                        codif="",
                        motivo=MotivoRecusaFornecedor.CODIF_AUSENTE,
                        detalhe="CODIF vazio.",
                    ),
                )
            )
            continue

        if not PADRAO_CODIF.fullmatch(codif_bruto):
            processados.append(
                (
                    "recusa",
                    RecusaFornecedor(
                        linha=numero_linha,
                        codif="",
                        motivo=MotivoRecusaFornecedor.CODIF_INVALIDO,
                        detalhe="CODIF fora do formato numérico.",
                    ),
                )
            )
            continue

        if valores["NOME"].strip() == "":
            processados.append(
                (
                    "recusa",
                    RecusaFornecedor(
                        linha=numero_linha,
                        codif=codif_bruto,
                        motivo=MotivoRecusaFornecedor.NOME_AUSENTE,
                        detalhe="NOME vazio.",
                    ),
                )
            )
            continue

        bloq_opcao = valores["BLOQ_OPCAO"]
        if bloq_opcao not in _VALORES_BLOQ_OPCAO:
            processados.append(
                (
                    "recusa",
                    RecusaFornecedor(
                        linha=numero_linha,
                        codif=codif_bruto,
                        motivo=MotivoRecusaFornecedor.SITUACAO_BLOQUEIO_INVALIDA,
                        detalhe="BLOQ_OPCAO fora de {S, B}.",
                    ),
                )
            )
            continue

        processados.append(("candidato", (numero_linha, valores, codif_bruto)))

    contagem_codif = Counter(item[1][2] for item in processados if item[0] == "candidato")
    # Guarda só as primeiras K+1 linhas de cada grupo duplicado — o bastante
    # para `_detalhe_codif_duplicado` sempre ter K linhas após excluir a
    # própria, sem reter O(n) linhas por grupo (ver comentário acima).
    limite_grupo = _LIMITE_LINHAS_DETALHE_CODIF_DUPLICADO + 1
    linhas_por_codif: dict[str, list[int]] = {}
    for tipo, dados in processados:
        if tipo == "candidato" and contagem_codif[dados[2]] > 1:
            grupo = linhas_por_codif.setdefault(dados[2], [])
            if len(grupo) < limite_grupo:
                grupo.append(dados[0])

    aceitos: list[FornecedorLido] = []
    recusas: list[RecusaFornecedor] = []

    for tipo, dados in processados:
        if tipo == "recusa":
            recusas.append(dados)
            continue

        numero_linha, valores, codif_bruto = dados

        if contagem_codif[codif_bruto] > 1:
            recusas.append(
                RecusaFornecedor(
                    linha=numero_linha,
                    codif=codif_bruto,
                    motivo=MotivoRecusaFornecedor.CODIF_DUPLICADO,
                    detalhe=_detalhe_codif_duplicado(
                        numero_linha=numero_linha,
                        total_ocorrencias=contagem_codif[codif_bruto],
                        primeiras_linhas=linhas_por_codif[codif_bruto],
                    ),
                )
            )
            continue

        aceitos.append(
            FornecedorLido(
                linha=numero_linha,
                codif=codif_bruto,
                nome=valores["NOME"],
                nome_fantasia=valores["NOM_FANT"],
                documento=valores["INSMF"],
                tipo=valores["CODTIP"],
                bloqueado=valores["BLOQ_OPCAO"] == "B",
                motivo_bloqueio=valores["MSG_BLOQ"],
                tipo_bloqueio=valores["TIPO_BLOQ"],
            )
        )

    return aceitos, recusas


# ---------------------------------------------------------------------------
# Leitura completa (§1, §2)
# ---------------------------------------------------------------------------


def ler_fornecedores(conteudo: bytes) -> LeituraFornecedores:
    """Lê e valida todos os registros do arquivo (§2, §3).

    Levanta `catalogo.leitura_scpi.ArquivoRecusado` nas recusas do arquivo
    inteiro (§1). Arquivo vazio, só com espaços/quebras de linha, ou só com
    cabeçalho válido: zero registros recebidos, sem erro.
    """
    texto = decodificar(conteudo)
    if texto.strip() == "":
        return LeituraFornecedores(aceitos=(), recusas=(), total_recebidos=0)

    if "\n" in texto and "\r\n" not in texto:
        raise _arquivo_recusado(
            "ARQUIVO_TERMINADOR_INVALIDO",
            "O arquivo precisa terminar cada registro com CRLF (\\r\\n).",
        )

    segmentos = texto.split("\r\n")
    if segmentos and segmentos[-1] == "":
        # Um último elemento vazio, produzido pelo terminador final do
        # último registro, é descartado (§2) — não vira uma "linha" própria.
        segmentos.pop()

    indices, n_campos = _validar_cabecalho(segmentos[0])
    registros = segmentos[1:]

    aceitos, recusas = _validar_registros(registros, indices, n_campos, primeira_linha=2)

    return LeituraFornecedores(
        aceitos=tuple(aceitos),
        recusas=tuple(recusas),
        total_recebidos=len(aceitos) + len(recusas),
    )


# ---------------------------------------------------------------------------
# Serialização (sessão da prévia, `fornecedores.importacao`) — whitelist de
# chaves exata (`INV-SUPPLIER-004`).
# ---------------------------------------------------------------------------


def para_json(leitura: LeituraFornecedores) -> dict:
    return {
        "aceitos": [
            {
                "linha": aceito.linha,
                "codif": aceito.codif,
                "nome": aceito.nome,
                "nome_fantasia": aceito.nome_fantasia,
                "documento": aceito.documento,
                "tipo": aceito.tipo,
                "bloqueado": aceito.bloqueado,
                "motivo_bloqueio": aceito.motivo_bloqueio,
                "tipo_bloqueio": aceito.tipo_bloqueio,
            }
            for aceito in leitura.aceitos
        ],
        "recusas": [
            {
                "linha": recusa.linha,
                "codif": recusa.codif,
                "motivo": recusa.motivo,
                "detalhe": recusa.detalhe,
            }
            for recusa in leitura.recusas
        ],
        "total_recebidos": leitura.total_recebidos,
    }


def de_json(dados: dict) -> LeituraFornecedores:
    return LeituraFornecedores(
        aceitos=tuple(FornecedorLido(**item) for item in dados["aceitos"]),
        recusas=tuple(RecusaFornecedor(**item) for item in dados["recusas"]),
        total_recebidos=dados["total_recebidos"],
    )


# ---------------------------------------------------------------------------
# Dígitos — usada por `documento_digitos` e pela busca (research R6).
# ---------------------------------------------------------------------------


def somente_digitos(texto: str) -> str:
    """Só os dígitos ASCII de `texto` (`[0-9]`, nunca `\\d`/`isdigit()` —
    dígitos Unicode fora de `0-9` não contam)."""
    return "".join(_PADRAO_DIGITO.findall(texto))
