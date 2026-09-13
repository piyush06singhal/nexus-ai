"""Cryptographic primitives for NEXUS security (Phase 11).

Dependency-free policy wrapper around ``cryptography``:
- **Fernet (AES-256-GCM)** for secret ciphertext at rest, keyed by
  ``SECRET_ENCRYPTION_KEY`` from the environment (never committed, never
  hardcoded). An empty key in non-production falls back to an ephemeral key
  derived per-process so dev/test need no environment; production-readiness
  FAILs when the key is missing in production.
- **PBKDF2-HMAC-SHA256** for password hashing (210k iterations) — bcrypt-free,
  pure ``cryptography``.
- **HMAC-SHA256** for token signing (HS256).

Redaction of these values in logs is handled by ``core/redaction.py`` — this
module never logs key material.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets as _secrets

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_EPHEMERAL_TOKEN_KEY: bytes | None = None
_EPHEMERAL_ENC_KEY: str | None = None

_PBKDF2_ITERATIONS = 210_000

# ── Key material (env → derived → ephemeral fallback) ───────────────────────


def _token_key_bytes() -> bytes:
    """Return the 32-byte HMAC key for access tokens (HS256)."""
    global _EPHEMERAL_TOKEN_KEY
    configured = settings.jwt_secret_key
    if configured:
        # Accept a raw secret; derive a fixed 32-byte key from it.
        return hashlib.sha256(configured.encode("utf-8")).digest()
    if _EPHEMERAL_TOKEN_KEY is None:
        _EPHEMERAL_TOKEN_KEY = os.urandom(32)
    return _EPHEMERAL_TOKEN_KEY


def _fernet_key_bytes() -> bytes:
    """Return valid Fernet key bytes from ``SECRET_ENCRYPTION_KEY``."""
    global _EPHEMERAL_ENC_KEY
    configured = settings.secret_encryption_key
    if configured:
        try:
            key = configured.encode("utf-8")
            Fernet(key)  # validate form
            return key
        except Exception:
            # Accept a raw passphrase by deriving a 32-byte url-safe key.
            return base64.urlsafe_b64encode(hashlib.sha256(configured.encode("utf-8")).digest())
    if _EPHEMERAL_ENC_KEY is None:
        _EPHEMERAL_ENC_KEY = Fernet.generate_key().decode("utf-8")
    return _EPHEMERAL_ENC_KEY.encode("utf-8")


def fingerprint_key(key_material: str) -> str:
    """sha256 fingerprint of key material — safe to store/compare, not the key."""
    return hashlib.sha256(key_material.encode("utf-8")).hexdigest()


# ── Token signatures (HMAC-SHA256 / HS256) ──────────────────────────────────


def hmac_sign(payload_b64: str) -> str:
    """Sign ``payload_b64`` and return the hex signature."""
    return hmac.new(_token_key_bytes(), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_hmac(payload_b64: str, signature: str) -> bool:
    """Constant-time check of an HMAC signature."""
    expected = hmac_sign(payload_b64)
    return hmac.compare_digest(expected.encode("utf-8"), signature.encode("utf-8"))


# ── Passwords (PBKDF2-HMAC-SHA256) ──────────────────────────────────────────


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Hash a password and return ``(hash_b64, salt_hex)`` for storage.

    The salt is random per call unless supplied (for deterministic tests).
    """
    salt = salt or _secrets.token_hex(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt.encode("utf-8"),
        iterations=_PBKDF2_ITERATIONS,
    )
    derived = kdf.derive(password.encode("utf-8"))
    return base64.urlsafe_b64encode(derived).decode("utf-8"), salt


def verify_password(password: str, hash_b64: str, salt: str) -> bool:
    """Constant-time password verification against stored hash + salt."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt.encode("utf-8"),
        iterations=_PBKDF2_ITERATIONS,
    )
    try:
        kdf.verify(password.encode("utf-8"), base64.urlsafe_b64decode(hash_b64))
        return True
    except Exception:
        return False


# ── Secret ciphertext (Fernet / AES-256-GCM) ────────────────────────────────


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a plaintext secret; returns url-safe ciphertext (never plaintext)."""
    data = Fernet(_fernet_key_bytes()).encrypt(plaintext.encode("utf-8"))
    return data.decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt ciphertext produced by :func:`encrypt_secret`.

    Raises :class:`InvalidToken` when the key does not match (rotation/retirement).
    """
    data = Fernet(_fernet_key_bytes()).decrypt(ciphertext.encode("utf-8"))
    return data.decode("utf-8")


def generate_key_id(label: str = "key") -> str:
    """Return a stable, human-friendly key identifier."""
    return f"{label}-{_secrets.token_hex(4)}"
