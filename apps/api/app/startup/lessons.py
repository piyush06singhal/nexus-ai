"""Lessons — distilled learnings mirrored into the Phase 4 memory system.

:class:`LessonRecorder` writes a ``startup_lessons`` row for every real outcome
(decision outcomes, failed assumptions, success patterns, process improvements,
strategic insights) and mirrors it into the company memory namespace via
:class:`CompanyMemoryService` — single source, two views. Lessons are reflective:
they change *future* planning, never the codebase or the current artifacts.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.company.memory import CompanyMemoryService
from app.db.models.memory import MemoryType
from app.db.models.startup import LessonType, StartupLesson
from app.startup.events import StartupEventLogger, StartupEvents


class LessonRecorder:
    """Record lessons and mirror them into company memory."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._events = StartupEventLogger(db)
        self._memory = CompanyMemoryService(db)

    def record(
        self,
        *,
        company_id: UUID,
        lesson_type: LessonType | str,
        title: str,
        content: str,
        mission_id: UUID | None = None,
        source: dict[str, Any] | None = None,
    ) -> StartupLesson:
        row = StartupLesson(
            company_id=company_id,
            mission_id=mission_id,
            lesson_type=LessonType(lesson_type),
            title=title,
            content=content,
            source=__import__("json").dumps(source, default=str) if source else None,
        )
        self._db.add(row)
        self._db.commit()
        # Mirror to Phase 4 memory (company namespace) — same learning, 2 views.
        self._memory.store_company_memory(
            company_id=company_id,
            memory_type=MemoryType.EPISODIC,
            content=content,
            summary=f"[{LessonType(row.lesson_type).value}] {title}",
            metadata_json={
                "kind": "startup_lesson",
                "lesson_type": LessonType(row.lesson_type).value,
                "mission_id": str(mission_id) if mission_id else None,
                "startup_lesson_id": str(row.id),
            },
        )
        self._events.log(
            action=StartupEvents.LESSON_RECORDED,
            company_id=company_id,
            target_type="startup_lesson",
            target_id=row.id,
            details={
                "lesson_type": LessonType(row.lesson_type).value,
                "title": title,
                "mission_id": str(mission_id) if mission_id else None,
            },
            outcome="success",
        )
        return row

    def record_recovery(
        self,
        *,
        company_id: UUID,
        execution_id: UUID,
        outcome: str,
        attempts: int,
        mission_id: UUID | None = None,
    ) -> StartupLesson | None:
        """Capture a recovery outcome as a lesson when it was non-trivial.

        A first-attempt recovery is normal operation; retries and fallbacks are
        worth learning from because they reveal design or execution gaps.
        """
        if attempts <= 1 and outcome == "recovered":
            return None
        title = (
            "Execution recovered via retry"
            if outcome == "recovered"
            else "Execution required escalation"
        )
        return self.record(
            company_id=company_id,
            lesson_type=LessonType.PROCESS_IMPROVEMENT,
            title=title,
            content=(
                f"Execution {execution_id} {outcome} after {attempts} recovery "
                f"attempt(s); revisit how this work is decomposed and verified."
            ),
            mission_id=mission_id,
            source={"execution_id": str(execution_id), "attempts": attempts},
        )

    def list_(
        self,
        company_id: UUID,
        *,
        lesson_type: LessonType | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(StartupLesson)
            .where(StartupLesson.company_id == company_id)
            .order_by(StartupLesson.created_at.desc())
            .limit(limit)
        )
        if lesson_type is not None:
            stmt = stmt.where(StartupLesson.lesson_type == lesson_type)
        return [_lesson_to_dict(r) for r in self._db.execute(stmt).scalars().all()]


def _lesson_to_dict(row: StartupLesson) -> dict[str, Any]:
    import json

    def _loads(raw: str | None) -> Any:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    return {
        "id": str(row.id),
        "company_id": str(row.company_id),
        "mission_id": str(row.mission_id) if row.mission_id else None,
        "lesson_type": row.lesson_type.value,
        "title": row.title,
        "content": row.content,
        "source": _loads(row.source),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
