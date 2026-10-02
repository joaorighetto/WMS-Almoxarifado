"""Operações sobre usuários (feature 005) — parte de CADASTRO (T017, US1).

Cobre `contas.organizacao.cadastrar_usuario(autor, *, matricula, nome, setor_id,
papeis_adicionais, chave_confirmacao) -> (User, senha_provisoria)` conforme a linha
`cadastrar_usuario` de `contracts/operacoes-organizacionais.md`. As stories seguintes
(editar, papéis, transferência — T031) ACRESCENTAM seções a este arquivo.

O que este arquivo protege, em ordem de consequência:

- INV-ORG-001/002/005/006 e FR-016a (002): a conta nasce ativa, num único setor, só com
  `ROLE-REQUESTER` e os papéis adicionais válidos; cadastrar chefe é *designação* e no
  Almoxarifado leva os três papéis; qualquer combinação que violaria uma invariante é recusada;
- toda recusa é atômica: nenhuma linha de `User`, `PapelUsuario` ou `EventoOrganizacional`,
  e a `chave_confirmacao` NÃO é consumida (o administrador corrige e reenvia a mesma tela);
- a senha provisória é devolvida uma vez, guardada só como hash e nunca vai a evento (FR-031);
- repetir a mesma `chave_confirmacao` (F5, duplo clique) não cria outra conta: levanta
  `OperacaoJaExecutada` mesmo que, agora, a matrícula já exista;
- se o evento não puder ser gravado, a conta também não nasce (FR-041, FR-047);
- duas operações concorrentes são serializadas pelo lock (FR-047): nunca `IntegrityError`,
  nunca dois chefes, nunca duas contas da mesma matrícula.

TDD: escrito antes de `cadastrar_usuario` (T020) existir — falha por `AttributeError` até lá.
"""

import ast
import json
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.test import Client
from django.utils import timezone

from config.texto import normalizar_para_busca
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
    recusa_de,
    rodar_em_threads,
    rota,
    setor_ativo,
    validar_tudo,
)

pytestmark = pytest.mark.django_db

PAPEIS_DO_CHEFE_DO_ALMOXARIFADO = {Papel.REQUISITANTE, *PAPEIS_CHEFE_ALMOXARIFADO}


@pytest.fixture
def cenario(admin_sistema):
    """Administrador no Almoxarifado Central (inativo, sem chefe — fixture `setor`), a ETA
    ativa com chefe e o Laboratório inativo e sem chefe."""
    eta, chefe_eta = setor_ativo("ETA", "eta-chefe")
    laboratorio = org.provisionar_setor("Laboratório")
    return SimpleNamespace(
        admin=admin_sistema,
        almoxarifado=admin_sistema.setor,
        eta=eta,
        chefe_eta=chefe_eta,
        lab=laboratorio,
    )


def _cadastrar(autor, **substituicoes):
    argumentos = {
        "matricula": "NOVO-0001",
        "nome": "Maria da Silva",
        "setor_id": None,
        "papeis_adicionais": set(),
        "chave_confirmacao": uuid.uuid4(),
    }
    argumentos.update(substituicoes)
    return org.cadastrar_usuario(autor, **argumentos)


def _papeis(usuario):
    atribuidos = PapelUsuario.objects.filter(usuario=usuario).values_list("papel", flat=True)
    return {Papel(p) for p in atribuidos}


# ---------------------------------------------------------------------------
# Efeitos do cadastro (FR-006, FR-007, FR-016a da 002)
# ---------------------------------------------------------------------------


def test_cadastro_cria_conta_ativa_no_setor_so_com_requisitante(cenario):
    usuario, senha = _cadastrar(cenario.admin, setor_id=cenario.eta.pk)

    usuario = User.objects.get(pk=usuario.pk)
    assert usuario.matricula == "NOVO-0001"
    assert usuario.is_active is True
    assert usuario.is_superuser is False
    assert usuario.setor == cenario.eta
    assert _papeis(usuario) == {Papel.REQUISITANTE}
    assert isinstance(senha, str) and senha
    validar_tudo()


def test_cadastro_devolve_a_provisoria_e_guarda_so_o_hash(cenario):
    antes = timezone.now()

    usuario, senha = _cadastrar(cenario.admin, setor_id=cenario.eta.pk)

    usuario = User.objects.get(pk=usuario.pk)
    assert usuario.check_password(senha)
    assert usuario.password != senha
    assert senha not in usuario.password
    # credencial provisória: marcada agora, para valer 7 dias (FR-035)
    assert usuario.senha_provisoria_em is not None
    assert antes - timedelta(seconds=5) <= usuario.senha_provisoria_em <= timezone.now()


def test_cadastro_grava_nome_sem_espacos_nas_pontas_e_nome_busca_sem_acento(cenario):
    usuario, _ = _cadastrar(cenario.admin, setor_id=cenario.eta.pk, nome="   João da Silva  ")

    usuario = User.objects.get(pk=usuario.pk)
    assert usuario.nome == "João da Silva"
    assert usuario.nome_busca == normalizar_para_busca("João da Silva")
    assert "joao" in usuario.nome_busca


def test_cadastro_com_papeis_adicionais(cenario):
    usuario, _ = _cadastrar(
        cenario.admin,
        setor_id=cenario.eta.pk,
        papeis_adicionais={Papel.AUDITOR, Papel.ADMINISTRADOR_SISTEMA, Papel.AUXILIAR_SETOR},
    )

    assert _papeis(usuario) == {
        Papel.REQUISITANTE,
        Papel.AUDITOR,
        Papel.ADMINISTRADOR_SISTEMA,
        Papel.AUXILIAR_SETOR,
    }
    validar_tudo()


def test_cadastro_em_setor_inativo_e_permitido(cenario):
    usuario, _ = _cadastrar(cenario.admin, setor_id=cenario.lab.pk)

    assert User.objects.get(pk=usuario.pk).setor == cenario.lab
    cenario.lab.refresh_from_db()
    assert cenario.lab.ativo is False


def test_cadastro_de_funcionario_no_almoxarifado(cenario):
    usuario, _ = _cadastrar(
        cenario.admin,
        setor_id=cenario.almoxarifado.pk,
        papeis_adicionais={Papel.FUNCIONARIO_ALMOXARIFADO},
    )

    assert _papeis(usuario) == {Papel.REQUISITANTE, Papel.FUNCIONARIO_ALMOXARIFADO}
    validar_tudo()


def test_cadastro_nao_concede_papel_por_efeito_colateral(cenario):
    """FR-003/SC-008: quem é cadastrado só tem os papéis pedidos, mesmo no Almoxarifado e
    mesmo sendo administrador — `ROLE-SYSTEM-ADMIN` não vira papel operacional."""
    usuario, _ = _cadastrar(
        cenario.admin,
        setor_id=cenario.almoxarifado.pk,
        papeis_adicionais={Papel.ADMINISTRADOR_SISTEMA},
    )

    assert _papeis(usuario) == {Papel.REQUISITANTE, Papel.ADMINISTRADOR_SISTEMA}


# ---------------------------------------------------------------------------
# Chefia no cadastro: é designação (FR-012, INV-ORG-002, INV-ORG-006)
# ---------------------------------------------------------------------------


def test_cadastro_de_chefe_em_setor_inativo_sem_chefe_e_designacao(cenario):
    usuario, _ = _cadastrar(
        cenario.admin, setor_id=cenario.lab.pk, papeis_adicionais={Papel.CHEFE_SETOR}
    )

    assert _papeis(usuario) == {Papel.REQUISITANTE, Papel.CHEFE_SETOR}
    assert list(chefes_ativos(cenario.lab.pk)) == [usuario]
    cenario.lab.refresh_from_db()
    assert cenario.lab.ativo is False  # designar não ativa
    validar_tudo()


