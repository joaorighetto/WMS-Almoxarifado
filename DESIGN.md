---
name: WMS-Almoxarifado
description: Ferramenta operacional interna de gestão de materiais, estoque e movimentações do almoxarifado do SAEP.
colors:
  primary: "#2F5D8A"
  primary-hover: "#274E74"
  background: "#E6E9ED"
  surface: "#FFFFFF"
  surface-subtle: "#EFF1F4"
  border: "#D6DAE0"
  border-frame: "#C2C8D0"
  border-strong: "#9AA1AC"
  text: "#1B1E22"
  text-muted: "#5B6270"
  disabled: "#B7BCC4"
  disabled-surface: "#DCE0E5"
  disabled-text: "#6E7480"
  success: "#236B3A"
  success-surface: "#E7F3EB"
  success-border: "#5E9B76"
  warning: "#8A5700"
  warning-surface: "#FCF3E1"
  warning-border: "#BC8B3C"
  danger: "#9E2019"
  danger-surface: "#FBEAE8"
  danger-border: "#C9756C"
  info: "#1F6572"
  info-surface: "#E3F1F3"
  info-border: "#56949D"
  selected: "#E4ECF4"
  focus: "#2F5D8A"
  ink: "#1E2833"
  ink-raised: "#29343F"
  ink-border: "#374250"
  on-ink: "#FFFFFF"
  on-ink-muted: "#C9D2DC"
  on-ink-accent: "#9CC3E6"
typography:
  metric:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.01em"
    fontFeature: "\"tnum\""
  page-title:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  section-title:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.25
  body:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
    lineHeight: 1.5
  numeric:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "\"tnum\""
  meta:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.5
  table-header:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "0.04em"
  badge:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.25
  code:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  sm: "2px"
  md: "4px"
spacing:
  space-1: "4px"
  space-2: "8px"
  space-3: "12px"
  space-4: "16px"
  space-6: "24px"
  space-8: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
    height: "44px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.surface}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
    height: "44px"
  button-primary-disabled:
    backgroundColor: "{colors.disabled-surface}"
    textColor: "{colors.disabled-text}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
    height: "44px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
    height: "44px"
  button-secondary-hover:
    backgroundColor: "{colors.surface-subtle}"
    textColor: "{colors.text}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
    height: "44px"
  button-secondary-disabled:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.disabled-text}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
    height: "44px"
  input-text:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
    width: "100%"
    height: "44px"
  field-label:
    textColor: "{colors.text}"
    typography: "{typography.label}"
  field-hint:
    textColor: "{colors.text-muted}"
    typography: "{typography.meta}"
  field-error:
    textColor: "{colors.danger}"
    typography: "{typography.meta}"
  alert-danger:
    backgroundColor: "{colors.danger-surface}"
    textColor: "{colors.danger}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "12px"
  alert-warning:
    backgroundColor: "{colors.warning-surface}"
    textColor: "{colors.warning}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "12px"
  alert-info:
    backgroundColor: "{colors.info-surface}"
    textColor: "{colors.info}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "12px"
  alert-success:
    backgroundColor: "{colors.success-surface}"
    textColor: "{colors.success}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "12px"
  badge-success:
    backgroundColor: "{colors.success-surface}"
    textColor: "{colors.success}"
    typography: "{typography.badge}"
    rounded: "{rounded.sm}"
    padding: "4px 8px"
  badge-warning:
    backgroundColor: "{colors.warning-surface}"
    textColor: "{colors.warning}"
    typography: "{typography.badge}"
    rounded: "{rounded.sm}"
    padding: "4px 8px"
  badge-danger:
    backgroundColor: "{colors.danger-surface}"
    textColor: "{colors.danger}"
    typography: "{typography.badge}"
    rounded: "{rounded.sm}"
    padding: "4px 8px"
  badge-info:
    backgroundColor: "{colors.info-surface}"
    textColor: "{colors.info}"
    typography: "{typography.badge}"
    rounded: "{rounded.sm}"
    padding: "4px 8px"
  badge-neutral:
    backgroundColor: "{colors.surface-subtle}"
    textColor: "{colors.text}"
    typography: "{typography.badge}"
    rounded: "{rounded.sm}"
    padding: "4px 8px"
  table:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    width: "100%"
  table-header-cell:
    backgroundColor: "{colors.surface-subtle}"
    textColor: "{colors.text-muted}"
    typography: "{typography.table-header}"
    padding: "8px 12px"
  table-cell:
    textColor: "{colors.text}"
    typography: "{typography.body}"
    padding: "8px 12px"
  table-cell-numeric:
    textColor: "{colors.text}"
    typography: "{typography.numeric}"
    padding: "8px 12px"
  table-cell-code:
    textColor: "{colors.text}"
    typography: "{typography.code}"
    padding: "8px 12px"
  table-row-clickable-hover:
    backgroundColor: "{colors.surface-subtle}"
  table-empty-row:
    textColor: "{colors.text-muted}"
    typography: "{typography.body}"
    padding: "24px 12px"
  pagination-link:
    textColor: "{colors.text}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "4px 8px"
    height: "36px"
  pagination-link-hover:
    backgroundColor: "{colors.surface-subtle}"
    textColor: "{colors.text}"
  pagination-link-current:
    textColor: "{colors.primary}"
    rounded: "{rounded.sm}"
    padding: "4px 8px"
    height: "36px"
  pagination-link-disabled:
    textColor: "{colors.disabled-text}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "4px 8px"
    height: "36px"
  pagination-summary:
    textColor: "{colors.text-muted}"
    typography: "{typography.meta}"
  page-header-title:
    textColor: "{colors.text}"
    typography: "{typography.page-title}"
  page-header-description:
    textColor: "{colors.text-muted}"
    typography: "{typography.body}"
  empty-state:
    textColor: "{colors.text-muted}"
    typography: "{typography.body}"
    padding: "32px 16px"
  empty-state-title:
    textColor: "{colors.text}"
  file-upload-meta:
    textColor: "{colors.text-muted}"
    typography: "{typography.meta}"
  loading-indicator:
    textColor: "{colors.text-muted}"
    typography: "{typography.meta}"
  summary-label:
    textColor: "{colors.text-muted}"
    typography: "{typography.meta}"
  summary-value:
    textColor: "{colors.text}"
    typography: "{typography.metric}"
  explanatory-note:
    textColor: "{colors.text-muted}"
    typography: "{typography.body}"
    width: "72ch"
  confirmation-bar:
    backgroundColor: "{colors.surface}"
    padding: "12px 16px"
  form-surface:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "24px 16px"
  card-surface:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "24px 16px"
