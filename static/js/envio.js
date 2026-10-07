/*
 * Estado de processamento das telas de importação (T029)
 *
 * Movido de `catalogo/static/catalogo/js/envio.js` para `static/js/` (nome
 * neutro, consolidação de UX, Fase A): já era carregado também pelas telas
 * de envio/prévia de `fornecedores` (cópia por `<script src>`, sem app
 * "dono"). Contrato inalterado — tudo por atributos `data-*`.
 *
 * Mesmo padrão de contas/static/contas/js/login.js (Constitution, Princípio VIII):
 * botão desabilitado, rótulo "Processando…", `aria-busy`, bloqueio de duplo envio e
 * reset no `pageshow` (bfcache). Aqui generalizado por atributos `data-*` para valer
 * em mais de um formulário na mesma página (envio; confirmação e, opcionalmente,
 * cancelamento, na prévia). Tudo funciona sem este script: sem JS, os formulários
 * continuam submetendo normalmente.
 *
 * Barra de confirmação (`.confirmation-bar`, prévia): enquanto o formulário de confirmar está
 * ocupado, os demais botões da mesma barra (o Cancelar) também ficam desabilitados — cancelar no
 * meio da confirmação apagaria o pedido que o servidor acabou de receber. Voltam no `pageshow`.
 *
 * Consumidores: catalogo/templates/catalogo/importacao_envio.html,
 * catalogo/templates/catalogo/importacao_previa.html,
 * fornecedores/templates/fornecedores/importacao_envio.html,
 * fornecedores/templates/fornecedores/importacao_previa.html.
 */
(() => {
  "use strict";

  /* Formulários da mesma página que enviam para a mesma action compartilham o bloqueio de duplo
     envio — hoje a prévia tem um só par confirmar/cancelar (a barra), mas o mecanismo vale para
     mais de um formulário. O servidor já recusa a segunda confirmação pelo token único; isto só
     evita que o usuário perca a mensagem de sucesso da primeira. */
  const ocupantesPorAction = new Map();

  const inicializarProcessamento = (form) => {
    const submitButton = form.querySelector("[data-processing-submit]");
    const submitLabel = form.querySelector("[data-processing-submit-label]");
    if (!submitButton || !submitLabel) {
      return;
    }

    const rotuloOcupado = form.dataset.processingLabel || "Processando…";
    /* `innerHTML`, não `textContent`: o rótulo pode ter marcação interna (a prévia envolve os totais
       num `<small>` que o celular oculta só visualmente) e o reset precisa devolvê-la intacta. A
       marcação é a que o servidor renderizou, nunca texto do usuário. */
    const rotuloOriginal = submitLabel.innerHTML;
    const barra = form.closest(".confirmation-bar");
    let desabilitadosPelaBarra = [];

    const resetar = () => {
      form.dataset.submitting = "false";
      form.removeAttribute("aria-busy");
      submitButton.disabled = false;
      submitButton.style.minWidth = "";
      submitLabel.innerHTML = rotuloOriginal;
      desabilitadosPelaBarra.forEach((botao) => {
        botao.disabled = false;
      });
      desabilitadosPelaBarra = [];
    };

    const ocupar = () => {
      form.dataset.submitting = "true";
      form.setAttribute("aria-busy", "true");
      /* Fixa a largura atual antes de trocar o rótulo: "Confirmando…" é curto e o botão encolheria,
         arrastando o que vem ao lado (o Cancelar) no desktop. Sai no reset. */
      submitButton.style.minWidth = `${submitButton.offsetWidth}px`;
      submitButton.disabled = true;
      submitLabel.textContent = rotuloOcupado;
      if (barra) {
        /* Só os botões que estavam habilitados: o reset não reabilita o que já nasceu desabilitado. */
        desabilitadosPelaBarra = Array.from(barra.querySelectorAll("button")).filter(
          (botao) => !form.contains(botao) && !botao.disabled,
        );
        desabilitadosPelaBarra.forEach((botao) => {
          botao.disabled = true;
        });
      }
    };

    const chave = form.action;
    if (!ocupantesPorAction.has(chave)) {
      ocupantesPorAction.set(chave, []);
    }
    ocupantesPorAction.get(chave).push(ocupar);

    form.addEventListener("submit", (event) => {
      if (form.dataset.submitting === "true") {
        event.preventDefault();
        return;
      }

      ocupantesPorAction.get(chave).forEach((ocuparIrmao) => ocuparIrmao());
    });

    /* Restaura os controles ao voltar pelo histórico quando a página vem do bfcache. */
    window.addEventListener("pageshow", resetar);
  };

  document.querySelectorAll("[data-processing-form]").forEach(inicializarProcessamento);

  /* Preenche `.file-upload-meta` (DESIGN.md → Components → File Upload) com nome e
     tamanho do arquivo escolhido, antes do envio. Revisão do gate visual (achado P2):
     o input nativo agora fica oculto só visualmente (`static/css/components.css`), então
     este texto passa a ser a única confirmação visível de qual arquivo foi escolhido —
     por isso o HTML já nasce com um texto padrão em pt-BR ("Nenhum arquivo
     selecionado."), nunca `hidden`; sem JS, esse texto simplesmente não é atualizado
     (o envio em si continua funcionando normalmente). */
  const inputArquivo = document.querySelector("[data-file-upload-input]");
  const metaArquivo = document.querySelector("[data-file-upload-meta]");
  const textoPadraoMeta = metaArquivo ? metaArquivo.textContent : "";

  if (inputArquivo && metaArquivo) {
    const formatarTamanho = (bytes) => {
      if (bytes < 1024) {
        return `${bytes} B`;
      }

      const unidades = ["KB", "MB", "GB"];
      let valor = bytes;
      let indice = -1;

      do {
        valor /= 1024;
        indice += 1;
      } while (valor >= 1024 && indice < unidades.length - 1);

      return `${valor.toFixed(1)} ${unidades[indice]}`;
    };

    inputArquivo.addEventListener("change", () => {
      const arquivo = inputArquivo.files && inputArquivo.files[0];

      if (!arquivo) {
        metaArquivo.textContent = textoPadraoMeta;
        return;
      }

      metaArquivo.textContent = `${arquivo.name} — ${formatarTamanho(arquivo.size)}`;
    });
  }
})();
