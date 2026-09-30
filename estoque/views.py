"""Views de composição, confirmação, consulta, detalhe e estorno da entrada
(`contracts/rotas-e-autorizacao.md`, `contracts/composicao-entrada.md`,
research R9, R12).

Contrato de contexto por template (Constitution V: a decisão fica na view,
o template só apresenta os dados já prontos):

`estoque/entrada_nova.html` (duas seções: `#formulario` e `#resumo` — os
nomes de partial usados por `render(request, "estoque/entrada_nova.html#<nome>")`
quando `HX-Request`):
- `cabecalho_form` (`CabecalhoEntradaForm`), `item_formset`
  (`ItemEntradaFormSet`, prefixo `itens`);
- `linhas_itens`: lista de `{"posicao": int, "form": ItemEntradaForm,
  "material": Material | None}`, uma por linha do formset, na mesma ordem;
  `material` é sempre lido do banco pelo `pk` oculto do form (nunca do
  texto digitado);
- `emitente_escolhido`: `Fornecedor | None`, lido pelo `pk` guardado em
  `cabecalho_form` (campo oculto `emitente`);
- `resultados_material`: `None` (nenhuma busca) ou `{"itens": [{"material":
  Material, "ja_incluido": bool}], "total": int, "excedeu": bool}` — até 20
  itens, `excedeu` quando `total` passa disso (pedir para refinar);
- `resultados_emitente`: `None` ou `{"itens": [Fornecedor], "total": int,
  "excedeu": bool}` (até 20; bloqueado aparece no próprio objeto via
  `fornecedor.bloqueado`/`motivo_bloqueio`);
- `erros_gerais`: `list[str]` — mensagens sem campo/linha correspondente
  (ex.: "Inclua ao menos um material.", ou o "too_many_forms" de
  `item_formset.non_form_errors()` quando `TOTAL_FORMS` chega acima de
  `absolute_max`), exibidas como alerta;
- `entrada_existente`: `Entrada | None` — só presente quando o erro foi
  `ReferenciaJaUsada` (referência de outra entrada não estornada); o
  template usa `{% if entrada_existente %}` para o link ao detalhe dela;
- modo `resumo` (quando "Revisar" foi aceito): `itens_resumo` (lista de
  `{"material": Material, "quantidade": Decimal, "saldo_atual": Decimal,
  "saldo_resultante": Decimal}`), `motivo_label`, `tipo_documento_label`,
  `total_itens`; o próprio `cabecalho_form`/`item_formset` (renderizados
  como campos ocultos) carregam os dados a reenviar para
  `entrada_confirmar`.

`estoque/entrada_detalhe.html`:
- `entrada` (`Entrada`, com `emitente`/`registrada_por` já carregados);
- `itens`: queryset de `ItemEntrada` com `material` carregado;
- `estorno`: `EstornoEntrada | None`;
- `pode_estornar`: `bool` (chefe do almoxarifado e entrada não estornada).

`estoque/entradas.html`:
- `pagina`: `Page` de `Entrada` (50/página, `select_related`
  `registrada_por`/`emitente`, `annotate(total_itens=Count("itens"))`).

`estoque/entrada_estorno.html`:
- `entrada` (com `emitente`/`registrada_por` já carregados), `form`
  (`EstornoEntradaForm`);
- `linhas`: lista de `{"item": ItemEntrada, "saldo_atual": Decimal,
  "saldo_resultante": Decimal, "bloqueado": bool}` — `bloqueado` já indica,
  antes de qualquer POST, o item cujo saldo atual não comporta o estorno;
- `algum_bloqueado`: `bool`.

`EntradaEstornoView` nunca renderiza esse template para uma entrada já
estornada (GET ou POST): redireciona direto ao detalhe com o aviso "Esta
entrada já foi estornada." (achado do gate visual — reabrir o formulário de
uma ação que não pode mais ser repetida é confuso, além de desnecessário).
"""