@pytest.mark.parametrize(
    "pedido",
    [
        pytest.param({Papel.CHEFE_SETOR}, id="so-chefe-de-setor"),
        pytest.param({Papel.CHEFE_SETOR, Papel.CHEFE_ALMOXARIFADO}, id="chefe-e-chefia-de-estoque"),
        pytest.param(set(PAPEIS_CHEFE_ALMOXARIFADO), id="os-tres-explicitos"),
    ],
)
def test_cadastro_de_chefe_no_almoxarifado_inclui_os_tres_papeis(cenario, pedido):
    """No Almoxarifado, `ROLE-SECTOR-HEAD` implica a designação completa: o resultado é o
    mesmo, peça-se um, dois ou os três papéis (INV-ORG-006). E o setor passa a poder ser
    ativado."""
    usuario, _ = _cadastrar(
        cenario.admin, setor_id=cenario.almoxarifado.pk, papeis_adicionais=pedido
    )

    assert _papeis(usuario) == PAPEIS_DO_CHEFE_DO_ALMOXARIFADO
    validar_tudo()
    org.provisionar_ativacao(cenario.almoxarifado)  # exige chefe com os papéis de estoque
    cenario.almoxarifado.refresh_from_db()
    assert cenario.almoxarifado.ativo is True


# ---------------------------------------------------------------------------
# Eventos (FR-040, FR-031)
# ---------------------------------------------------------------------------


def test_cadastro_grava_dois_eventos_com_autor_e_a_chave_sem_senha(cenario):
    chave = uuid.uuid4()

    usuario, senha = _cadastrar(
        cenario.admin,
        setor_id=cenario.eta.pk,
        matricula="EVT-0001",
        nome="Ana Evento",
        chave_confirmacao=chave,
    )

    eventos = EventoOrganizacional.objects.filter(usuario=usuario)
    assert sorted(e.tipo for e in eventos) == sorted(
        [TipoEvento.USUARIO_CADASTRADO, TipoEvento.SENHA_PROVISORIA_GERADA]
    )
    assert all(e.autor == cenario.admin for e in eventos)

    cadastrado = eventos.get(tipo=TipoEvento.USUARIO_CADASTRADO)
    assert cadastrado.chave_confirmacao == chave
    assert cadastrado.setor == cenario.eta
    conteudo = json.dumps(cadastrado.dados, ensure_ascii=False)
    assert "EVT-0001" in conteudo and "Ana Evento" in conteudo

    for evento in eventos:
        assert senha not in json.dumps(evento.dados, ensure_ascii=False)
        assert senha not in evento.justificativa


def test_cadastro_nao_gera_outros_eventos_alem_dos_dois(cenario):
    antes = EventoOrganizacional.objects.count()

    _cadastrar(cenario.admin, setor_id=cenario.eta.pk)

    assert EventoOrganizacional.objects.count() == antes + 2


# ---------------------------------------------------------------------------
# Recusas: nenhuma escrita, nenhum evento, chave NÃO consumida
# (tabela de recusas de contracts/operacoes-organizacionais.md)
# ---------------------------------------------------------------------------


def _ativar_almoxarifado_com_chefe(cenario):
    membro(cenario.almoxarifado, "alm-chefe", PAPEIS_CHEFE_ALMOXARIFADO)
    org.provisionar_ativacao(cenario.almoxarifado)


def _lab_com_chefe(cenario):
    membro(cenario.lab, "lab-chefe", {Papel.CHEFE_SETOR})


# (id, prepara(cenario) -> argumentos, exige caminho para resolver?)
RECUSAS = [
    pytest.param(
        lambda c: {"matricula": c.admin.matricula, "setor_id": c.lab.pk},
        False,
        id="matricula-repetida",
    ),
    pytest.param(lambda c: {"matricula": "", "setor_id": c.lab.pk}, False, id="matricula-vazia"),
    pytest.param(lambda c: {"nome": "", "setor_id": c.lab.pk}, False, id="nome-vazio"),
    pytest.param(lambda c: {"nome": "     ", "setor_id": c.lab.pk}, False, id="nome-so-espacos"),
    pytest.param(lambda c: {"setor_id": None}, False, id="setor-ausente"),
    pytest.param(lambda c: {"setor_id": 987_654_321}, False, id="setor-inexistente"),
    pytest.param(
        lambda c: {"setor_id": c.eta.pk, "papeis_adicionais": {Papel.CHEFE_SETOR}},
        True,
        id="chefe-em-setor-ativo-que-ja-tem-chefe",
    ),
    pytest.param(
        lambda c: (
            _lab_com_chefe(c),
            {"setor_id": c.lab.pk, "papeis_adicionais": {Papel.CHEFE_SETOR}},
        )[1],
        True,
        id="chefe-em-setor-inativo-que-ja-tem-chefe",
    ),
    pytest.param(
        lambda c: {"setor_id": c.eta.pk, "papeis_adicionais": {Papel.FUNCIONARIO_ALMOXARIFADO}},
        True,
        id="funcionario-do-almoxarifado-fora-dele",
    ),
    pytest.param(
        lambda c: {"setor_id": c.lab.pk, "papeis_adicionais": {Papel.FUNCIONARIO_ALMOXARIFADO}},
        True,
        id="funcionario-do-almoxarifado-em-setor-inativo-comum",
    ),
    pytest.param(
        lambda c: {"setor_id": c.eta.pk, "papeis_adicionais": {Papel.CHEFE_ALMOXARIFADO}},
        True,
        id="chefe-do-almoxarifado-fora-dele",
    ),
    pytest.param(
        lambda c: {
            "setor_id": c.almoxarifado.pk,
            "papeis_adicionais": {Papel.CHEFE_ALMOXARIFADO},
        },
        True,
        id="chefia-de-estoque-sem-a-chefia-do-setor",
    ),
    pytest.param(
        lambda c: {
            "setor_id": c.almoxarifado.pk,
            "papeis_adicionais": {Papel.CHEFE_ALMOXARIFADO, Papel.FUNCIONARIO_ALMOXARIFADO},
        },
        True,
        id="chefia-de-estoque-so-com-funcionario",
    ),
    pytest.param(
        lambda c: (
            _ativar_almoxarifado_com_chefe(c),
            {"setor_id": c.almoxarifado.pk, "papeis_adicionais": set(PAPEIS_CHEFE_ALMOXARIFADO)},
        )[1],
        True,
        id="segundo-chefe-do-almoxarifado-ativo",
    ),
    pytest.param(
        lambda c: (
            _ativar_almoxarifado_com_chefe(c),
            {"setor_id": c.almoxarifado.pk, "papeis_adicionais": {Papel.CHEFE_SETOR}},
        )[1],
        True,
        id="segundo-chefe-de-setor-no-almoxarifado-ativo",
    ),
]


@pytest.mark.parametrize("preparar, exige_caminho", RECUSAS)
def test_recusa_nao_escreve_nada_e_nao_consome_a_chave(cenario, preparar, exige_caminho):
    argumentos = {"chave_confirmacao": uuid.uuid4(), **preparar(cenario)}
    antes = foto_organizacao()

    recusa = recusa_de(lambda: _cadastrar(cenario.admin, **argumentos))

    assert recusa.motivo
    if exige_caminho:
        assert recusa.caminho, "FR-048: a recusa indica o caminho para resolver"
    assert foto_organizacao() == antes, "recusa não pode deixar linha, papel nem evento"
    assert not operacao_em_curso(), "a barreira de escrita não pode vazar depois da recusa"

    # A chave só é consumida por uma operação efetivada: corrigida a tela, o mesmo envio vale.
    usuario, _ = _cadastrar(
        cenario.admin,
        matricula="REENVIO-0001",
        setor_id=cenario.eta.pk,
        chave_confirmacao=argumentos["chave_confirmacao"],
    )
    assert User.objects.filter(pk=usuario.pk).exists()


