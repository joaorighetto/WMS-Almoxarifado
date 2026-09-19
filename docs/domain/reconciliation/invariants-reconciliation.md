# Reconciliação da Matriz de Invariantes Legada — WMS-Almoxarifado

## Status

```text
Status: CONCLUÍDO — HISTÓRICO / NÃO NORMATIVO
Resultado canônico: docs/domain/invariants-matrix.md
```

Este documento cumpriu seu papel: reconciliar a matriz de invariantes legada e produzir decisões de
domínio. O subconjunto confirmado e independente de feature ainda não especificada já foi
canonizado em `docs/domain/invariants-matrix.md`, que é a fonte normativa de invariantes a partir de
agora. Este arquivo permanece como registro histórico do raciocínio, das alternativas descartadas e
dos itens ainda pendentes — não deve ser lido como fonte de autorização nem de invariante canônica.

> A canonização promoveu apenas o subconjunto confirmado. Itens `PENDENTE` continuam candidatos
> históricos e poderão ser revisitados quando suas features forem especificadas.

Este documento é uma análise de domínio. **Não implementa código, não altera models, migrations,
views, services, forms ou testes, não cria feature no Spec Kit e não altera a Constitution.**

Nenhuma classificação abaixo é definitiva além do que já foi promovido para
`docs/domain/invariants-matrix.md`. Itens `PENDENTE`, `DESCARTAR` e `NÃO É INVARIANTE` continuam
como estavam — são resultado histórico deste processo, não uma nova rodada de decisão.

## Fontes

Lidas nesta ordem, conforme instruído:

1. `CLAUDE.md` — ordem de autoridade das fontes do projeto.
2. `.specify/memory/constitution.md` v1.1.0 — princípios de integridade de estoque (III),
   rastreabilidade e auditoria (IV), regras de negócio no backend (V), segurança por padrão (VI).
3. `PRODUCT.md` — papéis, fluxo de requisição/aprovação/atendimento em alto nível, posicionamento
   frente ao SCPI, princípios de produto.
4. `docs/domain/permissions-matrix.md` — **CANÔNICA**. Usada para não duplicar capabilities e para
   extrair condições de operação que já são normativas.
5. `docs/domain-legacy/reconciliation/permissions-reconciliation.md` — histórico/não normativo, mas
   rico em decisões do dono do produto já tomadas (2026-09-18) que afetam diretamente candidatos a
   invariante (ex.: estrutura organizacional, exclusividade do chefe do almoxarifado, existência da
   capacidade de entrada de estoque).
6. `specs/001-importacao-catalogo-materiais/spec.md` — única feature especificada; fonte primária
   para invariantes de catálogo e importação SCPI.
7. Documentação de domínio legada, tratada em todo este documento como:

   ```text
   LEGACY — NÃO NORMATIVO
   ```

   - `docs/domain-legacy/matriz-invariantes.md` (objeto principal desta reconciliação);
   - `docs/domain-legacy/matriz-permissoes.md` (contexto de papéis/escopo por trás das entradas
     `PER-*`);
   - `docs/domain-legacy/processos-almoxarifado.md` (fluxo de requisição, importação SCPI,
     estornos);
   - `docs/domain-legacy/estado-transicoes-requisicao.md` (máquina de estados detalhada,
     deliberadamente fora de escopo do novo produto por ora);
   - `docs/domain-legacy/processos-saida-excepcional.md` (fluxo de saída excepcional).

Código não foi consultado como fonte primária: não há `models.py` nem qualquer app Django além de
`config/` neste repositório. Documentação herdada nunca foi tratada como correta por já existir —
cada item foi confrontado com as fontes vigentes do novo produto.

## Resumo executivo

- A estrutura organizacional (usuário → um único setor; setor ativo → um único chefe ativo do
  próprio setor; chefe → um único setor) já está confirmada por `PRODUCT.md` e pela reconciliação
  de permissões, e é reaproveitada aqui sem reabrir a decisão (USR-03, USR-04, USR-05).
- A maior parte da matriz legada (`REQ-*`, `ITEM-*`, a maioria de `EST-*`, `LED-06`, `LED-07`,
  parte de `SAE-*`) depende de dois mecanismos que o novo produto **ainda não especificou**: a
  máquina de estados detalhada de requisição e o mecanismo de **reserva de estoque**
  (`saldo_reservado`, `saldo_disponível`). Sem eles, invariantes como "autorização reserva
  integralmente" ou "divergência crítica físico < reservado" não têm onde se apoiar hoje. Todas
  ficam `PENDENTE`, conforme instruído — não foram descartadas, só não podem ser canonizadas ainda.
- A spec 001 (importação de catálogo) sustenta um conjunto de invariantes de catálogo/SCPI que **não
  tinham equivalente na matriz legada** (a matriz legada não modelava importação de catálogo em
  absoluto): opacidade do `CADPRO`, unicidade do `CADPRO`, proibição de criação manual, autoridade
  cadastral do SCPI e não sobrescrita de saldo pela reimportação. Todas entram como candidatas
  `NOVA LACUNA`.
- Um conflito direto e já resolvido foi reencontrado: `processos-almoxarifado.md` §1.4 propõe
  mapear sinônimos de unidade de medida (`UND`/`PC` → `un`) para material novo; a spec 001 (FR-019)
  proíbe qualquer normalização. A spec vigente prevalece; documentado aqui para não ser reaberto.