import logging
import re
import uuid

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.views.generic import View

from catalogo.leitura_scpi import PADRAO_CADPRO, normalizar_para_busca
from catalogo.models import Material
from catalogo.views import ExigePapelMixin
from contas.models import Papel
from estoque.entradas import (
    EntradaInvalida,
    EntradaJaEstornada,
    EntradaJaRegistrada,
    EstornoBloqueadoPorSaldo,
    JustificativaAusente,
    ReferenciaJaUsada,
    entrada_corresponde_ao_conteudo,
    estornar_entrada,
    registrar_entrada,
    validar_entrada,
)
from estoque.forms import (
    CabecalhoEntradaForm,
    EstornoEntradaForm,
    ItemEntradaFormSet,
    aplicar_entrada_invalida,
    montar_entrada_informada,
)
from estoque.models import Entrada, MotivoEntrada, TipoDocumentoEntrada
from fornecedores.models import Fornecedor

logger = logging.getLogger("estoque.entradas")

LIMITE_RESULTADOS_BUSCA = 20

TAMANHO_PAGINA_ENTRADAS = 50

_CARACTERES_DOCUMENTO = set("0123456789./-")


def _buscar_materiais(texto: str):
    texto = texto.strip()
    if not texto:
        return Material.objects.none()
    if PADRAO_CADPRO.fullmatch(texto):
        return Material.objects.filter(cadpro=texto)
    materiais = Material.objects.all()
    for palavra in normalizar_para_busca(texto).split():
        materiais = materiais.filter(descricao_busca__contains=palavra)
    return materiais


def _buscar_emitentes(texto: str):
    texto = texto.strip()
    if not texto:
        return Fornecedor.objects.none()

    apenas_digitos = "".join(caractere for caractere in texto if caractere.isdigit())

    if texto.isdigit():
        return Fornecedor.objects.filter(Q(codif=texto) | Q(documento_digitos=texto))

    parece_documento = len(apenas_digitos) >= 3 and all(
        caractere in _CARACTERES_DOCUMENTO for caractere in texto
    )
    if parece_documento:
        return Fornecedor.objects.filter(documento_digitos=apenas_digitos)

    fornecedores = Fornecedor.objects.all()
    for palavra in normalizar_para_busca(texto).split():
        fornecedores = fornecedores.filter(nome_busca__contains=palavra)
    return fornecedores


def _para_int(valor) -> int | None:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _pk_informado(texto) -> int | None:
    """`pk` vindo de um botão do formulário: só dígitos ASCII. `str.isdigit()`
    aceita dígitos Unicode ("²") que o ORM recusaria com `ValueError` (500).
    No máximo 18 dígitos: cabe em `bigint` e fica longe do limite de dígitos
    do `int()` do Python."""
    if not isinstance(texto, str) or not re.fullmatch(r"[0-9]{1,18}", texto):
        return None
    return int(texto) or None


