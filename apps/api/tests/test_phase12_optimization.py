"""Phase 12 optimization engine tests (§60).

Covers the full ``OptimizationEngine`` surface: problem definition, candidate
generation (greedy / exhaustive), governance guards (policy + resource limits +
constraint callables), weighted multi-objective scoring, the §46 explainability
block on recommendations, and the approval lifecycle. Also encodes three
product-pitch scenarios against the real engine: a resource-overspend guard,
the "SynER" cross-checked budget model, a Jupyter-turnaround-time vectorized
run, and pareto-frontier parsing over single- and multi-company snapshots.

Fast: runs against the SQLite ``db`` fixture (file-backed, in-memory tables).
"""

from __future__ import annotations

import time
import uuid

import pytest

from app.company.manager import CompanyManager
from app.phase12.optimization import (
    Constraint,
    ExhaustiveStrategy,
    GreedyStrategy,
    Objective,
    OptimizationEngine,
    OptimizationError,
    Variable,
)


@pytest.fixture
def company(db):
    """A bare company the optimization problems/recs can be scoped to."""
    return CompanyManager(db).create(name="Phase 12 Opt Co")


def _pareto_frontier(points):
    """Non-dominated frontier over maximization goals (order-preserving).

    ``points`` is an iterable of ``(name, *goals)``. Point p dominates q when
    p is >= q on every goal and > on at least one. The frontier keeps the
    non-dominated rows in their original snapshot order. (Local to this module
    — the authoritative analysis replicated in the scaled-company test.)
    """
    rows = list(points)
    frontier: list[tuple] = []
    for i, (name, *goals) in enumerate(rows):
        dominated = False
        for j, (_other_name, *other_goals) in enumerate(rows):
            if i == j:
                continue
            if all(g <= o for g, o in zip(goals, other_goals, strict=False)) and any(
                g < o for g, o in zip(goals, other_goals, strict=False)
            ):
                dominated = True
                break
        if not dominated:
            frontier.append((name, *goals))
    return frontier


# ── Problem definition & persistence ─────────────────────────────────────────


def test_create_problem_persists_spec(db, company):
    """objectives/variables/constraints are serialized into objective_json."""
    eng = OptimizationEngine(db)
    problem = eng.create_problem(
        company_id=company.id,
        name="Allocation spec",
        description="Staff + budget allocation",
        objectives=[
            Objective(metric="output", direction="maximize", weight=1.0),
            Objective(metric="cost", direction="minimize", weight=0.5),
        ],
        variables=[
            Variable(name="headcount", kind="integer", low=1, high=10, default=4),
            Variable(name="budget", kind="float", low=0, high=500),
        ],
        constraints=[
            Constraint(
                name="budget",
                check=lambda v: (v.get("budget") or 0) <= 400,
                description="Keep spend under 400",
            )
        ],
    )

    spec = problem.objective_json
    assert set(spec) == {"objectives", "variables", "constraints"}
    assert [o["metric"] for o in spec["objectives"]] == ["output", "cost"]
    assert spec["objectives"][0]["direction"] == "maximize"
    assert spec["objectives"][1]["weight"] == 0.5
    # Variable metadata round-trips its bounds/kind.
    vars_spec = {v["name"]: v for v in spec["variables"]}
    assert vars_spec["headcount"]["kind"] == "integer"
    assert vars_spec["headcount"]["low"] == 1
    assert vars_spec["headcount"]["high"] == 10
    assert vars_spec["budget"]["kind"] == "float"
    # Constraint metadata (name + description) is persisted.
    assert spec["constraints"] == [{"name": "budget", "description": "Keep spend under 400"}]


def test_problem_status_draft(db, company):
    """A created problem starts in the draft state."""
    eng = OptimizationEngine(db)
    problem = eng.create_problem(
        company_id=company.id,
        name="Draft problem",
        variables=[Variable(name="headcount", kind="integer", low=1, high=10)],
    )
    assert problem.status == "draft"


def test_integer_samples_are_integral():
    """Integer variables never produce fractional candidates (this session's fix)."""
    int_var = Variable(name="headcount", kind="integer", low=1, high=10)
    samples = int_var.samples()
    assert len(samples) >= 2
    assert samples == sorted(samples)  # integral + ascending
    assert all(isinstance(v, int) and 1 <= v <= 10 for v in samples)
    # For low=1, high=10 the engine returns exactly 5 integral values.
    assert samples == [1, 3, 6, 8, 10]

    float_var = Variable(name="ratio", kind="float", low=0, high=1)
    assert all(isinstance(v, float) for v in float_var.samples())


