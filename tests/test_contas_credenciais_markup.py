"""Markup do login e da tela `/senha/` (propagação P1, credenciais) do redesign Observatory.

Fontes: `docs/redesign-observatory/contrato.md` (§3 Login e Credencial provisória; §8) e
`docs/redesign-observatory/plano.md` (§3, "Ganchos de markup" e "Contratos que não podem mudar").
O comportamento de credenciais (política de senha, vencimento, restrição da provisória, sessões)
está em `tests/test_contas_credenciais.py`; o shell e o logout, em `tests/test_shell.py`. Aqui só o
que o redesign pode quebrar sem que nenhum desses falhe:

- o login anônimo é UMA página sem shell (um só `<main>`, sem `.app`/`.side`/`.top`), com a marca
  como texto e os ganchos que `contas/js/login.js` consome (`data-login-*`);
- recusa de login anuncia o erro a leitor de tela (`role="alert"`, "Erro:" no título), nunca ecoa a
  senha e não mostra alerta nenhum quando não há erro;
- a ligação campo -> mensagem por `aria-describedby`/`aria-invalid` aponta sempre para um elemento
  que existe: o Django referencia `<auto_id>_error` e `<auto_id>_helptext` e o template precisa
  renderizá-los com esses ids, senão a associação acessível quebra em silêncio;
- `/senha/` nos dois estados da credencial (troca voluntária e definição provisória) vive dentro do
  shell com um único `<main id="main">` (sem `<main>` aninhado nem os contêineres legados), com os
  campos, o "Cancelar" e o título certos de cada estado, os ganchos de `static/js/envio.js` e sem
  jamais repopular uma senha.

O parsing é estrutural (`tests/html_helpers.py`).
"""

from datetime import timedelta

import pytest
from django.urls import reverse

from contas.organizacao import OperacaoRecusada
from tests.contas_helpers import (
    CAMPOS_SENHA,
    SENHA_NOVA_VALIDA,
    SENHA_TESTE,
    envelhecer_provisoria,
    membro,
    membro_provisorio,
    rota,
)
from tests.html_helpers import analisar

pytestmark = pytest.mark.django_db

MENSAGEM_LOGIN_RECUSADO = "Matrícula ou senha inválidas. Confira os dados e tente novamente."


def _ids_referenciados(no):
    return (no.get("aria-describedby") or "").split()


def _com_esse_id(documento, id_):
    return documento.buscar(id=id_)


def _todos_os_ids_referenciados_existem(documento, campos):
    """Todo id de `aria-describedby` de cada widget existe, uma única vez, no documento."""
    for campo in campos:
        for id_ in _ids_referenciados(campo):
            assert len(_com_esse_id(documento, id_)) == 1, (
                f"{campo.get('name')}: aria-describedby aponta para #{id_}, que não existe "
                "(ou existe mais de uma vez) no documento"
            )


# ---------------------------------------------------------------------------
# Login (anônimo)
# ---------------------------------------------------------------------------


def _login_get(client):
    resposta = client.get(reverse("login"))
    assert resposta.status_code == 200
    return analisar(resposta.content)


def test_login_e_uma_pagina_sem_shell_com_um_unico_main(client):
    documento = _login_get(client)

    principal = documento.unico("main")
    assert principal.get("id") == "main"
    assert principal.tem_classe("login")
    for classe in ("app", "side", "top", "page-container", "page-header", "appbar"):
        assert documento.buscar(classe=classe) == [], f".{classe} não pertence ao login"
    # O card do formulário e o título da página estão dentro do único <main>.
    card = principal.unico(classe="login-card")
    assert card.unico("h1").texto == "Entrar no sistema"
    assert len(documento.buscar("h1")) == 1


def test_login_traz_os_ganchos_de_javascript_do_formulario_e_do_botao(client):
    documento = _login_get(client)

    formulario = documento.unico("form", data_login_form=True)
    assert formulario.get("method", "").lower() == "post"
    assert formulario.buscar("input", name="csrfmiddlewaretoken")
    botao = formulario.unico("button", data_login_submit=True)
    assert botao.get("type") == "submit"
    assert botao.unico(data_login_submit_label=True).texto == "Entrar"
    # Os dois campos do formulário nativo continuam sendo os que o `AuthenticationForm` valida.
    assert formulario.unico("input", name="username")
    assert formulario.unico("input", name="password", type="password")


def test_login_sem_erro_nao_mostra_alerta_nem_marca_campo_invalido(client):
    documento = _login_get(client)

    assert documento.buscar(classe="error-box") == []
    assert documento.buscar(role="alert") == []
    assert documento.buscar(classe="field-error") == []
    assert documento.buscar(aria_invalid=True) == []
    assert "Erro:" not in documento.unico("title").texto


def test_login_recusado_anuncia_o_erro_sem_ecoar_a_senha(client, usuario_ativo):
    senha_digitada = "senha-digitada-que-nao-pode-voltar"

    resposta = client.post(
        reverse("login"), {"username": usuario_ativo.matricula, "password": senha_digitada}
    )

    assert resposta.status_code == 200
    documento = analisar(resposta.content)
    assert documento.unico("title").texto.startswith("Erro: ")
    principal = documento.unico("main")
    alerta = principal.unico(classe="error-box")
    assert alerta.get("role") == "alert"
    assert MENSAGEM_LOGIN_RECUSADO in alerta.texto
    # O caminho de recuperação acompanha o erro, mas fora do alerta (que só anuncia a recusa).
    recuperacao = principal.unico(classe="login-recovery")
    assert recuperacao.tem_classe("note")
    assert alerta not in list(recuperacao.ancestrais())
    assert recuperacao not in list(alerta.descendentes())
    assert "almoxarifado@saep.sp.gov.br" in recuperacao.texto
    assert recuperacao.unico("a").get("href") == "mailto:almoxarifado@saep.sp.gov.br"
    # Nenhuma senha volta no HTML, nem em atributo `value`.
    assert senha_digitada not in resposta.content.decode()
    assert not documento.unico("input", name="password").get("value")


