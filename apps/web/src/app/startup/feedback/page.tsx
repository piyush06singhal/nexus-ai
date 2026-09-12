"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, RefreshCw } from "lucide-react";
import {
  createFeedback,
  fetchFeedback,
  replanCompany,
} from "@/lib/api";
import type { StartupFeedback } from "@/lib/types";
import { useStartup } from "../_components/StartupShell";
import { ActionButton, SectionCard } from "../_components/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; feedback: StartupFeedback[] }
  | { kind: "error"; message: string };

export default function FeedbackPage() {
  const { companyId } = useStartup();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    fetchFeedback(companyId)
      .then((feedback) => !cancelled && setState({ kind: "ok", feedback }))
      .catch((err: Error) =>
        !cancelled && setState({ kind: "error", message: err.message }),
      );
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  async function runReplan() {
    if (!companyId) return;
    setBusy(true);
    setMsg(null);
    try {
      const result = await replanCompany(companyId);
      const resp = result.decision.response;
      setMsg(
        result.decision.requires_approval
          ? `Replan response '${resp}' requires approval — check Approvals.`
          : `Replan decision: ${resp}. ${result.decision.reason}`,
      );
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Replan request failed");
    } finally {
      setBusy(false);
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

  const { feedback } = state;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
            Feedback & replanning
          </h2>
          <p className="max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
            Structured feedback signals surface from KPI, task, verification,
            recovery, project, and resource signals. Feedback is advisory — it
            never auto-executes a recommendation. Replanning evaluates triggers
            and produces a bounded response.
          </p>
        </div>
        <div className="flex gap-2">
          <ActionButton onClick={() => setShowForm((v) => !v)}>
            Record feedback
          </ActionButton>
          <ActionButton onClick={runReplan} busy={busy}>
            <span className="inline-flex items-center gap-1">
              <RefreshCw className="h-3.5 w-3.5" /> Evaluate replan
            </span>
          </ActionButton>
        </div>
      </div>

      {msg && (
        <p className="rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300">
          {msg}
        </p>
      )}

      {showForm && (
        <FeedbackForm companyId={companyId} onCreated={() => setShowForm(false)} />
      )}

      <SectionCard
        title={`Feedback records (${feedback.length})`}
      >
        {feedback.length === 0 ? (
          <div className="flex flex-col items-center py-8 text-center">
            <CheckCircle2 className="h-8 w-8 text-zinc-300 dark:text-zinc-700" />
            <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
              No feedback recorded yet. Operating cycles record feedback from
              observed state.
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {feedback.map((f) => (
              <li key={f.id} className="py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-zinc-100 px-2 py-0.5 text-[11px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                    {f.category}
                  </span>
                  <span
                    className={
                      "rounded-full px-2 py-0.5 text-[11px] font-medium " +
                      (f.confidence >= 0.7
                        ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                        : f.confidence >= 0.4
                          ? "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300"
                          : "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400")
                    }
                  >
                    {Math.round(f.confidence * 100)}% conf
                  </span>
                  <span className="text-xs text-zinc-400">
                    {f.source ?? "system"} ·{" "}
                    {f.created_at ? new Date(f.created_at).toLocaleString() : ""}
                  </span>
                </div>
                <p className="mt-1.5 text-sm text-zinc-700 dark:text-zinc-300">
                  {f.observation}
                </p>
                {f.recommendation && (
                  <p className="mt-1 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                    Recommendation: {f.recommendation}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}

function FeedbackForm({
  companyId,
  onCreated,
}: {
  companyId: string;
  onCreated: () => void;
}) {
  const [category, setCategory] = useState("");
  const [observation, setObservation] = useState("");
  const [recommendation, setRecommendation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createFeedback(companyId, {
        category,
        observation,
        recommendation: recommendation || undefined,
        source: "operator",
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to record feedback");
    } finally {
      setBusy(false);
    }
  }

  const base =
    "w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

  return (
    <form
      onSubmit={submit}
      className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950"
    >
      <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
        Record a feedback signal
      </h3>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field label="Category" required>
          <input
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            required
            className={base}
            placeholder="e.g. risk_exposure"
          />
        </Field>
        <Field label="Recommendation">
          <input
            value={recommendation}
            onChange={(e) => setRecommendation(e.target.value)}
            className={base}
            placeholder="Advisory — never auto-executed"
          />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Observation" required>
            <textarea
              value={observation}
              onChange={(e) => setObservation(e.target.value)}
              required
              rows={3}
              className={base}
              placeholder="What did you observe about this company?"
            />
          </Field>
        </div>
      </div>
      {error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}
      <div className="mt-4">
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900"
        >
          {busy ? "Saving…" : "Record feedback"}
        </button>
      </div>
    </form>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-zinc-500 dark:text-zinc-400">
        {label}
        {required && <span className="text-red-500"> *</span>}
      </span>
      {children}
    </label>
  );
}