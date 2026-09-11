import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BarChart3,
  Bell,
  Bot,
  Brain,
  Building2,
  ClipboardList,
  GitBranch,
  LayoutDashboard,
  ListChecks,
  Network,
  RefreshCw,
  Settings,
  ShieldCheck,
  Target,
  TrendingUp,
  Users,
  Wrench,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

/** Primary navigation sections shown in the sidebar and dashboard. */
export const NAV_SECTIONS: NavItem[] = [
  { href: "/companies", label: "Companies", description: "AI company layer — departments, goals, KPIs, budgets, decisions, risks, and health.", icon: Building2 },
  { href: "/missions", label: "Missions", description: "High-level business objectives the workforce is working toward.", icon: Target },
  { href: "/agents", label: "Agents", description: "Individual AI agents and their roles, capabilities, and status.", icon: Bot },
  { href: "/employees", label: "Employees", description: "AI employees with roles, skills, goals, and performance tracking.", icon: Users },
  { href: "/employee-workbench", label: "Workbench", description: "Employee task assignments, priorities, and today's work.", icon: ClipboardList },
  { href: "/employee-goals", label: "Goals", description: "Goal dashboard — progress, targets, and deadlines across employees.", icon: Target },
  { href: "/employee-performance", label: "Performance", description: "Employee performance metrics, reviews, and comparisons.", icon: TrendingUp },
  { href: "/tasks", label: "Tasks", description: "Discrete units of work assigned to and executed by agents.", icon: ListChecks },
  { href: "/workflows", label: "Workflows", description: "Multi-step orchestrated workflows with triggers, conditions, and retries.", icon: GitBranch },
  { href: "/orchestrations", label: "Orchestrations", description: "Multi-agent teams coordinating on shared objectives — plan, assign, execute, collaborate.", icon: Network },
  { href: "/tools", label: "Tools", description: "Tool definitions available to agents during execution.", icon: Wrench },
  { href: "/memories", label: "Memories", description: "Agent memory store — episodic, semantic, and working memory.", icon: Brain },
  { href: "/verifications", label: "Verifications", description: "Deterministic and model-based verification of agent, workflow, and orchestration outputs.", icon: ShieldCheck },
  { href: "/recoveries", label: "Recoveries", description: "Failure diagnosis and bounded, policy-driven recovery of failed executions.", icon: RefreshCw },
  { href: "/evaluations", label: "Evaluations", description: "Metrics, run comparison, and regression detection across cases and targets.", icon: BarChart3 },
  { href: "/escalations", label: "Escalations", description: "Human-in-the-loop review of executions that could not recover safely.", icon: Bell },
  { href: "/activity", label: "Activity", description: "A live feed of agent actions, tool calls, and system events.", icon: Activity },
  { href: "/approvals", label: "Approvals", description: "Actions awaiting human review before execution proceeds.", icon: ShieldCheck },
  { href: "/settings", label: "Settings", description: "Workforce, provider, security, and infrastructure configuration.", icon: Settings },
];

export const SIDEBAR_ITEMS: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  ...NAV_SECTIONS.map(({ href, label, icon }) => ({ href, label, icon })),
];