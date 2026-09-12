"use client";

import type { ReactNode } from "react";

/** Small stat card used across the external dashboards. */
export function StatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <p className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        {label}
      </p>
      <p className="mt-1.5 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
        {value}
      </p>
      {hint && (
        <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">{hint}</p>
      )}
    </div>
  );
}

/** Section card with a title and optional right-side actions. */
export function SectionCard({
  title,
  action,
  children,
  className,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={
        className ??
        "rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950"
      }
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
          {title}
        </h2>
        {action}
      </div>
      {children}
    </div>
  );
}

/** Value-or-dash cell for nullable fields. */
export function Dash({ value }: { value: ReactNode }) {
  if (value === null || value === undefined || value === "") {
    return <span className="text-zinc-400 dark:text-zinc-600">—</span>;
  }
  return <>{value}</>;
}

/** Inline action button (matches the repo's secondary button style). */
export function ActionButton({
  onClick,
  children,
  busy = false,
  disabled = false,
}: {
  onClick: () => void;
  children: ReactNode;
  busy?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled || busy}
      className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
    >
      {busy ? "Working…" : children}
    </button>
  );
}

/** Renders a list-of-strings JSON column (or null). */
export function StringList({ value }: { value: unknown }) {
  if (Array.isArray(value) && value.length > 0) {
    return (
      <ul className="space-y-1">
        {value.map((v, i) => (
          <li key={i} className="text-sm text-zinc-600 dark:text-zinc-400">
            · {String(v)}
          </li>
        ))}
      </ul>
    );
  }
  return <Dash value={null} />;
}

/** Pretty-prints a JSON value into a scrollable mono block. */
export function JsonBlock({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <Dash value={null} />;
  const text =
    typeof value === "string"
      ? value
      : JSON.stringify(value, null, 2);
  return (
    <pre className="max-h-64 overflow-auto rounded-lg bg-zinc-100 p-3 text-xs leading-relaxed text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
      {text}
    </pre>
  );
}

/** Definition-style key/value row with an optional hover source link. */
export function Row({
  k,
  v,
}: {
  k: string;
  v: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-zinc-100 py-2 last:border-0 dark:border-zinc-800">
      <dt className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        {k}
      </dt>
      <dd className="min-w-0 break-words text-right text-sm text-zinc-900 dark:text-zinc-100">
        {v}
      </dd>
    </div>
  );
}

/** Key/value detail card (dl) reused across integration/action/session pages. */
export function DetailCard({ title, rows }: { title: string; rows: { k: string; v: ReactNode }[] }) {
  return (
    <SectionCard title={title}>
      <dl className="divide-y divide-zinc-100 dark:divide-zinc-800">
        {rows.map((r) => (
          <Row key={r.k} k={r.k} v={r.v} />
        ))}
      </dl>
    </SectionCard>
  );
}