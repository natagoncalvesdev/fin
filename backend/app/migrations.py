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

        # Índices compostos (id_usuario, data): as leituras de mês/ano sempre
        # filtram por usuário + intervalo de data. Sem isto o Postgres varre
        # todas as linhas do usuário e filtra a data em memória.
        for nome, tabela, coluna in (
            ("ix_conta_usuario_data", "conta", "data_conta"),
            ("ix_entrada_usuario_data", "entrada", "data_entrada"),
            ("ix_debito_usuario_data", "debito", "data_debito"),
            ("ix_reservado_usuario_data", "reservado", "data_reservado"),
            ("ix_compra_cartao_usuario_comp", "compra_cartao", "data_competencia"),
        ):
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS {nome} "
                    f"ON {tabela} (id_usuario, {coluna})"
                )
            )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_fatura_usuario_ano "
                "ON fatura_cartao (id_usuario, ano)"
            )
        )

        # Saúde: registros de peso, medidas, metas e conquistas ficam em tabelas
        # próprias, criadas pelo create_all.
        for nome, tabela, coluna in (
            ("ix_registro_peso_usuario_data", "registro_peso", "data_registro"),
            ("ix_registro_medidas_usuario_data", "registro_medidas", "data_registro"),
            ("ix_meta_peso_usuario_situacao", "meta_peso", "situacao"),
            ("ix_conquista_usuario_data", "conquista", "data_conquista"),
        ):
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS {nome} "
                    f"ON {tabela} (id_usuario, {coluna})"
                )
            )
