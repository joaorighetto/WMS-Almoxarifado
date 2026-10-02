"""Backend de autenticação do WMS (research R9 da 005)."""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from contas.credenciais import provisoria_vencida


class WMSModelBackend(ModelBackend):
    """`ModelBackend` que também recusa o login com senha provisória vencida.

    O vencimento é indistinguível, para quem tenta entrar, de uma senha errada
    (FR-003 da 002, FR-035). `get_user` só exige conta ativa: numa sessão já aberta, quem
    encerra a credencial vencida é o `CredencialProvisoriaMiddleware`, que precisa enxergar o
    usuário para fazer o logout.
    """

    def user_can_authenticate(self, user):
        return super().user_can_authenticate(user) and not provisoria_vencida(user)

    def get_user(self, user_id):
        try:
            user = get_user_model()._default_manager.get(pk=user_id)
        except get_user_model().DoesNotExist:
            return None
        return user if super().user_can_authenticate(user) else None
