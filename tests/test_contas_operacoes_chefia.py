"""Operações de chefia (feature 005, US4 — T036): `designar_chefia`, `retirar_chefia`,
`previa_substituicao` e `substituir_chefia`, conforme `contracts/operacoes-organizacionais.md`,
FR-012, FR-014 a FR-018 e FR-052.

O que este arquivo protege, em ordem de consequência:

- a substituição troca a chefia numa operação só: o novo chefe recebe `ROLE-SECTOR-HEAD`, o anterior
  o perde, continua ativo no setor e com todos os outros papéis (FR-014); no Almoxarifado a chefia
  de estoque (`ROLE-WAREHOUSE-HEAD`) vai junto, o novo chefe recebe `ROLE-WAREHOUSE-STAFF` se faltar
  e o anterior mantém o seu (FR-016, `INV-ORG-006`); em momento nenhum o setor tem zero ou dois
  chefes (`INV-ORG-002`; a prova no banco está em `test_contas_banco.py` e a corrida em
  `test_contas_concorrencia.py`);
- designar e retirar só valem em setor INATIVO; em setor ativo a única via é a substituição
  (FR-012, FR-014); no Almoxarifado, designar concede os três papéis e retirar tira os dois de
  chefia;
- a substituição recusa o que o contrato lista (novo chefe de outro setor, inativo ou igual ao
  atual; setor inativo; `chefe_esperado_id` que já não é o chefe — FR-015, FR-017), sem escrita e
  sem evento;
- uma substituição efetivada passa a valer na consulta e na autorização seguintes (FR-052);
- toda mudança tem UM evento com autor e os alvos de `data-model.md` (FR-040).

Contratos de nome fixados pelos testes (ajustar AQUI se a implementação divergir):

- `designar_chefia(autor, setor_id, usuario_id) -> User` e `retirar_chefia(autor, setor_id) -> User`
  (o usuário que passou a ser / deixou de ser chefe);
- `previa_substituicao(setor_id, novo_chefe_id) -> PreviaSubstituicao`, só leitura, com `setor`,
  `chefe_atual`, `novo_chefe` (instâncias) e `novo_ganha` / `anterior_perde` (conjuntos de `Papel`:
  só o que MUDA — `novo_ganha` não lista o `ROLE-WAREHOUSE-STAFF` que o novo chefe já tem); recusa
  (`OperacaoRecusada`) o que a substituição recusaria quanto ao setor e ao novo chefe;
- `substituir_chefia(autor, setor_id, *, chefe_esperado_id, novo_chefe_id) -> User` (o novo chefe);
- `CHEFIA_DESIGNADA`/`CHEFIA_RETIRADA`: `usuario` e `setor`; `CHEFIA_SUBSTITUIDA`: `usuario` = novo
  chefe, `usuario_relacionado` = anterior, `setor`.
"""

import json
from types import SimpleNamespace

import pytest
from django.test import Client
from django.urls import reverse

from contas import organizacao as org
from contas.models import (
    EventoOrganizacional,
    Papel,
    PapelUsuario,
    TipoEvento,
    User,
    chefes_ativos,
    operacao_em_curso,
)
from tests.contas_helpers import (
    PAPEIS_CHEFE_ALMOXARIFADO,
    SENHA_TESTE,
    foto_organizacao,
    membro,
    operacao,
    recusa_de,
    rota,
    texto_visivel,
    validar_tudo,
)

pytestmark = pytest.mark.django_db

PAPEIS_DA_CHEFIA_DO_ALMOXARIFADO = {Papel.CHEFE_SETOR, Papel.CHEFE_ALMOXARIFADO}


@pytest.fixture
def admin():
    return membro(org.provisionar_setor("Administração"), "admin-01", {Papel.ADMINISTRADOR_SISTEMA})


