<!-- SEED: established with the user before implementation, via /impeccable shape (fundação visual + revisão incremental de responsividade por papel/dispositivo), sem código, comp ou geração de imagem. Re-execute /impeccable document em modo scan assim que houver templates, CSS e componentes reais implementados, para extrair os tokens e o sidecar `.impeccable/design.json` a partir do código de fato construído. -->

---
name: WMS-Almoxarifado
description: Ferramenta operacional interna de gestão de materiais, estoque e movimentações do almoxarifado do SAEP.
---

# Design System: WMS-Almoxarifado

## Overview

**Creative North Star: "A Bancada de Trabalho Confiável"**

O WMS-Almoxarifado é uma ferramenta operacional interna, não um produto de mercado: quem a abre já sabe o que veio fazer, e a interface existe para que essa tarefa seja concluída rápido, sem ambiguidade e sem erro — como uma bancada de trabalho bem organizada, onde cada ferramenta está sempre no mesmo lugar. A personalidade é a de uma ferramenta operacional confiável, não a de um software vistoso: densidade útil, baixa carga cognitiva, comparação rápida entre registros, previsibilidade de onde cada ação mora e clareza inequívoca de estado. Hierarquia visual é resolvida por tipografia, alinhamento, spacing, bordas e superfície — nunca por decoração aplicada por cima.

Este sistema é compartilhado entre papéis com contextos operacionais muito diferentes — Solicitantes e Chefes de setor usam predominantemente celular, Funcionários do almoxarifado usam predominantemente desktop, e também operam em tablet dentro do almoxarifado. Por isso a fundação (papéis semânticos, primitives, comportamento de estado) é uma só, mas a composição e a densidade variam conscientemente por papel, tarefa e dispositivo — isto é uma decisão de produto estabelecida, não uma lacuna (ver Layout).

Rejeições visuais confirmadas: dashboards decorativos, cards como estrutura universal de conteúdo, glassmorphism, gradientes, sombras decorativas, arredondamento excessivo, animações chamativas, estética de SaaS genérico, tipografia de marketing, excesso de whitespace tratado como hierarquia. Não existe identidade institucional definida hoje (sem logotipo, sem cor oficial do órgão); nenhum valor cromático abaixo é branding aprovado — é hipótese de direção sujeita a validação visual.

**Key Characteristics:**
- Densidade útil como padrão, não como exceção.
- Estado ou seleção relevante nunca depende só de cor — sempre há uma pista não cromática adequada ao contexto.
- Ação primária previsível, no mesmo lugar, em toda superfície equivalente.
- Uma só fundação visual para mobile, tablet e desktop — composição varia, papéis e tokens não.
- Nenhuma decoração sem função operacional.

## Colors

Estratégia cromática: **Restrained** — base neutra, um único accent funcional para ação primária, cores semânticas usadas apenas para estado e significado. Todos os valores abaixo são **initial design values**: hipótese de direção para viabilizar implementação futura, não aprovados como identidade institucional e sujeitos a refinamento visual.

### Primary
- **Azul-Operação** (`#2F5D8A`, initial design value): cor de ação primária. Usada na ação visualmente dominante de cada contexto de interação e em estados de foco/seleção — nunca em áreas grandes de fundo. É o único accent funcional do sistema; dentro de um mesmo contexto, outras cores não devem competir com ele por destaque de ação.

### Neutral
- **Fundo** (`background`, `#F7F8FA`, initial design value): fundo geral da página.
- **Superfície** (`surface`, `#FFFFFF`, initial design value): fundo de tabela, formulário, modal e demais blocos de conteúdo.
- **Superfície sutil** (`surface-subtle`, `#EEF0F3`, initial design value): fundo de hover funcional, região secundária, ou realce leve sem função de estado.
- **Borda** (`border`, `#D7DBE0`, initial design value): divisores padrão entre linhas, campos e seções.
- **Borda de ênfase** (`border-strong`, `#9AA1AC`, initial design value): borda usada para marcar uma linha/região que exige atenção (ex.: linha com erro ou divergência), sempre acompanhada de texto ou badge.
- **Texto** (`text`, `#1B1E22`, initial design value): texto principal, dado tabular, título.
- **Texto secundário** (`text-muted`, `#5B6270`, initial design value): metadado, legenda, texto auxiliar.
- **Desabilitado** (`disabled`, `#B7BCC4`, initial design value): controle inativo — sempre combinado com `cursor: not-allowed` e, quando aplicável, texto explicando a razão.

