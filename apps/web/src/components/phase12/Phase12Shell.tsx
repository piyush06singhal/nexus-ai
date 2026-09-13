"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  Beaker,
  FlaskConical,
  GitCompare,
  Layers,
  SlidersHorizontal,
  Store,
  ThumbsUp,
  Sparkles,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { fetchCompanies } from "@/lib/api";
import type { Company } from "@/lib/types";
import { cn } from "@/lib/cn";

const STORAGE_KEY = "nexus.phase12.companyId";

/** The company the Phase 12 centers operate on (optional filter). */
export interface Phase12ContextValue {
  companyId: string | null;
  companies: Company[];
  company: Company | null;
  setCompanyId: (id: string) => void;
  href: (path: string) => string;
}

const Phase12Context = createContext<Phase12ContextValue | null>(null);

export function usePhase12() {
  const ctx = useContext(Phase12Context);
  if (!ctx) throw new Error("usePhase12 must be used within <Phase12Shell>");
  return ctx;
}

const CENTER_ICONS: Record<string, LucideIcon> = {
  simulation: FlaskConical,
  optimization: SlidersHorizontal,
  experiments: Beaker,
  marketplace: Store,
};

const SUB_NAVS: Record<string, { href: string; label: string; icon: LucideIcon }[]> = {
  simulation: [
    { href: "/simulations", label: "Overview", icon: FlaskConical },
    { href: "/simulations/scenarios", label: "Scenarios", icon: Layers },
    { href: "/simulations/compare", label: "Compare", icon: GitCompare },
  ],
  optimization: [
    { href: "/optimization", label: "Overview", icon: SlidersHorizontal },
    { href: "/optimization/recommendations", label: "Recommendations", icon: ThumbsUp },
  ],
  experiments: [{ href: "/experiments", label: "Experiments", icon: Beaker }],
  marketplace: [
    { href: "/marketplace", label: "Overview", icon: Store },
    { href: "/marketplace/recommendations", label: "Agent Recommendations", icon: Sparkles },
  ],
};

/**
 * Shared Phase 12 shell: company filter + center sub-nav + header. Mirrors the
 * Phase 11 ControlShell pattern so every Phase 12 center reads from the same
 * company context.
 */
export function Phase12Shell({
  center,
  eyebrow,
  title,
  description,
  children,
}: {
  center: "simulation" | "optimization" | "experiments" | "marketplace";
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyIdState] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchCompanies()
      .then((list) => {
        if (cancelled) return;
        setCompanies(list);
        const saved = localStorage.getItem(STORAGE_KEY);
        const initial = list.find((c) => c.id === saved)?.id ?? list[0]?.id ?? null;
        if (!saved && initial) localStorage.setItem(STORAGE_KEY, initial);
        setCompanyIdState(initial);
        setLoaded(true);
      })
      .catch(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function setCompanyId(id: string) {
    localStorage.setItem(STORAGE_KEY, id);
    setCompanyIdState(id);
  }

  const company = companies.find((c) => c.id === companyId) ?? null;

  const value: Phase12ContextValue = {
    companyId,
    companies,
    company,
    setCompanyId,
    href: (path: string) =>
      companyId ? `${path}?companyId=${encodeURIComponent(companyId)}` : path,
  };

  const Icon = CENTER_ICONS[center];

  return (
    <Phase12Context.Provider value={value}>
      <div className="space-y-6">
        <Phase12Header
          icon={Icon}
          eyebrow={eyebrow}
          title={title}
          description={description}
          subnav={SUB_NAVS[center]}
        />
        {!loaded ? (
          <div className="h-48 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
        ) : (
          children
        )}
      </div>
    </Phase12Context.Provider>
  );
}

function Phase12Header({
  icon: Icon,
  eyebrow,
  title,
  description,
  subnav,
}: {
  icon: LucideIcon;
  eyebrow: string;
  title: string;
  description: string;
  subnav: { href: string; label: string; icon: LucideIcon }[];
}) {
  const pathname = usePathname();
  const { companies, company, companyId, setCompanyId } = usePhase12();
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-zinc-500">
            <Icon className="h-3.5 w-3.5" />
            {eyebrow}
          </p>
          <h1 className="mt-1 flex items-center gap-2 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            {title}
          </h1>
        </div>
        {companies.length > 0 && (
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Filter by company
            </span>
            <select
              value={companyId ?? ""}
              onChange={(e) => setCompanyId(e.target.value)}
              className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            >
              <option value="">All companies</option>
              {companies.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {company && (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Company-scoped view for <strong>{company.name}</strong>
          {company.industry ? ` · ${company.industry}` : ""}
        </p>
      )}

      {description && (
        <p className="max-w-3xl text-sm text-zinc-600 dark:text-zinc-400">{description}</p>
      )}

      <nav className="flex flex-wrap gap-1 border-b border-zinc-200 pb-2 dark:border-zinc-800">
        {subnav.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-zinc-500 transition hover:bg-zinc-200 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100",
              "data-[active=true]:bg-zinc-900 data-[active=true]:text-white dark:data-[active=true]:bg-white dark:data-[active=true]:text-zinc-900",
            )}
            data-active={pathname === item.href ? "true" : undefined}
          >
            <item.icon className="h-3.5 w-3.5" />
            {item.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}