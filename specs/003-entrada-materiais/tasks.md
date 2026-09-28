---

description: "Task list for implementing 003-entrada-materiais"
---

# Tasks: Entrada de Materiais

**Input**: Design documents from `specs/003-entrada-materiais/` (`spec.md`, `plan.md`,
`research.md`, `data-model.md`, `contracts/rotas-e-autorizacao.md`,
`contracts/composicao-entrada.md`, `contracts/interface-estoque.md`, `quickstart.md`)

**Prerequisites**: `plan.md` (Constitution Check PASS), `spec.md` (3 user stories, P1–P3),
`research.md` (R1–R14). Dependências obrigatórias do roadmap satisfeitas: `001` (Importação do
catálogo) e `FOR` (Importação de fornecedores).

**Tests**: obrigatórios (Constitution VII). A feature é a primeira que altera saldo: toca estoque,
movimentações, permissões, transações, concorrência e rollback. Em cada story, os testes vêm antes
da implementação e devem falhar primeiro.

**Organization**: por user story, na ordem de prioridade da spec. O modelo de dados inteiro e os
triggers ficam na fase Foundational, porque as três stories compartilham as mesmas tabelas. O
detalhe da entrada fica na US1, porque a confirmação redireciona para ele. A lista, o acesso do
auditor pela Home e o atalho de consulta ficam na US2.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: paralelizável (arquivo diferente, sem dependência de task incompleta)
- **[Story]**: US1–US3; ausente em Setup, Foundational e Polish
- **Executor**: sem marca → `task-implementer`; **(test-engineer)** → só testes;
  **(frontend-implementer)** → frontend significativo com `frontend-design`, dentro do
  `DESIGN.md`; **(coordenador)** → etapa do Claude principal
- **Aplica / Preserva**: IDs canônicos das matrizes

## Path Conventions

Django monolítico, apps na raiz (`contas/`, `catalogo/`, `fornecedores/`, novo `estoque/`), testes
em `tests/` com prefixo `test_estoque_`, primitivos CSS em `static/css/components.css`. Sem
migrations: depois de mudar models ou o handler de triggers, `make resetdb`.

## Escopo — limite para todas as tasks (ROADMAP, linha ENT, "Não inclui")

Nenhuma task pode introduzir: criação, edição ou exclusão de material, ou alteração de qualquer
campo de `Material` que não seja `saldo`; criação, edição ou importação de fornecedor; compras,
licitações, empenhos, empréstimos ou doações como módulos; devolução de requisição (`DEV`); ajuste
de inventário (`INV`); saídas, requisições ou atendimento (`SAE`, `REQ`, `ATE`); consulta
transversal de movimentações, filtros por material ou por operação (`HIS`); importação de
movimentações ou integração com o SCPI; controle de lançamentos pendentes no SCPI; locais, lotes,
validade, código de barras ou notificações; regra de material inativo (`MAT`); estorno parcial;
rascunho de entrada; refactor de `catalogo` ou `fornecedores` (só importar deles). Se uma task
parecer exigir isso, o implementador **para e reporta** ao coordenador.

---

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 Criar o app `estoque` na raiz (`estoque/__init__.py`, `estoque/apps.py` com
  `EstoqueConfig`, `default_auto_field` igual ao de `catalogo`), incluí-lo em `INSTALLED_APPS` de
  `config/settings/base.py` **depois** de `"fornecedores"` e acrescentar
  `path("estoque/", include("estoque.urls"))` em `config/urls.py`, com `estoque/urls.py` vazio
  (`app_name = "estoque"`)
- [x] T002 [P] Acrescentar o logger `estoque.entradas` em `LOGGING` de `config/settings/base.py`,
  no mesmo formato de `catalogo.importacao` e `fornecedores.importacao`
- [x] T003 [P] (test-engineer) Acrescentar a `tests/conftest.py` as fixtures de dados de estoque,
  criadas diretamente pelo ORM, sem CRUD de domínio: `execucao_catalogo` (uma
  `catalogo.ExecucaoImportacao` válida); `criar_material(cadpro, saldo, unidade="UN",
  descricao=...)`, com `saldo_inicial = saldo` e `descricao_busca` por `normalizar_para_busca`;
  `execucao_fornecedores`; `criar_fornecedor(codif, nome, bloqueado=False, documento="")`, com
  `nome_busca` e `documento_digitos` derivados como em `fornecedores/importacao.py`. Só dados
  fictícios

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: nenhuma story começa antes desta fase.

