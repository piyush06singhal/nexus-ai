# NEXUS — Memory System Reference

Phase 4 gives NEXUS agents a **persistent, provider-independent memory**. The system stores five kinds of memory in a single table, isolates them by namespace and ownership, retrieves them with hybrid (semantic + keyword + recency + importance) ranking, and is wired into the Agent Runtime so agents recall prior work across sessions and tasks.

Two places the memory system touches the agent loop:

1. **Before** building context, the runtime queries for memories relevant to the current task and injects a `[Memory]`-labeled section into the system prompt.
2. **After** an execution completes, the runtime extracts and persists new memories (episodic always; semantic on success with output; procedural when tools were used).

Both hooks are best-effort — a memory failure never blocks an agent from running.

---

## 1. Memory types

Every memory has one of five `type`s (the discriminator column on the single `memories` table):

| Type | Meaning | Example |
| ---- | ------- | ------- |
| `working` | Short-term, task-local context; expires via TTL | "currently revising the Q3 forecast" |
| `episodic` | Past experiences and event sequences | "On 2026-09-09 I completed 'Summarize Q1' in 1.2s" |
| `semantic` | Facts, knowledge, relationships | "Sales grew 12% in Q1" |
| `procedural` | How-to knowledge, skills, patterns | "To compute totals, call the calculator tool" |
| `structured` | JSON records (entities, relations) | `{"entity": "product_x", "attr": "price", "value": 99}` |

Each memory also carries:

- **`status`** — `active`, `archived`, or `expired` (expired status is set by TTL cleanup).
- **`owner_type` / `owner_id`** — `agent` (the agent that owns the memory) or `system`.
- **`source_type` / `source_id`** — where the memory came from: `execution` / `user_input` / `tool_output` / `imported`. When `execution`, `source_id` is the `AgentExecution.id`, so a memory can be traced back to its origin.
- **`namespace`** — the isolation key (e.g. `default`, `teamA`). Retrieval and listing are always namespace-scoped.
- **`importance` / `confidence`** — 0–1 scores used in ranking and write gating.
- **`access_count` / `last_accessed_at`** — usage tracking, incremented on retrieval.
- **`expires_at`** — TTL for working (and any time-bounded) memory.

---

## 2. Storage & isolation

All memory lives in **one `memories` table** (migration `0005_memories`), with composite indexes for the common query shapes:

- `(namespace, owner_id)` — owner-scoped reads
- `(namespace, type)`, `(namespace, status)` — filterable listing
- `(namespace, created_at)` — recency-ordered listing
- `(expires_at, status)` — TTL cleanup scans

**Namespace isolation** is enforced by construction: every `MemoryService.list` and every `HybridRetriever.retrieve` filters on `namespace`. Memories in `teamA` are invisible to queries scoped to `teamB`, even with identical content. Ownership (`owner_id`) is an additional, optional scoping layer within a namespace.

Embeddings are stored as **text-serialized JSON vectors** in the `embedding` column. Cosine similarity is computed in Python — a deliberate choice to avoid a hard `pgvector` dependency during the Python 3.14 bootstrap. At scale this path can be replaced by a native vector index without changing any caller.

---

## 3. Embedding abstraction

`app/memory/embedding.py` defines a minimal provider protocol:

```python
class EmbeddingProvider(Protocol):
    @property
    def dimensions(self) -> int: ...
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
```

Two implementations:

- **`MockEmbeddingProvider`** — deterministic, hash-based, 128-dim. The same text always maps to the same vector, and lexically-similar tokens share dimensions so cosine similarity rises with word overlap. No network or API key — semantic retrieval is fully exercised in tests and local dev. This is what `MEMORY_EMBEDDING_PROVIDER=mock` selects.
- **`OpenAIEmbeddingProvider`** — a scaffold for production (1536-dim, `text-embedding-3-small`). Concrete network calls are intentionally deferred so the system stays testable without credentials.

`get_embedding_provider(settings)` returns a provider only when `memory_embedding_provider` is `"mock"` or `"openai"`; otherwise it returns `None` and the retriever scores purely by keyword/recency/importance. Embeddings are therefore an **optional enhancement**, never a hard requirement.

---

## 4. Hybrid retrieval

`app/memory/retrieval.py` implements `HybridRetriever`. Given a query (and scope filters), it:

1. **Filters candidates** by namespace, owner, memory type, and status, excluding expired memories (unless `include_expired=True`).
2. When an embedding provider is present, embeds the query once.
3. **Scores each candidate** as a weighted combination:

```
final_score =
    W_semantic · max(semantic_cosine, keyword_dice)     # W = 0.4 default
  + W_recency  · recency                                 #    0.2
  + W_importance · importance                            #    0.2
  + W_confidence  · confidence                           #    0.2
  × type_multiplier (if the policy defines per-type weights)
```

