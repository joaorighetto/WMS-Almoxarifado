# Data Model — Entrada de Materiais

App `estoque`. Sem migrations (Constitution XIII, v1.2.0): schema criado por `migrate --run-syncdb`,
triggers de imutabilidade criados no `post_migrate` ([research R7](./research.md)). Nenhuma
exclusão física: todas as FKs com `PROTECT`, nenhum modelo registrado no admin.

`catalogo.Material` e `fornecedores.Fornecedor` **não mudam de estrutura**. A entrada só altera
`Material.saldo`, sempre por `estoque.entradas`.

## Listas fechadas

`MotivoEntrada` (FR-006):

| Valor | Rótulo | Emitente |
|---|---|---|
| `COMPRA` | Compra | obrigatório |
| `DOACAO_RECEBIDA` | Doação recebida | opcional |
| `DEVOLUCAO_FORNECEDOR_GARANTIA` | Devolução de fornecedor/garantia | obrigatório |
| `EMPRESTIMO_DEVOLVIDO` | Empréstimo devolvido | opcional |

`TipoDocumentoEntrada` (FR-007), independente do motivo:

| Valor | Rótulo |
|---|---|
| `NOTA_FISCAL` | Nota fiscal |
| `TERMO_DOACAO` | Termo de doação |
| `TERMO_RECIBO_DEVOLUCAO` | Termo/recibo de devolução |

`TipoMovimentacao`: `ENTRADA` (Entrada), `ESTORNO_ENTRADA` (Estorno de entrada). A lista cresce com
as operações futuras; não é enum canônico de domínio (research R2).

## Entrada

| Campo | Tipo | Regras |
|---|---|---|
| `chave_confirmacao` | UUID | `UNIQUE`; gerada na abertura da composição (research R4) |
| `motivo` | escolha `MotivoEntrada` | `CHECK motivo IN (...)` |
| `tipo_documento` | escolha `TipoDocumentoEntrada` | `CHECK tipo_documento IN (...)` |
| `numero_documento` | texto | gravado após `strip()`, sem outra normalização; `CHECK trim(numero_documento) <> ''` |
| `emitente` | FK → `fornecedores.Fornecedor`, anulável | `PROTECT`; `CHECK emitente IS NOT NULL OR motivo IN (DOACAO_RECEBIDA, EMPRESTIMO_DEVOLVIDO)`; não bloqueado na confirmação (aplicação, sob lock) |
| `registrada_por` | FK → `contas.User` | `PROTECT`; `request.user` da confirmação |
| `registrada_em` | data/hora | atribuída pelo sistema na confirmação (FR-019) |
| `estornada` | booleano | `default False`; só muda de `False` para `True`, junto com o `EstornoEntrada` |

Constraints adicionais:

- `UniqueConstraint(fields=["tipo_documento", "numero_documento", "emitente"],
  condition=Q(estornada=False), nulls_distinct=False, name="estoque_entrada_referencia_unica")`
  (FR-007a).

Ordenação padrão: `-registrada_em`, `-pk`. Trigger: nenhum `DELETE`; `UPDATE` só de `estornada`
`false → true`, e só com o `EstornoEntrada` da entrada já criado.

## ItemEntrada

| Campo | Tipo | Regras |
|---|---|---|
| `entrada` | FK → `Entrada` | `PROTECT`, `related_name="itens"` |
| `material` | FK → `catalogo.Material` | `PROTECT` |
| `quantidade` | decimal (15, 3) | `CHECK quantidade > 0`; unidade do material, sem conversão (`INV-CATALOG-005`) |

Constraints: `UNIQUE (entrada, material)` (FR-004). Ordenação: `material__cadpro`. Trigger: nem
`UPDATE` nem `DELETE`.

A regra de "pelo menos um item" é da aplicação (`registrar_entrada` recusa lista vazia): cardinalidade
mínima entre tabelas não cabe num `CHECK`.

## EstornoEntrada

| Campo | Tipo | Regras |
|---|---|---|
| `entrada` | `OneToOne` → `Entrada` | `PROTECT`, `related_name="estorno"`; no máximo um estorno por entrada (`INV-ENT-001`, FR-027) |
| `justificativa` | texto | gravada após `strip()`; `CHECK trim(justificativa) <> ''` (FR-024) |
| `estornada_por` | FK → `contas.User` | `PROTECT` |
| `estornada_em` | data/hora | atribuída pelo sistema |

Trigger: nem `UPDATE` nem `DELETE`. O estorno é sempre total (FR-023): não tem itens próprios. Cada
item da entrada gera uma movimentação `ESTORNO_ENTRADA` na quantidade integral.

