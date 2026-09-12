"""Deterministic external provider adapters (Phase 10).

Each provider is an in-repo adapter behind the :class:`IntegrationProvider`
protocol: deterministic mock behaviour only, no paid services, no real network
in tests/CI/demos (spec §68–§70). Real provider SDKs are an explicit Phase 11
hardening item; the protocol seam is stable so swapping a mock for an SDK only
means a new class implementing the same surface.
"""

from __future__ import annotations

from app.external.providers.calendar import CalendarProvider
from app.external.providers.development import DevelopmentProvider
from app.external.providers.email import EmailProvider
from app.external.providers.http_connector import GenericHTTPConnectorProvider
from app.external.providers.web import WebResearchProvider

# The generic HTTP connector is registered in the provider registry only when
# ``external_generic_http_connector_enabled`` is set (§14); it stays importable
# here so the class exists but arbitrary outbound HTTP is never on by default.

__all__ = [
    "CalendarProvider",
    "DevelopmentProvider",
    "EmailProvider",
    "GenericHTTPConnectorProvider",
    "WebResearchProvider",
]
