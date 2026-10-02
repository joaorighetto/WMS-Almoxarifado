"""Formulários de `contas`: autenticação do WMS e, ao fim, os da administração da organização
(feature 005: definição e troca de senha, cadastro, edição, papéis, transferência, desativação,
reativação e redefinição de senha de usuário, setor, chefia de setor e filtros das listas).

O restante desta docstring cobre só o formulário de autenticação.

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

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, SetPasswordForm
from django.urls import reverse_lazy

from contas.models import Papel, Setor, User


class WMSAuthenticationForm(AuthenticationForm):
    """`AuthenticationForm` nativo com uma única mensagem de recusa reescrita.

    A string permanece **genérica e idêntica** para as três causas de recusa —
    senha incorreta, matrícula inexistente e conta inativa —, preservando
    `FR-003`/`SC-003` (não-enumeração de usuário): nada no texto revela qual
    das condições ocorreu.
    """

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": ("Matrícula ou senha inválidas. Confira os dados e tente novamente."),
    }


class DefinirSenhaForm(SetPasswordForm):
    """Definição obrigatória da própria senha (`/senha/`, estado provisório).

    Só valida: nova senha, confirmação e a política de `AUTH_PASSWORD_VALIDATORS` (R12) vêm do
    `SetPasswordForm`. Quem grava é `contas.credenciais.definir_propria_senha`, que sozinha tem
    permissão de escrever a credencial — por isso não se chama `save()` aqui.
    """


class TrocarSenhaForm(PasswordChangeForm):
    """Troca voluntária da própria senha (`/senha/`, credencial definitiva): senha atual, nova e
    confirmação (`old_password`, `new_password1`, `new_password2`). Como `DefinirSenhaForm`, só
    valida — quem grava é `contas.credenciais.trocar_propria_senha`, que confere a senha atual
    de novo sob o lock."""


PAPEIS_ADICIONAIS = [
    (valor, rotulo) for valor, rotulo in Papel.choices if valor != Papel.REQUISITANTE
]


class UsuarioCadastroForm(forms.Form):
    """Cadastro de usuário (`usuario_novo`). `ROLE-REQUESTER` não é opção: toda conta o recebe
    (FR-016a). As regras de domínio (chefia, papéis de almoxarifado) são de
    `organizacao.cadastrar_usuario`; aqui só a forma dos dados. A `chave_confirmacao` oculta é a
    chave de idempotência do POST (research R8)."""

    matricula = forms.CharField(
        label="Matrícula", max_length=User._meta.get_field("matricula").max_length
    )
    nome = forms.CharField(label="Nome", max_length=User._meta.get_field("nome").max_length)
    # Ao mudar o setor, a região de papéis é trocada por HTMX: `usuario_novo?setor=<pk>` devolve só
    # o parcial dos papéis (os já marcados seguem na requisição). Sem JS, o envio re-renderiza.
    setor = forms.ModelChoiceField(
        label="Setor",
        queryset=Setor.objects.order_by("nome"),
        empty_label="Escolha o setor",
        widget=forms.Select(
            attrs={
                "hx-get": reverse_lazy("usuario_novo"),
                "hx-trigger": "change",
                "hx-target": "#papeis-cadastro",
                "hx-swap": "outerHTML",
                "hx-include": "#papeis-cadastro",
            }
        ),
    )
    papeis = forms.MultipleChoiceField(
        label="Papéis adicionais",
        choices=PAPEIS_ADICIONAIS,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    chave_confirmacao = forms.UUIDField(widget=forms.HiddenInput)


class UsuarioEdicaoForm(forms.Form):
    """Edição de nome e matrícula (`usuario_editar`). A unicidade da matrícula e o que mais
    couber ao domínio são de `organizacao.editar_usuario`; aqui só a forma dos dados."""

    nome = forms.CharField(label="Nome", max_length=User._meta.get_field("nome").max_length)
    matricula = forms.CharField(
        label="Matrícula", max_length=User._meta.get_field("matricula").max_length
    )


class UsuarioPapeisForm(forms.Form):
    """Conjunto DESEJADO de papéis (`usuario_papeis`), com os sete códigos possíveis; a view
    calcula o que conceder e remover contra o estado atual. Código fora do catálogo é erro do
    formulário. Quais papéis podem mudar é decisão de `organizacao.alterar_papeis`."""

    papeis = forms.MultipleChoiceField(label="Papéis", choices=Papel.choices, required=False)


class TransferenciaForm(forms.Form):
    """Transferência em duas etapas (`usuario_transferir`): o primeiro envio traz o destino e
    mostra a prévia; o segundo traz `confirmar` e os papéis que a prévia anunciou remover.
    Recusas de domínio (destino igual, chefe de setor ativo) são de `organizacao`."""

    setor = forms.ModelChoiceField(
        label="Setor de destino",
        queryset=Setor.objects.order_by("nome"),
        empty_label="Escolha o setor",
    )
    confirmar = forms.BooleanField(required=False)
    papeis_removidos_previstos = forms.MultipleChoiceField(choices=Papel.choices, required=False)


class ChefiaForm(forms.Form):
    """Chefia do setor (`setor_chefia`). O estado do setor (`estado`: `substituir`, `designar` ou
    `retirar`) decide qual campo é obrigatório. Os pks de usuário não são limitados a um
    queryset: um candidato fora do alcance (outro setor, inativo, conta técnica) é recusado por
    `organizacao`, com motivo e caminho (FR-015, FR-048). `confirmar` é a segunda etapa da
    substituição e da retirada; a substituição confirmada traz `chefe_esperado` (FR-017) e os
    efeitos que a prévia mostrou (`novo_ganha_previsto`, `anterior_perde_previsto`), conferidos
    pela operação (FR-049)."""

    novo_chefe = forms.IntegerField(label="Novo chefe", min_value=1, required=False)
    usuario = forms.IntegerField(label="Chefe", min_value=1, required=False)
    chefe_esperado = forms.IntegerField(label="Chefe atual", min_value=1, required=False)
    novo_ganha_previsto = forms.MultipleChoiceField(choices=Papel.choices, required=False)
    anterior_perde_previsto = forms.MultipleChoiceField(choices=Papel.choices, required=False)
    confirmar = forms.BooleanField(required=False)

    def __init__(self, *args, estado, **kwargs):
        super().__init__(*args, **kwargs)
        self.estado = estado
        obrigatorio = {"substituir": "novo_chefe", "designar": "usuario"}.get(estado)
        if obrigatorio:
            self.fields[obrigatorio].required = True

    def clean(self):
        dados = super().clean()
        if (
            self.estado == "substituir"
            and dados.get("confirmar")
            and not dados.get("chefe_esperado")
        ):
            self.add_error("chefe_esperado", "Informe o chefe atual que você viu ao confirmar.")
        return dados


class DesativacaoForm(forms.Form):
    """Desativação de usuário (`usuario_desativar`): `confirmar` é a segunda etapa; a
    `justificativa` é opcional e vai ao evento. Recusas de domínio são de `organizacao`."""

    justificativa = forms.CharField(
        label="Justificativa", max_length=500, required=False, widget=forms.Textarea
    )
    confirmar = forms.BooleanField(required=False)


class ReativacaoForm(forms.Form):
    """Reativação de usuário (`usuario_reativar`): `papeis` é o conjunto MANTIDO e `confirmar` a
    segunda etapa. Código fora do catálogo é erro do formulário; quais papéis podem voltar é
    decisão de `organizacao.reativar_usuario`."""

    papeis = forms.MultipleChoiceField(label="Papéis", choices=Papel.choices, required=False)
    confirmar = forms.BooleanField(required=False)


class RedefinicaoSenhaForm(forms.Form):
    """Redefinição da senha de terceiros (`usuario_redefinir_senha`): só a `chave_confirmacao`
    de idempotência (research R8). A senha nova nunca é escolhida pelo administrador (D-13)."""

    chave_confirmacao = forms.UUIDField(widget=forms.HiddenInput)


class ConfirmacaoForm(forms.Form):
    """Confirmação simples (`setor_ativar`, `setor_desativar`): sem `confirmar`, a tela só mostra
    o que será feito. Recusas de domínio são de `organizacao`."""

    confirmar = forms.BooleanField(required=False)


class SetorForm(forms.Form):
    """Criação e renomeação de setor (`setor_novo`, `setor_editar`). O limite é o do campo; a
    unicidade do nome e o que mais couber ao domínio são de `organizacao`."""

    nome = forms.CharField(label="Nome", max_length=Setor._meta.get_field("nome").max_length)


class FiltroUsuariosForm(forms.Form):
    """Filtros GET da lista de usuários. Valor inválido é ignorado (o filtro some), nunca erro."""

    q = forms.CharField(label="Nome ou matrícula", required=False)
    setor = forms.ModelChoiceField(
        label="Setor",
        queryset=Setor.objects.order_by("nome"),
        required=False,
        empty_label="Todos os setores",
    )
    situacao = forms.ChoiceField(
        label="Situação",
        choices=[("", "Todas"), ("ativo", "Ativo"), ("inativo", "Inativo")],
        required=False,
    )
    papel = forms.ChoiceField(
        label="Papel", choices=[("", "Todos"), *Papel.choices], required=False
    )


class FiltroSetoresForm(forms.Form):
    """Filtros GET da lista de setores."""

    q = forms.CharField(label="Nome do setor", required=False)
    situacao = forms.ChoiceField(
        label="Situação",
        choices=[("", "Todas"), ("ativo", "Ativo"), ("inativo", "Inativo")],
        required=False,
    )
