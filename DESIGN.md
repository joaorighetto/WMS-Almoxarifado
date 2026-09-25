---
name: WMS-Almoxarifado
description: Ferramenta operacional interna de gestão de materiais, estoque e movimentações do almoxarifado do SAEP.
colors:
  primary: "#1757B8"
  primary-hover: "#11468F"
  background: "#E6E4DF"
  surface: "#FFFFFF"
  surface-subtle: "#F2F1EE"
  border: "#D9D6CF"
  border-frame: "#BFBBB2"
  border-strong: "#8E8A80"
  text: "#1C1B19"
  text-muted: "#5C5A55"
  disabled: "#B0ABA1"
  disabled-surface: "#DFDDD8"
  disabled-text: "#595751"
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
  selected: "#E3ECF8"
  focus: "#1757B8"
  signal: "#F2C200"
  ink: "#1E1E1C"
  ink-raised: "#2A2A27"
  on-ink: "#FFFFFF"
  on-ink-muted: "#C9C7C1"
  on-ink-accent: "#F2C200"
typography:
  metric:
    fontFamily: "\"Atkinson Hyperlegible Next\", system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.01em"
    fontFeature: "\"tnum\""
  page-title:
    fontFamily: "\"Atkinson Hyperlegible Next\", system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  section-title:
    fontFamily: "\"Atkinson Hyperlegible Next\", system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.25
  section-marker:
    fontFamily: "\"Atkinson Hyperlegible Next\", system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "0.04em"
  body:
    fontFamily: "\"Atkinson Hyperlegible Next\", system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "\"Atkinson Hyperlegible Next\", system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
    lineHeight: 1.5
  numeric:
    fontFamily: "\"Atkinson Hyperlegible Next\", system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "\"tnum\""
  meta:
    fontFamily: "\"Atkinson Hyperlegible Next\", system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.5
  table-header:
    fontFamily: "\"Atkinson Hyperlegible Next\", system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "0.04em"
  badge:
    fontFamily: "\"Atkinson Hyperlegible Next\", system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.25
  code:
    fontFamily: "\"Atkinson Hyperlegible Mono\", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  code-meta:
    fontFamily: "\"Atkinson Hyperlegible Mono\", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  sm: "4px"
  md: "8px"
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
  badge-planned:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-muted}"
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
  table-cell-numeric-attention:
    textColor: "{colors.warning}"
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
  summary-value-attention:
    textColor: "{colors.warning}"
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
  appbar:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
    height: "56px"
  appbar-brand:
    textColor: "{colors.on-ink}"
    typography: "{typography.section-title}"
  appbar-matricula:
    textColor: "{colors.on-ink-muted}"
    typography: "{typography.code-meta}"
  appbar-logout:
    textColor: "{colors.on-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "4px 12px"
    height: "44px"
  appbar-logout-hover:
    backgroundColor: "{colors.ink-raised}"
    textColor: "{colors.on-ink}"
  section-marker:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
    typography: "{typography.section-marker}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
  section-marker-arrow:
    textColor: "{colors.on-ink-accent}"
    size: "14px"
  section-marker-attached:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
    typography: "{typography.section-marker}"
    padding: "8px 12px"
  section-marker-muted:
    textColor: "{colors.text-muted}"
    typography: "{typography.section-marker}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
  back-link:
    textColor: "{colors.primary}"
    typography: "{typography.meta}"
    height: "44px"
  back-link-arrow:
    textColor: "{colors.primary}"
    size: "14px"
  task-row:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.section-title}"
    rounded: "{rounded.md}"
    padding: "16px"
    height: "56px"
  task-row-hover:
    backgroundColor: "{colors.surface-subtle}"
  task-row-description:
    textColor: "{colors.text-muted}"
    typography: "{typography.body}"
  task-row-arrow:
    textColor: "{colors.primary}"
    size: "20px"
  id-plate:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "16px"
  id-plate-label:
    textColor: "{colors.text-muted}"
    typography: "{typography.meta}"
  planned-zone:
    backgroundColor: "{colors.surface-subtle}"
    textColor: "{colors.text-muted}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "16px"
  planned-zone-item-title:
    textColor: "{colors.text-muted}"
    typography: "{typography.label}"
---

# Design System: WMS-Almoxarifado

## Overview

**Creative North Star: "Tubulação e Piso Industrial"**

O WMS-Almoxarifado é lido como a própria planta do almoxarifado: piso de concreto quente, folhas brancas de trabalho assentadas sobre ele, texto grafite, e o que está em circulação identificado como a indústria identifica tubulações e corredores — faixa de identificação escura com rótulo e seta de fluxo, linha de demarcação amarela, fita zebrada onde há obra. O código de cores de segurança NR-26 não é ornamento importado: é a gramática semântica do sistema. Azul é ação obrigatória, amarelo é circulação e demarcação, verde, vermelho e âmbar são estado. Quem abre a ferramenta já sabe o que veio fazer; a interface existe para que isso aconteça rápido, sem ambiguidade e sem erro.

O mundo substitui a fundação anterior ("A Bancada de Trabalho Confiável", azul-acinzentada, fonte do sistema, raios de 2/4px), mas não as regras operacionais dela: densidade útil, uma só fundação para todos os papéis e dispositivos, estado nunca só por cor, superfícies planas. Hierarquia continua resolvida por tipografia, alinhamento, spacing, borda e tom de superfície. A composição nova cobre a Home autenticada, as cinco telas do catálogo (consulta, envio, prévia, histórico e execução) e o login: a barra de trabalho em toda tela autenticada, a faixa de identidade no login, os marcadores de tubulação, o retorno contextual e, na Home, a lista de tarefas e a zona "Em preparação". Ver "Estado de validação" em Layout.

