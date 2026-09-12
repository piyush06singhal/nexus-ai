"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { createComputerSession, fetchComputerSessions } from "@/lib/api";
import type { ComputerSession } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { useExternal } from "../_components/ExternalShell";
import { ActionButton, SectionCard, StatCard } from "../_components/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; sessions: ComputerSession[] }
  | { kind: "error"; message: string };

export default function ComputerCenterPage() {
  const { companyId } = useExternal();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    fetchComputerSessions(companyId)
      .then((sessions) => {
        if (!cancelled) setState({ kind: "ok", sessions });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            kind: "error",
            message: err instanceof Error ? err.message : "Failed to load computer sessions",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  async function create() {
    if (!companyId) return;
    setBusy(true);
    setMsg(null);
    try {
      await createComputerSession(companyId);
      const sessions = await fetchComputerSessions(companyId);
      setState({ kind: "ok", sessions });
      setMsg("Computer session created on the simulated NEXUS Desk.");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Failed to create computer session");
    } finally {
      setBusy(false);
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

  const { sessions } = state;
  const active = sessions.filter((s) => s.status === "active" || s.status === "created").length;
  const totalActions = sessions.reduce((acc, s) => acc + s.action_count, 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
            Computer use center
          </h2>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Bounded simulated desktop sessions. The desk includes a §67
            purchase fixture: elements on the purchase path are HIGH risk and
            always require an approval gate — the simulator never performs
            payments.
          </p>
        </div>
        <ActionButton onClick={create} busy={busy}>
          New computer session
        </ActionButton>
      </div>

      {msg && (
        <p className="rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300">
          {msg}
        </p>
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
        <StatCard label="Sessions" value={sessions.length} hint={`${active} active/created`} />
        <StatCard label="Total actions" value={totalActions} />
        <StatCard label="Terminated" value={sessions.filter((s) => s.status === "terminated").length} />
      </div>

      <SectionCard title="Computer sessions">
        {sessions.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No computer sessions yet. Create one to interact with the simulated
            NEXUS Desk (reports, composer, checkout).
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-zinc-200 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
                <tr>
                  <th className="px-2 py-2">Session</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">Focus</th>
                  <th className="px-2 py-2">Actions</th>
                  <th className="px-2 py-2">Cursor</th>
                  <th className="px-2 py-2">Started</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {sessions.map((s) => {
                  const screen = (s.screen ?? {}) as { focus?: string; windows?: unknown[] };
                  const cursor = (s.cursor ?? {}) as { x?: number; y?: number };
                  return (
                    <tr key={s.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-900/40">
                      <td className="px-2 py-2.5">
                        <Link
                          href={`/computer/sessions/${s.id}`}
                          className="font-mono text-xs text-zinc-900 underline-offset-2 hover:underline dark:text-zinc-100"
                        >
                          {s.id.slice(0, 8)}
                        </Link>
                      </td>
                      <td className="px-2 py-2.5">
                        <StatusBadge status={s.status as never} />
                      </td>
                      <td className="px-2 py-2.5 text-zinc-600 dark:text-zinc-400">
                        {screen.focus ?? "—"}
                      </td>
                      <td className="px-2 py-2.5 text-zinc-600 dark:text-zinc-400">
                        {s.action_count}
                      </td>
                      <td className="px-2 py-2.5 text-zinc-600 dark:text-zinc-400">
                        {cursor.x != null ? `${cursor.x}, ${cursor.y}` : "—"}
                      </td>
                      <td className="px-2 py-2.5 text-zinc-500">
                        {s.started_at ? new Date(s.started_at).toLocaleString() : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </div>
  );
}