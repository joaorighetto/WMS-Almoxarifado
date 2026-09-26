"""Views de importação de fornecedores (US1, T017).

`contracts/rotas-e-autorizacao.md` fixa as rotas e a tabela de "Efetivação".
`ExigePapelMixin` é reusado de `catalogo.views` (research R1) — anônimo é
redirecionado ao login, autenticado sem `papel_exigido` recebe 403, sem
exceção para superusuário técnico (`INV-AUTH-001`).

Upload em memória (research R4): `ImportacaoEnvioView` troca
`request.upload_handlers` em `setup()` — chamado por `View.as_view()` antes
de `dispatch()`, portanto antes de `ExigePapelMixin` (que não acessa
`request.POST`/`FILES`) e antes de qualquer leitura do corpo da requisição.
A view é `csrf_exempt` (necessário para trocar os upload handlers antes do
CSRF ler `request.POST`) com `csrf_protect` só no método que de fato
processa o POST — padrão documentado pelo Django ("Modifying upload handlers
on the fly", topics/http/file-uploads).
"""

import logging
import uuid

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.files.uploadhandler import MemoryFileUploadHandler
from django.core.paginator import Paginator
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.db.models.functions import Length
from django.shortcuts import redirect, render
from django.template.defaultfilters import pluralize
from django.utils.cache import patch_vary_headers
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.generic import DetailView, ListView, View

from catalogo.leitura_scpi import LIMITE_TAMANHO_ARQUIVO, ArquivoRecusado, normalizar_para_busca
from catalogo.ordenacao import ColunaOrdenacao, OrdenacaoMixin
from catalogo.views import ExigePapelMixin
from contas.models import Papel
from fornecedores import importacao
from fornecedores.forms import (
    MENSAGEM_ARQUIVO_TAMANHO_EXCEDIDO,
    ArquivoFornecedoresForm,
    ConsultaFornecedoresForm,
)
from fornecedores.models import (
    CampoFornecedor,
    ExecucaoImportacaoFornecedores,
    Fornecedor,
    MotivoRecusaFornecedor,
)

logger = logging.getLogger("fornecedores.importacao")

TAMANHO_PAGINA_EXCECOES = 50

TAMANHO_PAGINA_CONSULTA = 50

# Só os campos mínimos do arquivo (`INV-SUPPLIER-004`) — a consulta nunca
# mostra nada além deles.
CAMPOS_EXIBIDOS_CONSULTA = (
    "codif",
    "nome",
    "nome_fantasia",
    "documento",
    "tipo",
    "bloqueado",
    "motivo_bloqueio",
    "tipo_bloqueio",
)

# Rótulo legível para o valor de `bloqueado` na trilha de alterações
# (gravado como "S"/"B", research R5) — decisão de apresentação (Constitution
# V: a decisão fica na view), pedida explicitamente pelo coordenador para a
# seção de alterações da prévia e do detalhe.
_ROTULOS_BLOQUEADO = {"S": "Liberado", "B": "Bloqueado"}

# Margem sobre o limite de 10 MB do arquivo (research R4): o handler decide
# se aceita o upload pelo Content-Length do CORPO INTEIRO da requisição (que
# inclui cabeçalhos multipart, boundary e o token CSRF), não só pelo tamanho
# do arquivo em si — sem margem, um arquivo de exatamente 10 MB poderia ser
# empurrado para fora do limite do handler antes mesmo de chegar a
# `ArquivoFornecedoresForm.clean_arquivo`, que é quem decide com precisão
# (`arquivo.size`, sem o overhead do envelope) se o arquivo excede o limite
# (código `ARQUIVO_TAMANHO_EXCEDIDO`).
_MARGEM_ENVELOPE_MULTIPART = 64 * 1024
_LIMITE_HANDLER_UPLOAD_MEMORIA = LIMITE_TAMANHO_ARQUIVO + _MARGEM_ENVELOPE_MULTIPART


