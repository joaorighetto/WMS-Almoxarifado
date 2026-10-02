"""Telas de organização que explicam antes de oferecer (feature 005, correções do gate visual).

O servidor continua decidindo em cada operação; as telas ganham o cálculo antecipado, só de
leitura, do que a operação recusaria:

- ação impedida (desativar setor com membros, desativar o chefe de setor ativo ou a própria
  conta, ativar setor sem chefia, transferir o chefe de setor ativo) NÃO oferece o botão de
  confirmação: a página explica o motivo, aponta o caminho e devolve; o POST segue recusado e
  não grava (DESIGN.md → Buttons, Destrutivo);
- a ficha mantém a ação impedida visível: ela leva à tela que explica;
- cadastro: matrícula repetida vira erro do campo, com a conta existente à mão; papéis
  incompatíveis com o setor chegam bloqueados e explicados, trocados por HTMX ao mudar o setor;
- ficha do setor inativo: prontidão para ativar; designação sem candidatos oferece caminho;
- substituição no Almoxarifado diz por extenso a autoridade de estoque que muda de mãos.

As asserções usam conteúdo visível, status, contexto e banco — nunca classes de CSS. O "botão
de confirmação" é o campo `confirmar` do formulário de confirmação: sem ele não há como confirmar.

Aplica: PERM-USER-MANAGE, PERM-SECTOR-MANAGE.
Preserva: INV-ORG-001, INV-ORG-002, INV-ORG-004, INV-ORG-006.
"""

import re
from types import SimpleNamespace

import pytest

from contas import organizacao as org
from contas.models import Papel, Setor, User
from tests.contas_helpers import (
    PAPEIS_CHEFE_ALMOXARIFADO,
    dados_do_cadastro,
    foto_organizacao,
    hrefs,
    membro,
    recusa_de,
    rota,
    setor_ativo,
    texto_principal,
)

pytestmark = pytest.mark.django_db

HTMX = {"HTTP_HX_REQUEST": "true"}


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


def _oferece_confirmar(resposta):
    """A tela traz o formulário que confirma a operação (campo `confirmar`)."""
    return 'name="confirmar"' in resposta.content.decode()


def _explica(resposta, recusa):
    texto = texto_principal(resposta.content.decode())
    assert re.sub(r"\s+", " ", recusa.motivo) in texto
    if recusa.caminho:
        assert re.sub(r"\s+", " ", recusa.caminho) in texto
    return texto


def _input_do_papel(resposta, papel):
    """A tag `<input>` do checkbox do papel na região de papéis do cadastro."""
    achados = re.findall(rf'<input\b[^>]*value="{papel.value}"[^>]*>', resposta.content.decode())
    assert len(achados) == 1, achados
    return achados[0]


# ===========================================================================
# 1. Ação impedida não chega à confirmação com botão
# ===========================================================================


def test_desativar_o_chefe_de_setor_ativo_explica_e_leva_a_substituicao_sem_botao(client, cenario):
    alvo = cenario.chefe_eta
    esperada = recusa_de(lambda: org.desativar_usuario(cenario.admin, alvo.pk))
    antes = foto_organizacao()

    resposta = client.get(rota("usuario_desativar", alvo.pk))

    assert resposta.status_code == 200
    assert not _oferece_confirmar(resposta)
    _explica(resposta, esperada)
    assert resposta.context["impedimento"].motivo == esperada.motivo
    assert resposta.context["destino_impedimento"]["url"] == rota("setor_chefia", cenario.eta.pk)
    assert rota("setor_chefia", cenario.eta.pk) in hrefs(resposta.content.decode())
    assert rota("usuario", alvo.pk) in hrefs(resposta.content.decode()), "só o retorno"
    assert foto_organizacao() == antes


def test_desativar_a_propria_conta_explica_sem_botao(client, cenario):
    esperada = recusa_de(lambda: org.desativar_usuario(cenario.admin, cenario.admin.pk))

    resposta = client.get(rota("usuario_desativar", cenario.admin.pk))

    assert not _oferece_confirmar(resposta)
    _explica(resposta, esperada)
    assert resposta.context["impedimento"].codigo == org.RECUSA_PROPRIA_CONTA
    assert resposta.context["destino_impedimento"] is None


