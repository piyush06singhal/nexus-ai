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
import json
import time
from collections.abc import Iterator
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.openai.com/v1"
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"

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


def resolve_base_url(configured: str, default: str = DEFAULT_BASE_URL) -> str:
    """Return the base URL, defaulting to *default* (which is provider-specific)."""
    return (configured or default).rstrip("/")


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
    headers: dict[str, str] | None = None,
    default_base_url: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Perform one provider call with bounded exponential-backoff retries.

    Returns the parsed JSON response body. Raises ``OpenAIRequestError`` for
    definitive errors and ``OpenAIUnavailableError`` when retries are
    exhausted. ``transport`` is a test seam (``httpx.MockTransport``).
    ``headers`` (optional) are merged over the default auth/content-type
    headers — Anthropic uses ``x-api-key`` instead of ``Authorization: Bearer``,
    so the adapter passes its own auth headers here. ``default_base_url`` lets a
    non-OpenAI provider pin its own endpoint when its configured base is empty.
    """
    url = f"{resolve_base_url(base_url, default_base_url or DEFAULT_BASE_URL)}/{path.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **(headers or {}),
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
    headers: dict[str, str] | None = None,
    default_base_url: str | None = None,
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
        headers=headers,
        default_base_url=default_base_url,
        transport=transport,
    )


def _stream(
    *,
    method: str,
    path: str,
    base_url: str,
    api_key: str,
    json_body: dict[str, Any],
    timeout: float,
    max_retries: int,
    backoff: float,
    headers: dict[str, str] | None = None,
    default_base_url: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> Iterator[dict[str, Any]]:
    """Perform one provider streaming call; yields decoded SSE frames.

    Unlike :func:`_request`, retries apply only to *establishing* the stream —
    a connect-time transport error or retryable status is retried, but once
    bytes start flowing a mid-stream failure raises ``OpenAIUnavailableError``
    (there is no resend of a partially-consumed stream). The ``[DONE]`` marker
    is consumed here, so every yielded dict is the parsed JSON of one ``data:``
    frame. ``headers`` merges over the default auth/content-type headers and
    ``default_base_url`` pins a non-OpenAI endpoint, as in :func:`_request`.
    """
    url = f"{resolve_base_url(base_url, default_base_url or DEFAULT_BASE_URL)}/{path.lstrip('/')}"
    request = httpx.Request(
        method,
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            **(headers or {}),
        },
        json=json_body,
    )

    for attempt in range(max_retries + 1):
        client = httpx.Client(timeout=timeout, transport=transport)
        try:
            response = client.send(request, stream=True)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            client.close()
            if attempt < max_retries:
                time.sleep(backoff * (2**attempt))
                continue
            raise OpenAIUnavailableError(
                f"OpenAI stream transport failure: {exc.__class__.__name__}"
            ) from exc

        if response.status_code in _RETRYABLE_STATUSES and attempt < max_retries:
            client.close()
            time.sleep(backoff * (2**attempt))
            continue

        if response.status_code >= 400:
            detail = _error_detail(response)
            client.close()
            if response.status_code in _RETRYABLE_STATUSES:
                raise OpenAIUnavailableError(f"OpenAI stream retries exhausted: {detail}")
            raise OpenAIRequestError(response.status_code, detail)

        # Connection established — stream SSE frames. Retries stop here.
        try:
            for line in response.iter_lines():
                stripped = line.strip()
                if not stripped.startswith("data:"):
                    continue
                payload = stripped[len("data:") :].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    yield json.loads(payload)
                except ValueError as exc:
                    raise OpenAIUnavailableError(
                        "OpenAI stream sent a non-JSON data frame"
                    ) from exc
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise OpenAIUnavailableError(
                f"OpenAI stream interrupted: {exc.__class__.__name__}"
            ) from exc
        return

    raise OpenAIUnavailableError("OpenAI stream retries exhausted")  # pragma: no cover - defensive


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