class _HandlerUploadEmMemoria(MemoryFileUploadHandler):
    """`MemoryFileUploadHandler` com limite próprio da feature, independente
    de `settings.FILE_UPLOAD_MAX_MEMORY_SIZE` (research R4): nunca aciona o
    handler de disco, mesmo que o padrão global do projeto permitisse (não é
    alterado).

    Um upload maior que o limite nunca é aceito por nenhum handler —
    `request.FILES` fica sem a chave `arquivo` — mas `tamanho_excedido` fica
    `True` neste handler para a view substituir o erro genérico de "campo
    obrigatório" do formulário pelo código `ARQUIVO_TAMANHO_EXCEDIDO`
    correto (`contracts/arquivo-fornecedores.md` §1). O conteúdo em si nunca
    é guardado quando isso acontece — só o sinalizador booleano.

    Diferente do `MemoryFileUploadHandler` de origem, não tenta
    `stream.seek()` para redescobrir o tamanho real do corpo: esse recurso
    existe lá para servidores ASGI, em que o `Content-Length` pode faltar ou
    estar subestimado (`Transfer-Encoding: chunked`). Este projeto roda só
    em WSGI (`config/wsgi.py`, sem `asgi.py`) — chamar `seek()` num
    `wsgi.input` real (tipicamente não seekable) seria só código morto,
    nunca exercitado em produção.

    `content_length` (parâmetro desta função) nunca chega como `None` na
    prática: `MultiPartParser` sempre converte um `Content-Length` ausente
    ou não numérico em `0` antes de chamar este método (nunca `None`) — a
    checagem `content_length is not None` abaixo é só defensiva, para o caso
    de um chamador direto não seguir esse contrato. A proteção real contra
    um cliente que mentisse um `Content-Length` pequeno e enviasse um corpo
    maior não é feita aqui: é o `LimitedStream` do próprio servidor WSGI que
    trunca a leitura do corpo em `Content-Length` bytes, antes mesmo deste
    handler ver os dados.
    """

    tamanho_excedido = False

    def __init__(self, request=None, *, limite):
        super().__init__(request)
        self._limite = limite

    def handle_raw_input(self, input_data, META, content_length, boundary, encoding=None):
        self.activated = content_length is not None and content_length <= self._limite
        self.tamanho_excedido = not self.activated


def _valor_legivel(campo: str, valor: str) -> str:
    """Valor de exibição de uma alteração: `bloqueado` grava `"S"`/`"B"` na
    trilha (research R5) — aqui vira um rótulo legível; os demais campos são
    exibidos como gravados."""
    if campo == CampoFornecedor.BLOQUEADO:
        return _ROTULOS_BLOQUEADO.get(valor, valor)
    return valor


def _linha_alteracao(
    *, codif: str, nome: str, campo: str, valor_anterior: str, valor_novo: str
) -> dict:
    """Uma linha da seção de alterações (prévia e detalhe) — dict, não
    model/dataclass, para os dois contextos (plano em memória e
    `AlteracaoFornecedor` persistida) alimentarem o mesmo template com a
    mesma forma (mesmo padrão de `recusas_para_exibicao`, abaixo)."""
    return {
        "codif": codif,
        "nome": nome,
        "campo": campo,
        "campo_label": CampoFornecedor(campo).label,
        "valor_anterior": valor_anterior,
        "valor_anterior_legivel": _valor_legivel(campo, valor_anterior),
        "valor_novo": valor_novo,
        "valor_novo_legivel": _valor_legivel(campo, valor_novo),
    }


