# Feature Specification: Importação do Cadastro de Fornecedores do SCPI

**Feature Branch**: `004-importacao-fornecedores`

**Feature Directory**: `specs/004-importacao-fornecedores`

**Created**: 2026-09-25

**Status**: Draft

**Input**: User description: "Feature FOR do ROADMAP.md — Importação do cadastro de fornecedores do
SCPI. Objetivo: do CSV exportado do SCPI à consulta de fornecedores e à conferência auditável da
carga, para que sirvam de emitente nas entradas de materiais (spec 003, FR-007/FR-007a). Inclui:
carga por CSV com prévia sem persistência e confirmação explícita; consulta; reimportação;
resultado auditável (totais, exceções, histórico de execuções). Não inclui: cadastro ou edição
manual de fornecedores; compras/licitações/contratos; dados financeiros ou fiscais além da
identificação; integração automática com o SCPI. Regras canônicas: PERM-SUPPLIER-IMPORT-EXECUTE e
PERM-SUPPLIER-IMPORT-HISTORY-VIEW (ROLE-WAREHOUSE-HEAD), PERM-SUPPLIER-VIEW (ROLE-WAREHOUSE-STAFF);
INV-SUPPLIER-001 a 005, INV-SCPI-001, INV-AUTH-001, INV-STOCK-004 aplicada à gravação atômica.
Seguir o modelo da spec 001. Arquivo real analisado: UTF-8 com BOM, ';', CRLF como terminador de
registro, 132 colunas com delimitador final, 10.035 registros; dados mínimos guardados: CODIF,
NOME, NOM_FANT, INSMF, CODTIP, situação e motivo de bloqueio; fornecedor ausente do arquivo
permanece inalterado."

## Clarifications

### Sessão 2026-09-25 — decisões anteriores à spec

Tomadas com o dono do produto durante o `clarify` da spec 003 e registradas nas matrizes canônicas
e no `ROADMAP.md` antes desta spec:

- Fornecedor só entra no WMS pela importação do SCPI e só muda por reimportação; não há cadastro
  nem edição manual (`INV-SUPPLIER-003`).
- O chefe do almoxarifado importa e consulta o histórico de importações; os funcionários do
  almoxarifado consultam fornecedores (`PERM-SUPPLIER-IMPORT-EXECUTE`,
  `PERM-SUPPLIER-IMPORT-HISTORY-VIEW`, `PERM-SUPPLIER-VIEW`).
- O WMS guarda só os dados de identificação; dados bancários, PIS, endereço, contato e demais
  colunas do arquivo são descartados (`INV-SUPPLIER-004`).
- Fornecedor bloqueado no SCPI é importado, com a situação visível, mas não pode ser emitente de
  nova entrada (`INV-SUPPLIER-005`, aplicada na spec 003).

### Sessão 2026-09-25 — análise do arquivo real

Arquivo real exportado do SCPI (`docs/CSVs/fornecedores.csv`, só local, ignorado pelo Git por
conter dados pessoais):

- UTF-8 com BOM, separador `;`, delimitador ao final de cada linha, 132 colunas, 10.035 registros.
  Cada registro termina em CRLF; um campo de contato contém uma quebra de linha LF isolada, que
  pertence ao campo e não encerra o registro. Não há aspas nem caractere nulo no arquivo.
- `CODIF`: numérico, de 1 a 19614, único e sempre preenchido — o identificador do fornecedor.
- `NOME`: sempre preenchido, até 50 caracteres; 1.690 nomes se repetem entre códigos distintos.
- `NOM_FANT`: preenchido em 4.418 registros.
- `INSMF` (CNPJ/CPF): 5.217 CNPJ formatados, 1.507 CPF formatados, 3.310 vazios e 1 malformado;
  37 documentos aparecem em mais de um código.
- `CODTIP`: `01` (com CNPJ) 5.219; `02` (com CPF) 1.602; `03` (sem documento) 3.210; `09` (sem
  documento) 4.
