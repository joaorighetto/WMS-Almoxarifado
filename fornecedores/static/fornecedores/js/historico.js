/*
 * Histórico de importações de fornecedores — clique em qualquer ponto da
 * linha (T027, mesmo padrão de `catalogo/static/catalogo/js/historico.js`,
 * com as classes próprias `fornecedores-historico-*`).
 *
 * Aprimoramento progressivo pontual: cada linha já tem um `<a>` real na
 * coluna "Execução" (`fornecedores/templates/fornecedores/historico.html`),
 * que funciona sozinho, sem nenhum script. Este arquivo só estende a área
 * de clique para a linha inteira, sem introduzir overlay CSS que bloqueie a
 * seleção de texto das outras células.
 *
 * Ignora o clique quando há uma seleção de texto não vazia (o usuário
 * estava selecionando/copiando, não navegando), quando o próprio alvo do
 * clique já é o link (evita disparar `link.click()` duas vezes) e quando o
 * clique vem com modificador ou botão não-primário (deixa o gesto ao
 * navegador).
 */
(() => {
  "use strict";

  document.querySelectorAll(".fornecedores-historico-row").forEach((linha) => {
    const link = linha.querySelector(".fornecedores-historico-link");
    if (!link) {
      return;
    }

    linha.addEventListener("click", (evento) => {
      if (evento.target.closest("a")) {
        return;
      }

      if (evento.button !== 0 || evento.ctrlKey || evento.metaKey || evento.shiftKey || evento.altKey) {
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
