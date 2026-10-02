"""Histórico organizacional nas fichas de usuário e de setor (T026, US2).

Fontes: FR-040 a FR-042, FR-031, `data-model.md` ("Eventos"), research R7. Eventos são só de
acréscimo (a imutabilidade em si é testada em `test_contas_banco.py`); aqui se verifica o que a
ficha MOSTRA a partir dos eventos gravados:

- a ficha do usuário lista os eventos em que ele é `usuario` OU `usuario_relacionado`, e a do
  setor os em que ele é `setor` OU `setor_relacionado` — e nenhum evento alheio;
- cada evento aparece com autor, momento e valores anterior/novo; evento sem autor (provisionamento
  técnico) aparece como "Provisionamento técnico";
- a ordem é cronológica; o histórico é paginado; operação sem efeito não gera evento; nenhum evento
  guarda senha (FR-031).

Os eventos são criados direto no model quando o teste precisa controlar `momento`, relacionados
ou tipos que as operações das stories seguintes (US3 a US7) ainda não produzem; são recortes
legítimos: o model não tem barreira de escrita e o histórico é só leitura.

Contratos FIXADOS por estes testes (ajustar aqui se a implementação divergir):

- o TIPO do evento é exibido pelo rótulo de `TipoEvento` (ex.: "Usuário editado");
- a ordem é cronológica CRESCENTE (do mais antigo ao mais recente), como diz o spec;
- o parâmetro de página do histórico é `pagina` (o mesmo das listas);
- `dados` segue `{"anterior": {...}, "novo": {...}}` e seus valores são exibidos.

TDD: escrito antes de `UsuarioFichaView`/`SetorFichaView` com histórico (T024, T028) existirem.
"""

import json
import uuid
from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from contas import organizacao as org
from contas.models import EventoOrganizacional, TipoEvento, User
from tests.contas_helpers import (
    PARAM_PAGINA,
    SENHA_TESTE,
    dados_do_cadastro,
    fixar_senha_gerada,
    membro,
    rota,
    setor_ativo,
    texto_visivel,
)

pytestmark = pytest.mark.django_db

PROVISIONAMENTO_TECNICO = "Provisionamento técnico"
CHAVES_PROIBIDAS_EM_DADOS = {"senha", "password", "senha_provisoria", "nova_senha", "hash"}


def _momento(ano, mes, dia, hora=10, minuto=0):
    return timezone.make_aware(datetime(ano, mes, dia, hora, minuto))


def _evento(tipo, **campos):
    campos.setdefault("dados", {})
    return EventoOrganizacional.objects.create(tipo=tipo, **campos)


def _ficha_usuario(client, usuario):
    resposta = client.get(rota("usuario", usuario.pk))
    assert resposta.status_code == 200
    return texto_visivel(resposta.content.decode())


def _ficha_setor(client, setor):
    resposta = client.get(rota("setor", setor.pk))
    assert resposta.status_code == 200
    return texto_visivel(resposta.content.decode())


@pytest.fixture
def cenario(admin_sistema, client):
    eta, chefe_eta = setor_ativo("ETA", "eta-chefe")
    laboratorio = org.provisionar_setor("Laboratório")
    terceiro = org.provisionar_setor("Setor Terceiro")
    client.force_login(admin_sistema)

    class Cenario:
        admin = admin_sistema
        setor_eta = eta
        chefe = chefe_eta
        lab = laboratorio
        outro_setor = terceiro

    return Cenario


# ---------------------------------------------------------------------------
# Quais eventos aparecem em cada ficha
# ---------------------------------------------------------------------------


def test_ficha_do_usuario_lista_eventos_em_que_ele_e_alvo_ou_relacionado_e_nenhum_alheio(
    client, cenario
):
    alvo = membro(cenario.setor_eta, "hist-alvo")
    outro = membro(cenario.setor_eta, "hist-outro")
    _evento(TipoEvento.USUARIO_EDITADO, usuario=alvo, autor=cenario.admin)
    _evento(
        TipoEvento.CHEFIA_SUBSTITUIDA,
        usuario=outro,
        usuario_relacionado=alvo,  # o chefe anterior também vê a substituição
        setor=cenario.setor_eta,
        autor=cenario.admin,
    )
    _evento(TipoEvento.PAPEIS_ALTERADOS, usuario=outro, autor=cenario.admin)
    _evento(TipoEvento.SETOR_RENOMEADO, setor=cenario.setor_eta, autor=cenario.admin)

    texto = _ficha_usuario(client, alvo)

    assert TipoEvento.USUARIO_EDITADO.label in texto
    assert TipoEvento.CHEFIA_SUBSTITUIDA.label in texto
    assert TipoEvento.PAPEIS_ALTERADOS.label not in texto  # evento de outra pessoa
    assert TipoEvento.SETOR_RENOMEADO.label not in texto  # evento do setor, sem o usuário


