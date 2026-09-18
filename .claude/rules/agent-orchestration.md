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
- `task-implementer`: implementação de tarefas claramente definidas;
- `code-reviewer`: revisão independente read-only;
- `debugger`: diagnóstico e correção de bugs;
- `test-engineer`: projeto, criação e revisão de testes.

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

Forneça ao implementador:

- objetivo;
- task correspondente;
- artefatos Spec Kit relevantes;
- resultado da exploração, se houver;
- cenários críticos identificados pelo `test-engineer`, se houver;
- limites explícitos de escopo.

Não peça ao `task-implementer` para redefinir requisitos ou arquitetura.

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
- problema de implementação da tarefa → `task-implementer`.

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

## Segurança e permissões

Mudanças significativas envolvendo autorização, autenticação ou isolamento
de dados devem normalmente passar por:

`test-engineer → task-implementer → code-reviewer`

Quando código existente ou dependências não estiverem claros, adicione
`wms-explorer` antes.

## Trabalho frontend

Enquanto não existir um `frontend-implementer` especializado:

- pequenas mudanças frontend podem ser atribuídas ao `task-implementer`;
- mudanças frontend significativas devem ser tratadas com cautela e
  respeitar `DESIGN.md` quando ele existir.

Não crie ou invoque um agente frontend inexistente.

Essa política será atualizada quando o workflow Impeccable + frontend-design
estiver configurado.

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
- `spec.md` → comportamento/requisitos da feature;
- `plan.md` → solução técnica planejada;
- `tasks.md` → unidades de implementação;
- `DESIGN.md` → design system, quando existir;
- código existente → realidade atual da implementação;
- relatórios dos subagents → evidência e análise, não novas fontes
  normativas.

Se houver conflito material entre essas fontes, não escolha arbitrariamente.
Apresente ou resolva o conflito antes de continuar.

Relatórios, findings, hipóteses e recomendações produzidos pelos subagents
são evidências e análises. Eles não alteram automaticamente:

- Constitution;
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
