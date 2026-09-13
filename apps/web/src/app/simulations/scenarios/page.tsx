"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  fetchScenarios,
  fetchSimulations,
  runScenario,
} from "@/lib/api";
import type {
  ScenarioPublic,
  SimulationPublic,
  SimulationRunPublic,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { usePhase12 } from "@/components/phase12/Phase12Shell";
import { ActionButton, SectionCard } from "@/components/phase12/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

export default function ScenariosPage() {
  const { companyId } = usePhase12();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [scenarios, setScenarios] = useState<ScenarioPublic[]>([]);
  const [simulations, setSimulations] = useState<SimulationPublic[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busyRun, setBusyRun] = useState<string | null>(null);

  function load() {
    Promise.all([
      fetchScenarios({ companyId: companyId ?? undefined }),
      fetchSimulations({ companyId: companyId ?? undefined }),
    ])
      .then(([sc, sims]) => {
        setError(null);
        setScenarios(sc);
        setSimulations(sims);
        setState({ kind: "ok" });
      })
      .catch((err: unknown) => {
        setState({
          kind: "error",
          message:
            err instanceof Error ? err.message : "Failed to load scenarios",
        });
      });
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  async function runNow(sc: ScenarioPublic) {
    setBusyRun(sc.id);
    setError(null);
    setDone(null);
    try {
      const run: SimulationRunPublic = await runScenario(sc.id, {});
      setDone(
        `Scenario "${sc.name}" run ${run.id.slice(0, 8)} → ${run.status}. Outcomes are modeled estimates.`,
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Scenario run failed");
    } finally {
      setBusyRun(null);
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

  const bySimulation = new Map<string, SimulationPublic>();
  for (const s of simulations) bySimulation.set(s.id, s);

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

      <p className="max-w-3xl text-xs text-zinc-500 dark:text-zinc-400">
        Scenarios are variants run inside the closed sandbox against a parent
        simulation&apos;s assumptions. A <strong>baseline</strong> scenario is
        the reference; what-if, stress, and capacity scenarios compare against
        it. All outputs are SIMULATED estimates.
      </p>

      <SectionCard
        title="Scenarios"
        action={
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            {scenarios.length} scenario{scenarios.length === 1 ? "" : "s"}
          </span>
        }
      >
        {scenarios.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No scenarios found. Open a simulation detail page to create one.
          </p>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {scenarios.map((sc) => {
              const parent = bySimulation.get(sc.simulation_id);
              return (
                <li
                  key={sc.id}
                  className="flex flex-wrap items-center justify-between gap-3 py-3"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        href={`/simulations/${sc.simulation_id}`}
                        className="text-sm font-medium text-indigo-600 hover:underline dark:text-indigo-400"
                      >
                        {sc.name}
                      </Link>
                      <StatusBadge status={sc.scenario_type as never} />
                      {sc.is_baseline && (
                        <StatusBadge status="baseline" />
                      )}
                    </div>
                    {sc.description && (
                      <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
                        {sc.description}
                      </p>
                    )}
                    <p className="mt-0.5 text-xs text-zinc-400">
                      {parent ? (
                        <>
                          parent{" "}
                          <Link
                            href={`/simulations/${parent.id}`}
                            className="text-zinc-600 hover:underline dark:text-zinc-300"
                          >
                            {parent.name}
                          </Link>{" "}
                          ·{" "}
                        </>
                      ) : (
                        <>parent {sc.simulation_id.slice(0, 8)} · </>
                      )}
                      horizon {sc.horizon_days ?? "—"}d · created{" "}
                      {new Date(sc.created_at).toLocaleString()}
                    </p>
                  </div>
                  <ActionButton
                    busy={busyRun === sc.id}
                    onClick={() => runNow(sc)}
                  >
                    Run scenario
                  </ActionButton>
                </li>
              );
            })}
          </ul>
        )}
      </SectionCard>

      {scenarios.filter((s) => s.scenario_type === "baseline").length > 0 && (
        <SectionCard title="Compare">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Pick a baseline run and a scenario run to see the modeled deltas
            (KPI, cost, time, utilization, risk):
          </p>
          <p className="mt-2">
            <Link
              href="/simulations/compare"
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              Open comparison tool →
            </Link>
          </p>
        </SectionCard>
      )}
    </div>
  );
}