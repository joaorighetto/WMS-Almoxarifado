# WMS-Almoxarifado

Sistema de gestão de materiais, estoque e movimentações do SAEP.

## Desenvolvimento local

### Preparação

```bash
uv sync
cp .env.example .env
docker compose up -d --wait
```

### Django

```bash
uv run --env-file .env python manage.py migrate
uv run --env-file .env python manage.py runserver
```

### Testes

```bash
uv run --env-file .env pytest
```

### Verificação completa

```bash
./scripts/verify.sh
```
