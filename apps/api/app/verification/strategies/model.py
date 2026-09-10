"""Model verification strategy (Phase 6, spec §9).

Uses a model provider (LLM) to evaluate a produced result. Provider-independent:
wraps a :class:`ModelProvider` protocol so any backend (OpenAI, Anthropic, mock)
can be used.

The model evaluator returns **no chain-of-thought** — only concise evidence,
criteria, and reason. The model's verdict is NEVER treated as absolute truth;
it contributes only as one strategy among many.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.verification.types import StrategyOutcome as _StrategyOutcome
from app.verification.types import VerificationCriteria, VerificationStatus


class StrategyOutcome(_StrategyOutcome):
    """Local alias."""


@runtime_checkable
class ModelProvider(Protocol):
    """Provider protocol for model-based verification."""

    def evaluate(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Send a prompt to the model and return structured JSON.

        Expected return format::

            {
                "status": "pass" | "fail" | "uncertain",
                "score": 0.0-1.0,
                "confidence": 0.0-1.0,
                "criteria": [
                    {"key": "...", "passed": bool, "reason": "..."}
                ],
                "evidence": "concise summary",
                "reason": "one-line verdict"
            }
        """


@dataclass
class MockModelEvaluator:
    """Deterministic mock evaluator for tests (spec §53).

    Returns PASS/FAIL based on whether the result_data contains a ``_mock_pass``
    key set to True. Confidence is 1.0 (mock is "sure" of itself).
    """

    def evaluate(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        # Deterministic: look for a marker in the prompt
        should_pass = "_mock_pass" in prompt or "should_pass" in prompt
        return {
            "status": "pass" if should_pass else "fail",
            "score": 1.0 if should_pass else 0.0,
            "confidence": 1.0,
            "criteria": [
                {
                    "key": "mock_evaluation",
                    "passed": should_pass,
                    "reason": "Mock evaluator determined outcome",
                }
            ],
            "evidence": "mock evaluation",
            "reason": "Pass" if should_pass else "Fail",
        }


@runtime_checkable
class ModelVerifier(Protocol):
    """Protocol for the model verification strategy."""

    def verify(
        self,
        result_data: dict[str, Any],
        criteria: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> StrategyOutcome:
        """Use a model to evaluate result_data."""


@dataclass
class DefaultModelVerifier:
    """Default model verification implementation.

    Context must include:
    - ``model_provider``: a :class:`ModelProvider` instance

    The prompt is constructed deterministically from the result_data and criteria.
    """

    def verify(
        self,
        result_data: dict[str, Any],
        criteria: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> StrategyOutcome:
        context = context or {}
        criteria = criteria or []

        provider = context.get("model_provider")
        if not provider or not isinstance(provider, ModelProvider):
            return StrategyOutcome(
                status=VerificationStatus.SKIPPED,
                score=0.0,
                confidence=0.0,
                recommendation="No model_provider in context",
            )

        # Build evaluation prompt (concise, un-biased — spec §9)
        verification_criteria_text = ""
        for c in criteria:
            if c.get("type") == "model":
                verification_criteria_text += (
                    f"- {c.get('label', c.get('key', ''))}: {c.get('expected', 'check')}\n"
                )

        if not verification_criteria_text:
            verification_criteria_text = "Check that the output is correct and complete.\n"

        prompt = (
            "Evaluate the following result against these criteria.\n"
            "Return ONLY: status (pass/fail/uncertain), score (0-1), confidence (0-1), "
            "evidence (brief), reason (one line).\n\n"
            "RESULT:\n"
            f"{_summarize(result_data)}\n\n"
            "CRITERIA:\n"
            f"{verification_criteria_text}"
        )

        try:
            response = provider.evaluate(prompt)
        except Exception as exc:
            return StrategyOutcome(
                status=VerificationStatus.UNCERTAIN,
                score=0.0,
                confidence=0.0,
                recommendation=f"Model evaluation failed: {exc}",
            )

        # Parse response
        status_str = response.get("status", "uncertain").lower()
        status_map = {
            "pass": VerificationStatus.PASS,
            "fail": VerificationStatus.FAIL,
            "uncertain": VerificationStatus.UNCERTAIN,
            "partial": VerificationStatus.PARTIAL,
        }
        status = status_map.get(status_str, VerificationStatus.UNCERTAIN)
        score = float(response.get("score", 0.5))
        confidence = float(response.get("confidence", 0.5))
        reason = response.get("reason", "")
        evidence_text = response.get("evidence", "")

        model_criteria = []
        for rc in response.get("criteria", []):
            model_criteria.append(
                VerificationCriteria(
                    key=rc.get("key", "model"),
                    label=rc.get("reason", "Model evaluation"),
                    type="model",
                    passed=rc.get("passed"),
                    evidence=evidence_text,
                )
            )

        return StrategyOutcome(
            status=status,
            score=score,
            confidence=confidence,
            criteria=model_criteria
            if model_criteria
            else [
                VerificationCriteria(
                    key="model_verdict",
                    label="Model evaluation",
                    type="model",
                    passed=status == VerificationStatus.PASS,
                    evidence=evidence_text,
                )
            ],
            evidence=[evidence_text] if evidence_text else [],
            recommendation=reason,
        )


def _summarize(data: dict[str, Any]) -> str:
    """Create a concise summary of result data for the prompt."""
    import json

    # Truncate large values to keep prompt concise
    summary: dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, str) and len(v) > 500:
            summary[k] = v[:500] + "..."
        elif isinstance(v, (list, dict)) and len(str(v)) > 500:
            summary[k] = f"<{type(v).__name__} with {len(v)} items>"
        else:
            summary[k] = v
    try:
        return json.dumps(summary, indent=2, default=str)[:2000]
    except Exception:
        return str(summary)[:2000]
