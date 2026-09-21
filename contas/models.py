from contextlib import contextmanager

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

    Faz `select_for_update()` na própria linha do `Setor`: é o mesmo lock que
    `Setor.save()` adquire ao ativar um setor. Sem esse lock compartilhado, uma
    ativação de setor e uma desativação/remoção do único chefe podem cada uma
    ler o estado anterior da outra (setor ainda inativo; chefe ainda ativo) e
    ambas comitar, violando `INV-ORG-002` (condição de corrida).
    """
    if setor_id is None:
        return
    setor = Setor.objects.select_for_update().filter(pk=setor_id).first()
    if setor is None or not setor.ativo:
        return
    if not chefes_ativos(setor_id, excluir_usuario_id=excluir_usuario_id).exists():
        raise ValidationError(
            "Operação recusada: deixaria o setor ativo sem chefe ativo "
            "(INV-ORG-002). Desative o setor ou designe outro chefe antes."
        )


def _exigir_chefia_nao_duplicada(setor_id, excluir_usuario_id=None):
    """Recusa a operação se ela daria a um setor um segundo chefe ativo
    (`FR-022`). Mantém, intencionalmente, o comportamento anterior de não
    condicionar a checagem a `Setor.ativo` — a mesma checagem já feita antes
    desta correção.

    Faz o mesmo `select_for_update()` na linha do `Setor` que
    `_exigir_chefia_preservada` e `Setor.save()` — todas as mutações que
    podem afetar a chefia de um setor serializam sobre o mesmo lock.
    """
    if setor_id is None:
        return
    Setor.objects.select_for_update().filter(pk=setor_id).first()
    if chefes_ativos(setor_id, excluir_usuario_id=excluir_usuario_id).exists():
        raise ValidationError(
            "Operação recusada: o setor já possui um chefe ativo (INV-ORG-002)."
        )


class SetorQuerySet(models.QuerySet):
    """Impede que operações em lote contornem ``Setor.save()``."""

    def update(self, **kwargs):
        if "ativo" in kwargs:
            raise ValidationError(
                "Atualize o estado do setor por Setor.save(), que preserva INV-ORG-002."
            )
        return super().update(**kwargs)

    def bulk_create(self, objs, **kwargs):
        objs = list(objs)
        if any(obj.ativo for obj in objs):
            raise ValidationError(
                "Setores ativos não podem ser criados em lote; use Setor.save() "
                "para preservar INV-ORG-002."
            )
        return super().bulk_create(objs, **kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        if "ativo" in fields:
            raise ValidationError(
                "Atualize o estado do setor por Setor.save(), que preserva INV-ORG-002."
            )
        return super().bulk_update(objs, fields, **kwargs)


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

    objects = SetorQuerySet.as_manager()

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
                # Mesmo lock usado por `_exigir_chefia_preservada`/
                # `_exigir_chefia_nao_duplicada`: serializa esta ativação com
                # qualquer mutação concorrente de usuário/papel que poderia
                # alterar a contagem de chefes ativos deste setor, prevenindo
                # a condição de corrida entre ativar o setor e desativar (ou
                # remover) o seu único chefe.
                Setor.objects.select_for_update().filter(pk=self.pk).first()
                total = chefes_ativos(self.pk).count()
                if total != 1:
                    raise ValidationError(
                        f"Setor ativo exige exatamente um chefe ativo do próprio setor "
                        f"(INV-ORG-002); encontrados: {total}."
                    )
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)


class UserQuerySet(models.QuerySet):
    """Fecha os atalhos do ORM que não chamam ``User.save()``/``delete()``."""

    CAMPOS_ORGANIZACIONAIS = {"is_active", "is_superuser", "setor", "setor_id"}

    def create(self, **kwargs):
        raise ValidationError(
            "Crie contas por create_user() ou create_superuser(), que preservam "
            "a atribuição atômica dos papéis de negócio."
        )

    def bulk_create(self, objs, **kwargs):
        raise ValidationError(
            "Contas não podem ser criadas em lote; use create_user() ou create_superuser()."
        )

    def update(self, **kwargs):
        if self.CAMPOS_ORGANIZACIONAIS.intersection(kwargs):
            raise ValidationError(
                "Atualize is_active, is_superuser ou setor por User.save(), que preserva "
                "as invariantes de identidade e INV-ORG-002."
            )
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        if self.CAMPOS_ORGANIZACIONAIS.intersection(fields):
            raise ValidationError(
                "Atualize is_active, is_superuser ou setor por User.save(), que preserva "
                "as invariantes de identidade e INV-ORG-002."
            )
        return super().bulk_update(objs, fields, **kwargs)

    def delete(self):
        with transaction.atomic():
            total = 0
            detalhes = {}
            for usuario in self.order_by("pk"):
                removidos, por_modelo = usuario.delete()
                total += removidos
                for modelo, quantidade in por_modelo.items():
                    detalhes[modelo] = detalhes.get(modelo, 0) + quantidade
            return total, detalhes


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
            # Todas as escritas de identidade/papel seguem Usuário → Setor →
            # PapelUsuario. Travar o usuário primeiro estabiliza seu setor e
            # serializa reativação/promoção com concessão/remoção de papéis.
            # Setor.save() só trava o setor; nunca adquire lock de usuário.
            anterior = (
                User.objects.select_for_update()
                .filter(pk=self.pk)
                .values("setor_id", "is_active")
                .first()
            )
            if anterior is None:
                return super().save(*args, **kwargs)

            setores_para_travar = sorted(
                {sid for sid in (anterior["setor_id"], self.setor_id) if sid is not None}
            )
            for setor_id in setores_para_travar:
                Setor.objects.select_for_update().filter(pk=setor_id).first()

            if self.is_superuser and self.papeis.exists():
                raise ValidationError(
                    "Superusuário técnico não pode possuir papéis de negócio ROLE-*."
                )

            if (
                self.is_active
                and not self.is_superuser
                and not self.tem_papel(Papel.REQUISITANTE)
            ):
                raise ValidationError(
                    "Identidade de negócio ativa precisa possuir ROLE-REQUESTER."
                )

            saiu_do_setor = anterior["setor_id"] != self.setor_id
            foi_desativado = anterior["is_active"] and not self.is_active

            if (saiu_do_setor or foi_desativado) and self.tem_papel(Papel.CHEFE_SETOR):
                _exigir_chefia_preservada(anterior["setor_id"], excluir_usuario_id=self.pk)

            # `FR-022`: entrar (ou voltar a ficar ativo) como chefe num setor ativo
            # que já tem chefe criaria um segundo chefe.
            entrou_no_setor = saiu_do_setor
            foi_reativado = not anterior["is_active"] and self.is_active
            if (entrou_no_setor or foi_reativado) and self.is_active:
                if self.tem_papel(Papel.CHEFE_SETOR):
                    _exigir_chefia_nao_duplicada(self.setor_id, excluir_usuario_id=self.pk)

            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            atual = User.objects.select_for_update().filter(pk=self.pk).first()
            if atual is not None and atual.is_active and atual.tem_papel(Papel.CHEFE_SETOR):
                _exigir_chefia_preservada(atual.setor_id, excluir_usuario_id=atual.pk)
            return super().delete(*args, **kwargs)


class PapelUsuarioQuerySet(models.QuerySet):
    """Mantém as invariantes de papéis também nas operações em lote."""

    def update(self, **kwargs):
        if {"papel", "usuario", "usuario_id"}.intersection(kwargs):
            raise ValidationError(
                "Altere papel ou usuário por PapelUsuario.save(), que preserva as invariantes."
            )
        return super().update(**kwargs)

    def bulk_create(self, objs, **kwargs):
        objs = list(objs)
        if objs:
            raise ValidationError(
                "Papéis não podem ser criados em lote; use PapelUsuario.save() para preservar "
                "as invariantes."
            )
        return super().bulk_create(objs, **kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        if {"papel", "usuario", "usuario_id"}.intersection(fields):
            raise ValidationError(
                "Altere papel ou usuário por PapelUsuario.save(), que preserva as invariantes."
            )
        return super().bulk_update(objs, fields, **kwargs)

    def delete(self):
        with transaction.atomic():
            total = 0
            detalhes = {}
            for atribuicao in self.order_by("pk"):
                removidos, por_modelo = atribuicao.delete()
                total += removidos
                for modelo, quantidade in por_modelo.items():
                    detalhes[modelo] = detalhes.get(modelo, 0) + quantidade
            return total, detalhes


class _TitularAlteradoDuranteBloqueio(Exception):
    """Sinal interno para liberar os locks e reler uma atribuição reapontada."""


@contextmanager
def _bloquear_atribuicao(atribuicao_id, usuario_destino_id=None):
    """Lê o estado atual na ordem Usuário → Setor → PapelUsuario.

    O titular precisa ser descoberto antes de travar a atribuição. Se outra
    transação o trocar nessa janela, desfazemos o savepoint para liberar os
    locks antes de repetir, inclusive dentro da transação externa do Admin.
    Evita validar um usuário diferente daquele efetivamente alterado/excluído.
    """
    while True:
        try:
            with transaction.atomic():
                titular_id = (
                    PapelUsuario.objects.filter(pk=atribuicao_id)
                    .values_list("usuario_id", flat=True)
                    .first()
                )
                ids = {pk for pk in (titular_id, usuario_destino_id) if pk is not None}
                usuarios = {
                    usuario.pk: usuario
                    for usuario in (
                        User.objects.select_for_update().filter(pk__in=ids).order_by("pk")
                    )
                }
                setores = {usuario.setor_id for usuario in usuarios.values()}
                list(Setor.objects.select_for_update().filter(pk__in=setores).order_by("pk"))
                atual = PapelUsuario.objects.select_for_update().filter(pk=atribuicao_id).first()
                if atual is not None and atual.usuario_id not in usuarios:
                    raise _TitularAlteradoDuranteBloqueio
                yield atual, usuarios
                return
        except _TitularAlteradoDuranteBloqueio:
            continue


class PapelUsuario(models.Model):
    """Atribuição explícita de um papel a um usuário — a única forma de um
    usuário "ter" um papel. Cada linha é uma concessão independente, sem
    herança implícita entre papéis (`docs/domain/permissions-matrix.md`, regra 3)."""

    usuario = models.ForeignKey("contas.User", related_name="papeis", on_delete=models.CASCADE)
    papel = models.CharField(max_length=32, choices=Papel.choices)

    objects = PapelUsuarioQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "papel"],
                name="papelusuario_unico_usuario_papel",
            )
        ]

    def __str__(self):
        return f"{self.usuario_id} — {self.papel}"

    @staticmethod
    def exigir_papel_removivel(usuario_id, papel):
        usuario = User.objects.filter(pk=usuario_id).values("is_active", "is_superuser").first()
        if (
            papel == Papel.REQUISITANTE
            and usuario is not None
            and usuario["is_active"]
            and not usuario["is_superuser"]
        ):
            raise ValidationError(
                "ROLE-REQUESTER não pode ser removido de uma identidade de negócio ativa."
            )

    def _exigir_usuario_de_negocio(self):
        if User.objects.filter(pk=self.usuario_id, is_superuser=True).exists():
            raise ValidationError(
                "Superusuário técnico não pode possuir papéis de negócio ROLE-*."
            )

    def clean(self):
        # Pré-validação de formulário, que pode ocorrer fora de transação.
        # save()/delete() repetem as regras com os usuários atuais bloqueados.
        super().clean()
        self._exigir_usuario_de_negocio()
        if self.pk is None:
            return
        anterior = PapelUsuario.objects.filter(pk=self.pk).values("papel", "usuario_id").first()
        if anterior is not None and (
            anterior["papel"] != self.papel or anterior["usuario_id"] != self.usuario_id
        ):
            self.exigir_papel_removivel(anterior["usuario_id"], anterior["papel"])

    def save(self, *args, **kwargs):
        with _bloquear_atribuicao(self.pk, self.usuario_id) as (anterior, usuarios):
            self._exigir_usuario_de_negocio()
            papel_anterior = anterior.papel if anterior is not None else None
            usuario_id_anterior = anterior.usuario_id if anterior is not None else None
            usuario_mudou = (
                usuario_id_anterior is not None and usuario_id_anterior != self.usuario_id
            )

            if papel_anterior is not None and (usuario_mudou or papel_anterior != self.papel):
                self.exigir_papel_removivel(usuario_id_anterior, papel_anterior)

            # `FR-021`: o titular ANTIGO desta linha deixa de ser chefe quando
            # o `papel` muda para outra coisa OU quando a própria linha passa
            # a apontar para outro usuário (troca de titular sem passar por
            # `delete()`) — os dois casos abandonam a chefia do titular antigo.
            deixando_de_ser_chefe = papel_anterior == Papel.CHEFE_SETOR and (
                usuario_mudou or self.papel != Papel.CHEFE_SETOR
            )

            # `FR-022`: o titular ATUAL (`self.usuario_id`) passa a ser chefe
            # por esta linha quando `papel` é (ou permanece) `CHEFE_SETOR` e
            # essa atribuição é nova para ele — concessão nova, edição de
            # outro papel para chefe, ou troca de titular mantendo
            # `CHEFE_SETOR` (o mesmo caso de troca acima, do lado do novo
            # titular).
            tornando_se_chefe = self.papel == Papel.CHEFE_SETOR and (
                self.pk is None or usuario_mudou or papel_anterior != Papel.CHEFE_SETOR
            )

            if not (tornando_se_chefe or deixando_de_ser_chefe):
                return super().save(*args, **kwargs)

            if deixando_de_ser_chefe:
                usuario_antigo = usuarios[usuario_id_anterior]
                if usuario_antigo.is_active:
                    _exigir_chefia_preservada(
                        usuario_antigo.setor_id, excluir_usuario_id=usuario_antigo.pk
                    )
            if tornando_se_chefe:
                usuario_novo = usuarios[self.usuario_id]
                if usuario_novo.is_active:
                    _exigir_chefia_nao_duplicada(
                        usuario_novo.setor_id, excluir_usuario_id=usuario_novo.pk
                    )

            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with _bloquear_atribuicao(self.pk) as (atual, usuarios):
            if atual is not None:
                self.exigir_papel_removivel(atual.usuario_id, atual.papel)
                usuario = usuarios[atual.usuario_id]
                if atual.papel == Papel.CHEFE_SETOR and usuario.is_active:
                    _exigir_chefia_preservada(
                        usuario.setor_id, excluir_usuario_id=usuario.pk
                    )
            return super().delete(*args, **kwargs)
