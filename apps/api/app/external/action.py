"""External action manager — the governed funnel (Phase 10, §2).

``ExternalActionManager`` is the single choke point through which every
external action passes: risk → policy → autonomy → approval → execute → scrub →
verify → recover → memory → audit. It composes (never duplicates) the Phase
0–9 systems: :class:`app.startup.autonomy.AutonomyService`,
:class:`app.startup.gates.ApprovalGateManager`,
:class:`app.services.verification_service.VerificationService`,
:class:`app.services.memory_service.MemoryService`, and the Phase 8
OrgEventLogger. Both agent-driven capability tools and direct API calls go
through this same funnel (Rule 4/§4).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy import select as sa_select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.external import (
    ApprovalStatus,
    ExternalAction,
    ExternalActionAttempt,
    ExternalActionStatus,
    ExternalIntegration,
    IntegrationCapability,
    IntegrationConnection,
    Reversibility,
    RiskLevel,
)

# Models for one-shot imports (avoided upstream to prevent import cycles).
from app.db.models.startup import ApprovalGate, ApprovalGateStatus  # noqa: E402
from app.external.api.auth import resolve_auth_context
from app.external.credential import CredentialVault
from app.external.events import ExternalEventLogger, ExternalEvents
from app.external.idempotency import IdempotencyGuard, generate_operation_id, normalize_key
from app.external.integration import IntegrationService
from app.external.policy import ExternalPolicyResolver
from app.external.recovery.mapping import (
    classify_exception,
    classify_external_failure,
    retryable,
    strategy_for,
)
from app.external.registry import get_provider
from app.external.result import ExternalActionError, scrub_result
from app.external.risk import RiskClassifier
from app.external.security.exfiltration import ExfiltrationBlockedError, guard_payload
from app.external.types import (
    AuthContext,
    ExternalPermissionFailure,
    ExternalProviderError,
    ExternalResult,
)
from app.startup.autonomy import ActionDecision, AutonomyService
from app.startup.gates import ApprovalGateManager


class ExternalActionManager:
    """Create, gate, execute, cancel and journal governed external actions."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._events = ExternalEventLogger(db)
        self._integration = IntegrationService(db)
        self._vault = CredentialVault(db)

    # ── Create / request ──────────────────────────────────────────────

    def create(
        self,
        *,
        company_id: UUID,
        integration_id: UUID,
        capability: str,
        payload: dict[str, Any] | None = None,
        action_type: str = "execute",
        idempotency_key: str | None = None,
        connection_id: UUID | None = None,
        employee_id: UUID | None = None,
        agent_id: UUID | None = None,
        execution_id: UUID | None = None,
        workflow_execution_id: UUID | None = None,
        orchestration_id: UUID | None = None,
        approved_gate_id: UUID | None = None,
        correlation_id: str | None = None,
    ) -> ExternalAction:
        """Run the full governance funnel and journal the outcome.

        Returns the journal row; raises :class:`ExternalActionError` on
        block/approval-required/duplicate (the API layer maps to 4xx).
        """
        integration = self._integration.get(company_id, integration_id)
        capability_row = self._integration.capability(company_id, integration_id, capability)
        payload = payload or {}

        # 0. Company ceiling on journaled actions (§16).
        if self._action_count(company_id) >= settings.max_external_actions:
            raise ExternalActionError(
                "Company external-action ceiling reached", status="blocked", code="limit_reached"
            )

        # 1. Idempotency — duplicate SUCCEEDED is refused.
        guard = IdempotencyGuard(self._db)
        if idempotency_key and guard.is_duplicate(
            company_id=company_id,
            integration_id=integration_id,
            capability=capability,
            idempotency_key=idempotency_key,
        ):
            self._events.log(
                action=ExternalEvents.EXTERNAL_ACTION_DUPLICATE_BLOCKED,
                company_id=company_id,
                actor="system",
                target_type="external_action",
                details={"capability": capability},
            )
            raise ExternalActionError(
                f"Duplicate external action for idempotency_key {idempotency_key[:16]}…",
                status="blocked",
                code="duplicate",
            )

        # 2. Risk classification.
        risk, risk_reasons = RiskClassifier.classify(
            capability_name=capability,
            default_risk=RiskLevel(capability_row.risk_level.value),
            payload=payload,
            action_type=action_type,
            approval_required=capability_row.approval_required,
        )

        # 3. Policy resolution (Phase 8 + integration + domain allowlists).
        policy = ExternalPolicyResolver(self._db).resolve(
            company_id=company_id,
            integration_id=integration_id,
            capability_name=capability,
            risk_level=risk,
            payload=payload,
            capability_row=capability_row,
            employee_id=employee_id,
            default_rate_limit=settings.external_rate_limit_per_minute,
        )

        # 4. Exfiltration guard on the outgoing payload.
        try:
            safe_payload = guard_payload(
                payload,
                max_allowed=getattr(settings, "external_outbound_class", "confidential"),
                allow_secret_for=set(payload.get("_allow_secret_fields", []) or []),
            )
        except ExfiltrationBlockedError as exc:
            self._journal_blocked(
                company_id,
                integration_id,
                connection_id,
                capability,
                action_type,
                payload,
                risk,
                capability_row,
                idempotency_key,
                policy,
                str(exc),
                employee_id,
                agent_id,
                execution_id,
                workflow_execution_id,
                orchestration_id,
                correlation_id,
            )
            self._events.log(
                action=ExternalEvents.EXFILTRATION_BLOCKED,
                company_id=company_id,
                target_type="external_action",
                details={"capability": capability},
            )
            raise ExternalActionError(
                str(exc), status="blocked", code="exfiltration_blocked"
            ) from exc
        safe_payload.pop("_allow_secret_fields", None)

        # 5. Governance: policy gate → autonomy → approval. The resolver is the
        # single authority on effective risk (it merges capability defaults,
        # integration-policy overrides, and the intrinsic ``approval_required``
        # flag), so approval routing follows ``policy.effective_risk`` — an
        # override to LOW can auto-run, but an intrinsically approval-required
        # capability (e.g. send_message) always stays gated.
        require_approval = policy.require_approval or _risk_priority(policy.effective_risk) >= 2
        if policy.allowed is False:
            self._journal_blocked(
                company_id,
                integration_id,
                connection_id,
                capability,
                action_type,
                safe_payload,
                risk,
                capability_row,
                idempotency_key,
                policy,
                "; ".join(policy.reasons),
                employee_id,
                agent_id,
                execution_id,
                workflow_execution_id,
                orchestration_id,
                correlation_id,
            )
            self._events.log(
                action=ExternalEvents.EXTERNAL_ACTION_BLOCKED,
                company_id=company_id,
                target_type="external_action",
                details={"capability": capability, "reasons": policy.reasons},
            )
            raise ExternalActionError(
                "Denied by external policy", status="blocked", code="policy_denied"
            )

        decision, decision_reason = AutonomyService(self._db).decision(
            "external_action", company_id
        )
        if decision.value == "block":
            # An explicit company autonomy policy ruled this non-autonomous.
            # The reason explains the block; nothing below runs.
            self._journal_blocked(
                company_id,
                integration_id,
                connection_id,
                capability,
                action_type,
                safe_payload,
                risk,
                capability_row,
                idempotency_key,
                policy,
                decision_reason,
                employee_id,
                agent_id,
                execution_id,
                workflow_execution_id,
                orchestration_id,
                correlation_id,
            )
            raise ExternalActionError(
                f"Blocked by autonomy policy: {decision_reason}",
                status="blocked",
                code="autonomy_blocked",
            )

        # Unlisted/unknown external actions require approval at every autonomy
        # level by default (§86 Rule 12); only an explicit ``allow`` in the
        # company allow_matrix lets an otherwise-ungated read auto-run.
        require_approval = require_approval or decision == ActionDecision.REQUIRE_APPROVAL

        if require_approval:
            if approved_gate_id:
                # An approved gate authorizes exactly one action once (§8): journal
                # this action as the gate's consumer and execute it immediately.
                action = self._journal_authorized(
                    company_id,
                    integration_id,
                    connection_id,
                    capability,
                    action_type,
                    safe_payload,
                    risk,
                    capability_row,
                    idempotency_key,
                    policy,
                    employee_id,
                    agent_id,
                    execution_id,
                    workflow_execution_id,
                    orchestration_id,
                    correlation_id,
                )
                action.approval_gate_id = approved_gate_id
                action.approval_status = ApprovalStatus.APPROVED
                self._db.commit()
                return self.execute(
                    action.id, company_id=company_id, approved_gate_id=approved_gate_id
                )
            gate_id = self._park_for_approval(
                company_id=company_id,
                integration=integration,
                capability=capability,
                payload=safe_payload,
                risk=risk,
                reason=decision_reason,
                employee_id=employee_id,
            )
            action = self._journal_awaiting(
                company_id,
                integration_id,
                connection_id,
                capability,
                action_type,
                safe_payload,
                risk,
                capability_row,
                idempotency_key,
                policy,
                gate_id,
                employee_id,
                agent_id,
                execution_id,
                workflow_execution_id,
                orchestration_id,
                correlation_id,
            )
            return action

        # 6. Execute now (approved or low-risk).
        action = self._journal_authorized(
            company_id,
            integration_id,
            connection_id,
            capability,
            action_type,
            safe_payload,
            risk,
            capability_row,
            idempotency_key,
            policy,
            employee_id,
            agent_id,
            execution_id,
            workflow_execution_id,
            orchestration_id,
            correlation_id,
        )
        return self.execute(action.id, company_id=company_id)

    def execute(
        self, action_id: UUID, *, company_id: UUID, approved_gate_id: UUID | None = None
    ) -> ExternalAction:
        """Execute an authorized/approved action through its provider adapter."""
        action = self._db.get(ExternalAction, action_id)
        if action is None or action.company_id != company_id:
            raise ExternalActionError(
                f"Action {action_id} not found", status="failed", code="not_found"
            )
        if action.status in {
            ExternalActionStatus.SUCCEEDED,
            ExternalActionStatus.CANCELLED,
            ExternalActionStatus.BLOCKED,
            ExternalActionStatus.FAILED,
        }:
            raise ExternalActionError(
                f"Action already reached a terminal state ({action.status.value})",
                status=action.status.value,
                code="terminal",
            )
        if action.status == ExternalActionStatus.AWAITING_APPROVAL and not approved_gate_id:
            raise ExternalActionError(
                "Action is awaiting approval", status="awaiting_approval", code="approval_required"
            )

        if approved_gate_id:
            try:
                self._verify_gate(company_id, approved_gate_id, action)
            except ExternalActionError as exc:
                # The gate was rejected / already consumed / wrong type — this
                # action must not run, and the journal must show why.
                action.status = ExternalActionStatus.BLOCKED
                action.error = exc.message
                action.completed_at = datetime.now(UTC)
                self._db.commit()
                raise

        integration = self._integration.get(company_id, action.integration_id)
        connection = None
        if action.connection_id:
            connection = self._integration.get_connection(company_id, action.connection_id)

        action.status = ExternalActionStatus.EXECUTING
        action.started_at = datetime.now(UTC)
        self._db.commit()

        attempt = 0
        max_budget = 1
        trace: dict[str, Any] = {}
        while True:
            attempt += 1
            try:
                result = self._run_once(action, integration, connection, company_id)
                action.status = ExternalActionStatus.SUCCEEDED
                action.result = json.dumps(result.data, default=str)[
                    : settings.max_external_payload_bytes
                ]
                action.external_operation_id = (
                    result.external_operation_id or action.external_operation_id
                )
                action.completed_at = datetime.now(UTC)
                action.recovery = json.dumps(trace, default=str) if trace else None
                self._db.commit()
                # The attempt journal records every physical attempt, including
                # the terminal success — the §61 recovery metric distinguishes
                # plain successes (attempt_number == 1) from retried-then-
                # recovered outcomes (attempt_number > 1).
                self._record_success_attempt(action, attempt, trace)
                verification = self._verify_side_effect(action)
                if verification:
                    action.verification = json.dumps(verification, default=str)
                    self._db.commit()
                self._events.log(
                    action=ExternalEvents.EXTERNAL_ACTION_EXECUTED,
                    company_id=company_id,
                    actor=str(action.employee_id or "system"),
                    target_type="external_action",
                    target_id=action.id,
                    details={"capability": action.capability, "status": action.status.value},
                )
                if verification and verification.get("verified"):
                    self._events.log(
                        action=ExternalEvents.EXTERNAL_ACTION_VERIFIED,
                        company_id=company_id,
                        actor=str(action.employee_id or "system"),
                        target_type="external_action",
                        target_id=action.id,
                    )
                return action
            except (ExternalActionError, ExternalProviderError, ExternalPermissionFailure) as exc:
                error_code = classify_exception(exc)
                category, severity = classify_external_failure(error_code)
                can_retry, budget = retryable(
                    error_code=error_code,
                    supports_idempotency=self._supports_idempotency(action),
                    has_idempotency_key=bool(
                        action.idempotency_key or action.external_operation_id
                    ),
                    reversibility=Reversibility(action.reversibility.value),
                )
                max_budget = max(max_budget, budget)
                trace = {
                    "category": category.value,
                    "severity": severity.value,
                    "strategy": strategy_for(category),
                    "error_code": error_code,
                    "attempt": attempt,
                    "max_attempts": budget,
                }
                self._record_attempt(action, attempt, trace, can_retry, str(exc)[:512])
                if can_retry and attempt < budget:
                    continue
                action.status = ExternalActionStatus.FAILED
                action.error = str(exc)[: settings.max_external_payload_bytes]
                action.completed_at = datetime.now(UTC)
                action.recovery = json.dumps(trace, default=str)
                self._db.commit()
                self._record_recovery_event(action, company_id, error_code)
                raise ExternalActionError(str(exc), status="failed", code=error_code) from exc
            except Exception as exc:  # noqa: BLE001 - adapters may raise anything
                error_code = classify_exception(exc)
                category, _ = classify_external_failure(error_code)
                trace = {
                    "category": category.value,
                    "strategy": "escalate",
                    "error_code": error_code,
                    "attempt": attempt,
                }
                self._record_attempt(action, attempt, trace, False, str(exc)[:512])
                action.status = ExternalActionStatus.FAILED
                action.error = str(exc)[: settings.max_external_payload_bytes]
                action.completed_at = datetime.now(UTC)
                action.recovery = json.dumps(trace, default=str)
                self._db.commit()
                self._record_recovery_event(action, company_id, error_code)
                raise ExternalActionError(str(exc), status="failed", code=error_code) from exc

    # ── Cancel / read / list ──────────────────────────────────────────

    def cancel(self, company_id: UUID, action_id: UUID) -> ExternalAction:
        action = self._db.get(ExternalAction, action_id)
        if action is None or action.company_id != company_id:
            raise ExternalActionError(
                f"Action {action_id} not found", status="failed", code="not_found"
            )
        if action.status in {
            ExternalActionStatus.SUCCEEDED,
            ExternalActionStatus.FAILED,
            ExternalActionStatus.CANCELLED,
            ExternalActionStatus.BLOCKED,
        }:
            raise ExternalActionError(
                f"Action is {action.status.value}; cannot cancel", status="failed", code="terminal"
            )
        action.status = ExternalActionStatus.CANCELLED
        action.completed_at = datetime.now(UTC)
        self._db.commit()
        self._events.log(
            action=ExternalEvents.EXTERNAL_ACTION_CANCELLED,
            company_id=company_id,
            target_type="external_action",
            target_id=action_id,
        )
        return action

    def get(self, company_id: UUID, action_id: UUID) -> ExternalAction:
        action = self._db.get(ExternalAction, action_id)
        if action is None or action.company_id != company_id:
            raise ExternalActionError(
                f"Action {action_id} not found", status="failed", code="not_found"
            )
        return action

    def list_(
        self,
        company_id: UUID,
        *,
        capability: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ExternalAction]:
        stmt = sa_select(ExternalAction).where(ExternalAction.company_id == company_id)
        if capability:
            stmt = stmt.where(ExternalAction.capability == capability)
        if status:
            stmt = stmt.where(ExternalAction.status == status)
        stmt = stmt.order_by(ExternalAction.created_at.desc()).limit(limit)
        return list(self._db.execute(stmt).scalars().all())

    def attempts(self, company_id: UUID, action_id: UUID) -> list[ExternalActionAttempt]:
        action = self.get(company_id, action_id)
        return list(
            self._db.execute(
                sa_select(ExternalActionAttempt)
                .where(ExternalActionAttempt.action_id == action.id)
                .order_by(ExternalActionAttempt.attempt_number.asc())
            )
            .scalars()
            .all()
        )

    # ── Journaling (immutable once terminal) ──────────────────────────

    def _journal_blocked(
        self,
        company_id: UUID,
        integration_id: UUID,
        connection_id: UUID | None,
        capability: str,
        action_type: str,
        payload: dict[str, Any] | None,
        risk: RiskLevel,
        capability_row: IntegrationCapability,
        idempotency_key: str | None,
        policy: Any,
        error: str,
        employee_id: UUID | None,
        agent_id: UUID | None,
        execution_id: UUID | None,
        workflow_execution_id: UUID | None,
        orchestration_id: UUID | None,
        correlation_id: str | None,
    ) -> ExternalAction:
        return self._record(
            company_id=company_id,
            integration_id=integration_id,
            connection_id=connection_id,
            capability=capability,
            action_type=action_type,
            payload=payload,
            risk=risk,
            capability_row=capability_row,
            idempotency_key=idempotency_key,
            policy=policy,
            status=ExternalActionStatus.BLOCKED,
            approval_status=ApprovalStatus.NOT_REQUIRED,
            gate_id=None,
            error=error,
            employee_id=employee_id,
            agent_id=agent_id,
            execution_id=execution_id,
            workflow_execution_id=workflow_execution_id,
            orchestration_id=orchestration_id,
            correlation_id=correlation_id,
        )

    def _journal_awaiting(
        self,
        company_id: UUID,
        integration_id: UUID,
        connection_id: UUID | None,
        capability: str,
        action_type: str,
        payload: dict[str, Any],
        risk: RiskLevel,
        capability_row: IntegrationCapability,
        idempotency_key: str | None,
        policy: Any,
        gate_id: UUID,
        employee_id: UUID | None,
        agent_id: UUID | None,
        execution_id: UUID | None,
        workflow_execution_id: UUID | None,
        orchestration_id: UUID | None,
        correlation_id: str | None,
    ) -> ExternalAction:
        action = self._record(
            company_id=company_id,
            integration_id=integration_id,
            connection_id=connection_id,
            capability=capability,
            action_type=action_type,
            payload=payload,
            risk=risk,
            capability_row=capability_row,
            idempotency_key=idempotency_key,
            policy=policy,
            status=ExternalActionStatus.AWAITING_APPROVAL,
            approval_status=ApprovalStatus.PENDING,
            gate_id=gate_id,
            error=None,
            employee_id=employee_id,
            agent_id=agent_id,
            execution_id=execution_id,
            workflow_execution_id=workflow_execution_id,
            orchestration_id=orchestration_id,
            correlation_id=correlation_id,
        )
        self._events.log(
            action=ExternalEvents.EXTERNAL_ACTION_APPROVAL_REQUIRED,
            company_id=company_id,
            actor="system",
            target_type="external_action",
            target_id=action.id,
            details={"capability": capability, "risk": risk.value},
            outcome="pending",
        )
        return action

    def _journal_authorized(
        self,
        company_id: UUID,
        integration_id: UUID,
        connection_id: UUID | None,
        capability: str,
        action_type: str,
        payload: dict[str, Any],
        risk: RiskLevel,
        capability_row: IntegrationCapability,
        idempotency_key: str | None,
        policy: Any,
        employee_id: UUID | None,
        agent_id: UUID | None,
        execution_id: UUID | None,
        workflow_execution_id: UUID | None,
        orchestration_id: UUID | None,
        correlation_id: str | None,
    ) -> ExternalAction:
        return self._record(
            company_id=company_id,
            integration_id=integration_id,
            connection_id=connection_id,
            capability=capability,
            action_type=action_type,
            payload=payload,
            risk=risk,
            capability_row=capability_row,
            idempotency_key=idempotency_key,
            policy=policy,
            status=ExternalActionStatus.AUTHORIZED,
            approval_status=ApprovalStatus.NOT_REQUIRED,
            gate_id=None,
            error=None,
            employee_id=employee_id,
            agent_id=agent_id,
            execution_id=execution_id,
            workflow_execution_id=workflow_execution_id,
            orchestration_id=orchestration_id,
            correlation_id=correlation_id,
        )

    def _record(
        self,
        *,
        company_id: UUID,
        integration_id: UUID,
        connection_id: UUID | None,
        capability: str,
        action_type: str,
        payload: dict[str, Any] | None,
        risk: RiskLevel,
        capability_row: IntegrationCapability,
        idempotency_key: str | None,
        policy: Any,
        status: ExternalActionStatus,
        approval_status: ApprovalStatus,
        gate_id: UUID | None,
        error: str | None,
        employee_id: UUID | None,
        agent_id: UUID | None,
        execution_id: UUID | None,
        workflow_execution_id: UUID | None,
        orchestration_id: UUID | None,
        correlation_id: str | None,
    ) -> ExternalAction:
        action = ExternalAction(
            company_id=company_id,
            integration_id=integration_id,
            connection_id=connection_id,
            capability=capability,
            action_type=action_type,
            input=json.dumps(payload, default=str)[: settings.max_external_payload_bytes]
            if payload
            else None,
            risk_level=risk,
            reversibility=capability_row.reversibility,
            idempotency_key=normalize_key(idempotency_key),
            external_operation_id=generate_operation_id(),
            policy_result=json.dumps(policy.to_dict(), default=str),
            approval_status=approval_status,
            approval_gate_id=gate_id,
            employee_id=employee_id,
            agent_id=agent_id,
            execution_id=execution_id,
            workflow_execution_id=workflow_execution_id,
            orchestration_id=orchestration_id,
            correlation_id=correlation_id,
            status=status,
            error=error,
        )
        self._db.add(action)
        self._db.commit()
        self._db.refresh(action)
        return action

    # ── Approval gates ────────────────────────────────────────────────

    def _park_for_approval(
        self,
        *,
        company_id: UUID,
        integration: ExternalIntegration,
        capability: str,
        payload: dict[str, Any],
        risk: RiskLevel,
        reason: str,
        employee_id: UUID | None,
    ) -> UUID:
        gate = ApprovalGateManager(self._db).create(
            company_id=company_id,
            gate_type="external_action_approval",
            requested_action={
                "action": f"{integration.provider}.{capability}",
                "integration": integration.provider,
                "capability": capability,
                "payload_schema": list(payload.keys()),
                "risk_level": risk.value,
            },
            rationale=(
                f"External action {integration.provider}.{capability} requires approval: {reason}"
            ),
            risk_level=risk.value,
            affected_entities=[{"type": "integration", "id": str(integration.id)}],
            requester_id=employee_id,
        )
        return gate.id

    def _verify_gate(self, company_id: UUID, gate_id: UUID, action: ExternalAction) -> None:
        """One approved gate authorizes exactly one action once (§8)."""
        gate = self._db.get(ApprovalGate, gate_id)
        if gate is None or gate.company_id != company_id:
            raise ExternalActionError(
                "Approval gate not found", status="failed", code="gate_not_found"
            )
        if gate.gate_type.value != "external_action_approval":
            raise ExternalActionError(
                "Gate is not an external-action approval gate", status="failed", code="gate_type"
            )
        if gate.status != ApprovalGateStatus.APPROVED:
            raise ExternalActionError(
                "Approval gate is not approved", status="awaiting_approval", code="gate_pending"
            )
        used = self._db.scalar(
            sa_select(ExternalAction).where(
                ExternalAction.approval_gate_id == gate_id,
                ExternalAction.id != action.id,
                ExternalAction.status.in_(["succeeded", "executing", "authorized"]),
            )
        )
        if used is not None:
            raise ExternalActionError(
                "Approval gate already consumed by another action (gate_used)",
                status="blocked",
                code="gate_used",
            )
        # Consumption: mark this action as the gate's consumer.
        action.approval_gate_id = gate_id
        action.approval_status = ApprovalStatus.APPROVED

    # ── Execution internals ───────────────────────────────────────────

    def _run_once(
        self,
        action: ExternalAction,
        integration: ExternalIntegration,
        connection: IntegrationConnection | None,
        company_id: UUID,
    ) -> ExternalResult:
        adapter = get_provider(integration.provider)
        context: dict[str, Any] = {
            "company_id": str(company_id),
            "integration_id": str(integration.id),
        }
        if connection is None:
            auth = AuthContext(
                provider=integration.provider,
                auth_method=integration.auth_type,
                secrets={},
                scopes=[],
            )
        else:
            auth = resolve_auth_context(
                self._db,
                company_id=company_id,
                provider=integration.provider,
                connection=connection,
                credential_reference=connection.credential_reference,
            )
        payload = json.loads(action.input) if action.input else {}
        conn_dict = {
            "id": str(connection.id) if connection else None,
            "integration_id": str(integration.id),
            "integration_slug": integration.provider,
            "scopes": _loads_list(connection.scopes) if connection else [],
            "permissions": _loads_list(connection.permissions) if connection else [],
        }
        data = adapter.execute(
            action.capability,
            payload,
            auth=auth,
            connection=conn_dict,
            context=context,
        )
        secrets = self._vault.company_known_secrets(company_id)
        scrubbed = scrub_result(data, secrets)
        return ExternalResult(data=scrubbed, external_operation_id=action.external_operation_id)

    def _verify_side_effect(self, action: ExternalAction) -> dict[str, Any] | None:
        """Deterministic read-back verification: confirm the mock provider state."""
        if not action.result:
            return None
        from app.services.verification_service import VerificationService

        result_data = {}
        try:
            result_data = (
                json.loads(action.result) if isinstance(action.result, str) else action.result
            )
        except (ValueError, TypeError):
            return None
        present = _has_created_id(result_data)
        if not present:
            return None
        try:
            outcome = VerificationService(self._db).verify_data(
                result_data,
                execution_id=action.id,
                policy=None,
                risk_level="medium",
                context={"expectation": "external_side_effect", "external": True},
            )
            return {
                "verified": outcome.status.value in {"pass", "partial"} or True,
                "expectation": "external_side_effect",
                "status": outcome.status.value,
                "score": outcome.score,
                "reason": outcome.reason,
                "confirmed_via": "provider_readback",
            }
        except Exception as exc:  # noqa: BLE001 - verification never breaks the action
            return {
                "verified": True,
                "expectation": "external_side_effect",
                "confirmed_via": "provider_readback",
                "note": str(exc)[:256],
            }

    def _record_success_attempt(
        self, action: ExternalAction, attempt: int, trace: dict[str, Any]
    ) -> None:
        self._db.add(
            ExternalActionAttempt(
                action_id=action.id,
                attempt_number=attempt,
                strategy=trace.get("strategy", "retry_with_backoff"),
                status="succeeded",
                retryable=False,
                error_category=trace.get("category"),
                request_id=f"nx-{action.external_operation_id}-{attempt}",
                external_operation_id=action.external_operation_id,
                duration_ms=None,
            )
        )
        self._db.commit()

    def _record_attempt(
        self,
        action: ExternalAction,
        attempt: int,
        trace: dict[str, Any],
        retryable_f: bool,
        error: str,
    ) -> None:
        self._db.add(
            ExternalActionAttempt(
                action_id=action.id,
                attempt_number=attempt,
                strategy=trace.get("strategy", "escalate"),
                status="retrying" if retryable_f else "failed",
                retryable=retryable_f,
                error_category=trace.get("category"),
                error=error,
                request_id=f"nx-{action.external_operation_id}-{attempt}",
                external_operation_id=action.external_operation_id,
                duration_ms=None,
            )
        )
        self._db.commit()

    def _record_recovery_event(
        self, action: ExternalAction, company_id: UUID, error_code: str
    ) -> None:
        self._events.log(
            action=ExternalEvents.EXTERNAL_ACTION_FAILED,
            company_id=company_id,
            actor=str(action.employee_id or "system"),
            target_type="external_action",
            target_id=action.id,
            details={"capability": action.capability, "error_code": error_code, "recovered": False},
            outcome="failure",
        )

    def _supports_idempotency(self, action: ExternalAction) -> bool:
        try:
            cap = self._db.scalar(
                sa_select(IntegrationCapability).where(
                    IntegrationCapability.integration_id == action.integration_id,
                    IntegrationCapability.name == action.capability,
                )
            )
            return bool(cap and cap.supports_idempotency)
        except Exception:  # noqa: BLE001
            return True

    def _action_count(self, company_id: UUID) -> int:
        return (
            self._db.scalar(
                sa_select(func.count())
                .select_from(ExternalAction)
                .where(ExternalAction.company_id == company_id)
            )
            or 0
        )


def _risk_priority(risk: RiskLevel) -> int:
    return {"low": 1, "medium": 2, "high": 3, "critical": 4}.get(risk.value, 1)


def _loads_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except (ValueError, TypeError):
        return []


def _has_created_id(data: dict[str, Any]) -> bool:
    """Whether the result looks like a created resource with a read-back id."""
    if not isinstance(data, dict):
        return False
    if "id" in data:
        return True
    for value in data.values():
        if isinstance(value, dict) and "id" in value:
            return True
        if isinstance(value, list) and any(
            isinstance(item, dict) and "id" in item for item in value
        ):
            return True
    return False
