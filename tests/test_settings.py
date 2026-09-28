"""Smoke tests para as invariantes de segurança dos settings de produção.

Não usam @pytest.mark.django_db: apenas importam config/settings/production.py
como módulo Python comum para verificar seu comportamento no import, sem
depender do Django settings ativo (config.settings.test) nem de banco.
"""

import importlib
import sys

import pytest
from django.conf import global_settings


def _reimport_production_settings():
    sys.modules.pop("config.settings.production", None)
    return importlib.import_module("config.settings.production")


def test_production_settings_require_secret_key(monkeypatch):
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)

    try:
        _reimport_production_settings()
    except KeyError as exc:
        assert exc.args[0] == "DJANGO_SECRET_KEY"
    else:
        raise AssertionError(
            "config.settings.production deveria falhar sem DJANGO_SECRET_KEY"
        )


@pytest.mark.parametrize(
    "modulo", ["config.settings.development", "config.settings.production"]
)
def test_hasher_rapido_dos_testes_nao_vaza_para_outros_ambientes(monkeypatch, modulo):
    """`config.settings.test` usa MD5 só para acelerar a suíte; os demais
    ambientes precisam continuar com o hasher forte padrão do Django."""
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-only-secret-for-settings-import")
    sys.modules.pop(modulo, None)

    settings_modulo = importlib.import_module(modulo)
    hashers = getattr(settings_modulo, "PASSWORD_HASHERS", global_settings.PASSWORD_HASHERS)

    assert hashers[0] == "django.contrib.auth.hashers.PBKDF2PasswordHasher"
    assert "django.contrib.auth.hashers.MD5PasswordHasher" not in hashers


def test_production_settings_enable_transport_security(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-only-secret-for-settings-import")

    production_settings = _reimport_production_settings()

    assert production_settings.SECURE_SSL_REDIRECT is True
    assert production_settings.SESSION_COOKIE_SECURE is True
    assert production_settings.CSRF_COOKIE_SECURE is True
    assert production_settings.SECURE_HSTS_SECONDS > 0
