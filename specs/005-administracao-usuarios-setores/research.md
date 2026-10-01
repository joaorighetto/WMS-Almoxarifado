# Research — Administração de Usuários, Papéis e Setores

Decisões técnicas do plano da 005. Cada item registra a decisão, a justificativa e as alternativas
descartadas. Base observada no código em 2026-10-01: `contas/models.py` (guardas por `save()`,
`_bloquear_atribuicao`, `QuerySet` fechados), `contas/admin.py`, `contas/management/commands/seed_dev.py`,
`estoque/apps.py` (triggers em `post_migrate`), `estoque/entradas.py` (módulo de domínio) e
`tests/conftest.py`.

## R1 — Operações num módulo de domínio `contas/organizacao.py`

**Decisão**: cada operação da spec é uma função de `contas/organizacao.py` — `cadastrar_usuario`,
`editar_usuario`, `alterar_papeis`, `transferir_usuario`, `designar_chefia`, `retirar_chefia`,
`substituir_chefia`, `desativar_usuario`, `reativar_usuario`, `criar_setor`, `renomear_setor`,
`ativar_setor`, `desativar_setor`, `redefinir_senha` — mais as funções de prévia, só de leitura,
usadas pelas telas de confirmação (`previa_transferencia`, `previa_reativacao`,
`previa_substituicao`). Cada operação: abre `transaction.atomic()`, toma o lock de R2, relê o estado
atual, aplica as regras da spec, escreve, valida o estado final (R3) e registra o evento (R7). Recusa
é a exceção `OperacaoRecusada(motivo, caminho)`, que a view mostra como está (FR-048). As funções de
credencial do próprio usuário ficam em `contas/credenciais.py` (R8 a R11).

**Justificativa**: as operações atravessam `User`, `Setor`, `PapelUsuario` e o histórico, sob lock,
e precisam ser chamadas pela view, pelo provisionamento, pelo `seed_dev`, pelo shell técnico e pelos
testes de concorrência. É o mesmo desenho de `estoque/entradas.py` na 003.

**Alternativas descartadas**: regras nas views (inacessíveis ao provisionamento e aos testes de
concorrência sem cliente HTTP); regras só nos `save()` dos models (R3 mostra por que não bastam);
forms com a regra (misturam HTTP e domínio, Constitution V).

## R2 — Serialização por um advisory lock único de organização

**Decisão**: toda operação de escrita organizacional começa com
`pg_advisory_xact_lock(CHAVE_LOCK_ORGANIZACAO)`, constante própria, distinta das chaves de
importação. Isso serializa todas as operações de ORG entre si (D-24, FR-047): a segunda sempre é
avaliada sobre o resultado da primeira. A substituição recebe o chefe esperado e, já sob o lock,
recusa se ele não for mais o chefe (FR-017).

**Justificativa**: o volume é mínimo — um administrador, dezenas a centenas de usuários — e as
operações tocam conjuntos variáveis de linhas (o último administrador ativo, a chefia de dois
setores numa transferência, a chefia do almoxarifado). Um lock único elimina a ordem de locks por
linha e o risco de deadlock que hoje exige `_bloquear_atribuicao` com repetição. O login e a
atualização de `last_login` não tomam o lock.

**Alternativas descartadas**: `select_for_update` por linha em ordem fixa (o desenho atual da 002):
para "último administrador ativo" exigiria travar um conjunto que muda dentro da própria operação, e
a substituição não tem uma linha natural para travar antes de saber quem é o chefe; nível de
isolamento `SERIALIZABLE` com repetição: exige laço de retry em toda view e complica a mensagem de
recusa.

## R3 — Regras validadas sobre o estado final da operação

**Decisão**: as guardas por `save()` da 002 (`_exigir_chefia_preservada`,
`_exigir_chefia_nao_duplicada`, a lógica de `User.save()` e de `PapelUsuario.save()/delete()`, e
`_bloquear_atribuicao`) são substituídas por uma função `validar_organizacao(setores, usuarios)`
chamada ao fim de cada operação, antes do commit, sobre o estado já escrito. Ela verifica
`INV-ORG-001` a `INV-ORG-006` e o papel mínimo de FR-016a da 002 nos setores e usuários afetados, e
levanta `OperacaoRecusada` com a regra violada. As regras próprias de cada operação (por exemplo, a
recusa de remover `ROLE-SECTOR-HEAD` do chefe de setor ativo fora da substituição, ou de desativar a
própria conta) continuam verificadas antes de escrever, com motivo e caminho específicos.

