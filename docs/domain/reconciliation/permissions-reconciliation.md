# Reconciliação da Matriz de Permissões Legada — WMS-Almoxarifado

```text
Status: CONCLUÍDO — HISTÓRICO / NÃO NORMATIVO
Resultado canônico: docs/domain/permissions-matrix.md
Status da matriz de origem: LEGACY — NÃO NORMATIVO
```

Este documento cumpriu seu papel: reconciliar a matriz legada e produzir decisões de produto. Essas
decisões já foram canonizadas em `docs/domain/permissions-matrix.md`, que é a fonte normativa de
autorização a partir de agora. Este arquivo permanece como registro histórico do raciocínio, das
alternativas descartadas e dos itens ainda pendentes — não deve ser lido como fonte de autorização.

Este documento reconcilia `docs/domain/matriz-permissoes.md` — herdada de um projeto anterior
abandonado (referido aqui como "WMS-SAEP legado") — com o que está hoje confirmado para o novo
WMS-Almoxarifado. É um artefato de análise de domínio. **Não implementa autorização, não cria
models/views/services, não abre feature no Spec Kit e não altera a Constitution.**

A matriz legada não é tratada como correta por já existir. Cada item foi confrontado com
`PRODUCT.md`, a Constitution, `specs/001-importacao-catalogo-materiais/spec.md` e as clarificações
dadas pelo dono do produto nesta conversa, e classificado como **MANTER**, **ALTERAR**,
**DESCARTAR**, **PENDENTE** ou **NOVA LACUNA**.

## 1. Fontes lidas, nesta ordem

1. `CLAUDE.md` — precedência de fontes do projeto e escopo dos subagents.
2. `.specify/memory/constitution.md` v1.1.0 — princípios de integridade de estoque (III),
   rastreabilidade (IV), regras de negócio no backend (V), segurança por padrão (VI), design
   system e interface operacional (VIII, inclusive a nota sobre acessibilidade não ser padrão).
3. `PRODUCT.md` — papéis confirmados (funcionário do almoxarifado, chefe do almoxarifado, chefe de
   setor, requisitante, gestor/auditor, administrador de sistema) e o fluxo de
   requisição/aprovação/atendimento descrito nesta própria conversa.
4. `.claude/rules/agent-orchestration.md` — não altera o escopo desta tarefa, apenas confirma que
   mudanças de permissão passariam pelo pipeline `test-engineer → task-implementer →
   code-reviewer` **quando** viessem a ser implementadas — o que não é o caso aqui.
5. `docs/domain/matriz-permissoes.md` — a matriz legada em si (objeto desta reconciliação).
6. Documentação de domínio correlata, também herdada e lida como evidência do mesmo projeto
   abandonado, não como norma:
   - `docs/domain/matriz-invariantes.md`;
   - `docs/domain/processos-almoxarifado.md`;
   - `docs/domain/processos-saida-excepcional.md`;
   - `docs/domain/estado-transicoes-requisicao.md`.
7. `specs/001-importacao-catalogo-materiais/spec.md` — única feature já especificada no novo
   projeto; onde ela e a matriz legada tratam do mesmo assunto (catálogo, importação SCPI), a spec
   vigente tem precedência.

Não foi lido código de implementação como fonte primária: não há `models.py` nem qualquer app
Django além de `config/` neste repositório (confirmado por busca antes de iniciar a análise). Os
ADRs, `docs/CONVENTIONS.md`, `docs/design-system.md` e `CONTEXT.md` citados como referência dentro
dos documentos herdados **não existem neste repositório** — só os cinco arquivos de
`docs/domain/` foram trazidos do projeto abandonado. Isso por si só já é uma lacuna: várias
observações da matriz legada remetem a decisões (ADR-0005, ADR-0010, ADR-0011, ADR-0013, ADR-0015)
que não estão disponíveis para verificação.

## 2. Achados de maior impacto

Estes pontos precisam de decisão do dono do produto antes de qualquer especificação futura. Estão
detalhados nas seções seguintes, mas resumidos aqui porque mudam a matriz de forma material.

Todos os nove pontos abaixo foram levados ao dono do produto em 2026-09-18. As decisões estão
registradas inline; o raciocínio original de cada achado foi preservado para rastreabilidade.

1. **Registrar devolução pode ter mudado de escopo.** A matriz legada permite tanto ao funcionário
   quanto ao chefe do almoxarifado registrar devolução (`§4`, linha "Registrar devolução": Sim para
   `auxiliar_almoxarifado` e `chefe_almoxarifado`). Na clarificação de hoje, "devoluções" aparece
   listada ao lado de "estornos" e "saídas excepcionais" como atribuição que **você, como chefe**,
   deve poder operar — no mesmo grupo de operações excepcionais exclusivas.
   **Decisão (2026-09-18): registrar devolução é exclusivo do chefe do almoxarifado.** O legado é
   **ALTERADO** — deixa de ser "aux. + chefe" e passa a ser "só chefe", alinhando-se ao mesmo grupo
   de exclusividades de estorno e saída excepcional. Ver 7.8.
2. **Superusuário (legado) e Administrador de sistema (novo) não são claramente o mesmo papel.** A
   matriz legada funde inteiramente capacidade técnica (gerenciar usuários/setores/papéis, override
   de qualquer regra) num único `superuser` de framework. O `PRODUCT.md` já registra "Administrador
   de sistema" como papel de produto distinto, sem confirmar se ele herda o poder de override total
   sobre operações de estoque/requisição que o legado dava ao superusuário.
   **Decisão (2026-09-18): Administrador de sistema fica como já definido no `PRODUCT.md`
   (configura usuários, permissões e parâmetros) — o legado é esquecido nesse ponto.** Não há
   herança do poder de override de negócio do antigo `superuser`; nenhum papel de produto acumula
   autorização total sobre operações de estoque/requisição só por ser administrativo. Ver seção 6.
3. **"Auxiliar de setor" não tem confirmação no novo produto.** É um papel inteiro da matriz legada
   (cria requisição em nome de colegas do próprio setor não-almoxarifado) que nenhuma fonte do novo
   projeto menciona.
   **Decisão (2026-09-18): o papel Auxiliar de setor deve existir no novo WMS**, com a definição do
   legado (cria em nome de funcionários do próprio setor; não supervisiona o setor; sem acesso a
   outros setores, autorização, estoque ou operação de almoxarifado). Ver seção 4 e 7.3.
4. **Criar requisição em nome de terceiros ainda não foi confirmado para nenhum papel fora do
   almoxarifado.** A clarificação de hoje detalhou quem *aprova* e quem *atende*, mas não quem pode
   *criar em nome de outro funcionário*. A matriz legada assume que chefes e auxiliares de setor
   podem fazer isso pelos próprios funcionários.
   **Decisão (2026-09-18): fica como estava no legado** — chefe de setor e auxiliar de setor criam
   para funcionários do próprio setor; Almoxarifado (funcionário ou chefe) cria para qualquer
   funcionário de qualquer setor. Ver 7.3.
