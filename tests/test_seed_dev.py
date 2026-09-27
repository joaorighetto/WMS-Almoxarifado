"""Bootstrap de desenvolvimento: dados reais de domínio, isolamento e repetição segura.

Os testes importam somente a fixture sintética compartilhada. Não dependem do
catálogo local nem de rede. INV-ORG-001/002/003, INV-AUTH-001,
INV-CATALOG-001/003/004/005 e INV-STOCK-001/002/003/004.
"""

import os
import threading
import uuid
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth import authenticate
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import override_settings

from catalogo.leitura_scpi import ler_registros
from catalogo.models import (
    CAMPOS_CADASTRAIS_ATUALIZAVEIS,
    AlteracaoCadastralMaterial,
    DivergenciaSaldo,
    ExcecaoImportacao,
    ExecucaoImportacao,
    Material,
    MotivoRecusa,
)
from contas.models import Papel, PapelUsuario, Setor, User
from fornecedores.models import (
    AlteracaoFornecedor,
    ExcecaoImportacaoFornecedores,
    ExecucaoImportacaoFornecedores,
    Fornecedor,
)

CATALOGO = Path(__file__).parent / "fixtures" / "catalogo" / "carga_inicial_valida.csv"
# Fixture sintética de fornecedores (feature 004, T033) — nunca o arquivo real
# `docs/CSVs/fornecedores.csv` (proibido nos testes: dado real sensível, fora do
# Git). Um caminho garantidamente inexistente, para os testes que exercitam a
# ausência do arquivo sem depender de nada do sistema de arquivos local.
FORNECEDORES_VALIDO = Path(__file__).parent / "fixtures" / "fornecedores" / "valido_basico.csv"
FORNECEDORES_INEXISTENTE = (
    Path(__file__).parent / "fixtures" / "fornecedores" / "__inexistente_para_teste__.csv"
)
MODELOS = (
    Setor,
    User,
    PapelUsuario,
    Material,
    ExecucaoImportacao,
    ExcecaoImportacao,
    DivergenciaSaldo,
    AlteracaoCadastralMaterial,
)
MODELOS_FORNECEDORES = (
    Fornecedor,
    ExecucaoImportacaoFornecedores,
    ExcecaoImportacaoFornecedores,
    AlteracaoFornecedor,
)


@pytest.fixture(autouse=True)
def ambiente_dev(monkeypatch, senha_valida):
    monkeypatch.setenv("SEED_DEV_PASSWORD", senha_valida)
    # Cada override cria UserSettingsHolder, cujo SETTINGS_MODULE padrão é
    # None: aplicar as duas opções juntas evita mascarar o módulo selecionado.
    with override_settings(
        SETTINGS_MODULE="config.settings.development",
        PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    ):
        yield


def executar_seed(**opcoes):
    """`fornecedores` (opcional) SEMPRE vira um `--fornecedores CAMINHO`
    explícito — por padrão um caminho garantidamente inexistente
    (`FORNECEDORES_INEXISTENTE`), nunca o padrão real do comando
    (`docs/CSVs/fornecedores.csv`), para nenhum teste depender do arquivo real
    local (proibido: dado real sensível, fora do Git)."""
    saida = StringIO()
    fornecedores = opcoes.pop("fornecedores", FORNECEDORES_INEXISTENTE)
    call_command(
        "seed_dev",
        "--catalogo",
        str(CATALOGO),
        "--fornecedores",
        str(fornecedores),
        stdout=saida,
        **opcoes,
    )
    return saida.getvalue()


def estado_dominio():
    return {
        modelo._meta.label: list(modelo.objects.order_by("pk").values())
        for modelo in MODELOS
    }


@pytest.mark.parametrize("modulo", ["config.settings.production", "config.settings.test"])
def test_recusa_ambiente_fora_development_mesmo_com_debug(modulo):
    """Sem acesso ao banco: a guarda antecede qualquer consulta/gravação."""
    with override_settings(SETTINGS_MODULE=modulo, DEBUG=True):
        with pytest.raises(CommandError, match="development"):
            executar_seed()


