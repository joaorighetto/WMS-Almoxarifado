import os

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "test-secret-key-not-for-production")
ALLOWED_HOSTS = ["*"]
