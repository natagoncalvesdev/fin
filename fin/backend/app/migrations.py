"""Migrações leves executadas na inicialização (sem Alembic)."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


FINANCEIRO_TABELAS = (
    "contas",
    "adicionais",
    "debitos",
    "reservados",
    "compras_cartao",
    "vale_cargas",
)


def run_migrations(engine: Engine) -> None:
    if not engine.url.drivername.startswith("postgresql"):
        return

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table in FINANCEIRO_TABELAS:
            if table not in existing_tables:
                continue

            columns = {col["name"] for col in inspector.get_columns(table)}
            if "user_id" not in columns:
                conn.execute(
                    text(f'ALTER TABLE "{table}" ADD COLUMN user_id VARCHAR(36)')
                )

            conn.execute(
                text(
                    f"""
                    UPDATE "{table}" AS t
                    SET user_id = m.user_id
                    FROM meses_financeiros AS m
                    WHERE t.mes_id = m.id AND t.user_id IS NULL
                    """
                )
            )

            conn.execute(
                text(
                    f"""
                    DO $$ BEGIN
                        ALTER TABLE "{table}"
                        ADD CONSTRAINT fk_{table}_user_id
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
                    EXCEPTION WHEN duplicate_object THEN NULL;
                    END $$;
                    """
                )
            )

            conn.execute(
                text(
                    f'CREATE INDEX IF NOT EXISTS ix_{table}_user_id ON "{table}" (user_id)'
                )
            )

            conn.execute(
                text(
                    f"""
                    DO $$ BEGIN
                        ALTER TABLE "{table}" ALTER COLUMN user_id SET NOT NULL;
                    EXCEPTION WHEN others THEN NULL;
                    END $$;
                    """
                )
            )