### Estados semânticos
- **Sucesso** (`success`, `#2E7D46`, initial design value): confirmação de operação concluída (ex.: importação efetivada).
- **Alerta** (`warning`, `#A66A00`, initial design value): condição que merece atenção mas não bloqueia (ex.: divergência de saldo).
- **Perigo** (`danger`, `#B3261E`, initial design value): erro, recusa ou ação destrutiva/irreversível.
- **Informação** (`info`, `#3B6EA5`, initial design value): mensagem neutra de contexto, distinta do accent de ação.
- **Selecionado** (`selected`/`surface-selected`, `#E4ECF4`, initial design value): tom sutil do primary em baixa saturação, usado para linha selecionada e item de navegação ativo.
- **Foco** (`focus`, mesmo tom do Azul-Operação, initial design value): anel de foco visível em todo controle interativo — nunca removido, mesmo em uso por teclado.

### Named Rules
**The One Accent Rule.** Deve existir uma ação visualmente dominante por contexto de interação, quando houver uma ação principal clara — a tela inteira, um dialog/modal que abre seu próprio contexto, ou uma região independente da página. O uso de `primary` permanece raro e hierarquizado, evitando múltiplas ações concorrentes com o mesmo peso visual; isso não licencia vários botões primários competindo dentro do mesmo contexto.

**The No Color-Only State Rule.** Nenhum estado ou seleção relevante depende exclusivamente de cor; deve existir ao menos uma pista não cromática adequada ao contexto — texto, ícone, peso tipográfico, borda, forma, posição ou outro indicador estrutural. Para estados semânticos como erro, warning, sucesso e divergência, prefira texto explícito quando o significado não puder ser inferido inequivocamente; para estados estruturais como selecionado ou item de navegação ativo, peso, borda, posição ou outro indicador estrutural bastam, sem exigir texto redundante.

## Typography

**Fonte de UI (display/corpo/label):** stack de sistema — `system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`. Não há fonte de exibição separada: peso e contraste resolvem hierarquia antes de tamanho, e uma ferramenta operacional interna não tem hoje um ganho comprovado que justifique dependência de fonte externa (Constitution, Princípio XI — dependências com parcimônia).

**Fonte de código/identificador:** monoespaçada de sistema — `ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`, usada exclusivamente para o `CADPRO` e outros identificadores técnicos opacos do domínio, para sinalizar visualmente que não é prosa e não deve ser editado como texto livre.

**Character:** um único par funcional — sistema para tudo que é dado e interface, monoespaçada só para identificador — sem par decorativo de exibição.

### Hierarquia

Os tamanhos abaixo são a escala sugerida pelo shape original: **valor inicial sugerido**, não validado em uso real; a densidade final por contexto (desktop/tablet/celular) será confirmada durante a implementação (ver Layout).

- **Título de página** (peso semibold, ~20–22px, valor inicial sugerido): título no page header de cada superfície.
- **Título de seção** (peso semibold/médio, ~16px, valor inicial sugerido): divide blocos dentro de uma página densa (ex.: "Arquivo" vs. "Confirmação" na importação).
- **Corpo / dado tabular** (peso regular, ~14px, valor inicial sugerido): texto de tabela, formulário, conteúdo padrão. Números comparáveis (saldo, quantidade) usam `font-variant-numeric: tabular-nums` — decisão estabelecida, não sujeita a validação — para alinhar dígitos entre linhas e favorecer comparação vertical.
- **Metadado / legenda** (peso regular, ~12–13px, valor inicial sugerido, cor `text-muted`): informação auxiliar, contexto secundário de page header, timestamp.
- **Estado / badge** (peso médio, ~12px, valor inicial sugerido): rótulo curto de estado semântico.
- **Código** (`CADPRO` e identificadores): mesmo tamanho do corpo, família monoespaçada — decisão estabelecida.

### Named Rules
**The No Display Font Rule.** Nenhuma fonte de exibição decorativa é introduzida; hierarquia se resolve por peso, contraste e posição antes de tamanho.

## Layout

### Fundamento: contexto operacional por papel e dispositivo (decisão de produto estabelecida)

- **Solicitantes** → uso predominantemente em celular.
- **Chefes de setor** → uso predominantemente em celular.
- **Funcionários do almoxarifado** → uso predominantemente em desktop.
- **Funcionários do almoxarifado** → tablet também faz parte do contexto operacional dentro do almoxarifado.

Consequência direta na estratégia visual: não existe uma composição de referência única para o produto inteiro. A responsividade é orientada por **papel + fluxo**, não por um "desktop padrão" que se adapta igualmente a tudo:

