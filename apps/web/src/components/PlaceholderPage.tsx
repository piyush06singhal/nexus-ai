import { Construction } from "lucide-react";

/** Full-page placeholder used by unbuilt section routes. */
export function PlaceholderPage({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-col items-start gap-6">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-zinc-500">
        <Construction className="h-3.5 w-3.5" />
        Under development
      </div>

      <div className="w-full rounded-xl border border-dashed border-zinc-300 bg-zinc-50/50 p-10 dark:border-zinc-700 dark:bg-zinc-900/30">
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
          {title}
        </h1>
        <p className="mt-3 max-w-xl text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
          {description}
        </p>
        <p className="mt-6 text-xs text-zinc-500 dark:text-zinc-500">
          This section is a placeholder for NEXUS Phase 0 and has no functional
          behaviour yet. It will be implemented in a later phase of the roadmap.
        </p>
      </div>
    </div>
  );
}