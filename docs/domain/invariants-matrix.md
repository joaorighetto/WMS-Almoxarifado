# Matriz Canônica de Invariantes — WMS-Almoxarifado

```text
Status: VALIDADO
Autoridade: CANÔNICA PARA INVARIANTES DE DOMÍNIO
Versão: 1.1
Última validação: 2026-09-18
Última alteração: 2026-09-25 (INV-ENT-001, INV-SUPPLIER-001 a 005)

Escopo:
propriedades transversais atualmente confirmadas que devem permanecer
verdadeiras nos estados e operações relevantes do WMS.
```

> Esta matriz não pretende antecipar regras de features ainda não especificadas. Novas
> invariantes podem ser adicionadas ou invariantes existentes podem ser alteradas somente através
> de decisão explícita de domínio.

**Origem**:
- `PRODUCT.md`
- `.specify/memory/constitution.md`
- `specs/001-importacao-catalogo-materiais/spec.md`
- decisões do dono do produto de 2026-09-25, na especificação de `specs/003-entrada-materiais` e
  da importação de fornecedores (`FOR`)
- `docs/domain/permissions-matrix.md` (condições de capability usadas como evidência, nunca
  duplicadas sem necessidade)
- `docs/domain/reconciliation/invariants-reconciliation.md` (histórico do raciocínio completo,
  inclusive dos itens não promovidos)

Esta matriz é **parcial por design**: representa somente as propriedades transversais já
confirmadas. A ausência de uma invariante sobre uma feature ainda não especificada não significa
que qualquer comportamento seja permitido nessa área — significa apenas que a propriedade ainda não
foi definida transversalmente. Ver seção 4, "Fora desta matriz".

## 1. Regras canônicas de interpretação

1. Uma invariante descreve uma propriedade do domínio, não sua implementação.
2. Violar uma invariante significa produzir estado ou comportamento incorreto do negócio.
3. Specs, plans, tasks e a implementação devem preservar toda invariante aplicável.
4. Nenhuma spec pode contradizer uma invariante silenciosamente; alterá-la exige decisão explícita
   registrada nesta matriz.
5. Alteração de invariante exige atualização explícita deste documento.
6. IDs `INV-*` publicados são estáveis.
7. IDs aposentados não devem ser reutilizados para outro significado.
8. `docs/domain/permissions-matrix.md` responde **quem** pode agir.
9. `docs/domain/invariants-matrix.md` responde **o que** deve permanecer verdadeiro,
   independentemente de quem executa a operação.

## 2. Catálogo de invariantes

### Organização e autenticação

| ID | Domínio | Invariante | Severidade | Verificação recomendada |
|---|---|---|---|---|
| `INV-ORG-001` | Organização | Todo usuário pertence a um único setor. | CRÍTICA | domínio; banco/constraint |
| `INV-ORG-002` | Organização | Todo setor ativo possui exatamente um chefe ativo, pertencente ao próprio setor. Nenhuma operação sobre usuário ou setor pode deixar um setor ativo sem chefe ativo. | CRÍTICA | domínio; banco/constraint |
| `INV-ORG-003` | Organização | Um chefe responde por um único setor. | CRÍTICA | domínio; banco/constraint |
| `INV-AUTH-001` | Autenticação | Usuário inativo não pode acessar nem executar nenhuma operação no sistema, qualquer que seja o mecanismo de autenticação. | CRÍTICA | autorização |

**Evidência**: `PRODUCT.md`, Operating Context — "Cada funcionário do SAEP pertence a um único
setor. Todo setor ativo tem exatamente um chefe ativo, que pertence a esse mesmo setor; um chefe
responde por um único setor. Essas invariantes são a base de todo escopo 'próprio setor'... sem
elas, esse escopo fica indefinido." `INV-AUTH-001`: Constitution, Princípio VI (segurança por
padrão).

### Catálogo

