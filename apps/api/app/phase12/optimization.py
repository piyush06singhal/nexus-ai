"""Optimization engine — weighted multi-objective, provider-neutral, governed.

Every recommendation carries the §46 explainability block (what / why /
alternatives / constraints / why-this-candidate / expected benefit / expected
cost / risks / assumptions / approval). The optimizer never proposes a
policy-violating solution: candidates are evaluated through Phase 11
``PolicyEngine`` + ``ResourceGovernanceService``, and violations are rejected.

Strategies are deterministic and provider-neutral (no external SaaS):
``greedy``, ``exhaustive`` (bounded combinatorial), ``ranking``. Extensible
through an ``OptimizationStrategy`` interface.
"""

from __future__ import annotations

import itertools
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.phase12 import (
    OptimizationCandidate,
    OptimizationProblem,
    OptimizationRecommendation,
    OptimizationRun,
    OptimizationScore,
    OptimizationStatus,
)

# Objective direction helpers.
_MIN = "minimize"
_MAX = "maximize"


class OptimizationError(ValueError):
    """Problem/run/recommendation lifecycle error."""


@dataclass
class Objective:
    metric: str
    direction: str = _MAX
    weight: float = 1.0


@dataclass
class Variable:
    name: str
    kind: str = "float"
    low: float | None = None
    high: float | None = None
    default: float | None = None
    options: list[Any] = field(default_factory=list)

    def samples(self) -> list[Any]:
        if self.options:
            return list(self.options)
        lo = float(self.low if self.low is not None else 0.0)
        hi = float(self.high if self.high is not None else lo + 1.0)
        span = hi - lo
        if span <= 0:
            span = 1.0
        samples = [round(lo + span * (i / 4), 4) for i in range(5)]
        # Integer variables must not produce fractional candidates.
        if self.kind == "integer":
            samples = [round(v) for v in samples]
            samples = list(dict.fromkeys(samples))
        return samples


@dataclass
class Constraint:
    """A constraint on candidate validity (checked by a callable)."""

    name: str
    check: Callable[[dict[str, Any]], bool]
    description: str | None = None


@dataclass
class Candidate:
    values: dict[str, Any]
    scores: dict[str, float] = field(default_factory=dict)
    total_score: float = 0.0
    valid: bool = True
    reason: str | None = None


class OptimizerStrategy(Protocol):
    def name(self) -> str: ...

    def generate(self, variables: list[Variable]) -> list[dict[str, Any]]: ...


class GreedyStrategy:
    """Start from defaults and nudge each variable in the maximizing direction."""

    def name(self) -> str:
        return "greedy"

    def generate(self, variables: list[Variable]) -> list[dict[str, Any]]:
        base: dict[str, Any] = {}
        for v in variables:
            samples = v.samples()
            default_val = v.default
            base[v.name] = (
                default_val if default_val is not None else (samples[0] if samples else None)
            )
        out = [dict(base)]
        for v in variables:
            for s in v.samples():
                if s != base.get(v.name):
                    cand = dict(base)
                    cand[v.name] = s
                    out.append(cand)
        return out


class ExhaustiveStrategy:
    """Bounded combinatorial search over variable sample grids."""

    def name(self) -> str:
        return "exhaustive"

    def generate(self, variables: list[Variable]) -> list[dict[str, Any]]:
        grids = [v.samples() for v in variables]
        out: list[dict[str, Any]] = []
        for combo in itertools.product(*grids):
            out.append(dict(zip([v.name for v in variables], combo, strict=False)))
        return out


class RankingStrategy:
    """Rank candidates by an external scoring signal."""

    def name(self) -> str:
        return "ranking"


