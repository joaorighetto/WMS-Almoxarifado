# WMS-Almoxarifado — mapa raiz

Django monolith, server-driven (Templates + HTMX + CSS próprio). Código, docs e identificadores em pt-BR.

## Mapa de fontes
- `config/` — settings split (`settings/base.py` + `development|test|production`), `urls.py` (admin/, catalogo/, "" → contas).
- `contas/` — identidade, setores, papéis, login/home, middleware pós-login. Detalhes: `mem:contas/core`.
- `catalogo/` — catálogo de materiais importado do SCPI (CSV), consulta, histórico de importações. Detalhes: `mem:catalogo/core`.
- `static/` — CSS global (`fonts.css` com os `@font-face`, `tokens.css`, `base.css`, `components.css`), HTMX vendorizado (`static/vendor/htmx/`) e fontes Atkinson Hyperlegible Next/Mono auto-hospedadas com licença OFL (`static/vendor/fonts/`, sem CDN). CSS/JS por app em `<app>/static/<app>/`.
- `DESIGN.md` — design system vigente; `.impeccable/design.json` é o sidecar dele e `.impeccable/surfaces/` guarda os contratos de direção. Comentários de CSS/templates citam seções do DESIGN.md.
- `tests/` — suíte pytest única e plana (`test_<app>_<tema>.py`), fixtures CSV em `tests/fixtures/catalogo/`.
- `specs/NNN-*/` — artefatos Spec Kit por feature (spec/plan/tasks/research/contracts/data-model). Docstrings citam IDs deles (`FR-*`, `SC-*`, `research.md R*`, `T0**`).
- `docs/domain/permissions-matrix.md` (`PERM-*`, `ROLE-*`) e `invariants-matrix.md` (`INV-*`) — regras canônicas; código cita os IDs.
- `.specify/` vendorizado (excluído do ruff); `.claude/`, `.codex/`, `.agents/`, `.github/skills|agents` — tooling de agentes, não código de produto.

## Invariantes de projeto
- Autorização sempre por papel explícito (`User.tem_papel`), sem herança entre papéis e sem bypass de superusuário.
- Escritas críticas: `transaction.atomic` + `select_for_update` em ordem fixa ou `pg_advisory_xact_lock`; guardas vivem no model/queryset, não na view.
- Integridade também no banco (CheckConstraint/UniqueConstraint/FK PROTECT), não só em validação Python.
- PostgreSQL obrigatório (pg_trgm, advisory locks, `django.contrib.postgres`); não há suporte a SQLite.

Stack/versões: `mem:tech_stack`. Comandos: `mem:suggested_commands`. Estilo: `mem:conventions`. Gate de conclusão: `mem:task_completion`.
