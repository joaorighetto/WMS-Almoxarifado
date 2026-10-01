# Feature Specification: Administração de Usuários, Papéis e Setores

**Feature Branch**: `claude/005-administracao-usuarios-setores`

**Feature Directory**: `specs/005-administracao-usuarios-setores`

**Created**: 2026-10-01

**Status**: Draft

**Input**: User description: "Feature ORG do ROADMAP.md — Administração de usuários, papéis e
setores. Resultado: manter identidades e sua organização com chefia válida e atribuições
explícitas. Inclui: gestão pelo administrador de sistema; vínculo setorial; atribuição dos papéis
canônicos; manutenção das invariantes organizacionais; entrega e redefinição de credenciais pelo
administrador; troca da própria senha pelo usuário autenticado. Não inclui: redefinir papéis;
conceder poderes operacionais implícitos; gestão de estoque; redefinir o login; recuperação de
senha sem o administrador; e-mail, notificações ou SSO. Dependências: O: 002 (entregue); R: antes
do uso amplo de REQ, sem bloqueá-la. Regras canônicas: PERM-USER-MANAGE, PERM-SECTOR-MANAGE;
INV-ORG-001 a INV-ORG-006, INV-AUTH-001. Preservar FR-016a e FR-019 a FR-023 da 002. Decisões de
produto D-01 a D-27 do brainstorming de 2026-10-01 tratadas como requisitos já decididos; D-19 a
D-21 são compartilhadas com REQ e aqui só se declara o lado de ORG do contrato. Pendências da
seção 8 do brainstorming ficam para o clarify."

## Origem das decisões

Os requisitos desta spec codificam as decisões de produto D-01 a D-27, tomadas pelo dono do produto
no [brainstorming de 2026-10-01](../../docs/brainstorming/2026-10-01-org-administracao-usuarios-setores.md).
Aquele documento é insumo, não fonte normativa: as regras transversais que ele produziu já estão em
`docs/domain/permissions-matrix.md` e `docs/domain/invariants-matrix.md` (versão 1.2), que prevalecem
sobre ele e sobre esta spec. As referências "(D-nn)" abaixo servem só para rastreabilidade.

Pelas regras vigentes da 002, não é possível trocar o chefe de um setor ativo em passos separados:
remover o chefe atual é recusado por FR-021 e dar o papel ao novo antes é recusado por FR-022. Esta
spec resolve isso com uma operação própria de substituição, sem alterar aqueles requisitos.

## Clarifications

### Sessão 2026-10-01

- Q: Depois que o usuário define a própria senha, obrigatória por causa da senha provisória, para
  onde o sistema deve levá-lo? → A: Ao destino solicitado antes de autenticar, quando ele atende às
  condições de FR-010 da 002; caso contrário, à Home autenticada mínima (FR-010a da 002) (FR-034).
- Q: A senha provisória deve deixar de valer se não for usada dentro de um prazo? → A: Sim, expira 7
  dias depois de gerada se não tiver sido usada para definir a senha; vencida, é recusada com a
  mensagem genérica de login da 002, e o administrador redefine (FR-035).
- Q: Que regras o nome completo do usuário deve obedecer, além de ser obrigatório? → A: Texto livre,
  não vazio depois de removidos os espaços nas pontas; nomes repetidos são permitidos; o tamanho
  máximo é limite técnico do plan (FR-006).
- Q: Que regras a senha escolhida pelo usuário deve cumprir, na definição obrigatória e na troca
  voluntária? → A: A política vigente no projeto: no mínimo 8 caracteres, não ser senha comum, não
  ser só números e não se parecer com os dados do próprio usuário (FR-038).
- Q: O aceite da feature deve incluir uma meta de tempo para cadastrar um usuário? → A: Não; a meta
  de tempo foi retirada, e o SC-001 (operações cotidianas sem o caminho técnico) basta para um fluxo
  raro e de um único operador.

## User Scenarios & Testing *(mandatory)*

Nos cenários abaixo, "administrador" é uma identidade de negócio ativa com `ROLE-SYSTEM-ADMIN`. ETA
e Laboratório são setores comuns; Almoxarifado é o setor designado como tal (`INV-ORG-004`).

### User Story 1 - Cadastrar usuário e entregar a credencial (Priority: P1)

O administrador cadastra um funcionário novo informando matrícula, nome completo, setor e os papéis
que ele ocupa além de requisitante. O sistema cria a conta ativa, já com `ROLE-REQUESTER`, e gera uma
senha provisória que aparece uma única vez ao administrador, que a entrega pessoalmente. No primeiro
acesso, o funcionário só consegue definir a própria senha; depois disso usa o sistema normalmente.

**Why this priority**: é o que tira a manutenção cotidiana de identidades do caminho técnico de
provisionamento. Sem ela, nenhum funcionário novo chega ao WMS, e as demais histórias pressupõem
contas existentes.

**Independent Test**: com um administrador e um setor existentes, cadastrar um usuário, anotar a
senha provisória exibida, autenticar com ela, verificar que só a definição de senha está disponível,
definir a senha e verificar o acesso normal com a nova senha.

**Acceptance Scenarios**:

1. **Given** o administrador e o setor ETA, **When** ele cadastra a matrícula 1234, o nome completo
   e o setor ETA, sem papéis adicionais, **Then** a conta nasce ativa, no setor ETA, com exatamente
   `ROLE-REQUESTER`, e uma senha provisória é exibida uma única vez.
2. **Given** um usuário já cadastrado com a matrícula 1234, **When** o administrador tenta cadastrar
   outro usuário com a matrícula 1234, **Then** o cadastro é recusado por matrícula repetida e nada é
   criado.
3. **Given** um cadastro sem nome completo ou sem setor, **When** o administrador confirma, **Then**
   o cadastro é recusado, indicando o dado que falta.
4. **Given** a ETA ativa com chefe, **When** o administrador cadastra um usuário da ETA com
   `ROLE-SECTOR-HEAD`, **Then** o cadastro é recusado e indica usar a substituição de chefia.
5. **Given** um cadastro no Laboratório, **When** o administrador escolhe `ROLE-WAREHOUSE-STAFF` ou
   `ROLE-WAREHOUSE-HEAD`, **Then** o cadastro é recusado (`INV-ORG-005`).
