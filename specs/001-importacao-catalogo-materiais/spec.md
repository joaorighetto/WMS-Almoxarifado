# Feature Specification: Importação Inicial e Consulta do Catálogo de Materiais

**Feature Branch**: `main` (nenhuma branch dedicada — extensão git do Spec Kit não instalada)

**Feature Directory**: `specs/001-importacao-catalogo-materiais`

**Created**: 2026-09-18

**Status**: Draft

**Input**: User description: "Criar a funcionalidade de importação inicial e consulta do catálogo de materiais do WMS-Almoxarifado do SAEP. O SCPI da Fiorilli é o sistema oficial do SAEP. O WMS-Almoxarifado operará o almoxarifado em paralelo, e os lançamentos nele realizados serão posteriormente registrados manualmente no SCPI. Os materiais já existem no SCPI. O WMS-Almoxarifado não deve permitir criação manual de materiais. Cada material importado possui o código oficial do SCPI no campo `CADPRO`, no formato `XXX.YYY.ZZZ`. `CADPRO` deve ser armazenado como texto, preservando pontos e zeros à esquerda; é a referência única entre WMS-Almoxarifado e SCPI, e o WMS não pode gerar, alterar, reformatar, completar, converter para número, decompor ou inferir qualquer parte desse código. A classificação já foi definida no SCPI; esta funcionalidade não classifica materiais, não valida grupos ou subgrupos e não altera o código recebido. A carga inicial vem de CSV UTF-8 com BOM, separado por `;` e com delimitador final, com os campos `CADPRO`, `DISC1`, `UNID1`, `QUAN3` e `DISCR1`. Valores numéricos usam convenção brasileira, com vírgula decimal, e as quantidades devem manter precisão decimal. Zero é saldo válido; ausência de quantidade é erro de importação, nunca zero. A descrição principal não é chave de identificação e descrições iguais não devem ser mescladas. O detalhamento técnico pode estar vazio. Unidades de medida devem ser preservadas como recebidas, sem normalizar variações. A carga contém descrições com quebras físicas de linha sem delimitação CSV, e o processo deve impedir deslocamento de colunas. A importação deve validar o formato de `CADPRO` e a ausência de duplicidade no mesmo arquivo, e gerar resultado auditável com totais e motivos de exceção. A consulta deve permitir localizar materiais pelo código SCPI exato e pela descrição. O estoque importado é a base inicial do WMS; não há integração automática de movimentações com o SCPI."

## Clarifications

### Sessão 2026-09-18

- **Campos de classificação**: `GRUPO`, `SUBGRUPO`, `NOMEGRUPO` e `NOMESUBGRUPO` são armazenados
  como dados recebidos do SCPI e exibidos na consulta, sem qualquer validação (FR-022, FR-023).
- **Reexecução da importação**: é permitida com o catálogo já populado. Materiais existentes têm
  seus dados cadastrais atualizados por `CADPRO` e novos códigos são inseridos. O saldo de material
  já existente nunca é sobrescrito pelo arquivo; diferenças entre o saldo do arquivo e o saldo do
  WMS são apontadas como divergências, para posterior ajuste por inventário dentro do próprio WMS
  (FR-025 a FR-032, FR-047).
- **Entrega do arquivo**: o responsável autorizado envia o arquivo pela interface do sistema e o
  resultado da execução é apresentado na tela (FR-044).

### Sessão 2026-09-18 — análise do arquivo real

Análise de `relacao-de-todos-produtos-importados-do-SCPI.csv` (1588 materiais, 1605 linhas físicas,
21 colunas mais a vazia final). Resultados que alteraram a spec:

- **Quebras de linha também ocorrem em `DISC1`**, não apenas em `DISCR1` — o material
  `004.001.002` tem duas. FR-009 foi corrigido: a recomposição acontece antes da separação dos
  campos e não presume o campo de destino.
- **Aspas duplas são literais de polegada** (434 ocorrências, nenhum campo delimitado por aspas).
  FR-007a foi acrescentado, porque um parser CSV com quoting habilitado desalinha as colunas.
- **`QUAN3` traz ruído de ponto flutuante** (`53,4000000000001`). Definida escala de três casas
  decimais com arredondamento (FR-012, SC-004).
