"""Defesa das invariantes organizacionais NO BANCO (T005, research R5).

Cada teste escreve por SQL direto (`connection.cursor()`), sem passar pelas operações
de `contas.organizacao` e sem a barreira de escrita do ORM: é exatamente o caminho que o
trigger adiado precisa fechar (`INV-ORG-002`, `INV-ORG-004`, `INV-ORG-005`, `INV-ORG-006`
e o papel mínimo de FR-016a da 002). `django_db(transaction=True)` porque o trigger só
dispara no COMMIT (`CONSTRAINT TRIGGER ... DEFERRABLE INITIALLY DEFERRED`) e testes
não transacionais nunca fazem commit. A verificação por commit usa
`transaction.atomic()` externo: o `Error` aparece na saída do bloco.

Convenções:

- `_recusado(...)` executa os passos numa única transação e exige que o COMMIT falhe com
  erro de banco que NÃO seja de lock/deadlock (`OperationalError`): a recusa precisa
  vir da regra, não de um timeout que "também falharia" o teste;
- `_aceito(...)` exige que o mesmo tipo de escrita, em estado final válido, seja
  confirmada — são os controles que provam que o trigger não recusa tudo;
- a verificação de erro é por `django.db.Error` (como em `test_estoque_modelos.py`): o
  SQLSTATE exato é escolha do implementador do trigger.

TDD: escrito antes de `contas/apps.py` criar os triggers (T009) e de
`contas/organizacao.py` existir (T010/T011) — falha inteiro até lá.
"""

import threading
from contextlib import contextmanager
from functools import partial
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.db import Error, OperationalError, connection, transaction
from django.utils import timezone

from contas import organizacao as org
from contas.models import EventoOrganizacional, Papel, PapelUsuario, Setor, User, chefes_ativos
from tests.contas_helpers import (
    PAPEIS_CHEFE_ALMOXARIFADO,
    SENHA_TESTE,
    almoxarifado_ativo,
    membro,
    operacao,
    setor_ativo,
    validar_tudo,
)

pytestmark = pytest.mark.django_db(transaction=True)

T_SETOR = Setor._meta.db_table
T_USER = User._meta.db_table
T_PAPEL = PapelUsuario._meta.db_table
T_EVENTO = EventoOrganizacional._meta.db_table


# ---------------------------------------------------------------------------
# Apoio: SQL direto
# ---------------------------------------------------------------------------


def _sql(comando, *parametros):
    with connection.cursor() as cursor:
        cursor.execute(comando, parametros)


def _conceder(usuario, papel):
    _sql(f'INSERT INTO "{T_PAPEL}" (usuario_id, papel) VALUES (%s, %s)', usuario.pk, papel.value)


def _retirar(usuario, papel):
    _sql(f'DELETE FROM "{T_PAPEL}" WHERE usuario_id = %s AND papel = %s', usuario.pk, papel.value)


def _usuario_set(usuario, coluna, valor):
    _sql(f'UPDATE "{T_USER}" SET {coluna} = %s WHERE id = %s', valor, usuario.pk)


def _setor_set(setor, coluna, valor):
    _sql(f'UPDATE "{T_SETOR}" SET {coluna} = %s WHERE id = %s', valor, setor.pk)


def _ativar_setor(setor):
    _sql(f'UPDATE "{T_SETOR}" SET ativo = true, ativado_em = now() WHERE id = %s', setor.pk)


def _recusado(*passos):
    with pytest.raises(Error) as excinfo:
        with transaction.atomic():
            for passo in passos:
                passo()
    assert not isinstance(excinfo.value, OperationalError), (
        "a recusa deve vir da regra de banco, não de lock/deadlock: " + repr(excinfo.value)
    )


def _aceito(*passos):
    with transaction.atomic():
        for passo in passos:
            passo()


def _papeis(usuario):
    return set(PapelUsuario.objects.filter(usuario=usuario).values_list("papel", flat=True))