def test_login_com_matricula_vazia_liga_o_campo_ao_proprio_erro(client):
    resposta = client.post(reverse("login"), {"username": "", "password": "qualquer-senha"})

    assert resposta.status_code == 200
    documento = analisar(resposta.content)
    campo = documento.unico("input", name="username")
    assert campo.get("aria-invalid") == "true"
    assert "id_username_error" in _ids_referenciados(campo)
    erro = documento.unico(id="id_username_error")
    assert erro.tag == "p" and erro.tem_classe("field-error") and erro.texto
    # O erro está no bloco do próprio campo, não solto na página.
    assert erro.pai is campo.pai
    # O campo da senha, que veio preenchido, não é marcado como inválido.
    senha = documento.unico("input", name="password")
    assert "aria-invalid" not in senha.attrs
    _todos_os_ids_referenciados_existem(documento, [campo, senha])


# ---------------------------------------------------------------------------
# /senha/ nos dois estados da credencial
# ---------------------------------------------------------------------------

ESTADOS = ["voluntaria", "provisoria"]


@pytest.fixture
def conta(request, setor):
    """A conta de cada estado, já autenticada no cliente do teste: `(usuario, estado)`."""
    estado = request.param
    if estado == "provisoria":
        usuario, _ = membro_provisorio(setor, "markup-prov")
    else:
        usuario = membro(setor, "markup-def")
    return usuario, estado


# Parametrização indireta: cada teste roda uma vez por estado da credencial.
POR_ESTADO = pytest.mark.parametrize("conta", ESTADOS, indirect=True)


@pytest.fixture
def senha_get(client, conta):
    usuario, estado = conta
    client.force_login(usuario)
    resposta = client.get(rota("definir_senha"))
    assert resposta.status_code == 200
    return estado, analisar(resposta.content)


@pytest.fixture
def senha_post_invalido(client, conta):
    """POST que erra em todos os campos possíveis do estado, com senhas reconhecíveis."""
    usuario, estado = conta
    client.force_login(usuario)
    dados = {
        CAMPOS_SENHA["nova"]: SENHA_NOVA_VALIDA,
        CAMPOS_SENHA["confirmacao"]: SENHA_NOVA_VALIDA + "-divergente",
    }
    if estado == "voluntaria":
        dados[CAMPOS_SENHA["atual"]] = "senha-atual-errada-digitada"
    resposta = client.post(rota("definir_senha"), dados)
    assert resposta.status_code == 200, "pré-condição: o POST inválido re-renderiza o formulário"
    return estado, analisar(resposta.content), resposta.content.decode(), dados


def _campos_de_senha(documento):
    campos = documento.unico("main").buscar("input", type="password")
    assert campos, "pré-condição: a tela tem campos de senha"
    return campos


@POR_ESTADO
def test_senha_vive_no_shell_com_um_unico_main_sem_estrutura_legada(senha_get):
    _, documento = senha_get

    principal = documento.unico("main")
    assert documento.unico(id="main") is principal
    assert principal.buscar("main") == [], "<main> aninhado"
    assert len(documento.buscar(classe="app")) == 1
    assert len(documento.buscar("aside", classe="side")) == 1
    for classe in ("page-container", "page-header", "appbar"):
        assert documento.buscar(classe=classe) == [], f".{classe} é estrutura legada"
    # Cabeçalho do base (`.top`) e o formulário no card, ambos dentro do <main>.
    assert principal.unico(classe="top")
    assert principal.unico(classe="card").tem_classe("card-form")
    assert principal.unico("form").esta_dentro_de("main")
    assert len(documento.buscar("h1")) == 1


@POR_ESTADO
def test_senha_tem_o_titulo_o_botao_e_os_campos_do_estado(senha_get):
    estado, documento = senha_get
    principal = documento.unico("main")
    formulario = principal.unico("form")
    nomes = {campo.get("name") for campo in formulario.buscar("input", type="password")}

    if estado == "provisoria":
        assert principal.unico("h1").texto == "Defina a sua senha"
        assert nomes == {CAMPOS_SENHA["nova"], CAMPOS_SENHA["confirmacao"]}
        assert "Senha atual" not in principal.texto
        assert formulario.unico(data_processing_submit_label=True).texto == "Definir senha"
    else:
        assert principal.unico("h1").texto == "Trocar a senha"
        assert nomes == set(CAMPOS_SENHA.values())
        assert "Senha atual" in formulario.texto
        assert formulario.unico(data_processing_submit_label=True).texto == "Trocar senha"


@POR_ESTADO
def test_senha_oferece_cancelar_para_a_home_so_na_troca_voluntaria(senha_get):
    estado, documento = senha_get
    formulario = documento.unico("main").unico("form")

    cancelar = [a for a in formulario.buscar("a") if a.texto == "Cancelar"]
    if estado == "voluntaria":
        assert len(cancelar) == 1
        assert cancelar[0].get("href") == reverse("home")
    else:
        # Sem retorno: não há para onde voltar enquanto a senha não for definida.
        assert cancelar == []
        assert reverse("home") not in {a.get("href") for a in documento.buscar("a", href=True)}


@POR_ESTADO
def test_senha_traz_os_ganchos_de_envio_e_o_script_que_os_consome(senha_get):
    estado, documento = senha_get
    formulario = documento.unico("main").unico("form", data_processing_form=True)

    assert formulario.get("method", "").lower() == "post"
    assert formulario.buscar("input", name="csrfmiddlewaretoken")
    esperado = "Definindo…" if estado == "provisoria" else "Trocando…"
    assert formulario.get("data-processing-label") == esperado
    botao = formulario.unico("button", data_processing_submit=True)
    assert botao.get("type") == "submit"
    assert botao.unico(data_processing_submit_label=True)
    scripts = [
        s for s in documento.buscar("script", src=True) if s.attrs["src"].endswith("/js/envio.js")
    ]
    assert len(scripts) == 1 and "defer" in scripts[0].attrs


