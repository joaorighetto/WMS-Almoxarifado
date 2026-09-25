# ADR 0001 — App shell: barra de trabalho global no template base, sem sidebar

- **Status:** aceito
- **Data da decisão:** 2026-09, na modernização visual "Tubulação e piso industrial" (Home-laboratório
  no PR #15, propagação ao catálogo no PR #17). Registrado depois, em 2026-09-25.
- **Fonte vigente do detalhe visual:** `DESIGN.md` → Layout → App shell e Components → Navigation.
  Este ADR registra a decisão estrutural e os motivos, não medidas nem estilo.

## Contexto

A fundação visual anterior ("A Bancada de Trabalho Confiável") previa uma sidebar lateral no
desktop e deixava em aberto a largura dela e a navegação no celular. As features 001 e 002 foram
entregues sem app shell: cada tela do catálogo tinha um link "← Início" para voltar à Home.

O produto tem hoje poucos destinos (Home, consulta do catálogo, envio, prévia e histórico de
importações). As tabelas densas do almoxarifado são a superfície principal no desktop, e
Solicitantes e Chefes de setor usam o sistema principalmente no celular. `DESIGN.md` → The Shared
Foundation Rule exige uma só fundação para celular, tablet e desktop.

## Decisão

1. O app shell é uma **barra de trabalho horizontal no topo**, a mesma no celular e no desktop, no
   lugar da sidebar.
2. A barra é **declarada uma única vez** em `contas/templates/contas/base.html`, no bloco
   `{% block appbar %}`, e só é renderizada para usuário autenticado. O conteúdo fica no parcial
   `contas/templates/contas/_barra_trabalho.html`. Nenhuma tela inclui o parcial fora do bloco
   `appbar`; a Home sobrescreve o bloco e reinclui o parcial com `esconde_matricula_compacta=True`.
3. A marca da barra é o **único retorno global à Home**: fora da Home ela é link; na Home é o item
   atual (`aria-current`, sem link). Saem os links "← Início" das telas. O retorno a outra tela de
   origem usa o componente `.back-link`.
4. O logout fica na barra, sempre como formulário POST com CSRF (Constitution VI), que funciona
   sem JavaScript (Constitution IX).
5. Respostas HTMX parciais renderizam só o template partial (por exemplo,
   `"catalogo/consulta.html#resultados_consulta"`) e por isso não trazem a barra do `base.html`. O
   login não a tem, porque a página é anônima.

## Alternativas consideradas

- **Sidebar lateral no desktop** (prevista pela fundação anterior): toma largura das tabelas, exige
  uma segunda solução para o celular e fica vazia com o número atual de destinos.
- **Sem app shell e com link de volta por tela** (o estado das 001/002): cada tela reinventa a volta
  à Home, o logout só aparece na Home e não há lugar comum para navegação futura.

## Por que é um ADR

`docs/adr/README.md` exclui decisões fáceis de reverter. Esta não é: é um contrato de template entre
apps, não um ajuste visual.

- Todo template autenticado de `contas` e `catalogo` herda o bloco, e as features futuras (REQ,
  ATE e as demais) vão herdá-lo também.
- A estrutura de página depende dele: o teto de 1120px é compartilhado pela barra e pelo conteúdo,
  e o título de página começa no mesmo x da marca. O `scroll-padding-top` compensa a barra sticky
  pelo token `--appbar-height`.
- Testes fixam o contrato (`tests/test_barra_trabalho.py`: barra em cada tela do catálogo,
  ausência no fragmento HTMX e no login, formulário de logout único).
- Trocar para sidebar exigiria rever todas as telas, a estrutura de página, os testes e o modelo de
  navegação de uma vez.

## Consequências

- Toda tela autenticada nova ganha a barra sem fazer nada; uma tela que não deva tê-la precisa
  sobrescrever o bloco `appbar` explicitamente.
- Navegação e autorização continuam separadas: a barra não mostra nem esconde destinos por papel, e
  a autorização segue nas rotas.
- **Em aberto** (ver `DESIGN.md` → Layout → Estado de validação e Components → Navigation):
  - destinos adicionais na barra, estado ativo por item e comportamento com muitos destinos;
  - a navegação de Solicitante/Chefe de setor quando houver mais destinos;
  - a validação da barra e das telas densas em tablet.

  Resolver esses pontos deve estender a barra. Se exigir outra forma de app shell, isso substitui
  este ADR por um novo.
