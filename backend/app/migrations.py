"""Migrações leves executadas na inicialização (sem Alembic)."""

from sqlalchemy import text
from sqlalchemy.engine import Engine


def run_migrations(engine: Engine) -> None:
    """Aplica alterações incrementais em bancos já existentes."""
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE usuario ADD COLUMN IF NOT EXISTS id_telegram VARCHAR(64)")
        )
        conn.execute(
            text("ALTER TABLE compra_cartao ADD COLUMN IF NOT EXISTS serie_uuid VARCHAR(36)")
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_compra_cartao_serie_uuid "
                "ON compra_cartao (serie_uuid)"
            )
        )
