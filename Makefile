# WMS-Almoxarifado — rotinas de desenvolvimento
#
# Fluxo efêmero (fase atual, sem deploy previsto):
# - o projeto não mantém migrations: MIGRATION_MODULES em
#   config/settings/base.py desliga todas, e o schema é criado direto dos
#   models com `migrate --run-syncdb` (aqui e no banco de testes do pytest);
# - o banco local é descartável: mudou model, rode `make resetdb`;
# - a extensão pg_trgm vem do pre_migrate em catalogo/apps.py, não de migration.
#
# Compatível com o GNU Make 3.81 que acompanha o macOS.

# ------------------------------------------------------------------------------
# Ambiente
# ------------------------------------------------------------------------------

# O .env é lido aqui para as guardas do reset e para a conexão do psql.
# Comandos Django/pytest recebem o arquivo via `uv run --env-file`, como em
# scripts/verify.sh; o make exporta só as DATABASE_* (ver abaixo).
ENV_FILE ?= .env
ENV_EXAMPLE_FILE ?= .env.example

ifneq (,$(wildcard $(ENV_FILE)))
include $(ENV_FILE)
endif

SHELL := /bin/bash
.DEFAULT_GOAL := help

# No Windows o find.exe nativo (System32) não entende a sintaxe GNU e vence o
# do Git for Windows na ordem do PATH; por isso o caminho absoluto.
ifeq ($(OS),Windows_NT)
FIND := "/c/Program Files/Git/usr/bin/find"
else
FIND := find
endif

VENV_DIR ?= .venv
UV ?= uv
PSQL ?= psql
DOCKER_COMPOSE ?= docker compose

# Settings dos alvos Django deste Makefile. Um DJANGO_SETTINGS_MODULE vindo do
# .env ganha desta atribuição (o include acima vem antes); a guarda de
# resetpostgres existe justamente para esse caso.
DJANGO_SETTINGS_MODULE ?= config.settings.development
MANAGE := $(UV) run --env-file $(ENV_FILE) python manage.py
DJANGO := DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(MANAGE)

DATABASE_HOST ?= localhost
DATABASE_PORT ?= 5432

# Exportadas para psql e Django enxergarem o mesmo banco, inclusive com
# override na linha de comando (make resetdb DATABASE_NAME=outro): variável de
# ambiente vence o `uv run --env-file`.
export DATABASE_NAME DATABASE_USER DATABASE_PASSWORD DATABASE_HOST DATABASE_PORT

# Conexão do psql pelas variáveis PG* (sem montar URL: senha com caractere
# especial não quebra). Referências do shell ($$), para a senha não ir ao log.
PSQL_CONN := PGHOST="$$DATABASE_HOST" PGPORT="$$DATABASE_PORT" \
	PGUSER="$$DATABASE_USER" PGPASSWORD="$$DATABASE_PASSWORD" \
	PGDATABASE="$$DATABASE_NAME"

PYTEST_ARGS ?=

# Diretórios/artefatos locais que podem ser removidos sem medo
EPHEMERAL_DIRS ?= \
	.pytest_cache \
	.ruff_cache \
	htmlcov \
	staticfiles

# ------------------------------------------------------------------------------
# Ajuda e fallback
# ------------------------------------------------------------------------------

help: ## Mostrar rotinas disponíveis
	@printf "\033[33;1mRotinas disponíveis:\033[0m\n"
	@grep -E '^[a-zA-Z_-]+:.*## ' $(firstword $(MAKEFILE_LIST)) \
		| awk 'BEGIN {FS = ":.*## "}; {printf "  \033[37;1m%-16s\033[0m %s\n", $$1, $$2}'

# Sem estas regras vazias, o make tentaria "refazer" o Makefile e o .env
# incluído usando o fallback abaixo.
Makefile $(ENV_FILE): ;

%:
	@printf "\033[31;1mRotina não reconhecida: '%s'\033[0m\n" "$@"
	@$(MAKE) --no-print-directory help
	@exit 1

# ------------------------------------------------------------------------------
# Bootstrap
# ------------------------------------------------------------------------------

prepare: ## Materializar .env a partir do exemplo (não sobrescreve)
	@test -f $(ENV_FILE) || cp $(ENV_EXAMPLE_FILE) $(ENV_FILE)

# init não toca o banco: num clone novo o .env acabou de ser copiado do
# exemplo e ainda não foi revisado. Resetar o banco é papel de setup.
init: clean-python prepare ## Recriar .venv e instalar dependências (não toca o banco)
	$(UV) sync

setup: ## Subir o PostgreSQL e recriar o schema do zero
	@$(MAKE) --no-print-directory db-up
	@$(MAKE) --no-print-directory resetdb

# ------------------------------------------------------------------------------
# PostgreSQL (compose.yml)
# ------------------------------------------------------------------------------

db-up: ## Subir o PostgreSQL do compose.yml e esperar ficar saudável
	$(DOCKER_COMPOSE) up -d --wait

db-down: ## Parar o PostgreSQL (mantém o volume)
	$(DOCKER_COMPOSE) down

db-destroy: ## Parar o PostgreSQL e APAGAR o volume de dados
	$(DOCKER_COMPOSE) down -v

# ------------------------------------------------------------------------------
# Schema efêmero
# ------------------------------------------------------------------------------

