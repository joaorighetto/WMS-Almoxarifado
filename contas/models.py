from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models


class Setor(models.Model):
    """Setor organizacional ao qual todo usuário pertence (`INV-ORG-001`).

    Modelo mínimo: esta feature não gerencia setores (criação/edição/inativação
    de setor pertence à futura `PERM-SECTOR-MANAGE`).
    """

    nome = models.CharField(blank=False)
    ativo = models.BooleanField(default=True)

    def __str__(self):
        return self.nome


class UserManager(BaseUserManager):
    """Manager de `User`, seguindo o padrão documentado do Django para modelo
    de usuário customizado com `USERNAME_FIELD` diferente de `username`."""

    use_in_migrations = True

    def _criar_usuario(self, matricula, password, setor, **extra_fields):
        if not matricula:
            raise ValueError("A matrícula é obrigatória.")
        if setor is None:
            raise ValueError("O setor é obrigatório.")
        usuario = self.model(matricula=matricula, **extra_fields)
        # `createsuperuser` entrega a PK do setor, não a instância: para um campo de
        # `REQUIRED_FIELDS`, o comando aplica `field.clean()`, que numa ForeignKey
        # devolve o valor da chave. Atribuir isso a `usuario.setor` seria rejeitado
        # pelo descriptor do ORM, quebrando o bootstrap descrito em quickstart.md §1.2.
        # Uma PK inexistente continua sendo recusada pela FK no banco (INV-ORG-001
        # protegida também em persistência, Constitution III).
        if isinstance(setor, Setor):
            usuario.setor = setor
        else:
            usuario.setor_id = setor
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, matricula, password=None, setor=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._criar_usuario(matricula, password, setor, **extra_fields)

    def create_superuser(self, matricula, password=None, setor=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superusuário precisa ter is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superusuário precisa ter is_superuser=True.")

        return self._criar_usuario(matricula, password, setor, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Usuário autenticável do WMS. Identificado por `matricula` (identificador
    opaco de negócio) — nunca por nome de exibição ou e-mail."""

    matricula = models.CharField(max_length=32, unique=True, verbose_name="matrícula")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    setor = models.ForeignKey("contas.Setor", on_delete=models.PROTECT)

    objects = UserManager()

    USERNAME_FIELD = "matricula"
    REQUIRED_FIELDS = ["setor"]

    def __str__(self):
        return self.matricula

    def tem_papel(self, *codigos: str) -> bool:
        """Retorna True se o usuário possui, explicitamente, algum dos papéis
        informados. Não infere nem herda papel algum
        (`docs/domain/permissions-matrix.md`, regra 3)."""
        return self.papeis.filter(papel__in=codigos).exists()


class Papel(models.TextChoices):
    """Catálogo fechado de papéis de negócio — espelha, em código,
    `docs/domain/permissions-matrix.md` → "Catálogo de papéis". Não é editável
    via administração como dado solto."""

    REQUISITANTE = "ROLE-REQUESTER", "Requisitante"
    AUXILIAR_SETOR = "ROLE-SECTOR-ASSISTANT", "Auxiliar de setor"
    CHEFE_SETOR = "ROLE-SECTOR-HEAD", "Chefe de setor"
    FUNCIONARIO_ALMOXARIFADO = "ROLE-WAREHOUSE-STAFF", "Funcionário do almoxarifado"
    CHEFE_ALMOXARIFADO = "ROLE-WAREHOUSE-HEAD", "Chefe do almoxarifado"
    AUDITOR = "ROLE-AUDITOR", "Gestor/auditor"
    ADMINISTRADOR_SISTEMA = "ROLE-SYSTEM-ADMIN", "Administrador de sistema"


class PapelUsuario(models.Model):
    """Atribuição explícita de um papel a um usuário — a única forma de um
    usuário "ter" um papel. Cada linha é uma concessão independente, sem
    herança implícita entre papéis (`docs/domain/permissions-matrix.md`, regra 3)."""

    usuario = models.ForeignKey("contas.User", related_name="papeis", on_delete=models.CASCADE)
    papel = models.CharField(max_length=32, choices=Papel.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "papel"],
                name="papelusuario_unico_usuario_papel",
            )
        ]

    def __str__(self):
        return f"{self.usuario_id} — {self.papel}"
