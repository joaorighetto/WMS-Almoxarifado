# Comandos
Setup:
- `uv sync` · `cp .env.example .env` · `docker compose up -d --wait` (Postgres local em 127.0.0.1:5432)

Django (sempre com `--env-file .env`, settings default vêm do env/manage.py):
- `uv run --env-file .env python manage.py migrate`
- `uv run --env-file .env python manage.py runserver`
- `uv run --env-file .env python manage.py createsuperuser` (pede `setor` → PK de Setor existente)

Testes/lint:
- `uv run --env-file .env pytest` (precisa do Postgres rodando)
- `uv run --env-file .env pytest tests/test_catalogo_importacao.py -k <expr>`
- `uv run ruff check .` · `uv run ruff format .`
- Verificação completa: `./scripts/verify.sh` (ver `mem:task_completion`)

Darwin: `sed -i ''` (BSD) em vez de `sed -i`; `grep -P` indisponível — usar `grep -E` ou `rg`.
