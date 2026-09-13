"""Self-contained HS256 signed JSON tokens (Phase 11).

Deliberately NOT a JWT dependency: we implement the minimal safe subset with
stdlib JSON + HMAC-SHA256 via ``crypto.hmac_sign`` so the surface is tiny and
we never inherit a parser's algorithm-confusion bugs.

Properties enforced by :class:`TokenService`:
- ``alg`` is restricted to ``HS256``; any other (including ``none``) ⇒ invalid.
- Signature verified in constant time; unsigned/tampered tokens rejected.
- ``iss``/``aud`` match our configured issuer/audience.
- ``exp`` is required and enforced; an expired token is invalid.
- Every token carries a unique ``jti`` for revocation tracking.
"""

from __future__ import annotations

import base64
import json
import time
import uuid as uuid_lib
from typing import Any

from app.core.config import settings
from app.security.crypto import hmac_sign, verify_hmac

_ALG = "HS256"
_ISS = "nexus"
_AUD = "nexus-api"


class InvalidToken(Exception):
    """Raised when a bearer token fails any structural/signature/expiry check."""


class ExpiredToken(InvalidToken):
    """Raised when a structurally valid token is past its ``exp`` clamp."""


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


class TokenService:
    """Sign and verify short-lived access tokens (HS256, self-contained)."""

    def __init__(self, issuer: str = _ISS, audience: str = _AUD) -> None:
        self.issuer = issuer
        self.audience = audience

    # ── signing ────────────────────────────────────────────────────────────

    def create_access_token(
        self,
        *,
        identity_id: str,
        identity_kind: str,
        company_id: str | None,
        ttl_minutes: int | None = None,
    ) -> str:
        now = int(time.time())
        ttl = ttl_minutes or settings.access_token_lifetime_minutes
        payload = {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": str(identity_id),
            "kind": identity_kind,
            "cid": str(company_id) if company_id else None,
            "iat": now,
            "exp": now + ttl * 60,
            "jti": str(uuid_lib.uuid4()),
        }
        header = _b64url_encode(json.dumps({"alg": _ALG, "typ": "JWT"}).encode("utf-8"))
        body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signature = hmac_sign(f"{header}.{body}")
        return f"{header}.{body}.{signature}"

    # ── verification ───────────────────────────────────────────────────────

    def verify_token(self, token: str) -> dict[str, Any]:
        """Return the verified payload or raise :class:`InvalidToken`."""
        header, body, signature = self._split(token)
        # Constant-time signature check over the exact signed input.
        if not verify_hmac(f"{header}.{body}", signature):
            raise InvalidToken("Token signature is invalid.")
        try:
            header_obj = json.loads(_b64url_decode(header))
            payload = json.loads(_b64url_decode(body))
        except (ValueError, UnicodeDecodeError) as exc:
            raise InvalidToken("Token payload is not valid JSON.") from exc

        if header_obj.get("alg") != _ALG:
            raise InvalidToken("Algorithm restriction violated (only HS256).")
        if header_obj.get("typ") != "JWT":
            raise InvalidToken("Token type is not JWT.")
        if payload.get("iss") != self.issuer:
            raise InvalidToken("Token issuer mismatch.")
        if payload.get("aud") != self.audience:
            raise InvalidToken("Token audience mismatch.")
        exp = payload.get("exp")
        if not isinstance(exp, int) or exp <= int(time.time()):
            raise ExpiredToken("Token has expired.")
        return payload

    # ── helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _split(token: str) -> tuple[str, str, str]:
        parts = token.split(".")
        if len(parts) != 3:
            raise InvalidToken("Token must have three parts.")
        return parts[0], parts[1], parts[2]
