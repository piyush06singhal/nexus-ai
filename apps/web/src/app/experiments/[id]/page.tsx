"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  completeExperiment,
  fetchExperiment,
  fetchExperimentResults,
} from "@/lib/api";
import type { ExperimentPublic, ExperimentResultPublic } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { usePhase12 } from "@/components/phase12/Phase12Shell";
import { ActionButton, JsonBlock, SectionCard } from "@/components/phase12/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

const INPUT_CLASS =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";
const SELECT_CLASS =
  "rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

export default function ExperimentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  usePhase12(); // keep company context in sync
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [experiment, setExperiment] = useState<ExperimentPublic | null>(null);
  const [results, setResults] = useState<ExperimentResultPublic[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  // complete form
  const [conclusion, setConclusion] = useState("inconclusive");
  const [winningVariant, setWinningVariant] = useState("");
  const [metricsText, setMetricsText] = useState("");
  const [confidenceText, setConfidenceText] = useState("");
  const [limitationsText, setLimitationsText] = useState("");
  const [completing, setCompleting] = useState(false);

  function load() {
    Promise.all([fetchExperiment(id), fetchExperimentResults(id)])
      .then(([ex, rs]) => {
        setError(null);
        setExperiment(ex);
        setResults(rs);
        setState({ kind: "ok" });
      })
      .catch((err: unknown) => {
        setState({
          kind: "error",
          message:
            err instanceof Error ? err.message : "Failed to load experiment",
        });
      });
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function complete() {
    let metrics: Record<string, unknown> | null = null;
    let confidence: Record<string, unknown> | null = null;
    let limitations: Record<string, unknown> | null = null;
    try {
      metrics = metricsText.trim() ? JSON.parse(metricsText) : null;
      confidence = confidenceText.trim() ? JSON.parse(confidenceText) : null;
      limitations = limitationsText.trim() ? JSON.parse(limitationsText) : null;
    } catch {
      setError("Metrics / confidence / limitations must each be valid JSON or empty.");
      return;
    }
    setCompleting(true);
    setError(null);
    setDone(null);
    try {
      const result = await completeExperiment(id, {
        conclusion,
        winning_variant_id: winningVariant.trim() || null,
        metrics,
        confidence,
        limitations,
      });
      setDone(
        `Conclusion recorded: ${result.conclusion}. Significance is bounded by the recorded limitations.`,
      );
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to record conclusion");
    } finally {
      setCompleting(false);
    }
  }

  if (state.kind === "loading") {
    return (
      <div className="h-48 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
    );
  }
  if (state.kind === "error") {
    return (
      <p className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300">
        {state.message}
      </p>
    );
  }
  if (!experiment) return null;

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

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              {experiment.name}
            </h2>
            <StatusBadge status={experiment.status as never} />
            {experiment.approval_gate_id && (
              <StatusBadge status="pending_approval" />
            )}
          </div>
          {experiment.description && (
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              {experiment.description}
            </p>
          )}
        </div>
      </div>

      <SectionCard title="Design">
        {experiment.hypothesis && (
          <p className="mb-2 text-sm text-zinc-700 dark:text-zinc-300">
            <span className="font-medium">Hypothesis:</span> {experiment.hypothesis}
          </p>
        )}
        <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
          sample size {experiment.sample_size ?? "—"}
          {experiment.approval_gate_id
            ? ` · approval gate ${experiment.approval_gate_id.slice(0, 8)}`
            : ""}{" "}
          · created {new Date(experiment.created_at).toLocaleString()}
        </p>
        {experiment.metrics_json && Object.keys(experiment.metrics_json).length > 0 && (
          <JsonBlock value={experiment.metrics_json} />
        )}
      </SectionCard>

      {experiment.baseline_json && (
        <SectionCard title="Baseline">
          <JsonBlock value={experiment.baseline_json} />
        </SectionCard>
      )}

      <SectionCard title="Results">
        {results.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No result recorded yet. Complete the experiment below once it has
            run.
          </p>
        ) : (
          <ul className="space-y-3 divide-y divide-zinc-100 dark:divide-zinc-800">
            {results.map((r) => (
              <li key={r.id} className="space-y-2 py-3">
                <p className="flex flex-wrap items-center gap-2 text-sm">
                  <StatusBadge status={r.conclusion as never} />
                  <span className="text-zinc-600 dark:text-zinc-400">
                    winning variant{" "}
                    <span className="font-mono">{r.winning_variant_id?.slice(0, 8) ?? "—"}</span>{" "}
                    · sample {r.sample_size ?? "—"}
                  </span>
                </p>
                {r.metrics_json && <JsonBlock value={r.metrics_json} />}
                <div className="grid gap-2 sm:grid-cols-2">
                  {r.confidence_json && (
                    <div>
                      <p className="mb-1 text-xs uppercase tracking-wide text-zinc-500">confidence</p>
                      <JsonBlock value={r.confidence_json} />
                    </div>
                  )}
                  {r.limitations_json && (
                    <div>
                      <p className="mb-1 text-xs uppercase tracking-wide text-zinc-500">limitations</p>
                      <JsonBlock value={r.limitations_json} />
                    </div>
                  )}
                </div>
                {r.assumptions_json && (
                  <div>
                    <p className="mb-1 text-xs uppercase tracking-wide text-zinc-500">assumptions</p>
                    <JsonBlock value={r.assumptions_json} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
          Significance claims are bounded by the sample size and limitations
          shown — the model never overstates a winner.
        </p>
      </SectionCard>

      <SectionCard
        title="Complete the experiment"
        action={
          <ActionButton busy={completing} onClick={complete} disabled={results.length > 0}>
            Record conclusion
          </ActionButton>
        }
      >
        <div className="space-y-2 text-sm">
          <select
            value={conclusion}
            onChange={(e) => setConclusion(e.target.value)}
            className={SELECT_CLASS}
          >
            <option value="winner">winner</option>
            <option value="loser">loser</option>
            <option value="inconclusive">inconclusive</option>
          </select>
          <input
            value={winningVariant}
            onChange={(e) => setWinningVariant(e.target.value)}
            placeholder="winning variant id (if winner)"
            className={INPUT_CLASS}
          />
          <textarea
            value={metricsText}
            onChange={(e) => setMetricsText(e.target.value)}
            placeholder={'Metrics JSON (optional), e.g. {"win_rate": {"variant": 0.58}}'}
            rows={2}
            className={`${INPUT_CLASS} font-mono text-xs`}
          />
          <textarea
            value={confidenceText}
            onChange={(e) => setConfidenceText(e.target.value)}
            placeholder={'Confidence JSON (optional), e.g. {"level": 0.95, "ci": [0.51, 0.65]}'}
            rows={2}
            className={`${INPUT_CLASS} font-mono text-xs`}
          />
          <textarea
            value={limitationsText}
            onChange={(e) => setLimitationsText(e.target.value)}
            placeholder={'Limitations JSON (optional), e.g. {"seasonality": "north-hemisphere only"}'}
            rows={2}
            className={`${INPUT_CLASS} font-mono text-xs`}
          />
          {results.length > 0 && (
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              A conclusion is already recorded. Results are append points, not
              overwrites.
            </p>
          )}
        </div>
      </SectionCard>
    </div>
  );
}