Rejeições visuais confirmadas: dashboards decorativos, grade de cards iguais como estrutura, eyebrow acima de título, glassmorphism, gradiente de cor suave, sombra decorativa, arredondamento pronunciado, animação chamativa, estética de SaaS genérico, tipografia de marketing, whitespace tratado como hierarquia. Não existe identidade institucional do SAEP (sem logotipo, sem cor oficial); a paleta é a do mundo escolhido, não branding aprovado. Escopo de acessibilidade: as regras de estado não cromático, contraste e foco visível abaixo são decisões deste design system a serviço da leitura operacional, não promessa de conformidade; requisitos específicos entram quando uma feature os exigir (Constitution).

**Key Characteristics:**
- Piso concreto quente, folhas brancas, tinta grafite: profundidade por tom e moldura, nunca por sombra.
- Cor de segurança NR-26 como significado, nunca como decoração.
- Uma família legível auto-hospedada, igual em Windows, Android e Linux; mono só para dado e identificador.
- O que está disponível ganha a faixa grafite, e a seta de fluxo só quando leva a algum lugar; o que está planejado fica atrás da fita, atenuado e sem link.
- Densidade útil como padrão; uma só fundação para celular, tablet e desktop.

## Colors

Estratégia **Restrained** dentro de uma gramática de sinalização industrial: base neutra quente, um único accent de ação (azul), amarelo de segurança restrito a demarcação sobre ou junto da tinta grafite, e famílias semânticas só para estado. `static/css/tokens.css` é a fonte única; o frontmatter espelha seus valores e é normativo.

### Primary
- **Azul Ação Obrigatória** (`primary`; hover/pressionado em `primary-hover`): o azul NR-26 de "ação obrigatória". Fundo da ação dominante de um contexto, anel de foco (`focus` é alias dele), página atual da paginação, seta de ordenação vigente, cursor de digitação, o traço da seta desenhada de cada linha de tarefa disponível e o texto e a seta do retorno contextual. Branco sobre ele mede 6,79:1 (9,14:1 no hover); como texto, 6,79:1 sobre a folha e 5,35:1 sobre o piso. Nunca área grande de fundo, nunca moldura permanente.

### Secondary
- **Amarelo Segurança** (`signal` e `on-ink-accent`, mesmo valor, papéis distintos): circulação e demarcação. `signal` é **linha**: a linha de corredor de 4px sob a barra de trabalho e sob a faixa de identidade do login, e a fita zebrada da zona "Em preparação", sobre qualquer fundo. `on-ink-accent` é **texto/ícone sobre tinta**: a seta de fluxo do marcador de seção e o anel de foco dentro da barra de trabalho (9,93:1 sobre `ink`). Sobre branco mede 1,68:1: nunca é texto, ícone ou preenchimento de controle sobre fundo claro.

### Neutral
- **Piso Concreto** (`background`): canvas da página, deliberadamente mais escuro que a folha (1,27:1 contra `surface`) para tabela, formulário, placa e lista assentarem sem sombra.
- **Folha Branca** (`surface`): tabela, formulário, placa de identificação, lista de tarefas, barra de confirmação.
- **Concreto Claro** (`surface-subtle`): hover funcional, cabeçalho de tabela, badge neutro, corpo da zona "Em preparação".
- **Divisor** (`border`): entre linhas de tabela, linhas de tarefa, itens planejados e campos.
- **Moldura** (`border-frame`): contorno externo de tabela, placa, lista de tarefas, formulário isolado, caixa de login, page header, barra de confirmação e botão secundário. Mede 1,91:1 sobre a folha e 1,51:1 sobre o piso: a estrutura aparece antes do conteúdo.
- **Borda de Ênfase** (`border-strong`): linha de exceção de tabela, cabeçalho de tabela (2px), badge neutro, contorno tracejado de `badge-planned` e do marcador atenuado, e o contorno do "Sair" sobre a faixa grafite (4,85:1 sobre `ink`, 4,18:1 sobre `ink-raised`).
- **Tinta Grafite** (`text`): texto principal e dado; 17,2:1 sobre a folha, 13,6:1 sobre o piso.
- **Grafite Atenuado** (`text-muted`): metadado, legenda, descrição, rótulo de cabeçalho; 6,89:1 sobre a folha, 5,42:1 sobre o piso.
- **Desabilitado** (`disabled` só como borda de controle inativo; `disabled-surface` + `disabled-text` para fundo e rótulo, 5,32:1): sempre com `cursor: not-allowed` e, quando aplicável, o gerúndio da ação ("Enviando…").

### Tinta estrutural
- **Grafite de Faixa** (`ink`, `ink-raised`, `on-ink`, `on-ink-muted`): a única área grande de cor do sistema, consumida pela barra de trabalho, pela faixa de identidade do login e pelo marcador de seção disponível. Neutra de propósito: gastar o azul de ação numa faixa permanente o anularia como sinal. `on-ink` (branco) mede 16,7:1 sobre `ink`; `on-ink-muted` mede 9,88:1; `ink-raised` é o hover de controle sobre a faixa. Contorno de controle sobre a faixa usa `border-strong` (4,85:1 sobre `ink`): uma borda grafite própria mediria só 1,46:1 e não existe como token.