- **semantic** — cosine similarity of the query and memory embeddings (0 when no provider or no stored embedding).
- **keyword** — Dice-coefficient overlap of query and content tokens (`2·|A∩B| / (|A|+|B|)`). Used as a fallback when embeddings are absent, and combined with semantic by taking the max.
- **recency** — exponential half-life decay: `2^(−age_hours / 72)`. Fresh memories score higher; the half-life is configurable.
- **importance** and **confidence** — direct field values.

4. Filters below `min_score`, sorts descending, and returns the top `top_k` `MemoryRetrievalResult`s. Each result carries a **`breakdown`** dict (`semantic`, `keyword`, `recency`, `importance`, `confidence`, `type_multiplier`) so a caller can see exactly why a memory ranked.

### Policies (`app/memory/policies.py`)

- **`RetrievalPolicy`** — `context_budget` (soft cap on chars of memory content injected into a context window), `relevance_threshold` (minimum score), `max_memories` (hard cap), and optional `type_weights`.
- **`WritePolicy`** — `min_importance` (don't store trivia), `dedup_threshold` (cosine above this is a near-duplicate), `max_working` (cap on `working` memories per owner; oldest pruned), `default_ttl_hours`.

Both have `from_settings()` builders so runtime behavior is driven by config.

---

## 5. Extraction from executions

`app/memory/extraction.py::extract_memories_from_execution` turns a completed `AgentExecution` into persistent memories:

- **Episodic** — always. "Agent X completed task 'Y' in Tms ([status])."
- **Semantic** — on success when there is output data. Distills the output into a factual knowledge memory.
- **Procedural** — when the execution used tools. Captures which tools were used and why, as reusable know-how.

Importance and confidence are derived from the execution (success, output presence, tool use, token usage). Memories are embedded in bulk when a provider is present (`zip(..., strict=True)` across the created rows).

The `MemoryService.extract_and_store` method wraps this with store-time gating: it only stores memories above `min_importance`, de-dups against similar existing memories (`is_duplicate`), and prunes oversize working-memory sets per owner.

---

## 6. Runtime integration

In `app/runtime/runtime.py`, `execute_task` gains two hooks (both gated by `memory_extraction_enabled`, both wrapped so failures are logged, not raised):

**Before building context** — `_retrieve_memories` builds a query from the task's title/description and calls the `HybridRetriever` scoped to `namespace="default"` and `owner_id=agent.id`, capped by `RetrievalPolicy.max_memories` and `relevance_threshold`. The results are passed to `build_context(..., memories=...)`, which injects a `[Memory]` section (type + importance labeled) into the system prompt. Access is recorded on every memory actually injected.

**After execution completes** — `_extract_memories` calls `extract_and_store` with the execution and the set of tools used, persisting fresh episodic/semantic/procedural memories.

Because the runtime is synchronous and the memory layer is async, the two hooks bridge with `asyncio.run(...)` against the execution's own DB session — deterministic and testable.

```python
# build_context now accepts memories (Phase 4)
def build_context(agent, task, *, tool_definitions=None, memories=None) -> list[ChatMessage]:
    ...
    if memories:
        system_prompt += format_memory_context(memories)   # "[Memory] (type=.., importance=..) ..."
```

---

## 7. Service layer

`app/services/memory_service.py::MemoryService(db, embedding_provider=None)`:

- **CRUD** — `create` (embedding attached best-effort via `ensure_embedding`), `get`, `update`, `delete`, scoped `list` (returns `(memories, total)` using `func.count`).
- **Search** — `async search(MemorySearchRequest)` delegates to the `HybridRetriever`.
- **Lifecycle** — `archive`, `expire_working(owner_id)`, `cleanup_expired()` returns the number expired.
- **Extraction** — `async extract_and_store(execution, namespace, agent_id, used_tools)`.
- **Access tracking** — `record_access`, `record_access_many`.
- **Write gating helpers** — `_should_store`, `_find_similar`, `_prune_working` (dedup + importance + cap).
- `to_dict()` serializes a `Memory` row for API responses.

---

## 8. API reference

All endpoints live under `/api/v1/memories` (router in `app/api/v1/endpoints/memories.py`).

| Method | Path | Description |
| ------ | ---- | ----------- |
| `GET` | `/memories` | List memories. Query params: `namespace` (required), `owner_id`, `owner_type`, `type`, `status`, `limit` (≤200), `offset`. Returns `{memories, total}`. |
| `POST` | `/memories` | Create a memory. Body: `MemoryCreate`. Best-effort embedding attach. `201`. |
| `GET` | `/memories/{id}` | Fetch one memory. |
| `PATCH` | `/memories/{id}` | Update content/summary/status/importance/confidence/expires_at. |
| `DELETE` | `/memories/{id}` | Delete a memory. `204`. |
| `POST` | `/memories/search` | Hybrid search. Body: `{query, namespace, owner_id?, memory_types?, top_k?, min_score?}` → `[{memory, score, breakdown}]`. |
| `POST` | `/memories/{id}/archive` | Set status to `archived`. |
| `POST` | `/memories/cleanup` | Expire past-due TTL memories; returns `{expired_count}`. |

The literal `/search` and `/cleanup` routes are declared before the `/{memory_id}` parameter route so they are never shadowed by a UUID.

### Example

```bash
# List memories in the "default" namespace
curl 'localhost:8000/api/v1/memories?namespace=default&limit=20'

# Create a semantic memory manually
curl -X POST localhost:8000/api/v1/memories -H 'Content-Type: application/json' \
  -d '{"namespace":"default","type":"semantic","content":"Sales grew 12% in Q1",
       "summary":"Q1 growth","importance":0.8,"confidence":0.9}'

# Hybrid-search
curl -X POST localhost:8000/api/v1/memories/search -H 'Content-Type: application/json' \
  -d '{"query":"Q1 growth","namespace":"default","top_k":5}' | jq '.[0].breakdown'

# Expire anything past its TTL
curl -X POST localhost:8000/api/v1/memories/cleanup
```

---

## 9. Configuration

All memory settings live on the `Settings` singleton (environment variables / `.env`):

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `MEMORY_EMBEDDING_PROVIDER` | *(unset)* | `mock` or `openai` to enable semantic retrieval; unset = keyword-only. |
| `MEMORY_EMBEDDING_MODEL` | `text-embedding-3-small` | Model for the OpenAI provider scaffold. |
| `MEMORY_EMBEDDING_DIMENSIONS` | `1536` | Embedding dimension for the OpenAI provider scaffold. |
| `MEMORY_RETRIEVAL_WEIGHT_SEMANTIC` | `0.4` | Weight of the semantic/keyword component. |
| `MEMORY_RETRIEVAL_WEIGHT_RECENCY` | `0.2` | Weight of the recency component. |
| `MEMORY_RETRIEVAL_WEIGHT_IMPORTANCE` | `0.2` | Weight of the importance component. |
| `MEMORY_RETRIEVAL_WEIGHT_CONFIDENCE` | `0.2` | Weight of the confidence component. |
| `MEMORY_RETRIEVAL_CONTEXT_BUDGET` | `5000` | Max chars of memory content injected into a context window. |
| `MEMORY_RETRIEVAL_RELEVANCE_THRESHOLD` | `0.3` | Minimum hybrid score to retain a memory. |
| `MEMORY_RETRIEVAL_MAX_MEMORIES` | `20` | Hard cap on memories retrieved per query. |
| `MEMORY_WRITE_MIN_IMPORTANCE` | `0.1` | Don't store memories below this importance. |
| `MEMORY_WRITE_DEDUP_THRESHOLD` | `0.95` | Cosine above this marks a near-duplicate (skip storage). |
| `MEMORY_WRITE_MAX_WORKING` | `50` | Cap on `working` memories per owner (oldest pruned). |
| `MEMORY_WRITE_DEFAULT_TTL_HOURS` | `24` | TTL for working memory when none is given. |
| `MEMORY_EXTRACTION_ENABLED` | `true` | Auto-extract + retrieve memories in the runtime. |

---

## 10. Frontend

The `/memories` page (`apps/web/src/app/memories/page.tsx`) provides:

- A **namespace selector** (`default` / `teamA` / `teamB`) driving the active store.
- A **hybrid search** box (Enter runs `POST /memories/search`; an active query supersedes the type/status filters) and an **agent-owner filter**.
- **Type and status filter chips** (`all` / `working` / `episodic` / `semantic` / `procedural` / `structured`; `all` / `active` / `archived` / `expired`).
- A **memory list** — each card shows type + status badges, summary/content, owner, namespace, access count, creation date, and importance/confidence. Expanding reveals full content, source/expiry metadata, `metadata_json`, and **archive** / **delete** actions.
- A **New memory** form (namespace, type, content, summary, importance/confidence sliders).
- A **Cleanup expired** button and limit/offset **pagination** (only when not actively searching).

The API client (`apps/web/src/lib/api.ts`) adds `fetchMemories`, `createMemory`, `getMemory`, `updateMemory`, `deleteMemory`, `searchMemories`, `archiveMemory`, and `cleanupExpiredMemories`; shared types live in `apps/web/src/lib/types.ts`. The sidebar and dashboard nav include a **Memories** entry between Tools and Activity.

---

## 11. Observability & scale

- **Breakdown-driven ranking** — every retrieved memory reports which signals drove its score, matching the observability-first principle across NEXUS.
- **Source traceability** — `source_type`/`source_id` link a memory back to its originating execution.
- **Access tracking** — `access_count` + `last_accessed_at` quantify how often each memory is actually used.
- **Scale path** — embeddings-as-text + Python cosine is a deliberately deferred optimization. When memory volume warrants it, swap in a native vector index (e.g. pgvector) and a real embedding provider without changing the `EmbeddingProvider` protocol or any caller.