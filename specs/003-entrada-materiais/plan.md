# Implementation Plan: Entrada de Materiais

**Branch**: `claude/003-entrada-materiais` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-entrada-materiais/spec.md`

## Summary

Registrar no WMS o recebimento de materiais: o funcionário do almoxarifado compõe uma entrada com
motivo, referência (tipo, número e emitente do cadastro de fornecedores) e um ou mais itens do
catálogo. Ele revisa um resumo com os saldos atual e resultante e confirma. O saldo de cada
material aumenta atomicamente, com uma movimentação rastreável por item. As entradas podem ser
consultadas pelo almoxarifado e pelo auditor. O chefe do almoxarifado corrige uma entrada errada
por estorno total, com justificativa, bloqueado se deixar saldo negativo.

Abordagem técnica: novo app `estoque`, dono de `MovimentacaoEstoque`, o fato transversal que as
próximas operações e `HIS` vão usar, e da `Entrada`, com itens e estorno. As duas operações que
alteram saldo ficam em `estoque/entradas.py`, numa transação com locks em ordem fixa. Na composição
não há estado no servidor: o formulário carrega a entrada até a confirmação, que revalida tudo, e
uma chave única de confirmação impede duplicidade. As listas fechadas, a referência única entre
entradas não estornadas, o emitente obrigatório por motivo, o saldo não negativo e o estorno único
também são garantidos no banco. Triggers impedem alterar ou apagar os fatos registrados. Reusa
`ExigePapelMixin`, `normalizar_para_busca`, `PADRAO_CADPRO` e os componentes visuais existentes.
Nenhuma dependência nova. Decisões em [research.md](./research.md).

## Situação no roadmap e prontidão

- **Linha do ROADMAP**: `ENT` — Inclui: entrada nos motivos canônicos, com referência e emitente
  do cadastro de fornecedores; rastreabilidade da operação; estorno total pelo chefe, com
  justificativa. **Não inclui**: criar materiais; cadastrar ou importar fornecedores;
  compras/licitações; devolução de requisição (`DEV`); ajuste de inventário (`INV`); importar
  movimentações do SCPI; estorno parcial. Este plano não atravessa nenhuma dessas exclusões. A
  consulta das entradas é a da própria operação, sem filtros. A consulta transversal fica com `HIS`
  (Histórico de movimentações).
- **Dependências obrigatórias**: `001` (Importação do catálogo) e `FOR` (Importação de
  fornecedores, spec 004, [PR #21](https://github.com/joaorighetto/WMS-Almoxarifado/pull/21)),
  ambas concluídas em `main`. A `002` (Autenticação) também está entregue.
- **Decisões pendentes da capacidade**: composição, referência, fluxo de confirmação, bloqueio de
  documento repetido, emitente e estorno foram fixados na spec (sessão de 2026-09-25 e `clarify`).
  Nenhum `[NEEDS CLARIFICATION]` resta. A regra de material inativo fica para `MAT`, como a spec
  registra, e não bloqueia a implementação.
- **Branch**: `claude/003-entrada-materiais`, criada a partir de `main` em 2026-09-27. A branch
  local antiga `003-entrada-materiais` ficou para trás de `main` e não é usada.

## Technical Context

**Language/Version**: Python 3.13; Django 6.x (`django>=6.0`).

**Primary Dependencies**: `django` (com `django.contrib.postgres`), `psycopg`. HTMX 4 já versionado em
`static/vendor/htmx/`. Nenhum pacote novo.

**Storage**: PostgreSQL 16. Esquema efêmero, sem migrations; triggers de imutabilidade criados no
`post_migrate` de `estoque`. `UniqueConstraint(nulls_distinct=False)` exige PostgreSQL 15+.

**Testing**: pytest + pytest-django; `django_db(transaction=True)` com `threading.Barrier` para
concorrência, no molde de `tests/test_catalogo_atomicidade.py`; fixtures de papel de
`tests/conftest.py`; `Material` e `Fornecedor` criados diretamente em fixtures de teste (não há
CRUD de domínio para eles).

**Target Platform**: servidor Linux; desktop do almoxarifado (tablet ainda não validado no design
system).

**Project Type**: aplicação Django monolítica server-rendered.

**Performance Goals**: uma entrada de um material, do início à confirmação, em menos de um minuto
(SC-007). Buscas de material e emitente pelos índices existentes (GIN trigram, btree, `UNIQUE`),
limitadas a 20 resultados. Lista de entradas paginada com `select_related` e contagem de itens
anotada, sem N+1.

**Constraints**: nada gravado antes da confirmação (FR-008); registro e estorno indivisíveis
(`INV-STOCK-004`); nenhuma perda de atualização sob concorrência (FR-012); confirmação idempotente
(FR-013); fatos imutáveis (`INV-MOV-001`); saldo nunca negativo (`INV-STOCK-001`).

**Scale/Scope**: equipe pequena do almoxarifado; dezenas de entradas por dia, com poucos a algumas
dezenas de itens cada; cerca de 10 mil materiais e 10 mil fornecedores.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Princípio | Status | Justificativa |
|---|---|---|
| I. Simplicidade | PASS, com duas justificativas | Models, forms, formset, CBVs e mixins nativos. O módulo de domínio `estoque/entradas.py` e os triggers de imutabilidade estão justificados em Complexity Tracking. Nenhuma camada genérica de "operação de estoque" (research R1). |
| II. Server-Driven | PASS | Django Templates; a composição inteira é server-side, e o HTMX só troca a região do formulário (research R3). |
| III. Integridade de Dados | PASS | Transação única por operação; `select_for_update` em ordem fixa (`Entrada` → `Fornecedor` → `Material` por `pk`); no banco: `CHECK` de listas fechadas, número não vazio, emitente por motivo, quantidade > 0, saldo posterior ≥ 0 e coerente, origem por tipo; `UNIQUE` de chave, referência ativa, item por material e movimentação por item e tipo; `OneToOne` do estorno; triggers de imutabilidade. |
| IV. Rastreabilidade | PASS | Entrada com autor, momento e referência; movimentação por item com saldos anterior e posterior; estorno como registro próprio; nada é excluído nem sobrescrito. |
| V. Regras no Backend | PASS | A confirmação revalida tudo que veio do formulário. Templates recebem saldos e flags prontos. |
| VI. Segurança | PASS | Papel explícito em toda rota, inclusive nos POSTs de composição; CSRF padrão; 404 só depois da checagem de papel; mensagens de erro genéricas em falha inesperada; texto livre fora do log. |
| VII. Testes | PASS | Por risco: conservação de saldo, atomicidade com falha injetada, concorrência de entradas e de estornos, idempotência, referência única sob corrida, emitente bloqueado sob corrida, imutabilidade no banco, permissões rota × papel, quantidade e fluxo HTTP. |
| VIII. Design System | PASS, com gate pendente | Reusa Page Header, Filter Bar, Table, Badge, Resumo de totais, Confirmação persistente, Alert, Empty State, Pagination e Retorno contextual. Estreia o botão Destrutivo já previsto. Composição com tabela editável é padrão novo → `DESIGN.md` atualizado por `impeccable document`. `frontend-implementer` com `frontend-design`; `impeccable critique` depois do `code-reviewer`. |
| IX. Progressive Enhancement | PASS | Toda ação da composição é um submit comum; o HTMX só evita recarregar a página. |
| X. Performance | PASS | Buscas indexadas e limitadas; lista paginada; `select_related`/`annotate`; locks só nas linhas da operação. |
| XI. Dependências | PASS | Nenhuma nova. |
| XII. Manutenibilidade | PASS | Nomes do domínio (`Entrada`, `ItemEntrada`, `EstornoEntrada`, `MovimentacaoEstoque`, `registrar_entrada`). Parser de quantidade próprio em vez de flags no do catálogo (research R8). |
| XIII. Migrações | PASS | Esquema efêmero: models + `make resetdb`. O SQL dos triggers vira `RunSQL` quando as migrations voltarem (research R7). |
| XIV. Observabilidade | PASS | Logger `estoque.entradas` com ids, autor, motivo e contagens; sem número de documento nem justificativa (research R14). |

**Re-check pós-design**: `data-model.md` e os contratos mantêm todos os itens. Nenhuma violação
nova.

## Project Structure

### Documentation (this feature)

```text
specs/003-entrada-materiais/
├── spec.md
├── plan.md                         # este arquivo
├── research.md                     # R1–R14
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── rotas-e-autorizacao.md      # rotas, papel/capability, respostas, matriz de teste
│   ├── composicao-entrada.md       # campos, ações, resumo, quantidade, mensagens
│   └── interface-estoque.md        # assinaturas e exceções de estoque.entradas/quantidade
├── checklists/requirements.md
└── tasks.md                        # /speckit-tasks
```

### Source Code (repository root)

```text
config/settings/base.py            # ALTERADO: INSTALLED_APPS += "estoque" (depois de
                                   #   "fornecedores"); logger "estoque.entradas"
