/*
 * "Mostrar senha(s)" — login e `/senha/` (WMS-Almoxarifado)
 *
 * Aprimoramento progressivo: uma caixa `<input type="checkbox" data-mostrar-senha>` dentro do
 * `<form>` alterna entre `type="password"` e `type="text"` todos os campos de senha desse mesmo
 * formulário, identificados por `autocomplete="current-password"` ou `autocomplete="new-password"`
 * (o Django põe esses valores nos widgets dos formulários de credencial). Sem JavaScript a caixa
 * não aparece (`html:not(.js) .field-check-js`, components.css) e os campos ficam sempre ocultos.
 *
 * Contrato:
 *   - `data-mostrar-senha` na caixa; o escopo é o `<form>` mais próximo (a caixa sem formulário não
 *     faz nada). A caixa não tem `name`, então nunca é enviada.
 *   - Ao enviar o formulário, os campos voltam a `type="password"` antes do envio, para o navegador
 *     não guardar a senha como texto comum (histórico de preenchimento, restauração de sessão).
 *   - Na restauração pelo bfcache (`pageshow`) a caixa é desmarcada e os campos voltam a
 *     `password`.
 *   - O valor da senha nunca é lido, copiado nem guardado aqui: só o atributo `type` muda.
 *
 * Carregado uma vez, com `defer`; os listeners são delegados em `document`.
 */
(() => {
  "use strict";

  const SELETOR_CAMPOS =
    'input[autocomplete="current-password"], input[autocomplete="new-password"]';

  const camposDe = (form) => form.querySelectorAll(SELETOR_CAMPOS);

  const definirTipo = (form, tipo) => {
    camposDe(form).forEach((campo) => {
      campo.type = tipo;
    });
  };

  const ocultar = (form) => {
    form.querySelectorAll("[data-mostrar-senha]").forEach((caixa) => {
      caixa.checked = false;
    });
    definirTipo(form, "password");
  };

  document.addEventListener("change", (evento) => {
    const caixa = evento.target;
    if (!caixa || !caixa.matches || !caixa.matches("[data-mostrar-senha]")) {
      return;
    }
    const form = caixa.closest("form");
    if (!form) {
      return;
    }
    definirTipo(form, caixa.checked ? "text" : "password");
  });

  document.addEventListener("submit", (evento) => {
    const form = evento.target;
    if (form && form.querySelector && form.querySelector("[data-mostrar-senha]")) {
      definirTipo(form, "password");
    }
  });

  window.addEventListener("pageshow", () => {
    document.querySelectorAll("form").forEach((form) => {
      if (form.querySelector("[data-mostrar-senha]")) {
        ocultar(form);
      }
    });
  });
})();
