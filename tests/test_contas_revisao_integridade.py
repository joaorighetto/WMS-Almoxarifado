"""Regressões da revisão 5266085774 e `FR-016a` da 002, reescritas sobre a 005 (T006).

A revisão do PR 5 achou caminhos que contornavam as guardas por `save()` da 002: instâncias
obsoletas (cópia em memória diferente do banco), `update_fields` ignorando o estado
organizacional, criação genérica sem papel mínimo e corridas entre reativação, remoção do
papel mínimo e promoção a conta técnica. Na 005 o mecanismo muda (barreira de escrita,
`validar_organizacao` sobre o estado final, trigger adiado), mas cada risco continua
protegido — este arquivo prova isso caso a caso:

- criação genérica, exclusão por instância obsoleta e `update_fields`: barreira (R4);
- papel mínimo e conta técnica: `validar_organizacao` (R3) e, no banco, o trigger
  (`tests/test_contas_banco.py`, que também cobre as três corridas da revisão por SQL direto);
- `_bloquear_atribuicao` (retry de titular que muda durante o bloqueio): mecanismo REMOVIDO
  (R3) — o lock único de organização (R2) elimina a janela; não há o que portar.

Os casos de `reativar_usuario`/`alterar_papeis`/`desativar_usuario` foram completados à
medida que cada operação passou a existir (US3 e US5).
"""

import pytest
from django.core.exceptions import ValidationError