@POR_ESTADO
def test_senha_sem_erro_todo_aria_describedby_aponta_para_elemento_existente(senha_get):
    _, documento = senha_get

    campos = _campos_de_senha(documento)
    _todos_os_ids_referenciados_existem(documento, campos)
    # A dica de cada campo com `help_text` é referenciada e renderizada mesmo sem erro.
    assert documento.unico(id="id_new_password1_helptext")
    # Sem erro: nada de alerta, de mensagem de campo nem de campo inválido.
    assert documento.buscar(classe="error-box") == []
    assert documento.buscar(classe="field-error") == []
    assert documento.buscar(aria_invalid=True) == []


@POR_ESTADO
def test_senha_com_erro_liga_cada_campo_invalido_ao_proprio_erro_e_mantem_as_dicas(
    senha_post_invalido,
):
    estado, documento, _, _ = senha_post_invalido

    campos = _campos_de_senha(documento)
    _todos_os_ids_referenciados_existem(documento, campos)
    invalidos = [campo for campo in campos if campo.get("aria-invalid") == "true"]
    esperados = {CAMPOS_SENHA["confirmacao"]} | (
        {CAMPOS_SENHA["atual"]} if estado == "voluntaria" else set()
    )
    assert {campo.get("name") for campo in invalidos} == esperados
    for campo in invalidos:
        id_do_erro = f"{campo.get('id')}_error"
        assert id_do_erro in _ids_referenciados(campo)
        erro = documento.unico(id=id_do_erro)
        assert erro.tem_classe("field-error") and erro.texto
        assert erro.pai is campo.pai, "o erro fica no bloco do próprio campo"
    # Um erro por campo inválido, e nenhum outro.
    assert len(documento.buscar(classe="field-error")) == len(invalidos)
    # A dica do campo continua renderizada ao lado do erro (o widget a referencia sempre).
    assert documento.unico(id="id_new_password1_helptext")


@POR_ESTADO
def test_senha_nunca_e_repopulada_nem_ecoada_apos_erro(senha_post_invalido):
    _, documento, conteudo, enviados = senha_post_invalido

    for campo in _campos_de_senha(documento):
        assert not campo.get("value"), f"{campo.get('name')} voltou preenchido"
    for senha in enviados.values():
        assert senha not in conteudo


def test_troca_recusada_pela_operacao_mostra_alerta_com_role_alert_dentro_do_card(
    client, setor, monkeypatch
):
    usuario = membro(setor, "markup-recusa")
    client.force_login(usuario)

    def _recusa(*args, **kwargs):
        raise OperacaoRecusada("A senha não pôde ser trocada.", "Entre em contato.")

    # A recusa de domínio da operação não tem caminho natural a partir de um POST válido (o
    # formulário já filtrou a senha atual e a política); só se força a recusa para verificar como
    # a tela a mostra. A operação em si é coberta por `test_contas_credenciais.py`.
    monkeypatch.setattr("contas.views.trocar_propria_senha", _recusa)

    resposta = client.post(
        rota("definir_senha"),
        {
            CAMPOS_SENHA["atual"]: SENHA_TESTE,
            CAMPOS_SENHA["nova"]: SENHA_NOVA_VALIDA,
            CAMPOS_SENHA["confirmacao"]: SENHA_NOVA_VALIDA,
        },
    )

    assert resposta.status_code == 200
    documento = analisar(resposta.content)
    card = documento.unico("main").unico(classe="card-form")
    alerta = card.unico(classe="error-box")
    assert alerta.get("role") == "alert"
    assert "A senha não pôde ser trocada. Entre em contato." in alerta.texto
    # Um erro só geral também anuncia o erro no título da aba.
    assert documento.unico("title").texto.startswith("Erro: ")
    # Erro geral não é erro de campo: nenhum campo é marcado como inválido por causa dele.
    assert documento.buscar(aria_invalid=True) == []
    _todos_os_ids_referenciados_existem(documento, _campos_de_senha(documento))


def test_definicao_recusada_pela_operacao_vira_erro_do_campo_da_nova_senha(
    client, setor, monkeypatch
):
    usuario, _ = membro_provisorio(setor, "markup-recusa-prov")
    client.force_login(usuario)

    def _recusa(*args, **kwargs):
        raise OperacaoRecusada("A senha não pôde ser definida.")

    monkeypatch.setattr("contas.views.definir_propria_senha", _recusa)

    resposta = client.post(
        rota("definir_senha"),
        {CAMPOS_SENHA["nova"]: SENHA_NOVA_VALIDA, CAMPOS_SENHA["confirmacao"]: SENHA_NOVA_VALIDA},
    )

    assert resposta.status_code == 200
    documento = analisar(resposta.content)
    campo = documento.unico("input", name=CAMPOS_SENHA["nova"])
    assert campo.get("aria-invalid") == "true"
    erro = documento.unico(id="id_new_password1_error")
    assert "A senha não pôde ser definida." in erro.texto
    assert "id_new_password1_error" in _ids_referenciados(campo)
    _todos_os_ids_referenciados_existem(documento, _campos_de_senha(documento))


# ---------------------------------------------------------------------------
# Foco inicial, ordem do aria-describedby e textos de ajuda (correções do gate visual)
# ---------------------------------------------------------------------------

AJUDA_NOVA_SENHA = (
    "Use pelo menos 8 caracteres, sem ser só números. "
    "Evite sua matrícula, seu nome e senhas comuns."
)


def _com_foco(documento, nomes):
    """Nomes dos campos que têm `autofocus` (a tela deve ter exatamente um)."""
    campos = [c for c in documento.buscar("input") if c.get("name") in nomes]
    return [c.get("name") for c in campos if "autofocus" in c.attrs]


def test_login_sem_erro_foca_a_matricula(client):
    documento = _login_get(client)

    assert _com_foco(documento, {"username", "password"}) == ["username"]
    # A Matrícula não tem dica; a Senha aponta para a orientação de primeiro acesso.
    assert not documento.unico("input", name="username").get("aria-describedby")
    assert _ids_referenciados(documento.unico("input", name="password")) == [
        "id_password_helptext"
    ]


