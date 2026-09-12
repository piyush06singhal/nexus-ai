"""Risk classification for external capabilities/actions (Phase 10).

A capability carries a default risk level; company ``integration_policies`` may
override it; and the classifier deterministically *escalates* by action intent
and payload so an otherwise-low read never slips through as an untracked write
or transfer. The result feeds approval routing and the journal.
"""

from __future__ import annotations

from typing import Any

from app.db.models.external import IntegrationCapability, RiskLevel

# Action intents that flag a capability as a write.
_WRITE_INTENT = frozenset(
    {"send", "create", "update", "delete", "cancel", "publish", "merge", "close", "archive"}
)
# Intents that escalate to HIGH.
_HIGH_INTENT = frozenset({"send", "publish", "delete", "merge", "transfer", "deploy"})
# Payload keys that escalate (money/credentials/people/private data).
_SENSITIVE_KEYS = frozenset(
    {
        "amount",
        "payment",
        "price",
        "charge",
        "salary",
        "secret",
        "credential",
        "password",
        "token",
        "api_key",
        "recipients",
        "cc",
        "bcc",
        "high_risk",
    }
)
# Capability names that are intrinsically HIGH/CRITICAL-looking.
_HIGH_CAPABILITY_MARKERS = (
    "send",
    "publish",
    "delete",
    "merge",
    "deploy",
    "transfer",
    "pay",
    "charge",
)
_CRITICAL_CAPABILITY_MARKERS = ("pay", "charge", "transfer", "deploy", "merge")


def _escalate(level: RiskLevel, steps: int = 1) -> RiskLevel:
    order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
    idx = order.index(level)
    return order[min(idx + steps, len(order) - 1)]


class RiskClassifier:
    """Deterministic risk classification for an external action."""

    @staticmethod
    def classify(
        *,
        capability_name: str,
        default_risk: RiskLevel = RiskLevel.LOW,
        payload: dict[str, Any] | None = None,
        action_type: str | None = None,
        risk_override: RiskLevel | None = None,
        approval_required: bool = False,
    ) -> tuple[RiskLevel, list[str]]:
        """Return ``(effective_risk, reasons)``.

        Order: capability default → company override → intent escalation →
        payload escalation → capability-name escalation.
        """
        level = RiskLevel(default_risk)
        reasons: list[str] = [f"capability default {default_risk.value}"]

        if risk_override is not None:
            level = RiskLevel(risk_override)
            reasons = [f"policy override {risk_override.value}"]

        payload = payload or {}
        action_type = (action_type or capability_name).lower()

        # Payload-driven escalation.
        keys = set(str(k).lower() for k in payload.keys())
        if keys & _SENSITIVE_KEYS:
            level = _escalate(level)
            reasons.append("sensitive payload keys present")

        # Intent escalation.
        if any(marker in action_type for marker in _HIGH_INTENT):
            level = _escalate(level, 2 if level == RiskLevel.LOW else 1)
            reasons.append("high-risk intent detected")
        elif any(marker in action_type for marker in _WRITE_INTENT):
            level = _escalate(level, 1)
            reasons.append("write intent detected")

        # Capability-name escalation.
        if any(marker in capability_name.lower() for marker in _CRITICAL_CAPABILITY_MARKERS):
            level = _escalate(level, 2)
            reasons.append("critical capability marker")
        elif any(marker in capability_name.lower() for marker in _HIGH_CAPABILITY_MARKERS):
            level = _escalate(level, 1)
            reasons.append("high-risk capability marker")

        if approval_required:
            reasons.append("capability requires approval")
        return (level, reasons)

    @staticmethod
    def from_capability_row(
        row: IntegrationCapability,
        *,
        payload: dict[str, Any] | None = None,
        risk_override: RiskLevel | None = None,
    ) -> tuple[RiskLevel, list[str]]:
        """Classify from a persisted ``IntegrationCapability`` row."""
        return RiskClassifier.classify(
            capability_name=row.name,
            default_risk=RiskLevel(row.risk_level.value),
            payload=payload,
            risk_override=risk_override,
            approval_required=row.approval_required,
        )
