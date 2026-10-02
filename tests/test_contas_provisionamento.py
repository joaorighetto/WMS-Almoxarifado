"""API de provisionamento técnico e comando `provisionar_organizacao` (T007).

Cobre `provisionar_setor`, `provisionar_usuario` e `provisionar_ativacao` (research R15,
`contracts/operacoes-organizacionais.md`) e o comando que cria o estado inicial do SAEP:
o único Almoxarifado, a primeira identidade de negócio com `ROLE-SYSTEM-ADMIN` e a
chefia válida do Almoxarifado (FR-050, D-23).

O que este arquivo protege, em ordem de consequência:

- o provisionamento nunca grava estado que viole `INV-ORG-004` a `INV-ORG-006`: cada
  recusa deixa o banco intacto (FR-047) — são as MESMAS regras e os MESMOS eventos das
  operações (FR-046), com `autor` nulo;
- a senha provisória aparece uma vez (impressa pelo comando) e nunca em evento nem em
  log; o banco guarda só o hash (FR-031);
- `senha=` conhecida só existe em desenvolvimento e testes: em qualquer outro ambiente é
  recusada ANTES de gravar (FR-031, D-23);
- o comando é recusado, sem gravar nada, em banco que já tem setor ou identidade de
  negócio, e é atômico (FR-050).

TDD: escrito antes de `contas/organizacao.py` (T010/T011) e do comando (T012) existirem.
"""

import json
import logging
from contextlib import contextmanager
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from catalogo.leitura_scpi import normalizar_para_busca
from contas import organizacao as org
from contas.models import (
    EventoOrganizacional,
    Papel,
    PapelUsuario,
    Setor,
    TipoEvento,
    User,
    chefes_ativos,
)
from tests.contas_helpers import (
    PAPEIS_CHEFE_ALMOXARIFADO,
    SENHA_TESTE,
    almoxarifado_ativo,
    membro,
    setor_ativo,
    validar_tudo,
)

pytestmark = pytest.mark.django_db

PAPEIS_DO_PRIMEIRO_ADMINISTRADOR = {
    Papel.REQUISITANTE,
    Papel.ADMINISTRADOR_SISTEMA,
    Papel.CHEFE_SETOR,
    Papel.CHEFE_ALMOXARIFADO,
    Papel.FUNCIONARIO_ALMOXARIFADO,
}

ARGUMENTOS_DO_COMANDO = [
    "--setor-almoxarifado",
    "Almoxarifado Central",
    "--matricula",
    "1001",
    "--nome",
    "Dono do Produto",
]


def _snapshot():
    """Contagem de tudo que o provisionamento escreve — igualdade antes/depois prova que
    uma recusa não deixou nada."""
    return (
        Setor.objects.count(),
        User.objects.count(),
        PapelUsuario.objects.count(),
        EventoOrganizacional.objects.count(),
    )


def _papeis(usuario):
    return set(usuario.papeis.values_list("papel", flat=True))


def _conteudo_dos_eventos():
    """Todo texto que os eventos guardam — a senha não pode estar em lugar nenhum."""
    return " ".join(
        json.dumps(evento.dados, default=str) + " " + evento.justificativa
        for evento in EventoOrganizacional.objects.all()
    )


@contextmanager
def _coletar_logs(nome="contas.organizacao"):
    """Coleta o que o logger emite mesmo que a configuração não propague para o root."""
    mensagens = []

    class Coletor(logging.Handler):
        def emit(self, record):
            mensagens.append(record.getMessage() + " " + str(record.exc_text or ""))

    logger = logging.getLogger(nome)
    coletor = Coletor(level=logging.DEBUG)
    nivel = logger.level
    logger.addHandler(coletor)
    logger.setLevel(logging.DEBUG)
    try:
        yield mensagens
    finally:
        logger.removeHandler(coletor)
        logger.setLevel(nivel)


