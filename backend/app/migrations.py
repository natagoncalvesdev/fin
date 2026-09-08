"""Migrações leves executadas na inicialização (sem Alembic)."""

from sqlalchemy import text
from sqlalchemy.engine import Engine


def run_migrations(engine: Engine) -> None:
    """Aplica alterações incrementais em bancos já existentes."""
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE usuario ADD COLUMN IF NOT EXISTS sexo VARCHAR(20)")
        )
        # Integração com Telegram removida.
        conn.execute(text("ALTER TABLE usuario DROP COLUMN IF EXISTS id_telegram"))
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

        # Saúde / cofrinhos / conquistas: tabelas próprias, criadas pelo create_all.
        for nome, tabela, coluna in (
            ("ix_registro_peso_usuario_data", "registro_peso", "data_registro"),
            ("ix_registro_medidas_usuario_data", "registro_medidas", "data_registro"),
            ("ix_meta_peso_usuario_situacao", "meta_peso", "situacao"),
            ("ix_conquista_usuario_data", "conquista", "data_conquista"),
            ("ix_cofrinho_usuario_situacao", "cofrinho", "situacao"),
        ):
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS {nome} "
                    f"ON {tabela} (id_usuario, {coluna})"
                )
            )

        # `conquista` mudou de forma durante o desenvolvimento. Adiciona as
        # colunas novas e REMOVE as antigas — a coluna `nivel` era NOT NULL e,
        # se ficar, quebra todo INSERT novo (o modelo atual não a preenche).
        for coluna, tipo in (
            ("chave", "VARCHAR(120)"),
            ("icone", "VARCHAR(30)"),
            ("valor", "DOUBLE PRECISION"),
        ):
            conn.execute(text(f"ALTER TABLE conquista ADD COLUMN IF NOT EXISTS {coluna} {tipo}"))
        for coluna in ("nivel", "peso_alvo", "meta_uuid"):
            conn.execute(text(f"ALTER TABLE conquista DROP COLUMN IF EXISTS {coluna}"))
        # Linhas do schema antigo (sem `chave`) — a tabela é 100% derivada e se
        # repovoa sozinha no próximo carregamento.
        conn.execute(text("DELETE FROM conquista WHERE chave IS NULL"))

        # `usuario.meta_peso` foi a 1ª versão da meta de peso; agrupada agora na
        # tabela `meta_peso`. Coluna morta — remove.
        conn.execute(text("ALTER TABLE usuario DROP COLUMN IF EXISTS meta_peso"))

        # Cofrinhos: cada mês vira uma linha em `conta` (paga = guardada). O
        # modelo antigo (aporte_cofrinho + débito-espelho) foi substituído.
        conn.execute(text("ALTER TABLE conta ADD COLUMN IF NOT EXISTS id_cofrinho INTEGER"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_conta_id_cofrinho ON conta (id_cofrinho)"))
        conn.execute(text("DROP TABLE IF EXISTS aporte_cofrinho"))
        conn.execute(text("DELETE FROM debito WHERE compra LIKE 'Cofrinho: %'"))

        # Grupos (saúde) + cofrinhos compartilhados: tabelas próprias criadas pelo
        # create_all. As leituras sempre filtram por (usuário|grupo|cofrinho) +
        # situação (pendente/ativo).
        for nome, tabela, colunas in (
            ("ix_grupo_membro_usuario", "grupo_membro", "id_usuario, situacao"),
            ("ix_grupo_membro_grupo", "grupo_membro", "id_grupo, situacao"),
            ("ix_cofrinho_participante_usuario", "cofrinho_participante", "id_usuario, situacao"),
            ("ix_cofrinho_participante_cofrinho", "cofrinho_participante", "id_cofrinho, situacao"),
        ):
            conn.execute(
                text(f"CREATE INDEX IF NOT EXISTS {nome} ON {tabela} ({colunas})")
            )
