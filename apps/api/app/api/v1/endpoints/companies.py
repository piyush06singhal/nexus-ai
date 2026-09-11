"""AI Company Layer — company endpoints (Phase 8).

CRUD + lifecycle for companies plus the aggregate read endpoints that compose
the executive dashboard: departments, employees, org chart, goals, KPIs,
budgets, performance, reports, risks, alerts, decisions, analytics, health,
timeline, policies, memberships, and roles. All data comes from real service
methods backed by authoritative tables — no mock dashboard numbers.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.company.lifecycle import CompanyLifecycleError
from app.company.manager import CompanyManager
from app.company.reports import ReportGenerator
from app.db.models.company import Company
from app.db.session import get_db
from app.schemas.company import (
    CompanyCreate,
    CompanyRead,
    CompanyUpdate,
    DepartmentCreate,
    DepartmentRead,
    EffectivePolicy,
    GoalCreate,
    GoalRead,
    KpiCreate,
    KpiRead,
    MembershipCreate,
    MembershipRead,
    MembershipUpdate,
    OrgChartNodeRead,
    OrgEventRead,
    PolicyCreate,
    PolicyRead,
    RiskCreate,
    RiskRead,
)

router = APIRouter(tags=["companies"], prefix="/companies")


def _company_or_404(db: Session, company_id: UUID) -> Company:
    mgr = CompanyManager(db)
    company = mgr.get(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def _lifecycle_error(exc: Exception) -> HTTPException:
    if isinstance(exc, CompanyLifecycleError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


# ── CRUD ────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=CompanyRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a company",
)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> CompanyRead:
    mgr = CompanyManager(db)
    try:
        company = mgr.create(
            name=payload.name,
            description=payload.description,
            mission=payload.mission,
            vision=payload.vision,
            industry=payload.industry,
            timezone=payload.timezone,
            currency=payload.currency,
        )
        return CompanyManager(db).to_read(company)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("", response_model=list[CompanyRead], summary="List companies")
def list_companies(db: Session = Depends(get_db)) -> list[CompanyRead]:  # noqa: B008
    mgr = CompanyManager(db)
    return [mgr.to_read(c) for c in mgr.list_()]


@router.get("/{company_id}", response_model=CompanyRead, summary="Get a company")
def get_company(
    company_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> CompanyRead:
    company = _company_or_404(db, company_id)
    return CompanyManager(db).to_read(company)


@router.put("/{company_id}", response_model=CompanyRead, summary="Update a company")
def update_company(
    company_id: UUID,
    payload: CompanyUpdate,
    db: Session = Depends(get_db),  # noqa: B008
) -> CompanyRead:
    mgr = CompanyManager(db)
    try:
        company = mgr.update(
            company_id,
            **payload.model_dump(exclude_unset=True),
        )
        return mgr.to_read(company)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ── Lifecycle ───────────────────────────────────────────────────────────


@router.post("/{company_id}/activate", response_model=CompanyRead, summary="Activate a company")
def activate_company(
    company_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> CompanyRead:
    mgr = CompanyManager(db)
    try:
        return mgr.to_read(mgr.activate(company_id))
    except Exception as e:  # noqa: BLE001 - lifecycle/validation
        raise _lifecycle_error(e) from e


@router.post("/{company_id}/pause", response_model=CompanyRead, summary="Pause a company")
def pause_company(
    company_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> CompanyRead:
    mgr = CompanyManager(db)
    try:
        return mgr.to_read(mgr.pause(company_id))
    except Exception as e:  # noqa: BLE001
        raise _lifecycle_error(e) from e


@router.post("/{company_id}/archive", response_model=CompanyRead, summary="Archive a company")
def archive_company(
    company_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> CompanyRead:
    mgr = CompanyManager(db)
    try:
        return mgr.to_read(mgr.archive(company_id))
    except Exception as e:  # noqa: BLE001
        raise _lifecycle_error(e) from e


# ── Departments ─────────────────────────────────────────────────────────


@router.post(
    "/{company_id}/departments",
    response_model=DepartmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a department in a company",
)
def create_department(
    company_id: UUID,
    payload: DepartmentCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> DepartmentRead:
    mgr = CompanyManager(db)
    try:
        dept = mgr.create_department(
            company_id=company_id,
            name=payload.name,
            description=payload.description,
            mission=payload.mission,
            manager_id=payload.manager_id,
            parent_department_id=payload.parent_department_id,
        )
        return mgr.to_dept_read(dept)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get(
    "/{company_id}/departments",
    response_model=list[DepartmentRead],
    summary="List departments in a company",
)
def list_departments(
    company_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[DepartmentRead]:
    _company_or_404(db, company_id)
    mgr = CompanyManager(db)
    return [mgr.to_dept_read(d) for d in mgr.get_departments(company_id)]


# ── Employees / memberships ────────────────────────────────────────────


@router.get(
    "/{company_id}/employees",
    summary="List all employees in a company",
)
def company_employees(
    company_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[dict]:
    _company_or_404(db, company_id)
    return CompanyManager(db).company_employees(company_id)


@router.get(
    "/{company_id}/memberships",
    response_model=list[MembershipRead],
    summary="List employee memberships in a company",
)
def list_memberships(
    company_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[MembershipRead]:
    _company_or_404(db, company_id)
    mgr = CompanyManager(db)
    return mgr.get_memberships(company_id)


@router.post(
    "/{company_id}/memberships",
    response_model=MembershipRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add an employee to a company",
)
def add_membership(
    company_id: UUID,
    payload: MembershipCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> MembershipRead:
    mgr = CompanyManager(db)
    try:
        return mgr.add_membership(
            company_id=company_id,
            employee_id=payload.employee_id,
            department_id=payload.department_id,
            role_id=payload.role_id,
            manager_id=payload.manager_id,
            responsibility=payload.responsibility,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.put(
    "/{company_id}/memberships/{membership_id}",
    response_model=MembershipRead,
    summary="Update a membership (department/role/manager/responsibility)",
)
def update_membership(
    company_id: UUID,
    membership_id: UUID,
    payload: MembershipUpdate,
    db: Session = Depends(get_db),  # noqa: B008
) -> MembershipRead:
    mgr = CompanyManager(db)
    try:
        return mgr.update_membership(
            membership_id,
            department_id=payload.department_id,
            role_id=payload.role_id,
            manager_id=payload.manager_id,
            responsibility=payload.responsibility,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete(
    "/{company_id}/memberships/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an employee from a company",
)
def remove_membership(
    company_id: UUID,
    membership_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> None:
    mgr = CompanyManager(db)
    try:
        mgr.remove_membership(membership_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get(
    "/{company_id}/organization-chart",
    response_model=OrgChartNodeRead,
    summary="Get the company organization chart",
)
def organization_chart(
    company_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> OrgChartNodeRead:
    _company_or_404(db, company_id)
    return CompanyManager(db).organization_chart(company_id)


# ── Goals ───────────────────────────────────────────────────────────────


@router.get(
    "/{company_id}/goals/tree",
    summary="Get the company goal tree",
)
def company_goal_tree(
    company_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[dict]:
    _company_or_404(db, company_id)
    return CompanyManager(db).goal_tree(company_id)


@router.get(
    "/{company_id}/goals",
    response_model=list[GoalRead],
    summary="List company goals",
)
def company_goals(
    company_id: UUID,
    scope_type: str | None = Query(default=None),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[GoalRead]:
    _company_or_404(db, company_id)
    return CompanyManager(db).get_goals(company_id, scope_type=scope_type)


@router.post(
    "/{company_id}/goals",
    response_model=GoalRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a company/department goal",
)
def create_goal(
    company_id: UUID,
    payload: GoalCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> GoalRead:
    mgr = CompanyManager(db)
    try:
        return mgr.create_goal(company_id=company_id, **payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ── KPIs ────────────────────────────────────────────────────────────────


@router.get("/{company_id}/kpis", response_model=list[KpiRead], summary="List company KPIs")
def company_kpis(
    company_id: UUID,
    scope_type: str | None = Query(default=None),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[KpiRead]:
    _company_or_404(db, company_id)
    return CompanyManager(db).get_kpis(company_id, scope_type=scope_type)


@router.post(
    "/{company_id}/kpis",
    response_model=KpiRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a KPI for a company",
)
def create_kpi(
    company_id: UUID,
    payload: KpiCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> KpiRead:
    mgr = CompanyManager(db)
    try:
        return mgr.create_kpi(company_id=company_id, **payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/{company_id}/kpis/recompute",
    summary="Recompute all KPI values from authoritative data",
)
def recompute_kpis(
    company_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> dict:
    _company_or_404(db, company_id)
    return CompanyManager(db).recompute_kpis(company_id)


# ── Budgets ─────────────────────────────────────────────────────────────


@router.get("/{company_id}/budgets", summary="Get company + department budgets")
def company_budgets(
    company_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> dict:
    _company_or_404(db, company_id)
    return CompanyManager(db).budgets(company_id)


# ── Performance / reports ───────────────────────────────────────────────


@router.get("/{company_id}/performance", summary="Get company performance aggregates")
def company_performance(
    company_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> dict:
    _company_or_404(db, company_id)
    return CompanyManager(db).performance(company_id)


@router.get("/{company_id}/reports", summary="List company reports")
def company_reports(
    company_id: UUID,
    report_type: str | None = Query(default=None),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[dict]:
    _company_or_404(db, company_id)
    return CompanyManager(db).reports(company_id, report_type=report_type)


@router.post("/{company_id}/reports/generate", summary="Generate a company report")
def generate_report(
    company_id: UUID,
    report_type: str = "weekly",
    db: Session = Depends(get_db),  # noqa: B008
) -> dict:
    _company_or_404(db, company_id)
    generator = ReportGenerator(db)
    report = generator.generate(company_id, report_type=report_type)
    generator.verify(report)
    return generator.to_dict(report)


# ── Risks ───────────────────────────────────────────────────────────────


@router.get("/{company_id}/risks", response_model=list[RiskRead], summary="List company risks")
def company_risks(
    company_id: UUID,
    severity: str | None = Query(default=None),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[RiskRead]:
    _company_or_404(db, company_id)
    return CompanyManager(db).get_risks(company_id, severity=severity)


@router.post(
    "/{company_id}/risks",
    response_model=RiskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a risk",
)
def create_risk(
    company_id: UUID,
    payload: RiskCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> RiskRead:
    mgr = CompanyManager(db)
    try:
        return mgr.create_risk(company_id=company_id, **payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ── Alerts ──────────────────────────────────────────────────────────────


@router.get("/{company_id}/alerts", summary="List company alerts")
def company_alerts(
    company_id: UUID,
    severity: str | None = Query(default=None),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[dict]:
    _company_or_404(db, company_id)
    return CompanyManager(db).get_alerts(company_id, severity=severity)


@router.post(
    "/{company_id}/alerts/check",
    summary="Run threshold checks and generate alerts",
)
def check_alerts(company_id: UUID, db: Session = Depends(get_db)) -> dict:  # noqa: B008
    _company_or_404(db, company_id)
    return CompanyManager(db).check_alerts(company_id)


# ── Decisions ───────────────────────────────────────────────────────────


@router.get("/{company_id}/decisions", summary="List company decisions")
def company_decisions(
    company_id: UUID,
    status: str | None = Query(default=None),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[dict]:
    _company_or_404(db, company_id)
    from app.company.decisions import DecisionManager

    mgr = DecisionManager(db)
    decisions = mgr.list_(company_id, status=status)
    return [mgr.to_dict(d) for d in decisions]


# ── Analytics / health ──────────────────────────────────────────────────


@router.get("/{company_id}/analytics", summary="Get full company analytics")
def company_analytics(
    company_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> dict:
    _company_or_404(db, company_id)
    return CompanyManager(db).analytics(company_id)


@router.get("/{company_id}/health", summary="Get company health")
def company_health(
    company_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> dict:
    _company_or_404(db, company_id)
    return CompanyManager(db).health(company_id)


# ── Timeline ────────────────────────────────────────────────────────────


@router.get(
    "/{company_id}/timeline",
    response_model=list[OrgEventRead],
    summary="Get the company timeline / audit log",
)
def company_timeline(
    company_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[OrgEventRead]:
    _company_or_404(db, company_id)
    return CompanyManager(db).timeline(company_id, limit=limit)


# ── Policies ────────────────────────────────────────────────────────────


@router.get("/{company_id}/policies", response_model=list[PolicyRead], summary="List policies")
def company_policies(
    company_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[PolicyRead]:
    _company_or_404(db, company_id)
    return CompanyManager(db).get_policies(company_id)


@router.post(
    "/{company_id}/policies",
    response_model=PolicyRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a policy",
)
def create_policy(
    company_id: UUID,
    payload: PolicyCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> PolicyRead:
    mgr = CompanyManager(db)
    try:
        return mgr.create_policy(company_id=company_id, **payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get(
    "/{company_id}/policies/effective",
    response_model=EffectivePolicy,
    summary="Resolve the effective (most-restrictive) policy value for a key",
)
def effective_policy(
    company_id: UUID,
    key: str = Query(...),  # noqa: B008
    department_id: UUID | None = Query(default=None),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> EffectivePolicy:
    _company_or_404(db, company_id)
    return CompanyManager(db).effective_policy(company_id, key=key, department_id=department_id)


# ── Roles ───────────────────────────────────────────────────────────────


@router.get("/{company_id}/roles", response_model=list[dict], summary="List company roles")
def company_roles(
    company_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[dict]:
    _company_or_404(db, company_id)
    return CompanyManager(db).get_roles(company_id)