- Uma tensão foi identificada — e uma correção equivocada dela foi **revertida por review
  (2026-09-18)**: `docs/domain/permissions-matrix.md` usa o termo "saldo reservado" na condição de
  `PERM-MATERIAL-DEACTIVATE` ("Exige saldo físico e saldo reservado zerados"), mas nenhuma fonte
  vigente do novo produto define "saldo reservado" como propriedade transversal de domínio — o
  mecanismo de reserva é uma das duas pendências deliberadas da reconciliação de permissões. Uma
  revisão anterior havia enfraquecido essa condição para "Exige saldo físico zerado", tratando a
  ausência de definição formal como se revogasse a decisão de produto já confirmada; isso foi
  identificado como incorreto e revertido — a condição permanece exigindo saldo reservado zerado,
  com nota de reavaliação quando o mecanismo de reserva for especificado. Ver seção "Conflitos".
- Boa parte da matriz legada de permissões (`PER-*`) não é invariante — é autorização, já coberta
  (ou superada) por `docs/domain/permissions-matrix.md`. Isso inclui a rejeição explícita do
  `superuser` como papel de override total (seção 6 da reconciliação de permissões), que também
  invalida `PER-05` como invariante candidata.

## Reconciliação detalhada

Convenção de ID candidato: famílias `INV-ORG`, `INV-AUTH`, `INV-CATALOG`, `INV-STOCK`, `INV-MOV`,
`INV-SCPI`, `INV-SAE`, `INV-RETURN`. Nenhum ID abaixo é estável — são candidatos para revisão.

### Organização e autenticação

| Legado | Candidato INV | Regra reconciliada | Domínio | Classificação | Severidade | Evidência | Verificação futura |
|---|---|---|---|---|---|---|---|
| USR-03 | INV-ORG-001 | Todo usuário pertence a um único setor. | Organização | **MANTER** | CRÍTICA | `PRODUCT.md` Operating Context ("Cada funcionário do SAEP pertence a um único setor"); reconciliação de permissões §5, "RESOLVIDO... USR-03... MANTIDAS". | domínio; banco/constraint |
| USR-04 + USR-07 | INV-ORG-002 | Todo setor ativo possui exatamente um chefe ativo, que pertence a esse mesmo setor. Nenhuma operação sobre usuário ou setor (ex.: desativação do usuário que chefia, remanejamento de setor) pode deixar um setor ativo sem chefe ativo — a operação deve ser bloqueada, ou exigir designação prévia de outro chefe ativo do próprio setor. | Organização | **REFORMULAR** | CRÍTICA | `PRODUCT.md`: "Todo setor ativo tem exatamente um chefe ativo, que pertence a esse mesmo setor... Essas invariantes são a base de todo escopo 'próprio setor'... sem elas, esse escopo fica indefinido"; reconciliação de permissões §5. | domínio; banco/constraint |
| USR-05 | INV-ORG-003 | Um chefe responde por um único setor. | Organização | **MANTER** | CRÍTICA | Mesma evidência de USR-03/04, `PRODUCT.md` e reconciliação §5. | domínio; banco/constraint |
| USR-01 | INV-AUTH-001 | Usuário inativo não acessa nem executa nenhuma operação no sistema, qualquer que seja o mecanismo de autenticação eventualmente escolhido. | Autenticação | **MANTER** | CRÍTICA | Constitution, Princípio VI ("segurança por padrão"); reconciliação de permissões §7.1 (`PERM-AUTH-ACTIVE-REQUIRED`, MANTER, mecanismo de login adiado mas pré-condição de usuário ativo confirmada). | autorização |
| USR-02 | — | Todo usuário ativo é, no mínimo, Requisitante. | — | **NÃO É INVARIANTE** | — | Já é regra de composição de papéis, canonizada em `docs/domain/permissions-matrix.md` §2 ("Notas de composição"): "Todo usuário ativo do WMS ocupa, no mínimo, `ROLE-REQUESTER`". | — |
| USR-06 | — | Setor inativo permanece em histórico e não recebe nova requisição; setor não é desativado com requisição em voo aguardando autorização. | Organização/Requisição | **PENDENTE** | — | Depende de dois conceitos ainda não confirmados no novo produto: "setor inativo" (nenhuma fonte vigente trata desativação de setor) e a máquina de estados de requisição, deliberadamente adiada. | — |

### Permissões legadas (`PER-*`) — checagem de falso invariante

| Legado | Candidato INV | Regra reconciliada | Domínio | Classificação | Severidade | Evidência | Verificação futura |
|---|---|---|---|---|---|---|---|
| PER-01 | — | Solicitante cria requisição apenas para si. | — | **NÃO É INVARIANTE** | — | Já é `PERM-REQ-CREATE-SELF` em `docs/domain/permissions-matrix.md`. | — |
| PER-02 | — | Auxiliar de setor cria para si e para usuários do próprio setor. | — | **NÃO É INVARIANTE** | — | Já é `PERM-REQ-CREATE-FOR-OTHER` (escopo "próprio setor"). | — |
| PER-03 | — | Chefe autoriza só beneficiários do próprio setor. | — | **NÃO É INVARIANTE** | — | Já é `PERM-REQ-AUTHORIZE` (escopo "próprio setor"). | — |
| PER-04 | — | Almoxarifado cria em nome de qualquer usuário de qualquer setor. | — | **NÃO É INVARIANTE** | — | Já é `PERM-REQ-CREATE-FOR-OTHER` (escopo "qualquer setor" para `ROLE-WAREHOUSE-STAFF`). | — |
| PER-05 | — | Superusuário tem permissões totais, incluindo administração, consulta ampla e operações de negócio/estoque. | — | **DESCARTAR** | — | A reconciliação de permissões §6 rejeitou explicitamente esse papel: "não existe papel de produto que herde o poder de negócio total... nenhum papel de produto acumula autorização total sobre operações de estoque/requisição só por ser administrativo". Não sobra nenhuma propriedade de domínio a preservar aqui. | — |
| PER-06 | INV-REQ-001 (candidato futuro) | Uma requisição pertence ao setor do beneficiário, nunca ao setor do criador; isso define a fila de autorização. | Requisição | **PENDENTE** | — | Conceitualmente já confirmado como núcleo em `permissions-reconciliation.md` §4 ("Setor do beneficiário... MANTER"), mas a requisição em si — como entidade e máquina de estados — ainda não tem spec. Não canonizar antes da spec de requisições, por instrução explícita da seção 12. | domínio |
| PER-08 | — | Views e services chamam a mesma policy contextual. | — | **DESCARTAR** | — | Prescreve uma camada de implementação (`policies.py` compartilhado) e não uma propriedade de domínio; a reconciliação de permissões já tratou isso no "Esclarecimento — camadas de implementação e Constitution Princípio I": a camada não é adotada automaticamente e exigiria justificativa própria no `plan.md` da feature que a introduzir. | — |