### Estados semânticos
Cada estado é uma família de três papéis (texto, superfície, borda), não texto colorido sobre o cinza comum; os pares texto/superfície medem entre 5,53:1 e 6,74:1.
- **Verde Condição Segura** (`success`): operação concluída.
- **Âmbar Atenção** (`warning`): condição que merece atenção sem bloquear. Inclui a rejeição de linhas numa importação (decisão do dono do produto: rejeição é atenção, não erro): o total de rejeitados diferente de zero aparece em `warning` semibold no resumo da prévia e da execução e na célula do histórico, ao lado do selo "Com rejeições" (`badge-warning`). Como texto, mede 6,10:1 sobre a folha e 4,80:1 sobre o piso.
- **Vermelho Perigo** (`danger`): erro, recusa, ação destrutiva.
- **Petróleo Informação** (`info`): contexto neutro. Petróleo, não azul, para "contexto" e "ação" não se confundirem.
- **Seleção** (`selected`): hoje só no `::selection` de texto; reservado a linha selecionada e item de navegação ativo quando existirem.

### Named Rules

**The NR-26 Grammar Rule.** Cada cor de segurança tem um só significado em todo o sistema: azul é ação, amarelo é circulação/demarcação, verde/âmbar/vermelho são estado. Uma cor usada fora do próprio significado é um erro, mesmo que "combine".

**The One Accent Rule.** Por contexto de interação (tela, dialog ou região independente) existe no máximo uma ação preenchida em `primary`, quando houver uma ação principal clara. Onde ela existe, é primária: deixar tudo em secundário não é aplicar a regra, é não decidir. Fora do preenchimento, o azul aparece só como sinal de ação pequeno (traço da seta de tarefa, página atual, seta de ordenação), nunca competindo como segundo botão.

**The Yellow-On-Ink Rule.** O amarelo de segurança só existe sobre a tinta grafite ou como linha de demarcação. Nunca é texto, ícone, preenchimento de botão ou fundo sobre superfície clara.

**The No Color-Only State Rule.** Nenhum estado ou seleção relevante depende só de cor: há sempre uma pista não cromática (texto, peso, borda, forma, posição). Estados semânticos preferem texto explícito; estados estruturais (página atual, coluna ordenada, item disponível vs. planejado) podem usar peso, borda, forma ou presença/ausência de seta.

## Typography

**Fonte de UI (título, corpo, rótulo):** Atkinson Hyperlegible Next, variável (wght 200–800), com fallback `system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`.
**Fonte de dado/identificador:** Atkinson Hyperlegible Mono, variável, com fallback `ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`.

Ambas auto-hospedadas em `static/vendor/fonts/` (woff2 variável, subset latino, cerca de 52 KB somadas, licença OFL ao lado de cada arquivo), declaradas em `static/css/fonts.css` com `font-display: swap`, sem CDN. Aprovadas pelo usuário por dois motivos operacionais: renderização igual em Windows, Android e Linux, e desambiguação de 0/O e 1/l/I, que importa em CADPRO e matrícula.

**Character:** um par funcional, não um par de exibição. A Next carrega tudo que é interface; a Mono sinaliza "isto é dado, não prosa".

### Hierarquia
- **Valor de total** (semibold, 1.75rem, 1.25, tracking -0.01em, `tabular-nums`): o número de um total de operação; o elemento de maior peso da seção, por tipografia.
- **Título de página** (bold, 1.5rem, 1.25, tracking -0.01em): título de cada superfície ("Início", page header).
- **Título de seção** (semibold, 1rem, 1.25): divide blocos em página densa; também é o título de cada linha de tarefa e a marca da barra de trabalho. Em peso médio, título de empty state.
- **Marcador de seção** (semibold, 1rem, 1.25, caixa-alta, tracking +0.04em): o rótulo da faixa de identificação. É o próprio `<h2>` da seção, nunca um rótulo acima de outro título.
- **Corpo / dado tabular** (regular, 0.875rem, 1.5): tabela, formulário, descrição. Número comparável usa `tabular-nums`.
- **Rótulo** (médio, 0.875rem, 1.5): rótulo de campo, texto de botão, título de item planejado.
- **Cabeçalho de tabela** (semibold, 0.75rem, 1.25, tracking +0.04em, caixa-alta, `text-muted`): rótulo, não dado; no máximo ~3 palavras.
- **Metadado** (regular, 0.8125rem, 1.5, `text-muted`): dica, erro de campo, resumo de paginação, rótulo da placa de identificação, descrição de item planejado.
- **Estado / badge** (semibold, 0.75rem, 1.25).
- **Código** (Mono, 0.875rem): CADPRO, SHA-256, matrícula na placa e o texto digitado no campo de matrícula do login (só a família muda; tamanho e altura seguem o campo). **Código compacto** (Mono, 0.8125rem): matrícula na barra de trabalho.

Sob `pointer: coarse`, o texto digitado nos campos sobe para 1rem (evita o zoom automático do Safari); o resto da escala não muda.

### Named Rules

**The Legible Pair Rule.** O sistema usa uma família legível auto-hospedada (Atkinson Hyperlegible Next e Mono) e nenhuma outra. Não se acrescenta fonte de exibição, fonte de CDN nem terceira família; hierarquia se resolve por peso, caixa e posição antes de tamanho. Substitui a antiga No Display Font Rule.

**The Mono-Is-Data Rule.** A Mono é exclusiva de dado e identificador opaco (CADPRO, matrícula, hash). Nunca em título, rótulo, botão ou prosa.

## Layout

### Fundamento: contexto operacional por papel e dispositivo (decisão de produto estabelecida)

- **Solicitantes** e **Chefes de setor** → predominantemente celular.
- **Funcionários do almoxarifado** → predominantemente desktop, e também tablet dentro do almoxarifado.

