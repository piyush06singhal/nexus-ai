"""Authentication service (Phase 11).

Wires users → identity → sessions → tokens into the ``login / refresh /
logout / validate`` flows. Session lifecycle SESSION_CREATED/REFRESHED/REVOKED/
EXPIRED is recorded on the session row and mirrored as audit events; failed
logins and invalid tokens flow to security events (AUTH_FAILURE/TOKEN_INVALID).

No secrets cross the wire beyond the short-lived access token.
"""

from __future__ import annotations

import secrets as _secrets
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import PermissionDeniedError
from app.core.logging import get_logger
from app.db.models.security import Identity, IdentityStatus, UserAccount
from app.security.detection import SecurityEventService
from app.security.identity import IdentityManager, UserAccountManager
from app.security.sessions import SessionManager
from app.security.tokens import InvalidToken, TokenService

logger = get_logger(__name__)


@dataclass
class SessionResult:
    """Everything a login/refresh returns (no plaintext refresh token stored)."""

    access_token: str
    refresh_token: str
    session_id: UUID
    identity: Identity
    user: UserAccount | None = None
    company_id: UUID | None = None


class AuthService:
    """High-level authentication flows over Identity/Session/Token services."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.identities = IdentityManager(db)
        self.users = UserAccountManager(db)
        self.sessions = SessionManager(db)
        self.tokens = TokenService()
        self.events = SecurityEventService(db)

    # ── login ──────────────────────────────────────────────────────────────

    def login(
        self,
        email: str,
        password: str,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> SessionResult:
        """Authenticate a human and mint a new session pair."""
        verified = self.users.verify_login(email, password)
        if verified is None:
            self.events.auth_failure(email=email, ip=ip or "", reason="invalid_credentials")
            logger.warning(
                "auth.login_failed",
                extra={"email": email, "ip": ip},
            )
            self._deny(PermissionDeniedError("Invalid credentials.", code="invalid_credentials"))
        user, identity = verified
        if identity.status != IdentityStatus.ACTIVE.value:
            self.events.auth_failure(email=email, ip=ip or "", reason=f"identity_{identity.status}")
            self._deny(PermissionDeniedError("Identity is not active.", code="identity_inactive"))
        self.users.mark_success(user)
        self.identities.touch_last_active(identity.id)
        return self._open_session(identity, ip=ip, user_agent=user_agent, user=user)

    # ── token flows ────────────────────────────────────────────────────────

    def validate_access_token(self, token: str, *, ip: str | None = None) -> Identity:
        """Verify a bearer access token and return the ACTIVE principal."""
        try:
            payload = self.tokens.verify_token(token)
        except InvalidToken as exc:
            self.events.token_invalid(reason=str(exc), ip=ip or "")
            self._deny(
                PermissionDeniedError(
                    "Missing or invalid authentication token.",
                    code="auth_required",
                ),
                from_exc=exc,
            )
        identity_id = UUID(payload["sub"])
        identity = self.identities.get_optional(identity_id)
        if identity is None or identity.status != IdentityStatus.ACTIVE.value:
            raise PermissionDeniedError("Identity is not active.", code="identity_inactive")
        return identity

    def refresh(self, refresh_token: str, *, ip: str | None = None) -> SessionResult:
        """Rotate a refresh token to a new pair. Old token is immediately dead."""
        session = self.sessions.get_by_refresh_token(refresh_token)
        if session is None:
            self.events.token_invalid(reason="unknown_refresh_token", ip=ip or "")
            self._deny(
                PermissionDeniedError("Refresh token is invalid.", code="invalid_credentials")
            )
        try:
            self.sessions.require_active(session)
        except PermissionDeniedError as exc:
            self.events.token_invalid(reason="session_not_active", ip=ip or "")
            self._deny(exc)
        identity = self.identities.get_optional(session.identity_id)
        if identity is None or identity.status != IdentityStatus.ACTIVE.value:
            raise PermissionDeniedError("Identity is not active.", code="identity_inactive")
        new_token = _secrets.token_urlsafe(48)
        replacement = self.sessions.rotate(session, new_token)
        self.sessions.mark_used(replacement)
        self.identities.touch_last_active(identity.id)
        user = self._user_for(identity)
        return self._build_result(identity, replacement, new_token, ip=ip, user=user)

    def logout(self, refresh_token: str) -> None:
        """Revoke the refresh session (and its rotation lineage ends)."""
        session = self.sessions.get_by_refresh_token(refresh_token)
        if session is not None and session.status == "active":
            self.sessions.revoke(session)
            logger.info(
                "auth.logout",
                extra={"identity_id": str(session.identity_id)},
            )

    def revoke_identity_sessions(self, identity_id: UUID, *, by: UUID | None = None) -> int:
        """Revoke every active session of a principal (enable on incident action)."""
        return self.sessions.revoke_all_for_identity(identity_id, by=by)

    def _deny(self, exc: PermissionDeniedError, *, from_exc: BaseException | None = None) -> None:
        """Persist then raise *exc* on an auth failure.

        Failed-auth paths (bad login, invalid token, dead session) return a 4xx
        and the endpoint's success-path ``db.commit()`` never runs — so without
        an explicit commit here the AUTH_FAILURE/TOKEN_INVALID event AND any
        account lock-out set by ``verify_login`` would be silently rolled back,
        defeating audit logging and brute-force lockout over HTTP.
        """
        self.db.commit()
        raise exc from from_exc

    # ── session result helpers ─────────────────────────────────────────────

    def _open_session(
        self,
        identity: Identity,
        *,
        ip: str | None,
        user_agent: str | None,
        user: UserAccount | None = None,
    ) -> SessionResult:
        refresh_token = _secrets.token_urlsafe(48)
        session = self.sessions.create(
            identity_id=identity.id,
            company_id=identity.company_id,
            refresh_token=refresh_token,
            ip_address=ip,
            user_agent=user_agent,
        )
        return self._build_result(identity, session, refresh_token, ip=ip, user=user)

    def _build_result(
        self,
        identity: Identity,
        session,
        refresh_token: str,
        *,
        ip: str | None,
        user: UserAccount | None,
    ) -> SessionResult:
        access = self.tokens.create_access_token(
            identity_id=str(identity.id),
            identity_kind=identity.kind,
            company_id=str(identity.company_id) if identity.company_id else None,
        )
        return SessionResult(
            access_token=access,
            refresh_token=refresh_token,
            session_id=session.id,
            identity=identity,
            user=user,
            company_id=identity.company_id,
        )

    def _user_for(self, identity: Identity) -> UserAccount | None:
        if identity.external_ref and identity.external_ref.startswith("user:"):
            return self.users.get_by_email(identity.external_ref[len("user:") :])
        return None

    # ── service/agent principals (for seeds & RBAC tests) ──────────────────

    def mint_session_for_identity(
        self,
        identity: Identity,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> SessionResult:
        """Create a session + token pair for an existing principal."""
        refresh = _secrets.token_urlsafe(48)
        session = self.sessions.create(
            identity_id=identity.id,
            company_id=identity.company_id,
            refresh_token=refresh,
            ip_address=ip,
            user_agent=user_agent,
        )
        return self._build_result(identity, session, refresh, ip=ip, user=None)

    def create_user_and_session(
        self,
        *,
        email: str,
        display_name: str,
        password: str | None = None,
        roles: list[str] | None = None,
        company_id: UUID | None = None,
        ip: str | None = None,
    ) -> SessionResult:
        """Idempotent convenience for seeds/tests: create user OR reuse existing."""
        existing = self.users.get_by_email(email)
        if existing is not None:
            identity = self.identities.get(existing.identity_id)
        else:
            identity, _ = self.users.create_user(
                email=email,
                display_name=display_name,
                password=password,
                company_id=company_id,
                roles=roles,
            )
        if roles:
            self._ensure_roles(email, identity.id, company_id, roles)
        result = self.mint_session_for_identity(identity, ip=ip)
        result.user = existing or None
        result.company_id = identity.company_id
        return result

    def _ensure_roles(
        self, email: str, identity_id: UUID, company_id: UUID | None, roles: list[str]
    ) -> None:
        from app.security.authorization import RoleService

        RoleService(self.db).assign_roles_to_identity(identity_id, roles, company_id=company_id)