config/urls.py                     # ALTERADO: include("estoque.urls") em "estoque/"

estoque/                           # NOVO app
├── apps.py                        # post_migrate → criar_triggers_imutabilidade (idempotente)
├── models.py                      # MotivoEntrada, TipoDocumentoEntrada, TipoMovimentacao,
│                                  #   Entrada, ItemEntrada, EstornoEntrada, MovimentacaoEstoque
├── quantidade.py                  # interpretar_quantidade_recebida, QuantidadeInvalida
├── entradas.py                    # EntradaInformada, validar_entrada, registrar_entrada,
│                                  #   estornar_entrada, exceções
├── forms.py                       # CabecalhoEntradaForm, ItemEntradaForm + formset,
│                                  #   EstornoEntradaForm
├── views.py                       # ConsultaEntradasMixin; lista, detalhe, composição,
│                                  #   confirmação, estorno
├── urls.py                        # app_name = "estoque"
├── templates/estoque/
│   ├── entradas.html              # lista paginada
│   ├── entrada_detalhe.html
│   ├── entrada_nova.html          # página + partials: formulário, resultados de busca, resumo
│   └── entrada_estorno.html
└── static/estoque/css/estoque.css # só composição específica da feature, se precisar

contas/views.py                    # ALTERADO: pode_registrar_entrada, pode_consultar_entradas;
                                   #   item ENT removido de CAPACIDADES_PLANEJADAS
