"""Bootstrap explícito de desenvolvimento, atômico e repetível."""

import hashlib
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
from fornecedores import importacao as importacao_fornecedores
from fornecedores.leitura_fornecedores import ler_fornecedores
from fornecedores.models import Fornecedor

# Identificadores públicos de idempotência, não credenciais ou tokens de autenticação.
SEED_TOKENS = (
    UUID("f76e99e0-bfc4-497b-a566-816dc567c001"),
    UUID("f76e99e0-bfc4-497b-a566-816dc567c002"),
    UUID("f76e99e0-bfc4-497b-a566-816dc567c003"),
)
# Token próprio da importação (opcional) de fornecedores — distinto dos três acima
# (catálogo/organização), pelo mesmo motivo que `fornecedores.importacao` usa uma
# chave de advisory lock própria: são fluxos de domínio independentes.
SEED_TOKEN_FORNECEDORES = UUID("f76e99e0-bfc4-497b-a566-816dc567c004")
CATALOGO_PADRAO = Path("docs/CSVs/relacao-de-todos-produtos-importados-do-SCPI.csv")
# Diferente do catálogo: o cadastro de fornecedores é OPCIONAL no seed (feature 004,
# T033) — a ausência do arquivo (padrão ou informado via --fornecedores) emite um
# aviso e o seed segue sem falhar, em vez de recusar como o catálogo faz.
FORNECEDORES_PADRAO = Path("docs/CSVs/fornecedores.csv")


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
            help="CSV SCPI de origem; padrão: arquivo local em docs/CSVs.",
        )
        parser.add_argument(
            "--fornecedores", type=Path,
            help=(
                "CSV de fornecedores do SCPI; padrão: docs/CSVs/fornecedores.csv. "
                "Opcional: ausente (padrão ou caminho informado), a importação de "
                "fornecedores é pulada com um aviso, sem falhar."
            ),
        )

    def handle(self, *args, **options):
        if settings.SETTINGS_MODULE != "config.settings.development":
            raise CommandError("seed_dev só pode executar com config.settings.development.")
        if options["check"]:
            self._validar_entradas(options["catalogo"])
            self._ler_arquivo_fornecedores(options["fornecedores"])
            self.stdout.write(self.style.SUCCESS("Pré-requisitos do seed_dev válidos."))
            return

        # Mesmo lock da importação, inclusive durante o bootstrap organizacional:
        # duas invocações não disputam matrículas e importações não intercalam as revisões.
        # INV-STOCK-004: conta, papel, setor, catálogo, fornecedores (quando importados)
        # e histórico revertem juntos.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [CHAVE_LOCK_IMPORTACAO_SCPI])
            if ExecucaoImportacao.objects.filter(token_previa__in=SEED_TOKENS).count() == 3:
                self.stdout.write(self.style.SUCCESS("seed_dev já aplicado; nenhum dado alterado."))
                return
            if any(
                model.objects.exists()
                for model in (Setor, User, Material, ExecucaoImportacao, Fornecedor)
            ):
                raise CommandError(
                    "O banco já contém dados e não possui o seed_dev completo. "
                    "Use um banco vazio; make resetdb descarta o banco local."
                )
            senha, caminho, conteudo, revisao = self._validar_entradas(options["catalogo"])
            # Validado ANTES de criar qualquer coisa (mesmo padrão do catálogo): se o
            # arquivo existe mas é inválido, o comando falha cedo, sem gravar nada — a
            # ausência do arquivo, ao contrário, só é um aviso (ver
            # `_ler_arquivo_fornecedores`).
            dados_fornecedores = self._ler_arquivo_fornecedores(options["fornecedores"])
            chefe = self._criar_organizacao(senha)
            # PERM-SCPI-IMPORT-EXECUTE / PERM-SUPPLIER-IMPORT-EXECUTE: o ator de
            # ambas as importações é o mesmo chefe ativo provisionado acima.
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

            execucao_fornecedores = None
            if dados_fornecedores is not None:
                caminho_fornecedores, conteudo_fornecedores, leitura_fornecedores = (
                    dados_fornecedores
                )
                sha256_fornecedores = hashlib.sha256(conteudo_fornecedores).hexdigest()
                plano_fornecedores = importacao_fornecedores.calcular_plano(
                    leitura_fornecedores, sha256_fornecedores
                )
                pedido_fornecedores = importacao_fornecedores.PedidoPrevia(
                    token=str(SEED_TOKEN_FORNECEDORES),
                    nome_arquivo=caminho_fornecedores.name[:255],
                    tamanho=len(conteudo_fornecedores),
                    sha256=sha256_fornecedores,
                    leitura=leitura_fornecedores,
                )
                execucao_fornecedores = importacao_fornecedores.confirmar_importacao(
                    pedido_fornecedores, plano_fornecedores.impressao_digital, chefe
                )

        resumo_fornecedores = ""
        if execucao_fornecedores is not None:
            # Só totais — nunca nome, documento ou qualquer outro valor do arquivo
            # (INV-SUPPLIER-004): a saída do comando não é um canal de dados pessoais.
            resumo_fornecedores = (
                f" Fornecedores: {execucao_fornecedores.total_recebidos} recebido(s), "
                f"{execucao_fornecedores.total_inseridos} inserido(s), "
                f"{execucao_fornecedores.total_atualizados} atualizado(s), "
                f"{execucao_fornecedores.total_rejeitados} rejeitado(s)."
            )
        self.stdout.write(
            self.style.SUCCESS(
                "seed_dev concluído: 8 setores, 32 usuários e 3 importações. "
                "Catálogo original preservado; históricos de revisão identificados como simulação."
                + resumo_fornecedores
            )
        )
        self.stdout.write("Senha de todas as contas: SEED_DEV_PASSWORD. Principais matrículas:")
        self.stdout.write("  admin          - superusuário técnico (Django Admin, /admin/)")
        self.stdout.write("  chefe          - chefe do almoxarifado (/login/)")
        self.stdout.write("  funcionario    - funcionário do almoxarifado (/login/)")
        self.stdout.write("  requisitante   - requisitante do almoxarifado (/login/)")
        self.stdout.write(
            "Demais matrículas e papéis: contas/dev_seed/dados.py ou o Django Admin."
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
                "docs/CSVs ou informe --catalogo CAMINHO."
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

    def _ler_arquivo_fornecedores(self, caminho):
        """Lê e valida o CSV de fornecedores (opcional, diferente do catálogo):
        devolve `(caminho, conteudo, leitura)` quando o arquivo existe e é válido,
        ou `None` quando está ausente — só um aviso, nunca uma falha. Não acessa o
        banco: usado tanto por `--check` quanto pela execução real, antes de criar
        qualquer coisa."""
        caminho = Path(caminho) if caminho else settings.BASE_DIR / FORNECEDORES_PADRAO
        if not caminho.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"Arquivo de fornecedores não encontrado em {caminho}; a importação de "
                    "fornecedores é opcional e será pulada. Informe --fornecedores CAMINHO "
                    "para outro local."
                )
            )
            return None
        try:
            with caminho.open("rb") as arquivo:
                conteudo = arquivo.read(LIMITE_TAMANHO_ARQUIVO + 1)
        except OSError as exc:
            raise CommandError(
                f"Não foi possível ler o arquivo de fornecedores em {caminho}."
            ) from exc
        if len(conteudo) > LIMITE_TAMANHO_ARQUIVO:
            raise CommandError("O arquivo de fornecedores excede o limite de 10 MB.")
        try:
            leitura = ler_fornecedores(conteudo)
        except ArquivoRecusado as exc:
            raise CommandError(f"Arquivo de fornecedores inválido: {exc.mensagem}") from exc
        return caminho, conteudo, leitura

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