---

# Design System: WMS-Almoxarifado

## Overview

**Creative North Star: "A Bancada de Trabalho Confiável"**

O WMS-Almoxarifado é uma ferramenta operacional interna, não um produto de mercado: quem a abre já sabe o que veio fazer, e a interface existe para que essa tarefa seja concluída rápido, sem ambiguidade e sem erro — como uma bancada de trabalho bem organizada, onde cada ferramenta está sempre no mesmo lugar. A personalidade é a de uma ferramenta operacional confiável, não a de um software vistoso: densidade útil, baixa carga cognitiva, comparação rápida entre registros, previsibilidade de onde cada ação mora e clareza inequívoca de estado. Hierarquia visual é resolvida por tipografia, alinhamento, spacing, bordas e superfície — nunca por decoração aplicada por cima.

Este sistema é compartilhado entre papéis com contextos operacionais muito diferentes — Solicitantes e Chefes de setor usam predominantemente celular, Funcionários do almoxarifado usam predominantemente desktop, e também operam em tablet dentro do almoxarifado. Por isso a fundação (papéis semânticos, primitives, comportamento de estado) é uma só, mas a composição e a densidade variam conscientemente por papel, tarefa e dispositivo — isto é uma decisão de produto estabelecida, não uma lacuna (ver Layout).

Rejeições visuais confirmadas: dashboards decorativos, cards como estrutura universal de conteúdo, glassmorphism, gradientes, sombras decorativas, arredondamento excessivo, animações chamativas, estética de SaaS genérico, tipografia de marketing, excesso de whitespace tratado como hierarquia. Não existe identidade institucional definida hoje (sem logotipo, sem cor oficial do órgão); nenhum valor cromático abaixo é branding aprovado — é hipótese de direção sujeita a validação visual.

Escopo de acessibilidade: as regras de estado não cromático e de foco visível abaixo são decisões deste design system, a serviço da leitura operacional — não uma promessa de conformidade. Requisitos específicos de acessibilidade (WCAG, ARIA, leitores de tela, navegação por teclado) não são adicionados por padrão; entram só quando necessários ao funcionamento correto de um componente ou quando uma feature os exigir explicitamente (Constitution).

**Key Characteristics:**
- Densidade útil como padrão, não como exceção.
- Estado ou seleção relevante nunca depende só de cor — sempre há uma pista não cromática adequada ao contexto.
- Ação primária previsível, no mesmo lugar, em toda superfície equivalente.
- Uma só fundação visual para mobile, tablet e desktop — composição varia, papéis e tokens não.
- Nenhuma decoração sem função operacional.

## Colors

Estratégia cromática: **Restrained** — base neutra, um único accent funcional para ação primária, cores semânticas usadas apenas para estado e significado. A revisão de presença visual de 2026-09-22 (`impeccable colorize`) manteve essa estratégia e corrigiu o que a tornava invisível: a rampa neutra tinha diferenças abaixo do limiar de percepção (canvas x superfície a 1,06:1) e os quatro estados semânticos dividiam o mesmo cinza, distinguindo-se só pela cor de um texto pequeno. Todos os valores abaixo estão **implementados** como custom properties em `static/css/tokens.css` (fonte única; o frontmatter acima é normativo). Eles continuam **não aprovados como identidade institucional** — o SAEP não tem logotipo nem cor oficial definidos — e permanecem sujeitos a refinamento visual; o que mudou é que deixaram de ser hipótese não escrita e passaram a ser o token real consumido pela aplicação.

### Primary
- **Azul-Operação** (`primary`, initial design value): cor de ação primária. Usada na ação visualmente dominante de cada contexto de interação, em estados de foco/seleção (anel de foco, página atual da paginação) e em links de retorno textuais — nunca em áreas grandes de fundo. É o único accent funcional do sistema; dentro de um mesmo contexto, outras cores não devem competir com ele por destaque de ação.

### Neutral
- **Fundo** (`background`, initial design value): canvas da página — deliberadamente mais escuro que a superfície de trabalho (1,22:1 contra o branco, medido). É esse degrau que faz tabela, formulário e barra de confirmação assentarem sem nenhuma sombra.
- **Superfície** (`surface`, initial design value): fundo de tabela, formulário, modal, barra de confirmação persistente e demais blocos de conteúdo.
- **Superfície sutil** (`surface-subtle`, initial design value): fundo de hover funcional, cabeçalho de tabela, fundo de alert e badge, ou realce leve sem função de estado.
- **Borda** (`border`, initial design value): divisor interno — entre linhas de tabela, campos e seções.
- **Moldura** (`border-frame`, initial design value): contorno externo de tabela, formulário isolado, barra de confirmação e faixa do page header. Um passo mais firme que o divisor interno (1,68:1 contra o branco), para a estrutura aparecer antes do conteúdo. Também é a borda do botão secundário, que precisa ler como controle tanto sobre superfície quanto sobre o canvas.
- **Borda de ênfase** (`border-strong`, initial design value): borda usada para marcar uma linha/região que é de fato uma exceção (ex.: linha rejeitada na tabela de exceções da importação), sempre acompanhada de texto na própria linha (o motivo) ou badge. Também é a borda do badge neutro.
- **Texto** (`text`, initial design value): texto principal, dado tabular, título.
- **Texto secundário** (`text-muted`, initial design value): metadado, legenda, texto auxiliar, nota explicativa.
- **Desabilitado** (`disabled`, `disabled-surface`, `disabled-text`, initial design values): controle inativo — sempre combinado com `cursor: not-allowed` e, quando aplicável, texto explicando a razão. O rótulo de qualquer controle desabilitado usa `disabled-text`, nunca `disabled` nem `surface`: o par anterior (fundo `disabled` + texto `surface`) media 1,91:1 e apagava justamente o rótulo de "Enviando…"/"Confirmando…", o momento em que o usuário mais depende de ler o botão. `disabled` permanece só como borda de controle inativo.

