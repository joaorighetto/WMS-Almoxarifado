# Contrato — Rotas, autorização e respostas

Superfícies HTTP da feature. Todas são server-rendered (Django Templates). Só a consulta do
catálogo usa HTMX, como aprimoramento. A autorização é sempre verificada no servidor, antes de
qualquer efeito e antes de validar ou interpretar o arquivo enviado (o `CsrfViewMiddleware`
do Django pode já ter recebido o upload para ler o token; isso não produz efeito de domínio). Fundamento: [research.md](../research.md) R8, R12, R15
e R16.

Convenções:
- **Anônimo** → `302` para `/login/?next=<caminho>` (comportamento nativo, contrato da 002).
- **Autenticado sem o papel** → `403` padrão do Django.
- **Inativo** → tratado como anônimo pelo Django (`INV-AUTH-001`, já coberto pela 002).
- Todo `POST` exige CSRF.

| Rota | Métodos | Nome | Capability → papel exigido |
|---|---|---|---|
| `/catalogo/` | GET | `catalogo:consulta` | `PERM-MATERIAL-VIEW` → `ROLE-REQUESTER` |
| `/catalogo/importacao/` | GET, POST | `catalogo:importacao_envio` | `PERM-SCPI-IMPORT-EXECUTE` → `ROLE-WAREHOUSE-HEAD` |
| `/catalogo/importacao/previa/` | GET | `catalogo:importacao_previa` | `PERM-SCPI-IMPORT-EXECUTE` → `ROLE-WAREHOUSE-HEAD` |
| `/catalogo/importacao/confirmar/` | POST | `catalogo:importacao_confirmar` | `PERM-SCPI-IMPORT-EXECUTE` → `ROLE-WAREHOUSE-HEAD` |
| `/catalogo/importacao/cancelar/` | POST | `catalogo:importacao_cancelar` | `PERM-SCPI-IMPORT-EXECUTE` → `ROLE-WAREHOUSE-HEAD` |
| `/catalogo/importacoes/` | GET | `catalogo:historico` | `PERM-SCPI-IMPORT-HISTORY-VIEW` → `ROLE-WAREHOUSE-HEAD` |
| `/catalogo/importacoes/<int:pk>/` | GET | `catalogo:execucao_detalhe` | `PERM-SCPI-IMPORT-HISTORY-VIEW` → `ROLE-WAREHOUSE-HEAD` |

O papel é checado por atribuição explícita (`User.tem_papel`), nunca por herança. Superusuário
técnico sem `ROLE-*` recebe `403` em todas as rotas.

## `GET /catalogo/` — consulta (US2)

Parâmetros de query: `codigo`, `descricao`, `pagina`.

| Situação | Resposta |
|---|---|
| sem filtros | 200; catálogo paginado (50/página) ordenado por `cadpro` |
| `codigo` no formato `XXX.YYY.ZZZ` (após aparar bordas) | 200; 0 ou 1 material, por igualdade exata |
| `codigo` fora do formato | 200; estado de validação "informe o código completo no formato XXX.YYY.ZZZ"; nenhuma consulta executada |
| `descricao` preenchida | 200; materiais cuja descrição contém **todas** as palavras do termo (separadas por espaço), em qualquer ordem, cada uma parcial, sem diferenciar maiúsculas nem acentos (FR-040) |
| `codigo` e `descricao` | 200; interseção dos dois filtros |
| nenhum resultado | 200; estado explícito de ausência de resultados (FR-043) |
| `pagina` inválida ou fora do intervalo | 200; página mais próxima válida (`Paginator.get_page`) |
| cabeçalho `HX-Request` | 200; **só o fragmento** da região de resultados, com a mesma lógica |

Colunas por material (FR-041, FR-023): código, descrição, unidade, classificação recebida do SCPI
(grupo, subgrupo e nomes, identificados como origem externa), saldo (3 casas, `tabular-nums`) e
detalhamento técnico (truncado com forma previsível de ver o valor completo). `CADPRO` exibido
como texto, em fonte monoespaçada, sem nenhuma transformação.

## `GET/POST /catalogo/importacao/` — envio (US1)