def test_o_post_da_desativacao_impedida_segue_recusado_sem_gravar_e_sem_repetir_o_motivo(
    client, cenario
):
    alvo = cenario.chefe_eta
    esperada = recusa_de(lambda: org.desativar_usuario(cenario.admin, alvo.pk))
    antes = foto_organizacao()

    resposta = client.post(rota("usuario_desativar", alvo.pk), {"confirmar": "1"})

    assert resposta.status_code == 200
    assert not _oferece_confirmar(resposta)
    texto = _explica(resposta, esperada)
    assert texto.count(esperada.motivo) == 1
    assert foto_organizacao() == antes
    assert User.objects.get(pk=alvo.pk).is_active is True


def test_desativar_conta_sem_impedimento_continua_oferecendo_a_confirmacao(client, cenario):
    alvo = membro(cenario.eta, "eta-comum")

    resposta = client.get(rota("usuario_desativar", alvo.pk))

    assert _oferece_confirmar(resposta)
    assert resposta.context["impedimento"] is None


def test_desativar_setor_com_membros_lista_cada_um_com_link_para_a_ficha_sem_botao(client, cenario):
    pedro = membro(cenario.eta, "eta-pedro")
    paula = membro(cenario.eta, "eta-paula")
    esperada = recusa_de(lambda: org.desativar_setor(cenario.admin, cenario.eta.pk))
    antes = foto_organizacao()

    resposta = client.get(rota("setor_desativar", cenario.eta.pk))

    assert resposta.status_code == 200
    assert not _oferece_confirmar(resposta)
    _explica(resposta, esperada)
    assert [u.pk for u in resposta.context["impedimento"].membros] == [paula.pk, pedro.pk]
    links = hrefs(resposta.content.decode())
    assert {rota("usuario", paula.pk), rota("usuario", pedro.pk)} <= links
    assert foto_organizacao() == antes


def test_o_post_de_desativar_setor_com_membros_segue_recusado_sem_gravar(client, cenario):
    membro(cenario.eta, "eta-pedro")
    esperada = recusa_de(lambda: org.desativar_setor(cenario.admin, cenario.eta.pk))
    antes = foto_organizacao()

    resposta = client.post(rota("setor_desativar", cenario.eta.pk), {"confirmar": "1"})

    assert resposta.status_code == 200
    assert not _oferece_confirmar(resposta)
    assert _explica(resposta, esperada).count(esperada.motivo) == 1
    assert foto_organizacao() == antes
    assert Setor.objects.get(pk=cenario.eta.pk).ativo is True


def test_desativar_o_almoxarifado_ativo_explica_sem_botao(client, cenario):
    membro(cenario.almoxarifado, "almox-chefe", PAPEIS_CHEFE_ALMOXARIFADO)
    org.provisionar_ativacao(cenario.almoxarifado)
    esperada = recusa_de(lambda: org.desativar_setor(cenario.admin, cenario.almoxarifado.pk))

    resposta = client.get(rota("setor_desativar", cenario.almoxarifado.pk))

    assert not _oferece_confirmar(resposta)
    _explica(resposta, esperada)


def test_desativar_setor_so_com_o_chefe_continua_oferecendo_a_confirmacao(client, cenario):
    solo, _ = setor_ativo("Solo", "solo-chefe")

    resposta = client.get(rota("setor_desativar", solo.pk))

    assert _oferece_confirmar(resposta)
    assert resposta.context["impedimento"] is None


def test_ativar_setor_sem_chefe_explica_e_leva_a_designacao_sem_botao(client, cenario):
    esperada = recusa_de(lambda: org.ativar_setor(cenario.admin, cenario.lab.pk))
    antes = foto_organizacao()

    resposta = client.get(rota("setor_ativar", cenario.lab.pk))

    assert resposta.status_code == 200
    assert not _oferece_confirmar(resposta)
    _explica(resposta, esperada)
    assert resposta.context["destino_impedimento"]["url"] == rota("setor_chefia", cenario.lab.pk)
    assert rota("setor_chefia", cenario.lab.pk) in hrefs(resposta.content.decode())
    assert foto_organizacao() == antes


def test_o_post_de_ativar_setor_sem_chefe_segue_recusado_sem_gravar(client, cenario):
    esperada = recusa_de(lambda: org.ativar_setor(cenario.admin, cenario.lab.pk))
    antes = foto_organizacao()

    resposta = client.post(rota("setor_ativar", cenario.lab.pk), {"confirmar": "1"})

    assert resposta.status_code == 200
    assert not _oferece_confirmar(resposta)
    assert _explica(resposta, esperada).count(esperada.motivo) == 1
    assert foto_organizacao() == antes
    assert Setor.objects.get(pk=cenario.lab.pk).ativo is False