### Requisição e itens (`REQ-*`, `ITEM-*`) — bloco integralmente dependente da máquina de estados adiada

Nenhum destes é descartado: a hierarquia de papéis por trás de cada um é plausível e coerente com o
que já está confirmado, mas o estado/mecânica em si (rascunho, envio, retorno, atendimento parcial,
separação para retirada, cópia) foi deliberadamente adiado pelo dono do produto em 2026-09-18 para
uma spec própria de requisições (`permissions-reconciliation.md`, item 5 da seção 9). Promover
qualquer um agora violaria a instrução da seção 12 desta tarefa.

| Legado | Regra original (resumo) | Domínio | Classificação | Severidade se confirmado | Evidência | Verificação futura |
|---|---|---|---|---|---|---|
| REQ-01 | Toda requisição começa em rascunho. | Requisição | **PENDENTE** | NORMAL | Máquina de estados adiada. | domínio |
| REQ-02 | Rascunho nunca enviado não tem número público. | Requisição | **PENDENTE** | NORMAL | Idem. | domínio |
| REQ-03 | Número público nasce no primeiro envio, padrão `REQ-AAAA-NNNNNN`. | Requisição | **PENDENTE** | NORMAL | Idem; formato específico é detalhe a decidir na spec. | domínio |
| REQ-04 | Reenvios preservam número público. | Requisição | **PENDENTE** | NORMAL | Idem. | domínio |
| REQ-05 | Requisição precisa de ao menos um item. | Requisição | **PENDENTE** | ALTA | Idem. | domínio |
| REQ-06 | Após envio, não há edição direta de itens. | Requisição | **PENDENTE** | ALTA | Idem. | domínio |
| REQ-07 | Registrar criador, beneficiário e setor do beneficiário. | Requisição/Rastreabilidade | **PENDENTE** | ALTA | Conceito de escopo já confirmado (ver PER-06); a obrigatoriedade de registro fica pendente até a spec existir formalmente. | domínio |
| REQ-08 | Timeline registra eventos e é visível a autorizados. | Requisição/Auditoria | **PENDENTE** | ALTA | Máquina de estados adiada; princípio de rastreabilidade já existe na Constitution IV, mas o mecanismo "timeline" é específico da feature. | domínio; autorização |
| REQ-09 | Cópia recalcula saldo e não copia autorizado/entregue. | Requisição | **PENDENTE** | NORMAL | Feature de conveniência não confirmada em nenhuma fonte do novo produto. | domínio |
| ITEM-01 | Autorização é sempre integral (nunca parcial). | Requisição | **PENDENTE** | ALTA | `permissions-reconciliation.md` §7.4 mantém isso como "núcleo confirmado hoje ipsis litteris" a nível de permissão (`PERM-REQ-AUTHORIZE`), mas a mecânica de item/quantidade em si depende da spec de requisições. | domínio |
| ITEM-02 | Entregue nunca maior que autorizado. | Requisição | **PENDENTE** | CRÍTICA (se confirmado) | Máquina de estados adiada. | domínio; banco/constraint |
| ITEM-03 | Atendimento parcial exige justificativa. | Requisição | **PENDENTE** | NORMAL | Idem. | domínio |
| ITEM-04 | Item autorizado com zero não é permitido. | Requisição | **PENDENTE** | NORMAL | Idem. | domínio |
| ITEM-05 | Entrega zero exige justificativa. | Requisição | **PENDENTE** | NORMAL | Idem. | domínio |
| ITEM-06 | Requisição atendida precisa de ao menos um item entregue > 0. | Requisição | **PENDENTE** | NORMAL | Idem. | domínio |

### Estoque (`EST-*`)

