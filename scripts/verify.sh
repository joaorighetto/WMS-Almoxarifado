#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> uv lock --check"
uv lock --check

echo "==> ruff check"
uv run --frozen ruff check .

echo "==> manage.py check"
uv run --frozen --env-file .env python manage.py check

echo "==> manage.py makemigrations --check --dry-run"
uv run --frozen --env-file .env python manage.py makemigrations --check --dry-run

echo "==> pytest"
uv run --frozen --env-file .env pytest
