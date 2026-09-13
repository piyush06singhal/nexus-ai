"use client";

import { useEffect, useState } from "react";
import {
  fetchHealthProbe,
  fetchHealthRecords,
  fetchMetricSnapshot,
} from "@/lib/api";
import type {
  MetricsSnapshot,
  SystemHealthProbe,
  SystemHealthRecordPublic,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { Dash, DetailCard, SectionCard } from "../_components/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

export default function HealthPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [probe, setProbe] = useState<SystemHealthProbe | null>(null);
  const [ready, setReady] = useState<SystemHealthProbe | null>(null);
  const [deps, setDeps] = useState<SystemHealthProbe | null>(null);
  const [metrics, setMetrics] = useState<MetricsSnapshot | null>(null);
  const [records, setRecords] = useState<SystemHealthRecordPublic[]>([]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetchHealthProbe("live"),
      fetchHealthProbe("ready"),
      fetchHealthProbe("dependencies"),
      fetchMetricSnapshot(),
      fetchHealthRecords(),
    ])
      .then(([live, rd, dep, met, rec]) => {
        if (cancelled) return;
        setProbe(live);
        setReady(rd);
        setDeps(dep);
        setMetrics(met);
        setRecords(rec);
        setState({ kind: "ok" });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            kind: "error",
            message:
              err instanceof Error ? err.message : "Failed to load system health",
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

  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-3">
        <ProbeCard title="Liveness" probe={probe} />
        <ProbeCard title="Readiness" probe={ready} />
        <ProbeCard title="Dependencies" probe={deps} />
      </div>

      {metrics && (
        <SectionCard title="Runtime metrics">
          <DetailCard
            title="Snapshot"
            rows={[
              { k: "Recorded", v: new Date(metrics.recorded_at).toLocaleString() },
              {
                k: "Counters",
                v:
                  Object.entries(metrics.counters).length > 0 ? (
                    <MetricList data={metrics} />
                  ) : (
                    <Dash value={null} />
                  ),
              },
            ]}
          />
        </SectionCard>
      )}

      <SectionCard title="Health records">
        {records.length === 0 ? (
          <p className="text-sm text-zinc-500">No health records yet.</p>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {records.map((r) => (
              <li
                key={r.id}
                className="flex flex-wrap items-center justify-between gap-2 py-2"
              >
                <div>
                  <p className="text-sm text-zinc-900 dark:text-zinc-100">
                    {r.service} <span className="text-zinc-400">/</span>{" "}
                    {r.component}
                  </p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {new Date(r.recorded_at).toLocaleString()}
                    {r.latency_ms !== null ? ` · ${r.latency_ms} ms` : ""}
                  </p>
                </div>
                <StatusBadge status={r.healthy ? "healthy" : "degraded"} />
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}

function ProbeCard({ title, probe }: { title: string; probe: SystemHealthProbe | null }) {
  if (!probe) return null;
  const ok = probe.status === "ok" || probe.status === "up" || probe.status === "healthy";
  return (
    <SectionCard
      title={title}
      action={<StatusBadge status={ok ? "pass" : "fail"} />}
    >
      <dl className="space-y-1 text-sm">
        <div className="flex justify-between">
          <dt className="text-zinc-500 dark:text-zinc-400">status</dt>
          <dd className="text-zinc-900 dark:text-zinc-100">{probe.status}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-zinc-500 dark:text-zinc-400">service</dt>
          <dd className="text-zinc-900 dark:text-zinc-100">{probe.service}</dd>
        </div>
        {probe.checks &&
          Object.entries(probe.checks).map(([k, v]) => (
            <div key={k} className="flex justify-between">
              <dt className="text-zinc-500 dark:text-zinc-400">{k}</dt>
              <dd className="text-zinc-900 dark:text-zinc-100">{String(v)}</dd>
            </div>
          ))}
      </dl>
    </SectionCard>
  );
}

function MetricList({ data }: { data: MetricsSnapshot }) {
  const entries = Object.entries(data.counters).slice(0, 12);
  return (
    <ul className="space-y-0.5">
      {entries.map(([k, v]) => (
        <li key={k} className="flex justify-between gap-4 font-mono text-xs">
          <span className="text-zinc-600 dark:text-zinc-400">{k}</span>
          <span className="text-zinc-900 dark:text-zinc-100">{v}</span>
        </li>
      ))}
    </ul>
  );
}