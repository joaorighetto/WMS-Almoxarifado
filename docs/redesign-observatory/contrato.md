# Contrato de fidelidade — redesign baseado no django-observatory

Contrato visual e estrutural do redesign da interface de produto do WMS-Almoxarifado. Complementa o
direction contract em `.impeccable/surfaces/contas-templates-contas-home-html.md` (que o resume em
seis blocos) e é a instrução que o `frontend-implementer` recebe. O plano de execução está em
[`plano.md`](plano.md).

Este documento descreve a **direção a construir**. Ao fim do laboratório, `DESIGN.md` e
`.impeccable/design.json` são reescritos pelo `impeccable-documenter` a partir do código construído;
a partir daí eles são a fonte vigente, e este contrato vira registro da direção que os originou.

## 1. Referência fixada

| Item | Valor |
|---|---|
| Projeto | django-observatory (MIT) |
| Versão publicada | 0.1.0 (única versão no PyPI em 2026-10-05) |
| Commit | `6edda16667c8a8601670f76e3286f86bed16e37d` (HEAD do repositório em 2026-10-05) |
| URL imutável | https://github.com/AzeemQidwai/django-observatory/tree/6edda16667c8a8601670f76e3286f86bed16e37d |
| Wheel conferido | `django_observatory-0.1.0-py3-none-any.whl`, sha256 `ffbb3b11d2bb685c7d125f667bff5c07d8f42aab9b09a94e4ab18c4c382fdaf6` |
| Correspondência | `templates/` e `static/` do wheel são idênticos byte a byte aos do commit |
| Capturas | `docs/images/*.png` do commit (1440 × 900; `logs.png` 1440 × 800), só alteradas no commit inicial `0352462` |
| Licença | MIT, "Copyright (c) 2026 django-observability contributors" |

Arquivos estudados: `templates/django_observatory/base.html`, `list.html`, `_cells.html`,
`_range.html`, `dashboard.html`, `log_detail.html`, `request_detail.html`, `settings.html`,
`health.html`, `search.html`, `alerts.html`, `static/django_observatory/app.css` (195 linhas),
`app.js` (372 linhas; só o trecho de tema é portado), `docs/user-guide.md`, `docs/architecture.md`
e as capturas `dashboard.png`, `logs.png`, `request.png`, `performance.png`, `database-dark.png`.

As capturas foram feitas num Linux (a fonte de sistema renderizada é Ubuntu). No macOS a mesma pilha
`system-ui` resolve para SF Pro e no Windows para Segoe UI; comparações de tipografia consideram
métrica (tamanho, peso, entrelinha), não o desenho da fonte.

### Valores do ponto de partida confirmados no código

Todos confirmados em `app.css`: sidebar `216px` (`.app { grid-template-columns: 216px minmax(0, 1fr) }`),
conteúdo na largura restante sem teto, `html { font-size: 14px }` com `--sans: system-ui, "Segoe UI",
Roboto, Helvetica, Arial, sans-serif`, `--bg #f4f4f2`, `--surface #fcfcfb`, `--border #dddcd6`,
`--accent #1c5cab`, `--radius 8px`, tabelas com `padding 6px 10px` e `tabular-nums`, tema escuro por
custom properties em `@media (prefers-color-scheme: dark)` + `[data-theme]`, preferência persistida em
`localStorage`.

### Proveniência e licença

- Trechos portados (valores de tokens, regras de `app.css`, a lógica de tema de `app.js`) levam no
  cabeçalho do arquivo de destino a linha de origem: projeto, versão, commit e "MIT — ver
  THIRD-PARTY-NOTICES.md".
- `THIRD-PARTY-NOTICES.md` (raiz) reproduz o aviso de copyright e o texto integral da licença MIT do
  django-observatory, como a licença exige para "substantial portions".
- Nenhum template, ícone, imagem ou texto do upstream é copiado para o produto; a única forma
  gráfica reaproveitada é a convenção do glifo da marca (SVG 18 px, `stroke-width 2.4`), com desenho
  próprio do WMS.

## 2. O que é portado e o que não é

Portado: a camada de apresentação — shell com sidebar, cabeçalho de página, tokens claro/escuro,
controles, cards, tiles, tabelas, paginação, badges com forma, mensagens, `dl.kv`, tabs e a
preferência de tema.

