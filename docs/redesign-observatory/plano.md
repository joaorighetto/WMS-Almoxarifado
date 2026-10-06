# Plano — redesign da interface de produto baseado no django-observatory

Plano persistido e retomável. Contrato visual: [`contrato.md`](contrato.md). Direction contract:
`.impeccable/surfaces/contas-templates-contas-home-html.md`. Decisão estrutural do shell:
[`docs/adr/0002-app-shell-sidebar-contextual.md`](../adr/0002-app-shell-sidebar-contextual.md).

**Natureza do trabalho.** Redesign transversal de capacidades existentes. Não é capacidade do
`ROADMAP.md` e não muda o status de nenhuma feature. Não altera rotas, contratos de entrada,
resultados de fluxo, permissões, invariantes, models nem stack. Não há ciclo de Spec Kit: nenhum
requisito funcional muda.

**Decisões do dono do produto (prompt de 2026-10-05), não reabrir:** escopo final = todas as
superfícies de produto; execução incremental; laboratório = shell + Home + consulta do catálogo;
checkpoint humano obrigatório antes da propagação; fidelidade desktop prioritária; adaptações de
navegação/toque/formulário autorizadas no celular; temas claro e escuro na entrega; só a camada de
apresentação é portada; Django Admin técnico fora.

## Estado

