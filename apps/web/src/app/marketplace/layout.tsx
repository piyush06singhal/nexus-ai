import type { ReactNode } from "react";
import { Phase12Shell } from "@/components/phase12/Phase12Shell";

export const metadata = {
  title: "Agent Marketplace — NEXUS",
  description:
    "Internal metadata-only agent packages — capabilities, versions, benchmarks, and reputation. Agent Marketplace — Phase 12.",
};

export default function MarketplaceLayout({ children }: { children: ReactNode }) {
  return (
    <Phase12Shell
      center="marketplace"
      eyebrow="Phase 12 · Agent Marketplace"
      title="Agent Marketplace"
      description="Internal metadata-only package registry — capabilities, versions, benchmarks, and reputation. Packages never bundle secrets, credentials, memories, or executable payloads, and installing never silently replaces production agents."
    >
      {children}
    </Phase12Shell>
  );
}