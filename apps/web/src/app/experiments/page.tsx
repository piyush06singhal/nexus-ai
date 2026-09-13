"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  approveExperiment,
  createExperiment,
  fetchExperiments,
  runExperiment,
  stopExperiment,
  submitExperiment,
} from "@/lib/api";
import type { ExperimentPublic } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { usePhase12 } from "@/components/phase12/Phase12Shell";
import { ActionButton, SectionCard } from "@/components/phase12/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

const INPUT_CLASS =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

export default function ExperimentsPage() {
  const { companyId } = usePhase12();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [experiments, setExperiments] = useState<ExperimentPublic[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // create form
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [hypothesis, setHypothesis] = useState("");
  const [sampleSize, setSampleSize] = useState("200");
  const [metrics, setMetrics] = useState("win_rate");
  const [variantsText, setVariantsText] = useState("");

  function load() {
    if (!companyId) return;
    fetchExperiments({ companyId })
      .then((list) => {
        setError(null);
        setExperiments(list);
        setState({ kind: "ok" });
      })
      .catch((err: unknown) => {
        setState({
          kind: "error",
          message:
            err instanceof Error ? err.message : "Failed to load experiments",
        });
      });
  }

  useEffect(() => {
    if (!companyId) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  async function act(action: "submit" | "approve" | "run" | "stop", id: string, ex: ExperimentPublic) {
    setBusy(id);
    setError(null);
    setDone(null);
    if (action === "approve") {
      const ok = window.confirm(
        `Approve experiment "${ex.name}"?\n\nHypothesis: ${ex.hypothesis ?? "—"}\nSample size: ${ex.sample_size ?? "default"}\nAuthors a bounded, isolated comparison — no production traffic unless policy permits.`,
      );
      if (!ok) {
        setBusy(null);
        return;
      }
    }
    try {
      if (action === "submit") await submitExperiment(id);
      else if (action === "approve") await approveExperiment(id);
      else if (action === "run") await runExperiment(id);
      else await stopExperiment(id);
      setDone(`Experiment "${ex.name}" → ${action}.`);
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Experiment action failed");
    } finally {
      setBusy(null);
    }
  }

  async function createExp() {
    if (!companyId) {
      setError("Select a company first.");
      return;
    }
    if (!name.trim()) {
      setError("Give the experiment a name.");
      return;
    }
    let variants: Record<string, unknown>[] | undefined;
    if (variantsText.trim()) {
      try {
        const parsed = JSON.parse(variantsText);
        if (!Array.isArray(parsed)) throw new Error("not array");
        variants = parsed as Record<string, unknown>[];
      } catch {
        setError("Variants JSON must be an array, e.g. [{\"name\":\"a\"}].");
        return;
      }
    }
    setBusy("create");
    setError(null);
    setDone(null);
    try {
      const created = await createExperiment({
        company_id: companyId,
        name: name.trim(),
        description: description.trim() || null,
        hypothesis: hypothesis.trim() || null,
        sample_size: Number(sampleSize) || undefined,
        metrics: metrics
          .split(",")
          .map((m) => m.trim())
          .filter(Boolean),
        variants: variants ?? [],
      });
      setDone(`Experiment "${created.name}" created → ${created.status}.`);
      setName("");
      setDescription("");
      setHypothesis("");
      setVariantsText("");
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create experiment");
    } finally {
      setBusy(null);
    }
  }

  if (!companyId) {
    return (
      <p className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
        Select a company in the top bar to view and run experiments.
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
        Experiments are <strong>isolated comparisons</strong>, approval-gated
        and off for production traffic by default. Conclusions carry sample
        size, confidence, and limitations — no overstated significance.
      </p>

      <SectionCard
        title="Define a new experiment"
        action={
          <ActionButton
            busy={busy === "create"}
            disabled={!companyId || !name.trim()}
            onClick={createExp}
          >
            Create experiment
          </ActionButton>
        }
      >
        <div className="space-y-3 text-sm">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Launch timing: 4-week vs 6-week"
            className={INPUT_CLASS}
          />
          <input
            value={hypothesis}
            onChange={(e) => setHypothesis(e.target.value)}
            placeholder="Hypothesis"
            className={INPUT_CLASS}
          />
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description (optional)"
            rows={2}
            className={INPUT_CLASS}
          />
          <div className="grid gap-2 sm:grid-cols-2">
            <input
              type="number"
              value={sampleSize}
              onChange={(e) => setSampleSize(e.target.value)}
              placeholder="sample size"
              className={INPUT_CLASS}
            />
            <input
              value={metrics}
              onChange={(e) => setMetrics(e.target.value)}
              placeholder="metrics (comma-separated)"
              className={INPUT_CLASS}
            />
          </div>
          <textarea
            value={variantsText}
            onChange={(e) => setVariantsText(e.target.value)}
            placeholder={'Variants JSON (optional), e.g. [{"name":"4wk"},{"name":"6wk"}]'}
            rows={2}
            className={`${INPUT_CLASS} font-mono text-xs`}
          />
        </div>
      </SectionCard>

      <SectionCard
        title="Experiments"
        action={
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            {experiments.length} experiment{experiments.length === 1 ? "" : "s"}
          </span>
        }
      >
        {experiments.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No experiments yet. Define one above to start.
          </p>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {experiments.map((ex) => (
              <li
                key={ex.id}
                className="flex flex-wrap items-center justify-between gap-3 py-3"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      href={`/experiments/${ex.id}`}
                      className="text-sm font-medium text-indigo-600 hover:underline dark:text-indigo-400"
                    >
                      {ex.name}
                    </Link>
                    <StatusBadge status={ex.status as never} />
                  </div>
                  {ex.hypothesis && (
                    <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
                      {ex.hypothesis}
                    </p>
                  )}
                  <p className="mt-0.5 text-xs text-zinc-400">
                    sample {ex.sample_size ?? "—"}
                    {ex.approval_gate_id ? " · approval-gated" : ""} · created{" "}
                    {new Date(ex.created_at).toLocaleString()}
                  </p>
                </div>
                <div className="flex items-center gap-1.5">
                  {ex.status === "draft" && (
                    <ActionButton busy={busy === ex.id} onClick={() => act("submit", ex.id, ex)}>
                      Submit
                    </ActionButton>
                  )}
                  {ex.status === "pending_approval" && (
                    <ActionButton busy={busy === ex.id} onClick={() => act("approve", ex.id, ex)}>
                      Approve
                    </ActionButton>
                  )}
                  {ex.status === "approved" && (
                    <ActionButton busy={busy === ex.id} onClick={() => act("run", ex.id, ex)}>
                      Run
                    </ActionButton>
                  )}
                  {ex.status === "running" && (
                    <ActionButton busy={busy === ex.id} onClick={() => act("stop", ex.id, ex)}>
                      Stop
                    </ActionButton>
                  )}
                  <Link
                    href={`/experiments/${ex.id}`}
                    className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
                  >
                    Open
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}