- `BLOQ_OPCAO`: `S` em 10.017 e `B` (bloqueado) em 18. O motivo aparece em `MSG_BLOQ` (por exemplo
  "FORNECEDOR NÃO PODE SER UTILIZADO") e em `TIPO_BLOQ` (por exemplo "MUDANÇA DE CNPJ"). As datas
  de início e fim de bloqueio são sentinelas (1899/1901 a 2099/2200) ou vazias, e não indicam
  prazo real.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Carregar o cadastro de fornecedores (Priority: P1)

O chefe do almoxarifado exporta o cadastro de fornecedores do SCPI em CSV e o envia ao WMS. O WMS
mostra uma prévia — quantos fornecedores serão inseridos, atualizados e recusados, com o motivo de
cada recusa — sem gravar nada. O chefe confere e confirma; só então o cadastro é gravado, de uma vez.

**Why this priority**: sem fornecedores importados, a entrada de materiais por compra ou por
devolução de fornecedor/garantia não pode ser registrada (spec 003, FR-007).

**Independent Test**: com o banco sem fornecedores, enviar o arquivo real, conferir a prévia,
confirmar e verificar que os 10.035 fornecedores estão disponíveis, cada um com código, nome, nome
fantasia, CNPJ/CPF, tipo e situação de bloqueio iguais aos do arquivo, e nenhum outro dado.

**Acceptance Scenarios**:

1. **Given** nenhum fornecedor no WMS, **When** o chefe do almoxarifado envia o arquivo, **Then** vê
   a prévia com os totais de recebidos, a inserir, a atualizar e recusados, e nenhum fornecedor é
   gravado.
2. **Given** a prévia exibida, **When** o chefe confirma, **Then** os fornecedores aceitos são
   gravados de uma vez e o resultado da execução fica registrado.
3. **Given** a prévia exibida, **When** o chefe desiste, **Then** nada é gravado.
4. **Given** um arquivo sem uma das colunas obrigatórias, **When** o chefe o envia, **Then** o
   arquivo inteiro é recusado, informando a coluna ausente.
5. **Given** um registro com `CODIF` vazio, não numérico ou repetido no arquivo, ou com nome vazio,
   **When** a importação é processada, **Then** o registro é recusado com linha e motivo, e os
   demais são importados.
6. **Given** um fornecedor com `BLOQ_OPCAO` igual a `B`, **When** é importado, **Then** fica
   registrado como bloqueado, com o motivo recebido.
7. **Given** um usuário sem o papel de chefe do almoxarifado, **When** tenta acessar ou executar a
   importação, inclusive por envio direto, **Then** a operação é negada.

---

### User Story 2 - Consultar fornecedores (Priority: P2)

Um funcionário do almoxarifado precisa conferir um fornecedor — por exemplo, o emitente de uma nota
fiscal. Ele busca pelo código SCPI, pelo nome ou nome fantasia, ou pelo CNPJ/CPF, e vê os dados de
identificação e se o fornecedor está bloqueado no SCPI.

**Why this priority**: é a mesma localização que a entrada de materiais usará para escolher o
emitente, e permite conferir o resultado da carga.

**Independent Test**: com fornecedores importados, localizar um fornecedor por cada critério de
busca e verificar os dados exibidos contra o arquivo.

**Acceptance Scenarios**:

1. **Given** fornecedores importados, **When** o funcionário busca por código exato, **Then** vê
   aquele fornecedor.
2. **Given** fornecedores importados, **When** busca por palavras do nome ou do nome fantasia,
   **Then** vê os fornecedores cujo nome ou nome fantasia contém todas as palavras, em qualquer
   ordem, sem diferenciar maiúsculas nem acentuação.
3. **Given** um fornecedor com CNPJ `62.011.929/0001-73`, **When** o funcionário busca por
   `62011929000173` ou pelo valor formatado, **Then** encontra o fornecedor.
4. **Given** um fornecedor bloqueado, **When** aparece na consulta, **Then** a situação de bloqueio
   e o motivo ficam visíveis.
5. **Given** um usuário sem `ROLE-WAREHOUSE-STAFF`, **When** tenta consultar fornecedores, **Then**
   o acesso é negado.
6. **Given** qualquer usuário, **When** consulta um fornecedor, **Then** não existe caminho para
   criar, editar ou excluir fornecedor.

