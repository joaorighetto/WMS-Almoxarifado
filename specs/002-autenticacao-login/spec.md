# Feature Specification: Fundação de Autenticação e Login

**Feature Branch**: `main` (nenhuma branch dedicada — extensão git do Spec Kit não instalada)

**Feature Directory**: `specs/002-autenticacao-login`

**Created**: 2026-09-19

**Status**: Draft

**Input**: User description: "Criar a fundação mínima de autenticação e login do WMS-Almoxarifado,
necessária para que qualquer outra feature (incluindo `001-importacao-catalogo-materiais`) possa
presumir usuário autenticado e ações condicionadas a papel. A numeração desta feature não indica
ordem de implementação em relação à 001; a 001 não deve ser renumerada nem alterada. Fluxo esperado:
acessa o WMS → informa suas credenciais → é autenticado → entra na área autenticada → permanece
identificado durante a sessão → encerra a sessão quando desejar. Um visitante não autenticado que
tentar acessar uma superfície protegida não deve receber o conteúdo protegido, deve ser direcionado
ao fluxo de autenticação e, após autenticar com sucesso, deve retornar ao destino originalmente
solicitado quando isso for seguro e aplicável. Escopo: login (acesso à página de login, envio de
credenciais, autenticação válida, credenciais inválidas sem revelar existência de usuário, conta
inativa impedida de autenticar, manutenção de sessão); acesso protegido (negar conteúdo, redirecionar
ao login, retornar ao destino original); identificação de usuário e papel após login, usando
exclusivamente o catálogo de papéis já canônico em `docs/domain/permissions-matrix.md`, sem redefinir
papéis; logout. Fora de escopo: administração de usuários/papéis/setores, recuperação de senha e
provisionamento de credencial, escolha do mecanismo de autenticação além do necessário para descrever
login básico, autorização específica de outras features de negócio, MFA e políticas de senha/
throttling sem evidência de necessidade. Não determinar mecanismo técnico de sessão, middleware ou
estratégia de redirect."

## Clarifications

### Sessão 2026-09-19

- **Identificador de login**: nesta primeira versão, o identificador informado junto da senha é a
  matrícula funcional do SAEP. A escolha não impede uma futura migração para SSO, e-mail
  institucional ou outro mecanismo (FR-001a).
- **Destino autenticado padrão**: a feature define conceitualmente uma Home autenticada mínima —
  sem funcionalidades de negócio de outra feature, alinhada a `DESIGN.md` — como destino padrão
  sempre que não houver destino anterior aplicável: login direto, ausência de destino anterior,
  destino inexistente/inválido, destino não autorizado ao usuário, ou usuário já autenticado
  acessando a página de login (FR-005a, FR-012).
- **Retorno pós-login**: o retorno ao destino originalmente solicitado só ocorre quando ele é
  interno ao WMS, ainda existe e o usuário autenticado tem autorização para acessá-lo (FR-010); em
  qualquer outro caso, o usuário é direcionado à Home autenticada mínima (FR-010a), nunca a um
  endereço externo (FR-011, inalterado).
- **Destino após logout**: imediatamente após o encerramento explícito da sessão, o usuário é
  direcionado à página de login (FR-017a); a sessão encerrada continua sem conceder acesso a
  superfícies protegidas (FR-017, FR-018, inalterados).
- **Contrato funcional da matrícula como identificador**: nenhuma fonte normativa (`PRODUCT.md`,
  constitution, matrizes de domínio) determina unicidade ou formato da matrícula funcional — o
  mecanismo de login é deliberadamente deferido nessas fontes
  (`docs/domain/permissions-matrix.md`; `docs/domain/reconciliation/permissions-reconciliation.md`,
  §7.1). Decisão de produto: a matrícula usada para login DEVE identificar de forma inequívoca uma
  única conta do WMS e DEVE ser tratada como identificador opaco, sem conversão numérica que altere
  sua representação cadastrada (FR-001b). Formato, tamanho e máscara continuam indefinidos, por
  falta de evidência.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Entrar no sistema com credenciais válidas (Priority: P1)

