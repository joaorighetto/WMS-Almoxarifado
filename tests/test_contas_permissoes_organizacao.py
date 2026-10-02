"""Autorização das rotas de administração da organização (`/organizacao/`) — T019 (US1:
`usuario_novo`, `usuario`), T027 (US2: `usuarios`, `setores`, `setor`), T032, T037, T042 (US5:
`usuario_desativar`, `usuario_reativar`, FR-052), T047 (US6: `usuario_redefinir_senha` e a rota
`definir_senha`) e T051 (US7: `setor_novo`, `setor_editar`, `setor_ativar`, `setor_desativar`).
`PERM-USER-MANAGE`, `PERM-SECTOR-MANAGE`, `INV-AUTH-001`, FR-001, FR-002, FR-004, FR-032, FR-039,
FR-052.

COMO ACRESCENTAR UMA ROTA: acrescente UMA linha a `ROTAS_ORGANIZACAO`:

    pytest.param("usuario_editar", "post", "usuario", _payload, (302,), id="usuario_editar-post")

- 1º: nome da rota (como em `rota(...)`, com ou sem namespace);
- 2º: método;
- 3º: alvo do `<pk>` — `None` ou um atributo da fixture `alvos`: `"usuario"` (ativo), `"inativo"`
  (usuário inativo, para a reativação), `"setor"` (ativo, com chefe e um membro), `"setor_pronto"`
  (inativo com chefe, pronto para ativar) ou `"setor_solo"` (ativo, só o chefe, pronto para
  desativar);
- 4º: `None` ou uma função `alvos -> dict` com o corpo do POST. Use um corpo VÁLIDO e perigoso
  (que, sem a autorização, GRAVARIA): é ele que prova que o 403 impediu a escrita;
- 5º: status aceitos quando o administrador executa a rota.

Cada linha entra sozinha em todos os testes genéricos abaixo: anônimo, inativo, administrador com
credencial provisória, os papéis sem `ROLE-SYSTEM-ADMIN`, `<pk>` inexistente e conta técnica. Um
teste guarda a completude: toda rota registrada sob `/organizacao/` precisa estar nesta tabela —
esquecer de testar uma rota nova derruba o teste.

O que este módulo protege, em ordem de consequência:

- só identidade de negócio ATIVA com `ROLE-SYSTEM-ADMIN` executa ou consulta (a conta técnica,
  mesmo superusuária, não; o auditor, nem o chefe do almoxarifado, nem outro papel);
- recusa por papel é SEMPRE 403 e NUNCA grava `User`, `Setor`, `PapelUsuario` nem
  `EventoOrganizacional` — inclusive no POST direto, sem passar pela tela, com um corpo que
  concederia `ROLE-SYSTEM-ADMIN` ao próprio chamador (escalada de privilégio);
- a checagem de papel vem ANTES da existência do `<pk>`: quem não é administrador recebe 403 mesmo
  para `<pk>` inexistente (a recusa não revela quem existe); o administrador recebe 404 para
  inexistente e para a conta técnica (FR-004);
- anônimo e conta inativa são tratados como anônimos (login); administrador com credencial
  provisória só alcança `/senha/` (FR-032);
- `ROLE-SYSTEM-ADMIN` não concede nenhum poder operacional (FR-003, SC-008);
- quem perde `ROLE-SYSTEM-ADMIN` perde o acesso na PRÓXIMA requisição, na mesma sessão (FR-052);
- `/senha/` (`definir_senha`) é mecânica de autenticação: todo autenticado ativo, sem papel
  (FR-039); anônimo e conta inativa vão ao login.
"""

import uuid
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from django.test import Client
from django.urls import get_resolver, reverse

from contas import organizacao as org
from contas.models import Papel, User
from tests.contas_helpers import (
    dados_do_cadastro,
    foto_organizacao,
    membro,
    membro_provisorio,
    operacao,
    rota,
    setor_ativo,
)

pytestmark = pytest.mark.django_db

PREFIXO_ORGANIZACAO = "organizacao/"
PK_INEXISTENTE = 987_654_321


def _payload_cadastro(alvos):
    """Cadastro VÁLIDO que, sem a autorização, criaria uma conta administradora (escalada)."""
    return dados_do_cadastro(
        alvos.setor,
        matricula="ESCALADA-001",
        nome="Quem Tenta Escalar",
        papeis=[Papel.ADMINISTRADOR_SISTEMA.value],
        chave_confirmacao=str(uuid.uuid4()),
    )