| ID | Domínio | Invariante | Severidade | Verificação recomendada |
|---|---|---|---|---|
| `INV-CATALOG-001` | Catálogo | `CADPRO` é identificador textual opaco. O WMS não o gera, altera, reformata, completa, converte para número, decompõe ou infere, em nenhuma etapa. | CRÍTICA | domínio; integração |
| `INV-CATALOG-002` | Catálogo | Não podem existir dois materiais com o mesmo `CADPRO` no catálogo. | CRÍTICA | domínio; banco/constraint |
| `INV-CATALOG-003` | Catálogo | Material só entra no catálogo através da importação do SCPI; não existe criação manual de material por nenhum papel. | CRÍTICA | domínio; integração |
| `INV-CATALOG-004` | Catálogo | Os dados cadastrais de um material cuja autoridade é o SCPI (descrição, unidade, detalhamento técnico, classificação) só mudam por nova importação. A observação interna é campo próprio do WMS e não pertence aos dados de autoridade do SCPI. | ALTA | integração; domínio |
| `INV-CATALOG-005` | Catálogo | A unidade de medida de um material é preservada exatamente como recebida do SCPI; não há normalização, unificação ou conversão automática de variações. | ALTA | integração |
| `INV-CATALOG-006` | Catálogo | Inativação de material preserva o material e todo o histórico associado a ele; não equivale a exclusão física. | ALTA | domínio |

**Evidência**: Spec 001, FR-001, FR-002, FR-003, FR-005, FR-006, FR-017, FR-019, FR-020, FR-022,
FR-026; `PRODUCT.md`, Positioning e Capabilities and Constraints; `docs/domain/permissions-matrix.md`,
`PERM-MATERIAL-EDIT-NOTE`; Constitution, Princípio IV (preferência por inativação sobre exclusão).

### Estoque

| ID | Domínio | Invariante | Severidade | Verificação recomendada |
|---|---|---|---|---|
| `INV-STOCK-001` | Estoque | Saldo físico de um material nunca pode ficar negativo. | CRÍTICA | banco/constraint; concorrência |
| `INV-STOCK-002` | Estoque | O saldo de um material é inicialmente estabelecido pela importação do SCPI que cria esse material no WMS e, a partir daí, só é alterado por operação própria do WMS. Importações posteriores nunca sobrescrevem o saldo de material já existente. | CRÍTICA | integração; domínio |
| `INV-STOCK-003` | Estoque | A diferença entre a quantidade observada no arquivo do SCPI e o saldo atual do WMS é informativa: não corrige o saldo automaticamente e não bloqueia nenhuma operação por si só. | ALTA | integração |
| `INV-STOCK-004` | Estoque | Uma operação de estoque composta por alterações dependentes não pode concluir parcialmente. Falha em qualquer parte impede que saldo, histórico ou demais efeitos dependentes permaneçam parcialmente aplicados. | CRÍTICA | transacional; concorrência |

**Evidência**: Constitution, Princípio III (integridade de dados, não-negociável — cita
literalmente "verificação de não-negatividade" e a exigência de atomicidade); Spec 001, FR-016,
FR-028, FR-029, FR-030, FR-038; `permissions-reconciliation.md` §2 (esclarecimento sobre
divergência de saldo). `INV-STOCK-003` é distinta de qualquer eventual divergência entre saldo
físico e saldo reservado — esse segundo conceito continua fora desta matriz (seção 4).

### Movimentações e rastreabilidade

| ID | Domínio | Invariante | Severidade | Verificação recomendada |
|---|---|---|---|---|
| `INV-MOV-001` | Movimentação | Os fatos de uma movimentação de estoque relevantes para saldo, origem da operação e auditoria (quantidade, efeito no saldo, operação de origem, ator e momento) não são alterados nem removidos depois de registrados. Toda correção desses fatos ocorre por um novo registro compensatório e rastreável, nunca por sobrescrita do registro original. | CRÍTICA | domínio; banco/constraint |
| `INV-MOV-002` | Movimentação | Toda alteração de saldo posterior ao estabelecimento inicial do material deve possuir um registro de movimentação correspondente, criado na mesma operação, com informação suficiente para identificar a origem da operação, o ator, a quantidade e o momento. O estabelecimento inicial do saldo pela importação que cria o material segue a rastreabilidade específica da importação SCPI. | CRÍTICA | transacional; domínio |