# ---------------------------------------------------------------------------
# Organização-base (válida) usada por quase todos os testes
# ---------------------------------------------------------------------------


@pytest.fixture
def base():
    """Almoxarifado e ETA ativos (cada um com chefe), um setor inativo COM chefe
    (Laboratório), um setor inativo SEM chefe, um ex-chefe inativo na ETA e a conta
    técnica. Tudo montado pela API de provisionamento, ou seja, válido no commit."""
    almox, chefe_almox = almoxarifado_ativo()
    membro_almox = membro(almox, "almox-membro", {Papel.FUNCIONARIO_ALMOXARIFADO})
    eta, chefe_eta = setor_ativo("ETA", "eta-chefe")
    membro_eta = membro(eta, "eta-membro")
    inativo = membro(eta, "eta-inativo", is_active=False)
    dormente = membro(eta, "eta-dormente", is_active=False)
    with operacao():  # ex-chefe: inativo mantém o papel; não conta como chefe ativo
        PapelUsuario.objects.create(usuario=dormente, papel=Papel.CHEFE_SETOR)
    lab = org.provisionar_setor("Laboratório")
    chefe_lab = membro(lab, "lab-chefe", {Papel.CHEFE_SETOR})
    vazio = org.provisionar_setor("Sem Chefia")
    membro_vazio = membro(vazio, "vazio-membro")
    tecnica = User.objects.create_superuser(
        matricula="tecnica", password=SENHA_TESTE, setor=almox, nome="Conta Técnica"
    )
    return SimpleNamespace(
        almox=almox,
        chefe_almox=chefe_almox,
        membro_almox=membro_almox,
        eta=eta,
        chefe_eta=chefe_eta,
        membro_eta=membro_eta,
        inativo=inativo,
        dormente=dormente,
        lab=lab,
        chefe_lab=chefe_lab,
        vazio=vazio,
        membro_vazio=membro_vazio,
        tecnica=tecnica,
    )


# ---------------------------------------------------------------------------
# INV-ORG-002 — setor ativo tem exatamente um chefe ativo do próprio setor
# ---------------------------------------------------------------------------


def test_setor_ativo_sem_chefe_ativo_e_recusado_no_commit(base):
    """FR-020/FR-021 da 002 no banco. O Laboratório tem chefe, mas é de OUTRO setor:
    ele não habilita a ativação do setor sem chefia."""
    _recusado(partial(_ativar_setor, base.vazio))

    base.vazio.refresh_from_db()
    assert base.vazio.ativo is False and base.vazio.ativado_em is None, "sem estado parcial"


def test_setor_cujo_unico_chefe_esta_inativo_nao_pode_ser_ativado(base):
    _aceito(partial(_usuario_set, base.chefe_lab, "is_active", False))  # setor inativo: permitido

    _recusado(partial(_ativar_setor, base.lab))

    base.lab.refresh_from_db()
    assert base.lab.ativo is False


def test_setor_com_exatamente_um_chefe_ativo_pode_ser_ativado(base):
    """Controle: a mesma escrita, com estado final válido, é confirmada."""
    _aceito(partial(_ativar_setor, base.lab))

    base.lab.refresh_from_db()
    assert base.lab.ativo is True and base.lab.ativado_em is not None
    assert [u.pk for u in chefes_ativos(base.lab.pk)] == [base.chefe_lab.pk]


@pytest.mark.parametrize(
    "escrever",
    [
        pytest.param(
            lambda b: _conceder(b.membro_eta, Papel.CHEFE_SETOR), id="papel_dado_a_outro_membro"
        ),
        pytest.param(
            lambda b: _usuario_set(b.chefe_lab, "setor_id", b.eta.pk),
            id="chefe_transferido_para_setor_ativo_com_chefe",
        ),
        pytest.param(
            lambda b: _usuario_set(b.dormente, "is_active", True), id="ex_chefe_reativado"
        ),
    ],
)
def test_setor_ativo_com_dois_chefes_ativos_e_recusado_no_commit(base, escrever):
    """FR-022 da 002 no banco, pelos três caminhos que o criam."""
    _recusado(partial(escrever, base))

    assert [u.pk for u in chefes_ativos(base.eta.pk)] == [base.chefe_eta.pk]


