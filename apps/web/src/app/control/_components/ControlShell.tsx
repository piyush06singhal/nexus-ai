"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  KeyRound,
  HeartPulse,
  ScrollText,
  ShieldAlert,
  ShieldCheck,
  Siren,
} from "lucide-react";
import { fetchCompanies } from "@/lib/api";
import type { Company } from "@/lib/types";
import { cn } from "@/lib/cn";

const STORAGE_KEY = "nexus.control.companyId";

/** The company the Control Center pages operate on (optional filter). */
export interface ControlContextValue {
  companyId: string | null;
  companies: Company[];
  company: Company | null;
  setCompanyId: (id: string) => void;
  href: (path: string) => string;
}

const ControlContext = createContext<ControlContextValue | null>(null);

export function useControl() {
  const ctx = useContext(ControlContext);
  if (!ctx) throw new Error("useControl must be used within <ControlShell>");
  return ctx;
}

/** Client shell for the Phase 11 Control Center: company selector + sub-nav. */
export function ControlShell({ children }: { children: ReactNode }) {
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

  const value: ControlContextValue = {
    companyId,
    companies,
    company,
    setCompanyId,
    href: (path: string) =>
      companyId ? `${path}?companyId=${encodeURIComponent(companyId)}` : path,
  };

  return (
    <ControlContext.Provider value={value}>
      <div className="space-y-6">
        <ControlHeader />
        {!loaded ? (
          <div className="h-48 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
        ) : (
          children
        )}
      </div>
    </ControlContext.Provider>
  );
}

const SUB_NAV = [
  { href: "/control", label: "Overview", icon: ShieldCheck },
  { href: "/control/governance", label: "Governance", icon: ShieldAlert },
  { href: "/control/security", label: "Security", icon: Siren },
  { href: "/control/incidents", label: "Incidents", icon: ScrollText },
  { href: "/control/audit", label: "Audit", icon: KeyRound },
  { href: "/control/health", label: "Health", icon: HeartPulse },
  { href: "/control/access", label: "Access", icon: ShieldCheck },
];

function ControlHeader() {
  const pathname = usePathname();
  const { companies, company, companyId, setCompanyId } = useControl();
  const active = SUB_NAV.find((item) => pathname === item.href);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-zinc-500">
            Phase 11 · Security, Governance &amp; Production Hardening
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            Control Center
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

      {active ? (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          <span className="font-medium text-zinc-900 dark:text-zinc-100">
            {active.label}
          </span>{" "}
          — the invariant chain: IDENTITY → AUTHORIZATION → POLICY → RESOURCE
          LIMIT → APPROVAL → ACTION → VERIFICATION → AUDIT → OBSERVABILITY →
          RECOVERY. Every refusal is recorded, never silently dropped.
        </p>
      ) : null}

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