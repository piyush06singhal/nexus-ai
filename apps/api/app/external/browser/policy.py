"""Browser policy — sensitive-action classification + bounded limits (Phase 10).

Simulated page actions are mostly read/navigation (LOW). A small set of
*sensitive interactions* — anything resembling payment, purchase, submit,
delete, publish, private-data upload, or changing auth/policy settings — is
classified here and routed to an approval gate (§86 Rule 11 / §26-§27). The
session manager enforces action/navigation/session budgets from Settings.
"""

from __future__ import annotations

from typing import Any

from app.db.models.external import ApprovalStatus, RiskLevel

# Literal action types that are always sensitive (none are in the enum, but
# defensive classification keeps this adapter-driven, not enum-driven).
_SENSITIVE_ACTION_TYPES = {
    "submit_payment",
    "purchase",
    "send_message",
    "delete",
    "publish",
    "upload_private_data",
}

_SENSITIVE_TARGET_HINTS = (
    "pay",
    "purchase",
    "checkout",
    "submit",
    "delete",
    "remove",
    "publish",
    "credentials",
    "api key",
    "api_key",
    "secret",
    "password",
    "card_number",
    "ssn",
    "routing",
    "bank",
    "authorize",
    "approve",
    "settings",
    "policy",
)

_SENSITIVE_FIELD_HINTS = (
    "password",
    "card",
    "cvv",
    "card_number",
    "ssn",
    "secret",
    "api_key",
    "token",
    "credential",
)


def classify_risk(action_type: str, target: dict[str, Any] | None) -> RiskLevel:
    """Risk of an action for approval purposes (sensitive ⇒ HIGH/approval)."""
    if action_type in _SENSITIVE_ACTION_TYPES:
        return RiskLevel.HIGH

    label = ""
    element_type = ""
    target_id = ""
    if isinstance(target, dict):
        label = str(target.get("label") or target.get("text") or "")
        element_type = str(target.get("type") or "")
        target_id = str(target.get("id") or "")

    haystack = f"{action_type} {action_type} {element_type} {target_id} {label}".lower()
    if any(hint in haystack for hint in _SENSITIVE_TARGET_HINTS):
        return RiskLevel.HIGH
    if any(hint in haystack for hint in _SENSITIVE_FIELD_HINTS):
        return RiskLevel.HIGH
    if action_type in {"click", "type", "select"}:
        return RiskLevel.MEDIUM if element_type in {"input", "select"} else RiskLevel.LOW
    return RiskLevel.LOW


def approval_status_for(risk: RiskLevel) -> ApprovalStatus:
    """Approval routing: HIGH ⇒ REQUIRED, everything else ⇒ NOT_REQUIRED."""
    return ApprovalStatus.REQUIRED if risk is RiskLevel.HIGH else ApprovalStatus.NOT_REQUIRED
