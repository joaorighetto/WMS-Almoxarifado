# Implementation Plan: Administração de Usuários, Papéis e Setores

**Branch**: `claude/005-administracao-usuarios-setores`, criada a partir de `main` em 2026-10-01 | **Date**: 2026-10-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/005-administracao-usuarios-setores/spec.md`

## Summary

O administrador de sistema passa a manter, no próprio WMS, usuários (matrícula e nome), setores
(nome único), vínculo setorial e papéis canônicos: cadastro com senha provisória exibida uma vez,
transferência com remoção explícita dos papéis presos ao setor, substituição atômica de chefia
(no Almoxarifado, junto com a chefia de estoque), desativação e reativação com revisão de papéis,
ciclo de vida de setores e histórico organizacional consultável. Todo usuário define a própria
senha no primeiro acesso e pode trocá-la depois.

Abordagem técnica: as operações ficam em `contas/organizacao.py`, cada uma numa transação
serializada por um advisory lock único de organização, com as regras validadas sobre o **estado
final** — o que torna possível a substituição atômica, hoje bloqueada pelas guardas por `save()` da
002. Uma barreira de escrita faz qualquer gravação organizacional fora dessas operações falhar, e o
banco protege as invariantes com constraints e um trigger de verificação adiado para o commit. O
histórico é um model só de acréscimo, imutável por trigger. A senha provisória vence em 7 dias pelo
backend de autenticação, e um middleware restringe a conta provisória à definição da senha. O Django
Admin fica somente leitura; o provisionamento inicial vira um comando próprio. Nenhuma dependência
nova. Decisões em [research.md](./research.md).

## Situação no roadmap e prontidão

- **Linha do ROADMAP**: `ORG` — Inclui: gestão pelo administrador de sistema; vínculo setorial;
  atribuição dos papéis canônicos; manutenção das invariantes organizacionais; entrega e redefinição
  de credenciais pelo administrador; troca da própria senha. **Não inclui**: redefinir papéis;
  conceder poderes operacionais implícitos; gestão de estoque; redefinir o login; recuperação de
  senha sem o administrador. Este plano não atravessa nenhuma exclusão: o login da 002 ganha só a
  etapa de definição obrigatória, já prevista na emenda ao SC-001, e o backend de autenticação só
  acrescenta a recusa por vencimento, com a mesma mensagem.
- **Dependências obrigatórias**: `002` (Autenticação e acesso inicial), entregue. A recomendação de
  entregar antes do uso amplo de `REQ` (Solicitação e autorização de materiais) não bloqueia nada.
- **Decisões pendentes da capacidade**: todas fixadas na spec (`clarify` de 2026-10-01). A única
  pendência deixada ao plan — Django Admin somente leitura ou com escrita protegida — é decidida em
  research R6. A trava de desativação de setor por requisições é da spec de `REQ` (research R17).
- **Fronteira com REQ**: nenhum model de outro app é lido ou escrito; o ponto de extensão da
  desativação de setor é único e documentado, sem mecanismo genérico.

## Technical Context

**Language/Version**: Python 3.13; Django 6.x (`django>=6.0`).

**Primary Dependencies**: `django` (com `django.contrib.postgres`), `psycopg`. HTMX já versionado em
`static/vendor/htmx/`. Nenhum pacote novo.

**Storage**: PostgreSQL 16. Esquema efêmero, sem migrations (`make resetdb`). Constraints
funcionais (`Lower(Trim(...))`) e `UniqueConstraint` com `condition`; triggers e o trigger de
verificação adiado criados no `post_migrate` de `contas`, idempotentes, no molde de `estoque/apps.py`.

**Testing**: pytest + pytest-django. `django_db(transaction=True)` com `threading.Barrier` para
concorrência e para o trigger adiado (testes não transacionais não fazem commit); `SET CONSTRAINTS
ALL IMMEDIATE` onde for mais simples. Relógio controlado por `monkeypatch` de `timezone.now` para o
vencimento. Fixtures de `tests/conftest.py` passam a criar a organização pelas operações.

**Target Platform**: servidor Linux; desktop do administrador.

**Project Type**: aplicação Django monolítica server-rendered.

**Performance Goals**: listas paginadas (50) com papéis em `prefetch_related` e chefe/membros
anotados numa consulta; busca por `nome_busca` sem índice especial (centenas de usuários).

**Constraints**: nenhuma recusa deixa estado parcial (FR-047); operações serializadas; invariantes
`INV-ORG-001` a `INV-ORG-006` verdadeiras por qualquer caminho (FR-046); senha provisória nunca
persistida em claro nem exibida duas vezes (FR-031); histórico imutável (FR-041).

**Scale/Scope**: um administrador; dezenas a poucas centenas de usuários; algumas dezenas de setores;
17 templates de página novos (16 de administração e `/senha/`, com suas duas variantes).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Princípio | Status | Justificativa |
|---|---|---|
| I. Simplicidade | PASS, com justificativas | Models, forms, CBVs, `ModelBackend` e middleware nativos. Módulo de domínio, barreira de escrita, triggers e middleware de credencial justificados em Complexity Tracking. Sem registro genérico de condições para REQ (research R17), sem biblioteca de auditoria (R7). Remove `_bloquear_atribuicao` e as guardas por `save()` da 002. |
| II. Server-Driven | PASS | Django Templates; prévias e confirmações por POST comum; HTMX só nos filtros das listas. |
| III. Integridade de Dados | PASS | Transação única por operação; advisory lock único (R2); validação do estado final (R3); constraints de nome, designação e ativação; trigger adiado para `INV-ORG-002/005/006` e papel mínimo (R5). |
| IV. Rastreabilidade | PASS | `EventoOrganizacional` só de acréscimo, com autor, momento, alvos e anterior/novo, imutável por trigger; nada é excluído. |
| V. Regras no Backend | PASS | Toda regra em `contas.organizacao`/`contas.credenciais`; as views passam flags prontas ("pode desativar", papéis editáveis); a confirmação revalida a prévia sob lock. |
| VI. Segurança | PASS | `ExigePapelMixin(ADMINISTRADOR_SISTEMA)` em GET e POST; restrição da credencial provisória em middleware, não por view; senha só na resposta `no-store`; recusa por vencimento indistinguível; nenhuma senha em log ou evento. |
| VII. Testes | PASS | Por risco (research R19): invariantes, concorrência, banco, barreira, credenciais, permissões e regressão integral de FR-016a e FR-019 a FR-023 da 002. |
| VIII. Design System | PASS, com gate pendente | Reusa Page Header, Filter Bar, Table, Badge, Pagination, Alert, Empty State, Confirmação e Retorno contextual. Novidades prováveis: bloco de exibição única da senha provisória e lista de papéis com estado bloqueado. `frontend-implementer` com `frontend-design`; `impeccable critique` depois do `code-reviewer`; `impeccable document` (scan) para `DESIGN.md` e sidecar. |
| IX. Progressive Enhancement | PASS | Tudo funciona por GET/POST comuns; o HTMX só evita recarregar a lista. |
| X. Performance | PASS | Paginação; `prefetch_related`/`annotate`; lock só nas operações de escrita, que são raras. |
| XI. Dependências | PASS | Nenhuma nova. |
| XII. Manutenibilidade | PASS | Nomes do domínio (`cadastrar_usuario`, `substituir_chefia`, `EventoOrganizacional`); uma função por operação da spec. |
| XIII. Migrações | PASS | Esquema efêmero; o SQL dos triggers vira `RunSQL` quando as migrations voltarem. |
| XIV. Observabilidade | PASS | Logger `contas.organizacao` com tipo, ids e autor; nunca senha (R18). |

**Re-check pós-design**: `data-model.md` e os contratos mantêm todos os itens. Nenhuma violação nova.

## Project Structure

### Documentation (this feature)

```text
specs/005-administracao-usuarios-setores/
├── spec.md
├── plan.md                              # este arquivo
├── research.md                          # R1–R19
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── rotas-e-autorizacao.md           # rotas, capability, respostas, matriz de teste
│   ├── operacoes-organizacionais.md     # assinaturas, recusas, efeitos, eventos
│   └── credenciais.md                   # senha provisória, vencimento, middleware, /senha/
├── checklists/requirements.md
└── tasks.md                             # /speckit-tasks
```

### Source Code (repository root)

```text
config/settings/base.py            # ALTERADO: AUTHENTICATION_BACKENDS = contas.backends.WMSModelBackend;
                                   #   MIDDLEWARE += CredencialProvisoriaMiddleware (após Authentication);
                                   #   UserAttributeSimilarityValidator(user_attributes=matricula, nome);
                                   #   logger "contas.organizacao"

