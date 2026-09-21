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

import threading
import time

import pytest
from django.core.exceptions import ValidationError
from django.db import connection

import contas.models as models_mod
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
def test_queryset_update_nao_contorna_guarda_do_unico_chefe(setor_inativo):
    chefe = _criar_chefe(setor_inativo)
    _ativar(setor_inativo)

    with pytest.raises(ValidationError, match="User.save"):
        User.objects.filter(pk=chefe.pk).update(is_active=False)

    chefe.refresh_from_db()
    assert chefe.is_active is True


@pytest.mark.django_db
def test_excluir_o_unico_chefe_de_setor_ativo_e_recusado(setor_inativo):
    chefe = _criar_chefe(setor_inativo)
    _ativar(setor_inativo)

    with pytest.raises(ValidationError):
        chefe.delete()
    with pytest.raises(ValidationError):
        User.objects.filter(pk=chefe.pk).delete()

    assert User.objects.filter(pk=chefe.pk).exists()
    assert chefes_ativos(setor_inativo.pk).count() == 1


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
def test_queryset_delete_nao_remove_papel_do_unico_chefe(setor_inativo):
    chefe = _criar_chefe(setor_inativo)
    _ativar(setor_inativo)

    with pytest.raises(ValidationError):
        PapelUsuario.objects.filter(usuario=chefe, papel=Papel.CHEFE_SETOR).delete()

    assert PapelUsuario.objects.filter(usuario=chefe, papel=Papel.CHEFE_SETOR).exists()


@pytest.mark.django_db
def test_excluir_usuario_comum_remove_papeis_em_cascata_sem_afetar_chefia(setor_inativo):
    chefe = _criar_chefe(setor_inativo)
    _ativar(setor_inativo)
    comum = User.objects.create_user(matricula="comum-cascata", password=SENHA, setor=setor_inativo)
    usuario_id = comum.pk
    papel_id = comum.papeis.get(papel=Papel.REQUISITANTE).pk

    comum.delete()

    assert User.objects.filter(pk=usuario_id).exists() is False
    assert PapelUsuario.objects.filter(pk=papel_id).exists() is False
    assert list(chefes_ativos(setor_inativo.pk).values_list("pk", flat=True)) == [chefe.pk]


@pytest.mark.django_db
def test_editar_o_papel_do_unico_chefe_de_setor_ativo_para_outro_papel_e_recusado(setor_inativo):
    """Regressão: a validação de `FR-021` só rodava em `PapelUsuario.delete()`.
    Editar a linha existente (`papel` de `CHEFE_SETOR` para outro papel, sem
    excluir a linha) contornava as duas guardas e deixava o setor ativo sem
    chefe."""
    chefe = _criar_chefe(setor_inativo)
    _ativar(setor_inativo)

    atribuicao = PapelUsuario.objects.get(usuario=chefe, papel=Papel.CHEFE_SETOR)
    atribuicao.papel = Papel.AUXILIAR_SETOR
    with pytest.raises(ValidationError):
        atribuicao.save()

    atribuicao.refresh_from_db()
    assert atribuicao.papel == Papel.CHEFE_SETOR, "recusa não deixa estado parcial (FR-023)"
    assert chefes_ativos(setor_inativo.pk).count() == 1


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
def test_trocar_o_titular_de_uma_linha_de_chefe_e_recusado_quando_o_setor_esta_ativo(
    setor_inativo,
):
    """Regressão: `PapelUsuario.save()` só olhava a transição de `papel`
    (`tornando_se_chefe`/`deixando_de_ser_chefe`) comparando `self.papel` com
    o `papel` anterior. Quando `papel` não muda (permanece `CHEFE_SETOR`) mas
    o `usuario_id` da linha é reapontado para outro usuário, nenhuma das duas
    flags disparava e a troca de titular contornava as duas guardas —
    podendo deixar o setor original sem chefe e/ou duplicar a chefia do
    setor de destino (INV-ORG-002)."""
    titular = _criar_chefe(setor_inativo, matricula="titular-01")
    _ativar(setor_inativo)

    outro_setor = Setor.objects.create(nome="Outro")
    chefe_de_outro_setor = _criar_chefe(outro_setor, matricula="chefe-outro-setor")
    _ativar(outro_setor)

    atribuicao = PapelUsuario.objects.get(usuario=titular, papel=Papel.CHEFE_SETOR)
    atribuicao.usuario = chefe_de_outro_setor

    with pytest.raises(ValidationError):
        atribuicao.save()

    atribuicao.refresh_from_db()
    assert atribuicao.usuario_id == titular.pk, "recusa não deixa estado parcial (FR-023)"
    assert chefes_ativos(setor_inativo.pk).count() == 1
    assert list(chefes_ativos(setor_inativo.pk).values_list("pk", flat=True)) == [titular.pk]
    assert list(chefes_ativos(outro_setor.pk).values_list("pk", flat=True)) == [
        chefe_de_outro_setor.pk
    ]


