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
  Rocket,
  Settings,
  ShieldCheck,
  Target,
  TrendingUp,
  Users,
  Wrench,
  Globe,
  MonitorSmartphone,
  KeyRound,
  ScrollText,
  Siren,
  HeartPulse,
  UserCog,
  ShieldAlert,
  FlaskConical,
  Beaker,
  Layers,
  GitCompare,
  SlidersHorizontal,
  ThumbsUp,
  Store,
  Sparkles,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

/** Primary navigation sections shown in the sidebar and dashboard. */
export const NAV_SECTIONS: NavItem[] = [
  { href: "/startup", label: "Autonomous Startup", description: "Mission-driven autonomous startup engine — mission graph, operating cycles, governance, and feedback.", icon: Rocket },
  { href: "/missions", label: "Missions", description: "Startup missions — objectives, analysis, strategy, plans, and mission-graph traceability.", icon: Target },
  { href: "/companies", label: "Companies", description: "AI company layer — departments, goals, KPIs, budgets, decisions, risks, and health.", icon: Building2 },
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
  // ── Phase 10: External Integrations & Computer Use ──
  { href: "/integrations", label: "External Integrations", description: "Governed external integrations — connections, capabilities, external-action journal, and events.", icon: Network },
  { href: "/integrations/actions", label: "External Actions", description: "The external-action journal — risk, approval, execution, verification, and recovery timeline.", icon: Activity },
  { href: "/browser", label: "Browser Use", description: "Bounded simulated browser sessions with structured untrusted observations and domain policy.", icon: Globe },
  { href: "/computer", label: "Computer Use", description: "Bounded simulated desktop sessions with sensitive purchase-path approval.", icon: MonitorSmartphone },
  // ── Phase 11: Security, Governance & Production Hardening ──
  { href: "/control", label: "Control Center", description: "Security posture, governance, audit chain, incidents, and system health.", icon: ShieldCheck },
  { href: "/control/governance", label: "Governance", description: "Kill switch scopes, resource limits, policies, and break-glass access.", icon: ShieldAlert },
  { href: "/control/security", label: "Security", description: "Security events and alerts from the Phase 11 detection pipeline.", icon: Siren },
  { href: "/control/incidents", label: "Incidents", description: "Incident lifecycle with audited containment actions.", icon: ScrollText },
  { href: "/control/audit", label: "Audit", description: "Append-only hash-chained audit trail with chain verification.", icon: UserCog },
  { href: "/control/health", label: "Health", description: "Live/readiness/dependency probes, metrics, and health records.", icon: HeartPulse },
  { href: "/control/access", label: "Access", description: "Users, roles, permissions, and secret references (never values).", icon: KeyRound },
  // ── Phase 12: Simulation, Optimization & Agent Marketplace ──
  { href: "/simulations", label: "Simulation Center", description: "Modeled what-if scenarios — company digital twins, baselines, forecasts, and comparisons. Simulated outputs are estimates, never ACTUAL.", icon: FlaskConical },
  { href: "/simulations/scenarios", label: "Scenarios", description: "Simulation scenarios — baseline, what-if, stress, capacity, and risk tests across a modeled company.", icon: Layers },
  { href: "/simulations/compare", label: "Compare", description: "Baseline-versus-scenario comparison — KPI, cost, time, utilization, and risk deltas.", icon: GitCompare },
  { href: "/optimization", label: "Optimization", description: "Multi-objective optimization problems — constraints, candidates, scores, and tradeoffs.", icon: SlidersHorizontal },
  { href: "/optimization/recommendations", label: "Recommendations", description: "Explainable optimization recommendations that require explicit approval before any execution.", icon: ThumbsUp },
  { href: "/experiments", label: "Experiments", description: "Controlled A/B-style experiments — variants, metrics, results, and honest confidence.", icon: Beaker },
  { href: "/marketplace", label: "Agent Marketplace", description: "Internal metadata-only agent packages — capabilities, versions, benchmarks, reputation, and safe installs.", icon: Store },
  { href: "/marketplace/recommendations", label: "Agent Recommendations", description: "Evidence-based agent recommendations — ranked on real benchmark and reliability data only.", icon: Sparkles },
  { href: "/settings", label: "Settings", description: "Workforce, provider, security, and infrastructure configuration.", icon: Settings },
];

export const SIDEBAR_ITEMS: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  ...NAV_SECTIONS.map(({ href, label, icon }) => ({ href, label, icon })),
];