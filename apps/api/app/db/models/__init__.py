"""Database models package.

Import every model here so that SQLAlchemy's metadata and Alembic's
``target_metadata`` can discover all mapped tables.
"""

from app.db.models.agent import Agent, AgentStatus
from app.db.models.agent_tool_permission import AgentToolPermission
from app.db.models.execution import AgentExecution, ExecutionStatus
from app.db.models.task import Task, TaskStatus
from app.db.models.tool_call import ToolCallRecord, ToolCallStatus
from app.db.models.workflow import (
    IdempotencyTag,
    StepExecution,
    StepStatus,
    TriggerType,
    Workflow,
    WorkflowExecution,
    WorkflowExecutionStatus,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStepType,
    WorkflowTrigger,
)

__all__ = [
    "Agent",
    "AgentStatus",
    "AgentToolPermission",
    "Task",
    "TaskStatus",
    "AgentExecution",
    "ExecutionStatus",
    "ToolCallRecord",
    "ToolCallStatus",
    "Workflow",
    "WorkflowStatus",
    "WorkflowStep",
    "WorkflowStepType",
    "WorkflowTrigger",
    "TriggerType",
    "WorkflowExecution",
    "WorkflowExecutionStatus",
    "StepExecution",
    "StepStatus",
    "IdempotencyTag",
]
