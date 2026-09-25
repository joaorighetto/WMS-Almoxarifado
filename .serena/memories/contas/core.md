# contas — identidade, setores, papéis
Arquivos: `models.py` (núcleo), `admin.py` (única UI de administração), `views.py` (`WMSLoginView`, `HomeView`), `forms.py` (`WMSAuthenticationForm`), `middleware.py` (`RetornoPosLoginMiddleware`), templates `base.html` (layout global herdado pelos outros apps; declara a barra de trabalho no bloco `appbar`, só para autenticado), `_barra_trabalho.html` (parcial da barra: marca → Home, matrícula, logout POST), `login.html`, `home.html` (sobrescreve `appbar` só para passar `esconde_matricula_compacta`).

## Modelo
- `Papel` (TextChoices, códigos `ROLE-*`): catálogo fechado espelhando `permissions-matrix.md`; não é dado editável.
- `User` (AbstractBaseUser+PermissionsMixin): `USERNAME_FIELD="matricula"`, `REQUIRED_FIELDS=["setor"]`, FK `setor` PROTECT obrigatória (INV-ORG-001).
- `Setor` com `SetorQuerySet`; `PapelUsuario` (related_name `papeis`) com `PapelUsuarioQuerySet`.
- `chefes_ativos`, `_exigir_chefia_preservada`, `_exigir_chefia_nao_duplicada`: setor ativo tem exatamente um chefe (`ROLE-SECTOR-HEAD`).

## Invariantes codificadas (não contornar)
- Criar conta só via `User.objects.create_user/create_superuser`; cria conta + `ROLE-REQUESTER` na mesma transação. `UserQuerySet.create/bulk_create` levantam `ValidationError`.
- `update/bulk_update` com `is_active|is_superuser|setor|setor_id` são bloqueados (`UserQuerySet.CAMPOS_ORGANIZACIONAIS`); alterar via `User.save()`.
- `User.save()` de existente: identidade ativa não-superusuário precisa de `ROLE-REQUESTER`; superusuário técnico não pode ter papéis `ROLE-*`; desativar/transferir/reativar chefe checa chefia preservada/não duplicada.
- `QuerySet.delete()` de User itera `User.delete()` para aplicar guardas.
- Ordem de lock: Usuário → Setor → PapelUsuario (`_bloquear_atribuicao` com retry `_MAX_TENTATIVAS_BLOQUEIO_ATRIBUICAO`). `Setor.save()` trava só setor.
- `RetornoPosLoginMiddleware`: só converte `PermissionDenied` em redirect à Home quando a requisição é a tentativa de retorno pós-login marcada na sessão; demais 403 inalterados.
- Testes relacionados: `tests/test_contas_*.py` (incl. `test_contas_revisao_integridade.py` para concorrência/integridade).
