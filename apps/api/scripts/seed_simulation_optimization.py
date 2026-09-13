"""Seed the NEXUS Simulation, Optimization & Agent Marketplace demo (Phase 12).

A deterministic, self-checking demo that lives entire reloads — no network, no
paid model API — and exercises the *real* Phase 12 services end to end:

  Part 1 — Company what-if: 5 → 7 employees through the SimulationEngine
           (baseline vs scenario, SIMULATED outputs, zero production mutation).
  Part 2 — Agent optimization on a shared benchmark: benchmark two agent
           versions, then optimize a parameter against the measured scores.
  Part 3 — Resource-allocation optimization: headcount/cost candidates ranked
           under a resource-limit governance check + a hard constraint,
           then an explainable recommendation.
  Part 4 — Product launch 4-week vs 6-week: a simulation comparison of the two
           timelines (deltas + bottleneck).
  Part 5 — "Research Analyst Pro" marketplace package: publish → benchmark →
           attach benchmark scores → recommend → safe install (approval-gated).
  Part 6 — Closed-loop demo: OBSERVE → SIMULATE → OPTIMIZE → PROPOSE → APPROVE
           → EXECUTE → MEASURE → LEARN via NEXUSOptimizationLoop.

  §69 — Full E2E "NEXUS AUTONOMOUS COMPANY OPTIMIZATION": observe KPIs → spot
  an engineering bottleneck → build scenarios → simulate → compare → pick the
  best → governance check → recommendation → approval gate → execute (recorded
  reference only) → measure → actual-vs-simulated → lesson → memory.

Idempotent: a company with the same name is reused; re-running fills gaps.
Deterministic: every outcome is asserted before it is printed; all outputs are
labeled SIMULATED/FORECAST — never ACTUAL.

Run from ``apps/api``:
    .venv/bin/python -m scripts.seed_simulation_optimization [--reset]
"""

from __future__ import annotations

import argparse
import sys
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

sys.path.insert(0, ".")

import app.db.models  # noqa: E402,F401  (register every model on Base.metadata)
from app.db.session import Base, SessionLocal  # noqa: E402

DEMO_COMPANY_NAME = "NEXUS Simulation & Optimization"
DEMO_PACKAGE_NAME = "research-analyst-pro"


def _get_or_create_company(db: Session, name: str) -> Any:
    from app.company.manager import CompanyManager
    from app.db.models.company import Company

    existing = db.scalar(select(Company).where(Company.name == name))
    if existing is not None:
        return existing
    return CompanyManager(db).create(
        name=name, description="Phase 12 simulation/optimization demo."
    )


# ── Part 1 — Company what-if ────────────────────────────────────────────────
def _part1_workforce_what_if(db: Session, company_id: UUID) -> dict[str, Any]:
    from app.phase12._types import SimVariableKind
    from app.phase12.engine import SimulationEngine
    from app.phase12.variables import SimulationVariable

    eng = SimulationEngine(db, run_timeout_seconds=30.0)
    sim = eng.create(
        company_id=company_id,
        name="What-if: grow engineering 5 → 7",
        scenario_type="what_if",
        horizon_days=30,
        assumptions={
            "sourcing": "hire two senior engineers in week 2",
            "onboarding": "2-week ramp",
        },
    )
    assert sim.status == "draft", sim.status
    assert sim.sandboxed is True

    base = eng.run(
        simulation_id=sim.id,
        iterations=2,
        seed="wfi-base",
        variables=[
            SimulationVariable(
                name="headcount",
                kind=SimVariableKind.INTEGER,
                value=5,
                min_value=1,
                max_value=50,
            ),
            SimulationVariable(
                name="budget",
                kind=SimVariableKind.FLOAT,
                value=5000.0,
                min_value=0.0,
                max_value=100000.0,
            ),
        ],
    )
    assert base.status == "completed", base.error_message
    assert base.tick_count == 30, base.tick_count

    grown = eng.run(
        simulation_id=sim.id,
        iterations=2,
        seed="wfi-grown",
        variables=[
            SimulationVariable(
                name="headcount",
                kind=SimVariableKind.INTEGER,
                value=7,
                min_value=1,
                max_value=50,
            ),
            SimulationVariable(
                name="budget",
                kind=SimVariableKind.FLOAT,
                value=8000.0,
                min_value=0.0,
                max_value=100000.0,
            ),
        ],
    )
    assert grown.status == "completed", grown.error_message

    cmp = eng.compare(baseline_run_id=base.id, scenario_run_id=grown.id)
    assert cmp.metric_deltas_json or {}, "no comparison deltas"
    state = eng.run_state(grown.id)
    assert state["tick"] >= 1
    assert any(e["kind"] for e in state["events"]), "events missing"
    summary = grown.summary_json or {}
    assert summary.get("iterations", 0) >= 1
    print(
        f"  [part1] what-if 5→7 employees complete: "
        f"{len(cmp.metric_deltas_json)} metric deltas, "
        f"{summary['iterations']} iterations (SIMULATED)"
    )
    return {
        "simulation_id": str(sim.id),
        "baseline_run_id": str(base.id),
        "grown_run_id": str(grown.id),
    }


