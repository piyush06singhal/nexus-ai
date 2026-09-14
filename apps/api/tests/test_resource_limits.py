"""Tests for per-tenant resource limit provisioning from config defaults."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.models.security import ResourceCategory, ResourceLimit, ResourceLimitScope
from app.db.session import Base
from app.security.resources import ResourceGovernanceService


def _setup_db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(bind=engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Provisioning
# ---------------------------------------------------------------------------


class TestProvisionDefaultLimits:
    """ResourceGovernanceService.provision_default_limits"""

    def test_provisions_global_rows(self):
        db = _setup_db()
        svc = ResourceGovernanceService(db)
        created = svc.provision_default_limits()
        db.commit()
        # 5 core categories + 8 Phase 12 categories = 13 global rows.
        assert len(created) == 13

        for lim in created:
            assert lim.scope == ResourceLimitScope.GLOBAL.value
            assert lim.tenant_id is None
            assert lim.period == "per_day"
            assert lim.enforced is True
            assert lim.max_value > 0
        db.close()

    def test_provisions_per_company_rows(self):
        db = _setup_db()
        c1 = uuid4()
        c2 = uuid4()
        created = ResourceGovernanceService(db).provision_default_limits(company_ids=[c1, c2])
        db.commit()
        # 13 GLOBAL rows + 13 categories × 2 companies = 39 rows returned.
        assert len(created) == 39
        company_rows = [lim for lim in created if lim.tenant_id is not None]
        assert len(company_rows) == 26
        tenants = {lim.tenant_id for lim in company_rows}
        assert tenants == {c1, c2}
        for lim in company_rows:
            assert lim.scope == ResourceLimitScope.COMPANY.value
        db.close()

    def test_idempotent_on_re_run(self):
        db = _setup_db()
        svc = ResourceGovernanceService(db)
        svc.provision_default_limits()
        db.commit()
        svc.provision_default_limits()
        db.commit()
        total = db.query(ResourceLimit).count()
        # Only 13 rows (one per category) — re-run updated existing rows.
        assert total == 13
        db.close()

    def test_values_match_config_defaults(self):
        db = _setup_db()
        created = ResourceGovernanceService(db).provision_default_limits()
        db.commit()
        by_cat = {lim.category: lim.max_value for lim in created}
        assert by_cat[ResourceCategory.TOKENS.value] == float(settings.resource_max_tokens_default)
        assert by_cat[ResourceCategory.COST.value] == settings.resource_max_cost_default
        assert by_cat[ResourceCategory.TOOL_CALLS.value] == float(
            settings.resource_max_tool_calls_default
        )
        assert by_cat[ResourceCategory.ITERATIONS.value] == float(
            settings.resource_max_iterations_default
        )
        assert by_cat[ResourceCategory.DURATION_SECONDS.value] == float(
            settings.resource_max_duration_seconds_default
        )
        # Each Phase 12 category (sim_runs/optimization_candidates/…) is seeded at
        # the shared resource_max_phase12_default.
        from app.phase12.governance import PHASE12_CATEGORIES

        assert len(PHASE12_CATEGORIES) == 8
        for category in PHASE12_CATEGORIES:
            assert by_cat[category] == settings.resource_max_phase12_default
        db.close()


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------


class TestResourceLimitsConfig:
    def test_resource_limits_provision_flag_default_off(self):
        """The flag defaults to False — off-by-default preserves dev/test behavior."""
        # In the test CI the flag is unset/False; this test also protects against
        # accidental change to True as the default.
        assert settings.resource_limits_provision is False

    def test_resource_max_defaults_are_positive(self):
        assert settings.resource_max_tokens_default > 0
        assert settings.resource_max_cost_default > 0
        assert settings.resource_max_tool_calls_default > 0
        assert settings.resource_max_iterations_default > 0
        assert settings.resource_max_duration_seconds_default > 0
        assert settings.resource_max_phase12_default > 0


# ---------------------------------------------------------------------------
# Readiness check
# ---------------------------------------------------------------------------


class TestReadinessResourceLimits:
    def test_readiness_warns_when_provision_off(self):
        """When RESOURCE_LIMITS_PROVISION is not set the readiness check WARNs."""
        from app.checks.production_readiness import ProductionReadiness

        check = ProductionReadiness()
        results = {r.name: r for r in check.run_all()}
        rl = results.get("resource_limits")
        assert rl is not None
        assert rl.status == "WARN"
        assert "not provisioned" in rl.message.lower()

    def test_readiness_passes_when_provision_on(self, monkeypatch):
        """With RESOURCE_LIMITS_PROVISION=true both resource checks PASS."""
        from app.checks.production_readiness import ProductionReadiness

        monkeypatch.setattr(settings, "resource_limits_provision", True)
        check = ProductionReadiness()
        results = {r.name: r for r in check.run_all()}
        assert results["resource_limits"].status == "PASS"
        assert results["phase12_resource_limits"].status == "PASS"
