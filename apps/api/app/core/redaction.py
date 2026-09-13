"""Central redaction for PII & credentials (Phase 11, §44).

A logging formatter + a standalone ``redact_text`` that scrub secrets (AWS
keys, bearer tokens, api keys, passwords), email addresses, phone numbers and
the configured key-valued env vars. Applied centrally in ``setup_logging`` so
teams don't have to remember to redact their own messages. This is defense in
depth, never a replacement for storing secrets reference-only.
"""

from __future__ import annotations

import logging
import re

from app.core.config import settings

_KEY_VALUE_ENV = [
    "secret_encryption_key",
    "jwt_secret_key",
]

# Coverage is intentional and layered: token formats, key material, PII.
_PATTERNS: list[tuple[re.Pattern, str]] = [
    # AWS-style access keys / secret material
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[redacted:aws_access_key]"),
    (re.compile(r"-----BEGIN(?: [A-Z ]+)? PRIVATE KEY-----", re.S), "[redacted:private_key]"),
    # Bearer / api-key / sk-* tokens
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"), r"\1[redacted:bearer]"),
    (re.compile(r"\b(sk|pk)-[A-Za-z0-9_\-]{16,}\b"), "[redacted:api_key]"),
    (
        re.compile(r"\b(token|secret|password|passwd|api[_-]?key)\s*[=:]\s*\S+", re.I),
        r"\1 [redacted]",
    ),
    # PII
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I), "[redacted:email]"),
    (re.compile(r"\b(?:\+?\d{1,3}[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}\b"), "[redacted:phone]"),
    (re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"), "[redacted:card]"),
]


def _config_value_patterns() -> list[tuple[re.Pattern, str]]:
    out = []
    for attr in _KEY_VALUE_ENV:
        value = getattr(settings, attr, None)
        if value and len(str(value)) >= 8:
            out.append((re.compile(re.escape(str(value))), f"[redacted:{attr}]"))
    return out


_ALL_PATTERNS = _PATTERNS + _config_value_patterns()


def redact_text(text: str) -> str:
    """Scrub every configured pattern out of a string."""
    if not text:
        return text
    for pattern, replacement in _ALL_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _redact_value(value):
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_value(v) for v in value]
    return value


def scrubbed(record_dict: dict) -> dict:
    """Return a deep-copied, redacted dict of log extra fields."""
    return _redact_value(record_dict)


class RedactionFilter(logging.Filter):
    """Scrub message + attributes in place before a handler formats."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        record.args = _redact_value(record.args) if record.args else ()
        for attr in ("extra",):
            if hasattr(record, attr):
                setattr(record, attr, _redact_value(getattr(record, attr)))
        # Scrub the standard formatted message too (records already rendered).
        return True
