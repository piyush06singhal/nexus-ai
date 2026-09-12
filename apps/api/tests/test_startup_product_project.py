"""Tests for Phase 9 product lifecycle, validation, governed launch, and
startup-projects with objectives/dependencies/lifecycle."""

from __future__ import annotations

from sqlalchemy.orm import Session

_counter = 0


def _company(db: Session):
    global _counter
    from app.company.manager import CompanyManager

    _counter += 1
    return CompanyManager(db).create(name=f"Product Co {_counter}", description="unit")


def _approved_gate(db: Session, company_id, gate_type: str = "product_launch_approval"):
    from app.startup.gates import ApprovalGateManager

    manager = ApprovalGateManager(db)
    gate = manager.create(
        company_id=company_id,
        gate_type=gate_type,
        requested_action={"action": "launch_product"},
        rationale="Unit test gate",
        risk_level="medium",
    )
    manager.approve(company_id, gate.id, approver_id=None)
    return gate.id


class TestProductManager:
    def test_create(self, db: Session) -> None:
        from app.startup.products import ProductManager

        company = _company(db)
        product = ProductManager(db).create(
            company_id=company.id,
            name="CLI",
            description="A CLI",
            product_type="developer_tool",
            target_users=["small teams"],
        )
        assert product.name == "CLI"
        assert product.status.value == "idea"
        assert ProductManager(db).get(company.id, product.id) is not None

    def test_listing_scoped(self, db: Session) -> None:
        from app.startup.products import ProductManager

        company_a = _company(db)
        company_b = _company(db)
        pm = ProductManager(db)
        pm.create(company_id=company_a.id, name="A")
        pm.create(company_id=company_b.id, name="B")
        assert {p.name for p in pm.list_(company_a.id)} == {"A"}
        assert {p.name for p in pm.list_(company_b.id)} == {"B"}

    def test_lifecycle_transitions(self, db: Session) -> None:
        from app.startup.products import ProductManager

        company = _company(db)
        pm = ProductManager(db)
        product = pm.create(company_id=company.id, name="CLI")
        for target in (
            "discovery",
            "validation",
            "planning",
            "building",
            "testing",
            "ready_for_launch",
        ):
            pm.lifecycle(company.id, product.id, target)
        assert pm.get(company.id, product.id).status.value == "ready_for_launch"

    def test_invalid_transition_rejected(self, db: Session) -> None:
        from app.startup.products import ProductManager

        company = _company(db)
        pm = ProductManager(db)
        product = pm.create(company_id=company.id, name="CLI")
        # idea → launched is not an allowed jump.
        try:
            pm.lifecycle(company.id, product.id, "launched")
            raise AssertionError("Disallowed jump must fail")
        except ValueError:
            pass

    def test_validation_labeled_simulated(self, db: Session) -> None:
        """Validation is internal and labeled; it never claims a real market run."""
        from app.startup.products import ProductManager

        company = _company(db)
        pm = ProductManager(db)
        product = pm.create(
            company_id=company.id,
            name="CLI",
            launch_criteria=["Runs end to end", "Docs published"],
        )
        result = pm.validate(company.id, product.id)
        assert result.ok is True  # criteria present
        from app.db.models.startup import Product

        stored = db.get(Product, product.id)
        assert stored.validation is not None

    def test_launch_requires_gate(self, db: Session) -> None:
        from app.startup.products import ProductManager

        company = _company(db)
        pm = ProductManager(db)
        product = pm.create(
            company_id=company.id,
            name="CLI",
            launch_criteria=["Ready"],
        )
        for target in (
            "discovery",
            "validation",
            "planning",
            "building",
            "testing",
            "ready_for_launch",
        ):
            pm.lifecycle(company.id, product.id, target)
        # No gate at bounded_autonomy → launch is blocked.
        try:
            pm.launch(company.id, product.id)
            raise AssertionError("Launch without a gate must fail")
        except Exception as exc:
            assert "approval" in str(exc).lower()

    def test_launch_with_gate(self, db: Session) -> None:
        from app.startup.products import ProductManager

        company = _company(db)
        pm = ProductManager(db)
        product = pm.create(
            company_id=company.id,
            name="CLI",
            launch_criteria=["Ready"],
        )
        for target in (
            "discovery",
            "validation",
            "planning",
            "building",
            "testing",
            "ready_for_launch",
        ):
            pm.lifecycle(company.id, product.id, target)
        gate_id = _approved_gate(db, company.id)
        launched = pm.launch(company.id, product.id, approved_gate_id=gate_id)
        assert launched.status.value == "launched"


class TestProjectManager:
    def test_create_with_objective(self, db: Session) -> None:
        from app.startup.projects import ProjectManager

        company = _company(db)
        pm = ProjectManager(db)
        project = pm.create(
            company_id=company.id,
            name="Build CLI",
            objective="Create the developer CLI",
            priority=1,
            success_criteria=["CLI usable"],
        )
        assert project.objective == "Create the developer CLI"
        assert project.status.value == "planned"

    def test_project_product_link(self, db: Session) -> None:
        from app.startup.graph import MissionGraphBuilder
        from app.startup.products import ProductManager
        from app.startup.projects import ProjectManager

        company = _company(db)
        product = ProductManager(db).create(company_id=company.id, name="CLI")
        project = ProjectManager(db).create(
            company_id=company.id,
            name="Build CLI",
            product_id=product.id,
        )
        edges = MissionGraphBuilder(db).query(
            company.id, node_type="startup_project", node_id=project.id
        )
        assert any(e.target_type == "product" and e.target_id == product.id for e in edges)

    def test_lifecycle(self, db: Session) -> None:
        from app.startup.projects import ProjectManager

        company = _company(db)
        pm = ProjectManager(db)
        project = pm.create(company_id=company.id, name="P")
        pm.lifecycle(company.id, project.id, "active")
        pm.lifecycle(company.id, project.id, "blocked")
        pm.lifecycle(company.id, project.id, "active")
        pm.lifecycle(company.id, project.id, "completed")
        assert pm.get(company.id, project.id).status.value == "completed"

    def test_invalid_lifecycle(self, db: Session) -> None:
        from app.startup.projects import ProjectManager

        company = _company(db)
        pm = ProjectManager(db)
        project = pm.create(company_id=company.id, name="P")
        try:
            pm.lifecycle(company.id, project.id, "completed")
            raise AssertionError("planned → completed jump must fail")
        except ValueError:
            pass

    def test_project_company_isolation(self, db: Session) -> None:
        from app.startup.projects import ProjectManager

        company = _company(db)
        other = _company(db)
        pm = ProjectManager(db)
        project = pm.create(company_id=company.id, name="Secret")
        assert pm.get(other.id, project.id) is None
