# Orquestração do Codex — WMS-Almoxarifado

Este arquivo orienta o agente principal do Codex e os subagents deste repositório.
O agente principal coordena o trabalho, consolida resultados e mantém a responsabilidade
pela resposta final. Subagents executam somente o papel recebido e não criam uma segunda
camada de orquestração.

## Espelho normativo

Este arquivo é o espelho, para o Codex, da orquestração definida em `CLAUDE.md` e
`.claude/rules/agent-orchestration.md`. As duas versões descrevem a mesma política; diferem
apenas no que é específico de ferramenta — nomes de agente com `_`, `sandbox_mode` e ausência
do Serena MCP.

Qualquer alteração de regra de domínio, gate obrigatório, escopo de agente ou fonte de
autoridade DEVE ser aplicada nos dois lados no mesmo commit. Se os dois divergirem, nenhum dos
dois prevalece automaticamente: identifique a divergência e obtenha uma decisão antes de agir
com base nela. Nenhum dos dois sobrepõe a Constitution, `PRODUCT.md` ou as matrizes canônicas.

## Princípio geral

Use subagents quando a especialização, o isolamento de contexto ou o paralelismo trouxerem
benefício concreto. Não invoque agentes apenas para cumprir um ritual. Consultas simples,
documentação pequena e mudanças localizadas de baixo risco podem ser executadas diretamente.

Paralelize preferencialmente trabalho independente e read-only, como exploração, desenho de
testes e análise. Serialize etapas dependentes e agentes que escrevem no working tree. Nunca
coloque dois agentes editando os mesmos arquivos simultaneamente.

O agente principal deve:

1. entender a intenção do usuário e delimitar o escopo — quando o pedido envolver uma feature,
   situando-o no `ROADMAP.md`;
2. selecionar o menor workflow suficiente;
3. fornecer objetivo, contexto, artefatos e limites claros a cada subagent;
4. aguardar e interpretar os resultados;
5. decidir o próximo passo sem delegar a responsabilidade de coordenação;
6. manter o usuário informado sobre achados e impedimentos materiais;
7. impedir ciclos de review e correção sem progresso concreto.

## Fontes de autoridade

Respeite, de forma combinada, as seguintes fontes:

1. `.specify/memory/constitution.md` — princípios obrigatórios de engenharia;
2. `PRODUCT.md` — verdade do produto;
3. `docs/domain/permissions-matrix.md` — fonte canônica de papéis, capabilities,
   escopos e condições de autorização;
4. `docs/domain/invariants-matrix.md` — fonte canônica das propriedades transversais
   que devem permanecer verdadeiras;
5. `ROADMAP.md` — decomposição funcional: quais capacidades merecem spec própria, seu
   recorte, dependências, ordem recomendada e status;
6. `spec.md` — comportamento e requisitos da feature;
7. `plan.md` — solução técnica planejada;
8. `tasks.md` — unidades de implementação;
9. `DESIGN.md` — design system e direção visual;
10. código existente — realidade atual da implementação.

Essa ordem não é uma regra simples de "fonte de cima sempre sobrescreve a de baixo". Uma
feature respeita os artefatos canônicos transversais: uma spec não contorna silenciosamente
uma permissão ou invariante canônica, nem move silenciosamente a fronteira que o roadmap
definiu para a feature.

Relatórios em `docs/domain/reconciliation/` e `docs/domain-legacy/reconciliation/` são
históricos e não normativos: explicam origem, alternativas consideradas, decisões descartadas
e pendências, mas nunca substituem as matrizes canônicas. Quando houver divergência, as
matrizes representam o estado vigente — não use um relatório de reconciliação para reviver
algo lá descartado, pendente ou substituído.

Relatórios de subagents são evidência e análise; não alteram automaticamente nenhuma fonte
normativa.

Se houver conflito material, não escolha silenciosamente uma interpretação. Identifique o
conflito e obtenha uma decisão antes de implementar algo que dependa dela.

Uma mudança em permissão ou invariante canônica segue este fluxo:

