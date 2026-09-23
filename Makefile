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

# O make não lê o .env (um `include` guardaria aspas e interpretaria `$` e `#`
# de outro jeito que o dotenv). Todo comando recebe o arquivo via
# `uv run --env-file`, como em scripts/verify.sh, então psql e Django leem os
# mesmos valores. Overrides na linha de comando (make resetdb DATABASE_NAME=x)
# chegam ao ambiente da receita e vencem o .env.
ENV_FILE ?= .env
ENV_EXAMPLE_FILE ?= .env.example

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
# Compose recebe o mesmo ENV_FILE do reset e dos comandos Django (sem isso ele
# leria sempre o .env padrão). Só quando o arquivo existe: sem .env, o compose
# usa os defaults do compose.yml.
DOCKER_COMPOSE ?= docker compose $(if $(wildcard $(ENV_FILE)),--env-file $(ENV_FILE))

# Settings dos alvos Django deste Makefile, passadas pelo ambiente: vencem um
# DJANGO_SETTINGS_MODULE que o .env venha a definir. O reset só as aceita em
# lista permitida (scripts/resetpostgres.sh).
DJANGO_SETTINGS_MODULE ?= config.settings.development
UV_RUN := DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(UV) run --env-file $(ENV_FILE)
DJANGO := $(UV_RUN) python manage.py

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

# Sem esta regra vazia, o make tentaria "refazer" o Makefile usando o fallback
# abaixo.
Makefile: ;

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

# As guardas (settings, PGHOSTADDR/PGSERVICE, host local, nome do banco com
# confirmação para fora do padrão) estão no script, que roda sob
# `uv run --env-file` para ler o .env como o Django lê.
resetpostgres: ## Apagar o schema public do banco local e recriá-lo vazio
	@test -f $(ENV_FILE) || { echo "resetpostgres: $(ENV_FILE) não encontrado (rode 'make prepare')." >&2; exit 1; }
	@$(UV_RUN) ./scripts/resetpostgres.sh

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