def _payload_edicao(alvos):
    """Edição VÁLIDA que, sem a autorização, trocaria a matrícula (identidade) do alvo."""
    return {"nome": "Nome Sem Autorização", "matricula": "MATRICULA-TROCADA"}


def _payload_papeis(alvos):
    """Papéis VÁLIDOS que, sem a autorização, tornariam o alvo administrador (escalada)."""
    return {"papeis": [Papel.REQUISITANTE.value, Papel.ADMINISTRADOR_SISTEMA.value]}


def _payload_transferencia(alvos):
    """Transferência VÁLIDA e já confirmada (o alvo não tem papel preso a remover)."""
    return {"setor": str(alvos.destino.pk), "confirmar": "1"}


def _payload_chefia(alvos):
    """Substituição VÁLIDA e já confirmada: o membro do setor viraria chefe."""
    return {
        "novo_chefe": str(alvos.usuario.pk),
        "confirmar": "1",
        "chefe_esperado": str(alvos.chefe.pk),
        "novo_ganha_previsto": ["ROLE-SECTOR-HEAD"],
        "anterior_perde_previsto": ["ROLE-SECTOR-HEAD"],
    }


def _payload_desativacao(alvos):
    """Desativação VÁLIDA e confirmada (o alvo é um membro comum): cortaria o acesso dele."""
    return {"justificativa": "Sem autorização", "confirmar": "1"}


def _payload_reativacao(alvos):
    """Reativação VÁLIDA e confirmada do usuário inativo, só com `ROLE-REQUESTER`."""
    return {"papeis": [Papel.REQUISITANTE.value], "confirmar": "1"}


def _payload_redefinicao(alvos):
    """Redefinição VÁLIDA: trocaria a senha do alvo (tomada de conta)."""
    return {"chave_confirmacao": str(uuid.uuid4())}


def _payload_setor_novo(alvos):
    return {"nome": "Setor Sem Autorização"}


def _payload_setor_editar(alvos):
    return {"nome": "Nome Sem Autorização"}


def _payload_confirmar(alvos):
    """Ativação ou desativação de setor VÁLIDAS e confirmadas."""
    return {"confirmar": "1"}


# (nome da rota, método, alvo do <pk>, corpo do POST, status do administrador)
ROTAS_ORGANIZACAO = [
    pytest.param("usuarios", "get", None, None, (200,), id="usuarios-get"),
    pytest.param("usuario_novo", "get", None, None, (200,), id="usuario_novo-get"),
    pytest.param("usuario_novo", "post", None, _payload_cadastro, (200,), id="usuario_novo-post"),
    pytest.param("usuario", "get", "usuario", None, (200,), id="usuario-get"),
    pytest.param("usuario", "post", "usuario", None, (405,), id="usuario-post"),
    pytest.param("usuario_editar", "get", "usuario", None, (200,), id="usuario_editar-get"),
    pytest.param(
        "usuario_editar", "post", "usuario", _payload_edicao, (302,), id="usuario_editar-post"
    ),
    pytest.param("usuario_papeis", "get", "usuario", None, (200,), id="usuario_papeis-get"),
    pytest.param(
        "usuario_papeis", "post", "usuario", _payload_papeis, (302,), id="usuario_papeis-post"
    ),
    pytest.param("usuario_transferir", "get", "usuario", None, (200,), id="usuario_transferir-get"),
    pytest.param(
        "usuario_transferir",
        "post",
        "usuario",
        _payload_transferencia,
        (302,),
        id="usuario_transferir-post",
    ),
    pytest.param("setores", "get", None, None, (200,), id="setores-get"),
    pytest.param("setor", "get", "setor", None, (200,), id="setor-get"),
    pytest.param("setor", "post", "setor", None, (405,), id="setor-post"),
    pytest.param("setor_chefia", "get", "setor", None, (200,), id="setor_chefia-get"),
    pytest.param("setor_chefia", "post", "setor", _payload_chefia, (302,), id="setor_chefia-post"),
    pytest.param("usuario_desativar", "get", "usuario", None, (200,), id="usuario_desativar-get"),
    pytest.param(
        "usuario_desativar",
        "post",
        "usuario",
        _payload_desativacao,
        (302,),
        id="usuario_desativar-post",
    ),
    pytest.param("usuario_reativar", "get", "inativo", None, (200,), id="usuario_reativar-get"),
    pytest.param(
        "usuario_reativar",
        "post",
        "inativo",
        _payload_reativacao,
        (302,),
        id="usuario_reativar-post",
    ),
    pytest.param(
        "usuario_redefinir_senha", "get", "usuario", None, (200,), id="usuario_redefinir_senha-get"
    ),
    pytest.param(
        "usuario_redefinir_senha",
        "post",
        "usuario",
        _payload_redefinicao,
        (200,),
        id="usuario_redefinir_senha-post",
    ),
    pytest.param("setor_novo", "get", None, None, (200,), id="setor_novo-get"),
    pytest.param("setor_novo", "post", None, _payload_setor_novo, (302,), id="setor_novo-post"),
    pytest.param("setor_editar", "get", "setor", None, (200,), id="setor_editar-get"),
    pytest.param(
        "setor_editar", "post", "setor", _payload_setor_editar, (302,), id="setor_editar-post"
    ),
    pytest.param("setor_ativar", "get", "setor_pronto", None, (200,), id="setor_ativar-get"),
    pytest.param(
        "setor_ativar",
        "post",
        "setor_pronto",
        _payload_confirmar,
        (302,),
        id="setor_ativar-post",
    ),
    pytest.param("setor_desativar", "get", "setor_solo", None, (200,), id="setor_desativar-get"),
    pytest.param(
        "setor_desativar",
        "post",
        "setor_solo",
        _payload_confirmar,
        (302,),
        id="setor_desativar-post",
    ),
]