contas/
├── apps.py                        # ALTERADO: post_migrate → triggers de setor, histórico e verificação adiada
├── models.py                      # ALTERADO: User.nome/nome_busca/senha_provisoria_em; Setor.almoxarifado/
│                                  #   ativado_em + constraints; EventoOrganizacional, TipoEvento;
│                                  #   barreira de escrita nos save/delete/QuerySet; remove guardas por save()
│                                  #   e _bloquear_atribuicao (research R3, R4)
├── organizacao.py                 # NOVO: operações, prévias, validar_organizacao, OperacaoRecusada,
│                                  #   CHAVE_LOCK_ORGANIZACAO, provisionamento (research R1–R3, R15, R17)
├── credenciais.py                 # NOVO: gerar_senha_provisoria, VALIDADE_SENHA_PROVISORIA,
│                                  #   definir_propria_senha, trocar_propria_senha (research R8–R12)
├── backends.py                    # NOVO: WMSModelBackend (vencimento, research R9)
├── middleware.py                  # ALTERADO: + CredencialProvisoriaMiddleware (research R10)
├── admin.py                       # ALTERADO: somente leitura; EventoOrganizacional para consulta (R6)
├── forms.py                       # ALTERADO: forms de usuário, papéis, transferência, chefia,
│                                  #   reativação, setor, senha, filtros
├── views.py                       # ALTERADO: views de /organizacao/ e /senha/; HomeView
│                                  #   (pode_administrar_organizacao; ORG sai de CAPACIDADES_PLANEJADAS)
├── urls.py                        # ALTERADO: rotas de rotas-e-autorizacao.md
├── management/commands/
│   ├── provisionar_organizacao.py # NOVO (research R15)
│   └── seed_dev.py                # ALTERADO: organização pelas operações; almox designado; nomes
├── dev_seed/dados.py              # ALTERADO: nome fictício por conta
├── templates/contas/
│   ├── _barra_trabalho.html       # ALTERADO: link "Senha"
│   ├── home.html                  # ALTERADO: atalhos Usuários e Setores
│   ├── senha.html                 # NOVO: definição obrigatória e troca voluntária
│   └── organizacao/               # NOVO: usuarios, usuario (ficha), usuario_form, usuario_senha_entregue,
│                                  #   usuario_editar, usuario_papeis, usuario_transferir, usuario_desativar,
│                                  #   usuario_reativar, usuario_redefinir_senha, setores, setor (ficha),
│                                  #   setor_form, setor_chefia, setor_ativar, setor_desativar,
│                                  #   _historico, _resultados_usuarios
└── static/contas/css/organizacao.css  # NOVO, só se a composição exigir

