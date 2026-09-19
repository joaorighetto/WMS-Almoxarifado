"""Testes do Django Admin de `contas`.

O Admin não é tela de produto: é a ferramenta técnica de bootstrap/manutenção
(`research.md` R6) e, enquanto a administração de usuários não for
especificada, o **único** meio de criar contas, definir senha e conceder
`Papel` fora dos testes. Por isso os caminhos abaixo são protegidos contra
regressão, ainda que `manage.py check` já valide a *configuração* do Admin.

Protegido aqui:
- senha nunca é gravada crua — sempre via `set_password()`/hashers nativos
  (Constitution, Princípio VI);
- o formulário de alteração não expõe a senha como campo editável em texto;
- criar uma conta pelo Admin não concede nenhum `Papel` (`ROLE-*`)
  automaticamente (`docs/domain/permissions-matrix.md`, regras 3, 7 e 8);
- `INV-ORG-001`: o Admin não permite criar usuário sem setor.
"""

import pytest

from contas.admin import ContaAlteracaoForm, ContaCriacaoForm
from contas.models import Setor, User

SENHA = "uma-senha-de-admin-bastante-forte-123"


@pytest.mark.django_db
def test_criacao_via_admin_grava_senha_com_hash_nunca_crua():
    setor = Setor.objects.create(nome="Almoxarifado")

    form = ContaCriacaoForm(
        data={
            "matricula": "adm-001",
            "setor": setor.pk,
            "password1": SENHA,
            "password2": SENHA,
            "is_active": True,
        }
    )
    assert form.is_valid(), form.errors

    usuario = form.save()

    assert usuario.password != SENHA, "senha crua nunca pode ser persistida"
    assert usuario.check_password(SENHA), "a senha definida precisa autenticar"
    assert usuario.password.startswith("pbkdf2_"), (
        "deve usar o hasher nativo do Django, nunca criptografia própria"
    )


@pytest.mark.django_db
def test_criacao_via_admin_concede_apenas_o_papel_minimo():
    setor = Setor.objects.create(nome="Almoxarifado")

    form = ContaCriacaoForm(
        data={
            "matricula": "adm-002",
            "setor": setor.pk,
            "password1": SENHA,
            "password2": SENHA,
            "is_active": True,
            "is_staff": True,
            "is_superuser": True,
        }
    )
    assert form.is_valid(), form.errors

    usuario = form.save()

    # `FR-016a`: a criação administrativa é o segundo caminho suportado de
    # criação de identidade de negócio, e também concede o papel mínimo —
    # explicitamente, como linha persistida.
    assert list(usuario.papeis.values_list("papel", flat=True)) == ["ROLE-REQUESTER"]
    assert usuario.tem_papel("ROLE-SYSTEM-ADMIN") is False, (
        "marcar is_superuser no Admin não concede ROLE-SYSTEM-ADMIN "
        "(permissions-matrix, regras 7-8)"
    )


@pytest.mark.django_db
def test_criacao_via_admin_exige_setor():
    form = ContaCriacaoForm(
        data={
            "matricula": "adm-003",
            "password1": SENHA,
            "password2": SENHA,
            "is_active": True,
        }
    )

    assert form.is_valid() is False, "INV-ORG-001: usuário sem setor não pode ser criado"
    assert "setor" in form.errors


@pytest.mark.django_db
def test_form_de_alteracao_nao_expoe_senha_editavel_em_texto():
    setor = Setor.objects.create(nome="Almoxarifado")
    usuario = User.objects.create_user(matricula="adm-004", password=SENHA, setor=setor)
    hash_original = usuario.password

    form = ContaAlteracaoForm(instance=usuario)

    # `ReadOnlyPasswordHashField` nativo: mostra o hash, nunca um input de texto
    # que permita gravar senha crua ao salvar.
    assert form.fields["password"].disabled is True
    assert form.initial.get("password") == hash_original
