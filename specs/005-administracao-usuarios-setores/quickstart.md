# Quickstart — validação da 005

Roteiro para provar a feature de ponta a ponta depois da implementação. Detalhes de regra em
[operacoes-organizacionais.md](./contracts/operacoes-organizacionais.md), rotas em
[rotas-e-autorizacao.md](./contracts/rotas-e-autorizacao.md) e senhas em
[credenciais.md](./contracts/credenciais.md).

## 1. Preparar

```bash
make resetdb
```

```bash
make seed_dev
```

O schema mudou (`User.nome`, `Setor.almoxarifado` etc.), por isso o `resetdb`. O `seed_dev` cria a
organização fictícia pelas operações de ORG, com o setor `almox` designado como Almoxarifado.

## 2. Testes automatizados

```bash
make test
```

```bash
make verify
```

Esperado: tudo verde, incluindo os testes transacionais de concorrência e do trigger adiado.

## 3. Provisionamento em banco vazio

```bash
make resetdb
```

```bash
uv run --env-file .env python manage.py provisionar_organizacao --setor-almoxarifado "Almoxarifado" --matricula 1001 --nome "Pessoa Administradora"
```

Esperado: um setor ativo designado como Almoxarifado; a conta 1001 ativa com `ROLE-REQUESTER`,
`ROLE-SYSTEM-ADMIN`, `ROLE-SECTOR-HEAD`, `ROLE-WAREHOUSE-HEAD` e `ROLE-WAREHOUSE-STAFF`; a senha
provisória impressa uma vez; eventos com autor nulo. Rodar de novo é recusado. Volte ao estado do
passo 1 depois.

## 4. Roteiro manual (servidor de desenvolvimento)

Abra `/organizacao/usuarios/?dev_como=administrador-sistema` (login simulado,
`docs/development/login-simulado.md`).

| # | Ação | Esperado | Spec |
|---|---|---|---|
| 1 | Cadastrar usuário no setor ETA, sem papéis extras | senha provisória exibida uma vez; F5 não gera outra | US1, FR-031 |
| 2 | Sair, entrar com a matrícula e a provisória | só a tela de senha; outras URLs voltam a ela | FR-032 |
| 3 | Definir senha igual à provisória; depois uma válida | a primeira é recusada; a segunda leva à Home | FR-034, FR-036 |
| 4 | Buscar "joao" sem acento; filtrar por setor e papel | resultados combinados | US2, FR-043 |
| 5 | Na ETA, tentar conceder `ROLE-SECTOR-HEAD` a um operador | recusa com caminho "substituição" | US3-1 |
| 6 | Substituir o chefe da ETA por um operador | um único chefe; anterior continua na ETA; evento nas duas fichas | US4-1 |
| 7 | Substituir o chefe do Almoxarifado por `funcionario` | três papéis de chefia no novo; anterior só com `ROLE-WAREHOUSE-STAFF` dentre os de almoxarifado | US4-3 |
| 8 | Transferir `eta.auxiliar` para o Laboratório | prévia lista `ROLE-SECTOR-ASSISTANT`; depois só papéis não presos | US3-4 |
| 9 | Desativar a ETA com membros ativos; desativar o Almoxarifado | recusas com motivo | US7-5, US7-6 |
| 10 | Desativar e reativar `almox.inativo` | revisão lista `ROLE-WAREHOUSE-STAFF`; resultado = confirmado | US5-4 |
| 11 | Redefinir a senha de uma conta com sessão aberta em outra janela | a outra sessão cai na próxima interação | US6-1 |
| 12 | Trocar a própria senha em `/senha/` com a atual errada e certa | errada não muda nada; certa encerra as outras sessões | US6-2, US6-3 |
| 13 | Abrir `/admin/contas/user/` como superusuário técnico | só consulta, sem adicionar, alterar ou excluir | research R6 |
| 14 | Abrir `/organizacao/usuarios/` como `?dev_como=chefe-almoxarifado` | 403 | FR-001 |

Para o vencimento de 7 dias, use o teste automatizado (relógio controlado); não há atalho manual.

## 5. Gate visual

Depois do `code-reviewer`, rodar `impeccable critique` nas telas de `/organizacao/` como
`administrador-sistema` e em `/senha/` nos dois estados (provisória e definitiva), conforme
`.claude/rules/agent-orchestration.md`.