5. **"Ajustar estoque manualmente" está descartado no legado ("Fora do MVP"), mas a spec 001 já
   aponta que essa capacidade vai existir.** FR-047 diz explicitamente que divergência de saldo
   "será corrigida por ajuste de inventário dentro do WMS, em funcionalidade própria" — ou seja, o
   "Não" categórico do legado para essa linha já está desatualizado à luz de uma fonte mais
   autoritativa (a spec vigente).
   **Decisão (2026-09-18): fica como está na spec 001** — a capacidade existirá como funcionalidade
   própria de ajuste de inventário, ainda não especificada. **Atualização (2026-09-18, segunda
   rodada): o ator já está confirmado — só o chefe do almoxarifado executa o ajuste de inventário**,
   pela mesma lógica de estorno/devolução/saída excepcional. O mecanismo (telas, fluxo) continua em
   aberto até essa feature ser desenhada. Ver 7.6.
6. **"Executar carga inicial técnica" via script conflita com a spec 001.** FR-006 e FR-044 dizem
   que material só entra pela interface de importação, executada pelo responsável (hoje: chefe do
   almoxarifado). Uma via técnica paralela por script, mesmo restrita a superusuário, não tem
   respaldo na spec vigente.
   **Decisão (2026-09-18): fica como está na spec 001** — confirma-se DESCARTAR; não haverá via
   técnica paralela de carga inicial fora da interface de importação. Ver 7.9.
7. **Dois conceitos de "divergência" com nomes parecidos não podem ser confundidos.** Esclarecido
   abaixo, nesta mesma seção, em "Esclarecimento — divergência de saldo × divergência crítica".
8. **Nota arquitetural, fora do escopo de permissões:** a documentação legada pressupõe camadas
   próprias de `policies.py`, `services`, `selectors.py` por papel/ação. Esclarecido abaixo, em
   "Esclarecimento — camadas de implementação e Constitution Princípio I".
9. **Nota de acessibilidade, também fora do escopo de permissões:** `processos-saida-excepcional.md`
   §1.8 exige WCAG AA, ARIA e navegação por teclado como requisito do MVP. A Constitution vigente
   (Princípio VIII) diz o oposto por padrão.
   **Decisão (2026-09-18): fica como está no atual** — prevalece a Constitution vigente (Princípio
   VIII): nenhum requisito de acessibilidade é adicionado por padrão. A exigência de WCAG AA/ARIA do
   documento herdado não é adotada, a menos que uma feature futura exija explicitamente algum
   requisito pontual de acessibilidade para funcionar corretamente.

### Esclarecimento — divergência de saldo × divergência crítica

São dois mecanismos diferentes que só compartilham a palavra "divergência":

- **Divergência de saldo** (spec 001, FR-029/FR-030/FR-035): surge quando o catálogo é
  reimportado do SCPI e a quantidade do arquivo é diferente do saldo atual do material no WMS. É
  **puramente informativa** — nunca bloqueia nada, nunca muda o saldo sozinha, e existe desde a
  primeira feature especificada do projeto. A causa é sempre a mesma: o WMS e o SCPI são
  atualizados de forma independente, então os dois números podem se afastar com o tempo.
- **Divergência crítica** (legado, invariante EST-07): surge quando `saldo_físico < saldo_reservado`
  de um material — ou seja, quando existe mais estoque **reservado** por requisições autorizadas do
  que estoque físico disponível para cobrir essas reservas. Isso só pode acontecer depois que o
  mecanismo de **reserva de estoque por requisição autorizada** existir (algo que a matriz legada
  descreve em detalhe em `estado-transicoes-requisicao.md`, mas que **o novo WMS ainda não tem
  especificado** — hoje só existe a confirmação de alto nível de que chefe aprova e almoxarifado
  atende, não o mecanismo de reserva). No legado, essa divergência bloqueia separação e nova
  autorização até ser resolvida (repondo estoque ou cancelando a requisição).
- **Por que importa agora:** o nome "divergência" já está em uso na spec 001 vigente com um
  significado específico e restrito (arquivo × saldo). Quando a futura feature de requisições for
  especificada e precisar nomear o problema "reservado > físico", ela **não deve reutilizar o termo
  "divergência" sem qualificá-lo** (por exemplo, "divergência de saldo" continua exclusiva da
  reconciliação com o SCPI; o problema de reserva pode ser chamado de outra coisa, como
  "indisponibilidade de estoque reservado" ou equivalente, a decidir nessa especificação futura).
  Esta reconciliação não nomeia a feature futura — só impede que os dois conceitos sejam fundidos
  silenciosamente por reaproveitarem o mesmo rótulo.

### Esclarecimento — camadas de implementação e Constitution Princípio I

A documentação legada foi escrita presumindo uma arquitetura Django estendida com camadas
próprias: `policies.py` (autorização compartilhada entre views e services), `services` (regras de
negócio e transações) e `selectors.py` (consultas/visibilidade). Cada uma dessas camadas é uma
estrutura adicional além do que o Django oferece nativamente (models, forms, views, ORM, admin,
middleware).

A Constitution vigente, Princípio I ("Simplicidade Arquitetural"), estabelece a ordem inversa: toda
solução **DEVE** usar primeiro o recurso convencional do Django, e camadas como services,
repositories ou equivalentes **NÃO DEVEM** ser criadas sem um problema concreto e identificável que
elas resolvam, com essa justificativa registrada por escrito na mudança que as introduz.

O que isso significa na prática para este relatório:

- As **regras de negócio e de autorização** capturadas nesta reconciliação (quem pode fazer o quê,
  sob qual escopo e condição) continuam válidas como conhecimento de domínio, independentemente de
  como venham a ser implementadas.
- O **padrão de camadas** do legado (um arquivo `policies.py` e um `selectors.py` por app, services
  para cada mutação) **não é adotado automaticamente** só porque o projeto anterior o usava. Se a
  futura implementação decidir usar essas camadas, o `plan.md` daquela feature precisa justificar
  por escrito o problema concreto que cada camada resolve — por exemplo, "autorização contextual
  repetida por objeto/setor/estado, chamada por view e por comando de management, precisa de um
  ponto único" seria uma justificativa concreta; "o projeto anterior organizava assim" não seria.
- Esta reconciliação **não decide isso agora** — só evita que a decisão seja tomada por inércia
  quando a implementação começar.

### Motivos de saída excepcional — RESOLVIDO em 2026-09-18 (segunda rodada)

Lista fechada final, unindo os dois conjuntos e removendo redundâncias:

- **deterioração**
- **vencimento**
- **obsolescência**
- **doação**
- **empréstimo**
- **perda/extravio**
- **quebra/dano**

Removidos do enum herdado: `ajuste_operacional` (passa a ser coberto pela feature de ajuste de
inventário — achado 5/7.6 — evitando dois mecanismos diferentes para o mesmo problema) e
`consumo_interno` (confirmado que não ocorre na prática do almoxarifado). Ver 7.7.

## 3. Taxonomia usada

Separando os quatro conceitos que a matriz legada às vezes mistura em uma única célula:

- **Papel/perfil**: quem age (ex.: chefe do almoxarifado, requisitante).
- **Ação/capacidade**: o que pode ser feito (ex.: registrar saída excepcional), nomeada como
  capacidade de negócio, nunca como view, endpoint, template ou verbo HTTP.