- **Colunas extras do export permanecem fora de escopo**: `CODREDUZ`, `CODBARRA`, `QUANMIN`,
  `VAUN1` e `PRECOMEDIO` ficam para features futuras. `QUANMAX`, `NOCULTAR` e `LOCALFISICO` são
  inúteis no arquivo real — valor único ou integralmente vazio nos 1588 registros.

Confirmações que não exigiram mudança: formato e unicidade de `CADPRO` (1588 válidos, nenhum
duplicado); ausência de vazios em `DISC1`, `UNID1`, `QUAN3` e nos campos de classificação;
descrições repetidas em 14 registros; 33 variantes de unidade de medida; e a validade da heurística
de recomposição, que produz exatamente 22 campos em todos os 1588 registros.

### Sessão 2026-09-18 — reconciliação de permissões (prévia da importação)

- **Execução da importação em duas etapas**: a entrega do arquivo (sessão de clarificação acima)
  deixa de persistir o resultado em um único passo. O sistema agora apresenta uma prévia — totais
  esperados, exceções e divergências — sem gravar nada, e só persiste após confirmação explícita do
  responsável autorizado (FR-044, FR-044a). Decisão do dono do produto, registrada em
  `docs/domain-legacy/reconciliation/permissions-reconciliation.md`, §7.9; não altera nenhum outro
  comportamento desta feature — proibição de criação manual, regras de saldo/divergência, histórico
  de execuções e não normalização de unidade de medida permanecem exatamente como especificados.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Realizar a carga inicial do catálogo (Priority: P1)

O responsável pelo almoxarifado precisa trazer para o WMS-Almoxarifado o catálogo de materiais que
já existe no SCPI, junto com o saldo de estoque de cada item, para que o WMS passe a ter uma base
fiel ao sistema oficial. Ele envia ao sistema o arquivo exportado do SCPI e o sistema processa a
carga, aceitando os registros válidos e recusando os que não atendem às regras, sem nunca inventar,
corrigir ou deslocar dados.

**Why this priority**: sem catálogo não existe nada a consultar nem a movimentar. É a fundação de
todo o WMS e o único ponto em que materiais entram no sistema.

**Independent Test**: enviar um arquivo de carga com registros válidos e verificar que os materiais
passam a existir no sistema com código, descrição, unidade, classificação, detalhamento e saldo
idênticos aos do arquivo. Entrega valor mesmo sem a tela de consulta, pois estabelece a base de
dados oficial.

**Acceptance Scenarios**:

1. **Given** um arquivo de carga com registros íntegros e o catálogo vazio, **When** o responsável
   executa a importação, **Then** cada material é criado com o `CADPRO` exatamente como consta no
   arquivo, incluindo pontos e zeros à esquerda, e com o saldo inicial correspondente.
2. **Given** uma linha cujo `CADPRO` é `000.000.002`, **When** o material é importado e depois
   exibido, **Then** o código apresentado é exatamente `000.000.002`, sem supressão de zeros e sem
   qualquer reformatação.
3. **Given** uma linha cuja quantidade é `0,000`, **When** a importação é executada, **Then** o
   material é importado com saldo zero e não é tratado como erro.
4. **Given** uma linha cuja quantidade está vazia, **When** a importação é executada, **Then** a
   linha é rejeitada e registrada como exceção, e o saldo não é assumido como zero.
5. **Given** duas linhas com a mesma descrição principal e códigos `CADPRO` diferentes, **When** a
   importação é executada, **Then** dois materiais distintos são criados e nenhum registro é
   mesclado.
6. **Given** uma linha cujo detalhamento técnico está vazio, **When** a importação é executada,
   **Then** o material é importado normalmente.
7. **Given** um arquivo contendo os mesmos códigos `CADPRO` em duas linhas, **When** a importação é
   executada, **Then** nenhuma das ocorrências duplicadas é importada e todas são reportadas como
   exceção.
8. **Given** um arquivo com unidades `UN`, `UND`, `M`, `MT` e `MTS`, **When** a importação é
   executada, **Then** cada unidade é gravada exatamente como recebida, sem unificação.
