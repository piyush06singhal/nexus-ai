"""Phase 12 resource governance (§ Wave G).

Wraps the Phase 11 :class:`~app.security.resources.ResourceGovernanceService`
with the Phase 12 category set (sim runs/iterations/events, optimization
candidates, benchmark cases/runs, experiment runs, marketplace ops) and an
in-process concurrency gate for simultaneous simulation/optimization run
execution. Limits are *configured* through the same Phase 11 resource-limit
endpoints/settings; the helper only records consumption and DENIES when a
configured budget is exceeded. When no limit is configured, categories are
unlimited (the engine's own hard ceilings — max ticks/events/iterations,
timeouts — still bound every run).
"""

from __future__ import annotations

import threading
from uuid import UUID

from sqlalchemy.orm import Session

from app.phase12._errors import SimulationEngineError
from app.security.resources import ResourceGovernanceService

# Phase 12 categories (mirrors ResourceCategory additions in the model).
PHASE12_CATEGORIES: dict[str, str] = {
    "sim_runs": "simulation runs started (per day)",
    "sim_iterations": "simulation iterations executed (per day)",
    "sim_events": "simulation events recorded (per day)",
    "optimization_candidates": "optimization candidates generated (per day)",
    "benchmark_cases": "benchmark cases executed (per day)",
    "benchmark_runs": "benchmark runs started (per day)",
    "experiment_runs": "experiment runs started (per day)",
    "marketplace_ops": "marketplace install/publish/deprecate operations (per day)",
}

# Hard in-process ceiling on simultaneous Phase 12 run executions. 0 =
# unlimited (the default); operators can tighten this constant for shipping.
MAX_CONCURRENT_PHASE12_RUNS = 8


class Phase12Governance:
    """Record & enforce Phase 12 consumption through ResourceGovernanceService."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._svc = ResourceGovernanceService(db)

    def check(
        self,
        category: str,
        amount: float,
        *,
        company_id: UUID | None = None,
    ) -> None:
        """Record usage; raise SimulationEngineError when a budget is exceeded.

        Transforms the Phase 11 :class:`ResourceExceededError` into the engine's
        error so an over-budget run fails honestly with the budget message.
        """
        if category not in PHASE12_CATEGORIES:
            raise SimulationEngineError(f"Unknown Phase 12 resource category {category!r}")
        try:
            self._svc.check_and_record(
                category=category,
                amount=amount,
                company_id=company_id,
                period="per_day",
            )
        except Exception as exc:  # ResourceExceededError (PermissionDeniedError)
            raise SimulationEngineError(str(exc)) from exc

    def remaining(self, category: str, *, company_id: UUID | None = None) -> float | None:
        """Return remaining budget in the current day, or None when unlimited."""
        limit = self._svc.effective_limit(category, company_id=company_id, period="per_day")
        if limit is None:
            return None
        used = self._svc.consumed(category, company_id=company_id, period="per_day")
        return max(0.0, limit - used)


class Phase12RunBudget:
    """Count-down interface used by engines at run boundaries.

    ``checkrecord`` both enforces and records: over an explicit limit it raises,
    otherwise consumption is recorded for observability. Hard engine ceilings
    (max ticks/events/iterations, timeout) are enforced separately inside the
    engine and are always active.
    """

    def __init__(self, db: Session) -> None:
        self._gov = Phase12Governance(db)

    def checkrecord(
        self,
        category: str,
        amount: float,
        *,
        company_id: UUID | None = None,
    ) -> None:
        self._gov.check(category, amount, company_id=company_id)


class ConcurrentRunGate:
    """In-process concurrency gate for Phase 12 run execution.

    Tracks live executions per company; ``acquire`` raises when the configured
    ceiling (``MAX_CONCURRENT_PHASE12_RUNS``) is reached. 0 = unlimited.
    """

    def __init__(self, max_concurrent: int = MAX_CONCURRENT_PHASE12_RUNS) -> None:
        self._max = max_concurrent
        self._lock = threading.Lock()
        self._active: dict[UUID | None, int] = {}

    @property
    def max_concurrent(self) -> int:
        return self._max

    def acquire(self, company_id: UUID | None) -> None:
        if self._max <= 0:
            return
        with self._lock:
            current = self._active.get(company_id, 0)
            if current >= self._max:
                raise SimulationEngineError(
                    f"Concurrency budget exceeded: {current} live Phase 12 runs "
                    f"for company {company_id} (max {self._max})"
                )
            self._active[company_id] = current + 1

    def release(self, company_id: UUID | None) -> None:
        with self._lock:
            current = self._active.get(company_id, 0)
            if current <= 1:
                self._active.pop(company_id, None)
            else:
                self._active[company_id] = current - 1


__all__ = [
    "ConcurrentRunGate",
    "PHASE12_CATEGORIES",
    "Phase12Governance",
    "Phase12RunBudget",
]
