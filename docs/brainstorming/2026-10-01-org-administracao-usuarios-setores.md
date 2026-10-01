# Brainstorming — ORG: administração de usuários, papéis e setores

```text
Status: INSUMO PARA SPEC — NÃO NORMATIVO
Data: 2026-10-01
Participantes: dono do produto (também o único administrador de sistema) e Claude Code
Destino: speckit-specify de ORG
Fontes canônicas afetadas: docs/domain/invariants-matrix.md (INV-ORG-004 a INV-ORG-006),
docs/domain/permissions-matrix.md (condições de PERM-USER-MANAGE e PERM-SECTOR-MANAGE),
specs/002-autenticacao-login/spec.md (SC-001), ROADMAP.md (recorte e pendências de ORG)
```

Este documento registra as decisões de produto tomadas no brainstorming de `ORG`, para servirem
de insumo à futura spec. **Não é fonte canônica nem substitui nenhuma.** As regras transversais
decididas aqui foram registradas nas matrizes canônicas, que prevalecem sobre este texto. Os
requisitos de comportamento passam a valer quando a spec de ORG for escrita e validada. Em caso
de divergência, valem as matrizes, depois a spec.

Convenções: **Decidido** marca uma escolha explícita do dono do produto nesta sessão;
**Derivado** marca uma consequência direta de regra vigente ou de decisão desta sessão,
apresentada e validada em bloco; **Pendente** marca o que continua em aberto (seção 8).

## 1. Recorte de ORG

Situado na linha `ORG` do [roadmap](../../ROADMAP.md).

- **Resultado:** manter identidades e sua organização com chefia válida e atribuições explícitas.
- **Inclui:** gestão pelo administrador de sistema; vínculo setorial; atribuição dos papéis
  canônicos; manutenção das invariantes organizacionais; entrega e redefinição de credenciais pelo
  administrador; troca da própria senha pelo usuário autenticado (ampliação decidida em D-14).
- **Não inclui:** redefinir papéis; conceder poderes operacionais implícitos; gestão de estoque;
  redefinir o login (a emenda pontual ao SC-001 da 002 está em D-13); recuperação de senha sem o
  administrador; e-mail, notificações ou SSO.
- **Dependências:** `O: 002` (entregue). `R: antes do uso amplo de REQ` — continua recomendação.
  REQ pode usar identidades, setores e chefias válidos vindos do provisionamento da 002.

## 2. Regras vigentes preservadas (não reabertas)

`PERM-USER-MANAGE`, `PERM-SECTOR-MANAGE`, `INV-ORG-001` a `INV-ORG-003`, `INV-AUTH-001`; spec 002
FR-016a e FR-019 a FR-023; notas de composição de `permissions-matrix.md` (`ROLE-REQUESTER`
explícito na criação, desativação não remove papéis, superusuário técnico sem papéis de negócio,
administrador sem override de negócio).

**Estado implementado observado (002), relevante para o plan:** `User` tem só `matricula`, `setor`
e `is_active`; `Setor` tem só `nome` (sem unicidade) e `ativo`; a chefia é derivada de
`ROLE-SECTOR-HEAD` mais o setor do usuário; não há histórico de alterações organizacionais; a única
interface é o Django Admin; usuários ativos podem estar em setor inativo (é o provisionamento). Pelas
regras atuais, não é possível trocar o chefe de um setor ativo em passos separados: remover o chefe
atual é recusado por FR-021 e dar o papel ao novo antes é recusado por FR-022.

## 3. Decisões

