"""External result scrubbing + structured errors (Phase 10, §8).

Every external action result is scrubbed of known secrets, capped in size, and
kept within the journal. The :func:`scrub_result` helper is the single choke
point between adapter output and any persistence/response surface.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.external.credential import redact_data


def scrub_result(data: Any, secrets: list[str], *, max_bytes: int | None = None) -> dict[str, Any]:
    """Redact secrets and cap the serialized size of an action result."""
    cap = max_bytes or settings.max_external_payload_bytes
    cleaned = redact_data(data, secrets)
    serialized = _stringify(cleaned)
    if len(serialized) > cap:
        # Drop to a bounded summary rather than failing the whole action.
        serialized = serialized[:cap]
        try:
            cleaned = json.loads(serialized)
        except json.JSONDecodeError:
            cleaned = {"_truncated": True, "preview": serialized[:1024]}
    return cleaned if isinstance(cleaned, dict) else {"result": cleaned}


def scrub_journal_json(input_data: dict[str, Any], secrets: list[str]) -> str | None:
    """Serialize action input for the journal with secrets redacted."""
    if not input_data:
        return None
    cleaned = redact_data(input_data, secrets)
    text = json.dumps(cleaned, default=str)
    if len(text) > settings.max_external_payload_bytes:
        text = text[: settings.max_external_payload_bytes]
    return text


def _stringify(value: Any) -> str:
    try:
        return json.dumps(value, default=str, ensure_ascii=False)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return str(value)


class ExternalActionError(Exception):
    """Raised when a governed external action cannot be executed.

    Carries the journal status/error so the API layer can map it to a clean 4xx.
    """

    def __init__(
        self, message: str, *, status: str = "failed", code: str = "external_error"
    ) -> None:
        self.message = message
        self.status = status
        self.code = code
        super().__init__(message)