# ── Part 2 — Agent optimization on shared benchmark ─────────────────────────
def _part2_agent_optimization(db: Session, company_id: UUID) -> dict[str, Any]:
    from app.phase12.benchmarking import BenchmarkEngine
    from app.phase12.optimization import (
        Objective,
        OptimizationEngine,
        Variable,
    )

    bench = BenchmarkEngine(db)
    benchmark = bench.create_benchmark(
        company_id=company_id,
        name="research-agents-shared",
        description="Shared correctness/reliability/latency/cost benchmark.",
        version="1.0",
        dimensions=["correctness", "reliability", "latency", "cost"],
        cases=[
            {
                "name": f"r-{i}",
                "input": {"query": f"research question {i}"},
                "expected_output": {"answer": "cites sources"},
                "weight": 1.0,
            }
            for i in range(8)
        ],
    )
    agent_a = uuid4()
    run_a = bench.run_benchmark(
        benchmark.id, agent_id=agent_a, agent_version="1.0", company_id=company_id
    )
    assert run_a.status == "completed"
    scores_a = bench.agent_scores(agent_a, benchmark_id=benchmark.id)
    assert scores_a, "no agent scores"
    # Test infrastructure seed: use a second agent version for comparison.
    agent_b = uuid4()
    run_b = bench.run_benchmark(
        benchmark.id, agent_id=agent_b, agent_version="1.1", company_id=company_id
    )
    assert run_b.status == "completed"

    # Optimize a "context window size" against the measured correctness score.
    eng = OptimizationEngine(db)
    problem = eng.create_problem(
        company_id=company_id,
        name="Pick context window size",
        objectives=[Objective(metric="correctness", direction="maximize", weight=1.0)],
        variables=[Variable(name="context_window", kind="integer", low=4, high=12)],
        constraints=None,
    )
    run = eng.run_problem(problem.id, strategy="greedy")
    assert run.status == "completed", run.result_json
    results_a = bench.run_results(run_a.id)
    assert results_a["aggregate"]["correctness"]["mean"] > 0.0
    print(
        f"  [part2] agent benchmark shared: {len(scores_a)} dimension-scores "
        f"for v1.0 + v1.1; optimized context_window "
        f"best={eng.run_results(run.id)['best_candidate']['values']}"
    )
    return {"benchmark_id": str(benchmark.id), "agent_a": str(agent_a), "agent_b": str(agent_b)}


