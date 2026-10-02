"""Telas de administração da organização — US1 (T019: cadastro e ficha) e US2 (T027: listas,
filtros e ficha de setor). As stories seguintes ACRESCENTAM seções a este arquivo (edição,
papéis, transferência, chefia, situação, redefinição de senha, setores — T032, T037, T042, T047,
T051).

Fontes: `contracts/rotas-e-autorizacao.md` (rotas e "Respostas comuns às operações"),
`contracts/credenciais.md`, FR-007, FR-008, FR-031, FR-043 a FR-045, FR-048, research R8 e R14.
A AUTORIZAÇÃO (quem recebe 403) vive em `test_contas_permissoes_organizacao.py`; aqui o usuário
é sempre o administrador.

O que este arquivo protege, em ordem de consequência:

- a senha provisória aparece UMA vez — na resposta 200 do POST de cadastro, com
  `Cache-Control: no-store` e sem redirect — e nunca em ficha, lista, mensagem, sessão, evento
  ou log; repetir o POST (F5) avisa "já executada" e leva à ficha, sem senha (FR-031, R8);
- toda recusa re-renderiza a tela com o motivo e o caminho EXATAMENTE como a operação os produziu,
  preserva os dados digitados e não grava nada nem consome a `chave_confirmacao` (FR-048);
- a conta técnica não existe para a interface de organização: não é listada, não tem ficha e
  não conta como membro de setor (FR-004, FR-028);
- a lista de usuários combina filtros, busca nome sem acento ou matrícula exata, pagina a 50 e não
  faz N+1; com `HX-Request` devolve só a região de resultados.

Para não acoplar ao markup que o `frontend-implementer` ainda vai refinar, as asserções usam
conteúdo visível (nomes, matrículas, rótulos), status, headers, banco e mensagens — nunca classes
ou estrutura de tags. Os nomes de pessoa são únicos por teste e a presença de uma pessoa na lista
é verificada pelo NOME completo (o eco do filtro `q` nunca é o nome inteiro).

TDD: escrito antes das views de `contas` (T024, T028) existirem.
"""

import logging
import re
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.sessions.models import Session
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from contas import organizacao as org
from contas.models import (
    EventoOrganizacional,
    Papel,
    Setor,
    TipoEvento,
    User,
)
from tests.contas_helpers import (
    PAPEIS_CHEFE_ALMOXARIFADO,
    PARAM_PAGINA,
    SENHA_TESTE,
    chave_do_formulario,
    dados_do_cadastro,
    data_hora,
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
    setor_ativo,
    texto_principal,
    texto_visivel,
)

pytestmark = pytest.mark.django_db

MENSAGEM_JA_EXECUTADA = (
    "Esta operação já foi executada; a senha provisória não é exibida novamente."
)


def _pessoa(nome, matricula, setor, papeis=(), *, ativo=True):
    usuario, _ = org.provisionar_usuario(
        matricula, nome, setor, set(papeis), senha=SENHA_TESTE, is_active=ativo
    )
    return usuario


# ===========================================================================
# US1 — Cadastro (T019)
# ===========================================================================


@pytest.fixture
def cenario(admin_sistema, client):
    """Administrador logado no Almoxarifado Central (inativo, sem chefe), a ETA ativa com chefe
    e o Laboratório inativo."""
    eta, chefe_eta = setor_ativo("ETA", "eta-chefe")
    laboratorio = org.provisionar_setor("Laboratório")
    client.force_login(admin_sistema)
    return SimpleNamespace(
        admin=admin_sistema,
        almoxarifado=admin_sistema.setor,
        eta=eta,
        chefe_eta=chefe_eta,
        lab=laboratorio,
    )


def test_formulario_de_cadastro_traz_uma_chave_de_confirmacao_nova_a_cada_abertura(client, cenario):
    primeira = client.get(rota("usuario_novo"))
    segunda = client.get(rota("usuario_novo"))

    assert primeira.status_code == 200
    assert chave_do_formulario(primeira) != chave_do_formulario(segunda)


def test_seletores_de_setor_tem_rotulo_vazio_em_portugues(client, cenario):
    """O rótulo vazio padrão do Django para `ModelChoiceField` ("- Select an option -") não
    aparece: cadastro e transferência pedem "Escolha o setor" e o filtro diz "Todos os setores"."""
    alvo = _pessoa("Joana Seletor", "SEL-100", cenario.eta)
    paginas = {
        "usuario_novo": ((), "Escolha o setor"),
        "usuarios": ((), "Todos os setores"),
        "usuario_transferir": ((alvo.pk,), "Escolha o setor"),
    }

    for nome, (args, rotulo) in paginas.items():
        conteudo = client.get(rota(nome, *args)).content.decode()
        assert rotulo in conteudo, nome
        assert "Select an option" not in conteudo, nome
        assert "---------" not in conteudo, nome


def test_post_valido_responde_200_com_a_senha_no_store_e_nunca_redireciona(
    client, cenario, monkeypatch
):
    senha = fixar_senha_gerada(monkeypatch)

    resposta = client.post(rota("usuario_novo"), dados_do_cadastro(cenario.eta, nome="Ana Nova"))

    assert resposta.status_code == 200
    assert not resposta.has_header("Location")
    assert "no-store" in resposta["Cache-Control"]
    conteudo = resposta.content.decode()
    assert senha in conteudo
    novo = User.objects.get(matricula="NOVO-0001")
    # ficha resumida e caminho para a ficha completa (FR-007, T025)
    assert "Ana Nova" in conteudo and "NOVO-0001" in conteudo
    assert rota("usuario", novo.pk) in conteudo


def test_post_valido_cria_a_conta_com_os_papeis_do_formulario_e_a_senha_exibida_vale(
    client, cenario, monkeypatch
):
    senha = fixar_senha_gerada(monkeypatch)

    client.post(
        rota("usuario_novo"),
        dados_do_cadastro(
            cenario.eta,
            papeis=[Papel.AUDITOR.value, Papel.AUXILIAR_SETOR.value],
        ),
    )

    novo = User.objects.get(matricula="NOVO-0001")
    assert novo.is_active and novo.setor == cenario.eta
    assert set(novo.papeis.values_list("papel", flat=True)) == {
        Papel.REQUISITANTE,
        Papel.AUDITOR,
        Papel.AUXILIAR_SETOR,
    }
    assert novo.check_password(senha)
    assert novo.senha_provisoria_em is not None
    evento = EventoOrganizacional.objects.get(usuario=novo, tipo=TipoEvento.USUARIO_CADASTRADO)
    assert evento.autor == cenario.admin


