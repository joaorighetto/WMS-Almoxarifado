"""Testes de proteção da Home e da página de login (User Story 1).

Cobre FR-005a, FR-007, FR-008, FR-009 e o contrato de campos do formulário
nativo de login.

TDD: escritos antes de `contas/views.py`/`contas/urls.py` (T018-T019) e dos
templates `contas/home.html`/`contas/login.html` (T020-T021) existirem — é
esperado que TODOS falhem agora (por `NoReverseMatch` ao resolver `login`/
`home`, ou por `TemplateDoesNotExist` uma vez que a rota exista mas o
template ainda não), não por erro de escrita do teste.
"""

import unicodedata
from urllib.parse import parse_qs, urlsplit

import pytest
from django.templatetags.static import static
from django.urls import reverse


def _sem_acentos(texto):
    """Normaliza texto removendo acentuação, para comparação robusta de
    rótulos independente de capitalização/acentuação exata renderizada."""
    forma_decomposta = unicodedata.normalize("NFKD", texto)
    return "".join(
        caractere for caractere in forma_decomposta if not unicodedata.combining(caractere)
    )


@pytest.mark.django_db
def test_visitante_anonimo_e_redirecionado_ao_login_sem_receber_conteudo_protegido(client):
    response = client.get("/")

    assert response.status_code == 302
    # Redirect nativo de LoginRequiredMixin: corpo vazio — nenhum conteúdo da
    # Home é entregue ao visitante não autenticado (FR-008).
    assert response.content == b""

    destino = urlsplit(response.url)
    assert destino.path == reverse("login")

    query = parse_qs(destino.query)
    assert query.get("next") == ["/"]


@pytest.mark.django_db
def test_home_renderiza_200_para_usuario_autenticado_com_template_correto(
    client, usuario_ativo, senha_valida
):
    logou = client.login(username=usuario_ativo.matricula, password=senha_valida)
    assert logou, "pré-condição do teste: login direto via client deveria funcionar"

    response = client.get(reverse("home"))

    assert response.status_code == 200
    nomes_templates = [template.name for template in response.templates]
    assert "contas/home.html" in nomes_templates


@pytest.mark.django_db
def test_login_renderiza_200_com_campos_de_matricula_e_senha(client):
    response = client.get(reverse("login"))

    assert response.status_code == 200
    conteudo = response.content.decode()

    # Campo HTML nativo do `AuthenticationForm`: continua "username", mesmo
    # com `USERNAME_FIELD = "matricula"` — só o rótulo exibido muda.
    assert 'name="username"' in conteudo
    assert 'name="password"' in conteudo
    assert "Entrar no sistema" in conteudo
    assert "Almoxarifado SAEP" in conteudo
    assert "gestão de materiais" in conteudo
    assert "data-login-form" in conteudo
    assert "data-login-submit" in conteudo
    assert static("contas/js/login.js") in conteudo

    conteudo_sem_acento = _sem_acentos(conteudo).lower()
    assert "atricula" in conteudo_sem_acento


@pytest.mark.django_db
def test_mensagem_de_erro_generica_aparece_no_html_de_login_invalido(client, usuario_ativo):
    response = client.post(
        reverse("login"),
        {"username": usuario_ativo.matricula, "password": "senha-completamente-errada"},
    )

    assert response.status_code == 200
    mensagem_esperada = str(response.context["form"].non_field_errors()[0])

    assert mensagem_esperada in response.content.decode()
    assert "Confira os dados e tente novamente." in mensagem_esperada
    assert "Se o problema continuar, procure o responsável pelo sistema." in (
        response.content.decode()
    )


@pytest.mark.django_db
def test_erros_de_campo_usam_os_ids_referenciados_pelo_django(client):
    response = client.post(reverse("login"), {"username": "", "password": ""})

    assert response.status_code == 200
    conteudo = response.content.decode()

    assert 'aria-describedby="id_username_error"' in conteudo
    assert 'id="id_username_error"' in conteudo
    assert 'aria-describedby="id_password_error"' in conteudo
    assert 'id="id_password_error"' in conteudo
