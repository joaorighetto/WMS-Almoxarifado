"""Testes de "sem criação manual" do catálogo (T048, Fase 7 — Polish, de
`specs/001-importacao-catalogo-materiais/`).

Protege três garantias estruturais do FR-006/SC-005 (`Material` é
somente-inserção pela aplicação, exceto os campos cadastrais atualizáveis por
reimportação) e do "Não inclui" do ROADMAP (linha 001): nenhuma criação,
edição ou exclusão manual de material.

1. Nenhum modelo de `catalogo` está registrado em `django.contrib.admin`
   — o app não tem `catalogo/admin.py`, e isso é intencional: o admin do
   Django oferece CRUD genérico, que contornaria `aplicar_plano` como único
   caminho de escrita.
2. Das rotas de `catalogo` (enumeradas a partir de `catalogo.urls.urlpatterns`,
   não à mão, para que uma rota nova entre automaticamente neste teste), só
   `importacao_envio`, `importacao_confirmar` e `importacao_cancelar` aceitam
   POST; nenhuma rota aceita PUT, PATCH ou DELETE. Usa `chefe_almoxarifado`
   (autorizado em toda rota do app) para que a resposta reflita o método, não
   a autorização — o 405 de GET em `importacao_confirmar`/`importacao_cancelar`
   já está coberto em `tests/test_catalogo_permissoes.py` (T019).
3. `Material` só é instanciado em `catalogo/importacao.py`: varredura
   estática (texto/regex) dos demais arquivos de `catalogo/` (nunca de
   `tests/`, onde os próprios testes criam materiais diretamente para montar
   cenários) por `Material(`, `Material.objects.create(` ou qualquer
   `bulk_create(`.

Preserva: `INV-CATALOG-003`, `INV-CATALOG-004`.
"""

import pathlib
import re

import pytest
from django.apps import apps
from django.contrib import admin
from django.urls import reverse

from catalogo import urls as catalogo_urls

# ---------------------------------------------------------------------------
# 1. Nenhum modelo do catálogo registrado no admin.
# ---------------------------------------------------------------------------


def test_nenhum_modelo_do_catalogo_esta_registrado_no_admin():
    modelos_catalogo = set(apps.get_app_config("catalogo").get_models())
    modelos_registrados = set(admin.site._registry.keys())

    registrados_indevidamente = modelos_catalogo & modelos_registrados

    assert not registrados_indevidamente, (
        "modelo(s) do catálogo registrado(s) no admin (não deveria existir "
        "catalogo/admin.py, FR-006/SC-005/INV-CATALOG-003): "
        + ", ".join(sorted(m.__name__ for m in registrados_indevidamente))
    )


# ---------------------------------------------------------------------------
# 2. Só as rotas de escrita da importação aceitam POST; nenhuma rota aceita
#    PUT/PATCH/DELETE. Rotas enumeradas de `catalogo.urls.urlpatterns`.
# ---------------------------------------------------------------------------


def _rotas_do_catalogo() -> list:
    """Extrai (nome, kwargs) de cada rota registrada em `catalogo.urls`,
    inferindo os `kwargs` exigidos pelos conversores de `path()` (ex.:
    `pk` em `execucao_detalhe`) em vez de listar rotas à mão — uma rota
    nova em `catalogo/urls.py` entra neste teste automaticamente."""
    rotas = []
    for padrao in catalogo_urls.urlpatterns:
        conversores = getattr(padrao.pattern, "converters", {})
        kwargs = {nome_parametro: 1 for nome_parametro in conversores}
        rotas.append(pytest.param(padrao.name, kwargs, id=padrao.name))
    return rotas


ROTAS_CATALOGO = _rotas_do_catalogo()

ROTAS_QUE_ACEITAM_POST = frozenset(
    {"importacao_envio", "importacao_confirmar", "importacao_cancelar"}
)


@pytest.mark.django_db
@pytest.mark.parametrize("nome, kwargs", ROTAS_CATALOGO)
def test_somente_rotas_de_escrita_da_importacao_aceitam_post(
    client, chefe_almoxarifado, nome, kwargs
):
    client.force_login(chefe_almoxarifado)
    url = reverse(f"catalogo:{nome}", kwargs=kwargs)

    resposta = client.post(url)

    if nome in ROTAS_QUE_ACEITAM_POST:
        assert resposta.status_code != 405, f"POST em catalogo:{nome} deveria ser aceito"
    else:
        assert resposta.status_code == 405, (
            f"POST em catalogo:{nome} deveria ser 405 (só "
            f"{sorted(ROTAS_QUE_ACEITAM_POST)} aceitam POST)"
        )


@pytest.mark.django_db
@pytest.mark.parametrize("metodo", ["put", "patch", "delete"])
@pytest.mark.parametrize("nome, kwargs", ROTAS_CATALOGO)
def test_nenhuma_rota_do_catalogo_aceita_put_patch_ou_delete(
    client, chefe_almoxarifado, nome, kwargs, metodo
):
    client.force_login(chefe_almoxarifado)
    url = reverse(f"catalogo:{nome}", kwargs=kwargs)

    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 405, f"{metodo.upper()} em catalogo:{nome} deveria ser 405"


# ---------------------------------------------------------------------------
# 3. `Material` só é criado no caminho de `aplicar_plano`.
# ---------------------------------------------------------------------------

_CATALOGO_DIR = pathlib.Path(__file__).resolve().parent.parent / "catalogo"
_ARQUIVO_PERMITIDO = _CATALOGO_DIR / "importacao.py"

_PADROES_CRIACAO_MATERIAL = (
    # Instanciação (`Material(...)`), nunca a declaração da própria classe
    # (`class Material(models.Model):`, em catalogo/models.py).
    re.compile(r"(?<!class )\bMaterial\("),
    re.compile(r"\bMaterial\.objects\.create\("),
    re.compile(r"\bbulk_create\("),
)


def test_material_so_e_criado_pelo_caminho_de_aplicar_plano():
    ocorrencias = []
    for caminho in sorted(_CATALOGO_DIR.rglob("*.py")):
        if caminho == _ARQUIVO_PERMITIDO:
            continue
        if "migrations" in caminho.parts:
            # Geradas por `makemigrations`: referenciam o nome do modelo só
            # como string (`name='Material'`), nunca como chamada — e não
            # são o "código" que esta task protege.
            continue

        texto = caminho.read_text(encoding="utf-8")
        for numero, linha in enumerate(texto.splitlines(), start=1):
            if any(padrao.search(linha) for padrao in _PADROES_CRIACAO_MATERIAL):
                ocorrencias.append(f"{caminho.relative_to(_CATALOGO_DIR.parent)}:{numero}")

    assert not ocorrencias, (
        "criação de Material (ou bulk_create) fora de catalogo/importacao.py, "
        "violando INV-CATALOG-003/INV-CATALOG-004: " + ", ".join(ocorrencias)
    )
