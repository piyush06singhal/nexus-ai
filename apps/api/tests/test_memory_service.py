"""Tests for the MemoryService CRUD + lifecycle (Phase 4)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.errors import NotFoundError
from app.db.models.memory import MemoryOwnerType, MemoryStatus, MemoryType
from app.schemas.memory import MemoryCreate, MemoryUpdate
from app.services.memory_service import MemoryService, to_dict


def _create(db, **overrides) -> MemoryService:
    svc = MemoryService(db)
    payload = MemoryCreate(
        namespace=overrides.pop("namespace", "default"),
        type=overrides.pop("type", MemoryType.SEMANTIC),
        content=overrides.pop("content", "Some fact"),
        importance=overrides.pop("importance", 0.6),
        **overrides,
    )
    memory = svc.create(payload)
    return svc, memory


def test_create_and_get(db):
    svc, memory = _create(db, content="Revenue grew 12%")
    fetched = svc.get(memory.id)
    assert fetched.id == memory.id
    assert fetched.content == "Revenue grew 12%"
    assert fetched.status == MemoryStatus.ACTIVE
    assert fetched.type == MemoryType.SEMANTIC
    assert fetched.access_count == 0


def test_update(db):
    svc, memory = _create(db)
    updated = svc.update(
        memory.id,
        MemoryUpdate(content="New content", importance=0.9),
    )
    assert updated.content == "New content"
    assert updated.importance == 0.9


def test_delete(db):
    svc, memory = _create(db)
    svc.delete(memory.id)
    with pytest.raises(NotFoundError):
        svc.get(memory.id)


def test_list_namespace_isolation(db):
    _create(db, namespace="teamA", content="A secret")
    _create(db, namespace="teamB", content="A secret")
    list_a, total_a = MemoryService(db).list(namespace="teamA")
    list_b, total_b = MemoryService(db).list(namespace="teamB")
    assert total_a == 1 and list_a[0].namespace == "teamA"
    assert total_b == 1 and list_b[0].namespace == "teamB"


def test_list_filters_by_type_and_status(db):
    _create(db, type=MemoryType.EPISODIC, content="ep")
    _create(db, type=MemoryType.SEMANTIC, content="sem")
    results, total = MemoryService(db).list(namespace="default", memory_type=MemoryType.EPISODIC)
    assert total == 1
    assert results[0].type == MemoryType.EPISODIC


def test_archive(db):
    svc, memory = _create(db)
    archived = svc.archive(memory.id)
    assert archived.status == MemoryStatus.ARCHIVED


def test_cleanup_expired_marks_expired(db):
    svc, memory = _create(
        db, type=MemoryType.WORKING, expires_at=datetime.now(UTC) - timedelta(hours=1)
    )
    count = svc.cleanup_expired()
    assert count == 1
    assert svc.get(memory.id).status == MemoryStatus.EXPIRED


def test_expire_working_owner(db):
    owner_id = uuid4()
    svc, working = _create(
        db,
        type=MemoryType.WORKING,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
        owner_type=MemoryOwnerType.AGENT,
        owner_id=owner_id,
    )
    count = svc.expire_working(owner_id=owner_id, namespace="default")
    assert count == 1
    assert svc.get(working.id).status == MemoryStatus.EXPIRED


def test_record_access_increments(db):
    svc, memory = _create(db)
    svc.record_access(memory.id)
    assert svc.get(memory.id).access_count == 1


def test_to_dict_round_trip(db):
    _, memory = _create(db, summary="short", content="fact")
    data = to_dict(memory)
    assert data["content"] == "fact"
    assert data["type"] == "semantic"
    assert data["summary"] == "short"


def test_owner_type_defaults_to_system(db):
    svc, memory = _create(db, content="system note")
    assert memory.owner_type == MemoryOwnerType.SYSTEM
    assert memory.owner_id is None