def test_ativar_o_almoxarifado_sem_a_chefia_de_estoque_completa_explica_sem_botao(client, cenario):
    membro(cenario.almoxarifado, "almox-chefe", {Papel.CHEFE_SETOR})
    esperada = recusa_de(lambda: org.ativar_setor(cenario.admin, cenario.almoxarifado.pk))

    resposta = client.get(rota("setor_ativar", cenario.almoxarifado.pk))

    assert not _oferece_confirmar(resposta)
    _explica(resposta, esperada)
    assert resposta.context["impedimento"].codigo == org.RECUSA_CHEFIA_DE_ESTOQUE_INCOMPLETA


def test_ativar_setor_pronto_continua_oferecendo_a_confirmacao(client, cenario):
    luiza = membro(cenario.lab, "lab-luiza")
    org.designar_chefia(cenario.admin, cenario.lab.pk, luiza.pk)

    resposta = client.get(rota("setor_ativar", cenario.lab.pk))

    assert _oferece_confirmar(resposta)
    assert resposta.context["impedimento"] is None


def test_a_ficha_do_chefe_de_setor_ativo_mostra_transferir_e_a_tela_explica(client, cenario):
    alvo = cenario.chefe_eta
    esperada = recusa_de(
        lambda: org.transferir_usuario(
            cenario.admin, alvo.pk, cenario.lab.pk, papeis_removidos_previstos=[]
        )
    )

    ficha = client.get(rota("usuario", alvo.pk))
    tela = client.get(rota("usuario_transferir", alvo.pk))

    assert rota("usuario_transferir", alvo.pk) in hrefs(ficha.content.decode())
    assert ficha.context["impedimento_transferir"].motivo == esperada.motivo
    assert tela.status_code == 200
    _explica(tela, esperada)
    assert tela.context["destino_impedimento"]["url"] == rota("setor_chefia", cenario.eta.pk)
    assert rota("setor_chefia", cenario.eta.pk) in hrefs(tela.content.decode())
    assert 'name="setor"' not in tela.content.decode(), "sem formulário de destino"


def test_o_post_da_transferencia_do_chefe_de_setor_ativo_segue_recusado_sem_gravar(client, cenario):
    alvo = cenario.chefe_eta
    esperada = recusa_de(
        lambda: org.transferir_usuario(
            cenario.admin, alvo.pk, cenario.lab.pk, papeis_removidos_previstos=[]
        )
    )
    antes = foto_organizacao()

    resposta = client.post(rota("usuario_transferir", alvo.pk), {"setor": cenario.lab.pk})

    assert resposta.status_code == 200
    assert _explica(resposta, esperada).count(esperada.motivo) == 1
    assert foto_organizacao() == antes
    assert User.objects.get(pk=alvo.pk).setor_id == cenario.eta.pk


def test_a_ficha_de_quem_nao_chefia_oferece_transferir_sem_impedimento(client, cenario):
    alvo = membro(cenario.eta, "eta-comum")

    ficha = client.get(rota("usuario", alvo.pk))
    tela = client.get(rota("usuario_transferir", alvo.pk))

    assert rota("usuario_transferir", alvo.pk) in hrefs(ficha.content.decode())
    assert ficha.context["impedimento_transferir"] is None
    assert tela.context["impedimento"] is None
    assert 'name="setor"' in tela.content.decode()


# ===========================================================================
# 2. Cadastro
# ===========================================================================


def test_matricula_repetida_vira_erro_do_campo_com_a_ficha_da_conta(client, cenario):
    existente = cenario.chefe_eta
    antes = foto_organizacao()

    resposta = client.post(
        rota("usuario_novo"),
        dados_do_cadastro(cenario.lab, matricula=existente.matricula, nome="Outra Pessoa"),
    )

    assert resposta.status_code == 200
    assert resposta.context["form"].errors["matricula"] == ["Matrícula já usada por outra conta."]
    assert resposta.context["conta_existente"] == {
        "pk": existente.pk,
        "nome": existente.nome,
        "ativo": True,
        "situacao": "Ativo",
    }
    conteudo = resposta.content.decode()
    assert rota("usuario", existente.pk) in hrefs(conteudo)
    assert rota("usuario_reativar", existente.pk) not in hrefs(conteudo)
    assert 'aria-invalid="true"' in conteudo
    assert foto_organizacao() == antes


