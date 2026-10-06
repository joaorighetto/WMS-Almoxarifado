(() => {
  "use strict";

  const form = document.querySelector("[data-login-form]");
  if (!form) {
    return;
  }

  const submitButton = form.querySelector("[data-login-submit]");
  const submitLabel = form.querySelector("[data-login-submit-label]");

  const resetSubmitState = () => {
    form.dataset.submitting = "false";
    form.removeAttribute("aria-busy");
    submitButton.disabled = false;
    submitLabel.textContent = "Entrar";
  };

  /* O foco inicial é decidido pelo servidor (`autofocus` em um único campo, ver
     `contas/forms.py`): nenhum foco por script aqui. */

  form.addEventListener("submit", (event) => {
    if (form.dataset.submitting === "true") {
      event.preventDefault();
      return;
    }

    form.dataset.submitting = "true";
    form.setAttribute("aria-busy", "true");
    submitButton.disabled = true;
    submitLabel.textContent = "Entrando…";
  });

  /* Restaura controles ao voltar pelo histórico quando a página vem do bfcache. */
  window.addEventListener("pageshow", resetSubmitState);
})();