## MovimentacaoEstoque

| Campo | Tipo | Regras |
|---|---|---|
| `material` | FK → `catalogo.Material` | `PROTECT`, `related_name="movimentacoes"` |
| `tipo` | escolha `TipoMovimentacao` | `CHECK tipo IN (...)` |
| `variacao` | decimal (16, 3) | com sinal; `CHECK variacao <> 0` |
| `saldo_anterior` | decimal (15, 3) | lido sob lock |
| `saldo_posterior` | decimal (15, 3) | `CHECK saldo_posterior = saldo_anterior + variacao`; `CHECK saldo_posterior >= 0` |
| `registrada_por` | FK → `contas.User` | `PROTECT`; autor da operação de origem |
| `registrada_em` | data/hora | o mesmo momento da operação de origem |
| `item_entrada` | FK → `ItemEntrada`, anulável | `PROTECT` |
| `estorno_entrada` | FK → `EstornoEntrada`, anulável | `PROTECT` |

Constraints:

- `CHECK` de origem por tipo:
  `(tipo = ENTRADA AND item_entrada IS NOT NULL AND estorno_entrada IS NULL AND variacao > 0)` OR
  `(tipo = ESTORNO_ENTRADA AND item_entrada IS NOT NULL AND estorno_entrada IS NOT NULL AND variacao < 0)`.
- `UNIQUE (item_entrada, tipo)`: uma movimentação de entrada e no máximo uma de estorno por item.
- Índice `(material, -registrada_em)` para o detalhe por material que `HIS` vai precisar. Custa pouco
  e evita refazer o índice depois.

Ordenação padrão: `-registrada_em`, `-pk`. Trigger: nem `UPDATE` nem `DELETE`.

A consistência `material = item_entrada.material` e `|variacao| = item_entrada.quantidade` atravessa
tabelas. É garantida por `estoque.entradas`, que cria os dois registros juntos, e verificada pelos
testes de SC-001/SC-002.

## Transições de estado

```text
Entrada:  (não existe) ──confirmar──▶ registrada (estornada=False)
          registrada ──estornar [chefe, justificativa, saldo suficiente]──▶ estornada (estornada=True)
          estornada ──▶ (final; nenhuma outra transição)
```

Material.saldo:

- entrada: `saldo += quantidade` para cada item, sob lock, com movimentação `ENTRADA`;
- estorno: `saldo -= quantidade` para cada item, sob lock, só se nenhum ficar negativo, com
  movimentação `ESTORNO_ENTRADA`.

## Propriedade de conservação (SC-001)

Para todo material `m`, em qualquer momento:

```text
m.saldo = m.saldo_inicial + Σ variacao das MovimentacaoEstoque de m
        = m.saldo_inicial + Σ quantidade dos ItemEntrada de m em entradas não estornadas
```

A primeira igualdade vale para qualquer operação futura. A segunda é específica enquanto a entrada
for a única operação. A reimportação do catálogo não altera `saldo` (`INV-STOCK-002`, garantido em
`catalogo/importacao.py`), então a propriedade sobrevive a ela.

## Rastreamento spec → modelo

| Requisito | Mecanismo |
|---|---|
| FR-002, FR-015 | FK `PROTECT` para `Material`; só `saldo` é escrito, só por `estoque.entradas` |
| FR-004 | `UNIQUE (entrada, material)`; lista vazia recusada em `registrar_entrada` |
| FR-005 | `CHECK quantidade > 0`; decimal (15, 3); `interpretar_quantidade_recebida` (research R8) |
| FR-006 | `MotivoEntrada` + `CHECK IN` |
| FR-007 | `TipoDocumentoEntrada` + `CHECK IN`; `numero_documento` aparado e não vazio; FK `emitente` + `CHECK` por motivo; bloqueio conferido sob lock |
| FR-007a | índice único parcial com `nulls_distinct=False` |
| FR-010 a FR-012 | `estoque.entradas.registrar_entrada` em transação, com locks ordenados (research R5) |
| FR-013 | `chave_confirmacao UNIQUE` |
| FR-014 | decimal (15, 3); `SaldoAcimaDoLimite` sob lock |
| FR-016, FR-017, FR-019 | campos da `Entrada` + `MovimentacaoEstoque` com origem, autor, saldos e momento do sistema |
| FR-018, FR-025 | sem rota de edição, sem admin; triggers de imutabilidade (research R7) |
| FR-022 a FR-028 | `EstornoEntrada` `OneToOne`; `estornar_entrada` sob lock da entrada e dos materiais; `CHECK saldo_posterior >= 0` |
| SC-001, SC-002 | propriedade de conservação; uma movimentação por item e por efeito |