---

### User Story 3 - Auditar as importações (Priority: P3)

O chefe do almoxarifado consulta o histórico de execuções da importação de fornecedores — quem
executou, quando, qual arquivo, os totais — e abre uma execução para ver as recusas e o que mudou.

**Why this priority**: torna a carga verificável e mostra ao responsável o que corrigir na origem.

**Independent Test**: executar duas importações e verificar que ambas aparecem no histórico com
seus totais e recusas, sem que a segunda sobrescreva a primeira.

**Acceptance Scenarios**:

1. **Given** importações executadas, **When** o chefe abre o histórico, **Then** vê cada execução,
   da mais recente para a mais antiga, com responsável, momento, arquivo e totais.
2. **Given** uma execução com recusas, **When** o chefe a abre, **Then** vê cada recusa com linha,
   motivo e código quando identificável.
3. **Given** um usuário sem `ROLE-WAREHOUSE-HEAD`, **When** tenta abrir o histórico, **Then** o
   acesso é negado.

---

### User Story 4 - Reimportar o cadastro (Priority: P4)

O cadastro de fornecedores muda no SCPI: novos fornecedores, nomes corrigidos, bloqueios. O chefe
exporta um arquivo novo e o importa de novo. Fornecedores novos são inseridos, os existentes têm os
dados de identificação atualizados, e os ausentes do arquivo permanecem como estavam.

**Why this priority**: mantém o cadastro alinhado ao SCPI, inclusive os bloqueios que impedem uma
entrada; depende da carga inicial.

**Independent Test**: importar um arquivo, alterar nome e bloqueio de um fornecedor e remover outro
num segundo arquivo, reimportar e verificar inserções, atualizações, ausentes inalterados e o
registro das alterações.

**Acceptance Scenarios**:

1. **Given** um fornecedor existente cujo nome mudou no arquivo, **When** a reimportação é
   confirmada, **Then** o nome é atualizado e a alteração fica registrada com valor anterior, novo,
   execução, responsável e momento.
2. **Given** um fornecedor desbloqueado que vem bloqueado no novo arquivo, **When** a reimportação
   é confirmada, **Then** ele passa a bloqueado e deixa de poder ser emitente de nova entrada.
3. **Given** um fornecedor bloqueado que vem desbloqueado, **When** a reimportação é confirmada,
   **Then** ele volta a poder ser emitente.
4. **Given** um fornecedor existente ausente do novo arquivo, **When** a reimportação é confirmada,
   **Then** ele permanece inalterado e o resultado informa quantos fornecedores estão nessa
   situação.
5. **Given** um fornecedor já usado como emitente de entradas, **When** seus dados mudam na
   reimportação, **Then** as entradas continuam vinculadas a ele.

---

### Edge Cases

- **Quebra de linha isolada dentro de um campo**: permanece no campo; só CRLF encerra o registro.
- **Registro com número de campos diferente do cabeçalho**: recusado como deslocamento de colunas,
  sem tentativa de correção.
- **Aspas duplas**: tratadas como caractere literal, como na importação do catálogo.
- **Caractere nulo no conteúdo**: arquivo inteiro recusado, indicando as linhas.
- **Arquivo sem BOM**: aceito, como na importação do catálogo.
- **Arquivo em outra codificação**: recusado com mensagem clara, sem gravar nada.
- **Arquivo vazio ou só com cabeçalho válido**: zero recebidos, sem erro, como na importação do
  catálogo.
- **`CODIF` com zeros à esquerda**: preservado como recebido (`INV-SUPPLIER-001`).
- **`CODIF` repetido no arquivo**: todas as ocorrências recusadas e reportadas.
- **CNPJ/CPF vazio, malformado ou repetido em outro código**: aceito e preservado como recebido; o
  documento não identifica o fornecedor (`INV-SUPPLIER-002`).
- **Nome igual ao de outro fornecedor**: aceito; são fornecedores distintos.
- **`BLOQ_OPCAO` vazio ou diferente de `S` e `B`**: registro recusado, porque a situação de bloqueio
  decide se o fornecedor pode ser emitente.
