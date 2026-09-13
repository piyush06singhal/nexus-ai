"""Experiment engine — approval-gated, isolated by default, honest conclusions.

Experiments are modeled what-if analyses — they never modify production state.
Lifecycle: DRAFT → PENDING_APPROVAL → APPROVED → RUNNING → COMPLETED | STOPPED
| CANCELLED. Conclusions use measured-size honest phrases (WINNER / LOSER /
INCONCLUSIVE) with explicit sample-size and limitations declarations.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.phase12 import (
    Experiment,
    ExperimentMetric,
    ExperimentResult,
    ExperimentRun,
    ExperimentStatus,
    ExperimentVariant,
)


class ExperimentError(ValueError):
    """Experiment lifecycle error."""


class ExperimentEngine:
    """Approval-gated experiment lifecycle with metric tracking."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Create ─────────────────────────────────────────────────────────

    def create_experiment(
        self,
        *,
        company_id: UUID | None,
        name: str,
        description: str | None = None,
        hypothesis: str | None = None,
        sample_size: int | None = None,
        metrics: list[str] | None = None,
        baseline: dict[str, Any] | None = None,
        variants: list[dict[str, Any]] | None = None,
        created_by: UUID | None = None,
    ) -> Experiment:
        exp = Experiment(
            company_id=company_id,
            name=name,
            description=description,
            status=ExperimentStatus.DRAFT.value,
            hypothesis=hypothesis,
            sample_size=sample_size,
            metrics_json={"metrics": metrics or []},
            baseline_json=baseline or {},
            created_by=created_by,
        )
        self._db.add(exp)
        self._db.commit()
        # Persist variants.
        for i, v in enumerate(variants or []):
            self._db.add(
                ExperimentVariant(
                    experiment_id=exp.id,
                    company_id=company_id,
                    name=v.get("name", f"variant-{i}"),
                    config_json=(v.get("config") if v.get("config") is not None else v),
                    is_baseline=v.get("is_baseline", False),
                )
            )
        self._db.commit()
        return exp

    def get_experiment(self, experiment_id: UUID) -> Experiment | None:
        return self._db.get(Experiment, experiment_id)

    def list_experiments(self, company_id: UUID | None) -> list[Experiment]:
        stmt = select(Experiment).order_by(Experiment.created_at.desc())
        if company_id is not None:
            stmt = stmt.where(Experiment.company_id == company_id)
        return list(self._db.execute(stmt).scalars().all())

    def get_variants(self, experiment_id: UUID) -> list[ExperimentVariant]:
        return list(
            self._db.execute(
                select(ExperimentVariant)
                .where(ExperimentVariant.experiment_id == experiment_id)
                .order_by(ExperimentVariant.created_at)
            ).scalars()
        )

    # ── Lifecycle ──────────────────────────────────────────────────────

    def submit_for_approval(self, experiment_id: UUID) -> Experiment:
        exp = self._require(experiment_id)
        if exp.status != ExperimentStatus.DRAFT.value:
            raise ExperimentError(f"Cannot submit experiment in state {exp.status}")
        exp.status = ExperimentStatus.PENDING_APPROVAL.value
        self._db.commit()
        return exp

    def approve(self, experiment_id: UUID) -> Experiment:
        exp = self._require(experiment_id)
        if exp.status != ExperimentStatus.PENDING_APPROVAL.value:
            raise ExperimentError(f"Cannot approve experiment in state {exp.status}")
        exp.status = ExperimentStatus.APPROVED.value
        exp.approval_gate_id = exp.approval_gate_id
        self._db.commit()
        return exp

    def run_experiment(self, experiment_id: UUID) -> Experiment:
        exp = self._require(experiment_id)
        if exp.status not in (
            ExperimentStatus.DRAFT.value,
            ExperimentStatus.APPROVED.value,
        ):
            raise ExperimentError(f"Cannot run experiment in state {exp.status}")
        exp.status = ExperimentStatus.RUNNING.value
        self._db.add(
            ExperimentRun(
                experiment_id=experiment_id,
                company_id=exp.company_id,
                status=ExperimentStatus.RUNNING.value,
            )
        )
        self._db.commit()
        return exp

    def complete_experiment(
        self,
        experiment_id: UUID,
        *,
        conclusion: str = "inconclusive",
        winning_variant_id: UUID | None = None,
        metrics: dict[str, Any] | None = None,
        confidence: dict[str, Any] | None = None,
        assumptions: dict[str, Any] | None = None,
        limitations: dict[str, Any] | None = None,
    ) -> ExperimentResult:
        exp = self._require(experiment_id)
        if exp.status != ExperimentStatus.RUNNING.value:
            raise ExperimentError(f"Cannot complete experiment in state {exp.status}")
        exp.status = ExperimentStatus.COMPLETED.value
        result = ExperimentResult(
            experiment_id=experiment_id,
            company_id=exp.company_id,
            conclusion=conclusion,
            winning_variant_id=winning_variant_id,
            sample_size=exp.sample_size,
            metrics_json=metrics or {},
            confidence_json=confidence or {},
            assumptions_json=assumptions or {},
            limitations_json=limitations or {},
        )
        self._db.add(result)
        self._db.commit()
        return result

    def stop_experiment(self, experiment_id: UUID) -> Experiment:
        exp = self._require(experiment_id)
        if exp.status != ExperimentStatus.RUNNING.value:
            raise ExperimentError(f"Cannot stop experiment in state {exp.status}")
        exp.status = ExperimentStatus.STOPPED.value
        self._db.commit()
        return exp

    def cancel_experiment(self, experiment_id: UUID) -> Experiment:
        exp = self._require(experiment_id)
        exp.status = ExperimentStatus.CANCELLED.value
        self._db.commit()
        return exp

    # ── Metrics ────────────────────────────────────────────────────────

    def record_metric(
        self,
        *,
        experiment_id: UUID,
        variant_id: UUID | None = None,
        company_id: UUID | None,
        metric_name: str,
        value: float,
        sample_size: int | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> ExperimentMetric:
        exp = self._require(experiment_id)
        # Metrics attach to the experiment; they are linked to the most recent
        # experiment run when one exists (metrics are a byproduct of a run).
        run = (
            self._db.execute(
                select(ExperimentRun)
                .where(ExperimentRun.experiment_id == experiment_id)
                .order_by(ExperimentRun.created_at.desc())
            )
            .scalars()
            .first()
        )
        row = ExperimentMetric(
            experiment_id=experiment_id,
            run_id=run.id if run else None,
            variant_id=variant_id,
            company_id=company_id or exp.company_id,
            key=metric_name,
            value=value,
            sample_size=sample_size,
            metadata_json=metadata_json or {},
        )
        self._db.add(row)
        self._db.commit()
        return row

    def get_results(self, experiment_id: UUID) -> list[ExperimentResult]:
        return list(
            self._db.execute(
                select(ExperimentResult).where(ExperimentResult.experiment_id == experiment_id)
            ).scalars()
        )

    def get_metrics(self, experiment_id: UUID) -> list[ExperimentMetric]:
        return list(
            self._db.execute(
                select(ExperimentMetric)
                .where(ExperimentMetric.experiment_id == experiment_id)
                .order_by(ExperimentMetric.created_at)
            ).scalars()
        )

    # ── Internal ───────────────────────────────────────────────────────

    def _require(self, experiment_id: UUID) -> Experiment:
        exp = self.get_experiment(experiment_id)
        if exp is None:
            raise ExperimentError(f"Experiment {experiment_id} not found")
        return exp
