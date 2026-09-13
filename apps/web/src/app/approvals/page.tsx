"use client";

/**
 * Approvals Center — every governed proposal waiting for a human decision,
 * aggregated across the autonomy (Phase 9) and optimization (Phase 12)
 * surfaces. Approving authorizes exactly one governed action; it never widens
 * future autonomy. (Final-pass §16/§44 — replaces the former placeholder.)
 */

import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import {
  approveApprovalGate,
  approveRecommendation,
  fetchApprovalGates,
  fetchRecommendations,
  rejectApprovalGate,
  rejectRecommendation,
} from "@/lib/api";
import type { ApprovalGate, RecommendationPublic } from "@/lib/types";
import { StatusBadge, type BadgeStatus } from "@/components/StatusBadge";

/** Map a recommendation lifecycle status onto a badge colour. */
function recommendationBadge(status: string | undefined | null): BadgeStatus {
  const map: Record<string, BadgeStatus> = {
    pending: "pending",
    approved: "approved",
    rejected: "rejected",
    applied: "applied",
  };
  return map[status?.toLowerCase() ?? ""] ?? "unknown";
}
import { Dash, SectionCard } from "@/components/phase12/ui";
import { useCompanyScope } from "@/lib/useCompanyScope";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; gates: ApprovalGate[]; recommendations: RecommendationPublic[] }
  | { kind: "error"; message: string };

