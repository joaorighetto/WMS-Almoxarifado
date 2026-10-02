"""Situação do usuário (feature 005, US5 — T041): `desativar_usuario`, `previa_reativacao` e
`reativar_usuario`, conforme `contracts/operacoes-organizacionais.md`, FR-019 a FR-024, FR-021,
`INV-AUTH-001`, `INV-ORG-002`, `INV-ORG-005` e `INV-ORG-006`.

O que este arquivo protege, em ordem de consequência:

- desativar corta o acesso na interação seguinte, inclusive em sessão aberta (`INV-AUTH-001`), e
  PRESERVA todos os papéis (FR-016a da 002, FR-019); reativar devolve o acesso com a mesma
  credencial;
- nenhuma desativação deixa a organização inválida: o chefe de setor ATIVO (inclusive o do
  Almoxarifado), a própria conta do autor e o último administrador ativo são recusados (FR-020,
  FR-022); em setor INATIVO o chefe pode ser desativado e mantém a chefia preservada;
- a desativação nunca é bloqueada por registros de outro recorte nem os altera (FR-021, FR-051);
- a reativação mostra os papéis preservados (`previa_reativacao`), devolve EXATAMENTE o que foi
  confirmado e recusa, com o motivo por papel, o que violaria `INV-ORG-002` (segundo chefe),
  `INV-ORG-005` ou `INV-ORG-006` — desmarcando o papel, prossegue (FR-023, FR-024); `ROLE-REQUESTER`
  é sempre mantido e a reativação nunca concede um papel que a conta não tinha;
- toda recusa deixa o estado intacto e sem evento; desativação e reativação são atômicas com o
  evento (FR-041, FR-047); a corrida contra `alterar_papeis` está em `test_contas_concorrencia.py`.

Contratos de nome fixados pelos testes (ajustar AQUI se a implementação divergir):

- `desativar_usuario(autor, usuario_id, *, justificativa="") -> User`; `USUARIO_DESATIVADO` com
  `usuario` e `setor` (o do usuário), `justificativa` no campo próprio e nenhuma senha;
- `previa_reativacao(usuario_id) -> PreviaReativacao`, só leitura, com `usuario` (instância),
  `papeis_preservados` (os papéis que a conta tem hoje, `ROLE-REQUESTER` incluído, na ordem do
  catálogo) e `recusas` (`dict[Papel, OperacaoRecusada]`: só os papéis preservados que, mantidos,
  violariam uma regra — o mesmo `motivo` que `reativar_usuario` levanta ao mantê-los);
- `reativar_usuario(autor, usuario_id, *, papeis_mantidos: set[Papel]) -> User`; `USUARIO_REATIVADO`
  com `usuario` e `setor` e, em `dados`, os papéis confirmados e os desmarcados.
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
    membro_provisorio,
    recusa_de,
    rota,
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
    """ETA ativa (chefe Maria, mais Pedro, com `ROLE-AUDITOR` e `ROLE-SECTOR-ASSISTANT`),
    Laboratório inativo sem chefe (Luiza e Lucas) e o Almoxarifado designado, INATIVO e sem chefe
    (João sem papel de almoxarifado e Carla com `ROLE-WAREHOUSE-STAFF`)."""
    almoxarifado = org.provisionar_setor("Almoxarifado Central", almoxarifado=True)
    eta = org.provisionar_setor("ETA")
    maria = membro(eta, "eta-maria", {Papel.CHEFE_SETOR})
    org.provisionar_ativacao(eta)
    eta.refresh_from_db()
    lab = org.provisionar_setor("Laboratório")
    return SimpleNamespace(
        admin=admin,
        almoxarifado=almoxarifado,
        joao=membro(almoxarifado, "alm-joao"),
        carla=membro(almoxarifado, "alm-carla", {Papel.FUNCIONARIO_ALMOXARIFADO}),
        eta=eta,
        maria=maria,
        pedro=membro(eta, "eta-pedro", {Papel.AUDITOR, Papel.AUXILIAR_SETOR}),
        lab=lab,
        luiza=membro(lab, "lab-luiza"),
        lucas=membro(lab, "lab-lucas"),
    )


def _papeis(usuario):
    atribuidos = PapelUsuario.objects.filter(usuario=usuario).values_list("papel", flat=True)
    return {Papel(p) for p in atribuidos}


def _eventos(tipo):
    return EventoOrganizacional.objects.filter(tipo=tipo)


def _ex_chefe_do_laboratorio(c):
    """Luiza era a chefe do Laboratório (inativo): foi desativada — permitido em setor inativo —
    preservando `ROLE-SECTOR-HEAD`; Lucas foi designado e o Laboratório, ativado. Pelas operações
    reais, não por escrita direta."""
    org.designar_chefia(c.admin, c.lab.pk, c.luiza.pk)
    org.desativar_usuario(c.admin, c.luiza.pk)
    org.designar_chefia(c.admin, c.lab.pk, c.lucas.pk)
    org.provisionar_ativacao(c.lab)
    return User.objects.get(pk=c.luiza.pk)


def _ex_chefe_do_almoxarifado(c):
    """Mesma história no Almoxarifado: João (os três papéis) é desativado enquanto o setor está
    inativo; Carla é designada e o Almoxarifado, ativado."""
    org.designar_chefia(c.admin, c.almoxarifado.pk, c.joao.pk)
    org.desativar_usuario(c.admin, c.joao.pk)
    org.designar_chefia(c.admin, c.almoxarifado.pk, c.carla.pk)
    org.provisionar_ativacao(c.almoxarifado)
    return User.objects.get(pk=c.joao.pk)


def _almoxarifado_ativo_com_chefe(c):
    chefe = membro(c.almoxarifado, "alm-chefe", PAPEIS_CHEFE_ALMOXARIFADO)
    org.provisionar_ativacao(c.almoxarifado)
    return chefe


# ===========================================================================
# desativar_usuario — efeitos (FR-019)
# ===========================================================================


def test_desativar_inativa_a_conta_e_preserva_todos_os_papeis(cenario):
    devolvido = org.desativar_usuario(cenario.admin, cenario.pedro.pk)

    assert devolvido.pk == cenario.pedro.pk
    cenario.pedro.refresh_from_db()
    assert cenario.pedro.is_active is False
    assert cenario.pedro.setor == cenario.eta, "a desativação não tira a pessoa do setor"
    assert _papeis(cenario.pedro) == {Papel.REQUISITANTE, Papel.AUDITOR, Papel.AUXILIAR_SETOR}
    validar_tudo()


def test_desativar_grava_um_evento_com_autor_alvo_setor_e_justificativa(cenario):
    org.desativar_usuario(cenario.admin, cenario.pedro.pk, justificativa="Aposentadoria")

    evento = _eventos(TipoEvento.USUARIO_DESATIVADO).get()
    assert evento.autor == cenario.admin
    assert evento.usuario == cenario.pedro and evento.setor == cenario.eta
    assert evento.justificativa == "Aposentadoria"
    assert "Aposentadoria" not in json.dumps(evento.dados), "a justificativa tem campo próprio"


def test_a_justificativa_e_opcional(cenario):
    org.desativar_usuario(cenario.admin, cenario.pedro.pk)

    evento = _eventos(TipoEvento.USUARIO_DESATIVADO).get()
    assert evento.justificativa == ""


def test_sessao_aberta_perde_o_acesso_na_interacao_seguinte_e_nao_volta_a_autenticar(cenario):
    """`INV-AUTH-001`, SC-006: a sessão já aberta e um novo login são recusados; os papéis,
    porém, continuam registrados."""
    sessao = Client()
    sessao.force_login(cenario.pedro)
    assert sessao.get(rota("home")).status_code == 200

    org.desativar_usuario(cenario.admin, cenario.pedro.pk)

    resposta = sessao.get(rota("home"))
    assert resposta.status_code == 302 and resposta.url.startswith(rota("login"))
    assert Client().login(username=cenario.pedro.matricula, password=SENHA_TESTE) is False
    assert Papel.AUDITOR in _papeis(cenario.pedro)


def test_desativar_chefe_de_setor_inativo_e_permitido_e_preserva_a_chefia(cenario):
    """Edge case da spec: `INV-ORG-002` só exige chefe de setor ATIVO."""
    org.designar_chefia(cenario.admin, cenario.lab.pk, cenario.luiza.pk)

    org.desativar_usuario(cenario.admin, cenario.luiza.pk)

    assert chefes_ativos(cenario.lab.pk).count() == 0
    assert Papel.CHEFE_SETOR in _papeis(cenario.luiza), "o papel fica registrado (FR-019)"
    validar_tudo()


def test_desativar_com_outro_administrador_ativo_e_permitido_e_o_remanescente_vira_o_ultimo(
    cenario,
):
    outro = membro(cenario.eta, "eta-outro-admin", {Papel.ADMINISTRADOR_SISTEMA})

    org.desativar_usuario(cenario.admin, outro.pk)  # sobra um administrador: permitido

    outro.refresh_from_db()
    assert outro.is_active is False
    recusa = recusa_de(lambda: org.desativar_usuario(cenario.pedro, cenario.admin.pk))
    assert recusa.motivo, "agora ele é o último administrador ativo (D-15)"


def test_desativar_conta_ja_inativa_nao_tem_efeito_nem_evento(cenario):
    org.desativar_usuario(cenario.admin, cenario.pedro.pk)
    antes = foto_organizacao()

    devolvido = org.desativar_usuario(cenario.admin, cenario.pedro.pk, justificativa="De novo")

    assert devolvido.pk == cenario.pedro.pk
    assert foto_organizacao() == antes
    assert _eventos(TipoEvento.USUARIO_DESATIVADO).count() == 1


# ===========================================================================
# desativar_usuario — recusas (FR-020, FR-022; sem escrita, sem evento)
# ===========================================================================


def _admin_unico_com_autor_comum(c):
    """O alvo é o último administrador ativo e quem pede é outra pessoa."""
    return c.pedro, c.admin


def _propria_conta_com_outro_administrador(c):
    membro(c.eta, "eta-outro-admin", {Papel.ADMINISTRADOR_SISTEMA})
    return c.admin, c.admin


def _chefe_do_almoxarifado_ativo(c):
    return c.admin, _almoxarifado_ativo_com_chefe(c)


def _conta_tecnica(c):
    tecnica = User.objects.create_superuser(
        matricula="tecnica-01", password=SENHA_TESTE, setor=c.eta, nome="Conta Técnica"
    )
    return c.admin, tecnica


# (id, prepara(cenario) -> (autor, alvo), exige caminho?)
RECUSAS_DE_DESATIVACAO = [
    pytest.param(lambda c: (c.admin, c.maria), True, id="chefe-de-setor-ativo"),
    pytest.param(_chefe_do_almoxarifado_ativo, True, id="chefe-do-almoxarifado-ativo"),
    pytest.param(_admin_unico_com_autor_comum, False, id="ultimo-administrador-ativo"),
    pytest.param(_propria_conta_com_outro_administrador, False, id="propria-conta"),
    pytest.param(_conta_tecnica, False, id="conta-tecnica"),
]


@pytest.mark.parametrize("preparar, exige_caminho", RECUSAS_DE_DESATIVACAO)
def test_desativacao_recusada_nao_escreve_nada_nem_gera_evento(cenario, preparar, exige_caminho):
    autor, alvo = preparar(cenario)
    antes = foto_organizacao()

    recusa = recusa_de(lambda: org.desativar_usuario(autor, alvo.pk, justificativa="Tentativa"))

    assert recusa.motivo
    if exige_caminho:
        assert recusa.caminho, "FR-048: indica substituir a chefia antes"
    assert foto_organizacao() == antes
    assert User.objects.get(pk=alvo.pk).is_active is True
    assert not operacao_em_curso()
    validar_tudo()


def test_desativar_usuario_inexistente_e_recusado(cenario):
    antes = foto_organizacao()

    recusa_de(lambda: org.desativar_usuario(cenario.admin, 987_654_321))

    assert foto_organizacao() == antes


def test_sem_evento_nao_ha_desativacao(cenario, monkeypatch):
    """FR-041/FR-047: se o evento não puder ser gravado, a conta continua ativa."""
    antes = foto_organizacao()

    def _falha(self, *args, **kwargs):
        raise RuntimeError("falha simulada ao gravar o evento")

    with monkeypatch.context() as patch:
        patch.setattr(EventoOrganizacional, "save", _falha)
        with pytest.raises(RuntimeError):
            org.desativar_usuario(cenario.admin, cenario.pedro.pk)

    assert foto_organizacao() == antes
    assert not operacao_em_curso()


# ===========================================================================
# FR-021: nunca bloqueada por registros de outro recorte
# ===========================================================================


def test_desativar_nao_e_bloqueada_nem_altera_registros_de_outros_recortes(
    admin, execucao_catalogo, execucao_fornecedores
):
    """Quem autoria importações (catálogo e fornecedores) é desativado sem recusa, e as
    importações — autoria incluída — continuam exatamente como estavam (FR-021, FR-051)."""
    from catalogo.models import ExecucaoImportacao
    from fornecedores.models import ExecucaoImportacaoFornecedores

    importacoes = list(ExecucaoImportacao.objects.values())
    importacoes_fornecedores = list(ExecucaoImportacaoFornecedores.objects.values())
    autores = [execucao_catalogo.executada_por, execucao_fornecedores.executada_por]

    for autor_da_importacao in autores:
        org.desativar_usuario(admin, autor_da_importacao.pk)

    assert all(User.objects.get(pk=a.pk).is_active is False for a in autores)
    assert list(ExecucaoImportacao.objects.values()) == importacoes
    assert list(ExecucaoImportacaoFornecedores.objects.values()) == importacoes_fornecedores


# ===========================================================================
# previa_reativacao (FR-023, FR-049)
# ===========================================================================


def test_previa_lista_os_papeis_preservados_com_o_requisitante(cenario):
    org.desativar_usuario(cenario.admin, cenario.pedro.pk)

    previa = org.previa_reativacao(cenario.pedro.pk)

    assert previa.usuario.pk == cenario.pedro.pk
    assert set(previa.papeis_preservados) == {
        Papel.REQUISITANTE,
        Papel.AUDITOR,
        Papel.AUXILIAR_SETOR,
    }
    assert previa.recusas == {}, "nada neste conjunto violaria regra"


def test_a_previa_e_so_leitura(cenario):
    org.desativar_usuario(cenario.admin, cenario.pedro.pk)
    antes = foto_organizacao()

    org.previa_reativacao(cenario.pedro.pk)

    assert foto_organizacao() == antes, "a prévia não reativa, não altera papel e não gera evento"


def test_previa_do_ex_chefe_de_setor_que_ja_tem_outro_chefe_indica_o_papel_recusado(cenario):
    ex_chefe = _ex_chefe_do_laboratorio(cenario)

    previa = org.previa_reativacao(ex_chefe.pk)

    assert set(previa.papeis_preservados) == {Papel.REQUISITANTE, Papel.CHEFE_SETOR}
    assert set(previa.recusas) == {Papel.CHEFE_SETOR}
    assert previa.recusas[Papel.CHEFE_SETOR].motivo


def test_previa_do_ex_chefe_do_almoxarifado_recusa_as_duas_chefias_e_nao_o_funcionario(cenario):
    ex_chefe = _ex_chefe_do_almoxarifado(cenario)

    previa = org.previa_reativacao(ex_chefe.pk)

    assert set(previa.papeis_preservados) == {Papel.REQUISITANTE, *PAPEIS_CHEFE_ALMOXARIFADO}
    assert set(previa.recusas) == {Papel.CHEFE_SETOR, Papel.CHEFE_ALMOXARIFADO}


# ===========================================================================
# reativar_usuario — efeitos (FR-023)
# ===========================================================================


def test_reativar_com_todos_os_papeis_devolve_o_acesso_e_o_que_foi_confirmado(cenario):
    org.desativar_usuario(cenario.admin, cenario.pedro.pk)
    previa = org.previa_reativacao(cenario.pedro.pk)

    devolvido = org.reativar_usuario(
        cenario.admin, cenario.pedro.pk, papeis_mantidos=set(previa.papeis_preservados)
    )

    assert devolvido.pk == cenario.pedro.pk
    cenario.pedro.refresh_from_db()
    assert cenario.pedro.is_active is True and cenario.pedro.setor == cenario.eta
    assert _papeis(cenario.pedro) == {Papel.REQUISITANTE, Papel.AUDITOR, Papel.AUXILIAR_SETOR}
    evento = _eventos(TipoEvento.USUARIO_REATIVADO).get()
    assert evento.autor == cenario.admin
    assert evento.usuario == cenario.pedro and evento.setor == cenario.eta
    validar_tudo()


def test_o_resultado_e_exatamente_o_confirmado_o_desmarcado_e_removido(cenario):
    org.desativar_usuario(cenario.admin, cenario.pedro.pk)

    org.reativar_usuario(
        cenario.admin, cenario.pedro.pk, papeis_mantidos={Papel.REQUISITANTE, Papel.AUDITOR}
    )

    assert _papeis(cenario.pedro) == {Papel.REQUISITANTE, Papel.AUDITOR}
    evento = _eventos(TipoEvento.USUARIO_REATIVADO).get()
    registrado = json.dumps(evento.dados, ensure_ascii=False)
    assert Papel.AUXILIAR_SETOR.value in registrado, "o evento registra o papel desmarcado"
    assert Papel.AUDITOR.value in registrado, "e os confirmados"


def test_reativar_nao_altera_a_credencial_e_devolve_o_acesso(cenario):
    """Assumptions da spec: a conta volta com a senha que tinha — inclusive uma provisória."""
    usuario, _ = membro_provisorio(cenario.eta, "eta-provisorio")
    org.desativar_usuario(cenario.admin, usuario.pk)
    desativado = User.objects.get(pk=usuario.pk)

    org.reativar_usuario(cenario.admin, usuario.pk, papeis_mantidos={Papel.REQUISITANTE})

    reativado = User.objects.get(pk=usuario.pk)
    assert reativado.is_active is True
    assert reativado.password == desativado.password
    assert reativado.senha_provisoria_em == desativado.senha_provisoria_em is not None


def test_conta_reativada_volta_a_autenticar(cenario):
    assert Client().login(username=cenario.pedro.matricula, password=SENHA_TESTE) is True
    org.desativar_usuario(cenario.admin, cenario.pedro.pk)
    assert Client().login(username=cenario.pedro.matricula, password=SENHA_TESTE) is False

    org.reativar_usuario(
        cenario.admin, cenario.pedro.pk, papeis_mantidos={Papel.REQUISITANTE, Papel.AUDITOR}
    )

    assert Client().login(username=cenario.pedro.matricula, password=SENHA_TESTE) is True


def test_reativar_em_setor_inativo_e_permitido(cenario):
    org.desativar_usuario(cenario.admin, cenario.luiza.pk)

    org.reativar_usuario(cenario.admin, cenario.luiza.pk, papeis_mantidos={Papel.REQUISITANTE})

    cenario.luiza.refresh_from_db()
    assert cenario.luiza.is_active is True and cenario.lab.ativo is False


def test_ex_chefe_de_setor_inativo_sem_outro_chefe_volta_como_chefe_mantendo_a_chefia(cenario):
    """Edge case da spec: "reativação em setor inativo"."""
    org.designar_chefia(cenario.admin, cenario.lab.pk, cenario.luiza.pk)
    org.desativar_usuario(cenario.admin, cenario.luiza.pk)

    org.reativar_usuario(
        cenario.admin,
        cenario.luiza.pk,
        papeis_mantidos={Papel.REQUISITANTE, Papel.CHEFE_SETOR},
    )

    assert [u.pk for u in chefes_ativos(cenario.lab.pk)] == [cenario.luiza.pk]
    validar_tudo()


def test_ex_chefe_do_almoxarifado_inativo_sem_outro_chefe_volta_com_os_tres_papeis(cenario):
    org.designar_chefia(cenario.admin, cenario.almoxarifado.pk, cenario.joao.pk)
    org.desativar_usuario(cenario.admin, cenario.joao.pk)

    org.reativar_usuario(
        cenario.admin,
        cenario.joao.pk,
        papeis_mantidos={Papel.REQUISITANTE, *PAPEIS_CHEFE_ALMOXARIFADO},
    )

    assert _papeis(cenario.joao) == {Papel.REQUISITANTE, *PAPEIS_CHEFE_ALMOXARIFADO}
    assert [u.pk for u in chefes_ativos(cenario.almoxarifado.pk)] == [cenario.joao.pk]
    validar_tudo()


# ===========================================================================
# reativar_usuario — recusas (FR-023, FR-024, `INV-ORG-002`, `INV-ORG-006`)
# ===========================================================================


def test_reativar_mantendo_papel_que_viola_regra_e_recusado_com_o_motivo_do_papel(cenario):
    """Cenário 5 da US5: o setor já tem outro chefe ativo."""
    ex_chefe = _ex_chefe_do_laboratorio(cenario)
    previa = org.previa_reativacao(ex_chefe.pk)
    antes = foto_organizacao()

    recusa = recusa_de(
        lambda: org.reativar_usuario(
            cenario.admin,
            ex_chefe.pk,
            papeis_mantidos={Papel.REQUISITANTE, Papel.CHEFE_SETOR},
        )
    )

    assert recusa.motivo == previa.recusas[Papel.CHEFE_SETOR].motivo
    assert recusa.caminho, "FR-048: indica desmarcar o papel"
    assert foto_organizacao() == antes
    assert User.objects.get(pk=ex_chefe.pk).is_active is False
    assert [u.pk for u in chefes_ativos(cenario.lab.pk)] == [cenario.lucas.pk]
    assert not operacao_em_curso()


def test_desmarcando_o_papel_recusado_a_reativacao_prossegue(cenario):
    ex_chefe = _ex_chefe_do_laboratorio(cenario)

    org.reativar_usuario(cenario.admin, ex_chefe.pk, papeis_mantidos={Papel.REQUISITANTE})

    ex_chefe.refresh_from_db()
    assert ex_chefe.is_active is True
    assert _papeis(ex_chefe) == {Papel.REQUISITANTE}
    assert [u.pk for u in chefes_ativos(cenario.lab.pk)] == [cenario.lucas.pk]
    validar_tudo()


def test_ex_chefe_de_setor_inativo_que_ja_tem_outro_chefe_tambem_e_recusado(cenario):
    """FR-022 da 002 vale para o setor, ativo ou não: um segundo chefe nunca."""
    org.designar_chefia(cenario.admin, cenario.lab.pk, cenario.luiza.pk)
    org.desativar_usuario(cenario.admin, cenario.luiza.pk)
    org.designar_chefia(cenario.admin, cenario.lab.pk, cenario.lucas.pk)  # setor segue inativo
    antes = foto_organizacao()

    recusa_de(
        lambda: org.reativar_usuario(
            cenario.admin,
            cenario.luiza.pk,
            papeis_mantidos={Papel.REQUISITANTE, Papel.CHEFE_SETOR},
        )
    )

    assert foto_organizacao() == antes


MANTER_AS_CHEFIAS_DO_ALMOXARIFADO = [
    pytest.param(
        {Papel.REQUISITANTE, *PAPEIS_CHEFE_ALMOXARIFADO}, id="os-tres-papeis-de-chefia"
    ),
    pytest.param(
        {Papel.REQUISITANTE, Papel.CHEFE_SETOR, Papel.FUNCIONARIO_ALMOXARIFADO},
        id="so-a-chefia-do-setor",
    ),
    pytest.param(
        {Papel.REQUISITANTE, Papel.CHEFE_ALMOXARIFADO, Papel.FUNCIONARIO_ALMOXARIFADO},
        id="so-a-chefia-de-estoque",
    ),
]


@pytest.mark.parametrize("mantidos", MANTER_AS_CHEFIAS_DO_ALMOXARIFADO)
def test_ex_chefe_do_almoxarifado_nao_volta_com_nenhuma_das_chefias_enquanto_ha_outro_chefe(
    cenario, mantidos
):
    """`INV-ORG-002` e `INV-ORG-006`: ambos os papéis precisam ser desmarcados."""
    ex_chefe = _ex_chefe_do_almoxarifado(cenario)
    antes = foto_organizacao()

    recusa_de(
        lambda: org.reativar_usuario(cenario.admin, ex_chefe.pk, papeis_mantidos=set(mantidos))
    )

    assert foto_organizacao() == antes
    assert [u.pk for u in chefes_ativos(cenario.almoxarifado.pk)] == [cenario.carla.pk]


@pytest.mark.parametrize(
    "mantidos",
    [
        pytest.param({Papel.REQUISITANTE, Papel.FUNCIONARIO_ALMOXARIFADO}, id="mantem-funcionario"),
        pytest.param({Papel.REQUISITANTE}, id="desmarca-tudo-o-que-da-para-desmarcar"),
    ],
)
def test_desmarcadas_as_chefias_o_ex_chefe_do_almoxarifado_volta(cenario, mantidos):
    ex_chefe = _ex_chefe_do_almoxarifado(cenario)

    org.reativar_usuario(cenario.admin, ex_chefe.pk, papeis_mantidos=set(mantidos))

    ex_chefe.refresh_from_db()
    assert ex_chefe.is_active is True
    assert _papeis(ex_chefe) == set(mantidos)
    assert [u.pk for u in chefes_ativos(cenario.almoxarifado.pk)] == [cenario.carla.pk]
    validar_tudo()


def test_role_requester_e_sempre_mantido_na_reativacao(cenario):
    """Cenário 6 da US5 (FR-023): `papeis_mantidos` sem `ROLE-REQUESTER` não é aceito."""
    org.desativar_usuario(cenario.admin, cenario.pedro.pk)
    antes = foto_organizacao()

    recusa = recusa_de(
        lambda: org.reativar_usuario(
            cenario.admin, cenario.pedro.pk, papeis_mantidos={Papel.AUDITOR}
        )
    )

    assert recusa.motivo
    assert foto_organizacao() == antes
    assert User.objects.get(pk=cenario.pedro.pk).is_active is False


def test_reativar_nunca_concede_um_papel_que_a_conta_nao_tinha(cenario):
    """Escalada de privilégio: pedir para "manter" `ROLE-SYSTEM-ADMIN` numa conta que nunca o
    teve não pode concedê-lo. A operação pode recusar ou ignorar o papel alheio — nunca
    concedê-lo."""
    org.desativar_usuario(cenario.admin, cenario.pedro.pk)
    antes = foto_organizacao()

    try:
        org.reativar_usuario(
            cenario.admin,
            cenario.pedro.pk,
            papeis_mantidos={Papel.REQUISITANTE, Papel.AUDITOR, Papel.ADMINISTRADOR_SISTEMA},
        )
    except org.OperacaoRecusada:
        assert foto_organizacao() == antes

    assert Papel.ADMINISTRADOR_SISTEMA not in _papeis(cenario.pedro)
    assert _papeis(cenario.pedro) <= {Papel.REQUISITANTE, Papel.AUDITOR, Papel.AUXILIAR_SETOR}
    validar_tudo()


def test_reativar_conta_ja_ativa_nao_tem_efeito_nem_evento(cenario):
    antes = foto_organizacao()

    devolvido = org.reativar_usuario(
        cenario.admin, cenario.pedro.pk, papeis_mantidos={Papel.REQUISITANTE}
    )

    assert devolvido.pk == cenario.pedro.pk
    assert foto_organizacao() == antes, "os papéis de uma conta ativa não são tocados"
    assert _eventos(TipoEvento.USUARIO_REATIVADO).count() == 0


def test_reativar_conta_tecnica_ou_inexistente_e_recusado(cenario):
    tecnica = User.objects.create_superuser(
        matricula="tecnica-01", password=SENHA_TESTE, setor=cenario.eta, nome="Conta Técnica"
    )
    antes = foto_organizacao()

    recusa_de(lambda: org.reativar_usuario(cenario.admin, tecnica.pk, papeis_mantidos=set()))
    recusa_de(lambda: org.reativar_usuario(cenario.admin, 987_654_321, papeis_mantidos=set()))

    assert foto_organizacao() == antes


def test_sem_evento_nao_ha_reativacao(cenario, monkeypatch):
    org.desativar_usuario(cenario.admin, cenario.pedro.pk)
    antes = foto_organizacao()

    def _falha(self, *args, **kwargs):
        raise RuntimeError("falha simulada ao gravar o evento")

    with monkeypatch.context() as patch:
        patch.setattr(EventoOrganizacional, "save", _falha)
        with pytest.raises(RuntimeError):
            org.reativar_usuario(
                cenario.admin,
                cenario.pedro.pk,
                papeis_mantidos={Papel.REQUISITANTE, Papel.AUDITOR},
            )

    assert foto_organizacao() == antes
    assert User.objects.get(pk=cenario.pedro.pk).is_active is False
    assert not operacao_em_curso()


def test_o_estado_final_e_valido_depois_de_ciclos_de_desativar_e_reativar(cenario):
    for _ in range(2):
        org.desativar_usuario(cenario.admin, cenario.pedro.pk)
        org.reativar_usuario(
            cenario.admin,
            cenario.pedro.pk,
            papeis_mantidos=set(org.previa_reativacao(cenario.pedro.pk).papeis_preservados),
        )

    assert _papeis(cenario.pedro) == {Papel.REQUISITANTE, Papel.AUDITOR, Papel.AUXILIAR_SETOR}
    assert _eventos(TipoEvento.USUARIO_DESATIVADO).count() == 2
    assert _eventos(TipoEvento.USUARIO_REATIVADO).count() == 2
    validar_tudo()
    assert not operacao_em_curso(), "o marcador de operação não vaza para fora das chamadas"
