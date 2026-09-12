"use client";

import { Fragment, useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { cancelExternalAction, fetchExternalActions } from "@/lib/api";
import type { ExternalAction } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { useExternal } from "../../_components/ExternalShell";
import { ActionButton, Dash, JsonBlock, SectionCard, StatCard } from "../../_components/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; actions: ExternalAction[] }
  | { kind: "error"; message: string };

export default function ExternalActionsPage() {
  const { companyId } = useExternal();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const reload = (company: string) => {
    fetchExternalActions(company)
      .then((actions) => setState({ kind: "ok", actions }))
      .catch((err: unknown) => {
        setState({
          kind: "error",
          message: err instanceof Error ? err.message : "Failed to load external actions",
        });
      });
  };

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    fetchExternalActions(companyId)
      .then((actions) => {
        if (!cancelled) setState({ kind: "ok", actions });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            kind: "error",
            message: err instanceof Error ? err.message : "Failed to load external actions",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  async function cancel(actionId: string) {
    if (!companyId) return;
    setBusy(actionId);
    setMsg(null);
    try {
      await cancelExternalAction(companyId, actionId);
      setMsg("Action cancelled.");
      reload(companyId);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Failed to cancel");
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

  const { actions } = state;
  const byStatus = new Map<string, number>();
  for (const a of actions) byStatus.set(a.status, (byStatus.get(a.status) ?? 0) + 1);
  const pending = actions.filter((a) => a.status === "awaiting_approval").length;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          External action journal
        </h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Immutable, per-company ledger of every external action: risk, policy,
          approval, execution, verification, recovery, and audit outcome.
        </p>
      </div>

      {msg && (
        <p className="rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300">
          {msg}
        </p>
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Total actions" value={actions.length} />
        <StatCard label="Awaiting approval" value={pending} hint="gates require a human" />
        <StatCard
          label="Succeeded"
          value={byStatus.get("succeeded") ?? 0}
        />
        <StatCard label="Failed / blocked" value={(byStatus.get("failed") ?? 0) + (byStatus.get("blocked") ?? 0)} />
      </div>

      <SectionCard title={`Journal (${actions.length})`}>
        {actions.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No external actions yet. The journal records every governed
            capability call for this company.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-zinc-200 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
                <tr>
                  <th className="px-2 py-2"></th>
                  <th className="px-2 py-2">Capability</th>
                  <th className="px-2 py-2">Risk</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">Approval</th>
                  <th className="px-2 py-2">Reversibility</th>
                  <th className="px-2 py-2">Attempts</th>
                  <th className="px-2 py-2">Created</th>
                  <th className="px-2 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {actions.map((a) => {
                  const open = expanded === a.id;
                  return (
                    <Fragment key={a.id}>
                      <tr
                        onClick={() => setExpanded(open ? null : a.id)}
                        className="cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-900/40"
                      >
                        <td className="px-2 py-2.5">
                          {open ? (
                            <ChevronDown className="h-4 w-4 text-zinc-400" />
                          ) : (
                            <ChevronRight className="h-4 w-4 text-zinc-400" />
                          )}
                        </td>
                        <td className="px-2 py-2.5 font-mono text-zinc-900 dark:text-zinc-100">
                          {a.capability}
                        </td>
                        <td className="px-2 py-2.5">
                          <StatusBadge status={a.risk_level} />
                        </td>
                        <td className="px-2 py-2.5">
                          <StatusBadge status={a.status as never} />
                        </td>
                        <td className="px-2 py-2.5">
                          {a.approval_status ? (
                            <StatusBadge status={a.approval_status as never} />
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="px-2 py-2.5 text-zinc-600 dark:text-zinc-400">
                          {a.reversibility.replace("_", " ")}
                        </td>
                        <td className="px-2 py-2.5 text-zinc-600 dark:text-zinc-400">
                          {a.attempts.length}
                        </td>
                        <td className="px-2 py-2.5 text-zinc-500">
                          {a.created_at ? new Date(a.created_at).toLocaleString() : "—"}
                        </td>
                        <td className="px-2 py-2.5 text-right">
                          {a.status === "awaiting_approval" ? (
                            <span onClick={(e) => e.stopPropagation()}>
                              <ActionButton onClick={() => cancel(a.id)} busy={busy === a.id}>
                                Cancel
                              </ActionButton>
                            </span>
                          ) : null}
                        </td>
                      </tr>
                      {open && (
                        <tr className="bg-zinc-50 dark:bg-zinc-900/40">
                          <td colSpan={9} className="px-4 py-4">
                            <ActionTimeline a={a} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </div>
  );
}

/** Expandable timeline for one journal row (§52). */
function ActionTimeline({ a }: { a: ExternalAction }) {
  const steps: { label: string; value?: unknown; error?: string | null }[] = [
    { label: "Requested", value: a.created_at },
    { label: "Risk", value: `${a.risk_level} · ${a.reversibility}` },
    {
      label: "Policy",
      value: a.policy_result ?? undefined,
    },
    {
      label: "Approval",
      value: a.approval_status ? `${a.approval_status}${a.approval_gate_id ? ` (gate ${a.approval_gate_id})` : ""}` : "not required",
    },
    { label: "Result", value: a.status === "succeeded" ? a.result : undefined },
    { label: "Verification", value: a.verification ?? undefined },
    { label: "Recovery", value: a.recovery ?? undefined },
    { label: "Error", error: a.error },
  ];

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Timeline
        </p>
        <ol className="relative space-y-3 border-l border-zinc-200 pl-4 dark:border-zinc-700">
          {steps.map((s) => (
            <li key={s.label}>
              <span className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                {s.label}
              </span>
              <div className="text-sm text-zinc-800 dark:text-zinc-200">
                {s.error !== undefined ? (
                  s.error ? (
                    <span className="text-red-600 dark:text-red-400">{s.error}</span>
                  ) : (
                    <Dash value={null} />
                  )
                ) : s.value !== undefined && s.value !== null ? (
                  typeof s.value === "string" ? (
                    s.value.length > 160 ? (
                      <span title={s.value}>{s.value.slice(0, 160)}…</span>
                    ) : (
                      s.value
                    )
                  ) : (
                    <JsonBlock value={s.value} />
                  )
                ) : (
                  <Dash value={null} />
                )}
              </div>
            </li>
          ))}
        </ol>
      </div>

      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Input
        </p>
        <JsonBlock value={a.input} />
        {a.attempts.length > 0 && (
          <>
            <p className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Attempts
            </p>
            <div className="space-y-2">
              {a.attempts.map((t) => (
                <div
                  key={t.id}
                  className="rounded-md border border-zinc-200 p-2 text-xs dark:border-zinc-800"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-zinc-800 dark:text-zinc-200">
                      attempt #{t.attempt_number}
                    </span>
                    <StatusBadge status={t.status as never} />
                    {t.strategy && <span className="text-zinc-500">{t.strategy}</span>}
                    {t.duration_ms != null && (
                      <span className="text-zinc-500">{t.duration_ms}ms</span>
                    )}
                  </div>
                  {t.error && <p className="mt-1 text-red-600 dark:text-red-400">{t.error}</p>}
                  {t.error_category && (
                    <p className="mt-0.5 text-zinc-500">category: {t.error_category}</p>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}