# Reset agressivo, equivalente a apagar um db.sqlite3. Guardas, na ordem:
# - settings em lista permitida (não proibida): um settings novo, como
#   production, já nasce protegido;
# - host local: este alvo nunca apaga schema de banco remoto;
# - variáveis de conexão presentes;
# - banco do projeto: DATABASE_NAME precisa ser wms_almoxarifado ou
#   wms_almoxarifado_<sufixo>. Outro nome só com confirmação digitada
#   (RESETDB_CONFIRMA=<nome>), porque o mesmo servidor local tem outros bancos;
#   os de sistema (postgres, template0, template1) são recusados sempre;
# - psql instalado.
# DROP e CREATE vão num único -c, que o psql executa numa transação só.
resetpostgres: ## Apagar o schema public do banco local e recriá-lo vazio
	@case "$(DJANGO_SETTINGS_MODULE)" in \
		config.settings.development|config.settings.test) ;; \
		*) echo "resetpostgres: DJANGO_SETTINGS_MODULE='$(DJANGO_SETTINGS_MODULE)' fora da lista permitida (config.settings.development, config.settings.test) -- abortando." >&2; exit 1 ;; \
	esac
	@case "$(DATABASE_HOST)" in \
		localhost|127.0.0.1|::1) ;; \
		*) echo "resetpostgres: DATABASE_HOST='$(DATABASE_HOST)' não é local -- abortando." >&2; exit 1 ;; \
	esac
	@test -n "$(DATABASE_NAME)" -a -n "$(DATABASE_USER)" \
		|| { echo "resetpostgres: DATABASE_NAME/DATABASE_USER ausentes em $(ENV_FILE) (rode 'make prepare')." >&2; exit 1; }
	@case "$(DATABASE_NAME)" in \
		postgres|template0|template1) \
			echo "resetpostgres: DATABASE_NAME='$(DATABASE_NAME)' é banco de sistema -- abortando." >&2; exit 1 ;; \
		wms_almoxarifado|wms_almoxarifado_*) ;; \
		*) test "$(RESETDB_CONFIRMA)" = "$(DATABASE_NAME)" \
			|| { echo "resetpostgres: DATABASE_NAME='$(DATABASE_NAME)' não é banco do projeto (wms_almoxarifado[_*]) -- abortando. Para apagar o schema dele mesmo assim: make $(MAKECMDGOALS) RESETDB_CONFIRMA=$(DATABASE_NAME)" >&2; exit 1; } ;; \
	esac
	@command -v $(PSQL) >/dev/null 2>&1 || { echo "resetpostgres: psql não encontrado." >&2; exit 1; }
	@echo "==> recriando schema public de '$(DATABASE_NAME)' em $(DATABASE_HOST):$(DATABASE_PORT)"
	@$(PSQL_CONN) $(PSQL) -X -q -v ON_ERROR_STOP=1 \
		-c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"

# --run-syncdb cria as tabelas de todos os apps direto dos models (nenhum app
# tem migrations). Em schema vazio é uma materialização completa; em schema já
# populado só cria tabelas novas e não altera as existentes — por isso, depois
# de mudar model, use resetdb e não syncdb.
syncdb: ## Criar no banco as tabelas que ainda não existem (não altera as existentes)
	$(DJANGO) migrate --run-syncdb

resetdb: resetpostgres ## Recriar o schema do zero a partir dos models atuais
	@$(MAKE) --no-print-directory syncdb

# ------------------------------------------------------------------------------
# Aplicação
# ------------------------------------------------------------------------------

run: ## Subir o servidor de desenvolvimento
	$(DJANGO) runserver

shell: ## Abrir o shell do Django
	$(DJANGO) shell

# ------------------------------------------------------------------------------
# Qualidade
# ------------------------------------------------------------------------------

# O pytest-django cria um banco de testes novo a cada execução, também via
# syncdb, então os testes acompanham os models sem passo extra. As settings
# vêm do pyproject.toml (config.settings.test). Ex.: make test PYTEST_ARGS="-k catalogo"
test: ## Rodar a suíte de testes
	$(UV) run --env-file $(ENV_FILE) pytest $(PYTEST_ARGS)

lint: ## Rodar o ruff
	$(UV) run ruff check .

verify: ## Rodar a verificação completa do CI (scripts/verify.sh)
	./scripts/verify.sh

# ------------------------------------------------------------------------------
# Limpeza
# ------------------------------------------------------------------------------

# clean não toca o banco: limpar cache e apagar dados são decisões separadas.
# Diretórios migrations/ que alguém gere por engano são ignorados pelas
# settings (e pelo .gitignore); removê-los só evita confusão.
clean: ## Remover caches e artefatos locais (não toca o banco nem a .venv)
	-rm -rf $(EPHEMERAL_DIRS)
	-rm -rf */migrations

clean-python: ## Remover .venv e bytecode Python (não toca o banco)
	-rm -rf $(VENV_DIR)
	-$(FIND) . -path "./$(VENV_DIR)" -prune -o -type d -name "__pycache__" -prune -exec rm -rf {} +

# clean-python fica na receita, não nos pré-requisitos, para não correr em
# paralelo com clean sob `make -jN`.
veryclean: clean ## Voltar o workspace ao estado "do zero" (não toca o banco)
	@$(MAKE) --no-print-directory clean-python

.PHONY: help prepare init setup db-up db-down db-destroy resetpostgres syncdb resetdb \
	run shell test lint verify clean clean-python veryclean