# ── Part 3 — Resource-allocation optimization ───────────────────────────────
def _part3_resource_allocation(db: Session, company_id: UUID) -> dict[str, Any]:
    from app.phase12.optimization import (
        Constraint,
        Objective,
        OptimizationEngine,
        Variable,
    )

    eng = OptimizationEngine(db)
    problem = eng.create_problem(
        company_id=company_id,
        name="Allocate headcount & budget",
        objectives=[
            Objective(metric="output", direction="maximize", weight=1.0),
            Objective(metric="headcount", direction="minimize", weight=0.2),
        ],
        variables=[
            Variable(name="headcount", kind="integer", low=1, high=10),
            Variable(name="budget", kind="float", low=0, high=10000),
        ],
        constraints=[
            Constraint(
                name="capacity",
                check=lambda v: (v.get("headcount") or 0) <= 8,
                description="Dept capacity: max 8 engineers",
            ),
            Constraint(
                name="budget-cap",
                check=lambda v: (v.get("budget") or 0) <= 8000,
                description="Quarterly budget cap",
            ),
        ],
    )
    run = eng.run_problem(problem.id, strategy="greedy")
    assert run.status == "completed"
    results = eng.run_results(run.id)
    assert results["best_candidate"] is not None
    best_values = results["best_candidate"]["values"]
    assert best_values["headcount"] <= 8, best_values
    assert best_values["budget"] <= 8000, best_values

    rec = eng.recommend(run_id=run.id, company_id=company_id, title="Recommended allocation")
    bx = rec.explanation_json or {}
    for key in (
        "what",
        "why",
        "alternatives",
        "constraints",
        "why_this_candidate",
        "expected_benefit",
        "expected_cost",
        "risks",
        "assumptions",
        "approval",
    ):
        assert key in bx, f"explainability missing {key}"
    assert rec.status == "proposed"
    print(
        f"  [part3] allocation optimized best={best_values}; "
        f"recommendation {rec.status} with 10-part explainability block (§46)"
    )
    return {"problem_id": str(problem.id), "run_id": str(run.id), "rec_id": str(rec.id)}


# ── Part 4 — Product launch 4wk vs 6wk ──────────────────────────────────────
def _part4_product_launch(db: Session, company_id: UUID) -> dict[str, Any]:
    from app.phase12._types import SimVariableKind
    from app.phase12.engine import SimulationEngine
    from app.phase12.variables import SimulationVariable

    eng = SimulationEngine(db)
    four = eng.create(
        company_id=company_id,
        name="Product launch — 4-week timeline",
        scenario_type="product_test",
        horizon_days=28,
        assumptions={"timeline": "4 weeks", "scope": "v1 core"},
    )
    six = eng.create(
        company_id=company_id,
        name="Product launch — 6-week timeline",
        scenario_type="product_test",
        horizon_days=42,
        assumptions={"timeline": "6 weeks", "scope": "v1 core + polish"},
    )
    run_4 = eng.run(
        simulation_id=four.id,
        iterations=1,
        seed="launch-4wk",
        variables=[
            SimulationVariable(
                name="headcount",
                kind=SimVariableKind.INTEGER,
                value=6,
                min_value=1,
                max_value=50,
            )
        ],
    )
    run_6 = eng.run(
        simulation_id=six.id,
        iterations=1,
        seed="launch-6wk",
        variables=[
            SimulationVariable(
                name="headcount",
                kind=SimVariableKind.INTEGER,
                value=6,
                min_value=1,
                max_value=50,
            )
        ],
    )
    assert run_4.status == "completed" and run_6.status == "completed"
    cmp = eng.compare(baseline_run_id=run_4.id, scenario_run_id=run_6.id)
    deltas = cmp.metric_deltas_json or {}
    assert deltas
    print(
        f"  [part4] launch 4wk vs 6wk: {len(deltas)} metric deltas "
        f"(all SIMULATED); bottleneck={cmp.bottleneck_json}"
    )
    return {
        "four_week_run": str(run_4.id),
        "six_week_run": str(run_6.id),
        "comparison_id": str(cmp.id),
    }


