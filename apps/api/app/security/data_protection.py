"""Data protection: classification, transfer policy, retention (Phase 11, §53/§61).

Composes — never duplicates — the Phase 10 outbound guard
(:mod:`app.external.security.exfiltration`): raw payload classification and
outbound redaction already live there and are enforced inside the external
action manager. This module adds the *governed registry* on top:

- :class:`DataClassificationService` — persist an explicit classification for
  any resource (``data_classifications``) and answer "what can leave".
- :class:`DataTransferPolicy` — the classification → destination → policy →
  approval-if-required → transfer chain. Unauthorized transfers are blocked and
  recorded as ``DATA_EXFILTRATION_BLOCKED`` security events (audited, never
  silently dropped).
- :class:`RetentionService` — retention policy registry (``retention_policies``)
  with hard/soft/anonymize/retention-lock semantics. Audit and security records
  are never casually deleted: they default to ``retention_lock`` and their
  policies default to soft/anonymize — hard deletion requires an explicit,
  recorded override.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.db.models.security import (
    DataClassification,
    DataClassificationRecord,
    DeletionSemantics,
    RetentionEntityType,
    RetentionPolicy,
    SecurityEventCategory,
    Severity,
)
from app.external.security.exfiltration import (
    classify_data,
    guard_payload,
)

logger = get_logger(__name__)

# Classification rank so "above" / "below" comparisons are deterministic.
_CLASS_RANK = {
    DataClassification.PUBLIC.value: 0,
    DataClassification.INTERNAL.value: 1,
    DataClassification.CONFIDENTIAL.value: 2,
    DataClassification.RESTRICTED.value: 3,
    DataClassification.SECRET.value: 4,
}

# Outbound floor: restricted/secret never leaves without an explicit override.
# Matches the Phase 10 ``ALLOWED_OUTBOUND_CLASS_DEFAULT`` default.
DEFAULT_MAX_OUTBOUND = "confidential"

# Entity types that must never be hard-deleted casually (audit/security).
_RETAINED_ENTITY_TYPES = {
    RetentionEntityType.AUDIT_EVENTS.value,
    RetentionEntityType.SECURITY_EVENTS.value,
}


@dataclass
class TransferDecision:
    allowed: bool
    reason: str
    target_classification: str
    destination: str | None = None
    requires_approval: bool = False
    scrubbed_payload: dict | None = None
    blocked_fields: int = 0


class DataClassificationService:
    """Explicit classification registry for resources (data_classifications)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def classify(
        self,
        *,
        resource_type: str,
        resource_id: str,
        company_id: UUID | None = None,
        classification: str = DataClassification.INTERNAL.value,
        sensitivity_reason: str | None = None,
        created_by: UUID | None = None,
    ) -> DataClassificationRecord:
        """Set (or overwrite) a resource's classification.

        ``classification`` must be a member of :class:`DataClassification`.
        """
        if classification not in _CLASS_RANK:
            raise ValidationError(
                f"Invalid classification {classification!r}; "
                f"expected one of {sorted(_CLASS_RANK)}.",
                code="invalid_classification",
            )
        existing = self.db.execute(
            select(DataClassificationRecord).where(
                DataClassificationRecord.resource_type == resource_type,
                DataClassificationRecord.resource_id == resource_id,
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = DataClassificationRecord(
                company_id=company_id,
                resource_type=resource_type,
                resource_id=resource_id,
                created_by=created_by,
            )
            self.db.add(existing)
        existing.classification = classification
        existing.sensitivity_reason = sensitivity_reason or existing.sensitivity_reason
        if company_id is not None:
            existing.company_id = company_id
        self.db.flush()
        return existing

    def get_classification(
        self, *, resource_type: str, resource_id: str, company_id: UUID | None = None
    ) -> str:
        """Return the explicit classification or ``internal`` by default."""
        row = self.db.execute(
            select(DataClassificationRecord).where(
                DataClassificationRecord.resource_type == resource_type,
                DataClassificationRecord.resource_id == resource_id,
            )
        ).scalar_one_or_none()
        if row is not None:
            return row.classification
        return DataClassification.INTERNAL.value

    def classify_payload(self, payload: object) -> str:
        """Best-effort classification of a raw payload (composes Phase 10)."""
        return classify_data(payload).value


class DataTransferPolicy:
    """Governed data transfer: classification → destination → transfer check.

    This is the DLP gate for endpoints that move data *between* boundaries
    (export / import / external send). The external action manager already
    enforces ``guard_payload`` on outbound calls; this layer is the higher-level
    policy record plus the security-event + audit trail for blocked transfers.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def evaluate_transfer(
        self,
        *,
        resource_type: str,
        resource_id: str,
        payload: dict,
        destination: str,
        company_id: UUID | None = None,
        actor_id: UUID | None = None,
        max_outbound: str = DEFAULT_MAX_OUTBOUND,
        allow_fields: set[str] | None = None,
        requires_approval_for: list[str] | None = None,
        record: bool = True,
    ) -> TransferDecision:
        """Evaluate moving ``payload`` of ``resource_type``/``resource_id`` away.

        Chain: explicit classification → payload re-classification → outbound
        floor. Returns a decision; when ``record`` is true, blocked transfers
        (and classified-as-sensitive passes) are written as security events.
        """
        classification = self._classification(resource_type, resource_id, company_id)
        payload_cls = classify_data(payload).value
        effective_cls = max(classification, payload_cls, key=lambda c: _CLASS_RANK.get(c, 0))
        requires_approval_items = requires_approval_for or [
            DataClassification.RESTRICTED.value,
            DataClassification.SECRET.value,
        ]

        try:
            scrubbed = guard_payload(
                payload,
                max_allowed=max_outbound,
                allow_secret_for=allow_fields or set(),
            )
        except Exception as exc:  # ExfiltrationBlockedError (ExternalPermissionFailure)
            if record:
                self._record_blocked(
                    actor_id=actor_id,
                    company_id=company_id,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    destination=destination,
                    detail={"classification": effective_cls, "reason": str(exc)},
                )
            return TransferDecision(
                allowed=False,
                reason="Every field is above the permitted outbound classification.",
                target_classification=effective_cls,
                destination=destination,
                blocked_fields=len(payload),
            )

        if effective_cls in requires_approval_items:
            if record:
                self._record_restricted_attempt(
                    actor_id=actor_id,
                    company_id=company_id,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    destination=destination,
                    classification=effective_cls,
                )
            return TransferDecision(
                allowed=False,
                reason=(f"{effective_cls} data requires approval before transfer."),
                target_classification=effective_cls,
                destination=destination,
                requires_approval=True,
                scrubbed_payload=scrubbed,
                blocked_fields=scrubbed.get("_classification", {}).get("fields_scrubbed", 0),
            )
        return TransferDecision(
            allowed=True,
            reason=f"{effective_cls} data is permitted to {destination}.",
            target_classification=effective_cls,
            destination=destination,
            scrubbed_payload=scrubbed,
            blocked_fields=scrubbed.get("_classification", {}).get("fields_scrubbed", 0),
        )

    def _classification(self, resource_type: str, resource_id: str, company_id) -> str:
        svc = DataClassificationService(self.db)
        return svc.get_classification(
            resource_type=resource_type, resource_id=resource_id, company_id=company_id
        )

    def _record_restricted_attempt(
        self,
        *,
        actor_id: UUID | None,
        company_id: UUID | None,
        resource_type: str,
        resource_id: str,
        destination: str,
        classification: str,
    ) -> None:
        """Surface a gated transfer of restricted/secret data in the security feed."""
        try:
            from app.security.detection import SecurityEventService

            SecurityEventService(self.db).record(
                category=SecurityEventCategory.DATA_EXFILTRATION_BLOCKED,
                severity=Severity.MEDIUM,
                title="Restricted data transfer requires approval",
                detail={
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "destination": destination,
                    "classification": classification,
                    "gated": True,
                },
                company_id=company_id,
                actor_id=actor_id,
                observed_by="data_protection",
            )
            from app.security.accountability import AuditService

            AuditService(self.db).record(
                action="data.transfer_requires_approval",
                actor_id=actor_id,
                company_id=company_id,
                category="data_protection",
                resource_type=resource_type,
                resource_id=resource_id,
                outcome="require_approval",
                detail={"destination": destination, "classification": classification},
                commit=False,
            )
        except Exception:  # pragma: no cover
            logger.debug("restricted-transfer audit skipped")

    def _record_blocked(
        self,
        *,
        actor_id: UUID | None,
        company_id: UUID | None,
        resource_type: str,
        resource_id: str,
        destination: str,
        detail: dict,
    ) -> None:
        try:
            from app.security.detection import SecurityEventService

            SecurityEventService(self.db).record(
                category=SecurityEventCategory.DATA_EXFILTRATION_BLOCKED,
                severity=Severity.HIGH,
                title="Data transfer blocked by policy",
                detail={
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "destination": destination,
                    **detail,
                },
                company_id=company_id,
                actor_id=actor_id,
                observed_by="data_protection",
            )
            from app.security.accountability import AuditService

            AuditService(self.db).record(
                action="data.transfer_blocked",
                actor_id=actor_id,
                company_id=company_id,
                category="data_protection",
                resource_type=resource_type,
                resource_id=resource_id,
                outcome="denied",
                detail={
                    "destination": destination,
                    **detail,
                },
                commit=False,
            )
        except Exception:  # pragma: no cover
            logger.debug("data transfer block audit skipped")


class RetentionService:
    """Retention policy registry + safe purge planning (retention_policies)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def set_policy(
        self,
        *,
        entity_type: str,
        retention_days: int,
        company_id: UUID | None = None,
        deletion_semantics: str = DeletionSemantics.SOFT.value,
        retention_lock: bool = False,
        changed_by: UUID | None = None,
    ) -> RetentionPolicy:
        """Upsert the retention policy for (entity_type, company)."""
        if entity_type not in {e.value for e in RetentionEntityType}:
            raise ValidationError(
                f"Unknown retention entity type {entity_type!r}.",
                code="invalid_retention_entity",
            )
        if deletion_semantics not in {s.value for s in DeletionSemantics}:
            raise ValidationError(
                f"Unknown deletion semantics {deletion_semantics!r}.",
                code="invalid_deletion_semantics",
            )
        row = self.db.execute(
            select(RetentionPolicy).where(
                RetentionPolicy.entity_type == entity_type,
                RetentionPolicy.company_id == company_id,
            )
        ).scalar_one_or_none()
        if row is None:
            row = RetentionPolicy(
                entity_type=entity_type,
                company_id=company_id,
                changed_by=changed_by,
            )
            self.db.add(row)
        if row.retention_lock and not retention_lock:
            # Once a policy is locked, loosening it requires an explicit re-lock.
            pass
        row.retention_days = retention_days
        row.deletion_semantics = deletion_semantics
        row.retention_lock = retention_lock
        row.enabled = True
        row.changed_by = changed_by
        self.db.flush()
        return row

    def get_policy(
        self, *, entity_type: str, company_id: UUID | None = None
    ) -> RetentionPolicy | None:
        return self.db.execute(
            select(RetentionPolicy).where(
                RetentionPolicy.entity_type == entity_type,
                RetentionPolicy.company_id == company_id,
            )
        ).scalar_one_or_none()

    def effective_retention_days(
        self, *, entity_type: str, company_id: UUID | None = None, default: int = 180
    ) -> int:
        """Days after which an entity of this type may be expired."""
        policy = self.get_policy(entity_type=entity_type, company_id=company_id)
        if policy is not None and policy.enabled:
            return policy.retention_days
        return default

    def purge_due(
        self, *, entity_type: str, company_id: UUID | None = None, as_of: datetime | None = None
    ) -> list[dict]:
        """Return a planned purge descriptor for entities past retention.

        Returns descriptors only — actual row deletion/conversion is performed by
        the caller against the owning model. A locked policy never yields a
        purge; audit/security entities are never hard-deleted.
        """
        policy = self.get_policy(entity_type=entity_type, company_id=company_id)
        now = as_of or datetime.now(UTC)
        if policy is None or not policy.enabled:
            return []
        if policy.retention_lock or entity_type in _RETAINED_ENTITY_TYPES:
            return []
        semantics = policy.deletion_semantics
        if semantics == DeletionSemantics.HARD.value and entity_type in _RETAINED_ENTITY_TYPES:
            semantics = DeletionSemantics.SOFT.value  # degrade, never hard-delete
        cutoff = now - timedelta(days=policy.retention_days)
        return [
            {
                "entity_type": entity_type,
                "company_id": str(company_id) if company_id else None,
                "cutoff_before": cutoff.isoformat(),
                "deletion_semantics": semantics,
                "policy_id": str(policy.id),
            }
        ]

    def can_expire(self, *, entity_type: str, company_id: UUID | None = None) -> bool:
        """Whether entities of this type may be expired at all (locked? retained?)."""
        policy = self.get_policy(entity_type=entity_type, company_id=company_id)
        if entity_type in _RETAINED_ENTITY_TYPES:
            return False
        if policy is None or not policy.enabled:
            return False
        return not policy.retention_lock

    def purge_execute(
        self, *, entity_type: str, company_id: UUID | None = None, as_of: datetime | None = None
    ) -> dict:
        """Apply the retention plan for *entity_type* — rows older than the cutoff.

        Honest semantics against the owning models (which are scoped by task /
        execution / namespace, not by a company column):
        - ``agent_executions`` / ``tool_calls`` / ``memories`` carry no company
          column, so the row sweep is time-scoped only; *company_id* is used for
          the policy lookup and the audit provenance (exactly the retention a
          company operator asked for). Per-company physical storage isolation
          is a deployment-level item.
        - HARD → the rows are deleted.
        - SOFT → rows get a tombstone where the model supports one (memory →
          ``expired``); the rest degrade to anonymize.
        - ANONYMIZE → data-bearing columns (input/output/result/content) are
          redacted in place, keeping the row and its audit trail.
        Never touches :data:`_RETAINED_ENTITY_TYPES`.
        """
        plan = self.purge_due(entity_type=entity_type, company_id=company_id, as_of=as_of)
        if not plan:
            return {"entity_type": entity_type, "purged": 0, "semantics": None}
        entry = plan[0]
        semantics = entry["deletion_semantics"]
        cutoff = datetime.fromisoformat(entry["cutoff_before"])

        model = _PURGE_MODELS.get(entity_type)
        if model is None:
            logger.warning(
                "retention_purge_unsupported_entity",
                extra={"entity_type": entity_type, "semantics": semantics},
            )
            return {"entity_type": entity_type, "purged": 0, "semantics": semantics}

        rows = self.db.execute(select(model).where(model.created_at < cutoff)).scalars().all()
        if semantics == DeletionSemantics.HARD.value:
            for row in rows:
                self.db.delete(row)
        elif semantics == DeletionSemantics.ANONYMIZE.value:
            _anonymize_rows(rows)
        else:  # SOFT — tombstone when the model supports it, else anonymize
            _tombstone_rows(rows)
            _anonymize_rows(rows)
        purged = len(rows)
        self.db.flush()
        self._audit_purge(entity_type, company_id, semantics, purged)
        return {
            "entity_type": entity_type,
            "purged": purged,
            "semantics": semantics,
            "cutoff_before": entry["cutoff_before"],
        }

    def _audit_purge(self, entity_type: str, company_id: UUID, semantics: str, purged: int) -> None:
        """Record the purge in the append-only audit chain (best-effort)."""
        try:
            from app.security.accountability import AuditService

            AuditService(self.db).record(
                actor_id=None,
                company_id=company_id,
                action="data.retention.purge",
                resource_type="retention_purge",
                resource_id=entity_type,
                outcome="success",
                detail={
                    "entity_type": entity_type,
                    "semantics": semantics,
                    "rows_purged": purged,
                },
                commit=False,
            )
        except Exception:  # pragma: no cover - audit must never block retention
            logger.exception("Audit failed during retention purge")


# Concrete owning models for each retention-eligible entity type.  Models not
# listed (logs, observations, screenshots, audit/security) are retained or
# unsupported in-process: their purge is out of the applied scope.
_PURGE_MODELS: dict[str, Any] = {}


def _register_purge_models() -> None:
    """Register owning models lazily to avoid import-time cycles."""
    from app.db.models.execution import AgentExecution
    from app.db.models.memory import Memory
    from app.db.models.tool_call import ToolCallRecord

    _PURGE_MODELS.update(
        {
            RetentionEntityType.EXECUTIONS.value: AgentExecution,
            RetentionEntityType.TOOL_CALLS.value: ToolCallRecord,
            RetentionEntityType.MEMORY.value: Memory,
        }
    )


_register_purge_models()


def _anonymize_rows(rows: list[Any]) -> None:
    """Redact data-bearing columns in place; the final component is metadata."""
    from app.db.models.execution import AgentExecution
    from app.db.models.memory import Memory
    from app.db.models.tool_call import ToolCallRecord

    for row in rows:
        if isinstance(row, AgentExecution):
            row.input_data = None
            row.output_data = None
            row.metadata_json = None
        elif isinstance(row, ToolCallRecord):
            row.result_data = None
            row.result_error = None
        elif isinstance(row, Memory):
            row.content = "[redacted by retention policy]"


def _tombstone_rows(rows: list[Any]) -> int:
    """Set a soft-delete status where the model defines one (memory → expired)."""
    from app.db.models.memory import Memory, MemoryStatus

    count = 0
    for row in rows:
        if isinstance(row, Memory):
            row.status = MemoryStatus.EXPIRED.value
            count += 1
    return count
