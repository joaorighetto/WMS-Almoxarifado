from django.contrib.auth.views import LogoutView
from django.urls import path

from contas.forms import WMSAuthenticationForm
from contas.views import HomeView, WMSLoginView

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
]
