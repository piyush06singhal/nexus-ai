"""AI Company Layer — lifecycle state machines.

Defines the explicit status transitions for companies, departments, and
decision requests. Any transition not listed here raises
:class:`CompanyLifecycleError` (a ``ValueError``) so endpoints can map it to
HTTP 400.

State machines (per Phase 8 spec §2, §6, §38):

Company::

    draft ─────────► active
    active ────────► paused | suspended | archived
    paused ────────► active | archived
    suspended ─────► active | archived
    archived       (final — no outgoing transitions)

Department::

    draft ─────► active
    active ────► paused | archived
    paused ────► active | archived
    archived   (final)

Decision::

    draft ─────────────► pending_review | cancelled
    pending_review ────► approved | rejected | cancelled | expired
    approved ──────────► implemented
    implemented        (final)
    rejected / cancelled / expired  (final)
"""

from __future__ import annotations

from app.db.models.company import (
    CompanyStatus,
    DecisionStatus,
    DepartmentStatus,
)


class CompanyLifecycleError(ValueError):
    """Raised when an invalid status transition is requested."""

    def __init__(self, current: str, target: str, entity: str = "entity") -> None:
        self.current = current
        self.target = target
        self.entity = entity
        super().__init__(f"Invalid {entity} transition: {current} → {target}")


# ── Company ──────────────────────────────────────────────────────────────────

_COMPANY_TRANSITIONS: dict[CompanyStatus, set[CompanyStatus]] = {
    CompanyStatus.DRAFT: {CompanyStatus.ACTIVE},
    CompanyStatus.ACTIVE: {
        CompanyStatus.PAUSED,
        CompanyStatus.SUSPENDED,
        CompanyStatus.ARCHIVED,
    },
    CompanyStatus.PAUSED: {CompanyStatus.ACTIVE, CompanyStatus.ARCHIVED},
    CompanyStatus.SUSPENDED: {CompanyStatus.ACTIVE, CompanyStatus.ARCHIVED},
    CompanyStatus.ARCHIVED: set(),
}


def validate_company_transition(current: CompanyStatus, target: CompanyStatus) -> None:
    """Raise :class:`CompanyLifecycleError` if ``current → target`` is invalid."""
    allowed = _COMPANY_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise CompanyLifecycleError(current.value, target.value, entity="company")


# ── Department ───────────────────────────────────────────────────────────────

_DEPARTMENT_TRANSITIONS: dict[DepartmentStatus, set[DepartmentStatus]] = {
    DepartmentStatus.DRAFT: {DepartmentStatus.ACTIVE},
    DepartmentStatus.ACTIVE: {DepartmentStatus.PAUSED, DepartmentStatus.ARCHIVED},
    DepartmentStatus.PAUSED: {DepartmentStatus.ACTIVE, DepartmentStatus.ARCHIVED},
    DepartmentStatus.ARCHIVED: set(),
}


def validate_department_transition(current: DepartmentStatus, target: DepartmentStatus) -> None:
    """Raise :class:`CompanyLifecycleError` if an invalid department transition."""
    allowed = _DEPARTMENT_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise CompanyLifecycleError(current.value, target.value, entity="department")


# ── Decision ─────────────────────────────────────────────────────────────────

_DECISION_TRANSITIONS: dict[DecisionStatus, set[DecisionStatus]] = {
    DecisionStatus.DRAFT: {
        DecisionStatus.PENDING_REVIEW,
        DecisionStatus.CANCELLED,
    },
    DecisionStatus.PENDING_REVIEW: {
        DecisionStatus.APPROVED,
        DecisionStatus.REJECTED,
        DecisionStatus.CANCELLED,
        DecisionStatus.EXPIRED,
    },
    DecisionStatus.APPROVED: {DecisionStatus.IMPLEMENTED},
    DecisionStatus.IMPLEMENTED: set(),
    DecisionStatus.REJECTED: set(),
    DecisionStatus.CANCELLED: set(),
    DecisionStatus.EXPIRED: set(),
}


def validate_decision_transition(current: DecisionStatus, target: DecisionStatus) -> None:
    """Raise :class:`CompanyLifecycleError` if an invalid decision transition."""
    allowed = _DECISION_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise CompanyLifecycleError(current.value, target.value, entity="decision")