def _totais_bloqueio_do_plano(plano: importacao.PlanoImportacao) -> dict:
    """Situação de bloqueio em destaque na prévia (P1 do gate visual): três
    totais, calculados só em memória a partir do plano (nada persistido):
    - `total_passam_a_bloqueado`/`total_voltam_a_liberado`: contam, entre
      `plano.atualizacoes`, as mudanças do campo `bloqueado`
      (`valor_novo` "B"/"S" — `research.md` R5);
    - `total_chegam_bloqueados`: inserções (`plano.insercoes`) com
      `bloqueado=True`. Só é possível na prévia porque `FornecedorLido.
      bloqueado` reflete o arquivo sendo confirmado agora — o detalhe de uma
      execução já confirmada NÃO tem esse total (ver `ExecucaoDetalheView`),
      porque o `Fornecedor.bloqueado` atual pode já ter mudado numa
      reimportação posterior, e não há campo que preserve o valor da
      inserção original."""
    passam_a_bloqueado = 0
    voltam_a_liberado = 0
    for atualizacao in plano.atualizacoes:
        for campo, _valor_anterior, valor_novo in atualizacao.alteracoes:
            if campo != CampoFornecedor.BLOQUEADO:
                continue
            if valor_novo == "B":
                passam_a_bloqueado += 1
            elif valor_novo == "S":
                voltam_a_liberado += 1
    return {
        "total_passam_a_bloqueado": passam_a_bloqueado,
        "total_voltam_a_liberado": voltam_a_liberado,
        "total_chegam_bloqueados": sum(1 for lido in plano.insercoes if lido.bloqueado),
    }


def _contexto_previa(pedido: importacao.PedidoPrevia, request) -> dict:
    """Contexto comum à prévia (GET) e ao re-render da prévia depois de uma
    falha inesperada na confirmação — sempre recalculado só com leituras."""
    plano = importacao.calcular_plano(pedido.leitura, pedido.sha256)
    recusas_para_exibicao = [
        {
            "linha": recusa.linha,
            "codif": recusa.codif,
            "motivo": recusa.motivo,
            "motivo_label": MotivoRecusaFornecedor(recusa.motivo).label,
            "detalhe": recusa.detalhe,
        }
        for recusa in plano.recusas
    ]
    paginador_excecoes = Paginator(recusas_para_exibicao, TAMANHO_PAGINA_EXCECOES)
    excecoes_pagina = paginador_excecoes.get_page(request.GET.get("pagina_excecoes"))

    # Seção de alterações (US4, T029): achatada de `plano.atualizacoes` —
    # só as atualizações que de fato mudam algo (`atualizacao.alteracoes`
    # não vazio), uma linha por campo alterado. Nada disso é gravado: o
    # plano é só leituras (`calcular_plano`).
    linhas_alteracoes = [
        _linha_alteracao(
            codif=atualizacao.codif,
            nome=atualizacao.lido.nome,
            campo=campo,
            valor_anterior=valor_anterior,
            valor_novo=valor_novo,
        )
        for atualizacao in plano.atualizacoes
        for campo, valor_anterior, valor_novo in atualizacao.alteracoes
    ]
    # Situação de bloqueio em destaque (P1 do gate visual): as linhas do
    # campo `bloqueado` vêm primeiro, o resto mantém a ordem atual (por
    # codif) — `sort` é estável, então só reordena os grupos entre si.
    linhas_alteracoes.sort(key=lambda linha: linha["campo"] != CampoFornecedor.BLOQUEADO)
    paginador_alteracoes = Paginator(linhas_alteracoes, TAMANHO_PAGINA_EXCECOES)
    alteracoes_pagina = paginador_alteracoes.get_page(request.GET.get("pagina_alteracoes"))

    return {
        "pedido": pedido,
        "plano": plano,
        "excecoes_pagina": excecoes_pagina,
        "alteracoes_pagina": alteracoes_pagina,
        "token": pedido.token,
        "impressao_digital": plano.impressao_digital,
        **_totais_bloqueio_do_plano(plano),
    }


