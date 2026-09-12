"use client";

import { useEffect, useState } from "react";
import { fetchExternalEvents } from "@/lib/api";
import type { ExternalEvent } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { useExternal } from "../../_components/ExternalShell";
import { Dash, JsonBlock, SectionCard, StatCard } from "../../_components/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; events: ExternalEvent[] }
  | { kind: "error"; message: string };

export default function ExternalEventsPage() {
  const { companyId } = useExternal();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    fetchExternalEvents(companyId)
      .then((events) => {
        if (!cancelled) setState({ kind: "ok", events });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            kind: "error",
            message: err instanceof Error ? err.message : "Failed to load external events",
          });
        }
      });
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

  const { events } = state;
  const verified = events.filter((e) => e.verification_status === "verified").length;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          External events
        </h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Normalized events ingressed from external sources. Unauthenticated
          payloads are never trusted commands — they are verified, deduped, and
          journaled only.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Events" value={events.length} />
        <StatCard label="Verified" value={verified} hint="verification_status = verified" />
        <StatCard
          label="Signature OK"
          value={events.filter((e) => e.signature_status === "signature_ok").length}
        />
        <StatCard label="Deduped ingests" value={events.filter((e) => e.ingest_id).length} />
      </div>

      <SectionCard title="Event feed">
        {events.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No external events yet. Events arrive via webhooks or the external
            action funnel.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-zinc-200 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
                <tr>
                  <th className="px-2 py-2">Source</th>
                  <th className="px-2 py-2">Type</th>
                  <th className="px-2 py-2">Verification</th>
                  <th className="px-2 py-2">Signature</th>
                  <th className="px-2 py-2">Size</th>
                  <th className="px-2 py-2">Received</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {events.map((e) => (
                  <tr
                    key={e.id}
                    onClick={() => setExpanded(expanded === e.id ? null : e.id)}
                    className="cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-900/40"
                  >
                    <td className="px-2 py-2.5 font-mono text-zinc-900 dark:text-zinc-100">
                      {e.source}
                    </td>
                    <td className="px-2 py-2.5">{e.event_type}</td>
                    <td className="px-2 py-2.5">
                      <StatusBadge status={e.verification_status as never} />
                    </td>
                    <td className="px-2 py-2.5">
                      <StatusBadge status={e.signature_status as never} />
                    </td>
                    <td className="px-2 py-2.5 text-zinc-600 dark:text-zinc-400">
                      {e.payload_size} b
                    </td>
                    <td className="px-2 py-2.5 text-zinc-500">
                      {e.received_at ? new Date(e.received_at).toLocaleString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {state.kind === "ok" && expanded && (
        <SectionCard title="Event detail">
          {(() => {
            const e = state.events.find((x) => x.id === expanded);
            if (!e) return <p className="text-sm text-zinc-500">Event not found.</p>;
            return (
              <div className="space-y-2">
                <p className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="text-zinc-500">correlation:</span>{" "}
                  <Dash value={e.correlation_id} />{" "}
                  <span className="text-zinc-500">ingest:</span>{" "}
                  <Dash value={e.ingest_id} />
                </p>
                <JsonBlock value={e.payload} />
              </div>
            );
          })()}
        </SectionCard>
      )}
    </div>
  );
}