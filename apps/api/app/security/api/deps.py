"""FastAPI dependencies for the security layer (Phase 11).

Authorization is *gated* by ``settings.auth_enabled``: when auth is off
(dev/test) these dependencies pass through anonymously so the platform is
fully usable without a token; when auth is on (production) they enforce the
full chain (identity → company → role → permission → policy).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import PermissionDeniedError
from app.db.session import get_db  # noqa: B008


@dataclass
class AnonymousIdentity:
    """Inert principal used when auth is disabled (no token attached)."""

    id: UUID | None = None
    kind: str = "system"
    name: str = "anonymous"
    status: str = "active"
    company_id: UUID | None = None
    company_scope_all: bool = True
    external_ref: str | None = None


def get_current_identity(request: Request):
    """Return the authenticated identity, or an anonymous principal iff auth off."""
    identity = getattr(request.state, "identity", None)
    if identity is not None:
        return identity
    if not settings.auth_enabled:
        return AnonymousIdentity()
    raise PermissionDeniedError("Authentication required.", code="auth_required")


def require_permission(action: str):
    """Dependency factory: authorize ``action`` for the caller.

    Inert when ``auth_enabled`` is False (dev/test); enforcing when True.
    """

    async def _dependency(
        identity=Depends(get_current_identity),  # noqa: B008
        db: Session = Depends(get_db),  # noqa: B008
    ):
        if settings.auth_enabled:
            from app.security.authorization import AuthorizationService

            AuthorizationService(db).require(
                identity.id,
                action,
                company_id=getattr(identity, "company_id", None),
            )
        return identity

    return _dependency


bearer_scheme = HTTPBearer(auto_error=False)


def extract_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),  # noqa: B008
) -> str | None:
    """Pull the raw token from the Authorization header (no validation here)."""
    if credentials is None:
        return None
    return credentials.credentials
