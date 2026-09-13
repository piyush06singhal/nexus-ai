"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  createAgentPackage,
  deprecateAgentPackage,
  fetchAgentPackages,
  publishAgentPackage,
  scanMarketplace,
} from "@/lib/api";
import type { AgentPackagePublic } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { usePhase12 } from "@/components/phase12/Phase12Shell";
import { ActionButton, SectionCard } from "@/components/phase12/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

const SCURITY_LEVELS = ["public", "internal", "confidential", "restricted"] as const;

const INPUT_CLASS =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";
const SELECT_CLASS =
  "rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

export default function MarketplacePage() {
  const { companyId } = usePhase12();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [packages, setPackages] = useState<AgentPackagePublic[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // create form
  const [name, setName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [capabilities, setCapabilities] = useState("");
  const [skills, setSkills] = useState("");
  const [taskTypes, setTaskTypes] = useState("");
  const [security, setSecurity] = useState("internal");
  const [requirementsText, setRequirementsText] = useState("");
  const [version, setVersion] = useState("");
  const [changelog, setChangelog] = useState("");

  function load() {
    if (!companyId) return;
    fetchAgentPackages({ companyId })
      .then((list) => {
        setError(null);
        setPackages(list);
        setState({ kind: "ok" });
      })
      .catch((err: unknown) => {
        setState({
          kind: "error",
          message:
            err instanceof Error ? err.message : "Failed to load packages",
        });
      });
  }

  useEffect(() => {
    if (!companyId) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  async function doScan() {
    setBusy("scan");
    setError(null);
    setDone(null);
    try {
      const out = await scanMarketplace();
      setDone(
        `Marketplace scan recorded: ${out.scanned ?? ""} ${out.message ?? ""}`.trim() ||
          "Marketplace scan recorded.",
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setBusy(null);
    }
  }

  async function publish(pkg: AgentPackagePublic) {
    const ok = window.confirm(
      `Publish "${pkg.display_name ?? pkg.name}"?\n\nPublishing makes the package visible to internal installers. It does NOT install it anywhere.`,
    );
    if (!ok) return;
    setBusy(`pub:${pkg.id}`);
    setError(null);
    setDone(null);
    try {
      const updated = await publishAgentPackage(pkg.id);
      setDone(`"${updated.name}" → ${updated.status}.`);
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Publish failed");
    } finally {
      setBusy(null);
    }
  }

  async function deprecate(pkg: AgentPackagePublic) {
    const ok = window.confirm(
      `Deprecate "${pkg.display_name ?? pkg.name}"?\n\nDeprecating stops new installs. Installed agents are unchanged.`,
    );
    if (!ok) return;
    setBusy(`dep:${pkg.id}`);
    setError(null);
    setDone(null);
    try {
      const updated = await deprecateAgentPackage(pkg.id);
      setDone(`"${updated.name}" → ${updated.status}.`);
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Deprecate failed");
    } finally {
      setBusy(null);
    }
  }

  async function createPackage() {
    if (!companyId) {
      setError("Select a company first.");
      return;
    }
    if (!name.trim()) {
      setError("Give the package a name.");
      return;
    }
    const cap = capabilities.split(",").map((c) => c.trim()).filter(Boolean);
    const sk = skills.split(",").map((s) => s.trim()).filter(Boolean);
    const tt = taskTypes.split(",").map((t) => t.trim()).filter(Boolean);
    if (cap.length === 0) {
      setError("List at least one capability.");
      return;
    }
    if (version.trim() && !/^\d+\.\d+\.\d+$/.test(version.trim())) {
      setError("Initial version must look like major.minor.patch (e.g. 1.0.0).");
      return;
    }
    let requirements: Record<string, unknown> | null = null;
    if (requirementsText.trim()) {
      try {
        requirements = JSON.parse(requirementsText);
      } catch {
        setError("Requirements JSON is invalid.");
        return;
      }
    }
    const input = {
      company_id: companyId,
      name: name.trim(),
      display_name: displayName.trim() || null,
      description: description.trim() || null,
      capabilities: cap,
      skills: sk,
      supported_task_types: tt,
      requirements,
      security,
      version:
        capabilities.length > 0 && version.trim()
          ? { version: version.trim(), changelog: changelog.trim() || null }
          : null,
    };
    setBusy("create");
    setError(null);
    setDone(null);
    try {
      const created = await createAgentPackage(input);
      setDone(`Package "${created.name}" created → ${created.status}.`);
      setName("");
      setDisplayName("");
      setDescription("");
      setCapabilities("");
      setSkills("");
      setTaskTypes("");
      setRequirementsText("");
      setVersion("");
      setChangelog("");
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create package");
    } finally {
      setBusy(null);
    }
  }

  if (!companyId) {
    return (
      <p className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
        Select a company in the top bar to browse and publish agent packages.
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
        The marketplace is <strong>internal and metadata-only</strong>: packages
        carry capabilities, requirements, and benchmark evidence — never
        credentials, secrets, memories, or executable payloads. Installing
        creates a governed agent and can require approval; it never replaces a
        production agent silently.
      </p>

      <SectionCard
        title="Publish a new agent package"
        action={
          <div className="flex items-center gap-2">
            <ActionButton busy={busy === "scan"} onClick={doScan}>
              Scan marketplace
            </ActionButton>
            <ActionButton
              busy={busy === "create"}
              disabled={!companyId || !name.trim()}
              onClick={createPackage}
            >
              Create package
            </ActionButton>
          </div>
        }
      >
        <div className="space-y-3 text-sm">
          <div className="grid gap-2 sm:grid-cols-2">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="name (e.g. research-analyst-pro)" className={INPUT_CLASS} />
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="display name" className={INPUT_CLASS} />
          </div>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description (metadata only)" rows={2} className={INPUT_CLASS} />
          <div className="grid gap-2 sm:grid-cols-2">
            <input value={capabilities} onChange={(e) => setCapabilities(e.target.value)} placeholder="capabilities (comma-separated)" className={INPUT_CLASS} />
            <input value={skills} onChange={(e) => setSkills(e.target.value)} placeholder="skills (comma-separated)" className={INPUT_CLASS} />
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <input value={taskTypes} onChange={(e) => setTaskTypes(e.target.value)} placeholder="supported task types (comma-separated)" className={INPUT_CLASS} />
            <select value={security} onChange={(e) => setSecurity(e.target.value)} className={SELECT_CLASS}>
              {SCURITY_LEVELS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <textarea value={requirementsText} onChange={(e) => setRequirementsText(e.target.value)} placeholder={'Requirements JSON (optional), e.g. {"tools": ["web_search"]}'} rows={2} className={`${INPUT_CLASS} font-mono text-xs`} />
          <div className="grid gap-2 sm:grid-cols-2">
            <input value={version} onChange={(e) => setVersion(e.target.value)} placeholder="initial version (major.minor.patch)" className={INPUT_CLASS} />
            <input value={changelog} onChange={(e) => setChangelog(e.target.value)} placeholder="changelog (optional)" className={INPUT_CLASS} />
          </div>
        </div>
      </SectionCard>

      <PackageList
        packages={packages}
        busy={busy}
        onPublish={publish}
        onDeprecate={deprecate}
      />
    </div>
  );
}

function PackageList({
  packages,
  busy,
  onPublish,
  onDeprecate,
}: {
  packages: AgentPackagePublic[];
  busy: string | null;
  onPublish: (p: AgentPackagePublic) => void;
  onDeprecate: (p: AgentPackagePublic) => void;
}) {
  return (
    <SectionCard
      title="Packages"
      action={
        <span className="text-xs text-zinc-500 dark:text-zinc-400">
          {packages.length} package{packages.length === 1 ? "" : "s"}
        </span>
      }
    >
      {packages.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          No packages yet. Publish one above.
        </p>
      ) : (
        <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {packages.map((p) => {
            const caps = Object.keys(p.capabilities_json ?? {});
            const skills_ = Object.keys(p.skills_json ?? {});
            return (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link href={`/marketplace/agents/${p.id}`} className="text-sm font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                      {p.display_name ?? p.name}
                    </Link>
                    <StatusBadge status={p.status as never} />
                    <StatusBadge status={p.security as never} />
                  </div>
                  {p.description && (
                    <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">{p.description}</p>
                  )}
                  <p className="mt-0.5 text-xs text-zinc-400">
                    {caps.length} capabilities · {skills_.length} skills
                    {p.published_at ? ` · published ${new Date(p.published_at).toLocaleString()}` : ""}
                    {p.deprecated_at ? ` · deprecated ${new Date(p.deprecated_at).toLocaleString()}` : ""}
                  </p>
                </div>
                <div className="flex items-center gap-1.5">
                  {p.status === "draft" && (
                    <ActionButton busy={busy === `pub:${p.id}`} onClick={() => onPublish(p)}>
                      Publish
                    </ActionButton>
                  )}
                  {p.status === "published" && (
                    <ActionButton busy={busy === `dep:${p.id}`} onClick={() => onDeprecate(p)}>
                      Deprecate
                    </ActionButton>
                  )}
                  <Link
                    href={`/marketplace/agents/${p.id}`}
                    className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
                  >
                    Open
                  </Link>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </SectionCard>
  );
}