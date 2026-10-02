# Contrato — Rotas e autorização

Rotas de administração com prefixo `/organizacao/`, com nomes globais em `contas/urls.py` (sem
`app_name`: um namespace quebraria `reverse("home")`, `LOGIN_URL = "login"` e os demais consumidores
das rotas da 002). Todas usam
`catalogo.views.ExigePapelMixin` com `papel_exigido = Papel.ADMINISTRADOR_SISTEMA`: anônimo vai ao
login; autenticado sem o papel recebe 403; inativo é tratado como anônimo (`INV-AUTH-001`). Não há
exceção para o superusuário técnico, que não tem papel de negócio (FR-004). Toda autorização é
verificada na rota, no GET e no POST; link na interface é só conveniência.

`<pk>` inexistente, ou de conta técnica, dá 404 depois da checagem de papel (FR-002, FR-004).

## Usuários — `PERM-USER-MANAGE`

| Método e rota | Nome | Efeito |
|---|---|---|
| GET `/organizacao/usuarios/` | `usuarios` | lista paginada (50); filtros GET `q` (nome ou matrícula), `setor`, `situacao`, `papel`; com `HX-Request`, só a região de resultados |
| GET `/organizacao/usuarios/novo/` | `usuario_novo` | formulário com nova `chave_confirmacao` |
| POST `/organizacao/usuarios/novo/` | `usuario_novo` | `cadastrar_usuario`; sucesso → **200** com a ficha resumida e a senha provisória (`Cache-Control: no-store`), nunca redirect |
| GET `/organizacao/usuarios/<pk>/` | `usuario` | ficha: dados, situação da credencial, papéis, ações disponíveis, histórico paginado |
| GET/POST `/organizacao/usuarios/<pk>/editar/` | `usuario_editar` | nome; matrícula (correção) |
| GET/POST `/organizacao/usuarios/<pk>/papeis/` | `usuario_papeis` | lista dos sete papéis com o estado atual e o que pode ser alterado; POST → `alterar_papeis` |
| GET/POST `/organizacao/usuarios/<pk>/transferir/` | `usuario_transferir` | escolha do destino → prévia com papéis a remover → POST com `confirmar=1` → `transferir_usuario` |
| GET/POST `/organizacao/usuarios/<pk>/desativar/` | `usuario_desativar` | confirmação com justificativa opcional |
| GET/POST `/organizacao/usuarios/<pk>/reativar/` | `usuario_reativar` | revisão dos papéis preservados (`ROLE-REQUESTER` marcado e travado) → `reativar_usuario` |
| GET/POST `/organizacao/usuarios/<pk>/senha/` | `usuario_redefinir_senha` | confirmação → `redefinir_senha`; sucesso → **200** com a senha provisória (`no-store`) |

## Setores — `PERM-SECTOR-MANAGE`

| Método e rota | Nome | Efeito |
|---|---|---|
| GET `/organizacao/setores/` | `setores` | lista com nome, situação, chefe, membros ativos e marca de Almoxarifado; filtros `q`, `situacao` |
| GET/POST `/organizacao/setores/novo/` | `setor_novo` | `criar_setor` → 302 para a ficha |
| GET `/organizacao/setores/<pk>/` | `setor` | ficha: dados, chefe, membros ativos e inativos, ações disponíveis, histórico paginado |
| GET/POST `/organizacao/setores/<pk>/editar/` | `setor_editar` | `renomear_setor` |
| GET/POST `/organizacao/setores/<pk>/chefia/` | `setor_chefia` | setor ativo: substituição (escolha entre membros ativos → prévia → `confirmar=1`, com `chefe_esperado`); setor inativo sem chefe: designação; setor inativo com chefe: retirada |
| GET/POST `/organizacao/setores/<pk>/ativar/` | `setor_ativar` | confirmação → `ativar_setor` |
| GET/POST `/organizacao/setores/<pk>/desativar/` | `setor_desativar` | confirmação → `desativar_setor`; o Almoxarifado ativado não oferece a ação |

## Senha do próprio usuário — mecânica de autenticação (D-27, FR-039)

| Método e rota | Nome | Acesso | Efeito |
|---|---|---|---|
| GET/POST `/senha/` | `definir_senha` | qualquer usuário autenticado e ativo | com credencial provisória: definição obrigatória (sem senha atual); senão: troca voluntária, com senha atual. Ver [credenciais.md](./credenciais.md) |

## Respostas comuns às operações (POST)

| Situação | Resposta |
|---|---|
| sucesso | mensagem curta → 302 para a ficha (exceto as duas respostas com senha provisória, acima) |
| `OperacaoRecusada(motivo, caminho)` | 200, página re-renderizada com alerta de motivo e caminho (FR-048); dados do formulário preservados; nada gravado |
| erro de formulário | 200, erros por campo |
| `chave_confirmacao` já usada | aviso "Esta operação já foi executada; a senha provisória não é exibida novamente." → 302 para a ficha |
| prévia desatualizada (o estado mudou entre a prévia e a confirmação) | a operação revalida sob o lock: recusa com motivo, ou nova prévia quando os efeitos mudaram |
| erro inesperado | log com traceback; alerta genérico; nada gravado |

## Home e barra de trabalho

- `HomeView` ganha `pode_administrar_organizacao` (`ADMINISTRADOR_SISTEMA`), derivado do mesmo
  `set` de papéis já lido; o item ORG sai de `CAPACIDADES_PLANEJADAS` e vira dois atalhos (Usuários,
  Setores).
- A barra de trabalho ganha, ao lado de "Sair", o link "Senha" para `/senha/`, visível a todo
  usuário autenticado.

## Django Admin

`User`, `Setor`, `PapelUsuario` e `EventoOrganizacional` só para consulta: sem adicionar, alterar ou
excluir (research R6).

## Matriz de teste de permissão

Rota × {anônimo, inativo, superusuário técnico, requisitante, chefe de setor, auditor, funcionário
do almoxarifado, chefe do almoxarifado, administrador de sistema, administrador com credencial
provisória}:

| Rota | Autorizados | Demais |
|---|---|---|
| todas as de `/organizacao/` | administrador de sistema | 403 e nenhuma escrita (anônimo e inativo → login); administrador com credencial provisória → redirecionado a `/senha/` |
| `/senha/` | todo autenticado ativo | anônimo e inativo → login |
| qualquer outra rota | conforme a feature dona | usuário com credencial provisória → redirecionado a `/senha/` (exceto logout) |

O teste inclui POST direto sem passar pela tela e confirma, depois de cada 403, que nenhum
`User`, `Setor`, `PapelUsuario` ou `EventoOrganizacional` mudou.
