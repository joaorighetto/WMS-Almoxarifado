"""`INV-ORG-002` / `INV-ORG-003` (FR-019 a FR-023 da 002) e, no estado final,
`INV-ORG-005` / `INV-ORG-006` — reescrito sobre `contas.organizacao` (T006).

Invariante canônica: *todo setor ativo possui exatamente um chefe ativo, pertencente ao
próprio setor; nenhuma operação sobre usuário ou setor pode deixar um setor ativo sem
chefe ativo.* A 005 troca o MECANISMO da 002 — guardas por `save()` e `select_for_update`
por linha — por (a) `validar_organizacao` sobre o estado final, (b) a barreira de escrita
que recusa qualquer gravação fora das operações e (c) o trigger adiado do banco
(`tests/test_contas_banco.py`). O COMPORTAMENTO observável de FR-019 a FR-023 não muda, e
cada caso hoje coberto continua coberto aqui, chamando a operação do contrato.

Os casos que dependiam de operações das stories seguintes (desativar o chefe, transferir o
chefe, remover o papel do chefe, segundo chefe por papel, reativação, substituição) já
chamam a operação e foram completados à medida que cada uma passou a existir (US3 a US5).
Nenhum caso da 002 foi descartado; o mapeamento completo está no relatório do
test-engineer (T003/T006).

Estados que a aplicação nunca produz (setor ativo sem chefe, dois chefes...) são montados
por `estado_descartavel()` — escrita dentro de uma operação, desfeita ao fim — para provar
que `validar_organizacao` os recusa.
"""