# `ROTAS_ORGANIZACAO` filtrada por GET, para os testes de `<pk>` inválido.
ROTAS_COM_PK = [
    pytest.param(*p.values[:2], p.values[2], id=p.id)
    for p in ROTAS_ORGANIZACAO
    if p.values[2] is not None and p.values[1] == "get"
]

# Papéis SEM `ROLE-SYSTEM-ADMIN` (fixtures de `tests/conftest.py`), mais a conta técnica.
PAPEIS_SEM_ADMINISTRACAO = [
    "superusuario_tecnico",
    "requisitante",
    "chefe_setor",
    "auditor",
    "funcionario_almoxarifado",
    "chefe_almoxarifado",
]


@pytest.fixture
def alvos(setor):
    """Alvos para as rotas com `<pk>`: nada de especial neles. O setor é ativo, com o chefe `chefe`
    e o membro `usuario` (candidato a novo chefe); `destino` é outro setor, inativo, para a
    transferência; `inativo` é um membro inativo (reativação); `setor_pronto` é inativo e já tem
    chefe (ativação); `setor_solo` é ativo e o chefe é seu único membro (desativação)."""
    setor_alvo, chefe = setor_ativo("Setor Alvo", "alvo-chefe")
    setor_pronto = org.provisionar_setor("Setor Pronto")
    membro(setor_pronto, "pronto-chefe", {Papel.CHEFE_SETOR})
    setor_solo, _ = setor_ativo("Setor Solo", "solo-chefe")
    return SimpleNamespace(
        usuario=membro(setor_alvo, "alvo-membro"),
        inativo=membro(setor_alvo, "alvo-inativo", is_active=False),
        setor=setor_alvo,
        chefe=chefe,
        destino=org.provisionar_setor("Setor Destino"),
        setor_pronto=setor_pronto,
        setor_solo=setor_solo,
    )


def _url(nome, alvo, alvos, pk=None):
    if alvo is None:
        return rota(nome)
    return rota(nome, pk if pk is not None else getattr(alvos, alvo).pk)


def _corpo(payload, alvos):
    return payload(alvos) if payload else {}


def _enviar(client, metodo, url, corpo):
    return getattr(client, metodo)(url, corpo) if metodo == "post" else client.get(url)


def _para_login(resposta):
    return resposta.status_code == 302 and urlsplit(resposta.url).path == reverse("login")


# ---------------------------------------------------------------------------
# Anônimo, inativo e administrador com credencial provisória
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nome, metodo, alvo, payload, esperado", ROTAS_ORGANIZACAO)
def test_anonimo_e_redirecionado_ao_login_sem_conteudo_e_sem_escrita(
    client, alvos, nome, metodo, alvo, payload, esperado
):
    antes = foto_organizacao()

    resposta = _enviar(client, metodo, _url(nome, alvo, alvos), _corpo(payload, alvos))

    assert _para_login(resposta)
    assert resposta.content == b""
    assert foto_organizacao() == antes


