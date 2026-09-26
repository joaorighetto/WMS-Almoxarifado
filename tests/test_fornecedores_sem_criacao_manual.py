"""Testes de "sem criação manual" de fornecedores (T031, Fase 7 — Polish).

Protege SC-008 e `INV-SUPPLIER-003` (fornecedor só entra/muda pela
importação do SCPI; não existe criação, edição ou exclusão manual por
nenhum papel), no mesmo molde de
`tests/test_catalogo_sem_criacao_manual.py` (T048):

1. Nenhum modelo de `fornecedores` está registrado em
   `django.contrib.admin` — o app não tem `fornecedores/admin.py` (já
   coberto também em `tests/test_fornecedores_modelos.py`, T006; mantido
   aqui de novo porque é exatamente o que SC-008 pede nesta task, e a
   redundância é barata).
2. Das rotas de `fornecedores` (enumeradas a partir de
   `fornecedores.urls.urlpatterns`, não à mão — uma rota nova entra neste
   teste automaticamente, inclusive `consulta`/`historico`, em
   implementação em paralelo no momento em que este arquivo foi escrito),
   só `importacao_envio`, `importacao_confirmar` e `importacao_cancelar`
   aceitam POST; nenhuma rota aceita PUT, PATCH ou DELETE.
3. `Fornecedor` só é instanciado em `fornecedores/importacao.py`: varredura
   estática (texto/regex) dos demais arquivos de `fornecedores/` por
   `Fornecedor(`, `Fornecedor.objects.create(` ou qualquer `bulk_create(`.

Preserva: `INV-SUPPLIER-003`.
"""

import pathlib
import re

import pytest
from django.apps import apps
from django.contrib import admin
from django.urls import reverse

from fornecedores import urls as fornecedores_urls

# ---------------------------------------------------------------------------
# 1. Nenhum modelo de fornecedores registrado no admin.
# ---------------------------------------------------------------------------


def test_nenhum_modelo_de_fornecedores_esta_registrado_no_admin():
    modelos_fornecedores = set(apps.get_app_config("fornecedores").get_models())
    modelos_registrados = set(admin.site._registry.keys())

    registrados_indevidamente = modelos_fornecedores & modelos_registrados

    assert not registrados_indevidamente, (
        "modelo(s) de fornecedores registrado(s) no admin (não deveria existir "
        "fornecedores/admin.py, SC-008/INV-SUPPLIER-003): "
        + ", ".join(sorted(m.__name__ for m in registrados_indevidamente))
    )


# ---------------------------------------------------------------------------
# 2. Só as rotas de escrita da importação aceitam POST; nenhuma rota aceita
#    PUT/PATCH/DELETE. Rotas enumeradas de `fornecedores.urls.urlpatterns` —
#    genérico de propósito: cobre o que existir no momento da execução,
#    inclusive rotas acrescentadas depois deste arquivo ter sido escrito
#    (consulta, histórico).
# ---------------------------------------------------------------------------


def _rotas_de_fornecedores() -> list:
    """Extrai (nome, kwargs) de cada rota registrada em `fornecedores.urls`,
    inferindo os `kwargs` exigidos pelos conversores de `path()` (ex.: `pk`
    em `execucao_detalhe`) em vez de listar rotas à mão."""
    rotas = []
    for padrao in fornecedores_urls.urlpatterns:
        conversores = getattr(padrao.pattern, "converters", {})
        kwargs = {nome_parametro: 1 for nome_parametro in conversores}
        rotas.append(pytest.param(padrao.name, kwargs, id=padrao.name))
    return rotas


ROTAS_FORNECEDORES = _rotas_de_fornecedores()

ROTAS_QUE_ACEITAM_POST = frozenset(
    {"importacao_envio", "importacao_confirmar", "importacao_cancelar"}
)


@pytest.mark.django_db
@pytest.mark.parametrize("nome, kwargs", ROTAS_FORNECEDORES)
def test_somente_rotas_de_escrita_da_importacao_aceitam_post(
    client, chefe_almoxarifado, nome, kwargs
):
    """`chefe_almoxarifado` está autorizado em toda rota de `fornecedores`
    hoje registrada (importação e, quando existirem, consulta/histórico —
    `PERM-SUPPLIER-VIEW`/`PERM-SUPPLIER-IMPORT-HISTORY-VIEW` também usam
    `ROLE-WAREHOUSE-STAFF`/`ROLE-WAREHOUSE-HEAD`, que ele possui), para que
    a resposta reflita o MÉTODO, não a autorização."""
    client.force_login(chefe_almoxarifado)
    url = reverse(f"fornecedores:{nome}", kwargs=kwargs)

    resposta = client.post(url)

    if nome in ROTAS_QUE_ACEITAM_POST:
        assert resposta.status_code != 405, f"POST em fornecedores:{nome} deveria ser aceito"
    else:
        assert resposta.status_code == 405, (
            f"POST em fornecedores:{nome} deveria ser 405 (só "
            f"{sorted(ROTAS_QUE_ACEITAM_POST)} aceitam POST)"
        )


@pytest.mark.django_db
@pytest.mark.parametrize("metodo", ["put", "patch", "delete"])
@pytest.mark.parametrize("nome, kwargs", ROTAS_FORNECEDORES)
def test_nenhuma_rota_de_fornecedores_aceita_put_patch_ou_delete(
    client, chefe_almoxarifado, nome, kwargs, metodo
):
    client.force_login(chefe_almoxarifado)
    url = reverse(f"fornecedores:{nome}", kwargs=kwargs)

    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 405, f"{metodo.upper()} em fornecedores:{nome} deveria ser 405"


# ---------------------------------------------------------------------------
# 3. `Fornecedor` só é criado no caminho de `aplicar_plano`.
# ---------------------------------------------------------------------------

_FORNECEDORES_DIR = pathlib.Path(__file__).resolve().parent.parent / "fornecedores"
_ARQUIVO_PERMITIDO = _FORNECEDORES_DIR / "importacao.py"

_PADROES_CRIACAO_FORNECEDOR = (
    # Instanciação (`Fornecedor(...)`), nunca a declaração da própria
    # classe (`class Fornecedor(models.Model):`, em fornecedores/models.py).
    re.compile(r"(?<!class )\bFornecedor\("),
    re.compile(r"\bFornecedor\.objects\.create\("),
    re.compile(r"\bbulk_create\("),
)


def test_fornecedor_so_e_criado_pelo_caminho_de_aplicar_plano():
    ocorrencias = []
    for caminho in sorted(_FORNECEDORES_DIR.rglob("*.py")):
        if caminho == _ARQUIVO_PERMITIDO:
            continue
        if "migrations" in caminho.parts:
            continue

        texto = caminho.read_text(encoding="utf-8")
        for numero, linha in enumerate(texto.splitlines(), start=1):
            if any(padrao.search(linha) for padrao in _PADROES_CRIACAO_FORNECEDOR):
                ocorrencias.append(f"{caminho.relative_to(_FORNECEDORES_DIR.parent)}:{numero}")

    assert not ocorrencias, (
        "criação de Fornecedor (ou bulk_create) fora de fornecedores/importacao.py, "
        "violando INV-SUPPLIER-003: " + ", ".join(ocorrencias)
    )
