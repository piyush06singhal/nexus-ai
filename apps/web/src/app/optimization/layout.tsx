import type { ReactNode } from "react";
import { Phase12Shell } from "@/components/phase12/Phase12Shell";

export const metadata = {
  title: "Optimization Center — NEXUS",
  description:
    "Multi-objective optimization that proposes — never applies. Every recommendation is explainable and requires explicit approval. Phase 12.",
};

export default function OptimizationLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <Phase12Shell
      center="optimization"
      eyebrow="Phase 12 · Optimization"
      title="Optimization Center"
      description="Multi-objective optimization that proposes — never applies. Every recommendation is explainable and requires explicit approval."
    >
      {children}
    </Phase12Shell>
  );
}