class _ComposicaoEntradaBase(ExigePapelMixin, View):
    """Base comum de `EntradaNovaView`/`EntradaConfirmarView`: as duas
    telas revalidam e re-renderizam o mesmo formulário de composição."""

    papel_exigido = Papel.FUNCIONARIO_ALMOXARIFADO
    template_name = "estoque/entrada_nova.html"

    def _linhas_itens(self, item_formset):
        ids = []
        for form in item_formset.forms:
            form.is_valid()
            material_id = form.cleaned_data.get("material")
            if material_id is not None:
                ids.append(material_id)
        materiais_por_id = {m.pk: m for m in Material.objects.filter(pk__in=ids)}
        linhas = []
        for posicao, form in enumerate(item_formset.forms):
            material_id = form.cleaned_data.get("material")
            material = materiais_por_id.get(material_id)
            # Apresentação (achado do gate visual, acessibilidade): o campo de
            # quantidade não tem um `<label>` próprio nesta linha (o rótulo de
            # coluna "Quantidade recebida" já está no `<th>`) — sem isto, um
            # leitor de tela anuncia só "Quantidade", igual em toda linha.
            if material is not None:
                form.fields["quantidade"].widget.attrs.setdefault(
                    "aria-label", f"Quantidade recebida de {material.cadpro}"
                )
            linhas.append(
                {
                    "posicao": posicao,
                    "form": form,
                    "material": material,
                }
            )
        return linhas

    def _resultados_material(self, texto, ids_ja_incluidos):
        texto = (texto or "").strip()
        if not texto:
            return None
        queryset = _buscar_materiais(texto).order_by("cadpro")
        total = queryset.count()
        itens = [
            {"material": material, "ja_incluido": material.pk in ids_ja_incluidos}
            for material in queryset[:LIMITE_RESULTADOS_BUSCA]
        ]
        return {"itens": itens, "total": total, "excedeu": total > LIMITE_RESULTADOS_BUSCA}

    def _resultados_emitente(self, texto):
        texto = (texto or "").strip()
        if not texto:
            return None
        queryset = _buscar_emitentes(texto).order_by("nome")
        total = queryset.count()
        itens = list(queryset[:LIMITE_RESULTADOS_BUSCA])
        return {"itens": itens, "total": total, "excedeu": total > LIMITE_RESULTADOS_BUSCA}

    def _renderizar(self, request, contexto, fragmento):
        veio_de_htmx = bool(request.headers.get("HX-Request")) and not request.headers.get(
            "HX-History-Restore-Request"
        )
        contexto["veio_de_htmx"] = veio_de_htmx
        template_name = (
            f"{self.template_name}#{fragmento}" if veio_de_htmx else self.template_name
        )
        resposta = render(request, template_name, contexto)
        patch_vary_headers(resposta, ["HX-Request", "HX-History-Restore-Request"])
        return resposta

    def _renderizar_formulario(
        self,
        request,
        cabecalho_form,
        item_formset,
        erros_gerais=None,
        foco_posicao=None,
        entrada_existente=None,
    ):
        # `is_valid()` num form NÃO vinculado (GET inicial, só `initial=`)
        # retorna `False` sem popular `cleaned_data` — por isso os valores
        # são lidos com uma queda para `{}` quando o form não está vinculado
        # a dados de POST.
        if cabecalho_form.is_bound:
            cabecalho_form.is_valid()
            dados_cabecalho = cabecalho_form.cleaned_data
        else:
            dados_cabecalho = {}

        linhas_itens = self._linhas_itens(item_formset)
        ids_ja_incluidos = {
            linha["material"].pk for linha in linhas_itens if linha["material"] is not None
        }

        # Apresentação (T018): depois de "Adicionar", o foco vai para a
        # quantidade da nova linha (`contracts/composicao-entrada.md`). Só
        # marca o atributo HTML nativo `autofocus` no widget da linha
        # recém-criada — funciona sem JS numa renderização de página
        # inteira; `estoque/static/estoque/js/estoque.js` reforça o mesmo
        # foco depois de uma troca HTMX (`htmx:afterSettle`), que nem
        # sempre reaciona `autofocus` num nó inserido via `innerHTML`.
        if foco_posicao is not None:
            for linha in linhas_itens:
                if linha["posicao"] == foco_posicao:
                    linha["form"].fields["quantidade"].widget.attrs["autofocus"] = True
                    break

        emitente_id = dados_cabecalho.get("emitente")
        emitente_escolhido = (
            Fornecedor.objects.filter(pk=emitente_id).first() if emitente_id else None
        )

        contexto = {
            "cabecalho_form": cabecalho_form,
            "item_formset": item_formset,
            "linhas_itens": linhas_itens,
            "emitente_escolhido": emitente_escolhido,
            "resultados_material": self._resultados_material(
                dados_cabecalho.get("busca_material"), ids_ja_incluidos
            ),
            "resultados_emitente": self._resultados_emitente(
                dados_cabecalho.get("busca_emitente")
            ),
            "erros_gerais": erros_gerais or [],
            "entrada_existente": entrada_existente,
            "modo": "formulario",
        }
        return self._renderizar(request, contexto, "formulario")

    def _renderizar_entrada_invalida(self, request, exc, cabecalho_form, item_formset):
        """Re-render comum a `EntradaInvalida` (e subclasses) tanto na
        composição ("Revisar") quanto na confirmação: erros de campo/linha
        (`aplicar_entrada_invalida`), o emitente indisponível limpo do campo
        oculto e a entrada existente no contexto quando a referência já foi
        usada (`ReferenciaJaUsada`, para o link ao detalhe dela).

        A limpeza do emitente olha `exc.erros_campo` (não só
        `isinstance(exc, EmitenteIndisponivel)`, resíduo do review): os
        erros básicos de cabeçalho (`tem_erro_basico`) têm prioridade em
        `validar_entrada` e podem chegar aqui como `EntradaInvalida`
        genérica mesmo com um emitente bloqueado/inexistente junto — o
        usuário não pode confirmar aquela escolha de qualquer forma."""
        if "emitente" in exc.erros_campo:
            dados_sem_emitente = cabecalho_form.data.copy()
            dados_sem_emitente["emitente"] = ""
            cabecalho_form = CabecalhoEntradaForm(dados_sem_emitente)

        erros_gerais = aplicar_entrada_invalida(exc, cabecalho_form, item_formset)
        entrada_existente = exc.entrada if isinstance(exc, ReferenciaJaUsada) else None
        return self._renderizar_formulario(
            request,
            cabecalho_form,
            item_formset,
            erros_gerais=erros_gerais,
            entrada_existente=entrada_existente,
        )

    def _tratar_entrada_ja_registrada(self, request, exc, dados_informados):
        """Reenvio da mesma `chave_confirmacao` (research R4): idempotente
        se o conteúdo bate com o já registrado, aviso de formulário
        reaproveitado caso contrário (item 6 da 1ª rodada do review) — usada
        tanto por `EntradaConfirmarView` quanto por `EntradaNovaView._revisar`
        (item 1 da 2ª rodada: `validar_entrada` também pode levantar
        `EntradaJaRegistrada` ao reenviar a mesma chave/referência a partir
        de "Revisar")."""
        if entrada_corresponde_ao_conteudo(exc.entrada, dados_informados):
            messages.warning(request, "Esta entrada já foi registrada.")
        else:
            messages.warning(
                request,
                "Este formulário já foi usado para registrar a entrada "
                f"#{exc.entrada.pk}; inicie uma nova entrada.",
            )
        destino = reverse("estoque:entrada_detalhe", args=[exc.entrada.pk])
        veio_de_htmx = bool(request.headers.get("HX-Request")) and not request.headers.get(
            "HX-History-Restore-Request"
        )
        if veio_de_htmx:
            # "Revisar" é POST HTMX com alvo `#entrada-composicao`: um 302 seria
            # seguido pelo `fetch` e a página de detalhe inteira acabaria
            # aninhada no formulário. `HX-Redirect` faz o htmx navegar a página.
            resposta = HttpResponse(status=204)
            resposta["HX-Redirect"] = destino
            return resposta
        return redirect(destino)

    def _renderizar_resumo(self, request, cabecalho_form, item_formset, dados_informados):
        materiais_por_id = {
            material.pk: material
            for material in Material.objects.filter(
                pk__in=[item.material_id for item in dados_informados.itens]
            )
        }
        itens_resumo = []
        for item in dados_informados.itens:
            material = materiais_por_id[item.material_id]
            itens_resumo.append(
                {
                    "material": material,
                    "quantidade": item.quantidade,
                    "saldo_atual": material.saldo,
                    "saldo_resultante": material.saldo + item.quantidade,
                }
            )

        emitente_escolhido = (
            Fornecedor.objects.filter(pk=dados_informados.emitente_id).first()
            if dados_informados.emitente_id
            else None
        )

        contexto = {
            "cabecalho_form": cabecalho_form,
            "item_formset": item_formset,
            "itens_resumo": itens_resumo,
            "emitente_escolhido": emitente_escolhido,
            "motivo_label": MotivoEntrada(dados_informados.motivo).label,
            "tipo_documento_label": TipoDocumentoEntrada(dados_informados.tipo_documento).label,
            "total_itens": len(itens_resumo),
            "modo": "resumo",
        }
        return self._renderizar(request, contexto, "resumo")


