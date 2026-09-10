"""Verification service (Phase 6).

Thin CRUD, lifecycle orchestration, and serialization over the verification
ORM models — the API and engine layers stay decoupled from the DB.

The service wires the six verification strategies together: given a policy
and result data, it runs the selected strategies in order, aggregates the
outcomes into a single :class:`VerificationResult`, persists the run and
result, and returns the outcome.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.reliability import (
    VerificationPolicy as VerificationPolicyRow,
)
from app.db.models.reliability import (
    VerificationResult as VerificationResultRow,
)
from app.db.models.reliability import (
    VerificationRun,
    VerificationStatus,
)
from app.verification.policy import VerificationPolicy
from app.verification.strategies.deterministic import DefaultDeterministicVerifier
from app.verification.strategies.independent_agent import DefaultIndependentAgentVerifier
from app.verification.strategies.model import DefaultModelVerifier
from app.verification.strategies.rules import DefaultRuleVerifier
from app.verification.strategies.schema import DefaultSchemaVerifier
from app.verification.strategies.tool import DefaultToolVerifier
from app.verification.types import StrategyOutcome
from app.verification.types import VerificationResult as VerificationResultDTO
from app.verification.types import VerificationStatus as VStatus

# ── Strategy registry ─────────────────────────────────────────────────────────

_STRATEGY_INSTANCES: dict[str, Any] = {
    "deterministic": DefaultDeterministicVerifier(),
    "schema": DefaultSchemaVerifier(),
    "rules": DefaultRuleVerifier(),
    "tool": DefaultToolVerifier(),
    "model": DefaultModelVerifier(),
    "independent_agent": DefaultIndependentAgentVerifier(),
}

# ── Serialization helpers ─────────────────────────────────────────────────────


def _loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str)


def to_dict(run: VerificationRun) -> dict:
    return {
        "id": str(run.id),
        "execution_id": str(run.execution_id) if run.execution_id else None,
        "task_id": str(run.task_id) if run.task_id else None,
        "orchestration_id": str(run.orchestration_id) if run.orchestration_id else None,
        "workflow_id": str(run.workflow_id) if run.workflow_id else None,
        "policy_id": str(run.policy_id) if run.policy_id else None,
        "strategy_used": run.strategy_used,
        "status": run.status.value if run.status else "skipped",
        "score": run.score,
        "confidence": run.confidence,
        "created_at": run.created_at,
    }


def result_to_dict(row: VerificationResultRow) -> dict:
    return {
        "id": str(row.id),
        "run_id": str(row.run_id),
        "execution_id": str(row.execution_id) if row.execution_id else None,
        "verifier_type": row.verifier_type,
        "verifier_id": str(row.verifier_id) if row.verifier_id else None,
        "status": row.status.value if row.status else "skipped",
        "score": row.score,
        "confidence": row.confidence,
        "reason": row.reason,
        "failed_criteria": _loads(row.failed_criteria),
        "passed_criteria": _loads(row.passed_criteria),
        "evidence": _loads(row.evidence),
        "recommendations": _loads(row.recommendations),
        "created_at": row.created_at,
    }


def policy_to_dict(row: VerificationPolicyRow) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "config": _loads(row.json_config),
        "scope_type": row.scope_type,
        "scope_id": str(row.scope_id) if row.scope_id else None,
        "enabled": row.enabled,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


# ── Main service ──────────────────────────────────────────────────────────────


class VerificationService:
    """Manages verification lifecycle: run strategies, aggregate, persist."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def verify(
        self,
        result_data: dict[str, Any],
        *,
        policy: VerificationPolicy | None = None,
        execution_id: UUID | None = None,
        task_id: UUID | None = None,
        orchestration_id: UUID | None = None,
        workflow_id: UUID | None = None,
        context: dict[str, Any] | None = None,
        risk_level: str = "medium",
    ) -> VerificationResultDTO:
        """Run verification strategies and return an aggregated result.

        Args:
            result_data: The structured output to verify.
            policy: Verification policy (strategies, thresholds, etc.).
            execution_id: Execution being verified (optional).
            task_id: Task being verified (optional).
            orchestration_id: Orchestration being verified (optional).
            workflow_id: Workflow being verified (optional).
            context: Additional context passed to strategies.
            risk_level: Risk level for strategy gating (low/medium/high).

        Returns:
            The aggregated :class:`VerificationResult`.
        """
        if policy is None:
            policy = VerificationPolicy()

        if not policy.required:
            return VerificationResultDTO(
                status=VStatus.SKIPPED,
                score=0.0,
                confidence=0.0,
                reason="Verification not required by policy",
            )

        context = context or {}

        # Select strategies based on risk level (§54)
        active_strategies = policy.select_strategies(risk_level)

        if not active_strategies:
            return VerificationResultDTO(
                status=VStatus.SKIPPED,
                score=0.0,
                confidence=0.0,
                reason="No strategies selected for this risk level",
            )

        # Run each strategy
        outcomes: list[StrategyOutcome] = []
        for strategy_name in active_strategies:
            verifier = _STRATEGY_INSTANCES.get(strategy_name)
            if verifier is None:
                continue

            try:
                outcome = verifier.verify(
                    result_data=result_data,
                    criteria=context.get("criteria", []),
                    context=context,
                )
                outcomes.append(outcome)
            except Exception as exc:
                # Strategy failure → UNCERTAIN for this strategy
                outcomes.append(
                    StrategyOutcome(
                        status=VStatus.UNCERTAIN,
                        score=0.0,
                        confidence=0.0,
                        recommendation=f"Strategy '{strategy_name}' failed: {exc}",
                    )
                )

        # Aggregate
        aggregated = self._aggregate_outcomes(outcomes, active_strategies)

        # Persist
        run_row = VerificationRun(
            id=uuid4(),
            execution_id=execution_id,
            task_id=task_id,
            orchestration_id=orchestration_id,
            workflow_id=workflow_id,
            strategy_used=",".join(active_strategies),
            status=VerificationStatus(aggregated.status.value),
            score=aggregated.score,
            confidence=aggregated.confidence,
        )
        self.db.add(run_row)

        result_row = VerificationResultRow(
            id=uuid4(),
            run_id=run_row.id,
            execution_id=execution_id,
            verifier_type=",".join(active_strategies),
            status=VerificationStatus(aggregated.status.value),
            score=aggregated.score,
            confidence=aggregated.confidence,
            reason=aggregated.reason,
            failed_criteria=_dumps(aggregated.failed_criteria),
            passed_criteria=_dumps(aggregated.passed_criteria),
            evidence=_dumps(aggregated.evidence),
            recommendations=_dumps(aggregated.recommendations),
        )
        self.db.add(result_row)
        self.db.flush()

        return VerificationResultDTO(
            id=result_row.id,
            run_id=run_row.id,
            execution_id=execution_id,
            verifier_type=",".join(active_strategies),
            status=aggregated.status,
            score=aggregated.score,
            confidence=aggregated.confidence,
            reason=aggregated.reason,
            passed_criteria=aggregated.passed_criteria,
            failed_criteria=aggregated.failed_criteria,
            evidence=aggregated.evidence,
            recommendations=aggregated.recommendations,
            created_at=result_row.created_at,
        )

    def _aggregate_outcomes(
        self,
        outcomes: list[StrategyOutcome],
        strategy_names: list[str],
    ) -> VerificationResultDTO:
        """Aggregate multiple strategy outcomes into a single result."""
        if not outcomes:
            return VerificationResultDTO(
                status=VStatus.SKIPPED,
                score=0.0,
                confidence=0.0,
            )

        from app.verification.types import aggregate_confidence, aggregate_score, aggregate_status

        agg_status = aggregate_status(outcomes)
        agg_score = aggregate_score(outcomes)
        agg_confidence = aggregate_confidence(outcomes)

        # Collect all criteria
        all_passed: list[str] = []
        all_failed: list[str] = []
        all_evidence: list = []
        all_recommendations: list[str] = []

        for o in outcomes:
            all_passed.extend(o.passed_keys())
            all_failed.extend(o.failed_keys())
            all_evidence.extend(o.evidence)
            if o.recommendation:
                all_recommendations.append(o.recommendation)

        reason_parts = []
        for o in outcomes:
            if o.recommendation:
                reason_parts.append(o.recommendation)

        return VerificationResultDTO(
            status=agg_status,
            score=agg_score,
            confidence=agg_confidence,
            reason="; ".join(reason_parts) if reason_parts else None,
            passed_criteria=all_passed,
            failed_criteria=all_failed,
            evidence=all_evidence,
            recommendations=all_recommendations,
        )

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get(self, result_id: UUID) -> VerificationResultRow | None:
        return self.db.get(VerificationResultRow, result_id)

    def get_run(self, run_id: UUID) -> VerificationRun | None:
        return self.db.get(VerificationRun, run_id)

    def get_policy(self, policy_id: UUID) -> VerificationPolicyRow | None:
        return self.db.get(VerificationPolicyRow, policy_id)

    def list_for_execution(self, execution_id: UUID) -> list[VerificationRun]:
        stmt = (
            select(VerificationRun)
            .where(VerificationRun.execution_id == execution_id)
            .order_by(VerificationRun.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def latest_for_execution(self, execution_id: UUID) -> VerificationRun | None:
        stmt = (
            select(VerificationRun)
            .where(VerificationRun.execution_id == execution_id)
            .order_by(VerificationRun.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()

    def list_runs(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[VerificationRun]:
        stmt = select(VerificationRun)
        if status:
            stmt = stmt.where(VerificationRun.status == VerificationStatus(status))
        stmt = stmt.order_by(VerificationRun.created_at.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def list_results_for_run(self, run_id: UUID) -> list[VerificationResultRow]:
        stmt = (
            select(VerificationResultRow)
            .where(VerificationResultRow.run_id == run_id)
            .order_by(VerificationResultRow.created_at)
        )
        return list(self.db.execute(stmt).scalars().all())

    # ── Policy CRUD ───────────────────────────────────────────────────────────

    def create_policy(
        self,
        name: str,
        config: dict[str, Any],
        scope_type: str | None = None,
        scope_id: UUID | None = None,
    ) -> VerificationPolicyRow:
        """Create and persist a verification policy."""
        # Validate the config eagerly so bad policies fail fast.
        VerificationPolicy.from_dict(config)
        row = VerificationPolicyRow(
            id=uuid4(),
            name=name,
            json_config=_dumps(config),
            scope_type=scope_type,
            scope_id=scope_id,
            enabled=True,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def get_policy_for_scope(
        self,
        scope_type: str,
        scope_id: UUID | None = None,
    ) -> VerificationPolicy | None:
        """Find the most specific policy for a scope."""
        stmt = select(VerificationPolicyRow).where(
            VerificationPolicyRow.scope_type == scope_type,
            VerificationPolicyRow.enabled == True,  # noqa: E712
        )
        if scope_id:
            stmt = stmt.where(VerificationPolicyRow.scope_id == scope_id)
        else:
            stmt = stmt.where(VerificationPolicyRow.scope_id.is_(None))

        row = self.db.execute(stmt).first()
        if not row:
            return None
        return VerificationPolicy.from_json(row[0].json_config)
