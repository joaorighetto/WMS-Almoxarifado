"""Leituras antecipadas do que as operações de organização recusariam (feature 005).

As funções `impedimento_de_*`, `prontidao_do_setor` e `bloqueios_de_papeis_no_cadastro` só
leem: devolvem a `OperacaoRecusada` que a operação levantaria (ou `None`) para a tela explicar
antes de oferecer o botão. A decisão continua sendo da operação, sob o lock — por isso cada
teste compara a antecipação com a recusa REAL da operação (mesmo motivo, mesmo caminho) e prova
que ler não escreve. Também cobre as recusas do cadastro no tempo verbal do cadastro.

Aplica: PERM-USER-MANAGE, PERM-SECTOR-MANAGE.
Preserva: INV-ORG-001, INV-ORG-002, INV-ORG-004, INV-ORG-006.
"""

import uuid

import pytest

from contas import organizacao as org
from contas.models import Papel, User
from tests.contas_helpers import (
    PAPEIS_CHEFE_ALMOXARIFADO,
    foto_organizacao,
    membro,
    recusa_de,
    setor_ativo,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario(admin_sistema):
    """O Almoxarifado Central (inativo, sem chefe), a ETA ativa com chefe e o Laboratório
    inativo."""
    eta, chefe_eta = setor_ativo("ETA", "eta-chefe")
    laboratorio = org.provisionar_setor("Laboratório")
    return {
        "admin": admin_sistema,
        "almoxarifado": admin_sistema.setor,
        "eta": eta,
        "chefe_eta": chefe_eta,
        "lab": laboratorio,
    }


def _igual_a_da_operacao(impedimento, real):
    assert impedimento is not None
    assert (impedimento.motivo, impedimento.caminho) == (real.motivo, real.caminho)


# ---------------------------------------------------------------------------
# desativar_usuario
# ---------------------------------------------------------------------------


def test_chefe_de_setor_ativo_nao_pode_ser_desativado_e_a_antecipacao_e_a_da_operacao(cenario):
    chefe = User.objects.select_related("setor").get(pk=cenario["chefe_eta"].pk)
    antes = foto_organizacao()

    impedimento = org.impedimento_de_desativar_usuario(cenario["admin"], chefe)

    assert impedimento.codigo == org.RECUSA_CHEFE_DE_SETOR_ATIVO
    _igual_a_da_operacao(
        impedimento, recusa_de(lambda: org.desativar_usuario(cenario["admin"], chefe.pk))
    )
    assert foto_organizacao() == antes


def test_a_propria_conta_do_autor_nao_pode_ser_desativada(cenario):
    admin = User.objects.select_related("setor").get(pk=cenario["admin"].pk)

    impedimento = org.impedimento_de_desativar_usuario(admin, admin)

    assert impedimento.codigo == org.RECUSA_PROPRIA_CONTA
    _igual_a_da_operacao(impedimento, recusa_de(lambda: org.desativar_usuario(admin, admin.pk)))


def test_o_ultimo_administrador_ativo_nao_pode_ser_desativado(cenario):
    """O autor aqui não é administrador (a tela exige o papel): mostra a regra isolada."""
    autor = membro(cenario["eta"], "eta-autor")
    admin = User.objects.select_related("setor").get(pk=cenario["admin"].pk)

    impedimento = org.impedimento_de_desativar_usuario(autor, admin)

    assert impedimento.codigo == org.RECUSA_ULTIMO_ADMINISTRADOR
    _igual_a_da_operacao(impedimento, recusa_de(lambda: org.desativar_usuario(autor, admin.pk)))


def test_conta_comum_e_conta_ja_inativa_nao_tem_impedimento_de_desativacao(cenario):
    comum = membro(cenario["eta"], "eta-comum")
    inativa = membro(cenario["eta"], "eta-inativa", is_active=False)

    assert org.impedimento_de_desativar_usuario(cenario["admin"], comum) is None
    assert org.impedimento_de_desativar_usuario(cenario["admin"], inativa) is None


def test_chefe_de_setor_inativo_pode_ser_desativado(cenario):
    chefe = membro(cenario["lab"], "lab-chefe", {Papel.CHEFE_SETOR})

    assert org.impedimento_de_desativar_usuario(cenario["admin"], chefe) is None


# ---------------------------------------------------------------------------
# transferir_usuario
# ---------------------------------------------------------------------------


def test_chefe_de_setor_ativo_nao_pode_ser_transferido_e_a_antecipacao_e_a_da_operacao(cenario):
    chefe = User.objects.select_related("setor").get(pk=cenario["chefe_eta"].pk)

    impedimento = org.impedimento_de_transferir_usuario(chefe)

    assert impedimento.codigo == org.RECUSA_CHEFE_DE_SETOR_ATIVO
    _igual_a_da_operacao(
        impedimento,
        recusa_de(
            lambda: org.transferir_usuario(
                cenario["admin"], chefe.pk, cenario["lab"].pk, papeis_removidos_previstos=[]
            )
        ),
    )


def test_quem_nao_chefia_setor_ativo_nao_tem_impedimento_de_transferencia(cenario):
    comum = membro(cenario["eta"], "eta-comum")
    chefe_do_inativo = membro(cenario["lab"], "lab-chefe", {Papel.CHEFE_SETOR})

    assert org.impedimento_de_transferir_usuario(comum) is None
    assert org.impedimento_de_transferir_usuario(chefe_do_inativo) is None


# ---------------------------------------------------------------------------
# desativar_setor
# ---------------------------------------------------------------------------


def test_setor_com_membros_ativos_alem_do_chefe_traz_os_membros_em_forma_estruturada(cenario):
    paula = membro(cenario["eta"], "eta-paula")
    pedro = membro(cenario["eta"], "eta-pedro")
    membro(cenario["eta"], "eta-inativo", is_active=False)
    antes = foto_organizacao()

    impedimento = org.impedimento_de_desativar_setor(cenario["eta"])

    assert impedimento.codigo == org.RECUSA_MEMBROS_ATIVOS
    assert [u.pk for u in impedimento.membros] == [paula.pk, pedro.pk]
    _igual_a_da_operacao(
        impedimento, recusa_de(lambda: org.desativar_setor(cenario["admin"], cenario["eta"].pk))
    )
    assert foto_organizacao() == antes


def test_o_almoxarifado_ativo_nunca_pode_ser_desativado(cenario):
    almoxarifado = cenario["almoxarifado"]
    membro(almoxarifado, "almox-chefe", PAPEIS_CHEFE_ALMOXARIFADO)
    org.provisionar_ativacao(almoxarifado)
    almoxarifado.refresh_from_db()

    impedimento = org.impedimento_de_desativar_setor(almoxarifado)

    assert impedimento.codigo == org.RECUSA_ALMOXARIFADO_PERMANENTE
    _igual_a_da_operacao(
        impedimento, recusa_de(lambda: org.desativar_setor(cenario["admin"], almoxarifado.pk))
    )


def test_setor_so_com_o_chefe_ativo_e_setor_inativo_nao_tem_impedimento_de_desativacao(cenario):
    solo, _ = setor_ativo("Solo", "solo-chefe")
    membro(solo, "solo-inativo", is_active=False)

    assert org.impedimento_de_desativar_setor(solo) is None
    assert org.impedimento_de_desativar_setor(cenario["lab"]) is None


# ---------------------------------------------------------------------------
# ativar_setor e prontidão
# ---------------------------------------------------------------------------


def test_setor_sem_chefe_nao_esta_pronto_e_a_antecipacao_e_a_da_operacao(cenario):
    lab = cenario["lab"]

    impedimento = org.impedimento_de_ativar_setor(lab)
    prontidao = org.prontidao_do_setor(lab)

    assert impedimento.codigo == org.RECUSA_SETOR_SEM_CHEFE
    _igual_a_da_operacao(impedimento, recusa_de(lambda: org.ativar_setor(cenario["admin"], lab.pk)))
    assert [(item["rotulo"], item["atendido"]) for item in prontidao] == [
        ("Chefe ativo designado", False)
    ]


def test_setor_com_chefe_designado_esta_pronto(cenario):
    lab = cenario["lab"]
    chefe = membro(lab, "lab-chefe")
    org.designar_chefia(cenario["admin"], lab.pk, chefe.pk)

    assert org.impedimento_de_ativar_setor(lab) is None
    assert all(item["atendido"] for item in org.prontidao_do_setor(lab))


def test_no_almoxarifado_a_prontidao_inclui_a_chefia_de_estoque_completa(cenario):
    almoxarifado = cenario["almoxarifado"]
    chefe = membro(almoxarifado, "almox-chefe", {Papel.CHEFE_SETOR})

    prontidao = org.prontidao_do_setor(almoxarifado)
    impedimento = org.impedimento_de_ativar_setor(almoxarifado)

    assert [(item["rotulo"], item["atendido"]) for item in prontidao] == [
        ("Chefe ativo designado", True),
        ("Chefia de estoque completa", False),
    ]
    assert impedimento.codigo == org.RECUSA_CHEFIA_DE_ESTOQUE_INCOMPLETA
    assert chefe.matricula in impedimento.motivo
    _igual_a_da_operacao(
        impedimento, recusa_de(lambda: org.ativar_setor(cenario["admin"], almoxarifado.pk))
    )


def test_no_almoxarifado_a_designacao_completa_a_chefia_de_estoque(cenario):
    almoxarifado = cenario["almoxarifado"]
    chefe = membro(almoxarifado, "almox-chefe")
    org.designar_chefia(cenario["admin"], almoxarifado.pk, chefe.pk)

    assert org.impedimento_de_ativar_setor(almoxarifado) is None
    assert all(item["atendido"] for item in org.prontidao_do_setor(almoxarifado))


def test_setor_ja_ativo_nao_tem_impedimento_de_ativacao(cenario):
    assert org.impedimento_de_ativar_setor(cenario["eta"]) is None


# ---------------------------------------------------------------------------
# Cadastro: bloqueios por setor e recusas no tempo verbal do cadastro
# ---------------------------------------------------------------------------


def test_fora_do_almoxarifado_os_papeis_de_almoxarifado_ficam_bloqueados_no_cadastro(cenario):
    bloqueios = org.bloqueios_de_papeis_no_cadastro(cenario["lab"])

    assert set(bloqueios) == {Papel.FUNCIONARIO_ALMOXARIFADO, Papel.CHEFE_ALMOXARIFADO}
    for recusa in bloqueios.values():
        assert recusa.codigo == org.RECUSA_PAPEL_DE_ALMOXARIFADO_FORA_DO_ALMOXARIFADO
        assert "só podem ser dados a quem é do setor Almoxarifado" in recusa.motivo


def test_setor_ativo_ou_com_chefe_bloqueia_o_papel_de_chefe_no_cadastro(cenario):
    do_ativo = org.bloqueios_de_papeis_no_cadastro(cenario["eta"])
    chefe = membro(cenario["lab"], "lab-chefe", {Papel.CHEFE_SETOR})
    do_inativo_com_chefe = org.bloqueios_de_papeis_no_cadastro(cenario["lab"])
    outro_inativo = org.provisionar_setor("Compras")
    do_inativo_sem_chefe = org.bloqueios_de_papeis_no_cadastro(outro_inativo)

    assert do_ativo[Papel.CHEFE_SETOR].codigo == org.RECUSA_SETOR_JA_TEM_CHEFE
    assert do_inativo_com_chefe[Papel.CHEFE_SETOR].codigo == org.RECUSA_SETOR_JA_TEM_CHEFE
    assert Papel.CHEFE_SETOR not in do_inativo_sem_chefe
    assert chefe.is_active


def test_no_almoxarifado_sem_chefe_nada_fica_bloqueado_no_cadastro(cenario):
    assert org.bloqueios_de_papeis_no_cadastro(cenario["almoxarifado"]) == {}


def test_o_requisitante_nunca_e_oferecido_nem_bloqueado_no_cadastro(cenario):
    assert Papel.REQUISITANTE not in org.bloqueios_de_papeis_no_cadastro(cenario["eta"])


def test_cadastro_com_papel_de_almoxarifado_fora_do_almoxarifado_recusa_com_texto_do_cadastro(
    cenario,
):
    antes = foto_organizacao()

    recusa = recusa_de(
        lambda: org.cadastrar_usuario(
            cenario["admin"],
            matricula="NOVO-1",
            nome="Nova Pessoa",
            setor_id=cenario["eta"].pk,
            papeis_adicionais={Papel.FUNCIONARIO_ALMOXARIFADO},
            chave_confirmacao=uuid.uuid4(),
        )
    )

    assert recusa.motivo == (
        "Os papéis de almoxarifado só podem ser dados a quem é do setor Almoxarifado."
    )
    assert recusa.caminho == "Escolha o setor Almoxarifado ou desmarque o papel."
    assert "A conta" not in recusa.motivo
    assert foto_organizacao() == antes


def test_cadastro_de_chefe_em_setor_que_ja_tem_chefe_recusa_sem_gravar(cenario):
    antes = foto_organizacao()

    recusa = recusa_de(
        lambda: org.cadastrar_usuario(
            cenario["admin"],
            matricula="NOVO-2",
            nome="Nova Pessoa",
            setor_id=cenario["eta"].pk,
            papeis_adicionais={Papel.CHEFE_SETOR},
            chave_confirmacao=uuid.uuid4(),
        )
    )

    assert recusa.codigo == org.RECUSA_SETOR_JA_TEM_CHEFE
    assert recusa.motivo == "O setor ETA já tem chefe."
    assert foto_organizacao() == antes


def test_cadastro_de_chefe_em_setor_inativo_sem_chefe_continua_valendo(cenario):
    usuario, _ = org.cadastrar_usuario(
        cenario["admin"],
        matricula="NOVO-3",
        nome="Nova Chefe",
        setor_id=cenario["lab"].pk,
        papeis_adicionais={Papel.CHEFE_SETOR},
        chave_confirmacao=uuid.uuid4(),
    )

    assert Papel.CHEFE_SETOR in {p.papel for p in usuario.papeis.all()}


def test_matricula_repetida_no_cadastro_e_identificavel_pelo_codigo(cenario):
    recusa = recusa_de(
        lambda: org.cadastrar_usuario(
            cenario["admin"],
            matricula=cenario["chefe_eta"].matricula,
            nome="Outra Pessoa",
            setor_id=cenario["lab"].pk,
            papeis_adicionais=set(),
            chave_confirmacao=uuid.uuid4(),
        )
    )

    assert recusa.codigo == org.RECUSA_MATRICULA_EM_USO
    assert recusa.motivo == "Matrícula já usada por outra conta."


def test_o_provisionamento_tecnico_mantem_a_recusa_de_estado_final(cenario):
    """O texto do cadastro é só do cadastro: o provisionamento (sem autor) segue pela
    validação do estado final."""
    with pytest.raises(org.OperacaoRecusada) as excecao:
        org.provisionar_usuario(
            "TEC-1", "Pessoa Técnica", cenario["eta"], {Papel.FUNCIONARIO_ALMOXARIFADO}
        )

    assert "tem papel de almoxarifado fora do setor Almoxarifado" in excecao.value.motivo
