"""Testes de model do app `contas` (T004, Phase 2 de `specs/005-administracao-usuarios-setores/`).

Substitui o arquivo da 002 (T015). Continua cobrindo a camada de dados (`Setor`,
`UserManager`, `User`, `Papel`, `PapelUsuario`) e acrescenta o que a 005 muda:

- as constraints de `data-model.md`, cada uma com `IntegrityError` e pelo NOME
  (`INV-ORG-004`, FR-025, FR-030) — a defesa é do banco, não da aplicação;
- a BARREIRA DE ESCRITA (research R4): fora de uma operação organizacional,
  `save()`/`delete()` de `Setor` e `PapelUsuario`, `save()` de identidade de
  negócio que altere matrícula/nome/setor/situação/`is_superuser`/
  `senha_provisoria_em`, `delete()` de `User` e os atalhos de `QuerySet`
  (`create`, `bulk_create`, `update`, `bulk_update`, `delete`) levantam
  `ValidationError` e não escrevem nada (FR-046, FR-005);
- o que continua livre: `create_superuser`, `save(update_fields=["last_login"])`
  e `save(update_fields=["password"])` (rehash de senha feito pelo login).

TDD: escrito antes de `contas/organizacao.py` e dos novos campos existirem — falha
inteiro por `ImportError` até lá. Os estados são montados pela API de
provisionamento (T011); só quando é preciso um estado que a aplicação nunca
produz usa-se o marcador de operação (`tests/contas_helpers.py::operacao`).

Invariantes/requisitos protegidos: `INV-ORG-001`, `INV-ORG-004`, FR-001b,
FR-016a, FR-014/FR-015 e FR-025 a FR-030 da 005 (ver cada seção).
"""

import uuid
from types import SimpleNamespace

