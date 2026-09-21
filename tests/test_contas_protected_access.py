"""Testes de proteção de superfícies e retorno seguro pós-login (User Story 2).

Cobre FR-006, FR-008 a FR-012, FR-010a, `INV-AUTH-001`
(`docs/domain/invariants-matrix.md`) e SC-005/SC-006 de `spec.md`, seguindo o
contrato descrito em `contracts/protecao-e-redirecionamento.md` (seções
"Resolução segura do destino pós-login" e "Fallback de autorização") e as
decisões de `research.md` R8/R9.

TDD: escritos antes de `WMSLoginView`/`RetornoPosLoginMiddleware` (T026-T029)
existirem. Vários cenários abaixo DEVEM falhar agora, pelo motivo documentado
em cada teste — não por erro de escrita do teste. Alguns cenários já passam
"de graça" hoje, porque `contracts/protecao-e-redirecionamento.md` e
`tasks.md` (Phase 3) documentam que o `LoginView` nativo já resolve
corretamente a checagem de host/esquema (`url_has_allowed_host_and_scheme`)
e que `ModelBackend.get_user()` já reavalia `is_active` a cada requisição —
nenhum dos dois depende de `WMSLoginView`/`RetornoPosLoginMiddleware`.

Usa o urlconf de teste `tests/urls_test_permission_denied.py` (T024) via
`pytest.mark.urls`, que expõe:
- `destino_autorizado` (`login_required`, sempre 200) — destino interno,
  existente e autorizado;
- `destino_nao_autorizado` (`login_required`, sempre `PermissionDenied`) —
  destino interno, existente, mas não autorizado;
- as rotas `login`/`home` de `contas.urls`, incluídas nesse mesmo urlconf.
"""

from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from django.urls import reverse

pytestmark = [pytest.mark.django_db, pytest.mark.urls("tests.urls_test_permission_denied")]

MARCADOR_SESSAO = "_retorno_pos_login_destino"


def _login_url_com_next(destino):
    """URL de login com `?next=<destino>`, imitando o redirecionamento que
    `login_required`/`LoginRequiredMixin` produziriam ao proteger qualquer
    superfície — evita depender, nestes testes, do encoding exato usado por
    esses utilitários nativos (já coberto em `tests/test_contas_home.py`)."""
    return f"{reverse('login')}?{urlencode({'next': destino})}"


def test_visitante_nao_autenticado_e_enviado_ao_login_com_next_sem_receber_conteudo(client):
    destino = reverse("destino_autorizado")

    response = client.get(destino)

    assert response.status_code == 302
    # Redirect nativo de `login_required`: corpo vazio — o conteúdo protegido
    # nunca é entregue a um visitante sem sessão válida (FR-008).
    assert response.content == b""

    destino_do_redirect = urlsplit(response.url)
    assert destino_do_redirect.path == reverse("login")

    query = parse_qs(destino_do_redirect.query)
    assert query.get("next") == [destino], "next deve apontar exatamente para o destino original"


def test_destino_interno_existente_e_autorizado_retorna_apos_login_sem_parametro_tecnico(
    client, usuario_ativo, senha_valida
):
    destino = reverse("destino_autorizado")

    resposta_login = client.post(
        _login_url_com_next(destino),
        {"username": usuario_ativo.matricula, "password": senha_valida},
    )

    assert resposta_login.status_code == 302
    assert resposta_login.url == destino, (
        "destino interno, existente e autorizado deve ser devolvido exatamente, "
        "sem nenhum parâmetro técnico de retorno na URL (FR-010, SC-005)"
    )

    # T026/T027: WMSLoginView.get_success_url() deve gravar o destino exato em
    # sessão logo após o login bem-sucedido. Falha agora porque a rota
    # `login` ainda usa o `LoginView` nativo (contas/urls.py), que nunca
    # grava esse marcador.
    assert client.session.get(MARCADOR_SESSAO) == destino, (
        "esperava o marcador de sessão do destino pendente gravado por "
        "WMSLoginView.get_success_url() — ainda não implementado (T026/T027)"
    )

    resposta_destino = client.get(destino)
    assert resposta_destino.status_code == 200
    assert resposta_destino.content == b"destino autorizado"

    # T028/T029: RetornoPosLoginMiddleware.process_view() deve consumir
    # (remover) o marcador na primeira requisição cujo `get_full_path()`
    # bata exatamente com o destino gravado.
    assert MARCADOR_SESSAO not in client.session, (
        "marcador de sessão deveria ter sido consumido (uso único) pelo "
        "RetornoPosLoginMiddleware — ainda não registrado em MIDDLEWARE (T028/T029)"
    )


