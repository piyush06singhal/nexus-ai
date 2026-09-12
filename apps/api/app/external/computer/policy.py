"""Computer policy — sensitive-action classification + limits (Phase 10, §51).

Input actions on the simulated desktop are mostly navigation/data entry (LOW-
MEDIUM). Anything that touches the *purchase/sensitive path* (§67: Confirm
purchase, card fields, credential fields) is HIGH and routed to an approval
gate. The session manager enforces action/session budgets from Settings.
"""

from __future__ import annotations

from typing import Any

from app.db.models.external import ApprovalStatus, RiskLevel

# Literally-dangerous action types (defensive; the enum has none of these,
# but keeps classification adapter-driven rather than enum-driven).
_SENSITIVE_ACTION_TYPES = {
    "submit_payment",
    "purchase",
    "confirm_purchase",
    "send_money",
    "approve_expense",
}


def classify_risk(
    action_type: str, driver: Any, action_type_value: str, input_data: dict[str, Any]
) -> RiskLevel:
    """Risk of a computer action for approval purposes."""
    if action_type_value in _SENSITIVE_ACTION_TYPES:
        return RiskLevel.HIGH
    if hasattr(driver, "is_sensitive") and driver.is_sensitive(action_type_value, input_data or {}):
        return RiskLevel.HIGH
    if action_type_value in {"click", "double_click", "type", "drag", "key_press"}:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def approval_status_for(risk: RiskLevel) -> ApprovalStatus:
    """Approval routing: HIGH ⇒ REQUIRED, everything else ⇒ NOT_REQUIRED."""
    return ApprovalStatus.REQUIRED if risk is RiskLevel.HIGH else ApprovalStatus.NOT_REQUIRED
