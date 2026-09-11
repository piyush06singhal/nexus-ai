"""AI Company Layer — company/department policy service.

Policies flow through the organizational hierarchy:

    Global System Policy → Company Policy → Department Policy → Employee Policy → Task Policy

Policy resolution algorithm (documented + unit-tested):

1. Collect every applicable policy for the target hierarchy (employee or
   task or bare company/department). Each policy carries a scope: ``system``
   (company_id None), ``company``, ``department``, ``employee`` (from the
   employee's Phase 7 ``policies`` JSON), or ``task`` (optional caller-provided
   task policies).
2. For each policy key, gather all applicable values across the hierarchy.
3. The **effective value is the most restrictive applicable value**. For a
   value that imposes a restriction, "most restrictive" is the one that most
   constrains behavior:
   - boolean restriction flags (e.g. ``high_risk_actions_require_approval``):
     ``True`` is more restrictive than ``False``.
   - numeric *limits* (keys containing ``limit`` / ``budget`` / ``max`` /
     ``cap`` / ``tokens``): the **minimum** is more restrictive.
   - numeric *minimum thresholds* (keys containing ``score`` / ``threshold`` /
     ``minimum`` / ``min`` / ``verify``): the **maximum** is more restrictive.
   - otherwise the value from the **narrowest scope** wins (task > employee >
     department > company > system).
4. A less restrictive child policy can never weaken a more restrictive parent
   — this is exactly the "most restrictive wins" rule.

Policies are enforced by backend services (budget, routing, approval) by
querying :meth:`PolicyResolver.effective`, never merely by prompting.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.company.events import OrgEventLogger
from app.db.models.company import (
    Policy,
    PolicyScopeType,
)
from app.db.models.employee import AIEmployee

# Keys whose policy values are a boolean restriction flag (True = restrictive).
_BOOLEAN_RESTRICTION_KEYS = {
    "require_approval",
    "high_risk_actions_require_approval",
    "require_verification",
    "require_approval_for_tools",
    "read_only",
    "approval_required",
    "manual_approval",
}

# Keys whose policy values are numeric limits (min is restrictive).
_NUMERIC_LIMIT_HINTS = ("limit", "budget", "max", "cap", "tokens", "concurrency", "spend", "cost")

# Keys whose policy values are numeric minimum thresholds (max is restrictive).
_NUMERIC_THRESHOLD_HINTS = (
    "score",
    "threshold",
    "minimum",
    "min_",
    "verify",
    "confidence",
    "success_rate",
)


def _is_boolean_restriction(key: str) -> bool:
    return key.lower() in _BOOLEAN_RESTRICTION_KEYS


def _is_numeric_value(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _scope_rank(scope: str) -> int:
    """Higher rank = narrower (more specific) scope."""
    order = {"system": 0, "company": 1, "department": 2, "employee": 3, "task": 4}
    return order.get(scope, 1)


def most_restrictive(key: str, a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Return the more restrictive of two {value, scope} policy candidates."""
    va = a["value"]
    vb = b["value"]

    kl = key.lower()
    if _is_boolean_restriction(kl):
        # True (restriction enabled) beats False.
        if va is not vb and isinstance(va, bool) and isinstance(vb, bool):
            return a if va is True else b
    elif _is_numeric_value(va) and _is_numeric_value(vb):
        if any(h in kl for h in _NUMERIC_LIMIT_HINTS):
            return a if va <= vb else b  # min limit is restrictive
        if any(h in kl for h in _NUMERIC_THRESHOLD_HINTS):
            return a if va >= vb else b  # max threshold is restrictive
    # Default: narrowest scope wins.
    if a["scope"] != b["scope"]:
        return a if _scope_rank(a["scope"]) > _scope_rank(b["scope"]) else b
    return a


