---
name: WMS-Almoxarifado
description: Interface de operador baseada no django-observatory, com trabalho denso e temas claro e escuro.
colors:
  background: "#f4f4f2"
  surface: "#fcfcfb"
  surface-subtle: "#efeeeb"
  border: "#dddcd6"
  text: "#0b0b0b"
  text-muted: "#52514e"
  text-subtle: "#7b7a74"
  primary: "#1c5cab"
  primary-hover: "#174d8f"
  selected: "#e3eefc"
  series-1: "#2a78d6"
  success-surface: "#e2f4e2"
  warning-surface: "#fdf0cf"
  serious-surface: "#fbe6dc"
  danger-surface: "#f8dddd"
  neutral-surface: "#e9e8e4"
  danger-hover: "#b02f2f"
  success: "#0ca30c"
  warning: "#fab219"
  serious: "#ec835a"
  danger: "#d03b3b"
  dark-background: "#111110"
  dark-surface: "#1a1a19"
  dark-surface-subtle: "#252523"
  dark-border: "#383835"
  dark-text: "#ffffff"
  dark-text-muted: "#c3c2b7"
  dark-text-subtle: "#8f8e86"
  dark-primary: "#86b6ef"
  dark-primary-hover: "#a3c8f4"
  dark-selected: "#173a66"
  dark-series-1: "#3987e5"
  dark-success-surface: "#12351a"
  dark-warning-surface: "#40330d"
  dark-serious-surface: "#46281a"
  dark-danger-surface: "#4a1c1c"
  dark-neutral-surface: "#2e2e2b"
typography:
  page-title:
    fontFamily: "system-ui, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1.45rem"
    fontWeight: 650
    lineHeight: 1.45
  section-title:
    fontFamily: "system-ui, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1rem"
    fontWeight: 650
    lineHeight: 1.45
  body:
    fontFamily: "system-ui, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.45
  metric:
    fontFamily: "system-ui, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1.6rem"
    fontWeight: 650
    lineHeight: 1.25
    fontFeature: "\"tnum\""
  label:
    fontFamily: "system-ui, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.85rem"
    fontWeight: 400
    lineHeight: 1.45
  meta:
    fontFamily: "system-ui, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.88rem"
    fontWeight: 400
    lineHeight: 1.45
  table-header:
    fontFamily: "system-ui, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.8rem"
    fontWeight: 600
    lineHeight: 1.45
  badge:
    fontFamily: "system-ui, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.78rem"
    fontWeight: 600
    lineHeight: 1.45
  code:
    fontFamily: "ui-monospace, \"Cascadia Mono\", Consolas, \"SF Mono\", Menlo, monospace"
    fontSize: "0.88rem"
    fontWeight: 400
    lineHeight: 1.45
rounded:
  focus: "3px"
  sm: "6px"
  md: "8px"
  badge: "10px"
  chip: "12px"
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
    rounded: "{rounded.sm}"
    padding: "5px 10px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    padding: "5px 10px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "5px 10px"
  button-danger:
    backgroundColor: "{colors.danger}"
    textColor: "#fff"
    rounded: "{rounded.sm}"
    padding: "5px 10px"
  button-disabled:
    backgroundColor: "{colors.surface-subtle}"
    textColor: "{colors.text-muted}"
    rounded: "{rounded.sm}"
    padding: "5px 10px"
  input-text:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "5px 10px"
    width: "100%"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "14px 16px"
  tile:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "12px 14px"
  tile-warning:
    backgroundColor: "{colors.warning-surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "12px 14px"
  badge-neutral:
    backgroundColor: "{colors.neutral-surface}"
    textColor: "{colors.text}"
    typography: "{typography.badge}"
    rounded: "{rounded.badge}"
    padding: "1px 8px"
  badge-warning:
    backgroundColor: "{colors.warning-surface}"
    textColor: "{colors.text}"
    typography: "{typography.badge}"
    rounded: "{rounded.badge}"
    padding: "1px 8px"
  badge-plain:
    backgroundColor: "{colors.neutral-surface}"
    textColor: "{colors.text}"
    typography: "{typography.badge}"
    rounded: "{rounded.badge}"
    padding: "1px 8px"
  badge-info:
    backgroundColor: "{colors.selected}"
    textColor: "{colors.text}"
    typography: "{typography.badge}"
    rounded: "{rounded.badge}"
    padding: "1px 8px"
  table:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
  navigation-current:
    backgroundColor: "{colors.selected}"
    textColor: "{colors.primary}"
    rounded: "{rounded.sm}"
    padding: "5px 8px"
  alert-danger:
    backgroundColor: "{colors.danger-surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
  confirmation-bar-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "12px 16px"
---

# Design System: WMS-Almoxarifado

## Overview

**Creative North Star: "Interface de operador — django-observatory"**

