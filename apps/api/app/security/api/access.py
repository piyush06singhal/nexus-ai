"""Access management endpoints (Phase 11) — identities, users, roles, secrets.

Secret rows are always rendered as references + masked hint; ciphertext and
plaintext are never returned.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db  # noqa: B008
from app.schemas.security import (
    IdentityPublic,
    PermissionPublic,
    RoleAssignRequest,
    RolePublic,
    SecretCreate,
    SecretReference,
    UserCreate,
    UserCreateResponse,
    UserPublic,
)
from app.security.api.deps import get_current_identity

router = APIRouter(prefix="/access", tags=["access"])


def _err(msg: str, *, code: int = 400) -> None:
    raise HTTPException(code, msg)


# ── Users ───────────────────────────────────────────────────────────────────


@router.get("/users", response_model=list[UserPublic], status_code=200)
async def list_users(
    company_id: UUID | None = None,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.db.models.security import UserAccount

    stmt = __import__("sqlalchemy").select(UserAccount)
    if company_id is not None:
        from app.db.models.security import Identity as IdentityRow

        stmt = stmt.join(IdentityRow, IdentityRow.id == UserAccount.identity_id).where(
            IdentityRow.company_id == company_id
        )
    users = list(db.execute(stmt).scalars().all())
    return [UserPublic.model_validate(u) for u in users]


@router.post("/users", response_model=UserCreateResponse, status_code=201)
async def create_user(
    payload: UserCreate,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.security.auth import AuthService

    result = AuthService(db).create_user_and_session(
        email=payload.email,
        display_name=payload.display_name,
        password=payload.password,
        roles=payload.roles,
        company_id=payload.company_id,
    )
    db.commit()
    return UserCreateResponse(
        identity=IdentityPublic.model_validate(result.identity),
        user=UserPublic.model_validate(result.user),
        roles=payload.roles,
    )


@router.post("/users/{user_id}/roles", response_model=UserPublic, status_code=200)
async def assign_user_roles(
    user_id: UUID,
    payload: RoleAssignRequest,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.security.authorization import RoleService
    from app.security.identity import UserAccountManager

    user = UserAccountManager(db).get(user_id)
    RoleService(db).assign_roles_to_identity(
        user.identity_id, payload.roles, company_id=payload.company_id
    )
    db.commit()
    return UserPublic.model_validate(user)


# ── Roles / Permissions ────────────────────────────────────────────────────


@router.get("/roles", response_model=list[RolePublic], status_code=200)
async def list_roles(
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from sqlalchemy import select

    from app.db.models.security import Role

    roles = list(db.execute(select(Role)).scalars().all())
    return [RolePublic.model_validate(r) for r in roles]


@router.get("/permissions", response_model=list[PermissionPublic], status_code=200)
async def list_permissions(
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from sqlalchemy import select

    from app.db.models.security import Permission

    perms = list(db.execute(select(Permission)).scalars().all())
    return [PermissionPublic.model_validate(p) for p in perms]


# ── Secrets (references + masked only) ─────────────────────────────────────


@router.get("/secrets", response_model=list[SecretReference], status_code=200)
async def list_secrets(
    company_id: UUID | None = None,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from sqlalchemy import select

    from app.db.models.security import Secret

    stmt = select(Secret)
    if company_id is not None:
        stmt = stmt.where(Secret.company_id == company_id)
    secrets = list(db.execute(stmt).scalars().all())
    return [SecretReference.model_validate(s) for s in secrets]


@router.post("/secrets", response_model=SecretReference, status_code=201)
async def create_secret(
    payload: SecretCreate,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.security.secrets import SecretManager

    ref = SecretManager(db).store(
        name=payload.name,
        plaintext=payload.plaintext,
        company_id=payload.company_id,
        kind=payload.kind,
        created_by=identity.id,
        rotation_days=payload.rotation_days,
    )
    db.commit()
    return SecretReference.model_validate(ref)


@router.delete("/secrets/{secret_id}", status_code=204)
async def revoke_secret(
    secret_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    from app.security.secrets import SecretManager

    SecretManager(db).revoke(secret_id)
    db.commit()
