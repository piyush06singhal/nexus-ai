"""Observation layer — aggregate observable company state into a snapshot.

:class:`ObservationLayer` samples authoritative data (tasks, verifications,
recoveries, budgets, KPIs, goals, risks, products, projects) and produces a
:class:`StateSnapshot` where every dimension is backed by a real, server-side
computed metric — never a fabricated score. The operating cycle's OBSERVE stage
uses this to decide what to assess next.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.company.budget import BudgetManager
from app.company.kpis import KPIService
from app.company.performance import PerformanceAggregator
from app.company.risks import RiskManager
from app.startup.products import ProductManager
from app.startup.projects import ProjectManager
from app.startup.types import StateSnapshot

# Dimension weights used to fold normalized metrics into an overall score.
_DIMENSION_WEIGHTS: dict[str, float] = {
    "execution_health": 0.25,
    "verification": 0.20,
    "recovery": 0.15,
    "budget": 0.20,
    "goal_progress": 0.10,
    "workforce": 0.10,
}


class ObservationLayer:
    """Sample company state → :class:`StateSnapshot` (all metrics observable)."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._performance = PerformanceAggregator(db)
        self._kpis = KPIService(db)
        self._budgets = BudgetManager(db)
        self._risks = RiskManager(db)

    def observe(self, company_id: UUID) -> StateSnapshot:
        perf = self._performance.aggregate(company_id)
        kpi_values = self._kpi_readings(company_id)
        risk = self._risk_score(company_id)
        budget = self._budget_health(company_id)
        projects = ProjectManager(self._db).list_(company_id)
        products = ProductManager(self._db).list_(company_id)

        success_rate = _pct(perf.get("success_rate"))
        verification_rate = _pct(perf.get("verification_rate"))
        recovery_rate = _pct(perf.get("recovery_rate"))

        dimensions: dict[str, float] = {
            "execution_health": _ratio(success_rate),
            "verification": _ratio(verification_rate),
            "recovery": _ratio(recovery_rate),
            "budget": budget["health"],
            "goal_progress": _ratio(perf.get("goal_progress")),
            "workforce": _ratio(perf.get("employee_utilization")),
            "risk": 1.0 - risk["score"],
        }
        overall = _weighted_score(dimensions)

        metrics = {
            "task_volume": perf.get("task_volume", 0),
            "completed_tasks": perf.get("completed_tasks", 0),
            "failed_tasks": perf.get("failed_tasks", 0),
            "verification_rate": verification_rate,
            "recovery_rate": recovery_rate,
            "total_cost": perf.get("total_cost", 0.0),
            "average_latency_ms": perf.get("average_latency_ms", 0.0),
            "employee_count": perf.get("employee_count", 0),
            "employee_utilization": perf.get("employee_utilization", 0.0),
            "kpis": kpi_values,
            "budget": budget["metrics"],
            "open_risks": risk["count"],
            "active_projects": sum(1 for p in projects if p.status.value in ("planned", "active")),
            "products": len(products),
        }
        explanations = _explanations(perf, kpi_values, budget, risk)
        return StateSnapshot(
            overall_score=round(overall, 4),
            dimensions={k: round(v, 4) for k, v in dimensions.items()},
            explanations=explanations,
            metrics=metrics,
        )

    def persist(
        self,
        company_id: UUID,
        snapshot: StateSnapshot,
        *,
        cycle_id: UUID | None = None,
    ) -> Any:
        """Write a snapshot row (auditable, never mutable after creation)."""
        from app.db.models.startup import CompanyStateSnapshot

        row = CompanyStateSnapshot(
            company_id=company_id,
            cycle_id=cycle_id,
            overall_score=snapshot.overall_score,
            dimensions=__import__("json").dumps(snapshot.dimensions, default=str),
            explanations=__import__("json").dumps(snapshot.explanations, default=str),
        )
        self._db.add(row)
        self._db.commit()
        return row

    def list_snapshots(self, company_id: UUID, *, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent snapshot rows (index 0 = most recent)."""
        from sqlalchemy import select

        from app.db.models.startup import CompanyStateSnapshot

        stmt = (
            select(CompanyStateSnapshot)
            .where(CompanyStateSnapshot.company_id == company_id)
            .order_by(CompanyStateSnapshot.computed_at.desc())
            .limit(limit)
        )
        rows = list(self._db.execute(stmt).scalars().all())
        return [_snapshot_to_dict(r) for r in rows]

    def latest_snapshot(self, company_id: UUID) -> dict[str, Any] | None:
        snapshots = self.list_snapshots(company_id, limit=1)
        return snapshots[0] if snapshots else None

    # ── Internals ─────────────────────────────────────────────────────

    def _kpi_readings(self, company_id: UUID) -> list[dict[str, Any]]:
        readings = []
        for kpi in self._kpis.list_(company_id):
            latest = self._kpis._latest_value(kpi.id)
            target = kpi.target
            attainment = (
                None
                if latest is None
                else (1.0 if target is None or not target else _ratio(latest / target))
            )
            readings.append(
                {
                    "kpi_id": str(kpi.id),
                    "name": kpi.name,
                    "source_metric": kpi.source_metric,
                    "value": latest,
                    "target": target,
                    "attainment": round(attainment, 4) if attainment is not None else None,
                }
            )
        return readings

    def _budget_health(self, company_id: UUID) -> dict[str, Any]:
        budget = self._budgets.company_budget(company_id)
        if budget is None or not budget.monthly_limit:
            return {"health": 1.0, "metrics": {"monthly_limit": 0, "spent": 0}}
        spent = float(budget.spent or 0.0)
        limit = float(budget.monthly_limit)
        ratio = spent / limit
        return {
            "health": round(max(0.0, 1.0 - ratio), 4),
            "metrics": {
                "monthly_limit": limit,
                "spent": spent,
                "utilization": round(ratio, 4),
            },
        }

    def _risk_score(self, company_id: UUID) -> dict[str, Any]:
        risks = self._risks.list_(company_id)
        if not risks:
            return {"score": 0.0, "count": 0}
        weights = {"critical": 1.0, "high": 0.7, "medium": 0.4, "low": 0.15}
        # Count only open risks (not closed/mitigated).
        open_risks = [
            r
            for r in risks
            if getattr(r.status, "value", r.status) not in ("closed", "mitigated", "resolved")
        ]
        score = sum(weights.get(getattr(r.severity, "value", "medium"), 0.4) for r in open_risks)
        return {"score": min(1.0, score / max(1, len(risks))), "count": len(open_risks)}


def _snapshot_to_dict(row) -> dict[str, Any]:
    import json

    def _loads(raw: str | None) -> Any:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    return {
        "id": str(row.id),
        "company_id": str(row.company_id),
        "cycle_id": str(row.cycle_id) if row.cycle_id else None,
        "overall_score": row.overall_score,
        "dimensions": _loads(row.dimensions) or {},
        "explanations": _loads(row.explanations) or {},
        "computed_at": row.computed_at.isoformat() if row.computed_at else None,
    }


def _pct(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _ratio(value: Any) -> float:
    try:
        v = float(value or 0.0)
    except (TypeError, ValueError):
        v = 0.0
    if v >= 1.0:
        return v / 100.0 if v > 1.5 else v
    return v


def _weighted_score(dimensions: dict[str, float]) -> float:
    total_weight = 0.0
    weighted = 0.0
    for name, weight in _DIMENSION_WEIGHTS.items():
        value = dimensions.get(name)
        if value is None:
            continue
        total_weight += weight
        weighted += weight * max(0.0, min(1.0, value))
    if total_weight == 0:
        return 0.0
    # Fold the unweighted safety dimensions (risk) in.
    risk = dimensions.get("risk")
    if risk is not None:
        weighted += 0.2 * max(0.0, min(1.0, risk))
        total_weight += 0.2
    return weighted / total_weight


def _explanations(
    perf: dict[str, Any],
    kpi_values: list[dict[str, Any]],
    budget: dict[str, Any],
    risk: dict[str, Any],
) -> dict[str, str]:
    return {
        "execution_health": (
            f"Task success rate is {_pct(perf.get('success_rate')):.0f}% "
            f"across {perf.get('task_volume', 0)} tasks"
        ),
        "verification": (f"Verification pass rate is {_pct(perf.get('verification_rate')):.0f}%"),
        "recovery": (f"Recovery rate is {_pct(perf.get('recovery_rate')):.0f}%"),
        "budget": (
            f"${budget.get('metrics', {}).get('spent', 0):.2f} spent of "
            f"${budget.get('metrics', {}).get('monthly_limit', 0):.2f} monthly limit"
        ),
        "goal_progress": f"Average goal progress is {_pct(perf.get('goal_progress')):.0f}%",
        "workforce": (
            f"Employee utilization is {_pct(perf.get('employee_utilization')):.0f}% "
            f"({perf.get('employee_count', 0)} employees)"
        ),
        "risk": f"{risk.get('count', 0)} open risks",
        "kpis": (
            f"{len(kpi_values)} KPIs tracked "
            f"({sum(1 for k in kpi_values if (k.get('attainment') or 0) >= 1.0)} at target)"
        ),
    }
