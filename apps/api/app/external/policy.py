"""External policy resolution (Phase 10).

The effective permissions for an external action compose three layers with
*most-restrictive-wins* semantics — the same principle as Phase 8
``PolicyResolver``:

1. Phase 8 company/department/employee policies (via ``PolicyResolver.effective``).
2. Company ``integration_policies`` rows (capability patterns, require_approval,
   risk overrides, rate/budget limits, allowed domains).
3. Company ``domain_allowlists`` rules (ALLOW/BLOCK per domain).

No external action runs against this — the funnel consults the resolution
before any adapter executes, and nothing a provider returns can weaken a
resolution (Rule 1/2/5/6).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.company.policies import PolicyResolver
from app.core.config import settings
from app.db.models.external import (
    DomainAllowlist,
    DomainDecision,
    IntegrationCapability,
    IntegrationPolicy,
    RiskLevel,
)


@dataclass
class ExternalPolicyResolution:
    """Effective governance verdict for one external action."""

    allowed: bool = True
    require_approval: bool = False
    effective_risk: RiskLevel = RiskLevel.LOW
    reasons: list[str] = field(default_factory=list)
    rate_limit_per_minute: int = 0
    budget: dict[str, Any] = field(default_factory=dict)
    domain_allowed: bool = True
    blocked_domains: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "require_approval": self.require_approval,
            "effective_risk": self.effective_risk.value,
            "reasons": self.reasons,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "budget": self.budget,
            "domain_allowed": self.domain_allowed,
            "blocked_domains": self.blocked_domains,
        }


class ExternalPolicyResolver:
    """Resolve the effective external policy for an action."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._phase8 = PolicyResolver(db)

    # ── Public ─────────────────────────────────────────────────────────

    def resolve(
        self,
        *,
        company_id: UUID,
        integration_id: UUID,
        capability_name: str,
        risk_level: RiskLevel,
        payload: dict[str, Any] | None = None,
        capability_row: IntegrationCapability | None = None,
        employee_id: UUID | None = None,
        department_id: UUID | None = None,
        default_rate_limit: int | None = None,
    ) -> ExternalPolicyResolution:
        payload = payload or {}
        res = ExternalPolicyResolution(effective_risk=risk_level)
        res.rate_limit_per_minute = default_rate_limit or settings.external_rate_limit_per_minute

        # 1. Phase 8 company policies.
        ext_allowed = self._phase8.effective(
            "external_actions_allowed",
            company_id=company_id,
            department_id=department_id,
            employee_id=employee_id,
            default=True,
        )
        if ext_allowed is False:
            res.allowed = False
            res.reasons.append("Phase 8 policy external_actions_allowed=false")
        high_risk_approval = self._phase8.effective(
            "high_risk_actions_require_approval",
            company_id=company_id,
            department_id=department_id,
            employee_id=employee_id,
            default=True,
        )

        # 2. Integration policies (most-restrictive-wins).
        policies = self._matching_policies(company_id, integration_id, capability_name)
        for policy in policies:
            if policy.allowed is False:
                res.allowed = False
                res.reasons.append(f"policy {policy.id} sets allowed=false")
            if policy.require_approval:
                res.require_approval = True
                res.reasons.append(f"policy {policy.id} requires approval")
            if policy.risk_level_override is not None:
                res.effective_risk = RiskLevel(policy.risk_level_override.value)
                res.reasons.append(f"policy {policy.id} overrides risk")
            if policy.rate_limit and isinstance(policy.rate_limit, str):
                try:
                    rate = json.loads(policy.rate_limit).get("per_minute")
                    if rate:
                        res.rate_limit_per_minute = min(res.rate_limit_per_minute, int(rate))
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
            if policy.budget and isinstance(policy.budget, str):
                try:
                    budget = json.loads(policy.budget)
                    if budget:
                        res.budget = budget
                except json.JSONDecodeError:
                    pass

        # Integration policies with require_approval for this capability.
        if capability_row is not None and capability_row.approval_required:
            res.require_approval = True
            res.reasons.append("capability approval_required")

        # 3. High-risk gating (independent of autonomy defaults).
        if res.effective_risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            if bool(high_risk_approval) or settings.startup_require_approval_for_high_risk:
                res.require_approval = True
                res.reasons.append(f"risk {res.effective_risk.value} requires approval by policy")

        # 4. Domain rules for any outbound target in the payload.
        domains = _extract_domains(payload)
        if domains:
            for domain, allow in self._domain_decisions(company_id, integration_id, domains):
                if allow is False:
                    res.allowed = False
                    res.domain_allowed = False
                    res.blocked_domains.append(domain)
                    res.reasons.append(f"domain {domain} blocked by allowlist")

        if res.effective_risk.value != risk_level.value:
            res.reasons.append(
                f"policy escalated risk from {risk_level.value} to {res.effective_risk.value}"
            )
        return res

    # ── Internals ──────────────────────────────────────────────────────

    def _matching_policies(
        self, company_id: UUID, integration_id: UUID, capability_name: str
    ) -> list[IntegrationPolicy]:
        stmt = (
            select(IntegrationPolicy)
            .where(
                IntegrationPolicy.company_id == company_id,
                IntegrationPolicy.enabled.is_(True),
                (IntegrationPolicy.integration_id == integration_id)
                | (IntegrationPolicy.integration_id.is_(None)),
            )
            .order_by(IntegrationPolicy.created_at.asc())
        )
        rows = list(self._db.execute(stmt).scalars().all())
        matched: list[IntegrationPolicy] = []
        for row in rows:
            pattern = row.capability_pattern
            if not pattern or pattern == "*" or _pattern_match(capability_name, pattern):
                matched.append(row)
        return matched

    def _domain_decisions(
        self, company_id: UUID, integration_id: UUID, domains: list[str]
    ) -> list[tuple[str, bool]]:
        stmt = select(DomainAllowlist).where(
            DomainAllowlist.company_id == company_id,
            DomainAllowlist.enabled.is_(True),
            DomainAllowlist.domain.in_(domains),
        )
        rows = list(self._db.execute(stmt).scalars().all())
        # Most restrictive: any BLOCK for a domain wins over an ALLOW.
        decided: dict[str, bool] = {}
        for row in rows:
            if row.decision == DomainDecision.BLOCK:
                decided[row.domain] = False
            elif row.decision == DomainDecision.ALLOW:
                decided.setdefault(row.domain, True)
        return list(decided.items())


def _pattern_match(name: str, pattern: str) -> bool:
    """``*``-wildcard match: ``email.*`` matches ``email.search_messages``."""
    if pattern.endswith(".*"):
        return name.startswith(pattern[:-2])
    return name == pattern


def _extract_domains(payload: dict[str, Any]) -> list[str]:
    """Extract hostnames from url/domain/webhook-url fields in a payload."""
    import re
    from urllib.parse import urlparse

    domains: set[str] = set()
    for key in ("url", "target_url", "domain", "base_url", "redirect_url", "href"):
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            continue
        if re.match(r"^https?://", value, re.IGNORECASE):
            host = urlparse(value).hostname
            if host:
                domains.add(host.lower())
        elif re.match(r"^[a-z0-9\-\.]+\.[a-z]{2,}$", value, re.IGNORECASE):
            domains.add(value.lower())
    return sorted(domains)
