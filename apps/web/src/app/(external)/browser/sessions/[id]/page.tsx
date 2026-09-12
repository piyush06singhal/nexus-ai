"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  fetchBrowserObservations,
  fetchBrowserSession,
  pauseBrowserSession,
  runBrowserAction,
  terminateBrowserSession,
} from "@/lib/api";
import type { BrowserAction, BrowserObservation, BrowserSession } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { useExternal } from "../../../_components/ExternalShell";
import {
  ActionButton,
  Dash,
  DetailCard,
  JsonBlock,
  SectionCard,
  StatCard,
} from "../../../_components/ui";

const FIXTURE_CATALOG = [
  "https://discovery.nexus.test/",
  "https://discovery.nexus.test/products/nexus",
  "https://discovery.nexus.test/products/alpha",
  "https://discovery.nexus.test/products/beta",
  "https://discovery.nexus.test/compare",
  "https://discovery.nexus.test/industry/security",
  "https://discovery.nexus.test/industry/malicious-injection",
];

const ACTIONS = [
  { value: "open_page", label: "Open page", needsUrl: true },
  { value: "navigate", label: "Navigate", needsUrl: true },
  { value: "back", label: "Back", needsUrl: false },
  { value: "forward", label: "Forward", needsUrl: false },
  { value: "refresh", label: "Refresh", needsUrl: false },
  { value: "click", label: "Click element", needsSelector: true },
  { value: "type", label: "Type into field", needsSelector: true, needsText: true },
  { value: "select", label: "Select option", needsSelector: true },
  { value: "scroll", label: "Scroll", needsSelector: false },
  { value: "extract_text", label: "Extract text", needsUrl: false },
  { value: "extract_links", label: "Extract links", needsUrl: false },
  { value: "screenshot", label: "Screenshot (ref)", needsUrl: false },
];

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; session: BrowserSession; observations: BrowserObservation[] }
  | { kind: "error"; message: string };

