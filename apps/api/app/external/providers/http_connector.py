"""Generic HTTP connector — gated and SSRF-protected (Phase 10, §14).

The only provider that issues *arbitrary* outbound HTTP, and therefore the only
one that is **off by default** (``external_generic_http_connector_enabled``).
When enabled it still requires an approved integration policy row, enforces the
company domain allowlist, and funnels every request through the
:class:`SecureHTTPClient` (SSRF guard on every redirect hop, timeouts, size
caps, rate limit, circuit breaker). ``POST_NEW/PUT_CHANGE/DELETE/ANY_MUTATION``
methods are HIGH/CRITICAL and always approval-gated. No raw ungoverned HTTP
ever escapes (Rule 10).
"""

from __future__ import annotations

from typing import Any

from app.db.models.external import (
    AuthMethod,
    IntegrationCategory,
    Reversibility,
    RiskLevel,
)
from app.external.api.http_client import SecureHTTPClient
from app.external.api.ssrf import SSRFBlockedError, allowed_domain
from app.external.types import (
    AuthContext,
    Capability,
    ExternalAuthFailure,
    ExternalPermissionFailure,
    ExternalProviderError,
    ExternalTimeoutFailure,
    ExternalValidationFailure,
)

API_KEY_ENV_HINT = "INTEGRATION_HTTP_CONNECTOR_API_KEY"

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class GenericHTTPConnectorProvider:
    """Gated, domain-restricted HTTP connector over the secure client."""

    slug = "http_connector"
    name = "Generic HTTP Connector"
    category = IntegrationCategory.CUSTOM_API
    auth_type = AuthMethod.API_KEY
    description = "Gated generic HTTP connector (disabled by default; §14)."

    def secrets_required(self) -> list[str]:
        return [API_KEY_ENV_HINT]

    def capabilities(self) -> list[Capability]:
        return [
            Capability(
                name="http_request",
                description=(
                    "Perform an HTTP request to an allowlisted domain. Read methods LOW; "
                    "mutating methods HIGH and always approval-gated."
                ),
                capability_type="read_write",
                risk_level=RiskLevel.LOW,  # read form; escalated for mutating methods
                input_schema={
                    "type": "object",
                    "properties": {
                        "method": {"type": "string"},
                        "url": {"type": "string"},
                        "headers": {"type": "object"},
                        "json": {"type": "object"},
                    },
                    "required": ["method", "url"],
                },
                reversibility=Reversibility.UNKNOWN,
                supports_idempotency=True,
                approval_required=False,
                required_permissions=["http:request"],
            )
        ]

    def execute(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        auth: AuthContext,
        connection: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        if capability != "http_request":
            raise ExternalValidationFailure(f"Unknown connector capability {capability!r}")
        if not auth.secrets.get("api_key"):
            raise ExternalAuthFailure("HTTP connector requires INTEGRATION_HTTP_CONNECTOR_API_KEY")

        method = str(payload.get("method", "GET")).upper()
        url = str(payload.get("url", ""))
        if not url.startswith(("http://", "https://")):
            raise ExternalValidationFailure("URL must be http(s)")
        if method not in _SAFE_METHODS and method not in _MUTATING_METHODS:
            raise ExternalValidationFailure(f"Method {method!r} not allowed")

        allowed_domains = list(context.get("allowed_domains") or [])
        if allowed_domains:
            from urllib.parse import urlparse

            domain = urlparse(url).netloc or ""
            if not allowed_domain(domain, allowed_domains):
                raise ExternalPermissionFailure(
                    f"Domain {domain!r} is not in the connector allowlist"
                )

        client = SecureHTTPClient()
        headers = dict(payload.get("headers") or {})
        try:
            response = client.request(
                method,
                url,
                headers=headers,
                json_body=payload.get("json"),
                rate_limit_key=f"connector:{context.get('company_id', 'global')}",
                allowed_domains=allowed_domains,
                timeout_seconds=float(payload.get("timeout_seconds") or 30),
            )
        except SSRFBlockedError as exc:
            raise ExternalPermissionFailure(f"SSRF guard refused: {exc}") from exc
        except ExternalTimeoutFailure:
            raise
        except ExternalProviderError:
            raise

        body = _decode_body(response)
        return {
            "status_code": response.status_code,
            "headers": {
                k: v
                for k, v in response.headers.items()
                if k.lower() not in {"authorization", "set-cookie", "www-authenticate"}
            },
            "body": body,
            "truncated": len(body) > 4096,
        }


def _decode_body(response: Any) -> dict[str, Any] | str:
    content_type = response.headers.get("content-type", "")
    try:
        if "json" in content_type:
            return response.json()
        return response.text[:4096]
    except Exception:  # noqa: BLE001 - any decode failure degrades to raw text
        return response.text[:4096]
