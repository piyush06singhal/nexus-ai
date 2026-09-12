"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { createBrowserSession, fetchBrowserSessions } from "@/lib/api";
import type { BrowserSession } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { useExternal } from "../_components/ExternalShell";
import { ActionButton, Dash, SectionCard, StatCard } from "../_components/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; sessions: BrowserSession[] }
  | { kind: "error"; message: string };

export default function BrowserCenterPage() {
  const { companyId } = useExternal();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    fetchBrowserSessions(companyId)
      .then((sessions) => {
        if (!cancelled) setState({ kind: "ok", sessions });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            kind: "error",
            message: err instanceof Error ? err.message : "Failed to load browser sessions",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  async function createSession() {
    if (!companyId) return;
    setBusy(true);
    setMsg(null);
    try {
      // Default allowed domains are the deterministic fixture catalog.
      await createBrowserSession(companyId);
      const sessions = await fetchBrowserSessions(companyId);
      setState({ kind: "ok", sessions });
      setMsg("Browser session created. Open a fixture page from the fixture catalog.");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Failed to create browser session");
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
            Browser use center
          </h2>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Bounded simulated browser sessions. Page content is untrusted
            (content_type=EXTERNAL_UNTRUSTED_CONTENT) and never treated as an
            instruction. Domain policy and per-session limits bound every
            session.
          </p>
        </div>
        <ActionButton onClick={createSession} busy={busy}>
          New browser session
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
        <StatCard
          label="Terminated"
          value={sessions.filter((s) => s.status === "terminated").length}
        />
      </div>

      <SectionCard title="Browser sessions">
        {sessions.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No browser sessions yet. Create one to browse the deterministic
            fixture catalog (e.g. https://discovery.nexus.test/).
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-zinc-200 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
                <tr>
                  <th className="px-2 py-2">Session</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">Current URL</th>
                  <th className="px-2 py-2">Actions</th>
                  <th className="px-2 py-2">Navs</th>
                  <th className="px-2 py-2">Started</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {sessions.map((s) => (
                  <tr key={s.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-900/40">
                    <td className="px-2 py-2.5">
                      <Link
                        href={`/browser/sessions/${s.id}`}
                        className="font-mono text-xs text-zinc-900 underline-offset-2 hover:underline dark:text-zinc-100"
                      >
                        {s.id.slice(0, 8)}
                      </Link>
                    </td>
                    <td className="px-2 py-2.5">
                      <StatusBadge status={s.status as never} />
                    </td>
                    <td className="max-w-xs truncate px-2 py-2.5 text-zinc-600 dark:text-zinc-400">
                      <Dash value={s.current_url} />
                    </td>
                    <td className="px-2 py-2.5 text-zinc-600 dark:text-zinc-400">
                      {s.action_count}
                    </td>
                    <td className="px-2 py-2.5 text-zinc-600 dark:text-zinc-400">
                      {s.navigation_count}
                    </td>
                    <td className="px-2 py-2.5 text-zinc-500">
                      {s.started_at ? new Date(s.started_at).toLocaleString() : "—"}
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