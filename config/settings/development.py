import os

from .base import *  # noqa: F403

DEBUG = os.environ.get("DJANGO_DEBUG", "True") == "True"
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Login simulado por papel (contas/login_simulado.py): autentica uma conta real do seed_dev
# sem o formulário, para verificações visuais e agentes. Só existe nestas settings e só com
# DEBUG; desligue com WMS_LOGIN_SIMULADO=False no .env para exercitar o login de verdade.
WMS_LOGIN_SIMULADO = DEBUG and os.environ.get("WMS_LOGIN_SIMULADO", "True") == "True"
WMS_LOGIN_SIMULADO_PADRAO = os.environ.get("WMS_LOGIN_SIMULADO_PADRAO", "chefe-almoxarifado")

if WMS_LOGIN_SIMULADO:
    # Lista nova, não insert(): `from .base import *` compartilha o objeto com base.py.
    _posicao = MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1  # noqa: F405
    MIDDLEWARE = [  # noqa: F405
        *MIDDLEWARE[:_posicao],  # noqa: F405
        "contas.login_simulado.LoginSimuladoMiddleware",
        *MIDDLEWARE[_posicao:],  # noqa: F405
    ]
    LOGGING = {  # noqa: F405
        **LOGGING,  # noqa: F405
        "loggers": {
            **LOGGING["loggers"],  # noqa: F405
            "contas.login_simulado": {"handlers": ["console"], "level": "INFO"},
        },
    }