| ID | Tema | Decisão | Tipo | Justificativa / alternativas descartadas |
|---|---|---|---|---|
| D-01 | Troca de chefia | A troca de chefe é feita por **uma operação de substituição atômica**, usada tanto para troca definitiva quanto para substituição temporária (férias, licença). Não existe chefe substituto com prazo nem retorno automático. | Decidido | Substituição temporária é rara no SAEP. Descartado: designação temporária com volta automática (conceitos de titular/substituto e transição por data sem evidência de necessidade). |
| D-02 | Substituição de chefe | Só o administrador executa. Em uma transação, o novo chefe recebe `ROLE-SECTOR-HEAD` e o anterior o perde; o setor nunca fica sem chefe nem com dois. O anterior continua ativo, no mesmo setor, com os demais papéis. Em setor inativo, basta a atribuição comum. Substituições concorrentes no mesmo setor são serializadas, e a segunda é recusada se o chefe anterior informado já não for o chefe. | Decidido | Preserva `INV-ORG-002` e FR-021 a FR-023 sem alterá-las. |
| D-03 | Origem do novo chefe | O novo chefe precisa já ser usuário **ativo do próprio setor**. Quem vem de outro setor é transferido antes, como funcionário comum. | Decidido | Mantém uma responsabilidade por operação. Descartado: transferir e promover na mesma operação. |
| D-04 | Chefia do almoxarifado | **Acoplamento total (B1)**: existe um único setor designado Almoxarifado, fixo desde o provisionamento; papéis de almoxarifado só existem nele; o chefe do setor Almoxarifado é o único usuário ativo com `ROLE-WAREHOUSE-HEAD` e também ocupa `ROLE-WAREHOUSE-STAFF`. A substituição do chefe do Almoxarifado move `ROLE-SECTOR-HEAD` e `ROLE-WAREHOUSE-HEAD` juntos; o anterior mantém `ROLE-WAREHOUSE-STAFF`. Quem substitui o chefe (inclusive nas férias) assume todas as atribuições exclusivas de estoque. | Decidido | Canonizado como `INV-ORG-004` a `INV-ORG-006`. Descartados: papéis independentes (A); unicidade sem coincidir com a chefia (B2); acoplamento só na interface (C). |
| D-05 | Dados do usuário | **Matrícula e nome completo**, ambos obrigatórios. O nome é editável. A matrícula só é editável para corrigir erro de digitação, com registro no histórico. Não há e-mail nem outro contato. | Decidido | REQ precisará escolher beneficiário por pessoa; histórico legível. Descartado: só matrícula; dados de contato sem uso. |
| D-06 | Exclusão | ORG não exclui usuários nem setores; oferece desativação. | Derivado | Constitution IV; autores de estoque já são protegidos por FK. |
| D-07 | Papéis na criação | A conta nasce com `ROLE-REQUESTER` (FR-016a) e os demais papéis escolhidos explicitamente. `ROLE-WAREHOUSE-HEAD` nunca é atribuído sozinho: acompanha a chefia do setor Almoxarifado. A criação respeita FR-022 e `INV-ORG-005`. | Derivado | — |
| D-08 | Histórico organizacional | Toda operação de ORG gera um **evento só de acréscimo** com autor, momento, alvo e valores anteriores e novos. Inclui criação, edição de nome e matrícula, transferência, concessão e remoção de papel, substituição de chefia, ativação, desativação e reativação de usuário e setor, entrega, redefinição e troca de senha (o evento, nunca a senha). Consultável pelo administrador na ficha do usuário e do setor, sob `PERM-USER-MANAGE`/`PERM-SECTOR-MANAGE`. | Decidido | Constitution IV. Descartados: só "última alteração" (perde histórico); acesso do auditor (exigiria `PERM-*` nova sem necessidade). |
| D-09 | Dados do setor | Nome obrigatório e **único entre setores**, comparado sem diferenciar maiúsculas e minúsculas e sem espaços nas pontas. Editável pelo administrador, com histórico. | Decidido | Evita dois setores indistinguíveis para o administrador e para a fila de REQ. |
| D-10 | Transferência | Chefe de setor ativo não pode ser transferido (FR-021): substitui-se antes. A transferência **remove, na mesma transação e de forma explícita, os papéis presos ao setor**: `ROLE-SECTOR-ASSISTANT`, `ROLE-SECTOR-HEAD` (possível só se o setor de origem estiver inativo), `ROLE-WAREHOUSE-STAFF` e `ROLE-WAREHOUSE-HEAD`. A tela lista o que será removido antes de confirmar. `ROLE-REQUESTER`, `ROLE-AUDITOR` e `ROLE-SYSTEM-ADMIN` são mantidos. Entrar no Almoxarifado não concede papel nenhum. | Decidido | Evita poder implícito no setor de destino. Descartados: recusar até remoção manual; papel de auxiliar acompanhando a pessoa. |
| D-11 | Desativação de usuário | Só o administrador desativa. O acesso cai na próxima interação (FR-006). É recusada para o chefe de setor ativo, inclusive do Almoxarifado. Os papéis são preservados. Justificativa curta opcional, registrada no histórico. | Decidido | — |
| D-12 | Reativação de usuário | **Restaura os papéis preservados, com revisão**: a tela lista o que voltará a valer, e o administrador pode desmarcar qualquer papel, menos `ROLE-REQUESTER`. Papéis que violariam uma regra (segundo chefe, segundo chefe do almoxarifado, papel de almoxarifado fora dele) são recusados com o motivo, e o administrador os desmarca para prosseguir. | Decidido | Descartados: restaurar tudo sem revisão; reativar só com `ROLE-REQUESTER`. |
| D-13 | Entrega e recuperação de credenciais | Na criação e na redefinição, o sistema **gera uma senha provisória aleatória**, mostrada **uma única vez** ao administrador, que a entrega pessoalmente. A redefinição encerra as sessões abertas da conta. Com senha provisória, o usuário precisa **definir a própria senha antes de usar o sistema**. O SC-001 da 002 foi emendado com essa exceção. | Decidido | O administrador não conhece senhas definitivas; a autoria das ações continua forte. Descartados: senha definida pelo administrador; código de ativação por página pública. |
| D-14 | Troca voluntária de senha | **Ampliação de recorte aprovada:** o usuário autenticado troca a própria senha quando quiser, confirmando a senha atual. A troca encerra as outras sessões da conta e gera evento no histórico. Recuperação sem o administrador continua fora (não há canal para provar identidade). | Decidido | Reaproveita a tela de D-13. Descartados: depender do administrador; capacidade separada. |
| D-15 | Proteções do administrador | ORG recusa desativar o último administrador ativo, retirar dele `ROLE-SYSTEM-ADMIN` e o administrador desativar a própria conta. Demais alterações sobre a própria conta são permitidas e ficam no histórico. Não há segregação de funções: o SAEP terá **um único administrador, o dono do produto**. | Decidido | Evita bloqueio total sem depender do superusuário técnico. Descartados: segregação (inviável com um administrador e exigiria condição canônica nova); nenhuma proteção. |
| D-16 | Desativação de setor | Só é permitida quando **o chefe é o único membro ativo restante**; os demais são transferidos ou desativados antes. Depois disso o chefe pode ser transferido (perde `ROLE-SECTOR-HEAD`, D-10) ou desativado. Reativar o setor equivale a ativá-lo (FR-020). | Decidido | Nenhuma pessoa ativa fica presa em setor sem chefia. Descartados: desativar com membros ativos; transferência em massa. |
| D-17 | Setor Almoxarifado | Uma vez ativado, **nunca pode ser desativado**. | Decidido | Canonizado em `INV-ORG-004`. |
| D-18 | Estado do setor | Existe **um único estado inativo** (em formação ou desativado); o histórico mostra se o setor já esteve ativo. Criar usuário ou transferir para setor inativo continua permitido. | Decidido | REQ não precisa distinguir os casos (D-19, D-20). |
| D-19 | Setor da requisição | **Decisão compartilhada com REQ/ATE.** A requisição pertence ao setor do beneficiário **no momento da criação**, fixado nela. Decide o **chefe atual** desse setor no momento da decisão, e a requisição grava quem decidiu. A spec de REQ codifica isso e canoniza o candidato `INV-REQ-001`. | Decidido | Escopo "próprio setor" estável no tempo; relatórios por setor estáveis. Descartados: seguir o setor atual do beneficiário; adiar a decisão. |
| D-20 | Requisições pendentes e desativações | **Decisão compartilhada com REQ.** A desativação de usuário **nunca** é bloqueada por requisições; REQ define o tratamento de requisição cujo beneficiário ficou inativo. A desativação de setor **é bloqueada** enquanto houver requisição não encerrada do setor. Os estados que contam como não encerrada são de REQ/ATE, e a trava é especificada e implementada por REQ. A spec de ORG só declara que a desativação de setor admite condições impostas por outros recortes. | Decidido | Segurança antes de fluxo de negócio; evita fila órfã. Descartados: nenhum bloqueio com efeito automático em REQ; bloquear também a desativação de usuário. |
| D-21 | Contrato ORG ↔ REQ/ATE | (1) A autorização é sempre avaliada no momento da ação, com o estado organizacional atual. (2) O criador continua vendo o que criou (`PERM-REQ-VIEW-OWN`). (3) A visão de setor acompanha a chefia atual: o novo chefe vê o histórico do setor e o anterior deixa de ver. (4) ATE não tem atribuição pessoal, então retirar `ROLE-WAREHOUSE-STAFF` não deixa nada órfão. (5) ORG nunca altera registros de outros recortes. | Decidido | — |
| D-22 | Caminhos de escrita | Toda escrita organizacional, por qualquer caminho (ORG, Django Admin, shell), preserva as mesmas regras e gera o mesmo evento de histórico. O Django Admin deixa de ser manutenção cotidiana e fica como recurso técnico do superusuário para provisionamento e emergência. | Decidido | Constitution III e IV. Se o Admin fica somente leitura ou com escrita protegida é decisão do plan. |
| D-23 | Provisionamento inicial | O caminho técnico cria o setor Almoxarifado com sua designação fixa, a primeira identidade de negócio com `ROLE-SYSTEM-ADMIN` e a chefia válida do Almoxarifado (D-04). Depois disso, a manutenção é feita por ORG. | Decidido | — |
| D-24 | Atomicidade e concorrência | Toda operação de ORG é atômica e serializada sobre os registros que afeta (amplia FR-023 para além da chefia). Operação recusada não deixa estado parcial; uma operação concorrente é avaliada sobre o resultado da outra. | Decidido | Constitution III. |
| D-25 | Recusas | Toda recusa informa o motivo e o caminho. A interface pode antecipar, mas a decisão é do servidor. | Decidido | Constitution V. |
| D-26 | Superusuário técnico | ORG administra apenas identidades de negócio; a conta técnica de superusuário fica fora das telas de ORG. | Decidido | `permissions-matrix.md`, regras 7 e 8; confirmado na revisão final. |
| D-27 | Senha e matriz de permissões | Definir e trocar a própria senha é mecânica de autenticação, como login e logout, e **não** vira capability em `permissions-matrix.md`. | Decidido | Mesmo tratamento da 002 para login e logout; nenhuma `PERM-*` nova. |