- **Superfícies de Solicitante/Chefe de setor são mobile-first** (criar solicitação, consultar solicitação, acompanhar situação, aprovar/rejeitar, e os dados necessários a essas tarefas): operação confortável ao toque, leitura rápida, ação primária evidente, formulário em coluna única com campos ocupando a largura do container quando isso favorecer o toque, navegação simples, nenhuma dependência de hover, menos informação simultânea quando não for necessária à tarefa. Mobile-first não significa "tudo em card" — a representação segue o tipo de informação e o fluxo, não uma conversão automática.
- **Superfícies operacionais densas do almoxarifado são desktop-first** (catálogo de materiais, importação do SCPI e sua prévia, histórico de execuções, e futuras superfícies de movimentação/comparação em massa): densidade útil, teclado e mouse, comparação entre registros, tabelas, filtros, múltiplas colunas, produtividade repetitiva, preservação de contexto entre interações.
- **Tablet do almoxarifado é um contexto próprio**, não um desktop reduzido nem um mobile ampliado: as mesmas operações permanecem utilizáveis, com alvos de interação maiores, mais espaçamento entre controles acionáveis, filtros reorganizados, toolbar adaptativa, menos ações simultaneamente expostas quando necessário, e scroll horizontal consciente em tabela — sem virar cards automaticamente.

**The Shared Foundation Rule.** Papéis semânticos, primitives e comportamento de estado são únicos e compartilhados entre mobile, tablet e desktop. O que varia por contexto é composição e densidade, nunca a linguagem de tokens — dois design systems separados (um "mobile", um "desktop") são uma violação desta fundação.

### Densidade por contexto

Não existe uma densidade única de produto:

- **Desktop do almoxarifado** — densidade **compacta**: prioriza volume de informação, comparação, produtividade repetitiva.
- **Tablet do almoxarifado** — densidade **compacta a intermediária**: equilíbrio entre informação útil e alvo de toque confortável; não reduz permanentemente a capacidade operacional da superfície densa.
- **Celular — Solicitantes e Chefes de setor** — densidade **normal orientada à tarefa**: clareza, progressão do fluxo, toque confortável, redução de informação simultânea quando não necessária. Não se tenta reproduzir no celular a densidade de uma tabela operacional desktop.

A escala de spacing usa base 4px como direção da fundação (ex.: 4/8/12/16/24/32 — passos exatos ficam para validação em implementação). Spacing serve agrupamento, separação conceitual, densidade e alinhamento; whitespace nunca substitui hierarquia — um bloco não fica "importante" só por ter mais espaço ao redor, fica importante por peso, posição e contraste.

### App shell (desktop)

Sidebar lateral compacta é a direção aprovada para navegação em desktop, mas largura exata, `position: fixed` e comportamento definitivo de colapso **não estão fixados** — pertencem ao refinamento em implementação. O item ativo deve ser evidente, discreto e consistente — usando peso, indicador, `surface-selected` (token acima) ou outra combinação funcional; um fundo de seleção sutil é permitido, desde que não compita com o conteúdo principal.

### App shell (mobile)

A navegação de Solicitante/Chefe de setor **ainda não está definida** — não presumir sidebar só-ícone, bottom navigation, drawer ou hamburger sem evidência de fluxo suficiente. Fica registrada como decisão em aberto, a resolver quando os fluxos de solicitação/aprovação forem especificados.

### Estrutura de página

Page header com título, contexto/descrição secundária quando necessária, e ações primárias/secundárias — em desktop/largura confortável, título/contexto à esquerda e ações à direita são a direção padrão; em celular ou largura insuficiente, as ações podem quebrar, empilhar ou ocupar linha própria, sem comprimir controles só para preservar a composição desktop, mantendo a ação principal evidente e previsível. Filtros posicionados próximos ao conteúdo que afetam, em disposição adaptável por dispositivo (ver Components → Filter Bar) — nunca uma segunda coluna lateral roubando espaço de dado tabular; breadcrumbs só quando há profundidade real de navegação; área operacional aproveitando a largura disponível da tela (sem contenção estreita tipo página de marketing); páginas densas (ex.: prévia de importação) separadas por estrutura, divisor e spacing — nunca por cards empilhados.

### Tabelas — responsividade