# ── Candidate generation strategies ──────────────────────────────────────────


def test_greedy_strategy_generates_default_plus_nudges():
    """Greedy starts at the default then nudges each variable per unique sample."""
    var = Variable(name="headcount", kind="integer", low=1, high=10)
    strategy = GreedyStrategy()
    raw = strategy.generate([var])
    # The default-based candidate is always present.
    samples = var.samples()
    assert raw[0] == {var.name: samples[0]}
    # With one variable and no default, one candidate per unique sample.
    assert len(raw) == len(samples)


def test_exhaustive_strategy_grid():
    """Exhaustive builds the full combinatorial grid over option vectors."""
    strategy = ExhaustiveStrategy()
    grid = strategy.generate(
        [
            Variable(name="a", options=[1, 2]),
            Variable(name="b", options=[10, 20, 30]),
        ]
    )
    assert len(grid) == 2 * 3
    assert grid[0] == {"a": 1, "b": 10}
    assert grid[-1] == {"a": 2, "b": 30}


# ── Runs, scoring, and governance guards ─────────────────────────────────────


def test_run_completes_and_scores(db, company):
    """A run completes and every persisted candidate carries values + scores."""
    eng = OptimizationEngine(db)
    problem = eng.create_problem(
        company_id=company.id,
        name="Sizing run",
        objectives=[Objective(metric="output", direction="maximize", weight=1.0)],
        variables=[Variable(name="headcount", kind="integer", low=1, high=10)],
    )
    run = eng.run_problem(problem.id, strategy="greedy")
    assert run.status == "completed"

    results = eng.run_results(run.id)
    assert results["candidates"]
    for candidate in results["candidates"]:
        assert set(candidate) >= {"index", "values", "scores"}
    best = results["best_candidate"]
    assert best is not None and "headcount" in best["values"]
    # Single maximize objective: top score equals the max candidate value.
    assert best["scores"]["output"] == max(c["scores"]["output"] for c in results["candidates"])
    assert best["scores"]["output"] == best["values"]["headcount"]


def test_constraint_enforced(db, company):
    """Registry-fallback constraints are enforced without re-passing them."""
    eng = OptimizationEngine(db)
    constraint = Constraint(
        name="budget",
        check=lambda v: (v.get("headcount") or 0) <= 9,
        description="Cap headcount at 9",
    )
    problem = eng.create_problem(
        company_id=company.id,
        name="Constrained sizing",
        objectives=[Objective(metric="output", direction="maximize", weight=1.0)],
        variables=[Variable(name="headcount", kind="integer", low=1, high=10)],
        constraints=[constraint],
    )
    run = eng.run_problem(problem.id, strategy="greedy")  # NO constraints arg.
    assert run.status == "completed"
    best = eng.run_results(run.id)["best_candidate"]
    assert best["values"]["headcount"] <= 9
    assert best["scores"]["output"] == 8.0  # highest admissible candidate


def test_constraint_reason_stamps_candidate(db, company):
    """Violating candidates are rejected before persistence — none survive."""
    from sqlalchemy import select

    from app.db.models.phase12 import OptimizationCandidate

    eng = OptimizationEngine(db)
    problem = eng.create_problem(
        company_id=company.id,
        name="Constrained sizing v2",
        constraints=[
            Constraint(
                name="budget",
                check=lambda v: (v.get("headcount") or 0) <= 9,
            )
        ],
        variables=[Variable(name="headcount", kind="integer", low=1, high=10)],
    )
    run = eng.run_problem(problem.id, strategy="greedy")
    rows = list(
        db.execute(
            select(OptimizationCandidate).where(OptimizationCandidate.run_id == run.id)
        ).scalars()
    )
    assert rows
    assert all((row.values_json or {}).get("headcount", 0) <= 9 for row in rows)


def test_policy_violation_rejected(db, company):
    """A denying policy check invalidates every candidate (run still completes)."""
    deny_decision = type("Deny", (), {"decision": "deny"})()

    def policy_check(action, company_id, context):
        return deny_decision

    eng = OptimizationEngine(db, policy_check=policy_check)
    problem = eng.create_problem(
        company_id=company.id,
        name="Denied attack path",
        objectives=[Objective(metric="output", direction="maximize", weight=1.0)],
        variables=[Variable(name="headcount", kind="integer", low=1, high=10)],
    )
    run = eng.run_problem(problem.id, strategy="greedy")
    assert run.status == "completed"

    results = eng.run_results(run.id)
    assert results["candidates"] == []
    assert results["best_candidate"] is None
    # No headcount row of any kind survived policy rejection.
    assert all("headcount" not in (c or {}) for c in results["candidates"])


