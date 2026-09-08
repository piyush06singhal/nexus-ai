"""AI abstraction layer.

Exposes the provider-agnostic interface and registry. Application code
should import providers from here rather than vendor SDKs directly:

    from app.ai import get_provider
    provider = get_provider("openai")
"""

from app.ai.base import BaseModelProvider
from app.ai.interfaces import ModelProvider
from app.ai.registry import get_provider, list_providers, register_provider
from app.ai.types import (
    ChatMessage,
    GenerationOptions,
    ModelResponse,
    TokenUsage,
)

__all__ = [
    "BaseModelProvider",
    "ChatMessage",
    "GenerationOptions",
    "ModelProvider",
    "ModelResponse",
    "TokenUsage",
    "get_provider",
    "list_providers",
    "register_provider",
]