Regra normativa, nesta ordem de preferência: (1) preservar toda coluna operacionalmente relevante; (2) ajustar largura de coluna conscientemente; (3) permitir scroll horizontal; (4) reorganizar controles externos à tabela; (5) ocultar coluna somente quando houver evidência de baixa prioridade para aquele fluxo específico. Nenhum campo (incluindo classificação recebida do SCPI) é tratado como descartável por padrão sem respaldo em specification. Tabela não vira card automaticamente por breakpoint, no tablet nem no celular — uma superfície de Solicitante pode ter composição diferente da equivalente de almoxarifado porque o *job* é diferente (poucas requisições próprias vs. milhares de materiais), nunca porque houve conversão automática.

### Touch

Ações necessárias nunca dependem de hover. Controles interativos são confortáveis ao toque nos contextos touch (tablet, celular), com dimensão mínima a validar em implementação. Densidade do desktop não é reduzida globalmente só para acomodar toque — tablet e celular variam spacing e dimensão de controle preservando os mesmos papéis semânticos.

## Elevation & Depth

O sistema é **flat por padrão**: profundidade é comunicada por tom de superfície (`background` vs. `surface` vs. `surface-subtle`) e por borda/divisor, nunca por sombra decorativa. Elementos genuinamente sobrepostos ao conteúdo — como dialog/modal e, futuramente, outros overlays funcionais quando realmente necessários — podem usar elevação mínima para comunicar sobreposição.

### Named Rules
**The Flat-By-Default Rule.** Superfícies em repouso são planas. Sombra só aparece como recurso funcional de separação em elementos genuinamente sobrepostos ao conteúdo, nunca como decoração de card, botão, tabela ou hover.

## Shapes

Cantos com raio mínimo e funcional (initial design value, ~2–4px) em botões, inputs e containers — o suficiente para não parecer bruto, nunca arredondamento pronunciado tipo app de consumo. Bordas finas (ver token `border`) são o principal recurso de separação entre linha, campo e seção. Sem clipping decorativo, sem geometria chamativa, sem `clip-path` ornamental.

## Components

Conjunto mínimo necessário para a vertical slice de referência (catálogo + importação do SCPI). Nenhum componente é antecipado para feature futura ainda não especificada.

### Buttons
- **Forma:** raio mínimo funcional (ver Shapes).
- **Primário:** `primary` como fundo, reservado à ação visualmente dominante de cada contexto de interação (tela, dialog ou região independente) — ver The One Accent Rule; uso raro e hierarquizado, sem múltiplas ações concorrentes de mesmo peso no mesmo contexto.
- **Secundário/Ghost:** borda ou texto em `text`/`border`, sem preenchimento de `primary`.
- **Destrutivo:** usa `danger`, reservado a ação de impacto real (nenhuma ainda especificada nesta feature).
- **Foco:** anel visível (`focus`) em todo estado de teclado, sem exceção.

### Table
- Superfície de primeira classe do produto, não um componente secundário.
- Densidade por contexto (ver Layout): linha de ~36–40px é **hipótese inicial para desktop**, não valor normativo — tablet pode exigir linha maior; valor definitivo fica para validação em implementação.
- Números alinhados à direita com `tabular-nums`; texto à esquerda; `CADPRO` em monoespaçada.
- Quando uma coluna for ordenável conforme os requisitos da superfície, seu cabeçalho deve oferecer a ação de ordenação e indicar claramente a direção/estado atual; sticky quando a listagem for longa.
- Truncamento de conteúdo longo: regra geral — truncar somente quando necessário para preservar densidade, sempre com uma forma previsível de consultar o valor completo (expansão, detalhe, tooltip ou outra solução apropriada ao componente/dispositivo); mecanismo técnico não fixado aqui.
- Linha em estado de erro/divergência: `border-strong` lateral + badge/texto — nunca fundo da linha inteira colorido.
- Empty state como linha única ocupando a largura da tabela; loading preserva scroll/posição.
- Ação de linha inline quando forem 1–2 ações frequentes; menu de opções reservado só a ações genuinamente raras.
- Sem zebra striping por padrão; hover só quando a linha for clicável/tiver ação.

### Status/Badge
- Rótulo curto de estado semântico (sucesso, warning, danger, info, divergência), sempre com texto — nunca só uma pastilha colorida.

### Alert
- Feedback de seção ou de página para informação, sucesso, warning ou erro que precisa de mais destaque que um badge — permanece visível até ser resolvido/dispensado quando exige ação do usuário.

### Confirmation / Dialog
- Confirmação explícita para ação de impacto (ex.: efetivar a importação após a prévia, conforme FR-044a da spec de importação) — reitera o resultado esperado antes de confirmar; pode usar elevação funcional mínima quando estiver sobreposto ao conteúdo, conforme as regras de `Elevation & Depth`.