6. **Given** um usuário recém-criado, **When** autentica com a senha provisória, **Then** só consegue
   definir a própria senha antes de acessar qualquer outra superfície; depois disso, usa a nova senha
   normalmente.
7. **Given** um usuário com senha provisória que tentou abrir uma superfície interna que lhe é
   autorizada, **When** autentica e define a própria senha, **Then** é levado a essa superfície; sem
   destino anterior aplicável, é levado à Home autenticada mínima.
8. **Given** o administrador que já fechou a tela onde a senha provisória apareceu, **When** volta à
   ficha do usuário, **Then** a senha não é exibida de novo em lugar nenhum; para entregar outra, ele
   usa a redefinição (User Story 6).

---

### User Story 2 - Consultar usuários, setores e histórico organizacional (Priority: P2)

O administrador localiza usuários e setores, abre a ficha de cada um e vê seus dados atuais e o
histórico de tudo o que mudou neles: quem alterou, quando e o que era antes.

**Why this priority**: todas as demais operações começam por encontrar a pessoa ou o setor certo, e
o histórico é a forma de investigar uma atribuição depois do fato (Constitution, Princípio IV).

**Independent Test**: com usuários e setores existentes e algumas operações já feitas, buscar por
nome parcial, matrícula, setor, situação e papel; abrir a ficha de um usuário e de um setor e
conferir dados atuais e histórico.

**Acceptance Scenarios**:

1. **Given** usuários em vários setores, **When** o administrador busca por parte do nome ou pela
   matrícula, **Then** a lista mostra os usuários correspondentes com matrícula, nome, setor,
   situação e papéis.
2. **Given** a lista de usuários, **When** o administrador filtra por setor, situação ou papel,
   **Then** só os usuários que atendem a todos os filtros aplicados aparecem.
3. **Given** um usuário que já foi transferido e teve papéis alterados, **When** o administrador abre
   sua ficha, **Then** vê os dados atuais e o histórico em ordem cronológica, cada evento com autor,
   momento e valores anteriores e novos.
4. **Given** um setor que já esteve ativo e foi desativado, **When** o administrador abre sua ficha,
   **Then** vê situação, chefe, membros e o histórico, que mostra que o setor já esteve ativo.
5. **Given** um usuário sem `ROLE-SYSTEM-ADMIN`, **When** tenta acessar a lista, uma ficha ou o
   histórico organizacional, **Then** o acesso é negado no servidor.

---

### User Story 3 - Manter dados, papéis e vínculo setorial (Priority: P3)

O administrador corrige o nome ou a matrícula de um usuário, concede e remove papéis respeitando as
regras de composição, e transfere a pessoa de setor, sabendo antes quais papéis presos ao setor de
origem serão removidos.

**Why this priority**: são os ajustes mais frequentes depois do cadastro; sem eles, mudanças reais de
função ou de lotação dependem do caminho técnico.

**Independent Test**: editar nome e matrícula de um usuário; conceder e remover papéis permitidos e
tentar os proibidos; transferir um auxiliar para outro setor e conferir a lista prévia e o resultado.

**Acceptance Scenarios**:

1. **Given** a ETA ativa com chefe, **When** o administrador tenta remover `ROLE-SECTOR-HEAD` da chefe
   ou conceder esse papel a outro membro, **Then** a operação é recusada com o motivo e a indicação de
   usar a substituição.
2. **Given** um usuário do Laboratório, **When** o administrador tenta conceder
   `ROLE-WAREHOUSE-STAFF`, **Then** a operação é recusada (`INV-ORG-005`).
3. **Given** um membro do Almoxarifado que não é o chefe, **When** o administrador tenta conceder
   `ROLE-WAREHOUSE-HEAD`, **Then** a operação é recusada: esse papel só acompanha a chefia do
   Almoxarifado.
4. **Given** Ana, auxiliar da ETA, **When** é transferida para o Laboratório, **Then** a confirmação
   lista a remoção de `ROLE-SECTOR-ASSISTANT`, e depois dela Ana pertence ao Laboratório só com os
   papéis não presos ao setor.
5. **Given** a chefe da ETA ativa, **When** o administrador tenta transferi-la, **Then** a operação é
   recusada e indica substituir antes.
6. **Given** um usuário com a matrícula digitada errada, **When** o administrador a corrige para uma
   matrícula ainda não usada, **Then** a nova matrícula passa a valer e o histórico registra a
   anterior; para uma matrícula já usada, a correção é recusada.
7. **Given** um usuário ativo, **When** o administrador tenta remover `ROLE-REQUESTER`, **Then** a
   operação é recusada.

---

### User Story 4 - Substituir o chefe de um setor ativo (Priority: P4)

O administrador troca o chefe de um setor ativo, de forma definitiva ou para cobrir férias e
licenças, numa única operação: o novo chefe recebe a chefia e o anterior a perde ao mesmo tempo. No
Almoxarifado, as atribuições exclusivas de estoque passam junto.

**Why this priority**: é a única forma de trocar a chefia de um setor ativo sem violar
`INV-ORG-002`, e a chefia define quem autoriza requisições do setor e, no Almoxarifado, quem detém
as atribuições exclusivas de estoque.

**Independent Test**: substituir o chefe de um setor comum e do Almoxarifado; tentar substituir por
alguém de outro setor; disparar duas substituições concorrentes no mesmo setor.

**Acceptance Scenarios**:

1. **Given** a ETA ativa com a chefe Maria e o membro ativo Pedro, **When** o administrador substitui
   Maria por Pedro, **Then** Pedro é o único chefe ativo da ETA, Maria continua ativa na ETA sem
   `ROLE-SECTOR-HEAD` e com os demais papéis, e o histórico registra a substituição com autor e
   momento.
2. **Given** um usuário de outro setor, **When** o administrador tenta escolhê-lo como novo chefe da
   ETA, **Then** a operação é recusada e indica transferir antes.
3. **Given** o Almoxarifado ativo com o chefe João, **When** o administrador o substitui por Carla,
   membro ativo com `ROLE-WAREHOUSE-STAFF`, **Then** Carla passa a ter `ROLE-SECTOR-HEAD` e
   `ROLE-WAREHOUSE-HEAD`, João mantém só `ROLE-WAREHOUSE-STAFF` dentre os papéis de almoxarifado, e
   em nenhum momento existem dois usuários ativos com `ROLE-WAREHOUSE-HEAD`.