@pytest.mark.parametrize("nome, metodo, alvo, payload, esperado", ROTAS_ORGANIZACAO)
def test_administrador_desativado_apos_o_login_e_tratado_como_anonimo(
    client, admin_sistema, alvos, nome, metodo, alvo, payload, esperado
):
    client.force_login(admin_sistema)
    with operacao():
        admin_sistema.is_active = False
        admin_sistema.save(update_fields=["is_active"])
    antes = foto_organizacao()

    resposta = _enviar(client, metodo, _url(nome, alvo, alvos), _corpo(payload, alvos))

    assert _para_login(resposta)
    assert foto_organizacao() == antes


@pytest.mark.parametrize("nome, metodo, alvo, payload, esperado", ROTAS_ORGANIZACAO)
def test_administrador_com_credencial_provisoria_so_alcanca_a_definicao_de_senha(
    client, setor, alvos, nome, metodo, alvo, payload, esperado
):
    admin_provisorio, _ = membro_provisorio(setor, "adm-provisorio", {Papel.ADMINISTRADOR_SISTEMA})
    client.force_login(admin_provisorio)
    antes = foto_organizacao()

    resposta = _enviar(client, metodo, _url(nome, alvo, alvos), _corpo(payload, alvos))

    assert resposta.status_code == 302
    assert urlsplit(resposta.url).path == rota("definir_senha")
    assert foto_organizacao() == antes


# ---------------------------------------------------------------------------
# Papéis sem ROLE-SYSTEM-ADMIN: 403 e nenhuma escrita
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nome, metodo, alvo, payload, esperado", ROTAS_ORGANIZACAO)
@pytest.mark.parametrize("fixture_usuario", PAPEIS_SEM_ADMINISTRACAO)
def test_sem_role_system_admin_recebe_403(
    client, request, alvos, fixture_usuario, nome, metodo, alvo, payload, esperado
):
    usuario = request.getfixturevalue(fixture_usuario)
    client.force_login(usuario)

    resposta = _enviar(client, metodo, _url(nome, alvo, alvos), _corpo(payload, alvos))

    assert resposta.status_code == 403, (
        f"{fixture_usuario} não tem PERM-USER-MANAGE/PERM-SECTOR-MANAGE e deveria receber 403 em "
        f"{nome} ({metodo.upper()})"
    )


@pytest.mark.parametrize("nome, metodo, alvo, payload, esperado", ROTAS_ORGANIZACAO)
@pytest.mark.parametrize("fixture_usuario", PAPEIS_SEM_ADMINISTRACAO)
def test_recusa_por_papel_nao_grava_usuario_setor_papel_nem_evento(
    client, request, alvos, fixture_usuario, nome, metodo, alvo, payload, esperado
):
    usuario = request.getfixturevalue(fixture_usuario)
    client.force_login(usuario)
    antes = foto_organizacao()

    _enviar(client, metodo, _url(nome, alvo, alvos), _corpo(payload, alvos))

    assert foto_organizacao() == antes, (
        f"{fixture_usuario} em {nome} ({metodo.upper()}) mudou User/Setor/PapelUsuario/Evento"
    )


@pytest.mark.parametrize("fixture_usuario", PAPEIS_SEM_ADMINISTRACAO)
def test_403_nao_revela_o_conteudo_administrado(client, request, alvos, fixture_usuario):
    usuario = request.getfixturevalue(fixture_usuario)
    client.force_login(usuario)

    corpo = client.get(rota("usuario", alvos.usuario.pk)).content.decode()

    assert alvos.usuario.matricula not in corpo and alvos.usuario.nome not in corpo


# ---------------------------------------------------------------------------
# Administrador: acesso e <pk> inválido
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nome, metodo, alvo, payload, esperado", ROTAS_ORGANIZACAO)
def test_administrador_acessa_todas_as_rotas(
    client, admin_sistema, alvos, nome, metodo, alvo, payload, esperado
):
    client.force_login(admin_sistema)

    resposta = _enviar(client, metodo, _url(nome, alvo, alvos), _corpo(payload, alvos))

    assert resposta.status_code in esperado, (
        f"{nome} ({metodo.upper()}) respondeu {resposta.status_code} ao administrador; "
        f"esperado {esperado}"
    )