def test_destino_interno_existente_mas_nao_autorizado_cai_na_home_na_primeira_requisicao(
    client, usuario_ativo, senha_valida
):
    destino = reverse("destino_nao_autorizado")

    resposta_login = client.post(
        _login_url_com_next(destino),
        {"username": usuario_ativo.matricula, "password": senha_valida},
    )
    assert resposta_login.status_code == 302
    assert resposta_login.url == destino

    resposta_destino = client.get(destino)

    # Contrato: RetornoPosLoginMiddleware.process_exception() deve reconhecer
    # que esta é a requisição imediatamente pós-login para o destino exato
    # esperado e converter o `PermissionDenied` levantado pela view em
    # redirect para a Home, em vez do 403 padrão. Falha agora: sem o
    # middleware registrado, o `PermissionDenied` é convertido normalmente
    # em 403 pelo próprio Django (`response.status_code` será 403, não 302).
    assert resposta_destino.status_code == 302, (
        "esperava redirect para Home via RetornoPosLoginMiddleware.process_exception() "
        "— middleware ainda não registrado em MIDDLEWARE (T028/T029)"
    )
    assert resposta_destino.url == reverse("home")


def test_mesma_url_nao_autorizada_fora_do_fluxo_de_login_mostra_403_padrao(
    client, usuario_ativo, senha_valida
):
    """Prova de que o fallback não é global nem residual: autenticado sem
    vir do redirecionamento de login para este destino específico, a mesma
    URL não autorizada deve sempre mostrar o 403 padrão do Django — nunca a
    Home. Já é verdade hoje (não há middleware algum) e deve continuar
    verdade depois de T028/T029, provando que o fallback é de uso único e
    vinculado ao destino exato, não uma regra global de "não autorizado
    → Home"."""
    logou = client.login(username=usuario_ativo.matricula, password=senha_valida)
    assert logou, "pré-condição do teste: login direto via client deveria funcionar"

    destino = reverse("destino_nao_autorizado")
    resposta = client.get(destino)

    assert resposta.status_code == 403


def test_query_string_forjada_manualmente_nao_tem_efeito_algum(client, usuario_ativo, senha_valida):
    """`?_retorno_pos_login=1` nunca existiu no contrato (o marcador vive só
    em sessão, nunca na URL) — adicioná-lo manualmente a uma URL não
    autorizada, acessada fora do fluxo de login, não deve mudar nada."""
    logou = client.login(username=usuario_ativo.matricula, password=senha_valida)
    assert logou, "pré-condição do teste: login direto via client deveria funcionar"

    destino = reverse("destino_nao_autorizado")
    resposta = client.get(f"{destino}?_retorno_pos_login=1")

    assert resposta.status_code == 403


def test_destino_legitimo_com_query_string_e_reconhecido_e_query_preservada(
    client, usuario_ativo, senha_valida
):
    destino_base = reverse("destino_autorizado")
    destino_com_query = f"{destino_base}?pagina=2&ordenacao=descricao"

    resposta_login = client.post(
        _login_url_com_next(destino_com_query),
        {"username": usuario_ativo.matricula, "password": senha_valida},
    )

    assert resposta_login.status_code == 302
    # Já verdade hoje: o `LoginView` nativo não separa path de query, então a
    # query legítima já é preservada no redirect mesmo sem `WMSLoginView`.
    assert resposta_login.url == destino_com_query, (
        "a query string legítima do destino deve ser preservada no redirect final"
    )

    # T026/T027: o marcador de sessão precisa considerar path + query exatos
    # (`request.get_full_path()`), não só o path — falha agora pelo mesmo
    # motivo do cenário anterior (marcador ainda não existe).
    assert client.session.get(MARCADOR_SESSAO) == destino_com_query, (
        "esperava o marcador de sessão vinculado ao destino exato (path + query) "
        "— WMSLoginView ainda não implementado (T026/T027)"
    )

    resposta_destino = client.get(destino_com_query)
    assert resposta_destino.status_code == 200

    assert MARCADOR_SESSAO not in client.session, (
        "marcador deveria ter sido consumido considerando a query exata "
        "— RetornoPosLoginMiddleware ainda não registrado (T028/T029)"
    )


