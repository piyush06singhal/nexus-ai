"use client";

/**
 * Shared company-scope resolution for standalone pages (final-pass §44:
 * factories out the fetch-companies + localStorage-selection logic that the
 * section shells each duplicate inline).
 *
 * Usage:
 *   const scope = useCompanyScope("nexus.approvals.companyId");
 *   if (!scope.loaded) return <Loading />;
 *   if (!scope.companyId) return <Empty />;   // no companies yet
 */

import { useEffect, useState } from "react";
import { fetchCompanies } from "@/lib/api";
import type { Company } from "@/lib/types";

export interface CompanyScope {
  companies: Company[];
  company: Company | null;
  companyId: string | null;
  loaded: boolean;
  setCompanyId: (id: string) => void;
}

export function useCompanyScope(storageKey: string): CompanyScope {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyIdState] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchCompanies()
      .then((list) => {
        if (cancelled) return;
        setCompanies(list);
        const saved = window.localStorage.getItem(storageKey);
        const initial =
          list.find((c) => c.id === saved)?.id ?? list[0]?.id ?? null;
        if (initial) window.localStorage.setItem(storageKey, initial);
        setCompanyIdState(initial);
        setLoaded(true);
      })
      .catch(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [storageKey]);

  function setCompanyId(id: string) {
    window.localStorage.setItem(storageKey, id);
    setCompanyIdState(id);
  }

  const company = companies.find((c) => c.id === companyId) ?? null;
  return { companies, company, companyId, loaded, setCompanyId };
}