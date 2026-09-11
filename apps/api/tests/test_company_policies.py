"""Tests for AI Company Layer — policies and most-restrictive-wins resolution."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.company.policies import PolicyManager, PolicyResolver, most_restrictive
from app.db.models.company import PolicyScopeType


def _make_company(db: Session):
    from app.company.manager import CompanyManager

    return CompanyManager(db).create(name="Test Co")


# ── Policy CRUD ───────────────────────────────────────────────────────────────


class TestPolicyCRUD:
    def test_create_system_policy(self, db: Session) -> None:
        mgr = PolicyManager(db)
        policy = mgr.create(
            scope_type=PolicyScopeType.SYSTEM,
            company_id=None,
            scope_id=None,
            name="Global Default",
            key="require_approval",
            value=True,
        )
        assert policy.company_id is None
        assert policy.scope_type == PolicyScopeType.SYSTEM

    def test_create_company_policy(self, db: Session) -> None:
        company = _make_company(db)
        mgr = PolicyManager(db)
        policy = mgr.create(
            scope_type=PolicyScopeType.COMPANY,
            company_id=company.id,
            scope_id=None,
            name="Company Policy",
            key="max_tokens",
            value=4096,
        )
        assert policy.company_id == company.id

    def test_create_department_policy(self, db: Session) -> None:
        company = _make_company(db)
        dept_id = uuid4()
        mgr = PolicyManager(db)
        policy = mgr.create(
            scope_type=PolicyScopeType.DEPARTMENT,
            company_id=company.id,
            scope_id=dept_id,
            name="Dept Policy",
            key="max_tokens",
            value=2048,
        )
        assert policy.scope_id == dept_id

    def test_list_policies_includes_global(self, db: Session) -> None:
        company = _make_company(db)
        mgr = PolicyManager(db)
        mgr.create(
            scope_type=PolicyScopeType.SYSTEM,
            company_id=None,
            scope_id=None,
            name="Global",
            key="k1",
            value=True,
        )
        mgr.create(
            scope_type=PolicyScopeType.COMPANY,
            company_id=company.id,
            scope_id=None,
            name="Company",
            key="k2",
            value=100,
        )
        policies = mgr.list_(company.id)
        assert len(policies) == 2

    def test_delete_policy(self, db: Session) -> None:
        company = _make_company(db)
        mgr = PolicyManager(db)
        policy = mgr.create(
            scope_type=PolicyScopeType.COMPANY,
            company_id=company.id,
            scope_id=None,
            name="Temp",
            key="temp_key",
            value="temp",
        )
        assert mgr.delete(policy.id) is True
        assert mgr.get(policy.id) is None

    def test_to_dict(self, db: Session) -> None:
        mgr = PolicyManager(db)
        policy = mgr.create(
            scope_type=PolicyScopeType.SYSTEM,
            company_id=None,
            scope_id=None,
            name="Global",
            key="require_approval",
            value=True,
        )
        d = mgr.to_dict(policy)
        assert d["value"] is True
        assert d["scope_type"] == "system"


# ── Policy Resolution (most-restrictive-wins) ────────────────────────────────


class TestMostRestrictive:
    def test_boolean_true_wins(self) -> None:
        a = {"value": True, "scope": "system"}
        b = {"value": False, "scope": "company"}
        assert most_restrictive("require_approval", a, b)["value"] is True

    def test_boolean_false_wins_when_true_not_present(self) -> None:
        a = {"value": False, "scope": "system"}
        b = {"value": False, "scope": "company"}
        result = most_restrictive("require_approval", a, b)
        # Same value, narrower scope wins
        assert result["scope"] == "company"

    def test_numeric_limit_min_wins(self) -> None:
        a = {"value": 4096, "scope": "system"}
        b = {"value": 2048, "scope": "company"}
        result = most_restrictive("max_tokens", a, b)
        assert result["value"] == 2048  # min limit wins

    def test_numeric_limit_min_wins_reversed(self) -> None:
        a = {"value": 1024, "scope": "company"}
        b = {"value": 4096, "scope": "system"}
        result = most_restrictive("max_tokens", a, b)
        assert result["value"] == 1024  # min limit wins

    def test_numeric_threshold_max_wins(self) -> None:
        a = {"value": 0.7, "scope": "system"}
        b = {"value": 0.85, "scope": "company"}
        result = most_restrictive("verification_threshold", a, b)
        assert result["value"] == 0.85  # max threshold wins

    def test_narrower_scope_wins_default(self) -> None:
        a = {"value": "loose", "scope": "system"}
        b = {"value": "strict", "scope": "company"}
        result = most_restrictive("some_key", a, b)
        assert result["scope"] == "company"


class TestPolicyResolver:
    def test_effective_with_no_policies(self, db: Session) -> None:
        resolver = PolicyResolver(db)
        val = resolver.effective("nonexistent_key")
        assert val is None

    def test_effective_with_default(self, db: Session) -> None:
        resolver = PolicyResolver(db)
        val = resolver.effective("nonexistent_key", default="fallback")
        assert val == "fallback"

    def test_company_policy_wins_over_system(self, db: Session) -> None:
        company = _make_company(db)
        PolicyManager(db).create(
            scope_type=PolicyScopeType.SYSTEM,
            company_id=None,
            scope_id=None,
            name="Global",
            key="max_tokens",
            value=4096,
        )
        PolicyManager(db).create(
            scope_type=PolicyScopeType.COMPANY,
            company_id=company.id,
            scope_id=None,
            name="Company",
            key="max_tokens",
            value=2048,
        )
        resolver = PolicyResolver(db)
        val = resolver.effective("max_tokens", company_id=company.id)
        assert val == 2048  # More restrictive (lower limit)

    def test_department_policy_wins_over_company(self, db: Session) -> None:
        company = _make_company(db)
        dept_id = uuid4()
        PolicyManager(db).create(
            scope_type=PolicyScopeType.COMPANY,
            company_id=company.id,
            scope_id=None,
            name="Company",
            key="max_tokens",
            value=4096,
        )
        PolicyManager(db).create(
            scope_type=PolicyScopeType.DEPARTMENT,
            company_id=company.id,
            scope_id=dept_id,
            name="Dept",
            key="max_tokens",
            value=1024,
        )
        resolver = PolicyResolver(db)
        val = resolver.effective("max_tokens", company_id=company.id, department_id=dept_id)
        assert val == 1024  # Department narrower, lower limit

    def test_effective_detail_returns_source(self, db: Session) -> None:
        company = _make_company(db)
        PolicyManager(db).create(
            scope_type=PolicyScopeType.COMPANY,
            company_id=company.id,
            scope_id=None,
            name="C",
            key="k",
            value=42,
        )
        resolver = PolicyResolver(db)
        detail = resolver.effective_detail("k", company_id=company.id)
        assert detail["value"] == 42
        assert detail["source_scope"] == "company"
        assert "applicable_scopes" in detail

    def test_boolean_restriction_hierarchy(self, db: Session) -> None:
        """System: require_approval=False, Company: True → True wins (more restrictive)."""
        company = _make_company(db)
        PolicyManager(db).create(
            scope_type=PolicyScopeType.SYSTEM,
            company_id=None,
            scope_id=None,
            name="Global",
            key="require_approval",
            value=False,
        )
        PolicyManager(db).create(
            scope_type=PolicyScopeType.COMPANY,
            company_id=company.id,
            scope_id=None,
            name="Company",
            key="require_approval",
            value=True,
        )
        resolver = PolicyResolver(db)
        val = resolver.effective("require_approval", company_id=company.id)
        assert val is True

    def test_task_policies_override(self, db: Session) -> None:
        company = _make_company(db)
        PolicyManager(db).create(
            scope_type=PolicyScopeType.COMPANY,
            company_id=company.id,
            scope_id=None,
            name="C",
            key="max_tokens",
            value=4096,
        )
        resolver = PolicyResolver(db)
        val = resolver.effective(
            "max_tokens",
            company_id=company.id,
            task_policies={"max_tokens": 512},
        )
        assert val == 512  # Task is narrowest scope
