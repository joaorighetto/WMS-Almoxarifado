"""Provisionamento inicial da organização (FR-050, research R15 da 005).

Cria, em banco sem nenhum setor nem identidade de negócio, o único Almoxarifado, a primeira
identidade de negócio (administrador de sistema e chefe do Almoxarifado) e ativa o setor.
Tudo pela API de `contas.organizacao`, com autor nulo e numa só transação. Imprime a senha
provisória uma única vez, depois do commit.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from contas.models import Papel, Setor, User
from contas.organizacao import (
    CHAVE_LOCK_ORGANIZACAO,
    OperacaoRecusada,
    provisionar_ativacao,
    provisionar_setor,
    provisionar_usuario,
)

PAPEIS_DA_PRIMEIRA_IDENTIDADE = frozenset(
    {
        Papel.ADMINISTRADOR_SISTEMA,
        Papel.CHEFE_SETOR,
        Papel.CHEFE_ALMOXARIFADO,
        Papel.FUNCIONARIO_ALMOXARIFADO,
    }
)


class Command(BaseCommand):
    help = (
        "Cria o Almoxarifado e a primeira identidade de negócio (administrador de sistema e "
        "chefe do Almoxarifado) em banco sem setor nem identidade de negócio."
    )

    def add_arguments(self, parser):
        parser.add_argument("--setor-almoxarifado", required=True, help="Nome do Almoxarifado.")
        parser.add_argument("--matricula", required=True, help="Matrícula da primeira identidade.")
        parser.add_argument("--nome", required=True, help="Nome da primeira identidade.")

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                # Mesmo lock das operações: duas execuções não passam juntas pela checagem.
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(%s)", [CHAVE_LOCK_ORGANIZACAO])
                if Setor.objects.exists() or User.objects.filter(is_superuser=False).exists():
                    raise CommandError(
                        "O banco já tem setor ou identidade de negócio: o provisionamento "
                        "inicial só roda em banco sem organização. Nada foi gravado."
                    )
                setor = provisionar_setor(options["setor_almoxarifado"], almoxarifado=True)
                _, senha = provisionar_usuario(
                    options["matricula"],
                    options["nome"],
                    setor,
                    PAPEIS_DA_PRIMEIRA_IDENTIDADE,
                )
                provisionar_ativacao(setor)
        except OperacaoRecusada as exc:
            raise CommandError(
                f"{exc.motivo} {exc.caminho or ''}".strip() + " Nada foi gravado."
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Organização provisionada: Almoxarifado '{options['setor_almoxarifado']}' "
                f"ativo e conta {options['matricula']}."
            )
        )
        self.stdout.write(
            "Senha provisória (exibida uma única vez; deve ser trocada no primeiro acesso): "
            f"{senha}"
        )