def test_check_valida_precondicoes_sem_acessar_banco(senha_valida):
    saida = executar_seed(check=True)
    assert senha_valida not in saida


@pytest.mark.parametrize("senha", [None, "12345678"])
def test_check_recusa_senha_ausente_ou_fraca_sem_acessar_banco(monkeypatch, senha):
    if senha is None:
        monkeypatch.delenv("SEED_DEV_PASSWORD")
    else:
        monkeypatch.setenv("SEED_DEV_PASSWORD", senha)
    with pytest.raises(CommandError, match="SEED_DEV_PASSWORD"):
        executar_seed(check=True)


def test_check_recusa_catalogo_inexistente_sem_acessar_banco():
    with pytest.raises(CommandError, match="catálogo SCPI"):
        call_command(
            "seed_dev", "--catalogo", str(CATALOGO.with_name("inexistente.csv")), check=True
        )


def test_catalogo_padrao_fica_em_docs_csvs(monkeypatch, tmp_path):
    """Sem `--catalogo`, o seed lê `docs/CSVs/` (mesma pasta local e ignorada do
    CSV de fornecedores). `BASE_DIR` aponta para um diretório temporário com a
    fixture sintética: o teste nunca toca o arquivo real."""
    from django.conf import settings

    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    destino = tmp_path / "docs" / "CSVs" / "relacao-de-todos-produtos-importados-do-SCPI.csv"
    destino.parent.mkdir(parents=True)
    destino.write_bytes(CATALOGO.read_bytes())

    call_command(
        "seed_dev", "--fornecedores", str(FORNECEDORES_INEXISTENTE), check=True,
        stdout=StringIO(),
    )


def test_catalogo_padrao_ausente_indica_docs_csvs(monkeypatch, tmp_path):
    from django.conf import settings

    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)

    with pytest.raises(CommandError, match="docs/CSVs"):
        call_command(
            "seed_dev", "--fornecedores", str(FORNECEDORES_INEXISTENTE), check=True
        )


@pytest.mark.django_db
def test_seed_cria_organizacao_com_papeis_explicitos_e_credenciais_validas(senha_valida):
    saida = executar_seed()
    assert senha_valida not in saida
    assert 25 <= User.objects.count() <= 35
    assert 6 <= Setor.objects.count() <= 8
    assert Setor.objects.filter(ativo=True).exists()
    assert Setor.objects.filter(ativo=False).exists()
    assert set(PapelUsuario.objects.values_list("papel", flat=True)) == set(Papel.values)
    assert PapelUsuario.objects.count() == 52

    for setor in Setor.objects.filter(ativo=True):
        assert User.objects.filter(
            setor=setor, is_active=True, papeis__papel=Papel.CHEFE_SETOR
        ).count() == 1

    for usuario in User.objects.prefetch_related("papeis"):
        assert usuario.setor_id is not None
        assert usuario.check_password(senha_valida)
        papeis = {atribuicao.papel for atribuicao in usuario.papeis.all()}
        if usuario.is_superuser:
            assert not papeis
        else:
            assert Papel.REQUISITANTE in papeis
        if Papel.CHEFE_ALMOXARIFADO in papeis:
            assert {
                Papel.REQUISITANTE,
                Papel.CHEFE_SETOR,
                Papel.FUNCIONARIO_ALMOXARIFADO,
                Papel.CHEFE_ALMOXARIFADO,
            } <= papeis

    assert User.objects.filter(is_superuser=True).count() == 1
    inativos = list(User.objects.filter(is_active=False))
    assert inativos
    for usuario in inativos:
        assert usuario.papeis.exists()
        assert authenticate(matricula=usuario.matricula, password=senha_valida) is None

    chefe = User.objects.get(is_active=True, papeis__papel=Papel.CHEFE_ALMOXARIFADO)
    assert authenticate(matricula=chefe.matricula, password=senha_valida) == chefe


