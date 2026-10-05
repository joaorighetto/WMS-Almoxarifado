from django.utils.functional import SimpleLazyObject

from contas.navegacao import montar_navegacao


def navegacao(request):
    """Expõe `navegacao` a todo template de usuário autenticado. Preguiçoso: nenhuma consulta
    ao banco até um template ler um atributo. Anônimo: sem a chave."""
    if not request.user.is_authenticated:
        return {}
    return {"navegacao": SimpleLazyObject(lambda: montar_navegacao(request))}