def test_destino_externo_manipulado_e_rejeitado_cai_na_home(client, usuario_ativo, senha_valida):
    """FR-011/SC-006 — já garantido nativamente por
    `url_has_allowed_host_and_scheme()`, chamado pelo `LoginView` mesmo antes
    de `WMSLoginView` existir. Deve passar hoje."""
    resposta = client.post(
        _login_url_com_next("https://exemplo-externo.com/pagina-maliciosa/"),
        {"username": usuario_ativo.matricula, "password": senha_valida},
    )

    assert resposta.status_code == 302
    assert resposta.url == reverse("home"), (
        "next apontando para host externo nunca deve ser seguido — nunca deve "
        "resultar em redirecionamento fora do WMS"
    )


def test_destino_inexistente_cai_na_home_em_vez_de_seguir_para_rota_inexistente(
    client, usuario_ativo, senha_valida
):
    destino_inexistente = "/esta-rota-nao-existe-em-nenhum-urlconf/"

    resposta = client.post(
        _login_url_com_next(destino_inexistente),
        {"username": usuario_ativo.matricula, "password": senha_valida},
    )

    assert resposta.status_code == 302
    # Falha agora: o `LoginView` nativo não checa existência de rota via
    # `resolve()` — apenas host/esquema — então hoje ele redireciona direto
    # para `destino_inexistente` (que resultaria em 404 se seguido), em vez
    # de cair na Home. Corrigido por `WMSLoginView.get_redirect_url()`
    # (T026/T027).
    assert resposta.url == reverse("home"), (
        "destino inexistente deve cair na Home (FR-010a) — exige a checagem via "
        "django.urls.resolve() de WMSLoginView.get_redirect_url() (T026/T027)"
    )


def test_conta_desativada_apos_login_nega_acesso_na_proxima_requisicao_protegida(
    client, usuario_ativo, senha_valida
):
    """Cenário crítico — FR-006 / `INV-AUTH-001`.

    Este teste protege uma premissa NATIVA do Django
    (`ModelBackend.get_user()` + `AuthenticationMiddleware`, via
    `user_can_authenticate()` — ver `research.md` R9), não código próprio
    desta feature: nenhuma linha de `contas` verifica `is_active` a cada
    requisição manualmente. Deve passar hoje, independente de T026-T029. Se
    este teste passar a falhar no futuro, o motivo mais provável é uma
    mudança de versão do Django ou de `AUTHENTICATION_BACKENDS` que deixou
    de reavaliar `is_active` a cada request — não um bug introduzido em
    `contas`.
    """
    logou = client.login(username=usuario_ativo.matricula, password=senha_valida)
    assert logou, "pré-condição do teste: login direto via client deveria funcionar"

    resposta_home_autenticada = client.get(reverse("home"))
    assert resposta_home_autenticada.status_code == 200

    usuario_ativo.is_active = False
    usuario_ativo.save(update_fields=["is_active"])

    resposta_apos_desativacao = client.get(reverse("home"))

    assert resposta_apos_desativacao.status_code == 302
    assert urlsplit(resposta_apos_desativacao.url).path == reverse("login"), (
        "usuário desativado em sessão em andamento não pode continuar acessando "
        "superfície protegida, sem exigir logout explícito antes"
    )


# ---------------------------------------------------------------------------
# Propriedade central do fallback: vínculo ao destino EXATO + uso único.
#
# Os testes acima sempre visitam exatamente o destino gravado, então passariam
# igualmente com as duas alternativas explicitamente REJEITADAS em
# `research.md` R8 — comparação por prefixo e flag booleana global em sessão.
# Os testes abaixo existem para que essas duas alternativas falhem.
# ---------------------------------------------------------------------------