Uma ferramenta de operador com coluna de trabalho ampla, sidebar discreta e dados compactos. A
fundação construída segue a apresentação do django-observatory 0.1.0, commit
`6edda16667c8a8601670f76e3286f86bed16e37d`: fonte do sistema, superfícies neutras, borda fina,
accent azul e ausência de elevação decorativa. A prioridade é localizar a tarefa e ler material,
saldo e identidade com pouco atrito, conforme o propósito operacional de `PRODUCT.md`.

Esta é a documentação do código construído, em modo Operate e caminho code-led, após a direção
fixada pelo usuário (seed `5138d9c5`). Shell compartilhado, Home e consulta do catálogo formam o
laboratório recomposto; as telas de credencial (entrada e senha) foram recompostas no lote P1 e
a consulta de fornecedores, os históricos e os resultados de execução das importações de catálogo
e fornecedores, no lote P2; o envio e a prévia dessas duas importações, no lote P3; a consulta,
o registro, o detalhe e o estorno de entradas de estoque, no lote P4. As demais telas (organização)
já herdam os tokens, mas sua composição continua em transição. A referência é de
apresentação: não fornece funcionalidades nem regras de domínio.
A marca textual e o SVG próprio do WMS não constituem identidade institucional aprovada do SAEP.

**Key Characteristics:**
- Coluna ampla, sidebar compacta e hierarquia por estrutura, peso e espaço.
- Claro e escuro equivalentes, com um accent azul e estados com texto e forma.
- Controles compactos no desktop e alvos ampliados no toque, sob a mesma fundação.
- Tabelas preservadas no celular, com rolagem lateral e conteúdo completo acessível.

Fonte vigente: `static/css/tokens.css`, `base.css`, `components.css` e os templates construídos.
O sidecar `.impeccable/design.json` estende o frontmatter; as capturas e medições em
`.impeccable/review/captures.json` registram o resultado real. Direção e proveniência estão em
`.impeccable/surfaces/contas-templates-contas-home-html.md`,
`docs/redesign-observatory/contrato.md` e `THIRD-PARTY-NOTICES.md`.

## Colors

Neutros levemente quentes sustentam uma única família de ação azul. O frontmatter registra os
valores claros e as substituições `dark-*`; os nomes CSS `--color-*` permanecem a API de todos os
CSS de feature. Aliases de API resolvem para os mesmos papéis: `border-frame` → `border`,
`focus` → `series-1`, `info` → `series-1`, `info-surface` → `selected` e `neutral` → `text-subtle`.

### Primary

- **Azul de ação** (`primary`): links, ação principal e texto do destino atual; `primary-hover`
  acompanha o tema. O preenchimento do botão usa texto em `surface`, inclusive no escuro.
- **Azul de seleção** (`selected`): fundo de item atual, botão selecionado e seleção de texto.
- **Azul de foco** (`series-1`): anel de foco, SVG da marca e borda de seleção; informação usa
  essa mesma família, sem acrescentar um accent de produto.

### Neutral

- **Fundo de trabalho** (`background`): área externa e coluna de trabalho.
- **Superfície de leitura** (`surface`): sidebar, painel, campo, botão secundário e tabela.
- **Superfície de apoio** (`surface-subtle`): hover e controle desabilitado.
- **Borda de separação** (`border`): delimita superfície e linha de tabela, sem moldura pesada.
- **Texto principal** (`text`): corpo, dados, estados e erros por extenso.
- **Texto de apoio** (`text-muted`): descrições, labels, notas e rótulo de processamento.
- **Texto discreto** (`text-subtle`): metadados breves, rótulos da sidebar e pistas secundárias.

Três valores do upstream ficam abaixo de AA no tema claro e são mantidos por fidelidade, por
decisão do dono do produto: rótulos de grupo da sidebar (0.7rem em `text-subtle`), rodapé da conta
em `text-subtle` (~4,2:1 sobre `surface`) e borda de campo em `border` (~1,34:1 sobre o card). É
uma decisão registrada sobre esses três usos, não uma recomendação: texto novo de leitura usa
`text-muted` ou `text`.

### Estados

Os indicadores `success`, `warning`, `serious` e `danger` mantêm sua cor nos dois temas; os fundos
`*-surface` mudam com o tema. Sucesso usa círculo, atenção usa losango, perigo usa triângulo e
informação usa quadrado. `serious` preserva o token da referência, mas não tem variante de badge
implementada; não inventar um componente a partir da existência do token. Neutro usa círculo;
papéis e itens planejados usam badge sem marcador. `danger-hover` é derivado para confirmação.

**The One Accent Rule.** Quando houver ação principal clara no contexto, ela usa o primário;
as demais ações usam o secundário. Links e seleção usam a mesma família azul, sem accents
concorrentes introduzidos por tela.

**The No Color-Only State Rule.** Estado e seleção têm pista não cromática: texto, forma, peso,
borda ou posição. Cor de estado identifica marcador, borda ou fundo; texto de badge, mensagem e
erro permanece no papel `text`.

