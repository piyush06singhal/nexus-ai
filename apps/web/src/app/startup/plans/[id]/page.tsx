"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, ListChecks } from "lucide-react";
import {
  approveStartupPlan,
  bootstrapStartupPlan,
  executeStartupPlan,
  getStartupPlan,
  validateStartupPlan,
} from "@/lib/api";
import type { OperatingCycle, StartupPlan, ValidationResult } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { useStartup } from "../../_components/StartupShell";
import { ActionButton, Dash, SectionCard, StringList } from "../../_components/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "missing-mission" }
  | { kind: "ok"; plan: StartupPlan; validation: ValidationResult | null; cycle: OperatingCycle | null }
  | { kind: "error"; message: string };

export default function PlanDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { href, companyId, missionForPlan } = useStartup();
  const [planId, setPlanId] = useState("");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    params.then((p) => setPlanId(p.id));
  }, [params]);

  // The plans router scopes all reads by mission_id; the parent mission detail
  // records that mapping (plan → mission) when it links a plan. Resolve the
  // mission here and fetch through the mission-scoped endpoint.
  useEffect(() => {
    if (!planId) return;
    let cancelled = false;
    if (!companyId) return;
    const mId = missionForPlan(planId);
    if (!mId) {
      Promise.resolve().then(() => {
        if (!cancelled) setState({ kind: "missing-mission" });
      });
      return () => {
        cancelled = true;
      };
    }
    getStartupPlan(companyId, mId, planId)
      .then((plan) => {
        if (!cancelled) setState({ kind: "ok", plan, validation: null, cycle: null });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ kind: "error", message: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, [planId, companyId, missionForPlan]);

  if (state.kind === "missing-mission") {
    return (
      <div className="space-y-6">
        <Link
          href={href("/startup/missions")}
          className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
        >
          <ArrowLeft className="h-4 w-4" /> Missions
        </Link>
        <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-4 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300">
          <p className="font-medium">This plan needs a mission context.</p>
          <p className="mt-1">
            Startup plans are company/mission-scoped. Open the parent mission to
            view and approve its plan.
          </p>
        </div>
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

  const { plan } = state;

  return (
    <div className="space-y-6">
      <Link
        href={href("/startup/missions")}
        className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
      >
        <ArrowLeft className="h-4 w-4" /> Missions
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
              Startup plan
            </h1>
            <StatusBadge status={plan.status} />
          </div>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Mission plan for {plan.mission_id}. Approve then bootstrap to
            stand up the operating company.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <ActionButton onClick={() => run("validate")} busy={busy === "validate"}>
            Validate
          </ActionButton>
          <ActionButton onClick={() => run("approve")} busy={busy === "approve"}>
            Approve
          </ActionButton>
          <ActionButton onClick={() => run("bootstrap")} busy={busy === "bootstrap"}>
            Bootstrap
          </ActionButton>
          <ActionButton onClick={() => run("execute")} busy={busy === "execute"}>
            Run cycle
          </ActionButton>
        </div>
      </div>

      {msg && (
        <p className="rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300">
          {msg}
        </p>
      )}

      {state.validation && (
        <SectionCard title="Validation">
          <div className="space-y-2">
            <p className="text-sm">
              Verdict: <StatusBadge status={state.validation.ok ? "pass" : "fail"} />
            </p>
            {state.validation.errors.map((e, i) => (
              <p key={i} className="text-sm text-red-700 dark:text-red-400">
                [{e.code}] {e.message}
              </p>
            ))}
            {state.validation.warnings.map((w, i) => (
              <p key={i} className="text-sm text-amber-700 dark:text-amber-400">
                [{w.code}] {w.message}
              </p>
            ))}
          </div>
        </SectionCard>
      )}

      {state.cycle && (
        <SectionCard
          title="Latest operating cycle"
          action={
            <Link
              href={href(`/startup/operations/${state.cycle.id}`)}
              className="text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
            >
              Open →
            </Link>
          }
        >
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
              Cycle #{state.cycle.cycle_number}
            </span>
            <StatusBadge status={state.cycle.status} />
          </div>
        </SectionCard>
      )}

      <PlanSections plan={plan} />
    </div>
  );

  async function run(
    action: "validate" | "approve" | "bootstrap" | "execute",
  ) {
    const missionId = plan.mission_id;
    if (!missionId || !companyId) return;
    setBusy(action);
    setMsg(null);
    try {
      if (action === "validate") {
        const v = await validateStartupPlan(companyId, missionId, plan.id);
        setState((s) => (s.kind === "ok" ? { ...s, validation: v } : s));
      }
      if (action === "approve") {
        const p = await approveStartupPlan(companyId, missionId, plan.id);
        setState((s) => (s.kind === "ok" ? { ...s, plan: p } : s));
        setMsg("Plan approved.");
      }
      if (action === "bootstrap") {
        const summary = await bootstrapStartupPlan(companyId, missionId, plan.id);
        const p = await getStartupPlan(companyId, missionId, plan.id);
        setState((s) => (s.kind === "ok" ? { ...s, plan: p } : s));
        setMsg(
          `Company bootstrapped: ${(summary.employees as unknown[])?.length ?? 0} employees, ` +
            `${(summary.departments as unknown[])?.length ?? 0} departments.`,
        );
      }
      if (action === "execute") {
        const c = await executeStartupPlan(companyId, missionId, plan.id);
        setState((s) => (s.kind === "ok" ? { ...s, cycle: c } : s));
        setMsg(`Operating cycle #${c.cycle_number} → ${c.status}.`);
      }
    } catch (err) {
      setMsg(
        `Action '${action}' failed: ${err instanceof Error ? err.message : "unknown"}`,
      );
    } finally {
      setBusy(null);
    }
  }
}

function PlanSections({ plan }: { plan: StartupPlan }) {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <SectionCard title="Business objectives">
        <StringList value={plan.business_objectives} />
      </SectionCard>
      <SectionCard title="Product objectives">
        <StringList value={plan.product_objectives} />
      </SectionCard>
      <SectionCard title="Market objectives">
        <StringList value={plan.market_objectives} />
      </SectionCard>
      <SectionCard title="Organization objectives">
        <StringList value={plan.organization_objectives} />
      </SectionCard>

      <SectionCard title="Departments">
        {Array.isArray(plan.departments) && plan.departments.length > 0 ? (
          <ul className="space-y-2">
            {plan.departments.map((d, i) => {
              const dept = d as Record<string, unknown>;
              const roles = (dept.roles as Record<string, unknown>[]) ?? [];
              return (
                <li key={i} className="text-sm">
                  <span className="font-medium text-zinc-900 dark:text-zinc-100">
                    {String(dept.name)}
                  </span>
                  <span className="ml-2 text-xs text-zinc-500">
                    {roles.length} roles
                  </span>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {String(dept.mission ?? "")}
                  </p>
                </li>
              );
            })}
          </ul>
        ) : (
          <Dash value={null} />
        )}
      </SectionCard>

      <SectionCard title="Initial products">
        {Array.isArray(plan.initial_products) && plan.initial_products.length > 0 ? (
          <ul className="space-y-2">
            {plan.initial_products.map((raw, i) => {
              const p = raw as Record<string, unknown>;
              return (
                <li key={i} className="text-sm">
                  <span className="font-medium text-zinc-900 dark:text-zinc-100">
                    {String(p.name)}
                  </span>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {String(p.description ?? "")}
                  </p>
                </li>
              );
            })}
          </ul>
        ) : (
          <Dash value={null} />
        )}
      </SectionCard>

      <SectionCard title="Initial projects">
        {Array.isArray(plan.initial_projects) && plan.initial_projects.length > 0 ? (
          <ul className="space-y-1">
            {plan.initial_projects.map((raw, i) => (
              <li
                key={i}
                className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300"
              >
                <ListChecks className="h-3.5 w-3.5 text-zinc-400" />
                {String((raw as Record<string, unknown>).name ?? "")}
              </li>
            ))}
          </ul>
        ) : (
          <Dash value={null} />
        )}
      </SectionCard>

      <SectionCard title="KPI targets">
        {plan.kpi_targets &&
        typeof plan.kpi_targets === "object" &&
        Object.keys(plan.kpi_targets as object).length > 0 ? (
          <ul className="space-y-1">
            {Object.entries(plan.kpi_targets as Record<string, unknown>).map(
              ([k, v]) => (
                <li
                  key={k}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="text-zinc-700 dark:text-zinc-300">
                    {k.replace("_", " ")}
                  </span>
                  <span className="font-medium text-zinc-900 dark:text-zinc-100">
                    {String(v)}
                  </span>
                </li>
              ),
            )}
          </ul>
        ) : (
          <Dash value={null} />
        )}
      </SectionCard>
    </div>
  );
}