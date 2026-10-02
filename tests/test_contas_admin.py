"""Django Admin de `contas`: consulta técnica, somente leitura (T015, research R6 da 005).

O Admin deixou de ser meio de criar contas, definir senha ou conceder `Papel`: a escrita
organizacional é só das operações de `contas.organizacao` (FR-046). A conta técnica
(superusuário, sem papel de negócio) consulta `User`, `Setor`, `PapelUsuario` e
`EventoOrganizacional`, e NÃO adiciona, altera nem exclui — nem por POST direto, nem pela
ação em lote de exclusão. Preserva `INV-ORG-001`, `INV-ORG-004`; FR-016a e FR-005 (rastro
e preservação histórica: nada é excluído por aqui).
"""

import pytest
from django.contrib import admin
from django.urls import NoReverseMatch, reverse

from contas.models import EventoOrganizacional, PapelUsuario, Setor, User

pytestmark = pytest.mark.django_db

MODELOS = ("user", "setor", "papelusuario", "eventoorganizacional")


@pytest.fixture
def admin_logado(client, superusuario_tecnico):
    client.force_login(superusuario_tecnico)
    return client


@pytest.fixture
def alvo(requisitante):
    """Uma identidade de negócio com histórico, papel e setor: o que há para consultar."""
    return requisitante


def _foto():
    return (
        list(Setor.objects.order_by("pk").values()),
        list(User.objects.order_by("pk").values()),
        list(PapelUsuario.objects.order_by("pk").values()),
        list(EventoOrganizacional.objects.order_by("pk").values()),
    )


def _pk_de(modelo, alvo):
    return {
        "user": alvo.pk,
        "setor": alvo.setor_id,
        "papelusuario": alvo.papeis.first().pk,
        "eventoorganizacional": EventoOrganizacional.objects.filter(usuario=alvo).first().pk,
    }[modelo]


@pytest.mark.parametrize("modelo", MODELOS)
def test_superusuario_tecnico_consulta_lista_e_ficha(admin_logado, alvo, modelo):
    lista = admin_logado.get(reverse(f"admin:contas_{modelo}_changelist"))
    ficha = admin_logado.get(reverse(f"admin:contas_{modelo}_change", args=[_pk_de(modelo, alvo)]))

    assert lista.status_code == 200
    assert ficha.status_code == 200


def test_lista_de_usuarios_mostra_nome_e_a_de_setores_mostra_a_designacao(admin_logado, alvo):
    usuarios = admin_logado.get(reverse("admin:contas_user_changelist")).content.decode()
    setores = admin_logado.get(reverse("admin:contas_setor_changelist")).content.decode()

    assert alvo.matricula in usuarios and alvo.nome in usuarios
    assert "Almoxarifado Central" in setores
    assert "almoxarifado" in setores.lower() and "ativado em" in setores.lower()


def test_ficha_do_usuario_nunca_exibe_o_hash_da_senha(admin_logado, alvo):
    ficha = admin_logado.get(reverse("admin:contas_user_change", args=[alvo.pk]))

    assert alvo.password not in ficha.content.decode()
    assert "pbkdf2" not in ficha.content.decode() and "md5$" not in ficha.content.decode()


@pytest.mark.parametrize("modelo", MODELOS)
def test_admin_nao_oferece_adicionar_alterar_nem_excluir(admin_logado, alvo, modelo):
    antes = _foto()
    pk = _pk_de(modelo, alvo)

    adicionar_get = admin_logado.get(reverse(f"admin:contas_{modelo}_add"))
    adicionar_post = admin_logado.post(reverse(f"admin:contas_{modelo}_add"), data={"nome": "x"})
    alterar_post = admin_logado.post(
        reverse(f"admin:contas_{modelo}_change", args=[pk]), data={"nome": "alterado"}
    )
    excluir_get = admin_logado.get(reverse(f"admin:contas_{modelo}_delete", args=[pk]))
    excluir_post = admin_logado.post(
        reverse(f"admin:contas_{modelo}_delete", args=[pk]), data={"post": "yes"}
    )

    for resposta in (adicionar_get, adicionar_post, alterar_post, excluir_get, excluir_post):
        assert resposta.status_code == 403
    assert _foto() == antes, "nenhuma escrita, nem por POST direto"


@pytest.mark.parametrize("modelo", MODELOS)
def test_acao_em_lote_de_exclusao_nao_existe_e_nao_exclui(admin_logado, alvo, modelo):
    antes = _foto()
    pk = _pk_de(modelo, alvo)

    resposta = admin_logado.post(
        reverse(f"admin:contas_{modelo}_changelist"),
        data={"action": "delete_selected", "_selected_action": [pk], "post": "yes"},
    )

    assert resposta.status_code in (200, 302)
    assert _foto() == antes


def test_troca_de_senha_pelo_admin_nao_esta_disponivel(admin_logado, alvo):
    """O Admin não é caminho de credencial: a rota de troca de senha do `UserAdmin` nativo
    não existe, e um POST direto ao endereço antigo não altera a credencial."""
    antes = alvo.password

    with pytest.raises(NoReverseMatch):
        reverse("admin:auth_user_password_change", args=[alvo.pk])
    admin_logado.post(
        f"/admin/contas/user/{alvo.pk}/password/",
        data={"password1": "outra-senha-bem-forte-456", "password2": "outra-senha-bem-forte-456"},
        follow=True,
    )

    alvo.refresh_from_db()
    assert alvo.password == antes


@pytest.mark.parametrize("modelo", [User, Setor, PapelUsuario, EventoOrganizacional])
def test_todo_model_organizacional_esta_registrado_somente_leitura(modelo):
    ma = admin.site._registry[modelo]

    assert ma.has_add_permission(None) is False
    assert ma.has_change_permission(None) is False
    assert ma.has_delete_permission(None) is False


def test_conta_tecnica_continua_sem_papeis_apos_consultar_o_admin(
    admin_logado, superusuario_tecnico
):
    admin_logado.get(reverse("admin:contas_user_change", args=[superusuario_tecnico.pk]))

    assert not PapelUsuario.objects.filter(usuario=superusuario_tecnico).exists()
