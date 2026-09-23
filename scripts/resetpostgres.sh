#!/usr/bin/env bash
# Apaga o schema public do banco local do projeto e o recria vazio. Reset
# agressivo, equivalente a apagar um db.sqlite3.
#
# Chamado por `make resetpostgres` via `uv run --env-file .env`: as DATABASE_*
# chegam pelo mesmo parser de dotenv que o Django usa (aspas, `$` e `#` intactos),
# e variáveis de ambiente — inclusive overrides da linha de comando do make —
# vencem o .env.
set -euo pipefail

falha() {
    echo "resetpostgres: $* -- abortando." >&2
    exit 1
}

# Guardas, na ordem:
# - settings em lista permitida (não proibida): um settings novo, como
#   production, já nasce protegido;
# - sem PGHOSTADDR/PGSERVICE: o libpq (psql e psycopg) deixa hostaddr vencer
#   host, então esses dois podem levar a conexão para outro servidor mesmo com
#   DATABASE_HOST local;
# - host local: este script nunca apaga schema de banco remoto;
# - variáveis de conexão presentes;
# - banco do projeto: wms_almoxarifado ou wms_almoxarifado_<sufixo>. Outro nome
#   só com confirmação digitada (RESETDB_CONFIRMA=<nome>), porque o mesmo
#   servidor local tem outros bancos; os de sistema são recusados sempre;
# - psql instalado.
case "${DJANGO_SETTINGS_MODULE:-}" in
    config.settings.development | config.settings.test) ;;
    *) falha "DJANGO_SETTINGS_MODULE='${DJANGO_SETTINGS_MODULE:-}' fora da lista permitida (config.settings.development, config.settings.test)" ;;
esac

[ -z "${PGHOSTADDR:-}" ] || falha "PGHOSTADDR='$PGHOSTADDR' definido no ambiente; ele vence DATABASE_HOST no libpq"
[ -z "${PGSERVICE:-}" ] || falha "PGSERVICE='$PGSERVICE' definido no ambiente; o serviço pode redirecionar a conexão"

host="${DATABASE_HOST:-localhost}"
port="${DATABASE_PORT:-5432}"
case "$host" in
    localhost | 127.0.0.1 | ::1) ;;
    *) falha "DATABASE_HOST='$host' não é local" ;;
esac

[ -n "${DATABASE_NAME:-}" ] && [ -n "${DATABASE_USER:-}" ] \
    || falha "DATABASE_NAME/DATABASE_USER ausentes no .env (rode 'make prepare')"

case "$DATABASE_NAME" in
    postgres | template0 | template1)
        falha "DATABASE_NAME='$DATABASE_NAME' é banco de sistema" ;;
    wms_almoxarifado | wms_almoxarifado_*) ;;
    *)
        [ "${RESETDB_CONFIRMA:-}" = "$DATABASE_NAME" ] \
            || falha "DATABASE_NAME='$DATABASE_NAME' não é banco do projeto (wms_almoxarifado[_*]). Para apagar o schema dele mesmo assim, repita o comando com RESETDB_CONFIRMA=$DATABASE_NAME" ;;
esac

command -v psql >/dev/null 2>&1 || falha "psql não encontrado"

echo "==> recriando schema public de '$DATABASE_NAME' em $host:$port"
# Conexão pelas variáveis PG* (sem montar URL: senha com caractere especial não
# quebra). DROP e CREATE vão num único -c, que o psql executa numa transação só.
PGHOST="$host" PGPORT="$port" PGUSER="$DATABASE_USER" \
    PGPASSWORD="${DATABASE_PASSWORD:-}" PGDATABASE="$DATABASE_NAME" \
    psql -X -q -v ON_ERROR_STOP=1 -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
