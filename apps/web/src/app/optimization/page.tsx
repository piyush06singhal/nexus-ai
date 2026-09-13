"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  approveOptimizationCycle,
  cancelOptimizationCycle,
  createOptimizationCycle,
  createOptimizationProblem,
  fetchOptimizationCycles,
  fetchOptimizationProblems,
  runOptimizationCycle,
  runOptimizationProblem,
} from "@/lib/api";
import type {
  OptimizationCyclePublic,
  OptimizationProblemPublic,
  OptimizationRunPublic,
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

/** A cycle is finished once it reaches a terminal state. */
const TERMINAL_CYCLE_STATUSES = ["completed", "cancelled", "failed"];

const INPUT_CLASS =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";
const SELECT_CLASS =
  "rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

interface ObjectiveRow {
  metric: string;
  direction: string;
  weight: string;
}

interface VariableRow {
  name: string;
  kind: string;
  low: string;
  high: string;
}

const VARIABLE_KINDS = [
  "float",
  "integer",
  "percentage",
  "currency",
  "rate",
  "boolean",
  "enum",
  "string",
] as const;

export default function OptimizationPage() {
  const { companyId } = usePhase12();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [problems, setProblems] = useState<OptimizationProblemPublic[]>([]);
  const [cycles, setCycles] = useState<OptimizationCyclePublic[]>([]);
  const [recentRuns, setRecentRuns] = useState<
    Record<string, OptimizationRunPublic>
  >({});

  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  // create form
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [strategy, setStrategy] = useState("");
  const [objectives, setObjectives] = useState<ObjectiveRow[]>([
    { metric: "", direction: "maximize", weight: "1" },
    { metric: "", direction: "maximize", weight: "1" },
  ]);
  const [variables, setVariables] = useState<VariableRow[]>([
    { name: "", kind: "float", low: "", high: "" },
  ]);
  const [constraintsText, setConstraintsText] = useState("");
  const [constraintsError, setConstraintsError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [runningProblem, setRunningProblem] = useState<string | null>(null);

  // cycle coordinator
  const [cycleName, setCycleName] = useState("");
  const [cycleObserve, setCycleObserve] = useState(true);
  const [cycleBusy, setCycleBusy] = useState<"create" | string | null>(null);

  function load() {
    if (!companyId) return;
    Promise.all([
      fetchOptimizationProblems({ companyId }),
      fetchOptimizationCycles({ companyId }),
    ])
      .then(([pl, cy]) => {
        setError(null);
        setProblems(pl);
        setCycles(cy);
        setState({ kind: "ok" });
      })
      .catch((err: unknown) => {
        setState({
          kind: "error",
          message:
            err instanceof Error
              ? err.message
              : "Failed to load optimization center",
        });
      });
  }

  useEffect(() => {
    if (!companyId) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  function setObjective(i: number, patch: Partial<ObjectiveRow>) {
    setObjectives((rows) =>
      rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)),
    );
  }

  function setVariable(i: number, patch: Partial<VariableRow>) {
    setVariables((rows) =>
      rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)),
    );
  }

  async function runProblem(problemId: string) {
    setRunningProblem(problemId);
    setError(null);
    setDone(null);
    try {
      const run = await runOptimizationProblem(problemId);
      setRecentRuns((prev) => ({ ...prev, [problemId]: run }));
      setDone(
        `Run ${run.id.slice(0, 8)} → ${run.status}. Open the problem to inspect candidates.`,
      );
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to start optimization run",
      );
    } finally {
      setRunningProblem(null);
    }
  }

  async function createProblem() {
    if (!companyId) {
      setError("Select a company first.");
      return;
    }
    const goodObjectives = objectives.filter((o) => o.metric.trim());
    if (!name.trim()) {
      setError("Give the problem a name.");
      return;
    }
    if (goodObjectives.length === 0) {
      setError("Add at least one objective (metric + direction).");
      return;
    }
    // Constraints are expressed as a JSON array of {name, description} specs.
    // Real bounds are enforced by PolicyEngine + resource governance at run
    // time; the JSON here is informational, so a tolerant parse is fine.
    let constraints: Record<string, unknown>[] | null = null;
    if (constraintsText.trim()) {
      try {
        const parsed = JSON.parse(constraintsText);
        if (!Array.isArray(parsed)) {
          setConstraintsError("Constraints must be a JSON array.");
          return;
        }
        constraints = parsed as Record<string, unknown>[];
      } catch {
        setConstraintsError(
          "Constraints JSON is invalid. Fix it (a JSON array of {name, description}) or clear the field.",
        );
        return;
      }
    }
    setConstraintsError(null);
    const input = {
      company_id: companyId,
      name: name.trim(),
      description: description.trim() || null,
      strategy: strategy.trim() || null,
      objectives: goodObjectives.map((o) => ({
        metric: o.metric.trim(),
        direction: o.direction,
        weight: Number(o.weight) || 0,
      })),
      variables: variables
        .filter((v) => v.name.trim())
        .map((v) => ({
          name: v.name.trim(),
          kind: v.kind,
          low: v.low.trim() ? Number(v.low) : null,
          high: v.high.trim() ? Number(v.high) : null,
        })),
      constraints,
    };
    setCreating(true);
    setError(null);
    setDone(null);
    try {
      const created = await createOptimizationProblem(input);
      setDone(`Problem "${created.name}" created.`);
      setName("");
      setDescription("");
      setStrategy("");
      setObjectives([
        { metric: "", direction: "maximize", weight: "1" },
        { metric: "", direction: "maximize", weight: "1" },
      ]);
      setVariables([{ name: "", kind: "float", low: "", high: "" }]);
      setConstraintsText("");
      load();
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to create problem",
      );
    } finally {
      setCreating(false);
    }
  }

  async function cycleAct(action: "create" | "run" | "approve" | "cancel", id?: string) {
    if (!companyId) {
      setError("Select a company first.");
      return;
    }
    setCycleBusy(action === "create" ? "create" : `${id}:${action}`);
    setError(null);
    setDone(null);
    try {
      if (action === "create") {
        if (!cycleName.trim()) {
          setError("Give the cycle a name.");
          return;
        }
        const c = await createOptimizationCycle({
          company_id: companyId,
          name: cycleName.trim(),
          observe: cycleObserve,
        });
        setDone(`Cycle "${c.name}" created → ${c.status}. Run it to start.`);
        setCycleName("");
      } else if (id) {
        if (action === "run") {
          const c = await runOptimizationCycle(id);
          setDone(`Cycle run complete → ${c.status}.`);
        } else if (action === "approve") {
          const c = await approveOptimizationCycle(id);
          setDone(`Cycle approved → ${c.status}.`);
        } else {
          const c = await cancelOptimizationCycle(id);
          setDone(`Cycle cancelled → ${c.status}.`);
        }
      }
      load();
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Cycle action failed",
      );
    } finally {
      setCycleBusy(null);
    }
  }

  if (!companyId) {
    return (
      <p className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
        Select a company in the top bar to view and run optimization problems.
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
        Optimization builds <strong>modeled</strong> candidates and proposes
        changes — it never applies anything to production. Run results are
        estimates for review; turning a proposal into action happens through
        approval elsewhere.
      </p>

      <SectionCard
        title="Define a new optimization problem"
        action={
          <ActionButton
            busy={creating}
            disabled={!companyId || !name.trim()}
            onClick={createProblem}
          >
            Create problem
          </ActionButton>
        }
      >
        <div className="space-y-3 text-sm">
          <div className="grid gap-2 sm:grid-cols-2">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Problem name (e.g. Reduce compute cost vs. latency)"
              className={INPUT_CLASS}
            />
            <input
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              placeholder="Strategy (optional, e.g. greedy / genetic / random)"
              className={INPUT_CLASS}
            />
          </div>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description (optional)"
            rows={2}
            className={INPUT_CLASS}
          />

          <div>
            <div className="mb-1 flex items-center justify-between">
              <p className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                Objectives (what we optimize)
              </p>
              <button
                type="button"
                onClick={() =>
                  setObjectives((rows) => [
                    ...rows,
                    { metric: "", direction: "maximize", weight: "1" },
                  ])
                }
                className="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400"
              >
                + Add objective
              </button>
            </div>
            {objectives.map((o, i) => (
              <div
                key={i}
                className="mb-2 grid grid-cols-[1fr_auto_auto] gap-2"
              >
                <input
                  value={o.metric}
                  onChange={(e) => setObjective(i, { metric: e.target.value })}
                  placeholder={`metric ${i + 1} (e.g. compute_cost)`}
                  className={INPUT_CLASS}
                />
                <select
                  value={o.direction}
                  onChange={(e) =>
                    setObjective(i, { direction: e.target.value })
                  }
                  className={SELECT_CLASS}
                >
                  <option value="maximize">maximize</option>
                  <option value="minimize">minimize</option>
                </select>
                <input
                  type="number"
                  step="0.1"
                  value={o.weight}
                  onChange={(e) => setObjective(i, { weight: e.target.value })}
                  title="weight"
                  className={`${INPUT_CLASS} w-20`}
                />
              </div>
            ))}
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <p className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                Variables (decision space)
              </p>
              <button
                type="button"
                onClick={() =>
                  setVariables((rows) => [
                    ...rows,
                    { name: "", kind: "float", low: "", high: "" },
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
                className="mb-2 grid grid-cols-[1fr_auto_5rem_5rem] gap-2"
              >
                <input
                  value={v.name}
                  onChange={(e) => setVariable(i, { name: e.target.value })}
                  placeholder={`variable ${i + 1} (e.g. worker_count)`}
                  className={INPUT_CLASS}
                />
                <select
                  value={v.kind}
                  onChange={(e) => setVariable(i, { kind: e.target.value })}
                  className={SELECT_CLASS}
                >
                  {VARIABLE_KINDS.map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  value={v.low}
                  onChange={(e) => setVariable(i, { low: e.target.value })}
                  placeholder="low"
                  className={INPUT_CLASS}
                />
                <input
                  type="number"
                  value={v.high}
                  onChange={(e) => setVariable(i, { high: e.target.value })}
                  placeholder="high"
                  className={INPUT_CLASS}
                />
              </div>
            ))}
          </div>

          <div>
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              Constraints (informational JSON; policy + resource limits are
              enforced at run time)
            </p>
            <textarea
              value={constraintsText}
              onChange={(e) => {
                setConstraintsText(e.target.value);
                setConstraintsError(null);
              }}
              placeholder={'[{"name": "budget_cap", "description": "…"}]'}
              rows={2}
              className={`${INPUT_CLASS} font-mono text-xs`}
            />
            {constraintsError && (
              <p className="mt-1 text-xs text-red-600 dark:text-red-400">
                {constraintsError}
              </p>
            )}
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="Optimization problems"
        action={
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            {problems.length} problem{problems.length === 1 ? "" : "s"}
          </span>
        }
      >
        {problems.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No problems yet. Define one above to start.
          </p>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {problems.map((p) => {
              const run = recentRuns[p.id];
              const objectives_ = (
                (p.objective_json?.objectives as
                  | { metric: string; direction?: string; weight?: number }[]
                  | undefined) ?? []
              );
              return (
                <li
                  key={p.id}
                  className="flex flex-wrap items-center justify-between gap-3 py-3"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        href={`/optimization/${p.id}`}
                        className="text-sm font-medium text-indigo-600 hover:underline dark:text-indigo-400"
                      >
                        {p.name}
                      </Link>
                      <StatusBadge status={p.status as never} />
                      {p.strategy && (
                        <span className="text-xs text-zinc-500 dark:text-zinc-400">
                          strategy {p.strategy}
                        </span>
                      )}
                    </div>
                    {p.description && (
                      <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
                        {p.description}
                      </p>
                    )}
                    {objectives_.length > 0 && (
                      <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">
                        {objectives_.map((o, i) => (
                          <span key={i} className="mr-3 inline-flex items-center gap-1">
                            <StatusBadge status={"minimize"} />
                            {o.metric}
                            <span className="text-zinc-400">×{o.weight ?? 1}</span>
                          </span>
                        ))}
                      </p>
                    )}
                    <p className="mt-0.5 text-xs text-zinc-400">
                      created {new Date(p.created_at).toLocaleString()}
                    </p>
                    {run && (
                      <p className="mt-1 inline-flex items-center gap-2 text-xs">
                        <StatusBadge status={run.status as never} />
                        <span className="font-mono text-zinc-500 dark:text-zinc-400">
                          run {run.id.slice(0, 8)}
                        </span>
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/optimization/${p.id}`}
                      className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
                    >
                      Open
                    </Link>
                    <ActionButton
                      busy={runningProblem === p.id}
                      onClick={() => runProblem(p.id)}
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

      <CyclePanel
        cycles={cycles}
        companyId={companyId}
        cycleName={cycleName}
        setCycleName={setCycleName}
        cycleObserve={cycleObserve}
        setCycleObserve={setCycleObserve}
        cycleBusy={cycleBusy}
        onAct={cycleAct}
      />
    </div>
  );
}

// ── closed-loop cycle coordinator ────────────────────────────────────────────

function CyclePanel({
  cycles,
  companyId,
  cycleName,
  setCycleName,
  cycleObserve,
  setCycleObserve,
  cycleBusy,
  onAct,
}: {
  cycles: OptimizationCyclePublic[];
  companyId: string | null;
  cycleName: string;
  setCycleName: (v: string) => void;
  cycleObserve: boolean;
  setCycleObserve: (v: boolean) => void;
  cycleBusy: "create" | string | null;
  onAct: (action: "create" | "run" | "approve" | "cancel", id?: string) => void;
}) {
  return (
    <SectionCard
      title="Closed-loop optimization cycles"
      action={
        <span className="text-xs text-zinc-500 dark:text-zinc-400">
          observe → simulate → optimize → propose → approve → execute
        </span>
      }
    >
      <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
        A cycle coordinates the full loop and records references only —
        execution is delegated to governed systems <strong>after</strong> an
        approval gate. The proposal step is the boundary: nothing touches
        production without explicit approval.
      </p>

      <div className="mb-4 flex flex-wrap items-end gap-2">
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-zinc-500 dark:text-zinc-400">
            New cycle name
          </span>
          <input
            value={cycleName}
            onChange={(e) => setCycleName(e.target.value)}
            placeholder="e.g. Q3 cost–latency tuning"
            className="w-64 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
        </label>
        <label className="flex items-center gap-2 pb-1.5 text-sm text-zinc-600 dark:text-zinc-400">
          <input
            type="checkbox"
            checked={cycleObserve}
            onChange={(e) => setCycleObserve(e.target.checked)}
          />
          seed from observed state
        </label>
        <ActionButton
          busy={cycleBusy === "create"}
          disabled={!companyId || !cycleName.trim()}
          onClick={() => onAct("create")}
        >
          Create cycle
        </ActionButton>
      </div>

      {cycles.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          No cycles yet. Create one to run the closed loop.
        </p>
      ) : (
        <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {cycles.map((c) => {
            const terminal = TERMINAL_CYCLE_STATUSES.includes(c.status);
            return (
              <li key={c.id} className="py-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                        {c.name}
                      </span>
                      <StatusBadge status={c.status as never} />
                    </div>
                    <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                      <span className="font-mono">{c.id.slice(0, 8)}</span> ·
                      started {new Date(c.started_at).toLocaleString()}
                      {c.completed_at
                        ? ` · completed ${new Date(c.completed_at).toLocaleString()}`
                        : ""}
                      {c.error_message ? ` · ${c.error_message}` : ""}
                    </p>
                    {(c.simulation_run_id ||
                      c.optimization_run_id ||
                      c.recommendation_id ||
                      c.approval_gate_id ||
                      c.execute_ref) && (
                      <p className="mt-1 truncate font-mono text-[11px] text-zinc-500 dark:text-zinc-400">
                        sim {c.simulation_run_id ? c.simulation_run_id.slice(0, 8) : "—"}
                        {" · "}opt {c.optimization_run_id ? c.optimization_run_id.slice(0, 8) : "—"}
                        {" · "}rec {c.recommendation_id ? c.recommendation_id.slice(0, 8) : "—"}
                        {" · "}gate {c.approval_gate_id ? c.approval_gate_id.slice(0, 8) : "—"}
                        {c.execute_ref ? ` · apply ${c.execute_ref}` : ""}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <ActionButton
                      busy={cycleBusy === `${c.id}:run`}
                      disabled={c.status !== "observing"}
                      onClick={() => onAct("run", c.id)}
                    >
                      Run cycle
                    </ActionButton>
                    <ActionButton
                      busy={cycleBusy === `${c.id}:approve`}
                      disabled={c.status !== "awaiting_approval"}
                      onClick={() => onAct("approve", c.id)}
                    >
                      Approve
                    </ActionButton>
                    <ActionButton
                      busy={cycleBusy === `${c.id}:cancel`}
                      disabled={terminal}
                      onClick={() => onAct("cancel", c.id)}
                    >
                      Cancel
                    </ActionButton>
                  </div>
                </div>

                {(c.measures_json || c.lesson_json) && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                      {c.status === "completed" || c.status === "learning"
                        ? "Measures & lesson learned"
                        : "Modeled measures so far"}
                    </summary>
                    <div className="mt-2 space-y-2">
                      {c.measures_json && (
                        <div>
                          <p className="mb-1 text-xs uppercase tracking-wide text-zinc-500">
                            measures (modeled)
                          </p>
                          <JsonBlock value={c.measures_json} />
                        </div>
                      )}
                      {c.lesson_json && (
                        <div>
                          <p className="mb-1 text-xs uppercase tracking-wide text-zinc-500">
                            lesson
                          </p>
                          <JsonBlock value={c.lesson_json} />
                        </div>
                      )}
                    </div>
                  </details>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </SectionCard>
  );
}