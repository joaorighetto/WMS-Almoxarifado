# catalogo — catálogo de materiais do SCPI (feature 001)
Arquivos:
- `leitura_scpi.py` — parsing puro do CSV SCPI: `decodificar`, `verificar_arquivo` (cabeçalho/`COLUNAS_OBRIGATORIAS`/`LIMITE_TAMANHO_ARQUIVO`), `ler_registros` → `ResultadoLeitura` (`RegistroAceito`/`Recusa`), recomposição de registros multilinha (`_RegistroBruto`), `interpretar_quantidade`, `normalizar_para_busca`. Sem ORM.
- `importacao.py` — serviço: `calcular_plano` → `PlanoImportacao` (inserções, `Atualizacao` com diff de campos, `Divergencia` de saldo, impressão digital), `aplicar_plano`, `confirmar_importacao`; prévia na sessão (`guardar_pedido/obter_pedido/descartar_pedido`, chave `CHAVE_SESSAO_PREVIA`, conteúdo zlib+base64).
- `models.py` — `Material`, `ExecucaoImportacao`, `ExcecaoImportacao` (+`MotivoRecusa`), `DivergenciaSaldo`, `AlteracaoCadastralMaterial` (+`CampoCadastral`), `CAMPOS_CADASTRAIS_ATUALIZAVEIS`.
- `views.py` — `ExigePapelMixin`; `ConsultaCatalogoView`, `ImportacaoEnvioView` → `ImportacaoPreviaView` → `ImportacaoConfirmarView`/`ImportacaoCancelarView`, `HistoricoImportacoesView`, `ExecucaoDetalheView`. URLs namespace `catalogo:`.
- `forms.py` (`ArquivoImportacaoForm`, `ConsultaCatalogoForm`), `templatetags/catalogo_extras.py` (`querystring_pagina`), JS `envio.js`/`historico.js`.

## Invariantes (não contornar)
- `Material` só é criado/alterado por `catalogo.importacao` (INV-CATALOG-003); não há CRUD manual nem Admin de Material. Só `CAMPOS_CADASTRAIS_ATUALIZAVEIS` mudam em reimportação (INV-CATALOG-004); `cadpro`, `saldo_inicial`, `execucao_origem` são `editable=False`.
- Reimportação NÃO altera saldo: diferença de quantidade vira `DivergenciaSaldo` (INV-STOCK-003).
- Constraints no banco: `cadpro` único e `^[0-9]{3}\.[0-9]{3}\.[0-9]{3}$` (nunca `\d`, que aceita dígito Unicode — research R3), `saldo`/`saldo_inicial` >= 0.
- Busca por `descricao_busca` (normalizada) com índice GIN trigram (migration `0001_pg_trgm` habilita extensão).
- Confirmação: dentro de `transaction.atomic` → `pg_advisory_xact_lock(CHAVE_LOCK_IMPORTACAO_SCPI)` → idempotência por `token_previa` (`PreviaJaConfirmada`) → recálculo com `bloquear=True` e comparação de impressão digital (`PreviaDesatualizada`) → `aplicar_plano`. Nada é gravado na prévia.
- Papéis por view via `papel_exigido` (PERM-MATERIAL-VIEW, PERM-SCPI-IMPORT-EXECUTE, PERM-SCPI-IMPORT-HISTORY-VIEW).
- Testes: `tests/test_catalogo_*.py` (atomicidade, reimportação, permissões, `sem_criacao_manual`, arquivo real) + CSVs em `tests/fixtures/catalogo/` (README descreve cada caso).