class EntradaNovaView(_ComposicaoEntradaBase):
    """Composição da entrada (`entrada_nova`): GET gera uma nova
    `chave_confirmacao`; POST trata cada ação de
    `contracts/composicao-entrada.md` sem gravar nada."""

    def get(self, request, *args, **kwargs):
        cabecalho_form = CabecalhoEntradaForm(initial={"chave_confirmacao": uuid.uuid4()})
        # Apresentação (achado do gate visual, "Flexibilidade e eficiência"):
        # foco inicial no Motivo ao abrir a composição — só aqui, nunca num
        # re-render de POST, para não competir com o `autofocus` que
        # `_renderizar_formulario` marca na quantidade da linha recém-criada.
        cabecalho_form.fields["motivo"].widget.attrs["autofocus"] = True
        item_formset = ItemEntradaFormSet(prefix="itens")
        return self._renderizar_formulario(request, cabecalho_form, item_formset)

    def post(self, request, *args, **kwargs):
        dados = request.POST.copy()
        acao = dados.get("acao", "")
        foco_posicao = None

        if "adicionar_material" in dados:
            foco_posicao = self._aplicar_adicionar_material(dados)
        elif "remover_item" in dados:
            self._aplicar_remover_item(dados)
        elif "escolher_emitente" in dados:
            self._aplicar_escolher_emitente(dados)
        elif acao == "limpar_emitente":
            dados["emitente"] = ""

        # Decisão do dono do produto (gate visual, 2026-09-27,
        # `contracts/composicao-entrada.md`): em qualquer re-render da
        # composição, quando o motivo é COMPRA e o tipo ainda está vazio, o
        # tipo passa a "Nota fiscal" (o usuário pode trocar). Só apresentação
        # — a confirmação nunca aplica isso por conta própria, exige o tipo
        # já enviado (visto pelo usuário no resumo).
        if dados.get("motivo") == MotivoEntrada.COMPRA and not dados.get("tipo_documento"):
            dados["tipo_documento"] = TipoDocumentoEntrada.NOTA_FISCAL

        cabecalho_form = CabecalhoEntradaForm(dados)
        item_formset = ItemEntradaFormSet(dados, prefix="itens")

        if acao == "revisar":
            return self._revisar(request, cabecalho_form, item_formset)

        return self._renderizar_formulario(
            request, cabecalho_form, item_formset, foco_posicao=foco_posicao
        )

    def _aplicar_adicionar_material(self, dados):
        """Acrescenta a linha e devolve sua posição (para o foco de
        apresentação em `_renderizar_formulario`), ou `None` quando nada foi
        acrescentado (pk inválido, material inexistente, já incluído ou
        `TOTAL_FORMS` fora do teto do formset)."""
        pk = _pk_informado(dados.get("adicionar_material", ""))
        dados["busca_material"] = ""
        if pk is None or not Material.objects.filter(pk=pk).exists():
            return None
        pk_texto = str(pk)
        total = _para_int(dados.get("itens-TOTAL_FORMS")) or 0
        # `range(total)` sobre um `TOTAL_FORMS` cru do POST, ANTES de o
        # formset (que teria seu próprio `absolute_max`) sequer existir —
        # sem este teto, um valor absurdo trava o processo por minutos.
        # `< absolute_max` (não `<=`, item 5 da 2ª rodada): acrescentar uma
        # linha quando `total == absolute_max` estouraria o teto do formset.
        if not (0 <= total < ItemEntradaFormSet.absolute_max):
            return None
        for indice in range(total):
            if dados.get(f"itens-{indice}-material") == pk_texto:
                return None
        dados[f"itens-{total}-material"] = pk_texto
        dados[f"itens-{total}-quantidade"] = ""
        dados["itens-TOTAL_FORMS"] = str(total + 1)
        return total

    def _aplicar_remover_item(self, dados):
        indice_remover = _para_int(dados.get("remover_item"))
        total = _para_int(dados.get("itens-TOTAL_FORMS")) or 0
        # Mesmo teto de `_aplicar_adicionar_material`, pelo mesmo motivo.
        if not (0 <= total <= ItemEntradaFormSet.absolute_max):
            return
        if indice_remover is None or not (0 <= indice_remover < total):
            return
        linhas = [
            (
                dados.get(f"itens-{indice}-material", ""),
                dados.get(f"itens-{indice}-quantidade", ""),
            )
            for indice in range(total)
            if indice != indice_remover
        ]
        for indice in range(total):
            dados.pop(f"itens-{indice}-material", None)
            dados.pop(f"itens-{indice}-quantidade", None)
        for indice, (material, quantidade) in enumerate(linhas):
            dados[f"itens-{indice}-material"] = material
            dados[f"itens-{indice}-quantidade"] = quantidade
        dados["itens-TOTAL_FORMS"] = str(len(linhas))

    def _aplicar_escolher_emitente(self, dados):
        pk = _pk_informado(dados.get("escolher_emitente", ""))
        dados["busca_emitente"] = ""
        if pk is None:
            return
        fornecedor = Fornecedor.objects.filter(pk=pk).first()
        if fornecedor is not None and not fornecedor.bloqueado:
            dados["emitente"] = str(pk)

    def _revisar(self, request, cabecalho_form, item_formset):
        dados_informados = montar_entrada_informada(cabecalho_form, item_formset)
        if dados_informados is None:
            return self._renderizar_formulario(
                request,
                cabecalho_form,
                item_formset,
                erros_gerais=list(item_formset.non_form_errors()),
            )

        try:
            validar_entrada(dados_informados)
        except EntradaJaRegistrada as exc:
            # Reenvio da mesma chave/referência a partir de "Revisar" (item
            # 1 da 2ª rodada do review: ex. confirmar, voltar pelo
            # navegador, "Revisar" de novo com o mesmo payload) — trata como
            # a confirmação trata, não como `EntradaInvalida`.
            return self._tratar_entrada_ja_registrada(request, exc, dados_informados)
        except EntradaInvalida as exc:
            return self._renderizar_entrada_invalida(request, exc, cabecalho_form, item_formset)

        # `validar_entrada` já recusa com `EntradaInvalida` enquanto
        # `dados_informados.tem_item_com_erro_de_formato` for `True` (item 3
        # da 2ª rodada do review) — chegar aqui garante que não há resumo
        # possível sem essa quantidade.
        return self._renderizar_resumo(request, cabecalho_form, item_formset, dados_informados)


