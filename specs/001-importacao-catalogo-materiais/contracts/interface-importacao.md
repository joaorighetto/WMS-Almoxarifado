# Contrato — Interface interna da importação

Assinaturas Python que os testes (T015–T019, T041–T043) e a implementação (T020–T026, T044–T046)
compartilham. Fixadas antes do código para que os testes escritos primeiro não precisem ser
reescritos. Comportamento: [arquivo-scpi.md](./arquivo-scpi.md),
[rotas-e-autorizacao.md](./rotas-e-autorizacao.md) e [research.md](../research.md) R3–R11.
Nomes adicionais internos (funções auxiliares privadas) ficam a critério do implementador.

## `catalogo/leitura_scpi.py` — sem banco

```python
PADRAO_CADPRO: re.Pattern          # r"[0-9]{3}\.[0-9]{3}\.[0-9]{3}", usar com fullmatch
COLUNAS_OBRIGATORIAS: tuple[str, ...]   # as 9 de FR-008
LIMITE_TAMANHO_ARQUIVO: int        # 10 * 1024 * 1024

class ArquivoRecusado(Exception):
    codigo: str                    # códigos de arquivo-scpi.md §1 (ex.: "ARQUIVO_COLUNA_OBRIGATORIA_AUSENTE")
    mensagem: str                  # legível, sem detalhe interno

class QuantidadeInvalida(Exception):
    motivo: str                    # MotivoRecusa: QUANTIDADE_AUSENTE | _NAO_NUMERICA | _NEGATIVA | _FORA_DO_LIMITE

@dataclass(frozen=True)
class RegistroAceito:
    linha_inicial: int
    linha_final: int
    cadpro: str
    descricao: str                 # DISC1, exatamente como lido
    unidade: str                   # UNID1
    detalhamento: str              # DISCR1
    grupo: str
    subgrupo: str
    nome_grupo: str
    nome_subgrupo: str
    quantidade: Decimal            # já arredondada para 3 casas (R6)

@dataclass(frozen=True)
class Recusa:
    linha_inicial: int
    linha_final: int
    cadpro: str                    # 1º campo como recebido; "" se vazio ou LINHA_NAO_ASSOCIAVEL
    motivo: str                    # valor de MotivoRecusa
    detalhe: str

@dataclass(frozen=True)
class ResultadoLeitura:
    aceitos: tuple[RegistroAceito, ...]    # na ordem do arquivo
    recusas: tuple[Recusa, ...]            # na ordem do arquivo
    total_recebidos: int                   # len(aceitos) + len(recusas)

def decodificar(conteudo: bytes) -> str                 # ArquivoRecusado(ARQUIVO_CODIFICACAO_INVALIDA | ARQUIVO_CARACTERE_NULO)
def verificar_arquivo(conteudo: bytes) -> None          # decodificação + cabeçalho; levanta ArquivoRecusado
def ler_registros(conteudo: bytes) -> ResultadoLeitura  # levanta ArquivoRecusado nos casos da §1
def interpretar_quantidade(texto: str) -> Decimal       # levanta QuantidadeInvalida
def normalizar_para_busca(texto: str) -> str            # já existe (T012)
```

`ARQUIVO_TAMANHO_EXCEDIDO` e `ARQUIVO_NAO_ENVIADO` são verificados no formulário (T025), que
também chama `verificar_arquivo`.

## `catalogo/importacao.py` — com banco

```python
CHAVE_LOCK_IMPORTACAO_SCPI: int
CHAVE_SESSAO_PREVIA = "catalogo_importacao_previa"

@dataclass(frozen=True)
class Atualizacao:
    material_id: int
    cadpro: str
    registro: RegistroAceito
    alteracoes: tuple[tuple[str, str, str], ...]   # (campo, valor_anterior, valor_novo), ordenado por campo;
                                                   # vazio = existente sem mudança cadastral

@dataclass(frozen=True)
class Divergencia:
    material_id: int
    cadpro: str
    saldo_wms: Decimal
    saldo_arquivo: Decimal
    diferenca: Decimal             # saldo_arquivo - saldo_wms, nunca 0

@dataclass(frozen=True)
class PlanoImportacao:
    sha256_arquivo: str
    insercoes: tuple[RegistroAceito, ...]      # ordenadas por cadpro
    atualizacoes: tuple[Atualizacao, ...]      # ordenadas por cadpro
    recusas: tuple[Recusa, ...]                # ordenadas por linha_inicial
    divergencias: tuple[Divergencia, ...]      # ordenadas por cadpro
    total_recebidos: int
    total_inseridos: int
    total_atualizados: int
    total_atualizados_com_alteracao: int
    total_rejeitados: int
    total_divergencias: int
    total_ausentes_no_arquivo: int
    impressao_digital: str                     # sha256 hex da serialização canônica

@dataclass(frozen=True)
class PedidoPrevia:
    token: str                     # UUID4 em texto
    nome_arquivo: str              # truncado em 255
    tamanho: int
    sha256: str
    conteudo: bytes

class PreviaDesatualizada(Exception):
    plano_atual: PlanoImportacao

class PreviaJaConfirmada(Exception):
    execucao: ExecucaoImportacao

def calcular_plano(conteudo: bytes, *, bloquear: bool = False) -> PlanoImportacao
    # só leituras; bloquear=True só dentro de transação (select_for_update ordenado por pk)
def aplicar_plano(plano: PlanoImportacao, *, usuario, token_previa: str,
                  nome_arquivo: str, tamanho_arquivo: int) -> ExecucaoImportacao
    # exige transação aberta pelo chamador; grava tudo do plano; nunca escreve saldo de existente
def confirmar_importacao(pedido: PedidoPrevia, impressao_digital: str, usuario) -> ExecucaoImportacao
    # transaction.atomic + pg_advisory_xact_lock + checagem de token + recálculo + comparação + aplicar_plano
def guardar_pedido(session, *, nome_arquivo: str, conteudo: bytes) -> PedidoPrevia
def obter_pedido(session) -> PedidoPrevia | None
def descartar_pedido(session) -> None
```

Desde T044/T045, `Atualizacao.alteracoes` e `PlanoImportacao.divergencias` são preenchidos pela
reimportação (US4): `alteracoes` traz o diff exato dos `CAMPOS_CADASTRAIS_ATUALIZAVEIS` do
registro contra o material existente, e `divergencias` traz uma entrada por material existente
cuja quantidade do arquivo difere do saldo atual. Os campos já existiam desde a US1 para a
assinatura não mudar; na carga inicial sobre catálogo vazio (sem atualizações) eles continuam
vazios.
