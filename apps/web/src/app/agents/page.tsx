"use client";

import { useEffect, useState } from "react";
import { Bot, Plus, Trash2 } from "lucide-react";
import { createAgent, deleteAgent, fetchAgents, updateAgent } from "@/lib/api";
import type { Agent } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; agents: Agent[] }
  | { kind: "error"; message: string };

export default function AgentsPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [showForm, setShowForm] = useState(false);

  // Initial load — async callbacks only (avoids the set-state-in-effect rule).
  useEffect(() => {
    let cancelled = false;
    fetchAgents()
      .then((agents) => {
        if (!cancelled) setState({ kind: "ok", agents });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ kind: "error", message: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function reload() {
    setState({ kind: "loading" });
    fetchAgents()
      .then((agents) => setState({ kind: "ok", agents }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }

  async function handleDelete(id: string) {
    await deleteAgent(id);
    reload();
  }

  async function handleToggle(agent: Agent) {
    const next = agent.status === "active" ? "inactive" : "active";
    await updateAgent(agent.id, { status: next });
    reload();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            Agents
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Individual AI workers with roles, capabilities, and model
            configuration. Active agents can execute assigned tasks.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          <Plus className="h-4 w-4" />
          New agent
        </button>
      </div>

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
          {state.message}
        </p>
      )}

      {showForm && (
        <AgentForm onCreated={() => { setShowForm(false); reload(); }} />
      )}

      {state.kind === "loading" && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-40 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800"
            />
          ))}
        </div>
      )}

      {state.kind === "ok" && state.agents.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <Bot className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            No agents yet. Create your first agent to define a role, a system
            prompt, and the model it uses.
          </p>
        </div>
      )}

      {state.kind === "ok" && state.agents.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {state.agents.map((agent) => (
            <div
              key={agent.id}
              className="flex flex-col rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <Bot className="h-5 w-5 text-zinc-400" />
                  <h3 className="font-semibold text-zinc-900 dark:text-zinc-100">
                    {agent.name}
                  </h3>
                </div>
                <StatusBadge status={agent.status} />
              </div>
              {agent.role && (
                <p className="mt-1 text-xs uppercase tracking-wide text-zinc-500">
                  {agent.role}
                </p>
              )}
              {agent.description && (
                <p className="mt-2 line-clamp-2 text-sm text-zinc-600 dark:text-zinc-400">
                  {agent.description}
                </p>
              )}
              <div className="mt-3 flex flex-wrap gap-1.5">
                <span className="rounded-md bg-zinc-100 px-2 py-0.5 font-mono text-[11px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                  {agent.provider}
                </span>
                <span className="rounded-md bg-zinc-100 px-2 py-0.5 font-mono text-[11px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                  {agent.model_name}
                </span>
              </div>
              <div className="mt-4 flex items-center gap-2 border-t border-zinc-100 pt-3 dark:border-zinc-800">
                <button
                  onClick={() => handleToggle(agent)}
                  className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
                >
                  {agent.status === "active" ? "Deactivate" : "Activate"}
                </button>
                <button
                  onClick={() => handleDelete(agent.id)}
                  aria-label={`Delete ${agent.name}`}
                  className="ml-auto rounded-md p-1.5 text-zinc-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AgentForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [description, setDescription] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [provider, setProvider] = useState("mock");
  const [modelName, setModelName] = useState("mock-model");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createAgent({
        name,
        role: role || null,
        description: description || null,
        system_prompt: systemPrompt || null,
        provider,
        model_name: modelName,
        status: "active",
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create agent");
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
        Create agent
      </h2>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field label="Name" required>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className={inputCls}
            placeholder="e.g. market-analyst"
          />
        </Field>
        <Field label="Role">
          <input
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className={inputCls}
            placeholder="e.g. analyst"
          />
        </Field>
        <Field label="Provider">
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className={inputCls}
          >
            <option value="mock">mock</option>
            <option value="openai">openai</option>
            <option value="anthropic">anthropic</option>
          </select>
        </Field>
        <Field label="Model">
          <input
            value={modelName}
            onChange={(e) => setModelName(e.target.value)}
            className={inputCls}
            placeholder="e.g. gpt-4o"
          />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Description">
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className={inputCls}
              rows={2}
            />
          </Field>
        </div>
        <div className="sm:col-span-2">
          <Field label="System prompt">
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              className={inputCls}
              rows={3}
              placeholder="Base instructions the agent follows on every task."
            />
          </Field>
        </div>
      </div>

      {error && (
        <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>
      )}

      <div className="mt-4 flex items-center gap-2">
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900"
        >
          {busy ? "Creating…" : "Create agent"}
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