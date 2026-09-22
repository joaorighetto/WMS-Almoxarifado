# Roadmap funcional — WMS-Almoxarifado

## 1. Objetivo do roadmap

Ser a fonte de verdade para a **decomposição funcional** do WMS: quais capacidades merecem
spec própria, o que permanece junto, seus limites e sua ordem lógica de evolução. Este documento
não é um cronograma nem substitui os requisitos das specs ou as regras canônicas do domínio.

**Uma feature do Spec Kit representa uma capacidade de negócio coesa, demonstrável e validável
de ponta a ponta.** As divisões futuras abaixo são propostas de escopo; não autorizam regras ainda
indefinidas nem criam specs automaticamente.

### Fontes e estado observado

A análise seguiu a precedência solicitada: [constitution](.specify/memory/constitution.md),
[spec 001](specs/001-importacao-catalogo-materiais/spec.md) e
[spec 002](specs/002-autenticacao-login/spec.md), depois [produto](PRODUCT.md),
[permissões](docs/domain/permissions-matrix.md) e
[invariantes](docs/domain/invariants-matrix.md). Planos, tarefas e código foram usados apenas
para verificar o estado atual. Os documentos de [reconciliação](docs/domain/reconciliation/)
são históricos: candidatos pendentes não foram promovidos a requisitos.

- **001 é `001-importacao-catalogo-materiais`**, não uma spec genérica de infraestrutura.
  Contém importação inicial, consulta, auditoria e reimportação do catálogo.