class PolicyManager:
    """CRUD for company/system/department policies."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self.events = OrgEventLogger(db)

    def create(
        self,
        *,
        scope_type: PolicyScopeType,
        company_id: UUID | None,
        scope_id: UUID | None,
        name: str,
        key: str,
        value: Any,
        priority: int = 0,
        enabled: bool = True,
    ) -> Policy:
        """Create a policy. ``scope_type=system`` implies ``company_id=None``."""
        if scope_type == PolicyScopeType.SYSTEM:
            company_id = None
            scope_id = None
        policy = Policy(
            company_id=company_id,
            scope_type=scope_type,
            scope_id=scope_id,
            name=name,
            key=key,
            value=json.dumps(value),
            priority=priority,
            enabled=enabled,
        )
        self._db.add(policy)
        self._db.flush()
        if company_id is not None:
            self.events.log(
                actor="system",
                action="policy_created",
                company_id=company_id,
                target_type="policy",
                target_id=policy.id,
                details={"name": name, "key": key},
                outcome="success",
            )
        self._db.commit()
        return policy

    def get(self, policy_id: UUID) -> Policy | None:
        return self._db.get(Policy, policy_id)

    def delete(self, policy_id: UUID) -> bool:
        policy = self._db.get(Policy, policy_id)
        if policy is None:
            return False
        self._db.delete(policy)
        self._db.commit()
        return True

    def list_(self, company_id: UUID) -> list[Policy]:
        stmt = (
            select(Policy)
            .where((Policy.company_id == company_id) | (Policy.company_id.is_(None)))
            .order_by(Policy.created_at.desc())
        )
        return list(self._db.execute(stmt).scalars().all())

    def to_dict(self, policy: Policy) -> dict[str, Any]:
        """Serialize a policy for API output."""
        return {
            "id": str(policy.id),
            "company_id": str(policy.company_id) if policy.company_id else None,
            "scope_type": policy.scope_type.value,
            "scope_id": str(policy.scope_id) if policy.scope_id else None,
            "name": policy.name,
            "key": policy.key,
            "value": json.loads(policy.value) if policy.value else None,
            "priority": policy.priority,
            "enabled": policy.enabled,
            "created_at": policy.created_at.isoformat() if policy.created_at else None,
            "updated_at": policy.updated_at.isoformat() if policy.updated_at else None,
        }


class PolicyResolver:
    """Resolve the effective (most restrictive) policy for a hierarchy."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def _collect_policy_values(
        self,
        company_id: UUID | None,
        department_id: UUID | None,
        employee_id: UUID | None,
        task_policies: dict[str, Any] | None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Collect applicable {value, scope} candidates for every key."""
        candidates: dict[str, list[dict[str, Any]]] = {}

        def _add(key: str, value: Any, scope: str) -> None:
            if key is None or value is None:
                return
            candidates.setdefault(key, []).append({"value": value, "scope": scope})

        # 1. Global system policies.
        stmt = select(Policy).where(
            Policy.scope_type == PolicyScopeType.SYSTEM, Policy.enabled.is_(True)
        )
        for p in self._db.execute(stmt).scalars():
            _add(p.key, json.loads(p.value), "system")

        if company_id is not None:
            # 2. Company policies.
            for p in self._db.execute(
                select(Policy).where(
                    Policy.scope_type == PolicyScopeType.COMPANY,
                    Policy.company_id == company_id,
                    Policy.enabled.is_(True),
                )
            ).scalars():
                _add(p.key, json.loads(p.value), "company")

        if department_id is not None:
            # 3. Department policies.
            for p in self._db.execute(
                select(Policy).where(
                    Policy.scope_type == PolicyScopeType.DEPARTMENT,
                    Policy.scope_id == department_id,
                    Policy.enabled.is_(True),
                )
            ).scalars():
                _add(p.key, json.loads(p.value), "department")

        if employee_id is not None:
            # 4. Employee policies (Phase 7 AIEmployee.policies JSON).
            emp = self._db.get(AIEmployee, employee_id)
            if emp is not None and emp.policies:
                try:
                    emp_policies = json.loads(emp.policies)
                except json.JSONDecodeError:
                    emp_policies = {}
                for k, v in emp_policies.items():
                    _add(k, v, "employee")

        if task_policies:
            # 5. Task policies (caller-provided, narrowest scope).
            for k, v in task_policies.items():
                _add(k, v, "task")

        return candidates

    def effective(
        self,
        key: str,
        *,
        company_id: UUID | None = None,
        department_id: UUID | None = None,
        employee_id: UUID | None = None,
        task_policies: dict[str, Any] | None = None,
        default: Any = None,
    ) -> Any:
        """Resolve the effective (most-restrictive) value for a single key."""
        candidates = self._collect_policy_values(
            company_id, department_id, employee_id, task_policies
        ).get(key)
        if not candidates:
            return default
        chosen = candidates[0]
        for cand in candidates[1:]:
            chosen = most_restrictive(key, chosen, cand)
        return chosen["value"]

    def effective_all(
        self,
        *,
        company_id: UUID | None = None,
        department_id: UUID | None = None,
        employee_id: UUID | None = None,
        task_policies: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve every key across the hierarchy (most restrictive per key)."""
        candidates = self._collect_policy_values(
            company_id, department_id, employee_id, task_policies
        )
        out: dict[str, Any] = {}
        for key, cands in candidates.items():
            chosen = cands[0]
            for cand in cands[1:]:
                chosen = most_restrictive(key, chosen, cand)
            out[key] = chosen["value"]
        return out

    def effective_detail(
        self,
        key: str,
        *,
        company_id: UUID | None = None,
        department_id: UUID | None = None,
        employee_id: UUID | None = None,
        task_policies: dict[str, Any] | None = None,
        default: Any = None,
    ) -> dict[str, Any]:
        """Return the resolved value + the source scope for explainability."""
        candidates = self._collect_policy_values(
            company_id, department_id, employee_id, task_policies
        ).get(key)
        if not candidates:
            return {"key": key, "value": default, "source_scope": None, "source_name": None}
        chosen = candidates[0]
        for cand in candidates[1:]:
            chosen = most_restrictive(key, chosen, cand)
        return {
            "key": key,
            "value": chosen["value"],
            "source_scope": chosen["scope"],
            "applicable_scopes": [c["scope"] for c in candidates],
        }