**Justificativa**: a substituição atômica (FR-014) passa necessariamente por um estado intermediário
que as guardas por `save()` recusam — tirar o papel do chefe antes deixa o setor sem chefe (FR-021),
dar ao novo antes cria dois (FR-022). É exatamente o impasse que o brainstorming registrou. A
validação do estado final preserva FR-019 a FR-023 da 002 sem esse impasse.

**Alternativas descartadas**: manter as guardas e desligá-las por flag durante a substituição (dois
mecanismos para a mesma regra, e a flag vira um atalho); fazer a substituição reapontar a linha de
`PapelUsuario` do chefe (as guardas atuais também recusam, porque olham o banco linha a linha).

## R4 — Barreira de escrita: só `contas.organizacao` escreve dados organizacionais

**Decisão**: um `ContextVar` privado de `contas.organizacao` marca a operação em curso. Fora dele,
são recusados (`ValidationError`): `save()` e `delete()` de `Setor` e `PapelUsuario`; `save()` de
identidade de negócio (`is_superuser=False`) que altere `matricula`, `nome`, `setor`, `is_active`,
`is_superuser` ou `senha_provisoria_em`; `delete()` de `User`; e os atalhos de `QuerySet`
(`create`, `bulk_create`, `update`, `bulk_update`, `delete`) sobre esses campos. Ficam liberados
fora da barreira: criação da conta técnica por `create_superuser`, atualização de `last_login` e a
regravação de hash de senha feita pelo Django no login (`update_fields=["password"]`).

**Justificativa**: D-22 e FR-046 exigem que toda escrita, por qualquer caminho, aplique as mesmas
regras e gere o mesmo evento. Só as operações sabem o autor e a semântica do evento (uma
substituição não é duas alterações de papel soltas). A barreira transforma uma escrita acidental
pelo ORM ou pelo shell em erro explícito, em vez de um estado sem histórico.

**Limite**: quem, no shell técnico, entrar deliberadamente no `ContextVar` privado contorna a
barreira. As regras de integridade continuam garantidas pelo banco (R5); só o evento ficaria
faltando. É o mesmo limite de qualquer controle da aplicação contra acesso direto; registrado nas
Assumptions da spec.

**Alternativas descartadas**: eventos gerados nos `save()` por diferença de campos (perde a
semântica de D-08 e não conhece o autor); só documentar que o shell deve usar as operações (não
cumpre FR-046).

## R5 — Defesa no banco: constraints e um trigger de verificação adiado

**Decisão**:

- **Constraints declaradas nos models**: nome de setor único por `Lower(Trim(nome))`; no máximo um
  setor com `almoxarifado = true` (`UniqueConstraint` com `condition`); setor ativo tem
  `ativado_em`; o Almoxarifado já ativado não fica inativo
  (`almoxarifado = false OR ativado_em IS NULL OR ativo = true`); `nome` e `matricula` de usuário
  não vazios.
- **Trigger de imutabilidade de setor** (`BEFORE UPDATE`): recusa mudar `almoxarifado` e mudar
  `ativado_em` depois de preenchido (`INV-ORG-004`).
- **Trigger de verificação adiado** (`CONSTRAINT TRIGGER ... DEFERRABLE INITIALLY DEFERRED`, `AFTER
  INSERT OR DELETE OR UPDATE OF setor_id, is_active, is_superuser` em `contas_user` e `AFTER INSERT
  OR UPDATE OR DELETE` em `contas_papelusuario` e `contas_setor`, de modo que o login
  (`last_login`) e a regravação do hash de senha não disparem a verificação nem tomem o lock): no
  commit,
  toma o mesmo advisory lock de R2 e verifica, nos setores e usuários tocados, `INV-ORG-002`,
  `INV-ORG-005`, `INV-ORG-006` e o papel mínimo de identidade de negócio ativa (FR-016a da 002).
- **Trigger de imutabilidade do histórico**: `BEFORE UPDATE OR DELETE` em `EventoOrganizacional`
  recusa tudo (R7).