@pytest.fixture
def cenario(admin):
    """ETA ativa (chefe Maria, mais Pedro e Paulo), Laboratório inativo sem chefe (Luiza e Lucas)
    e o Almoxarifado designado, INATIVO e sem chefe (Carla com `ROLE-WAREHOUSE-STAFF`, Davi sem
    papel de almoxarifado). `ativar_almoxarifado(c)` ativa o Almoxarifado com o chefe João."""
    almoxarifado = org.provisionar_setor("Almoxarifado Central", almoxarifado=True)
    eta = org.provisionar_setor("ETA")
    maria = membro(eta, "eta-maria", {Papel.CHEFE_SETOR, Papel.AUDITOR, Papel.AUXILIAR_SETOR})
    org.provisionar_ativacao(eta)
    eta.refresh_from_db()
    lab = org.provisionar_setor("Laboratório")
    return SimpleNamespace(
        admin=admin,
        almoxarifado=almoxarifado,
        carla=membro(almoxarifado, "alm-carla", {Papel.FUNCIONARIO_ALMOXARIFADO}),
        davi=membro(almoxarifado, "alm-davi"),
        eta=eta,
        maria=maria,
        pedro=membro(eta, "eta-pedro"),
        paulo=membro(eta, "eta-paulo", {Papel.AUDITOR}),
        lab=lab,
        luiza=membro(lab, "lab-luiza"),
        lucas=membro(lab, "lab-lucas"),
    )


def ativar_almoxarifado(cenario):
    """Chefe completo (João) e Almoxarifado ativo. Devolve João."""
    joao = membro(cenario.almoxarifado, "alm-joao", PAPEIS_CHEFE_ALMOXARIFADO)
    org.provisionar_ativacao(cenario.almoxarifado)
    cenario.almoxarifado.refresh_from_db()
    return joao


def _papeis(usuario):
    atribuidos = PapelUsuario.objects.filter(usuario=usuario).values_list("papel", flat=True)
    return {Papel(p) for p in atribuidos}


def _eventos(tipo):
    return EventoOrganizacional.objects.filter(tipo=tipo)


def _substituir(cenario, setor, atual, novo):
    return org.substituir_chefia(
        cenario.admin, setor.pk, chefe_esperado_id=atual.pk, novo_chefe_id=novo.pk
    )


def _quem_tem_o_papel_ativo(papel):
    return set(
        User.objects.filter(is_active=True, papeis__papel=papel).values_list("pk", flat=True)
    )


# ===========================================================================
# substituir_chefia — efeitos (FR-014, FR-016, FR-018)
# ===========================================================================


def test_substituicao_em_setor_comum_move_so_a_chefia_e_o_anterior_continua_ativo_no_setor(
    cenario,
):
    """Cenário 1 da US4."""
    devolvido = _substituir(cenario, cenario.eta, cenario.maria, cenario.pedro)

    assert devolvido.pk == cenario.pedro.pk
    assert [u.pk for u in chefes_ativos(cenario.eta.pk)] == [cenario.pedro.pk]
    cenario.maria.refresh_from_db()
    assert cenario.maria.is_active and cenario.maria.setor == cenario.eta
    assert _papeis(cenario.maria) == {Papel.REQUISITANTE, Papel.AUDITOR, Papel.AUXILIAR_SETOR}
    assert _papeis(cenario.pedro) == {Papel.REQUISITANTE, Papel.CHEFE_SETOR}
    cenario.eta.refresh_from_db()
    assert cenario.eta.ativo is True, "a substituição não desativa o setor"
    validar_tudo()


def test_o_novo_chefe_mantem_os_papeis_que_ja_tinha(cenario):
    _substituir(cenario, cenario.eta, cenario.maria, cenario.paulo)

    assert _papeis(cenario.paulo) == {Papel.REQUISITANTE, Papel.AUDITOR, Papel.CHEFE_SETOR}