- **Escopo**: sobre o quê (ex.: próprio setor, todos os setores, objeto criado pelo próprio
  usuário).
- **Condição adicional**: quando/sob que regra (ex.: só em determinado estado, só com
  justificativa, só se o material estiver ativo).

**Autorização não é interface.** Nenhum item classificado abaixo foi tratado como permissão por
estar visível ou escondido em algum botão, menu ou template — a matriz legada, nesse aspecto
específico, já é predominantemente redigida em termos de autorização de domínio/backend (ela
explicita, por exemplo, que "ocultar um elemento não é autorização" em espírito, ao dizer que
`permission_classes` não substitui validação por objeto/setor/papel/estado). A única seção herdada
que mistura UI é `processos-saida-excepcional.md` §1.8 ("Front-end"); ela foi excluída desta
reconciliação de permissões e citada só como nota de conflito de acessibilidade (achado 9, acima).

## 4. Reconciliação de papéis

| Papel legado | Técnico legado | Papel novo correspondente | Classificação | Evidência |
|---|---|---|---|---|
| Solicitante | `solicitante` | Requisitante | ALTERAR (nome) | PRODUCT.md usa "Requisitante"; conceito idêntico: qualquer funcionário pode solicitar material para si. |
| Auxiliar de setor | `auxiliar_setor` | Auxiliar de setor | MANTER | **Decisão (2026-09-18):** o papel deve existir no novo WMS, com a definição do legado — cria em nome de funcionários do próprio setor; consulta o que criou; não supervisiona o setor; sem acesso a outros setores, autorização, estoque ou operação de almoxarifado. |
| Chefe de setor | `chefe_setor` | Chefe de setor | MANTER | Confirmado nesta conversa: "qualquer outro chefe deve poder aprovar requisições feitas por funcionários dos seus setores." |
| Auxiliar de Almoxarifado | `auxiliar_almoxarifado` | Funcionário do almoxarifado | ALTERAR (nome) | PRODUCT.md e esta conversa usam "funcionário do almoxarifado"; capacidades centrais (registrar movimentação, atender requisição aprovada) coincidem. |
| Chefe de Almoxarifado | `chefe_almoxarifado` | Chefe do almoxarifado | MANTER (com ajustes pontuais de escopo — ver §7) | Confirmado nesta conversa como o próprio dono do produto; a maior parte das exclusividades do legado (importação SCPI, estorno, saída excepcional) já bate com o que foi dito hoje. |
| Superusuário | `superuser` | Não adotado como papel de produto | DESCARTAR (como papel de negócio) | **Decisão (2026-09-18):** Administrador de sistema fica como já definido no `PRODUCT.md`; o legado é esquecido nesse ponto. Não há papel de produto que herde o poder de override total de negócio do antigo `superuser`. Uma conta técnica de manutenção (Django superuser) pode continuar existindo como mecanismo de infraestrutura, mas isso é decisão de implementação, não um papel do modelo de permissões. Ver seção 6. |
| — | — | Gestor/auditor | NOVA LACUNA (papel existe; escopo confirmado) | Confirmado nesta conversa ("todos estes existem e mais"). **Decisão (2026-09-18, segunda rodada):** vê relatórios/consumo consolidado de **todos os setores** e o **histórico completo de movimentações de estoque** (mesmo nível de acesso do Almoxarifado no ledger). Histórico de importações do SCPI não foi incluído no escopo deste papel — continua exclusivo do chefe do almoxarifado. A matriz legada não tinha papel equivalente. |
| — | — | Administrador de sistema | MANTER (definição do PRODUCT.md) | **Decisão (2026-09-18):** fica exatamente como no `PRODUCT.md` — "configura usuários, permissões e parâmetros do WMS" — sem herdar poder de negócio/operação de estoque do `superuser` legado. |

### Conceitos de escopo (§3 da matriz legada)

| Conceito | Regra legada | Classificação | Evidência |
|---|---|---|---|
| Criador | Quem registrou a requisição; pode agir nos estados permitidos. | PENDENTE | Útil e coerente, mas depende da máquina de estados de requisição, ainda não confirmada (ver §7.2). |
| Beneficiário | Quem recebe o material; pode agir nos estados permitidos. | PENDENTE | Mesma dependência acima. |
| Setor do beneficiário | Define o setor da requisição e a fila de autorização; nunca o setor do criador. | MANTER | Consistente com a confirmação de hoje: a aprovação segue o setor de quem vai receber o material, e o chefe de cada setor aprova a própria equipe. |
| Chefe autorizador | Chefe do setor do beneficiário; chefe de Almoxarifado só autoriza o setor Almoxarifado. | MANTER | Bate exatamente com "eu como chefe devo poder aprovar requisições feitas por funcionários do almoxarifado, assim como qualquer outro chefe... de seus setores." |
| Saída excepcional (conceito) | Documento de estoque próprio, sem beneficiário/setor de destino; consulta mais ampla que mutação. | MANTER (conceito); registro/estorno exclusivos do chefe do almoxarifado | Confirmado hoje: estornos, devoluções e saídas excepcionais são atribuição do chefe. |

## 5. Escopo organizacional

- O `PRODUCT.md` confirma **um único almoxarifado físico**. A matriz legada nunca presume mais de
  um almoxarifado — ela trata "Almoxarifado" como uma única operação transversal a todos os
  setores. Não há conflito aqui: **MANTER** o modelo de almoxarifado único.
- Toda autorização de requisição no legado é escopada por **setor**, nunca por local físico
  arbitrário. Isso é compatível com o que foi confirmado hoje. **MANTER** o eixo "setor" como
  unidade de escopo organizacional para aprovação.
- A estrutura organizacional — **RESOLVIDO em 2026-09-18 (segunda rodada)**: fica exatamente como
  no legado. USR-03 (usuário pertence a um único setor), USR-04 (todo setor ativo tem exatamente um
  chefe ativo, que pertence ao próprio setor) e USR-05 (um chefe responde por um único setor) são
  **MANTIDAS** como invariantes confirmadas da estrutura organizacional do novo WMS.

## 6. Administrador (tratamento especial) — RESOLVIDO em 2026-09-18

**Decisão do dono do produto: Leitura A.** Administrador de sistema é só o escopo (1) — configurar
usuários, permissões e parâmetros — exatamente como já registrado no `PRODUCT.md`. O legado é
esquecido nesse ponto: não existe papel de produto que herde o poder de negócio total (2) que o
antigo `superuser` tinha (autorizar qualquer setor, importar SCPI, registrar saída excepcional
etc. só por ser administrador). Cada ação de negócio permanece exclusivamente sob a regra própria
já reconciliada nas seções 4 e 7 (chefe do almoxarifado, chefe de setor, auxiliar de setor,
funcionário do almoxarifado). O raciocínio original que levou a essa decisão fica abaixo, para
rastreabilidade.

A matriz legada usa "superusuário" para dois papéis normativamente diferentes, sem separá-los:

