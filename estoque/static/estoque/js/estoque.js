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
        alerta geral (`erros_gerais`, `.error-box[role="alert"]`); a revisão
        (`#resumo-heading`) recebe o foco no lugar do botão "Revisar";
     3. depois de escolher um emitente, a busca de material (próximo passo
        natural da composição);
     4. depois de remover um item, a linha que ocupou a posição removida, ou
        a busca de material quando a removida era a última.
     O último botão acionado é capturado no "submit" (fase de bolha, o
     próprio evento nativo já traz `submitter`) ANTES do htmx interceptar —
     necessário porque, depois do swap, não há mais como perguntar ao
     servidor "qual ação foi esta". Sem JS, nenhum destes casos quebra
     nada: o formulário funciona normalmente, só sem o foco automático. */
  /* Campo da tabela de Materiais à vista depois de focado (achado do gate visual, 2ª rodada): num
     `.table-wrapper` rolável (até ~860px a quantidade e o erro ficam além da borda direita), o
     `focus()` nem sempre rola o wrapper na horizontal (acontece com o erro na 2ª linha, com a 1ª
     sem rolagem) e o campo e o texto do erro ficavam fora da área visível. Rola a página até a
     célula e, depois, o wrapper o mínimo para caber o campo e o bloco de erro da linha (o campo vem
     primeiro se os dois não couberem). Só apresentação: não muda foco nem valor. */
  const revelarCampo = (campo) => {
    const celula = campo.closest("td") || campo;
    celula.scrollIntoView({ block: "nearest", inline: "nearest" });
    const wrapper = campo.closest(".table-wrapper");
    if (!wrapper) {
      return;
    }
    const caixa = wrapper.getBoundingClientRect();
    const erro = celula.querySelector(".estoque-erro-linha");
    const retangulos = [campo, erro].filter(Boolean).map((no) => no.getBoundingClientRect());
    const esquerda = Math.min(...retangulos.map((r) => r.left));
    const direita = Math.max(...retangulos.map((r) => r.right));
    if (direita > caixa.right) {
      /* Não passa do ponto em que o campo começa a sair pela esquerda. */
      const campoEsquerda = campo.getBoundingClientRect().left;
      wrapper.scrollLeft += Math.min(direita - caixa.right, campoEsquerda - caixa.left);
    } else if (esquerda < caixa.left) {
      wrapper.scrollLeft -= caixa.left - esquerda;
    }
  };

  /* Confirmar logo depois do Revisar (achado do gate visual, 2ª rodada): a revisão troca o botão
     "Revisar" pelo "Confirmar entrada" no mesmo ponto da tela (viewports baixas: o primário da barra
     gruda no rodapé exatamente onde estava "Revisar"), e um segundo toque ou clique, ainda do gesto
     de Revisar, gravaria sem que a revisão fosse lida. Por `JANELA_LEITURA_MS` depois que a revisão
     entra no DOM, o envio do formulário de confirmação é ignorado (o botão NÃO fica `disabled`: sem
     JS, ou depois da janela, é um envio comum, com o estado "Confirmando…" de sempre). Observa o
     alvo da troca em vez de um evento do HTMX: o `#resumo-heading` aparece no mesmo instante da
     inserção, sem janela entre a troca e o início da proteção. */
  const JANELA_LEITURA_MS = 500;

  const protegerConfirmacaoRecemExibida = (alvo) => {
    const form = alvo.querySelector("form[data-processing-form]");
    if (!form || form.dataset.aguardandoLeitura) {
      return;
    }
    form.dataset.aguardandoLeitura = "true";
    window.setTimeout(() => {
      delete form.dataset.aguardandoLeitura;
    }, JANELA_LEITURA_MS);
  };

  const alvoComposicao = document.getElementById("entrada-composicao");
  if (alvoComposicao && typeof MutationObserver === "function") {
    new MutationObserver(() => {
      if (alvoComposicao.querySelector("#resumo-heading")) {
        protegerConfirmacaoRecemExibida(alvoComposicao);
      }
    }).observe(alvoComposicao, { childList: true });
  }

  let ultimaAcaoAcionada = null;

  document.body.addEventListener("submit", (evento) => {
    const submitter = evento.submitter;
    ultimaAcaoAcionada = submitter
      ? { nome: submitter.name || "", valor: submitter.value || "" }
      : null;
  });

  /* Evento do HTMX 4 (`htmx:after:settle`; o `htmx:afterSettle` do 2.x não existe mais e esta
     rotina nunca chegou a rodar). A composição é a única tela com troca HTMX aqui: o alvo é sempre
     `#entrada-composicao`. */
  document.body.addEventListener("htmx:after:settle", (evento) => {
    const alvo = document.getElementById("entrada-composicao");
    const acao = ultimaAcaoAcionada;
    ultimaAcaoAcionada = null;
    if (!alvo || !(evento.target instanceof Node) || !alvo.contains(evento.target)) {
      return;
    }

    const campoComFoco = alvo.querySelector("[autofocus]");
    if (campoComFoco) {
      campoComFoco.focus();
      revelarCampo(campoComFoco);
      return;
    }

    const campoInvalido = alvo.querySelector(
      '[aria-invalid="true"]:not([type="hidden"])'
    );
    if (campoInvalido) {
      campoInvalido.focus();
      revelarCampo(campoInvalido);
      return;
    }

    const alertaGeral = alvo.querySelector('.error-box[role="alert"]');
    if (alertaGeral) {
      alertaGeral.setAttribute("tabindex", "-1");
      alertaGeral.focus();
      return;
    }

    /* "Revisar" troca o formulário inteiro pela revisão: o botão acionado deixa de existir e o foco
       cairia no <body>. O título da revisão (`tabindex="-1"` no template) o recebe. */
    const tituloRevisao = alvo.querySelector("#resumo-heading");
    if (tituloRevisao) {
      tituloRevisao.focus();
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
     formulário de confirmação da REVISÃO (`#resumo`, `estoque/templates/
     estoque/entrada_nova.html`) só existe depois de um swap HTMX de
     "Revisar" — um listener preso ao load (`querySelectorAll` direto,
     versão anterior) nunca o alcançava, e o botão nunca ganhava o estado
     "Confirmando…". Delegação em `document.body` é idempotente por
     natureza: um único listener cobre qualquer `[data-processing-form]`,
     presente no load ou inserido depois por um swap.

     Paridade com `envio.js` (barra de confirmação, `.confirmation-bar`): enquanto o envio está
     ocupado, a largura do botão fica fixada (o rótulo "Confirmando…"/"Estornando…" é mais curto e o
     botão encolheria, arrastando o vizinho) e os demais controles da MESMA barra — "Voltar e corrigir"
     (botão de outro formulário) e "Cancelar" (link) — ficam desabilitados: cancelar no meio do envio
     não desfaz o que o servidor acabou de receber. Tudo volta no `pageshow`. O rótulo original é
     guardado como HTML (`innerHTML`): ele carrega os totais num `<small>` que o celular oculta só
     visualmente, e o reset precisa devolvê-los intactos. A marcação é a que o servidor renderizou,
     nunca texto do usuário. */
  const estadoPorFormulario = new WeakMap();

  const controlesDaBarra = (form) => {
    const barra = form.closest(".confirmation-bar") || form.querySelector(".confirmation-bar");
    return barra ? Array.from(barra.querySelectorAll("button, a.btn")) : [];
  };

  const ocuparControle = (controle) => {
    if (controle.matches("a")) {
      controle.setAttribute("aria-disabled", "true");
      controle.setAttribute("tabindex", "-1");
    } else {
      controle.disabled = true;
    }
  };

  const liberarControle = (controle) => {
    if (controle.matches("a")) {
      controle.removeAttribute("aria-disabled");
      controle.removeAttribute("tabindex");
    } else {
      controle.disabled = false;
    }
  };

  const estaOcupado = (controle) =>
    controle.matches("a") ? controle.getAttribute("aria-disabled") === "true" : controle.disabled;

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

    if (form.getAttribute("aria-busy") === "true" || form.dataset.aguardandoLeitura) {
      evento.preventDefault();
      return;
    }

    /* Só os controles que estavam livres: o reset não reabilita o que já nasceu desabilitado. */
    const ocupadosPelaBarra = controlesDaBarra(form).filter(
      (controle) => controle !== submitButton && !estaOcupado(controle)
    );
    estadoPorFormulario.set(form, {
      rotuloOriginal: submitLabel.innerHTML,
      ocupadosPelaBarra,
    });

    form.setAttribute("aria-busy", "true");
    submitButton.style.minWidth = `${submitButton.offsetWidth}px`;
    submitButton.disabled = true;
    submitLabel.textContent = form.dataset.processingLabel || "Processando…";
    ocupadosPelaBarra.forEach(ocuparControle);
  });

  /* Um link desabilitado (`aria-disabled`) não navega: o `aria-disabled` sozinho não impede o clique. */
  document.body.addEventListener("click", (evento) => {
    const link = evento.target instanceof Element ? evento.target.closest('a.btn[aria-disabled="true"]') : null;
    if (link) {
      evento.preventDefault();
    }
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
      const estado = estadoPorFormulario.get(form);
      form.removeAttribute("aria-busy");
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.style.minWidth = "";
      }
      if (submitLabel && estado) {
        submitLabel.innerHTML = estado.rotuloOriginal;
      }
      if (estado) {
        estado.ocupadosPelaBarra.forEach(liberarControle);
      }
    });
  });
})();
