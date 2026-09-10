"use client";

import { useEffect, useState } from "react";
import { Bell, Check, X } from "lucide-react";
import {
  approveEscalation,
  fetchEscalations,
  rejectEscalation,
} from "@/lib/api";
import type { Escalation, EscalationState } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; escalations: Escalation[] }
  | { kind: "error"; message: string };

const STATE_OPTIONS: EscalationState[] = [
  "pending_human_review",
  "approved",
  "rejected",
];

export default function EscalationsPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [filter, setFilter] = useState<EscalationState | "all">("all");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchEscalations(filter === "all" ? undefined : filter)
      .then((res) => {
        if (!cancelled) setState({ kind: "ok", escalations: res.escalations });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ kind: "error", message: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, [filter]);

  function reload() {
    fetchEscalations(filter === "all" ? undefined : filter)
      .then((res) => setState({ kind: "ok", escalations: res.escalations }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }

  async function handleDecision(
    esc: Escalation,
    decision: "approve" | "reject",
    reason: string,
  ) {
    setBusy(true);
    setError(null);
    try {
      if (decision === "approve") await approveEscalation(esc.id, reason || undefined);
      else await rejectEscalation(esc.id, reason || undefined);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to record decision");
    } finally {
      setBusy(false);
    }
  }

  const pendingCount =
    state.kind === "ok"
      ? state.escalations.filter((e) => e.state === "pending_human_review").length
      : 0;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            Escalations
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Executions that could not recover safely, surfaced for human review.
            Approving never grants the agent new permissions.
          </p>
        </div>
        {state.kind === "ok" && pendingCount > 0 && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
            <Bell className="h-3.5 w-3.5" />
            {pendingCount} awaiting review
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {(["all", ...STATE_OPTIONS] as const).map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition ${
              filter === s
                ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900"
                : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400"
            }`}
          >
            {s.replaceAll("_", " ")}
          </button>
        ))}
      </div>

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
          {error}
        </p>
      )}

      {state.kind === "loading" && (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
          ))}
        </div>
      )}

      {state.kind === "ok" && state.escalations.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <Bell className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            No escalations in this view. Escalations appear when recovery cannot proceed safely.
          </p>
        </div>
      )}

      {state.kind === "ok" && state.escalations.length > 0 && (
        <div className="space-y-3">
          {state.escalations.map((esc) => (
            <EscalationRow key={esc.id} esc={esc} disabled={busy} onDecision={handleDecision} />
          ))}
        </div>
      )}
    </div>
  );
}

function EscalationRow({
  esc,
  disabled,
  onDecision,
}: {
  esc: Escalation;
  disabled: boolean;
  onDecision: (esc: Escalation, decision: "approve" | "reject", reason: string) => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function decide(decision: "approve" | "reject") {
    setBusy(true);
    try {
      await onDecision(esc, decision, note);
      setNote("");
    } finally {
      setBusy(false);
    }
  }

  const isPending = esc.state === "pending_human_review";

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between gap-3 p-4 text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <StatusBadge status={esc.state} />
            <StatusBadge status={esc.category} />
            <span className="text-[11px] uppercase tracking-wide text-zinc-400">
              severity {esc.severity}
            </span>
          </div>
          <p className="mt-1.5 text-sm font-medium text-zinc-800 dark:text-zinc-200">
            {esc.issue}
          </p>
          <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
            Execution {esc.execution_id ? short(esc.execution_id) : "—"} ·{" "}
            {new Date(esc.created_at).toLocaleString()}
          </p>
        </div>
        <span className="shrink-0 text-xs text-zinc-400">
          {expanded ? "collapse" : "expand"}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-zinc-100 bg-zinc-50/60 p-4 dark:border-zinc-800 dark:bg-zinc-900/30">
          <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
            <Meta label="Category" value={esc.category} />
            <Meta label="Workflow" value={esc.workflow_id ? short(esc.workflow_id) : "—"} />
            <Meta label="Orchestration" value={esc.orchestration_id ? short(esc.orchestration_id) : "—"} />
            <Meta
              label="Reviewed"
              value={esc.reviewed_at ? new Date(esc.reviewed_at).toLocaleString() : "Not yet"}
            />
          </div>

          {esc.context && Object.keys(esc.context).length > 0 && (
            <pre className="mt-3 max-h-40 overflow-auto rounded-md bg-zinc-100 p-3 text-xs text-zinc-800 dark:bg-zinc-900 dark:text-zinc-200">
              {JSON.stringify(esc.context, null, 2)}
            </pre>
          )}

          {esc.decision_reason && (
            <p className="mt-3 text-sm text-zinc-700 dark:text-zinc-300">
              <span className="font-medium">Decision note:</span> {esc.decision_reason}
            </p>
          )}

          {isPending && (
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Optional note for this decision…"
                className="min-w-55 flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
              />
              <button
                onClick={() => decide("approve")}
                disabled={disabled || busy}
                className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                <Check className="h-4 w-4" />
                Approve
              </button>
              <button
                onClick={() => decide("reject")}
                disabled={disabled || busy}
                className="inline-flex items-center gap-1.5 rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                <X className="h-4 w-4" />
                Reject
              </button>
            </div>
          )}
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

function short(id: string): string {
  return `${id.slice(0, 8)}…`;
}