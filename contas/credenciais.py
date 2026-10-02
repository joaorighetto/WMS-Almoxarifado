"""Credenciais da organização (`contracts/credenciais.md`, research R8 a R12).

Validade da senha provisória, gerador, a definição obrigatória da própria senha no
primeiro acesso (US1) e a troca voluntária, com a senha atual (US6).
"""

import logging
import secrets
from datetime import timedelta

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone

from contas.models import TipoEvento, User

logger = logging.getLogger("contas.organizacao")

# Provisória vencida é recusada no login com a mesma mensagem de senha errada
# (research R9): a constante vive num só lugar.
VALIDADE_SENHA_PROVISORIA = timedelta(days=7)

_COMPRIMENTO_SENHA_PROVISORIA = 12
# Sem caracteres ambíguos para ditar ou copiar: nada de 0/O nem 1/l/I.
_LETRAS = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_DIGITOS = "23456789"
_ALFABETO = _LETRAS + _DIGITOS


def gerar_senha_provisoria() -> str:
    """12 caracteres de `secrets`, alfabeto sem `0 O 1 l I`, com ao menos uma
    letra e um dígito (satisfaz os validadores de senha de R12)."""
    while True:
        senha = "".join(secrets.choice(_ALFABETO) for _ in range(_COMPRIMENTO_SENHA_PROVISORIA))
        if any(c in _LETRAS for c in senha) and any(c in _DIGITOS for c in senha):
            return senha


def provisoria_vencida(usuario, agora=None) -> bool:
    """A credencial é provisória e passou de `VALIDADE_SENHA_PROVISORIA` (research R9)."""
    if usuario.senha_provisoria_em is None:
        return False
    return (agora or timezone.now()) > usuario.senha_provisoria_em + VALIDADE_SENHA_PROVISORIA


def _exigir_senha_na_politica(nova, usuario):
    """Política de R12 (`AUTH_PASSWORD_VALIDATORS`) sobre a senha nova da conta."""
    from contas.organizacao import _recusar

    try:
        validate_password(nova, usuario)
    except ValidationError as exc:
        raise _recusar(" ".join(exc.messages), "Escolha outra senha.") from exc


def definir_propria_senha(request, usuario, nova):
    """Definição obrigatória da própria senha, no primeiro acesso (FR-034, FR-036, D-27).

    Numa operação de organização (a barreira recusa `senha_provisoria_em` fora dela): relê a
    conta sob o lock, exige credencial ainda provisória e vigente, política de R12 e senha
    diferente da provisória; grava o hash, limpa `senha_provisoria_em` e registra
    `SENHA_DEFINIDA` com o próprio usuário como autor — sem a senha. Depois do commit, mantém a
    sessão em uso e encerra as demais (`update_session_auth_hash`). Recusa levanta
    `OperacaoRecusada` sem alterar nada.
    """
    # `organizacao` importa este módulo (`gerar_senha_provisoria`): o import local evita o ciclo.
    from contas.organizacao import _operacao, _recusar, _registrar_evento

    with _operacao():
        atual = User.objects.get(pk=usuario.pk)
        if atual.senha_provisoria_em is None:
            raise _recusar("A senha já foi definida.", "Use a troca de senha.")
        if provisoria_vencida(atual):
            raise _recusar("A senha provisória venceu.", "Peça uma nova ao administrador.")
        if atual.check_password(nova):
            raise _recusar(
                "A nova senha precisa ser diferente da senha provisória.",
                "Escolha outra senha.",
            )
        _exigir_senha_na_politica(nova, atual)
        atual.set_password(nova)
        atual.senha_provisoria_em = None
        atual.save(update_fields=["password", "senha_provisoria_em"])
        _registrar_evento(
            atual,
            TipoEvento.SENHA_DEFINIDA,
            usuario=atual,
            dados={"motivo": "definicao_obrigatoria"},
        )
    update_session_auth_hash(request, atual)
    return atual


def trocar_propria_senha(request, usuario, atual, nova):
    """Troca voluntária da própria senha, com a senha atual (FR-037, FR-038, D-27).

    Mesma forma de `definir_propria_senha`: numa operação de organização, relê a conta sob o lock,
    exige a senha atual correta e a política de R12, grava o hash e registra `SENHA_DEFINIDA`
    (`motivo: troca_voluntaria`) com o próprio usuário como autor — sem nenhuma das senhas. Só vale
    com credencial já definitiva: a provisória tem a definição obrigatória. Depois do commit,
    mantém a sessão em uso e encerra as demais. Recusa levanta `OperacaoRecusada` sem alterar nada.
    """
    from contas.organizacao import _operacao, _recusar, _registrar_evento

    with _operacao():
        conta = User.objects.get(pk=usuario.pk)
        if conta.senha_provisoria_em is not None:
            raise _recusar(
                "A credencial ainda é provisória.",
                "Defina a sua senha pela tela de primeiro acesso.",
            )
        if not conta.check_password(atual):
            raise _recusar("A senha atual não confere.", "Confira a senha atual e tente de novo.")
        _exigir_senha_na_politica(nova, conta)
        conta.set_password(nova)
        conta.save(update_fields=["password"])
        _registrar_evento(
            conta,
            TipoEvento.SENHA_DEFINIDA,
            usuario=conta,
            dados={"motivo": "troca_voluntaria"},
        )
    update_session_auth_hash(request, conta)
    return conta
