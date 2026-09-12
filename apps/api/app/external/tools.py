"""Capability tools registered with the Phase 2 tool registry (Phase 10).

Every provider capability materializes as a :class:`BaseTool` (name
``{provider}.{capability}``) and is auto-registered at import time. The
tool delegates to :class:`ExternalActionManager` so the full governance
funnel (permission → policy → autonomy → approval → execute → scrub →
verify → recover → audit) is identical for agent-driven and direct calls.
High/critical capabilities have ``dangerous=True`` so Phase 2 requires
explicit agent permission. No raw ``http_request`` tool is registered by
default.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from app.db.models.external import ExternalActionStatus, RiskLevel
from app.external.registry import get_provider, list_providers

# NOTE: ``ExternalActionManager`` is deliberately imported lazily inside
# ``_run``. This module is imported from ``app/tools/registry.py`` at import
# time, and ``ExternalActionManager`` drags in the Phase 9 stack (startup →
# employee → runtime). Importing it eagerly here would create a circular
# import whenever ``app.tools`` is first loaded. The provider/capability graph
# itself is light, so the registry hook stays side-effect free.
from app.tools.base import BaseTool
from app.tools.registry import register_tool
from app.tools.types import (
    ToolDefinition,
    ToolParameter,
    ToolParameterType,
    ToolResult,
    ToolResultStatus,
)


def _as_uuid(value: Any) -> UUID | None:
    """Coerce a possibly-raw id to UUID, tolerating None."""
    if value is None:
        return None
    return value if isinstance(value, UUID) else UUID(str(value))


def register_capability_tools() -> list[str]:
    """Register a tool for every capability of every registered provider.

    Returns the list of tool names registered.
    """
    registered: list[str] = []
    for provider_slug in list_providers():
        provider = get_provider(provider_slug)
        for cap in provider.capabilities():
            tool = _CapabilityTool(provider_slug, cap)
            register_tool(tool)
            registered.append(tool.definition.name)
    return registered


class _CapabilityTool(BaseTool):
    """Thin wrapper that forwards a provider capability through the external action funnel."""

    def __init__(self, provider_slug: str, capability: Any) -> None:
        self._provider_slug = provider_slug
        self._capability = capability
        # Build parameter list from the capability's input_schema
        params = _schema_to_parameters(capability.input_schema or {})
        self._definition = ToolDefinition(
            name=f"{provider_slug}.{capability.name}",
            description=f"[{provider_slug}] {capability.description}",
            parameters=params,
            dangerous=_is_dangerous(capability.risk_level),
            timeout_seconds=settings.external_action_timeout_seconds,
            tags=[provider_slug, "external", capability.capability_type],
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def execute(self, **kwargs: Any) -> ToolResult:
        # Import locally to avoid circular deps at module import time.
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            # The tool must receive company_id to scope the action. Agents pass
            # it explicitly (from their permission context); direct callers can
            # supply it from the API layer.
            company_id = kwargs.pop("company_id", None)
            if company_id is None:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error="company_id is required for external capability tools",
                )
            connection_id = kwargs.pop("connection_id", None)
            employee_id = kwargs.pop("employee_id", None)
            agent_id = kwargs.pop("agent_id", None)
            execution_id = kwargs.pop("execution_id", None)
            workflow_execution_id = kwargs.pop("workflow_execution_id", None)
            orchestration_id = kwargs.pop("orchestration_id", None)
            idempotency_key = kwargs.pop("idempotency_key", None)
            approved_gate_id = kwargs.pop("approved_gate_id", None)
            correlation_id = kwargs.pop("correlation_id", None)

            try:
                company_uuid = company_id if isinstance(company_id, UUID) else UUID(str(company_id))
            except ValueError:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"company_id is not a valid UUID: {company_id!r}",
                )
            integration_id = self._integration_id(db, company_uuid)
            if integration_id is None:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=(
                        f"No {self._provider_slug} integration for company "
                        f"{company_uuid}. Create and connect one first."
                    ),
                )

            result = self._run(
                db,
                company_uuid,
                integration_id,
                {
                    "connection_id": connection_id,
                    "employee_id": employee_id,
                    "agent_id": agent_id,
                    "execution_id": execution_id,
                    "workflow_execution_id": workflow_execution_id,
                    "orchestration_id": orchestration_id,
                    "idempotency_key": idempotency_key,
                    "approved_gate_id": approved_gate_id,
                    "correlation_id": correlation_id,
                },
                kwargs,
            )
            return result
        finally:
            db.close()

    def _run(
        self,
        db: Any,
        company_uuid: UUID,
        integration_id: UUID,
        conductors: dict[str, Any],
        payload: dict[str, Any],
    ) -> ToolResult:
        """Forward the capability call through the external action funnel."""
        # Imported lazily to avoid dragging the Phase 9 stack into the tool
        # registry's import-time hook (see module docstring note).
        from app.external.action import ExternalActionError, ExternalActionManager

        mgr = ExternalActionManager(db)
        try:
            action = mgr.create(
                company_id=company_uuid,
                integration_id=integration_id,
                capability=self._capability.name,
                payload=payload,
                connection_id=_as_uuid(conductors.get("connection_id")),
                employee_id=_as_uuid(conductors.get("employee_id")),
                agent_id=_as_uuid(conductors.get("agent_id")),
                execution_id=_as_uuid(conductors.get("execution_id")),
                workflow_execution_id=_as_uuid(conductors.get("workflow_execution_id")),
                orchestration_id=_as_uuid(conductors.get("orchestration_id")),
                idempotency_key=conductors.get("idempotency_key"),
                approved_gate_id=_as_uuid(conductors.get("approved_gate_id")),
                correlation_id=conductors.get("correlation_id"),
            )
        except ExternalActionError as exc:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=exc.message,
                data={"code": exc.code, "status": exc.status},
            )

        if action.status.value == ExternalActionStatus.AWAITING_APPROVAL.value:
            return ToolResult(
                status=ToolResultStatus.WAITING,
                data={
                    "action_id": str(action.id),
                    "gate_id": str(action.approval_gate_id) if action.approval_gate_id else None,
                    "message": "Action awaiting human approval",
                },
            )
        data = json.loads(action.result) if action.result else {}
        return ToolResult(status=ToolResultStatus.SUCCESS, data=data)

    def _integration_id(self, db: Any, company_id: UUID) -> UUID | None:
        """Return the company's integration id for this provider, or None."""
        from app.external.integration import IntegrationService

        for integ in IntegrationService(db).list_(company_id):
            if integ.provider == self._provider_slug:
                return integ.id
        return None


