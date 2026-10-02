# Data Model — Administração de Usuários, Papéis e Setores

Esquema efêmero (Constitution XIII): mudanças só nos models, aplicadas por `make resetdb`. Nenhum
dado durável a migrar. Triggers criados em `post_migrate` de `contas` (research R5).

## `contas.User` (alterado)

| Campo | Tipo | Regra |
|---|---|---|
| `matricula` | `CharField(32)`, `unique` | existente; texto opaco (FR-001b da 002); `CHECK matricula <> ''`; editável só por `editar_usuario` (correção, FR-009) |
| `nome` | `CharField(150)` | **novo**; obrigatório; gravado sem espaços nas pontas; `CHECK nome <> ''` (FR-006) |
| `nome_busca` | `CharField(150)` | **novo**; `normalizar_para_busca(nome)`, gravado junto com `nome` (research R14) |
| `setor` | FK `Setor`, `PROTECT` | existente; um único setor (`INV-ORG-001`) |
| `is_active` | `bool` | existente; desativação preserva papéis |
| `is_staff`, `is_superuser` | `bool` | existentes; só a conta técnica tem `is_superuser` (FR-004) |
| `senha_provisoria_em` | `DateTimeField`, nulo | **novo**; preenchido ao gerar senha provisória (cadastro, redefinição); nulo depois que o usuário define a própria senha (research R8 a R10) |

Derivados (não persistidos):

- **credencial provisória**: `senha_provisoria_em is not None`;
- **provisória vencida**: `senha_provisoria_em + 7 dias <= agora` (`VALIDADE_SENHA_PROVISORIA`);
- **chefe de setor**: usuário ativo com `ROLE-SECTOR-HEAD` no próprio setor (como na 002);
- **administrador ativo**: identidade de negócio ativa com `ROLE-SYSTEM-ADMIN`.

`REQUIRED_FIELDS = ["setor", "nome"]`. `create_user` e `create_superuser` continuam existindo, mas
`create_user` só funciona dentro de uma operação de `contas.organizacao` (research R4).

## `contas.Setor` (alterado)

| Campo | Tipo | Regra |
|---|---|---|
| `nome` | `CharField(100)` | gravado sem espaços nas pontas; único por `Lower(Trim(nome))` (FR-025) |
| `ativo` | `bool`, padrão `False` | existente; nasce inativo (FR-019 da 002) |
| `almoxarifado` | `bool`, padrão `False` | **novo**; designação; no máximo um `True`; imutável por trigger (`INV-ORG-004`) |
| `ativado_em` | `DateTimeField`, nulo | **novo**; momento da primeira ativação; imutável depois de preenchido (FR-030) |

Constraints:

| Nome | Expressão | Regra |
|---|---|---|
| `setor_nome_unico_normalizado` | `UNIQUE (lower(trim(nome)))` | FR-025 |
| `setor_nome_nao_vazio` | `CHECK trim(nome) <> ''` | FR-025 |
| `setor_um_unico_almoxarifado` | `UNIQUE (almoxarifado) WHERE almoxarifado` | `INV-ORG-004` |
| `setor_ativo_tem_ativacao` | `CHECK NOT ativo OR ativado_em IS NOT NULL` | FR-030 |
| `setor_almoxarifado_nao_desativado` | `CHECK NOT almoxarifado OR ativado_em IS NULL OR ativo` | `INV-ORG-004`, FR-029 |

"Exatamente um" Almoxarifado vale depois do provisionamento: o banco garante "no máximo um" e o
provisionamento cria o único.

## `contas.PapelUsuario` (sem mudança de schema)

`(usuario, papel)` único; `papel` na lista fechada `Papel`. Deixa de ter regras em `save()`/`delete()`
(research R3); a barreira de escrita de R4 e o trigger adiado de R5 assumem esse papel.

## `contas.EventoOrganizacional` (novo)

| Campo | Tipo | Regra |
|---|---|---|
| `momento` | `DateTimeField`, padrão agora | |
| `autor` | FK `User`, `PROTECT`, nulo | nulo só no provisionamento técnico (R15) |
| `tipo` | `CharField`, lista fechada `TipoEvento` | abaixo |
| `usuario` | FK `User`, `PROTECT`, nulo | alvo principal |
| `usuario_relacionado` | FK `User`, `PROTECT`, nulo | chefe anterior na substituição |
| `setor` | FK `Setor`, `PROTECT`, nulo | setor alvo, de destino ou do usuário |
| `setor_relacionado` | FK `Setor`, `PROTECT`, nulo | setor de origem na transferência |
| `dados` | `JSONField` | `{"anterior": {...}, "novo": {...}}` e detalhes do tipo; **nunca senha** |
| `justificativa` | `TextField`, vazio permitido | desativação de usuário (FR-019) |
| `chave_confirmacao` | `UUIDField`, nulo, `unique` | cadastro e redefinição (research R8) |