9. **Given** um arquivo cujos campos de classificação vêm preenchidos, **When** a importação é
   executada, **Then** grupo, subgrupo e seus nomes são gravados exatamente como recebidos, sem
   validação e sem influenciar a aceitação do registro.
10. **Given** o registro `004.001.002`, cuja descrição principal está partida em três linhas
    físicas, **When** a importação é executada, **Then** a descrição é recomposta por inteiro e
    nenhum valor das demais colunas é deslocado.
11. **Given** uma descrição contendo aspas duplas como símbolo de polegada, como
    `COTOVELO GALVANIZADO ¾" X 90º`, **When** a importação é executada, **Then** o texto é gravado
    com as aspas preservadas e as colunas seguintes permanecem alinhadas.
12. **Given** o registro `000.029.742`, cuja quantidade no arquivo é `53,4000000000001`, **When** a
    importação é executada, **Then** o saldo gravado é `53,400`.

---

### User Story 2 - Consultar o catálogo de materiais (Priority: P2)

O operador do almoxarifado precisa localizar rapidamente um material, seja porque tem em mãos o
código oficial do SCPI, seja porque conhece apenas parte da descrição, para conferir unidade,
classificação, saldo e detalhamento técnico antes de qualquer operação.

**Why this priority**: é o uso diário do catálogo e o que torna a carga útil, mas depende de haver
materiais importados.

**Independent Test**: com o catálogo carregado, buscar um material pelo código exato e outro por um
trecho da descrição, verificando que ambos são localizados e que os dados exibidos correspondem ao
que foi importado.

**Acceptance Scenarios**:

1. **Given** o catálogo carregado, **When** o operador informa o código `000.000.002` na busca por
   código, **Then** o material correspondente é exibido com descrição, unidade, classificação,
   saldo e detalhamento.
2. **Given** o catálogo carregado, **When** o operador busca por um trecho da descrição, **Then**
   são listados todos os materiais cuja descrição contém aquele trecho, cada um com seu próprio
   código.
3. **Given** uma busca que não encontra nenhum material, **When** o resultado é apresentado,
   **Then** o sistema exibe explicitamente o estado de ausência de resultados, e não uma lista
   vazia sem explicação.
4. **Given** um catálogo com muitos materiais, **When** a busca retorna muitos resultados, **Then**
   os resultados são paginados em vez de carregados integralmente.

---

### User Story 3 - Auditar o resultado da importação (Priority: P3)

O responsável pela carga precisa saber exatamente o que entrou, o que foi atualizado e o que não
entrou no sistema, e por quê, para corrigir o arquivo na origem e reprocessar, e para poder
justificar divergências diante do SCPI depois.

**Why this priority**: indispensável para confiar na carga, mas o valor só aparece depois que a
importação existe; pode ser demonstrado separadamente.

**Independent Test**: executar uma importação com um arquivo contendo erros propositais e verificar
que o resultado apresenta os totais corretos e uma linha de exceção por registro recusado, com
motivo identificável.

**Acceptance Scenarios**:

1. **Given** um arquivo com registros válidos e inválidos, **When** a importação termina, **Then**
   o sistema apresenta os totais de registros recebidos, inseridos, atualizados e rejeitados, e a
   soma de inseridos, atualizados e rejeitados é igual aos recebidos.
2. **Given** um registro rejeitado por formato inválido de código, **When** o resultado é
   consultado, **Then** a exceção informa a linha do arquivo, o motivo da recusa e o código quando
   identificável.
3. **Given** uma importação concluída anteriormente, **When** o responsável consulta o histórico,
   **Then** o resultado daquela execução continua disponível, com quem executou e quando.

---

### User Story 4 - Reconciliar o catálogo com o SCPI (Priority: P4)

Depois que o WMS já está em operação, o responsável recebe um novo arquivo do SCPI, com materiais
novos, cadastros corrigidos e saldos que podem ter mudado no sistema oficial. Ele reprocessa o
arquivo para atualizar o cadastro e descobrir onde o saldo do WMS e o do SCPI deixaram de bater,
para depois corrigir por inventário dentro do próprio WMS.

**Why this priority**: só faz sentido quando já houve carga e movimentação; é manutenção contínua,
não pré-requisito de operação.

