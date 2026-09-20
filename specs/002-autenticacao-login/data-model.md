# Phase 1 — Data Model: Fundação de Autenticação e Login

Entidades derivadas de `spec.md` → seção "Key Entities" e requisitos funcionais. Todas vivem no
app `contas` (ver `research.md`, R10), numa única migration inicial (R14).

## `Setor`

Representação mínima exigida por `INV-ORG-001`. Não é gerenciável por esta feature (ver
`research.md`, R4).

| Campo | Tipo | Regras | Origem |
|---|---|---|---|
| `id` | `BigAutoField` (padrão do projeto, `DEFAULT_AUTO_FIELD`) | PK | — |
| `nome` | `CharField` | Obrigatório. **Sem `unique=True`** — nenhuma fonte normativa (`PRODUCT.md`, constitution, matrizes canônicas) afirma que nomes de setor são únicos, nem exige um identificador/código de setor. Uma constraint de unicidade não é criada só por conveniência (ver `research.md`, R4 — correção desta revisão). | Necessário para identificar o setor de forma legível. |
| `ativo` | `BooleanField`, default **`False`** | Nasce inativo (`FR-019`). Só pode ser `True` quando existir exatamente um chefe ativo do próprio setor (`FR-020`), validado em `Setor.save()`. | `INV-ORG-002` — **imposta por esta feature**, porque seu bootstrap escreve em setor/usuário/papel (`research.md` R4, revisão 3). |

Eventual identidade canônica de setor (nome único, código) pertence à futura definição da
administração de setores (`PERM-SECTOR-MANAGE`), não a esta feature.

Sem campo `chefe`: chefia é derivada de `PapelUsuario` (usuário com papel `ROLE-SECTOR-HEAD` e
`User.setor` igual a este setor), nunca uma coluna própria (evita duplicar a mesma informação em
dois lugares).

## `User` (`AUTH_USER_MODEL = "contas.User"`)

`AbstractBaseUser` + `PermissionsMixin` + `UserManager` próprio (ver `research.md`, R1).

| Campo | Tipo | Regras | Requisito/Invariante |
|---|---|---|---|
| `matricula` | `CharField(max_length=32, unique=True)` | `USERNAME_FIELD`. Texto opaco, sem conversão numérica; a entrada do login recebe apenas o `strip` + NFKC técnicos do `UsernameField` nativo, enquanto o valor cadastrado é preservado (ver `research.md`, R2). | `FR-001a`, `FR-001b` |
| `password` | herdado de `AbstractBaseUser` | Hash via `set_password()`/hashers nativos do Django (PBKDF2 por padrão) | Constitution, Princípio VI |
| `last_login` | herdado de `AbstractBaseUser` | — | — |
| `is_active` | `BooleanField`, default `True` | `False` = condição "equivalente a inativa" da spec | `FR-004`, `FR-006`, `INV-AUTH-001` |
| `is_staff` | `BooleanField`, default `False` | Só uso técnico (acesso ao Django Admin); nunca implica papel de negócio | `docs/domain/permissions-matrix.md`, regras 7–8 |
| `is_superuser` | herdado de `PermissionsMixin` | Só uso técnico/manutenção | idem |
| `setor` | `ForeignKey("contas.Setor", on_delete=models.PROTECT)` | Obrigatório (`null=False`) | `INV-ORG-001`, `FR-016` |

**Validação de unicidade**: `unique=True` em `matricula` cria um índice único no PostgreSQL —
garante unicidade também no nível de persistência, não só na aplicação (`FR-001b`).

**Método de conveniência**: `User.tem_papel(*codigos: str) -> bool` — consulta
`self.papeis.filter(papel__in=codigos).exists()`. Não concede nem infere papel; apenas lê
atribuições já existentes (`FR-014`, `FR-015`).

**Managers**: `UserManager.create_user(matricula, password=None, setor=None, **extra_fields)` e
`create_superuser(...)` seguindo o padrão documentado do Django, ambos exigindo `setor` (nenhum
usuário pode ser criado sem setor, por `INV-ORG-001`). Ambos aceitam `setor` como instância **ou**
como PK, porque `createsuperuser` entrega a chave, não o objeto.

`create_user` cria uma **identidade de negócio** e concede `ROLE-REQUESTER` na mesma transação
(`FR-016a`/`FR-023`). `create_superuser` cria a conta **técnica** do Django e **não** concede papel
algum (`permissions-matrix.md`, regras 7-8). A criação administrativa (`ContaCriacaoForm.save()`)
segue a mesma regra de `create_user` — são os dois caminhos suportados.

