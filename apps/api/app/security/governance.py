"""Governance: kill switch (system flags) + governance guard (Phase 11, §61–§63).

The kill switch is a ``system_flags`` row scoped GLOBAL / COMPANY / EMPLOYEE /
AGENT / EXTERNAL / WORKFLOW. A pause flips the matching ``*_paused`` flag to
ACTIVE; the :class:`GovernanceGuard` is consulted at every entry point
(external action manager, workflow engine, orchestrator, agent runtime,
browser/computer session create) and raises :class:`GovernancePausedError`
when the relevant scope is paused. Pauses are idempotent, audited, and carry
a reason + set_by. Global pause is the emergency brake.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import PermissionDeniedError
from app.core.logging import get_logger
from app.db.models.security import (
    SystemFlag,
    SystemFlagScope,
    SystemFlagStatus,
)

logger = get_logger(__name__)

# scope → flag name toggled by a pause of that scope
_SCOPE_FLAG: dict[str, str] = {
    SystemFlagScope.GLOBAL.value: "autonomy_paused",
    SystemFlagScope.COMPANY.value: "company_paused",
    SystemFlagScope.EMPLOYEE.value: "employee_paused",
    SystemFlagScope.AGENT.value: "agent_paused",
    SystemFlagScope.EXTERNAL.value: "external_paused",
    SystemFlagScope.WORKFLOW.value: "workflow_paused",
}


class GovernancePausedError(PermissionDeniedError):
    """Raised when a governance guard blocks an action (scope paused)."""


def governance_flag_for_scope(scope: str) -> str:
    """Return the flag name associated with a scope (validated)."""
    if scope not in _SCOPE_FLAG:
        raise ValueError(f"Unknown governance scope {scope!r}.")
    return _SCOPE_FLAG[scope]


class KillSwitchService:
    """Manage pause/resume flags per scope (idempotent, audited)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def scope_exists(scope: str) -> bool:
        return scope in _SCOPE_FLAG

    def pause(
        self,
        scope: str,
        reason: str,
        set_by: UUID | None = None,
        tenant_id: UUID | None = None,
    ) -> SystemFlag:
        """Pause a scope. Idempotent: re-pausing returns the existing flag."""
        flag_name = governance_flag_for_scope(scope)
        existing = self._active(scope, tenant_id, flag_name)
        if existing is not None:
            return existing
        flag = SystemFlag(
            scope=scope,
            tenant_id=tenant_id,
            flag=flag_name,
            status=SystemFlagStatus.ACTIVE.value,
            reason=reason,
            set_by=set_by,
        )
        self.db.add(flag)
        self.db.flush()
        self._audit("governance.pause", scope, tenant_id, flag, reason, set_by)
        logger.warning(
            "Governance scope paused",
            extra={"scope": scope, "tenant_id": str(tenant_id), "reason": reason},
        )
        return flag

    def resume(
        self, scope: str, by: UUID | None = None, tenant_id: UUID | None = None
    ) -> SystemFlag | None:
        """Clear the pause for a scope (if active)."""
        flag_name = governance_flag_for_scope(scope)
        flag = self._active(scope, tenant_id, flag_name)
        if flag is None:
            return None
        flag.status = SystemFlagStatus.CLEARED.value
        flag.cleared_at = datetime.now(UTC)
        flag.cleared_by = by
        self.db.flush()
        self._audit("governance.resume", scope, tenant_id, flag, "resumed", by)
        logger.info("Governance scope resumed", extra={"scope": scope})
        return flag

    def is_paused(self, scope: str, *, tenant_id: UUID | None = None) -> bool:
        """True if a scope (or its parent) is currently paused."""
        flag_name = governance_flag_for_scope(scope)
        return self._active(scope, tenant_id, flag_name) is not None

    def scope_status(self) -> list[dict]:
        """Snapshot of every active flag (for the governance API/dashboard)."""
        stmt = select(SystemFlag).where(SystemFlag.status == SystemFlagStatus.ACTIVE.value)
        rows = [
            {
                "scope": f.scope,
                "flag": f.flag,
                "tenant_id": str(f.tenant_id) if f.tenant_id else None,
                "reason": f.reason,
                "set_by": str(f.set_by) if f.set_by else None,
                "set_at": f.set_at.isoformat(),
            }
            for f in self.db.execute(stmt).scalars().all()
        ]
        return rows

    # External action / workflow / agent entry checks ----------------------

    def guard(
        self,
        scope: str,
        *,
        tenant_id: UUID | None = None,
    ) -> None:
        """Raise :class:`GovernancePausedError` if the scope is paused."""
        if self.is_paused(scope, tenant_id=tenant_id):
            raise GovernancePausedError(
                f"{scope} scope is paused by governance.",
                code="governance_paused",
            )

    def _active(self, scope: str, tenant_id: UUID | None, flag_name: str) -> SystemFlag | None:
        stmt = select(SystemFlag).where(
            SystemFlag.scope == scope,
            SystemFlag.status == SystemFlagStatus.ACTIVE.value,
            SystemFlag.flag == flag_name,
        )
        if tenant_id is not None:
            stmt = stmt.where(SystemFlag.tenant_id == tenant_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def _audit(
        self, action: str, scope: str, tenant_id: UUID | None, flag, reason: str, actor: UUID | None
    ) -> None:
        """Record the pause/resume in the append-only audit chain (best-effort)."""
        try:
            from app.security.accountability import AuditService

            AuditService(self.db).record(
                actor_id=actor,
                company_id=tenant_id,
                action=action,
                resource_type="system_flags",
                resource_id=str(flag.id),
                outcome="success",
                detail={
                    "scope": scope,
                    "flag": flag.flag,
                    "reason": reason,
                    "status": flag.status,
                },
                commit=False,
            )
        except Exception:  # pragma: no cover - audit must never block governance
            logger.exception("Audit failed during governance change")


class GovernanceGuard:
    """Composable guard used at runtime entry points (workflows, agents, tools)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def allowed(self, scope: str, *, tenant_id: UUID | None = None) -> bool:
        service = KillSwitchService(self.db)
        if service.is_paused(SystemFlagScope.GLOBAL.value):
            return False
        return not service.is_paused(scope, tenant_id=tenant_id)

    def require(self, scope: str, *, tenant_id: UUID | None = None) -> None:
        """Raise if the scope or its global parent is paused."""
        if not self.allowed(scope, tenant_id=tenant_id):
            raise GovernancePausedError(
                f"{scope} scope is paused by governance.",
                code="governance_paused",
            )
