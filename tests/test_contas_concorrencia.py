"""Concorrência das operações organizacionais (FR-047, research R2/R19) — T031 (US3) e T036 (US4).

Todas as operações de organização tomam o MESMO advisory lock (R2): duas operações simultâneas são
serializadas e a segunda é avaliada sobre o resultado da primeira. Cada teste dispara as duas
operações em threads reais, uma conexão por thread, liberadas juntas por uma `Barrier`
(`rodar_em_threads`) — dois comandos em sequência nunca provariam isso. Como a ordem de chegada ao
lock não é controlável, o que se afirma é a propriedade que importa: o resultado equivale a UMA das
ordens seriais possíveis, e nenhuma outra exceção (deadlock, `IntegrityError`, violação do trigger
adiado) aparece. Cada teste repete a corrida em algumas rodadas, com dados novos, para que as duas
ordens tenham chance de acontecer.

`django_db(transaction=True)`: o lock, o commit e o trigger adiado só existem em transações reais.
As corridas de US5 (desativações — T041) e de US7 (criações e renomeações — T050) são as seções
seguintes.
"""

import pytest

from contas import organizacao as org
from contas.models import Papel, PapelUsuario, Setor, User, chefes_ativos
from tests.contas_helpers import (
    almoxarifado_ativo,
    membro,
    operacao,
    rodar_em_threads,
    setor_ativo,
    validar_tudo,
)

pytestmark = pytest.mark.django_db(transaction=True)

RODADAS = 6


@pytest.fixture
def admin():
    return membro(
        org.provisionar_setor("Administração"), "admin-conc", {Papel.ADMINISTRADOR_SISTEMA}
    )


def _vencedores(resultados):
    """Nomes das operações que terminaram sem exceção."""
    return [nome for nome, r in resultados.items() if not isinstance(r, Exception)]


def _papeis(usuario):
    return {
        Papel(p)
        for p in PapelUsuario.objects.filter(usuario=usuario).values_list("papel", flat=True)
    }


# ===========================================================================
# US3 — alteração de papéis × transferência do mesmo usuário
# ===========================================================================


def test_alteracao_de_papeis_e_transferencia_do_mesmo_usuario_equivalem_a_uma_ordem_serial(admin):
    """O usuário é do Almoxarifado, sem papel de almoxarifado. Uma operação concede
    `ROLE-WAREHOUSE-STAFF`; a outra o transfere para a ETA, com a prévia que viu antes da corrida
    (nada a remover). Ordens seriais possíveis:

    - concessão, depois transferência: a transferência encontra um papel preso que a prévia não
      listava e é recusada como `PreviaDesatualizada` — fica no Almoxarifado, com o papel;
    - transferência, depois concessão: a concessão é recusada (papel de almoxarifado fora do
      Almoxarifado, `INV-ORG-005`) — fica na ETA, sem o papel.

    Nunca "na ETA com o papel de almoxarifado" (nenhuma ordem serial o produz).
    """
    almoxarifado, _ = almoxarifado_ativo()
    eta, _ = setor_ativo("ETA", "eta-chefe")
    for rodada in range(RODADAS):
        alvo = membro(almoxarifado, f"alvo-{rodada}")

        resultados = rodar_em_threads(
            {
                "conceder": lambda alvo=alvo: org.alterar_papeis(
                    admin,
                    alvo.pk,
                    conceder={Papel.FUNCIONARIO_ALMOXARIFADO},
                    remover=set(),
                ),
                "transferir": lambda alvo=alvo: org.transferir_usuario(
                    admin, alvo.pk, eta.pk, papeis_removidos_previstos=set()
                ),
            }
        )

        assert len(_vencedores(resultados)) == 1, resultados
        alvo = User.objects.get(pk=alvo.pk)
        if "conceder" in _vencedores(resultados):
            assert isinstance(resultados["transferir"], org.PreviaDesatualizada), resultados
            assert alvo.setor == almoxarifado
            assert Papel.FUNCIONARIO_ALMOXARIFADO in _papeis(alvo)
        else:
            assert isinstance(resultados["conceder"], org.OperacaoRecusada), resultados
            assert alvo.setor == eta
            assert Papel.FUNCIONARIO_ALMOXARIFADO not in _papeis(alvo)
        validar_tudo()


