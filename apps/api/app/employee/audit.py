"""AI Employee OS — audit logging.

Records every important employee operation (created, activated, task assigned,
tool used, permission denied, budget exceeded, terminated, etc.) with actor,
employee, action, target, timestamp, correlation_id, and outcome.

Audit logs are **append-only**; there is no update or delete API.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.employee import EmployeeAuditLog


class AuditLogger:
    """Append-only audit trail for AI employee operations."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def log(
        self,
        *,
        actor: str = "system",
        action: str,
        employee_id: UUID | None = None,
        target_type: str | None = None,
        target_id: UUID | None = None,
        details: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        outcome: str | None = None,
    ) -> EmployeeAuditLog:
        """Append an audit event.  Returns the persisted ``EmployeeAuditLog`` row."""
        if not settings.employee_audit_enabled:
            # Still return a transient object for callers that need it, but
            # don't hit the database.
            entry = EmployeeAuditLog(
                employee_id=employee_id,
                actor=actor,
                action=action,
                target_type=target_type,
                target_id=target_id,
                details=json.dumps(details) if details else None,
                correlation_id=correlation_id,
                outcome=outcome,
            )
            return entry

        entry = EmployeeAuditLog(
            employee_id=employee_id,
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=json.dumps(details) if details else None,
            correlation_id=correlation_id,
            outcome=outcome,
        )
        self._db.add(entry)
        # Don't flush here — let the caller commit within their own transaction.
        return entry

    def query(
        self,
        *,
        employee_id: UUID | None = None,
        action: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EmployeeAuditLog]:
        """Query audit log entries with optional filters."""
        stmt = select(EmployeeAuditLog).order_by(EmployeeAuditLog.created_at.desc())
        if employee_id is not None:
            stmt = stmt.where(EmployeeAuditLog.employee_id == employee_id)
        if action is not None:
            stmt = stmt.where(EmployeeAuditLog.action == action)
        stmt = stmt.limit(limit).offset(offset)
        return list(self._db.execute(stmt).scalars().all())
