"""Phase 12 experiments tests (§60).

Experiments are approval-gated, isolated-by-default, what-if analyses. They
never modify production state; conclusions use measured-size honest phrases
(WINNER / LOSER / INCONCLUSIVE) with explicit sample-size and limitations
declarations.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.phase12 import ExperimentRun
from app.phase12.experiments import ExperimentEngine, ExperimentError


def _make_company(db: Session):
    from app.company.manager import CompanyManager

    return CompanyManager(db).create(name="Experiments Co")


def _running_experiment(db: Session):
    """Prepare an approved, running experiment with two variants."""
    company = _make_company(db)
    eng = ExperimentEngine(db)
    exp = eng.create_experiment(
        company_id=company.id,
        name="Pricing A/B",
        description="Week-long conversion experiment",
        hypothesis="A lower anchor lifts conversion.",
        sample_size=200,
        metrics=["conversion", "revenue_per_user"],
        baseline={"conversion": 0.03},
        variants=[
            {"name": "control", "config": {"price": 49}, "is_baseline": True},
            {"name": "test", "config": {"price": 39}},
        ],
    )
    eng.submit_for_approval(exp.id)
    eng.approve(exp.id)
    eng.run_experiment(exp.id)
    return company, eng, exp


class TestCreate:
    def test_create_experiment_starts_draft(self, db: Session) -> None:
        company = _make_company(db)
        eng = ExperimentEngine(db)
        exp = eng.create_experiment(company_id=company.id, name="E1")
        assert exp.status == "draft"
        assert eng.get_experiment(exp.id) is exp or eng.get_experiment(exp.id).id == exp.id
        assert exp.company_id == company.id

    def test_create_persists_variants_and_baseline(self, db: Session) -> None:
        company = _make_company(db)
        eng = ExperimentEngine(db)
        exp = eng.create_experiment(
            company_id=company.id,
            name="E2",
            sample_size=100,
            baseline={"conversion": 0.05},
            variants=[
                {"name": "control", "is_baseline": True},
                {"name": "test", "config": {"x": 1}},
            ],
        )
        variants = eng.get_variants(exp.id)
        assert len(variants) == 2
        by_name = {v.name: v for v in variants}
        assert by_name["control"].is_baseline is True
        assert by_name["test"].config_json == {"x": 1}


class TestLifecycle:
    def test_submit_for_approval_transitions(self, db: Session) -> None:
        company = _make_company(db)
        eng = ExperimentEngine(db)
        exp = eng.create_experiment(company_id=company.id, name="E")
        assert eng.submit_for_approval(exp.id).status == "pending_approval"

    def test_submit_requires_draft(self, db: Session) -> None:
        company = _make_company(db)
        eng = ExperimentEngine(db)
        exp = eng.create_experiment(company_id=company.id, name="E")
        eng.submit_for_approval(exp.id)
        with pytest.raises(ExperimentError, match="state"):
            eng.submit_for_approval(exp.id)

    def test_approve_transitions(self, db: Session) -> None:
        company = _make_company(db)
        eng = ExperimentEngine(db)
        exp = eng.create_experiment(company_id=company.id, name="E")
        eng.submit_for_approval(exp.id)
        assert eng.approve(exp.id).status == "approved"

    def test_approve_requires_pending(self, db: Session) -> None:
        company = _make_company(db)
        eng = ExperimentEngine(db)
        exp = eng.create_experiment(company_id=company.id, name="E")
        with pytest.raises(ExperimentError, match="state"):
            eng.approve(exp.id)

    def test_run_experiment_creates_run(self, db: Session) -> None:
        company = _make_company(db)
        eng = ExperimentEngine(db)
        exp = eng.create_experiment(company_id=company.id, name="E")
        eng.run_experiment(exp.id)
        assert exp.status == "running"
        runs = list(
            db.execute(select(ExperimentRun).where(ExperimentRun.experiment_id == exp.id)).scalars()
        )
        assert len(runs) == 1
        assert runs[0].status == "running"

    def test_run_rejects_non_runnable_states(self, db: Session) -> None:
        company = _make_company(db)
        eng = ExperimentEngine(db)
        exp = eng.create_experiment(company_id=company.id, name="E")
        exp.status = "pending_approval"  # pending cannot run directly
        db.commit()
        with pytest.raises(ExperimentError, match="state"):
            eng.run_experiment(exp.id)

    def test_complete_requires_running(self, db: Session) -> None:
        company = _make_company(db)
        eng = ExperimentEngine(db)
        exp = eng.create_experiment(company_id=company.id, name="E")
        with pytest.raises(ExperimentError, match="state"):
            eng.complete_experiment(exp.id)

    def test_complete_winner_is_honest(self, db: Session) -> None:
        """A WINNER needs sample_size + confidence + limitations on the row."""
        company, eng, exp = _running_experiment(db)
        variants = eng.get_variants(exp.id)
        winner = next(v for v in variants if not v.is_baseline)
        result = eng.complete_experiment(
            exp.id,
            conclusion="winner",
            winning_variant_id=winner.id,
            metrics={"conversion": 0.041},
            confidence={"p_value": 0.012, "interval": [0.031, 0.052]},
            limitations={"coverage": "north america only", "season": "summer"},
        )
        assert exp.status == "completed"
        assert result is eng.get_results(exp.id)[0]
        assert result.conclusion == "winner"
        assert result.winning_variant_id == winner.id
        # Honesty contract: measured-size claims carry sample + limitations.
        assert result.sample_size == exp.sample_size == 200
        assert result.confidence_json == {"p_value": 0.012, "interval": [0.031, 0.052]}
        assert result.limitations_json == {
            "coverage": "north america only",
            "season": "summer",
        }

    def test_complete_inconclusive(self, db: Session) -> None:
        company, eng, exp = _running_experiment(db)
        result = eng.complete_experiment(exp.id)
        assert exp.status == "completed"
        assert result.conclusion == "inconclusive"

    def test_stop_requires_running(self, db: Session) -> None:
        company = _make_company(db)
        eng = ExperimentEngine(db)
        exp = eng.create_experiment(company_id=company.id, name="E")
        with pytest.raises(ExperimentError, match="state"):
            eng.stop_experiment(exp.id)
        eng.run_experiment(exp.id)
        assert eng.stop_experiment(exp.id).status == "stopped"
        # Stopped is terminal for stop.
        with pytest.raises(ExperimentError, match="state"):
            eng.stop_experiment(exp.id)

    def test_cancel_any_state(self, db: Session) -> None:
        company = _make_company(db)
        eng = ExperimentEngine(db)
        for exp in (
            eng.create_experiment(company_id=company.id, name="c1"),
            eng.create_experiment(company_id=company.id, name="c2"),
        ):
            assert eng.cancel_experiment(exp.id).status == "cancelled"


class TestMetrics:
    def test_record_metric_and_read_back(self, db: Session) -> None:
        company, eng, exp = _running_experiment(db)
        metric = eng.record_metric(
            experiment_id=exp.id,
            company_id=company.id,
            metric_name="conversion",
            value=0.041,
            sample_size=100,
            metadata_json={"bucket": "week-1"},
        )
        assert metric.key == "conversion"
        assert metric.value == 0.041
        assert metric.experiment_id == exp.id
        rows = eng.get_metrics(exp.id)
        assert len(rows) == 1
        assert rows[0].id == metric.id
        assert rows[0].sample_size == 100
        assert rows[0].metadata_json == {"bucket": "week-1"}

    def test_metrics_attach_to_latest_run(self, db: Session) -> None:
        company, eng, exp = _running_experiment(db)
        run = (
            db.execute(select(ExperimentRun).where(ExperimentRun.experiment_id == exp.id))
            .scalars()
            .one()
        )
        metrics = eng.get_metrics(exp.id)
        assert metrics == []  # nothing recorded yet
        eng.record_metric(
            experiment_id=exp.id,
            company_id=company.id,
            metric_name="revenue",
            value=120.5,
        )
        assert eng.get_metrics(exp.id)[0].run_id == run.id

    def test_metrics_require_experiment(self, db: Session) -> None:
        import uuid

        eng = ExperimentEngine(db)
        with pytest.raises(ExperimentError, match="not found"):
            eng.record_metric(
                experiment_id=uuid.uuid4(),
                company_id=uuid.uuid4(),
                metric_name="x",
                value=1.0,
            )


class TestListing:
    def test_list_experiments_company_scoped(self, db: Session) -> None:
        from app.company.manager import CompanyManager

        company_a = CompanyManager(db).create(name="Experiments Co A")
        company_b = CompanyManager(db).create(name="Experiments Co B")
        eng = ExperimentEngine(db)
        eng.create_experiment(company_id=company_a.id, name="Secret A")
        eng.create_experiment(company_id=company_b.id, name="B experiment")
        # A's listing only ever contains A's experiments — no cross-tenant leak.
        assert [e.company_id for e in eng.list_experiments(company_a.id)] == [company_a.id]
        assert [e.company_id for e in eng.list_experiments(company_b.id)] == [company_b.id]

    def test_get_results_only_after_completion(self, db: Session) -> None:
        company, eng, exp = _running_experiment(db)
        assert eng.get_results(exp.id) == []
        eng.complete_experiment(exp.id)
        assert len(eng.get_results(exp.id)) == 1


def test_error_is_value_error_subclass() -> None:
    assert issubclass(ExperimentError, ValueError)
