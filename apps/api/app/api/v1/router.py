"""Version 1 API router.

Aggregates all v1 endpoints under a single router, mounted in ``main.py``
with the configured prefix. Adding a v2 API later is additive: create a
``v2`` package and mount its router alongside this one.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import health

api_router = APIRouter()
api_router.include_router(health.router)
