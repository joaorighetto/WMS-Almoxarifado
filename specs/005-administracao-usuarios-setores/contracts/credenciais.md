# Contrato — Credenciais

Cobre FR-031 a FR-039 da spec e a emenda ao SC-001 da 002. Decisões em research R8 a R12.

## Senha provisória

| Aspecto | Contrato |
|---|---|
| Geração | `gerar_senha_provisoria()`: 12 caracteres de `secrets`, alfabeto sem `0 O 1 l I`, ao menos uma letra e um dígito; satisfaz os validadores de R12 |
| Persistência | só o hash (`set_password`) e `User.senha_provisoria_em = agora` |
| Exibição | uma vez, na resposta 200 ao POST de cadastro ou redefinição, com `Cache-Control: no-store`; nunca em sessão, mensagem, log, evento ou outra tela |
| Repetição do POST | mesma `chave_confirmacao` → "já executada", sem nova senha |
| Validade | `VALIDADE_SENHA_PROVISORIA = timedelta(days=7)` contados de `senha_provisoria_em` |
| Vencida no login | `WMSModelBackend.user_can_authenticate` → `False`; mensagem genérica de FR-003 da 002 |
| Vencida com sessão aberta | `CredencialProvisoriaMiddleware` faz `logout` e redireciona ao login |
| Ficha do usuário | "Provisória — vence em DD/MM/AAAA HH:MM" ou "Provisória vencida em …"; nunca a senha |

## `CredencialProvisoriaMiddleware`

Posição: logo depois de `django.contrib.auth.middleware.AuthenticationMiddleware` (antes do
`RetornoPosLoginMiddleware`). Para requisição de usuário autenticado com `senha_provisoria_em`:

| Caso | Resposta |
|---|---|
| provisória vencida | `logout` → 302 para o login |
| rota `definir_senha` ou `logout`, ou arquivo estático | segue |
| qualquer outra rota | 302 para `definir_senha` (com `HX-Redirect` em requisição HTMX) |

Usuário sem credencial provisória, anônimo ou inativo: o middleware não age.

## `/senha/` (`definir_senha`)

| Estado | Campos | Regras |
|---|---|---|
| credencial provisória | nova senha, confirmação | política de R12; diferente da provisória (FR-036) |
| credencial definitiva | senha atual, nova senha, confirmação | senha atual correta, senão nada muda (FR-037); política de R12 |

Sucesso, nos dois estados, numa transação sob o lock de organização:

1. `set_password(nova)`; `senha_provisoria_em = None`;
2. `update_session_auth_hash(request, usuario)` — mantém a sessão em uso e encerra as demais;
3. evento `SENHA_DEFINIDA` (`dados.motivo`: `definicao_obrigatoria` ou `troca_voluntaria`), sem senha;
4. redirecionamento:
   - definição obrigatória: para o destino do marcador `_retorno_pos_login_destino`, quando existir
     (o `RetornoPosLoginMiddleware` da 002 devolve à Home se o destino for proibido), senão para a
     Home (FR-034);
   - troca voluntária: para a Home, com a mensagem "Senha alterada."

Com credencial provisória, a página não mostra a barra de navegação nem atalhos; só o logout.

## Redefinição pelo administrador

`redefinir_senha` grava nova provisória e `senha_provisoria_em = agora`. O hash muda, então toda
sessão aberta da conta perde a validade na interação seguinte (FR-033), inclusive a do próprio
administrador quando ele redefine a própria senha (edge case da spec).

## Política (`AUTH_PASSWORD_VALIDATORS`)

`UserAttributeSimilarityValidator` com `user_attributes=("matricula", "nome")`;
`MinimumLengthValidator` (8); `CommonPasswordValidator`; `NumericPasswordValidator`. Sem exigência
de tipos de caractere nem expiração periódica.

## Não fazer

- Nenhuma capability nova em `permissions-matrix.md` (D-27, FR-039).
- Nenhuma recuperação de senha sem o administrador, e-mail ou página pública.
- Nenhuma mensagem que distinga senha vencida de senha errada.