export default function BrowserSessionDetailPage() {
  const { companyId } = useExternal();
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionType, setActionType] = useState(ACTIONS[0].value);
  const [url, setUrl] = useState(FIXTURE_CATALOG[0]);
  const [selector, setSelector] = useState("");
  const [text, setText] = useState("");
  const [gateId, setGateId] = useState("");
  const [recent, setRecent] = useState<BrowserAction[]>([]);

  useEffect(() => {
    if (!companyId || !id) return;
    let cancelled = false;
    Promise.all([
      fetchBrowserSession(companyId, id),
      fetchBrowserObservations(companyId, id).catch(() => []),
    ])
      .then(([session, observations]) => {
        if (!cancelled) setState({ kind: "ok", session, observations });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            kind: "error",
            message: err instanceof Error ? err.message : "Failed to load browser session",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [companyId, id]);

  const sel = ACTIONS.find((a) => a.value === actionType);

  async function run() {
    if (!companyId || !id) return;
    setBusy("run");
    setMsg(null);
    const target: Record<string, unknown> = {};
    const input: Record<string, unknown> = {};
    if (sel?.needsUrl) {
      if (!url.trim()) {
        setMsg("Enter a fixture URL (https://discovery.nexus.test/…)");
        return;
      }
      target.url = url.trim();
    }
    if (sel?.needsSelector) {
      if (!selector.trim()) {
        setMsg("Enter an element selector (#btn-prod-nexus or an element label).");
        return;
      }
      target.selector = selector.trim();
    }
    if (sel?.needsText) input.text = text;
    try {
      const action = await runBrowserAction(companyId, id, {
        action_type: actionType,
        target: Object.keys(target).length ? target : undefined,
        input: Object.keys(input).length ? input : undefined,
        approved_gate_id: gateId.trim() || undefined,
      });
      setRecent((r) => [action, ...r].slice(0, 10));
      setMsg(
        action.status === "succeeded"
          ? `${actionType} succeeded in ${action.duration_ms ?? "?"}ms`
          : `Action → ${action.status}`,
      );
      const [session, observations] = await Promise.all([
        fetchBrowserSession(companyId, id),
        fetchBrowserObservations(companyId, id).catch(() => []),
      ]);
      setState({ kind: "ok", session, observations });
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(null);
    }
  }

  async function pause() {
    if (!companyId || !id) return;
    setBusy("pause");
    setMsg(null);
    try {
      const session = await pauseBrowserSession(companyId, id);
      setState((s) => (s.kind === "ok" ? { ...s, session } : s));
      setMsg("Session paused.");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Failed to pause");
    } finally {
      setBusy(null);
    }
  }

  async function terminate() {
    if (!companyId || !id) return;
    setBusy("terminate");
    setMsg(null);
    try {
      const session = await terminateBrowserSession(companyId, id);
      setState((s) => (s.kind === "ok" ? { ...s, session } : s));
      setMsg("Session terminated.");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Failed to terminate");
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

  const { session, observations } = state;
  const latest = observations[observations.length - 1];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link
            href="/browser"
            className="text-xs text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
          >
            ← Browser center
          </Link>
          <h2 className="mt-1 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
            Browser session <span className="font-mono">{id.slice(0, 8)}</span>{" "}
            <StatusBadge status={session.status as never} />
          </h2>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Page content is untrusted. Observations carry an{" "}
            <code className="text-zinc-500">EXTERNAL_UNTRUSTED_CONTENT</code>{" "}
            marker and are never treated as instructions.
          </p>
        </div>
        <div className="flex gap-2">
          <ActionButton onClick={pause} busy={busy === "pause"}>
            Pause
          </ActionButton>
          <ActionButton onClick={terminate} busy={busy === "terminate"}>
            Terminate
          </ActionButton>
        </div>
      </div>

      {msg && (
        <p className="rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300">
          {msg}
        </p>
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Status" value={<StatusBadge status={session.status as never} />} />
        <StatCard label="Actions" value={session.action_count} hint={`${session.navigation_count} navigations`} />
        <StatCard label="Observations" value={observations.length} />
        <StatCard label="Screenshots" value={observations.filter((o) => o.screenshot_ref).length} hint="refs only, no real images" />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <SectionCard title="Run an action">
            <div className="mb-3 flex flex-wrap items-end gap-2">
              <label className="block">
                <span className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">Action</span>
                <select
                  value={actionType}
                  onChange={(e) => setActionType(e.target.value)}
                  className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                >
                  {ACTIONS.map((a) => (
                    <option key={a.value} value={a.value}>
                      {a.label}
                    </option>
                  ))}
                </select>
              </label>
              {sel?.needsUrl && (
                <label className="block min-w-64 flex-1">
                  <span className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">
                    Fixture URL
                  </span>
                  <input
                    list="fixture-urls"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    className="w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                  />
                  <datalist id="fixture-urls">
                    {FIXTURE_CATALOG.map((u) => (
                      <option key={u} value={u} />
                    ))}
                  </datalist>
                </label>
              )}
              {sel?.needsSelector && (
                <label className="block min-w-56 flex-1">
                  <span className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">
                    Element (#id or label)
                  </span>
                  <input
                    value={selector}
                    onChange={(e) => setSelector(e.target.value)}
                    placeholder="#btn-prod-nexus"
                    className="w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                  />
                </label>
              )}
              {sel?.needsText && (
                <label className="block min-w-40 flex-1">
                  <span className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">Text</span>
                  <input
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    className="w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                  />
                </label>
              )}
              <ActionButton onClick={run} busy={busy === "run"}>
                Run
              </ActionButton>
            </div>
            <label className="block">
              <span className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">
                Approved gate id (required when a sensitive element gates the action)
              </span>
              <input
                value={gateId}
                onChange={(e) => setGateId(e.target.value)}
                placeholder="approval gate UUID after approving on Integrations → Approvals"
                className="w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
              />
            </label>
          </SectionCard>

          <SectionCard title="Recent actions">
            {recent.length === 0 ? (
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                Run an action above to see result, verification, and risk here.
              </p>
            ) : (
              <ul className="space-y-3">
                {recent.map((a) => (
                  <li key={a.id} className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span className="font-mono text-sm text-zinc-900 dark:text-zinc-100">
                        {a.action_type}
                      </span>
                      <StatusBadge status={a.status as never} />
                      <StatusBadge status={a.risk_level} />
                      {a.approval_status !== "not_required" && (
                        <StatusBadge status={a.approval_status as never} />
                      )}
                      {a.duration_ms != null && (
                        <span className="text-xs text-zinc-500">{a.duration_ms}ms</span>
                      )}
                    </div>
                    {a.error && <p className="text-sm text-red-600 dark:text-red-400">{a.error}</p>}
                    {a.result ? <JsonBlock value={a.result} /> : null}
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>

          <SectionCard title={`Observations (${observations.length})`}>
            {observations.length === 0 ? (
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                No observations yet. Open a page to observe its untrusted
                structured snapshot.
              </p>
            ) : (
              <div className="space-y-4">
                {observations
                  .slice()
                  .reverse()
                  .map((o) => (
                    <ObservationCard key={o.id} o={o} />
                  ))}
              </div>
            )}
          </SectionCard>
        </div>

        <div className="space-y-4">
          <DetailCard
            title="Session"
            rows={[
              { k: "Status", v: <StatusBadge status={session.status as never} /> },
              { k: "Current URL", v: <Dash value={session.current_url} /> },
              { k: "Domain", v: <Dash value={session.domain} /> },
              { k: "Actions", v: session.action_count },
              { k: "Navigations", v: session.navigation_count },
              {
                k: "Started",
                v: session.started_at ? new Date(session.started_at).toLocaleString() : "—",
              },
              {
                k: "Last activity",
                v: session.last_activity_at
                  ? new Date(session.last_activity_at).toLocaleString()
                  : "—",
              },
            ]}
          />
          <DetailCard
            title="Policy"
            rows={[
              { k: "Allowed domains", v: <Dash value={Array.isArray(session.allowed_domains) ? session.allowed_domains.join(", ") : String(session.allowed_domains ?? "")} /> },
              { k: "Policy JSON", v: <JsonBlock value={session.policy} /> },
            ]}
          />
          {latest && (
            <SectionCard title="Latest page">
              <p className="mb-1 flex items-center gap-2 text-sm text-zinc-800 dark:text-zinc-200">
                {latest.title}
                <StatusBadge status={latest.content_type as never} />
              </p>
              <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">{latest.url}</p>
              <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
                observation #{latest.observation_number}
              </p>
              <JsonBlock value={latest.snapshot} />
            </SectionCard>
          )}
        </div>
      </div>
    </div>
  );
}

function ObservationCard({ o }: { o: BrowserObservation }) {
  const snap = (o.snapshot ?? {}) as { visible_text?: string; interactive?: unknown[]; links?: unknown[] };
  return (
    <div className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{o.title ?? "Untitled"}</span>
        <StatusBadge status={o.content_type as never} />
        {o.screenshot_ref && (
          <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
            📸 {o.screenshot_ref}
          </span>
        )}
      </div>
      <p className="mb-2 truncate text-xs text-zinc-500 dark:text-zinc-400">{o.url}</p>
      {snap.visible_text && (
        <p className="mb-2 max-h-32 overflow-auto whitespace-pre-line text-sm text-zinc-700 dark:text-zinc-300">
          {snap.visible_text}
        </p>
      )}
      {(() => {
        const interactive = snap.interactive ?? [];
        if (interactive.length === 0) return null;
        return (
          <div className="mb-2 flex flex-wrap gap-1">
            {interactive.map((el, i) => (
              <span
                key={i}
                className="rounded border border-zinc-200 px-1.5 py-0.5 text-[11px] text-zinc-600 dark:border-zinc-700 dark:text-zinc-400"
              >
                {(el as { id?: string; label?: string }).label ?? (el as { id?: string }).id}
              </span>
            ))}
          </div>
        );
      })()}
      {(snap.links?.length ?? 0) > 0 && (
        <p className="max-h-20 overflow-auto text-xs text-zinc-500 dark:text-zinc-400">
          {(snap.links as { href?: string }[])
            .map((l) => l.href)
            .filter(Boolean)
            .slice(0, 8)
            .join(" · ")}
        </p>
      )}
    </div>
  );
}