Não existe composição de referência única. Superfícies de Solicitante/Chefe de setor são **mobile-first** (toque confortável, ação primária evidente, coluna única, nada dependente de hover, menos informação simultânea; mobile-first não é "tudo em card"). Superfícies operacionais densas do almoxarifado são **desktop-first** (tabelas, filtros, múltiplas colunas, comparação, teclado e mouse). O **tablet** é contexto próprio: mesmas operações, alvos maiores, filtros reorganizados, scroll horizontal consciente em tabela, sem virar card.

**The Shared Foundation Rule.** Papéis semânticos, primitives e comportamento de estado são únicos entre celular, tablet e desktop. Varia a composição e a densidade, nunca a linguagem de tokens. Dois design systems ("mobile" e "desktop") violam esta fundação.

### Densidade por contexto

- **Desktop do almoxarifado:** compacta.
- **Tablet do almoxarifado:** compacta a intermediária, sem reduzir permanentemente a capacidade da superfície densa.
- **Celular (Solicitantes, Chefes de setor):** normal, orientada à tarefa.

Spacing em base 4px (4/8/12/16/24/32px; `space-N` = N × 4px), sem passos fora da escala. Densidade é decidida por token: `--control-height` (44px, botão e campo em qualquer dispositivo), `--control-height-compact` (36px, controle secundário no desktop) e `--table-cell-pad-y`/`-x` (8 × 12px). Sob `pointer: coarse`, só esses tokens mudam, num único bloco de `tokens.css`: o compacto sobe para 44px e o padding vertical da célula para 12px. Whitespace nunca substitui hierarquia.

### App shell: barra de trabalho

A barra de trabalho grafite no topo (ver Components → Navigation) **substitui a sidebar lateral** prevista pela fundação anterior. Com poucos destinos, uma faixa horizontal não rouba largura das tabelas, que são a superfície de primeira classe do produto. Ela é a mesma em celular e desktop e aparece em toda tela autenticada: declarada uma única vez no template base, só para usuário autenticado (o login tem, no lugar dela, a faixa de identidade: ver Components → Navigation); a Home sobrescreve o bloco apenas para ocultar a matrícula compacta. A altura de conteúdo é o token `--appbar-height` (56px; 48px abaixo de 480px), sem contar a linha de corredor de 4px; o `html` compensa a barra sticky com `scroll-padding-top` igual a essa altura + 4px, para âncora de seção ou paginação e foco de teclado não ficarem sob ela. Marca à esquerda, matrícula e "Sair" à direita. A marca é o retorno global à Home; não existe mais link textual de volta ao Início nas telas. A navegação específica de Solicitante/Chefe de setor, quando houver mais destinos, continua em aberto.

### Estrutura de página

Todas as telas seguem o mesmo modelo de duas caixas (Home, catálogo e login): a página carrega só o respiro, 16px lateral (respeitando `safe-area-inset`) e 24px no topo / 32px no fim, sem teto; um container filho centraliza o conteúdo com teto de 1120px, ou 640px para formulário simples e isolado (envio do CSV), ou 360px para a caixa de login. O conteúdo começa sempre 24px abaixo da faixa, nunca centralizado na vertical: no celular o teclado virtual não reduz o viewport de layout, e uma caixa centralizada nele ficaria sob o teclado. O teto é do conteúdo, não da caixa com padding: a barra de trabalho embute o mesmo cálculo, e por isso o título de página das telas largas começa exatamente no mesmo x da marca. Page header: título/contexto à esquerda e ações à direita no desktop; abaixo de 480px as ações ganham linha própria e dividem a largura. Filtros ficam próximos e antes do conteúdo que afetam, nunca em coluna lateral.

Páginas densas se dividem em seções separadas só por 24px de espaço; a primeira não recebe nem isso, já separada do page header pela borda dele. Onde a seção abre com marcador de tubulação, a própria faixa grafite é o separador: não há divisor fino entre seções, e nunca cards empilhados. Estado vazio solto numa seção (fora de moldura) perde o padding próprio, lateral e vertical: alinha com o marcador e a tabela, e o ritmo até a próxima seção continua em 24px.

Na Home: título, depois uma grade de uma coluna que a partir de 900px vira `conteúdo | 320px` (tarefas à esquerda, placa de identificação à direita, por posição na grade, sem mudar a ordem do DOM: no celular a placa vem antes das tarefas). Superfícies lado a lado alinham pela borda da superfície, não pelo marcador de seção: a seção de tarefas repassa suas duas linhas (marcador | lista) por `subgrid`, e a placa ocupa só a da lista. A zona "Em preparação" vem abaixo, em largura total, a 32px.

### Tabelas: responsividade

Nesta ordem: (1) preservar toda coluna operacionalmente relevante; (2) ajustar largura de coluna; (3) scroll horizontal; (4) reorganizar controles externos; (5) ocultar coluna só com evidência de baixa prioridade para aquele fluxo. Tabela nunca vira card por breakpoint. O passo 2 inclui a ordem das colunas: o dado que decide o fluxo vem cedo, para ficar visível antes do scroll no celular. Na consulta do catálogo a ordem é Código, Descrição, Saldo, Unidade, Classificação, Detalhamento: o Saldo vem logo após a identificação do material porque é o que o requisitante procura no celular.

### Touch

**The No Hover Dependency Rule.** Nenhuma ação necessária depende de hover. Realce de hover é bônus de ponteiro fino: em componente novo, fica dentro de `@media (hover: hover)` para não "prender" após um toque (como na lista de tarefas da Home e na linha clicável de tabela). Botões e campos têm 44px em qualquer dispositivo; controles compactos do desktop crescem só sob `pointer: coarse`.

### Estado de validação