- **Colunas descartadas com conteúdo** (conta bancária, PIS, endereço): lidas apenas para manter o
  alinhamento dos campos; nada delas é gravado, nem nas exceções ou na trilha de alterações.
- **Duas importações confirmadas ao mesmo tempo**: não podem deixar o cadastro misturado; uma
  conclui antes da outra ou a segunda é recusada.
- **Arquivo alterado entre a prévia e a confirmação**: a confirmação grava exatamente o que a prévia
  mostrou, ou é recusada se o estado do cadastro mudou desde a prévia.

## Requirements *(mandatory)*

### Functional Requirements

#### Identificação do fornecedor

- **FR-001**: O sistema DEVE armazenar o `CODIF` exatamente como recebido, em forma textual,
  preservando eventuais zeros à esquerda, e NÃO DEVE gerá-lo, alterá-lo, reformatá-lo ou
  completá-lo em nenhuma etapa (`INV-SUPPLIER-001`).
- **FR-002**: O `CODIF` DEVE ser o identificador único do fornecedor e a única referência de
  correspondência com o SCPI. Nome e CNPJ/CPF NÃO DEVEM ser usados para identificar ou mesclar
  fornecedores (`INV-SUPPLIER-002`).
- **FR-003**: O sistema DEVE recusar registro com `CODIF` vazio ou com caractere que não seja dígito.
- **FR-004**: O sistema DEVE recusar todas as ocorrências de um `CODIF` repetido no mesmo arquivo,
  reportando cada uma.
- **FR-005**: O sistema NÃO DEVE oferecer meio de criar, editar ou excluir fornecedor fora da
  importação (`INV-SUPPLIER-003`).

#### Leitura do arquivo

- **FR-006**: O sistema DEVE ler CSV em UTF-8, com BOM opcional, separador `;` e delimitador ao
  final da linha, sem que o BOM ou a coluna vazia final contaminem valores, e DEVE recusar o
  arquivo inteiro se ele não for UTF-8 válido.
- **FR-007**: Cada registro DEVE terminar em CRLF; uma quebra de linha LF isolada DEVE permanecer
  dentro do campo em que aparece.
- **FR-008**: Aspas duplas DEVEM ser tratadas como caractere literal, nunca como delimitador.
- **FR-009**: O sistema DEVE recusar o arquivo inteiro, sem gravar nada, se o conteúdo contiver
  caractere nulo, indicando as linhas.
- **FR-010**: O sistema DEVE identificar as colunas `CODIF`, `NOME`, `NOM_FANT`, `INSMF`, `CODTIP`,
  `BLOQ_OPCAO`, `MSG_BLOQ` e `TIPO_BLOQ` pelo cabeçalho e DEVE recusar o arquivo inteiro se alguma
  estiver ausente. As demais colunas não são obrigatórias.
- **FR-011**: Registro cujo número de campos difira do cabeçalho DEVE ser recusado como
  deslocamento de colunas; o sistema NUNCA DEVE importar valor vindo de coluna diferente da sua.

#### Dados do fornecedor

- **FR-012**: O sistema DEVE guardar do fornecedor somente: código (`CODIF`), nome (`NOME`), nome
  fantasia (`NOM_FANT`), CNPJ/CPF (`INSMF`), tipo (`CODTIP`), situação de bloqueio (`BLOQ_OPCAO`) e
  motivo do bloqueio (`MSG_BLOQ` e `TIPO_BLOQ`). Nenhuma outra coluna do arquivo DEVE ser armazenada
  em nenhum registro do WMS, inclusive exceções, prévias e trilha de alterações
  (`INV-SUPPLIER-004`).
- **FR-013**: O sistema DEVE recusar registro com nome vazio. Nome fantasia, CNPJ/CPF, tipo e motivo
  de bloqueio podem vir vazios.
- **FR-014**: Nome, nome fantasia, CNPJ/CPF, tipo e motivo de bloqueio DEVEM ser preservados como
  recebidos, sem validação de dígitos, normalização ou formatação. O WMS não infere o tipo a partir
  do documento nem o documento a partir do tipo.