Um funcionário do SAEP já cadastrado no WMS precisa acessar o sistema para realizar qualquer tarefa
operacional. Ele acessa a página de login, informa suas credenciais e, quando elas correspondem a
uma conta ativa, é autenticado e passa a ter acesso à área autenticada do sistema, permanecendo
identificado enquanto navega.

**Why this priority**: sem esta capacidade nenhuma outra funcionalidade do WMS pode presumir usuário
autenticado nem papel aplicável — é o pré-requisito de toda superfície protegida, incluindo a
importação e consulta do catálogo (`specs/001-importacao-catalogo-materiais/spec.md`, FR-045).

**Independent Test**: com um usuário ativo já cadastrado, acessar a página de login, enviar
credenciais válidas e verificar que o sistema concede acesso à área autenticada e mantém o usuário
identificado ao navegar para outra página autenticada, sem exigir nova autenticação.

**Acceptance Scenarios**:

1. **Given** um usuário ativo cadastrado e sem sessão autenticada, **When** ele acessa a página de
   login e informa credenciais válidas, **Then** é autenticado e passa a ter acesso à área
   autenticada do sistema.
2. **Given** um usuário ativo cadastrado, **When** ele informa uma senha incorreta, **Then** o
   sistema recusa o acesso e apresenta uma mensagem de erro genérica.
3. **Given** um identificador de login que não corresponde a nenhum usuário cadastrado, **When**
   alguém tenta autenticar com ele, **Then** o sistema apresenta exatamente a mesma mensagem de erro
   genérica usada para senha incorreta, sem indicar que o login não existe.
4. **Given** um usuário cuja conta está em condição equivalente a inativa, **When** ele tenta
   autenticar com o que seriam credenciais válidas se a conta estivesse ativa, **Then** o sistema
   recusa a autenticação e não concede nenhum acesso.
5. **Given** um usuário autenticado com sucesso, **When** ele navega para outra página da área
   autenticada dentro da mesma sessão, **Then** permanece identificado, sem precisar autenticar
   novamente.
6. **Given** um usuário sem nenhum destino anterior solicitado, **When** ele autentica diretamente
   pela página de login, **Then** é direcionado à Home autenticada mínima.

---

### User Story 2 - Impedir acesso não autenticado a superfícies protegidas (Priority: P2)

Um visitante sem sessão autenticada tenta acessar diretamente uma superfície protegida do WMS (por
exemplo, digitando o endereço). O sistema não pode entregar o conteúdo protegido; em vez disso,
direciona o visitante ao fluxo de autenticação e, depois que ele autentica com sucesso, o devolve ao
destino que havia solicitado originalmente, quando isso for seguro e aplicável.

**Why this priority**: autenticação sem proteção efetiva das superfícies não protege nada — esta
história é o que torna a User Story 1 relevante para segurança, não apenas para identificação.

**Independent Test**: sem sessão autenticada, acessar diretamente o endereço de uma superfície
protegida e verificar que o conteúdo protegido não é entregue e que o visitante é direcionado ao
fluxo de autenticação; depois, autenticar e verificar o retorno ao destino original.

**Acceptance Scenarios**:

1. **Given** um visitante sem sessão autenticada válida, **When** ele tenta acessar uma superfície
   protegida, **Then** o conteúdo protegido não é entregue e o visitante é direcionado ao fluxo de
   autenticação.
2. **Given** um visitante direcionado ao fluxo de autenticação a partir de uma tentativa de acesso a
   uma superfície protegida interna do WMS, **When** ele autentica com sucesso, **Then** é
   devolvido ao destino originalmente solicitado.
3. **Given** um visitante direcionado ao fluxo de autenticação, **When** ele autentica com sucesso,
   **Then** o sistema nunca o encaminha para um endereço fora do próprio WMS, ainda que algum
   parâmetro de retorno tenha sido manipulado.
4. **Given** um destino originalmente solicitado que deixou de existir, não é interno ao WMS, ou não
   é autorizado ao usuário autenticado, **When** ele autentica com sucesso, **Then** é direcionado à
   Home autenticada mínima em vez do destino original.