docs/development/seed-dev.md, login-simulado.md   # ALTERADOS: nomes, almox designado, provisionamento
DESIGN.md, .impeccable/design.json                # ALTERADOS na entrega, por `impeccable document` (scan)

tests/
├── conftest.py                              # ALTERADO: setor Almoxarifado designado; usuários e papéis
│                                            #   criados pelas operações; nome nas fábricas
├── test_contas_organizacao.py               # REESCRITO: FR-019 a FR-023 da 002 sobre as operações
├── test_contas_revisao_integridade.py       # REESCRITO: FR-016a e regressões da revisão do PR 5
├── test_contas_models.py                    # ALTERADO: constraints, barreira de escrita
├── test_contas_admin.py                     # REESCRITO: Admin somente leitura
├── test_contas_banco.py                     # NOVO: trigger adiado, imutabilidade (transacional)
├── test_contas_operacoes_usuario.py         # NOVO: cadastro, edição, papéis, transferência
├── test_contas_operacoes_chefia.py          # NOVO: designação, retirada, substituição, almoxarifado
├── test_contas_operacoes_situacao.py        # NOVO: desativação, reativação, proteções do administrador
├── test_contas_operacoes_setor.py           # NOVO: criar, renomear, ativar, desativar
├── test_contas_concorrencia.py              # NOVO: transacional (research R19)
├── test_contas_historico.py                 # NOVO: eventos por operação, sem senha, imutáveis
├── test_contas_credenciais.py               # NOVO: provisória, vencimento, middleware, /senha/, sessões
├── test_contas_views_organizacao.py         # NOVO: fluxos HTTP, prévias, respostas no-store
├── test_contas_permissoes_organizacao.py    # NOVO: matriz rota × papel, sem escrita quando negado
├── test_contas_provisionamento.py           # NOVO: comando provisionar_organizacao
├── test_contas_home_papeis.py               # ALTERADO: atalhos de ORG
└── test_seed_dev.py                         # ALTERADO: almox designado, invariantes válidas
```

**Structure Decision**: tudo em `contas`, dono dos models organizacionais, com a mesma divisão de
`estoque` (módulo de domínio, views finas, testes em `tests/` com o prefixo do app).

## Fluxos

### Operação com prévia (transferência; substituição e reativação são análogas)

```text
GET  /organizacao/usuarios/<pk>/transferir/             [ADMINISTRADOR_SISTEMA]
  formulário: setor de destino