def test_substituicao_no_almoxarifado_move_a_chefia_de_estoque_junto(cenario):
    """Cenário 3 da US4: Carla (com `ROLE-WAREHOUSE-STAFF`) assume; João fica só com o de
    funcionário dentre os papéis de almoxarifado; nunca dois `ROLE-WAREHOUSE-HEAD`."""
    joao = ativar_almoxarifado(cenario)

    _substituir(cenario, cenario.almoxarifado, joao, cenario.carla)

    assert _papeis(cenario.carla) == {Papel.REQUISITANTE, *PAPEIS_CHEFE_ALMOXARIFADO}
    assert _papeis(joao) == {Papel.REQUISITANTE, Papel.FUNCIONARIO_ALMOXARIFADO}
    assert _quem_tem_o_papel_ativo(Papel.CHEFE_ALMOXARIFADO) == {cenario.carla.pk}
    assert [u.pk for u in chefes_ativos(cenario.almoxarifado.pk)] == [cenario.carla.pk]
    joao.refresh_from_db()
    assert joao.is_active and joao.setor == cenario.almoxarifado
    validar_tudo()


def test_novo_chefe_do_almoxarifado_sem_papel_de_funcionario_recebe_o_na_mesma_operacao(cenario):
    """Cenário 4 da US4."""
    joao = ativar_almoxarifado(cenario)
    assert Papel.FUNCIONARIO_ALMOXARIFADO not in _papeis(cenario.davi)

    _substituir(cenario, cenario.almoxarifado, joao, cenario.davi)

    assert _papeis(cenario.davi) == {Papel.REQUISITANTE, *PAPEIS_CHEFE_ALMOXARIFADO}
    evento = _eventos(TipoEvento.CHEFIA_SUBSTITUIDA).get()
    registrado = json.dumps(evento.dados, ensure_ascii=False)
    assert Papel.FUNCIONARIO_ALMOXARIFADO.value in registrado, "o evento mostra a concessão extra"
    validar_tudo()


def test_o_chefe_anterior_pode_voltar_pela_mesma_operacao_sem_prazo_nem_retorno_automatico(
    cenario,
):
    """FR-018: cobertura temporária é só uma segunda substituição, a pedido do administrador."""
    _substituir(cenario, cenario.eta, cenario.maria, cenario.pedro)
    assert [u.pk for u in chefes_ativos(cenario.eta.pk)] == [cenario.pedro.pk]

    _substituir(cenario, cenario.eta, cenario.pedro, cenario.maria)

    assert [u.pk for u in chefes_ativos(cenario.eta.pk)] == [cenario.maria.pk]
    assert _papeis(cenario.pedro) == {Papel.REQUISITANTE}
    assert _eventos(TipoEvento.CHEFIA_SUBSTITUIDA).count() == 2
    validar_tudo()


# ---------------------------------------------------------------------------
# Evento (FR-040) e fichas (FR-042)
# ---------------------------------------------------------------------------


def test_substituicao_grava_um_evento_com_autor_novo_chefe_chefe_anterior_e_setor(cenario):
    _substituir(cenario, cenario.eta, cenario.maria, cenario.pedro)

    evento = _eventos(TipoEvento.CHEFIA_SUBSTITUIDA).get()
    assert evento.autor == cenario.admin
    assert evento.usuario == cenario.pedro
    assert evento.usuario_relacionado == cenario.maria
    assert evento.setor == cenario.eta
    assert (
        EventoOrganizacional.objects.filter(
            tipo__in=[TipoEvento.CHEFIA_DESIGNADA, TipoEvento.CHEFIA_RETIRADA]
        ).count()
        == 0
    ), "a substituição é UM evento, não uma retirada mais uma designação"


def test_o_evento_da_substituicao_aparece_nas_fichas_dos_dois_usuarios_e_do_setor(cenario, client):
    _substituir(cenario, cenario.eta, cenario.maria, cenario.pedro)
    client.force_login(cenario.admin)
    rotulo = TipoEvento.CHEFIA_SUBSTITUIDA.label

    for destino in (
        rota("usuario", cenario.pedro.pk),
        rota("usuario", cenario.maria.pk),
        rota("setor", cenario.eta.pk),
    ):
        resposta = client.get(destino)
        assert resposta.status_code == 200
        assert rotulo in texto_visivel(resposta.content.decode()), destino


# ---------------------------------------------------------------------------
# FR-052: vale na consulta e na autorização seguintes
# ---------------------------------------------------------------------------