```text
necessidade nova → decisão explícita de domínio → atualizar a matriz canônica
→ atualizar specs afetadas → plan/tasks → implementação → review
```

## Roadmap funcional

`ROADMAP.md` é a fonte de verdade para a **decomposição funcional** do produto: quais
capacidades merecem spec própria, o que cada uma inclui e não inclui, suas dependências
obrigatórias (`O`) e recomendadas (`R`), a ordem recomendada de evolução e o status de cada
capacidade.

A autoridade do roadmap é delimitada:

- decide **recorte, fronteiras, dependências e ordem** entre features;
- não define requisitos nem comportamento dentro de uma feature — isso é de `spec.md`;
- não define regra de domínio — isso é das matrizes canônicas, das quais o roadmap apenas
  cita IDs como evidência;
- não define solução técnica — isso é de `plan.md`;
- não é cronograma, e a ordem recomendada não é bloqueio funcional: só as dependências
  obrigatórias bloqueiam implementação e aceite;
- os "Pontos ainda indefinidos" são pendências a esclarecer, não regras vigentes.

Os IDs `ORG`, `ENT`, `REQ` etc. são rótulos do mapa, não números de spec. A numeração é
atribuída sequencialmente pelo `speckit-specify` ao criar cada spec, independentemente da ordem
do roadmap; `001` e `002` permanecem com seus números.

O roadmap orienta planejamento de features. Bugs, refactors, ajustes pontuais e tarefas triviais
não precisam consultá-lo, salvo quando ameaçarem mover a fronteira entre capacidades.

Alterar recorte, fronteira ou dependência, ou incluir uma capacidade que não está no mapa, segue
o mesmo princípio das matrizes — decisão explícita antes da spec, nunca o caminho inverso. A
decisão é do usuário, como dono do produto: nem o agente principal nem um subagent alteram o
recorte por conta própria; eles identificam a necessidade e a apresentam.

```text
necessidade nova → decisão explícita de recorte → atualizar ROADMAP.md
→ specify/atualizar specs afetadas → plan/tasks → implementação → review
```

Se a mudança também alterar uma permissão ou invariante, o fluxo das matrizes canônicas vem
primeiro. Uma spec não amplia silenciosamente o próprio recorte para absorver capacidade que o
roadmap atribui a outra feature.

Atualizar a coluna de status não exige decisão de recorte; é acompanhamento e cabe ao agente
principal. Mantenha o status fiel ao estado observável da feature, incluindo a anotação que o
acompanha: atualize-o ao criar a spec, sempre que a anotação deixar de ser verdadeira — por
exemplo, ao gerar `plan.md` e `tasks.md` de uma feature anotada como "sem plano/tarefas" — e
depois do merge em `main`, quando ela passa a concluída. Não marque uma feature como concluída
antes da entrega efetiva.

Isso chega aos subagents pelo prompt de delegação, sem alterar suas definições:

- `wms_explorer`: quando a análise de impacto tocar outra capacidade do mapa, aponta a
  fronteira afetada;
- `code_reviewer`: verifica se o diff implementa algo que o roadmap atribui a outra feature ou
  lista em "Não inclui" da feature em andamento;
- implementadores: tratam "Não inclui" como limite de escopo; se a task exigir atravessá-lo,
  param e reportam ao coordenador.

## Agentes disponíveis

As definições ficam em `.codex/agents/`:

- `wms_explorer`: exploração e análise de impacto read-only;
- `task_implementer`: implementação de tarefas definidas de backend e mudanças frontend
  pequenas ou inseparáveis;
- `frontend_implementer`: frontend significativo em Django Templates, HTMX, CSS e
  JavaScript pontual, dentro de `DESIGN.md`;
- `code_reviewer`: revisão independente e read-only;
- `debugger`: diagnóstico, causa raiz, correção mínima e teste de regressão;
- `test_engineer`: desenho, criação e revisão de testes, sem alterar produção.

