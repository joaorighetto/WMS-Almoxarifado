"""Testes de model do app `catalogo` (T014, Phase 2 — Foundational, de
`specs/001-importacao-catalogo-materiais/`).

Escritos contra o contrato de `data-model.md`, **antes** da implementação de
`catalogo/models.py` (T008–T010) e `normalizar_para_busca`
(`catalogo/leitura_scpi.py`, T012) estar pronta. Até lá, este arquivo falha
inteiro por `ImportError` — isso é esperado.

Cobre exclusivamente a camada de dados: constraints de banco (`CHECK`,
`UNIQUE`, `PROTECT`) que precisam valer mesmo contornando a aplicação, e a
função pura `normalizar_para_busca`. Não cobre `calcular_plano`/
`aplicar_plano` (T016), leitura do CSV (T015) nem views (T018/T019).

Invariantes/requisitos protegidos:
- `INV-CATALOG-001`: `cadpro` só existe no formato `XXX.YYY.ZZZ`, com
  dígitos ASCII (nunca `\\d`, que aceitaria dígitos Unicode — research.md R3),
  gravado e relido sem nenhuma normalização.
- `INV-CATALOG-002`: `cadpro` é único também em persistência.
- `INV-STOCK-001`: `saldo`/`saldo_inicial` nunca são negativos, com `>= 0`
  como fronteira exata (zero é um saldo físico válido).
- `INV-STOCK-003`: uma divergência só existe quando há diferença real
  (`diferenca <> 0`) e consistente com os dois saldos que a originam.
- `INV-CATALOG-004`/FR-032: toda alteração cadastral tem um valor anterior
  e um novo genuinamente diferentes, um registro por campo e execução.
- FR-034/SC-003 e R10: os totais de `ExecucaoImportacao` obedecem a
  identidade fechada (`recebidos = inseridos + atualizados + rejeitados`) e
  o subtotal informativo nunca excede o total que subdivide.
- FR-036: `linha_final >= linha_inicial` em toda exceção de importação.
- Constitution IV / `data-model.md` (Diagrama): nenhuma FK entre os modelos
  de `catalogo` permite exclusão física de um registro referenciado
  (`on_delete=PROTECT`).

As factories `execucao_valida`/`criar_material` abaixo criam objetos direto
pelo ORM, dentro de cada teste. Isso **não é caminho de produto** — só
`aplicar_plano` pode gravar `Material`/`ExecucaoImportacao` (SC-005,
`INV-CATALOG-003`, ver `tests/test_catalogo_sem_criacao_manual.py`, T048).
Aqui serve só para popular as FKs obrigatórias e exercitar cada constraint
isoladamente, sem depender do parser nem do serviço de importação.
"""

import uuid
from decimal import Decimal

import pytest
from django.db import DataError, IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from catalogo.leitura_scpi import normalizar_para_busca
from catalogo.models import (
    AlteracaoCadastralMaterial,
    DivergenciaSaldo,
    ExcecaoImportacao,
    ExecucaoImportacao,
    Material,
    MotivoRecusa,
)

SHA256_FAKE = "0" * 64


def _dados_execucao(usuario, **overrides):
    """Kwargs válidos mínimos para `ExecucaoImportacao.objects.create`.

    Não é caminho de produto (ver docstring do módulo) — só monta uma linha
    consistente com as constraints de totais para poder violar, em cada
    teste, exatamente uma delas por vez.
    """
    dados = dict(
        token_previa=uuid.uuid4(),
        executada_por=usuario,
        concluida_em=timezone.now(),
        nome_arquivo="carga.csv",
        tamanho_arquivo=1024,
        sha256_arquivo=SHA256_FAKE,
        total_recebidos=1,
        total_inseridos=1,
        total_atualizados=0,
        total_atualizados_com_alteracao=0,
        total_rejeitados=0,
        total_divergencias=0,
        total_ausentes_no_arquivo=0,
    )
    dados.update(overrides)
    return dados


@pytest.fixture
def execucao_valida(chefe_almoxarifado):
    """`ExecucaoImportacao` válida, para popular o FK obrigatório de
    `Material`/`ExcecaoImportacao`/`DivergenciaSaldo`/
    `AlteracaoCadastralMaterial` em testes que não exercitam os próprios
    totais da execução."""
    return ExecucaoImportacao.objects.create(**_dados_execucao(chefe_almoxarifado))


