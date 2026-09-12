"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  Bot,
  CheckCircle2,
  GitBranch,
  ListChecks,
  Package,
  Rocket,
  ShieldCheck,
} from "lucide-react";
import { fetchCompanies } from "@/lib/api";
import type { Company } from "@/lib/types";
import { cn } from "@/lib/cn";

const PLAN_MISSION_KEY = "nexus.startup.planMission";

/** The company every /startup page operates on (Phase 9 is per-company). */
export interface StartupContextValue {
  companyId: string | null;
  companies: Company[];
  company: Company | null;
  setCompanyId: (id: string) => void;
  /** href builder carrying the selected company. */
  href: (path: string) => string;
  /** Remember which mission a startup plan belongs to (for scoped fetches). */
  rememberMission: (planId: string, missionId: string) => void;
  /** Resolve a startup plan's parent mission id (from localStorage). */
  missionForPlan: (planId: string) => string | null;
}

const StartupContext = createContext<StartupContextValue | null>(null);

export function useStartup() {
  const ctx = useContext(StartupContext);
  if (!ctx) throw new Error("useStartup must be used within <StartupShell>");
  return ctx;
}

const STORAGE_KEY = "nexus.startup.companyId";

/** Client shell for the Autonomous Startup suite: company selector + sub-nav. */
export function StartupShell({ children }: { children: ReactNode }) {
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
        const initial =
          list.find((c) => c.id === saved)?.id ?? list[0]?.id ?? null;
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

  function rememberMission(planId: string, missionId: string) {
    try {
      const map = JSON.parse(
        localStorage.getItem(PLAN_MISSION_KEY) ?? "{}",
      ) as Record<string, string>;
      map[planId] = missionId;
      localStorage.setItem(PLAN_MISSION_KEY, JSON.stringify(map));
    } catch {
      /* non-essential bookkeeping */
    }
  }

  function missionForPlan(planId: string): string | null {
    try {
      const map = JSON.parse(
        localStorage.getItem(PLAN_MISSION_KEY) ?? "{}",
      ) as Record<string, string>;
      return map[planId] ?? null;
    } catch {
      return null;
    }
  }

  const company = companies.find((c) => c.id === companyId) ?? null;

  const value: StartupContextValue = {
    companyId,
    companies,
    company,
    setCompanyId,
    href: (path: string) =>
      companyId ? `${path}?companyId=${encodeURIComponent(companyId)}` : path,
    rememberMission,
    missionForPlan,
  };

  return (
    <StartupContext.Provider value={value}>
      <div className="space-y-6">
        <StartupHeader />
        {!loaded ? (
          <div className="h-48 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
        ) : (
          children
        )}
      </div>
    </StartupContext.Provider>
  );
}

const SUB_NAV = [
  { href: "/startup", label: "Overview", icon: Rocket },
  { href: "/startup/missions", label: "Missions", icon: ListChecks },
  { href: "/startup/operations", label: "Operations", icon: GitBranch },
  { href: "/startup/products", label: "Products", icon: Package },
  { href: "/startup/projects", label: "Projects", icon: Bot },
  { href: "/startup/approvals", label: "Approvals", icon: ShieldCheck },
  { href: "/startup/mission-graph", label: "Mission Graph", icon: GitBranch },
  { href: "/startup/feedback", label: "Feedback", icon: CheckCircle2 },
];

function StartupHeader() {
  const pathname = usePathname();
  const { companies, company, companyId, setCompanyId } = useStartup();
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-zinc-500">
            Phase 9 · Autonomous Startup Engine
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            Autonomous Startup
          </h1>
        </div>
        {companies.length > 0 && (
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Operating company
            </span>
            <select
              value={companyId ?? ""}
              onChange={(e) => setCompanyId(e.target.value)}
              className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            >
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
          {company.name}
          {company.industry ? ` · ${company.industry}` : ""}
          {company.mission ? ` — ${company.mission}` : ""}
        </p>
      )}

      <nav className="flex flex-wrap gap-1 border-b border-zinc-200 pb-2 dark:border-zinc-800">
        {SUB_NAV.map((item) => (
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