"""Testes de model do app `contas` (T015, Phase 2 de `specs/002-autenticacao-login/`).

Cobre exclusivamente a camada de dados (`Setor`, `UserManager`, `User`, `Papel`,
`PapelUsuario`) — sem login/views/urls/middleware (T016+).

Invariantes/requisitos protegidos:
- `FR-001b`: `matricula` é identificador opaco (nunca convertida para número, nunca normalizada).
- `unique=True` em `User.matricula`: unicidade também em persistência (banco), não só aplicação.
- `INV-ORG-001`: todo usuário pertence a um `Setor` (obrigatório em domínio e em banco).
- `FR-014`/`FR-015`: papéis são concessões explícitas e independentes, sem herança implícita
  (`docs/domain/permissions-matrix.md`, regras 3 e 4), garantidas pela `UniqueConstraint`
  `papelusuario_unico_usuario_papel` e por `User.tem_papel()`.
- `docs/domain/permissions-matrix.md`, regras 7-8: `is_staff`/`is_superuser` são técnicos e nunca
  implicam papel de negócio (`ROLE-SYSTEM-ADMIN`).
"""

import pytest
from django.db import IntegrityError, transaction

from contas.models import Papel, PapelUsuario, Setor, User


@pytest.fixture
def setor(db):
    return Setor.objects.create(nome="Almoxarifado Central")


# ---------------------------------------------------------------------------
# Matrícula: identificador opaco (FR-001b)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_matricula_com_zeros_a_esquerda_e_preservada_exatamente(setor):
    usuario = User.objects.create_user(matricula="000123", password="senha-valida", setor=setor)

    # Força uma volta ao banco: se houvesse qualquer conversão numérica no
    # caminho de persistência (ex.: coluna numérica, cast, normalização), os
    # zeros à esquerda desapareceriam aqui.
    usuario_recarregado = User.objects.get(pk=usuario.pk)

    assert usuario_recarregado.matricula == "000123"
    assert isinstance(usuario_recarregado.matricula, str)
    assert usuario_recarregado.matricula != "123"


@pytest.mark.django_db
def test_matriculas_com_e_sem_zeros_a_esquerda_sao_identidades_distintas(setor):
    # Se a matrícula fosse tratada como número em algum ponto do fluxo,
    # "007" e "7" colidiriam na unicidade — o que nunca deve acontecer.
    com_zeros = User.objects.create_user(matricula="007", password="senha-valida", setor=setor)
    sem_zeros = User.objects.create_user(matricula="7", password="senha-valida", setor=setor)

    assert com_zeros.pk != sem_zeros.pk
    assert User.objects.get(pk=com_zeros.pk).matricula == "007"
    assert User.objects.get(pk=sem_zeros.pk).matricula == "7"


# ---------------------------------------------------------------------------
# Unicidade de matrícula em nível de banco
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_matricula_duplicada_e_rejeitada_pelo_banco(setor):
    User.objects.create_user(matricula="000123", password="senha-valida", setor=setor)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            User.objects.create_user(matricula="000123", password="outra-senha", setor=setor)


# ---------------------------------------------------------------------------
# Setor obrigatório (INV-ORG-001)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_user_sem_setor_e_rejeitado_pelo_manager():
    with pytest.raises(ValueError):
        User.objects.create_user(matricula="000123", password="senha-valida", setor=None)

    assert not User.objects.filter(matricula="000123").exists()


@pytest.mark.django_db
def test_usuario_sem_setor_e_rejeitado_pelo_banco_mesmo_contornando_o_manager():
    # Garante a invariante também como constraint de persistência
    # (NOT NULL), não apenas como validação de aplicação no manager.
    usuario = User(matricula="000123", setor=None)
    usuario.set_password("senha-valida")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            usuario.save()