## 4. Fluxos principais e exceções

Todos os fluxos são executados pelo administrador de sistema, exceto 4.9. Todos geram evento de
histórico (D-08) e seguem D-24 e D-25.

### 4.1 Criar usuário
Informa matrícula, nome completo, setor e papéis adicionais. A conta nasce ativa, com
`ROLE-REQUESTER`, e com senha provisória exibida uma vez (D-13).
**Recusa quando:** matrícula repetida; falta nome ou setor; `ROLE-SECTOR-HEAD` em setor que já tem
chefe ativo (FR-022); papel de almoxarifado fora do Almoxarifado (`INV-ORG-005`);
`ROLE-WAREHOUSE-HEAD` sem a chefia do Almoxarifado (`INV-ORG-006`).

### 4.2 Editar usuário
Nome livremente. Matrícula para correção, com valor anterior no histórico; a nova matrícula
também precisa ser única.

### 4.3 Conceder e remover papéis
`ROLE-AUDITOR` e `ROLE-SYSTEM-ADMIN` em qualquer setor. `ROLE-SECTOR-ASSISTANT` no próprio setor.
`ROLE-WAREHOUSE-STAFF` só no Almoxarifado.
**Recusa quando:** remover `ROLE-REQUESTER` de conta ativa; remover `ROLE-SECTOR-HEAD` do chefe de
setor ativo (usar 4.5); conceder ou remover `ROLE-WAREHOUSE-HEAD` fora da substituição ou
designação da chefia do Almoxarifado; remover `ROLE-WAREHOUSE-STAFF` do chefe do Almoxarifado;
retirar `ROLE-SYSTEM-ADMIN` do último administrador ativo.