Os auxiliares do workflow visual Impeccable — `impeccable_asset_producer`,
`impeccable_documenter`, `impeccable_finish_reviewer` e `impeccable_manual_edit_applier` — não
são definidos aqui: a própria skill os empacota em `.agents/skills/impeccable/agents/`, e essa
é a definição vigente. Não crie uma segunda definição desses nomes em `.codex/agents/`; ela
divergiria silenciosamente a cada atualização da skill. Eles estabelecem, documentam e auditam
a fundação do design system — não implementam telas do dia a dia.

Use os nomes acima ao solicitar explicitamente um papel. Os agentes especializados não
devem delegar para outros agentes; quando precisarem de outro papel, devem devolver ao
coordenador uma solicitação objetiva.

Quando uma etapa for importante para o workflow, invoque explicitamente o agente apropriado.
Use roteamento implícito apenas para casos óbvios: não dependa dele para gates importantes,
como a revisão de uma implementação crítica.

## Contexto do projeto

O sistema é um WMS server-driven baseado principalmente em Python, Django, PostgreSQL,
Django Templates, HTMX, CSS próprio e JavaScript pontual.

Priorize:

- integridade de estoque e consistência transacional;
- autorização no backend e isolamento correto de dados;
- regras de negócio explícitas;
- rastreabilidade e preservação histórica;
- testes de comportamento e invariantes;
- simplicidade arquitetural e manutenção.

Não introduza SPA, framework frontend, biblioteca relevante ou nova camada arquitetural sem
necessidade concreta e decisão compatível com a Constitution.

## Documentação canônica de domínio

Consulte `docs/domain/permissions-matrix.md` antes de especificar, desenhar testes,
implementar ou revisar trabalho que envolva autenticação, autorização, papéis, escopo por
setor, visibilidade de objetos, administração de usuários ou operações protegidas.

Consulte `docs/domain/invariants-matrix.md` antes das mesmas etapas quando o trabalho alterar
estado de domínio, estoque, catálogo, movimentações, relações organizacionais ou operações
críticas. Trabalho crítico de estoque que também envolva autorização consulta ambas.

Quando aplicável, preserve a rastreabilidade pelos IDs `PERM-*` e `INV-*` em specs, tasks,
testes, implementação e review. Não copie a definição inteira das matrizes para outros
artefatos nem redefina seu significado silenciosamente.

Specs relacionadas a operações ou regras transversais referenciam as capabilities e
invariantes aplicáveis por ID numa seção `## Regras canônicas aplicáveis`, com as subseções
`### Permissões` e `### Invariantes` (por exemplo `PERM-REQ-CREATE-SELF` e `INV-STOCK-004`).
Use essa seção só quando houver regra transversal relevante — nunca como seção obrigatória em
toda spec, e nunca copiando o texto completo das matrizes. Tasks de domínio crítico podem
referenciar os IDs que aplicam e preservam (ex.: `Aplica: PERM-STOCK-ENTRY-CREATE` /
`Preserva: INV-STOCK-001, INV-STOCK-004`); isso não é obrigatório para tasks triviais.

Uma spec nova não redefine silenciosamente o significado de uma capability ou invariante
existente. Para alterar uma, registre a decisão e atualize a matriz canônica antes de usar o
novo comportamento na spec.

## Workflow de feature com Spec Kit

Antes de iniciar — ou retomar, como no caso de uma spec já existente em `Draft` — o ciclo do
Spec Kit para uma capacidade, situe o pedido no roadmap:

1. identifique a linha correspondente em `ROADMAP.md`. Se o pedido não corresponder a
   nenhuma, ou atravessar a fronteira entre duas, pare e trate como alteração de recorte
   (seção "Roadmap funcional");
2. verifique as dependências obrigatórias. Algumas são features a entregar; outras são
   condições, como identidades, setores e chefias válidos, que podem ser atendidas sem a
   feature que as administra. A especificação pode antecipar contratos de uma feature
   dependente; a implementação e o aceite de ponta a ponta exigem as dependências
   obrigatórias satisfeitas;
