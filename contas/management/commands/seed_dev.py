"""Bootstrap explícito de desenvolvimento, atômico e repetível."""

import os
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from catalogo.importacao import (
    CHAVE_LOCK_IMPORTACAO_SCPI,
    PedidoPrevia,
    calcular_plano,
    confirmar_importacao,
)
from catalogo.leitura_scpi import LIMITE_TAMANHO_ARQUIVO, ArquivoRecusado, ler_registros
from catalogo.models import ExecucaoImportacao, Material
from contas.dev_seed.dados import SETORES, USUARIOS, revisao_simulada
from contas.models import Papel, PapelUsuario, Setor, User

# Identificadores públicos de idempotência, não credenciais ou tokens de autenticação.
SEED_TOKENS = (
    UUID("f76e99e0-bfc4-497b-a566-816dc567c001"),
    UUID("f76e99e0-bfc4-497b-a566-816dc567c002"),
    UUID("f76e99e0-bfc4-497b-a566-816dc567c003"),
)
CATALOGO_PADRAO = Path("docs/domain-legacy/relacao-de-todos-produtos-importados-do-SCPI.csv")


class Command(BaseCommand):
    help = "Prepara contas, catálogo SCPI e históricos de demonstração no banco de desenvolvimento."
    # --check precisa funcionar antes da criação do schema, sem qualquer consulta.
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument(
            "--check", action="store_true",
            help="Valida ambiente, senha e catálogo sem acessar o banco.",
        )
        parser.add_argument(
            "--catalogo", type=Path,
            help="CSV SCPI de origem; padrão: arquivo local em docs/domain-legacy.",
        )

    def handle(self, *args, **options):
        if settings.SETTINGS_MODULE != "config.settings.development":
            raise CommandError("seed_dev só pode executar com config.settings.development.")
        if options["check"]:
            self._validar_entradas(options["catalogo"])
            self.stdout.write(self.style.SUCCESS("Pré-requisitos do seed_dev válidos."))
            return

        # Mesmo lock da importação, inclusive durante o bootstrap organizacional:
        # duas invocações não disputam matrículas e importações não intercalam as revisões.
        # INV-STOCK-004: conta, papel, setor, catálogo e histórico revertem juntos.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [CHAVE_LOCK_IMPORTACAO_SCPI])
            if ExecucaoImportacao.objects.filter(token_previa__in=SEED_TOKENS).count() == 3:
                self.stdout.write(self.style.SUCCESS("seed_dev já aplicado; nenhum dado alterado."))
                return
            if any(model.objects.exists() for model in (Setor, User, Material, ExecucaoImportacao)):
                raise CommandError(
                    "O banco já contém dados e não possui o seed_dev completo. "
                    "Use um banco vazio; make resetdb descarta o banco local."
                )
            senha, caminho, conteudo, revisao = self._validar_entradas(options["catalogo"])
            chefe = self._criar_organizacao(senha)
            # PERM-SCPI-IMPORT-EXECUTE: o ator é o chefe ativo provisionado acima.
            if (
                not chefe.is_active
                or chefe.is_superuser
                or not chefe.tem_papel(Papel.CHEFE_ALMOXARIFADO)
            ):
                raise CommandError("O ator do seed precisa ser chefe ativo do almoxarifado.")
            arquivos = (
                (caminho.name, conteudo),
                ("seed_dev_02_revisao_simulada.csv", revisao),
                ("seed_dev_03_restauracao_" + caminho.name, conteudo),
            )
            # Invocar seed_dev confirma explicitamente estes cenários locais.
            # Cada gravação segue prévia + confirmação, sem criar Material/histórico por ORM.
            for token, (nome, dados) in zip(SEED_TOKENS, arquivos, strict=True):
                plano = calcular_plano(dados)
                pedido = PedidoPrevia(
                    token=str(token), nome_arquivo=nome[:255], tamanho=len(dados),
                    sha256=plano.sha256_arquivo, conteudo=dados,
                )
                confirmar_importacao(pedido, plano.impressao_digital, chefe)

        self.stdout.write(self.style.SUCCESS(
            "seed_dev concluído: 8 setores, 32 usuários e 3 importações. "
            "Catálogo original preservado; históricos de revisão identificados como simulação."
        ))
        self.stdout.write(
            "Acesso: admin, chefe, funcionario ou requisitante; senha de SEED_DEV_PASSWORD."
        )

    def _validar_entradas(self, caminho):
        senha = os.environ.get("SEED_DEV_PASSWORD", "")
        if not senha.strip():
            raise CommandError("Defina SEED_DEV_PASSWORD no .env antes de executar seed_dev.")
        try:
            validate_password(senha)
        except ValidationError as exc:
            raise CommandError("SEED_DEV_PASSWORD inválida: " + " ".join(exc.messages)) from exc
        caminho = Path(caminho) if caminho else settings.BASE_DIR / CATALOGO_PADRAO
        try:
            with caminho.open("rb") as arquivo:
                conteudo = arquivo.read(LIMITE_TAMANHO_ARQUIVO + 1)
        except OSError as exc:
            raise CommandError(
                "Não foi possível ler o catálogo SCPI. Disponibilize o arquivo em "
                "docs/domain-legacy ou informe --catalogo CAMINHO."
            ) from exc
        if len(conteudo) > LIMITE_TAMANHO_ARQUIVO:
            raise CommandError("O catálogo SCPI excede o limite de 10 MB.")
        try:
            resultado = ler_registros(conteudo)
            if not resultado.aceitos:
                raise CommandError("O catálogo SCPI não contém materiais válidos para importar.")
            revisao = revisao_simulada(resultado.aceitos)
        except (ArquivoRecusado, ValueError) as exc:
            raise CommandError(f"Catálogo SCPI inválido: {exc}") from exc
        return senha, caminho, conteudo, revisao

    @staticmethod
    def _criar_organizacao(senha):
        # INV-ORG-001/002/003: setor nasce inativo, recebe chefe próprio e só então é ativado.
        setores = {chave: Setor.objects.create(nome=nome) for chave, nome, _ in SETORES}
        User.objects.create_superuser(matricula="admin", password=senha, setor=setores["almox"])
        usuarios = {}
        for matricula, setor, papeis, ativo in USUARIOS:
            usuario = User.objects.create_user(
                matricula=matricula, password=senha, setor=setores[setor], is_active=ativo,
            )
            for papel in papeis:
                PapelUsuario.objects.create(usuario=usuario, papel=papel)
            usuarios[matricula] = usuario
        for chave, _, ativo in SETORES:
            if ativo:
                setor = setores[chave]
                setor.ativo = True
                setor.save(update_fields=["ativo"])
        return usuarios["chefe"]
