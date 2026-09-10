"""Verification policy (Phase 6).

A :class:`VerificationPolicy` defines *how* to verify a produced result: which
strategies to run, minimum thresholds, retry/escalation behavior, and scope
restrictions. Policies are persisted as JSON in ``verification_policies`` and
loaded here at runtime.

The policy system is intentionally deterministic and stateless — the same
inputs always produce the same policy object, making testing straightforward.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

KNOWN_STRATEGIES = frozenset(
    {
        "deterministic",
        "schema",
        "rules",
        "tool",
        "model",
        "independent_agent",
    }
)


@dataclass
class VerificationPolicy:
    """Configurable verification policy (spec §11).

    Attributes:
        required: Whether verification must run at all. If False, verification
            is a no-op and the result is implicitly ACCEPTED.
        strategies: Ordered list of strategy names to run. Unknown names raise
            at load time.
        minimum_score: Aggregate score (0-1) required to treat the result as
            PASS. Below this → FAIL (or PARTIAL if some strategies passed).
        minimum_confidence: Aggregate confidence (0-1) required. Below this
            → UNCERTAIN (triggers additional verification or escalation).
        max_attempts: Maximum times to re-run verification for the same
            execution (e.g. after a recovery retry).
        allowed_verifier_types: If non-empty, restricts the verifier_type that
            may be used for the independent_agent/model strategies.
        escalation_behavior: "auto" | "manual" | "none" — what to do when the
            aggregate falls below thresholds.
        retry_behavior: "reverify" | "retry_then_verify" | "none" — how
            recovery interacts with verification.
    """

    required: bool = False
    strategies: list[str] = field(default_factory=list)
    minimum_score: float = 0.85
    minimum_confidence: float = 0.80
    max_attempts: int = 2
    allowed_verifier_types: list[str] = field(default_factory=list)
    escalation_behavior: str = "manual"
    retry_behavior: str = "reverify"

    # Runtime-only fields (not persisted)
    _validated: bool = field(default=False, init=False, repr=False)

    def __post_init__(self):
        if self._validated:
            return
        self._validate()
        self._validated = True

    def _validate(self) -> None:
        if not 0.0 <= self.minimum_score <= 1.0:
            raise ValueError("minimum_score must be in [0, 1]")
        if not 0.0 <= self.minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be in [0, 1]")
        if self.max_attempts < 0:
            raise ValueError("max_attempts must be >= 0")
        unknown = set(self.strategies) - KNOWN_STRATEGIES
        if unknown:
            raise ValueError(f"Unknown verification strategy(s): {sorted(unknown)}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON storage."""
        return {
            "required": self.required,
            "strategies": list(self.strategies),
            "minimum_score": self.minimum_score,
            "minimum_confidence": self.minimum_confidence,
            "max_attempts": self.max_attempts,
            "allowed_verifier_types": list(self.allowed_verifier_types),
            "escalation_behavior": self.escalation_behavior,
            "retry_behavior": self.retry_behavior,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationPolicy:
        """Deserialize from JSON storage."""
        # Guard against None/empty
        if not data:
            return cls()
        return cls(
            required=data.get("required", False),
            strategies=data.get("strategies", []),
            minimum_score=data.get("minimum_score", 0.85),
            minimum_confidence=data.get("minimum_confidence", 0.80),
            max_attempts=data.get("max_attempts", 2),
            allowed_verifier_types=data.get("allowed_verifier_types", []),
            escalation_behavior=data.get("escalation_behavior", "manual"),
            retry_behavior=data.get("retry_behavior", "reverify"),
        )

    @classmethod
    def from_json(cls, json_text: str | None) -> VerificationPolicy:
        """Deserialize from a JSON string (as stored in the DB)."""
        if not json_text:
            return cls()
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError:
            return cls()
        return cls.from_dict(data)

    def select_strategies(self, risk_level: str = "medium") -> list[str]:
        """Return the subset of strategies applicable for a risk level (§54).

        Deterministic gating so low-risk tasks don't pay for expensive model
        or independent-agent verification:
        - low: deterministic only (or schema if present)
        - medium: deterministic + schema + rules + tool
        - high: all enabled strategies
        """
        if risk_level == "low":
            return [s for s in self.strategies if s in ("deterministic", "schema")]
        if risk_level == "medium":
            return [s for s in self.strategies if s in ("deterministic", "schema", "rules", "tool")]
        return list(self.strategies)

    def should_escalate(self, score: float, confidence: float) -> bool:
        """Whether the aggregate result triggers escalation."""
        if self.escalation_behavior == "none":
            return False
        return score < self.minimum_score or confidence < self.minimum_confidence


# Convenience: the default "off" policy used when verification is disabled.
DEFAULT_OFF = VerificationPolicy(required=False)