4. **Given** o Almoxarifado ativo e um membro ativo sem `ROLE-WAREHOUSE-STAFF`, **When** o
   administrador o escolhe como novo chefe, **Then** ele recebe também `ROLE-WAREHOUSE-STAFF` na
   mesma operação, e a confirmação mostra isso antes.
5. **Given** duas substituições concorrentes do chefe do mesmo setor, **When** ambas são confirmadas,
   **Then** uma é aplicada e a outra é recusada por ter sido avaliada sobre o novo estado; o setor
   nunca fica com zero ou dois chefes.

---

### User Story 5 - Desativar e reativar usuários (Priority: P5)

O administrador desativa quem deixa de trabalhar no SAEP ou não deve mais acessar o WMS, preservando
seus papéis para rastreabilidade, e reativa a conta quando cabível, revisando quais papéis voltam a
valer.

**Why this priority**: retirar acesso é uma necessidade de segurança; a reativação com revisão evita
devolver automaticamente um poder que já não corresponde à função real.

**Independent Test**: desativar um usuário com sessão aberta e verificar a perda de acesso; tentar
desativar um chefe de setor ativo e o último administrador; reativar com papéis preservados,
desmarcando alguns e tentando manter um que viola regra.

**Acceptance Scenarios**:

1. **Given** um usuário com sessão aberta, **When** o administrador o desativa, **Then** a próxima
   interação dele é recusada (`INV-AUTH-001`) e seus papéis continuam registrados.
2. **Given** a chefe da ETA ativa, **When** o administrador tenta desativá-la, **Then** a operação é
   recusada e indica substituir antes.
3. **Given** o único administrador ativo, **When** ele tenta desativar a própria conta ou retirar de
   si `ROLE-SYSTEM-ADMIN`, **Then** a operação é recusada.
4. **Given** um funcionário desativado com `ROLE-WAREHOUSE-STAFF` preservado, **When** o
   administrador o reativa, **Then** a tela lista esse papel para revisão, e o resultado é exatamente
   o que foi confirmado.
5. **Given** um ex-chefe inativo com `ROLE-SECTOR-HEAD` preservado num setor que já tem outro chefe,
   **When** o administrador tenta reativá-lo mantendo esse papel, **Then** a reativação é recusada com
   o motivo; desmarcando o papel, ela prossegue.
6. **Given** a revisão de reativação, **When** o administrador tenta desmarcar `ROLE-REQUESTER`,
   **Then** isso não é aceito: a conta reativada sempre mantém `ROLE-REQUESTER`.

---

### User Story 6 - Redefinir a senha e trocar a própria senha (Priority: P6)

Quando um funcionário esquece a senha, o administrador a redefine: o sistema gera nova senha
provisória, exibida uma vez, e encerra as sessões abertas da conta. Qualquer usuário autenticado
também pode trocar a própria senha quando quiser, confirmando a atual.

**Why this priority**: sem recuperação por e-mail, a redefinição pelo administrador é o único
caminho para quem perdeu a senha; a troca voluntária permite ao usuário reagir a uma suspeita de
exposição sem depender de ninguém.

**Independent Test**: redefinir a senha de um usuário com sessão aberta e verificar perda da sessão e
definição obrigatória no próximo acesso; trocar a própria senha com a senha atual certa e errada.

**Acceptance Scenarios**:

1. **Given** um usuário com sessão aberta, **When** o administrador redefine sua senha, **Then** a
   sessão deixa de valer, a senha provisória só aparece uma vez para o administrador, e o próximo
   acesso exige definir a própria senha.
2. **Given** um usuário autenticado, **When** troca a própria senha informando a atual corretamente,
   **Then** a nova passa a valer, as outras sessões dele são encerradas, a sessão em uso continua e o
   histórico registra o evento sem a senha.
3. **Given** um usuário autenticado, **When** tenta trocar a própria senha informando a atual
   errada, **Then** nada muda.
4. **Given** um usuário com senha provisória, **When** tenta definir como nova senha a própria senha
   provisória, **Then** a definição é recusada.
5. **Given** uma senha provisória gerada há mais de 7 dias e nunca usada para definir a senha,
   **When** o usuário tenta autenticar com ela, **Then** recebe a mesma mensagem genérica de falha de
   login, e a ficha do usuário mostra ao administrador que a credencial provisória venceu.

---

### User Story 7 - Administrar setores (Priority: P7)

O administrador cria setores, corrige seus nomes, designa o chefe de um setor ainda inativo, ativa o
setor quando ele tem chefia válida e desativa setores que deixaram de existir, depois de transferir
ou desativar seus membros.

**Why this priority**: setores mudam com menos frequência que pessoas, e os existentes vêm do
provisionamento; ainda assim, sem esta história a estrutura organizacional fica congelada no caminho
técnico.

**Independent Test**: criar um setor, tentar repetir o nome com outra caixa e espaços, designar
chefe, ativar, tentar desativar com membros ativos, transferir os membros, desativar; tentar
desativar o Almoxarifado.

**Acceptance Scenarios**:

1. **Given** o administrador, **When** cria o setor "Laboratório", **Then** o setor nasce inativo
   (FR-019 da 002).
2. **Given** um setor chamado "ETA", **When** o administrador cria ou renomeia outro setor como
   " eta ", **Then** a operação é recusada por nome repetido.
3. **Given** um setor inativo sem chefe e um membro ativo dele, **When** o administrador concede
   `ROLE-SECTOR-HEAD` a esse membro e depois ativa o setor, **Then** o setor fica ativo com
   exatamente um chefe ativo.
4. **Given** um setor inativo sem chefe ativo, **When** o administrador tenta ativá-lo, **Then** a
   ativação é recusada (FR-020 da 002).
5. **Given** um setor com chefe e mais um membro ativo, **When** o administrador tenta desativá-lo,
   **Then** a operação é recusada; depois de transferido o membro, a desativação é aceita.
6. **Given** o setor Almoxarifado ativo, **When** o administrador tenta desativá-lo, **Then** a
   operação é sempre recusada.
7. **Given** o setor Almoxarifado inativo, **When** o administrador designa seu chefe, **Then** o
   designado recebe `ROLE-SECTOR-HEAD` e `ROLE-WAREHOUSE-HEAD` juntos, e também
   `ROLE-WAREHOUSE-STAFF` se ainda não o tiver.

---

