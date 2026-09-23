from django.apps import AppConfig
from django.db import connections
from django.db.models.signals import pre_migrate


def criar_extensao_pg_trgm(using, **kwargs):
    """Garante a extensão exigida pelo GinIndex `gin_trgm_ops` de `Material`.

    Sem migrations (ver MIGRATION_MODULES em config.settings.base), não há
    `TrigramExtension()` para criá-la; `pre_migrate` roda antes do syncdb,
    tanto no banco local quanto no banco de testes.
    """
    with connections[using].cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


class CatalogoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "catalogo"

    def ready(self):
        pre_migrate.connect(criar_extensao_pg_trgm, sender=self)
