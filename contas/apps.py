from django.apps import AppConfig
from django.db import connections
from django.db.models.signals import post_migrate


def criar_triggers_organizacao(using, **kwargs):
    """Cria, de forma idempotente, os triggers de banco da organização
    (research R5 da 005; `INV-ORG-002`, `INV-ORG-004` a `INV-ORG-006`,
    FR-016a da 002, FR-030 e FR-041).

    - `contas_setor_proteger_designacao` (`BEFORE UPDATE` em `Setor`): recusa
      mudar `almoxarifado` (`INV-ORG-004`) e mudar `ativado_em` já preenchido
      (FR-030).
    - `contas_evento_recusar_alteracao` (`BEFORE UPDATE OR DELETE` em
      `EventoOrganizacional`): o histórico só recebe acréscimos (FR-041).
    - `contas_verificar_organizacao` (`CONSTRAINT TRIGGER ... DEFERRABLE
      INITIALLY DEFERRED` em `User`, `PapelUsuario` e `Setor`): no commit, toma
      o mesmo advisory lock das operações (research R2) e verifica, para os
      setores e usuários tocados, as quatro regras de "Verificação de estado
      final" de `data-model.md`. É adiado de propósito: a substituição de
      chefia passa por estados intermediários inválidos dentro da transação.
      Só dispara em escrita organizacional — em `contas_user`, o UPDATE só
      dispara quando `setor_id`, `is_active` ou `is_superuser` mudam de fato
      (`WHEN ... IS DISTINCT FROM`) —, então o login (`last_login`), a
      regravação do hash de senha e um `save()` completo sem mudança não o
      disparam nem tomam o lock. A função é VOLATILE (padrão do plpgsql): cada
      consulta enxerga o que outra transação já confirmou, mesmo em READ
      COMMITTED. As recusas de regra são `check_violation`; o advisory lock
      no commit só espera, e só entre escritas organizacionais efetivas, que
      as operações já serializam pelo mesmo lock (research R2).

    Nenhum trigger é de TRUNCATE: o `flush` dos testes transacionais precisa
    funcionar. `CREATE OR REPLACE FUNCTION` e `DROP TRIGGER IF EXISTS` antes
    de cada `CREATE` tornam o handler idempotente (o `flush` reemite
    `post_migrate` a cada teste). Os nomes de tabela e coluna vêm de `_meta`.

    Sem migrations nesta fase (Constitution XIII, v1.2.0): o handler é
    conectado a `post_migrate` com `sender=self` em `ContasConfig.ready()`,
    depois que `migrate --run-syncdb` cria as tabelas. Quando as migrations
    voltarem, este SQL vira uma `RunSQL` versionada.
    """
    from contas.models import EventoOrganizacional, Papel, PapelUsuario, Setor, User
    from contas.organizacao import CHAVE_LOCK_ORGANIZACAO

    t_setor = Setor._meta.db_table
    t_user = User._meta.db_table
    t_papel = PapelUsuario._meta.db_table
    t_evento = EventoOrganizacional._meta.db_table
    c_user_setor = User._meta.get_field("setor").column
    c_papel_usuario = PapelUsuario._meta.get_field("usuario").column

    requisitante = Papel.REQUISITANTE.value
    chefe_setor = Papel.CHEFE_SETOR.value
    staff = Papel.FUNCIONARIO_ALMOXARIFADO.value
    chefe_almox = Papel.CHEFE_ALMOXARIFADO.value

    with connections[using].cursor() as cursor:
        # --- Setor: designação e primeira ativação imutáveis -----------------
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION contas_setor_proteger_designacao()
            RETURNS trigger AS $$
            BEGIN
                IF NEW.almoxarifado IS DISTINCT FROM OLD.almoxarifado THEN
                    RAISE EXCEPTION
                        'INV-ORG-004: a designação de Almoxarifado do setor % não muda',
                        OLD.id;
                END IF;
                IF OLD.ativado_em IS NOT NULL
                   AND NEW.ativado_em IS DISTINCT FROM OLD.ativado_em THEN
                    RAISE EXCEPTION
                        'FR-030: o momento da primeira ativação do setor % não muda',
                        OLD.id;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        cursor.execute(f'DROP TRIGGER IF EXISTS proteger_designacao ON "{t_setor}"')
        cursor.execute(
            f"""
            CREATE TRIGGER proteger_designacao
            BEFORE UPDATE ON "{t_setor}"
            FOR EACH ROW EXECUTE FUNCTION contas_setor_proteger_designacao()
            """
        )

        # --- Evento organizacional: só de acréscimo --------------------------
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION contas_evento_recusar_alteracao()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION
                    'Registro imutável: % não é permitido em %',
                    TG_OP, TG_TABLE_NAME;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        cursor.execute(f'DROP TRIGGER IF EXISTS recusar_alteracao ON "{t_evento}"')
        cursor.execute(
            f"""
            CREATE TRIGGER recusar_alteracao
            BEFORE UPDATE OR DELETE ON "{t_evento}"
            FOR EACH ROW EXECUTE FUNCTION contas_evento_recusar_alteracao()
            """
        )

        # --- Estado final: regras 1 e 3 (parte do setor) ---------------------
        cursor.execute(
            f"""
            CREATE OR REPLACE FUNCTION contas_verificar_setor(p_setor_id bigint)
            RETURNS void AS $$
            DECLARE
                v_ativo boolean;
                v_almoxarifado boolean;
                v_chefes integer;
            BEGIN
                SELECT ativo, almoxarifado INTO v_ativo, v_almoxarifado
                  FROM "{t_setor}" WHERE id = p_setor_id;
                IF NOT FOUND THEN
                    RETURN;
                END IF;

                SELECT count(*) INTO v_chefes
                  FROM "{t_user}" u
                 WHERE u."{c_user_setor}" = p_setor_id
                   AND u.is_active
                   AND EXISTS (
                       SELECT 1 FROM "{t_papel}" p
                        WHERE p."{c_papel_usuario}" = u.id AND p.papel = '{chefe_setor}');

                IF v_chefes > 1 THEN
                    RAISE EXCEPTION 'INV-ORG-002: o setor % tem mais de um chefe ativo', p_setor_id
                        USING ERRCODE = 'check_violation';
                END IF;
                IF v_ativo AND v_chefes <> 1 THEN
                    RAISE EXCEPTION 'INV-ORG-002: o setor ativo % não '
                        'tem exatamente um chefe ativo', p_setor_id
                        USING ERRCODE = 'check_violation';
                END IF;

                -- INV-ORG-006: com o Almoxarifado ativo, o chefe ativo tem os
                -- papéis de chefia e de funcionário do almoxarifado.
                IF v_ativo AND v_almoxarifado AND EXISTS (
                    SELECT 1 FROM "{t_user}" u
                     WHERE u."{c_user_setor}" = p_setor_id
                       AND u.is_active
                       AND EXISTS (
                           SELECT 1 FROM "{t_papel}" p
                            WHERE p."{c_papel_usuario}" = u.id AND p.papel = '{chefe_setor}')
                       AND NOT (
                           EXISTS (
                               SELECT 1 FROM "{t_papel}" p
                                WHERE p."{c_papel_usuario}" = u.id AND p.papel = '{chefe_almox}')
                           AND EXISTS (
                               SELECT 1 FROM "{t_papel}" p
                                WHERE p."{c_papel_usuario}" = u.id AND p.papel = '{staff}'))
                ) THEN
                    RAISE EXCEPTION 'INV-ORG-006: o chefe do Almoxarifado ativo % precisa de '
                        'ROLE-WAREHOUSE-HEAD e ROLE-WAREHOUSE-STAFF', p_setor_id
                        USING ERRCODE = 'check_violation';
                END IF;
            END;
            $$ LANGUAGE plpgsql;
            """
        )

        # --- Estado final: regras 2, 3 (parte do usuário) e 4 ----------------
        cursor.execute(
            f"""
            CREATE OR REPLACE FUNCTION contas_verificar_usuario(p_usuario_id bigint)
            RETURNS void AS $$
            DECLARE
                v_ativo boolean;
                v_tecnica boolean;
                v_setor_id bigint;
                v_almoxarifado boolean;
                v_algum boolean;
                v_requisitante boolean;
                v_chefe boolean;
                v_staff boolean;
                v_head boolean;
            BEGIN
                SELECT is_active, is_superuser, "{c_user_setor}"
                  INTO v_ativo, v_tecnica, v_setor_id
                  FROM "{t_user}" WHERE id = p_usuario_id;
                IF NOT FOUND THEN
                    RETURN;
                END IF;

                SELECT count(*) > 0,
                       COALESCE(bool_or(papel = '{requisitante}'), false),
                       COALESCE(bool_or(papel = '{chefe_setor}'), false),
                       COALESCE(bool_or(papel = '{staff}'), false),
                       COALESCE(bool_or(papel = '{chefe_almox}'), false)
                  INTO v_algum, v_requisitante, v_chefe, v_staff, v_head
                  FROM "{t_papel}" WHERE "{c_papel_usuario}" = p_usuario_id;

                -- FR-016a (002): a conta técnica não tem nenhum papel de negócio.
                IF v_tecnica THEN
                    IF v_algum THEN
                        RAISE EXCEPTION 'FR-016a: a conta técnica % não '
                            'pode ter papel de negócio', p_usuario_id
                        USING ERRCODE = 'check_violation';
                    END IF;
                    RETURN;
                END IF;

                -- FR-016a (002): identidade de negócio ativa tem ROLE-REQUESTER.
                IF v_ativo AND NOT v_requisitante THEN
                    RAISE EXCEPTION 'FR-016a: a conta ativa % precisa '
                        'de ROLE-REQUESTER', p_usuario_id
                        USING ERRCODE = 'check_violation';
                END IF;

                -- INV-ORG-005: papéis de almoxarifado só no setor Almoxarifado.
                IF v_staff OR v_head THEN
                    SELECT almoxarifado INTO v_almoxarifado
                      FROM "{t_setor}" WHERE id = v_setor_id;
                    IF NOT COALESCE(v_almoxarifado, false) THEN
                        RAISE EXCEPTION 'INV-ORG-005: papel de almoxarifado '
                            'fora do Almoxarifado (usuário %)', p_usuario_id
                        USING ERRCODE = 'check_violation';
                    END IF;
                END IF;

                -- INV-ORG-006: quem tem a chefia do almoxarifado é o chefe do setor e
                -- funcionário do almoxarifado.
                IF v_ativo AND v_head AND NOT (v_chefe AND v_staff) THEN
                    RAISE EXCEPTION 'INV-ORG-006: ROLE-WAREHOUSE-HEAD exige '
                        'ROLE-SECTOR-HEAD e ROLE-WAREHOUSE-STAFF (usuário %)', p_usuario_id
                        USING ERRCODE = 'check_violation';
                END IF;
            END;
            $$ LANGUAGE plpgsql;
            """
        )

        # --- Trigger adiado: despacha pelo que a linha tocou -----------------
        cursor.execute(
            f"""
            CREATE OR REPLACE FUNCTION contas_verificar_organizacao()
            RETURNS trigger AS $$
            BEGIN
                PERFORM pg_advisory_xact_lock({int(CHAVE_LOCK_ORGANIZACAO)});

                IF TG_TABLE_NAME = '{t_user}' THEN
                    IF TG_OP IN ('INSERT', 'UPDATE') THEN
                        PERFORM contas_verificar_usuario(NEW.id);
                        PERFORM contas_verificar_setor(NEW."{c_user_setor}");
                    END IF;
                    IF TG_OP IN ('UPDATE', 'DELETE') THEN
                        PERFORM contas_verificar_setor(OLD."{c_user_setor}");
                    END IF;
                ELSIF TG_TABLE_NAME = '{t_papel}' THEN
                    IF TG_OP IN ('INSERT', 'UPDATE') THEN
                        PERFORM contas_verificar_usuario(NEW."{c_papel_usuario}");
                        PERFORM contas_verificar_setor(u."{c_user_setor}")
                           FROM "{t_user}" u WHERE u.id = NEW."{c_papel_usuario}";
                    END IF;
                    IF TG_OP IN ('UPDATE', 'DELETE') THEN
                        PERFORM contas_verificar_usuario(OLD."{c_papel_usuario}");
                        PERFORM contas_verificar_setor(u."{c_user_setor}")
                           FROM "{t_user}" u WHERE u.id = OLD."{c_papel_usuario}";
                    END IF;
                ELSE
                    IF TG_OP IN ('INSERT', 'UPDATE') THEN
                        PERFORM contas_verificar_setor(NEW.id);
                    END IF;
                END IF;
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        for tabela in (t_user, t_papel, t_setor):
            cursor.execute(f'DROP TRIGGER IF EXISTS verificar_organizacao ON "{tabela}"')
        cursor.execute(f'DROP TRIGGER IF EXISTS verificar_organizacao_update ON "{t_user}"')
        # Em `contas_user` o UPDATE é separado do INSERT/DELETE: `WHEN` com `OLD` não vale
        # para INSERT. Só uma mudança efetiva de coluna organizacional dispara o trigger;
        # um `save()` completo sem mudança (o `UPDATE` inclui `setor_id`) não pede o
        # advisory lock segurando o lock da linha, o que deixaria uma operação concorrente
        # que já tem o lock e atualiza a mesma linha em deadlock.
        cursor.execute(
            f"""
            CREATE CONSTRAINT TRIGGER verificar_organizacao
            AFTER INSERT OR DELETE ON "{t_user}"
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION contas_verificar_organizacao()
            """
        )
        cursor.execute(
            f"""
            CREATE CONSTRAINT TRIGGER verificar_organizacao_update
            AFTER UPDATE ON "{t_user}"
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW
            WHEN (OLD."{c_user_setor}" IS DISTINCT FROM NEW."{c_user_setor}"
                  OR OLD.is_active IS DISTINCT FROM NEW.is_active
                  OR OLD.is_superuser IS DISTINCT FROM NEW.is_superuser)
            EXECUTE FUNCTION contas_verificar_organizacao()
            """
        )
        for tabela in (t_papel, t_setor):
            cursor.execute(
                f"""
                CREATE CONSTRAINT TRIGGER verificar_organizacao
                AFTER INSERT OR UPDATE OR DELETE ON "{tabela}"
                DEFERRABLE INITIALLY DEFERRED
                FOR EACH ROW EXECUTE FUNCTION contas_verificar_organizacao()
                """
            )


class ContasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "contas"

    def ready(self):
        post_migrate.connect(criar_triggers_organizacao, sender=self)