@pytest.fixture
def criar_material(execucao_valida):
    """Factory de `Material` válido, com `cadpro` único por chamada.

    Não é caminho de produto (ver docstring do módulo): a aplicação só cria
    `Material` via `aplicar_plano`. Aqui serve só para testar as constraints
    de `Material` e para ser referenciado por `DivergenciaSaldo`/
    `AlteracaoCadastralMaterial` nos testes seguintes.
    """
    contador = {"valor": 0}

    def _criar_material(
        *,
        cadpro=None,
        saldo=Decimal("10.000"),
        saldo_inicial=None,
        execucao=None,
        **overrides,
    ):
        contador["valor"] += 1
        if cadpro is None:
            cadpro = f"000.000.{contador['valor']:03d}"
        if saldo_inicial is None:
            saldo_inicial = saldo
        dados = dict(
            cadpro=cadpro,
            descricao="Parafuso",
            descricao_busca=normalizar_para_busca("Parafuso"),
            unidade="UN",
            detalhamento="",
            grupo="",
            subgrupo="",
            nome_grupo="",
            nome_subgrupo="",
            saldo=saldo,
            saldo_inicial=saldo_inicial,
            execucao_origem=execucao or execucao_valida,
        )
        dados.update(overrides)
        return Material.objects.create(**dados)

    return _criar_material


# ---------------------------------------------------------------------------
# Material.cadpro: formato e unicidade (INV-CATALOG-001/002)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_cadpro_duplicado_e_rejeitado_pelo_banco(criar_material):
    """`INV-CATALOG-002`: único também em persistência, não só por validação
    de aplicação."""
    criar_material(cadpro="000.000.002")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            criar_material(cadpro="000.000.002")

    assert Material.objects.filter(cadpro="000.000.002").count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "cadpro_invalido",
    ["2", "000.000.2", "٠٠٠.٠٠٠.٠٠٢", "000.000.02 ", " 00.000.002", "000 000.002"],
    ids=[
        "muito_curto_sem_pontuacao",
        "ultimo_grupo_com_1_digito",
        "digitos_unicode_nao_ascii",
        # Espaço com exatamente 11 caracteres: cabe em `varchar(11)`, então a
        # recusa só pode vir do CHECK de formato (não de truncamento).
        "espaco_final_11_caracteres",
        "espaco_inicial_11_caracteres",
        "espaco_no_lugar_do_ponto",
    ],
)
def test_cadpro_fora_do_formato_e_rejeitado_pelo_check_de_banco(criar_material, cadpro_invalido):
    """`INV-CATALOG-001`: o `CHECK` de formato roda mesmo contornando a
    aplicação. O caso Unicode (`٠` = dígito arábico-índico) trava
    especificamente contra o uso de `\\d` no lugar de `[0-9]` na regex do
    banco (research.md R3): `\\d` aceitaria esse dígito, `[0-9]` não."""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            criar_material(cadpro=cadpro_invalido)

    assert not Material.objects.filter(cadpro=cadpro_invalido).exists()


@pytest.mark.django_db
def test_cadpro_com_espaco_nas_bordas_e_rejeitado_pelo_banco(criar_material):
    """`INV-CATALOG-001`: espaço nas bordas nunca é um `cadpro` válido.

    Nota: `" 000.000.002"` tem 12 caracteres — 1 a mais que o
    `max_length=11` do contrato (`data-model.md`). Por isso o Postgres pode
    recusar por `DataError` (truncamento de `varchar(11)`, SQLSTATE classe
    22) em vez de `IntegrityError` (`CHECK`, SQLSTATE classe 23), dependendo
    de qual restrição de coluna é avaliada primeiro na inserção — as duas
    são aceitas aqui porque o que `INV-CATALOG-001` exige é que nenhum
    `cadpro` com espaço seja persistido, não qual exceção especificamente
    carrega essa recusa.
    """
    with pytest.raises((IntegrityError, DataError)):
        with transaction.atomic():
            criar_material(cadpro=" 000.000.002")

    assert not Material.objects.filter(cadpro=" 000.000.002").exists()


