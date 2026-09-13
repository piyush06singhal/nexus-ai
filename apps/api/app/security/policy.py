"""Policy engine (§51/§52) — most-restrictive-wins over ``policy_rules``.

The security policy engine evaluates governance rules for an action and returns
``ALLOW`` / ``DENY`` / ``REQUIRE_APPROVAL``. It composes — never replaces —
the org-level ``app/company/policies.py::PolicyResolver`` (which continues to
enforce company/department/employee/task policy downstream), and it records
every decision to ``policy_decisions`` for auditability.

Resolution rules:
- Applicable rules: enabled, subject pattern matches the principal kind (or
  ``*``), action pattern matches the action, and the rule's tenant scope
  matches (SYSTEM applies everywhere; COMPANY/… apply to their tenant).
- Most restrictive wins: ``DENY`` > ``REQUIRE_APPROVAL`` > ``ALLOW``.
- On effect ties, highest priority wins; then the most specific scope.
- Lower levels can never weaken a higher one (a SYSTEM DENY always beats a
  COMPANY ALLOW).
- No matching rule ⇒ ``ALLOW`` (the safe default for an explicitly-authorized
  action; denial is enforced elsewhere first).
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models.security import (
    PolicyDecision as PolicyDecisionRow,
)
from app.db.models.security import (
    PolicyDecisionType,
    PolicyRule,
    PolicyScope,
)

logger = get_logger(__name__)

DecisionKind = Literal["allow", "deny", "require_approval"]

# More specific scope outranks broader scope on effect/priority ties.
_SCOPE_RANK = {
    PolicyScope.SYSTEM.value: 0,
    PolicyScope.COMPANY.value: 1,
    PolicyScope.DEPARTMENT.value: 2,
    PolicyScope.EMPLOYEE.value: 3,
    PolicyScope.AGENT.value: 4,
    PolicyScope.EXTERNAL.value: 5,
}


@dataclass
class PolicyDecision:
    decision: DecisionKind
    reason: str
    matched_rule_id: UUID | None = None
    matched_rule_scope: str | None = None
    risk_level: str = "low"


class PolicyEngine:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_rule(
        self,
        *,
        effect: str,
        action_pattern: str,
        scope: str,
        company_id: UUID | None = None,
        resource_type: str | None = None,
        subject_pattern: str = "*",
        conditions: dict | None = None,
        reason: str | None = None,
        priority: int = 0,
        risk_level: str = "low",
        created_by: UUID | None = None,
    ) -> PolicyRule:
        """Insert a policy rule (validated). ``conditions`` are advisory today."""
        if effect not in ("allow", "deny", "require_approval"):
            raise ValueError(f"Invalid policy effect {effect!r}.")
        if scope not in _SCOPE_RANK:
            raise ValueError(f"Invalid policy scope {scope!r}.")
        rule = PolicyRule(
            scope=scope,
            company_id=company_id,
            tenant_id=company_id,
            subject_pattern=subject_pattern,
            action_pattern=action_pattern,
            resource_pattern=resource_type or "*",
            effect=effect,
            risk_level=risk_level,
            priority=priority,
            reason=reason,
            enabled=True,
            created_by=created_by,
        )
        self.db.add(rule)
        self.db.flush()
        return rule

    def evaluate(
        self,
        *,
        identity_id: UUID | None,
        action: str,
        company_id: UUID | None = None,
        resource_type: str | None = None,
        context: dict | None = None,
        record: bool = True,
    ) -> PolicyDecision:
        """Resolve the effective decision for an action."""
        subject_kind = self._subject_kind(identity_id)
        rules = self._applicable_rules(action, subject_kind, company_id)
        # tuples (restrictive_rank, priority, scope_rank, rule)
        candidates: list[tuple[int, int, int, PolicyRule]] = []
        for rule in rules:
            effect_rank = {"deny": 3, "require_approval": 2, "allow": 1}.get(rule.effect, 0)
            scope_rank = _SCOPE_RANK.get(rule.scope, 0)
            candidates.append((effect_rank, rule.priority, scope_rank, rule))
        candidates.sort(key=lambda c: (c[0], c[1], c[2]), reverse=True)

        if not candidates:
            decision = PolicyDecision(decision="allow", reason="No policy rule matched.")
        else:
            _, _, _, rule = candidates[0]
            decision = PolicyDecision(
                decision=rule.effect,
                reason=rule.reason or f"Matched policy rule {rule.id}",
                matched_rule_id=rule.id,
                matched_rule_scope=rule.scope,
                risk_level=rule.risk_level,
            )
        if record:
            self._record(
                identity_id=identity_id,
                action=action,
                company_id=company_id,
                resource_type=resource_type,
                decision=decision,
            )
        return decision

    # ── rule collecting ────────────────────────────────────────────────────

    def _applicable_rules(
        self, action: str, subject_kind: str, company_id: UUID | None
    ) -> list[PolicyRule]:
        stmt = select(PolicyRule).where(PolicyRule.enabled.is_(True))
        rules = list(self.db.execute(stmt).scalars().all())
        out: list[PolicyRule] = []
        for rule in rules:
            if not fnmatch.fnmatchcase(action.lower(), rule.action_pattern.lower()):
                continue
            if rule.subject_pattern != "*" and not fnmatch.fnmatchcase(
                subject_kind, rule.subject_pattern
            ):
                continue
            # tenant scoping
            if rule.scope == PolicyScope.SYSTEM.value:
                out.append(rule)
            elif company_id is not None and (
                rule.company_id == company_id or rule.tenant_id == company_id
            ):
                out.append(rule)
        return out

    def _subject_kind(self, identity_id: UUID | None) -> str:
        if identity_id is None:
            return "system"
        from app.db.models.security import Identity

        identity = self.db.get(Identity, identity_id)
        return identity.kind if identity else "unknown"

    def _record(
        self,
        *,
        identity_id: UUID | None,
        action: str,
        company_id: UUID | None,
        resource_type: str | None,
        decision: PolicyDecision,
    ) -> None:
        row = PolicyDecisionRow(
            company_id=company_id,
            identity_id=identity_id,
            action=action,
            resource=resource_type,
            decision=PolicyDecisionType[decision.decision.upper()].value,
            reason=decision.reason,
            matched_rule_id=decision.matched_rule_id,
            matched_rule_scope=decision.matched_rule_scope,
            context_json={
                "evaluated_at": datetime.now(UTC).isoformat(),
                "risk_level": decision.risk_level,
            },
        )
        self.db.add(row)
        self.db.flush()
