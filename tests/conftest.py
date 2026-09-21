"""Fixtures compartilhadas entre os testes de `contas`.

Mantidas deliberadamente mínimas: apenas o necessário para criar um `Setor`
válido (`INV-ORG-001`) e usuários de teste através do manager real
(`User.objects.create_user`), nunca construindo instâncias manualmente ou
ignorando `set_password()`.
"""

import pytest

from contas.models import Setor, User

SENHA_VALIDA = "uma-senha-de-teste-bastante-forte-123"


@pytest.fixture
def senha_valida():
    """Senha padrão usada pelos usuários criados por `criar_usuario`."""
    return SENHA_VALIDA


@pytest.fixture
def setor(db):
    """Setor mínimo exigido por `INV-ORG-001` para qualquer `User`."""
    return Setor.objects.create(nome="Almoxarifado Central")


@pytest.fixture
def criar_usuario(db, setor):
    """Factory de usuários de teste, sempre vinculados a um setor válido.

    Gera uma matrícula única por chamada quando nenhuma é informada, para
    permitir criar múltiplos usuários no mesmo teste sem colisão.
    """
    contador = {"valor": 0}

    def _criar_usuario(*, matricula=None, password=None, is_active=True, **extra):
        contador["valor"] += 1
        if matricula is None:
            matricula = f"MAT-TESTE-{contador['valor']:04d}"
        if password is None:
            password = SENHA_VALIDA
        extra.setdefault("setor", setor)
        return User.objects.create_user(
            matricula=matricula, password=password, is_active=is_active, **extra
        )

    return _criar_usuario


@pytest.fixture
def usuario_ativo(criar_usuario):
    """Usuário ativo padrão, com senha `SENHA_VALIDA`."""
    return criar_usuario(matricula="0001234")
