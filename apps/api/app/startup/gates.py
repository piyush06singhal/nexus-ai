"""Approval gates — the human decision points of the startup engine.

An :class:`ApprovalGate` records that a specific high-impact autonomous action
was *requested*, what it would affect, who approved/rejected it, and when.
Every action that :class:`AutonomyService` classifies as ``require_approval``
must first produce an approved gate; no autonomous path skips this. Approving
an action authorizes exactly that action (via an audit event + the gate row) —
it is never a blanket grant of autonomy.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.startup import ApprovalGate, ApprovalGateStatus, ApprovalGateType
from app.startup.events import StartupEventLogger, StartupEvents

_DEFAULT_EXPIRATION_DAYS = 7


class ApprovalGateManager:
    """Create, resolve, and list human approval gates."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._events = StartupEventLogger(db)

    # ── CRUD ───────────────────────────────────────────────────────────

    def create(
        self,
        *,
        company_id: UUID,
        gate_type: ApprovalGateType | str,
        requested_action: dict[str, Any],
        rationale: str | None = None,
        risk_level: str = "medium",
        affected_entities: list[dict[str, Any]] | None = None,
        resource_impact: dict[str, Any] | None = None,
        requester_id: UUID | None = None,
        expiration: datetime | None = None,
    ) -> ApprovalGate:
        gate = ApprovalGate(
            company_id=company_id,
            gate_type=ApprovalGateType(gate_type),
            risk_level=risk_level,
            requested_action=json.dumps(requested_action, default=str),
            rationale=rationale,
            affected_entities=json.dumps(affected_entities) if affected_entities else None,
            resource_impact=json.dumps(resource_impact) if resource_impact else None,
            requester_id=requester_id,
            status=ApprovalGateStatus.PENDING,
            expiration=expiration or datetime.now() + timedelta(days=_DEFAULT_EXPIRATION_DAYS),
        )
        self._db.add(gate)
        self._db.commit()
        self._events.log(
            action=StartupEvents.APPROVAL_REQUESTED,
            company_id=company_id,
            actor="system",
            target_type="approval_gate",
            target_id=gate.id,
            details={
                "gate_type": gate.gate_type.value,
                "action": requested_action.get("action"),
                "risk_level": risk_level,
            },
            outcome="pending",
        )
        return gate

    def get(self, company_id: UUID, gate_id: UUID) -> ApprovalGate | None:
        gate = self._db.get(ApprovalGate, gate_id)
        if gate is None or gate.company_id != company_id:
            return None
        return gate

    def list_(self, company_id: UUID, *, status: str | None = None) -> list[ApprovalGate]:
        stmt = (
            select(ApprovalGate)
            .where(ApprovalGate.company_id == company_id)
            .order_by(ApprovalGate.created_at.desc())
        )
        if status is not None:
            stmt = stmt.where(ApprovalGate.status == ApprovalGateStatus(status))
        return list(self._db.execute(stmt).scalars().all())

    def pending(self, company_id: UUID) -> list[ApprovalGate]:
        return self.list_(company_id, status=ApprovalGateStatus.PENDING.value)

    # ── Resolve (governed) ─────────────────────────────────────────────

    def _require_gate(self, company_id: UUID, gate_id: UUID) -> ApprovalGate:
        gate = self.get(company_id, gate_id)
        if gate is None:
            raise ValueError("Approval gate not found")
        return gate

    def approve(
        self, company_id: UUID, gate_id: UUID, *, approver_id: UUID | None = None
    ) -> ApprovalGate:
        gate = self._require_gate(company_id, gate_id)
        if gate.status != ApprovalGateStatus.PENDING:
            raise ValueError(
                f"Approval gate is {gate.status.value}; only pending gates can be approved"
            )
        gate.status = ApprovalGateStatus.APPROVED
        gate.approver_id = approver_id
        gate.decided_at = datetime.now()
        self._db.commit()
        self._events.log(
            action=StartupEvents.APPROVAL_GRANTED,
            company_id=company_id,
            actor="system",
            target_type="approval_gate",
            target_id=gate.id,
            details={"gate_type": gate.gate_type.value},
            outcome="success",
        )
        return gate

    def reject(
        self,
        company_id: UUID,
        gate_id: UUID,
        *,
        approver_id: UUID | None = None,
        rationale: str | None = None,
    ) -> ApprovalGate:
        gate = self._require_gate(company_id, gate_id)
        if gate.status != ApprovalGateStatus.PENDING:
            raise ValueError(
                f"Approval gate is {gate.status.value}; only pending gates can be rejected"
            )
        gate.status = ApprovalGateStatus.REJECTED
        gate.approver_id = approver_id
        gate.decided_at = datetime.now()
        if rationale:
            gate.rationale = (gate.rationale or "") + f"\nRejected: {rationale}"
        self._db.commit()
        self._events.log(
            action=StartupEvents.APPROVAL_REJECTED,
            company_id=company_id,
            actor="system",
            target_type="approval_gate",
            target_id=gate.id,
            details={"gate_type": gate.gate_type.value},
            outcome="rejected",
        )
        return gate

    def expire(self, company_id: UUID, gate_id: UUID) -> ApprovalGate:
        gate = self._require_gate(company_id, gate_id)
        if gate.status == ApprovalGateStatus.PENDING:
            gate.status = ApprovalGateStatus.EXPIRED
            gate.decided_at = datetime.now()
        self._db.commit()
        return gate

    def cancel(self, company_id: UUID, gate_id: UUID) -> ApprovalGate:
        gate = self._require_gate(company_id, gate_id)
        if gate.status == ApprovalGateStatus.PENDING:
            gate.status = ApprovalGateStatus.CANCELLED
            gate.decided_at = datetime.now()
        self._db.commit()
        return gate

    # ── Convenience for the engine ─────────────────────────────────────

    def require_approved(
        self,
        company_id: UUID,
        gate_type: ApprovalGateType,
        action: str,
        reason: str,
    ) -> ApprovalGate:
        """Return an approved gate for *action* or raise for one to be created.

        The engine calls this when :class:`AutonomyService` says an action
        needs approval. If a gate for the same action was already approved,
        that authorization is consumed; otherwise the action is surfaced as
        :class:`ApprovalRequiredError` (the API layer creates the gate record).
        """
        stmt = (
            select(ApprovalGate)
            .where(
                ApprovalGate.company_id == company_id,
                ApprovalGate.gate_type == gate_type,
                ApprovalGate.status == ApprovalGateStatus.APPROVED,
            )
            .order_by(ApprovalGate.decided_at.desc())
        )
        stmt = stmt.limit(1)
        gate = self._db.scalar(stmt)
        if gate is not None:
            return gate
        from app.startup.types import ApprovalRequiredError

        raise ApprovalRequiredError(company_id, action, reason, gate_type=gate_type.value)

    def to_dict(self, gate: ApprovalGate) -> dict[str, Any]:
        return {
            "id": str(gate.id),
            "company_id": str(gate.company_id),
            "gate_type": gate.gate_type.value,
            "risk_level": gate.risk_level,
            "requested_action": _loads(gate.requested_action),
            "rationale": gate.rationale,
            "affected_entities": _loads(gate.affected_entities),
            "resource_impact": _loads(gate.resource_impact),
            "requester_id": str(gate.requester_id) if gate.requester_id else None,
            "approver_id": str(gate.approver_id) if gate.approver_id else None,
            "status": gate.status.value,
            "decided_at": gate.decided_at.isoformat() if gate.decided_at else None,
            "expiration": gate.expiration.isoformat() if gate.expiration else None,
            "created_at": gate.created_at.isoformat() if gate.created_at else None,
        }


def _loads(raw: str | None) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