@pytest.mark.django_db
def test_cadpro_valido_e_relido_identico(criar_material):
    """`INV-CATALOG-001`: `000.000.002` é gravado e relido byte a byte — os
    zeros à esquerda não podem desaparecer nem ser tratados como número."""
    material = criar_material(cadpro="000.000.002")

    recarregado = Material.objects.get(pk=material.pk)

    assert recarregado.cadpro == "000.000.002"
    assert isinstance(recarregado.cadpro, str)


# ---------------------------------------------------------------------------
# Material.saldo / saldo_inicial: nunca negativos (INV-STOCK-001)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_saldo_negativo_e_rejeitado_pelo_banco(criar_material):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            criar_material(saldo=Decimal("-0.001"), saldo_inicial=Decimal("10.000"))


@pytest.mark.django_db
def test_saldo_inicial_negativo_e_rejeitado_pelo_banco(criar_material):
    """A constraint é independente da de `saldo`: um `saldo` válido não
    esconde um `saldo_inicial` inválido."""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            criar_material(saldo=Decimal("10.000"), saldo_inicial=Decimal("-0.001"))


@pytest.mark.django_db
def test_saldo_zero_e_aceito(criar_material):
    """`0.000` é saldo físico válido (material sem estoque) — a fronteira
    exata de `INV-STOCK-001` é `>= 0`, não `> 0`."""
    material = criar_material(saldo=Decimal("0.000"), saldo_inicial=Decimal("0.000"))

    assert Material.objects.get(pk=material.pk).saldo == Decimal("0.000")


# ---------------------------------------------------------------------------
# ExecucaoImportacao: identidade fechada dos totais (FR-034/SC-003, R10)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_totais_com_soma_inconsistente_sao_rejeitados_pelo_banco(chefe_almoxarifado):
    """`recebidos = inseridos + atualizados + rejeitados` também é garantido
    em persistência, não só pelo código que soma os totais."""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ExecucaoImportacao.objects.create(
                **_dados_execucao(
                    chefe_almoxarifado,
                    total_recebidos=5,
                    total_inseridos=1,
                    total_atualizados=1,
                    total_rejeitados=1,
                )
            )


@pytest.mark.django_db
def test_atualizados_com_alteracao_maior_que_atualizados_e_rejeitado(chefe_almoxarifado):
    """R10: o subtotal informativo (`total_atualizados_com_alteracao`) nunca
    pode superar o total que subdivide."""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ExecucaoImportacao.objects.create(
                **_dados_execucao(
                    chefe_almoxarifado,
                    total_recebidos=1,
                    total_inseridos=0,
                    total_atualizados=1,
                    total_atualizados_com_alteracao=2,
                    total_rejeitados=0,
                )
            )


# ---------------------------------------------------------------------------
# ExcecaoImportacao: linha_final >= linha_inicial (FR-036)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_linha_final_menor_que_linha_inicial_e_rejeitada_pelo_banco(execucao_valida):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ExcecaoImportacao.objects.create(
                execucao=execucao_valida,
                linha_inicial=5,
                linha_final=3,
                cadpro="",
                motivo=MotivoRecusa.LINHA_NAO_ASSOCIAVEL,
                detalhe="",
            )


# ---------------------------------------------------------------------------
# DivergenciaSaldo: diferenca consistente e não-nula (INV-STOCK-003)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_diferenca_incompativel_com_os_saldos_e_rejeitada(execucao_valida, criar_material):
    material = criar_material(saldo=Decimal("10.000"))

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            DivergenciaSaldo.objects.create(
                execucao=execucao_valida,
                material=material,
                saldo_wms=Decimal("10.000"),
                saldo_arquivo=Decimal("12.000"),
                diferenca=Decimal("1.000"),  # deveria ser 2.000
            )


@pytest.mark.django_db
def test_diferenca_zero_e_rejeitada_mesmo_calculada_corretamente(execucao_valida, criar_material):
    """`INV-STOCK-003`: uma divergência só existe quando há diferença real —
    `diferenca = 0`, mesmo consistente com os dois saldos informados, nunca
    deveria ter sido criada."""
    material = criar_material(saldo=Decimal("10.000"))

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            DivergenciaSaldo.objects.create(
                execucao=execucao_valida,
                material=material,
                saldo_wms=Decimal("10.000"),
                saldo_arquivo=Decimal("10.000"),
                diferenca=Decimal("0.000"),
            )