- **FR-015**: O fornecedor DEVE ser registrado como bloqueado quando `BLOQ_OPCAO` for `B` e como não
  bloqueado quando for `S`; qualquer outro valor, inclusive vazio, DEVE causar a recusa do
  registro. As datas de bloqueio do arquivo não são consideradas.

#### Prévia, confirmação e reimportação

- **FR-016**: A importação DEVE ocorrer em duas etapas: prévia, que apresenta os totais de
  recebidos, a inserir, a atualizar, recusados e existentes ausentes do arquivo, com as recusas,
  sem gravar nada; e confirmação explícita, única etapa que grava.
- **FR-017**: A gravação confirmada DEVE ser atômica: todo o conjunto aceito é gravado, ou nada é
  (`INV-STOCK-004`, aplicada por analogia à carga do cadastro).
- **FR-018**: A confirmação DEVE gravar exatamente o resultado mostrado na prévia. Se o cadastro
  tiver mudado desde a prévia — por outra importação confirmada —, a confirmação DEVE ser recusada
  e uma nova prévia exigida.
- **FR-019**: Para `CODIF` inexistente, o sistema DEVE inserir o fornecedor.
- **FR-020**: Para `CODIF` existente, o sistema DEVE atualizar nome, nome fantasia, CNPJ/CPF, tipo,
  situação e motivo de bloqueio com os valores do arquivo.
- **FR-021**: Toda alteração de dado de fornecedor existente DEVE ser rastreável, com campo, valor
  anterior, valor novo, execução, responsável e momento.
- **FR-022**: Fornecedor existente ausente do arquivo NÃO DEVE ser alterado nem excluído; o
  resultado DEVE informar quantos estão nessa situação.
- **FR-023**: A reimportação NÃO DEVE desfazer nem alterar o vínculo de entradas já registradas com
  seus emitentes.

#### Resultado auditável

- **FR-024**: Cada execução confirmada DEVE registrar responsável, momento, nome do arquivo e totais
  de recebidos, inseridos, atualizados e recusados, com recebidos igual à soma dos outros três, e o
  total de existentes ausentes do arquivo.
- **FR-025**: Cada recusa DEVE registrar a linha do arquivo, o motivo e o `CODIF` quando
  identificável, sem nenhum dado além dos permitidos em FR-012.
- **FR-026**: O histórico de execuções DEVE ser preservado, da mais recente para a mais antiga, sem
  que uma execução sobrescreva outra, e DEVE ser paginado.

#### Consulta

- **FR-027**: O sistema DEVE permitir localizar fornecedor por `CODIF` exato; por palavras do nome
  ou do nome fantasia, cada uma inteira ou parcial, todas presentes em qualquer ordem, sem diferenciar
  maiúsculas nem acentuação; e por CNPJ/CPF, comparando só os dígitos do valor buscado e do valor
  armazenado.
- **FR-028**: O resultado DEVE exibir código, nome, nome fantasia, CNPJ/CPF, tipo e situação de
  bloqueio com o motivo, identificados como dados de origem do SCPI, e DEVE ser paginado, com ordem
  padrão por nome e desempate pelo código.
- **FR-029**: A consulta DEVE apresentar explicitamente os estados de ausência de resultados e de
  erro.

#### Acesso e limites

- **FR-030**: Executar a importação exige `ROLE-WAREHOUSE-HEAD` (`PERM-SUPPLIER-IMPORT-EXECUTE`);
  consultar o histórico de execuções exige `ROLE-WAREHOUSE-HEAD`
  (`PERM-SUPPLIER-IMPORT-HISTORY-VIEW`); consultar fornecedores exige `ROLE-WAREHOUSE-STAFF`
  (`PERM-SUPPLIER-VIEW`). Toda verificação ocorre no servidor; ocultar elementos não é autorização.
- **FR-031**: Usuário inativo não importa nem consulta (`INV-AUTH-001`).
- **FR-032**: O sistema NÃO DEVE realizar integração automática com o SCPI em nenhuma direção
  (`INV-SCPI-001`).

### Key Entities

- **Fornecedor**: pessoa ou entidade do cadastro do SCPI, identificada unicamente pelo `CODIF`. Tem
  nome, nome fantasia opcional, CNPJ/CPF opcional, tipo conforme o SCPI e situação de bloqueio com
  motivo. Só entra e muda pela importação; é o emitente das entradas de materiais (spec 003).
