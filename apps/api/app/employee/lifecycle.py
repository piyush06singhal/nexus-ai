"""AI Employee OS — lifecycle state machine.

Defines valid status transitions for AI employees.  Any transition not listed
here raises ``EmployeeLifecycleError``.

State machine::

    draft ──────► active
    active ─────► busy | paused | suspended | terminated
    busy ────────► active | suspended | terminated
    paused ──────► active | terminated
    suspended ───► active | terminated
    on_leave ────► active | terminated

A terminated employee cannot receive tasks.
"""

from __future__ import annotations

from app.employee.types import EmployeeStatus

# Valid transitions: current_status → set of allowed target statuses.
_VALID_TRANSITIONS: dict[EmployeeStatus, set[EmployeeStatus]] = {
    EmployeeStatus.DRAFT: {EmployeeStatus.ACTIVE},
    EmployeeStatus.ACTIVE: {
        EmployeeStatus.BUSY,
        EmployeeStatus.PAUSED,
        EmployeeStatus.SUSPENDED,
        EmployeeStatus.TERMINATED,
    },
    EmployeeStatus.BUSY: {
        EmployeeStatus.ACTIVE,
        EmployeeStatus.SUSPENDED,
        EmployeeStatus.TERMINATED,
    },
    EmployeeStatus.PAUSED: {EmployeeStatus.ACTIVE, EmployeeStatus.TERMINATED},
    EmployeeStatus.ON_LEAVE: {EmployeeStatus.ACTIVE, EmployeeStatus.TERMINATED},
    EmployeeStatus.SUSPENDED: {EmployeeStatus.ACTIVE, EmployeeStatus.TERMINATED},
    EmployeeStatus.TERMINATED: set(),
}


class EmployeeLifecycleError(ValueError):
    """Raised when an invalid status transition is attempted.

    Inherits from ``ValueError`` so that endpoint ``except ValueError`` handlers
    catch it and return a proper 400/422 response.
    """

    def __init__(self, current: EmployeeStatus, target: EmployeeStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Cannot transition from {current.value!r} to {target.value!r}")


def can_transition(current: EmployeeStatus, target: EmployeeStatus) -> bool:
    """Return ``True`` if the transition from *current* to *target* is valid."""
    return target in _VALID_TRANSITIONS.get(current, set())


def validate_transition(current: EmployeeStatus, target: EmployeeStatus) -> None:
    """Validate a transition, raising ``EmployeeLifecycleError`` on failure."""
    if not can_transition(current, target):
        raise EmployeeLifecycleError(current, target)


def is_available_for_tasks(status: EmployeeStatus) -> bool:
    """Return ``True`` if the employee can accept new tasks."""
    return status in {EmployeeStatus.ACTIVE, EmployeeStatus.BUSY}
