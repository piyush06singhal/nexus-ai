"use client";

import { useEffect, useState } from "react";
import { BarChart3, Play } from "lucide-react";
import {
  checkRegression,
  compareEvaluationRuns,
  fetchEvaluationResults,
  fetchEvaluationRuns,
  runEvaluation,
} from "@/lib/api";
import type {
  EvaluationComparison,
  EvaluationResult,
  EvaluationRun,
  RegressionReport,
} from "@/lib/types";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; runs: EvaluationRun[] }
  | { kind: "error"; message: string };

export default function EvaluationsPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [expandedRun, setExpandedRun] = useState<string | null>(null);
  const [results, setResults] = useState<EvaluationResult[] | null>(null);
  const [compare, setCompare] = useState<{ a: string; b: string }>({ a: "", b: "" });
  const [comparison, setComparison] = useState<EvaluationComparison | null>(null);
  const [regression, setRegression] = useState<RegressionReport | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchEvaluationRuns()
      .then((res) => {
        if (!cancelled) setState({ kind: "ok", runs: res.runs });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ kind: "error", message: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function reload() {
    fetchEvaluationRuns()
      .then((res) => setState({ kind: "ok", runs: res.runs }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }

  async function handleRun() {
    setBusy(true);
    setNote(null);
    try {
      await runEvaluation({ use_default_dataset: true });
      setNote("Evaluation run started against the default dataset.");
      reload();
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Evaluation failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleExpand(runId: string) {
    if (expandedRun === runId) {
      setExpandedRun(null);
      setResults(null);
      return;
    }
    setExpandedRun(runId);
    setResults(null);
    try {
      setResults(await fetchEvaluationResults(runId));
    } catch {
      setResults([]);
    }
  }

  async function handleCompare(e: React.FormEvent) {
    e.preventDefault();
    if (!compare.a || !compare.b) return;
    setNote(null);
    try {
      const res = await compareEvaluationRuns(compare.a, compare.b);
      setComparison(res);
      const reg = await checkRegression(res.score_a, res.score_b);
      setRegression(reg);
      setNote(
        `Δ ${res.delta >= 0 ? "+" : ""}${res.delta.toFixed(3)} — ${
          res.regression ? "regression detected" : "no regression"
        }`,
      );
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Comparison failed");
    }
  }

  const runs = state.kind === "ok" ? state.runs : [];
  const bestScore = runs.reduce((acc, r) => Math.max(acc, r.score ?? 0), 0);
  const latest = runs[0];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            Evaluations
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Metric-driven evaluation of agents, workflows, and orchestrations,
            with run comparison and regression detection.
          </p>
        </div>
        <button
          onClick={handleRun}
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          <Play className="h-4 w-4" />
          {busy ? "Running…" : "Run default suite"}
        </button>
      </div>

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
          {state.message}
        </p>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Runs" value={String(runs.length)} />
        <Stat label="Best score" value={bestScore.toFixed(2)} />
        <Stat
          label="Latest"
          value={latest ? `${(latest.score ?? 0).toFixed(2)}` : "—"}
        />
        <Stat
          label="Total cases"
          value={String(runs.reduce((a, r) => a + (r.result_count ?? 0), 0))}
        />
      </div>

      {/* Compare panel */}
      <form
        onSubmit={handleCompare}
        className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950"
      >
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
          Compare runs
        </h2>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <select
            value={compare.a}
            onChange={(e) => setCompare((c) => ({ ...c, a: e.target.value }))}
            className="min-w-40 flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          >
            <option value="">Run A…</option>
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {short(r.id)} — {(r.score ?? 0).toFixed(2)}
              </option>
            ))}
          </select>
          <select
            value={compare.b}
            onChange={(e) => setCompare((c) => ({ ...c, b: e.target.value }))}
            className="min-w-40 flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          >
            <option value="">Run B…</option>
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {short(r.id)} — {(r.score ?? 0).toFixed(2)}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={!compare.a || !compare.b}
            className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            Compare
          </button>
        </div>
        {comparison && (
          <div className="mt-3 grid gap-2 text-sm sm:grid-cols-3">
            <CompareStat label="Run A" value={comparison.score_a.toFixed(3)} />
            <CompareStat label="Run B" value={comparison.score_b.toFixed(3)} />
            <CompareStat
              label="Delta"
              value={`${comparison.delta >= 0 ? "+" : ""}${comparison.delta.toFixed(3)}`}
              tone={comparison.regression ? "red" : "green"}
            />
          </div>
        )}
        {regression && (
          <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">{regression.message}</p>
        )}
      </form>

      {note && (
        <p className="rounded-lg border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-sm text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
          {note}
        </p>
      )}

      {state.kind === "loading" && (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
          ))}
        </div>
      )}

      {state.kind === "ok" && runs.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <BarChart3 className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            No evaluation runs yet. Run the default suite to begin.
          </p>
        </div>
      )}

      {state.kind === "ok" && runs.length > 0 && (
        <div className="space-y-4">
          {runs.map((run) => (
            <RunCard
              key={run.id}
              run={run}
              expanded={expandedRun === run.id}
              results={expandedRun === run.id ? results : null}
              onToggle={() => handleExpand(run.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function RunCard({
  run,
  expanded,
  results,
  onToggle,
}: {
  run: EvaluationRun;
  expanded: boolean;
  results: EvaluationResult[] | null;
  onToggle: () => void;
}) {
  const metrics = run.metrics ?? {};
  const metricRows = Object.entries(metrics).slice(0, 6);

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-3 p-4 text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              Run {short(run.id)}
            </span>
            <span className="rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
              {run.status}
            </span>
          </div>
          <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
            score {(run.score ?? 0).toFixed(3)} · {run.result_count ?? 0} cases ·{" "}
            {new Date(run.created_at).toLocaleString()}
          </p>
        </div>
        <span className="shrink-0 text-xs text-zinc-400">
          {expanded ? "collapse" : "expand"}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-zinc-100 bg-zinc-50/60 p-4 dark:border-zinc-800 dark:bg-zinc-900/30">
          {metricRows.length > 0 && (
            <div className="space-y-2">
              {metricRows.map(([key, value]) => (
                <div key={key} className="flex items-center gap-2">
                  <span className="w-40 shrink-0 truncate text-xs text-zinc-500 dark:text-zinc-400">
                    {key.replaceAll("_", " ")}
                  </span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
                    <div
                      className="h-full rounded-full bg-zinc-900 dark:bg-white"
                      style={{ width: `${Math.min(100, value * 100)}%` }}
                    />
                  </div>
                  <span className="w-10 text-right text-xs font-medium text-zinc-700 dark:text-zinc-300">
                    {value.toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          )}

          {results === null && (
            <p className="mt-2 text-xs text-zinc-400">Loading results…</p>
          )}
          {results && results.length === 0 && (
            <p className="mt-2 text-xs text-zinc-400">No per-case results recorded.</p>
          )}
          {results && results.length > 0 && (
            <div className="mt-3 space-y-1.5">
              {results.map((r) => (
                <div
                  key={r.id}
                  className="flex items-center gap-2 rounded-md bg-white px-3 py-1.5 text-sm dark:bg-zinc-950"
                >
                  <span
                    className={`h-2 w-2 shrink-0 rounded-full ${r.passed ? "bg-emerald-500" : "bg-red-500"}`}
                  />
                  <span className="min-w-0 flex-1 truncate text-zinc-700 dark:text-zinc-300">
                    {r.case_id ? short(r.case_id) : "case"}
                  </span>
                  <span className="text-xs text-zinc-400">
                    {r.score != null ? r.score.toFixed(2) : "—"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CompareStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "red" | "green";
}) {
  const color =
    tone === "red"
      ? "text-red-600 dark:text-red-400"
      : tone === "green"
        ? "text-emerald-600 dark:text-emerald-400"
        : "text-zinc-800 dark:text-zinc-200";
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-950">
      <p className="text-[11px] uppercase tracking-wide text-zinc-400">{label}</p>
      <p className={`mt-0.5 text-lg font-semibold ${color}`}>{value}</p>
    </div>
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