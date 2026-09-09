"""Tests for workflow step-graph validation.

Pure-logic tests that construct ``WorkflowStep`` objects via the service
layer against an in-memory DB, then run the validator.
"""

import json
from uuid import uuid4

import pytest

from app.db.models.workflow import IdempotencyTag, WorkflowStep, WorkflowStepType
from app.schemas.workflow import WorkflowStepCreate
from app.workflow.validator import validate_workflow_steps


def _raw_step(name, *, step_type="delay", deps=None, configuration=None):
    """Construct a bare WorkflowStep without DB persistence.

    The validator only reads attributes, so a lightweight stub sidesteps the
    service's unique-name enforcement (useful for duplicate-name tests).
    """
    return WorkflowStep(
        id=uuid4(),
        workflow_id=uuid4(),
        name=name,
        step_type=step_type,
        configuration=json.dumps(configuration) if configuration else None,
        dependencies=json.dumps(deps) if deps else None,
        order=0,
        idempotency=IdempotencyTag.NON_IDEMPOTENT,
    )


def _make_agent_step(service, workflow_id, name, deps=None, agent_id="agent-1"):
    return service.add_step(
        workflow_id,
        WorkflowStepCreate(
            name=name,
            step_type=WorkflowStepType.AGENT_TASK,
            dependencies=deps or None,
            configuration={"agent_id": agent_id, "input_mapping": {}},
        ),
    )


def _make_tool_step(service, workflow_id, name, deps=None, tool="calculator"):
    return service.add_step(
        workflow_id,
        WorkflowStepCreate(
            name=name,
            step_type=WorkflowStepType.TOOL_ACTION,
            dependencies=deps or None,
            configuration={"tool_name": tool, "arguments": {"expression": "1+1"}},
        ),
    )


def _make_condition_step(service, workflow_id, name, deps=None):
    return service.add_step(
        workflow_id,
        WorkflowStepCreate(
            name=name,
            step_type=WorkflowStepType.CONDITION,
            dependencies=deps or None,
            configuration={"condition": {"field": "input.x", "op": "gt", "value": 1}},
        ),
    )


def _make_delay_step(service, workflow_id, name, deps=None):
    return service.add_step(
        workflow_id,
        WorkflowStepCreate(
            name=name,
            step_type=WorkflowStepType.DELAY,
            dependencies=deps or None,
            configuration={"duration": 0},
        ),
    )


@pytest.fixture
def svc_and_wf(db):
    from app.schemas.workflow import WorkflowCreate
    from app.services.workflow_service import WorkflowService

    svc = WorkflowService(db)
    wf = svc.create(WorkflowCreate(name="validation-wf"))
    return svc, wf


class TestValidation:
    def test_valid_chain_validates_clean(self, svc_and_wf):
        svc, wf = svc_and_wf
        steps = [
            _make_agent_step(svc, wf.id, "a"),
            _make_condition_step(svc, wf.id, "b", deps=["a"]),
            _make_tool_step(svc, wf.id, "c", deps=["b"]),
        ]
        result = validate_workflow_steps(steps)
        assert result.valid
        assert result.errors == []

    def test_missing_dependency_reference_is_error(self, svc_and_wf):
        svc, wf = svc_and_wf
        steps = [_make_agent_step(svc, wf.id, "a", deps=["nonexistent_step"])]
        result = validate_workflow_steps(steps)
        assert not result.valid
        assert any("unknown dependency" in e for e in result.errors)

    def test_circular_dependency_is_error(self, svc_and_wf):
        steps = [
            _raw_step("a", deps=["b"]),
            _raw_step("b", deps=["a"]),
        ]
        result = validate_workflow_steps(steps)
        assert not result.valid
        assert any("circular" in e.lower() for e in result.errors)

    def test_duplicate_step_name_is_error(self, svc_and_wf):
        steps = [
            _raw_step("a"),
            _raw_step("a"),
        ]
        result = validate_workflow_steps(steps)
        assert not result.valid
        assert any("duplicate" in e.lower() for e in result.errors)

    def test_missing_agent_id_is_error(self, svc_and_wf):
        svc, wf = svc_and_wf
        step = svc.add_step(
            wf.id,
            WorkflowStepCreate(
                name="a",
                step_type=WorkflowStepType.AGENT_TASK,
                configuration={},  # no agent_id
            ),
        )
        result = validate_workflow_steps([step])
        assert not result.valid
        assert any("agent_id" in e for e in result.errors)

    def test_unknown_tool_is_error(self, svc_and_wf):
        svc, wf = svc_and_wf
        step = svc.add_step(
            wf.id,
            WorkflowStepCreate(
                name="a",
                step_type=WorkflowStepType.TOOL_ACTION,
                configuration={"tool_name": "definitely_not_a_real_tool"},
            ),
        )
        result = validate_workflow_steps([step])
        assert not result.valid
        assert any("unknown tool" in e for e in result.errors)

    def test_empty_workflow_is_warning_not_error(self, svc_and_wf):
        result = validate_workflow_steps([])
        assert result.valid
        assert any("no steps" in w.lower() for w in result.warnings)

    def test_delay_step_without_duration_is_error(self, svc_and_wf):
        svc, wf = svc_and_wf
        step = svc.add_step(
            wf.id,
            WorkflowStepCreate(
                name="d",
                step_type=WorkflowStepType.DELAY,
                configuration={},  # no duration
            ),
        )
        result = validate_workflow_steps([step])
        assert not result.valid
        assert any("duration" in e for e in result.errors)

    def test_condition_step_without_condition_is_error(self, svc_and_wf):
        svc, wf = svc_and_wf
        step = svc.add_step(
            wf.id,
            WorkflowStepCreate(
                name="c",
                step_type=WorkflowStepType.CONDITION,
                configuration={},  # no condition
            ),
        )
        result = validate_workflow_steps([step])
        assert not result.valid
        assert any("condition" in e for e in result.errors)

    def test_invalid_retry_policy_warns_for_side_effecting(self, svc_and_wf):
        svc, wf = svc_and_wf
        step = svc.add_step(
            wf.id,
            WorkflowStepCreate(
                name="a",
                step_type=WorkflowStepType.TOOL_ACTION,
                configuration={"tool_name": "calculator"},
                retry_policy={"max_attempts": 5},
                idempotency=IdempotencyTag.SIDE_EFFECTING,
            ),
        )
        result = validate_workflow_steps([step])
        assert result.valid
        assert any("unsafe" in w.lower() for w in result.warnings)