1. **Override técnico**: acesso irrestrito por ser conta técnica/de manutenção do sistema
   (equivalente ao superusuário do Django), incluindo ações que nenhum papel de negócio deveria ter
   rotineiramente (gerenciar usuários, setores, papéis; executar carga inicial técnica).
2. **Poder de negócio total**: o mesmo papel também herda, no legado, toda capacidade operacional
   de qualquer outro papel (autorizar qualquer setor, importar SCPI, registrar saída excepcional
   etc.) — inclusive quando um papel de negócio mais específico (chefe do almoxarifado, chefe de
   setor) já cobre essa ação.

O `PRODUCT.md` só confirma um "Administrador de sistema" com escopo (1) — configurar usuários,
permissões e parâmetros — e não confirma (2). Duas leituras são possíveis e nenhuma foi decidida:

- **Leitura A**: Administrador de sistema é só (1); poder de negócio total (2) não existe como
  papel — cada ação de negócio segue exclusivamente sua regra própria (chefe do almoxarifado, chefe
  de setor etc.), sem atalho técnico.
- **Leitura B**: existe um papel técnico com override total, do jeito que o legado modela, mas ele
  não deveria se chamar "Administrador de sistema" nem ser confundido com ele — seria uma conta de
  manutenção separada.

A Leitura A foi a escolhida, exatamente para não esconder ausência de modelagem atrás de "admin
pode tudo": cada capacidade antes marcada como "herdada do superusuário" nas tabelas da seção 7 foi
atualizada para refletir que **não há mais um papel de override total** — o que resta dessas linhas
é a regra de negócio específica (chefe do almoxarifado, chefe de setor etc.), sem a coluna extra de
"superusuário: Sim".

## 7. Inventário e classificação das permissões (ação por ação)

Convenção de código: `PERM-<DOMÍNIO>-<AÇÃO>`. Nomes evitam view, endpoint, template ou verbo HTTP.

### 7.1 Autenticação e acesso geral

| Nome legado | Código novo | Papéis legados | Escopo | Condição | Classificação | Evidência / justificativa |
|---|---|---|---|---|---|---|
| Autenticar por matrícula | `PERM-AUTH-LOGIN` | Todos | Geral | Usuário inativo não acessa. | PENDENTE (deferido) | A exigência de autenticação é sólida (Constitution, Princípio VI) e fica MANTIDA. **O mecanismo específico (matrícula, e-mail institucional, SSO) foi perguntado em 2026-09-18 e adiado deliberadamente** para quando a feature de autenticação/usuários for desenhada — não é uma lacuna esquecida. |
| Acessar como usuário ativo | `PERM-AUTH-ACTIVE-REQUIRED` | Todos | Geral | Pré-condição de qualquer ação. | MANTER | Regra genérica e de baixo risco, coerente com Constitution Princípio VI; nenhuma fonte a contradiz. |

### 7.2 Administração técnica

| Nome legado | Código novo | Papéis legados | Escopo | Condição | Classificação | Evidência / justificativa |
|---|---|---|---|---|---|---|
| Gerenciar usuários | `PERM-USER-MANAGE` | Superusuário → Administrador de sistema | Global | — | ALTERAR | **Resolvido (2026-09-18):** passa para Administrador de sistema, sem trazer junto o poder de negócio que o `superuser` legado tinha (seção 6). |
| Gerenciar setores | `PERM-SECTOR-MANAGE` | Superusuário → Administrador de sistema | Global | Setor exige chefe (USR-04). | ALTERAR | Mesma resolução acima; a regra "setor exige chefe ativo" (USR-04) é plausível mas depende da estrutura organizacional ainda pendente (seção 5). |
| Gerenciar papéis | `PERM-ROLE-MANAGE` | — | — | — | DESCARTAR | **Decisão (2026-09-18, segunda rodada):** papéis são fixos no código (chefe, funcionário do almoxarifado, chefe de setor, auxiliar de setor, requisitante, gestor/auditor, administrador de sistema), sem tela de gestão de papéis em runtime — coerente com a Constitution, Princípio I. Administrador de sistema continua atribuindo papéis existentes a usuários (`PERM-USER-MANAGE`), mas não cria papéis novos. |

### 7.3 Requisição — criação e visibilidade

| Nome legado | Código novo | Papéis legados | Escopo | Condição | Classificação | Evidência / justificativa |
|---|---|---|---|---|---|---|
| Criar requisição para si | `PERM-REQ-CREATE-SELF` | Todos | Próprio usuário | — | MANTER | PRODUCT.md: qualquer funcionário de qualquer setor pode ser requisitante. |
| Criar para funcionário do próprio setor | `PERM-REQ-CREATE-SECTOR-PROXY` | Auxiliar de setor, Chefe de setor (próprio setor); Almoxarifado (qualquer setor) | Setor próprio / qualquer setor | — | MANTER | **Decisão (2026-09-18): fica como era no legado.** Auxiliar de setor e chefe de setor criam para funcionários do próprio setor; Almoxarifado cria para qualquer funcionário de qualquer setor. |
| Criar para funcionário de outro setor | `PERM-REQ-CREATE-ANY-SECTOR` | Almoxarifado | Qualquer setor | — | MANTER | Mesma decisão acima. |
| Ver próprias requisições como criador | `PERM-REQ-VIEW-OWN-AS-CREATOR` | Todos | Próprio objeto | — | MANTER | Consequência direta de poder criar; nenhuma fonte contradiz. |
| Ver próprias requisições como beneficiário | `PERM-REQ-VIEW-OWN-AS-BENEFICIARY` | Todos | Próprio objeto | Exceto rascunho criado por terceiro. | PENDENTE | A regra em si é razoável, mas depende do conceito de "rascunho" e de criação por terceiro, ambos pendentes. |
| Ver requisições do setor | `PERM-REQ-VIEW-SECTOR` | Chefe de setor (próprio setor); Almoxarifado (qualquer setor) | Setor / qualquer setor | Rascunho de terceiro fica fora. | MANTER (núcleo); PENDENTE (o recorte de rascunho) | O núcleo — chefe vê as requisições do próprio setor para poder decidir — está diretamente confirmado hoje. O detalhe "rascunho de terceiro fica fora" depende do estado "rascunho", pendente. |
| Ver todos os setores | `PERM-REQ-VIEW-ALL-SECTORS` | Almoxarifado | Todos os setores | — | MANTER | Confirmado hoje: qualquer funcionário do almoxarifado deve poder atender qualquer requisição aprovada, o que exige poder vê-la, seja qual for o setor de origem. |

### 7.4 Requisição — ciclo de vida

