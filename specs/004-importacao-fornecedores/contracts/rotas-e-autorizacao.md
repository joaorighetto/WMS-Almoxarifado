# Contrato — Rotas e autorização (fornecedores)

Prefixo `/fornecedores/`, `app_name = "fornecedores"`. Todas as views usam
`catalogo.views.ExigePapelMixin`: anônimo → login; autenticado sem o papel → 403; inativo →
tratado como anônimo (`INV-AUTH-001`). Sem exceção para superusuário técnico.

| Método e rota | Nome | Papel exigido | Capability | Efeito |
|---|---|---|---|---|
| GET `/fornecedores/` | `consulta` | `FUNCIONARIO_ALMOXARIFADO` | `PERM-SUPPLIER-VIEW` | consulta paginada; com `HX-Request`, devolve só o fragmento de resultados |
| GET `/fornecedores/importacao/` | `importacao_envio` | `CHEFE_ALMOXARIFADO` | `PERM-SUPPLIER-IMPORT-EXECUTE` | formulário; aviso de prévia pendente |
| POST `/fornecedores/importacao/` | `importacao_envio` | idem | idem | lê e projeta o arquivo (upload em memória, research R4); recusa de arquivo → re-render com erro, nada guardado; ok → projeção na sessão, 302 para a prévia |
| GET `/fornecedores/importacao/previa/` | `importacao_previa` | idem | idem | plano recalculado só com leituras; totais, recusas paginadas (`?pagina_excecoes=`), token e impressão digital |
| POST `/fornecedores/importacao/confirmar/` | `importacao_confirmar` | idem | idem | ver "Efetivação" |
| POST `/fornecedores/importacao/cancelar/` | `importacao_cancelar` | idem | idem | descarta a prévia da sessão; 302 para o envio |
| GET `/fornecedores/importacoes/` | `historico` | `CHEFE_ALMOXARIFADO` | `PERM-SUPPLIER-IMPORT-HISTORY-VIEW` | histórico paginado e ordenável |
| GET `/fornecedores/importacoes/<pk>/` | `execucao_detalhe` | idem | idem | totais, recusas e alterações paginadas |

Nenhuma rota cria, edita ou exclui fornecedor. Nenhum modelo de `fornecedores` é registrado no
admin.

## Efetivação (POST confirmar)

| Situação | Resposta |
|---|---|
| token já confirmado | aviso "Esta prévia já foi confirmada." → 302 para o detalhe da execução |
| sem prévia na sessão ou token diferente | aviso → 302 para o envio |
| `PreviaDesatualizada` | aviso "A prévia ficou desatualizada; revise antes de confirmar." → 302 para a prévia |
| erro inesperado | log com traceback; mensagem genérica; prévia re-renderizada; sessão mantida |
| sucesso | prévia descartada; mensagem com totais; 302 para o detalhe |

## Consulta — parâmetros GET

| Parâmetro | Validação | Filtro |
|---|---|---|
| `codigo` | aparado; fora de `[0-9]+` → erro "Informe só os dígitos do código." | `codif=` exato |
| `nome` | livre | cada palavra normalizada → `nome_busca__contains`, combinadas por E |
| `documento` | só os dígitos; menos de 3 → erro | `documento_digitos=` exato |
| `ordem` | `codigo`, `-codigo`, `nome`, `-nome`, `documento`, `-documento`; desconhecido → padrão | padrão `nome`, desempate `codif` |
| `pagina` | número de página | 50 por página |

Sem nenhum filtro, a consulta lista todos os fornecedores, paginados.