**Independent Test**: com o catálogo já carregado e ao menos um saldo alterado por movimentação,
reprocessar o mesmo arquivo e verificar que os cadastros são atualizados, que nenhum saldo é
sobrescrito e que a divergência aparece listada.

**Acceptance Scenarios**:

1. **Given** um material já existente cuja descrição mudou no arquivo, **When** a importação é
   reexecutada, **Then** a descrição do material é atualizada e o `CADPRO` permanece inalterado.
2. **Given** um material já existente cujo saldo no WMS é `10` e no arquivo é `10`, **When** a
   importação é reexecutada, **Then** nenhuma divergência é registrada para esse material.
3. **Given** um material já existente cujo saldo no WMS é `8` e no arquivo é `10`, **When** a
   importação é reexecutada, **Then** o saldo no WMS permanece `8` e é registrada uma divergência
   informando ambos os valores e a diferença.
4. **Given** um arquivo com um `CADPRO` ainda inexistente no WMS, **When** a importação é
   reexecutada, **Then** o material é inserido com o saldo do arquivo como saldo inicial.
5. **Given** um material existente no WMS que não consta no arquivo, **When** a importação é
   reexecutada, **Then** o material não é alterado nem excluído, e o sistema informa quantos
   materiais estão nessa situação.

---

### Edge Cases

- **Quebra física de linha dentro de um campo de texto**: uma linha física que não inicia um novo
  registro identificável precisa ser reconhecida como continuação do registro anterior, nunca como
  novo registro nem como valores deslocados entre colunas. Ocorre em `DISCR1` e também em `DISC1`.
- **Aspas duplas literais**: descrições usam `"` como símbolo de polegada, sem função de
  delimitação; interpretá-las como campo citado corrompe o alinhamento de colunas.
- **Ruído decimal vindo do SCPI**: quantidade como `53,4000000000001` representa um valor inteiro
  contaminado por aritmética de ponto flutuante na origem.
- **Continuação não associável**: se uma linha física não puder ser associada com segurança nem a
  um novo registro nem a uma continuação, o registro envolvido é recusado e reportado.
- **Continuação no fim do arquivo**: arquivo terminado no meio de um detalhamento multilinha.
- **Código fora do formato**: valores como `2`, `000.000.2`, `0.0.2` ou com espaços.
- **Código ausente**: linha sem `CADPRO`.
- **Quantidade não numérica ou negativa**: recusa com motivo específico.
- **Quantidade com separador de milhar**: convenção brasileira aplicada sem perda de casas
  decimais.
- **Descrição principal ausente**: recusa.
- **Unidade de medida ausente**: recusa.
- **Campos de classificação vazios**: aceitos, por serem apenas dados recebidos.
- **Arquivo sem alguma coluna obrigatória no cabeçalho**: o arquivo inteiro é recusado antes de
  importar qualquer registro.
- **Arquivo vazio ou apenas com cabeçalho**: informado como zero registros recebidos, sem erro.
- **Delimitador final na linha**: a coluna vazia gerada ao fim de cada linha não pode ser
  interpretada como campo com valor.
- **Marca BOM no início do arquivo**: não pode contaminar o nome da primeira coluna nem o primeiro
  código lido.
- **Reexecução com saldo divergente**: divergência apontada, saldo do WMS preservado.
- **Reexecução de material nunca movimentado**: também gera divergência se o arquivo trouxer saldo
  diferente, sem tratamento especial.
- **Reexecução do mesmo arquivo sem alterações**: nenhuma divergência e nenhum dado alterado.
- **Falha no meio do processamento**: o catálogo não pode ficar parcialmente gravado.

## Requirements *(mandatory)*

### Functional Requirements

#### Identificação do material

- **FR-001**: O sistema DEVE armazenar o `CADPRO` exatamente como recebido, em forma textual,
  preservando pontos e zeros à esquerda.
- **FR-002**: O sistema NÃO DEVE gerar, alterar, reformatar, completar, converter para número,
  decompor ou inferir qualquer parte do `CADPRO`, em nenhuma etapa — importação, armazenamento,
  atualização, consulta, exibição ou exportação.
- **FR-003**: O sistema DEVE tratar o `CADPRO` como identificador único do material e como única
  referência de correspondência com o SCPI.
