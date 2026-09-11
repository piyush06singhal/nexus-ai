"""Tests for AI Company Layer — company/department memory namespace isolation."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models.memory import MemoryType


def _make_company(db: Session):
    from app.company.manager import CompanyManager

    return CompanyManager(db).create(name="Test Co")


class TestCompanyMemory:
    def test_store_and_list(self, db: Session) -> None:
        from app.company.memory import CompanyMemoryService

        company = _make_company(db)
        svc = CompanyMemoryService(db)
        svc.store_company_memory(
            company_id=company.id,
            memory_type=MemoryType.WORKING,
            content="Q4 strategy: expand into EU market",
            summary="EU expansion strategy",
        )
        memories = svc.list_company_memories(company.id)
        assert len(memories) >= 1
        assert any("EU market" in m["content"] for m in memories)

    def test_delete_company_memories(self, db: Session) -> None:
        from app.company.memory import CompanyMemoryService

        company = _make_company(db)
        svc = CompanyMemoryService(db)
        svc.store_company_memory(
            company_id=company.id,
            memory_type=MemoryType.WORKING,
            content="Some decision",
        )
        count = svc.delete_company_memories(company.id)
        assert count >= 1
        assert svc.list_company_memories(company.id) == []


class TestDepartmentMemory:
    def test_store_and_list(self, db: Session) -> None:
        from app.company.memory import CompanyMemoryService

        svc = CompanyMemoryService(db)
        dept_id = uuid4()
        svc.store_department_memory(
            department_id=dept_id,
            memory_type=MemoryType.WORKING,
            content="Sprint 42 retrospective: need better test coverage",
            summary="Sprint 42 retro",
        )
        memories = svc.list_department_memories(dept_id)
        assert len(memories) >= 1

    def test_company_and_dept_memories_are_isolated(self, db: Session) -> None:
        from app.company.memory import CompanyMemoryService

        company = _make_company(db)
        svc = CompanyMemoryService(db)
        svc.store_company_memory(
            company_id=company.id,
            memory_type=MemoryType.WORKING,
            content="Company-level decision",
        )
        dept_id = uuid4()
        svc.store_department_memory(
            department_id=dept_id,
            memory_type=MemoryType.WORKING,
            content="Dept-level decision",
        )
        company_memories = svc.list_company_memories(company.id)
        dept_memories = svc.list_department_memories(dept_id)
        assert len(company_memories) >= 1
        assert len(dept_memories) >= 1
        # Company memories should not contain dept content
        for m in company_memories:
            assert "Dept-level" not in m["content"]