### 4.4 Transferir de setor
Escolhe o destino, ativo ou inativo. A tela lista os papéis presos ao setor que serão removidos
(D-10); a confirmação aplica tudo numa transação.
**Recusa quando:** a pessoa é chefe de setor ativo.

### 4.5 Substituir chefe de setor ativo
Escolhe o novo chefe entre os membros ativos do setor (D-03). A chefia passa atomicamente (D-02).
No Almoxarifado, `ROLE-WAREHOUSE-HEAD` vai junto, e o novo chefe precisa ter ou receber
`ROLE-WAREHOUSE-STAFF` (D-04).
**Recusa quando:** o escolhido não é membro ativo do setor; o chefe anterior informado não é mais o
chefe (concorrência).

### 4.6 Desativar e reativar usuário
Desativação: D-11, com recusa para chefe de setor ativo e para a própria conta ou o último
administrador (D-15). Reativação: D-12, com revisão dos papéis preservados.

### 4.7 Criar, editar, ativar e desativar setor
Criação com nome único (D-09); nasce inativo (FR-019). Designar o chefe de setor inativo é uma
atribuição comum (no Almoxarifado, com `ROLE-WAREHOUSE-HEAD` e `ROLE-WAREHOUSE-STAFF`). Ativação
exige exatamente um chefe ativo do próprio setor (FR-020) e, no Almoxarifado, `INV-ORG-006`.
Desativação: D-16, D-17 e D-20.
**Recusa quando:** outro membro ativo além do chefe; setor Almoxarifado; requisição não encerrada
(trava entregue por REQ).