O padrão segue `prefers-color-scheme`. A preferência explícita em `data-theme` vence o sistema e
é persistida como `wms-tema`; o script do head aplica-a antes da pintura. `color-scheme` acompanha
o tema para controles nativos. Sem JavaScript, a preferência do sistema continua funcional e o
botão de alternância fica oculto. A paleta clara não é aplicada como fallback visual ao escuro.

## Typography

**Body Font:** pilha do sistema registrada no frontmatter, também usada em títulos e controles.
**Label/Mono Font:** pilha mono do sistema, exclusiva de identificadores e dados técnicos.

**Character:** uma única voz de interface, compacta e legível. A família concreta acompanha o
sistema operacional; fidelidade à referência considera tamanho, peso e entrelinha. A raiz é
14 px, portanto os `rem` do frontmatter se referem a essa base, não a 16 px.

### Hierarchy

- **Page title:** título de página, peso 650; sem fonte de exibição nem tracking especial.
- **Section title:** título de card no tamanho de corpo, peso 650, margem inferior de 0.7rem.
- **Body:** dados e prosa com entrelinha base; descrições de cabeçalho limitadas a 70ch e notas
  longas a 72ch, sem limitar a largura da coluna operacional.
- **Metric:** valor de tile e total, peso 650, entrelinha compacta e numerais tabulares.
  O valor efetivo dos tiles é 1.6rem (22.4px), também no celular.
- **Label / meta:** label acima do campo; nota abaixo ou inline ao título quando complementa-o.
- **Table header / badge:** cabeçalho sem caixa-alta; badge compacto sem perda do texto.
- **Code:** CADPRO, matrícula, códigos SCPI, documento e hash, preservados como texto.

Rótulos de grupo usam caixa-alta com 0.04em e peso 600; na sidebar usam 0.7rem, fora dela 0.8rem.
O rótulo de tile usa 0.82rem; a nota de tile usa 0.8rem. São papéis de apoio, não títulos de
exibição. Labels de formulário permanecem visíveis. A marca da tela de entrada usa 1.15rem,
derivação local fora da escala do frontmatter; não é papel tipográfico a reutilizar.

**The Mono-Is-Data Rule.** Mono pertence a dado e identificador opaco; não a prosa, título de
página, rótulo ou botão. O valor de matrícula dentro do tile é dado, portanto pode ser mono.

**The Opaque CADPRO Rule.** Exibir CADPRO inteiro e copiável, sem reformatação, decomposição,
conversão numérica ou truncamento destrutivo. A família mono muda só a apresentação.

## Layout

A aplicação autenticada usa grade de duas colunas: sidebar (216px) e trabalho
`minmax(0, 1fr)`, com altura mínima de viewport. A sidebar é sticky no desktop, tem altura de
viewport, rolagem própria, padding 14px 10px e borda à direita. O conteúdo ocupa a largura
restante sem teto, com padding 18px 24px 48px. Um único main por página; fragmentos HTMX trazem
apenas a região atualizada. O cabeçalho agrupa título/descrição e ferramentas, com quebra flex,
gap 12px e margem inferior 16px.

A grade de painéis usa gap 14px. Painéis têm padding 14px 16px; tiles, 12px 14px. A grade de tiles
usa mínimo de 150px e alinha cada tile pelo topo, sem esticar vizinhos para igualar alturas. Só a
faixa de métricas (`.tiles.tiles-metricas`, totais de uma execução) estica os tiles da linha para a
mesma altura; os tiles de identidade da Home continuam alinhados pelo topo.
A grade de duas colunas usa mínimo de 380px e passa a uma coluna até 860px. Na Home, a largura
390px comporta Matrícula e Setor lado a lado; Papéis ocupa a linha inteira até 640px. Esses
são dados de identidade, sem clique e sem contadores inventados.

Até 860px a sidebar vira barra superior estática com padding lateral 16px: marca e botão Menu
ficam na mesma linha, com 8px acima/abaixo. A navegação abre em fluxo abaixo dela, sem overlay.
Os itens e controles têm alvo mínimo de 44px; Escape fecha e devolve foco ao botão. Sem JS,
a navegação fica aberta e Menu fica oculto. O main usa padding 14px 16px 40px. Não há barra
horizontal industrial como alternativa de shell. No shell da credencial provisória não há destino
a abrir: até 860px não existe botão Menu e o rodapé da conta fica sempre visível, em fluxo logo
abaixo da barra da marca; no desktop esse shell não muda.

A credencial anônima não tem shell: sem sidebar nem cabeçalho de página, um único main em coluna
centralizada sobre `background`, com a marca (glifo e nome, texto, nunca link) acima de um card
de formulário. A coluna se ancora no topo com respiro `clamp(24px, 10vh, 96px)`, não no centro
vertical, para o teclado virtual não cobrir o campo focado; as laterais respeitam a área segura
(mínimo 16px). O erro de autenticação é uma mensagem de erro acima do formulário, com id
referenciado pelos campos, e a orientação de recuperação é nota permanente no pé do card.