export default function ApprovalsPage() {
  const { companyId, companies, setCompanyId, loaded } = useCompanyScope(
    "nexus.approvals.companyId",
  );
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    Promise.all([
      fetchApprovalGates(companyId),
      fetchRecommendations({ companyId }),
    ])
      .then(([gates, recommendations]) => {
        if (!cancelled) setState({ kind: "ok", gates, recommendations });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            kind: "error",
            message:
              err instanceof Error
                ? err.message
                : "Failed to load approvals",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  async function refresh() {
    if (!companyId) return;
    const [gates, recommendations] = await Promise.all([
      fetchApprovalGates(companyId),
      fetchRecommendations({ companyId }),
    ]);
    setState({ kind: "ok", gates, recommendations });
  }

  async function decideGate(gateId: string, action: "approve" | "reject") {
    if (!companyId) return;
    setBusy(gateId);
    setMsg(null);
    try {
      if (action === "approve") await approveApprovalGate(companyId, gateId);
      if (action === "reject") await rejectApprovalGate(companyId, gateId);
      setMsg(`Autonomy gate ${action}d.`);
      await refresh();
    } catch (err) {
      setMsg(
        err instanceof Error ? err.message : `Failed to ${action} gate`,
      );
    } finally {
      setBusy(null);
    }
  }

  async function decideRecommendation(
    id: string,
    action: "approve" | "reject",
  ) {
    setBusy(id);
    setMsg(null);
    try {
      if (action === "approve") await approveRecommendation(id);
      if (action === "reject")
        await rejectRecommendation(id, { reason: "Rejected in Approvals Center" });
      setMsg(`Optimization recommendation ${action}d.`);
      await refresh();
    } catch (err) {
      setMsg(
        err instanceof Error
          ? err.message
          : `Failed to ${action} recommendation`,
      );
    } finally {
      setBusy(null);
    }
  }

  if (!loaded) {
    return (
      <div className="h-64 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
    );
  }
  if (!companyId) {
    return (
      <p className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300">
        No company available yet — create a company first.
      </p>
    );
  }
  if (state.kind === "loading") {
    return (
      <div className="h-64 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
    );
  }
  if (state.kind === "error") {
    return (
      <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
        {state.message}
      </p>
    );
  }

  const { gates, recommendations } = state;
  const pendingGates = gates.filter((g) => g.status === "pending");
  const pendingRecs = recommendations.filter(
    (r) => r.status?.toLowerCase() === "pending",
  );
  const pendingTotal = pendingGates.length + pendingRecs.length;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          Approvals
        </h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Every governed proposal awaiting a human decision —
          {pendingTotal} pending across autonomy gates and optimization
          recommendations. Approving authorizes exactly one action; it never
          widens future autonomy.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
          Company
        </label>
        <select
          value={companyId ?? ""}
          onChange={(e) => setCompanyId(e.target.value)}
          className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
        >
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      {msg && (
        <p className="rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300">
          {msg}
        </p>
      )}

      <SectionCard title={`Autonomy approval gates (${pendingGates.length} pending)`}>
        {gates.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No autonomy gates yet. Gates are created when an autonomous action
            requires human authorization.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-zinc-200 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
                <tr>
                  <th className="px-3 py-2">Gate</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Risk</th>
                  <th className="px-3 py-2">Rationale</th>
                  <th className="px-3 py-2">Created</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {gates.map((g) => (
                  <tr key={g.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-900/40">
                    <td className="px-3 py-2.5">
                      <StatusBadge status={g.gate_type} />
                    </td>
                    <td className="px-3 py-2.5">
                      <StatusBadge status={g.status} />
                    </td>
                    <td className="px-3 py-2.5 text-zinc-600 dark:text-zinc-400">
                      {g.risk_level}
                    </td>
                    <td className="max-w-xs px-3 py-2.5">
                      <Dash value={g.rationale} />
                    </td>
                    <td className="px-3 py-2.5 text-zinc-600 dark:text-zinc-400">
                      {g.created_at
                        ? new Date(g.created_at).toLocaleDateString()
                        : "—"}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {g.status === "pending" ? (
                        <div className="flex justify-end gap-2">
                          <button
                            onClick={() => decideGate(g.id, "approve")}
                            disabled={busy === g.id}
                            className="rounded-md border border-emerald-300 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-50 disabled:opacity-50 dark:border-emerald-900 dark:text-emerald-300 dark:hover:bg-emerald-950/40"
                          >
                            {busy === g.id ? "Working…" : "Approve"}
                          </button>
                          <button
                            onClick={() => decideGate(g.id, "reject")}
                            disabled={busy === g.id}
                            className="rounded-md border border-red-300 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/40"
                          >
                            Reject
                          </button>
                        </div>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-xs text-zinc-400">
                          <ShieldCheck className="h-3.5 w-3.5" />
                          {g.decided_at
                            ? new Date(g.decided_at).toLocaleDateString()
                            : "decided"}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      <SectionCard
        title={`Optimization recommendations (${pendingRecs.length} pending)`}
      >
        {recommendations.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No optimization recommendations yet. The optimization engine
            produces explainable recommendations that require explicit approval
            before any execution — RECOMMENDATION, never a completed action.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-zinc-200 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
                <tr>
                  <th className="px-3 py-2">Recommendation</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Created</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {recommendations.map((r) => (
                  <tr key={r.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-900/40">
                    <td className="max-w-md px-3 py-2.5">
                      <span className="font-medium text-zinc-900 dark:text-zinc-100">
                        {r.title}
                      </span>
                      <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] uppercase tracking-wide text-amber-700 dark:bg-amber-950 dark:text-amber-300">
                        RECOMMENDATION
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <StatusBadge status={recommendationBadge(r.status)} />
                    </td>
                    <td className="px-3 py-2.5 text-zinc-600 dark:text-zinc-400">
                      {new Date(r.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {r.status?.toLowerCase() === "pending" ? (
                        <div className="flex justify-end gap-2">
                          <button
                            onClick={() => decideRecommendation(r.id, "approve")}
                            disabled={busy === r.id}
                            className="rounded-md border border-emerald-300 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-50 disabled:opacity-50 dark:border-emerald-900 dark:text-emerald-300 dark:hover:bg-emerald-950/40"
                          >
                            {busy === r.id ? "Working…" : "Approve"}
                          </button>
                          <button
                            onClick={() => decideRecommendation(r.id, "reject")}
                            disabled={busy === r.id}
                            className="rounded-md border border-red-300 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/40"
                          >
                            Reject
                          </button>
                        </div>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-xs text-zinc-400">
                          <ShieldCheck className="h-3.5 w-3.5" />
                          {r.approved_at ?? "decided"}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </div>
  );
}