contas/templates/contas/home.html  # ALTERADO: duas linhas na lista de tarefas

DESIGN.md, .impeccable/design.json # ALTERADOS na entrega, por `impeccable document` (scan)

tests/
├── conftest.py                                  # ALTERADO: fixtures material/fornecedor
├── test_estoque_quantidade.py                   # tabela normativa de composicao-entrada.md
├── test_estoque_modelos.py                      # constraints e triggers
├── test_estoque_registro.py                     # registrar_entrada: efeito, regras, SC-001/002
├── test_estoque_estorno.py                      # estornar_entrada: efeito, bloqueio, único
├── test_estoque_concorrencia.py                 # transacional: soma, chave, referência,
│                                                #   emitente bloqueado, estornos, importação
├── test_estoque_atomicidade.py                  # falha injetada no meio → nada gravado
├── test_estoque_views_entrada.py                # composição, resumo, confirmação (HTTP e HTMX)
├── test_estoque_views_consulta.py               # lista, detalhe, estados vazios
├── test_estoque_views_estorno.py
├── test_estoque_permissoes.py                   # rota × papel, sem escrita quando negado
└── test_contas_home_papeis.py                   # ALTERADO: novos atalhos por papel
```

**Structure Decision**: app novo na raiz, com a convenção de `catalogo` e `fornecedores`. Testes em
`tests/`, com o prefixo do app.

## Fluxos

### Composição, resumo e confirmação

```text
GET  /estoque/entradas/nova/                       [FUNCIONARIO_ALMOXARIFADO]
  formulário vazio + chave_confirmacao = uuid4()

