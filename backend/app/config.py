from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str = "dev-secret-key-change-in-production"
    database_url: str = "postgresql://fin:fin@localhost:5432/fin"
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 dias

    class Config:
        env_file = ".env"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