---

### User Story 3 - Identificar usuário autenticado e papel aplicável (Priority: P3)

Depois de autenticado, o sistema — e as demais funcionalidades do WMS que dependem de autorização —
precisam saber com segurança qual identidade está agindo e qual papel (ou papéis) do catálogo já
definido em `docs/domain/permissions-matrix.md` se aplica a ela, para que decisões de autorização de
outras features possam ser tomadas no servidor.

**Why this priority**: sem essa identificação consultável, nenhuma feature de negócio consegue
verificar autorização no servidor (Constitution, Princípios V e VI); depende da User Story 1 já
estar implementada.

**Independent Test**: autenticar com um usuário que tenha papel(is) atribuído(s) e verificar que a
identidade autenticada e o(s) papel(is) aplicável(is) ficam disponíveis de forma consultável, sem
que o sistema infira ou conceda nenhum papel além dos explicitamente atribuídos.

**Acceptance Scenarios**:

1. **Given** um usuário autenticado com um único papel atribuído, **When** o sistema consulta sua
   identidade, **Then** o papel identificado é exatamente o atribuído, sem herança de nenhum outro
   papel.
2. **Given** um usuário autenticado que ocupa mais de um papel ao mesmo tempo (por exemplo, chefe do
   almoxarifado), **When** o sistema consulta sua identidade, **Then** todos os papéis
   explicitamente atribuídos são identificáveis, sem que um papel conceda capacidades de outro.
3. **Given** um usuário autenticado, **When** o sistema consulta seu setor, **Then** exatamente um
   setor é identificado, consistente com `INV-ORG-001`.

---

### User Story 4 - Encerrar a sessão (Priority: P4)

Um usuário autenticado termina seu trabalho no WMS e encerra a sessão explicitamente, para que o
acesso à área autenticada volte a exigir nova autenticação a partir desse momento.

**Why this priority**: importante para higiene de sessão em dispositivos compartilhados do
almoxarifado, mas depende inteiramente das histórias anteriores já existirem; não bloqueia o uso
diário do sistema por si só.

**Independent Test**: autenticar, encerrar a sessão explicitamente e verificar que uma tentativa
subsequente de acessar superfície protegida exige nova autenticação.

**Acceptance Scenarios**:

1. **Given** um usuário autenticado, **When** ele encerra a sessão explicitamente, **Then** a sessão
   deixa de conceder acesso à área autenticada e ele é imediatamente direcionado à página de login.
2. **Given** uma sessão já encerrada, **When** ocorre uma nova tentativa de acessar uma superfície
   protegida usando essa mesma sessão, **Then** o sistema exige nova autenticação.

---

### Edge Cases

- **Conta desativada durante uma sessão já em andamento**: um usuário autenticado tem sua conta
  alterada para condição equivalente a inativa enquanto ainda possui sessão aberta; a partir desse
  momento ele não pode continuar acessando nem executando nenhuma operação, consistente com
  `INV-AUTH-001` — a invariante se aplica independentemente do mecanismo de autenticação, incluindo
  uma sessão já estabelecida.
- **Usuário já autenticado acessa a página de login diretamente**: em vez de pedir nova autenticação,
  o sistema o direciona à Home autenticada mínima.
- **Destino de retorno pós-login manipulado ou externo**: o sistema nunca trata um endereço fora do
  próprio WMS como destino de retorno válido após autenticação (proteção contra redirecionamento
  aberto); nesse caso o usuário é direcionado à Home autenticada mínima, nunca ao endereço externo.
- **Destino de retorno que não existe mais ou que o usuário autenticado não pode acessar**: o sistema
  não presume que devolver a esse destino é seguro; em vez de tentar concluir o retorno, direciona o
  usuário à Home autenticada mínima.
- **Logout sem sessão autenticada ativa**: solicitar encerramento de sessão quando já não há sessão
  válida não pode falhar de forma que confunda o usuário nem revele informação sensível.
- **Tentativas repetidas de autenticação com credenciais inválidas**: fora de escopo desta feature
  (ver Fora de Escopo), a menos que evidência futura mostre necessidade concreta.