Todos criados em `post_migrate` de `contas`, de forma idempotente, no molde de `estoque/apps.py`.

**Justificativa**: Constitution III exige proteger no banco a invariante crítica que puder ser
expressa ali, e a matriz recomenda "banco/constraint" para `INV-ORG-001` a `INV-ORG-005`. As regras
de chefia cruzam tabelas e passam por estados intermediários dentro da operação (R3), por isso a
verificação é adiada para o commit. Tomar o advisory lock dentro do trigger fecha a anomalia de
escrita concorrente mesmo para SQL direto. `INV-ORG-001` já é estrutural (`setor` obrigatório) e
`INV-ORG-003` decorre dela.

**Efeito nos testes**: testes não transacionais do pytest-django nunca fazem commit, então o
trigger adiado não dispara neles. Os testes do trigger usam `django_db(transaction=True)` ou
`SET CONSTRAINTS ALL IMMEDIATE`. As mensagens de recusa vistas pelo administrador vêm sempre de R3;
o trigger é a última linha de defesa.

**Alternativas descartadas**: nenhuma proteção no banco além de `UNIQUE`/`FK` (o desenho atual,
abaixo do que a Constitution pede); denormalizar `setor` e `is_active` em `PapelUsuario` para usar
índices parciais (duplica estado que precisaria de sincronia própria); trigger imediato (recusaria
os estados intermediários da substituição).

## R6 — Django Admin somente leitura para dados organizacionais

**Decisão**: `UserAdmin`, `SetorAdmin` e `PapelUsuarioAdmin` passam a somente leitura
(`has_add_permission`, `has_change_permission` e `has_delete_permission` retornam `False`; listas e
fichas continuam consultáveis). `EventoOrganizacional` é registrado só para consulta. O provisionamento
inicial é o comando `provisionar_organizacao` (R15). Correções técnicas de emergência são feitas no
shell chamando as operações de `contas.organizacao`, com o superusuário técnico como autor.

**Justificativa**: resolve a pendência que a spec deixou ao plan (D-22). Com escrita protegida, o
Admin precisaria reproduzir prévia de transferência, revisão de reativação, substituição atômica,
senha provisória e eventos — uma segunda interface inteira para as mesmas regras. Com a barreira de
R4, uma escrita pelo Admin falharia de qualquer jeito.

**Alternativas descartadas**: Admin com escrita protegida chamando as operações (duplicação de
fluxo, D-22 o rebaixa a recurso técnico); remover os models do Admin (perde a consulta técnica de
emergência).

## R7 — Histórico organizacional: `EventoOrganizacional`, só de acréscimo

**Decisão**: um model `EventoOrganizacional` com `momento`, `autor` (FK `User`, nula só para o
provisionamento técnico), `tipo` (lista fechada, ver `data-model.md`), `usuario` e
`usuario_relacionado` (FKs nulas), `setor` e `setor_relacionado` (FKs nulas), `dados` (JSON com
valores anteriores e novos), `justificativa` (texto opcional) e `chave_confirmacao` (UUID único,
nulo). Um evento por operação efetivada, gravado na mesma transação; operação sem efeito não gera
evento (Assumptions da spec). A ficha do usuário lista os eventos em que ele é `usuario` ou
`usuario_relacionado`; a do setor, em que ele é `setor` ou `setor_relacionado`. FKs `PROTECT`.
Imutável por trigger (R5).

**Justificativa**: D-08 pede eventos semânticos (substituição, transferência com papéis removidos),
não diffs de linha. Dois pares de FK cobrem as operações que envolvem duas pessoas (substituição) ou
dois setores (transferência) sem tabela de associação. O JSON guarda "anterior/novo" sem uma coluna
por tipo de evento.

**Alternativas descartadas**: biblioteca de auditoria genérica (dependência nova sem necessidade,
Constitution XI, e diffs sem semântica); uma tabela por tipo de evento (multiplica models para uma
consulta só de leitura); M2M de usuários envolvidos (tabela extra para no máximo dois envolvidos).

## R8 — Senha provisória: geração, exibição única e idempotência