3. não leve à implementação uma capacidade com status "Requer clarificação" enquanto o
   conteúdo mínimo do aceite não estiver definido. Com qualquer status, os "Pontos ainda
   indefinidos" que afetam a capacidade precisam estar resolvidos na spec, pelo `clarify`,
   antes da implementação — o roadmap os lista justamente como decisões exigidas antes da
   spec ou da implementação;
4. passe ao `speckit-specify` uma descrição que nomeie a capacidade e carregue seu recorte — o
   "Inclui", o "Não inclui" e os pontos indefinidos que lhe dizem respeito — em vez de deixar o
   escopo ser inferido só do texto do pedido.

Com a capacidade situada, use as skills existentes em `.agents/skills` e siga normalmente:

```text
ROADMAP.md (situar a capacidade)
→ speckit-specify → speckit-clarify → speckit-plan → speckit-checklist (quando agregar valor)
→ speckit-tasks → speckit-analyze → implementação → review → correções
→ speckit-converge
→ atualizar o status no ROADMAP.md após o merge
```

Não execute `speckit-converge` antes da implementação. Se a clarificação ou análise conflitar
com uma regra canônica, exponha o conflito e siga o fluxo explícito de mudança de domínio.

Em `speckit-clarify`, os "Pontos ainda indefinidos" do roadmap para aquela capacidade são a
pauta natural das perguntas. Não reabra o que o roadmap já decidiu sobre recorte e
granularidade: se uma resposta mover a fronteira da feature, trate como alteração de recorte em
vez de deixar a clarificação redefinir o mapa.

Quando um ponto indefinido for compartilhado entre recortes — como reserva, disponibilidade ou
material inativo —, esclareça-o em conjunto, e não na clarificação de uma feature isolada.
Antes de fixá-lo, verifique o que as specs das outras features afetadas já dizem sobre ele; se
a decisão mudar o que elas pressupõem, apresente o conflito ao usuário em vez de deixar uma
feature decidir pelas demais.

Em `speckit-analyze`, verifique também que a spec não contradiz as matrizes canônicas, que
`plan.md`/`tasks.md` oferecem meios adequados para preservar as invariantes e permissões
aplicáveis, que a spec não ultrapassa o "Não inclui" do roadmap, não absorve capacidade
atribuída a outra feature, declara dependências compatíveis com as do mapa e resolve os
"Pontos ainda indefinidos" que afetam a capacidade.

Em `speckit-converge`, verifique que implementação, testes e specs continuam consistentes com
as matrizes canônicas e que nenhuma decisão de domínio nova ficou registrada só no código. O
converge continua usando `spec.md`, `plan.md` e `tasks.md` como fonte da intenção da feature —
o roadmap não acrescenta requisitos a ele. Se a implementação tiver movido a fronteira da
feature, isso é alteração de recorte a registrar no roadmap, não trabalho a absorver.

Depois que spec, plan e tasks estiverem suficientemente definidos:

- use `wms_explorer` quando o fluxo atual, dependências cross-file, consumidores ou regras
  compartilhadas não estiverem claros;
- use `test_engineer` antes da implementação quando houver risco relevante de negócio,
  estoque, permissão, transação, concorrência, rollback ou idempotência;
- encaminhe backend e trabalho geral bem definido ao `task_implementer`;
- encaminhe frontend significativo ao `frontend_implementer`;
- após implementação significativa, use `code_reviewer` como revisão independente;
- após resolver findings bloqueantes e passar verificações, execute `speckit-converge`.

Se o converge revelar trabalho concreto, implemente-o, revise novamente quando material e
repita o converge. Pare quando houver conflito de requisito/arquitetura ou quando uma nova
rodada não produzir progresso concreto.

## Informação passada aos agentes

Todo prompt de delegação deve incluir, quando aplicável:

- objetivo e comportamento esperado;
- escopo e exclusões — em trabalho de feature, o recorte do roadmap, em especial o
  "Não inclui";
- spec/task e outros artefatos relevantes;
- arquivos ou símbolos já conhecidos;
- IDs `PERM-*` e `INV-*` aplicáveis;
- resultados relevantes de agentes anteriores;
- verificações esperadas;
- formato de retorno necessário.