No desktop com mouse, controles têm mínimo 30px e padding 5px 10px; células têm 6px 10px.
`pointer: coarse` ou largura até 860px amplia controles para 44px e campos para fonte 16px.
No toque, o padding vertical das células sobe para 12px. A escala compartilhada de espaços
é baseada em 4px; medidas portadas como 14px e 10px são preservadas, sem arredondá-las à escala.

Filtros quebram por flex; até 640px os campos empilham e Buscar/Limpar dividem a linha. Na
consulta, o campo CADPRO tem base 240px acima de 640px e Descrição cresce. Tabelas conservam a
estrutura tabular e rolam lateralmente dentro do painel; nunca viram cards por registro. O
catálogo usa mínimo de 46rem para tabela, 14rem para Descrição no desktop (10rem–12rem no
celular), 16rem para Classificação com nome e código inline e 14rem–24rem para Detalhamento.
Números e identificadores não quebram; descrição pode quebrar sem perder o texto.
A consulta de fornecedores segue o mesmo molde: Código (CODIF) e Documento em mono com base de
200px e 260px acima de 640px, Nome com base de 320px, tabela com mínimo de 44rem e coluna Nome
de 14rem (10rem–12rem no celular). A largura mínima vale só para a tabela de resultados (a que tem
`tabindex="-1"`, alvo do foco após a busca); a tabela do estado vazio cabe no card, e na consulta
do catálogo até 640px o seu `thead` fica só para leitor de tela, para a mensagem ocupar o card.

**Composição das telas recompostas.** A página preenche os blocos `heading`, `sub`, `tools` e
`page` do shell. Em tela interna, `sub` traz a trilha "Seção / item" com link para a seção; em
tela de seção, a descrição. A ação de página fica em `tools` como botão secundário. Tabelas,
paginação e vazio ficam dentro de um card. O resultado de uma execução segue a ordem: faixa de
tiles do resumo logo após o cabeçalho, notas do resumo (`text-note`), card de metadados com
`dl.kv` e um card por seção de resultado. Nas tabelas de seção, preenchimento horizontal menor
e cabeçalhos que quebram linha até 640px são ajustes do CSS de feature para caber no card.

A prévia de uma importação é a execução antes de gravar e repete a mesma composição (tiles do
resumo primeiro, notas, um card por seção), no tom de "ainda não gravado": selo `badge-info` "Não
gravada" no h1, trilha "Importar … / Prévia" em `sub`, `tools` vazio, aviso informativo
(`role="status"`) com o arquivo e "nada foi gravado ainda" acima do resumo e rótulos de tile no
futuro ("Serão inseridos"). A seção de Exceções não pinta as linhas com `table-row-error`: o card já
é a lista de rejeitados e a atenção fica no tile. O único par de ações é a barra de confirmação, no
fim da página. O envio de arquivo é formulário isolado em card de formulário, com o histórico em
`tools` e, havendo prévia pendente, aviso informativo acima do card com o link para continuá-la.

A composição de uma operação (registro de entrada) é um formulário com um card por seção. A ação
de fim do formulário que ainda não grava ("Revisar") fica em `.form-actions`, primária, com uma
nota ao lado dizendo que nada é gravado; não gruda no rodapé. Só a barra de confirmação gruda.
Quando a revisão chega por troca HTMX, o h1 não muda: o fragmento abre com um título de seção
que leva o selo `badge-info` "Não gravada" e recebe o foco, seguido do aviso informativo
(`role="status"`) e dos cards, no tom da prévia de importação.

O detalhe de um objeto com situação leva o selo no h1, a trilha em `sub` e, só para quem pode
executá-lo, o convite destrutivo em `tools`. Uma operação que o servidor recusaria vira tela de
estado, não de ação: selo `badge-warning` "Bloqueado" no h1, `.error-box` com `role="alert"`
nomeando a causa (os CADPRO afetados) antes do conteúdo e no lugar do aviso de consequência, sem
barra de confirmação, só o link de volta em `.form-actions`.

Regras de CSS de feature por `id` de seção são escopadas pela classe da tela
(`:is(.execucao-secao, .previa-secao)#alteracoes`): prévia e execução reusam os mesmos ids, e um
seletor só por `id` atingiria também a consulta e o histórico da feature.

**The Shared Foundation Rule.** Papéis, primitivas e estados são únicos entre desktop, tablet e
celular. Composição e densidade variam; tokens e linguagem visual não se bifurcam por dispositivo.

**The No Hover Dependency Rule.** Nenhuma ação necessária depende de hover. Links reais, labels,
foco e indicadores de ordenação continuam descobríveis no toque e por teclado. Hover é realce
adicional; linhas de tabela o aplicam somente sob `hover: hover`.

### Transição de composição