| Etapa | Estado |
|---|---|
| Estudo da referência e contrato | concluído (2026-10-05) |
| Laboratório (L1–L10) | concluído tecnicamente em 2026-10-05; evidências da retomada abaixo |
| Checkpoint humano | aceito pelo dono do produto em 2026-10-05 (laboratório integrado à `main` pelo PR #27) |
| Propagação (P1–P6) | P1 concluído na branch `redesign/observatory-p1-credenciais` (aguarda commit/PR); P2–P6 pendentes |

Atualize esta tabela e a coluna "Etapa/estado" da matriz ao fechar cada tarefa.

## 1. Inventário de superfícies e matriz de cobertura

Papéis: REQ requisitante · AUX auxiliar de setor · CS chefe de setor · FA funcionário do
almoxarifado · CA chefe do almoxarifado · AUD gestor/auditor · ADM administrador de sistema.
Papel de captura = conta do `seed_dev` usada com `?dev_como=` (ver
`docs/development/login-simulado.md`).

| # | Superfície (template) | Rota | Quem usa | Captura como | HTMX/JS | Etapa/estado |
|---|---|---|---|---|---|---|
| S1 | Shell (`contas/base.html` + sidebar) | todas autenticadas | todos | requisitante, auditor, chefe-almoxarifado, administrador-sistema | `shell.js` (tema, menu) | Lab concluído; aguarda aceite |
| S2 | Shell mínimo de credencial provisória (`senha.html` com `provisoria`) | `definir_senha` | conta com senha provisória | `critica.provisoria` | `envio.js` | P1 concluído |
| S3 | Home (`contas/home.html`) | `home` | todos | requisitante, auditor, chefe-almoxarifado, administrador-sistema, sem papel | — | Lab concluído; aguarda aceite |
| S4 | Consulta do catálogo (`catalogo/consulta.html`) | `catalogo:consulta` | REQ | requisitante | HTMX: filtros, ordenação, paginação, OOB, histórico | Lab concluído; aguarda aceite |
| S5 | Parciais compartilhados (`interface/_paginacao`, `_th_ordenavel`, `_mensagens`, `_consulta_falha`) | várias | — | via S4 | HTMX | Lab concluído; compatibilidade herdada conferida (afeta S6, S10, S11, S20) |
| S6 | Consulta de fornecedores | `fornecedores:consulta` | FA | funcionario-almoxarifado | HTMX igual a S4 | P2 |
| S7 | Login (`contas/login.html`) | `login` | anônimo | anonimo | `login.js` | P1 concluído |
| S8 | Troca voluntária de senha (`contas/senha.html`) | `definir_senha` | todos | requisitante | `envio.js` | P1 concluído |
| S9 | Envio de importação do catálogo | `catalogo:importacao_envio` | CA | chefe-almoxarifado | `envio.js` | P3 |
| S10 | Prévia de importação do catálogo (+ confirmar/cancelar) | `catalogo:importacao_previa` | CA | chefe-almoxarifado | `envio.js` | P3 |
| S11 | Histórico de importações do catálogo | `catalogo:historico` | CA | chefe-almoxarifado | `linha-clicavel.js` | P2 |
| S12 | Execução de importação do catálogo | `catalogo:execucao_detalhe` | CA | chefe-almoxarifado | — | P2 |
| S13 | Envio de importação de fornecedores | `fornecedores:importacao_envio` | CA | chefe-almoxarifado | `envio.js` | P3 |
| S14 | Prévia de importação de fornecedores | `fornecedores:importacao_previa` | CA | chefe-almoxarifado | `envio.js` | P3 |
| S15 | Histórico de importações de fornecedores | `fornecedores:historico` | CA | chefe-almoxarifado | `linha-clicavel.js` | P2 |
| S16 | Execução de importação de fornecedores | `fornecedores:execucao_detalhe` | CA | chefe-almoxarifado | — | P2 |
| S17 | Entradas | `estoque:entradas` | FA, AUD | funcionario-almoxarifado, auditor | `linha-clicavel.js` | P4 |
| S18 | Registrar entrada (composição, resumo, recusa) | `estoque:entrada_nova` (+ `entrada_confirmar`) | FA | funcionario-almoxarifado | HTMX `#entrada-composicao`, `estoque.js` | P4 |
| S19 | Detalhe da entrada | `estoque:entrada_detalhe` | FA, AUD (estorno: CA) | funcionario-almoxarifado, chefe-almoxarifado | — | P4 |
| S20 | Estorno de entrada (confirmação destrutiva) | `estoque:entrada_estorno` | CA | chefe-almoxarifado | `estoque.js` | P4 |
| S21 | Usuários (lista) | `usuarios` | ADM | administrador-sistema | HTMX `#resultados-usuarios` | P5 |
| S22 | Novo usuário / editar / papéis / transferir | `usuario_novo`, `usuario_editar`, `usuario_papeis`, `usuario_transferir` | ADM | administrador-sistema | HTMX `#papeis-cadastro`, `envio.js` | P5 |
| S23 | Ficha do usuário (+ histórico) | `usuario` | ADM | administrador-sistema | — | P5 |
| S24 | Desativar / reativar usuário, redefinir senha (confirmações) | `usuario_desativar`, `usuario_reativar`, `usuario_redefinir_senha` | ADM | administrador-sistema | `envio.js` | P5 |
| S25 | Senha entregue (segredo exibido uma vez) | resposta de `usuario_novo`/`usuario_redefinir_senha` | ADM | administrador-sistema | `copiar.js` | P5 |
| S26 | Setores (lista) e ficha | `setores`, `setor` | ADM | administrador-sistema | — | P5 |
| S27 | Setor novo/editar, chefia, ativar/desativar (impedimentos, recusas) | `setor_novo`, `setor_editar`, `setor_chefia`, `setor_ativar`, `setor_desativar` | ADM | administrador-sistema | `envio.js` | P5 |

Fora do escopo: Django Admin técnico (`/admin/`). Não há templates próprios de erro 403/404/500;
o projeto usa as páginas padrão do Django. Criar essas páginas seria superfície nova — decisão do
dono do produto, registrada como pendência para o checkpoint, não feita por conveniência.

## 2. Mapeamento Observatory → WMS

| Observatory (`app.css`/templates) | WMS | Observação |
|---|---|---|
| `.app`, `.side`, `.brand`, `.side nav`, `.side h3`, `aria-current` | `contas/base.html` + `contas/_navegacao.html` (substitui `_barra_trabalho.html`) | itens vindos de `navegacao.grupos` |
| `.meta-env` + `[data-theme-toggle]` | rodapé da conta na sidebar | matrícula, setor, Senha, Sair (POST), tema |
| `.main`, `.top`, `h1`, `.sub`, `.tools` | blocos `heading`, `sub`, `tools` do `base.html` | substitui `.page-header` e `.page-container` |
| `.card`, `.grid.two/.three`, `.tile` | `.card`, `.grid`, `.tile` em `components.css` | substitui `.home-id-plate`, `.home-task-list`, `.form-frame`, `.summary` progressivamente |
| `button`, `.btn`, `.btn.primary`, `.btn.on` | `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger` | nomes WMS mantidos (há consumidores em todos os templates); valores do upstream |
| `label`, `input`, `select`, `.filters`, `form.grid` | `.field`, `.filter-bar` | labels visíveis (diferença 4) |
| `table`, `th`, `td`, `.num`, `.table-wrap`, `.empty` | `.table`, `.table-wrapper`, `.table-cell-numeric`, `.table-cell-code`, `.table-empty-row` | nomes WMS mantidos, regras do upstream |
| `th a` + `▲/▼` | `interface/_th_ordenavel.html` | `aria-sort`, IDs e `hx-*` preservados |
| `.pager` | `interface/_paginacao.html` | numerada, IDs de foco preservados |
| `.badge` + forma | `.badge`, `.badge-success/-warning/-danger/-neutral/-info/-planned` | marcador `::before` com forma |
| `.error-box`, `.note` | `.alert`, `.alert-danger/-success/-warning/-info`, `interface/_mensagens.html`, `_consulta_falha.html` | `role` preservado |
| `dl.kv` | `.metadata` (ficha, detalhe) | propagação |
| `.tabs` | — | só se uma superfície já tiver abas |
| `.chip`, gráficos, `.tip`, `#graph`, `.bars`, `.wf`, Live, `_range.html` | — | não portados |

## 3. Arquivos e contratos afetados

**Laboratório**

- `static/css/tokens.css` — valores do upstream nos nomes `--color-*` existentes; tokens novos
  (`--color-text-subtle`, `--color-series-1`, `--color-*-indicator`, `--color-neutral-surface`,
  `--sidebar-width`); tema escuro (`prefers-color-scheme` + `[data-theme]`); `html` 14 px;
  remoção de `--appbar-height`, `--color-ink*`, `--color-signal`, `--color-on-ink*` quando o último
  consumidor sair.
- `static/css/base.css` — reset compatível com o upstream, sem `scroll-padding-top` da barra.
- `static/css/components.css` — primitivas reescritas segundo o contrato; seções de barra de
  trabalho, marcador de tubulação e fita removidas quando sem consumidores; seção nova de shell.
- `static/css/fonts.css`, `static/vendor/fonts/*` — removidos.
- `static/js/shell.js` (novo) — tema e menu móvel por delegação em `document`.
- `contas/templates/contas/base.html` — shell novo, script de tema inline no `<head>`, `shell.js`
  no `<head>`, blocos novos.
- `contas/templates/contas/_navegacao.html` (novo) e remoção de `_barra_trabalho.html`.
- `contas/templates/contas/home.html`, `contas/static/contas/css/home.css`.
- `catalogo/templates/catalogo/consulta.html`, `catalogo/static/catalogo/css/catalogo.css`.
- `interface/templates/interface/_paginacao.html`, `_th_ordenavel.html`, `_mensagens.html`,
  `_consulta_falha.html` — markup preservado, classes/estilo conforme contrato.
- `contas/templates/contas/senha.html` — deixa de sobrescrever `appbar`; o shell mínimo vem do
  `base.html`.
- `contas/navegacao.py` (novo), `contas/context_processors.py` (novo),
  `config/settings/base.py` (`TEMPLATES.context_processors`), `contas/views.py` (`HomeView` passa a
  usar a mesma fonte).
- Testes: `tests/test_barra_trabalho.py` (substituído por testes do shell),
  `tests/test_contas_home_papeis.py`, `tests/test_contas_home.py`,
  `tests/test_contas_views_organizacao.py`, `tests/test_catalogo_consulta.py` e novos testes de
  navegação.
- Documentação: `DESIGN.md`, `.impeccable/design.json` (documenter, no fim), `docs/adr/0002-*`,
  `docs/adr/0001-*` (status), `docs/adr/README.md`, `THIRD-PARTY-NOTICES.md`.

**Contratos que não podem mudar:** nomes de rotas e querystrings; IDs `#resultados-consulta`,
`#resultados-indicador`, `#resultados-anuncio`, `#campo-codigo`, `#campo-ordem`,
`#resultados-erro-rede`, `#resultados-erro-servidor`, `ordenar-<coluna>`, `pagina-*`; `hx-*` e
`hx-on::*` da consulta; `meta htmx-config` e `<script>` do HTMX no `<head>`; `body_attrs`;
`data-estado`; `aria-sort`, `aria-current`, `aria-describedby`; partial
`consulta.html#resultados_consulta` sem shell; cabeçalhos `Vary`, `HX-Reswap`, `HX-Push-Url`;
logout POST + CSRF; `data-processing-*`, `data-linha-*`, `data-copiar-*`, `data-login-*`;
CADPRO exibido sem transformação (`INV-CATALOG-001`).

### Contrato de navegação (servidor)

- `contas/navegacao.py` concentra os destinos de navegação: grupos ordenados (Catálogo,
  Fornecedores, Estoque, Administração) e itens (rótulo, descrição usada na Home, nome de rota,
  chave). As flags são as mesmas de hoje (`pode_*`, mesmo conjunto de papéis da `HomeView`, papel
  explícito, sem herança, sem `is_staff`).
- Context processor `contas.context_processors.navegacao` expõe `navegacao`, **preguiçoso**
  (só consulta o banco se o template o usar): `grupos` filtrados por capability, item `atual`
  marcado a partir de `request.resolver_match` (mapa de rota → chave, incluindo telas internas de
  fluxo), `provisoria` (`senha_provisoria_em is not None`, mesma regra do
  `CredencialProvisoriaMiddleware`). Anônimo: nada.
- No máximo **uma** consulta de papéis por requisição, compartilhada entre a sidebar e a
  `HomeView`. Teto de queries da Home (10) mantido. Sem consulta por item de menu.
- `HomeView` mantém no contexto as flags `pode_*`, `papeis`, `setor` e `capacidades_planejadas`
  (testes leem `response.context`).

### Ganchos de markup compartilhados por testes e implementação

- Sidebar: `<aside class="side">`, `<nav aria-label="Seções">`; item atual com
  `aria-current="page"`; grupos em `<h3>`.
- Marca: link para `home` com classe `brand`; na Home, `aria-current="page"` no item Início.
- Logout: um único `<form method="post" action="/logout/">` com CSRF por página.
- Tema: `button[data-theme-toggle]`; `<script>` inline de tema e `shell.js` no `<head>`, uma vez.
- Menu móvel: `button[aria-controls]` com `aria-expanded`.
- Home: seção de tarefas e seção "Em preparação" identificáveis por `aria-labelledby`.
- Fragmentos HTMX: sem `class="side"`, sem `action="/logout/"`, sem "Almoxarifado SAEP".

### Compatibilidade das telas ainda não propagadas

- `base.html` mantém `{% block content %}` como encaixe legado: por padrão ele renderiza o
  `<main class="main" id="main">` novo (com `.top` e o bloco interno das páginas novas); uma tela
  legada que sobrescreve `content` continua trazendo o próprio `<main>`, sem `<main>` aninhado.
- As telas legadas ficam dentro do `.app`, com os tokens novos, sem recomposição. Ajustes
  permitidos: só o necessário para continuarem legíveis e operáveis nos dois temas (por exemplo
  `.page-container` sem teto de 1120 px fora do lugar, cores herdadas de tokens removidos).
- Login (anônimo) continua sem shell e funcional; sua recomposição é P1.

## 4. Tarefas em ordem de dependência

| ID | Tarefa | Responsável | Limite de escrita | Depende de |
|---|---|---|---|---|
| L0 | Contrato, brief, plano, ADR 0002, avisos de terceiros | Claude principal | `docs/`, `.impeccable/surfaces/`, `THIRD-PARTY-NOTICES.md` | — |
| L1 | Testes do contrato de navegação (falhando) | `test-engineer` | `tests/` | L0 |
| L2 | `contas/navegacao.py`, context processor, `HomeView` | `task-implementer` | `contas/navegacao.py`, `contas/context_processors.py`, `contas/views.py` (`HomeView`), `config/settings/base.py` (só `context_processors`) | L1 |
| L3 | Fundação: tokens, base, componentes, shell, sidebar, `shell.js`, remoção da Atkinson, shell provisório, compatibilidade legada | `frontend-implementer` | `static/css/`, `static/js/shell.js`, `static/vendor/fonts/`, `contas/templates/contas/base.html`, `_navegacao.html`, `_barra_trabalho.html`, `senha.html` (só o shell), CSS de feature (só compatibilidade) | L2 |
| L4 | Home e consulta do catálogo; parciais `interface/` | `frontend-implementer` (continuação) | `home.html`, `home.css`, `catalogo/consulta.html`, `catalogo.css`, `interface/templates/interface/*` | L3 |
| L5 | Atualizar testes de markup quebrados por decisão do contrato; novos testes de shell, tema, provisório, fragmentos | `test-engineer` | `tests/` | L4 |
| L6 | Verificação: `make verify`; inspeção no navegador; capturas | Claude principal | `.impeccable/review/` | L5 |
| L7 | Revisão funcional | `code-reviewer` | — | L6 |
| L8 | `impeccable detect` + gate visual | Claude principal + `impeccable-finish-reviewer` | `.impeccable/review/` | L7 |
| L9 | Correções de findings (P0/P1; P2 do escopo) e nova revisão quando material | `frontend-implementer` / `task-implementer` / `debugger` | conforme finding | L7, L8 |
| L10 | `DESIGN.md` e sidecar a partir do código; conferência contra CSS e templates; atualização deste plano | `impeccable-documenter` + Claude principal | `DESIGN.md`, `.impeccable/design.json`, `docs/redesign-observatory/` | L9 |
| — | **Checkpoint humano. PARAR.** | Claude principal | — | L10 |

### Propagação (após aceite explícito)

| ID | Lote | Superfícies | Motivo da posição |
|---|---|---|---|
| P1 | Credenciais | S7, S8 | Login é a única tela fora do shell; fecha a autenticação junto do shell provisório |
| P2 | Consultas e históricos | S6, S11, S12, S15, S16 | Reusam diretamente tabela, pager e filtros do laboratório |
| P3 | Importações | S9, S10, S13, S14 | Prévia e confirmação usam componentes de resumo derivados |
| P4 | Estoque | S17–S20 | Operação crítica: confirmação, recusa e estorno destrutivo |
| P5 | Organização | S21–S27 | Maior número de formulários, impedimentos e confirmações |
| P6 | Limpeza e fechamento | CSS legado sem consumidor, encaixe `content` legado, prompts dos agentes que descrevem a fundação antiga (`.claude/agents/frontend-implementer.md` e espelho Codex), `DESIGN.md` final | Só quando nenhuma tela usar a fundação anterior |

Cada lote: `frontend-implementer` → testes do lote → `code-reviewer` → `impeccable critique` nas
superfícies entregues (papel correto por tela) → correções → atualização incremental de `DESIGN.md`
(`impeccable document` em modo scan, ou `impeccable-documenter` sob este contrato) → atualizar este
plano.

## 5. Verificações e evidências esperadas

| Verificação | Comando/ferramenta | Evidência |
|---|---|---|
| Suíte e checks | `make verify` (`scripts/verify.sh`: `uv lock --check`, `ruff`, `check`, `check --deploy`, `pytest`) | saída completa, 0 falhas |
| Subconjuntos durante as tarefas | `make test PYTEST_ARGS="..."` | saída |
| Navegação por papel | testes + navegador com `?dev_como=` | sidebar de requisitante, auditor, chefe-almoxarifado, administrador-sistema |
| Acesso direto a rota protegida | testes existentes de 403/redirect | inalterados e verdes |
| Credencial provisória | teste de markup novo + captura | shell sem navegação |
| Logout e CSRF | testes + inspeção | um form POST por página |
| Filtros, ordenação, paginação, histórico HTMX | testes + navegador (voltar/avançar, rede de dev) | sem shell duplicado, sem script duplicado, foco e anúncio |
| Tema | navegador: sistema, alternância, persistência, após troca HTMX e voltar | capturas claro/escuro |
| Telas herdadas | captura rápida de S6, S7, S11, S17, S21 nos dois temas | legíveis e operáveis |
| Detector | `.claude/skills/impeccable/scripts/impeccable detect --json` nos alvos alterados | achados tratados ou repassados |

### Matriz de capturas do laboratório

| Superfície | Papel | 1440×900 claro | 1440×900 escuro | 1280×800 | 820×1180 (tablet, toque) | 390×844 claro | 390×844 escuro |
|---|---|---|---|---|---|---|---|
| Home | chefe-almoxarifado (menu maior) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Home | requisitante (menu mínimo) | ✓ | | | | ✓ | |
| Home | administrador-sistema | ✓ | | | | | |
| Home | auditor | ✓ | | | | | |
| Consulta catálogo — resultados | requisitante | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Consulta — código inválido | requisitante | ✓ | | | | ✓ | |
| Consulta — nenhum resultado | requisitante | | ✓ | | | | |
| Menu móvel aberto | chefe-almoxarifado | | | | ✓ | ✓ | ✓ |
| Shell provisório | conta com senha provisória | ✓ | | | | ✓ | |

Arquivos em `.impeccable/review/` (`desktop.png` e `mobile.png` exigidos pelo finish reviewer, mais
um arquivo por cenário da matriz). A retomada gerou **44 cenários**, cada um com full-page e
`*-viewport.png`, além de `captures.json` (papel, viewport, tema, mídia observada, navegação e
geometria). Inclui S6/S7/S11/S17/S21 em ambos os temas, conta provisória e Home sem papel.
O roteiro persistido é `docs/redesign-observatory/capturar.mjs` (Node ≥22 + Chrome instalado,
sem dependências npm), com `--capturas`, `--interacoes` e seleção `--alvos=`. A comparação com o upstream usa `docs/images/*.png` do commit
fixado: geometria (216 px, paddings, alturas de linha), tipografia (tamanho/peso/entrelinha),
espaçamento, bordas, cores e densidade, medidos por `getComputedStyle` e inspeção lado a lado.

### Comparação medida com o upstream (rodada 1, Chrome, macOS, 1440 × 900)

Valores lidos por `getComputedStyle` na Home e na consulta, comparados ao `app.css` do commit fixado.

| Elemento | Upstream (`app.css`) | WMS medido |
|---|---|---|
| Raiz / corpo | 14px; `line-height 1.45`; `#f4f4f2` / `#0b0b0b`; `system-ui` | 14px; 20.3px; `rgb(244,244,242)` / `rgb(11,11,11)`; `system-ui, "Segoe UI", …` |
| Sidebar | 216px; `#fcfcfb`; borda `#dddcd6`; `14px 10px`; sticky | x0 w216 h900; `rgb(252,252,251)`; `rgb(221,220,214)`; `14px 10px`; sticky |
| Item de navegação / atual | `5px 8px`, raio 6, `--text-2`; atual `#e3eefc` / `#1c5cab` / 600 | `5px 8px`, 6px; atual `rgb(227,238,252)` / `rgb(28,92,171)` / 600 |
| Rótulo de grupo | `.7rem`, `--text-3`, `14px 8px 4px`, caixa-alta `.04em` | 9.8px, `rgb(123,122,116)`, `14px 8px 4px`, uppercase, 0.392px |
| Coluna principal | `18px 24px 48px`, sem teto | x216, `18px 24px 48px`, largura restante |
| `h1` / `.sub` / `.top` | 1.45rem 650 / `--text-2` +2px / margem 16px | 20.3px 650 / `rgb(82,81,78)` 2px / 16px |
| Card | `#fcfcfb`, borda, raio 8, `14px 16px` | idem |
| Célula / `h2` | `6px 10px` / 1rem 650 `0 0 .7rem` | `6px 10px` / 14px 650 `0 0 9.8px` |
| Controle | `min-height 30px`, `5px 10px`, raio 6 | 30px, `5px 10px`, 6px |
| Badge / valor de tile | `.78rem`, `1px 8px`, raio 10 / 1.6rem 650 | 10.92px, `1px 8px`, 10px / 22.4px 650 |
| Rodapé da conta | `.82rem`, `--text-3`, borda superior, `margin-top 16px`, `padding-top 10px` | 11.48px, `rgb(123,122,116)`, idem |
| Tema escuro | `#111110` fundo, `color-scheme: dark` | `rgb(17,17,16)`, `dark` |

A fonte renderizada difere (SF Pro no macOS; Ubuntu nas capturas do upstream), como previsto no contrato.

## 6. Critérios de conclusão

**Laboratório:** L1–L10 fechados; `make verify` verde; contratos HTMX da consulta conferidos no
navegador; shell correto em todos os papéis da matriz; tema persistido nos dois sentidos; telas
herdadas legíveis; `code-reviewer` sem P0/P1 abertos; finish review com disposição `ship` ou fixes
resolvidos (ou tabela pendente apresentada); `DESIGN.md` e sidecar refletindo o código; este plano
atualizado.

**Propagação (cada lote):** superfícies do lote recompostas, testes, review, critique, docs.

**Conclusão total:** critérios do prompt, seção 11 — inventário coberto, uma fundação, dois temas,
fluxos/permissões/invariantes preservados, origem e licença registradas, limitações informadas.

## 7. Ponto de parada do laboratório

Depois de L10, entregar ao dono do produto: resumo, capturas da Home e do catálogo (desktop e
celular, claro e escuro), evidência da navegação por papel, comparação objetiva com a referência,
diferenças deliberadas, resultados de testes e reviews, findings pendentes, arquivos alterados e o
plano restante. **Nenhum lote de propagação começa sem aceite visual explícito.**

## 8. Registro de execução

| Data | Tarefa | Resultado |
|---|---|---|
| 2026-10-05 | L0 | Referência conferida (wheel 0.1.0 ≡ commit 6edda16); contrato, brief (seed 5138d9c5, canon fixado), plano, ADR 0002, avisos MIT. Gate de contrato aprovado pelo dono do produto |
| 2026-10-05 | L1 | `tests/test_navegacao.py` (150 testes; 147 falhando por ausência da implementação, 3 guardas de regressão) |
| 2026-10-05 | L2 | `contas/navegacao.py`, `contas/context_processors.py`, `HomeView` na mesma fonte; `test_navegacao.py` + Home: 195 passed; suíte completa 2895 passed, 3 skipped (relato do implementador; subconjunto reconferido pelo coordenador) |
| 2026-10-05 | L3 | Tokens/base/componentes reescritos, shell + `_navegacao.html` + `shell.js`, Atkinson removida, `_barra_trabalho.html` removido. Suíte: 2886 passed, 3 skipped, 9 failed (5 igualdade de hrefs da Home por marca/Início/skip link; 4 busca de setor captura o setor do rodapé) — decisão do contrato, para L5. Decisões: marca segue o código do upstream; desabilitado com `--text-2` |
| 2026-10-05 | L4 | Home e consulta do catálogo recompostas nos blocos novos; `home.css` removido; `_th_ordenavel` com ▲/▼ e ↕ em `(hover: none)`; mensagens na família `.error-box`. Mesmas 9 falhas da L3, sem regressão |
| 2026-10-05 | L6 (rodada 1) | Navegador (8011): valores computados conferidos contra `app.css`; HTMX ao vivo (ordenar, paginar, voltar/avançar, código inválido), tema (alternância, persistência, após restauração de histórico) OK. 33 capturas em `.impeccable/review/` sem overflow horizontal. Defeitos enviados em lote: barra móvel sem respiro (F1), Detalhamento inflando linhas em tablet/celular (F2), linha de estado ociosa ocupando ~40px (F3) |
| 2026-10-05 | L5 | `tests/test_shell.py` (67), `tests/html_helpers.py` + `tests/test_html_helpers.py` (7); hrefs da Home escopados à seção de tarefas, mais igualdade sidebar = tarefas ∪ {/}; busca de setores escopada ao `<main>`; `tests/test_barra_trabalho.py` removido (cenários realocados) |
| 2026-10-05 | L6 (rodada 2) | F1–F3 corrigidos e confirmados na recaptura (31 capturas + 2 do shell provisório, sem overflow); indicador do HTMX confirmado ao vivo; `make verify` verde: 2969 passed, 3 skipped. Detector: 13 avisos consultivos "fora do DESIGN.md", nenhum não consultivo |
| 2026-10-05 | L7 | `code-reviewer`: sem P0/P1. P2 links em prosa só por cor → L9; P3 tema inerte sem JS → L9; P3 contrato citava `tema.js` → corrigido |
| 2026-10-05 | L8 | Detector: só consultivos. `impeccable-finish-reviewer`: disposição **fix**, 8 correções; 6 enviadas à L9 (largura da Descrição e pista de rolagem ≤640; "Em preparação" ≤640; Classificação inline; tiles ≤640 e alinhamento; nota inline). Não aplicadas: painel provisório aberto (aberto pelo script de captura) e scroll interno de 60vh das tabelas herdadas (preexistente no HEAD → P2) |
| 2026-10-05 | L9 — retomada, rodada 1 | R1/R2 e V1–V6 conferidos no código; `make verify`: 2969 passed, 3 skipped; 44 cenários recapturados em Chrome via CDP. Revisão funcional L9 independente sem findings relevantes. Finish verdict: V1/V2/V4/V5/V6 resolvidos; V3 parcial no tablet; disposição **fix**. Coluna única de "Em preparação" aceita no gate e registrada no contrato §12 |
| 2026-10-05 | L9 — rodada 2 | `catalogo.css`: Classificação com mínimo de 16rem; sete consultas afetadas recapturadas. Finish verdict: V3 resolvido, demais itens mantidos, sem regressão; disposição **ship**, limitada a V1–V6. Verificação final: 2969 passed, 3 skipped em 111,53s. Dez checks do navegador passaram, incluindo HTMX/histórico, tema, menu e sem JS. Relatório: `reviews-laboratorio.md`; logs e JSON em `.impeccable/review/` |
| 2026-10-05 | L10 / checkpoint | DESIGN.md e sidecar schemaVersion 2 reescritos pelo `impeccable_documenter`; coordenador conferiu tokens, componentes, CSS de feature e templates, 37 cores, 44 refs e 10 snippets. Detector final: 9 consultivos, nenhum determinístico; limitações de leitura de templates Django registradas. Checkpoint em `checkpoint.md`, com capturas, navegação, comparação, diferenças, limites, arquivos e P1–P6. Aguarda aceite; propagação não iniciada |
| 2026-10-05 | Aceite | Dono do produto aceitou o checkpoint e pediu a propagação; laboratório integrado à `main` (#27). P1 iniciado em branch própria |
| 2026-10-05 | P1 (em andamento) | Login/senha recompostos; review funcional sem P0–P2 (3 rodadas); gate visual: rodada 1 (29/40 login, 26/40 senha) e rodada 2 (31/40, 29/40) com correções aprovadas pelo dono do produto (foco/ARIA de erro, shell provisório sem Menu ≤860px, textos, mostrar senha, política na Nova senha, dicas, username oculto, Caps Lock, divergência no cliente). Decisões: e-mail do almoxarifado mantido; contrastes do upstream (rótulos/rodapé da sidebar, borda de campo) mantidos por fidelidade; fechamento por conferência sem 3ª rodada. Pendente: testes e review da 3ª leva, recaptura (falhou com erro do Node na última tentativa), DESIGN.md/sidecar (`.field-check`, `.field-hint-atencao`, `.card-form`, `.side-provisoria`), revert dos arquivos reformatados por engano (usuário). Limitação: "Senha definida." pode ficar pendente se o destino for tela de organização ainda não recomposta (P5) |
| 2026-10-06 | P1 concluído | 3ª leva (política de senha na Nova senha, dicas de Senha atual e do login vindas do form, username oculto, Caps Lock, divergência barrada no cliente) implementada; testes 3060 passed, 3 skipped; `code-reviewer` sem findings; recaptura de 18 cenários conferida (o `capturar.mjs` passou a provocar o erro de `/senha/` com senhas iguais, já que a divergência não recarrega mais a página). Gate visual fechado por conferência, sem 3ª rodada de `critique` (decisão do dono do produto). `DESIGN.md`/sidecar atualizados pelo `impeccable-documenter` e conferidos contra o CSS. Pendências fora do P1: "Senha definida." pode ficar pendente se o destino for tela de organização legada (some em P5); logout/sessão expirada sem mensagem no login (toca a spec 002); arquivos reformatados por engano a reverter antes do commit |

## Retomada encerrada — checkpoint de 2026-10-05

O estado de pausa abaixo é histórico. Seus seis passos foram executados: lote conferido,
verificação verde, matriz renovada, dois vereditos limitados aos mesmos findings, documentação
conferida e checkpoint entregue. **Próxima ação depende do aceite visual explícito do dono do
produto; não começar P1–P6.** Nada foi commitado, enviado ou integrado; branch preservada.

### Estado histórico ao pausar

Estado ao pausar: L1–L8 concluídas; L9 aplicada pelo `frontend-implementer` (relato: suíte 2969
passed, 3 skipped; ruff limpo), **ainda não conferida em tela pelo coordenador**. Desvio a avaliar no
veredito: "Em preparação" virou tabela de uma coluna (título + selo + descrição na mesma célula) em
vez das três colunas do contrato §12 — se aceito, registrar no contrato. A pista de rolagem por
gradiente vale para todo `.table-wrapper`, inclusive telas herdadas. Nada foi commitado; o working tree contém todo
o trabalho do laboratório.

Itens da L9 enviados: R1 links em prosa sublinhados (diferença 14 do contrato); R2 botão de tema
oculto sem `html.js`; V1 largura da Descrição e pista de rolagem do card em ≤640px; V2 "Em
preparação" em ≤640px; V3 Classificação em uma linha ("GERAL / GERAL · 000.000"); V4 tiles da
Home dois por linha em ≤640px; V5 tiles alinhados no topo em 1280/1440; V6 nota de "Em preparação"
inline no h2.

Próximos passos, em ordem:

1. Conferir no diff que R1–R2/V1–V6 foram aplicados (`static/css/base.css`, `components.css`,
   `catalogo.css`, `contas/templates/contas/home.html`).
2. `make verify` (deve ficar verde).
3. Recapturar a matriz: `node <scratchpad>/capture.mjs` não persiste entre sessões — recriar o
   script (Chrome headless + CDP: viewport, `prefers-color-scheme`, `pointer`/`hover`, toque,
   `?dev_como=<papel>`) e regerar `.impeccable/review/*.png` (lista em
   `.impeccable/review/captures.json`); shell provisório com `?dev_como=critica.provisoria`.
   Servidor: `.claude/launch.json` → `django-8011`.
4. Veredito do finish review: novo `impeccable-finish-reviewer` com as recapturas, pontuando só
   V1–V6 (resolvido/parcial/não resolvido). Se a revisão funcional precisar, rodar `code-reviewer`
   só sobre o diff da L9.
5. L10: `impeccable-documenter` reescreve `DESIGN.md` e `.impeccable/design.json` a partir do
   código; conferir contra `static/css/tokens.css`, `components.css`, CSS de feature e templates.
6. Atualizar este plano e entregar o checkpoint humano (seção 7). **Não iniciar a propagação.**

Pendências já decididas para registrar no checkpoint: scroll interno de 60vh das tabelas herdadas
(preexistente, lote P2); login ainda com a barra antiga (P1); páginas próprias de erro 403/404/500
inexistentes (decisão do dono do produto); prompts dos agentes ainda descrevem a fundação antiga
(P6); referências a Atkinson em `DESIGN.md`, `specs/005-*`, `.serena/memories` e
`.claude/agents/frontend-implementer.md` (L10/P6).
