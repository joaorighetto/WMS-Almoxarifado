"""Formulários de composição, resumo e confirmação da entrada
(`contracts/composicao-entrada.md`, T016).

O estado da entrada viaja no próprio formulário (research R3): nada é
gravado antes da confirmação. `CabecalhoEntradaForm` e `ItemEntradaFormSet`
só validam estrutura/tipo (UUID, inteiro, texto) — de propósito: o usuário
continua buscando material e emitente antes de "Revisar", com o motivo ou o
número do documento ainda em branco, sem que isso derrube o restante do
formulário. A regra de negócio (motivo/tipo válidos, número não vazio,
emitente por motivo, material existente, referência já usada, limite de
saldo) é aplicada por `estoque.entradas.validar_entrada`/`registrar_entrada`
a partir da `EntradaInformada` que `montar_entrada_informada` monta; a
mesma função interpreta a quantidade de cada item (`estoque.quantidade`,
único ponto de erro de formato tratado aqui, por ser detalhe de campo, não
regra de negócio) e `aplicar_entrada_invalida` traduz uma `EntradaInvalida`
de volta em erros de campo/linha, para o re-render preservar os dados
(FR-009).
"""

from django import forms
from django.forms import BaseFormSet, formset_factory

from estoque.entradas import EntradaInformada, EntradaInvalida, ItemInformado
from estoque.models import MotivoEntrada, TipoDocumentoEntrada
from estoque.quantidade import QuantidadeInvalida, interpretar_quantidade_recebida


class CabecalhoEntradaForm(forms.Form):
    """Cabeçalho da entrada em composição. Todos os campos de negócio são
    opcionais neste nível — a obrigatoriedade é regra de negócio, aplicada
    por `estoque.entradas.validar_entrada` — para que buscar material ou
    emitente continue funcionando antes de o cabeçalho estar completo."""

    chave_confirmacao = forms.UUIDField(widget=forms.HiddenInput)
    motivo = forms.ChoiceField(
        choices=[("", "Escolha um motivo")] + list(MotivoEntrada.choices),
        required=False,
        label="Motivo",
    )
    tipo_documento = forms.ChoiceField(
        choices=[("", "Escolha um tipo")] + list(TipoDocumentoEntrada.choices),
        required=False,
        label="Tipo de documento",
    )
    numero_documento = forms.CharField(required=False, label="Número do documento")
    # Só o `pk` do fornecedor escolhido — nome, código e documento exibidos
    # vêm sempre do banco (a view resolve pelo pk), nunca deste campo.
    emitente = forms.IntegerField(required=False, widget=forms.HiddenInput)
    busca_emitente = forms.CharField(required=False, label="Buscar emitente")
    busca_material = forms.CharField(required=False, label="Buscar material")


class ItemEntradaForm(forms.Form):
    """Uma linha do formset de itens. `material` é sempre o `pk` oculto
    escolhido na busca (código, descrição e unidade exibidos vêm do banco,
    nunca deste campo)."""

    material = forms.IntegerField(widget=forms.HiddenInput)
    quantidade = forms.CharField(
        required=False,
        label="Quantidade",
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
    )


ItemEntradaFormSet = formset_factory(
    ItemEntradaForm, formset=BaseFormSet, extra=0, can_delete=False
)


