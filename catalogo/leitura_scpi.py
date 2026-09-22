"""Parser do arquivo de carga do catálogo SCPI (`contracts/arquivo-scpi.md`).

Módulo puro, sem banco de dados (`research.md` R2): decodificação, validação
de cabeçalho, recomposição de linhas físicas em registros lógicos (R3) e
validação por registro (R5, R6). O único ponto de contato com o resto do
domínio é `catalogo.models.MotivoRecusa`, usado para nomear os motivos de
recusa de forma consistente com `ExcecaoImportacao`.
"""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from catalogo.models import MotivoRecusa

# ---------------------------------------------------------------------------
# Constantes do contrato (`contracts/interface-importacao.md`)
# ---------------------------------------------------------------------------

# Usado sempre com `fullmatch`. `[0-9]`, nunca `\d` — em Python `\d` também
# casa dígitos Unicode (ex.: `٣`), que não são válidos no SCPI (research R3).
PADRAO_CADPRO = re.compile(r"[0-9]{3}\.[0-9]{3}\.[0-9]{3}")

# As 9 colunas obrigatórias do cabeçalho (FR-008). As demais colunas do
# arquivo real (`VAUN1`, `PRECOMEDIO`, ...) são fora de escopo: contam para a
# estrutura do registro, mas nenhum valor delas é lido ou gravado.
COLUNAS_OBRIGATORIAS = (
    "CADPRO",
    "DISC1",
    "UNID1",
    "QUAN3",
    "DISCR1",
    "GRUPO",
    "SUBGRUPO",
    "NOMEGRUPO",
    "NOMESUBGRUPO",
)

LIMITE_TAMANHO_ARQUIVO = 10 * 1024 * 1024

# Gramática de `QUAN3` (research R6): sinal opcional; parte inteira simples
# ou agrupada de 3 em 3 por ponto; parte decimal opcional separada por vírgula.
_PADRAO_QUANTIDADE = re.compile(r"^-?([0-9]+|[0-9]{1,3}(\.[0-9]{3})+)(,[0-9]+)?$")

_LIMITE_DIGITOS_INTEIROS_QUANTIDADE = 12


class ArquivoRecusado(Exception):
    """Recusa do arquivo inteiro, antes de qualquer registro (§1)."""

    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


class QuantidadeInvalida(Exception):
    """`QUAN3` não interpretável como quantidade válida (§3, R6)."""

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


@dataclass(frozen=True)
class RegistroAceito:
    linha_inicial: int
    linha_final: int
    cadpro: str
    descricao: str
    unidade: str
    detalhamento: str
    grupo: str
    subgrupo: str
    nome_grupo: str
    nome_subgrupo: str
    quantidade: Decimal


@dataclass(frozen=True)
class Recusa:
    linha_inicial: int
    linha_final: int
    cadpro: str
    motivo: str
    detalhe: str


@dataclass(frozen=True)
class ResultadoLeitura:
    aceitos: tuple[RegistroAceito, ...]
    recusas: tuple[Recusa, ...]
    total_recebidos: int


# ---------------------------------------------------------------------------
# Decodificação e cabeçalho (§1, §2)
# ---------------------------------------------------------------------------


def decodificar(conteudo: bytes) -> str:
    """`utf-8-sig` estrito: remove a BOM se presente e aceita arquivo sem
    BOM. Byte inválido recusa o arquivo inteiro (FR-007).

    O caractere nulo (U+0000) é UTF-8 válido, mas o PostgreSQL não o aceita
    em coluna de texto: também recusa o arquivo inteiro, informando as
    linhas físicas em que aparece (FR-007b), em vez de a prévia aceitar um
    arquivo que a confirmação não consegue gravar."""
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ArquivoRecusado(
            "ARQUIVO_CODIFICACAO_INVALIDA",
            "O arquivo não está em uma codificação UTF-8 válida.",
        ) from exc

    if "\x00" in texto:
        linhas = [
            numero for numero, linha in enumerate(texto.split("\n"), start=1) if "\x00" in linha
        ]
        raise ArquivoRecusado(
            "ARQUIVO_CARACTERE_NULO",
            _mensagem_caractere_nulo(linhas),
        )
    return texto


