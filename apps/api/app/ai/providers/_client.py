"""Shared HTTP transport for the OpenAI provider adapters.

A small, dependency-minimal client that both the chat provider and the
embedding provider use so retry/backoff and error mapping live in exactly one
place. It deliberately does NOT reuse ``app.external.api.http_client`` — that
client applies SSRF protection designed for user-supplied URLs, whereas
``api.openai.com`` (or a configured compatible endpoint) is a trusted vendor
endpoint.

Error contract:
    - ``OpenAIRequestError``  — a definitive 4xx (bad request, auth, quota,
      invalid model). Not retryable.
    - ``OpenAIUnavailableError`` — transport error, timeout, or retryable
      status (408/429/5xx) after the retry budget is exhausted.

Both wrap raw ``httpx`` exceptions so downstream code never imports httpx.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.openai.com/v1"

#: Statuses worth retrying (they may succeed after a short backoff).
_RETRYABLE_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}


class OpenAIError(Exception):
    """Base class for provider transport errors."""


class OpenAIRequestError(OpenAIError):
    """A definitive API error (4xx): no amount of retrying will fix it."""

    def __init__(self, status: int, detail: str, *, code: str | None = None) -> None:
        self.status = status
        self.detail = detail
        self.code = code or f"openai_http_{status}"
        super().__init__(f"OpenAI API error {status}: {detail}")


class OpenAIUnavailableError(OpenAIError):
    """Transport failure or exhausted retry budget (others may eventually succeed)."""


def resolve_base_url(configured: str) -> str:
    """Return the base URL, defaulting to the public OpenAI endpoint."""
    return (configured or DEFAULT_BASE_URL).rstrip("/")


def _retryable(exception: Exception) -> bool:
    """True if the exception represents a transient failure worth retrying."""
    return isinstance(exception, (httpx.TimeoutException, httpx.TransportError))


def _request(
    *,
    method: str,
    path: str,
    base_url: str,
    api_key: str,
    json_body: dict[str, Any],
    timeout: float,
    max_retries: int,
    backoff: float,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Perform one provider call with bounded exponential-backoff retries.

    Returns the parsed JSON response body. Raises ``OpenAIRequestError`` for
    definitive errors and ``OpenAIUnavailableError`` when retries are
    exhausted. ``transport`` is a test seam (``httpx.MockTransport``).
    """
    url = f"{resolve_base_url(base_url)}/{path.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    for attempt in range(max_retries + 1):
        try:
            with httpx.Client(timeout=timeout, transport=transport) as client:
                response = client.request(method, url, headers=headers, json=json_body)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if attempt < max_retries and _retryable(exc):
                time.sleep(backoff * (2**attempt))
                continue
            raise OpenAIUnavailableError(
                f"OpenAI transport failure: {exc.__class__.__name__}"
            ) from exc

        if response.status_code in _RETRYABLE_STATUSES and attempt < max_retries:
            time.sleep(backoff * (2**attempt))
            continue

        if response.status_code >= 400:
            detail = _error_detail(response)
            if response.status_code in _RETRYABLE_STATUSES:
                # Retry budget exhausted on a retryable status.
                raise OpenAIUnavailableError(f"OpenAI retries exhausted: {detail}")
            raise OpenAIRequestError(response.status_code, detail)

        return response.json()

    raise OpenAIUnavailableError("OpenAI retries exhausted")  # pragma: no cover - defensive


async def _request_async(
    *,
    method: str,
    path: str,
    base_url: str,
    api_key: str,
    json_body: dict[str, Any],
    timeout: float,
    max_retries: int,
    backoff: float,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Async variant of :func:`_request` (used by the embeddings provider).

    The retry loop itself is synchronous; the network I/O runs in a worker
    thread so the event loop is not blocked.
    """
    return await asyncio.to_thread(
        _request,
        method=method,
        path=path,
        base_url=base_url,
        api_key=api_key,
        json_body=json_body,
        timeout=timeout,
        max_retries=max_retries,
        backoff=backoff,
        transport=transport,
    )


def _error_detail(response: httpx.Response) -> str:
    """Pull a human-readable detail from an error body, truncating output."""
    try:
        payload = response.json()
        message = (payload.get("error") or {}).get("message")
        if isinstance(message, str) and message:
            return message[:300]
    except ValueError:
        pass
    return (response.text or "")[:300]
