# Contrato — Interface interna de `estoque`

Assinaturas usadas pelas views e pelos testes. Os nomes são normativos para a implementação; os
corpos não.

## `estoque/quantidade.py`

```python
class QuantidadeInvalida(ValueError):
    mensagem: str   # texto para o usuário (research R8)

def interpretar_quantidade_recebida(texto: str) -> Decimal: ...
```

Pura, sem banco. Retorna `Decimal` com três casas, estritamente positivo, com no máximo 12 dígitos
inteiros. Nunca arredonda.

## `estoque/entradas.py`

```python
@dataclass(frozen=True)
class ItemInformado:
    material_id: int
    quantidade: Decimal          # já interpretada

@dataclass(frozen=True)
class EntradaInformada:
    chave_confirmacao: UUID
    motivo: str                  # MotivoEntrada
    tipo_documento: str          # TipoDocumentoEntrada
    numero_documento: str        # aparado
    emitente_id: int | None
    itens: tuple[ItemInformado, ...]

def validar_entrada(dados: EntradaInformada) -> None: ...
def registrar_entrada(dados: EntradaInformada, autor: User) -> Entrada: ...
def estornar_entrada(entrada_id: int, justificativa: str, autor: User) -> EstornoEntrada: ...
```

- `validar_entrada`: só leitura. Aplica todas as regras de negócio que não dependem de lock: lista
  não vazia, sem material repetido, materiais existentes, motivo e tipo na lista, número não vazio,
  emitente obrigatório por motivo, emitente existente e não bloqueado, referência não usada em
  entrada não estornada, saldo resultante dentro do limite. Levanta `EntradaInvalida` com os erros
  por campo e por item. Usada pelo "Revisar" e, de novo, dentro de `registrar_entrada`.
- `registrar_entrada`: a sequência de [research R5](../research.md), dentro de uma
  `transaction.atomic()` própria. Retorna a entrada criada.
- `estornar_entrada`: a sequência de estorno de R5, dentro de uma `transaction.atomic()` própria.

Nenhuma das duas confia em papel: a autorização é da view. Elas recebem o `autor` para registrar
quem agiu.

### Exceções

| Exceção | Quando | Atributos |
|---|---|---|
| `EntradaInvalida` | regra de validação violada | `erros_campo: dict[str, list[str]]`, `erros_item: dict[int, list[str]]` (pela posição do item em `itens`, para apontar a linha repetida) |
| `EntradaJaRegistrada` | `chave_confirmacao` já usada | `entrada` |
| `ReferenciaJaUsada(EntradaInvalida)` | outra entrada não estornada com a mesma referência (pré-checagem ou índice) | `entrada` |
| `EmitenteIndisponivel(EntradaInvalida)` | emitente inexistente ou bloqueado sob lock | — |
| `SaldoAcimaDoLimite(EntradaInvalida)` | saldo resultante acima de 999.999.999.999,999 | `material_id` |
| `EntradaJaEstornada` | estorno de entrada já estornada | `entrada` |
| `JustificativaAusente` | justificativa vazia após `strip()` | — |
| `EstornoBloqueadoPorSaldo` | algum saldo ficaria negativo | `itens: list[tuple[ItemEntrada, Decimal]]` (item e saldo atual) |

Todas levantadas antes de qualquer escrita, ou dentro da transação, que então é desfeita por
inteiro (`INV-STOCK-004`).

## `estoque/apps.py`

```python
def criar_triggers_imutabilidade(using, **kwargs) -> None: ...   # post_migrate, idempotente
```

Cria a função e os triggers de [research R7](../research.md). Conectado com `sender=self` em
`EstoqueConfig.ready()`.

## Logger

`estoque.entradas`, configurado em `config/settings/base.py` ao lado de `catalogo.importacao` e
`fornecedores.importacao` (research R14).