def test_depois_da_substituicao_a_consulta_de_chefes_devolve_so_o_novo_chefe(cenario):
    assert [u.pk for u in chefes_ativos(cenario.eta.pk)] == [cenario.maria.pk]

    _substituir(cenario, cenario.eta, cenario.maria, cenario.pedro)

    assert [u.pk for u in chefes_ativos(cenario.eta.pk)] == [cenario.pedro.pk]
    assert not User.objects.get(pk=cenario.maria.pk).tem_papel(Papel.CHEFE_SETOR)
    assert User.objects.get(pk=cenario.pedro.pk).tem_papel(Papel.CHEFE_SETOR)


def test_a_chefia_de_estoque_perdida_deixa_de_autorizar_na_requisicao_seguinte_da_mesma_sessao(
    cenario,
):
    """FR-052 de ponta a ponta: a importação do catálogo exige `ROLE-WAREHOUSE-HEAD`. O chefe
    antigo, com a sessão já aberta, perde o acesso; o novo chefe ganha."""
    joao = ativar_almoxarifado(cenario)
    sessao_de_joao, sessao_de_carla = Client(), Client()
    sessao_de_joao.force_login(joao)
    sessao_de_carla.force_login(cenario.carla)
    importacao = reverse("catalogo:importacao_envio")
    assert sessao_de_joao.get(importacao).status_code == 200
    assert sessao_de_carla.get(importacao).status_code == 403

    _substituir(cenario, cenario.almoxarifado, joao, cenario.carla)

    assert sessao_de_joao.get(importacao).status_code == 403
    assert sessao_de_carla.get(importacao).status_code == 200


# ---------------------------------------------------------------------------
# previa_substituicao (FR-049)
# ---------------------------------------------------------------------------


def test_previa_em_setor_comum_lista_o_que_cada_pessoa_ganha_e_perde(cenario):
    previa = org.previa_substituicao(cenario.eta.pk, cenario.pedro.pk)

    assert previa.setor == cenario.eta
    assert previa.chefe_atual == cenario.maria
    assert previa.novo_chefe == cenario.pedro
    assert set(previa.novo_ganha) == {Papel.CHEFE_SETOR}
    assert set(previa.anterior_perde) == {Papel.CHEFE_SETOR}


def test_previa_no_almoxarifado_inclui_a_chefia_de_estoque_e_o_funcionario_que_falta(cenario):
    joao = ativar_almoxarifado(cenario)

    com_funcionario = org.previa_substituicao(cenario.almoxarifado.pk, cenario.carla.pk)
    sem_funcionario = org.previa_substituicao(cenario.almoxarifado.pk, cenario.davi.pk)

    assert com_funcionario.chefe_atual == joao
    assert set(com_funcionario.novo_ganha) == PAPEIS_DA_CHEFIA_DO_ALMOXARIFADO
    assert set(sem_funcionario.novo_ganha) == {
        *PAPEIS_DA_CHEFIA_DO_ALMOXARIFADO,
        Papel.FUNCIONARIO_ALMOXARIFADO,
    }
    for previa in (com_funcionario, sem_funcionario):
        assert set(previa.anterior_perde) == PAPEIS_DA_CHEFIA_DO_ALMOXARIFADO


def test_a_previa_e_so_leitura_e_recusa_o_que_a_substituicao_recusaria(cenario):
    antes = foto_organizacao()

    org.previa_substituicao(cenario.eta.pk, cenario.pedro.pk)

    assert foto_organizacao() == antes, "a prévia não escreve papel nem evento"
    recusa_de(lambda: org.previa_substituicao(cenario.eta.pk, cenario.luiza.pk))  # outro setor
    recusa_de(lambda: org.previa_substituicao(cenario.eta.pk, cenario.maria.pk))  # o próprio chefe
    recusa_de(lambda: org.previa_substituicao(cenario.lab.pk, cenario.luiza.pk))  # setor inativo
    assert foto_organizacao() == antes


# ---------------------------------------------------------------------------
# substituir_chefia — recusas (FR-015, FR-017; sem escrita, sem evento)
# ---------------------------------------------------------------------------


def _inativo_da_eta(c):
    return membro(c.eta, "eta-inativo", is_active=False)


