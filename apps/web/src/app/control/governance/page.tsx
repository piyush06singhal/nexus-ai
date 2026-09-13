"use client";

import { useEffect, useState } from "react";
import {
  activateBreakGlass,
  createPolicyRule,
  fetchBreakGlass,
  fetchFeatureFlags,
  fetchPolicyRules,
  fetchResourceLimits,
  fetchResourceUsage,
  fetchSystemFlags,
  pauseScope,
  resumeScope,
  setFeatureFlag,
  setResourceLimit,
} from "@/lib/api";
import type {
  BreakGlassPublic,
  FeatureFlagPublic,
  PolicyRulePublic,
  ResourceLimitPublic,
  ResourceUsagePublic,
  SystemFlagPublic,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { ActionButton, Dash, SectionCard } from "../_components/ui";
import { useControl } from "../_components/ControlShell";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

/** Kill-switch scopes exposed by the backend (GLOBAL…WORKFLOW). */
const SWITCH_SCOPES = [
  "global",
  "company",
  "employee",
  "agent",
  "external",
  "workflow",
] as const;

export default function GovernancePage() {
  const { companyId } = useControl();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [flags, setFlags] = useState<SystemFlagPublic[]>([]);
  const [limits, setLimits] = useState<ResourceLimitPublic[]>([]);
  const [usage, setUsage] = useState<ResourceUsagePublic[]>([]);
  const [policyRules, setPolicyRules] = useState<PolicyRulePublic[]>([]);
  const [featureFlags, setFeatureFlags] = useState<FeatureFlagPublic[]>([]);
  const [breakGlass, setBreakGlass] = useState<BreakGlassPublic[]>([]);

  const [reason, setReason] = useState("");
  const [pausing, setPausing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  function load() {
    Promise.all([
      fetchSystemFlags(),
      fetchResourceLimits(),
      fetchResourceUsage(),
      fetchPolicyRules(),
      fetchFeatureFlags(),
      fetchBreakGlass(),
    ])
      .then(([fl, li, us, po, ff, bg]) => {
        setError(null);
        setFlags(fl);
        setLimits(li);
        setUsage(us);
        setPolicyRules(po);
        setFeatureFlags(ff);
        setBreakGlass(bg);
        setState({ kind: "ok" });
      })
      .catch((err: unknown) => {
        setState({
          kind: "error",
          message:
            err instanceof Error ? err.message : "Failed to load governance data",
        });
      });
  }

  useEffect(() => {
    load();
  }, [companyId]);

  async function toggleSwitch(scope: string, active: boolean) {
    setPausing(scope);
    setError(null);
    setDone(null);
    try {
      if (active) {
        await resumeScope(scope);
      } else if (reason.trim()) {
        await pauseScope(scope, reason.trim(), companyId);
      } else {
        setError(`Set a pause reason for scope "${scope}" first.`);
        return;
      }
      setDone(`Kill switch ${active ? "resumed" : "paused"}: ${scope}`);
      setReason("");
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Kill switch action failed");
    } finally {
      setPausing(null);
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

  const pausedScopes = new Set(
    flags.filter((f) => f.status === "active").map((f) => f.scope),
  );

  return (
    <div className="space-y-6">
      {(error || done) && (
        <p
          className={
            error
              ? "rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300"
              : "rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:border-emerald-900/40 dark:bg-emerald-950/30 dark:text-emerald-300"
          }
        >
          {error ?? done}
        </p>
      )}

      <SectionCard title="Kill switch">
        <div className="mb-3 space-y-2">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Pause reason (required to pause a scope)
            </span>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Outbound-failure investigation (incident #…)"
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            />
          </label>
          {companyId ? (
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              Company-scoped pauses apply to{" "}
              <strong className="text-zinc-700 dark:text-zinc-300">
                company {companyId}
              </strong>{" "}
              (scope: company).
            </p>
          ) : (
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              Company-scoped pauses require selecting a company in the filter.
            </p>
          )}
        </div>

        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {SWITCH_SCOPES.map((scope) => {
            const active = pausedScopes.has(scope);
            return (
              <div
                key={scope}
                className="flex items-center justify-between gap-3 rounded-lg border border-zinc-200 p-3 dark:border-zinc-800"
              >
                <div>
                  <p className="text-sm font-medium capitalize text-zinc-900 dark:text-zinc-100">
                    {scope}
                  </p>
                  <StatusBadge status={active ? "paused" : "active"} />
                </div>
                <ActionButton
                  busy={pausing === scope}
                  disabled={active ? false : !reason.trim()}
                  onClick={() => toggleSwitch(scope, active)}
                >
                  {active ? "Resume" : "Pause"}
                </ActionButton>
              </div>
            );
          })}
        </div>

        {flags.length > 0 && (
          <ul className="mt-4 space-y-1 text-sm">
            {flags.map((f) => (
              <li
                key={f.id}
                className="flex flex-wrap items-center justify-between gap-2 text-zinc-600 dark:text-zinc-400"
              >
                <span className="font-mono text-xs">{f.flag}</span>
                <span className="text-xs">
                  <Dash value={f.reason} /> · {f.status} · set at{" "}
                  {new Date(f.set_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <LimitPanel
        limits={limits}
        usage={usage}
        onSetLimit={async (data) => {
          await setResourceLimit({
            ...data,
            tenant_id: companyId,
          });
          load();
        }}
        onError={setError}
        onDone={setDone}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <PolicyPanel rules={policyRules} onCreate={createPolicyRule} />

        <BreakGlassPanel
          entries={breakGlass}
          onActivate={activateBreakGlass}
        />
      </div>

      <FeatureFlagPanel
        flags={featureFlags}
        onToggle={async (name, enabled, rationale) => {
          await setFeatureFlag(name, { enabled, rationale });
          setDone(`Feature flag "${name}" ${enabled ? "enabled" : "disabled"}`);
          load();
        }}
      />
    </div>
  );
}

// ── resource limits ──────────────────────────────────────────────────────────

function LimitPanel({
  limits,
  usage,
  onSetLimit,
  onError,
  onDone,
}: {
  limits: ResourceLimitPublic[];
  usage: ResourceUsagePublic[];
  onSetLimit: (data: {
    category: string;
    max_value: number;
    scope: string;
    period: string;
  }) => Promise<void>;
  onError: (msg: string) => void;
  onDone: (msg: string) => void;
}) {
  const [category, setCategory] = useState("");
  const [maxValue, setMaxValue] = useState("100");
  const [scope, setScope] = useState("company");
  const [period, setPeriod] = useState("per_day");
  const [busy, setBusy] = useState(false);

  return (
    <SectionCard title="Resource limits">
      <div className="grid gap-2 sm:grid-cols-5">
        <input
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          placeholder="category (e.g. api_calls)"
          className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 sm:col-span-2"
        />
        <input
          type="number"
          value={maxValue}
          onChange={(e) => setMaxValue(e.target.value)}
          placeholder="max value"
          className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        />
        <select
          value={scope}
          onChange={(e) => setScope(e.target.value)}
          className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        >
          <option value="global">global</option>
          <option value="company">company</option>
          <option value="employee">employee</option>
          <option value="agent">agent</option>
        </select>
        <select
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        >
          <option value="per_run">per run</option>
          <option value="per_day">per day</option>
          <option value="per_week">per week</option>
        </select>
      </div>
      <div className="mt-2">
        <ActionButton
          busy={busy}
          disabled={!category.trim() || !maxValue.trim()}
          onClick={async () => {
            setBusy(true);
            try {
              await onSetLimit({
                category: category.trim(),
                max_value: Number(maxValue),
                scope,
                period,
              });
              setCategory("");
              onDone("Resource limit set (enforced).");
            } catch (err: unknown) {
              onError(
                err instanceof Error ? err.message : "Failed to set limit",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          Set limit
        </ActionButton>
      </div>

      {limits.length > 0 && (
        <ul className="mt-4 divide-y divide-zinc-100 dark:divide-zinc-800">
          {limits.map((l) => (
            <li
              key={l.id}
              className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"
            >
              <div>
                <p className="text-zinc-900 dark:text-zinc-100">
                  {l.category}{" "}
                  <span className="text-xs text-zinc-500 dark:text-zinc-400">
                    ≤ {l.max_value} / {l.period ?? "?"}
                  </span>
                </p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  scope {l.scope}
                  {l.tenant_id ? ` · company ${l.tenant_id}` : ""}
                </p>
              </div>
              <StatusBadge status={l.enforced ? "active" : "skipped"} />
            </li>
          ))}
        </ul>
      )}

      {usage.length > 0 && (
        <div className="mt-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">
            Recent usage
          </p>
          <ul className="space-y-1">
            {usage.slice(0, 8).map((u) => (
              <li
                key={u.id}
                className="flex justify-between text-xs text-zinc-600 dark:text-zinc-400"
              >
                <span>
                  {u.category}
                  {u.instrument ? ` · ${u.instrument}` : ""}
                </span>
                <span>
                  {u.amount} {u.unit ?? ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </SectionCard>
  );
}

// ── policies ────────────────────────────────────────────────────────────────

function PolicyPanel({
  rules,
  onCreate,
}: {
  rules: PolicyRulePublic[];
  onCreate: (input: {
    action_pattern: string;
    effect: string;
    subject_pattern?: string;
    resource_pattern?: string;
    risk_level?: string;
    reason?: string;
  }) => Promise<PolicyRulePublic>;
}) {
  const [action, setAction] = useState("");
  const [effect, setEffect] = useState("deny");
  const [subject, setSubject] = useState("agent:*");
  const [resource, setResource] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <SectionCard title="Policy rules">
      <div className="space-y-2 text-sm">
        <input
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder="subject pattern (e.g. agent:finance-* )"
          className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        />
        <div className="grid grid-cols-2 gap-2">
          <input
            value={action}
            onChange={(e) => setAction(e.target.value)}
            placeholder="action (e.g. tool:execute)"
            className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
          <input
            value={resource}
            onChange={(e) => setResource(e.target.value)}
            placeholder="resource pattern"
            className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <select
            value={effect}
            onChange={(e) => setEffect(e.target.value)}
            className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          >
            <option value="allow">allow</option>
            <option value="deny">deny</option>
            <option value="require_approval">require_approval</option>
          </select>
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="reason"
            className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
        </div>
        {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
        <ActionButton
          busy={busy}
          disabled={!action.trim()}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              await onCreate({
                action_pattern: action.trim(),
                effect,
                subject_pattern: subject.trim() || undefined,
                resource_pattern: resource.trim() || undefined,
                reason: reason.trim() || undefined,
              });
              setAction("");
              setReason("");
            } catch (err: unknown) {
              setError(
                err instanceof Error ? err.message : "Failed to create policy rule",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          Add rule
        </ActionButton>
      </div>

      {rules.length > 0 && (
        <ul className="mt-4 divide-y divide-zinc-100 dark:divide-zinc-800">
          {rules.map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-2 py-2">
              <div>
                <p className="text-sm text-zinc-900 dark:text-zinc-100">
                  <span className="font-mono text-xs">{r.action_pattern}</span>{" "}
                  <StatusBadge
                    status={
                      r.effect === "allow"
                        ? "active"
                        : r.effect === "deny"
                          ? "blocked"
                          : "pending"
                    }
                  />
                </p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  subject {r.subject_pattern} · resource {r.resource_pattern} ·
                  risk {r.risk_level}
                </p>
              </div>
              <span className="text-xs text-zinc-400">
                p{r.priority}
                {!r.enabled ? " · disabled" : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

// ── break glass ─────────────────────────────────────────────────────────────

function BreakGlassPanel({
  entries,
  onActivate,
}: {
  entries: BreakGlassPublic[];
  onActivate: (input: {
    reason: string;
    scope?: string;
    max_minutes?: number;
  }) => Promise<BreakGlassPublic>;
}) {
  const [reason, setReason] = useState("");
  const [scope, setScope] = useState("*");
  const [minutes, setMinutes] = useState("60");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const active = entries.filter((b) => b.status === "active");

  return (
    <SectionCard title="Break-glass access">
      <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
        Temporarily elevates access for a scoped operation, auto-expires, and is
        audited. Not for routine use.
      </p>
      <div className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
        {active.length} active · {entries.length} recorded
      </div>
      <div className="space-y-2 text-sm">
        <select
          value={scope}
          onChange={(e) => setScope(e.target.value)}
          className="w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        >
          <option value="*">any scope</option>
          <option value="external">external</option>
          <option value="browser">browser</option>
          <option value="computer">computer</option>
        </select>
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Reason (audited, required)"
          className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        />
        <input
          type="number"
          value={minutes}
          onChange={(e) => setMinutes(e.target.value)}
          placeholder="auto-expiry (minutes)"
          className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        />
        {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
        <ActionButton
          busy={busy}
          disabled={!reason.trim()}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              await onActivate({
                reason: reason.trim(),
                scope,
                max_minutes: Number(minutes) || undefined,
              });
              setReason("");
            } catch (err: unknown) {
              setError(
                err instanceof Error ? err.message : "Break-glass activation failed",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          Activate break-glass
        </ActionButton>
      </div>

      {entries.length > 0 && (
        <ul className="mt-4 divide-y divide-zinc-100 dark:divide-zinc-800">
          {entries.map((b) => (
            <li key={b.id} className="flex items-start justify-between gap-2 py-2">
              <div>
                <p className="text-sm text-zinc-900 dark:text-zinc-100">
                  {b.reason}
                </p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  scope {b.scope} · expires {new Date(b.expires_at).toLocaleString()}
                </p>
              </div>
              <StatusBadge
                status={
                  b.status === "active"
                    ? "active"
                    : b.status === "revoked"
                      ? "revoked"
                      : "expired"
                }
              />
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

// ── feature flags ───────────────────────────────────────────────────────────

function FeatureFlagPanel({
  flags,
  onToggle,
}: {
  flags: FeatureFlagPublic[];
  onToggle: (
    name: string,
    enabled: boolean,
    rationale: string,
  ) => Promise<void>;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  async function toggle(f: FeatureFlagPublic, enabled: boolean) {
    setBusy(f.name);
    try {
      await onToggle(f.name, enabled, "Toggled from Control Center");
    } finally {
      setBusy(null);
    }
  }

  return (
    <SectionCard title="Feature flags (risky capabilities)">
      {flags.length === 0 ? (
        <p className="text-sm text-zinc-500">No feature flags registered.</p>
      ) : (
        <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {flags.map((f) => (
            <li
              key={f.id}
              className="flex flex-wrap items-center justify-between gap-2 py-2"
            >
              <div>
                <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                  {f.name}
                </p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  {f.scope}
                  {f.company_id ? ` · company ${f.company_id}` : ""}
                  {f.rationale ? ` · ${f.rationale}` : ""}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge status={f.enabled ? "active" : "inactive"} />
                <ActionButton
                  busy={busy === f.name}
                  onClick={() => toggle(f, !f.enabled)}
                >
                  {f.enabled ? "Disable" : "Enable"}
                </ActionButton>
              </div>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}