Passe um resumo focado. Não despeje toda a conversa ou o repositório no prompt quando o
agente puder localizar o restante a partir de referências precisas.

## Exploração

Use `wms_explorer` antes da implementação quando a feature modifica código existente
relevante, o fluxo não está claro, há dependências cross-file, regras compartilhadas ou risco
significativo de regressão. A saída deve distinguir relações confirmadas de riscos possíveis.

Não use exploração como etapa obrigatória para código novo isolado ou mudança trivial com
contexto já suficiente.

## Implementação

Use `task_implementer` somente quando houver objetivo e escopo concretos. Não peça ao agente
para redefinir requisitos ou arquitetura. Use `frontend_implementer` para tela, componente,
formulário, estado, responsividade ou revisão visual significativa. Se uma tarefa combinar
backend substancial e frontend significativo, divida em etapas e serialize as escritas quando
houver sobreposição de arquivos ou dependência entre elas.

Implementadores devem executar verificações proporcionais ao risco e relatar arquivos,
testes, decisões não óbvias e limitações. Eles não fazem commit, push, merge, rebase ou troca
de branch.

## Review e findings

Depois de uma implementação significativa, use `code_reviewer` com o escopo, a task/spec e
o diff a revisar. O implementador não substitui uma revisão independente.

Trate findings assim:

- P0/P1: corrigir antes de concluir; bug localizado vai ao `debugger`, problema de
  implementação volta ao implementador apropriado;
- P2: normalmente corrigir quando diretamente relacionado ao escopo;
- P3: avaliar sem iniciar automaticamente novo ciclo.

Fluxo normal:

```text
implementação → code_reviewer → correção → code_reviewer
```

Após duas rodadas de correção ainda com desacordo material, requisito inconsistente ou
problema arquitetural não resolvido, pare e apresente a situação ao usuário.

## Bugs

Para bug claramente descrito, use:

```text
debugger → code_reviewer, quando a correção for significativa ou crítica
```

O `debugger` reproduz, coleta evidência, confirma a causa raiz, aplica a menor correção
coerente e adiciona teste de regressão quando viável. Use `wms_explorer` antes somente se o
problema exigir compreensão arquitetural ampla.

## Testes

Use `test_engineer` isoladamente para desenhar cenários, encontrar lacunas comportamentais,
fortalecer testes ou implementar testes sem alterar produção. Se encontrar bug de produção,
encaminhe ao `debugger`; se encontrar funcionalidade ausente, ao `task_implementer`.

## Refactors

Para refactor significativo:

```text
wms_explorer → task_implementer → code_reviewer
```

A exploração deve localizar símbolos, consumidores, contratos, testes e impacto cross-file.
Renomeação ou refactor trivial e localizado não exige o pipeline completo.

## Estoque, segurança e permissões

Para alterações significativas de entrada, saída, transferência, ajuste, inventário,
reserva, saldo ou movimentação, prefira:

```text
wms_explorer → test_engineer → task_implementer → code_reviewer
```

Examine atomicidade, concorrência, locking, idempotência, rollback, autorização,
preservação histórica e consistência de saldo. Happy path isolado não conclui trabalho
crítico de estoque.

Para autenticação, autorização ou isolamento de dados, use normalmente:

```text
test_engineer → task_implementer → code_reviewer
```

Adicione `wms_explorer` quando o código ou as dependências não estiverem claros.

## Trabalho frontend

O `frontend_implementer` trabalha dentro de `DESIGN.md`, da Constitution e dos componentes e
tokens existentes. Regras críticas, autorização e invariantes permanecem no backend.

A skill `impeccable` tem dois usos, e a separação entre eles é o que sustenta o gate.

Como orientação de craft, ela é do implementador: trabalho de frontend significativo corresponde
à descrição da skill e pode ativá-la, e o `frontend_implementer` deve segui-la ao construir,
dentro da fundação já estabelecida em `DESIGN.md`.