@pytest.mark.parametrize(
    "tirar_chefia",
    [
        pytest.param(lambda b: _usuario_set(b.chefe_eta, "is_active", False), id="desativado"),
        pytest.param(lambda b: _usuario_set(b.chefe_eta, "setor_id", b.vazio.pk), id="transferido"),
        pytest.param(
            lambda b: _retirar(b.chefe_eta, Papel.CHEFE_SETOR), id="papel_de_chefe_removido"
        ),
    ],
)
def test_setor_ativo_nao_fica_sem_chefe_por_nenhuma_escrita(base, tirar_chefia):
    """FR-021 da 002 no banco: desativar o chefe, transferi-lo ou tirar-lhe o papel."""
    _recusado(partial(tirar_chefia, base))

    assert [u.pk for u in chefes_ativos(base.eta.pk)] == [base.chefe_eta.pk]


@pytest.mark.parametrize("ordem", ["novo_antes", "antigo_antes"])
def test_troca_de_chefe_e_aceita_quando_o_estado_final_e_valido(base, ordem):
    """Base da substituição atômica: o estado INTERMEDIÁRIO (dois chefes, ou nenhum) é
    inválido, mas o trigger é adiado — só o estado no commit conta."""
    dar = partial(_conceder, base.membro_eta, Papel.CHEFE_SETOR)
    tirar = partial(_retirar, base.chefe_eta, Papel.CHEFE_SETOR)

    _aceito(*((dar, tirar) if ordem == "novo_antes" else (tirar, dar)))

    assert [u.pk for u in chefes_ativos(base.eta.pk)] == [base.membro_eta.pk]


# ---------------------------------------------------------------------------
# INV-ORG-005 — papéis de almoxarifado só no setor Almoxarifado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("papel", [Papel.FUNCIONARIO_ALMOXARIFADO, Papel.CHEFE_ALMOXARIFADO])
@pytest.mark.parametrize("alvo", ["membro_eta", "chefe_eta", "inativo"])
def test_papel_de_almoxarifado_fora_do_almoxarifado_e_recusado(base, alvo, papel):
    """Vale também para conta inativa: `INV-ORG-005` não qualifica a situação."""
    usuario = getattr(base, alvo)

    _recusado(partial(_conceder, usuario, papel))

    assert papel not in _papeis(usuario)


def test_transferir_para_fora_do_almoxarifado_sem_remover_os_papeis_e_recusado(base):
    """A transferência só vale se os papéis presos ao setor saírem na mesma operação."""
    _recusado(partial(_usuario_set, base.membro_almox, "setor_id", base.eta.pk))

    base.membro_almox.refresh_from_db()
    assert base.membro_almox.setor_id == base.almox.pk


def test_transferencia_que_remove_os_papeis_de_almoxarifado_e_aceita(base):
    _aceito(
        partial(_retirar, base.membro_almox, Papel.FUNCIONARIO_ALMOXARIFADO),
        partial(_usuario_set, base.membro_almox, "setor_id", base.eta.pk),
    )

    base.membro_almox.refresh_from_db()
    assert base.membro_almox.setor_id == base.eta.pk
    assert _papeis(base.membro_almox) == {Papel.REQUISITANTE}


# ---------------------------------------------------------------------------
# INV-ORG-006 — a chefia do almoxarifado acompanha a chefia do setor
# ---------------------------------------------------------------------------


def test_papel_de_chefe_do_almoxarifado_em_quem_nao_chefia_o_setor_e_recusado(base):
    """O membro tem `ROLE-WAREHOUSE-STAFF`, mas não é o chefe do Almoxarifado."""
    _recusado(partial(_conceder, base.membro_almox, Papel.CHEFE_ALMOXARIFADO))

    assert Papel.CHEFE_ALMOXARIFADO not in _papeis(base.membro_almox)