class OptimizationEngine:
    """Persistence-facing optimization engine with governance guards."""

    def __init__(
        self,
        db: Session,
        *,
        max_candidates: int = 500,
        policy_check: Callable[[str, UUID | None, dict | None], Any] | None = None,
        resource_limits: Callable[[str, UUID | None], float | None] | None = None,
    ) -> None:
        self._db = db
        self.max_candidates = max_candidates
        self.policy_check = policy_check or self._default_policy
        self.resource_limits = resource_limits or self._default_resource_limit
        # Constraint callables can't be serialized; store them keyed by problem
        # ID so that run_problem() can pick them up without the caller re-passing.
        self._constraint_registry: dict[UUID, list[Constraint]] = {}

    def _default_policy(
        self,
        action: str,
        company_id: UUID | None,
        context: dict | None,
    ) -> Any:
        from app.security.policy import PolicyEngine

        decision = PolicyEngine(self._db).evaluate(
            identity_id=None,
            action=action,
            company_id=company_id,
            context=context,
            record=False,
        )
        return decision

    def _default_resource_limit(self, category: str, company_id: UUID | None) -> float | None:
        from app.security.resources import ResourceGovernanceService

        svc = ResourceGovernanceService(self._db)
        return svc.effective_limit(category, company_id=company_id)

    # ── Problems ──────────────────────────────────────────────────────

    def create_problem(
        self,
        *,
        company_id: UUID | None,
        name: str,
        description: str | None = None,
        strategy: str = "greedy",
        objectives: list[Objective] | None = None,
        variables: list[Variable] | None = None,
        constraints: list[Constraint] | None = None,
        created_by: UUID | None = None,
    ) -> OptimizationProblem:
        problem = OptimizationProblem(
            company_id=company_id,
            name=name,
            description=description,
            status=OptimizationStatus.DRAFT.value,
            objective_json={
                "objectives": [
                    {
                        "metric": o.metric,
                        "direction": o.direction,
                        "weight": o.weight,
                    }
                    for o in (objectives or [])
                ],
                "variables": [self._variable_public(v) for v in (variables or [])],
                "constraints": [
                    {"name": c.name, "description": c.description} for c in (constraints or [])
                ],
            },
            strategy=strategy,
            created_by=created_by,
        )
        self._db.add(problem)
        self._db.commit()
        if constraints:
            self._constraint_registry[problem.id] = constraints
        return problem

    def get_problem(self, problem_id: UUID) -> OptimizationProblem | None:
        return self._db.get(OptimizationProblem, problem_id)

    def list_problems(self, company_id: UUID | None) -> list[OptimizationProblem]:
        stmt = select(OptimizationProblem).order_by(OptimizationProblem.created_at.desc())
        if company_id is not None:
            stmt = stmt.where(OptimizationProblem.company_id == company_id)
        return list(self._db.execute(stmt).scalars().all())

    @staticmethod
    def _variable_public(v: Variable) -> dict[str, Any]:
        return {
            "name": v.name,
            "kind": v.kind,
            "low": v.low,
            "high": v.high,
            "default": v.default,
            "options": v.options,
        }

    # ── Runs ──────────────────────────────────────────────────────────

    def run_problem(
        self,
        problem_id: UUID,
        *,
        strategy: str | None = None,
        constraints: list[Constraint] | None = None,
    ) -> OptimizationRun:
        problem = self.get_problem(problem_id)
        if problem is None:
            raise OptimizationError(f"Problem {problem_id} not found")
        strategy = strategy or problem.strategy or "greedy"
        run = OptimizationRun(
            problem_id=problem_id,
            company_id=problem.company_id,
            status=OptimizationStatus.RUNNING.value,
            strategy=strategy,
        )
        self._db.add(run)
        self._db.commit()
        try:
            self._execute_run(run, constraints=constraints)
        except OptimizationError:
            run.status = OptimizationStatus.FAILED.value
            self._db.commit()
            raise
        return run

    def _execute_run(
        self,
        run: OptimizationRun,
        *,
        constraints: list[Constraint] | None = None,
    ) -> None:
        problem = self.get_problem(run.problem_id)
        if problem is None:
            raise OptimizationError(f"Problem {run.problem_id} not found")
        if constraints is None:
            constraints = self._constraint_registry.get(run.problem_id)
        objectives = self._objectives(problem)
        variables = self._variables(problem)

        gen = self._strategy(run.strategy or "greedy")
        if gen is None:
            raise OptimizationError(f"Unknown strategy {run.strategy}")
        raw_candidates = gen.generate(variables)
        if len(raw_candidates) > self.max_candidates:
            raise OptimizationError(
                f"Candidate search exceeded max_candidates={self.max_candidates}"
            )

        evaluated: list[Candidate] = []
        for raw in raw_candidates:
            candidate = self._evaluate(
                raw,
                objectives,
                variables,
                company_id=problem.company_id,
                constraints=constraints,
            )
            if candidate.valid:
                evaluated.append(candidate)
        evaluated.sort(key=lambda c: c.total_score, reverse=True)

        self._persist_candidates(run, evaluated)
        run.status = OptimizationStatus.COMPLETED.value
        run.completed_at = datetime.now()
        run.result_json = {
            "count": len(evaluated),
            "best": evaluated[0].values if evaluated else None,
            "best_score": (evaluated[0].total_score if evaluated else None),
            "strategy": run.strategy,
        }
        self._db.commit()

    def _strategy(self, name: str) -> OptimizerStrategy | None:
        for cls in (GreedyStrategy, ExhaustiveStrategy, RankingStrategy):
            instance = cls()
            if instance.name() == name:
                return instance
        return None

    def _objectives(self, problem: OptimizationProblem) -> list[Objective]:
        spec = problem.objective_json or {}
        out = []
        for o in spec.get("objectives", []):
            out.append(
                Objective(
                    metric=o.get("metric", ""),
                    direction=o.get("direction", _MAX),
                    weight=float(o.get("weight", 1.0)),
                )
            )
        if not out:
            out.append(Objective(metric="score", direction=_MAX, weight=1.0))
        return out

    def _variables(self, problem: OptimizationProblem) -> list[Variable]:
        spec = problem.objective_json or {}
        out = []
        for v in spec.get("variables", []):
            out.append(
                Variable(
                    name=v.get("name", ""),
                    kind=v.get("kind", "float"),
                    low=v.get("low"),
                    high=v.get("high"),
                    default=v.get("default"),
                    options=v.get("options") or [],
                )
            )
        return out

    def _evaluate(
        self,
        raw: dict[str, Any],
        objectives: list[Objective],
        variables: list[Variable],
        *,
        company_id: UUID | None,
        constraints: list[Constraint] | None = None,
    ) -> Candidate:
        candidate = Candidate(values=raw)
        # Governance: policy + resource limits first —
        # never score a disallowed candidate.
        policy_decision = self.policy_check("optimization.apply", company_id, {"candidate": raw})
        decision = getattr(policy_decision, "decision", str(policy_decision))
        if decision in ("deny", "require_approval"):
            candidate.valid = False
            candidate.reason = f"policy: {decision}"
            return candidate
        # Resource budget guard.
        budget = self.resource_limits("cost", company_id)
        if budget is not None:
            candidate_cost = float(raw.get("budget", 0) or 0)
            if candidate_cost > budget:
                candidate.valid = False
                candidate.reason = f"resource: expected cost {candidate_cost} > limit {budget}"
                return candidate
        # User/engine-supplied candidate constraints — a candidate failing
        # any constraint is rejected before scoring (never proposed).
        for c in constraints or []:
            try:
                ok = bool(c.check(dict(raw)))
            except Exception as exc:  # noqa: BLE001
                ok = False
                candidate.reason = f"constraint: {c.name} error: {exc}"
            if not ok:
                candidate.valid = False
                candidate.reason = candidate.reason or (f"constraint: {c.name}")
                return candidate

        # Score: weighted objectives over variables.
        total = 0.0
        for obj in objectives:
            value = self._objective_value(obj.metric, raw, variables)
            scaled = (value if obj.direction == _MAX else -value) * float(obj.weight)
            candidate.scores[obj.metric] = round(value, 4)
            total += scaled
        candidate.total_score = round(total, 6)
        return candidate

    def _objective_value(
        self,
        metric: str,
        raw: dict[str, Any],
        variables: list[Variable],
    ) -> float:
        # Direct variable references: metric == variable name.
        if metric in raw:
            try:
                return float(raw[metric])
            except (TypeError, ValueError):
                return 0.0
        # Derive objective from available numeric variables.
        nums = []
        for v in variables:
            val = raw.get(v.name)
            try:
                nums.append(float(val))
            except (TypeError, ValueError):
                continue
        if not nums:
            return 0.0
        return float(statistics.fmean(nums))

    def _persist_candidates(
        self,
        run: OptimizationRun,
        candidates: list[Candidate],
    ) -> None:
        for i, c in enumerate(candidates):
            row = OptimizationCandidate(
                run_id=run.id,
                company_id=run.company_id,
                candidate_index=i,
                values_json=c.values,
                variables_json={k: v for k, v in c.values.items()},
                objective_scores_json=c.scores,
            )
            self._db.add(row)
            self._db.flush()  # materialize row.id for child scores
            for metric, value in c.scores.items():
                self._db.add(
                    OptimizationScore(
                        candidate_id=row.id,
                        company_id=run.company_id,
                        metric=metric,
                        value=value,
                        weight=1.0,
                        normalized=c.total_score,
                    )
                )
        self._db.commit()

    def get_run(self, run_id: UUID) -> OptimizationRun | None:
        return self._db.get(OptimizationRun, run_id)

    def run_results(self, run_id: UUID) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run is None:
            raise OptimizationError(f"Run {run_id} not found")
        rows = list(
            self._db.execute(
                select(OptimizationCandidate)
                .where(OptimizationCandidate.run_id == run_id)
                .order_by(OptimizationCandidate.candidate_index)
            ).scalars()
        )
        candidates = [
            {
                "index": c.candidate_index,
                "values": c.values_json,
                "scores": c.objective_scores_json,
            }
            for c in rows
        ]
        return {
            "run_id": str(run_id),
            "status": run.status,
            "strategy": run.strategy,
            "candidates": candidates,
            "best_candidate": candidates[0] if candidates else None,
            "result": run.result_json,
        }

    # ── Recommendations (explainable, approval-gated) ─────────────────

    def recommend(
        self,
        *,
        run_id: UUID,
        company_id: UUID | None,
        title: str,
        created_by: UUID | None = None,
    ) -> OptimizationRecommendation:
        run = self.get_run(run_id)
        if run is None:
            raise OptimizationError(f"Run {run_id} not found")
        best = self._best_candidate(run)
        explanation = self._explainability_block(run, best)
        rec = OptimizationRecommendation(
            run_id=run_id,
            company_id=company_id,
            status="proposed",
            title=title,
            candidate_values_json=(best.get("values") if best else None),
            explanation_json=explanation,
            expected_benefit_json={"description": self._benefit(explanation)},
            expected_cost_json={"description": ("modeled cost, to be confirmed before execution")},
            risk_json={
                "level": "low",
                "notes": [explanation.get("risks", "")],
            },
            assumptions_json={"assumptions": explanation.get("assumptions", [])},
            created_by=created_by,
        )
        self._db.add(rec)
        self._db.commit()
        return rec

    def _best_candidate(self, run: OptimizationRun) -> dict[str, Any] | None:
        rows = list(
            self._db.execute(
                select(OptimizationCandidate)
                .where(OptimizationCandidate.run_id == run.id)
                .order_by(OptimizationCandidate.candidate_index)
            ).scalars()
        )
        if not rows:
            return None
        return {
            "values": rows[0].values_json,
            "scores": rows[0].objective_scores_json,
        }

    def _explainability_block(
        self,
        run: OptimizationRun,
        best: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """§46 — the ten-question explainability block."""
        scores = (best or {}).get("scores") or {}
        return {
            "what": (f"Recommended candidate from run {run.id}"),
            "why": ("Ranked top by weighted objective score across the strategy"),
            "alternatives": [],
            "constraints": ("Policy + resource limits were enforced; no violation allowed"),
            "why_this_candidate": ("Highest total weighted score in the evaluated set"),
            "expected_benefit": {k: v for k, v in scores.items()},
            "expected_cost": ("Modeled cost estimate; confirm before execution"),
            "risks": ("Modeled estimates only — verify before applying"),
            "assumptions": ("Candidate stays within resource limits; scenario unchanged"),
            "approval": ("Required before any execution (ApprovalGateManager)"),
        }

    def _benefit(self, explanation: dict[str, Any]) -> str:
        benefit = explanation.get("expected_benefit")
        if isinstance(benefit, dict):
            return ", ".join(f"{k}={v}" for k, v in benefit.items())
        return "top-ranked candidate"

    def approve_rec(
        self,
        rec_id: UUID,
        *,
        approver_id: UUID | None = None,
    ) -> OptimizationRecommendation:
        rec = self._db.get(OptimizationRecommendation, rec_id)
        if rec is None:
            raise OptimizationError(f"Recommendation {rec_id} not found")
        if rec.status not in ("proposed", "pending_approval"):
            raise OptimizationError(f"Cannot approve recommendation in state {rec.status}")
        rec.status = "approved"
        rec.approved_by = approver_id
        rec.approved_at = datetime.now()
        self._db.commit()
        return rec

    def reject_rec(
        self,
        rec_id: UUID,
        *,
        reason: str | None = None,
    ) -> OptimizationRecommendation:
        rec = self._db.get(OptimizationRecommendation, rec_id)
        if rec is None:
            raise OptimizationError(f"Recommendation {rec_id} not found")
        rec.status = "rejected"
        rec.rejected_reason = reason
        self._db.commit()
        return rec
