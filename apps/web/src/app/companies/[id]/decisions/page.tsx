"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, Plus, Scale } from "lucide-react";
import { createCompanyDecision, fetchCompanyDecisions } from "@/lib/api";
import type { Decision, DecisionOption } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; decisions: Decision[] }
  | { kind: "error"; message: string };

const STATUSES = [
  "draft",
  "pending_review",
  "approved",
  "rejected",
  "implemented",
  "expired",
  "cancelled",
];

export default function CompanyDecisionsPage({ params }: { params: Promise<{ id: string }> }) {
  const [companyId, setCompanyId] = useState<string>("");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [showForm, setShowForm] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("");

  useEffect(() => {
    params.then((p) => setCompanyId(p.id));
  }, [params]);

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    fetchCompanyDecisions(companyId, statusFilter || undefined)
      .then((decisions) => {
        if (!cancelled) setState({ kind: "ok", decisions });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ kind: "error", message: err.message });
      });
    return () => { cancelled = true; };
  }, [companyId, statusFilter]);

  function reload() {
    if (!companyId) return;
    setState({ kind: "loading" });
    fetchCompanyDecisions(companyId, statusFilter || undefined)
      .then((decisions) => setState({ kind: "ok", decisions }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }

  return (
    <div className="space-y-6">
      <Link href={`/companies/${companyId}`} className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
        <ArrowLeft className="h-4 w-4" /> Company
      </Link>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">Decision Center</h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Decisions require authorized review with a full audit trail. Recommendations never execute automatically.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          <Plus className="h-4 w-4" />
          New decision
        </button>
      </div>

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{state.message}</p>
      )}

      {showForm && (
        <DecisionForm
          companyId={companyId}
          onCreated={() => { setShowForm(false); reload(); }}
        />
      )}

      {state.kind === "ok" && state.decisions.length > 0 && (
        <div className="flex flex-wrap gap-3">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          >
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>{s.replace("_", " ")}</option>
            ))}
          </select>
        </div>
      )}

      {state.kind === "loading" && <div className="h-48 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />}

      {state.kind === "ok" && state.decisions.length === 0 && !statusFilter && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <Scale className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            No decisions yet. Create a decision to route it through the review lifecycle.
          </p>
        </div>
      )}

      {state.kind === "ok" && state.decisions.length === 0 && statusFilter && (
        <p className="text-sm text-zinc-500">No decisions with status “{statusFilter.replace("_", " ")}”.</p>
      )}

      {state.kind === "ok" && state.decisions.length > 0 && (
        <div className="space-y-2">
          {state.decisions.map((d) => <DecisionRow key={d.id} decision={d} companyId={companyId} />)}
        </div>
      )}
    </div>
  );
}

function DecisionRow({ decision, companyId }: { decision: Decision; companyId: string }) {
  return (
    <Link
      href={`/companies/${companyId}/decisions/${decision.id}`}
      className="block rounded-xl border border-zinc-200 bg-white p-4 transition hover:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:border-zinc-600"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{decision.question}</p>
          <p className="mt-1 text-xs text-zinc-500">
            {decision.options.length} options · risk {decision.risk_level} · requires {decision.required_authority.replace(/_/g, " ")}
          </p>
          {decision.selected_option && (
            <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">
              selected: {decision.selected_option.label}
            </p>
          )}
        </div>
        <StatusBadge status={decision.status} />
      </div>
    </Link>
  );
}

function DecisionForm({ companyId, onCreated }: { companyId: string; onCreated: () => void }) {
  const [question, setQuestion] = useState("");
  const [optionsText, setOptionsText] = useState("");
  const [riskLevel, setRiskLevel] = useState("medium");
  const [requiredAuthority, setRequiredAuthority] = useState("manager");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const options: DecisionOption[] = optionsText
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((label, i) => ({ id: `option_${i + 1}`, label }));
    if (options.length < 2) {
      setError("Provide at least two options, one per line.");
      setBusy(false);
      return;
    }
    try {
      await createCompanyDecision(companyId, {
        question,
        options,
        risk_level: riskLevel,
        required_authority: requiredAuthority as Decision["required_authority"],
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create decision");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
      <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Create decision</h2>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field label="Question" required>
            <input value={question} onChange={(e) => setQuestion(e.target.value)} required className={inputCls} placeholder="e.g. Should we adopt microservices?" />
          </Field>
        </div>
        <div className="sm:col-span-2">
          <Field label="Options (one per line)" required>
            <textarea value={optionsText} onChange={(e) => setOptionsText(e.target.value)} required rows={3} className={inputCls} placeholder={"Yes\nNo\nDefer"} />
          </Field>
        </div>
        <Field label="Risk level">
          <select value={riskLevel} onChange={(e) => setRiskLevel(e.target.value)} className={inputCls}>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
        </Field>
        <Field label="Required authority">
          <select value={requiredAuthority} onChange={(e) => setRequiredAuthority(e.target.value)} className={inputCls}>
            <option value="individual_contributor">Individual contributor</option>
            <option value="team_lead">Team lead</option>
            <option value="manager">Manager</option>
            <option value="executive">Executive</option>
            <option value="company_admin">Company admin</option>
          </select>
        </Field>
      </div>

      {error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="mt-4 flex items-center gap-2">
        <button type="submit" disabled={busy} className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900">
          {busy ? "Creating…" : "Create decision"}
        </button>
      </div>
    </form>
  );
}

const inputCls = "w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-zinc-500 dark:text-zinc-400">
        {label}{required && <span className="text-red-500"> *</span>}
      </span>
      {children}
    </label>
  );
}