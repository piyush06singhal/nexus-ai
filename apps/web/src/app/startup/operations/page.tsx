"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { GitBranch, Play } from "lucide-react";
import {
  fetchCycles,
  fetchMissions,
  runCycle,
} from "@/lib/api";
import type { Mission, OperatingCycle } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { useStartup } from "../_components/StartupShell";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; cycles: OperatingCycle[]; missions: Mission[] }
  | { kind: "error"; message: string };

export default function OperationsPage() {
  const { companyId, href } = useStartup();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [selectedMission, setSelectedMission] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    Promise.all([fetchCycles(companyId), fetchMissions(companyId)])
      .then(([cycles, missions]) => {
        if (!cancelled) {
          setState({ kind: "ok", cycles, missions });
          setSelectedMission((cur) => cur || (missions[0]?.id ?? ""));
        }
      })
      .catch((err: Error) =>
        !cancelled && setState({ kind: "error", message: err.message }),
      );
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  async function startCycle() {
    if (!companyId || !selectedMission) return;
    setBusy(true);
    setMsg(null);
    try {
      const cycle = await runCycle(companyId, { mission_id: selectedMission });
      setMsg(`Cycle #${cycle.cycle_number} → ${cycle.status}.`);
      const cycles = await fetchCycles(companyId);
      setState((s) => (s.kind === "ok" ? { ...s, cycles } : s));
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Failed to run cycle");
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

  const { cycles, missions } = state;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4 rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
        <div>
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            Run an operating cycle
          </h2>
          <p className="mt-1 max-w-xl text-sm text-zinc-600 dark:text-zinc-400">
            OperatingEngine runs the 10-stage loop — observe → assess → plan →
            prioritize → allocate → execute → verify → measure → learn → replan —
            and writes an immutable cycle record. The engine is bounded by the
            company&apos;s autonomy policy.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {missions.length > 0 && (
            <select
              value={selectedMission}
              onChange={(e) => setSelectedMission(e.target.value)}
              className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            >
              {missions.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.title}
                </option>
              ))}
            </select>
          )}
          <button
            onClick={startCycle}
            disabled={busy || missions.length === 0}
            className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            <Play className="h-4 w-4" />
            {busy ? "Running…" : "Run cycle"}
          </button>
        </div>
      </div>

      {msg && (
        <p className="rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300">
          {msg}
        </p>
      )}

      {cycles.length === 0 ? (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <GitBranch className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            No operating cycles yet. Run one for a mission above, or bootstrap a
            startup plan from a mission.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-zinc-200 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
              <tr>
                <th className="px-4 py-3">Cycle</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Stages</th>
                <th className="px-4 py-3">Failures</th>
                <th className="px-4 py-3">Recovery</th>
                <th className="px-4 py-3">Started</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {cycles.map((c) => (
                <tr key={c.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-900/40">
                  <td className="px-4 py-3 font-medium text-zinc-900 dark:text-zinc-100">
                    #{c.cycle_number}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={c.status} />
                  </td>
                  <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">
                    {c.stages.length}
                  </td>
                  <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">
                    {c.failures.length}
                  </td>
                  <td className="px-4 py-3">
                    {c.recovery.length > 0 ? (
                      <StatusBadge status={c.recovery[0].outcome === "recovered" ? "recovered" : "failed"} />
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">
                    {c.started_at ? new Date(c.started_at).toLocaleString() : "—"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={href(`/startup/operations/${c.id}`)}
                      className="text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
                    >
                      Open →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}