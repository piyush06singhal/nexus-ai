"""Simulation variables — typed, bounded, validated (never unvalidated input)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.phase12._types import SimVariableKind


class VariableValidationError(ValueError):
    """A variable is out of bounds / wrong type for its declared kind."""


@dataclass
class SimulationVariable:
    """A typed variable driving a scenario. Bounds enforced at validation.

    Kinds: INTEGER, FLOAT, BOOLEAN, STRING, ENUM, DURATION, PERCENTAGE,
    CURRENCY, RATE. ``value`` is stored serialized as text; ``as_number`` /
    ``serialized`` expose typed access.
    """

    name: str
    kind: SimVariableKind | str
    value: Any = None
    min_value: Any = None
    max_value: Any = None
    default: Any = None
    description: str | None = None
    source: str | None = None
    confidence: float | None = None
    options: list[Any] = field(default_factory=list)  # for ENUM kind

    def __post_init__(self) -> None:
        self.kind = SimVariableKind(self.kind)

    # ── Validation ────────────────────────────────────────────────────

    def validate(self) -> bool:
        self._coerce()
        if self.kind is SimVariableKind.ENUM:
            if self.options and self.value not in self.options:
                raise VariableValidationError(
                    f"Variable '{self.name}' = {self.value!r} not in {self.options}"
                )
        if self.min_value is not None and self.value is not None:
            if isinstance(self.value, (int, float)) and self.value < self.min_value:
                raise VariableValidationError(f"Variable '{self.name}' below min {self.min_value}")
        if self.max_value is not None and self.value is not None:
            if isinstance(self.value, (int, float)) and self.value > self.max_value:
                raise VariableValidationError(f"Variable '{self.name}' above max {self.max_value}")
        if self.kind is SimVariableKind.PERCENTAGE:
            v = self.value if isinstance(self.value, (int, float)) else 0
            if not (0 <= v <= 100):
                raise VariableValidationError(f"Variable '{self.name}' must be a percentage 0..100")
        if self.kind is SimVariableKind.BOOLEAN and not isinstance(self.value, bool):
            raise VariableValidationError(f"Variable '{self.name}' must be boolean")
        return True

    def _coerce(self) -> None:
        if self.value is None:
            self.value = self.default
        if self.value is None:
            return
        if self.kind is SimVariableKind.INTEGER:
            self.value = int(self.value)
        elif self.kind in (
            SimVariableKind.FLOAT,
            SimVariableKind.PERCENTAGE,
            SimVariableKind.CURRENCY,
            SimVariableKind.RATE,
        ):
            self.value = float(self.value)
        elif self.kind is SimVariableKind.BOOLEAN:
            if isinstance(self.value, str):
                self.value = self.value.strip().lower() in ("1", "true", "yes", "on")

    @property
    def as_number(self) -> float | None:
        if self.value is None:
            return None
        try:
            return float(self.value)
        except (TypeError, ValueError):
            return None

    @property
    def serialized(self) -> str | None:
        if self.value is None:
            return None
        return str(self.value)

    def to_public(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "value": self.value,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "default": self.default,
            "description": self.description,
            "source": self.source,
            "confidence": self.confidence,
        }


def validate_variables(variables: list[SimulationVariable]) -> list[SimulationVariable]:
    """Validate every variable; raises at first error so invalid sims are rejected."""
    for v in variables:
        v.validate()
    return variables
