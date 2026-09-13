"""Phase 12 router bundle.

Aggregates the simulation + optimization + experiments + benchmarks +
marketplace + recommendations + closed-loop routers under one mount so
``app/api/v1/router.py`` stays a one-liner.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.phase12.api.benchmarks import router as benchmarks_router
from app.phase12.api.cycle import router as cycle_router
from app.phase12.api.experiments import router as experiments_router
from app.phase12.api.marketplace import router as marketplace_router
from app.phase12.api.optimization import router as optimization_router
from app.phase12.api.recommendations import router as recommendations_router
from app.phase12.api.simulation import router as simulation_router

phase12_api_router = APIRouter()
phase12_api_router.include_router(simulation_router)
phase12_api_router.include_router(optimization_router)
phase12_api_router.include_router(experiments_router)
phase12_api_router.include_router(benchmarks_router)
phase12_api_router.include_router(marketplace_router)
phase12_api_router.include_router(recommendations_router)
phase12_api_router.include_router(cycle_router)

__all__ = ["phase12_api_router"]