def _schema_to_parameters(schema: dict[str, Any]) -> list[ToolParameter]:
    """Convert a JSON-schema-like object to ToolParameter list."""
    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
    required = set(schema.get("required", []))
    params: list[ToolParameter] = []
    for name, spec in props.items():
        t = _json_type_to_param_type(spec.get("type", "string"))
        params.append(
            ToolParameter(
                name=name,
                type=t,
                description=spec.get("description", ""),
                required=name in required,
                default=spec.get("default"),
                enum=spec.get("enum"),
            )
        )
    return params


def _json_type_to_param_type(js_type: str) -> ToolParameterType:
    return {
        "string": ToolParameterType.STRING,
        "integer": ToolParameterType.INTEGER,
        "number": ToolParameterType.FLOAT,
        "boolean": ToolParameterType.BOOLEAN,
        "array": ToolParameterType.ARRAY,
        "object": ToolParameterType.OBJECT,
    }.get(js_type, ToolParameterType.STRING)


def _is_dangerous(risk: RiskLevel) -> bool:
    return risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}


# Import settings lazily so this module can be imported before settings is configured.
try:
    from app.core.config import settings  # noqa: F401
except Exception:

    class _Settings:
        external_action_timeout_seconds = 60

    settings = _Settings()  # type: ignore