# ---------------------------------------------------------------------------
# Fornecedores (feature 004, T033) — opcional: ausência emite aviso e não
# falha; presença importa pelo mesmo `confirmar_importacao` da aplicação;
# saída do comando nunca vaza dado do arquivo, só totais.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_seed_sem_arquivo_de_fornecedores_emite_aviso_e_nao_falha():
    """`executar_seed()` já passa `--fornecedores` apontando para um caminho
    inexistente (ver docstring de `executar_seed`) — o cenário padrão desta
    suíte é justamente a ausência do arquivo."""
    saida = executar_seed()

    assert "seed_dev concluído" in saida
    assert "fornecedores" in saida.lower()
    assert any(palavra in saida.lower() for palavra in ("aviso", "pulad", "não encontrado")), saida
    assert not any(modelo.objects.exists() for modelo in MODELOS_FORNECEDORES)


@pytest.mark.django_db
def test_seed_importa_fornecedores_quando_arquivo_informado(senha_valida):
    saida = executar_seed(fornecedores=str(FORNECEDORES_VALIDO))

    assert Fornecedor.objects.count() == 4
    execucao = ExecucaoImportacaoFornecedores.objects.get()
    assert execucao.total_recebidos == execucao.total_inseridos == 4
    assert execucao.total_atualizados == execucao.total_rejeitados == 0
    chefe = User.objects.get(is_active=True, papeis__papel=Papel.CHEFE_ALMOXARIFADO)
    assert execucao.executada_por_id == chefe.pk

    # Saída só com totais — nunca nome, documento ou qualquer valor do
    # arquivo (INV-SUPPLIER-004): a fixture `valido_basico.csv` tem
    # fornecedores nomeados "FORNECEDOR ALFA COMERCIO LTDA" e o documento
    # "11.111.111/0001-11"; nenhum dos dois pode vazar para stdout.
    assert "FORNECEDOR ALFA" not in saida.upper()
    assert "11.111.111/0001-11" not in saida
    assert str(execucao.total_inseridos) in saida


@pytest.mark.django_db
def test_reexecucao_com_fornecedores_nao_falha_nem_duplica(senha_valida):
    """Rodar o seed duas vezes com o mesmo arquivo de fornecedores não pode
    falhar nem duplicar: a segunda chamada é interceptada pelo mesmo
    early-return que já protege organização/catálogo (`SEED_TOKENS`) — a
    importação de fornecedores nunca chega a ser tentada de novo (ver
    docstring de `Command.handle`)."""
    executar_seed(fornecedores=str(FORNECEDORES_VALIDO))
    assert Fornecedor.objects.count() == 4

    saida = executar_seed(fornecedores=str(FORNECEDORES_VALIDO))

    assert "já aplicado" in saida
    assert Fornecedor.objects.count() == 4
    assert ExecucaoImportacaoFornecedores.objects.count() == 1


@pytest.mark.django_db
def test_check_com_arquivo_de_fornecedores_invalido_falha_sem_acessar_banco():
    invalido = Path(__file__).parent / "fixtures" / "fornecedores" / "sem_coluna_bloq.csv"

    with pytest.raises(CommandError, match="fornecedores"):
        call_command(
            "seed_dev",
            "--catalogo",
            str(CATALOGO),
            "--fornecedores",
            str(invalido),
            check=True,
        )


@pytest.mark.django_db
def test_arquivo_de_fornecedores_invalido_nao_grava_nada():
    invalido = Path(__file__).parent / "fixtures" / "fornecedores" / "sem_coluna_bloq.csv"

    with pytest.raises(CommandError, match="fornecedores"):
        executar_seed(fornecedores=str(invalido))

    assert not any(modelo.objects.exists() for modelo in MODELOS)
    assert not any(modelo.objects.exists() for modelo in MODELOS_FORNECEDORES)


