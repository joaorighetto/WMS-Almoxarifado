"""Formulários de autenticação do WMS.

Escopo deliberadamente mínimo — ver `research.md` R3 (reabertura parcial,
revisão 3). Este módulo existe por **um** motivo concreto e verificado em
execução: a mensagem de recusa traduzida do Django em pt-BR sai como
"Por favor, entre com um matrícula e senha corretos…". O `%(username)s` é
interpolado com o `verbose_name` do `USERNAME_FIELD`, e "matrícula" é
feminino — o artigo masculino produz um desacordo de gênero visível toda vez
que alguém erra a senha.

O que este módulo NÃO faz, por decisão registrada:
- não implementa autenticação própria (continua `ModelBackend`);
- não sobrescreve `confirm_login_allowed()` — inalcançável com o backend
  padrão, porque `authenticate()` já rejeita `is_active=False` antes;
- não toca rótulo nem `max_length` dos campos — ambos já vêm do model.
"""

from django.contrib.auth.forms import AuthenticationForm


class WMSAuthenticationForm(AuthenticationForm):
    """`AuthenticationForm` nativo com uma única mensagem de recusa reescrita.

    A string permanece **genérica e idêntica** para as três causas de recusa —
    senha incorreta, matrícula inexistente e conta inativa —, preservando
    `FR-003`/`SC-003` (não-enumeração de usuário): nada no texto revela qual
    das condições ocorreu.
    """

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Matrícula ou senha inválidas.",
    }
