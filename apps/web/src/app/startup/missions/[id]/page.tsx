"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, GitBranch, ListChecks } from "lucide-react";
import {
  activateMission,
  analyzeMission,
  cancelMission,
  fetchCycles,
  fetchMissionGraph,
  getMission,
  getStartupPlan,
  pauseMission,
  planMission,
  validateMission,
} from "@/lib/api";
import type {
  Mission,
  MissionAnalysisResult,
  MissionGraph,
  OperatingCycle,
  StartupPlan,
  ValidationResult,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { useStartup } from "../../_components/StartupShell";
import { ActionButton, Dash, SectionCard, StringList } from "../../_components/ui";

type LoadState =
  | { kind: "loading" }
  | {
      kind: "ok";
      mission: Mission;
      startupPlan: StartupPlan | null;
      cycleCount: number;
    }
  | { kind: "error"; message: string };

export default function MissionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { companyId, href, rememberMission } = useStartup();
  const [missionId, setMissionId] = useState<string>("");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [graph, setGraph] = useState<MissionGraph | null>(null);
  const [cycles, setCycles] = useState<OperatingCycle[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    params.then((p) => setMissionId(p.id));
  }, [params]);

  useEffect(() => {
    if (!companyId || !missionId) return;
    let cancelled = false;
    getMission(companyId, missionId)
      .then(async (mission) => {
        const [g, c] = await Promise.all([
          fetchMissionGraph(companyId, missionId),
          fetchCycles(companyId),
        ]);
        if (!cancelled) {
          setGraph(g);
          setCycles(c);
          setState({
            kind: "ok",
            mission,
            startupPlan: null,
            cycleCount: c.length,
          });
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            kind: "error",
            message: err instanceof Error ? err.message : "Failed to load mission",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [companyId, missionId]);

  // Record the plan→mission mapping so /startup/plans/[id] can resolve the
  // mission-scoped fetch after navigation (layout persists across /startup).
  const loadedPlan = state.kind === "ok" ? state.startupPlan : null;
  const loadedMission = state.kind === "ok" ? state.mission : null;
  useEffect(() => {
    if (loadedPlan && loadedMission) rememberMission(loadedPlan.id, loadedMission.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadedPlan?.id, loadedMission?.id]);

  async function runAction(action: "analyze" | "validate" | "plan" | "activate" | "pause" | "cancel") {
    if (!companyId || !missionId) return;
    setBusy(action);
    setMsg(null);
    try {
      if (action === "analyze") await analyzeMission(companyId, missionId);
      if (action === "validate") await validateMission(companyId, missionId);
      if (action === "plan") {
        const result = await planMission(companyId, missionId);
        // Load the derived startup plan if one was produced.
        const sp = await getStartupPlan(companyId, missionId, result.startup_plan_id);
        setState((s) =>
          s.kind === "ok" ? { ...s, mission: { ...s.mission }, startupPlan: sp } : s,
        );
        setMsg(`Planned — startup plan ${sp.status}.`);
      }
      if (action === "activate") await activateMission(companyId, missionId);
      if (action === "pause") await pauseMission(companyId, missionId);
      if (action === "cancel") await cancelMission(companyId, missionId);
      const mission = await getMission(companyId, missionId);
      setState((s) => (s.kind === "ok" ? { ...s, mission } : s));
      setMsg(`Mission ${action}d.`);
    } catch (err) {
      setMsg(`Action '${action}' failed: ${err instanceof Error ? err.message : "unknown"}`);
    } finally {
      setBusy(null);
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

  const { mission, startupPlan } = state;
  const analysis = mission.analysis as MissionAnalysisResult | null;
  const validation = mission.validation as ValidationResult | null;

  return (
    <div className="space-y-6">
      <Link
        href={href("/startup/missions")}
        className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
      >
        <ArrowLeft className="h-4 w-4" /> Missions
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
              {mission.title}
            </h1>
            <StatusBadge status={mission.status} />
          </div>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            {mission.mission_statement}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <ActionButton onClick={() => runAction("analyze")} busy={busy === "analyze"}>
            Analyze
          </ActionButton>
          <ActionButton onClick={() => runAction("validate")} busy={busy === "validate"}>
            Validate
          </ActionButton>
          <ActionButton onClick={() => runAction("plan")} busy={busy === "plan"}>
            Plan
          </ActionButton>
          <ActionButton onClick={() => runAction("activate")} busy={busy === "activate"}>
            Activate
          </ActionButton>
          <ActionButton onClick={() => runAction("pause")} busy={busy === "pause"}>
            Pause
          </ActionButton>
          <ActionButton onClick={() => runAction("cancel")} busy={busy === "cancel"}>
            Cancel
          </ActionButton>
        </div>
      </div>

      {msg && (
        <p className="rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300">
          {msg}
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Info label="Target market" value={mission.target_market} />
        <Info label="Desired outcome" value={mission.desired_outcome} />
        <Info label="Priority" value={String(mission.priority)} />
        <Info label="Operating cycles" value={String(cycles.length)} />
      </div>

      {startupPlan && (
        <SectionCard
          title="Startup plan"
          action={
            <Link
              href={href(`/startup/plans/${startupPlan.id}`)}
              className="inline-flex items-center gap-1 text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
            >
              <ListChecks className="h-3.5 w-3.5" /> Open plan →
            </Link>
          }
        >
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={startupPlan.status} />
            <span className="text-xs text-zinc-500 dark:text-zinc-400">
              Derived from the mission&apos;s strategy.
            </span>
          </div>
        </SectionCard>
      )}

      <SectionCard title="Analysis">
        {!analysis ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Run <em>Analyze</em> to decompose the mission into objectives, risks,
            capabilities, and success criteria (deterministic by default).
          </p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <Subtitle>Objectives</Subtitle>
              <StringList value={analysis.objectives} />
            </div>
            <div>
              <Subtitle>Required capabilities</Subtitle>
              <StringList value={analysis.required_capabilities} />
            </div>
            <div>
              <Subtitle>Risks</Subtitle>
              <StringList value={analysis.risks} />
            </div>
            <div>
              <Subtitle>Unknowns</Subtitle>
              <StringList value={analysis.unknowns} />
            </div>
            <div>
              <Subtitle>Constraints</Subtitle>
              <StringList value={analysis.constraints} />
            </div>
            <div>
              <Subtitle>Assumptions</Subtitle>
              <StringList value={analysis.assumptions} />
            </div>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Validation">
        {!validation ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Run <em>Validate</em> to check the mission against the
            completeness/safety checklist.
          </p>
        ) : (
          <div className="space-y-3">
            <p className="text-sm">
              Verdict: <StatusBadge status={validation.ok ? "pass" : "fail"} />
            </p>
            {validation.warnings.length > 0 && (
              <IssueList title="Warnings" items={validation.warnings} />
            )}
            {validation.errors.length > 0 && (
              <IssueList title="Errors" items={validation.errors} />
            )}
            {validation.warnings.length === 0 && validation.errors.length === 0 && (
              <p className="text-sm text-zinc-600 dark:text-zinc-400">
                No findings — mission is complete and safe to plan.
              </p>
            )}
          </div>
        )}
      </SectionCard>

      <SectionCard
        title={`Mission graph (${graph?.total ?? 0} edges)`}
        action={
          <Link
            href={href("/startup/mission-graph")}
            className="inline-flex items-center gap-1 text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
          >
            <GitBranch className="h-3.5 w-3.5" /> Full graph →
          </Link>
        }
      >
        {!graph || graph.edges.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No edges yet. The pipeline records provenance edges as it runs.
          </p>
        ) : (
          <ul className="max-h-80 space-y-1 overflow-y-auto">
            {graph.edges.map((e) => (
              <li key={e.id} className="flex items-center gap-2 text-sm">
                <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                  {e.source_type}
                </span>
                <span className="text-zinc-400">{e.relation.replace("_", " ")}</span>
                <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                  {e.target_type}
                </span>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <SectionCard title="Operating cycles">
        {cycles.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No operating cycles yet. Approve + bootstrap the startup plan, then
            run a cycle from the Operations page.
          </p>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {cycles.slice(0, 5).map((c) => (
              <li key={c.id} className="flex items-center justify-between py-2">
                <Link
                  href={href(`/startup/operations/${c.id}`)}
                  className="text-sm font-medium text-zinc-900 hover:underline dark:text-zinc-100"
                >
                  Cycle #{c.cycle_number}
                </Link>
                <StatusBadge status={c.status} />
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}

function Info({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <p className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        {label}
      </p>
      <p className="mt-1 text-sm font-medium text-zinc-900 dark:text-zinc-100">
        <Dash value={String(value)} />
      </p>
    </div>
  );
}

function Subtitle({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
      {children}
    </p>
  );
}

function IssueList({
  title,
  items,
}: {
  title: string;
  items: { code: string; message: string; severity: string }[];
}) {
  return (
    <div>
      <Subtitle>{title}</Subtitle>
      <ul className="space-y-1">
        {items.map((it, i) => (
          <li key={i} className="text-sm text-zinc-700 dark:text-zinc-300">
            [{it.code}] {it.message}
          </li>
        ))}
      </ul>
    </div>
  );
}