## Requirements *(mandatory)*

### Functional Requirements

#### Login

- **FR-001**: O sistema DEVE apresentar uma página de login acessível a qualquer visitante sem
  sessão autenticada válida.
- **FR-001a**: O sistema DEVE solicitar, nesta primeira versão, a matrícula funcional do SAEP como
  identificador de login, informada junto da senha. Esta decisão não impede uma futura migração para
  outro mecanismo (SSO, e-mail institucional, Active Directory, entre outros).
- **FR-001b**: A matrícula funcional usada para autenticação DEVE identificar de forma inequívoca
  uma única conta do WMS e DEVE ser armazenada como texto, preservando a representação cadastrada,
  incluindo zeros à esquerda e demais caracteres que façam parte dela. O sistema NÃO DEVE
  convertê-la para valor numérico, aplicar máscara, completar, decompor ou reformular seus
  caracteres. O campo de entrada do login segue a canonicalização técnica do `AuthenticationForm`
  nativo do Django (remoção de espaços nas pontas e normalização Unicode NFKC) — comportamento de
  framework, aplicado à entrada submetida, que não altera a representação já cadastrada e é
  irrelevante para matrículas ASCII. Formato, tamanho e máscara da matrícula não são definidos por
  esta spec.
- **FR-002**: O sistema DEVE autenticar o visitante quando as credenciais informadas corresponderem
  a um usuário cadastrado em condição ativa.
- **FR-003**: O sistema DEVE recusar a autenticação, com a mesma mensagem de erro genérica em todos
  os casos, quando as credenciais não corresponderem a um usuário ativo cadastrado — seja porque o
  login não existe, porque a senha está incorreta, ou porque o usuário existe mas está em condição
  equivalente a inativa — sem revelar qual dessas condições ocorreu (Constitution, Princípio VI;
  evita enumeração de usuário).
- **FR-004**: O sistema NÃO DEVE conceder nenhum acesso a um usuário cuja conta esteja em condição
  equivalente a inativa, mesmo que as demais credenciais estejam corretas, consistente com
  `INV-AUTH-001`.
- **FR-005**: O sistema DEVE manter o usuário identificado durante sua sessão após autenticação bem-
  sucedida, sem exigir nova autenticação a cada navegação dentro da área autenticada.
- **FR-005a**: O sistema DEVE oferecer uma Home autenticada mínima — superfície autenticada sem
  funcionalidades de negócio de outra feature (ex.: catálogo, importação SCPI), alinhada a
  `DESIGN.md` — como destino autenticado padrão, usada sempre que não houver destino anterior
  aplicável: ausência de destino anterior, destino inexistente/inválido, destino não autorizado ao
  usuário, ou usuário já autenticado acessando a página de login (ver FR-010a, FR-012).
- **FR-006**: O sistema DEVE impedir que uma sessão autenticada continue concedendo acesso ou
  execução de operações a um usuário cuja conta deixou de estar ativa, mesmo que a sessão já
  estivesse em andamento antes da desativação.
- **FR-007**: O sistema DEVE apresentar mensagem de erro clara ao usuário quando a autenticação
  falhar, sem expor detalhes internos sensíveis (stack trace, consulta ao banco, caminho de arquivo
  ou dado de outro usuário), conforme Constitution, Princípio VI.

#### Acesso protegido

- **FR-008**: O sistema DEVE impedir que um visitante sem sessão autenticada válida receba o
  conteúdo de qualquer superfície protegida.
- **FR-009**: O sistema DEVE direcionar o visitante não autenticado que tentar acessar uma superfície
  protegida ao fluxo de autenticação.
- **FR-010**: O sistema DEVE, após autenticação bem-sucedida originada de uma tentativa de acesso a
  superfície protegida, devolver o usuário ao destino originalmente solicitado somente quando esse
  destino for, simultaneamente: (a) uma superfície interna do próprio WMS; (b) ainda existente/
  válida; e (c) autorizada ao usuário autenticado.
