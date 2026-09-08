"""Structured logging foundation.

Sets up application logging with consistent, machine-parseable output.
All modules should obtain their logger via `get_logger()` rather than
`logging.getLogger()` directly, so a `service` field is always attached.
"""

import logging
import sys

from app.core.config import settings

_LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(service)s] %(name)s | %(message)s"


class _ServiceFilter(logging.Filter):
    """Attaches a stable ``service`` field to every log record."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self.service  # type: ignore[attr-defined]
        return True


def setup_logging() -> None:
    """Configure the root logger once.

    Safe to call more than once; reconfiguration leaves handlers intact.
    """
    root = logging.getLogger()

    # Avoid stacking duplicate handlers on repeated calls (tests, reload).
    if any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    handler.addFilter(_ServiceFilter("nexus-api"))

    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    # Log unhandled library loggers at a quieter level to reduce noise.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a logger for a module, namespaced under the app root."""
    return logging.getLogger(f"nexus.{name}")
