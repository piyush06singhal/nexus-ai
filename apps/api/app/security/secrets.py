"""Secrets management & encryption-at-rest (Phase 11, §58–§60).

``secrets`` stores Fernet (AES-256-GCM) ciphertext only — never plaintext.
Keys come from ``SECRET_ENCRYPTION_KEY`` (env); ``encryption_keys`` stores
only fingerprints, never key material. Rotation snapshots the current
ciphertext into a ``secret_version`` and re-encrypts; retrieve enforces
active status and logs an audit trail. Redaction composes the Phase 10
``CredentialVault.redact_text`` so plaintext never leaks into logs/tool output.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.logging import get_logger
from app.db.models.security import (
    EncryptionKey,
    EncryptionKeyStatus,
    Secret,
    SecretKind,
    SecretStatus,
    SecretVersion,
)
from app.security import crypto

logger = get_logger(__name__)


def mask_hint(plaintext: str) -> str:
    """Return a safe display hint (…last4) — never the value itself."""
    if not plaintext:
        return ""
    return f"••••{plaintext[-4:]}" if len(plaintext) > 4 else "••••"


class KeyManager:
    """Track the active encryption key id (fingerprint-based; no material stored)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def current(self) -> EncryptionKey:
        stmt = (
            select(EncryptionKey)
            .where(EncryptionKey.status == EncryptionKeyStatus.ACTIVE.value)
            .order_by(EncryptionKey.activated_at.desc())
            .limit(1)
        )
        key = self.db.execute(stmt).scalar_one_or_none()
        if key is None:
            key = self._register_current()
        return key

    def _register_current(self) -> EncryptionKey:
        """Upsert the env-derived key's fingerprint as the active EncryptionKey."""
        # The Fernet key bytes are process-local; derive fingerprint from the
        # effective key identifier (env value or ephemeral).
        configured = crypto.settings.secret_encryption_key
        material = configured or "ephemeral"  # never stored verbatim when ephemeral
        fp = crypto.fingerprint_key(material)
        key_id = crypto.generate_key_id("nexus-enc")
        existing = self.db.execute(
            select(EncryptionKey).where(EncryptionKey.fingerprint == fp)
        ).scalar_one_or_none()
        if existing is not None:
            existing.status = EncryptionKeyStatus.ACTIVE.value
            self.db.flush()
            return existing
        key = EncryptionKey(
            key_id=key_id,
            label="NEXUS fernet key",
            status=EncryptionKeyStatus.ACTIVE.value,
            fingerprint=fp,
            metadata_json={"source": "env" if configured else "ephemeral"},
        )
        self.db.add(key)
        self.db.flush()
        return key


class SecretManager:
    """Store / retrieve / rotate / revoke encrypted secrets.

    ``store`` and ``rotate`` never echo plaintext; ``retrieve`` is the only
    plaintext path and it is gated on ACTIVE status + audited.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def store(
        self,
        *,
        name: str,
        plaintext: str,
        company_id: UUID | None = None,
        kind: str = SecretKind.API_KEY.value,
        created_by: UUID | None = None,
        rotation_days: int | None = None,
    ) -> Secret:
        if not plaintext:
            raise ValueError("A secret cannot be empty.")
        key = KeyManager(self.db).current()
        ciphertext = crypto.encrypt_secret(plaintext)
        secret = Secret(
            name=name,
            company_id=company_id,
            kind=kind,
            status=SecretStatus.ACTIVE.value,
            ciphertext=ciphertext,
            key_id=key.key_id,
            mask_hint=mask_hint(plaintext),
            rotation_due_at=(
                datetime.now(UTC) + timedelta(days=rotation_days) if rotation_days else None
            ),
            created_by=created_by,
        )
        self.db.add(secret)
        self.db.flush()
        self._audit(
            "secret.store",
            secret,
            company_id,
            created_by,
            detail={"kind": kind, "rotation_days": rotation_days},
        )
        return secret

    def retrieve(
        self, secret_id: UUID, *, by: UUID | None = None, company_id: UUID | None = None
    ) -> str:
        secret = self._require(secret_id)
        if company_id is not None and secret.company_id is not None:
            if secret.company_id != company_id:
                raise PermissionDeniedError(
                    "Cross-company secret access denied.", code="secret_company_mismatch"
                )
        if secret.status != SecretStatus.ACTIVE.value:
            raise PermissionDeniedError(
                f"Secret is {secret.status} and cannot be read.", code="secret_inactive"
            )
        try:
            plaintext = crypto.decrypt_secret(secret.ciphertext)
        except Exception as exc:  # pragma: no cover - key mismatch
            raise PermissionDeniedError(
                "Secret cannot be decrypted (key mismatch).", code="secret_key_mismatch"
            ) from exc
        self._audit("secret.retrieve", secret, secret.company_id, by)
        return plaintext

    def rotate(self, secret_id: UUID, *, by: UUID | None = None) -> Secret:
        secret = self._require(secret_id)
        version_no = int(
            self.db.execute(
                select(func.max(SecretVersion.version)).where(SecretVersion.secret_id == secret_id)
            ).scalar()
            or 0
        )
        version = SecretVersion(
            secret_id=secret_id,
            version=version_no + 1,
            ciphertext=secret.ciphertext,
            key_id=secret.key_id,
            status=SecretStatus.RETIRED.value,
        )
        self.db.add(version)
        # Re-key the current value with the active key (env-key rotation via config).
        try:
            plaintext = crypto.decrypt_secret(secret.ciphertext)
        except Exception:  # pragma: no cover - cannot re-encrypt older material
            plaintext = None
        if plaintext is not None:
            secret.ciphertext = crypto.encrypt_secret(plaintext)
            secret.key_id = KeyManager(self.db).current().key_id
        secret.updated_at = datetime.now(UTC)
        self.db.flush()
        self._audit("secret.rotate", secret, secret.company_id, by)
        return secret

    def revoke(self, secret_id: UUID, *, by: UUID | None = None) -> Secret:
        secret = self._require(secret_id)
        secret.status = SecretStatus.REVOKED.value
        secret.updated_at = datetime.now(UTC)
        self.db.flush()
        self._audit("secret.revoke", secret, secret.company_id, by)
        return secret

    def list_company(self, company_id: UUID | None = None) -> list[Secret]:
        stmt = select(Secret).order_by(Secret.created_at.desc())
        if company_id is not None:
            stmt = stmt.where(Secret.company_id == company_id)
        return list(self.db.execute(stmt).scalars().all())

    def _require(self, secret_id: UUID) -> Secret:
        secret = self.db.get(Secret, secret_id)
        if secret is None:
            raise NotFoundError("Secret not found.")
        return secret

    def _audit(
        self,
        action: str,
        secret: Secret,
        company_id: UUID | None,
        actor: UUID | None,
        *,
        detail: dict | None = None,
    ) -> None:
        try:
            from app.security.accountability import AuditService

            AuditService(self.db).record(
                actor_id=actor,
                company_id=company_id,
                action=action,
                category="secrets",
                resource_type="secrets",
                resource_id=str(secret.id),
                outcome="success",
                detail={"name": secret.name, "kind": secret.kind, **(detail or {})},
                commit=False,
            )
        except Exception:  # pragma: no cover
            logger.debug("audit skip for %s", action)
