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

    # Verification, recovery & evaluation (Phase 6)
    verification_enabled: bool = False  # True in tests: auto-verify inline
    verification_default_policy: str = "{}"  # JSON VerificationPolicy config
    recovery_enabled: bool = False  # True in tests: recovery runs inline
    recovery_execute_sync: bool = False
    recovery_execution_budget_json: str = "{}"  # max_retries/attempts/time/tokens/cost
    recovery_max_attempts: int = 3
    recovery_retry_base_delay_ms: int = 0
    evaluation_regression_threshold: float = 0.05
    escalation_auto_approve: bool = False
    failure_injection_enabled: bool = False

    # AI Employee OS (Phase 7)
    employee_default_capacity: int = 5
    employee_max_concurrent_tasks: int = 5
    employee_budget_default_monthly: float = 50.0
    employee_evaluation_on_task_complete: bool = False  # True in tests
    employee_context_max_tokens: int = 4000
    employee_audit_enabled: bool = True

    # Autonomous Startup Engine (Phase 9)
    # Bounded-autonomy hard limits from §63. Every autonomous action is checked
    # against these; anything beyond a limit requires a human approval gate.
    startup_max_operating_cycle_duration: int = 90  # minutes until a cycle is forced to checkpoint
    startup_max_autonomous_actions_per_cycle: int = 25
    startup_max_employees: int = 20  # MAX_AUTONOMOUS_EMPLOYEES (per company)
    startup_max_budget: float = 1500.0  # MAX_STARTUP_BUDGET (USD, per company)
    startup_max_projects_per_plan: int = 10
    startup_max_replanning_attempts: int = 3
    startup_max_concurrent_operations: int = 5
    startup_default_autonomy_level: str = (
        "bounded_autonomy"  # manual|assisted|bounded_autonomy|high_autonomy
    )
    startup_require_approval_for_high_risk: bool = (
        True  # deny high-risk autonomous actions without a gate
    )

    # Computer Use & External Integrations (Phase 10)
    # Governed external interaction boundaries. Every external action, browser or
    # computer session, and webhook ingest is bounded here; anything beyond a
    # limit is refused (approval gate or explicit hard block). These mirror the
    # §81 / §16 limits — no unbounded external behaviour anywhere.
    external_action_timeout_seconds: int = 60
    external_connect_timeout_seconds: int = 10
    external_read_timeout_seconds: int = 30
    max_external_actions: int = 500  # per company, hard ceiling on journaled actions
    max_browser_sessions: int = 10  # concurrent per company
    max_computer_sessions: int = 5  # concurrent per company
    max_browser_actions: int = 200  # actions per browser session
    max_computer_actions: int = 100  # actions per computer session
    max_browser_session_duration_minutes: int = 30
    max_computer_session_duration_minutes: int = 30
    max_browser_navigations: int = 50  # navigations per browser session
    max_page_size_bytes: int = 4096  # structured page observation size cap
    max_external_payload_bytes: int = 16384  # external action result cap
    max_webhook_payload_bytes: int = 16384
    max_external_events: int = 1000  # per company, retained external events
    external_rate_limit_per_minute: int = 60  # default per-provider rate limit
    external_circuit_breaker_threshold: int = 5
    external_circuit_breaker_reset_seconds: int = 30
    default_external_risk_policy_json: str = "{}"  # default integration policies
    ssrf_protection_enabled: bool = True
    prompt_injection_protection_enabled: bool = True
    external_workspace_root: str = ""  # empty ⇒ deterministic virtual workspace
    external_generic_http_connector_enabled: bool = (
        False  # arbitrary HTTP connector is off by default (§14)
    )
    external_webhook_hmac_secret: str = ""  # operator secret for signed webhooks (empty ⇒ 503)
    external_outbound_class: str = (
        "confidential"  # max data class allowed outward (§64 exfiltration)
    )

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