- **FR-004**: O sistema DEVE recusar todo registro cujo `CADPRO` não esteja no formato
  `XXX.YYY.ZZZ`, com três grupos de três dígitos separados por ponto.
- **FR-005**: O sistema DEVE recusar registros com `CADPRO` repetido dentro do mesmo arquivo, sem
  importar nenhuma das ocorrências envolvidas, reportando todas elas.
- **FR-006**: O sistema NÃO DEVE oferecer nenhum meio de criar material manualmente; materiais
  entram no sistema exclusivamente pela importação.

#### Leitura do arquivo de carga

- **FR-007**: O sistema DEVE ler arquivo CSV em UTF-8 com BOM, com `;` como separador e com
  delimitador ao final da linha, sem que a marca BOM ou a coluna vazia final contaminem qualquer
  valor.
- **FR-007a**: O sistema DEVE tratar aspas duplas como caractere literal do conteúdo e NÃO DEVE
  interpretá-las como delimitação de campo. O arquivo usa `"` para indicar polegadas — como em
  `Adaptador PVC RS 3"` — sem nunca delimitar campos com aspas; interpretá-las como delimitador
  desalinha os campos a partir da primeira ocorrência.
- **FR-008**: O sistema DEVE identificar as colunas `CADPRO`, `DISC1`, `UNID1`, `QUAN3`, `DISCR1`,
  `GRUPO`, `SUBGRUPO`, `NOMEGRUPO` e `NOMESUBGRUPO` pelo cabeçalho do arquivo e DEVE recusar o
  arquivo inteiro, sem importar nada, se alguma dessas colunas estiver ausente.
- **FR-009**: O sistema DEVE recompor as linhas físicas em registro lógico antes de separar os
  campos, de modo que uma quebra de linha não delimitada permaneça dentro do campo a que pertence,
  qualquer que seja esse campo. Quebras ocorrem tanto em `DISCR1` quanto em `DISC1`, e a
  recomposição NÃO DEVE presumir que a continuação pertence ao detalhamento técnico.
- **FR-010**: Quando uma linha física não puder ser classificada com segurança como novo registro
  ou como continuação, o sistema DEVE recusar o registro envolvido e registrá-lo como exceção.
- **FR-011**: O sistema NUNCA DEVE importar um registro cujo valor tenha origem em coluna diferente
  da sua; deslocamento de colunas é motivo obrigatório de recusa, não de tentativa de correção.

#### Quantidade e saldo

- **FR-012**: O sistema DEVE interpretar `QUAN3` na convenção numérica brasileira, com vírgula
  decimal, e DEVE registrar o saldo com três casas decimais, arredondando o valor recebido para
  essa escala. O arredondamento serve exclusivamente para absorver ruído de ponto flutuante
  originado no SCPI — como `53,4000000000001` — e NÃO DEVE descartar precisão legítima, já que
  nenhum material do arquivo real usa mais de três casas de forma significativa.
- **FR-013**: O sistema DEVE aceitar quantidade zero como saldo válido.
- **FR-014**: O sistema DEVE recusar registro cuja quantidade esteja ausente ou vazia e NUNCA DEVE
  interpretar ausência de quantidade como zero.
- **FR-015**: O sistema DEVE recusar registro cuja quantidade não seja numérica ou seja negativa.
- **FR-016**: Para material inserido pela importação, o sistema DEVE registrar a quantidade do
  arquivo como saldo inicial, com origem identificável como carga do SCPI e distinguível de
  quantidades resultantes de movimentações do WMS.

#### Demais campos do material

- **FR-017**: O sistema DEVE preservar `DISC1` como recebida e NÃO DEVE tratá-la como chave de
  identificação; registros com descrição idêntica e `CADPRO` distinto são materiais distintos e não
  podem ser mesclados.
- **FR-018**: O sistema DEVE recusar registro cuja descrição principal esteja ausente ou vazia.
- **FR-019**: O sistema DEVE preservar `UNID1` exatamente como recebida e NÃO DEVE normalizar,
  unificar ou converter variações como `UN`, `UND`, `M`, `MT` e `MTS`.