def _conta_tecnica_na_eta(c):
    return User.objects.create_superuser(
        matricula="tecnica-eta", password=SENHA_TESTE, setor=c.eta, nome="Conta Técnica"
    )


def _depois_de_outra_substituicao(c):
    """O chefe esperado (Maria) já não é o chefe: Pedro assumiu."""
    _substituir(c, c.eta, c.maria, c.pedro)
    return c.eta.pk, c.maria.pk, c.paulo.pk


# (id, prepara(cenario) -> (setor_id, chefe_esperado_id, novo_chefe_id), exige caminho?)
RECUSAS_DE_SUBSTITUICAO = [
    pytest.param(
        lambda c: (c.eta.pk, c.maria.pk, c.luiza.pk), True, id="novo-chefe-de-outro-setor"
    ),
    pytest.param(
        lambda c: (c.eta.pk, c.maria.pk, _inativo_da_eta(c).pk), False, id="novo-chefe-inativo"
    ),
    pytest.param(
        lambda c: (c.eta.pk, c.maria.pk, c.maria.pk), False, id="novo-chefe-igual-ao-atual"
    ),
    pytest.param(
        lambda c: (c.lab.pk, c.luiza.pk, c.lucas.pk), True, id="setor-inativo-usa-a-designacao"
    ),
    pytest.param(
        lambda c: (c.eta.pk, c.pedro.pk, c.paulo.pk),
        False,
        id="chefe-esperado-nunca-foi-o-chefe",
    ),
    pytest.param(_depois_de_outra_substituicao, False, id="chefe-esperado-ja-foi-substituido"),
    pytest.param(lambda c: (c.eta.pk, c.maria.pk, 987_654_321), False, id="novo-chefe-inexistente"),
    pytest.param(
        lambda c: (c.eta.pk, c.maria.pk, _conta_tecnica_na_eta(c).pk),
        False,
        id="conta-tecnica-nao-vira-chefe",
    ),
]


@pytest.mark.parametrize("preparar, exige_caminho", RECUSAS_DE_SUBSTITUICAO)
def test_substituicao_recusada_nao_escreve_nada_nem_gera_evento(cenario, preparar, exige_caminho):
    setor_id, esperado_id, novo_id = preparar(cenario)
    antes = foto_organizacao()

    recusa = recusa_de(
        lambda: org.substituir_chefia(
            cenario.admin, setor_id, chefe_esperado_id=esperado_id, novo_chefe_id=novo_id
        )
    )

    assert recusa.motivo
    if exige_caminho:
        assert recusa.caminho, "FR-048: a recusa indica o caminho para resolver"
    assert foto_organizacao() == antes, "recusa não pode deixar papel nem evento"
    assert not operacao_em_curso()
    validar_tudo()


def test_substituicao_no_almoxarifado_com_chefe_esperado_desatualizado_nao_move_a_chefia_de_estoque(
    cenario,
):
    joao = ativar_almoxarifado(cenario)
    _substituir(cenario, cenario.almoxarifado, joao, cenario.carla)
    antes = foto_organizacao()

    recusa_de(lambda: _substituir(cenario, cenario.almoxarifado, joao, cenario.davi))

    assert foto_organizacao() == antes
    assert _quem_tem_o_papel_ativo(Papel.CHEFE_ALMOXARIFADO) == {cenario.carla.pk}


def test_sem_evento_nao_ha_substituicao(cenario, monkeypatch):
    """FR-041/FR-047: se o evento não puder ser gravado, a troca de papéis também desaparece."""
    antes = foto_organizacao()

    def _falha(self, *args, **kwargs):
        raise RuntimeError("falha simulada ao gravar o evento")

    with monkeypatch.context() as patch:
        patch.setattr(EventoOrganizacional, "save", _falha)
        with pytest.raises(RuntimeError):
            _substituir(cenario, cenario.eta, cenario.maria, cenario.pedro)

    assert foto_organizacao() == antes
    assert [u.pk for u in chefes_ativos(cenario.eta.pk)] == [cenario.maria.pk]
    assert not operacao_em_curso()