@pytest.mark.django_db
def test_trocar_o_titular_de_uma_linha_de_chefe_e_recusado_por_duplicar_chefia_no_destino(
    setor_inativo,
):
    """Regressão: o teste acima só exercita o lado `usuario_antigo` de
    `usuario_mudou` (setor de origem ativo perdendo seu único chefe), porque
    `_exigir_chefia_preservada` recusa antes de `_exigir_chefia_nao_duplicada`
    chegar a rodar. Aqui o setor de origem está INATIVO (não sujeito a
    INV-ORG-002 — FR-019), isolando o lado `usuario_novo`: a troca de titular
    deve ser recusada só porque o setor de destino, já ativo, já tem outro
    chefe (FR-022) — `usuario_destino` nunca teve `CHEFE_SETOR`, para não
    colidir com a constraint de unicidade (usuario, papel) e garantir que a
    recusa vem da validação de negócio, não do banco."""
    titular = _criar_chefe(setor_inativo, matricula="titular-01")

    setor_destino = Setor.objects.create(nome="Destino")
    chefe_destino = _criar_chefe(setor_destino, matricula="chefe-destino")
    _ativar(setor_destino)
    usuario_destino = User.objects.create_user(
        matricula="requisitante-destino", password=SENHA, setor=setor_destino
    )

    atribuicao = PapelUsuario.objects.get(usuario=titular, papel=Papel.CHEFE_SETOR)
    atribuicao.usuario = usuario_destino

    with pytest.raises(ValidationError):
        atribuicao.save()

    atribuicao.refresh_from_db()
    assert atribuicao.usuario_id == titular.pk, "recusa não deixa estado parcial (FR-023)"
    assert list(chefes_ativos(setor_destino.pk).values_list("pk", flat=True)) == [
        chefe_destino.pk
    ]


