# Feature Specification: Entrada de Materiais

**Feature Branch**: `003-entrada-materiais`

**Feature Directory**: `specs/003-entrada-materiais`

**Created**: 2026-09-25

**Status**: Draft

**Input**: User description: "Feature ENT do ROADMAP.md — Entrada de materiais. Objetivo: registrar
o recebimento de materiais no almoxarifado e conferir seu efeito no saldo e no registro da operação.
Inclui: entrada de estoque nos motivos canônicos, com referência obrigatória; rastreabilidade da
operação (origem, ator, quantidade, momento). Não inclui: criar materiais; compras/licitações;
devolução de requisição (DEV); ajuste de inventário (INV); importar movimentações do SCPI;
integração automática com o SCPI; consulta transversal do histórico de movimentações (HIS);
estorno de outras operações. Dependências: 001 e 002, entregues. Regras canônicas:
PERM-STOCK-ENTRY-CREATE; INV-STOCK-001, INV-STOCK-002, INV-STOCK-004, INV-MOV-001, INV-MOV-002,
INV-CATALOG-003, INV-SCPI-001. Pontos a fixar antes da implementação: composição do registro
operacional, informações de referência, fluxo de confirmação e correção de entrada registrada com
erro, sem inventar capability nova. Não ampliar para compras, empréstimos ou doações; não fixar
regra que restrinja MAT. Lançamentos do WMS são registrados depois, manualmente, no SCPI; um único
almoxarifado físico, sem locais, lotes ou validade."

## Clarifications

### Sessão 2026-09-25

- **Composição da entrada**: uma entrada tem um motivo e uma referência e contém um ou mais itens
  (material e quantidade), como os itens de uma mesma nota fiscal. O registro é indivisível: todos
  os itens ou nenhum (FR-004, FR-011).
- **Referência**: estruturada em tipo de documento, de lista fechada — Nota fiscal; Termo de
  doação; Termo/recibo de devolução —, mais número do documento, texto obrigatório. Não há tipo
  "Outro". O tipo é independente do motivo (FR-007). O emitente foi acrescentado à referência na
  sessão de `clarify` abaixo.
- **Correção de entrada com erro**: por estorno total da entrada, exclusivo do chefe do
  almoxarifado, com justificativa obrigatória e bloqueado se deixar saldo negativo. Não há estorno
  parcial. A capability `PERM-STOCK-ENTRY-REVERSE` foi incluída em
  `docs/domain/permissions-matrix.md` (versão 1.1) e o "Inclui" da `ENT` em `ROADMAP.md` foi
  ampliado por decisão do dono do produto antes desta spec usá-la (US3, FR-022 a FR-028).
- Q: Como a entrada passa a valer — resumo e confirmação, rascunho salvo ou registro direto? → A:
  resumo e confirmação; nada é persistido antes da confirmação e não há rascunho (FR-008).
- Q: O que fazer quando o mesmo documento já foi usado em outra entrada não estornada? → A: a nota
  só é lançada depois que a entrega termina, sem entregas parciais; documento repetido é bloqueado.
  Como o número de nota só é único por emitente, a referência passa a incluir o emitente, vindo de
  um cadastro de fornecedores importado do SCPI por CSV (FR-007, FR-007a).