def test_cadastro_nao_deixa_estado_parcial_quando_o_evento_falha(cenario, monkeypatch):
    """FR-041/FR-047: sem evento não há operação. Conta, papéis e senha desaparecem juntos."""
    antes = foto_organizacao()

    def _falha(self, *args, **kwargs):
        raise RuntimeError("falha simulada ao gravar o evento")

    with monkeypatch.context() as patch:
        patch.setattr(EventoOrganizacional, "save", _falha)
        with pytest.raises(RuntimeError):
            _cadastrar(
                cenario.admin,
                setor_id=cenario.eta.pk,
                matricula="PARCIAL-1",
                papeis_adicionais={Papel.AUDITOR},
            )

    assert foto_organizacao() == antes
    assert not User.objects.filter(matricula="PARCIAL-1").exists()
    assert not operacao_em_curso()


# ---------------------------------------------------------------------------
# Idempotência (research R8): a mesma chave nunca gera outra conta nem outra senha
# ---------------------------------------------------------------------------


def test_mesma_chave_levanta_operacao_ja_executada_sem_nova_conta(cenario):
    chave = uuid.uuid4()
    primeiro, _ = _cadastrar(cenario.admin, setor_id=cenario.eta.pk, chave_confirmacao=chave)
    depois_do_primeiro = foto_organizacao()

    with pytest.raises(org.OperacaoJaExecutada) as excecao:
        # Mesmos dados: agora a matrícula JÁ existe (é a conta recém-criada) e, mesmo assim, a
        # resposta correta é "já executada", não "matrícula repetida" (F5 do cadastro).
        _cadastrar(cenario.admin, setor_id=cenario.eta.pk, chave_confirmacao=chave)

    assert excecao.value.evento.tipo == TipoEvento.USUARIO_CADASTRADO
    assert excecao.value.evento.usuario == primeiro
    assert foto_organizacao() == depois_do_primeiro
    assert User.objects.filter(matricula="NOVO-0001").count() == 1


def test_chave_nova_com_a_mesma_matricula_e_recusa_por_matricula_repetida(cenario):
    """O contrário da anterior: reenviar com OUTRA chave não é F5, é outro cadastro — e a
    matrícula repetida o recusa."""
    _cadastrar(cenario.admin, setor_id=cenario.eta.pk)

    recusa = recusa_de(lambda: _cadastrar(cenario.admin, setor_id=cenario.eta.pk))

    assert recusa.motivo


# ---------------------------------------------------------------------------
# Concorrência real (FR-047): threads, uma conexão cada, liberadas juntas por uma Barrier
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_cadastros_concorrentes_com_a_mesma_chave_criam_uma_conta_so(cenario):
    chave = uuid.uuid4()

    def tentar():
        return _cadastrar(cenario.admin, setor_id=cenario.eta.pk, chave_confirmacao=chave)

    resultados = rodar_em_threads({"a": tentar, "b": tentar})

    sucessos = [r for r in resultados.values() if isinstance(r, tuple)]
    ja_executadas = [r for r in resultados.values() if isinstance(r, org.OperacaoJaExecutada)]
    assert len(sucessos) == 1 and len(ja_executadas) == 1, resultados
    assert User.objects.filter(matricula="NOVO-0001").count() == 1
    assert EventoOrganizacional.objects.filter(chave_confirmacao=chave).count() == 1


@pytest.mark.django_db(transaction=True)
def test_cadastros_concorrentes_da_mesma_matricula_um_vence_e_o_outro_e_recusado(cenario):
    def tentar():
        return _cadastrar(cenario.admin, setor_id=cenario.eta.pk, chave_confirmacao=uuid.uuid4())

    resultados = rodar_em_threads({"a": tentar, "b": tentar})

    sucessos = [r for r in resultados.values() if isinstance(r, tuple)]
    recusas = [r for r in resultados.values() if isinstance(r, org.OperacaoRecusada)]
    # nunca IntegrityError vazando: a segunda operação é avaliada sobre o resultado da primeira
    assert len(sucessos) == 1 and len(recusas) == 1, resultados
    assert User.objects.filter(matricula="NOVO-0001").count() == 1
    validar_tudo()


@pytest.mark.django_db(transaction=True)
def test_cadastros_concorrentes_de_chefe_no_mesmo_setor_nunca_geram_dois_chefes(cenario):
    def tentar(matricula):
        return lambda: _cadastrar(
            cenario.admin,
            matricula=matricula,
            setor_id=cenario.lab.pk,
            papeis_adicionais={Papel.CHEFE_SETOR},
        )

    resultados = rodar_em_threads({"a": tentar("CHEFE-A"), "b": tentar("CHEFE-B")})

    sucessos = [r for r in resultados.values() if isinstance(r, tuple)]
    recusas = [r for r in resultados.values() if isinstance(r, org.OperacaoRecusada)]
    assert len(sucessos) == 1 and len(recusas) == 1, resultados
    assert chefes_ativos(cenario.lab.pk).count() == 1
    validar_tudo()


# ===========================================================================
# US3 (T031) — editar_usuario, alterar_papeis, previa_transferencia, transferir_usuario
#
# Contratos fixados pelos testes (ajustar AQUI se a implementação divergir):
# - `editar_usuario(autor, usuario_id, *, nome=None, matricula=None) -> User`;
# - `alterar_papeis(autor, usuario_id, *, conceder: set[Papel], remover: set[Papel]) -> User`;
# - `previa_transferencia(usuario_id, setor_destino_id) -> PreviaTransferencia`, só leitura, com
#   `papeis_removidos` (conjunto de `Papel`); recusa (`OperacaoRecusada`) o que a transferência
#   recusaria;
# - `transferir_usuario(autor, usuario_id, setor_destino_id, *, papeis_removidos_previstos)
#   -> User`; previstos diferentes dos efeitos recalculados sob o lock → `PreviaDesatualizada` (com
#   `.previa`), sem escrita;
# - eventos: `dados["anterior"]` e `dados["novo"]` (dicts por campo — o mesmo formato que a
#   ficha já lê), com `nome`/`matricula` em USUARIO_EDITADO e `papeis` em PAPEIS_ALTERADOS;
#   USUARIO_TRANSFERIDO: usuario, setor = destino, setor_relacionado = origem.
# ===========================================================================


def _eventos(tipo):
    return EventoOrganizacional.objects.filter(tipo=tipo)


def _chefe_do_almoxarifado(cenario, matricula="alm-chefe"):
    """Chefe completo do Almoxarifado, com o setor já ativado."""
    chefe = membro(cenario.almoxarifado, matricula, PAPEIS_CHEFE_ALMOXARIFADO)
    org.provisionar_ativacao(cenario.almoxarifado)
    return chefe


def _chefe_do_laboratorio(cenario, matricula="lab-chefe"):
    return membro(cenario.lab, matricula, {Papel.CHEFE_SETOR})


def _com_outro_administrador_inativo(cenario):
    """Devolve o administrador do cenário depois de existir outro, mas inativo."""
    membro(cenario.lab, "adm-inativo", {Papel.ADMINISTRADOR_SISTEMA}, is_active=False)
    return cenario.admin


# ---------------------------------------------------------------------------
# editar_usuario (FR-009)
# ---------------------------------------------------------------------------


def _editar(autor, usuario, **campos):
    return org.editar_usuario(autor, usuario.pk, **campos)


def test_editar_nome_grava_sem_espacos_nas_pontas_e_atualiza_nome_busca(cenario):
    alvo = membro(cenario.eta, "ED-001")

    devolvido = _editar(cenario.admin, alvo, nome="  Álvaro Novo  ")

    alvo.refresh_from_db()
    assert devolvido.pk == alvo.pk
    assert alvo.nome == "Álvaro Novo"
    assert alvo.nome_busca == normalizar_para_busca("Álvaro Novo")
    assert alvo.matricula == "ED-001"
    validar_tudo()