POST /organizacao/usuarios/<pk>/transferir/  (sem confirmar)
  previa_transferencia(pk, destino)          # só leitura
    → página de confirmação: papéis que serão removidos + campos ocultos

POST /organizacao/usuarios/<pk>/transferir/  (confirmar=1, papeis_removidos_previstos)
  transferir_usuario(autor, pk, destino, papeis_removidos_previstos):
    transaction.atomic():
      pg_advisory_xact_lock(CHAVE_LOCK_ORGANIZACAO); barreira ligada
      relê usuário → chefe de setor ativo? destino = atual? → OperacaoRecusada
      papéis presos calculados ≠ previstos → PreviaDesatualizada (view mostra nova prévia)
      UPDATE User.setor; DELETE PapelUsuario presos
      validar_organizacao({origem, destino}, {usuário})
      INSERT EventoOrganizacional(USUARIO_TRANSFERIDO)
    [commit → trigger adiado verifica de novo]
  302 ficha
```

### Cadastro com senha provisória

```text
POST /organizacao/usuarios/novo/  (chave_confirmacao)
  cadastrar_usuario(...):
    lock; chave já usada → OperacaoJaExecutada → 302 ficha, sem senha
    regras de FR-008; create_user dentro da barreira; papéis; senha_provisoria_em = agora
    validar_organizacao; eventos USUARIO_CADASTRADO (chave) + SENHA_PROVISORIA_GERADA
  200 usuario_senha_entregue.html com a senha (Cache-Control: no-store)
```

### Primeiro acesso

```text
POST /login/  (credenciais provisórias válidas, não vencidas)
  WMSModelBackend aceita → sessão; marcador de destino gravado como na 002
qualquer GET → CredencialProvisoriaMiddleware → 302 /senha/
POST /senha/ → definir_propria_senha → update_session_auth_hash → 302 destino do marcador ou Home
```

## Autorização

Ver [rotas-e-autorizacao.md](./contracts/rotas-e-autorizacao.md). Usuários → `PERM-USER-MANAGE`;
setores → `PERM-SECTOR-MANAGE`; ambos só `ROLE-SYSTEM-ADMIN`, por `ExigePapelMixin`. `/senha/` não é
capability (D-27, FR-039): só login exigido. O papel de administrador não concede nada operacional:
nenhuma view de outro app muda. Nenhuma capability é criada, ampliada ou redefinida.

## Regras canônicas aplicadas e preservadas

| ID | Mecanismo |
|---|---|
| `PERM-USER-MANAGE`, `PERM-SECTOR-MANAGE` | `ExigePapelMixin(ADMINISTRADOR_SISTEMA)` em toda rota de `/organizacao/`, GET e POST; conta técnica fora das listas e 404 nas fichas |
| `INV-ORG-001` | `User.setor` obrigatório (`PROTECT`); transferência só troca o valor |
| `INV-ORG-002` | regras por operação + `validar_organizacao` + trigger adiado; substituição atômica sob lock com chefe esperado |
| `INV-ORG-003` | estrutural (chefia derivada do setor único do usuário), como na 002 |
| `INV-ORG-004` | `Setor.almoxarifado` com unicidade parcial e trigger de imutabilidade; `CHECK` de não desativação depois de `ativado_em`; só o provisionamento designa |
| `INV-ORG-005` | recusa em cadastro, papéis e reativação; transferência remove os papéis; trigger adiado |
| `INV-ORG-006` | designação, retirada e substituição movem `ROLE-SECTOR-HEAD` e `ROLE-WAREHOUSE-HEAD` juntos; validação final e trigger adiado |
| `INV-AUTH-001` | comportamento da 002 (`ModelBackend.get_user`); desativação preserva papéis; middleware de credencial não age em inativo |
| FR-016a (002) | papel mínimo concedido no cadastro; remoção recusada; validação final e trigger; conta técnica sem papéis |
| FR-019 a FR-023 (002) | setor nasce inativo; ativação com exatamente um chefe; nenhuma operação deixa setor ativo sem chefe nem com dois; atomicidade estendida a todas as operações |

## Testes

Priorizados por risco; o `test-engineer` revisa e completa antes da implementação (research R19).
Os cenários CRÍTICOS:

- **Invariantes**: cada operação, em cada caso da tabela de recusas, deixa o estado intacto e sem
  evento; depois de qualquer sequência válida, `validar_organizacao` sobre tudo não recusa.
- **Substituição**: setor comum e Almoxarifado; nunca zero nem dois chefes, nem dois chefes do
  almoxarifado; concorrência de duas substituições e de substituição × transferência.
- **Último administrador**: desativações e remoções de papel concorrentes de dois administradores.
- **Banco**: o trigger adiado recusa, por SQL direto, cada violação de `data-model.md`; histórico e
  designação imutáveis.
- **Credenciais**: senha exibida uma vez, nunca no evento, log ou sessão; F5 com a mesma chave;
  vencimento com relógio controlado; middleware em todas as rotas; FR-034; sessões encerradas.
- **Regressão da 002**: nenhum caso de FR-016a e FR-019 a FR-023 deixa de ser coberto ao reescrever
  `test_contas_organizacao.py` e `test_contas_revisao_integridade.py`.

## Pipeline de implementação

Segurança, permissões e invariantes CRÍTICAS, com frontend significativo:

```text
test-engineer (cenários críticos acima e matriz de permissões)
→ task-implementer (models, constraints, triggers, barreira, organizacao, credenciais, backend,
  middleware, admin, provisionamento, seed_dev, conftest, views sem acabamento visual, testes)