Não portado (decisão do dono do produto, prompt do redesign): infraestrutura de telemetria, polling
"Live", linguagem de busca e seus chips, motor declarativo de tabelas (`tables.py`/`_cells.html`),
exports CSV/JSON/NDJSON, seletor de intervalo de tempo, gráficos, tooltips, grafo de relações,
contadores na sidebar. Nada disso tem equivalente nos fluxos atuais do WMS.

## 3. Shell

### Estrutura (desktop, > 860 px)

```text
body
└─ a.skip "Pular para o conteúdo" (→ #main)
└─ div.app  grid 216px | minmax(0,1fr), min-height 100vh
   ├─ aside.side  surface, border-right 1px border, padding 14px 10px,
   │              sticky top 0, height 100vh, overflow-y auto
   │  ├─ marca (link para a Home; aria-current na Home)
   │  ├─ nav[aria-label="Seções"]  itens e grupos (h3) por capability
   │  └─ rodapé da conta (.meta-env)
   └─ main.main#main  padding 18px 24px 48px, min-width 0
      ├─ div.top  cabeçalho da página (título, descrição, ferramentas)
      └─ conteúdo da página
```

- Conteúdo ocupa toda a largura restante, sem `max-width` (como o upstream). Parágrafos longos
  (descrições, notas) limitam a própria medida (`max-width` em `ch`), não a coluna.
- Um único `<main>` por página. Fragmentos HTMX nunca trazem `.app`, `.side` nem `.top`.

### Marca

- Glifo SVG 18 × 18, `viewBox 0 0 24 24`, `stroke currentColor`, `stroke-width 2.4`, cor
  `--series-1`; desenho próprio do WMS (caixa/volume de almoxarifado), não o pulso do upstream.
- Texto "Almoxarifado SAEP", peso 700, `gap 8px`. O valor computado segue o código do upstream,
  onde `.side a` vence `.brand` por especificidade: `padding 5px 8px`, cor `--text-2`, glifo à
  esquerda e texto alinhado à direita (`justify-content: space-between`). As capturas confirmam esse
  resultado; mantido por fidelidade.
- `aria-current="page"` fica só no item Início, nunca também na marca.

### Navegação

- Primeiro item, sem grupo: **Início** (equivale a "Dashboard").
- Grupos em `h3` (`.7rem`, 600, caixa-alta, `letter-spacing .04em`, cor `--text-3`,
  `margin 14px 8px 4px`), na ordem abaixo. Um grupo só aparece com ao menos um item visível.

| Grupo | Item | Destino | Condição de exibição |
|---|---|---|---|
| — | Início | `home` | autenticado sem credencial provisória |
| Catálogo | Materiais | `catalogo:consulta` | `pode_consultar_catalogo` |
| Catálogo | Importar catálogo | `catalogo:importacao_envio` | `pode_importar_catalogo` |
| Catálogo | Histórico de importações | `catalogo:historico` | `pode_importar_catalogo` |
| Fornecedores | Fornecedores | `fornecedores:consulta` | `pode_consultar_fornecedores` |
| Fornecedores | Importar fornecedores | `fornecedores:importacao_envio` | `pode_importar_fornecedores` |
| Fornecedores | Histórico de importações | `fornecedores:historico` | `pode_importar_fornecedores` |
| Estoque | Registrar entrada | `estoque:entrada_nova` | `pode_registrar_entrada` |
| Estoque | Entradas | `estoque:entradas` | `pode_consultar_entradas` |
| Administração | Usuários | `usuarios` | `pode_administrar_organizacao` |
| Administração | Setores | `setores` | `pode_administrar_organizacao` |

- As flags são as mesmas que a Home já usa, calculadas uma vez por requisição pelo mesmo mecanismo
  de capabilities (ver `plano.md` → T2). A sidebar não decide autorização: cada rota continua
  verificando no servidor.
- Item: `display flex; justify-content space-between; padding 5px 8px; border-radius 6px;
  color --text-2`. Hover: fundo `--surface-2`, cor `--text`, sem sublinhado.