**Decisão**: `gerar_senha_provisoria()` usa `secrets` para gerar 12 caracteres de um alfabeto sem
caracteres ambíguos (sem `0/O`, `1/l/I`), garantindo ao menos uma letra e um dígito, e ela passa
pelos validadores de R12. A conta guarda só o hash, como qualquer senha, mais
`senha_provisoria_em` (momento da geração; nulo quando a credencial é definitiva). A senha aparece
na **resposta ao POST** do cadastro ou da redefinição, renderizada diretamente, sem redirect e com
`Cache-Control: no-store` — nunca em sessão, mensagem flash, log ou evento. O formulário carrega uma
`chave_confirmacao` (UUID) gravada no evento: repetir o POST com a mesma chave responde "operação já
executada" e não gera nem mostra outra senha.

**Justificativa**: FR-031 proíbe recuperar a senha depois. Guardá-la na sessão para sobreviver a um
redirect a gravaria no banco de sessões. Sem a chave, um F5 na página da redefinição geraria outra
senha e invalidaria a que o administrador acabou de anotar.

**Alternativas descartadas**: `make_random_password` (removido do Django); senha legível por
palavras (sem ganho para entrega pessoal e com política de R12 mais difícil de garantir);
PRG com a senha em sessão.

## R9 — Vencimento em 7 dias pelo backend de autenticação

**Decisão**: `contas.backends.WMSModelBackend(ModelBackend)` sobrescreve `user_can_authenticate` para
recusar também a credencial provisória vencida (`senha_provisoria_em` há mais de 7 dias). O
`AuthenticationForm` continua mostrando a mesma mensagem genérica de recusa (FR-003 da 002). Sessão
aberta com credencial vencida é encerrada pelo middleware de R10. `AUTHENTICATION_BACKENDS` aponta
para o novo backend. A ficha do usuário mostra "provisória, vence em …" ou "provisória vencida".

**Justificativa**: é o ponto que o próprio `ModelBackend` usa para recusar conta inativa, então a
recusa por vencimento é indistinguível das outras, como a clarificação pediu. A constante
`VALIDADE_SENHA_PROVISORIA = timedelta(days=7)` fica num só lugar.

**Alternativas descartadas**: checar o vencimento na view de login (mensagem diferente ou caminho
paralelo ao `authenticate`); tarefa periódica que invalida senhas (infraestrutura nova sem
necessidade).

## R10 — Definição obrigatória da senha por middleware

**Decisão**: `contas.middleware.CredencialProvisoriaMiddleware`, logo depois de
`AuthenticationMiddleware`. Para usuário autenticado com `senha_provisoria_em` preenchido: se
vencida, faz `logout` e redireciona ao login; senão, só deixa passar a rota de definição de senha
(`definir_senha`), o logout e os arquivos estáticos — qualquer outra rota redireciona para
`definir_senha` (FR-032). O destino da FR-034 reaproveita o marcador de sessão que
`WMSLoginView.form_valid` já grava (`_retorno_pos_login_destino`): depois de definir a senha, a view
redireciona para esse destino quando existir, e o `RetornoPosLoginMiddleware` da 002 já devolve à
Home se ele for proibido. Sem marcador, vai à Home.

**Justificativa**: a restrição precisa valer em toda rota, inclusive nas que outras features
acrescentarem, e não pode depender de cada view lembrar dela (Constitution VI). Reusar o marcador
evita uma segunda lógica de retorno: as três condições de FR-010 da 002 continuam aplicadas pelo
mesmo código.

**Alternativas descartadas**: decorator ou mixin em cada view (uma rota nova esquecida libera o
acesso); passar o destino por `?next=` até a tela da senha (revalidação duplicada de FR-010/FR-011).

## R11 — Encerramento de sessões pelo hash de autenticação da sessão

**Decisão**: o Django já invalida toda sessão cuja `session auth hash` não corresponde à senha
atual. Assim: a redefinição pelo administrador troca o hash e encerra todas as sessões da conta
(FR-033); a definição e a troca da própria senha chamam `update_session_auth_hash` para manter só a
sessão em uso (FR-036, FR-037). A desativação continua coberta pela 002 (`ModelBackend.get_user`
descarta usuário inativo).

**Justificativa**: comportamento nativo e testado do Django, sem varrer a tabela de sessões.

**Alternativas descartadas**: registro próprio de sessões por usuário (estrutura nova sem
necessidade); varrer `django_session` decodificando cada sessão (caro e frágil).

## R12 — Política de senha

