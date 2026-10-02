# Contrato — Operações organizacionais (`contas/organizacao.py`)

Toda operação de escrita:

1. abre `transaction.atomic()` e toma `pg_advisory_xact_lock(CHAVE_LOCK_ORGANIZACAO)` (research R2);
2. marca a operação em curso (barreira de escrita, research R4);
3. relê o estado atual e verifica as regras próprias da operação, na ordem da tabela de recusas;
4. escreve;
5. chama `validar_organizacao(setores, usuarios)` sobre o estado final (research R3);
6. grava o `EventoOrganizacional` (data-model);
7. retorna o objeto alterado ou um resultado; operação sem efeito retorna sem evento.

Recusa: `OperacaoRecusada(motivo: str, caminho: str | None)`, sem nenhuma escrita. `autor` é a
identidade que executa; `None` só no provisionamento (R15). As funções não recebem `request`.

## Assinaturas

```text
cadastrar_usuario(autor, *, matricula, nome, setor_id, papeis_adicionais, chave_confirmacao)
    -> (User, senha_provisoria: str)
editar_usuario(autor, usuario_id, *, nome=None, matricula=None) -> User
alterar_papeis(autor, usuario_id, *, conceder: set[Papel], remover: set[Papel]) -> User
previa_transferencia(usuario_id, setor_destino_id) -> PreviaTransferencia   # só leitura
transferir_usuario(autor, usuario_id, setor_destino_id, *, papeis_removidos_previstos) -> User
designar_chefia(autor, setor_id, usuario_id) -> User
retirar_chefia(autor, setor_id) -> User
previa_substituicao(setor_id, novo_chefe_id) -> PreviaSubstituicao          # só leitura
substituir_chefia(autor, setor_id, *, chefe_esperado_id, novo_chefe_id) -> User
desativar_usuario(autor, usuario_id, *, justificativa="") -> User
previa_reativacao(usuario_id) -> PreviaReativacao                          # só leitura
reativar_usuario(autor, usuario_id, *, papeis_mantidos: set[Papel]) -> User
criar_setor(autor, *, nome) -> Setor
renomear_setor(autor, setor_id, *, nome) -> Setor
ativar_setor(autor, setor_id) -> Setor
desativar_setor(autor, setor_id) -> Setor
redefinir_senha(autor, usuario_id, *, chave_confirmacao) -> senha_provisoria: str
validar_organizacao(setores, usuarios) -> None   # levanta OperacaoRecusada
```

`papeis_removidos_previstos` (transferência) e a prévia da substituição servem para detectar que o
estado mudou entre a prévia e a confirmação: se os efeitos calculados sob o lock forem diferentes, a
view mostra a nova prévia em vez de executar (FR-049).

## Recusas por operação

Mensagens orientativas; o texto final é ajustado na implementação, mantendo motivo e caminho.

| Operação | Recusa quando | Motivo / caminho |
|---|---|---|
| `cadastrar_usuario` | matrícula vazia ou já usada | "Matrícula já usada por outra conta." |
| | nome vazio após remover espaços; setor ausente ou inexistente | erro no campo |
| | `ROLE-SECTOR-HEAD` em setor com chefe ativo | "O setor já tem chefe." / "Use a substituição de chefia na ficha do setor." |
| | `ROLE-SECTOR-HEAD` em setor ativo | idem (setor ativo sempre tem chefe) |
| | papel de almoxarifado fora do Almoxarifado | `INV-ORG-005` / "Cadastre no setor Almoxarifado." |
| | `ROLE-WAREHOUSE-HEAD` sem a chefia do Almoxarifado | `INV-ORG-006` / "Designe a chefia do Almoxarifado." |
| `editar_usuario` | nome vazio; matrícula vazia ou já usada | erro no campo |
| `alterar_papeis` | remover `ROLE-REQUESTER` de conta ativa | "Toda conta ativa é requisitante." |
| | conceder ou remover `ROLE-SECTOR-HEAD` | "A chefia muda pela ficha do setor." / designação, retirada ou substituição |
| | conceder ou remover `ROLE-WAREHOUSE-HEAD` | "Acompanha a chefia do Almoxarifado." |
| | conceder `ROLE-WAREHOUSE-STAFF` fora do Almoxarifado | `INV-ORG-005` / "Transfira para o Almoxarifado antes." |
| | remover `ROLE-WAREHOUSE-STAFF` do chefe do Almoxarifado | `INV-ORG-006` |
| | remover `ROLE-SYSTEM-ADMIN` do último administrador ativo | "É o último administrador ativo." / "Conceda o papel a outra pessoa antes." |
| | alvo é conta técnica | 404 na view; recusa na função |
| `transferir_usuario` | destino igual ao setor atual | "O usuário já pertence a este setor." |
| | usuário é chefe de setor ativo | "Substitua a chefia do setor antes." |
| `designar_chefia` | setor ativo | "Use a substituição." |
| | setor já tem chefe ativo | FR-022 da 002 |
| | usuário inativo ou de outro setor | "Transfira para o setor antes." |
| `retirar_chefia` | setor ativo | "Use a substituição." |
| `substituir_chefia` | setor inativo | "Use a designação." |
| | `chefe_esperado_id` não é mais o chefe | "A chefia mudou desde que você abriu esta tela." (FR-017) |
| | novo chefe inativo, de outro setor, ou igual ao atual | "Transfira para o setor antes." (FR-015) |
| `desativar_usuario` | é a própria conta do autor | D-15 |
| | é o último administrador ativo | D-15 |
| | é chefe de setor ativo | "Substitua a chefia do setor antes." (FR-020) |
| | já inativo | sem efeito |
| `reativar_usuario` | `papeis_mantidos` sem `ROLE-REQUESTER` | FR-023 |
| | a conta inativa perdeu `ROLE-REQUESTER` (permitido por FR-011, que só protege conta ativa) | FR-023, FR-016a da 002 / "Conceda o papel de requisitante na tela de papéis antes de reativar." |
| | papel mantido violaria regra (segundo chefe, segundo chefe do almoxarifado, papel de almoxarifado fora dele) | motivo por papel / "Desmarque o papel para prosseguir." (FR-024) |
| | já ativo | sem efeito |
| `criar_setor`, `renomear_setor` | nome vazio ou repetido (sem caixa e espaços) | "Já existe o setor X." |
| `ativar_setor` | sem exatamente um chefe ativo do próprio setor | FR-020 da 002 / "Designe a chefia antes." |
| | Almoxarifado sem `ROLE-WAREHOUSE-HEAD` e `ROLE-WAREHOUSE-STAFF` no chefe | `INV-ORG-006` |
| `desativar_setor` | Almoxarifado | `INV-ORG-004` (FR-029) |
| | outros membros ativos além do chefe (só identidades de negócio; conta técnica não conta) | lista os membros / "Transfira ou desative antes." (FR-028) |
| | condição de outro recorte não atendida | motivo do recorte (FR-053; ponto único, research R17) |
| `redefinir_senha` | alvo é conta técnica | 404 na view |