- Item atual: `aria-current="page"`, fundo `--accent-bg`, cor `--accent`, peso 600. Telas internas
  de um fluxo marcam o item do fluxo (prévia e execução de importação → "Importar …"/"Histórico …";
  detalhe e estorno de entrada → "Entradas"; telas de usuário/setor → "Usuários"/"Setores").
- Capacidades planejadas (ROADMAP) **não** entram na sidebar: ela lista só destinos disponíveis. A
  distinção disponível × planejado continua na Home.

### Rodapé da conta (`.meta-env`)

- `border-top 1px --border; margin-top 16px; padding 10px 8px 0; color --text-3; font-size .82rem`.
- Linha 1: matrícula (mono) · nome do setor. Linha 2, a partir de `margin-top 8px`, botões
  compactos: **Senha** (link `.btn` para `definir_senha`, `aria-current` na própria tela),
  **Sair** (`<form method="post">` + `{% csrf_token %}` + `<button>`), **Claro / escuro**
  (`button[data-theme-toggle]`).
- Logout continua exclusivamente POST com CSRF, funcional sem JavaScript.

### Credencial provisória

O shell mínimo mantém a estrutura `.app`, mas a sidebar mostra só a marca **sem link** e o rodapé da
conta (Senha como item atual, Sair, tema). Nenhum item de navegação, nenhum grupo.

### Login (anônimo)

Sem sidebar. Card centralizado (`.card`, largura de formulário) sobre `--bg`, com a marca acima.
Composição derivada; pertence à etapa de propagação, não ao laboratório.

## 4. Cabeçalho de página (`.top`)

- `display flex; align-items center; justify-content space-between; gap 12px; flex-wrap wrap;
  margin-bottom 16px`.
- Esquerda: `h1` (`1.45rem`, peso 650, margem 0) e `.sub` (cor `--text-2`, `margin-top 2px`). Em
  telas internas, `.sub` pode trazer a trilha "Seção / item" com link, como em `request.png`.
- Direita: `.tools` (`gap 8px`), ações secundárias da página como `.btn`. A ação primária de um
  formulário fica no formulário, não no `.tools`.
- Mensagens (`django.contrib.messages`) logo abaixo do `.top`, antes do conteúdo.

## 5. Tipografia

| Papel | Valor |
|---|---|
| Raiz | `html { font-size: 14px }` (todos os `rem` são relativos a 14 px, como no upstream) |
| Família | `system-ui, "Segoe UI", Roboto, Helvetica, Arial, sans-serif` |
| Mono | `ui-monospace, "Cascadia Mono", Consolas, "SF Mono", Menlo, monospace`, `.88rem` |
| Corpo | `1rem` (14 px), `line-height 1.45`, cor `--text` |
| h1 | `1.45rem`, 650 |
| h2 (título de card) | `1rem`, 650, `margin 0 0 .7rem`; complemento opcional em `.note` inline |
| h3 (rótulo de grupo) | `.8rem`, 600, caixa-alta, `.04em`, `--text-2` (na sidebar `.7rem`, `--text-3`) |
| Label | `.85rem`, `--text-2` |
| Nota | `.88rem`, `--text-2` |
| Cabeçalho de tabela | `.8rem`, 600, `--text-2`, sem caixa-alta |
| Badge | `.78rem`, 600 |
| Valor de tile | `1.6rem`, 650, `tabular-nums` (rótulo `.82rem --text-2`; nota `.8rem --text-3`) |

- Atkinson Hyperlegible Next/Mono sai do produto: `static/css/fonts.css` e os arquivos em
  `static/vendor/fonts/` deixam de ser carregados e são removidos com as licenças OFL respectivas.
- Mono continua reservada a identificador opaco e dado técnico (CADPRO, matrícula, códigos do SCPI,
  documento de fornecedor). CADPRO é exibido inteiro, como texto, sem formatação.

## 6. Paletas

Valores exatos do upstream. Os nomes `--color-*` do WMS são mantidos como API dos CSS de feature e
passam a apontar para estes valores (mapa em `plano.md` → T3).

