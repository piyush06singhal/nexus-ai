"""Autonomous Startup Engine — product endpoints.

CRUD + lifecycle for startup products, deterministic (internal) validation, and
the governed launch path (requires an approved PRODUCT_LAUNCH gate at
autonomy levels where ``launch_product`` is not auto-allowed).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.models.company import Company
from app.db.session import get_db
from app.schemas.startup import (
    ProductCreate,
    ProductLifecycleMove,
    ProductRead,
    ProductUpdate,
    ValidationResultRead,
)
from app.startup.products import ProductManager

router = APIRouter(tags=["products"], prefix="/products")


def _company_or_404(db: Session, company_id: UUID) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def _product_or_404(db: Session, company_id: UUID, product_id: UUID):
    manager = ProductManager(db)
    product = manager.get(company_id, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


def _error(exc: Exception) -> HTTPException:
    detail = str(exc) or "Invalid request"
    return HTTPException(status_code=400, detail=detail)


# ── CRUD ────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a product",
)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> ProductRead:
    _company_or_404(db, payload.company_id)
    manager = ProductManager(db)
    try:
        product = manager.create(**payload.model_dump())
        return manager.to_dict(product)
    except ValueError as e:
        raise _error(e) from e


@router.get("", response_model=list[ProductRead], summary="List products for a company")
def list_products(
    company_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[ProductRead]:
    _company_or_404(db, company_id)
    manager = ProductManager(db)
    return [manager.to_dict(p) for p in manager.list_(company_id)]


@router.get("/{product_id}", response_model=ProductRead, summary="Get a product")
def get_product(
    product_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ProductRead:
    product = _product_or_404(db, company_id, product_id)
    return ProductManager(db).to_dict(product)


@router.put("/{product_id}", response_model=ProductRead, summary="Update a product")
def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    company_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ProductRead:
    manager = ProductManager(db)
    try:
        product = manager.update(company_id, product_id, **payload.model_dump(exclude_unset=True))
        return manager.to_dict(product)
    except ValueError as e:
        raise _error(e) from e


# ── Lifecycle / validation / launch ─────────────────────────────────────


@router.post(
    "/{product_id}/status",
    response_model=ProductRead,
    summary="Move a product through its lifecycle",
)
def product_status(
    product_id: UUID,
    payload: ProductLifecycleMove,
    company_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ProductRead:
    _product_or_404(db, company_id, product_id)
    manager = ProductManager(db)
    try:
        product = manager.lifecycle(company_id, product_id, payload.target.value)
        return manager.to_dict(product)
    except ValueError as e:
        raise _error(e) from e


@router.post(
    "/{product_id}/validate",
    response_model=ValidationResultRead,
    summary="Validate launch readiness (deterministic, internal)",
)
def validate_product(
    product_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ValidationResultRead:
    _product_or_404(db, company_id, product_id)
    try:
        return ProductManager(db).validate(company_id, product_id).to_dict()
    except ValueError as e:
        raise _error(e) from e


@router.post(
    "/{product_id}/launch",
    response_model=ProductRead,
    summary="Launch a product (governed; may require an approved gate)",
)
def launch_product(
    product_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    approved_gate_id: UUID | None = Query(default=None),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ProductRead:
    _product_or_404(db, company_id, product_id)
    manager = ProductManager(db)
    try:
        product = manager.launch(company_id, product_id, approved_gate_id=approved_gate_id)
        return manager.to_dict(product)
    except ValueError as e:
        raise _error(e) from e
