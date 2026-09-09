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

    Configures logging and, when enabled, starts the workflow worker and
    scheduler daemon threads.
    """
    setup_logging()
    logger.info("NEXUS API starting", extra={"env": settings.environment})

    worker = None
    scheduler = None
    if settings.workflow_worker_enabled:
        from app.db.session import SessionLocal
        from app.workflow.scheduler import WorkflowScheduler
        from app.workflow.worker import WorkflowWorker

        worker = WorkflowWorker(
            SessionLocal,
            poll_interval=settings.workflow_worker_poll_interval,
        )
        scheduler = WorkflowScheduler(
            SessionLocal,
            poll_interval=settings.workflow_scheduler_poll_interval,
        )
        worker.start()
        scheduler.start()

    yield

    if worker is not None:
        worker.stop()
    if scheduler is not None:
        scheduler.stop()
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

    register_exception_handlers(app)

    # API versioning: mount v1 under its prefix. Future versions are additive.
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, str]:
        return {"service": settings.app_name, "docs": "/docs", "health": "/api/v1/health"}

    return app


app = create_app()