### 4.8 Redefinir senha
Gera nova senha provisória exibida uma vez, encerra as sessões da conta e exige troca no próximo
acesso (D-13).

### 4.9 Definir ou trocar a própria senha (usuário autenticado)
Com senha provisória, a única superfície disponível é a definição da própria senha. Fora disso, o
usuário troca quando quiser, confirmando a atual (D-14). Ambos encerram as demais sessões da conta.

### 4.10 Consultar
Listar e buscar usuários (por nome, matrícula, setor, situação e papel) e setores, e ver na ficha
de cada um seus dados atuais e o histórico (D-08). Filtros e apresentação ficam para a spec.

## 5. Cenários de aceitação observáveis

1. **Dado** a ETA ativa com a chefe Maria e o membro ativo Pedro, **quando** o administrador
   substitui Maria por Pedro, **então** Pedro é o único chefe ativo da ETA, Maria continua ativa na
   ETA sem `ROLE-SECTOR-HEAD`, e o histórico registra a substituição com autor e momento.
2. **Dado** a ETA ativa com chefe, **quando** o administrador tenta remover `ROLE-SECTOR-HEAD` da
   chefe ou conceder esse papel a outro membro, **então** a operação é recusada com o motivo e a
   indicação de usar a substituição.
3. **Dado** um usuário de outro setor, **quando** o administrador tenta escolhê-lo como novo chefe
   da ETA, **então** a operação é recusada e indica transferir antes.
4. **Dado** o setor Almoxarifado ativo com chefe João, **quando** o administrador o substitui por
   Carla, membro ativo com `ROLE-WAREHOUSE-STAFF`, **então** Carla passa a ter `ROLE-SECTOR-HEAD` e
   `ROLE-WAREHOUSE-HEAD`, João mantém só `ROLE-WAREHOUSE-STAFF`, e em nenhum momento existem dois
   usuários ativos com `ROLE-WAREHOUSE-HEAD`.
