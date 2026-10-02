from contextvars import ContextVar

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.db.models.functions import Length, Lower, Trim
from django.db.models.signals import pre_save
from django.utils import timezone

from config.texto import normalizar_para_busca


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


# ---------------------------------------------------------------------------
# Barreira de escrita (research R4 da 005)
# ---------------------------------------------------------------------------
#
# Só as operações de `contas.organizacao` escrevem dados organizacionais: é
# `contas.organizacao._operacao()` que liga este marcador (e mais ninguém).
# Fora dele, `save()`/`delete()` e os atalhos de `QuerySet` sobre `Setor`,
# `PapelUsuario` e os campos organizacionais de `User` levantam
# `ValidationError` ANTES de qualquer escrita (e antes do `Collector` do
# Django, que responderia `ProtectedError`). As regras de integridade em si
# não moram aqui: são `validar_organizacao` (R3) e o trigger adiado (R5).
# Caminhos que não chamam `save()`/`QuerySet` do manager padrão também passam
# pela barreira: `Meta.base_manager_name = "objects"` faz os gerenciadores
# reversos (`setor.user_set.add`, `usuario.papeis.add`, que atualizam por
# `_base_manager`) usarem os QuerySets guardados abaixo, e um `pre_save` recusa
# a carga bruta (`raw=True`) de `loaddata`/`deserialize`. O marcador vive neste
# módulo, e não em `organizacao`, só para evitar import
# circular.

_OPERACAO_EM_CURSO = ContextVar("contas_operacao_organizacional", default=False)


def operacao_em_curso():
    return _OPERACAO_EM_CURSO.get()


def _exigir_operacao(descricao):
    if not _OPERACAO_EM_CURSO.get():
        raise ValidationError(
            f"{descricao} só é permitido pelas operações de contas.organizacao "
            "(escrita organizacional protegida, FR-046)."
        )


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