# ---------------------------------------------------------------------------
# substituir_chefia — prévia desatualizada (FR-049)
# ---------------------------------------------------------------------------


def _substituir_como_na_previa(cenario, setor, atual, novo):
    """Confirma com os efeitos que a prévia mostrou, como a tela de confirmação faz."""
    previa = org.previa_substituicao(setor.pk, novo.pk)
    return previa, lambda: org.substituir_chefia(
        cenario.admin,
        setor.pk,
        chefe_esperado_id=atual.pk,
        novo_chefe_id=novo.pk,
        novo_ganha_previsto=previa.novo_ganha,
        anterior_perde_previsto=previa.anterior_perde,
    )


def test_confirmar_com_os_efeitos_da_previa_executa_a_substituicao(cenario):
    joao = ativar_almoxarifado(cenario)
    previa, confirmar = _substituir_como_na_previa(
        cenario, cenario.almoxarifado, joao, cenario.carla
    )

    assert confirmar() == cenario.carla

    assert set(previa.novo_ganha) == PAPEIS_DA_CHEFIA_DO_ALMOXARIFADO
    assert _quem_tem_o_papel_ativo(Papel.CHEFE_ALMOXARIFADO) == {cenario.carla.pk}


def test_papel_que_a_previa_nao_mostrava_ao_novo_chefe_deixa_a_previa_desatualizada(cenario):
    """A prévia de Carla não lista `ROLE-WAREHOUSE-STAFF` em "Recebe" porque ela já o tinha; se
    o papel é retirado antes da confirmação, a substituição passaria a conceder algo que a
    pessoa não viu: a operação não executa e devolve a prévia nova."""
    joao = ativar_almoxarifado(cenario)
    previa, confirmar = _substituir_como_na_previa(
        cenario, cenario.almoxarifado, joao, cenario.carla
    )
    assert Papel.FUNCIONARIO_ALMOXARIFADO not in previa.novo_ganha
    org.alterar_papeis(
        cenario.admin,
        cenario.carla.pk,
        conceder=set(),
        remover={Papel.FUNCIONARIO_ALMOXARIFADO},
    )
    antes = foto_organizacao()

    with pytest.raises(org.PreviaDesatualizada) as excinfo:
        confirmar()

    assert foto_organizacao() == antes, "não escreve papel nem evento"
    nova = excinfo.value.previa
    assert nova.chefe_atual == joao and nova.novo_chefe == cenario.carla
    assert set(nova.novo_ganha) == {
        *PAPEIS_DA_CHEFIA_DO_ALMOXARIFADO,
        Papel.FUNCIONARIO_ALMOXARIFADO,
    }
    assert set(nova.anterior_perde) == PAPEIS_DA_CHEFIA_DO_ALMOXARIFADO
    assert _quem_tem_o_papel_ativo(Papel.CHEFE_ALMOXARIFADO) == {joao.pk}


def test_papel_que_o_chefe_anterior_perderia_a_mais_ou_a_menos_deixa_a_previa_desatualizada(
    cenario,
):
    """O que o chefe anterior perde também é conferido: aqui a prévia anuncia perder só a
    chefia de setor, mas o chefe do Almoxarifado perderia também a de estoque."""
    joao = ativar_almoxarifado(cenario)
    antes = foto_organizacao()

    with pytest.raises(org.PreviaDesatualizada) as excinfo:
        org.substituir_chefia(
            cenario.admin,
            cenario.almoxarifado.pk,
            chefe_esperado_id=joao.pk,
            novo_chefe_id=cenario.carla.pk,
            novo_ganha_previsto={Papel.CHEFE_SETOR, Papel.CHEFE_ALMOXARIFADO},
            anterior_perde_previsto={Papel.CHEFE_SETOR},
        )

    assert set(excinfo.value.previa.anterior_perde) == PAPEIS_DA_CHEFIA_DO_ALMOXARIFADO
    assert foto_organizacao() == antes


