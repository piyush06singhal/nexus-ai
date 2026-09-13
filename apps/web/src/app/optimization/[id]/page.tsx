"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  fetchOptimizationProblem,
  fetchOptimizationResults,
  fetchOptimizationRun,
  recommendFromRun,
  runOptimizationProblem,
} from "@/lib/api";
import type {
  OptimizationProblemPublic,
  OptimizationResultsPublic,
  OptimizationRunPublic,
  RecommendationPublic,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { usePhase12 } from "@/components/phase12/Phase12Shell";
import {
  ActionButton,
  Dash,
  JsonBlock,
  SectionCard,
} from "@/components/phase12/ui";
import { HBar } from "@/components/phase12/charts";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

const TERMINAL_RUN_STATUSES = ["completed", "failed", "cancelled"];

function sumScores(candidate: Record<string, unknown>): number {
  const scores = (candidate.scores ?? {}) as Record<string, number>;
  return Object.values(scores).reduce((a, b) => a + Number(b || 0), 0);
}

export default function OptimizationProblemDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { companyId } = usePhase12();
  const [problemId, setProblemId] = useState("");
  const cancelledRef = useRef(false);

  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [problem, setProblem] = useState<OptimizationProblemPublic | null>(null);
  const [runs, setRuns] = useState<OptimizationRunPublic[]>([]);
  const [results, setResults] = useState<
    Record<string, OptimizationResultsPublic>
  >({});
  const [recommendations, setRecommendations] = useState<
    Record<string, RecommendationPublic>
  >({});

  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [recommending, setRecommending] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState<string | null>(null);

  useEffect(() => {
    params.then((p) => setProblemId(p.id));
  }, [params]);

  useEffect(() => {
    if (!problemId) return;
    let cancelled = false;
    cancelledRef.current = false;
    fetchOptimizationProblem(problemId)
      .then((p) => {
        if (cancelled) return;
        setProblem(p);
        setState({ kind: "ok" });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setState({
          kind: "error",
          message:
            err instanceof Error ? err.message : "Failed to load problem",
        });
      });
    return () => {
      cancelled = true;
      cancelledRef.current = true;
    };
  }, [problemId]);

  /** Follow a run to completion and pull its results once it is done. */
  async function pollRun(runId: string) {
    for (let i = 0; i < 24; i++) {
      if (cancelledRef.current) return;
      await new Promise((r) => setTimeout(r, 1200));
      if (cancelledRef.current) return;
      let run: OptimizationRunPublic;
      try {
        run = await fetchOptimizationRun(runId);
      } catch {
        return;
      }
      if (cancelledRef.current) return;
      setRuns((prev) => prev.map((r) => (r.id === runId ? run : r)));
      if (run.status === "completed") {
        try {
          const res = await fetchOptimizationResults(runId);
          if (!cancelledRef.current) {
            setResults((prev) => ({ ...prev, [runId]: res }));
            setDone(`Run complete — ${res.candidates.length} modeled candidates.`);
          }
        } catch {
          /* results not ready yet; stop polling */
        }
        return;
      }
      if (TERMINAL_RUN_STATUSES.includes(run.status)) return;
    }
  }

  async function loadResults(runId: string) {
    try {
      const res = await fetchOptimizationResults(runId);
      setResults((prev) => ({ ...prev, [runId]: res }));
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to load run results",
      );
    }
  }

  async function refreshRun(runId: string) {
    setRefreshing(runId);
    setError(null);
    setDone(null);
    try {
      const run = await fetchOptimizationRun(runId);
      setRuns((prev) => prev.map((r) => (r.id === runId ? run : r)));
      if (run.status === "completed") await loadResults(runId);
      setDone(`Run ${run.id.slice(0, 8)} is ${run.status}.`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Refresh failed");
    } finally {
      setRefreshing(null);
    }
  }

  async function runProblem() {
    if (!problem) return;
    setRunning(true);
    setError(null);
    setDone(null);
    try {
      const run = await runOptimizationProblem(problem.id);
      setRuns((prev) => [run, ...prev]);
      if (run.status === "completed") {
        // synchronous backend completion: surface results immediately
        try {
          await loadResults(run.id);
        } catch {
          /* poll will retry */
        }
      } else {
        setDone(`Run started — ${run.status}.`);
      }
      void pollRun(run.id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to run problem");
    } finally {
      setRunning(false);
    }
  }

  async function createRecommendation(runId: string) {
    setRecommending(runId);
    setError(null);
    setDone(null);
    try {
      const rec = await recommendFromRun(runId);
      setRecommendations((prev) => ({ ...prev, [runId]: rec }));
      setDone(
        `Recommendation ${rec.id.slice(0, 8)} created (${rec.status}). Approval is governed elsewhere.`,
      );
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to build recommendation",
      );
    } finally {
      setRecommending(null);
    }
  }

  if (state.kind === "loading") {
    return (
      <div className="h-48 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
    );
  }
  if (state.kind === "error" || !problem) {
    return (
      <p className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300">
        {state.kind === "error" ? state.message : "Problem not found"}
      </p>
    );
  }

  const objectives =
    ((problem.objective_json?.objectives as
      | { metric: string; direction?: string; weight?: number }[]
      | undefined) ?? []);

  return (
    <div className="space-y-6">
      {(error || done) && (
        <p
          className={
            error
              ? "rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300"
              : "rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:border-emerald-900/40 dark:bg-emerald-950/30 dark:text-emerald-300"
          }
        >
          {error ?? done}
        </p>
      )}

      <SectionCard
        title={problem.name}
        action={<StatusBadge status={problem.status as never} />}
      >
        <div className="space-y-2 text-sm">
          <p className="text-zinc-600 dark:text-zinc-400">
            {problem.description ?? "No description."}
          </p>
          {problem.strategy && (
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              Strategy <strong>{problem.strategy}</strong>
            </p>
          )}
          {objectives.length > 0 && (
            <div>
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                Objectives
              </p>
              <ul className="space-y-1">
                {objectives.map((o, i) => (
                  <li
                    key={i}
                    className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300"
                  >
                    <StatusBadge
                      status={(o.direction ?? "maximize") as never}
                    />
                    <span>{o.metric}</span>
                    <span className="text-xs text-zinc-400">
                      weight {o.weight ?? 1}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {problem.objective_json && (
            <div>
              <p className="mb-1 mt-2 text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                Problem spec (objectives + variables)
              </p>
              <JsonBlock value={problem.objective_json} />
            </div>
          )}
          <p className="text-xs text-zinc-400">
            created {new Date(problem.created_at).toLocaleString()}
            {problem.updated_at
              ? ` · updated ${new Date(problem.updated_at).toLocaleString()}`
              : ""}
            {companyId ? ` · company ${companyId.slice(0, 8)}` : ""}
          </p>
        </div>
      </SectionCard>

      <SectionCard
        title="Runs"
        action={
          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-500 dark:text-zinc-400">
              {runs.length} run{runs.length === 1 ? "" : "s"} this session
            </span>
            <ActionButton busy={running} onClick={runProblem}>
              Run optimization
            </ActionButton>
          </div>
        }
      >
        {runs.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No runs yet this session. Run the problem to generate modeled
            candidates.
          </p>
        ) : (
          <ul className="space-y-4">
            {runs.map((run) => (
              <RunCard
                key={run.id}
                run={run}
                results={results[run.id]}
                recommendation={recommendations[run.id]}
                refreshing={refreshing === run.id}
                recommending={recommending === run.id}
                onRefresh={() => refreshRun(run.id)}
                onRecommend={() => createRecommendation(run.id)}
              />
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}

function RunCard({
  run,
  results,
  recommendation,
  refreshing,
  recommending,
  onRefresh,
  onRecommend,
}: {
  run: OptimizationRunPublic;
  results: OptimizationResultsPublic | undefined;
  recommendation: RecommendationPublic | undefined;
  refreshing: boolean;
  recommending: boolean;
  onRefresh: () => void;
  onRecommend: () => void;
}) {
  const candidates = results?.candidates ?? [];
  const best = results?.best_candidate ?? null;
  const bestIndex = best ? best.index : null;
  const totals = candidates.map(sumScores);
  const maxTotal = Math.max(1, ...totals);

  return (
    <li
      className={`rounded-lg border p-4 ${
        run.status === "completed"
          ? "border-emerald-200 dark:border-emerald-900/40"
          : "border-zinc-200 dark:border-zinc-800"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs text-zinc-500 dark:text-zinc-400">
            {run.id}
          </span>
          <StatusBadge status={run.status as never} />
          {run.strategy && (
            <span className="text-xs text-zinc-500 dark:text-zinc-400">
              {run.strategy}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <ActionButton busy={refreshing} onClick={onRefresh}>
            Refresh
          </ActionButton>
          <ActionButton
            busy={recommending}
            disabled={run.status !== "completed"}
            onClick={onRecommend}
          >
            Recommend from run
          </ActionButton>
        </div>
      </div>

      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
        <Dash
          value={
            run.started_at ? `started ${new Date(run.started_at).toLocaleString()}` : null
          }
        />{" "}
        <Dash
          value={
            run.completed_at
              ? `· completed ${new Date(run.completed_at).toLocaleString()}`
              : null
          }
        />
      </p>

      {run.error_message && (
        <p className="mt-2 text-xs text-red-600 dark:text-red-400">
          {run.error_message}
        </p>
      )}

      {run.constraints_json && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">
            Runnable constraints
          </summary>
          <div className="mt-2">
            <JsonBlock value={run.constraints_json} />
          </div>
        </details>
      )}

      {recommendation && (
        <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-900/40 dark:bg-amber-950/30">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
              Recommendation {recommendation.id.slice(0, 8)}
              <span className="ml-2">
                <StatusBadge status={recommendation.status as never} />
              </span>
            </p>
            <Link
              href="/optimization/recommendations"
              className="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400"
            >
              View in Recommendations →
            </Link>
          </div>
          <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">
            {recommendation.title} — a proposal only. Approval is governed
            elsewhere and never applies without review.
          </p>
        </div>
      )}

      {run.status === "completed" && results && candidates.length > 0 && (
        <div className="mt-3 space-y-2">
          <p className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            Modeled candidates (ranked by objective scores)
          </p>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            Scores are modeled estimates, normalized within this run for
            ranking. They are not real-world outcomes — verify before acting.
          </p>
          {candidates.map((c, i) => {
            const index = c.index as number;
            const isBest = bestIndex != null && index === bestIndex;
            const values = (c.values ?? {}) as Record<string, unknown>;
            const scores = (c.scores ?? {}) as Record<string, number>;
            const pct = (sumScores(c) / maxTotal) * 100;
            return (
              <div
                key={i}
                className={`rounded-lg border p-3 ${
                  isBest
                    ? "border-emerald-300 bg-emerald-50/60 dark:border-emerald-800 dark:bg-emerald-950/30"
                    : "border-zinc-200 dark:border-zinc-800"
                }`}
              >
                <div className="mb-1 flex items-center justify-between gap-2">
                  <p className="text-xs font-medium text-zinc-700 dark:text-zinc-300">
                    Candidate #{index}
                    {isBest && (
                      <span className="ml-2">
                        <StatusBadge status={"winner"} />
                      </span>
                    )}
                    {isBest && (
                      <span className="ml-1 text-[11px] text-emerald-600 dark:text-emerald-400">
                        top-ranked
                      </span>
                    )}
                  </p>
                  <p className="font-mono text-[11px] text-zinc-500 dark:text-zinc-400">
                    {Object.entries(values)
                      .map(([k, v]) => `${k}=${String(v)}`)
                      .join(" · ")}
                  </p>
                </div>
                <HBar
                  label={`score ${index}`}
                  value={pct}
                  max={100}
                  suffix="%"
                />
                <p className="mt-1 font-mono text-[11px] text-zinc-500 dark:text-zinc-400">
                  {Object.entries(scores)
                    .map(([k, v]) => `${k}=${Number(v).toLocaleString()}`)
                    .join(" · ")}
                </p>
              </div>
            );
          })}
        </div>
      )}

      {run.status === "completed" && results && candidates.length === 0 && (
        <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
          Run completed with no candidates recorded.
        </p>
      )}
    </li>
  );
}