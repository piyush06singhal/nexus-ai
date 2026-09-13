import type { ReactNode } from "react";
import { Phase12Shell } from "@/components/phase12/Phase12Shell";

export const metadata = {
  title: "Experiment Center — NEXUS",
  description:
    "Controlled comparisons of baselines vs variants with honest significance. Experiment Center — Phase 12 Experimentation.",
};

export default function ExperimentsLayout({ children }: { children: ReactNode }) {
  return (
    <Phase12Shell
      center="experiments"
      eyebrow="Phase 12 · Experimentation"
      title="Experiment Center"
      description="Controlled comparisons of baselines vs variants. Statements of significance are honest — sample sizes and limitations are always shown, and results never claim more than the data supports."
    >
      {children}
    </Phase12Shell>
  );
}