def test_editar_nome_registra_um_evento_com_autor_anterior_e_novo(cenario):
    alvo = membro(cenario.eta, "ED-002")

    _editar(cenario.admin, alvo, nome="Nome Corrigido")

    evento = _eventos(TipoEvento.USUARIO_EDITADO).get()
    assert evento.autor == cenario.admin and evento.usuario == alvo
    assert evento.dados["anterior"]["nome"] == "Pessoa ED-002"
    assert evento.dados["novo"]["nome"] == "Nome Corrigido"
    assert "matricula" not in evento.dados["anterior"], "só o que mudou entra no evento"


def test_corrigir_a_matricula_vale_para_o_proximo_login_e_o_evento_guarda_a_anterior(cenario):
    alvo = membro(cenario.eta, "DIGITADA-ERRADA")

    _editar(cenario.admin, alvo, matricula="DIGITADA-CERTA")

    alvo.refresh_from_db()
    assert alvo.matricula == "DIGITADA-CERTA"
    assert not User.objects.filter(matricula="DIGITADA-ERRADA").exists()
    assert Client().login(username="DIGITADA-CERTA", password=SENHA_TESTE)
    assert not Client().login(username="DIGITADA-ERRADA", password=SENHA_TESTE)
    evento = _eventos(TipoEvento.USUARIO_EDITADO).get()
    assert evento.dados["anterior"]["matricula"] == "DIGITADA-ERRADA"
    assert evento.dados["novo"]["matricula"] == "DIGITADA-CERTA"
    assert "nome" not in evento.dados["anterior"]


def test_corrigir_a_matricula_nao_encerra_a_sessao_aberta(cenario):
    """Assumption da spec: a conta é a mesma; só o próximo login usa a matrícula nova."""
    alvo = membro(cenario.eta, "SESSAO-ANTIGA")
    em_uso = Client()
    em_uso.force_login(alvo)
    assert em_uso.get(rota("home")).status_code == 200

    _editar(cenario.admin, alvo, matricula="SESSAO-NOVA")

    assert em_uso.get(rota("home")).status_code == 200


def test_editar_nome_e_matricula_juntos_gera_um_so_evento_com_os_dois_campos(cenario):
    alvo = membro(cenario.eta, "ED-003")

    _editar(cenario.admin, alvo, nome="Outro Nome", matricula="ED-003-B")

    evento = _eventos(TipoEvento.USUARIO_EDITADO).get()
    assert evento.dados["anterior"]["nome"] == "Pessoa ED-003"
    assert evento.dados["anterior"]["matricula"] == "ED-003"
    assert evento.dados["novo"]["nome"] == "Outro Nome"
    assert evento.dados["novo"]["matricula"] == "ED-003-B"


def test_editar_nao_mexe_em_papeis_setor_situacao_nem_credencial(cenario):
    alvo = membro(cenario.eta, "ED-004", {Papel.AUDITOR})
    antes = User.objects.get(pk=alvo.pk)

    _editar(cenario.admin, alvo, nome="Só o nome", matricula="ED-004-B")

    depois = User.objects.get(pk=alvo.pk)
    assert (depois.setor_id, depois.is_active, depois.password, depois.senha_provisoria_em) == (
        antes.setor_id,
        antes.is_active,
        antes.password,
        antes.senha_provisoria_em,
    )
    assert _papeis(depois) == {Papel.REQUISITANTE, Papel.AUDITOR}


@pytest.mark.parametrize(
    "campos",
    [
        pytest.param({}, id="nada-informado"),
        pytest.param({"nome": "Pessoa ED-005"}, id="mesmo-nome"),
        pytest.param({"nome": "   Pessoa ED-005  "}, id="mesmo-nome-com-espacos"),
        pytest.param({"matricula": "ED-005"}, id="mesma-matricula"),
        pytest.param({"nome": "Pessoa ED-005", "matricula": "ED-005"}, id="os-dois-iguais"),
    ],
)
def test_editar_sem_mudanca_nao_escreve_nem_gera_evento(cenario, campos):
    alvo = membro(cenario.eta, "ED-005")
    antes = foto_organizacao()

    _editar(cenario.admin, alvo, **campos)

    assert foto_organizacao() == antes


@pytest.mark.parametrize(
    "campos",
    [
        pytest.param({"matricula": "ED-OUTRA"}, id="matricula-ja-usada"),
        pytest.param({"matricula": ""}, id="matricula-vazia"),
        pytest.param({"matricula": "   "}, id="matricula-so-espacos"),
        pytest.param({"nome": ""}, id="nome-vazio"),
        pytest.param({"nome": "     "}, id="nome-so-espacos"),
        pytest.param({"nome": "x" * 151}, id="nome-longo-demais"),
        pytest.param({"matricula": "m" * 33}, id="matricula-longa-demais"),
        pytest.param(
            {"nome": "Nome Válido", "matricula": "ED-OUTRA"}, id="nome-valido-nao-vale-sozinho"
        ),
    ],
)
def test_editar_recusado_nao_escreve_nada_nem_gera_evento(cenario, campos):
    alvo = membro(cenario.eta, "ED-006")
    membro(cenario.eta, "ED-OUTRA")
    antes = foto_organizacao()

    recusa = recusa_de(lambda: _editar(cenario.admin, alvo, **campos))

    assert recusa.motivo
    assert foto_organizacao() == antes
    assert not operacao_em_curso()


# ---------------------------------------------------------------------------
# alterar_papeis (FR-010, FR-011)
# ---------------------------------------------------------------------------


def _alterar(autor, usuario, *, conceder=(), remover=()):
    return org.alterar_papeis(autor, usuario.pk, conceder=set(conceder), remover=set(remover))


@pytest.mark.parametrize("onde", ["eta", "lab", "almoxarifado"])
@pytest.mark.parametrize("papel", [Papel.AUDITOR, Papel.ADMINISTRADOR_SISTEMA])
def test_auditor_e_administrador_sao_concedidos_e_removidos_em_usuario_de_qualquer_setor(
    cenario, onde, papel
):
    alvo = membro(getattr(cenario, onde), "PAP-001")

    devolvido = _alterar(cenario.admin, alvo, conceder={papel})

    assert devolvido.pk == alvo.pk
    assert _papeis(alvo) == {Papel.REQUISITANTE, papel}
    _alterar(cenario.admin, alvo, remover={papel})
    assert _papeis(alvo) == {Papel.REQUISITANTE}
    assert _eventos(TipoEvento.PAPEIS_ALTERADOS).count() == 2
    validar_tudo()


@pytest.mark.parametrize("onde", ["eta", "lab", "almoxarifado"])
def test_auxiliar_de_setor_e_concedido_e_removido_no_proprio_setor_do_usuario(cenario, onde):
    alvo = membro(getattr(cenario, onde), "PAP-002")

    _alterar(cenario.admin, alvo, conceder={Papel.AUXILIAR_SETOR})
    assert _papeis(alvo) == {Papel.REQUISITANTE, Papel.AUXILIAR_SETOR}
    _alterar(cenario.admin, alvo, remover={Papel.AUXILIAR_SETOR})

    assert _papeis(alvo) == {Papel.REQUISITANTE}
    validar_tudo()


def test_funcionario_do_almoxarifado_e_concedido_e_removido_no_almoxarifado(cenario):
    alvo = membro(cenario.almoxarifado, "PAP-003")

    _alterar(cenario.admin, alvo, conceder={Papel.FUNCIONARIO_ALMOXARIFADO})
    assert _papeis(alvo) == {Papel.REQUISITANTE, Papel.FUNCIONARIO_ALMOXARIFADO}
    _alterar(cenario.admin, alvo, remover={Papel.FUNCIONARIO_ALMOXARIFADO})

    assert _papeis(alvo) == {Papel.REQUISITANTE}
    validar_tudo()


