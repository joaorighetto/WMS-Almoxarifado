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
- criar uma conta comum pelo Admin concede automaticamente apenas o papel
  mínimo `ROLE-REQUESTER` (`FR-016a`), sem inferir nenhum outro `Papel`
  (`ROLE-*`) a partir de `is_staff`/`is_superuser`
  (`docs/domain/permissions-matrix.md`, regras 3, 7 e 8);
- criar uma conta com `is_superuser=True` pelo Admin não concede
  `ROLE-REQUESTER` nem nenhum outro papel: a conta técnica de superusuário
  não é identidade de negócio, mesmo quando criada pelo Admin em vez de
  `createsuperuser` (`permissions-matrix.md`, regra 8; `FR-016a`);
- `INV-ORG-001`: o Admin não permite criar usuário sem setor.

Os testes de concessão de papel abaixo passam pela *view* real do Admin
(`Client.post`), não apenas por `form.save()` isolado: `ModelAdmin.save_form`
sempre chama `form.save(commit=False)` internamente, então uma concessão de
papel que só existisse dentro de `ContaCriacaoForm.save(commit=True)` nunca
seria exercida em produção — foi exatamente esse gap que deixou
`FR-016a` sem efeito quando a conta era criada pelo Admin de verdade.
"""

import pytest
from django.urls import reverse

from contas.admin import ContaAlteracaoForm, ContaCriacaoForm
from contas.models import PapelUsuario, Setor, User

SENHA = "uma-senha-de-admin-bastante-forte-123"


def _payload_inline_vazio(**campos):
    """Payload mínimo do form de criação, com o management form do inline
    `PapelUsuarioInline` vazio (nenhuma linha de papel adicionada à mão)."""
    payload = {
        "password1": SENHA,
        "password2": SENHA,
        "is_active": True,
        "papeis-TOTAL_FORMS": "0",
        "papeis-INITIAL_FORMS": "0",
        "papeis-MIN_NUM_FORMS": "0",
        "papeis-MAX_NUM_FORMS": "1000",
    }
    payload.update(campos)
    return payload


@pytest.fixture
def admin_logado(client, django_user_model):
    """Superusuário técnico autenticado no client, para acessar as views do
    Admin (`permissions-matrix.md`, regras 7-8: não é identidade de negócio,
    não recebe `ROLE-*` — só precisa de `is_staff`/`is_superuser`)."""
    setor = Setor.objects.create(nome="Almoxarifado")
    superuser = User.objects.create_superuser(
        matricula="root-admin", password=SENHA, setor=setor
    )
    client.force_login(superuser)
    return client, setor


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
def test_criacao_via_admin_concede_apenas_o_papel_minimo(admin_logado):
    """Regressão: `ModelAdmin.save_form` sempre chama `form.save(commit=False)`,
    então a concessão de `ROLE-REQUESTER` precisa sobreviver ao fluxo real do
    Admin (POST na view de adição) — não só a uma chamada direta a
    `form.save()`, que passava mesmo quando a conta criada pela view real
    ficava sem nenhum papel (`FR-016a`)."""
    client, setor = admin_logado

    resp = client.post(
        reverse("admin:contas_user_add"),
        data=_payload_inline_vazio(
            matricula="adm-002",
            setor=setor.pk,
            is_staff=False,
            is_superuser=False,
        ),
    )
    if resp.status_code == 200:
        pytest.fail(f"form inválido: {resp.context['adminform'].form.errors}")
    assert resp.status_code == 302

    usuario = User.objects.get(matricula="adm-002")

    # `FR-016a`: a criação administrativa é o segundo caminho suportado de
    # criação de identidade de negócio, e também concede o papel mínimo —
    # explicitamente, como linha persistida.
    assert list(usuario.papeis.values_list("papel", flat=True)) == ["ROLE-REQUESTER"]


@pytest.mark.django_db
def test_criacao_via_admin_de_superusuario_nao_concede_nenhum_papel(admin_logado):
    """A conta técnica de superusuário do Django não é identidade de negócio
    e não deve receber `ROLE-REQUESTER` nem nenhum outro papel, também
    quando criada pelo Admin — o mesmo padrão já seguido por
    `UserManager.create_superuser` para o outro caminho de criação suportado
    (`permissions-matrix.md`, regra 8; `FR-016a`)."""
    client, setor = admin_logado

    resp = client.post(
        reverse("admin:contas_user_add"),
        data=_payload_inline_vazio(
            matricula="adm-007",
            setor=setor.pk,
            is_staff=True,
            is_superuser=True,
        ),
    )
    if resp.status_code == 200:
        pytest.fail(f"form inválido: {resp.context['adminform'].form.errors}")
    assert resp.status_code == 302

    usuario = User.objects.get(matricula="adm-007")

    assert list(usuario.papeis.values_list("papel", flat=True)) == []


@pytest.mark.django_db
def test_criacao_via_admin_nao_duplica_papel_ja_concedido_no_inline(admin_logado):
    """Um administrador pode conceder `ROLE-REQUESTER` explicitamente pela
    linha do inline `PapelUsuarioInline` ao criar a conta — a concessão
    automática precisa apenas confirmar a linha já existente
    (`get_or_create`), nunca duplicá-la e violar
    `papelusuario_unico_usuario_papel`."""
    client, setor = admin_logado

    payload = _payload_inline_vazio(matricula="adm-005", setor=setor.pk)
    payload.update(
        {
            "papeis-TOTAL_FORMS": "1",
            "papeis-0-papel": "ROLE-REQUESTER",
            "papeis-0-id": "",
        }
    )
    resp = client.post(reverse("admin:contas_user_add"), data=payload)
    assert resp.status_code == 302

    usuario = User.objects.get(matricula="adm-005")
    assert list(usuario.papeis.values_list("papel", flat=True)) == ["ROLE-REQUESTER"]


@pytest.mark.django_db
def test_alteracao_via_admin_nao_re_concede_papel_removido(admin_logado):
    """Editar uma conta existente pelo Admin não deve re-conceder
    `ROLE-REQUESTER` (a concessão automática só se aplica à criação —
    `FR-023`: conta e papel mínimo nascem juntos ou não nascem; removê-lo
    depois é uma decisão deliberada, não revertida por uma edição comum)."""
    client, setor = admin_logado

    usuario = User.objects.create_user(matricula="adm-006", password=SENHA, setor=setor)
    PapelUsuario.objects.filter(usuario=usuario, papel="ROLE-REQUESTER").delete()

    resp = client.post(
        reverse("admin:contas_user_change", args=[usuario.pk]),
        data={
            "matricula": "adm-006",
            "setor": setor.pk,
            "is_active": True,
            "papeis-TOTAL_FORMS": "0",
            "papeis-INITIAL_FORMS": "0",
            "papeis-MIN_NUM_FORMS": "0",
            "papeis-MAX_NUM_FORMS": "1000",
        },
    )
    assert resp.status_code == 302

    usuario.refresh_from_db()
    assert list(usuario.papeis.values_list("papel", flat=True)) == []


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
