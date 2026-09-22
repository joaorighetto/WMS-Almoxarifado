# Conclusão de tarefa
Rodar `./scripts/verify.sh` (mesmo gate do CI `.github/workflows/ci.yml`), que executa em ordem:
1. `uv lock --check`
2. `uv run --frozen ruff check .`
3. `manage.py check` (com `.env`)
4. `manage.py check --deploy --fail-level WARNING --settings=config.settings.production` (secret/hosts fictícios injetados pelo script)
5. `manage.py makemigrations --check --dry-run` — mudança de model sem migration falha aqui
6. `pytest`
Requer Postgres ativo (`docker compose up -d --wait`) e `.env` presente.
Commit/push só com pedido explícito do usuário (CLAUDE.md).