@pytest.mark.parametrize("nome, metodo, alvo", ROTAS_COM_PK)
def test_administrador_recebe_404_para_pk_inexistente(
    client, admin_sistema, alvos, nome, metodo, alvo
):
    client.force_login(admin_sistema)

    resposta = client.get(_url(nome, alvo, alvos, pk=PK_INEXISTENTE))

    assert resposta.status_code == 404


ROTAS_COM_PK_DE_USUARIO = [r for r in ROTAS_COM_PK if r.values[2] in ("usuario", "inativo")]


@pytest.mark.parametrize("nome, metodo, alvo", ROTAS_COM_PK_DE_USUARIO)
def test_administrador_recebe_404_para_a_conta_tecnica(
    client, admin_sistema, alvos, superusuario_tecnico, nome, metodo, alvo
):
    """FR-004: a conta técnica não existe para as telas de organização."""
    client.force_login(admin_sistema)

    resposta = client.get(_url(nome, alvo, alvos, pk=superusuario_tecnico.pk))

    assert resposta.status_code == 404


@pytest.mark.parametrize("nome, metodo, alvo", ROTAS_COM_PK)
@pytest.mark.parametrize("fixture_usuario", PAPEIS_SEM_ADMINISTRACAO)
def test_quem_nao_e_administrador_recebe_403_mesmo_para_pk_inexistente(
    client, request, alvos, fixture_usuario, nome, metodo, alvo
):
    """A checagem de papel vem antes da existência do objeto: 404 só para quem pode saber."""
    client.force_login(request.getfixturevalue(fixture_usuario))

    resposta = client.get(_url(nome, alvo, alvos, pk=PK_INEXISTENTE))

    assert resposta.status_code == 403


# ---------------------------------------------------------------------------
# CSRF e ausência de poder operacional
# ---------------------------------------------------------------------------


def test_post_de_cadastro_sem_token_csrf_e_recusado_e_nao_grava(admin_sistema, alvos):
    cliente = Client(enforce_csrf_checks=True)
    cliente.force_login(admin_sistema)
    antes = foto_organizacao()

    resposta = cliente.post(rota("usuario_novo"), _payload_cadastro(alvos))

    assert resposta.status_code == 403
    assert foto_organizacao() == antes


@pytest.mark.parametrize(
    "nome_rota",
    [
        "estoque:entrada_nova",
        "estoque:entradas",
        "catalogo:importacao_envio",
        "fornecedores:consulta",
        "fornecedores:importacao_envio",
    ],
)
def test_role_system_admin_sozinho_nao_concede_poder_operacional(client, admin_sistema, nome_rota):
    """FR-003/SC-008: o administrador administra a organização e só isso; estoque, importação e
    consulta de fornecedores continuam exigindo os papéis operacionais."""
    client.force_login(admin_sistema)

    assert client.get(reverse(nome_rota)).status_code == 403


# ---------------------------------------------------------------------------
# Completude: nenhuma rota de /organizacao/ fica fora da matriz
# ---------------------------------------------------------------------------


def _nomes_das_rotas_de_organizacao():
    nomes = set()

    def percorrer(padroes, prefixo=""):
        for padrao in padroes:
            trecho = prefixo + str(padrao.pattern)
            if hasattr(padrao, "url_patterns"):
                percorrer(padrao.url_patterns, trecho)
            elif trecho.startswith(PREFIXO_ORGANIZACAO):
                nomes.add(padrao.name)

    percorrer(get_resolver().url_patterns)
    return nomes


def test_toda_rota_de_organizacao_esta_na_tabela_de_permissoes():
    registradas = _nomes_das_rotas_de_organizacao()
    na_tabela = {p.values[0] for p in ROTAS_ORGANIZACAO}

    assert {
        "usuarios",
        "usuario_novo",
        "usuario",
        "usuario_editar",
        "usuario_papeis",
        "usuario_transferir",
        "usuario_desativar",
        "usuario_reativar",
        "usuario_redefinir_senha",
        "setores",
        "setor",
        "setor_chefia",
        "setor_novo",
        "setor_editar",
        "setor_ativar",
        "setor_desativar",
    } <= registradas
    assert registradas <= na_tabela, (
        f"rotas de {PREFIXO_ORGANIZACAO} sem linha em ROTAS_ORGANIZACAO: "
        f"{sorted(registradas - na_tabela)}"
    )