### Estados semânticos
Cada estado é uma **família de três papéis** — texto, superfície e borda (`success`/`success-surface`/`success-border`, e assim por diante) —, não um texto colorido sobre o cinza comum. A superfície tingida é o que torna o estado legível por visão periférica numa tela densa; o texto explícito continua sendo o que carrega o significado. Todos os pares texto/superfície ficam entre 5,53:1 e 6,74:1 (medidos no browser).

- **Sucesso** (`success`, initial design value): confirmação de operação concluída (ex.: alert de sucesso após confirmar a importação, selo "Concluída" no resultado da execução e "Sem rejeições" no histórico).
- **Alerta** (`warning`, initial design value): condição que merece atenção mas não bloqueia (ex.: mensagem de aviso de nível `warning`, selo "Com rejeições" no histórico). Divergência de saldo **não** usa este tom — é informativa (ver Components → Table).
- **Perigo** (`danger`, initial design value): erro, recusa ou ação destrutiva/irreversível. Também reforça, em peso semibold, um número que é em si a notícia ruim (ex.: rejeitados diferente de zero no histórico) — o número continua sendo a pista primária, nunca a cor sozinha.
- **Informação** (`info`, initial design value): mensagem neutra de contexto (ex.: "esta é só uma prévia, nada foi gravado"). **Azul-petróleo, não azul** (decisão do dono do produto, 2026-09-22): o valor anterior estava a 1,30:1 do `primary` e competia com a ação pelo mesmo significado cromático. Fora do eixo do azul, "contexto neutro" e "ação" deixam de se confundir, e o Azul-Operação volta a ser o único azul do sistema.
- **Selecionado** (`selected`, initial design value): tom sutil do primary em baixa saturação, reservado para linha selecionada e item de navegação ativo. Definido em `tokens.css`, ainda não consumido — nenhuma seleção de linha nem navegação existe no código.
- **Foco** (`focus`, alias do Azul-Operação em `tokens.css`, initial design value): anel de foco visível em todo controle interativo — nunca removido, mesmo em uso por teclado.

### Tinta estrutural (direção aprovada, ainda não consumida)

`ink`, `ink-raised`, `ink-border`, `on-ink`, `on-ink-muted` e `on-ink-accent` são a rampa do app shell de desktop (ver Layout → App shell). Neutra e escura de propósito: é a única área grande de cor prevista no sistema, e não pode ser `primary` — gastar o accent de ação numa moldura permanente o anularia como sinal. Definidos em `tokens.css` e **ainda não consumidos**, como `selected`, porque nenhuma navegação existe no código. Dentro dela, o anel de foco usa `on-ink-accent` (8,08:1), não `focus`, que sumiria sobre a tinta.

### Named Rules

**The One Accent Rule.** Deve existir uma ação visualmente dominante por contexto de interação, quando houver uma ação principal clara — a tela inteira, um dialog/modal que abre seu próprio contexto, ou uma região independente da página. O uso de `primary` permanece raro e hierarquizado, evitando múltiplas ações concorrentes com o mesmo peso visual; isso não licencia vários botões primários competindo dentro do mesmo contexto.

**The No Color-Only State Rule.** Nenhum estado ou seleção relevante depende exclusivamente de cor; deve existir ao menos uma pista não cromática adequada ao contexto — texto, ícone, peso tipográfico, borda, forma, posição ou outro indicador estrutural. Para estados semânticos como erro, warning, sucesso e divergência, prefira texto explícito quando o significado não puder ser inferido inequivocamente; para estados estruturais como selecionado ou item de navegação ativo, peso, borda, posição ou outro indicador estrutural bastam, sem exigir texto redundante.

## Typography

**Fonte de UI (display/corpo/label):** stack de sistema — `system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`. Não há fonte de exibição separada: peso e contraste resolvem hierarquia antes de tamanho, e uma ferramenta operacional interna não tem hoje um ganho comprovado que justifique dependência de fonte externa (Constitution, Princípio XI — dependências com parcimônia).

**Fonte de código/identificador:** monoespaçada de sistema — `ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`, usada exclusivamente para o `CADPRO` e outros identificadores técnicos opacos do domínio (ex.: SHA-256 do arquivo importado), para sinalizar visualmente que não é prosa e não deve ser editado como texto livre.

**Character:** um único par funcional — sistema para tudo que é dado e interface, monoespaçada só para identificador — sem par decorativo de exibição.

### Hierarquia

Os tamanhos abaixo estão **implementados** em `static/css/tokens.css` (valores exatos no frontmatter). A escala original escolhia sempre o passo mais baixo de cada faixa, e o resultado tinha razões de 1,25 e 1,14 entre passos vizinhos — hierarquia achatada. A revisão de 2026-09-22 abriu os dois extremos (valor de total e título de página para cima, cabeçalho de tabela para baixo) e manteve corpo, rótulo e metadado onde estavam. A densidade desktop já está aplicada às superfícies do catálogo (consulta, importação, prévia, histórico, resultado da execução), mas segue **não validada em uso real**, e nenhuma superfície mobile-first de Solicitante/Chefe de setor existe ainda (ver Layout).