| Papel | Claro | Escuro |
|---|---|---|
| `--bg` | `#f4f4f2` | `#111110` |
| `--surface` | `#fcfcfb` | `#1a1a19` |
| `--surface-2` | `#efeeeb` | `#252523` |
| `--border` | `#dddcd6` | `#383835` |
| `--text` | `#0b0b0b` | `#ffffff` |
| `--text-2` | `#52514e` | `#c3c2b7` |
| `--text-3` | `#7b7a74` | `#8f8e86` |
| `--accent` | `#1c5cab` | `#86b6ef` |
| `--accent-bg` | `#e3eefc` | `#173a66` |
| `--series-1` (foco, glifo, borda de seleção) | `#2a78d6` | `#3987e5` |
| `--good` / `--good-bg` | `#0ca30c` / `#e2f4e2` | `#0ca30c` / `#12351a` |
| `--warning` / `--warning-bg` | `#fab219` / `#fdf0cf` | `#fab219` / `#40330d` |
| `--serious` / `--serious-bg` | `#ec835a` / `#fbe6dc` | `#ec835a` / `#46281a` |
| `--critical` / `--critical-bg` | `#d03b3b` / `#f8dddd` | `#d03b3b` / `#4a1c1c` |
| `--neutral-bg` | `#e9e8e4` | `#2e2e2b` |

- `color-scheme` acompanha o tema (`light`/`dark`).
- Regra do upstream mantida: cor de estado nunca carrega texto. O texto de badge, mensagem e linha
  de erro é `--text`; a cor de estado aparece no marcador de forma, no fundo `-bg` e na borda.
- Séries `--series-2..5` não entram (não há gráficos).

## 7. Forma, espaço e densidade

- Raios: painel/card/tile `8px`; controle, item de sidebar, mensagem `6px`; badge `10px`; chip `12px`;
  foco `3px`.
- Bordas: sempre `1px solid --border`. Sem sombra (a única sombra do upstream é a do tooltip, que
  não é portado).
- Espaços de referência: card `padding 14px 16px`, `margin-bottom 14px`; grid `gap 14px`; filtros
  `gap 8px`, `margin-bottom 10px`; célula `6px 10px`; pager `margin-top 10px`.
- Densidade desktop compacta: controles `min-height 30px`, `padding 5px 10px`.

## 8. Componentes

| Componente | Contrato |
|---|---|
| Botão `.btn` / `button` | `--surface`, borda `--border`, raio 6, `5px 10px`, `min-height 30px`, `inline-flex gap 6px`; hover `--surface-2` |
| Primário `.btn.primary` | fundo e borda `--accent`, texto `--surface`, 600 |
| Selecionado `.btn.on` | fundo `--accent-bg`, borda `--series-1` (página atual da paginação) |
| Destrutivo (derivado) | fundo e borda `--critical`, texto `#fff`, 600; usado só em confirmação de ação irreversível |
| Desabilitado (derivado) | fundo `--surface-2`, texto `--text-2`, borda `--border`, `cursor not-allowed`; rótulo ≥ 4,5:1 ("Enviando…" precisa ser lido) |
| Campo `input`/`select`/`textarea` | mesmo contrato do botão; `label` em grade `gap 3px`, `.85rem --text-2` acima do campo |
| Campo com erro (derivado) | borda `--critical`, `aria-invalid`, mensagem abaixo com marcador ▲ e texto `--text` |
| Filtros `.filters` | flex `gap 8px` `wrap`, busca principal `flex 1 1 320px`; código em mono |
| Card `.card` | `--surface`, borda, raio 8, `14px 16px`, `overflow-x auto` |
| Tile `.tile` | como card, `12px 14px`; `.k` rótulo, `.v` valor, `.d` nota |
| Grades | `.grid.tiles` `minmax(150px,1fr)`, `.grid.two` `minmax(380px,1fr)`, `gap 14px` |
| Tabela | `width 100%`, `collapse`, `tabular-nums`; `th` à esquerda, `.8rem` 600 `--text-2`, `6px 10px`, borda inferior, `nowrap`; `td` `6px 10px`, borda inferior, `vertical-align top`; última linha sem borda; hover de linha `--surface-2`; `.num` à direita |
| Ordenação | `th a` com `color inherit`; indicador `▲`/`▼` só na coluna vigente; `aria-sort` mantido. Em `(hover: none)`, colunas ordenáveis não vigentes mostram `↕` em `--text-3` (sem hover, o toque não descobre a ordenação) |
| Vazio `.empty` | `--text-3`, `padding 28px 10px`, centralizado; título + orientação |
| Paginação `.pager` | flex `space-between`, `margin-top 10px`, `--text-2`; esquerda "Página X de Y · N itens", direita botões numerados com reticências, atual em `.btn.on` + `aria-current` |
| `dl.kv` | grade `max-content minmax(0,1fr)`, `gap 4px 16px`, `dt --text-2` |
| Badge `.badge` | pílula `1px 8px`, raio 10, `.78rem` 600, `--neutral-bg`, texto `--text`; marcador `::before` 7 px: neutro círculo `--text-3`, `good` círculo, `warning` losango, `serious` quadrado, `critical` triângulo, `plain` sem marcador |
| Mensagem `.error-box` e família | `padding 8px 12px`, raio 6, `margin-bottom 12px`; erro `--critical-bg` + borda `--critical` (`role="alert"`); sucesso/aviso/informação derivados com `-bg` + borda do mesmo tom e o marcador de forma do badge (`role="status"`) |
| Tabs `.tabs` | links `7px 12px`, atual com borda inferior 2 px `--series-1` e peso 600 |
| Carregamento (derivado) | `.note` com spinner de borda 12 px (`--border`/`--series-1`), sem animação sob `prefers-reduced-motion` |
| Foco | `outline 2px solid --series-1`, `offset 2px`, raio 3 |

