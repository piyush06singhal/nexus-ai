"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  createSimulation,
  fetchSimulations,
  runSimulation,
} from "@/lib/api";
import type {
  SimulationPublic,
  SimulationRunPublic,
  SimulationVariableInput,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { usePhase12 } from "@/components/phase12/Phase12Shell";
import { ActionButton, SectionCard } from "@/components/phase12/ui";

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

const VM_KINDS = [
  "integer",
  "float",
  "boolean",
  "string",
  "enum",
  "duration",
  "percentage",
  "currency",
  "rate",
] as const;

const INPUT_CLASS =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";
const SELECT_CLASS =
  "rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

interface VariableRow {
  name: string;
  kind: string;
  value: string;
}

export default function SimulationsPage() {
  const { companyId } = usePhase12();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [simulations, setSimulations] = useState<SimulationPublic[]>([]);
  const [recentRuns, setRecentRuns] = useState<
    Record<string, SimulationRunPublic>
  >({});
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  // create simulation form
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [scenarioType, setScenarioType] = useState("what_if");
  const [horizonDays, setHorizonDays] = useState("90");
  const [clockTick, setClockTick] = useState("week");
  const [variables, setVariables] = useState<VariableRow[]>([
    { name: "", kind: "integer", value: "" },
  ]);
  const [creating, setCreating] = useState(false);
  const [runningId, setRunningId] = useState<string | null>(null);

  function load() {
    if (!companyId) return;
    fetchSimulations({ companyId })
      .then((list) => {
        setError(null);
        setSimulations(list);
        setState({ kind: "ok" });
      })
      .catch((err: unknown) => {
        setState({
          kind: "error",
          message:
            err instanceof Error
              ? err.message
              : "Failed to load simulations",
        });
      });
  }

  useEffect(() => {
    if (!companyId) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  function setVariable(i: number, patch: Partial<VariableRow>) {
    setVariables((rows) =>
      rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)),
    );
  }

  async function runNow(id: string) {
    setRunningId(id);
    setError(null);
    setDone(null);
    try {
      const run = await runSimulation(id, { iterations: 1 });
      setRecentRuns((prev) => ({ ...prev, [id]: run }));
      setDone(
        `Run ${run.id.slice(0, 8)} → ${run.status}. Open the simulation to inspect state and results.`,
      );
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to start simulation",
      );
    } finally {
      setRunningId(null);
    }
  }

  async function createSim() {
    if (!companyId) {
      setError("Select a company first.");
      return;
    }
    if (!name.trim()) {
      setError("Give the simulation a name.");
      return;
    }
    const goodVars = variables.filter((v) => v.name.trim());
    const input = {
      company_id: companyId,
      name: name.trim(),
      description: description.trim() || null,
      scenario_type: scenarioType,
      horizon_days: Number(horizonDays) || undefined,
      clock_tick: clockTick,
      variables: goodVars.map(
        (v): SimulationVariableInput => ({
          name: v.name.trim(),
          kind: v.kind,
          value: v.value.trim() || null,
        }),
      ),
    };
    setCreating(true);
    setError(null);
    setDone(null);
    try {
      const created = await createSimulation(input);
      setDone(`Simulation "${created.name}" created (${created.scenario_type}).`);
      setName("");
      setDescription("");
      setVariables([{ name: "", kind: "integer", value: "" }]);
      load();
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to create simulation",
      );
    } finally {
      setCreating(false);
    }
  }

  if (!companyId) {
    return (
      <p className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
        Select a company in the top bar to run and compare simulations.
      </p>
    );
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
        Simulations run in a <strong>closed sandbox</strong> — the digital twin
        is a read-only model of the company and simulations perform zero real
        side effects. All outputs are modeled estimates labeled SIMULATED /
        FORECAST, never ACTUAL.
      </p>

      <SectionCard
        title="Define a new simulation"
        action={
          <ActionButton
            busy={creating}
            disabled={!companyId || !name.trim()}
            onClick={createSim}
          >
            Create simulation
          </ActionButton>
        }
      >
        <div className="space-y-3 text-sm">
          <div className="grid gap-2 sm:grid-cols-2">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. What-if: grow engineering 5 → 7"
              className={INPUT_CLASS}
            />
            <select
              value={scenarioType}
              onChange={(e) => setScenarioType(e.target.value)}
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
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description (optional)"
            rows={2}
            className={INPUT_CLASS}
          />
          <div className="grid gap-2 sm:grid-cols-2">
            <input
              type="number"
              value={horizonDays}
              onChange={(e) => setHorizonDays(e.target.value)}
              placeholder="horizon (days)"
              className={INPUT_CLASS}
            />
            <select
              value={clockTick}
              onChange={(e) => setClockTick(e.target.value)}
              className={SELECT_CLASS}
            >
              <option value="day">day</option>
              <option value="week">week</option>
              <option value="hour">hour</option>
            </select>
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <p className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                Model variables (simulation inputs)
              </p>
              <button
                type="button"
                onClick={() =>
                  setVariables((rows) => [
                    ...rows,
                    { name: "", kind: "integer", value: "" },
                  ])
                }
                className="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400"
              >
                + Add variable
              </button>
            </div>
            {variables.map((v, i) => (
              <div
                key={i}
                className="mb-2 grid grid-cols-[1fr_auto_1fr] gap-2"
              >
                <input
                  value={v.name}
                  onChange={(e) => setVariable(i, { name: e.target.value })}
                  placeholder={`variable ${i + 1} (e.g. employee_count)`}
                  className={INPUT_CLASS}
                />
                <select
                  value={v.kind}
                  onChange={(e) => setVariable(i, { kind: e.target.value })}
                  className={SELECT_CLASS}
                >
                  {VM_KINDS.map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
                <input
                  value={v.value}
                  onChange={(e) => setVariable(i, { value: e.target.value })}
                  placeholder="value"
                  className={INPUT_CLASS}
                />
              </div>
            ))}
          </div>
        </div>
      </SectionCard>

      <SimulationList
        simulations={simulations}
        recentRuns={recentRuns}
        runningId={runningId}
        onRun={runNow}
      />
    </div>
  );
}

