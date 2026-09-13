"use client";

import { useEffect, useState } from "react";
import {
  acknowledgeSecurityAlert,
  fetchSecurityAlerts,
  fetchSecurityEvents,
  resolveSecurityAlert,
} from "@/lib/api";
import type {
  SecurityAlertPublic,
  SecurityEventPublic,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { ActionButton, Dash, JsonBlock, SectionCard } from "../_components/ui";
import { useControl } from "../_components/ControlShell";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

const CATEGORIES = [
  "auth_failure",
  "token_invalid",
  "permission_denied",
  "policy_denied",
  "cross_company_access",
  "prompt_injection",
  "ssrf_blocked",
  "external_action_suspicious",
  "resource_exceeded",
  "rate_limit_exceeded",
  "secret_access_denied",
  "data_exfiltration_blocked",
  "scanner_suspected",
] as const;

export default function SecurityPage() {
  const { companyId } = useControl();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [events, setEvents] = useState<SecurityEventPublic[]>([]);
  const [alerts, setAlerts] = useState<SecurityAlertPublic[]>([]);
  const [category, setCategory] = useState<string>("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const categoryLabel = category === "" ? null : category;

  function load() {
    Promise.all([
      fetchSecurityEvents({ category: categoryLabel, companyId, limit: 50 }),
      fetchSecurityAlerts({ companyId }),
    ])
      .then(([ev, al]) => {
        setEvents(ev);
        setAlerts(al);
        setState({ kind: "ok" });
      })
      .catch((err: unknown) => {
        setState({
          kind: "error",
          message:
            err instanceof Error ? err.message : "Failed to load security data",
        });
      });
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId, category]);

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

  async function act(fn: () => Promise<unknown>, id: string) {
    setBusy(id);
    setError(null);
    try {
      await fn();
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Alert action failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300">
          {error}
        </p>
      )}

      <SectionCard
        title="Alerts"
        action={
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            {alerts.length} shown
          </span>
        }
      >
        {alerts.length === 0 ? (
          <p className="text-sm text-zinc-500">No security alerts.</p>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {alerts.map((a) => (
              <li
                key={a.id}
                className="flex flex-wrap items-start justify-between gap-3 py-3"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge
                      status={
                        a.severity === "critical"
                          ? "critical"
                          : a.severity === "high"
                            ? "high"
                            : a.severity === "medium"
                              ? "medium"
                              : "low"
                      }
                    />
                    <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                      {a.title}
                    </span>
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
                  </div>
                  <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                    {a.description ?? <Dash value={null} />}
                    {a.rule_code ? ` · rule ${a.rule_code}` : ""}
                    {a.company_id ? ` · company ${a.company_id}` : ""} ·{" "}
                    {new Date(a.created_at).toLocaleString()}
                  </p>
                </div>
                {a.status === "open" ? (
                  <div className="flex shrink-0 gap-2">
                    <ActionButton
                      busy={busy === `ack:${a.id}`}
                      onClick={() =>
                        act(() => acknowledgeSecurityAlert(a.id), `ack:${a.id}`)
                      }
                    >
                      Acknowledge
                    </ActionButton>
                    <ActionButton
                      busy={busy === `res:${a.id}`}
                      onClick={() =>
                        act(() => resolveSecurityAlert(a.id), `res:${a.id}`)
                      }
                    >
                      Resolve
                    </ActionButton>
                  </div>
                ) : (
                  <StatusBadge
                    status={a.status === "resolved" ? "resolved" : "acknowledged"}
                  />
                )}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <SectionCard
        title="Security events"
        action={
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          >
            <option value="">All categories</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        }
      >
        {events.length === 0 ? (
          <p className="text-sm text-zinc-500">No security events recorded.</p>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {events.map((e) => (
              <li key={e.id} className="py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge
                    status={
                      e.severity === "critical"
                        ? "critical"
                        : e.severity === "high"
                          ? "high"
                          : e.severity === "medium"
                            ? "medium"
                            : e.severity === "low"
                              ? "low"
                              : "informational"
                    }
                  />
                  <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                    {e.title}
                  </span>
                  <span className="font-mono text-xs text-zinc-400">
                    {e.category}
                  </span>
                </div>
                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                  <Dash value={e.actor_id} />
                  {e.company_id ? ` · company ${e.company_id}` : ""} ·{" "}
                  {new Date(e.created_at).toLocaleString()}
                </p>
                {e.detail && Object.keys(e.detail).length > 0 && (
                  <JsonBlock value={e.detail} />
                )}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}