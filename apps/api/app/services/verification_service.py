"""Verification service (Phase 6).

Thin CRUD and lifecycle orchestration over the verification package. Mirrors
the `OrchestrationService` pattern: routes → service → engine package →
DB models. Handles policy resolution, execution result verification, and
serialization.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.execution import AgentExecution
from app.verification.policy import VerificationPolicy
from app.verification.service import (
    VerificationService as VerificationCoreService,
)
from app.verification.types import VerificationResult


class VerificationService:
    """Coordinates verification operations via the verification core service."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._core = VerificationCoreService(db)

    def get(self, result_id: UUID):
        return self._core.get(result_id)

    def get_run(self, run_id: UUID):
        return self._core.get_run(run_id)

    def get_policy(self, policy_id: UUID):
        return self._core.get_policy(policy_id)

    def list_for_execution(self, execution_id: UUID):
        return self._core.list_for_execution(execution_id)

    def latest_for_execution(self, execution_id: UUID):
        return self._core.latest_for_execution(execution_id)

    def list_runs(self, status: str | None = None, limit: int = 50):
        return self._core.list_runs(status=status, limit=limit)

    def create_policy(
        self,
        name: str,
        config: dict,
        scope_type: str | None = None,
        scope_id: UUID | None = None,
    ):
        return self._core.create_policy(
            name=name, config=config, scope_type=scope_type, scope_id=scope_id
        )

    def verify_execution(
        self,
        execution_id: UUID,
        risk_level: str = "medium",
        policy_override: dict | None = None,
        context: dict | None = None,
    ) -> VerificationResult | None:
        """Verify an execution's result.

        Fetches the execution, builds result data from its output, resolves a
        policy, and runs verification through the core service.
        """
        execution = self.db.get(AgentExecution, execution_id)
        if not execution:
            return None

        # Build result data from execution output
        result_data: dict = {}
        if execution.output_data:
            result_data["output"] = execution.output_data
        if execution.structured_data:
            result_data["structured"] = execution.structured_data

        # Resolve policy
        policy = self._resolve_policy(execution, policy_override)

        return self._core.verify(
            result_data,
            policy=policy,
            execution_id=execution_id,
            task_id=execution.task_id if hasattr(execution, "task_id") else None,
            context=context,
            risk_level=risk_level,
        )

    def verify_data(
        self,
        result_data: dict,
        *,
        execution_id: UUID | None = None,
        task_id: UUID | None = None,
        orchestration_id: UUID | None = None,
        workflow_id: UUID | None = None,
        policy: VerificationPolicy | None = None,
        risk_level: str = "medium",
        context: dict | None = None,
    ) -> VerificationResult:
        """Verify arbitrary result data with an optional policy override."""
        if policy is None:
            policy = self._resolve_policy(None, None)
        result = self._core.verify(
            result_data,
            policy=policy,
            execution_id=execution_id,
            task_id=task_id,
            orchestration_id=orchestration_id,
            workflow_id=workflow_id,
            context=context,
            risk_level=risk_level,
        )
        self._store_outcome_memory(result, source_id=execution_id or task_id)
        return result

    def _store_outcome_memory(self, result: VerificationResult, source_id: UUID | None) -> None:
        """Store zero-or-one semantic memory per verified PASS (§28)."""
        from app.services.memory_service import MemoryService

        if result.status.value != "pass" or not result.passed_criteria:
            return
        content = " ".join(result.passed_criteria[:3])
        if not content:
            return
        MemoryService(self.db).store_reliability_memory(
            namespace="nexus",
            kind="verified_fact",
            content=f"Verified fact (criteria): {content}",
            source_id=source_id,
            importance=0.7,
            metadata_json={"verification_status": result.status.value, "score": result.score},
        )

    def _resolve_policy(
        self,
        execution: AgentExecution | None,
        policy_override: dict | None,
    ) -> VerificationPolicy:
        """Resolve the verification policy for an execution."""
        if policy_override is not None:
            return VerificationPolicy.from_dict(policy_override)

        if execution and hasattr(execution, "agent_id") and execution.agent_id:
            scoped = self._core.get_policy_for_scope("agent", execution.agent_id)
            if scoped:
                return scoped

        if execution and hasattr(execution, "task_id") and execution.task_id:
            scoped = self._core.get_policy_for_scope("task", execution.task_id)
            if scoped:
                return scoped

        # Fall back to global verification_enabled setting behavior
        return VerificationPolicy()


def to_dict(result) -> dict:
    """Serialize a verification result to a dict for API response."""
    from app.verification.service import result_to_dict

    # Accept either VerificationResultDTO or ORM row
    if hasattr(result, "to_dict"):
        return result.to_dict()
    return result_to_dict(result) if result is not None else None


def run_to_dict(run) -> dict:
    """Serialize a verification run to a dict for API response."""
    from app.verification.service import to_dict as run_serializer

    return run_serializer(run)