Os lotes P1 (credenciais), P2 (consultas e históricos de importação), P3 (envio e prévia das
importações) e P4 (entradas de estoque) estão recompostos; P5 (organização) e P6 estão pendentes.
`.page*`, `.page-header*`, `.section-marker*`, `.back-link`, `.page-section`, `.meta-grid`,
`.form-frame`, `.alert-danger`, `.table-wrapper-marker-attached`, a barra de confirmação base e
`table-sticky-header` seguem em `components.css` só como compatibilidade da organização, a única
área ainda não recomposta; nenhuma tela recomposta os usa. `.summary` e `.field-label` ficaram sem
consumidor depois do P4. `table-row-error` segue em uso só no estoque, na linha de exceção.

O shell mínimo da credencial provisória usa a mesma sidebar, com marca sem link e conta, sem
grupos de navegação; o formulário de senha usa o cabeçalho de página e o card de formulário.
A entrada anônima segue a composição sem shell descrita acima; a barra de marca legada foi
removida. `.page`, `page-header`,
`page-container-narrow` (640px) e o bloco `content` próprio são compatibilidade temporária, não
uma segunda fundação nem a composição a reproduzir em telas novas.

Os lotes P1–P6 de `docs/redesign-observatory/plano.md` recompõem credenciais, consultas/históricos,
importações, estoque e organização e retiram compatibilidade sem consumidor. Resumos, metadados,
confirmações sticky, listas de opções e padrões de impedimento das features existentes continuam
em uso, consumindo os novos tokens; sua presença não significa propagação concluída. Referências
antigas em PRODUCT, specs e definições de agentes são pendências de alinhamento documental de
P6; não restabelecem a fundação anterior.

## Elevation & Depth

Painéis, tiles, botões e sidebar são planos: separação por superfície, borda de 1px, estrutura e
espaço. Não foi portada a sombra de tooltip da referência. O wrapper de tabela tem uma pista
funcional de rolagem lateral feita por backgrounds: capas lineares de 32px e gradientes radiais
de 10px nas bordas; os backgrounds locais cobrem a pista na extremidade alcançada. Isso indica
conteúdo fora da área visível e não é elevação de painel.

**The Flat-By-Default Rule.** Não adicionar sombra em card, tile, botão ou hover. A pista lateral
de scroll informa continuidade do conteúdo, sem instaurar uma linguagem de cartões elevados.

O cabeçalho sticky com scrollport de 60vh e linha de sombra inset (`table-sticky-header`)
pertence a tabelas herdadas. A pendência foi resolvida no P2 sem ele: históricos e resultados de
execução rolam com a página, sem segundo scrollport vertical, e a tabela larga rola só na
horizontal dentro do card. A regra continua em `components.css` apenas para os consumidores
legados da organização (P5); o estoque deixou de usá-la no P4. Não é padrão de tela recomposta nem
regra a generalizar.

## Shapes

Bordas finas e curvas pequenas substituem as faixas e molduras industriais anteriores. O
frontmatter define raios: controle/item/mensagem em `sm`, painel/tile em `md`, badge em `badge`,
chip em `chip`, anel em `focus`. A existência do token chip não autoriza portar chips de busca
por linguagem: esse componente não existe no laboratório. SVG da marca (18px, traço 2.4) é
próprio do WMS; estados usam pequenas formas CSS, não ícones de fonte nem imagens.

## Components

### Buttons

Controles discretos, com superfície e borda de 1px. O primário preenche ação e borda em `primary`,
com peso 600; hover usa `primary-hover`. O secundário usa `surface`, hover em `surface-subtle`.
Selecionado usa `selected` com borda `series-1`. Destrutivo mantém fundo/borda de perigo e texto
branco, concentrado na confirmação; o convite usa secundário com borda de perigo. A variante
já usada pelas features não altera regras de domínio ou quais operações exigem confirmação. Na
fundação recomposta, o estorno de entrada é o consumidor: o convite fica em `tools`, só para quem
pode executar, e na barra de confirmação o destrutivo ocupa o lugar do primário e recita a
consequência; operação destrutiva não usa o primário azul. Um `<summary>` com a forma do
secundário (disclosure que abre uma busca) mostra o estado aberto por fundo `selected`, borda
`series-1` e peso 600, além do estado nativo do `<details>`.

Desabilitado usa `surface-subtle`, borda normal e texto `text-muted`, cursor de impedimento;
o rótulo de processamento continua legível. Em processamento (`envio.js`, por data-attribute) o
botão desabilita, o formulário ganha `aria-busy` e o rótulo vira um verbo por extenso ("Enviando…",
"Confirmando…"); a largura do botão fica fixada para o vizinho não se deslocar, os demais botões da
mesma barra de confirmação desabilitam juntos e tudo volta no `pageshow`. Formulários com a mesma
action compartilham o bloqueio de duplo envio. `estoque.js` cumpre o mesmo contrato por delegação
em `document`, cobrindo o formulário de confirmação inserido por troca HTMX; o link da barra
ocupado recebe `aria-disabled` e não navega. Todos os controles interativos têm foco visível
em `focus`: outline 2px, offset 2px e raio de foco. As ações de formulário quebram e empilham
até 480px, mantendo primária antes de Cancelar. Botão oculto pelo atributo hidden permanece oculto.

