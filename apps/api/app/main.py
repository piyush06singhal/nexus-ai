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

    Currently only configures logging. Database/Redis connections are created
    lazily on first use, so the app boots even if dependencies are down —
    the health endpoint reports their actual state.
    """
    setup_logging()
    logger.info("NEXUS API starting", extra={"env": settings.environment})
    yield
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
