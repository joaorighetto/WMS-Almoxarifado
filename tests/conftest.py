"""Fixtures compartilhadas entre os testes de `contas`.

Mantidas deliberadamente mínimas: apenas o necessário para criar um `Setor`
válido (`INV-ORG-001`) e usuários de teste através do manager real
(`User.objects.create_user`), nunca construindo instâncias manualmente ou
ignorando `set_password()`.
"""

import pathlib

import pytest

from contas.models import Papel, PapelUsuario, Setor, User

SENHA_VALIDA = "uma-senha-de-teste-bastante-forte-123"

FIXTURES_CATALOGO_DIR = pathlib.Path(__file__).parent / "fixtures" / "catalogo"
FIXTURES_FORNECEDORES_DIR = pathlib.Path(__file__).parent / "fixtures" / "fornecedores"


@pytest.fixture
def senha_valida():
    """Senha padrão usada pelos usuários criados por `criar_usuario`."""
    return SENHA_VALIDA


@pytest.fixture
def setor(db):
    """Setor mínimo exigido por `INV-ORG-001` para qualquer `User`."""
    return Setor.objects.create(nome="Almoxarifado Central")


@pytest.fixture
def criar_usuario(db, setor):
    """Factory de usuários de teste, sempre vinculados a um setor válido.

    Gera uma matrícula única por chamada quando nenhuma é informada, para
    permitir criar múltiplos usuários no mesmo teste sem colisão.
    """
    contador = {"valor": 0}

    def _criar_usuario(*, matricula=None, password=None, is_active=True, **extra):
        contador["valor"] += 1
        if matricula is None:
            matricula = f"MAT-TESTE-{contador['valor']:04d}"
        if password is None:
            password = SENHA_VALIDA
        extra.setdefault("setor", setor)
        return User.objects.create_user(
            matricula=matricula, password=password, is_active=is_active, **extra
        )

    return _criar_usuario


@pytest.fixture
def usuario_ativo(criar_usuario):
    """Usuário ativo padrão, com senha `SENHA_VALIDA`."""
    return criar_usuario(matricula="0001234")


# ---------------------------------------------------------------------------
# Papéis de negócio (feature 001 — importação e consulta do catálogo)
# ---------------------------------------------------------------------------
#
# `criar_usuario_com_papeis` delega a `criar_usuario` (acima) a criação da
# conta — mesmo manager real (`create_user`), mesma geração de matrícula única
# — e só acrescenta a concessão explícita dos papéis extra, um de cada vez
# por `PapelUsuario.objects.create` (nunca em lote: `PapelUsuarioQuerySet`
# recusa `bulk_create`).


@pytest.fixture
def criar_usuario_com_papeis(criar_usuario):
    """Factory de usuários de teste com papéis além do `ROLE-REQUESTER`
    mínimo (já concedido por `create_user`).

    Uso: `criar_usuario_com_papeis(Papel.AUDITOR, matricula="...")`. Os
    `**extra` são repassados a `criar_usuario` (`matricula`, `password`,
    `is_active`, `setor`, ...).
    """

    def _criar_usuario_com_papeis(*papeis, **extra):
        usuario = criar_usuario(**extra)
        for papel in papeis:
            PapelUsuario.objects.create(usuario=usuario, papel=papel)
        return usuario

    return _criar_usuario_com_papeis


@pytest.fixture
def chefe_almoxarifado(criar_usuario_com_papeis):
    """Chefe do almoxarifado: `ROLE-WAREHOUSE-STAFF` + `ROLE-SECTOR-HEAD`
    (chefe do setor padrão da suíte) + `ROLE-WAREHOUSE-HEAD`
    (`PERM-SCPI-IMPORT-EXECUTE`, `PERM-SCPI-IMPORT-HISTORY-VIEW`)."""
    return criar_usuario_com_papeis(
        Papel.FUNCIONARIO_ALMOXARIFADO, Papel.CHEFE_SETOR, Papel.CHEFE_ALMOXARIFADO
    )


@pytest.fixture
def funcionario_almoxarifado(criar_usuario_com_papeis):
    """Funcionário do almoxarifado (`ROLE-WAREHOUSE-STAFF`), sem chefia."""
    return criar_usuario_com_papeis(Papel.FUNCIONARIO_ALMOXARIFADO)


@pytest.fixture
def chefe_setor(db, criar_usuario_com_papeis):
    """Chefe de OUTRO setor (`ROLE-SECTOR-HEAD`), sem `ROLE-WAREHOUSE-HEAD`.

    Precisa de um `Setor` próprio: mesmo inativo, um setor só pode ter um
    chefe ativo com `ROLE-SECTOR-HEAD` por vez
    (`_exigir_chefia_nao_duplicada`, `contas/models.py`), e `chefe_almoxarifado`
    já ocupa essa posição no setor padrão desta suíte (fixture `setor`).
    """
    outro_setor = Setor.objects.create(nome="Setor Outro")
    return criar_usuario_com_papeis(Papel.CHEFE_SETOR, setor=outro_setor)


@pytest.fixture
def requisitante(criar_usuario_com_papeis):
    """Identidade de negócio comum, só com `ROLE-REQUESTER`."""
    return criar_usuario_com_papeis()


@pytest.fixture
def auditor(criar_usuario_com_papeis):
    """Gestor/auditor (`ROLE-AUDITOR`)."""
    return criar_usuario_com_papeis(Papel.AUDITOR)


@pytest.fixture
def admin_sistema(criar_usuario_com_papeis):
    """Administrador de sistema (`ROLE-SYSTEM-ADMIN`)."""
    return criar_usuario_com_papeis(Papel.ADMINISTRADOR_SISTEMA)


@pytest.fixture
def superusuario_tecnico(db, setor):
    """Conta TÉCNICA (`create_superuser`): nenhum papel `ROLE-*` de negócio
    (`permissions-matrix.md`, regras 7-8)."""
    return User.objects.create_superuser(
        matricula="9999999", password=SENHA_VALIDA, setor=setor
    )


@pytest.fixture
def csv_fixture():
    """Factory `nome -> bytes` que lê um arquivo de
    `tests/fixtures/catalogo/`, para os testes de importação do catálogo."""

    def _csv_fixture(nome):
        return (FIXTURES_CATALOGO_DIR / nome).read_bytes()

    return _csv_fixture


@pytest.fixture
def csv_fornecedores():
    """Factory `nome -> bytes` que lê um arquivo de
    `tests/fixtures/fornecedores/`, para os testes de importação de
    fornecedores (feature 004). Mesmo padrão de `csv_fixture` (catálogo,
    001); ver `tests/fixtures/fornecedores/README.md` para o que cada
    arquivo cobre e `gerar_fixtures.py`, no mesmo diretório, para como os
    bytes exatos (BOM, CRLF, LF embutido) foram produzidos e verificados."""

    def _csv_fornecedores(nome):
        return (FIXTURES_FORNECEDORES_DIR / nome).read_bytes()

    return _csv_fornecedores