### Inputs / Fields

Mesma borda, superfície e curva do botão, largura total e altura mínima de controle. Label,
campo, dica e erro formam coluna com gap 3px. Campo em erro ganha borda de perigo, mensagem
com triângulo de 7px e texto normal; `aria-invalid` e referências a dica/erro permanecem no HTML.
Campo de identificador usa mono. Textarea permite resize vertical. Envio de arquivo mantém
input acessível e label com aparência de botão, sem exigir JS para abrir o seletor; o texto ao lado
nasce "Nenhum arquivo selecionado." e o script o troca por nome e tamanho. O erro do campo tem id
`<auto_id>_error`, referenciado pelo widget em `aria-describedby`.

Dica é parágrafo de apoio com id `<auto_id>_helptext`, renderizada só quando o campo tem dica e
também com erro. Nos formulários de credencial o widget referencia erro, dica e mensagens gerais
nessa ordem, e o servidor põe o foco inicial em um único campo: o primeiro inválido ou,
sem erro de campo, o escolhido pelo formulário.

Caixa avulsa sob um campo ("Mostrar senha") usa o rótulo inteiro como alvo, com altura de
controle (44px no toque e até 860px), caixa de 18px em `primary` e gap 8px. A variante que só
funciona com JavaScript fica oculta sem `html.js`, como o botão de tema. O aviso de atenção do
campo (Caps Lock) é região `aria-live="polite"` que nasce vazia e sem altura; com texto, usa o
tamanho da dica, texto em `text` e losango de 7px em `warning`. Não é descritor do campo e fica
fora do `aria-describedby`.

Comportamentos pontuais são contratos por data-attribute, carregados com `defer` e delegados em
`document`; sem JS o formulário funciona e o servidor valida. Mostrar senha alterna o tipo dos
campos de senha do mesmo formulário e os devolve a `password` no envio e no `pageshow`. Caps Lock
escreve no aviso a mensagem do atributo `data-mensagem`, nunca texto do script. A checagem da
confirmação cancela, na captura, o envio divergente e renderiza o mesmo erro de campo do servidor,
com o texto vindo do formulário.

Depois de uma troca HTMX num formulário, o foco vai, nesta ordem, ao campo com `autofocus`, ao
primeiro `aria-invalid`, ao alerta geral (`.error-box` com `role="alert"`) ou ao título da revisão;
um campo dentro de wrapper rolável é revelado também na horizontal, junto do seu erro. Campo dentro
de célula de tabela leva o erro num bloco próprio de medida fixa sob o campo, que identifica o
material pelo CADPRO (só visual); a linha só ganha `table-row-error` quando o erro é da linha.

### Navigation

Um shell declarado na base; navegação recebe destinos calculados no servidor e marca o atual
com `aria-current="page"`, seleção de fundo e peso 600. Item tem padding 5px 8px, curva de controle
e texto de apoio; hover usa superfície de apoio e texto principal. Os grupos são visíveis só
quando contêm destino. A sidebar não inclui capacidades planejadas. Rodapé agrupa matrícula,
setor, Senha, Sair e tema; o logout mantém formulário POST com CSRF. Filtrar links não substitui
a autorização das rotas. O link Pular para o conteúdo fica visível ao receber foco.

Links em texto corrido (parágrafos, listas, definições, notas, descrições, dicas, erros, mensagens
e vazios) ficam sublinhados: a cor sozinha não distingue o destino da prosa. Navegação, botões,
paginação, ordenação, link de linha de tabela e retorno contextual usam sua própria affordance
e seguem sem sublinhado em repouso. O modificador `text-link` mantém seu sublinhado explícito
como pista textual de link. O foco e o hover preservam os estados definidos pelo componente.

### Cards / Tiles

Painéis agrupam conteúdo relacionado com título em corpo e peso 650, borda leve e fundo de
superfície. Tile destaca dado com rótulo acima, valor e nota opcional. Só tile com destino real
é link; os três tiles de identidade da Home são leitura. Altura acompanha o conteúdo.
Tarefas da Home usam card por grupo, com link e descrição na mesma célula por tarefa.
No título de página, um badge pode acompanhar o h1 como selo de estado do objeto (resultado
"Com rejeições"/"Sem rejeições"; entrada "Registrada" em `badge-success` ou "Estornada" em
`badge-neutral`, estado final legítimo e não erro), da prévia ("Não gravada", em `badge-info`) ou
de impedimento ("Bloqueado", em `badge-warning`), com 8px de afastamento e alinhado ao meio. A
lista de entradas repete o mesmo selo de situação por linha.