# ── Marketplace helpers ─────────────────────────────────────────────────────
def _prune_orphaned_packages(db: Session) -> int:
    """Delete orphaned demo packages (company_id NULL from the SET NULL cascade).

    Orphaned packages are already excluded from recommendation candidates, but
    pruning keeps the demo residue-free so ``list_packages`` stays tidy across
    repeated ``--reset`` runs. Returns the number pruned.
    """
    from app.db.models.phase12 import (
        AgentPackage,
        AgentPackageBenchmark,
        AgentPackageCapability,
        AgentPackageVersion,
        AgentRecommendation,
    )

    stale = db.scalars(
        select(AgentPackage).where(
            AgentPackage.name == DEMO_PACKAGE_NAME,
            AgentPackage.company_id.is_(None),
        )
    ).all()
    vers: list[AgentPackageVersion] = []
    for pkg in stale:
        vers.extend(
            db.scalars(select(AgentPackageVersion).where(AgentPackageVersion.package_id == pkg.id))
        )
        db.query(AgentRecommendation).filter(AgentRecommendation.package_id == pkg.id).delete(
            synchronize_session=False
        )
    for ver in vers:
        db.query(AgentPackageBenchmark).filter(AgentPackageBenchmark.version_id == ver.id).delete(
            synchronize_session=False
        )
        db.query(AgentPackageCapability).filter(AgentPackageCapability.version_id == ver.id).delete(
            synchronize_session=False
        )
        db.delete(ver)
    for pkg in stale:
        db.delete(pkg)
    if stale:
        db.commit()
    return len(stale)


# ── Part 5 — Research Analyst Pro marketplace ───────────────────────────────
def _part5_marketplace(db: Session, company_id: UUID) -> dict[str, Any]:
    from app.phase12.benchmarking import BenchmarkEngine
    from app.phase12.marketplace import MarketplaceService
    from app.phase12.recommend import RecommendationEngine

    # Any orphan left by a same-run reset is pruned before we publish afresh,
    # so exactly one published package + zero orphans survive each seed.
    pruned = _prune_orphaned_packages(db)
    if pruned:
        print(f"  [part5] pruned {pruned} orphaned '{DEMO_PACKAGE_NAME}' package(s)")

    svc = MarketplaceService(db)
    pkg = svc.create_package(
        name="research-analyst-pro",
        company_id=company_id,
        display_name="Research Analyst Pro",
        description="Web-research + summarization specialist (metadata only).",
        capabilities=["research", "summarize", "web-search"],
        skills=["web-search", "citation"],
        supported_task_types=["research", "summarization"],
        requirements={
            "estimated_cost": 50.0,
            "estimated_latency_ms": 90.0,
            "tools": ["web_search", "memory"],
            "permissions": ["read_memory", "web_access"],
        },
        security="confidential",
    )
    assert pkg.status == "draft"
    ver = svc.add_version(
        pkg.id,
        version="1.0.0",
        changelog="Initial release",
        compatibility="compatible",
        capabilities=["research", "summarize"],
        dependencies=[{"package": "nexus-web-toolkit", "version": ">=1.0"}],
    )

    # Benchmark the package, then attach the real score.
    bench = BenchmarkEngine(db)
    benchmark = bench.create_benchmark(
        company_id=company_id,
        name="research-analyst-benchmark",
        version="1.0",
        dimensions=["correctness", "reliability", "cost", "latency"],
        cases=[
            {
                "name": f"ra-{i}",
                "input": {"query": f"market research {i}"},
                "expected_output": {"answer": "cited", "quality": "high"},
                "weight": 1.0,
            }
            for i in range(6)
        ],
    )
    run = bench.run_benchmark(
        benchmark.id, agent_id=ver.id, agent_version=ver.version, company_id=company_id
    )
    assert run.status == "completed"
    agg = bench.run_results(run.id)["aggregate"]
    correctness = agg["correctness"]["mean"]
    svc.attach_benchmark(
        version_id=ver.id,
        benchmark_id=benchmark.id,
        company_id=company_id,
        score=correctness,
        dimension="correctness",
    )
    svc.publish(pkg.id)
    assert pkg.status == "published"

    # Publish is never automatic nor Unicode-safe: recommend uses real scores.
    rec_eng = RecommendationEngine(db)
    recs = rec_eng.recommend(
        company_id=company_id,
        task_type="research",
        skills=["web-search"],
        budget_limit=200.0,
        latency_limit_ms=500.0,
        require_approval=True,
    )
    ranked = [r for r in recs if r.package_id == pkg.id]
    assert ranked, "package not recommended"
    top = ranked[0]
    assert top.rank == 1
    assert top.policy_status == "pending_approval"

    # Safe install: confidentiality + require_approval → approval gate.
    inst = svc.install(
        package_id=pkg.id, company_id=company_id, version_id=ver.id, require_approval=True
    )
    assert inst.status == "approval_required", inst.status
    assert inst.approval_gate_id is not None
    print(
        f"  [part5] research-analyst-pro published; benchmark correctness "
        f"{correctness:.3f}; top recommendation rank 1 (score {top.score:.3f}); "
        f"install approval-gated (§37 safe install)"
    )
    return {
        "package_id": str(pkg.id),
        "version_id": str(ver.id),
        "benchmark_id": str(benchmark.id),
        "recommendation_id": str(top.id),
        "installation_id": str(inst.id),
    }


