"""Verification domain types (Phase 6).

Shared, structured types for the verification layer. A :class:`VerificationResult`
is the machine-readable outcome of checking whether a produced result is
*acceptable* — status, score, confidence, and per-criteria evidence. It is
provider-independent and never treated as absolute truth on its own.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class VerificationStatus(StrEnum):
    """Outcome of a verification run/result (spec §3)."""

    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"
    UNCERTAIN = "uncertain"
    SKIPPED = "skipped"


class VerificationError(Exception):
    """Base exception for verification failures."""


class UnknownStrategyError(VerificationError):
    """The verification policy referenced an unknown strategy."""


class PolicyViolationError(VerificationError):
    """A verification policy constraint was violated (e.g. too many attempts)."""


#: Rank helper to aggregate statuses: higher is "better"/more decisive.
_STATUS_RANK = {
    VerificationStatus.FAIL: 0,
    VerificationStatus.PARTIAL: 1,
    VerificationStatus.UNCERTAIN: 2,
    VerificationStatus.SKIPPED: 3,
    VerificationStatus.PASS: 4,
}


@dataclass
class VerificationCriteria:
    """A single checked criterion and its outcome."""

    key: str
    label: str
    type: str  # presence|schema|rule|tool|model|independent_agent
    passed: bool | None = None
    actual: object = None
    expected: object = None
    evidence: object = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VerificationResult:
    """Structured, machine-readable outcome of a verification (spec §3).

    Attributes:
        id: Verification id.
        execution_id: The execution whose result was verified (may be None for
            non-execution subjects like orchestration results).
        verifier_type: The strategy / verifier kind that produced this.
        verifier_id: Id of the specific verifier (agent / policy) that ran.
        status: pass / fail / partial / uncertain / skipped.
        score: 0-1 aggregate score across the checked criteria.
        confidence: 0-1 confidence in the verdict.
        reason: Human-readable summary of the outcome.
        passed_criteria: Keys of checked criteria that passed.
        failed_criteria: Keys of checked criteria that failed.
        evidence: Structured evidence captured during verification.
        recommendations: Suggested next actions (e.g. "retry_with_fact_checking").
        created_at: Timestamp.
    """

    id: UUID = field(default_factory=uuid4)
    run_id: UUID | None = None
    execution_id: UUID | None = None
    verifier_type: str | None = None
    verifier_id: UUID | None = None
    status: VerificationStatus = VerificationStatus.UNCERTAIN
    score: float = 0.0
    confidence: float = 0.0
    reason: str | None = None
    passed_criteria: list[str] = field(default_factory=list)
    failed_criteria: list[str] = field(default_factory=list)
    evidence: list = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        """Serialize to a plain JSON-serializable dict."""
        return {
            "id": str(self.id),
            "run_id": str(self.run_id) if self.run_id else None,
            "execution_id": str(self.execution_id) if self.execution_id else None,
            "verifier_type": self.verifier_type,
            "verifier_id": str(self.verifier_id) if self.verifier_id else None,
            "status": self.status.value,
            "score": self.score,
            "confidence": self.confidence,
            "reason": self.reason,
            "passed_criteria": self.passed_criteria,
            "failed_criteria": self.failed_criteria,
            "evidence": self.evidence,
            "recommendations": self.recommendations,
            "created_at": self.created_at,
        }

    def to_json(self) -> str:
        """Return a JSON string encoding of :meth:`to_dict`."""
        return json.dumps(self.to_dict(), default=str)


@dataclass
class StrategyOutcome:
    """The outcome of a single verification strategy."""

    status: VerificationStatus = VerificationStatus.UNCERTAIN
    score: float = 0.0
    confidence: float = 0.0
    criteria: list[VerificationCriteria] = field(default_factory=list)
    evidence: list = field(default_factory=list)
    recommendation: str | None = None

    def passed_keys(self) -> list[str]:
        return [c.key for c in self.criteria if c.passed]

    def failed_keys(self) -> list[str]:
        return [c.key for c in self.criteria if c.passed is False]


def aggregate_status(outcomes: list[StrategyOutcome]) -> VerificationStatus:
    """Combine per-strategy statuses into one aggregate (spec §5/§7).

    A FAIL from any non-skipped strategy fails the aggregate; otherwise the
    least-decisive result (PASS healthy, PARTIAL, UNCERTAIN) wins. Skipped
    strategies do not influence the aggregate except when nothing else ran.
    """
    nonskipped = [o for o in outcomes if o.status != VerificationStatus.SKIPPED]
    if not nonskipped:
        return VerificationStatus.SKIPPED
    if any(o.status == VerificationStatus.FAIL for o in nonskipped):
        return VerificationStatus.FAIL
    if any(o.status == VerificationStatus.UNCERTAIN for o in nonskipped):
        return VerificationStatus.UNCERTAIN
    if any(o.status == VerificationStatus.PARTIAL for o in nonskipped):
        return VerificationStatus.PARTIAL
    return VerificationStatus.PASS


def aggregate_score(outcomes: list[StrategyOutcome]) -> float:
    """Mean score across non-skipped strategies, 0-1."""
    nonskipped = [o for o in outcomes if o.status != VerificationStatus.SKIPPED]
    if not nonskipped:
        return 0.0
    return sum(o.score for o in nonskipped) / len(nonskipped)


def aggregate_confidence(outcomes: list[StrategyOutcome]) -> float:
    """Product-based confidence across non-skipped strategies, 0-1.

    Confidence should not climb simply because more checks ran, so we multiply
    (each additional check can only lower or hold overall certainty). A single
    confident, decisive deterministic check yields high confidence.
    """
    nonskipped = [o for o in outcomes if o.status != VerificationStatus.SKIPPED]
    if not nonskipped:
        return 0.0
    conf = 1.0
    for o in nonskipped:
        conf *= max(0.0, min(1.0, o.confidence))
    return round(conf, 6)