_LIMITE_LINHAS_CARACTERE_NULO = 10


def _mensagem_caractere_nulo(linhas: list[int]) -> str:
    """Mensagem com as linhas físicas (cabeçalho = linha 1) que contêm
    U+0000, listando no máximo `_LIMITE_LINHAS_CARACTERE_NULO`."""
    listadas = ", ".join(str(n) for n in linhas[:_LIMITE_LINHAS_CARACTERE_NULO])
    restantes = len(linhas) - _LIMITE_LINHAS_CARACTERE_NULO
    if restantes > 0:
        listadas += f" e mais {restantes}"
    rotulo = "na linha" if len(linhas) == 1 else "nas linhas"
    return (
        f"O arquivo contém caractere nulo (U+0000) {rotulo} {listadas}. "
        "Gere o arquivo novamente no SCPI ou remova o caractere antes de enviar."
    )


def _dividir_linhas_fisicas(texto: str) -> list[str]:
    """Linhas físicas separadas só por `\\n` (nunca `str.splitlines()`),
    removendo um `\\r` final de cada linha. Um único `\\n` final do arquivo
    não cria linha extra (research R2)."""
    linhas = texto.split("\n")
    if linhas and linhas[-1] == "":
        linhas.pop()
    return [linha[:-1] if linha.endswith("\r") else linha for linha in linhas]


def _validar_cabecalho(linha_cabecalho: str) -> tuple[dict[str, int], int]:
    """Valida o cabeçalho e devolve (índice de cada coluna obrigatória, N).

    Ordem dos motivos de recusa de arquivo: ausência antes de duplicidade
    antes de posição do `CADPRO` — nenhum teste exercita combinações
    simultâneas, mas essa ordem é a mais informativa (não dá pra saber a
    posição de uma coluna que nem existe).
    """
    campos = linha_cabecalho.split(";")
    n_campos = len(campos)
    contagem = Counter(campos)

    faltantes = [nome for nome in COLUNAS_OBRIGATORIAS if contagem[nome] == 0]
    if faltantes:
        raise ArquivoRecusado(
            "ARQUIVO_COLUNA_OBRIGATORIA_AUSENTE",
            "Coluna(s) obrigatória(s) ausente(s) no cabeçalho: " + ", ".join(faltantes) + ".",
        )

    duplicadas = [nome for nome in COLUNAS_OBRIGATORIAS if contagem[nome] > 1]
    if duplicadas:
        raise ArquivoRecusado(
            "ARQUIVO_COLUNA_DUPLICADA",
            "Coluna(s) obrigatória(s) duplicada(s) no cabeçalho: " + ", ".join(duplicadas) + ".",
        )

    if campos.index("CADPRO") != 0:
        raise ArquivoRecusado(
            "ARQUIVO_CADPRO_NAO_E_PRIMEIRA_COLUNA",
            "A coluna CADPRO precisa ser a primeira do cabeçalho.",
        )

    indices = {nome: campos.index(nome) for nome in COLUNAS_OBRIGATORIAS}
    return indices, n_campos


def verificar_arquivo(conteudo: bytes) -> None:
    """Decodificação + validação de cabeçalho, sem processar registros
    (usado pelo formulário de envio, T025). Arquivo vazio (ou só espaços e
    quebras de linha) não é recusado aqui — é o caso "zero recebidos, sem
    erro" (I-2), decidido em `ler_registros`."""
    texto = decodificar(conteudo)
    if texto.strip() == "":
        return
    linhas_fisicas = _dividir_linhas_fisicas(texto)
    _validar_cabecalho(linhas_fisicas[0])


# ---------------------------------------------------------------------------
# Recomposição de linhas físicas em registros lógicos (§2, research R3)
# ---------------------------------------------------------------------------


