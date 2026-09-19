"""Testes de autenticação (login) da User Story 1.

Cobre FR-002 a FR-007, FR-012 e o teste central de não enumeração de usuário
(FR-003/SC-003 — `docs/domain/invariants-matrix.md` não define este ID, mas
`INV-AUTH-001` cobre a parte de conta inativa).

TDD: escritos antes de `contas/views.py`/`contas/urls.py` (T018-T019) e do
template de login (T020) existirem — é esperado que TODOS falhem agora, por
`django.urls.exceptions.NoReverseMatch` ao resolver as rotas nomeadas
`login`/`home`, não por erro de escrita do teste.

Usa exclusivamente o `AuthenticationForm` nativo: o campo HTML do
identificador de login continua se chamando `username` mesmo com
`USERNAME_FIELD = "matricula"` — apenas o rótulo exibido muda, via
`verbose_name` de `User.matricula` (ver `tests/test_contas_home.py` para a
verificação do rótulo).
"""

import pytest
from django.urls import reverse

from contas.models import Papel, PapelUsuario


def _erro_do_formulario(response):
    """Extrai a mensagem de erro geral (`non_field_errors`) de uma resposta
    de login recusado, como string única — usada para comparar mensagens
    entre diferentes causas de recusa (FR-003)."""
    erros = response.context["form"].non_field_errors()
    assert erros, "esperava ao menos uma mensagem de erro geral no formulário"
    return str(erros[0])


@pytest.mark.django_db
def test_credenciais_validas_autentica_e_redireciona_para_home(
    client, usuario_ativo, senha_valida
):
    response = client.post(
        reverse("login"),
        {"username": usuario_ativo.matricula, "password": senha_valida},
    )

    assert response.status_code == 302
    assert response.url == reverse("home")
    assert str(client.session.get("_auth_user_id")) == str(usuario_ativo.pk)


@pytest.mark.django_db
def test_senha_incorreta_recusa_com_mensagem_generica(client, usuario_ativo):
    response = client.post(
        reverse("login"),
        {"username": usuario_ativo.matricula, "password": "senha-completamente-errada"},
    )

    assert response.status_code == 200
    assert "_auth_user_id" not in client.session
    assert _erro_do_formulario(response)


@pytest.mark.django_db
def test_matricula_inexistente_recusa_com_a_mesma_mensagem_generica(
    client, usuario_ativo, senha_valida
):
    resposta_senha_errada = client.post(
        reverse("login"),
        {"username": usuario_ativo.matricula, "password": "senha-completamente-errada"},
    )
    resposta_inexistente = client.post(
        reverse("login"),
        {"username": "mat-inexistente-cadastro", "password": senha_valida},
    )

    assert resposta_inexistente.status_code == 200
    assert "_auth_user_id" not in client.session
    assert _erro_do_formulario(resposta_inexistente) == _erro_do_formulario(resposta_senha_errada)


@pytest.mark.django_db
def test_usuario_inativo_recusa_com_a_mesma_mensagem_generica(client, criar_usuario, senha_valida):
    inativo = criar_usuario(matricula="mat-conta-inativa", is_active=False)

    resposta_senha_errada = client.post(
        reverse("login"),
        {"username": inativo.matricula, "password": "senha-completamente-errada"},
    )
    resposta_inativo = client.post(
        reverse("login"),
        {"username": inativo.matricula, "password": senha_valida},
    )

    assert resposta_inativo.status_code == 200
    assert "_auth_user_id" not in client.session
    assert _erro_do_formulario(resposta_inativo) == _erro_do_formulario(resposta_senha_errada)


@pytest.mark.django_db
def test_recusas_por_senha_errada_matricula_inexistente_e_conta_inativa_sao_identicas(
    client, criar_usuario, senha_valida
):
    """Teste central de FR-003/SC-003 (não enumeração de usuário): as três
    causas de recusa distintas — senha errada, matrícula inexistente e conta
    inativa — precisam produzir exatamente a mesma string de erro. Qualquer
    diferença entre elas permitiria a um visitante malicioso descobrir quais
    matrículas existem no cadastro (Constitution, Princípio VI)."""
    ativo = criar_usuario(matricula="mat-ativa-comparacao")
    inativo = criar_usuario(matricula="mat-inativa-comparacao", is_active=False)

    resposta_senha_errada = client.post(
        reverse("login"),
        {"username": ativo.matricula, "password": "senha-completamente-errada"},
    )
    resposta_matricula_inexistente = client.post(
        reverse("login"),
        {"username": "mat-jamais-cadastrada", "password": senha_valida},
    )
    resposta_inativo = client.post(
        reverse("login"),
        {"username": inativo.matricula, "password": senha_valida},
    )

    mensagem_senha_errada = _erro_do_formulario(resposta_senha_errada)
    mensagem_matricula_inexistente = _erro_do_formulario(resposta_matricula_inexistente)
    mensagem_inativo = _erro_do_formulario(resposta_inativo)

    assert mensagem_senha_errada == mensagem_matricula_inexistente == mensagem_inativo