@pytest.mark.django_db
def test_editar_papel_de_outro_usuario_para_chefe_em_setor_com_titular_e_recusado(setor_inativo):
    """Regressão: a correção anterior estendeu `tornando_se_chefe` para
    cobrir a edição de uma linha existente de outro papel PARA
    `CHEFE_SETOR`, mas esse caminho de UPDATE ficou sem teste de regressão
    (FR-022 + FR-023)."""
    _criar_chefe(setor_inativo, matricula="titular-01")
    _ativar(setor_inativo)

    requisitante = User.objects.create_user(
        matricula="requisitante-01", password=SENHA, setor=setor_inativo
    )
    atribuicao = PapelUsuario.objects.get(usuario=requisitante, papel=Papel.REQUISITANTE)
    atribuicao.papel = Papel.CHEFE_SETOR

    with pytest.raises(ValidationError):
        atribuicao.save()

    atribuicao.refresh_from_db()
    assert atribuicao.papel == Papel.REQUISITANTE, "recusa não deixa estado parcial (FR-023)"
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
# Condição de corrida: ativação de setor vs. desativação do único chefe
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_ativacao_de_setor_e_desativacao_do_unico_chefe_nao_podem_ambas_vencer(monkeypatch):
    """Regressão: `Setor.save()` (ativação) e `User.save()` (desativação do
    chefe) faziam lock em linhas diferentes (Setor vs. User) e sem lock
    compartilhado. Duas transações concorrentes — uma ativando o setor, outra
    desativando o único chefe ativo — podiam ambas ler o estado anterior uma
    da outra (setor ainda inativo; chefe ainda ativo) e ambas comitar,
    resultando em `setor.ativo=True` com zero chefes ativos.

    Este teste força deterministicamente a janela de corrida: a thread que
    ativa o setor força a avaliação antecipada de `chefes_ativos(...)` (o
    mesmo valor que seria lido de qualquer forma) e introduz uma pausa real
    antes de retornar — sem alterar nenhuma decisão de negócio — dando à
    outra thread uma janela real para tentar desativar o único chefe
    concorrentemente.
    """
    setor = Setor.objects.create(nome="Almoxarifado")
    chefe = User.objects.create_user(matricula="chefe-01", password=SENHA, setor=setor)
    PapelUsuario.objects.create(usuario=chefe, papel=Papel.CHEFE_SETOR)

    no_ponto_critico = threading.Event()
    original_chefes_ativos = models_mod.chefes_ativos

    def chefes_ativos_com_pausa(*args, **kwargs):
        contagem = list(original_chefes_ativos(*args, **kwargs))
        no_ponto_critico.set()
        time.sleep(0.5)

        class _ResultadoConhecido:
            def count(self):
                return len(contagem)

            def exists(self):
                return len(contagem) > 0

        return _ResultadoConhecido()

    monkeypatch.setattr(models_mod, "chefes_ativos", chefes_ativos_com_pausa)

    resultados = {}

    def ativar_setor():
        try:
            s = Setor.objects.get(pk=setor.pk)
            s.ativo = True
            s.save()
        except Exception as exc:  # noqa: BLE001 — captura para asserção
            resultados["ativacao_erro"] = exc
        finally:
            # Conexão é thread-local: sem isso, fica aberta após a thread
            # terminar e impede o teardown do banco de teste.
            connection.close()

    def desativar_chefe():
        no_ponto_critico.wait(timeout=5)
        try:
            u = User.objects.get(pk=chefe.pk)
            u.is_active = False
            u.save()
        except Exception as exc:  # noqa: BLE001 — captura para asserção
            resultados["desativacao_erro"] = exc
        finally:
            connection.close()

    t_ativar = threading.Thread(target=ativar_setor)
    t_desativar = threading.Thread(target=desativar_chefe)

    t_ativar.start()
    t_desativar.start()
    t_ativar.join(timeout=10)
    t_desativar.join(timeout=10)

    assert not t_ativar.is_alive(), "thread de ativação não terminou dentro do timeout"
    assert not t_desativar.is_alive(), "thread de desativação não terminou dentro do timeout"

    setor.refresh_from_db()
    chefe.refresh_from_db()

    ativacao_falhou = "ativacao_erro" in resultados
    desativacao_falhou = "desativacao_erro" in resultados

    # O lock compartilhado deve serializar as duas operações: exatamente uma
    # vence e a outra é recusada — nunca as duas (violaria INV-ORG-002) nem
    # nenhuma (indicaria que o lock não seria de fato compartilhado, ou que
    # a corrida não foi exercitada).
    assert ativacao_falhou != desativacao_falhou, (
        "exatamente uma das duas operações concorrentes deveria ser recusada; "
        f"ativacao_erro={resultados.get('ativacao_erro')!r}, "
        f"desativacao_erro={resultados.get('desativacao_erro')!r}, "
        f"setor.ativo={setor.ativo}, chefe.is_active={chefe.is_active}"
    )

    erro = resultados.get("ativacao_erro") or resultados.get("desativacao_erro")
    assert isinstance(erro, ValidationError), (
        "a operação recusada deve falhar especificamente com ValidationError "
        f"(INV-ORG-002), não {type(erro).__name__}: {erro!r} — qualquer outra exceção "
        "(deadlock, timeout, erro de conexão) satisfaria a asserção anterior sem provar "
        "que a corrida foi de fato serializada pela regra de negócio."
    )

    if ativacao_falhou:
        # A desativação venceu: setor permanece inativo (ativação recusada
        # por não haver, ainda, chefe algum num setor que continua inativo é
        # impossível — a recusa real é por deixar o setor SEM chefe ao
        # ativar; o resultado observável é o setor inativo com o chefe já
        # desativado).
        assert setor.ativo is False
        assert chefe.is_active is False
    else:
        # A ativação venceu: setor ativo com exatamente o chefe original
        # ainda ativo (a desativação foi recusada por deixaria o setor ativo
        # sem chefe).
        assert setor.ativo is True
        assert chefe.is_active is True
        assert chefes_ativos(setor.pk).count() == 1


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
