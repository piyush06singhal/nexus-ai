"""Seed the NEXUS Autonomous AI Startup demo (§51).

Deterministic end-to-end chain for the Autonomous Startup Engine:

  company → mission → analyze → validate → strategic plan (derived) →
  startup plan (derived) → validate → approve → bootstrap company
  (departments → workforce → KPIs → budgets → products → projects → goals)
  → product lifecycle + governed launch → tasks → operating cycle
  (observe→assess→plan→prioritize→allocate→execute→verify→measure→learn→replan)
  → injected task failure → recovery → feedback → replan evaluation →
  approval gates (replan + product-dev budget +20%) → resumed cycle →
  mission-graph query → final state summary.

Everything runs through the real Phase 8 + Phase 9 services with the
deterministic MockProvider — no model API required. The one injected failure
is driven by temporarily misconfiguring a provisioned agent's mock reply, then
restoring it, so recovery is exercised through ``Executor``/``RecoveryService``
exactly as a real failure would be.

Idempotent: a company/mission with the same name is reused and the seed fills
in any missing pieces.

Run from ``apps/api``:
    .venv/bin/python -m scripts.seed_autonomous_startup [--reset]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

# Ensure ``app.db.session`` resolves when run as a script inside apps/api.
sys.path.insert(0, ".")

from app.db.models.startup import (  # noqa: E402
    Mission,
    StartupPlan,
    StartupPlanStatus,
)
from app.db.session import Base, SessionLocal  # noqa: E402

# ── Demo definitions ──────────────────────────────────────────────────────────

DEMO_COMPANY_NAME = "NEXUS Autonomous AI Startup"
MISSION_TITLE = "NEXUS Autonomous AI Startup"

DEMO_MISSION = {
    "title": MISSION_TITLE,
    "mission_statement": (
        "Build an AI-driven developer productivity platform for small software "
        "teams with verifiable operating cycles and bounded autonomy."
    ),
    "description": (
        "A deterministic Phase 9 demo mission that runs the full startup engine "
        "chain without any paid model provider."
    ),
    "desired_outcome": "A validated product released to an initial cohort with "
    "measurably improved team velocity.",
    "target_market": "small software teams",
    "constraints": [
        "Bounded autonomy only; no external integrations.",
        "Operating cycles must complete within configured limits.",
        "No autonomous finance, legal, hiring, or firing actions.",
    ],
    "assumptions": [
        "Small teams adopt AI-assisted development tooling.",
        "The mock execution provider is representative of task outcomes.",
    ],
    "success_criteria": [
        "Task success rate above 90%.",
        "Verification rate above 90%.",
        "Product reaches launch-ready stage within the operating cycle.",
    ],
    "strategic_context": {
        "phase": 9,
        "mode": "deterministic",
        "governance": "bounded_autonomy",
    },
    "priority": 1,
}

# The default backing-agent reply for provisioned employees (matches
# :class:`~app.employee.manager`). We temporarily replace it to inject a
# failure for the recovery demo, then restore it.
_DEFAULT_AGENT_REPLY = '{"summary":"ok","output":{"status":"done"}}'

# Roles chosen from the bootstrapped workforce for the demo tasks.
_TASKS = [
    {
        "title": "Define the core agent workflow for the productivity platform",
        "input": {"focus": "agent_workflow", "depth": "design"},
    },
    {
        "title": "Implement the developer CLI for the platform",
        "input": {"focus": "cli", "stack": "python"},
    },
    {
        "title": "Prepare the go-to-market brief for the initial cohort",
        "input": {"focus": "gtm", "segment": "small software teams"},
    },
]

_FAILING_TASK = {
    "title": "Research competitive alternatives for the AI development assistant",
    "input": {"focus": "competitor research", "segment": "developer tools"},
}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _loads(raw: Any) -> Any:
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


def _slugify(name: str) -> str:
    return name.lower().replace(" ", "-")


def _get_or_create_company(db: Session, name: str) -> Any:
    from app.company.manager import CompanyManager
    from app.db.models.company import Company

    existing = db.scalar(select(Company).where(Company.slug == _slugify(name)))
    if existing is not None:
        if existing.status.value != "active":
            CompanyManager(db).activate(existing.id)
        return existing
    return CompanyManager(db).create(name=name, description="Phase 9 demo startup.")


def _get_or_create_mission(db: Session, company_id: UUID) -> Any:
    from app.startup.mission import MissionManager

    mission = db.scalar(
        select(Mission).where(Mission.company_id == company_id, Mission.title == MISSION_TITLE)
    )
    if mission is not None:
        return mission
    return MissionManager(db).create(
        company_id=company_id,
        **{k: v for k, v in DEMO_MISSION.items() if k != "title"},
        title=MISSION_TITLE,
    )


def _latest_startup_plan(db: Session, mission_id: UUID) -> Any:

    return db.scalar(
        select(StartupPlan)
        .where(StartupPlan.mission_id == mission_id)
        .order_by(StartupPlan.created_at.desc())
        .limit(1)
    )


def _member_agent_ids(db: Session, company_id: UUID) -> list[UUID]:
    """Binding agent ids for every employee with a company membership."""
    from app.db.models.company import OrganizationalMembership
    from app.db.models.employee import AIEmployee

    memberships = list(
        db.execute(
            select(OrganizationalMembership).where(
                OrganizationalMembership.company_id == company_id
            )
        ).scalars()
    )
    emp_ids = [m.employee_id for m in memberships]
    if not emp_ids:
        return []
    emps = list(db.execute(select(AIEmployee).where(AIEmployee.id.in_(emp_ids))).scalars())
    return [e.agent_id for e in emps if e.agent_id is not None]


def _set_agent_reply(db: Session, agent_id: UUID, reply: str) -> None:
    from app.db.models.agent import Agent

    agent = db.get(Agent, agent_id)
    if agent is None:
        raise RuntimeError(f"Injected-failure agent {agent_id} no longer exists")
    agent.model_params = json.dumps({"reply": reply})
    db.commit()


def _queue_task(db: Session, agent_id: UUID, title: str, input_data: dict) -> Any:
    """Create a QUEUED task for an agent so the operating cycle picks it up."""
    from app.db.models.task import TaskStatus
    from app.schemas.task import TaskCreate
    from app.services.task_service import TaskService

    task = TaskService(db).create(
        TaskCreate(
            title=title,
            description=f"Demo task: {title}",
            input_data=input_data,
            assigned_agent_id=agent_id,
        )
    )
    task.status = TaskStatus.QUEUED
    db.commit()
    return task


def _create_gate(
    db: Session, company_id: UUID, gate_type: str, action: str, rationale: str
) -> UUID:
    """Create a pending approval gate and approve it (as the operator)."""
    from app.startup.gates import ApprovalGateManager

    manager = ApprovalGateManager(db)
    gate = manager.create(
        company_id=company_id,
        gate_type=gate_type,
        requested_action={"action": action, "detail": rationale},
        rationale=rationale,
        risk_level="medium",
    )
    manager.approve(company_id, gate.id, approver_id=None)
    return gate.id


def _print_gate(db: Session, company_id: UUID, gate_id: UUID) -> None:
    from app.startup.gates import ApprovalGateManager

    gate = ApprovalGateManager(db).get(company_id, gate_id)
    if gate is None:
        return
    data = ApprovalGateManager(db).to_dict(gate)
    print(f"      gate        : {data['gate_type']} [{data['status']}]")
    print(f"      requested   : {data['requested_action']}")


# ── Phases ───────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the NEXUS Autonomous AI Startup demo.")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate the demo company")
    args = parser.parse_args()

    Base.metadata.create_all(bind=SessionLocal.kw["bind"])

    with SessionLocal() as db:
        summary = _run_demo(db, reset=args.reset)
        _print_final_summary(db, summary)


def _run_demo(db: Session, *, reset: bool = False) -> dict[str, Any]:
    from app.db.models.company import Company
    from app.startup.autonomy import AutonomyService
    from app.startup.bootstrap import CompanyBootstrapper
    from app.startup.cycle import OperatingEngine
    from app.startup.feedback import FeedbackService
    from app.startup.gates import ApprovalGateManager
    from app.startup.graph import MissionGraphBuilder
    from app.startup.mission import MissionManager
    from app.startup.observe import ObservationLayer
    from app.startup.plans import StartupPlanManager
    from app.startup.products import ProductManager
    from app.startup.replan import ReplanningEngine
    from app.startup.types import FeedbackRecord

    if reset:
        existing = db.scalar(select(Company).where(Company.slug == _slugify(DEMO_COMPANY_NAME)))
        if existing is not None:
            db.delete(existing)
            db.commit()

    company = _get_or_create_company(db, DEMO_COMPANY_NAME)
    company_id = company.id
    mission = _get_or_create_mission(db, company_id)
    mission_id = mission.id

    print("\n=== Phase 1 — Company + mission ===")
    print(f"  company     : {company.name} ({company_id})")
    print(f"  mission     : {mission.title} [{mission.status.value}]")

    mgr = MissionManager(db)

    # ── Analysis + validation ──────────────────────────────────────────
    if mission.status.value == "draft":
        print("\n=== Phase 2 — Mission analysis + validation ===")
        analysis = mgr.analyze(mission).to_dict()
        print(f"  objectives  : {len(analysis['objectives'])} {analysis['objectives'][:2]}")
        print(f"  solution    : {analysis['proposed_solution']}")
        print(f"  capabilities: {analysis['required_capabilities']}")
        validation = mgr.validate(mission).to_dict()
        print(
            f"  validation  : ok={validation['ok']} "
            f"errors={len(validation['errors'])} warnings={len(validation['warnings'])}"
        )

        # ── Strategic + startup plan (derived) ─────────────────────────
        print("\n=== Phase 3 — Strategic + startup plan (derived) ===")
        planned = mgr.plan(mission)
        print(f"  mission     : {planned['status']}")
        print(f"  strategic   : {planned['strategic_plan_id']}")
        print(f"  startup plan: {planned['startup_plan_id']}")

        # ── Plan validation + approval ─────────────────────────────────
        plan = db.get(StartupPlan, UUID(planned["startup_plan_id"]))
        plan_manager = StartupPlanManager(db)
        plan_result = plan_manager.validate(plan).to_dict()
        print("\n=== Phase 4 — Startup plan validation + approval ===")
        print(
            f"  validation  : ok={plan_result['ok']} "
            f"errors={len(plan_result['errors'])} warnings={len(plan_result['warnings'])}"
        )
        plan_manager.approve(plan, actor="demo")
        print(f"  plan        : {plan.status.value}")
    else:
        plan = _latest_startup_plan(db, mission_id)
        print("\n  (mission already planned/active — reusing existing plan)")
        # Idempotency: a previous run may have crashed between plan creation
        # and approval, leaving a draft plan behind a planned mission. Recover
        # it by re-validating and approving so bootstrap can proceed.
        if plan is not None and plan.status.value == StartupPlanStatus.DRAFT.value:
            plan_manager = StartupPlanManager(db)
            plan_result = plan_manager.validate(plan).to_dict()
            print("  (recovering previously created draft plan)")
            print(
                f"  validation  : ok={plan_result['ok']} "
                f"errors={len(plan_result['errors'])} warnings={len(plan_result['warnings'])}"
            )
            plan_manager.approve(plan, actor="demo")
            print(f"  plan        : {plan.status.value}")

    # ── Bootstrap company (governed by an approved gate) ───────────────
    if plan is None:
        raise RuntimeError("No startup plan available for bootstrap")
    if plan.status.value in (StartupPlanStatus.APPROVED.value, StartupPlanStatus.ACTIVE.value):
        print("\n=== Phase 5 — Bootstrap company ===")
        if plan.status.value == "approved":
            gate_id = _create_gate(
                db,
                company_id,
                "company_bootstrap_approval",
                "provision_employee",
                "Bootstrap the startup company with a governed workforce.",
            )
            _print_gate(db, company_id, gate_id)
            boot = CompanyBootstrapper(db).bootstrap(plan, approved_gate_id=gate_id, actor="demo")
            print(f"  departments : {len(boot['departments'])}")
            print(f"  employees   : {len(boot['employees'])} provisioned")
            print(f"  products    : {len(boot['products'])}")
            print(f"  projects    : {len(boot['projects'])}")
            print(f"  goals       : {boot['goals']} | kpis: {boot['kpis']}")
        else:
            print("  (already bootstrapped — reusing the provisioned company)")
    else:
        raise RuntimeError(f"Startup plan is {plan.status.value}; cannot bootstrap")

    # ── Product lifecycle + governed launch ────────────────────────────
    print("\n=== Phase 6 — Product lifecycle + governed launch ===")
    products = ProductManager(db).list_(company_id)
    product = products[0] if products else None
    if product is None:
        raise RuntimeError("Bootstrap produced no products")
    lifecycle_stages = frozenset(
        {"idea", "discovery", "validation", "planning", "building", "testing"}
    )
    if product.status.value not in lifecycle_stages:
        print(f"  product     : {product.name} already {product.status.value} — skipping")
    else:
        product_id = product.id
        pm = ProductManager(db)
        for target in (
            "discovery",
            "validation",
            "planning",
            "building",
            "testing",
            "ready_for_launch",
        ):
            pm.lifecycle(company_id, product_id, target)
        readiness = pm.validate(company_id, product_id).to_dict()
        print(f"  product     : {product.name} → ready_for_launch")
        print(
            f"  readiness   : ok={readiness['ok']} "
            f"errors={len(readiness['errors'])} warnings={len(readiness['warnings'])}"
        )
        launch_gate = _create_gate(
            db,
            company_id,
            "product_launch_approval",
            "launch_product",
            f"Launch '{product.name}' for the initial cohort.",
        )
        _print_gate(db, company_id, launch_gate)
        pm.launch(company_id, product_id, approved_gate_id=launch_gate)
        print(f"  launch      : {pm.get(company_id, product_id).status.value}")

    # ── Work + clean operating cycle ───────────────────────────────────
    print("\n=== Phase 7 — Work + first operating cycle ===")
    agent_ids = _member_agent_ids(db, company_id)
    if not agent_ids:
        raise RuntimeError("No provisioned agents to run work")
    clean_agents = list(agent_ids)
    print(f"  agents      : {len(agent_ids)} member agents")
    for i, cfg in enumerate(_TASKS):
        agent_id = clean_agents[i % len(clean_agents)]
        task = _queue_task(db, agent_id, cfg["title"], cfg["input"])
        print(f"  queued task : {task.title[:58]} → {task.status.value}")

    engine = OperatingEngine(db)
    cycle1 = engine.run_cycle(
        company_id=company_id,
        mission_id=mission_id,
        startup_plan_id=plan.id,
        actor="demo",
    )
    _print_cycle(cycle1)

    # ── Injected failure → recovery → replan → approval gate ───────────
    print("\n=== Phase 8 — Injected failure → recovery → replan → approval ===")
    fail_agent = clean_agents[0]
    _set_agent_reply(db, fail_agent, "not a valid agent result")  # ← injection
    failing = _queue_task(
        db,
        fail_agent,
        _FAILING_TASK["title"],
        _FAILING_TASK["input"],
    )
    print(f"  injected    : research task '{failing.title[:44]}…' fails on first attempt")

    cycle2 = engine.run_cycle(
        company_id=company_id,
        mission_id=mission_id,
        startup_plan_id=plan.id,
        actor="demo",
    )
    _print_cycle(cycle2, label="cycle 2")

    recovery_records = cycle2["recovery"] or []
    print(f"  recovery    : {len(recovery_records)} recovery attempt(s) recorded")
    for r in recovery_records:
        print(
            f"    attempt    : outcome={r.get('outcome')} strategy={r.get('strategy')}"
            f"{' error=' + r.get('error')[:120] if r.get('error') else ''}"
        )

    # Feedback surfaced from the degraded state.
    obs2 = ObservationLayer(db).observe(company_id)
    feedback = FeedbackService(db).list_(company_id, limit=5)
    print(f"  feedback    : {len(feedback)} signal(s) from the failed cycle")
    for f in feedback:
        print(f"    {f['category']:<24} conf={f['confidence']:.0%} — {f['recommendation']}")

    # Record one explicit operator feedback record (governed, advisory only).
    FeedbackService(db).record(
        company_id,
        FeedbackRecord(
            category="budget_pressure",
            observation="Product development needs headroom to absorb recovery cost.",
            source="demo-operator",
            impact="Blocked replanning + recovery consumed cycle capacity",
            confidence=0.85,
            recommendation="Approve a +20% product development budget with a gate.",
            objective_type={"kind": "budget"},
        ),
        mission_id=mission_id,
    )

    # Replan evaluation (non-executing decision) for visibility.
    decision = ReplanningEngine(db).evaluate(
        company_id=company_id,
        mission_id=mission_id,
        state=obs2,
    )
    print(
        f"  replan      : trigger={decision.trigger} → {decision.response.value} "
        f"(approval={'yes' if decision.requires_approval else 'no'})"
    )
    for a in decision.actions:
        print(f"    action     : {a.get('kind')} {a.get('detail', '')}")

    # Approve the replan gate the blocked cycle surfaced (if any).
    replan_gate_id = None
    if cycle2["status"] == "blocked":
        for entry in cycle2.get("approvals") or []:
            if entry.get("action") == "replan" and entry.get("gate_id"):
                replan_gate_id = UUID(entry["gate_id"])
        if replan_gate_id is None:
            pending_id = (cycle2.get("outcome") or {}).get("pending_gate_id")
            if pending_id:
                replan_gate_id = UUID(pending_id)
    if replan_gate_id is not None:
        ApprovalGateManager(db).approve(company_id, replan_gate_id, approver_id=None)
        print(f"  approval    : replan gate {replan_gate_id} approved")
        applied = ReplanningEngine(db).apply(
            company_id=company_id,
            decision=decision,
            approved_gate_id=replan_gate_id,
            actor="demo",
        )
        print(f"  replan      : applied actions → {applied['applied']}")

    # Approval gate for the budget increase (governed, operator-approves).
    from app.company.budget import BudgetManager
    from app.company.manager import CompanyManager
    from app.db.models.company import GoalScopeType

    company_current = CompanyManager(db).get(company_id)
    if getattr(company_current.status, "value", None) != "active":
        CompanyManager(db).activate(company_id)
    budget = BudgetManager(db).company_budget(company_id)
    allocation = _loads(plan.budget_allocation) or {}
    baseline = float((allocation or {}).get("company") or 1000.0)
    target = round(baseline * 1.2, 2)
    # Idempotency: the +20% bump applies once, anchored to the plan's
    # bootstrap baseline — never compounded on re-runs.
    if budget is None or float(budget.monthly_limit or 0.0) < target:
        budget_gate = _create_gate(
            db,
            company_id,
            "budget_approval",
            "allocate_budget",
            f"Increase the product development budget +20% ({baseline:.0f} → {target:.0f}).",
        )
        _print_gate(db, company_id, budget_gate)
        if budget is None:
            budget = BudgetManager(db).ensure_budget(
                company_id,
                GoalScopeType.COMPANY,
                company_id,
                monthly_limit=baseline,
            )
        BudgetManager(db).set_allocation(budget.id, monthly_limit=target, actor="demo")
        print(f"  budget      : {baseline:.0f} → {target:.0f} (monthly_limit)")
    else:
        print(f"  budget      : already at {budget.monthly_limit:g} (bump already applied)")

    # Restore the injected agent and queue replacement work.
    _set_agent_reply(db, fail_agent, _DEFAULT_AGENT_REPLY)
    restored_task = _queue_task(
        db,
        fail_agent,
        "Deliver the recovery follow-up for the research task",
        {"focus": "recovery follow-up"},
    )
    print(f"  restored    : agent reply restored; task '{restored_task.title[:48]}…' queued")

    cycle3 = engine.run_cycle(
        company_id=company_id,
        mission_id=mission_id,
        startup_plan_id=plan.id,
        actor="demo",
        approved_gate_id=replan_gate_id,
    )
    _print_cycle(cycle3, label="cycle 3 (resumed)")

    # ── Final state + leaderboard/graph ────────────────────────────────
    print("\n=== Phase 9 — Final state + mission graph ===")
    final = ObservationLayer(db).observe(company_id)
    print(f"  overall     : {final.overall_score:.2f}/1.00")
    for dim, score in sorted(final.dimensions.items()):
        print(f"    {dim:<20} {score:.2f}")
    builder = MissionGraphBuilder(db)
    edges = builder.query(company_id)
    counts: dict[str, int] = {}
    for e in edges:
        counts[e.relation.value] = counts.get(e.relation.value, 0) + 1
    print(
        f"  graph       : {len(edges)} edge(s) "
        f"= {', '.join(f'{k}:{v}' for k, v in sorted(counts.items()))}"
    )

    return {
        "company_id": str(company_id),
        "mission_id": str(mission_id),
        "cycle_count": len(engine.list_cycles(company_id)),
        "graph_edges": len(edges),
        "policy": AutonomyService(db).to_dict(company_id),
    }


def _print_cycle(cycle: dict[str, Any], *, label: str = "cycle") -> None:
    stages = cycle["stages"] or []
    names = [s["stage"] for s in stages]
    active = " → ".join(names)
    print(f"  {label:<8}: run #{cycle['cycle_number']} {cycle['status']} [{active}]")
    for s in stages:
        if s.get("status") == "blocked":
            print(f"    blocked   : {s['stage']} — {s.get('summary')}")
    if cycle.get("failures"):
        print(f"    failures  : {len(cycle['failures'])}")
    if cycle.get("recovery"):
        print(f"    recovery  : {len(cycle['recovery'])} attempt(s)")
    outcome = cycle.get("outcome") or {}
    if outcome.get("blocked_reason"):
        print(f"    reason    : {outcome['blocked_reason']}")
    if outcome.get("pending_gate_id"):
        print(f"    gate      : {outcome['pending_gate_id']}")


def _print_final_summary(db: Session, summary: dict[str, Any]) -> None:
    company_id = UUID(summary["company_id"])
    mission_row = db.get(Mission, UUID(summary["mission_id"]))
    plan = _latest_startup_plan(db, mission_row.id)
    from app.startup.cycle import OperatingEngine
    from app.startup.products import ProductManager

    products = ProductManager(db).list_(company_id)
    cycles = OperatingEngine(db).list_cycles(company_id)
    print("\n=== NEXUS Autonomous AI Startup seeded ===")
    print(f"company_id : {summary['company_id']}")
    print(f"mission    : {mission_row.title} [{mission_row.status.value}]")
    print(f"plan       : {plan.status.value if plan else 'n/a'}")
    print(
        f"products   : {', '.join(p.name for p in products)} → {[p.status.value for p in products]}"
    )
    print(f"cycles     : {summary['cycle_count']} total ({', '.join(c['status'] for c in cycles)})")
    print(f"graph      : {summary['graph_edges']} edges")
    policy = summary["policy"]
    print(f"autonomy   : {policy['autonomy_level']}")
    print(
        "Verify with:\n"
        "  curl localhost:8000/api/v1/startup/<company_id>/state\n"
        "  curl localhost:8000/api/v1/missions?company_id=<company_id>\n"
        "  curl localhost:8000/api/v1/missions/graph?company_id=<company_id>"
    )


if __name__ == "__main__":
    main()