### Integridade em todos os caminhos de escrita

Este cenário não forma uma história própria; vale para todas as anteriores.

1. **Given** uma alteração de papel feita pelo caminho técnico de manutenção, fora das telas de ORG,
   **When** ela é salva, **Then** as mesmas regras se aplicam e o mesmo evento de histórico é gerado.

### Edge Cases

- **Senha provisória perdida antes da entrega**: a senha não é recuperável depois de exibida; o
  administrador redefine a senha, o que gera outra provisória (FR-031, FR-033).
- **Administrador redefine a própria senha**: é permitido (D-15); como a redefinição encerra as
  sessões da conta, inclusive a que está em uso, ele volta a autenticar com a senha provisória e
  define a própria antes de continuar. Para trocar sem isso, usa a troca voluntária (FR-037).
- **Mais de um administrador ativo**: as proteções de FR-022 só se aplicam ao último administrador
  ativo; com outro administrador ativo, retirar `ROLE-SYSTEM-ADMIN` de si é permitido. Desativar a
  própria conta continua sempre recusado.
- **Transferência de chefe de setor inativo**: permitida; o chefe perde `ROLE-SECTOR-HEAD` na mesma
  operação e o setor de origem fica sem chefe, o que só impede sua futura ativação até nova
  designação. No Almoxarifado inativo, perde também `ROLE-WAREHOUSE-HEAD` e `ROLE-WAREHOUSE-STAFF`.
- **Transferência de usuário inativo**: segue as mesmas regras; os papéis presos ao setor de origem,
  ainda que preservados pela desativação, são removidos e listados antes da confirmação.
- **Transferência para o Almoxarifado**: não concede papel nenhum; papéis de almoxarifado são
  concedidos depois, numa operação própria.
- **Transferência para o próprio setor atual**: não é uma transferência e é recusada.
- **Cadastro ou transferência para setor inativo**: permitidos (D-18); membros de setor inativo
  continuam podendo acessar o WMS conforme os próprios papéis.
- **Desativação de chefe de setor inativo**: permitida; `INV-ORG-002` só exige chefe para setor
  ativo.
- **Reativação de ex-chefe do Almoxarifado com outro chefe ativo**: manter `ROLE-SECTOR-HEAD` ou
  `ROLE-WAREHOUSE-HEAD` é recusado (`INV-ORG-002`, `INV-ORG-006`); ambos precisam ser desmarcados.
- **Reativação em setor inativo**: permitida; se o setor não tiver chefe, o reativado pode voltar
  como chefe desse setor inativo mantendo `ROLE-SECTOR-HEAD`.
- **Desativação de setor com membros inativos**: só membros ativos além do chefe impedem a
  desativação; membros inativos permanecem vinculados ao setor.
- **Conta técnica vinculada a um setor**: o vínculo da conta técnica é só um requisito técnico e não
  a torna membro. Ela não impede a desativação do setor e não aparece nas listas nem nas fichas
  (FR-004, FR-028).
- **Renomear o setor Almoxarifado**: permitido como qualquer setor; a designação de Almoxarifado não
  depende do nome e não muda (`INV-ORG-004`).
- **Operações sobre o mesmo usuário ou setor ao mesmo tempo**: são serializadas; a segunda é avaliada
  sobre o resultado da primeira e recusada se tiver ficado inválida (por exemplo, transferir um
  usuário enquanto ele é feito chefe).
- **Operação que não muda nada** (salvar o mesmo nome, conceder papel já atribuído): não gera evento
  de histórico.
- **Senha provisória vence com sessão aberta**: quem autenticou com a provisória e não definiu a
  própria senha antes do vencimento perde a sessão na interação seguinte e não consegue mais
  definir a senha com ela; precisa de nova redefinição (FR-035).
- **Usuário com credencial provisória e sessão aberta em outro dispositivo**: a definição da própria
  senha encerra as demais sessões (FR-036).

## Requirements *(mandatory)*

### Functional Requirements

#### Autorização e abrangência

- **FR-001**: As operações sobre usuários, papéis e credenciais de terceiros DEVEM estar disponíveis
  somente a identidades de negócio ativas com `ROLE-SYSTEM-ADMIN` (`PERM-USER-MANAGE`), e as
  operações sobre setores somente a essas mesmas identidades (`PERM-SECTOR-MANAGE`). A autorização
  DEVE ser verificada no servidor no momento de cada operação e de cada consulta, independentemente
  do que a interface apresente.
- **FR-002**: Quem não tem a capability correspondente NÃO DEVE receber o conteúdo das superfícies de
  administração (listas, fichas, histórico) nem conseguir executar suas operações; a recusa NÃO DEVE
  revelar dados das identidades ou setores administrados.
- **FR-003**: ORG NÃO DEVE criar, renomear, redefinir nem remover papéis: atribui apenas os sete
  papéis do catálogo canônico de `docs/domain/permissions-matrix.md`. Nenhuma operação de ORG DEVE
  conceder capability por efeito colateral; um usuário só ocupa os papéis explicitamente atribuídos,
  e `ROLE-SYSTEM-ADMIN` não concede nenhuma capacidade operacional (regras 3, 4 e 7 da matriz).
- **FR-004**: ORG DEVE administrar apenas identidades de negócio. A conta técnica de superusuário NÃO
  DEVE aparecer nas listas e fichas de ORG, NÃO DEVE ser alterada por elas e NÃO DEVE receber papel de
  negócio (FR-016a da 002; regra 8 da matriz) (D-26).
- **FR-005**: ORG NÃO DEVE excluir usuários nem setores; a retirada de uso é feita por desativação
  (Constitution, Princípio IV) (D-06).

#### Usuário: dados e cadastro

- **FR-006**: Todo usuário DEVE ter matrícula e nome completo, ambos obrigatórios. A matrícula segue
  FR-001b da 002 (identifica uma única conta, tratada como texto opaco). O nome completo é texto
  livre, sem formato exigido, e DEVE ser recusado quando vazio depois de removidos os espaços nas
  pontas; nomes repetidos são permitidos, porque a matrícula identifica a pessoa. O WMS NÃO DEVE
  guardar e-mail nem outro dado de contato do usuário (D-05).