def test_dois_chefes_do_almoxarifado_ativos_sao_recusados(base):
    _recusado(
        partial(_conceder, base.membro_almox, Papel.CHEFE_SETOR),
        partial(_conceder, base.membro_almox, Papel.CHEFE_ALMOXARIFADO),
    )

    assert [u.pk for u in chefes_ativos(base.almox.pk)] == [base.chefe_almox.pk]


@pytest.mark.parametrize("papel", [Papel.CHEFE_ALMOXARIFADO, Papel.FUNCIONARIO_ALMOXARIFADO])
def test_chefe_ativo_do_almoxarifado_ativo_sem_um_dos_papeis_de_estoque_e_recusado(base, papel):
    _recusado(partial(_retirar, base.chefe_almox, papel))

    assert _papeis(base.chefe_almox) == {Papel.REQUISITANTE, *PAPEIS_CHEFE_ALMOXARIFADO}


@pytest.mark.parametrize("ordem", ["novo_antes", "antigo_antes"])
def test_troca_da_chefia_do_almoxarifado_move_a_chefia_de_estoque_junto(base, ordem):
    """INV-ORG-006: trocar a chefia do setor troca também a chefia de estoque, na mesma
    operação. Qualquer ordem dentro da transação; só o commit é verificado."""
    novo = [
        partial(_conceder, base.membro_almox, Papel.CHEFE_SETOR),
        partial(_conceder, base.membro_almox, Papel.CHEFE_ALMOXARIFADO),
    ]
    antigo = [
        partial(_retirar, base.chefe_almox, Papel.CHEFE_SETOR),
        partial(_retirar, base.chefe_almox, Papel.CHEFE_ALMOXARIFADO),
    ]

    _aceito(*((novo + antigo) if ordem == "novo_antes" else (antigo + novo)))

    assert _papeis(base.membro_almox) == {Papel.REQUISITANTE, *PAPEIS_CHEFE_ALMOXARIFADO}
    assert _papeis(base.chefe_almox) == {Papel.REQUISITANTE, Papel.FUNCIONARIO_ALMOXARIFADO}


def test_troca_que_move_so_a_chefia_do_setor_e_nao_a_de_estoque_e_recusada(base):
    """Um chefe do Almoxarifado ativo sem `ROLE-WAREHOUSE-HEAD` e um ex-chefe ainda com
    ele: exatamente o estado que a substituição incompleta deixaria."""
    _recusado(
        partial(_conceder, base.membro_almox, Papel.CHEFE_SETOR),
        partial(_retirar, base.chefe_almox, Papel.CHEFE_SETOR),
    )

    assert _papeis(base.chefe_almox) == {Papel.REQUISITANTE, *PAPEIS_CHEFE_ALMOXARIFADO}


def test_regras_de_almoxarifado_valem_so_para_usuario_ativo_e_para_setor_ativo():
    """`INV-ORG-006` restringe usuários ATIVOS e a exigência de `ROLE-WAREHOUSE-HEAD` no
    chefe só existe com o Almoxarifado ATIVO: antes da ativação, o chefe pode ter a
    chefia retirada (`retirar_chefia`), e desativar um chefe preserva os papéis."""
    setor = org.provisionar_setor("Almoxarifado", almoxarifado=True)
    chefe = membro(setor, "almox-inativo-chefe", PAPEIS_CHEFE_ALMOXARIFADO)

    _aceito(partial(_usuario_set, chefe, "is_active", False))
    assert _papeis(chefe) == {Papel.REQUISITANTE, *PAPEIS_CHEFE_ALMOXARIFADO}, "papéis preservados"

    _aceito(partial(_usuario_set, chefe, "is_active", True))
    _aceito(partial(_retirar, chefe, Papel.CHEFE_ALMOXARIFADO))  # Almoxarifado ainda inativo
    _recusado(partial(_ativar_setor, setor))  # com o setor ativo, o chefe precisa dos 3 papéis

    setor.refresh_from_db()
    assert setor.ativo is False


