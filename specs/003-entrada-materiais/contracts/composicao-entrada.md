# Contrato — Composição, resumo e confirmação da entrada

O estado da entrada em composição viaja no próprio formulário ([research R3](../research.md)).
Nada é guardado no servidor antes da confirmação (FR-008).

## Campos do formulário

| Campo | Controle | Validação no "Revisar" e na confirmação |
|---|---|---|
| `chave_confirmacao` | oculto | UUID válido; gerado no GET e preservado em todos os POSTs |
| `motivo` | seleção de `MotivoEntrada`, sem valor inicial | obrigatório; fora da lista → "Escolha um motivo da lista." |
| `tipo_documento` | seleção de `TipoDocumentoEntrada`, sem valor inicial; quando o motivo é `COMPRA` e o tipo ainda está vazio, passa a "Nota fiscal", que o usuário pode trocar (decisão do dono do produto no gate visual, 2026-09-27) | obrigatório; fora da lista → recusa |
| `numero_documento` | texto | obrigatório após `strip()`; só espaços = ausente |
| `emitente` | oculto (`pk` do fornecedor escolhido) + nome, código e documento exibidos | obrigatório em `COMPRA` e `DEVOLUCAO_FORNECEDOR_GARANTIA`; precisa existir e não estar bloqueado |
| `busca_emitente` | texto | só para a ação de busca; não é dado da entrada |
| `busca_material` | texto | só para a ação de busca; não é dado da entrada |
| itens (`formset` com prefixo `itens`) | por linha: `material` oculto (`pk`), código, descrição e unidade exibidos, `quantidade` texto (`inputmode="decimal"`) | ao menos um item; material existente; sem material repetido; quantidade por `interpretar_quantidade_recebida` |

O formset usa o management form padrão do Django (`TOTAL_FORMS`, `INITIAL_FORMS`), sem
`can_delete`: remover um item é reconstruir o formset sem a linha. O código, a descrição, a unidade
e o saldo exibidos vêm sempre do banco, a partir do `pk`, e nunca do POST.

## Ações (POST `/estoque/entradas/nova/`)

Identificadas pelo botão acionado. Nenhuma grava nada.

| Botão (`name` = `value`) | Efeito |
|---|---|
| `acao` = `buscar_material` | lista até 20 materiais para `busca_material` (research R9), cada um com "Adicionar"; já incluídos aparecem como "Já incluído"; sem resultado → estado vazio explicado |
| `adicionar_material` = `<pk>` | acrescenta uma linha com quantidade vazia e foco nela; limpa a busca de material |
| `remover_item` = `<índice>` | retira a linha |
| `acao` = `buscar_emitente` | lista até 20 fornecedores para `busca_emitente`; bloqueados com selo "Bloqueado" e motivo, sem ação |
| `escolher_emitente` = `<pk>` | fixa o emitente (recusado se bloqueado ou inexistente); limpa a busca |
| `acao` = `limpar_emitente` | remove o emitente escolhido |
| `acao` = `revisar` | valida tudo (tabela acima + referência já usada + saldo resultante acima do limite); inválido → formulário com erros por campo, dados preservados; válido → **resumo** |
| `acao` = `voltar` | do resumo, devolve o formulário preenchido |

Com `HX-Request` (e sem `HX-History-Restore-Request`), a resposta é o fragmento do formulário ou do
resumo; sem ele, a página inteira. Enter dentro de um campo de busca aciona a busca
correspondente, nunca "Revisar". As ações que só leem (buscar) podem ser acionadas por HTMX
enquanto se digita, com atraso, mas continuam funcionando sem JS.

## Resumo

Mostra motivo, tipo e número do documento, emitente (nome, código, documento) ou "Sem emitente" e,
por item: código SCPI (Mono, sem reformatar), descrição, unidade, quantidade, saldo atual e saldo
resultante (FR-008). Os saldos são lidos no momento do resumo e rotulados como tais: o registro usa
o saldo efetivo no momento da confirmação.

Barra de confirmação persistente com o único par de ações:

- primário: "Confirmar entrada: N itens", que envia para `/estoque/entradas/nova/confirmar/` todos
  os dados em campos ocultos + `chave_confirmacao`, com estado "Confirmando…";
- secundário: "Voltar e corrigir" (`acao=voltar`).

Desistir (fechar, navegar para outra página, voltar) não registra nada.

## Quantidade — exemplos normativos

| Digitado | Resultado |
|---|---|
| `5` | 5,000 |
| `0,750` | 0,750 |
| `1.250,5` | 1.250,500 |
| `1250,5` | 1.250,500 |
| ` 12 ` | 12,000 |
| `0` / `0,000` | recusa: maior que zero |
| `-3` | recusa: formato |
| `2,5001` | recusa: no máximo três casas decimais |
| `0.750` | recusa: formato (grupo de milhar não começa com zero) |
| `2.500` | 2.500,000 (ponto é milhar) |
| `1.25` | recusa: formato |
| `,5` | recusa: formato (parte inteira obrigatória) |
| `abc`, `1,2,3`, vazio | recusa |
| `1000000000000` (13 dígitos) | recusa: fora do limite |

O "Revisar" também recusa o item cujo saldo resultante ultrapassaria 999.999.999.999,999.

## Mensagens por campo

| Condição | Mensagem |
|---|---|
| motivo ausente | "Escolha o motivo da entrada." |
| tipo ausente | "Escolha o tipo de documento." |
| número ausente | "Informe o número do documento." |
| emitente ausente em compra ou devolução de fornecedor/garantia | "Informe o emitente do documento." |
| emitente bloqueado | "O fornecedor escolhido está bloqueado no SCPI; escolha outro emitente." |
| referência já usada | "Este documento já foi lançado na entrada de <momento> por <autor>." + link |
| nenhum item | "Inclua ao menos um material." |
| material repetido | "Este material já está na entrada." (na linha repetida) |
| quantidade | mensagens de [research R8](../research.md) |