5. **Dado** um usuário do Laboratório, **quando** o administrador tenta conceder
   `ROLE-WAREHOUSE-STAFF`, **então** a operação é recusada (`INV-ORG-005`).
6. **Dado** Ana, auxiliar da ETA, **quando** é transferida para o Laboratório, **então** a
   confirmação lista a remoção de `ROLE-SECTOR-ASSISTANT`, e depois dela Ana pertence ao
   Laboratório só com os papéis não presos ao setor.
7. **Dado** a chefe da ETA ativa, **quando** o administrador tenta transferi-la ou desativá-la,
   **então** a operação é recusada e indica substituir antes.
8. **Dado** um funcionário desativado com `ROLE-WAREHOUSE-STAFF` preservado, **quando** o
   administrador o reativa, **então** a tela lista esse papel para revisão, e o resultado é
   exatamente o que foi confirmado.
9. **Dado** um ex-chefe inativo com `ROLE-SECTOR-HEAD` preservado num setor que já tem outro chefe,
   **quando** o administrador tenta reativá-lo mantendo esse papel, **então** a reativação é recusada
   com o motivo; desmarcando o papel, ela prossegue.
10. **Dado** um setor com chefe e mais um membro ativo, **quando** o administrador tenta desativá-lo,
    **então** a operação é recusada; depois de transferido o membro, a desativação é aceita.
11. **Dado** o setor Almoxarifado ativo, **quando** o administrador tenta desativá-lo, **então** a
    operação é sempre recusada.
12. **Dado** um usuário com sessão aberta, **quando** o administrador o desativa, **então** a próxima
    interação dele é recusada (`INV-AUTH-001`).
13. **Dado** o único administrador ativo, **quando** ele tenta desativar a própria conta ou retirar
    de si `ROLE-SYSTEM-ADMIN`, **então** a operação é recusada.
14. **Dado** um usuário recém-criado, **quando** autentica com a senha provisória, **então** só
    consegue definir a própria senha antes de acessar qualquer outra superfície; depois disso,
    usa a nova senha normalmente.
15. **Dado** um usuário com sessão aberta, **quando** o administrador redefine sua senha, **então**
    a sessão deixa de valer, e a senha provisória só aparece uma vez para o administrador.
16. **Dado** um usuário autenticado, **quando** troca a própria senha informando a atual
    corretamente, **então** a nova passa a valer, as outras sessões dele são encerradas e o
    histórico registra o evento sem a senha; com a senha atual errada, nada muda.
17. **Dado** um setor chamado "ETA", **quando** o administrador cria ou renomeia outro setor como
    " eta ", **então** a operação é recusada por nome repetido.
18. **Dado** duas substituições concorrentes do chefe do mesmo setor, **quando** ambas são
    confirmadas, **então** uma é aplicada e a outra é recusada por ter sido avaliada sobre o novo
    estado; o setor nunca fica com zero ou dois chefes.
19. **Dado** uma alteração de papel feita pelo Django Admin, **quando** ela é salva, **então** as
    mesmas regras se aplicam e o mesmo evento de histórico é gerado.

## 6. Impactos em regras canônicas e outras capacidades

