"use client";

import { useEffect, useState } from "react";
import { Brain, Plus, Search, Trash2 } from "lucide-react";
import {
  archiveMemory,
  cleanupExpiredMemories,
  createMemory,
  deleteMemory,
  fetchAgents,
  fetchMemories,
  searchMemories,
} from "@/lib/api";
import type {
  Agent,
  Memory,
  MemoryListResponse,
  MemoryStatus,
  MemoryType,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

const TYPE_OPTIONS: MemoryType[] = [
  "working",
  "episodic",
  "semantic",
  "procedural",
  "structured",
];

const STATUS_OPTIONS: MemoryStatus[] = ["active", "archived", "expired"];

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; data: MemoryListResponse; agents: Agent[] }
  | { kind: "error"; message: string };

export default function MemoriesPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [namespace, setNamespace] = useState("default");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<MemoryType | "all">("all");
  const [statusFilter, setStatusFilter] = useState<MemoryStatus | "all">("all");
  const [agentFilter, setAgentFilter] = useState("all");
  const [offset, setOffset] = useState(0);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const limit = 50;

  // Initial load + whenever a filter changes (except search which debounces).
  useEffect(() => {
    let cancelled = false;
    Promise.all([reloadMemories(), fetchAgents()])
      .then(([data, agents]) => {
        if (!cancelled) setState({ kind: "ok", data, agents });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ kind: "error", message: err.message });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [namespace, typeFilter, statusFilter, agentFilter, offset, activeQuery]);

  function reloadMemories(): Promise<MemoryListResponse> {
    if (activeQuery.trim()) {
      return searchMemories({
        query: activeQuery,
        namespace,
        owner_id: agentFilter === "all" ? undefined : agentFilter,
        memory_types: typeFilter === "all" ? undefined : [typeFilter],
        top_k: limit,
      }).then((results) => ({ memories: results.map((r) => r.memory), total: results.length }));
    }
    return fetchMemories({
      namespace,
      owner_id: agentFilter === "all" ? undefined : agentFilter,
      type: typeFilter === "all" ? undefined : typeFilter,
      status: statusFilter === "all" ? undefined : statusFilter,
      limit,
      offset,
    });
  }

  function reload() {
    setState((s) => ({ ...s, kind: "loading" }));
    Promise.all([reloadMemories(), fetchAgents()])
      .then(([data, agents]) => setState({ kind: "ok", data, agents }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }

  async function handleCreate(input: {
    namespace: string;
    type: MemoryType;
    content: string;
    summary?: string;
    importance: number;
    confidence: number;
  }) {
    setBusy(true);
    setError(null);
    try {
      await createMemory(input);
      setShowForm(false);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create memory");
    } finally {
      setBusy(false);
    }
  }

  async function handleArchive(memory: Memory) {
    setBusy(true);
    setError(null);
    try {
      await archiveMemory(memory.id);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to archive memory");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(memory: Memory) {
    setBusy(true);
    setError(null);
    try {
      await deleteMemory(memory.id);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete memory");
    } finally {
      setBusy(false);
    }
  }

  async function handleCleanup() {
    setBusy(true);
    setError(null);
    try {
      const res = await cleanupExpiredMemories();
      setError(
        res.expired_count > 0
          ? `Cleaned up ${res.expired_count} expired memories.`
          : null,
      );
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cleanup failed");
    } finally {
      setBusy(false);
    }
  }

  const agents = state.kind === "ok" ? state.agents : [];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            Memories
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            The persistent knowledge store shared by agents — episodic,
            semantic, procedural, and working memory.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleCleanup}
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            <Trash2 className="h-4 w-4" />
            Cleanup expired
          </button>
          <button
            onClick={() => setShowForm((v) => !v)}
            className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            <Plus className="h-4 w-4" />
            New memory
          </button>
        </div>
      </div>

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
          {error}
        </p>
      )}

      {/* Controls */}
      <div className="grid gap-3 rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={namespace}
            onChange={(e) => {
              setNamespace(e.target.value);
              setOffset(0);
            }}
            className="rounded-md border border-zinc-300 px-3 py-2 text-sm text-zinc-700 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
          >
            <option value="default">default</option>
            <option value="teamA">teamA</option>
            <option value="teamB">teamB</option>
          </select>

          <div className="relative min-w-[220px] flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  setActiveQuery(searchQuery);
                  setOffset(0);
                }
              }}
              placeholder="Search memories… (Enter to run hybrid search)"
              className="w-full rounded-md border border-zinc-300 bg-white py-2 pl-10 pr-3 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            />
          </div>

          <select
            value={agentFilter}
            onChange={(e) => {
              setAgentFilter(e.target.value);
              setOffset(0);
            }}
            className="rounded-md border border-zinc-300 px-3 py-2 text-sm text-zinc-700 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
          >
            <option value="all">All agents</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {(["all", ...TYPE_OPTIONS] as const).map((t) => (
            <button
              key={t}
              onClick={() => {
                setTypeFilter(t);
                setOffset(0);
              }}
              className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition ${
                typeFilter === t
                  ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900"
                  : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400"
              }`}
            >
              {t}
            </button>
          ))}
          <span className="mx-1 h-4 w-px bg-zinc-300 dark:bg-zinc-700" />
          {(["all", ...STATUS_OPTIONS] as const).map((s) => (
            <button
              key={s}
              onClick={() => {
                setStatusFilter(s);
                setOffset(0);
              }}
              className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition ${
                statusFilter === s
                  ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900"
                  : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {showForm && (
        <MemoryForm
          defaultNamespace={namespace}
          onCreated={handleCreate}
          onCancel={() => setShowForm(false)}
        />
      )}

      {state.kind === "loading" && (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
          ))}
        </div>
      )}

      {state.kind === "ok" && state.data.memories.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <Brain className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            No memories yet in this view. Memories are auto-extracted when agents
            complete tasks, or you can create one manually.
          </p>
        </div>
      )}

      {state.kind === "ok" && (
        <>
          <div className="space-y-3">
            {state.data.memories.map((memory) => (
              <MemoryRow
                key={memory.id}
                memory={memory}
                agents={agents}
                disabled={busy}
                onArchive={() => handleArchive(memory)}
                onDelete={() => handleDelete(memory)}
              />
            ))}
          </div>

          {/* Pagination: only meaningful when not in active search mode. */}
          {!activeQuery && state.data.total > limit && (
            <div className="flex items-center justify-between text-sm text-zinc-500 dark:text-zinc-400">
              <button
                onClick={() => setOffset((o) => Math.max(0, o - limit))}
                disabled={offset === 0}
                className="rounded-md border border-zinc-300 px-3 py-1.5 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
              >
                Previous
              </button>
              <span>
                Showing {offset + 1}–{Math.min(offset + limit, state.data.total)} of{" "}
                {state.data.total}
              </span>
              <button
                onClick={() => setOffset((o) => o + limit)}
                disabled={offset + limit >= state.data.total}
                className="rounded-md border border-zinc-300 px-3 py-1.5 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function MemoryRow({
  memory,
  agents,
  disabled,
  onArchive,
  onDelete,
}: {
  memory: Memory;
  agents: Agent[];
  disabled: boolean;
  onArchive: () => void;
  onDelete: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const owner =
    memory.owner_type === "agent"
      ? agents.find((a) => a.id === memory.owner_id)?.name ?? "Unknown agent"
      : "System";

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-3 p-4 text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <StatusBadge status={memory.type} />
            <StatusBadge status={memory.status} />
          </div>
          <p className="mt-1.5 line-clamp-2 text-sm text-zinc-800 dark:text-zinc-200">
            {memory.summary || memory.content}
          </p>
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            {owner} · ns:{memory.namespace} · accessed {memory.access_count}× ·{" "}
            {new Date(memory.created_at).toLocaleDateString()}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <span className="text-[11px] text-zinc-400">
            imp {memory.importance.toFixed(2)} · conf {memory.confidence.toFixed(2)}
          </span>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-zinc-100 bg-zinc-50/60 p-4 dark:border-zinc-800 dark:bg-zinc-900/30">
          <p className="text-sm text-zinc-800 dark:text-zinc-200">
            {memory.content}
          </p>

          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Meta label="Type" value={memory.type} />
            <Meta label="Source" value={memory.source_type ?? "—"} />
            <Meta
              label="Expires"
              value={
                memory.expires_at
                  ? new Date(memory.expires_at).toLocaleString()
                  : "Never"
              }
            />
            <Meta
              label="Last accessed"
              value={
                memory.last_accessed_at
                  ? new Date(memory.last_accessed_at).toLocaleString()
                  : "—"
              }
            />
          </div>

          {memory.metadata_json && Object.keys(memory.metadata_json).length > 0 && (
            <pre className="mt-3 max-h-48 overflow-auto rounded-md bg-zinc-100 p-3 text-xs text-zinc-800 dark:bg-zinc-900 dark:text-zinc-200">
              {JSON.stringify(memory.metadata_json, null, 2)}
            </pre>
          )}

          <div className="mt-3 flex gap-2">
            <button
              onClick={onArchive}
              disabled={disabled || memory.status === "archived"}
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 disabled:opacity-40 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              Archive
            </button>
            <button
              onClick={onDelete}
              disabled={disabled}
              className="inline-flex items-center gap-1 rounded-md border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-40 dark:border-red-900 dark:text-red-400 dark:hover:bg-red-950/30"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-zinc-400">{label}</p>
      <p className="mt-0.5 text-sm font-medium capitalize text-zinc-800 dark:text-zinc-200">
        {value}
      </p>
    </div>
  );
}

function MemoryForm({
  defaultNamespace,
  onCreated,
  onCancel,
}: {
  defaultNamespace: string;
  onCreated: (input: {
    namespace: string;
    type: MemoryType;
    content: string;
    summary?: string;
    importance: number;
    confidence: number;
  }) => Promise<void>;
  onCancel: () => void;
}) {
  const [namespace, setNamespace] = useState(defaultNamespace);
  const [type, setType] = useState<MemoryType>("semantic");
  const [content, setContent] = useState("");
  const [summary, setSummary] = useState("");
  const [importance, setImportance] = useState(0.5);
  const [confidence, setConfidence] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onCreated({
        namespace,
        type,
        content,
        summary: summary || undefined,
        importance,
        confidence,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create memory");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950"
    >
      <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
        Create memory
      </h2>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field label="Namespace" required>
          <input
            value={namespace}
            onChange={(e) => setNamespace(e.target.value)}
            required
            className={inputCls}
          />
        </Field>
        <Field label="Type" required>
          <select
            value={type}
            onChange={(e) => setType(e.target.value as MemoryType)}
            className={inputCls}
          >
            {TYPE_OPTIONS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </Field>
        <div className="sm:col-span-2">
          <Field label="Content" required>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              required
              rows={3}
              className={inputCls}
              placeholder="The fact, skill, or experience to remember…"
            />
          </Field>
        </div>
        <div className="sm:col-span-2">
          <Field label="Summary">
            <input
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              className={inputCls}
              placeholder="Short label (optional)"
            />
          </Field>
        </div>
        <Field label={`Importance — ${importance.toFixed(2)}`}>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={importance}
            onChange={(e) => setImportance(Number(e.target.value))}
            className="w-full"
          />
        </Field>
        <Field label={`Confidence — ${confidence.toFixed(2)}`}>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={confidence}
            onChange={(e) => setConfidence(Number(e.target.value))}
            className="w-full"
          />
        </Field>
      </div>

      {error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="mt-4 flex gap-2">
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900"
        >
          {busy ? "Creating…" : "Create memory"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

const inputCls =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-zinc-500 dark:text-zinc-400">
        {label}
        {required && <span className="text-red-500"> *</span>}
      </span>
      {children}
    </label>
  );
}