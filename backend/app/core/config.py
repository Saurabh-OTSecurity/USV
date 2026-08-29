from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str = "usv"
    database_user: str = "usv_app"
    database_password: str = ""
    app_env: str = "development"

    auth_secret_key: str = "dev-only-insecure-secret-change-me"
    auth_token_expiry_minutes: int = 30

    app_host: str = "127.0.0.1"
    app_port: int = 8000
    cors_allowed_origins: str = "http://localhost:4200"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.database_user}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )


settings = Settings()
