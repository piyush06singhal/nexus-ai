"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, BellRing, RefreshCw } from "lucide-react";
import { acknowledgeAlert, checkCompanyAlerts, fetchCompanyAlerts, resolveAlert } from "@/lib/api";
import type { Alert } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; alerts: Alert[] }
  | { kind: "error"; message: string };

const SEV_ORDER: Record<string, number> = { critical: 0, warning: 1, informational: 2 };

export default function CompanyAlertsPage({ params }: { params: Promise<{ id: string }> }) {
  const [companyId, setCompanyId] = useState<string>("");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [severityFilter, setSeverityFilter] = useState<string>("");
  const [flash, setFlash] = useState<string | null>(null);

  useEffect(() => {
    params.then((p) => setCompanyId(p.id));
  }, [params]);

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    fetchCompanyAlerts(companyId, severityFilter || undefined)
      .then((alerts) => {
        if (!cancelled) {
          setState({
            kind: "ok",
            alerts: [...alerts].sort((a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9)),
          });
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ kind: "error", message: err.message });
      });
    return () => { cancelled = true; };
  }, [companyId, severityFilter]);

  function reload() {
    if (!companyId) return;
    setState({ kind: "loading" });
    fetchCompanyAlerts(companyId, severityFilter || undefined)
      .then((alerts) => {
        setState({
          kind: "ok",
          alerts: [...alerts].sort((a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9)),
        });
      })
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }

  async function handleCheck() {
    setFlash(null);
    const res = await checkCompanyAlerts(companyId);
    setFlash(`Alert check generated ${res.generated} new alert${res.generated === 1 ? "" : "s"}.`);
    reload();
  }

  async function handleAck(id: string) {
    await acknowledgeAlert(id);
    reload();
  }

  async function handleResolve(id: string) {
    await resolveAlert(id);
    reload();
  }

  return (
    <div className="space-y-6">
      <Link href={`/companies/${companyId}`} className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
        <ArrowLeft className="h-4 w-4" /> Company
      </Link>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">Alert Center</h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Threshold-based alerts for budget, reliability, and goal-at-risk violations.
          </p>
        </div>
        <button
          onClick={handleCheck}
          className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          <RefreshCw className="h-4 w-4" />
          Run checks
        </button>
      </div>

      {flash && <p className="text-sm text-zinc-600 dark:text-zinc-400">{flash}</p>}

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{state.message}</p>
      )}

      {state.kind === "ok" && state.alerts.length > 0 && (
        <div className="flex flex-wrap gap-3">
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          >
            <option value="">All severities</option>
            <option value="critical">Critical</option>
            <option value="warning">Warning</option>
            <option value="informational">Informational</option>
          </select>
        </div>
      )}

      {state.kind === "loading" && <div className="h-48 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />}

      {state.kind === "ok" && state.alerts.length === 0 && !severityFilter && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <BellRing className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            No alerts. Run threshold checks to detect budget, reliability, and goal violations.
          </p>
        </div>
      )}

      {state.kind === "ok" && state.alerts.length === 0 && severityFilter && (
        <p className="text-sm text-zinc-500">No alerts at this severity.</p>
      )}

      {state.kind === "ok" && state.alerts.length > 0 && (
        <div className="space-y-2">
          {state.alerts.map((a) => (
            <div key={a.id} className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-start gap-3">
                  <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${a.severity === "critical" ? "bg-red-500" : a.severity === "warning" ? "bg-amber-500" : "bg-sky-500"}`} />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{a.title}</p>
                    <p className="mt-0.5 text-xs text-zinc-500">{a.category} · scope {a.scope_type}</p>
                    <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{a.message}</p>
                    {a.created_at && <p className="mt-1 text-xs text-zinc-400">{fmtDate(a.created_at)}</p>}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <StatusBadge status={a.severity} />
                  <StatusBadge status={a.status} />
                  {a.status === "active" && (
                    <button
                      onClick={() => handleAck(a.id)}
                      className="rounded-md border border-zinc-300 px-2 py-1 text-[11px] text-zinc-600 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
                    >
                      Acknowledge
                    </button>
                  )}
                  {(a.status === "active" || a.status === "acknowledged") && (
                    <button
                      onClick={() => handleResolve(a.id)}
                      className="rounded-md border border-emerald-300 px-2 py-1 text-[11px] text-emerald-700 hover:bg-emerald-50 dark:border-emerald-800 dark:text-emerald-400 dark:hover:bg-emerald-950/40"
                    >
                      Resolve
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString();
}