/*
 * Copiar o texto de um elemento — aprimoramento progressivo genérico.
 *
 * Primeiro uso: o bloco da senha provisória exibida uma única vez
 * (`contas/templates/contas/organizacao/usuario_senha_entregue.html`).
 *
 * Contrato por atributos `data-*`:
 * - `<button data-copiar-alvo="id-do-elemento" hidden>`: o botão nasce oculto no HTML e só
 *   é revelado aqui, quando o navegador oferece `navigator.clipboard` (contexto seguro). Sem
 *   JS ou sem a API, a pessoa seleciona o texto à mão (`user-select: all` no próprio elemento).
 * - `data-copiar-ok` / `data-copiar-falha` no botão: textos do aviso, escritos num elemento
 *   `role="status"` que é o próximo irmão do botão.
 *
 * Nada é guardado: o texto é lido do elemento no momento do clique, vai direto à área de
 * transferência e não passa por atributo, armazenamento, URL nem log. O aviso nunca repete o
 * texto copiado.
 */
(() => {
  "use strict";

  const botoes = document.querySelectorAll("[data-copiar-alvo]");
  if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") {
    return;
  }

  botoes.forEach((botao) => {
    const alvo = document.getElementById(botao.dataset.copiarAlvo);
    const aviso = botao.nextElementSibling;
    if (!alvo || !aviso) {
      return;
    }

    botao.hidden = false;

    let limpar = null;
    const avisar = (texto) => {
      aviso.textContent = texto;
      window.clearTimeout(limpar);
      limpar = window.setTimeout(() => {
        aviso.textContent = "";
      }, 5000);
    };

    botao.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(alvo.textContent.trim());
        avisar(botao.dataset.copiarOk || "Copiado.");
      } catch {
        avisar(botao.dataset.copiarFalha || "Não foi possível copiar. Selecione o texto e copie.");
      }
    });
  });
})();