- A composição do mundo novo está implementada e revisada na Home (desktop e celular, chefe e requisitante) e nas cinco telas do catálogo: consulta, envio, prévia, histórico e execução. Todas recebem a barra de trabalho; prévia e execução, os marcadores de tubulação e o retorno contextual.
- O login está recomposto e revisado (desktop 1440 e celular 390 com toque; vazio, erro de credencial, erro de campo, "Entrando…" e foco): faixa de identidade no topo, caixa ao topo como folha emoldurada, matrícula em Mono. Depois de um erro de credencial, a orientação de recuperação nomeia o Setor de Almoxarifado e o e-mail dele (`mailto:`, em `primary` e sublinhado).
- A densidade das tabelas foi medida com a Atkinson: linha simples de ~38px, linha composta de ~62px, Filter Bar alinhada e cabeçalhos sem quebra a 1440px.
- Tablet continua em aberto: nem a composição das telas densas nem o app shell foram validados nesse contexto. A navegação de Solicitante/Chefe de setor com mais destinos também não está definida.

## Elevation & Depth

Nenhuma sombra existe no código. Profundidade é o piso de concreto sob a folha branca (1,27:1), a moldura mais firme que o divisor interno, e a faixa grafite. Elementos que grudam na viewport (barra de trabalho no topo, cabeçalho fixo de tabela, barra de confirmação no rodapé) usam `position: sticky`, nunca `fixed`, e se separam por fundo opaco e borda: a barra de trabalho pela linha amarela de 4px, as demais por borda fina de 1px. Um dialog genuinamente sobreposto, se vier a existir, pode usar elevação funcional mínima.

### Named Rules

**The Flat-By-Default Rule.** Superfícies em repouso são planas. Sombra só aparece como separação funcional de um elemento genuinamente sobreposto ao conteúdo, nunca em card, botão, tabela, faixa ou hover.

## Shapes

Cantos pequenos e funcionais, um degrau acima da fundação anterior. **4px** (`rounded.sm`) em controles e peças pequenas: botão, campo, alert, badge, link de paginação, contorno de tabela, marcador de seção, "Sair" e o topo da fita zebrada. **8px** (`rounded.md`) em containers isolados: placa de identificação, lista de tarefas, zona "Em preparação", formulário isolado, caixa de login. Quando um marcador de seção encosta numa superfície (`-attached`: a lista de tarefas ou a moldura de uma tabela), os cantos que se tocam ficam retos dos dois lados: o marcador perde os cantos inferiores e a superfície perde só o canto superior esquerdo, para a faixa ler como presa ao tubo. Formas circulares só nos spinners.

Bordas de 1px separam; exceções deliberadas: a borda de 2px do cabeçalho de tabela e da coluna ordenada, a lateral de 3px em `border-strong` da linha de exceção, e a linha de corredor de 4px da barra de trabalho. Tracejado de 1px é exclusivo do que é **planejado** (selo e marcador atenuado). O único preenchimento padronizado é a fita zebrada da zona "Em preparação": listras diagonais a 135°, `signal` e `ink` alternados a cada ~10px, 6px de altura, com paradas duras. É sinal de demarcação, não gradiente.

## Components

Primitivos compartilhados vivem em `static/css/components.css` e nunca são duplicados por tela. Padrões de composição usados por uma só feature vivem no CSS dela (`catalogo.css`, `home.css`) e sobem para `components.css` sem mudar de forma quando outra feature os reutilizar.

### Buttons
- **Forma:** 4px, altura mínima de 44px, rótulo em peso médio, sem sublinhado mesmo quando é `<a>`.
- **Primário:** fundo `primary`, rótulo `surface`, borda da mesma cor; hover/pressionado em `primary-hover`. Uma por contexto (The One Accent Rule). Desabilitado: `disabled-surface` + `disabled-text`, `cursor: not-allowed`.
- **Secundário:** fundo `surface`, moldura `border-frame`, texto `text`; hover em `surface-subtle`. Lê como controle tanto sobre a folha quanto sobre o piso. Também é a aparência de link-ação e do gatilho do File Upload.
- **Destrutivo:** `danger`, reservado a ação de impacto real (nenhuma especificada ainda).
- **Foco:** anel de 2px em `focus`, afastado 2px, em todo controle; sobre `ink`, o anel vira `on-ink-accent`.
- **Processando:** o botão de envio de efeito real fica desabilitado e troca o rótulo pelo gerúndio ("Enviando…", "Confirmando…", "Entrando…"). Sem JS, o formulário envia normalmente.

### Chips (Badge)
- **Estilo:** `.badge` + `-success`/`-warning`/`-danger`/`-info`/`-neutral`: superfície, borda de 1px e texto da própria família, semibold 12px, padding 4 × 8px, 4px, sem quebra. Sempre com texto. O neutro (`surface-subtle`, `border-strong`, `text`) marca papéis na placa de identificação.
- **Planejado** (`.badge-planned`): fundo `surface`, borda **tracejada** em `border-strong`, texto `text-muted`, rótulo "Planejado". Marca algo que ainda não existe no sistema, não um valor de dado; o tracejado é o que o distingue do neutro.
- Rótulo que quebra dentro do selo é rótulo longo demais: encurte preservando a distinção. Não usar badge para marcar linha de divergência de saldo.

### Cards / Containers
Não há card como estrutura universal. Há quatro superfícies isoladas, todas `surface` + moldura de 1px em `border-frame` + 8px, sem sombra: a **placa de identificação** da Home (pares rótulo/valor em grade `auto-fit` de colunas ≥130px, rótulo em metadado acima do valor, "Papéis" ocupando a linha inteira, padding 16px), a **lista de tarefas**, o **formulário isolado** (envio do CSV, padding 24 × 16px) e a **caixa de login** (360px, padding 24 × 16px; 32 × 24px a partir de 480px; subtítulo e linha de recuperação com `text-wrap: pretty` para não deixar palavra sozinha). Listagem densa não ganha moldura por fora: a superfície dela é a própria tabela.

