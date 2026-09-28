from django.urls import path

from estoque import views

app_name = "estoque"

urlpatterns = [
    path("entradas/", views.EntradasView.as_view(), name="entradas"),
    path("entradas/nova/", views.EntradaNovaView.as_view(), name="entrada_nova"),
    path(
        "entradas/nova/confirmar/",
        views.EntradaConfirmarView.as_view(),
        name="entrada_confirmar",
    ),
    path("entradas/<int:pk>/", views.EntradaDetalheView.as_view(), name="entrada_detalhe"),
    path(
        "entradas/<int:pk>/estorno/",
        views.EntradaEstornoView.as_view(),
        name="entrada_estorno",
    ),
]
