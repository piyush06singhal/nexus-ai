"""NEXUS FastAPI application entry point.

Factory-style app with a lifespan hook for startup/shutdown, CORS, the v1
router, and structured exception handlers. Versioning lives in the prefix
constant from :mod:`app.core.config`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup/shutdown lifecycle.

    Configures logging and, when enabled, starts the workflow worker,
    workflow scheduler, and orchestration worker daemon threads. Worker
    startup is shared with the headless worker process (``app.main_worker``)
    via :func:`app.workers.start_workers`, so an independently deployed
    worker container consumes the queues instead of the API process.
    """
    setup_logging()
    logger.info("NEXUS API starting", extra={"env": settings.environment})

    from app.workers import start_workers, stop_workers

    worker_handles = start_workers()

    # Bootstrap admin: non-prod deployments with AUTH_DEV_BOOTSTRAP_* get a
    # usable login on first startup when no admin exists (no-op otherwise).
    if settings.auth_enabled and settings.auth_dev_bootstrap_email:
        from app.db.session import SessionLocal
        from app.security.identity import UserAccountManager

        session = SessionLocal()
        try:
            UserAccountManager(session).bootstrap_admin()
            session.commit()
        finally:
            session.close()

    # Governance: seed per-tenant resource limits from the resource_max_* config
    # defaults (global + one row per existing tenant). Flag-gated, idempotent —
    # off by default so dev/test start unlimited. Standalone alternative:
    # scripts/seed_resource_limits.py.
    if settings.resource_limits_provision:
        from sqlalchemy import select

        from app.db.models.company import Company
        from app.db.session import SessionLocal
        from app.security.resources import ResourceGovernanceService

        session = SessionLocal()
        try:
            company_ids = list(session.execute(select(Company.id)).scalars().all())
            ResourceGovernanceService(session).provision_default_limits(company_ids=company_ids)
            session.commit()
            logger.info(
                "resource_limits_provisioned",
                extra={"companies": len(company_ids), "env": settings.environment},
            )
        except Exception:  # noqa: BLE001 — provisioning must not take the API down
            logger.exception("resource_limits_provision_failed")
        finally:
            session.close()

    yield

    stop_workers(worker_handles)
    logger.info("NEXUS API shutting down")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="NEXUS API",
        description="Backend for NEXUS — an Autonomous AI Workforce & Company OS.",
        version=settings.version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Phase 11 — observability + API-security chain (each piece self-gated).
    from app.core.middleware import install_security_middleware

    install_security_middleware(app)

    # Phase 11 — bearer-token gate (inert when auth_enabled=False).
    from app.security.api.middleware import AuthMiddleware

    app.add_middleware(AuthMiddleware)

    register_exception_handlers(app)

    # API versioning: mount v1 under its prefix. Future versions are additive.
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, str]:
        return {"service": settings.app_name, "docs": "/docs", "health": "/api/v1/health"}

    return app


app = create_app()
