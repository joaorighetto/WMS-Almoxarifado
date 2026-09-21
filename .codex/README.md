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
| `impeccable-*` | `impeccable_*` (empacotados pela skill, ver abaixo) |

Os quatro auxiliares `impeccable_*` não são definidos em `agents/`. A skill Impeccable já os
versiona em `../.agents/skills/impeccable/agents/`, com os mesmos `name`, e essa é a definição
vigente. Redefini-los aqui criaria dois registros do mesmo id e faria as cópias divergirem em
silêncio a cada atualização da skill.

## Uso

O agente principal pode escolher esses papéis ao seguir `AGENTS.md`. Para solicitar
delegação explicitamente, descreva o papel, a divisão do trabalho e se deve aguardar todos
os resultados. Exemplo:

```text
Use wms_explorer para mapear o impacto desta mudança e test_engineer para desenhar os
cenários críticos em paralelo. Aguarde ambos e então encaminhe uma tarefa delimitada ao
task_implementer. Ao final, use code_reviewer e consolide os findings.
```

## Permissões

Subagents read-only possuem `sandbox_mode = "read-only"`. Agentes de implementação declaram
`workspace-write`, mas isso não eleva permissão: o Codex reaplica a política de sandbox e as
escolhas de aprovação do turno pai ao criar o filho, mesmo quando o arquivo do agente declara
outro padrão. Na prática, `sandbox_mode` só consegue restringir um subagent, nunca ampliá-lo
além do que a sessão principal já tem.

### Lacuna conhecida: guardrails do `test_engineer`

No Claude Code, a restrição "o `test_engineer` só edita testes" não é prosa: dois hooks
PreToolUse fail-closed a impõem — `validate-test-engineer-write.py` (allowlist estrutural de
caminhos) e `validate-test-engineer-bash.py` (allowlist de comandos, que bloqueia encadeamento,
redirecionamento e substituição, e exige `--frozen`/`--locked` em `uv run`).

O `hooks.json` desta pasta só registra PostToolUse/Stop do detector Impeccable; não há
equivalente por agente. No Codex, portanto, essa restrição existe apenas como instrução dentro
de `agents/test_engineer.toml`, que descreve os mesmos caminhos, programas e flags que os
validadores aplicam.

Isso é uma **equivalência instrucional, não enforcement**. A instrução depende do agente
respeitá-la; o hook não depende — ele bloqueia a chamada e sai com código 2, inclusive nos casos
que não consegue classificar. Não trate as duas formas como garantias equivalentes: no Codex, uma
violação é detectável em review, não impedida em tempo de execução. Por isso o allowlist está
escrito de forma explícita o suficiente para que a revisão consiga apontá-la.

Se o Codex passar a oferecer hook PreToolUse com escopo de subagent, porte os dois validadores e
remova esta seção.

## Manutenção

Reinicie a sessão do Codex depois de alterar `AGENTS.md`, `config.toml` ou uma definição de
agente para garantir que toda a configuração seja recarregada.

`AGENTS.md` é o espelho normativo de `../CLAUDE.md` e `../.claude/rules/agent-orchestration.md`.
Alterações de regra de domínio, gate obrigatório, escopo de agente ou fonte de autoridade devem
ser aplicadas nos dois lados no mesmo commit.
