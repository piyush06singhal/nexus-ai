"""Email provider — deterministic mock mailbox (Phase 10, §68/§70).

A single in-process mock mailbox keyed by integration slug makes the email
capabilities fully deterministic for tests, CI and the demo scripts (no email
server, no network). The adapter mirrors what a real provider adapter would
expose: search/read triage (LOW), draft creation (MEDIUM), and send (HIGH — an
irreversible, approval-gated capability). Real SMTP/IMAP providers are a Phase
11 hardening item behind this same protocol seam.
"""

from __future__ import annotations

from typing import Any

from app.db.models.external import (
    AuthMethod,
    IntegrationCategory,
    Reversibility,
    RiskLevel,
)
from app.external.types import (
    AuthContext,
    Capability,
    ExternalAuthFailure,
    ExternalMessage,
    ExternalNotFoundFailure,
    ExternalValidationFailure,
)

API_KEY_ENV_HINT = "INTEGRATION_EMAIL_API_KEY"

# Deterministic mock mailbox: slug -> {message_id: ExternalMessage}
# Seeded at module import so every provider instance observes the same fixture.
_MAILBOX: dict[str, dict[str, ExternalMessage]] = {}
_SENT: dict[str, list[dict[str, Any]]] = {}
_DRAFTS: dict[str, dict[str, ExternalMessage]] = {}


def _seed_mailbox(slug: str) -> None:
    if slug in _MAILBOX:
        return
    _MAILBOX[slug] = {
        "msg-001": ExternalMessage(
            id="msg-001",
            subject="Q3 campaign results",
            from_="metrics@example.com",
            to=["marketing@nexus.test"],
            body="The Q3 campaign finished with a 23% lift in click-through.",
            status="unread",
            thread_id="thr-001",
        ),
        "msg-002": ExternalMessage(
            id="msg-002",
            subject="Invoice #2041 due",
            from_="billing@example.com",
            to=["finance@nexus.test"],
            body="Invoice #2041 for platform fees is due in 7 days.",
            status="read",
            thread_id="thr-002",
        ),
    }
    _SENT[slug] = []
    _DRAFTS[slug] = {}


class EmailProvider:
    """Deterministic email adapter over a mock mailbox."""

    slug = "email"
    name = "Email"
    category = IntegrationCategory.COMMUNICATION
    auth_type = AuthMethod.API_KEY
    description = "Deterministic email adapter over a mock mailbox (Phase 10)."

    def __init__(self) -> None:
        _seed_mailbox(self.slug)

    def secrets_required(self) -> list[str]:
        return [API_KEY_ENV_HINT]

    def capabilities(self) -> list[Capability]:
        return [
            Capability(
                name="search_messages",
                description="Search the mailbox for messages matching a query.",
                capability_type="read",
                risk_level=RiskLevel.LOW,
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                },
                output_schema={"type": "array", "items": {"$ref": "message"}},
                reversibility=Reversibility.REVERSIBLE,
                supports_idempotency=True,
            ),
            Capability(
                name="get_message",
                description="Fetch a single message by id.",
                capability_type="read",
                risk_level=RiskLevel.LOW,
                input_schema={"type": "object", "properties": {"message_id": {"type": "string"}}},
                reversibility=Reversibility.REVERSIBLE,
            ),
            Capability(
                name="create_draft",
                description="Create a draft message (not sent).",
                capability_type="write",
                risk_level=RiskLevel.MEDIUM,
                input_schema={
                    "type": "object",
                    "properties": {
                        "to": {"type": "array", "items": {"type": "string"}},
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["to", "subject", "body"],
                },
                reversibility=Reversibility.PARTIALLY_REVERSIBLE,
                supports_idempotency=True,
            ),
            Capability(
                name="send_message",
                description="Send a message to external recipients. Irreversible.",
                capability_type="write",
                risk_level=RiskLevel.HIGH,
                input_schema={
                    "type": "object",
                    "properties": {
                        "to": {"type": "array", "items": {"type": "string"}},
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                        "draft_id": {"type": "string"},
                    },
                    "required": ["to", "subject", "body"],
                },
                reversibility=Reversibility.IRREVERSIBLE,
                supports_idempotency=True,
                approval_required=True,
                required_permissions=["email:send"],
                required_scopes=["email:send"],
            ),
        ]

    def test(
        self, *, payload: dict[str, Any], auth: AuthContext, context: dict[str, Any]
    ) -> tuple[str, str]:
        _require_auth(auth)
        return "connected", "Mailbox reachable (mock)."

    def execute(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        auth: AuthContext,
        connection: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        _require_auth(auth)
        if capability == "search_messages":
            return {"messages": _search(payload, self.slug)}
        if capability == "get_message":
            return {"message": _get(payload, self.slug)}
        if capability == "create_draft":
            return {"draft": _create_draft(payload, self.slug)}
        if capability == "send_message":
            return _send(payload, self.slug)
        raise ExternalValidationFailure(f"Unknown email capability {capability!r}")


def _require_auth(auth: AuthContext) -> None:
    if not auth.secrets.get("api_key"):
        raise ExternalAuthFailure("Email provider requires INTEGRATION_EMAIL_API_KEY")


def _search(payload: dict[str, Any], slug: str) -> list[dict[str, Any]]:
    query = str(payload.get("query", "")).lower()
    limit = int(payload.get("limit", 20))
    matches = []
    for message in _MAILBOX[slug].values():
        if query in message.subject.lower() or query in message.body.lower() or not query:
            matches.append(message.to_dict())
    return matches[:limit]


def _get(payload: dict[str, Any], slug: str) -> dict[str, Any]:
    message_id = str(payload.get("message_id", ""))
    message = _MAILBOX[slug].get(message_id) or _DRAFTS.get(slug, {}).get(message_id)
    if message is None:
        raise ExternalNotFoundFailure(f"Message {message_id!r} not found")
    return message.to_dict()


def _create_draft(payload: dict[str, Any], slug: str) -> dict[str, Any]:
    to = payload.get("to") or []
    subject = str(payload.get("subject", ""))
    body = str(payload.get("body", ""))
    if not to or not isinstance(to, list) or not subject or not body:
        raise ExternalValidationFailure("Draft requires to[], subject and body")
    draft_id = f"draft-{len(_DRAFTS[slug]) + 1:03d}"
    draft = ExternalMessage(
        id=draft_id,
        subject=subject,
        from_="nexus@nexus.test",
        to=[str(t) for t in to],
        body=body,
        status="draft",
    )
    _DRAFTS[slug][draft_id] = draft
    return draft.to_dict()


def _send(payload: dict[str, Any], slug: str) -> dict[str, Any]:
    to = payload.get("to") or []
    subject = str(payload.get("subject", ""))
    body = str(payload.get("body", ""))
    if not to or not isinstance(to, list) or not subject or not body:
        raise ExternalValidationFailure("Send requires to[], subject and body")
    sent_id = f"sent-{len(_SENT[slug]) + 1:04d}"
    record = {
        "id": sent_id,
        "to": [str(t) for t in to],
        "subject": subject,
        "body": body,
        "status": "sent",
    }
    _SENT[slug].append(record)
    return {"message": record}