- **FR-020**: O sistema DEVE recusar registro cuja unidade de medida esteja ausente ou vazia.
- **FR-021**: O sistema DEVE aceitar `DISCR1` vazio, e detalhamento ausente NÃO DEVE impedir a
  importação do registro.
- **FR-022**: O sistema DEVE armazenar `GRUPO`, `SUBGRUPO`, `NOMEGRUPO` e `NOMESUBGRUPO` exatamente
  como recebidos, aceitando valores vazios, sem validá-los e sem que influenciem a aceitação ou
  recusa do registro.
- **FR-023**: O sistema DEVE exibir os campos de classificação recebidos do SCPI na consulta do
  material, identificados como dado de origem externa.
- **FR-024**: O sistema NÃO DEVE classificar materiais, validar grupos ou subgrupos, nem derivar
  classificação a partir do `CADPRO`.

#### Reexecução e reconciliação

- **FR-025**: O sistema DEVE permitir executar a importação novamente com o catálogo já populado.
- **FR-026**: Para `CADPRO` já existente no catálogo, o sistema DEVE atualizar os dados cadastrais
  do material — descrição principal, unidade de medida, detalhamento técnico e campos de
  classificação — com os valores do arquivo.
- **FR-027**: Para `CADPRO` ainda inexistente, o sistema DEVE inserir o material com a quantidade
  do arquivo como saldo inicial.
- **FR-028**: O sistema NUNCA DEVE sobrescrever o saldo de um material já existente com a
  quantidade vinda do arquivo.
- **FR-029**: Quando a quantidade do arquivo diferir do saldo atual do material no WMS, o sistema
  DEVE registrar uma divergência de saldo contendo o `CADPRO`, o saldo no WMS, o saldo no arquivo,
  a diferença entre ambos e a execução em que foi detectada.
- **FR-030**: O sistema DEVE apresentar as divergências no resultado da execução e mantê-las
  consultáveis depois, associadas à execução que as detectou.
- **FR-031**: Material existente no catálogo e ausente do arquivo NÃO DEVE ser alterado nem
  excluído; o sistema DEVE informar quantos materiais estão nessa situação.
- **FR-032**: O sistema DEVE tornar rastreável toda alteração de dados cadastrais de material já
  existente, permitindo determinar o que mudou, quem executou e quando.

#### Resultado auditável da importação

- **FR-033**: O sistema DEVE registrar cada execução de importação identificando quem executou,
  quando ocorreu e qual arquivo foi processado.
- **FR-034**: O sistema DEVE apresentar, ao final de cada execução, os totais de registros
  recebidos, inseridos, atualizados e rejeitados, de modo que recebidos seja igual à soma de
  inseridos, atualizados e rejeitados.
- **FR-035**: O sistema DEVE informar, no resultado da execução, o total de divergências de saldo
  detectadas.
- **FR-036**: O sistema DEVE registrar, para cada registro recusado, a linha do arquivo, o motivo
  da recusa e o `CADPRO` quando este for identificável.
- **FR-037**: O sistema DEVE preservar o resultado de cada execução para consulta posterior, sem
  que o histórico seja sobrescrito por execuções seguintes.
- **FR-038**: O sistema DEVE efetivar o conjunto de inserções e atualizações aceitas de forma
  atômica, de modo que uma falha durante o processamento não deixe o catálogo parcialmente gravado.

#### Consulta do catálogo

- **FR-039**: O sistema DEVE permitir localizar um material informando o `CADPRO` exato e completo.
- **FR-040**: O sistema DEVE permitir localizar materiais por trecho da descrição principal, sem
  diferenciar maiúsculas de minúsculas nem acentuação.
- **FR-041**: O sistema DEVE exibir, no resultado da consulta, o código, a descrição principal, a
  unidade de medida, a classificação recebida, o saldo e o detalhamento técnico do material.
- **FR-042**: O sistema DEVE paginar os resultados da consulta, sem carregar o catálogo inteiro de
  uma vez.
- **FR-043**: O sistema DEVE apresentar explicitamente os estados de carregamento, ausência de
  resultados e erro na consulta.

#### Acesso e limites

