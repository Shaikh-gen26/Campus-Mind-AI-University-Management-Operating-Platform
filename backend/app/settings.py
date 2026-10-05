from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from typing import Annotated


class Settings(BaseSettings):
    database_url: str = "sqlite:///./campusmind.db"
    jwt_secret: str = "development-only-change-this-secret"
    access_token_minutes: int = Field(default=60, gt=0, le=1440)
    app_env: str = "development"
    ai_api_key: str = ""
    ai_model: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    allowed_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "api"]
    )
    attendance_alert_threshold: float = Field(default=75.0, ge=0, le=100)
    demo_password: str = ""
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=20, ge=0, le=100)
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("cors_origins", "allowed_hosts", mode="before")
    @classmethod
    def split_csv_values(cls, value):
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @model_validator(mode="after")
    def validate_production_settings(self):
        if self.app_env.lower() != "production":
            return self

        if (
            len(self.jwt_secret) < 32
            or "replace" in self.jwt_secret.lower()
            or "change-me" in self.jwt_secret.lower()
            or self.jwt_secret == "development-only-change-this-secret"
        ):
            raise ValueError("Production requires a unique JWT_SECRET of at least 32 characters")
        if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("Production requires PostgreSQL through DATABASE_URL")
        if "replace" in self.database_url.lower():
            raise ValueError("Replace database URL placeholders before production")
        if (
            not self.allowed_hosts
            or "*" in self.allowed_hosts
            or all(host in {"localhost", "127.0.0.1", "api"} for host in self.allowed_hosts)
        ):
            raise ValueError("Production requires explicit ALLOWED_HOSTS")
        if (
            not self.cors_origins
            or "*" in self.cors_origins
            or any(not origin.startswith("https://") for origin in self.cors_origins)
        ):
            raise ValueError("Production requires explicit CORS_ORIGINS")
        if self.ai_api_key and not self.ai_base_url.startswith("https://"):
            raise ValueError("Production AI provider connections must use HTTPS")
        if self.demo_password:
            raise ValueError("DEMO_PASSWORD must be unset in production")

        return self


settings = Settings()