@pytest.mark.django_db
def test_seed_preserva_catalogo_original_e_produz_historico_completo():
    executar_seed()
    inicial, revisao, restauracao = ExecucaoImportacao.objects.order_by("pk")
    registros = ler_registros(CATALOGO.read_bytes()).aceitos
    assert Material.objects.count() == len(registros) == 9

    for registro in registros:
        material = Material.objects.get(cadpro=registro.cadpro)
        assert material.execucao_origem_id == inicial.pk
        assert material.saldo == material.saldo_inicial == registro.quantidade
        for campo in CAMPOS_CADASTRAIS_ATUALIZAVEIS:
            assert getattr(material, campo) == getattr(registro, campo)

    assert Material.objects.get(cadpro="000.000.002").saldo == Decimal("0")
    assert Material.objects.get(cadpro="010.020.032").saldo == Decimal("1234.500")
    assert Material.objects.get(cadpro="000.029.742").saldo == Decimal("53.400")
    assert set(Material.objects.values_list("unidade", flat=True)) == {
        "UN", "UND", "M", "MT", "MTS"
    }
    assert inicial.total_inseridos == 9
    assert revisao.total_inseridos == restauracao.total_inseridos == 0
    assert restauracao.total_atualizados == 9
    assert inicial.sha256_arquivo == restauracao.sha256_arquivo
    assert inicial.sha256_arquivo != revisao.sha256_arquivo
    assert set(revisao.excecoes.values_list("motivo", flat=True)) == set(MotivoRecusa.values)
    assert revisao.divergencias.filter(diferenca__gt=0).exists()
    assert revisao.divergencias.filter(diferenca__lt=0).exists()
    assert restauracao.total_divergencias == 0
    assert set(revisao.alteracoes.values_list("campo", flat=True)) == set(
        CAMPOS_CADASTRAIS_ATUALIZAVEIS
    )

    for alteracao in revisao.alteracoes.all():
        retorno = restauracao.alteracoes.get(material=alteracao.material, campo=alteracao.campo)
        assert alteracao.valor_anterior != alteracao.valor_novo
        assert retorno.valor_anterior == alteracao.valor_novo
        assert retorno.valor_novo == alteracao.valor_anterior

    for divergencia in DivergenciaSaldo.objects.select_related("material"):
        assert divergencia.diferenca == divergencia.saldo_arquivo - divergencia.saldo_wms
        assert divergencia.material.saldo == divergencia.saldo_wms

    for execucao in (inicial, revisao, restauracao):
        assert execucao.executada_por.papeis.filter(papel=Papel.CHEFE_ALMOXARIFADO).exists()
        assert execucao.total_recebidos == (
            execucao.total_inseridos + execucao.total_atualizados + execucao.total_rejeitados
        )
        assert execucao.total_rejeitados == execucao.excecoes.count()
        assert execucao.total_divergencias == execucao.divergencias.count()
        assert execucao.total_atualizados_com_alteracao == (
            execucao.alteracoes.values("material_id").distinct().count()
        )


@pytest.mark.django_db
def test_reexecucao_preserva_todos_dados_mesmo_sem_senha_e_catalogo(monkeypatch):
    executar_seed()
    usuario = User.objects.filter(is_superuser=False, is_active=True).first()
    usuario.set_password("senha-alterada-pelo-desenvolvedor-987")
    usuario.save()
    setor = Setor.objects.filter(ativo=False).first()
    setor.nome = "Nome alterado depois do bootstrap"
    setor.save()
    antes = estado_dominio()
    monkeypatch.delenv("SEED_DEV_PASSWORD")

    call_command(
        "seed_dev", "--catalogo", str(CATALOGO.with_name("inexistente.csv")), stdout=StringIO()
    )

    assert estado_dominio() == antes
    usuario.refresh_from_db()
    assert usuario.check_password("senha-alterada-pelo-desenvolvedor-987")


@pytest.mark.django_db
@pytest.mark.parametrize("tipo", ["setor", "usuario", "superusuario"])
def test_recusa_dados_preexistentes_sem_modifica_los(tipo, senha_valida):
    setor = Setor.objects.create(nome="Setor preexistente")
    if tipo == "usuario":
        User.objects.create_user(matricula="EXISTENTE", password=senha_valida, setor=setor)
    elif tipo == "superusuario":
        User.objects.create_superuser(matricula="TECNICO", password=senha_valida, setor=setor)
    antes = estado_dominio()

    with pytest.raises(CommandError):
        executar_seed()

    assert estado_dominio() == antes


