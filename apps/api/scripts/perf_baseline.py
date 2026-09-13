"""NEXUS development-environment performance baseline.

Times core operations using the deterministic MockProvider on a file-backed
SQLite database. Results are **development-environment measurements**, not
production SLAs (§42). Repeat count is small; numbers are indicative only.

Run from ``apps/api``:
    .venv/bin/python -m scripts.perf_baseline
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

sys.path.insert(0, ".")

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

# Register all ORM models on Base.metadata before using create_all.
import app.db.models  # noqa: F401,E402
from app.ai.providers.mock_provider import MockProvider
from app.db.models.agent import AgentStatus
from app.db.models.memory import MemoryOwnerType, MemorySourceType, MemoryType
from app.db.models.workflow import WorkflowStepType
from app.db.session import Base
from app.phase12._types import SimVariableKind
from app.phase12.benchmarking import BenchmarkEngine
from app.phase12.engine import SimulationEngine
from app.phase12.optimization import Objective, OptimizationEngine, Variable
from app.phase12.variables import SimulationVariable
from app.runtime.runtime import AgentRuntime
from app.schemas.agent import AgentCreate
from app.schemas.memory import MemoryCreate, MemorySearchRequest
from app.schemas.task import TaskCreate
from app.schemas.workflow import WorkflowCreate, WorkflowStepCreate
from app.services.agent_service import AgentService
from app.services.execution_service import ExecutionService
from app.services.memory_service import MemoryService
from app.services.task_service import TaskService
from app.services.workflow_service import WorkflowService
from app.workflow.engine import WorkflowEngine

REPEATS = 3
TIMEOUT_SECONDS = 60

# ── File-backed SQLite setup ────────────────────────────────────────────────

DB_PATH = Path("perf_baseline.db")


def _make_session() -> Session:
    eng = create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(eng, "connect")
    def _set_wal(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        try:
            cur.execute("PRAGMA journal_mode=WAL")
        finally:
            cur.close()

    Base.metadata.create_all(eng)
    return Session(bind=eng, expire_on_commit=False)


# ── Helpers ─────────────────────────────────────────────────────────────────

GOOD_JSON = (
    '{"summary": "Analysis complete", "output": {"status": "done"}, '
    '"confidence": 0.9, "followup_actions": ["review"]}'
)

TOOL_CALL_JSON = json.dumps(
    {"tool_calls": [{"tool": "calculator", "arguments": {"expression": "2 + 3"}}]}
)
FINAL_JSON = json.dumps({"summary": "Computed 5", "output": {"result": 5}, "confidence": 0.99})


def _seed_agent(db: Session) -> tuple[Any, Any]:
    from app.db.models.company import Company as Co

    co = db.scalar(select(Co).limit(1))
    if co is None:
        from app.company.manager import CompanyManager

        co = CompanyManager(db).create(name="PerfBaseline", description="perf baseline co")
        db.commit()
    agent = AgentService(db).create(
        AgentCreate(
            name=f"perf-agent-{uuid4().hex[:6]}",
            status=AgentStatus.ACTIVE,
            provider="mock",
            model_name="mock-model",
        )
    )
    return agent, co


def _make_runtime(db: Session, provider=None, *, enable_tools=False):
    return AgentRuntime(
        agent_service=AgentService(db),
        task_service=TaskService(db),
        execution_service=ExecutionService(db),
        provider=provider or MockProvider(reply=GOOD_JSON),
        enable_tools=enable_tools,
        max_tool_iterations=5,
    )


def _bench(label: str, fn, *, repeats: int = REPEATS, timeout: float = TIMEOUT_SECONDS):
    """Run *fn* up to *repeats* times, report median ± stdev ms."""
    times: list[float] = []
    result = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        result = fn()
        elapsed = time.perf_counter() - t0
        times.append(elapsed * 1000)
    med = statistics.median(times)
    sd = statistics.stdev(times) if len(times) > 1 else 0.0
    short_label = label[:40].ljust(40)
    print(f"| {short_label} | {med:8.1f} ms | ± {sd:5.1f} ms |")
    return result


# ── Benchmark functions ─────────────────────────────────────────────────────


def bench_agent_execution(db: Session, agent) -> None:
    task = TaskService(db).create(TaskCreate(title="Perf task", input_data={"n": 1}))
    TaskService(db).assign(task.id, agent.id)
    rt = _make_runtime(db, MockProvider(reply=GOOD_JSON))
    rt.execute_task(task.id)


def bench_single_tool_call(db: Session, agent) -> None:
    task = TaskService(db).create(TaskCreate(title="Tool task", input_data={}))
    TaskService(db).assign(task.id, agent.id)
    # Scripted: first generate → tool request; second → final result.
    provider = MockProvider(
        script=[
            TOOL_CALL_JSON,
            FINAL_JSON,
        ],
    )
    rt = _make_runtime(db, provider, enable_tools=True)
    rt.execute_task(task.id)


def bench_workflow_run(db: Session, agent) -> None:
    svc = WorkflowService(db)
    wf = svc.create(WorkflowCreate(name=f"perf-wf-{uuid4().hex[:6]}"))
    svc.add_step(
        wf.id,
        WorkflowStepCreate(
            name="research",
            step_type=WorkflowStepType.AGENT_TASK,
            configuration={"agent_id": str(agent.id), "input_mapping": {}},
        ),
    )
    svc.activate(wf.id)
    execution = svc.create_execution(wf.id, trigger_type="manual", input_data={"topic": "perf"})
    WorkflowEngine(db).execute(execution.id)


def bench_memory_write_and_search(db: Session) -> None:
    svc = MemoryService(db)
    # Write 5 memories.
    ids = []
    for i in range(5):
        m = svc.create(
            MemoryCreate(
                namespace="perf-test",
                type=MemoryType.SEMANTIC,
                content=f"Performance test memory item {i} about alpha-{uuid4().hex[:4]}",
                owner_type=MemoryOwnerType.SYSTEM,
                owner_id=None,
                source_type=MemorySourceType.EXECUTION,
            )
        )
        ids.append(m.id)
    # Search (nearest-neighbor on content via embeddings; falls back to
    # content-match if no embedding provider is configured).
    asyncio.run(
        svc.search(
            MemorySearchRequest(
                query="alpha",
                namespace="perf-test",
                memory_types=[MemoryType.SEMANTIC],
                top_k=3,
            )
        )
    )


def bench_simulation_run(db: Session, company_id) -> None:
    eng = SimulationEngine(db, run_timeout_seconds=TIMEOUT_SECONDS)
    sim = eng.create(
        company_id=company_id,
        name=f"perf-sim-{uuid4().hex[:6]}",
        scenario_type="what_if",
        horizon_days=14,
        assumptions={"source": "perf baseline"},
    )
    eng.run(
        simulation_id=sim.id,
        iterations=1,
        seed="perf-base",
        variables=[
            SimulationVariable(
                name="headcount",
                kind=SimVariableKind.INTEGER,
                value=5,
                min_value=1,
                max_value=50,
            ),
        ],
    )


def bench_optimization_run(db: Session, company_id) -> None:
    eng = OptimizationEngine(db)
    problem = eng.create_problem(
        company_id=company_id,
        name=f"perf-opt-{uuid4().hex[:6]}",
        objectives=[Objective(metric="output", direction="maximize", weight=1.0)],
        variables=[Variable(name="budget", kind="float", low=0, high=1000)],
        constraints=None,
    )
    eng.run_problem(problem.id, strategy="greedy")


def bench_benchmark_run(db: Session, company_id) -> None:
    bench = BenchmarkEngine(db)
    bm = bench.create_benchmark(
        company_id=company_id,
        name=f"perf-bench-{uuid4().hex[:6]}",
        version="1.0",
        dimensions=["correctness", "latency"],
        cases=[
            {
                "name": f"bc-{i}",
                "input": {"query": f"test {i}"},
                "expected_output": {"answer": "ok"},
                "weight": 1.0,
            }
            for i in range(5)
        ],
    )
    bench.run_benchmark(bm.id, agent_id=uuid4(), agent_version="1.0", company_id=company_id)


def bench_marketplace_search(db: Session, company_id) -> None:
    from app.phase12.recommend import RecommendationEngine

    svc_eng = RecommendationEngine(db)
    svc_eng.recommend(
        company_id=company_id,
        task_type="research",
        skills=["web-search"],
        budget_limit=500.0,
        latency_limit_ms=1000.0,
        require_approval=False,
    )


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> int:
    print("NEXUS performance baseline (development-environment measurements, not SLAs — §42)\n")
    db = _make_session()

    try:
        # Seed a company + agent for the runtime and phase12 benchmarks.
        agent, company = _seed_agent(db)
        company_id = company.id

        print(f"| {'Operation':<40} | {'Median':>8}   | {'Std Dev':>8}   |")
        print(f"|{'-' * 42}|{'-' * 11}|{'-' * 11}|")

        _bench(
            "Agent execution (single task)",
            lambda: bench_agent_execution(db, agent),
        )
        _bench(
            "Single tool call (tool loop)",
            lambda: bench_single_tool_call(db, agent),
        )
        _bench(
            "Workflow run (1 agent step)",
            lambda: bench_workflow_run(db, agent),
        )
        _bench(
            "Memory write 5 + search",
            lambda: bench_memory_write_and_search(db),
        )
        _bench(
            "Simulation (14-day, 1 iter)",
            lambda: bench_simulation_run(db, company_id),
        )
        _bench(
            "Optimization (greedy, 1 var)",
            lambda: bench_optimization_run(db, company_id),
        )
        _bench(
            "Benchmark (5 cases)",
            lambda: bench_benchmark_run(db, company_id),
        )
        _bench(
            "Marketplace search",
            lambda: bench_marketplace_search(db, company_id),
        )

        print(
            "\nAll values are development-environment measurements on a "
            "file-backed SQLite database with the MockProvider. "
            "They are NOT production SLAs."
        )
        return 0

    finally:
        db.close()
        DB_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