def test_ficha_do_setor_lista_eventos_em_que_ele_e_alvo_ou_relacionado_e_nenhum_alheio(
    client, cenario
):
    viajante = membro(cenario.setor_eta, "hist-viajante")
    _evento(
        TipoEvento.USUARIO_TRANSFERIDO,
        usuario=viajante,
        setor=cenario.lab,  # destino
        setor_relacionado=cenario.setor_eta,  # origem
        autor=cenario.admin,
    )
    _evento(TipoEvento.SETOR_RENOMEADO, setor=cenario.outro_setor, autor=cenario.admin)

    origem = _ficha_setor(client, cenario.setor_eta)
    destino = _ficha_setor(client, cenario.lab)
    terceiro = _ficha_setor(client, cenario.outro_setor)

    assert TipoEvento.USUARIO_TRANSFERIDO.label in origem
    assert TipoEvento.USUARIO_TRANSFERIDO.label in destino
    assert TipoEvento.USUARIO_TRANSFERIDO.label not in terceiro
    assert TipoEvento.SETOR_RENOMEADO.label in terceiro
    assert TipoEvento.SETOR_RENOMEADO.label not in origem
    assert TipoEvento.SETOR_RENOMEADO.label not in destino


# ---------------------------------------------------------------------------
# Conteúdo de cada evento: autor, momento, anterior e novo
# ---------------------------------------------------------------------------


def test_evento_mostra_autor_momento_e_valores_anterior_e_novo(client, cenario):
    alvo = membro(cenario.setor_eta, "hist-conteudo")
    autor = membro(cenario.setor_eta, "AUT-777")
    _evento(
        TipoEvento.USUARIO_EDITADO,
        usuario=alvo,
        autor=autor,
        momento=_momento(2024, 3, 5, 14, 30),
        dados={"anterior": {"nome": "Nome-Antigo-Zq"}, "novo": {"nome": "Nome-Novo-Zq"}},
    )

    texto = _ficha_usuario(client, alvo)

    assert "05/03/2024" in texto
    assert autor.nome in texto or autor.matricula in texto
    assert "Nome-Antigo-Zq" in texto and "Nome-Novo-Zq" in texto


def test_evento_sem_autor_aparece_como_provisionamento_tecnico_nas_duas_fichas(client, cenario):
    # `membro` e `provisionar_setor` gravam eventos com autor nulo (provisionamento, R15)
    provisionado = membro(cenario.lab, "hist-provisionado")

    ficha_usuario = _ficha_usuario(client, provisionado)
    ficha_setor = _ficha_setor(client, cenario.lab)

    assert PROVISIONAMENTO_TECNICO in ficha_usuario
    assert PROVISIONAMENTO_TECNICO in ficha_setor


def test_cadastro_pelo_administrador_aparece_no_historico_com_autor_e_sem_rotulo_tecnico(
    client, cenario, monkeypatch
):
    fixar_senha_gerada(monkeypatch)
    client.post(rota("usuario_novo"), dados_do_cadastro(cenario.setor_eta, matricula="HIST-NOVO"))
    novo = User.objects.get(matricula="HIST-NOVO")

    texto = _ficha_usuario(client, novo)

    assert TipoEvento.USUARIO_CADASTRADO.label in texto
    assert PROVISIONAMENTO_TECNICO not in texto  # tudo foi feito por uma pessoa


# ---------------------------------------------------------------------------
# Ordem cronológica e paginação
# ---------------------------------------------------------------------------


def test_historico_em_ordem_cronologica_independente_da_ordem_de_gravacao(client, cenario):
    alvo = membro(cenario.setor_eta, "hist-ordem")
    # gravados fora de ordem: o momento é que manda
    _evento(TipoEvento.PAPEIS_ALTERADOS, usuario=alvo, momento=_momento(2024, 2, 1))
    _evento(
        TipoEvento.USUARIO_TRANSFERIDO,
        usuario=alvo,
        setor=cenario.lab,
        momento=_momento(2024, 3, 1),
    )
    _evento(TipoEvento.USUARIO_EDITADO, usuario=alvo, momento=_momento(2024, 1, 1))

    texto = _ficha_usuario(client, alvo)

    posicoes = [
        texto.index(TipoEvento.USUARIO_EDITADO.label),
        texto.index(TipoEvento.PAPEIS_ALTERADOS.label),
        texto.index(TipoEvento.USUARIO_TRANSFERIDO.label),
    ]
    assert posicoes == sorted(posicoes), "esperava do mais antigo ao mais recente"


