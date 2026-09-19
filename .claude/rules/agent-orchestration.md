# Orquestração de subagents — WMS-Almoxarifado

Esta regra orienta principalmente o **Claude da sessão principal**, que é o
coordenador do trabalho neste projeto.

Os subagents especializados não devem tentar criar uma segunda camada de
orquestração. Cada um continua respeitando seu próprio system prompt e suas
restrições de ferramentas — este arquivo não os substitui nem os reescreve.

## Princípio geral

O Claude principal coordena o trabalho.

Para alterações significativas no repositório, prefira delegar trabalho
especializado aos subagents existentes em vez de executar todas as etapas
diretamente no contexto principal.

Os agentes disponíveis são:

- `wms-explorer`: exploração semântica read-only e análise de impacto;
- `task-implementer`: implementação de tarefas claramente definidas
  (backend e frontend pequeno ou inseparável da tarefa);
- `frontend-implementer`: implementação de trabalho frontend significativo,
  usando obrigatoriamente a skill `frontend-design` dentro da fundação
  visual já estabelecida em `DESIGN.md`;
- `code-reviewer`: revisão independente read-only;
- `debugger`: diagnóstico e correção de bugs;
- `test-engineer`: projeto, criação e revisão de testes.

O projeto também possui os agentes auxiliares do workflow Impeccable
(`impeccable-asset-producer`, `impeccable-documenter`,
`impeccable-finish-reviewer`, `impeccable-manual-edit-applier`), responsáveis
por estabelecer, documentar e auditar a fundação do design system — não por
implementar telas do dia a dia. Ver seção "Trabalho frontend".

Não invoque agentes apenas para seguir um ritual. Mudanças triviais,
consultas simples e tarefas sem benefício claro de especialização não
precisam atravessar todo o pipeline.

## Responsabilidade do Claude principal

O Claude principal deve:

1. entender a intenção do usuário;
2. identificar o workflow apropriado;
3. fornecer a cada subagent contexto suficiente e objetivo;
4. receber e interpretar o resultado;
5. decidir o próximo passo;
6. manter o usuário informado sobre findings ou impedimentos relevantes;
7. impedir ciclos desnecessários entre agentes.

O Claude principal é responsável pela orquestração. Não conceda essa
responsabilidade implicitamente aos subagents.

## Documentação canônica de domínio

`docs/domain/permissions-matrix.md` e `docs/domain/invariants-matrix.md` são fontes canônicas
válidas em todo o repositório — a primeira responde quem pode agir, a segunda o que deve permanecer
verdadeiro. Não é necessário invocar um agente só para lê-las.

Quando uma feature envolver autorização, papéis, escopo, visibilidade de objetos ou administração de
usuários, consulte `docs/domain/permissions-matrix.md` antes de especificar, desenhar testes,
implementar ou revisar.

Quando uma feature alterar estado de domínio, estoque, catálogo, movimentações, relações
organizacionais, ou introduzir operações críticas, consulte `docs/domain/invariants-matrix.md` pelo
mesmo motivo. Features críticas de estoque que também envolvam autorização devem consultar ambas.

Relatórios em `docs/domain/reconciliation/` e `docs/domain-legacy/reconciliation/` são
histórico/não normativo — nunca os trate como as matrizes canônicas.

Isso se reflete no trabalho de cada subagent, sem alterar seus prompts individuais:

- `wms-explorer`: ao analisar impacto relevante, identifica as capabilities (`PERM-*`) e
  invariantes (`INV-*`) aplicáveis.
- `test-engineer`: usa as invariantes aplicáveis como fonte de cenários de teste, priorizando as de
  severidade CRÍTICA.
- `task-implementer`: preserva explicitamente as invariantes e permissões aplicáveis à task.
- `code-reviewer`: verifica se o diff quebra alguma `INV-*`, amplia uma `PERM-*`, ignora escopo, ou
  introduz comportamento incompatível com os artefatos canônicos.
- `debugger`: quando o bug representar quebra de invariante ou autorização, referencia o ID
  correspondente na análise quando isso melhorar a rastreabilidade.
- `frontend-implementer`: quando a superfície implementada expuser dado ou ação sensível a
  papel/setor, consulta `permissions-matrix.md` para garantir que a interface reflita a mesma
  autorização já garantida no backend — nunca usa visibilidade de elemento como autorização.

