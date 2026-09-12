"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchConnections, fetchIntegrations } from "@/lib/api";
import type { ExternalIntegration, IntegrationConnection } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { useExternal } from "../../_components/ExternalShell";
import { Dash, SectionCard, StatCard } from "../../_components/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; rows: { integration: ExternalIntegration; connection: IntegrationConnection }[] }
  | { kind: "error"; message: string };

export default function ConnectionsPage() {
  const { companyId } = useExternal();
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    (async () => {
      try {
        const integrations = await fetchIntegrations(companyId);
        const per = await Promise.all(
          integrations.map(async (i) => {
            const conns = await fetchConnections(companyId, i.id).catch(() => []);
            return conns.map((c) => ({ integration: i, connection: c }));
          }),
        );
        if (!cancelled) setState({ kind: "ok", rows: per.flat() });
      } catch (err) {
        if (!cancelled) {
          setState({
            kind: "error",
            message: err instanceof Error ? err.message : "Failed to load connections",
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [companyId]);

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

  const { rows } = state;
  const connected = rows.filter((r) => r.connection.status === "connected").length;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          Connections
        </h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Credential bindings across your integrations. Secrets are
          reference-only — a connection stores an opaque reference, never the
          secret value.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
        <StatCard label="Total connections" value={rows.length} />
        <StatCard label="Connected" value={connected} />
        <StatCard label="Revoked / error" value={rows.filter((r) => ["revoked", "error"].includes(r.connection.status)).length} />
      </div>

      <SectionCard title="All connections">
        {rows.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No connections yet. Open an integration and connect a credential.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-zinc-200 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
                <tr>
                  <th className="px-2 py-2">Integration</th>
                  <th className="px-2 py-2">Auth</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">Credential ref</th>
                  <th className="px-2 py-2">Scopes</th>
                  <th className="px-2 py-2">Last used</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {rows.map(({ integration, connection }) => (
                  <tr key={connection.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-900/40">
                    <td className="px-2 py-2.5">
                      <Link
                        href={`/integrations/${integration.id}`}
                        className="text-zinc-900 underline-offset-2 hover:underline dark:text-zinc-100"
                      >
                        {integration.name}
                      </Link>
                      <span className="ml-1 text-xs text-zinc-400">{integration.provider}</span>
                    </td>
                    <td className="px-2 py-2.5 text-zinc-600 dark:text-zinc-400">
                      {connection.auth_method}
                    </td>
                    <td className="px-2 py-2.5">
                      <StatusBadge status={connection.status as never} />
                    </td>
                    <td className="px-2 py-2.5">
                      <code className="text-xs text-zinc-600 dark:text-zinc-300">
                        <Dash value={connection.credential_reference} />
                      </code>
                    </td>
                    <td className="px-2 py-2.5 text-zinc-600 dark:text-zinc-400">
                      {Array.isArray(connection.scopes) ? connection.scopes.join(", ") : <Dash value={null} />}
                    </td>
                    <td className="px-2 py-2.5 text-zinc-500">
                      {connection.last_used_at
                        ? new Date(connection.last_used_at).toLocaleString()
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </div>
  );
}