import pytest
from django.core import serializers
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import Error, IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from contas import organizacao as org
from contas.models import EventoOrganizacional, Papel, PapelUsuario, Setor, TipoEvento, User
from tests.contas_helpers import (
    SENHA_TESTE,
    almoxarifado_ativo,
    estado_descartavel,
    membro,
    operacao,
    setor_ativo,
    validar_tudo,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def setor():
    return org.provisionar_setor("Setor de Teste")


@pytest.fixture
def cenario():
    """Organização válida e pequena: Almoxarifado e ETA ativos (cada um com chefe),
    um membro comum da ETA, um setor vazio e a conta técnica."""
    almox, chefe_almox = almoxarifado_ativo()
    eta, chefe_eta = setor_ativo("ETA", "eta-chefe")
    comum = membro(eta, "eta-comum")
    vazio = org.provisionar_setor("Setor Vazio")
    tecnica = User.objects.create_superuser(
        matricula="tecnica", password=SENHA_TESTE, setor=almox, nome="Conta Técnica"
    )
    return SimpleNamespace(
        almox=almox,
        chefe_almox=chefe_almox,
        eta=eta,
        chefe_eta=chefe_eta,
        comum=comum,
        vazio=vazio,
        tecnica=tecnica,
    )


def _foto():
    """Retrato completo das tabelas organizacionais — igualdade antes/depois
    prova que uma recusa não escreveu, alterou nem removeu nada."""
    return (
        list(Setor.objects.order_by("pk").values()),
        list(User.objects.order_by("pk").values()),
        list(PapelUsuario.objects.order_by("pk").values()),
        EventoOrganizacional.objects.count(),
    )


def _alterar(objeto, **campos):
    for campo, valor in campos.items():
        setattr(objeto, campo, valor)
    objeto.save()


# ---------------------------------------------------------------------------
# Matrícula: identificador opaco (FR-001b)
# ---------------------------------------------------------------------------


def test_matricula_com_zeros_a_esquerda_e_preservada_exatamente(setor):
    usuario = membro(setor, "000123")

    # Força uma volta ao banco: qualquer conversão numérica no caminho de
    # persistência (coluna numérica, cast, normalização) apagaria os zeros.
    recarregado = User.objects.get(pk=usuario.pk)

    assert recarregado.matricula == "000123"
    assert isinstance(recarregado.matricula, str)
    assert recarregado.matricula != "123"


def test_matriculas_com_e_sem_zeros_a_esquerda_sao_identidades_distintas(setor):
    com_zeros = membro(setor, "007")
    sem_zeros = membro(setor, "7")

    assert com_zeros.pk != sem_zeros.pk
    assert User.objects.get(pk=com_zeros.pk).matricula == "007"
    assert User.objects.get(pk=sem_zeros.pk).matricula == "7"


def test_matricula_duplicada_e_rejeitada_pelo_banco(setor):
    membro(setor, "000123")

    with operacao():
        with pytest.raises(IntegrityError), transaction.atomic():
            User(matricula="000123", nome="Outra Pessoa", setor=setor).save()


# ---------------------------------------------------------------------------
# Setor obrigatório (INV-ORG-001)
# ---------------------------------------------------------------------------


def test_create_user_sem_setor_e_rejeitado_pelo_manager():
    with operacao():
        with pytest.raises(ValueError):
            User.objects.create_user(
                matricula="000123", password="senha-valida", setor=None, nome="Sem Setor"
            )

    assert not User.objects.filter(matricula="000123").exists()


def test_usuario_sem_setor_e_rejeitado_pelo_banco_mesmo_contornando_o_manager():
    # NOT NULL em persistência, não só validação de aplicação no manager.
    with operacao():
        with pytest.raises(IntegrityError), transaction.atomic():
            User(matricula="000123", nome="Sem Setor", setor=None).save()


def test_pk_de_setor_inexistente_e_recusado_pelo_banco():
    """`INV-ORG-001` também em persistência: uma PK que não existe não produz
    usuário órfão. A FK é DEFERRABLE INITIALLY DEFERRED; `check_constraints()`
    antecipa a verificação para dentro do bloco. `Error` (e não só
    `IntegrityError`) porque o trigger adiado de R5 também é verificado ali."""
    with operacao():
        with pytest.raises(Error), transaction.atomic():
            User.objects.create_user(matricula="pk-orfao", password="x", setor=999999, nome="Órfão")
            connection.check_constraints()


# ---------------------------------------------------------------------------
# Papéis explícitos, múltiplos, sem herança (FR-014/FR-015; FR-016a)
# ---------------------------------------------------------------------------


def test_chefe_do_almoxarifado_acumula_papeis_distintos_simultaneamente():
    _, chefe = almoxarifado_ativo()

    assert set(chefe.papeis.values_list("papel", flat=True)) == {
        Papel.REQUISITANTE,  # concessão mínima da criação (FR-016a)
        Papel.FUNCIONARIO_ALMOXARIFADO,
        Papel.CHEFE_SETOR,
        Papel.CHEFE_ALMOXARIFADO,
    }
    assert chefe.tem_papel(Papel.FUNCIONARIO_ALMOXARIFADO)
    assert chefe.tem_papel(Papel.CHEFE_SETOR)
    assert chefe.tem_papel(Papel.CHEFE_ALMOXARIFADO)


def test_atribuicao_duplicada_do_mesmo_papel_e_rejeitada_pelo_banco(setor):
    usuario = membro(setor, "000123", {Papel.AUDITOR})

    with operacao():
        with pytest.raises(IntegrityError), transaction.atomic():
            PapelUsuario.objects.create(usuario=usuario, papel=Papel.AUDITOR)

    assert PapelUsuario.objects.filter(usuario=usuario, papel=Papel.AUDITOR).count() == 1


def test_tem_papel_nao_infere_nenhum_outro_papel(setor):
    usuario = membro(setor, "000123", {Papel.CHEFE_SETOR})

    assert usuario.tem_papel(Papel.CHEFE_SETOR) is True
    # Chefe de setor não herda nenhuma capacidade de almoxarifado nem de admin.
    assert usuario.tem_papel(Papel.CHEFE_ALMOXARIFADO) is False
    assert usuario.tem_papel(Papel.FUNCIONARIO_ALMOXARIFADO) is False
    assert usuario.tem_papel(Papel.ADMINISTRADOR_SISTEMA) is False
    # Semântica OR entre vários códigos, sem conceder o que não foi atribuído.
    assert usuario.tem_papel(Papel.CHEFE_ALMOXARIFADO, Papel.FUNCIONARIO_ALMOXARIFADO) is False
    assert usuario.tem_papel(Papel.CHEFE_SETOR, Papel.AUDITOR) is True


def test_identidade_de_negocio_nasce_com_role_requester_e_mais_nada(setor):
    """`FR-016a`: a concessão mínima é uma linha real e persistida, atômica com a
    criação — não um papel derivado em tempo de consulta."""
    usuario = membro(setor, "000123")

    assert list(usuario.papeis.values_list("papel", flat=True)) == [Papel.REQUISITANTE]
    outros = [c.value for c in Papel if c != Papel.REQUISITANTE]
    assert usuario.tem_papel(*outros) is False, "nenhum outro papel é concedido junto"


def test_create_superuser_e_tecnico_e_nao_concede_role_system_admin(setor):
    # `is_staff`/`is_superuser` são mecanismo técnico do Django Admin; a conta
    # técnica não é `ROLE-SYSTEM-ADMIN` (permissions-matrix, regras 7-8; FR-004).
    superusuario = User.objects.create_superuser(
        matricula="000001", password="senha-valida", setor=setor, nome="Conta Técnica"
    )

    assert superusuario.is_staff is True
    assert superusuario.is_superuser is True
    assert PapelUsuario.objects.filter(usuario=superusuario).exists() is False
    assert superusuario.tem_papel(Papel.ADMINISTRADOR_SISTEMA) is False


def test_create_superuser_continua_funcionando_sem_informar_nome(setor):
    """T013 mantém `superusuario_tecnico` inalterado: a fixture chama
    `create_superuser(matricula, password, setor)` SEM `nome`. Como `CHECK nome <> ''`
    vale também para a conta técnica, o manager precisa preencher um nome padrão (por
    exemplo, a matrícula) — ver o relatório do test-engineer."""
    superusuario = User.objects.create_superuser(
        matricula="000009", password="senha-valida", setor=setor
    )

    superusuario.refresh_from_db()
    assert superusuario.is_superuser is True
    assert superusuario.nome.strip() != ""


def test_create_superuser_aceita_setor_como_pk_como_o_createsuperuser_entrega(setor):
    # Para campo de `REQUIRED_FIELDS`, `createsuperuser` entrega a PK do setor, não a
    # instância; o manager precisa aceitar as duas formas.
    superusuario = User.objects.create_superuser(
        matricula="pk-su-01", password="x", setor=setor.pk, nome="Conta Técnica"
    )

    superusuario.refresh_from_db()
    assert superusuario.setor == setor
    assert superusuario.is_staff is True
    assert superusuario.is_superuser is True


def test_comando_createsuperuser_funciona_com_setor_e_nome(setor):
    """Protege o caminho literal de `quickstart.md` §1.2 contra regressão: a conta
    técnica continua criável por `createsuperuser` mesmo com a barreira de escrita."""
    call_command(
        "createsuperuser",
        interactive=False,
        matricula="su-cmd-01",
        setor=setor.pk,
        nome="Conta Técnica",
        verbosity=0,
    )

    criado = User.objects.get(matricula="su-cmd-01")
    assert criado.setor == setor, "INV-ORG-001 preservada pelo caminho do comando"
    assert criado.is_staff is True and criado.is_superuser is True
    assert criado.tem_papel(*[p.value for p in Papel]) is False, (
        "superusuário técnico nunca recebe papel de negócio (permissions-matrix, regras 7-8)"
    )


def test_catalogo_de_papeis_bate_com_os_ids_canonicos():
    # Trava contra redefinição silenciosa do catálogo fechado de papéis: os `value`
    # precisam continuar idênticos aos IDs de `docs/domain/permissions-matrix.md`
    # (a 005 não cria, renomeia nem redefine papéis — FR-003).
    ids_canonicos = {
        "ROLE-REQUESTER",
        "ROLE-SECTOR-ASSISTANT",
        "ROLE-SECTOR-HEAD",
        "ROLE-WAREHOUSE-STAFF",
        "ROLE-WAREHOUSE-HEAD",
        "ROLE-AUDITOR",
        "ROLE-SYSTEM-ADMIN",
    }

    assert {codigo.value for codigo in Papel} == ids_canonicos


# ---------------------------------------------------------------------------
# Constraints de data-model.md — IntegrityError, pelo nome (defesa do banco)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nome_novo", ["ETA", "eta", " ETA ", "  eTa"])
def test_nome_de_setor_e_unico_sem_diferenciar_caixa_nem_espacos_nas_pontas(nome_novo):
    org.provisionar_setor("ETA")

    with operacao():
        with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
            Setor.objects.create(nome=nome_novo)

    assert "setor_nome_unico_normalizado" in str(excinfo.value)
    assert Setor.objects.count() == 1


def test_nomes_diferentes_de_setor_convivem():
    """Controle: a unicidade é por nome normalizado, não por prefixo nem por parte."""
    org.provisionar_setor("ETA")

    org.provisionar_setor("ETA Norte")

    assert Setor.objects.count() == 2


@pytest.mark.parametrize("nome_vazio", ["", "   "])
def test_nome_de_setor_vazio_ou_so_espacos_e_rejeitado_pelo_banco(nome_vazio):
    with operacao():
        with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
            Setor.objects.create(nome=nome_vazio)

    assert "setor_nome_nao_vazio" in str(excinfo.value)


def test_so_um_setor_pode_ser_o_almoxarifado_no_banco():
    org.provisionar_setor("Almoxarifado", almoxarifado=True)

    with operacao():
        with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
            Setor.objects.create(nome="Outro Almoxarifado", almoxarifado=True)

    assert "setor_um_unico_almoxarifado" in str(excinfo.value)
    assert Setor.objects.filter(almoxarifado=True).count() == 1


def test_setor_ativo_sem_ativacao_e_rejeitado_pelo_banco():
    with operacao():
        with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
            Setor.objects.create(nome="Compras", ativo=True)

    assert "setor_ativo_tem_ativacao" in str(excinfo.value)


def test_almoxarifado_ativado_nao_volta_a_inativo_no_banco(cenario):
    """`INV-ORG-004`: a CHECK protege a regra também de um UPDATE direto."""
    with operacao():
        with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
            Setor.objects.filter(pk=cenario.almox.pk).update(ativo=False)

    assert "setor_almoxarifado_nao_desativado" in str(excinfo.value)
    cenario.almox.refresh_from_db()
    assert cenario.almox.ativo is True


def test_setor_comum_ativado_pode_voltar_a_inativo_no_banco(cenario):
    """Controle da CHECK acima: a regra é só do Almoxarifado (FR-028/FR-030 permitem
    desativar e reativar os demais setores)."""
    with estado_descartavel():
        Setor.objects.filter(pk=cenario.eta.pk).update(ativo=False)

        cenario.eta.refresh_from_db()
        assert cenario.eta.ativo is False
        assert cenario.eta.ativado_em is not None, "o histórico de já ter estado ativo permanece"
        validar_tudo()


@pytest.mark.parametrize(
    "campos",
    [{"matricula": "m-sem-nome", "nome": ""}, {"matricula": "", "nome": "Sem Matrícula"}],
    ids=["nome_vazio", "matricula_vazia"],
)
def test_usuario_com_nome_ou_matricula_vazios_e_rejeitado_pelo_banco(setor, campos):
    with operacao():
        with pytest.raises(IntegrityError), transaction.atomic():
            User(setor=setor, **campos).save()


def test_evento_exige_usuario_ou_setor_como_alvo():
    setor = org.provisionar_setor("Alvo")
    usuario = membro(setor, "alvo-01")

    with operacao():
        with pytest.raises(IntegrityError), transaction.atomic():
            EventoOrganizacional.objects.create(tipo=TipoEvento.SETOR_CRIADO, dados={})

        # Controle: qualquer um dos dois alvos basta.
        EventoOrganizacional.objects.create(
            tipo=TipoEvento.SETOR_CRIADO, setor=setor, dados={"controle": 1}
        )
        EventoOrganizacional.objects.create(
            tipo=TipoEvento.USUARIO_EDITADO, usuario=usuario, dados={"controle": 2}
        )


def test_chave_de_confirmacao_e_unica_e_varios_eventos_podem_ficar_sem_chave():
    """A chave é a base da idempotência do cadastro e da redefinição (research R8):
    duas operações com a mesma chave não podem coexistir nem sob corrida."""
    setor = org.provisionar_setor("Chaves")
    chave = uuid.uuid4()

    with operacao():
        EventoOrganizacional.objects.create(
            tipo=TipoEvento.SETOR_RENOMEADO, setor=setor, dados={}, chave_confirmacao=chave
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            EventoOrganizacional.objects.create(
                tipo=TipoEvento.SETOR_RENOMEADO, setor=setor, dados={}, chave_confirmacao=chave
            )
        # Eventos sem chave (a maioria) não colidem entre si.
        EventoOrganizacional.objects.create(tipo=TipoEvento.SETOR_RENOMEADO, setor=setor, dados={})
        EventoOrganizacional.objects.create(tipo=TipoEvento.SETOR_RENOMEADO, setor=setor, dados={})


@pytest.mark.parametrize("alvo", ["setor", "usuario"])
def test_setor_e_usuario_com_historico_nao_podem_ser_excluidos(alvo):
    """Preservação histórica (Constitution IV): as FKs do evento são `PROTECT`. Mesmo
    dentro de uma operação, nada que já tem histórico desaparece."""
    setor = org.provisionar_setor("Com Histórico")
    usuario = membro(setor, "com-historico")
    objeto = {"setor": setor, "usuario": usuario}[alvo]

    with operacao():
        with pytest.raises(ProtectedError), transaction.atomic():
            objeto.delete()

    assert type(objeto).objects.filter(pk=objeto.pk).exists()


# ---------------------------------------------------------------------------
# Barreira de escrita (research R4, FR-046): fora de uma operação, tudo recusado
# ---------------------------------------------------------------------------

_AGORA = timezone.now  # avaliado na chamada, não na coleta


def _com(objeto, **campos):
    for campo, valor in campos.items():
        setattr(objeto, campo, valor)
    return objeto


CASOS_SETOR = [
    pytest.param(lambda c: Setor.objects.create(nome="Novo"), id="setor_create"),
    pytest.param(lambda c: Setor(nome="Novo").save(), id="setor_save_novo"),
    pytest.param(lambda c: _alterar(c.eta, nome="Renomeado"), id="setor_save_nome"),
    pytest.param(lambda c: _alterar(c.eta, ativo=False), id="setor_save_desativar"),
    pytest.param(lambda c: c.vazio.delete(), id="setor_delete"),
    pytest.param(
        lambda c: Setor.objects.filter(pk=c.eta.pk).update(nome="Renomeado"), id="setor_qs_update"
    ),
    pytest.param(
        lambda c: Setor.objects.filter(pk=c.eta.pk).update(ativo=False),
        id="setor_qs_update_ativo",
    ),
    pytest.param(
        lambda c: Setor.objects.bulk_create([Setor(nome="Lote")]), id="setor_qs_bulk_create"
    ),
    pytest.param(
        lambda c: Setor.objects.bulk_update([_com(c.eta, nome="Lote")], ["nome"]),
        id="setor_qs_bulk_update",
    ),
    pytest.param(lambda c: Setor.objects.filter(pk=c.vazio.pk).delete(), id="setor_qs_delete"),
]


def _editar_papel(c):
    atribuicao = c.comum.papeis.get(papel=Papel.REQUISITANTE)
    atribuicao.papel = Papel.AUXILIAR_SETOR
    atribuicao.save()


CASOS_PAPEL = [
    pytest.param(
        lambda c: PapelUsuario.objects.create(usuario=c.comum, papel=Papel.AUDITOR),
        id="papel_create",
    ),
    pytest.param(
        lambda c: PapelUsuario(usuario=c.comum, papel=Papel.AUDITOR).save(), id="papel_save_novo"
    ),
    pytest.param(_editar_papel, id="papel_save_editar"),
    pytest.param(
        lambda c: c.comum.papeis.get(papel=Papel.REQUISITANTE).delete(), id="papel_delete"
    ),
    pytest.param(
        lambda c: PapelUsuario.objects.bulk_create(
            [PapelUsuario(usuario=c.comum, papel=Papel.AUDITOR)]
        ),
        id="papel_qs_bulk_create",
    ),
    pytest.param(
        lambda c: PapelUsuario.objects.filter(usuario=c.comum).update(papel=Papel.AUDITOR),
        id="papel_qs_update",
    ),
    pytest.param(
        lambda c: PapelUsuario.objects.bulk_update(
            [_com(c.comum.papeis.get(papel=Papel.REQUISITANTE), papel=Papel.AUDITOR)], ["papel"]
        ),
        id="papel_qs_bulk_update",
    ),
    pytest.param(lambda c: c.comum.papeis.all().delete(), id="papel_qs_delete"),
]

CASOS_USUARIO = [
    # save() de identidade de negócio que altera cada campo organizacional
    pytest.param(lambda c: _alterar(c.comum, matricula="outra"), id="user_save_matricula"),
    pytest.param(lambda c: _alterar(c.comum, nome="Outro Nome"), id="user_save_nome"),
    pytest.param(lambda c: _alterar(c.comum, setor=c.almox), id="user_save_setor"),
    pytest.param(lambda c: _alterar(c.comum, is_active=False), id="user_save_is_active"),
    pytest.param(lambda c: _alterar(c.comum, is_superuser=True), id="user_save_is_superuser"),
    pytest.param(
        lambda c: _alterar(c.comum, senha_provisoria_em=_AGORA()),
        id="user_save_senha_provisoria_em",
    ),
    # criação e exclusão
    pytest.param(
        lambda c: User(matricula="novo-direto", nome="Novo", setor=c.eta).save(),
        id="user_save_novo",
    ),
    pytest.param(
        lambda c: User.objects.create_user(
            matricula="novo-manager", password="x", setor=c.eta, nome="Novo"
        ),
        id="user_create_user_fora_de_operacao",
    ),
    pytest.param(
        lambda c: User.objects.create(matricula="novo-qs", nome="Novo", setor=c.eta),
        id="user_qs_create",
    ),
    pytest.param(
        lambda c: User.objects.bulk_create([User(matricula="novo-lote", nome="N", setor=c.eta)]),
        id="user_qs_bulk_create",
    ),
    pytest.param(lambda c: c.comum.delete(), id="user_delete"),
    pytest.param(lambda c: User.objects.filter(pk=c.comum.pk).delete(), id="user_qs_delete"),
    # atalhos de QuerySet sobre campos organizacionais
    pytest.param(
        lambda c: User.objects.filter(pk=c.comum.pk).update(is_active=False),
        id="user_qs_update_is_active",
    ),
    pytest.param(
        lambda c: User.objects.filter(pk=c.comum.pk).update(is_superuser=True),
        id="user_qs_update_is_superuser",
    ),
    pytest.param(
        lambda c: User.objects.filter(pk=c.comum.pk).update(setor=c.almox),
        id="user_qs_update_setor",
    ),
    pytest.param(
        lambda c: User.objects.filter(pk=c.comum.pk).update(setor_id=c.almox.pk),
        id="user_qs_update_setor_id",
    ),
    pytest.param(
        lambda c: User.objects.filter(pk=c.comum.pk).update(nome="Outro Nome"),
        id="user_qs_update_nome",
    ),
    pytest.param(
        lambda c: User.objects.filter(pk=c.comum.pk).update(matricula="outra-matricula"),
        id="user_qs_update_matricula",
    ),
    pytest.param(
        lambda c: User.objects.filter(pk=c.comum.pk).update(senha_provisoria_em=_AGORA()),
        id="user_qs_update_senha_provisoria_em",
    ),
    pytest.param(
        lambda c: User.objects.bulk_update([_com(c.comum, is_active=False)], ["is_active"]),
        id="user_qs_bulk_update_is_active",
    ),
    pytest.param(
        lambda c: User.objects.bulk_update([_com(c.comum, setor=c.almox)], ["setor"]),
        id="user_qs_bulk_update_setor",
    ),
    pytest.param(
        lambda c: User.objects.bulk_update([_com(c.comum, nome="Outro")], ["nome"]),
        id="user_qs_bulk_update_nome",
    ),
    pytest.param(
        lambda c: User.objects.bulk_update([_com(c.comum, matricula="outra")], ["matricula"]),
        id="user_qs_bulk_update_matricula",
    ),
]


@pytest.mark.parametrize("escrever", CASOS_SETOR + CASOS_PAPEL + CASOS_USUARIO)
def test_escrita_organizacional_fora_de_operacao_e_recusada_sem_efeito(cenario, escrever):
    antes = _foto()

    with pytest.raises(ValidationError):
        escrever(cenario)

    assert _foto() == antes, "a recusa não pode escrever, alterar nem remover nada"


# Caminhos que não passam por `save()`/`QuerySet` do manager padrão: gerenciadores
# reversos (`add`/`set` atualizam por `_base_manager`) e carga bruta (`loaddata`,
# `deserialize(...).save()` gravam por `save_base(raw=True)`).


def _carga_bruta(*objetos):
    """Grava como o `loaddata`: serializa e salva cada objeto deserializado."""
    dados = serializers.serialize("json", objetos)
    for item in serializers.deserialize("json", dados):
        item.save()


def _loaddata(tmp_path, *objetos):
    arquivo = tmp_path / "carga.json"
    arquivo.write_text(serializers.serialize("json", objetos))
    call_command("loaddata", str(arquivo), verbosity=0)


def _papel_de(usuario, papel):
    return PapelUsuario(usuario=usuario, papel=papel)


CASOS_CAMINHOS_INDIRETOS = [
    pytest.param(lambda c: c.vazio.user_set.add(c.comum), id="reverso_setor_user_add"),
    pytest.param(
        lambda c: c.vazio.user_set.add(c.comum, bulk=False), id="reverso_setor_user_add_sem_bulk"
    ),
    pytest.param(lambda c: c.vazio.user_set.set([c.comum]), id="reverso_setor_user_set"),
    pytest.param(
        lambda c: c.comum.papeis.add(c.chefe_eta.papeis.get(papel=Papel.CHEFE_SETOR)),
        id="reverso_usuario_papeis_add",
    ),
    pytest.param(
        lambda c: c.comum.papeis.add(c.chefe_eta.papeis.get(papel=Papel.CHEFE_SETOR), bulk=False),
        id="reverso_usuario_papeis_add_sem_bulk",
    ),
    pytest.param(
        lambda c: c.comum.papeis.set([c.chefe_eta.papeis.get(papel=Papel.CHEFE_SETOR)]),
        id="reverso_usuario_papeis_set",
    ),
    pytest.param(lambda c: _carga_bruta(_com(c.eta, nome="Raw")), id="raw_setor_alterar"),
    pytest.param(lambda c: _carga_bruta(Setor(pk=9999, nome="Raw Novo")), id="raw_setor_novo"),
    pytest.param(lambda c: _carga_bruta(_com(c.comum, setor=c.almox)), id="raw_user_setor"),
    pytest.param(lambda c: _carga_bruta(_com(c.comum, is_active=False)), id="raw_user_is_active"),
    pytest.param(
        lambda c: _carga_bruta(User(pk=9999, matricula="raw-novo", nome="Raw", setor=c.eta)),
        id="raw_user_novo",
    ),
    pytest.param(lambda c: _carga_bruta(_papel_de(c.comum, Papel.AUDITOR)), id="raw_papel_novo"),
    pytest.param(
        lambda c: _carga_bruta(
            _com(c.comum.papeis.get(papel=Papel.REQUISITANTE), papel=Papel.AUDITOR)
        ),
        id="raw_papel_alterar",
    ),
]


@pytest.mark.parametrize("escrever", CASOS_CAMINHOS_INDIRETOS)
def test_caminhos_indiretos_do_orm_tambem_sao_recusados_sem_efeito(cenario, escrever):
    antes = _foto()

    # `add(bulk=False)` falha dentro de um `atomic` próprio, sem savepoint.
    with pytest.raises(ValidationError), transaction.atomic():
        escrever(cenario)

    assert _foto() == antes, "a recusa não pode escrever, alterar nem remover nada"


@pytest.mark.parametrize("modelo", ["setor", "usuario", "papel"])
def test_loaddata_de_modelo_organizacional_e_recusado_sem_efeito(cenario, tmp_path, modelo):
    objeto = {
        "setor": lambda: _com(cenario.eta, nome="Raw"),
        "usuario": lambda: _com(cenario.comum, setor=cenario.almox),
        "papel": lambda: _papel_de(cenario.comum, Papel.AUDITOR),
    }[modelo]()
    antes = _foto()

    with pytest.raises(ValidationError):
        _loaddata(tmp_path, objeto)

    assert _foto() == antes


def test_caminhos_indiretos_funcionam_dentro_de_uma_operacao(cenario):
    """Controle: os mesmos gerenciadores reversos escrevem quando há operação, então
    as recusas acima vêm da barreira."""
    with operacao():
        cenario.vazio.user_set.add(cenario.comum)
        cenario.comum.papeis.add(_papel_de(cenario.comum, Papel.AUDITOR), bulk=False)
        _carga_bruta(_com(cenario.vazio, nome="Raw Permitido"))

    cenario.comum.refresh_from_db()
    cenario.vazio.refresh_from_db()
    assert cenario.comum.setor_id == cenario.vazio.pk
    assert cenario.comum.tem_papel(Papel.AUDITOR)
    assert cenario.vazio.nome == "Raw Permitido"


def test_a_mesma_escrita_funciona_dentro_de_uma_operacao(cenario):
    """Controle da barreira: o marcador de operação é o que libera a escrita — não
    há outro caminho. Garante que as recusas acima vêm da barreira, não de um erro
    de montagem do cenário."""
    with operacao():
        Setor.objects.create(nome="Dentro da Operação")
        PapelUsuario.objects.create(usuario=cenario.comum, papel=Papel.AUDITOR)
        cenario.comum.nome = "Nome Corrigido"
        cenario.comum.save()

    cenario.comum.refresh_from_db()
    assert cenario.comum.nome == "Nome Corrigido"
    assert cenario.comum.tem_papel(Papel.AUDITOR)
    assert Setor.objects.filter(nome="Dentro da Operação").exists()


def test_barreira_volta_a_valer_depois_da_operacao_mesmo_quando_ela_falha(cenario):
    """Um marcador que "vaza" depois da operação ou de uma exceção deixaria toda a
    barreira aberta pelo resto do processo."""
    with operacao():
        pass
    with pytest.raises(ValidationError):
        Setor.objects.create(nome="Depois da Operação")

    with pytest.raises(RuntimeError), operacao():
        raise RuntimeError("falha no meio da operação")
    with pytest.raises(ValidationError):
        _alterar(cenario.comum, nome="Depois da Falha")

    assert not Setor.objects.filter(nome="Depois da Operação").exists()
    cenario.comum.refresh_from_db()
    assert cenario.comum.nome != "Depois da Falha"


# ---------------------------------------------------------------------------
# O que a barreira NÃO bloqueia (research R4, "ficam liberados")
# ---------------------------------------------------------------------------


def test_last_login_continua_gravavel_fora_de_operacao(cenario):
    cenario.comum.last_login = timezone.now()

    cenario.comum.save(update_fields=["last_login"])

    cenario.comum.refresh_from_db()
    assert cenario.comum.last_login is not None


def test_rehash_de_senha_do_login_continua_funcionando(cenario):
    """O Django regrava o hash no login com `update_fields=["password"]`."""
    cenario.comum.set_password("uma-outra-senha-bem-forte-456")

    cenario.comum.save(update_fields=["password"])

    cenario.comum.refresh_from_db()
    assert cenario.comum.check_password("uma-outra-senha-bem-forte-456")


def test_atalhos_de_queryset_sobre_campos_nao_organizacionais_continuam_livres(cenario):
    User.objects.filter(pk=cenario.comum.pk).update(last_login=timezone.now())
    cenario.comum.last_login = timezone.now()
    User.objects.bulk_update([cenario.comum], ["last_login"])

    cenario.comum.refresh_from_db()
    assert cenario.comum.last_login is not None


def test_conta_tecnica_esta_fora_da_barreira(cenario):
    """A barreira protege a identidade de negócio; `changepassword` da conta técnica
    (`set_password` + `save()`) segue como caminho de manutenção (FR-004)."""
    cenario.tecnica.set_password("a-senha-tecnica-nova-789")

    cenario.tecnica.save()

    cenario.tecnica.refresh_from_db()
    assert cenario.tecnica.check_password("a-senha-tecnica-nova-789")


def test_conta_tecnica_nao_recebe_papel_de_negocio_por_save(cenario):
    """Regressão da 002 (`superusuario_tecnico_nao_pode_receber_papel_por_save`).
    A promoção de identidade com papel a conta técnica por `save()` é o caso
    `user_save_is_superuser` da barreira acima."""
    with pytest.raises(ValidationError):
        PapelUsuario.objects.create(usuario=cenario.tecnica, papel=Papel.ADMINISTRADOR_SISTEMA)

    assert cenario.tecnica.papeis.exists() is False


# ---------------------------------------------------------------------------
# Login: canonicalização da ENTRADA, não do cadastro (FR-001b)
# ---------------------------------------------------------------------------


def test_entrada_do_login_sofre_strip_e_nfkc_do_django_mas_o_cadastro_nao(setor):
    """Documenta a ressalva de `FR-001b` (revisão 3) para travar o texto.

    O `UsernameField` do `AuthenticationForm` nativo aplica `strip` e NFKC à
    **entrada submetida**. O valor já **cadastrado** não é reformulado.
    """
    import unicodedata

    from contas.forms import WMSAuthenticationForm

    campo = WMSAuthenticationForm().fields["username"]

    assert campo.to_python("  000123  ") == "000123", "strip nas pontas"
    assert campo.to_python("００７") == unicodedata.normalize("NFKC", "００７") == "007", (
        "dígitos fullwidth são canonicalizados para NFKC"
    )

    usuario = membro(setor, "000123")
    assert User.objects.get(pk=usuario.pk).matricula == "000123"


def test_mensagem_de_recusa_concorda_em_genero_e_permanece_generica():
    """`FR-003`/`SC-003` preservados, com o português correto (research.md R3 da 002).

    A string é única para as três causas de recusa; a 005 acrescenta o vencimento da
    senha provisória como quarta causa SEM mudar o texto (FR-035).
    """
    from contas.forms import WMSAuthenticationForm

    mensagem = WMSAuthenticationForm().error_messages["invalid_login"]

    assert mensagem == "Matrícula ou senha inválidas. Confira os dados e tente novamente."
    assert "um matrícula" not in mensagem, "desacordo de gênero da tradução nativa"
    for vazamento in ("inativ", "não existe", "inexistente", "incorreta", "venc", "provisória"):
        assert vazamento not in mensagem.lower()