def test_edicoes_concorrentes_para_a_mesma_matricula_uma_vence_e_a_outra_e_recusada(admin):
    """A segunda é avaliada sobre o resultado da primeira: matrícula repetida, nunca
    `IntegrityError` vazando da constraint única."""
    setor, _ = setor_ativo("ETA", "eta-chefe")
    primeiro = membro(setor, "EDIT-A")
    segundo = membro(setor, "EDIT-B")

    resultados = rodar_em_threads(
        {
            "a": lambda: org.editar_usuario(admin, primeiro.pk, matricula="EDIT-FINAL"),
            "b": lambda: org.editar_usuario(admin, segundo.pk, matricula="EDIT-FINAL"),
        }
    )

    assert len(_vencedores(resultados)) == 1, resultados
    (perdedor,) = [r for r in resultados.values() if isinstance(r, Exception)]
    assert isinstance(perdedor, org.OperacaoRecusada), resultados
    assert User.objects.filter(matricula="EDIT-FINAL").count() == 1
    validar_tudo()


# ===========================================================================
# US4 — substituição de chefia
# ===========================================================================


def _equipe(tipo):
    """Setor ativo com o chefe `m0` e dois candidatos `m1` e `m2` (sem papel algum, nem o de
    funcionário do almoxarifado, que a substituição concede ao novo chefe do Almoxarifado)."""
    if tipo == "almoxarifado":
        setor, chefe = almoxarifado_ativo("conc-alm-m0")
        prefixo = "conc-alm"
    else:
        setor, chefe = setor_ativo("ETA", "conc-eta-m0")
        prefixo = "conc-eta"
    return setor, [chefe, membro(setor, f"{prefixo}-m1"), membro(setor, f"{prefixo}-m2")]


def _quem_tem_o_papel(papel):
    return list(
        User.objects.filter(is_active=True, papeis__papel=papel).values_list("matricula", flat=True)
    )


@pytest.mark.parametrize("tipo", ["comum", "almoxarifado"])
def test_duas_substituicoes_do_mesmo_setor_uma_aplicada_e_a_outra_recusada(admin, tipo):
    """Nunca zero nem dois chefes: as duas partem do mesmo chefe esperado; a que chega depois ao
    lock encontra outro chefe e é recusada. No Almoxarifado, a chefia de estoque acompanha."""
    setor, membros = _equipe(tipo)
    chefe = membros[0]
    for _ in range(RODADAS):
        candidatos = [m for m in membros if m.pk != chefe.pk]

        resultados = rodar_em_threads(
            {
                f"para-{c.matricula}": lambda c=c, chefe=chefe: org.substituir_chefia(
                    admin, setor.pk, chefe_esperado_id=chefe.pk, novo_chefe_id=c.pk
                )
                for c in candidatos
            }
        )

        assert len(_vencedores(resultados)) == 1, resultados
        (perdedora,) = [r for r in resultados.values() if isinstance(r, Exception)]
        assert isinstance(perdedora, org.OperacaoRecusada), resultados
        (nome,) = _vencedores(resultados)
        vencedor = resultados[nome]
        assert [u.pk for u in chefes_ativos(setor.pk)] == [vencedor.pk]
        if tipo == "almoxarifado":
            assert _quem_tem_o_papel(Papel.CHEFE_ALMOXARIFADO) == [vencedor.matricula]
            assert _quem_tem_o_papel(Papel.CHEFE_SETOR) == [vencedor.matricula]
        assert User.objects.get(pk=chefe.pk).is_active, "o chefe anterior continua ativo"
        validar_tudo()
        chefe = vencedor


def test_substituicao_e_transferencia_do_novo_chefe_equivalem_a_uma_ordem_serial(admin):
    """Ordens seriais possíveis, com o candidato `novo` da ETA e a transferência dele para o
    Laboratório (inativo):

    - substituição, depois transferência: ele já é chefe de setor ativo, a transferência é recusada;
    - transferência, depois substituição: ele já é do Laboratório, não pode ser novo chefe da ETA.

    Nunca "chefe da ETA que mora no Laboratório" nem "ETA sem chefe".
    """
    eta, chefe = setor_ativo("ETA", "conc-eta-m0")
    laboratorio = org.provisionar_setor("Laboratório")
    for rodada in range(RODADAS):
        novo = membro(eta, f"conc-novo-{rodada}")
        chefe_anterior = chefe

        resultados = rodar_em_threads(
            {
                "substituir": lambda novo=novo, anterior=chefe_anterior: org.substituir_chefia(
                    admin, eta.pk, chefe_esperado_id=anterior.pk, novo_chefe_id=novo.pk
                ),
                "transferir": lambda novo=novo: org.transferir_usuario(
                    admin, novo.pk, laboratorio.pk, papeis_removidos_previstos=set()
                ),
            }
        )

        assert len(_vencedores(resultados)) == 1, resultados
        novo = User.objects.get(pk=novo.pk)
        if "substituir" in _vencedores(resultados):
            assert isinstance(resultados["transferir"], org.OperacaoRecusada), resultados
            assert [u.pk for u in chefes_ativos(eta.pk)] == [novo.pk]
            assert novo.setor == eta
            chefe = novo
        else:
            assert isinstance(resultados["substituir"], org.OperacaoRecusada), resultados
            assert [u.pk for u in chefes_ativos(eta.pk)] == [chefe_anterior.pk]
            assert novo.setor == laboratorio
        validar_tudo()