- **FR-044**: O sistema DEVE permitir que o responsável autorizado envie o arquivo de carga pela
  interface da aplicação e DEVE apresentar o resultado da execução na própria interface, incluindo
  totais, exceções e divergências. A execução ocorre em duas etapas — prévia e confirmação —,
  detalhadas em FR-044a.
- **FR-044a**: O sistema DEVE apresentar, antes de persistir qualquer alteração no catálogo, uma
  prévia da importação com os totais esperados de inseridos, atualizados, rejeitados e
  divergências, sem efetivar nenhuma inserção, atualização ou registro de divergência nessa etapa.
  O sistema só DEVE persistir o resultado da importação — de forma atômica, conforme FR-038 — após
  confirmação explícita do responsável autorizado sobre essa prévia. *Emenda de 2026-09-18:
  acrescenta a etapa de prévia sem persistência a uma versão anterior deste requisito, que descrevia
  envio e persistência como um único passo; decisão do dono do produto registrada em
  `docs/domain-legacy/reconciliation/permissions-reconciliation.md`, §7.9.*
- **FR-045**: O sistema DEVE exigir autenticação para consultar o catálogo e autorização específica
  para executar a importação, ambas verificadas no servidor.
- **FR-046**: O sistema NÃO DEVE realizar integração automática de movimentações com o SCPI; o
  registro no sistema oficial permanece manual e externo a esta funcionalidade.
- **FR-047**: Esta funcionalidade NÃO DEVE corrigir saldo divergente; a correção ocorre por ajuste
  de inventário dentro do WMS, em funcionalidade própria.

### Key Entities

- **Material**: item do catálogo oficial, identificado unicamente pelo código `CADPRO` do SCPI.
  Possui descrição principal, unidade de medida, detalhamento técnico opcional e campos de
  classificação recebidos, todos preservados como vieram do SCPI. Não pode ser criado manualmente.
- **Saldo**: quantidade decimal associada a um material. Nasce da importação como saldo inicial e,
  a partir daí, só muda por operação do próprio WMS.
- **Execução de importação**: registro de uma carga realizada, com responsável, momento da
  execução, arquivo processado e totais de recebidos, inseridos, atualizados, rejeitados e
  divergências.
- **Exceção de importação**: registro de um recusado dentro de uma execução, com a linha do
  arquivo, o motivo da recusa e o código do material quando identificável.
- **Divergência de saldo**: diferença detectada entre a quantidade do arquivo e o saldo do material
  no WMS, com ambos os valores, a diferença e a execução que a detectou. É informativa e não altera
  saldo.

## Regras canônicas aplicáveis

### Permissões

Capabilities de `docs/domain/permissions-matrix.md` relevantes para esta feature:

- `PERM-MATERIAL-VIEW` — consulta do catálogo (FR-039 a FR-043).
- `PERM-SCPI-IMPORT-EXECUTE` — envio do arquivo, prévia e confirmação da importação (FR-044,
  FR-044a).
- `PERM-SCPI-IMPORT-HISTORY-VIEW` — consulta do histórico de execuções (FR-037).

### Invariantes

Invariantes de `docs/domain/invariants-matrix.md` que esta feature preserva:

- `INV-AUTH-001` — usuário inativo não acessa nem executa operações (FR-045).
- `INV-CATALOG-001` — opacidade do `CADPRO` (FR-001, FR-002).
- `INV-CATALOG-002` — unicidade do `CADPRO` no catálogo (FR-003, FR-005).
- `INV-CATALOG-003` — material só entra pela importação do SCPI (FR-006).
- `INV-CATALOG-004` — autoridade cadastral do SCPI sobre os dados do material (FR-017, FR-022,
  FR-026).
- `INV-CATALOG-005` — unidade de medida preservada como recebida (FR-019, FR-020).
- `INV-STOCK-001` — saldo físico nunca negativo (FR-015).
- `INV-STOCK-002` — saldo estabelecido pela importação que cria o material; reimportação nunca
  sobrescreve saldo existente (FR-016, FR-025 a FR-028).
- `INV-STOCK-003` — divergência de saldo é informativa (FR-029, FR-030).
- `INV-STOCK-004` — atomicidade da gravação da importação (FR-038).
- `INV-MOV-002` — saldo inicial identificável como carga do SCPI, distinguível de movimentações
  posteriores do WMS (FR-016).