- **Valor de total** (semibold, 1.75rem, 1.25, tracking -0.01em, `tabular-nums`): o número de um total de operação (resumo da prévia e do resultado da importação). É o passo mais alto da escala de propósito — o número é o elemento de maior peso da seção, por tipografia, sem card nem cor. Antes da revisão de 2026-09-22 ele empatava com o título da página.
- **Título de página** (bold, 1.5rem, altura de linha 1.25, tracking -0.01em): título no page header de cada superfície. O tracking negativo compensa o espaçamento da stack de sistema, calibrada para corpo e frouxa neste tamanho.
- **Título de seção** (semibold, 1rem, 1.25): divide blocos dentro de uma página densa (ex.: "Resumo", "Divergências de saldo", "Exceções"). Em peso médio, é também o título de um empty state.
- **Corpo / dado tabular** (regular, 0.875rem, 1.5): texto de tabela, formulário, conteúdo padrão. Números comparáveis (saldo, quantidade, totais) usam `font-variant-numeric: tabular-nums` (token `numeric`) — decisão estabelecida — para alinhar dígitos entre linhas e favorecer comparação vertical.
- **Rótulo** (médio, 0.875rem, 1.5): rótulo de campo e texto de botão.
- **Cabeçalho de tabela** (semibold, 0.75rem, 1.25, tracking +0.04em, caixa-alta, cor `text-muted`): o cabeçalho é rótulo, não dado. A ênfase é deliberadamente invertida — o dado passa a ser o elemento mais escuro e mais pesado da tabela, que é a superfície de primeira classe do produto. Pré-requisito: rótulo curto. Acima de ~3 palavras, caixa-alta atrapalha a leitura e o rótulo deve ser encurtado em vez de perder a convenção.
- **Metadado / legenda** (regular, 0.8125rem, 1.5, cor `text-muted`): informação auxiliar, dica e erro de campo, resumo da paginação, rótulo de total, timestamp.
- **Estado / badge** (semibold, 0.75rem, 1.25): rótulo curto de estado semântico. A 12px sobre superfície tingida, o peso médio lia como texto auxiliar em vez de estado.
- **Código** (`CADPRO` e identificadores): mesmo tamanho do corpo, família monoespaçada — decisão estabelecida.

Em dispositivo de ponteiro grosso (`pointer: coarse`), o texto digitado nos campos sobe para 1rem, para evitar o zoom automático do Safari ao focar — o restante da escala não muda.

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

A escala de spacing usa base 4px, implementada nos passos do frontmatter (4/8/12/16/24/32px; o nome `space-N` é N × 4px). Não há passos intermediários fora dela.

Densidade é decidida por **token**, não por número solto em cada componente: `--control-height` (44px, botão e campo em qualquer dispositivo), `--control-height-compact` (36px, controle secundário no desktop) e `--table-cell-pad-y`/`-x` (padding da célula). Sob `pointer: coarse`, só esses tokens mudam — `--control-height-compact` sobe para 44px e o padding vertical da célula vai a 12px —, num único bloco em `tokens.css`. É o que mantém a variação por dispositivo governável sem duplicar regra por componente (The Shared Foundation Rule). Spacing serve agrupamento, separação conceitual, densidade e alinhamento; whitespace nunca substitui hierarquia — um bloco não fica "importante" só por ter mais espaço ao redor, fica importante por peso, posição e contraste.

### App shell (desktop)

Sidebar lateral compacta é a direção aprovada para navegação em desktop, mas largura exata, `position: fixed` e comportamento definitivo de colapso **não estão fixados** — pertencem ao refinamento em implementação. O item ativo deve ser evidente, discreto e consistente — usando peso, indicador, `selected` (token acima) ou outra combinação funcional; um fundo de seleção sutil é permitido, desde que não compita com o conteúdo principal. Nenhum app shell existe ainda no código: enquanto isso, as superfícies do catálogo levam um link textual de retorno ("← Início", "← Envio") acima do page header, e a página inicial lista os atalhos permitidos ao papel como botões secundários — solução provisória, não a navegação definitiva.

### App shell (mobile)

A navegação de Solicitante/Chefe de setor **ainda não está definida** — não presumir sidebar só-ícone, bottom navigation, drawer ou hamburger sem evidência de fluxo suficiente. Fica registrada como decisão em aberto, a resolver quando os fluxos de solicitação/aprovação forem especificados.

### Estrutura de página

Page header com título, contexto/descrição secundária quando necessária, e ações primárias/secundárias — em desktop/largura confortável, título/contexto à esquerda e ações à direita são a direção padrão; em celular ou largura insuficiente, as ações podem quebrar, empilhar ou ocupar linha própria, sem comprimir controles só para preservar a composição desktop, mantendo a ação principal evidente e previsível. Filtros posicionados próximos ao conteúdo que afetam, em disposição adaptável por dispositivo (ver Components → Filter Bar) — nunca uma segunda coluna lateral roubando espaço de dado tabular; breadcrumbs só quando há profundidade real de navegação; área operacional larga, centralizada e com teto generoso (hoje 1120px, com respiro lateral de 16px e vertical de 24px) — nunca contenção estreita tipo página de marketing; um formulário simples e isolado, como o envio do CSV, usa coluna mais contida (640px) **e** ganha superfície própria — `surface`, moldura de 1px em `border-frame`, raio `md`, sem sombra. A regra anterior o proibia, mas foi escrita quando canvas e superfície eram indistinguíveis (1,06:1): com o canvas atual, a única tela cujo trabalho é uma ação de impacto real ficava inteiramente cinza, sem nenhuma referência de superfície sob os próprios controles (correção do gate visual, 2026-09-22). Páginas densas (ex.: prévia de importação, resultado da execução) são separadas em seções por divisor fino no topo + 24px de spacing — nunca por cards empilhados; a primeira seção dispensa o divisor, já separada do page header pela borda dele.

### Tabelas — responsividade

Regra normativa, nesta ordem de preferência: (1) preservar toda coluna operacionalmente relevante; (2) ajustar largura de coluna conscientemente; (3) permitir scroll horizontal; (4) reorganizar controles externos à tabela; (5) ocultar coluna somente quando houver evidência de baixa prioridade para aquele fluxo específico. Nenhum campo (incluindo classificação recebida do SCPI) é tratado como descartável por padrão sem respaldo em specification. Tabela não vira card automaticamente por breakpoint, no tablet nem no celular — uma superfície de Solicitante pode ter composição diferente da equivalente de almoxarifado porque o *job* é diferente (poucas requisições próprias vs. milhares de materiais), nunca porque houve conversão automática.

