"""Independent agent verification strategy (Phase 6, spec §10).

Runs a *different* role/capability agent as verifier through the existing
:class:`AgentRuntime` with explicit verification criteria and **minimal,
un-biased context** (only the candidate output + criteria, not the reasoning).

Uses ``resolve_agent_capabilities`` to pick an agent whose role differs from
the producer's role, ensuring verifier independence (spec §2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from app.verification.types import StrategyOutcome as _StrategyOutcome
from app.verification.types import VerificationCriteria, VerificationStatus


class StrategyOutcome(_StrategyOutcome):
    """Local alias."""


@runtime_checkable
class AgentRunner(Protocol):
    """Protocol for running an agent verification task.

    Wraps the existing AgentRuntime.run() interface so we don't depend on
    the runtime directly in the strategy layer.
    """

    def run(
        self,
        agent_id: UUID,
        task_description: str,
        *,
        input_data: dict[str, Any] | None = None,
        permission_context: Any = None,
    ) -> dict[str, Any]:
        """Run the agent and return its structured output."""

    def resolve_verifier_agent(
        self,
        producer_role: str | None = None,
        allowed_verifier_types: list[str] | None = None,
    ) -> UUID | None:
        """Pick an agent whose role differs from the producer's."""


@runtime_checkable
class IndependentAgentVerifier(Protocol):
    """Protocol for the independent agent verification strategy."""

    def verify(
        self,
        result_data: dict[str, Any],
        criteria: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> StrategyOutcome:
        """Run an independent agent to verify result_data."""


@dataclass
class DefaultIndependentAgentVerifier:
    """Default implementation of independent agent verification.

    Safety guarantees (spec §2, §10):
    - The verifier agent's role differs from the producer's role.
    - The verifier only receives the candidate output + criteria — NOT the
      producer's reasoning, chain-of-thought, or intermediate steps.
    - If no suitable agent can be resolved, the strategy is SKIPPED.

    Context must include:
    - ``agent_runner``: an :class:`AgentRunner` instance
    - ``producer_role`` (optional): role of the producing agent
    - ``allowed_verifier_types`` (optional): restrict which agent types can verify
    """

    def verify(
        self,
        result_data: dict[str, Any],
        criteria: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> StrategyOutcome:
        context = context or {}
        criteria = criteria or []

        runner = context.get("agent_runner")
        if not runner or not isinstance(runner, AgentRunner):
            return StrategyOutcome(
                status=VerificationStatus.SKIPPED,
                score=0.0,
                confidence=0.0,
                recommendation="No agent_runner in context",
            )

        # Resolve an independent verifier agent (§2: must differ from producer)
        producer_role = context.get("producer_role")
        allowed_types = context.get("allowed_verifier_types", [])

        verifier_agent_id = runner.resolve_verifier_agent(
            producer_role=producer_role,
            allowed_verifier_types=allowed_types or None,
        )

        if not verifier_agent_id:
            return StrategyOutcome(
                status=VerificationStatus.SKIPPED,
                score=0.0,
                confidence=0.0,
                recommendation="No independent verifier agent available",
            )

        # Build verification task (minimal, un-biased — §10)
        verification_criteria_text = ""
        for c in criteria:
            if c.get("type") == "independent_agent":
                verification_criteria_text += (
                    f"- {c.get('label', c.get('key', ''))}: {c.get('expected', 'verify')}\n"
                )
        if not verification_criteria_text:
            verification_criteria_text = "Verify the correctness and completeness of this output.\n"

        task_description = (
            "You are an independent verifier. Evaluate the following output "
            "against the stated criteria. Return ONLY:\n"
            "- status: pass / fail / uncertain\n"
            "- score: 0.0 to 1.0\n"
            "- confidence: 0.0 to 1.0\n"
            "- reason: one-line explanation\n"
            "- evidence: brief factual observations (no chain-of-thought)\n\n"
            "OUTPUT TO VERIFY:\n"
            f"{_truncate(str(result_data), 2000)}\n\n"
            "CRITERIA:\n"
            f"{verification_criteria_text}"
        )

        try:
            response = runner.run(
                agent_id=verifier_agent_id,
                task_description=task_description,
                input_data={"result_to_verify": _truncate_dict(result_data, 2000)},
            )
        except Exception as exc:
            return StrategyOutcome(
                status=VerificationStatus.UNCERTAIN,
                score=0.0,
                confidence=0.0,
                recommendation=f"Agent verification failed: {exc}",
            )

        # Parse agent response
        status_str = str(
            response.get("status", response.get("output", {}).get("status", "uncertain"))
        ).lower()
        status_map = {
            "pass": VerificationStatus.PASS,
            "fail": VerificationStatus.FAIL,
            "uncertain": VerificationStatus.UNCERTAIN,
            "partial": VerificationStatus.PARTIAL,
        }
        status = status_map.get(status_str, VerificationStatus.UNCERTAIN)

        score = float(response.get("score", response.get("output", {}).get("score", 0.5)))
        confidence = float(
            response.get("confidence", response.get("output", {}).get("confidence", 0.5))
        )
        reason = response.get("reason", response.get("output", {}).get("reason", ""))
        evidence = response.get("evidence", response.get("output", {}).get("evidence", ""))

        criteria_list = [
            VerificationCriteria(
                key=f"independent_agent_{verifier_agent_id}",
                label=f"Independent agent verification by {verifier_agent_id}",
                type="independent_agent",
                passed=status == VerificationStatus.PASS,
                actual=response,
                expected="pass",
                evidence=evidence,
            )
        ]

        return StrategyOutcome(
            status=status,
            score=score,
            confidence=confidence,
            criteria=criteria_list,
            evidence=[evidence] if evidence else [],
            recommendation=reason,
        )


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _truncate_dict(data: dict[str, Any], max_len: int) -> dict[str, Any]:
    """Truncate string values in a dict to keep prompt size bounded."""
    result: dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, str) and len(v) > max_len // max(1, len(data)):
            limit = max_len // max(1, len(data))
            result[k] = v[:limit] + "..."
        else:
            result[k] = v
    return result