### Inputs / Fields
- **Estilo:** label acima (peso médio), campo `surface` com borda `border`, 4px, padding 8 × 12px, altura mínima de 44px; dica abaixo em metadado `text-muted`.
- **Foco:** anel `focus` sempre visível.
- **Erro:** texto em `danger` abaixo do campo e borda `danger` no campo (via `.field-has-error` no wrapper), nunca só a borda.
- **Largura:** no desktop reflete o comprimento esperado do dado; no celular ocupa a largura do container.

### Navigation
- **Barra de trabalho** (`.appbar`, parcial `contas/_barra_trabalho.html`): faixa `ink` sticky no topo, linha de corredor de 4px em `signal` na borda inferior, conteúdo com o mesmo teto de 1120px da página. Marca "Almoxarifado SAEP" em `on-ink`, título de seção; na Home ela é o item atual (`aria-current`, sem link), em outras telas vira link para a Home, sublinhado no hover/foco. À direita, matrícula em Mono 13px `on-ink-muted` (páginas com placa própria a ocultam abaixo de 900px, via `esconde_matricula_compacta`) e "Sair": botão de formulário POST + CSRF, contorno de 1px em `border-strong`, texto `on-ink`, 4px, alvo de 44px, hover em `ink-raised`. Nunca preenchido de `primary` nem de amarelo. Presente em toda tela autenticada (ver Layout → App shell).
- **Retorno contextual** (`.back-link`, em `components.css`): link acima do page header para a tela de origem quando ela **não** é a Home (prévia → "Envio"; execução → "Histórico de importações"). Texto em metadado `primary`, seta para a esquerda em SVG desenhado (14px, traço 1.75, o mesmo traço da seta de fluxo espelhado, `aria-hidden`), 4px entre os dois, alvo de 44px de altura sem inflar o texto, 16px abaixo antes do page header, sublinhado no hover e no foco. Não é botão. O retorno à Home é sempre a marca da barra, nunca um back-link.
- **Faixa de identidade** (login, `.appbar.login-band`): a mesma faixa `ink` com linha de corredor `signal`, altura e x da marca da barra de trabalho, reaproveitando os primitivos `.appbar`/`.appbar-inner`/`.appbar-brand`. Só a marca, como texto: nunca link, nunca `aria-current`, sem matrícula, sem "Sair" e sem seta de fluxo (não leva a lugar algum). Não é sticky: no login nada rola por baixo dela. É o que ancora a tela anônima no mesmo mundo da Home, sem logo nem identidade inventada.
- Destinos adicionais na barra, estado ativo por item e comportamento com muitos destinos ainda não existem.

### Section Marker (marcador de tubulação)
- O `<h2>` da seção como faixa de identificação de tubo: `ink`, texto `on-ink` em caixa-alta semibold com tracking, padding 8 × 12px, 4px, dimensionado ao conteúdo (etiqueta, não banner), 16px antes do conteúdo. Três variantes, três significados:
  - **Cheio com seta:** a seção leva a algum lugar ("Suas tarefas", uma lista de destinos). Leva a **seta de fluxo** SVG desenhada (14px, traço 1.75, `on-ink-accent`), `aria-hidden`.
  - **Cheio sem seta:** seção de leitura, disponível mas sem destino (nas telas densas: "Resumo", "Execução", "Divergências de saldo (N)", "Exceções (N)", "Alterações cadastrais (N)"). A contagem entre parênteses faz parte do rótulo.
  - **`-muted`:** para o que ainda não existe ("Em preparação"): sem fundo, contorno tracejado em `border-strong`, texto `text-muted`, **nunca** com seta.
- **`-attached`:** encosta na superfície viva renderizada logo abaixo dele (a lista de tarefas, ou a moldura da tabela com `.table-wrapper-marker-attached`): cantos inferiores retos e sem margem; a superfície replica o canto reto sob ele. Só quando a superfície vem imediatamente depois: com uma nota entre o marcador e a tabela, ou no estado vazio (sem tabela), o marcador fica simples.

**The Available-Versus-Planned Rule.** O fundo grafite pertence só ao que está disponível. O que é planejado fica atenuado, tracejado, sem seta, sem link e sem cursor de clique. Planejado nunca pode parecer clicável nem disponível.

**The Flow Arrow Rule.** A seta de fluxo afirma que a seção leva a algum lugar; ela não é decoração do marcador. Faixa cheia com seta = leva a algum lugar; faixa cheia sem seta = seção de leitura; `-muted` = planejado. Seta numa seção de leitura promete um destino que não existe.

### Lista de tarefas
- Uma única superfície branca com divisores de 1px entre linhas, não uma grade de cards. Cada linha é um `<a>` que ocupa a linha inteira (mínimo 56px, padding 16px): título com **verbo primeiro** ("Consultar catálogo de materiais") em título de seção semibold, descrição de uma frase em corpo `text-muted`, e à direita a seta SVG desenhada (20px, `primary`).
- Hover (`surface-subtle` e a seta desliza 3px, 0,18s ease-out) só dentro de `@media (hover: hover)`; o foco por teclado desloca a seta sempre. Com `prefers-reduced-motion`, sem transição.
- Visibilidade por papel é conveniência; a autorização continua na rota. Sem nenhuma tarefa, um empty state com o mesmo canto reto ocupa o lugar da lista.

