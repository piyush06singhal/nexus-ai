"""AI Company Layer — roles endpoints (Phase 8)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.company.roles import RoleManager
from app.db.session import get_db
from app.schemas.company import OrgRoleCreate

router = APIRouter(tags=["roles"], prefix="/roles")


@router.post("", status_code=201, summary="Create an organizational role")
def create_role(
    payload: OrgRoleCreate,
    company_id: UUID | None = Query(default=None),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> dict:
    mgr = RoleManager(db)
    try:
        role = mgr.create(
            company_id=company_id,
            name=payload.name,
            title=payload.title,
            authority_level=payload.authority_level,
            responsibilities=payload.responsibilities,
            required_skills=payload.required_skills,
            default_policies=payload.default_policies,
        )
        return mgr.to_dict(role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("", response_model=list[dict], summary="List organizational roles")
def list_roles(
    company_id: UUID | None = Query(default=None),  # noqa: B008
    authority_level: str | None = Query(default=None),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[dict]:
    mgr = RoleManager(db)
    roles = mgr.list_(company_id=company_id, authority_level=authority_level)
    return [mgr.to_dict(r) for r in roles]


@router.get("/{role_id}", response_model=dict, summary="Get an organizational role")
def get_role(role_id: UUID, db: Session = Depends(get_db)) -> dict:  # noqa: B008
    mgr = RoleManager(db)
    role = mgr.get(role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return mgr.to_dict(role)