def test_chefe_esperado_desatualizado_continua_recusado_mesmo_com_efeitos_previstos(cenario):
    previa, confirmar = _substituir_como_na_previa(
        cenario, cenario.eta, cenario.maria, cenario.pedro
    )
    _substituir(cenario, cenario.eta, cenario.maria, cenario.paulo)
    antes = foto_organizacao()

    recusa_de(confirmar)

    assert foto_organizacao() == antes


def test_efeito_previsto_com_papel_desconhecido_e_recusado_sem_escrever(cenario):
    antes = foto_organizacao()

    recusa_de(
        lambda: org.substituir_chefia(
            cenario.admin,
            cenario.eta.pk,
            chefe_esperado_id=cenario.maria.pk,
            novo_chefe_id=cenario.pedro.pk,
            novo_ganha_previsto={"ROLE-INEXISTENTE"},
        )
    )

    assert foto_organizacao() == antes


# ===========================================================================
# designar_chefia (FR-012)
# ===========================================================================


def test_designar_em_setor_inativo_sem_chefe_concede_a_chefia_e_nao_ativa_o_setor(cenario):
    devolvido = org.designar_chefia(cenario.admin, cenario.lab.pk, cenario.luiza.pk)

    assert devolvido.pk == cenario.luiza.pk
    assert _papeis(cenario.luiza) == {Papel.REQUISITANTE, Papel.CHEFE_SETOR}
    assert [u.pk for u in chefes_ativos(cenario.lab.pk)] == [cenario.luiza.pk]
    cenario.lab.refresh_from_db()
    assert cenario.lab.ativo is False
    evento = _eventos(TipoEvento.CHEFIA_DESIGNADA).get()
    assert evento.autor == cenario.admin
    assert evento.usuario == cenario.luiza and evento.setor == cenario.lab
    validar_tudo()


def test_o_setor_com_chefe_designado_pode_ser_ativado(cenario):
    """US7, cenário 3: a designação é o que habilita a ativação."""
    org.designar_chefia(cenario.admin, cenario.lab.pk, cenario.luiza.pk)

    org.provisionar_ativacao(cenario.lab)

    cenario.lab.refresh_from_db()
    assert cenario.lab.ativo is True


@pytest.mark.parametrize(
    "candidato", ["davi", "carla"], ids=["sem-papel-de-funcionario", "ja-e-funcionario"]
)
def test_designar_no_almoxarifado_concede_os_tres_papeis_e_o_funcionario_so_se_faltar(
    cenario, candidato
):
    """US7, cenário 7 (FR-012, `INV-ORG-006`)."""
    escolhido = getattr(cenario, candidato)

    org.designar_chefia(cenario.admin, cenario.almoxarifado.pk, escolhido.pk)

    assert _papeis(escolhido) == {Papel.REQUISITANTE, *PAPEIS_CHEFE_ALMOXARIFADO}
    assert (
        PapelUsuario.objects.filter(usuario=escolhido, papel=Papel.FUNCIONARIO_ALMOXARIFADO).count()
        == 1
    )
    validar_tudo()
    org.provisionar_ativacao(cenario.almoxarifado)  # com os três papéis, o Almoxarifado ativa
    cenario.almoxarifado.refresh_from_db()
    assert cenario.almoxarifado.ativo is True


def test_ex_chefe_inativo_que_preservou_o_papel_nao_impede_designar_outro(cenario):
    """Só o chefe ATIVO conta (`INV-ORG-002`): a desativação preserva papéis (FR-016a)."""
    ex_chefe = membro(cenario.lab, "lab-ex-chefe", is_active=False)
    with operacao():
        PapelUsuario.objects.create(usuario=ex_chefe, papel=Papel.CHEFE_SETOR)

    org.designar_chefia(cenario.admin, cenario.lab.pk, cenario.luiza.pk)

    assert [u.pk for u in chefes_ativos(cenario.lab.pk)] == [cenario.luiza.pk]
    validar_tudo()


def _lab_que_ja_tem_chefe(c):
    org.designar_chefia(c.admin, c.lab.pk, c.luiza.pk)
    return c.lab.pk, c.lucas.pk


