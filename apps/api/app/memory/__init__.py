"""Memory system package (Phase 4).

Provides the provider-independent embedded memory layer used by the agent
runtime to persist, retrieve, and reason over information across sessions.
"""

from app.memory.embedding import (
    EmbeddingProvider,
    MockEmbeddingProvider,
    get_embedding_provider,
)
from app.memory.extraction import extract_memories_from_execution
from app.memory.policies import RetrievalPolicy, WritePolicy
from app.memory.retrieval import HybridRetriever, MemoryRetrievalResult

__all__ = [
    "EmbeddingProvider",
    "MockEmbeddingProvider",
    "get_embedding_provider",
    "HybridRetriever",
    "MemoryRetrievalResult",
    "RetrievalPolicy",
    "WritePolicy",
    "extract_memories_from_execution",
]