@method_decorator(csrf_exempt, name="dispatch")
class ImportacaoEnvioView(ExigePapelMixin, View):
    """Envio do arquivo de importação de fornecedores (US1; GET exibe o
    formulário, POST recebe o arquivo — PRG para a prévia).

    Contexto do template `fornecedores/importacao_envio.html`:
    - `form`: `ArquivoFornecedoresForm` (vazio no GET; com erros no POST
      inválido — recusa de tamanho ou de estrutura do arquivo);
    - `pedido_pendente`: `fornecedores.importacao.PedidoPrevia | None` — se
      houver uma prévia pendente na sessão, o template mostra um aviso com
      link para ela.
    """

    papel_exigido = Papel.CHEFE_ALMOXARIFADO
    template_name = "fornecedores/importacao_envio.html"

    def setup(self, request, *args, **kwargs):
        self._handler_upload = _HandlerUploadEmMemoria(
            request, limite=_LIMITE_HANDLER_UPLOAD_MEMORIA
        )
        request.upload_handlers = [self._handler_upload]
        super().setup(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return self._renderizar(request, ArquivoFornecedoresForm())

    @method_decorator(csrf_protect)
    def post(self, request, *args, **kwargs):
        form = ArquivoFornecedoresForm(request.POST, request.FILES)
        if not form.is_valid():
            if self._handler_upload.tamanho_excedido:
                # O upload handler já descartou o corpo por tamanho, antes
                # de `arquivo` chegar a `request.FILES` — sem isso, o
                # `FileField` obrigatório reportaria "campo obrigatório",
                # uma mensagem enganosa para um arquivo que na verdade só
                # excedeu o limite (`contracts/arquivo-fornecedores.md` §1).
                form.errors.pop("arquivo", None)
                form.add_error(
                    "arquivo",
                    ValidationError(
                        MENSAGEM_ARQUIVO_TAMANHO_EXCEDIDO, code="ARQUIVO_TAMANHO_EXCEDIDO"
                    ),
                )
            # Recusa de tamanho: re-renderiza com erro. Nada é gravado em
            # sessão nem em banco.
            return self._renderizar(request, form)

        arquivo = form.cleaned_data["arquivo"]
        try:
            importacao.guardar_pedido(
                request.session,
                nome_arquivo=arquivo.name,
                conteudo=form.conteudo_arquivo,
            )
        except ArquivoRecusado as exc:
            # Recusa de estrutura (`contracts/arquivo-fornecedores.md` §1):
            # re-renderiza com erro, sem tocar a sessão (`guardar_pedido` só
            # escreve a sessão depois de ler o arquivo com sucesso).
            form.add_error("arquivo", ValidationError(exc.mensagem, code=exc.codigo))
            return self._renderizar(request, form)

        return redirect("fornecedores:importacao_previa")

    def _renderizar(self, request, form):
        contexto = {
            "form": form,
            "pedido_pendente": importacao.obter_pedido(request.session),
        }
        return render(request, self.template_name, contexto)


class ImportacaoPreviaView(ExigePapelMixin, View):
    """Prévia da importação (GET), recalculada só com leituras — nenhuma
    escrita de domínio antes da confirmação.

    Contexto do template `fornecedores/importacao_previa.html`:
    - `pedido`: `fornecedores.importacao.PedidoPrevia`;
    - `plano`: `fornecedores.importacao.PlanoImportacao` recalculado;
    - `excecoes_pagina`: página (`Paginator`, 50/página) das recusas do
      plano, parametrizada por `?pagina_excecoes=`;
    - `alteracoes_pagina`: página (`Paginator`, 50/página, US4, T029) das
      alterações que a confirmação gravaria — achatada de
      `plano.atualizacoes`, uma linha por campo alterado (dict com `codif`,
      `nome`, `campo`, `campo_label`, `valor_anterior(_legivel)`,
      `valor_novo(_legivel)`), parametrizada por `?pagina_alteracoes=`; as
      linhas do campo `bloqueado` vêm primeiro (P1 do gate visual), o resto
      mantém a ordem por codif;
    - `total_passam_a_bloqueado`/`total_voltam_a_liberado`/
      `total_chegam_bloqueados`: situação de bloqueio em destaque (P1 do
      gate visual, `_totais_bloqueio_do_plano`) — quantos fornecedores
      existentes vão de liberado para bloqueado, de bloqueado para liberado,
      e quantos fornecedores novos já chegam bloqueados;
    - `token`/`impressao_digital`: valores a devolver no POST de
      confirmação (campos ocultos do formulário).
    """

    papel_exigido = Papel.CHEFE_ALMOXARIFADO
    template_name = "fornecedores/importacao_previa.html"

    def get(self, request, *args, **kwargs):
        pedido = importacao.obter_pedido(request.session)
        if pedido is None:
            messages.info(request, "Não há prévia pendente. Envie um arquivo para começar.")
            return redirect("fornecedores:importacao_envio")

        contexto = _contexto_previa(pedido, request)
        return render(request, self.template_name, contexto)


class ImportacaoConfirmarView(ExigePapelMixin, View):
    """Confirmação da importação (POST), conforme
    `contracts/rotas-e-autorizacao.md` → "Efetivação"."""

    papel_exigido = Papel.CHEFE_ALMOXARIFADO

    def post(self, request, *args, **kwargs):
        token = request.POST.get("token", "")
        impressao_digital = request.POST.get("impressao_digital", "")

        execucao_existente = None
        if _token_valido(token):
            execucao_existente = ExecucaoImportacaoFornecedores.objects.filter(
                token_previa=token
            ).first()
        if execucao_existente is not None:
            messages.warning(request, "Esta prévia já foi confirmada.")
            return redirect("fornecedores:execucao_detalhe", pk=execucao_existente.pk)

        pedido = importacao.obter_pedido(request.session)
        if pedido is None or pedido.token != token:
            messages.warning(request, "Prévia não encontrada. Envie o arquivo novamente.")
            return redirect("fornecedores:importacao_envio")

        try:
            execucao = importacao.confirmar_importacao(pedido, impressao_digital, request.user)
        except importacao.PreviaJaConfirmada as exc:
            messages.warning(request, "Esta prévia já foi confirmada.")
            return redirect("fornecedores:execucao_detalhe", pk=exc.execucao.pk)
        except importacao.PreviaDesatualizada:
            messages.warning(request, "A prévia ficou desatualizada; revise antes de confirmar.")
            return redirect("fornecedores:importacao_previa")
        except Exception:
            # Constitution VI: mensagem genérica ao usuário, nunca o texto
            # da exceção; o traceback vai para o log. O pedido de prévia
            # permanece na sessão para nova tentativa.
            logger.exception(
                "Falha inesperada ao confirmar a importação de fornecedores (token=%s).",
                token,
            )
            messages.error(
                request,
                "Não foi possível concluir a confirmação por um erro inesperado. Tente novamente.",
            )
            contexto = _contexto_previa(pedido, request)
            return render(request, ImportacaoPreviaView.template_name, contexto, status=200)

        importacao.descartar_pedido(request.session)
        messages.success(
            request,
            f"Importação concluída: {execucao.total_inseridos} "
            f"inserido{pluralize(execucao.total_inseridos)}, "
            f"{execucao.total_atualizados} "
            f"atualizado{pluralize(execucao.total_atualizados)}, "
            f"{execucao.total_rejeitados} "
            f"rejeitado{pluralize(execucao.total_rejeitados)}.",
        )
        return redirect("fornecedores:execucao_detalhe", pk=execucao.pk)


class ImportacaoCancelarView(ExigePapelMixin, View):
    """Cancelamento da prévia pendente (POST): remove o pedido da sessão,
    sem nenhum efeito em banco."""

    papel_exigido = Papel.CHEFE_ALMOXARIFADO

    def post(self, request, *args, **kwargs):
        importacao.descartar_pedido(request.session)
        return redirect("fornecedores:importacao_envio")


class ExecucaoDetalheView(ExigePapelMixin, DetailView):
    """Resultado de uma execução confirmada (US1/US3/US4).

    Contexto adicional do template `fornecedores/execucao_detalhe.html`,
    além de `execucao` (`ExecucaoImportacaoFornecedores`, via `DetailView`):
    - `excecoes_pagina`: página (`Paginator`, 50/página) das exceções da
      execução, parametrizada por `?pagina_excecoes=`;
    - `alteracoes_pagina`: página (`Paginator`, 50/página, US4, T026) das
      `AlteracaoFornecedor` da execução, uma linha por campo alterado (dict
      com `codif`, `nome`, `campo`, `campo_label`,
      `valor_anterior(_legivel)`, `valor_novo(_legivel)` — mesma forma da
      prévia, `_linha_alteracao`), parametrizada por `?pagina_alteracoes=`.
      A queryset usa `select_related("fornecedor")`: sem isso, exibir
      `codif`/`nome` de cada alteração custaria uma query por linha (N+1).
      `nome` é o nome ATUAL do fornecedor (`alteracao.fornecedor.nome`), não
      o nome vigente na época desta execução — uma execução posterior pode
      ter alterado o nome de novo. O template rotula essa coluna "Nome
      atual" (revisão do code-reviewer, P3); `codif` continua a
      identificação estável da linha. As linhas do campo `bloqueado` vêm
      primeiro (P1 do gate visual), o resto mantém `fornecedor__codif`,
      `campo`;
    - `total_passam_a_bloqueado`/`total_voltam_a_liberado`: situação de
      bloqueio em destaque (P1 do gate visual) — contagem, numa única query
      agregada, das `AlteracaoFornecedor` desta execução com
      `campo="bloqueado"` e `valor_novo` "B"/"S". **Sem**
      `total_chegam_bloqueados` aqui (diferente da prévia,
      `_totais_bloqueio_do_plano`): não há como saber, com fidelidade
      histórica e sem campo novo no model, se um fornecedor INSERIDO nesta
      execução chegou bloqueado — `Fornecedor.bloqueado` é o estado ATUAL,
      que uma reimportação posterior pode já ter mudado; usar esse valor
      aqui produziria um total historicamente errado para execuções antigas
      (mesmo problema do "Nome atual", mas sem correção possível sem mudar o
      modelo — reportado ao coordenador).
    """

    papel_exigido = Papel.CHEFE_ALMOXARIFADO
    template_name = "fornecedores/execucao_detalhe.html"
    context_object_name = "execucao"

    def get_queryset(self):
        return ExecucaoImportacaoFornecedores.objects.select_related("executada_por")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        excecoes = self.object.excecoes.all()
        paginador = Paginator(excecoes, TAMANHO_PAGINA_EXCECOES)
        contexto["excecoes_pagina"] = paginador.get_page(self.request.GET.get("pagina_excecoes"))

        agregados_bloqueio = self.object.alteracoes.filter(
            campo=CampoFornecedor.BLOQUEADO
        ).aggregate(
            total_passam_a_bloqueado=Count("pk", filter=Q(valor_novo="B")),
            total_voltam_a_liberado=Count("pk", filter=Q(valor_novo="S")),
        )
        contexto["total_passam_a_bloqueado"] = agregados_bloqueio["total_passam_a_bloqueado"]
        contexto["total_voltam_a_liberado"] = agregados_bloqueio["total_voltam_a_liberado"]

        alteracoes = (
            self.object.alteracoes.select_related("fornecedor")
            .annotate(
                _bloqueado_primeiro=Case(
                    When(campo=CampoFornecedor.BLOQUEADO, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            )
            .order_by("_bloqueado_primeiro", "fornecedor__codif", "campo")
        )
        paginador_alteracoes = Paginator(alteracoes, TAMANHO_PAGINA_EXCECOES)
        pagina_alteracoes = paginador_alteracoes.get_page(
            self.request.GET.get("pagina_alteracoes")
        )
        pagina_alteracoes.object_list = [
            _linha_alteracao(
                codif=alteracao.fornecedor.codif,
                nome=alteracao.fornecedor.nome,
                campo=alteracao.campo,
                valor_anterior=alteracao.valor_anterior,
                valor_novo=alteracao.valor_novo,
            )
            for alteracao in pagina_alteracoes.object_list
        ]
        contexto["alteracoes_pagina"] = pagina_alteracoes
        return contexto


class ConsultaFornecedoresView(OrdenacaoMixin, ExigePapelMixin, View):
    """Consulta do cadastro de fornecedores (US2, FR-027–FR-029,
    `contracts/rotas-e-autorizacao.md` → "Consulta"), no molde de
    `catalogo.views.ConsultaCatalogoView` (research R6).

    Contrato de contexto (`fornecedores/consulta.html`, partial
    `resultados_consulta`):
    - `form`: `ConsultaFornecedoresForm` ligado a `request.GET`;
    - `codigo_invalido`/`documento_invalido`: `bool` — quando `True`,
      **nenhuma** query é feita em `Fornecedor` e `pagina` é `None`;
    - `pagina`: `Page` de `Fornecedor` (50/página) ou `None`;
    - `ordem`/`ordenacao_rotulos`: mesma convenção de `OrdenacaoMixin`
      (`catalogo/ordenacao.py`), sempre presentes.

    `codigo` filtra por `codif=` exato — nunca completa zeros
    (`INV-SUPPLIER-001`). `nome` é normalizado (`normalizar_para_busca`) e
    separado em palavras; cada palavra vira um `nome_busca__contains`,
    combinadas por E. `documento` (já só dígitos, `ConsultaFornecedoresForm.
    clean_documento`) filtra por `documento_digitos=` exato — busca sempre
    exata, nunca parcial (decisão do dono do produto). Os três filtros se
    combinam por interseção. Só os campos mínimos são exibidos/`only()`-ados
    (`CAMPOS_EXIBIDOS_CONSULTA`, `INV-SUPPLIER-004`). Nenhuma ação de
    escrita nesta tela (SC-008).

    Ordenação por código (decisão do dono do produto, revisão do gate
    visual): por (comprimento do CODIF, CODIF), nunca pelo texto do CODIF
    sozinho — comparação textual colocaria "100" antes de "49" — e nunca
    convertendo CODIF para número (`INV-SUPPLIER-001`: `codif` é texto
    opaco, sem aritmética). `codif_len` (anotado em `get`, `Length("codif")`)
    é o campo real ordenável; `resolver_ordenacao` (`_expandir_codif`,
    abaixo) expande toda ocorrência de `codif`/`-codif` resolvida por
    `OrdenacaoMixin` — tanto a coluna "código" quanto o desempate de
    qualquer outra coluna — para o par `(codif_len, codif)`/`(-codif_len,
    -codif)`, sem alterar `catalogo/ordenacao.py` (que só lida com nomes de
    campo simples — string —, não expressões de queryset; um campo anotado
    contorna essa limitação sem precisar de suporte a expressões ali).
    """

    papel_exigido = Papel.FUNCIONARIO_ALMOXARIFADO
    template_name = "fornecedores/consulta.html"
    fragmento_partial_name = "resultados_consulta"

    colunas_ordenacao = {
        "codigo": ColunaOrdenacao(("codif",), "código"),
        "nome": ColunaOrdenacao(("nome_busca",), "nome"),
        "documento": ColunaOrdenacao(("documento_digitos",), "documento"),
    }
    ordem_padrao = "nome"
    campo_desempate = "codif"

    def resolver_ordenacao(self, valor_bruto: str) -> tuple[str, tuple[str, ...]]:
        ordem_efetiva, campos_ordenacao = super().resolver_ordenacao(valor_bruto)
        campos_ordenacao = tuple(
            campo_expandido
            for campo in campos_ordenacao
            for campo_expandido in self._expandir_codif(campo)
        )
        return ordem_efetiva, campos_ordenacao

    @staticmethod
    def _expandir_codif(campo: str) -> tuple[str, ...]:
        """Substitui `codif`/`-codif` por `(codif_len, codif)`/`(-codif_len,
        -codif)` — comprimento antes do valor, nunca CODIF como número
        (`INV-SUPPLIER-001`). `codif_len` precisa estar anotado na queryset
        (`get`, abaixo) antes de `order_by` usar este nome."""
        if campo == "codif":
            return ("codif_len", "codif")
        if campo == "-codif":
            return ("-codif_len", "-codif")
        return (campo,)

    def get(self, request, *args, **kwargs):
        form = ConsultaFornecedoresForm(request.GET)
        form.is_valid()
        codigo_invalido = "codigo" in form.errors
        documento_invalido = "documento" in form.errors
        veio_de_htmx = bool(request.headers.get("HX-Request")) and not request.headers.get(
            "HX-History-Restore-Request"
        )

        ordem_efetiva, campos_ordenacao = self.resolver_ordenacao(
            request.GET.get("ordem", "")
        )

        pagina = None
        if not codigo_invalido and not documento_invalido:
            codigo = form.cleaned_data["codigo"]
            nome = form.cleaned_data.get("nome", "").strip()
            documento_digitos = form.cleaned_data["documento"]

            fornecedores = Fornecedor.objects.only(*CAMPOS_EXIBIDOS_CONSULTA).annotate(
                codif_len=Length("codif")
            )
            if codigo:
                fornecedores = fornecedores.filter(codif=codigo)
            for palavra in normalizar_para_busca(nome).split():
                fornecedores = fornecedores.filter(nome_busca__contains=palavra)
            if documento_digitos:
                fornecedores = fornecedores.filter(documento_digitos=documento_digitos)
            fornecedores = fornecedores.order_by(*campos_ordenacao)
            paginador = Paginator(fornecedores, TAMANHO_PAGINA_CONSULTA)
            pagina = paginador.get_page(request.GET.get("pagina"))

        contexto = {
            "form": form,
            "codigo_invalido": codigo_invalido,
            "documento_invalido": documento_invalido,
            "pagina": pagina,
            "veio_de_htmx": veio_de_htmx,
            "ordem": ordem_efetiva,
            "ordenacao_rotulos": self.ordenacao_rotulos,
        }
        template_name = (
            f"{self.template_name}#{self.fragmento_partial_name}"
            if veio_de_htmx
            else self.template_name
        )
        resposta = render(request, template_name, contexto)
        patch_vary_headers(resposta, ["HX-Request", "HX-History-Restore-Request"])
        return resposta


class HistoricoImportacoesView(OrdenacaoMixin, ExigePapelMixin, ListView):
    """Histórico de importações confirmadas de fornecedores (US3,
    `contracts/rotas-e-autorizacao.md` → "GET /fornecedores/importacoes/"),
    no molde de `catalogo.views.HistoricoImportacoesView` — sem
    divergências (fornecedores não tem esse conceito).

    Contexto do template `fornecedores/historico.html`, além de
    `execucoes` (`ExecucaoImportacaoFornecedores` da página atual, via
    `ListView`): paginação de 20/página, parametrizada por `?pagina=`.
    Ordenação por coluna via `OrdenacaoMixin`: `concluida` (padrão,
    decrescente), `executor`, `recebidos`, `rejeitados`; desempate `-pk`
    (execução mais recente primeiro, qualquer que seja a coluna escolhida).
    """

    papel_exigido = Papel.CHEFE_ALMOXARIFADO
    model = ExecucaoImportacaoFornecedores
    template_name = "fornecedores/historico.html"
    context_object_name = "execucoes"
    paginate_by = 20
    page_kwarg = "pagina"

    colunas_ordenacao = {
        "concluida": ColunaOrdenacao(("concluida_em",), "data de conclusão"),
        "executor": ColunaOrdenacao(("executada_por__matricula",), "executor"),
        "recebidos": ColunaOrdenacao(("total_recebidos",), "recebidos"),
        "rejeitados": ColunaOrdenacao(("total_rejeitados",), "rejeitados"),
    }
    ordem_padrao = "-concluida"
    campo_desempate = "-pk"

    def get_queryset(self):
        self.ordem_efetiva, campos_order_by = self.resolver_ordenacao(
            self.request.GET.get("ordem", "")
        )
        return ExecucaoImportacaoFornecedores.objects.select_related("executada_por").order_by(
            *campos_order_by
        )

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["ordem"] = self.ordem_efetiva
        contexto["ordenacao_rotulos"] = self.ordenacao_rotulos
        return contexto


def _token_valido(token: str) -> bool:
    """Evita levantar `ValidationError` ao filtrar
    `ExecucaoImportacaoFornecedores` por um `token_previa` (UUID) com
    formato inválido — token vazio ou mal formado nunca corresponde a uma
    execução existente (mesmo padrão de `catalogo.views._token_valido`)."""
    try:
        uuid.UUID(token)
    except (ValueError, AttributeError, TypeError):
        return False
    return True
