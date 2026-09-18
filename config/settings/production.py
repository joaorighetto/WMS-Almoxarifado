import os

from .base import *  # noqa: F403

DEBUG = False
# Falha explicitamente se ausente, sem default hardcoded.
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()
]

# Princípio VI da Constitution: proteções de sessão/transporte DEVEM
# permanecer ativas. SECURE_PROXY_SSL_HEADER e HSTS de longo prazo dependem
# de detalhes de deploy (proxy reverso, domínio) ainda não definidos e
# ficam para quando o deploy for configurado.
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 3600