- Q: Onde entra o cadastro de fornecedores? → A: em feature própria (`FOR`, "Importação do
  cadastro de fornecedores do SCPI"), incluída no `ROADMAP.md` como dependência obrigatória da
  `ENT`. Esta spec só consome fornecedores; a implementação e o aceite da `ENT` esperam `FOR`.
- Q: Em quais motivos o emitente é obrigatório? → A: em compra e em devolução de
  fornecedor/garantia; em doação recebida e empréstimo devolvido é opcional (FR-007).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Registrar a entrada de materiais recebidos (Priority: P1)

Um funcionário do almoxarifado recebe materiais — de uma compra, de uma doação, de uma devolução de
fornecedor ou garantia, ou de um empréstimo que retornou. Ele escolhe o motivo da entrada, informa
o documento que a justifica (tipo, número e emitente), localiza no catálogo importado do SCPI cada material
recebido e informa a quantidade de cada um, confere o resumo do que será registrado e confirma. O saldo de cada
material aumenta na quantidade informada, e a operação fica registrada com motivo, referência,
quantidades, autor e momento.

**Why this priority**: é o primeiro fluxo de estoque após a carga do catálogo. Sem ele, o saldo do
WMS só reflete o arquivo inicial e se afasta da realidade a cada recebimento; a operação diária do
almoxarifado continuaria dependendo do SCPI.

**Independent Test**: com o catálogo importado e um funcionário do almoxarifado autenticado,
registrar uma entrada e verificar que o saldo do material aumentou exatamente na quantidade
informada e que o registro da operação exibe motivo, referência, quantidade, autor e momento.

**Acceptance Scenarios**:

1. **Given** um material do catálogo com saldo 10, **When** o funcionário do almoxarifado registra
   uma entrada de 5 unidades desse material com motivo "compra", referência "Nota fiscal" número
   "12345" emitida por um fornecedor do cadastro e confirma, **Then** o saldo do material passa a 15 e a operação fica registrada com o
   motivo, a referência, a quantidade, o funcionário e o momento do registro.
2. **Given** dois materiais com saldos 10 e 0, **When** o funcionário registra uma única entrada com
   os dois itens, 4 e 6 unidades, e confirma, **Then** os saldos passam a 14 e 6, e uma única
   entrada registra os dois itens sob o mesmo motivo e a mesma referência.
3. **Given** o funcionário preencheu a entrada, **When** ele revisa o resumo antes de confirmar e
   desiste, **Then** nenhum saldo é alterado e nenhuma operação é registrada.
4. **Given** um material com unidade "KG" e saldo 2,500, **When** o funcionário registra entrada de
   0,750, **Then** o saldo passa a 3,250, sem arredondamento além de três casas decimais e sem
   conversão de unidade.
5. **Given** o funcionário não informou motivo, tipo ou número do documento, emitente em compra ou
   devolução de fornecedor/garantia, nenhum item, ou informou quantidade inválida, **When** tenta
   confirmar, **Then** a entrada é recusada com indicação do campo a corrigir, os dados já
   preenchidos são preservados e nenhum saldo é alterado.
6. **Given** já existe entrada não estornada com a Nota fiscal "12345" do mesmo emitente, **When**
   o funcionário tenta confirmar outra entrada com essa referência, **Then** a entrada é recusada,
   indicando a entrada existente, e nenhum saldo é alterado.
7. **Given** o funcionário incluiu o mesmo material duas vezes na entrada, **When** tenta
   confirmar, **Then** a entrada é recusada com indicação do item repetido, sem alterar saldo.
8. **Given** um usuário autenticado sem o papel de funcionário do almoxarifado, **When** tenta
   acessar o registro de entrada ou enviar uma entrada diretamente, **Then** a operação é negada e
   nenhum saldo é alterado.

---

### User Story 2 - Conferir as entradas registradas (Priority: P2)

Depois de registrar, e também em outro momento — por exemplo, ao lançar manualmente as entradas no
SCPI —, o funcionário do almoxarifado consulta as entradas registradas no WMS e abre cada uma para
conferir motivo, referência, materiais, quantidades, autor e momento.

**Why this priority**: torna verificável o efeito da própria operação e apoia o lançamento manual
posterior no SCPI. Não substitui a consulta transversal de movimentações, que pertence à feature
`HIS`.

**Independent Test**: registrar duas entradas e verificar que ambas aparecem na consulta de
entradas, da mais recente para a mais antiga, e que o detalhe de cada uma exibe exatamente os dados
confirmados.

**Acceptance Scenarios**:

1. **Given** entradas registradas por funcionários diferentes, **When** um funcionário do
   almoxarifado abre a consulta de entradas, **Then** vê todas elas, da mais recente para a mais
   antiga, com momento, motivo, referência, autor e situação (registrada ou estornada) de cada uma.
2. **Given** uma entrada registrada, **When** o funcionário abre seu detalhe, **Then** vê motivo,
   referência, autor, momento e, para cada material, código SCPI, descrição, unidade e quantidade
   recebida; se a entrada tiver sido estornada, vê também autor, momento e justificativa do
   estorno.
3. **Given** um usuário autenticado sem autorização de consulta ao histórico de movimentações,
   **When** tenta abrir a consulta ou o detalhe de uma entrada, **Then** o acesso é negado.
4. **Given** uma entrada registrada, **When** qualquer usuário tenta alterar ou excluir sua
   quantidade, material, motivo, referência, autor ou momento, **Then** nenhum caminho da aplicação
   permite a alteração.

---

### User Story 3 - Corrigir uma entrada registrada com erro (Priority: P3)

Uma entrada foi registrada com erro — material, quantidade, motivo ou referência errados. O chefe
do almoxarifado abre a entrada, informa a justificativa e estorna a entrada inteira. Os saldos dos
itens voltam ao que eram sem ela, e a entrada original permanece registrada, marcada como
estornada. Se necessário, um funcionário registra depois a entrada correta.

**Why this priority**: a entrada não pode ser editada (`INV-MOV-001`). Sem estorno, um erro de
digitação deixaria o saldo errado até existir o ajuste por inventário. É menos frequente que o
registro e depende dele.

**Independent Test**: registrar uma entrada, estorná-la como chefe do almoxarifado e verificar que
os saldos voltaram aos valores anteriores, que a entrada original continua consultável e marcada
como estornada, e que o estorno exibe autor, momento e justificativa.

**Acceptance Scenarios**:

1. **Given** uma entrada com itens de 4 e 6 unidades sobre materiais com saldos atuais 14 e 6,
   **When** o chefe do almoxarifado a estorna com justificativa e confirma, **Then** os saldos
   passam a 10 e 0, a entrada aparece como estornada e o estorno fica registrado com autor, momento
   e justificativa.
2. **Given** uma entrada de 10 unidades cujo material hoje tem saldo 7, **When** o chefe tenta
   estorná-la, **Then** o estorno é recusado inteiro, indicando o item que ficaria com saldo
   negativo, e nenhum saldo é alterado.
3. **Given** uma entrada já estornada, **When** alguém tenta estorná-la de novo, **Then** a
   operação é recusada e nenhum saldo é alterado.
4. **Given** o chefe não informou justificativa, **When** tenta confirmar o estorno, **Then** o
   estorno é recusado sem efeito.
5. **Given** um funcionário do almoxarifado que não é chefe, ou qualquer outro papel, **When**
   tenta estornar uma entrada, inclusive enviando o pedido diretamente, **Then** a operação é
   negada.

---

### Edge Cases

- **Entradas simultâneas do mesmo material**: duas entradas confirmadas ao mesmo tempo para o mesmo
  material somam ambas ao saldo; nenhuma sobrescreve a outra.
- **Confirmação repetida**: clique duplo, reenvio do formulário ou repetição da requisição após
  falha de rede não registram a mesma entrada duas vezes.
- **Falha no meio do registro**: se qualquer parte do registro falhar, nenhum saldo é alterado e
  nenhuma operação ou item fica registrado (`INV-STOCK-004`).
- **Quantidade zero, negativa, vazia ou não numérica**: recusada; entrada nunca reduz saldo.
- **Quantidade com mais de três casas decimais**: recusada com orientação, em vez de arredondada em
  silêncio, porque o saldo é mantido em três casas decimais.
- **Quantidade com separador de milhar ou vírgula decimal**: interpretada na convenção brasileira,
  como na importação do catálogo.
- **Saldo resultante acima do máximo representável**: a entrada é recusada, sem alterar saldo.
- **Material inexistente no catálogo**: não pode ser escolhido; a entrada não cria material
  (`INV-CATALOG-003`).
- **Material com saldo zero**: aceita entrada normalmente.
- **Reimportação do catálogo depois de uma entrada**: não sobrescreve o saldo alterado pela entrada
  (`INV-STOCK-002`); a eventual diferença para o arquivo é divergência informativa da 001.
- **Referência só com espaços**: tratada como ausente.
- **Mesmo documento já lançado** (mesmo tipo, número e emitente em entrada não estornada): recusado,
  indicando a entrada existente (FR-007a).
- **Mesmo número de nota de emitentes diferentes**: aceito; são documentos distintos.
- **Compra ou devolução de fornecedor/garantia sem emitente**: recusada.
- **Emitente ausente do cadastro de fornecedores**: não pode ser escolhido; a entrada não cadastra
  fornecedor. O cadastro é atualizado pela importação de `FOR`, fora desta feature.
- **Motivo fora da lista fechada**, inclusive enviado diretamente sem passar pela tela: recusado.
- **Sessão expirada durante o preenchimento**: a confirmação não registra nada; o usuário é levado
  ao login conforme a 002.
- **Usuário desativado entre o preenchimento e a confirmação**: a confirmação é negada
  (`INV-AUTH-001`).
- **Mesmo material repetido na entrada**: recusado; cada material aparece no máximo uma vez por
  entrada.
- **Entrada sem nenhum item**: recusada.
- **Estorno concorrente com outra operação que reduz saldo**: a verificação de saldo não negativo
  considera o saldo efetivo no momento do estorno; nunca resulta em saldo negativo.
- **Dois estornos simultâneos da mesma entrada**: no máximo um é efetivado.
- **Estorno bloqueado por saldo insuficiente** (material já saiu em parte): a entrada permanece
  como está; a correção fica para o ajuste de inventário (`INV`), fora desta feature.

## Requirements *(mandatory)*

### Functional Requirements

**Registro da entrada**

- **FR-001**: O sistema DEVE permitir que um usuário com o papel `ROLE-WAREHOUSE-STAFF` registre uma
  entrada de estoque. Nenhum outro papel pode registrar entrada, inclusive o administrador de
  sistema e o superusuário técnico.
- **FR-002**: A entrada DEVE referenciar apenas materiais já existentes no catálogo importado do
  SCPI, identificados pelo código `CADPRO`. A entrada NÃO DEVE criar, alterar ou completar dados
  cadastrais de material.
- **FR-003**: O usuário DEVE poder localizar o material pelo código SCPI exato ou pela descrição,
  com o mesmo comportamento de busca da consulta do catálogo da 001.
- **FR-004**: Uma entrada DEVE conter um ou mais itens, cada um formado por um material e sua
  quantidade recebida, todos sob o mesmo motivo e a mesma referência. Um material NÃO DEVE aparecer
  em mais de um item da mesma entrada.
- **FR-005**: Cada material da entrada DEVE ter quantidade recebida estritamente maior que zero,
  com no máximo três casas decimais, na unidade de medida do material tal como importada do SCPI,
  sem conversão ou normalização de unidade.
- **FR-006**: A entrada DEVE ter exatamente um motivo, escolhido da lista fechada: compra; doação
  recebida; devolução de fornecedor/garantia; empréstimo devolvido. Nenhum outro motivo é aceito.
- **FR-007**: A entrada DEVE ter referência obrigatória, composta por: tipo de documento,
  escolhido da lista fechada — Nota fiscal; Termo de doação; Termo/recibo de devolução —; número
  do documento, texto livre não vazio após remover espaços das pontas, preservado como informado;
  e emitente, escolhido do cadastro de fornecedores importado do SCPI (`FOR`). O emitente é
  obrigatório nos motivos compra e devolução de fornecedor/garantia e opcional nos motivos doação
  recebida e empréstimo devolvido. O tipo de documento é independente do motivo. Tipo fora da lista
  ou emitente inexistente no cadastro são recusados. A entrada não cria nem altera fornecedor.
- **FR-007a**: Uma entrada NÃO DEVE ser registrada se já existir outra entrada não estornada com a
  mesma referência — mesmo tipo de documento, mesmo número (comparado após remover espaços das
  pontas, sem outra normalização) e mesmo emitente, ou ambas sem emitente. A recusa indica a
  entrada existente. Depois de estornada, a referência pode ser usada de novo. Entradas simultâneas
  com a mesma referência efetivam no máximo uma.
- **FR-008**: Antes de registrar, o sistema DEVE apresentar ao usuário um resumo da entrada —
  motivo, referência (tipo, número e emitente), materiais, quantidades, saldo atual e saldo
  resultante de cada material — e só registrar após confirmação explícita. Nada é persistido antes
  da confirmação: não existe rascunho, e desistir no resumo ou abandonar o preenchimento não
  registra nada.
- **FR-009**: Dados inválidos DEVEM ser recusados com indicação de cada campo a corrigir,
  preservando o que já foi preenchido.

**Efeito no saldo e atomicidade**

- **FR-010**: Ao confirmar, o sistema DEVE aumentar o saldo de cada material exatamente na
  quantidade recebida informada.
- **FR-011**: O aumento de saldo e o registro da operação DEVEM ocorrer juntos, de forma
  indivisível: ou todo o registro é efetivado — todos os materiais, saldos e o registro da
  operação —, ou nada é efetivado (`INV-STOCK-004`).
- **FR-012**: Entradas concorrentes sobre o mesmo material DEVEM ter todas as suas quantidades
  refletidas no saldo final, sem perda de atualização.
- **FR-013**: Uma mesma confirmação, repetida por clique duplo, reenvio ou nova tentativa após
  falha de comunicação, NÃO DEVE registrar a entrada mais de uma vez.
- **FR-014**: O saldo resultante DEVE respeitar a precisão de três casas decimais e o limite
  máximo representável; entrada que ultrapasse esse limite é recusada sem efeito.
- **FR-015**: A entrada NÃO DEVE alterar nenhum outro material além dos que contém, nem qualquer
  dado cadastral do material.

**Rastreabilidade**

- **FR-016**: Cada entrada registrada DEVE preservar: motivo, referência (tipo, número e emitente,
  quando houver), autor (a identidade
  autenticada que confirmou), momento do registro e, para cada material, a quantidade recebida
  (`INV-MOV-002`).
- **FR-017**: Cada alteração de saldo produzida por uma entrada DEVE ser identificável como
  proveniente daquela entrada e distinguível do saldo inicial estabelecido pela importação do SCPI.
- **FR-018**: Os fatos de uma entrada registrada — materiais, quantidades, motivo, referência,
  autor e momento — NÃO DEVEM ser alterados nem excluídos por nenhum caminho da aplicação
  (`INV-MOV-001`). Toda correção ocorre por estorno, um novo registro compensatório e rastreável
  (FR-022 a FR-028).
- **FR-019**: O momento do registro DEVE ser atribuído pelo sistema no instante da confirmação,
  não informado pelo usuário.

**Consulta das entradas**

- **FR-020**: O sistema DEVE oferecer a consulta das entradas registradas, da mais recente para a
  mais antiga, e o detalhe de cada entrada com os dados de FR-016, sua situação (registrada ou
  estornada), os dados do estorno quando houver (FR-025) e, para cada material, código SCPI,
  descrição e unidade.
- **FR-021**: A consulta e o detalhe das entradas seguem `PERM-STOCK-HISTORY-VIEW`. Como uma
  entrada não pertence a setor requisitante e só pode ser criada por funcionário do almoxarifado,
  a aplicação dessa capability resulta em: `ROLE-WAREHOUSE-STAFF` e `ROLE-AUDITOR` veem todas as
  entradas; os demais papéis não veem nenhuma. Ocultar o acesso na interface não substitui a
  verificação da autorização.

**Correção**

- **FR-022**: O sistema DEVE permitir que um usuário com o papel `ROLE-WAREHOUSE-HEAD` estorne uma
  entrada registrada. Nenhum outro papel pode estornar entrada, inclusive `ROLE-WAREHOUSE-STAFF`
  sem `ROLE-WAREHOUSE-HEAD` (`PERM-STOCK-ENTRY-REVERSE`).
- **FR-023**: O estorno DEVE ser total: abrange todos os itens da entrada, cada um na quantidade
  integral recebida. Não há estorno de item isolado nem de parte da quantidade.
- **FR-024**: O estorno DEVE exigir justificativa, texto não vazio após remover espaços das pontas,
  e confirmação explícita após o resumo dos saldos atuais e resultantes de cada item.
- **FR-025**: O estorno DEVE ser registrado como operação própria, com autor, momento atribuído
  pelo sistema, justificativa e vínculo com a entrada estornada; cada redução de saldo que produz
  DEVE ter movimentação correspondente identificável como proveniente do estorno (`INV-MOV-002`).
  Os fatos do estorno NÃO DEVEM ser alterados nem excluídos (`INV-MOV-001`).
- **FR-026**: O estorno DEVE ser recusado inteiro, sem efeito, se reduzir o saldo de qualquer item
  abaixo de zero no momento de sua efetivação (`INV-STOCK-001`), indicando os itens que o impedem.
- **FR-027**: Uma entrada DEVE poder ser estornada no máximo uma vez; estorno de estorno não existe.
  Pedidos repetidos ou simultâneos de estorno da mesma entrada efetivam no máximo um.
- **FR-028**: A redução dos saldos, o registro do estorno e a marcação da entrada como estornada
  DEVEM ocorrer de forma indivisível (`INV-STOCK-004`). A entrada original permanece registrada e
  consultável, com seus fatos inalterados.

**Limites**

- **FR-029**: A feature NÃO DEVE realizar integração automática com o SCPI em nenhuma direção; o
  lançamento equivalente no SCPI permanece manual e externo ao WMS (`INV-SCPI-001`).
- **FR-030**: Usuário inativo não registra, estorna nem consulta entradas (`INV-AUTH-001`).

### Key Entities

- **Entrada**: operação de recebimento de materiais no almoxarifado. Tem motivo, referência (tipo
  de documento e número), autor e momento; contém um ou mais itens (FR-004). Seus fatos são
  imutáveis depois de registrada; sua situação passa de registrada a estornada no máximo uma vez.
- **Item da entrada**: um material do catálogo e a quantidade recebida dele na entrada.
- **Motivo de entrada**: valor de lista fechada — compra, doação recebida, devolução de
  fornecedor/garantia, empréstimo devolvido.
- **Tipo de documento de referência**: valor de lista fechada — Nota fiscal, Termo de doação,
  Termo/recibo de devolução.
- **Fornecedor** (de `FOR`): emitente do documento de referência, vindo do cadastro de fornecedores
  importado do SCPI. A entrada só o referencia; seus atributos e sua identidade são definidos pela
  spec de `FOR`.
- **Estorno de entrada**: operação compensatória que anula integralmente uma entrada. Tem autor,
  momento, justificativa e vínculo com a entrada; imutável.
- **Movimentação de estoque**: o registro de cada alteração de saldo, identificando a operação de
  origem (a entrada ou seu estorno), o material, a quantidade, o autor e o momento. É o fato que `HIS` consultará
  transversalmente no futuro.
- **Material** (da 001): entidade do catálogo cujo saldo a entrada aumenta; seus dados cadastrais
  não mudam.

## Regras canônicas aplicáveis

### Permissões

- `PERM-STOCK-ENTRY-CREATE` — registro da entrada, somente `ROLE-WAREHOUSE-STAFF`, com motivo de
  lista fechada e referência obrigatória (FR-001, FR-006, FR-007).
- `PERM-STOCK-ENTRY-REVERSE` — estorno total da entrada, somente `ROLE-WAREHOUSE-HEAD`, com
  justificativa obrigatória e bloqueio por saldo negativo (FR-022 a FR-028). Capability incluída na
  matriz em 2026-09-25 por decisão do dono do produto.
- `PERM-STOCK-HISTORY-VIEW` — consulta e detalhe das entradas registradas (FR-020, FR-021).
- `PERM-MATERIAL-VIEW` — localização do material ao compor a entrada (FR-003).

### Invariantes

- `INV-AUTH-001` — usuário inativo não opera nem consulta (FR-030).
- `INV-CATALOG-003` — entrada não cria material (FR-002).
- `INV-CATALOG-004` — entrada não altera dados cadastrais do material (FR-002, FR-015).
- `INV-CATALOG-005` — quantidade na unidade do material, sem conversão (FR-005).
- `INV-STOCK-001` — saldo nunca negativo; entrada só aumenta saldo e estorno é bloqueado se
  deixar saldo negativo (FR-005, FR-010, FR-026).
- `INV-STOCK-002` — reimportação não sobrescreve saldo alterado por entrada (Edge Cases).
- `INV-STOCK-004` — registro e estorno indivisíveis (FR-011, FR-012, FR-028).
- `INV-MOV-001` — fatos da entrada e do estorno imutáveis; correção por estorno compensatório
  (FR-018, FR-025, FR-028).
- `INV-MOV-002` — toda alteração de saldo com movimentação correspondente na mesma operação (FR-016,
  FR-017, FR-025).
- `INV-SCPI-001` — sem integração automática com o SCPI (FR-029).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Após qualquer sequência de entradas e estornos, o saldo de cada material é igual ao
  saldo inicial da importação somado às quantidades das entradas não estornadas registradas para
  ele, em 100% dos materiais.
- **SC-002**: 100% das alterações de saldo produzidas por entradas têm movimentação correspondente
  com operação de origem, autor, quantidade e momento.
- **SC-003**: Nenhuma falha durante o registro deixa saldo alterado sem entrada registrada, ou
  entrada registrada sem o saldo correspondente.
- **SC-004**: Com entradas confirmadas simultaneamente para o mesmo material, o saldo final reflete
  a soma de todas elas.
- **SC-005**: Uma confirmação repetida nunca produz mais de uma entrada.
- **SC-006**: Nenhum usuário sem `ROLE-WAREHOUSE-STAFF` consegue registrar entrada, por nenhum
  caminho da aplicação.
- **SC-007**: Um funcionário do almoxarifado registra uma entrada de um material, do início à
  confirmação, em menos de um minuto.
- **SC-008**: Nenhum caminho da aplicação permite alterar ou excluir uma entrada ou um estorno
  registrados.
- **SC-009**: Nenhum usuário sem `ROLE-WAREHOUSE-HEAD` consegue estornar entrada, e nenhuma entrada
  é estornada mais de uma vez nem deixa saldo negativo.

## Fora de Escopo

- Criação, edição ou exclusão de materiais (`INV-CATALOG-003`, `INV-CATALOG-004`).
- Cadastro, importação, edição ou consulta própria de fornecedores (`FOR`).
- Módulos de compras, licitações, empenhos, empréstimos ou doações; o motivo apenas classifica a
  entrada.
- Devolução de material atendido em requisição (`DEV`).
- Ajuste de saldo por inventário (`INV`).
- Saídas de qualquer natureza, requisições e atendimento (`SAE`, `REQ`, `ATE`).
- Consulta transversal do histórico de movimentações, filtros por material e por operação (`HIS`).
- Importação de movimentações do SCPI e qualquer integração automática com ele.
- Controle de lançamentos pendentes no SCPI.
- Locais de armazenamento, lotes, validade, leitura de código de barras e notificações.
- Regras sobre material inativo, que não existe antes de `MAT`.
- Estorno parcial de entrada, por item ou por quantidade.
- Correção de entrada cujo estorno é bloqueado por saldo insuficiente, que é ajuste de inventário
  (`INV`).

## Assumptions

- Dependência: `FOR` (importação do cadastro de fornecedores do SCPI) entrega fornecedores
  identificáveis e localizáveis para escolha como emitente. Esta spec não define atributos nem
  formato do fornecedor; se a spec de `FOR` fixar algo incompatível com FR-007/FR-007a, esta spec
  é revista pelo fluxo normal.
- Não há aprovação por segundo usuário: a confirmação do próprio funcionário registra a entrada.
- Não há prazo para estorno: uma entrada não estornada pode ser estornada a qualquer tempo, sujeita
  a FR-026.
- O momento relevante é o do registro no WMS; não há data de recebimento retroativa informada pelo
  usuário.
- Quantidades seguem a escala de três casas decimais já adotada para o saldo na 001.
- A consulta de entradas desta feature é a da própria operação (lista e detalhe das entradas), sem
  filtros; investigação transversal de movimentações fica em `HIS`.
- Esta feature não fixa se material inativo aceita entrada; quando `MAT` existir, a regra será
  decidida lá e aplicada aqui pelo fluxo normal.
- Não há necessidade confirmada de valores monetários, fornecedor estruturado ou dados fiscais na
  entrada; a referência (tipo, número e emitente) é o elo documental com o recebimento. Não se
  valida o formato do número do documento.