### Touch

Ações necessárias nunca dependem de hover. Controles interativos são confortáveis ao toque nos contextos touch (tablet, celular): botões e campos têm altura mínima de 44px em qualquer dispositivo; controles mais compactos no desktop (link de paginação, 32px) e o padding vertical das células de tabela crescem só sob `pointer: coarse` (paginação para 44px, célula de 8px para 12px). Densidade do desktop não é reduzida globalmente só para acomodar toque — tablet e celular variam spacing e dimensão de controle preservando os mesmos papéis semânticos.

## Elevation & Depth

O sistema é **flat por padrão**: profundidade é comunicada por tom de superfície (`background` vs. `surface` vs. `surface-subtle`) e por borda/divisor, nunca por sombra decorativa. Nenhuma sombra existe hoje no código. Para que isso funcione de fato, a rampa precisa ter degraus perceptíveis e a moldura precisa ser mais firme que o divisor interno: canvas contra superfície a 1,22:1 e `border-frame` contra superfície a 1,68:1, contra 1,06:1 e 1,39:1 da fundação anterior, em que a profundidade existia no documento e não na tela. Elementos genuinamente sobrepostos ao conteúdo — como dialog/modal e, futuramente, outros overlays funcionais quando realmente necessários — podem usar elevação mínima para comunicar sobreposição. Elementos que apenas grudam na viewport durante a rolagem (cabeçalho fixo de tabela, barra de confirmação persistente) continuam planos: separam-se do conteúdo por fundo opaco e borda fina, não por sombra.

### Named Rules
**The Flat-By-Default Rule.** Superfícies em repouso são planas. Sombra só aparece como recurso funcional de separação em elementos genuinamente sobrepostos ao conteúdo, nunca como decoração de card, botão, tabela ou hover.

## Shapes

Cantos com raio mínimo e funcional: 2px (`rounded.sm`) em botões, campos, alerts, badges, links de paginação e no contorno da tabela; 4px (`rounded.md`) só nos containers isolados das telas de entrada e início — o suficiente para não parecer bruto, nunca arredondamento pronunciado tipo app de consumo. A única forma circular é o spinner do indicador de carregamento. Bordas finas de 1px (ver token `border`) são o principal recurso de separação entre linha, campo e seção; a borda lateral de 3px em `border-strong` é reservada à linha de exceção. Sem clipping decorativo, sem geometria chamativa, sem `clip-path` ornamental.

## Components

Conjunto mínimo necessário para a vertical slice de referência (catálogo + importação do SCPI). Nenhum componente é antecipado para feature futura ainda não especificada.

**Estado de implementação** (extraído do código ao fim da feature `001-importacao-catalogo-materiais`): Buttons, Inputs / Fields, Alert, Table, Status/Badge, File Upload, Filter Bar, Pagination, Page Header, Empty State e Loading Indicator existem de fato em `static/css/components.css` — primitivos de projeto, compartilhados entre páginas, nunca duplicados por tela. A paginação tem também um parcial de template reutilizável (`catalogo/templates/catalogo/_paginacao.html`). Os padrões de composição (resumo de totais, nota explicativa, barra de confirmação persistente, superfície de formulário isolado) vivem por enquanto em `catalogo/static/catalogo/css/catalogo.css`, porque só o catálogo os usa; ao serem reutilizados por outra feature, sobem para `components.css` sem mudar de forma. `Confirmation / Dialog` existe só na forma não modal descrita abaixo, e `Navigation` permanece **não implementada**.

### Buttons
- **Forma:** raio mínimo funcional (ver Shapes); altura mínima de 44px; rótulo em peso médio.
- **Primário** (`.btn .btn-primary`): `primary` como fundo, reservado à ação visualmente dominante de cada contexto de interação (tela, dialog ou região independente) — ver The One Accent Rule; uso raro e hierarquizado, sem múltiplas ações concorrentes de mesmo peso no mesmo contexto. Raro não é ausente: onde há uma ação principal clara, ela é primária ("Importar catálogo" no histórico, "Nova importação" no resultado da execução) — deixar toda ação em ghost não é aplicar a regra, é não decidir. Hover/active em `primary-hover`. Desabilitado: fundo `disabled-surface`, rótulo `disabled-text`, `cursor: not-allowed`.
- **Secundário/Ghost** (`.btn .btn-secondary`): fundo `surface`, borda `border-frame`, texto `text`; hover em `surface-subtle`. O fundo explícito e a moldura não são decoração: com a borda `border` sobre o canvas atual o controle media 1,15:1 e desaparecia fora de uma superfície branca. Desabilitado: rótulo em `disabled-text`. Também é a aparência de links que agem como ação (ex.: "Nova importação", "Limpar", atalhos da página inicial) e do gatilho do File Upload.
- **Destrutivo:** usa `danger`, reservado a ação de impacto real (nenhuma ainda especificada nesta feature).
- **Foco:** anel visível (`focus`, 2px, afastado 2px) em todo estado de teclado, sem exceção.
- **Processando:** ao enviar um formulário de efeito real, o botão fica desabilitado e troca o rótulo pelo gerúndio da ação ("Enviando…", "Confirmando…", "Entrando…") — bloqueia o duplo envio e sinaliza estado por texto. Sem JS, o formulário continua enviando normalmente.

