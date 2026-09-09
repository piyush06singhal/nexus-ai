"""Provider registry.

A simple registry mapping provider name -> provider class/instance. This is
the seam that future agent-execution code uses to resolve a provider:

    provider = get_provider("openai")

Registering a provider just means adding it here (or calling
``register_provider``); no downstream code changes.
"""

from __future__ import annotations

from app.ai.interfaces import ModelProvider
from app.ai.providers.mock_provider import MockProvider
from app.ai.providers.openai_provider import OpenAIProvider

# name -> callable that builds a provider instance.
_PROVIDER_FACTORIES: dict[str, type[ModelProvider]] = {}


def register_provider(name: str, factory: type[ModelProvider]) -> None:
    """Register a provider class under the given name."""
    _PROVIDER_FACTORIES[name] = factory


def get_provider(name: str) -> ModelProvider:
    """Return a provider instance by name. Raises KeyError if unknown."""
    if name not in _PROVIDER_FACTORIES:
        raise KeyError(f"Unknown model provider: {name!r}")
    factory = _PROVIDER_FACTORIES[name]
    # Providers are constructed fresh per request; cheap and avoids state bleed.
    return factory()


def list_providers() -> list[str]:
    """Return the names of all registered providers."""
    return sorted(_PROVIDER_FACTORIES)


# Auto-register built-in providers at import time.
# MockProvider is registered alongside OpenAI so ``provider="mock"`` agents can
# be executed deterministically in tests and local dev without an API key.
register_provider(OpenAIProvider.name, OpenAIProvider)
register_provider(MockProvider.name, MockProvider)
