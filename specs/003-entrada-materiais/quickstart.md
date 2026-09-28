# Quickstart — validação de ponta a ponta

Roteiro para comprovar a feature 003 depois de implementada. Contratos:
[rotas-e-autorizacao.md](./contracts/rotas-e-autorizacao.md),
[composicao-entrada.md](./contracts/composicao-entrada.md),
[interface-estoque.md](./contracts/interface-estoque.md). Modelo: [data-model.md](./data-model.md).

## Pré-requisitos

- Ambiente da 001, 002 e 004 funcionando. Schema recriado com `make resetdb` depois de incluir o app
  `estoque` (sem migrations; os triggers nascem no `post_migrate`).
- `make setup` cria os usuários de desenvolvimento (`chefe`, `funcionario`, `auditor`,
  `requisitante`, `almox.inativo`...) e importa o catálogo. Os fornecedores são importados quando
  `docs/CSVs/fornecedores.csv` existe localmente. Sem ele, importar um CSV de
  `tests/fixtures/fornecedores/` pela tela da 004 antes de começar.

## 1. Suíte automatizada

```bash
make test
```

Esperado: toda a suíte passa, incluindo `tests/test_estoque_*.py` e os testes da Home. Os testes de
concorrência rodam com `transaction=True`.

## 2. Registrar entrada (US1)

Como `funcionario`, abrir **Registrar entrada de materiais** na Home.

1. Anotar o saldo de dois materiais na consulta do catálogo (A com saldo > 0; B qualquer).
2. Motivo "Compra", tipo "Nota fiscal", número `12345`, emitente buscado pelo nome e escolhido.
   Buscar A pelo código exato e B por duas palavras da descrição sem acento. Quantidades `4` e
   `0,750`.
3. "Revisar": o resumo mostra referência, emitente, os dois itens, saldo atual e resultante.
   Conferir no catálogo que nenhum saldo mudou.
4. "Voltar e corrigir", mudar a quantidade de B para `1,5`, revisar de novo e confirmar. Esperado:
   detalhe da entrada com motivo, referência, autor `funcionario`, momento e os dois itens; no
   catálogo, os saldos de A e B aumentaram exatamente 4 e 1,5 (SC-001).
5. Voltar no navegador até o resumo e confirmar de novo. Esperado: aviso "já foi registrada" e o
   mesmo detalhe; continua existindo uma única entrada (SC-005).
6. Nova entrada com a mesma nota `12345` do mesmo emitente: "Revisar" recusa e aponta a entrada
   existente. Com outro emitente, a mesma nota é aceita.
7. Recusas sem efeito: motivo "Compra" sem emitente; nenhum item; o mesmo material duas vezes;
   quantidade `0`, `-1`, `2,5001` e `0.750`. Cada uma indica o campo e preserva o resto.
8. Escolher emitente: um fornecedor bloqueado aparece com o selo e sem ação de escolher.

Cronometrar uma entrada de um material, do clique na Home à confirmação: menos de um minuto
(SC-007).

## 3. Consultar entradas (US2)

1. Como `funcionario` e como `auditor`: **Consultar entradas** lista as entradas da mais recente
   para a mais antiga, com momento, motivo, referência, autor e situação; o detalhe mostra código,
   descrição, unidade e quantidade de cada item.
2. Como `requisitante`: `/estoque/entradas/` e o detalhe respondem 403, e a Home não oferece os
   atalhos. `/estoque/entradas/nova/` também responde 403 para `auditor`.
3. Nenhuma tela oferece editar ou excluir entrada.

## 4. Estornar (US3)

1. Como `funcionario`, abrir `/estoque/entradas/<pk>/estorno/` da entrada da seção 2: 403.
2. Como `chefe`, abrir o detalhe e **Estornar entrada**: a página mostra, por item, o saldo atual e
   o resultante. Confirmar sem justificativa: recusado. Com justificativa: os saldos voltam ao que
   eram antes da entrada, a situação passa a "Estornada" e o detalhe mostra autor, momento e
   justificativa do estorno.
3. Repetir o POST do estorno (voltar e reenviar): aviso "já foi estornada", nada muda.
4. Registrar a nota `12345` do mesmo emitente de novo: agora é aceita.
5. Saldo insuficiente: registrar uma entrada de 10 unidades de um material de saldo 0. Pelo
   `make shell`, reduzir o saldo desse material para 7, simulando uma saída de uma feature futura:

   ```python
   Material.objects.filter(pk=...).update(saldo=7)
   ```

   Tentar estornar: recusado inteiro, com o item marcado. Refazer `make resetdb` depois, porque o
   ajuste manual quebra a propriedade de conservação.

## 5. Imutabilidade no banco

No `make shell`:

```python
MovimentacaoEstoque.objects.update(variacao=1)
ItemEntrada.objects.all().delete()
Entrada.objects.update(numero_documento="x")
```

Esperado: cada comando levanta erro do banco e nada muda (FR-018, `INV-MOV-001`).
