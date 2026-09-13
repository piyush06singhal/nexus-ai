"use client";

/**
 * Settings — runtime configuration and health overview, rendered from live API
 * data. Displays safe operational values only (environment, versions, probes,
 * feature flags, governance flags, resource limits, health records) and never
 * keys, tokens, or ciphertext. (Final-pass §16/§44 — replaces the former
 * placeholder.)
 */

import { useEffect, useState } from "react";
import {
  fetchFeatureFlags,
  fetchHealthDependencies,
  fetchHealthLive,
  fetchHealthOverview,
  fetchHealthReady,
  fetchHealthRecords,
  fetchMetricSnapshot,
  fetchResourceLimits,
  fetchSystemFlags,
} from "@/lib/api";
import type {
  FeatureFlagPublic,
  HealthProbe,
  MetricsSnapshot,
  ResourceLimitPublic,
  SystemFlagPublic,
  SystemHealthRecordPublic,
} from "@/lib/types";
import { StatusBadge, type BadgeStatus } from "@/components/StatusBadge";

/** Map a dependency-probe status ("ok"|"degraded"|"unavailable") to a badge. */
function dependencyBadge(status: string): BadgeStatus {
  if (status === "ok") return "active";
  if (status === "degraded") return "degraded";
  return "inactive";
}
import { Dash, Row, SectionCard, StatCard } from "@/components/phase12/ui";

interface SettingsData {
  live: HealthProbe | null;
  ready: HealthProbe | null;
  dependencies: HealthProbe | null;
  flags: SystemFlagPublic[];
  featureFlags: FeatureFlagPublic[];
  limits: ResourceLimitPublic[];
  records: SystemHealthRecordPublic[];
  metrics: MetricsSnapshot | null;
  overview: { incidents_open: number; alerts_open: number } | null;
}

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; data: SettingsData }
  | { kind: "error"; message: string };

function probeCheck(
  probe: HealthProbe | null,
): { ok: boolean; label: string } {
  if (!probe) return { ok: false, label: "unavailable" };
  const allOk = Object.values(probe.checks).every((c) => c.status === "ok");
  return { ok: allOk, label: allOk ? "ready" : "degraded" };
}

