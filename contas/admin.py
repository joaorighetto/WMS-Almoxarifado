from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms.models import BaseInlineFormSet

from .models import Papel, PapelUsuario, Setor, User


class ContaCriacaoForm(UserCreationForm):
    """Form de criação de `User` no Admin. `UserCreationForm` nativo pressupõe
    o `User` padrão do Django (campo `username`); aqui ele é restrito aos
    campos reais de `contas.User`. A senha continua sendo definida via
    `set_password()` pelo `save()` herdado — nunca gravada crua.

    Não sobrescreve `save()` para conceder `ROLE-REQUESTER`: o Django Admin
    sempre chama `form.save(commit=False)` internamente
    (`ModelAdmin.save_form`), então qualquer lógica de concessão de papel
    aqui seria código morto no fluxo real do Admin. A concessão fica em
    `UserAdmin.save_related`, o ponto real de integração onde o Admin
    persiste o objeto e seus inlines (`FR-016a`)."""

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


class PapelUsuarioInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        for form in self.forms:
            if not form.cleaned_data or not self._should_delete_form(form):
                continue
            atribuicao = form.instance
            try:
                atribuicao.exigir_papel_removivel(atribuicao.usuario_id, atribuicao.papel)
            except ValidationError as exc:
                raise ValidationError(exc.messages) from exc


class PapelUsuarioInline(admin.TabularInline):
    """Atribuição de papéis manuais sempre explícita: nenhuma linha é
    pré-preenchida (`extra = 0`) — o inline em si nunca sugere ou pré-marca um
    `Papel`. A única concessão automática do Admin é o `ROLE-REQUESTER`
    mínimo, feita fora deste inline por `UserAdmin.save_related` (`FR-016a`),
    e apenas na criação de contas não-superusuário."""

    model = PapelUsuario
    formset = PapelUsuarioInlineFormSet
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

    def get_inlines(self, request, obj=None):
        # Contas técnicas nunca exibem o editor de papéis de negócio. No POST
        # de criação, ``obj`` ainda é None; o valor validado será persistido pelo
        # form principal, e ocultar o inline impede que uma submissão forjada
        # grave ROLE-* no mesmo fluxo.
        valor_superusuario = request.POST.get("is_superuser", "").lower()
        superusuario_no_post = (
            obj is None
            and request.method == "POST"
            and valor_superusuario in {"1", "true", "on", "yes"}
        )
        if (obj is not None and obj.is_superuser) or superusuario_no_post:
            return []
        return super().get_inlines(request, obj)

    def save_related(self, request, form, formsets, change):
        """Concede `ROLE-REQUESTER` junto com a conta nova (`FR-016a`).

        O Admin é o segundo caminho suportado de criação de identidade de
        negócio (o outro é `User.objects.create_user`), e a matriz canônica
        exige que a concessão seja explícita e persistida — nunca inferida.
        `ModelAdmin.save_form` sempre chama `form.save(commit=False)`, então
        não é no form que o Admin de fato persiste papéis — é aqui.

        Roda depois de `super()` (que salva o inline `PapelUsuarioInline`) de
        propósito: um administrador pode conceder `ROLE-REQUESTER`
        explicitamente pelo próprio inline ao criar a conta, e nesse caso
        `get_or_create` apenas confirma a linha já existente, sem duplicar
        (`papelusuario_unico_usuario_papel`). Rodar antes duplicaria e
        quebraria a constraint quando o inline também grava a mesma linha.

        Só concede na criação (`not change`): conta e papel mínimo nascem
        juntos ou não nascem (`FR-023`); alterar uma conta existente não
        deve re-conceder nem duplicar o papel mínimo.

        Nunca concede quando `is_superuser=True`: a conta técnica de
        superusuário do Django não é identidade de negócio e não deve
        receber `ROLE-REQUESTER` nem nenhum outro papel
        (`permissions-matrix.md`, regra 8; `FR-016a`), o mesmo padrão já
        seguido por `UserManager.create_superuser` para o outro caminho de
        criação suportado.
        """
        with transaction.atomic():
            super().save_related(request, form, formsets, change)
            if not change and not form.instance.is_superuser:
                PapelUsuario.objects.get_or_create(usuario=form.instance, papel=Papel.REQUISITANTE)


@admin.register(Setor)
class SetorAdmin(admin.ModelAdmin):
    list_display = ["nome", "ativo"]


@admin.register(PapelUsuario)
class PapelUsuarioAdmin(admin.ModelAdmin):
    list_display = ["usuario", "papel"]
    list_filter = ["papel"]
    autocomplete_fields = ["usuario"]

    def has_delete_permission(self, request, obj=None):
        if (
            obj is not None
            and obj.papel == Papel.REQUISITANTE
            and obj.usuario.is_active
            and not obj.usuario.is_superuser
        ):
            return False
        return super().has_delete_permission(request, obj)