def test_login_recusado_foca_a_senha_e_liga_os_dois_campos_ao_alerta_sem_acusar_nenhum(
    client, usuario_ativo
):
    resposta = client.post(
        reverse("login"), {"username": usuario_ativo.matricula, "password": "senha-errada-1"}
    )

    documento = analisar(resposta.content)
    assert _com_foco(documento, {"username", "password"}) == ["password"]
    for nome in ("username", "password"):
        campo = documento.unico("input", name=nome)
        assert "login-erro" in _ids_referenciados(campo)
        assert "aria-invalid" not in campo.attrs, "o erro geral não aponta um campo como culpado"


def test_login_com_erro_de_campo_foca_o_campo_invalido_e_nao_liga_ao_alerta_geral(client):
    resposta = client.post(reverse("login"), {"username": "", "password": "qualquer-senha"})

    documento = analisar(resposta.content)
    assert _com_foco(documento, {"username", "password"}) == ["username"]
    assert "login-erro" not in _ids_referenciados(documento.unico("input", name="username"))


def test_login_com_senha_vazia_foca_a_senha(client, usuario_ativo):
    resposta = client.post(reverse("login"), {"username": usuario_ativo.matricula, "password": ""})

    documento = analisar(resposta.content)
    assert _com_foco(documento, {"username", "password"}) == ["password"]


@POR_ESTADO
def test_senha_sem_erro_foca_o_primeiro_campo_do_formulario(senha_get):
    estado, documento = senha_get

    esperado = CAMPOS_SENHA["atual"] if estado == "voluntaria" else CAMPOS_SENHA["nova"]
    assert _com_foco(documento, set(CAMPOS_SENHA.values())) == [esperado]


@POR_ESTADO
def test_senha_com_erro_foca_so_o_primeiro_campo_invalido_na_ordem_do_formulario(
    senha_post_invalido,
):
    estado, documento, _, _ = senha_post_invalido

    # Voluntária: a senha atual (errada) vem antes da confirmação divergente.
    esperado = CAMPOS_SENHA["atual"] if estado == "voluntaria" else CAMPOS_SENHA["confirmacao"]
    assert _com_foco(documento, set(CAMPOS_SENHA.values())) == [esperado]


def test_senha_com_so_erro_geral_foca_o_primeiro_campo(client, setor, monkeypatch):
    usuario = membro(setor, "markup-foco-geral")
    client.force_login(usuario)

    def _recusa(*args, **kwargs):
        raise OperacaoRecusada("A senha não pôde ser trocada.")

    monkeypatch.setattr("contas.views.trocar_propria_senha", _recusa)
    resposta = client.post(
        rota("definir_senha"),
        {
            CAMPOS_SENHA["atual"]: SENHA_TESTE,
            CAMPOS_SENHA["nova"]: SENHA_NOVA_VALIDA,
            CAMPOS_SENHA["confirmacao"]: SENHA_NOVA_VALIDA,
        },
    )

    documento = analisar(resposta.content)
    assert _com_foco(documento, set(CAMPOS_SENHA.values())) == [CAMPOS_SENHA["atual"]]


@POR_ESTADO
def test_senha_com_erro_o_aria_describedby_lista_o_erro_antes_da_dica(client, conta):
    usuario, estado = conta
    client.force_login(usuario)
    # Nova senha ausente: erro de campo "obrigatório" na própria nova senha, que tem dica.
    dados = {CAMPOS_SENHA["nova"]: "", CAMPOS_SENHA["confirmacao"]: SENHA_NOVA_VALIDA}
    if estado == "voluntaria":
        dados[CAMPOS_SENHA["atual"]] = SENHA_TESTE

    resposta = client.post(rota("definir_senha"), dados)

    documento = analisar(resposta.content)
    nova = documento.unico("input", name=CAMPOS_SENHA["nova"])
    assert _ids_referenciados(nova) == ["id_new_password1_error", "id_new_password1_helptext"]
    _todos_os_ids_referenciados_existem(documento, _campos_de_senha(documento))
    assert _com_foco(documento, set(CAMPOS_SENHA.values())) == [CAMPOS_SENHA["nova"]]


SENHAS_FORA_DA_POLITICA = [
    pytest.param("Ab1-xyz", id="curta"),
    pytest.param("qwertyuiop", id="comum"),
    pytest.param("48291736052", id="so-numeros"),
]


def _enviar_senha_nova(client, conta, nova, confirmacao=None):
    """POST com a Nova senha e a Confirmação dadas (e a Senha atual certa na troca)."""
    usuario, estado = conta
    client.force_login(usuario)
    dados = {
        CAMPOS_SENHA["nova"]: nova,
        CAMPOS_SENHA["confirmacao"]: nova if confirmacao is None else confirmacao,
    }
    if estado == "voluntaria":
        dados[CAMPOS_SENHA["atual"]] = SENHA_TESTE
    resposta = client.post(rota("definir_senha"), dados)
    assert resposta.status_code == 200, "pré-condição: o POST inválido re-renderiza o formulário"
    return analisar(resposta.content)


@POR_ESTADO
@pytest.mark.parametrize("nova", SENHAS_FORA_DA_POLITICA)
def test_senha_fora_da_politica_acusa_a_nova_senha_com_erro_antes_da_dica(client, conta, nova):
    documento = _enviar_senha_nova(client, conta, nova)

    nova_senha = documento.unico("input", name=CAMPOS_SENHA["nova"])
    confirmacao = documento.unico("input", name=CAMPOS_SENHA["confirmacao"])
    # Erro e dica no mesmo campo, nessa ordem; o foco cai nele.
    assert nova_senha.get("aria-invalid") == "true"
    assert _ids_referenciados(nova_senha) == ["id_new_password1_error", "id_new_password1_helptext"]
    erro = documento.unico(id="id_new_password1_error")
    assert erro.tem_classe("field-error") and erro.texto
    assert erro.pai is nova_senha.pai, "o erro fica no bloco da Nova senha"
    assert _com_foco(documento, set(CAMPOS_SENHA.values())) == [CAMPOS_SENHA["nova"]]
    # A Confirmação não é culpada: sem erro, sem `aria-invalid`, sem dica.
    assert "aria-invalid" not in confirmacao.attrs
    assert not confirmacao.get("aria-describedby")
    assert documento.buscar(id="id_new_password2_error") == []
    assert len(documento.buscar(classe="field-error")) == 1
    _todos_os_ids_referenciados_existem(documento, _campos_de_senha(documento))


