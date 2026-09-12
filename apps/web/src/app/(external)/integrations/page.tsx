"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CheckCircle2 } from "lucide-react";
import {
  approveApprovalGate,
  createIntegration,
  fetchConnections,
  fetchExternalDashboard,
  fetchExternalEvents,
  fetchIntegrations,
  rejectApprovalGate,
} from "@/lib/api";
import type {
  ExternalDashboard,
  ExternalEvent,
  ExternalIntegration,
  IntegrationConnection,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { useExternal } from "../_components/ExternalShell";
import { ActionButton, Dash, SectionCard, StatCard } from "../_components/ui";

const PROVIDERS = [
  { slug: "email", label: "Email", hint: "Mailbox / compose / send" },
  { slug: "calendar", label: "Calendar", hint: "Events & scheduling" },
  { slug: "development", label: "Development", hint: "Repos, issues, comments" },
  { slug: "web_research", label: "Web Research", hint: "Fixture pages & search" },
];

type LoadState =
  | { kind: "loading" }
  | {
      kind: "ok";
      integrations: ExternalIntegration[];
      connects: Record<string, IntegrationConnection[]>;
      events: ExternalEvent[];
      dashboard: ExternalDashboard | null;
    }
  | { kind: "error"; message: string };

export default function IntegrationsDashboardPage() {
  const { companyId } = useExternal();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [provider, setProvider] = useState(PROVIDERS[0].slug);
  const [name, setName] = useState("");

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    Promise.all([
      fetchIntegrations(companyId),
      fetchExternalDashboard(companyId).catch(() => null),
      fetchExternalEvents(companyId).catch(() => []),
      fetchConnectionsForAll(companyId).catch(() => ({})),
    ])
      .then(([integrations, dashboard, events, connects]) => {
        if (!cancelled) setState({ kind: "ok", integrations, connects, events, dashboard });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            kind: "error",
            message: err instanceof Error ? err.message : "Failed to load integrations",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  async function addIntegration() {
    if (!companyId) return;
    setBusy("create");
    setMsg(null);
    try {
      const created = await createIntegration(companyId, {
        provider,
        name: name.trim() || provider,
      });
      setMsg(`Integration ${created.provider} created — connect a credential to use it.`);
      const list = await fetchIntegrations(companyId);
      setState((s) => (s.kind === "ok" ? { ...s, integrations: list } : s));
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Failed to create integration");
    } finally {
      setBusy(null);
    }
  }

  async function decide(gateId: string, decision: "approve" | "reject") {
    if (!companyId) return;
    setBusy(gateId);
    setMsg(null);
    try {
      if (decision === "approve") await approveApprovalGate(companyId, gateId);
      if (decision === "reject") await rejectApprovalGate(companyId, gateId);
      setMsg(
        `External-action gate ${decision}d. Replay the parked action with its approval gate id to execute it once.`,
      );
      const dashboard = await fetchExternalDashboard(companyId).catch(() => null);
      setState((s) => (s.kind === "ok" ? { ...s, dashboard } : s));
    } catch (err) {
      setMsg(err instanceof Error ? err.message : `Failed to ${decision} gate`);
    } finally {
      setBusy(null);
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

  const { integrations, connects, events, dashboard } = state;
  const connected = integrations.filter((i) => i.status === "connected");
  const pending = dashboard?.pending_approvals ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
            Integrations center
          </h2>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            External providers registered as governed integrations. Every
            capability call passes risk → policy → approval → execution →
            verification → audit.
          </p>
        </div>
        <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            Add integration
          </p>
          <div className="flex gap-2">
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            >
              {PROVIDERS.map((p) => (
                <option key={p.slug} value={p.slug}>
                  {p.label}
                </option>
              ))}
            </select>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Display name"
              className="w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            />
            <ActionButton onClick={addIntegration} busy={busy === "create"}>
              Add
            </ActionButton>
          </div>
          <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
            {PROVIDERS.find((p) => p.slug === provider)?.hint}
          </p>
        </div>
      </div>

      {msg && (
        <p className="rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300">
          {msg}
        </p>
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Integrations" value={integrations.length} hint={`${connected.length} connected`} />
        <StatCard label="Total external actions" value={dashboard?.total_actions ?? 0} />
        <StatCard
          label="Success rate"
          value={dashboard ? `${(dashboard.success_rate * 100).toFixed(0)}%` : "—"}
          hint={dashboard ? `${(dashboard.failure_rate * 100).toFixed(0)}% failed` : undefined}
        />
        <StatCard label="Pending approvals" value={pending.length} hint="gates awaiting a human" />
      </div>

      {pending.length > 0 && (
        <SectionCard title={`External-action approvals (${pending.length})`}>
          <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
            A high-risk or approval-required external capability parked at an{" "}
            <span className="text-zinc-700 dark:text-zinc-300">external_action_approval</span> gate.
            Approving authorizes exactly one action, executed once on replay with its gate id.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-zinc-200 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
                <tr>
                  <th className="px-3 py-2">Capability</th>
                  <th className="px-3 py-2">Risk</th>
                  <th className="px-3 py-2">Created</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {pending.map((g) => (
                  <tr key={g.gate_id ?? g.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-900/40">
                    <td className="px-3 py-2.5">
                      <StatusBadge status="external_action_approval" />
                      <span className="ml-2 text-zinc-700 dark:text-zinc-300">{g.capability}</span>
                    </td>
                    <td className="px-3 py-2.5">
                      <StatusBadge status={(g.risk_level as never) ?? "unverified"} />
                    </td>
                    <td className="px-3 py-2.5 text-zinc-600 dark:text-zinc-400">
                      {g.created_at ? new Date(g.created_at).toLocaleString() : "—"}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {g.gate_id ? (
                        <div className="flex justify-end gap-2">
                          <ActionButton
                            onClick={() => g.gate_id && decide(g.gate_id, "approve")}
                            busy={busy === g.gate_id}
                          >
                            Approve
                          </ActionButton>
                          <ActionButton
                            onClick={() => g.gate_id && decide(g.gate_id, "reject")}
                            busy={busy === g.gate_id}
                          >
                            Reject
                          </ActionButton>
                        </div>
                      ) : (
                        <span className="text-xs text-zinc-400">no gate</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      <SectionCard title="Integrations">
        {integrations.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No integrations yet. Add one above, then connect a credential on its
            detail page. Secrets are reference-only — only a masked suffix is
            ever stored or rendered.
          </p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {integrations.map((i) => {
              const conns = connects[i.id] ?? [];
              const active = conns.filter((c) => c.status === "connected").length;
              return (
                <Link
                  key={i.id}
                  href={`/integrations/${i.id}`}
                  className="rounded-xl border border-zinc-200 bg-white p-4 transition hover:border-zinc-300 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:border-zinc-700 dark:hover:bg-zinc-900"
                >
                  <div className="mb-2 flex items-center justify-between">
                    <div>
                      <p className="font-medium text-zinc-900 dark:text-zinc-100">
                        {i.name}
                      </p>
                      <p className="text-xs text-zinc-500 dark:text-zinc-400">
                        {i.provider} · {i.category}
                      </p>
                    </div>
                    <StatusBadge status={i.status as never} />
                  </div>
                  <p className="mb-3 min-h-8 text-sm text-zinc-600 dark:text-zinc-400">
                    <Dash value={i.description} />
                  </p>
                  <div className="flex items-center gap-3 text-xs text-zinc-500 dark:text-zinc-400">
                    <span className="inline-flex items-center gap-1">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                      {active} connected
                    </span>
                    <span>· {conns.length} total</span>
                    <span>· auth {i.auth_type}</span>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </SectionCard>

      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard title="Recent external events">
          {events.length === 0 ? (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">No external events yet.</p>
          ) : (
            <ul className="space-y-2">
              {events.slice(0, 8).map((e) => (
                <li key={e.id} className="flex items-center justify-between gap-2 text-sm">
                  <span className="min-w-0 truncate text-zinc-700 dark:text-zinc-300">
                    <StatusBadge status={e.verification_status as never} />
                    <span className="ml-2">
                      {e.source} · {e.event_type}
                    </span>
                  </span>
                  <span className="shrink-0 text-xs text-zinc-400">
                    {e.received_at ? new Date(e.received_at).toLocaleString() : "—"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
        <SectionCard title="Governance help">
          <ul className="space-y-2 text-sm text-zinc-600 dark:text-zinc-400">
            <li>
              · Integrations are company-scoped; other companies cannot read
              your integrations or actions.
            </li>
            <li>
              · External content is untrusted by default and never treated as an
              instruction (§20/§65).
            </li>
            <li>
              · High/irreversible capabilities always require an approval gate,
              even with an allow matrix.
            </li>
            <li>
              · Idempotency keys block duplicate external effects; each approved
              gate authorizes exactly one action once.
            </li>
          </ul>
        </SectionCard>
      </div>
    </div>
  );
}

/** Fetch connections for every integration in parallel (tolerates 404/empty). */
async function fetchConnectionsForAll(
  companyId: string,
): Promise<Record<string, IntegrationConnection[]>> {
  const integrations = await fetchIntegrations(companyId);
  const entries = await Promise.all(
    integrations.map(async (i) => {
      const conns = await fetchConnections(companyId, i.id).catch(
        () => [] as IntegrationConnection[],
      );
      return [i.id, conns] as const;
    }),
  );
  return Object.fromEntries(entries);
}