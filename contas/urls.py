from django.contrib.auth.views import LogoutView
from django.urls import path

from contas.forms import WMSAuthenticationForm
from contas.views import (
    HomeView,
    SenhaView,
    SetorAtivarView,
    SetorChefiaView,
    SetorDesativarView,
    SetorEditarView,
    SetoresView,
    SetorFichaView,
    SetorNovoView,
    UsuarioDesativarView,
    UsuarioEditarView,
    UsuarioFichaView,
    UsuarioNovoView,
    UsuarioPapeisView,
    UsuarioReativarView,
    UsuarioRedefinirSenhaView,
    UsuariosView,
    UsuarioTransferirView,
    WMSLoginView,
)

urlpatterns = [
    path(
        "login/",
        WMSLoginView.as_view(
            template_name="contas/login.html",
            authentication_form=WMSAuthenticationForm,
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("", HomeView.as_view(), name="home"),
    path("senha/", SenhaView.as_view(), name="definir_senha"),
    # Administração da organização (feature 005). Sem `app_name`: `home`, `login` e `logout` já são
    # nomes globais e `LOGIN_URL = "login"` depende disso.
    path("organizacao/usuarios/", UsuariosView.as_view(), name="usuarios"),
    path("organizacao/usuarios/novo/", UsuarioNovoView.as_view(), name="usuario_novo"),
    path("organizacao/usuarios/<int:pk>/", UsuarioFichaView.as_view(), name="usuario"),
    path(
        "organizacao/usuarios/<int:pk>/editar/", UsuarioEditarView.as_view(), name="usuario_editar"
    ),
    path(
        "organizacao/usuarios/<int:pk>/papeis/", UsuarioPapeisView.as_view(), name="usuario_papeis"
    ),
    path(
        "organizacao/usuarios/<int:pk>/transferir/",
        UsuarioTransferirView.as_view(),
        name="usuario_transferir",
    ),
    path(
        "organizacao/usuarios/<int:pk>/desativar/",
        UsuarioDesativarView.as_view(),
        name="usuario_desativar",
    ),
    path(
        "organizacao/usuarios/<int:pk>/reativar/",
        UsuarioReativarView.as_view(),
        name="usuario_reativar",
    ),
    path(
        "organizacao/usuarios/<int:pk>/senha/",
        UsuarioRedefinirSenhaView.as_view(),
        name="usuario_redefinir_senha",
    ),
    path("organizacao/setores/", SetoresView.as_view(), name="setores"),
    path("organizacao/setores/novo/", SetorNovoView.as_view(), name="setor_novo"),
    path("organizacao/setores/<int:pk>/", SetorFichaView.as_view(), name="setor"),
    path("organizacao/setores/<int:pk>/editar/", SetorEditarView.as_view(), name="setor_editar"),
    path("organizacao/setores/<int:pk>/chefia/", SetorChefiaView.as_view(), name="setor_chefia"),
    path("organizacao/setores/<int:pk>/ativar/", SetorAtivarView.as_view(), name="setor_ativar"),
    path(
        "organizacao/setores/<int:pk>/desativar/",
        SetorDesativarView.as_view(),
        name="setor_desativar",
    ),
]