### Table
- Superfície de primeira classe do produto, não um componente secundário. Estrutura: `.table-wrapper` (borda fina + raio `sm`, scroll horizontal consciente) contendo `.table`.
- Estrutura do wrapper: moldura de 1px em `border-frame` (não `border`, que é o divisor interno) + raio `sm`.
- Cabeçalho em `surface-subtle`, como **rótulo**: 12px semibold em caixa-alta com tracking, cor `text-muted`, e borda inferior de 2px em `border-strong` separando rótulo de dado (ver Typography → Cabeçalho de tabela). Células com padding `--table-cell-pad-y`/`-x` (8px × 12px no desktop, vertical a 12px sob `pointer: coarse`), divisor inferior em `border`, alinhadas pelo topo.
- Altura de linha: ~38px quando cada célula tem uma linha de texto (caso do detalhe da execução). Numa tabela cuja célula empilha dois elementos — a classificação da consulta do catálogo — a linha real fica em ~61px (medido no browser). A densidade compacta é a do padding, não uma altura garantida: célula composta custa altura, e isso é decisão de composição de cada superfície.
- `.table-cell-numeric`: números alinhados à direita com `tabular-nums` e sem quebra, aplicado tanto no `th` quanto no `td` da coluna. Texto à esquerda.
- `.table-cell-code`: `CADPRO` e identificadores em monoespaçada, sem quebra, nunca reformatados.
- `.table-sticky-header`: cabeçalho fixo quando a listagem for longa. Aplicado ao wrapper, dá a ele um scrollport vertical próprio (altura máxima de 60% da viewport) — sem isso `position: sticky` não tem contra o que colar. Wrapper sem essa classe (ex.: tabela vazia) rola com a página. Em contexto de toque ou tela estreita, o scrollport vertical próprio é desligado e a tabela rola com a página (só a rolagem horizontal fica no wrapper): rolagem dentro de rolagem no celular é pior que perder o cabeçalho fixo (decisão do dono do produto, 2026-09-22).
- `.table-row-error`: **só para exceções** (ex.: linha rejeitada da importação) — borda lateral de 3px em `border-strong` na primeira célula + o motivo em texto na própria linha; nunca fundo da linha inteira colorido.
- **Divergência de saldo é informativa, não exceção.** A tabela de divergências não usa `.table-row-error` nem selo por linha: marcar toda linha com ênfase de erro anularia a ênfase e contradiria a nota que declara a divergência não acionável ali. O sinal da diferença (`+`/`−`), em peso semibold, é o diferenciador; uma nota explicativa acima da tabela declara a convenção de sinal e o escopo.
- `.table-empty-row`: ausência de resultado como linha única ocupando a largura da tabela (`colspan` total), texto `text-muted` com padding 24px × 12px — usada quando há colunas e filtros a preservar como referência (ex.: consulta filtrada sem resultado). Leva título e descrição com as mesmas classes do Empty State. Loading preserva scroll/posição.
- Truncamento de conteúdo longo: truncar somente quando necessário para preservar densidade, sempre com uma forma previsível de consultar o valor completo. Implementado hoje como `<details>` nativo (resumo de até 60 caracteres, texto completo ao expandir, quebras de linha preservadas), sem JS e sem alterar o dado.
- `.table-row-clickable`: linha com ação própria ganha `cursor: pointer` e hover em `surface-subtle`; a navegação é sempre um `<a>` real numa célula (a linha inteira só estende o clique como aprimoramento, sem bloquear seleção de texto).
- Quando uma coluna for ordenável conforme os requisitos da superfície, seu cabeçalho deve oferecer a ação de ordenação e indicar claramente a direção/estado atual. Em uso na consulta do catálogo (FR-042a): o rótulo do cabeçalho é um link real (navegação sem JS, troca parcial por HTMX), a coluna vigente expõe `aria-sort` e um indicador de direção que não depende só de cor. O indicador é um único par de setas (acima/abaixo), sempre colado ao rótulo: em coluna não vigente as duas setas ficam neutras; na vigente, a seta da direção atual é enfatizada (em `primary`, opaca) e a outra esmaece — a mesma forma nos três estados, sem trocar de glifo. O `<th>` vigente ganha ainda borda inferior de 2px em `primary` (pista estrutural). O link ocupa a célula inteira do cabeçalho. A ordem vigente também é dita em texto no resumo da paginação ("· ordenado por saldo, decrescente"), para continuar visível quando a coluna estiver fora da tela.
- Coluna de estado: quando uma listagem distingue execuções/registros por desfecho (ex.: o histórico de importações), o estado vai numa coluna própria com `.badge` e **texto explícito**, perto do início da linha — nunca só um número que o usuário precise comparar mentalmente com os vizinhos. O rótulo é o par mínimo que distingue de fato ("Sem rejeições"/"Com rejeições"), não uma palavra que toda linha compartilha. Um número que é em si a notícia ruim ganha peso semibold + `danger` na própria célula, continuando a pista primária.
- Ação de linha inline quando forem 1–2 ações frequentes; menu de opções reservado só a ações genuinamente raras.
- Sem zebra striping.

### Status/Badge
- Rótulo curto de estado semântico (`.badge` + `.badge-success`/`-warning`/`-danger`/`-info`/`-neutral`), sempre com texto — nunca só uma pastilha colorida. Superfície, borda e texto da própria família semântica (o neutro usa `surface-subtle`, `border-strong` e `text`), peso semibold, padding 4px × 8px, `white-space: nowrap`.
- O rótulo cabe numa linha. Um selo que quebra dentro da própria borda é sinal de rótulo longo demais, não de largura insuficiente: encurte o texto preservando a distinção (ver Table → coluna de estado).
- Uso atual: selo "Concluída" (`badge-success`) ao lado do título do resultado da execução, alinhado ao meio do título — persiste o estado depois que a mensagem de sucesso some na navegação seguinte.
- Não usar badge para marcar linha de divergência de saldo (ver Table).

### Alert
- Feedback de seção ou de página para informação, sucesso, warning ou erro que precisa de mais destaque que um badge (`.alert` + `.alert-danger`/`-warning`/`-info`/`-success`): superfície, borda de 1px e texto da própria família semântica, padding 12px, raio `sm`; o conteúdo é sempre uma frase explícita. Sem barra lateral colorida: a superfície tingida já separa o alerta do que está em volta, e uma faixa de cor acima de 1px em callout é decoração.
- `alert-success` é a confirmação da importação efetivada; `alert-info` marca contexto neutro (prévia ainda não gravada, prévia pendente de uma sessão anterior); `alert-danger` cobre recusa de login, erro de formulário e falha de rede na atualização parcial (exibido sem apagar os resultados anteriores).
- Mensagens de sistema permanecem visíveis até a próxima navegação — nunca somem sozinhas por tempo — e nunca são usadas como toast para um resultado que já é visível pela própria mudança de tela.

