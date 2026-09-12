"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import {
  approveCycleGate,
  cancelCycle,
  getCycle,
  resumeCycle,
} from "@/lib/api";
import type { OperatingCycle } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { useStartup } from "../../_components/StartupShell";
import { ActionButton, Dash, SectionCard } from "../../_components/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; cycle: OperatingCycle }
  | { kind: "error"; message: string };

const STAGES = [
  "observe",
  "assess",
  "plan",
  "prioritize",
  "allocate",
  "execute",
  "verify",
  "measure",
  "learn",
  "replan",
] as const;

export default function CycleDetailPage({
  params,
}: {
  params: Promise<{ cycleId: string }>;
}) {
  const { companyId, href } = useStartup();
  const [cycleId, setCycleId] = useState("");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    params.then((p) => setCycleId(p.cycleId));
  }, [params]);

  useEffect(() => {
    if (!companyId || !cycleId) return;
    let cancelled = false;
    getCycle(companyId, cycleId)
      .then((cycle) => !cancelled && setState({ kind: "ok", cycle }))
      .catch((err: Error) =>
        !cancelled && setState({ kind: "error", message: err.message }),
      );
    return () => {
      cancelled = true;
    };
  }, [companyId, cycleId]);

  async function act(
    action: "resume" | "approve" | "cancel",
  ) {
    if (!companyId || !cycleId) return;
    setBusy(true);
    setMsg(null);
    try {
      if (action === "resume") {
        const c = await resumeCycle(companyId, cycleId);
        setState({ kind: "ok", cycle: c });
        setMsg(`Resumed — new cycle #${c.cycle_number} → ${c.status}.`);
      }
      if (action === "approve") {
        const c = await approveCycleGate(companyId, cycleId);
        setState({ kind: "ok", cycle: c });
        setMsg(`Approval granted for cycle #${c.cycle_number}.`);
      }
      if (action === "cancel") {
        const c = await cancelCycle(companyId, cycleId);
        setState({ kind: "ok", cycle: c });
        setMsg(`Cycle #${c.cycle_number} cancelled.`);
      }
    } catch (err) {
      setMsg(err instanceof Error ? err.message : `Action '${action}' failed`);
    } finally {
      setBusy(false);
    }
  }

  if (state.kind === "loading") {
    return <div className="h-64 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />;
  }
  if (state.kind === "error") {
    return (
      <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
        {state.message}
      </p>
    );
  }

  const { cycle } = state;
  const stageSet = new Set(cycle.stages.map((s) => s.stage));

  return (
    <div className="space-y-6">
      <Link
        href={href("/startup/operations")}
        className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
      >
        <ArrowLeft className="h-4 w-4" /> Operations
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
              Operating cycle #{cycle.cycle_number}
            </h1>
            <StatusBadge status={cycle.status} />
          </div>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            {cycle.started_at ? new Date(cycle.started_at).toLocaleString() : ""}
            {cycle.ended_at
              ? ` — ${new Date(cycle.ended_at).toLocaleString()}`
              : ""}
          </p>
        </div>
        {(cycle.status === "blocked" || cycle.status === "awaiting_approval") && (
          <div className="flex flex-wrap gap-2">
            <ActionButton onClick={() => act("approve")} busy={busy}>
              Approve gate
            </ActionButton>
            <ActionButton onClick={() => act("resume")} busy={busy}>
              Resume
            </ActionButton>
            <ActionButton onClick={() => act("cancel")} busy={busy}>
              Cancel
            </ActionButton>
          </div>
        )}
      </div>

      {msg && (
        <p className="rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300">
          {msg}
        </p>
      )}

      <SectionCard title="Stage timeline">
        <ol className="space-y-1">
          {STAGES.map((name, i) => {
            const run = cycle.stages.find((s) => s.stage === name);
            const reached = stageSet.has(name);
            return (
              <li key={name} className="flex items-center gap-3 py-1.5">
                <span
                  className={
                    "inline-flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-semibold " +
                    (reached
                      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                      : "bg-zinc-100 text-zinc-400 dark:bg-zinc-800 dark:text-zinc-600")
                  }
                >
                  {i + 1}
                </span>
                <span className="w-32 text-sm font-medium text-zinc-900 capitalize dark:text-zinc-100">
                  {name}
                </span>
                {run ? (
                  <>
                    <StatusBadge status={(run.status ?? "completed") as "completed"} />
                    <span className="text-xs text-zinc-500 dark:text-zinc-400">
                      {run.duration_ms
                        ? `${(run.duration_ms / 1000).toFixed(1)}s`
                        : ""}
                    </span>
                  </>
                ) : (
                  <span className="text-xs text-zinc-400 dark:text-zinc-600">
                    not reached
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </SectionCard>

      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard title={`Failures (${cycle.failures.length})`}>
          {cycle.failures.length === 0 ? (
            <Dash value={null} />
          ) : (
            <ul className="space-y-2">
              {cycle.failures.map((f, i) => (
                <li key={i} className="text-sm text-zinc-700 dark:text-zinc-300">
                  <pre className="whitespace-pre-wrap rounded bg-zinc-50 p-2 text-xs dark:bg-zinc-900">
                    {JSON.stringify(f, null, 2)}
                  </pre>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        <SectionCard title={`Recovery (${cycle.recovery.length})`}>
          {cycle.recovery.length === 0 ? (
            <Dash value={null} />
          ) : (
            <ul className="space-y-2">
              {cycle.recovery.map((r, i) => (
                <li key={i} className="text-sm text-zinc-700 dark:text-zinc-300">
                  <div className="flex items-center gap-2">
                    <StatusBadge
                      status={(r.outcome as string) === "recovered" ? "recovered" : "failed"}
                    />
                    <span className="font-medium">
                      {(r.strategy as string)?.replace("_", " ")}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                    {String(r.reason ?? "")}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        <SectionCard title={`Approvals (${cycle.approvals.length})`}>
          {cycle.approvals.length === 0 ? (
            <Dash value={null} />
          ) : (
            <ul className="space-y-1">
              {cycle.approvals.map((a, i) => (
                <li key={i} className="text-sm text-zinc-700 dark:text-zinc-300">
                  {JSON.stringify(a)}
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        <SectionCard title="Outcome">
          {Object.keys(cycle.outcome).length === 0 ? (
            <Dash value={null} />
          ) : (
            <pre className="whitespace-pre-wrap rounded bg-zinc-50 p-3 text-xs text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
              {JSON.stringify(cycle.outcome, null, 2)}
            </pre>
          )}
        </SectionCard>
      </div>

      <SectionCard title="Decisions & actions">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              Decisions ({cycle.decisions.length})
            </p>
            <ul className="space-y-1">
              {cycle.decisions.length === 0 ? (
                <Dash value={null} />
              ) : (
                cycle.decisions.map((d, i) => (
                  <li key={i} className="text-sm text-zinc-700 dark:text-zinc-300">
                    {JSON.stringify(d)}
                  </li>
                ))
              )}
            </ul>
          </div>
          <div>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              Actions ({cycle.actions.length})
            </p>
            <ul className="space-y-1">
              {cycle.actions.length === 0 ? (
                <Dash value={null} />
              ) : (
                cycle.actions.map((a, i) => (
                  <li key={i} className="text-sm text-zinc-700 dark:text-zinc-300">
                    {JSON.stringify(a)}
                  </li>
                ))
              )}
            </ul>
          </div>
        </div>
      </SectionCard>
    </div>
  );
}