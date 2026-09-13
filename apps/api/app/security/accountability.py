"""Append-only, hash-chained audit (Phase 11, §46/§47).

Every meaningful autonomous action is recorded in ``audit_events``. Each row
carries ``prev_hash`` (hash of the previous row) and ``hash`` (SHA-256 of its
own serialized content), so the chain is tamper-evident: recomputing hashes
and comparing ``prev_hash[i] == hash[i-1]`` detects insertion / deletion /
modification. There is deliberately **no UPDATE/DELETE path** — the service
only inserts.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models.security import AuditEvent, AuditOutcome

logger = get_logger(__name__)

ZERO_HASH = "0" * 64


def _stable_json(value) -> str:
    return json.dumps(value or {}, sort_keys=True, default=str)


class AuditService:
    """Record + verify the audit chain. Insert-only by design."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        action: str,
        *,
        actor_id: UUID | None = None,
        actor_type: str | None = None,
        actor_name: str | None = None,
        company_id: UUID | None = None,
        category: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        outcome: str = "success",
        detail: dict | None = None,
        before: dict | None = None,
        after: dict | None = None,
        policy_result: str | None = None,
        approval_ref: str | None = None,
        correlation_id: str | None = None,
        ip_address: str | None = None,
        commit: bool = True,
    ) -> AuditEvent:
        """Append one event to the chain; returns the created row."""
        prev = self._last()
        prev_hash = prev.hash if prev is not None else ZERO_HASH
        seq = (prev.seq if prev is not None else 0) + 1
        now = datetime.now(UTC)
        content = {
            "seq": seq,
            "action": action,
            "actor_id": str(actor_id) if actor_id else None,
            "actor_type": actor_type,
            "actor_name": actor_name,
            "company_id": str(company_id) if company_id else None,
            "category": category,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "outcome": _validate_outcome(outcome),
            "detail": _stable_json(detail),
            "before": _stable_json(before),
            "after": _stable_json(after),
            "policy_result": policy_result,
            "approval_ref": approval_ref,
            "correlation_id": correlation_id,
            "ip_address": ip_address,
            "created_at": now.replace(tzinfo=None).isoformat(),
        }
        event = AuditEvent(
            seq=seq,
            prev_hash=prev_hash,
            hash=_row_hash(prev_hash, content),
            action=action,
            actor_id=actor_id,
            actor_type=actor_type,
            actor_name=actor_name,
            company_id=company_id,
            category=category,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=content["outcome"],
            detail=detail,
            before_json=before,
            after_json=after,
            policy_result=policy_result,
            approval_ref=approval_ref,
            correlation_id=correlation_id,
            ip_address=ip_address,
            created_at=now,
        )
        self.db.add(event)
        self.db.flush()
        self._mirror_to_ops(company_id, action, actor_id, resource_type, resource_id, detail)
        if commit:
            self.db.commit()
        return event

    def verify_chain(self) -> tuple[bool, int, UUID | None]:
        """Recompute and compare the whole chain.

        Returns ``(valid, checked_count, first_broken_event_id)`` where the
        id is ``None`` when the entire chain verifies.
        """
        rows = list(
            self.db.execute(
                select(AuditEvent).order_by(AuditEvent.seq.asc(), AuditEvent.created_at.asc())
            )
            .scalars()
            .all()
        )
        expected_prev = ZERO_HASH
        for idx, row in enumerate(rows):
            content = {
                "seq": row.seq,
                "action": row.action,
                "actor_id": str(row.actor_id) if row.actor_id else None,
                "actor_type": row.actor_type,
                "actor_name": row.actor_name,
                "company_id": str(row.company_id) if row.company_id else None,
                "category": row.category,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "outcome": row.outcome,
                "detail": _stable_json(row.detail),
                "before": _stable_json(row.before_json),
                "after": _stable_json(row.after_json),
                "policy_result": row.policy_result,
                "approval_ref": row.approval_ref,
                "correlation_id": row.correlation_id,
                "ip_address": row.ip_address,
                "created_at": (
                    row.created_at.replace(tzinfo=None).isoformat() if row.created_at else ""
                ),
            }
            if row.prev_hash != expected_prev:
                return False, idx, row.id
            if row.hash != _row_hash(expected_prev, content):
                return False, idx + 1, row.id
            expected_prev = row.hash
        return True, len(rows), None

    def latest_seq(self) -> int:
        stmt = select(func.max(AuditEvent.seq))
        value = self.db.execute(stmt).scalar()
        return int(value or 0)

    def _last(self) -> AuditEvent | None:
        stmt = (
            select(AuditEvent)
            .order_by(AuditEvent.seq.desc(), AuditEvent.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _mirror_to_ops(
        self, company_id, action, actor_id, resource_type, resource_id, detail
    ) -> None:
        """Mirror to the Phase 8 OrgEventLogger so ops/GUI views stay in sync."""
        try:
            from app.company.events import OrgEventLogger

            OrgEventLogger(self.db).log(
                company_id=company_id,
                event_type=action,
                actor_id=actor_id,
                detail={
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    **(detail or {}),
                },
            )
        except Exception:  # pragma: no cover
            logger.debug("OrgEvent mirror skipped for audit event %s", action)


def _row_hash(prev_hash: str, content: dict) -> str:
    payload = {"prev_hash": prev_hash, "content": content}
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _validate_outcome(outcome: str) -> str:
    if outcome not in {o.value for o in AuditOutcome}:
        return AuditOutcome.INFO.value if outcome == "info" else AuditOutcome.SUCCESS.value
    return outcome