### Inputs / Fields
- Label acima do campo; texto auxiliar abaixo, em `text-muted`; erro abaixo do campo, em `danger`, com texto (não só borda vermelha).
- Largura do campo por contexto: no desktop do almoxarifado, reflete o tipo e comprimento esperado do dado quando isso melhorar leitura e produtividade, evitando campo ocupando arbitrariamente toda a largura disponível; no celular, campo em coluna única normalmente ocupa a largura do container quando isso favorecer a operação por toque e a clareza, sem forçar largura estreita baseada no comprimento teórico do dado; no tablet, a escolha segue a composição e o fluxo da tela.
- Foco sempre visível (`focus`).

### File Upload
- Mostra nome/tamanho do arquivo selecionado antes de processar; usado no envio do CSV de importação do catálogo.

### Filter Bar
- Região de filtros posicionada próxima e antes do conteúdo que afeta — a horizontalidade não é obrigatória em todo dispositivo. Desktop: disposição predominantemente horizontal quando houver espaço. Tablet: pode quebrar em múltiplas linhas ou reorganizar controles. Celular: pode empilhar controles ou usar outra composição compacta apropriada ao fluxo. Nunca uma coluna lateral competindo com espaço de superfície tabular densa, e nunca ocultar filtro essencial só para manter a barra em uma linha.

### Pagination
- Navegação de lista grande sem carregar tudo de uma vez; obrigatória na consulta do catálogo (spec de importação, FR-042). Recomendável também no histórico de execuções por densidade e volume, consistente com o shape aprovado, ainda que a specification não fixe uma FR específica de paginação para essa superfície.

### Page Header
- Título, contexto/descrição secundária opcional. Em desktop/largura confortável, ações primárias/secundárias alinhadas à direita é a direção padrão; em celular ou largura insuficiente, as ações podem quebrar, empilhar ou ocupar linha própria — sem comprimir controles só para preservar a composição desktop. A ação principal permanece evidente e previsível em qualquer largura.

### Empty State
- Estado de ausência de resultado explícito — nunca uma lista vazia sem explicação (spec de importação, FR-043).

### Loading Indicator
- Local à região em atualização parcial (HTMX) — nunca bloqueio de página inteira para uma troca pequena.

### Navigation
- Ver Layout → App shell (desktop): sidebar como direção aprovada, detalhes de largura/colapso em aberto.
- Ver Layout → App shell (mobile): navegação de Solicitante/Chefe de setor ainda a definir.

## Do's and Don'ts

### Do:
- **Do** resolver hierarquia por peso tipográfico, alinhamento e spacing antes de recorrer a card ou sombra.
- **Do** manter papéis semânticos, primitives e comportamento de estado únicos entre mobile, tablet e desktop (The Shared Foundation Rule).
- **Do** preservar coluna de tabela por padrão e usar scroll horizontal antes de ocultar dado.
- **Do** usar `tabular-nums` para número comparável e monoespaçada para `CADPRO` e identificadores opacos.
- **Do** exigir confirmação explícita antes de ação de impacto (ex.: efetivar importação).
- **Do** garantir que nenhuma ação necessária dependa de hover, em qualquer dispositivo.
- **Do** apoiar todo estado ou seleção relevante em ao menos uma pista não cromática (texto, ícone, peso, borda, posição ou indicador estrutural); preferir texto explícito para erro, warning, sucesso e divergência quando o significado não for inequívoco.

### Don't:
- **Don't** transformar cada registro de catálogo (ou qualquer listagem densa) em card por estar em tela mobile/tablet.
- **Don't** introduzir sombra decorativa, gradiente, glassmorphism ou arredondamento pronunciado.
- **Don't** esconder ação frequente (buscar, filtrar, confirmar) atrás de menu de três pontos.
- **Don't** reduzir permanentemente a densidade do desktop para acomodar tablet ou celular.
- **Don't** criar dois design systems separados — um "mobile" e outro "desktop" — em vez de compartilhar papéis e primitives.
- **Don't** reformatar, truncar de forma destrutiva ou "limpar" o `CADPRO` ou qualquer identificador opaco do domínio (viola `INV-CATALOG-001` mesmo só na camada visual).
- **Don't** deixar erro ou exceção de importação desaparecer sozinho — o usuário depende dela para corrigir e reprocessar.
- **Don't** usar toast para informação já visível pela própria mudança de resultado (ex.: aplicar filtro não precisa de toast de confirmação).
