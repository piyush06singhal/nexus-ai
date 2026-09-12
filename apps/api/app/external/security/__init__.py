"""External security: exfiltration guard + model-context trust labels."""

from __future__ import annotations

from app.external.security.context import (
    EXTERNAL_UNTRUSTED_CONTENT,
    TRUSTED_POLICY,
    TRUSTED_SYSTEM,
    TRUSTED_USER,
    annotate_observation,
)
from app.external.security.exfiltration import (
    ExfiltrationBlockedError,
    guard_payload,
    is_payload_allowed,
)

__all__ = [
    "EXTERNAL_UNTRUSTED_CONTENT",
    "TRUSTED_POLICY",
    "TRUSTED_SYSTEM",
    "TRUSTED_USER",
    "ExfiltrationBlockedError",
    "annotate_observation",
    "guard_payload",
    "is_payload_allowed",
]