def test_concessao_de_papel_a_conta_inativa_e_a_remocao_dela_seguem_as_mesmas_regras(cenario):
    """O papel é preservado na desativação (FR-016a da 002): alterá-lo não exige conta ativa."""
    alvo = membro(cenario.eta, "PAP-004", {Papel.AUDITOR}, is_active=False)

    _alterar(cenario.admin, alvo, conceder={Papel.AUXILIAR_SETOR}, remover={Papel.AUDITOR})

    assert _papeis(alvo) == {Papel.REQUISITANTE, Papel.AUXILIAR_SETOR}
    alvo.refresh_from_db()
    assert alvo.is_active is False


def test_uma_alteracao_com_varias_mudancas_gera_um_so_evento_com_papeis_anteriores_e_novos(
    cenario,
):
    alvo = membro(cenario.eta, "PAP-005", {Papel.AUXILIAR_SETOR})

    _alterar(
        cenario.admin, alvo, conceder={Papel.AUDITOR}, remover={Papel.AUXILIAR_SETOR}
    )

    evento = _eventos(TipoEvento.PAPEIS_ALTERADOS).get()
    assert evento.autor == cenario.admin
    assert evento.usuario == alvo and evento.setor == cenario.eta
    assert set(evento.dados["anterior"]["papeis"]) == {Papel.REQUISITANTE, Papel.AUXILIAR_SETOR}
    assert set(evento.dados["novo"]["papeis"]) == {Papel.REQUISITANTE, Papel.AUDITOR}


@pytest.mark.parametrize(
    "conceder, remover",
    [
        pytest.param({Papel.AUDITOR}, set(), id="conceder-papel-ja-atribuido"),
        pytest.param(set(), {Papel.AUXILIAR_SETOR}, id="remover-papel-que-nao-tem"),
        pytest.param({Papel.REQUISITANTE}, set(), id="conceder-requisitante-ja-atribuido"),
        pytest.param({Papel.AUDITOR}, {Papel.AUXILIAR_SETOR}, id="as-duas-coisas"),
        pytest.param(set(), set(), id="nada-pedido"),
    ],
)
def test_alteracao_sem_efeito_nao_escreve_nem_gera_evento(cenario, conceder, remover):
    alvo = membro(cenario.eta, "PAP-006", {Papel.AUDITOR})
    antes = foto_organizacao()

    _alterar(cenario.admin, alvo, conceder=conceder, remover=remover)

    assert foto_organizacao() == antes


def test_remover_administrador_de_si_e_permitido_havendo_outro_administrador_ativo(cenario):
    membro(cenario.lab, "adm-2", {Papel.ADMINISTRADOR_SISTEMA})

    _alterar(cenario.admin, cenario.admin, remover={Papel.ADMINISTRADOR_SISTEMA})

    assert Papel.ADMINISTRADOR_SISTEMA not in _papeis(cenario.admin)
    validar_tudo()


# (preparar(cenario) -> (usuario, conceder, remover), exige caminho para resolver?)
RECUSAS_DE_PAPEIS = [
    pytest.param(
        lambda c: (membro(c.eta, "RP-01"), set(), {Papel.REQUISITANTE}),
        False,
        id="remover-requisitante-de-conta-ativa",
    ),
    pytest.param(
        lambda c: (membro(c.eta, "RP-02"), {Papel.CHEFE_SETOR}, set()),
        True,
        id="conceder-chefia-de-setor-ativo-que-ja-tem-chefe",
    ),
    pytest.param(
        lambda c: (membro(c.lab, "RP-03"), {Papel.CHEFE_SETOR}, set()),
        True,
        id="conceder-chefia-em-setor-inativo-tambem-vai-pela-ficha-do-setor",
    ),
    pytest.param(
        lambda c: (c.chefe_eta, set(), {Papel.CHEFE_SETOR}),
        True,
        id="remover-chefia-de-setor-ativo",
    ),
    pytest.param(
        lambda c: (_chefe_do_laboratorio(c), set(), {Papel.CHEFE_SETOR}),
        True,
        id="remover-chefia-de-setor-inativo-tambem-vai-pela-ficha-do-setor",
    ),
    pytest.param(
        lambda c: (
            membro(c.almoxarifado, "RP-04", {Papel.FUNCIONARIO_ALMOXARIFADO}),
            {Papel.CHEFE_ALMOXARIFADO},
            set(),
        ),
        False,
        id="conceder-chefia-de-estoque",
    ),
    pytest.param(
        lambda c: (_chefe_do_almoxarifado(c), set(), {Papel.CHEFE_ALMOXARIFADO}),
        False,
        id="remover-chefia-de-estoque",
    ),
    pytest.param(
        lambda c: (membro(c.eta, "RP-05"), {Papel.FUNCIONARIO_ALMOXARIFADO}, set()),
        True,
        id="funcionario-do-almoxarifado-em-setor-ativo-comum",
    ),
    pytest.param(
        lambda c: (membro(c.lab, "RP-06"), {Papel.FUNCIONARIO_ALMOXARIFADO}, set()),
        True,
        id="funcionario-do-almoxarifado-em-setor-inativo-comum",
    ),
    pytest.param(
        lambda c: (_chefe_do_almoxarifado(c), set(), {Papel.FUNCIONARIO_ALMOXARIFADO}),
        False,
        id="remover-funcionario-do-almoxarifado-do-chefe",
    ),
    pytest.param(
        lambda c: (c.admin, set(), {Papel.ADMINISTRADOR_SISTEMA}),
        True,
        id="remover-administrador-do-ultimo-administrador-ativo",
    ),
    pytest.param(
        lambda c: (_com_outro_administrador_inativo(c), set(), {Papel.ADMINISTRADOR_SISTEMA}),
        True,
        id="outro-administrador-inativo-nao-conta",
    ),
    pytest.param(
        lambda c: (membro(c.eta, "RP-08"), {Papel.AUDITOR}, {Papel.REQUISITANTE}),
        False,
        id="uma-mudanca-valida-nao-salva-a-invalida-do-mesmo-pedido",
    ),
]


@pytest.mark.parametrize("preparar, exige_caminho", RECUSAS_DE_PAPEIS)
def test_recusa_de_papeis_nao_escreve_nada_nem_gera_evento(cenario, preparar, exige_caminho):
    usuario, conceder, remover = preparar(cenario)
    antes = foto_organizacao()

    recusa = recusa_de(lambda: _alterar(cenario.admin, usuario, conceder=conceder, remover=remover))

    assert recusa.motivo
    if exige_caminho:
        assert recusa.caminho, "FR-048: a recusa indica o caminho para resolver"
    assert foto_organizacao() == antes, "recusa não pode deixar papel nem evento"
    assert not operacao_em_curso()


# ---------------------------------------------------------------------------
# A conta técnica não é administrada (FR-004)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "operacao_sobre_a_conta",
    [
        pytest.param(
            lambda c, t: org.editar_usuario(c.admin, t.pk, nome="Outro Nome"), id="editar"
        ),
        pytest.param(
            lambda c, t: org.alterar_papeis(
                c.admin, t.pk, conceder={Papel.AUDITOR}, remover=set()
            ),
            id="alterar-papeis",
        ),
        pytest.param(
            lambda c, t: org.transferir_usuario(
                c.admin, t.pk, c.eta.pk, papeis_removidos_previstos=set()
            ),
            id="transferir",
        ),
    ],
)
def test_conta_tecnica_nao_e_alterada_por_nenhuma_operacao_de_usuario(
    cenario, superusuario_tecnico, operacao_sobre_a_conta
):
    antes = foto_organizacao()

    recusa = recusa_de(lambda: operacao_sobre_a_conta(cenario, superusuario_tecnico))

    assert recusa.motivo
    assert foto_organizacao() == antes


# ---------------------------------------------------------------------------
# previa_transferencia e transferir_usuario (FR-013, FR-049)
# ---------------------------------------------------------------------------


def _transferir(autor, usuario, destino, removidos=()):
    return org.transferir_usuario(
        autor, usuario.pk, destino.pk, papeis_removidos_previstos=set(removidos)
    )


