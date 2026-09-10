"""Schema verification strategy (Phase 6, spec §6).

Validates structured output against a lightweight hand-rolled schema.
Checks required fields, per-field types, enum values, and nested constraints.
No external dependency on ``jsonschema`` — all validation is inline and
deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.verification.types import StrategyOutcome as _StrategyOutcome
from app.verification.types import VerificationCriteria, VerificationStatus


class StrategyOutcome(_StrategyOutcome):
    """Local alias."""


# ── Lightweight schema validator ──────────────────────────────────────────────

_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "str": str,
    "number": (int, float),
    "integer": int,
    "int": int,
    "float": float,
    "boolean": bool,
    "bool": bool,
    "list": list,
    "array": list,
    "dict": dict,
    "object": dict,
    "null": type(None),
}


def _check_type(value: Any, expected_type_name: str) -> bool:
    """Return True if *value* matches the named type."""
    t = _TYPE_MAP.get(expected_type_name.lower())
    if t is None:
        return True  # Unknown type spec → pass (don't block)
    return isinstance(value, t)


def _validate_node(
    data: Any,
    schema: dict[str, Any],
    path: str = "$",
) -> list[tuple[str, str]]:
    """Validate *data* against *schema*, returning list of (path, error_msg)."""
    errors: list[tuple[str, str]] = []

    if not isinstance(schema, dict):
        return errors

    # type check
    expected_type = schema.get("type")
    if expected_type and not _check_type(data, expected_type):
        errors.append((path, f"Expected type '{expected_type}', got '{type(data).__name__}'"))
        return errors  # type mismatch → skip deeper checks

    # required fields
    required = schema.get("required", [])
    if isinstance(data, dict):
        for field_name in required:
            if field_name not in data:
                errors.append((f"{path}.{field_name}", "Required field missing"))

    # properties
    properties = schema.get("properties", {})
    if isinstance(data, dict) and properties:
        for prop_name, prop_schema in properties.items():
            if prop_name in data:
                sub = _validate_node(data[prop_name], prop_schema, f"{path}.{prop_name}")
                errors.extend(sub)

    # enum
    enum_vals = schema.get("enum")
    if enum_vals is not None and data not in enum_vals:
        errors.append((path, f"Value {data!r} not in enum {enum_vals!r}"))

    # min/max for numbers
    if isinstance(data, (int, float)):
        if "minimum" in schema and data < schema["minimum"]:
            errors.append((path, f"Value {data} < minimum {schema['minimum']}"))
        if "maximum" in schema and data > schema["maximum"]:
            errors.append((path, f"Value {data} > maximum {schema['maximum']}"))

    # minItems/maxItems for arrays
    if isinstance(data, list):
        if "minItems" in schema and len(data) < schema["minItems"]:
            errors.append((path, f"Array length {len(data)} < minItems {schema['minItems']}"))
        if "maxItems" in schema and len(data) > schema["maxItems"]:
            errors.append((path, f"Array length {len(data)} > maxItems {schema['maxItems']}"))
        # Validate items if items schema present
        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            for i, item in enumerate(data):
                sub = _validate_node(item, items_schema, f"{path}[{i}]")
                errors.extend(sub)

    # minLength/maxLength for strings
    if isinstance(data, str):
        if "minLength" in schema and len(data) < schema["minLength"]:
            errors.append((path, f"String length {len(data)} < minLength {schema['minLength']}"))
        if "maxLength" in schema and len(data) > schema["maxLength"]:
            errors.append((path, f"String length {len(data)} > maxLength {schema['maxLength']}"))

    # additionalProperties = false for objects
    if isinstance(data, dict) and schema.get("additionalProperties") is False and properties:
        extra = set(data.keys()) - set(properties.keys())
        for extra_key in extra:
            errors.append((f"{path}.{extra_key}", f"Unexpected additional property '{extra_key}'"))

    return errors


@dataclass
class ResultSchema:
    """Schema specification for structured output validation."""

    required: list[str] = field(default_factory=list)
    properties: dict[str, dict[str, Any]] = field(default_factory=dict)
    additional_properties: bool = True

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.required:
            d["required"] = list(self.required)
        if self.properties:
            d["properties"] = dict(self.properties)
        if not self.additional_properties:
            d["additionalProperties"] = False
        d["type"] = "object"
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResultSchema:
        if not data:
            return cls()
        return cls(
            required=data.get("required", []),
            properties=data.get("properties", {}),
            additional_properties=data.get("additionalProperties", True),
        )


@runtime_checkable
class SchemaVerifier(Protocol):
    """Protocol for the schema verification strategy."""

    def verify(
        self,
        result_data: dict[str, Any],
        criteria: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> StrategyOutcome:
        """Verify result_data against a schema (in criteria or context)."""


@dataclass
class DefaultSchemaVerifier:
    """Default schema verification implementation.

    The schema can be supplied via:
    - ``criteria`` (each criterion with ``type="schema"`` and ``expected`` as the schema)
    - ``context["schema"]`` as a ``ResultSchema`` dict
    """

    def verify(
        self,
        result_data: dict[str, Any],
        criteria: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> StrategyOutcome:
        context = context or {}
        criteria = criteria or []

        # Build schema from criteria or context
        schemas: list[tuple[str, dict[str, Any]]] = []

        for c in criteria:
            if c.get("type") == "schema" and c.get("expected"):
                schemas.append((c.get("key", "schema"), c["expected"]))

        ctx_schema = context.get("schema")
        if ctx_schema and not schemas:
            if isinstance(ctx_schema, dict):
                schemas.append(("context_schema", ctx_schema))
            elif isinstance(ctx_schema, ResultSchema):
                schemas.append(("context_schema", ctx_schema.to_dict()))

        if not schemas:
            # No schema provided → SKIP
            return StrategyOutcome(
                status=VerificationStatus.SKIPPED,
                score=0.0,
                confidence=0.0,
            )

        checked: list[VerificationCriteria] = []
        all_errors: list[tuple[str, str]] = []

        for schema_name, schema_dict in schemas:
            errors = _validate_node(result_data, schema_dict)
            all_errors.extend(errors)
            passed = len(errors) == 0

            checked.append(
                VerificationCriteria(
                    key=schema_name,
                    label=f"Schema validation: {schema_name}",
                    type="schema",
                    passed=passed,
                    actual={"errors": [f"{p}: {m}" for p, m in errors]} if errors else "valid",
                    expected=schema_dict,
                    evidence={"error_count": len(errors)},
                )
            )

        n = len(checked)
        passed_count = sum(1 for c in checked if c.passed is True)
        score = passed_count / n if n else 0.0

        if all_errors:
            status = VerificationStatus.FAIL
        else:
            status = VerificationStatus.PASS

        return StrategyOutcome(
            status=status,
            score=score,
            confidence=1.0,
            criteria=checked,
            evidence=[c.to_dict() for c in checked],
        )