@POR_ESTADO
def test_senha_com_confirmacao_diferente_acusa_so_a_confirmacao(client, conta):
    documento = _enviar_senha_nova(
        client, conta, SENHA_NOVA_VALIDA, confirmacao=SENHA_NOVA_VALIDA + "-divergente"
    )

    nova_senha = documento.unico("input", name=CAMPOS_SENHA["nova"])
    confirmacao = documento.unico("input", name=CAMPOS_SENHA["confirmacao"])
    assert confirmacao.get("aria-invalid") == "true"
    assert _ids_referenciados(confirmacao) == ["id_new_password2_error"]
    assert "não correspondem" in documento.unico(id="id_new_password2_error").texto
    assert "aria-invalid" not in nova_senha.attrs
    assert _ids_referenciados(nova_senha) == ["id_new_password1_helptext"]
    assert _com_foco(documento, set(CAMPOS_SENHA.values())) == [CAMPOS_SENHA["confirmacao"]]
    _todos_os_ids_referenciados_existem(documento, _campos_de_senha(documento))


@POR_ESTADO
def test_senha_sem_erro_so_a_nova_senha_tem_dica_e_a_confirmacao_nao(senha_get):
    _, documento = senha_get

    nova = documento.unico("input", name=CAMPOS_SENHA["nova"])
    confirmacao = documento.unico("input", name=CAMPOS_SENHA["confirmacao"])
    assert _ids_referenciados(nova) == ["id_new_password1_helptext"]
    assert not confirmacao.get("aria-describedby")
    assert documento.buscar(id="id_new_password2_helptext") == []
    assert documento.unico(id="id_new_password1_helptext").texto == AJUDA_NOVA_SENHA


@pytest.fixture
def troca_get_e_post(client, setor):
    """Conta definitiva autenticada: `(GET, POST com a Senha atual errada)` já analisados."""
    client.force_login(membro(setor, "markup-dica-atual"))
    get = analisar(client.get(rota("definir_senha")).content)
    post = analisar(
        client.post(
            rota("definir_senha"),
            {
                CAMPOS_SENHA["atual"]: "senha-atual-errada-digitada",
                CAMPOS_SENHA["nova"]: SENHA_NOVA_VALIDA,
                CAMPOS_SENHA["confirmacao"]: SENHA_NOVA_VALIDA,
            },
        ).content
    )
    return get, post


def test_senha_atual_da_troca_tem_dica_com_e_sem_erro_e_o_erro_vem_antes(troca_get_e_post):
    sem_erro, com_erro = troca_get_e_post
    dica = (
        "Esqueceu a senha atual? Saia e peça ao administrador do sistema uma senha provisória."
    )

    atual = sem_erro.unico("input", name=CAMPOS_SENHA["atual"])
    assert _ids_referenciados(atual) == ["id_old_password_helptext"]
    assert sem_erro.unico(id="id_old_password_helptext").texto == dica

    atual = com_erro.unico("input", name=CAMPOS_SENHA["atual"])
    assert atual.get("aria-invalid") == "true"
    assert _ids_referenciados(atual) == ["id_old_password_error", "id_old_password_helptext"]
    assert com_erro.unico(id="id_old_password_helptext").texto == dica
    assert _com_foco(com_erro, set(CAMPOS_SENHA.values())) == [CAMPOS_SENHA["atual"]]
    _todos_os_ids_referenciados_existem(com_erro, _campos_de_senha(com_erro))


def test_login_a_senha_aponta_para_a_dica_com_e_sem_recusa_e_a_matricula_nao_tem_dica(
    client, usuario_ativo
):
    from contas.forms import ajuda_primeiro_acesso

    # Sem recusa: só a dica. Com a recusa: a dica e depois o alerta geral (ids gerais por último).
    sem_recusa = _login_get(client)
    assert _ids_referenciados(sem_recusa.unico("input", name="password")) == [
        "id_password_helptext"
    ]
    com_recusa = _login_recusado(client, usuario_ativo)
    assert _ids_referenciados(com_recusa.unico("input", name="password")) == [
        "id_password_helptext",
        ID_ALERTA_LOGIN,
    ]
    # A Matrícula nunca tem dica; só o alerta, com a recusa.
    assert not sem_recusa.unico("input", name="username").get("aria-describedby")
    assert _ids_referenciados(com_recusa.unico("input", name="username")) == [ID_ALERTA_LOGIN]
    # A mensagem da recusa continua genérica (FR-003) e o texto da dica é o do formulário.
    assert MENSAGEM_LOGIN_RECUSADO in com_recusa.unico(id=ID_ALERTA_LOGIN).texto
    assert "senha provisória" in ajuda_primeiro_acesso()


# ---------------------------------------------------------------------------
# Alerta do login ligado aos campos, nota de recuperação, "Mostrar senha", título de erro e shell
# provisório (correções do gate visual)
# ---------------------------------------------------------------------------

ID_ALERTA_LOGIN = "login-erro"
EMAIL_ALMOXARIFADO = "almoxarifado@saep.sp.gov.br"


def _login_recusado(client, usuario_ativo):
    resposta = client.post(
        reverse("login"), {"username": usuario_ativo.matricula, "password": "senha-errada-1"}
    )
    assert resposta.status_code == 200, "pré-condição: o login recusado re-renderiza o formulário"
    return analisar(resposta.content)


def test_login_recusado_o_alerta_tem_o_id_que_os_dois_campos_referenciam(client, usuario_ativo):
    documento = _login_recusado(client, usuario_ativo)

    # O id existe uma única vez, é o do alerta (`role="alert"`) e ambos os campos o referenciam.
    alertas = documento.buscar(id=ID_ALERTA_LOGIN)
    assert len(alertas) == 1
    assert alertas[0].get("role") == "alert" and alertas[0].tem_classe("error-box")
    for nome in ("username", "password"):
        campo = documento.unico("input", name=nome)
        assert _ids_referenciados(campo).count(ID_ALERTA_LOGIN) == 1
    _todos_os_ids_referenciados_existem(
        documento, [documento.unico("input", name=n) for n in ("username", "password")]
    )