### Confirmation / Dialog
- Confirmação explícita para ação de impacto (ex.: efetivar a importação após a prévia, conforme FR-044a da spec de importação) — reitera o resultado esperado antes de confirmar. Implementada hoje **sem modal**: a própria prévia é o contexto de confirmação, e o rótulo do botão primário repete o resultado ("Confirmar importação: N inseridos, M atualizados"), ao lado de "Cancelar" secundário. Um dialog sobreposto, se vier a existir, pode usar elevação funcional mínima conforme `Elevation & Depth`.
- **Barra de confirmação persistente** (`.catalogo-confirmacao-sticky`): quando a página que antecede a confirmação pode ser longa, o mesmo par de ações fica disponível numa barra `position: sticky; bottom: 0` (nunca `fixed`) — no fluxo da página, fundo `surface`, borda superior fina, padding vertical de 12px, **sem sombra**. Ela não substitui a seção final de confirmação; é o mesmo par, disponível mais cedo. Abaixo de 480px, os botões empilham e ocupam a largura.

### Inputs / Fields
- Label acima do campo (peso médio); texto auxiliar abaixo (`.field-hint`, metadado em `text-muted`); erro abaixo do campo (`.field-error`, metadado em `danger`) com texto — o campo com erro (`.field-has-error` no wrapper) ganha borda `danger`, nunca só a borda.
- Campo de texto: fundo `surface`, borda `border`, raio `sm`, padding 8px × 12px, altura mínima de 44px.
- Largura do campo por contexto: no desktop do almoxarifado, reflete o tipo e comprimento esperado do dado quando isso melhorar leitura e produtividade, evitando campo ocupando arbitrariamente toda a largura disponível; no celular, campo em coluna única normalmente ocupa a largura do container quando isso favorecer a operação por toque e a clareza, sem forçar largura estreita baseada no comprimento teórico do dado; no tablet, a escolha segue a composição e o fluxo da tela.
- Foco sempre visível (`focus`).

### File Upload
- Usado no envio do CSV de importação do catálogo. O input nativo de arquivo fica **oculto só visualmente** (nunca `display: none`, continua no formulário e focável); um `<label for>` com aparência de botão secundário ("Escolher arquivo") abre o seletor nativo sem JS, e o anel de foco do input é transferido para esse rótulo.
- Ao lado, `.file-upload-meta` (metadado em `text-muted`) mostra o nome e o tamanho do arquivo escolhido antes de processar; nasce com o texto em pt-BR "Nenhum arquivo selecionado." — o texto nativo do widget segue o idioma do navegador e não pode ser traduzido, por isso é substituído.
- Dica e erro seguem Inputs / Fields.

### Filter Bar
- Região de filtros posicionada próxima e antes do conteúdo que afeta — a horizontalidade não é obrigatória em todo dispositivo. Desktop: disposição predominantemente horizontal quando houver espaço. Tablet: pode quebrar em múltiplas linhas ou reorganizar controles. Celular: pode empilhar controles ou usar outra composição compacta apropriada ao fluxo. Nunca uma coluna lateral competindo com espaço de superfície tabular densa, e nunca ocultar filtro essencial só para manter a barra em uma linha.
- Implementação (`.filter-bar`): cada filtro é um `.field` que cresce lado a lado (base 220px, mínimo 160px), com as ações em `.filter-bar-actions` ao fim (primária "Buscar" + secundária "Limpar"). Quebra naturalmente por `flex-wrap`; até 640px vira coluna única, com campos e ações ocupando a largura.
- **Alinhamento pelo topo:** a barra usa `align-items: flex-start`, para que rótulo alinhe com rótulo e campo com campo mesmo quando só um filtro exibe dica ou erro abaixo. Como as ações não têm rótulo, a partir de 641px recebem uma compensação de topo equivalente a uma linha de rótulo + o gap do campo — nunca alinhamento pela base.

### Pagination
- Navegação de lista grande sem carregar tudo de uma vez; em uso na consulta do catálogo (FR-042), no histórico de execuções e em cada seção paginada da prévia e do resultado da execução.
- **Anterior / páginas numeradas / Próxima**, com reticências (`…`) no lugar dos intervalos distantes da página atual — primeira e última página sempre acessíveis, para continuar utilizável com milhares de itens (decisão do dono do produto, 2026-09-22; substitui a regra anterior de só Anterior/Próxima). À esquerda, um resumo em metadado ("Página X de Y — N no total"); à direita, os controles com borda fina, raio `sm`, mínimo de 32px (44px sob `pointer: coarse`). A página atual não é clicável e se marca por peso semibold + borda e texto em `primary`; o controle indisponível usa o rótulo em `disabled-text`, sem ação — o mesmo token de qualquer controle desabilitado do sistema (`disabled` sozinho media 1,57:1 contra o canvas); a reticência é texto, não controle, e mais estreita que um alvo de toque. Em tela estreita (≤640px), mostra só um vizinho de cada lado da página atual, com os números numa linha e Anterior/Próxima juntos na linha de baixo, dividindo a largura. Com uma página só, aparece apenas o resumo, sem controles. O total usa separador de milhar e o substantivo no plural correto ("3.408 materiais").
- Um único parcial de template (`_paginacao.html`) atende todas as listas. Os links preservam todos os demais parâmetros da URL — filtros e a página de outras seções paginadas na mesma tela —, trocando só o parâmetro da própria seção. Com âncora opcional, a navegação volta à própria seção em vez do topo da página; em região atualizada por HTMX, a troca é parcial.