PRESOS_AO_SETOR = {
    Papel.AUXILIAR_SETOR,
    Papel.CHEFE_SETOR,
    Papel.FUNCIONARIO_ALMOXARIFADO,
    Papel.CHEFE_ALMOXARIFADO,
}


# (id, prepara(cenario) -> (usuario, destino), papéis removidos, papéis que ficam)
TRANSFERENCIAS = [
    pytest.param(
        lambda c: (
            membro(
                c.eta,
                "TR-01",
                {Papel.AUXILIAR_SETOR, Papel.AUDITOR, Papel.ADMINISTRADOR_SISTEMA},
            ),
            c.lab,
        ),
        {Papel.AUXILIAR_SETOR},
        {Papel.REQUISITANTE, Papel.AUDITOR, Papel.ADMINISTRADOR_SISTEMA},
        id="auxiliar-da-eta-para-setor-inativo",
    ),
    pytest.param(
        lambda c: (
            membro(
                c.almoxarifado,
                "TR-02",
                {Papel.FUNCIONARIO_ALMOXARIFADO, Papel.AUXILIAR_SETOR, Papel.AUDITOR},
            ),
            c.eta,
        ),
        {Papel.FUNCIONARIO_ALMOXARIFADO, Papel.AUXILIAR_SETOR},
        {Papel.REQUISITANTE, Papel.AUDITOR},
        id="funcionario-do-almoxarifado-para-fora-dele",
    ),
    pytest.param(
        lambda c: (
            membro(
                c.almoxarifado,
                "TR-03",
                {
                    *PAPEIS_CHEFE_ALMOXARIFADO,
                    Papel.AUXILIAR_SETOR,
                    Papel.AUDITOR,
                    Papel.ADMINISTRADOR_SISTEMA,
                },
            ),
            c.eta,
        ),
        PRESOS_AO_SETOR,
        {Papel.REQUISITANTE, Papel.AUDITOR, Papel.ADMINISTRADOR_SISTEMA},
        id="chefe-do-almoxarifado-inativo-perde-exatamente-os-quatro-papeis-presos",
    ),
    pytest.param(
        lambda c: (
            membro(c.lab, "TR-04", {Papel.CHEFE_SETOR, Papel.AUDITOR}),
            c.eta,
        ),
        {Papel.CHEFE_SETOR},
        {Papel.REQUISITANTE, Papel.AUDITOR},
        id="chefe-de-setor-inativo-perde-a-chefia",
    ),
    pytest.param(
        lambda c: (membro(c.eta, "TR-05", {Papel.AUXILIAR_SETOR}, is_active=False), c.lab),
        {Papel.AUXILIAR_SETOR},
        {Papel.REQUISITANTE},
        id="usuario-inativo-perde-o-papel-preservado-pela-desativacao",
    ),
    pytest.param(
        lambda c: (membro(c.eta, "TR-06"), c.lab),
        set(),
        {Papel.REQUISITANTE},
        id="sem-papeis-presos-nada-a-remover",
    ),
]


@pytest.mark.parametrize("preparar, removidos, mantidos", TRANSFERENCIAS)
def test_transferencia_remove_exatamente_os_papeis_presos_e_mantem_os_demais(
    cenario, preparar, removidos, mantidos
):
    usuario, destino = preparar(cenario)
    origem = User.objects.get(pk=usuario.pk).setor
    situacao = usuario.is_active

    previa = org.previa_transferencia(usuario.pk, destino.pk)
    devolvido = _transferir(cenario.admin, usuario, destino, previa.papeis_removidos)

    assert set(previa.papeis_removidos) == removidos
    usuario.refresh_from_db()
    assert devolvido.pk == usuario.pk
    assert usuario.setor == destino
    assert usuario.is_active is situacao
    assert _papeis(usuario) == mantidos
    evento = _eventos(TipoEvento.USUARIO_TRANSFERIDO).get()
    assert evento.autor == cenario.admin and evento.usuario == usuario
    assert evento.setor == destino and evento.setor_relacionado == origem
    registrado = json.dumps(evento.dados, ensure_ascii=False)
    assert all(papel.value in registrado for papel in removidos)
    validar_tudo()


def test_transferir_chefe_de_setor_inativo_deixa_o_setor_de_origem_sem_chefe(cenario):
    chefe = _chefe_do_laboratorio(cenario)

    _transferir(cenario.admin, chefe, cenario.eta, {Papel.CHEFE_SETOR})

    assert chefes_ativos(cenario.lab.pk).count() == 0
    cenario.lab.refresh_from_db()
    assert cenario.lab.ativo is False
    with pytest.raises(org.OperacaoRecusada):  # só impede a ativação futura
        org.provisionar_ativacao(cenario.lab)


def test_transferir_para_o_almoxarifado_nao_concede_papel_nenhum(cenario):
    alvo = membro(cenario.eta, "TR-07", {Papel.AUDITOR, Papel.AUXILIAR_SETOR})

    _transferir(cenario.admin, alvo, cenario.almoxarifado, {Papel.AUXILIAR_SETOR})

    alvo.refresh_from_db()
    assert alvo.setor == cenario.almoxarifado
    assert _papeis(alvo) == {Papel.REQUISITANTE, Papel.AUDITOR}


def test_transferir_nao_encerra_a_sessao_nem_toca_a_credencial(cenario):
    alvo = membro(cenario.eta, "TR-08")
    senha_antes = User.objects.get(pk=alvo.pk).password
    em_uso = Client()
    em_uso.force_login(alvo)

    _transferir(cenario.admin, alvo, cenario.lab)

    assert User.objects.get(pk=alvo.pk).password == senha_antes
    assert em_uso.get(rota("home")).status_code == 200


# (id, prepara(cenario) -> (usuario_id, destino_id), exige caminho?)
RECUSAS_DE_TRANSFERENCIA = [
    pytest.param(
        lambda c: (c.chefe_eta.pk, c.lab.pk), True, id="chefe-de-setor-ativo"
    ),
    pytest.param(
        lambda c: (_chefe_do_almoxarifado(c).pk, c.eta.pk), True, id="chefe-do-almoxarifado-ativo"
    ),
    pytest.param(
        lambda c: (membro(c.eta, "RT-01").pk, c.eta.pk), False, id="destino-igual-ao-setor-atual"
    ),
    pytest.param(
        lambda c: (membro(c.eta, "RT-02").pk, 987_654_321), False, id="destino-inexistente"
    ),
]


@pytest.mark.parametrize("preparar, exige_caminho", RECUSAS_DE_TRANSFERENCIA)
def test_transferencia_recusada_nao_escreve_nada_nem_gera_evento(
    cenario, preparar, exige_caminho
):
    usuario_id, destino_id = preparar(cenario)
    antes = foto_organizacao()

    recusa = recusa_de(
        lambda: org.transferir_usuario(
            cenario.admin, usuario_id, destino_id, papeis_removidos_previstos=set()
        )
    )

    assert recusa.motivo
    if exige_caminho:
        assert recusa.caminho, "FR-048: a recusa indica o caminho para resolver"
    assert foto_organizacao() == antes
    assert not operacao_em_curso()


def test_a_previa_nao_escreve_e_recusa_o_que_a_transferencia_recusaria(cenario):
    alvo = membro(cenario.eta, "PV-01", {Papel.AUXILIAR_SETOR})
    antes = foto_organizacao()

    previa = org.previa_transferencia(alvo.pk, cenario.lab.pk)

    assert set(previa.papeis_removidos) == {Papel.AUXILIAR_SETOR}
    assert foto_organizacao() == antes, "a prévia é só leitura: nem papel nem evento"
    recusa_de(lambda: org.previa_transferencia(cenario.chefe_eta.pk, cenario.lab.pk))
    recusa_de(lambda: org.previa_transferencia(alvo.pk, cenario.eta.pk))  # destino igual
    assert foto_organizacao() == antes


