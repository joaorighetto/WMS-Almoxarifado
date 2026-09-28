from django.apps import AppConfig
from django.db import connections
from django.db.models.signals import post_migrate


def criar_triggers_imutabilidade(using, **kwargs):
    """Cria, de forma idempotente, os triggers de banco que garantem a
    imutabilidade dos fatos de estoque (`INV-MOV-001`, research R7).

    `ItemEntrada`, `EstornoEntrada` e `MovimentacaoEstoque` recusam qualquer
    `UPDATE` ou `DELETE`. `Entrada` recusa qualquer `DELETE` e só aceita um
    `UPDATE` que mude exclusivamente `estornada` de `False` para `True`
    (o estorno em si é um `EstornoEntrada` próprio, também imutável).

    `CREATE OR REPLACE FUNCTION` e `DROP TRIGGER IF EXISTS` antes de
    `CREATE TRIGGER` tornam a criação idempotente: o `flush` dos testes
    transacionais (`django_db(transaction=True)`) reemite `post_migrate` a
    cada teste. Os nomes de tabela vêm de `Model._meta.db_table`, nunca de
    literais, para não descolar de uma eventual renomeação de modelo.

    Sem migrations nesta fase (Constitution XIII, v1.2.0): o handler roda a
    partir de `EstoqueConfig.ready()`, conectado a `post_migrate` com
    `sender=self`, depois que `migrate --run-syncdb` cria as tabelas. Quando
    as migrations voltarem, este SQL vira uma `RunSQL` versionada.
    """
    from estoque.models import (
        Entrada,
        EstornoEntrada,
        ItemEntrada,
        MovimentacaoEstoque,
    )

    tabela_entrada = Entrada._meta.db_table
    tabela_item = ItemEntrada._meta.db_table
    tabela_estorno = EstornoEntrada._meta.db_table
    tabela_movimentacao = MovimentacaoEstoque._meta.db_table

    with connections[using].cursor() as cursor:
        # Função genérica: recusa qualquer UPDATE ou DELETE. Usada pelas
        # tabelas totalmente imutáveis.
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION estoque_recusar_alteracao()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION
                    'Registro imutável: % não é permitido em %',
                    TG_OP, TG_TABLE_NAME;
            END;
            $$ LANGUAGE plpgsql;
            """
        )

        # Função específica de Entrada: DELETE sempre recusado; UPDATE só
        # aceito quando a única mudança é `estornada` de false para true.
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION estoque_entrada_recusar_alteracao()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION
                        'Registro imutável: DELETE não é permitido em %',
                        TG_TABLE_NAME;
                END IF;

                IF NOT (
                    NOT OLD.estornada
                    AND NEW.estornada
                    AND (to_jsonb(OLD) - 'estornada') = (to_jsonb(NEW) - 'estornada')
                ) THEN
                    RAISE EXCEPTION
                        'Registro imutável: em %, só é aceito o estorno '
                        '(estornada de false para true, sem outra mudança)',
                        TG_TABLE_NAME;
                END IF;

                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )

        for tabela in (tabela_item, tabela_estorno, tabela_movimentacao):
            cursor.execute(f'DROP TRIGGER IF EXISTS recusar_alteracao ON "{tabela}"')
            cursor.execute(
                f"""
                CREATE TRIGGER recusar_alteracao
                BEFORE UPDATE OR DELETE ON "{tabela}"
                FOR EACH ROW EXECUTE FUNCTION estoque_recusar_alteracao()
                """
            )

        cursor.execute(f'DROP TRIGGER IF EXISTS recusar_alteracao ON "{tabela_entrada}"')
        cursor.execute(
            f"""
            CREATE TRIGGER recusar_alteracao
            BEFORE UPDATE OR DELETE ON "{tabela_entrada}"
            FOR EACH ROW EXECUTE FUNCTION estoque_entrada_recusar_alteracao()
            """
        )


class EstoqueConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "estoque"

    def ready(self):
        post_migrate.connect(criar_triggers_imutabilidade, sender=self)
