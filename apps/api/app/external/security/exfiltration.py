"""Data-exfiltration guard — classification of outgoing payloads (Phase 10).

Before any external action leaves the boundary the payload is classified
(PUBLIC → SECRET) and only permitted data travels outward. Secret/sensitive
data (credential-like strings, apparent secrets, classified fields) is
automatically blocked without an explicit policy allowance for the target
integration — the "no unsanctioned data leaves" rule (§exfiltration/§17).
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.external.credential import _EAGER_PATTERN
from app.external.types import ExternalPermissionFailure

# Data classification levels.
DATA_CLASS = ("public", "internal", "confidential", "restricted", "secret")


class DataClassification(StrEnum):
    """Classification levels for outbound payloads (§data-exfiltration).

    Public: nothing sensitive; Internal: internal identifiers/heuristic-safe;
    Confidential: business data; Restricted: financially/legally sensitive
    (SSN, card numbers, PINs) that needs explicit policy; Secret: credential-
    looking or explicitly marked secret (api keys, passwords, tokens).
    """

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    SECRET = "secret"


# Field-name signals that mark a payload as credential/secret regardless of value.
_CREDENTIAL_FIELDS = (
    "secret",
    "token",
    "oauth",
    "api_key",
    "api-key",
    "password",
    "passwd",
    "credential",
    "private_key",
    "authorization",
)

# Field-name signals that mark financially/legally sensitive data (restricted): it
# needs explicit policy to leave the boundary, but is not itself a credential.
_FINANCIAL_FIELDS = (
    "ssn",
    "pin",
    "cvv",
    "card_number",
    "card_no",
    "credit_card",
    "account_number",
    "routing_number",
)

# Minimum allowed classification for outgoing payloads by default. Operators
# can tighten per-integration via integration_policies; this is the floor.
ALLOWED_OUTBOUND_CLASS_DEFAULT = "confidential"  # restricted/secret blocked


class ExfiltrationBlockedError(ExternalPermissionFailure):
    """The outgoing payload is classified above what the boundary permits."""


def classify_data(value: Any) -> DataClassification:
    """Classify a payload (best-effort, deterministic).

    Public: nothing sensitive; Internal: internal identifiers/heuristic-safe;
    Confidential: business data; Restricted: financially/legally sensitive that
    needs explicit policy; Secret: credential-looking or marked secret.
    """
    if isinstance(value, dict):
        keys = " ".join(k.lower() for k in value)
        for field in _CREDENTIAL_FIELDS:
            if field in keys:
                return DataClassification.SECRET
        for field in _FINANCIAL_FIELDS:
            if field in keys:
                return DataClassification.RESTRICTED
        return _classify_scalar(value)
    if isinstance(value, str):
        if (
            _EAGER_PATTERN.search(value)
            or len(value) >= 24
            and _HIGH_ENTROPY_THRESHOLD.search(value)
        ):
            return DataClassification.SECRET
        return DataClassification.INTERNAL
    return DataClassification.INTERNAL


def guard_payload(
    payload: dict[str, Any],
    *,
    max_allowed: str = ALLOWED_OUTBOUND_CLASS_DEFAULT,
    allow_secret_for: set[str] | None = None,
) -> dict[str, Any]:
    """Redact or block sensitive fields before an outbound call.

    Fields classified above ``max_allowed`` are dropped from the payload unless
    explicitly allowlisted in ``allow_secret_for`` (set of field names). Returns
    the scrubbed payload; if *every* field was blocked, raises
    :class:`ExfiltrationBlockedError`.
    """
    allowlist = allow_secret_for or set()
    allowed_levels = ("public", "internal", "confidential", "restricted", "secret")
    permitted_rank = allowed_levels.index(max_allowed)
    output: dict[str, Any] = {}
    blocked = 0
    for key, value in payload.items():
        if key in allowlist:
            output[key] = value
            continue
        klass = _classify_field(key, value)
        if allowed_levels.index(klass) <= permitted_rank:
            output[key] = redact_outbound(value) if klass in {"restricted", "secret"} else value
        else:
            blocked += 1
    if blocked and not output:
        raise ExfiltrationBlockedError(
            "Outgoing payload blocked: every field is above the permitted classification"
        )
    output["_classification"] = {
        "max_allowed": max_allowed,
        "fields_scrubbed": blocked,
    }
    return output


def _classify_scalar(value: Any) -> DataClassification:
    # Non-dict structural data is treated as business/internal data.
    return DataClassification.INTERNAL


def _classify_field(key: str, value: Any) -> DataClassification:
    """Classify one outbound field, honoring the *field name* in addition to
    the value. The name itself is a strong sensitivity signal: a bare string
    ``"4111-1111-1111-1111"`` under the key ``card_number`` would otherwise
    classify as INTERNAL and sail past the guard. Key signals win, then the
    value is classified as before."""
    lowered = key.lower()
    for field in _CREDENTIAL_FIELDS:
        if field in lowered:
            return DataClassification.SECRET
    for field in _FINANCIAL_FIELDS:
        if field in lowered:
            return DataClassification.RESTRICTED
    return classify_data(value)


_HIGH_ENTROPY_THRESHOLD = re.compile(r"[A-Za-z0-9_\-\.\/+=]{40,}")


def redact_outbound(value: Any) -> Any:
    """Replace high-value contents with ellipses for outbound redaction."""
    if isinstance(value, dict):
        return {k: redact_outbound(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_outbound(v) for v in value]
    if isinstance(value, str):
        return value[:8] + "…[redacted]" if len(value) > 16 else "••••"
    return value


def is_payload_allowed(
    company_id: UUID, payload: dict[str, Any], *, max_allowed: str = ALLOWED_OUTBOUND_CLASS_DEFAULT
) -> bool:
    try:
        guard_payload(payload, max_allowed=max_allowed)
        return True
    except ExfiltrationBlockedError:
        return False
