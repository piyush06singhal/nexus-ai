"""Global auth middleware (Phase 11, §5).

Enforces a valid bearer access token on every ``/api/v1`` route EXCEPT the
public whitelist (``/auth/*``, ``/health`` + subpaths, ``/docs``, plus any
route outside the v1 prefix). The enforcement only engages when
``settings.auth_enabled`` is true — dev/test run open and the existing 935
tests are untouched. Valid identity is attached to ``request.state.identity``
for ``get_current_identity`` and the permission dependencies.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.errors import NexusError, PermissionDeniedError, _error_envelope
from app.db.session import SessionLocal, get_db


def _requires_token(path: str) -> bool:
    prefix = settings.api_v1_prefix
    if not path.startswith(prefix):
        return False
    if path == f"{prefix}/health" or path.startswith(f"{prefix}/health/"):
        return False
    if path in _public_auth_paths():
        return False
    return True


# Public, token-free endpoints: obtaining / ending a session. Everything else
# under ``/api/v1`` (including ``/auth/session``) requires a valid token.
def _public_auth_paths() -> frozenset[str]:
    prefix = settings.api_v1_prefix
    return frozenset(
        {
            f"{prefix}/auth/login",
            f"{prefix}/auth/logout",
            f"{prefix}/auth/refresh",
        }
    )


class AuthMiddleware(BaseHTTPMiddleware):
    """Bearer-token gate on the API surface (active only when auth_enabled)."""

    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        # Read live so tests/dev can toggle auth without restarting the app.
        if not settings.auth_enabled or not _requires_token(request.url.path):
            return await call_next(request)
        identity = await self._resolve_identity(request)
        if identity is None:
            return JSONResponse(
                status_code=401,
                content=_error_envelope(
                    NexusError(
                        "Missing or invalid authentication token.",
                        code="auth_required",
                    )
                ),
            )
        request.state.identity = identity
        return await call_next(request)

    async def _resolve_identity(self, request: Request):
        auth = request.headers.get("Authorization", "")
        scheme, _, token = auth.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        db, gen = self._open_db(request.app)
        try:
            from app.security.auth import AuthService

            return AuthService(db).validate_access_token(
                token, ip=request.client.host if request.client else None
            )
        except (PermissionDeniedError, ValueError):
            return None
        finally:
            self._close_db(db, gen)

    @staticmethod
    def _open_db(app):
        """Respect FastAPI dependency_overrides (tests) else use SessionLocal."""
        override = app.dependency_overrides.get(get_db)
        if override is not None:
            gen = override()
            return next(gen), gen
        return SessionLocal(), None

    @staticmethod
    def _close_db(db, gen):
        if gen is not None:
            gen.close()
        db.close()