## 9. Responsivo

- **> 860 px**: shell desktop, contrato acima.
- **≤ 860 px** (tablet em retrato e celular). O upstream empilha a sidebar como bloco no topo com os
  links em linha; o WMS adapta (autorizado no prompt) para:
  - barra superior `--surface` com borda inferior, **estática** (não fixa, como o `.side` do
    upstream nessa largura): marca à esquerda, botão **Menu** (`aria-expanded`, `aria-controls`) à
    direita, altura mínima 44 px;
  - a navegação abre em fluxo abaixo da barra (não sobrepõe o conteúdo), com os mesmos grupos `h3`
    e itens de 44 px; o rodapé da conta fica no fim do painel;
  - sem JavaScript, a navegação aparece aberta; `Esc` fecha e devolve o foco ao botão;
  - `main` com `padding 14px 16px 40px` (upstream); `.grid.two` em uma coluna.
- **Toque** (`pointer: coarse`, qualquer largura) e **≤ 860 px**: controles, itens de navegação e
  links de paginação com `min-height 44px`; campos com `font-size 16px` (evita o zoom do iOS); a
  linguagem visual (cores, bordas, raios, tipografia) é a mesma.
- **Tabelas**: nunca viram cards. O card rola na horizontal (`overflow-x auto`), com largura mínima
  por coluna para não esmagar dados; CADPRO e números `nowrap`; descrição quebra linha; conteúdo
  truncado visualmente continua acessível por inteiro (`<details>` existente do detalhamento).
- **Filtros**: em ≤ 640 px os campos ocupam a largura toda, um por linha, e Buscar/Limpar ficam lado a
  lado com 44 px.

## 10. Tema

- Padrão: preferência do sistema (`prefers-color-scheme`). O botão alterna e persiste em
  `localStorage` (`wms-tema`), com `try/catch` (armazenamento indisponível não quebra a página).
- Diferença deliberada: o tema salvo é aplicado por um script mínimo inline no `<head>`, antes da
  primeira pintura, em vez de no `defer` do upstream (evita o flash de tema errado). O listener do
  botão fica em `static/js/shell.js` (que também controla o menu móvel), carregado uma vez no `<head>` (`defer`), por delegação em
  `document` — sobrevive às trocas de `<body>` da restauração de histórico do HTMX 4 sem duplicar.

## 11. Estados

Toda superfície do laboratório mostra, quando aplicável: carregando, vazio, nenhum resultado, erro de
validação, erro de servidor/rede, sucesso, indisponível/impedido e confirmação. Estado nunca só por
cor (forma + texto). Foco visível em todo controle, nos dois temas.

## 12. Composição do laboratório

### Home

- `.top`: h1 "Início"; `.sub` com a descrição curta da tela.
- `.grid.tiles` com três tiles **não clicáveis** de identidade: Matrícula (mono), Setor, Papéis
  (badges `plain`; "Nenhum papel de negócio atribuído" quando vazio). São dados de identidade, não
  indicadores.