def test_login_sem_alerta_geral_nao_renderiza_nem_referencia_o_id_do_alerta(client):
    # Sem erro nenhum e com erro só de campo: nada de `login-erro` no documento nem nos campos.
    sem_erro = _login_get(client)
    so_campo = analisar(
        client.post(reverse("login"), {"username": "", "password": "qualquer-senha"}).content
    )

    for documento in (sem_erro, so_campo):
        assert documento.buscar(id=ID_ALERTA_LOGIN) == []
        for nome in ("username", "password"):
            assert ID_ALERTA_LOGIN not in _ids_referenciados(
                documento.unico("input", name=nome)
            )


def _nota_de_recuperacao(documento):
    principal = documento.unico("main")
    nota = principal.unico(classe="login-recovery")
    assert nota.tem_classe("note")
    assert nota.esta_dentro_de("main") and nota.pai is principal.unico(classe="login-card")
    return nota


def test_login_mostra_a_nota_de_recuperacao_sem_erro_e_fora_de_qualquer_alerta(client):
    documento = _login_get(client)

    nota = _nota_de_recuperacao(documento)
    assert documento.buscar(role="alert") == []
    assert nota.unico("a").get("href") == f"mailto:{EMAIL_ALMOXARIFADO}"
    assert EMAIL_ALMOXARIFADO in nota.texto
    # Abaixo do botão de envio (não dentro do formulário).
    assert not nota.esta_dentro_de("form")
    ordem = list(documento.unico("main").descendentes())
    assert ordem.index(documento.unico("button", data_login_submit=True)) < ordem.index(nota)


def _recusa_por_causa(causa, client, setor, usuario_ativo, senha_valida):
    """POST de login recusado por cada causa distinta; devolve o documento da resposta."""
    if causa == "senha-errada":
        dados = {"username": usuario_ativo.matricula, "password": "senha-errada-1"}
    elif causa == "matricula-inexistente":
        dados = {"username": "NAO-EXISTE-1", "password": senha_valida}
    elif causa == "conta-inativa":
        inativo = membro(setor, "markup-inativo", is_active=False)
        dados = {"username": inativo.matricula, "password": SENHA_TESTE}
    else:  # provisória vencida
        provisorio, senha = membro_provisorio(setor, "markup-vencida")
        envelhecer_provisoria(provisorio, timedelta(days=8))
        dados = {"username": provisorio.matricula, "password": senha}
    resposta = client.post(reverse("login"), dados)
    assert resposta.status_code == 200, f"pré-condição: {causa} recusa o login"
    return analisar(resposta.content)


@pytest.mark.parametrize(
    "causa", ["senha-errada", "matricula-inexistente", "conta-inativa", "provisoria-vencida"]
)
def test_login_recusado_tem_a_mesma_nota_e_o_mesmo_alerta_qualquer_que_seja_a_causa(
    causa, client, setor, usuario_ativo, senha_valida
):
    referencia = _recusa_por_causa("senha-errada", client, setor, usuario_ativo, senha_valida)
    documento = _recusa_por_causa(causa, client, setor, usuario_ativo, senha_valida)

    nota = _nota_de_recuperacao(documento)
    alerta = documento.unico("main").unico(role="alert")
    # A nota fica fora do alerta e, como a mensagem do alerta, não diz o que deu errado (FR-003).
    assert nota not in list(alerta.descendentes()) and alerta not in list(nota.ancestrais())
    assert MENSAGEM_LOGIN_RECUSADO in alerta.texto
    assert nota.texto == _nota_de_recuperacao(referencia).texto
    assert alerta.texto == referencia.unico("main").unico(role="alert").texto
    assert nota.unico("a").get("href") == f"mailto:{EMAIL_ALMOXARIFADO}"


def _caixas_de_mostrar_senha(documento):
    return documento.buscar("input", data_mostrar_senha=True)


def _scripts_mostrar_senha(documento):
    return [
        s
        for s in documento.buscar("script", src=True)
        if s.attrs["src"].endswith("/js/mostrar-senha.js")
    ]


def _confere_caixa_de_mostrar_senha(documento):
    """Uma caixa, não enviada, dentro do mesmo formulário dos campos de senha, com o script."""
    caixas = _caixas_de_mostrar_senha(documento)
    assert len(caixas) == 1
    caixa = caixas[0]
    assert caixa.get("type") == "checkbox"
    assert "name" not in caixa.attrs, "a caixa não pode ser enviada com o formulário"
    formulario = next(a for a in caixa.ancestrais() if a.tag == "form")
    senhas = formulario.buscar("input", type="password")
    assert senhas, "pré-condição: o formulário da caixa tem campos de senha"
    assert senhas == documento.unico("main").buscar("input", type="password"), (
        "a caixa tem de estar no formulário que contém TODOS os campos de senha da tela"
    )
    # `static/js/mostrar-senha.js` acha os campos pelo `autocomplete`; sem ele, a caixa é inerte.
    for campo in senhas:
        assert campo.get("autocomplete") in {"current-password", "new-password"}, campo.get("name")
    scripts = _scripts_mostrar_senha(documento)
    assert len(scripts) == 1 and "defer" in scripts[0].attrs


def test_login_oferece_a_caixa_mostrar_senha_sem_enviar_nada_ao_servidor(client, usuario_ativo):
    for documento in (_login_get(client), _login_recusado(client, usuario_ativo)):
        _confere_caixa_de_mostrar_senha(documento)
        caixa = _caixas_de_mostrar_senha(documento)[0]
        # No bloco do campo da senha (dentro de um `<label>` próprio), não no da matrícula.
        assert caixa.pai.tag == "label" and "Mostrar senha" in caixa.pai.texto
        assert caixa.pai.pai is documento.unico("input", name="password").pai