- `GET` → 200; formulário de envio. Se houver prévia pendente na sessão, mostra aviso com link
  para ela.
- `POST` (multipart, campo `arquivo`):
  - recusa de arquivo ([arquivo-scpi.md §1](./arquivo-scpi.md)) → 200; formulário com erro
    explícito; **nada** em sessão nem em banco;
  - aceito → grava o pedido de prévia na sessão (substituindo o anterior) → `302` para
    `catalogo:importacao_previa`. **Nenhuma** escrita em tabela de domínio.

## `GET /catalogo/importacao/previa/` — prévia (FR-044a)

- Sem pedido de prévia na sessão → `302` para `catalogo:importacao_envio` com aviso.
- Com pedido → 200. O plano é recalculado **só com leituras** e a página mostra:
  - identificação do arquivo (nome, tamanho);
  - totais esperados: recebidos, inseridos, atualizados (e quantos com alteração), rejeitados,
    divergências, ausentes do arquivo;
  - exceções (linha, `CADPRO` quando identificável, motivo), paginadas (`pagina_excecoes`);
  - divergências (`CADPRO`, saldo WMS, saldo arquivo, diferença), paginadas
    (`pagina_divergencias`);
  - aviso de que nada foi gravado ainda;
  - formulário de confirmação (`token`, `impressao_digital`) com botão primário que reitera o
    resultado ("Confirmar importação: N inseridos, M atualizados") e ação secundária de cancelar.

Os formulários de envio e de confirmação mostram estado de processamento ao serem submetidos, com
o botão desabilitado e o rótulo "Processando…", como aprimoramento em JS. Sem JS, o fluxo funciona
igual, e a idempotência da confirmação é garantida no servidor.

## `POST /catalogo/importacao/confirmar/` — efetivação (FR-038, FR-044a)

Campos: `token`, `impressao_digital`.

| Situação | Efeito | Resposta |
|---|---|---|
| já existe execução com esse `token` (verificado fora e, sob o advisory lock, dentro da transação) | nenhum | `302` → detalhe da execução existente, com aviso "esta prévia já foi confirmada" |
| `token` não corresponde e não há execução | nenhum | `302` → envio, com aviso "prévia não encontrada" |
| impressão digital recalculada ≠ enviada | nenhum (rollback) | `302` → prévia, com alerta "a prévia ficou desatualizada; revise antes de confirmar" |
| sucesso | execução + materiais + alterações + exceções + divergências, atômico; pedido removido da sessão | `302` → `catalogo:execucao_detalhe` (resultado na interface, FR-044) |
| falha inesperada | rollback total; pedido mantido; erro no log | 200 na página de prévia, com alerta de erro genérico sem detalhe interno |

## `POST /catalogo/importacao/cancelar/`

Remove o pedido de prévia da sessão → `302` para `catalogo:importacao_envio`. Nenhum efeito em
banco.

## `GET /catalogo/importacoes/` — histórico (FR-037, US3)

200; execuções paginadas (20/página), da mais recente para a mais antiga: momento, executada por
(matrícula), arquivo, recebidos, inseridos, atualizados, rejeitados, divergências. Sem execuções,
mostra estado vazio explícito.

## `GET /catalogo/importacoes/<pk>/` — resultado de uma execução

- `pk` inexistente → 404.
- 200: cabeçalho com quem, quando, arquivo (nome, tamanho, SHA-256); totais (FR-034, FR-035,
  FR-031); seções paginadas de exceções (FR-036, `pagina_excecoes`), divergências (FR-030,
  `pagina_divergencias`) e alterações cadastrais (FR-032: `CADPRO`, campo, valor anterior, valor
  novo; `pagina_alteracoes`). Cada seção tem estado vazio próprio.

## Home (`/`, da 002)

A view acrescenta ao contexto flags calculadas por `tem_papel`: `pode_consultar_catalogo`
(`ROLE-REQUESTER`) e `pode_importar_catalogo` (`ROLE-WAREHOUSE-HEAD`, cobrindo importação e
histórico). O template mostra os links correspondentes. A autorização efetiva continua nas rotas
acima.