# ---------------------------------------------------------------------------
# FR-016a (002) — papel mínimo da identidade de negócio; conta técnica sem papel
# ---------------------------------------------------------------------------


def test_identidade_ativa_sem_role_requester_e_recusada(base):
    _recusado(partial(_retirar, base.membro_eta, Papel.REQUISITANTE))

    assert Papel.REQUISITANTE in _papeis(base.membro_eta)


def test_identidade_inativa_pode_ficar_sem_role_requester_mas_nao_ser_reativada_assim(base):
    _aceito(partial(_retirar, base.inativo, Papel.REQUISITANTE))

    _recusado(partial(_usuario_set, base.inativo, "is_active", True))

    base.inativo.refresh_from_db()
    assert base.inativo.is_active is False


def test_conta_tecnica_com_papel_de_negocio_e_recusada(base):
    _recusado(partial(_conceder, base.tecnica, Papel.ADMINISTRADOR_SISTEMA))

    assert _papeis(base.tecnica) == set()


def test_identidade_com_papel_nao_vira_conta_tecnica(base):
    _recusado(partial(_usuario_set, base.membro_eta, "is_superuser", True))

    base.membro_eta.refresh_from_db()
    assert base.membro_eta.is_superuser is False


# ---------------------------------------------------------------------------
# INV-ORG-004 e FR-030 — imutabilidade por trigger
# ---------------------------------------------------------------------------


def test_designacao_de_almoxarifado_nao_muda(base):
    """A designação é do provisionamento e não muda depois. Só o trigger a fecha: nem
    `UNIQUE` nem `CHECK` impedem um UPDATE de `true` para `false`."""
    _recusado(partial(_setor_set, base.almox, "almoxarifado", False))

    base.almox.refresh_from_db()
    assert base.almox.almoxarifado is True


def test_setor_comum_nao_vira_almoxarifado_depois_de_criado():
    """A designação nasce com o setor: um UPDATE posterior é recusado mesmo que nenhum
    outro Almoxarifado exista (a unicidade parcial, sozinha, deixaria passar)."""
    setor = org.provisionar_setor("Setor Comum")

    _recusado(partial(_setor_set, setor, "almoxarifado", True))

    setor.refresh_from_db()
    assert setor.almoxarifado is False


@pytest.mark.parametrize("novo_valor", [None, "outro_momento"])
def test_ativado_em_preenchido_nao_muda(base, novo_valor):
    """FR-030: o momento da primeira ativação é imutável (sustenta "já esteve ativo")."""
    _aceito(partial(_setor_set, base.eta, "ativo", False))  # ETA comum, com chefe: válido
    base.eta.refresh_from_db()
    original = base.eta.ativado_em
    assert original is not None
    valor = timezone.now() if novo_valor == "outro_momento" else None

    _recusado(partial(_setor_set, base.eta, "ativado_em", valor))

    base.eta.refresh_from_db()
    assert base.eta.ativado_em == original


def test_reativar_setor_mantem_o_momento_da_primeira_ativacao(base):
    _aceito(partial(_setor_set, base.eta, "ativo", False))
    base.eta.refresh_from_db()
    original = base.eta.ativado_em

    _aceito(partial(_setor_set, base.eta, "ativo", True))

    base.eta.refresh_from_db()
    assert base.eta.ativo is True and base.eta.ativado_em == original


@pytest.mark.parametrize(
    "comando",
    [
        pytest.param(f"UPDATE \"{T_EVENTO}\" SET justificativa = 'adulterada'", id="update_texto"),
        pytest.param(f'UPDATE "{T_EVENTO}" SET momento = now()', id="update_momento"),
        pytest.param(f'DELETE FROM "{T_EVENTO}"', id="delete"),
    ],
)
def test_evento_organizacional_e_imutavel_no_banco(base, comando):
    """FR-041 / INV de rastreabilidade: o histórico só recebe acréscimos."""
    antes = list(EventoOrganizacional.objects.order_by("pk").values())
    assert antes, "o provisionamento deveria ter gerado eventos"

    with pytest.raises(Error), transaction.atomic():
        _sql(comando)

    assert list(EventoOrganizacional.objects.order_by("pk").values()) == antes


