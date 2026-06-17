"""Migrações leves executadas na inicialização (sem Alembic)."""

from sqlalchemy import text
from sqlalchemy.engine import Engine


def run_migrations(engine: Engine) -> None:
    """Aplica alterações incrementais em bancos já existentes."""
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE usuario ADD COLUMN IF NOT EXISTS id_telegram VARCHAR(64)")
        )