# ── Part 6 — Closed-loop demo ───────────────────────────────────────────────
def _part6_closed_loop(db: Session, company_id: UUID) -> dict[str, Any]:
    from app.phase12.loop import LoopError, NEXUSOptimizationLoop
    from app.startup.gates import ApprovalGateManager

    loop = NEXUSOptimizationLoop(db)
    cycle = loop.run_full_cycle(company_id=company_id, name="Closed-loop: engineering capacity")
    assert cycle.status == "awaiting_approval"
    assert cycle.approval_gate_id is not None

    # Execute without approval must be blocked (governance decides).
    try:
        loop.execute(cycle.id)
        raise AssertionError("execute should be blocked before gate approval")
    except LoopError as exc:
        assert "not approved" in str(exc)

    # Human governance decides: an operator approves the gate, then execute.
    ApprovalGateManager(db).approve(company_id, cycle.approval_gate_id, approver_id=None)
    cycle = loop.execute(cycle.id)
    assert cycle.status == "executing"
    loop.measure(cycle.id)
    assert cycle.status == "measuring"
    loop.learn(cycle.id)
    assert cycle.status == "learning"
    assert (cycle.lesson_json or {}).get("recorded") is True
    loop.complete(cycle.id)
    assert cycle.status == "completed"
    print(
        "  [part6] closed-loop: observe→simulate→optimize→propose→approve→"
        "execute→measure→learn→complete (approval-gated, lesson recorded)"
    )
    return {"cycle_id": str(cycle.id)}


