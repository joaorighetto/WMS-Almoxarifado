from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models, transaction


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


def chefes_ativos(setor_id, excluir_usuario_id=None):
    """Chefes ativos de um setor (`INV-ORG-002`).

    A chefia é derivada, nunca uma coluna própria: é o usuário ativo cujo
    `setor` é este e que possui `ROLE-SECTOR-HEAD` explicitamente atribuído.
    Como `User.setor` é único (`INV-ORG-001`), um chefe jamais responde por
    mais de um setor — `INV-ORG-003` é estrutural, sem regra adicional.

    `excluir_usuario_id` permite avaliar o estado *resultante* de uma operação
    ainda não persistida (ex.: "e se este chefe sair deste setor?").
    """
    consulta = User.objects.filter(
        setor_id=setor_id,
        is_active=True,
        papeis__papel=Papel.CHEFE_SETOR,
    )
    if excluir_usuario_id is not None:
        consulta = consulta.exclude(pk=excluir_usuario_id)
    return consulta


def _exigir_chefia_preservada(setor_id, excluir_usuario_id=None):
    """Recusa a operação se ela deixaria um setor ATIVO sem chefe ativo.

    Setor inativo não está sob `INV-ORG-002` — é exatamente por isso que um
    setor nasce inativo (`FR-019`): provisionar deixa de exigir um chefe que
    ainda não existe.
    """
    if setor_id is None:
        return
    if not Setor.objects.filter(pk=setor_id, ativo=True).exists():
        return
    if not chefes_ativos(setor_id, excluir_usuario_id=excluir_usuario_id).exists():
        raise ValidationError(
            "Operação recusada: deixaria o setor ativo sem chefe ativo "
            "(INV-ORG-002). Desative o setor ou designe outro chefe antes."
        )


class Setor(models.Model):
    """Setor organizacional ao qual todo usuário pertence (`INV-ORG-001`).

    Esta feature não oferece administração de setores como funcionalidade de
    produto (`PERM-SECTOR-MANAGE` segue pendente), mas seu caminho de bootstrap
    escreve em setor/usuário/papel — e por isso está sujeito a `INV-ORG-002`
    como qualquer outro caminho de escrita (`research.md` R4, revisão 3).
    """

    nome = models.CharField(blank=False)
    # Nasce INATIVO (`FR-019`): criar um setor nunca produz, por si só, um setor
    # ativo sem chefe ativo. A ativação é um passo deliberado, validado abaixo.
    ativo = models.BooleanField(default=False)

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        # `FR-020`: ativar exige exatamente um chefe ativo do próprio setor.
        # Verificado a cada save de setor ativo, não só na transição, para que
        # nenhum caminho de escrita (Admin, ORM, shell) escape da invariante.
        if self.ativo:
            with transaction.atomic():
                if self.pk is None:
                    raise ValidationError(
                        "Um setor não pode ser criado já ativo: não há como ter um chefe "
                        "ativo antes de o setor existir (INV-ORG-002). Crie o setor, "
                        "designe o chefe e só então ative."
                    )
                total = chefes_ativos(self.pk).count()
                if total != 1:
                    raise ValidationError(
                        f"Setor ativo exige exatamente um chefe ativo do próprio setor "
                        f"(INV-ORG-002); encontrados: {total}."
                    )
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)


class UserManager(BaseUserManager):
    """Manager de `User`, seguindo o padrão documentado do Django para modelo
    de usuário customizado com `USERNAME_FIELD` diferente de `username`."""

    use_in_migrations = True

    def _criar_usuario(self, matricula, password, setor, conceder_papel_minimo, **extra_fields):
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
        # `FR-016a`/`FR-023`: conta e papel mínimo nascem juntos ou não nascem.
        with transaction.atomic(using=self._db):
            usuario.save(using=self._db)
            if conceder_papel_minimo:
                PapelUsuario.objects.using(self._db).create(
                    usuario=usuario, papel=Papel.REQUISITANTE
                )
        return usuario

    def create_user(self, matricula, password=None, setor=None, **extra_fields):
        """Cria uma identidade de NEGÓCIO.

        Recebe `ROLE-REQUESTER` como concessão explícita e persistida
        (`FR-016a`; `permissions-matrix.md`, Notas de composição) — nunca
        inferida em tempo de consulta a partir de `is_active`.
        """
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._criar_usuario(
            matricula, password, setor, conceder_papel_minimo=True, **extra_fields
        )

    def create_superuser(self, matricula, password=None, setor=None, **extra_fields):
        """Cria a conta TÉCNICA de manutenção do Django.

        Não é identidade de negócio: não recebe `ROLE-REQUESTER` nem nenhum
        outro `ROLE-*` (`permissions-matrix.md`, regras 7-8). Sem papel de
        negócio, não possui nenhuma capability de domínio.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superusuário precisa ter is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superusuário precisa ter is_superuser=True.")

        return self._criar_usuario(
            matricula, password, setor, conceder_papel_minimo=False, **extra_fields
        )


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

    def save(self, *args, **kwargs):
        if self.pk is None:
            return super().save(*args, **kwargs)

        # `FR-021`/`FR-023`: desativar o chefe ou transferi-lo de setor não pode
        # deixar um setor ativo sem chefe. Avaliado dentro da transação, sobre o
        # estado anterior lido do banco.
        with transaction.atomic():
            anterior = (
                User.objects.select_for_update()
                .filter(pk=self.pk)
                .values("setor_id", "is_active")
                .first()
            )
            if anterior is None:
                return super().save(*args, **kwargs)

            saiu_do_setor = anterior["setor_id"] != self.setor_id
            foi_desativado = anterior["is_active"] and not self.is_active

            if (saiu_do_setor or foi_desativado) and self.tem_papel(Papel.CHEFE_SETOR):
                _exigir_chefia_preservada(anterior["setor_id"], excluir_usuario_id=self.pk)

            # `FR-022`: entrar (ou voltar a ficar ativo) como chefe num setor ativo
            # que já tem chefe criaria um segundo chefe.
            entrou_no_setor = saiu_do_setor
            foi_reativado = not anterior["is_active"] and self.is_active
            if (entrou_no_setor or foi_reativado) and self.is_active:
                if self.tem_papel(Papel.CHEFE_SETOR) and chefes_ativos(
                    self.setor_id, excluir_usuario_id=self.pk
                ).exists():
                    raise ValidationError(
                        "Operação recusada: o setor já possui um chefe ativo "
                        "(INV-ORG-002)."
                    )

            return super().save(*args, **kwargs)


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

    def save(self, *args, **kwargs):
        # `FR-022`: um setor ativo não pode ganhar um segundo chefe ativo.
        if self.pk is None and self.papel == Papel.CHEFE_SETOR:
            with transaction.atomic():
                usuario = User.objects.select_related("setor").get(pk=self.usuario_id)
                if usuario.is_active and chefes_ativos(
                    usuario.setor_id, excluir_usuario_id=usuario.pk
                ).exists():
                    raise ValidationError(
                        "Operação recusada: o setor já possui um chefe ativo "
                        "(INV-ORG-002)."
                    )
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # `FR-021`: remover o papel do único chefe de um setor ativo o deixaria
        # sem chefia.
        if self.papel == Papel.CHEFE_SETOR:
            with transaction.atomic():
                usuario = User.objects.filter(pk=self.usuario_id).first()
                if usuario is not None and usuario.is_active:
                    _exigir_chefia_preservada(
                        usuario.setor_id, excluir_usuario_id=usuario.pk
                    )
                return super().delete(*args, **kwargs)
        return super().delete(*args, **kwargs)
