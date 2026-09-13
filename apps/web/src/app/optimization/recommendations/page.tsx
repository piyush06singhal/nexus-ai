"use client";

import { useEffect, useState } from "react";
import {
  approveRecommendation,
  fetchRecommendations,
  rejectRecommendation,
} from "@/lib/api";
import type { RecommendationPublic } from "@/lib/types";
import { usePhase12 } from "@/components/phase12/Phase12Shell";
import {
  ActionButton,
  Dash,
  JsonBlock,
  SectionCard,
  StringList,
} from "@/components/phase12/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

/** Convert an unknown JSON-ish value into a readable line for dialogs. */
function asText(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v;
  if (Array.isArray(v)) return v.map(asText).filter((s) => s !== "—").join("; ");
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function humanPreview(v: unknown, limit = 220): string {
  const t = asText(v);
  return t.length > limit ? `${t.slice(0, limit)}…` : t;
}

const EXPLANATION_ROWS: { key: string; label: string }[] = [
  { key: "what", label: "What" },
  { key: "why", label: "Why" },
  { key: "why_this_candidate", label: "Why this candidate" },
  { key: "constraints", label: "Constraints honored" },
  { key: "expected_cost", label: "Expected cost" },
  { key: "risks", label: "Risks" },
  { key: "assumptions", label: "Assumptions" },
  { key: "approval", label: "Approval" },
];

export default function RecommendationsPage() {
  const { companyId } = usePhase12();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [recs, setRecs] = useState<RecommendationPublic[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState<{ id: string; action: string } | null>(null);

  function load() {
    if (!companyId) return;
    fetchRecommendations({ companyId })
      .then((list) => {
        setError(null);
        setRecs(list);
        setState({ kind: "ok" });
      })
      .catch((err: unknown) => {
        setState({
          kind: "error",
          message:
            err instanceof Error
              ? err.message
              : "Failed to load recommendations",
        });
      });
  }

  useEffect(() => {
    if (!companyId) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  function updateRec(updated: RecommendationPublic) {
    setRecs((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
  }

  async function approve(rec: RecommendationPublic) {
    const text = [
      `Approve recommendation ${rec.id.slice(0, 8)} ("${rec.title}")?`,
      "",
      "This marks the proposal for execution — execution itself is governed and approved elsewhere. It does NOT apply changes here.",
      "",
      `Assumptions: ${humanPreview(rec.assumptions_json ?? rec.explanation_json?.assumptions)}`,
      `Expected benefit: ${humanPreview(rec.expected_benefit_json ?? rec.explanation_json?.expected_benefit)}`,
      `Risks: ${humanPreview(rec.risk_json ?? rec.explanation_json?.risks)}`,
    ].join("\n");
    if (!window.confirm(text)) return;
    setBusy({ id: rec.id, action: "approve" });
    setError(null);
    setDone(null);
    try {
      const updated = await approveRecommendation(rec.id);
      updateRec(updated);
      setDone(`Recommendation approved → ${updated.status}.`);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Approval failed",
      );
    } finally {
      setBusy(null);
    }
  }

  async function reject(rec: RecommendationPublic) {
    const reason = window.prompt(
      `Reject recommendation ${rec.id.slice(0, 8)}?\n\nRejection reason (optional):`,
    );
    if (reason === null) return;
    setBusy({ id: rec.id, action: "reject" });
    setError(null);
    setDone(null);
    try {
      const updated = await rejectRecommendation(rec.id, {
        reason: reason.trim() || null,
      });
      updateRec(updated);
      setDone(`Recommendation rejected${reason.trim() ? " with reason recorded" : ""}.`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Rejection failed");
    } finally {
      setBusy(null);
    }
  }

  if (!companyId) {
    return (
      <p className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
        Select a company in the top bar to review optimization recommendations.
      </p>
    );
  }
  if (state.kind === "loading") {
    return (
      <div className="h-48 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
    );
  }
  if (state.kind === "error") {
    return (
      <p className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300">
        {state.message}
      </p>
    );
  }

  return (
    <div className="space-y-6">
      {(error || done) && (
        <p
          className={
            error
              ? "rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300"
              : "rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:border-emerald-900/40 dark:bg-emerald-950/30 dark:text-emerald-300"
          }
        >
          {error ?? done}
        </p>
      )}

      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-300">
        <p className="font-semibold">RECOMMENDED / SIMULATED</p>
        <p className="mt-1 text-xs">
          These proposals do not modify production. Scores, benefits, costs and
          risks are <strong>modeled estimates</strong>. Approval marks a
          proposal for execution; execution is governed and requires review
          elsewhere. Rejections are recorded with a reason for the audit trail.
        </p>
      </div>

      {recs.length === 0 ? (
        <SectionCard title="Recommendations">
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No recommendations yet. Run an optimization problem, then choose
            &quot;Recommend from run&quot; to generate an explainable proposal.
          </p>
        </SectionCard>
      ) : (
        <>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {recs.length} recommendation{recs.length === 1 ? "" : "s"}
          </p>
          {recs.map((rec) => {
            const resolved = ["approved", "rejected", "applied"].includes(
              rec.status,
            );
            const explanation = rec.explanation_json ?? {};
            return (
              <SectionCard
                key={rec.id}
                title={`${rec.title}  ·  ${rec.status.replace("_", " ")}`}
                action={
                  <span className="text-xs text-zinc-400">
                    {new Date(rec.created_at).toLocaleString()}
                  </span>
                }
              >
                <div className="space-y-3">
                  <div className="grid grid-cols-1 gap-2 text-xs text-zinc-500 dark:text-zinc-400 sm:grid-cols-3">
                    <p>
                      run{" "}
                      <span className="font-mono text-zinc-700 dark:text-zinc-300">
                        {rec.run_id}
                      </span>
                    </p>
                    <p>
                      approval gate{" "}
                      <Dash value={rec.approval_gate_id} />
                    </p>
                    <p>
                      approved at{" "}
                      <Dash
                        value={
                          rec.approved_at
                            ? new Date(rec.approved_at).toLocaleString()
                            : null
                        }
                      />
                    </p>
                  </div>

                  {rec.applied_ref && (
                    <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:border-emerald-900/40 dark:bg-emerald-950/30 dark:text-emerald-300">
                      Applied reference:{" "}
                      <span className="font-mono">{rec.applied_ref}</span>
                    </p>
                  )}
                  {rec.rejected_reason && (
                    <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300">
                      Rejection reason: {rec.rejected_reason}
                    </p>
                  )}

                  <details>
                    <summary className="cursor-pointer text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                      Explanation (what / why / constraints)
                    </summary>
                    <div className="mt-2 space-y-2">
                      <dl className="divide-y divide-zinc-100 dark:divide-zinc-800">
                        {EXPLANATION_ROWS.map(({ key, label }) => {
                          const value = explanation[key];
                          if (value === undefined || value === null) return null;
                          return (
                            <div
                              key={key}
                              className="flex items-start justify-between gap-4 py-2"
                            >
                              <dt className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                                {label}
                              </dt>
                              <dd className="min-w-0 flex-1 break-words text-right text-sm text-zinc-900 dark:text-zinc-100">
                                {key === "alternatives" ? (
                                  <StringList value={value} />
                                ) : (
                                  asText(value)
                                )}
                              </dd>
                            </div>
                          );
                        })}
                        {Boolean(explanation.alternatives) && (
                          <div className="flex items-start justify-between gap-4 py-2">
                            <dt className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                              Alternatives
                            </dt>
                            <dd className="min-w-0 flex-1">
                              <StringList value={explanation.alternatives} />
                            </dd>
                          </div>
                        )}
                      </dl>
                      {Object.keys(explanation).length === 0 && (
                        <p className="text-xs text-zinc-400">
                          No structured explanation recorded for this
                          recommendation.
                        </p>
                      )}
                    </div>
                  </details>

                  <details>
                    <summary className="cursor-pointer text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                      Proposed candidate values
                    </summary>
                    <div className="mt-2">
                      <JsonBlock value={rec.candidate_values_json} />
                    </div>
                  </details>

                  <details>
                    <summary className="cursor-pointer text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                      Benefit / cost / risk / assumptions (modeled)
                    </summary>
                    <div className="mt-2 grid gap-2 lg:grid-cols-2">
                      <div>
                        <p className="mb-1 text-xs uppercase tracking-wide text-zinc-500">
                          Expected benefit
                        </p>
                        <JsonBlock value={rec.expected_benefit_json} />
                      </div>
                      <div>
                        <p className="mb-1 text-xs uppercase tracking-wide text-zinc-500">
                          Expected cost
                        </p>
                        <JsonBlock value={rec.expected_cost_json} />
                      </div>
                      <div>
                        <p className="mb-1 text-xs uppercase tracking-wide text-zinc-500">
                          Risk
                        </p>
                        <JsonBlock value={rec.risk_json} />
                      </div>
                      <div>
                        <p className="mb-1 text-xs uppercase tracking-wide text-zinc-500">
                          Assumptions
                        </p>
                        <JsonBlock value={rec.assumptions_json} />
                      </div>
                    </div>
                  </details>

                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    <ActionButton
                      busy={busy?.id === rec.id && busy?.action === "approve"}
                      disabled={resolved}
                      onClick={() => approve(rec)}
                    >
                      Approve (marks for execution)
                    </ActionButton>
                    <ActionButton
                      busy={busy?.id === rec.id && busy?.action === "reject"}
                      disabled={resolved}
                      onClick={() => reject(rec)}
                    >
                      Reject
                    </ActionButton>
                    {resolved && (
                      <p className="text-xs text-zinc-400">
                        Already {rec.status}.
                      </p>
                    )}
                  </div>
                </div>
              </SectionCard>
            );
          })}
        </>
      )}
    </div>
  );
}