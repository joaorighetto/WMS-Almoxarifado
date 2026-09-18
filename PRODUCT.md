# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

O almoxarifado tem hoje uma equipe pequena: um chefe (dono do produto) e dois funcionários.

- **Funcionário do almoxarifado**: registra movimentações de estoque e completa o atendimento de
  requisições já aprovadas. Uma requisição aprovada pode ser atendida e concluída por qualquer
  funcionário do almoxarifado, sem atribuição individual a uma pessoa específica. Qualquer
  funcionário do almoxarifado — não só o chefe — também replica manualmente no SCPI os
  lançamentos feitos no WMS depois; por isso precisa de acesso ao histórico de requisições
  concluídas (e, de modo geral, ao histórico de movimentações), não só à fila do que ainda está
  pendente.
- **Chefe do almoxarifado**: acumula tudo que um funcionário do almoxarifado faz, mais atribuições
  exclusivas dele:
  - importa o catálogo de materiais do SCPI (feature `001-importacao-catalogo-materiais`, em
    especificação) e autoriza essa operação;
  - aprova as requisições criadas por funcionários do próprio almoxarifado (o almoxarifado também
    é, ele mesmo, um setor requisitante quando precisa de material);
  - opera estorno, devolução e saída excepcional de estoque (deterioração, vencimento,
    obsolescência, doação, empréstimo, entre outras) — operações que os demais funcionários do
    almoxarifado não podem executar.
- **Chefe de setor** (qualquer outro setor do SAEP): aprova as requisições criadas pelos
  requisitantes do seu próprio setor. Não tem acesso operacional ao estoque do almoxarifado nem às
  operações exclusivas do chefe do almoxarifado (estorno, devolução, saída excepcional).
- **Requisitante**: qualquer funcionário de qualquer setor do SAEP — incluindo os próprios
  funcionários do almoxarifado — que cria uma solicitação de material. A requisição segue para
  aprovação do chefe do setor a que o requisitante pertence.
- **Gestor/auditor**: acompanha relatórios, divergências e histórico com visão gerencial, sem
  operar estoque diretamente.
- **Administrador de sistema**: configura usuários, permissões e parâmetros do WMS.

O fluxo de requisição-aprovação-atendimento descrito acima (requisitante → chefe de setor →
qualquer funcionário do almoxarifado atende) e as operações exclusivas do chefe do almoxarifado
(estorno, devolução, saída excepcional) ainda não têm feature especificada no Spec Kit; são
capacidades confirmadas em produto, mas não implementadas.

## Product Purpose

Sistema de gestão de materiais, estoque e movimentações do almoxarifado do SAEP. Opera em
paralelo ao SCPI da Fiorilli (sistema contábil oficial do SAEP) para dar agilidade operacional ao
dia a dia — entradas, saídas, requisições e consulta —, enquanto os lançamentos equivalentes
continuam sendo registrados manualmente no SCPI pela equipe do almoxarifado. Sucesso é catálogo e saldo
confiáveis e rastreáveis no WMS, operação diária mais rápida do que pelo SCPI, e nenhuma
divergência entre os dois sistemas que passe despercebida.

## Positioning

O WMS-Almoxarifado não substitui o SCPI como sistema contábil oficial e não integra com ele
automaticamente em nenhuma direção. Ele existe porque o SCPI é lento e burocrático demais para o
uso operacional diário do almoxarifado. O mecanismo distintivo é operar como camada rápida e
auditável sobre o mesmo catálogo oficial — identificado pelo código `CADPRO` do SCPI, tratado
sempre como texto opaco, nunca gerado, alterado, reformatado ou decomposto pelo WMS — somada a um
fluxo próprio de requisição e autorização hierárquica por setor que o SCPI não oferece.

## Operating Context

- Atende um único almoxarifado físico do SAEP; não há necessidade confirmada de segmentar
  estoque por múltiplos locais.
- O catálogo de materiais é importado periodicamente do SCPI via arquivo CSV exportado
  manualmente pelo chefe do almoxarifado (feature `001-importacao-catalogo-materiais`, em
  especificação); não existe integração automática nem API com o SCPI.
- Fora do WMS, existe automação própria (`domain/Scripts/extrair-relatorio/`) que extrai relatórios
  do SCPI (catálogo, entradas, saídas, pedidos, compras) por scraping da interface web, porque o
  SCPI não oferece exportação nativa amigável — evidência do porte e formato reais dos dados que o
  WMS deverá tratar, mesmo quando essas outras extrações estiverem fora do escopo de uma feature
  específica.
