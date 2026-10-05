/*
 * Shell — tema claro/escuro e menu móvel (WMS-Almoxarifado)
 *
 * A lógica de alternância de tema é a de django-observatory 0.1.0 (commit
 * 6edda16667c8a8601670f76e3286f86bed16e37d, `app.js`: sem `data-theme` usa a preferência do
 * sistema; o botão alterna e persiste). MIT — ver THIRD-PARTY-NOTICES.md. Diferenças
 * deliberadas: chave `wms-tema` e o tema salvo é aplicado antes da primeira pintura por um
 * script inline mínimo no <head> de contas/base.html (este arquivo só cuida da alternância).
 *
 * Carregado uma vez, com `defer`, no <head> (nunca no <body>): na restauração de histórico o
 * HTMX troca o <body> inteiro e re-executa os scripts que estejam nele. Todos os listeners são
 * delegados em `document`, então sobrevivem a essa troca sem duplicar.
 *
 * Sem JavaScript, a navegação aparece aberta (o botão "Menu" só existe com `html.js`) e o
 * tema segue a preferência do sistema.
 */
(function () {
  "use strict";

  var CHAVE_TEMA = "wms-tema";
  var raiz = document.documentElement;

  function guardar(valor) {
    try {
      localStorage.setItem(CHAVE_TEMA, valor);
    } catch (e) {
      /* armazenamento indisponível: o tema vale só para esta página */
    }
  }

  function escuroAtivo() {
    var atual = raiz.getAttribute("data-theme");
    return atual
      ? atual === "dark"
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function fecharMenu(lateral, devolverFoco) {
    var botao = lateral.querySelector("[data-menu-toggle]");
    lateral.removeAttribute("data-open");
    if (botao) {
      botao.setAttribute("aria-expanded", "false");
      if (devolverFoco) botao.focus();
    }
  }

  document.addEventListener("click", function (evento) {
    var alvo = evento.target;
    if (!alvo || !alvo.closest) return;

    var tema = alvo.closest("[data-theme-toggle]");
    if (tema) {
      var proximo = escuroAtivo() ? "light" : "dark";
      raiz.setAttribute("data-theme", proximo);
      guardar(proximo);
      return;
    }

    var menu = alvo.closest("[data-menu-toggle]");
    if (menu) {
      var lateral = menu.closest(".side");
      if (!lateral) return;
      var abrir = !lateral.hasAttribute("data-open");
      if (abrir) {
        lateral.setAttribute("data-open", "");
        menu.setAttribute("aria-expanded", "true");
      } else {
        fecharMenu(lateral, false);
      }
      return;
    }

    /* "Pular para o conteúdo": telas ainda não propagadas trazem um <main> sem id; sem este
       desvio o link não encontraria destino. */
    var pular = alvo.closest("a.skip");
    if (pular) {
      var id = (pular.getAttribute("href") || "").replace(/^#/, "");
      if (id && document.getElementById(id)) return;
      var principal = document.querySelector("main");
      if (!principal) return;
      evento.preventDefault();
      principal.setAttribute("tabindex", "-1");
      principal.focus();
    }
  });

  document.addEventListener("keydown", function (evento) {
    if (evento.key !== "Escape") return;
    var aberta = document.querySelector(".side[data-open]");
    if (aberta) fecharMenu(aberta, true);
  });
})();
