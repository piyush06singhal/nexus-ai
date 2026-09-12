"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  fetchComputerObservations,
  fetchComputerSession,
  pauseComputerSession,
  runComputerAction,
  terminateComputerSession,
} from "@/lib/api";
import type { ComputerAction, ComputerObservation, ComputerSession } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { useExternal } from "../../../_components/ExternalShell";
import {
  ActionButton,
  Dash,
  DetailCard,
  JsonBlock,
  SectionCard,
} from "../../../_components/ui";

interface ActionOption {
  value: string;
  label: string;
  needsElement?: boolean;
  needsText?: boolean;
  needsKey?: boolean;
  needsDirection?: boolean;
  needsX?: boolean;
  needsY?: boolean;
}

const ACTIONS: ActionOption[] = [
  { value: "move_mouse", label: "Move mouse", needsX: true, needsY: true },
  { value: "click", label: "Click element", needsElement: true },
  { value: "double_click", label: "Double-click element", needsElement: true },
  { value: "type", label: "Type into field", needsElement: true, needsText: true },
  { value: "key_press", label: "Press key", needsKey: true },
  { value: "scroll", label: "Scroll", needsDirection: true },
  { value: "drag", label: "Drag element", needsElement: true, needsX: true, needsY: true },
  { value: "screenshot", label: "Screenshot (ref)" },
  { value: "wait", label: "Wait" },
];

const ELEMENTS = [
  { id: "#btn-reports", label: "Open reports" },
  { id: "#btn-compose", label: "Compose message" },
  { id: "#btn-purchase", label: "Purchase plan (navigates to checkout)" },
  { id: "#btn-export", label: "Export CSV" },
  { id: "#fld-to", label: "Composer To" },
  { id: "#fld-subject", label: "Composer Subject" },
  { id: "#fld-body", label: "Composer Body" },
  { id: "#btn-send", label: "Composer Send" },
  { id: "#btn-confirm", label: "Confirm purchase (⚠ high risk, gated)" },
  { id: "#fld-cc", label: "Card number (sensitive)" },
  { id: "#fld-cvv", label: "CVV (sensitive)" },
];

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; session: ComputerSession; observations: ComputerObservation[] }
  | { kind: "error"; message: string };

interface Screen {
  focus?: string;
  windows?: {
    id?: string;
    title?: string;
    sensitive?: boolean;
    elements?: { id?: string; label?: string; type?: string; sensitive?: boolean; purchase?: boolean }[];
  }[];
}