def test_matricula_repetida_de_conta_inativa_oferece_reativar(client, cenario):
    inativa = membro(cenario.eta, "eta-inativa", is_active=False)

    resposta = client.post(
        rota("usuario_novo"), dados_do_cadastro(cenario.lab, matricula=inativa.matricula)
    )

    assert resposta.context["conta_existente"]["ativo"] is False
    assert resposta.context["conta_existente"]["situacao"] == "Inativo"
    assert rota("usuario_reativar", inativa.pk) in hrefs(resposta.content.decode())


def test_matricula_repetida_de_conta_tecnica_e_erro_do_campo_sem_conta_existente(
    client, cenario, superusuario_tecnico
):
    resposta = client.post(
        rota("usuario_novo"),
        dados_do_cadastro(cenario.lab, matricula=superusuario_tecnico.matricula),
    )

    assert resposta.context["form"].errors["matricula"]
    assert resposta.context["conta_existente"] is None


def test_o_cadastro_de_papel_de_almoxarifado_fora_do_almoxarifado_usa_o_texto_do_cadastro(
    client, cenario
):
    antes = foto_organizacao()

    resposta = client.post(
        rota("usuario_novo"),
        dados_do_cadastro(cenario.eta, papeis=[Papel.FUNCIONARIO_ALMOXARIFADO.value]),
    )

    assert resposta.status_code == 200
    texto = texto_principal(resposta.content.decode())
    assert "Os papéis de almoxarifado só podem ser dados a quem é do setor Almoxarifado." in texto
    assert "Escolha o setor Almoxarifado ou desmarque o papel." in texto
    assert "tem papel de almoxarifado fora do setor" not in texto
    assert foto_organizacao() == antes
    assert "disabled" in _input_do_papel(resposta, Papel.FUNCIONARIO_ALMOXARIFADO)


def test_o_parcial_htmx_traz_so_a_regiao_de_papeis_com_os_bloqueios_do_setor(client, cenario):
    resposta = client.get(rota("usuario_novo"), {"setor": cenario.eta.pk}, **HTMX)

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "<html" not in conteudo and 'name="chave_confirmacao"' not in conteudo
    assert "HX-Request" in resposta["Vary"]
    for papel in (Papel.FUNCIONARIO_ALMOXARIFADO, Papel.CHEFE_ALMOXARIFADO, Papel.CHEFE_SETOR):
        assert "disabled" in _input_do_papel(resposta, papel), papel
    assert "disabled" not in _input_do_papel(resposta, Papel.AUDITOR)
    bloqueios = {o["papel"]: o for o in resposta.context["opcoes_de_papeis"] if o["bloqueio"]}
    assert set(bloqueios) == {
        Papel.FUNCIONARIO_ALMOXARIFADO,
        Papel.CHEFE_ALMOXARIFADO,
        Papel.CHEFE_SETOR,
    }
    assert bloqueios[Papel.CHEFE_SETOR]["destino"]["url"] == rota("setor_chefia", cenario.eta.pk)
    assert rota("setor_chefia", cenario.eta.pk) in hrefs(conteudo)
    assert resposta.context["implicados_pela_chefia"] == []


def test_o_parcial_htmx_de_setor_inativo_sem_chefe_libera_o_papel_de_chefe(client, cenario):
    resposta = client.get(rota("usuario_novo"), {"setor": cenario.lab.pk}, **HTMX)

    assert "disabled" not in _input_do_papel(resposta, Papel.CHEFE_SETOR)
    assert "disabled" in _input_do_papel(resposta, Papel.FUNCIONARIO_ALMOXARIFADO)


def test_o_parcial_htmx_do_almoxarifado_declara_o_efeito_de_chefe_de_setor(client, cenario):
    resposta = client.get(rota("usuario_novo"), {"setor": cenario.almoxarifado.pk}, **HTMX)

    for papel in (Papel.FUNCIONARIO_ALMOXARIFADO, Papel.CHEFE_SETOR):
        assert "disabled" not in _input_do_papel(resposta, papel)
    assert resposta.context["implicados_pela_chefia"] == [
        Papel.FUNCIONARIO_ALMOXARIFADO.label,
        Papel.CHEFE_ALMOXARIFADO.label,
    ]
    texto = texto_principal(resposta.content.decode())
    assert Papel.CHEFE_ALMOXARIFADO.label in texto


