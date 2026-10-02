"""Administração de setores (feature 005, US7 — T050): `criar_setor`, `renomear_setor`,
`ativar_setor` e `desativar_setor`, conforme `contracts/operacoes-organizacionais.md`, FR-025 a
FR-030, FR-053, `INV-ORG-002`, `INV-ORG-004` e `INV-ORG-006`.

O que este arquivo protege, em ordem de consequência:

- o setor nasce INATIVO e nunca como Almoxarifado (a designação é só do provisionamento); o nome é
  único sem diferenciar caixa nem espaços nas pontas, na criação e na renomeação (FR-025, FR-026);
- a ativação exige exatamente um chefe ativo do próprio setor e, no Almoxarifado, a chefia de
  estoque completa; `ativado_em` registra só a PRIMEIRA ativação (FR-027, FR-030);
- a desativação só vale com o chefe como único membro ativo — membros inativos e a conta técnica
  não impedem —, lista os demais membros na recusa e NUNCA vale para o Almoxarifado já ativado
  (FR-028, FR-029, `INV-ORG-004`); o chefe mantém `ROLE-SECTOR-HEAD` depois (D-16);
- renomear o Almoxarifado mantém a designação, o estado e `ativado_em`;
- toda recusa deixa o estado intacto e sem evento; cada efetivação grava um evento com autor e é
  atômica com ele (FR-040, FR-041, FR-047); operação sem efeito não gera evento.

Contratos de nome fixados pelos testes (ajustar AQUI se a implementação divergir): as quatro
operações recebem `(autor, ...)` e devolvem o `Setor` (instância); `SETOR_CRIADO`,
`SETOR_RENOMEADO`, `SETOR_ATIVADO` e `SETOR_DESATIVADO` têm `setor` e `autor`, e nenhum
`usuario`; a lista dos demais membros ativos vem no `motivo`/`caminho` da recusa de
`desativar_setor` (o nome ou a matrícula de cada um). As corridas de criação e renomeação
concorrentes estão em `test_contas_concorrencia.py`.
"""

import json
from types import SimpleNamespace

import pytest
from django.test import Client