**Decisão**: mantém os quatro validadores atuais de `AUTH_PASSWORD_VALIDATORS` e configura
`UserAttributeSimilarityValidator` com `user_attributes=("matricula", "nome")`, porque os atributos
padrão (`username`, `first_name`, `last_name`, `email`) não existem neste `User`. A definição e a
troca chamam `validate_password(senha, usuario)` e recusam também a senha provisória em uso
(`check_password`) (FR-036, FR-038). As mensagens dos validadores já vêm traduzidas em pt-BR.

**Justificativa**: é a política escolhida no `clarify`. Sem configurar os atributos, a recusa por
semelhança com matrícula e nome não aconteceria.

## R13 — Nome único de setor e designação do Almoxarifado

**Decisão**: o nome é gravado sem espaços nas pontas e a unicidade é a constraint funcional
`Lower(Trim("nome"))` (R5). `criar_setor` e `renomear_setor` comparam antes, com a mesma expressão,
para dar a mensagem de nome repetido (FR-025); a constraint cobre a corrida. A designação é o campo
`Setor.almoxarifado`, gravado só pelo provisionamento e imutável no banco. `ativado_em` registra a
primeira ativação e sustenta a regra de nunca desativar o Almoxarifado e a indicação de "já esteve
ativo" (FR-030).

**Alternativas descartadas**: `CITEXT` (extensão nova para um único campo); coluna normalizada
separada (duplica o nome sem ganho sobre a constraint funcional).

## R14 — Consulta de usuários e setores

**Decisão**: lista de usuários paginada (50), só identidades de negócio (`is_superuser=False`, FR-004),
com busca por parte do nome — comparada sem acento e sem diferenciar maiúsculas, com
`normalizar_para_busca` de `catalogo.leitura_scpi` gravado em `User.nome_busca` — ou pela matrícula
exata, e filtros combináveis de setor, situação e papel por GET. Os papéis da página vêm num único
`prefetch_related`. A lista de setores anota chefe e quantidade de membros ativos numa só consulta; contas técnicas
não contam como membro, ali nem na desativação de setor (FR-028).
O filtro é um formulário GET comum; o HTMX só troca a região de resultados, como no catálogo.

**Justificativa**: nomes em português com e sem acento ("João"/"Joao") são o caso comum de busca.
Com centenas de usuários não é preciso índice trigram.

**Alternativas descartadas**: extensão `unaccent` (outra extensão para o mesmo efeito que a função
já existente); busca da matrícula por parte do texto (a matrícula é identificador opaco, FR-001b da
002).

## R15 — Provisionamento e `seed_dev`

**Decisão**: novo comando `provisionar_organizacao --setor-almoxarifado NOME --matricula M --nome N`,
para banco sem nenhum setor nem identidade de negócio. Numa transação, por meio das operações de
`contas.organizacao` com autor nulo: cria o setor designado como Almoxarifado, cadastra a primeira
identidade de negócio nele com `ROLE-SYSTEM-ADMIN`, designa-a chefe do Almoxarifado
(`ROLE-SECTOR-HEAD`, `ROLE-WAREHOUSE-HEAD`, `ROLE-WAREHOUSE-STAFF`), ativa o setor e imprime a senha
provisória uma única vez (FR-050). No SAEP essa pessoa é o dono do produto, que é ao mesmo tempo
administrador e chefe do almoxarifado. O `seed_dev` passa a criar a organização fictícia pelas mesmas
operações, com o setor `almox` designado, cada conta com nome fictício e a senha definitiva
`SEED_DEV_PASSWORD`, que registra o evento com autor nulo. A API de provisionamento só aceita senha
conhecida (`senha=`) com `config.settings.development` ou `config.settings.test`; em qualquer outro
ambiente a chamada é recusada antes de gravar, e o provisionamento sempre gera senha provisória
(FR-031).

**Justificativa**: o provisionamento é o único caminho que cria o Almoxarifado (`INV-ORG-004`) e
precisa produzir de saída um estado válido de `INV-ORG-006`. Usar as mesmas operações garante as
mesmas regras e eventos (FR-046).

**Alternativas descartadas**: provisionar pelo Admin (somente leitura por R6); designar o
Almoxarifado por configuração (`settings`), o que tiraria a designação do banco e da verificação de
R5.

