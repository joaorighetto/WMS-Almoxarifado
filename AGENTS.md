# Orquestração do Codex — WMS-Almoxarifado

Este arquivo orienta o agente principal do Codex e os subagents deste repositório.
O agente principal coordena o trabalho, consolida resultados e mantém a responsabilidade
pela resposta final. Subagents executam somente o papel recebido e não criam uma segunda
camada de orquestração.

## Princípio geral

Use subagents quando a especialização, o isolamento de contexto ou o paralelismo trouxerem
benefício concreto. Não invoque agentes apenas para cumprir um ritual. Consultas simples,
documentação pequena e mudanças localizadas de baixo risco podem ser executadas diretamente.

Paralelize preferencialmente trabalho independente e read-only, como exploração, desenho de
testes e análise. Serialize etapas dependentes e agentes que escrevem no working tree. Nunca
coloque dois agentes editando os mesmos arquivos simultaneamente.

O agente principal deve:

1. entender a intenção do usuário e delimitar o escopo;
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
5. `spec.md` — comportamento e requisitos da feature;
6. `plan.md` — solução técnica planejada;
7. `tasks.md` — unidades de implementação;
8. `DESIGN.md` — design system e direção visual;
9. código existente — realidade atual da implementação.

Relatórios em `docs/domain/reconciliation/` e `docs/domain-legacy/reconciliation/` são
históricos e não normativos. Relatórios de subagents são evidência e análise; não alteram
automaticamente nenhuma fonte normativa.

Se houver conflito material, não escolha silenciosamente uma interpretação. Identifique o
conflito e obtenha uma decisão antes de implementar algo que dependa dela.

Uma mudança em permissão ou invariante canônica segue este fluxo:

```text
necessidade nova → decisão explícita de domínio → atualizar a matriz canônica
→ atualizar specs afetadas → plan/tasks → implementação → review
```

## Agentes disponíveis

As definições ficam em `.codex/agents/`:

- `wms_explorer`: exploração e análise de impacto read-only;
- `task_implementer`: implementação de tarefas definidas de backend e mudanças frontend
  pequenas ou inseparáveis;
- `frontend_implementer`: frontend significativo em Django Templates, HTMX, CSS e
  JavaScript pontual, dentro de `DESIGN.md`;
- `code_reviewer`: revisão independente e read-only;
- `debugger`: diagnóstico, causa raiz, correção mínima e teste de regressão;
- `test_engineer`: desenho, criação e revisão de testes, sem alterar produção;
- `impeccable_asset_producer`, `impeccable_documenter`,
  `impeccable_finish_reviewer` e `impeccable_manual_edit_applier`: auxiliares do
  workflow visual Impeccable.

Use os nomes acima ao solicitar explicitamente um papel. Os agentes especializados não
devem delegar para outros agentes; quando precisarem de outro papel, devem devolver ao
coordenador uma solicitação objetiva.

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

## Workflow de feature com Spec Kit

Quando uma feature possuir o fluxo Spec Kit, use as skills existentes em `.agents/skills`
e siga normalmente:

```text
speckit-specify → speckit-clarify → speckit-plan → speckit-checklist (quando agregar valor)
→ speckit-tasks → speckit-analyze → implementação → review → correções
→ speckit-converge
```

Não execute `speckit-converge` antes da implementação. Se a clarificação ou análise conflitar
com uma regra canônica, exponha o conflito e siga o fluxo explícito de mudança de domínio.

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
- escopo e exclusões;
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

O `frontend_implementer` trabalha dentro de `DESIGN.md`, da Constitution e dos componentes
existentes. Para tarefas de design ou melhoria de interface, use a skill `impeccable` conforme
suas instruções. Regras críticas, autorização e invariantes permanecem no backend.

Fluxo sugerido para frontend significativo:

```text
wms_explorer, quando necessário
→ frontend_implementer
→ code_reviewer (funcional)
→ revisão visual com a skill impeccable
→ correções aprovadas
→ nova revisão quando material
```

O review funcional não substitui o gate visual. Use `impeccable critique` para a crítica de
design e `impeccable audit` como complemento técnico. Quando existir um build Impeccable
com contrato de direção e capturas, use `impeccable_finish_reviewer`.

Se a crítica produzir três ou mais Priority Issues e a skill exigir escolha do usuário,
aguarde essa seleção antes de encaminhar correções. Não use `impeccable polish` como gate,
pois ele modifica a implementação.

Após a primeira implementação visual real, execute o modo de documentação/scan definido
pela skill `impeccable` para promover o seed de `DESIGN.md` a uma representação do código
construído. Em mudanças posteriores, documente apenas tokens e padrões reutilizáveis duráveis.

## Tarefas triviais

Não use pipelines complexos para typo, documentação simples, configuração pequena, consulta
sem modificação ou alteração localizada de baixo risco. Use o menor conjunto de agentes que
agregue valor real.

## Conclusão

Uma implementação significativa só está concluída quando:

- as verificações relevantes passaram;
- findings bloqueantes foram tratados;
- o resultado permanece dentro do escopo;
- limitações e verificações não executadas foram informadas;
- gates de domínio e frontend aplicáveis foram satisfeitos.

Não faça commit, push, merge ou rebase automaticamente. Essas ações exigem solicitação
explícita do usuário.