@dataclass
class _RegistroBruto:
    """Registro em recomposição (§2, research R3).

    O texto de cada linha física fica em `partes` (uma lista, nunca
    concatenado a cada continuação) e só é unido com `"\\n".join` uma vez,
    via a propriedade `texto` — concatenar string a string a cada linha
    (`corrente.texto += ...`) seria custo quadrático no número de
    continuações, porque um atributo de objeto não recebe a otimização
    in-place de `str +=` do CPython.

    `n_separadores` e `ultimo_caractere` tornam `_completo()` incremental:
    em vez de re-`split(";")` o texto acumulado a cada linha em branco
    (também quadrático), a contagem de separadores e o último caractere são
    atualizados só quando uma parte é anexada. `ultimo_caractere == ""`
    sinaliza texto vazio (equivalente a `campos[-1] == ""` quando
    `texto == ""`), caso que só pode ocorrer com um cabeçalho de 1 coluna —
    inatingível a partir de `ler_registros` (o cabeçalho sempre tem as 9
    colunas obrigatórias), mas mantido correto por clareza.
    """

    linha_inicial: int
    linha_final: int
    partes: list[str]
    nao_associavel: bool
    n_separadores: int
    ultimo_caractere: str

    @property
    def texto(self) -> str:
        return "\n".join(self.partes)

    @classmethod
    def iniciar(cls, numero_linha: int, linha: str, nao_associavel: bool) -> "_RegistroBruto":
        return cls(
            linha_inicial=numero_linha,
            linha_final=numero_linha,
            partes=[linha],
            nao_associavel=nao_associavel,
            n_separadores=linha.count(";"),
            ultimo_caractere=linha[-1] if linha else "",
        )

    def anexar_continuacao(self, numero_linha: int, linha: str) -> None:
        self.partes.append(linha)
        self.linha_final = numero_linha
        self.n_separadores += linha.count(";")
        self.ultimo_caractere = linha[-1] if linha else "\n"


def _recompor_registros(
    linhas_dados: list[str], n_campos: int, primeira_linha_numero: int
) -> list[_RegistroBruto]:
    separadores_esperados = n_campos - 1
    registros: list[_RegistroBruto] = []
    corrente: _RegistroBruto | None = None

    def _completo(registro: _RegistroBruto) -> bool:
        return (
            registro.n_separadores + 1 == n_campos
            and registro.ultimo_caractere in ("", ";")
        )

    for indice, linha in enumerate(linhas_dados):
        numero_linha = primeira_linha_numero + indice
        primeiro_campo = linha.split(";", 1)[0]
        n_separadores = linha.count(";")

        if PADRAO_CADPRO.fullmatch(primeiro_campo):
            if corrente is not None:
                registros.append(corrente)
            corrente = _RegistroBruto.iniciar(numero_linha, linha, False)
        elif n_separadores == separadores_esperados:
            if corrente is not None:
                registros.append(corrente)
            corrente = _RegistroBruto.iniciar(numero_linha, linha, False)
        elif linha.strip() == "" and (corrente is None or _completo(corrente)):
            # D-1: linha vazia/só espaços ignorada — não conta como recebida,
            # mas a numeração de linha física segue contando-a.
            continue
        elif corrente is None:
            registros.append(_RegistroBruto.iniciar(numero_linha, linha, True))
        else:
            corrente.anexar_continuacao(numero_linha, linha)

    if corrente is not None:
        registros.append(corrente)

    return registros


# ---------------------------------------------------------------------------
# Validação por registro (§3, research R5)
# ---------------------------------------------------------------------------