### Em preparação
- Zona abaixo das tarefas para capacidades planejadas do ROADMAP, **filtradas por papel na view**. A única demarcação é a fita zebrada superior (6px); o corpo é `surface-subtle` com borda `border` e cantos inferiores de 8px, padding 16px.
- Dentro: marcador `-muted`, nota curta em `text-muted` (até 72ch), lista atenuada (título em rótulo `text-muted`, descrição em metadado, divisor de 1px entre itens, duas colunas de lista a partir de 640px) com o selo "Planejado" em cada item. Sem link, sem seta.
- Nunca vira métrica, contagem, alerta ou promessa de data.

### Table
- Superfície de primeira classe. `.table-wrapper`: moldura de 1px em `border-frame`, 4px, scroll horizontal consciente.
- Cabeçalho como rótulo: `surface-subtle`, 12px semibold caixa-alta com tracking em `text-muted`, borda inferior de 2px em `border-strong`. Células com padding por token (8 × 12px; 12px vertical sob toque), divisor `border`, alinhadas pelo topo. Sem zebra.
- Linha de ~38px com uma linha de texto; célula composta custa altura, e isso é decisão de composição.
- `.table-cell-numeric`: à direita, `tabular-nums`, sem quebra, no `th` e no `td`. `.table-cell-code`: Mono, sem quebra, **nunca reformatado**.
- `.table-sticky-header`: scrollport próprio de 60vh no desktop; desligado sob `pointer: coarse` ou até 768px (rolagem dentro de rolagem no celular é pior que perder o cabeçalho fixo).
- `.table-row-error`: só para exceção real, lateral de 3px em `border-strong` + motivo em texto na linha; nunca fundo colorido. Divergência de saldo é informativa: sinal (`+`/`−`) em semibold e nota explicativa, sem marcar linha.
- `.table-empty-row`: linha única com `colspan` total, padding 24 × 12px, título e descrição do Empty State.
- Coluna ordenável: rótulo é link real que cobre o `th`; `aria-sort` na vigente; indicador SVG de par de setas (neutras na não vigente; a da direção atual em `primary`, a outra a 40%); borda inferior de 2px em `primary` no `th` vigente; ordem também dita em texto no resumo da paginação.
- Coluna de estado com `.badge` e texto explícito perto do início da linha. Conteúdo longo truncado só com forma previsível de ver o todo (`<details>` nativo).
- `.table-row-clickable`: `cursor: pointer`, hover em `surface-subtle` só dentro de `@media (hover: hover)`, a navegação é sempre um `<a>` real numa célula.
- Número de atenção numa célula (rejeitados diferente de zero no histórico): `warning` semibold na própria célula numérica, acompanhado do selo `badge-warning` na coluna de situação; zero fica sem ênfase.

### Pagination
- Anterior / números / Próxima, com reticências nos intervalos distantes; primeira e última sempre acessíveis. Resumo em metadado à esquerda ("Página X de Y — N no total", separador de milhar, plural correto).
- Links com borda fina, 4px, mínimo de 36px (44px sob toque). Página atual: semibold + borda e texto `primary`, não clicável, `aria-current`. Indisponível: `disabled-text`, sem ação. Reticência é texto, não controle.
- Até 640px: um vizinho de cada lado, números numa linha e Anterior/Próxima juntos embaixo dividindo a largura. Uma página só: só o resumo.
- Um parcial único (`_paginacao.html`) preserva os demais parâmetros da URL e pode ancorar na própria seção.

### Filter Bar
- Antes do conteúdo que afeta. Campos crescem lado a lado (base 220px, mínimo 160px), ações ao fim (primária "Buscar" + secundária "Limpar"); quebra por `flex-wrap`; até 640px vira coluna única de largura total.
- Alinhamento pelo topo; a partir de 641px as ações recebem compensação de topo igual a uma linha de rótulo + gap. Nunca coluna lateral, nunca esconder filtro essencial.

### Alert
- `.alert` + `-danger`/`-warning`/`-info`/`-success`: superfície, borda de 1px e texto da família, padding 12px, 4px, conteúdo sempre em frase explícita e curta. A faixa ocupa a largura da coluna e o parágrafo acompanha a faixa, sem teto de 72ch (limitar só o texto deixaria faixa tingida vazia). Sem barra lateral colorida.
- Mensagens de sistema ficam visíveis até a próxima navegação; nunca somem por tempo e nunca viram toast para resultado já visível.

### Page Header
- Título, descrição opcional (corpo `text-muted`, até 70ch) e ações. Separado do conteúdo por borda inferior em `border-frame` + 24px. Um badge de estado pode acompanhar o título. A Home usa o mesmo estilo de título sem a faixa do page header.

### Empty State
- Nunca uma lista vazia sem explicação. `.empty-state`: padding 32 × 16px, título em tamanho de título de seção (peso médio, `text`) + descrição (até 72ch) dizendo por que está vazio ou o que fazer. Dentro de tabela com filtros, `.table-empty-row`.

### Loading Indicator
- Local à região atualizada por HTMX, nunca bloqueio de página. Spinner de 14px (borda `border`, arco `primary`, 0,6s linear) + texto em metadado, numa linha de altura reservada; com `prefers-reduced-motion`, o spinner para e o texto fica. Em envio de formulário, o equivalente é o estado Processando do botão.

### File Upload
- Input nativo oculto só visualmente (nunca `display: none`); um `<label for>` com aparência de botão secundário ("Escolher arquivo") abre o seletor sem JS e recebe o anel de foco. Ao lado, metadado com nome e tamanho do arquivo, nascendo com "Nenhum arquivo selecionado.". Dica e erro seguem Inputs / Fields.

