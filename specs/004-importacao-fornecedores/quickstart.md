# Quickstart — validação de ponta a ponta

Roteiro para comprovar a feature 004 depois de implementada. Contratos:
[arquivo-fornecedores.md](./contracts/arquivo-fornecedores.md),
[rotas-e-autorizacao.md](./contracts/rotas-e-autorizacao.md). Modelo: [data-model.md](./data-model.md).

## Pré-requisitos

- Ambiente da 001/002 funcionando; schema recriado com `make resetdb` depois de incluir o app
  `fornecedores` (sem migrations).
- Usuários de validação da 001 (`quickstart.md` §1 da 001): `chefe`, `funcionario` e
  `requisitante`. `make setup` os cria por `seed_dev`.
- Para o aceite com dado real: `docs/CSVs/fornecedores.csv`, só local e ignorado pelo Git.

## 1. Suíte automatizada

```bash
make test
```

Esperado: toda a suíte passa, incluindo os testes `tests/test_fornecedores_*.py`. O teste com
arquivo real fica pulado sem `FORNECEDORES_CSV_REAL`.

```bash
FORNECEDORES_CSV_REAL=docs/CSVs/fornecedores.csv uv run --env-file .env pytest tests/test_fornecedores_arquivo_real.py
```

Esperado (SC-001, SC-002, SC-003): 10.035 recebidos e inseridos, 0 rejeitados, 18 bloqueados; os
campos gravados conferem com o arquivo; nenhum dado de conta, PIS, endereço ou contato no banco nem
na sessão.

## 2. Carga inicial (US1)

1. Entrar como `chefe`, abrir **Importar fornecedores** na Home e enviar
   `docs/CSVs/fornecedores.csv`.
2. Prévia: 10.035 recebidos, 10.035 a inserir, 0 a atualizar, 0 recusados, 0 ausentes. Conferir
   que nada foi gravado: a consulta de fornecedores continua vazia.
3. Confirmar. Esperado: mensagem com os totais, detalhe da execução, e cada etapa em menos de 30
   segundos (SC-006).
4. Enviar de novo e confirmar a mesma prévia duas vezes (voltar e reenviar o formulário). Esperado:
   uma única execução; a segunda tentativa leva ao detalhe com "já confirmada".

## 3. Consulta (US2)

Como `funcionario`:

1. Buscar por código `1`: um resultado.
2. Buscar por uma palavra do nome sem acento e em minúsculas: resultados com a palavra em qualquer
   posição do nome ou do nome fantasia.
3. Buscar pelo CNPJ de um fornecedor, formatado e só com dígitos: o mesmo resultado.
4. Localizar um bloqueado: situação e motivo visíveis.

Como `requisitante`: `/fornecedores/` responde 403. Nenhuma tela oferece criar, editar ou excluir.

## 4. Histórico e reimportação (US3, US4)

1. Copiar o arquivo real para um temporário fora do repositório; mudar o `NOME` de um registro,
   trocar `BLOQ_OPCAO` de `S` para `B` em outro e remover um terceiro.
2. Importar a cópia. Prévia: 1 ausente e 2 atualizados com alteração.
3. Confirmar. No detalhe: as alterações com valor anterior e novo; o bloqueado aparece como tal na
   consulta; o ausente continua igual.
4. `funcionario` abre `/fornecedores/importacoes/`: 403.
5. Apagar a cópia temporária.

## 5. Arquivos inválidos

Enviar um arquivo convertido para LF (sem CRLF): recusado inteiro, com mensagem de terminador. Um
arquivo sem a coluna `BLOQ_OPCAO`: recusado, citando a coluna.
