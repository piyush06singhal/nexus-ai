"""Structured logging foundation.

Sets up application logging with consistent, machine-parseable output.
All modules should obtain their logger via `get_logger()` rather than
`logging.getLogger()` directly, so a `service` field is always attached.

Phase 11: a central :class:`RedactionFilter` scrubs PII/credentials from every
emitted record (defense in depth), and ``settings.logging_json`` selects a
JSON formatter with request/trace correlation fields.

This module never logs secrets: values are redacted before formatting.
"""

import json
import logging
import sys
import time

from app.core.config import settings

_TEXT_FORMAT = "%(asctime)s %(levelname)-8s [%(service)s] %(name)s | %(message)s"


class _ServiceFilter(logging.Filter):
    """Attaches a stable ``service`` field to every log record."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self.service  # type: ignore[attr-defined]
        return True


class _JsonFormatter(logging.Formatter):
    """One JSON object per line, with stable ordering for greppability."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "service": getattr(record, "service", "nexus"),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "trace_id", "span_id", "company_id", "identity_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class _RedactionFormatter(logging.Formatter):
    """Apply the central redactor to the final rendered line.

    ``settings.logging_json`` picks JSON; otherwise the human text format.
    Both pass through :func:`app.core.redaction.redact_text`.
    """

    def __init__(self, fmt: str | None = None) -> None:
        self._inner = _JsonFormatter() if settings.logging_json else logging.Formatter(fmt)
        super().__init__(fmt)

    def format(self, record: logging.LogRecord) -> str:
        from app.core.redaction import redact_text

        return redact_text(self._inner.format(record))


def setup_logging() -> None:
    """Configure the root logger once.

    Safe to call more than once; reconfiguration leaves handlers intact.
    """
    root = logging.getLogger()

    # Avoid stacking duplicate handlers on repeated calls (tests, reload).
    if any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_RedactionFormatter(_TEXT_FORMAT))
    handler.addFilter(_ServiceFilter("nexus-api"))
    from app.core.redaction import RedactionFilter

    handler.addFilter(RedactionFilter())

    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    # Log unhandled library loggers at a quieter level to reduce noise.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a logger for a module, namespaced under the app root."""
    return logging.getLogger(f"nexus.{name}")
