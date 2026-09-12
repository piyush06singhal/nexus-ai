"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import {
  getProduct,
  launchProduct,
  moveProductStatus,
  validateProduct,
} from "@/lib/api";
import type { Product, ProductStatus, ValidationResult } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { useStartup } from "../../_components/StartupShell";
import { ActionButton, Dash, SectionCard, StringList } from "../../_components/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; product: Product; validation: ValidationResult | null }
  | { kind: "error"; message: string };

const NEXT: Record<ProductStatus, ProductStatus[]> = {
  idea: ["discovery", "paused", "retired"],
  discovery: ["validation", "paused"],
  validation: ["planning", "building", "paused"],
  planning: ["building", "paused"],
  building: ["testing", "paused"],
  testing: ["ready_for_launch", "building", "paused"],
  ready_for_launch: ["launched", "testing", "paused"],
  launched: ["measuring", "iterating", "paused"],
  measuring: ["iterating", "paused", "retired"],
  iterating: ["measuring", "paused"],
  paused: ["discovery", "planning", "building"],
  retired: [],
};

export default function ProductDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { companyId, href } = useStartup();
  const [productId, setProductId] = useState("");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    params.then((p) => setProductId(p.id));
  }, [params]);

  useEffect(() => {
    if (!companyId || !productId) return;
    let cancelled = false;
    getProduct(companyId, productId)
      .then((product) =>
        !cancelled && setState({ kind: "ok", product, validation: null }),
      )
      .catch((err: Error) =>
        !cancelled && setState({ kind: "error", message: err.message }),
      );
    return () => {
      cancelled = true;
    };
  }, [companyId, productId]);

  async function act(action: "validate" | "launch") {
    if (!companyId || !productId) return;
    setBusy(true);
    setMsg(null);
    try {
      if (action === "validate") {
        const v = await validateProduct(companyId, productId);
        setState((s) => (s.kind === "ok" ? { ...s, validation: v } : s));
      }
      if (action === "launch") {
        const p = await launchProduct(companyId, productId);
        setState((s) => (s.kind === "ok" ? { ...s, product: p } : s));
        setMsg(`Product launched (${p.status}).`);
      }
    } catch (err) {
      setMsg(err instanceof Error ? err.message : `Action '${action}' failed`);
    } finally {
      setBusy(false);
    }
  }

  async function move(target: ProductStatus) {
    if (!companyId || !productId) return;
    setBusy(true);
    setMsg(null);
    try {
      const p = await moveProductStatus(companyId, productId, target);
      setState((s) => (s.kind === "ok" ? { ...s, product: p } : s));
      setMsg(`Moved to ${p.status}.`);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Lifecycle move failed");
    } finally {
      setBusy(false);
    }
  }

  if (state.kind === "loading") {
    return <div className="h-64 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />;
  }
  if (state.kind === "error") {
    return (
      <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
        {state.message}
      </p>
    );
  }

  const { product } = state;
  const next = NEXT[product.status] ?? [];

  return (
    <div className="space-y-6">
      <Link
        href={href("/startup/products")}
        className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
      >
        <ArrowLeft className="h-4 w-4" /> Products
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
              {product.name}
            </h1>
            <StatusBadge status={product.status} />
          </div>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            {product.product_type ?? "product"} · priority {product.strategic_priority}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <ActionButton onClick={() => act("validate")} busy={busy}>
            Validate
          </ActionButton>
          <ActionButton onClick={() => act("launch")} busy={busy}>
            Launch
          </ActionButton>
          {next.map((t) => (
            <ActionButton key={t} onClick={() => move(t)} busy={busy}>
              → {t.replace("_", " ")}
            </ActionButton>
          ))}
        </div>
      </div>

      {product.value_proposition && (
        <p className="max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
          {product.value_proposition}
        </p>
      )}

      {msg && (
        <p className="rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300">
          {msg}
        </p>
      )}

      {state.validation && (
        <SectionCard title="Launch readiness validation">
          <div className="space-y-2">
            <p className="text-sm">
              Verdict: <StatusBadge status={state.validation.ok ? "pass" : "fail"} />
            </p>
            {state.validation.errors.map((e, i) => (
              <p key={i} className="text-sm text-red-700 dark:text-red-400">
                [{e.code}] {e.message}
              </p>
            ))}
            {state.validation.warnings.map((w, i) => (
              <p key={i} className="text-sm text-amber-700 dark:text-amber-400">
                [{w.code}] {w.message}
              </p>
            ))}
          </div>
        </SectionCard>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard title="Success metrics">
          <StringList value={product.success_metrics} />
        </SectionCard>
        <SectionCard title="Launch criteria">
          <StringList value={product.launch_criteria} />
        </SectionCard>
        <SectionCard title="Target users">
          <StringList value={Array.isArray(product.target_users) ? product.target_users : null} />
        </SectionCard>
        <SectionCard title="Budget">
          {product.budget ? (
            <pre className="whitespace-pre-wrap rounded bg-zinc-50 p-3 text-xs text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
              {JSON.stringify(product.budget, null, 2)}
            </pre>
          ) : (
            <Dash value={null} />
          )}
        </SectionCard>
      </div>
    </div>
  );
}