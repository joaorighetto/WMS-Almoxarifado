"""Regressões da revisão 5266085774: integridade do provisionamento da 002."""

import threading
import time

import pytest
from django.core.exceptions import ValidationError
from django.db import connection

import contas.models as models_mod
from contas.models import Papel, PapelUsuario, Setor, User, chefes_ativos


@pytest.mark.django_db
@pytest.mark.parametrize("operacao", ["create", "bulk_create"])
def test_criacao_generica_nao_persiste_conta_sem_papel_minimo(setor, operacao):
    with pytest.raises(ValidationError, match="create_user"):
        if operacao == "create":
            User.objects.all().create(matricula="sem-papel", setor=setor)
        else:
            User.objects.bulk_create([User(matricula="sem-papel", setor=setor)])

    assert not User.objects.filter(matricula="sem-papel").exists()


@pytest.mark.django_db
@pytest.mark.parametrize("campo_obsoleto", ["is_active", "setor"])
def test_exclusao_de_usuario_revalida_chefia_atual(setor, campo_obsoleto):
    usuario = User.objects.create_user(
        matricula="chefe-obsoleto", setor=setor, is_active=False
    )
    PapelUsuario.objects.create(usuario=usuario, papel=Papel.CHEFE_SETOR)
    antigo = User.objects.get(pk=usuario.pk)
    if campo_obsoleto == "setor":
        usuario.setor = Setor.objects.create(nome="Destino")
        antigo.is_active = True
    usuario.is_active = True
    usuario.save()
    destino = usuario.setor
    destino.ativo = True
    destino.save()

    with pytest.raises(ValidationError, match="sem chefe ativo"):
        antigo.delete()

    assert User.objects.filter(pk=usuario.pk).exists()
    assert chefes_ativos(destino.pk).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("campo_obsoleto", ["papel", "usuario"])
def test_exclusao_de_atribuicao_revalida_chefia_atual(setor, campo_obsoleto):
    usuario = User.objects.create_user(matricula="titular", setor=setor)
    atribuicao = PapelUsuario.objects.create(
        usuario=usuario,
        papel=Papel.AUXILIAR_SETOR if campo_obsoleto == "papel" else Papel.CHEFE_SETOR,
    )
    antiga = PapelUsuario.objects.get(pk=atribuicao.pk)
    if campo_obsoleto == "usuario":
        setor = Setor.objects.create(nome="Destino")
        usuario = User.objects.create_user(matricula="novo-titular", setor=setor)
        atribuicao.usuario = usuario
    atribuicao.papel = Papel.CHEFE_SETOR
    atribuicao.save()
    setor.ativo = True
    setor.save()

    with pytest.raises(ValidationError, match="sem chefe ativo"):
        antiga.delete()

    assert PapelUsuario.objects.filter(pk=atribuicao.pk).exists()
    assert chefes_ativos(setor.pk).count() == 1


@pytest.mark.django_db
def test_exclusao_de_atribuicao_revalida_papel_minimo_atual(setor):
    usuario = User.objects.create_user(matricula="requisitante", setor=setor, is_active=False)
    usuario.papeis.all().delete()
    atribuicao = PapelUsuario.objects.create(usuario=usuario, papel=Papel.AUXILIAR_SETOR)
    antiga = PapelUsuario.objects.get(pk=atribuicao.pk)
    atribuicao.papel = Papel.REQUISITANTE
    atribuicao.save()
    usuario.is_active = True
    usuario.save()

    with pytest.raises(ValidationError, match="ROLE-REQUESTER"):
        antiga.delete()

    assert usuario.tem_papel(Papel.REQUISITANTE)


@pytest.mark.django_db
def test_save_com_update_fields_nao_organizacionais_ignora_estado_organizacional_em_memoria(
    setor,
):
    usuario = User.objects.create_user(matricula="senha-isolada", setor=setor)
    usuario.is_superuser = True
    usuario.set_password("nova-senha")

    usuario.save(update_fields=["password"])

    usuario.refresh_from_db()
    assert usuario.check_password("nova-senha")
    assert usuario.is_superuser is False


@pytest.mark.django_db
def test_save_com_update_fields_organizacionais_preserva_validacoes(setor):
    chefe = User.objects.create_user(matricula="chefe-update-fields", setor=setor)
    PapelUsuario.objects.create(usuario=chefe, papel=Papel.CHEFE_SETOR)
    setor.ativo = True
    setor.save()
    chefe.is_active = False

    with pytest.raises(ValidationError, match="sem chefe ativo"):
        chefe.save(update_fields=["is_active"])