@pytest.fixture
def pronta():
    """Organização já provisionada: Almoxarifado e ETA ativos, mais um setor inativo."""
    almox, chefe_almox = almoxarifado_ativo()
    eta, chefe_eta = setor_ativo("ETA", "eta-chefe")
    inativo = org.provisionar_setor("Laboratório")
    return SimpleNamespace(
        almox=almox, chefe_almox=chefe_almox, eta=eta, chefe_eta=chefe_eta, inativo=inativo
    )


# ---------------------------------------------------------------------------
# provisionar_setor
# ---------------------------------------------------------------------------


def test_provisionar_setor_comum_nasce_inativo_sem_designacao_e_registra_o_evento():
    setor = org.provisionar_setor("ETA")

    setor.refresh_from_db()
    assert setor.ativo is False and setor.ativado_em is None
    assert setor.almoxarifado is False
    (evento,) = EventoOrganizacional.objects.filter(setor=setor)
    assert evento.tipo == TipoEvento.SETOR_CRIADO
    assert evento.autor is None, "provisionamento técnico: autor nulo (research R15)"


def test_provisionar_setor_pode_designar_o_almoxarifado_no_nascimento():
    setor = org.provisionar_setor("Almoxarifado Central", almoxarifado=True)

    setor.refresh_from_db()
    assert setor.almoxarifado is True
    assert setor.ativo is False, "o Almoxarifado também nasce inativo (FR-019 da 002)"


def test_provisionar_setor_grava_o_nome_sem_espacos_nas_pontas():
    setor = org.provisionar_setor("  ETA  ")

    setor.refresh_from_db()
    assert setor.nome == "ETA"


def test_provisionar_segundo_almoxarifado_e_recusado_sem_gravar_nada():
    """`INV-ORG-004`: existe um único Almoxarifado, designado no provisionamento."""
    org.provisionar_setor("Almoxarifado Central", almoxarifado=True)
    antes = _snapshot()

    with pytest.raises(org.OperacaoRecusada):
        org.provisionar_setor("Outro Almoxarifado", almoxarifado=True)

    assert _snapshot() == antes
    assert Setor.objects.filter(almoxarifado=True).count() == 1


# ---------------------------------------------------------------------------
# provisionar_usuario
# ---------------------------------------------------------------------------


def test_provisionar_usuario_com_senha_provisoria_gerada(pronta):
    usuario, senha = org.provisionar_usuario(
        "1234", "  João da Silva  ", pronta.eta, {Papel.AUDITOR}
    )

    usuario.refresh_from_db()
    assert usuario.is_active is True
    assert usuario.setor_id == pronta.eta.pk
    assert _papeis(usuario) == {Papel.REQUISITANTE, Papel.AUDITOR}, "FR-016a + o pedido"
    assert usuario.nome == "João da Silva", "gravado sem espaços nas pontas (FR-006)"
    assert usuario.nome_busca == normalizar_para_busca("João da Silva") == "joao da silva"
    assert usuario.check_password(senha), "a senha devolvida é a credencial vigente"
    assert usuario.senha_provisoria_em is not None, "credencial provisória (FR-031)"
    assert abs(timezone.now() - usuario.senha_provisoria_em) < timedelta(minutes=1)
    validar_tudo()


def test_provisionar_usuario_registra_eventos_com_autor_nulo_e_sem_a_senha(pronta):
    usuario, senha = org.provisionar_usuario("1234", "Maria Souza", pronta.eta, set())

    eventos = EventoOrganizacional.objects.filter(usuario=usuario)
    assert {e.tipo for e in eventos} >= {
        TipoEvento.USUARIO_CADASTRADO,
        TipoEvento.SENHA_PROVISORIA_GERADA,
    }
    assert all(e.autor is None for e in eventos)
    assert senha not in _conteudo_dos_eventos(), "nenhum evento guarda a senha (FR-031)"


