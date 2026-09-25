---
version: 1
slug: "contas-templates-contas-home-html"
primary_target: "contas/templates/contas/home.html"
related_targets: []
---

# Home autenticada — surface brief

Modo: Operate. Laboratório da nova direção visual antes da propagação a catálogo e importação.

- Público: qualquer identidade autenticada; chefe/equipe do almoxarifado no desktop, requisitantes e chefes de setor no celular.
- Trabalho: saber quem está logado (matrícula, setor, papéis), ir direto à tarefa permitida, ver o que está em preparação, sair.
- Prova/conteúdo: só dado real — matrícula, setor, papéis (002), atalhos por papel (001), capacidades planejadas do ROADMAP filtradas pela permissions-matrix. Nada de métricas, alertas, contagens ou rotas novas; não é o painel PAI.
- Restrições: links e visibilidade por papel inalterados; autorização continua nas rotas; logout POST + CSRF; placeholders sem `<a>`.

## Direction contract

THESIS: A Home é a planta de circulação do almoxarifado — o que você pode fazer aparece identificado como a própria planta identifica tubulações e corredores: faixa de identificação com rótulo e seta de fluxo, sobre piso de concreto. Recusa a grade de cards de atalho (padrão da categoria) e a caixa branca solitária (incumbente).

OWN-WORLD: Piso concreto quente (#E6E4DF), folhas brancas, texto grafite. Código de cores NR-26 como gramática semântica: azul = ação obrigatória (primário #1757B8), amarelo segurança = circulação/atual (#F2C200, só sobre grafite ou como linha de demarcação), verde/vermelho/âmbar nos estados. Barra de trabalho grafite com linha de corredor amarela. Atkinson Hyperlegible Next/Mono auto-hospedadas; raios 4/8px; sem sombra.

STORY: Quem entra entende em um olhar onde está (setor, papéis), vai direto à tarefa permitida e sabe o que ainda está em obra — sem confundir planejado com disponível.

FIRST VIEWPORT: Barra grafite 56px (marca à esquerda; matrícula e Sair à direita) com linha amarela de 4px. Abaixo, título "Início" e placa de identificação (Matrícula mono · Setor · Papéis). Depois, marcador de tubulação "Suas tarefas →" e lista única de linhas grandes (título + descrição + seta desenhada), inteiras clicáveis. Abaixo, zona "Em preparação" delimitada por fita de demarcação tracejada, itens atenuados com selo "Planejado", sem seta.

FORM: Tubulação e piso industrial — 1º da lista fundamentada do re-roll (escolha do Impeccable, aceita pelo usuário); seed key b7969869, reroll 1.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
