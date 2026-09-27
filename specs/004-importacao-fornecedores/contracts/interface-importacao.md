# Contrato — Interface interna da importação de fornecedores

Assinaturas compartilhadas por testes e implementação, fixadas antes da US1 para que os testes
escritos primeiro não dependam de nomes inventados.

## `fornecedores/leitura_fornecedores.py` (puro, sem banco)

```python
COLUNAS_OBRIGATORIAS = ("CODIF", "NOME", "NOM_FANT", "INSMF", "CODTIP",
                        "BLOQ_OPCAO", "MSG_BLOQ", "TIPO_BLOQ")
PADRAO_CODIF = re.compile(r"[0-9]+")          # sempre fullmatch

@dataclass(frozen=True)
class FornecedorLido:          # projeção mínima (arquivo-fornecedores.md §4)
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
    codif: str                 # "" quando não identificável
    motivo: str                # MotivoRecusaFornecedor
    detalhe: str               # texto fixo, sem valor do arquivo além do codif

@dataclass(frozen=True)
class LeituraFornecedores:
    aceitos: tuple[FornecedorLido, ...]
    recusas: tuple[RecusaFornecedor, ...]
    total_recebidos: int

def ler_fornecedores(conteudo: bytes) -> LeituraFornecedores: ...
    # levanta catalogo.leitura_scpi.ArquivoRecusado nas recusas de arquivo (§1)
def para_json(leitura: LeituraFornecedores) -> dict: ...
def de_json(dados: dict) -> LeituraFornecedores: ...
def somente_digitos(texto: str) -> str: ...     # para documento_digitos e busca
```

## `fornecedores/importacao.py`

```python
CHAVE_LOCK_IMPORTACAO_FORNECEDORES: int     # distinta de catalogo.importacao
CHAVE_SESSAO_PREVIA = "fornecedores_importacao_previa"
TAMANHO_LOTE = 500

@dataclass(frozen=True)
class Atualizacao:
    fornecedor_id: int
    codif: str
    lido: FornecedorLido
    alteracoes: tuple[tuple[str, str, str], ...]   # (campo, anterior, novo), por campo

@dataclass(frozen=True)
class PlanoImportacao:
    sha256_arquivo: str
    insercoes: tuple[FornecedorLido, ...]
    atualizacoes: tuple[Atualizacao, ...]
    recusas: tuple[RecusaFornecedor, ...]
    total_recebidos: int
    total_inseridos: int
    total_atualizados: int
    total_atualizados_com_alteracao: int
    total_rejeitados: int
    total_ausentes_no_arquivo: int
    impressao_digital: str

@dataclass(frozen=True)
class PedidoPrevia:
    token: str
    nome_arquivo: str
    tamanho: int
    sha256: str
    leitura: LeituraFornecedores       # nunca os bytes do arquivo

class PreviaDesatualizada(Exception): plano_atual: PlanoImportacao
class PreviaJaConfirmada(Exception): execucao: ExecucaoImportacaoFornecedores

def calcular_plano(leitura, sha256_arquivo, *, bloquear=False) -> PlanoImportacao: ...
def aplicar_plano(plano, *, usuario, token_previa, nome_arquivo, tamanho_arquivo)
    -> ExecucaoImportacaoFornecedores: ...          # exige transação aberta
def confirmar_importacao(pedido, impressao_digital_enviada, usuario)
    -> ExecucaoImportacaoFornecedores: ...
def guardar_pedido(session, *, nome_arquivo, conteudo: bytes) -> PedidoPrevia: ...
    # lê, projeta e guarda só a projeção; propaga ArquivoRecusado sem tocar a sessão
def obter_pedido(session) -> PedidoPrevia | None: ...
def descartar_pedido(session) -> None: ...
```

`bloqueado` entra nas alterações e na impressão digital como `"B"`/`"S"`.
