"""AI Company Layer — goal endpoints (Phase 8)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.company.goals import GoalManager
from app.company.lifecycle import CompanyLifecycleError
from app.db.session import get_db
from app.schemas.company import GoalUpdate

router = APIRouter(tags=["goals"], prefix="/goals")


@router.get("/{goal_id}", response_model=dict, summary="Get a goal")
def get_goal(goal_id: UUID, db: Session = Depends(get_db)) -> dict:  # noqa: B008
    mgr = GoalManager(db)
    goal = mgr.get(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return mgr.to_dict(goal)


@router.put("/{goal_id}", response_model=dict, summary="Update a goal")
def update_goal(
    goal_id: UUID,
    payload: GoalUpdate,
    db: Session = Depends(get_db),  # noqa: B008
) -> dict:
    mgr = GoalManager(db)
    try:
        goal = mgr.update(goal_id, **payload.model_dump(exclude_unset=True))
        return mgr.to_dict(goal)
    except (CompanyLifecycleError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{goal_id}/progress", summary="Recompute and get goal progress")
def goal_progress(goal_id: UUID, db: Session = Depends(get_db)) -> dict:  # noqa: B008
    mgr = GoalManager(db)
    goal = mgr.get(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    mgr.recompute_progress(goal_id)
    return mgr.to_dict(goal)


@router.get("/{goal_id}/children", response_model=list[dict], summary="Child goals")
def goal_children(goal_id: UUID, db: Session = Depends(get_db)) -> list[dict]:  # noqa: B008
    mgr = GoalManager(db)
    goal = mgr.get(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return [mgr.to_dict(c) for c in mgr.children(goal_id)]


@router.get("/{goal_id}/tasks", summary="Tasks attached to a goal")
def goal_tasks(goal_id: UUID, db: Session = Depends(get_db)) -> list[dict]:  # noqa: B008
    mgr = GoalManager(db)
    goal = mgr.get(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return [_task_dict(t) for t in mgr.goal_tasks(goal_id)]


def _task_dict(task) -> dict:
    return {
        "id": str(task.id),
        "title": task.title,
        "description": task.description,
        "status": getattr(task.status, "value", task.status),
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }
