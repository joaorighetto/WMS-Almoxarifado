import os

from .base import *  # noqa: F403

DEBUG = os.environ.get("DJANGO_DEBUG", "True") == "True"
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
