"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  executeIncidentAction,
  fetchIncident,
  transitionIncident,
} from "@/lib/api";
import type {
  IncidentActionPublic,
  IncidentDetailPublic,
  IncidentTransitionInput,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { ActionButton, Dash, JsonBlock, SectionCard } from "../../_components/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; incident: IncidentDetailPublic }
  | { kind: "error"; message: string };

/** Incident transition states available from each lifecycle status. */
const TRANSITIONS: { to: string; label: string }[] = [
  { to: "investigating", label: "Start investigation" },
  { to: "contained", label: "Contain" },
  { to: "resolved", label: "Resolve" },
  { to: "closed", label: "Close" },
];

/** Audited containment actions (§85). */
const ACTIONS = [
  {
    code: "pause_company",
    label: "Pause company",
    hint: "Scoped kill switch on the incident company",
  },
  {
    code: "disable_external_actions",
    label: "Disable external actions",
    hint: "Pause the external-action scope for the company",
  },
  {
    code: "disable_agent",
    label: "Disable agent",
    hint: "Suspends the agent identity (target_ref: NEXUS agent id)",
  },
  {
    code: "suspend_employee",
    label: "Suspend employee",
    hint: "Suspends the employee identity (target_ref: NEXUS employee id)",
  },
  {
    code: "disable_integration",
    label: "Disable integration",
    hint: "Revokes access to an external integration (target_ref)",
  },
  {
    code: "revoke_credential",
    label: "Revoke credential",
    hint: "Rotates/revokes a stored credential (target_ref: secret name)",
  },
  {
    code: "terminate_browser_session",
    label: "Terminate browser session",
    hint: "Ends a browser session (target_ref: session id)",
  },
  {
    code: "terminate_computer_session",
    label: "Terminate computer session",
    hint: "Ends a computer session (target_ref: session id)",
  },
];

export default function IncidentDetailPage() {
  const params = useParams<{ id: string }>();
  const incidentId = params.id;

  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [targetRef, setTargetRef] = useState("");
  const [actionCode, setActionCode] = useState(ACTIONS[0].code);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  function load() {
    fetchIncident(incidentId)
      .then((incident) => {
        setError(null);
        setState({ kind: "ok", incident });
      })
      .catch((err: unknown) => {
        setState({
          kind: "error",
          message:
            err instanceof Error ? err.message : "Failed to load incident",
        });
      });
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incidentId]);

  async function transition(to: string) {
    if (state.kind !== "ok") return;
    setBusy(`t:${to}`);
    setError(null);
    setDone(null);
    try {
      const input: IncidentTransitionInput = {
        to_status: to,
        note: note.trim() || null,
      };
      await transitionIncident(state.incident.id, input);
      setDone(`Transitioned to "${to}".`);
      setNote("");
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Transition failed");
    } finally {
      setBusy(null);
    }
  }

  async function runAction() {
    if (state.kind !== "ok") return;
    setBusy(`a:${actionCode}`);
    setError(null);
    setDone(null);
    try {
      await executeIncidentAction(state.incident.id, {
        incident_id: state.incident.id,
        action: actionCode,
        params: {
          company_id: state.incident.company_id ?? undefined,
          rationale: note.trim() || undefined,
          ...(targetRef.trim() ? { target_ref: targetRef.trim() } : {}),
        },
      });
      setDone(`Incident action applied and audited.`);
      setTargetRef("");
      setNote("");
      load();
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Incident action failed",
      );
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

  const { incident } = state;
  const actions = incident.actions ?? [];
  const alerts = incident.alerts ?? [];
  const timeline: Record<string, unknown>[] = Array.isArray(
    incident.timeline_json,
  )
    ? (incident.timeline_json as Record<string, unknown>[])
    : [];

  return (
    <div className="space-y-6">
      <Link
        href="/control/incidents"
        className="text-xs text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
      >
        ← All incidents
      </Link>

      <div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge
            status={
              incident.severity === "critical"
                ? "critical"
                : incident.severity === "high"
                  ? "high"
                  : incident.severity === "medium"
                    ? "medium"
                    : "low"
            }
          />
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
            {incident.title}
          </h1>
          <StatusBadge
            status={
              incident.status as
                | "detected"
                | "investigating"
                | "contained"
                | "resolved"
                | "closed"
            }
          />
        </div>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          <Dash value={incident.description} />
          {incident.company_id ? ` · company ${incident.company_id}` : ""} ·
          opened {new Date(incident.created_at).toLocaleString()}
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

      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard title="Lifecycle">
          <div className="flex flex-wrap items-center gap-2">
            {TRANSITIONS.map((t) => (
              <ActionButton
                key={t.to}
                busy={busy === `t:${t.to}`}
                disabled={t.to === incident.status}
                onClick={() => transition(t.to)}
              >
                {t.label}
              </ActionButton>
            ))}
          </div>
          <label className="mt-3 block">
            <span className="mb-1 block text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Note (recorded on transition)
            </span>
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            />
          </label>
        </SectionCard>

        <SectionCard title="Containment actions (audited)">
          <div className="space-y-2">
            <select
              value={actionCode}
              onChange={(e) => setActionCode(e.target.value)}
              className="w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            >
              {ACTIONS.map((a) => (
                <option key={a.code} value={a.code}>
                  {a.label} — {a.hint}
                </option>
              ))}
            </select>
            <input
              value={targetRef}
              onChange={(e) => setTargetRef(e.target.value)}
              placeholder="target_ref (e.g. agent/employee/session id)"
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            />
            <ActionButton busy={busy === `a:${actionCode}`} onClick={runAction}>
              Execute {ACTIONS.find((a) => a.code === actionCode)?.label}
            </ActionButton>
          </div>
        </SectionCard>
      </div>

      <SectionCard title="Action history">
        {actions.length === 0 ? (
          <p className="text-sm text-zinc-500">No containment actions yet.</p>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {actions.map((a: IncidentActionPublic) => (
              <li key={a.id} className="py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-zinc-700 dark:text-zinc-300">
                    {a.action_code}
                  </span>
                  <StatusBadge
                    status={
                      a.state === "applied"
                        ? "applied"
                        : a.state === "reverted"
                          ? "reverted"
                          : a.state === "failed"
                            ? "failed"
                            : "pending"
                    }
                  />
                  <span className="text-xs text-zinc-500 dark:text-zinc-400">
                    {new Date(a.created_at).toLocaleString()}
                  </span>
                </div>
                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                  by <Dash value={a.performed_by} />
                  {a.target_ref ? ` · ${a.target_ref}` : ""}
                </p>
                {a.result_json && <JsonBlock value={a.result_json} />}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      {alerts.length > 0 && (
        <SectionCard title="Linked alerts">
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {alerts.map((a) => (
              <li
                key={a.id}
                className="flex items-start justify-between gap-3 py-2"
              >
                <div>
                  <p className="text-sm text-zinc-900 dark:text-zinc-100">
                    {a.title}
                  </p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {a.severity} · {a.status}
                  </p>
                </div>
                <StatusBadge
                  status={
                    a.status === "open"
                      ? "open"
                      : a.status === "escalated"
                        ? "escalated"
                        : a.status === "acknowledged"
                          ? "acknowledged"
                          : "resolved"
                  }
                />
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      {timeline.length > 0 && (
        <SectionCard title="Timeline">
          <ul className="space-y-1">
            {timeline.map((entry, idx) => (
              <li
                key={idx}
                className="flex items-start justify-between gap-3 text-xs text-zinc-600 dark:text-zinc-400"
              >
                <span>
                  {String(
                    entry.status ?? entry.action ?? entry.event ?? "",
                  )}
                </span>
                <span className="shrink-0 text-zinc-400">
                  <Dash
                    value={
                      entry.at == null ? null : String(entry.at)
                    }
                  />
                </span>
              </li>
            ))}
          </ul>
        </SectionCard>
      )}
    </div>
  );
}