from contas import organizacao as org
from contas.models import Papel, PapelUsuario, Setor, User, chefes_ativos
from tests.contas_helpers import (
    SENHA_TESTE,
    estado_descartavel,
    membro,
    operacao,
    rodar_em_threads,
    validar_tudo,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def setor():
    return org.provisionar_setor("Setor")


@pytest.fixture
def admin():
    return membro(
        org.provisionar_setor("Administração"), "admin-01", {Papel.ADMINISTRADOR_SISTEMA}
    )


def _ativar(setor):
    org.provisionar_ativacao(setor)
    setor.refresh_from_db()
    return setor


# ---------------------------------------------------------------------------
# Criação genérica não persiste conta sem o papel mínimo (FR-016a)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("operacao_de_criacao", ["create", "bulk_create", "save"])
def test_criacao_generica_nao_persiste_conta_sem_papel_minimo(setor, operacao_de_criacao):
    with pytest.raises(ValidationError):
        if operacao_de_criacao == "create":
            User.objects.all().create(matricula="sem-papel", nome="Sem Papel", setor=setor)
        elif operacao_de_criacao == "bulk_create":
            User.objects.bulk_create([User(matricula="sem-papel", nome="Sem Papel", setor=setor)])
        else:
            User(matricula="sem-papel", nome="Sem Papel", setor=setor).save()

    assert not User.objects.filter(matricula="sem-papel").exists()


def test_identidade_de_negocio_nasce_com_o_papel_minimo_atomicamente(setor):
    """FR-016a: conta e `ROLE-REQUESTER` nascem juntos ou não nascem."""
    usuario = membro(setor, "novo-01")

    assert list(usuario.papeis.values_list("papel", flat=True)) == [Papel.REQUISITANTE]


def test_conta_nao_nasce_quando_a_criacao_e_recusada_no_meio(setor):
    """Atomicidade: se a operação é recusada depois de criar a conta (aqui, pelo estado
    final), nenhuma conta nem papel sobra (FR-016a, FR-023)."""
    with pytest.raises(org.OperacaoRecusada):
        membro(setor, "recusado-01", {Papel.FUNCIONARIO_ALMOXARIFADO})  # fora do Almoxarifado

    assert not User.objects.filter(matricula="recusado-01").exists()
    assert not PapelUsuario.objects.filter(usuario__matricula="recusado-01").exists()


# ---------------------------------------------------------------------------
# Instâncias OBSOLETAS (cópia em memória diferente do banco)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("campo_obsoleto", ["is_active", "setor"])
def test_exclusao_de_usuario_por_instancia_obsoleta_e_recusada(setor, campo_obsoleto):
    """Regressão: `delete()` de uma cópia desatualizada (inativa, ou ainda no setor
    antigo) não pode apagar o chefe ATUAL de um setor ativo. Na 005 nenhum usuário é
    excluído (FR-005) — a recusa não depende do que a cópia em memória diz."""
    usuario = membro(setor, "chefe-obsoleto", is_active=False)
    with operacao():
        PapelUsuario.objects.create(usuario=usuario, papel=Papel.CHEFE_SETOR)
    antigo = User.objects.get(pk=usuario.pk)  # cópia obsoleta: inativa, setor original
    destino = setor
    if campo_obsoleto == "setor":
        destino = org.provisionar_setor("Destino")
    with operacao():
        usuario.setor = destino
        usuario.is_active = True
        usuario.save()
    _ativar(destino)
    if campo_obsoleto == "setor":
        antigo.is_active = True

    with pytest.raises(ValidationError):
        antigo.delete()

    assert User.objects.filter(pk=usuario.pk).exists()
    assert chefes_ativos(destino.pk).count() == 1


@pytest.mark.parametrize("campo_obsoleto", ["papel", "usuario"])
def test_exclusao_de_atribuicao_por_instancia_obsoleta_e_recusada(setor, campo_obsoleto):
    """Regressão: `delete()` de uma `PapelUsuario` obsoleta (era auxiliar; apontava para
    outro titular) não pode remover a chefia ATUAL de um setor ativo."""
    usuario = membro(setor, "titular")
    with operacao():
        atribuicao = PapelUsuario.objects.create(
            usuario=usuario,
            papel=Papel.AUXILIAR_SETOR if campo_obsoleto == "papel" else Papel.CHEFE_SETOR,
        )
    antiga = PapelUsuario.objects.get(pk=atribuicao.pk)  # cópia obsoleta
    destino = setor
    with operacao():
        if campo_obsoleto == "usuario":
            destino = Setor.objects.create(nome="Destino")
            novo_titular = User.objects.create_user(
                matricula="novo-titular", setor=destino, nome="Novo Titular"
            )
            atribuicao.usuario = novo_titular
        atribuicao.papel = Papel.CHEFE_SETOR
        atribuicao.save()
    _ativar(destino)

    with pytest.raises(ValidationError):
        antiga.delete()

    assert PapelUsuario.objects.filter(pk=atribuicao.pk).exists()
    assert chefes_ativos(destino.pk).count() == 1


def test_exclusao_de_atribuicao_obsoleta_nao_remove_o_papel_minimo_atual(setor):
    usuario = membro(setor, "requisitante", is_active=False)
    with operacao():
        usuario.papeis.all().delete()
        atribuicao = PapelUsuario.objects.create(usuario=usuario, papel=Papel.AUXILIAR_SETOR)
    antiga = PapelUsuario.objects.get(pk=atribuicao.pk)  # cópia: era auxiliar
    with operacao():
        atribuicao.papel = Papel.REQUISITANTE
        atribuicao.save()
        usuario.is_active = True
        usuario.save()

    with pytest.raises(ValidationError):
        antiga.delete()

    assert usuario.tem_papel(Papel.REQUISITANTE)


# ---------------------------------------------------------------------------
# `update_fields`
# ---------------------------------------------------------------------------


def test_save_com_update_fields_nao_organizacionais_ignora_estado_organizacional_em_memoria(
    setor,
):
    """Só grava os campos pedidos: o `is_superuser=True` apenas em memória não vaza para
    o banco quando o rehash de senha regrava `password`."""
    usuario = membro(setor, "senha-isolada")
    usuario.is_superuser = True
    usuario.set_password("nova-senha-forte-do-teste-1")

    usuario.save(update_fields=["password"])

    usuario.refresh_from_db()
    assert usuario.check_password("nova-senha-forte-do-teste-1")
    assert usuario.is_superuser is False


def test_save_com_update_fields_organizacionais_continua_recusado_fora_de_operacao(setor):
    chefe = membro(setor, "chefe-update-fields", {Papel.CHEFE_SETOR})
    _ativar(setor)
    chefe.is_active = False

    with pytest.raises(ValidationError):
        chefe.save(update_fields=["is_active"])

    chefe.refresh_from_db()
    assert chefe.is_active is True
    assert chefes_ativos(setor.pk).count() == 1


# ---------------------------------------------------------------------------
# FR-016a no estado final: papel mínimo e conta técnica sem papéis
# ---------------------------------------------------------------------------


@pytest.fixture
def conta_tecnica(setor):
    return User.objects.create_superuser(
        matricula="tecnica", password=SENHA_TESTE, setor=setor, nome="Conta Técnica"
    )


def test_validar_organizacao_recusa_identidade_ativa_sem_role_requester(setor):
    usuario = membro(setor, "sem-requisitante")

    with estado_descartavel():
        PapelUsuario.objects.filter(usuario=usuario, papel=Papel.REQUISITANTE).delete()

        with pytest.raises(org.OperacaoRecusada) as excinfo:
            validar_tudo()

        assert excinfo.value.motivo


def test_identidade_inativa_pode_ficar_sem_role_requester_mas_nao_ser_reativada_assim(setor):
    """`ROLE-REQUESTER` só é exigido da identidade ATIVA; a reativação sem ele é recusada."""
    usuario = membro(setor, "inativo-01", is_active=False)

    with estado_descartavel():
        PapelUsuario.objects.filter(usuario=usuario).delete()
        validar_tudo()  # inativa, sem nenhum papel: válido

        User.objects.filter(pk=usuario.pk).update(is_active=True)
        with pytest.raises(org.OperacaoRecusada):
            validar_tudo()


def test_validar_organizacao_recusa_conta_tecnica_com_papel_de_negocio(setor, conta_tecnica):
    validar_tudo()  # a conta técnica sem papéis é válida

    with estado_descartavel():
        PapelUsuario.objects.create(usuario=conta_tecnica, papel=Papel.ADMINISTRADOR_SISTEMA)

        with pytest.raises(org.OperacaoRecusada):
            validar_tudo()


def test_validar_organizacao_recusa_promocao_de_identidade_com_papel_a_conta_tecnica(setor):
    usuario = membro(setor, "promovido-01")

    with estado_descartavel():
        User.objects.filter(pk=usuario.pk).update(is_superuser=True)

        with pytest.raises(org.OperacaoRecusada):
            validar_tudo()


# ---------------------------------------------------------------------------
# Operações das stories seguintes: papel mínimo, desativação, reativação
# ---------------------------------------------------------------------------


def test_role_requester_nao_pode_ser_removido_de_identidade_ativa(setor, admin):
    usuario = membro(setor, "ativo-01")

    with pytest.raises(org.OperacaoRecusada):
        org.alterar_papeis(admin, usuario.pk, conceder=set(), remover={Papel.REQUISITANTE})

    assert usuario.tem_papel(Papel.REQUISITANTE)


def test_papeis_sobrevivem_a_desativacao_da_conta(setor, admin):
    """Desativar não remove papel: o bloqueio é transversal (`INV-AUTH-001`)."""
    usuario = membro(setor, "para-desativar", {Papel.AUDITOR})

    org.desativar_usuario(admin, usuario.pk)

    usuario.refresh_from_db()
    assert usuario.is_active is False
    assert set(usuario.papeis.values_list("papel", flat=True)) == {
        Papel.REQUISITANTE,
        Papel.AUDITOR,
    }


def test_reativar_sem_role_requester_e_recusado(setor, admin):
    usuario = membro(setor, "inativo-01", is_active=False)
    with operacao():
        usuario.papeis.filter(papel=Papel.REQUISITANTE).delete()

    with pytest.raises(org.OperacaoRecusada):
        org.reativar_usuario(admin, usuario.pk, papeis_mantidos=set())

    usuario.refresh_from_db()
    assert usuario.is_active is False


# ---------------------------------------------------------------------------
# Corridas da revisão (operações; o mesmo por SQL direto está em test_contas_banco.py)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_reativacao_nao_concorre_com_remocao_do_papel_minimo(admin):
    """Regressão: reativar uma conta inativa e remover-lhe `ROLE-REQUESTER`, ao mesmo
    tempo, não pode deixar uma conta ATIVA sem o papel mínimo. Qualquer ordem serial é
    aceitável (a reativação refaz/exige o papel, ou a remoção chega antes e a reativação é
    recusada); o que nenhuma produz é ativa-sem-papel."""
    setor = org.provisionar_setor("Setor")
    usuario = membro(setor, "inativo-01", is_active=False)

    resultados = rodar_em_threads(
        {
            "reativar": lambda: org.reativar_usuario(
                admin, usuario.pk, papeis_mantidos={Papel.REQUISITANTE}
            ),
            "remover": lambda: org.alterar_papeis(
                admin, usuario.pk, conceder=set(), remover={Papel.REQUISITANTE}
            ),
        }
    )

    inesperadas = [
        r
        for r in resultados.values()
        if isinstance(r, Exception) and not isinstance(r, org.OperacaoRecusada)
    ]
    assert not inesperadas, resultados
    usuario.refresh_from_db()
    assert not (usuario.is_active and not usuario.tem_papel(Papel.REQUISITANTE))
    validar_tudo()