# ---------------------------------------------------------------------------
# Idempotência do post_migrate
# ---------------------------------------------------------------------------


def _triggers_de_contas():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.relname, t.tgname
              FROM pg_trigger t
              JOIN pg_class c ON c.oid = t.tgrelid
             WHERE NOT t.tgisinternal AND c.relname = ANY(%s)
             ORDER BY 1, 2
            """,
            [[T_SETOR, T_USER, T_PAPEL, T_EVENTO]],
        )
        return cursor.fetchall()


def test_post_migrate_e_idempotente_no_flush():
    """O `flush` dos testes transacionais reemite `post_migrate` a cada teste: o handler
    (`CREATE OR REPLACE`, `DROP TRIGGER IF EXISTS`) não pode falhar nem duplicar triggers,
    e os triggers precisam continuar funcionando depois."""
    antes = _triggers_de_contas()
    assert {tabela for tabela, _ in antes} == {T_SETOR, T_USER, T_PAPEL, T_EVENTO}, (
        "cada tabela organizacional deve ter ao menos um trigger"
    )

    call_command("flush", verbosity=0, interactive=False)
    call_command("flush", verbosity=0, interactive=False)

    assert _triggers_de_contas() == antes
    almoxarifado_ativo()  # os fluxos válidos continuam passando
    with pytest.raises(Error), transaction.atomic():
        _sql(f'DELETE FROM "{T_EVENTO}"')


# ---------------------------------------------------------------------------
# O login não toma o lock de organização
# ---------------------------------------------------------------------------


@contextmanager
def _lock_de_organizacao_tomado_em_outra_conexao():
    pronto = threading.Event()
    liberar = threading.Event()
    erros = []

    def segurar():
        try:
            with operacao():  # transação aberta com o advisory lock de R2
                pronto.set()
                liberar.wait(timeout=15)
        except Exception as exc:  # noqa: BLE001 — devolvida ao teste
            erros.append(exc)
        finally:
            pronto.set()
            connection.close()

    thread = threading.Thread(target=segurar)
    thread.start()
    assert pronto.wait(timeout=5), "a outra conexão não tomou o lock"
    try:
        yield
    finally:
        liberar.set()
        thread.join(timeout=10)
    assert not thread.is_alive()
    assert not erros, erros


def test_login_com_last_login_nao_espera_pelo_lock_de_organizacao(base, client):
    """Research R2/R5: a atualização de `last_login` e o rehash de senha (que o trigger não
    dispara, pois só reage a mudança efetiva de coluna organizacional) não esperam uma
    operação organizacional em andamento. Com o lock tomado em outra conexão, o login
    conclui; o controle prova que o lock está de fato tomado: uma escrita organizacional
    (`is_active`) espera por ele e estoura o `lock_timeout`."""
    _sql("SET lock_timeout = '1500ms'")
    try:
        with _lock_de_organizacao_tomado_em_outra_conexao():
            assert client.login(username=base.membro_eta.matricula, password=SENHA_TESTE)
            base.membro_eta.refresh_from_db()
            assert base.membro_eta.last_login is not None

            base.membro_eta.set_password("outra-senha-forte-do-teste-456")
            base.membro_eta.save(update_fields=["password"])

            with pytest.raises(OperationalError), transaction.atomic():
                _usuario_set(base.membro_eta, "is_active", False)
    finally:
        _sql("SET lock_timeout = 0")


def test_escrita_de_user_sem_mudanca_organizacional_nao_espera_pelo_lock(base):
    """Um `save()` completo de identidade de negócio sem mudança é admitido pela barreira,
    mas o `UPDATE` inclui `setor_id`, `is_active` e `is_superuser`. O trigger só dispara
    quando uma dessas colunas muda de fato (`WHEN ... IS DISTINCT FROM`): do contrário, ele
    pediria o advisory lock no commit segurando o lock da linha, e uma operação concorrente
    que já tem o lock e atualiza a mesma linha entraria em deadlock. Com o lock tomado em
    outra conexão, o commit conclui sem esperar; o controle é uma mudança real, que espera."""
    _sql("SET lock_timeout = '1500ms'")
    try:
        with _lock_de_organizacao_tomado_em_outra_conexao():
            base.membro_eta.save()
            _usuario_set(base.membro_eta, "setor_id", base.membro_eta.setor_id)
            _sql(
                f'UPDATE "{T_USER}" SET is_active = is_active, is_superuser = is_superuser '
                "WHERE id = %s",
                base.membro_eta.pk,
            )

            with pytest.raises(OperationalError), transaction.atomic():
                _usuario_set(base.membro_eta, "setor_id", base.vazio.pk)
    finally:
        _sql("SET lock_timeout = 0")


# ---------------------------------------------------------------------------
# Concorrência por SQL direto: o lock DENTRO do trigger fecha a anomalia de escrita
# ---------------------------------------------------------------------------


def _corrida(passo_a, passo_b):
    """Duas transações, cada uma válida sobre o instantâneo que enxerga, executadas
    até o último comando ANTES de qualquer COMMIT (a barreira garante isso) e
    confirmadas ao mesmo tempo. O estado combinado é inválido: sem a serialização do
    trigger, as duas passariam (write skew)."""
    barreira = threading.Barrier(2, timeout=10)
    resultados = {}

    def executar(nome, passo):
        try:
            _sql("SET lock_timeout = '5s'")
            with transaction.atomic():
                passo()
                barreira.wait()
            resultados[nome] = None  # COMMIT concluído
        except Exception as exc:  # noqa: BLE001 — coletada para asserção
            resultados[nome] = exc
        finally:
            connection.close()

    threads = [
        threading.Thread(target=executar, args=("a", passo_a)),
        threading.Thread(target=executar, args=("b", passo_b)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert not any(thread.is_alive() for thread in threads), "thread não terminou no timeout"

    falhas = {nome: erro for nome, erro in resultados.items() if erro is not None}
    assert len(falhas) == 1, f"exatamente uma das duas deveria ser recusada: {resultados!r}"
    (erro,) = falhas.values()
    assert isinstance(erro, Error) and not isinstance(erro, OperationalError), (
        "a recusa deve vir da regra de banco, não de lock/deadlock/barreira: " + repr(erro)
    )
    validar_tudo()  # o estado final nunca é um que nenhuma ordem serial produziria


def test_ativacao_de_setor_e_desativacao_do_unico_chefe_nao_podem_ambas_vencer(base):
    """Regressão da 002 (corrida entre `Setor.save()` de ativação e a desativação do
    único chefe), agora no banco: uma é recusada, nunca as duas."""
    _corrida(
        partial(_ativar_setor, base.lab),
        partial(_usuario_set, base.chefe_lab, "is_active", False),
    )

    base.lab.refresh_from_db()
    base.chefe_lab.refresh_from_db()
    assert not (base.lab.ativo and not base.chefe_lab.is_active)


def test_reativacao_e_remocao_do_papel_minimo_nao_podem_ambas_vencer(base):
    """Regressão da 002 (`reativacao_nao_concorre_com_remocao_do_papel_minimo`)."""
    _corrida(
        partial(_usuario_set, base.inativo, "is_active", True),
        partial(_retirar, base.inativo, Papel.REQUISITANTE),
    )

    base.inativo.refresh_from_db()
    assert not (base.inativo.is_active and Papel.REQUISITANTE not in _papeis(base.inativo))


def test_concessao_de_papel_e_promocao_a_conta_tecnica_nao_podem_ambas_vencer(base):
    """Regressão da 002 (`concessao_de_papel_nao_concorre_com_promocao_a_superusuario`)."""
    sem_papeis = membro(base.eta, "eta-sem-papeis", is_active=False)
    _aceito(partial(_retirar, sem_papeis, Papel.REQUISITANTE))

    _corrida(
        partial(_conceder, sem_papeis, Papel.AUDITOR),
        partial(_usuario_set, sem_papeis, "is_superuser", True),
    )

    sem_papeis.refresh_from_db()
    assert not (sem_papeis.is_superuser and _papeis(sem_papeis))


# ---------------------------------------------------------------------------
# Substituição de chefia (T036): nenhum commit com dois chefes do almoxarifado
# ---------------------------------------------------------------------------


def _quem_tem_o_papel_ativo(papel):
    return set(
        User.objects.filter(is_active=True, papeis__papel=papel).values_list("pk", flat=True)
    )


def test_substituicao_do_almoxarifado_so_confirma_o_estado_final_e_nunca_dois_chefes(
    base, monkeypatch
):
    """`substituir_chefia` passa por estados intermediários (os dois com a chefia, ou nenhum),
    mas tudo acontece numa transação: quem olha de OUTRA conexão antes do commit enxerga só o
    estado antigo, com um único chefe do setor e um único `ROLE-WAREHOUSE-HEAD`.

    A operação é parada, sem `sleep`, no ponto em que já escreveu tudo e validou (a chamada de
    `validar_organizacao`, passo 5 do contrato) — e só segue quando o teste a libera. É o
    equivalente determinístico a observar "durante a substituição" em outra conexão.
    """
    administrador = membro(base.vazio, "admin-banco", {Papel.ADMINISTRADOR_SISTEMA})
    escrita_pronta, liberar = threading.Event(), threading.Event()
    validar_original = org.validar_organizacao

    def validar_e_segurar(*args, **kwargs):
        validar_original(*args, **kwargs)
        escrita_pronta.set()
        assert liberar.wait(timeout=15), "o teste não liberou a operação"

    monkeypatch.setattr(org, "validar_organizacao", validar_e_segurar)
    desfecho = {}

    def substituir():
        try:
            desfecho["novo_chefe"] = org.substituir_chefia(
                administrador,
                base.almox.pk,
                chefe_esperado_id=base.chefe_almox.pk,
                novo_chefe_id=base.membro_almox.pk,
            )
        except Exception as exc:  # noqa: BLE001 — devolvida ao teste
            desfecho["erro"] = exc
            escrita_pronta.set()  # não deixa o teste esperando por uma operação que já falhou
        finally:
            connection.close()

    thread = threading.Thread(target=substituir)
    thread.start()
    try:
        assert escrita_pronta.wait(timeout=10), "a substituição não chegou ao fim das escritas"

        # a substituição está escrita e validada, mas NÃO confirmada: nada dela é visível aqui
        assert [u.pk for u in chefes_ativos(base.almox.pk)] == [base.chefe_almox.pk]
        assert _quem_tem_o_papel_ativo(Papel.CHEFE_ALMOXARIFADO) == {base.chefe_almox.pk}
        assert _papeis(base.membro_almox) == {
            Papel.REQUISITANTE,
            Papel.FUNCIONARIO_ALMOXARIFADO,
        }
    finally:
        liberar.set()
        thread.join(timeout=15)

    assert not thread.is_alive()
    assert "erro" not in desfecho, desfecho
    # confirmada: o estado final, inteiro, e só ele (FR-052: a consulta seguinte já o vê)
    assert [u.pk for u in chefes_ativos(base.almox.pk)] == [base.membro_almox.pk]
    assert _quem_tem_o_papel_ativo(Papel.CHEFE_ALMOXARIFADO) == {base.membro_almox.pk}
    assert _papeis(base.membro_almox) == {Papel.REQUISITANTE, *PAPEIS_CHEFE_ALMOXARIFADO}
    assert _papeis(base.chefe_almox) == {Papel.REQUISITANTE, Papel.FUNCIONARIO_ALMOXARIFADO}
    validar_tudo()
