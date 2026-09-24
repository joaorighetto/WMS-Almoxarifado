# WMS-Almoxarifado

Sistema de gestão de materiais, estoque e movimentações do SAEP.

## Desenvolvimento local

O ambiente local é descartável e o projeto não mantém migrations nesta fase: o
schema é criado direto dos models (`migrate --run-syncdb`). Veja `make help`.

### Preparação

```bash
make init    # .venv + dependências; cria .env a partir do .env.example
make setup   # sobe o PostgreSQL (compose.yml) e cria o schema do zero
```

### Dia a dia

```bash
make run       # servidor de desenvolvimento
make resetdb   # depois de alterar models: recria o schema (apaga os dados locais)
make test      # testes (make test PYTEST_ARGS="-k catalogo")
```

### Verificação completa

```bash
make verify    # o mesmo scripts/verify.sh do CI
```