POST /estoque/entradas/nova/  (acao / adicionar_material / remover_item / escolher_emitente ...)
  reconstrói cabeçalho + formset do POST; exibição de material/emitente lida do banco pelo pk
  buscar → só SELECT limitado a 20
  revisar → validar_entrada(dados)            # só leitura
              inválido → formulário com erros (200)
              válido   → resumo com saldos atuais e resultantes + dados em campos ocultos

POST /estoque/entradas/nova/confirmar/
  dados = do POST, revalidados pelos forms
  registrar_entrada(dados, request.user):
    transaction.atomic():
      chave já usada → EntradaJaRegistrada
      validar_entrada(dados)
      Fornecedor select_for_update → bloqueado? → EmitenteIndisponivel
      Material select_for_update order_by pk → limite? → SaldoAcimaDoLimite
      savepoint: INSERT Entrada → IntegrityError(ref) → ReferenciaJaUsada
                                 → IntegrityError(chave) → EntradaJaRegistrada
      INSERT ItemEntrada × n; UPDATE Material.saldo × n; INSERT MovimentacaoEstoque × n
  302 detalhe
```

### Estorno

```text
GET  /estoque/entradas/<pk>/estorno/               [CHEFE_ALMOXARIFADO]
  itens com saldo atual e resultante; itens que ficariam negativos já marcados

POST /estoque/entradas/<pk>/estorno/
  estornar_entrada(pk, justificativa, request.user):
    transaction.atomic():
      Entrada select_for_update → estornada? → EntradaJaEstornada
      justificativa vazia → JustificativaAusente
      Material select_for_update order_by pk → algum saldo < quantidade → EstornoBloqueadoPorSaldo
      INSERT EstornoEntrada; UPDATE Entrada.estornada = true
      UPDATE Material.saldo × n; INSERT MovimentacaoEstoque(ESTORNO_ENTRADA) × n
  302 detalhe
