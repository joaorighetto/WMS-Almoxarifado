/*
 * Aviso de Caps Lock — campos de senha (login e `/senha/`, WMS-Almoxarifado)
 *
 * Aprimoramento progressivo: sem JavaScript nada aparece.
 *
 * Contrato:
 *   - `data-caps-lock` no bloco do campo (o `.field` que contém o `<input>` de senha);
 *   - dentro dele, o aviso `<p class="field-hint-atencao" aria-live="polite"
 *     data-caps-lock-aviso data-mensagem="Caps Lock está ativado.">`. Ele nasce vazio (sem
 *     altura), para que a região `aria-live` já exista quando o texto for escrito; o texto vem do
 *     atributo `data-mensagem`, nunca do script;
 *   - o script lê `getModifierState("CapsLock")` em `keydown`/`keyup` dentro do bloco, escreve a
 *     mensagem enquanto o Caps Lock estiver ativo e a apaga ao desligar e no `blur` do campo.
 *
 * Só há aviso: nada é bloqueado e o valor digitado nunca é lido. Carregado uma vez, com `defer`;
 * os listeners são delegados em `document`.
 */
(() => {
  "use strict";

  const bloco = (evento) => {
    const alvo = evento.target;
    return alvo && alvo.closest ? alvo.closest("[data-caps-lock]") : null;
  };

  const aviso = (elemento) => elemento.querySelector("[data-caps-lock-aviso]");

  const definir = (elemento, ativo) => {
    const destino = aviso(elemento);
    if (!destino) {
      return;
    }
    const texto = ativo ? destino.dataset.mensagem || "" : "";
    if (destino.textContent !== texto) {
      destino.textContent = texto;
    }
  };

  const verificar = (evento) => {
    const elemento = bloco(evento);
    if (!elemento || typeof evento.getModifierState !== "function") {
      return;
    }
    if (!evento.target.matches("input")) {
      return;
    }
    definir(elemento, evento.getModifierState("CapsLock"));
  };

  document.addEventListener("keydown", verificar);
  document.addEventListener("keyup", verificar);

  document.addEventListener("focusout", (evento) => {
    const elemento = bloco(evento);
    if (elemento) {
      definir(elemento, false);
    }
  });

  /* Restauração pelo bfcache: o estado do teclado pode ter mudado fora da página. */
  window.addEventListener("pageshow", () => {
    document.querySelectorAll("[data-caps-lock]").forEach((elemento) => definir(elemento, false));
  });
})();
