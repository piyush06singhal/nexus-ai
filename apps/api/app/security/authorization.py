"""Roles, permissions & authorization (Phase 11, §7 chain).

The authorization chain: **identity** (must be ACTIVE) → **company scope**
(cross-company isolation) → **role** → **permission** → ownership → policy →
ALLOW/DENY. Policies are evaluated by the :class:`PolicyEngine` (in
``policy.py``) which the authorization service consults for actions that carry
a policy rule; authorization also composes Phase 11's policy engine so a
DENY/REQUIRE_APPROVAL policy outcome can veto an otherwise-permitted action.

System roles are seeded idempotently (created when missing) — never mutate
user-configured roles.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import PermissionDeniedError
from app.db.models.security import (
    IdentityRole,
    Permission,
    Role,
    RolePermission,
    RoleScope,
)
from app.security.detection import SecurityEventService

ADMIN_ROLE_CODE = "platform_admin"

# ── Permission catalog (action codes) ────────────────────────────────────────

PERMISSION_CATALOG: dict[str, tuple[str, str]] = {
    # (code, description)
    "identity.read": ("Read identities", "identity"),
    "identity.manage": ("Create/suspend/revoke identities", "identity"),
    "users.read": ("Read user accounts", "identity"),
    "users.manage": ("Create/disable user accounts", "identity"),
    "auth.session.manage": ("Revoke sessions", "identity"),
    "roles.read": ("Read roles and grants", "identity"),
    "roles.manage": ("Manage roles and grants", "identity"),
    "secrets.read": ("Read secret references (never values)", "secrets"),
    "secrets.manage": ("Create/rotate/revoke secrets", "secrets"),
    "audit.read": ("Read the audit chain", "accountability"),
    "security.read": ("Read security events/alerts", "detection"),
    "security.manage": ("Acknowledge/resolve alerts", "detection"),
    "incidents.read": ("Read incidents", "incidents"),
    "incidents.manage": ("Create/update incidents", "incidents"),
    "incidents.contain": ("Apply incident containment actions", "incidents"),
    "policy.read": ("Read governance policies", "policy"),
    "policy.manage": ("Create/update policy rules", "policy"),
    "approvals.read": ("Read approval gates", "approvals"),
    "approvals.approve": ("Approve/reject gates", "approvals"),
    "approvals.manage": ("Manage approval governance", "approvals"),
    "governance.read": ("Read governance posture/controls", "governance"),
    "governance.manage": ("Tune governance controls", "governance"),
    "feature_flags.read": ("Read feature flags", "governance"),
    "feature_flags.manage": ("Toggle feature flags", "governance"),
    "resources.read": ("Read resource limits/usage", "resources"),
    "resources.manage": ("Set resource limits", "resources"),
    "retention.manage": ("Manage retention policies", "data_governance"),
    "break_glass.use": ("Activate time-limited break-glass access", "governance"),
    "health.read": ("Read system health", "observability"),
    "metrics.read": ("Read metrics", "observability"),
    "access.manage": ("Manage RBAC grants", "identity"),
}

WILDCARD = "*"  # a role holding this permission code is permitted any action


def permission_codes() -> list[str]:
    return list(PERMISSION_CATALOG)


# ── System role definitions ─────────────────────────────────────────────────

SYSTEM_ROLES: dict[str, tuple[str, list[str]]] = {
    "platform_admin": ("Platform administrator (all access)", [WILDCARD]),
    "company_admin": (
        "Company administrator",
        [
            "identity.read",
            "identity.manage",
            "users.read",
            "users.manage",
            "auth.session.manage",
            "roles.read",
            "roles.manage",
            "secrets.read",
            "secrets.manage",
            "audit.read",
            "security.read",
            "security.manage",
            "incidents.read",
            "incidents.manage",
            "incidents.contain",
            "policy.read",
            "policy.manage",
            "approvals.read",
            "approvals.approve",
            "approvals.manage",
            "governance.read",
            "governance.manage",
            "feature_flags.read",
            "feature_flags.manage",
            "resources.read",
            "resources.manage",
            "retention.manage",
            "health.read",
            "metrics.read",
            "access.manage",
        ],
    ),
    "executive": (
        "Executive (read posture, approve)",
        [
            "identity.read",
            "users.read",
            "roles.read",
            "audit.read",
            "security.read",
            "incidents.read",
            "policy.read",
            "approvals.read",
            "approvals.approve",
            "governance.read",
            "resources.read",
            "health.read",
            "metrics.read",
        ],
    ),
    "manager": (
        "Manager within a company",
        [
            "identity.read",
            "users.read",
            "roles.read",
            "security.read",
            "incidents.read",
            "policy.read",
            "approvals.read",
            "approvals.approve",
            "governance.read",
            "resources.read",
            "health.read",
            "metrics.read",
        ],
    ),
    "employee": (
        "Employee (day-to-day read/use)",
        [
            "identity.read",
            "users.read",
            "approvals.read",
            "policy.read",
            "governance.read",
            "resources.read",
            "health.read",
            "metrics.read",
        ],
    ),
    "analyst": (
        "Analyst (read + metrics)",
        [
            "identity.read",
            "users.read",
            "policy.read",
            "governance.read",
            "resources.read",
            "health.read",
            "metrics.read",
        ],
    ),
    "auditor": (
        "Auditor (read-only accountability)",
        [
            "audit.read",
            "security.read",
            "incidents.read",
            "policy.read",
            "governance.read",
            "identity.read",
            "users.read",
            "health.read",
        ],
    ),
    "read_only": (
        "Read-only",
        [
            "health.read",
            "metrics.read",
            "identity.read",
            "users.read",
            "policy.read",
            "governance.read",
        ],
    ),
}


@dataclass
class AuthorizationDecision:
    allowed: bool
    reason: str
    permission_code: str | None = None
    policy_effect: str | None = None

    @classmethod
    def allow(cls, *, permission_code: str | None = None, policy_effect: str | None = None):
        return cls(
            allowed=True,
            reason="allowed",
            permission_code=permission_code,
            policy_effect=policy_effect,
        )

    @classmethod
    def deny(cls, reason: str, *, permission_code: str | None = None):
        return cls(allowed=False, reason=reason, permission_code=permission_code)


class RoleService:
    """Idempotent system-role/permission seeding and grant management."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def seed_permissions(self) -> None:
        existing = {p.code for p in self.db.execute(select(Permission)).scalars().all()}
        for code, (desc, cat) in PERMISSION_CATALOG.items():
            if code in existing:
                continue
            self.db.add(Permission(code=code, description=desc, category=cat, builtin=True))
        self.db.flush()

    def seed_system_roles(self) -> None:
        """Create system roles + their permission grants if absent (idempotent)."""
        self.seed_permissions()
        permission_map = {p.code: p for p in self.db.execute(select(Permission)).scalars().all()}
        for code, (description, perms) in SYSTEM_ROLES.items():
            role = self.db.execute(
                select(Role).where(Role.code == code, Role.scope == RoleScope.SYSTEM.value)
            ).scalar_one_or_none()
            if role is None:
                role = Role(
                    name=description.split(" (")[0],
                    code=code,
                    scope=RoleScope.SYSTEM.value,
                    description=description,
                    builtin=True,
                )
                self.db.add(role)
                self.db.flush()
            self._ensure_role_permissions(role, perms, permission_map)
        self.db.flush()

    def _ensure_role_permissions(
        self, role: Role, perms: list[str], permission_map: dict[str, Permission]
    ) -> None:
        granted = {
            rp.permission_id: rp
            for rp in self.db.execute(
                select(RolePermission).where(RolePermission.role_id == role.id)
            )
            .scalars()
            .all()
        }
        for code in perms:
            perm = permission_map.get(code)
            if perm is None or perm.id in granted:
                continue
            self.db.add(RolePermission(role_id=role.id, permission_id=perm.id))
        self.db.flush()

    def get_role_by_code(self, code: str, *, scope: str | None = None) -> Role | None:
        stmt = select(Role).where(Role.code == code)
        if scope is not None:
            stmt = stmt.where(Role.scope == scope)
        return self.db.execute(stmt).scalar_one_or_none()

    def assign_roles_to_identity(
        self,
        identity_id: UUID,
        role_codes: list[str],
        *,
        company_id: UUID | None = None,
        granted_by: UUID | None = None,
    ) -> None:
        for code in role_codes:
            role = self.get_role_by_code(code)
            if role is None:
                # Idempotently seed system roles (first assignment in a fresh DB),
                # then retry before declaring the role unknown.
                self.seed_system_roles()
                role = self.get_role_by_code(code)
            if role is None:
                raise PermissionDeniedError(f"Unknown role {code!r}.", code="unknown_role")
            existing = self.db.execute(
                select(IdentityRole).where(
                    IdentityRole.identity_id == identity_id,
                    IdentityRole.role_id == role.id,
                    IdentityRole.company_id == company_id,
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            self.db.add(
                IdentityRole(
                    identity_id=identity_id,
                    role_id=role.id,
                    company_id=company_id,
                    granted_by=granted_by,
                )
            )
        self.db.flush()

    def roles_for_identity(self, identity_id: UUID, *, company_id: UUID | None = None) -> list[str]:
        """Return the codes of every role the identity holds (company-filtered)."""
        stmt = (
            select(Role.code)
            .join(IdentityRole, IdentityRole.role_id == Role.id)
            .where(IdentityRole.identity_id == identity_id)
        )
        if company_id is not None:
            stmt = stmt.where(
                (Role.scope == RoleScope.SYSTEM.value)
                | (Role.company_id == company_id)
                | (IdentityRole.company_id == company_id)
            )
        return [code for (code,) in self.db.execute(stmt).all()]

    def permissions_for_identity(
        self, identity_id: UUID, *, company_id: UUID | None = None
    ) -> set[str]:
        """Union of permission codes across the identity's applicable roles."""
        roles_stmt = (
            select(Role)
            .join(IdentityRole, IdentityRole.role_id == Role.id)
            .where(IdentityRole.identity_id == identity_id)
        )
        roles = list(self.db.execute(roles_stmt).scalars().all())
        codes: set[str] = set()
        for role in roles:
            if role.scope == RoleScope.COMPANY.value and company_id is not None:
                if role.company_id != company_id:
                    continue
            perm_stmt = (
                select(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id == role.id)
            )
            for (code,) in self.db.execute(perm_stmt).all():
                codes.add(code)
        return codes


class AuthorizationService:
    """The §7 authorization chain: ACTIVE → company → role → permission → policy."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.roles = RoleService(db)
        self.events = SecurityEventService(db)

    def authorize(
        self,
        identity_id: UUID,
        action: str,
        *,
        company_id: UUID | None = None,
        resource_type: str | None = None,
        policy_context: dict | None = None,
        record_events: bool = True,
    ) -> AuthorizationDecision:
        from app.security.policy import PolicyEngine

        decision = self._precheck(identity_id, action, record_events)
        if decision is not None:
            return decision
        identity = self._require_active(identity_id)
        # Company isolation (cross-company ⇒ DENY + event)
        if company_id is not None and not identity.company_scope_all:
            if identity.company_id != company_id:
                if record_events:
                    self.events.cross_company(
                        identity_id=identity_id,
                        company_id=identity.company_id,
                        target_company_id=company_id,
                    )
                return AuthorizationDecision.deny(
                    "Cross-company access is not permitted.",
                    permission_code=action,
                )
        # Role → permission
        perms = self.roles.permissions_for_identity(identity_id, company_id=company_id)
        if WILDCARD in perms or action in perms:
            decision = AuthorizationDecision.allow(permission_code=action)
        else:
            if record_events:
                self.events.permission_denied(
                    action=action,
                    identity_id=identity_id,
                    company_id=company_id,
                )
            return AuthorizationDecision.deny(
                "Identity lacks the required permission.",
                permission_code=action,
            )
        # Policy engine (may elevate to REQUIRE_APPROVAL / downgrade to DENY)
        pol = PolicyEngine(self.db).evaluate(
            identity_id=identity_id,
            action=action,
            company_id=company_id,
            resource_type=resource_type,
            context=policy_context or {},
        )
        if pol.decision in ("deny", "require_approval"):
            blocked = AuthorizationDecision.deny(
                f"Policy rule blocked: {pol.reason}", permission_code=action
            )
            blocked.policy_effect = pol.decision
            return blocked
        return decision

    def require(
        self,
        identity_id: UUID,
        action: str,
        *,
        company_id: UUID | None = None,
        resource_type: str | None = None,
        policy_context: dict | None = None,
    ) -> None:
        """Authorize and raise :class:`PermissionDeniedError` on DENY."""
        decision = self.authorize(
            identity_id,
            action,
            company_id=company_id,
            resource_type=resource_type,
            policy_context=policy_context,
        )
        if not decision.allowed:
            raise PermissionDeniedError(decision.reason, code="permission_denied")

    def has_permission(
        self, identity_id: UUID, action: str, *, company_id: UUID | None = None
    ) -> bool:
        decision = self.authorize(identity_id, action, company_id=company_id, record_events=False)
        return decision.allowed

    # ── internals ──────────────────────────────────────────────────────────

    def _precheck(
        self, identity_id: UUID, action: str, record_events: bool
    ) -> AuthorizationDecision | None:
        identity = self._require_active(identity_id)
        if identity.status != "active":
            if record_events:
                self.events.permission_denied(
                    action=action, identity_id=identity_id, detail={"reason": "inactive"}
                )
            return AuthorizationDecision.deny("Identity is not active.")
        return None

    def _require_active(self, identity_id: UUID):
        from app.db.models.security import Identity

        identity = self.db.get(Identity, identity_id)
        if identity is None:
            raise PermissionDeniedError("Identity not found.", code="identity_not_found")
        return identity
