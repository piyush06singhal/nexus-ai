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

    # Workflow orchestration
    workflow_worker_enabled: bool = False
    workflow_worker_poll_interval: float = 1.0
    workflow_scheduler_poll_interval: float = 30.0
    workflow_max_steps: int = 50
    workflow_max_execution_duration_seconds: int = 3600
    workflow_execute_sync: bool = False  # True in tests: execute runs inline

    # Memory system (Phase 4)
    memory_embedding_provider: str | None = None  # "openai" to enable embeddings, else None
    memory_embedding_model: str = "text-embedding-3-small"
    memory_embedding_dimensions: int = 1536
    memory_retrieval_weight_semantic: float = 0.4
    memory_retrieval_weight_recency: float = 0.2
    memory_retrieval_weight_importance: float = 0.2
    memory_retrieval_weight_confidence: float = 0.2
    memory_retrieval_context_budget: int = 5000
    memory_retrieval_relevance_threshold: float = 0.3
    memory_retrieval_max_memories: int = 20
    memory_write_min_importance: float = 0.1
    memory_write_dedup_threshold: float = 0.95
    memory_write_max_working: int = 50
    memory_write_default_ttl_hours: int = 24
    memory_extraction_enabled: bool = True

    # Multi-agent orchestration (Phase 5)
    orchestration_worker_enabled: bool = False
    orchestration_execute_sync: bool = False  # True in tests: execute runs inline
    orchestration_default_strategy: str = "deterministic"
    orchestration_max_agents: int = 20
    orchestration_max_tasks: int = 50
    orchestration_max_parallel_agents: int = 5
    orchestration_max_parallel_tasks: int = 5
    orchestration_max_execution_duration_seconds: int = 3600
    orchestration_max_execution_iterations: int = 100
    orchestration_max_messages_per_orchestration: int = 500
    orchestration_max_review_iterations: int = 3
    orchestration_token_budget: int | None = None
    orchestration_cost_budget: float | None = None
    orchestration_conflict_numeric_threshold: float = 0.2
    orchestration_memory_namespace: str = "orchestration"

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
