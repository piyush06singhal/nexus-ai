"""Provider registry for external integrations (Phase 10).

A provider is a deterministic adapter exposing a set of capabilities. The
registry mirrors ``app.ai.registry``: register by slug, resolve by slug. Mock
providers are registered at import time so tests, CI, and the demo scripts are
deterministic with no paid services. The generic HTTP connector is *not*
registered unless ``external_generic_http_connector_enabled`` is set (§14).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.core.config import settings
from app.external.types import AuthContext, AuthMethod, Capability, IntegrationCategory


@runtime_checkable
class IntegrationProvider(Protocol):
    """A provider adapter exposing capabilities to the external layer.

    All providers are deterministic, in-repo adapters in Phase 10. Real
    provider SDKs are an explicit Phase 11 hardening item; the protocol seam
    is already stable so swapping a mock for an SDK requires only a new class.
    """

    slug: str
    name: str
    category: IntegrationCategory
    auth_type: AuthMethod
    description: str = ""

    def secrets_required(self) -> list[str]:
        """Names of operator env vars / one-shot secrets this provider needs."""

    def capabilities(self) -> list[Capability]:
        """Capabilities this provider exposes."""

    def test(
        self, *, payload: dict[str, Any], auth: AuthContext, context: dict[str, Any]
    ) -> tuple[str, str]:
        """Return ``(ConnectionTestResult.value, message)``. Never secrets."""

    def execute(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        auth: AuthContext,
        connection: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute one capability. Raises ``ExternalProviderError`` on failure."""


@dataclass
class ProviderDescriptor:
    """Registry entry for a registered provider."""

    slug: str
    name: str
    category: IntegrationCategory
    auth_type: AuthMethod
    description: str = ""
    secrets_required: list[str] = field(default_factory=list)


# slug -> callable that builds the provider instance (mirror app/ai/registry).
_PROVIDER_FACTORIES: dict[str, type] = {}


def register_provider(name: str, factory: type) -> None:
    _PROVIDER_FACTORIES[name] = factory


def unregister_provider(name: str) -> None:
    _PROVIDER_FACTORIES.pop(name, None)


def get_provider(name: str) -> IntegrationProvider:
    if name not in _PROVIDER_FACTORIES:
        raise KeyError(f"Unknown external provider: {name!r}")
    return _PROVIDER_FACTORIES[name]()


def list_providers() -> list[str]:
    return sorted(_PROVIDER_FACTORIES)


def provider_descriptors() -> list[ProviderDescriptor]:
    out: list[ProviderDescriptor] = []
    for slug in list_providers():
        p = get_provider(slug)
        out.append(
            ProviderDescriptor(
                slug=p.slug,
                name=p.name,
                category=p.category,
                auth_type=p.auth_type,
                description=getattr(p, "description", ""),
                secrets_required=p.secrets_required(),
            )
        )
    return out


# Auto-register deterministic mock providers at import time.
def _register_builtin_providers() -> None:
    from app.external.providers import (  # local import to avoid cycles
        CalendarProvider,
        DevelopmentProvider,
        EmailProvider,
        GenericHTTPConnectorProvider,
        WebResearchProvider,
    )

    register_provider(EmailProvider.slug, EmailProvider)
    register_provider(CalendarProvider.slug, CalendarProvider)
    register_provider(DevelopmentProvider.slug, DevelopmentProvider)
    register_provider(WebResearchProvider.slug, WebResearchProvider)
    if settings.external_generic_http_connector_enabled:
        register_provider(GenericHTTPConnectorProvider.slug, GenericHTTPConnectorProvider)


_register_builtin_providers()
