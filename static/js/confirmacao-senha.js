/*
 * Checagem de divergência da confirmação de senha antes do envio — `/senha/` (WMS-Almoxarifado)
 *
 * Aprimoramento progressivo: poupa uma ida ao servidor quando a Nova senha e a Confirmação são
 * diferentes. O servidor continua sendo quem valida (sem este script, ou com ele burlado, a
 * divergência é recusada do mesmo jeito, no mesmo campo e com o mesmo texto).
 *
 * Contrato:
 *   - `data-confirmacao-senha` no `<form>`; os campos são `new_password1` e `new_password2`;
 *   - `data-mensagem-divergencia="…"` no `<form>`: o texto do erro, entregue pelo template a partir
 *     do formulário (`error_messages.password_mismatch`); o script não tem texto próprio, e sem o
 *     atributo não checa nada.
 *
 * No `submit`, com os dois campos preenchidos e diferentes: cancela o envio, mostra no bloco da
 * Confirmação o erro com a mesma estrutura do servidor
 * (`<div class="field-error" id="id_new_password2_error"><p>…</p></div>`), marca `aria-invalid`,
 * põe o id do erro no começo do `aria-describedby` do campo e foca a Confirmação. Se o erro do
 * servidor já está na página, o mesmo elemento é reaproveitado (o id nunca se duplica). Ao editar
 * qualquer um dos dois campos, o erro mostrado por este script é removido junto com `aria-invalid`,
 * a classe `field-has-error` e o id no `aria-describedby`.
 *
 * Ordem com os outros scripts do formulário: o listener é de `submit` em `document`, na fase de
 * captura, e para a propagação ao cancelar. Assim ele roda antes do listener do `<form>` de
 * `envio.js` (que nem chega a marcar "Trocando…/Definindo…") e do listener de `document` de
 * `mostrar-senha.js` (que nem chega a devolver os campos a `password`: um envio cancelado deixa a
 * caixa "Mostrar senhas" e o tipo dos campos como estavam). O valor das senhas só é comparado,
 * nunca guardado nem copiado.
 */
(() => {
  "use strict";

  const MARCA = "data-erro-cliente";

  const campos = (form) => ({
    nova: form.elements.namedItem("new_password1"),
    confirmacao: form.elements.namedItem("new_password2"),
  });

  const idsDe = (campo) => (campo.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);

  const definirIds = (campo, ids) => {
    if (ids.length) {
      campo.setAttribute("aria-describedby", ids.join(" "));
    } else {
      campo.removeAttribute("aria-describedby");
    }
  };

  const idDoErro = (campo) => `${campo.id}_error`;

  const mostrarErro = (confirmacao, mensagem) => {
    const id = idDoErro(confirmacao);
    const bloco = confirmacao.closest(".field");
    let erro = document.getElementById(id);
    if (!erro) {
      erro = document.createElement("div");
      erro.className = "field-error";
      erro.id = id;
      confirmacao.after(erro);
    }
    const texto = document.createElement("p");
    texto.textContent = mensagem;
    erro.replaceChildren(texto);
    erro.setAttribute(MARCA, "");
    if (bloco) {
      bloco.classList.add("field-has-error");
    }
    confirmacao.setAttribute("aria-invalid", "true");
    const ids = idsDe(confirmacao).filter((atual) => atual !== id);
    definirIds(confirmacao, [id, ...ids]);
  };

  const removerErro = (confirmacao) => {
    const id = idDoErro(confirmacao);
    const erro = document.getElementById(id);
    if (!erro || !erro.hasAttribute(MARCA)) {
      return;
    }
    erro.remove();
    const bloco = confirmacao.closest(".field");
    if (bloco) {
      bloco.classList.remove("field-has-error");
    }
    confirmacao.removeAttribute("aria-invalid");
    definirIds(
      confirmacao,
      idsDe(confirmacao).filter((atual) => atual !== id),
    );
  };

  document.addEventListener(
    "submit",
    (evento) => {
      const form = evento.target;
      if (!form || !form.matches || !form.matches("[data-confirmacao-senha]")) {
        return;
      }
      const mensagem = form.dataset.mensagemDivergencia;
      const { nova, confirmacao } = campos(form);
      if (!mensagem || !nova || !confirmacao) {
        return;
      }
      if (nova.value && confirmacao.value && nova.value !== confirmacao.value) {
        evento.preventDefault();
        evento.stopPropagation();
        mostrarErro(confirmacao, mensagem);
        confirmacao.focus();
      }
    },
    true,
  );

  document.addEventListener("input", (evento) => {
    const campo = evento.target;
    const form = campo && campo.form;
    if (!form || !form.matches("[data-confirmacao-senha]")) {
      return;
    }
    const { nova, confirmacao } = campos(form);
    if (confirmacao && (campo === nova || campo === confirmacao)) {
      removerErro(confirmacao);
    }
  });
})();