### Confirmação
- Ação de impacto exige confirmação explícita que reitera o resultado. Hoje sem modal: a prévia é o contexto, e o botão primário repete o resultado com plural correto ("Confirmar importação: 1 inserido, 12 atualizados"), acrescentando "(N rejeitados ficam de fora)" só quando N > 0, ao lado de "Cancelar".
- **Barra de confirmação persistente:** o **único** par Confirmar/Cancelar da página, sem seção "Confirmação" separada e sem marcador próprio. É o último elemento da coluna: `sticky; bottom: 0` (nunca `fixed`) a mantém grudada ao rodapé da viewport durante a rolagem, e ela assenta na própria posição no fim da página. Fica dentro da coluna de conteúdo, sem sangrar além dela. Fundo `surface`, borda superior em `border-frame`, padding 12 × 16px, 24px acima, sem sombra; abaixo de 480px os botões empilham em largura total. Enquanto ela está grudada, a página ganha `scroll-padding-bottom` (80px; 160px abaixo de 480px, onde a barra chega a ~141px), o espelho do `scroll-padding-top` da barra de trabalho: foco de teclado e âncora nunca param sob ela.

### Resumo de totais e nota explicativa
- Pares rótulo/valor lado a lado: rótulo em metadado acima do valor em `metric`, separados por divisor vertical fino e 24px; até 640px os pares quebram em duas colunas e perdem o divisor vertical (o gap separa). Detalhe secundário em metadado; valor que não entra na soma fica separado por espaço **e** explicado por extenso. Rejeitados diferente de zero: rótulo e valor em `warning` semibold (ver Colors → Estados semânticos).
- Nota explicativa: corpo `text-muted`, até 72ch, antes do conteúdo que explica; não é alert.

## Do's and Don'ts

### Do:
- **Do** usar cada cor de segurança só no próprio significado: azul para ação, amarelo para circulação/demarcação, verde/âmbar/vermelho para estado (The NR-26 Grammar Rule).
- **Do** manter o amarelo de segurança sobre a tinta grafite (9,93:1) ou como linha de demarcação.
- **Do** resolver hierarquia por peso, caixa, alinhamento e spacing antes de recorrer a superfície própria.
- **Do** manter papéis semânticos, primitives e tokens únicos entre celular, tablet e desktop (The Shared Foundation Rule).
- **Do** mudar densidade só pelos tokens de controle e célula sob `pointer: coarse`, com botões e campos de 44px em qualquer dispositivo.
- **Do** desenhar setas e ícones em SVG inline com `currentColor`, marcados `aria-hidden` quando o texto já diz a ação.
- **Do** escrever o título de tarefa com o verbo primeiro e tornar a linha inteira o alvo.
- **Do** colocar realce de hover novo dentro de `@media (hover: hover)`; nenhuma ação depende dele.
- **Do** separar o disponível do planejado por forma, não só por cor: grafite para o primeiro (com seta só quando leva a algum lugar), tracejado, atenuação e ausência de link para o segundo.
- **Do** deixar o retorno à Home com a marca da barra de trabalho e usar o retorno contextual só quando a origem é outra tela.
- **Do** usar a Mono para CADPRO, matrícula e hash, e `tabular-nums` para número comparável.
- **Do** preservar coluna de tabela e usar scroll horizontal antes de ocultar dado.
- **Do** dar a cada estado semântico a família completa (texto + superfície + borda) e texto explícito.
- **Do** reconferir contraste de borda, texto atenuado e rótulo desabilitado contra a folha **e** o piso sempre que a rampa neutra mudar.
- **Do** reutilizar os primitivos de `components.css` e o parcial de paginação em vez de recompor por tela.

### Don't:
- **Don't** colocar eyebrow, kicker ou rótulo em caixa-alta acima de um título; o marcador de seção é o próprio título.
- **Don't** usar grade de cards iguais como estrutura de atalhos, tarefas ou listagem, em nenhum dispositivo.
- **Don't** usar seta ou símbolo Unicode (→, ←, ⇅, ▲) no lugar de ícone; setas são SVG desenhadas.
- **Don't** usar amarelo como texto, ícone, fundo de botão ou preenchimento sobre superfície clara (1,68:1 sobre branco).
- **Don't** preencher faixa, moldura ou área grande com `primary`, nem colocar mais de uma ação preenchida em `primary` no mesmo contexto.
- **Don't** introduzir sombra, glassmorphism, gradiente de cor suave ou arredondamento acima de 8px; a fita zebrada de paradas duras é o único preenchimento padronizado.
- **Don't** dar seta de fluxo, fundo grafite, link ou cursor de clique a algo planejado, nem transformar "Em preparação" em métrica, contagem ou alerta.
- **Don't** dar seta de fluxo a uma seção de leitura; a seta promete um destino.
- **Don't** duplicar a ação de confirmação numa seção final quando a barra persistente já a oferece.
- **Don't** acrescentar fonte de CDN, fonte de exibição ou terceira família; nem usar a Mono em título, rótulo ou prosa.
- **Don't** reformatar, truncar de forma destrutiva ou "limpar" o CADPRO ou outro identificador opaco (viola `INV-CATALOG-001` mesmo na camada visual).
- **Don't** transformar listagem densa em card por estar em tablet ou celular, nem reduzir permanentemente a densidade do desktop para acomodar toque.
- **Don't** usar barra lateral colorida acima de 1px em alert, callout ou item de lista; a lateral de 3px é exclusiva da linha de exceção.
- **Don't** marcar toda linha de uma tabela com selo ou borda de erro; ênfase universal se anula.
- **Don't** deixar erro de importação sumir sozinho nem usar toast para resultado já visível.
- **Don't** esconder ação frequente (buscar, filtrar, confirmar) atrás de menu de três pontos.
