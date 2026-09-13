"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  addPackageVersion,
  confirmInstallation,
  createPackageReview,
  fetchAgentPackage,
  fetchInstallations,
  fetchPackageBenchmarks,
  fetchPackageReviews,
  fetchPackageVersions,
  installAgentPackage,
  rejectInstallation,
} from "@/lib/api";
import type {
  AgentPackagePublic,
  AgentPackageVersionPublic,
  InstallationPublic,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { usePhase12 } from "@/components/phase12/Phase12Shell";
import { ActionButton, JsonBlock, SectionCard, StringList } from "@/components/phase12/ui";
import { HBar } from "@/components/phase12/charts";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

const INPUT_CLASS =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";
const SELECT_CLASS =
  "rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

export default function PackageDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const { companyId } = usePhase12();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [pkg, setPkg] = useState<AgentPackagePublic | null>(null);
  const [versions, setVersions] = useState<AgentPackageVersionPublic[]>([]);
  const [benchmarks, setBenchmarks] = useState<Record<string, unknown>[]>([]);
  const [reviews, setReviews] = useState<Record<string, unknown>[]>([]);
  const [installations, setInstallations] = useState<InstallationPublic[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // add version form
  const [vVersion, setVVersion] = useState("");
  const [vChangelog, setVChangelog] = useState("");
  const [vCompat, setVCompat] = useState("compatible");

  // review form
  const [rating, setRating] = useState("5");
  const [comment, setComment] = useState("");

  function load() {
    Promise.all([
      fetchAgentPackage(id),
      fetchPackageVersions(id),
      fetchPackageBenchmarks(id),
      fetchPackageReviews(id),
      companyId ? fetchInstallations({ companyId }) : Promise.resolve([]),
    ])
      .then(([p, vs, bs, rv, inst]) => {
        setError(null);
        setPkg(p);
        setVersions(vs);
        setBenchmarks(Array.isArray(bs) ? bs : []);
        setReviews(Array.isArray(rv) ? rv : []);
        setInstallations(inst);
        setState({ kind: "ok" });
      })
      .catch((err: unknown) => {
        setState({
          kind: "error",
          message:
            err instanceof Error ? err.message : "Failed to load package",
        });
      });
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, companyId]);

  async function addVersion() {
    if (!vVersion.trim() || !/^\d+\.\d+\.\d+$/.test(vVersion.trim())) {
      setError("Version must look like major.minor.patch (e.g. 1.1.0).");
      return;
    }
    setBusy("version");
    setError(null);
    setDone(null);
    try {
      const v = await addPackageVersion(id, {
        version: vVersion.trim(),
        changelog: vChangelog.trim() || null,
        compatibility: vCompat,
      });
      setDone(`Version ${v.version} added (${v.compatibility}).`);
      setVVersion("");
      setVChangelog("");
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to add version");
    } finally {
      setBusy(null);
    }
  }

  async function submitReview() {
    if (!comment.trim()) {
      setError("Add a comment with the review.");
      return;
    }
    setBusy("review");
    setError(null);
    setDone(null);
    try {
      await createPackageReview(id, {
        rating: Number(rating) || 0,
        comment: comment.trim(),
        company_id: companyId ?? undefined,
      });
      setDone("Review recorded.");
      setRating("5");
      setComment("");
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to submit review");
    } finally {
      setBusy(null);
    }
  }

  async function installNow() {
    if (!companyId) {
      setError("Select a company to install into first.");
      return;
    }
    const reqs = pkg?.requirements_json ?? null;
    const ok = window.confirm(
      `Install "${pkg?.display_name ?? pkg?.name}" into company ${companyId}?\n\nSecurity classification: ${pkg?.security}\nRequirements: ${JSON.stringify(reqs ?? {})}\n\nInstalling creates a governed agent via existing employee/agent management and may require approval. It never replaces a production agent silently.`,
    );
    if (!ok) return;
    setBusy("install");
    setError(null);
    setDone(null);
    try {
      const inst = await installAgentPackage({
        package_id: id,
        company_id: companyId,
        require_approval: true,
      });
      setDone(
        inst.status === "approval_required" || inst.status === "pending"
          ? `Installation created → ${inst.status}. It needs explicit confirmation below.`
          : `Installation → ${inst.status}.`,
      );
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Install failed");
    } finally {
      setBusy(null);
    }
  }

  async function decideInstallation(inst: InstallationPublic, confirm: boolean) {
    setBusy(`inst:${inst.id}`);
    setError(null);
    setDone(null);
    try {
      const updated = confirm
        ? await confirmInstallation(inst.id)
        : await rejectInstallation(inst.id);
      setDone(`Installation → ${updated.status}.`);
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Installation decision failed");
    } finally {
      setBusy(null);
    }
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
  if (!pkg) return null;

  const capKeys = Object.keys(pkg.capabilities_json ?? {});
  const skillKeys = Object.keys(pkg.skills_json ?? {});
  const taskKeys = Object.keys(pkg.supported_task_types_json ?? {});

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

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              {pkg.display_name ?? pkg.name}
            </h2>
            <StatusBadge status={pkg.status as never} />
            <StatusBadge status={pkg.security as never} />
          </div>
          {pkg.description && (
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{pkg.description}</p>
          )}
          <p className="mt-1 text-xs text-zinc-400">
            name <span className="font-mono">{pkg.name}</span> · created{" "}
            {new Date(pkg.created_at).toLocaleString()}
          </p>
        </div>
        <ActionButton
          busy={busy === "install"}
          disabled={!companyId || pkg.status !== "published"}
          onClick={installNow}
        >
          Install to this company
        </ActionButton>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <SectionCard title="Capabilities">
          <StringList value={capKeys} />
        </SectionCard>
        <SectionCard title="Skills">
          <StringList value={skillKeys} />
        </SectionCard>
        <SectionCard title="Supported task types">
          <StringList value={taskKeys} />
        </SectionCard>
      </div>

      {pkg.requirements_json && (
        <SectionCard title="Requirements & permissions">
          <JsonBlock value={pkg.requirements_json} />
          <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
            Requirements are metadata only — they describe what an installed
            agent may need, and are reviewed before installation.
          </p>
        </SectionCard>
      )}

      <SectionCard
        title="Versions"
        action={
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            {versions.length} version{versions.length === 1 ? "" : "s"}
          </span>
        }
      >
        {versions.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">No versions recorded.</p>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {versions.map((v) => (
              <li key={v.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <div>
                  <p className="text-sm text-zinc-900 dark:text-zinc-100">
                    <span className="font-mono">v{v.version}</span>{" "}
                    <StatusBadge status={v.compatibility as never} />
                  </p>
                  {v.changelog && (
                    <p className="text-xs text-zinc-500 dark:text-zinc-400">{v.changelog}</p>
                  )}
                </div>
                <span className="text-xs text-zinc-400">
                  {new Date(v.created_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-3 grid gap-2 sm:grid-cols-3 border-t border-zinc-100 pt-3 dark:border-zinc-800">
          <input
            value={vVersion}
            onChange={(e) => setVVersion(e.target.value)}
            placeholder="1.1.0"
            className={INPUT_CLASS}
          />
          <input
            value={vChangelog}
            onChange={(e) => setVChangelog(e.target.value)}
            placeholder="changelog (optional)"
            className={INPUT_CLASS}
          />
          <select value={vCompat} onChange={(e) => setVCompat(e.target.value)} className={SELECT_CLASS}>
            <option value="compatible">compatible</option>
            <option value="compatible_with_note">compatible_with_note</option>
            <option value="incompatible">incompatible</option>
          </select>
        </div>
        <div className="mt-2">
          <ActionButton busy={busy === "version"} disabled={!vVersion.trim()} onClick={addVersion}>
            Add version
          </ActionButton>
        </div>
      </SectionCard>

      <SectionCard
        title="Benchmarks"
        action={
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            +{benchmarks.length} record{benchmarks.length === 1 ? "" : "s"}
          </span>
        }
      >
        {benchmarks.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No benchmark evidence on file. Run this package&apos;s agent through
            a benchmark in the Evaluation surface.
          </p>
        ) : (
          <div className="space-y-1.5">
            {benchmarks.map((row, i) => {
              const r = row as Record<string, unknown>;
              const label = String(r.agent_name ?? r.benchmark ?? `benchmark ${i + 1}`);
              const score =
                typeof r.score === "number"
                  ? r.score
                  : typeof r.correctness === "number"
                    ? (r.correctness as number)
                    : typeof r.overall === "number"
                      ? (r.overall as number)
                      : 0;
              return (
                <HBar key={i} label={label} value={score * 100} max={100} suffix="%" />
              );
            })}
          </div>
        )}
        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
          Benchmark-derived evidence only — reputation is measured, never
          self-rated.
        </p>
      </SectionCard>

      <SectionCard
        title="Installations"
        action={
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            {installations.length} total
          </span>
        }
      >
        {installations.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Nothing installed yet for this company.
          </p>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {installations.map((inst) => (
              <li key={inst.id} className="flex flex-wrap items-center justify-between gap-3 py-2">
                <div>
                  <p className="flex flex-wrap items-center gap-2 text-sm text-zinc-900 dark:text-zinc-100">
                    <StatusBadge status={inst.status as never} />
                    <span className="font-mono text-xs text-zinc-500">{inst.id.slice(0, 8)}</span>
                    {inst.agent_id && <span className="text-xs text-zinc-500">agent {inst.agent_id.slice(0, 8)}</span>}
                  </p>
                  {inst.installed_at && (
                    <p className="text-xs text-zinc-400">installed {new Date(inst.installed_at).toLocaleString()}</p>
                  )}
                </div>
                {["approval_required", "pending", "installing"].includes(inst.status) && (
                  <div className="flex items-center gap-1.5">
                    <ActionButton busy={busy === `inst:${inst.id}`} onClick={() => decideInstallation(inst, true)}>
                      Confirm
                    </ActionButton>
                    <ActionButton busy={busy === `inst:${inst.id}`} onClick={() => decideInstallation(inst, false)}>
                      Reject
                    </ActionButton>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <SectionCard
        title="Reviews"
        action={
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            {reviews.length} review{reviews.length === 1 ? "" : "s"}
          </span>
        }
      >
        {reviews.length > 0 && (
          <ul className="mb-3 divide-y divide-zinc-100 dark:divide-zinc-800">
            {reviews.map((rv, i) => {
              const r = rv as Record<string, unknown>;
              return (
                <li key={i} className="py-2">
                  <p className="text-sm text-zinc-700 dark:text-zinc-300">
                    {"★".repeat(Number(r.rating) || 0) || "no rating"}{" "}
                    <span className="text-xs text-zinc-400">
                      · {String(r.reviewer_id ?? r.reviewer ?? "").slice(0, 8)}
                    </span>
                  </p>
                  {typeof r.comment === "string" && <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">{r.comment}</p>}
                </li>
              );
            })}
          </ul>
        )}
        <div className="grid gap-2 sm:grid-cols-[8rem_1fr]">
          <input
            type="number" min={1} max={5}
            value={rating}
            onChange={(e) => setRating(e.target.value)}
            className={INPUT_CLASS}
          />
          <input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Review comment"
            className={INPUT_CLASS}
          />
        </div>
        <div className="mt-2">
          <ActionButton busy={busy === "review"} disabled={!comment.trim()} onClick={submitReview}>
            Add review
          </ActionButton>
        </div>
      </SectionCard>

      <SectionCard title="Package record">
        <JsonBlock
          value={{
            id: pkg.id,
            name: pkg.name,
            status: pkg.status,
            security: pkg.security,
            capabilities: capKeys,
          }}
        />
      </SectionCard>
    </div>
  );
}