A matriz legada assume uma máquina de estados detalhada (rascunho → aguardando autorização →
autorizada → pronta para retirada → atendida → cancelada → estornada) descrita em
`estado-transicoes-requisicao.md`. **Perguntado explicitamente em 2026-09-18 (segunda rodada) e
adiado deliberadamente para uma spec própria de requisições** — não é uma lacuna esquecida, é uma
decisão de sequenciamento do próprio dono do produto. Só o formato de alto nível ("requisitante
cria → chefe do setor aprova → almoxarifado atende") está confirmado. Por isso, toda linha desta
subseção carrega a mesma ressalva: a hierarquia de papéis é plausível e consistente com o que já se
sabe, mas o estado/mecânica em si continua pendente até aquela spec.

| Nome legado | Código novo | Papéis legados | Escopo | Condição | Classificação | Evidência / justificativa |
|---|---|---|---|---|---|---|
| Editar rascunho | `PERM-REQ-EDIT-DRAFT` | Criador | Próprio objeto | Só em estado rascunho. | PENDENTE | Estado "rascunho" não confirmado. |
| Enviar para autorização | `PERM-REQ-SUBMIT` | Criador | Próprio objeto | — | PENDENTE | Mesma razão. |
| Retornar para rascunho (inclui a antiga "recusa") | `PERM-REQ-RETURN-TO-DRAFT` | Criador, Beneficiário, Chefe do setor do beneficiário | Próprio objeto / setor | Motivo obrigatório quando é o chefe decidindo; opcional quando é criador/beneficiário. | PENDENTE | O papel que decide (chefe do setor do beneficiário) é coerente com o que foi confirmado; o mecanismo de "retorno" versus "recusa" como o mesmo evento é detalhe de implementação herdado, não confirmado. |
| Cancelar aguardando autorização | `PERM-REQ-CANCEL-PENDING` | Criador, Beneficiário | Próprio objeto | Sem justificativa. | PENDENTE | Depende do estado. |
| Cancelar autorizada/pronta para retirada | `PERM-REQ-CANCEL-AUTHORIZED` | Criador, Beneficiário, Almoxarifado | Próprio objeto | Com justificativa; libera reserva. | PENDENTE | Depende do estado e do mecanismo de reserva, nenhum confirmado ainda. |
| Copiar atendida | `PERM-REQ-COPY` | Quem via a origem e pode criar para o beneficiário resultante | Próprio objeto de origem | Não copia autorizada/entregue. | PENDENTE | Feature de conveniência plausível, sem qualquer confirmação de produto. |
| Ver fila de autorizações | `PERM-REQ-AUTH-QUEUE-VIEW` | Chefe de setor (próprio setor); Chefe de Almoxarifado (setor Almoxarifado) | Setor | — | MANTER | Decorre diretamente de quem aprova, já confirmado. |
| Autorizar | `PERM-REQ-AUTHORIZE` | Chefe de setor (próprio setor); Chefe de Almoxarifado (setor Almoxarifado) | Setor | Autorização é integral, nunca parcial. | MANTER | Núcleo confirmado hoje ipsis litteris. |
| Autorizar parcialmente | `PERM-REQ-AUTHORIZE-PARTIAL` | Ninguém (regra sempre negativa) | — | — | PENDENTE | Regra de negócio herdada plausível ("autoriza tudo ou devolve"), mas não confirmada; requer decisão explícita quando a feature de requisição for especificada. |
| Autorizar outro setor | `PERM-REQ-AUTHORIZE-OTHER-SECTOR` | Ninguém | — | — | MANTER (bloqueio) | **Resolvido pela seção 6:** sem papel de override de negócio, ninguém autoriza requisição de setor alheio — nem mesmo Administrador de sistema. |
| Ver fila de atendimento | `PERM-REQ-FULFILLMENT-QUEUE-VIEW` | Almoxarifado | Todos os setores | Requisições autorizadas/prontas para retirada. | MANTER (núcleo) | Decorre de "qualquer funcionário do almoxarifado atende requisição aprovada", confirmado hoje. O recorte por dois estados distintos (autorizada/pronta para retirada) é detalhe pendente. |
| Separar para retirada | `PERM-REQ-PREPARE` | Almoxarifado | — | Transição intermediária antes da entrega. | PENDENTE | Etapa extra do legado não confirmada; hoje só se confirmou "atender e concluir", sem uma etapa distinta de separação. |
| Registrar atendimento parcial | `PERM-REQ-FULFILL-PARTIAL` | Almoxarifado | — | Exige justificativa por item menor/zero. | PENDENTE | Atendimento parcial em si não foi mencionado hoje. |
| Registrar atendimento total | `PERM-REQ-FULFILL-TOTAL` | Almoxarifado | — | — | MANTER | Núcleo confirmado hoje: qualquer funcionário do almoxarifado conclui o atendimento de uma requisição aprovada. |
| Cancelar por falta operacional antes da retirada | `PERM-REQ-CANCEL-OPERATIONAL` | Almoxarifado, Criador, Beneficiário | — | Justificativa obrigatória. | PENDENTE | Depende do estado "pronta para retirada", pendente. |
| Liberar reserva não entregue | — (efeito automático, não uma permissão concedida a um papel) | — | — | — | DESCARTAR (como item de matriz de permissões) | É consequência automática de outras transições, não uma ação que um papel solicita; pertence a uma futura matriz de invariantes/estados, não a uma matriz de permissões. Mecanismo de "reserva" em si, pendente. |

### 7.5 Materiais / catálogo

| Nome legado | Código novo | Papéis legados | Escopo | Condição | Classificação | Evidência / justificativa |
|---|---|---|---|---|---|---|
| Buscar materiais para requisição | `PERM-MATERIAL-SEARCH-FOR-REQUEST` | Todos | — | Bloqueia inativo, sem saldo ou divergente. | PENDENTE | Depende da feature de requisição, ainda não especificada; a regra de elegibilidade em si é plausível. |
| Consultar materiais | `PERM-MATERIAL-VIEW` | Todos | — | Histórico amplo segue escopo de relatório. | MANTER | Já coberto por `specs/001-importacao-catalogo-materiais/spec.md` FR-039 a FR-043: consulta exige só autenticação (FR-045), sem recorte por papel. Convergência forte entre legado e spec vigente. |
| Editar observação interna do material | `PERM-MATERIAL-EDIT-NOTE` | Funcionário do almoxarifado (qualquer, inclui chefe) | — | Único campo textual editável localmente, sem relação com dados do SCPI. | MANTER | **Decisão (2026-09-18, segunda rodada):** confirmado que o campo deve existir, editável por qualquer funcionário do almoxarifado. Não conflita com FR-002/FR-024/FR-026 da spec 001 porque é um campo próprio do WMS, nunca enviado ou derivado do SCPI. |
| Inativar material | `PERM-MATERIAL-DEACTIVATE` | Chefe de Almoxarifado (exclusivo) | — | Exige físico e reservado zerados. | MANTER | **Decisão (2026-09-18, segunda rodada):** confirmado, exclusivo do chefe do almoxarifado, como no legado. Não conflita com a spec 001 (Fora de Escopo: "criação, edição ou exclusão manual de materiais" — inativação é reversível e não é nenhuma das três). |
| Criação manual de material | *(não existe no legado como permissão concedida a ninguém)* | Ninguém | — | — | MANTER (bloqueio) | Confirmado com a força máxima possível: spec 001 FR-006 — "o sistema NÃO DEVE oferecer nenhum meio de criar material manualmente." Convergência total com o legado, que também nunca concede essa permissão a nenhum papel. |

### 7.6 Movimentação de estoque

| Nome legado | Código novo | Papéis legados | Escopo | Condição | Classificação | Evidência / justificativa |
|---|---|---|---|---|---|---|
| Operar movimentação de estoque | `PERM-STOCK-MOVEMENT-OPERATE` | Almoxarifado | — | Só por operação formal (não ad-hoc). | MANTER (princípio); PENDENTE (mecânica) | O princípio — só o almoxarifado opera estoque, e só por operação formal e rastreável — é diretamente reforçado pela Constitution (Princípios III e IV). A mecânica específica (ledger `MovimentacaoEstoque`, deltas assinados) é detalhe de implementação herdado, não confirmado. |
| Ajustar estoque manualmente | `PERM-STOCK-ADJUST-MANUAL` | Chefe de Almoxarifado (exclusivo) | — | Feature própria de ajuste de inventário (FR-047), ainda não desenhada. | ALTERAR | O legado bloqueava isso para todos. A spec 001 (FR-047) já estabelece que a correção de saldo divergente **vai** existir como funcionalidade própria. **Decisão (2026-09-18, segunda rodada): o ator é o chefe do almoxarifado**, exclusivo, pela mesma lógica de estorno/devolução/saída excepcional. O mecanismo/telas continuam em aberto. |
| Consultar histórico de movimentações | `PERM-STOCK-HISTORY-VIEW` | Escopado por papel (auxiliar de setor: só o que criou; chefe de setor: setor + o que criou; Almoxarifado e Gestor/auditor: tudo) | Variável | — | MANTER | **Decisão (2026-09-18, segunda rodada):** confirmado que deve existir esse histórico/ledger consultável, com o escopo de visibilidade do legado, incluindo o Gestor/auditor no grupo que vê tudo. |
| Consultar divergências críticas | `PERM-STOCK-DIVERGENCE-CRITICAL-VIEW` | Almoxarifado | — | Marcador `físico < reservado` (EST-07). | PENDENTE | **Atenção**: este é um conceito de divergência diferente da "divergência de saldo" já definida na spec 001 (arquivo SCPI × saldo do WMS) — ver esclarecimento na seção 2. EST-07 depende do mecanismo de reserva de requisições, cuja máquina de estados foi deliberadamente adiada (seção 2, achado 1; seção 7.4). Continua pendente até essa feature ser desenhada. |
| **Registrar entrada de estoque** *(nenhum equivalente no legado)* | `PERM-STOCK-ENTRY-CREATE` | Funcionário do almoxarifado (qualquer, inclui chefe) | — | Motivo fechado + referência obrigatória (nota fiscal/empenho/documento equivalente). | NOVA LACUNA (resolvida em 2026-09-18, discussão dedicada) | **Motivação:** a spec 001 (FR-028) proíbe a reimportação do catálogo de sobrescrever saldo de material já existente — ela só cria material novo ou aponta divergência. Não existia, em nenhuma fonte, um jeito de um material **já existente** ganhar saldo por chegada física de compra/doação/devolução de fornecedor/empréstimo devolvido, fora do fluxo de importação. **Decisão:** capacidade nova, rotineira (não excepcional) — qualquer funcionário do almoxarifado registra, com motivo de uma lista fechada e referência obrigatória para rastreabilidade (Constitution, Princípio IV). Distinta de: saldo inicial (nasce da importação SCPI), ajuste de inventário (7.6, exclusivo do chefe, corrige divergência), e devolução de requisição (7.8, exclusiva do chefe, vinculada a uma requisição atendida). |

**Motivos fechados de entrada de estoque**: Compra, Doação recebida, Devolução de
fornecedor/garantia, Empréstimo devolvido por outro setor/órgão.

### 7.7 Saída excepcional

| Nome legado | Código novo | Papéis legados | Escopo | Condição | Classificação | Evidência / justificativa |
|---|---|---|---|---|---|---|
| Consultar saídas excepcionais | `PERM-SAE-VIEW` | Almoxarifado (funcionário e chefe) | — | Lista e detalhe do documento. | MANTER | Consulta mais ampla que mutação é um princípio razoável; nenhuma fonte nova o contradiz, e não há indicação de que o funcionário comum precise deixar de ver esses documentos. Sem override de superusuário (seção 6). |
| Registrar saída excepcional | `PERM-SAE-CREATE` | Chefe de Almoxarifado (exclusivo) | — | Motivo fechado (enum) e observação obrigatória; baixa física direta. | MANTER | Confirmado hoje quase literalmente: "saídas excepcionais (por deterioração, vencimento, obsolescência, doação, empréstimos, etc.)" como atribuição do chefe. Sem override de superusuário (seção 6). Enum de motivos redefinido — ver nota abaixo. |
| Estornar saída excepcional | `PERM-SAE-REVERSE` | Chefe de Almoxarifado (exclusivo) | — | Estorno total only; justificativa obrigatória. | MANTER | Confirmado hoje: "estornos" listados junto de saídas excepcionais como atribuição do chefe. Sem override de superusuário (seção 6). |

**Nota sobre motivos de saída excepcional — RESOLVIDO em 2026-09-18 (segunda rodada)**: o enum
final é **deterioração, vencimento, obsolescência, doação, empréstimo, perda/extravio, quebra/dano**
(7 motivos). `ajuste_operacional` do legado foi removido (passa a ser coberto pela feature de
ajuste de inventário, 7.6) e `consumo_interno` também foi removido (confirmado que não ocorre na
prática). Ver esclarecimento completo na seção 2.

### 7.8 Devolução e estorno de requisição

| Nome legado | Código novo | Papéis legados | Escopo | Condição | Classificação | Evidência / justificativa |
|---|---|---|---|---|---|---|
| Registrar devolução | `PERM-RETURN-CREATE` | Chefe de Almoxarifado (exclusivo) | — | Vinculada a requisição atendida. | ALTERAR | **Decisão (2026-09-18):** exclusivo do chefe do almoxarifado. O legado (aux. + chefe) é alterado — funcionário comum do almoxarifado não registra devolução. |
| Estornar requisição finalizada | `PERM-REQ-REVERSE` | Chefe de Almoxarifado | — | Justificativa obrigatória; encerra definitivamente. | MANTER | Confirmado hoje: "estornos" como atribuição do chefe. |
| Estornar devolução | `PERM-RETURN-REVERSE` | Chefe de Almoxarifado | — | Exige saldo disponível suficiente. | MANTER | Mesma evidência acima; consequência natural de "devoluções" e "estornos" estarem no mesmo grupo de exclusividades citado hoje. |

### 7.9 Importação e reconciliação com o SCPI

| Nome legado | Código novo | Papéis legados | Escopo | Condição | Classificação | Evidência / justificativa |
|---|---|---|---|---|---|---|
| Executar carga inicial técnica | `PERM-SCPI-BOOTSTRAP-TECH` | Superusuário | — | "Piloto pode usar script/modo técnico." | DESCARTAR | Conflita com a spec vigente: FR-006 ("nenhum meio de criar material manualmente") e FR-044 ("o responsável autorizado envia o arquivo pela interface da aplicação") não deixam espaço para uma via técnica paralela de carga inicial fora da interface de importação. A spec 001 tem precedência sobre a matriz legada. |
| Executar importação SCPI | `PERM-SCPI-IMPORT-EXECUTE` | Chefe de Almoxarifado (exclusivo) | — | — | MANTER | Confirmação direta e explícita nesta conversa e no `PRODUCT.md`; também já era a conclusão da própria matriz legada. Sem override de superusuário (seção 6). Convergência forte. |
| Pré-visualizar importação | `PERM-SCPI-IMPORT-PREVIEW` | Chefe de Almoxarifado (exclusivo) | — | Sem persistência. | MANTER | **Decisão (2026-09-18, segunda rodada):** confirmado — a importação tem duas etapas, prévia (sem gravar) e confirmação. **Nota:** a spec 001, no texto atual, descreve um fluxo de um passo só ("o responsável autorizado envia o arquivo... e o sistema apresenta o resultado da execução", FR-044). Essa decisão não contradiz nenhum FR da spec 001 (o resultado ainda é apresentado na interface), mas adiciona uma etapa que o texto vigente não descreve explicitamente — vale revisar/emendar a spec 001 quando essa parte da feature for implementada, para não deixar a UI real desalinhada do texto normativo. |
| Confirmar importação com alertas | `PERM-SCPI-IMPORT-CONFIRM` | Chefe de Almoxarifado (exclusivo) | — | Confirmação explícita. | MANTER | Mesma decisão acima. |
| Consultar histórico de importações | `PERM-SCPI-IMPORT-HISTORY-VIEW` | Chefe de Almoxarifado (exclusivo) | — | — | MANTER | Já coberto por FR-037 da spec 001 ("preservar o resultado de cada execução para consulta posterior"); o papel responsável (chefe) é coerente com quem executa a importação. Sem override de superusuário (seção 6). |

### 7.10 Notificações — DESCARTADO em 2026-09-18 (segunda rodada)

**Decisão: sem notificações no MVP.** Usuários conferem status entrando no sistema. As três linhas
abaixo do legado são descartadas por ora; podem ser reabertas se uma necessidade concreta aparecer
depois que o fluxo de requisições estiver em produção.

| Nome legado | Código novo | Papéis legados | Escopo | Condição | Classificação | Evidência / justificativa |
|---|---|---|---|---|---|---|
| Receber notificações das próprias requisições | `PERM-NOTIFICATION-RECEIVE-OWN` | Todos | Próprio objeto | Criador e beneficiário. | DESCARTAR | Decisão explícita: sem notificações por enquanto. |
| Receber autorização pendente | `PERM-NOTIFICATION-RECEIVE-AUTH-PENDING` | Chefe de setor / Chefe de Almoxarifado | Setor | Quem pode autorizar. | DESCARTAR | Mesma decisão. |
| Receber notificação de atendimento | `PERM-NOTIFICATION-RECEIVE-FULFILLMENT` | Todos | Próprio objeto | Criador e beneficiário. | DESCARTAR | Mesma decisão. |

### 7.11 Relatórios e painéis

| Nome legado | Código novo | Papéis legados | Escopo | Condição | Classificação | Evidência / justificativa |
|---|---|---|---|---|---|---|
| Acessar relatórios gerais (consolidado, todos os setores) | `PERM-REPORT-GENERAL-VIEW` | Gestor/auditor | Todos os setores | — | MANTER | **Decisão (2026-09-18, segunda rodada):** confirmado — o Gestor/auditor vê relatórios/consumo consolidado de todos os setores. |
| Acessar relatórios do próprio setor | `PERM-REPORT-SECTOR-VIEW` | Chefe de setor | Setor | — | MANTER | **Decisão (2026-09-18, segunda rodada):** confirmado, como no legado. |
| Exportar CSV de relatórios | `PERM-REPORT-EXPORT-CSV` | Chefe de setor, Gestor/auditor | Conforme filtro | Respeita escopo. | MANTER | Mesma decisão acima. |
| Painel Gestão do Almoxarifado | `PERM-ALMOX-MANAGEMENT-PANEL-VIEW` | Chefe de Almoxarifado (exclusivo) | — | — | MANTER | **Decisão (2026-09-18, segunda rodada):** confirmado — tela própria, mais ampla, exclusiva do chefe do almoxarifado, distinta dos relatórios do Gestor/auditor. |

## 8. Checklist de áreas do domínio (usado só para achar lacunas, não como exigência de permissões independentes)

| Área | Coberta pela matriz legada? | Coberta por fonte já confirmada do novo produto? | Observação |
|---|---|---|---|
| Materiais / catálogo | Sim | Sim (spec 001) | Convergência forte; ver 7.5. |
| Consulta de estoque | Sim (junto de materiais) | Sim (spec 001, saldo é campo do material) | Sem lacuna nova. |
| Entradas | Não modelada como ação própria — só aparece embutida em "operar movimentação de estoque" e na importação SCPI (saldo inicial). | **Resolvido (2026-09-18):** nova capacidade "Registrar entrada de estoque" (`PERM-STOCK-ENTRY-CREATE`), aberta a qualquer funcionário do almoxarifado, com motivo fechado e referência obrigatória. | NOVA LACUNA, discutida e fechada — ver 7.6. |
| Saídas (não excepcionais) | Só via atendimento de requisição. | Fluxo de requisição confirmado em alto nível, não em detalhe. | Ver 7.4. |
| Saídas excepcionais | Sim, detalhada. | Confirmada hoje como exclusividade do chefe. | Ver 7.7. |
| Transferências | Explicitamente fora do escopo do legado ("não cobre... transferência"). | Não mencionada em nenhuma fonte do novo produto. | Sem evidência — não é lacuna, é ausência simétrica dos dois lados. |
| Ajustes | Bloqueado no legado ("Fora do MVP"). | Já anunciado pela spec 001 (FR-047); ator confirmado como chefe do almoxarifado. | **ALTERAR, resolvido quanto ao ator** — ver 7.6 e achado 5. |
| Inventários (contagem formal) | Explicitamente fora do escopo do legado. | Citado pela spec 001 como o mecanismo que resolverá divergências de saldo (FR-047), mas nunca especificado. | NOVA LACUNA — feature inteira ainda não existe em nenhum dos dois lados; a spec 001 só a menciona como destino futuro. |
| Histórico / movimentações | Sim, detalhado. | **Resolvido:** deve existir, com o escopo de visibilidade do legado + Gestor/auditor no grupo que vê tudo. | Ver 7.6. |
| Administração de usuários/papéis | Sim, exclusiva de superusuário. | Papel "Administrador de sistema" confirmado, com o escopo definido no `PRODUCT.md` (sem poder de negócio herdado); papéis são fixos no código, sem tela de gestão de papéis. | Resolvido — ver seção 6 e 7.2. |
| Relatórios | Sim. | **Resolvido:** Gestor/auditor (consolidado, todos os setores) + chefe de setor (próprio setor, com CSV) + Painel de Gestão do Almoxarifado (exclusivo do chefe do almoxarifado). | Ver 7.11. |
| Fluxo com SCPI | Sim, detalhado (importação, divergência, unidades). | Spec 001 cobre a parte de catálogo/saldo inicial e reconciliação de saldo; unidades de medida na spec 001 são preservadas como recebidas, sem tradução de sinônimos — diferente do legado, que prevê um "mapeamento de sinônimos aprovado pelo chefe" (`UND`/`PC` → `un` etc.). | **Conflito direto**: spec 001 FR-019 diz "NÃO DEVE normalizar, unificar ou converter variações" de unidade; o legado `processos-almoxarifado.md` §1.4 propõe exatamente esse mapeamento de sinônimos para material novo. A spec 001, sendo artefato já ratificado, prevalece — a tradução de sinônimos do legado é **DESCARTAR** enquanto FR-019 estiver em vigor, a menos que a spec seja emendada. |

## 9. Resumo consolidado de pendências (para revisão antes de qualquer spec futura)

Três rodadas de decisão com o dono do produto (2026-09-18). Itens 1–4 vêm da primeira rodada; 6–15,
da segunda; 17, da terceira (16 é uma nota de continuidade sobre uma decisão anterior à primeira
rodada, não uma pendência própria). Desta lista de 17 itens, só os itens **5** (máquina de estados
de requisição) e **12** (mecanismo de autenticação/login) continuam genuinamente em aberto — os
demais foram decididos ou adiados deliberadamente, e as decisões já estão canonizadas em
`docs/domain/permissions-matrix.md`.

1. ~~Registrar devolução: exclusividade do chefe ou compartilhada com funcionário do
   almoxarifado?~~ **Resolvido: exclusivo do chefe do almoxarifado.** *(achado 1, 7.8)*
2. ~~Superusuário técnico vs. Administrador de sistema: mesmo papel, papéis sobrepostos ou papéis
   totalmente separados?~~ **Resolvido: totalmente separados — Administrador de sistema fica só
   como o `PRODUCT.md` já define, sem herdar poder de negócio do superusuário legado.**
   *(achado 2, seção 6)*
3. ~~Existe "auxiliar de setor" (fora do almoxarifado) no novo produto?~~ **Resolvido: sim, com a
   definição do legado.** *(seção 4)*
4. ~~Quem pode criar requisição em nome de terceiros, e para quais setores?~~ **Resolvido: fica
   como era no legado (chefe/auxiliar de setor para o próprio setor; Almoxarifado para qualquer
   setor).** *(7.3)*
5. **Em aberto, deliberadamente adiado.** Existe estado de rascunho, atendimento parcial, separação
   para retirada como etapa distinta, e cópia de requisição atendida? Toda a granularidade de
   `estado-transicoes-requisicao.md` segue pendente até uma spec própria de requisições. *(7.4)*
6. ~~Estrutura organizacional: um usuário pertence a um único setor? Todo setor ativo tem exatamente
   um chefe?~~ **Resolvido: sim, exatamente como no legado (USR-03, USR-04, USR-05).** *(seção 5)*
7. ~~Quem executa o ajuste de inventário que corrige divergência de saldo (FR-047)?~~ **Resolvido:
   exclusivo do chefe do almoxarifado.** O mecanismo/telas dessa feature continuam por especificar.
   *(7.6, achado 5)*
8. ~~O que exatamente o papel "Gestor/auditor" precisa ver?~~ **Resolvido: relatórios/consumo
   consolidado de todos os setores + histórico completo de movimentações de estoque.** Histórico de
   importações do SCPI não entrou no escopo deste papel. *(seção 4, 7.11)*
9. ~~Notificações: existem como feature no novo produto?~~ **Resolvido: não, por enquanto —
   descartado para o MVP.** *(7.10)*
10. ~~Motivos fechados de saída excepcional~~: **Resolvido — deterioração, vencimento,
    obsolescência, doação, empréstimo, perda/extravio, quebra/dano (7 motivos).** *(7.7)*
11. ~~Papéis configuráveis em runtime ou fixos no código?~~ **Resolvido: fixos no código, sem
    tela de gestão de papéis.** *(7.2)*
12. **Em aberto, deliberadamente adiado.** Mecanismo de autenticação/login (matrícula, e-mail
    institucional, SSO) — decisão adiada para a feature de autenticação/usuários. *(7.1)*
13. ~~Deve existir observação interna editável no material?~~ **Resolvido: sim, editável por
    qualquer funcionário do almoxarifado.** *(7.5)*
14. ~~Deve existir inativação de material?~~ **Resolvido: sim, exclusiva do chefe do
    almoxarifado.** *(7.5)*
15. ~~Importação SCPI: prévia separada da confirmação, ou um passo só?~~ **Resolvido: duas
    etapas.** A spec 001 já foi emendada (FR-044a) para refletir essa decisão. *(7.9)*
16. Unidades de medida na importação SCPI: a spec 001 (FR-019) proíbe qualquer tradução/normalização
    de unidade; o processo herdado propõe mapear sinônimos para material novo. Esse ponto já tem
    resposta (a spec vigente prevalece) e não deveria reabrir — registrado aqui só para não ser
    reintroduzido inadvertidamente numa feature futura. *(seção 8)*
17. ~~Entradas de estoque: como um material já existente ganha saldo por compra/doação/devolução de
    fornecedor/empréstimo devolvido, já que a reimportação do catálogo nunca soma saldo (FR-028)?~~
    **Resolvido (terceira rodada, 2026-09-18): nova capacidade "Registrar entrada de estoque",
    aberta a qualquer funcionário do almoxarifado, com motivo fechado (compra, doação recebida,
    devolução de fornecedor/garantia, empréstimo devolvido por outro setor/órgão) e referência
    obrigatória.** *(7.6)*

## 10. O que este documento não decide

- Este documento não resolve automaticamente itens ainda classificados como `PENDENTE` (hoje,
  apenas os itens 5 e 12 da seção 9). Decisões explicitamente registradas como resolvidas durante
  a reconciliação constituem resultado histórico deste processo, já canonizado em
  `docs/domain/permissions-matrix.md`.
- Não determina a arquitetura de implementação (se haverá `policies.py`/`services`/`selectors.py`
  próprios ou uso direto dos mecanismos do Django); essa decisão pertence a um futuro `plan.md` e
  deve ser justificada ali conforme a Constitution, Princípio I.
- Não resolve o conflito de acessibilidade (achado 9) — fica registrado para quando a UI da feature
  correspondente for desenhada.
- Não abre spec, tarefa ou feature no Spec Kit.

## 11. Uso recomendado

Para autorização de domínio, use `docs/domain/permissions-matrix.md` — é a fonte canônica. Volte a
este documento apenas para entender o raciocínio por trás de uma decisão, ou para revisar as linhas
ainda `PENDENTE` (hoje, itens 5 e 12 da seção 9). Quando o dono do produto decidir uma feature que
dependa delas, trate cada uma como pergunta obrigatória de `speckit-clarify` antes de avançar para
`plan.md`; a decisão resultante deve ser promovida à matriz canônica, não apenas registrada aqui.
Itens `DESCARTAR` não devem ser reintroduzidos sem nova justificativa por escrito, dado que já há
uma fonte vigente (spec 001) que os contradiz.