Alterar uma permissão ou invariante canônica segue sempre o mesmo fluxo, nunca o caminho inverso
(mudar comportamento e só depois atualizar a documentação):

```text
necessidade nova → decisão explícita de domínio → atualizar a matriz canônica correspondente
→ atualizar specs afetadas → plan/tasks → implementação/review
```

## Feature nova

Quando existir uma feature definida através do Spec Kit, use normalmente o
ciclo completo quando aplicável:

```text
specify → clarify → plan → checklist → tasks → analyze
→ implementação
→ review
→ correções quando necessárias
→ converge
```

`checklist` pode ser omitido quando não agregar valor à feature. Não execute
`converge` antes da implementação.

Durante `clarify`, se uma resposta proposta contradisser uma `INV-*`, exigir uma capability ainda
inexistente, ampliar o escopo de uma `PERM-*` ou enfraquecer uma regra canônica, explicite o
conflito em vez de deixar `clarify` sobrescrever a matriz silenciosamente. Se o dono do produto
decidir pela mudança, siga o fluxo de alteração descrito acima antes de codificar a decisão na spec.

Em `analyze`, verifique também que a spec não contradiz `permissions-matrix.md`/`invariants-matrix.md`
e que `plan.md`/`tasks.md` oferecem meios adequados para preservar as invariantes e permissões
aplicáveis. Em `converge`, verifique que implementação, testes e specs continuam consistentes com as
matrizes canônicas e que nenhuma decisão de domínio nova ficou registrada só no código.

Depois que `spec.md`, `plan.md` e `tasks.md` estiverem suficientemente
definidos:

### Exploração

Use `wms-explorer` antes da implementação quando:

- a feature modifica código existente relevante;
- o fluxo atual não está claro;
- há dependências cross-file;
- existem regras de negócio compartilhadas;
- há risco significativo de regressão;
- a alteração toca estoque, permissões, transações ou contratos existentes.

Não invoque `wms-explorer` para código novo isolado ou mudança trivial
quando o contexto já estiver claro.

### Test design

Use `test-engineer` antes da implementação quando a feature envolver risco
relevante, especialmente:

- regras de negócio;
- estoque;
- movimentações;
- permissões;
- transações;
- concorrência;
- rollback;
- idempotência;
- comportamento com casos de erro significativos.

O objetivo neste momento é identificar cenários críticos, não criar testes
por quantidade. Para CRUD simples ou alteração trivial, essa etapa pode ser
omitida.

### Implementação

A implementação de código de produção deve ser atribuída ao
`task-implementer` quando houver uma tarefa concreta e bem definida.

Quando a tarefa envolver trabalho frontend significativo (tela nova,
componente novo, redesenho aprovado de superfície existente, revisão visual
relevante), atribua essa parte ao `frontend-implementer` em vez do
`task-implementer`. Se a tarefa combinar backend e frontend significativo,
separe o trabalho entre os dois agentes; não peça ao `task-implementer` para
absorver frontend significativo só por conveniência, nem peça ao
`frontend-implementer` para implementar regra de negócio, autorização ou
mudança de estoque substancial.

Forneça ao implementador (`task-implementer` ou `frontend-implementer`):

- objetivo;
- task correspondente;
- artefatos Spec Kit relevantes (e `DESIGN.md` quando o trabalho for
  frontend);
- resultado da exploração, se houver;
- cenários críticos identificados pelo `test-engineer`, se houver;
- limites explícitos de escopo.

Não peça ao `task-implementer` nem ao `frontend-implementer` para redefinir
requisitos ou arquitetura.

### Review

Após implementação significativa, invoque `code-reviewer`.

O reviewer deve receber:

- o escopo da alteração;
- a specification/task relevante;
- informação suficiente para identificar o diff que deve ser revisado.

Não peça ao implementador para revisar o próprio trabalho como substituto
do `code-reviewer`.

## Converge após review

Quando a feature estiver sendo desenvolvida através do Spec Kit, depois que:

- implementação estiver concluída;
- verificações relevantes tiverem passado;
- findings bloqueantes do `code-reviewer` tiverem sido resolvidos;

execute `/speckit.converge`.

Se `converge` identificar trabalho restante e adicionar ou revelar tasks
pendentes:

1. encaminhe as tarefas apropriadas ao `task-implementer`;
2. execute review novamente quando a mudança for significativa;
3. execute `converge` novamente.

Repita somente enquanto houver trabalho concreto e bem definido. Não crie
loop infinito.

Se houver conflito de requisitos, arquitetura ou interpretação que impeça
convergência, pare e apresente o conflito ao usuário.

## Findings do code-reviewer

Ao receber findings:

### P0 ou P1

Devem ser tratados antes de considerar a tarefa concluída.

Encaminhe:

- bug/correção localizada → `debugger`, quando a natureza for diagnóstico de
  comportamento incorreto;
- problema de implementação da tarefa → `task-implementer`, ou
  `frontend-implementer` quando o finding for especificamente sobre a parte
  frontend significativa implementada por ele.

Depois da correção, execute novamente `code-reviewer` sobre o novo estado.

### P2

Normalmente deve ser tratado quando relacionado diretamente ao escopo
atual. Avalie a relevância antes de delegar a correção.

### P3

Não entre automaticamente em ciclo de correção. Avalie se vale corrigir
agora ou registrar para depois.

Não transforme findings pequenos em expansão desnecessária de escopo.

## Ciclo de review

Evite loops infinitos.

Fluxo normal:

`implementação → code-reviewer → correção → code-reviewer`

Se após duas rodadas de correção ainda houver desacordo relevante,
inconsistência de requisitos ou problema arquitetural não resolvido, pare o
ciclo automático e apresente a situação ao usuário.

Não continue modificando código indefinidamente para satisfazer opiniões
não fundamentadas.

## Bugs

Para bug claramente descrito:

`debugger → code-reviewer`

O `debugger` já é responsável por:

- reproduzir;
- investigar;
- encontrar causa raiz;
- corrigir minimamente;
- adicionar teste de regressão quando viável.

Não invoque `wms-explorer` automaticamente antes de todo bug. Use
`wms-explorer` antes do debugger somente quando o problema exigir
compreensão arquitetural ampla que não esteja disponível.

Após a correção, use `code-reviewer` quando a mudança for significativa ou
tocar regras críticas.

## Testes

Use `test-engineer` isoladamente quando a tarefa for:

- analisar qualidade da suíte;
- desenhar cenários de teste;
- encontrar lacunas de cobertura comportamental;
- fortalecer testes existentes;
- criar testes sem alterar produção.

Se o `test-engineer` encontrar bug de produção, o Claude principal deve
encaminhar a correção ao `debugger`.

Se encontrar funcionalidade ausente ou implementação necessária, encaminhe
ao `task-implementer`.

## Refactors

Para refactor significativo:

`wms-explorer → task-implementer → code-reviewer`

A exploração deve identificar:

- símbolos afetados;
- consumidores;
- contratos;
- testes;
- impacto cross-file.

O implementador deve receber limites claros. O reviewer deve verificar
regressões e consumidores esquecidos.

Para renomeação ou refactor trivial e claramente localizado, não é
obrigatório usar todo o pipeline.

## Alterações de estoque

Para alterações significativas em entrada, saída, transferência, ajuste,
inventário, reserva, saldo ou movimentações, prefira o pipeline completo:

`wms-explorer → test-engineer → task-implementer → code-reviewer`

Dê atenção especial a:

- concorrência;
- atomicidade;
- locking;
- idempotência;
- rollback;
- autorização;
- preservação histórica;
- saldo consistente.

Não considere uma alteração crítica de estoque concluída apenas porque o
happy path passa.

Consulte `docs/domain/invariants-matrix.md` antes de especificar, desenhar testes, implementar ou
revisar qualquer uma dessas alterações; consulte também `docs/domain/permissions-matrix.md` quando
a alteração envolver autorização (ver seção seguinte).

## Segurança e permissões

Mudanças significativas envolvendo autorização, autenticação ou isolamento
de dados devem normalmente passar por:

`test-engineer → task-implementer → code-reviewer`

Quando código existente ou dependências não estiverem claros, adicione
`wms-explorer` antes.

Quando uma feature envolver autorização, papéis, escopo por setor, visibilidade de objetos,
administração de usuários ou qualquer operação protegida, o Claude principal DEVE consultar
`docs/domain/permissions-matrix.md` antes de especificar comportamento definitivo, solicitar test
design, implementar ou revisar. Não é necessário invocar um agente só para ler a matriz.