@pytest.mark.django_db
def test_divergencia_duplicada_para_mesma_execucao_e_material_e_rejeitada(
    execucao_valida, criar_material
):
    material = criar_material(saldo=Decimal("10.000"))
    DivergenciaSaldo.objects.create(
        execucao=execucao_valida,
        material=material,
        saldo_wms=Decimal("10.000"),
        saldo_arquivo=Decimal("12.000"),
        diferenca=Decimal("2.000"),
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            DivergenciaSaldo.objects.create(
                execucao=execucao_valida,
                material=material,
                saldo_wms=Decimal("10.000"),
                saldo_arquivo=Decimal("15.000"),
                diferenca=Decimal("5.000"),
            )

    assert (
        DivergenciaSaldo.objects.filter(execucao=execucao_valida, material=material).count() == 1
    )


# ---------------------------------------------------------------------------
# AlteracaoCadastralMaterial: mudança real e unicidade (INV-CATALOG-004,
# FR-032)
#
# `campo` recebe a string literal do nome do campo cadastral (ex.:
# "descricao"), sem importar `CampoCadastral`: o contrato (`data-model.md`,
# T010) fixa que há 7 campos atualizáveis, mas não o nome exato dos membros
# do enum, que é escolha do implementador. `CharField(choices=...)` não é
# validado em `.create()` (só via `full_clean()`), então o valor literal
# exercita a constraint de igualdade sem depender desse detalhe.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_valor_anterior_igual_ao_novo_e_rejeitado(execucao_valida, criar_material):
    material = criar_material()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            AlteracaoCadastralMaterial.objects.create(
                execucao=execucao_valida,
                material=material,
                campo="descricao",
                valor_anterior="Parafuso",
                valor_novo="Parafuso",
            )


@pytest.mark.django_db
def test_alteracao_duplicada_para_mesma_execucao_material_e_campo_e_rejeitada(
    execucao_valida, criar_material
):
    material = criar_material()
    AlteracaoCadastralMaterial.objects.create(
        execucao=execucao_valida,
        material=material,
        campo="descricao",
        valor_anterior="Parafuso",
        valor_novo="Parafuso M6",
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            AlteracaoCadastralMaterial.objects.create(
                execucao=execucao_valida,
                material=material,
                campo="descricao",
                valor_anterior="Parafuso M6",
                valor_novo="Parafuso M8",
            )

    assert (
        AlteracaoCadastralMaterial.objects.filter(
            execucao=execucao_valida, material=material, campo="descricao"
        ).count()
        == 1
    )


# ---------------------------------------------------------------------------
# Preservação histórica: nenhuma exclusão física de execução referenciada
# (Constitution IV; data-model.md, Diagrama: todas as FKs são PROTECT)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_execucao_referenciada_por_material_nao_pode_ser_excluida(execucao_valida, criar_material):
    criar_material(execucao=execucao_valida)

    with pytest.raises(ProtectedError):
        execucao_valida.delete()

    assert ExecucaoImportacao.objects.filter(pk=execucao_valida.pk).exists()
    assert Material.objects.filter(execucao_origem=execucao_valida).exists()


# ---------------------------------------------------------------------------
# normalizar_para_busca (FR-040, research.md R15) — função pura, sem banco
# ---------------------------------------------------------------------------


def test_normalizar_para_busca_ignora_acentos_e_caixa():
    """Mesma função grava `descricao_busca` e normaliza o termo digitado —
    sem essa igualdade a busca acentuada/maiúscula não encontraria nada."""
    assert normalizar_para_busca("Ação ÇÃO") == normalizar_para_busca("acao cao")
    assert normalizar_para_busca("Ação ÇÃO") == "acao cao"


def test_normalizar_para_busca_preserva_o_que_nao_e_acento():
    """Só remove marcas combinantes (NFKD, categoria Mn) e aplica
    `casefold()` — dígitos, pontuação e hífen atravessam intactos, sem
    virar espaço nem desaparecer."""
    assert normalizar_para_busca("Cotovelo-90 3/4") == "cotovelo-90 3/4"