- [x] T004 (coordenador) Acionar o `test-engineer` com `plan.md` → "Testes", `data-model.md`,
  `contracts/interface-estoque.md`, `contracts/composicao-entrada.md` e
  `docs/domain/invariants-matrix.md`, para revisar e completar os cenários críticos antes da
  implementação. Prioridade para as `INV-*` de severidade CRÍTICA: `INV-STOCK-001`,
  `INV-STOCK-004`, `INV-MOV-001`, `INV-MOV-002`, `INV-ENT-001`. Os cenários aprovados entram nas
  tasks de teste abaixo, sem criar tasks novas fora do escopo
- [x] T005 Criar em `estoque/models.py`, conforme `data-model.md`:
  `MotivoEntrada` (`COMPRA` "Compra", `DOACAO_RECEBIDA` "Doação recebida",
  `DEVOLUCAO_FORNECEDOR_GARANTIA` "Devolução de fornecedor/garantia", `EMPRESTIMO_DEVOLVIDO`
  "Empréstimo devolvido"); `TipoDocumentoEntrada` (`NOTA_FISCAL` "Nota fiscal", `TERMO_DOACAO`
  "Termo de doação", `TERMO_RECIBO_DEVOLUCAO` "Termo/recibo de devolução"); `TipoMovimentacao`
  (`ENTRADA` "Entrada", `ESTORNO_ENTRADA` "Estorno de entrada").
  `Entrada`: `chave_confirmacao` UUID `UNIQUE`; `motivo` com `CHECK motivo IN (...)`;
  `tipo_documento` com `CHECK tipo_documento IN (...)`; `numero_documento` texto com
  "`CHECK trim(numero_documento) <> ''`"; `emitente` FK `fornecedores.Fornecedor` anulável
  `PROTECT` com "`CHECK emitente IS NOT NULL OR motivo IN (DOACAO_RECEBIDA,
  EMPRESTIMO_DEVOLVIDO)`"; `registrada_por` FK `contas.User` `PROTECT`; `registrada_em`;
  `estornada` booleano `default=False`; `UniqueConstraint(fields=["tipo_documento",
  "numero_documento", "emitente"], condition=Q(estornada=False), nulls_distinct=False,
  name="estoque_entrada_referencia_unica")`; ordering `-registrada_em`, `-pk`.
  `ItemEntrada`: `entrada` FK `PROTECT` `related_name="itens"`; `material` FK `catalogo.Material`
  `PROTECT`; `quantidade` decimal (15, 3) com "`CHECK quantidade > 0`"; `UNIQUE (entrada,
  material)`; ordering `material__cadpro`.
  `EstornoEntrada`: `entrada` `OneToOneField` `PROTECT` `related_name="estorno"`; `justificativa`
  com "`CHECK trim(justificativa) <> ''`"; `estornada_por` FK `contas.User` `PROTECT`;
  `estornada_em`.
  `MovimentacaoEstoque`: `material` FK `PROTECT` `related_name="movimentacoes"`; `tipo` com
  `CHECK tipo IN (...)`; `variacao` decimal (16, 3) com "`CHECK variacao <> 0`";
  `saldo_anterior` e `saldo_posterior` decimal (15, 3) com "`CHECK saldo_posterior =
  saldo_anterior + variacao`" e "`CHECK saldo_posterior >= 0`"; `registrada_por` FK `PROTECT`;
  `registrada_em`; `item_entrada` FK anulável `PROTECT`; `estorno_entrada` FK anulável `PROTECT`;
  `CHECK` de origem por tipo "`(tipo = ENTRADA AND item_entrada IS NOT NULL AND estorno_entrada IS
  NULL AND variacao > 0) OR (tipo = ESTORNO_ENTRADA AND item_entrada IS NOT NULL AND
  estorno_entrada IS NOT NULL AND variacao < 0)`"; `UNIQUE (item_entrada, tipo)`; índice
  `(material, -registrada_em)`; ordering `-registrada_em`, `-pk`.
  Nomes de constraint com prefixo `estoque_`. Nada registrado no admin. Rodar `make resetdb`.
  Preserva: `INV-CATALOG-003`, `INV-CATALOG-005`, `INV-STOCK-001`, `INV-MOV-002`, `INV-ENT-001`
- [x] T006 Implementar em `estoque/apps.py` `criar_triggers_imutabilidade(using, **kwargs)`,
  conectada a `post_migrate` com `sender=self` em `EstoqueConfig.ready()`, idempotente
  (`CREATE OR REPLACE FUNCTION`, `DROP TRIGGER IF EXISTS` antes de `CREATE TRIGGER`), conforme
  research R7: triggers `BEFORE UPDATE OR DELETE` que levantam erro em `ItemEntrada`,
  `EstornoEntrada` e `MovimentacaoEstoque`; em `Entrada`, `DELETE` levanta erro e `UPDATE` só é
  aceito quando a única mudança é `estornada` de `false` para `true` (`to_jsonb(OLD) - 'estornada'
  = to_jsonb(NEW) - 'estornada'` e `NOT OLD.estornada AND NEW.estornada`). Nomes de tabela via
  `Model._meta.db_table`, nunca literais. Docstring registrando que o SQL vira `RunSQL` quando as
  migrations voltarem (Constitution XIII). Rodar `make resetdb`. Preserva: `INV-MOV-001`
- [x] T007 [P] (test-engineer) Escrever `tests/test_estoque_modelos.py`: um `IntegrityError` para
  cada `CHECK` e `UNIQUE` de T005, incluindo referência repetida entre entradas não estornadas,
  "ambas sem emitente" como mesma referência, mesma referência aceita depois de `estornada=True`,
  mesmo número com emitentes diferentes aceito, compra sem emitente recusada, doação sem emitente
  aceita, movimentação com sinal ou origem incoerente com o tipo, segundo `EstornoEntrada` para a
  mesma entrada. Triggers: `update()`, `save()` e `delete()` em `ItemEntrada`, `EstornoEntrada` e
  `MovimentacaoEstoque` levantam erro do banco; `Entrada` recusa `DELETE`, recusa `UPDATE` de
  `numero_documento` e de `estornada` `true → false`, aceita só `false → true`; o handler pode
  rodar duas vezes seguidas sem erro. Nenhum modelo de `estoque` no admin

**Checkpoint**: modelos e triggers criados, constraints e imutabilidade testadas no banco.

---

## Phase 3: User Story 1 - Registrar a entrada de materiais recebidos (Priority: P1) 🎯 MVP

**Goal**: o funcionário do almoxarifado compõe a entrada (motivo, referência com emitente, itens),
revisa o resumo com saldos atual e resultante e confirma. Os saldos aumentam atomicamente, com uma
movimentação por item, e a confirmação repetida não duplica.

**Independent Test**: com materiais e fornecedores de fixture e um funcionário do almoxarifado
autenticado, registrar uma entrada de dois itens pela tela e verificar que cada saldo aumentou
exatamente na quantidade informada, que há uma movimentação `ENTRADA` por item e que o detalhe
exibe motivo, referência, itens, autor e momento. Reenviar a confirmação não cria uma segunda
entrada.

### Tests for User Story 1 ⚠️ (escrever primeiro; devem falhar)

- [x] T008 [P] [US1] (test-engineer) Escrever `tests/test_estoque_quantidade.py` (sem banco): toda a
  tabela "Quantidade — exemplos normativos" de `contracts/composicao-entrada.md`, com a mensagem de
  cada recusa (research R8); o retorno é sempre `Decimal` com três casas; nunca arredonda
- [x] T009 [P] [US1] (test-engineer) Escrever `tests/test_estoque_registro.py` sobre
  `estoque.entradas`: US1 cenários 1, 2, 4 a 7; `validar_entrada` não grava nada; cada regra de
  `EntradaInvalida` (lista vazia, material repetido, material inexistente, motivo e tipo fora da
  lista, número só com espaços, emitente ausente em compra e em devolução de fornecedor/garantia,
  emitente opcional em doação e empréstimo, emitente inexistente, emitente bloqueado, saldo
  resultante acima de 999.999.999.999,999); `numero_documento` gravado aparado e sem outra
  normalização; `ReferenciaJaUsada` aponta a entrada existente; `EntradaJaRegistrada` para chave
  repetida, sem nova gravação; material com saldo zero aceito; `registrada_em` atribuído pelo
  sistema; uma `MovimentacaoEstoque` `ENTRADA` por item com `variacao`, `saldo_anterior`,
  `saldo_posterior`, autor e momento iguais aos da entrada (SC-002); campos cadastrais do material e
  outros materiais intactos (FR-015, `INV-CATALOG-004`); unidade preservada; conservação
  `saldo = saldo_inicial + Σ variacao` (SC-001). Regressão `INV-STOCK-002`/`INV-STOCK-003`:
  reimportar o catálogo depois de uma entrada preserva o saldo e registra a divergência informativa
- [x] T010 [P] [US1] (test-engineer) Escrever `tests/test_estoque_atomicidade.py` (registro): falha
  injetada por `monkeypatch` depois da primeira movimentação e depois da atualização do primeiro
  saldo → nenhuma `Entrada`, `ItemEntrada`, `MovimentacaoEstoque` gravada e nenhum saldo alterado
  (`INV-STOCK-004`, SC-003)
- [x] T011 [P] [US1] (test-engineer) Escrever `tests/test_estoque_concorrencia.py` (registro),
  `django_db(transaction=True)`, no molde de `tests/test_catalogo_atomicidade.py` (`Barrier`,
  `SET lock_timeout`, `connection.close()` em `finally`, `join(timeout)`, exceções coletadas por
  thread): N entradas simultâneas do mesmo material → saldo final = soma de todas (FR-012,
  SC-004); mesma `chave_confirmacao` em paralelo → uma entrada, a outra `EntradaJaRegistrada`
  (SC-005); mesma referência com chaves diferentes em paralelo → uma entrada, a outra
  `ReferenciaJaUsada`; bloqueio do emitente por atualização concorrente de `Fornecedor.bloqueado`
  → a entrada é recusada ou vem antes, nunca registra depois do bloqueio; entrada concorrente com
  `catalogo.importacao.confirmar_importacao` sobre o mesmo material → sem deadlock e saldo da
  entrada preservado
- [x] T012 [P] [US1] (test-engineer) Escrever `tests/test_estoque_views_entrada.py`: GET da
  composição gera `chave_confirmacao`; cada ação de `contracts/composicao-entrada.md` (buscar
  material por código exato e por palavras sem acento; "Já incluído"; adicionar; remover; buscar
  emitente por código, por documento formatado e por nome; bloqueado sem ação de escolher;
  escolher; limpar; revisar; voltar) responde sem gravar nada; erros por campo com dados
  preservados (FR-009); o resumo mostra motivo, referência, emitente e, por item, saldo atual e
  resultante (FR-008); a confirmação redireciona ao detalhe; o reenvio leva ao detalhe com "Esta
  entrada já foi registrada."; campos ocultos adulterados (material inexistente, motivo inválido,
  emitente bloqueado, quantidade inválida) → recusa sem gravar; respostas com `HX-Request`
  (fragmento) e sem ele (página inteira); usuário desativado e sessão ausente na confirmação →
  login, nada gravado (`INV-AUTH-001`); o detalhe exibe motivo, referência, autor, momento e, por
  item, código, descrição, unidade e quantidade
- [x] T013 [P] [US1] (test-engineer) Escrever em `tests/test_estoque_permissoes.py` a parte de
  registro e detalhe da matriz de `contracts/rotas-e-autorizacao.md`: GET e POST de
  `entrada_nova` e POST de `entrada_confirmar` para anônimo, inativo, superusuário técnico,
  requisitante, chefe de setor, administrador de sistema, auditor, funcionário do almoxarifado e
  chefe do almoxarifado; POSTs diretos negados não gravam nada (SC-006); `entrada_detalhe` para
  os mesmos papéis (auditor, funcionário e chefe do almoxarifado autorizados); pk inexistente →
  404 só para autorizados

### Implementation for User Story 1

- [x] T014 [P] [US1] Implementar `estoque/quantidade.py`: `QuantidadeInvalida(ValueError)` com
  `mensagem` e `interpretar_quantidade_recebida(texto) -> Decimal`, conforme research R8 e
  `contracts/interface-estoque.md`: parte inteira `[0-9]+` ou `[1-9][0-9]{0,2}(\.[0-9]{3})+`,
  vírgula decimal opcional, sem sinal, no máximo três casas decimais sem arredondar, maior que zero,
  no máximo 12 dígitos inteiros. Não importar nem alterar `catalogo.leitura_scpi.interpretar_quantidade`.
  Preserva: `INV-CATALOG-005`
- [x] T015 [US1] Implementar em `estoque/entradas.py`: `ItemInformado`, `EntradaInformada`, as
  exceções `EntradaInvalida` (`erros_campo`, `erros_item` indexado pela posição do item), `EntradaJaRegistrada`,
  `ReferenciaJaUsada`, `EmitenteIndisponivel`, `SaldoAcimaDoLimite`, `validar_entrada(dados)` (só
  leitura) e `registrar_entrada(dados, autor)` com a sequência de research R5 numa única
  `transaction.atomic()`: chave já usada → `EntradaJaRegistrada`; `validar_entrada`; `Fornecedor`
  `select_for_update()` e reconferência de `bloqueado`; `Material.objects.filter(pk__in=...)
  .select_for_update().order_by("pk")`; limite de saldo; `INSERT` de `Entrada` num savepoint
  (`transaction.atomic()` aninhado), mapeando `IntegrityError` de
  `estoque_entrada_referencia_unica` para `ReferenciaJaUsada` e de `chave_confirmacao` para
  `EntradaJaRegistrada`; `ItemEntrada`; `Material.saldo` com `save(update_fields=["saldo"])`; uma
  `MovimentacaoEstoque` `ENTRADA` por item com saldos lidos sob lock e o mesmo `registrada_em`.
  Mensagens de `contracts/composicao-entrada.md`. Log `INFO`/`WARNING` conforme research R14, sem
  número de documento. Aplica: `PERM-STOCK-ENTRY-CREATE` (regras de motivo e referência).
  Preserva: `INV-STOCK-001`, `INV-STOCK-004`, `INV-MOV-002`, `INV-CATALOG-003`,
  `INV-CATALOG-004`, `INV-SUPPLIER-003`, `INV-SUPPLIER-005`
- [x] T016 [US1] Implementar em `estoque/forms.py` o `CabecalhoEntradaForm` (`chave_confirmacao`
  UUID oculto, `motivo`, `tipo_documento`, `numero_documento`, `emitente` oculto por `pk`,
  `busca_emitente`, `busca_material`) e o `ItemEntradaForm` + `formset_factory` com prefixo
  `itens`, sem `can_delete`, com `quantidade` validada por `interpretar_quantidade_recebida`
  (`inputmode="decimal"`); um método que monta `EntradaInformada` a partir dos forms válidos e
  traduz `EntradaInvalida` em erros de campo e de linha
- [x] T017 [US1] Implementar em `estoque/views.py` e `estoque/urls.py` (research R9, R12;
  `contracts/rotas-e-autorizacao.md`; `contracts/composicao-entrada.md`): `EntradaNovaView`
  (`ExigePapelMixin`, `papel_exigido = Papel.FUNCIONARIO_ALMOXARIFADO`) com GET (nova chave) e
  POST por ação (`acao`, `adicionar_material`, `remover_item`, `escolher_emitente`), buscas
  limitadas a 20 com total, exibição de material e emitente lida do banco pelo `pk` e fragmento
  com `HX-Request` (padrão `veio_de_htmx` de `catalogo/views.py`, com `patch_vary_headers`);
  `EntradaConfirmarView` (POST: revalida forms, chama `registrar_entrada` com `request.user`,
  trata cada exceção conforme a tabela "Confirmação", 400 para chave malformada, erro inesperado
  logado com mensagem genérica); `ConsultaEntradasMixin(ExigePapelMixin)` com `test_func` =
  `tem_papel(FUNCIONARIO_ALMOXARIFADO, AUDITOR)`; `EntradaDetalheView` com `select_related` e
  `prefetch_related` dos itens com material. Templates recebem saldos e flags prontos
  (Constitution V). Rotas `entrada_nova`, `entrada_confirmar`, `entrada_detalhe`.
  Aplica: `PERM-STOCK-ENTRY-CREATE`, `PERM-STOCK-HISTORY-VIEW` (recorte de FR-021).
  Preserva: `INV-AUTH-001`
- [x] T018 [US1] (frontend-implementer) Criar `estoque/templates/estoque/entrada_nova.html` (página
  + partials de formulário, resultados de busca de material, resultados de busca de emitente e
  resumo) e `estoque/templates/estoque/entrada_detalhe.html`, com os componentes de `DESIGN.md`:
  Page Header; campos com erro por `.field-has-error`; Filter Bar para as buscas; Table para itens
  e resultados (`.table-cell-code` sem reformatar o CADPRO; `.table-cell-numeric` para quantidade e
  saldos); Badge "Bloqueado" com o motivo; "Já incluído" sem ação; Empty State explicado; Resumo de
  totais; barra de Confirmação persistente com "Confirmar entrada: N itens" e "Voltar e corrigir",
  com estado "Confirmando…"; Alert para mensagens. Enter num campo de busca aciona a busca, nunca
  "Revisar"; tudo funciona sem JS (Constitution IX). CSS específico só em
  `estoque/static/estoque/css/estoque.css`. Desktop-first; toque sob `pointer: coarse` pelos tokens
  existentes
- [x] T019 [US1] Em `contas/views.py`, acrescentar `pode_registrar_entrada`
  (`FUNCIONARIO_ALMOXARIFADO`, a partir do mesmo `set` de papéis) e retirar o item ENT
  ("Registrar entrada de materiais") de `CAPACIDADES_PLANEJADAS`; em
  `contas/templates/contas/home.html`, a linha "Registrar entrada de materiais" na lista de
  tarefas, com link para `estoque:entrada_nova`; atualizar `tests/test_contas_home_papeis.py` e
  `tests/test_contas_home.py` onde esperavam o item planejado

**Checkpoint**: US1 funcional e testada por si só — é o MVP.

---

## Phase 4: User Story 2 - Conferir as entradas registradas (Priority: P2)

**Goal**: o funcionário do almoxarifado e o auditor consultam as entradas, da mais recente para a
mais antiga, e abrem o detalhe de cada uma.

**Independent Test**: registrar duas entradas por `registrar_entrada`, abrir a lista como
funcionário do almoxarifado e como auditor, verificar a ordem e as colunas e abrir o detalhe de
cada uma. Requisitante recebe 403.

### Tests for User Story 2 ⚠️ (escrever primeiro; devem falhar)

- [x] T020 [P] [US2] (test-engineer) Escrever `tests/test_estoque_views_consulta.py`: US2 cenários
  1 a 3; lista ordenada por `-registrada_em`, `-pk`, com momento, motivo, referência (tipo,
  número, emitente ou "Sem emitente"), autor e situação ("Registrada"/"Estornada"); paginação de
  50; estado vazio; número de queries constante com 1 e com 30 entradas
  (`django_assert_num_queries`); detalhe de entrada estornada mostra autor, momento e
  justificativa do estorno (dados criados diretamente no ORM, já que o estorno é da US3)
- [x] T021 [P] [US2] (test-engineer) Completar `tests/test_estoque_permissoes.py` com a rota
  `entradas` para todos os papéis da matriz; e `tests/test_contas_home_papeis.py` com o atalho
  "Consultar entradas" visível para funcionário do almoxarifado e auditor, ausente para os demais

### Implementation for User Story 2

- [x] T022 [US2] Implementar em `estoque/views.py` e `estoque/urls.py` a `EntradasView`
  (`ConsultaEntradasMixin`, rota `entradas`): `Paginator` de 50,
  `select_related("registrada_por", "emitente")`, `annotate(total_itens=Count("itens"))`, parcial
  de paginação de `catalogo/_paginacao.html`. Aplica: `PERM-STOCK-HISTORY-VIEW` (recorte de
  FR-021)
- [x] T023 [US2] (frontend-implementer) Criar `estoque/templates/estoque/entradas.html` com Page
  Header, Table (linha clicável com `<a>` real para o detalhe; situação em Badge com texto), Empty
  State e Pagination de `DESIGN.md`; acrescentar ao detalhe o retorno contextual para a lista, a
  situação em Badge e a seção do estorno quando houver (autor, momento, justificativa — US2
  cenário 2)
- [x] T024 [US2] Em `contas/views.py`, acrescentar `pode_consultar_entradas`
  (`FUNCIONARIO_ALMOXARIFADO` ou `AUDITOR`, do mesmo `set`); em
  `contas/templates/contas/home.html`, a linha "Consultar entradas" com link para
  `estoque:entradas`. O item `HIS` continua em `CAPACIDADES_PLANEJADAS`

**Checkpoint**: US1 e US2 funcionam de forma independente.

---

## Phase 5: User Story 3 - Corrigir uma entrada registrada com erro (Priority: P3)

**Goal**: o chefe do almoxarifado estorna uma entrada inteira, com justificativa; os saldos voltam,
a entrada permanece registrada como estornada, e o estorno é bloqueado se deixar saldo negativo.

**Independent Test**: registrar uma entrada, estorná-la como chefe do almoxarifado e verificar os
saldos anteriores restaurados, a situação "Estornada", o estorno com autor, momento e
justificativa, e uma movimentação `ESTORNO_ENTRADA` por item. O funcionário do almoxarifado
recebe 403.

### Tests for User Story 3 ⚠️ (escrever primeiro; devem falhar)

- [x] T025 [P] [US3] (test-engineer) Escrever `tests/test_estoque_estorno.py` sobre
  `estornar_entrada`: US3 cenários 1 a 4; estorno sempre total, cada item na quantidade integral
  (`INV-ENT-001`, FR-023); `EstornoBloqueadoPorSaldo` lista os itens que o impedem, sem efeito
  (FR-026); `EntradaJaEstornada` na segunda tentativa; `JustificativaAusente` para vazio e só
  espaços; `justificativa` gravada aparada; uma `MovimentacaoEstoque` `ESTORNO_ENTRADA` por item
  com `variacao` negativa, saldos, autor e momento; fatos da entrada original inalterados
  (FR-028); referência liberada para nova entrada depois do estorno; conservação SC-001 depois de
  uma sequência mista de entradas e estornos
- [x] T026 [P] [US3] (test-engineer) Acrescentar a `tests/test_estoque_atomicidade.py` a falha
  injetada no meio do estorno (depois da primeira redução de saldo) → nada gravado, entrada não
  estornada; e a `tests/test_estoque_concorrencia.py`: dois estornos simultâneos da mesma entrada →
  um efetivado, o outro `EntradaJaEstornada` (FR-027, SC-009); estorno concorrente com redução
  direta de saldo sob `select_for_update` do mesmo material → nunca saldo negativo
- [x] T027 [P] [US3] (test-engineer) Escrever `tests/test_estoque_views_estorno.py`: GET mostra por
  item o saldo atual e o resultante, com os itens que ficariam negativos já marcados; POST sem
  justificativa → erro no campo; POST válido → 302 para o detalhe com "Entrada estornada."; reenvio
  → "Esta entrada já foi estornada."; bloqueio por saldo → itens marcados e nada gravado; o detalhe
  mostra a ação "Estornar entrada" só para o chefe do almoxarifado e só em entrada não estornada; e
  completar `tests/test_estoque_permissoes.py` com `entrada_estorno` (GET e POST) para todos os
  papéis da matriz, incluindo o funcionário do almoxarifado negado e sem gravação (US3 cenário 5)

### Implementation for User Story 3

- [x] T028 [US3] Implementar em `estoque/entradas.py` as exceções `EntradaJaEstornada`,
  `JustificativaAusente` e `EstornoBloqueadoPorSaldo(itens)` e
  `estornar_entrada(entrada_id, justificativa, autor)`, numa única `transaction.atomic()`:
  `Entrada` `select_for_update()` → já estornada → `EntradaJaEstornada`; justificativa vazia após
  `strip()` → `JustificativaAusente`; materiais dos itens `select_for_update().order_by("pk")`;
  algum saldo menor que a quantidade → `EstornoBloqueadoPorSaldo`; `INSERT` de `EstornoEntrada`,
  `Entrada.estornada = True` (`save(update_fields=["estornada"])`), redução de cada saldo e uma
  `MovimentacaoEstoque` `ESTORNO_ENTRADA` por item com o mesmo momento. Log conforme research R14,
  sem a justificativa. Aplica: `PERM-STOCK-ENTRY-REVERSE` (regras de total, justificativa e
  bloqueio). Preserva: `INV-ENT-001`, `INV-STOCK-001`, `INV-STOCK-004`, `INV-MOV-001`,
  `INV-MOV-002`
- [x] T029 [US3] Implementar `EstornoEntradaForm` (`justificativa`, `Textarea`) em
  `estoque/forms.py` e `EntradaEstornoView` em `estoque/views.py` e `estoque/urls.py`
  (`ExigePapelMixin`, `papel_exigido = Papel.CHEFE_ALMOXARIFADO`, rota `entrada_estorno`): GET
  com saldo atual e resultante por item e itens que ficariam negativos; POST chamando
  `estornar_entrada` com `request.user` e tratando cada exceção conforme a tabela "Estorno" de
  `contracts/rotas-e-autorizacao.md`. No contexto do detalhe, `pode_estornar` (chefe do
  almoxarifado e entrada não estornada). Aplica: `PERM-STOCK-ENTRY-REVERSE`
- [x] T030 [US3] (frontend-implementer) Criar `estoque/templates/estoque/entrada_estorno.html`
  (retorno contextual para o detalhe; Page Header; Table de itens com saldo atual, quantidade a
  estornar e saldo resultante; `.table-row-error` com o motivo na linha para item que ficaria
  negativo; campo de justificativa; barra de Confirmação persistente com o botão **Destrutivo**
  "Estornar entrada: N itens", estado "Estornando…", e "Cancelar"; Alert quando bloqueado). No
  detalhe, a ação "Estornar entrada" quando `pode_estornar` (a seção do estorno já vem de T023)

**Checkpoint**: todas as stories funcionais.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T031 [P] (test-engineer) Escrever `tests/test_estoque_sem_alteracao.py` (SC-008, FR-018):
  nenhum modelo de `estoque` registrado no admin; as rotas de `estoque` só aceitam os métodos de
  `contracts/rotas-e-autorizacao.md`; nenhuma rota altera ou exclui entrada, item, estorno ou
  movimentação
- [x] T032 (coordenador) Rodar `make verify` e o roteiro de `quickstart.md` (§1 a §5), cronometrando
  SC-007
- [x] T033 (coordenador) Acionar o `code-reviewer` com o escopo da feature, `spec.md`, `plan.md`,
  as matrizes canônicas e o "Não inclui" da linha ENT do roadmap; tratar P0/P1 pelo fluxo de
  findings
- [x] T034 (coordenador) Gate visual: `impeccable critique` nas telas de `estoque` (composição,
  resumo, detalhe, lista, estorno) e na Home, depois do `code-reviewer`; encaminhar ao
  `frontend-implementer` só os findings aprovados
- [x] T035 (coordenador) Atualizar `DESIGN.md` e `.impeccable/design.json` por `impeccable
  document` (modo scan) com os padrões novos: composição com tabela de itens editável na mesma folha
  e primeiro uso do botão Destrutivo; conferir contra `static/css/components.css`,
  `estoque/static/estoque/css/` e os templates
- [ ] T036 (coordenador) `/speckit-converge`; depois do merge em `main`, atualizar o status de
  `ENT` no `ROADMAP.md` para concluída e registrar que a dependência "ao menos uma operação de
  estoque entregue" de `HIS` foi satisfeita

---

## Dependencies & Execution Order

- Setup (T001–T003) → Foundational (T004–T007) → US1 (T008–T019) → US2 (T020–T024) e US3
  (T025–T030) → Polish (T031–T036).
- Dentro de cada story: testes → domínio (`quantidade.py`, `entradas.py`) → forms/views →
  templates → Home.
- US2 depende da Foundational e da US1 só por dados: as entradas dos testes vêm de
  `registrar_entrada`, e o detalhe da US1 é estendido com o retorno contextual.
- US3 depende da US1 (`entradas.py`, detalhe) e pode andar em paralelo com a US2, exceto em
  `estoque/views.py`, `estoque/urls.py` e `entrada_detalhe.html`, onde as tasks são sequenciais.
- T017 depende de T015 e T016; T018 depende de T017 (contrato de contexto); T028 depende de T015.

## Parallel Opportunities

- T002 e T003; T007 depois de T005–T006.
- US1: T008–T013 juntos; T014 em paralelo com a escrita dos testes.
- US2: T020 e T021 juntos. US3: T025–T027 juntos.
- US2 (T020–T024) em paralelo com o domínio da US3 (T025, T026, T028), serializando só os arquivos
  compartilhados de views, urls e detalhe.
- T031 em paralelo com T032.

## Parallel Example: User Story 1

```text
Task: "(test-engineer) tests/test_estoque_quantidade.py"
Task: "(test-engineer) tests/test_estoque_registro.py"
Task: "(test-engineer) tests/test_estoque_atomicidade.py"
Task: "(test-engineer) tests/test_estoque_concorrencia.py"
Task: "(test-engineer) tests/test_estoque_views_entrada.py"
Task: "(test-engineer) tests/test_estoque_permissoes.py (registro e detalhe)"
Task: "estoque/quantidade.py"
```

## Implementation Strategy

1. **MVP**: Setup + Foundational + US1. O almoxarifado registra entradas com efeito atômico e
   rastreável no saldo.
2. US2 (consulta), depois US3 (estorno).
3. Polish: review, gate visual, `DESIGN.md`, converge.
4. Pipeline de estoque em cada etapa crítica: `test-engineer` → `task-implementer` →
   `frontend-implementer` → `code-reviewer`. Não considerar concluída uma etapa em que só o happy
   path passa.

---

## Phase 7: Convergence

- [x] T037 Registrar em `specs/003-entrada-materiais/contracts/rotas-e-autorizacao.md` (tabelas "Confirmação" e "Estorno") os refinamentos implementados após o review: mensagem "Este formulário já foi usado para registrar a entrada #<pk>; inicie uma nova entrada." quando a mesma chave volta com conteúdo diferente; resposta `HX-Redirect` ao detalhe no "Revisar" via HTMX de entrada já registrada; GET e POST do estorno de entrada já estornada redirecionam ao detalhe com "Esta entrada já foi estornada." per FR-013, FR-027 (unrequested)
- [ ] T038 (coordenador, com o dono do produto) Cronometrar no ambiente de desenvolvimento o registro de uma entrada de um material, do clique na Home à confirmação, e confirmar menos de um minuto per SC-007 (partial)