Constraints: `CHECK usuario_id IS NOT NULL OR setor_id IS NOT NULL`; `tipo` na lista fechada.
Índices: `(usuario, momento)`, `(usuario_relacionado, momento)`, `(setor, momento)`,
`(setor_relacionado, momento)`. Trigger `BEFORE UPDATE OR DELETE` recusa qualquer alteração (FR-041).

### `TipoEvento` e conteúdo de `dados`

| Tipo | Alvos | `dados` |
|---|---|---|
| `USUARIO_CADASTRADO` | usuário, setor | matrícula, nome, setor, papéis |
| `USUARIO_EDITADO` | usuário | `nome` e/ou `matricula`, anterior e novo |
| `PAPEIS_ALTERADOS` | usuário, setor | papéis anteriores e novos |
| `USUARIO_TRANSFERIDO` | usuário, setor (destino), setor_relacionado (origem) | papéis removidos |
| `CHEFIA_DESIGNADA` | usuário, setor | papéis concedidos (no Almoxarifado, os três) |
| `CHEFIA_RETIRADA` | usuário, setor | papéis retirados |
| `CHEFIA_SUBSTITUIDA` | usuário (novo), usuario_relacionado (anterior), setor | papéis movidos e concedidos |
| `USUARIO_DESATIVADO` | usuário, setor | — (justificativa no campo próprio) |
| `USUARIO_REATIVADO` | usuário, setor | papéis preservados, confirmados e desmarcados |
| `SETOR_CRIADO` | setor | nome |
| `SETOR_RENOMEADO` | setor | nome anterior e novo |
| `SETOR_ATIVADO` | setor | chefe no momento; primeira ativação ou reativação |
| `SETOR_DESATIVADO` | setor | chefe no momento |
| `SENHA_PROVISORIA_GERADA` | usuário | motivo: cadastro, redefinição ou provisionamento |
| `SENHA_DEFINIDA` | usuário | definição obrigatória ou troca voluntária; definida por provisionamento de desenvolvimento |

O cadastro gera dois eventos (`USUARIO_CADASTRADO` e `SENHA_PROVISORIA_GERADA`) com a mesma
`chave_confirmacao` no primeiro; a redefinição gera só `SENHA_PROVISORIA_GERADA`, com a chave.

## Transições

**Usuário (situação)**: `ativo → inativo` por `desativar_usuario`; `inativo → ativo` por
`reativar_usuario`. Nunca excluído.

**Credencial**:

```text
(cadastro) → provisória ──definir_propria_senha──→ definitiva
                │  └─ 7 dias sem uso → provisória vencida (login recusado)
definitiva ──redefinir_senha──→ provisória      (também a partir de provisória ou vencida)
definitiva ──trocar_propria_senha──→ definitiva
```

**Setor**: `inativo → ativo` por `ativar_setor` (preenche `ativado_em` na primeira vez);
`ativo → inativo` por `desativar_setor` (nunca para o Almoxarifado). Nunca excluído.

**Chefia**: setor inativo sem chefe → `designar_chefia`; setor inativo com chefe →
`retirar_chefia`; setor ativo → só `substituir_chefia`.

## Verificação de estado final (`validar_organizacao`) e trigger adiado

Verificado ao fim de toda operação (research R3) e, no commit, pelo trigger (research R5), para os
setores e usuários tocados:

1. setor ativo tem exatamente um usuário ativo do próprio setor com `ROLE-SECTOR-HEAD`
   (`INV-ORG-002`); nenhum setor, ativo ou inativo, tem mais de um (FR-022 da 002);
2. `ROLE-WAREHOUSE-STAFF` e `ROLE-WAREHOUSE-HEAD` só em usuário do setor Almoxarifado
   (`INV-ORG-005`);
3. usuário ativo com `ROLE-WAREHOUSE-HEAD` tem `ROLE-SECTOR-HEAD` no Almoxarifado e
   `ROLE-WAREHOUSE-STAFF`; com o Almoxarifado ativo, seu chefe ativo tem `ROLE-WAREHOUSE-HEAD`
   (`INV-ORG-006`);
4. identidade de negócio ativa tem `ROLE-REQUESTER`; conta técnica não tem nenhum papel (FR-016a da
   002).

## Rastreamento spec → modelo

| Requisito | Onde |
|---|---|
| FR-005, FR-019 | sem exclusão: barreira de R4 recusa `delete()`; FKs `PROTECT` |
| FR-006, FR-009 | `User.nome`, `nome_busca`, `matricula` + constraints |
| FR-025, FR-026, FR-029, FR-030 | `Setor` + constraints + trigger de designação |
| FR-031 a FR-035 | `User.senha_provisoria_em`; `EventoOrganizacional.chave_confirmacao` |
| FR-040 a FR-042 | `EventoOrganizacional` + trigger de imutabilidade |
| FR-046, FR-047 | barreira (R4), lock (R2), validação final (R3), trigger adiado (R5) |
| FR-050 | `Setor.almoxarifado`, comando `provisionar_organizacao` |