- **FR-007**: O administrador DEVE poder cadastrar um usuário informando matrícula, nome completo,
  setor (ativo ou inativo) e papéis adicionais. A conta DEVE nascer ativa, com `ROLE-REQUESTER`
  atribuído de forma explícita e atômica com a criação (FR-016a da 002) e com os papéis adicionais
  escolhidos, e DEVE receber uma senha provisória (FR-031) (D-07, D-13).
- **FR-008**: O cadastro DEVE ser recusado, sem criar nada, quando: a matrícula já pertence a outra
  conta; falta nome completo ou setor; `ROLE-SECTOR-HEAD` é pedido num setor que já tem chefe ativo
  (FR-022 da 002); um papel de almoxarifado é pedido fora do setor Almoxarifado (`INV-ORG-005`); ou
  `ROLE-WAREHOUSE-HEAD` é pedido sem a chefia do setor Almoxarifado (`INV-ORG-006`).
- **FR-009**: O administrador DEVE poder editar o nome completo. A matrícula DEVE ser editável apenas
  para corrigir erro de digitação, com o valor anterior registrado no histórico, e a nova matrícula
  DEVE obedecer à mesma unicidade do cadastro (D-05).

#### Papéis

- **FR-010**: O administrador DEVE poder conceder e remover papéis segundo estas regras de
  composição: `ROLE-AUDITOR` e `ROLE-SYSTEM-ADMIN` em usuário de qualquer setor;
  `ROLE-SECTOR-ASSISTANT` para o próprio setor do usuário; `ROLE-WAREHOUSE-STAFF` somente a usuário
  do setor Almoxarifado; `ROLE-SECTOR-HEAD` conforme FR-012 e FR-014 a FR-018; `ROLE-WAREHOUSE-HEAD`
  somente junto com a chefia do setor Almoxarifado (FR-012, FR-016).
- **FR-011**: A concessão ou remoção de papel DEVE ser recusada quando: remove `ROLE-REQUESTER` de
  conta ativa; remove `ROLE-SECTOR-HEAD` do chefe de setor ativo ou concede esse papel num setor que
  já tem chefe ativo (indicando a substituição, FR-014); concede ou remove `ROLE-WAREHOUSE-HEAD` fora
  da designação ou substituição da chefia do Almoxarifado; remove `ROLE-WAREHOUSE-STAFF` do chefe do
  setor Almoxarifado; concede papel de almoxarifado fora do Almoxarifado; ou retira
  `ROLE-SYSTEM-ADMIN` do último administrador ativo (FR-022).
- **FR-012**: Num setor inativo sem chefe ativo, designar o chefe DEVE ser uma concessão comum de
  `ROLE-SECTOR-HEAD` a um membro do próprio setor, respeitando FR-022 da 002. No setor Almoxarifado,
  a designação DEVE conceder, na mesma operação, `ROLE-SECTOR-HEAD` e `ROLE-WAREHOUSE-HEAD`, e
  `ROLE-WAREHOUSE-STAFF` se o designado ainda não o tiver; retirar a chefia de um Almoxarifado
  inativo DEVE retirar juntos `ROLE-SECTOR-HEAD` e `ROLE-WAREHOUSE-HEAD` (D-04, D-07).

#### Transferência de setor

- **FR-013**: O administrador DEVE poder transferir um usuário para outro setor, ativo ou inativo. A
  transferência DEVE:
  - ser recusada quando o usuário é chefe de setor ativo, indicando substituir a chefia antes (FR-021
    da 002);
  - ser recusada quando o destino é o setor atual do usuário;
  - remover, na mesma operação e de forma explícita, os papéis presos ao setor de origem:
    `ROLE-SECTOR-ASSISTANT`, `ROLE-SECTOR-HEAD` (possível só com o setor de origem inativo),
    `ROLE-WAREHOUSE-STAFF` e `ROLE-WAREHOUSE-HEAD`;
  - manter `ROLE-REQUESTER`, `ROLE-AUDITOR` e `ROLE-SYSTEM-ADMIN`;
  - não conceder papel nenhum no destino, inclusive quando o destino é o Almoxarifado;
  - listar ao administrador, antes da confirmação, os papéis que serão removidos (D-10).

#### Substituição de chefia

- **FR-014**: O administrador DEVE poder substituir o chefe de um setor ativo numa única operação, na
  qual o novo chefe recebe `ROLE-SECTOR-HEAD` e o anterior o perde; em nenhum momento o setor fica
  sem chefe ou com dois. O chefe anterior DEVE continuar ativo, no mesmo setor e com os demais papéis
  (D-01, D-02).
- **FR-015**: O novo chefe DEVE ser usuário ativo do próprio setor e diferente do chefe atual; caso
  contrário, a substituição DEVE ser recusada, indicando, para usuário de outro setor, transferi-lo
  antes (D-03).
- **FR-016**: No setor Almoxarifado, a substituição DEVE mover junto `ROLE-WAREHOUSE-HEAD` para o novo
  chefe, conceder-lhe `ROLE-WAREHOUSE-STAFF` se ainda não o tiver, e preservar
  `ROLE-WAREHOUSE-STAFF` do chefe anterior. Em nenhum momento podem existir dois usuários ativos com
  `ROLE-WAREHOUSE-HEAD` (`INV-ORG-006`) (D-04).
- **FR-017**: A substituição DEVE identificar o chefe que o administrador viu ao confirmar e DEVE ser
  recusada se, no momento da execução, ele já não for o chefe do setor; substituições concorrentes no
  mesmo setor DEVEM ser serializadas (D-02).
- **FR-018**: A mesma operação DEVE servir para troca definitiva e para cobertura temporária (férias,
  licença). NÃO DEVE existir chefe substituto com prazo nem retorno automático; quem assume a chefia
  do Almoxarifado, mesmo temporariamente, assume também as atribuições exclusivas de estoque
  (D-01, D-04).

#### Desativação e reativação de usuário

- **FR-019**: O administrador DEVE poder desativar um usuário, opcionalmente com uma justificativa
  curta registrada no histórico. A desativação DEVE preservar os papéis do usuário (FR-016a da 002) e
  DEVE fazer o acesso cessar na próxima interação, inclusive em sessão já aberta (FR-006 da 002;
  `INV-AUTH-001`) (D-11).
- **FR-020**: A desativação DEVE ser recusada para o chefe de setor ativo, inclusive do Almoxarifado,
  indicando substituir antes (FR-021 da 002).
