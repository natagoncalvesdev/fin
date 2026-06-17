"""Migrações leves executadas na inicialização (sem Alembic)."""

from sqlalchemy.engine import Engine


def run_migrations(engine: Engine) -> None:
    """Schema criado via Base.metadata.create_all. Reservado para migrações futuras."""
    del engine