@POR_ESTADO
def test_senha_oferece_a_caixa_mostrar_senhas_sem_enviar_nada_ao_servidor(senha_get):
    _, documento = senha_get

    _confere_caixa_de_mostrar_senha(documento)
    caixa = _caixas_de_mostrar_senha(documento)[0]
    # Abaixo da confirmação, no bloco do último campo de senha.
    assert caixa.pai.pai is documento.unico("input", name=CAMPOS_SENHA["confirmacao"]).pai


@POR_ESTADO
def test_senha_com_erro_continua_oferecendo_a_caixa_mostrar_senhas(senha_post_invalido):
    _, documento, _, _ = senha_post_invalido

    _confere_caixa_de_mostrar_senha(documento)


@POR_ESTADO
def test_senha_so_tem_o_prefixo_erro_no_titulo_quando_ha_erro(senha_get, senha_post_invalido):
    _, sem_erro = senha_get
    _, com_erro, _, _ = senha_post_invalido

    assert not sem_erro.unico("title").texto.startswith("Erro")
    assert com_erro.unico("title").texto.startswith("Erro: ")
    # O resto do título é o mesmo: o prefixo é o único acréscimo.
    assert com_erro.unico("title").texto.removeprefix("Erro: ") == sem_erro.unico("title").texto


@POR_ESTADO
def test_senha_renderiza_so_as_dicas_dos_campos_que_as_tem_com_e_sem_erro(
    senha_get, senha_post_invalido
):
    estado, sem_erro = senha_get
    _, com_erro, _, _ = senha_post_invalido
    # Nova senha sempre; Senha atual só na troca voluntária; a Confirmação nunca.
    esperados = (["id_old_password_helptext"] if estado == "voluntaria" else []) + [
        "id_new_password1_helptext"
    ]

    for documento in (sem_erro, com_erro):
        dicas = documento.buscar(classe="field-hint")
        assert [d.get("id") for d in dicas] == esperados
        nova = documento.unico(id="id_new_password1_helptext")
        assert nova.tag == "p" and nova.texto == AJUDA_NOVA_SENHA
        assert all(d.buscar() == [] for d in dicas), "a dica é texto simples, sem marcação"
        ids_de_dica = [
            n.get("id") for n in documento.buscar() if (n.get("id") or "").endswith("_helptext")
        ]
        assert ids_de_dica == esperados
        _todos_os_ids_referenciados_existem(documento, _campos_de_senha(documento))


@POR_ESTADO
def test_senha_shell_da_credencial_provisoria_nao_tem_botao_menu_e_a_definitiva_tem(senha_get):
    estado, documento = senha_get

    lateral = documento.unico("aside", classe="side")
    menus = documento.buscar(data_menu_toggle=True)
    botoes_menu = [b for b in documento.buscar("button") if b.texto == "Menu"]
    if estado == "provisoria":
        assert lateral.tem_classe("side-provisoria")
        assert menus == [] and botoes_menu == []
        assert documento.buscar(aria_controls=True) == []
    else:
        assert not lateral.tem_classe("side-provisoria")
        assert len(menus) == 1 and menus == botoes_menu
        assert menus[0].get("aria-expanded") == "false"
        assert documento.unico(id=menus[0].get("aria-controls")).esta_dentro_de("aside")


def test_home_da_conta_definitiva_mantem_o_botao_menu_e_nao_marca_a_sidebar_como_provisoria(
    client, requisitante, senha_valida
):
    assert client.login(username=requisitante.matricula, password=senha_valida)

    documento = analisar(client.get(reverse("home")).content)

    lateral = documento.unico("aside", classe="side")
    assert not lateral.tem_classe("side-provisoria")
    assert len(documento.buscar("button", data_menu_toggle=True)) == 1
    assert documento.unico("nav", aria_label="Seções")


def test_ordem_do_aria_describedby_nao_vaza_para_outros_formularios():
    from django import forms

    class Outro(forms.Form):
        campo = forms.CharField(help_text="dica")

    formulario = Outro({"campo": ""})
    assert formulario["campo"].aria_describedby == "id_campo_helptext id_campo_error"


def test_textos_de_ajuda_citam_os_valores_vigentes_da_validade_e_da_politica():
    """As dicas do login e da Nova senha repetem números que vivem em outro lugar
    (`VALIDADE_SENHA_PROVISORIA`, `MinimumLengthValidator`): se a regra mudar, o texto tem de
    mudar junto. Lê-se o `help_text` do formulário, que é o que o template renderiza."""
    from django.conf import settings

    from contas.credenciais import VALIDADE_SENHA_PROVISORIA
    from contas.forms import DefinirSenhaForm, WMSAuthenticationForm

    validade = VALIDADE_SENHA_PROVISORIA
    assert validade == timedelta(days=validade.days), "validade em dias inteiros"
    dica_do_login = WMSAuthenticationForm().fields["password"].help_text
    assert f"Ela vale {validade.days} dias a partir da emissão" in dica_do_login

    minimo = next(
        v.get("OPTIONS", {}).get("min_length", 8)
        for v in settings.AUTH_PASSWORD_VALIDATORS
        if v["NAME"].endswith("MinimumLengthValidator")
    )
    dica_da_nova_senha = DefinirSenhaForm(None).fields["new_password1"].help_text
    assert f"pelo menos {minimo} caracteres" in dica_da_nova_senha
    assert dica_da_nova_senha == AJUDA_NOVA_SENHA


# ---------------------------------------------------------------------------
# Aviso de Caps Lock, matrícula oculta e confirmação no navegador (2ª rodada do gate visual).
# O comportamento é de JavaScript (`static/js/caps-lock.js`, `confirmacao-senha.js`); aqui só o que
# o servidor entrega e de que o script depende.
# ---------------------------------------------------------------------------


def _scripts_de(documento, nome):
    return [
        s for s in documento.buscar("script", src=True) if s.attrs["src"].endswith(f"/js/{nome}")
    ]