- **FR-021**: A desativação de usuário NÃO DEVE ser bloqueada por registros de outros recortes,
  como requisições em andamento (D-20).
- **FR-022**: O sistema DEVE recusar: que o administrador desative a própria conta; a desativação do
  último administrador ativo; e a retirada de `ROLE-SYSTEM-ADMIN` do último administrador ativo. As
  demais operações sobre a própria conta DEVEM ser permitidas e registradas no histórico como
  quaisquer outras (D-15).
- **FR-023**: A reativação DEVE apresentar ao administrador os papéis preservados que voltarão a
  valer e permitir desmarcar qualquer um deles, exceto `ROLE-REQUESTER`. O resultado DEVE ser
  exatamente o que foi confirmado (D-12).
- **FR-024**: A reativação DEVE ser recusada, com o motivo, enquanto incluir papel que violaria uma
  regra — segundo chefe ativo do setor, segundo chefe do almoxarifado ativo, papel de almoxarifado
  fora do Almoxarifado ou qualquer outra condição de FR-010 e FR-011; desmarcando esses papéis, ela
  prossegue (D-12).

#### Setores

- **FR-025**: Todo setor DEVE ter nome obrigatório, único entre os setores, comparado sem diferenciar
  maiúsculas de minúsculas e desconsiderando espaços nas pontas. O nome DEVE ser editável pelo
  administrador, com registro no histórico (D-09).
- **FR-026**: O setor criado pelo administrador DEVE nascer inativo (FR-019 da 002) e NÃO DEVE ser
  designado como Almoxarifado.
- **FR-027**: A ativação de setor DEVE exigir exatamente um chefe ativo pertencente ao próprio setor
  (FR-020 da 002; `INV-ORG-002`, `INV-ORG-003`) e, no Almoxarifado, que esse chefe tenha
  `ROLE-WAREHOUSE-HEAD` e `ROLE-WAREHOUSE-STAFF` (`INV-ORG-006`).
- **FR-028**: A desativação de setor DEVE ser permitida somente quando o chefe for o único membro
  ativo restante; havendo outros membros ativos, DEVE ser recusada, indicando transferi-los ou
  desativá-los antes. Depois da desativação, o chefe mantém `ROLE-SECTOR-HEAD` e pode ser transferido
  (FR-013) ou desativado (D-16). Contas técnicas (FR-004) não contam como membro do setor, nem nesta
  regra nem nas contagens de membros.
- **FR-029**: A desativação do setor Almoxarifado DEVE ser sempre recusada depois que ele tiver sido
  ativado (`INV-ORG-004`) (D-17).
- **FR-030**: Setor DEVE ter um único estado inativo, sem distinguir "em formação" de "desativado"; o
  histórico do setor DEVE permitir saber se ele já esteve ativo. Reativar um setor DEVE seguir as
  mesmas condições da ativação (FR-027) (D-16, D-18).

#### Credenciais

- **FR-031**: No cadastro e na redefinição, o sistema DEVE gerar uma senha provisória aleatória e
  exibi-la ao administrador uma única vez, no momento da operação. Ela NÃO DEVE ser exibida de novo,
  recuperada, registrada no histórico nem em logs. O administrador NÃO DEVE definir a senha de
  terceiros (D-13).
- **FR-032**: Quem autentica com senha provisória DEVE ter acesso apenas à definição da própria senha
  e ao encerramento da sessão, até definir a própria senha; qualquer outra superfície DEVE ser negada
  no servidor (emenda de 2026-10-01 ao SC-001 da 002) (D-13).
- **FR-033**: O administrador DEVE poder redefinir a senha de um usuário. A redefinição DEVE
  gerar nova senha provisória (FR-031), encerrar todas as sessões abertas da conta e exigir a
  definição da própria senha no próximo acesso (D-13).
- **FR-034**: Depois de definir a própria senha, o usuário DEVE ser direcionado ao destino que
  solicitou antes de autenticar, quando esse destino atender às condições de FR-010 da 002 (interno,
  existente e autorizado); caso contrário, à Home autenticada mínima (FR-010a da 002). O destino
  NUNCA DEVE ser externo ao WMS (FR-011 da 002).
- **FR-035**: A senha provisória DEVE deixar de valer 7 dias depois de gerada, se até lá não tiver
  sido usada para definir a própria senha. A autenticação com senha provisória vencida DEVE ser
  recusada com a mesma mensagem genérica de FR-003 da 002, sem revelar o vencimento; para voltar a
  acessar, o usuário depende de nova redefinição pelo administrador (FR-033). A ficha do usuário
  (FR-045) DEVE indicar quando a credencial provisória está vencida.
- **FR-036**: A definição da própria senha DEVE recusar como nova senha a senha provisória em uso,
  DEVE encerrar as demais sessões da conta e DEVE gerar evento no histórico, sem a senha (D-13,
  D-14).
- **FR-037**: Todo usuário autenticado e ativo DEVE poder trocar a própria senha quando quiser,
  confirmando a senha atual. Com a senha atual errada, nada DEVE mudar. A troca bem-sucedida DEVE
  encerrar as demais sessões da conta, manter a sessão em uso e gerar evento no histórico, sem a
  senha (D-14).
- **FR-038**: A nova senha, na definição e na troca, DEVE ter no mínimo 8 caracteres e DEVE ser
  recusada, com o motivo, quando for uma senha comum, quando for composta só de números ou quando se
  parecer com os dados do próprio usuário (matrícula, nome). Não há exigência de combinação de tipos
  de caractere nem de expiração periódica.
- **FR-039**: Definir e trocar a própria senha são mecânicas de autenticação, como login e logout:
  NÃO DEVEM depender de papel nem criar capability nova em `permissions-matrix.md` (D-27).

#### Histórico organizacional

- **FR-040**: Toda operação de ORG efetivada DEVE gerar, na mesma operação, um evento de histórico com
  autor, momento, alvo e valores anteriores e novos. Isso inclui: cadastro; edição de nome e de
  matrícula; transferência, com os papéis removidos; concessão e remoção de papel; substituição de
  chefia; desativação, com a justificativa quando houver, e reativação de usuário, com os papéis
  confirmados; criação, edição, ativação e desativação de setor; entrega e redefinição de senha pelo
  administrador; definição e troca da própria senha. Nos eventos do provisionamento técnico
  (FR-050), o autor é registrado e exibido como "provisionamento técnico". Eventos de senha NÃO DEVEM
  conter a senha (D-08).
