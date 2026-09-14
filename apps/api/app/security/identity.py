"""Identity & user management (Phase 11).

``IdentityManager`` unifies all principals (§3) — humans, services, AI
employees, agents and companies — in one ``identities`` table with a kind,
status, owner and company scope. ``UserAccountManager`` adds the human-login
facade (``users`` table): PBKDF2-hashed passwords, failed-login lockout, safe
bootstrap of a dev admin. No plaintext password is ever stored or logged.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.core.logging import get_logger
from app.db.models.security import (
    Identity,
    IdentityKind,
    IdentityRole,
    IdentityStatus,
    Role,
    UserAccount,
    UserStatus,
)
from app.security.crypto import hash_password, verify_password

logger = get_logger(__name__)


def _as_utc(value) -> datetime:
    """DB datetimes round-trip naive (SQLite) — assume UTC before comparing."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class IdentityManager:
    """CRUD + lifecycle for unified principals."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        kind: IdentityKind,
        name: str,
        company_id: UUID | None = None,
        owner_id: UUID | None = None,
        company_scope_all: bool = False,
        external_ref: str | None = None,
        metadata_json: dict | None = None,
    ) -> Identity:
        """Create a new principal. Kind defaults to the str value of the enum."""
        existing = None
        if external_ref:
            existing = self.db.execute(
                select(Identity).where(Identity.external_ref == external_ref)
            ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(f"An identity for {external_ref!r} already exists.")
        identity = Identity(
            kind=str(kind.value),
            name=name,
            company_id=company_id,
            owner_id=owner_id,
            company_scope_all=company_scope_all,
            external_ref=external_ref,
            metadata_json=metadata_json,
        )
        self.db.add(identity)
        self.db.flush()
        return identity

    def get(self, identity_id: UUID) -> Identity:
        obj = self.db.get(Identity, identity_id)
        if obj is None:
            raise NotFoundError("Identity not found.")
        return obj

    def get_optional(self, identity_id: UUID) -> Identity | None:
        return self.db.get(Identity, identity_id)

    def get_by_ref(self, external_ref: str) -> Identity | None:
        return self.db.execute(
            select(Identity).where(Identity.external_ref == external_ref)
        ).scalar_one_or_none()

    def set_status(self, identity_id: UUID, status: IdentityStatus) -> Identity:
        obj = self.get(identity_id)
        obj.status = status.value
        self.db.flush()
        return obj

    def activate(self, identity_id: UUID) -> Identity:
        return self.set_status(identity_id, IdentityStatus.ACTIVE)

    def suspend(self, identity_id: UUID) -> Identity:
        return self.set_status(identity_id, IdentityStatus.SUSPENDED)

    def revoke(self, identity_id: UUID) -> Identity:
        return self.set_status(identity_id, IdentityStatus.REVOKED)

    def require_active(self, identity_id: UUID) -> Identity:
        """Raise if the principal is not ACTIVE (used by the authz chain)."""
        obj = self.get(identity_id)
        if obj.status != IdentityStatus.ACTIVE.value:
            raise PermissionDeniedError(
                f"Identity is {obj.status}, not active.",
                code="identity_inactive",
            )
        return obj

    def touch_last_active(self, identity_id: UUID) -> None:
        obj = self.db.get(Identity, identity_id)
        if obj is not None:
            obj.last_active = datetime.now(UTC)
            self.db.flush()


class UserAccountManager:
    """Human login records: creation, verification with lockout, bootstrap."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._identity = IdentityManager(db)

    def create_user(
        self,
        *,
        email: str,
        display_name: str,
        password: str | None,
        company_id: UUID | None = None,
        roles: list[str] | None = None,
        is_bootstrap: bool = False,
    ) -> tuple[Identity, UserAccount]:
        """Create an identity + user with a PBKDF2-hashed password."""
        email = email.strip().lower()
        if self.get_by_email(email) is not None:
            raise ConflictError("A user with that email already exists.")
        password_hash: str | None = None
        password_salt: str | None = None
        if password:
            password_hash, password_salt = hash_password(password)
        identity = self._identity.create(
            kind=IdentityKind.USER,
            name=display_name,
            company_id=company_id,
            external_ref=f"user:{email}",
        )
        user = UserAccount(
            identity_id=identity.id,
            email=email,
            display_name=display_name,
            password_hash=password_hash,
            password_salt=password_salt,
            status=UserStatus.ACTIVE.value,
            is_bootstrap=is_bootstrap,
        )
        self.db.add(user)
        self.db.flush()
        return identity, user

    def get_by_email(self, email: str) -> UserAccount | None:
        return self.db.execute(
            select(UserAccount).where(UserAccount.email == email.strip().lower())
        ).scalar_one_or_none()

    def get(self, user_id: UUID) -> UserAccount:
        obj = self.db.get(UserAccount, user_id)
        if obj is None:
            raise NotFoundError("User not found.")
        return obj

    def verify_login(
        self, email: str, password: str, *, require_password: bool = True
    ) -> tuple[UserAccount, Identity] | None:
        """Verify credentials. Returns ``(user, identity)`` or ``None``.

        Lockout: after ``max_failed_login_attempts`` consecutive failures the
        account is locked for ``login_lockout_seconds``. Callers must reset the
        counter on success (via :meth:`mark_success`).
        """
        user = self.get_by_email(email)
        if user is None:
            raise PermissionDeniedError("Invalid credentials.", code="invalid_credentials")
        if user.status == UserStatus.DISABLED.value:
            raise PermissionDeniedError("Account is disabled.", code="account_disabled")
        locked_until = _as_utc(user.locked_until)
        if locked_until is not None and locked_until > datetime.now(UTC):
            raise PermissionDeniedError(
                "Account temporarily locked. Try again later.",
                code="account_locked",
            )
        if not user.password_hash or not user.password_salt:
            if require_password:
                raise PermissionDeniedError(
                    "This account has no password.", code="invalid_credentials"
                )
            ok = True
        else:
            ok = verify_password(password, user.password_hash, user.password_salt)
        if not ok:
            user.failed_login_count = (user.failed_login_count or 0) + 1
            if user.failed_login_count >= settings.max_failed_login_attempts:
                user.locked_until = datetime.now(UTC) + timedelta(
                    seconds=settings.login_lockout_seconds
                )
                user.status = UserStatus.LOCKED.value
            self.db.flush()
            return None
        return user, self._identity.get(user.identity_id)

    def mark_success(self, user: UserAccount) -> None:
        """Reset failure counter, clear lock, stamp last login."""
        user.failed_login_count = 0
        user.locked_until = None
        if user.status == UserStatus.LOCKED.value:
            user.status = UserStatus.ACTIVE.value
        user.last_login_at = datetime.now(UTC)
        self.db.flush()

    def record_failure(self, user: UserAccount) -> None:
        """Persist a login failure (used when creation of session fails)."""
        user.failed_login_count = (user.failed_login_count or 0) + 1
        self.db.flush()

    def bootstrap_admin(self) -> tuple[Identity, UserAccount] | None:
        """Create the configured dev/bootstrap admin if none exists.

        Only meaningful outside production; production deployments must not set
        ``auth_dev_bootstrap_*`` (production_readiness checks this).
        """
        if not settings.auth_dev_bootstrap_email or not settings.auth_dev_bootstrap_password:
            return None
        existing = self.get_by_email(settings.auth_dev_bootstrap_email)
        if existing is not None or not settings.auth_dev_bootstrap_if_no_admin:
            return None
        # Only bootstrap when no admin at all exists yet.
        from app.security.authorization import ADMIN_ROLE_CODE

        has_admin = self.db.execute(
            select(func.count())
            .select_from(IdentityRole)
            .join(Role, Role.id == IdentityRole.role_id)
            .where(Role.code == ADMIN_ROLE_CODE)
        ).scalar_one()
        if has_admin:
            return None
        identity, user = self.create_user(
            email=settings.auth_dev_bootstrap_email,
            display_name="Bootstrap Admin",
            password=settings.auth_dev_bootstrap_password,
            is_bootstrap=True,
        )
        # The bootstrap admin must actually administer: grant the platform-admin
        # role (wildcard permission), else a fresh deploy has no usable login.
        from app.security.authorization import RoleService

        RoleService(self.db).assign_roles_to_identity(identity.id, [ADMIN_ROLE_CODE])
        logger.warning(
            "security.bootstrap_admin",
            extra={"email": identity.external_ref},
        )
        return identity, user