def test_marcador_de_um_destino_nao_libera_fallback_em_outro_destino(
    client, usuario_ativo, senha_valida
):
    """Login com `next=A` não pode converter em Home um `PermissionDenied` de B.

    Prova que o fallback é vinculado ao destino exato, e não uma flag global
    de sessão "acabei de logar" (alternativa rejeitada em `research.md` R8).
    """
    destino_autorizado = reverse("destino_autorizado")
    destino_nao_autorizado = reverse("destino_nao_autorizado")

    resposta_login = client.post(
        _login_url_com_next(destino_autorizado),
        {"username": usuario_ativo.matricula, "password": senha_valida},
    )
    assert resposta_login.status_code == 302
    assert client.session[MARCADOR_SESSAO] == destino_autorizado

    resposta = client.get(destino_nao_autorizado, raise_request_exception=False)

    assert resposta.status_code == 403, (
        "o marcador vale só para o destino gravado; um PermissionDenied em OUTRA "
        "rota continua sendo o 403 padrão do Django (Garantia 1 do contrato)"
    )
    assert client.session.get(MARCADOR_SESSAO) == destino_autorizado, (
        "o marcador do destino A não pode ser consumido por uma requisição a B"
    )


def test_marcador_nao_casa_por_prefixo_de_caminho(client, usuario_ativo, senha_valida):
    """`/destino-autorizado/` gravado não pode casar com uma sub-rota dele.

    Prova que a comparação é por igualdade exata de `get_full_path()`, nunca
    por prefixo (`research.md` R8, item 5 das garantias).
    """
    destino = reverse("destino_autorizado")

    client.post(
        _login_url_com_next(destino),
        {"username": usuario_ativo.matricula, "password": senha_valida},
    )
    assert client.session[MARCADOR_SESSAO] == destino

    # Mesmo prefixo, caminho diferente (query string a mais).
    client.get(f"{destino}?algo=1")

    assert client.session.get(MARCADOR_SESSAO) == destino, (
        "uma URL que apenas compartilha o prefixo do destino não pode consumir o marcador"
    )


def test_fallback_e_de_uso_unico_segunda_visita_volta_a_403(
    client, usuario_ativo, senha_valida
):
    """Depois do fallback, a mesma URL não autorizada volta a dar 403 padrão."""
    destino_nao_autorizado = reverse("destino_nao_autorizado")

    client.post(
        _login_url_com_next(destino_nao_autorizado),
        {"username": usuario_ativo.matricula, "password": senha_valida},
    )

    primeira = client.get(destino_nao_autorizado, raise_request_exception=False)
    assert primeira.status_code == 302, "primeira requisição pós-login cai na Home"
    assert primeira.url == reverse("home")
    assert MARCADOR_SESSAO not in client.session, "marcador consumido na primeira requisição"

    segunda = client.get(destino_nao_autorizado, raise_request_exception=False)
    assert segunda.status_code == 403, (
        "consumido o marcador, a mesma URL volta ao 403 padrão — o fallback não é global"
    )


def test_get_em_login_por_usuario_autenticado_nao_arma_o_marcador(
    client, usuario_ativo, senha_valida
):
    """`GET /login/?next=...` de quem já está logado não pode armar o marcador.

    `LoginView.dispatch()` chama `get_success_url()` no caminho
    `redirect_authenticated_user`, sem nenhuma autenticação ter ocorrido.
    Gravar o marcador ali permitiria armá-lo por GET, sem CSRF, para uma URL
    escolhida pelo próprio usuário — mascarando como Home um 403 legítimo
    (contracts/protecao-e-redirecionamento.md → Garantias 2 e 3).
    """
    client.force_login(usuario_ativo)
    destino_nao_autorizado = reverse("destino_nao_autorizado")

    resposta = client.get(_login_url_com_next(destino_nao_autorizado))

    assert resposta.status_code == 302
    assert MARCADOR_SESSAO not in client.session, (
        "nenhum login ocorreu nesta requisição; o marcador não pode existir"
    )

    # E o 403 daquela rota continua sendo um 403 comum.
    assert client.get(destino_nao_autorizado, raise_request_exception=False).status_code == 403


def test_next_apontando_para_a_propria_pagina_de_login_nao_gera_erro(
    client, usuario_ativo, senha_valida
):
    """`GET /login/?next=/login/` de quem já está logado não pode dar 500.

    O `LoginView` nativo levanta ValueError ("Redirection loop for
    authenticated user detected") quando o destino é o próprio path e
    `redirect_authenticated_user=True` — 500 acionável por link externo.
    """
    client.force_login(usuario_ativo)

    resposta = client.get(_login_url_com_next(reverse("login")))

    assert resposta.status_code == 302
    assert resposta.url == reverse("home"), "deve cair na Home, nunca em loop nem em 500"
