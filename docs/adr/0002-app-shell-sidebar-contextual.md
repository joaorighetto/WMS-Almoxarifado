# ADR 0002 — App shell: sidebar contextual por capability, no padrão do django-observatory

- **Status:** aceito
- **Data da decisão:** 2026-10-05, pelo dono do produto, no pedido de redesign da interface baseado
  no django-observatory 0.1.0 (commit `6edda16`).
- **Substitui:** [ADR 0001](0001-app-shell-barra-de-trabalho.md).
- **Fonte vigente do detalhe visual:** `DESIGN.md` (depois do laboratório). Até lá,
  `docs/redesign-observatory/contrato.md`.

## Contexto

O ADR 0001 adotou uma barra de trabalho horizontal sem navegação, porque havia poucos destinos. Hoje
há cinco grupos de destinos (catálogo, fornecedores, estoque, administração e Início), e a
navegação por papel existia só na Home: fora dela, voltar a outra tarefa exigia passar pela Home. O
dono do produto escolheu adotar a arquitetura de apresentação do django-observatory, cujo shell é
uma sidebar lateral.

## Decisão

1. O app shell autenticado é uma **sidebar lateral de 216 px** no desktop, com a coluna de conteúdo
   ocupando o resto da largura. Em até 860 px, vira uma barra superior estática com botão Menu.
2. O shell é declarado uma única vez em `contas/templates/contas/base.html`. Respostas HTMX parciais
   continuam renderizando só o partial e nunca trazem o shell. O login, anônimo, não tem shell.
3. A sidebar **mostra os destinos que o usuário pode usar**, a partir das mesmas flags de
   capability da Home, montadas no servidor (`contas/navegacao.py`) e expostas por um context
   processor preguiçoso, com no máximo uma consulta de papéis por requisição. A autorização continua
   nas rotas; a sidebar não é barreira (Constitution V e VI).
4. Identidade, troca de senha, logout (POST com CSRF) e tema ficam no rodapé da sidebar.
5. Com credencial provisória, o shell mostra só a marca sem link e o rodapé da conta, sem destinos.
6. Capacidades planejadas não entram na sidebar; continuam só na Home, sem link.

## Alternativas consideradas

- **Manter a barra horizontal e acrescentar destinos a ela:** diverge da referência escolhida e não
  comporta cinco grupos sem um segundo nível de menu.
- **Sidebar com todos os destinos e bloqueio no clique:** mostra o que o papel não pode usar e
  depende da rota para explicar a recusa; contraria a disciplina do upstream, que já filtra por
  permissão.

## Consequências

- Os testes que fixavam a barra (`tests/test_barra_trabalho.py`) passam a fixar o shell novo: um
  logout por página, ausência de shell em fragmento HTMX e no login, destinos por papel.
- Uma feature nova que acrescente destino acrescenta um item em `contas/navegacao.py`, com a flag de
  capability correspondente; não edita o template da sidebar.
- O `scroll-padding-top` e o token `--appbar-height` deixam de existir: no desktop não há barra fixa,
  e a barra móvel é estática.
