"""Testes de `INV-ORG-002` / `INV-ORG-003` (FR-019 a FR-023).

Invariante canônica (`docs/domain/invariants-matrix.md`): *todo setor ativo
possui exatamente um chefe ativo, pertencente ao próprio setor; nenhuma
operação sobre usuário ou setor pode deixar um setor ativo sem chefe ativo.*

Esta feature não entrega administração de setores como produto, mas seu
caminho de bootstrap **escreve** em setor, usuário e papel — e por isso está
sujeito à invariante como qualquer outro caminho de escrita (`research.md` R4,
revisão 3). Os testes abaixo protegem cada uma das operações que poderiam
quebrá-la.

`INV-ORG-003` (um chefe responde por um único setor) é estrutural: a chefia é
derivada de `ROLE-SECTOR-HEAD` combinado ao setor único do próprio usuário
(`INV-ORG-001`), nunca de um vínculo separado — não há operação capaz de dar
dois setores ao mesmo chefe. Coberto pelo teste de leitura ao final.
"""

import pytest
from django.core.exceptions import ValidationError

from contas.models import Papel, PapelUsuario, Setor, User, chefes_ativos

SENHA = "uma-senha-de-teste-bastante-forte-123"


@pytest.fixture
def setor_inativo(db):
    return Setor.objects.create(nome="Almoxarifado")


def _criar_chefe(setor, matricula="chefe-01", is_active=True):
    chefe = User.objects.create_user(
        matricula=matricula, password=SENHA, setor=setor, is_active=is_active
    )
    PapelUsuario.objects.create(usuario=chefe, papel=Papel.CHEFE_SETOR)
    return chefe


def _ativar(setor):
    setor.ativo = True
    setor.save()
    setor.refresh_from_db()
    return setor


# ---------------------------------------------------------------------------
# FR-019: setor nasce inativo
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_setor_nasce_inativo():
    """Criar um setor nunca produz, sozinho, um setor ativo sem chefe."""
    setor = Setor.objects.create(nome="Compras")

    assert setor.ativo is False


@pytest.mark.django_db
def test_setor_nao_pode_ser_criado_ja_ativo():
    with pytest.raises(ValidationError):
        Setor.objects.create(nome="Compras", ativo=True)

    assert Setor.objects.filter(nome="Compras").exists() is False


# ---------------------------------------------------------------------------
# FR-020: ativação exige exatamente um chefe ativo do próprio setor
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_ativar_setor_sem_chefe_e_recusado(setor_inativo):
    setor_inativo.ativo = True

    with pytest.raises(ValidationError):
        setor_inativo.save()

    setor_inativo.refresh_from_db()
    assert setor_inativo.ativo is False, "operação recusada não deixa estado parcial (FR-023)"


@pytest.mark.django_db
def test_ativar_setor_com_exatamente_um_chefe_ativo_e_permitido(setor_inativo):
    _criar_chefe(setor_inativo)

    setor = _ativar(setor_inativo)

    assert setor.ativo is True
    assert chefes_ativos(setor.pk).count() == 1


@pytest.mark.django_db
def test_ativar_setor_cujo_unico_chefe_esta_inativo_e_recusado(setor_inativo):
    _criar_chefe(setor_inativo, is_active=False)

    setor_inativo.ativo = True
    with pytest.raises(ValidationError):
        setor_inativo.save()

    setor_inativo.refresh_from_db()
    assert setor_inativo.ativo is False


@pytest.mark.django_db
def test_chefe_de_outro_setor_nao_habilita_ativacao(setor_inativo):
    """O chefe precisa pertencer ao PRÓPRIO setor (`INV-ORG-002`)."""
    outro = Setor.objects.create(nome="Outro")
    _criar_chefe(outro, matricula="chefe-outro")

    setor_inativo.ativo = True
    with pytest.raises(ValidationError):
        setor_inativo.save()


# ---------------------------------------------------------------------------
# FR-021: nenhuma operação pode deixar um setor ativo sem chefe
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_desativar_o_unico_chefe_de_setor_ativo_e_recusado(setor_inativo):
    chefe = _criar_chefe(setor_inativo)
    _ativar(setor_inativo)

    chefe.is_active = False
    with pytest.raises(ValidationError):
        chefe.save()

    chefe.refresh_from_db()
    assert chefe.is_active is True, "recusa não deixa estado parcial (FR-023)"


@pytest.mark.django_db
def test_transferir_o_unico_chefe_para_outro_setor_e_recusado(setor_inativo):
    chefe = _criar_chefe(setor_inativo)
    _ativar(setor_inativo)
    destino = Setor.objects.create(nome="Destino")

    chefe.setor = destino
    with pytest.raises(ValidationError):
        chefe.save()

    chefe.refresh_from_db()
    assert chefe.setor_id == setor_inativo.pk


