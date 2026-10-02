"""Apoio exclusivo dos testes da organização (feature 005).

Não é fixture global (`tests/conftest.py` é da T013): reúne só o que mais de um
arquivo `test_contas_*` precisa — montar organizações válidas pela API de
provisionamento (T011) e construir, de forma controlada, estados que a
aplicação nunca produz, para provar que a validação e o banco os recusam.

Suposições de nome que o implementador precisa respeitar (ou ajustar AQUI, em
um único lugar, se divergirem):

- `contas.organizacao._operacao()`: o context manager interno que abre
  `transaction.atomic()`, toma o advisory lock e liga a barreira de escrita
  (research R2/R4, T010);
- `contas.organizacao.validar_organizacao(setores, usuarios)`: aceita iteráveis
  (querysets, listas ou sets) de instâncias de `Setor` e `User`;
- `provisionar_usuario(..., papeis=...)` recebe os papéis ADICIONAIS; o
  `ROLE-REQUESTER` é sempre concedido pela própria criação (FR-016a) e não
  precisa ser informado.
"""

import html as html_lib
import re
import threading
import uuid
from contextlib import contextmanager

import pytest
from django.db import connection, transaction
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from contas import organizacao as org
from contas.models import EventoOrganizacional, Papel, PapelUsuario, Setor, User

SENHA_TESTE = "uma-senha-de-teste-bastante-forte-123"

# Composição exigida do chefe do Almoxarifado (INV-ORG-006): três papéis
# explícitos, nunca herdados.
PAPEIS_CHEFE_ALMOXARIFADO = frozenset(
    {Papel.CHEFE_SETOR, Papel.CHEFE_ALMOXARIFADO, Papel.FUNCIONARIO_ALMOXARIFADO}
)


def operacao():
    """Marcador de operação organizacional (liga a barreira de escrita)."""
    return org._operacao()


def validar_tudo():
    """`validar_organizacao` sobre todo o banco; levanta `OperacaoRecusada`."""
    org.validar_organizacao(Setor.objects.all(), User.objects.all())


class _Descartar(Exception):
    """Sinal interno para desfazer o savepoint de `estado_descartavel`."""


@contextmanager
def estado_descartavel():
    """Abre uma operação e DESFAZ tudo o que o bloco escrever.

    Serve para montar um estado que a aplicação nunca produz (setor ativo sem
    chefe, papel de almoxarifado fora do Almoxarifado...) e chamar
    `validar_tudo()` sobre ele. O savepoint é revertido ao fim: testes não
    transacionais do pytest-django executam `check_constraints()` no teardown, o
    que dispara o trigger adiado sobre qualquer estado inválido que ficasse
    pendente.
    """
    try:
        with transaction.atomic():
            with operacao():
                yield
            raise _Descartar
    except _Descartar:
        pass


def rodar_em_threads(alvos, timeout=20):
    """Executa `alvos` (`nome -> callable` sem argumentos) em threads reais, uma
    conexão por thread, todas liberadas juntas por uma `Barrier` — nunca duas chamadas
    sequenciais no lugar de concorrência. Só para testes `django_db(transaction=True)`.

    Devolve `nome -> valor de retorno ou exceção capturada` (a exceção é devolvida, não
    propagada, para o teste poder afirmar sobre ela).
    """
    resultados = {}
    barreira = threading.Barrier(len(alvos), timeout=10)

    def executar(nome, funcao):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
            barreira.wait()
            resultados[nome] = funcao()
        except Exception as exc:  # noqa: BLE001 — devolvida ao teste
            resultados[nome] = exc
        finally:
            connection.close()

    threads = [
        threading.Thread(target=executar, args=(nome, funcao)) for nome, funcao in alvos.items()
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=timeout)
    assert not any(thread.is_alive() for thread in threads), "thread não terminou no timeout"
    return resultados


