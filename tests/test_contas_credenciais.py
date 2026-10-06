"""Credenciais da organização — parte da US1 (T018): senha provisória, vencimento, definição
obrigatória no primeiro acesso e restrição de acesso enquanto a credencial é provisória.

Fontes: `contracts/credenciais.md`, research R8 a R12, FR-031 a FR-039, FR-016a/FR-003/FR-010/
FR-011 da 002, `INV-AUTH-001`. A redefinição pelo administrador e a troca voluntária da própria
senha (US6 — T046) são as seções finais.

Contratos de nome fixados pela US6 (ajustar AQUI se a implementação divergir):

- `contas.organizacao.redefinir_senha(autor, usuario_id, *, chave_confirmacao) -> str` (a senha
  provisória, em claro, só no retorno); evento `SENHA_PROVISORIA_GERADA` com `usuario`, `autor`, a
  `chave_confirmacao` e `dados["motivo"] == "redefinicao"`; a mesma chave levanta
  `OperacaoJaExecutada`; chave ausente, conta técnica e usuário inexistente levantam
  `OperacaoRecusada`;
- `contas.credenciais.trocar_propria_senha(request, usuario, atual, nova) -> User`, mesma forma de
  `definir_propria_senha`: sob a operação de organização, exige a senha atual correta e a
  política de R12, grava o hash, mantém a sessão em uso (`update_session_auth_hash`) e registra
  `SENHA_DEFINIDA` com `dados["motivo"] == "troca_voluntaria"` e o próprio usuário como autor;
  recusa levanta `OperacaoRecusada` sem alterar nada;
- `/senha/` com credencial definitiva: campos `old_password`, `new_password1`, `new_password2`.

O que este arquivo protege, em ordem de consequência:

- quem autentica com senha provisória não alcança NENHUMA outra superfície do WMS (nem as de
  catálogo, fornecedores, estoque, organização ou Admin) além de `/senha/` e do logout, nem por
  GET nem por POST, com HTMX recebendo `HX-Redirect` (FR-032, SC-005). Os testes usam uma conta
  com TODOS os papéis: sem a restrição, cada rota responderia 200;
- a provisória vence em 7 dias e o vencimento é indistinguível, para quem tenta entrar, de uma
  senha errada (FR-035, FR-003 da 002); sessão aberta que vence perde o acesso;
- a definição recusa a própria provisória e senhas fora da política, sem alterar nada quando
  recusa; quando aceita, limpa a marca de provisória, mantém só a sessão em uso, grava
  `SENHA_DEFINIDA` sem senha e devolve o usuário ao destino pedido antes do login (FR-034);
- nenhuma senha, provisória ou definida, aparece em log, sessão ou evento (FR-031).

O vencimento é simulado recuando `senha_provisoria_em` no banco (`envelhecer_provisoria`), sem
`sleep` e sem depender de como a implementação importa `timezone.now`.

TDD: escrito antes de `WMSModelBackend` (T021), `CredencialProvisoriaMiddleware` (T022) e da
rota `/senha/` (T023) existirem. Os testes de `gerar_senha_provisoria` já passam (T011).
"""

import logging
import uuid
from datetime import timedelta
from urllib.parse import urlsplit

import pytest
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone

from contas import credenciais
from contas import organizacao as org
from contas.credenciais import VALIDADE_SENHA_PROVISORIA, gerar_senha_provisoria
from contas.models import EventoOrganizacional, Papel, TipoEvento, User
from tests.contas_helpers import (
    CAMPOS_SENHA,
    SENHA_NOVA_VALIDA,
    SENHA_TESTE,
    dados_do_cadastro,
    envelhecer_provisoria,
    fixar_senha_gerada,
    foto_organizacao,
    hrefs,
    membro,
    membro_provisorio,
    mensagens,
    operacao,
    recusa_de,
    rota,
)

pytestmark = pytest.mark.django_db

MARCADOR_SESSAO = "_retorno_pos_login_destino"
MENSAGEM_LOGIN_RECUSADO = "Matrícula ou senha inválidas. Confira os dados e tente novamente."

