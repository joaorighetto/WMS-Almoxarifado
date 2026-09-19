"""Testes de logout da User Story 4 (T031, `specs/002-autenticacao-login/tasks.md`).

Cobre FR-017, FR-017a, FR-018, SC-007, SC-008.

TDD: escritos antes de `contas/urls.py` declarar a rota nomeada `logout` (T032)
— é esperado que TODOS falhem agora, por `django.urls.exceptions.NoReverseMatch`
ao resolver `reverse("logout")`, não por erro de escrita do teste.

Contrato-alvo (`contracts/protecao-e-redirecionamento.md`, `research.md` R7):
rota `logout` em `/logout/`, usando o `LogoutView` nativo do Django **sem
subclasse**. `LogoutView.http_method_names = ["post", "options"]` — só aceita
`POST` (verificado contra o Django 6.1.1 instalado). `LOGOUT_REDIRECT_URL =
"login"` já está configurado (T004) e não é responsabilidade desta task.

`LogoutView.post()` chama `django.contrib.auth.logout()` incondicionalmente,
sem exigir `request.user` autenticado antes — por isso logout sem sessão
válida é um no-op seguro, não um erro (`research.md` R7).
"""

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_logout_com_sessao_valida_encerra_a_sessao_e_redireciona_para_login(
    client, usuario_ativo, senha_valida
):
    logou = client.login(username=usuario_ativo.matricula, password=senha_valida)
    assert logou, "pré-condição do teste: login direto via client deveria funcionar"
    assert str(client.session.get("_auth_user_id")) == str(usuario_ativo.pk)

    response = client.post(reverse("logout"))

    assert response.status_code == 302
    assert response.url == reverse("login")
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_apos_logout_acessar_superficie_protegida_com_a_mesma_sessao_exige_autenticacao(
    client, usuario_ativo, senha_valida
):
    logou = client.login(username=usuario_ativo.matricula, password=senha_valida)
    assert logou, "pré-condição do teste: login direto via client deveria funcionar"

    logout_response = client.post(reverse("logout"))
    assert logout_response.status_code == 302

    # Mesma instância de `client` (mesmos cookies/sessão) tentando acessar a
    # Home depois do logout — precisa voltar a exigir autenticação (FR-018,
    # SC-007), não reaproveitar identidade nenhuma da sessão anterior.
    resposta_home = client.get(reverse("home"))

    assert resposta_home.status_code == 302
    assert resposta_home.url.startswith(reverse("login"))


@pytest.mark.django_db
def test_logout_sem_sessao_valida_tambem_redireciona_para_login_como_noop_seguro():
    """Edge case da spec: 'Logout sem sessão autenticada ativa' não pode
    falhar de forma que confunda o usuário nem revele informação sensível —
    precisa se comportar de maneira indistinguível de um logout normal aos
    olhos do cliente (mesmo status, mesmo destino, nenhuma exceção)."""
    from django.test import Client

    client_sem_sessao = Client()

    response = client_sem_sessao.post(reverse("logout"))

    assert response.status_code == 302
    assert response.url == reverse("login")


@pytest.mark.django_db
def test_logout_com_e_sem_sessao_previa_produzem_respostas_indistinguiveis(
    client, usuario_ativo, senha_valida
):
    """Comparação direta entre as duas respostas de logout (com e sem sessão
    prévia): nenhuma delas pode vazar, por status, destino ou corpo, se havia
    ou não uma sessão autenticada antes do POST."""
    from django.test import Client

    client_com_sessao = client
    logou = client_com_sessao.login(username=usuario_ativo.matricula, password=senha_valida)
    assert logou, "pré-condição do teste: login direto via client deveria funcionar"

    client_sem_sessao = Client()

    resposta_com_sessao = client_com_sessao.post(reverse("logout"))
    resposta_sem_sessao = client_sem_sessao.post(reverse("logout"))

    assert resposta_com_sessao.status_code == resposta_sem_sessao.status_code == 302
    assert resposta_com_sessao.url == resposta_sem_sessao.url == reverse("login")
    assert resposta_com_sessao.content == resposta_sem_sessao.content == b""


@pytest.mark.django_db
def test_logout_via_get_nao_e_aceito(client, usuario_ativo, senha_valida):
    """`LogoutView.http_method_names = ["post", "options"]` — proteção nativa
    contra logout disparado por link/CSRF simples (GET). Sem essa restrição,
    um `<img>` ou link malicioso de terceiros poderia encerrar a sessão do
    usuário sem ação deliberada dele; a spec não pede isso explicitamente,
    mas é comportamento nativo real do `LogoutView` e vale proteger contra
    regressão (ex.: futura subclasse que reabrisse `GET` sem necessidade)."""
    logou = client.login(username=usuario_ativo.matricula, password=senha_valida)
    assert logou, "pré-condição do teste: login direto via client deveria funcionar"

    response = client.get(reverse("logout"))

    assert response.status_code == 405
    # GET não deve encerrar a sessão — o método nem é aceito pela view.
    assert str(client.session.get("_auth_user_id")) == str(usuario_ativo.pk)