@pytest.mark.django_db
@pytest.mark.parametrize("tokens_ausentes", [1, 2, 3])
def test_tokens_incompletos_nao_sao_tratados_como_seed_concluido(tokens_ausentes):
    executar_seed()
    for execucao in ExecucaoImportacao.objects.order_by("pk")[:tokens_ausentes]:
        ExecucaoImportacao.objects.filter(pk=execucao.pk).update(token_previa=uuid.uuid4())
    antes = estado_dominio()

    with pytest.raises(CommandError):
        executar_seed()

    assert estado_dominio() == antes


@pytest.mark.django_db(transaction=True)
def test_falha_na_terceira_importacao_desfaz_organizacao_catalogo_e_historico():
    from contas.management.commands import seed_dev

    confirmar = seed_dev.confirmar_importacao
    chamadas = []

    def falhar_apos_segunda_importacao(*args, **kwargs):
        chamadas.append(args)
        if len(chamadas) == 3:
            assert ExecucaoImportacao.objects.count() == 2
            assert Material.objects.exists()
            assert AlteracaoCadastralMaterial.objects.exists()
            assert ExcecaoImportacao.objects.exists()
            raise RuntimeError("falha simulada na terceira importação")
        return confirmar(*args, **kwargs)

    with patch.object(seed_dev, "confirmar_importacao", side_effect=falhar_apos_segunda_importacao):
        with pytest.raises(RuntimeError, match="falha simulada"):
            executar_seed()

    assert len(chamadas) == 3
    assert all(not modelo.objects.exists() for modelo in MODELOS)
    executar_seed()
    assert ExecucaoImportacao.objects.count() == 3
    assert Material.objects.count() == 9


@pytest.mark.django_db(transaction=True)
def test_duas_execucoes_concorrentes_criam_um_unico_seed():
    assert connection.vendor == "postgresql", "o contrato de locking exige PostgreSQL real"
    barreira = threading.Barrier(2)
    resultados = {}

    def executar_em_thread(nome):
        primeiro_lock = True

        def sincronizar_lock(execute, sql, params, many, context):
            nonlocal primeiro_lock
            if primeiro_lock and "pg_advisory_xact_lock" in sql:
                primeiro_lock = False
                barreira.wait(timeout=10)
            return execute(sql, params, many, context)

        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '10s'")
            with connection.execute_wrapper(sincronizar_lock):
                executar_seed()
            resultados[nome] = "ok"
        except Exception as exc:  # noqa: BLE001 — propaga a falha para a thread do teste
            resultados[nome] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=executar_em_thread, args=(nome,)) for nome in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert all(not thread.is_alive() for thread in threads), "execução concorrente não terminou"
    assert resultados == {"a": "ok", "b": "ok"}
    assert ExecucaoImportacao.objects.count() == 3
    assert Material.objects.count() == 9
    assert 25 <= User.objects.count() <= 35
    assert 6 <= Setor.objects.count() <= 8


@pytest.mark.django_db
def test_seed_com_catalogo_real_quando_disponibilizado():
    caminho = os.environ.get("SCPI_CSV_REAL")
    if not caminho:
        pytest.skip("Defina SCPI_CSV_REAL para validar o seed com o catálogo SCPI local.")
    registros = ler_registros(Path(caminho).read_bytes()).aceitos
    assert registros, "o catálogo real deve conter materiais válidos"

    # `--fornecedores` explícito e inexistente: este teste valida só o catálogo
    # real (gated por SCPI_CSV_REAL); nunca deve tocar o padrão real de
    # fornecedores (docs/CSVs/fornecedores.csv), mesmo que esse arquivo exista
    # localmente na máquina de quem roda o teste.
    call_command(
        "seed_dev",
        "--catalogo",
        caminho,
        "--fornecedores",
        str(FORNECEDORES_INEXISTENTE),
        stdout=StringIO(),
    )

    assert all(modelo.objects.exists() for modelo in MODELOS)
    assert ExecucaoImportacao.objects.count() == 3
    assert Material.objects.count() == len(registros)
    materiais = {material.cadpro: material for material in Material.objects.all()}
    for registro in registros:
        material = materiais[registro.cadpro]
        assert material.saldo == material.saldo_inicial == registro.quantidade
        for campo in CAMPOS_CADASTRAIS_ATUALIZAVEIS:
            assert getattr(material, campo) == getattr(registro, campo)