class EntradaConfirmarView(_ComposicaoEntradaBase):
    """Confirmação da entrada (`entrada_confirmar`): revalida tudo por
    inteiro e registra (`contracts/rotas-e-autorizacao.md` → "Confirmação")."""

    def post(self, request, *args, **kwargs):
        chave_texto = request.POST.get("chave_confirmacao", "")
        try:
            uuid.UUID(chave_texto)
        except (ValueError, AttributeError, TypeError):
            return HttpResponseBadRequest("Requisição inválida.")

        cabecalho_form = CabecalhoEntradaForm(request.POST)
        item_formset = ItemEntradaFormSet(request.POST, prefix="itens")

        dados_informados = montar_entrada_informada(cabecalho_form, item_formset)
        if dados_informados is None:
            return self._renderizar_formulario(
                request,
                cabecalho_form,
                item_formset,
                erros_gerais=list(item_formset.non_form_errors()),
            )

        # `registrar_entrada` chama `validar_entrada` antes de qualquer
        # escrita, que já recusa com `EntradaInvalida` enquanto
        # `dados_informados.tem_item_com_erro_de_formato` for `True` (item 3
        # da 2ª rodada do review) — nunca registra uma entrada vazia ou
        # parcial, sem precisar de um ramo especial aqui.
        try:
            entrada = registrar_entrada(dados_informados, request.user)
        except EntradaJaRegistrada as exc:
            return self._tratar_entrada_ja_registrada(request, exc, dados_informados)
        except EntradaInvalida as exc:
            return self._renderizar_entrada_invalida(request, exc, cabecalho_form, item_formset)
        except Exception:
            logger.exception("Falha inesperada ao confirmar o registro da entrada.")
            messages.error(
                request,
                "Não foi possível concluir o registro por um erro inesperado. "
                "Tente novamente.",
            )
            return self._renderizar_formulario(request, cabecalho_form, item_formset)

        total_itens = len(dados_informados.itens)
        sufixo_item = "m" if total_itens == 1 else "ns"
        messages.success(
            request, f"Entrada registrada: {total_itens} ite{sufixo_item}."
        )
        return redirect("estoque:entrada_detalhe", pk=entrada.pk)


