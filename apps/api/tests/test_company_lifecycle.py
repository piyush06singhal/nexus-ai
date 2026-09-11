"""Tests for AI Company lifecycle state machine (Phase 8)."""

import pytest

from app.company.lifecycle import (
    CompanyLifecycleError,
    validate_company_transition,
)
from app.company.manager import CompanyManager
from app.db.models.company import CompanyStatus

# ── Pure state machine tests ──────────────────────────────────────────────────


def test_draft_can_activate():
    assert validate_company_transition(CompanyStatus.DRAFT, CompanyStatus.ACTIVE) is None


def test_draft_cannot_skip_to_paused():
    with pytest.raises(CompanyLifecycleError):
        validate_company_transition(CompanyStatus.DRAFT, CompanyStatus.PAUSED)


def test_active_can_pause_suspend_archive():
    for target in (
        CompanyStatus.PAUSED,
        CompanyStatus.SUSPENDED,
        CompanyStatus.ARCHIVED,
    ):
        assert validate_company_transition(CompanyStatus.ACTIVE, target) is None


def test_paused_can_activate_or_archive():
    assert validate_company_transition(CompanyStatus.PAUSED, CompanyStatus.ACTIVE) is None
    assert validate_company_transition(CompanyStatus.PAUSED, CompanyStatus.ARCHIVED) is None


def test_suspended_can_activate_or_archive():
    assert validate_company_transition(CompanyStatus.SUSPENDED, CompanyStatus.ACTIVE) is None
    assert validate_company_transition(CompanyStatus.SUSPENDED, CompanyStatus.ARCHIVED) is None


def test_archived_is_final():
    for target in (
        CompanyStatus.DRAFT,
        CompanyStatus.ACTIVE,
        CompanyStatus.PAUSED,
        CompanyStatus.SUSPENDED,
    ):
        with pytest.raises(CompanyLifecycleError):
            validate_company_transition(CompanyStatus.ARCHIVED, target)


# ── Manager integration tests ─────────────────────────────────────────────────


def test_full_lifecycle_cycle(db):
    mgr = CompanyManager(db)
    company = mgr.create(name="Acme Corp", industry="software")
    assert company.status == CompanyStatus.DRAFT

    mgr.activate(company.id)
    assert mgr.get(company.id).status == CompanyStatus.ACTIVE

    mgr.pause(company.id)
    assert mgr.get(company.id).status == CompanyStatus.PAUSED

    mgr.activate(company.id)
    assert mgr.get(company.id).status == CompanyStatus.ACTIVE

    mgr.archive(company.id)
    assert mgr.get(company.id).status == CompanyStatus.ARCHIVED


def test_invalid_transition_raises(db):
    mgr = CompanyManager(db)
    company = mgr.create(name="Beta Inc")
    # DRAFT → ARCHIVED is invalid per the state machine.
    with pytest.raises(CompanyLifecycleError):
        mgr.archive(company.id)


def test_archived_cannot_reactivate(db):
    mgr = CompanyManager(db)
    company = mgr.create(name="Gamma LLC")
    mgr.activate(company.id)
    mgr.pause(company.id)
    mgr.activate(company.id)
    mgr.archive(company.id)
    # Archived is final — reactivation must raise.
    with pytest.raises(CompanyLifecycleError):
        mgr.activate(company.id)


def test_create_and_get(db):
    mgr = CompanyManager(db)
    company = mgr.create(name="Delta Co", mission="Test")
    fetched = mgr.get(company.id)
    assert fetched.id == company.id
    assert fetched.name == "Delta Co"
    assert fetched.mission == "Test"


def test_list_companies(db):
    mgr = CompanyManager(db)
    mgr.create(name="First Co")
    mgr.create(name="Second Co")
    all_companies = mgr.list_()
    assert len(all_companies) >= 2
    names = {c.name for c in all_companies}
    assert "First Co" in names
    assert "Second Co" in names


def test_company_isolation(db):
    """Companies are isolated — membership/goals/budgets don't leak."""
    mgr = CompanyManager(db)
    c1 = mgr.create(name="Isolated A")
    c2 = mgr.create(name="Isolated B")

    # Add a department to c1
    mgr.create_department(company_id=c1.id, name="Dept A")
    depts_c1 = mgr.get_departments(c1.id)
    depts_c2 = mgr.get_departments(c2.id)
    assert len(depts_c1) == 1
    assert len(depts_c2) == 0
