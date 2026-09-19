# WMS-Almoxarifado

Este repositório utiliza Claude Code com Spec Kit, Serena MCP e subagents especializados.

## Fontes de autoridade

Ao trabalhar neste projeto, respeite a seguinte ordem de contexto:

1. `.specify/memory/constitution.md` — princípios obrigatórios de engenharia;
2. `PRODUCT.md` e a documentação canônica de domínio (`docs/domain/permissions-matrix.md` e
   `docs/domain/invariants-matrix.md`) — verdade de produto, de autorização e de invariantes válida
   em todo o repositório, não só na feature em andamento;
3. `spec.md` — requisitos e comportamento esperado da feature;
4. `plan.md` — solução técnica planejada;
5. `tasks.md` — unidades de implementação;
6. `DESIGN.md` — design system, quando existir;
7. código existente — realidade atual da implementação.

Essa ordem não é uma regra simples de "arquivo de cima sempre sobrescreve arquivo de baixo". Uma
feature deve respeitar os artefatos canônicos transversais. Se uma nova decisão de produto precisar
alterar uma permissão ou invariante já canônica, o artefato transversal correspondente deve ser
atualizado explicitamente — nunca contornado silenciosamente por uma spec.

Se houver conflito material entre essas fontes, não escolha silenciosamente uma interpretação. Identifique o conflito antes de prosseguir.

## Documentação canônica de domínio

Além dos artefatos de feature (`spec.md`/`plan.md`/`tasks.md`), o projeto mantém documentação de
domínio válida em todo o repositório, independente de qual feature está sendo trabalhada:

- `docs/domain/permissions-matrix.md`
  Fonte canônica de papéis, capabilities, escopos e condições de autorização. **Validada.**
- `docs/domain/invariants-matrix.md`
  Fonte canônica das propriedades transversais que devem permanecer verdadeiras no domínio.
  **Validada.**

Resumindo a diferença: `permissions-matrix.md` responde **quem** pode executar determinada
capacidade, dentro de qual escopo e condições; `invariants-matrix.md` responde **o que** deve
permanecer verdadeiro no domínio, independentemente de quem executa a operação.

Relatórios em `docs/domain/reconciliation/` e em `docs/domain-legacy/reconciliation/` são
históricos e não normativos — explicam origem, alternativas consideradas, decisões descartadas e
pendências, mas nunca substituem as matrizes canônicas acima. Quando houver divergência, as
matrizes canônicas representam o estado vigente; não use um relatório de reconciliação para reviver
algo lá descartado, pendente ou substituído.

Specifications relacionadas a operações ou regras transversais devem referenciar as capabilities e
invariantes aplicáveis por ID, numa seção `## Regras canônicas aplicáveis` (com subseções
`### Permissões` e `### Invariantes`, por exemplo `PERM-REQ-CREATE-SELF` e `INV-STOCK-004`) — só
quando houver regra transversal relevante, nunca como seção obrigatória em toda spec, e nunca
copiando o texto completo das matrizes. Uma spec nova não redefine silenciosamente o significado de
uma capability ou invariante existente; para alterar uma, primeiro registre a decisão e atualize a
matriz canônica correspondente, só depois use o novo comportamento na spec.

Pela mesma lógica, tasks de domínio crítico podem referenciar os IDs que aplicam e preservam (ex.:
`Aplica: PERM-STOCK-ENTRY-CREATE` / `Preserva: INV-STOCK-001, INV-STOCK-004, INV-MOV-002`) — não é
obrigatório para tasks triviais.

## Arquitetura base

O projeto utiliza principalmente:

- Python;
- Django;
- PostgreSQL;
- Django Templates;
- HTMX;
- CSS próprio;
- JavaScript pontual.

A aplicação é predominantemente server-driven.

Não introduza SPA, framework frontend, biblioteca relevante ou nova camada arquitetural sem necessidade concreta e justificativa compatível com a Constitution.

## Serena MCP

Use Serena como ferramenta preferencial para exploração e modificação semântica de código existente quando apropriado.

Priorize Serena para:

- localizar símbolos;
- encontrar referências e consumidores;
- compreender fluxos existentes;
- avaliar impacto de alterações;
- realizar refactors semânticos quando suportados.

Não force Serena para documentação, configuração, CSS, templates ou pequenas alterações textuais quando ferramentas convencionais forem mais adequadas.

## Subagents

Este projeto possui os seguintes subagents:

- `wms-explorer` — exploração semântica e análise de impacto read-only;
- `task-implementer` — implementação de tarefas definidas;
- `code-reviewer` — revisão independente read-only;
- `debugger` — diagnóstico e correção de bugs;
- `test-engineer` — estratégia, criação e revisão de testes.

O Claude da sessão principal é responsável por coordenar esses agentes.

As regras detalhadas de orquestração estão em:

`.claude/rules/agent-orchestration.md`

Use os agentes quando agregarem valor real. Não execute pipelines completos para alterações triviais.

## Escopo

Evite ampliar escopo silenciosamente.

Não use uma tarefa como oportunidade para:

- refatorar áreas não relacionadas;
- trocar bibliotecas;
- alterar arquitetura;
- corrigir bugs independentes;
- introduzir abstrações especulativas.

Problemas relevantes fora do escopo devem ser reportados separadamente.

## Testes

Testes devem proteger comportamento e invariantes relevantes, não apenas aumentar cobertura.

Dê atenção especial a:

- regras de negócio;
- permissões;
- estoque;
- transações;
- concorrência;
- rollback;
- regressões.

## Git

Não faça commit, push, merge, rebase ou alteração de branch sem solicitação explícita do usuário.

Mantenha o working tree sob controle e informe claramente arquivos modificados e verificações executadas.