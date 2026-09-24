# Quickstart — validação de ponta a ponta

Roteiro para comprovar a feature 001 depois de implementada. Não contém código de implementação.
Contratos: [arquivo-scpi.md](./contracts/arquivo-scpi.md),
[rotas-e-autorizacao.md](./contracts/rotas-e-autorizacao.md). Modelo:
[data-model.md](./data-model.md).

## Pré-requisitos

- Ambiente da 002 funcionando (`.env` conforme `.env.example`, PostgreSQL 16 via `compose.yml`).
- O usuário do banco precisa poder executar `CREATE EXTENSION pg_trgm`. `pg_trgm` é *trusted* no
  PostgreSQL ≥ 13: basta o privilégio `CREATE` no banco. O usuário dono do banco em `compose.yml`
  e na CI já tem esse privilégio.
- Schema criado a partir dos models: `make resetdb` (equivale a
  `uv run --env-file .env python manage.py migrate --run-syncdb` sobre um schema vazio). O projeto
  não mantém migrations nesta fase ("Schema efêmero" em `CLAUDE.md`); a extensão `pg_trgm` é
  criada no `pre_migrate` de `catalogo/apps.py`.

## 1. Usuários de validação

Seguindo o provisionamento da 002 (`specs/002-autenticacao-login/quickstart.md` §1), crie no setor
Almoxarifado:

| Matrícula (exemplo) | Papéis explícitos | Uso |
|---|---|---|
| chefe | `ROLE-REQUESTER`, `ROLE-WAREHOUSE-STAFF`, `ROLE-SECTOR-HEAD`, `ROLE-WAREHOUSE-HEAD` | importa, consulta, vê histórico |
| funcionario | `ROLE-REQUESTER`, `ROLE-WAREHOUSE-STAFF` | só consulta |
| requisitante | `ROLE-REQUESTER` | só consulta |

O superusuário técnico da 002 não tem papel de negócio e deve receber 403 em todas as rotas do
catálogo.

## 2. Suíte automatizada

```bash
./scripts/verify.sh          # lock, ruff, check, check --deploy, pytest
```

Os testes do catálogo usam as fixtures sintéticas de `tests/fixtures/catalogo/`. O teste contra o
arquivo real é *skipped* sem a variável descrita em §5.

## 3. Roteiro manual — carga inicial (US1, US3)

1. Entre como **chefe** → Home mostra "Catálogo de materiais", "Importar catálogo" e "Histórico
   de importações".
2. Importar catálogo → envie `tests/fixtures/catalogo/carga_inicial_casos_spec.csv`.
3. **Prévia**: confira os totais esperados, a lista de exceções com linha e motivo, e o aviso de
   que nada foi gravado. Abra `/catalogo/` em outra aba: o catálogo continua vazio (FR-044a).
4. Confirme → você é levado ao resultado da execução: totais com `recebidos = inseridos +
   atualizados + rejeitados`, exceções idênticas às da prévia.
5. Recarregue/reenvie o POST de confirmação (voltar + reenviar): nenhuma segunda execução é criada.
6. Histórico de importações: a execução aparece com matrícula, momento e arquivo.

## 4. Roteiro manual — consulta (US2) e reimportação (US4)

1. Entre como **requisitante** → `/catalogo/`:
   - código `000.000.002` → exatamente um material, código exibido sem alteração;
   - código `2` → mensagem pedindo o código completo, sem resultados;
   - palavras da descrição em minúsculas, sem acento e fora de ordem (ex.: `registro valv`) →
     encontra a descrição acentuada;
   - palavra inexistente → estado "nenhum material encontrado";
   - com JavaScript desativado, a mesma busca funciona por página inteira.
2. Como **requisitante**, abra `/catalogo/importacao/` e `/catalogo/importacoes/` → 403.
3. Como **chefe**, altere no shell o saldo de `010.020.031` — o material que a fixture usa para
   divergência —, simulando uma movimentação futura
   (`Material.objects.filter(cadpro="010.020.031").update(saldo=8)`), e reimporte
   `tests/fixtures/catalogo/reimportacao.csv` (que traz `QUAN3=15` para esse código):
   - prévia: divergência com saldo WMS 8, arquivo 15, diferença +7; atualização de descrição em
     outros materiais; contagem de ausentes do arquivo;
   - confirme: saldo continua 8; descrição atualizada; alteração cadastral visível no detalhe da
     execução.
4. Reimporte o mesmo arquivo sem mudanças → "atualizados com alteração" = 0; nenhuma alteração
   cadastral nova.

## 5. Validação contra o arquivo real (aceite de SC-001, SC-002, SC-004, SC-008)

O export real não é versionado. Hoje ele existe só localmente, em
`docs/domain-legacy/relacao-de-todos-produtos-importados-do-SCPI.csv`, ignorado pelo Git. Com o
arquivo disponível no ambiente de validação:

```bash
SCPI_CSV_REAL=/caminho/para/relacao-de-todos-produtos-importados-do-SCPI.csv \
  uv run --frozen --env-file .env pytest tests/test_catalogo_arquivo_real.py -v
```

Resultado esperado (conforme a análise registrada na spec): 1588 recebidos, 1588 inseridos, 0
rejeitados sobre catálogo vazio; todo `CADPRO` idêntico ao arquivo; `004.001.002` com a descrição
recomposta; `000.029.742` com saldo `53.400`; saldo de cada material igual ao `QUAN3` do arquivo
na escala de 3 casas. Uma reimportação imediata do mesmo arquivo dá 1588 atualizados, 0 com
alteração e 0 divergências.

Sem o arquivo, a feature pode ser implementada e revisada, mas o aceite desses SCs fica pendente
(ROADMAP, "Evidências de importação").

## 6. Gates antes de concluir

- `code-reviewer` sobre o diff completo.
- `impeccable critique` das telas de consulta, envio/prévia e histórico/detalhe (gate visual
  obrigatório).
- `impeccable document` para registrar no `DESIGN.md` os componentes que passaram a existir.
- `/speckit-converge`.
