"use client";

import { useEffect, useState } from "react";
import { GitBranch } from "lucide-react";
import { fetchMissionGraph } from "@/lib/api";
import type { MissionGraph, MissionGraphRelation } from "@/lib/types";
import { useStartup } from "../_components/StartupShell";
import { SectionCard } from "../_components/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; graph: MissionGraph }
  | { kind: "error"; message: string };

const RELATIONS: (MissionGraphRelation | "")[] = [
  "",
  "derived_from",
  "depends_on",
  "assigned_to",
  "executed_by",
  "measured_by",
  "blocked_by",
  "generated_by",
  "improves",
  "triggers",
];

export default function MissionGraphPage() {
  const { companyId } = useStartup();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [relation, setRelation] = useState<string>("");
  const [grouped, setGrouped] = useState(false);

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    fetchMissionGraph(companyId, undefined, relation || undefined)
      .then((graph) => !cancelled && setState({ kind: "ok", graph }))
      .catch((err: Error) =>
        !cancelled && setState({ kind: "error", message: err.message }),
      );
    return () => {
      cancelled = true;
    };
  }, [companyId, relation]);

  const edges = state.kind === "ok" ? state.graph.edges : [];
  const groupedEdges = new Map<string, typeof edges>();
  for (const e of edges) {
    const key = `${e.source_type} → ${e.target_type}`;
    groupedEdges.set(key, [...(groupedEdges.get(key) ?? []), e]);
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
            Mission graph
          </h2>
          <p className="max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
            Every startup artifact links into a directed provenance graph as it
            is created. Walking edges back answers &quot;why does this exist&quot; —
            each route ends at a mission.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={relation}
            onChange={(e) => setRelation(e.target.value)}
            className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          >
            {RELATIONS.map((r) => (
              <option key={r} value={r}>
                {r === "" ? "All relations" : r.replace("_", " ")}
              </option>
            ))}
          </select>
          <button
            onClick={() => setGrouped((v) => !v)}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            {grouped ? "Flat view" : "Group by nodes"}
          </button>
        </div>
      </div>

      {state.kind === "loading" && (
        <div className="h-64 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
      )}
      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
          {state.message}
        </p>
      )}

      {state.kind === "ok" && edges.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <GitBranch className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            No graph edges yet. Runs the mission pipeline (analyze → validate →
            plan → bootstrap → cycles) to record provenance edges.
          </p>
        </div>
      )}

      {state.kind === "ok" && edges.length > 0 && (
        <SectionCard title={`${edges.length} edges`}>
          {grouped ? (
            <ul className="space-y-3">
              {Array.from(groupedEdges.entries()).map(([key, list]) => (
                <li key={key}>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                    {key} · {list.length}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {list.map((e) => (
                      <span
                        key={e.id}
                        className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
                      >
                        {e.relation.replace("_", " ")}
                      </span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <ul className="max-h-[28rem] space-y-1.5 overflow-y-auto">
              {edges.map((e) => (
                <li key={e.id} className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                    {e.source_type}
                  </span>
                  <span className="text-zinc-400">{e.relation.replace("_", " ")}</span>
                  <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                    {e.target_type}
                  </span>
                  <span className="ml-auto font-mono text-[11px] text-zinc-400">
                    {e.source_id.slice(0, 8)} → {e.target_id.slice(0, 8)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      )}
    </div>
  );
}