O resumo de métricas usa tiles de leitura com rótulo, valor e nota. Tile de atenção
(`tile-warning`) segue a gramática do alerta de aviso: fundo e borda de `warning`, losango de 7px
antes do rótulo e rótulo em peso 600, com texto em `text`; aplica-se só quando o total é maior
que zero. Valor que não entra na soma dos demais (`tile-aside`) tem borda tracejada e nota "fora
da soma" em texto. A nota do tile pode trazer um atalho textual para a seção correspondente
("ver exceções"), só quando o total é maior que zero: link real numa linha própria, sem tornar o
tile inteiro clicável, com faixa de toque de 44px por pseudo-elemento no toque ou até 860px. A
nota do tile permanece em `text-subtle` (0.8rem), como é hoje.

Na prévia de fornecedores, com quatro valores fora da soma, o CSS da feature agrupa o resumo em
dois grupos nomeados ("Composição da carga" e "Fora da soma"; `role="group"` com `aria-labelledby`
no rótulo visível, em `text-muted`, meta, peso 600), quatro colunas no desktop e duas até 640px. No
grupo de fora da soma, o tile em atenção engrossa o tracejado para 2px, porque a borda de `warning`
apagava o tracejado de 1px. É composição de feature (`fornecedores.css`), não primitiva: os tiles
compartilhados não mudam e, com um único valor fora da soma (catálogo), `tile-aside` basta.

Cards consecutivos de pares rótulo/valor (`dl.kv`) na mesma página podem fixar a coluna de
rótulos pelo CSS de feature (no estoque, 12rem; 8.5rem até 480px) para os valores se alinharem de
um card a outro. A identidade composta de uma entidade (no estoque, o emitente: nome · código ·
documento) é um único fragmento, reusado na revisão, no registro e na escolha: identificadores em
mono, separadores visuais `aria-hidden` e rótulos "código"/"documento" em `visually-hidden`.

Formulário isolado usa o card com medida de formulário (máximo 420px): a coluna de trabalho não
tem teto, então é o card que limita a própria largura, alinhado à esquerda; na entrada anônima o
mesmo card se centraliza.

**The Available-Versus-Planned Rule.** Disponível tem destino real; planejado permanece texto,
com selo explícito e sem link ou cursor de clique. Na Home, Em preparação usa uma célula por
função: título e selo na primeira linha, descrição abaixo. Não simular disponibilidade por forma.

### Badges / Messages

Badge é pílula com padding 1px 8px, peso 600 e texto normal; marcador de 7px e fundo carregam
o estado. Badge plain não tem marcador e serve a papel ou Planejado. Lista de badges quebra
com gap 4px. Mensagem usa padding 8px 12px, raio de controle e margem inferior 12px, com
fundo/borda da família. Sucesso, atenção e informação incluem marcador; erro explicita o motivo.
Erro usa role alert; mensagens de estado usam role status. Nenhum texto de erro fica vermelho
como única pista. O aviso de consequência de uma operação irreversível é `alert-warning` estático,
sem `role`, acima do conteúdo. Mensagem de largura total pode limitar a medida do texto (75ch no
estoque) sem estreitar a caixa.

### Tables / Pagination

Tabela com bordas horizontais, numerais tabulares e números à direita. Cabeçalho mantém rótulos
em uma linha e peso 600, sem caixa-alta. Link real oferece ordenação, `aria-sort` e indicador de
direção; no toque as outras colunas mostram indicador de ordenabilidade. A consulta também
anuncia a ordem por texto fora da região HTMX trocada. Conteúdo longo usa details/summary
com texto integral disponível, sem hover; nome e código de Classificação ficam inline.

Célula pode trazer uma linha secundária (`cell-secondary`) sob o dado principal: descrição ou
nome atual sob o código, detalhe sob o motivo, em `text-muted`, tamanho de meta, inteira e com as
quebras do dado preservadas. Linhas consecutivas do mesmo código mostram código e linha
secundária só na primeira; nas seguintes o código fica em `visually-hidden`. Cabeçalho pode
quebrar linha por `th-wrap`. Wrapper rolável de seção é região nomeada e focável
(`role="region"`, `aria-label` "Tabela de …", `tabindex="0"`). Nos históricos, o link da linha
(`#N`) usa a cor de acento, via CSS de feature; a consulta de entradas segue o mesmo molde. O nome de arquivo longo é cortado no meio em duas
versões alternadas por largura (estreita até 860px, larga acima), cada uma com `<details>` que
revela o nome inteiro. Até 640px uma tabela pode juntar duas colunas numa célula alternando
`so-desktop` e `so-movel`, com rótulos em `visually-hidden` e seta decorativa `aria-hidden`.

