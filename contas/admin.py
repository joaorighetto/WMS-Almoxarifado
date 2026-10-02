"""Django Admin de `contas`: consulta técnica, somente leitura (research R6 da 005).

Toda escrita organizacional é feita por `contas.organizacao`, que valida o estado final e
registra o evento (FR-046). O Admin não reproduziria prévia, revisão, substituição atômica,
senha provisória nem eventos; e a barreira de escrita de `contas.models` recusaria a
gravação de qualquer jeito. Por isso nenhum model organizacional pode ser adicionado,
alterado ou excluído por aqui, nem por POST direto: as páginas seguem consultáveis pela
conta técnica. Correções técnicas de emergência: shell chamando as operações, com o
superusuário técnico como autor.
"""

from django.contrib import admin

from .models import EventoOrganizacional, PapelUsuario, Setor, User


class SomenteLeituraMixin:
    def has_add_permission(self, request, *args, **kwargs):
        return False

    def has_change_permission(self, request, *args, **kwargs):
        return False

    def has_delete_permission(self, request, *args, **kwargs):
        return False


class PapelUsuarioInline(SomenteLeituraMixin, admin.TabularInline):
    model = PapelUsuario
    extra = 0
    can_delete = False


@admin.register(User)
class UserAdmin(SomenteLeituraMixin, admin.ModelAdmin):
    list_display = ("matricula", "nome", "setor", "is_active", "is_staff", "is_superuser")
    list_filter = ("is_active", "is_staff", "is_superuser", "setor")
    search_fields = ("matricula", "nome")
    ordering = ("matricula",)
    # O hash da senha não é exibido: nenhum campo de credencial entra na consulta.
    fields = (
        "matricula",
        "nome",
        "setor",
        "is_active",
        "is_staff",
        "is_superuser",
        "senha_provisoria_em",
        "last_login",
    )
    inlines = [PapelUsuarioInline]

    def get_inlines(self, request, obj=None):
        # Conta técnica não tem papéis de negócio: sem o bloco de papéis.
        if obj is not None and obj.is_superuser:
            return []
        return super().get_inlines(request, obj)


@admin.register(Setor)
class SetorAdmin(SomenteLeituraMixin, admin.ModelAdmin):
    list_display = ("nome", "ativo", "almoxarifado", "ativado_em")
    list_filter = ("ativo", "almoxarifado")
    search_fields = ("nome",)


@admin.register(PapelUsuario)
class PapelUsuarioAdmin(SomenteLeituraMixin, admin.ModelAdmin):
    list_display = ("usuario", "papel")
    list_filter = ("papel",)
    list_select_related = ("usuario",)


@admin.register(EventoOrganizacional)
class EventoOrganizacionalAdmin(SomenteLeituraMixin, admin.ModelAdmin):
    list_display = ("momento", "tipo", "autor", "usuario", "setor")
    list_filter = ("tipo",)
    list_select_related = ("autor", "usuario", "setor")
    date_hierarchy = "momento"
