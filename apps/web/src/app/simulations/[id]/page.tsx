"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  cancelSimulationRun,
  createScenario,
  fetchScenarios,
  fetchSimulation,
  fetchSimulationEvents,
  fetchSimulationResults,
  fetchSimulationState,
  pauseSimulationRun,
  runSimulation,
} from "@/lib/api";
import type {
  ScenarioPublic,
  SimulationPublic,
  SimulationResultsPublic,
  SimulationRunPublic,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { usePhase12 } from "@/components/phase12/Phase12Shell";
import {
  ActionButton,
  JsonBlock,
  SectionCard,
} from "@/components/phase12/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

const SCENARIO_TYPES = [
  "baseline",
  "what_if",
  "stress_test",
  "capacity_test",
  "resource_test",
  "strategy_test",
  "workforce_test",
  "agent_test",
  "product_test",
  "risk_test",
  "custom",
] as const;

const INPUT_CLASS =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";
const SELECT_CLASS =
  "rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

export default function SimulationDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const { companyId } = usePhase12();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [sim, setSim] = useState<SimulationPublic | null>(null);
  const [scenarios, setScenarios] = useState<ScenarioPublic[]>([]);
  const [runs, setRuns] = useState<Record<string, SimulationRunPublic>>({});
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  // scenario create form
  const [scName, setScName] = useState("");
  const [scType, setScType] = useState("what_if");
  const [scDescription, setScDescription] = useState("");
  const [scAssumptions, setScAssumptions] = useState("");
  const [creatingSc, setCreatingSc] = useState(false);

  const [busyRun, setBusyRun] = useState<string | null>(null);

  function load() {
    Promise.all([
      fetchSimulation(id),
      fetchScenarios({ simulationId: id }),
    ])
      .then(([s, sc]) => {
        setError(null);
        setSim(s);
        setScenarios(sc);
        setState({ kind: "ok" });
      })
      .catch((err: unknown) => {
        setState({
          kind: "error",
          message:
            err instanceof Error ? err.message : "Failed to load simulation",
        });
      });
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, companyId]);

  async function runIt() {
    setBusyRun("sim");
    setError(null);
    setDone(null);
    try {
      const run = await runSimulation(id, {});
      setRuns((prev) => ({ ...prev, [run.id]: run }));
      setDone(`Run ${run.id.slice(0, 8)} started → ${run.status}.`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Run failed");
    } finally {
      setBusyRun(null);
    }
  }

  async function runScenario(scenarioId: string) {
    setBusyRun(scenarioId);
    setError(null);
    setDone(null);
    try {
      const run = await runScenarioId(scenarioId);
      setRuns((prev) => ({ ...prev, [run.id]: run }));
      setDone(`Scenario run ${run.id.slice(0, 8)} → ${run.status}.`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Scenario run failed");
    } finally {
      setBusyRun(null);
    }
  }

  async function runScenarioId(scenarioId: string): Promise<SimulationRunPublic> {
    const { runScenario } = await import("@/lib/api");
    return runScenario(scenarioId, {});
  }

  async function pauseRun(runId: string) {
    setError(null);
    setDone(null);
    try {
      const run = await pauseSimulationRun(runId);
      setRuns((prev) => ({ ...prev, [runId]: run }));
      setDone(`Run paused → ${run.status}.`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Pause failed");
    }
  }

  async function cancelRun(runId: string) {
    setError(null);
    setDone(null);
    try {
      const run = await cancelSimulationRun(runId);
      setRuns((prev) => ({ ...prev, [runId]: run }));
      setDone(`Run cancelled → ${run.status}.`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Cancel failed");
    }
  }

  async function createScenarioNow() {
    if (!scName.trim()) {
      setError("Give the scenario a name.");
      return;
    }
    let assumptions: Record<string, unknown> | null = null;
    if (scAssumptions.trim()) {
      try {
        assumptions = JSON.parse(scAssumptions);
      } catch {
        setError("Assumptions JSON is invalid.");
        return;
      }
    }
    setCreatingSc(true);
    setError(null);
    setDone(null);
    try {
      const sc = await createScenario({
        simulation_id: id,
        name: scName.trim(),
        scenario_type: scType,
        company_id: companyId ?? undefined,
        description: scDescription.trim() || null,
        assumptions,
      });
      setDone(`Scenario "${sc.name}" created (${sc.scenario_type}).`);
      setScName("");
      setScDescription("");
      setScAssumptions("");
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create scenario");
    } finally {
      setCreatingSc(false);
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
  if (!sim) return null;

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
              {sim.name}
            </h2>
            <StatusBadge status={sim.status as never} />
            <StatusBadge status={sim.scenario_type as never} />
            {sim.sandboxed && (
              <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                closed sandbox
              </span>
            )}
          </div>
          {sim.description && (
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              {sim.description}
            </p>
          )}
          <p className="mt-1 text-xs text-zinc-400">
            horizon {sim.horizon_days ?? "—"}d · tick {sim.clock_tick ?? "—"} · model{" "}
            {sim.model_name ?? "—"} v{sim.model_version ?? "—"} · updated{" "}
            {new Date(sim.updated_at).toLocaleString()}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ActionButton
            busy={busyRun === "sim"}
            disabled={!["draft", "ready"].includes(sim.status)}
            onClick={runIt}
          >
            Run simulation
          </ActionButton>
        </div>
      </div>

      {sim.assumptions_json && Object.keys(sim.assumptions_json).length > 0 && (
        <SectionCard title="Model assumptions">
          <JsonBlock value={sim.assumptions_json} />
        </SectionCard>
      )}

      <SectionCard
        title="Runs"
        action={
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            {Object.keys(runs).length} run{Object.keys(runs).length === 1 ? "" : "s"} this
            session
          </span>
        }
      >
        {Object.keys(runs).length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No runs yet this page view. Run the simulation or a scenario below.
          </p>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {Object.values(runs).map((r) => (
              <RunRow
                key={r.id}
                run={r}
                onPause={() => pauseRun(r.id)}
                onCancel={() => cancelRun(r.id)}
              />
            ))}
          </ul>
        )}
      </SectionCard>

      <SectionCard
        title="Scenarios"
        action={
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            {scenarios.length} scenario{scenarios.length === 1 ? "" : "s"}
          </span>
        }
      >
        {scenarios.length === 0 ? (
          <p className="mb-3 text-sm text-zinc-500 dark:text-zinc-400">
            No scenarios on this simulation yet. Create one below and run it
            against the baseline.
          </p>
        ) : (
          <ul className="mb-3 divide-y divide-zinc-100 dark:divide-zinc-800">
            {scenarios.map((sc) => (
              <li
                key={sc.id}
                className="flex flex-wrap items-center justify-between gap-3 py-2"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                      {sc.name}
                    </span>
                    <StatusBadge status={sc.scenario_type as never} />
                    {sc.is_baseline && (
                      <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                        baseline
                      </span>
                    )}
                  </div>
                  {sc.description && (
                    <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
                      {sc.description}
                    </p>
                  )}
                </div>
                <ActionButton
                  busy={busyRun === sc.id}
                  onClick={() => runScenario(sc.id)}
                >
                  Run scenario
                </ActionButton>
              </li>
            ))}
          </ul>
        )}

        <div className="space-y-2 border-t border-zinc-100 pt-3 text-sm dark:border-zinc-800">
          <p className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            New scenario on this simulation
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input
              value={scName}
              onChange={(e) => setScName(e.target.value)}
              placeholder="e.g. Stress: 20% demand spike"
              className={INPUT_CLASS}
            />
            <select
              value={scType}
              onChange={(e) => setScType(e.target.value)}
              className={SELECT_CLASS}
            >
              {SCENARIO_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <textarea
            value={scDescription}
            onChange={(e) => setScDescription(e.target.value)}
            placeholder="Description (optional)"
            rows={2}
            className={INPUT_CLASS}
          />
          <textarea
            value={scAssumptions}
            onChange={(e) => setScAssumptions(e.target.value)}
            placeholder={'Assumptions JSON (optional), e.g. {"demand_growth": 0.2}'}
            rows={2}
            className={`${INPUT_CLASS} font-mono text-xs`}
          />
          <ActionButton
            busy={creatingSc}
            disabled={!scName.trim()}
            onClick={createScenarioNow}
          >
            Create scenario
          </ActionButton>
        </div>
      </SectionCard>
    </div>
  );
}

function RunRow({
  run,
  onPause,
  onCancel,
}: {
  run: SimulationRunPublic;
  onPause: () => void;
  onCancel: () => void;
}) {
  const [state, setState] = useState<Record<string, unknown> | null>(null);
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);
  const [results, setResults] = useState<SimulationResultsPublic | null>(null);
  const [expanded, setExpanded] = useState(false);

  async function loadDetail() {
    setExpanded(true);
    try {
      const [st] = await Promise.all([
        fetchSimulationState(run.id),
      ]);
      setState({
        status: st.status,
        tick: st.tick,
        entities: st.entities,
        events: st.events,
      });
    } catch {
      /* keep partial */
    }
    try {
      const [evs, res] = await Promise.all([
        fetchSimulationEvents(run.id),
        fetchSimulationResults(run.id),
      ]);
      setEvents(evs as unknown as Record<string, unknown>[]);
      setResults(res);
    } catch {
      /* results may not exist until a run completes */
    }
  }

  return (
    <li className="py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={run.status as never} />
          <span className="font-mono text-xs text-zinc-600 dark:text-zinc-400">
            {run.id.slice(0, 8)}
          </span>
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            {run.tick_count} ticks · seed {run.seed ?? "auto"}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={loadDetail}
            className="rounded-md border border-zinc-300 px-2.5 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            {expanded ? "Collapse" : "State & results"}
          </button>
          <ActionButton
            disabled={run.status !== "running" && run.status !== "ready"}
            onClick={onPause}
          >
            Pause
          </ActionButton>
          <ActionButton
            disabled={["completed", "cancelled", "failed"].includes(run.status)}
            onClick={onCancel}
          >
            Cancel
          </ActionButton>
        </div>
      </div>
      {run.error_message && (
        <p className="mt-1 text-xs text-red-600 dark:text-red-400">
          {run.error_message}
        </p>
      )}
      {expanded && (
        <div className="mt-2 space-y-2">
          {state && (
            <div>
              <p className="mb-1 text-xs uppercase tracking-wide text-zinc-500">
                live state (simulated)
              </p>
              <JsonBlock value={state} />
            </div>
          )}
          {events.length > 0 && (
            <div>
              <p className="mb-1 text-xs uppercase tracking-wide text-zinc-500">
                events ({events.length})
              </p>
              <ul className="space-y-1 text-xs">
                {events.slice(0, 30).map((e, i) => (
                  <li key={i} className="flex gap-2 text-zinc-600 dark:text-zinc-400">
                    <span className="font-mono text-zinc-400">
                      t{Number((e as { tick?: number }).tick ?? "?")}
                    </span>
                    <StatusBadge
                      status={String((e as { event_kind?: string }).event_kind ?? "unknown") as never}
                    />
                    <span className="truncate">
                      {String((e as { entity_ref?: string }).entity_ref ?? "")}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {results && (
            <div>
              <p className="mb-1 text-xs uppercase tracking-wide text-zinc-500">
                multi-run results — {results.iterations} iterations · modeled
                estimates (SIMULATED)
              </p>
              {results.summary_json && <JsonBlock value={results.summary_json} />}
              <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                <Link
                  href={`/simulations/compare`}
                  className="text-indigo-600 hover:underline dark:text-indigo-400"
                >
                  Compare this run against a baseline →
                </Link>
              </p>
            </div>
          )}
        </div>
      )}
    </li>
  );
}