@pytest.mark.django_db
def test_sessao_persiste_entre_requisicoes_subsequentes(client, usuario_ativo, senha_valida):
    login_response = client.post(
        reverse("login"),
        {"username": usuario_ativo.matricula, "password": senha_valida},
    )
    assert login_response.status_code == 302

    resposta_seguinte = client.get(reverse("home"))

    assert resposta_seguinte.status_code == 200
    assert str(client.session.get("_auth_user_id")) == str(usuario_ativo.pk)


@pytest.mark.django_db
def test_usuario_ja_autenticado_que_acessa_login_e_redirecionado_para_home(
    client, usuario_ativo, senha_valida
):
    logou = client.login(username=usuario_ativo.matricula, password=senha_valida)
    assert logou, "pré-condição do teste: login direto via client deveria funcionar"

    response = client.get(reverse("login"))

    assert response.status_code == 302
    assert response.url == reverse("home")


# ---------------------------------------------------------------------------
# User Story 3 (T030) — identidade/papel/setor através de uma sessão
# autenticada real, não apenas no nível de model (já coberto em
# `tests/test_contas_models.py`). O que importa aqui é `request.user` depois
# de um login de verdade pelo test client — por isso cada cenário autentica
# via `POST /login/` (ciclo HTTP completo) e só então inspeciona
# `response.wsgi_request.user`, o `request.user` real da requisição seguinte
# servida através da sessão, nunca uma consulta direta ao ORM.
# ---------------------------------------------------------------------------


def _usuario_da_sessao_autenticada(client, matricula, senha):
    """Autentica via `POST /login/` (ciclo HTTP real) e devolve o
    `request.user` de uma requisição subsequente à Home, obtido de
    `response.wsgi_request` — a mesma instância que qualquer view protegida
    do WMS veria em `request.user` (FR-013)."""
    login_response = client.post(
        reverse("login"),
        {"username": matricula, "password": senha},
    )
    assert login_response.status_code == 302, "pré-condição: login deveria suceder"

    home_response = client.get(reverse("home"))
    assert home_response.status_code == 200

    return home_response.wsgi_request.user


@pytest.mark.django_db
def test_usuario_com_papel_unico_tem_exatamente_esse_papel_sem_heranca(
    client, usuario_ativo, senha_valida
):
    PapelUsuario.objects.create(usuario=usuario_ativo, papel=Papel.REQUISITANTE)

    usuario_sessao = _usuario_da_sessao_autenticada(
        client, usuario_ativo.matricula, senha_valida
    )

    assert usuario_sessao.pk == usuario_ativo.pk
    assert usuario_sessao.tem_papel(Papel.REQUISITANTE) is True

    # FR-015: nenhum outro papel do catálogo é concedido implicitamente.
    outros_papeis = [codigo for codigo in Papel if codigo != Papel.REQUISITANTE]
    assert usuario_sessao.tem_papel(*outros_papeis) is False


@pytest.mark.django_db
def test_usuario_com_multiplos_papeis_simultaneos_expoe_todos_sem_conceder_outros(
    client, usuario_ativo, senha_valida
):
    # Cenário real: chefe do almoxarifado acumula três papéis explícitos
    # simultaneamente (spec.md, User Story 3, Acceptance Scenario 2).
    papeis_atribuidos = {
        Papel.FUNCIONARIO_ALMOXARIFADO,
        Papel.CHEFE_SETOR,
        Papel.CHEFE_ALMOXARIFADO,
    }
    for papel in papeis_atribuidos:
        PapelUsuario.objects.create(usuario=usuario_ativo, papel=papel)

    usuario_sessao = _usuario_da_sessao_autenticada(
        client, usuario_ativo.matricula, senha_valida
    )

    codigos_na_sessao = set(usuario_sessao.papeis.all().values_list("papel", flat=True))
    assert codigos_na_sessao == papeis_atribuidos

    for papel in papeis_atribuidos:
        assert usuario_sessao.tem_papel(papel) is True

    # Um papel não atribuído continua ausente mesmo com múltiplos papéis
    # concedidos ao mesmo usuário — nenhum concede implicitamente a
    # capacidade de outro (FR-015).
    assert usuario_sessao.tem_papel(Papel.ADMINISTRADOR_SISTEMA) is False
    assert usuario_sessao.tem_papel(Papel.REQUISITANTE) is False
    assert usuario_sessao.tem_papel(Papel.AUDITOR) is False


@pytest.mark.django_db
def test_usuario_autenticado_expoe_exatamente_um_setor_nunca_none(
    client, usuario_ativo, senha_valida, setor
):
    usuario_sessao = _usuario_da_sessao_autenticada(
        client, usuario_ativo.matricula, senha_valida
    )

    assert usuario_sessao.setor is not None
    assert usuario_sessao.setor.pk == setor.pk