- **FR-041**: Eventos de histórico NÃO DEVEM ser alterados nem removidos depois de registrados. Se o
  evento não puder ser registrado, a operação DEVE falhar inteira.
- **FR-042**: O histórico DEVE ser consultável pelo administrador na ficha do usuário e na ficha do
  setor, em ordem cronológica, sob `PERM-USER-MANAGE` e `PERM-SECTOR-MANAGE`. Nenhum outro papel DEVE
  acessá-lo (D-08).

#### Consulta

- **FR-043**: O administrador DEVE poder listar e buscar usuários por parte do nome, matrícula, setor,
  situação (ativo ou inativo) e papel, combinando filtros, com resultado paginado. A lista DEVE
  mostrar matrícula, nome, setor, situação e papéis.
- **FR-044**: O administrador DEVE poder listar setores, buscar por nome e filtrar por situação. A
  lista DEVE mostrar nome, situação, chefe atual (quando houver), quantidade de membros ativos (só identidades
  de negócio) e a indicação do setor designado como Almoxarifado.
- **FR-045**: A ficha do usuário DEVE mostrar matrícula, nome, setor, situação, papéis, se a
  credencial vigente é provisória (e, nesse caso, se já venceu, FR-035) e o histórico. A ficha do setor DEVE mostrar nome, situação, chefe,
  membros ativos e inativos e o histórico.

#### Integridade, concorrência e recusas

- **FR-046**: Depois de qualquer operação que escreva usuário, setor ou papel, por qualquer caminho —
  as superfícies de ORG ou o caminho técnico de manutenção —, `INV-ORG-001` a `INV-ORG-006` DEVEM
  continuar verdadeiras, as mesmas regras desta spec DEVEM ter sido aplicadas e o mesmo evento de
  histórico DEVE ter sido gerado (D-22).
- **FR-047**: Toda operação de ORG DEVE ser atômica e serializada sobre os registros que afeta: uma
  operação recusada NÃO DEVE deixar estado parcial, e uma operação concorrente DEVE ser avaliada sobre
  o resultado da outra. Isso estende FR-023 da 002 a todas as operações desta spec (D-24).
- **FR-048**: Toda recusa DEVE informar o motivo e o caminho para resolvê-lo (por exemplo,
  "substitua o chefe antes", "transfira para o setor antes"), sem expor detalhes internos. A interface
  PODE antecipar recusas, mas a decisão DEVE ser do servidor (D-25).
- **FR-049**: Antes de confirmar uma transferência, uma reativação ou uma substituição de chefia, o
  administrador DEVE ver os efeitos sobre papéis que a operação produzirá (D-10, D-12).

#### Provisionamento inicial

- **FR-050**: O provisionamento inicial, pelo caminho técnico, DEVE criar o único setor designado como
  Almoxarifado, a primeira identidade de negócio com `ROLE-SYSTEM-ADMIN` e a chefia válida do
  Almoxarifado (`INV-ORG-004` a `INV-ORG-006`). Depois disso, a manutenção cotidiana é feita pelas
  superfícies de ORG. ORG NÃO DEVE oferecer criação de outro Almoxarifado nem mudança da designação
  (D-23).

#### Contrato com outros recortes (lado de ORG)

- **FR-051**: Nenhuma operação de ORG DEVE alterar registros de outros recortes — requisições,
  movimentações, entradas, importações ou quaisquer outros. Transferir, desativar, substituir chefia
  ou alterar papéis não reescreve autoria nem vínculo já registrado nesses recortes (D-21).
- **FR-052**: Cada alteração organizacional DEVE passar a valer para toda decisão de autorização
  tomada depois de efetivada: a autorização é avaliada no momento da ação, com o estado organizacional
  atual. ORG NÃO DEVE preservar, para quem perdeu papel, chefia, setor ou situação ativa, nenhuma
  autorização derivada do estado anterior (D-21).
- **FR-053**: A desativação de setor DEVE admitir condições adicionais impostas por outros recortes e,
  quando alguma delas não for atendida, DEVE ser recusada com o motivo informado por ela. Esta spec
  não define essas condições (D-20).

### Key Entities

- **Usuário (identidade de negócio)**: pessoa que acessa o WMS. Tem matrícula única, nome completo,
  exatamente um setor (`INV-ORG-001`), situação ativa ou inativa, papéis explicitamente atribuídos e
  uma credencial que pode estar provisória ou definida pelo próprio usuário. Nunca é excluído.
- **Setor**: unidade organizacional do SAEP. Tem nome único (sem diferenciar caixa e espaços nas
  pontas), situação ativa ou inativa e, quando ativo, exatamente um chefe ativo do próprio setor
  (`INV-ORG-002`). A chefia é a atribuição de `ROLE-SECTOR-HEAD` a um usuário do setor. Nunca é
  excluído.
- **Designação de Almoxarifado**: marca, fixada no provisionamento, do único setor que é o
  Almoxarifado (`INV-ORG-004`). Determina onde papéis de almoxarifado podem existir (`INV-ORG-005`)
  e acopla sua chefia à chefia de estoque (`INV-ORG-006`).
- **Atribuição de papel**: vínculo explícito entre um usuário e um dos sete papéis canônicos.
  Preservada na desativação; removida explicitamente na transferência quando presa ao setor.
- **Credencial provisória**: estado da credencial de uma conta cuja senha foi gerada pelo sistema no
  cadastro ou na redefinição. Enquanto vigente, restringe o acesso à definição da própria senha.
- **Evento do histórico organizacional**: registro só de acréscimo de uma operação de ORG efetivada,
  com autor, momento, alvo, tipo de operação e valores anteriores e novos; nunca contém senha.

## Regras canônicas aplicáveis

### Permissões

- `PERM-USER-MANAGE` — cadastro, edição, transferência, papéis, substituição de chefia, desativação,
  reativação, redefinição de senha e consulta de usuários e de seu histórico (FR-001, FR-002,
  FR-006 a FR-024, FR-031, FR-033, FR-040 a FR-045). Condição: toda atribuição respeita `INV-ORG-001`
  a `INV-ORG-006`.
- `PERM-SECTOR-MANAGE` — criação, edição, ativação, desativação e consulta de setores e de seu
  histórico (FR-001, FR-002, FR-025 a FR-030, FR-040 a FR-044, FR-053). Condição: setor ativo com
  chefe ativo do próprio setor; Almoxarifado único, fixo e não desativado depois de ativo.