export default function ComputerSessionDetailPage() {
  const { companyId } = useExternal();
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionType, setActionType] = useState(ACTIONS[0].value);
  const [element, setElement] = useState("#btn-reports");
  const [text, setText] = useState("");
  const [key, setKey] = useState("enter");
  const [direction, setDirection] = useState("down");
  const [x, setX] = useState("640");
  const [y, setY] = useState("400");
  const [gateId, setGateId] = useState("");
  const [recent, setRecent] = useState<ComputerAction[]>([]);

  useEffect(() => {
    if (!companyId || !id) return;
    let cancelled = false;
    Promise.all([
      fetchComputerSession(companyId, id),
      fetchComputerObservations(companyId, id).catch(() => []),
    ])
      .then(([session, observations]) => {
        if (!cancelled) setState({ kind: "ok", session, observations });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            kind: "error",
            message: err instanceof Error ? err.message : "Failed to load computer session",
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
    const input: Record<string, unknown> = {};
    if (sel?.needsElement) input.element = element.slice(1); // strip '#'
    if (sel?.needsText) input.text = text;
    if (sel?.needsKey) input.key = key;
    if (sel?.needsDirection) input.direction = direction;
    if (sel?.needsX) input.x = Number(x) || 0;
    if (sel?.needsY) input.y = Number(y) || 0;
    if (sel?.value === "drag") {
      input.dx = 40;
      input.dy = 0;
    }
    try {
      const action = await runComputerAction(companyId, id, {
        action_type: actionType,
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
        fetchComputerSession(companyId, id),
        fetchComputerObservations(companyId, id).catch(() => []),
      ]);
      setState({ kind: "ok", session, observations });
    } catch (err) {
      const m = err instanceof Error ? err.message : "Action failed";
      setMsg(m);
      if (/approval/i.test(m)) {
        setMsg(`${m} — approve the external_action_approval gate on the Integrations dashboard, then re-run with its gate id.`);
      }
    } finally {
      setBusy(null);
    }
  }

  async function pause() {
    if (!companyId || !id) return;
    setBusy("pause");
    setMsg(null);
    try {
      const session = await pauseComputerSession(companyId, id);
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
      const session = await terminateComputerSession(companyId, id);
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
  const screen = (session.screen ?? {}) as Screen;
  const cursor = (session.cursor ?? {}) as { x?: number; y?: number };
  const latest = observations[observations.length - 1];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link
            href="/computer"
            className="text-xs text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
          >
            ← Computer center
          </Link>
          <h2 className="mt-1 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
            Computer session <span className="font-mono">{id.slice(0, 8)}</span>{" "}
            <StatusBadge status={session.status as never} />
          </h2>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Simulated desk (nexus-desk). Purchase/sensitive elements route
            through an approval gate before the driver runs them.
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

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <SectionCard title="Run an input action">
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
              {sel?.needsElement && (
                <label className="block min-w-64 flex-1">
                  <span className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">
                    Element (#id or label)
                  </span>
                  <select
                    value={element}
                    onChange={(e) => setElement(e.target.value)}
                    className="w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                  >
                    {ELEMENTS.map((e) => (
                      <option key={e.id} value={e.id}>
                        {e.label}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {sel?.needsText && (
                <label className="block min-w-48 flex-1">
                  <span className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">Text</span>
                  <input
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    className="w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                  />
                </label>
              )}
              {sel?.needsKey && (
                <label className="block">
                  <span className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">Key</span>
                  <select
                    value={key}
                    onChange={(e) => setKey(e.target.value)}
                    className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                  >
                    <option value="enter">enter</option>
                    <option value="escape">escape</option>
                    <option value="tab">tab</option>
                    <option value="backspace">backspace</option>
                  </select>
                </label>
              )}
              {sel?.needsDirection && (
                <label className="block">
                  <span className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">Direction</span>
                  <select
                    value={direction}
                    onChange={(e) => setDirection(e.target.value)}
                    className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                  >
                    <option value="down">down</option>
                    <option value="up">up</option>
                  </select>
                </label>
              )}
              {sel?.needsX && (
                <label className="block">
                  <span className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">X</span>
                  <input
                    value={x}
                    onChange={(e) => setX(e.target.value)}
                    className="w-20 rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                  />
                </label>
              )}
              {sel?.needsY && (
                <label className="block">
                  <span className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">Y</span>
                  <input
                    value={y}
                    onChange={(e) => setY(e.target.value)}
                    className="w-20 rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                  />
                </label>
              )}
              <ActionButton onClick={run} busy={busy === "run"}>
                Run
              </ActionButton>
            </div>

            <div className="flex flex-wrap items-end gap-2">
              <label className="block flex-1">
                <span className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">
                  Approved gate id (needed for high-risk elements like Confirm purchase)
                </span>
                <input
                  value={gateId}
                  onChange={(e) => setGateId(e.target.value)}
                  placeholder="UUID after approving the gate on Integrations"
                  className="w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                />
              </label>
            </div>
          </SectionCard>

          <SectionCard title="Recent actions">
            {recent.length === 0 ? (
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                Run an action above. Typing into sensitive fields (card/CVV)
                always reports masked ****, never the value.
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
                No observations yet. Run an action to observe the screen state.
              </p>
            ) : (
              <div className="space-y-3">
                {observations
                  .slice()
                  .reverse()
                  .map((o, i) => (
                    <div key={o.id} className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800">
                      <p className="mb-1 text-xs text-zinc-500 dark:text-zinc-400">
                        observation #{o.observation_number} · {o.created_at ? new Date(o.created_at).toLocaleTimeString() : ""}
                        {o.screenshot_ref ? ` · 📸 ${o.screenshot_ref}` : ""}
                      </p>
                      {i === 0 && <JsonBlock value={o.snapshot} />}
                    </div>
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
              { k: "Focus", v: <Dash value={screen.focus} /> },
              { k: "Cursor", v: cursor.x != null ? `${cursor.x}, ${cursor.y}` : "—" },
              { k: "Actions", v: session.action_count },
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
          <DetailCard title="Policy" rows={[{ k: "Policy JSON", v: <JsonBlock value={session.policy} /> }]} />

          <SectionCard title="Screen">
            {(screen.windows ?? []).map((w) => (
              <div
                key={w.id}
                className={
                  "mb-2 rounded-lg border p-3 " +
                  (w.sensitive || (w.elements ?? []).some((e) => e.purchase)
                    ? "border-red-200 bg-red-50/50 dark:border-red-900 dark:bg-red-950/30"
                    : "border-zinc-200 dark:border-zinc-800")
                }
              >
                <p className="mb-1 flex items-center gap-2 text-sm font-medium text-zinc-900 dark:text-zinc-100">
                  {w.title ?? w.id}
                  {w.sensitive && <StatusBadge status="high" />}
                </p>
                <div className="flex flex-wrap gap-1">
                  {(w.elements ?? []).map((e) => (
                    <button
                      key={e.id}
                      onClick={() => setElement(`#${e.id}`)}
                      className={
                        "rounded border px-1.5 py-0.5 text-[11px] " +
                        (e.purchase
                          ? "border-red-300 text-red-700 hover:bg-red-100 dark:border-red-800 dark:text-red-300"
                          : e.sensitive
                            ? "border-amber-300 text-amber-700 hover:bg-amber-100 dark:border-amber-800 dark:text-amber-300"
                            : "border-zinc-300 text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300")
                      }
                    >
                      {e.label ?? e.id}
                      {e.sensitive ? " *" : ""}
                    </button>
                  ))}
                </div>
              </div>
            ))}
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              Select an element to target it — click its chip above.
            </p>
          </SectionCard>

          {latest && (
            <SectionCard title="Latest snapshot">
              <JsonBlock value={latest.snapshot} />
            </SectionCard>
          )}
        </div>
      </div>
    </div>
  );
}