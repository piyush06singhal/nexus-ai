"use client";

import { useEffect, useState } from "react";
import { Play, RefreshCw } from "lucide-react";
import {
  fetchExecutionDiagnosis,
  fetchExecutionRecoveries,
  recoverExecution,
} from "@/lib/api";
import type {
  FailureCategory,
  FailureDiagnosis,
  RecoveryAttempt,
  RecoveryState,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; attempts: RecoveryAttempt[]; diagnosis: FailureDiagnosis | null }
  | { kind: "error"; message: string };

const RECOVERY_FLOW: RecoveryState[] = [
  "detected",
  "classified",
  "recovery_planned",
  "recovering",
  "retrying",
  "replanning",
  "fallback",
  "reverified",
  "recovered",
];

export default function RecoveriesPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [executionId, setExecutionId] = useState("");
  const [selectedExecution, setSelectedExecution] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!selectedExecution) return;
    let cancelled = false;
    Promise.all([fetchExecutionRecoveries(selectedExecution), safeDiagnosis(selectedExecution)])
      .then(([attempts, diagnosis]) => {
        if (!cancelled) setState({ kind: "ok", attempts, diagnosis });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ kind: "error", message: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, [selectedExecution]);

  async function handleTrigger() {
    if (!executionId.trim()) return;
    setBusy(true);
    setNote(null);
    try {
      const attempt = await recoverExecution(executionId.trim());
      setSelectedExecution(executionId.trim());
      setNote(`Recovery ${attempt.outcome ?? attempt.state} — ${attempt.reason ?? ""}`);
      setExecutionId("");
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Recovery failed");
    } finally {
      setBusy(false);
    }
  }

  const attempts = state.kind === "ok" ? state.attempts : [];
  const recovered = attempts.filter((a) => a.outcome === "recovered").length;
  const escalated = attempts.filter((a) => a.outcome === "escalated").length;
  const failed = attempts.filter((a) => a.outcome === "failed" || a.outcome === "aborted").length;
  const successRate = attempts.length > 0 ? recovered / attempts.length : 0;
  const categoryCounts: Partial<Record<FailureCategory, number>> = {};
  if (state.kind === "ok" && state.diagnosis?.category) {
    categoryCounts[state.diagnosis.category] = 1;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
          Recoveries
        </h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Failure diagnosis and bounded, policy-driven recovery. Recovery never
          broadens permissions and retries are gated by idempotency.
        </p>
      </div>

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
          {state.message}
        </p>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Attempts" value={String(attempts.length)} />
        <Stat label="Success rate" value={attempts.length ? `${(successRate * 100).toFixed(0)}%` : "—"} />
        <Stat label="Recovered" value={String(recovered)} />
        <Stat label="Escalated" value={String(escalated)} />
      </div>

      {attempts.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs uppercase tracking-wide text-zinc-400">Outcome:</span>
          <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
            {recovered} recovered
          </span>
          <span className="rounded-full bg-orange-100 px-3 py-1 text-xs font-medium text-orange-700 dark:bg-orange-900/40 dark:text-orange-300">
            {escalated} escalated
          </span>
          <span className="rounded-full bg-red-100 px-3 py-1 text-xs font-medium text-red-700 dark:bg-red-900/40 dark:text-red-300">
            {failed} failed
          </span>
        </div>
      )}

      {/* Trigger */}
      <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={executionId}
            onChange={(e) => setExecutionId(e.target.value)}
            placeholder="Execution ID to recover…"
            className="min-w-55 flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
          <button
            onClick={handleTrigger}
            disabled={busy || !executionId.trim()}
            className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            <Play className="h-4 w-4" />
            {busy ? "Recovering…" : "Recover"}
          </button>
        </div>
        {note && <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{note}</p>}
      </div>

      {state.kind === "loading" && selectedExecution && (
        <div className="space-y-3">
          {[0, 1].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
          ))}
        </div>
      )}

      {selectedExecution === null && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <RefreshCw className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            Enter an execution ID above, or the recovery timeline will appear here.
          </p>
        </div>
      )}

      {state.kind === "ok" && attempts.length === 0 && selectedExecution && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            No recovery attempts recorded for this execution.
          </p>
        </div>
      )}

      {state.kind === "ok" && attempts.length > 0 && (
        <>
          {state.diagnosis && (
            <DiagnosisCard diagnosis={state.diagnosis} categoryCounts={categoryCounts} />
          )}
          <div className="space-y-2">
            {attempts.map((a) => (
              <TimelineRow key={a.id} attempt={a} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function DiagnosisCard({
  diagnosis,
  categoryCounts,
}: {
  diagnosis: FailureDiagnosis;
  categoryCounts: Partial<Record<FailureCategory, number>>;
}) {
  const topCategory = (Object.entries(categoryCounts) as [FailureCategory, number][])
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([cat]) => cat);

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
        Latest diagnosis
      </h2>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <StatusBadge status={diagnosis.category} />
        <span className="rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs font-medium capitalize text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
          severity {diagnosis.severity}
        </span>
        <span className="text-xs text-zinc-500 dark:text-zinc-400">
          confidence {diagnosis.confidence.toFixed(2)} · retryable{" "}
          {diagnosis.retryable ? "yes" : "no"}
        </span>
      </div>
      {diagnosis.root_cause && (
        <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">
          <span className="font-medium">Root cause:</span> {diagnosis.root_cause}
        </p>
      )}
      {diagnosis.recommended_strategy && (
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Recommended strategy: <span className="font-medium">{diagnosis.recommended_strategy}</span>
        </p>
      )}
      {topCategory.length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-[11px] uppercase tracking-wide text-zinc-400">
            Failure categories
          </p>
          <div className="flex flex-wrap gap-1.5">
            {topCategory.map((c) => (
              <StatusBadge key={c} status={c} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TimelineRow({ attempt }: { attempt: RecoveryAttempt }) {
  const [expanded, setExpanded] = useState(false);
  const currentIndex = RECOVERY_FLOW.indexOf(attempt.state);

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-3 p-4 text-left"
      >
        <StatusBadge status={attempt.state} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-zinc-800 dark:text-zinc-200">
            {attempt.strategy ?? "recovery"} · attempt #{attempt.attempt_number}
          </p>
          <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">{attempt.reason}</p>
        </div>
        <span className="shrink-0 text-xs text-zinc-400">
          {attempt.outcome ?? "in progress"}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-zinc-100 bg-zinc-50/60 p-4 dark:border-zinc-800 dark:bg-zinc-900/30">
          {/* State machine timeline */}
          <div className="flex flex-wrap items-center gap-1">
            {RECOVERY_FLOW.map((state, idx) => (
              <div key={state} className="flex items-center gap-1">
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                    currentIndex >= idx
                      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                      : "bg-zinc-100 text-zinc-400 dark:bg-zinc-800"
                  }`}
                >
                  {state.replace("_", " ")}
                </span>
                {idx < RECOVERY_FLOW.length - 1 && (
                  <span className="text-zinc-300 dark:text-zinc-600">→</span>
                )}
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
            Started {attempt.started_at ? new Date(attempt.started_at).toLocaleString() : "—"}
            {attempt.completed_at
              ? ` · completed ${new Date(attempt.completed_at).toLocaleString()}`
              : ""}
          </p>
        </div>
      )}
    </div>
  );
}

/** Fetch a diagnosis, tolerating 404 (no diagnosis recorded yet). */
async function safeDiagnosis(executionId: string): Promise<FailureDiagnosis | null> {
  try {
    return await fetchExecutionDiagnosis(executionId);
  } catch {
    return null;
  }
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <p className="text-[11px] uppercase tracking-wide text-zinc-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{value}</p>
    </div>
  );
}