LETRAS = set("ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
DIGITOS = set("23456789")
TODOS_OS_PAPEIS_DE_NEGOCIO = {
    Papel.ADMINISTRADOR_SISTEMA,
    Papel.CHEFE_SETOR,
    Papel.CHEFE_ALMOXARIFADO,
    Papel.FUNCIONARIO_ALMOXARIFADO,
}


def _login(client, matricula, senha, destino=None):
    url = rota("login") if destino is None else f"{rota('login')}?next={destino}"
    return client.post(url, {"username": matricula, "password": senha})


def _erro_de_login(resposta):
    erros = resposta.context["form"].non_field_errors()
    assert erros, "esperava erro geral de login"
    return str(erros[0])


def _definir(client, nova=SENHA_NOVA_VALIDA, confirmacao=None):
    return client.post(
        rota("definir_senha"),
        {
            CAMPOS_SENHA["nova"]: nova,
            CAMPOS_SENHA["confirmacao"]: nova if confirmacao is None else confirmacao,
        },
    )


def _caminho(resposta):
    assert resposta.status_code == 302, f"esperava redirect, veio {resposta.status_code}"
    return urlsplit(resposta.url).path


def _eventos_de_senha_definida(usuario):
    return EventoOrganizacional.objects.filter(usuario=usuario, tipo=TipoEvento.SENHA_DEFINIDA)


@pytest.fixture
def provisorio(setor):
    """Conta com credencial provisória e TODOS os papéis de negócio relevantes: sem a
    restrição do middleware, qualquer rota existente responderia 200."""
    usuario, senha = membro_provisorio(setor, "prov-todos", TODOS_OS_PAPEIS_DE_NEGOCIO)
    usuario.senha_provisoria_clara = senha
    return usuario


@pytest.fixture
def comum(setor):
    """Conta com credencial provisória e só `ROLE-REQUESTER`."""
    usuario, senha = membro_provisorio(setor, "prov-comum")
    usuario.senha_provisoria_clara = senha
    return usuario


# ---------------------------------------------------------------------------
# Geração (R8, R12)
# ---------------------------------------------------------------------------


def test_senha_gerada_tem_12_caracteres_do_alfabeto_sem_ambiguos_com_letra_e_digito():
    for _ in range(500):
        senha = gerar_senha_provisoria()

        assert len(senha) == 12
        assert set(senha) <= LETRAS | DIGITOS, f"caractere fora do alfabeto em {senha!r}"
        assert not set(senha) & set("0O1lI")
        assert set(senha) & LETRAS and set(senha) & DIGITOS


def test_senha_gerada_satisfaz_os_validadores_de_senha_do_projeto():
    usuario = User(matricula="123456", nome="Fulano de Tal")
    for _ in range(300):
        validate_password(gerar_senha_provisoria(), usuario)  # levanta ValidationError se não


def test_senhas_geradas_nao_se_repetem():
    assert len({gerar_senha_provisoria() for _ in range(200)}) == 200


def test_provisionamento_sem_senha_gera_provisoria_com_a_marca_de_provisoria(setor):
    usuario, senha = membro_provisorio(setor, "prov-marca")

    usuario.refresh_from_db()
    assert usuario.check_password(senha)
    assert usuario.senha_provisoria_em is not None


# ---------------------------------------------------------------------------
# Política de senha (R12, FR-038): os validadores do projeto reconhecem matrícula e nome
# ---------------------------------------------------------------------------

POLITICA = [
    pytest.param("Ab1-xyz", "prov-comum", "Pessoa prov-comum", id="menos-de-8-caracteres"),
    pytest.param("qwertyuiop", "prov-comum", "Pessoa prov-comum", id="senha-comum"),
    pytest.param("48291736052", "prov-comum", "Pessoa prov-comum", id="so-numeros"),
    pytest.param("prov-comum1", "prov-comum", "Pessoa prov-comum", id="parecida-com-matricula"),
    pytest.param(
        "fernandaalbuquerque", "12-ABC", "Fernanda Albuquerque Lima", id="parecida-com-nome"
    ),
]


@pytest.mark.parametrize("senha, matricula, nome", POLITICA)
def test_politica_de_senha_recusa_curta_comum_numerica_e_parecida_com_os_dados(
    senha, matricula, nome
):
    with pytest.raises(ValidationError):
        validate_password(senha, User(matricula=matricula, nome=nome))


def test_politica_de_senha_aceita_a_senha_valida_dos_testes():
    validate_password(SENHA_NOVA_VALIDA, User(matricula="prov-comum", nome="Pessoa prov-comum"))


# ---------------------------------------------------------------------------
# Contrato de configuração: backend e posição do middleware (R9, R10)
# ---------------------------------------------------------------------------


def test_backend_de_autenticacao_do_projeto_e_o_wms_model_backend():
    assert settings.AUTHENTICATION_BACKENDS[0] == "contas.backends.WMSModelBackend"


def test_middleware_fica_logo_depois_da_autenticacao_e_antes_do_retorno_pos_login():
    """A ordem importa: ele precisa agir ANTES do `RetornoPosLoginMiddleware`, senão o marcador
    de destino seria consumido por uma requisição que a restrição deveria ter barrado."""
    middlewares = list(settings.MIDDLEWARE)
    autenticacao = middlewares.index("django.contrib.auth.middleware.AuthenticationMiddleware")
    credencial = middlewares.index("contas.middleware.CredencialProvisoriaMiddleware")
    retorno = middlewares.index("contas.middleware.RetornoPosLoginMiddleware")

    assert autenticacao < credencial < retorno


def test_backend_recusa_provisoria_vencida_e_aceita_vigente_definitiva_e_recusa_inativa(setor):
    from contas.backends import WMSModelBackend

    backend = WMSModelBackend()
    vigente, _ = membro_provisorio(setor, "bk-vigente")
    vencida, _ = membro_provisorio(setor, "bk-vencida")
    definitiva = membro(setor, "bk-definitiva")
    inativa = membro(setor, "bk-inativa", is_active=False)
    envelhecer_provisoria(vencida, VALIDADE_SENHA_PROVISORIA + timedelta(minutes=1))
    envelhecer_provisoria(vigente, VALIDADE_SENHA_PROVISORIA - timedelta(hours=1))
    for usuario in (vigente, vencida):
        usuario.refresh_from_db()

    assert backend.user_can_authenticate(vigente) is True
    assert backend.user_can_authenticate(definitiva) is True
    assert backend.user_can_authenticate(vencida) is False
    assert backend.user_can_authenticate(inativa) is False


# ---------------------------------------------------------------------------
# Login com provisória e vencimento (FR-035, FR-003 da 002)
# ---------------------------------------------------------------------------


def test_login_com_provisoria_valida_autentica(client, comum):
    resposta = _login(client, comum.matricula, comum.senha_provisoria_clara)

    assert resposta.status_code == 302
    assert str(client.session["_auth_user_id"]) == str(comum.pk)


def test_login_com_provisoria_a_um_minuto_de_vencer_ainda_autentica(client, comum):
    envelhecer_provisoria(comum, VALIDADE_SENHA_PROVISORIA - timedelta(minutes=1))

    resposta = _login(client, comum.matricula, comum.senha_provisoria_clara)

    assert resposta.status_code == 302
    assert "_auth_user_id" in client.session


def test_login_com_provisoria_vencida_e_recusado_com_a_mesma_mensagem_de_senha_errada(
    client, comum
):
    envelhecer_provisoria(comum, VALIDADE_SENHA_PROVISORIA + timedelta(minutes=1))

    vencida = _login(client, comum.matricula, comum.senha_provisoria_clara)
    errada = _login(client, comum.matricula, "senha-completamente-errada")

    assert vencida.status_code == 200
    assert "_auth_user_id" not in client.session
    assert _erro_de_login(vencida) == _erro_de_login(errada) == MENSAGEM_LOGIN_RECUSADO


def test_sessao_aberta_com_provisoria_que_vence_perde_o_acesso_na_interacao_seguinte(
    client, comum
):
    _login(client, comum.matricula, comum.senha_provisoria_clara)
    assert client.get(rota("definir_senha")).status_code == 200  # antes de vencer, define-se

    envelhecer_provisoria(comum, VALIDADE_SENHA_PROVISORIA + timedelta(minutes=1))

    seguinte = client.get(rota("definir_senha"))
    assert _caminho(seguinte) == reverse("login")
    # a sessão não serve mais para nada: nova tentativa também vai ao login
    assert _caminho(client.get(reverse("home"))) == reverse("login")


def test_provisoria_vencida_nao_pode_ser_usada_para_definir_a_senha(client, comum):
    _login(client, comum.matricula, comum.senha_provisoria_clara)
    envelhecer_provisoria(comum, VALIDADE_SENHA_PROVISORIA + timedelta(minutes=1))
    antes = User.objects.get(pk=comum.pk)

    _definir(client)

    depois = User.objects.get(pk=comum.pk)
    assert depois.password == antes.password
    assert depois.senha_provisoria_em == antes.senha_provisoria_em
    assert not _eventos_de_senha_definida(comum).exists()


# ---------------------------------------------------------------------------
# Restrição enquanto a credencial é provisória (FR-032, SC-005, R10)
# ---------------------------------------------------------------------------

ROTAS_EXISTENTES = [
    pytest.param(("home",), id="home"),
    pytest.param(("catalogo:consulta",), id="catalogo-consulta"),
    pytest.param(("catalogo:importacao_envio",), id="catalogo-importacao"),
    pytest.param(("catalogo:historico",), id="catalogo-historico"),
    pytest.param(("catalogo:execucao_detalhe", 1), id="catalogo-execucao-detalhe"),
    pytest.param(("fornecedores:consulta",), id="fornecedores-consulta"),
    pytest.param(("fornecedores:importacao_envio",), id="fornecedores-importacao"),
    pytest.param(("fornecedores:historico",), id="fornecedores-historico"),
    pytest.param(("estoque:entradas",), id="estoque-entradas"),
    pytest.param(("estoque:entrada_nova",), id="estoque-entrada-nova"),
    pytest.param(("estoque:entrada_detalhe", 1), id="estoque-entrada-detalhe"),
    pytest.param(("usuarios",), id="organizacao-usuarios"),
    pytest.param(("usuario_novo",), id="organizacao-usuario-novo"),
    pytest.param(("usuario", 1), id="organizacao-usuario"),
    pytest.param(("setores",), id="organizacao-setores"),
]


@pytest.mark.parametrize("rota_args", ROTAS_EXISTENTES)
def test_provisoria_redireciona_toda_rota_a_definicao_de_senha(client, provisorio, rota_args):
    client.force_login(provisorio)

    resposta = client.get(rota(*rota_args))

    assert _caminho(resposta) == rota("definir_senha")


@pytest.mark.parametrize(
    "rota_args",
    [
        pytest.param(("estoque:entrada_nova",), id="estoque-entrada-nova"),
        pytest.param(("catalogo:importacao_previa",), id="catalogo-importacao-previa"),
        pytest.param(("fornecedores:importacao_confirmar",), id="fornecedores-confirmar"),
        pytest.param(("usuario_novo",), id="organizacao-usuario-novo"),
    ],
)
def test_provisoria_redireciona_tambem_o_post_sem_executar_nada(client, provisorio, rota_args):
    client.force_login(provisorio)
    usuarios_antes = User.objects.count()

    resposta = client.post(rota(*rota_args), dados_do_cadastro(provisorio.setor))

    assert _caminho(resposta) == rota("definir_senha")
    assert User.objects.count() == usuarios_antes


def test_provisoria_nao_alcanca_o_admin(client, provisorio):
    client.force_login(provisorio)

    resposta = client.get("/admin/")

    assert _caminho(resposta) == rota("definir_senha")


def test_requisicao_htmx_de_provisoria_recebe_hx_redirect_para_a_definicao(client, provisorio):
    client.force_login(provisorio)

    resposta = client.get(rota("catalogo:consulta"), HTTP_HX_REQUEST="true")

    assert resposta.status_code < 400
    assert urlsplit(resposta["HX-Redirect"]).path == rota("definir_senha")


def test_definicao_de_senha_e_o_logout_continuam_acessiveis_com_provisoria(client, provisorio):
    client.force_login(provisorio)

    assert client.get(rota("definir_senha")).status_code == 200

    saida = client.post(reverse("logout"))
    assert _caminho(saida) == reverse("login")
    # depois do logout o usuário é anônimo: vai ao login, não à definição de senha
    assert _caminho(client.get(reverse("home"))) == reverse("login")


def test_arquivos_estaticos_nao_sao_redirecionados_a_definicao_de_senha(client, provisorio):
    client.force_login(provisorio)

    resposta = client.get("/static/css/tokens.css")

    redirecionada = resposta.status_code == 302 and (
        urlsplit(resposta.url).path == rota("definir_senha")
    )
    assert not redirecionada


def test_pagina_de_definicao_obrigatoria_nao_mostra_navegacao_so_o_logout(client, provisorio):
    client.force_login(provisorio)

    resposta = client.get(rota("definir_senha"))

    conteudo = resposta.content.decode()
    links = hrefs(conteudo)
    for prefixo in ("/catalogo/", "/fornecedores/", "/estoque/", "/organizacao/"):
        assert not any(link.startswith(prefixo) for link in links), f"navegação para {prefixo}"
    assert reverse("home") not in links
    assert reverse("logout") in conteudo  # o logout continua disponível


def test_middleware_nao_age_sobre_usuario_com_credencial_definitiva(client, requisitante):
    client.force_login(requisitante)

    assert client.get(rota("catalogo:consulta")).status_code == 200


def test_middleware_nao_age_sobre_anonimo_nem_sobre_inativo(client, comum):
    anonimo = client.get(rota("catalogo:consulta"))
    assert _caminho(anonimo) == reverse("login")

    client.force_login(comum)
    with operacao():
        User.objects.filter(pk=comum.pk).update(is_active=False)

    inativo = client.get(rota("catalogo:consulta"))
    assert _caminho(inativo) == reverse("login")


def test_definir_senha_exige_autenticacao(client):
    assert _caminho(client.get(rota("definir_senha"))) == reverse("login")
    assert _caminho(_definir(client)) == reverse("login")


def test_definir_senha_de_conta_inativa_e_tratado_como_anonimo(client, comum):
    client.force_login(comum)
    with operacao():
        User.objects.filter(pk=comum.pk).update(is_active=False)

    assert _caminho(client.get(rota("definir_senha"))) == reverse("login")


# ---------------------------------------------------------------------------
# Definição obrigatória (FR-034, FR-036, FR-038, R11, R12)
# ---------------------------------------------------------------------------

SENHAS_FORA_DA_POLITICA = [
    pytest.param("Ab1-xyz", id="menos-de-8-caracteres"),
    pytest.param("qwertyuiop", id="senha-comum"),
    pytest.param("48291736052", id="so-numeros"),
    pytest.param("prov-comum1", id="parecida-com-a-matricula"),
]


@pytest.mark.parametrize("nova", SENHAS_FORA_DA_POLITICA)
def test_definicao_recusa_senha_fora_da_politica_sem_alterar_nada(client, comum, nova):
    _login(client, comum.matricula, comum.senha_provisoria_clara)
    antes = User.objects.get(pk=comum.pk)

    resposta = _definir(client, nova)

    assert resposta.status_code == 200
    depois = User.objects.get(pk=comum.pk)
    assert depois.password == antes.password
    assert depois.senha_provisoria_em == antes.senha_provisoria_em is not None
    assert not _eventos_de_senha_definida(comum).exists()
    # continua restrito: nada além de /senha/
    assert _caminho(client.get(rota("catalogo:consulta"))) == rota("definir_senha")


def test_definicao_recusa_senha_parecida_com_o_nome(client, setor):
    usuario, senha = org.provisionar_usuario("12-ABC", "Fernanda Albuquerque Lima", setor, set())
    _login(client, usuario.matricula, senha)

    resposta = _definir(client, "fernandaalbuquerque")

    assert resposta.status_code == 200
    assert not _eventos_de_senha_definida(usuario).exists()
    assert User.objects.get(pk=usuario.pk).senha_provisoria_em is not None


def test_definicao_recusa_a_propria_senha_provisoria(client, comum):
    _login(client, comum.matricula, comum.senha_provisoria_clara)

    resposta = _definir(client, comum.senha_provisoria_clara)

    assert resposta.status_code == 200
    depois = User.objects.get(pk=comum.pk)
    assert depois.senha_provisoria_em is not None
    assert depois.check_password(comum.senha_provisoria_clara)
    assert not _eventos_de_senha_definida(comum).exists()


def test_definicao_recusa_confirmacao_diferente(client, comum):
    _login(client, comum.matricula, comum.senha_provisoria_clara)

    resposta = _definir(client, SENHA_NOVA_VALIDA, confirmacao=SENHA_NOVA_VALIDA + "x")

    assert resposta.status_code == 200
    assert User.objects.get(pk=comum.pk).senha_provisoria_em is not None
    assert not _eventos_de_senha_definida(comum).exists()


def test_definicao_valida_avisa_que_a_senha_foi_definida_e_a_home_mostra_o_aviso(client, comum):
    _login(client, comum.matricula, comum.senha_provisoria_clara)

    resposta = _definir(client)

    assert _caminho(resposta) == reverse("home")
    assert mensagens(resposta) == ["Senha definida. Use-a nos próximos acessos."]
    home = client.get(reverse("home"))
    assert "Senha definida. Use-a nos próximos acessos." in home.content.decode()


def test_definicao_recusada_nao_avisa_que_a_senha_foi_definida(client, comum):
    _login(client, comum.matricula, comum.senha_provisoria_clara)

    resposta = _definir(client, "qwertyuiop")

    assert resposta.status_code == 200
    assert "Senha definida. Use-a nos próximos acessos." not in mensagens(resposta)


def test_definicao_valida_troca_a_senha_e_limpa_a_marca_de_provisoria(client, comum):
    _login(client, comum.matricula, comum.senha_provisoria_clara)

    resposta = _definir(client)

    assert resposta.status_code == 302
    depois = User.objects.get(pk=comum.pk)
    assert depois.senha_provisoria_em is None
    assert depois.check_password(SENHA_NOVA_VALIDA)
    assert not depois.check_password(comum.senha_provisoria_clara)
    # restrição levantada: as rotas voltam a responder
    assert client.get(rota("catalogo:consulta")).status_code == 200


def test_definicao_valida_registra_evento_sem_senha_com_o_proprio_usuario_como_autor(client, comum):
    _login(client, comum.matricula, comum.senha_provisoria_clara)

    _definir(client)

    evento = _eventos_de_senha_definida(comum).get()
    assert evento.autor == comum
    assert evento.dados["motivo"] == "definicao_obrigatoria"
    texto = f"{evento.dados} {evento.justificativa}"
    assert SENHA_NOVA_VALIDA not in texto
    assert comum.senha_provisoria_clara not in texto


def test_definicao_mantem_a_sessao_em_uso_e_encerra_as_demais(comum):
    em_uso, outro_dispositivo = Client(), Client()
    _login(em_uso, comum.matricula, comum.senha_provisoria_clara)
    _login(outro_dispositivo, comum.matricula, comum.senha_provisoria_clara)

    _definir(em_uso)

    assert em_uso.get(rota("catalogo:consulta")).status_code == 200
    assert _caminho(outro_dispositivo.get(rota("definir_senha"))) == reverse("login")


def test_definicao_sem_destino_anterior_leva_a_home(client, comum):
    _login(client, comum.matricula, comum.senha_provisoria_clara)

    resposta = _definir(client)

    assert resposta.url == reverse("home")


def test_definicao_leva_ao_destino_pedido_antes_do_login_e_consome_o_marcador(client, comum):
    destino = reverse("catalogo:consulta")
    _login(client, comum.matricula, comum.senha_provisoria_clara, destino=destino)
    assert client.session.get(MARCADOR_SESSAO) == destino
    # tentar o destino com provisória só leva à definição — e não gasta o marcador
    assert _caminho(client.get(destino)) == rota("definir_senha")
    assert client.session.get(MARCADOR_SESSAO) == destino

    resposta = _definir(client)

    assert resposta.url == destino
    assert client.get(destino).status_code == 200
    assert MARCADOR_SESSAO not in client.session


def test_destino_proibido_depois_da_definicao_cai_na_home(client, comum):
    """FR-034 / FR-010 da 002: o marcador aponta a rota, mas quem decide é a autorização —
    sem `ROLE-WAREHOUSE-HEAD`, a importação do catálogo devolve à Home."""
    destino = reverse("catalogo:importacao_envio")
    _login(client, comum.matricula, comum.senha_provisoria_clara, destino=destino)

    resposta = _definir(client)

    assert resposta.url == destino
    assert _caminho(client.get(destino)) == reverse("home")


def test_nenhuma_senha_aparece_em_log_sessao_ou_evento_na_definicao(client, comum, caplog):
    caplog.set_level(logging.DEBUG)
    _login(client, comum.matricula, comum.senha_provisoria_clara)

    _definir(client)

    sessoes = " ".join(str(s.get_decoded()) + s.session_data for s in Session.objects.all())
    eventos = " ".join(
        f"{e.dados} {e.justificativa}" for e in EventoOrganizacional.objects.filter(usuario=comum)
    )
    for senha in (SENHA_NOVA_VALIDA, comum.senha_provisoria_clara):
        assert senha not in caplog.text
        assert senha not in sessoes
        assert senha not in eventos


def test_definicao_e_atomica_se_o_evento_falha_a_senha_nao_muda(comum, monkeypatch):
    cliente = Client(raise_request_exception=False)
    _login(cliente, comum.matricula, comum.senha_provisoria_clara)
    antes = User.objects.get(pk=comum.pk)

    def _falha(self, *args, **kwargs):
        raise RuntimeError("falha simulada ao gravar o evento")

    with monkeypatch.context() as patch:
        patch.setattr(EventoOrganizacional, "save", _falha)
        cliente.post(
            rota("definir_senha"),
            {
                CAMPOS_SENHA["nova"]: SENHA_NOVA_VALIDA,
                CAMPOS_SENHA["confirmacao"]: SENHA_NOVA_VALIDA,
            },
        )

    depois = User.objects.get(pk=comum.pk)
    assert depois.password == antes.password
    assert depois.senha_provisoria_em == antes.senha_provisoria_em is not None


# ---------------------------------------------------------------------------
# Ponta a ponta da US1 (spec, "Independent Test")
# ---------------------------------------------------------------------------


def test_fluxo_completo_cadastro_provisoria_definicao_e_acesso_normal(
    admin_sistema, setor, monkeypatch
):
    """Cadastrar, anotar a senha, autenticar com ela, ver só a definição de senha, definir e
    acessar normalmente — pelas rotas, como o administrador e o novo usuário fariam."""
    senha = fixar_senha_gerada(monkeypatch)
    administrador = Client()
    administrador.force_login(admin_sistema)

    cadastro = administrador.post(
        rota("usuario_novo"), dados_do_cadastro(setor, matricula="FLUXO-1")
    )
    assert cadastro.status_code == 200
    assert senha in cadastro.content.decode()

    novo = Client()
    assert _login(novo, "FLUXO-1", senha).status_code == 302
    assert _caminho(novo.get(rota("catalogo:consulta"))) == rota("definir_senha")
    assert novo.get(rota("definir_senha")).status_code == 200

    assert _definir(novo).status_code == 302
    assert novo.get(rota("catalogo:consulta")).status_code == 200

    novo.post(reverse("logout"))
    assert _login(Client(), "FLUXO-1", senha).status_code == 200  # a provisória já não vale
    assert _login(Client(), "FLUXO-1", SENHA_NOVA_VALIDA).status_code == 302


def test_a_provisoria_do_cadastro_pelo_administrador_nao_e_a_senha_em_texto_no_banco(
    admin_sistema, setor, monkeypatch
):
    senha = fixar_senha_gerada(monkeypatch)
    administrador = Client()
    administrador.force_login(admin_sistema)

    administrador.post(rota("usuario_novo"), dados_do_cadastro(setor, matricula="HASH-1"))

    usuario = User.objects.get(matricula="HASH-1")
    assert usuario.check_password(senha)
    assert senha not in usuario.password


# ===========================================================================
# US6 (T046) — redefinição pelo administrador (FR-031, FR-033, FR-035, R11)
# ===========================================================================


def _redefinir(autor, alvo, chave=None):
    return org.redefinir_senha(
        autor, alvo.pk, chave_confirmacao=chave if chave is not None else uuid.uuid4()
    )


def _eventos_de_redefinicao(usuario):
    return EventoOrganizacional.objects.filter(
        usuario=usuario, tipo=TipoEvento.SENHA_PROVISORIA_GERADA, dados__motivo="redefinicao"
    )


@pytest.fixture
def alvo(setor):
    """Conta de negócio com senha DEFINITIVA conhecida (`SENHA_TESTE`)."""
    return membro(setor, "red-alvo")


def test_redefinir_gera_uma_nova_provisoria_e_a_conta_volta_a_exigir_a_definicao(
    admin_sistema, alvo
):
    senha = _redefinir(admin_sistema, alvo)

    alvo.refresh_from_db()
    assert alvo.check_password(senha) and not alvo.check_password(SENHA_TESTE)
    assert alvo.senha_provisoria_em is not None
    assert abs(timezone.now() - alvo.senha_provisoria_em) < timedelta(minutes=1)
    assert len(senha) == 12 and set(senha) <= LETRAS | DIGITOS
    assert senha not in alvo.password, "só o hash fica no banco"
    cliente = Client()
    assert _login(cliente, alvo.matricula, senha).status_code == 302
    assert _caminho(cliente.get(rota("catalogo:consulta"))) == rota("definir_senha")


def test_redefinir_substitui_uma_provisoria_ja_emitida(admin_sistema, setor):
    usuario, antiga = membro_provisorio(setor, "red-provisorio")

    nova = _redefinir(admin_sistema, usuario)

    assert nova != antiga
    usuario.refresh_from_db()
    assert usuario.check_password(nova) and not usuario.check_password(antiga)


def test_redefinir_recupera_a_conta_cuja_provisoria_venceu(admin_sistema, setor):
    """Cenário 5 da US6 / edge case: o único caminho de volta é nova redefinição."""
    usuario, antiga = membro_provisorio(setor, "red-vencida")
    envelhecer_provisoria(usuario, VALIDADE_SENHA_PROVISORIA + timedelta(days=1))
    assert _login(Client(), usuario.matricula, antiga).status_code == 200  # recusada

    nova = _redefinir(admin_sistema, usuario)

    assert _login(Client(), usuario.matricula, nova).status_code == 302


def test_o_prazo_de_sete_dias_conta_da_redefinicao_e_nao_do_cadastro(admin_sistema, setor):
    usuario, _ = membro_provisorio(setor, "red-prazo")
    envelhecer_provisoria(usuario, timedelta(days=5))
    senha = _redefinir(admin_sistema, usuario)

    envelhecer_provisoria(usuario, timedelta(days=3))  # 8 dias desde o cadastro, 3 da redefinição
    assert _login(Client(), usuario.matricula, senha).status_code == 302

    envelhecer_provisoria(usuario, VALIDADE_SENHA_PROVISORIA + timedelta(minutes=1))
    vencida = _login(Client(), usuario.matricula, senha)
    errada = _login(Client(), usuario.matricula, "senha-completamente-errada")
    assert vencida.status_code == 200
    assert _erro_de_login(vencida) == _erro_de_login(errada) == MENSAGEM_LOGIN_RECUSADO


def test_redefinir_grava_um_evento_com_a_chave_o_autor_e_nenhuma_senha(admin_sistema, alvo):
    chave = uuid.uuid4()

    senha = _redefinir(admin_sistema, alvo, chave)

    evento = _eventos_de_redefinicao(alvo).get()
    assert evento.autor == admin_sistema and evento.usuario == alvo
    assert evento.chave_confirmacao == chave
    texto = f"{evento.dados} {evento.justificativa}"
    assert senha not in texto and SENHA_TESTE not in texto


def test_redefinir_encerra_todas_as_sessoes_da_conta_inclusive_a_do_administrador_que_a_redefine(
    admin_sistema, alvo
):
    """FR-033, R11: o hash muda e nenhuma sessão aberta sobrevive — vão ao LOGIN, não à
    definição."""
    sessoes = [Client(), Client()]
    for sessao in sessoes:
        sessao.force_login(alvo)
        assert sessao.get(reverse("home")).status_code == 200
    do_administrador = Client()
    do_administrador.force_login(admin_sistema)

    _redefinir(admin_sistema, alvo)

    for sessao in sessoes:
        assert _caminho(sessao.get(reverse("home"))) == reverse("login")
    assert do_administrador.get(reverse("home")).status_code == 200, "só a conta alvo é afetada"


def test_o_administrador_que_redefine_a_propria_senha_perde_a_sessao_e_define_a_nova(
    admin_sistema,
):
    """Edge case: é permitido (D-15); ele volta a autenticar com a provisória e define a própria."""
    sessao = Client()
    sessao.force_login(admin_sistema)

    senha = _redefinir(admin_sistema, admin_sistema)

    assert _caminho(sessao.get(reverse("home"))) == reverse("login")
    nova_sessao = Client()
    assert _login(nova_sessao, admin_sistema.matricula, senha).status_code == 302
    assert _caminho(nova_sessao.get(reverse("home"))) == rota("definir_senha")
    assert _definir(nova_sessao).status_code == 302
    assert nova_sessao.get(reverse("home")).status_code == 200


def test_a_mesma_chave_nao_gera_outra_senha(admin_sistema, alvo):
    chave = uuid.uuid4()
    primeira = _redefinir(admin_sistema, alvo, chave)
    hash_depois_da_primeira = User.objects.get(pk=alvo.pk).password

    with pytest.raises(org.OperacaoJaExecutada) as excecao:
        _redefinir(admin_sistema, alvo, chave)

    assert excecao.value.evento == _eventos_de_redefinicao(alvo).get()
    depois = User.objects.get(pk=alvo.pk)
    assert depois.password == hash_depois_da_primeira and depois.check_password(primeira)


def test_chaves_diferentes_sao_redefinicoes_diferentes(admin_sistema, alvo):
    primeira = _redefinir(admin_sistema, alvo)
    segunda = _redefinir(admin_sistema, alvo)

    assert primeira != segunda
    assert User.objects.get(pk=alvo.pk).check_password(segunda)
    assert _eventos_de_redefinicao(alvo).count() == 2


def test_redefinir_sem_chave_e_recusado_sem_gerar_senha(admin_sistema, alvo):
    antes = foto_organizacao()

    recusa_de(lambda: org.redefinir_senha(admin_sistema, alvo.pk, chave_confirmacao=None))

    assert foto_organizacao() == antes


def test_redefinir_conta_tecnica_ou_usuario_inexistente_e_recusado(
    admin_sistema, superusuario_tecnico
):
    antes = foto_organizacao()

    recusa_de(lambda: _redefinir(admin_sistema, superusuario_tecnico))
    recusa_de(
        lambda: org.redefinir_senha(admin_sistema, 987_654_321, chave_confirmacao=uuid.uuid4())
    )

    assert foto_organizacao() == antes
    assert User.objects.get(pk=superusuario_tecnico.pk).check_password(SENHA_TESTE)


def test_redefinir_nao_mexe_em_situacao_papeis_nem_setor(admin_sistema, setor):
    usuario = membro(setor, "red-intacto", {Papel.AUDITOR})
    antes = foto_organizacao()

    _redefinir(admin_sistema, usuario)

    depois = foto_organizacao()
    for chave in ("setores", "papeis"):
        assert depois[chave] == antes[chave]
    recarregado = User.objects.get(pk=usuario.pk)
    assert recarregado.is_active and recarregado.setor == setor
    assert recarregado.nome == usuario.nome and recarregado.matricula == usuario.matricula


def test_redefinicao_e_atomica_se_o_evento_falha_a_senha_nao_muda(
    admin_sistema, alvo, monkeypatch
):
    antes = User.objects.get(pk=alvo.pk)

    def _falha(self, *args, **kwargs):
        raise RuntimeError("falha simulada ao gravar o evento")

    with monkeypatch.context() as patch:
        patch.setattr(EventoOrganizacional, "save", _falha)
        with pytest.raises(RuntimeError):
            _redefinir(admin_sistema, alvo)

    depois = User.objects.get(pk=alvo.pk)
    assert depois.password == antes.password
    assert depois.senha_provisoria_em == antes.senha_provisoria_em is None


def test_a_senha_redefinida_nao_aparece_em_log_sessao_nem_evento(
    admin_sistema, alvo, monkeypatch, caplog
):
    caplog.set_level(logging.DEBUG)
    senha = fixar_senha_gerada(monkeypatch)
    sessao = Client()
    sessao.force_login(admin_sistema)

    assert _redefinir(admin_sistema, alvo) == senha

    sessoes = " ".join(str(s.get_decoded()) + s.session_data for s in Session.objects.all())
    eventos = " ".join(f"{e.dados} {e.justificativa}" for e in EventoOrganizacional.objects.all())
    assert senha not in caplog.text and senha not in sessoes and senha not in eventos


# ===========================================================================
# US6 (T046) — troca voluntária da própria senha (FR-037, FR-038, R11, R12)
# ===========================================================================


def _trocar(client, atual, nova=SENHA_NOVA_VALIDA, confirmacao=None):
    return client.post(
        rota("definir_senha"),
        {
            CAMPOS_SENHA["atual"]: atual,
            CAMPOS_SENHA["nova"]: nova,
            CAMPOS_SENHA["confirmacao"]: nova if confirmacao is None else confirmacao,
        },
    )


def _trocas(usuario):
    return EventoOrganizacional.objects.filter(
        usuario=usuario, tipo=TipoEvento.SENHA_DEFINIDA, dados__motivo="troca_voluntaria"
    )


@pytest.fixture
def definitivo(setor):
    """Conta com senha DEFINITIVA (`SENHA_TESTE`), já autenticada num cliente."""
    usuario = membro(setor, "troca-1")
    sessao = Client()
    assert _login(sessao, usuario.matricula, SENHA_TESTE).status_code == 302
    usuario.sessao = sessao
    return usuario


def _requisicao_de(usuario):
    from django.contrib.sessions.backends.db import SessionStore

    requisicao = RequestFactory().post(rota("definir_senha"))
    requisicao.session = SessionStore()
    requisicao.user = usuario
    return requisicao


def test_pagina_de_troca_pede_a_senha_atual_a_nova_e_a_confirmacao(definitivo):
    resposta = definitivo.sessao.get(rota("definir_senha"))

    assert resposta.status_code == 200, "a conta definitiva não é mais devolvida à Home"
    conteudo = resposta.content.decode()
    for campo in CAMPOS_SENHA.values():
        assert f'name="{campo}"' in conteudo


def test_troca_com_a_senha_atual_certa_vale_e_registra_o_evento_sem_senha(definitivo):
    resposta = _trocar(definitivo.sessao, SENHA_TESTE)

    assert resposta.status_code == 302
    depois = User.objects.get(pk=definitivo.pk)
    assert depois.check_password(SENHA_NOVA_VALIDA) and not depois.check_password(SENHA_TESTE)
    assert depois.senha_provisoria_em is None, "continua definitiva"
    evento = _trocas(definitivo).get()
    assert evento.autor == definitivo
    texto = f"{evento.dados} {evento.justificativa}"
    assert SENHA_NOVA_VALIDA not in texto and SENHA_TESTE not in texto
    assert _login(Client(), definitivo.matricula, SENHA_NOVA_VALIDA).status_code == 302
    assert _login(Client(), definitivo.matricula, SENHA_TESTE).status_code == 200


def test_troca_mantem_a_sessao_em_uso_e_encerra_as_demais(setor):
    usuario = membro(setor, "troca-sessoes")
    em_uso, outro_dispositivo = Client(), Client()
    _login(em_uso, usuario.matricula, SENHA_TESTE)
    _login(outro_dispositivo, usuario.matricula, SENHA_TESTE)

    _trocar(em_uso, SENHA_TESTE)

    assert em_uso.get(rota("catalogo:consulta")).status_code == 200
    assert _caminho(outro_dispositivo.get(reverse("home"))) == reverse("login")


def test_troca_com_a_senha_atual_errada_nao_muda_nada(setor):
    usuario = membro(setor, "troca-errada")
    em_uso, outro_dispositivo = Client(), Client()
    _login(em_uso, usuario.matricula, SENHA_TESTE)
    _login(outro_dispositivo, usuario.matricula, SENHA_TESTE)
    antes = User.objects.get(pk=usuario.pk)

    resposta = _trocar(em_uso, "senha-atual-errada")

    assert resposta.status_code == 200
    depois = User.objects.get(pk=usuario.pk)
    assert depois.password == antes.password and depois.check_password(SENHA_TESTE)
    assert not _trocas(usuario).exists()
    assert outro_dispositivo.get(reverse("home")).status_code == 200, "ninguém foi deslogado"
    assert em_uso.get(reverse("home")).status_code == 200


def test_troca_sem_informar_a_senha_atual_nao_muda_nada(definitivo):
    resposta = definitivo.sessao.post(
        rota("definir_senha"),
        {
            CAMPOS_SENHA["nova"]: SENHA_NOVA_VALIDA,
            CAMPOS_SENHA["confirmacao"]: SENHA_NOVA_VALIDA,
        },
    )

    assert resposta.status_code == 200
    assert User.objects.get(pk=definitivo.pk).check_password(SENHA_TESTE)
    assert not _trocas(definitivo).exists()


@pytest.mark.parametrize("nova", SENHAS_FORA_DA_POLITICA)
def test_troca_recusa_senha_fora_da_politica_sem_alterar_nada(setor, nova):
    usuario = membro(setor, "prov-comum")  # a política reconhece a matrícula (R12)
    cliente = Client()
    _login(cliente, usuario.matricula, SENHA_TESTE)

    resposta = _trocar(cliente, SENHA_TESTE, nova)

    assert resposta.status_code == 200
    assert User.objects.get(pk=usuario.pk).check_password(SENHA_TESTE)
    assert not _trocas(usuario).exists()


def test_troca_recusa_senha_parecida_com_o_nome(setor):
    usuario = org.provisionar_usuario(
        "12-ABC", "Fernanda Albuquerque Lima", setor, set(), senha=SENHA_TESTE
    )[0]
    cliente = Client()
    _login(cliente, usuario.matricula, SENHA_TESTE)

    resposta = _trocar(cliente, SENHA_TESTE, "fernandaalbuquerque")

    assert resposta.status_code == 200
    assert User.objects.get(pk=usuario.pk).check_password(SENHA_TESTE)


def test_troca_recusa_confirmacao_diferente(definitivo):
    resposta = _trocar(definitivo.sessao, SENHA_TESTE, SENHA_NOVA_VALIDA, SENHA_NOVA_VALIDA + "x")

    assert resposta.status_code == 200
    assert User.objects.get(pk=definitivo.pk).check_password(SENHA_TESTE)


def test_trocar_propria_senha_pela_operacao_grava_mantem_a_sessao_e_registra_o_evento(definitivo):
    requisicao = _requisicao_de(definitivo)

    credenciais.trocar_propria_senha(requisicao, definitivo, SENHA_TESTE, SENHA_NOVA_VALIDA)

    depois = User.objects.get(pk=definitivo.pk)
    assert depois.check_password(SENHA_NOVA_VALIDA)
    assert _trocas(definitivo).get().autor == definitivo
    assert requisicao.session.get("_auth_user_hash") == depois.get_session_auth_hash(), (
        "a sessão em uso passa a valer com o hash novo"
    )


def test_trocar_propria_senha_pela_operacao_recusa_atual_errada_e_politica(definitivo):
    antes = foto_organizacao()

    recusa_de(
        lambda: credenciais.trocar_propria_senha(
            _requisicao_de(definitivo), definitivo, "senha-atual-errada", SENHA_NOVA_VALIDA
        )
    )
    recusa_de(
        lambda: credenciais.trocar_propria_senha(
            _requisicao_de(definitivo), definitivo, SENHA_TESTE, "qwertyuiop"
        )
    )

    assert foto_organizacao() == antes


def test_troca_e_atomica_se_o_evento_falha_a_senha_nao_muda(setor, monkeypatch):
    usuario = membro(setor, "troca-atomica")
    cliente = Client(raise_request_exception=False)
    _login(cliente, usuario.matricula, SENHA_TESTE)
    antes = User.objects.get(pk=usuario.pk)

    def _falha(self, *args, **kwargs):
        raise RuntimeError("falha simulada ao gravar o evento")

    with monkeypatch.context() as patch:
        patch.setattr(EventoOrganizacional, "save", _falha)
        _trocar(cliente, SENHA_TESTE)

    assert User.objects.get(pk=usuario.pk).password == antes.password
    assert not _trocas(usuario).exists()
    # sem a falha, a mesma troca funciona: o resultado acima não é o de uma rota que nada faz
    assert _trocar(cliente, SENHA_TESTE).status_code == 302
    assert User.objects.get(pk=usuario.pk).check_password(SENHA_NOVA_VALIDA)


def test_nenhuma_senha_da_troca_aparece_em_log_sessao_ou_evento(definitivo, caplog):
    caplog.set_level(logging.DEBUG)

    assert _trocar(definitivo.sessao, SENHA_TESTE).status_code == 302

    sessoes = " ".join(str(s.get_decoded()) + s.session_data for s in Session.objects.all())
    eventos = " ".join(
        f"{e.dados} {e.justificativa}"
        for e in EventoOrganizacional.objects.filter(usuario=definitivo)
    )
    for senha in (SENHA_NOVA_VALIDA, SENHA_TESTE):
        assert senha not in caplog.text
        assert senha not in sessoes
        assert senha not in eventos


def test_a_troca_nao_depende_de_papel(setor):
    """FR-039: mecânica de autenticação, não capability — o requisitante comum e o administrador
    trocam do mesmo jeito."""
    for matricula, papeis in (("troca-req", set()), ("troca-adm", {Papel.ADMINISTRADOR_SISTEMA})):
        usuario = membro(setor, matricula, papeis)
        cliente = Client()
        _login(cliente, matricula, SENHA_TESTE)

        assert _trocar(cliente, SENHA_TESTE).status_code == 302
        assert User.objects.get(pk=usuario.pk).check_password(SENHA_NOVA_VALIDA)


# ===========================================================================
# Onde cai o erro da política de senha: na Nova senha, não na Confirmação
# ===========================================================================

SENHAS_FORA_DA_POLITICA_SEM_MATRICULA = [
    pytest.param("Ab1-xyz", id="curta"),
    pytest.param("qwertyuiop", id="comum"),
    pytest.param("48291736052", id="so-numeros"),
]


@pytest.mark.parametrize("nova", SENHAS_FORA_DA_POLITICA_SEM_MATRICULA)
def test_definicao_fora_da_politica_acusa_a_nova_senha_e_nao_a_confirmacao(client, comum, nova):
    _login(client, comum.matricula, comum.senha_provisoria_clara)

    erros = _definir(client, nova).context["form"].errors

    assert set(erros) == {CAMPOS_SENHA["nova"]}


@pytest.mark.parametrize("nova", SENHAS_FORA_DA_POLITICA_SEM_MATRICULA)
def test_troca_fora_da_politica_acusa_a_nova_senha_e_nao_a_confirmacao(definitivo, nova):
    resposta = _trocar(definitivo.sessao, SENHA_TESTE, nova)

    assert set(resposta.context["form"].errors) == {CAMPOS_SENHA["nova"]}


def test_definicao_com_confirmacao_diferente_acusa_so_a_confirmacao(client, comum):
    _login(client, comum.matricula, comum.senha_provisoria_clara)

    erros = _definir(client, SENHA_NOVA_VALIDA, confirmacao=SENHA_NOVA_VALIDA + "x").context[
        "form"
    ].errors

    assert set(erros) == {CAMPOS_SENHA["confirmacao"]}
    assert "não correspondem" in str(erros[CAMPOS_SENHA["confirmacao"]])


def test_troca_com_confirmacao_diferente_acusa_so_a_confirmacao(definitivo):
    resposta = _trocar(definitivo.sessao, SENHA_TESTE, SENHA_NOVA_VALIDA, SENHA_NOVA_VALIDA + "x")

    assert set(resposta.context["form"].errors) == {CAMPOS_SENHA["confirmacao"]}


def test_senha_fraca_e_confirmacao_diferente_acusam_cada_erro_no_seu_campo(client, comum):
    _login(client, comum.matricula, comum.senha_provisoria_clara)

    erros = _definir(client, "qwertyuiop", confirmacao="outra-coisa").context["form"].errors

    assert set(erros) == {CAMPOS_SENHA["nova"], CAMPOS_SENHA["confirmacao"]}
    assert "não correspondem" in str(erros[CAMPOS_SENHA["confirmacao"]])


def test_definicao_com_a_propria_provisoria_acusa_a_nova_senha(client, comum):
    _login(client, comum.matricula, comum.senha_provisoria_clara)

    erros = _definir(client, comum.senha_provisoria_clara).context["form"].errors

    assert set(erros) == {CAMPOS_SENHA["nova"]}
    assert "diferente da senha provisória" in str(erros[CAMPOS_SENHA["nova"]])


# ===========================================================================
# Textos de dica montados a partir das regras vigentes
# ===========================================================================


def test_dica_da_senha_do_login_cita_a_validade_vigente_da_provisoria():
    from contas.forms import WMSAuthenticationForm

    dica = WMSAuthenticationForm().fields["password"].help_text

    assert dica == (
        "No primeiro acesso, use a senha provisória que você recebeu. "
        f"Ela vale {VALIDADE_SENHA_PROVISORIA.days} dias a partir da emissão; "
        "ao entrar, você define uma senha sua."
    )
    assert WMSAuthenticationForm().fields["username"].help_text == ""


def test_dica_da_senha_do_login_segue_a_constante_de_validade(monkeypatch):
    from contas import forms as formularios

    monkeypatch.setattr(formularios, "VALIDADE_SENHA_PROVISORIA", timedelta(days=3))

    assert "Ela vale 3 dias" in formularios.ajuda_primeiro_acesso()


def test_dica_da_nova_senha_cita_o_minimo_efetivo_do_validador(settings):
    from contas.forms import DefinirSenhaForm

    assert DefinirSenhaForm(None).fields["new_password1"].help_text == (
        "Use pelo menos 8 caracteres, sem ser só números. "
        "Evite sua matrícula, seu nome e senhas comuns."
    )

    settings.AUTH_PASSWORD_VALIDATORS = [
        {
            "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
            "OPTIONS": {"min_length": 12},
        }
    ]
    # O `setting_changed` do Django limpa o cache dos validadores ao trocar a configuração.
    assert "pelo menos 12 caracteres" in DefinirSenhaForm(None).fields["new_password1"].help_text


def test_senha_atual_da_troca_tem_a_dica_de_quem_a_esqueceu(definitivo):
    form = definitivo.sessao.get(rota("definir_senha")).context["form"]

    assert form.fields["old_password"].help_text == (
        "Esqueceu a senha atual? Saia e peça ao administrador do sistema uma senha provisória."
    )
