"""Reference-only credential vault (Phase 10, §6/§7).

A credential is stored as an *opaque reference* — never the secret. The vault
records provider, kind, a masked suffix, the operator env-var hint it resolves
through, and the scopes it grants. At connect/execute time the reference is
resolved against the operator's environment (``INTEGRATION_<PROVIDER>_<NAME>_SECRET``)
or a caller-supplied one-shot value that is used once and never persisted.

This is an explicit developer-mode abstraction (documented in the phase doc);
a real secrets manager (KMS/Vault) is a Phase 11 hardening item. The guarantee
that matters and is tested: **no plaintext secret is ever written to the
database, logs, tool output, or model context** (Rule 3 / Rule 18).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.external import CredentialKind, ExternalCredential

# Module-level one-shot store: reference -> secret value. Volatile (per-process
# and per-test), used only to let dev/demo flows supply a credential without
# putting it in the DB or the environment. Never persisted anywhere.
_ONE_SHOT: dict[str, str] = {}

_REDACTED = "[REDACTED]"


def mask_secret(value: str | None) -> str:
    """Build a display-safe masked suffix (never the full secret)."""
    if not value:
        return "••••"
    if len(value) <= 4:
        return "••••"
    return "••••" + value[-4:]


def redact_text(text: str, secrets: list[str]) -> str:
    """Replace every occurrence of a known secret inside *text*."""
    out = text
    for secret in sorted((s for s in secrets if s and len(s) >= 4), key=len, reverse=True):
        out = out.replace(secret, _REDACTED)
    # Also scrub generic token-looking fragments defensively.
    out = _EAGER_PATTERN.sub(_REDACTED, out)
    return out


# Eager scrub for obvious credential patterns that may not be in the known set.
_EAGER_PATTERN = re.compile(
    r"(?i)(bearer\s+[a-z0-9_\-\.]{8,}|"
    r"api[_-]?key['\"]?\s*[:=]\s*['\"]?[a-z0-9_\-]{8,}|"
    r"secret['\"]?\s*[:=]\s*['\"]?[a-z0-9_\-]{8,}|"
    r"password['\"]?\s*[:=]\s*['\"]?[a-z0-9_\-@#$%^&*]{8,})"
)


def redact_data(value: Any, secrets: list[str]) -> Any:
    """Recursively redact every known secret from a JSON-able structure."""
    if isinstance(value, dict):
        return {k: redact_data(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_data(v, secrets) for v in value]
    if isinstance(value, str):
        return redact_text(value, secrets)
    return value


class CredentialVault:
    """Store references only; resolve secrets transiently at call time."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Registration (never the secret) ────────────────────────────────

    def create_reference(
        self,
        *,
        company_id: UUID,
        provider: str,
        kind: CredentialKind | str,
        secret_value: str | None = None,
        env_var_hint: str | None = None,
        scopes: list[str] | None = None,
        integration_id: UUID | None = None,
        connection_id: UUID | None = None,
    ) -> ExternalCredential:
        """Register a reference and (optionally) a one-shot secret.

        If ``secret_value`` is supplied it is held transiently in the volatile
        one-shot store for resolution during this process and dropped on
        restart — the DB row stores only the masked suffix + env-var hint.
        """
        ref = "nexref_" + uuid4().hex[:12]
        kind_v = CredentialKind(kind)
        credential = ExternalCredential(
            reference=ref,
            integration_id=integration_id,
            connection_id=connection_id,
            company_id=company_id,
            provider=provider,
            kind=kind_v,
            masked_value=mask_secret(secret_value),
            env_var_hint=env_var_hint,
            scopes=json.dumps(scopes or []),
        )
        self._db.add(credential)
        self._db.commit()
        self._db.refresh(credential)
        if secret_value:
            _ONE_SHOT[ref] = secret_value
        return credential

    def get(self, company_id: UUID, reference: str) -> ExternalCredential | None:
        credential = self._db.scalar(
            select(ExternalCredential).where(
                ExternalCredential.reference == reference,
                ExternalCredential.company_id == company_id,
            )
        )
        return credential

    def connection_reference(self, company_id: UUID, connection_id: UUID) -> str | None:
        """Return the credential reference bound to a connection, if any."""
        credential = self._db.scalar(
            select(ExternalCredential).where(
                ExternalCredential.connection_id == connection_id,
                ExternalCredential.company_id == company_id,
            )
        )
        return credential.reference if credential else None

    # ── Resolution (transient) ─────────────────────────────────────────

    def resolve(self, reference: str) -> dict[str, str]:
        """Resolve a reference to ``{env_var_hint: secret}``.

        Order: volatile one-shot store → operator environment. Returns an empty
        dict when neither is available. The result is used for the duration of
        a single call and never written back.
        """
        secret = _ONE_SHOT.get(reference)
        if secret is not None:
            return {"retrieved_from": "one_shot", "value": secret}
        credential = self._db.scalar(
            select(ExternalCredential).where(ExternalCredential.reference == reference)
        )
        if credential is None or not credential.env_var_hint:
            return {}
        value = os.environ.get(credential.env_var_hint)
        if value is None:
            return {}
        return {"retrieved_from": "environment", "value": value}

    def mark_used(self, reference: str | None) -> None:
        """Record last_used_at on a credential reference (no secret involved)."""
        if not reference:
            return
        from datetime import UTC, datetime

        credential = self._db.scalar(
            select(ExternalCredential).where(ExternalCredential.reference == reference)
        )
        if credential is not None:
            credential.last_used_at = datetime.now(UTC)
            self._db.commit()

    def pop_one_shot(self, reference: str) -> None:
        """Conume a one-shot secret so it cannot be reused (Rule 3 hygiene)."""
        _ONE_SHOT.pop(reference, None)

    # ── Scrub helpers ──────────────────────────────────────────────────

    def company_known_secrets(self, company_id: UUID) -> list[str]:
        """Known secret values for a company (one-shot + env-backed), for redaction."""
        refs = list(
            self._db.execute(
                select(ExternalCredential).where(ExternalCredential.company_id == company_id)
            )
            .scalars()
            .all()
        )
        values: list[str] = []
        for ref in refs:
            resolved = self.resolve(ref.reference)
            if "value" in resolved:
                values.append(resolved["value"])
        return values

    def scrub(self, data: Any, company_id: UUID) -> Any:
        """Recursively redact every known secret for the company from *data*."""
        return redact_data(data, self.company_known_secrets(company_id))

    def scrub_connection(self, reference: str, data: Any) -> Any:
        resolved = self.resolve(reference)
        secrets = [resolved["value"]] if "value" in resolved else []
        return redact_data(data, secrets)