| Legado | Candidato INV | Regra reconciliada | Domínio | Classificação | Severidade | Evidência | Verificação futura |
|---|---|---|---|---|---|---|---|
| EST-01 | — | Físico e reservado são armazenados; disponível = físico − reservado. | Estoque | **PENDENTE** | CRÍTICA (se confirmado) | Nenhuma fonte vigente do novo WMS confirma a existência de "saldo reservado" ou "saldo disponível" como conceitos distintos do saldo único hoje usado pela spec 001. Depende do mecanismo de reserva por requisição, ainda não especificado. | domínio |
| EST-02 | — | Autorização reserva integralmente o solicitado, sem baixar físico. | Estoque/Requisição | **PENDENTE** | ALTA | Idem — depende de reserva e de autorização de requisição. | domínio; transacional |
| EST-03 | — | Atendimento consome reserva e baixa físico. | Estoque/Requisição | **PENDENTE** | CRÍTICA (se confirmado) | Idem. | transacional |
| EST-04 | — | Reserva não entregue deve ser liberada. | Estoque/Requisição | **PENDENTE** | ALTA | Idem. | domínio; transacional |
| EST-05 | — | Não pode reservar acima do disponível. | Estoque/Requisição | **PENDENTE** | CRÍTICA (se confirmado) | Idem. | concorrência; banco/constraint |
| EST-06 | — | Operações críticas usam transação e lock (`atomic()`, `select_for_update()`). | — | **NÃO É INVARIANTE** | — | É técnica de implementação, explicitamente excluída pela definição de invariante desta tarefa. A garantia de resultado que essa técnica protege já está coberta por `INV-STOCK-004` (atomicidade, abaixo) e pela Constitution, Princípio III, que já exige exatamente isso; a técnica em si pertence ao `plan.md` da feature que mexer em estoque. | — |
| EST-07 | (mantido explicitamente fora, por instrução) | Divergência crítica: físico < reservado. | Estoque/Requisição | **PENDENTE** | — | Depende inteiramente do mecanismo de reserva de estoque por requisição autorizada, ainda não especificado. **Distinto da "divergência de saldo" da spec 001** (arquivo SCPI × saldo do WMS, ver INV-STOCK-003) — os dois conceitos não devem ser fundidos, conforme já apontado em `permissions-reconciliation.md` §2. Não promovida agora, por instrução explícita desta tarefa (seção 11). | domínio |
| EST-08 | — | Material divergente (crítico) bloqueia novas requisições, autorizações e separação. | Estoque/Requisição | **PENDENTE** | — | Depende de EST-07, que é pendente. | domínio |
| EST-09 | — | Divergência crítica resolve quando físico ≥ reservado. | Estoque/Requisição | **PENDENTE** | — | Depende de EST-07. | domínio |
| EST-10 | — | Material inativo não entra em nova requisição. | Catálogo/Requisição | **PENDENTE** | ALTA (se confirmado) | A metade "requisição" depende da máquina de estados adiada. A metade "material inativo não é elegível para nova operação" é plausível e mais geral que só requisição, mas nenhuma fonte vigente confirma o comportamento fora da precondição de inativação (ver EST-11/INV-CATALOG-007) — mantido pendente para não presumir política ainda não decidida (ex.: material inativo pode ainda receber entrada de estoque de devolução?). | domínio |
| EST-11 | ~~INV-CATALOG-007~~ (não promovido) | Material só pode ser inativado com saldo físico zerado e saldo reservado zerado. | Catálogo | **NÃO PROMOVIDO NESTA CANONIZAÇÃO** — dividido em duas partes | — | Ver nota abaixo. | — |

