import type { ReactNode } from "react";
import { ExternalShell } from "./_components/ExternalShell";

export const metadata = {
  title: "External Integrations — NEXUS",
  description:
    "Governed external integrations, external actions, browser use, and computer use — with risk, approval, verification, and audit on every action.",
};

export default function ExternalLayout({ children }: { children: ReactNode }) {
  return <ExternalShell>{children}</ExternalShell>;
}