export default function SettingsPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    const results = Promise.allSettled([
      fetchHealthLive(),
      fetchHealthReady().catch(() => null),
      fetchHealthDependencies(),
      fetchSystemFlags(),
      fetchFeatureFlags(),
      fetchResourceLimits(),
      fetchHealthRecords(),
      fetchMetricSnapshot(),
      fetchHealthOverview(),
    ]);
    results
      .then(([live, ready, deps, flags, featureFlags, limits, records, metrics, overview]) => {
        if (cancelled) return;
        const value = (r: PromiseSettledResult<unknown>) =>
          r.status === "fulfilled" ? (r.value as never) : null;
        setState({
          kind: "ok",
          data: {
            live: value(live) as HealthProbe | null,
            ready: value(ready) as HealthProbe | null,
            dependencies: value(deps) as HealthProbe | null,
            flags: (value(flags) as SystemFlagPublic[] | null) ?? [],
            featureFlags: (value(featureFlags) as FeatureFlagPublic[] | null) ?? [],
            limits: (value(limits) as ResourceLimitPublic[] | null) ?? [],
            records: (value(records) as SystemHealthRecordPublic[] | null) ?? [],
            metrics: value(metrics) as MetricsSnapshot | null,
            overview: value(overview) as SettingsData["overview"] | null,
          },
        });
      })
      .catch(() => {
        // Values should not be null-only, but if the data-race guard trips we
        // still surface a failure rather than a blank page.
        if (!cancelled)
          setState({ kind: "error", message: "Failed to load settings" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.kind === "loading") {
    return (
      <div className="h-64 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
    );
  }
  if (state.kind === "error") {
    return (
      <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
        {state.message}
      </p>
    );
  }

  const d = state.data;
  const live = probeCheck(d.live);
  const ready = probeCheck(d.ready);
  const deps = probeCheck(d.dependencies);
  const recordCount = d.records.length;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          Settings
        </h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Runtime configuration and operational health, read live from the API.
          Secret values are never displayed here.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Service" value={d.live?.service ?? "NEXUS API"} />
        <StatCard label="Version" value={d.live?.version ?? "—"} />
        <StatCard label="Environment" value={d.live?.environment ?? "—"} />
        <StatCard label="Open incidents" value={d.overview?.incidents_open ?? "—"} />
      </div>

      <SectionCard title="Health probes">
        <div className="grid gap-3 sm:grid-cols-3">
          <ProbeCard name="Liveness" ok={live.ok} label={live.label} />
          <ProbeCard name="Readiness" ok={ready.ok} label={ready.label} />
          <ProbeCard name="Dependencies" ok={deps.ok} label={deps.label} />
        </div>
        {d.dependencies && Object.keys(d.dependencies.checks).length > 0 && (
          <div className="mt-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              Per-dependency status
            </p>
            <div className="flex flex-wrap gap-2">
              {Object.entries(d.dependencies.checks).map(([name, check]) => (
                <span
                  key={name}
                  className="inline-flex items-center gap-1.5 rounded-full border border-zinc-200 px-2.5 py-1 text-xs text-zinc-600 dark:border-zinc-800 dark:text-zinc-400"
                >
                  {name}
                  <StatusBadge status={dependencyBadge(check.status)} />
                </span>
              ))}
            </div>
          </div>
        )}
      </SectionCard>

      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard title="Feature flags">
          {d.featureFlags.length === 0 ? (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              No feature flags configured.
            </p>
          ) : (
            <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {d.featureFlags.map((f) => (
                <li key={f.id} className="flex items-center justify-between py-2 text-sm">
                  <span className="text-zinc-700 dark:text-zinc-300">{f.name}</span>
                  <StatusBadge status={f.enabled ? "active" : "inactive"} />
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        <SectionCard title="Governance flags (kill-switch scopes)">
          {d.flags.length === 0 ? (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              No governance flags set — all scopes are running.
            </p>
          ) : (
            <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {d.flags.map((f) => (
                <li key={f.id} className="flex items-center justify-between py-2 text-sm">
                  <span className="text-zinc-700 dark:text-zinc-300">{f.scope}</span>
                  <StatusBadge
                    status={f.status === "paused" ? "paused" : "active"}
                  />
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>

      <SectionCard title="Resource limits">
        {d.limits.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No resource limits configured yet — add them via Governance.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-zinc-200 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
                <tr>
                  <th className="px-3 py-2">Category</th>
                  <th className="px-3 py-2">Scope</th>
                  <th className="px-3 py-2">Max value</th>
                  <th className="px-3 py-2">Period</th>
                  <th className="px-3 py-2">Enforced</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {d.limits.map((l) => (
                  <tr key={l.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-900/40">
                    <td className="px-3 py-2.5">{l.category}</td>
                    <td className="px-3 py-2.5">{l.scope}</td>
                    <td className="px-3 py-2.5">{l.max_value}</td>
                    <td className="px-3 py-2.5">
                      <Dash value={l.period} />
                    </td>
                    <td className="px-3 py-2.5">
                      <StatusBadge status={l.enforced ? "active" : "inactive"} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Runtime metrics (since process start)">
        {d.metrics && Object.keys(d.metrics.counters).length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {Object.entries(d.metrics.counters)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([name, value]) => (
                <StatCard key={name} label={name} value={Math.round(value)} />
              ))}
          </div>
        ) : (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No metrics recorded yet.
          </p>
        )}
      </SectionCard>

      <SectionCard title={`Health records (${recordCount} recent)`}>
        {recordCount === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No health records recorded yet.
          </p>
        ) : (
          <div className="max-h-80 space-y-1 overflow-y-auto">
            {d.records.slice(0, 30).map((r) => (
              <Row
                key={r.id}
                k={`${r.service} / ${r.component}`}
                v={
                  <span className="flex items-center gap-2">
                    <StatusBadge status={r.healthy ? "active" : "inactive"} />
                    <span className="text-xs text-zinc-500 dark:text-zinc-400">
                      {r.latency_ms != null ? `${r.latency_ms}ms` : "—"}
                    </span>
                  </span>
                }
              />
            ))}
          </div>
        )}
      </SectionCard>
    </div>
  );
}

function ProbeCard({ name, ok, label }: { name: string; ok: boolean; label: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800">
      <p className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        {name}
      </p>
      <p className="mt-1 flex items-center gap-2 text-sm font-medium text-zinc-900 dark:text-zinc-100">
        <span
          className={`h-2 w-2 rounded-full ${
            ok ? "bg-emerald-500" : "bg-amber-500"
          }`}
        />
        {label}
      </p>
    </div>
  );
}