def test_provisionar_usuario_com_senha_conhecida_grava_definitiva_e_registra_senha_definida(
    pronta,
):
    """Só desenvolvimento e testes (D-23): a conta nasce com a credencial definitiva,
    sem a etapa de definição obrigatória, e o evento diz que a senha foi DEFINIDA — não
    gerada — e nunca a contém."""
    usuario, _ = org.provisionar_usuario(
        "1234", "Maria Souza", pronta.eta, set(), senha=SENHA_TESTE
    )

    usuario.refresh_from_db()
    assert usuario.check_password(SENHA_TESTE)
    assert usuario.senha_provisoria_em is None
    tipos = {e.tipo for e in EventoOrganizacional.objects.filter(usuario=usuario)}
    assert TipoEvento.SENHA_DEFINIDA in tipos
    assert TipoEvento.SENHA_PROVISORIA_GERADA not in tipos
    assert SENHA_TESTE not in _conteudo_dos_eventos()


def test_provisionar_usuario_inativo(pronta):
    usuario, _ = org.provisionar_usuario(
        "1234", "Maria Souza", pronta.eta, set(), senha=SENHA_TESTE, is_active=False
    )

    usuario.refresh_from_db()
    assert usuario.is_active is False
    assert _papeis(usuario) == {Papel.REQUISITANTE}


def test_provisionar_o_chefe_completo_do_almoxarifado_antes_da_ativacao():
    """O caminho do SAEP: setor designado → chefe com os três papéis → ativação."""
    setor = org.provisionar_setor("Almoxarifado Central", almoxarifado=True)
    chefe = membro(setor, "chefe-almox", PAPEIS_CHEFE_ALMOXARIFADO)

    org.provisionar_ativacao(setor)

    setor.refresh_from_db()
    assert setor.ativo is True and setor.ativado_em is not None
    assert [u.pk for u in chefes_ativos(setor.pk)] == [chefe.pk]
    assert _papeis(chefe) == {Papel.REQUISITANTE, *PAPEIS_CHEFE_ALMOXARIFADO}
    tipos = {e.tipo for e in EventoOrganizacional.objects.filter(setor=setor)}
    assert TipoEvento.SETOR_ATIVADO in tipos
    assert all(e.autor is None for e in EventoOrganizacional.objects.all())
    validar_tudo()


RECUSAS = [
    pytest.param(
        lambda p: org.provisionar_usuario(
            "9001", "Fulano", p.eta, {Papel.FUNCIONARIO_ALMOXARIFADO}, senha=SENHA_TESTE
        ),
        id="inv_org_005_staff_fora_do_almoxarifado",
    ),
    pytest.param(
        lambda p: org.provisionar_usuario(
            "9001", "Fulano", p.eta, {Papel.CHEFE_ALMOXARIFADO}, senha=SENHA_TESTE
        ),
        id="inv_org_005_head_fora_do_almoxarifado",
    ),
    pytest.param(
        lambda p: org.provisionar_usuario(
            "9001",
            "Fulano",
            p.almox,
            {Papel.CHEFE_ALMOXARIFADO, Papel.FUNCIONARIO_ALMOXARIFADO},
            senha=SENHA_TESTE,
        ),
        id="inv_org_006_head_sem_a_chefia_do_setor",
    ),
    pytest.param(
        lambda p: org.provisionar_usuario(
            "9001", "Fulano", p.eta, {Papel.CHEFE_SETOR}, senha=SENHA_TESTE
        ),
        id="inv_org_002_segundo_chefe_em_setor_ativo",
    ),
    pytest.param(
        lambda p: org.provisionar_setor("Outro Almoxarifado", almoxarifado=True),
        id="inv_org_004_segundo_almoxarifado",
    ),
    pytest.param(
        lambda p: org.provisionar_ativacao(p.inativo), id="inv_org_002_ativar_setor_sem_chefe"
    ),
]


@pytest.mark.parametrize("provisionar", RECUSAS)
def test_provisionamento_recusado_nao_grava_nada(pronta, provisionar):
    """FR-047/SC-003: toda recusa deixa o estado inalterado — nem conta, nem papel, nem
    setor, nem evento. A conta que nasceria sem `ROLE-REQUESTER` ou com papel inválido
    não pode existir nem por um instante visível depois da recusa."""
    antes = _snapshot()

    with pytest.raises(org.OperacaoRecusada):
        provisionar(pronta)

    assert _snapshot() == antes
    validar_tudo()


