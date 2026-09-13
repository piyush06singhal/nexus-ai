"""Secure HTTP client for the external layer (Phase 10, §14).

A thin wrapper around httpx that enforces: SSRF protection (every redirect hop
re-validated), bounded timeouts, response size caps, request-id headers,
retry + backoff for retryable statuses, an optional rate limiter, and an
optional circuit breaker. The generic HTTP connector and the web-research
provider go through this — no raw httpx escapes the layer.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import settings
from app.external.api.circuit_breaker import CircuitBreaker
from app.external.api.rate_limit import RateLimiter
from app.external.api.retry import backoff_delay_ms, is_retryable_status_code
from app.external.api.ssrf import SSRFBlockedError, check_host_resolution, check_url
from app.external.types import (
    ExternalRateLimitFailure,
    ExternalSystemFailure,
    ExternalTransportFailure,
)


class SecureHTTPClient:
    """Outbound HTTP with SSRF, timeout, size, and reliability enforcement."""

    def __init__(
        self,
        *,
        connect_timeout: float | None = None,
        read_timeout: float | None = None,
        max_response_bytes: int | None = None,
        rate_limiter: RateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._connect_timeout = connect_timeout or settings.external_connect_timeout_seconds
        self._read_timeout = read_timeout or settings.external_read_timeout_seconds
        self._max_response_bytes = max_response_bytes or settings.max_external_payload_bytes
        self._rate_limiter = rate_limiter or RateLimiter(settings.external_rate_limit_per_minute)
        self._breaker = circuit_breaker or CircuitBreaker(
            threshold=settings.external_circuit_breaker_threshold,
            reset_seconds=settings.external_circuit_breaker_reset_seconds,
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        timeout_seconds: float | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        data: str | None = None,
        rate_limit_key: str = "default",
        rate_limit_per_minute: int | None = None,
        allowed_domains: list[str] | None = None,
        max_redirects: int = 5,
    ) -> httpx.Response:
        """Perform a governed request, validating every redirect hop."""
        check_url(url)
        _resolve_and_check(url)
        if not self._breaker.allow_request():
            raise ExternalTransportFailure(
                f"Circuit {self._breaker.state}: provider temporarily refused"
            )
        if not self._rate_limiter.allow(rate_limit_key, per_minute=rate_limit_per_minute):
            raise ExternalRateLimitFailure(f"Rate limit exceeded for {rate_limit_key!r}")

        timeout = timeout_seconds or max(
            self._connect_timeout + self._read_timeout, settings.external_action_timeout_seconds
        )
        auth_parts = []
        req_headers = {
            "User-Agent": "NEXUS-External/1.0 (governed)",
            "X-NEXUS-Request-Id": _request_id(),
            **(headers or {}),
        }
        try:
            with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                current_url = url
                redirects = 0
                while True:
                    resp = _send(client, method, current_url, req_headers, json_body, data, timeout)
                    if resp.is_redirect and redirects < max_redirects:
                        location = resp.headers.get("location")
                        if not location:
                            break
                        next_url = urljoin(current_url, location)
                        check_url(next_url)  # re-validate the hop (SSRF)
                        _resolve_and_check(next_url)  # …and re-resolve it (rebinding)
                        auth_parts.append(next_url)
                        current_url = next_url
                        redirects += 1
                        continue
                    if resp.is_redirect:
                        raise ExternalTransportFailure("Too many redirects")
                    # Materialise the body now (bufsize/stream lifecycle in httpx
                    # manages the connection pool); ``.read()`` is idempotent.
                    resp.read()
                    break
        except (SSRFBlockedError, ExternalRateLimitFailure, ExternalTransportFailure):
            self._breaker.record_failure()
            raise
        except httpx.TimeoutException as exc:
            self._breaker.record_failure()
            raise ExternalTransportFailure(f"Outbound request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            self._breaker.record_failure()
            raise ExternalTransportFailure(f"Outbound transport error: {exc}") from exc

        if resp.status_code >= 500 or resp.status_code in (408, 429):
            self._breaker.record_failure()
        else:
            self._breaker.record_success()

        body = resp.content
        if len(body) > self._max_response_bytes:
            raise ExternalSystemFailure(f"Response exceeded {self._max_response_bytes} bytes cap")
        return resp

    def retry_with_backoff(
        self,
        method: str,
        url: str,
        *,
        attempt: int = 0,
        max_attempts: int = 2,
        **kwargs: Any,
    ) -> httpx.Response:
        """Retry retryable statuses with exponential backoff."""
        for i in range(attempt, max_attempts + 1):
            try:
                resp = self.request(method, url, **kwargs)
                if not is_retryable_status_code(resp.status_code):
                    return resp
            except (ExternalTransportFailure, ExternalRateLimitFailure):
                if i >= max_attempts:
                    raise
            if i < max_attempts:
                time.sleep(backoff_delay_ms(i) / 1000)
        raise ExternalSystemFailure("Retry budget exhausted")


def _resolve_and_check(url: str) -> None:
    """SSRF-resolve the URL's host right before connecting (DNS-rebinding)."""
    try:
        check_host_resolution(urlparse(url).hostname or "")
    except (AttributeError, TypeError):  # pragma: no cover
        pass


def _send(
    client: httpx.Client,
    method: str,
    url: str,
    headers: dict[str, str],
    json_body: dict[str, Any] | None,
    data: str | None,
    timeout: float,
) -> httpx.Response:
    return client.request(
        method,
        url,
        headers=headers,
        json=json_body,
        content=data,
        timeout=timeout,
    )


def _request_id() -> str:
    import uuid

    return f"nx-{uuid.uuid4().hex[:12]}"
