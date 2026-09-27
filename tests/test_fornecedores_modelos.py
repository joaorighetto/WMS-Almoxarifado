"""Testes de model do app `fornecedores` (T006, Phase 2 — Foundational).

Escritos contra `data-model.md`/`contracts/interface-importacao.md` e a task
T005 (já implementada — ver `fornecedores/models.py`, diferente da situação
TDD usual: este arquivo roda de verdade agora, contra os models reais, não
apenas falha por `ImportError`). Cobre exclusivamente a camada de dados:
constraints de banco (`CHECK`, `UNIQUE`, `PROTECT`) que precisam valer mesmo
contornando a aplicação — não cobre `calcular_plano`/`aplicar_plano`
(`tests/test_fornecedores_importacao.py`), leitura do CSV
(`tests/test_fornecedores_leitura.py`) nem views.

Invariantes/requisitos protegidos:
- `INV-SUPPLIER-001`: `codif` só existe como `[0-9]+`, nunca `\\d` (dígitos
  Unicode como `٣` continuam fora), gravado e relido sem normalização.
- `INV-SUPPLIER-002`: `codif` é único também em persistência.
- FR-013: `nome` vazio ou só espaços é rejeitado pelo banco, não só pela
  aplicação.
- Totais de `ExecucaoImportacaoFornecedores`: identidade fechada
  (`recebidos = inseridos + atualizados + rejeitados`) e o subtotal
  informativo nunca excede o total que subdivide (mesmo padrão de
  `ExecucaoImportacao` da 001, sem `total_divergencias` — fornecedores não
  tem divergência de saldo).
- `token_previa` único — é a defesa de banco por trás de `PreviaJaConfirmada`
  (`fornecedores.importacao`, ainda não implementado).
- FR-025: `linha >= 1` em toda exceção de importação.
- `AlteracaoFornecedor`: mudança real (`valor_anterior <> valor_novo`) e uma
  linha por (execução, fornecedor, campo) — decisão do coordenador para esta
  rodada, já refletida em `fornecedores/models.py`.
- Constitution IV / preservação histórica: nenhuma FK de `fornecedores`
  permite exclusão física de um registro referenciado (`on_delete=PROTECT`).
- SC-008: nenhum model de `fornecedores` está registrado no admin.

As factories `execucao_valida`/`criar_fornecedor` abaixo criam objetos direto
pelo ORM, dentro de cada teste. Isso **não é caminho de produto** — só
`aplicar_plano` (a implementar) pode gravar `Fornecedor`/
`ExecucaoImportacaoFornecedores` (`INV-SUPPLIER-003`,
`tests/test_fornecedores_sem_criacao_manual.py`, T031). Aqui serve só para
popular as FKs obrigatórias e exercitar cada constraint isoladamente.
"""

import uuid

import pytest
from django.contrib import admin
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from fornecedores.models import (
    AlteracaoFornecedor,
    ExcecaoImportacaoFornecedores,
    ExecucaoImportacaoFornecedores,
    Fornecedor,
    MotivoRecusaFornecedor,
)

SHA256_FAKE = "0" * 64


def _dados_execucao(usuario, **overrides):
    """Kwargs válidos mínimos para `ExecucaoImportacaoFornecedores.objects.
    create`. Não é caminho de produto (ver docstring do módulo) — só monta
    uma linha consistente com as constraints de totais para poder violar, em
    cada teste, exatamente uma delas por vez."""
    dados = dict(
        token_previa=uuid.uuid4(),
        executada_por=usuario,
        concluida_em=timezone.now(),
        nome_arquivo="fornecedores.csv",
        tamanho_arquivo=1024,
        sha256_arquivo=SHA256_FAKE,
        total_recebidos=1,
        total_inseridos=1,
        total_atualizados=0,
        total_atualizados_com_alteracao=0,
        total_rejeitados=0,
        total_ausentes_no_arquivo=0,
    )
    dados.update(overrides)
    return dados