# ---------------------------------------------------------------------------
# Múltiplos papéis simultâneos, sem herança implícita (FR-014/FR-015)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_usuario_pode_ter_multiplos_papeis_distintos_simultaneamente(setor):
    # Cenário real: chefe do almoxarifado acumula três papéis explícitos.
    chefe = User.objects.create_user(matricula="000999", password="senha-valida", setor=setor)
    PapelUsuario.objects.create(usuario=chefe, papel=Papel.FUNCIONARIO_ALMOXARIFADO)
    PapelUsuario.objects.create(usuario=chefe, papel=Papel.CHEFE_SETOR)
    PapelUsuario.objects.create(usuario=chefe, papel=Papel.CHEFE_ALMOXARIFADO)

    codigos = set(chefe.papeis.values_list("papel", flat=True))

    assert codigos == {
        Papel.FUNCIONARIO_ALMOXARIFADO,
        Papel.CHEFE_SETOR,
        Papel.CHEFE_ALMOXARIFADO,
    }
    assert chefe.tem_papel(Papel.FUNCIONARIO_ALMOXARIFADO)
    assert chefe.tem_papel(Papel.CHEFE_SETOR)
    assert chefe.tem_papel(Papel.CHEFE_ALMOXARIFADO)


@pytest.mark.django_db
def test_atribuicao_duplicada_do_mesmo_papel_e_rejeitada_pelo_banco(setor):
    usuario = User.objects.create_user(matricula="000123", password="senha-valida", setor=setor)
    PapelUsuario.objects.create(usuario=usuario, papel=Papel.CHEFE_SETOR)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PapelUsuario.objects.create(usuario=usuario, papel=Papel.CHEFE_SETOR)

    assert PapelUsuario.objects.filter(usuario=usuario, papel=Papel.CHEFE_SETOR).count() == 1


# ---------------------------------------------------------------------------
# tem_papel(): sem herança implícita (FR-015; permissions-matrix regras 3-4)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_tem_papel_nao_infere_nenhum_outro_papel(setor):
    usuario = User.objects.create_user(matricula="000123", password="senha-valida", setor=setor)
    PapelUsuario.objects.create(usuario=usuario, papel=Papel.CHEFE_SETOR)

    assert usuario.tem_papel(Papel.CHEFE_SETOR) is True

    # Chefe de setor não herda nenhuma capacidade de almoxarifado, mesmo
    # quando o chefe do almoxarifado (cenário real) acumula ambos os papéis
    # explicitamente em outro registro.
    assert usuario.tem_papel(Papel.CHEFE_ALMOXARIFADO) is False
    assert usuario.tem_papel(Papel.FUNCIONARIO_ALMOXARIFADO) is False
    assert usuario.tem_papel(Papel.ADMINISTRADOR_SISTEMA) is False

    # Semântica OR entre múltiplos códigos, sem conceder o que não foi
    # explicitamente atribuído.
    assert usuario.tem_papel(Papel.CHEFE_ALMOXARIFADO, Papel.FUNCIONARIO_ALMOXARIFADO) is False
    assert usuario.tem_papel(Papel.CHEFE_SETOR, Papel.AUDITOR) is True


@pytest.mark.django_db
def test_usuario_sem_nenhum_papel_atribuido_nao_tem_papel_algum(setor):
    usuario = User.objects.create_user(matricula="000123", password="senha-valida", setor=setor)

    assert usuario.tem_papel(Papel.REQUISITANTE) is False
    assert usuario.tem_papel(*[codigo.value for codigo in Papel]) is False


# ---------------------------------------------------------------------------
# Extras de baixo custo com risco real associado
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_superuser_e_tecnico_e_nao_concede_role_system_admin(setor):
    # `is_staff`/`is_superuser` são mecanismo técnico de acesso ao Django
    # Admin; superusuário técnico não é `ROLE-SYSTEM-ADMIN`
    # (`docs/domain/permissions-matrix.md`, regras 7-8).
    superusuario = User.objects.create_superuser(
        matricula="000001", password="senha-valida", setor=setor
    )

    assert superusuario.is_staff is True
    assert superusuario.is_superuser is True
    assert PapelUsuario.objects.filter(usuario=superusuario).exists() is False
    assert superusuario.tem_papel(Papel.ADMINISTRADOR_SISTEMA) is False