## Efeitos

| Operação | Escreve | Evento |
|---|---|---|
| `cadastrar_usuario` | `User` ativo com `nome`, `senha_provisoria_em`, hash da provisória; `ROLE-REQUESTER` + adicionais (no Almoxarifado, `ROLE-SECTOR-HEAD` implica designação, com os três papéis) | `USUARIO_CADASTRADO` (com a chave) + `SENHA_PROVISORIA_GERADA` |
| `editar_usuario` | `nome`, `nome_busca`, `matricula` | `USUARIO_EDITADO` |
| `alterar_papeis` | `PapelUsuario` | `PAPEIS_ALTERADOS` |
| `transferir_usuario` | `User.setor`; remove `ROLE-SECTOR-ASSISTANT`, `ROLE-SECTOR-HEAD`, `ROLE-WAREHOUSE-STAFF`, `ROLE-WAREHOUSE-HEAD` | `USUARIO_TRANSFERIDO` |
| `designar_chefia` | `ROLE-SECTOR-HEAD`; no Almoxarifado também `ROLE-WAREHOUSE-HEAD` e, se faltar, `ROLE-WAREHOUSE-STAFF` | `CHEFIA_DESIGNADA` |
| `retirar_chefia` | remove `ROLE-SECTOR-HEAD`; no Almoxarifado também `ROLE-WAREHOUSE-HEAD` | `CHEFIA_RETIRADA` |
| `substituir_chefia` | move `ROLE-SECTOR-HEAD` (e, no Almoxarifado, `ROLE-WAREHOUSE-HEAD`); concede `ROLE-WAREHOUSE-STAFF` ao novo se faltar; anterior mantém o resto | `CHEFIA_SUBSTITUIDA` |
| `desativar_usuario` | `is_active=False`; papéis intactos | `USUARIO_DESATIVADO` |
| `reativar_usuario` | `is_active=True`; remove os papéis desmarcados | `USUARIO_REATIVADO` |
| `criar_setor` | `Setor` inativo, `almoxarifado=False` | `SETOR_CRIADO` |
| `renomear_setor` | `nome` | `SETOR_RENOMEADO` |
| `ativar_setor` | `ativo=True`; `ativado_em` na primeira vez | `SETOR_ATIVADO` |
| `desativar_setor` | `ativo=False` | `SETOR_DESATIVADO` |
| `redefinir_senha` | hash da nova provisória; `senha_provisoria_em=agora` (encerra sessões, research R11) | `SENHA_PROVISORIA_GERADA` (com a chave) |

## Garantias verificáveis por teste

- Nenhuma recusa escreve nada nem gera evento.
- Depois de qualquer operação, `validar_organizacao` sobre todos os setores e usuários não recusa.
- Nenhuma operação importa ou escreve model fora de `contas` (FR-051).
- Duas operações concorrentes nunca produzem estado que nenhuma ordem serial produziria.
