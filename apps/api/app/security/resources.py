"""Resource governance & runaway guard (Phase 11, §64–§66).

``resource_limits`` define per scope/category budgets; ``resource_usage``
records consumption. :class:`ResourceGovernanceService` enforces limits and
records usage such that an over-limit request is DENIED rather than allowed to
run. :class:`RunawayGuard` wraps a running workload (agent run / workflow /
orchestration) with budget checks — iterations, duration, token/cost/tool-call
ceilings — and can stop long loops, composing the pre-existing
``orchestration_max_*`` / ``workflow_max_*`` / ``external_*`` config limits.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import PermissionDeniedError
from app.core.logging import get_logger
from app.db.models.security import (
    ResourceCategory,
    ResourceLimit,
    ResourceLimitScope,
    ResourceUsage,
)

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


class ResourceGovernanceService:
    """Track budgets and gate consumption per category."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── configuration ──────────────────────────────────────────────────────

    def set_limit(
        self,
        *,
        category: str,
        limit_value: float,
        scope: str = ResourceLimitScope.GLOBAL.value,
        company_id: UUID | None = None,
        period: str | None = "per_day",
        set_by: UUID | None = None,
    ) -> ResourceLimit:
        existing = self.db.execute(
            select(ResourceLimit).where(
                ResourceLimit.scope == scope,
                ResourceLimit.category == category,
                ResourceLimit.period == period,
                ResourceLimit.tenant_id == company_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.max_value = limit_value
            existing.enforced = True
            existing.updated_at = _now()
            limit = existing
        else:
            limit = ResourceLimit(
                scope=scope,
                tenant_id=company_id,
                category=category,
                max_value=limit_value,
                period=period,
                enforced=True,
            )
            self.db.add(limit)
            self.db.flush()
        return limit

    def provision_default_limits(
        self,
        *,
        company_ids: list[UUID] | None = None,
        scope: str = ResourceLimitScope.GLOBAL.value,
        set_by: UUID | None = None,
    ) -> list[ResourceLimit]:
        """Seed `ResourceLimit` rows from the ``resource_max_*`` config defaults.

        Turns the tunable defaults into real governance rows: one entry per core
        category (tokens/cost/tool_calls/iterations/duration_seconds) *and* per
        Phase 12 category (sim_runs/optimization_candidates/…, using
        ``resource_max_phase12_default``), at ``scope`` (global by default) and,
        when ``company_ids`` is given, one per-tenant entry per company.
        Idempotent — re-running updates existing rows via :meth:`set_limit`
        instead of duplicating them.

        Gated by the ``RESOURCE_LIMITS_PROVISION`` flag at startup (see the app
        lifespan) or by running ``scripts/seed_resource_limits.py`` standalone.
        """
        defaults = {
            ResourceCategory.TOKENS.value: settings.resource_max_tokens_default,
            ResourceCategory.COST.value: settings.resource_max_cost_default,
            ResourceCategory.TOOL_CALLS.value: settings.resource_max_tool_calls_default,
            ResourceCategory.ITERATIONS.value: settings.resource_max_iterations_default,
            ResourceCategory.DURATION_SECONDS.value: settings.resource_max_duration_seconds_default,
        }
        # Phase 12 category set (lazy import — governance.py imports this module;
        # a top-level import would be circular).
        try:
            from app.phase12.governance import PHASE12_CATEGORIES

            for category in PHASE12_CATEGORIES:
                defaults[category] = settings.resource_max_phase12_default
        except ImportError:
            PHASE12_CATEGORIES = {}  # noqa: F841 — phase12 absent: core only

        created: list[ResourceLimit] = []
        for category, limit_value in defaults.items():
            created.append(
                self.set_limit(
                    category=category,
                    limit_value=float(limit_value),
                    scope=scope,
                    period="per_day",
                    set_by=set_by,
                )
            )
            for company_id in company_ids or []:
                created.append(
                    self.set_limit(
                        category=category,
                        limit_value=float(limit_value),
                        scope=ResourceLimitScope.COMPANY.value,
                        company_id=company_id,
                        period="per_day",
                        set_by=set_by,
                    )
                )
        return created

    def effective_limit(
        self, category: str, *, company_id: UUID | None = None, period: str | None = "per_day"
    ) -> float | None:
        """Most-restrictive applicable limit. ``None`` = unlimited."""
        scopes = [ResourceLimitScope.GLOBAL.value]
        if company_id is not None:
            scopes.append(ResourceLimitScope.COMPANY.value)
        stmt = select(ResourceLimit).where(
            ResourceLimit.category == category,
            ResourceLimit.enforced.is_(True),
            ResourceLimit.period == period,
        )
        candidates = []
        for limit in self.db.execute(stmt).scalars().all():
            if limit.scope == ResourceLimitScope.GLOBAL.value:
                candidates.append((0, limit.max_value))
            elif limit.scope == ResourceLimitScope.COMPANY.value and limit.tenant_id == company_id:
                candidates.append((1, limit.max_value))
        if not candidates:
            # Fall through to config defaults.
            return self._config_default(category, period)
        candidates.sort(key=lambda c: c[0])
        return max(c[1] for c in candidates if c[1] > 0) or (
            min(c[1] for c in candidates) if candidates else None
        )

    # ── consumption ────────────────────────────────────────────────────────

    def record_usage(
        self,
        *,
        category: str,
        amount: float,
        company_id: UUID | None = None,
        tenant_id: UUID | None = None,
        actor_id: UUID | None = None,
        unit: str | None = None,
        instrument: str | None = None,
        reference_id: str | None = None,
    ) -> ResourceUsage:
        usage = ResourceUsage(
            company_id=company_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            category=category,
            amount=amount,
            unit=unit,
            instrument=instrument,
            reference_id=reference_id,
            recorded_at=_now(),
        )
        self.db.add(usage)
        self.db.flush()
        return usage

    def check_and_record(
        self,
        *,
        category: str,
        amount: float,
        company_id: UUID | None = None,
        tenant_id: UUID | None = None,
        actor_id: UUID | None = None,
        period: str = "per_day",
    ) -> ResourceUsage:
        """Record usage; raise :class:`ResourceExceededError` when over budget."""
        limit = self.effective_limit(category, company_id=company_id, period=period)
        current = self.consumed(category, company_id=company_id, period=period)
        if limit is not None and current + amount > limit:
            raise ResourceExceededError(
                f"Resource budget exceeded for {category}: {current + amount:.2f} > {limit:.2f}.",
                category=category,
                limit=limit,
                current=current,
            )
        return self.record_usage(
            category=category,
            amount=amount,
            company_id=company_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )

    def consumed(
        self, category: str, *, company_id: UUID | None = None, period: str = "per_day"
    ) -> float:
        since = _period_start(period)
        stmt = select(func.coalesce(func.sum(ResourceUsage.amount), 0.0)).where(
            ResourceUsage.category == category,
            ResourceUsage.recorded_at >= since,
        )
        if company_id is not None:
            stmt = stmt.where(ResourceUsage.company_id == company_id)
        return float(self.db.execute(stmt).scalar() or 0.0)

    def usage_summary(self, company_id: UUID | None = None, limit: int = 100) -> list[dict]:
        stmt = select(ResourceUsage).order_by(ResourceUsage.recorded_at.desc()).limit(limit)
        if company_id is not None:
            stmt = stmt.where(ResourceUsage.company_id == company_id)
        return [
            {
                "category": u.category,
                "amount": u.amount,
                "unit": u.unit,
                "company_id": str(u.company_id) if u.company_id else None,
                "actor_id": str(u.actor_id) if u.actor_id else None,
                "instrument": u.instrument,
                "recorded_at": u.recorded_at.isoformat(),
            }
            for u in self.db.execute(stmt).scalars().all()
        ]

    def _config_default(self, category: str, period: str) -> float | None:
        if period != "per_day":
            return None
        defaults = {
            ResourceCategory.TOKENS.value: getattr(
                settings, "resource_default_tokens_per_day", None
            ),
            ResourceCategory.COST.value: getattr(settings, "resource_default_cost_per_day", None),
            ResourceCategory.TOOL_CALLS.value: getattr(
                settings, "resource_default_tool_calls_per_day", None
            ),
            ResourceCategory.ITERATIONS.value: getattr(
                settings, "orchestration_max_iterations", None
            ),
        }
        return defaults.get(category)


class RunawayGuard:
    """Budget enforcement wrapper for a single running workload.

    Usage::

        guard = RunawayGuard(max_iterations=…, max_duration_seconds=…,
                             max_tool_calls=…, max_tokens=…)
        with guard.each() as frame:
            frame.record_tool_call(); frame.record_tokens(123)
            frame.ensure_within()   # raises RunawayGuardStopped when over budget

    ``stopped`` is populated with *why* the workload was halted.
    """

    def __init__(
        self,
        *,
        max_iterations: int | None = None,
        max_duration_seconds: int | None = None,
        max_tool_calls: int | None = None,
        max_tokens: int | None = None,
        max_cost: float | None = None,
        label: str = "workload",
    ) -> None:
        self.max_iterations = max_iterations
        self.max_duration_seconds = max_duration_seconds
        self.max_tool_calls = max_tool_calls
        self.max_tokens = max_tokens
        self.max_cost = max_cost
        self.label = label

    def frame(self) -> RunawayGuardFrame:
        return RunawayGuardFrame(self)

    def default_bounds(self) -> RunawayGuard:
        """Apply the configured production ceilings to a fresh guard."""
        merged = dict(
            max_iterations=_first(
                self.max_iterations,
                getattr(settings, "orchestration_max_iterations", None),
                100,
            ),
            max_duration_seconds=_first(
                self.max_duration_seconds,
                getattr(settings, "agent_max_duration_seconds", None),
                getattr(settings, "workflow_max_duration_seconds", None),
            ),
            max_tool_calls=_first(
                self.max_tool_calls,
                getattr(settings, "agent_max_tool_calls", None),
                getattr(settings, "workflow_max_tool_calls", None),
            ),
            max_tokens=getattr(settings, "agent_max_tokens", None),
            max_cost=getattr(settings, "runaway_guard_max_cost", None),
            label=self.label,
        )
        return RunawayGuard(**merged)


class RunawayGuardFrame:
    """Per-workload accounting; raises when any budget is exceeded."""

    def __init__(self, guard: RunawayGuard) -> None:
        self.guard = guard
        self.started = time.monotonic()
        self.iterations = 0
        self.tool_calls = 0
        self.tokens = 0
        self.cost = 0.0

    def _elapsed(self) -> float:
        return time.monotonic() - self.started

    def record_iteration(self) -> RunawayGuardFrame:
        self.iterations += 1
        return self

    def record_tool_call(self, count: int = 1) -> RunawayGuardFrame:
        self.tool_calls += count
        return self

    def record_tokens(self, count: int) -> RunawayGuardFrame:
        self.tokens += count
        return self

    def record_cost(self, amount: float) -> RunawayGuardFrame:
        self.cost += amount
        return self

    def ensure_within(self) -> None:
        g = self.guard
        if g.max_iterations is not None and self.iterations > g.max_iterations:
            raise RunawayGuardStopped(
                "iterations", self.iterations, g.max_iterations, self.guard.label
            )
        if g.max_tool_calls is not None and self.tool_calls > g.max_tool_calls:
            raise RunawayGuardStopped(
                "tool_calls", self.tool_calls, g.max_tool_calls, self.guard.label
            )
        if g.max_tokens is not None and self.tokens > g.max_tokens:
            raise RunawayGuardStopped("tokens", self.tokens, g.max_tokens, self.guard.label)
        if g.max_cost is not None and self.cost > g.max_cost:
            raise RunawayGuardStopped("cost", self.cost, g.max_cost, self.guard.label)
        if g.max_duration_seconds is not None and self._elapsed() > g.max_duration_seconds:
            raise RunawayGuardStopped(
                "duration", self._elapsed(), g.max_duration_seconds, self.guard.label
            )


class ResourceExceededError(PermissionDeniedError):
    def __init__(
        self,
        message: str,
        *,
        category: str,
        limit: float,
        current: float,
        code: str = "resource_limit_exceeded",
    ) -> None:
        self.category = category
        self.limit = limit
        self.current = current
        super().__init__(message, code=code)


class RunawayGuardStopped(Exception):
    """Raised when a budget proves exceeded — the workload must halt (no roll-back)."""

    def __init__(self, dimension: str, observed, limit, label: str) -> None:
        self.dimension = dimension
        self.observed = observed
        self.limit = limit
        self.label = label
        super().__init__(f"Runaway guard stopped {label}: {dimension} {observed} exceeds {limit}.")


def _period_start(period: str) -> datetime:
    now = _now()
    if period == "per_day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "per_hour":
        return now.replace(minute=0, second=0, microsecond=0)
    if period == "per_week":
        start = now.date() - timedelta(days=now.weekday())
        return datetime(start.year, start.month, start.day, tzinfo=UTC)
    return now.replace(minute=0, second=0, microsecond=0)


def _first(*values):
    for value in values:
        if value is not None:
            return value
    return None