**Evidência**: Constitution, Princípio IV — "Exclusão física de registros NÃO DEVE ser usada quando
prejudicar rastreabilidade... DEVE ser adotada inativação, cancelamento ou estorno, preservando o
registro original"; e "Operações relevantes DEVEM permitir determinar quem executou, o que foi
alterado, quando ocorreu e qual era o contexto da operação."

`INV-MOV-001` absorve o princípio de preservação/compensação que apareceria em um eventual
`INV-RETURN-001` de estorno: preservar o original, não sobrescrever fatos e registrar compensação
são a mesma propriedade transversal, qualquer que seja a operação estornada (saída excepcional,
devolução ou requisição). Não existe `INV-RETURN-001` separado — ver
`docs/domain/reconciliation/invariants-reconciliation.md`, seção de deduplicação. A reconciliação
matemática entre o somatório de movimentações e o saldo corrente (antiga `LED-02` do legado) é
tratada como propriedade verificável de `INV-MOV-002`, não como invariante própria.

`INV-MOV-001` canoniza somente os fatos historicamente relevantes para saldo, origem e auditoria —
não a imutabilidade absoluta de todo e qualquer campo de um eventual registro de movimentação
(nome de model, schema de colunas, metadados não relevantes para saldo/auditoria). O schema
completo do ledger ainda não foi desenhado; qual conjunto de campos além desses é imutável fica
como decisão da futura feature de movimentações.

### Saída excepcional

| ID | Domínio | Invariante | Severidade | Verificação recomendada |
|---|---|---|---|---|
| `INV-SAE-001` | Saída excepcional | Estorno de saída excepcional é sempre total; não existe estorno parcial. | CRÍTICA | domínio; transacional |
| `INV-SAE-002` | Saída excepcional | Saída excepcional é uma operação de baixa de estoque independente do fluxo de requisição; não nasce de, nem depende do estado de, uma requisição. | ALTA | domínio |