def test_provisionar_ativacao_do_almoxarifado_exige_a_chefia_de_estoque_no_chefe():
    """`INV-ORG-006`: com o Almoxarifado ativo, o chefe ativo tem `ROLE-WAREHOUSE-HEAD`.
    Ser chefe do setor (`ROLE-SECTOR-HEAD`) não basta."""
    setor = org.provisionar_setor("Almoxarifado Central", almoxarifado=True)
    membro(setor, "chefe-sem-estoque", {Papel.CHEFE_SETOR})
    antes = _snapshot()

    with pytest.raises(org.OperacaoRecusada):
        org.provisionar_ativacao(setor)

    assert _snapshot() == antes
    setor.refresh_from_db()
    assert setor.ativo is False and setor.ativado_em is None


# ---------------------------------------------------------------------------
# `senha=` conhecida: só config.settings.development e config.settings.test (FR-031)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "modulo_de_settings",
    ["config.settings.production", "config.settings.base", "config.settings.staging"],
)
def test_senha_conhecida_e_recusada_fora_de_desenvolvimento_e_testes(pronta, modulo_de_settings):
    """Em produção a credencial é SEMPRE gerada e entregue uma vez. Aceitar uma senha
    escolhida pelo chamador é o atalho que o ambiente real não pode ter — e a recusa vem
    ANTES de qualquer escrita."""
    antes = _snapshot()

    with override_settings(SETTINGS_MODULE=modulo_de_settings):
        with pytest.raises(ImproperlyConfigured):
            org.provisionar_usuario(
                "1234", "Maria Souza", pronta.eta, set(), senha="a-senha-escolhida-123"
            )

        # Só `senha=` é barrada: o provisionamento normal continua funcionando.
        usuario, senha = org.provisionar_usuario("5678", "Pedro Alves", pronta.eta, set())

    assert not User.objects.filter(matricula="1234").exists()
    assert _snapshot() != antes, "o provisionamento sem `senha=` gravou normalmente"
    assert usuario.check_password(senha) and usuario.senha_provisoria_em is not None


@pytest.mark.parametrize(
    "modulo_de_settings", ["config.settings.development", "config.settings.test"]
)
def test_senha_conhecida_e_aceita_em_desenvolvimento_e_testes(pronta, modulo_de_settings):
    with override_settings(SETTINGS_MODULE=modulo_de_settings):
        usuario, _ = org.provisionar_usuario(
            "1234", "Maria Souza", pronta.eta, set(), senha=SENHA_TESTE
        )

    assert usuario.check_password(SENHA_TESTE)


def test_senha_conhecida_continua_aceita_com_override_de_outra_configuracao(pronta, settings):
    """Armadilha do Django: sob `override_settings` (e sob a fixture `settings` do
    pytest-django), `settings.SETTINGS_MODULE` vira `None` — o atributo existe só no
    objeto de configuração original. As fábricas de teste (T013) criam toda conta com
    `senha=`, então qualquer teste que sobrescreva QUALQUER configuração quebraria se a
    checagem lesse `settings.SETTINGS_MODULE` sem tratar isso (por exemplo, caindo no
    `DJANGO_SETTINGS_MODULE` do ambiente)."""
    settings.SESSION_COOKIE_AGE = 1234

    usuario, _ = org.provisionar_usuario(
        "1234", "Maria Souza", pronta.eta, set(), senha=SENHA_TESTE
    )

    assert usuario.check_password(SENHA_TESTE)


def test_provisionamento_nunca_escreve_a_senha_em_log(pronta):
    with _coletar_logs() as mensagens:
        _, senha = org.provisionar_usuario("1234", "Maria Souza", pronta.eta, set())
        org.provisionar_usuario("5678", "Pedro Alves", pronta.eta, set(), senha=SENHA_TESTE)

    texto = " ".join(mensagens)
    assert senha not in texto
    assert SENHA_TESTE not in texto


# ---------------------------------------------------------------------------
# Comando `provisionar_organizacao` (FR-050, D-23)
# ---------------------------------------------------------------------------