function SimulationList({
  simulations,
  recentRuns,
  runningId,
  onRun,
}: {
  simulations: SimulationPublic[];
  recentRuns: Record<string, SimulationRunPublic>;
  runningId: string | null;
  onRun: (id: string) => void;
}) {
  return (
    <SectionCard
      title="Simulations"
      action={
        <span className="text-xs text-zinc-500 dark:text-zinc-400">
          {simulations.length} simulation{simulations.length === 1 ? "" : "s"}
        </span>
      }
    >
      {simulations.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          No simulations yet. Define one above, or open one of its scenarios.
        </p>
      ) : (
        <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {simulations.map((s) => {
            const run = recentRuns[s.id];
            return (
              <li
                key={s.id}
                className="flex flex-wrap items-center justify-between gap-3 py-3"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      href={`/simulations/${s.id}`}
                      className="text-sm font-medium text-indigo-600 hover:underline dark:text-indigo-400"
                    >
                      {s.name}
                    </Link>
                    <StatusBadge status={s.status as never} />
                    <StatusBadge status={s.scenario_type as never} />
                    {s.sandboxed && (
                      <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                        sandboxed
                      </span>
                    )}
                  </div>
                  {s.description && (
                    <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
                      {s.description}
                    </p>
                  )}
                  <p className="mt-0.5 text-xs text-zinc-400">
                    horizon {s.horizon_days ?? "—"}d · tick {s.clock_tick} ·
                    model {s.model_name ?? "—"} v{s.model_version ?? "—"} ·
                    created {new Date(s.created_at).toLocaleString()}
                  </p>
                  {run && (
                    <p className="mt-1 inline-flex items-center gap-2 text-xs">
                      <StatusBadge status={run.status as never} />
                      <span className="font-mono text-zinc-500 dark:text-zinc-400">
                        run {run.id.slice(0, 8)} · {run.tick_count} ticks
                      </span>
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Link
                    href={`/simulations/${s.id}`}
                    className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
                  >
                    Open
                  </Link>
                  <ActionButton
                    busy={runningId === s.id}
                    disabled={!["draft", "ready"].includes(s.status)}
                    onClick={() => onRun(s.id)}
                  >
                    Run
                  </ActionButton>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </SectionCard>
  );
}