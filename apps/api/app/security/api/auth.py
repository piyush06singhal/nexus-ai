"""Auth API router (Phase 11) — login / logout / refresh / session.

These endpoints sit on the public whitelist (no bearer required) so users can
obtain sessions; everything else under ``/api/v1`` demands a valid token when
``auth_enabled``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import NexusError
from app.db.session import get_db  # noqa: B008
from app.schemas.security import (
    AuthSessionResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    SessionResultDTO,
)
from app.security.api.deps import get_current_identity

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=SessionResultDTO, status_code=200)
async def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.security.auth import AuthService

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    try:
        result = AuthService(db).login(payload.email, payload.password, ip=ip, user_agent=ua)
    except NexusError as exc:
        raise exc
    db.commit()
    return SessionResultDTO(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        session_id=result.session_id,
        identity=result.identity,
        user=result.user,
        company_id=result.company_id,
    )


@router.post("/logout", status_code=200)
async def logout(
    payload: LogoutRequest,
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.security.auth import AuthService

    AuthService(db).logout(payload.refresh_token)
    db.commit()
    return {"ok": True}


@router.post("/refresh", response_model=SessionResultDTO, status_code=200)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.security.auth import AuthService

    ip = request.client.host if request.client else None
    result = AuthService(db).refresh(payload.refresh_token, ip=ip)
    db.commit()
    return SessionResultDTO(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        session_id=result.session_id,
        identity=result.identity,
        user=result.user,
        company_id=result.company_id,
    )


@router.get("/session", response_model=AuthSessionResponse, status_code=200)
async def current_session(
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.schemas.security import IdentityPublic, UserPublic
    from app.security.authorization import RoleService

    if identity.id is None:
        # auth disabled → anonymous principal; still respond with empty grants.
        return AuthSessionResponse(
            identity=IdentityPublic(
                id=None,
                kind="system",
                name="anonymous",
                status="active",
                company_id=None,
            ),
            user=None,
            roles=[],
            permissions=[],
        )
    role_service = RoleService(db)
    roles = role_service.roles_for_identity(identity.id)
    permissions = sorted(role_service.permissions_for_identity(identity.id))
    user_public = None
    user = None
    if identity.external_ref and identity.external_ref.startswith("user:"):
        from app.security.identity import UserAccountManager

        user = UserAccountManager(db).get_by_email(identity.external_ref[len("user:") :])
        if user is not None:
            user_public = UserPublic.model_validate(user)
    return AuthSessionResponse(
        identity=IdentityPublic.model_validate(identity),
        user=user_public,
        roles=roles,
        permissions=permissions,
    )