- **FR-010a**: O sistema DEVE, quando o destino originalmente solicitado não atender a alguma das
  condições de FR-010, direcionar o usuário à Home autenticada mínima (FR-005a) em vez de tentar
  concluir o retorno.
- **FR-011**: O sistema NÃO DEVE, em nenhuma circunstância, usar o destino de retorno pós-login para
  encaminhar o usuário a um endereço fora do próprio WMS (proteção contra redirecionamento aberto).
- **FR-012**: O sistema DEVE, quando um usuário já autenticado acessar a página de login diretamente,
  direcioná-lo à Home autenticada mínima em vez de solicitar nova autenticação.

#### Identificação de usuário e papel

- **FR-013**: O sistema DEVE, após autenticação, identificar de forma inequívoca qual usuário
  cadastrado está autenticado.
- **FR-014**: O sistema DEVE tornar consultável, para as demais funcionalidades do WMS, o papel ou
  papéis aplicáveis à identidade autenticada, restritos ao catálogo já canônico em
  `docs/domain/permissions-matrix.md` (`ROLE-REQUESTER`, `ROLE-SECTOR-ASSISTANT`,
  `ROLE-SECTOR-HEAD`, `ROLE-WAREHOUSE-STAFF`, `ROLE-WAREHOUSE-HEAD`, `ROLE-AUDITOR`,
  `ROLE-SYSTEM-ADMIN`); esta feature não define nem redefine papel algum.
- **FR-015**: O sistema NÃO DEVE inferir nem conceder à identidade autenticada nenhum papel além dos
  explicitamente atribuídos a ela, e um papel identificado NÃO DEVE conceder implicitamente as
  capacidades de outro papel que a mesma identidade também ocupe.
- **FR-016**: O sistema DEVE tornar consultável exatamente um setor por usuário autenticado,
  consistente com `INV-ORG-001`, como pré-condição para o escopo "próprio setor" usado por
  funcionalidades futuras de autorização.
- **FR-016a**: O sistema DEVE conceder `ROLE-REQUESTER` a toda identidade de negócio no momento de
  sua criação, como atribuição explícita e persistida, atômica com a criação da conta
  (`docs/domain/permissions-matrix.md`, Notas de composição). Essa concessão NÃO DEVE ser inferida
  em tempo de consulta a partir de `is_active` nem de qualquer outro atributo — permanece coerente
  com FR-015. A conta técnica de superusuário do Django NÃO é identidade de negócio e NÃO DEVE
  receber `ROLE-REQUESTER` nem nenhum outro papel (`permissions-matrix.md`, regras 7–8). Desativar
  uma conta NÃO DEVE remover seus papéis.

#### Organização: ativação de setor

> Estes requisitos existem porque o próprio bootstrap desta feature cria setores e concede
> `ROLE-SECTOR-HEAD` (ver Fora de Escopo). Sem eles, a feature produziria estados que violam
> `INV-ORG-002`, invariante CRÍTICA. Esta feature não oferece administração de setores como
> funcionalidade de produto — apenas impede que seu próprio caminho de provisionamento quebre a
> invariante.

- **FR-019**: Um setor recém-criado DEVE nascer inativo, de modo que sua criação nunca produza, por
  si só, um setor ativo sem chefe ativo.
- **FR-020**: O sistema DEVE permitir a ativação de um setor somente quando existir exatamente um
  chefe ativo (`ROLE-SECTOR-HEAD`) pertencente ao próprio setor, consistente com `INV-ORG-002` e
  `INV-ORG-003`.
- **FR-021**: O sistema DEVE impedir qualquer operação sobre usuário ou papel que deixe um setor
  ativo sem exatamente um chefe ativo — incluindo desativar o chefe, transferi-lo para outro setor
  e remover-lhe o papel de chefe.
- **FR-022**: O sistema DEVE impedir a atribuição de um segundo chefe a um setor que já possua um
  chefe ativo.
- **FR-023**: As operações de FR-019 a FR-022 DEVEM ser atômicas: uma operação recusada não pode
  deixar estado parcialmente alterado.

#### Logout