@pytest.fixture
def execucao_valida(chefe_almoxarifado):
    """`ExecucaoImportacaoFornecedores` válida, para popular o FK
    obrigatório de `Fornecedor`/`ExcecaoImportacaoFornecedores`/
    `AlteracaoFornecedor` em testes que não exercitam os próprios totais."""
    return ExecucaoImportacaoFornecedores.objects.create(**_dados_execucao(chefe_almoxarifado))


@pytest.fixture
def criar_fornecedor(execucao_valida):
    """Factory de `Fornecedor` válido, com `codif` único por chamada.

    Não é caminho de produto (ver docstring do módulo): a aplicação só cria
    `Fornecedor` via `aplicar_plano`. Aqui serve só para testar as
    constraints de `Fornecedor` e para popular o FK de `AlteracaoFornecedor`
    nos testes seguintes.
    """
    contador = {"valor": 0}

    def _criar_fornecedor(*, codif=None, execucao=None, **overrides):
        contador["valor"] += 1
        if codif is None:
            codif = str(600_000 + contador["valor"])
        dados = dict(
            codif=codif,
            nome="Fornecedor Teste",
            nome_fantasia="",
            documento="",
            documento_digitos="",
            tipo="",
            bloqueado=False,
            motivo_bloqueio="",
            tipo_bloqueio="",
            nome_busca="fornecedor teste",
            execucao_origem=execucao or execucao_valida,
        )
        dados.update(overrides)
        return Fornecedor.objects.create(**dados)

    return _criar_fornecedor


# ---------------------------------------------------------------------------
# Fornecedor.codif: formato e unicidade (INV-SUPPLIER-001/002)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_codif_duplicado_e_rejeitado_pelo_banco(criar_fornecedor):
    """`INV-SUPPLIER-002`: único também em persistência, não só por
    validação de aplicação. Nome e documento distintos não bastam para
    driblar a unicidade — só `codif` identifica o fornecedor."""
    criar_fornecedor(codif="700001", nome="Fornecedor Um")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            criar_fornecedor(codif="700001", nome="Fornecedor Outro Nome")

    assert Fornecedor.objects.filter(codif="700001").count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "codif_invalido",
    ["", "12A", "٣", "7 ", " 7", "7.0", "-7"],
    ids=[
        "vazio",
        "com_letra",
        "digito_unicode_arabico",
        "espaco_final",
        "espaco_inicial",
        "ponto",
        "sinal_negativo",
    ],
)
def test_codif_fora_do_formato_e_rejeitado_pelo_check_de_banco(criar_fornecedor, codif_invalido):
    """`INV-SUPPLIER-001`: o `CHECK ~ '^[0-9]+$'` roda mesmo contornando a
    aplicação. `٣` (dígito arábico-índico, U+0663) trava especificamente
    contra o uso de `\\d`/`\\w` no lugar de `[0-9]` na regex do banco
    (research.md R2, mesmo raciocínio da 001 para `CADPRO`)."""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            criar_fornecedor(codif=codif_invalido)

    assert not Fornecedor.objects.filter(codif=codif_invalido).exists()


@pytest.mark.django_db
def test_codif_com_zeros_a_esquerda_e_gravado_e_relido_identico(criar_fornecedor):
    """`INV-SUPPLIER-001`: `007` é gravado e relido byte a byte — os zeros à
    esquerda não podem desaparecer nem ser tratados como número, e `007`
    continua distinto de `7`."""
    fornecedor = criar_fornecedor(codif="007")
    criar_fornecedor(codif="7")

    recarregado = Fornecedor.objects.get(pk=fornecedor.pk)

    assert recarregado.codif == "007"
    assert isinstance(recarregado.codif, str)
    assert Fornecedor.objects.filter(codif="7").count() == 1
    assert Fornecedor.objects.filter(codif="007").count() == 1