def _paginas_percorridas(client, url, ate=15):
    """Texto das páginas `?pagina=1` a `?pagina=<ate>` do histórico (o tamanho da página é
    decisão do plan; 15 páginas cobrem qualquer tamanho a partir de 8 eventos)."""
    textos = []
    for numero in range(1, ate + 1):
        resposta = client.get(url, {PARAM_PAGINA: numero})
        assert resposta.status_code == 200
        textos.append(texto_visivel(resposta.content.decode()))
    return textos


@pytest.mark.parametrize("alvo_da_ficha", ["usuario", "setor"])
def test_historico_e_paginado_e_nenhum_evento_se_perde_entre_as_paginas(
    client, cenario, alvo_da_ficha
):
    alvo = membro(cenario.setor_eta, "hist-paginas")
    total = 120
    EventoOrganizacional.objects.bulk_create(
        [
            EventoOrganizacional(
                tipo=TipoEvento.USUARIO_EDITADO,
                usuario=alvo,
                setor=cenario.lab,
                momento=_momento(2023, 1, 1) + timedelta(minutes=i),
                dados={"anterior": {"nome": f"Ant-{i:04d}"}, "novo": {"nome": f"Evt-{i:04d}"}},
                justificativa=f"Evt-{i:04d}",
            )
            for i in range(1, total + 1)
        ]
    )
    url = rota("usuario", alvo.pk) if alvo_da_ficha == "usuario" else rota("setor", cenario.lab.pk)
    esperados = {f"Evt-{i:04d}" for i in range(1, total + 1)}

    paginas = _paginas_percorridas(client, url)

    na_primeira = {t for t in esperados if t in paginas[0]}
    assert 0 < len(na_primeira) < total, "a primeira página não pode mostrar o histórico inteiro"
    vistos = {t for pagina in paginas for t in esperados if t in pagina}
    assert vistos == esperados, (
        f"{len(esperados - vistos)} eventos inacessíveis percorrendo ?{PARAM_PAGINA}=1..N"
    )


# ---------------------------------------------------------------------------
# Sem efeito, sem evento; sem senha em nenhum evento
# ---------------------------------------------------------------------------


def test_operacao_sem_efeito_nao_gera_evento(cenario):
    """`provisionar_ativacao` de um setor já ativo não muda nada — e nada registra."""
    antes = EventoOrganizacional.objects.count()

    org.provisionar_ativacao(cenario.setor_eta)

    assert EventoOrganizacional.objects.count() == antes


def _chaves(obj):
    if isinstance(obj, dict):
        for chave, valor in obj.items():
            yield str(chave).lower()
            yield from _chaves(valor)
    elif isinstance(obj, list):
        for item in obj:
            yield from _chaves(item)


def test_nenhum_evento_guarda_senha_nem_campo_de_senha(cenario, monkeypatch):
    senha = fixar_senha_gerada(monkeypatch)
    cadastrado, senha_cadastro = org.cadastrar_usuario(
        cenario.admin,
        matricula="HIST-SENHA",
        nome="Pessoa Sem Senha No Evento",
        setor_id=cenario.setor_eta.pk,
        papeis_adicionais=set(),
        chave_confirmacao=uuid.uuid4(),
    )
    _, senha_provisionamento = org.provisionar_usuario(
        "HIST-PROV", "Provisionada", cenario.lab, set()
    )
    membro(cenario.lab, "hist-dev")  # provisionamento com senha conhecida (desenvolvimento)

    assert EventoOrganizacional.objects.filter(usuario=cadastrado).exists()
    for evento in EventoOrganizacional.objects.all():
        conteudo = json.dumps(evento.dados, ensure_ascii=False) + evento.justificativa
        for segredo in (senha, senha_cadastro, senha_provisionamento, SENHA_TESTE):
            assert segredo not in conteudo, evento.tipo
        assert not set(_chaves(evento.dados)) & CHAVES_PROIBIDAS_EM_DADOS, evento.tipo


def test_historico_so_para_o_administrador_ficha_de_outro_papel_e_negada(client, cenario, auditor):
    alvo = membro(cenario.setor_eta, "hist-negado")
    _evento(TipoEvento.USUARIO_EDITADO, usuario=alvo, dados={"novo": {"nome": "Segredo-Hist"}})
    client.force_login(auditor)

    resposta = client.get(rota("usuario", alvo.pk))

    assert resposta.status_code == 403
    assert "Segredo-Hist" not in resposta.content.decode()