# ---------------------------------------------------------------------------
# FR-052: a autorização é a do momento da ação (T042)
# ---------------------------------------------------------------------------


def test_retirado_o_role_system_admin_de_um_de_dois_administradores_a_proxima_requisicao_e_403(
    client, admin_sistema, criar_usuario_com_papeis, alvos
):
    """A sessão do segundo administrador já estava aberta e autorizada; depois que o primeiro lhe
    retira `ROLE-SYSTEM-ADMIN`, a requisição seguinte — na MESMA sessão — recebe 403, no GET e no
    POST direto, sem gravar nada. A sessão continua autenticada para o que não exige o papel."""
    outro = criar_usuario_com_papeis(Papel.ADMINISTRADOR_SISTEMA)
    client.force_login(outro)
    assert client.get(rota("usuarios")).status_code == 200
    primeiro = Client()
    primeiro.force_login(admin_sistema)

    org.alterar_papeis(
        admin_sistema, outro.pk, conceder=set(), remover={Papel.ADMINISTRADOR_SISTEMA}
    )

    antes = foto_organizacao()
    assert client.get(rota("usuarios")).status_code == 403
    assert client.get(rota("usuario", alvos.usuario.pk)).status_code == 403
    assert client.post(rota("usuario_novo"), _payload_cadastro(alvos)).status_code == 403
    assert foto_organizacao() == antes
    assert client.get(reverse("home")).status_code == 200, "continua autenticado, sem o papel"
    assert primeiro.get(rota("usuarios")).status_code == 200, "o outro administrador não é afetado"


# ---------------------------------------------------------------------------
# `definir_senha` (/senha/): mecânica de autenticação, sem papel (T047, FR-039)
# ---------------------------------------------------------------------------

AUTENTICADOS_ATIVOS = [
    "requisitante",
    "chefe_setor",
    "auditor",
    "funcionario_almoxarifado",
    "chefe_almoxarifado",
    "admin_sistema",
    "superusuario_tecnico",
]


def _troca(nova="Cavalo-Azul-Distante-4718"):
    return {
        "old_password": "uma-senha-de-teste-bastante-forte-123",
        "new_password1": nova,
        "new_password2": nova,
    }


@pytest.mark.parametrize("fixture_usuario", AUTENTICADOS_ATIVOS)
def test_definir_senha_e_acessivel_a_todo_autenticado_ativo_sem_depender_de_papel(
    client, request, fixture_usuario
):
    client.force_login(request.getfixturevalue(fixture_usuario))

    assert client.get(rota("definir_senha")).status_code == 200


@pytest.mark.parametrize("fixture_usuario", AUTENTICADOS_ATIVOS)
def test_todo_autenticado_ativo_troca_a_propria_senha_sem_depender_de_papel(
    client, request, fixture_usuario
):
    usuario = request.getfixturevalue(fixture_usuario)
    client.force_login(usuario)

    resposta = client.post(rota("definir_senha"), _troca())

    assert resposta.status_code == 302
    assert User.objects.get(pk=usuario.pk).check_password(_troca()["new_password1"])


def test_anonimo_vai_ao_login_ao_acessar_definir_senha_e_nada_muda(client, requisitante):
    antes = foto_organizacao()

    leitura = client.get(rota("definir_senha"))
    escrita = client.post(rota("definir_senha"), _troca())

    assert _para_login(leitura) and _para_login(escrita)
    assert leitura.content == b"" and escrita.content == b""
    assert foto_organizacao() == antes


def test_conta_desativada_apos_o_login_e_tratada_como_anonima_em_definir_senha(
    client, requisitante
):
    client.force_login(requisitante)
    with operacao():
        requisitante.is_active = False
        requisitante.save(update_fields=["is_active"])
    antes = foto_organizacao()

    leitura = client.get(rota("definir_senha"))
    escrita = client.post(rota("definir_senha"), _troca())

    assert _para_login(leitura) and _para_login(escrita)
    assert foto_organizacao() == antes, "nem a senha de uma conta inativa muda por esta rota"


def test_administrador_com_credencial_provisoria_alcanca_a_definicao_de_senha(client, setor):
    provisorio, _ = membro_provisorio(setor, "adm-prov-senha", {Papel.ADMINISTRADOR_SISTEMA})
    client.force_login(provisorio)

    assert client.get(rota("definir_senha")).status_code == 200
