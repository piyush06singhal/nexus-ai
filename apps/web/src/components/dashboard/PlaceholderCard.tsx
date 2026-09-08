import { Construction } from "lucide-react";

/**
 * A card that marks a not-yet-built area of the product.
 * Shown for every section that is planned but not implemented in this phase.
 */
export function PlaceholderCard({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-col rounded-xl border border-dashed border-zinc-300 bg-zinc-50/50 p-6 dark:border-zinc-700 dark:bg-zinc-900/30">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-zinc-900 dark:text-zinc-100">{title}</h3>
        <span className="inline-flex items-center gap-1 rounded-full bg-zinc-200 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
          <Construction className="h-3 w-3" />
          Placeholder
        </span>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
        {description}
      </p>
      <p className="mt-4 text-xs text-zinc-500 dark:text-zinc-500">
        This area is under development and has no functionality yet.
      </p>
    </div>
  );
}