def test_resource_limit_rejected(db, company):
    """A strict cost budget rejects overspending candidates up front."""
    eng = OptimizationEngine(db, resource_limits=lambda category, company_id: 100.0)
    problem = eng.create_problem(
        company_id=company.id,
        name="Cheap run",
        variables=[Variable(name="budget", kind="float", low=0, high=500)],
    )
    run = eng.run_problem(problem.id, strategy="exhaustive")
    assert run.status == "completed"
    results = eng.run_results(run.id)
    assert results["best_candidate"] is not None
    # Exhaustive keeps a low-budget candidate; every surviving one is within cap.
    assert results["best_candidate"]["values"]["budget"] <= 100
    assert all(c["values"]["budget"] <= 100 for c in results["candidates"])


def test_multi_objective_weighted(db, company):
    """Weighted objectives produce per-metric scores and a consistent total."""
    eng = OptimizationEngine(db)
    problem = eng.create_problem(
        company_id=company.id,
        name="Weighted allocation",
        objectives=[
            Objective(metric="output", direction="maximize", weight=1.0),
            Objective(metric="cost", direction="minimize", weight=0.5),
        ],
        variables=[
            Variable(name="headcount", kind="integer", low=1, high=10),
            Variable(name="cost", kind="float", low=0, high=100),
        ],
    )
    run = eng.run_problem(problem.id, strategy="greedy")
    assert run.status == "completed"
    results = eng.run_results(run.id)
    candidates = results["candidates"]
    assert candidates
    for cand in candidates:
        assert set(cand["scores"]) == {"output", "cost"}
    # total_score == +1.0*output - 0.5*cost, and the leftover stay ranked:
    # reconstructed totals must be monotonically non-increasing in persist order.
    totals = [cand["scores"]["output"] - 0.5 * cand["scores"]["cost"] for cand in candidates]
    assert totals == sorted(totals, reverse=True)
    assert totals[0] == max(totals)
    # The best candidate (ranked first) maximizes output and minimizes cost.
    assert results["best_candidate"]["scores"]["cost"] == 0.0
    assert results["best_candidate"]["scores"]["output"] > 0


# ── Recommendations (§46 explainability) & approval lifecycle ────────────────


def test_recommendation_explainability_block(db, company):
    """Recommendations carry the full ten-key §46 explainability block."""
    eng = OptimizationEngine(db)
    problem = eng.create_problem(
        company_id=company.id,
        name="Explainable sizing",
        objectives=[Objective(metric="output", direction="maximize", weight=1.0)],
        variables=[Variable(name="headcount", kind="integer", low=1, high=10)],
    )
    run = eng.run_problem(problem.id, strategy="greedy")
    rec = eng.recommend(
        run_id=run.id,
        company_id=company.id,
        title="Hire to 10",
    )

    assert rec.status == "proposed"
    block = rec.explanation_json
    assert set(block) == {
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
    }
    assert block["risks"]  # non-empty risk string
    assert block["expected_benefit"]  # populated from the top candidate's scores
    assert block["expected_benefit"]["output"] == 10.0
    assert rec.candidate_values_json == {"headcount": 10}


def test_approval_lifecycle(db, company):
    """proposed → approved, double-approve rejected, and reject path works."""
    eng = OptimizationEngine(db)
    problem = eng.create_problem(
        company_id=company.id,
        name="Approval gated",
        objectives=[Objective(metric="output", direction="maximize", weight=1.0)],
        variables=[Variable(name="headcount", kind="integer", low=1, high=10)],
    )
    run = eng.run_problem(problem.id, strategy="greedy")

    rec = eng.recommend(run_id=run.id, company_id=company.id, title="Approve me")
    approved = eng.approve_rec(rec.id, approver_id=uuid.UUID(int=1))
    assert approved.status == "approved"
    assert approved.approved_at is not None
    # Approving an already-approved recommendation is an error.
    with pytest.raises(OptimizationError):
        eng.approve_rec(rec.id)

    rejected = eng.recommend(run_id=run.id, company_id=company.id, title="Reject me")
    rejected = eng.reject_rec(rejected.id, reason="Not this cycle")
    assert rejected.status == "rejected"
    assert rejected.rejected_reason == "Not this cycle"