- **Execução de importação de fornecedores**: uma carga confirmada, com responsável, momento,
  arquivo e totais.
- **Recusa de importação de fornecedores**: registro recusado numa execução, com linha, motivo e
  código quando identificável.
- **Alteração de fornecedor**: mudança de um dado de fornecedor existente numa reimportação, com
  campo, valor anterior, valor novo e a execução que a produziu.

## Regras canônicas aplicáveis

### Permissões

- `PERM-SUPPLIER-IMPORT-EXECUTE` — envio, prévia e confirmação (FR-016, FR-030).
- `PERM-SUPPLIER-IMPORT-HISTORY-VIEW` — histórico de execuções e recusas (FR-024 a FR-026, FR-030).
- `PERM-SUPPLIER-VIEW` — consulta de fornecedores (FR-027 a FR-030).

### Invariantes

- `INV-AUTH-001` — usuário inativo não opera (FR-031).
- `INV-SUPPLIER-001` — `CODIF` opaco (FR-001).
- `INV-SUPPLIER-002` — unicidade do `CODIF`; nome e documento não identificam (FR-002, FR-004).
- `INV-SUPPLIER-003` — fornecedor só pela importação (FR-005, FR-020).
- `INV-SUPPLIER-004` — somente dados de identificação (FR-012, FR-025).
- `INV-SUPPLIER-005` — a situação de bloqueio importada é a que a spec 003 usa para recusar emitente
  (FR-015, FR-020).
- `INV-STOCK-004` — atomicidade da gravação, aplicada por analogia à carga do cadastro (FR-017).
- `INV-SCPI-001` — sem integração automática (FR-032).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Com o arquivo real, 100% dos 10.035 registros são importados, e código, nome, nome
  fantasia, CNPJ/CPF, tipo e situação de bloqueio de cada um conferem, caractere a caractere, com
  o arquivo.
- **SC-002**: Os 18 fornecedores bloqueados no arquivo real aparecem como bloqueados, e nenhum
  outro.
- **SC-003**: Nenhum dado de conta bancária, PIS, endereço ou contato do arquivo é encontrado em
  qualquer registro do WMS após a importação.
- **SC-004**: Toda linha não importada aparece no resultado com um motivo: recebidos é igual a
  inseridos mais atualizados mais recusados.
- **SC-005**: Uma falha durante a gravação não deixa nenhum fornecedor do arquivo gravado.
- **SC-006**: A prévia e a confirmação de um arquivo do porte real terminam, cada uma, em menos de
  30 segundos.
- **SC-007**: O funcionário localiza um fornecedor pelo CNPJ/CPF, formatado ou só com dígitos, em
  uma única busca.
- **SC-008**: Nenhum caminho da aplicação permite criar, editar ou excluir fornecedor fora da
  importação.

## Fora de Escopo

- Cadastro, edição ou exclusão manual de fornecedores.
- Compras, licitações, contratos, empenhos e pagamentos.
- Dados bancários, fiscais, de endereço ou de contato do fornecedor.
- Validação de dígitos verificadores de CNPJ/CPF.
- Registro de entradas e escolha do emitente, que pertencem à spec 003.
- Inativação ou exclusão de fornecedor ausente do arquivo.
- Integração automática com o SCPI.

## Assumptions

- O arquivo é exportado manualmente do SCPI pelo chefe do almoxarifado, como o do catálogo, e segue
  o formato do arquivo real analisado.
- A experiência de envio, prévia, confirmação e histórico segue a da importação do catálogo (001),
  com as diferenças desta spec.
- `CODTIP` é mostrado como recebido; a correspondência observada (`01` com CNPJ, `02` com CPF) não é
  usada como regra.
- Fornecedor removido do SCPI e ausente do novo arquivo continua podendo ser emitente, desde que não
  bloqueado; a remoção no SCPI não tem efeito no WMS nesta versão.
- O tamanho máximo aceito do arquivo comporta com folga o arquivo real (cerca de 4,6 MB).
