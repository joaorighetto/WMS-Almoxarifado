# Reviews do laboratório — retomada de 2026-10-05

## Revisão funcional da L9

Papel independente: `code_reviewer`. Escopo: R1/R2 e efeitos funcionais de V1–V6 em
`base.css`, `components.css`, `catalogo.css` e `home.html`; L1–L8 não foram reabertas.

Nenhum finding relevante encontrado. O revisor declarou explicitamente que não realizou
auditoria estética. Verificou Home via HTTP como chefe do almoxarifado, requisitante e
administrador; três tiles e ausência de links/controles na seção planejada; fragmento HTMX do
catálogo com resposta 200, sem shell/scripts; progressive enhancement, foco, backgrounds de
rolagem e `git diff --check`.

Observações encaminhadas ao gate: a redução mobile de `.tile .v` para `1.25rem` é sobrescrita
pela regra posterior (`1.6rem`); o auto-fit de 150 px permite uma coluna em 320 px. Nenhuma perda
funcional confirmada. A matriz captura 390 px, não 320 px; a documentação registra a fonte
efetiva e não promete duas colunas em qualquer largura.

## Finish review — veredito pós-L9

Papel independente: `impeccable_finish_reviewer`, conforme definição empacotada na skill.
Code-led; referências são as capturas reais e `app.css` do upstream fixado. Não houve comp gerado
nem nova rodada de direção. Evidência: `captures.json`, capturas full-page e de viewport em
`.impeccable/review/`; primeiro veredito após recaptura completa, segundo após recaptura das sete
consultas afetadas por V3.

| Item | Primeiro veredito | Veredito final e evidência |
|---|---|---|
| V1 | resolvido | Descrição mais estreita em 390 px deixa Saldo visível; pista na borda direita nos dois temas; Unidade acessível por rolagem |
| V2 | resolvido | Uma célula associa título e selo, com descrição abaixo, evitando colunas estreitas e linhas excessivamente altas; composição aceita também no desktop |
| V3 | parcial | Resolvido na segunda rodada: conjunto curto “GERAL / GERAL · 000.000” em uma linha em 820 px; nomes longos quebram naturalmente; densidade mantida em 1280/1440 px |
| V4 | resolvido | Matrícula e Setor lado a lado em 390 px, Papéis na linha inteira, valores íntegros; fonte efetiva maior não prejudica essas capturas |
| V5 | resolvido | Tiles pelo topo em 1280/1440 px, sem esticar as caixas de Matrícula e Setor |
| V6 | resolvido | Nota junto ao título, com quebra natural no celular |

Primeira disposição: **fix**. Correção da segunda rodada: largura mínima de `16rem` na célula de
Classificação, exclusivamente em `catalogo.css`. Nenhuma regressão identificada nessa correção.
Composição aceita de “Em preparação” registrada no contrato §12.

Disposição final: **ship**. Cobre **somente os itens V1–V6 pontuados**, não o aceite visual do
laboratório pelo dono do produto nem as telas de propagação. Nenhum item desse lote permanece
parcial ou não resolvido. Não houve terceira rodada de correção.

## Evidência complementar

- `make verify` completo, incluindo lock, ruff, checks Django/deploy e pytest: log em
  `.impeccable/review/verify-final.log`.
- Chrome local via CDP: dez verificações em `.impeccable/review/interacoes.json` (tema nos dois
  sentidos, persistência, ordenação, paginação/foco, histórico, erro de servidor por código
  inválido, menu, Escape/foco e shell sem JS).
- Na verificação de código inválido via HTMX, o roteiro desliga temporariamente a validação
  nativa do formulário para alcançar a validação do servidor; nenhuma alteração fica no produto.
- Detector final: nove consultivos (quatro de raio, três de cor e dois de tamanho de fonte),
  nenhum finding determinístico. Análise estática aplicada aos CSS e templates. A sintaxe `{% static %}` não pode ser resolvida
  pelo detector; as folhas foram incluídas explicitamente e os valores renderizados conferidos
  no Chrome. O detector é evidência complementar, não substitui o gate visual.
- Capturas usam dados locais de desenvolvimento e o login simulado com permissões reais.
  Não foram feitos lançamentos, importações nem alterações de cadastro durante o smoke.
