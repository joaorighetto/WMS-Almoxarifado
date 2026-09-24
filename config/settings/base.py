"""
Django settings comuns a todos os ambientes.

Cada ambiente (development, test, production) importa este módulo e
sobrescreve apenas o que precisa variar (DEBUG, ALLOWED_HOSTS, SECRET_KEY).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")

DEBUG = False

ALLOWED_HOSTS = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "contas",
    "django.contrib.postgres",
    "catalogo",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "contas.middleware.RetornoPosLoginMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DATABASE_NAME"),
        "USER": os.environ.get("DATABASE_USER"),
        "PASSWORD": os.environ.get("DATABASE_PASSWORD"),
        "HOST": os.environ.get("DATABASE_HOST", "localhost"),
        "PORT": os.environ.get("DATABASE_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "pt-br"

TIME_ZONE = "America/Sao_Paulo"

USE_I18N = True

USE_TZ = True

STATIC_URL = "static/"

STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Schema efêmero: nesta fase o projeto não mantém migrations. Com
# MIGRATION_MODULES respondendo None para qualquer app, o Django trata todos
# como "sem migrations" e `migrate --run-syncdb` (make resetdb, e o banco de
# testes do pytest-django) cria as tabelas direto dos models. Desligar todos os
# apps, e não só os do projeto, é obrigatório: `contas.User` é o
# AUTH_USER_MODEL, e um app com migrations (admin, auth) não pode depender de
# um app sem migrations. Antes do primeiro ambiente com dados duráveis, isto
# sai e as migrations voltam a ser geradas e versionadas (Constitution XIII).
class _SemMigrations:
    def __contains__(self, app_label):
        return True

    def __getitem__(self, app_label):
        return None


MIGRATION_MODULES = _SemMigrations()

AUTH_USER_MODEL = "contas.User"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

# Logger dedicado à importação do catálogo (Constitution XIV). Não altera o
# comportamento dos demais loggers do Django.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "catalogo.importacao": {
            "handlers": ["console"],
            "level": "INFO",
        },
    },
}
