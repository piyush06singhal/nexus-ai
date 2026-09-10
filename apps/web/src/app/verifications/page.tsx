"use client";

import { useEffect, useState } from "react";
import { Play, ShieldCheck } from "lucide-react";
import { fetchVerifications, verifyExecution } from "@/lib/api";
import type { VerificationRun, VerificationStatus } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; runs: VerificationRun[] }
  | { kind: "error"; message: string };

const STATUS_OPTIONS: VerificationStatus[] = [
  "pass",
  "fail",
  "partial",
  "uncertain",
];

export default function VerificationsPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [filter, setFilter] = useState<VerificationStatus | "all">("all");

  useEffect(() => {
    let cancelled = false;
    fetchVerifications(filter === "all" ? undefined : filter)
      .then((res) => {
        if (!cancelled) setState({ kind: "ok", runs: res.runs });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ kind: "error", message: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, [filter]);

  function reload() {
    fetchVerifications(filter === "all" ? undefined : filter)
      .then((res) => setState({ kind: "ok", runs: res.runs }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }

  const runs = state.kind === "ok" ? state.runs : [];
  const passCount = runs.filter((r) => r.status === "pass").length;
  const avgScore =
    runs.length > 0 ? runs.reduce((acc, r) => acc + (r.score ?? 0), 0) / runs.length : 0;
  const passRate = runs.length > 0 ? passCount / runs.length : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
          Verifications
        </h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Results of deterministic and model-based verification over agent,
          workflow, and orchestration outputs.
        </p>
      </div>

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
          {state.message}
        </p>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Runs" value={String(runs.length)} />
        <Stat label="Pass rate" value={`${(passRate * 100).toFixed(1)}%`} />
        <Stat label="Passed" value={String(passCount)} />
        <Stat label="Avg score" value={avgScore.toFixed(2)} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {(["all", ...STATUS_OPTIONS] as const).map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition ${
              filter === s
                ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900"
                : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      <TriggerPanel onDone={reload} />

      {state.kind === "loading" && (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-16 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
          ))}
        </div>
      )}

      {state.kind === "ok" && runs.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <ShieldCheck className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            No verification runs yet. Runs are created when outputs are verified.
          </p>
        </div>
      )}

      {state.kind === "ok" && runs.length > 0 && (
        <div className="space-y-2">
          {runs.map((run) => (
            <div
              key={run.id}
              className="flex items-center gap-3 rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950"
            >
              <StatusBadge status={run.status} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">
                  {run.strategy_used || "no strategy"} · exec{" "}
                  {run.execution_id ? short(run.execution_id) : "—"}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-3 text-right text-xs text-zinc-500 dark:text-zinc-400">
                <span>score {run.score?.toFixed(2) ?? "—"}</span>
                <span>{new Date(run.created_at).toLocaleString()}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TriggerPanel({ onDone }: { onDone: () => void }) {
  const [executionId, setExecutionId] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!executionId.trim()) return;
    setBusy(true);
    setNote(null);
    try {
      const result = await verifyExecution({ execution_id: executionId.trim() });
      setNote(
        `${result.status.toUpperCase()} — score ${result.score.toFixed(2)}${result.reason ? ` · ${result.reason}` : ""}`,
      );
      setExecutionId("");
      onDone();
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Verification failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={executionId}
          onChange={(e) => setExecutionId(e.target.value)}
          placeholder="Execution ID to verify…"
          className="min-w-55 flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        />
        <button
          type="submit"
          disabled={busy || !executionId.trim()}
          className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          <Play className="h-4 w-4" />
          {busy ? "Verifying…" : "Verify execution"}
        </button>
      </div>
      {note && <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{note}</p>}
    </form>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <p className="text-[11px] uppercase tracking-wide text-zinc-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{value}</p>
    </div>
  );
}

function short(id: string): string {
  return `${id.slice(0, 8)}…`;
}