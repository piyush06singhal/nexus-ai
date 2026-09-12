"""Startup plan management — create, validate, and approve bootstrap plans.

:class:`StartupPlanManager` owns the startup-plan lifecycle (draft → under
review → approved → bootstrapping/active). Validation is the plan's own
:class:`StartupPlanValidator` (deterministic, advisory with blocking errors);
approval persists a timestamped audit on ``plan.review`` and records the event
so the approval trail is complete. Bootstrap of an approved plan happens through
the separate :class:`CompanyBootstrapper`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.startup import (
    MissionGraphRelation,
    StartupPlan,
    StartupPlanStatus,
)
from app.startup.events import StartupEventLogger, StartupEvents
from app.startup.graph import MissionGraphBuilder
from app.startup.types import ValidationResult
from app.startup.validate import StartupPlanValidator

_JSON_FIELDS = (
    "business_objectives",
    "product_objectives",
    "market_objectives",
    "organization_objectives",
    "operational_objectives",
    "milestones",
    "departments",
    "roles",
    "capabilities",
    "initial_products",
    "initial_projects",
    "kpi_targets",
    "budget_allocation",
    "execution_priorities",
    "approval_requirements",
)


class StartupPlanManager:
    """Create, update, validate, and approve startup plans."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._events = StartupEventLogger(db)

    def create(
        self,
        *,
        mission_id: UUID,
        strategic_plan_id: UUID | None = None,
        status: StartupPlanStatus | str = StartupPlanStatus.DRAFT,
        approved: bool = False,
        actor: str = "api",
        **json_fields: Any,
    ) -> StartupPlan:
        plan = StartupPlan(
            mission_id=mission_id,
            strategic_plan_id=strategic_plan_id,
            status=StartupPlanStatus(status),
        )
        for name in _JSON_FIELDS:
            value = json_fields.get(name)
            if value is None:
                continue
            setattr(plan, name, json.dumps(value, default=str))
        self._db.add(plan)
        self._db.flush()
        MissionGraphBuilder(self._db).link(
            company_id=plan.mission.company_id,
            source_type="startup_plan",
            source_id=plan.id,
            target_type="mission",
            target_id=mission_id,
            relation=MissionGraphRelation.DERIVED_FROM,
        )
        self._db.commit()
        self._events.log(
            action=StartupEvents.STARTUP_PLAN_CREATED,
            company_id=plan.mission.company_id,
            target_type="startup_plan",
            target_id=plan.id,
            details={"mission_id": str(mission_id)},
            outcome="success",
        )
        if approved:
            self.approve(plan, actor=actor)
        return plan

    def get(self, mission_id: UUID, plan_id: UUID) -> StartupPlan | None:
        plan = self._db.get(StartupPlan, plan_id)
        if plan is None or plan.mission_id != mission_id:
            return None
        return plan

    def list_(self, mission_id: UUID) -> list[StartupPlan]:
        stmt = (
            select(StartupPlan)
            .where(StartupPlan.mission_id == mission_id)
            .order_by(StartupPlan.created_at.desc())
        )
        return list(self._db.execute(stmt).scalars().all())

    def update(self, mission_id: UUID, plan_id: UUID, **fields: Any) -> StartupPlan:
        plan = self._require(mission_id, plan_id)
        for key, value in fields.items():
            if value is None or not hasattr(plan, key):
                continue
            if key in _JSON_FIELDS and isinstance(value, (list, dict)):
                setattr(plan, key, json.dumps(value, default=str))
            elif key == "status":
                plan.status = StartupPlanStatus(value)
            else:
                setattr(plan, key, value)
        self._db.commit()
        return plan

    # ── Validate / approve ─────────────────────────────────────────────

    def validate(self, plan: StartupPlan) -> ValidationResult:
        result = StartupPlanValidator(self._db).validate(plan)
        plan.review = json.dumps(result.to_dict(), default=str)
        self._db.commit()
        self._events.log(
            action=StartupEvents.STARTUP_PLAN_VALIDATED,
            company_id=plan.mission.company_id,
            target_type="startup_plan",
            target_id=plan.id,
            details={
                "ok": result.ok,
                "errors": len([i for i in result.issues if i.severity == "error"]),
            },
            outcome="success" if result.ok else "feedback",
        )
        return result

    def approve(
        self,
        plan: StartupPlan,
        *,
        actor: str = "api",
        approved_gate_id: UUID | None = None,
    ) -> StartupPlan:
        """Approve a validated plan, persisting an audit trail.

        The approval is recorded on ``plan.review`` (a timestamped audit) and a
        ``STRATEGY_APPROVAL`` event. Bootstrap then consumes the approved plan.
        """
        latest = self._db.get(StartupPlan, plan.id)
        plan = latest or plan
        if plan.status != StartupPlanStatus.DRAFT:
            raise ValueError(
                f"Startup plan is {plan.status.value}; only draft plans can be approved"
            )
        # Validation advisory: blocking errors are required to be resolved.
        result = StartupPlanValidator(self._db).validate(plan)
        if not result.ok:
            raise ValueError(
                "Startup plan has blocking validation errors; fix them before approval"
            )
        review = _loads_dict(plan.review) or {}
        review.update(
            {
                "approved_at": datetime.now(UTC).isoformat(),
                "approved_by": actor,
                "approved_gate_id": str(approved_gate_id) if approved_gate_id else None,
            }
        )
        plan.review = json.dumps(review, default=str)
        plan.status = StartupPlanStatus.APPROVED
        self._db.commit()
        self._events.log(
            action=StartupEvents.STARTUP_PLAN_APPROVED,
            company_id=plan.mission.company_id,
            target_type="startup_plan",
            target_id=plan.id,
            details={"approved_by": actor},
            outcome="success",
        )
        return plan

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self, plan: StartupPlan) -> dict[str, Any]:
        return {
            "id": str(plan.id),
            "mission_id": str(plan.mission_id),
            "strategic_plan_id": str(plan.strategic_plan_id) if plan.strategic_plan_id else None,
            "company_id": str(plan.mission.company_id),
            "company_name": plan.mission.title,
            **{name: _loads(getattr(plan, name)) for name in _JSON_FIELDS},
            "status": plan.status.value,
            "review": _loads(plan.review),
            "created_at": plan.created_at.isoformat() if plan.created_at else None,
            "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
        }

    def _require(self, mission_id: UUID, plan_id: UUID) -> StartupPlan:
        plan = self.get(mission_id, plan_id)
        if plan is None:
            raise ValueError("Startup plan not found")
        return plan


def _loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _loads_dict(raw: str | None) -> dict[str, Any]:
    value = _loads(raw)
    return value if isinstance(value, dict) else {}
