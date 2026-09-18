import os

from .base import *  # noqa: F403

DEBUG = False
# Falha explicitamente se ausente, sem default hardcoded.
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()
]

# Princípio VI da Constitution: proteções de sessão/transporte DEVEM
# permanecer ativas. SECURE_PROXY_SSL_HEADER depende de detalhes de deploy
# (proxy reverso) ainda não definidos e fica para quando o deploy for
# configurado.
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 3600

# Desvio consciente (Constitution: "desvio DEVE ser documentado"): HSTS em
# subdomínios e submissão à preload list exigem confirmar antes que TODOS os
# subdomínios do domínio real sirvam exclusivamente HTTPS — decisão que
# depende do domínio de produção, ainda não definido. Ficam desligados e
# silenciados no `check --deploy` até essa decisão de deploy ser tomada;
# revisitar então (ligar SECURE_HSTS_INCLUDE_SUBDOMAINS/SECURE_HSTS_PRELOAD e
# remover daqui).
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]
