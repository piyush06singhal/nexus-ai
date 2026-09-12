"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Rocket } from "lucide-react";
import {
  fetchCycles,
  fetchFeedback,
  fetchMissions,
  fetchNextActions,
  fetchProducts,
  fetchStartupProjects,
} from "@/lib/api";
import type {
  CompanyStateSnapshot,
  Mission,
  MissionGraph,
  OperatingCycle,
  Product,
  StartupFeedback,
  StartupProject,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { useStartup } from "./_components/StartupShell";
import { SectionCard, StatCard } from "./_components/ui";

type LoadState =
  | { kind: "loading" }
  | {
      kind: "ok";
      state: CompanyStateSnapshot | null;
      missions: Mission[];
      products: Product[];
      projects: StartupProject[];
      cycles: OperatingCycle[];
      feedback: StartupFeedback[];
      graph: MissionGraph | null;
      pendingApprovals: number;
      needsAttention: boolean;
    }
  | { kind: "error"; message: string };

export default function StartupOverviewPage() {
  const { companyId, href } = useStartup();
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    Promise.all([
      fetchMissions(companyId),
      fetchProducts(companyId),
      fetchStartupProjects(companyId),
      fetchCycles(companyId, 5),
      fetchFeedback(companyId, undefined, 5),
    ])
      .then(async ([missions, products, projects, cycles, feedback]) => {
        let next: Awaited<ReturnType<typeof fetchNextActions>> | null = null;
        try {
          next = await fetchNextActions(companyId);
        } catch {
          /* next-actions is best-effort on partial setups */
        }
        if (!cancelled) {
          setState({
            kind: "ok",
            state: next ? next.state : null,
            missions,
            products,
            projects,
            cycles,
            feedback,
            graph: null,
            pendingApprovals: next?.pending_approval_count ?? 0,
            needsAttention: next?.needs_attention ?? false,
          });
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            kind: "error",
            message: err instanceof Error ? err.message : "Failed to load startup",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  if (!companyId) {
    return (
      <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
        <Rocket className="mx-auto h-8 w-8 text-zinc-400" />
        <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
          Select a company above (or create one under{" "}
          <Link href="/companies" className="font-medium underline">
            Companies
          </Link>
          ) to drive its autonomous startup engine.
        </p>
      </div>
    );
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

  const s = state;
  const latestCycle = s.cycles[0] ?? null;

  return (
    <div className="space-y-6">
      {s.needsAttention && (
        <div className="flex items-center justify-between rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 dark:border-amber-900 dark:bg-amber-950/30">
          <p className="text-sm text-amber-800 dark:text-amber-300">
            {s.pendingApprovals} approval gate
            {s.pendingApprovals === 1 ? "" : "s"} awaiting a decision.
          </p>
          <Link
            href={href("/startup/approvals")}
            className="inline-flex items-center gap-1 text-sm font-medium text-amber-800 underline dark:text-amber-300"
          >
            Review approvals <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Missions" value={s.missions.length} hint="mission graph roots" />
        <StatCard
          label="Overall score"
          value={
            s.state ? `${Math.round(s.state.overall_score * 100)}%` : "—"
          }
          hint={
            s.state ? `top dimension: ${topDimension(s.state)}` : "no snapshot yet"
          }
        />
        <StatCard label="Active products" value={s.products.filter((p) => p.status === "launched" || p.status === "building" || p.status === "measuring" || p.status === "iterating").length} />
        <StatCard
          label="Recent recovery"
          value={
            latestCycle && latestCycle.recovery.length > 0
              ? latestCycle.recovery[0].outcome === "recovered"
                ? "Recovered"
                : "Failed"
              : "None"
          }
        />
      </div>

      {latestCycle && (
        <SectionCard
          title={`Latest operating cycle #${latestCycle.cycle_number}`}
          action={
            <Link href={href(`/startup/operations/${latestCycle.id}`)} className="inline-flex items-center gap-1 text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
              Open <ArrowRight className="h-3 w-3" />
            </Link>
          }
        >
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={latestCycle.status} />
            <span className="text-xs text-zinc-500 dark:text-zinc-400">
              {latestCycle.stages.length} stages · started{" "}
              {latestCycle.started_at
                ? new Date(latestCycle.started_at).toLocaleString()
                : "—"}
            </span>
          </div>
          {latestCycle.failures.length > 0 && (
            <p className="mt-2 text-sm text-amber-700 dark:text-amber-300">
              {latestCycle.failures.length} failure
              {latestCycle.failures.length === 1 ? "" : "s"} this cycle
              {latestCycle.recovery.length > 0 ? " · recovered automatically" : ""}.
            </p>
          )}
        </SectionCard>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard
          title="Missions"
          action={
            <Link href={href("/startup/missions")} className="inline-flex items-center gap-1 text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
              All missions <ArrowRight className="h-3 w-3" />
            </Link>
          }
        >
          {s.missions.length === 0 ? (
            <Empty text="No missions yet. Create one to start the mission pipeline." />
          ) : (
            <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {s.missions.slice(0, 4).map((m) => (
                <li key={m.id} className="flex items-center justify-between py-2.5">
                  <div className="min-w-0">
                    <Link
                      href={href(`/startup/missions/${m.id}`)}
                      className="truncate text-sm font-medium text-zinc-900 hover:underline dark:text-zinc-100"
                    >
                      {m.title}
                    </Link>
                    <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">
                      {m.mission_statement}
                    </p>
                  </div>
                  <StatusBadge status={m.status} />
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        <SectionCard
          title="Products"
          action={
            <Link href={href("/startup/products")} className="inline-flex items-center gap-1 text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
              All products <ArrowRight className="h-3 w-3" />
            </Link>
          }
        >
          {s.products.length === 0 ? (
            <Empty text="No products yet. They are seeded when a startup plan is bootstrapped." />
          ) : (
            <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {s.products.slice(0, 4).map((p) => (
                <li key={p.id} className="flex items-center justify-between py-2.5">
                  <Link
                    href={href(`/startup/products/${p.id}`)}
                    className="text-sm font-medium text-zinc-900 hover:underline dark:text-zinc-100"
                  >
                    {p.name}
                  </Link>
                  <StatusBadge status={p.status} />
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        <SectionCard
          title="Projects"
          action={
            <Link href={href("/startup/projects")} className="inline-flex items-center gap-1 text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
              All projects <ArrowRight className="h-3 w-3" />
            </Link>
          }
        >
          {s.projects.length === 0 ? (
            <Empty text="No startup projects yet." />
          ) : (
            <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {s.projects.slice(0, 4).map((p) => (
                <li key={p.id} className="flex items-center justify-between py-2.5">
                  <Link
                    href={href(`/startup/projects/${p.id}`)}
                    className="text-sm font-medium text-zinc-900 hover:underline dark:text-zinc-100"
                  >
                    {p.name}
                  </Link>
                  <StatusBadge status={p.status} />
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        <SectionCard
          title="Latest feedback"
          action={
            <Link href={href("/startup/feedback")} className="inline-flex items-center gap-1 text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
              All feedback <ArrowRight className="h-3 w-3" />
            </Link>
          }
        >
          {s.feedback.length === 0 ? (
            <Empty text="Feedback is recorded once operating cycles run." />
          ) : (
            <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {s.feedback.slice(0, 4).map((f) => (
                <li key={f.id} className="py-2.5">
                  <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                    {f.category}
                  </p>
                  <p className="mt-0.5 line-clamp-2 text-xs text-zinc-600 dark:text-zinc-400">
                    {f.observation}
                  </p>
                  <p className="mt-1 text-xs text-zinc-500">
                    confidence {Math.round(f.confidence * 100)}%
                  </p>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>
    </div>
  );
}

function topDimension(state: CompanyStateSnapshot): string {
  const entries = Object.entries(state.dimensions);
  if (entries.length === 0) return "—";
  const [name, score] = entries.sort((a, b) => b[1] - a[1])[0];
  return `${name.replace("_", " ")} (${Math.round(score * 100)}%)`;
}

function Empty({ text }: { text: string }) {
  return (
    <p className="text-sm text-zinc-500 dark:text-zinc-400">{text}</p>
  );
}