# ===========================================================================
# US5 — desativação (T041)
# ===========================================================================


def _administradores_ativos():
    return User.objects.filter(is_active=True, papeis__papel=Papel.ADMINISTRADOR_SISTEMA)


def _desligar(*usuarios):
    """Limpeza entre rodadas: tira da disputa quem sobrou, por escrita direta sob a barreira
    (nenhuma regra do banco impede que o último administrador fique inativo)."""
    with operacao():
        User.objects.filter(pk__in=[u.pk for u in usuarios]).update(is_active=False)


def test_desativacao_concorrente_dos_dois_ultimos_administradores_uma_e_recusada():
    """FR-022: cada um pede a desativação do outro. A que chega depois ao lock encontra o alvo
    como último administrador ativo e é recusada — nunca zero administradores ativos."""
    setor = org.provisionar_setor("Administração")
    for rodada in range(RODADAS):
        a = membro(setor, f"adm-{rodada}-a", {Papel.ADMINISTRADOR_SISTEMA})
        b = membro(setor, f"adm-{rodada}-b", {Papel.ADMINISTRADOR_SISTEMA})

        resultados = rodar_em_threads(
            {
                "a-desativa-b": lambda a=a, b=b: org.desativar_usuario(a, b.pk),
                "b-desativa-a": lambda a=a, b=b: org.desativar_usuario(b, a.pk),
            }
        )

        assert len(_vencedores(resultados)) == 1, resultados
        (perdedora,) = [r for r in resultados.values() if isinstance(r, Exception)]
        assert isinstance(perdedora, org.OperacaoRecusada), resultados
        assert _administradores_ativos().count() == 1, "nunca zero (nem dois) administradores"
        validar_tudo()
        _desligar(a, b)


def test_desativar_um_administrador_e_retirar_o_papel_do_outro_nunca_zeram_os_administradores():
    """Mesma propriedade por dois caminhos: a desativação de B e a retirada de
    `ROLE-SYSTEM-ADMIN` de A. Em qualquer ordem serial a segunda é recusada."""
    setor = org.provisionar_setor("Administração")
    for rodada in range(RODADAS):
        a = membro(setor, f"adm-{rodada}-a", {Papel.ADMINISTRADOR_SISTEMA})
        b = membro(setor, f"adm-{rodada}-b", {Papel.ADMINISTRADOR_SISTEMA})

        resultados = rodar_em_threads(
            {
                "desativar-b": lambda a=a, b=b: org.desativar_usuario(a, b.pk),
                "retirar-papel-de-a": lambda a=a, b=b: org.alterar_papeis(
                    b, a.pk, conceder=set(), remover={Papel.ADMINISTRADOR_SISTEMA}
                ),
            }
        )

        assert len(_vencedores(resultados)) == 1, resultados
        (perdedora,) = [r for r in resultados.values() if isinstance(r, Exception)]
        assert isinstance(perdedora, org.OperacaoRecusada), resultados
        assert _administradores_ativos().count() == 1
        validar_tudo()
        _desligar(a, b)
        with operacao():  # devolve o papel retirado, para a próxima rodada começar limpa
            PapelUsuario.objects.get_or_create(usuario=a, papel=Papel.ADMINISTRADOR_SISTEMA)


def test_ativacao_de_setor_e_desativacao_do_unico_chefe_nunca_vencem_juntas(admin):
    """Regressão da 002 (FR-021 e FR-020): ativar o setor e desativar o único chefe ao mesmo
    tempo. Ordens seriais possíveis: ativação primeiro (a desativação é recusada: chefe de setor
    ativo) ou desativação primeiro (a ativação é recusada: sem chefe ativo). Nunca "setor ativo
    com chefe inativo"."""
    for rodada in range(RODADAS):
        setor = org.provisionar_setor(f"Setor {rodada}")
        chefe = membro(setor, f"chefe-{rodada}", {Papel.CHEFE_SETOR})

        resultados = rodar_em_threads(
            {
                "ativacao": lambda setor=setor: org.provisionar_ativacao(setor),
                "desativacao": lambda chefe=chefe: org.desativar_usuario(admin, chefe.pk),
            }
        )

        assert len(_vencedores(resultados)) == 1, resultados
        (perdedora,) = [r for r in resultados.values() if isinstance(r, Exception)]
        assert isinstance(perdedora, org.OperacaoRecusada), resultados
        setor = Setor.objects.get(pk=setor.pk)
        chefe = User.objects.get(pk=chefe.pk)
        if "ativacao" in _vencedores(resultados):
            assert setor.ativo and chefe.is_active
        else:
            assert not setor.ativo and not chefe.is_active
        validar_tudo()


