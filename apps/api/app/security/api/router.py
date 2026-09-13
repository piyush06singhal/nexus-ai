"""Security router bundle (Phase 11).

Aggregates the auth + access + security + governance + system routers under
one mount so ``app/api/v1/router.py`` stays a one-liner.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.security.api.access import router as access_router
from app.security.api.auth import router as auth_router
from app.security.api.data_protection import router as data_router
from app.security.api.governance import router as governance_router
from app.security.api.security_ops import router as security_router
from app.security.api.system import router as system_router

security_api_router = APIRouter()
security_api_router.include_router(auth_router)
security_api_router.include_router(access_router)
security_api_router.include_router(security_router)
security_api_router.include_router(governance_router)
security_api_router.include_router(data_router)
security_api_router.include_router(system_router)

__all__ = ["security_api_router"]
