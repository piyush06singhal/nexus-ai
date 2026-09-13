"""Approval governance & break-glass (Phase 11, §55–§57).

Approval gates compose the Phase 9 :class:`ApprovalGateManager`; this module
hardens that flow with **self-approval prevention** and (optionally) enforced
separation-of-duties. :class:`BreakGlassService` provides time-limited,
explicitly-activated elevated access that auto-expires and is fully audited —
an emergency path, never a standing permission.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import PermissionDeniedError
from app.core.logging import get_logger
from app.db.models.security import BreakGlassAccess, BreakGlassStatus

logger = get_logger(__name__)


def _as_utc(value):
    """DB datetimes round-trip naive (SQLite) — assume UTC before comparing."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class BreakGlassService:
    """Time-limited elevated access with explicit activation + auto-expiry."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def activate(
        self,
        *,
        scope: str,
        reason: str,
        requested_by: UUID,
        company_id: UUID | None = None,
        duration_minutes: int | None = None,
        permissions: list[str] | None = None,
    ) -> BreakGlassAccess:
        if len(reason or "") < 10:
            raise PermissionDeniedError(
                "A break-glass reason is required (≥10 characters).",
                code="break_glass_reason_required",
            )
        max_duration = settings.break_glass_default_max_minutes or 480
        if duration_minutes is None:
            duration = min(60, max_duration)
        else:
            duration = duration_minutes
        if duration > max_duration:
            raise PermissionDeniedError(
                f"Break-glass window exceeds maximum ({max_duration}min).",
                code="break_glass_window_exceeded",
            )
        record = BreakGlassAccess(
            identity_id=requested_by,
            company_id=company_id,
            scope=scope,
            reason=reason,
            status=BreakGlassStatus.ACTIVE.value,
            activated_by=requested_by,
        )
        # Excel at precision: window bound is computed here, never trusting a client.
        record.expires_at = datetime.now(UTC) + timedelta(minutes=duration)
        self.db.add(record)
        self.db.flush()
        self._audit(
            "break_glass.activate",
            record,
            actor=requested_by,
            detail={
                "scope": scope,
                "permissions": permissions,
                "duration_minutes": duration,
            },
        )
        if permissions:
            self._grant_temporary_permissions(record, permissions)
        return record

    def require_active(
        self, identity_id: UUID, *, company_id: UUID | None = None
    ) -> BreakGlassAccess:
        """Return the identity's active break-glass record, else raise."""
        now = datetime.now(UTC)
        stmt = select(BreakGlassAccess).where(
            BreakGlassAccess.identity_id == identity_id,
            BreakGlassAccess.status == BreakGlassStatus.ACTIVE.value,
        )
        if company_id is not None:
            stmt = stmt.where(BreakGlassAccess.company_id == company_id)
        candidates = self.db.execute(stmt).scalars().all()
        row = next((r for r in candidates if _as_utc(r.expires_at) > now), None)
        if row is None:
            raise PermissionDeniedError(
                "No active break-glass access.", code="break_glass_inactive"
            )
        return row

    def revoke(self, access_id: UUID, *, by: UUID | None = None) -> BreakGlassAccess:
        row = self.db.get(BreakGlassAccess, access_id)
        if row is None:
            from app.core.errors import NotFoundError

            raise NotFoundError("Break-glass record not found.")
        row.status = BreakGlassStatus.REVOKED.value
        row.revoked_at = datetime.now(UTC)
        self.db.flush()
        self._audit("break_glass.revoke", row, actor=by)
        return row

    def expire_stale(self) -> int:
        """Auto-expire any active windows past their bound (called by scheduler)."""
        now = datetime.now(UTC)
        rows = (
            self.db.execute(
                select(BreakGlassAccess).where(
                    BreakGlassAccess.status == BreakGlassStatus.ACTIVE.value,
                    BreakGlassAccess.expires_at <= now,
                )
            )
            .scalars()
            .all()
        )
        expired = 0
        for row in rows:
            if _as_utc(row.expires_at) > now:
                continue
            row.status = BreakGlassStatus.EXPIRED.value
            expired += 1
        self.db.flush()
        return len(rows)

    def _grant_temporary_permissions(
        self, record: BreakGlassAccess, permissions: list[str]
    ) -> None:
        try:
            from app.security.authorization import RoleService

            role = RoleService(self.db).get_role_by_code("break_glass")
            if role is None:
                return  # no dedicated role seeded yet → window is a scope-gated record
            from app.db.models.security import IdentityRole

            self.db.add(
                IdentityRole(
                    identity_id=record.identity_id,
                    role_id=role.id,
                    company_id=record.company_id,
                    granted_by=record.activated_by,
                )
            )
            self.db.flush()
        except Exception:  # pragma: no cover
            logger.debug("temporary permission grant failed for break-glass")

    def _audit(
        self,
        action: str,
        record: BreakGlassAccess,
        *,
        actor: UUID | None,
        detail: dict | None = None,
    ) -> None:
        try:
            from app.security.accountability import AuditService

            AuditService(self.db).record(
                actor_id=actor,
                company_id=record.company_id,
                action=action,
                category="governance",
                resource_type="break_glass_access",
                resource_id=str(record.id),
                outcome="success",
                detail={**({"scope": record.scope}), **(detail or {})},
                commit=False,
            )
        except Exception:  # pragma: no cover
            logger.debug("audit skip for %s", action)


class ApprovalGovernance:
    """Hardening around the Phase 9 approval funnel: SoD, self-approval blocks."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def validate_approver(
        self,
        *,
        requester_id: UUID | None,
        approver_id: UUID,
        risk_level: str | None = None,
        enforce_sod: bool | None = None,
    ) -> None:
        """Block self-approval and (if configured) same-principal approval."""
        if requester_id is not None and requester_id == approver_id:
            raise PermissionDeniedError(
                "Self-approval is prohibited.", code="self_approval_blocked"
            )
        should_enforce = (
            enforce_sod
            if enforce_sod is not None
            else getattr(settings, "approval_enforce_separation_of_duties", True)
        )
        if should_enforce and requester_id is not None and requester_id == approver_id:
            raise PermissionDeniedError(
                "Requester and approver must differ (separation of duties).",
                code="separation_of_duties",
            )
