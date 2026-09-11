"""Tests for AI Company Layer — API integration via TestClient."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient


class TestCompanyAPI:
    """Exercise the /companies endpoints via the api_client fixture."""

    def test_create_company(self, api_client: TestClient) -> None:
        resp = api_client.post(
            "/api/v1/companies",
            json={"name": "Acme", "industry": "tech"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Acme"
        assert data["status"] == "draft"

    def test_list_companies(self, api_client: TestClient) -> None:
        api_client.post("/api/v1/companies", json={"name": "A"})
        api_client.post("/api/v1/companies", json={"name": "B"})
        resp = api_client.get("/api/v1/companies")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    def test_get_company(self, api_client: TestClient) -> None:
        create = api_client.post("/api/v1/companies", json={"name": "X"})
        cid = create.json()["id"]
        resp = api_client.get(f"/api/v1/companies/{cid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "X"

    def test_get_company_not_found(self, api_client: TestClient) -> None:
        resp = api_client.get(f"/api/v1/companies/{uuid4()}")
        assert resp.status_code == 404

    def test_update_company(self, api_client: TestClient) -> None:
        create = api_client.post("/api/v1/companies", json={"name": "Y"})
        cid = create.json()["id"]
        resp = api_client.put(f"/api/v1/companies/{cid}", json={"name": "Y Updated"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Y Updated"

    def test_activate_company(self, api_client: TestClient) -> None:
        create = api_client.post("/api/v1/companies", json={"name": "Z"})
        cid = create.json()["id"]
        resp = api_client.post(f"/api/v1/companies/{cid}/activate")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_pause_company(self, api_client: TestClient) -> None:
        create = api_client.post("/api/v1/companies", json={"name": "P"})
        cid = create.json()["id"]
        api_client.post(f"/api/v1/companies/{cid}/activate")
        resp = api_client.post(f"/api/v1/companies/{cid}/pause")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

    def test_archive_company(self, api_client: TestClient) -> None:
        create = api_client.post("/api/v1/companies", json={"name": "A"})
        cid = create.json()["id"]
        api_client.post(f"/api/v1/companies/{cid}/activate")
        resp = api_client.post(f"/api/v1/companies/{cid}/archive")
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

    def test_invalid_transition_returns_400(self, api_client: TestClient) -> None:
        create = api_client.post("/api/v1/companies", json={"name": "D"})
        cid = create.json()["id"]
        # draft → pause is invalid
        resp = api_client.post(f"/api/v1/companies/{cid}/pause")
        assert resp.status_code == 400


class TestDepartmentAPI:
    def test_create_department(self, api_client: TestClient) -> None:
        create = api_client.post("/api/v1/companies", json={"name": "Co"})
        cid = create.json()["id"]
        resp = api_client.post(
            f"/api/v1/companies/{cid}/departments",
            json={"name": "Engineering"},
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Engineering"

    def test_list_departments(self, api_client: TestClient) -> None:
        create = api_client.post("/api/v1/companies", json={"name": "Co"})
        cid = create.json()["id"]
        api_client.post(
            f"/api/v1/companies/{cid}/departments",
            json={"name": "Engineering"},
        )
        resp = api_client.get(f"/api/v1/companies/{cid}/departments")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestGoalAPI:
    def test_create_goal(self, api_client: TestClient) -> None:
        create = api_client.post("/api/v1/companies", json={"name": "Co"})
        cid = create.json()["id"]
        resp = api_client.post(
            f"/api/v1/companies/{cid}/goals",
            json={
                "scope_type": "company",
                "scope_id": cid,
                "title": "Ship v2",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["title"] == "Ship v2"

    def test_list_goals(self, api_client: TestClient) -> None:
        create = api_client.post("/api/v1/companies", json={"name": "Co"})
        cid = create.json()["id"]
        api_client.post(
            f"/api/v1/companies/{cid}/goals",
            json={
                "scope_type": "company",
                "scope_id": cid,
                "title": "G1",
            },
        )
        resp = api_client.get(f"/api/v1/companies/{cid}/goals")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


class TestRiskAPI:
    def test_create_risk(self, api_client: TestClient) -> None:
        create = api_client.post("/api/v1/companies", json={"name": "Co"})
        cid = create.json()["id"]
        resp = api_client.post(
            f"/api/v1/companies/{cid}/risks",
            json={
                "scope_type": "company",
                "scope_id": cid,
                "title": "Budget Overrun",
                "severity": "high",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["title"] == "Budget Overrun"

    def test_list_risks(self, api_client: TestClient) -> None:
        create = api_client.post("/api/v1/companies", json={"name": "Co"})
        cid = create.json()["id"]
        api_client.post(
            f"/api/v1/companies/{cid}/risks",
            json={
                "scope_type": "company",
                "scope_id": cid,
                "title": "R1",
                "severity": "low",
            },
        )
        resp = api_client.get(f"/api/v1/companies/{cid}/risks")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


class TestPolicyAPI:
    def test_create_and_list_policies(self, api_client: TestClient) -> None:
        create = api_client.post("/api/v1/companies", json={"name": "Co"})
        cid = create.json()["id"]
        api_client.post(
            f"/api/v1/companies/{cid}/policies",
            json={
                "scope_type": "company",
                "name": "Token Limit",
                "key": "max_tokens",
                "value": 4096,
            },
        )
        resp = api_client.get(f"/api/v1/companies/{cid}/policies")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


class TestTimelineAPI:
    def test_timeline(self, api_client: TestClient) -> None:
        create = api_client.post("/api/v1/companies", json={"name": "Co"})
        cid = create.json()["id"]
        resp = api_client.get(f"/api/v1/companies/{cid}/timeline")
        assert resp.status_code == 200
        # At least the company_created event
        assert len(resp.json()) >= 1


class TestDecisionAPI:
    def test_create_and_list_decisions(self, api_client: TestClient) -> None:
        create = api_client.post("/api/v1/companies", json={"name": "Co"})
        cid = create.json()["id"]
        api_client.post(
            "/api/v1/decisions",
            params={"company_id": cid},
            json={
                "question": "Should we adopt microservices?",
                "options": [{"id": "a", "label": "Yes"}, {"id": "b", "label": "No"}],
            },
        )
        resp = api_client.get(f"/api/v1/companies/{cid}/decisions")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1
        assert resp.json()[0]["question"] == "Should we adopt microservices?"

    def test_list_decisions_filtered_by_status(self, api_client: TestClient) -> None:
        create = api_client.post("/api/v1/companies", json={"name": "Co2"})
        cid = create.json()["id"]
        api_client.post(
            "/api/v1/decisions",
            params={"company_id": cid},
            json={
                "question": "Hire more agents?",
                "options": [{"id": "a", "label": "Yes"}],
            },
        )
        resp = api_client.get(f"/api/v1/companies/{cid}/decisions", params={"status": "draft"})
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        resp = api_client.get(f"/api/v1/companies/{cid}/decisions", params={"status": "approved"})
        assert len(resp.json()) == 0


# ── Regression: aggregates, membership edits, decision lifecycle ──────────────


def _seed_company_with_employee(db_engine):
    """Create and activate a company with one employee for aggregate tests.

    Seeds through the same SQLite engine the ``api_client`` uses so the
    TestClient can see the rows (the production ``SessionLocal`` targets
    Postgres and would not be visible there).
    """
    from uuid import uuid4

    from sqlalchemy.orm import Session

    from app.company.manager import CompanyManager
    from app.employee.manager import EmployeeManager

    with Session(bind=db_engine, expire_on_commit=False) as db:
        mgr = CompanyManager(db)
        company = mgr.create(name=f"Regress-{uuid4().hex[:8]}", industry="tech")
        mgr.add_membership(
            company_id=company.id,
            employee_id=EmployeeManager(db).create(name=f"emp-{uuid4().hex[:6]}").id,
            responsibility="ic",
        )
        db.commit()
        return str(company.id)


class TestCompanyAggregates:
    """Ensure performance/analytics/health/budgets endpoints return 200."""

    def test_health_endpoint(self, api_client: TestClient, db_engine) -> None:
        cid = _seed_company_with_employee(db_engine)
        resp = api_client.get(f"/api/v1/companies/{cid}/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "overall_score" in body
        assert "status" in body
        assert "dimensions" in body

    def test_performance_endpoint(self, api_client: TestClient, db_engine) -> None:
        cid = _seed_company_with_employee(db_engine)
        resp = api_client.get(f"/api/v1/companies/{cid}/performance")
        assert resp.status_code == 200
        body = resp.json()
        assert "task_volume" in body
        assert "success_rate" in body

    def test_analytics_endpoint(self, api_client: TestClient, db_engine) -> None:
        cid = _seed_company_with_employee(db_engine)
        resp = api_client.get(f"/api/v1/companies/{cid}/analytics")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"workforce", "operations", "reliability", "finance", "strategy"}

    def test_budgets_endpoint(self, api_client: TestClient, db_engine) -> None:
        cid = _seed_company_with_employee(db_engine)
        resp = api_client.get(f"/api/v1/companies/{cid}/budgets")
        assert resp.status_code == 200
        body = resp.json()
        assert "company" in body
        assert "departments" in body


class TestMembershipUpdateRemove:
    """Membership update and remove endpoints (PUT / DELETE)."""

    def test_update_membership_role(self, api_client: TestClient, db_engine) -> None:
        from uuid import uuid4

        from sqlalchemy.orm import Session

        from app.company.manager import CompanyManager
        from app.company.roles import RoleManager
        from app.db.models.company import AuthorityLevel
        from app.employee.manager import EmployeeManager

        with Session(bind=db_engine, expire_on_commit=False) as db:
            company = CompanyManager(db).create(name="MemUpdCo")
            emp = EmployeeManager(db).create(name=f"mem-emp-{uuid4().hex[:6]}")
            mem = CompanyManager(db).add_membership(
                company_id=company.id, employee_id=emp.id, responsibility="ic"
            )
            role = RoleManager(db).create(
                company_id=company.id,
                name="tl",
                title="Tech Lead",
                authority_level=AuthorityLevel.TEAM_LEAD,
            )
            db.commit()
            mem_id, role_id = str(mem["id"]), str(role.id)

        resp = api_client.put(
            f"/api/v1/companies/{uuid4()}/memberships/{mem_id}",
            json={"role_id": role_id},
        )
        assert resp.status_code == 200
        assert resp.json()["role_id"] == role_id

    def test_remove_membership(self, api_client: TestClient, db_engine) -> None:
        from uuid import uuid4

        from sqlalchemy.orm import Session

        from app.company.manager import CompanyManager
        from app.employee.manager import EmployeeManager

        with Session(bind=db_engine, expire_on_commit=False) as db:
            company = CompanyManager(db).create(name="MemRmCo")
            emp = EmployeeManager(db).create(name=f"rm-emp-{uuid4().hex[:6]}")
            mem = CompanyManager(db).add_membership(company_id=company.id, employee_id=emp.id)
            db.commit()
            mem_id = str(mem["id"])

        resp = api_client.delete(f"/api/v1/companies/{uuid4()}/memberships/{mem_id}")
        assert resp.status_code == 204


class TestDecisionLifecycleAPI:
    """Decision create/submit/approve/implement via the public API with authz."""

    def test_full_decision_lifecycle(self, api_client: TestClient, db_engine) -> None:
        from uuid import uuid4

        from sqlalchemy.orm import Session

        from app.company.manager import CompanyManager
        from app.company.roles import RoleManager
        from app.db.models.company import AuthorityLevel
        from app.employee.manager import EmployeeManager

        with Session(bind=db_engine, expire_on_commit=False) as db:
            company = CompanyManager(db).create(name="DecLifeCo")
            emp = EmployeeManager(db).create(name=f"dec-emp-{uuid4().hex[:6]}")
            role = RoleManager(db).create(
                company_id=company.id,
                name="adm",
                title="Admin",
                authority_level=AuthorityLevel.COMPANY_ADMIN,
            )
            CompanyManager(db).add_membership(
                company_id=company.id, employee_id=emp.id, role_id=role.id, responsibility="manager"
            )
            db.commit()
            reviewer_id, cid = str(emp.id), str(company.id)

        resp = api_client.post(
            "/api/v1/decisions",
            params={"company_id": cid},
            json={
                "question": "Approve deployment?",
                "options": [{"id": "o1", "label": "Yes"}],
                "required_authority": "company_admin",
            },
        )
        assert resp.status_code == 201
        did = resp.json()["id"]
        assert resp.json()["status"] == "draft"

        resp = api_client.post(f"/api/v1/decisions/{did}/submit")
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending_review"

        resp = api_client.post(
            f"/api/v1/decisions/{did}/approve",
            params={"reviewer_id": reviewer_id},
            json={"rationale": "Looks good"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

        resp = api_client.post(
            f"/api/v1/decisions/{did}/implement", params={"actor_id": reviewer_id}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "implemented"

        resp = api_client.get(f"/api/v1/decisions/{did}/reviews")
        assert resp.status_code == 200
        reviews = resp.json()
        assert len(reviews) >= 3  # created + submitted + approved + implemented
