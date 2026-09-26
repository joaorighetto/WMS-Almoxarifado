from django.urls import path

from fornecedores import views

app_name = "fornecedores"

urlpatterns = [
    path("", views.ConsultaFornecedoresView.as_view(), name="consulta"),
    path("importacao/", views.ImportacaoEnvioView.as_view(), name="importacao_envio"),
    path(
        "importacao/previa/",
        views.ImportacaoPreviaView.as_view(),
        name="importacao_previa",
    ),
    path(
        "importacao/confirmar/",
        views.ImportacaoConfirmarView.as_view(),
        name="importacao_confirmar",
    ),
    path(
        "importacao/cancelar/",
        views.ImportacaoCancelarView.as_view(),
        name="importacao_cancelar",
    ),
    path(
        "importacoes/",
        views.HistoricoImportacoesView.as_view(),
        name="historico",
    ),
    path(
        "importacoes/<int:pk>/",
        views.ExecucaoDetalheView.as_view(),
        name="execucao_detalhe",
    ),
]
