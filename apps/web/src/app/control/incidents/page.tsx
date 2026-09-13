"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { createIncident, fetchIncidents } from "@/lib/api";
import type { IncidentPublic } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { ActionButton, Dash, SectionCard } from "../_components/ui";
import { useControl } from "../_components/ControlShell";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

export default function IncidentsPage() {
  const { companyId } = useControl();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [incidents, setIncidents] = useState<IncidentPublic[]>([]);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState("high");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  function load() {
    fetchIncidents({ companyId, limit: 50 })
      .then((rows) => {
        setIncidents(rows);
        setState({ kind: "ok" });
      })
      .catch((err: unknown) => {
        setState({
          kind: "error",
          message:
            err instanceof Error ? err.message : "Failed to load incidents",
        });
      });
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  async function create() {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const created = await createIncident({
        title: title.trim(),
        description: description.trim() || null,
        severity,
        company_id: companyId ?? undefined,
      });
      setDone(`Incident created: ${created.title}`);
      setTitle("");
      setDescription("");
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create incident");
    } finally {
      setBusy(false);
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

  const openCount = incidents.filter(
    (i) => i.status !== "resolved" && i.status !== "closed",
  ).length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          {openCount} open · {incidents.length} total
        </p>
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          Lifecycle: detected → investigating → contained → resolved → closed
        </p>
      </div>

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

      <SectionCard title="Open a new incident">
        <div className="space-y-2">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title (e.g. Repeated cross-company access attempt)"
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description"
            rows={2}
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
              className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            >
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
              <option value="critical">critical</option>
            </select>
            <ActionButton busy={busy} disabled={!title.trim()} onClick={create}>
              Create incident
            </ActionButton>
            <span className="text-xs text-zinc-500 dark:text-zinc-400">
              {companyId ? `company-scoped (${companyId})` : "global scope"}
            </span>
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Incidents">
        {incidents.length === 0 ? (
          <p className="text-sm text-zinc-500">No incidents.</p>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {incidents.map((i) => (
              <li key={i.id} className="py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge
                      status={
                        i.severity === "critical"
                          ? "critical"
                          : i.severity === "high"
                            ? "high"
                            : i.severity === "medium"
                              ? "medium"
                              : "low"
                      }
                    />
                    <Link
                      href={`/control/incidents/${i.id}`}
                      className="text-sm font-medium text-zinc-900 hover:underline dark:text-zinc-100"
                    >
                      {i.title}
                    </Link>
                    <StatusBadge
                      status={
                        i.status as
                          | "detected"
                          | "investigating"
                          | "contained"
                          | "resolved"
                          | "closed"
                      }
                    />
                  </div>
                  <span className="text-xs text-zinc-500 dark:text-zinc-400">
                    {new Date(i.created_at).toLocaleString()}
                  </span>
                </div>
                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                  <Dash value={i.description} />
                  {i.company_id ? ` · company ${i.company_id}` : ""}
                </p>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}