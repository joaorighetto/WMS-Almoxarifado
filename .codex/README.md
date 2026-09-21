# Subagents do Codex

Esta pasta contém a adaptação nativa para Codex da orquestração existente em
`.claude/rules/agent-orchestration.md` e `.claude/agents/`.

## Estrutura

- `../AGENTS.md`: política do coordenador, fontes de autoridade e workflows;
- `config.toml`: habilita subagents e limita a concorrência;
- `agents/*.toml`: papéis especializados carregados pelo Codex;
- `../.agents/skills/`: workflows reutilizáveis compartilhados pelo projeto.

Os nomes usam `_` porque esse formato é compatível com identificadores de tasks do Codex:

| Claude Code | Codex |
|---|---|
| `wms-explorer` | `wms_explorer` |
| `task-implementer` | `task_implementer` |
| `frontend-implementer` | `frontend_implementer` |
| `code-reviewer` | `code_reviewer` |
| `debugger` | `debugger` |
| `test-engineer` | `test_engineer` |
| `impeccable-*` | `impeccable_*` |

## Uso

O agente principal pode escolher esses papéis ao seguir `AGENTS.md`. Para solicitar
delegação explicitamente, descreva o papel, a divisão do trabalho e se deve aguardar todos
os resultados. Exemplo:

```text
Use wms_explorer para mapear o impacto desta mudança e test_engineer para desenhar os
cenários críticos em paralelo. Aguarde ambos e então encaminhe uma tarefa delimitada ao
task_implementer. Ao final, use code_reviewer e consolide os findings.
```

Subagents read-only possuem `sandbox_mode = "read-only"`. Agentes de implementação herdam
as permissões do turno principal e continuam sujeitos às instruções de escopo do próprio
arquivo. Reinicie a sessão do Codex depois de alterar `AGENTS.md`, `config.toml` ou uma
definição de agente para garantir que toda a configuração seja recarregada.