- "Suas tarefas": `.grid.two` de cards, um por grupo da navegação com itens disponíveis; cada card
  tem `h2` com o nome do grupo e uma tabela sem cabeçalho visível (Tarefa link + descrição). Mesmos
  destinos e mesmas flags da sidebar.
- Nenhuma tarefa: card com `.empty` e a orientação atual.
- "Em preparação": card com `h2` e nota inline "ainda indisponíveis nesta versão"; tabela de
  uma coluna, com Função + badge `plain` "Planejado" na primeira linha e descrição abaixo,
  sem link, texto `--text-2`. A L9 substituiu as três colunas inicialmente previstas para evitar
  células estreitas e linhas excessivamente altas no celular. O finish review da retomada aceitou
  a composição também no desktop, por manter a associação e a leitura compacta; ela integra o
  checkpoint de aceite visual do dono do produto.
- Nada de contadores, gráficos ou alertas.

### Consulta do catálogo

- `.top`: h1 "Consulta do catálogo", `.sub` com a descrição atual.
- Formulário `.filters` com labels visíveis (diferença deliberada: o upstream oculta o label; o WMS
  precisa de label, dica e erro associados): Código (CADPRO, mono), Descrição (flex), Buscar
  (primário), Limpar.
- Linha de estado (carregando, anúncio de ordenação para leitor de tela) e alertas de falha de rede
  e de servidor (`.error-box`), na mesma ordem e com os mesmos IDs.
- `.card` com a tabela e o `.pager` dentro, como `list.html`. Colunas: Código (CADPRO) mono `nowrap`,
  Descrição, Saldo `.num`, Unidade, Classificação (SCPI), Detalhamento (`<details>`).
- Vazio inicial, nenhum resultado e código inválido conforme os estados atuais.

## 13. Diferenças deliberadas em relação ao upstream

| # | Diferença | Motivo |
|---|---|---|
| 1 | Textos em pt-BR, marca "Almoxarifado SAEP" e glifo próprio | Produto e idioma do WMS; glifo de observabilidade não descreve almoxarifado |
| 2 | Sem Live, gráficos, busca por linguagem, exports, intervalo de tempo, contadores na sidebar | Não existem nos fluxos do WMS (prompt do redesign) |
| 3 | Rodapé da sidebar com conta (matrícula, setor, Senha, Sair) | O WMS precisa de identidade e logout no shell; o upstream mostra serviço/ambiente |
| 4 | Labels visíveis, dica e erro nos filtros | Validação de CADPRO com mensagem associada ao campo |
| 5 | Paginação numerada no `.pager` | Requisito existente da paginação do WMS; o upstream só tem "Newer/Older" |
| 6 | Shell ≤ 860 px com botão Menu e alvos de 44 px; campos 16 px no toque | Uso operacional em celular/tablet (autorizado) |
| 7 | Tema inicial aplicado inline no `<head>` | Evita flash; o resto da lógica é a do upstream |
| 8 | Botão destrutivo, desabilitado, campo com erro, mensagens de sucesso/aviso/informação, spinner | Estados que o WMS exige e o upstream não define; derivados dos tokens e da gramática de badge |
| 9 | Indicador de ordenação por texto `▲`/`▼` em vez do SVG duplo atual | Fidelidade ao `list.html`; `aria-sort` preserva a semântica |
| 10 | Atkinson removida | O upstream usa a fonte do sistema |
| 11 | `↕` nas colunas ordenáveis só em `(hover: none)` | Sem hover, o upstream não revela quais colunas ordenam |
| 12 | Itens de navegação e tarefas montados no servidor a partir das capabilities | Constitution V: dado de decisão chega pronto da view; o upstream decide no template |
| 13 | Desabilitado com texto `--text-2`, não `--text-3` | `--text-3` sobre `--surface-2` mede ~3,75:1 no claro; o rótulo de processamento precisa ser lido |
| 14 | Links em texto corrido sublinhados; navegação, botões e links de tabela sem sublinhado | O upstream remove o sublinhado de todo link; em prosa isso deixa o link só pela cor (#1c5cab sobre #0b0b0b ≈ 2,97:1) — revisão funcional L7, P2 |
