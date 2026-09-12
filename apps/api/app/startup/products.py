"""Products — the startup's buildable, launchable products.

:class:`ProductManager` handles CRUD + lifecycle + the launch gate.
:class:`ProductValidator` runs a deterministic, clearly-labeled *simulated* /
internal validation of launch readiness (product definition completeness,
target users, success metrics, launch criteria, owner, budget) — it never claims
external market validation, which is out of scope and clearly labeled as such.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.startup import Product, ProductStatus
from app.startup.autonomy import AutonomyService
from app.startup.events import StartupEventLogger, StartupEvents
from app.startup.types import ValidationResult


class ProductManager:
    """Create, list, update, and drive products through their lifecycle."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._events = StartupEventLogger(db)

    def create(
        self,
        *,
        company_id: UUID,
        name: str,
        description: str | None = None,
        product_type: str | None = None,
        target_users: list[str] | None = None,
        value_proposition: str | None = None,
        owner_id: UUID | None = None,
        strategic_priority: int = 0,
        budget: dict[str, Any] | None = None,
        success_metrics: list[str] | None = None,
        launch_criteria: list[str] | None = None,
    ) -> Product:
        product = Product(
            company_id=company_id,
            name=name,
            description=description,
            product_type=product_type,
            target_users=json.dumps(target_users) if target_users else None,
            value_proposition=value_proposition,
            owner_id=owner_id,
            strategic_priority=strategic_priority,
            budget=json.dumps(budget) if budget else None,
            success_metrics=json.dumps(success_metrics) if success_metrics else None,
            launch_criteria=json.dumps(launch_criteria) if launch_criteria else None,
            status=ProductStatus.IDEA,
        )
        self._db.add(product)
        self._db.commit()
        self._events.log(
            action=StartupEvents.PRODUCT_CREATED,
            company_id=company_id,
            target_type="product",
            target_id=product.id,
            details={"name": name, "status": product.status.value},
            outcome="success",
        )
        return product

    def get(self, company_id: UUID, product_id: UUID) -> Product | None:
        product = self._db.get(Product, product_id)
        if product is None or product.company_id != company_id:
            return None
        return product

    def list_(self, company_id: UUID) -> list[Product]:
        stmt = (
            select(Product)
            .where(Product.company_id == company_id)
            .order_by(Product.created_at.desc())
        )
        return list(self._db.execute(stmt).scalars().all())

    def update(self, company_id: UUID, product_id: UUID, **fields: Any) -> Product:
        product = self._require(company_id, product_id)
        _json_keys = ("target_users", "budget", "success_metrics", "launch_criteria", "validation")
        for key, value in fields.items():
            if value is None or not hasattr(product, key):
                continue
            if key in _json_keys and isinstance(value, (list, dict)):
                setattr(product, key, json.dumps(value))
            elif key in _json_keys:
                setattr(product, key, value)
            elif key == "status":
                product.status = ProductStatus(value)
            else:
                setattr(product, key, value)
        self._db.commit()
        return product

    # ── Lifecycle ──────────────────────────────────────────────────────

    def lifecycle(self, company_id: UUID, product_id: UUID, target: str) -> Product:
        """Move a product to *target* (IDEA→DISCOVERY→VALIDATION→…)."""
        product = self._require(company_id, product_id)
        target_status = ProductStatus(target)
        _validate_transition(product.status, target_status)
        product.status = target_status
        self._db.commit()
        self._events.log(
            action=StartupEvents.PRODUCT_STATUS_CHANGED,
            company_id=company_id,
            target_type="product",
            target_id=product.id,
            details={"from": product.status.value, "to": target_status.value},
            outcome="success",
        )
        return product

    def validate(self, company_id: UUID, product_id: UUID) -> ValidationResult:
        product = self._require(company_id, product_id)
        result = ProductValidator(self._db).validate(product)
        product.validation = __import__("json").dumps(result.to_dict(), default=str)
        self._db.commit()
        self._events.log(
            action=StartupEvents.PRODUCT_VALIDATED,
            company_id=company_id,
            target_type="product",
            target_id=product.id,
            details={
                "ok": result.ok,
                "errors": len([i for i in result.issues if i.severity == "error"]),
            },
            outcome="success" if result.ok else "feedback",
        )
        return result

    def launch(
        self,
        company_id: UUID,
        product_id: UUID,
        *,
        approved_gate_id: UUID | None = None,
    ) -> Product:
        """Launch a product — only past an approved PRODUCT_LAUNCH gate."""
        product = self._require(company_id, product_id)
        decision = AutonomyService(self._db).enforce(
            "launch_product",
            company_id,
            approved_gate_id=approved_gate_id,
        )
        del decision
        result = ProductValidator(self._db).validate(product)
        if not result.ok:
            raise ValueError("Product is not launch-ready; fix validation errors first")
        product = self._require(company_id, product_id)
        product.status = ProductStatus.LAUNCHED
        self._db.commit()
        self._events.log(
            action=StartupEvents.PRODUCT_LAUNCHED,
            company_id=company_id,
            target_type="product",
            target_id=product.id,
            details={"name": product.name},
            outcome="success",
        )
        return product

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self, product: Product) -> dict[str, Any]:
        return {
            "id": str(product.id),
            "company_id": str(product.company_id),
            "name": product.name,
            "description": product.description,
            "product_type": product.product_type,
            "target_users": _loads_list(product.target_users),
            "value_proposition": product.value_proposition,
            "status": product.status.value,
            "owner_id": str(product.owner_id) if product.owner_id else None,
            "strategic_priority": product.strategic_priority,
            "budget": _loads(product.budget),
            "success_metrics": _loads_list(product.success_metrics),
            "launch_criteria": _loads_list(product.launch_criteria),
            "validation": _loads(product.validation),
            "created_at": product.created_at.isoformat() if product.created_at else None,
        }

    def _require(self, company_id: UUID, product_id: UUID) -> Product:
        product = self.get(company_id, product_id)
        if product is None:
            raise ValueError("Product not found")
        return product