- `INV-SCPI-001` — ausência de integração automática com o SCPI (FR-046).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% dos códigos importados são idênticos, caractere a caractere, aos códigos do
  arquivo de origem, verificável por conferência direta entre arquivo e catálogo.
- **SC-002**: Nenhum material importado apresenta valor proveniente de campo diferente do seu, em
  arquivo contendo descrições com quebras físicas de linha.
- **SC-003**: Toda linha não importada aparece no resultado da execução com um motivo, sem
  exceções silenciosas: rejeitados reportados é igual a recebidos menos inseridos e atualizados.
- **SC-004**: 100% das quantidades importadas conferem com o arquivo de origem na escala de três
  casas decimais, sem perda de precisão legítima.
- **SC-005**: Nenhum caminho da aplicação permite criar, alterar ou excluir um material fora do
  processo de importação.
- **SC-006**: O operador localiza um material pelo código oficial em uma única interação, sem
  precisar consultar listagens intermediárias.
- **SC-007**: A busca por descrição em um catálogo de porte operacional retorna resultados de forma
  percebida como imediata pelo operador, sem espera perceptível.
- **SC-008**: Após a carga inicial, o saldo por material no WMS confere com o saldo do arquivo
  exportado do SCPI em 100% dos materiais importados.
- **SC-009**: Nenhuma reexecução da importação altera o saldo de material já existente no WMS.
- **SC-010**: 100% das diferenças entre a quantidade do arquivo e o saldo do WMS aparecem na lista
  de divergências da execução, sem omissão.

## Fora de Escopo

- Criação, edição ou exclusão manual de materiais.
- Ajuste ou correção de saldo divergente, que ocorrerá por inventário dentro do WMS.
- Classificação de materiais e validação de grupos e subgrupos.
- Normalização ou unificação de unidades de medida.
- Movimentações de entrada e saída, inventário e requisições.
- Integração automática, em qualquer direção, com o SCPI.
- Gestão de locais de armazenamento e saldo por local.

## Assumptions

- O arquivo de carga é obtido manualmente a partir do SCPI e enviado ao WMS pelo responsável; não
  há acesso direto ao banco de dados ou a uma interface programática do SCPI.
- A importação aceita parcialmente o arquivo: os registros válidos são inseridos ou atualizados e
  os inválidos recusados, conforme implicado pela exigência de totais separados. O conjunto aceito
  é efetivado de uma só vez (FR-038).
- Uma linha física é considerada início de novo registro quando seu primeiro campo corresponde ao
  formato `XXX.YYY.ZZZ`; caso contrário é tratada como continuação do registro anterior. Este é o
  critério para "continuação identificável", e foi verificado contra o arquivo real: recompõe os
  1588 registros com exatamente 22 campos cada, sem uma única exceção.
- O `CADPRO` codifica grupo e subgrupo nos dois primeiros trios em 100% dos registros do arquivo
  real. Essa correspondência é observação, não regra: decompor o código para inferir classificação
  continua proibido (FR-002, FR-024), e os campos de classificação vêm sempre do arquivo.
- `LOCALFISICO` vem vazio nos 1588 registros do arquivo real; a gestão de locais de armazenamento
  do WMS não pode partir do SCPI e terá de ser construída em funcionalidade própria.
- Quantidade negativa é inválida, por não haver situação legítima de saldo negativo na carga.
- Descrição principal e unidade de medida ausentes foram tratadas como recusa, por serem dados
  essenciais à operação do almoxarifado; detalhamento técnico e campos de classificação são os
  únicos que podem vir vazios.
- A comparação de saldo na reexecução considera divergente qualquer diferença numérica, sem
  tolerância, já que a precisão decimal é preservada dos dois lados.
- A busca por descrição é por correspondência parcial, ignorando maiúsculas, minúsculas e
  acentuação, por ser o comportamento esperado em busca operacional.
- O catálogo tem porte de milhares a dezenas de milhares de materiais, compatível com um
  almoxarifado de órgão público estadual.
- A exclusão física de materiais, execuções, exceções e divergências não é prevista, em
  conformidade com o princípio de rastreabilidade da constituição do projeto.
