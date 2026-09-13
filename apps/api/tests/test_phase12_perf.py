"""Phase 12 performance smoke tests (§62).

These are coarse order-of-magnitude guards, not timing-based flake traps:
each test asserts the engine completes a bounded workload in under a generous
wall-clock budget on CI-grade hardware. They exist to catch accidental
quadratic loops / runaway generation, not to benchmark precise throughput.
"""

from __future__ import annotations

import time

import pytest

from app.phase12 import experiments as exp_mod
from app.phase12 import optimization as opt
from app.phase12.benchmarking import BenchmarkEngine
from app.phase12.engine import SimulationEngine
from app.phase12.variables import SimulationVariable

# Generous budgets — a normal dev/CI box runs these in a few hundred ms.
_SIM_BUDGET_S = 10.0
_OPT_BUDGET_S = 10.0
_EXP_BUDGET_S = 10.0
_BENCH_BUDGET_S = 10.0
_MARKET_BUDGET_S = 5.0


@pytest.fixture
def company(db):
    from app.company.manager import CompanyManager

    return CompanyManager(db).create(name="Perf Co")


def test_simulation_100_tick_run_within_budget(db, company):
    eng = SimulationEngine(db, run_timeout_seconds=60.0, max_ticks=200)
    sim = eng.create(
        company_id=company.id,
        name="perf sim",
        scenario_type="stress_test",
        horizon_days=100,
    )
    started = time.monotonic()
    run = eng.run(
        simulation_id=sim.id,
        iterations=3,
        seed="perf",
        variables=[
            SimulationVariable(
                name="headcount", kind="integer", value=12, min_value=1, max_value=50
            ),
            SimulationVariable(
                name="budget", kind="float", value=5000.0, min_value=0.0, max_value=100000.0
            ),
        ],
    )
    elapsed = time.monotonic() - started
    assert run.status == "completed"
    assert run.tick_count == 100
    assert elapsed < _SIM_BUDGET_S
    # Multi-run aggregation landed in the summary (metrics is not empty).
    assert (run.summary_json or {}).get("metrics")


def test_optimization_200_candidates_within_budget(db, company):
    eng = opt.OptimizationEngine(db, max_candidates=300)
    problem = eng.create_problem(
        company_id=company.id,
        name="perf opt",
        objectives=[opt.Objective(metric="output", direction="maximize", weight=1.0)],
        variables=[opt.Variable(name="x", kind="float", low=0, high=100)],
        constraints=None,
    )
    started = time.monotonic()
    run = eng.run_problem(problem.id, strategy="exhaustive")
    elapsed = time.monotonic() - started
    assert run.status == "completed"
    assert elapsed < _OPT_BUDGET_S
    assert len(eng.run_results(run.id)["candidates"]) >= 1


def test_experiment_lifecycle_within_budget(db, company):
    eng = exp_mod.ExperimentEngine(db)
    started = time.monotonic()
    exp = eng.create_experiment(
        company_id=company.id,
        name="perf exp",
        metrics=["task_success_rate", "cost_per_task"],
        variants=[
            {"name": "control", "is_baseline": True, "config": {"latency": 50}},
            {"name": "variant-a", "config": {"latency": 30}},
        ],
    )
    eng.submit_for_approval(exp.id)
    eng.approve(exp.id)
    eng.run_experiment(exp.id)
    result = eng.complete_experiment(
        exp.id,
        conclusion="inconclusive",
        metrics={"task_success_rate": 0.81, "cost_per_task": 1.2},
        confidence={"sample_size_note": "n<30, not significant"},
        limitations={"note": "modeled estimates only"},
    )
    elapsed = time.monotonic() - started
    assert exp.status == "completed"
    assert result.conclusion == "inconclusive"
    assert elapsed < _EXP_BUDGET_S


def test_benchmark_40_cases_within_budget(db, company):
    eng = BenchmarkEngine(db)
    bench = eng.create_benchmark(
        company_id=company.id,
        name="perf bench",
        cases=[
            {
                "name": f"case-{i}",
                "input": {"q": i},
                "expected_output": {"ok": True},
                "weight": 1.0,
            }
            for i in range(40)
        ],
    )
    started = time.monotonic()
    run = eng.run_benchmark(bench.id, company_id=company.id)
    elapsed = time.monotonic() - started
    assert run.status == "completed"
    results = eng.run_results(run.id)
    assert len(results["results"]) == 40
    assert elapsed < _BENCH_BUDGET_S


def test_marketplace_full_install_path_within_budget(db, company):
    from app.phase12.marketplace import MarketplaceService

    svc = MarketplaceService(db)
    started = time.monotonic()
    pkg = svc.create_package(
        name="perf-pkg",
        company_id=company.id,
        capabilities=["perf"],
        skills=["fast"],
    )
    svc.add_version(pkg.id, version="1.0.0", capabilities=["perf"])
    svc.publish(pkg.id)
    inst = svc.install(package_id=pkg.id, company_id=company.id, require_approval=False)
    svc.confirm_install(inst.id)
    elapsed = time.monotonic() - started
    assert inst.status != "approval_required"
    assert elapsed < _MARKET_BUDGET_S
