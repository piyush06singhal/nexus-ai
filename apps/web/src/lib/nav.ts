import type { LucideIcon } from "lucide-react";
import {
  Activity,
  Bot,
  LayoutDashboard,
  ListChecks,
  Settings,
  ShieldCheck,
  Target,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

/** Primary navigation sections shown in the sidebar and dashboard. */
export const NAV_SECTIONS: NavItem[] = [
  { href: "/missions", label: "Missions", description: "High-level business objectives the workforce is working toward.", icon: Target },
  { href: "/agents", label: "Agents", description: "Individual AI agents and their roles, capabilities, and status.", icon: Bot },
  { href: "/tasks", label: "Tasks", description: "Discrete units of work assigned to and executed by agents.", icon: ListChecks },
  { href: "/activity", label: "Activity", description: "A live feed of agent actions, tool calls, and system events.", icon: Activity },
  { href: "/approvals", label: "Approvals", description: "Actions awaiting human review before execution proceeds.", icon: ShieldCheck },
  { href: "/settings", label: "Settings", description: "Workforce, provider, security, and infrastructure configuration.", icon: Settings },
];

export const SIDEBAR_ITEMS: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  ...NAV_SECTIONS.map(({ href, label, icon }) => ({ href, label, icon })),
];