def _validar_registros(
    registros_brutos: list[_RegistroBruto], indices: dict[str, int], n_campos: int
) -> tuple[list[RegistroAceito], list[Recusa]]:
    # Primeira passagem: recusas imediatas (estrutura, CADPRO ausente/formato
    # inválido) e candidatos com CADPRO bem formado, cuja duplicidade só pode
    # ser apurada depois de conhecer todos eles (FR-005).
    processados: list[tuple[str, object]] = []

    for registro in registros_brutos:
        if registro.nao_associavel:
            processados.append((
                "recusa",
                Recusa(
                    registro.linha_inicial, registro.linha_final, "",
                    MotivoRecusa.LINHA_NAO_ASSOCIAVEL,
                    "Linha de continuação sem registro anterior associável.",
                ),
            ))
            continue

        campos = registro.texto.split(";")
        if len(campos) != n_campos or campos[-1] != "":
            cadpro_bruto = campos[0] if campos else ""
            if len(campos) != n_campos:
                detalhe = f"Esperado {n_campos} campos; encontrado {len(campos)}."
            else:
                # Contagem de campos correta: a causa é o último campo (o
                # delimitador final) não estar vazio — mensagem diferente,
                # para não sair "Esperado N; encontrado N" (enganoso).
                detalhe = (
                    f"Esperado o último campo vazio (delimitador final); "
                    f"encontrado {campos[-1]!r}."
                )
            processados.append((
                "recusa",
                Recusa(
                    registro.linha_inicial, registro.linha_final, cadpro_bruto,
                    MotivoRecusa.ESTRUTURA_INCONSISTENTE,
                    detalhe,
                ),
            ))
            continue

        valores = {nome: campos[indice] for nome, indice in indices.items()}
        cadpro_bruto = valores["CADPRO"]

        if cadpro_bruto == "":
            processados.append((
                "recusa",
                Recusa(
                    registro.linha_inicial, registro.linha_final, "",
                    MotivoRecusa.CADPRO_AUSENTE, "CADPRO vazio.",
                ),
            ))
            continue

        if not PADRAO_CADPRO.fullmatch(cadpro_bruto):
            processados.append((
                "recusa",
                Recusa(
                    registro.linha_inicial, registro.linha_final, cadpro_bruto,
                    MotivoRecusa.CADPRO_FORMATO_INVALIDO,
                    f"CADPRO {cadpro_bruto!r} fora do formato XXX.YYY.ZZZ.",
                ),
            ))
            continue

        processados.append(("candidato", (registro, valores, cadpro_bruto)))

    contagem_cadpro = Counter(
        item[1][2] for item in processados if item[0] == "candidato"
    )

    aceitos: list[RegistroAceito] = []
    recusas: list[Recusa] = []

    for tipo, dados in processados:
        if tipo == "recusa":
            recusas.append(dados)
            continue

        registro, valores, cadpro_bruto = dados

        if contagem_cadpro[cadpro_bruto] > 1:
            recusas.append(Recusa(
                registro.linha_inicial, registro.linha_final, cadpro_bruto,
                MotivoRecusa.CADPRO_DUPLICADO_NO_ARQUIVO,
                f"CADPRO {cadpro_bruto} aparece em mais de um registro do arquivo.",
            ))
            continue

        descricao = valores["DISC1"]
        if descricao.strip() == "":
            recusas.append(Recusa(
                registro.linha_inicial, registro.linha_final, cadpro_bruto,
                MotivoRecusa.DESCRICAO_AUSENTE, "DISC1 vazio.",
            ))
            continue

        unidade = valores["UNID1"]
        if unidade.strip() == "":
            recusas.append(Recusa(
                registro.linha_inicial, registro.linha_final, cadpro_bruto,
                MotivoRecusa.UNIDADE_AUSENTE, "UNID1 vazio.",
            ))
            continue

        try:
            quantidade = interpretar_quantidade(valores["QUAN3"])
        except QuantidadeInvalida as exc:
            recusas.append(Recusa(
                registro.linha_inicial, registro.linha_final, cadpro_bruto,
                exc.motivo, f"QUAN3 recebido: {valores['QUAN3']!r}.",
            ))
            continue

        aceitos.append(RegistroAceito(
            linha_inicial=registro.linha_inicial,
            linha_final=registro.linha_final,
            cadpro=cadpro_bruto,
            descricao=descricao,
            unidade=unidade,
            detalhamento=valores["DISCR1"],
            grupo=valores["GRUPO"],
            subgrupo=valores["SUBGRUPO"],
            nome_grupo=valores["NOMEGRUPO"],
            nome_subgrupo=valores["NOMESUBGRUPO"],
            quantidade=quantidade,
        ))

    return aceitos, recusas


def ler_registros(conteudo: bytes) -> ResultadoLeitura:
    """Lê e valida todos os registros do arquivo (§2, §3).

    Levanta `ArquivoRecusado` nos casos de recusa do arquivo inteiro (§1).
    Arquivo vazio, só com espaços/quebras de linha, ou só com cabeçalho
    válido: zero registros recebidos, sem erro (I-2).
    """
    texto = decodificar(conteudo)
    if texto.strip() == "":
        return ResultadoLeitura(aceitos=(), recusas=(), total_recebidos=0)

    linhas_fisicas = _dividir_linhas_fisicas(texto)
    indices, n_campos = _validar_cabecalho(linhas_fisicas[0])
    linhas_dados = linhas_fisicas[1:]

    registros_brutos = _recompor_registros(linhas_dados, n_campos, primeira_linha_numero=2)
    aceitos, recusas = _validar_registros(registros_brutos, indices, n_campos)

    return ResultadoLeitura(
        aceitos=tuple(aceitos),
        recusas=tuple(recusas),
        total_recebidos=len(aceitos) + len(recusas),
    )


