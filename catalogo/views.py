import logging
import uuid

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.views.generic import DetailView, ListView, View

from catalogo import importacao
from catalogo.forms import ArquivoImportacaoForm, ConsultaCatalogoForm
from catalogo.leitura_scpi import normalizar_para_busca
from catalogo.models import ExecucaoImportacao, Material, MotivoRecusa
from contas.models import Papel

logger = logging.getLogger("catalogo.importacao")


class ExigePapelMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Exige que o usuário autenticado possua um papel de negócio específico.

    Usa só os mixins nativos do Django (`research.md` R12): anônimo é
    redirecionado ao login (`LoginRequiredMixin`); autenticado sem o papel
    recebe 403 (`UserPassesTestMixin`). A checagem é por papel explícito via
    `User.tem_papel()` — sem herança entre papéis e sem exceção para
    superusuário. Aplica a base de autorização de `PERM-MATERIAL-VIEW`,
    `PERM-SCPI-IMPORT-EXECUTE` e `PERM-SCPI-IMPORT-HISTORY-VIEW`; cada view
    concreta define `papel_exigido`.
    """

    papel_exigido: str

    def test_func(self):
        return self.request.user.tem_papel(self.papel_exigido)


# ---------------------------------------------------------------------------
# Importação do catálogo (US1) — `contracts/rotas-e-autorizacao.md`
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Consulta do catálogo (US2) — `contracts/rotas-e-autorizacao.md` → "GET
# /catalogo/"
# ---------------------------------------------------------------------------

TAMANHO_PAGINA_CONSULTA = 50

CAMPOS_EXIBIDOS_CONSULTA = (
    "cadpro",
    "descricao",
    "unidade",
    "grupo",
    "subgrupo",
    "nome_grupo",
    "nome_subgrupo",
    "saldo",
    "detalhamento",
)


class ConsultaCatalogoView(ExigePapelMixin, View):
    """Consulta do catálogo de materiais (US2, FR-039–FR-043).

    Contrato de contexto (fixo, `catalogo/consulta.html` e
    `catalogo/_resultados_consulta.html`, T035):
    - `form`: `ConsultaCatalogoForm` ligado a `request.GET` (campos
      `codigo`, `descricao`);
    - `codigo_invalido`: `bool`, True quando `codigo` foi preenchido fora do
      formato `XXX.YYY.ZZZ`. Nesse caso **nenhuma** query é feita em
      `Material` e `pagina` é `None`;
    - `pagina`: `Page` de `Material` (50/página, `Paginator.get_page`) ou
      `None` quando `codigo_invalido`.

    Os links de paginação (`catalogo/_paginacao.html`, revisão T051) montam a
    querystring a partir de `request.GET` diretamente (tag `querystring_pagina`,
    `catalogo/templatetags/catalogo_extras.py`) — não precisam de um valor
    calculado à parte no contexto para preservar `codigo`/`descricao`.

    `codigo` filtra por `cadpro=` exato; `descricao` é normalizada
    (`normalizar_para_busca`) e separada em palavras, e cada palavra vira um
    `descricao_busca__contains` combinado por E — todas as palavras, em
    qualquer ordem, cada uma parcial (FR-040, emenda de 2026-09-21). Os dois
    campos combinados restringem por interseção (FR-039, FR-040). Sem filtro,
    devolve o catálogo inteiro ordenado por `cadpro` (`Meta.ordering` de
    `Material`). Com o cabeçalho `HX-Request`, a resposta é só o fragmento
    de resultados (research R16).
    """

    papel_exigido = Papel.REQUISITANTE
    template_name = "catalogo/consulta.html"
    fragmento_template_name = "catalogo/_resultados_consulta.html"

    def get(self, request, *args, **kwargs):
        form = ConsultaCatalogoForm(request.GET)
        form.is_valid()
        codigo_invalido = "codigo" in form.errors
        # Usado tanto para escolher o template (fragmento x página inteira)
        # quanto pelo próprio fragmento, que precisa saber se está numa
        # troca HTMX para decidir como comunicar erro de validação (ver
        # docstring de `catalogo/templates/catalogo/_resultados_consulta.html`,
        # revisão do gate visual, achado P2).
        veio_de_htmx = bool(request.headers.get("HX-Request"))

        pagina = None
        if not codigo_invalido:
            codigo = form.cleaned_data["codigo"]
            descricao = form.cleaned_data["descricao"].strip()

            materiais = Material.objects.only(*CAMPOS_EXIBIDOS_CONSULTA)
            if codigo:
                materiais = materiais.filter(cadpro=codigo)
            # FR-040 (emenda de 2026-09-21): busca por palavras soltas — todas
            # precisam estar na descrição, em qualquer ordem, cada uma parcial.
            for palavra in normalizar_para_busca(descricao).split():
                materiais = materiais.filter(descricao_busca__contains=palavra)
            paginador = Paginator(materiais, TAMANHO_PAGINA_CONSULTA)
            pagina = paginador.get_page(request.GET.get("pagina"))

        contexto = {
            "form": form,
            "codigo_invalido": codigo_invalido,
            "pagina": pagina,
            "veio_de_htmx": veio_de_htmx,
        }
        template_name = (
            self.fragmento_template_name if veio_de_htmx else self.template_name
        )
        resposta = render(request, template_name, contexto)
        if codigo_invalido and veio_de_htmx:
            # Revisão do gate visual (achado P2): um código fora do formato não
            # pode mais substituir a última tabela de resultados visível pelo
            # alerta de erro (o usuário perde o que estava vendo). `HX-Reswap:
            # none` instrui o htmx a não tocar em `#resultados-consulta` nesta
            # resposta — o campo é sinalizado à parte, via out-of-band swap,
            # dentro do próprio fragmento (ver docstring do template).
            resposta["HX-Reswap"] = "none"
        return resposta


TAMANHO_PAGINA_EXCECOES = 50


def _contexto_previa(pedido: importacao.PedidoPrevia, request) -> dict:
    """Contexto comum à prévia (GET) e ao re-render da prévia depois de uma
    falha inesperada na confirmação — sempre recalculado só com leituras.

    `excecoes_pagina` (T029, frontend-implementer) pagina uma lista de
    dicionários derivados de `plano.recusas`, não as `Recusa` originais:
    cada um acrescenta `motivo_label`, o rótulo em pt-BR de `MotivoRecusa`
    correspondente ao código `motivo`. `Recusa` é um dataclass de leitura
    (`catalogo.leitura_scpi`), sem `get_motivo_display()` como um campo de
    model — isto só resolve apresentação (o código `motivo` continua no
    dicionário); nenhuma regra de negócio é decidida aqui.

    `divergencias_pagina` (T046, US4, `pagina_divergencias` — fixo em
    `contracts/rotas-e-autorizacao.md`) pagina `plano.divergencias`
    diretamente (dataclasses `Atualizacao`/`Divergencia`, sem FK — já trazem
    `cadpro`, `saldo_wms`, `saldo_arquivo` e `diferenca` prontos).
    """
    plano = importacao.calcular_plano(pedido.conteudo)
    recusas_para_exibicao = [
        {
            "linha_inicial": recusa.linha_inicial,
            "linha_final": recusa.linha_final,
            "cadpro": recusa.cadpro,
            "motivo": recusa.motivo,
            "motivo_label": MotivoRecusa(recusa.motivo).label,
            "detalhe": recusa.detalhe,
        }
        for recusa in plano.recusas
    ]
    paginador_excecoes = Paginator(recusas_para_exibicao, TAMANHO_PAGINA_EXCECOES)
    excecoes_pagina = paginador_excecoes.get_page(request.GET.get("pagina_excecoes"))

    paginador_divergencias = Paginator(plano.divergencias, TAMANHO_PAGINA_EXCECOES)
    divergencias_pagina = paginador_divergencias.get_page(
        request.GET.get("pagina_divergencias")
    )

    return {
        "pedido": pedido,
        "plano": plano,
        "excecoes_pagina": excecoes_pagina,
        "divergencias_pagina": divergencias_pagina,
        "token": pedido.token,
        "impressao_digital": plano.impressao_digital,
    }


class ImportacaoEnvioView(ExigePapelMixin, View):
    """Envio do arquivo de importação do catálogo (US1; GET exibe o
    formulário, POST recebe o arquivo — PRG para a prévia).

    Contexto do template `catalogo/importacao_envio.html` (T029):
    - `form`: `ArquivoImportacaoForm` (vazio no GET; com erros no POST
      inválido — `contracts/arquivo-scpi.md` §1);
    - `pedido_pendente`: `catalogo.importacao.PedidoPrevia | None` — se
      houver uma prévia pendente na sessão, o template mostra um aviso com
      link para ela.
    """

    papel_exigido = Papel.CHEFE_ALMOXARIFADO
    template_name = "catalogo/importacao_envio.html"

    def get(self, request, *args, **kwargs):
        return self._renderizar(request, ArquivoImportacaoForm())

    def post(self, request, *args, **kwargs):
        form = ArquivoImportacaoForm(request.POST, request.FILES)
        if not form.is_valid():
            # Recusa de arquivo: re-renderiza com erro. Nada é gravado em
            # sessão nem em banco (`contracts/rotas-e-autorizacao.md`).
            return self._renderizar(request, form)

        arquivo = form.cleaned_data["arquivo"]
        importacao.guardar_pedido(
            request.session,
            nome_arquivo=arquivo.name,
            conteudo=form.conteudo_arquivo,
        )
        return redirect("catalogo:importacao_previa")

    def _renderizar(self, request, form):
        contexto = {
            "form": form,
            "pedido_pendente": importacao.obter_pedido(request.session),
        }
        return render(request, self.template_name, contexto)


class ImportacaoPreviaView(ExigePapelMixin, View):
    """Prévia da importação (GET), recalculada só com leituras — nenhuma
    escrita de domínio antes da confirmação (FR-044a).

    Contexto do template `catalogo/importacao_previa.html` (T029/T047):
    - `pedido`: `catalogo.importacao.PedidoPrevia`;
    - `plano`: `catalogo.importacao.PlanoImportacao` recalculado;
    - `excecoes_pagina`: página (`Paginator`, 50/página) das recusas do
      plano, parametrizada por `?pagina_excecoes=`;
    - `divergencias_pagina`: página (`Paginator`, 50/página) de
      `plano.divergencias`, parametrizada por `?pagina_divergencias=`
      (T046, US4);
    - `token`/`impressao_digital`: valores a devolver no POST de
      confirmação (campos ocultos do formulário).
    """

    papel_exigido = Papel.CHEFE_ALMOXARIFADO
    template_name = "catalogo/importacao_previa.html"

    def get(self, request, *args, **kwargs):
        pedido = importacao.obter_pedido(request.session)
        if pedido is None:
            messages.info(request, "Não há prévia pendente. Envie um arquivo para começar.")
            return redirect("catalogo:importacao_envio")

        contexto = _contexto_previa(pedido, request)
        return render(request, self.template_name, contexto)


class ImportacaoConfirmarView(ExigePapelMixin, View):
    """Confirmação da importação (POST), conforme a tabela de
    `contracts/rotas-e-autorizacao.md` → "Efetivação"."""

    papel_exigido = Papel.CHEFE_ALMOXARIFADO

    def post(self, request, *args, **kwargs):
        token = request.POST.get("token", "")
        impressao_digital = request.POST.get("impressao_digital", "")

        execucao_existente = None
        if _token_valido(token):
            execucao_existente = ExecucaoImportacao.objects.filter(
                token_previa=token
            ).first()
        if execucao_existente is not None:
            messages.warning(request, "Esta prévia já foi confirmada.")
            return redirect("catalogo:execucao_detalhe", pk=execucao_existente.pk)

        pedido = importacao.obter_pedido(request.session)
        if pedido is None or pedido.token != token:
            messages.warning(request, "Prévia não encontrada. Envie o arquivo novamente.")
            return redirect("catalogo:importacao_envio")

        try:
            execucao = importacao.confirmar_importacao(pedido, impressao_digital, request.user)
        except importacao.PreviaJaConfirmada as exc:
            messages.warning(request, "Esta prévia já foi confirmada.")
            return redirect("catalogo:execucao_detalhe", pk=exc.execucao.pk)
        except importacao.PreviaDesatualizada:
            messages.warning(
                request, "A prévia ficou desatualizada; revise antes de confirmar."
            )
            return redirect("catalogo:importacao_previa")
        except Exception:
            # Constitution VI: mensagem genérica ao usuário, nunca o texto
            # da exceção; o traceback vai para o log (`research.md` R13). O
            # pedido de prévia permanece na sessão para nova tentativa.
            logger.exception(
                "Falha inesperada ao confirmar a importação do catálogo (token=%s).", token
            )
            messages.error(
                request,
                "Não foi possível concluir a confirmação por um erro inesperado. "
                "Tente novamente.",
            )
            contexto = _contexto_previa(pedido, request)
            return render(
                request, ImportacaoPreviaView.template_name, contexto, status=200
            )

        importacao.descartar_pedido(request.session)
        # Revisão do gate visual (achado P1): a confirmação — irreversível —
        # terminava em silêncio, sem nenhuma mensagem de sucesso; o selo
        # "Concluída" no page header do detalhe (`execucao_detalhe.html`)
        # mantém o estado legível depois que esta mensagem some.
        messages.success(
            request,
            f"Importação concluída: {execucao.total_inseridos} inseridos, "
            f"{execucao.total_atualizados} atualizados, "
            f"{execucao.total_rejeitados} rejeitados.",
        )
        return redirect("catalogo:execucao_detalhe", pk=execucao.pk)


class ImportacaoCancelarView(ExigePapelMixin, View):
    """Cancelamento da prévia pendente (POST): remove o pedido da sessão,
    sem nenhum efeito em banco."""

    papel_exigido = Papel.CHEFE_ALMOXARIFADO

    def post(self, request, *args, **kwargs):
        importacao.descartar_pedido(request.session)
        return redirect("catalogo:importacao_envio")


class ExecucaoDetalheView(ExigePapelMixin, DetailView):
    """Resultado de uma execução confirmada (US1/US3/US4, FR-044).

    Contexto adicional do template `catalogo/execucao_detalhe.html`
    (T029/T047), além de `execucao` (`ExecucaoImportacao`, via `DetailView`):
    - `excecoes_pagina`: página (`Paginator`, 50/página) das exceções da
      execução, parametrizada por `?pagina_excecoes=`;
    - `divergencias_pagina`: página (`Paginator`, 50/página) das
      `DivergenciaSaldo` da execução (`select_related("material")`),
      parametrizada por `?pagina_divergencias=` (T046, US4, FR-030);
    - `alteracoes_pagina`: página (`Paginator`, 50/página) das
      `AlteracaoCadastralMaterial` da execução
      (`select_related("material")`, ordenadas por `cadpro` e depois por
      `campo` para uma ordem estável), parametrizada por
      `?pagina_alteracoes=` (T046, US4, FR-032; nome de parâmetro proposto
      por `tests/test_catalogo_views_importacao.py`, não fixado em
      `contracts/rotas-e-autorizacao.md`).
    """

    papel_exigido = Papel.CHEFE_ALMOXARIFADO
    template_name = "catalogo/execucao_detalhe.html"
    context_object_name = "execucao"

    def get_queryset(self):
        return ExecucaoImportacao.objects.select_related("executada_por")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        excecoes = self.object.excecoes.all()
        paginador = Paginator(excecoes, TAMANHO_PAGINA_EXCECOES)
        contexto["excecoes_pagina"] = paginador.get_page(
            self.request.GET.get("pagina_excecoes")
        )

        divergencias = self.object.divergencias.select_related("material")
        paginador_divergencias = Paginator(divergencias, TAMANHO_PAGINA_EXCECOES)
        contexto["divergencias_pagina"] = paginador_divergencias.get_page(
            self.request.GET.get("pagina_divergencias")
        )

        alteracoes = self.object.alteracoes.select_related("material").order_by(
            "material__cadpro", "campo"
        )
        paginador_alteracoes = Paginator(alteracoes, TAMANHO_PAGINA_EXCECOES)
        contexto["alteracoes_pagina"] = paginador_alteracoes.get_page(
            self.request.GET.get("pagina_alteracoes")
        )
        return contexto


class HistoricoImportacoesView(ExigePapelMixin, ListView):
    """Histórico de importações confirmadas do catálogo (US3, FR-033–FR-037).

    Aplica `PERM-SCPI-IMPORT-HISTORY-VIEW`; preserva `INV-AUTH-001` (anônimo
    → login; sem papel → 403; superusuário técnico sem papel → 403 — já
    garantido por `ExigePapelMixin`).

    Contexto do template `catalogo/historico.html` (T040), além de
    `execucoes` (lista de `ExecucaoImportacao` da página atual, via
    `ListView`): paginação de 20/página, parametrizada por `?pagina=`
    (`tests/test_catalogo_historico.py`, mesmo nome de parâmetro da consulta
    e do parcial `catalogo/_paginacao.html`).
    """

    papel_exigido = Papel.CHEFE_ALMOXARIFADO
    model = ExecucaoImportacao
    template_name = "catalogo/historico.html"
    context_object_name = "execucoes"
    paginate_by = 20
    page_kwarg = "pagina"

    def get_queryset(self):
        return ExecucaoImportacao.objects.select_related("executada_por").order_by(
            "-concluida_em", "-pk"
        )


def _token_valido(token: str) -> bool:
    """Evita levantar `ValidationError` ao filtrar `ExecucaoImportacao` por
    um `token_previa` (UUID) com formato inválido — token vazio ou mal
    formado nunca corresponde a uma execução existente."""
    try:
        uuid.UUID(token)
    except (ValueError, AttributeError, TypeError):
        return False
    return True
