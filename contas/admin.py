from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import PapelUsuario, Setor, User


class ContaCriacaoForm(UserCreationForm):
    """Form de criação de `User` no Admin. `UserCreationForm` nativo pressupõe
    o `User` padrão do Django (campo `username`); aqui ele é restrito aos
    campos reais de `contas.User`. A senha continua sendo definida via
    `set_password()` pelo `save()` herdado — nunca gravada crua."""

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("matricula", "setor", "is_active", "is_staff", "is_superuser")


class ContaAlteracaoForm(UserChangeForm):
    """Form de alteração de `User` no Admin, restrito aos campos reais de
    `contas.User` (o `UserChangeForm` nativo, por padrão, usa `fields =
    "__all__"` do `User` padrão do Django)."""

    class Meta(UserChangeForm.Meta):
        model = User
        fields = (
            "matricula",
            "password",
            "setor",
            "is_active",
            "is_staff",
            "is_superuser",
        )


class PapelUsuarioInline(admin.TabularInline):
    """Atribuição de papéis sempre explícita: nenhuma linha é pré-preenchida
    (`extra = 0`) — o Admin nunca sugere nem concede um `Papel` por conta
    própria."""

    model = PapelUsuario
    extra = 0


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    add_form = ContaCriacaoForm
    form = ContaAlteracaoForm
    model = User

    list_display = ("matricula", "setor", "is_active", "is_staff", "is_superuser")
    list_filter = ("is_active", "is_staff", "is_superuser", "setor")
    search_fields = ("matricula",)
    ordering = ("matricula",)
    filter_horizontal = ()

    fieldsets = (
        (None, {"fields": ("matricula", "password")}),
        ("Organização", {"fields": ("setor",)}),
        ("Permissões", {"fields": ("is_active", "is_staff", "is_superuser")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "matricula",
                    "setor",
                    "password1",
                    "password2",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )

    inlines = [PapelUsuarioInline]


@admin.register(Setor)
class SetorAdmin(admin.ModelAdmin):
    list_display = ["nome", "ativo"]


@admin.register(PapelUsuario)
class PapelUsuarioAdmin(admin.ModelAdmin):
    list_display = ["usuario", "papel"]
    list_filter = ["papel"]
    autocomplete_fields = ["usuario"]