## Trabalho frontend

Divisão de responsabilidade:

- `task-implementer`: produção backend e mudanças frontend pequenas ou
  inseparáveis da tarefa (ver seção "Frontend" do seu próprio prompt).
- `frontend-implementer`: implementação frontend significativa — tela nova,
  componente novo, redesenho aprovado de superfície existente, revisão
  visual relevante — usando obrigatoriamente a skill `frontend-design`
  dentro da fundação já estabelecida em `DESIGN.md`.
- `wms-explorer`: exploração prévia quando o fluxo, impacto ou os
  componentes/consumidores existentes não estiverem claros.
- `test-engineer`: estratégia ou implementação de testes especializados
  (template, HTMX, comportamento) quando o risco justificar.
- `code-reviewer`: revisão funcional independente após mudança frontend
  significativa. Este agente não faz auditoria visual completa nem
  substitui o workflow Impeccable (ver seu próprio prompt, seção
  "Frontend").
- agentes `impeccable-*`: auxiliares do workflow Impeccable — estabelecem,
  documentam e auditam a fundação do design system (`DESIGN.md` e seu
  sidecar), produzem assets e revisam builds dirigidos por comp. Não são
  substitutos do implementador de produção, e o `frontend-implementer` não
  os invoca (não tem acesso à ferramenta `Agent`).

Um fluxo frontend significativo pode ser:

```text
wms-explorer, quando necessário
→ frontend-implementer
→ code-reviewer (revisão funcional)
→ revisão visual (gate obrigatório — ver abaixo)
→ correções pelo frontend-implementer, quando necessárias
→ nova revisão (funcional e/ou visual) quando material
```

Não imponha esse pipeline para alterações triviais — essas continuam com
`task-implementer` (ver seção "Tarefas triviais").

### Gate de revisão visual

A Constitution exige que mudanças significativas de frontend passem por
revisão visual quanto à aderência ao `DESIGN.md`, reutilização de
componentes, consistência visual e eficiência operacional. O
`code-reviewer` não cobre esse gate: ele faz revisão funcional e declara
explicitamente que não realiza auditoria estética completa (ver seu
próprio prompt, seção "Frontend"). O Claude principal não deve considerar
uma mudança frontend significativa concluída apenas porque o
`code-reviewer` aprovou.

Após a revisão funcional, coordene uma revisão visual proporcional ao
trabalho:

- use `impeccable critique <target>` como gate visual obrigatório para a
  mudança implementada — é uma crítica de design, não uma checagem técnica;
- `impeccable audit` é complementar, não substitui a crítica: cobre
  acessibilidade, performance, responsividade e integridade técnica;
- quando existir um build Impeccable completo com contrato de direção e
  capturas, use `impeccable-finish-reviewer` em vez de `critique`;
- `impeccable polish` não é parte do gate — ele modifica a implementação
  diretamente. Use-o apenas como alternativa explícita de correção quando
  o Claude principal optar por corrigir dessa forma em vez de encaminhar
  os findings ao `frontend-implementer`.

Quando o `critique` reportar 3 ou mais Priority Issues, seu próprio
contrato para na entrega do relatório e exige perguntas direcionadas ao
usuário antes de qualquer correção. Nesse caso, o Claude principal aguarda
a seleção do usuário e encaminha ao `frontend-implementer` somente os
findings aprovados — não repasse o relatório inteiro automaticamente. Com
menos de 3 Priority Issues, quando o próprio `critique` permitir seguir
sem perguntas, os findings podem ser encaminhados diretamente ao
`frontend-implementer`.

Se, durante um fluxo frontend, ficar evidente que a fundação do design
system precisa ser criada, revista ou passar por auditoria estrutural (não
apenas uma tela específica), direcione esse trabalho ao workflow `impeccable`
em vez de pedir ao `frontend-implementer` para assumi-lo — ele não tem esse
papel.

### Promoção do DESIGN.md seed

`DESIGN.md` nasce como seed (fundação acordada com o usuário, sem código,
comp ou geração de imagem) e declara explicitamente que deve ser
re-executado em modo scan assim que existirem templates, CSS e componentes
reais implementados, para extrair tokens e o sidecar
`.impeccable/design.json` a partir do código de fato construído. Essa
transição não deve depender de alguém perceber a necessidade
estruturalmente — trate-a como obrigatória:

- após a primeira implementação visual real de uma feature (quando
  templates, CSS e componentes deixam de ser hipotéticos), execute
  `impeccable document` em modo scan — não `impeccable-documenter`, que
  pressupõe um build Impeccable completo (contrato de direção e artefatos
  próprios desse workflow) que uma implementação comum do
  `frontend-implementer` não produz; reserve `impeccable-documenter` para
  quando esse contrato existir;
- em implementações frontend posteriores, documente apenas mudanças
  duráveis do sistema (novo token, novo padrão reutilizável), não cada
  tela individualmente.

Se o `frontend-implementer` reportar necessidade de mudança backend
substancial (regra de negócio, autorização, estoque, migration) que exceda
um ajuste local, encaminhe-a ao `task-implementer` como uma tarefa própria,
em vez de pedir ao `frontend-implementer` para implementá-la.

## Tarefas triviais

Não use pipelines complexos para:

- correção simples de documentação;
- typo;
- alteração claramente localizada e de baixo risco;
- consulta sobre código sem modificação;
- configuração pequena sem impacto no domínio.

Use o menor conjunto de agentes que agregue valor real.

## Delegação explícita

Quando uma etapa for importante para o workflow, invoque explicitamente o
subagent apropriado em vez de confiar somente na delegação automática.

Use delegação automática para casos óbvios, mas não dependa dela para gates
importantes como revisão de uma implementação crítica.

## Informação passada aos agentes

Não envie apenas "revise isso" ou "implemente a feature".

Forneça contexto suficiente para o agente atuar de maneira focada. Inclua
quando aplicável:

- objetivo;
- comportamento esperado;
- escopo;
- arquivos/símbolos relevantes já conhecidos;
- referência à spec/task;
- resultados relevantes de agentes anteriores;
- restrições importantes.

Não despeje toda a conversa ou todo o repositório no prompt do agente
quando um resumo focado for suficiente.

## Autoridade dos artefatos

Respeite a seguinte separação:

- Constitution → princípios obrigatórios;
- `PRODUCT.md` → verdade de produto;
- `docs/domain/permissions-matrix.md` e `docs/domain/invariants-matrix.md` → regras transversais
  canônicas (quem pode agir; o que deve permanecer verdadeiro), válidas em todo o repositório;
- `spec.md` → comportamento/requisitos da feature;
- `plan.md` → solução técnica planejada — decide **como** preservar uma invariante ou capability
  (ex.: `INV-STOCK-004` pode levar a transação, lock ou constraint quando tecnicamente apropriado),
  nunca o contrário;
- `tasks.md` → unidades de implementação;
- `DESIGN.md` → design system, quando existir;
- código existente → realidade atual da implementação;
- relatórios dos subagents e relatórios em `docs/domain/reconciliation/` /
  `docs/domain-legacy/reconciliation/` → evidência, análise e histórico, não novas fontes
  normativas.

Se houver conflito material entre essas fontes, não escolha arbitrariamente.
Apresente ou resolva o conflito antes de continuar.

Relatórios, findings, hipóteses e recomendações produzidos pelos subagents
são evidências e análises. Eles não alteram automaticamente:

- Constitution;
- `docs/domain/permissions-matrix.md`;
- `docs/domain/invariants-matrix.md`;
- `spec.md`;
- `plan.md`;
- `tasks.md`;
- `DESIGN.md`.

Se uma conclusão de um agente implicar mudança em um desses artefatos, o
Claude principal deve tratar a alteração explicitamente no fluxo apropriado
antes de implementar uma solução que dependa dela.

Não permita que uma recomendação de subagent sobrescreva silenciosamente uma
decisão normativa existente.

## Conclusão de uma tarefa

Não considere uma implementação significativa concluída apenas porque o
`task-implementer` terminou.

Quando o workflow exigir review, a tarefa só está pronta depois que:

- verificações relevantes passaram;
- findings bloqueantes do `code-reviewer` foram tratados;
- limitações conhecidas foram informadas;
- comportamento implementado continua dentro do escopo.

Não faça commits ou push automaticamente salvo quando o usuário pedir
explicitamente.