# (id, prepara(cenario) -> (setor_id, usuario_id), exige caminho?)
RECUSAS_DE_DESIGNACAO = [
    pytest.param(lambda c: (c.eta.pk, c.pedro.pk), True, id="setor-ativo-usa-a-substituicao"),
    pytest.param(_lab_que_ja_tem_chefe, False, id="setor-inativo-que-ja-tem-chefe-ativo"),
    pytest.param(
        lambda c: (c.lab.pk, membro(c.lab, "lab-inativo", is_active=False).pk),
        False,
        id="usuario-inativo",
    ),
    pytest.param(
        lambda c: (c.lab.pk, c.pedro.pk), True, id="usuario-de-outro-setor-transfere-antes"
    ),
    pytest.param(
        lambda c: (
            c.lab.pk,
            User.objects.create_superuser(
                matricula="tecnica-lab", password=SENHA_TESTE, setor=c.lab, nome="Conta Técnica"
            ).pk,
        ),
        False,
        id="conta-tecnica",
    ),
    pytest.param(lambda c: (c.lab.pk, 987_654_321), False, id="usuario-inexistente"),
]


@pytest.mark.parametrize("preparar, exige_caminho", RECUSAS_DE_DESIGNACAO)
def test_designacao_recusada_nao_escreve_nada_nem_gera_evento(cenario, preparar, exige_caminho):
    setor_id, usuario_id = preparar(cenario)
    antes = foto_organizacao()

    recusa = recusa_de(lambda: org.designar_chefia(cenario.admin, setor_id, usuario_id))

    assert recusa.motivo
    if exige_caminho:
        assert recusa.caminho, "FR-048: a recusa indica o caminho para resolver"
    assert foto_organizacao() == antes
    assert not operacao_em_curso()


# ===========================================================================
# retirar_chefia (FR-012)
# ===========================================================================


def test_retirar_a_chefia_de_setor_inativo_tira_o_papel_e_deixa_o_setor_sem_chefe(cenario):
    org.designar_chefia(cenario.admin, cenario.lab.pk, cenario.luiza.pk)

    devolvido = org.retirar_chefia(cenario.admin, cenario.lab.pk)

    assert devolvido.pk == cenario.luiza.pk
    assert _papeis(cenario.luiza) == {Papel.REQUISITANTE}
    assert chefes_ativos(cenario.lab.pk).count() == 0
    evento = _eventos(TipoEvento.CHEFIA_RETIRADA).get()
    assert evento.autor == cenario.admin
    assert evento.usuario == cenario.luiza and evento.setor == cenario.lab
    validar_tudo()
    # e outra pessoa pode ser designada em seguida
    org.designar_chefia(cenario.admin, cenario.lab.pk, cenario.lucas.pk)
    assert [u.pk for u in chefes_ativos(cenario.lab.pk)] == [cenario.lucas.pk]


def test_retirar_a_chefia_do_almoxarifado_inativo_tira_a_chefia_de_estoque_e_mantem_o_funcionario(
    cenario,
):
    org.designar_chefia(cenario.admin, cenario.almoxarifado.pk, cenario.carla.pk)

    org.retirar_chefia(cenario.admin, cenario.almoxarifado.pk)

    assert _papeis(cenario.carla) == {Papel.REQUISITANTE, Papel.FUNCIONARIO_ALMOXARIFADO}
    assert _quem_tem_o_papel_ativo(Papel.CHEFE_ALMOXARIFADO) == set()
    validar_tudo()


def test_retirar_a_chefia_de_setor_ativo_e_recusado_e_indica_a_substituicao(cenario):
    antes = foto_organizacao()

    recusa = recusa_de(lambda: org.retirar_chefia(cenario.admin, cenario.eta.pk))

    assert recusa.motivo and recusa.caminho
    assert foto_organizacao() == antes
    assert [u.pk for u in chefes_ativos(cenario.eta.pk)] == [cenario.maria.pk]


def test_retirar_a_chefia_de_setor_inativo_sem_chefe_ativo_e_recusado(cenario):
    antes = foto_organizacao()

    recusa_de(lambda: org.retirar_chefia(cenario.admin, cenario.lab.pk))

    assert foto_organizacao() == antes
    assert not operacao_em_curso()