- Esta spec não cria nem amplia capability. `ROLE-SYSTEM-ADMIN` não ganha override de operações de
  negócio (regra 7) e o superusuário técnico continua fora da matriz (regra 8). Definir e trocar a
  própria senha não são capabilities (FR-039).

### Invariantes

- `INV-ORG-001` — FR-006, FR-007, FR-013, FR-046.
- `INV-ORG-002` — FR-011, FR-012, FR-014, FR-017, FR-020, FR-024, FR-027, FR-028, FR-046, FR-047.
- `INV-ORG-003` — FR-012, FR-013, FR-015, FR-027.
- `INV-ORG-004` — FR-026, FR-029, FR-050.
- `INV-ORG-005` — FR-008, FR-010, FR-011, FR-013, FR-024.
- `INV-ORG-006` — FR-008, FR-011, FR-012, FR-016, FR-018, FR-024, FR-027, FR-050.
- `INV-AUTH-001` — FR-019, FR-032, FR-033, FR-037.

### Requisitos preservados da 002

FR-016a (`ROLE-REQUESTER` explícito na criação; superusuário técnico sem papéis; desativação não
remove papéis) e FR-019 a FR-023 (setor nasce inativo; ativação com exatamente um chefe ativo;
nenhuma operação deixa setor ativo sem chefe; sem segundo chefe; atomicidade) continuam valendo sem
alteração. Esta spec os aplica a todas as suas operações e estende a atomicidade de FR-023 (FR-047).
A emenda de 2026-10-01 ao SC-001 da 002 é atendida por FR-032.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O administrador realiza todas as operações cotidianas de ORG — cadastro, edição,
  papéis, transferência, substituição de chefia, desativação, reativação, redefinição de senha e
  manutenção de setores — sem recorrer ao caminho técnico de manutenção.
- **SC-002**: Em 100% dos estados verificados depois de qualquer operação, inclusive concorrente e
  por qualquer caminho de escrita, `INV-ORG-001` a `INV-ORG-006` permanecem verdadeiras; em nenhum
  momento um setor ativo tem zero ou dois chefes ativos, nem existem dois chefes do almoxarifado
  ativos.
- **SC-003**: 100% das operações recusadas deixam o estado inalterado e informam motivo e caminho.
- **SC-004**: 100% das operações efetivadas têm evento de histórico com autor, momento, alvo e valores
  anteriores e novos; nenhum evento, log ou tela posterior contém senha.
- **SC-005**: Em 100% das tentativas, quem está com senha provisória não acessa nenhuma superfície
  além da definição da própria senha e do encerramento da sessão.
- **SC-006**: Em 100% dos casos, depois de desativação ou de redefinição de senha, as sessões abertas
  da conta deixam de conceder acesso na interação seguinte.
- **SC-007**: O administrador localiza qualquer usuário por parte do nome ou pela matrícula numa única
  busca.
- **SC-008**: Nenhuma identidade obtém, por operação de ORG, capability além das concedidas aos
  papéis explicitamente atribuídos a ela; um administrador sem papéis operacionais continua sem
  acesso a estoque e requisições.

## Fora de Escopo

- Criar, renomear ou redefinir papéis, ou alterar o que cada papel concede (`permissions-matrix.md`).
- Conceder poderes operacionais implícitos, inclusive ao administrador ou por entrada no setor
  Almoxarifado.
- Gestão de estoque e qualquer operação de outro recorte.
- Redefinir o login da 002; a única alteração do acesso é a etapa de definição obrigatória da senha,
  já prevista na emenda ao SC-001.
- Recuperação de senha sem o administrador, autoatendimento por página pública, e-mail, notificações
  ou SSO.
- Designação temporária de chefe com prazo ou retorno automático; delegação de aprovação.
- Acesso do auditor ou de outro papel ao histórico organizacional.
- Exclusão física de usuários ou setores; transferência em massa.
- Lado de REQ do contrato organizacional: setor gravado na requisição, autor da decisão, tratamento
  de beneficiário inativo, estados que contam como "não encerrada", a trava de desativação de setor
  por requisições e a canonização de `INV-REQ-001` pertencem à spec de REQ (D-19, D-20).
- Exibir o nome do autor nas telas de entradas já existentes (ajuste opcional fora do recorte).

## Assumptions

- **Operações sem efeito e recusas** não geram evento de histórico; o histórico registra só o que
  mudou o estado.
- **Reativação não altera a credencial**: a conta reativada volta com a senha que tinha; se
  necessário, o administrador a redefine em seguida.
- **Corrigir a matrícula não encerra sessões**: a conta é a mesma; o próximo login usa a nova
  matrícula.
- **Desativação de usuário e de setor e redefinição de senha** pedem confirmação explícita no padrão
  de confirmação do design system.
- **Escala**: dezenas a poucas centenas de usuários e algumas dezenas de setores; o SAEP terá um
  único administrador, o dono do produto, mas o sistema não impede haver outros (D-15).
- **Limite dos caminhos técnicos**: as regras de integridade valem para qualquer escrita, inclusive
  SQL direto, porque o banco as verifica. O evento de histórico é garantido para toda escrita pelas
  operações de ORG e pelos caminhos técnicos suportados (provisionamento, shell chamando as
  operações). Quem contornar deliberadamente essas operações no shell técnico escreve sem evento;
  esse acesso é restrito ao superusuário técnico.
- **Decisões do plan**: se o caminho técnico de manutenção fica somente leitura ou com escrita
  protegida para dados organizacionais, o modelo do histórico e o mecanismo da senha provisória e da
  troca obrigatória são decididos no `plan.md`, respeitando FR-031 a FR-041 e FR-046.
- **Dependências**: `O: 002`, entregue. A recomendação de entregar ORG antes do uso amplo de REQ não
  bloqueia REQ, que pode usar identidades, setores e chefias válidos vindos do provisionamento.
- **Estado implementado da 002**: o usuário hoje não tem nome, o nome de setor não é único, não há
  designação de Almoxarifado nem histórico organizacional; adequar dados existentes, provisionamento
  de desenvolvimento e testes é trabalho do plan. Como o schema ainda é efêmero (Constitution,
  Princípio XIII), não há dado durável a migrar.
