#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> uv lock --check"
uv lock --check

echo "==> ruff check"
uv run --frozen ruff check .

echo "==> manage.py check"
uv run --frozen --env-file .env python manage.py check

# Settings de produção nunca são exercitadas por "manage.py check" acima
# (que valida o default, config.settings.development). Valida-as aqui com
# valores dedicados a esta checagem (não os de .env) — o objetivo é só
# confirmar que production.py está bem configurado, não simular um deploy
# real.
echo "==> manage.py check --deploy (config.settings.production)"
DJANGO_SECRET_KEY="ci-deploy-check-only-not-a-real-secret-0123456789abcdefghijklmnop" \
DJANGO_ALLOWED_HOSTS="verify.invalid" \
  uv run --frozen python manage.py check --deploy --fail-level WARNING --settings=config.settings.production

echo "==> manage.py makemigrations --check --dry-run"
uv run --frozen --env-file .env python manage.py makemigrations --check --dry-run

echo "==> pytest"
uv run --frozen --env-file .env pytest