**Nota sobre EST-11 (revisão pós-canonização, 2026-09-18; corrigida em revisão de PR no mesmo dia):**
esta linha foi classificada `MANTER` na primeira reconciliação, apoiada na condição de
`PERM-MATERIAL-DEACTIVATE` então vigente em `docs/domain/permissions-matrix.md` ("Exige saldo
físico e reservado zerados"). Ao criar a matriz canônica de invariantes, uma primeira revisão havia
enfraquecido essa condição para "Exige saldo físico zerado", por essa condição citar um conceito
(`saldo_reservado`) que o novo produto ainda não define formalmente como invariante de domínio — o
mecanismo de reserva de estoque é uma pendência deliberada (ver Pendências, item 1).

**Essa correção foi revertida por review**: a ausência de uma definição *formal, transversal* de
"saldo reservado" na matriz de invariantes não revoga uma decisão de produto já confirmada e
registrada em `docs/domain-legacy/reconciliation/permissions-reconciliation.md` — a exigência de
reserva zerada para inativar material. Enfraquecer a condição sem nova validação explícita do dono
do produto seria alterar comportamento por inferência editorial, não por decisão de domínio. A
condição canônica de `PERM-MATERIAL-DEACTIVATE` foi restaurada para **"Exige saldo físico e saldo
reservado zerados"**, com nota de que o mecanismo técnico de reserva ainda não está especificado e
que "reservado inexistente" se comporta, na prática, como "reservado zero" até lá. Como resultado:

- A condição de autorização (`PERM-MATERIAL-DEACTIVATE`) já está restaurada em
  `docs/domain/permissions-matrix.md` e reflete a decisão de produto integralmente — inclusive a
  metade sobre saldo reservado.
- Isso não promove `INV-CATALOG-007` à matriz canônica de invariantes: uma condição de autorização já
  decidida (regra 8/9 da matriz canônica: `permissions-matrix.md` responde quem/sob quais condições)
  é diferente de uma invariante transversal, que exigiria "saldo reservado" ser um conceito de
  domínio definido e verificável por si só — isso continua **PENDENTE** (ver Pendências, item 1).
  Não há contradição entre os dois documentos: a permissão pode decidir hoje uma condição que cita
  um conceito ainda não modelado formalmente, registrando explicitamente que será reavaliada quando
  esse conceito existir; a matriz de invariantes apenas não promove esse conceito como propriedade
  transversal própria antes disso.
- **Preservação histórica**: o legado (`matriz-invariantes.md`, EST-11) também exigia saldo
  reservado zerado para inativar material — essa exigência nunca foi considerada incorreta; a
  correção equivocada de uma revisão anterior deste relatório foi revertida.

### Ledger de movimentações (`LED-*`)

| Legado | Candidato INV | Regra reconciliada | Domínio | Classificação | Severidade | Evidência | Verificação futura |
|---|---|---|---|---|---|---|---|
| LED-01 | INV-MOV-002 | Toda alteração de saldo decorrente de uma operação própria do WMS (diferente da carga/atualização cadastral da importação SCPI) deve ter um registro de movimentação correspondente, na mesma operação, identificando a operação de origem, o ator, a quantidade e o momento. | Movimentação | **REFORMULAR** | CRÍTICA | Constitution, Princípio IV (rastreabilidade); consistente com a saída de escopo do bootstrap SCPI já prevista no próprio legado e com FR-016 (saldo inicial da importação tem "origem identificável"). Reformulado para remover nomes de model/service (`SaldoEstoque`, `MovimentacaoEstoque`, `_registrar_movimentacao`) e a referência a um ADR que não existe neste repositório. | domínio; transacional |
| LED-02 | (absorvido por INV-MOV-002) | Soma de deltas por material reconcilia com o saldo armazenado. | Movimentação | **REFORMULAR** | ALTA | Consequência de verificação de LED-01/INV-MOV-002; mantido como propriedade verificável, não como o esquema específico "dois deltas assinados por linha", que é decisão de schema ainda não tomada. | domínio |
| LED-03 | — | Movimentação tem exatamente uma origem (`requisicao` XOR `saida_excepcional`). | Movimentação | **PENDENTE** | — | A premissa de que só existem duas origens já está desatualizada: a reconciliação de permissões já confirmou uma terceira origem nova (`PERM-STOCK-ENTRY-CREATE`, entrada de estoque) e antecipa outras (ajuste de inventário, devolução, estorno). O conjunto completo de origens de movimentação não está definido para o novo WMS; não decidir a forma da regra antes de existir. | domínio; banco/constraint |
| LED-04 | — | Movimentação não pode ter ambos os deltas (físico e reservado) zero. | Movimentação | **PENDENTE** | — | Presume um schema de "dois deltas assinados por linha" que não foi adotado nem descartado para o novo produto. Fica para quando o ledger for desenhado. | banco/constraint |
| LED-05 | INV-MOV-001 | Um registro de movimentação de estoque, uma vez criado, não é alterado nem removido; qualquer correção ocorre por novo registro compensatório (estorno), preservando o original. | Movimentação | **REFORMULAR** | CRÍTICA | Constitution, Princípio IV: "Exclusão física de registros NÃO DEVE ser usada quando prejudicar rastreabilidade... DEVE ser adotada inativação, cancelamento ou estorno, preservando o registro original". Reformulado para remover a referência a `save`/`delete` override, que é técnica. | domínio; banco/constraint |

**Nota sobre o escopo de `INV-MOV-001` (revisão pós-canonização, 2026-09-18):** a primeira redação
canonizada declarava imutabilidade de "um registro de movimentação de estoque" sem qualificação,
o que poderia ser lido como imutabilidade absoluta de todo e qualquer campo de um schema de ledger
que ainda não foi desenhado — antecipando uma decisão de modelagem antes da hora, na mesma linha do
que já havia sido evitado para `LED-03`/`LED-04`. A redação canônica foi restringida para cobrir
apenas os fatos historicamente relevantes para saldo, origem da operação e auditoria (quantidade,
efeito no saldo, operação de origem, ator, momento) — exatamente o que a Constitution, Princípio IV,
exige preservar. Qualquer campo adicional de um futuro registro de movimentação que não seja um
desses fatos (ex.: metadado não relevante para saldo/auditoria) não está coberto por esta invariante
e sua imutabilidade, se fizer sentido, é decisão da futura feature de movimentações — não foi
descartada, apenas não antecipada.
| LED-06 | — | Entregue líquida de um item é calculada a partir do histórico de movimentações (consumo, devolução, estorno), sem armazenamento próprio. | Requisição/Devolução | **PENDENTE** | — | Depende da spec de devolução/estorno de requisição, que ainda não existe, embora as capabilities (`PERM-RETURN-CREATE`, `PERM-REQ-REVERSE`) já sejam canônicas. A fórmula de cálculo é mecânica de implementação sujeita à spec futura. | domínio |
| LED-07 | — | Devolvida líquida de um item limita a quantidade estornável de uma devolução. | Devolução | **PENDENTE** | — | Mesma dependência de LED-06. | domínio |

### Saída excepcional (`SAE-*`)

| Legado | Candidato INV | Regra reconciliada | Domínio | Classificação | Severidade | Evidência | Verificação futura |
|---|---|---|---|---|---|---|---|
| SAE-01 | INV-SAE-002 | Uma saída excepcional é um documento de baixa de estoque independente de qualquer requisição; não nasce de, nem depende do estado de, uma requisição. | Saída excepcional | **REFORMULAR** | ALTA | `PRODUCT.md`: estorno, devolução e saída excepcional são "operações exclusivas do chefe do almoxarifado" distintas do fluxo de requisição. Reformulado para remover referência a app/URLs/policies específicos (`/estoque/saidas-excepcionais/`), que é roteamento, não invariante. | domínio |
| SAE-02 | — | Documento de saída excepcional tem número público anual próprio (`SXP-AAAA-NNNNNN`), gerado no registro e imutável. | Saída excepcional | **PENDENTE** | — | A feature de saída excepcional em si não tem spec no novo produto; só sua exclusividade de ator está confirmada em `PRODUCT.md`. Formato de identificador é decisão a tomar na spec futura. | domínio |
| SAE-03 | — | Documento exige ao menos 1 item; mesmo material não aparece duas vezes no mesmo documento. | Saída excepcional | **PENDENTE** | — | Mesma dependência de SAE-02. | domínio |
| SAE-04 | (converge com INV-STOCK-004) | Registro de saída excepcional é indivisível: se 1 item falha, nada é persistido. | Saída excepcional | **PENDENTE** (como item de SAE especificamente) | — | O princípio geral de atomicidade já está capturado de forma transversal em `INV-STOCK-004`, apoiado diretamente pela Constitution III; a aplicação específica a este documento fica pendente até a feature existir, mas não é um risco novo — é instância do princípio já canônico. | transacional |
| SAE-05 | — | Registro baixa `saldo_fisico` e não altera `saldo_reservado`. | Saída excepcional/Estoque | **PENDENTE** | — | Depende do conceito de "saldo reservado", ainda não confirmado (ver EST-01, Conflitos). | domínio |
| SAE-06 | — | Saldo aplicável é único; ausência ou ambiguidade de saldo bloqueia o documento. | Estoque | **DESCARTAR** | — | Presume múltiplos estoques possíveis para o mesmo material (necessidade de desambiguação). `PRODUCT.md`, Operating Context: "Atende um único almoxarifado físico do SAEP; não há necessidade confirmada de segmentar estoque por múltiplos locais." Sem múltiplos estoques, o cenário de ambiguidade que esta regra trata não existe no novo produto. | — |
| SAE-07 | INV-SAE-001 | Estorno de saída excepcional é sempre total; nunca parcial. | Saída excepcional | **MANTER** | CRÍTICA | Já está na `docs/domain/permissions-matrix.md` **canônica**, condição de `PERM-SAE-REVERSE`: "Estorno é total; justificativa obrigatória." Convergência direta entre legado e fonte canônica atual. | domínio; transacional |
| SAE-08 | — | Consulta de saída excepcional é mais ampla que o poder de registrar/estornar. | — | **NÃO É INVARIANTE** | — | Já expresso em `docs/domain/permissions-matrix.md`: `PERM-SAE-VIEW` (funcionário do almoxarifado) é mais amplo que `PERM-SAE-CREATE`/`PERM-SAE-REVERSE` (exclusivos do chefe). | — |
| SAE-09 | — | Motivos de saída excepcional são de lista fechada; observação é obrigatória. | — | **NÃO É INVARIANTE** | — | Já é condição de `PERM-SAE-CREATE` em `docs/domain/permissions-matrix.md`; a lista de motivos em si já foi resolvida em `permissions-reconciliation.md` (7 motivos, seção "Motivos de saída excepcional"). | — |

### Devolução e estorno de requisição

Não havia IDs `RET-*`/`REV-*` na matriz legada — o tema aparecia disperso em `estado-transicoes-requisicao.md` (TR-020, TR-021, TR-023) e em `LED-06`/`LED-07`. Tratado aqui de forma consolidada.

| Legado | Candidato INV | Regra reconciliada | Domínio | Classificação | Severidade | Evidência | Verificação futura |
|---|---|---|---|---|---|---|---|
| TR-020/021/023 (legado, fora de `matriz-invariantes.md`) | ~~INV-RETURN-001~~ → absorvido por `INV-MOV-001` | Estorno de uma operação de estoque (devolução, requisição, saída excepcional) preserva o registro original e produz um novo registro compensatório; nunca sobrescreve nem apaga o fato original. | Movimentação/Estorno | **MANTER** (deduplicado) | CRÍTICA | Constitution, Princípio IV, aplicado literalmente a estorno; convergência com `PERM-SAE-REVERSE`, `PERM-REQ-REVERSE`, `PERM-RETURN-REVERSE`, todas já canônicas em `docs/domain/permissions-matrix.md`, todas com "justificativa obrigatória" e sem menção a edição do fato original. | domínio; transacional |

**Nota de deduplicação (canonização, 2026-09-18):** esta regra não recebeu ID próprio na matriz
canônica. "Preservar o original", "não sobrescrever fatos" e "registrar compensação" são a mesma
propriedade transversal de imutabilidade do ledger já expressa por `INV-MOV-001`
(`docs/domain/invariants-matrix.md`), qualquer que seja a operação estornada. Criar um
`INV-RETURN-001` separado duplicaria a mesma propriedade sob dois IDs sem diferença semântica
material. Uma família `INV-RETURN-*` própria pode voltar a fazer sentido quando a feature de
devolução/estorno de requisição for especificada e revelar regras que não sejam apenas instâncias
de `INV-MOV-001` (ex.: limites de quantidade estornável — ver `LED-06`/`LED-07`, pendentes).

### Notificações (`NOT-*`)

| Legado | Regra original | Domínio | Classificação | Evidência |
|---|---|---|---|---|
| NOT-01 | Regras de destinatário de notificação de autorização pendente. | Notificações | **DESCARTAR** | `permissions-reconciliation.md` §7.10: "sem notificações no MVP", decisão explícita do dono do produto em 2026-09-18. Toda a família de notificações do legado descartada junto. |

### Novas lacunas — candidatas sem equivalente na matriz legada

A matriz legada não modelava importação de catálogo em absoluto (o WMS-SAEP legado presumia
cadastro já existente, sem processo de carga). A spec 001 introduz um domínio de catálogo inteiro
que precisa de invariantes próprias.

| Candidato INV | Regra reconciliada | Domínio | Classificação | Severidade | Evidência | Verificação futura |
|---|---|---|---|---|---|---|
| INV-CATALOG-001 | O `CADPRO` nunca é gerado, alterado, reformatado, completado, convertido para número, decomposto ou inferido pelo WMS, em nenhuma etapa; é tratado sempre como identificador textual opaco. | Catálogo | **NOVA LACUNA** | CRÍTICA | Spec 001, FR-001/FR-002; `PRODUCT.md`, Positioning ("identificado pelo código `CADPRO`... tratado sempre como texto opaco, nunca gerado, alterado, reformatado ou decomposto pelo WMS"). | domínio; integração |
| INV-CATALOG-002 | Não podem existir dois materiais com o mesmo `CADPRO` no catálogo do WMS. | Catálogo | **NOVA LACUNA** | CRÍTICA | Spec 001, FR-003 ("identificador único"), FR-005 (recusa de duplicidade no arquivo). | domínio; banco/constraint |
| INV-CATALOG-003 | Um material só pode entrar no catálogo pela importação do SCPI; nenhum papel possui meio de criação manual. | Catálogo | **NOVA LACUNA** | CRÍTICA | Spec 001, FR-006 ("NÃO DEVE oferecer nenhum meio de criar material manualmente"); `PRODUCT.md`, Capabilities and Constraints. Convergência com o legado, que também nunca concedia essa permissão a ninguém — mas o legado nunca formulou isso como invariante de domínio, só como ausência de permissão. | domínio; integração |
| INV-CATALOG-004 | Os dados cadastrais de um material (descrição, unidade, detalhamento técnico, classificação) são autoridade do SCPI e só mudam por nova importação; a única exceção é a observação interna, campo próprio do WMS, que nunca deriva do SCPI nem é enviado a ele. | Catálogo | **NOVA LACUNA** | ALTA | Spec 001, FR-002/FR-017/FR-022/FR-026; `docs/domain/permissions-matrix.md`, `PERM-MATERIAL-EDIT-NOTE` ("Campo próprio do WMS; não deriva nem é enviado ao SCPI"). | integração; domínio |
| INV-CATALOG-005 | A unidade de medida de um material é preservada exatamente como recebida do SCPI; o WMS nunca normaliza, unifica ou converte variações. | Catálogo | **NOVA LACUNA** | ALTA | Spec 001, FR-019/FR-020. **Conflito direto e já resolvido** com `processos-almoxarifado.md` §1.4, que propunha um mapeamento de sinônimos (`UND`/`PC` → `un`) para material novo — ver seção Conflitos. | integração |
| INV-CATALOG-006 | A inativação de um material preserva o registro e todo o histórico associado a ele; não é exclusão física. | Catálogo | **NOVA LACUNA** | ALTA | Constitution, Princípio IV (preferência por inativação sobre exclusão); `permissions-reconciliation.md` §7.5, nota de que inativação "é reversível e não é" criação/edição/exclusão manual. | domínio |
| INV-STOCK-001 | O saldo físico de um material nunca é negativo. | Estoque | **NOVA LACUNA** | CRÍTICA | Constitution, Princípio III, cita literalmente "verificação de não-negatividade" como exemplo de invariante que deve virar constraint de banco quando expressável assim. | banco/constraint; concorrência |
| INV-STOCK-002 | O saldo de um material nasce da importação inicial do SCPI e, a partir daí, só muda por operação própria do WMS; reimportar o catálogo nunca sobrescreve saldo de material já existente. | Estoque/Catálogo | **NOVA LACUNA** (sourced de prosa legada, sem ID) | CRÍTICA | Spec 001, FR-016/FR-028; `PRODUCT.md`, Capabilities and Constraints ("Saldo de um material nasce da importação inicial... reimportar o catálogo nunca sobrescreve saldo existente"). A prosa de `processos-almoxarifado.md` §1.4 já dizia algo equivalente ("A importação SCPI nunca sobrescreve saldo"), mas sem ID formal na matriz compacta — daí tratada como lacuna da matriz legada, não como item a reconciliar. | integração; domínio |
| INV-STOCK-003 | A divergência entre a quantidade do arquivo SCPI e o saldo do WMS é puramente informativa: nunca corrige o saldo automaticamente e nunca bloqueia, por si só, nenhuma operação. **Distinta de qualquer divergência entre saldo físico e saldo reservado** (ver EST-07, pendente). | Estoque/Catálogo | **NOVA LACUNA** | ALTA | Spec 001, FR-029/FR-030; esclarecimento dedicado em `permissions-reconciliation.md` §2. | integração |
| INV-STOCK-004 | Uma operação de estoque que envolva mais de uma alteração dependente (saldo, item, registro de movimentação) não pode concluir parcialmente; falha em qualquer parte desfaz a operação inteira. | Estoque | **NOVA LACUNA** | CRÍTICA | Constitution, Princípio III: "executar atomicamente quando envolver mais de uma alteração dependente... impedir a criação de estados inválidos". Spec 001, FR-038, é uma instância já confirmada (importação é atômica). | transacional; concorrência |
| INV-SCPI-001 | O WMS nunca realiza integração automática com o SCPI, em nenhuma direção; todo lançamento no sistema oficial permanece manual e posterior. | SCPI | **NOVA LACUNA** | ALTA | Spec 001, FR-046; `PRODUCT.md`, Positioning ("não integra com ele automaticamente em nenhuma direção") e Operating Context (lançamento manual posterior por qualquer funcionário do almoxarifado). | integração |

## Falsos invariantes

Itens classificados como `NÃO É INVARIANTE` e seu destino correto:

| Item | Destino |
|---|---|
| USR-02 (todo usuário ativo é solicitante) | `docs/domain/permissions-matrix.md` — já coberto em "Notas de composição". |
| PER-01 (solicitante cria para si) | `docs/domain/permissions-matrix.md` — `PERM-REQ-CREATE-SELF`. |
| PER-02 (auxiliar cria para o setor) | `docs/domain/permissions-matrix.md` — `PERM-REQ-CREATE-FOR-OTHER`. |
| PER-03 (chefe autoriza o próprio setor) | `docs/domain/permissions-matrix.md` — `PERM-REQ-AUTHORIZE`. |
| PER-04 (Almoxarifado cria para qualquer setor) | `docs/domain/permissions-matrix.md` — `PERM-REQ-CREATE-FOR-OTHER`. |
| PER-08 (views/services chamam a mesma policy) | `plan.md` da feature que introduzir a camada, se justificada por escrito (Constitution, Princípio I); não é regra de domínio. |
| EST-06 (transação e lock em operações críticas) | Já garantido pela Constitution, Princípio III; a técnica específica é decisão de `plan.md` quando a feature de estoque for implementada. |
| SAE-08 (consulta mais ampla que mutação) | `docs/domain/permissions-matrix.md` — `PERM-SAE-VIEW` vs. `PERM-SAE-CREATE`/`PERM-SAE-REVERSE`. |
| SAE-09 (motivo fechado + observação obrigatória) | `docs/domain/permissions-matrix.md` — condição de `PERM-SAE-CREATE`. |

## Pendências

Estas perguntas exigem decisão humana de produto antes da canonização **das invariantes que delas
dependem** — elas não bloqueiam a canonização do subconjunto independente já confirmado, que está
em `docs/domain/invariants-matrix.md`. Ordenadas pelo número de itens que cada uma bloqueia:

1. **Existe reserva de estoque (`saldo_reservado`) no novo WMS, e se sim, com que mecânica?** Esta
   é a pendência com maior efeito cascata: bloqueia EST-01 a EST-05, EST-07 a EST-09, EST-10 (em
   parte), EST-11 (a metade "reservado zerado"), SAE-05, e é a origem de uma tensão terminológica já
   presente na `permissions-matrix.md` canônica (ver Conflitos). Já é uma das duas pendências
   deliberadamente adiadas por `permissions-reconciliation.md` (item 5/12 da seção 9).
2. **A máquina de estados detalhada de requisição será a do legado, uma variante, ou inteiramente
   nova?** Bloqueia REQ-01 a REQ-09, ITEM-01 a ITEM-06, LED-06, LED-07, PER-06/INV-REQ-001. Segunda
   pendência deliberadamente adiada por `permissions-reconciliation.md`.
3. **Saída excepcional será especificada com a mesma forma do legado (documento próprio, número
   anual `SXP-AAAA-NNNNNN`, motivos fechados) ou revisitada do zero?** A exclusividade de ator
   (chefe do almoxarifado) já está confirmada em `PRODUCT.md`; a mecânica do documento em si não
   tem spec. Bloqueia SAE-02, SAE-03, SAE-04 (como item específico), SAE-05.
4. **Material inativo pode continuar recebendo operações que não sejam "nova requisição" — por
   exemplo, uma entrada de estoque por devolução de empréstimo?** Afeta a formulação final de
   EST-10.
5. **Qual é o conjunto completo de origens possíveis de uma movimentação de estoque no novo WMS?**
   Hoje já se sabe que há pelo menos: carga inicial da importação SCPI (fora do ledger, por
   registro de origem próprio), entrada de estoque (nova, confirmada), e — quando especificados —
   ajuste de inventário, saída excepcional, devolução e estorno. Bloqueia LED-03, LED-04.
6. **Setor pode ser desativado? Sob que condição?** Bloqueia USR-06.

## Novas lacunas

Já listadas em detalhe na tabela "Novas lacunas — candidatas sem equivalente na matriz legada",
acima: `INV-CATALOG-001` a `INV-CATALOG-006`, `INV-STOCK-001`, `INV-STOCK-002`, `INV-STOCK-003`,
`INV-STOCK-004`, `INV-SCPI-001`. Todas sustentadas por fonte vigente (spec 001, `PRODUCT.md` ou
Constitution), não por boa prática genérica.

## Conflitos

1. **Unidade de medida — mapeamento de sinônimos (legado) × preservação literal (spec 001).**
   `processos-almoxarifado.md` §1.4 propõe traduzir sinônimos de unidade (`UND`/`PC` → `un`,
   `MT`/`MTS` → `m`, `LT` → `l`) para material novo, com criação de unidade e precisão inferidas.
   A spec 001 (FR-019, FR-020) proíbe qualquer normalização, unificação ou conversão de unidade,
   em qualquer material. **Já resolvido** em `permissions-reconciliation.md` §8: a spec 001
   prevalece por ser artefato ratificado mais recente; o mapeamento de sinônimos do legado é
   `DESCARTAR`. Registrado aqui apenas para reforçar `INV-CATALOG-005` e evitar reabertura
   inadvertida numa feature futura de importação.
2. **"Saldo reservado" citado como condição canônica sem definição transversal vigente — tensão
   documentada, não um erro, e não resolvida enfraquecendo a decisão de produto.**
   `docs/domain/permissions-matrix.md` usa a condição "Exige saldo físico e saldo reservado
   zerados" para `PERM-MATERIAL-DEACTIVATE`. Nenhuma fonte vigente do novo produto define "saldo
   reservado" como propriedade transversal de domínio — o mecanismo de reserva de estoque por
   requisição é uma pendência deliberada (ver Pendências, item 1), não uma decisão revogada. Uma
   revisão anterior deste processo de canonização havia enfraquecido a condição para "Exige saldo
   físico zerado", tratando a ausência de definição formal como se invalidasse a decisão de produto
   já confirmada em `permissions-reconciliation.md`; isso foi identificado em review e revertido —
   ver a nota sobre EST-11 na tabela de Estoque, acima. A condição permanece exigindo saldo
   reservado zerado, com nota explícita de que será reavaliada junto das invariantes
   correspondentes quando o mecanismo de reserva for especificado. A ausência de uma
   `INV-CATALOG-007` na matriz canônica de invariantes não contradiz isso: ela reflete apenas que
   "saldo reservado" ainda não é um conceito verificável o bastante para virar invariante
   transversal própria, não que a condição de autorização esteja errada ou pendente de decisão.
3. **Nenhum conflito material foi encontrado entre a Constitution, `PRODUCT.md` e a spec 001** para
   os itens classificados `MANTER`, `REFORMULAR` ou `NOVA LACUNA` nesta reconciliação. Onde a
   matriz legada e as fontes vigentes discordam (unidade de medida, superusuário, "divergência
   crítica" vs. "divergência de saldo"), a discordância já estava mapeada e resolvida pela
   reconciliação de permissões; este documento apenas confirma que a resolução se sustenta também
   do ponto de vista de invariantes.

## O que este documento não decide

- Não altera `docs/domain/invariants-matrix.md` diretamente. Esse documento já existe e é a fonte
  canônica de invariantes; qualquer mudança nele exige decisão explícita de domínio e atualização
  própria do arquivo, não apenas deste relatório histórico.
- Não resolve nenhuma das pendências listadas acima — elas exigem decisão de produto, não análise
  adicional de documentação.
- Não determina arquitetura de implementação (constraints de banco vs. validação de aplicação vs.
  camada própria); isso pertence a um futuro `plan.md`, justificado conforme a Constitution,
  Princípio I.
- Não abre spec, tarefa ou feature no Spec Kit.
