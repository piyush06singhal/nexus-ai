"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  createAgentRecommendation,
  fetchAgentRecommendations,
} from "@/lib/api";
import type { AgentRecommendationPublic } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { usePhase12 } from "@/components/phase12/Phase12Shell";
import { ActionButton, JsonBlock, SectionCard } from "@/components/phase12/ui";
import { HBar } from "@/components/phase12/charts";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok" }
  | {kind: "error"; message: string };

const INPUT_CLASS =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

export default function MarketplaceRecommendationsPage() {
  const { companyId } = usePhase12();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [recs, setRecs] = useState<AgentRecommendationPublic[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // create form
  const [taskType, setTaskType] = useState("");
  const [skillsText, setSkillsText] = useState("");
  const [budgetMax, setBudgetMax] = useState("");
  const [latencyMax, setLatencyMax] = useState("");

  function load() {
    if (!companyId) return;
    fetchAgentRecommendations({ companyId })
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

  async function createRec() {
    if (!companyId) {
      setError("Select a company first.");
      return;
    }
    if (!taskType.trim()) {
      setError("Provide a task type to get a recommendation.");
      return;
    }
    const skills = skillsText
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    setBusy("create");
    setError(null);
    setDone(null);
    try {
      await createAgentRecommendation({
        company_id: companyId,
        task_type: taskType.trim(),
        required_skills: skills.length > 0 ? skills : undefined,
        budget_max: budgetMax.trim() ? Number(budgetMax) : undefined,
        latency_max_ms: latencyMax.trim() ? Number(latencyMax) : undefined,
      });
      setDone("Recommendation generated — review candidates below.");
      setTaskType("");
      setSkillsText("");
      setBudgetMax("");
      setLatencyMax("");
      load();
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to generate recommendation",
      );
    } finally {
      setBusy(null);
    }
  }

  if (!companyId) {
    return (
      <p className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
        Select a company in the top bar to get agent recommendations.
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

      <p className="max-w-3xl text-xs text-zinc-500 dark:text-zinc-400">
        Agent recommendations are <strong>proposals</strong> backed by measured
        benchmark and evaluation data. They require explicit human approval
        before any agent is created, installed, or modified.
      </p>

      <SectionCard
        title="Get agent recommendation"
        action={
          <ActionButton
            busy={busy === "create"}
            disabled={!companyId || !taskType.trim()}
            onClick={createRec}
          >
            Generate recommendation
          </ActionButton>
        }
      >
        <div className="space-y-3 text-sm">
          <input
            value={taskType}
            onChange={(e) => setTaskType(e.target.value)}
            placeholder="Task type (e.g. code-review, data-analysis)"
            className={INPUT_CLASS}
          />
          <input
            value={skillsText}
            onChange={(e) => setSkillsText(e.target.value)}
            placeholder="Required skills (comma-separated, optional)"
            className={INPUT_CLASS}
          />
          <div className="grid gap-2 sm:grid-cols-2">
            <input
              value={budgetMax}
              onChange={(e) => setBudgetMax(e.target.value)}
              placeholder="Max budget (optional)"
              className={INPUT_CLASS}
            />
            <input
              value={latencyMax}
              onChange={(e) => setLatencyMax(e.target.value)}
              placeholder="Max latency ms (optional)"
              className={INPUT_CLASS}
            />
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="Recommendations"
        action={
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            {recs.length} recommendation{recs.length === 1 ? "" : "s"}
          </span>
        }
      >
        {recs.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No recommendations yet. Generate one above.
          </p>
        ) : (
          <ul className="space-y-5">
            {recs.map((rec) => (
              <li
                key={rec.id}
                className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      {rec.package_id ? (
                        <Link
                          href={`/marketplace/agents/${rec.package_id}`}
                          className="text-sm font-medium text-indigo-600 hover:underline dark:text-indigo-400"
                        >
                          {rec.agent_id
                            ? `agent ${rec.agent_id.slice(0, 8)}`
                            : `package ${rec.package_id.slice(0, 8)}`}
                        </Link>
                      ) : (
                        <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                          {rec.agent_id ? `agent ${rec.agent_id.slice(0, 8)}` : "recommendation"}
                        </span>
                      )}
                      <StatusBadge status={rec.policy_status as never} />
                    </div>
                    {rec.reasoning && (
                      <p className="mt-1 max-w-2xl text-xs text-zinc-500 dark:text-zinc-400">
                        {rec.reasoning}
                      </p>
                    )}
                  </div>
                  {typeof rec.rank === "number" && (
                    <span className="rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                      rank {rec.rank}
                    </span>
                  )}
                </div>

                {typeof rec.score === "number" && (
                  <div className="mt-3 max-w-sm">
                    <HBar
                      label="score"
                      value={rec.score * 100}
                      max={100}
                      suffix="%"
                    />
                  </div>
                )}

                {(rec.tradeoffs_json &&
                  Object.keys(rec.tradeoffs_json).length > 0) ||
                (rec.request_json &&
                  Object.keys(rec.request_json).length > 0) ? (
                  <div className="mt-3 grid gap-3 lg:grid-cols-2">
                    {rec.tradeoffs_json &&
                      Object.keys(rec.tradeoffs_json).length > 0 && (
                        <div>
                          <p className="mb-1 text-xs uppercase tracking-wide text-zinc-500">
                            tradeoffs
                          </p>
                          <JsonBlock value={rec.tradeoffs_json} />
                        </div>
                      )}
                    {rec.request_json &&
                      Object.keys(rec.request_json).length > 0 && (
                        <div>
                          <p className="mb-1 text-xs uppercase tracking-wide text-zinc-500">
                            request
                          </p>
                          <JsonBlock value={rec.request_json} />
                        </div>
                      )}
                  </div>
                ) : null}

                <p className="mt-2 text-[0.65rem] text-zinc-400">
                  created {new Date(rec.created_at).toLocaleString()} · policy{" "}
                  <span className="font-mono">{rec.policy_status}</span> ·
                  compatibility{" "}
                  <span className="font-mono">{rec.compatibility}</span> ·
                  not yet applied
                </p>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}