from contas import organizacao as org
from contas.models import (
    EventoOrganizacional,
    Papel,
    PapelUsuario,
    Setor,
    TipoEvento,
    User,
    chefes_ativos,
    operacao_em_curso,
)
from tests.contas_helpers import (
    PAPEIS_CHEFE_ALMOXARIFADO,
    SENHA_TESTE,
    almoxarifado_ativo,
    foto_organizacao,
    membro,
    recusa_de,
    rota,
    setor_ativo,
    texto_principal,
    validar_tudo,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    return membro(
        org.provisionar_setor("Administração"), "admin-01", {Papel.ADMINISTRADOR_SISTEMA}
    )


@pytest.fixture
def cenario(admin):
    """ETA ativa (chefe Maria, membros ativos Pedro e Paula), Laboratório inativo sem chefe (Luiza)
    e um setor "Solo" ativo em que o chefe é o único membro."""
    eta, maria = setor_ativo("ETA", "eta-maria")
    solo, chefe_solo = setor_ativo("Solo", "solo-chefe")
    lab = org.provisionar_setor("Laboratório")
    return SimpleNamespace(
        admin=admin,
        eta=eta,
        maria=maria,
        pedro=membro(eta, "eta-pedro"),
        paula=membro(eta, "eta-paula"),
        solo=solo,
        chefe_solo=chefe_solo,
        lab=lab,
        luiza=membro(lab, "lab-luiza"),
    )


def _eventos(tipo):
    return EventoOrganizacional.objects.filter(tipo=tipo)


def _papeis(usuario):
    atribuidos = PapelUsuario.objects.filter(usuario=usuario).values_list("papel", flat=True)
    return {Papel(p) for p in atribuidos}


def _texto_da_recusa(recusa):
    return f"{recusa.motivo} {recusa.caminho or ''}"


# ===========================================================================
# criar_setor (FR-025, FR-026)
# ===========================================================================


def test_criar_setor_nasce_inativo_comum_e_sem_espacos_nas_pontas(cenario):
    setor = org.criar_setor(cenario.admin, nome="  Compras  ")

    setor = Setor.objects.get(pk=setor.pk)
    assert setor.nome == "Compras"
    assert setor.ativo is False and setor.ativado_em is None
    assert setor.almoxarifado is False, "FR-026: nunca designado como Almoxarifado"
    validar_tudo()


def test_criar_setor_grava_um_evento_com_autor_e_o_setor_como_alvo(cenario):
    setor = org.criar_setor(cenario.admin, nome="Compras")

    evento = _eventos(TipoEvento.SETOR_CRIADO).get(setor=setor)
    assert evento.autor == cenario.admin and evento.usuario is None
    assert "Compras" in json.dumps(evento.dados, ensure_ascii=False)


def test_o_setor_criado_nao_tem_chefe_nem_membros_e_nao_pode_ser_ativado_ainda(cenario):
    setor = org.criar_setor(cenario.admin, nome="Compras")

    assert chefes_ativos(setor.pk).count() == 0
    assert User.objects.filter(setor=setor).count() == 0
    recusa_de(lambda: org.ativar_setor(cenario.admin, setor.pk))


@pytest.mark.parametrize(
    "nome",
    [
        pytest.param(" eta ", id="caixa-e-espacos-diante-de-ETA"),
        pytest.param("ETA", id="igual"),
        pytest.param("Eta", id="so-a-caixa"),
        pytest.param("\tEta\n", id="outros-espacos-nas-pontas"),
        pytest.param("", id="vazio"),
        pytest.param("   ", id="so-espacos"),
        pytest.param("x" * 101, id="maior-que-o-limite-do-campo"),
    ],
)
def test_criar_setor_recusado_nao_escreve_nada_nem_gera_evento(cenario, nome):
    """O setor de teste "ETA" já existe. A comparação do nome ignora caixa e espaços nas pontas
    (FR-025); a recusa é de domínio (`OperacaoRecusada`), nunca um erro do banco."""
    antes = foto_organizacao()

    recusa = recusa_de(lambda: org.criar_setor(cenario.admin, nome=nome))

    assert recusa.motivo
    assert foto_organizacao() == antes
    assert not operacao_em_curso()


def test_sem_evento_nao_ha_setor_criado(cenario, monkeypatch):
    antes = foto_organizacao()

    def _falha(self, *args, **kwargs):
        raise RuntimeError("falha simulada ao gravar o evento")

    with monkeypatch.context() as patch:
        patch.setattr(EventoOrganizacional, "save", _falha)
        with pytest.raises(RuntimeError):
            org.criar_setor(cenario.admin, nome="Compras")

    assert foto_organizacao() == antes
    assert not operacao_em_curso()


# ===========================================================================
# renomear_setor (FR-025)
# ===========================================================================


def test_renomear_muda_o_nome_e_registra_anterior_e_novo(cenario):
    devolvido = org.renomear_setor(cenario.admin, cenario.lab.pk, nome="  Laboratório Central ")

    assert devolvido.pk == cenario.lab.pk
    cenario.lab.refresh_from_db()
    assert cenario.lab.nome == "Laboratório Central"
    evento = _eventos(TipoEvento.SETOR_RENOMEADO).get()
    assert evento.autor == cenario.admin and evento.setor == cenario.lab
    registrado = json.dumps(evento.dados, ensure_ascii=False)
    assert "Laboratório Central" in registrado and "Laboratório" in registrado
    validar_tudo()


def test_o_mesmo_setor_pode_mudar_so_a_caixa_do_proprio_nome(cenario):
    """O setor não conflita consigo mesmo: "ETA" → "Eta" é uma renomeação válida."""
    org.renomear_setor(cenario.admin, cenario.eta.pk, nome="Eta")

    cenario.eta.refresh_from_db()
    assert cenario.eta.nome == "Eta"
    assert _eventos(TipoEvento.SETOR_RENOMEADO).count() == 1


@pytest.mark.parametrize("nome", ["Laboratório", "  Laboratório  "])
def test_renomear_para_o_mesmo_nome_nao_gera_evento(cenario, nome):
    antes = foto_organizacao()

    devolvido = org.renomear_setor(cenario.admin, cenario.lab.pk, nome=nome)

    assert devolvido.pk == cenario.lab.pk
    assert foto_organizacao() == antes


@pytest.mark.parametrize(
    "nome",
    [
        pytest.param(" eta ", id="caixa-e-espacos-de-outro-setor"),
        pytest.param("SOLO", id="caixa-de-outro-setor"),
        pytest.param("", id="vazio"),
        pytest.param("   ", id="so-espacos"),
        pytest.param("y" * 101, id="maior-que-o-limite-do-campo"),
    ],
)
def test_renomear_recusado_nao_escreve_nada_nem_gera_evento(cenario, nome):
    antes = foto_organizacao()

    recusa = recusa_de(lambda: org.renomear_setor(cenario.admin, cenario.lab.pk, nome=nome))

    assert recusa.motivo
    assert foto_organizacao() == antes
    assert not operacao_em_curso()


def test_renomear_setor_inexistente_e_recusado(cenario):
    antes = foto_organizacao()

    recusa_de(lambda: org.renomear_setor(cenario.admin, 987_654_321, nome="Qualquer"))

    assert foto_organizacao() == antes


def test_renomear_o_almoxarifado_mantem_a_designacao_o_estado_e_a_ativacao(admin):
    """Edge case da spec: a designação não depende do nome (`INV-ORG-004`)."""
    almoxarifado, _ = almoxarifado_ativo()
    ativado_em = almoxarifado.ativado_em

    org.renomear_setor(admin, almoxarifado.pk, nome="Depósito Geral")

    almoxarifado.refresh_from_db()
    assert almoxarifado.nome == "Depósito Geral"
    assert almoxarifado.almoxarifado is True
    assert almoxarifado.ativo is True and almoxarifado.ativado_em == ativado_em
    validar_tudo()


def test_sem_evento_nao_ha_renomeacao(cenario, monkeypatch):
    antes = foto_organizacao()

    def _falha(self, *args, **kwargs):
        raise RuntimeError("falha simulada ao gravar o evento")

    with monkeypatch.context() as patch:
        patch.setattr(EventoOrganizacional, "save", _falha)
        with pytest.raises(RuntimeError):
            org.renomear_setor(cenario.admin, cenario.lab.pk, nome="Outro Nome")

    assert foto_organizacao() == antes


# ===========================================================================
# ativar_setor (FR-027, FR-030)
# ===========================================================================


def test_ativar_setor_com_chefe_designado_ativa_e_registra_a_primeira_ativacao(cenario):
    """Cenário 3 da US7: designar e, depois, ativar."""
    org.designar_chefia(cenario.admin, cenario.lab.pk, cenario.luiza.pk)

    devolvido = org.ativar_setor(cenario.admin, cenario.lab.pk)

    assert devolvido.pk == cenario.lab.pk
    cenario.lab.refresh_from_db()
    assert cenario.lab.ativo is True and cenario.lab.ativado_em is not None
    assert [u.pk for u in chefes_ativos(cenario.lab.pk)] == [cenario.luiza.pk]
    evento = _eventos(TipoEvento.SETOR_ATIVADO).get(setor=cenario.lab)
    assert evento.autor == cenario.admin
    assert cenario.luiza.matricula in json.dumps(evento.dados), "o evento registra o chefe"
    validar_tudo()


def test_ativado_em_so_registra_a_primeira_ativacao_e_a_reativacao_segue_as_mesmas_condicoes(
    cenario,
):
    """FR-030: o setor tem um único estado inativo; `ativado_em` (imutável) diz que já esteve ativo.
    Reativar exige de novo um chefe ativo; desativado o setor, o chefe mantém a chefia."""
    org.designar_chefia(cenario.admin, cenario.lab.pk, cenario.luiza.pk)
    org.ativar_setor(cenario.admin, cenario.lab.pk)
    primeira = Setor.objects.get(pk=cenario.lab.pk).ativado_em
    org.desativar_setor(cenario.admin, cenario.lab.pk)  # Luiza é a única ativa do Laboratório

    inativo = Setor.objects.get(pk=cenario.lab.pk)
    assert inativo.ativo is False and inativo.ativado_em == primeira
    assert Papel.CHEFE_SETOR in _papeis(cenario.luiza), "o chefe mantém a chefia (FR-028)"

    org.retirar_chefia(cenario.admin, cenario.lab.pk)
    antes = foto_organizacao()
    recusa_de(lambda: org.ativar_setor(cenario.admin, cenario.lab.pk))  # sem chefe: como a ativação
    assert foto_organizacao() == antes

    org.designar_chefia(cenario.admin, cenario.lab.pk, cenario.luiza.pk)
    org.ativar_setor(cenario.admin, cenario.lab.pk)

    reativado = Setor.objects.get(pk=cenario.lab.pk)
    assert reativado.ativo is True
    assert reativado.ativado_em == primeira, "a primeira ativação não é reescrita"
    assert _eventos(TipoEvento.SETOR_ATIVADO).filter(setor=cenario.lab).count() == 2
    assert _eventos(TipoEvento.SETOR_DESATIVADO).filter(setor=cenario.lab).count() == 1
    validar_tudo()


def _sem_chefe(c):
    """O Laboratório não tem chefe próprio; o chefe da ETA não o habilita (`INV-ORG-002`)."""
    return c.lab.pk


def _chefe_inativo(c):
    org.designar_chefia(c.admin, c.lab.pk, c.luiza.pk)
    org.desativar_usuario(c.admin, c.luiza.pk)
    return c.lab.pk


def _almoxarifado_sem_a_chefia_de_estoque(c):
    """Chefe do Almoxarifado com `ROLE-SECTOR-HEAD` e `ROLE-WAREHOUSE-STAFF`, mas sem
    `ROLE-WAREHOUSE-HEAD` (estado válido enquanto o setor está inativo): `INV-ORG-006`."""
    almoxarifado = org.provisionar_setor("Almoxarifado Central", almoxarifado=True)
    membro(almoxarifado, "alm-chefe", {Papel.CHEFE_SETOR, Papel.FUNCIONARIO_ALMOXARIFADO})
    return almoxarifado.pk


# (id, prepara(cenario) -> setor_id, exige caminho?)
RECUSAS_DE_ATIVACAO = [
    pytest.param(_sem_chefe, True, id="sem-chefe-ativo"),
    pytest.param(_chefe_inativo, False, id="unico-chefe-esta-inativo"),
    pytest.param(
        _almoxarifado_sem_a_chefia_de_estoque, False, id="almoxarifado-sem-chefia-estoque"
    ),
    pytest.param(lambda c: 987_654_321, False, id="setor-inexistente"),
]


@pytest.mark.parametrize("preparar, exige_caminho", RECUSAS_DE_ATIVACAO)
def test_ativacao_recusada_nao_escreve_nada_nem_gera_evento(cenario, preparar, exige_caminho):
    setor_id = preparar(cenario)
    antes = foto_organizacao()

    recusa = recusa_de(lambda: org.ativar_setor(cenario.admin, setor_id))

    assert recusa.motivo
    if exige_caminho:
        assert recusa.caminho, "FR-048: indica designar a chefia antes"
    assert foto_organizacao() == antes
    assert not Setor.objects.filter(pk=setor_id, ativo=True).exists()
    assert not operacao_em_curso()
    validar_tudo()


def test_ativar_setor_ja_ativo_nao_tem_efeito_nem_evento(cenario):
    antes = foto_organizacao()

    devolvido = org.ativar_setor(cenario.admin, cenario.eta.pk)

    assert devolvido.pk == cenario.eta.pk
    assert foto_organizacao() == antes


def test_o_almoxarifado_com_a_chefia_completa_ativa(admin):
    """`INV-ORG-006`: designar no Almoxarifado concede os três papéis, e o setor ativa."""
    almoxarifado = org.provisionar_setor("Almoxarifado Central", almoxarifado=True)
    chefe = membro(almoxarifado, "alm-chefe")
    org.designar_chefia(admin, almoxarifado.pk, chefe.pk)

    org.ativar_setor(admin, almoxarifado.pk)

    almoxarifado.refresh_from_db()
    assert almoxarifado.ativo is True
    assert _papeis(chefe) == {Papel.REQUISITANTE, *PAPEIS_CHEFE_ALMOXARIFADO}
    validar_tudo()


def test_sem_evento_nao_ha_ativacao(cenario, monkeypatch):
    org.designar_chefia(cenario.admin, cenario.lab.pk, cenario.luiza.pk)
    antes = foto_organizacao()

    def _falha(self, *args, **kwargs):
        raise RuntimeError("falha simulada ao gravar o evento")

    with monkeypatch.context() as patch:
        patch.setattr(EventoOrganizacional, "save", _falha)
        with pytest.raises(RuntimeError):
            org.ativar_setor(cenario.admin, cenario.lab.pk)

    assert foto_organizacao() == antes
    cenario.lab.refresh_from_db()
    assert cenario.lab.ativo is False and cenario.lab.ativado_em is None


# ===========================================================================
# desativar_setor (FR-028, FR-029, FR-053)
# ===========================================================================


def test_desativar_setor_em_que_o_chefe_e_o_unico_membro_ativo(cenario):
    ativado_em = cenario.solo.ativado_em

    devolvido = org.desativar_setor(cenario.admin, cenario.solo.pk)

    assert devolvido.pk == cenario.solo.pk
    cenario.solo.refresh_from_db()
    assert cenario.solo.ativo is False and cenario.solo.ativado_em == ativado_em
    chefe = User.objects.get(pk=cenario.chefe_solo.pk)
    assert chefe.is_active and chefe.setor == cenario.solo
    assert Papel.CHEFE_SETOR in _papeis(chefe), "D-16: o chefe mantém a chefia"
    evento = _eventos(TipoEvento.SETOR_DESATIVADO).get()
    assert evento.autor == cenario.admin and evento.setor == cenario.solo
    assert cenario.chefe_solo.matricula in json.dumps(evento.dados), "o evento registra o chefe"
    validar_tudo()


def test_o_chefe_do_setor_desativado_pode_ser_transferido_e_desativado_depois(cenario):
    org.desativar_setor(cenario.admin, cenario.solo.pk)

    org.transferir_usuario(
        cenario.admin,
        cenario.chefe_solo.pk,
        cenario.lab.pk,
        papeis_removidos_previstos={Papel.CHEFE_SETOR},
    )

    assert User.objects.get(pk=cenario.chefe_solo.pk).setor == cenario.lab
    validar_tudo()


def test_desativar_com_outros_membros_ativos_e_recusado_listando_os_membros(cenario):
    """Cenário 5 da US7: Pedro e Paula ainda estão ativos na ETA."""
    antes = foto_organizacao()

    recusa = recusa_de(lambda: org.desativar_setor(cenario.admin, cenario.eta.pk))

    texto = _texto_da_recusa(recusa)
    for outro in (cenario.pedro, cenario.paula):
        assert outro.nome in texto or outro.matricula in texto, f"a recusa lista {outro.nome}"
    assert recusa.caminho, "FR-048: transfira ou desative antes"
    assert foto_organizacao() == antes
    assert Setor.objects.get(pk=cenario.eta.pk).ativo is True
    assert not operacao_em_curso()


def test_depois_de_transferir_ou_desativar_os_membros_a_desativacao_e_aceita(cenario):
    org.transferir_usuario(
        cenario.admin, cenario.pedro.pk, cenario.lab.pk, papeis_removidos_previstos=set()
    )
    org.desativar_usuario(cenario.admin, cenario.paula.pk)

    org.desativar_setor(cenario.admin, cenario.eta.pk)

    assert Setor.objects.get(pk=cenario.eta.pk).ativo is False
    validar_tudo()


def test_membros_inativos_nao_impedem_a_desativacao(cenario):
    inativo = membro(cenario.solo, "solo-inativo", is_active=False)

    org.desativar_setor(cenario.admin, cenario.solo.pk)

    inativo.refresh_from_db()
    assert Setor.objects.get(pk=cenario.solo.pk).ativo is False
    assert inativo.setor == cenario.solo, "os membros inativos permanecem vinculados"


def test_a_conta_tecnica_do_setor_nao_conta_como_membro(cenario):
    """FR-028, edge case "Conta técnica vinculada a um setor"."""
    User.objects.create_superuser(
        matricula="tecnica-solo", password=SENHA_TESTE, setor=cenario.solo, nome="Conta Técnica"
    )

    org.desativar_setor(cenario.admin, cenario.solo.pk)

    assert Setor.objects.get(pk=cenario.solo.pk).ativo is False


def test_a_conta_tecnica_tambem_nao_aparece_na_lista_dos_membros_que_impedem(cenario):
    User.objects.create_superuser(
        matricula="tecnica-eta", password=SENHA_TESTE, setor=cenario.eta, nome="Conta Técnica Eta"
    )

    recusa = recusa_de(lambda: org.desativar_setor(cenario.admin, cenario.eta.pk))

    texto = _texto_da_recusa(recusa)
    assert "Conta Técnica Eta" not in texto and "tecnica-eta" not in texto


def test_o_almoxarifado_ativado_nunca_e_desativado(admin):
    """`INV-ORG-004` (FR-029): nem quando o chefe é o único membro ativo."""
    almoxarifado, chefe = almoxarifado_ativo()
    antes = foto_organizacao()

    recusa = recusa_de(lambda: org.desativar_setor(admin, almoxarifado.pk))

    assert recusa.motivo
    assert foto_organizacao() == antes
    almoxarifado.refresh_from_db()
    assert almoxarifado.ativo is True
    assert chefe.tem_papel(Papel.CHEFE_ALMOXARIFADO)
    validar_tudo()


def test_desativar_setor_ja_inativo_nao_tem_efeito_nem_evento(cenario):
    antes = foto_organizacao()

    devolvido = org.desativar_setor(cenario.admin, cenario.lab.pk)

    assert devolvido.pk == cenario.lab.pk
    assert foto_organizacao() == antes


def test_desativar_setor_inexistente_e_recusado(cenario):
    antes = foto_organizacao()

    recusa_de(lambda: org.desativar_setor(cenario.admin, 987_654_321))

    assert foto_organizacao() == antes


def test_sem_evento_nao_ha_desativacao_de_setor(cenario, monkeypatch):
    antes = foto_organizacao()

    def _falha(self, *args, **kwargs):
        raise RuntimeError("falha simulada ao gravar o evento")

    with monkeypatch.context() as patch:
        patch.setattr(EventoOrganizacional, "save", _falha)
        with pytest.raises(RuntimeError):
            org.desativar_setor(cenario.admin, cenario.solo.pk)

    assert foto_organizacao() == antes
    assert Setor.objects.get(pk=cenario.solo.pk).ativo is True
    assert not operacao_em_curso()


# ===========================================================================
# Histórico: o setor que já esteve ativo aparece como tal (FR-030, cenário 4 da US2)
# ===========================================================================


def test_a_ficha_do_setor_desativado_mostra_que_ele_ja_esteve_ativo(cenario):
    org.desativar_setor(cenario.admin, cenario.solo.pk)
    client = Client()
    client.force_login(cenario.admin)

    desativado = client.get(rota("setor", cenario.solo.pk))
    nunca_ativo = client.get(rota("setor", cenario.lab.pk))

    assert TipoEvento.SETOR_ATIVADO.label in texto_principal(desativado.content.decode())
    assert TipoEvento.SETOR_DESATIVADO.label in texto_principal(desativado.content.decode())
    assert TipoEvento.SETOR_ATIVADO.label not in texto_principal(nunca_ativo.content.decode())


@pytest.mark.parametrize(
    "nome", [pytest.param("ETA", id="igual"), pytest.param(" eta ", id="caixa")]
)
def test_nome_de_setor_repetido_recusa_com_motivo_e_caminho(cenario, nome):
    """FR-048: a recusa por nome repetido diz o que fazer, não só o que houve."""
    recusa = recusa_de(lambda: org.criar_setor(cenario.admin, nome=nome))

    assert recusa.motivo
    assert recusa.caminho
