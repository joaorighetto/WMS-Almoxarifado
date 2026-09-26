# Matriz Canônica de Permissões — WMS-Almoxarifado

```text
Status: VALIDADO
Autoridade: CANÔNICA PARA AUTORIZAÇÃO DE DOMÍNIO
Versão: 1.1
Última validação: 2026-09-18
Última alteração: 2026-09-25 (PERM-STOCK-ENTRY-REVERSE; capabilities de fornecedores)
```

**Escopo**: capacidades de negócio atualmente definidas para o WMS-Almoxarifado.

**Origem**:
- `PRODUCT.md`
- `docs/domain-legacy/reconciliation/permissions-reconciliation.md`
- `specs/001-importacao-catalogo-materiais/spec.md`
- decisão do dono do produto de 2026-09-25, na especificação de `specs/003-entrada-materiais`
  (`PERM-STOCK-ENTRY-REVERSE`) e da importação de fornecedores (`PERM-SUPPLIER-*`)

> A ausência de uma capability para uma feature ainda não especificada não significa proibição
> permanente da feature; significa apenas que nenhuma autorização correspondente foi definida
> ainda. Capacidades hoje `PENDENTE` continuam registradas, com seu raciocínio completo, em
> `docs/domain-legacy/reconciliation/permissions-reconciliation.md`, e podem ser promovidas a este
> documento quando uma spec futura as definir.

## 1. Regras canônicas de interpretação

1. Autorização é negada por padrão (deny-by-default).
2. Somente concessões explicitamente registradas neste documento são válidas.
3. Não existe herança implícita entre papéis.
4. Uma identidade pode acumular papéis quando o modelo de usuários permitir, mas cada capability
   continua derivada de concessões explícitas — nunca de outro papel que a mesma identidade também
   ocupe.
5. Escopo e condições fazem parte da autorização; uma capability sem o escopo/condição corretos
   não está concedida.
6. Ocultar botão, rota ou elemento visual não constitui autorização.
7. Administrador de sistema (`ROLE-SYSTEM-ADMIN`) não possui override de operações de negócio.
8. Django superuser, se existir como mecanismo técnico de manutenção, não é papel de negócio e não
   aparece nesta matriz.
9. IDs `PERM-*` representam capacidades de domínio/documentação; não obrigam nem pressupõem
   determinada implementação técnica (framework, view, endpoint, camada).

## 2. Catálogo de papéis

| ID | Papel | Responsabilidade |
|---|---|---|
| `ROLE-REQUESTER` | Requisitante | Cria solicitação de material para si. |
| `ROLE-SECTOR-ASSISTANT` | Auxiliar de setor | Cria requisição em nome de colegas do próprio setor; acompanha o que criou. |
| `ROLE-SECTOR-HEAD` | Chefe de setor | Aprova requisições dos funcionários do próprio setor. |
| `ROLE-WAREHOUSE-STAFF` | Funcionário do almoxarifado | Opera movimentações do dia a dia e atende requisições aprovadas. |
| `ROLE-WAREHOUSE-HEAD` | Chefe do almoxarifado | Atribuições exclusivas sobre estoque (importação SCPI, estorno, devolução, saída excepcional, ajuste de inventário, inativação de material, painel de gestão). |
| `ROLE-AUDITOR` | Gestor/auditor | Visão consolidada de relatórios e histórico de movimentações, sem operar. |
| `ROLE-SYSTEM-ADMIN` | Administrador de sistema | Configura usuários, permissões e parâmetros do WMS. |

**Notas de composição** (aplicação da Regra 4, sem criar papel novo):