def test_o_parcial_htmx_preserva_os_papeis_ja_marcados_que_cabem_no_novo_setor(client, cenario):
    resposta = client.get(
        rota("usuario_novo"),
        {
            "setor": cenario.lab.pk,
            "papeis": [Papel.AUDITOR.value, Papel.FUNCIONARIO_ALMOXARIFADO.value],
        },
        **HTMX,
    )

    assert "checked" in _input_do_papel(resposta, Papel.AUDITOR)
    bloqueado = _input_do_papel(resposta, Papel.FUNCIONARIO_ALMOXARIFADO)
    assert "disabled" in bloqueado and "checked" not in bloqueado


def test_o_parcial_htmx_sem_setor_valido_nao_bloqueia_nada(client, cenario):
    for consulta in ({}, {"setor": "abc"}, {"setor": "987654321"}):
        resposta = client.get(rota("usuario_novo"), consulta, **HTMX)

        assert resposta.status_code == 200
        assert not [o for o in resposta.context["opcoes_de_papeis"] if o["bloqueio"]], consulta


def test_o_seletor_de_setor_do_cadastro_troca_os_papeis_por_htmx(client, cenario):
    conteudo = client.get(rota("usuario_novo")).content.decode()

    seletor = re.search(r'<select\b[^>]*name="setor"[^>]*>', conteudo).group(0)
    assert f'hx-get="{rota("usuario_novo")}"' in seletor
    assert 'hx-target="#papeis-cadastro"' in seletor
    assert 'id="papeis-cadastro"' in conteudo


def test_o_cadastro_sem_javascript_re_renderiza_com_os_bloqueios_do_setor_escolhido(
    client, cenario
):
    """O envio com erro de formulário (sem JS) devolve a página inteira com os papéis do setor
    já escolhido, bloqueados e explicados."""
    resposta = client.post(rota("usuario_novo"), dados_do_cadastro(cenario.eta, nome=""))

    assert resposta.status_code == 200
    assert "disabled" in _input_do_papel(resposta, Papel.FUNCIONARIO_ALMOXARIFADO)
    assert resposta.context["setor_escolhido"] == cenario.eta


def test_o_setor_da_query_pre_seleciona_o_cadastro(client, cenario):
    resposta = client.get(rota("usuario_novo"), {"setor": cenario.lab.pk})

    assert resposta.status_code == 200
    assert resposta.context["form"]["setor"].value() == cenario.lab.pk
    assert f'value="{cenario.lab.pk}" selected' in resposta.content.decode()
    assert resposta.context["setor_escolhido"] == cenario.lab


@pytest.mark.parametrize("valor", ["abc", "987654321", ""])
def test_setor_invalido_na_query_nao_pre_seleciona_nem_quebra(client, cenario, valor):
    resposta = client.get(rota("usuario_novo"), {"setor": valor})

    assert resposta.status_code == 200
    assert resposta.context["setor_escolhido"] is None
    assert resposta.context["form"]["setor"].value() is None


# ===========================================================================
# 3. Setor
# ===========================================================================


def test_a_ficha_do_setor_inativo_mostra_a_prontidao_para_ativar(client, cenario):
    antes = client.get(rota("setor", cenario.lab.pk))
    luiza = membro(cenario.lab, "lab-luiza")
    org.designar_chefia(cenario.admin, cenario.lab.pk, luiza.pk)
    depois = client.get(rota("setor", cenario.lab.pk))

    assert [(i["rotulo"], i["atendido"]) for i in antes.context["prontidao"]] == [
        ("Chefe ativo designado", False)
    ]
    assert antes.context["impedimento_ativar"].codigo == org.RECUSA_SETOR_SEM_CHEFE
    assert [i["atendido"] for i in depois.context["prontidao"]] == [True]
    assert depois.context["impedimento_ativar"] is None
    assert "Chefe ativo designado" in texto_principal(depois.content.decode())


def test_a_prontidao_do_almoxarifado_inclui_a_chefia_de_estoque_completa(client, cenario):
    membro(cenario.almoxarifado, "almox-chefe", {Papel.CHEFE_SETOR})

    resposta = client.get(rota("setor", cenario.almoxarifado.pk))

    assert [(i["rotulo"], i["atendido"]) for i in resposta.context["prontidao"]] == [
        ("Chefe ativo designado", True),
        ("Chefia de estoque completa", False),
    ]


