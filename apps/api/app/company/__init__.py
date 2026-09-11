"""AI Company Layer (Phase 8) — organizational services.

The thin service layer sits above the AI Employee OS (Phase 7) and adds the
organizational structure: company, departments, roles/memberships, goals, KPIs,
budgets, policies, decisions, risks, alerts, reporting, analytics, and company
memory. Business logic lives here, not in routes.
"""

from app.company.lifecycle import (
    CompanyLifecycleError,
    validate_company_transition,
    validate_decision_transition,
    validate_department_transition,
)

__all__ = [
    "CompanyLifecycleError",
    "validate_company_transition",
    "validate_department_transition",
    "validate_decision_transition",
]
