# WMS-Almoxarifado

Este repositório utiliza Claude Code com Spec Kit, Serena MCP e subagents especializados.

## Fontes de autoridade

Ao trabalhar neste projeto, respeite a seguinte ordem de contexto:

1. `.specify/memory/constitution.md` — princípios obrigatórios de engenharia;
2. `PRODUCT.md` e a documentação canônica transversal de domínio (`docs/domain/permissions-matrix.md`
   e, quando validada, `docs/domain/invariants-matrix.md`) — verdade de produto e de
   autorização/invariantes válida em todo o repositório, não só na feature em andamento;
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

## Documentação canônica transversal

Além dos artefatos de feature (`spec.md`/`plan.md`/`tasks.md`), o projeto mantém documentação de
domínio válida em todo o repositório, independente de qual feature está sendo trabalhada:

- `docs/domain/permissions-matrix.md` — fonte canônica de capabilities, papéis, escopos e
  condições de autorização. **Validada.**
- `docs/domain/invariants-matrix.md` — fonte canônica de invariantes de domínio, quando este
  documento existir e estiver validado. Até lá, não tem autoridade nenhuma e não deve ser tratado
  como fonte normativa.

`docs/domain-legacy/reconciliation/permissions-reconciliation.md` é histórico/não normativo — serve
para entender por que uma decisão de permissão existe, nunca para reviver algo lá descartado,
pendente ou substituído.

Specifications relacionadas a operações protegidas devem referenciar as capabilities aplicáveis por
ID, numa seção `## Autorizações aplicáveis` (por exemplo, `PERM-REQ-CREATE-SELF`) — só quando houver
autorização relevante, nunca como seção obrigatória em toda spec. Uma spec nova não redefine
silenciosamente o significado de uma capability existente; para alterar uma, primeiro registre a
decisão e atualize `permissions-matrix.md`, só depois use o novo comportamento na spec.

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