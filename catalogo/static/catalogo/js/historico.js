/*
 * Histórico de importações — clique em qualquer ponto da linha (revisão do gate
 * visual, achado menor 9c)
 *
 * Aprimoramento progressivo pontual: cada linha já tem um `<a>` real na coluna
 * "Execução" (`catalogo/templates/catalogo/historico.html`), que funciona sozinho,
 * sem nenhum script. Este arquivo só estende a área de clique para a linha inteira,
 * sem reintroduzir o overlay CSS que bloqueava a seleção de texto das outras células
 * (`catalogo/static/catalogo/css/catalogo.css`, comentário de `.catalogo-historico-link`).
 *
 * Ignora o clique quando há uma seleção de texto não vazia (o usuário estava
 * selecionando/copiando, não navegando) e quando o próprio alvo do clique já é o
 * link (evita disparar `link.click()` duas vezes).
 */
(() => {
  "use strict";

  document.querySelectorAll(".catalogo-historico-row").forEach((linha) => {
    const link = linha.querySelector(".catalogo-historico-link");
    if (!link) {
      return;
    }

    linha.addEventListener("click", (evento) => {
      if (evento.target.closest("a")) {
        return;
      }

      const selecao = window.getSelection ? window.getSelection() : null;
      if (selecao && selecao.toString().length > 0) {
        return;
      }

      link.click();
    });
  });
})();
