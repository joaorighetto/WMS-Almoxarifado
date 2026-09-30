/*
 * Composição da entrada — aprimoramentos progressivos pontuais (T018)
 *
 * Tudo nesta tela funciona sem este script (Constitution IX):
 * - Busca de material/emitente, adicionar/remover item, revisar, voltar e
 *   confirmar continuam clicáveis normalmente.
 * - Enter num campo de texto nunca aciona nada destrutivo mesmo sem JS: o
 *   primeiro botão de envio do `<form>` (`estoque/templates/estoque/
 *   entrada_nova.html`) é um botão neutro oculto (`acao=manter_dados`), que
 *   `EntradaNovaView.post` já trata como qualquer ação não reconhecida — só
 *   revalida e re-renderiza o formulário com os dados atuais, sem gravar
 *   nada e sem limpar emitente/itens (achado do code-reviewer: antes,
 *   "Remover emitente"/"Buscar emitente" eram os primeiros botões do
 *   formulário, e Enter em quantidade ou busca de material acionava um dos
 *   dois em silêncio).
 *
 * Com JS, os dois campos de busca passam a acionar a busca CORRESPONDENTE
 * (`contracts/composicao-entrada.md`: "Enter dentro de um campo de busca
 * aciona a busca correspondente, nunca 'Revisar'") em vez do botão neutro
 * acima — interceptando o Enter antes da submissão implícita do navegador
 * escolher o botão padrão do formulário.
 */
