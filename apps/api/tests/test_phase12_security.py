"""Phase 12 security — tenant isolation & rejection semantics (§ Wave H).

Adversarial fail-safe tests: company-scoped engines never leak rows across
companies, marketplace payloads carrying secrets/executable keys are rejected,
simulations are sandboxed with no production side effects, an un-approved
execution gate blocks the closed loop, and unpublished packages cannot be
installed (no silent production replacement).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.phase12 import SimulationOutcome, SimulationRun


def _companies(db: Session):
    """Two independent tenants (A and B)."""
    from app.company.manager import CompanyManager

    manager = CompanyManager(db)
    return manager.create(name="Tenant A"), manager.create(name="Tenant B")


# ── Tenant isolation ─────────────────────────────────────────────────────────


class TestTenantIsolation:
    def test_simulation_company_isolation(self, db: Session) -> None:
        from app.phase12.engine import SimulationEngine

        company_a, company_b = _companies(db)
        eng = SimulationEngine(db)
        sim = eng.create(company_id=company_a.id, name="A sim")
        # B's listing must not contain A's simulation.
        assert all(s.id != sim.id for s in eng.list_(company_b.id))
        # Simulated runs are reachable only by run_id; a company-scoped run
        # listing for B excludes A's run row entirely.
        run = eng.run(simulation_id=sim.id, iterations=1)
        assert run.status == "completed"
        assert run.company_id == company_a.id
        b_runs = list(
            db.execute(
                select(SimulationRun).where(SimulationRun.company_id == company_b.id)
            ).scalars()
        )
        assert run.id not in [r.id for r in b_runs]

    def test_optimization_problem_isolation(self, db: Session) -> None:
        from app.phase12.optimization import OptimizationEngine

        company_a, company_b = _companies(db)
        eng = OptimizationEngine(db)
        problem = eng.create_problem(company_id=company_a.id, name="A problem")
        assert all(p.id != problem.id for p in eng.list_problems(company_b.id))

    def test_experiment_isolation(self, db: Session) -> None:
        from app.phase12.experiments import ExperimentEngine

        company_a, company_b = _companies(db)
        eng = ExperimentEngine(db)
        exp = eng.create_experiment(company_id=company_a.id, name="A experiment")
        assert all(e.id != exp.id for e in eng.list_experiments(company_b.id))

    def test_marketplace_isolation(self, db: Session) -> None:
        from app.phase12.marketplace import MarketplaceService

        company_a, company_b = _companies(db)
        service = MarketplaceService(db)
        pkg = service.create_package(name="pkg-a", company_id=company_a.id)
        # B's catalog listing excludes A's package.
        assert all(p.id != pkg.id for p in service.list_packages(company_b.id))
        # Isolation is via creator listing, not global denial: once published,
        # a B-company install records company_id=B (metadata-only install).
        service.add_version(package_id=pkg.id, version="1.0.0")
        service.publish(pkg.id)
        installation = service.install(
            package_id=pkg.id, company_id=company_b.id, require_approval=False
        )
        assert installation.company_id == company_b.id
        assert installation.package_id == pkg.id

    def test_benchmark_isolation(self, db: Session) -> None:
        from app.phase12.benchmarking import BenchmarkEngine

        company_a, company_b = _companies(db)
        eng = BenchmarkEngine(db)
        bench = eng.create_benchmark(company_id=company_a.id, name="A benchmark")
        assert all(b.id != bench.id for b in eng.list_benchmarks(company_b.id))
        # B can run its own benchmarks, but not see A's.
        assert eng.list_benchmarks(company_b.id) == []


# ── Marketplace payload rejection ────────────────────────────────────────────


class TestPayloadRejection:
    def test_marketplace_secret_leak_rejected(self, db: Session) -> None:
        from app.phase12.marketplace import MarketplaceError, MarketplaceService

        company, _ = _companies(db)
        service = MarketplaceService(db)
        # `token` is a forbidden top-level key regardless of value.
        with pytest.raises(MarketplaceError, match="rejected"):
            service.create_package(
                name="leaky",
                company_id=company.id,
                metadata={"token": "sk-1234567890abcdefghijkl"},
            )
        # `api_key` is forbidden at the top level too.
        with pytest.raises(MarketplaceError, match="rejected"):
            service.create_package(
                name="leaky2",
                company_id=company.id,
                metadata={"api_key": "ak_live_abcdef"},
            )

    def test_executable_payload_rejected(self, db: Session) -> None:
        from app.phase12.marketplace import MarketplaceError, MarketplaceService

        company, _ = _companies(db)
        service = MarketplaceService(db)
        for key in ("script", "body", "code", "payload"):
            with pytest.raises(MarketplaceError, match="rejected"):
                service.create_package(
                    name=f"exec-{key}",
                    company_id=company.id,
                    metadata={key: "print('boom')"},
                )

    def test_safe_metadata_accepted(self, db: Session) -> None:
        from app.phase12.marketplace import MarketplaceService

        company, _ = _companies(db)
        service = MarketplaceService(db)
        pkg = service.create_package(
            name="clean",
            company_id=company.id,
            metadata={"display_name": "Clean", "category": "ops"},
        )
        assert pkg.name == "clean"


# ── Sandbox & governance ─────────────────────────────────────────────────────


class TestSandbox:
    def test_simulation_sandbox_no_production_side_effects(self, db: Session) -> None:
        from app.company.manager import CompanyManager
        from app.phase12.engine import SimulationEngine

        company, _ = _companies(db)
        manager = CompanyManager(db)
        company = manager.get(company.id)
        before = (company.name, company.status, company.industry)
        eng = SimulationEngine(db)
        sim = eng.create(company_id=company.id, name="sandboxed")
        run = eng.run(simulation_id=sim.id, iterations=1)
        assert run.status == "completed"
        # Production company row is byte-for-byte unchanged.
        company = manager.get(company.id)
        assert (company.name, company.status, company.industry) == before
        # Every stored simulation outcome is labeled SIMULATED — never ACTUAL.
        outcomes = list(db.execute(select(SimulationOutcome)).scalars())
        assert outcomes
        assert all(o.output_kind == "simulated" for o in outcomes)

    def test_no_simulation_budget_exceeded(self, db: Session) -> None:
        """No limit configured → the run budget records usage without raising."""
        from app.phase12.engine import SimulationEngine

        company, _ = _companies(db)
        eng = SimulationEngine(db)
        sim = eng.create(company_id=company.id, name="budgeted")
        run = eng.run(simulation_id=sim.id, iterations=1)
        assert run.status == "completed"
        assert run.summary_json is not None and run.summary_json["iterations"] == 1


class TestGovernance:
    def test_approval_gate_blocks_execution(self, db: Session) -> None:
        from app.phase12.loop import LoopError, NEXUSOptimizationLoop

        company, _ = _companies(db)
        loop = NEXUSOptimizationLoop(db)
        cycle = loop.run_full_cycle(company_id=company.id, name="Gated")
        assert cycle.status == "awaiting_approval"
        with pytest.raises(LoopError, match="not approved"):
            loop.execute(cycle.id)

    def test_publication_policy_bypass(self, db: Session) -> None:
        """Unpublished packages can never install — no silent replacement."""
        from app.phase12.marketplace import MarketplaceError, MarketplaceService

        company, _ = _companies(db)
        service = MarketplaceService(db)
        pkg = service.create_package(name="draft-pkg", company_id=company.id)
        service.add_version(package_id=pkg.id, version="1.0.0")
        assert pkg.status == "draft"
        with pytest.raises(MarketplaceError, match="not published"):
            service.install(package_id=pkg.id, company_id=company.id, require_approval=False)

    def test_tenant_uuid_validation(self, db: Session) -> None:
        """A random/foreign uuid yields empty listings, never cross-tenant data."""
        from app.phase12.benchmarking import BenchmarkEngine
        from app.phase12.engine import SimulationEngine
        from app.phase12.experiments import ExperimentEngine
        from app.phase12.loop import NEXUSOptimizationLoop
        from app.phase12.marketplace import MarketplaceService
        from app.phase12.optimization import OptimizationEngine

        stranger = uuid4()
        assert SimulationEngine(db).list_(stranger) == []
        assert OptimizationEngine(db).list_problems(stranger) == []
        assert ExperimentEngine(db).list_experiments(stranger) == []
        assert MarketplaceService(db).list_packages(stranger) == []
        assert BenchmarkEngine(db).list_benchmarks(stranger) == []
        assert NEXUSOptimizationLoop(db).list_cycles(stranger) == []


# ── API not-found semantics (REST: GET on a missing resource => 404, never 500) ─


class TestApiNotFoundSemantics:
    """A well-formed but nonexistent run id must produce 404, not an engine 500.

    Regression for the smoke sweep (scripts.smoke_api --phase 12): the run
    detail/state/results routes raised SimulationEngineError/BenchmarkError to
    the exception middleware, yielding internal_error 500s for missing ids.
    """

    def test_simulation_run_routes_404_on_missing_run(self, api_client):
        from uuid import uuid4

        missing = uuid4()
        for path in (
            f"/api/v1/simulations/runs/{missing}",
            f"/api/v1/simulations/runs/{missing}/state",
            f"/api/v1/simulations/runs/{missing}/results",
        ):
            resp = api_client.get(path)
            assert resp.status_code == 404, (
                f"{path} expected 404, got {resp.status_code}: {resp.text[:120]}"
            )

    def test_benchmark_run_results_404_on_missing_run(self, api_client):
        from uuid import uuid4

        resp = api_client.get(f"/api/v1/benchmarks/runs/{uuid4()}/results")
        assert resp.status_code == 404, f"expected 404, got {resp.status_code}: {resp.text[:120]}"

    def test_optimization_run_404_on_missing_run(self, api_client):
        from uuid import uuid4

        resp = api_client.get(f"/api/v1/optimization/runs/{uuid4()}")
        assert resp.status_code == 404, f"expected 404, got {resp.status_code}: {resp.text[:120]}"
