from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str = "dev-secret-key-change-in-production"
    database_url: str = "postgresql://fin:fin@localhost:5432/fin"
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 dias
    n8n_webhook_relatorio_url: str = "https://n8n.natdev.com.br/webhook/relatorio-fin"
    n8n_webhook_relatorio_url_internal: str = ""
    n8n_webhook_host_header: str = ""
    integration_api_key: str = "dev-integration-key-change-in-production"

    class Config:
        env_file = ".env"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def n8n_webhook_url(self) -> str:
        interna = self.n8n_webhook_relatorio_url_internal.strip()
        if interna:
            return interna
        return self.n8n_webhook_relatorio_url.strip()


settings = Settings()