class SetorQuerySet(models.QuerySet):
    """Fecha os atalhos do ORM que não chamam ``Setor.save()``/``delete()``."""

    def update(self, **kwargs):
        _exigir_operacao("Alterar setores")
        return super().update(**kwargs)

    def bulk_create(self, objs, **kwargs):
        _exigir_operacao("Criar setores em lote")
        return super().bulk_create(objs, **kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        _exigir_operacao("Alterar setores em lote")
        return super().bulk_update(objs, fields, **kwargs)

    def delete(self):
        _exigir_operacao("Excluir setores")
        return super().delete()


class Setor(models.Model):
    """Setor organizacional ao qual todo usuário pertence (`INV-ORG-001`).

    Nasce inativo (FR-019 da 002); a ativação é uma operação deliberada de
    `contas.organizacao`, que exige exatamente um chefe ativo (`INV-ORG-002`).
    A designação de Almoxarifado nasce com o setor e não muda (`INV-ORG-004`,
    trigger de banco); `ativado_em` registra a primeira ativação (FR-030).
    """

    nome = models.CharField(max_length=100)
    ativo = models.BooleanField(default=False)
    almoxarifado = models.BooleanField(default=False)
    ativado_em = models.DateTimeField(null=True, blank=True)

    objects = SetorQuerySet.as_manager()

    class Meta:
        # `_base_manager` é o que os gerenciadores reversos (`setor.user_set.add`)
        # usam para atualizar; apontá-lo para `objects` mantém a barreira de escrita.
        base_manager_name = "objects"
        constraints = [
            models.UniqueConstraint(Lower(Trim("nome")), name="setor_nome_unico_normalizado"),
            models.CheckConstraint(
                condition=models.lookups.GreaterThan(Length(Trim("nome")), 0),
                name="setor_nome_nao_vazio",
            ),
            models.UniqueConstraint(
                fields=["almoxarifado"],
                condition=Q(almoxarifado=True),
                name="setor_um_unico_almoxarifado",
            ),
            models.CheckConstraint(
                condition=Q(ativo=False) | Q(ativado_em__isnull=False),
                name="setor_ativo_tem_ativacao",
            ),
            models.CheckConstraint(
                condition=Q(almoxarifado=False) | Q(ativado_em__isnull=True) | Q(ativo=True),
                name="setor_almoxarifado_nao_desativado",
            ),
        ]

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        _exigir_operacao("Gravar um setor")
        self.nome = (self.nome or "").strip()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        _exigir_operacao("Excluir um setor")
        return super().delete(*args, **kwargs)


class UserQuerySet(models.QuerySet):
    """Fecha os atalhos do ORM que não chamam ``User.save()``/``delete()``."""

    CAMPOS_ORGANIZACIONAIS = frozenset(
        {
            "matricula",
            "nome",
            "nome_busca",
            "setor",
            "setor_id",
            "is_active",
            "is_superuser",
            "senha_provisoria_em",
        }
    )

    def bulk_create(self, objs, **kwargs):
        objs = list(objs)
        if any(not obj.is_superuser for obj in objs):
            _exigir_operacao("Criar contas em lote")
        return super().bulk_create(objs, **kwargs)

    def update(self, **kwargs):
        if self.CAMPOS_ORGANIZACIONAIS.intersection(kwargs):
            _exigir_operacao("Alterar dados organizacionais de contas")
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        if self.CAMPOS_ORGANIZACIONAIS.intersection(fields):
            _exigir_operacao("Alterar dados organizacionais de contas em lote")
        return super().bulk_update(objs, fields, **kwargs)

    def delete(self):
        _exigir_operacao("Excluir contas")
        return super().delete()


class UserManager(BaseUserManager.from_queryset(UserQuerySet)):
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
        """Cria uma identidade de NEGÓCIO, com `ROLE-REQUESTER` explícito e
        persistido (`FR-016a`; `permissions-matrix.md`, Notas de composição).

        Só funciona dentro de uma operação de `contas.organizacao` (barreira de
        escrita, research R4 da 005): a criação de identidade de negócio é
        feita pelas operações e pelo provisionamento, que validam o estado
        final e registram o evento.
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
        negócio, não possui nenhuma capability de domínio. Fica fora da
        barreira de escrita. Sem `nome`, usa a matrícula (a coluna é
        obrigatória, FR-006).
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("nome", matricula)

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
    nome = models.CharField(max_length=150)
    # `normalizar_para_busca(nome)`, gravado junto com `nome` (research R14).
    nome_busca = models.CharField(max_length=150, editable=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    setor = models.ForeignKey("contas.Setor", on_delete=models.PROTECT)
    # Preenchido ao gerar senha provisória; nulo depois que o usuário define a própria
    # (research R8 a R10).
    senha_provisoria_em = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "matricula"
    REQUIRED_FIELDS = ["setor", "nome"]

    class Meta:
        base_manager_name = "objects"  # ver `Setor.Meta`
        constraints = [
            models.CheckConstraint(condition=~Q(nome=""), name="user_nome_nao_vazio"),
            models.CheckConstraint(condition=~Q(matricula=""), name="user_matricula_nao_vazia"),
        ]

    def __str__(self):
        return self.matricula

    def tem_papel(self, *codigos: str) -> bool:
        """Retorna True se o usuário possui, explicitamente, algum dos papéis
        informados. Não infere nem herda papel algum
        (`docs/domain/permissions-matrix.md`, regra 3)."""
        return self.papeis.filter(papel__in=codigos).exists()

    # Campos comparados com o banco num `save()` completo fora de operação.
    CAMPOS_COMPARADOS = (
        "matricula",
        "nome",
        "setor_id",
        "is_active",
        "is_superuser",
        "senha_provisoria_em",
    )

    def _exigir_escrita_organizacional_permitida(self, update_fields):
        """Barreira de `save()` fora de operação (research R4).

        Livres: a conta técnica (criação e atualização, por `create_superuser`
        e `changepassword`) e qualquer `save()` que não altere campo
        organizacional (`last_login`, rehash de senha). Recusados: criar
        identidade de negócio e alterar `matricula`, `nome`, `setor`,
        `is_active`, `is_superuser` ou `senha_provisoria_em`.
        """
        if _OPERACAO_EM_CURSO.get():
            return
        if self.pk is None:
            if not self.is_superuser:
                _exigir_operacao("Criar uma identidade de negócio")
            return

        if update_fields is not None and not UserQuerySet.CAMPOS_ORGANIZACIONAIS.intersection(
            update_fields
        ):
            return

        atual = User.objects.filter(pk=self.pk).values(*self.CAMPOS_COMPARADOS).first()
        if atual is None:
            if not self.is_superuser:
                _exigir_operacao("Criar uma identidade de negócio")
            return
        if self.is_superuser and atual["is_superuser"]:
            return
        if update_fields is None and all(
            atual[campo] == getattr(self, campo) for campo in self.CAMPOS_COMPARADOS
        ):
            # Cópia idêntica ao banco no que é organizacional: nada a proteger.
            return
        _exigir_operacao("Alterar dados organizacionais de uma conta")

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        self._exigir_escrita_organizacional_permitida(update_fields)
        if update_fields is None or "nome" in update_fields:
            self.nome = (self.nome or "").strip()
            self.nome_busca = normalizar_para_busca(self.nome)
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "nome_busca"}
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        _exigir_operacao("Excluir uma conta")
        return super().delete(*args, **kwargs)


class PapelUsuarioQuerySet(models.QuerySet):
    """Fecha os atalhos do ORM que não chamam ``PapelUsuario.save()``/``delete()``."""

    def update(self, **kwargs):
        _exigir_operacao("Alterar papéis")
        return super().update(**kwargs)

    def bulk_create(self, objs, **kwargs):
        _exigir_operacao("Criar papéis em lote")
        return super().bulk_create(objs, **kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        _exigir_operacao("Alterar papéis em lote")
        return super().bulk_update(objs, fields, **kwargs)

    def delete(self):
        _exigir_operacao("Remover papéis")
        return super().delete()


class PapelUsuario(models.Model):
    """Atribuição explícita de um papel a um usuário — a única forma de um
    usuário "ter" um papel. Cada linha é uma concessão independente, sem
    herança implícita entre papéis (`docs/domain/permissions-matrix.md`, regra 3).

    Sem regra própria em `save()`/`delete()`: a barreira de escrita (R4) só
    admite escrita dentro das operações organizacionais, que validam o estado
    final (R3); o trigger adiado (R5) é a última defesa.
    """

    usuario = models.ForeignKey("contas.User", related_name="papeis", on_delete=models.CASCADE)
    papel = models.CharField(max_length=32, choices=Papel.choices)

    objects = PapelUsuarioQuerySet.as_manager()

    class Meta:
        base_manager_name = "objects"  # ver `Setor.Meta`
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "papel"],
                name="papelusuario_unico_usuario_papel",
            )
        ]

    def __str__(self):
        return f"{self.usuario_id} — {self.papel}"

    def save(self, *args, **kwargs):
        _exigir_operacao("Gravar um papel")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        _exigir_operacao("Remover um papel")
        return super().delete(*args, **kwargs)


def _recusar_carga_bruta(sender, raw=False, **kwargs):
    """`loaddata` e `serializers.deserialize(...).save()` gravam por
    `save_base(raw=True)`, sem passar por `save()`: o `pre_save` é o único ponto
    por onde essa carga passa (FR-046)."""
    if raw:
        _exigir_operacao(f"Carregar {sender._meta.verbose_name_plural} por carga bruta")


for _modelo in (Setor, User, PapelUsuario):
    pre_save.connect(
        _recusar_carga_bruta, sender=_modelo, dispatch_uid=f"barreira_{_modelo.__name__}"
    )


class TipoEvento(models.TextChoices):
    """Lista fechada dos eventos organizacionais (`data-model.md`)."""

    USUARIO_CADASTRADO = "USUARIO_CADASTRADO", "Usuário cadastrado"
    USUARIO_EDITADO = "USUARIO_EDITADO", "Usuário editado"
    PAPEIS_ALTERADOS = "PAPEIS_ALTERADOS", "Papéis alterados"
    USUARIO_TRANSFERIDO = "USUARIO_TRANSFERIDO", "Usuário transferido"
    CHEFIA_DESIGNADA = "CHEFIA_DESIGNADA", "Chefia designada"
    CHEFIA_RETIRADA = "CHEFIA_RETIRADA", "Chefia retirada"
    CHEFIA_SUBSTITUIDA = "CHEFIA_SUBSTITUIDA", "Chefia substituída"
    USUARIO_DESATIVADO = "USUARIO_DESATIVADO", "Usuário desativado"
    USUARIO_REATIVADO = "USUARIO_REATIVADO", "Usuário reativado"
    SETOR_CRIADO = "SETOR_CRIADO", "Setor criado"
    SETOR_RENOMEADO = "SETOR_RENOMEADO", "Setor renomeado"
    SETOR_ATIVADO = "SETOR_ATIVADO", "Setor ativado"
    SETOR_DESATIVADO = "SETOR_DESATIVADO", "Setor desativado"
    SENHA_PROVISORIA_GERADA = "SENHA_PROVISORIA_GERADA", "Senha provisória gerada"
    SENHA_DEFINIDA = "SENHA_DEFINIDA", "Senha definida"


class EventoOrganizacional(models.Model):
    """Histórico organizacional, só de acréscimo (FR-040 a FR-042, research R7).

    Um evento por operação efetivada, gravado na mesma transação. Imutável por
    trigger de banco (R5). `dados` guarda anterior/novo e detalhes do tipo —
    nunca senha. `autor` nulo só no provisionamento técnico (R15).
    """

    momento = models.DateTimeField(default=timezone.now)
    autor = models.ForeignKey("contas.User", null=True, on_delete=models.PROTECT, related_name="+")
    tipo = models.CharField(max_length=32, choices=TipoEvento.choices)
    usuario = models.ForeignKey(
        "contas.User", null=True, on_delete=models.PROTECT, related_name="eventos_como_alvo"
    )
    usuario_relacionado = models.ForeignKey(
        "contas.User", null=True, on_delete=models.PROTECT, related_name="eventos_como_relacionado"
    )
    setor = models.ForeignKey(
        "contas.Setor", null=True, on_delete=models.PROTECT, related_name="eventos_como_alvo"
    )
    setor_relacionado = models.ForeignKey(
        "contas.Setor",
        null=True,
        on_delete=models.PROTECT,
        related_name="eventos_como_relacionado",
    )
    dados = models.JSONField(default=dict)
    justificativa = models.TextField(blank=True, default="")
    # Cadastro e redefinição: repetir o POST com a mesma chave não repete a operação
    # (research R8).
    chave_confirmacao = models.UUIDField(null=True, unique=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(usuario__isnull=False) | Q(setor__isnull=False),
                name="evento_organizacional_tem_alvo",
            ),
            models.CheckConstraint(
                condition=Q(tipo__in=TipoEvento.values),
                name="evento_organizacional_tipo_fechado",
            ),
        ]
        indexes = [
            models.Index(fields=["usuario", "momento"], name="evento_org_usuario_momento"),
            models.Index(
                fields=["usuario_relacionado", "momento"], name="evento_org_usurel_momento"
            ),
            models.Index(fields=["setor", "momento"], name="evento_org_setor_momento"),
            models.Index(fields=["setor_relacionado", "momento"], name="evento_org_setrel_momento"),
        ]

    def __str__(self):
        return f"{self.tipo} em {self.momento:%Y-%m-%d %H:%M}"