## `Papel` (catálogo, não é tabela)

`django.db.models.TextChoices`, definido em código — não editável via admin como dado solto (ver
`research.md`, R5). `value` idêntico ao ID canônico de `docs/domain/permissions-matrix.md`.

| Membro | `value` | `label` (exibição) |
|---|---|---|
| `REQUISITANTE` | `ROLE-REQUESTER` | Requisitante |
| `AUXILIAR_SETOR` | `ROLE-SECTOR-ASSISTANT` | Auxiliar de setor |
| `CHEFE_SETOR` | `ROLE-SECTOR-HEAD` | Chefe de setor |
| `FUNCIONARIO_ALMOXARIFADO` | `ROLE-WAREHOUSE-STAFF` | Funcionário do almoxarifado |
| `CHEFE_ALMOXARIFADO` | `ROLE-WAREHOUSE-HEAD` | Chefe do almoxarifado |
| `AUDITOR` | `ROLE-AUDITOR` | Gestor/auditor |
| `ADMINISTRADOR_SISTEMA` | `ROLE-SYSTEM-ADMIN` | Administrador de sistema |

Esta feature não cria, edita nem redefine papel algum — o enum apenas espelha em código o que já é
canônico na matriz (`FR-014`).

## `PapelUsuario`

Tabela de atribuição — a única forma de um usuário "ter" um papel.

| Campo | Tipo | Regras | Requisito |
|---|---|---|---|
| `id` | `BigAutoField` | PK | — |
| `usuario` | `ForeignKey("contas.User", related_name="papeis", on_delete=models.CASCADE)` | Obrigatório | `FR-014` |
| `papel` | `CharField(max_length=32, choices=Papel.choices)` | Obrigatório, restrito ao catálogo `Papel` | `FR-014` |

**Constraint**: `Meta.constraints = [models.UniqueConstraint(fields=["usuario", "papel"],
name="papelusuario_unico_usuario_papel")]` — forma moderna e explícita (preferida a
`unique_together`, que é a API legada equivalente; projeto novo em Django 6.1, sem motivo para
manter a forma antiga) — impede atribuição duplicada do mesmo papel à mesma identidade; múltiplos
papéis diferentes para o mesmo usuário são múltiplas linhas (sem herança implícita entre elas —
`FR-015`).

## Relacionamentos

```text
Setor 1 ──── * User (User.setor obrigatório; on_delete=PROTECT)
User  1 ──── * PapelUsuario (User.papeis; on_delete=CASCADE — remover o usuário remove suas
                                                              atribuições, não o inverso)
Papel (enum) ──── restringe PapelUsuario.papel (não é uma tabela, não tem FK)
```

## Transições de estado

- `User.is_active`: `True → False` (desativação) e `False → True` (reativação) — a
  criação/alteração dessas transições **não pertence a esta feature** (fora de escopo:
  administração de usuários). O que esta feature garante é o *efeito observável* de `is_active`
  ser `False` a qualquer momento: recusa de login (R3) e perda de acesso a superfícies protegidas
  na próxima interação (R9) — não a interface que realiza a transição em si.
- Nenhuma outra entidade desta feature tem máquina de estados.

## Regras de validação consolidadas (rastreamento FR → modelo)

| FR | Onde é garantido |
|---|---|
| `FR-001a` | `User.matricula` é o `USERNAME_FIELD`, solicitado pelo `AuthenticationForm` nativo |
| `FR-001b` | Tipo `CharField` (nunca numérico) + `unique=True` (unicidade também em persistência) |
| `FR-004`, `INV-AUTH-001` | `User.is_active` + `ModelBackend.user_can_authenticate()` nativo |
| `INV-ORG-001`, `FR-016` | `User.setor` obrigatório (`null=False`), `on_delete=PROTECT` |
| `FR-014` | `PapelUsuario` + enum `Papel` + `User.tem_papel()` |
| `FR-015` | `UniqueConstraint` em `PapelUsuario.Meta.constraints` (cada papel é uma concessão explícita e independente) |
| `FR-016a` | `UserManager.create_user` + `ContaCriacaoForm.save()`, ambos em transação |
| `FR-019`, `FR-020` | `Setor.ativo` default `False` + validação em `Setor.save()` |
| `FR-021`, `FR-022` | Validação em `User.save()` e `PapelUsuario.save()`/`delete()` |
| `FR-023`, `INV-ORG-002` | `transaction.atomic()` + `select_for_update()` nos caminhos acima |
