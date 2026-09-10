"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Play, Square } from "lucide-react";
import type {
  AgentAssignment,
  AgentMessage,
  AgentReview,
  Orchestration,
  OrchestrationContextEntry,
  OrchestrationResult,
  OrchestrationTask,
  OrchestrationTimelineEvent,
} from "@/lib/types";
import {
  cancelOrchestration,
  executeOrchestration,
  fetchAgents,
  fetchOrchestrationAgents,
  fetchOrchestrationContext,
  fetchOrchestrationMessages,
  fetchOrchestrationResults,
  fetchOrchestrationReviews,
  fetchOrchestrationTasks,
  fetchOrchestrationTimeline,
  getOrchestration,
} from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { ExecutionGraph } from "@/components/orchestration/ExecutionGraph";
import { CollaborationView } from "@/components/orchestration/CollaborationView";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; orch: Orchestration }
  | { kind: "error"; message: string };

function formatJSON(value: unknown): string {
  if (value == null) return "—";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export default function OrchestrationDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [tasks, setTasks] = useState<OrchestrationTask[]>([]);
  const [assignments, setAssignments] = useState<AgentAssignment[]>([]);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [results, setResults] = useState<OrchestrationResult[]>([]);
  const [context, setContext] = useState<OrchestrationContextEntry[]>([]);
  const [reviews, setReviews] = useState<AgentReview[]>([]);
  const [timeline, setTimeline] = useState<OrchestrationTimelineEvent[]>([]);
  const [agentNames, setAgentNames] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const orch = await getOrchestration(id);
        if (cancelled) return;
        setState({ kind: "ok", orch });
        const agents = await fetchAgents();
        const names: Record<string, string> = {};
        for (const a of agents) names[a.id] = a.name;
        if (cancelled) return;
        setAgentNames(names);
      } catch (err) {
        if (!cancelled)
          setState({ kind: "error", message: (err as Error).message });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  // Load all the detail collections once the orchestration exists.
  useEffect(() => {
    if (state.kind !== "ok") return;
    let cancelled = false;
    Promise.all([
      fetchOrchestrationTasks(id),
      fetchOrchestrationAgents(id),
      fetchOrchestrationMessages(id),
      fetchOrchestrationResults(id),
      fetchOrchestrationContext(id),
      fetchOrchestrationReviews(id),
      fetchOrchestrationTimeline(id),
    ])
      .then(([t, a, m, r, c, rv, tl]) => {
        if (cancelled) return;
        setTasks(t);
        setAssignments(a);
        setMessages(m);
        setResults(r);
        setContext(c);
        setReviews(rv);
        setTimeline(tl);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [state.kind, id]);

  async function run() {
    if (state.kind !== "ok") return;
    setBusy(true);
    setError(null);
    try {
      const next = await executeOrchestration(state.orch.id);
      setState({ kind: "ok", orch: next });
      const agents = await fetchAgents();
      const names: Record<string, string> = {};
      for (const a of agents) names[a.id] = a.name;
      setAgentNames(names);
      const [t, a, m, r, c, rv, tl] = await Promise.all([
        fetchOrchestrationTasks(id),
        fetchOrchestrationAgents(id),
        fetchOrchestrationMessages(id),
        fetchOrchestrationResults(id),
        fetchOrchestrationContext(id),
        fetchOrchestrationReviews(id),
        fetchOrchestrationTimeline(id),
      ]);
      setTasks(t);
      setAssignments(a);
      setMessages(m);
      setResults(r);
      setContext(c);
      setReviews(rv);
      setTimeline(tl);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Execution failed");
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (state.kind !== "ok") return;
    setBusy(true);
    setError(null);
    try {
      const next = await cancelOrchestration(state.orch.id);
      setState({ kind: "ok", orch: next });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cancel failed");
    } finally {
      setBusy(false);
    }
  }

  if (state.kind === "loading") {
    return (
      <div className="space-y-3">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-20 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800"
          />
        ))}
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
        {state.message}
      </p>
    );
  }

  const orch = state.orch;
  const canRun = ["created", "planned", "failed"].includes(orch.status);
  const canCancel = ["created", "planning", "planned", "assigning", "running"].includes(
    orch.status,
  );
  const metrics = orch.metrics ?? {};

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            {orch.objective}
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            {orch.strategy} strategy · {(orch.selected_agents ?? []).length} agents
            selected
            {orch.duration_ms != null && ` · ${orch.duration_ms.toFixed(0)}ms`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={orch.status} />
          {canCancel && (
            <button
              onClick={() => void cancel()}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              <Square className="h-3.5 w-3.5" />
              Cancel
            </button>
          )}
          {canRun && (
            <button
              onClick={() => void run()}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900"
            >
              <Play className="h-3.5 w-3.5" />
              {busy ? "Running…" : "Execute"}
            </button>
          )}
        </div>
      </div>

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
          {error}
        </p>
      )}

      {orch.final_result && (() => {
        const fr = orch.final_result as Record<string, unknown>;
        const findings = (fr.findings ?? []) as Array<Record<string, unknown>>;
        const conflicts = (fr.conflicts ?? []) as Array<Record<string, unknown>>;
        return (
          <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              Final result
            </h2>
            <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">
              {typeof fr.summary === "string" ? fr.summary : ""}
            </p>
            {findings.length > 0 && (
              <ul className="mt-3 space-y-2">
                {findings.map((f, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 rounded-lg border border-zinc-100 bg-zinc-50/60 p-3 dark:border-zinc-800 dark:bg-zinc-900/30"
                  >
                    <span className="flex-1 text-sm text-zinc-800 dark:text-zinc-200">
                      {String(f.finding ?? "")}
                    </span>
                    <span className="font-mono text-[11px] text-zinc-400">
                      {typeof f.agent_id === "string" ? f.agent_id.slice(0, 8) : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {conflicts.length > 0 && (
              <div className="mt-3 rounded-md border border-yellow-200 bg-yellow-50 p-3 text-xs text-yellow-700 dark:border-yellow-900 dark:bg-yellow-950/30 dark:text-yellow-300">
                <p className="font-semibold">Conflicts detected:</p>
                <ul className="mt-1 list-inside list-disc">
                  {conflicts.map((c, i) => (
                    <li key={i}>{String(c.field ?? "")}</li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        );
      })()}

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            Execution graph
          </h2>
          <div className="mt-4">
            <ExecutionGraph
              tasks={tasks}
              assignments={assignments}
              agentNames={agentNames}
            />
          </div>
        </section>

        <div className="space-y-6">
          <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              Metrics
            </h2>
            <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
              <MetricItem label="Tasks" value={String(metrics.tasks_total ?? "—")} />
              <MetricItem
                label="Completed"
                value={String(metrics.tasks_completed ?? "—")}
              />
              <MetricItem label="Failed" value={String(metrics.tasks_failed ?? "—")} />
              <MetricItem
                label="Agents"
                value={String(metrics.agents_used ?? "—")}
              />
              <MetricItem label="Messages" value={String(metrics.messages ?? "—")} />
              <MetricItem
                label="Retries"
                value={String(metrics.retries ?? "—")}
              />
            </dl>
          </section>

          <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              Collaboration
            </h2>
            <div className="mt-4">
              <CollaborationView
                messages={messages}
                reviews={reviews}
                agentNames={agentNames}
              />
            </div>
          </section>

          {timeline.length > 0 && (
            <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
              <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                Timeline
              </h2>
              <ol className="mt-3 space-y-2">
                {timeline.map((ev, i) => (
                  <li key={i} className="flex items-start gap-3">
                    <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-zinc-300 dark:bg-zinc-600" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-zinc-800 dark:text-zinc-200">
                        {ev.description}
                      </p>
                      <p className="text-[11px] text-zinc-400">
                        {ev.event_type}
                        {ev.status ? ` · ${ev.status}` : ""} ·{" "}
                        {new Date(ev.timestamp).toLocaleString()}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            Results ({results.length})
          </h2>
          <ul className="mt-3 space-y-2">
            {results.map((r) => (
              <li
                key={r.id}
                className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800"
              >
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[11px] text-zinc-400">
                    {r.agent_id?.slice(0, 8) ?? "—"}
                  </span>
                  {r.confidence != null && (
                    <span className="text-[11px] text-zinc-400">
                      confidence {Math.round(r.confidence * 100)}%
                    </span>
                  )}
                </div>
                {r.content && (
                  <p className="mt-1 text-sm text-zinc-700 dark:text-zinc-300">
                    {r.content}
                  </p>
                )}
                {r.structured_data && (
                  <pre className="mt-2 max-h-40 overflow-auto rounded bg-zinc-50 p-2 font-mono text-[11px] text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
                    {formatJSON(r.structured_data)}
                  </pre>
                )}
              </li>
            ))}
            {results.length === 0 && (
              <li className="text-sm text-zinc-500 dark:text-zinc-400">
                No results produced yet.
              </li>
            )}
          </ul>
        </section>

        <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            Shared context ({context.length})
          </h2>
          <div className="mt-3 flex max-h-112 flex-col gap-2 overflow-auto">
            {context.map((c) => (
              <div
                key={c.id}
                className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800"
              >
                <div className="flex items-center gap-2">
                  <span className="truncate font-mono text-[11px] text-zinc-500 dark:text-zinc-400">
                    {c.key}
                  </span>
                  <span className="ml-auto rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                    {c.kind}
                  </span>
                </div>
                {c.value != null && (
                  <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-zinc-600 dark:text-zinc-400">
                    {formatJSON(c.value)}
                  </pre>
                )}
              </div>
            ))}
            {context.length === 0 && (
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                No shared context for this orchestration.
              </p>
            )}
          </div>
        </section>
      </div>

      {orch.execution_graph && (
        <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            Execution graph (raw)
          </h2>
          <pre className="mt-3 max-h-96 overflow-auto rounded bg-zinc-50 p-3 font-mono text-[11px] text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
            {formatJSON(orch.execution_graph)}
          </pre>
        </section>
      )}
    </div>
  );
}

function MetricItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-100 bg-zinc-50/60 p-3 dark:border-zinc-800 dark:bg-zinc-900/30">
      <dt className="text-[11px] uppercase tracking-wide text-zinc-400">{label}</dt>
      <dd className="mt-0.5 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
        {value}
      </dd>
    </div>
  );
}