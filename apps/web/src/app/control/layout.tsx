import type { ReactNode } from "react";
import { ControlShell } from "./_components/ControlShell";

export const metadata = {
  title: "Control Center — NEXUS",
  description:
    "Security posture, governance, audit chain, incidents, and system health — Phase 11 Security, Governance & Production Hardening.",
};

export default function ControlLayout({ children }: { children: ReactNode }) {
  return <ControlShell>{children}</ControlShell>;
}