class ConsultaEntradasMixin(ExigePapelMixin):
    """Recorte de `PERM-STOCK-HISTORY-VIEW` para a entrada (research R12):
    funcionário do almoxarifado e auditor. Não pretende servir de base para
    a capability inteira, que `HIS` implementará."""

    def test_func(self):
        return self.request.user.tem_papel(Papel.FUNCIONARIO_ALMOXARIFADO, Papel.AUDITOR)


class EntradasView(ConsultaEntradasMixin, View):
    """Lista de entradas (`entradas`), da mais recente para a mais antiga.

    `pode_registrar_entrada` cobre `PERM-STOCK-ENTRY-CREATE`
    (`ROLE-WAREHOUSE-STAFF`, que o chefe do almoxarifado também possui) —
    usado pelo template para mostrar a ação "Registrar entrada" no page
    header e variar o estado vazio. O auditor acessa esta lista via
    `ConsultaEntradasMixin` (`PERM-STOCK-HISTORY-VIEW`) mas não tem esse
    papel, então a flag fica `False` para ele. A autorização efetiva de
    registrar continua na rota `entrada_nova`
    (`_ComposicaoEntradaBase`/`ExigePapelMixin`) — este contexto é só
    apresentação (Constitution VI), mesmo padrão de `pode_estornar`
    (`EntradaDetalheView`, abaixo) e de `pode_registrar_entrada`
    (`contas/views.py`, `HomeView`).
    """

    template_name = "estoque/entradas.html"

    def get(self, request, *args, **kwargs):
        entradas = (
            Entrada.objects.select_related("registrada_por", "emitente")
            .annotate(total_itens=Count("itens"))
            .order_by("-registrada_em", "-pk")
        )
        paginador = Paginator(entradas, TAMANHO_PAGINA_ENTRADAS)
        pagina = paginador.get_page(request.GET.get("pagina"))
        pode_registrar_entrada = request.user.tem_papel(Papel.FUNCIONARIO_ALMOXARIFADO)
        contexto = {
            "pagina": pagina,
            "pode_registrar_entrada": pode_registrar_entrada,
        }
        return render(request, self.template_name, contexto)


