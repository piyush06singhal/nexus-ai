"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  Activity,
  Globe,
  MonitorSmartphone,
  Network,
  ShieldCheck,
} from "lucide-react";
import { fetchCompanies } from "@/lib/api";
import type { Company } from "@/lib/types";
import { cn } from "@/lib/cn";

const STORAGE_KEY = "nexus.external.companyId";

/** The company every /integrations,/browser,/computer page operates on. */
export interface ExternalContextValue {
  companyId: string | null;
  companies: Company[];
  company: Company | null;
  setCompanyId: (id: string) => void;
  /** href builder carrying the selected company. */
  href: (path: string) => string;
}

const ExternalContext = createContext<ExternalContextValue | null>(null);

export function useExternal() {
  const ctx = useContext(ExternalContext);
  if (!ctx) throw new Error("useExternal must be used within <ExternalShell>");
  return ctx;
}

/** Client shell for the External Integrations suite: company selector + sub-nav. */
export function ExternalShell({ children }: { children: ReactNode }) {
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

  const company = companies.find((c) => c.id === companyId) ?? null;

  const value: ExternalContextValue = {
    companyId,
    companies,
    company,
    setCompanyId,
    href: (path: string) =>
      companyId ? `${path}?companyId=${encodeURIComponent(companyId)}` : path,
  };

  return (
    <ExternalContext.Provider value={value}>
      <div className="space-y-6">
        <ExternalHeader />
        {!loaded ? (
          <div className="h-48 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
        ) : (
          children
        )}
      </div>
    </ExternalContext.Provider>
  );
}

const SUB_NAV = [
  { href: "/integrations", label: "Integrations", icon: Network },
  { href: "/integrations/actions", label: "Actions", icon: Activity },
  { href: "/integrations/events", label: "Events", icon: ShieldCheck },
  { href: "/browser", label: "Browser", icon: Globe },
  { href: "/computer", label: "Computer", icon: MonitorSmartphone },
];

function ExternalHeader() {
  const pathname = usePathname();
  const { companies, company, companyId, setCompanyId } = useExternal();
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-zinc-500">
            Phase 10 · External Integrations & Computer Use
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            External Integrations
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