```

## Autorização

Ver [rotas-e-autorizacao.md](./contracts/rotas-e-autorizacao.md). Composição, resumo e confirmação
→ `PERM-STOCK-ENTRY-CREATE` (`ROLE-WAREHOUSE-STAFF`). Estorno → `PERM-STOCK-ENTRY-REVERSE`
(`ROLE-WAREHOUSE-HEAD`). Lista e detalhe → `PERM-STOCK-HISTORY-VIEW`, no recorte que a spec fixa
para a entrada (FR-021): `ROLE-WAREHOUSE-STAFF` e `ROLE-AUDITOR` veem tudo, os demais nada. A busca
de material dentro da composição cabe em `PERM-MATERIAL-VIEW`, que todo funcionário do almoxarifado
tem por `ROLE-REQUESTER`. A de emitente cabe em `PERM-SUPPLIER-VIEW` (`ROLE-WAREHOUSE-STAFF`).
Nenhuma capability é criada, ampliada ou redefinida.

## Regras canônicas aplicadas e preservadas

| ID | Mecanismo |
|---|---|
| `PERM-STOCK-ENTRY-CREATE` | `ExigePapelMixin(FUNCIONARIO_ALMOXARIFADO)` em GET e POST de composição e na confirmação |
| `PERM-STOCK-ENTRY-REVERSE` | `ExigePapelMixin(CHEFE_ALMOXARIFADO)` no estorno; ação exibida só ao chefe |
| `PERM-STOCK-HISTORY-VIEW` | `ConsultaEntradasMixin`: `tem_papel(FUNCIONARIO_ALMOXARIFADO, AUDITOR)` |
| `PERM-MATERIAL-VIEW`, `PERM-SUPPLIER-VIEW` | buscas só dentro das rotas de composição, cujo papel já implica as duas |
| `INV-AUTH-001` | comportamento da 002; confirmação usa o `request.user` do próprio POST; teste com usuário desativado |
| `INV-CATALOG-003`, `INV-CATALOG-004` | FK `PROTECT`; `estoque` só escreve `Material.saldo` (`update_fields=["saldo"]`); teste de campos cadastrais intactos |
| `INV-CATALOG-005` | quantidade na unidade exibida, sem conversão |
| `INV-STOCK-001` | `CHECK saldo >= 0` de `Material` + `CHECK saldo_posterior >= 0`; estorno checado sob lock |
| `INV-STOCK-002`, `INV-STOCK-003` | `catalogo/importacao.py` nunca escreve `saldo` e compara o arquivo com o saldo atual. Teste de regressão: reimportar depois de uma entrada preserva o saldo e gera divergência informativa |
| `INV-STOCK-004` | `transaction.atomic()` única por operação; teste com falha injetada depois da primeira movimentação |
| `INV-MOV-001` | sem caminho de edição; triggers `BEFORE UPDATE OR DELETE`; estorno como registro compensatório |
| `INV-MOV-002` | uma `MovimentacaoEstoque` por item, na mesma transação, com origem, autor, variação, saldos e momento |
| `INV-ENT-001` | estorno sem itens próprios (sempre total); `OneToOne`; lock da entrada |
| `INV-SUPPLIER-003` | `estoque` só lê `Fornecedor` |
| `INV-SUPPLIER-005` | bloqueado sem ação na busca; recusado no "Revisar" e, sob lock, na confirmação |
| `INV-SCPI-001` | nenhuma chamada externa |

## Testes

Priorizados por risco. O `test-engineer` revisa e completa antes da implementação, pelo pipeline de
alterações de estoque.

- **Conservação** (CRÍTICO, SC-001/SC-002): depois de sequências de entradas e estornos, para cada
  material, `saldo = saldo_inicial + Σ variacao` e `= saldo_inicial + Σ itens de entradas não
  estornadas`; cada item tem exatamente uma movimentação `ENTRADA` e, se estornado, uma
  `ESTORNO_ENTRADA`.
- **Atomicidade** (CRÍTICO): falha injetada, por `monkeypatch`, no meio do registro e do estorno →
  nenhum saldo, entrada, item, estorno ou movimentação gravados.
- **Concorrência** (CRÍTICO, transacional): N entradas simultâneas do mesmo material → soma exata;
  mesma `chave_confirmacao` em paralelo → uma entrada; mesma referência em paralelo → uma entrada;
  bloqueio do emitente por reimportação concorrente → a entrada é recusada ou vem antes, nunca
  registra emitente bloqueado depois dele; dois estornos da mesma entrada → um; estorno concorrente
  com redução de saldo → nunca negativo; entrada concorrente com reimportação do catálogo → sem
  deadlock e saldo preservado.
- **Imutabilidade** (CRÍTICO): `update()`/`delete()` e `save()` em entrada, item, estorno e
  movimentação levantam erro do banco; `Entrada.estornada` só aceita `false → true`; o `flush`
  dos testes transacionais reemite o `post_migrate`, que precisa ser idempotente.
- **Constraints**: cada `CHECK` e `UNIQUE` de `data-model.md` com um `IntegrityError` esperado,
  incluindo "ambas sem emitente" (`nulls_distinct=False`) e referência liberada após o estorno.
- **Regras de registro**: motivo e tipo fora da lista, número só com espaços, emitente por motivo,
  lista vazia, material repetido, material inexistente, saldo acima do limite, material com saldo
  zero, unidade preservada.
- **Quantidade**: toda a tabela normativa de [composicao-entrada.md](./contracts/composicao-entrada.md).
- **Fluxo HTTP**: buscar, adicionar, remover e revisar não gravam nada; os dados são preservados
  nos erros; o resumo mostra saldo atual e resultante; desistir não grava; confirmar redireciona ao
  detalhe; reenvio → "já registrada"; campos ocultos adulterados (material inexistente, motivo
  inválido, emitente bloqueado) → recusa; respostas com e sem `HX-Request`; sessão expirada e
  usuário desativado → login, nada gravado.
- **Consulta**: ordem da mais recente para a mais antiga, paginação, situação, dados do estorno no
  detalhe, estado vazio, número fixo de queries na lista.
- **Permissões**: matriz de [rotas-e-autorizacao.md](./contracts/rotas-e-autorizacao.md), incluindo
  POSTs diretos sem passar pela tela e a verificação de que nada foi gravado.
- **SC-008**: nenhum modelo de `estoque` no admin; nenhuma rota aceita alteração de entrada.
- **Home**: atalhos por papel; ENT fora de "Em preparação".

## Pipeline de implementação

Alteração crítica de estoque com frontend significativo:

```text
test-engineer (cenários críticos acima)
→ task-implementer (models, triggers, quantidade, entradas, views sem acabamento visual, testes)
→ frontend-implementer (telas de composição, resumo, lista, detalhe, estorno; Home)
→ code-reviewer
→ impeccable critique (gate visual) → correções
→ impeccable document (scan) para DESIGN.md e sidecar
→ converge
```

O `wms-explorer` já rodou nesta fase de plano: impacto em `catalogo` (sem mudança de código),
padrões de autorização, busca, parser de quantidade e testes de concorrência.

## Spec/domain check

- **Spec**: FR-001 a FR-030 e SC-001 a SC-009 têm mecanismo (`data-model.md` → rastreamento;
  contratos). SC-007 depende do desenho da tela e é conferido no quickstart.
- **Matrizes canônicas**: consistente com `PERM-STOCK-ENTRY-CREATE`, `PERM-STOCK-ENTRY-REVERSE`,
  `PERM-STOCK-HISTORY-VIEW` (recorte justificado por FR-021), `PERM-MATERIAL-VIEW`,
  `PERM-SUPPLIER-VIEW` e com as `INV-*` listadas. `INV-STOCK-003` não está na seção de regras da
  spec, mas o edge case de reimportação a aplica; o plano a registra como preservada.
- **ROADMAP**: dentro do recorte de `ENT`. Status atualizado para refletir plano e tarefas
  gerados, ainda sem implementação.
- **Nenhum conflito material.**

## Open Questions

Nenhum PLAN BLOCKER. Não bloqueantes:

1. **Limite de 20 resultados** nas buscas de material e emitente (research R9): escolha de
   interface, não regra de domínio. Pode ser ajustado no gate visual sem tocar a spec.
2. **Recusa de `0.750`** (research R8): mais restritiva que a leitura do CSV do catálogo, para
   evitar ler ponto decimal como milhar. Se o dono do produto preferir outra convenção, muda só a
   tabela normativa.
3. **Índice `(material, -registrada_em)`** em `MovimentacaoEstoque`: antecipa a consulta por
   material de `HIS` sem implementá-la. Pode ser removido se o `code-reviewer` o considerar
   especulativo.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Módulo de domínio `estoque/entradas.py` fora de models/views | Registro e estorno atravessam quatro modelos sob locks ordenados numa transação, e a mesma regra é chamada pela view, pelo "Revisar" (validação) e pelos testes de concorrência. | Na view, a regra crítica ficaria misturada com formulário e HTTP e não poderia ser chamada pelos testes de concorrência sem cliente HTTP; num manager, atravessaria quatro modelos. |
| Triggers de imutabilidade criados em `post_migrate` | `INV-MOV-001` é CRÍTICA e classificada como "banco/constraint". Sem trigger, `QuerySet.update()`, `delete()` ou o shell alteram fatos de estoque em silêncio. | Só a ausência de caminho na aplicação protege contra a interface, mas não contra código futuro nem contra acesso direto (Constitution III). Uma migration com `RunSQL` não existe na fase atual (Constitution XIII). |
