/*
 * Linha de tabela clicável — aprimoramento progressivo genérico
 * (consolidação de UX, Fase A). Substitui `catalogo/static/catalogo/js/
 * historico.js` e `fornecedores/static/fornecedores/js/historico.js`
 * (cópias idênticas, só com classes de app trocadas).
 *
 * Contrato por data-attributes, não por classe de app:
 * - `<tr data-linha-clicavel>` marca a linha;
 * - dentro dela, `<a data-linha-link>` marca o link real que já funciona
 *   sozinho, sem nenhum script (DESIGN.md → Components → Table: "a
 *   navegação é sempre um `<a>` real numa célula").
 *
 * O script É QUEM aplica a affordance visual `.table-row-clickable`
 * (`static/css/components.css`) às linhas que ele de fato aprimora — uma
 * linha sem este script carregado nunca promete um clique que não tem.
 *
 * Comportamento preservado de `historico.js` (catalogo/fornecedores):
 * ignora o clique quando (a) o alvo já está dentro de um `<a>` (evita
 * `link.click()` duas vezes); (b) há seleção de texto não vazia (o usuário
 * estava selecionando/copiando, não navegando); (c) o clique tem
 * modificador (Ctrl/Cmd/Shift/Alt) ou botão não-primário (deixa o gesto ao
 * navegador — o link real continua aceitando abrir em nova aba).
 *
 * Correção do gate visual (P1, Fase B): também ignora o clique quando o
 * alvo está dentro de QUALQUER elemento interativo/expansível da linha —
 * não só `<a>`. Sem isso, o `<summary>` de `.table-cell-filename-detalhe`
 * (coluna Arquivo dos históricos) borbulhava até aqui e `link.click()`
 * navegava para a execução em vez de abrir/fechar o `<details>` (clicar no
 * nome completo já expandido tinha o mesmo problema). A lista cobre todo
 * controle nativo que a linha pode conter, mesmo que hoje só `<a>` e
 * `<summary>`/`<details>` apareçam: `button`, `input`, `select`, `textarea`
 * e `label` ficam de fora do aprimoramento pelo mesmo motivo — um controle
 * de formulário dentro de uma linha "clicável" nunca deve competir com o
 * próprio controle.
 *
 * Consumidores: catalogo/templates/catalogo/historico.html,
 * fornecedores/templates/fornecedores/historico.html,
 * estoque/templates/estoque/entradas.html.
 */
(() => {
  "use strict";

  document.querySelectorAll("[data-linha-clicavel]").forEach((linha) => {
    const link = linha.querySelector("[data-linha-link]");
    if (!link) {
      return;
    }

    linha.classList.add("table-row-clickable");

    linha.addEventListener("click", (evento) => {
      if (evento.target.closest("a, summary, details, button, input, select, textarea, label")) {
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