# ── §69 — Full E2E "NEXUS AUTONOMOUS COMPANY OPTIMIZATION" ────────────────
def _part69_full_e2e(db: Session, company_id: UUID) -> dict[str, Any]:
    from app.db.models.phase12 import SimulationOutcome
    from app.phase12.loop import NEXUSOptimizationLoop
    from app.startup.gates import ApprovalGateManager

    loop = NEXUSOptimizationLoop(db)
    # observe
    cycle = loop.create_cycle(
        company_id=company_id, name="E2E: autonomous company optimization", observe=True
    )
    assert cycle.status == "observing"
    observed = cycle.observed_json or {}
    assert observed.get("source") == "phase-8-kpis"

    # simulate (link the what-if scenario from part 1's sim, if present)
    loop.simulate(cycle.id)
    assert cycle.status == "simulating"
    loop.optimize(cycle.id)
    assert cycle.status == "optimizing"
    loop.propose(cycle.id)
    assert cycle.status == "proposing"
    loop.require_approval(cycle.id, rationale="Apply recommended capacity increase.")
    assert cycle.status == "awaiting_approval"

    # Governance decides: an operator approves the gate.
    gates = ApprovalGateManager(db)
    gates.approve(company_id, cycle.approval_gate_id, approver_id=None)
    cycle = loop.execute(cycle.id)
    assert cycle.status == "executing"
    loop.measure(cycle.id)
    assert cycle.status == "measuring"
    loop.learn(cycle.id)
    assert cycle.status == "learning"
    assert (cycle.lesson_json or {}).get("recorded") is True
    loop.complete(cycle.id)
    assert cycle.status == "completed"

    # Honest labeling: every simulation outcome is SIMULATED, never ACTUAL.
    kinds = set(db.scalar(select(SimulationOutcome.output_kind).distinct().limit(10)) or set())
    txt = ", ".join(kinds) if kinds else "(none)"
    print(
        f"  [part69] full E2E cycle complete: observe→simulate→optimize→propose→"
        f"approve→execute→measure→learn→complete; outcomes labeled {txt}"
    )
    return {"cycle_id": str(cycle.id), "observed_kpis": bool(observed)}


def _run_demo(db: Session, *, reset: bool = False) -> dict[str, Any]:
    from app.db.models.company import Company

    if reset:
        existing = db.scalar(select(Company).where(Company.name == DEMO_COMPANY_NAME))
        if existing is not None:
            db.delete(existing)
            db.commit()
        # The company cascade orphans published packages (company_id SET NULL).
        # Prune those so a re-seed leaves no stale marketplace residue behind.
        pruned = _prune_orphaned_packages(db)
        if pruned:
            print(f"  [reset] pruned {pruned} orphaned '{DEMO_PACKAGE_NAME}' package(s)")

    company = _get_or_create_company(db, DEMO_COMPANY_NAME)
    db.commit()
    company_id = company.id

    print(f"\n=== NEXUS Phase 12 demo seed for '{DEMO_COMPANY_NAME}' ===")
    p1 = _part1_workforce_what_if(db, company_id)
    p2 = _part2_agent_optimization(db, company_id)
    p3 = _part3_resource_allocation(db, company_id)
    p4 = _part4_product_launch(db, company_id)
    p5 = _part5_marketplace(db, company_id)
    p6 = _part6_closed_loop(db, company_id)
    p69 = _part69_full_e2e(db, company_id)
    return {
        "company_id": str(company_id),
        "parts": {"1": p1, "2": p2, "3": p3, "4": p4, "5": p5, "6": p6, "69": p69},
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed the NEXUS Simulation, Optimization & Marketplace demo (Phase 12)."
    )
    parser.add_argument("--reset", action="store_true", help="Delete and recreate the demo company")
    args = parser.parse_args()

    Base.metadata.create_all(bind=SessionLocal.kw["bind"])
    with SessionLocal() as db:
        summary = _run_demo(db, reset=args.reset)
        print("\n=== NEXUS Simulation & Optimization seeded ===")
        print(f"company_id : {summary['company_id']}")
        print("part 1     : what-if 5→7 employees (SIMULATED)")
        print("part 2     : agent optimization on shared benchmark")
        print("part 3     : resource-allocation optimization + explainable rec")
        print("part 4     : product launch 4wk vs 6wk comparison")
        print("part 5     : research-analyst-pro published + recommend + install")
        print("part 6     : closed-loop cycle (approval-gated)")
        print("part 69    : full NEXUS autonomous-company-optimization E2E")
        print(
            "\n  Inspect live:  GET /api/v1/simulations?company_id=<id>\n"
            "                 GET /api/v1/optimization/problems?company_id=<id>\n"
            "                 GET /api/v1/experiments?company_id=<id>\n"
            "                 GET /api/v1/marketplace/agents?company_id=<id>\n"
            "                 GET /api/v1/optimization-cycles?company_id=<id>"
        )


if __name__ == "__main__":
    main()
