import type { ReactNode } from "react";
import { Phase12Shell } from "@/components/phase12/Phase12Shell";

export const metadata = {
  title: "Simulation Center — NEXUS",
  description:
    "Modeled what-if scenarios over a company digital twin — baselines, stress tests, and forecasts. Simulation Center — Phase 12 Simulation & Intelligence.",
};

export default function SimulationsLayout({ children }: { children: ReactNode }) {
  return (
    <Phase12Shell
      center="simulation"
      eyebrow="Phase 12 · Simulation &amp; Intelligence"
      title="Simulation Center"
      description="Modeled what-if scenarios over a company digital twin — baselines, stress tests, and forecasts. Simulated outputs are modeled estimates and are always labeled SIMULATED / FORECAST — never actual results."
    >
      {children}
    </Phase12Shell>
  );
}