### Page Header
- Título, contexto/descrição secundária opcional (`.page-header-description`, corpo em `text-muted`) e ações (`.page-header-actions`). Em desktop/largura confortável, ações alinhadas à direita; abaixo de 480px as ações ocupam linha própria, com os botões dividindo a largura — sem comprimir controles só para preservar a composição desktop. A ação principal permanece evidente e previsível em qualquer largura.
- Separado do conteúdo por borda inferior fina em `border-frame` e 24px de spacing, nunca por card ou sombra. Um badge de estado pode acompanhar o título.

### Empty State
- Estado de ausência de resultado explícito — nunca uma lista vazia sem explicação (spec de importação, FR-043).
- `.empty-state`: bloco fora de tabela, padding 32px × 16px, título em tamanho de título de seção (peso médio, `text`) + descrição em corpo (`text-muted`) dizendo por que está vazio ou o que fazer. Usado quando uma seção ou página inteira não tem nenhum registro e não há colunas a preservar (ex.: histórico sem execuções, seção sem divergências). Dentro de uma tabela com filtros, use `.table-empty-row`.

### Loading Indicator
- Local à região em atualização parcial (HTMX) — nunca bloqueio de página inteira para uma troca pequena.
- `.loading-indicator`: spinner de 14px (borda `border` com o arco em `primary`) + texto em metadado `text-muted` ("Carregando resultados…"). Fica numa linha com altura reservada entre os filtros e a tabela, para a página não saltar quando ele aparece; a visibilidade é alternada pelo próprio HTMX, sem JS de projeto. Com `prefers-reduced-motion`, o spinner para de girar e o texto continua.
- Para envio de formulário, o equivalente local é o estado "Processando" do próprio botão (ver Buttons).

### Resumo de totais
- Padrão de composição para os totais de uma operação (hoje: prévia e resultado da importação): lista de pares rótulo/valor lado a lado, rótulo em metadado `text-muted` acima do valor no tamanho `metric` (1.75rem), semibold, `tabular-nums` — o número é o elemento de maior peso da seção, por tipografia, sem card nem cor. Itens separados por divisor vertical fino e 24px.
- Um detalhe secundário de um total (ex.: "(N com alteração)") segue o valor em metadado `text-muted`, nunca como segundo total de mesmo peso.
- Um valor que **não entra na soma** dos demais (ex.: "Ausentes do arquivo") fica num item separado por espaço adicional **e** tem a relação declarada por extenso numa nota explicativa logo abaixo — nunca só pelo espaçamento.

### Superfície de formulário isolado
- Um formulário simples que ocupa a tela sozinho (hoje o envio do CSV, `.catalogo-form`) recebe superfície `surface`, moldura de 1px em `border-frame`, raio `md` e padding 24px × 16px — **sem sombra**. Não é um card de conteúdo nem uma estrutura universal: é a aplicação, a uma tela sem nenhuma outra superfície, do mesmo degrau de profundidade que a tabela usa (ver Layout → Estrutura de página).
- Listagem densa continua sem essa moldura por fora: a superfície dela é a própria tabela.

### Nota explicativa
- Texto corrido em corpo `text-muted`, limitado a 72ch, colocado antes do conteúdo que explica (ex.: convenção de sinal da divergência, o que "Ausentes do arquivo" significa). Não é um alert: não exige ação nem denota erro. Ênfase interna em `<strong>` só na consequência que o usuário precisa reter ("não altera o saldo do WMS").

### Navigation
- Ver Layout → App shell (desktop): sidebar como direção aprovada, detalhes de largura/colapso em aberto; hoje só há o link textual de retorno provisório.
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
- **Do** reservar a marcação de exceção de linha (`border-strong` lateral) às linhas que são de fato exceção; em tabela informativa, deixe o próprio dado (sinal, peso) diferenciar.
- **Do** reutilizar o parcial de paginação e os primitivos de `components.css` em vez de recriar a composição por tela.
- **Do** dar a cada estado semântico a sua família completa (texto + superfície + borda) — quatro retângulos cinza distinguidos só pela cor do texto não são estado legível numa tela densa.
- **Do** re-derivar contraste de borda e de rótulo desabilitado contra **os dois** fundos em que o controle aparece (superfície e canvas) sempre que a rampa neutra mudar.
- **Do** promover a primária a ação principal de cada tela quando ela existe e é clara — a One Accent Rule limita o número de acentos, não proíbe usar o accent.
- **Do** suprimir zero decimal irrelevante (`722`, não `722,000`) preservando a parte fracionária quando ela existir de fato — o ruído sai, o dado não.

### Don't:
- **Don't** transformar cada registro de catálogo (ou qualquer listagem densa) em card por estar em tela mobile/tablet.
- **Don't** introduzir sombra decorativa, gradiente, glassmorphism ou arredondamento pronunciado.
- **Don't** esconder ação frequente (buscar, filtrar, confirmar) atrás de menu de três pontos.
- **Don't** reduzir permanentemente a densidade do desktop para acomodar tablet ou celular.
- **Don't** criar dois design systems separados — um "mobile" e outro "desktop" — em vez de compartilhar papéis e primitives.
- **Don't** reformatar, truncar de forma destrutiva ou "limpar" o `CADPRO` ou qualquer identificador opaco do domínio (viola `INV-CATALOG-001` mesmo só na camada visual).
- **Don't** deixar erro ou exceção de importação desaparecer sozinho — o usuário depende dela para corrigir e reprocessar.
- **Don't** usar toast para informação já visível pela própria mudança de resultado (ex.: aplicar filtro não precisa de toast de confirmação).
- **Don't** marcar toda linha de uma tabela com selo ou borda de erro — ênfase universal se anula (caso da divergência de saldo).
- **Don't** usar barra lateral colorida acima de 1px em alert, callout ou item de lista — a `border-strong` lateral de 3px é exclusiva da linha que é de fato exceção.
- **Don't** gastar `primary` em decoração, moldura permanente ou área grande de fundo; o app shell escuro usa a rampa `ink`, que é neutra justamente por isso.
- **Don't** deixar um rótulo de cabeçalho de tabela crescer além de ~3 palavras mantendo a caixa-alta — encurte o rótulo em vez de abandonar a convenção.
