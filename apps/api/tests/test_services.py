"""Tests for the persistence service layer using an in-memory SQLite DB."""

from uuid import uuid4

import pytest

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.db.models.agent import AgentStatus
from app.schemas.agent import AgentCreate, AgentUpdate
from app.schemas.task import TaskCreate
from app.services.agent_service import AgentService
from app.services.task_service import TaskService


def test_agent_create_and_get(db):
    service = AgentService(db)
    agent = service.create(AgentCreate(name="researcher", role="researcher", provider="mock"))
    assert service.get(agent.id).name == "researcher"


def test_agent_unique_name_conflict(db):
    service = AgentService(db)
    service.create(AgentCreate(name="dup"))
    with pytest.raises(ConflictError):
        service.create(AgentCreate(name="dup"))


def test_agent_get_missing_raises_not_found(db):
    service = AgentService(db)
    with pytest.raises(NotFoundError):
        service.get(uuid4())


def test_agent_update_status(db):
    service = AgentService(db)
    agent = service.create(AgentCreate(name="a"))
    updated = service.update(agent.id, AgentUpdate(status=AgentStatus.ACTIVE))
    assert updated.status == AgentStatus.ACTIVE


def test_agent_list_filter_by_status(db):
    service = AgentService(db)
    service.create(AgentCreate(name="active1", status=AgentStatus.ACTIVE))
    service.create(AgentCreate(name="draft1", status=AgentStatus.DRAFT))
    actives = service.list(status=AgentStatus.ACTIVE)
    assert [a.name for a in actives] == ["active1"]


def test_agent_delete(db):
    service = AgentService(db)
    agent = service.create(AgentCreate(name="gone"))
    service.delete(agent.id)
    with pytest.raises(NotFoundError):
        service.get(agent.id)


def test_task_create_and_assign(db):
    agent = AgentService(db).create(AgentCreate(name="worker", status=AgentStatus.ACTIVE))
    tasks = TaskService(db)
    task = tasks.create(TaskCreate(title="Build report", input_data={"topic": "q1"}))
    assert task.status.value == "pending"
    assigned = tasks.assign(task.id, agent.id)
    assert assigned.assigned_agent_id == agent.id
    assert assigned.status.value == "queued"


def test_task_assign_completed_rejected(db):
    agent = AgentService(db).create(AgentCreate(name="worker2", status=AgentStatus.ACTIVE))
    tasks = TaskService(db)
    task = tasks.create(TaskCreate(title="Already done"))
    tasks.assign(task.id, agent.id)
    tasks.mark_completed(task.id)
    with pytest.raises(ValidationError):
        tasks.assign(task.id, agent.id)


def test_task_lifecycle_transitions(db):
    agent = AgentService(db).create(AgentCreate(name="worker3", status=AgentStatus.ACTIVE))
    tasks = TaskService(db)
    task = tasks.create(TaskCreate(title="Transitions"))
    tasks.assign(task.id, agent.id)
    tasks.mark_in_progress(task.id)
    assert task.status.value == "in_progress"
    tasks.mark_completed(task.id)
    assert task.status.value == "completed"
    assert task.executed_at is not None


def test_task_get_missing_raises(db):
    tasks = TaskService(db)
    with pytest.raises(NotFoundError):
        tasks.get(uuid4())
