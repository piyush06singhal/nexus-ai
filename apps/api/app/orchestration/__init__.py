"""Multi-agent orchestration layer (Phase 5).

Coordinates multiple specialized agents toward a shared objective by reusing
the existing Agent Runtime, Tool Executor, Workflow engine, and Memory —
without duplicating any of them. See :mod:`app.orchestration.orchestrator` for
the engine and :mod:`app.orchestration.planner`, :mod:`app.orchestration.selector`,
:mod:`app.orchestration.bus`, etc. for the pluggable components.

Layering: ``API → orchestration_service → orchestrator (engine) → Agent Runtime
→ Tool Executor + Memory``.
"""

from app.orchestration.bus import AgentMessageBus
from app.orchestration.conflicts import ConflictDetector, NumericConflictDetector
from app.orchestration.context import build_assignment_context, upsert_shared_context
from app.orchestration.messages import AgentMessagePayload, AgentMessageType
from app.orchestration.orchestrator import Orchestrator, OrchestratorError
from app.orchestration.planner import DeterministicPlanner, Planner, validate_plan
from app.orchestration.policies import OrchestrationLimits
from app.orchestration.review import AgentReviewService, ReviewPolicy
from app.orchestration.selector import AgentSelector, CapabilityAgentSelector
from app.orchestration.state_machine import (
    transition_assignment,
    transition_orchestration,
    transition_task,
)
from app.orchestration.synthesizer import ResultSynthesizer
from app.orchestration.types import (
    AgentSelection,
    Conflict,
    ExecutionPlan,
    OrchestrationError,
    PlanTask,
)

__all__ = [
    "AgentMessageBus",
    "AgentMessagePayload",
    "AgentMessageType",
    "AgentReviewService",
    "AgentSelection",
    "AgentSelector",
    "CapabilityAgentSelector",
    "Conflict",
    "ConflictDetector",
    "DeterministicPlanner",
    "ExecutionPlan",
    "NumericConflictDetector",
    "OrchestrationError",
    "OrchestrationLimits",
    "Orchestrator",
    "OrchestratorError",
    "PlanTask",
    "Planner",
    "ResultSynthesizer",
    "ReviewPolicy",
    "build_assignment_context",
    "transition_assignment",
    "transition_orchestration",
    "transition_task",
    "upsert_shared_context",
    "validate_plan",
]