@pytest.mark.parametrize(
    "estado_inicial, mudanca, depois",
    [
        pytest.param(
            {Papel.FUNCIONARIO_ALMOXARIFADO},
            {"conceder": {Papel.AUXILIAR_SETOR}, "remover": set()},
            {Papel.FUNCIONARIO_ALMOXARIFADO, Papel.AUXILIAR_SETOR},
            id="papel-preso-acrescentado-depois-da-previa",
        ),
        pytest.param(
            {Papel.FUNCIONARIO_ALMOXARIFADO, Papel.AUXILIAR_SETOR},
            {"conceder": set(), "remover": {Papel.AUXILIAR_SETOR}},
            {Papel.FUNCIONARIO_ALMOXARIFADO},
            id="papel-preso-retirado-depois-da-previa",
        ),
    ],
)
def test_previa_desatualizada_nao_transfere_e_devolve_a_previa_nova(
    cenario, estado_inicial, mudanca, depois
):
    alvo = membro(cenario.almoxarifado, "PD-01", estado_inicial)
    previstos = org.previa_transferencia(alvo.pk, cenario.eta.pk).papeis_removidos
    assert set(previstos) == estado_inicial
    _alterar(cenario.admin, alvo, **mudanca)  # o estado mudou entre a prévia e a confirmação
    antes = foto_organizacao()

    with pytest.raises(org.PreviaDesatualizada) as excecao:
        org.transferir_usuario(
            cenario.admin, alvo.pk, cenario.eta.pk, papeis_removidos_previstos=set(previstos)
        )

    assert set(excecao.value.previa.papeis_removidos) == depois
    assert foto_organizacao() == antes, "prévia desatualizada: nada gravado, nenhum evento"
    assert not operacao_em_curso()
    # com os efeitos que a prévia nova mostra, a confirmação passa
    _transferir(cenario.admin, alvo, cenario.eta, excecao.value.previa.papeis_removidos)
    alvo.refresh_from_db()
    assert alvo.setor == cenario.eta
    assert _papeis(alvo) == {Papel.REQUISITANTE}


@pytest.mark.parametrize("operacao_atomica", ["alterar_papeis", "transferir_usuario"])
def test_sem_evento_nao_ha_alteracao_de_papel_nem_de_setor(cenario, monkeypatch, operacao_atomica):
    """FR-041/FR-047: se o evento não puder ser gravado, a operação inteira desaparece."""
    alvo = membro(cenario.almoxarifado, "ATM-01", {Papel.FUNCIONARIO_ALMOXARIFADO})
    antes = foto_organizacao()

    def _falha(self, *args, **kwargs):
        raise RuntimeError("falha simulada ao gravar o evento")

    with monkeypatch.context() as patch:
        patch.setattr(EventoOrganizacional, "save", _falha)
        with pytest.raises(RuntimeError):
            if operacao_atomica == "alterar_papeis":
                _alterar(cenario.admin, alvo, conceder={Papel.AUDITOR}, remover=set())
            else:
                _transferir(cenario.admin, alvo, cenario.eta, {Papel.FUNCIONARIO_ALMOXARIFADO})

    assert foto_organizacao() == antes
    assert not operacao_em_curso()


# ===========================================================================
# FR-051 (T055) — a organização não conhece nem escreve o estoque, o catálogo nem os fornecedores
#
# Duas provas complementares:
# 1. estática: `contas.organizacao` e `contas.credenciais` (e o que importam dentro do projeto)
#    não importam `catalogo`, `fornecedores` nem `estoque` — nem no topo, nem dentro de função,
#    nem por `import_module`/`get_model`. Não dá para provar isso inspecionando `sys.modules`
#    num subprocesso: `django.setup()` carrega os models de todos os apps instalados, então o
#    resultado seria sempre "importado".
# 2. comportamental: com entradas, estornos e movimentações já registrados, nenhuma operação
#    de `contas.organizacao` altera uma única linha das tabelas desses três apps.
# ===========================================================================

RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
APPS_DE_ESTOQUE = frozenset({"catalogo", "fornecedores", "estoque"})
MODULOS_DA_ORGANIZACAO = ("contas.organizacao", "contas.credenciais")
CHAMADAS_DE_IMPORTACAO_DINAMICA = frozenset({"import_module", "__import__", "get_model"})


def _importacoes_de(codigo, modulo):
    """Todos os módulos que `codigo` importa, em qualquer ponto da árvore (inclusive imports
    locais dentro de função) e por importação dinâmica com literal. Nomes absolutos."""
    pacote = modulo.rsplit(".", 1)[0]
    importados = set()
    for no in ast.walk(ast.parse(codigo)):
        if isinstance(no, ast.Import):
            importados.update(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom):
            if no.level:
                partes = pacote.split(".")
                base = ".".join(partes[: len(partes) - no.level + 1])
                origem = f"{base}.{no.module}" if no.module else base
            else:
                origem = no.module
            importados.add(origem)
            # `from contas import organizacao`: o nome importado pode ser um submódulo
            importados.update(f"{origem}.{alias.name}" for alias in no.names)
        elif isinstance(no, ast.Call):
            chamada = getattr(no.func, "attr", getattr(no.func, "id", None))
            if chamada in CHAMADAS_DE_IMPORTACAO_DINAMICA:
                importados.update(
                    arg.value
                    for arg in no.args
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                )
    return importados


def _arquivo_do_modulo(modulo):
    caminho = RAIZ_DO_PROJETO.joinpath(*modulo.split("."))
    if caminho.with_suffix(".py").is_file():
        return caminho.with_suffix(".py")
    pacote = caminho / "__init__.py"
    return pacote if pacote.is_file() else None


def _importacoes_proibidas(modulos_iniciais):
    """`{módulo analisado: importações de catalogo/fornecedores/estoque}`, seguindo os imports
    do próprio `contas`/`config` (um `contas.models` que importasse o estoque também quebraria
    o contrato)."""
    pendentes, vistos, proibidas = list(modulos_iniciais), set(), {}
    while pendentes:
        modulo = pendentes.pop()
        if modulo in vistos:
            continue
        vistos.add(modulo)
        arquivo = _arquivo_do_modulo(modulo)
        if arquivo is None:
            continue
        importados = _importacoes_de(arquivo.read_text(encoding="utf-8"), modulo)
        achados = {m for m in importados if m.split(".")[0] in APPS_DE_ESTOQUE}
        if achados:
            proibidas[modulo] = achados
        pendentes.extend(m for m in importados if m.split(".")[0] in {"contas", "config"})
    return proibidas


def test_o_analisador_de_imports_enxerga_import_local_relativo_e_dinamico():
    """Garante que a prova estática não é vacuamente verde: ela precisa achar o import
    escondido dentro de função, o `from X import submódulo` e a importação dinâmica."""
    codigo = (
        "import os\n"
        "from contas.models import User\n"
        "def f():\n"
        "    from estoque.models import Entrada\n"
        "def g():\n"
        "    import catalogo.models\n"
        "def h():\n"
        "    from fornecedores import models\n"
        "def i():\n"
        "    return importlib.import_module('catalogo.models')\n"
    )

    achados = {m.split(".")[0] for m in _importacoes_de(codigo, "contas.organizacao")}

    assert APPS_DE_ESTOQUE <= achados
    assert "estoque.Entrada" in _importacoes_de("apps.get_model('estoque.Entrada')\n", "contas.x")
    assert "contas.models" in _importacoes_de("from . import models\n", "contas.organizacao")


def test_organizacao_e_credenciais_nao_importam_catalogo_fornecedores_nem_estoque():
    """FR-051: nenhum import (de topo ou local) de `catalogo`, `fornecedores` ou `estoque` em
    `contas.organizacao`, `contas.credenciais` nem no que eles importam de `contas`/`config`.
    `config.texto` é utilitário compartilhado e permitido."""
    assert _importacoes_proibidas(MODULOS_DA_ORGANIZACAO) == {}


