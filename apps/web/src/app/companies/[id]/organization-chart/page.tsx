"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { fetchOrgChart } from "@/lib/api";
import type { EmployeeStatus, OrgChartNode } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; root: OrgChartNode }
  | { kind: "error"; message: string };

export default function OrgChartPage({ params }: { params: Promise<{ id: string }> }) {
  const [companyId, setCompanyId] = useState<string>("");
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    params.then((p) => setCompanyId(p.id));
  }, [params]);

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    fetchOrgChart(companyId)
      .then((root) => {
        if (!cancelled) setState({ kind: "ok", root });
      })
      .catch((err) => {
        if (!cancelled) {
          setState({
            kind: "error",
            message: err instanceof Error ? err.message : "Failed to load org chart",
          });
        }
      });
    return () => { cancelled = true; };
  }, [companyId]);

  return (
    <div className="space-y-6">
      <Link href={`/companies/${companyId}`} className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
        <ArrowLeft className="h-4 w-4" /> Company
      </Link>

      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">Organization chart</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Reporting structure built from departments, roles, and memberships.
        </p>
      </div>

      {state.kind === "loading" && <div className="h-64 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />}

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{state.message}</p>
      )}

      {state.kind === "ok" && (
        <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
          <OrgNode node={state.root} />
        </div>
      )}
    </div>
  );
}

function OrgNode({ node, depth = 0 }: { node: OrgChartNode; depth?: number }) {
  return (
    <div className="flex flex-col items-center">
      <div
        className={
          node.type === "company"
            ? "min-w-[180px] rounded-xl border border-zinc-900 bg-zinc-900 px-4 py-2 text-center dark:border-white dark:bg-white"
            : node.type === "department"
              ? "min-w-[160px] rounded-xl border border-zinc-300 bg-zinc-50 px-4 py-2 text-center dark:border-zinc-700 dark:bg-zinc-900"
              : "min-w-[140px] rounded-xl border border-zinc-200 bg-white px-4 py-2 text-center dark:border-zinc-700 dark:bg-zinc-950"
        }
      >
        <p
          className={
            node.type === "company"
              ? "text-sm font-semibold text-white dark:text-zinc-900"
              : "text-sm font-medium text-zinc-900 dark:text-zinc-100"
          }
        >
          {node.name}
        </p>
        <p className="text-[10px] uppercase tracking-wide text-zinc-500">{node.type}</p>
        {node.status && <StatusBadge status={node.status as EmployeeStatus} />}
      </div>

      {node.children.length > 0 && (
        <>
          <div className="h-5 w-px bg-zinc-300 dark:bg-zinc-700" />
          <div className="flex items-start gap-4">
            {node.children.map((child) => (
              <div key={child.id} className="flex flex-col items-center">
                <div className="h-5 w-px bg-zinc-300 dark:bg-zinc-700" />
                <OrgNode node={child} depth={depth + 1} />
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}