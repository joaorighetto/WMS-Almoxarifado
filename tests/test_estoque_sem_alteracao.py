"""Nenhum caminho da aplicação altera ou exclui entrada, item, estorno ou
movimentação (T031, SC-008, FR-018, FR-025).

Mesmo padrão de `tests/test_catalogo_sem_criacao_manual.py`/`tests/
test_fornecedores_sem_criacao_manual.py`: reforço explícito, além dos
triggers de banco já testados em `tests/test_estoque_modelos.py` — aqui o
foco é a ausência de CAMINHO na aplicação (admin, rotas), não a defesa do
banco em si.
"""

import uuid
from decimal import Decimal

import pytest
from django.contrib import admin
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_nenhum_modelo_de_estoque_esta_registrado_no_admin():
    from estoque.models import Entrada, EstornoEntrada, ItemEntrada, MovimentacaoEstoque

    modelos = {Entrada, ItemEntrada, EstornoEntrada, MovimentacaoEstoque}
    registrados = set(admin.site._registry.keys())

    assert not (modelos & registrados)


def _registrar(autor, material, quantidade):
    from estoque.entradas import EntradaInformada, ItemInformado, registrar_entrada
    from estoque.models import MotivoEntrada, TipoDocumentoEntrada

    dados = EntradaInformada(
        chave_confirmacao=uuid.uuid4(),
        motivo=MotivoEntrada.DOACAO_RECEBIDA,
        tipo_documento=TipoDocumentoEntrada.NOTA_FISCAL,
        numero_documento=str(uuid.uuid4()),
        emitente_id=None,
        itens=(ItemInformado(material_id=material.pk, quantidade=quantidade),),
    )
    return registrar_entrada(dados, autor)


@pytest.mark.parametrize(
    "nome_rota, kwargs",
    [
        pytest.param("estoque:entradas", {}, id="entradas"),
        pytest.param("estoque:entrada_detalhe", {"args": [1]}, id="entrada_detalhe"),
        pytest.param("estoque:entrada_nova", {}, id="entrada_nova"),
        pytest.param("estoque:entrada_confirmar", {}, id="entrada_confirmar"),
        pytest.param("estoque:entrada_estorno", {"args": [1]}, id="entrada_estorno"),
    ],
)
def test_nenhuma_rota_aceita_metodos_de_edicao_direta(
    client, chefe_almoxarifado, nome_rota, kwargs
):
    """`PUT`/`PATCH`/`DELETE` não são métodos suportados por nenhuma rota de
    `estoque` — todas são Django `View`s comuns (GET/POST), sem rota de
    edição dedicada. O chefe do almoxarifado passa na checagem de papel de
    todas as rotas, então a recusa vem do próprio despacho de método (405)."""
    client.force_login(chefe_almoxarifado)
    url = reverse(nome_rota, **kwargs)

    for metodo in ("put", "patch", "delete"):
        resposta = getattr(client, metodo)(url)
        assert resposta.status_code == 405, (
            f"{metodo.upper()} {nome_rota} deveria responder 405, recebeu {resposta.status_code}"
        )


def test_entrada_registrada_nao_pode_ser_alterada_por_nenhum_caminho_da_aplicacao(
    client, funcionario_almoxarifado, chefe_almoxarifado, criar_material
):
    from estoque.models import Entrada

    material = criar_material("910.000.001", Decimal("0.000"))
    entrada = _registrar(funcionario_almoxarifado, material, Decimal("5.000"))

    # Nenhum papel — nem o chefe do almoxarifado, autorizado a ESTORNAR —
    # consegue alterar os fatos da entrada por uma rota de edição, porque
    # nenhuma existe.
    client.force_login(chefe_almoxarifado)
    url_estorno = reverse("estoque:entrada_estorno", args=[entrada.pk])
    resposta = client.put(url_estorno, {"numero_documento": "ADULTERADO"})
    assert resposta.status_code in (403, 404, 405)

    entrada.refresh_from_db()
    assert entrada.numero_documento != "ADULTERADO"
    assert Entrada.objects.filter(pk=entrada.pk).exists()