@pytest.fixture
def cenario_com_estoque(cenario, criar_material, criar_fornecedor):
    """O cenário da organização sobre um banco com entradas registradas: duas entradas (uma
    estornada) feitas por um funcionário do Almoxarifado — o próprio usuário que as operações
    editam, transferem e desativam —, com material, fornecedor, itens e movimentações."""
    from estoque.entradas import (
        EntradaInformada,
        ItemInformado,
        estornar_entrada,
        registrar_entrada,
    )
    from estoque.models import MotivoEntrada, TipoDocumentoEntrada

    funcionario = membro(cenario.almoxarifado, "FUNC-EST", {Papel.FUNCIONARIO_ALMOXARIFADO})
    material = criar_material("990.000.001", Decimal("10.000"))
    fornecedor = criar_fornecedor("9901", "Fornecedor FR-051")

    def registrar(numero, quantidade):
        return registrar_entrada(
            EntradaInformada(
                chave_confirmacao=uuid.uuid4(),
                motivo=MotivoEntrada.COMPRA,
                tipo_documento=TipoDocumentoEntrada.NOTA_FISCAL,
                numero_documento=numero,
                emitente_id=fornecedor.pk,
                itens=(ItemInformado(material_id=material.pk, quantidade=quantidade),),
            ),
            funcionario,
        )

    registrar("FR051-A", Decimal("5.000"))
    estornada = registrar("FR051-B", Decimal("3.000"))
    estornar_entrada(estornada.pk, "Lançada por engano", funcionario)

    cenario.func = funcionario
    cenario.eta_membro = membro(cenario.eta, "ETA-MEMBRO")
    cenario.lab_membro = membro(cenario.lab, "LAB-MEMBRO")
    # chefia completa do Almoxarifado (ainda inativo), para `ativar_setor` ter o que ativar
    membro(cenario.almoxarifado, "ALM-CHEFE-EST", PAPEIS_CHEFE_ALMOXARIFADO)
    return cenario


def _foto_dos_apps_de_estoque():
    """Todas as linhas, com todos os campos, de todos os models de catalogo, fornecedores e
    estoque. Igualdade antes/depois prova que nada foi inserido, alterado nem excluído."""
    return {
        modelo._meta.label: list(modelo._base_manager.order_by("pk").values())
        for app in sorted(APPS_DE_ESTOQUE)
        for modelo in apps.get_app_config(app).get_models()
    }


def test_a_foto_dos_apps_de_estoque_tem_linhas_e_detecta_alteracao_de_campo(cenario_com_estoque):
    """Controle positivo: sem ele, as comparações abaixo poderiam ser verdes por uma foto vazia
    ou cega a mudanças."""
    from catalogo.models import Material
    from estoque.models import Entrada, EstornoEntrada, ItemEntrada, MovimentacaoEstoque
    from fornecedores.models import Fornecedor

    foto = _foto_dos_apps_de_estoque()
    for modelo in (Material, Fornecedor, Entrada, ItemEntrada, EstornoEntrada, MovimentacaoEstoque):
        assert foto[modelo._meta.label], f"{modelo._meta.label} deveria ter linhas no cenário"

    material = Material.objects.get()
    Material.objects.filter(pk=material.pk).update(saldo=material.saldo + 1)
    assert _foto_dos_apps_de_estoque() != foto, "alteração de campo não detectada"
    Material.objects.filter(pk=material.pk).update(saldo=material.saldo)
    assert _foto_dos_apps_de_estoque() == foto


def _preparar_desativada(c):
    org.desativar_usuario(c.admin, c.func.pk)
    return lambda: org.reativar_usuario(
        c.admin, c.func.pk, papeis_mantidos={Papel.REQUISITANTE, Papel.FUNCIONARIO_ALMOXARIFADO}
    )


def _preparar_chefia_do_laboratorio(c):
    org.designar_chefia(c.admin, c.lab.pk, c.lab_membro.pk)
    return lambda: org.retirar_chefia(c.admin, c.lab.pk)


def _preparar_eta_so_com_o_chefe(c):
    org.desativar_usuario(c.admin, c.eta_membro.pk)
    return lambda: org.desativar_setor(c.admin, c.eta.pk)


# (preparar(cenario) -> operação a medir): o que `preparar` escreve em `contas` roda ANTES da foto.
OPERACOES_DA_ORGANIZACAO = [
    pytest.param(
        lambda c: lambda: _cadastrar(c.admin, setor_id=c.eta.pk, papeis_adicionais={Papel.AUDITOR}),
        id="cadastrar_usuario",
    ),
    pytest.param(
        lambda c: lambda: org.editar_usuario(c.admin, c.func.pk, nome="Outro Nome", matricula="F2"),
        id="editar_usuario",
    ),
    pytest.param(
        lambda c: lambda: org.alterar_papeis(
            c.admin, c.func.pk, conceder={Papel.AUDITOR}, remover=set()
        ),
        id="alterar_papeis",
    ),
    pytest.param(
        lambda c: lambda: org.transferir_usuario(
            c.admin,
            c.func.pk,
            c.eta.pk,
            papeis_removidos_previstos={Papel.FUNCIONARIO_ALMOXARIFADO},
        ),
        id="transferir_usuario",
    ),
    pytest.param(
        lambda c: lambda: org.designar_chefia(c.admin, c.lab.pk, c.lab_membro.pk),
        id="designar_chefia",
    ),
    pytest.param(_preparar_chefia_do_laboratorio, id="retirar_chefia"),
    pytest.param(
        lambda c: lambda: org.substituir_chefia(
            c.admin, c.eta.pk, chefe_esperado_id=c.chefe_eta.pk, novo_chefe_id=c.eta_membro.pk
        ),
        id="substituir_chefia",
    ),
    pytest.param(
        lambda c: lambda: org.desativar_usuario(c.admin, c.func.pk, justificativa="Desligamento"),
        id="desativar_usuario",
    ),
    pytest.param(_preparar_desativada, id="reativar_usuario"),
    pytest.param(
        lambda c: lambda: org.redefinir_senha(c.admin, c.func.pk, chave_confirmacao=uuid.uuid4()),
        id="redefinir_senha",
    ),
    pytest.param(lambda c: lambda: org.criar_setor(c.admin, nome="Setor Novo"), id="criar_setor"),
    pytest.param(
        lambda c: lambda: org.renomear_setor(c.admin, c.lab.pk, nome="Laboratório Central"),
        id="renomear_setor",
    ),
    pytest.param(
        lambda c: lambda: org.ativar_setor(c.admin, c.almoxarifado.pk), id="ativar_setor"
    ),
    pytest.param(_preparar_eta_so_com_o_chefe, id="desativar_setor"),
]


@pytest.mark.parametrize("preparar", OPERACOES_DA_ORGANIZACAO)
def test_nenhuma_operacao_da_organizacao_altera_linha_de_catalogo_fornecedores_ou_estoque(
    cenario_com_estoque, preparar
):
    """FR-051/SC-007: a organização é independente do estoque. Cada operação de
    `contas.organizacao` é efetivada de verdade (a foto da organização muda) e, ainda assim, as
    tabelas de `catalogo`, `fornecedores` e `estoque` ficam idênticas, linha a linha."""
    operacao = preparar(cenario_com_estoque)
    estoque_antes = _foto_dos_apps_de_estoque()
    organizacao_antes = foto_organizacao()

    operacao()

    assert foto_organizacao() != organizacao_antes, "a operação deveria ter sido efetivada"
    assert _foto_dos_apps_de_estoque() == estoque_antes


def test_matricula_repetida_na_edicao_recusa_com_motivo_e_caminho(cenario):
    """FR-048: a recusa por matrícula já usada, na correção de matrícula, diz o que fazer."""
    alvo = membro(cenario.eta, "ED-007")
    membro(cenario.eta, "ED-OUTRA-2")

    recusa = recusa_de(lambda: _editar(cenario.admin, alvo, matricula="ED-OUTRA-2"))

    assert recusa.motivo == "Matrícula já usada por outra conta."
    assert recusa.caminho
