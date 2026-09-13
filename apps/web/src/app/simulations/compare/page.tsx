"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  compareRuns,
  fetchSimulations,
} from "@/lib/api";
import type {
  SimulationComparisonPublic,
  SimulationPublic,
} from "@/lib/types";
import { usePhase12 } from "@/components/phase12/Phase12Shell";
import { ActionButton, JsonBlock, SectionCard } from "@/components/phase12/ui";
import { Delta } from "@/components/phase12/charts";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

const INPUT_CLASS =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 font-mono text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

export default function ComparePage() {
  const params = useSearchParams();
  const { companyId } = usePhase12();
  const [state, setState] = useState<LoadState>({ kind: "ok" });
  const [simulations, setSimulations] = useState<SimulationPublic[]>([]);
  const [baseline, setBaseline] = useState(params.get("baseline") ?? "");
  const [scenario, setScenario] = useState(params.get("scenario") ?? "");
  const [comparison, setComparison] = useState<SimulationComparisonPublic | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function load() {
    fetchSimulations({ companyId: companyId ?? undefined })
      .then((list) => {
        setSimulations(list);
        setState({ kind: "ok" });
      })
      .catch((err: unknown) => {
        setState({
          kind: "error",
          message:
            err instanceof Error ? err.message : "Failed to load simulations",
        });
      });
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  async function doCompare() {
    if (!baseline.trim() || !scenario.trim()) {
      setError("Enter both a baseline run id and a scenario run id.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const comp = await compareRuns({
        baseline_run_id: baseline.trim(),
        scenario_run_id: scenario.trim(),
      });
      setComparison(comp);
      // Normalize into the URL so the comparison is shareable.
      const url = new URL(window.location.href);
      if (baseline.trim()) url.searchParams.set("baseline", baseline.trim());
      if (scenario.trim()) url.searchParams.set("scenario", scenario.trim());
      window.history.replaceState(null, "", url);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Comparison failed");
      setComparison(null);
    } finally {
      setBusy(false);
    }
  }

  if (state.kind === "error") {
    return (
      <p className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300">
        {state.message}
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <p className="max-w-3xl text-xs text-zinc-500 dark:text-zinc-400">
        Compare a baseline simulation run against a scenario run. Paste the two
        run ids (visible on the simulation detail page) or select a simulation
        below. Deltas are <strong>modeled estimates (SIMULATED)</strong> — they
        describe the model, not a promise about the real company.
      </p>

      <SectionCard title="Baseline vs scenario">
        <div className="space-y-2 text-sm">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Baseline run id
            </span>
            <input
              value={baseline}
              onChange={(e) => setBaseline(e.target.value)}
              placeholder="uuid of the baseline run"
              className={INPUT_CLASS}
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Scenario run id
            </span>
            <input
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              placeholder="uuid of the scenario run"
              className={INPUT_CLASS}
            />
          </label>
          <div className="flex items-center gap-2">
            <ActionButton busy={busy} disabled={!baseline.trim() || !scenario.trim()} onClick={doCompare}>
              Compare
            </ActionButton>
            {error && <span className="text-xs text-red-600 dark:text-red-400">{error}</span>}
          </div>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            Run ids come from the Runs panel on a{" "}
            <Link href="/simulations" className="text-indigo-600 hover:underline dark:text-indigo-400">
              simulation detail
            </Link>{" "}
            page after starting a run.
          </p>
        </div>
      </SectionCard>

      {simulations.length > 0 && (
        <SectionCard
          title="Simulations in scope"
          action={
            <span className="text-xs text-zinc-500 dark:text-zinc-400">
              {simulations.length} total
            </span>
          }
        >
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {simulations.map((s) => (
              <li key={s.id} className="py-2 text-sm text-zinc-600 dark:text-zinc-400">
                <span className="text-zinc-900 dark:text-zinc-100">{s.name}</span>{" "}
                <span className="font-mono text-xs text-zinc-500">{s.id}</span>
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      {comparison && (
        <ComparisonResult comp={comparison} />
      )}
    </div>
  );
}

function ComparisonResult({ comp }: { comp: SimulationComparisonPublic }) {
  const deltas = comp.metric_deltas_json ?? {};
  const bottleneck = comp.bottleneck_json ?? {};
  const entries = Object.entries(deltas);

  return (
    <>
      {comp.summary && (
        <SectionCard title="Summary">
          <p className="text-sm text-zinc-700 dark:text-zinc-300">{comp.summary}</p>
        </SectionCard>
      )}
      <SectionCard title="Metric deltas — baseline vs scenario (SIMULATED)">
        {entries.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">No metric deltas returned.</p>
        ) : (
          <dl className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {entries.map(([k, v]) => {
              const num = typeof v === "number" ? v : parseFloat(String(v));
              const isPct = String(v).includes("%") || isPctKey(k);
              return (
                <div key={k} className="flex items-center justify-between gap-4 py-2">
                  <dt className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                    {k}
                  </dt>
                  <dd className="text-sm text-zinc-900 dark:text-zinc-100">
                    {Number.isFinite(num) ? (
                      <Delta value={isPct ? num * 100 : num} />
                    ) : (
                      String(v)
                    )}
                  </dd>
                </div>
              );
            })}
          </dl>
        )}
        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
          Positive deltas favor the scenario unless the metric is a cost (e.g.
          cost, time, risk). Deltas are model outputs, not measurements.
        </p>
      </SectionCard>
      <SectionCard title="Bottleneck detection">
        {Object.keys(bottleneck).length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No bottleneck flagged by the model.
          </p>
        ) : (
          <JsonBlock value={bottleneck} />
        )}
      </SectionCard>
      <SectionCard title="Comparison record">
        <JsonBlock
          value={{
            id: comp.id,
            baseline_run_id: comp.baseline_run_id,
            scenario_run_id: comp.scenario_run_id,
            created_at: comp.created_at,
            output_kind: "simulated",
          }}
        />
      </SectionCard>
    </>
  );
}

function isPctKey(k: string): boolean {
  return /rate|util|growth|on.?time|margin|efficiency/i.test(k);
}