def test_a_ficha_do_setor_ativo_nao_traz_prontidao(client, cenario):
    resposta = client.get(rota("setor", cenario.eta.pk))

    assert resposta.context["prontidao"] == []
    assert resposta.context["impedimento_ativar"] is None


def test_designar_sem_candidatos_oferece_cadastrar_no_setor_e_transferir(client, cenario):
    resposta = client.get(rota("setor_chefia", cenario.lab.pk))

    assert resposta.status_code == 200
    esperado = f"{rota('usuario_novo')}?setor={cenario.lab.pk}"
    assert resposta.context["url_cadastrar_no_setor"] == esperado
    assert resposta.context["url_usuarios"] == rota("usuarios")
    assert {esperado, rota("usuarios")} <= hrefs(resposta.content.decode())
    texto = texto_principal(resposta.content.decode())
    assert "Nenhum membro ativo neste setor." in texto
    assert "Nenhum outro membro ativo" not in texto


def test_substituir_sem_outros_candidatos_mantem_o_texto_de_outro_membro(client, cenario):
    resposta = client.get(rota("setor_chefia", cenario.eta.pk))

    texto = texto_principal(resposta.content.decode())
    assert "Nenhum outro membro ativo neste setor." in texto
    assert f"{rota('usuario_novo')}?setor={cenario.eta.pk}" in hrefs(resposta.content.decode())


def test_a_ficha_do_setor_so_marca_chefe_ativo_e_sinaliza_o_chefe_inativo(client, cenario):
    luiza = membro(cenario.lab, "lab-luiza", {Papel.CHEFE_SETOR})
    org.desativar_usuario(cenario.admin, luiza.pk)
    ficha_do_lab = client.get(rota("setor", cenario.lab.pk))
    ficha_da_eta = client.get(rota("setor", cenario.eta.pk))

    do_lab = texto_principal(ficha_do_lab.content.decode())
    da_eta = texto_principal(ficha_da_eta.content.decode())
    assert "Chefe de setor (inativo)" in do_lab
    assert ficha_do_lab.context["chefe"] is None
    assert "Chefe de setor" in da_eta and "(inativo)" not in da_eta


# ===========================================================================
# 4. Prévia da substituição no Almoxarifado
# ===========================================================================


def _almoxarifado_com_substituta(cenario):
    chefe = membro(cenario.almoxarifado, "almox-chefe", PAPEIS_CHEFE_ALMOXARIFADO)
    carla = membro(cenario.almoxarifado, "almox-carla", {Papel.FUNCIONARIO_ALMOXARIFADO})
    org.provisionar_ativacao(cenario.almoxarifado)
    return chefe, carla


def test_a_previa_no_almoxarifado_diz_a_autoridade_de_estoque_que_muda_de_mao(client, cenario):
    chefe, carla = _almoxarifado_com_substituta(cenario)

    resposta = client.post(rota("setor_chefia", cenario.almoxarifado.pk), {"novo_chefe": carla.pk})

    autoridade = resposta.context["autoridade_de_estoque"]
    assert autoridade["anterior"] == chefe and autoridade["novo"] == carla
    assert chefe.nome in autoridade["texto"] and carla.nome in autoridade["texto"]
    texto = texto_principal(resposta.content.decode())
    assert re.sub(r"\s+", " ", autoridade["texto"]) in texto
    for atribuicao in ("estorno", "devolução", "saída excepcional"):
        assert atribuicao in autoridade["texto"]


def test_a_previa_fora_do_almoxarifado_nao_traz_autoridade_de_estoque(client, cenario):
    novo = membro(cenario.eta, "eta-novo")

    resposta = client.post(rota("setor_chefia", cenario.eta.pk), {"novo_chefe": novo.pk})

    assert resposta.status_code == 200
    assert resposta.context["previa"] is not None
    assert resposta.context["autoridade_de_estoque"] is None


def test_a_escolha_do_novo_chefe_nao_traz_autoridade_de_estoque(client, cenario):
    _almoxarifado_com_substituta(cenario)

    resposta = client.get(rota("setor_chefia", cenario.almoxarifado.pk))

    assert resposta.context["autoridade_de_estoque"] is None
