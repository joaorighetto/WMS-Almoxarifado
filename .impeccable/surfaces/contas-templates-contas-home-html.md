---
version: 1
slug: "contas-templates-contas-home-html"
primary_target: "contas/templates/contas/home.html"
related_targets: ["contas/templates/contas/base.html","catalogo/templates/catalogo/consulta.html"]
---

# Shell, Home e consulta do catálogo — surface brief

Modo: Operate. Laboratório do redesign baseado no django-observatory (shell compartilhado + Home +
consulta do catálogo) antes da propagação às demais superfícies. Substitui o contrato "Tubulação e
piso industrial" (seed b7969869), que fica no histórico do git.

- Público: qualquer identidade autenticada; chefe e equipe do almoxarifado no desktop, requisitantes
  e chefes de setor no celular; administrador de sistema nas telas de organização.
- Trabalho: saber onde está e quem está logado, ir direto à tarefa permitida, localizar material
  por CADPRO/descrição e conferir saldo, trocar senha, sair.
- Conteúdo: só dado real (matrícula, setor, papéis, destinos por capability, capacidades planejadas
  filtradas). Nada de métricas, contadores, gráficos ou alertas.
- Restrições: autorização continua nas rotas; logout POST + CSRF; credencial provisória sem
  navegação; contratos HTMX da consulta intactos; CADPRO opaco; sem telemetria, Live, busca por
  linguagem, exports ou gráficos do upstream.
- Contrato detalhado: `docs/redesign-observatory/contrato.md`. Plano: `docs/redesign-observatory/plano.md`.

## Direction contract

THESIS: O WMS fala a gramática do django-observatory 0.1.0 (commit 6edda16): ferramenta de operador, sidebar de 216 px e uma coluna de trabalho larga e calma. Recusa a barra horizontal industrial incumbente e qualquer reinterpretação livre da referência.

OWN-WORLD: Fundo #f4f4f2, superfície #fcfcfb, borda 1 px #dddcd6, texto #0b0b0b/#52514e/#7b7a74, um accent #1c5cab com fundo #e3eefc; escuro #111110/#1a1a19/#383835 com accent #86b6ef. Fonte do sistema a 14 px, mono só em identificador. Painéis raio 8, controles raio 6 e 30 px, sem sombra; badges em pílula com marcador de forma (●◆■▲).

STORY: O operador vê onde está pelo item ativo, encontra só o que pode fazer e chega à tabela de materiais sem atrito, no claro ou no escuro, no desktop ou no celular.

FIRST VIEWPORT: Sidebar 216 px à esquerda (marca, Início, grupos Catálogo/Fornecedores/Estoque/Administração, conta e tema no rodapé). À direita, título 1.45rem e descrição; na consulta, filtros em linha e card com tabela compacta e paginação; na Home, tiles de identidade e cards de tarefas.

FORM: Canon fixado pelo usuário (django-observatory, interface de operador) — fora da lista sorteada; seed key 5138d9c5 registrada como canon, sorteio subordinado à fixação.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Seed e desafiantes

Seed 5138d9c5 (direction, operate). A direção é fixada pelo usuário e vence o sorteio; os seis
desafiantes (espécime de fonte variável, carteira de passagens jet-age, catálogo Factory/Saville,
parede de streaming, prancha de anuário, espécime de grade Crouwel) foram declinados nos dois eixos —
identificação do público e clareza do produto — frente a uma linguagem de operador já escolhida.
Disciplina mantida da carteira de passagens: estado que cancela em vez de desaparecer (estorno),
já garantido pelo domínio. Nenhuma outra elevação aplicada: o prompt veda reinterpretar a referência.

Build path: code-led. Não há geração de imagem; a referência de crítica são as capturas reais do
upstream (`docs/images/*.png` do commit), não um comp gerado.