def membro(setor, matricula, papeis=(), *, is_active=True):
    """Usuário do setor, criado pela API de provisionamento (senha conhecida)."""
    usuario, _ = org.provisionar_usuario(
        matricula,
        f"Pessoa {matricula}",
        setor,
        set(papeis),
        senha=SENHA_TESTE,
        is_active=is_active,
    )
    return usuario


def almoxarifado_ativo(matricula_chefe="almox-chefe"):
    """Almoxarifado designado, com chefe completo (3 papéis), já ativado."""
    setor = org.provisionar_setor("Almoxarifado Central", almoxarifado=True)
    chefe = membro(setor, matricula_chefe, PAPEIS_CHEFE_ALMOXARIFADO)
    org.provisionar_ativacao(setor)
    setor.refresh_from_db()
    return setor, chefe


def setor_ativo(nome, matricula_chefe):
    """Setor comum com um chefe (`ROLE-SECTOR-HEAD`), já ativado."""
    setor = org.provisionar_setor(nome)
    chefe = membro(setor, matricula_chefe, {Papel.CHEFE_SETOR})
    org.provisionar_ativacao(setor)
    setor.refresh_from_db()
    return setor, chefe


# ---------------------------------------------------------------------------
# Apoio das stories de interface e credenciais (US1, US2 — tasks T017 a T027)
# ---------------------------------------------------------------------------
#
# Contratos de nome FIXADOS pelos testes (ajustar AQUI, num só lugar, se a
# implementação divergir):
#
# - rotas de `contas`: `rota("usuarios")`, `rota("usuario", pk)`, `rota("definir_senha")`...
#   resolvem o nome sem namespace e, se não existir, `contas:<nome>`;
# - campos do formulário de `/senha/` (`CAMPOS_SENHA`): os do `SetPasswordForm` /
#   `PasswordChangeForm` do Django;
# - parâmetro de página (`PARAM_PAGINA`): `pagina`, como no catálogo;
# - filtros GET de `usuarios`: `q`, `setor` (pk), `situacao` (`ativo`/`inativo`),
#   `papel` (valor de `Papel`); de `setores`: `q`, `situacao`.

PARAM_PAGINA = "pagina"

CAMPOS_SENHA = {
    "atual": "old_password",
    "nova": "new_password1",
    "confirmacao": "new_password2",
}

SENHA_PROVISORIA_CONHECIDA = "Zk7Qm3Xp9Rtw"
SENHA_NOVA_VALIDA = "Cavalo-Azul-Distante-4718"


def rota(nome, *args):
    """URL de uma rota de `contas`, com ou sem o namespace `contas:`.

    O contrato fala em `app_name = "contas"`, mas `home`, `login` e `logout` já existem sem
    namespace e as demais suítes fazem `reverse("home")`: a resolução tolera as duas formas
    para que o teste não decida essa escolha pelo implementador.
    """
    try:
        return reverse(nome, args=args)
    except NoReverseMatch:
        pass
    try:
        return reverse(f"contas:{nome}", args=args)
    except NoReverseMatch:
        raise NoReverseMatch(
            f"a rota {nome!r} (args={args}) não existe, nem sem namespace nem em 'contas:'"
        ) from None


def foto_organizacao():
    """Tudo o que uma operação organizacional pode escrever. Igualdade antes/depois prova
    que uma recusa (ou um 403) não deixou nada. `last_login` fica de fora: login não é
    escrita organizacional."""
    return {
        "usuarios": sorted(
            User.objects.values_list(
                "pk",
                "matricula",
                "nome",
                "nome_busca",
                "setor_id",
                "is_active",
                "is_superuser",
                "senha_provisoria_em",
                "password",
            )
        ),
        "setores": sorted(
            Setor.objects.values_list("pk", "nome", "ativo", "almoxarifado", "ativado_em")
        ),
        "papeis": sorted(PapelUsuario.objects.values_list("usuario_id", "papel")),
        "eventos": sorted(EventoOrganizacional.objects.values_list("pk", "tipo")),
    }


