import { redirect } from "next/navigation";

export const metadata = { title: "Missions — NEXUS" };

/**
 * Missions moved into the Autonomous Startup Engine (Phase 9) as part of the
 * mission → plan → bootstrap → operating-cycle pipeline. The legacy route now
 * redirects into the startup section, which resolves the operating company.
 */
export default function MissionsPage() {
  redirect("/startup/missions");
}