- **FR-017**: O sistema DEVE permitir que o usuário autenticado encerre sua sessão explicitamente.
- **FR-017a**: O sistema DEVE, imediatamente após o encerramento explícito da sessão, direcionar o
  usuário à página de login.
- **FR-018**: O sistema DEVE, após o encerramento explícito da sessão, exigir nova autenticação para
  qualquer tentativa subsequente de acessar uma superfície protegida através dela.

### Key Entities

- **Usuário (conta autenticável)**: identidade que pode autenticar-se no WMS. Pertence a exatamente
  um setor (`INV-ORG-001`), possui condição ativa ou equivalente a inativa que determina se pode
  autenticar e continuar operando, e possui um ou mais papéis atribuídos do catálogo canônico. Esta
  feature consome essa identidade; não a cria, edita nem administra.
- **Sessão autenticada**: vínculo temporário entre um usuário autenticado e o acesso concedido a
  partir do login, existente entre a autenticação bem-sucedida e o encerramento explícito (logout)
  ou a perda de validade por outra condição (por exemplo, a conta associada deixar de estar ativa).
- **Papel**: um dos papéis já canônicos definidos em `docs/domain/permissions-matrix.md`, atribuído a
  um usuário. Não é criado, redefinido, nem gerenciado por esta feature — apenas consultado a partir
  da identidade autenticada.
- **Home autenticada mínima**: superfície autenticada padrão desta feature, sem funcionalidades de
  negócio de outra feature (não antecipa catálogo, importação ou qualquer superfície de
  `001-importacao-catalogo-materiais`) e alinhada a `DESIGN.md`. Serve como destino ao autenticar
  sem um destino anterior aplicável e como fallback sempre que o retorno ao destino original não for
  seguro ou aplicável (FR-005a, FR-010a, FR-012).

## Regras canônicas aplicáveis

### Permissões

- Esta feature não cria nem redefine nenhuma capability de `docs/domain/permissions-matrix.md`. Ela
  consome o catálogo de papéis já canônico (`ROLE-REQUESTER`, `ROLE-SECTOR-ASSISTANT`,
  `ROLE-SECTOR-HEAD`, `ROLE-WAREHOUSE-STAFF`, `ROLE-WAREHOUSE-HEAD`, `ROLE-AUDITOR`,
  `ROLE-SYSTEM-ADMIN`) para expor identidade e papel autenticados (FR-013 a FR-016), sem decidir
  quem pode executar qual capability — essa decisão permanece em cada feature de negócio que a
  consumir.

### Invariantes

- `INV-AUTH-001` — usuário inativo não pode acessar nem executar nenhuma operação, qualquer que seja
  o mecanismo de autenticação (FR-002 a FR-004, FR-006).
- `INV-ORG-001` — usuário pertence a um único setor; esta feature consome essa invariante como
  pré-condição para o escopo "próprio setor" usado por autorização futura (FR-016).
- `INV-ORG-002` — todo setor ativo possui exatamente um chefe ativo do próprio setor, e nenhuma
  operação sobre usuário ou setor pode deixar um setor ativo sem chefe ativo. Como o bootstrap
  desta feature escreve em setor, usuário e papel, a invariante é **preservada aqui**, não adiada
  (FR-019 a FR-023).
- `INV-ORG-003` — um chefe responde por um único setor; preservada estruturalmente, já que a
  chefia deriva de `ROLE-SECTOR-HEAD` combinado ao setor único do próprio usuário (`INV-ORG-001`),
  nunca de um vínculo separado.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Um usuário ativo cadastrado consegue autenticar-se e acessar a área autenticada em uma
  única tentativa, informando apenas suas credenciais, sem etapa adicional.
- **SC-002**: 100% das tentativas de acesso a superfície protegida sem sessão autenticada válida são
  impedidas e direcionadas ao fluxo de autenticação, sem exceção.
- **SC-003**: 100% das tentativas de autenticação recusadas — senha incorreta, login inexistente ou
  conta inativa — apresentam a mesma mensagem de erro genérica, sem diferença perceptível entre as
  causas.
- **SC-004**: Nenhuma conta em condição inativa consegue autenticar ou continuar operando durante uma
  sessão já aberta, em 100% dos casos verificados.