Em tabela com um controle por linha (escolher, adicionar, remover), a coluna Ação vem primeiro,
para o controle ficar visível no celular sem rolagem lateral, e as células centralizam
verticalmente com ele. Quando a ação não cabe (fornecedor bloqueado, material já incluído), um
único selo ocupa o lugar do botão e o motivo fica em texto na linha. Tabelas de movimento de saldo
repetem a mesma ordem na revisão e no estorno (Código, Descrição, Saldo atual, Quantidade, Saldo
resultante, Unidade), lidas como a conta que são. `table-row-error` marca só a linha de exceção,
sempre com o motivo em texto na própria célula.

**The One Reading Rule.** Conteúdo alternado por largura usa `display: none` na versão que não
vale, nunca duas cópias visíveis ao leitor de tela; repetição visual suprimida continua no DOM
como texto oculto, não some da leitura.

Paginação dentro do painel: resumo à esquerda e botões à direita; atual usa fundo selecionado,
borda de foco e peso 600. Até 640px o resumo e números têm suas linhas, com Anterior/Próxima
lado a lado abaixo. Reticência é texto, não controle. O vazio preserva orientação por extenso,
com título e descrição, sem desenhar métrica fictícia. Spinner local tem 12px, giro linear de
0.6s; sob prefers-reduced-motion fica parado. Não há motion decorativo nem polling portado.

### Barra de confirmação

Único par de ações de uma página que confirma uma operação: último elemento do conteúdo, sticky no
rodapé da viewport (nunca `fixed`), primário antes do secundário, fundo `surface` e padding 12px
16px. A base, com borda superior e colada ao rodapé, segue só na organização. A variante de card,
usada nas prévias de importação, na revisão da entrada e no estorno, usa a gramática do painel:
borda de 1px em volta, raio `md`, sem sombra, flutuando 12px acima do rodapé; um pseudo-elemento
pinta esse vão com `background` a partir de 1px abaixo da borda inferior e 1px além de cada
lateral, para o conteúdo rolado não aparecer por baixo nem cortar a borda da barra. Fica dentro da coluna de trabalho,
nunca sobre a sidebar. No desktop a barra não quebra: o primário encolhe e quebra o rótulo longo,
alinhado à esquerda, e o Cancelar mantém a largura. Até 480px a barra empilha, os botões ocupam a
largura com texto centralizado e uma linha de resumo curta (`text-muted`, meta, itens separados por
"·") aparece acima deles; os totais do rótulo saem só da vista (fonte 0, inline, sem virar
fronteira de palavra). A folga de rolagem acompanha a barra: 7rem, ou 11rem até 480px (base: 5rem
e 10rem).

Quando a confirmação entra por troca HTMX no ponto em que estava o gatilho (Revisar → Confirmar),
o envio do formulário de confirmação é ignorado por 500 ms após a inserção, sem desabilitar o
botão, para o segundo toque do mesmo gesto não gravar sem leitura.

**The Consequence Label Rule.** O primário da confirmação recita a consequência (o que será
gravado e o que fica de fora) e esse texto inteiro é o nome acessível do botão. O resumo curto do
celular é só visual (`aria-hidden`), nunca uma segunda fonte do nome.

### Padrões existentes em transição

Resumos de totais, pares rótulo/valor, hashes, opções com motivo de bloqueio, a barra de confirmação
base e histórico por link continuam primitivos compartilhados. A organização conserva composição
própria (ações agrupadas, segredo copiável, efeitos por pessoa, checklist e impedimentos),
consumindo tokens da fundação. São contratos de uso a preservar ao recompor P5, sem copiar os
comentários antigos como direção estética.

## Do's and Don'ts

### Do:

- **Do** usar a API de tokens compartilhada e conferir claro e escuro nas mesmas superfícies.
- **Do** manter a coluna operacional larga e limitar a medida da prosa, não a tabela.
- **Do** usar controle compacto no desktop e alvos de 44px com campo de 16px no toque ou até 860px.
- **Do** manter foco visível, label associado e estado com texto e pista não cromática.
- **Do** manter CADPRO inteiro, copiável e opaco e números comparáveis alinhados à direita.
- **Do** distinguir destino disponível de função planejada por link real e texto explícito.
- **Do** reutilizar card, tile, campo, tabela e paginação e manter DESIGN e sidecar fiéis ao código.

### Don't:

- **Don't** reinstalar a linguagem de Tubulação, NR-26, amarelo de demarcação ou fontes Atkinson.
- **Don't** criar sombra de painel, gradiente decorativo ou família de exibição para reinterpretar a referência.
- **Don't** bifurcar tokens por dispositivo, esconder ação no hover ou remover o anel de foco.
- **Don't** transformar tabela em cards por registro ou esconder dado sem acesso ao conteúdo integral.
- **Don't** inventar indicadores, contadores, gráficos, Live, exports ou chips de busca do upstream.
- **Don't** promover encaixes legados, override móvel inefetivo ou scrollport de 60vh a regra de novas telas.
- **Don't** tratar visibilidade de link como autorização nem alterar domínio para acomodar apresentação.