def montar_entrada_informada(
    cabecalho_form: CabecalhoEntradaForm, item_formset: BaseFormSet
) -> EntradaInformada | None:
    """Monta `EntradaInformada` a partir dos forms. Só recusa aqui o que é
    erro de formato do próprio campo de quantidade (research R8) —
    anexado por linha via `form.add_error`, sem interromper o restante;
    qualquer outra regra de negócio é responsabilidade de
    `estoque.entradas.validar_entrada`/`registrar_entrada`, chamada pela
    view com o resultado.

    Retorna `None` quando o CABEÇALHO tem erro de formato (UUID
    ausente/malformado, `motivo`/`tipo_documento` fora da lista de opções)
    ou quando `item_formset.non_form_errors()` acusa `TOTAL_FORMS` acima de
    `absolute_max` (item 5 do review): sem isto, `item_formset.forms`
    clampa em silêncio nos primeiros `absolute_max` itens e montaríamos uma
    entrada parcial sem avisar ninguém. Nos dois casos não há como montar
    `EntradaInformada`; a view usa `item_formset.non_form_errors()` como
    `erros_gerais` do segundo caso.

    Um item com erro de formato (`material` sem `pk`, quantidade fora da
    gramática aceita) NÃO derruba o retorno — o erro já fica anexado ao
    form da linha (`item.add_error`) e o item é excluído de `itens`, com
    `tem_item_com_erro_de_formato=True` marcado para o cabeçalho continuar
    sendo validado (e mostrado) junto (item 8 do review: erros de cabeçalho
    e de item numa só resposta); `estoque.entradas.validar_entrada` recusa
    com `EntradaInvalida` enquanto esse marcador for `True` (item 3 do
    review: nunca registra uma entrada vazia ou parcial).
    """
    cabecalho_valido = cabecalho_form.is_valid()
    # `is_valid()` popula `non_form_errors()` (inclui "too_many_forms" —
    # Django já clampa `total_form_count()`/`.forms` em `absolute_max`, mas
    # só sinaliza isso aqui).
    item_formset.is_valid()
    if not cabecalho_valido or item_formset.non_form_errors():
        return None

    itens: list[ItemInformado] = []
    tem_item_com_erro_de_formato = False
    for posicao_formset, form in enumerate(item_formset.forms):
        if not form.is_valid():
            tem_item_com_erro_de_formato = True
            continue
        material_id = form.cleaned_data.get("material")
        texto_quantidade = form.cleaned_data.get("quantidade") or ""
        try:
            quantidade = interpretar_quantidade_recebida(texto_quantidade)
        except QuantidadeInvalida as exc:
            form.add_error("quantidade", exc.mensagem)
            tem_item_com_erro_de_formato = True
            continue
        itens.append(
            ItemInformado(
                material_id=material_id,
                quantidade=quantidade,
                posicao_formset=posicao_formset,
            )
        )

    dados = cabecalho_form.cleaned_data
    return EntradaInformada(
        chave_confirmacao=dados["chave_confirmacao"],
        motivo=dados.get("motivo") or "",
        tipo_documento=dados.get("tipo_documento") or "",
        numero_documento=dados.get("numero_documento") or "",
        emitente_id=dados.get("emitente"),
        itens=tuple(itens),
        tem_item_com_erro_de_formato=tem_item_com_erro_de_formato,
    )


def aplicar_entrada_invalida(
    exc: EntradaInvalida, cabecalho_form: CabecalhoEntradaForm, item_formset: BaseFormSet
) -> list[str]:
    """Traduz `EntradaInvalida` (e subclasses) em erros de campo do
    cabeçalho e de linha do formset. Mensagens sem campo/linha
    correspondente (ex.: `itens` vazio) voltam na lista de erros gerais,
    para a view exibir como alerta."""
    erros_gerais: list[str] = []

    for campo, mensagens in exc.erros_campo.items():
        if campo in cabecalho_form.fields:
            for mensagem in mensagens:
                cabecalho_form.add_error(campo, mensagem)
        else:
            erros_gerais.extend(mensagens)

    for posicao, mensagens in exc.erros_item.items():
        if 0 <= posicao < len(item_formset.forms):
            for mensagem in mensagens:
                item_formset.forms[posicao].add_error(None, mensagem)
        else:
            erros_gerais.extend(mensagens)

    return erros_gerais


class EstornoEntradaForm(forms.Form):
    """Justificativa do estorno (`EntradaEstornoView`, T029). A
    obrigatoriedade (não vazio após `strip()`) é regra de negócio, checada
    por `estoque.entradas.estornar_entrada` (`JustificativaAusente`) — o
    campo aqui é `required=False` pelo mesmo motivo de `CabecalhoEntradaForm`."""

    justificativa = forms.CharField(
        required=False,
        label="Justificativa",
        widget=forms.Textarea(attrs={"rows": 4}),
    )