def _bloco_do_campo(campo):
    """O `.field` mais próximo do widget."""
    return next(a for a in campo.ancestrais() if a.tem_classe("field"))


def _confere_aviso_de_caps_lock(documento, campos_de_senha):
    """Cada campo de senha tem, no seu `.field[data-caps-lock]`, exatamente um aviso vazio e
    `aria-live`, fora do `aria-describedby`; o script é incluído uma vez, com `defer`."""
    assert campos_de_senha, "pré-condição: a tela tem campos de senha"
    avisos_da_tela = documento.buscar(data_caps_lock_aviso=True)
    assert len(avisos_da_tela) == len(campos_de_senha), "um aviso por campo de senha, nenhum a mais"
    blocos = []
    for campo in campos_de_senha:
        bloco = _bloco_do_campo(campo)
        assert "data-caps-lock" in bloco.attrs, f"{campo.get('name')}: .field sem data-caps-lock"
        assert bloco.buscar("input", type="password") == [campo], "um só campo de senha por bloco"
        aviso = bloco.unico(data_caps_lock_aviso=True)
        blocos.append(bloco)
        # Região viva que nasce vazia: o script escreve a mensagem (que vem do atributo).
        assert aviso.get("aria-live") == "polite"
        assert aviso.get("data-mensagem", "").strip(), "a mensagem vem do servidor"
        assert aviso.texto == "" and aviso.buscar() == []
        # Não descreve o campo: sem id, não há como o `aria-describedby` do widget referenciá-lo.
        assert "id" not in aviso.attrs
    assert len({id(bloco) for bloco in blocos}) == len(blocos), "cada campo tem o seu bloco"
    scripts = _scripts_de(documento, "caps-lock.js")
    assert len(scripts) == 1 and "defer" in scripts[0].attrs


@pytest.mark.parametrize("com_recusa", [False, True], ids=["sem-erro", "recusado"])
def test_login_o_aviso_de_caps_lock_e_so_da_senha_e_nao_descreve_o_campo(
    client, usuario_ativo, com_recusa
):
    documento = _login_recusado(client, usuario_ativo) if com_recusa else _login_get(client)

    _confere_aviso_de_caps_lock(documento, [documento.unico("input", name="password")])
    # A Matrícula não tem aviso nem marca de Caps Lock no seu bloco.
    bloco_matricula = _bloco_do_campo(documento.unico("input", name="username"))
    assert "data-caps-lock" not in bloco_matricula.attrs
    assert bloco_matricula.buscar(data_caps_lock_aviso=True) == []


@POR_ESTADO
def test_senha_cada_campo_de_senha_tem_o_proprio_aviso_de_caps_lock(senha_get, senha_post_invalido):
    estado, sem_erro = senha_get
    _, com_erro, _, _ = senha_post_invalido
    esperados = 3 if estado == "voluntaria" else 2

    for documento in (sem_erro, com_erro):
        campos = _campos_de_senha(documento)
        assert len(campos) == esperados
        _confere_aviso_de_caps_lock(documento, campos)


@POR_ESTADO
def test_senha_tem_o_campo_de_matricula_oculto_para_o_gerenciador_de_senhas(
    conta, senha_get, senha_post_invalido
):
    usuario, _ = conta
    _, sem_erro = senha_get
    _, com_erro, _, _ = senha_post_invalido

    for documento in (sem_erro, com_erro):
        # Único campo de matrícula da tela, no formulário dos campos de senha e antes deles.
        campo = documento.unico("input", autocomplete="username")
        formulario = documento.unico("main").unico("form")
        ordem = list(formulario.descendentes())
        assert campo in ordem
        senhas = formulario.buscar("input", type="password")
        assert senhas and ordem.index(campo) < ordem.index(senhas[0])
        assert "hidden" in campo.attrs and "readonly" in campo.attrs
        # Nunca é enviado: sem `name`, o POST do formulário não depende dele.
        assert "name" not in campo.attrs
        assert campo.get("value") == usuario.get_username() == usuario.matricula


@POR_ESTADO
def test_senha_tem_os_ganchos_da_confirmacao_no_navegador_com_a_mensagem_do_servidor(client, conta):
    usuario, _ = conta
    client.force_login(usuario)

    resposta = client.get(rota("definir_senha"))

    documento = analisar(resposta.content)
    formulario = documento.unico("main").unico("form", data_confirmacao_senha=True)
    # A mensagem do cliente é a do servidor, lida do formulário em uso (não fixada no teste).
    mensagem = str(resposta.context["form"].error_messages["password_mismatch"])
    assert mensagem
    assert formulario.get("data-mensagem-divergencia") == mensagem
    # O script lê os dois campos pelo nome dentro do formulário que leva o gancho.
    assert formulario.unico("input", name=CAMPOS_SENHA["nova"])
    assert formulario.unico("input", name=CAMPOS_SENHA["confirmacao"])
    scripts = _scripts_de(documento, "confirmacao-senha.js")
    assert len(scripts) == 1 and "defer" in scripts[0].attrs


@POR_ESTADO
def test_senha_divergente_o_erro_do_servidor_e_a_mensagem_do_cliente_tem_o_mesmo_texto(
    client, conta
):
    usuario, estado = conta
    client.force_login(usuario)
    dados = {
        CAMPOS_SENHA["nova"]: SENHA_NOVA_VALIDA,
        CAMPOS_SENHA["confirmacao"]: SENHA_NOVA_VALIDA + "-divergente",
    }
    if estado == "voluntaria":
        dados[CAMPOS_SENHA["atual"]] = SENHA_TESTE

    resposta = client.post(rota("definir_senha"), dados)

    documento = analisar(resposta.content)
    formulario = documento.unico("main").unico("form", data_confirmacao_senha=True)
    mensagem = str(resposta.context["form"].error_messages["password_mismatch"])
    assert formulario.get("data-mensagem-divergencia") == mensagem
    # Sem o script, a divergência volta como erro da Confirmação, com o texto que o cliente usa.
    assert documento.unico(id="id_new_password2_error").texto == mensagem
    assert len(_scripts_de(documento, "confirmacao-senha.js")) == 1
