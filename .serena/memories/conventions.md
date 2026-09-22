# Convenções
- Nomes de domínio em pt-BR (classes, funções, campos, mensagens): `ExecucaoImportacao`, `calcular_plano`, `tem_papel`. Termos Django/infra permanecem em inglês.
- Docstrings em pt-BR explicam *por quê* e citam rastreabilidade: `INV-*`, `PERM-*`, `FR-*`, `SC-*`, `research.md R*`, `T0**`. Ao alterar comportamento, manter as citações coerentes com as matrizes.
- Helpers privados com prefixo `_`; constantes de módulo em MAIÚSCULAS no topo.
- Views: CBVs; autorização por mixin com `papel_exigido` (ex.: `catalogo.views.ExigePapelMixin`) — anônimo → login, sem papel → 403.
- Lógica de domínio fora das views, em módulos de serviço do app (ex.: `catalogo/importacao.py`, `catalogo/leitura_scpi.py`); dataclasses `frozen=True` para DTOs de plano/resultado; exceções de domínio próprias.
- Guardas de invariantes nos models/QuerySets: QuerySets customizados bloqueiam `create/bulk_create/update/bulk_update/delete` que contornariam `save()/delete()`.
- Concorrência: locks em ordem fixa Usuário → Setor → PapelUsuario (contas); advisory lock para importação (catalogo).
- Testes: pytest funcional (não unittest), um arquivo por tema `tests/test_<app>_<tema>.py`; criar usuários só via `User.objects.create_user` (fixture `criar_usuario` em `tests/conftest.py`), nunca instanciando `User` à mão.
- Templates por app em `<app>/templates/<app>/`; parciais prefixados com `_` (alvos HTMX).