class EntradaDetalheView(ConsultaEntradasMixin, View):
    """Detalhe de uma entrada (`entrada_detalhe`), com o estorno quando
    houver e a ação de estornar quando aplicável."""

    template_name = "estoque/entrada_detalhe.html"

    def get(self, request, *args, **kwargs):
        entrada = get_object_or_404(
            Entrada.objects.select_related("registrada_por", "emitente"),
            pk=kwargs["pk"],
        )
        itens = entrada.itens.select_related("material")
        estorno = getattr(entrada, "estorno", None)
        pode_estornar = not entrada.estornada and request.user.tem_papel(
            Papel.CHEFE_ALMOXARIFADO
        )
        contexto = {
            "entrada": entrada,
            "itens": itens,
            "estorno": estorno,
            "pode_estornar": pode_estornar,
        }
        return render(request, self.template_name, contexto)


class EntradaEstornoView(ExigePapelMixin, View):
    """Estorno de uma entrada (`entrada_estorno`), conforme
    `contracts/rotas-e-autorizacao.md` → "Estorno"."""

    papel_exigido = Papel.CHEFE_ALMOXARIFADO
    template_name = "estoque/entrada_estorno.html"

    def get(self, request, *args, **kwargs):
        entrada = get_object_or_404(
            Entrada.objects.select_related("emitente", "registrada_por"), pk=kwargs["pk"]
        )
        if entrada.estornada:
            # Achado do gate visual: reabrir o formulário de uma ação que
            # não pode mais ser repetida é confuso — vai direto ao detalhe,
            # sem renderizar o formulário.
            messages.warning(request, "Esta entrada já foi estornada.")
            return redirect("estoque:entrada_detalhe", pk=entrada.pk)
        return self._renderizar(request, entrada, EstornoEntradaForm())

    def post(self, request, *args, **kwargs):
        entrada = get_object_or_404(
            Entrada.objects.select_related("emitente", "registrada_por"), pk=kwargs["pk"]
        )
        if entrada.estornada:
            messages.warning(request, "Esta entrada já foi estornada.")
            return redirect("estoque:entrada_detalhe", pk=entrada.pk)
        form = EstornoEntradaForm(request.POST)
        justificativa = request.POST.get("justificativa", "")

        try:
            estornar_entrada(entrada.pk, justificativa, request.user)
        except EntradaJaEstornada:
            messages.warning(request, "Esta entrada já foi estornada.")
            return redirect("estoque:entrada_detalhe", pk=entrada.pk)
        except JustificativaAusente:
            form.add_error("justificativa", "Informe a justificativa do estorno.")
            return self._renderizar(request, entrada, form)
        except EstornoBloqueadoPorSaldo:
            messages.error(
                request,
                "O estorno foi bloqueado: algum item ficaria com saldo negativo.",
            )
            return self._renderizar(request, entrada, form)
        except Exception:
            logger.exception(
                "Falha inesperada ao estornar a entrada (entrada_id=%s).", entrada.pk
            )
            messages.error(
                request,
                "Não foi possível concluir o estorno por um erro inesperado. "
                "Tente novamente.",
            )
            return self._renderizar(request, entrada, form)

        messages.success(request, "Entrada estornada.")
        return redirect("estoque:entrada_detalhe", pk=entrada.pk)

    def _renderizar(self, request, entrada, form):
        linhas = []
        algum_bloqueado = False
        for item in entrada.itens.select_related("material"):
            saldo_atual = item.material.saldo
            saldo_resultante = saldo_atual - item.quantidade
            bloqueado = saldo_resultante < 0
            algum_bloqueado = algum_bloqueado or bloqueado
            linhas.append(
                {
                    "item": item,
                    "saldo_atual": saldo_atual,
                    "saldo_resultante": saldo_resultante,
                    "bloqueado": bloqueado,
                }
            )
        contexto = {
            "entrada": entrada,
            "form": form,
            "linhas": linhas,
            "algum_bloqueado": algum_bloqueado,
        }
        return render(request, self.template_name, contexto)