**Evidência**: `docs/domain/permissions-matrix.md`, condição de `PERM-SAE-REVERSE` ("Estorno é
total; justificativa obrigatória"); `PRODUCT.md` — estorno, devolução e saída excepcional como
"operações exclusivas do chefe do almoxarifado", distintas do fluxo de requisição-aprovação-
atendimento.

A atomicidade interna do registro de uma saída excepcional (falha em um item derruba o documento
inteiro) é instância de `INV-STOCK-004`, não uma invariante própria — evita duplicar a mesma
propriedade sob dois IDs.

### Entrada

| ID | Domínio | Invariante | Severidade | Verificação recomendada |
|---|---|---|---|---|
| `INV-ENT-001` | Entrada | Estorno de entrada é sempre total — todos os itens, na quantidade integral — e ocorre no máximo uma vez por entrada; não existe estorno parcial. | CRÍTICA | domínio; transacional |

**Evidência**: `docs/domain/permissions-matrix.md`, condição de `PERM-STOCK-ENTRY-REVERSE`; decisão
do dono do produto de 2026-09-25 (spec 003), no mesmo modelo de `INV-SAE-001`. A atomicidade do
registro e do estorno é instância de `INV-STOCK-004`, e o bloqueio por saldo negativo, de
`INV-STOCK-001`.

### Fornecedor

| ID | Domínio | Invariante | Severidade | Verificação recomendada |
|---|---|---|---|---|
| `INV-SUPPLIER-001` | Fornecedor | O código do fornecedor no SCPI (`CODIF`) é identificador opaco. O WMS não o gera, altera, reformata, completa ou infere. | CRÍTICA | domínio; integração |
| `INV-SUPPLIER-002` | Fornecedor | Não podem existir dois fornecedores com o mesmo `CODIF`. Nome e CNPJ/CPF não identificam o fornecedor. | CRÍTICA | domínio; banco/constraint |
| `INV-SUPPLIER-003` | Fornecedor | Fornecedor só entra no WMS pela importação do SCPI, e seus dados só mudam por nova importação; não existe criação ou edição manual por nenhum papel. | CRÍTICA | domínio; integração |
| `INV-SUPPLIER-004` | Fornecedor | O WMS guarda do fornecedor apenas os dados de identificação — código, nome, nome fantasia, CNPJ/CPF, tipo de pessoa e situação de bloqueio no SCPI. Dados bancários, PIS, endereço, contato e demais dados do arquivo não são armazenados. | ALTA | integração; segurança |
| `INV-SUPPLIER-005` | Fornecedor | Fornecedor bloqueado no SCPI, conforme a última importação, não pode ser emitente de nova entrada. | ALTA | domínio |

**Evidência**: decisões do dono do produto de 2026-09-25 — cadastro de fornecedores só pela
importação do SCPI, dados mínimos, bloqueado não pode ser emitente — e análise do CSV real
(10.035 registros: `CODIF` único e sempre preenchido; 1.690 nomes repetidos; CNPJ/CPF vazio em
3.310 e repetido em 37). Mesmo modelo de `INV-CATALOG-001` a `INV-CATALOG-004`; `PRODUCT.md`,
Product Principles (SCPI como fonte de verdade do cadastro oficial); Constitution, Princípio VI.

### SCPI

| ID | Domínio | Invariante | Severidade | Verificação recomendada |
|---|---|---|---|---|
| `INV-SCPI-001` | SCPI | O WMS não realiza integração automática com o SCPI, em nenhuma direção. O lançamento posterior no sistema oficial permanece processo externo e manual, fora do WMS. | ALTA | integração |

**Evidência**: Spec 001, FR-046; `PRODUCT.md`, Positioning — "não integra com ele automaticamente
em nenhuma direção" — e Operating Context (lançamento manual posterior por qualquer funcionário do
almoxarifado).

## 3. Total

25 invariantes canonizadas.

## 4. Fora desta matriz (deliberadamente, não por esquecimento)

Estas áreas têm candidatos identificados em `docs/domain/reconciliation/invariants-reconciliation.md`,
mas dependem de features ou decisões de produto ainda não especificadas. Não promovê-las agora não
significa que qualquer comportamento seja permitido nessas áreas — significa que a propriedade
transversal ainda não foi definida.

- **Reserva de estoque**: saldo reservado, saldo disponível, autorização gerando reserva, consumo
  de reserva, liberação de reserva, e qualquer divergência entre físico e reservado. Depende do
  mecanismo de reserva de estoque por requisição, ainda não especificado.
- **Máquina de estados de requisição**: rascunho, envio, retorno, cancelamentos por estado,
  atendimento parcial, separação para retirada, cópia de requisição, timeline específica.
  Deliberadamente adiada para uma spec própria de requisições.
- **Saída excepcional — mecânica ainda não especificada**: número público anual, estrutura
  específica do documento, regras de item, e qualquer comportamento relativo a saldo reservado.
  Só a exclusividade de ator e a independência do fluxo de requisição (`INV-SAE-001`,
  `INV-SAE-002`) estão confirmadas hoje.
- **Material inativo — operações além da inativação em si**: quais operações um material inativo
  pode ou não receber (ex.: nova requisição, entrada de estoque por devolução) continua em aberto.
- **Origens completas de movimentação de estoque**: o conjunto total de origens possíveis de uma
  movimentação (importação, entrada, ajuste de inventário, saída excepcional, devolução, estorno)
  ainda não está definido; não há enum canônico.
- **Desativação de setor**: nenhuma regra até que essa capacidade seja especificada.

Ver `docs/domain/reconciliation/invariants-reconciliation.md` para o raciocínio completo por trás
de cada item pendente e as perguntas de produto associadas.
