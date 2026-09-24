# WMS-Almoxarifado

Sistema de gestão de materiais, estoque e movimentações do SAEP.

## Desenvolvimento local

O ambiente local é descartável e o projeto não mantém migrations nesta fase: o
schema é criado direto dos models (`migrate --run-syncdb`). Veja `make help`.

### Preparação

```bash
make init    # .venv + dependências; cria .env a partir do .env.example
```

Defina `SEED_DEV_PASSWORD` no `.env` com a senha local das contas de demonstração
(sujeita aos validadores de senha do Django). O catálogo usa o arquivo existente
`docs/domain-legacy/relacao-de-todos-produtos-importados-do-SCPI.csv`, que não é
versionado e precisa estar disponível localmente.

```bash
make setup   # valida configuração, sobe PostgreSQL, recria schema e executa seed_dev
make run     # aplicação em http://127.0.0.1:8000/
```

O `setup` verifica a senha e o CSV antes de apagar o banco. Os dados e as contas
disponíveis estão em [Dados de desenvolvimento](docs/development/seed-dev.md).

### Dia a dia

```bash
make run       # servidor de desenvolvimento
make resetdb   # depois de alterar models: recria o schema (apaga os dados locais)
make seed_dev  # popula novamente após resetdb; repetir um seed completo não altera dados
make test      # testes (make test PYTEST_ARGS="-k catalogo")
```

### Verificação completa

```bash
make verify    # o mesmo scripts/verify.sh do CI
```