def test_catalogo_de_papeis_bate_com_os_ids_canonicos():
    # Trava contra redefinição silenciosa do catálogo fechado de papéis —
    # os `value` precisam continuar idênticos aos IDs canônicos de
    # `docs/domain/permissions-matrix.md`.
    ids_canonicos = {
        "ROLE-REQUESTER",
        "ROLE-SECTOR-ASSISTANT",
        "ROLE-SECTOR-HEAD",
        "ROLE-WAREHOUSE-STAFF",
        "ROLE-WAREHOUSE-HEAD",
        "ROLE-AUDITOR",
        "ROLE-SYSTEM-ADMIN",
    }

    assert {codigo.value for codigo in Papel} == ids_canonicos


# ---------------------------------------------------------------------------
# Bootstrap via `createsuperuser` (quickstart.md §1.2).
#
# Para um campo de `REQUIRED_FIELDS`, o comando aplica `field.clean()`, que numa
# ForeignKey devolve a PK — não a instância. O manager precisa aceitar as duas
# formas, ou o único caminho de provisionamento desta feature (research.md R6:
# createsuperuser + Django Admin) fica quebrado de ponta a ponta.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_user_aceita_setor_como_instancia():
    setor = Setor.objects.create(nome="Almoxarifado")

    usuario = User.objects.create_user(matricula="inst-01", password="x", setor=setor)

    assert usuario.setor == setor


@pytest.mark.django_db
def test_create_user_aceita_setor_como_pk():
    setor = Setor.objects.create(nome="Almoxarifado")

    usuario = User.objects.create_user(matricula="pk-01", password="x", setor=setor.pk)

    usuario.refresh_from_db()
    assert usuario.setor == setor, "PK de setor deve resolver para o Setor correto"


@pytest.mark.django_db
def test_create_superuser_aceita_setor_como_pk_como_o_createsuperuser_entrega():
    setor = Setor.objects.create(nome="Almoxarifado")

    superusuario = User.objects.create_superuser(
        matricula="pk-su-01", password="x", setor=setor.pk
    )

    superusuario.refresh_from_db()
    assert superusuario.setor == setor
    assert superusuario.is_staff is True
    assert superusuario.is_superuser is True


@pytest.mark.django_db
def test_create_user_com_pk_de_setor_inexistente_e_recusado_pelo_banco():
    # `INV-ORG-001` continua protegida em persistência: uma PK que não existe não
    # pode produzir um usuário órfão.
    #
    # A FK é criada como DEFERRABLE INITIALLY DEFERRED pelo Django, então a
    # violação só apareceria no commit; `check_constraints()` antecipa essa
    # verificação para dentro do bloco, tornando o teste determinístico.
    from django.db import connection

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(matricula="pk-orfao", password="x", setor=999999)
        connection.check_constraints()


@pytest.mark.django_db
def test_comando_createsuperuser_funciona_com_setor(capsys):
    """Protege o caminho literal de `quickstart.md` §1.2 contra regressão."""
    from django.core.management import call_command

    setor = Setor.objects.create(nome="Almoxarifado")

    call_command(
        "createsuperuser",
        interactive=False,
        matricula="su-cmd-01",
        setor=setor.pk,
        verbosity=0,
    )

    criado = User.objects.get(matricula="su-cmd-01")
    assert criado.setor == setor, "INV-ORG-001 preservada pelo caminho do comando"
    assert criado.is_staff is True and criado.is_superuser is True
    assert criado.tem_papel(*[p.value for p in Papel]) is False, (
        "superusuário técnico nunca recebe papel de negócio "
        "(permissions-matrix.md, regras 7-8)"
    )