from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from contas import organizacao as org
from contas.models import Papel, PapelUsuario, Setor, User, chefes_ativos
from tests.contas_helpers import (
    PAPEIS_CHEFE_ALMOXARIFADO,
    almoxarifado_ativo,
    estado_descartavel,
    membro,
    operacao,
    rodar_em_threads,
    setor_ativo,
    validar_tudo,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def setor_inativo():
    return org.provisionar_setor("Compras")


@pytest.fixture
def admin():
    """Autor das operações das stories seguintes (administrador ativo, noutro setor)."""
    return membro(
        org.provisionar_setor("Administração"), "admin-01", {Papel.ADMINISTRADOR_SISTEMA}
    )


def _chefe(setor, matricula="chefe-01", is_active=True):
    return membro(setor, matricula, {Papel.CHEFE_SETOR}, is_active=is_active)


def _ativar(setor):
    org.provisionar_ativacao(setor)
    setor.refresh_from_db()
    return setor


def _ex_chefe(setor, matricula="ex-chefe"):
    """Usuário INATIVO que preservou `ROLE-SECTOR-HEAD` (a desativação não remove papéis)."""
    usuario = membro(setor, matricula, is_active=False)
    with operacao():
        PapelUsuario.objects.create(usuario=usuario, papel=Papel.CHEFE_SETOR)
    return usuario


def _ids(chefes):
    return [u.pk for u in chefes]


# ---------------------------------------------------------------------------
# FR-019: setor nasce inativo
# ---------------------------------------------------------------------------


def test_setor_nasce_inativo():
    """Criar um setor nunca produz, sozinho, um setor ativo sem chefe."""
    setor = org.provisionar_setor("Compras")

    assert setor.ativo is False
    assert setor.ativado_em is None


def test_setor_nao_pode_ser_criado_ja_ativo():
    with pytest.raises(org.OperacaoRecusada):
        org.provisionar_setor("Compras", ativo=True)

    assert Setor.objects.filter(nome="Compras").exists() is False


# ---------------------------------------------------------------------------
# FR-020: ativação exige exatamente um chefe ativo do próprio setor
# ---------------------------------------------------------------------------


def test_ativar_setor_sem_chefe_e_recusado(setor_inativo):
    with pytest.raises(org.OperacaoRecusada):
        org.provisionar_ativacao(setor_inativo)

    setor_inativo.refresh_from_db()
    assert setor_inativo.ativo is False, "operação recusada não deixa estado parcial (FR-023)"
    assert setor_inativo.ativado_em is None


def test_ativar_setor_com_exatamente_um_chefe_ativo_e_permitido(setor_inativo):
    _chefe(setor_inativo)

    setor = _ativar(setor_inativo)

    assert setor.ativo is True
    assert setor.ativado_em is not None
    assert chefes_ativos(setor.pk).count() == 1
    validar_tudo()


def test_ativar_setor_cujo_unico_chefe_esta_inativo_e_recusado(setor_inativo):
    _chefe(setor_inativo, is_active=False)

    with pytest.raises(org.OperacaoRecusada):
        org.provisionar_ativacao(setor_inativo)

    setor_inativo.refresh_from_db()
    assert setor_inativo.ativo is False


def test_chefe_de_outro_setor_nao_habilita_ativacao(setor_inativo):
    """O chefe precisa pertencer ao PRÓPRIO setor (`INV-ORG-002`)."""
    outro = org.provisionar_setor("Outro")
    _chefe(outro, matricula="chefe-outro")

    with pytest.raises(org.OperacaoRecusada):
        org.provisionar_ativacao(setor_inativo)


# ---------------------------------------------------------------------------
# `validar_organizacao` recusa cada forma de violar `INV-ORG-002` no estado final
# ---------------------------------------------------------------------------


@pytest.fixture
def cenario():
    """Almoxarifado e ETA ativos (cada um com chefe), um membro comum da ETA, o
    Laboratório inativo com chefe, um setor inativo sem chefe e um ex-chefe inativo."""
    almox, chefe_almox = almoxarifado_ativo()
    membro_almox = membro(almox, "almox-membro", {Papel.FUNCIONARIO_ALMOXARIFADO})
    eta, chefe_eta = setor_ativo("ETA", "eta-chefe")
    membro_eta = membro(eta, "eta-membro")
    dormente = _ex_chefe(eta, "eta-dormente")
    lab = org.provisionar_setor("Laboratório")
    chefe_lab = _chefe(lab, "lab-chefe")
    vazio = org.provisionar_setor("Sem Chefia")
    membro_vazio = membro(vazio, "vazio-membro")
    return SimpleNamespace(
        almox=almox,
        chefe_almox=chefe_almox,
        membro_almox=membro_almox,
        eta=eta,
        chefe_eta=chefe_eta,
        membro_eta=membro_eta,
        dormente=dormente,
        lab=lab,
        chefe_lab=chefe_lab,
        vazio=vazio,
        membro_vazio=membro_vazio,
    )


def _conceder(usuario, papel):
    PapelUsuario.objects.create(usuario=usuario, papel=papel)


def _retirar(usuario, papel):
    PapelUsuario.objects.filter(usuario=usuario, papel=papel).delete()


def _usuario_set(usuario, **campos):
    User.objects.filter(pk=usuario.pk).update(**campos)


def _ativar_no_banco(setor):
    Setor.objects.filter(pk=setor.pk).update(ativo=True, ativado_em=timezone.now())


def _ativar_setor_cujo_chefe_esta_inativo(c):
    _usuario_set(c.chefe_lab, is_active=False)
    _ativar_no_banco(c.lab)


def _dois_chefes_do_almoxarifado(c):
    _conceder(c.membro_almox, Papel.CHEFE_SETOR)
    _conceder(c.membro_almox, Papel.CHEFE_ALMOXARIFADO)


def _troca_so_da_chefia_do_setor(c):
    _conceder(c.membro_almox, Papel.CHEFE_SETOR)
    _retirar(c.chefe_almox, Papel.CHEFE_SETOR)


def _staff_em_conta_inativa_fora_do_almoxarifado(c):
    _usuario_set(c.membro_eta, is_active=False)
    _conceder(c.membro_eta, Papel.FUNCIONARIO_ALMOXARIFADO)


VIOLACOES_INV_ORG_002 = [
    pytest.param(lambda c: _ativar_no_banco(c.vazio), id="setor_ativado_sem_chefe"),
    pytest.param(_ativar_setor_cujo_chefe_esta_inativo, id="setor_ativado_com_chefe_inativo"),
    pytest.param(
        lambda c: _retirar(c.chefe_eta, Papel.CHEFE_SETOR), id="papel_do_unico_chefe_removido"
    ),
    pytest.param(
        lambda c: _usuario_set(c.chefe_eta, is_active=False), id="unico_chefe_desativado"
    ),
    pytest.param(
        lambda c: _usuario_set(c.chefe_eta, setor=c.lab), id="unico_chefe_transferido"
    ),
    pytest.param(
        lambda c: _conceder(c.membro_eta, Papel.CHEFE_SETOR), id="segundo_chefe_por_papel"
    ),
    pytest.param(
        lambda c: _usuario_set(c.chefe_lab, setor=c.eta), id="chefe_transferido_para_setor_ativo"
    ),
    pytest.param(
        lambda c: _usuario_set(c.dormente, is_active=True), id="ex_chefe_reativado_como_segundo"
    ),
]


@pytest.mark.parametrize("violar", VIOLACOES_INV_ORG_002)
def test_validar_organizacao_recusa_setor_ativo_sem_exatamente_um_chefe_proprio(
    cenario, violar
):
    validar_tudo()  # o ponto de partida é válido

    with estado_descartavel():
        violar(cenario)

        with pytest.raises(org.OperacaoRecusada) as excinfo:
            validar_tudo()

        assert excinfo.value.motivo, "toda recusa informa o motivo (FR-048)"

    validar_tudo()  # nada do estado descartável sobreviveu


def test_validar_organizacao_avalia_o_estado_final_nao_cada_passo(cenario):
    """R3: trocar o chefe passa por um estado intermediário inválido; o que vale é o
    resultado — por isso a substituição atômica (US4) é possível."""
    with estado_descartavel():
        _conceder(cenario.membro_eta, Papel.CHEFE_SETOR)  # dois chefes: intermediário
        _retirar(cenario.chefe_eta, Papel.CHEFE_SETOR)  # um chefe: final

        validar_tudo()

        assert _ids(chefes_ativos(cenario.eta.pk)) == [cenario.membro_eta.pk]


def test_setor_inativo_nao_esta_sob_inv_org_002(cenario):
    """FR-019: é exatamente por isso que o setor nasce inativo — sem chefe, ou com o
    chefe inativo, nada é recusado enquanto ele não for ativado."""
    with estado_descartavel():
        _usuario_set(cenario.chefe_lab, is_active=False)

        validar_tudo()


# ---------------------------------------------------------------------------
# FR-021: nenhuma operação deixa setor ativo sem chefe
# ---------------------------------------------------------------------------


@pytest.fixture
def eta(setor_inativo):
    chefe = _chefe(setor_inativo)
    _ativar(setor_inativo)
    return setor_inativo, chefe


def test_desativar_o_unico_chefe_de_setor_ativo_e_recusado(eta, admin):
    setor, chefe = eta

    with pytest.raises(org.OperacaoRecusada):
        org.desativar_usuario(admin, chefe.pk)

    chefe.refresh_from_db()
    assert chefe.is_active is True, "recusa não deixa estado parcial (FR-023)"


def test_queryset_update_nao_contorna_a_protecao_do_unico_chefe(eta):
    _, chefe = eta

    with pytest.raises(ValidationError):
        User.objects.filter(pk=chefe.pk).update(is_active=False)

    chefe.refresh_from_db()
    assert chefe.is_active is True


def test_excluir_o_unico_chefe_de_setor_ativo_e_recusado(eta):
    setor, chefe = eta

    with pytest.raises(ValidationError):
        chefe.delete()
    with pytest.raises(ValidationError):
        User.objects.filter(pk=chefe.pk).delete()

    assert User.objects.filter(pk=chefe.pk).exists()
    assert chefes_ativos(setor.pk).count() == 1


def test_transferir_o_unico_chefe_para_outro_setor_e_recusado(eta, admin):
    setor, chefe = eta
    destino = org.provisionar_setor("Destino")

    with pytest.raises(org.OperacaoRecusada):
        org.transferir_usuario(admin, chefe.pk, destino.pk, papeis_removidos_previstos=set())

    chefe.refresh_from_db()
    assert chefe.setor_id == setor.pk


def test_remover_o_papel_do_unico_chefe_pela_operacao_e_recusado(eta, admin):
    _, chefe = eta

    with pytest.raises(org.OperacaoRecusada):
        org.alterar_papeis(admin, chefe.pk, conceder=set(), remover={Papel.CHEFE_SETOR})

    assert chefe.tem_papel(Papel.CHEFE_SETOR)


def test_remover_o_papel_do_unico_chefe_fora_das_operacoes_e_recusado(eta):
    """A exclusão da linha, a exclusão em lote e a edição da linha para outro papel
    (regressão: antes só `delete()` era validado) são recusadas."""
    setor, chefe = eta
    atribuicao = PapelUsuario.objects.get(usuario=chefe, papel=Papel.CHEFE_SETOR)

    with pytest.raises(ValidationError):
        atribuicao.delete()
    with pytest.raises(ValidationError):
        PapelUsuario.objects.filter(usuario=chefe, papel=Papel.CHEFE_SETOR).delete()
    atribuicao.papel = Papel.AUXILIAR_SETOR
    with pytest.raises(ValidationError):
        atribuicao.save()

    atribuicao.refresh_from_db()
    assert atribuicao.papel == Papel.CHEFE_SETOR, "recusa não deixa estado parcial (FR-023)"
    assert chefes_ativos(setor.pk).count() == 1


def test_excluir_usuario_comum_tambem_e_recusado_e_a_chefia_permanece(eta):
    """A 002 permitia excluir um usuário comum (cascata nos papéis). A 005 não exclui
    ninguém (FR-005): a mesma tentativa é recusada, e a chefia segue intacta."""
    setor, chefe = eta
    comum = membro(setor, "comum-cascata")
    papel_id = comum.papeis.get(papel=Papel.REQUISITANTE).pk

    with pytest.raises(ValidationError):
        comum.delete()

    assert User.objects.filter(pk=comum.pk).exists()
    assert PapelUsuario.objects.filter(pk=papel_id).exists()
    assert _ids(chefes_ativos(setor.pk)) == [chefe.pk]


def test_as_mesmas_operacoes_sao_permitidas_quando_o_setor_esta_inativo(setor_inativo, admin):
    """Setor inativo não está sob `INV-ORG-002` (FR-019)."""
    chefe = _chefe(setor_inativo)

    org.desativar_usuario(admin, chefe.pk)

    chefe.refresh_from_db()
    assert chefe.is_active is False


def test_desativar_usuario_comum_de_setor_ativo_e_permitido(eta, admin):
    """A regra vale para o chefe, não para qualquer usuário do setor."""
    setor, _ = eta
    comum = membro(setor, "comum-01")

    org.desativar_usuario(admin, comum.pk)

    comum.refresh_from_db()
    assert comum.is_active is False


# ---------------------------------------------------------------------------
# FR-022: nunca um segundo chefe
# ---------------------------------------------------------------------------


def test_cadastrar_segundo_chefe_em_setor_ativo_e_recusado(eta):
    setor, _ = eta
    antes = User.objects.count()

    with pytest.raises(org.OperacaoRecusada):
        membro(setor, "outro-01", {Papel.CHEFE_SETOR})

    assert User.objects.count() == antes, "a conta não pode nascer (FR-008/FR-023)"
    assert chefes_ativos(setor.pk).count() == 1


def test_cadastrar_segundo_chefe_em_setor_inativo_que_ja_tem_chefe_tambem_e_recusado(
    setor_inativo,
):
    """A guarda da 002 (`_exigir_chefia_nao_duplicada`) NÃO condicionava a `Setor.ativo`
    — de propósito — e FR-022 fala em "setor que já possua um chefe ativo", sem
    qualificar o setor. A tabela de recusas de `cadastrar_usuario` também diz "setor com
    chefe ativo". Ver "Lacunas e ambiguidades" no relatório do test-engineer."""
    _chefe(setor_inativo)

    with pytest.raises(org.OperacaoRecusada):
        membro(setor_inativo, "outro-01", {Papel.CHEFE_SETOR})

    assert chefes_ativos(setor_inativo.pk).count() == 1


def test_conceder_papel_de_chefe_a_segundo_membro_de_setor_ativo_e_recusado(eta, admin):
    setor, _ = eta
    outro = membro(setor, "outro-01")

    with pytest.raises(org.OperacaoRecusada):
        org.alterar_papeis(admin, outro.pk, conceder={Papel.CHEFE_SETOR}, remover=set())

    assert chefes_ativos(setor.pk).count() == 1


def test_atribuir_papel_de_chefe_fora_das_operacoes_e_recusado(eta):
    setor, _ = eta
    outro = membro(setor, "outro-01")

    with pytest.raises(ValidationError):
        PapelUsuario.objects.create(usuario=outro, papel=Papel.CHEFE_SETOR)

    assert chefes_ativos(setor.pk).count() == 1


def test_chefe_de_setor_inativo_transferido_para_setor_ativo_nao_cria_segundo_chefe(eta, admin):
    """Na 002 a transferência era RECUSADA (`_exigir_chefia_nao_duplicada`). Na 005
    (FR-013) ela remove `ROLE-SECTOR-HEAD` do transferido, então o resultado que FR-022
    protege — um único chefe no destino — se mantém por outro caminho."""
    destino, titular = eta
    origem = org.provisionar_setor("Origem")
    invasor = _chefe(origem, matricula="chefe-invasor")

    org.transferir_usuario(
        admin, invasor.pk, destino.pk, papeis_removidos_previstos={Papel.CHEFE_SETOR}
    )

    assert _ids(chefes_ativos(destino.pk)) == [titular.pk]
    assert not User.objects.get(pk=invasor.pk).tem_papel(Papel.CHEFE_SETOR)


def test_reativar_um_segundo_chefe_em_setor_ativo_e_recusado(eta, admin):
    setor, _ = eta
    dormente = _ex_chefe(setor, "chefe-dormente")

    with pytest.raises(org.OperacaoRecusada):
        org.reativar_usuario(
            admin, dormente.pk, papeis_mantidos={Papel.REQUISITANTE, Papel.CHEFE_SETOR}
        )

    dormente.refresh_from_db()
    assert dormente.is_active is False
    assert chefes_ativos(setor.pk).count() == 1


@pytest.mark.parametrize("como", ["save", "update"])
def test_trocar_o_titular_de_uma_linha_de_chefe_e_recusado(eta, como):
    """Regressão: reapontar o `usuario` de uma linha `CHEFE_SETOR` (o `papel` não muda)
    contornava as guardas da 002 e podia deixar o setor de origem sem chefe E duplicar a
    chefia do destino. Agora é uma escrita fora de operação — recusada pela barreira."""
    setor, titular = eta
    outro_setor = org.provisionar_setor("Outro")
    chefe_de_outro_setor = _chefe(outro_setor, matricula="chefe-outro-setor")
    _ativar(outro_setor)
    atribuicao = PapelUsuario.objects.get(usuario=titular, papel=Papel.CHEFE_SETOR)

    with pytest.raises(ValidationError):
        if como == "save":
            atribuicao.usuario = chefe_de_outro_setor
            atribuicao.save()
        else:
            PapelUsuario.objects.filter(pk=atribuicao.pk).update(usuario=chefe_de_outro_setor)

    atribuicao.refresh_from_db()
    assert atribuicao.usuario_id == titular.pk, "recusa não deixa estado parcial (FR-023)"
    assert _ids(chefes_ativos(setor.pk)) == [titular.pk]
    assert _ids(chefes_ativos(outro_setor.pk)) == [chefe_de_outro_setor.pk]


def test_trocar_o_titular_para_usuario_do_destino_ja_com_chefe_e_recusado(setor_inativo):
    """Regressão: isola o lado "duplicar a chefia do destino" — a origem é INATIVA (não
    sujeita a `INV-ORG-002`), o destino já ativo tem outro chefe (FR-022)."""
    titular = _chefe(setor_inativo, matricula="titular-01")
    destino = org.provisionar_setor("Destino")
    chefe_destino = _chefe(destino, matricula="chefe-destino")
    _ativar(destino)
    usuario_destino = membro(destino, "requisitante-destino")
    atribuicao = PapelUsuario.objects.get(usuario=titular, papel=Papel.CHEFE_SETOR)
    atribuicao.usuario = usuario_destino

    with pytest.raises(ValidationError):
        atribuicao.save()

    atribuicao.refresh_from_db()
    assert atribuicao.usuario_id == titular.pk
    assert _ids(chefes_ativos(destino.pk)) == [chefe_destino.pk]


def test_editar_papel_de_outro_usuario_para_chefe_em_setor_com_titular_e_recusado(eta):
    """Regressão: o caminho de UPDATE de outro papel PARA `CHEFE_SETOR` (FR-022)."""
    setor, _ = eta
    requisitante = membro(setor, "requisitante-01")
    atribuicao = PapelUsuario.objects.get(usuario=requisitante, papel=Papel.REQUISITANTE)
    atribuicao.papel = Papel.CHEFE_SETOR

    with pytest.raises(ValidationError):
        atribuicao.save()

    atribuicao.refresh_from_db()
    assert atribuicao.papel == Papel.REQUISITANTE, "recusa não deixa estado parcial (FR-023)"
    assert chefes_ativos(setor.pk).count() == 1


def test_substituicao_de_chefe_de_setor_ativo_e_possivel_numa_unica_operacao(eta, admin):
    """Caminho legítimo de troca. Na 002 só era possível desativando o setor antes; a
    substituição atômica (FR-014) a torna uma operação só, sem passar por estado
    inválido visível."""
    setor, antigo = eta
    novo = membro(setor, "chefe-novo")

    org.substituir_chefia(admin, setor.pk, chefe_esperado_id=antigo.pk, novo_chefe_id=novo.pk)

    assert _ids(chefes_ativos(setor.pk)) == [novo.pk]
    antigo.refresh_from_db()
    assert antigo.is_active is True and antigo.setor_id == setor.pk
    validar_tudo()


# ---------------------------------------------------------------------------
# Condição de corrida: ativação de setor vs. desativação do único chefe
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_ativacao_de_setor_e_desativacao_do_unico_chefe_nao_podem_ambas_vencer(admin):
    """Regressão da 002: ativar o setor e desativar o único chefe, concorrentemente,
    podiam ambas confirmar e deixar `setor.ativo=True` com zero chefes. As operações são
    serializadas pelo lock único (R2): a segunda é avaliada sobre o resultado da primeira.

    Exatamente uma é recusada, com `OperacaoRecusada` — qualquer outra exceção (deadlock,
    timeout) satisfaria "uma falhou" sem provar que a regra de negócio serializou a corrida.
    (O mesmo cenário por SQL direto, sem as operações, está em `test_contas_banco.py`.)
    """
    setor = org.provisionar_setor("Almoxarifado de Teste")
    chefe = _chefe(setor)

    resultados = rodar_em_threads(
        {
            "ativacao": lambda: org.provisionar_ativacao(setor),
            "desativacao": lambda: org.desativar_usuario(admin, chefe.pk),
        }
    )

    falhas = {nome: r for nome, r in resultados.items() if isinstance(r, Exception)}
    assert len(falhas) == 1, f"exatamente uma operação deveria ser recusada: {resultados!r}"
    assert all(isinstance(r, org.OperacaoRecusada) for r in falhas.values()), falhas
    setor.refresh_from_db()
    chefe.refresh_from_db()
    assert not (setor.ativo and not chefe.is_active)
    validar_tudo()


# ---------------------------------------------------------------------------
# INV-ORG-003: estrutural
# ---------------------------------------------------------------------------


def test_chefe_responde_por_um_unico_setor_estruturalmente(eta):
    setor, chefe = eta

    # A chefia não é um vínculo próprio: é o setor único do usuário (`INV-ORG-001`)
    # combinado ao papel. Não existe campo capaz de apontar para um segundo setor.
    assert chefe.setor_id == setor.pk
    assert Setor.objects.filter(ativo=True, user__pk=chefe.pk).count() == 1


# ---------------------------------------------------------------------------
# INV-ORG-005 / INV-ORG-006 no estado final (novas na 005)
# ---------------------------------------------------------------------------

VIOLACOES_ALMOXARIFADO = [
    pytest.param(
        lambda c: _conceder(c.membro_eta, Papel.FUNCIONARIO_ALMOXARIFADO),
        id="005_staff_fora_do_almoxarifado",
    ),
    pytest.param(
        lambda c: _conceder(c.chefe_eta, Papel.CHEFE_ALMOXARIFADO),
        id="005_head_fora_do_almoxarifado",
    ),
    pytest.param(
        _staff_em_conta_inativa_fora_do_almoxarifado,
        id="005_staff_fora_do_almoxarifado_em_conta_inativa",
    ),
    pytest.param(
        lambda c: _usuario_set(c.membro_almox, setor=c.eta),
        id="005_transferido_sem_remover_papeis_de_almoxarifado",
    ),
    pytest.param(
        lambda c: _conceder(c.membro_almox, Papel.CHEFE_ALMOXARIFADO),
        id="006_head_em_quem_nao_chefia",
    ),
    pytest.param(_dois_chefes_do_almoxarifado, id="006_dois_chefes_do_almoxarifado"),
    pytest.param(
        lambda c: _retirar(c.chefe_almox, Papel.CHEFE_ALMOXARIFADO),
        id="006_chefe_do_almoxarifado_ativo_sem_head",
    ),
    pytest.param(
        lambda c: _retirar(c.chefe_almox, Papel.FUNCIONARIO_ALMOXARIFADO),
        id="006_chefe_do_almoxarifado_sem_staff",
    ),
    pytest.param(_troca_so_da_chefia_do_setor, id="006_troca_so_da_chefia_do_setor"),
]


@pytest.mark.parametrize("violar", VIOLACOES_ALMOXARIFADO)
def test_validar_organizacao_recusa_violacoes_de_inv_org_005_e_006(cenario, violar):
    with estado_descartavel():
        violar(cenario)

        with pytest.raises(org.OperacaoRecusada) as excinfo:
            validar_tudo()

        assert excinfo.value.motivo

    validar_tudo()


def test_validar_organizacao_aceita_a_troca_completa_da_chefia_do_almoxarifado(cenario):
    """Controle: mover `ROLE-SECTOR-HEAD` e `ROLE-WAREHOUSE-HEAD` juntos (INV-ORG-006)
    produz um estado válido — as recusas acima vêm da regra, não de um cenário quebrado."""
    with estado_descartavel():
        _conceder(cenario.membro_almox, Papel.CHEFE_SETOR)
        _conceder(cenario.membro_almox, Papel.CHEFE_ALMOXARIFADO)
        _retirar(cenario.chefe_almox, Papel.CHEFE_SETOR)
        _retirar(cenario.chefe_almox, Papel.CHEFE_ALMOXARIFADO)

        validar_tudo()

        assert set(cenario.membro_almox.papeis.values_list("papel", flat=True)) == {
            Papel.REQUISITANTE,
            *PAPEIS_CHEFE_ALMOXARIFADO,
        }


def test_ex_chefe_inativo_do_almoxarifado_pode_preservar_os_papeis_de_chefia(cenario):
    """`INV-ORG-006` restringe usuários ATIVOS: a desativação preserva papéis."""
    with estado_descartavel():
        _conceder(cenario.membro_almox, Papel.CHEFE_SETOR)
        _conceder(cenario.membro_almox, Papel.CHEFE_ALMOXARIFADO)
        _retirar(cenario.chefe_almox, Papel.CHEFE_SETOR)
        _usuario_set(cenario.chefe_almox, is_active=False)  # mantém HEAD e STAFF, inativo

        validar_tudo()
