"use client";

import { useEffect, useState } from "react";
import { fetchAuditEvents, verifyAuditChain } from "@/lib/api";
import type { AuditChainVerify, AuditEventPublic } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { ActionButton, Dash, JsonBlock, SectionCard } from "../_components/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

export default function AuditPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [events, setEvents] = useState<AuditEventPublic[]>([]);
  const [chain, setChain] = useState<AuditChainVerify | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);

  function load() {
    Promise.all([fetchAuditEvents({ limit: 100 }), verifyAuditChain()])
      .then(([eventsList, chainResult]) => {
        setEvents(eventsList);
        setChain(chainResult);
        setState({ kind: "ok" });
      })
      .catch((err: unknown) => {
        setState({
          kind: "error",
          message:
            err instanceof Error ? err.message : "Failed to load audit trail",
        });
      });
  }

  useEffect(() => {
    load();
  }, []);

  async function reverify() {
    setVerifying(true);
    setError(null);
    try {
      setChain(await verifyAuditChain());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Verify failed");
    } finally {
      setVerifying(false);
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

  return (
    <div className="space-y-6">
      <SectionCard
        title="Chain integrity"
        action={
          chain ? (
            <StatusBadge status={chain.verified ? "pass" : "fail"} />
          ) : null
        }
      >
        {chain ? (
          <div className="flex flex-wrap items-center gap-4 text-sm">
            <p className="text-zinc-600 dark:text-zinc-400">
              <strong className="text-zinc-900 dark:text-zinc-100">
                {chain.checked}
              </strong>{" "}
              events hashed·linked
            </p>
            <p className="text-zinc-600 dark:text-zinc-400">
              First gap:{" "}
              <strong className="text-zinc-900 dark:text-zinc-100">
                <Dash value={chain.first_gap_at_seq} />
              </strong>
            </p>
            <ActionButton busy={verifying} onClick={reverify}>
              Re-verify
            </ActionButton>
          </div>
        ) : (
          <p className="text-sm text-zinc-500">No audit events yet.</p>
        )}
      </SectionCard>

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300">
          {error}
        </p>
      )}

      <SectionCard title="Audit events (append-only, hash-chained)">
        {events.length === 0 ? (
          <p className="text-sm text-zinc-500">
            No audit events recorded. Append-only — nothing here can be edited
            or deleted.
          </p>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {events.map((e) => (
              <li key={e.id} className="py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="w-10 shrink-0 font-mono text-xs text-zinc-400">
                    #{e.seq}
                  </span>
                  <StatusBadge
                    status={
                      e.outcome === "success"
                        ? "pass"
                        : e.outcome === "failure"
                          ? "fail"
                          : e.outcome === "denied"
                            ? "blocked"
                            : e.outcome === "require_approval"
                              ? "pending"
                              : "unknown"
                    }
                  />
                  <span className="font-mono text-xs text-zinc-700 dark:text-zinc-300">
                    {e.action}
                  </span>
                  <span className="text-xs text-zinc-500 dark:text-zinc-400">
                    {new Date(e.created_at).toLocaleString()}
                  </span>
                </div>
                <p className="mt-1 truncate text-xs text-zinc-500 dark:text-zinc-400">
                  actor <Dash value={e.actor_name ?? e.actor_id} />
                  {e.company_id ? ` · company ${e.company_id}` : ""}
                  {e.resource_type ? ` · ${e.resource_type}` : ""}
                  {e.policy_result ? ` · policy=${e.policy_result}` : ""}
                </p>
                <p className="mt-1 break-all font-mono text-[10px] text-zinc-400 dark:text-zinc-500">
                  prev {e.prev_hash ? `${e.prev_hash.slice(0, 16)}…` : "—"} →{" "}
                  {e.hash.slice(0, 16)}…
                </p>
                {e.detail && <JsonBlock value={e.detail} />}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}