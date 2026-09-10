"""Failure injection helpers (Phase 6, spec §49).

**Test-only** deterministic injection helpers for reliably testing the
recovery engine. Builds a :class:`FailInjectionSpec` and wraps a
:class:`MockProvider` or :class:`ToolExecutor` to simulate failures.

Gated to ``environment != production`` — never exposed via API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class InjectionKind(StrEnum):
    """Types of failure to inject."""

    MODEL = "model"
    TOOL = "tool"
    TIMEOUT = "timeout"
    MALFORMED = "malformed"
    VERIFICATION = "verification"
    COMMUNICATION = "communication"
    MEMORY = "memory"


@dataclass
class FailInjectionSpec:
    """Specification for injecting a failure.

    Attributes:
        kind: Type of failure to inject.
        target: Name of the tool/model/component to target (optional).
        error_message: Custom error message.
        error_type: Exception class name to raise.
        delay_ms: Artificial delay before failure (simulates timeout).
        malformed_output: Custom malformed output to return.
        repeat_count: Number of times the injection fires (0 = unlimited).
    """

    kind: InjectionKind = InjectionKind.MODEL
    target: str | None = None
    error_message: str = "Injected failure"
    error_type: str = "RuntimeError"
    delay_ms: int = 0
    malformed_output: dict[str, Any] | None = None
    repeat_count: int = 1

    _fire_count: int = field(default=0, init=False, repr=False)

    def should_fire(self) -> bool:
        """Check if this injection should fire on the current call."""
        if self.repeat_count == 0:
            return True  # Unlimited
        return self._fire_count < self.repeat_count

    def record_fire(self) -> None:
        """Record that the injection fired."""
        self._fire_count += 1

    def reset(self) -> None:
        """Reset the fire count."""
        self._fire_count = 0


class MockProvider:
    """Mock model provider that can inject failures (spec §53).

    By default returns a successful response. When wrapped with a
    :class:`FailInjectionSpec`, it raises or returns malformed output.
    """

    def __init__(
        self,
        spec: FailInjectionSpec | None = None,
        default_response: dict[str, Any] | None = None,
    ) -> None:
        self.spec = spec
        self.default_response = default_response or {
            "status": "pass",
            "score": 1.0,
            "confidence": 1.0,
            "reason": "Mock provider default success",
            "evidence": "default",
        }

    def evaluate(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Evaluate with optional failure injection."""
        if self.spec and self.spec.should_fire():
            self.spec.record_fire()
            return self._inject_failure(prompt)
        return self.default_response

    def _inject_failure(self, prompt: str) -> dict[str, Any]:
        """Inject the configured failure."""
        import time

        if self.spec.kind == InjectionKind.TIMEOUT:
            if self.spec.delay_ms > 0:
                time.sleep(self.spec.delay_ms / 1000.0)
            raise TimeoutError(self.spec.error_message)

        if self.spec.kind == InjectionKind.MODEL:
            raise RuntimeError(self.spec.error_message)

        if self.spec.kind == InjectionKind.MALFORMED:
            return self.spec.malformed_output or {"invalid": True}

        if self.spec.kind == InjectionKind.COMMUNICATION:
            raise ConnectionError(self.spec.error_message)

        raise RuntimeError(f"Unknown injection kind: {self.spec.kind}")


class MockToolExecutor:
    """Mock tool executor that can inject failures (spec §49).

    By default returns successful tool results. When wrapped with a
    :class:`FailInjectionSpec`, it raises or returns error results.
    """

    def __init__(
        self,
        spec: FailInjectionSpec | None = None,
        default_result: dict[str, Any] | None = None,
    ) -> None:
        self.spec = spec
        self.default_result = default_result or {
            "status": "success",
            "output": "Tool executed successfully",
        }

    def __call__(
        self,
        tool_name: str = "",
        args: dict[str, Any] | None = None,
        agent_id: Any = None,
        permission_context: Any = None,
    ) -> dict[str, Any]:
        """Execute with optional failure injection."""
        if self.spec and self.spec.should_fire():
            if self.spec.target and self.spec.target != tool_name:
                return self.default_result  # Not targeting this tool
            self.spec.record_fire()
            return self._inject_failure(tool_name)
        return self.default_result

    def _inject_failure(self, tool_name: str) -> dict[str, Any]:
        """Inject the configured failure."""
        import time

        if self.spec.kind == InjectionKind.TIMEOUT:
            if self.spec.delay_ms > 0:
                time.sleep(self.spec.delay_ms / 1000.0)
            return {"status": "timeout", "error": self.spec.error_message}

        if self.spec.kind == InjectionKind.TOOL:
            return {"status": "error", "error": self.spec.error_message}

        if self.spec.kind == InjectionKind.MALFORMED:
            return self.spec.malformed_output or {"status": "error", "error": "Malformed output"}

        return {"status": "error", "error": self.spec.error_message}


class MockAgentRunner:
    """Mock agent runner for testing independent agent verification."""

    def __init__(
        self,
        spec: FailInjectionSpec | None = None,
        default_response: dict[str, Any] | None = None,
        verifier_agent_id: Any = None,
    ) -> None:
        self.spec = spec
        self.default_response = default_response or {
            "status": "pass",
            "score": 1.0,
            "confidence": 0.9,
            "reason": "Mock agent verification passed",
            "evidence": "Mock evidence",
        }
        self.verifier_agent_id = verifier_agent_id

    def run(
        self,
        agent_id: Any,
        task_description: str,
        *,
        input_data: dict[str, Any] | None = None,
        permission_context: Any = None,
    ) -> dict[str, Any]:
        """Run with optional failure injection."""
        if self.spec and self.spec.should_fire():
            self.spec.record_fire()
            if self.spec.kind == InjectionKind.MODEL:
                raise RuntimeError(self.spec.error_message)
            if self.spec.kind == InjectionKind.COMMUNICATION:
                raise ConnectionError(self.spec.error_message)
        return self.default_response

    def resolve_verifier_agent(
        self,
        producer_role: str | None = None,
        allowed_verifier_types: list[str] | None = None,
    ) -> Any:
        """Return a mock verifier agent ID."""
        return self.verifier_agent_id or "mock-verifier-agent"
