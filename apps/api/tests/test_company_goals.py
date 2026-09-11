"""Tests for AI Company Layer — goals, cascade, progress, and tree."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.company.goals import GoalManager
from app.db.models.company import GoalScopeType, GoalStatusOrg


def _make_company(db: Session):
    from app.company.manager import CompanyManager

    return CompanyManager(db).create(name="Test Co")


def _make_dept(db: Session, company_id):
    from app.company.departments import DepartmentManager

    return DepartmentManager(db).create(company_id=company_id, name="Engineering")


class TestGoalCRUD:
    def test_create_company_goal(self, db: Session) -> None:
        company = _make_company(db)
        mgr = GoalManager(db)
        goal = mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Ship v2",
            priority=10,
            target="100",
        )
        assert goal.title == "Ship v2"
        assert goal.status == GoalStatusOrg.NOT_STARTED

    def test_create_with_progress(self, db: Session) -> None:
        company = _make_company(db)
        mgr = GoalManager(db)
        goal = mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Half done",
            progress=0.5,
        )
        assert goal.progress == 0.5
        assert goal.status == GoalStatusOrg.ACTIVE

    def test_create_completed_goal(self, db: Session) -> None:
        company = _make_company(db)
        mgr = GoalManager(db)
        goal = mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Done",
            progress=1.0,
        )
        assert goal.status == GoalStatusOrg.COMPLETED

    def test_list_goals(self, db: Session) -> None:
        company = _make_company(db)
        mgr = GoalManager(db)
        mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Goal 1",
        )
        mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Goal 2",
        )
        goals = mgr.list(company.id)
        assert len(goals) == 2


class TestGoalHierarchy:
    def test_parent_child_cascade(self, db: Session) -> None:
        company = _make_company(db)
        mgr = GoalManager(db)
        parent = mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Parent",
        )
        mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Child 1",
            parent_goal_id=parent.id,
            progress=0.5,
        )
        mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Child 2",
            parent_goal_id=parent.id,
            progress=0.8,
        )
        # Parent progress should be recomputed as mean of children
        parent_refreshed = mgr.get(parent.id)
        expected = round((0.5 + 0.8) / 2, 4)
        assert parent_refreshed.progress == expected
        assert parent_refreshed.status == GoalStatusOrg.ACTIVE

    def test_children(self, db: Session) -> None:
        company = _make_company(db)
        mgr = GoalManager(db)
        parent = mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Parent",
        )
        mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Child",
            parent_goal_id=parent.id,
        )
        kids = mgr.children(parent.id)
        assert len(kids) == 1
        assert kids[0].title == "Child"

    def test_parent_goal_not_found(self, db: Session) -> None:
        company = _make_company(db)
        mgr = GoalManager(db)
        with pytest.raises(ValueError, match="Parent goal not found"):
            mgr.create(
                company_id=company.id,
                scope_type=GoalScopeType.COMPANY,
                scope_id=company.id,
                title="Orphan",
                parent_goal_id=uuid4(),
            )

    def test_goal_tree(self, db: Session) -> None:
        company = _make_company(db)
        mgr = GoalManager(db)
        top = mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Top",
        )
        mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Sub",
            parent_goal_id=top.id,
        )
        tree = mgr.tree(company.id)
        assert len(tree) == 1
        assert tree[0]["goal"]["title"] == "Top"
        assert len(tree[0]["children"]) == 1


class TestGoalProgress:
    def test_update_progress(self, db: Session) -> None:
        company = _make_company(db)
        mgr = GoalManager(db)
        goal = mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Goal",
        )
        updated = mgr.update(goal.id, progress=0.75)
        assert updated.progress == 0.75
        assert updated.status == GoalStatusOrg.ACTIVE

    def test_progress_clamped(self, db: Session) -> None:
        company = _make_company(db)
        mgr = GoalManager(db)
        goal = mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Goal",
        )
        updated = mgr.update(goal.id, progress=1.5)
        assert updated.progress == 1.0
        assert updated.status == GoalStatusOrg.COMPLETED

    def test_completed_status_not_overwritten(self, db: Session) -> None:
        company = _make_company(db)
        mgr = GoalManager(db)
        goal = mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Goal",
            progress=1.0,
        )
        assert goal.status == GoalStatusOrg.COMPLETED
        # Updating with lower progress should not change status back
        updated = mgr.update(goal.id, progress=0.5)
        assert updated.status == GoalStatusOrg.COMPLETED


class TestGoalSerialization:
    def test_to_dict(self, db: Session) -> None:
        company = _make_company(db)
        mgr = GoalManager(db)
        goal = mgr.create(
            company_id=company.id,
            scope_type=GoalScopeType.COMPANY,
            scope_id=company.id,
            title="Ship v2",
        )
        d = mgr.to_dict(goal)
        assert d["title"] == "Ship v2"
        assert d["scope_type"] == "company"
        assert d["status"] == "not_started"
