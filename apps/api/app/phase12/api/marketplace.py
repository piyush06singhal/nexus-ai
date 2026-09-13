"""Marketplace endpoints (Phase 12) — agent packages, versions, safe install.

Metadata-only packages; safe install (§37) flows through approval gates for
sensitive/high-risk requests. The marketplace is internal/private and can
never bypass RBAC/ABAC/policy/limits/secrets/audit/approvals.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.phase12 import (
    AgentInstallation,
    AgentPackageBenchmark,
    AgentPackageReview,
    AgentPackageVersion,
)
from app.db.session import get_db  # noqa: B008
from app.phase12.marketplace import MarketplaceService, PackageScanner
from app.schemas.phase12 import (
    AgentPackageCreate,
    AgentPackagePublic,
    AgentPackageVersionPublic,
    InstallationPublic,
    InstallRequest,
    PackageVersionInput,
)
from app.security.api.deps import get_current_identity

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


def _identity_id(identity) -> UUID | None:
    return getattr(identity, "id", None)


def _service(db: Session) -> MarketplaceService:
    return MarketplaceService(db)


# ── Scanner (public, for tooling) ────────────────────────────────────────────


@router.post("/scan", response_model=dict, status_code=200)
async def scan_payload(
    payload: dict,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    return {"violations": PackageScanner.scan(payload.get("metadata"))}


# ── Packages ─────────────────────────────────────────────────────────────────


@router.get("/agents", response_model=list[AgentPackagePublic], status_code=200)
async def list_packages(
    company_id: UUID | None = None,
    status: str | None = None,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    return [
        AgentPackagePublic.model_validate(p)
        for p in _service(db).list_packages(company_id, status=status)
    ]


@router.post("/agents", response_model=AgentPackagePublic, status_code=201)
async def create_package(
    payload: AgentPackageCreate,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    svc = _service(db)
    pkg = svc.create_package(
        name=payload.name,
        company_id=payload.company_id,
        display_name=payload.display_name,
        description=payload.description,
        capabilities=payload.capabilities,
        skills=payload.skills,
        supported_task_types=payload.supported_task_types,
        requirements=payload.requirements,
        security=payload.security,
        created_by=_identity_id(identity),
    )
    if payload.version:
        svc.add_version(
            pkg.id,
            version=payload.version.version,
            changelog=payload.version.changelog,
            compatibility=payload.version.compatibility,
            metadata=payload.version.metadata,
            capabilities=payload.version.capabilities,
            dependencies=payload.version.dependencies,
        )
    return AgentPackagePublic.model_validate(pkg)


@router.get("/agents/{package_id}", response_model=AgentPackagePublic, status_code=200)
async def get_package(
    package_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    pkg = _service(db).get_package(package_id)
    if pkg is None:
        raise HTTPException(status_code=404, detail="Package not found")
    return AgentPackagePublic.model_validate(pkg)


@router.patch("/agents/{package_id}", response_model=AgentPackagePublic, status_code=200)
async def update_package(
    package_id: UUID,
    payload: dict,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    svc = _service(db)
    pkg = svc.get_package(package_id)
    if pkg is None:
        raise HTTPException(status_code=404, detail="Package not found")
    if "description" in payload and payload["description"] is not None:
        pkg.description = payload["description"]
    if "display_name" in payload and payload["display_name"] is not None:
        pkg.display_name = payload["display_name"]
    db.commit()
    return AgentPackagePublic.model_validate(pkg)


@router.post(
    "/agents/{package_id}/versions",
    response_model=AgentPackageVersionPublic,
    status_code=201,
)
async def add_version(
    package_id: UUID,
    payload: PackageVersionInput,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    ver = _service(db).add_version(
        package_id,
        version=payload.version,
        changelog=payload.changelog,
        compatibility=payload.compatibility,
        metadata=payload.metadata,
        capabilities=payload.capabilities,
        dependencies=payload.dependencies,
    )
    return AgentPackageVersionPublic.model_validate(ver)


@router.get(
    "/agents/{package_id}/versions",
    response_model=list[AgentPackageVersionPublic],
    status_code=200,
)
async def list_versions(
    package_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    return [
        AgentPackageVersionPublic.model_validate(v) for v in _service(db).list_versions(package_id)
    ]


@router.post("/agents/{package_id}/publish", response_model=AgentPackagePublic, status_code=200)
async def publish_package(
    package_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    return AgentPackagePublic.model_validate(_service(db).publish(package_id))


@router.post("/agents/{package_id}/deprecate", response_model=AgentPackagePublic, status_code=200)
async def deprecate_package(
    package_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    return AgentPackagePublic.model_validate(_service(db).deprecate(package_id))


# ── Install (safe, approval-gated) ──────────────────────────────────────────


@router.post("/install", response_model=InstallationPublic, status_code=201)
async def install(
    payload: InstallRequest,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    inst = _service(db).install(
        package_id=payload.package_id,
        company_id=payload.company_id,
        version_id=payload.version_id,
        config=payload.config,
        require_approval=payload.require_approval,
        requested_by=_identity_id(identity),
    )
    return InstallationPublic.model_validate(inst)


@router.get("/installations", response_model=list[InstallationPublic], status_code=200)
async def list_installations(
    company_id: UUID | None = None,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    stmt = select(AgentInstallation).order_by(AgentInstallation.created_at.desc())
    if company_id is not None:
        stmt = stmt.where(AgentInstallation.company_id == company_id)
    rows = list(db.execute(stmt).scalars())
    return [InstallationPublic.model_validate(r) for r in rows]


@router.post(
    "/installations/{installation_id}/confirm",
    response_model=InstallationPublic,
    status_code=200,
)
async def confirm_install(
    installation_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    return InstallationPublic.model_validate(_service(db).confirm_install(installation_id))


@router.post(
    "/installations/{installation_id}/reject",
    response_model=InstallationPublic,
    status_code=200,
)
async def reject_install(
    installation_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    return InstallationPublic.model_validate(_service(db).reject_install(installation_id))


# ── Reviews & benchmarks ─────────────────────────────────────────────────────


@router.post("/agents/{package_id}/reviews", response_model=AgentPackagePublic, status_code=201)
async def add_review(
    package_id: UUID,
    payload: dict,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    rating = int(payload.get("rating", 0))
    _service(db).add_review(
        package_id=package_id,
        company_id=(UUID(str(payload["company_id"])) if payload.get("company_id") else None),
        rating=rating,
        comment=payload.get("comment"),
        reviewer_id=_identity_id(identity),
    )
    pkg = _service(db).get_package(package_id)
    return AgentPackagePublic.model_validate(pkg)


@router.get("/agents/{package_id}/reviews", response_model=list, status_code=200)
async def list_reviews(
    package_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    rows = list(
        db.execute(
            select(AgentPackageReview)
            .where(AgentPackageReview.package_id == package_id)
            .order_by(AgentPackageReview.created_at.desc())
        ).scalars()
    )
    return [
        {
            "id": str(r.id),
            "rating": r.rating,
            "comment": r.comment,
            "reviewer_id": str(r.reviewer_id) if r.reviewer_id else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/agents/{package_id}/benchmarks", response_model=list, status_code=200)
async def package_benchmarks(
    package_id: UUID,
    identity=Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    version_ids = list(
        db.execute(
            select(AgentPackageVersion.id).where(AgentPackageVersion.package_id == package_id)
        ).scalars()
    )
    if not version_ids:
        return []
    rows = list(
        db.execute(
            select(AgentPackageBenchmark)
            .where(AgentPackageBenchmark.version_id.in_(version_ids))
            .order_by(AgentPackageBenchmark.created_at.desc())
        ).scalars()
    )
    return [
        {
            "id": str(r.id),
            "version_id": str(r.version_id),
            "benchmark_id": str(r.benchmark_id) if r.benchmark_id else None,
            "score": r.score,
            "dimension": (r.details_json or {}).get("dimension"),
        }
        for r in rows
    ]


__all__ = ["router"]
