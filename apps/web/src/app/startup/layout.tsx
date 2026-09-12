import type { ReactNode } from "react";
import { StartupShell } from "./_components/StartupShell";

export const metadata = {
  title: "Autonomous Startup — NEXUS",
  description:
    "Mission-driven autonomous startup engine — missions, strategic plans, operating cycles, governance, approval gates, feedback, and traceability.",
};

export default function StartupLayout({ children }: { children: ReactNode }) {
  return <StartupShell>{children}</StartupShell>;
}