- Lançamentos de movimentação feitos no WMS são posteriormente registrados manualmente no SCPI por
  qualquer funcionário do almoxarifado (não é exclusividade do chefe); a reconciliação de
  divergências de saldo é feita por ajuste de inventário dentro do próprio WMS, nunca
  sobrescrevendo automaticamente um saldo com o valor do SCPI.
- Fluxo de requisição: qualquer funcionário de qualquer setor do SAEP (inclusive do próprio
  almoxarifado) pode ser requisitante. A requisição é aprovada pelo chefe do setor a que o
  requisitante pertence — o chefe do almoxarifado aprova as requisições de sua própria equipe, da
  mesma forma que os demais chefes de setor aprovam as de suas equipes. Após aprovada, qualquer
  funcionário do almoxarifado pode atendê-la, registrá-la como concluída e, depois, lançá-la
  manualmente no SCPI — por isso o histórico de requisições concluídas precisa ficar acessível a
  toda a equipe do almoxarifado, não só ao chefe.

## Capabilities and Constraints

- `CADPRO` é o identificador único do material, no formato `XXX.YYY.ZZZ`, sempre armazenado e
  tratado como texto; o WMS nunca gera, altera, reformata, completa, converte para número,
  decompõe ou infere qualquer parte desse código.
- Materiais só entram no sistema pela importação do catálogo do SCPI; não há criação manual de
  materiais.
- Saldo de um material nasce da importação inicial e, a partir daí, só muda por operação própria
  do WMS; reimportar o catálogo nunca sobrescreve saldo existente, apenas aponta divergências.
- Escala esperada do catálogo: milhares a dezenas de milhares de materiais — evidência real
  observada: 1588 materiais em um arquivo de exportação analisado do SCPI.
- Stack, camadas de renderização e limites arquiteturais (Django, PostgreSQL, Django Templates,
  HTMX, CSS próprio, JavaScript pontual, sem SPA) são normativos e já fixados em
  `.specify/memory/constitution.md`; este documento não repete essa decisão.
- Regras de negócio, permissões e integridade de estoque devem ser garantidas no backend; nenhuma
  tela pode ser a única barreira de autorização (constitution, Princípios III, V, VI).
- Estorno, devolução e saída excepcional de estoque (deterioração, vencimento, obsolescência,
  doação, empréstimo, entre outras) são operações exclusivas do chefe do almoxarifado; nenhum
  outro papel — incluindo os demais funcionários do almoxarifado — pode executá-las.

## Evidence on Hand

- CSV real do catálogo de materiais do SCPI (1588 materiais), analisado em detalhe em
  `specs/001-importacao-catalogo-materiais/spec.md`, incluindo ruídos reais de formato (aspas
  literais, quebras de linha em campos, ruído decimal).
- CSVs reais de movimentações (saídas, entradas, pedidos, compras) extraídos do SCPI em
  `domain/Scripts/saidas/` e gerados pelos scripts de `domain/Scripts/extrair-relatorio/` —
  evidência de formato e volume reais de dados de movimentação, hoje fora do escopo de qualquer
  feature especificada.
- Nenhuma identidade visual, marca, depoimento ou material de marketing confirmado até o momento;
  trabalho visual futuro não deve presumir nenhum desses.

## Product Principles

1. O SCPI é sempre a fonte de verdade do cadastro oficial; o WMS reflete os dados recebidos dele,
   nunca os reformata nem os substitui.
2. Agilidade operacional do dia a dia do almoxarifado é a razão de existir do sistema; qualquer
   fricção que reproduza a lentidão do SCPI é uma falha de produto.
3. Toda divergência entre WMS e SCPI deve ficar visível e rastreável, nunca corrigida
   silenciosamente ou ocultada.
4. Autorização de operações críticas segue a hierarquia real do SAEP: cada chefe de setor aprova
   as requisições da própria equipe, e o chefe do almoxarifado concentra as atribuições exclusivas
   sobre o estoque (importação de catálogo, estorno, devolução, saída excepcional). Essa hierarquia
   deve ser garantida no servidor, nunca apenas ocultada na interface.
5. O sistema atende um único almoxarifado físico por ora; não presumir necessidade de
   segmentação multi-local antes que seja solicitada.