@pytest.mark.django_db
def test_remover_o_papel_do_unico_chefe_de_setor_ativo_e_recusado(setor_inativo):
    chefe = _criar_chefe(setor_inativo)
    _ativar(setor_inativo)

    atribuicao = PapelUsuario.objects.get(usuario=chefe, papel=Papel.CHEFE_SETOR)
    with pytest.raises(ValidationError):
        atribuicao.delete()

    assert PapelUsuario.objects.filter(usuario=chefe, papel=Papel.CHEFE_SETOR).exists()


@pytest.mark.django_db
def test_as_mesmas_operacoes_sao_permitidas_quando_o_setor_esta_inativo(setor_inativo):
    """Setor inativo não está sob `INV-ORG-002` — é exatamente o que torna o
    provisionamento possível sem um chefe preexistente (FR-019)."""
    chefe = _criar_chefe(setor_inativo)

    chefe.is_active = False
    chefe.save()
    chefe.refresh_from_db()

    assert chefe.is_active is False


@pytest.mark.django_db
def test_desativar_usuario_comum_de_setor_ativo_e_permitido(setor_inativo):
    """A regra vale para o chefe, não para qualquer usuário do setor."""
    _criar_chefe(setor_inativo)
    _ativar(setor_inativo)
    comum = User.objects.create_user(matricula="comum-01", password=SENHA, setor=setor_inativo)

    comum.is_active = False
    comum.save()
    comum.refresh_from_db()

    assert comum.is_active is False


# ---------------------------------------------------------------------------
# FR-022: nunca um segundo chefe num setor ativo
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_atribuir_segundo_chefe_a_setor_ativo_e_recusado(setor_inativo):
    _criar_chefe(setor_inativo)
    _ativar(setor_inativo)
    outro = User.objects.create_user(matricula="outro-01", password=SENHA, setor=setor_inativo)

    with pytest.raises(ValidationError):
        PapelUsuario.objects.create(usuario=outro, papel=Papel.CHEFE_SETOR)

    assert chefes_ativos(setor_inativo.pk).count() == 1


@pytest.mark.django_db
def test_transferir_um_chefe_para_setor_ativo_que_ja_tem_chefe_e_recusado(setor_inativo):
    _criar_chefe(setor_inativo, matricula="chefe-titular")
    _ativar(setor_inativo)

    origem = Setor.objects.create(nome="Origem")
    invasor = _criar_chefe(origem, matricula="chefe-invasor")

    invasor.setor = setor_inativo
    with pytest.raises(ValidationError):
        invasor.save()

    assert chefes_ativos(setor_inativo.pk).count() == 1


@pytest.mark.django_db
def test_reativar_um_segundo_chefe_em_setor_ativo_e_recusado(setor_inativo):
    dormente = _criar_chefe(setor_inativo, matricula="chefe-dormente", is_active=False)
    _criar_chefe(setor_inativo, matricula="chefe-titular")
    _ativar(setor_inativo)

    dormente.is_active = True
    with pytest.raises(ValidationError):
        dormente.save()

    assert chefes_ativos(setor_inativo.pk).count() == 1


@pytest.mark.django_db
def test_substituicao_de_chefe_e_possivel_desativando_o_setor(setor_inativo):
    """Caminho legítimo de troca: nenhuma regra impede a operação real, ela só
    exige passar por um estado que não viola a invariante."""
    antigo = _criar_chefe(setor_inativo, matricula="chefe-antigo")
    _ativar(setor_inativo)
    novo = User.objects.create_user(matricula="chefe-novo", password=SENHA, setor=setor_inativo)

    setor_inativo.ativo = False
    setor_inativo.save()

    PapelUsuario.objects.get(usuario=antigo, papel=Papel.CHEFE_SETOR).delete()
    PapelUsuario.objects.create(usuario=novo, papel=Papel.CHEFE_SETOR)

    setor = _ativar(setor_inativo)

    assert setor.ativo is True
    assert list(chefes_ativos(setor.pk).values_list("pk", flat=True)) == [novo.pk]


# ---------------------------------------------------------------------------
# INV-ORG-003: estrutural
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_chefe_responde_por_um_unico_setor_estruturalmente(setor_inativo):
    chefe = _criar_chefe(setor_inativo)
    _ativar(setor_inativo)

    # A chefia não é um vínculo próprio: é o setor único do usuário
    # (`INV-ORG-001`) combinado ao papel. Não existe campo capaz de apontar
    # para um segundo setor.
    assert chefe.setor_id == setor_inativo.pk
    assert Setor.objects.filter(ativo=True, user__pk=chefe.pk).count() == 1
