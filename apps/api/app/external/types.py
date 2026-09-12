"""External Integrations — domain types (Phase 10).

Transport-neutral dataclasses used between the external services. Enums are
re-exported from the ORM models (``app.db.models.external``) so there is a
single source of truth for closed value sets; only the runtime payloads live
here. Normalized external entities (§44) are plain dataclasses with ``to_dict``
so adapters and the action journal stay DB-free at the edge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.db.models.external import (  # noqa: F401  (re-exported for callers)
    ApprovalStatus,
    AuthMethod,
    BrowserActionType,
    BrowserSessionStatus,
    ComputerActionType,
    ComputerSessionStatus,
    ConnectionStatus,
    ConnectionTestResult,
    ContentType,
    CredentialKind,
    DomainDecision,
    ExternalActionStatus,
    ExternalEventSource,
    IntegrationCategory,
    IntegrationStatus,
    Reversibility,
    RiskLevel,
    ScopeType,
    SignatureStatus,
    VerificationStatusExternal,
)

# ── Capabilities / requests ──────────────────────────────────────────────────


@dataclass
class Capability:
    """A provider capability surfaced as an ``integration_capabilities`` row."""

    name: str
    description: str = ""
    capability_type: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    reversibility: Reversibility = Reversibility.REVERSIBLE
    supports_idempotency: bool = True
    approval_required: bool = False
    required_permissions: list[str] = field(default_factory=list)
    required_scopes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "capability_type": self.capability_type,
            "risk_level": self.risk_level.value,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "reversibility": self.reversibility.value,
            "supports_idempotency": self.supports_idempotency,
            "approval_required": self.approval_required,
            "required_permissions": self.required_permissions,
            "required_scopes": self.required_scopes,
        }


@dataclass
class AuthContext:
    """Resolved authentication for a single provider call (§6).

    ``secrets`` carries the resolved credential values for the duration of the
    call only — it is never persisted, logged, or returned by any API.
    """

    provider: str
    auth_method: AuthMethod
    secrets: dict[str, str] = field(default_factory=dict)
    scopes: list[str] = field(default_factory=list)


@dataclass
class ExternalActionRequest:
    """Input to the external action funnel (§2)."""

    company_id: UUID
    integration_id: UUID
    capability: str
    action_type: str = "execute"
    payload: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    connection_id: UUID | None = None
    employee_id: UUID | None = None
    agent_id: UUID | None = None
    execution_id: UUID | None = None
    workflow_execution_id: UUID | None = None
    orchestration_id: UUID | None = None
    approved_gate_id: UUID | None = None
    correlation_id: str | None = None


@dataclass
class ExternalResult:
    """Scrubbed, size-capped result of a successful external action."""

    data: dict[str, Any] = field(default_factory=dict)
    external_operation_id: str | None = None


@dataclass
class ConnectionTest:
    """Outcome of a connection test (never includes secrets)."""

    result: ConnectionTestResult
    message: str = ""
    tested_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": self.result.value,
            "message": self.message,
            "tested_at": self.tested_at,
        }


# ── External error taxonomy (maps onto Phase 6 FailureCategory via recovery) ─


class ExternalProviderError(Exception):
    """Base for provider/adapter failures during an external action.

    ``error_code`` is a short stable identifier (e.g. ``http_429``); the
    recovery layer re-classifies failures through the Phase 6 taxonomy.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "external_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.error_code = error_code
        self.details = details or {}
        super().__init__(message)


class ExternalAuthFailure(ExternalProviderError):
    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message, error_code="auth_failed")


class ExternalPermissionFailure(ExternalProviderError):
    def __init__(self, message: str = "Permission denied") -> None:
        super().__init__(message, error_code="permission_denied")


class ExternalRateLimitFailure(ExternalProviderError):
    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(message, error_code="http_429")


class ExternalTimeoutFailure(ExternalProviderError):
    def __init__(self, message: str = "External action timed out") -> None:
        super().__init__(message, error_code="timeout")


class ExternalValidationFailure(ExternalProviderError):
    def __init__(
        self, message: str = "Invalid input", details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message, error_code="validation_failed", details=details)


class ExternalNotFoundFailure(ExternalProviderError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, error_code="not_found")


class ExternalTransportFailure(ExternalProviderError):
    def __init__(self, message: str = "Transport failure") -> None:
        super().__init__(message, error_code="transport_error")


class ExternalSystemFailure(ExternalProviderError):
    def __init__(self, message: str = "External system failure") -> None:
        super().__init__(message, error_code="system_error")


# ── Normalized external entities (§44) ───────────────────────────────────────


@dataclass
class ExternalUser:
    """A normalized user handle from an external system."""

    id: str
    name: str
    email: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "email": self.email}


@dataclass
class ExternalMessage:
    """A normalized message (email)."""

    id: str
    subject: str
    from_: str
    to: list[str] = field(default_factory=list)
    body: str = ""
    status: str = "read"
    thread_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "subject": self.subject,
            "from": self.from_,
            "to": self.to,
            "body": self.body,
            "status": self.status,
            "thread_id": self.thread_id,
        }


@dataclass
class ExternalCalendarEvent:
    """A normalized calendar event."""

    id: str
    title: str
    start: str
    end: str
    status: str = "confirmed"
    attendees: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "start": self.start,
            "end": self.end,
            "status": self.status,
            "attendees": self.attendees,
            "notes": self.notes,
        }


@dataclass
class ExternalIssue:
    """A normalized issue/ticket."""

    id: str
    title: str
    state: str = "open"
    repository: str = ""
    number: int = 0
    body: str = ""
    labels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "state": self.state,
            "repository": self.repository,
            "number": self.number,
            "body": self.body,
            "labels": self.labels,
        }


@dataclass
class ExternalDocument:
    """A normalized document."""

    id: str
    name: str
    mime_type: str = "text/plain"
    size_bytes: int = 0
    uri: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "uri": self.uri,
        }


@dataclass
class ExternalRecord:
    """A normalized data record (CRM/database row)."""

    id: str
    object_type: str
    fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "object_type": self.object_type, "fields": self.fields}


@dataclass
class ExternalFile:
    """A normalized file within the Phase 10 files workspace."""

    path: str
    name: str
    mime_type: str = "text/plain"
    size_bytes: int = 0
    workspace: str = "virtual"

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "name": self.name,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "workspace": self.workspace,
        }


# ── Structured observations (prompt-injection boundary, §65) ─────────────────


@dataclass
class ExternalObservation:
    """A size-limited structured observation of an external surface.

    Every external-originated observation is labelled
    ``content_type=EXTERNAL_UNTRUSTED_CONTENT`` so the model-context builder
    (and every consumer) treats it as data, never as instruction.
    """

    content_type: ContentType
    url: str | None = None
    title: str | None = None
    snapshot: dict[str, Any] = field(default_factory=dict)
    screenshot_ref: str | None = None
    page_state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_type": self.content_type.value,
            "url": self.url,
            "title": self.title,
            "snapshot": self.snapshot,
            "screenshot_ref": self.screenshot_ref,
            "page_state": self.page_state,
        }