- **001 — `001-importacao-catalogo-materiais`: concluída e entregue em `main`** pelo merge do
  [PR #8](https://github.com/joaorighetto/WMS-Almoxarifado/pull/8) (commit `7dafa30`). A entrega inclui US1 a US4 e foi validada contra o CSV real do SCPI
  (1588 materiais). A dependência de catálogo e saldo inicial de `ENT`, `REQ`, `SAE`, `INV` e
  `MAT` está satisfeita.
- **002 — `002-autenticacao-login`: concluída e entregue em `main`** pelo merge do
  [PR #5](https://github.com/joaorighetto/WMS-Almoxarifado/pull/5)
  (commit `24b8c44`). A entrega inclui a fundação de acesso e as correções de integridade
  do provisionamento identificadas na revisão. A dependência de autenticação das próximas
  features está satisfeita; a administração de produto (`ORG`) permanece planejada.
- O SCPI permanece oficial para cadastro e administração/contabilidade. O WMS controla a
  operação do almoxarifado. A carga vem de CSV e o lançamento posterior no SCPI é manual,
  externo ao WMS. Não há integração automática em nenhuma direção (`INV-SCPI-001`).
- O produto atende um único almoxarifado físico. A menção geral a locais na constitution
  não define uma capacidade de endereçamento ou estoque por local: sua necessidade não está
  confirmada em `PRODUCT.md`.

## 2. Princípios de decomposição

- Separar quando houver resultado de negócio, regras e aceite próprios; manter junto o que
  fecha o mesmo ciclo operacional. Uma tela, entidade, permissão ou operação técnica isolada
  não basta para justificar uma spec.
- Cada recorte deve permitir demonstrar o resultado ao usuário usando suas dependências já
  entregues. Não é necessário que cada feature opere sem qualquer outra capacidade do sistema.
- Permissões, preservação histórica, integridade e testes acompanham cada capacidade desde sua
  entrega. Não são adiados para uma futura feature genérica de segurança, estoque ou auditoria.
- Estados e efeitos compartilhados devem ser esclarecidos antes de implementar os fluxos que
  os consomem. Uma dúvida não vira regra por aparecer neste roadmap.
- Preservar `001` e `002`. Os demais IDs são **rótulos deste mapa**, sem número de spec reservado;
  a numeração será atribuída ao criar cada spec, conforme o repositório estiver naquele momento.

### Decisões relevantes de granularidade

**001 — manter o recorte atual.** Importar, conferir o catálogo e consultar o resultado auditável
fecham a capacidade de disponibilizar a base oficial no WMS. Reimportação reutiliza a mesma
identidade e o mesmo processo de carga, preservando saldos existentes. As histórias podem ser
implementadas incrementalmente dentro da spec; não há motivo para criar outra spec de consulta,
prévia ou histórico de importações. A granularidade é adequada enquanto não absorver manutenção
local, entradas, requisições ou correção de saldo. Apontar divergência pertence à 001;
corrigi-la pertence a `INV`.

**002 — manter a fundação de acesso, com limite explícito.** Login, sessão, proteção, identidade,
retorno seguro, Home mínima e logout formam um ciclo demonstrável. As salvaguardas organizacionais
FR-016a e FR-019 a FR-023 já pertencem à spec porque seu provisionamento inicial escreve usuários,
papéis e setores; não devem ser removidas ou adiadas. Entretanto, o uso do Django Admin para esse
provisionamento não entrega a administração de produto (`ORG`). Novos fluxos de gestão de usuários,
chefias e setores, recuperação de senha, painéis e autorizações operacionais não devem ser
absorvidos pela 002. Cada feature de negócio aplica suas próprias permissões canônicas.

Os três [achados da revisão do PR 5](https://github.com/joaorighetto/WMS-Almoxarifado/pull/5#pullrequestreview-5266085774)
foram corrigidos e entregues na 002: criação de contas sem o papel mínimo, exclusões baseadas
em estado desatualizado e alterações concorrentes incompatíveis de usuários/papéis.
Essas correções preservam garantias já exigidas por FR-016a e FR-019 a FR-023 e não antecipam
os novos fluxos administrativos de `ORG`.

**Requisição e autorização juntas; atendimento separado.** `REQ` entrega uma solicitação que chega
à decisão do chefe competente, sem criar uma spec trivial apenas para aprovar. `ATE` tem outro
resultado: cumprir a solicitação autorizada, efetivar a saída e manter sua conclusão consultável.
Essa separação evita reunir todo o ciclo de estoque em uma única feature. A máquina de estados
e a eventual reserva exigem contrato coerente entre ambas antes da implementação de `ATE`.

**Saídas e correções seguem sua origem.** A saída ordinária pertence ao atendimento; não há
evidência para uma feature de saída livre paralela a ele. A saída excepcional (`SAE`) tem motivos,
autoridade e ciclo próprios, independentes de requisição. Estorno de saída excepcional fica em
`SAE`; estorno de requisição finalizada fica em `ATE`; devolução física vinculada ao atendimento
é `DEV`, incluindo seu próprio estorno. Não se cria uma feature genérica de estornos.

**Consulta histórica e análise têm resultados distintos.** `HIS` permite investigar movimentos
individuais; `REL` consolida consumo por escopo e inclui sua exportação CSV. O painel do chefe
(`PAI`) é uma superfície distinta confirmada, mas ainda não tem conteúdo definido. Observação
interna e inativação ficam juntas em `MAT`, como manutenção operacional local do material,
sem transformar o WMS em mestre do cadastro oficial.

## 3. Mapa de features

**Legenda:** `O` = dependência obrigatória; `R` = ordem recomendada. Todas as capacidades protegidas
consomem `002`; essa dependência está implícita nas linhas futuras. “Planejada” significa capacidade
confirmada com recorte proposto, ainda sem spec. “Requer clarificação” indica que nem o conteúdo
mínimo para delimitar o aceite está suficientemente definido. Pendências de regras das demais
features estão na seção 6.

| ID | Feature | Objetivo / resultado verificável | Inclui | Não inclui | Dependências | Status |
|---|---|---|---|---|---|---|
| 001 | Importação e consulta do catálogo | Do CSV à consulta de materiais e conferência auditável da carga | Prévia e confirmação; saldo inicial; busca; histórico de importações; reimportação cadastral e divergências informativas | Cadastro manual; manutenção local; correção de saldo; movimentações; integração automática | O: 002 | Concluída — entregue em `main` pelo [PR #8](https://github.com/joaorighetto/WMS-Almoxarifado/pull/8) |
| 002 | Autenticação e acesso inicial | Da matrícula e senha à sessão identificada, acesso protegido e logout | Home mínima; retorno seguro; papéis/setor consultáveis; salvaguardas do provisionamento inicial já especificadas | Gestão de produto de usuários/setores; recuperação de senha; painel; autorização das operações de negócio | Nenhuma feature funcional anterior | Concluída — entregue em `main` pelo [PR #5](https://github.com/joaorighetto/WMS-Almoxarifado/pull/5) |
| ORG | Administração de usuários, papéis e setores | Manter identidades e sua organização com chefia válida e atribuições explícitas | Gestão pelo administrador de sistema; vínculo setorial; atribuição dos papéis canônicos; manutenção das invariantes organizacionais | Redefinir papéis; conceder poderes operacionais implícitos; gestão de estoque; redefinir login | O: 002; R: antes do uso amplo de REQ | Planejada |
| ENT | Entrada de materiais | Registrar recebimento e conferir seu efeito no saldo e no registro da operação | Entrada nos motivos canônicos, com referência; rastreabilidade da operação | Criar materiais; compras/licitações; devolução de requisição; ajuste de inventário; importar movimentações do SCPI | O: 001; R: primeira movimentação após catálogo | Planejada |
| REQ | Solicitação e autorização de materiais | Criar solicitação para si ou para terceiro permitido e levá-la à decisão do chefe do setor | Criação; consulta conforme escopo; fila e autorização setorial; definição dos estados desta etapa | Atendimento; baixa física; saída excepcional; notificações; pressupor reserva ou autorização parcial | O: 001 e identidades/setores/chefias válidos; R: ORG | Planejada |
| ATE | Atendimento e conclusão de requisições | Da requisição autorizada à entrega, saída e conclusão consultável | Fila; atendimento por qualquer funcionário do almoxarifado; histórico de concluídas; estorno de requisição finalizada pelo chefe | Autorizar requisição; saída avulsa; devolução física; lançamento no SCPI; pressupor atendimento parcial | O: REQ; R: ENT e HIS | Planejada |
| HIS | Consulta do histórico de movimentações | Localizar movimento e conferir origem, ator, quantidade e momento no escopo permitido | Consulta transversal por permissões; rastreabilidade útil à conferência e ao lançamento manual externo no SCPI | Criar/alterar movimentos; histórico de cargas da 001; relatórios consolidados; controle de pendências no SCPI | O: ao menos uma operação de estoque entregue; R: iniciar após ENT | Planejada |
| SAE | Saídas excepcionais | Registrar baixa independente de requisição e, quando cabível, seu estorno total rastreável | Consulta; motivos e observação canônicos; registro pelo chefe; estorno total com justificativa | Atendimento; baixa livre sem motivo; estorno parcial; gestão completa de empréstimos/doações | O: 001; R: ENT e HIS | Planejada |
| DEV | Devoluções de materiais atendidos | Registrar retorno vinculado a requisição atendida e conferir o efeito no saldo | Devolução pelo chefe; vínculo à origem; estorno da devolução com saldo disponível suficiente | Estornar a própria requisição; entradas de outras origens; presumir devolução parcial | O: ATE; R: HIS | Planejada |
| INV | Ajuste de saldo por inventário | Corrigir no WMS uma divergência apurada, preservando a origem e o histórico do ajuste | Ajuste pelo chefe; tratamento da divergência apontada pela reimportação; rastreabilidade | Sobrescrever saldo por CSV; presumir campanha de contagem, contagem cega, bloqueio ou aprovação adicional | O: 001; R: ENT e HIS | Planejada |
| MAT | Manutenção operacional local de materiais | Acrescentar observação interna ou inativar material elegível, preservando dados oficiais e histórico | Observação pela equipe; inativação pelo chefe com saldo físico e reservado zerados | Criar material; editar cadastro do SCPI; normalizar unidades; exclusão física; presumir reativação | O: 001; interação com reserva a esclarecer | Planejada |
| REL | Relatórios de consumo por setor e consolidados | Consultar consumo no escopo permitido e exportar a mesma visão | Visão do próprio setor para seu chefe; consolidado para gestor/auditor; CSV conforme escopo | Painel exclusivo do almoxarifado; escrituração contábil; inventar métricas financeiras | O: fatos de consumo de ATE; demais fontes conforme métricas a definir; R: HIS e DEV | Requer clarificação |
| PAI | Painel de gestão do almoxarifado | Apoiar a gestão pelo chefe em superfície própria; resultado detalhado a definir | Acesso exclusivo já confirmado; conteúdo requer clarificação futura | Home mínima da 002; relatórios do auditor; indicadores ou alertas presumidos | O: 002; fontes funcionais a definir; R: fluxos operacionais e REL | Requer clarificação |

### Base de domínio dos recortes futuros

As referências abaixo sustentam a existência das capacidades, sem substituir as condições e
escopos completos das matrizes:

| Recorte | Evidência canônica principal |
|---|---|
| ORG | `PERM-USER-MANAGE`, `PERM-SECTOR-MANAGE`; `INV-ORG-001` a `INV-ORG-003` |
| ENT | `PERM-STOCK-ENTRY-CREATE`; `INV-STOCK-001`, `INV-STOCK-004`, `INV-MOV-001/002` |
| REQ | `PERM-REQ-CREATE-SELF`, `PERM-REQ-CREATE-FOR-OTHER`, permissões de consulta e `PERM-REQ-AUTHORIZE` |
| ATE | `PERM-REQ-FULFILLMENT-QUEUE-VIEW`, `PERM-REQUEST-FULFILL`, `PERM-REQ-REVERSE`; fluxo confirmado em `PRODUCT.md` |
| HIS | `PERM-STOCK-HISTORY-VIEW`; `INV-MOV-001/002` |
| SAE | `PERM-SAE-VIEW/CREATE/REVERSE`; `INV-SAE-001/002` |
| DEV | `PERM-RETURN-CREATE`, `PERM-RETURN-REVERSE` |
| INV | `PERM-INVENTORY-ADJUST`; spec 001, FR-047 |
| MAT | `PERM-MATERIAL-EDIT-NOTE`, `PERM-MATERIAL-DEACTIVATE`; `INV-CATALOG-004/006` |
| REL | `PERM-REPORT-GENERAL-VIEW`, `PERM-REPORT-SECTOR-VIEW`, `PERM-REPORT-EXPORT-CSV` |
| PAI | `PERM-ALMOX-MANAGEMENT-PANEL-VIEW` |

## 4. Dependências

### Obrigatórias

- `002 → 001`; `002 →` todas as demais superfícies protegidas. Dependência de autenticação
  satisfeita com a entrega da 002.
- `001 → ENT, REQ, SAE, INV, MAT`: materiais e saldos iniciais vêm do catálogo importado.
  Dependência satisfeita com a entrega da 001.
- `REQ → ATE → DEV`: atendimento exige autorização; devolução exige atendimento de origem.
  `ATE → REL` fornece o consumo por requisição; outras dependências de `REL` serão definidas
  pelas métricas escolhidas.
- `Uma operação de estoque entregue → HIS`: pode ser `ENT`, `ATE`, `SAE` ou `INV`.
  Não é necessário esperar todas. A consulta cresce com as novas origens.
- `REQ` exige usuários, setores e chefias válidos, mas **não exige a entrega de ORG**:
  o provisionamento inicial admitido pela 002 já pode fornecer essa base para validação.

### Ordem recomendada e evolução paralela

- `ENT` antes de `ATE`, `SAE` e `INV` facilita validar cedo a primeira alteração de saldo
  rastreável. Não é dependência obrigatória: a importação já estabelece saldo utilizável.
- Entregar `HIS` cedo facilita conferir operações e preparar o lançamento manual externo.
  Sua ausência não dispensa cada operação de registrar e tornar verificáveis os próprios efeitos.
- Com `002` e `001` entregues, `ORG` pode evoluir sem esperar outra feature; `ENT` e `REQ` podem evoluir
  em paralelo; `SAE`, `INV` e `MAT` não dependem do ciclo completo de requisição.
- A independência acima não autoriza decisões contraditórias sobre reserva, disponibilidade ou
  material inativo. Se afetarem dois recortes, essas decisões devem ser esclarecidas em conjunto.
- `HIS` e `REL` não bloqueiam um ao outro; investigação individual e consolidação usam fatos
  operacionais. `PAI` não depende obrigatoriamente de `REL` até que seu conteúdo seja definido.
- `001` não depende de `INV` para apontar divergências. `SAE` não depende de `REQ`
  (`INV-SAE-002`). Não há feature prévia de “motor de estoque”, “permissões” ou “integração SCPI”.

## 5. Ordem recomendada

1. ~~Entregar `001-importacao-catalogo-materiais`.~~ Concluída: catálogo e saldo inicial estão
   disponíveis a todas as operações.
2. **Especificar `ORG` e `ENT`**, agora que a 001 está entregue. A primeira organiza a
   administração cotidiana; a segunda entrega o primeiro fluxo de estoque após a carga.
3. **Especificar `REQ` e `HIS`**, com suas dependências satisfeitas para implementação. A primeira
   fecha solicitação/autorização; a segunda permite investigar os movimentos já produzidos.
4. **Especificar e implementar `ATE`**, fechando catálogo → solicitação → autorização → entrega
   → saída → consulta da conclusão. Resolver antes os pontos compartilhados de estados e reserva.
5. **Evoluir `DEV`, `SAE` e `INV`**, como ciclos próprios de retorno, saída excepcional e correção.
   `SAE` e `INV` podem ser antecipadas após a 001 se a operação precisar delas; sua posição aqui
   é recomendação para validar primeiro o fluxo ordinário, não bloqueio funcional.
6. **Evoluir `MAT` e delimitar `REL`/`PAI`**. MAT também pode ser antecipada após a 001, desde
   que se esclareçam os efeitos da inativação. Relatórios e painel precisam ter conteúdo e fontes
   definidos antes de receberem specs prontas para implementação.

A ordem de especificação pode antecipar contratos de features dependentes. A implementação e o
aceite de ponta a ponta respeitam as dependências obrigatórias. Números de specs não definem
prioridade: a 002 precede funcionalmente a 001 sem renumeração de nenhuma delas.

## 6. Pontos ainda indefinidos

| Recorte | Decisão que exige clarificação antes da respectiva spec/implementação |
|---|---|
| ORG | **A definir:** fluxos de manutenção, troca de chefia e desativação de setor; relação com requisições em andamento; entrega/recuperação de credenciais. O provisionamento da 002 não resolve esses fluxos de produto. |
| REQ / ATE | **Requer clarificação futura:** máquina de estados, envio/rascunho, recusa/retorno, cancelamentos, autorização parcial, atendimento parcial e eventual separação para retirada. Não tratar candidatos do legado como decisões vigentes. |
| REQ / ATE e demais operações | **A definir:** existência e mecanismo de reserva, momentos de reservar/consumir/liberar e conceito de saldo disponível. Preservar desde já as condições canônicas de inativação e estorno de devolução; reservado inexistente vale zero para inativação, conforme a matriz, sem obrigar a criar reserva antes de MAT. |
| ENT / SAE | **A definir:** composição do registro operacional, informações de referência e fluxo de confirmação. Motivos e autoridades já estão confirmados; não ampliar essas operações para módulos de compras, empréstimos ou doações. |
| ATE / DEV | **Requer clarificação futura:** limites quantitativos de devolução, possibilidade de parcialidade, relação entre devoluções e estorno da requisição, efeitos no consumo. Estorno de requisição exige justificativa e a encerra definitivamente; estorno de devolução exige saldo disponível suficiente, como já definido. |
| INV | **A definir:** apuração da quantidade correta, evidência do ajuste e fluxo de validação. Há confirmação de ajuste por inventário, não de um processo completo de campanhas e contagens. |
| MAT | **Requer clarificação futura:** operações permitidas sobre material inativo, eventual reativação e efeito da reimportação sobre atributos locais. A redação ampla de SC-005 da 001 deve ser conciliada explicitamente, na futura spec, com as capacidades canônicas de observação interna/inativação, sem liberar edição dos dados oficiais. |
| 001 / futuras | **A definir:** como o responsável leva as exceções de uma importação para fora do WMS a fim de corrigir o CSV na origem — exportação, filtro por motivo ou ordenação da lista de exceções. Hoje a 001 só exibe a lista paginada, e o trabalho de correção acontece fora do sistema; levantado pela revisão visual de 2026-09-22. Decidir o recorte (dentro da 001 ou capacidade própria) antes de implementar. |
| HIS | **A definir:** filtros e apresentação necessários à investigação. Os escopos por papel já são canônicos; não presumir que todo usuário vê todo o histórico. |
| REL / PAI | **A definir:** perguntas de gestão, métricas, períodos, tratamento de devoluções/estornos e fontes. Não inferir indicadores financeiros, alertas ou visões de pendências no SCPI. |
| Evidências de importação | `PRODUCT.md` referencia CSVs e scripts em `domain/Scripts/`, ausentes nesta árvore. O CSV real do catálogo está disponível só localmente (`docs/domain-legacy/`, ignorado pelo Git) e validou a 001 em 2026-09-22 por `tests/test_catalogo_arquivo_real.py` com `SCPI_CSV_REAL` (1588 recebidos e inseridos, 0 rejeitados). Como não é versionado, esse teste fica pulado no CI. **A definir:** se e como disponibilizar amostras dos demais CSVs (movimentações) para as próximas features. Isso não cria nova feature. |

Não entram como features confirmadas: múltiplos locais/endereçamento, lotes, validade como controle
próprio, leitura de códigos de barras, compras/licitações, notificações, integração automática,
importação de movimentos do SCPI ou controle de lançamentos pendentes no sistema oficial.
Nem a existência de colunas no CSV nem um motivo de saída autorizam inferir esses módulos.
Só uma necessidade de produto explicitamente confirmada poderá incluí-los neste mapa.

Ao criar cada spec futura, revisar seu recorte e suas pendências neste documento e referenciar
as permissões e invariantes aplicáveis. Atualizar o roadmap quando uma decisão de domínio mudar
fronteiras ou dependências; não redefinir silenciosamente as fontes canônicas.
