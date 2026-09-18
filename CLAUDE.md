# WMS-Almoxarifado

Este repositório utiliza Claude Code com Spec Kit, Serena MCP e subagents especializados.

## Fontes de autoridade

Ao trabalhar neste projeto, respeite a seguinte ordem de contexto:

1. `.specify/memory/constitution.md` — princípios obrigatórios de engenharia;
2. `spec.md` — requisitos e comportamento esperado da feature;
3. `plan.md` — solução técnica planejada;
4. `tasks.md` — unidades de implementação;
5. `DESIGN.md` — design system, quando existir;
6. código existente — realidade atual da implementação.

Se houver conflito material entre essas fontes, não escolha silenciosamente uma interpretação. Identifique o conflito antes de prosseguir.

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