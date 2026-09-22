/*
 * Estado de processamento das telas de importação (T029)
 *
 * Mesmo padrão de contas/static/contas/js/login.js (Constitution, Princípio VIII):
 * botão desabilitado, rótulo "Processando…", `aria-busy`, bloqueio de duplo envio e
 * reset no `pageshow` (bfcache). Aqui generalizado por atributos `data-*` para valer
 * em mais de um formulário na mesma página (envio; confirmação e, opcionalmente,
 * cancelamento, na prévia). Tudo funciona sem este script: sem JS, os formulários
 * continuam submetendo normalmente.
 */
(() => {
  "use strict";

  /* Formulários da mesma página que enviam para a mesma action (a prévia tem dois
     pares confirmar/cancelar: a barra fixa e a seção do fim) compartilham o bloqueio
     de duplo envio — confirmar num e depois no outro enviaria dois POSTs. O servidor
     já recusa a segunda confirmação pelo token único; isto só evita que o usuário
     perca a mensagem de sucesso da primeira. */
  const ocupantesPorAction = new Map();

  const inicializarProcessamento = (form) => {
    const submitButton = form.querySelector("[data-processing-submit]");
    const submitLabel = form.querySelector("[data-processing-submit-label]");
    if (!submitButton || !submitLabel) {
      return;
    }

    const rotuloOcupado = form.dataset.processingLabel || "Processando…";
    const rotuloOriginal = submitLabel.textContent;

    const resetar = () => {
      form.dataset.submitting = "false";
      form.removeAttribute("aria-busy");
      submitButton.disabled = false;
      submitLabel.textContent = rotuloOriginal;
    };

    const ocupar = () => {
      form.dataset.submitting = "true";
      form.setAttribute("aria-busy", "true");
      submitButton.disabled = true;
      submitLabel.textContent = rotuloOcupado;
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
