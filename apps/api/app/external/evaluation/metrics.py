"""External metrics aggregation (Phase 10, §61).

Aggregates a per-company health snapshot from the external journal —
``external_actions`` (+ their attempt/verification/recovery traces), the
``external_events`` store, and the browser/computer session logs — composing
over the existing Phase 6 evaluation surface rather than duplicating it. All
queries are company-scoped and honour an optional ``window_days`` cutoff.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select as sa_select
from sqlalchemy.orm import Session

from app.company.events import OrgEventLogger
from app.db.models.external import (
    BrowserAction,
    BrowserObservation,
    BrowserSession,
    ComputerAction,
    ComputerObservation,
    ComputerSession,
    ExternalAction,
    ExternalActionAttempt,
    ExternalEvent,
    ExternalEventSource,
    VerificationStatusExternal,
)
from app.external.events import ExternalEvents

_FAILED_STATUSES = {"failed", "blocked"}
_APPROVAL_STATUSES = {"required", "pending", "approved", "rejected"}


def _nearest_rank_percentiles(values: list[float], *percentiles: float) -> list[float]:
    """Nearest-rank percentiles over a sorted sample (mirrors conventional p50/p95/p99)."""
    if not values:
        return [0.0 for _ in percentiles]
    ordered = sorted(values)
    out: list[float] = []
    n = len(ordered)
    for p in percentiles:
        rank = max(1, int(__import__("math").ceil(p * n)))
        out.append(ordered[min(rank, n) - 1])
    return out


def _window_cutoff(window_days: int | None) -> datetime | None:
    if not window_days:
        return None
    return datetime.now(UTC) - timedelta(days=window_days)


def _filter_cutoff(stmt, column, cutoff: datetime | None):
    if cutoff is not None:
        stmt = stmt.where(column >= cutoff)
    return stmt


def _count(db: Session, model, *, company_id: UUID, cutoff: datetime | None, col) -> int:
    stmt = sa_select(model).where(model.company_id == company_id)
    stmt = _filter_cutoff(stmt, col, cutoff)
    return len(list(db.execute(stmt).scalars().all()))


def _verification_verified(action: ExternalAction) -> bool:
    if not action.verification:
        return False
    try:
        data = json.loads(action.verification)
    except (ValueError, TypeError):
        return False
    return bool(data.get("verified"))


def compute_external_metrics(
    db: Session, company_id: UUID, *, window_days: int | None = None
) -> dict[str, Any]:
    """Compute the per-company external-layer metrics snapshot (§61).

    Rates use ``max(1, denominator)`` so an empty window reports 0.0 rather
    than dividing by zero. Durations are measured from ``started_at`` →
    ``completed_at`` for journaled actions that actually executed.
    """
    cutoff = _window_cutoff(window_days)

    # ── External actions journal ────────────────────────────────────────
    stmt = sa_select(ExternalAction).where(ExternalAction.company_id == company_id)
    stmt = _filter_cutoff(stmt, ExternalAction.created_at, cutoff)
    actions = list(db.execute(stmt).scalars().all())

    total_actions = len(actions)
    succeeded = [a for a in actions if a.status.value == "succeeded"]
    failed = [a for a in actions if a.status.value in _FAILED_STATUSES]
    verified = [a for a in actions if _verification_verified(a)]
    requiring_approval = [a for a in actions if a.approval_status.value in _APPROVAL_STATUSES]

    # Recovery: attempts that were retried (>1) and ultimately succeeded.
    # A first-try success journals attempt_number == 1, so only multi-attempt
    # successes count as "recovered" (distinct from the plain success rate).
    recovered = 0
    if actions:
        action_ids = [a.id for a in actions]
        attempts = list(
            db.execute(
                sa_select(ExternalActionAttempt).where(
                    ExternalActionAttempt.action_id.in_(action_ids),
                    ExternalActionAttempt.status == "succeeded",
                )
            )
            .scalars()
            .all()
        )
        recovered = sum(1 for a in attempts if (a.attempt_number or 1) > 1)

    # Duplicate blocks are journaled as org events (duplicates persist no action row).
    blocked_duplicates = len(
        OrgEventLogger(db).query(
            company_id=company_id, action=ExternalEvents.EXTERNAL_ACTION_DUPLICATE_BLOCKED
        )
    )

    # Durations for actions that actually executed.
    durations: list[float] = []
    for a in actions:
        if a.started_at and a.completed_at:
            durations.append((a.completed_at - a.started_at).total_seconds() * 1000.0)
    p50, p95, p99 = _nearest_rank_percentiles(durations, 0.50, 0.95, 0.99)

    # ── Browser / computer sessions ─────────────────────────────────────
    browser_sessions = _count(
        db, BrowserSession, company_id=company_id, cutoff=cutoff, col=BrowserSession.created_at
    )
    browser_actions = _count(
        db, BrowserAction, company_id=company_id, cutoff=cutoff, col=BrowserAction.created_at
    )
    browser_observations = _count(
        db,
        BrowserObservation,
        company_id=company_id,
        cutoff=cutoff,
        col=BrowserObservation.created_at,
    )
    computer_sessions = _count(
        db, ComputerSession, company_id=company_id, cutoff=cutoff, col=ComputerSession.created_at
    )
    computer_actions = _count(
        db, ComputerAction, company_id=company_id, cutoff=cutoff, col=ComputerAction.created_at
    )
    computer_observations = _count(
        db,
        ComputerObservation,
        company_id=company_id,
        cutoff=cutoff,
        col=ComputerObservation.created_at,
    )

    # ── External events ─────────────────────────────────────────────────
    events_stmt = sa_select(ExternalEvent).where(ExternalEvent.company_id == company_id)
    events_stmt = _filter_cutoff(events_stmt, ExternalEvent.received_at, cutoff)
    events = list(db.execute(events_stmt).scalars().all())
    external_events_count = len(events)
    webhook_events_verified = len(
        [
            e
            for e in events
            if e.source == ExternalEventSource.WEBHOOK
            and e.verification_status == VerificationStatusExternal.VERIFIED
        ]
    )

    denom = max(1, total_actions)
    return {
        "success_rate": len(succeeded) / denom,
        "total_actions": total_actions,
        "succeeded_count": len(succeeded),
        "failed_count": len(failed),
        "verification_rate": len(verified) / denom,
        "verified_count": len(verified),
        "recovery_rate": recovered / denom,
        "recovered_count": recovered,
        "duplicate_rate": blocked_duplicates / denom,
        "blocked_duplicate_count": blocked_duplicates,
        "intervention_rate": len(requiring_approval) / denom,
        "actions_requiring_approval": len(requiring_approval),
        "duration_p50_ms": p50,
        "duration_p95_ms": p95,
        "duration_p99_ms": p99,
        "browser_sessions_count": browser_sessions,
        "browser_actions_count": browser_actions,
        "browser_observations_count": browser_observations,
        "computer_sessions_count": computer_sessions,
        "computer_actions_count": computer_actions,
        "computer_observations_count": computer_observations,
        "external_events_count": external_events_count,
        "webhook_events_verified": webhook_events_verified,
    }
