# Tech stack
- Python 3.13 (`requires-python >=3.13,<3.14`, `.python-version`).
- Django >=6.1, psycopg[binary] 3; PostgreSQL 16 (via `compose.yml` local e service no CI).
- Gerenciador: `uv` (`package = false`, `uv.lock` versionado; CI roda `uv sync --locked`, verify roda `uv lock --check`).
- Dev: pytest + pytest-django (`DJANGO_SETTINGS_MODULE=config.settings.test`, `testpaths=["tests"]`), ruff (py313, line-length 100, regras E,F,W,I,UP,B; migrations e `.specify` excluídos).
- Frontend: Django Templates (APP_DIRS), HTMX 4.0.0 vendorizado em `static/vendor/htmx/`, CSS próprio com tokens; sem bundler/npm.
- Config por env (`.env`, ver `.env.example`): `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DATABASE_*`.
- `AUTH_USER_MODEL = "contas.User"` (login por `matricula`); `LANGUAGE_CODE=pt-br`, `TIME_ZONE=America/Sao_Paulo`.
- Logger `catalogo.importacao` configurado em INFO no console.
