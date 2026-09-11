"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, Check, ShieldCheck, X } from "lucide-react";
import {
  approveDecision,
  fetchCompanyEmployees,
  fetchDecisionReviews,
  getDecision,
  implementDecision,
  rejectDecision,
  submitDecision,
} from "@/lib/api";
import type { CompanyEmployee, Decision, DecisionReviewEntry } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; decision: Decision; reviews: DecisionReviewEntry[]; employees: CompanyEmployee[] }
  | { kind: "error"; message: string };

export default function DecisionDetailPage({ params }: { params: Promise<{ id: string; decisionId: string }> }) {
  const [ids, setIds] = useState<{ companyId: string; decisionId: string }>({ companyId: "", decisionId: "" });
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [reviewer, setReviewer] = useState("");
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  useEffect(() => {
    params.then((p) => setIds({ companyId: p.id, decisionId: p.decisionId }));
  }, [params]);

  useEffect(() => {
    if (!ids.companyId || !ids.decisionId) return;
    let cancelled = false;
    Promise.all([
      getDecision(ids.decisionId),
      fetchDecisionReviews(ids.decisionId),
      fetchCompanyEmployees(ids.companyId),
    ])
      .then(([decision, reviews, employees]) => {
        if (!cancelled) setState({ kind: "ok", decision, reviews, employees });
      })
      .catch((err) => {
        if (!cancelled) {
          setState({
            kind: "error",
            message: err instanceof Error ? err.message : "Failed to load decision",
          });
        }
      });
    return () => { cancelled = true; };
  }, [ids]);

  function reload() {
    if (!ids.decisionId) return;
    setState({ kind: "loading" });
    Promise.all([
      getDecision(ids.decisionId),
      fetchDecisionReviews(ids.decisionId),
      fetchCompanyEmployees(ids.companyId),
    ])
      .then(([decision, reviews, employees]) => setState({ kind: "ok", decision, reviews, employees }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }

  async function act(action: "submit" | "approve" | "reject" | "implement") {
    if (state.kind !== "ok") return;
    setBusy(true);
    setFlash(null);
    try {
      if (action === "submit") {
        await submitDecision(state.decision.id, reviewer || undefined);
      } else if (action === "approve") {
        if (!reviewer) { setFlash("Select a reviewer first."); setBusy(false); return; }
        await approveDecision(state.decision.id, reviewer, rationale || undefined);
      } else if (action === "reject") {
        if (!reviewer) { setFlash("Select a reviewer first."); setBusy(false); return; }
        await rejectDecision(state.decision.id, reviewer, rationale || undefined);
      } else {
        if (!reviewer) { setFlash("Select an actor first."); setBusy(false); return; }
        await implementDecision(state.decision.id, reviewer);
      }
      setRationale("");
      reload();
    } catch (err) {
      setFlash(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <Link href={`/companies/${ids.companyId}/decisions`} className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
        <ArrowLeft className="h-4 w-4" /> Decisions
      </Link>

      {state.kind === "loading" && <div className="h-64 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />}

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{state.message}</p>
      )}

      {state.kind === "ok" && (
        <>
          <div className="flex items-start justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{state.decision.question}</h1>
                <StatusBadge status={state.decision.status} />
              </div>
              <p className="mt-1 text-sm text-zinc-500">
                risk {state.decision.risk_level} · requires {state.decision.required_authority.replace(/_/g, " ")}
              </p>
            </div>
            <div className="flex gap-2">
              {state.decision.status === "draft" && (
                <Btn label="Submit for review" icon={<ShieldCheck className="h-4 w-4" />} onClick={() => act("submit")} primary />
              )}
              {state.decision.status === "pending_review" && (
                <Btn label="Approve" icon={<Check className="h-4 w-4" />} onClick={() => act("approve")} primary />
              )}
              {state.decision.status === "pending_review" && (
                <Btn label="Reject" icon={<X className="h-4 w-4" />} onClick={() => act("reject")} danger />
              )}
              {state.decision.status === "approved" && (
                <Btn label="Implement" icon={<Check className="h-4 w-4" />} onClick={() => act("implement")} primary />
              )}
            </div>
          </div>

          {flash && <p className="text-sm text-amber-600 dark:text-amber-400">{flash}</p>}

          {/* Reviewer/actor picker */}
          {state.decision.status !== "implemented" && state.decision.status !== "rejected" && state.decision.status !== "draft" && (
            <div className="flex flex-wrap items-end gap-3 rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
              <Field label="Reviewer / actor">
                <select value={reviewer} onChange={(e) => setReviewer(e.target.value)} className={inputCls}>
                  <option value="">Select employee…</option>
                  {state.employees.map((e) => (
                    <option key={e.id} value={e.id}>{e.display_name || e.name} ({e.responsible_scope?.authority_level ?? e.role})</option>
                  ))}
                </select>
              </Field>
              {state.decision.status === "pending_review" && (
                <Field label="Rationale">
                  <input value={rationale} onChange={(e) => setRationale(e.target.value)} className={inputCls} placeholder="Rationale for the review" />
                </Field>
              )}
              {busy && <p className="mb-2 text-xs text-zinc-500">Working…</p>}
            </div>
          )}

          {/* Options */}
          <section>
            <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">Options</h2>
            <div className="space-y-2">
              {state.decision.options.map((o) => (
                <div
                  key={o.id}
                  className={`flex items-center justify-between rounded-lg border px-4 py-3 ${
                    state.decision.selected_option?.id === o.id
                      ? "border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30"
                      : "border-zinc-200 dark:border-zinc-800"
                  }`}
                >
                  <span className="text-sm text-zinc-700 dark:text-zinc-300">{o.id}<span className="text-zinc-400"> · </span>{o.label}</span>
                  {state.decision.selected_option?.id === o.id && (
                    <StatusBadge status="approved" />
                  )}
                </div>
              ))}
            </div>
          </section>

          {/* Detail grid */}
          <div className="grid gap-4 sm:grid-cols-2">
            {state.decision.rationale && (
              <DetailBlock title="Rationale" text={state.decision.rationale} />
            )}
            {state.decision.risk && (
              <DetailBlock title="Risk assessment" body={state.decision.risk} />
            )}
            {state.decision.budget_impact && (
              <DetailBlock title="Budget impact" body={state.decision.budget_impact} />
            )}
            {state.decision.evidence && (
              <DetailBlock title="Evidence" body={state.decision.evidence} />
            )}
          </div>

          {/* Audit trail */}
          <section>
            <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">Audit trail</h2>
            {state.reviews.length === 0 ? (
              <p className="text-sm text-zinc-500">No reviews recorded yet.</p>
            ) : (
              <div className="space-y-2">
                {state.reviews.map((r) => (
                  <div key={r.id} className="rounded-lg border border-zinc-200 px-4 py-3 dark:border-zinc-800">
                    <div className="flex items-center justify-between">
                      <p className="text-sm text-zinc-700 dark:text-zinc-300">
                        <span className="font-medium">{r.action.replace(/_/g, " ")}</span>
                        {r.verdict && <span className="text-zinc-500"> · {r.verdict.replace(/_/g, " ")}</span>}
                      </p>
                      <span className="text-xs text-zinc-400">{r.created_at ? fmtDate(r.created_at) : ""}</span>
                    </div>
                    {r.previous_status && r.next_status && (
                      <p className="mt-1 text-xs text-zinc-500">
                        {r.previous_status.replace(/_/g, " ")} → {r.next_status.replace(/_/g, " ")}
                      </p>
                    )}
                    {r.rationale && <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">{r.rationale}</p>}
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function DetailBlock({ title, text, body }: { title: string; text?: string; body?: Record<string, unknown> }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <p className="text-xs font-medium text-zinc-500">{title}</p>
      {text ? (
        <p className="mt-1 text-sm text-zinc-700 dark:text-zinc-300">{text}</p>
      ) : (
        <pre className="mt-1 whitespace-pre-wrap font-mono text-xs text-zinc-600 dark:text-zinc-400">
          {JSON.stringify(body, null, 2)}
        </pre>
      )}
    </div>
  );
}

function Btn({ label, icon, onClick, primary, danger }: { label: string; icon?: React.ReactNode; onClick: () => void; primary?: boolean; danger?: boolean }) {
  const cls = primary
    ? "inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
    : danger
      ? "inline-flex items-center gap-2 rounded-lg border border-red-300 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950/40"
      : "inline-flex items-center gap-2 rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800";
  return (
    <button onClick={onClick} className={cls}>
      {icon} {label}
    </button>
  );
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString();
}

const inputCls = "w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block min-w-[180px]">
      <span className="mb-1 block text-xs font-medium text-zinc-500 dark:text-zinc-400">{label}</span>
      {children}
    </label>
  );
}