(() => {
  "use strict";

  const acionarBuscaAoTeclarEnter = (idCampo, valorAcao) => {
    const campo = document.getElementById(idCampo);
    if (!campo) {
      return;
    }

    campo.addEventListener("keydown", (evento) => {
      if (evento.key !== "Enter") {
        return;
      }

      const form = campo.form;
      const botao =
        form && form.querySelector(`button[name="acao"][value="${valorAcao}"]`);
      if (!form || !botao) {
        return;
      }

      evento.preventDefault();
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit(botao);
      } else {
        botao.click();
      }
    });
  };

  acionarBuscaAoTeclarEnter("id_busca_emitente", "buscar_emitente");
  acionarBuscaAoTeclarEnter("id_busca_material", "buscar_material");

  /* Decisão do dono do produto (gate visual, 2026-09-27,
     `contracts/composicao-entrada.md`): em COMPRA com o tipo ainda vazio, o
     tipo pré-seleciona "Nota fiscal" — o usuário pode trocar livremente.
     `EntradaNovaView.post` (`estoque/views.py`) já aplica isto em qualquer
     re-render sem JS; este listener só antecipa o mesmo efeito, sem round
     trip, quando o motivo muda ao vivo. Delegado em `document.body` (não em
     `#id_motivo` diretamente) porque o campo é recriado a cada troca HTMX —
     um listener direto se perderia no primeiro swap. Os valores em string
     espelham `MotivoEntrada.COMPRA`/`TipoDocumentoEntrada.NOTA_FISCAL`
     (`estoque/models.py`) — puramente de apresentação, sem regra de negócio
     aqui: a confirmação nunca aceita isto por conta própria (exige o tipo já
     visto pelo usuário no resumo). */
  const MOTIVO_COMPRA = "COMPRA";
  const TIPO_NOTA_FISCAL = "NOTA_FISCAL";

  document.body.addEventListener("change", (evento) => {
    const campoMotivo = evento.target;
    if (!campoMotivo || campoMotivo.id !== "id_motivo") {
      return;
    }
    const campoTipo = document.getElementById("id_tipo_documento");
    if (campoTipo && campoMotivo.value === MOTIVO_COMPRA && !campoTipo.value) {
      campoTipo.value = TIPO_NOTA_FISCAL;
    }
  });

  /* Foco depois de uma troca HTMX na composição (achado do gate visual,
     "Flexibilidade e eficiência" / "Recuperação de erros"). Prioridade,
     nesta ordem:
     1. quantidade da linha recém-adicionada (`autofocus` nativo, marcado por
        `_renderizar_formulario` — cobre também a renderização de página
        inteira sem HTMX; aqui só reforça o foco num nó trocado por
        `innerHTML`, onde `autofocus` nem sempre é reprocessado);
     2. primeiro campo inválido (`aria-invalid="true"`, atributo automático
        do Django 4.1+ quando o campo tem erro) ou, sem campo específico, o
        alerta geral (`erros_gerais`);
     3. depois de escolher um emitente, a busca de material (próximo passo
        natural da composição);
     4. depois de remover um item, a linha que ocupou a posição removida, ou
        a busca de material quando a removida era a última.
     O último botão acionado é capturado no "submit" (fase de bolha, o
     próprio evento nativo já traz `submitter`) ANTES do htmx interceptar —
     necessário porque, depois do swap, não há mais como perguntar ao
     servidor "qual ação foi esta". Sem JS, nenhum destes casos quebra
     nada: o formulário funciona normalmente, só sem o foco automático. */
  let ultimaAcaoAcionada = null;

  document.body.addEventListener("submit", (evento) => {
    const submitter = evento.submitter;
    ultimaAcaoAcionada = submitter
      ? { nome: submitter.name || "", valor: submitter.value || "" }
      : null;
  });

  document.body.addEventListener("htmx:afterSettle", (evento) => {
    const alvo = evento.detail && evento.detail.target;
    const acao = ultimaAcaoAcionada;
    ultimaAcaoAcionada = null;
    if (!alvo) {
      return;
    }

    const campoComFoco = alvo.querySelector("[autofocus]");
    if (campoComFoco) {
      campoComFoco.focus();
      return;
    }

    const campoInvalido = alvo.querySelector(
      '[aria-invalid="true"]:not([type="hidden"])'
    );
    if (campoInvalido) {
      campoInvalido.focus();
      return;
    }

    const alertaGeral = alvo.querySelector(".alert-danger");
    if (alertaGeral) {
      alertaGeral.setAttribute("tabindex", "-1");
      alertaGeral.focus();
      return;
    }

    if (!acao) {
      return;
    }

    if (acao.nome === "escolher_emitente") {
      const buscaMaterial = alvo.querySelector("#id_busca_material");
      if (buscaMaterial) {
        buscaMaterial.focus();
      }
      return;
    }

    if (acao.nome === "remover_item") {
      const linhasQuantidade = alvo.querySelectorAll(
        'input[inputmode="decimal"]'
      );
      const posicaoRemovida = Number(acao.valor);
      const proximaLinha =
        linhasQuantidade[posicaoRemovida] ||
        linhasQuantidade[linhasQuantidade.length - 1];
      const alvoFoco = proximaLinha || alvo.querySelector("#id_busca_material");
      if (alvoFoco) {
        alvoFoco.focus();
      }
    }
  });

  /* Estado "Processando" dos envios de efeito real (Confirmar entrada,
     Estornar entrada) — mesmo padrão de `static/js/envio.js`/
     `contas/static/contas/js/login.js` (Constitution, Princípio
     VIII), sem a parte de file upload (não usada aqui). Nenhum dos dois
     formulários é HTMX em si (`entrada_confirmar`/`entrada_estorno`
     continuam envios comuns, para o redirect de sucesso/aviso carregar a
     página inteira) — sem risco de o botão desabilitado antes da hora
     interferir na leitura de `FormData` pelo htmx.

     Delegado em `document.body` (achado do gate visual, 2ª rodada): o
     formulário de confirmação do RESUMO (`#resumo`, `estoque/templates/
     estoque/entrada_nova.html`) só existe depois de um swap HTMX de
     "Revisar" — um listener preso ao load (`querySelectorAll` direto,
     versão anterior) nunca o alcançava, e o botão nunca ganhava o estado
     "Confirmando…". Delegação em `document.body` é idempotente por
     natureza: um único listener cobre qualquer `[data-processing-form]`,
     presente no load ou inserido depois por um swap. */
  const rotuloOriginalPorFormulario = new WeakMap();

  document.body.addEventListener("submit", (evento) => {
    const form = evento.target;
    if (!(form instanceof HTMLFormElement) || !form.matches("[data-processing-form]")) {
      return;
    }
    const submitButton = form.querySelector("[data-processing-submit]");
    const submitLabel = form.querySelector("[data-processing-submit-label]");
    if (!submitButton || !submitLabel) {
      return;
    }

    if (!rotuloOriginalPorFormulario.has(form)) {
      rotuloOriginalPorFormulario.set(form, submitLabel.textContent);
    }

    form.setAttribute("aria-busy", "true");
    submitButton.disabled = true;
    submitLabel.textContent = form.dataset.processingLabel || "Processando…";
  });

  /* Restaura os controles ao voltar pelo histórico quando a página vem do
     bfcache — cobre qualquer `[data-processing-form]` presente na página
     NESTE momento (o htmx não sobrevive ao bfcache: a página volta como
     estava antes do swap, então não há formulário "órfão" de uma troca
     HTMX para restaurar). */
  window.addEventListener("pageshow", () => {
    document.querySelectorAll("[data-processing-form]").forEach((form) => {
      const submitButton = form.querySelector("[data-processing-submit]");
      const submitLabel = form.querySelector("[data-processing-submit-label]");
      const rotuloOriginal = rotuloOriginalPorFormulario.get(form);
      form.removeAttribute("aria-busy");
      if (submitButton) {
        submitButton.disabled = false;
      }
      if (submitLabel && rotuloOriginal !== undefined) {
        submitLabel.textContent = rotuloOriginal;
      }
    });
  });
})();