# ---------------------------------------------------------------------------
# Fornecedor.nome: vazio ou só espaços rejeitado (FR-013)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("nome_invalido", ["", "   "], ids=["vazio", "so_espacos"])
def test_nome_vazio_ou_so_espacos_e_rejeitado_pelo_banco(criar_fornecedor, nome_invalido):
    """FR-013/`data-model.md`: `CHECK trim(nome) <> ''`, avaliado mesmo
    contornando a aplicação (a própria leitura do arquivo, T013, já recusa
    esses casos como `NOME_AUSENTE` antes de chegar aqui — este teste cobre
    a defesa de banco, independente da aplicação estar correta ou não)."""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            criar_fornecedor(nome=nome_invalido)


@pytest.mark.django_db
def test_nome_com_conteudo_alem_de_espaco_e_aceito(criar_fornecedor):
    """Fronteira exata do `CHECK`: qualquer caractere não-espaço já basta —
    não é uma regra de tamanho mínimo."""
    fornecedor = criar_fornecedor(nome=" X ")

    assert Fornecedor.objects.get(pk=fornecedor.pk).nome == " X "


# ---------------------------------------------------------------------------
# ExecucaoImportacaoFornecedores: token único e identidade fechada dos
# totais
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_token_previa_duplicado_e_rejeitado_pelo_banco(chefe_almoxarifado):
    """`token_previa` único é a defesa de banco por trás de
    `PreviaJaConfirmada` (`fornecedores.importacao`, ainda não
    implementado) — precisa valer mesmo que a checagem de aplicação falhe
    ou seja contornada."""
    token = uuid.uuid4()
    ExecucaoImportacaoFornecedores.objects.create(
        **_dados_execucao(chefe_almoxarifado, token_previa=token)
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ExecucaoImportacaoFornecedores.objects.create(
                **_dados_execucao(chefe_almoxarifado, token_previa=token, nome_arquivo="outro.csv")
            )

    assert ExecucaoImportacaoFornecedores.objects.filter(token_previa=token).count() == 1


@pytest.mark.django_db
def test_totais_com_soma_inconsistente_sao_rejeitados_pelo_banco(chefe_almoxarifado):
    """`recebidos = inseridos + atualizados + rejeitados` também é garantido
    em persistência, não só pelo código que soma os totais."""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ExecucaoImportacaoFornecedores.objects.create(
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
    """O subtotal informativo (`total_atualizados_com_alteracao`) nunca pode
    superar o total que subdivide."""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ExecucaoImportacaoFornecedores.objects.create(
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
# ExcecaoImportacaoFornecedores: linha >= 1 (FR-025)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_linha_zero_e_rejeitada_pelo_banco(execucao_valida):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ExcecaoImportacaoFornecedores.objects.create(
                execucao=execucao_valida,
                linha=0,
                codif="",
                motivo=MotivoRecusaFornecedor.CODIF_AUSENTE,
                detalhe="",
            )


@pytest.mark.django_db
def test_linha_um_e_aceita(execucao_valida):
    """Fronteira exata: `linha == 1` (o cabeçalho é a linha 1,
    `contracts/arquivo-fornecedores.md` §2) precisa ser aceita, não só
    `linha >= 2`."""
    excecao = ExcecaoImportacaoFornecedores.objects.create(
        execucao=execucao_valida,
        linha=1,
        codif="",
        motivo=MotivoRecusaFornecedor.CODIF_AUSENTE,
        detalhe="",
    )

    assert ExcecaoImportacaoFornecedores.objects.get(pk=excecao.pk).linha == 1


# ---------------------------------------------------------------------------
# AlteracaoFornecedor: mudança real e uma linha por (execução, fornecedor,
# campo) — decisão do coordenador para esta rodada.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_valor_anterior_igual_ao_novo_e_rejeitado(execucao_valida, criar_fornecedor):
    fornecedor = criar_fornecedor()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            AlteracaoFornecedor.objects.create(
                execucao=execucao_valida,
                fornecedor=fornecedor,
                campo="nome",
                valor_anterior="Fornecedor Teste",
                valor_novo="Fornecedor Teste",
            )


@pytest.mark.django_db
def test_alteracao_duplicada_para_mesma_execucao_fornecedor_e_campo_e_rejeitada(
    execucao_valida, criar_fornecedor
):
    fornecedor = criar_fornecedor()
    AlteracaoFornecedor.objects.create(
        execucao=execucao_valida,
        fornecedor=fornecedor,
        campo="nome",
        valor_anterior="Fornecedor Teste",
        valor_novo="Fornecedor Teste Revisado",
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            AlteracaoFornecedor.objects.create(
                execucao=execucao_valida,
                fornecedor=fornecedor,
                campo="nome",
                valor_anterior="Fornecedor Teste Revisado",
                valor_novo="Fornecedor Teste Revisado De Novo",
            )

    assert (
        AlteracaoFornecedor.objects.filter(
            execucao=execucao_valida, fornecedor=fornecedor, campo="nome"
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_alteracao_de_campo_bloqueado_usa_s_ou_b(execucao_valida, criar_fornecedor):
    """`interface-importacao.md`: "`bloqueado` entra nas alterações [...]
    como `S`/`B`" — mesmo o campo sendo um `BooleanField` no model,
    `AlteracaoFornecedor.valor_anterior`/`valor_novo` guardam a
    representação textual do arquivo, não `"True"`/`"False"`."""
    fornecedor = criar_fornecedor()

    alteracao = AlteracaoFornecedor.objects.create(
        execucao=execucao_valida,
        fornecedor=fornecedor,
        campo="bloqueado",
        valor_anterior="S",
        valor_novo="B",
    )

    assert alteracao.valor_anterior == "S"
    assert alteracao.valor_novo == "B"


# ---------------------------------------------------------------------------
# Preservação histórica: nenhuma exclusão física de execução/fornecedor
# referenciado (Constitution IV; todas as FKs de fornecedores são PROTECT)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_execucao_referenciada_por_fornecedor_nao_pode_ser_excluida(
    execucao_valida, criar_fornecedor
):
    criar_fornecedor(execucao=execucao_valida)

    with pytest.raises(ProtectedError):
        execucao_valida.delete()

    assert ExecucaoImportacaoFornecedores.objects.filter(pk=execucao_valida.pk).exists()
    assert Fornecedor.objects.filter(execucao_origem=execucao_valida).exists()


@pytest.mark.django_db
def test_usuario_executor_referenciado_nao_pode_ser_excluido(execucao_valida, chefe_almoxarifado):
    with pytest.raises(ProtectedError):
        chefe_almoxarifado.delete()

    assert ExecucaoImportacaoFornecedores.objects.filter(pk=execucao_valida.pk).exists()


@pytest.mark.django_db
def test_fornecedor_referenciado_por_alteracao_nao_pode_ser_excluido(
    execucao_valida, criar_fornecedor
):
    fornecedor = criar_fornecedor()
    AlteracaoFornecedor.objects.create(
        execucao=execucao_valida,
        fornecedor=fornecedor,
        campo="nome",
        valor_anterior="Fornecedor Teste",
        valor_novo="Fornecedor Teste Revisado",
    )

    with pytest.raises(ProtectedError):
        fornecedor.delete()

    assert Fornecedor.objects.filter(pk=fornecedor.pk).exists()


# ---------------------------------------------------------------------------
# SC-008: nenhum model de fornecedores no admin
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_nenhum_model_de_fornecedores_esta_registrado_no_admin():
    modelos_fornecedores = {
        Fornecedor,
        ExecucaoImportacaoFornecedores,
        ExcecaoImportacaoFornecedores,
        AlteracaoFornecedor,
    }
    registrados = modelos_fornecedores & set(admin.site._registry)

    assert not registrados, (
        f"model(s) de fornecedores registrado(s) no admin: {registrados} — "
        "SC-008 exige que a importação seja o único caminho de escrita"
    )
