"use client";

import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import {
  approveApprovalGate,
  fetchApprovalGates,
  fetchAutonomyPolicy,
  rejectApprovalGate,
} from "@/lib/api";
import type { ApprovalGate, AutonomyPolicy } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { useStartup } from "../_components/StartupShell";
import { ActionButton, Dash, SectionCard } from "../_components/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; gates: ApprovalGate[]; policy: AutonomyPolicy | null }
  | { kind: "error"; message: string };

export default function ApprovalsPage() {
  const { companyId } = useStartup();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    Promise.all([
      fetchApprovalGates(companyId),
      fetchAutonomyPolicy(companyId).catch(() => null),
    ])
      .then(([gates, policy]) => {
        if (!cancelled) setState({ kind: "ok", gates, policy });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            kind: "error",
            message: err instanceof Error ? err.message : "Failed to load approvals",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  async function decide(gateId: string, action: "approve" | "reject") {
    if (!companyId) return;
    setBusy(gateId);
    setMsg(null);
    try {
      if (action === "approve") await approveApprovalGate(companyId, gateId);
      if (action === "reject") await rejectApprovalGate(companyId, gateId);
      setMsg(`Gate ${action}d.`);
      const gates = await fetchApprovalGates(companyId);
      setState((s) => (s.kind === "ok" ? { ...s, gates } : s));
    } catch (err) {
      setMsg(err instanceof Error ? err.message : `Failed to ${action} gate`);
    } finally {
      setBusy(null);
    }
  }

  if (!companyId) return null;
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

  const { gates, policy } = state;
  const pending = gates.filter((g) => g.status === "pending");

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          Approvals & governance
        </h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Every action that exceeds the company&apos;s autonomy level parks at an
          approval gate. Approving a gate authorizes exactly one governed
          action — it never widens future autonomy.
        </p>
      </div>

      {msg && (
        <p className="rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300">
          {msg}
        </p>
      )}

      {policy && (
        <SectionCard title="Autonomy policy">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-xs uppercase tracking-wide text-zinc-500">
                Level
              </span>
              <StatusBadge status={policy.autonomy_level} />
            </div>
            <PolicyStat label="Max employees" value={policy.max_employees} />
            <PolicyStat label="Max departments" value={policy.max_departments} />
            <PolicyStat label="Max budget" value={policy.max_budget} />
            <PolicyStat label="Max concurrent work" value={policy.max_concurrent_work} />
          </div>
          {Object.keys(policy.allow_matrix).length > 0 && (
            <div className="mt-4">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                Per-action decisions
              </p>
              <ul className="max-h-64 space-y-1 overflow-y-auto">
                {Object.entries(policy.allow_matrix).map(([action, decision]) => (
                  <li
                    key={action}
                    className="flex items-center justify-between text-sm"
                  >
                    <span className="text-zinc-700 dark:text-zinc-300">
                      {action.replace("_", " ")}
                    </span>
                    <StatusBadge
                      status={
                        decision === "allow"
                          ? "approved"
                          : decision === "block"
                            ? "rejected"
                            : "pending"
                      }
                    />
                  </li>
                ))}
              </ul>
            </div>
          )}
          {policy.never_allowed.length > 0 && (
            <div className="mt-4">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                Never autonomous
              </p>
              <div className="flex flex-wrap gap-1">
                {policy.never_allowed.map((action) => (
                  <span
                    key={action}
                    className="rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-xs text-red-700 dark:border-red-900 dark:bg-red-950/50 dark:text-red-300"
                  >
                    {action.replace("_", " ")}
                  </span>
                ))}
              </div>
            </div>
          )}
        </SectionCard>
      )}

      <SectionCard title={`Approval gates (${pending.length} pending)`}>
        {gates.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No approval gates yet. Gates are created when an autonomous action
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
                      {g.created_at ? new Date(g.created_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {g.status === "pending" ? (
                        <div className="flex justify-end gap-2">
                          <ActionButton
                            onClick={() => decide(g.id, "approve")}
                            busy={busy === g.id}
                          >
                            Approve
                          </ActionButton>
                          <ActionButton
                            onClick={() => decide(g.id, "reject")}
                            busy={busy === g.id}
                          >
                            Reject
                          </ActionButton>
                        </div>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-xs text-zinc-400">
                          <ShieldCheck className="h-3.5 w-3.5" />
                          {g.decided_at ? new Date(g.decided_at).toLocaleDateString() : "decided"}
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

function PolicyStat({ label, value }: { label: string; value: number | null }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        {label}
      </p>
      <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
        {value ?? "—"}
      </p>
    </div>
  );
}