- **SC-005**: Em 100% dos casos em que o destino original solicitado é uma superfície interna do
  WMS, ainda existente e autorizada ao usuário autenticado, ele retorna a esse destino imediatamente
  após autenticação bem-sucedida, sem etapa de navegação adicional; em qualquer outro caso, é
  direcionado à Home autenticada mínima.
- **SC-006**: Nenhum caminho do sistema permite, através do fluxo de login, encaminhar o usuário
  autenticado para um endereço fora do próprio WMS.
- **SC-007**: Em 100% dos casos, após o usuário encerrar a sessão explicitamente, uma tentativa
  subsequente de acessar superfície protegida exige nova autenticação.
- **SC-008**: Em 100% dos casos, imediatamente após o logout explícito, o usuário é apresentado à
  página de login.

## Fora de Escopo

- Administração de usuários, papéis e setores como **funcionalidade de produto** — telas de
  gestão, fluxos de manutenção e as capabilities `PERM-USER-MANAGE`/`PERM-SECTOR-MANAGE`, já
  registradas na matriz de permissões mas ainda não implementadas.

  **Ressalva necessária**: esta feature precisa provisionar as primeiras contas e o primeiro setor
  para que o login exista (ver Assumptions e `quickstart.md`), e faz isso pelo Django Admin, que é
  ferramenta técnica de bootstrap. Como esse caminho **escreve** em setor, usuário e papel, ele
  está sujeito a `INV-ORG-002`/`INV-ORG-003` como qualquer outro caminho de escrita. Por isso
  FR-019 a FR-023 fazem parte do escopo: não para oferecer administração de setores, mas para
  impedir que o próprio bootstrap produza um estado que viole uma invariante CRÍTICA.
- Recuperação de senha, autoatendimento de conta, primeiro acesso ou provisionamento de credencial.
- Escolha do mecanismo de autenticação (matrícula, e-mail, SSO) além do necessário para descrever o
  comportamento observável de login desta feature.
- Qualquer regra de autorização específica de uma feature de negócio (por exemplo, quem aprova
  requisição, quem opera estoque) — esta feature apenas estabelece que autenticação e papel existem
  e são consultáveis, sem decidir quem pode fazer o quê em outra feature.
- Autenticação multifator, políticas de expiração ou rotação de senha, e limitação de tentativas de
  login (throttling), sem evidência de necessidade concreta.
- Sessão única por usuário ou encerramento remoto de sessões em outros dispositivos.

## Assumptions

- O identificador de login nesta primeira versão é a matrícula funcional do SAEP (FR-001a); a
  escolha de um mecanismo diferente no futuro (SSO, e-mail institucional, Active Directory, etc.) —
  lacuna já registrada em `docs/domain/permissions-matrix.md` — não é impedida por este requisito e
  não faz parte desta spec.
- Enquanto a funcionalidade própria de administração de usuários/papéis/setores não existir, presume-
  se que usuários, seus papéis e seu vínculo a um setor já existem por algum meio administrativo
  fora do escopo desta spec (por exemplo, um mecanismo administrativo de manutenção); esta feature
  consome essas identidades já existentes, não as cria.
- "Superfície interna" para fins de retorno pós-login (FR-010) é qualquer rota do próprio WMS; um
  endereço fora do WMS nunca é tratado como destino de retorno válido (FR-011).
- Sessão autenticada é de uso individual por dispositivo/navegador; não há, nesta feature, exigência
  de sessão única por usuário nem proibição de múltiplos acessos simultâneos com a mesma conta.
- A verificação de que uma conta permanece ativa durante uma sessão em andamento (FR-006) ocorre em
  prazo compatível com o uso operacional diário do sistema — tipicamente na primeira interação
  seguinte à desativação —, sem exigir revogação instantânea entre múltiplos processos ou
  servidores.
- Um usuário autenticado que acessa diretamente a página de login (FR-012) é redirecionado à Home
  autenticada mínima (FR-005a), em vez de reautenticar — comportamento de conveniência, não uma
  exigência de segurança desta feature.