# ===========================================================================
# US7 — setores (T050)
# ===========================================================================


def test_ativar_setor_e_desativar_o_unico_chefe_nunca_vencem_juntas(admin):
    """A mesma corrida pela operação `ativar_setor` (a anterior usa o provisionamento)."""
    for rodada in range(RODADAS):
        setor = org.provisionar_setor(f"Setor ativo {rodada}")
        chefe = membro(setor, f"chefe-ativo-{rodada}", {Papel.CHEFE_SETOR})

        resultados = rodar_em_threads(
            {
                "ativacao": lambda setor=setor: org.ativar_setor(admin, setor.pk),
                "desativacao": lambda chefe=chefe: org.desativar_usuario(admin, chefe.pk),
            }
        )

        assert len(_vencedores(resultados)) == 1, resultados
        (perdedora,) = [r for r in resultados.values() if isinstance(r, Exception)]
        assert isinstance(perdedora, org.OperacaoRecusada), resultados
        setor = Setor.objects.get(pk=setor.pk)
        assert not (setor.ativo and not User.objects.get(pk=chefe.pk).is_active)
        validar_tudo()


def _setores_com_o_nome(nome):
    return [s for s in Setor.objects.all() if s.nome.strip().lower() == nome.strip().lower()]


def test_criacoes_concorrentes_para_o_mesmo_nome_uma_e_recusada(admin):
    """A segunda é avaliada sobre o resultado da primeira: nome repetido (FR-025) — recusa de
    domínio, nunca um `IntegrityError` da constraint vazando."""
    for rodada in range(RODADAS):
        nome = f"Laboratório {rodada}"

        resultados = rodar_em_threads(
            {
                "a": lambda nome=nome: org.criar_setor(admin, nome=nome),
                "b": lambda nome=nome: org.criar_setor(admin, nome=f"  {nome.upper()} "),
            }
        )

        assert len(_vencedores(resultados)) == 1, resultados
        (perdedora,) = [r for r in resultados.values() if isinstance(r, Exception)]
        assert isinstance(perdedora, org.OperacaoRecusada), resultados
        assert len(_setores_com_o_nome(nome)) == 1
        validar_tudo()


def test_renomeacoes_concorrentes_para_o_mesmo_nome_uma_e_recusada(admin):
    for rodada in range(RODADAS):
        primeiro = org.provisionar_setor(f"Origem A {rodada}")
        segundo = org.provisionar_setor(f"Origem B {rodada}")
        nome = f"Destino {rodada}"

        resultados = rodar_em_threads(
            {
                "a": lambda s=primeiro, nome=nome: org.renomear_setor(admin, s.pk, nome=nome),
                "b": lambda s=segundo, nome=nome: org.renomear_setor(
                    admin, s.pk, nome=f" {nome.lower()}  "
                ),
            }
        )

        assert len(_vencedores(resultados)) == 1, resultados
        (perdedora,) = [r for r in resultados.values() if isinstance(r, Exception)]
        assert isinstance(perdedora, org.OperacaoRecusada), resultados
        assert len(_setores_com_o_nome(nome)) == 1
        validar_tudo()


def test_criacao_e_renomeacao_concorrentes_para_o_mesmo_nome_uma_e_recusada(admin):
    for rodada in range(RODADAS):
        existente = org.provisionar_setor(f"Existente {rodada}")
        nome = f"Disputado {rodada}"

        resultados = rodar_em_threads(
            {
                "criar": lambda nome=nome: org.criar_setor(admin, nome=nome),
                "renomear": lambda s=existente, nome=nome: org.renomear_setor(
                    admin, s.pk, nome=nome.upper()
                ),
            }
        )

        assert len(_vencedores(resultados)) == 1, resultados
        (perdedora,) = [r for r in resultados.values() if isinstance(r, Exception)]
        assert isinstance(perdedora, org.OperacaoRecusada), resultados
        assert len(_setores_com_o_nome(nome)) == 1
        validar_tudo()
