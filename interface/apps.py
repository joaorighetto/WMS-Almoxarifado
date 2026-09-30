"""App `interface` — componentes de interface compartilhados entre apps.

Consolidação de UX (Fase A): parciais, template tags e composição visual
usados por mais de um app (`catalogo`, `fornecedores`, `estoque`) vivem
aqui, em vez de ficarem duplicados ou "emprestados" de um app de domínio.
Este app não contém regra de domínio, model nem view — só apresentação.
"""

from django.apps import AppConfig


class InterfaceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "interface"
