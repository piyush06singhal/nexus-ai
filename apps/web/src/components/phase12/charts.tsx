"use client";

/**
 * Minimal SVG/CSS chart primitives for Phase 12 pages (no new charting deps).
 * All values follow the surrounding page labels: simulated/forecast estimates
 * are presented with their output-kind label, never as ACTUAL.
 */

/** Horizontal bar with a value from 0..max — for rankings, scores, usage. */
export function HBar({
  label,
  value,
  max = 100,
  suffix = "",
}: {
  label: string;
  value: number;
  max?: number;
  suffix?: string;
}) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="w-32 shrink-0 truncate text-xs text-zinc-500 dark:text-zinc-400">
        {label}
      </span>
      <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
        <div
          className="h-full rounded-full bg-indigo-500 dark:bg-indigo-400"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-16 shrink-0 text-right text-xs tabular-nums text-zinc-700 dark:text-zinc-300">
        {value.toLocaleString()}
        {suffix}
      </span>
    </div>
  );
}

/** Simple SVG line trajectory — used for KPI/time/cost model curves. */
export function Trajectory({
  points,
  width = 280,
  height = 72,
  color = "#6366f1",
}: {
  points: number[];
  width?: number;
  height?: number;
  color?: string;
}) {
  if (points.length === 0) return null;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const step = width / Math.max(points.length - 1, 1);
  const coords = points.map((p, i) => {
    const x = i * step;
    const y = height - ((p - min) / span) * (height - 8) - 4;
    return [x, y] as const;
  });
  const last = coords[coords.length - 1];
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-16 w-full max-w-xs text-zinc-800 dark:text-zinc-200"
      aria-hidden="true"
    >
      {coords.slice(0, -1).map(([x, y], i) => {
        const [nx, ny] = coords[i + 1];
        return (
          <line
            key={i}
            x1={x}
            y1={y}
            x2={nx}
            y2={ny}
            stroke={color}
            strokeWidth={1.5}
            strokeLinecap="round"
          />
        );
      })}
      <circle cx={last[0]} cy={last[1]} r={2.5} fill={color} />
    </svg>
  );
}

/** Baseline-vs-scenario delta embedded in a row (green better / red worse). */
export function Delta({ value, better = "up" }: { value: number; better?: "up" | "down" }) {
  const good = better === "up" ? value >= 0 : value <= 0;
  const cls = value === 0
    ? "text-zinc-500 dark:text-zinc-400"
    : good
      ? "text-emerald-600 dark:text-emerald-400"
      : "text-red-600 dark:text-red-400";
  const arrow = value > 0 && good ? "▲" : value < 0 && good ? "▼" : value >= 0 ? "▲" : "▼";
  return (
    <span className={`text-xs font-medium tabular-nums ${cls}`}>
      {arrow} {Math.abs(value).toLocaleString()}
    </span>
  );
}