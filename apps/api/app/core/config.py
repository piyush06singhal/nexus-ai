"""Application configuration.

Configuration is loaded from environment variables and an optional `.env`
file via pydantic-settings. This is the single source of truth for runtime
settings across the application.

No secrets are hardcoded here — everything comes from the environment.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the NEXUS API."""

    # Application
    app_name: str = "NEXUS API"
    environment: Literal["development", "test", "production"] = "development"
    version: str = "0.1.0"
    log_level: str = "INFO"

    # API
    api_v1_prefix: str = "/api/v1"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # CORS
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:3001"]
    )

    # Database
    # Host port 5433 is the NEXUS Postgres mapped by docker-compose, avoiding
    # conflicts with a system Postgres on 5432. Override via DATABASE_URL.
    database_url: str = "postgresql+psycopg://nexus:nexus_dev@localhost:5433/nexus"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Pydantic settings behaviour
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached, lazily-created Settings instance."""
    return Settings()


settings = get_settings()
