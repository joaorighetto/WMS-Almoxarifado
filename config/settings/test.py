import os

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "test-secret-key-not-for-production")
ALLOWED_HOSTS = ["*"]

# Hasher barato só nos testes: o PBKDF2 padrão (1,5M iterações) custava ~0,11s
# por usuário criado ou autenticado e respondia por ~84% do tempo da suíte. O
# fluxo real (set_password/check_password) continua exercitado; só o algoritmo
# muda. Nunca copie isto para outro ambiente: test_settings.py garante que
# development/production mantêm o hasher padrão do Django, e o teste do Admin
# que exige o hasher nativo restaura esse padrão localmente.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