→ frontend-implementer (telas de /organizacao/, /senha/, Home, barra de trabalho)
→ code-reviewer
→ impeccable critique (gate visual, como administrador-sistema; /senha/ nos dois estados)
→ correções
→ impeccable document (scan) para DESIGN.md e sidecar
→ converge
```

O `wms-explorer` não foi invocado: a exploração de `contas`, do Admin, do `seed_dev`, das fixtures e
do padrão de triggers de `estoque` foi feita diretamente nesta fase. Pontos de impacto confirmados:
toda a suíte depende de `tests/conftest.py`, que cria usuários e papéis pelo ORM e usa o setor
"Almoxarifado Central" sem designação — as fábricas passam a usar as operações e a designar esse
setor como Almoxarifado; `seed_dev` e `login_simulado` dependem das contas fictícias.

## Spec/domain check

- **Spec**: FR-001 a FR-053 e SC-001 a SC-008 têm mecanismo (data-model → rastreamento; contratos).
- **Matrizes canônicas**: consistente com `PERM-USER-MANAGE`, `PERM-SECTOR-MANAGE` e `INV-ORG-001` a
  `INV-ORG-006`, `INV-AUTH-001`. A matriz recomenda "banco/constraint" para `INV-ORG-001` a
  `INV-ORG-005`; o plano atende por constraints e trigger adiado (R5). Nenhuma decisão de domínio nova
  fica só no código.
- **002**: FR-016a e FR-019 a FR-023 preservados com outro mecanismo (R3). Mudança de comportamento
  observável só nos caminhos técnicos: o Admin deixa de escrever (R6) e o ORM fora das operações
  passa a recusar (R4) — ambos consequência de D-22.
- **ROADMAP**: dentro do recorte de `ORG`. Status atualizado a cada artefato gerado.
- **Nenhum conflito material.**

## Open Questions

Nenhum PLAN BLOCKER. Não bloqueantes:

1. **Nome na barra de trabalho e na Home**: com `User.nome`, a placa de identificação poderia mostrar
   o nome. Fora do recorte de ORG; fica para decisão à parte.
2. **Alfabeto e tamanho da senha provisória** (R8): escolha de usabilidade na entrega pessoal; pode
   mudar sem tocar a spec.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Módulo de domínio `contas/organizacao.py` | Cada operação atravessa `User`, `Setor`, `PapelUsuario` e o histórico sob lock, e é chamada pela view, pelo provisionamento, pelo `seed_dev`, pelo shell técnico e pelos testes de concorrência. | Na view, a regra ficaria inacessível ao provisionamento e aos testes; nos `save()`, os estados intermediários da substituição são recusados (research R3). |
| Barreira de escrita por `ContextVar` | FR-046/D-22: toda escrita, por qualquer caminho, precisa das mesmas regras e do mesmo evento, e só as operações conhecem o autor e a semântica. | Eventos nos `save()` perdem autor e semântica; só documentar não impede a escrita silenciosa pelo ORM. |
| Trigger de verificação adiado e triggers de imutabilidade em `post_migrate` | Constitution III e a matriz pedem proteção no banco para invariantes CRÍTICAS; as de chefia cruzam tabelas e passam por estados intermediários; histórico e designação precisam ser imutáveis. | Só constraints simples não expressam chefia nem composição; trigger imediato recusa a substituição; migration com `RunSQL` não existe na fase atual (Constitution XIII). |
| Backend de autenticação e middleware de credencial provisória | O Django não tem troca obrigatória de senha nem vencimento; a restrição precisa valer em toda rota atual e futura, e a recusa por vencimento precisa ser idêntica às demais. | Checar em cada view deixa rotas novas abertas; checar no login produz mensagem diferente e não cobre sessão aberta. |