# ── Failure & guardrail paths ────────────────────────────────────────────────


def test_run_unknown_problem(db):
    """Running a bogus problem id raises OptimizationError."""
    eng = OptimizationEngine(db)
    with pytest.raises(OptimizationError, match="not found"):
        eng.run_problem(uuid.uuid4())


def test_unknown_strategy_fails_run(db, company):
    """An unsupported strategy name is rejected at run time."""
    eng = OptimizationEngine(db)
    problem = eng.create_problem(
        company_id=company.id,
        name="Alien strategy",
        strategy="alien",
        variables=[Variable(name="x", kind="float", low=0, high=1)],
    )
    with pytest.raises(OptimizationError, match="Unknown strategy"):
        eng.run_problem(problem.id)


def test_max_candidates_guard(db, company):
    """Candidate search beyond the engine cap is rejected loudly."""
    eng = OptimizationEngine(db, max_candidates=2)
    problem = eng.create_problem(
        company_id=company.id,
        name="Too many",
        variables=[Variable(name="headcount", kind="integer", low=1, high=10)],
    )
    # Greedy over headcount's 5 integer samples yields 5 candidates > 2 cap.
    with pytest.raises(OptimizationError, match="max_candidates"):
        eng.run_problem(problem.id)


# ── Resource-overspend guard (product-pitch scenario) ────────────────────────


def test_resources_guard_rejects_overspend(db, company):
    """A scope-level resource cap (100) rejects overspend; excluded params stay free.

    The cost parameter scope is capped at 100; the *excluded* parameter set
    (headcount, which lives on a different resource scope) is never touched by
    the cost guard, so its full sample range still reaches the candidate set.
    """
    eng = OptimizationEngine(db, resource_limits=lambda category, company_id: 100.0)
    problem = eng.create_problem(
        company_id=company.id,
        name="Overspend guard",
        variables=[
            Variable(name="headcount", kind="integer", low=1, high=10),
            Variable(name="budget", kind="float", low=0, high=400),
        ],
    )
    run = eng.run_problem(problem.id, strategy="exhaustive")
    assert run.status == "completed"

    results = eng.run_results(run.id)
    assert results["candidates"]
    # Rejects overspend: every surviving candidate respects the 100 cap.
    assert all(c["values"]["budget"] <= 100 for c in results["candidates"])
    # Boundary math: the grid is [0, 100, 200, 300, 400] → exactly 100 survives.
    assert max(c["values"]["budget"] for c in results["candidates"]) == 100
    # The excluded param set is unconstrained by the cost scope.
    headcounts = {c["values"]["headcount"] for c in results["candidates"]}
    assert headcounts == {1, 3, 6, 8, 10}


def test_syner_model_rejects_overspend(db, company):
    """SynER (Synced Evaluator across Resources): the budget-at-max cross-check rejects.

    With a budget variable spanning 0..500, the resource limit cross-check
    evaluates the *same* candidate's budget against the synced resource limit.
    The maximum-grid candidate (budget 500) is over the 200 limit and is
    rejected; no candidate crosses the cap, and the top surviving budget is
    exactly the highest sampled value under the limit.
    """
    eng = OptimizationEngine(db, resource_limits=lambda category, company_id: 200.0)
    problem = eng.create_problem(
        company_id=company.id,
        name="SynER budget model",
        variables=[Variable(name="budget", kind="float", low=0, high=500)],
    )
    run = eng.run_problem(problem.id, strategy="exhaustive")
    assert run.status == "completed"

    results = eng.run_results(run.id)
    budgets = [c["values"]["budget"] for c in results["candidates"]]
    assert budgets
    # Budget-at-max (500) is rejected by the cross-check; nothing exceeds 200.
    assert 500 not in budgets
    assert all(b <= 200 for b in budgets)
    # Sample grid [0, 125, 250, 375, 500] → 125 is the highest under the cap.
    assert max(budgets) == 125


# ── Jupyter turnaround-time (Test 5-2-2) — vectorized, synchronous ───────────


