"use client";

import { useEffect, useState } from "react";
import {
  fetchGovernanceControls,
  fetchHealthOverview,
  fetchMetricSnapshot,
  fetchSystemFlags,
  verifyAuditChain,
} from "@/lib/api";
import type {
  AuditChainVerify,
  GovernanceControlPublic,
  HealthOverview,
  MetricsSnapshot,
  SystemFlagPublic,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { Dash, SectionCard, StatCard } from "./_components/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

export default function ControlOverviewPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [overview, setOverview] = useState<HealthOverview | null>(null);
  const [controls, setControls] = useState<GovernanceControlPublic[]>([]);
  const [flags, setFlags] = useState<SystemFlagPublic[]>([]);
  const [chain, setChain] = useState<AuditChainVerify | null>(null);
  const [metrics, setMetrics] = useState<MetricsSnapshot | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetchHealthOverview(),
      fetchGovernanceControls(),
      fetchSystemFlags(),
      verifyAuditChain(),
      fetchMetricSnapshot(),
    ])
      .then(([ov, ctrl, fl, ch, met]) => {
        if (cancelled) return;
        setOverview(ov);
        setControls(ctrl);
        setFlags(fl);
        setChain(ch);
        setMetrics(met);
        setState({ kind: "ok" });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            kind: "error",
            message:
              err instanceof Error
                ? err.message
                : "Failed to load Control Center overview",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

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

  const activeFlags = flags.filter((f) => f.status === "active");
  const pausedCount = activeFlags.length;
  const enforcedCount = controls.filter((c) => c.enforced).length;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Open incidents" value={overview?.incidents_open ?? 0} />
        <StatCard label="Open alerts" value={overview?.alerts_open ?? 0} />
        <StatCard label="Audit events" value={overview?.audit_events ?? 0} />
        <StatCard label="Resource limits" value={overview?.resource_limits ?? 0} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard
          title="Audit chain integrity"
          action={
            chain ? <StatusBadge status={chain.verified ? "pass" : "fail"} /> : null
          }
        >
          {chain ? (
            <dl className="divide-y divide-zinc-100 dark:divide-zinc-800">
              <div className="flex items-start justify-between py-2">
                <dt className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                  Verified
                </dt>
                <dd className="text-sm text-zinc-900 dark:text-zinc-100">
                  {chain.verified ? "INTACT" : "COMPROMISED"}
                </dd>
              </div>
              <div className="flex items-start justify-between py-2">
                <dt className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                  Events checked
                </dt>
                <dd className="text-sm text-zinc-900 dark:text-zinc-100">
                  {chain.checked}
                </dd>
              </div>
              <div className="flex items-start justify-between py-2">
                <dt className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                  First gap at
                </dt>
                <dd className="text-sm text-zinc-900 dark:text-zinc-100">
                  <Dash value={chain.first_gap_at_seq} />
                </dd>
              </div>
            </dl>
          ) : (
            <p className="text-sm text-zinc-500">No chain data yet.</p>
          )}
        </SectionCard>

        <SectionCard
          title="Kill switch"
          action={
            <span className="text-xs text-zinc-500 dark:text-zinc-400">
              {pausedCount} active pause
              {pausedCount === 1 ? "" : "s"}
            </span>
          }
        >
          {pausedCount > 0 ? (
            <ul className="space-y-2">
              {activeFlags.map((f) => (
                <li
                  key={f.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm dark:border-red-900/40 dark:bg-red-950/30"
                >
                  <div>
                    <p className="font-medium text-red-800 dark:text-red-300">
                      {f.flag}
                    </p>
                    <p className="text-xs text-red-700/70 dark:text-red-300/70">
                      {f.reason ?? "no reason recorded"}
                    </p>
                  </div>
                  <StatusBadge status="paused" />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-zinc-500">
              No scope is currently paused. All kill-switch scopes are running.
            </p>
          )}
        </SectionCard>
      </div>

      <SectionCard
        title="Governance posture"
        action={
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            {enforcedCount} / {controls.length} controls enforced
          </span>
        }
      >
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {controls.map((c) => (
            <div
              key={c.id}
              className="flex items-start justify-between gap-2 rounded-lg border border-zinc-200 p-3 dark:border-zinc-800"
            >
              <div>
                <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                  {c.title}
                </p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  {c.code} · {c.category}
                </p>
              </div>
              <StatusBadge status={c.enforced ? "active" : "skipped"} />
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="System metrics" >
        {metrics ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {Object.entries(metrics.counters).length > 0 ? (
              Object.entries(metrics.counters)
                .slice(0, 8)
                .map(([k, v]) => <StatCard key={k} label={k} value={v} />)
            ) : (
              <p className="text-sm text-zinc-500">No counters captured yet.</p>
            )}
          </div>
        ) : null}
      </SectionCard>
    </div>
  );
}