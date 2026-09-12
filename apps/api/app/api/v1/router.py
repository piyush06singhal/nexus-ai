"""Version 1 API router.

Aggregates all v1 endpoints under a single router, mounted in ``main.py``
with the configured prefix. Adding a v2 API later is additive: create a
``v2`` package and mount its router alongside this one.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    agents,
    alerts,
    autonomy,
    browser,
    companies,
    computer,
    decisions,
    departments,
    employee_templates,
    employees,
    escalations,
    evaluations,
    executions,
    external_actions,
    external_events,
    goals,
    health,
    integrations,
    memories,
    missions,
    orchestrations,
    products,
    recoveries,
    risks,
    roles,
    startup,
    startup_plans,
    startup_projects,
    tasks,
    tools,
    verifications,
    webhooks,
    workflows,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(agents.router)
api_router.include_router(tasks.router)
api_router.include_router(executions.router)
api_router.include_router(tools.router)
api_router.include_router(workflows.router)
api_router.include_router(memories.router)
api_router.include_router(orchestrations.router)
api_router.include_router(verifications.router)
api_router.include_router(recoveries.router)
api_router.include_router(escalations.router)
api_router.include_router(evaluations.router)
api_router.include_router(employees.router)
api_router.include_router(employee_templates.router)
# Phase 8 — AI Company Layer
api_router.include_router(companies.router)
api_router.include_router(departments.router)
api_router.include_router(goals.router)
api_router.include_router(decisions.router)
api_router.include_router(roles.router)
api_router.include_router(risks.router)
api_router.include_router(alerts.router)
# Phase 9 — Autonomous Startup Engine
api_router.include_router(missions.router)
api_router.include_router(startup_plans.router)
api_router.include_router(startup.router)
api_router.include_router(products.router)
api_router.include_router(startup_projects.router)
api_router.include_router(autonomy.router)
# Phase 10 — External Integrations & Computer Use
api_router.include_router(integrations.router)
api_router.include_router(external_actions.router)
api_router.include_router(browser.router)
api_router.include_router(computer.router)
api_router.include_router(external_events.router)
api_router.include_router(webhooks.router)