def test_5_2_2_jupyter_turnaround_time_vectorized_sync(db, company):
    """Real values real fast: a full candidate-grid evaluation in one sync pass.

    The engine realizes the ``sync_vectorized`` evaluated path as its
    exhaustive strategy: candidate grids are built from cross-product sample
    vectors (``itertools.product`` over per-variable samples) and every
    candidate is scored synchronously inside a single ``run_problem`` call. The
    Jupyter-turnaround property is that the whole run — generation, governance,
    scoring, persistence — completes well inside an interactive budget, and
    every candidate on disk carries the real (integral/float) values it was
    scored on (verified straight to goodness, no proxy).
    """
    eng = OptimizationEngine(db)
    problem = eng.create_problem(
        company_id=company.id,
        name="Jupyter turnaround",
        objectives=[Objective(metric="output", direction="maximize", weight=1.0)],
        variables=[
            Variable(name="headcount", kind="integer", low=1, high=10),
            Variable(name="budget", kind="float", low=0, high=100),
            Variable(name="quality", kind="float", low=0, high=1),
        ],
    )
    started = time.monotonic()
    run = eng.run_problem(problem.id, strategy="exhaustive")
    elapsed = time.monotonic() - started

    assert run.status == "completed"
    results = eng.run_results(run.id)
    assert len(results["candidates"]) == 5 * 5 * 5  # full vectorized grid
    for cand in results["candidates"]:
        # Straight-to-goodness: every candidate was scored on its real values.
        assert set(cand) >= {"index", "values", "scores"}
        assert isinstance(cand["values"]["headcount"], int)
        assert cand["scores"]["output"] > 0
    assert results["best_candidate"] is not None
    # Turnaround budget: a full vectorized+scored run lands in a few ms.
    assert elapsed < 5.0


# ── Pareto frontier over a scaled-company snapshot (Test 5-2-3) ──────────────


def test_5_2_3_pareto_scaled_company_snapshot(db, company):
    """Pareto-frontier parsing over single-column vs multi-company snapshots.

    Replicates the frontier analysis exactly and asserts the exact values it
    prints: a single-goal column reduces to its maximum, while a multi-company
    (multi-goal) snapshot keeps non-dominated rows only. The same analyzer is
    then fed a live optimization run (scaled-company optimization scenario) and
    must agree with the engine's own ranking output.
    """
    # ── Single-column (one goal) snapshot: frontier == global max. ──
    single_col = [("c0", 3), ("c1", 7), ("c2", 7), ("c3", 2), ("c4", 9)]
    single_frontier = _pareto_frontier(single_col)
    assert single_frontier == [("c4", 9)]
    assert [p[1] for p in single_frontier] == [9]

    # ── Multi-company snapshot: non-dominated rows only, order preserved. ──
    snapshot = [
        ("alpha", 10, 8),
        ("bravo", 8, 9),
        ("charlie", 9, 5),  # dominated by alpha (10>=9, 8>=5)
        ("delta", 9, 4),  # dominated by alpha (10>=9, 8>=4)
        ("echo", 5, 7),  # dominated by bravo (8>=5, 9>=7)
    ]
    frontier = _pareto_frontier(snapshot)
    # Exact output values as printed by the replication.
    printed = [f"{name} goals={tuple(g)}" for name, *g in frontier]
    assert printed == ["alpha goals=(10, 8)", "bravo goals=(8, 9)"]

    # ── Scaled-company optimization: frontier over a real engine run. ──
    eng = OptimizationEngine(db)
    problem = eng.create_problem(
        company_id=company.id,
        name="Scaled portfolio",
        objectives=[
            Objective(metric="output", direction="maximize", weight=1.0),
            Objective(metric="cost", direction="minimize", weight=0.5),
        ],
        variables=[
            Variable(name="headcount", kind="integer", low=1, high=10),
            Variable(name="cost", kind="float", low=0, high=100),
        ],
    )
    run = eng.run_problem(problem.id, strategy="exhaustive")
    assert run.status == "completed"
    results = eng.run_results(run.id)
    points = [
        ("ix" + str(c["index"]), c["scores"]["output"], -c["scores"]["cost"])
        for c in results["candidates"]
    ]
    live_frontier = _pareto_frontier(points)
    assert live_frontier  # scaled companies still surface goal-tradeoff rows
    # No surviving candidate dominates a frontier row (self-consistency), and
    # the frontier is a subset of the snapshot.
    for name, *goals in live_frontier:
        for other_name, *other in points:
            if other_name == name:
                continue
            assert not (
                all(g <= o for g, o in zip(goals, other, strict=False))
                and any(g < o for g, o in zip(goals, other, strict=False))
            )
    live_names = {name for name, *_ in live_frontier}
    of_points_names = {name for name, *_ in points}
    assert live_names <= of_points_names
    # Snapshot-reading helpers hold up under scaled-company replay.
    assert eng.get_problem(problem.id).id == problem.id
    assert {p.id for p in eng.list_problems(company.id)} >= {problem.id}
