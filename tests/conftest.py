"""Fixtures compartilhadas entre os testes de `contas`.

Mantidas deliberadamente mínimas: apenas o necessário para criar um `Setor`
válido (`INV-ORG-001`) e usuários de teste através do manager real
(`User.objects.create_user`), nunca construindo instâncias manualmente ou
ignorando `set_password()`.

A seção final (`execucao_catalogo`, `criar_material`, `execucao_fornecedores`,
`criar_fornecedor`) foi acrescentada pelo `test-engineer` (T003, spec
003-entrada-materiais) para popular `catalogo.Material` e
`fornecedores.Fornecedor` diretamente pelo ORM nos testes de `estoque` — não é
caminho de produto (só `catalogo.importacao`/`fornecedores.importacao` criam
esses registros de verdade; `INV-CATALOG-003`, `INV-SUPPLIER-003`), apenas
dados fictícios para exercitar `estoque.entradas` sem depender do parser CSV.
"""

import pathlib
import uuid
from decimal import Decimal

import pytest
from django.utils import timezone

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


# ---------------------------------------------------------------------------
# Dados de estoque (spec 003 — entrada de materiais): Material/Fornecedor
# criados diretamente pelo ORM, sem passar pelo parser CSV nem por
# `aplicar_plano`. Servem só para popular as FKs que `estoque.entradas`
# consome; a criação real de Material/Fornecedor é exclusiva das importações
# (`INV-CATALOG-003`, `INV-SUPPLIER-003` — ver `tests/test_catalogo_sem_
# criacao_manual.py`/`tests/test_fornecedores_sem_criacao_manual.py`, que
# continuam sendo a defesa real dessas invariantes).
# ---------------------------------------------------------------------------


@pytest.fixture
def execucao_catalogo(criar_usuario):
    """Uma `catalogo.ExecucaoImportacao` mínima e válida (totais zerados,
    identidade fechada respeitada), só para servir de `execucao_origem` aos
    materiais criados por `criar_material`."""
    from catalogo.models import ExecucaoImportacao

    return ExecucaoImportacao.objects.create(
        token_previa=uuid.uuid4(),
        executada_por=criar_usuario(matricula="EXEC-CATALOGO-ESTOQUE"),
        concluida_em=timezone.now(),
        nome_arquivo="fixture_estoque.csv",
        tamanho_arquivo=1,
        sha256_arquivo="0" * 64,
        total_recebidos=0,
        total_inseridos=0,
        total_atualizados=0,
        total_atualizados_com_alteracao=0,
        total_rejeitados=0,
        total_divergencias=0,
        total_ausentes_no_arquivo=0,
    )


@pytest.fixture
def criar_material(execucao_catalogo):
    """Factory `catalogo.Material` para os testes de `estoque`.

    `descricao_busca` é derivado por `normalizar_para_busca`, exatamente como
    `catalogo.importacao.aplicar_plano` faz — a busca de material da
    composição da entrada (`contracts/composicao-entrada.md`, R9) depende
    dessa mesma normalização.
    """
    from catalogo.leitura_scpi import normalizar_para_busca
    from catalogo.models import Material

    def _criar_material(cadpro, saldo, unidade="UN", descricao=None):
        if descricao is None:
            descricao = f"Material de teste {cadpro}"
        saldo = Decimal(saldo)
        return Material.objects.create(
            cadpro=cadpro,
            descricao=descricao,
            descricao_busca=normalizar_para_busca(descricao),
            unidade=unidade,
            detalhamento="",
            grupo="",
            subgrupo="",
            nome_grupo="",
            nome_subgrupo="",
            saldo=saldo,
            saldo_inicial=saldo,
            execucao_origem=execucao_catalogo,
        )

    return _criar_material


@pytest.fixture
def execucao_fornecedores(criar_usuario):
    """Uma `fornecedores.ExecucaoImportacaoFornecedores` mínima e válida, só
    para servir de `execucao_origem` aos fornecedores de `criar_fornecedor`."""
    from fornecedores.models import ExecucaoImportacaoFornecedores

    return ExecucaoImportacaoFornecedores.objects.create(
        token_previa=uuid.uuid4(),
        executada_por=criar_usuario(matricula="EXEC-FORNECEDORES-ESTOQUE"),
        concluida_em=timezone.now(),
        nome_arquivo="fixture_estoque.csv",
        tamanho_arquivo=1,
        sha256_arquivo="0" * 64,
        total_recebidos=0,
        total_inseridos=0,
        total_atualizados=0,
        total_atualizados_com_alteracao=0,
        total_rejeitados=0,
        total_ausentes_no_arquivo=0,
    )


@pytest.fixture
def criar_fornecedor(execucao_fornecedores):
    """Factory `fornecedores.Fornecedor` para os testes de `estoque`.

    `documento_digitos` e `nome_busca` derivados exatamente como
    `fornecedores.importacao.aplicar_plano` faz, para que a busca de emitente
    da composição da entrada (`contracts/composicao-entrada.md`, R9) encontre
    os fornecedores de fixture do mesmo jeito que encontraria um fornecedor
    importado de verdade.
    """
    from catalogo.leitura_scpi import normalizar_para_busca
    from fornecedores.leitura_fornecedores import somente_digitos
    from fornecedores.models import Fornecedor

    def _criar_fornecedor(codif, nome, bloqueado=False, documento=""):
        return Fornecedor.objects.create(
            codif=codif,
            nome=nome,
            nome_fantasia="",
            documento=documento,
            documento_digitos=somente_digitos(documento),
            tipo="",
            bloqueado=bloqueado,
            motivo_bloqueio="Bloqueado no SCPI (fixture de teste)." if bloqueado else "",
            tipo_bloqueio="B" if bloqueado else "",
            nome_busca=normalizar_para_busca(nome),
            execucao_origem=execucao_fornecedores,
        )

    return _criar_fornecedor
