"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  createConnection,
  fetchCapabilities,
  fetchConnections,
  fetchExternalActions,
  fetchIntegration,
  revokeConnection,
  testConnection,
} from "@/lib/api";
import type {
  ExternalAction,
  ExternalIntegration,
  IntegrationCapability,
  IntegrationConnection,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { useExternal } from "../../_components/ExternalShell";
import { ActionButton, DetailCard, SectionCard } from "../../_components/ui";

type LoadState =
  | { kind: "loading" }
  | {
      kind: "ok";
      integration: ExternalIntegration;
      capabilities: IntegrationCapability[];
      connections: IntegrationConnection[];
      actions: ExternalAction[];
    }
  | { kind: "error"; message: string };

export default function IntegrationDetailPage() {
  const { companyId } = useExternal();
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [authMethod, setAuthMethod] = useState("api_key");
  const [secretValue, setSecretValue] = useState("");
  const [envHint, setEnvHint] = useState("");

  useEffect(() => {
    if (!companyId || !id) return;
    let cancelled = false;
    Promise.all([
      fetchIntegration(companyId, id),
      fetchCapabilities(companyId, id),
      fetchConnections(companyId, id),
      fetchExternalActions(companyId).catch(() => []),
    ])
      .then(([integration, capabilities, connections, allActions]) => {
        if (cancelled) return;
        setState({
          kind: "ok",
          integration,
          capabilities,
          connections,
          actions: allActions.filter((a) => a.integration_id === id),
        });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            kind: "error",
            message: err instanceof Error ? err.message : "Failed to load integration",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [companyId, id]);

  async function connect() {
    if (!companyId || !id) return;
    setBusy("connect");
    setMsg(null);
    const secret_value = secretValue.trim() || undefined;
    const env_var_hint = envHint.trim() || undefined;
    if (!secret_value && !env_var_hint) {
      setMsg("Provide a one-shot secret value or an INTEGRATION_*_SECRET env var hint.");
      return;
    }
    try {
      await createConnection(companyId, id, {
        auth_method: authMethod,
        secret_value,
        env_var_hint,
        scopes: ["email:send"],
        permissions: ["email:send"],
      });
      setMsg("Connection created. Only a masked reference is stored — the secret itself is discarded.");
      const connections = await fetchConnections(companyId, id).catch(() => []);
      setState((s) => (s.kind === "ok" ? { ...s, connections } : s));
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Failed to connect");
    } finally {
      setBusy(null);
    }
  }

  async function test(connId: string) {
    if (!companyId || !id) return;
    setBusy(`test-${connId}`);
    setMsg(null);
    try {
      const r = await testConnection(companyId, id, connId);
      setMsg(`${r.result}: ${r.message ?? "ok"}`);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Test failed");
    } finally {
      setBusy(null);
    }
  }

  async function revoke(connId: string) {
    if (!companyId || !id) return;
    setBusy(`revoke-${connId}`);
    setMsg(null);
    try {
      await revokeConnection(companyId, id, connId);
      const connections = await fetchConnections(companyId, id).catch(() => []);
      setState((s) => (s.kind === "ok" ? { ...s, connections } : s));
      setMsg("Connection revoked.");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Failed to revoke");
    } finally {
      setBusy(null);
    }
  }

  if (!companyId || !id) return null;
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

  const { integration, capabilities, connections, actions } = state;

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/integrations"
          className="text-xs text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
        >
          ← Integrations
        </Link>
        <h2 className="mt-1 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          {integration.name} <StatusBadge status={integration.status as never} />
        </h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          {integration.provider} · {integration.category} · {integration.slug}
        </p>
      </div>

      {msg && (
        <p className="rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300">
          {msg}
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <SectionCard title={`Capabilities (${capabilities.length})`}>
            {capabilities.length === 0 ? (
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                No capabilities materialized from this provider.
              </p>
            ) : (
              <div className="space-y-3">
                {capabilities.map((c) => (
                  <div
                    key={c.id}
                    className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800"
                  >
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span className="font-mono text-sm text-zinc-900 dark:text-zinc-100">
                        {c.name}
                      </span>
                      <StatusBadge status={c.risk_level} />
                      <StatusBadge status={c.reversibility as never} />
                      {c.approval_required && <StatusBadge status="external_action_approval" />}
                    </div>
                    <p className="text-sm text-zinc-600 dark:text-zinc-400">{c.description}</p>
                    <div className="mt-1 flex flex-wrap gap-3 text-xs text-zinc-500 dark:text-zinc-400">
                      <span>type: {c.capability_type}</span>
                      <span>idempotent: {c.supports_idempotency ? "yes" : "no"}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </SectionCard>

          <SectionCard title="Connections">
            {connections.length === 0 && (
              <p className="mb-3 text-sm text-zinc-500 dark:text-zinc-400">
                No connections yet. Connect on the right — a one-shot secret or
                an env var hint; only the masked reference is persisted.
              </p>
            )}
            <div className="space-y-3">
              {connections.map((c) => (
                <div
                  key={c.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-zinc-200 p-3 dark:border-zinc-800"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                        {c.auth_method}
                      </span>
                      <StatusBadge status={c.status as never} />
                    </div>
                    <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
                      ref{" "}
                      <code className="text-zinc-600 dark:text-zinc-300">
                        {c.credential_reference}
                      </code>
                      {c.last_tested_at
                        ? ` · tested ${new Date(c.last_tested_at).toLocaleString()}`
                        : " · never tested"}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <ActionButton onClick={() => test(c.id)} busy={busy === `test-${c.id}`}>
                      Test
                    </ActionButton>
                    <ActionButton onClick={() => revoke(c.id)} busy={busy === `revoke-${c.id}`}>
                      Revoke
                    </ActionButton>
                  </div>
                </div>
              ))}
            </div>
          </SectionCard>

          <SectionCard title="Latest actions">
            {actions.length === 0 ? (
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                No external actions through this integration yet. Create one from
                the journal or a workflow step.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-zinc-200 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
                    <tr>
                      <th className="px-2 py-2">Capability</th>
                      <th className="px-2 py-2">Risk</th>
                      <th className="px-2 py-2">Status</th>
                      <th className="px-2 py-2">Approval</th>
                      <th className="px-2 py-2">When</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                    {actions.slice(0, 10).map((a) => (
                      <tr key={a.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-900/40">
                        <td className="px-2 py-2">{a.capability}</td>
                        <td className="px-2 py-2">
                          <StatusBadge status={a.risk_level} />
                        </td>
                        <td className="px-2 py-2">
                          <StatusBadge status={a.status as never} />
                        </td>
                        <td className="px-2 py-2">
                          {a.approval_status ? (
                            <StatusBadge status={a.approval_status as never} />
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="px-2 py-2 text-zinc-500">
                          {a.created_at ? new Date(a.created_at).toLocaleString() : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </SectionCard>
        </div>

        <div className="space-y-4">
          <DetailCard
            title="Details"
            rows={[
              { k: "Provider", v: integration.provider },
              { k: "Category", v: integration.category },
              { k: "Auth", v: integration.auth_type },
              { k: "Status", v: <StatusBadge status={integration.status as never} /> },
              {
                k: "Created",
                v: integration.created_at
                  ? new Date(integration.created_at).toLocaleString()
                  : "—",
              },
            ]}
          />

          <SectionCard title="Connect">
            <label className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">
              Auth method
            </label>
            <select
              value={authMethod}
              onChange={(e) => setAuthMethod(e.target.value)}
              className="mb-3 w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            >
              <option value="api_key">API key</option>
              <option value="basic">Basic auth</option>
              <option value="oauth">OAuth (mock)</option>
              <option value="none">None (public)</option>
            </select>
            <label className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">
              Operator env-var hint (e.g. INTEGRATION_EMAIL_API_KEY)
            </label>
            <input
              value={envHint}
              onChange={(e) => setEnvHint(e.target.value)}
              placeholder="INTEGRATION_*_SECRET"
              className="mb-3 w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            />
            <label className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">
              One-shot secret value (used once, never stored)
            </label>
            <input
              value={secretValue}
              onChange={(e) => setSecretValue(e.target.value)}
              placeholder="dev-only secret"
              type="password"
              className="mb-3 w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            />
            <ActionButton onClick={connect} busy={busy === "connect"}>
              Connect
            </ActionButton>
          </SectionCard>
        </div>
      </div>
    </div>
  );
}