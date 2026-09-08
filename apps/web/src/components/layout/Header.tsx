import { Cpu } from "lucide-react";

export function Header() {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-6 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400">
        <span className="hidden sm:inline">Autonomous AI Workforce &amp; Company OS</span>
        <span className="hidden text-zinc-300 sm:inline dark:text-zinc-600">·</span>
        <span>Foundation</span>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 text-xs text-zinc-600 dark:text-zinc-400">
          <Cpu className="h-3.5 w-3.5 text-zinc-400" />
          <span className="hidden sm:inline">Runtime</span>
        </div>
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-200 text-xs font-semibold text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
          OP
        </div>
      </div>
    </header>
  );
}