def fixar_senha_gerada(monkeypatch, valor=SENHA_PROVISORIA_CONHECIDA):
    """Faz `gerar_senha_provisoria` devolver `valor`, para os testes saberem a senha que a
    operação exibirá. Substitui o nome nos dois módulos: o de origem e o importado por
    `contas.organizacao`."""
    monkeypatch.setattr("contas.credenciais.gerar_senha_provisoria", lambda: valor)
    monkeypatch.setattr("contas.organizacao.gerar_senha_provisoria", lambda: valor)
    return valor


def membro_provisorio(setor, matricula, papeis=()):
    """Usuário com credencial PROVISÓRIA (sem `senha=`): `(usuario, senha_provisoria)`."""
    return org.provisionar_usuario(matricula, f"Pessoa {matricula}", setor, set(papeis))


def envelhecer_provisoria(usuario, tempo):
    """Recua `senha_provisoria_em` para `agora - tempo`, sem esperar e sem mexer no relógio."""
    with operacao():
        User.objects.filter(pk=usuario.pk).update(senha_provisoria_em=timezone.now() - tempo)


def vencimento_da_provisoria(usuario):
    """Momento em que a provisória vence (`senha_provisoria_em` + 7 dias)."""
    from contas.credenciais import VALIDADE_SENHA_PROVISORIA

    usuario.refresh_from_db()
    return usuario.senha_provisoria_em + VALIDADE_SENHA_PROVISORIA


def data_hora(momento):
    """`DD/MM/AAAA HH:MM` no fuso do projeto — formato de data das fichas."""
    return timezone.localtime(momento).strftime("%d/%m/%Y %H:%M")


def recusa_de(funcao):
    """Chama `funcao` esperando `OperacaoRecusada` e devolve a exceção."""
    with pytest.raises(org.OperacaoRecusada) as excecao:
        funcao()
    return excecao.value


def chave_do_formulario(resposta):
    """`chave_confirmacao` (UUID) do formulário renderizado, lida do `<input>` oculto."""
    conteudo = resposta.content.decode()
    for tag in re.findall(r"<input\b[^>]*>", conteudo):
        if re.search(r"""name=["']chave_confirmacao["']""", tag):
            valor = re.search(r"""value=["']([^"']+)["']""", tag)
            assert valor, f"input chave_confirmacao sem value: {tag}"
            return uuid.UUID(valor.group(1))
    raise AssertionError("o formulário não traz o campo chave_confirmacao")


def dados_do_cadastro(setor, /, **substituicoes):
    """Corpo de POST do formulário de cadastro (`usuario_novo`), válido por padrão."""
    dados = {
        "matricula": "NOVO-0001",
        "nome": "Maria da Silva",
        "setor": str(setor.pk),
        "papeis": [],
        "chave_confirmacao": str(uuid.uuid4()),
    }
    dados.update(substituicoes)
    return dados


def texto_visivel(conteudo):
    """HTML → texto corrido (sem tags, entidades resolvidas, espaços colapsados)."""
    sem_tags = re.sub(r"<[^>]+>", " ", conteudo)
    return re.sub(r"\s+", " ", html_lib.unescape(sem_tags)).strip()


def texto_principal(conteudo):
    """Texto visível só do `<main>` (sem `<title>` nem a barra com a marca do sistema)."""
    achado = re.search(r"<main\b.*?</main>", conteudo, re.S)
    return texto_visivel(achado.group(0) if achado else conteudo)


def hrefs(conteudo):
    """Todos os `href` do HTML, sem estáticos."""
    return {
        href
        for href in re.findall(r"""href=["']([^"']+)["']""", conteudo)
        if not href.startswith("/static/")
    }


def mensagens(resposta):
    """Textos das mensagens (framework `messages`) enfileiradas pela requisição."""
    from django.contrib.messages import get_messages

    return [str(mensagem) for mensagem in get_messages(resposta.wsgi_request)]