Como revisão, ela é do coordenador: `impeccable critique`, `impeccable audit` e
`impeccable_finish_reviewer` são executados por quem coordena, depois da entrega — nunca pelo
autor sobre o próprio trabalho. Um gate executado pelo autor da mudança não é gate. A fundação do
design system — estabelecer, documentar e auditar estruturalmente — também é do coordenador.

Fluxo para frontend significativo:

```text
wms_explorer, quando necessário
→ frontend_implementer
→ code_reviewer (funcional)
→ revisão visual (gate obrigatório — ver abaixo)
→ correções aprovadas
→ nova revisão quando material
```

O pipeline acima é uma sugestão; a revisão visual não é. A Constitution (Princípio VIII) exige
que mudanças significativas de frontend DEVAM passar por revisão visual quanto à aderência ao
`DESIGN.md`, reutilização de componentes, consistência visual e eficiência operacional. O
`code_reviewer` faz revisão funcional e declara explicitamente que não faz auditoria estética;
não considere uma mudança frontend significativa concluída apenas porque ele aprovou.

Use `impeccable critique <target>` como gate visual obrigatório — é crítica de design, não
checagem técnica. `impeccable audit` é complementar e cobre acessibilidade, performance,
responsividade e integridade técnica; não substitui a crítica. Quando existir um build
Impeccable completo, com contrato de direção e capturas, use `impeccable_finish_reviewer` em
lugar do `critique`. `impeccable polish` não faz parte do gate: ele modifica a implementação, e
só cabe como alternativa explícita de correção quando o coordenador optar por corrigir assim em
vez de encaminhar os findings ao `frontend_implementer`.

Quando o `critique` reportar três ou mais Priority Issues, o próprio contrato dele para na
entrega do relatório e exige perguntas direcionadas ao usuário antes de qualquer correção.
Nesse caso, aguarde a seleção do usuário e encaminhe ao `frontend_implementer` somente os
findings aprovados — não repasse o relatório inteiro automaticamente. Com menos de três
Priority Issues, quando o próprio `critique` permitir seguir sem perguntas, os findings podem
ir direto ao `frontend_implementer`.

Após a primeira implementação visual real — quando templates, CSS e componentes deixam de ser
hipotéticos — execute o comando `impeccable document` em modo scan para promover o seed de
`DESIGN.md` a uma representação do código construído e extrair o sidecar
`.impeccable/design.json`. Trate essa transição como obrigatória, não como algo a perceber
depois. Não delegue esse passo ao agente `impeccable_documenter`: ele pressupõe um build
Impeccable completo — contrato de direção e artefatos próprios desse workflow — que uma
implementação comum do `frontend_implementer` não produz; reserve-o para quando esse contrato
existir. Em implementações posteriores, documente apenas mudanças duráveis do sistema (novo
token, novo padrão reutilizável), não cada tela individualmente.

Se ficar evidente que a fundação do design system precisa ser criada, revista ou auditada
estruturalmente — e não apenas uma tela específica — direcione esse trabalho ao workflow
`impeccable`, não ao `frontend_implementer`.

## Tarefas triviais

Não use pipelines complexos para typo, documentação simples, configuração pequena, consulta
sem modificação ou alteração localizada de baixo risco. Use o menor conjunto de agentes que
agregue valor real.

## Conclusão

Uma implementação significativa só está concluída quando:

- as verificações relevantes passaram;
- findings bloqueantes foram tratados;
- o resultado permanece dentro do escopo e do recorte do roadmap;
- limitações e verificações não executadas foram informadas;
- gates de domínio e frontend aplicáveis foram satisfeitos.

Quando a tarefa concluir a entrega de uma feature do roadmap, atualize seu status no
`ROADMAP.md` depois do merge em `main` — e, se a entrega satisfizer dependências de outras
features, registre isso também. Como depende do merge, essa atualização vai num commit
posterior à entrega, sujeito à regra abaixo.

Não faça commit, push, merge ou rebase automaticamente. Essas ações exigem solicitação
explícita do usuário.