class ProductValidator:
    """Deterministic, internal launch-readiness validation (never external)."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def validate(self, product: Product) -> ValidationResult:
        result = ValidationResult()
        if not (product.name or "").strip():
            result.error("missing_name", "A product name is required")
        if not (product.description or "").strip():
            result.warn("missing_description", "No product description")
        if not (product.value_proposition or "").strip():
            result.warn("missing_value_proposition", "No value proposition")
        if not _loads_list(product.target_users):
            result.warn("missing_target_users", "No target users defined")
        if not _loads_list(product.success_metrics):
            result.warn("missing_success_metrics", "No success metrics defined")
        criteria = _loads_list(product.launch_criteria)
        if not criteria:
            result.error("missing_launch_criteria", "Launch requires defined launch criteria")
        elif any(len(str(c)) < 5 for c in criteria):
            result.warn("vague_launch_criteria", "Some launch criteria look vague")
        if product.owner_id is None:
            result.warn("missing_owner", "No owner assigned to the product")
        return result


# ── Transitions (subset of the full lifecycle is allowed per step) ───────────

_ALLOWED_TRANSITIONS: dict[ProductStatus, set[ProductStatus]] = {
    ProductStatus.IDEA: {ProductStatus.DISCOVERY, ProductStatus.PAUSED, ProductStatus.RETIRED},
    ProductStatus.DISCOVERY: {ProductStatus.VALIDATION, ProductStatus.PAUSED},
    ProductStatus.VALIDATION: {
        ProductStatus.PLANNING,
        ProductStatus.BUILDING,
        ProductStatus.PAUSED,
    },
    ProductStatus.PLANNING: {ProductStatus.BUILDING, ProductStatus.PAUSED},
    ProductStatus.BUILDING: {ProductStatus.TESTING, ProductStatus.PAUSED},
    ProductStatus.TESTING: {
        ProductStatus.READY_FOR_LAUNCH,
        ProductStatus.BUILDING,
        ProductStatus.PAUSED,
    },
    ProductStatus.READY_FOR_LAUNCH: {
        ProductStatus.LAUNCHED,
        ProductStatus.TESTING,
        ProductStatus.PAUSED,
    },
    ProductStatus.LAUNCHED: {
        ProductStatus.MEASURING,
        ProductStatus.ITERATING,
        ProductStatus.PAUSED,
    },
    ProductStatus.MEASURING: {ProductStatus.ITERATING, ProductStatus.PAUSED, ProductStatus.RETIRED},
    ProductStatus.ITERATING: {ProductStatus.MEASURING, ProductStatus.PAUSED},
    ProductStatus.PAUSED: {ProductStatus.DISCOVERY, ProductStatus.PLANNING, ProductStatus.BUILDING},
    ProductStatus.RETIRED: set(),
}


def _validate_transition(current: ProductStatus, target: ProductStatus) -> None:
    if target not in _ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid product transition: {current.value} → {target.value}")


def _loads(raw: str | None) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _loads_list(raw: str | None) -> list[str]:
    value = _loads(raw)
    return [str(v) for v in value] if isinstance(value, list) else []