| Artefato | Impacto | Situação |
|---|---|---|
| `docs/domain/invariants-matrix.md` | Novas `INV-ORG-004` (setor Almoxarifado único, fixo, nunca desativado depois de ativo), `INV-ORG-005` (papéis de almoxarifado só no Almoxarifado), `INV-ORG-006` (chefia de estoque acoplada à chefia do setor Almoxarifado). A seção 4 deixa de dizer que desativação de setor não tem regra nenhuma. | Aplicado nesta sessão (D-04, D-17) |
| `docs/domain/permissions-matrix.md` | Condições de `PERM-USER-MANAGE` e `PERM-SECTOR-MANAGE` passam a citar `INV-ORG-*`. A nota de composição do chefe do almoxarifado passa a citar `INV-ORG-006`. Nenhuma capability criada ou ampliada. | Aplicado nesta sessão |
| `specs/002-autenticacao-login/spec.md` | SC-001 emendado: exceção para credencial provisória. Clarificação registrada. | Aplicado nesta sessão (D-13) |
| `ROADMAP.md` | "Inclui" de ORG ampliado (D-13, D-14). Pendências de ORG e de REQ/ATE apontam para este documento. Status de ORG continua "Planejada". | Aplicado nesta sessão |
| REQ | Precisa gravar o setor do beneficiário na criação e o autor da decisão (D-19), canonizar `INV-REQ-001`, entregar a trava de desativação de setor (D-20) e definir o tratamento de beneficiário inativo. A escolha do beneficiário por nome passa a ser possível (D-05). | A cargo da spec de REQ |
| ATE | Sem impacto de atribuição (D-21, item 4). As atribuições exclusivas de estoque seguem a chefia do Almoxarifado (D-04). | Nenhuma ação |
| REL | O consumo por setor permanece estável depois de transferências (D-19). | Nenhuma ação |
| 002 implementada | O plan de ORG precisa acrescentar nome ao usuário, unicidade de nome de setor, designação do Almoxarifado, histórico organizacional, senha provisória e troca obrigatória, e ajustar Django Admin, `seed_dev` e testes de `contas`. | A cargo do plan de ORG |
| Telas existentes | Entradas mostram só a matrícula do autor; com D-05, poderão mostrar o nome. Ajuste opcional, fora do recorte de ORG. | Registrar à parte, se desejado |

## 7. Fora do que foi decidido

Não foram decididos, e a spec de ORG não deve presumir: estados de requisição, cancelamentos ou
reserva (REQ/ATE); delegação de aprovação; designação temporária com prazo; acesso do auditor ao
histórico organizacional; recuperação de senha sem o administrador; e-mail, notificações ou SSO.

## 8. Pendências remanescentes

| Pendência | Onde se resolve | O que bloqueia |
|---|---|---|
| Destino depois da definição obrigatória de senha: retornar ao destino original (regras de FR-010 da 002) ou ir à Home. | `clarify` de ORG | Nada antes da spec; fixar antes do plan. |
| Validade da senha provisória (expira ou não). | `clarify` de ORG | Idem. |
| Tamanho e formato do nome completo; política de senha além dos validadores do Django. | `clarify`/plan de ORG | Nada; sem evidência de necessidade além do padrão. |
| Django Admin somente leitura ou com escrita protegida para dados organizacionais (D-22). | plan de ORG | Nada antes do plan. |
| Estados que contam como "não encerrada" e tratamento de beneficiário inativo (D-20). | spec de REQ/ATE | A trava de desativação de setor só existe quando REQ for entregue. |
| Canonizar `INV-REQ-001` (D-19). | spec de REQ | Implementação de REQ. |

## 9. Resumo para o `speckit-specify`

Feature `ORG — Administração de usuários, papéis e setores`. O administrador de sistema
(`PERM-USER-MANAGE`, `PERM-SECTOR-MANAGE`) mantém usuários (matrícula e nome completo), setores
(nome único), vínculos setoriais e atribuições dos papéis canônicos. Isso inclui substituição
atômica de chefia, transferência com remoção explícita de papéis presos ao setor, desativação e
reativação com revisão de papéis, desativação de setor só com o chefe restante, histórico
organizacional consultável, entrega e redefinição de senha provisória com troca obrigatória e
troca voluntária da própria senha.

Preserva `INV-ORG-001` a `INV-ORG-006`, `INV-AUTH-001` e FR-016a, FR-019 a FR-023 da 002.
Não inclui redefinir papéis, conceder poderes implícitos, gestão de estoque, redefinir o login,
recuperação sem o administrador, e-mail, notificações ou SSO.
Dependência obrigatória: 002 (entregue). Recomendada antes do uso amplo de REQ, sem bloqueá-la.
Decisões D-01 a D-27 e pendências da seção 8 acima.