def test_a_senha_exibida_nao_aparece_em_nenhum_outro_lugar(client, cenario, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    senha = fixar_senha_gerada(monkeypatch)

    resposta = client.post(rota("usuario_novo"), dados_do_cadastro(cenario.eta))
    assert senha in resposta.content.decode()
    novo = User.objects.get(matricula="NOVO-0001")

    ficha = client.get(rota("usuario", novo.pk))
    lista = client.get(rota("usuarios"))

    assert senha not in ficha.content.decode()
    assert senha not in lista.content.decode()
    for r in (resposta, ficha, lista):
        assert all(senha not in texto for texto in mensagens(r))
    sessoes = " ".join(str(s.get_decoded()) + s.session_data for s in Session.objects.all())
    assert senha not in sessoes
    assert senha not in caplog.text
    for evento in EventoOrganizacional.objects.all():
        assert senha not in f"{evento.dados} {evento.justificativa}"


def test_repetir_o_post_avisa_ja_executada_e_leva_a_ficha_sem_senha(client, cenario, monkeypatch):
    senha = fixar_senha_gerada(monkeypatch)
    dados = dados_do_cadastro(cenario.eta)
    client.post(rota("usuario_novo"), dados)
    novo = User.objects.get(matricula="NOVO-0001")
    hash_antes = novo.password

    repetido = client.post(rota("usuario_novo"), dados)

    assert repetido.status_code == 302
    assert repetido.url == rota("usuario", novo.pk)
    assert senha not in repetido.content.decode()
    assert MENSAGEM_JA_EXECUTADA in mensagens(repetido)
    # nenhuma outra conta, nenhuma outra senha, nenhum outro evento
    assert User.objects.filter(matricula="NOVO-0001").count() == 1
    assert User.objects.get(pk=novo.pk).password == hash_antes
    assert (
        EventoOrganizacional.objects.filter(
            usuario=novo, tipo=TipoEvento.USUARIO_CADASTRADO
        ).count()
        == 1
    )
    ficha = client.get(repetido.url)
    assert ficha.status_code == 200 and senha not in ficha.content.decode()


CASOS_DE_RECUSA = {
    "matricula-repetida": lambda c: {"matricula": c.admin.matricula, "setor": c.eta, "papeis": []},
    "chefe-em-setor-que-ja-tem-chefe": lambda c: {
        "setor": c.eta,
        "papeis": [Papel.CHEFE_SETOR],
    },
    "papel-de-almoxarifado-fora-do-almoxarifado": lambda c: {
        "setor": c.eta,
        "papeis": [Papel.FUNCIONARIO_ALMOXARIFADO],
    },
    "chefia-de-estoque-sem-a-chefia-do-almoxarifado": lambda c: {
        "setor": c.almoxarifado,
        "papeis": [Papel.CHEFE_ALMOXARIFADO],
    },
}


@pytest.mark.parametrize("caso", sorted(CASOS_DE_RECUSA))
def test_recusa_re_renderiza_com_motivo_e_caminho_preserva_dados_e_nao_grava(
    client, cenario, monkeypatch, caso
):
    senha = fixar_senha_gerada(monkeypatch)
    pedido = CASOS_DE_RECUSA[caso](cenario)
    dados = dados_do_cadastro(
        pedido["setor"],
        matricula=pedido.get("matricula", "NOVO-0001"),
        nome="Fulano Preservado",
        papeis=[p.value for p in pedido["papeis"]],
    )
    # o motivo e o caminho esperados são os que a própria operação produz para os mesmos dados
    esperada = recusa_de(
        lambda: org.cadastrar_usuario(
            cenario.admin,
            matricula=dados["matricula"],
            nome=dados["nome"],
            setor_id=pedido["setor"].pk,
            papeis_adicionais={Papel(p) for p in dados["papeis"]},
            chave_confirmacao=uuid.uuid4(),
        )
    )
    antes = foto_organizacao()

    resposta = client.post(rota("usuario_novo"), dados)

    assert resposta.status_code == 200
    texto = texto_visivel(resposta.content.decode())
    assert re.sub(r"\s+", " ", esperada.motivo) in texto
    if esperada.caminho:
        assert re.sub(r"\s+", " ", esperada.caminho) in texto
    assert "Fulano Preservado" in resposta.content.decode()  # dados digitados preservados
    assert dados["matricula"] in resposta.content.decode()
    assert senha not in resposta.content.decode()
    assert foto_organizacao() == antes

    # a chave não foi gasta: corrigida a tela, o MESMO formulário (mesma chave) é aceito
    corrigido = client.post(
        rota("usuario_novo"), {**dados, "matricula": "CORRIGIDO-1", "papeis": []}
    )
    assert corrigido.status_code == 200 and senha in corrigido.content.decode()
    assert User.objects.filter(matricula="CORRIGIDO-1").exists()


def test_erro_de_formulario_re_renderiza_com_200_sem_gravar_nem_mostrar_senha(
    client, cenario, monkeypatch
):
    senha = fixar_senha_gerada(monkeypatch)
    antes = foto_organizacao()

    resposta = client.post(
        rota("usuario_novo"), dados_do_cadastro(cenario.eta, nome="   ", matricula="MANTIDA-1")
    )

    assert resposta.status_code == 200
    assert "MANTIDA-1" in resposta.content.decode()
    assert senha not in resposta.content.decode()
    assert foto_organizacao() == antes


@pytest.mark.parametrize(
    "chave",
    [pytest.param(None, id="sem-chave"), pytest.param("nao-e-uuid", id="chave-invalida")],
)
def test_post_sem_chave_valida_nao_cria_conta_porque_sem_chave_nao_ha_idempotencia(
    client, cenario, monkeypatch, chave
):
    senha = fixar_senha_gerada(monkeypatch)
    dados = dados_do_cadastro(cenario.eta)
    if chave is None:
        del dados["chave_confirmacao"]
    else:
        dados["chave_confirmacao"] = chave
    antes = foto_organizacao()

    resposta = client.post(rota("usuario_novo"), dados)

    assert resposta.status_code == 200
    assert senha not in resposta.content.decode()
    assert foto_organizacao() == antes


def test_cadastro_em_setor_inexistente_e_recusado_sem_gravar(client, cenario):
    antes = foto_organizacao()

    resposta = client.post(rota("usuario_novo"), dados_do_cadastro(cenario.eta, setor="987654321"))

    assert resposta.status_code == 200
    assert foto_organizacao() == antes


# ---------------------------------------------------------------------------
# Ficha do usuário (T019: dados, papéis e situação da credencial)
# ---------------------------------------------------------------------------


def test_ficha_mostra_dados_setor_e_papeis_da_conta_e_nao_os_que_ela_nao_tem(client, cenario):
    alvo = _pessoa("Beatriz Ficha", "FICHA-01", cenario.eta, {Papel.AUDITOR})

    resposta = client.get(rota("usuario", alvo.pk))

    assert resposta.status_code == 200
    texto = texto_visivel(resposta.content.decode())
    assert "FICHA-01" in texto and "Beatriz Ficha" in texto and "ETA" in texto
    assert "Requisitante" in texto and "Gestor/auditor" in texto
    for papel_ausente in (Papel.ADMINISTRADOR_SISTEMA, Papel.CHEFE_ALMOXARIFADO, Papel.CHEFE_SETOR):
        assert papel_ausente.label not in texto


def test_ficha_mostra_provisoria_vigente_com_o_momento_do_vencimento_e_nunca_a_senha(
    client, cenario
):
    alvo, senha = membro_provisorio(cenario.eta, "FICHA-PROV")
    vence = alvo.senha_provisoria_em + timedelta(days=7)

    resposta = client.get(rota("usuario", alvo.pk))

    texto = texto_visivel(resposta.content.decode())
    assert "Provisória" in texto
    assert f"vence em {data_hora(vence)}" in texto
    assert senha not in resposta.content.decode()
    assert alvo.password not in resposta.content.decode()


def test_ficha_mostra_provisoria_vencida_com_o_momento_em_que_venceu(client, cenario):
    alvo, _ = membro_provisorio(cenario.eta, "FICHA-VENC")
    envelhecer_provisoria(alvo, timedelta(days=9))
    alvo.refresh_from_db()
    venceu = alvo.senha_provisoria_em + timedelta(days=7)

    resposta = client.get(rota("usuario", alvo.pk))

    texto = texto_visivel(resposta.content.decode())
    assert "Provisória vencida em" in texto
    assert data_hora(venceu) in texto


def test_ficha_de_conta_com_senha_definitiva_nao_fala_em_provisoria(client, cenario):
    alvo = _pessoa("Carlos Definitivo", "FICHA-DEF", cenario.eta)

    resposta = client.get(rota("usuario", alvo.pk))

    assert "rovisória" not in texto_visivel(resposta.content.decode())


def test_ficha_da_conta_tecnica_e_de_usuario_inexistente_respondem_404(
    client, cenario, superusuario_tecnico
):
    assert client.get(rota("usuario", superusuario_tecnico.pk)).status_code == 404
    assert client.get(rota("usuario", 987654321)).status_code == 404


# ===========================================================================
# US2 — Listas de usuários e de setores, ficha de setor (T027)
# ===========================================================================


@pytest.fixture
def organizacao(client):
    """Organização para as listas. O Almoxarifado tem nome SEM a palavra "almoxarifado" (a marca
    de designação precisa distinguir-se do nome): "Central de Suprimentos". O administrador
    logado mora nele."""
    central = org.provisionar_setor("Central de Suprimentos", almoxarifado=True)
    adm = _pessoa("Adriana Administradora", "ADM-001", central, {Papel.ADMINISTRADOR_SISTEMA})
    eta = org.provisionar_setor("ETA")
    cl = _pessoa("Cláudia Chefe Estação", "CHEFE-ETA", eta, {Papel.CHEFE_SETOR})
    org.provisionar_ativacao(eta)
    lab = org.provisionar_setor("Laboratório Químico")
    ns = SimpleNamespace(
        central=central,
        eta=eta,
        lab=lab,
        admin=adm,
        chefe_eta=cl,
        joao=_pessoa("João da Silva Pereira", "USR-JOAO", eta),
        jose=_pessoa("José Álvaro Mendes", "USR-JOSE", lab),
        maria=_pessoa("Maria Oliveira", "USR-MARIA", eta, {Papel.AUDITOR}),
        pedro=_pessoa("Pedro Desligado", "USR-PEDRO", eta, {Papel.AUDITOR}, ativo=False),
        tecnica=User.objects.create_superuser(
            "TEC-9999", password=SENHA_TESTE, setor=eta, nome="Conta Tecnica Interna"
        ),
    )
    client.force_login(adm)
    return ns


NOMES_DE_USUARIOS = {
    "adm": "Adriana Administradora",
    "chefe_eta": "Cláudia Chefe Estação",
    "joao": "João da Silva Pereira",
    "jose": "José Álvaro Mendes",
    "maria": "Maria Oliveira",
    "pedro": "Pedro Desligado",
}


def _listados(resposta):
    """Chaves de `NOMES_DE_USUARIOS` cujo nome completo aparece na resposta."""
    conteudo = resposta.content.decode()
    return {chave for chave, nome in NOMES_DE_USUARIOS.items() if nome in conteudo}


def _buscar(client, **filtros):
    resposta = client.get(rota("usuarios"), filtros)
    assert resposta.status_code == 200
    return resposta


def test_lista_sem_filtro_mostra_ativos_e_inativos_e_nunca_a_conta_tecnica(client, organizacao):
    resposta = _buscar(client)

    assert _listados(resposta) == set(NOMES_DE_USUARIOS)
    conteudo = resposta.content.decode()
    assert "Conta Tecnica Interna" not in conteudo
    assert "TEC-9999" not in conteudo


@pytest.mark.parametrize(
    "consulta, esperados",
    [
        pytest.param("joao", {"joao"}, id="sem-acento-acha-com-acento"),
        pytest.param("João", {"joao"}, id="com-acento"),
        pytest.param("JOAO", {"joao"}, id="maiusculas"),
        pytest.param("ilva pere", {"joao"}, id="trecho-do-meio-do-nome"),
        pytest.param("alvaro", {"jose"}, id="alvaro-sem-acento"),
        pytest.param("ÁLVARO", {"jose"}, id="alvaro-maiusculo-acentuado"),
        pytest.param("josé", {"jose"}, id="jose-com-acento"),
        pytest.param("Oliveira", {"maria"}, id="sobrenome"),
        pytest.param("USR-MARIA", {"maria"}, id="matricula-exata"),
        pytest.param("USR-MAR", set(), id="matricula-parcial-nao-vale"),
        pytest.param("nome-que-ninguem-tem", set(), id="sem-resultado"),
    ],
)
def test_busca_por_parte_do_nome_ou_matricula_exata(client, organizacao, consulta, esperados):
    resposta = _buscar(client, q=consulta)

    assert _listados(resposta) == esperados


@pytest.mark.parametrize(
    "filtros, esperados",
    [
        pytest.param(
            {"situacao": "ativo"}, {"adm", "chefe_eta", "joao", "jose", "maria"}, id="ativos"
        ),
        pytest.param({"situacao": "inativo"}, {"pedro"}, id="inativos"),
        pytest.param({"papel": Papel.AUDITOR.value}, {"maria", "pedro"}, id="por-papel"),
        pytest.param({"papel": Papel.CHEFE_SETOR.value}, {"chefe_eta"}, id="por-papel-de-chefia"),
        pytest.param(
            {"papel": Papel.REQUISITANTE.value}, set(NOMES_DE_USUARIOS), id="requisitante-e-todos"
        ),
        pytest.param(
            {"situacao": "ativo", "papel": Papel.AUDITOR.value}, {"maria"}, id="situacao-e-papel"
        ),
        pytest.param(
            {"situacao": "inativo", "papel": Papel.CHEFE_SETOR.value}, set(), id="intersecao-vazia"
        ),
        pytest.param({"q": "Maria", "situacao": "inativo"}, set(), id="busca-e-situacao"),
    ],
)
def test_filtros_de_situacao_e_papel_combinam_por_intersecao(
    client, organizacao, filtros, esperados
):
    assert _listados(_buscar(client, **filtros)) == esperados


def test_filtro_de_setor_e_combinavel_com_os_outros(client, organizacao):
    so_eta = _buscar(client, setor=organizacao.eta.pk)
    assert _listados(so_eta) == {"chefe_eta", "joao", "maria", "pedro"}

    eta_auditores_ativos = _buscar(
        client, setor=organizacao.eta.pk, situacao="ativo", papel=Papel.AUDITOR.value
    )
    assert _listados(eta_auditores_ativos) == {"maria"}

    so_lab = _buscar(client, setor=organizacao.lab.pk)
    assert _listados(so_lab) == {"jose"}


def test_a_conta_tecnica_nunca_e_listada_nem_achada_por_busca_ou_filtro(client, organizacao):
    for filtros in (
        {"q": "Conta Tecnica"},
        {"q": "TEC-9999"},
        {"setor": organizacao.eta.pk},
        {"situacao": "ativo"},
        {"papel": Papel.REQUISITANTE.value},
    ):
        conteudo = _buscar(client, **filtros).content.decode()
        assert "Conta Tecnica Interna" not in conteudo, filtros
        assert conteudo.count("TEC-9999") <= 1, filtros  # no máximo o eco do filtro `q`


def test_resultado_mostra_matricula_nome_setor_e_papeis_da_pessoa(client, organizacao):
    """A região de resultados (via HTMX) não traz as opções dos filtros, então os rótulos de
    papel e o nome do setor que aparecem ali são os da linha."""
    resposta = client.get(rota("usuarios"), {"q": "Maria"}, HTTP_HX_REQUEST="true")

    texto = texto_visivel(resposta.content.decode())
    assert "USR-MARIA" in texto and "Maria Oliveira" in texto and "ETA" in texto
    assert "Requisitante" in texto and "Gestor/auditor" in texto
    assert Papel.CHEFE_SETOR.label not in texto and Papel.ADMINISTRADOR_SISTEMA.label not in texto


def test_com_hx_request_so_a_regiao_de_resultados_sem_a_pagina_inteira(client, organizacao):
    completa = client.get(rota("usuarios"), {"q": "Maria"})
    parcial = client.get(rota("usuarios"), {"q": "Maria"}, HTTP_HX_REQUEST="true")

    assert completa.status_code == parcial.status_code == 200
    assert "<html" in completa.content.decode().lower()
    fragmento = parcial.content.decode().lower()
    assert "<html" not in fragmento and "<body" not in fragmento and "<head" not in fragmento
    assert "Maria Oliveira" in parcial.content.decode()
    assert "Maria Oliveira" in completa.content.decode()
    assert "João da Silva Pereira" not in parcial.content.decode()


@pytest.mark.parametrize("com_htmx", [False, True], ids=["pagina", "htmx"])
def test_estado_vazio_sem_resultados(client, organizacao, com_htmx):
    extra = {"HTTP_HX_REQUEST": "true"} if com_htmx else {}

    resposta = client.get(rota("usuarios"), {"q": "ninguem-com-este-nome"}, **extra)

    assert resposta.status_code == 200
    assert _listados(resposta) == set()
    assert "nenhum" in texto_visivel(resposta.content.decode()).lower()


def test_lista_de_usuarios_pagina_a_50_por_pagina(client, organizacao):
    # 6 pessoas já existem; o total passa a 54 listáveis (a conta técnica não conta)
    for i in range(1, 49):
        _pessoa(f"Paginado {i:04d}", f"PAG-{i:04d}", organizacao.eta)
    nomes = {f"Paginado {i:04d}" for i in range(1, 49)} | set(NOMES_DE_USUARIOS.values())
    assert len(nomes) == 54

    def nomes_na_pagina(numero):
        resposta = client.get(rota("usuarios"), {PARAM_PAGINA: numero})
        assert resposta.status_code == 200
        conteudo = resposta.content.decode()
        return {nome for nome in nomes if nome in conteudo}

    primeira, segunda = nomes_na_pagina(1), nomes_na_pagina(2)

    assert len(primeira) == 50
    assert len(segunda) == 4
    assert primeira | segunda == nomes
    assert not primeira & segunda


def test_lista_de_usuarios_faz_numero_fixo_de_queries_independente_de_quantos_usuarios(
    client, organizacao
):
    client.get(rota("usuarios"))  # aquece caches de primeira requisição
    with CaptureQueriesContext(connection) as poucas:
        client.get(rota("usuarios"))

    for i in range(1, 16):
        _pessoa(f"Extra {i:03d}", f"EXT-{i:03d}", organizacao.eta, {Papel.AUDITOR})
    with CaptureQueriesContext(connection) as muitas:
        resposta = client.get(rota("usuarios"))

    assert "Extra 015" in resposta.content.decode()
    assert len(muitas) == len(poucas), (
        f"N+1: {len(poucas)} queries com 6 usuários, {len(muitas)} com 21"
    )


# ---------------------------------------------------------------------------
# Lista e ficha de setores
# ---------------------------------------------------------------------------


@pytest.fixture
def setores(client):
    """Cinco setores; "Setor Beta" nunca é o primeiro nem o último em ordem crescente ou
    decrescente de nome ou de pk (a leitura da linha de cada setor usa o texto até o nome do
    vizinho):

    - "Central de Suprimentos": Almoxarifado designado, ativo, com chefe completo;
    - "Setor Alfa": inativo, sem chefe, um membro ativo;
    - "Setor Beta": ativo, chefe + 6 membros ativos + 2 inativos + conta técnica;
    - "Setor Gama": inativo, nunca ativado, vazio;
    - "Setor Delta": já esteve ativo e foi desativado (mantém o chefe).
    """
    central = org.provisionar_setor("Central de Suprimentos", almoxarifado=True)
    adm = _pessoa("Adriana Administradora", "ADM-001", central, {Papel.ADMINISTRADOR_SISTEMA})
    chefe_central = _pessoa("Gustavo Chefe Central", "alm-ch", central, PAPEIS_CHEFE_ALMOXARIFADO)
    org.provisionar_ativacao(central)

    alfa = org.provisionar_setor("Setor Alfa")
    andre = _pessoa("André Alfa", "alfa-m1", alfa)

    beta = org.provisionar_setor("Setor Beta")
    chefe_beta = _pessoa("Beatriz Chefe Beta", "beta-ch", beta, {Papel.CHEFE_SETOR})
    ativos = [_pessoa(f"Ativo Beta {letra}", f"beta-a{letra}", beta) for letra in "abcdef"]
    inativos = [
        _pessoa(f"Inativo Beta {letra}", f"beta-i{letra}", beta, ativo=False) for letra in "xy"
    ]
    org.provisionar_ativacao(beta)
    tecnica = User.objects.create_superuser(
        "TEC-9999", password=SENHA_TESTE, setor=beta, nome="Conta Tecnica Interna"
    )

    gama = org.provisionar_setor("Setor Gama")

    delta, chefe_delta = setor_ativo("Setor Delta", "delta-ch")
    with operacao():  # estado de uma desativação já feita: inativo, mantém `ativado_em`
        Setor.objects.filter(pk=delta.pk).update(ativo=False)

    client.force_login(adm)
    return SimpleNamespace(
        central=central, chefe_central=chefe_central, alfa=alfa, andre=andre, beta=beta,
        chefe_beta=chefe_beta, ativos=ativos, inativos=inativos, tecnica=tecnica, gama=gama,
        delta=delta, chefe_delta=chefe_delta,
    )  # fmt: skip


def _bloco(texto, nome, outros):
    """Trecho do texto visível que vai do nome do setor até o próximo nome de setor (a linha
    do setor na lista), ou o fim da página."""
    inicio = texto.index(nome)
    fins = [texto.index(o, inicio + 1) for o in outros if o in texto[inicio + 1 :]]
    return texto[inicio : min(fins) if fins else len(texto)]


NOMES_DOS_SETORES = [
    "Central de Suprimentos",
    "Setor Alfa",
    "Setor Beta",
    "Setor Delta",
    "Setor Gama",
]


def _blocos(resposta):
    texto = texto_visivel(resposta.content.decode())
    return {
        nome: _bloco(texto, nome, [n for n in NOMES_DOS_SETORES if n != nome])
        for nome in NOMES_DOS_SETORES
    }


def test_lista_de_setores_mostra_chefe_membros_ativos_e_marca_de_almoxarifado(client, setores):
    resposta = client.get(rota("setores"))

    assert resposta.status_code == 200
    blocos = _blocos(resposta)
    beta = blocos["Setor Beta"]
    assert "Beatriz Chefe Beta" in beta
    inteiros = {int(n) for n in re.findall(r"\b\d+\b", beta)}
    # 1 chefe + 6 membros ativos; os 2 inativos e a conta técnica não contam (FR-028, FR-044)
    assert 7 in inteiros and not inteiros & {8, 9, 10}, beta
    assert "Gustavo Chefe Central" in blocos["Central de Suprimentos"]
    assert "almoxarifado" in blocos["Central de Suprimentos"].lower()  # marca de designação
    assert "almoxarifado" not in beta.lower()
    assert "almoxarifado" not in blocos["Setor Alfa"].lower()
    assert "Beatriz Chefe Beta" not in blocos["Setor Alfa"]  # sem chefe: não mostra o alheio
    assert "Conta Tecnica Interna" not in resposta.content.decode()


@pytest.mark.parametrize(
    "filtros, esperados",
    [
        pytest.param({"situacao": "ativo"}, {"Central de Suprimentos", "Setor Beta"}, id="ativos"),
        pytest.param(
            {"situacao": "inativo"}, {"Setor Alfa", "Setor Gama", "Setor Delta"}, id="inativos"
        ),
        pytest.param({"q": "beta"}, {"Setor Beta"}, id="busca-sem-diferenciar-caixa"),
        pytest.param({"q": "SETOR", "situacao": "ativo"}, {"Setor Beta"}, id="busca-e-situacao"),
        pytest.param({"q": "inexistente"}, set(), id="sem-resultado"),
    ],
)
def test_lista_de_setores_busca_por_nome_e_filtra_por_situacao(client, setores, filtros, esperados):
    resposta = client.get(rota("setores"), filtros)

    conteudo = resposta.content.decode()
    assert {nome for nome in NOMES_DOS_SETORES if nome in conteudo} == esperados


def test_lista_de_setores_sem_resultado_mostra_estado_vazio(client, setores):
    resposta = client.get(rota("setores"), {"q": "inexistente"})

    assert resposta.status_code == 200
    assert "nenhum" in texto_visivel(resposta.content.decode()).lower()


def test_lista_de_setores_faz_numero_fixo_de_queries(client, setores):
    client.get(rota("setores"))  # aquece caches
    with CaptureQueriesContext(connection) as poucas:
        client.get(rota("setores"))

    for i in range(1, 9):
        outro = org.provisionar_setor(f"Setor Extra {i}")
        for j in range(3):
            membro(outro, f"extra-{i}-{j}")
    with CaptureQueriesContext(connection) as muitas:
        resposta = client.get(rota("setores"))

    assert "Setor Extra 8" in resposta.content.decode()
    assert len(muitas) == len(poucas), (
        f"N+1: {len(poucas)} queries com 5 setores, {len(muitas)} com 13"
    )


def test_ficha_do_setor_mostra_chefe_e_membros_ativos_e_inativos_sem_a_conta_tecnica(
    client, setores
):
    resposta = client.get(rota("setor", setores.beta.pk))

    assert resposta.status_code == 200
    texto = texto_visivel(resposta.content.decode())
    assert "Setor Beta" in texto and "Beatriz Chefe Beta" in texto
    for membro_ativo in setores.ativos:
        assert membro_ativo.nome in texto
    for membro_inativo in setores.inativos:
        assert membro_inativo.nome in texto
    assert "Conta Tecnica Interna" not in texto
    # A marca de designação fica nos dados da ficha: o título e a barra trazem
    # o nome do sistema em toda tela, e o histórico registra "Almoxarifado: não".
    ficha = texto_principal(resposta.content.decode()).split("Histórico")[0]
    assert "almoxarifado" not in ficha.lower()


def test_ficha_do_almoxarifado_mostra_a_marca_de_designacao(client, setores):
    resposta = client.get(rota("setor", setores.central.pk))

    # Além do nome do setor ("Almoxarifado Central"), a marca de designação.
    principal = texto_principal(resposta.content.decode())
    assert re.search(r"Almoxarifado(?! Central)", principal)


def test_ficha_de_setor_que_ja_esteve_ativo_mostra_isso_no_historico(client, setores):
    desativado = texto_visivel(client.get(rota("setor", setores.delta.pk)).content.decode())
    nunca_ativo = texto_visivel(client.get(rota("setor", setores.gama.pk)).content.decode())

    assert TipoEvento.SETOR_ATIVADO.label in desativado
    assert TipoEvento.SETOR_ATIVADO.label not in nunca_ativo


def test_ficha_de_setor_inexistente_responde_404(client, setores):
    assert client.get(rota("setor", 987654321)).status_code == 404


def test_lista_de_usuarios_nao_mostra_credencial_de_ninguem(client, organizacao):
    """Conta com provisória não exibe senha nem hash na lista (FR-031)."""
    alvo, senha = membro_provisorio(organizacao.eta, "LISTA-PROV")

    conteudo = client.get(rota("usuarios")).content.decode()

    assert senha not in conteudo and alvo.password not in conteudo


# ===========================================================================
# US3 (T032) — edição, papéis e transferência
#
# Contratos fixados pelos testes (ajustar AQUI se a implementação divergir):
# - `usuario_editar`: POST `nome` e `matricula` (o formulário traz os dois);
# - `usuario_papeis`: POST `papeis` = o conjunto DESEJADO inteiro, com os sete códigos possíveis
#   (a view calcula `conceder`/`remover` contra o estado atual); a tela lista os sete papéis e,
#   nos que a operação recusaria alternar, o motivo da recusa (o mesmo `OperacaoRecusada.motivo`);
# - `usuario_transferir`: POST `setor` (destino); sem `confirmar` → prévia (200, contexto `previa`
#   com `papeis_removidos`, valores dos papéis nos campos que a confirmação reenvia); com
#   `confirmar=1` e `papeis_removidos_previstos` (valores de `Papel`, múltiplo) → executa e 302 para
#   a ficha; previstos que já não correspondem → nova prévia (200), sem executar;
# - toda recusa: 200 com motivo e caminho, dados preservados, nada gravado, nenhum evento.
# ===========================================================================


def _recusa_na_tela(resposta, esperada):
    """200 com o motivo e o caminho EXATAMENTE como a operação os produz."""
    assert resposta.status_code == 200
    texto = texto_visivel(resposta.content.decode())
    assert re.sub(r"\s+", " ", esperada.motivo) in texto
    if esperada.caminho:
        assert re.sub(r"\s+", " ", esperada.caminho) in texto


def _codigos(papeis):
    return sorted(papel.value for papel in papeis)


def _papeis_atuais(usuario):
    return {Papel(p) for p in usuario.papeis.values_list("papel", flat=True)}


# ---------------------------------------------------------------------------
# Edição de nome e matrícula
# ---------------------------------------------------------------------------


def test_formulario_de_edicao_traz_o_nome_e_a_matricula_atuais(client, cenario):
    alvo = _pessoa("Joana Edição", "ED-100", cenario.eta)

    resposta = client.get(rota("usuario_editar", alvo.pk))

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "Joana Edição" in conteudo and "ED-100" in conteudo


def test_edicao_valida_atualiza_a_conta_registra_o_evento_e_volta_a_ficha(client, cenario):
    alvo = _pessoa("Joana Edição", "ED-100", cenario.eta)

    resposta = client.post(
        rota("usuario_editar", alvo.pk), {"nome": "Joana Corrigida", "matricula": "ED-101"}
    )

    assert resposta.status_code == 302 and resposta.url == rota("usuario", alvo.pk)
    assert mensagens(resposta)
    alvo.refresh_from_db()
    assert (alvo.nome, alvo.matricula) == ("Joana Corrigida", "ED-101")
    evento = EventoOrganizacional.objects.get(tipo=TipoEvento.USUARIO_EDITADO)
    assert evento.autor == cenario.admin and evento.usuario == alvo


def test_a_matricula_anterior_aparece_no_historico_da_ficha(client, cenario):
    alvo = _pessoa("Joana Edição", "ED-100", cenario.eta)
    client.post(rota("usuario_editar", alvo.pk), {"nome": "Joana Edição", "matricula": "ED-101"})

    texto = texto_visivel(client.get(rota("usuario", alvo.pk)).content.decode())

    assert "ED-101" in texto
    assert "ED-100" in texto, "FR-009: o histórico registra a matrícula anterior"


@pytest.mark.parametrize(
    "campos",
    [
        pytest.param(
            {"nome": "Nome Digitado", "matricula": "ED-EXISTENTE"}, id="matricula-repetida"
        ),
        pytest.param({"nome": "   ", "matricula": "ED-NOVA"}, id="nome-so-espacos"),
        pytest.param({"nome": "Nome Digitado", "matricula": ""}, id="matricula-vazia"),
    ],
)
def test_edicao_recusada_re_renderiza_com_200_preserva_o_digitado_e_nao_grava(
    client, cenario, campos
):
    alvo = _pessoa("Joana Edição", "ED-100", cenario.eta)
    _pessoa("Outra Pessoa", "ED-EXISTENTE", cenario.eta)
    antes = foto_organizacao()

    resposta = client.post(rota("usuario_editar", alvo.pk), campos)

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    if campos["nome"].strip():
        assert campos["nome"] in conteudo, "dados digitados preservados"
    if campos["matricula"]:
        assert campos["matricula"] in conteudo
    assert foto_organizacao() == antes


def test_edicao_da_matricula_repetida_mostra_o_motivo_da_operacao(client, cenario):
    alvo = _pessoa("Joana Edição", "ED-100", cenario.eta)
    _pessoa("Outra Pessoa", "ED-EXISTENTE", cenario.eta)
    esperada = recusa_de(
        lambda: org.editar_usuario(cenario.admin, alvo.pk, matricula="ED-EXISTENTE")
    )

    resposta = client.post(
        rota("usuario_editar", alvo.pk), {"nome": "Joana Edição", "matricula": "ED-EXISTENTE"}
    )

    _recusa_na_tela(resposta, esperada)


def test_edicao_sem_mudanca_volta_a_ficha_sem_gerar_evento(client, cenario):
    alvo = _pessoa("Joana Edição", "ED-100", cenario.eta)
    antes = foto_organizacao()

    resposta = client.post(
        rota("usuario_editar", alvo.pk), {"nome": "Joana Edição", "matricula": "ED-100"}
    )

    assert resposta.status_code == 302 and resposta.url == rota("usuario", alvo.pk)
    assert foto_organizacao() == antes


# ---------------------------------------------------------------------------
# Papéis
# ---------------------------------------------------------------------------


def test_tela_de_papeis_lista_os_sete_papeis_e_o_motivo_dos_bloqueados(client, cenario):
    """Chefe da ETA: não pode perder `ROLE-REQUESTER` nem `ROLE-SECTOR-HEAD`, nem receber os dois
    papéis de almoxarifado — cada bloqueio traz o motivo que a operação daria."""
    chefe = cenario.chefe_eta

    def motivo_de(conceder=(), remover=()):
        return recusa_de(
            lambda: org.alterar_papeis(
                cenario.admin, chefe.pk, conceder=set(conceder), remover=set(remover)
            )
        )

    bloqueios = [
        motivo_de(remover={Papel.REQUISITANTE}),
        motivo_de(remover={Papel.CHEFE_SETOR}),
        motivo_de(conceder={Papel.CHEFE_ALMOXARIFADO}),
        motivo_de(conceder={Papel.FUNCIONARIO_ALMOXARIFADO}),
    ]

    resposta = client.get(rota("usuario_papeis", chefe.pk))

    assert resposta.status_code == 200
    texto = texto_principal(resposta.content.decode())
    for papel in Papel:
        assert papel.label in texto, f"a tela lista os sete papéis; faltou {papel.label}"
    for recusa in bloqueios:
        assert re.sub(r"\s+", " ", recusa.motivo) in texto


def test_concessao_valida_de_papel_grava_registra_o_evento_e_volta_a_ficha(client, cenario):
    alvo = _pessoa("Pedro Papéis", "PAP-100", cenario.eta, {Papel.AUXILIAR_SETOR})
    desejado = {Papel.REQUISITANTE, Papel.AUDITOR}  # concede auditor, remove auxiliar

    resposta = client.post(rota("usuario_papeis", alvo.pk), {"papeis": _codigos(desejado)})

    assert resposta.status_code == 302 and resposta.url == rota("usuario", alvo.pk)
    assert mensagens(resposta)
    assert _papeis_atuais(alvo) == desejado
    evento = EventoOrganizacional.objects.get(tipo=TipoEvento.PAPEIS_ALTERADOS)
    assert evento.autor == cenario.admin and evento.usuario == alvo


def test_envio_sem_mudanca_de_papeis_nao_gera_evento(client, cenario):
    alvo = _pessoa("Pedro Papéis", "PAP-100", cenario.eta, {Papel.AUDITOR})
    antes = foto_organizacao()

    resposta = client.post(
        rota("usuario_papeis", alvo.pk), {"papeis": _codigos(_papeis_atuais(alvo))}
    )

    assert resposta.status_code == 302
    assert foto_organizacao() == antes


# (id, conceder, remover) sobre um membro comum da ETA
PEDIDOS_DE_PAPEL_RECUSADOS = [
    pytest.param(set(), {Papel.REQUISITANTE}, id="remover-requisitante"),
    pytest.param({Papel.CHEFE_SETOR}, set(), id="conceder-chefia-de-setor-ativo-com-chefe"),
    pytest.param({Papel.CHEFE_ALMOXARIFADO}, set(), id="conceder-chefia-de-estoque"),
    pytest.param({Papel.FUNCIONARIO_ALMOXARIFADO}, set(), id="funcionario-fora-do-almoxarifado"),
    pytest.param({Papel.AUDITOR}, {Papel.REQUISITANTE}, id="valido-junto-com-invalido"),
]


@pytest.mark.parametrize("conceder, remover", PEDIDOS_DE_PAPEL_RECUSADOS)
def test_papeis_recusados_mostram_motivo_e_caminho_e_nao_gravam_nada(
    client, cenario, conceder, remover
):
    alvo = _pessoa("Pedro Papéis", "PAP-100", cenario.eta)
    esperada = recusa_de(
        lambda: org.alterar_papeis(cenario.admin, alvo.pk, conceder=conceder, remover=remover)
    )
    desejado = (_papeis_atuais(alvo) | conceder) - remover
    antes = foto_organizacao()

    resposta = client.post(rota("usuario_papeis", alvo.pk), {"papeis": _codigos(desejado)})

    _recusa_na_tela(resposta, esperada)
    assert foto_organizacao() == antes


def test_o_ultimo_administrador_nao_se_retira_o_papel_pela_tela(client, cenario):
    esperada = recusa_de(
        lambda: org.alterar_papeis(
            cenario.admin, cenario.admin.pk, conceder=set(), remover={Papel.ADMINISTRADOR_SISTEMA}
        )
    )
    desejado = _papeis_atuais(cenario.admin) - {Papel.ADMINISTRADOR_SISTEMA}
    antes = foto_organizacao()

    resposta = client.post(rota("usuario_papeis", cenario.admin.pk), {"papeis": _codigos(desejado)})

    _recusa_na_tela(resposta, esperada)
    assert foto_organizacao() == antes


def test_codigo_de_papel_desconhecido_e_recusado_sem_gravar(client, cenario):
    alvo = _pessoa("Pedro Papéis", "PAP-100", cenario.eta)
    antes = foto_organizacao()

    resposta = client.post(
        rota("usuario_papeis", alvo.pk), {"papeis": ["ROLE-REQUESTER", "ROLE-INEXISTENTE"]}
    )

    assert resposta.status_code == 200
    assert foto_organizacao() == antes


# ---------------------------------------------------------------------------
# Transferência em duas etapas (FR-013, FR-049)
# ---------------------------------------------------------------------------


@pytest.fixture
def auxiliar(cenario):
    return _pessoa("Ana Auxiliar", "TR-100", cenario.eta, {Papel.AUXILIAR_SETOR, Papel.AUDITOR})


def test_formulario_de_transferencia_oferece_os_setores_de_destino(client, cenario, auxiliar):
    resposta = client.get(rota("usuario_transferir", auxiliar.pk))

    assert resposta.status_code == 200
    assert "Laboratório" in texto_principal(resposta.content.decode())


def test_primeiro_envio_mostra_a_previa_com_os_papeis_a_remover_e_nao_transfere(
    client, cenario, auxiliar
):
    antes = foto_organizacao()

    resposta = client.post(rota("usuario_transferir", auxiliar.pk), {"setor": cenario.lab.pk})

    assert resposta.status_code == 200
    assert set(resposta.context["previa"].papeis_removidos) == {Papel.AUXILIAR_SETOR}
    texto = texto_principal(resposta.content.decode())
    assert Papel.AUXILIAR_SETOR.label in texto and "Laboratório" in texto
    assert Papel.AUXILIAR_SETOR.value in resposta.content.decode(), (
        "a confirmação precisa reenviar os papéis previstos"
    )
    assert foto_organizacao() == antes, "a prévia não grava nada nem gera evento"


def test_confirmacao_executa_a_transferencia_com_os_papeis_previstos(client, cenario, auxiliar):
    resposta = client.post(
        rota("usuario_transferir", auxiliar.pk),
        {
            "setor": cenario.lab.pk,
            "confirmar": "1",
            "papeis_removidos_previstos": [Papel.AUXILIAR_SETOR.value],
        },
    )

    assert resposta.status_code == 302 and resposta.url == rota("usuario", auxiliar.pk)
    assert mensagens(resposta)
    auxiliar.refresh_from_db()
    assert auxiliar.setor == cenario.lab
    assert _papeis_atuais(auxiliar) == {Papel.REQUISITANTE, Papel.AUDITOR}
    evento = EventoOrganizacional.objects.get(tipo=TipoEvento.USUARIO_TRANSFERIDO)
    assert evento.autor == cenario.admin and evento.usuario == auxiliar
    assert evento.setor == cenario.lab and evento.setor_relacionado == cenario.eta


@pytest.mark.parametrize(
    "previstos",
    [
        pytest.param(None, id="sem-previstos-nao-se-pula-a-previa"),
        pytest.param([Papel.AUDITOR.value], id="previstos-que-nao-sao-os-efeitos"),
        pytest.param(
            [Papel.AUXILIAR_SETOR.value, Papel.FUNCIONARIO_ALMOXARIFADO.value],
            id="previstos-a-mais",
        ),
    ],
)
def test_previa_desatualizada_mostra_a_previa_nova_e_nao_transfere(
    client, cenario, auxiliar, previstos
):
    corpo = {"setor": cenario.lab.pk, "confirmar": "1"}
    if previstos is not None:
        corpo["papeis_removidos_previstos"] = previstos
    antes = foto_organizacao()

    resposta = client.post(rota("usuario_transferir", auxiliar.pk), corpo)

    assert resposta.status_code == 200
    assert set(resposta.context["previa"].papeis_removidos) == {Papel.AUXILIAR_SETOR}
    assert Papel.AUXILIAR_SETOR.label in texto_principal(resposta.content.decode())
    assert foto_organizacao() == antes, "efeitos diferentes dos que foram vistos: não executa"

    # com a prévia nova, a confirmação passa
    confirmada = client.post(
        rota("usuario_transferir", auxiliar.pk),
        {
            "setor": cenario.lab.pk,
            "confirmar": "1",
            "papeis_removidos_previstos": [Papel.AUXILIAR_SETOR.value],
        },
    )
    assert confirmada.status_code == 302
    auxiliar.refresh_from_db()
    assert auxiliar.setor == cenario.lab


def test_transferencia_sem_papeis_a_remover_tambem_passa_pela_previa(client, cenario):
    simples = _pessoa("Sem Papéis", "TR-101", cenario.eta)

    previa = client.post(rota("usuario_transferir", simples.pk), {"setor": cenario.lab.pk})
    confirmada = client.post(
        rota("usuario_transferir", simples.pk), {"setor": cenario.lab.pk, "confirmar": "1"}
    )

    assert previa.status_code == 200 and set(previa.context["previa"].papeis_removidos) == set()
    assert confirmada.status_code == 302
    simples.refresh_from_db()
    assert simples.setor == cenario.lab


@pytest.mark.parametrize("confirmar", [False, True], ids=["na-previa", "na-confirmacao"])
def test_transferencia_de_chefe_de_setor_ativo_mostra_motivo_e_caminho_e_nao_grava(
    client, cenario, confirmar
):
    esperada = recusa_de(
        lambda: org.transferir_usuario(
            cenario.admin, cenario.chefe_eta.pk, cenario.lab.pk, papeis_removidos_previstos=set()
        )
    )
    corpo = {"setor": cenario.lab.pk}
    if confirmar:
        corpo["confirmar"] = "1"
    antes = foto_organizacao()

    resposta = client.post(rota("usuario_transferir", cenario.chefe_eta.pk), corpo)

    _recusa_na_tela(resposta, esperada)
    assert foto_organizacao() == antes


@pytest.mark.parametrize("confirmar", [False, True], ids=["na-previa", "na-confirmacao"])
def test_transferencia_para_o_proprio_setor_e_recusada_sem_gravar(client, cenario, confirmar):
    """A tela pode nem oferecer o setor atual; se vier por POST direto, o servidor recusa."""
    alvo = _pessoa("Ana Parada", "TR-102", cenario.eta, {Papel.AUXILIAR_SETOR})
    corpo = {"setor": cenario.eta.pk}
    if confirmar:
        corpo.update({"confirmar": "1", "papeis_removidos_previstos": [Papel.AUXILIAR_SETOR.value]})
    antes = foto_organizacao()

    resposta = client.post(rota("usuario_transferir", alvo.pk), corpo)

    assert resposta.status_code == 200
    assert foto_organizacao() == antes


@pytest.mark.parametrize(
    "destino", ["", "987654321", "abc"], ids=["vazio", "inexistente", "invalido"]
)
def test_transferencia_sem_destino_valido_re_renderiza_sem_gravar(
    client, cenario, auxiliar, destino
):
    antes = foto_organizacao()

    resposta = client.post(
        rota("usuario_transferir", auxiliar.pk), {"setor": destino, "confirmar": "1"}
    )

    assert resposta.status_code == 200
    assert foto_organizacao() == antes


# ===========================================================================
# US4 (T037) — chefia do setor: designar, retirar e substituir
#
# Contratos fixados pelos testes (ajustar AQUI se a implementação divergir): uma só rota,
# `setor_chefia`, cujo comportamento decide o estado do setor — ativo → substituição; inativo sem
# chefe ativo → designação; inativo com chefe → retirada.
# - substituição: POST `novo_chefe` (pk); sem `confirmar` → prévia (200, contexto `previa` com
#   `chefe_atual`, `novo_chefe`, `novo_ganha`, `anterior_perde`); com `confirmar=1` e
#   `chefe_esperado` (pk) → executa e 302 para a ficha do setor;
# - designação: POST `usuario` (pk) → executa e 302; retirada: POST com `confirmar=1`.
# - candidatos oferecidos na tela: membros ATIVOS do setor (a conta técnica nunca).
# ===========================================================================


@pytest.fixture
def chefias(cenario):
    """Candidatos para as telas de chefia, com nomes únicos e sem relação de substring."""
    return SimpleNamespace(
        pedro=_pessoa("Pedro Candidato", "CH-PEDRO", cenario.eta),
        paulo=_pessoa("Paulo Candidato", "CH-PAULO", cenario.eta, {Papel.AUDITOR}),
        inativo=_pessoa("Ines Inativa Eta", "CH-INAT", cenario.eta, ativo=False),
        tecnica=User.objects.create_superuser(
            "CH-TEC", password=SENHA_TESTE, setor=cenario.eta, nome="Conta Tecnica Chefia"
        ),
        luiza=_pessoa("Luiza Laboratorista", "CH-LUIZA", cenario.lab),
        lucas=_pessoa("Lucas Laboratorista", "CH-LUCAS", cenario.lab),
        inativa_lab=_pessoa("Iara Inativa Lab", "CH-IARA", cenario.lab, ativo=False),
        carla=_pessoa(
            "Carla Almoxarife", "CH-CARLA", cenario.almoxarifado, {Papel.FUNCIONARIO_ALMOXARIFADO}
        ),
        davi=_pessoa("Davi Sem Estoque", "CH-DAVI", cenario.almoxarifado),
    )


def _chefe_do_almoxarifado_ativo(cenario):
    joao = _pessoa("João Chefe Estoque", "CH-JOAO", cenario.almoxarifado, PAPEIS_CHEFE_ALMOXARIFADO)
    org.provisionar_ativacao(cenario.almoxarifado)
    return joao


def _papeis_do(usuario):
    atribuidos = User.objects.get(pk=usuario.pk).papeis.values_list("papel", flat=True)
    return {Papel(p) for p in atribuidos}


def _chefes(setor):
    return [u.pk for u in User.objects.filter(
        setor=setor, is_active=True, papeis__papel=Papel.CHEFE_SETOR
    )]  # fmt: skip


# ---------------------------------------------------------------------------
# Setor ativo: substituição
# ---------------------------------------------------------------------------


def test_tela_de_substituicao_mostra_o_chefe_atual_e_so_candidatos_ativos_do_setor(
    client, cenario, chefias
):
    resposta = client.get(rota("setor_chefia", cenario.eta.pk))

    assert resposta.status_code == 200
    texto = texto_principal(resposta.content.decode())
    assert cenario.chefe_eta.nome in texto
    assert "Pedro Candidato" in texto and "Paulo Candidato" in texto
    for fora_do_alcance in (chefias.inativo, chefias.tecnica, chefias.luiza, chefias.carla):
        assert fora_do_alcance.nome not in texto, fora_do_alcance.nome


def test_primeiro_envio_da_substituicao_mostra_a_previa_e_nao_troca_ninguem(
    client, cenario, chefias
):
    antes = foto_organizacao()

    resposta = client.post(rota("setor_chefia", cenario.eta.pk), {"novo_chefe": chefias.pedro.pk})

    assert resposta.status_code == 200
    previa = resposta.context["previa"]
    assert previa.chefe_atual == cenario.chefe_eta and previa.novo_chefe == chefias.pedro
    assert set(previa.novo_ganha) == {Papel.CHEFE_SETOR}
    assert set(previa.anterior_perde) == {Papel.CHEFE_SETOR}
    texto = texto_principal(resposta.content.decode())
    assert cenario.chefe_eta.nome in texto and "Pedro Candidato" in texto
    assert Papel.CHEFE_SETOR.label in texto
    assert foto_organizacao() == antes


def test_confirmacao_da_substituicao_troca_a_chefia_e_volta_a_ficha_do_setor(
    client, cenario, chefias
):
    resposta = client.post(
        rota("setor_chefia", cenario.eta.pk),
        {
            "novo_chefe": chefias.pedro.pk,
            "confirmar": "1",
            "chefe_esperado": cenario.chefe_eta.pk,
            "novo_ganha_previsto": [Papel.CHEFE_SETOR.value],
            "anterior_perde_previsto": [Papel.CHEFE_SETOR.value],
        },
    )

    assert resposta.status_code == 302 and resposta.url == rota("setor", cenario.eta.pk)
    assert mensagens(resposta)
    assert _chefes(cenario.eta) == [chefias.pedro.pk]
    assert _papeis_do(cenario.chefe_eta) == {Papel.REQUISITANTE}
    evento = EventoOrganizacional.objects.get(tipo=TipoEvento.CHEFIA_SUBSTITUIDA)
    assert evento.autor == cenario.admin
    assert evento.usuario == chefias.pedro and evento.usuario_relacionado == cenario.chefe_eta
    assert evento.setor == cenario.eta


def test_previa_no_almoxarifado_mostra_a_chefia_de_estoque_e_o_funcionario_que_falta(
    client, cenario, chefias
):
    """Cenário 4 da US4: a confirmação mostra antes que o novo chefe também vira funcionário."""
    joao = _chefe_do_almoxarifado_ativo(cenario)

    resposta = client.post(
        rota("setor_chefia", cenario.almoxarifado.pk), {"novo_chefe": chefias.davi.pk}
    )

    assert resposta.status_code == 200
    previa = resposta.context["previa"]
    assert previa.chefe_atual == joao
    assert set(previa.novo_ganha) == {
        Papel.CHEFE_SETOR,
        Papel.CHEFE_ALMOXARIFADO,
        Papel.FUNCIONARIO_ALMOXARIFADO,
    }
    assert set(previa.anterior_perde) == {Papel.CHEFE_SETOR, Papel.CHEFE_ALMOXARIFADO}
    texto = texto_principal(resposta.content.decode())
    for papel in (Papel.CHEFE_SETOR, Papel.CHEFE_ALMOXARIFADO, Papel.FUNCIONARIO_ALMOXARIFADO):
        assert papel.label in texto


def test_confirmacao_no_almoxarifado_move_a_chefia_de_estoque(client, cenario, chefias):
    joao = _chefe_do_almoxarifado_ativo(cenario)

    resposta = client.post(
        rota("setor_chefia", cenario.almoxarifado.pk),
        {
            "novo_chefe": chefias.carla.pk,
            "confirmar": "1",
            "chefe_esperado": joao.pk,
            "novo_ganha_previsto": [Papel.CHEFE_SETOR.value, Papel.CHEFE_ALMOXARIFADO.value],
            "anterior_perde_previsto": [Papel.CHEFE_SETOR.value, Papel.CHEFE_ALMOXARIFADO.value],
        },
    )

    assert resposta.status_code == 302
    assert _papeis_do(chefias.carla) == {Papel.REQUISITANTE, *PAPEIS_CHEFE_ALMOXARIFADO}
    assert _papeis_do(joao) == {Papel.REQUISITANTE, Papel.FUNCIONARIO_ALMOXARIFADO}


def test_a_previa_reenvia_os_efeitos_mostrados_para_a_confirmacao(client, cenario, chefias):
    _chefe_do_almoxarifado_ativo(cenario)

    resposta = client.post(
        rota("setor_chefia", cenario.almoxarifado.pk), {"novo_chefe": chefias.davi.pk}
    )

    assert {_valor(t) for t in _campos(resposta, "hidden", "novo_ganha_previsto")} == {
        Papel.CHEFE_SETOR.value,
        Papel.CHEFE_ALMOXARIFADO.value,
        Papel.FUNCIONARIO_ALMOXARIFADO.value,
    }
    assert {_valor(t) for t in _campos(resposta, "hidden", "anterior_perde_previsto")} == {
        Papel.CHEFE_SETOR.value,
        Papel.CHEFE_ALMOXARIFADO.value,
    }


def test_confirmacao_com_efeitos_desatualizados_mostra_a_previa_nova_e_nao_troca_ninguem(
    client, cenario, chefias
):
    """FR-049: a prévia de Carla não listava `ROLE-WAREHOUSE-STAFF` em "Recebe" porque ela já o
    tinha; o papel foi retirado antes da confirmação."""
    joao = _chefe_do_almoxarifado_ativo(cenario)
    org.alterar_papeis(
        cenario.admin,
        chefias.carla.pk,
        conceder=set(),
        remover={Papel.FUNCIONARIO_ALMOXARIFADO},
    )
    antes = foto_organizacao()

    resposta = client.post(
        rota("setor_chefia", cenario.almoxarifado.pk),
        {
            "novo_chefe": chefias.carla.pk,
            "confirmar": "1",
            "chefe_esperado": joao.pk,
            "novo_ganha_previsto": [Papel.CHEFE_SETOR.value, Papel.CHEFE_ALMOXARIFADO.value],
            "anterior_perde_previsto": [Papel.CHEFE_SETOR.value, Papel.CHEFE_ALMOXARIFADO.value],
        },
    )

    assert resposta.status_code == 200, "mostra a prévia nova, sem redirecionar"
    assert not mensagens(resposta)
    assert Papel.FUNCIONARIO_ALMOXARIFADO in resposta.context["previa"].novo_ganha
    assert Papel.FUNCIONARIO_ALMOXARIFADO.value in {
        _valor(t) for t in _campos(resposta, "hidden", "novo_ganha_previsto")
    }, "a confirmação seguinte já leva os efeitos novos"
    assert foto_organizacao() == antes
    assert _chefes(cenario.almoxarifado) == [joao.pk]


def test_confirmar_a_substituicao_sem_os_efeitos_previstos_nao_executa(client, cenario, chefias):
    """Um POST de confirmação sem os efeitos da prévia (forjado ou incompleto) é tratado como
    prévia desatualizada: o servidor devolve a prévia, não executa."""
    antes = foto_organizacao()

    resposta = client.post(
        rota("setor_chefia", cenario.eta.pk),
        {
            "novo_chefe": chefias.pedro.pk,
            "confirmar": "1",
            "chefe_esperado": cenario.chefe_eta.pk,
        },
    )

    assert resposta.status_code == 200
    assert set(resposta.context["previa"].novo_ganha) == {Papel.CHEFE_SETOR}
    assert foto_organizacao() == antes


def test_chefe_esperado_desatualizado_mostra_o_motivo_e_nao_troca_ninguem(client, cenario, chefias):
    """O administrador abriu a tela com a Maria como chefe; outra substituição aconteceu antes
    do clique (FR-017)."""
    org.substituir_chefia(
        cenario.admin,
        cenario.eta.pk,
        chefe_esperado_id=cenario.chefe_eta.pk,
        novo_chefe_id=chefias.pedro.pk,
    )
    esperada = recusa_de(
        lambda: org.substituir_chefia(
            cenario.admin,
            cenario.eta.pk,
            chefe_esperado_id=cenario.chefe_eta.pk,
            novo_chefe_id=chefias.paulo.pk,
        )
    )
    antes = foto_organizacao()

    resposta = client.post(
        rota("setor_chefia", cenario.eta.pk),
        {
            "novo_chefe": chefias.paulo.pk,
            "confirmar": "1",
            "chefe_esperado": cenario.chefe_eta.pk,
        },
    )

    _recusa_na_tela(resposta, esperada)
    assert _chefes(cenario.eta) == [chefias.pedro.pk]
    assert foto_organizacao() == antes


def test_confirmar_a_substituicao_sem_dizer_quem_era_o_chefe_nao_executa(client, cenario, chefias):
    antes = foto_organizacao()

    resposta = client.post(
        rota("setor_chefia", cenario.eta.pk), {"novo_chefe": chefias.pedro.pk, "confirmar": "1"}
    )

    assert resposta.status_code == 200
    assert foto_organizacao() == antes


@pytest.mark.parametrize("quem", ["luiza", "inativo", "tecnica", "chefe_atual", "inexistente"])
def test_candidato_a_novo_chefe_fora_do_alcance_nao_e_aceito_nem_com_post_direto(
    client, cenario, chefias, quem
):
    """Outro setor, inativo, conta técnica, o próprio chefe, pk inexistente: a tela só oferece
    membros ativos, e o servidor decide mesmo sem a tela (FR-015, FR-048)."""
    pk = {
        "luiza": chefias.luiza.pk,
        "inativo": chefias.inativo.pk,
        "tecnica": chefias.tecnica.pk,
        "chefe_atual": cenario.chefe_eta.pk,
        "inexistente": 987_654_321,
    }[quem]
    antes = foto_organizacao()

    previa = client.post(rota("setor_chefia", cenario.eta.pk), {"novo_chefe": pk})
    confirmada = client.post(
        rota("setor_chefia", cenario.eta.pk),
        {"novo_chefe": pk, "confirmar": "1", "chefe_esperado": cenario.chefe_eta.pk},
    )

    assert previa.status_code == 200 and confirmada.status_code == 200
    assert foto_organizacao() == antes
    assert _chefes(cenario.eta) == [cenario.chefe_eta.pk]


def test_campo_de_designacao_nao_substitui_o_chefe_de_setor_ativo(client, cenario, chefias):
    antes = foto_organizacao()

    resposta = client.post(rota("setor_chefia", cenario.eta.pk), {"usuario": chefias.pedro.pk})

    assert resposta.status_code == 200
    assert foto_organizacao() == antes


# ---------------------------------------------------------------------------
# Setor inativo sem chefe: designação
# ---------------------------------------------------------------------------


def test_tela_de_designacao_oferece_so_membros_ativos_do_setor(client, cenario, chefias):
    resposta = client.get(rota("setor_chefia", cenario.lab.pk))

    assert resposta.status_code == 200
    texto = texto_principal(resposta.content.decode())
    assert "Luiza Laboratorista" in texto and "Lucas Laboratorista" in texto
    for fora_do_alcance in (chefias.inativa_lab, chefias.pedro, chefias.carla):
        assert fora_do_alcance.nome not in texto, fora_do_alcance.nome


def test_designacao_concede_a_chefia_sem_ativar_o_setor_e_volta_a_ficha(client, cenario, chefias):
    resposta = client.post(rota("setor_chefia", cenario.lab.pk), {"usuario": chefias.luiza.pk})

    assert resposta.status_code == 302 and resposta.url == rota("setor", cenario.lab.pk)
    assert mensagens(resposta)
    assert _chefes(cenario.lab) == [chefias.luiza.pk]
    cenario.lab.refresh_from_db()
    assert cenario.lab.ativo is False
    evento = EventoOrganizacional.objects.get(tipo=TipoEvento.CHEFIA_DESIGNADA)
    assert evento.autor == cenario.admin
    assert evento.usuario == chefias.luiza and evento.setor == cenario.lab


def test_designacao_no_almoxarifado_inativo_concede_os_tres_papeis(client, cenario, chefias):
    resposta = client.post(
        rota("setor_chefia", cenario.almoxarifado.pk), {"usuario": chefias.davi.pk}
    )

    assert resposta.status_code == 302
    assert _papeis_do(chefias.davi) == {Papel.REQUISITANTE, *PAPEIS_CHEFE_ALMOXARIFADO}


@pytest.mark.parametrize("quem", ["inativa_lab", "pedro", "inexistente"])
def test_designacao_de_quem_nao_e_membro_ativo_do_setor_e_recusada_sem_gravar(
    client, cenario, chefias, quem
):
    pk = 987_654_321 if quem == "inexistente" else getattr(chefias, quem).pk
    antes = foto_organizacao()

    resposta = client.post(rota("setor_chefia", cenario.lab.pk), {"usuario": pk})

    assert resposta.status_code == 200
    assert foto_organizacao() == antes


# ---------------------------------------------------------------------------
# Setor inativo com chefe: retirada
# ---------------------------------------------------------------------------


@pytest.fixture
def lab_com_chefe(cenario, chefias):
    org.designar_chefia(cenario.admin, cenario.lab.pk, chefias.luiza.pk)
    return chefias.luiza


def test_tela_de_retirada_mostra_o_chefe_a_ser_retirado(client, cenario, lab_com_chefe):
    resposta = client.get(rota("setor_chefia", cenario.lab.pk))

    assert resposta.status_code == 200
    assert "Luiza Laboratorista" in texto_principal(resposta.content.decode())


def test_retirada_exige_confirmacao_e_depois_tira_a_chefia(client, cenario, lab_com_chefe):
    sem_confirmar = client.post(rota("setor_chefia", cenario.lab.pk), {"estado": "retirar"})
    assert sem_confirmar.status_code == 200
    assert _chefes(cenario.lab) == [lab_com_chefe.pk], "sem `confirmar` nada é retirado"

    confirmada = client.post(
        rota("setor_chefia", cenario.lab.pk), {"estado": "retirar", "confirmar": "1"}
    )

    assert confirmada.status_code == 302 and confirmada.url == rota("setor", cenario.lab.pk)
    assert mensagens(confirmada)
    assert _chefes(cenario.lab) == []
    assert _papeis_do(lab_com_chefe) == {Papel.REQUISITANTE}
    evento = EventoOrganizacional.objects.get(tipo=TipoEvento.CHEFIA_RETIRADA)
    assert evento.autor == cenario.admin
    assert evento.usuario == lab_com_chefe and evento.setor == cenario.lab


def test_depois_da_retirada_a_tela_volta_a_oferecer_a_designacao(client, cenario, lab_com_chefe):
    client.post(rota("setor_chefia", cenario.lab.pk), {"estado": "retirar", "confirmar": "1"})

    resposta = client.get(rota("setor_chefia", cenario.lab.pk))

    texto = texto_principal(resposta.content.decode())
    assert "Lucas Laboratorista" in texto


# ===========================================================================
# US5 (T042) — desativar e reativar usuário
#
# Contratos fixados pelos testes (ajustar AQUI se a implementação divergir):
# - `usuario_desativar`: GET mostra a confirmação (200, nada gravado); POST com `confirmar=1` e
#   `justificativa` (opcional) desativa e responde 302 para a ficha; sem `confirmar`, 200 sem
#   gravar;
# - `usuario_reativar`: GET mostra a revisão dos papéis preservados — `ROLE-REQUESTER` marcado e
#   TRAVADO (a caixa desabilitada, enviado por um campo oculto `papeis`, como em
#   `usuario_papeis`) e, na linha de cada papel que a reativação recusaria, o motivo de
#   `previa_reativacao(...).recusas`; POST `papeis` = o conjunto MANTIDO, com `confirmar=1`:
#   executa e 302 para a ficha; sem `confirmar` ou sem `ROLE-REQUESTER`, 200 sem gravar;
# - toda recusa: 200 com motivo e caminho da operação, dados preservados, nada gravado e nenhum
#   evento.
# ===========================================================================


def _campos(resposta, tipo, nome):
    """As tags `<input>` do tipo e nome dados."""
    achadas = []
    for tag in re.findall(r"<input\b[^>]*>", resposta.content.decode()):
        if re.search(rf"""type=["']{tipo}["']""", tag) and re.search(
            rf"""name=["']{nome}["']""", tag
        ):
            achadas.append(tag)
    return achadas


def _valor(tag):
    achado = re.search(r"""value=["']([^"']*)["']""", tag)
    return achado.group(1) if achado else ""


def _desativado(cenario, nome, matricula, papeis=()):
    """Usuário da ETA já desativado pela operação (papéis preservados)."""
    usuario = _pessoa(nome, matricula, cenario.eta, papeis)
    org.desativar_usuario(cenario.admin, usuario.pk)
    return User.objects.get(pk=usuario.pk)


@pytest.fixture
def ex_chefe(cenario):
    """Luiza era chefe do Laboratório (inativo): foi desativada e preservou `ROLE-SECTOR-HEAD`; o
    Laboratório já tem outro chefe (Lucas) e está ativo — reativá-la mantendo a chefia é
    recusado."""
    luiza = _pessoa("Luiza Ex-Chefe", "REA-LUIZA", cenario.lab)
    lucas = _pessoa("Lucas Novo Chefe", "REA-LUCAS", cenario.lab)
    org.designar_chefia(cenario.admin, cenario.lab.pk, luiza.pk)
    org.desativar_usuario(cenario.admin, luiza.pk)
    org.designar_chefia(cenario.admin, cenario.lab.pk, lucas.pk)
    org.provisionar_ativacao(cenario.lab)
    return User.objects.get(pk=luiza.pk)


# ---------------------------------------------------------------------------
# Desativação
# ---------------------------------------------------------------------------


def test_formulario_de_desativacao_mostra_quem_sera_desativado_e_nao_desativa(client, cenario):
    alvo = _pessoa("Paulo Desativável", "DES-100", cenario.eta, {Papel.AUDITOR})
    antes = foto_organizacao()

    resposta = client.get(rota("usuario_desativar", alvo.pk))

    assert resposta.status_code == 200
    assert "Paulo Desativável" in texto_principal(resposta.content.decode())
    assert foto_organizacao() == antes


def test_primeiro_envio_sem_confirmar_nao_desativa(client, cenario):
    alvo = _pessoa("Paulo Desativável", "DES-100", cenario.eta)
    antes = foto_organizacao()

    resposta = client.post(rota("usuario_desativar", alvo.pk), {"justificativa": "Já saiu"})

    assert resposta.status_code == 200
    assert foto_organizacao() == antes


def test_confirmacao_desativa_registra_a_justificativa_e_volta_a_ficha(client, cenario):
    alvo = _pessoa("Paulo Desativável", "DES-100", cenario.eta, {Papel.AUDITOR})

    resposta = client.post(
        rota("usuario_desativar", alvo.pk), {"confirmar": "1", "justificativa": "Aposentadoria"}
    )

    assert resposta.status_code == 302 and resposta.url == rota("usuario", alvo.pk)
    assert mensagens(resposta)
    alvo.refresh_from_db()
    assert alvo.is_active is False
    assert _papeis_atuais(alvo) == {Papel.REQUISITANTE, Papel.AUDITOR}, "papéis preservados"
    evento = EventoOrganizacional.objects.get(tipo=TipoEvento.USUARIO_DESATIVADO)
    assert evento.autor == cenario.admin and evento.usuario == alvo
    assert evento.justificativa == "Aposentadoria"


def test_a_justificativa_e_opcional_na_tela(client, cenario):
    alvo = _pessoa("Paulo Desativável", "DES-100", cenario.eta)

    resposta = client.post(rota("usuario_desativar", alvo.pk), {"confirmar": "1"})

    assert resposta.status_code == 302
    assert User.objects.get(pk=alvo.pk).is_active is False
    assert EventoOrganizacional.objects.get(tipo=TipoEvento.USUARIO_DESATIVADO).justificativa == ""


def test_a_sessao_aberta_do_desativado_perde_o_acesso_na_requisicao_seguinte(client, cenario):
    alvo = _pessoa("Paulo Desativável", "DES-100", cenario.eta)
    sessao = Client()
    sessao.force_login(alvo)
    assert sessao.get(rota("home")).status_code == 200

    client.post(rota("usuario_desativar", alvo.pk), {"confirmar": "1"})

    resposta = sessao.get(rota("home"))
    assert resposta.status_code == 302 and resposta.url.startswith(rota("login"))


@pytest.mark.parametrize("quem", ["chefe_de_setor_ativo", "propria_conta"])
def test_desativacao_recusada_mostra_motivo_e_caminho_e_nao_grava(client, cenario, quem):
    alvo = {"chefe_de_setor_ativo": cenario.chefe_eta, "propria_conta": cenario.admin}[quem]
    esperada = recusa_de(lambda: org.desativar_usuario(cenario.admin, alvo.pk))
    antes = foto_organizacao()

    resposta = client.post(rota("usuario_desativar", alvo.pk), {"confirmar": "1"})

    _recusa_na_tela(resposta, esperada)
    assert foto_organizacao() == antes
    assert User.objects.get(pk=alvo.pk).is_active is True


def test_desativar_conta_tecnica_ou_inexistente_responde_404_sem_gravar(
    client, cenario, superusuario_tecnico
):
    antes = foto_organizacao()

    for pk in (superusuario_tecnico.pk, 987_654_321):
        assert client.get(rota("usuario_desativar", pk)).status_code == 404
        assert client.post(rota("usuario_desativar", pk), {"confirmar": "1"}).status_code == 404
    assert foto_organizacao() == antes


def test_a_ficha_oferece_desativar_ao_ativo_e_reativar_ao_inativo(client, cenario):
    ativo = _pessoa("Paulo Ativo", "FIC-ATIVO", cenario.eta)
    inativo = _desativado(cenario, "Paula Inativa", "FIC-INAT")

    do_ativo = hrefs(client.get(rota("usuario", ativo.pk)).content.decode())
    do_inativo = hrefs(client.get(rota("usuario", inativo.pk)).content.decode())

    assert rota("usuario_desativar", ativo.pk) in do_ativo
    assert rota("usuario_reativar", ativo.pk) not in do_ativo
    assert rota("usuario_reativar", inativo.pk) in do_inativo
    assert rota("usuario_desativar", inativo.pk) not in do_inativo


# ---------------------------------------------------------------------------
# Reativação
# ---------------------------------------------------------------------------


def test_revisao_lista_os_papeis_preservados_e_trava_o_requisitante(client, cenario):
    alvo = _desativado(
        cenario, "Paulo Reativável", "REA-100", {Papel.AUDITOR, Papel.AUXILIAR_SETOR}
    )

    resposta = client.get(rota("usuario_reativar", alvo.pk))

    assert resposta.status_code == 200
    texto = texto_principal(resposta.content.decode())
    for papel in (Papel.REQUISITANTE, Papel.AUDITOR, Papel.AUXILIAR_SETOR):
        assert papel.label in texto, f"a revisão lista {papel.label}"
    for papel_ausente in (Papel.ADMINISTRADOR_SISTEMA, Papel.CHEFE_ALMOXARIFADO):
        assert papel_ausente.label not in texto, "só se revisa o que a conta tem"
    ocultos = [_valor(tag) for tag in _campos(resposta, "hidden", "papeis")]
    assert Papel.REQUISITANTE.value in ocultos, "ROLE-REQUESTER segue por um campo oculto"
    caixas = [t for t in _campos(resposta, "checkbox", "papeis") if _valor(t) == "ROLE-REQUESTER"]
    assert all("disabled" in tag for tag in caixas), "e a caixa dele está travada"


def _sem_requisitante(cenario, nome, matricula):
    """Conta desativada que depois perdeu `ROLE-REQUESTER` (remover o papel de conta inativa é
    permitido; reativar exige o papel)."""
    alvo = _desativado(cenario, nome, matricula, {Papel.AUDITOR})
    org.alterar_papeis(cenario.admin, alvo.pk, conceder=set(), remover={Papel.REQUISITANTE})
    return User.objects.get(pk=alvo.pk)


def test_revisao_de_conta_sem_requisitante_leva_a_tela_de_papeis_e_nao_oferece_o_envio(
    client, cenario
):
    alvo = _sem_requisitante(cenario, "Paulo Sem Requisitante", "REA-SEM")
    esperada = recusa_de(lambda: org.reativar_usuario(cenario.admin, alvo.pk, papeis_mantidos={}))

    resposta = client.get(rota("usuario_reativar", alvo.pk))

    assert resposta.status_code == 200
    corpo = resposta.content.decode()
    texto = texto_principal(corpo)
    assert "papel de requisitante na tela de papéis" in esperada.caminho
    assert re.sub(r"\s+", " ", esperada.motivo) in texto
    assert re.sub(r"\s+", " ", esperada.caminho) in texto
    assert rota("usuario_papeis", alvo.pk) in hrefs(corpo)
    botao = re.search(r"<button\b[^>]*data-processing-submit[^>]*>", corpo)
    assert botao and "disabled" in botao.group(0), "o envio que seria recusado não é oferecido"


def test_reativar_conta_sem_requisitante_por_post_mostra_o_caminho_e_nao_reativa(client, cenario):
    alvo = _sem_requisitante(cenario, "Paulo Sem Requisitante", "REA-SEM")
    esperada = recusa_de(
        lambda: org.reativar_usuario(
            cenario.admin, alvo.pk, papeis_mantidos={Papel.REQUISITANTE, Papel.AUDITOR}
        )
    )
    antes = foto_organizacao()

    resposta = client.post(
        rota("usuario_reativar", alvo.pk),
        {"confirmar": "1", "papeis": [Papel.REQUISITANTE.value, Papel.AUDITOR.value]},
    )

    assert resposta.status_code == 200
    assert re.sub(r"\s+", " ", esperada.caminho) in texto_principal(resposta.content.decode())
    assert foto_organizacao() == antes
    assert User.objects.get(pk=alvo.pk).is_active is False


def test_depois_de_conceder_o_requisitante_a_reativacao_volta_a_ser_oferecida(client, cenario):
    alvo = _sem_requisitante(cenario, "Paulo Sem Requisitante", "REA-SEM")

    concessao = client.post(
        rota("usuario_papeis", alvo.pk),
        {"papeis": [Papel.REQUISITANTE.value, Papel.AUDITOR.value]},
    )
    resposta = client.get(rota("usuario_reativar", alvo.pk))

    assert concessao.status_code == 302
    corpo = resposta.content.decode()
    assert rota("usuario_papeis", alvo.pk) not in hrefs(corpo)
    botao = re.search(r"<button\b[^>]*data-processing-submit[^>]*>", corpo)
    assert botao and "disabled" not in botao.group(0)


def test_a_revisao_nao_reativa_nem_grava_nada(client, cenario):
    alvo = _desativado(cenario, "Paulo Reativável", "REA-100", {Papel.AUDITOR})
    antes = foto_organizacao()

    client.get(rota("usuario_reativar", alvo.pk))

    assert foto_organizacao() == antes


def test_a_revisao_indica_na_linha_o_papel_que_seria_recusado_com_o_motivo(
    client, cenario, ex_chefe
):
    previa = org.previa_reativacao(ex_chefe.pk)

    resposta = client.get(rota("usuario_reativar", ex_chefe.pk))

    texto = texto_principal(resposta.content.decode())
    assert Papel.CHEFE_SETOR.label in texto
    assert re.sub(r"\s+", " ", previa.recusas[Papel.CHEFE_SETOR].motivo) in texto


def test_confirmacao_reativa_com_exatamente_os_papeis_confirmados(client, cenario):
    alvo = _desativado(
        cenario, "Paulo Reativável", "REA-100", {Papel.AUDITOR, Papel.AUXILIAR_SETOR}
    )
    mantidos = {Papel.REQUISITANTE, Papel.AUDITOR}  # desmarcou o auxiliar

    resposta = client.post(
        rota("usuario_reativar", alvo.pk), {"papeis": _codigos(mantidos), "confirmar": "1"}
    )

    assert resposta.status_code == 302 and resposta.url == rota("usuario", alvo.pk)
    assert mensagens(resposta)
    alvo.refresh_from_db()
    assert alvo.is_active is True
    assert _papeis_atuais(alvo) == mantidos
    evento = EventoOrganizacional.objects.get(tipo=TipoEvento.USUARIO_REATIVADO)
    assert evento.autor == cenario.admin and evento.usuario == alvo


def test_reativacao_sem_confirmar_volta_a_revisao_sem_gravar(client, cenario):
    alvo = _desativado(cenario, "Paulo Reativável", "REA-100", {Papel.AUDITOR})
    antes = foto_organizacao()

    resposta = client.post(
        rota("usuario_reativar", alvo.pk),
        {"papeis": _codigos({Papel.REQUISITANTE, Papel.AUDITOR})},
    )

    assert resposta.status_code == 200
    assert foto_organizacao() == antes


def test_desmarcar_o_requisitante_nao_e_aceito_nem_com_post_direto(client, cenario):
    alvo = _desativado(cenario, "Paulo Reativável", "REA-100", {Papel.AUDITOR})
    antes = foto_organizacao()

    resposta = client.post(
        rota("usuario_reativar", alvo.pk), {"papeis": [Papel.AUDITOR.value], "confirmar": "1"}
    )

    assert resposta.status_code == 200
    assert foto_organizacao() == antes
    assert User.objects.get(pk=alvo.pk).is_active is False


def test_papel_mantido_que_violaria_regra_e_recusado_com_o_motivo_e_nao_grava(
    client, cenario, ex_chefe
):
    mantidos = {Papel.REQUISITANTE, Papel.CHEFE_SETOR}
    esperada = recusa_de(
        lambda: org.reativar_usuario(cenario.admin, ex_chefe.pk, papeis_mantidos=mantidos)
    )
    antes = foto_organizacao()

    resposta = client.post(
        rota("usuario_reativar", ex_chefe.pk), {"papeis": _codigos(mantidos), "confirmar": "1"}
    )

    _recusa_na_tela(resposta, esperada)
    assert foto_organizacao() == antes
    assert User.objects.get(pk=ex_chefe.pk).is_active is False


def test_desmarcando_o_papel_recusado_a_reativacao_prossegue(client, cenario, ex_chefe):
    resposta = client.post(
        rota("usuario_reativar", ex_chefe.pk),
        {"papeis": [Papel.REQUISITANTE.value], "confirmar": "1"},
    )

    assert resposta.status_code == 302
    ex_chefe.refresh_from_db()
    assert ex_chefe.is_active is True and _papeis_atuais(ex_chefe) == {Papel.REQUISITANTE}


def test_codigo_de_papel_desconhecido_na_reativacao_e_recusado_sem_gravar(client, cenario):
    alvo = _desativado(cenario, "Paulo Reativável", "REA-100")
    antes = foto_organizacao()

    resposta = client.post(
        rota("usuario_reativar", alvo.pk),
        {"papeis": [Papel.REQUISITANTE.value, "ROLE-INEXISTENTE"], "confirmar": "1"},
    )

    assert resposta.status_code == 200
    assert foto_organizacao() == antes


def test_reativacao_nao_concede_papel_que_a_conta_nao_tinha(client, cenario):
    """POST direto "mantendo" `ROLE-SYSTEM-ADMIN` numa conta que nunca o teve: nunca é concedido."""
    alvo = _desativado(cenario, "Paulo Reativável", "REA-100", {Papel.AUDITOR})

    client.post(
        rota("usuario_reativar", alvo.pk),
        {
            "papeis": [
                Papel.REQUISITANTE.value,
                Papel.AUDITOR.value,
                Papel.ADMINISTRADOR_SISTEMA.value,
            ],
            "confirmar": "1",
        },
    )

    assert Papel.ADMINISTRADOR_SISTEMA not in _papeis_atuais(alvo)


def test_reativar_conta_tecnica_ou_inexistente_responde_404_sem_gravar(
    client, cenario, superusuario_tecnico
):
    antes = foto_organizacao()

    for pk in (superusuario_tecnico.pk, 987_654_321):
        assert client.get(rota("usuario_reativar", pk)).status_code == 404
        corpo = {"papeis": [Papel.REQUISITANTE.value], "confirmar": "1"}
        assert client.post(rota("usuario_reativar", pk), corpo).status_code == 404
    assert foto_organizacao() == antes


# ===========================================================================
# US6 (T047) — redefinição da senha de terceiros e `/senha/` definitivo
#
# Contratos fixados pelos testes (ajustar AQUI se a implementação divergir):
# - `usuario_redefinir_senha`: GET mostra a confirmação, com `chave_confirmacao` nova; POST com a
#   chave: 200 com a senha provisória, `Cache-Control: no-store` e nunca redirect; repetir o POST →
#   aviso de "já executada" e 302 para a ficha, sem senha; chave ausente ou inválida → 200 com uma
#   chave nova, sem redefinir;
# - `/senha/` com credencial definitiva: `old_password`, `new_password1`, `new_password2`; sucesso →
#   302 para a Home com a mensagem "Senha alterada."; a barra de trabalho traz o link "Senha".
# ===========================================================================


@pytest.fixture
def alvo_da_senha(cenario):
    return _pessoa("Rita Redefinição", "RED-100", cenario.eta)


def test_formulario_de_redefinicao_traz_chave_nova_e_nao_redefine(client, cenario, alvo_da_senha):
    antes = foto_organizacao()

    primeira = client.get(rota("usuario_redefinir_senha", alvo_da_senha.pk))
    segunda = client.get(rota("usuario_redefinir_senha", alvo_da_senha.pk))

    assert primeira.status_code == 200
    assert "Rita Redefinição" in texto_principal(primeira.content.decode())
    assert chave_do_formulario(primeira) != chave_do_formulario(segunda)
    assert foto_organizacao() == antes


def test_redefinicao_responde_200_com_a_senha_no_store_e_nunca_redireciona(
    client, cenario, alvo_da_senha, monkeypatch
):
    senha = fixar_senha_gerada(monkeypatch)
    chave = chave_do_formulario(client.get(rota("usuario_redefinir_senha", alvo_da_senha.pk)))

    resposta = client.post(
        rota("usuario_redefinir_senha", alvo_da_senha.pk), {"chave_confirmacao": str(chave)}
    )

    assert resposta.status_code == 200
    assert not resposta.has_header("Location")
    assert "no-store" in resposta["Cache-Control"]
    conteudo = resposta.content.decode()
    assert senha in conteudo
    assert rota("usuario", alvo_da_senha.pk) in conteudo, "e o caminho de volta à ficha"
    alvo_da_senha.refresh_from_db()
    assert alvo_da_senha.check_password(senha) and alvo_da_senha.senha_provisoria_em is not None
    evento = EventoOrganizacional.objects.get(
        tipo=TipoEvento.SENHA_PROVISORIA_GERADA, usuario=alvo_da_senha, chave_confirmacao=chave
    )
    assert evento.autor == cenario.admin


def test_repetir_a_redefinicao_avisa_ja_executada_e_leva_a_ficha_sem_senha(
    client, cenario, alvo_da_senha, monkeypatch
):
    senha = fixar_senha_gerada(monkeypatch)
    chave = chave_do_formulario(client.get(rota("usuario_redefinir_senha", alvo_da_senha.pk)))
    corpo = {"chave_confirmacao": str(chave)}
    client.post(rota("usuario_redefinir_senha", alvo_da_senha.pk), corpo)
    hash_antes = User.objects.get(pk=alvo_da_senha.pk).password

    repetido = client.post(rota("usuario_redefinir_senha", alvo_da_senha.pk), corpo)

    assert repetido.status_code == 302 and repetido.url == rota("usuario", alvo_da_senha.pk)
    assert senha not in repetido.content.decode()
    assert MENSAGEM_JA_EXECUTADA in mensagens(repetido)
    assert User.objects.get(pk=alvo_da_senha.pk).password == hash_antes
    assert (
        EventoOrganizacional.objects.filter(
            tipo=TipoEvento.SENHA_PROVISORIA_GERADA, usuario=alvo_da_senha, chave_confirmacao=chave
        ).count()
        == 1
    )


@pytest.mark.parametrize(
    "corpo",
    [
        pytest.param({}, id="sem-chave"),
        pytest.param({"chave_confirmacao": "nao-e-uuid"}, id="chave-invalida"),
    ],
)
def test_redefinicao_sem_chave_valida_nao_redefine_e_volta_com_chave_nova(
    client, cenario, alvo_da_senha, monkeypatch, corpo
):
    senha = fixar_senha_gerada(monkeypatch)
    antes = foto_organizacao()

    resposta = client.post(rota("usuario_redefinir_senha", alvo_da_senha.pk), corpo)

    assert resposta.status_code == 200
    assert senha not in resposta.content.decode()
    assert foto_organizacao() == antes
    nova = chave_do_formulario(resposta)
    aceita = client.post(
        rota("usuario_redefinir_senha", alvo_da_senha.pk), {"chave_confirmacao": str(nova)}
    )
    assert aceita.status_code == 200 and senha in aceita.content.decode()


def test_a_senha_redefinida_nao_aparece_na_ficha_em_mensagem_sessao_evento_nem_log(
    client, cenario, alvo_da_senha, monkeypatch, caplog
):
    caplog.set_level(logging.DEBUG)
    senha = fixar_senha_gerada(monkeypatch)
    chave = chave_do_formulario(client.get(rota("usuario_redefinir_senha", alvo_da_senha.pk)))
    resposta = client.post(
        rota("usuario_redefinir_senha", alvo_da_senha.pk), {"chave_confirmacao": str(chave)}
    )
    assert senha in resposta.content.decode()

    ficha = client.get(rota("usuario", alvo_da_senha.pk))

    assert senha not in ficha.content.decode()
    assert "Provisória" in texto_visivel(ficha.content.decode()), "a ficha mostra a provisória"
    for r in (resposta, ficha):
        assert all(senha not in texto for texto in mensagens(r))
    sessoes = " ".join(str(s.get_decoded()) + s.session_data for s in Session.objects.all())
    assert senha not in sessoes and senha not in caplog.text
    for evento in EventoOrganizacional.objects.all():
        assert senha not in f"{evento.dados} {evento.justificativa}"


def test_a_redefinicao_encerra_a_sessao_do_alvo(client, cenario, alvo_da_senha):
    sessao = Client()
    sessao.force_login(alvo_da_senha)
    assert sessao.get(rota("home")).status_code == 200
    chave = chave_do_formulario(client.get(rota("usuario_redefinir_senha", alvo_da_senha.pk)))

    client.post(
        rota("usuario_redefinir_senha", alvo_da_senha.pk), {"chave_confirmacao": str(chave)}
    )

    resposta = sessao.get(rota("home"))
    assert resposta.status_code == 302 and resposta.url.startswith(rota("login"))


def test_o_administrador_que_redefine_a_propria_senha_perde_a_sessao(client, cenario):
    chave = chave_do_formulario(client.get(rota("usuario_redefinir_senha", cenario.admin.pk)))

    resposta = client.post(
        rota("usuario_redefinir_senha", cenario.admin.pk), {"chave_confirmacao": str(chave)}
    )

    assert resposta.status_code == 200 and "no-store" in resposta["Cache-Control"]
    seguinte = client.get(rota("home"))
    assert seguinte.status_code == 302 and seguinte.url.startswith(rota("login"))


def test_redefinir_conta_tecnica_ou_inexistente_responde_404_sem_gravar(
    client, cenario, superusuario_tecnico
):
    antes = foto_organizacao()

    for pk in (superusuario_tecnico.pk, 987_654_321):
        assert client.get(rota("usuario_redefinir_senha", pk)).status_code == 404
        corpo = {"chave_confirmacao": str(uuid.uuid4())}
        assert client.post(rota("usuario_redefinir_senha", pk), corpo).status_code == 404
    assert foto_organizacao() == antes


def test_a_ficha_oferece_a_redefinicao_de_senha(client, cenario, alvo_da_senha):
    ficha = client.get(rota("usuario", alvo_da_senha.pk))

    assert rota("usuario_redefinir_senha", alvo_da_senha.pk) in hrefs(ficha.content.decode())


# ---------------------------------------------------------------------------
# `/senha/` no estado definitivo (troca voluntária)
# ---------------------------------------------------------------------------


@pytest.fixture
def definitivo():
    """Conta com senha definitiva, autenticada num cliente próprio (o `client` do cenário é o do
    administrador)."""
    setor = org.provisionar_setor("Setor da Troca")
    usuario = membro(setor, "TROCA-100")
    sessao = Client()
    sessao.force_login(usuario)
    return SimpleNamespace(usuario=usuario, sessao=sessao)


def _troca_de_senha(atual=SENHA_TESTE, nova="Cavalo-Azul-Distante-4718", confirmacao=None):
    return {
        "old_password": atual,
        "new_password1": nova,
        "new_password2": nova if confirmacao is None else confirmacao,
    }


def test_troca_voluntaria_valida_volta_a_home_com_a_mensagem_senha_alterada(definitivo):
    resposta = definitivo.sessao.post(rota("definir_senha"), _troca_de_senha())

    assert resposta.status_code == 302 and resposta.url == rota("home")
    assert "Senha alterada." in mensagens(resposta)
    usuario = User.objects.get(pk=definitivo.usuario.pk)
    assert usuario.check_password("Cavalo-Azul-Distante-4718")
    assert definitivo.sessao.get(rota("home")).status_code == 200, "a sessão em uso continua"


@pytest.mark.parametrize(
    "corpo",
    [
        pytest.param(_troca_de_senha(atual="errada-errada-1"), id="senha-atual-errada"),
        pytest.param(_troca_de_senha(nova="qwertyuiop"), id="fora-da-politica"),
        pytest.param(_troca_de_senha(confirmacao="Outra-Coisa-9999"), id="confirmacao-diferente"),
    ],
)
def test_troca_recusada_re_renderiza_com_200_e_nao_muda_nada(definitivo, corpo):
    antes = foto_organizacao()

    resposta = definitivo.sessao.post(rota("definir_senha"), corpo)

    assert resposta.status_code == 200
    assert foto_organizacao() == antes
    assert User.objects.get(pk=definitivo.usuario.pk).check_password(SENHA_TESTE)
    assert "Senha alterada." not in mensagens(resposta)


def test_a_pagina_de_troca_nao_mostra_a_senha_em_lugar_nenhum(definitivo):
    resposta = definitivo.sessao.post(
        rota("definir_senha"), _troca_de_senha(atual="errada-errada-1")
    )

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "errada-errada-1" not in conteudo, "a senha digitada não volta preenchida na tela"
    assert "Cavalo-Azul-Distante-4718" not in conteudo


def test_a_barra_de_trabalho_traz_o_link_senha_para_todo_autenticado(definitivo):
    """T049: ao lado de "Sair", visível a todo usuário autenticado, em qualquer tela com barra."""
    for destino in (rota("home"), rota("catalogo:consulta")):
        conteudo = definitivo.sessao.get(destino).content.decode()

        assert rota("definir_senha") in hrefs(conteudo), destino
        assert "Senha" in texto_visivel(conteudo) and "Sair" in texto_visivel(conteudo)


# ===========================================================================
# US7 (T051) — setores: criar, editar, ativar e desativar
#
# Contratos fixados pelos testes (ajustar AQUI se a implementação divergir):
# - `setor_novo` e `setor_editar`: POST `nome`; sucesso → 302 para a ficha do setor;
# - `setor_ativar` e `setor_desativar`: GET mostra a confirmação (200, nada gravado); POST com
#   `confirmar=1` executa e 302 para a ficha; sem `confirmar`, 200 sem gravar;
# - o Almoxarifado ativado não oferece a ação de desativar (a ficha não traz o link) e o servidor
#   recusa mesmo assim, com POST direto;
# - toda recusa: 200 com motivo e caminho da operação, dados preservados, nada gravado.
# ===========================================================================


def _setor_solo(nome="Solo", matricula="solo-chefe"):
    setor, chefe = setor_ativo(nome, matricula)
    return setor, chefe


def test_formulario_de_novo_setor_traz_o_campo_nome(client, cenario):
    resposta = client.get(rota("setor_novo"))

    assert resposta.status_code == 200
    assert 'name="nome"' in resposta.content.decode()


def test_criacao_valida_cria_o_setor_inativo_e_leva_a_ficha(client, cenario):
    resposta = client.post(rota("setor_novo"), {"nome": "  Compras  "})

    novo = Setor.objects.get(nome="Compras")
    assert resposta.status_code == 302 and resposta.url == rota("setor", novo.pk)
    assert mensagens(resposta)
    assert novo.ativo is False and novo.almoxarifado is False
    evento = EventoOrganizacional.objects.get(tipo=TipoEvento.SETOR_CRIADO, setor=novo)
    assert evento.autor == cenario.admin


@pytest.mark.parametrize(
    "nome",
    [
        pytest.param(" eta ", id="repetido-sem-caixa-nem-espacos"),
        pytest.param("   ", id="so-espacos"),
        pytest.param("", id="vazio"),
        pytest.param("x" * 101, id="maior-que-o-limite"),
    ],
)
def test_criacao_recusada_re_renderiza_com_200_e_nao_grava(client, cenario, nome):
    antes = foto_organizacao()

    resposta = client.post(rota("setor_novo"), {"nome": nome})

    assert resposta.status_code == 200
    assert foto_organizacao() == antes


def test_criacao_com_nome_repetido_mostra_o_motivo_da_operacao_e_preserva_o_digitado(
    client, cenario
):
    esperada = recusa_de(lambda: org.criar_setor(cenario.admin, nome="eta"))

    resposta = client.post(rota("setor_novo"), {"nome": "eta"})

    _recusa_na_tela(resposta, esperada)
    assert 'value="eta"' in resposta.content.decode(), "o nome digitado é preservado"


def test_formulario_de_edicao_traz_o_nome_atual(client, cenario):
    resposta = client.get(rota("setor_editar", cenario.lab.pk))

    assert resposta.status_code == 200
    assert "Laboratório" in resposta.content.decode()


def test_renomeacao_valida_grava_registra_o_evento_e_volta_a_ficha_do_setor(client, cenario):
    resposta = client.post(rota("setor_editar", cenario.lab.pk), {"nome": "Laboratório Central"})

    assert resposta.status_code == 302 and resposta.url == rota("setor", cenario.lab.pk)
    assert mensagens(resposta)
    cenario.lab.refresh_from_db()
    assert cenario.lab.nome == "Laboratório Central"
    evento = EventoOrganizacional.objects.get(tipo=TipoEvento.SETOR_RENOMEADO)
    assert evento.autor == cenario.admin and evento.setor == cenario.lab


def test_renomeacao_sem_mudanca_volta_a_ficha_sem_gerar_evento(client, cenario):
    antes = foto_organizacao()

    resposta = client.post(rota("setor_editar", cenario.lab.pk), {"nome": " Laboratório "})

    assert resposta.status_code == 302 and resposta.url == rota("setor", cenario.lab.pk)
    assert foto_organizacao() == antes


def test_renomeacao_para_nome_de_outro_setor_mostra_o_motivo_e_nao_grava(client, cenario):
    esperada = recusa_de(lambda: org.renomear_setor(cenario.admin, cenario.lab.pk, nome=" ETA "))
    antes = foto_organizacao()

    resposta = client.post(rota("setor_editar", cenario.lab.pk), {"nome": " ETA "})

    _recusa_na_tela(resposta, esperada)
    assert foto_organizacao() == antes


def test_editar_setor_inexistente_responde_404(client, cenario):
    assert client.get(rota("setor_editar", 987_654_321)).status_code == 404
    assert client.post(rota("setor_editar", 987_654_321), {"nome": "X"}).status_code == 404


# ---------------------------------------------------------------------------
# Ativação
# ---------------------------------------------------------------------------


@pytest.fixture
def lab_pronto(cenario):
    """O Laboratório (inativo) com a chefia já designada: pronto para ser ativado."""
    luiza = _pessoa("Luiza Laboratorista", "SET-LUIZA", cenario.lab)
    org.designar_chefia(cenario.admin, cenario.lab.pk, luiza.pk)
    return luiza


def test_confirmacao_de_ativacao_mostra_o_setor_e_nao_ativa(client, cenario, lab_pronto):
    antes = foto_organizacao()

    resposta = client.get(rota("setor_ativar", cenario.lab.pk))

    assert resposta.status_code == 200
    assert "Laboratório" in texto_principal(resposta.content.decode())
    assert foto_organizacao() == antes


def test_ativacao_sem_confirmar_nao_ativa(client, cenario, lab_pronto):
    antes = foto_organizacao()

    resposta = client.post(rota("setor_ativar", cenario.lab.pk), {})

    assert resposta.status_code == 200
    assert foto_organizacao() == antes


def test_ativacao_confirmada_ativa_e_volta_a_ficha(client, cenario, lab_pronto):
    resposta = client.post(rota("setor_ativar", cenario.lab.pk), {"confirmar": "1"})

    assert resposta.status_code == 302 and resposta.url == rota("setor", cenario.lab.pk)
    assert mensagens(resposta)
    cenario.lab.refresh_from_db()
    assert cenario.lab.ativo is True and cenario.lab.ativado_em is not None
    evento = EventoOrganizacional.objects.get(tipo=TipoEvento.SETOR_ATIVADO, setor=cenario.lab)
    assert evento.autor == cenario.admin


def test_ativacao_sem_chefe_mostra_motivo_e_caminho_e_nao_grava(client, cenario):
    esperada = recusa_de(lambda: org.ativar_setor(cenario.admin, cenario.lab.pk))
    antes = foto_organizacao()

    resposta = client.post(rota("setor_ativar", cenario.lab.pk), {"confirmar": "1"})

    _recusa_na_tela(resposta, esperada)
    assert foto_organizacao() == antes
    cenario.lab.refresh_from_db()
    assert cenario.lab.ativo is False


# ---------------------------------------------------------------------------
# Desativação
# ---------------------------------------------------------------------------


def test_confirmacao_de_desativacao_de_setor_mostra_o_setor_e_nao_desativa(client, cenario):
    solo, _ = _setor_solo()
    antes = foto_organizacao()

    resposta = client.get(rota("setor_desativar", solo.pk))

    assert resposta.status_code == 200
    assert "Solo" in texto_principal(resposta.content.decode())
    assert foto_organizacao() == antes


def test_desativacao_de_setor_sem_confirmar_nao_desativa(client, cenario):
    solo, _ = _setor_solo()
    antes = foto_organizacao()

    resposta = client.post(rota("setor_desativar", solo.pk), {})

    assert resposta.status_code == 200
    assert foto_organizacao() == antes


def test_desativacao_de_setor_confirmada_desativa_e_volta_a_ficha(client, cenario):
    solo, chefe = _setor_solo()

    resposta = client.post(rota("setor_desativar", solo.pk), {"confirmar": "1"})

    assert resposta.status_code == 302 and resposta.url == rota("setor", solo.pk)
    assert mensagens(resposta)
    solo.refresh_from_db()
    assert solo.ativo is False
    assert _papeis_atuais(chefe) >= {Papel.CHEFE_SETOR}, "o chefe mantém a chefia"
    evento = EventoOrganizacional.objects.get(tipo=TipoEvento.SETOR_DESATIVADO, setor=solo)
    assert evento.autor == cenario.admin


def test_desativacao_com_outros_membros_ativos_lista_os_membros_e_nao_grava(client, cenario):
    """A ETA tem o chefe e dois membros ativos; a recusa — com o motivo da operação, que os
    lista — chega à tela."""
    pedro = _pessoa("Pedro Membro Ativo", "SET-PEDRO", cenario.eta)
    paula = _pessoa("Paula Membro Ativa", "SET-PAULA", cenario.eta)
    esperada = recusa_de(lambda: org.desativar_setor(cenario.admin, cenario.eta.pk))
    antes = foto_organizacao()

    resposta = client.post(rota("setor_desativar", cenario.eta.pk), {"confirmar": "1"})

    _recusa_na_tela(resposta, esperada)
    texto = texto_principal(resposta.content.decode())
    assert all(p.nome in texto or p.matricula in texto for p in (pedro, paula))
    assert foto_organizacao() == antes
    assert Setor.objects.get(pk=cenario.eta.pk).ativo is True


def test_o_almoxarifado_ativado_nao_oferece_a_desativacao_e_o_servidor_a_recusa(client, cenario):
    _chefe_do_almoxarifado_ativo(cenario)
    esperada = recusa_de(lambda: org.desativar_setor(cenario.admin, cenario.almoxarifado.pk))
    antes = foto_organizacao()

    ficha = client.get(rota("setor", cenario.almoxarifado.pk))
    resposta = client.post(rota("setor_desativar", cenario.almoxarifado.pk), {"confirmar": "1"})

    assert ficha.status_code == 200
    assert rota("setor_desativar", cenario.almoxarifado.pk) not in hrefs(ficha.content.decode())
    _recusa_na_tela(resposta, esperada)
    assert foto_organizacao() == antes
    assert Setor.objects.get(pk=cenario.almoxarifado.pk).ativo is True


def test_desativar_ou_ativar_setor_inexistente_responde_404(client, cenario):
    for nome in ("setor_ativar", "setor_desativar"):
        assert client.get(rota(nome, 987_654_321)).status_code == 404
        assert client.post(rota(nome, 987_654_321), {"confirmar": "1"}).status_code == 404


# ---------------------------------------------------------------------------
# Ações oferecidas na ficha e na lista de setores
# ---------------------------------------------------------------------------


def test_a_ficha_oferece_ativar_ao_inativo_desativar_ao_ativo_e_sempre_editar(
    client, cenario, lab_pronto
):
    do_inativo = hrefs(client.get(rota("setor", cenario.lab.pk)).content.decode())
    do_ativo = hrefs(client.get(rota("setor", cenario.eta.pk)).content.decode())

    assert rota("setor_ativar", cenario.lab.pk) in do_inativo
    assert rota("setor_desativar", cenario.lab.pk) not in do_inativo
    assert rota("setor_desativar", cenario.eta.pk) in do_ativo
    assert rota("setor_ativar", cenario.eta.pk) not in do_ativo
    for links, setor in ((do_inativo, cenario.lab), (do_ativo, cenario.eta)):
        assert rota("setor_editar", setor.pk) in links


def test_a_lista_de_setores_oferece_criar_setor(client, cenario):
    resposta = client.get(rota("setores"))

    assert rota("setor_novo") in hrefs(resposta.content.decode())


# ===========================================================================
# Respostas comuns às operações (contracts/rotas-e-autorizacao.md)
# ===========================================================================


def _inativar(cenario, usuario):
    """Desativa `usuario` pela operação e o devolve (para as telas que partem de uma conta
    inativa)."""
    org.desativar_usuario(cenario.admin, usuario.pk)
    return usuario


@pytest.mark.parametrize(
    "chave",
    [pytest.param(None, id="sem-chave"), pytest.param("nao-e-uuid", id="chave-invalida")],
)
def test_cadastro_com_chave_ausente_ou_invalida_volta_com_uma_chave_nova(client, cenario, chave):
    """O reenvio da mesma tela nunca conserta uma chave ruim: o formulário volta com uma chave
    válida e os dados digitados, e o envio seguinte é aceito."""
    dados = dados_do_cadastro(cenario.eta)
    if chave is None:
        del dados["chave_confirmacao"]
    else:
        dados["chave_confirmacao"] = chave

    resposta = client.post(rota("usuario_novo"), dados)

    assert resposta.status_code == 200
    assert "NOVO-0001" in resposta.content.decode()
    nova = chave_do_formulario(resposta)
    reenvio = client.post(
        rota("usuario_novo"), dados_do_cadastro(cenario.eta, chave_confirmacao=str(nova))
    )
    assert reenvio.status_code == 200 and User.objects.filter(matricula="NOVO-0001").exists()


@pytest.mark.parametrize(
    "rota_e_dados",
    [
        pytest.param(
            lambda c, a: (
                rota("usuario_novo"),
                dados_do_cadastro(c.eta),
                "contas.views.cadastrar_usuario",
            ),
            id="cadastro",
        ),
        pytest.param(
            lambda c, a: (
                rota("usuario_editar", a.pk),
                {"nome": "Outro Nome", "matricula": "ERR-NOVA"},
                "contas.views.editar_usuario",
            ),
            id="edicao",
        ),
        pytest.param(
            lambda c, a: (
                rota("usuario_papeis", a.pk),
                {"papeis": [Papel.REQUISITANTE.value, Papel.AUDITOR.value]},
                "contas.views.alterar_papeis",
            ),
            id="papeis",
        ),
        pytest.param(
            lambda c, a: (
                rota("usuario_transferir", a.pk),
                {"setor": c.lab.pk, "confirmar": "1"},
                "contas.views.transferir_usuario",
            ),
            id="transferencia",
        ),
        pytest.param(
            lambda c, a: (
                rota("setor_chefia", c.eta.pk),
                {"novo_chefe": a.pk, "confirmar": "1", "chefe_esperado": c.chefe_eta.pk},
                "contas.views.substituir_chefia",
            ),
            id="substituicao-de-chefia",
        ),
        pytest.param(
            lambda c, a: (
                rota("usuario_desativar", a.pk),
                {"confirmar": "1"},
                "contas.views.desativar_usuario",
            ),
            id="desativacao",
        ),
        pytest.param(
            lambda c, a: (
                rota("usuario_reativar", _inativar(c, a).pk),
                {"papeis": [Papel.REQUISITANTE.value], "confirmar": "1"},
                "contas.views.reativar_usuario",
            ),
            id="reativacao",
        ),
        pytest.param(
            lambda c, a: (
                rota("usuario_redefinir_senha", a.pk),
                {"chave_confirmacao": str(uuid.uuid4())},
                "contas.views.redefinir_senha",
            ),
            id="redefinicao-de-senha",
        ),
        pytest.param(
            lambda c, a: (
                rota("setor_novo"),
                {"nome": "Setor Do Erro"},
                "contas.views.criar_setor",
            ),
            id="criacao-de-setor",
        ),
        pytest.param(
            lambda c, a: (
                rota("setor_editar", c.lab.pk),
                {"nome": "Outro Nome De Setor"},
                "contas.views.renomear_setor",
            ),
            id="renomeacao-de-setor",
        ),
        pytest.param(
            lambda c, a: (
                rota("setor_ativar", c.lab.pk),
                {"confirmar": "1"},
                "contas.views.ativar_setor",
            ),
            id="ativacao-de-setor",
        ),
        pytest.param(
            lambda c, a: (
                rota("setor_desativar", c.eta.pk),
                {"confirmar": "1"},
                "contas.views.desativar_setor",
            ),
            id="desativacao-de-setor",
        ),
    ],
)
def test_erro_inesperado_registra_o_traceback_mostra_alerta_generico_e_nao_grava(
    client, cenario, monkeypatch, caplog, rota_e_dados
):
    alvo = _pessoa("Pessoa Do Erro", "ERR-001", cenario.eta)
    destino, dados, operacao_com_falha = rota_e_dados(cenario, alvo)

    def _falha(*args, **kwargs):
        raise RuntimeError("falha-simulada-inesperada")

    monkeypatch.setattr(operacao_com_falha, _falha)
    antes = foto_organizacao()

    resposta = client.post(destino, dados)

    assert resposta.status_code == 200
    texto = texto_visivel(resposta.content.decode())
    assert "Nada foi gravado" in texto
    assert "falha-simulada-inesperada" not in texto, "o alerta é genérico: sem detalhe interno"
    assert "Traceback" in caplog.text and "falha-simulada-inesperada" in caplog.text
    assert foto_organizacao() == antes


def test_retirada_sem_o_estado_visto_nao_executa(client, cenario, lab_com_chefe):
    """A retirada é acionada só por `confirmar`: sem o estado que a tela mostrou, nada muda."""
    antes = foto_organizacao()

    resposta = client.post(rota("setor_chefia", cenario.lab.pk), {"confirmar": "1"})

    assert resposta.status_code == 200
    assert resposta.context["recusa"].caminho
    assert foto_organizacao() == antes


def test_confirmacao_de_substituicao_com_o_setor_ja_em_retirada_nao_retira_a_chefia(
    client, cenario, lab_com_chefe
):
    """A prévia de substituição foi aberta com o setor ativo; quando o setor passou ao estado de
    retirada (inativo, com chefe), confirmá-la não pode executar a retirada (FR-049)."""
    antes = foto_organizacao()

    resposta = client.post(
        rota("setor_chefia", cenario.lab.pk),
        {
            "estado": "substituir",
            "novo_chefe": lab_com_chefe.pk,
            "confirmar": "1",
            "chefe_esperado": lab_com_chefe.pk,
        },
    )

    assert resposta.status_code == 200
    assert resposta.context["estado"] == "retirar"
    assert resposta.context["recusa"].motivo
    assert foto_organizacao() == antes
    assert _chefes(cenario.lab) == [lab_com_chefe.pk]