# ---------------------------------------------------------------------------
# Interpretação de quantidade (§3, research R6)
# ---------------------------------------------------------------------------


def interpretar_quantidade(texto: str) -> Decimal:
    """`QUAN3` -> `Decimal`, sem `float`, quantizado a 3 casas
    (`ROUND_HALF_UP`). Sinal negativo é avaliado sobre o valor não
    arredondado — `-0,0001` é negativo; `-0`/`-0,000` valem zero (nunca
    zero negativo, mesmo no caso em que só o arredondamento produz `-0`).

    O limite de 12 dígitos inteiros (R7, FR-012) é verificado sobre o valor
    já quantizado, contando os dígitos do valor (zeros à esquerda no texto
    não contam) — o arredondamento pode ganhar um dígito por carry (ex.:
    `"999999999999,9995"` -> `1000000000000.000`, 13 dígitos), então checar
    só o texto aceitaria um valor que não cabe em
    `DecimalField(max_digits=15, decimal_places=3)`. Uma checagem barata
    sobre o texto (dígitos inteiros, com folga de 1 para o carry) evita
    quantizar valores absurdamente grandes só para descobrir que excedem o
    limite.
    """
    texto_aparado = texto.strip()
    if texto_aparado == "":
        raise QuantidadeInvalida(MotivoRecusa.QUANTIDADE_AUSENTE)

    if not _PADRAO_QUANTIDADE.fullmatch(texto_aparado):
        raise QuantidadeInvalida(MotivoRecusa.QUANTIDADE_NAO_NUMERICA)

    negativo = texto_aparado.startswith("-")
    corpo = texto_aparado[1:] if negativo else texto_aparado

    if "," in corpo:
        parte_inteira, parte_decimal = corpo.split(",", 1)
    else:
        parte_inteira, parte_decimal = corpo, ""

    parte_inteira_sem_milhar = parte_inteira.replace(".", "")

    texto_decimal = parte_inteira_sem_milhar + (f".{parte_decimal}" if parte_decimal else "")
    valor = Decimal(texto_decimal)
    if negativo:
        valor = -valor

    if valor < 0:
        raise QuantidadeInvalida(MotivoRecusa.QUANTIDADE_NEGATIVA)

    digitos_inteiros_texto = len(parte_inteira_sem_milhar.lstrip("0"))
    if digitos_inteiros_texto > _LIMITE_DIGITOS_INTEIROS_QUANTIDADE + 1:
        raise QuantidadeInvalida(MotivoRecusa.QUANTIDADE_FORA_DO_LIMITE)

    valor_quantizado = valor.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    if valor_quantizado == 0:
        valor_quantizado = Decimal("0.000")

    digitos_inteiros = len(str(int(valor_quantizado)))
    if digitos_inteiros > _LIMITE_DIGITOS_INTEIROS_QUANTIDADE:
        raise QuantidadeInvalida(MotivoRecusa.QUANTIDADE_FORA_DO_LIMITE)

    return valor_quantizado


# ---------------------------------------------------------------------------
# Busca por descrição (T012, já existente)
# ---------------------------------------------------------------------------


def normalizar_para_busca(texto: str) -> str:
    """Normaliza texto para comparação de busca por descrição (FR-040).

    Remove acentuação (decomposição NFKD seguida da remoção dos caracteres de
    categoria Unicode `Mn`, marcas combinantes) e aplica `casefold()`. A mesma
    função grava `Material.descricao_busca` e normaliza o termo digitado pelo
    usuário, para que a comparação seja simétrica (`research.md` R15).
    """
    sem_acento = "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", texto)
        if unicodedata.category(caractere) != "Mn"
    )
    return sem_acento.casefold()