- Toda **identidade de negócio** ativa do WMS ocupa, no mínimo, `ROLE-REQUESTER` — é a definição do
  papel (`PRODUCT.md`: "Requisitante: qualquer funcionário de qualquer setor do SAEP... que cria uma
  solicitação de material"). Por isso, uma capability concedida a `ROLE-REQUESTER` está, na
  prática, disponível para qualquer identidade de negócio com conta ativa, independentemente de
  quais outros papéis ela também ocupe.

  Isso é uma **concessão explícita, nunca inferida**: a criação de uma identidade de negócio
  persiste a atribuição `ROLE-REQUESTER` junto com a conta, atomicamente. Nenhum papel é derivado
  em tempo de consulta a partir de `is_active` — coerente com a Regra 3 (sem herança implícita) e
  com o requisito de atribuição explícita da feature `002-autenticacao-login` (FR-015).

  **Exceção — superusuário técnico do Django**: a conta criada por `createsuperuser` é um
  mecanismo técnico de manutenção, não uma identidade de negócio (ver Regra 8). Ela **não** recebe
  `ROLE-REQUESTER` nem nenhum outro `ROLE-*`, e portanto não possui nenhuma capability de negócio.
  Para operar o domínio, a pessoa precisa de uma identidade de negócio com os papéis explícitos
  correspondentes.

  Desativar uma conta (`is_active = False`) **não** remove seus papéis: a atribuição é preservada
  para rastreabilidade, e o bloqueio de acesso é transversal, garantido por `INV-AUTH-001`.
- A pessoa que chefia o almoxarifado ocupa, ao mesmo tempo, três papéis explícitos — nunca por
  herança: `ROLE-WAREHOUSE-STAFF` (opera como qualquer funcionário do almoxarifado);
  `ROLE-SECTOR-HEAD`, com escopo restrito ao setor Almoxarifado (`PRODUCT.md`: "aprova, como chefe
  de setor do próprio almoxarifado, as requisições criadas por funcionários do almoxarifado"); e
  `ROLE-WAREHOUSE-HEAD` (as atribuições exclusivas de estoque). Por isso a matriz abaixo não
  precisa de uma capability de aprovação separada e específica do almoxarifado: `PERM-REQ-AUTHORIZE`
  concedida a `ROLE-SECTOR-HEAD`, com escopo "próprio setor", já cobre o chefe do almoxarifado
  quando o setor em questão é o próprio almoxarifado.

## 3. Catálogo de capabilities

### Usuários e setores

| ID | Capacidade | Papéis autorizados | Escopo | Condições |
|---|---|---|---|---|
| `PERM-USER-MANAGE` | Gerenciar usuários e atribuição de papéis | `ROLE-SYSTEM-ADMIN` | Global | — |
| `PERM-SECTOR-MANAGE` | Gerenciar setores | `ROLE-SYSTEM-ADMIN` | Global | Setor ativo precisa de chefe ativo do próprio setor. |

### Requisição

| ID | Capacidade | Papéis autorizados | Escopo | Condições |
|---|---|---|---|---|
| `PERM-REQ-CREATE-SELF` | Criar requisição para si | `ROLE-REQUESTER` | Próprio usuário | — |
| `PERM-REQ-CREATE-FOR-OTHER` | Criar requisição em nome de outro funcionário | `ROLE-SECTOR-ASSISTANT`, `ROLE-SECTOR-HEAD` (próprio setor); `ROLE-WAREHOUSE-STAFF` (qualquer setor) | Próprio setor (auxiliar/chefe de setor); qualquer setor (funcionário do almoxarifado) | — |
| `PERM-REQ-VIEW-OWN` | Ver requisições que a própria identidade criou | `ROLE-REQUESTER`, `ROLE-SECTOR-ASSISTANT`, `ROLE-SECTOR-HEAD`, `ROLE-WAREHOUSE-STAFF` | Próprio objeto | — |
| `PERM-REQ-VIEW-SECTOR` | Ver requisições do setor | `ROLE-SECTOR-HEAD` | Próprio setor | — |
| `PERM-REQ-VIEW-ALL-SECTORS` | Ver requisições de todos os setores | `ROLE-WAREHOUSE-STAFF` | Todos os setores | — |
| `PERM-REQ-AUTH-QUEUE-VIEW` | Ver fila de autorização | `ROLE-SECTOR-HEAD` | Próprio setor | — |
| `PERM-REQ-AUTHORIZE` | Autorizar requisição | `ROLE-SECTOR-HEAD` | Próprio setor | — (se autorização parcial deve existir é uma decisão ainda `PENDENTE`; não promovida aqui). |
| `PERM-REQ-FULFILLMENT-QUEUE-VIEW` | Ver fila de atendimento | `ROLE-WAREHOUSE-STAFF` | Todos os setores | Requisições autorizadas. |
| `PERM-REQUEST-FULFILL` | Atender requisição autorizada | `ROLE-WAREHOUSE-STAFF` | — | Requisição precisa estar autorizada. |

### Materiais / catálogo

| ID | Capacidade | Papéis autorizados | Escopo | Condições |
|---|---|---|---|---|
| `PERM-MATERIAL-VIEW` | Consultar materiais do catálogo | `ROLE-REQUESTER` | — | Requer autenticação ativa. |
| `PERM-MATERIAL-EDIT-NOTE` | Editar observação interna do material | `ROLE-WAREHOUSE-STAFF` | — | Campo próprio do WMS; não deriva nem é enviado ao SCPI. |
| `PERM-MATERIAL-DEACTIVATE` | Inativar material | `ROLE-WAREHOUSE-HEAD` | — | Exige saldo físico e saldo reservado zerados. Decisão de produto confirmada em `docs/domain-legacy/reconciliation/permissions-reconciliation.md`; o mecanismo técnico de reserva ainda não está especificado, mas a exigência permanece válida enquanto ele não existir (reservado inexistente se comporta como reservado zero) e até nova decisão explícita do dono do produto. |

### Estoque

| ID | Capacidade | Papéis autorizados | Escopo | Condições |
|---|---|---|---|---|
| `PERM-STOCK-ENTRY-CREATE` | Registrar entrada de estoque | `ROLE-WAREHOUSE-STAFF` | — | Motivo fechado (compra, doação recebida, devolução de fornecedor/garantia, empréstimo devolvido) + referência obrigatória. |
| `PERM-STOCK-ENTRY-REVERSE` | Estornar entrada de estoque | `ROLE-WAREHOUSE-HEAD` | — | Estorno é total (a entrada inteira, uma única vez); justificativa obrigatória; bloqueado se deixar saldo negativo (`INV-STOCK-001`). |
| `PERM-INVENTORY-ADJUST` | Ajustar saldo por inventário | `ROLE-WAREHOUSE-HEAD` | — | Corrige divergência de saldo apontada pela reimportação do catálogo SCPI. |
| `PERM-STOCK-HISTORY-VIEW` | Consultar histórico de movimentações de estoque | `ROLE-SECTOR-ASSISTANT` (o que criou); `ROLE-SECTOR-HEAD` (setor que chefia + o que criou); `ROLE-WAREHOUSE-STAFF`, `ROLE-AUDITOR` (tudo) | Variável por papel | — |

### Saída excepcional

| ID | Capacidade | Papéis autorizados | Escopo | Condições |
|---|---|---|---|---|
| `PERM-SAE-VIEW` | Consultar saídas excepcionais | `ROLE-WAREHOUSE-STAFF` | — | — |
| `PERM-SAE-CREATE` | Registrar saída excepcional | `ROLE-WAREHOUSE-HEAD` | — | Motivo de lista fechada (deterioração, vencimento, obsolescência, doação, empréstimo, perda/extravio, quebra/dano) + observação obrigatória. |
| `PERM-SAE-REVERSE` | Estornar saída excepcional | `ROLE-WAREHOUSE-HEAD` | — | Estorno é total; justificativa obrigatória. |

### Devolução e estorno de requisição

| ID | Capacidade | Papéis autorizados | Escopo | Condições |
|---|---|---|---|---|
| `PERM-RETURN-CREATE` | Registrar devolução | `ROLE-WAREHOUSE-HEAD` | — | Vinculada a requisição atendida. |
| `PERM-REQ-REVERSE` | Estornar requisição finalizada | `ROLE-WAREHOUSE-HEAD` | — | Justificativa obrigatória; encerra a requisição definitivamente. |
| `PERM-RETURN-REVERSE` | Estornar devolução | `ROLE-WAREHOUSE-HEAD` | — | Exige saldo disponível suficiente. |

### Importação SCPI

| ID | Capacidade | Papéis autorizados | Escopo | Condições |
|---|---|---|---|---|
| `PERM-SCPI-IMPORT-EXECUTE` | Executar importação do catálogo SCPI | `ROLE-WAREHOUSE-HEAD` | — | Duas etapas obrigatórias — prévia sem persistência, depois confirmação explícita — antes de qualquer gravação (spec 001, FR-044a). |
| `PERM-SCPI-IMPORT-HISTORY-VIEW` | Consultar histórico de execuções de importação | `ROLE-WAREHOUSE-HEAD` | — | — |

### Fornecedores

| ID | Capacidade | Papéis autorizados | Escopo | Condições |
|---|---|---|---|---|
| `PERM-SUPPLIER-IMPORT-EXECUTE` | Executar importação do cadastro de fornecedores do SCPI | `ROLE-WAREHOUSE-HEAD` | — | Prévia sem persistência, depois confirmação explícita, antes de qualquer gravação. |
| `PERM-SUPPLIER-IMPORT-HISTORY-VIEW` | Consultar histórico de execuções da importação de fornecedores | `ROLE-WAREHOUSE-HEAD` | — | — |
| `PERM-SUPPLIER-VIEW` | Consultar fornecedores | `ROLE-WAREHOUSE-STAFF` | — | Somente os dados mantidos por `INV-SUPPLIER-004`. |

### Relatórios e painéis

| ID | Capacidade | Papéis autorizados | Escopo | Condições |
|---|---|---|---|---|
| `PERM-REPORT-GENERAL-VIEW` | Acessar relatórios/consumo consolidado | `ROLE-AUDITOR` | Todos os setores | — |
| `PERM-REPORT-SECTOR-VIEW` | Acessar relatório do próprio setor | `ROLE-SECTOR-HEAD` | Próprio setor | — |
| `PERM-REPORT-EXPORT-CSV` | Exportar relatório em CSV | `ROLE-SECTOR-HEAD`, `ROLE-AUDITOR` | Conforme o relatório de origem | Respeita o escopo/filtro do relatório exportado. |
| `PERM-ALMOX-MANAGEMENT-PANEL-VIEW` | Acessar Painel de Gestão do Almoxarifado | `ROLE-WAREHOUSE-HEAD` | — | — |

## 4. Fora desta matriz (por design, não por esquecimento)

Regras que permanecem verdadeiras sobre o domínio, mas não são capacidades concedíveis a um
papel, vivem em suas fontes apropriadas — Constitution, spec vigente ou
`docs/domain/invariants-matrix.md` — nunca aqui:

- usuário inativo não acessa nem opera (`INV-AUTH-001`);
- material não pode ser criado manualmente, por nenhum papel (`INV-CATALOG-003`; spec 001, FR-006);
- fornecedor não pode ser criado nem editado manualmente, por nenhum papel (`INV-SUPPLIER-003`);
- ninguém autoriza requisição de setor alheio ao seu (regra negativa confirmada);
- liberação de reserva não entregue é efeito automático de outras transições, não uma ação
  solicitada por um papel;
- atomicidade de gravação, rastreabilidade e demais invariantes de integridade (`INV-STOCK-004`,
  `INV-MOV-001`, `INV-MOV-002`; Constitution, Princípios III e IV).

Capacidades cuja existência depende de uma máquina de estados de requisição ainda não
especificada (rascunho, envio, retorno, cancelamento por estado, atendimento parcial, separação
para retirada, cópia de requisição atendida) e o mecanismo de autenticação (matrícula/e-mail/SSO)
permanecem fora desta versão — ver `docs/domain-legacy/reconciliation/permissions-reconciliation.md`
para o raciocínio completo de cada uma.