## R16 — Interface no app `contas`, sob `/organizacao/`

**Decisão**: as telas de administração ficam em `contas` (dono dos models), com prefixo
`/organizacao/`, protegidas por `ExigePapelMixin(Papel.ADMINISTRADOR_SISTEMA)` de
`catalogo.views` — o mesmo mixin que `estoque` usa. A tela de senha do próprio usuário fica em
`/senha/`, só com login exigido. Reusa Page Header, Filter Bar, Table, Badge, Pagination, Alert,
Empty State, Confirmação e Retorno contextual do design system. As prévias (transferência,
reativação, substituição) são uma etapa de confirmação do próprio POST: o primeiro envio mostra os
efeitos e o segundo, com `confirmar=1`, executa — tudo revalidado sob o lock. Rotas e respostas em
`contracts/rotas-e-autorizacao.md`.

**Justificativa**: um app novo só para views separaria as telas do código que elas chamam, sem
fronteira de domínio própria. Prévia sem estado no servidor é o padrão da 003.

## R17 — Contrato com REQ sem mecanismo especulativo

**Decisão**: `desativar_setor` concentra as condições de desativação num único ponto documentado.
Não se cria agora registro de condições externas nem sinal: quando a spec de REQ especificar a trava
de requisições não encerradas, ela acrescenta sua condição nesse ponto, com seu próprio motivo de
recusa (FR-053). `contas.organizacao` não importa nem altera nenhum model de outro app (FR-051), o
que é verificável por teste de importação. A autorização no momento da ação (FR-052) já é o
comportamento existente: cada view consulta os papéis atuais na própria requisição.

**Justificativa**: Constitution I proíbe generalização para necessidade hipotética; a condição de
REQ ainda não existe.

**Alternativas descartadas**: lista de callables registrável por outros apps; `Signal` de
"antes de desativar setor".

## R18 — Observabilidade

**Decisão**: logger `contas.organizacao` (INFO) com tipo da operação, ids de usuário e setor e autor;
recusas em INFO com o motivo. Nunca senha, provisória ou não, nem o conteúdo de `dados`. Erro
inesperado em ERROR com traceback e mensagem genérica na tela.

## R19 — Estratégia de testes

**Decisão**: testes por risco, no molde da 003, revisados pelo `test-engineer` antes da
implementação:

- **Invariantes (CRÍTICO)**: para cada operação, o estado final satisfaz `INV-ORG-001` a
  `INV-ORG-006` e FR-016a; tabela de recusas de `contracts/operacoes-organizacionais.md`, cada uma
  sem efeito e sem evento.
- **Concorrência (CRÍTICO, `transaction=True` com `threading.Barrier`)**: duas substituições do mesmo
  setor; substituição × transferência do novo chefe; desativação concorrente dos dois últimos
  administradores; ativação de setor × desativação do chefe; renomeação concorrente para o mesmo
  nome.
- **Banco (CRÍTICO)**: cada constraint de `data-model.md` com `IntegrityError`; trigger adiado
  recusando, por SQL direto, setor ativo sem chefe, segundo chefe do almoxarifado e papel de
  almoxarifado fora dele; imutabilidade do histórico e da designação.
- **Barreira de escrita**: `save()`, `delete()` e atalhos de `QuerySet` fora das operações são
  recusados; `last_login`, rehash de senha e `create_superuser` continuam funcionando.
- **Credenciais**: senha provisória exibida uma vez e nunca no evento, log ou sessão; repetição do
  POST com a mesma chave; vencimento em 7 dias com a mensagem genérica; sessão aberta vencida;
  restrição de rotas pelo middleware; destino de FR-034; encerramento de sessões na redefinição e
  das demais na troca; política de R12.
- **Permissões**: rota × papel de `contracts/rotas-e-autorizacao.md`, incluindo POSTs diretos e a
  verificação de que nada foi gravado.
- **Regressão da 002**: os cenários de FR-016a e FR-019 a FR-023 hoje cobertos por
  `test_contas_organizacao.py` e `test_contas_revisao_integridade.py` são reescritos sobre as
  operações, sem perder nenhum caso; `test_contas_admin.py` passa a cobrir o Admin somente leitura.
- **Contrato com outros recortes**: nenhuma operação escreve fora de `contas`.