def _executar_comando(*argumentos):
    saida = StringIO()
    call_command("provisionar_organizacao", *argumentos, stdout=saida, stderr=StringIO())
    return saida.getvalue()


def _senha_impressa(saida, usuario):
    """Encontra, na saída, a senha que de fato abre a conta — e exige que apareça uma
    única vez."""
    candidatas = {token.strip(".,;:!\"'()[]") for token in saida.split()}
    corretas = [token for token in candidatas if token and usuario.check_password(token)]
    assert len(corretas) == 1, f"a saída deveria trazer exatamente uma senha válida: {saida!r}"
    senha = corretas[0]
    assert saida.count(senha) == 1, "a senha provisória é impressa uma única vez"
    return senha


def test_comando_cria_o_almoxarifado_e_a_primeira_identidade_em_banco_vazio():
    with _coletar_logs() as mensagens:
        saida = _executar_comando(*ARGUMENTOS_DO_COMANDO)

    setor = Setor.objects.get()
    assert setor.nome == "Almoxarifado Central"
    assert setor.almoxarifado is True
    assert setor.ativo is True and setor.ativado_em is not None, "Almoxarifado ativo"
    usuario = User.objects.get(is_superuser=False)
    assert usuario.matricula == "1001" and usuario.nome == "Dono do Produto"
    assert usuario.setor_id == setor.pk and usuario.is_active is True
    assert usuario.is_staff is False, "identidade de negócio, não conta técnica"
    assert _papeis(usuario) == PAPEIS_DO_PRIMEIRO_ADMINISTRADOR
    assert [u.pk for u in chefes_ativos(setor.pk)] == [usuario.pk]
    assert usuario.senha_provisoria_em is not None, "deve definir a própria senha no 1º acesso"
    senha = _senha_impressa(saida, usuario)
    assert senha not in _conteudo_dos_eventos(), "a senha não vai a nenhum evento"
    assert senha not in " ".join(mensagens), "nem a nenhum log"
    tipos = {e.tipo for e in EventoOrganizacional.objects.all()}
    assert tipos >= {
        TipoEvento.SETOR_CRIADO,
        TipoEvento.USUARIO_CADASTRADO,
        TipoEvento.SENHA_PROVISORIA_GERADA,
        TipoEvento.SETOR_ATIVADO,
    }
    assert all(e.autor is None for e in EventoOrganizacional.objects.all())
    validar_tudo()


def test_comando_recusa_rodar_de_novo_sem_gravar_nada():
    _executar_comando(*ARGUMENTOS_DO_COMANDO)
    antes = _snapshot()

    with pytest.raises(CommandError):
        _executar_comando(*ARGUMENTOS_DO_COMANDO)

    assert _snapshot() == antes


@pytest.mark.parametrize("existente", ["setor_comum", "almoxarifado_ja_designado"])
def test_comando_recusa_banco_que_ja_tem_setor_sem_gravar_nada(existente):
    org.provisionar_setor("Qualquer", almoxarifado=existente == "almoxarifado_ja_designado")
    antes = _snapshot()

    with pytest.raises(CommandError):
        _executar_comando(*ARGUMENTOS_DO_COMANDO)

    assert _snapshot() == antes
    assert not User.objects.filter(matricula="1001").exists()


def test_comando_e_atomico_falha_no_fim_nao_deixa_setor_nem_conta(monkeypatch):
    """O comando roda numa transação (T012): se a ativação do setor falha, o setor e a
    conta recém-criados somem. Estado parcial aqui seria um Almoxarifado sem chefia ativa
    e uma conta com senha que ninguém viu."""
    from contas.management.commands import provisionar_organizacao as comando

    def falha(*args, **kwargs):
        raise RuntimeError("falha injetada na ativação")

    monkeypatch.setattr(org, "provisionar_ativacao", falha)
    monkeypatch.setattr(comando, "provisionar_ativacao", falha, raising=False)

    with pytest.raises((RuntimeError, CommandError)):
        _executar_comando(*ARGUMENTOS_DO_COMANDO)

    assert _snapshot() == (0, 0, 0, 0)
