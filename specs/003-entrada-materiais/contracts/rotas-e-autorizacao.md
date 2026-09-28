# Contrato — Rotas e autorização (entradas)

Prefixo `/estoque/`, `app_name = "estoque"`. Todas as views derivam de
`catalogo.views.ExigePapelMixin`: anônimo → login; autenticado sem o papel → 403; inativo → tratado
como anônimo (`INV-AUTH-001`). Sem exceção para superusuário técnico nem para administrador de
sistema. Toda autorização é checada na rota; visibilidade de link na interface é só conveniência.

| Método e rota | Nome | Papel exigido | Capability | Efeito |
|---|---|---|---|---|
| GET `/estoque/entradas/` | `entradas` | `FUNCIONARIO_ALMOXARIFADO` ou `AUDITOR` | `PERM-STOCK-HISTORY-VIEW` (recorte da entrada, FR-021) | lista paginada (50), da mais recente para a mais antiga |
| GET `/estoque/entradas/<pk>/` | `entrada_detalhe` | idem | idem | detalhe; dados do estorno quando houver; ação "Estornar entrada" só para `CHEFE_ALMOXARIFADO` em entrada não estornada |
| GET `/estoque/entradas/nova/` | `entrada_nova` | `FUNCIONARIO_ALMOXARIFADO` | `PERM-STOCK-ENTRY-CREATE` | formulário vazio com nova `chave_confirmacao` |
| POST `/estoque/entradas/nova/` | `entrada_nova` | idem | idem | ação de composição ou revisão ([composicao-entrada.md](./composicao-entrada.md)); nunca grava |
| POST `/estoque/entradas/nova/confirmar/` | `entrada_confirmar` | idem | idem | revalida tudo e registra (ver "Confirmação") |
| GET `/estoque/entradas/<pk>/estorno/` | `entrada_estorno` | `CHEFE_ALMOXARIFADO` | `PERM-STOCK-ENTRY-REVERSE` | resumo de saldos atual e resultante por item e campo de justificativa |
| POST `/estoque/entradas/<pk>/estorno/` | `entrada_estorno` | idem | idem | ver "Estorno" |

`<pk>` inexistente → 404, depois da checagem de papel (sem revelar existência a quem não tem
acesso). Nenhuma rota altera ou exclui entrada, item, estorno ou movimentação. Nenhum modelo de
`estoque` é registrado no admin.

## Confirmação (POST `/estoque/entradas/nova/confirmar/`)

| Situação | Resposta |
|---|---|
| `chave_confirmacao` ausente ou malformada | 400, mensagem genérica, nada gravado |
| `EntradaJaRegistrada` (também no "Revisar", quando a referência pertence à entrada registrada com a mesma chave) | conteúdo igual ao registrado: aviso "Esta entrada já foi registrada."; conteúdo diferente (motivo, tipo, número, emitente ou itens): aviso "Este formulário já foi usado para registrar a entrada #<pk>; inicie uma nova entrada."; nos dois casos, nada gravado e 302 para o detalhe da entrada existente — ou, em requisição HTMX, resposta com `HX-Redirect` para o mesmo detalhe |
| dados inválidos (campo, item, quantidade) | formulário de composição re-renderizado com erros por campo e dados preservados (FR-009); 200 |
| `ReferenciaJaUsada(entrada)` | formulário re-renderizado, erro no número do documento com link para a entrada existente |
| `EmitenteIndisponivel` (inexistente ou bloqueado) | formulário re-renderizado, erro no emitente, escolha limpa |
| `SaldoAcimaDoLimite(material)` | formulário re-renderizado, erro na quantidade do item |
| erro inesperado | log com traceback; alerta genérico; formulário re-renderizado com os dados preservados |
| sucesso | mensagem "Entrada registrada: N itens." → 302 para o detalhe |

Em toda recusa, nada é gravado e nenhum saldo muda.

## Estorno (POST `/estoque/entradas/<pk>/estorno/`)

| Situação | Resposta |
|---|---|
| `EntradaJaEstornada`, ou entrada já estornada no GET ou no POST | aviso "Esta entrada já foi estornada." → 302 para o detalhe, sem renderizar o formulário |
| justificativa vazia | página re-renderizada com erro no campo |
| `EstornoBloqueadoPorSaldo(itens)` | página re-renderizada com alerta e, na tabela, cada item que ficaria negativo marcado com o motivo; nada gravado |
| erro inesperado | log com traceback; alerta genérico; página re-renderizada |
| sucesso | mensagem "Entrada estornada." → 302 para o detalhe, que passa a mostrar a situação "Estornada" e os dados do estorno |

## Home

`contas.views.HomeView` ganha `pode_registrar_entrada` (`FUNCIONARIO_ALMOXARIFADO`) e
`pode_consultar_entradas` (`FUNCIONARIO_ALMOXARIFADO` ou `AUDITOR`), derivados do mesmo `set` de
papéis já lido (sem consulta extra). O item "Registrar entrada de materiais" sai de
`CAPACIDADES_PLANEJADAS`.

## Matriz de teste de permissão

Rota × {anônimo, inativo, superusuário técnico, requisitante, chefe de setor, administrador de
sistema, auditor, funcionário do almoxarifado, chefe do almoxarifado}:

| Rota | Autorizados | Demais |
|---|---|---|
| lista, detalhe | auditor, funcionário do almoxarifado, chefe do almoxarifado | 403 (anônimo e inativo → login) |
| nova (GET/POST), confirmar | funcionário do almoxarifado, chefe do almoxarifado (que também tem `ROLE-WAREHOUSE-STAFF`) | 403, e nenhuma escrita |
| estorno (GET/POST) | chefe do almoxarifado | 403, e nenhuma escrita (inclusive para o funcionário do almoxarifado) |

As fixtures de `tests/conftest.py` já cobrem esses papéis. O chefe do almoxarifado tem os três
papéis explícitos da matriz.
