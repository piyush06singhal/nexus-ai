"""Workflow execution state.

Maintains the structured dict that flows through the engine during a
workflow run.  Each step reads from and writes to this state so steps
can wire their inputs from earlier steps' outputs without sharing
mutable objects.
"""

from __future__ import annotations

from typing import Any


class WorkflowState:
    """Structured workflow state container.

    Structure::

        {
            "input": {...},
            "steps": {
                "step_name": {
                    "output": {...},
                    "status": "completed"
                }
            }
        }
    """

    def __init__(self, input_data: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = {
            "input": input_data or {},
            "steps": {},
        }

    def set_step_output(self, step_name: str, output: dict[str, Any] | None) -> None:
        """Store the output produced by a step."""
        self._data["steps"].setdefault(step_name, {})
        self._data["steps"][step_name]["output"] = output or {}
        self._data["steps"][step_name]["status"] = "completed"

    def mark_step(self, step_name: str, status: str) -> None:
        """Mark a step's status without setting output."""
        self._data["steps"].setdefault(step_name, {})
        self._data["steps"][step_name]["status"] = status

    def get_step_output(self, step_name: str) -> dict[str, Any] | None:
        """Return the output dict of a completed step, or ``None``."""
        step = self._data["steps"].get(step_name)
        if step is None:
            return None
        return step.get("output")

    def get_step_status(self, step_name: str) -> str | None:
        """Return the status string for a step, or ``None``."""
        step = self._data["steps"].get(step_name)
        if step is None:
            return None
        return step.get("status")

    def is_step_completed(self, step_name: str) -> bool:
        """Check whether a step has completed successfully."""
        return self.get_step_status(step_name) == "completed"

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict snapshot of the state."""
        return dict(self._data)
