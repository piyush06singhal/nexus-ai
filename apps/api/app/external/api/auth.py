"""Auth-context resolution for provider calls (Phase 10, §6).

Builds an :class:`AuthContext` (secrets transiently available to the adapter
only) from a connection's credential reference via the vault. The vault is the
only place a resolved secret exists; this seam never persists, logs, or returns
a secret outward. Auth failures surface as ``ExternalAuthFailure`` so the action
funnel maps them to a clean gate/error rather than a raw exception.
"""

from __future__ import annotations

import json
import time
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.external import AuthMethod, CredentialKind, IntegrationConnection
from app.external.credential import CredentialVault
from app.external.types import AuthContext, ExternalAuthFailure

# How a resolved credential value maps into the adapter's ``secrets`` dict,
# keyed by the credential *kind*. The adapter checks for these exact keys.
_SECRET_KEYS: dict[CredentialKind, str] = {
    CredentialKind.API_KEY: "api_key",
    CredentialKind.PASSWORD: "password",
    CredentialKind.TOKEN: "token",
    CredentialKind.OAUTH: "access_token",
    CredentialKind.SECRET: "secret",
}


def resolve_auth_context(
    db: Session,
    *,
    company_id: UUID,
    provider: str,
    connection: IntegrationConnection,
    credential_reference: str | None,
) -> AuthContext:
    """Resolve the transient auth context for one provider call.

    Raises :class:`ExternalAuthFailure` when a credential reference is bound but
    cannot be resolved (missing operator env var / one-shot value) so the action
    layer can react deterministically instead of failing mid-adapter.
    """
    auth_method = AuthMethod(connection.auth_method or AuthMethod.NONE.value)

    vault = CredentialVault(db)
    secrets: dict[str, Any] = {}
    if auth_method is AuthMethod.NONE:
        return AuthContext(
            provider=provider, auth_method=auth_method, secrets={}, scopes=_scopes(connection)
        )

    if not credential_reference:
        raise ExternalAuthFailure(
            f"Connection has no bound credential reference for {auth_method.value} auth"
        )

    resolved = vault.resolve(credential_reference)
    value = resolved.get("value")
    if not value:
        raise ExternalAuthFailure(
            "No resolvable secret for connection (env/one-shot missing); reference is valid but "
            "INTEGRATION_*_SECRET is not set"
        )

    credential = vault.get(company_id, credential_reference)
    kind = CredentialKind(credential.kind) if credential is not None else CredentialKind.SECRET
    secrets[_SECRET_KEYS.get(kind, "secret")] = value
    vault.mark_used(credential_reference)
    return AuthContext(
        provider=provider, auth_method=auth_method, secrets=secrets, scopes=_scopes(connection)
    )


def _scopes(connection: IntegrationConnection) -> list[str]:
    try:
        import json

        parsed = (
            json.loads(connection.scopes)
            if isinstance(connection.scopes, str)
            else connection.scopes
        )
        return list(parsed) if isinstance(parsed, list) else []
    except Exception:  # noqa: BLE001 - a malformed scopes blob degrades to []
        return []


def build_webhook_signature(
    secret: str, payload: dict[str, Any], *, timestamp: float | None = None
) -> str:
    """Build the ``t=<ts>,v1=<hmac-sha256>`` signature the webhook ingester verifies.

    The message is ``"<timestamp>." + canonical(payload)``, matching
    :func:`app.external.webhook.compute_hmac`. The payload is canonicalised with
    ``json.dumps(..., sort_keys=True, default=str)`` so both sides hash identical
    bytes regardless of key ordering or non-JSON-serialisable leaves.
    """
    from app.external.webhook import compute_hmac

    ts = int(time.time()) if timestamp is None else int(timestamp)
    payload_bytes = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    digest = compute_hmac(payload_bytes, str(secret), timestamp=str(ts))
    return f"t={ts},v1={digest}"
