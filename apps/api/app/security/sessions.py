"""Auth session management (Phase 11).

Refresh tokens are stored **hashed** (sha256) — never plaintext — so a leaked
`sessions` table exposes nothing usable. Sessions support rotation (each
refresh advances to a new opaque token, invalidating the old), explicit
revocation, idle/absolute expiry, and per-session metadata (ip, user-agent).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFoundError, PermissionDeniedError
from app.db.models.security import AuthSession, AuthSessionStatus


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _as_utc(value) -> datetime:
    """DB datetimes round-trip naive (SQLite) — assume UTC before comparing."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class SessionManager:
    """Create, rotate, revoke and expire refresh-token sessions."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        identity_id: UUID,
        company_id: UUID | None,
        refresh_token: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        ttl_days: int | None = None,
        metadata_json: dict | None = None,
    ) -> AuthSession:
        ttl = ttl_days or settings.refresh_token_lifetime_days
        session = AuthSession(
            identity_id=identity_id,
            company_id=company_id,
            token_hash=hash_refresh_token(refresh_token),
            status=AuthSessionStatus.ACTIVE.value,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=datetime.now(UTC) + timedelta(days=ttl),
            metadata_json=metadata_json,
        )
        self.db.add(session)
        self.db.flush()
        return session

    def get_by_refresh_token(self, refresh_token: str) -> AuthSession | None:
        token_hash = hash_refresh_token(refresh_token)
        return self.db.execute(
            select(AuthSession).where(
                AuthSession.token_hash == token_hash,
                AuthSession.status == AuthSessionStatus.ACTIVE.value,
            )
        ).scalar_one_or_none()

    def get(self, session_id: UUID) -> AuthSession:
        obj = self.db.get(AuthSession, session_id)
        if obj is None:
            raise NotFoundError("Session not found.")
        return obj

    def require_active(self, session: AuthSession) -> None:
        """Raise unless the session is active and within both timeouts."""
        now = datetime.now(UTC)
        if session.status != AuthSessionStatus.ACTIVE.value:
            raise PermissionDeniedError(
                "Session is not active.",
                code="session_inactive",
            )
        expires_at = _as_utc(session.expires_at)
        if expires_at and expires_at <= now:
            self.expire(session)
            raise PermissionDeniedError("Session has expired.", code="session_expired")
        created_at = _as_utc(session.created_at)
        if (
            created_at
            and created_at + timedelta(days=settings.session_absolute_timeout_days) <= now
        ):
            self.expire(session)
            raise PermissionDeniedError(
                "Session exceeds its absolute lifetime.",
                code="session_expired",
            )
        idle = _as_utc(session.last_used_at or session.created_at)
        if idle and idle + timedelta(minutes=settings.session_idle_timeout_minutes) <= now:
            self.expire(session)
            raise PermissionDeniedError(
                "Session has been idle too long.",
                code="session_expired",
            )

    def mark_used(self, session: AuthSession) -> None:
        session.last_used_at = datetime.now(UTC)
        self.db.flush()

    def rotate(
        self,
        session: AuthSession,
        new_refresh_token: str,
    ) -> AuthSession:
        """Rotate to a new opaque refresh token; the old one is dead."""
        now = datetime.now(UTC)
        session.status = AuthSessionStatus.REPLACED.value
        session.revoked_at = now
        new_ttl = settings.refresh_token_lifetime_days
        replacement = AuthSession(
            identity_id=session.identity_id,
            company_id=session.company_id,
            token_hash=hash_refresh_token(new_refresh_token),
            status=AuthSessionStatus.ACTIVE.value,
            ip_address=session.ip_address,
            user_agent=session.user_agent,
            created_at=now,
            expires_at=now + timedelta(days=new_ttl),
            last_used_at=now,
            replaced_by_id=session.id,
        )
        self.db.add(replacement)
        self.db.flush()
        return replacement

    def revoke(self, session: AuthSession, *, by: UUID | None = None) -> None:
        session.status = AuthSessionStatus.REVOKED.value
        session.revoked_at = datetime.now(UTC)
        self.db.flush()

    def expire(self, session: AuthSession) -> None:
        if session.status == AuthSessionStatus.ACTIVE.value:
            session.status = AuthSessionStatus.EXPIRED.value
            session.revoked_at = datetime.now(UTC)
            self.db.flush()

    def revoke_all_for_identity(self, identity_id: UUID, *, by: UUID | None = None) -> int:
        """Revoke every active session of a principal (logout-everywhere)."""
        sessions = (
            self.db.execute(
                select(AuthSession).where(
                    AuthSession.identity_id == identity_id,
                    AuthSession.status == AuthSessionStatus.ACTIVE.value,
                )
            )
            .scalars()
            .all()
        )
        for s in sessions:
            self.revoke(s, by=by)
        return len(sessions)
