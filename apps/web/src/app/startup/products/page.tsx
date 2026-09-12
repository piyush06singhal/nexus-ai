"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Package, Plus } from "lucide-react";
import { createProduct, fetchProducts } from "@/lib/api";
import type { Product } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { useStartup } from "../_components/StartupShell";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; products: Product[] }
  | { kind: "error"; message: string };

export default function ProductsPage() {
  const { companyId, href } = useStartup();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    fetchProducts(companyId)
      .then((products) => !cancelled && setState({ kind: "ok", products }))
      .catch((err: Error) =>
        !cancelled && setState({ kind: "error", message: err.message }),
      );
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  function reload() {
    if (!companyId) return;
    fetchProducts(companyId)
      .then((products) => setState({ kind: "ok", products }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
            Products
          </h2>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Lifecycle tracking, deterministic validation, and governed launch.
            Product rows are seeded when a startup plan is bootstrapped.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          <Plus className="h-4 w-4" />
          New product
        </button>
      </div>

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
          {state.message}
        </p>
      )}

      {showForm && companyId && (
        <ProductForm
          companyId={companyId}
          onCreated={() => {
            setShowForm(false);
            reload();
          }}
        />
      )}

      {state.kind === "loading" && (
        <div className="h-48 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
      )}

      {state.kind === "ok" && state.products.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <Package className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            No products yet. They are created when a startup plan is
            bootstrapped.
          </p>
        </div>
      )}

      {state.kind === "ok" && state.products.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {state.products.map((p) => (
            <div
              key={p.id}
              className="flex flex-col rounded-xl border border-zinc-200 bg-white p-5 transition hover:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:border-zinc-600"
            >
              <Link
                href={href(`/startup/products/${p.id}`)}
                className="flex items-start justify-between"
              >
                <h3 className="font-semibold text-zinc-900 dark:text-zinc-100">
                  {p.name}
                </h3>
                <StatusBadge status={p.status} />
              </Link>
              <p className="mt-1 text-xs uppercase tracking-wide text-zinc-500">
                {p.product_type ?? "product"}
              </p>
              {p.value_proposition && (
                <p className="mt-2 line-clamp-2 text-sm text-zinc-600 dark:text-zinc-400">
                  {p.value_proposition}
                </p>
              )}
              <Link
                href={href(`/startup/products/${p.id}`)}
                className="ml-auto mt-auto pt-3 text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
              >
                Open →
              </Link>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ProductForm({
  companyId,
  onCreated,
}: {
  companyId: string;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [productType, setProductType] = useState("");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createProduct({
        company_id: companyId,
        name,
        product_type: productType || undefined,
        value_proposition: value || undefined,
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create product");
    } finally {
      setBusy(false);
    }
  }

  const base =
    "w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

  return (
    <form
      onSubmit={submit}
      className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950"
    >
      <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
        Create product
      </h3>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field label="Name" required>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className={base}
            placeholder="e.g. AI Developer Productivity Platform"
          />
        </Field>
        <Field label="Product type">
          <input
            value={productType}
            onChange={(e) => setProductType(e.target.value)}
            className={base}
            placeholder="e.g. software"
          />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Value proposition">
            <input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className={base}
              placeholder="What value does it deliver?"
            />
          </Field>
        </div>
      </div>
      {error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}
      <div className="mt-4">
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900"
        >
          {busy ? "Creating…" : "Create product"}
        </button>
      </div>
    </form>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-zinc-500 dark:text-zinc-400">
        {label}
        {required && <span className="text-red-500"> *</span>}
      </span>
      {children}
    </label>
  );
}