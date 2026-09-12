"""Phase 10 external evaluation tests — §61 metric aggregation.

Metrics: success rate, verification rate, recovery rate, browser/computer session rates,
duplicate rate, intervention rate, duration percentiles.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

_counter = 0


def _company(db: Session):
    global _counter
    from app.company.manager import CompanyManager

    _counter += 1
    return CompanyManager(db).create(name=f"Eval Co {_counter}", description="unit")


def _email_setup(db: Session, company_id: UUID):
    from app.external.integration import IntegrationService

    svc = IntegrationService(db)
    integration = svc.create(company_id=company_id, provider="email", name="Email")
    connection = svc.connect(
        company_id=company_id,
        integration_id=integration.id,
        auth_method="api_key",
        secret_value="mail-secret-9876543210",
        env_var_hint="INTEGRATION_EMAIL_API_KEY",
        scopes=["email:send"],
        permissions=["email:send"],
    )
    return integration, connection


def _reset_mailbox():
    from app.external.providers import email as email_module

    email_module._MAILBOX.pop("email", None)
    email_module._SENT.pop("email", None)
    email_module._DRAFTS.pop("email", None)
    email_module._seed_mailbox("email")


class TestExternalMetricsAggregation:
    def test_success_rate_calculation(self, db: Session) -> None:
        from app.external.action import ExternalActionManager
        from app.external.evaluation.metrics import compute_external_metrics
        from app.startup.autonomy import AutonomyService

        _reset_mailbox()
        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        integration, connection = _email_setup(db, company.id)

        mgr = ExternalActionManager(db)

        # Create 3 successful actions
        for i in range(3):
            mgr.create(
                company_id=company.id,
                integration_id=integration.id,
                capability="search_messages",
                payload={"query": f"test-{i}"},
                connection_id=connection.id,
            )

        # Create 1 failed action (will be blocked by policy)
        from app.db.models.external import IntegrationPolicy, ScopeType

        db.add(
            IntegrationPolicy(
                company_id=company.id,
                integration_id=integration.id,
                scope_type=ScopeType.COMPANY,
                capability_pattern="send_message",
                allowed=False,
                require_approval=True,
                enabled=True,
            )
        )
        db.commit()

        try:
            mgr.create(
                company_id=company.id,
                integration_id=integration.id,
                capability="send_message",
                payload={"to": ["x@example.com"], "subject": "S", "body": "B"},
                connection_id=connection.id,
            )
        except Exception:
            pass

        metrics = compute_external_metrics(db, company.id)
        # 3 succeeded, 1 failed = 75% success rate
        assert metrics["success_rate"] == 0.75
        assert metrics["total_actions"] == 4
        assert metrics["succeeded_count"] == 3
        assert metrics["failed_count"] == 1

    def test_verification_rate(self, db: Session) -> None:
        from app.external.action import ExternalActionManager
        from app.external.evaluation.metrics import compute_external_metrics
        from app.startup.autonomy import AutonomyService

        _reset_mailbox()
        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        integration, connection = _email_setup(db, company.id)

        mgr = ExternalActionManager(db)

        # Create actions - all should have verification. An empty query matches
        # the seeded mailbox (each message carries an `id`), so the read-back
        # verification trace is recorded on every action row.
        for _ in range(5):
            mgr.create(
                company_id=company.id,
                integration_id=integration.id,
                capability="search_messages",
                payload={"query": ""},
                connection_id=connection.id,
            )

        metrics = compute_external_metrics(db, company.id)
        # All actions should be verified
        assert metrics["verification_rate"] == 1.0
        assert metrics["verified_count"] == 5

    def test_recovery_rate(self, db: Session) -> None:
        from app.db.models.external import ExternalActionAttempt
        from app.external.action import ExternalActionManager
        from app.external.evaluation.metrics import compute_external_metrics
        from app.startup.autonomy import AutonomyService

        _reset_mailbox()
        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        integration, connection = _email_setup(db, company.id)

        mgr = ExternalActionManager(db)

        # Create successful action
        action = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="search_messages",
            payload={"query": "test"},
            connection_id=connection.id,
        )

        # Manually add a retry attempt to simulate recovery
        attempt = ExternalActionAttempt(
            action_id=action.id,
            attempt_number=2,
            strategy="retry_with_backoff",
            status="succeeded",
            retryable=True,
            error_category="RESOURCE_LIMIT",
            duration_ms=1500,
        )
        db.add(attempt)
        db.commit()

        metrics = compute_external_metrics(db, company.id)
        assert metrics["recovery_rate"] == 1.0  # The retry succeeded

    def test_duplicate_rate(self, db: Session) -> None:
        from app.external.action import ExternalActionManager
        from app.external.evaluation.metrics import compute_external_metrics
        from app.external.result import ExternalActionError
        from app.startup.autonomy import AutonomyService

        _reset_mailbox()
        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        integration, connection = _email_setup(db, company.id)

        mgr = ExternalActionManager(db)

        # Create action with idempotency key. search_messages is LOW-risk and
        # auto-runs, so the first create reaches a terminal "succeeded" —
        # exactly the state IdempotencyGuard requires to detect a duplicate
        # (send_message would park at AWAITING_APPROVAL and never be terminal).
        mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="search_messages",
            payload={"query": "dup"},
            connection_id=connection.id,
            idempotency_key="dup-test-1",
        )

        # Try duplicate - should be blocked
        try:
            mgr.create(
                company_id=company.id,
                integration_id=integration.id,
                capability="search_messages",
                payload={"query": "dup"},
                connection_id=connection.id,
                idempotency_key="dup-test-1",
            )
        except ExternalActionError:
            pass

        metrics = compute_external_metrics(db, company.id)
        assert metrics["duplicate_rate"] > 0
        assert metrics["blocked_duplicate_count"] >= 1

    def test_intervention_rate(self, db: Session) -> None:
        from app.db.models.external import ExternalActionStatus
        from app.external.action import ExternalActionManager
        from app.external.evaluation.metrics import compute_external_metrics
        from app.startup.gates import ApprovalGateManager

        _reset_mailbox()
        company = _company(db)
        # NO allow_matrix - defaults to require approval
        integration, connection = _email_setup(db, company.id)

        mgr = ExternalActionManager(db)

        # Create action that requires approval
        action = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="send_message",
            payload={"to": ["x@example.com"], "subject": "S", "body": "B"},
            action_type="send_message",
            connection_id=connection.id,
        )
        assert action.status == ExternalActionStatus.AWAITING_APPROVAL

        # Approve
        ApprovalGateManager(db).approve(company.id, action.approval_gate_id)

        # Execute with gate
        mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="send_message",
            payload={"to": ["x@example.com"], "subject": "S", "body": "B"},
            action_type="send_message",
            connection_id=connection.id,
            approved_gate_id=action.approval_gate_id,
        )

        metrics = compute_external_metrics(db, company.id)
        # One action required intervention (approval)
        assert metrics["intervention_rate"] > 0
        assert metrics["actions_requiring_approval"] >= 1

    def test_duration_percentiles(self, db: Session) -> None:
        from app.external.action import ExternalActionManager
        from app.external.evaluation.metrics import compute_external_metrics
        from app.startup.autonomy import AutonomyService

        _reset_mailbox()
        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        integration, connection = _email_setup(db, company.id)

        mgr = ExternalActionManager(db)

        # Create several actions
        for i in range(10):
            mgr.create(
                company_id=company.id,
                integration_id=integration.id,
                capability="search_messages",
                payload={"query": f"test-{i}"},
                connection_id=connection.id,
            )

        metrics = compute_external_metrics(db, company.id)
        assert "duration_p50_ms" in metrics
        assert "duration_p95_ms" in metrics
        assert "duration_p99_ms" in metrics
        assert metrics["duration_p50_ms"] > 0
        assert metrics["duration_p95_ms"] >= metrics["duration_p50_ms"]
        assert metrics["duration_p99_ms"] >= metrics["duration_p95_ms"]

    def test_browser_session_metrics(self, db: Session) -> None:
        from app.external.browser.mock_driver import FIXTURE_DOMAIN
        from app.external.browser.session import BrowserSessionManager
        from app.external.evaluation.metrics import compute_external_metrics

        company = _company(db)
        mgr = BrowserSessionManager(db)

        # Create sessions and perform actions
        for _ in range(3):
            session = mgr.create(company_id=company.id, allowed_domains=[FIXTURE_DOMAIN])
            mgr.action(
                company.id,
                session.id,
                action_type="open_page",
                target={"url": f"https://{FIXTURE_DOMAIN}/"},
            )
            mgr.action(company.id, session.id, action_type="extract_text")

        metrics = compute_external_metrics(db, company.id)
        assert metrics["browser_sessions_count"] == 3
        assert metrics["browser_actions_count"] == 6  # 2 per session
        assert metrics["browser_observations_count"] >= 3

    def test_computer_session_metrics(self, db: Session) -> None:
        from app.external.computer.session import ComputerSessionManager
        from app.external.evaluation.metrics import compute_external_metrics

        company = _company(db)
        mgr = ComputerSessionManager(db)

        # Create sessions and perform actions. The mock driver resolves a click
        # against the screen's element map, so the click needs an element
        # reference (btn-reports is a real button on the simulated desk).
        for i in range(2):
            session = mgr.create(company_id=company.id)
            mgr.action(
                company.id,
                session.id,
                action_type="move_mouse",
                input_data={"x": i * 10, "y": i * 10},
            )
            mgr.action(
                company.id,
                session.id,
                action_type="click",
                input_data={"x": i * 10, "y": i * 10, "element": "btn-reports"},
            )

        metrics = compute_external_metrics(db, company.id)
        assert metrics["computer_sessions_count"] == 2
        assert metrics["computer_actions_count"] == 4  # 2 per session
        assert metrics["computer_observations_count"] >= 2

    def test_external_events_metrics(self, db: Session) -> None:

        from app.db.models.external import (
            ExternalEvent,
            ExternalEventSource,
            VerificationStatusExternal,
        )
        from app.external.evaluation.metrics import compute_external_metrics

        company = _company(db)

        # Create webhook events
        for i in range(5):
            payload = {"event": "message_received", "data": {"id": f"msg-{i}"}}
            event = ExternalEvent(
                source=ExternalEventSource.WEBHOOK,
                company_id=company.id,
                event_type="message_received",
                payload=json.dumps(payload),
                payload_size=len(json.dumps(payload)),
                timestamp=datetime.now(UTC),
                verification_status=VerificationStatusExternal.VERIFIED,
                signature_status="verified",
                ingest_id=f"evt-{i}",
                received_at=datetime.now(UTC),
            )
            db.add(event)
        db.commit()

        metrics = compute_external_metrics(db, company.id)
        assert metrics["external_events_count"] == 5
        assert metrics["webhook_events_verified"] == 5


class TestEvaluationTimeWindows:
    def test_metrics_respect_time_window(self, db: Session) -> None:
        from app.external.action import ExternalActionManager
        from app.external.evaluation.metrics import compute_external_metrics
        from app.startup.autonomy import AutonomyService

        _reset_mailbox()
        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        integration, connection = _email_setup(db, company.id)

        mgr = ExternalActionManager(db)

        # Create old action (outside window)
        old_action = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="search_messages",
            payload={"query": "old"},
            connection_id=connection.id,
        )
        # Manually backdate
        old_action.created_at = datetime.now(UTC) - timedelta(days=10)
        db.commit()

        # Create recent action
        mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="search_messages",
            payload={"query": "recent"},
            connection_id=connection.id,
        )

        # Default window should include both
        metrics_all = compute_external_metrics(db, company.id)
        # With 7-day window, only recent
        metrics_7d = compute_external_metrics(db, company.id, window_days=7)

        assert metrics_all["total_actions"] == 2
        assert metrics_7d["total_actions"] == 1


class TestEvaluationCrossCompany:
    def test_metrics_isolated_per_company(self, db: Session) -> None:
        from app.external.action import ExternalActionManager
        from app.external.evaluation.metrics import compute_external_metrics
        from app.startup.autonomy import AutonomyService

        _reset_mailbox()
        a, b = _company(db), _company(db)
        AutonomyService(db).set_policy(a.id, allow_matrix={"external_action": "allow"})
        AutonomyService(db).set_policy(b.id, allow_matrix={"external_action": "allow"})

        int_a, conn_a = _email_setup(db, a.id)
        int_b, conn_b = _email_setup(db, b.id)

        mgr = ExternalActionManager(db)

        # Create actions for company A
        for i in range(3):
            mgr.create(
                company_id=a.id,
                integration_id=int_a.id,
                capability="search_messages",
                payload={"query": f"a-{i}"},
                connection_id=conn_a.id,
            )

        # Create actions for company B
        for i in range(2):
            mgr.create(
                company_id=b.id,
                integration_id=int_b.id,
                capability="search_messages",
                payload={"query": f"b-{i}"},
                connection_id=conn_b.id,
            )

        metrics_a = compute_external_metrics(db, a.id)
        metrics_b = compute_external_metrics(db, b.id)

        assert metrics_a["total_actions"] == 3
        assert metrics_b["total_actions"] == 2