@pytest.mark.django_db
def test_bloqueio_falha_apos_limite_quando_titular_muda_repetidamente(
    setor, monkeypatch
):
    titular_lido = User.objects.create_user(matricula="titular-lido", setor=setor)
    titular_atual = User.objects.create_user(matricula="titular-atual", setor=setor)
    atribuicao = PapelUsuario.objects.create(
        usuario=titular_atual,
        papel=Papel.AUXILIAR_SETOR,
    )
    first_original = models_mod.PapelUsuarioQuerySet.first
    tentativas = 0

    def first_com_titular_alterado(queryset):
        nonlocal tentativas
        if queryset.query.values_select == ("usuario_id",):
            tentativas += 1
            return titular_lido.pk
        return first_original(queryset)

    monkeypatch.setattr(models_mod.PapelUsuarioQuerySet, "first", first_com_titular_alterado)

    with pytest.raises(
        ValidationError,
        match="titular mudou durante o bloqueio; a operação deve ser repetida",
    ):
        with models_mod._bloquear_atribuicao(atribuicao.pk):
            pytest.fail("o contexto não deve ser liberado com titular divergente")

    assert tentativas == models_mod._MAX_TENTATIVAS_BLOQUEIO_ATRIBUICAO


def _concorrer_apos_validacao(monkeypatch, nome_validacao, primeira, segunda):
    """Pausa após ler a pré-condição; libera ao concorrente terminar ou bloquear no banco.

    Assim o teste exerce a janela real de escrita sem depender de um sleep
    para supor que a segunda conexão já tentou adquirir o bloqueio.
    """
    validou = threading.Event()
    liberar = threading.Event()
    segunda_conectou = threading.Event()
    segunda_terminou = threading.Event()
    resultados = {}
    original = getattr(PapelUsuario, nome_validacao)

    def validar_com_pausa(*args, **kwargs):
        resultado = original(*args, **kwargs)
        if threading.current_thread().name == "primeira":
            validou.set()
            assert liberar.wait(8), "a validação não foi liberada"
        return resultado

    substituto = (
        staticmethod(validar_com_pausa)
        if nome_validacao == "exigir_papel_removivel"
        else validar_com_pausa
    )
    monkeypatch.setattr(PapelUsuario, nome_validacao, substituto)

    def executar(nome, operacao):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET statement_timeout = '8s'")
                if nome == "segunda":
                    cursor.execute("SELECT pg_backend_pid()")
                    resultados["pid"] = cursor.fetchone()[0]
                    segunda_conectou.set()
            operacao()
        except Exception as exc:  # noqa: BLE001 — distinguir recusa de deadlock/timeout
            resultados[nome] = exc
        finally:
            connection.close()
            if nome == "segunda":
                segunda_terminou.set()

    t1 = threading.Thread(target=executar, args=("primeira", primeira), name="primeira")
    t2 = threading.Thread(target=executar, args=("segunda", segunda), name="segunda")
    t1.start()
    try:
        assert validou.wait(5), "a primeira operação não chegou à validação"
        t2.start()
        assert segunda_conectou.wait(5), "a segunda conexão não iniciou"
        limite = time.monotonic() + 5
        while not segunda_terminou.is_set():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s",
                    [resultados["pid"]],
                )
                estado = cursor.fetchone()
            if estado and estado[0] == "Lock":
                break
            assert time.monotonic() < limite, "concorrente não terminou nem esperou por lock"
            time.sleep(0.01)
    finally:
        liberar.set()
        t1.join(10)
        if t2.ident is not None:
            t2.join(10)
    assert not t1.is_alive() and not t2.is_alive()
    assert "primeira" not in resultados, resultados.get("primeira")
    assert isinstance(resultados.get("segunda"), ValidationError), resultados


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("operacao", ["editar", "excluir"])
def test_reativacao_nao_concorre_com_remocao_do_papel_minimo(monkeypatch, operacao):
    setor = Setor.objects.create(nome="Setor")
    usuario = User.objects.create_user(matricula="inativo", setor=setor, is_active=False)
    atribuicao_id = usuario.papeis.get(papel=Papel.REQUISITANTE).pk

    def remover_papel():
        atribuicao = PapelUsuario.objects.get(pk=atribuicao_id)
        if operacao == "editar":
            atribuicao.papel = Papel.AUXILIAR_SETOR
            atribuicao.save()
        else:
            atribuicao.delete()

    def reativar():
        atual = User.objects.get(pk=usuario.pk)
        atual.is_active = True
        atual.save()

    _concorrer_apos_validacao(
        monkeypatch, "exigir_papel_removivel", remover_papel, reativar
    )
    usuario.refresh_from_db()
    assert not usuario.is_active
    assert not usuario.tem_papel(Papel.REQUISITANTE)


@pytest.mark.django_db(transaction=True)
def test_concessao_de_papel_nao_concorre_com_promocao_a_superusuario(monkeypatch):
    setor = Setor.objects.create(nome="Setor")
    usuario = User.objects.create_user(matricula="sem-papeis", setor=setor, is_active=False)
    usuario.papeis.all().delete()

    def conceder():
        PapelUsuario.objects.create(usuario_id=usuario.pk, papel=Papel.AUDITOR)

    def promover():
        atual = User.objects.get(pk=usuario.pk)
        atual.is_superuser = True
        atual.save()

    _concorrer_apos_validacao(
        monkeypatch, "_exigir_usuario_de_negocio", conceder, promover
    )
    usuario.refresh_from_db()
    assert not usuario.is_superuser
    assert usuario.tem_papel(Papel.AUDITOR)
