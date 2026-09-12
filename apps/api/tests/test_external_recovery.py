"""Phase 10 external recovery tests — provider failure codes → Phase 6 taxonomy
mapping → recovery-strategy selection → idempotency-protected retry (§75 Recovery).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

_counter = 0


def _company(db: Session):
    global _counter
    from app.company.manager import CompanyManager

    _counter += 1
    return CompanyManager(db).create(name=f"Recovery Co {_counter}", description="unit")


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


class TestExternalFailureClassification:
    def test_rate_limit_mapped_to_resource_limit(self, db: Session) -> None:
        from app.external.recovery.mapping import classify_external_failure
        from app.recovery.taxonomy import FailureCategory

        category, _ = classify_external_failure("http_429")
        assert category == FailureCategory.RESOURCE_LIMIT

    def test_auth_failure_mapped_to_permission_failure(self, db: Session) -> None:
        from app.external.recovery.mapping import classify_external_failure
        from app.recovery.taxonomy import FailureCategory

        category, _ = classify_external_failure("auth_failed")
        assert category == FailureCategory.PERMISSION_FAILURE
        category, _ = classify_external_failure("http_401")
        assert category == FailureCategory.PERMISSION_FAILURE
        category, _ = classify_external_failure("http_403")
        assert category == FailureCategory.PERMISSION_FAILURE

    def test_server_error_mapped_to_system_failure(self, db: Session) -> None:
        from app.external.recovery.mapping import classify_external_failure
        from app.recovery.taxonomy import FailureCategory

        for code in ("http_500", "http_502", "http_503", "transport_error", "system_error"):
            category, _ = classify_external_failure(code)
            assert category == FailureCategory.SYSTEM_FAILURE, code

    def test_timeout_mapped_to_timeout(self, db: Session) -> None:
        from app.external.recovery.mapping import classify_external_failure
        from app.recovery.taxonomy import FailureCategory

        category, _ = classify_external_failure("timeout")
        assert category == FailureCategory.TIMEOUT
        # 504 Gateway Timeout is classified as SYSTEM_FAILURE (5xx range)
        # Only 408 Request Timeout and explicit "timeout" code map to TIMEOUT
        category, _ = classify_external_failure("http_408")
        assert category == FailureCategory.TIMEOUT

    def test_missing_element_mapped_to_validation_failure(self, db: Session) -> None:
        from app.external.recovery.mapping import classify_external_failure
        from app.recovery.taxonomy import FailureCategory

        category, _ = classify_external_failure("validation_failed")
        assert category == FailureCategory.VALIDATION_FAILURE
        category, _ = classify_external_failure("not_found")
        assert category == FailureCategory.VALIDATION_FAILURE

    def test_unknown_error_mapped_to_tool_failure(self, db: Session) -> None:
        from app.external.recovery.mapping import classify_external_failure
        from app.recovery.taxonomy import FailureCategory

        category, _ = classify_external_failure("external_error")
        assert category == FailureCategory.TOOL_FAILURE


class TestRetryPolicy:
    def test_resource_limit_gets_backoff_retry(self, db: Session) -> None:
        from app.external.recovery.mapping import strategy_for
        from app.recovery.taxonomy import FailureCategory

        assert strategy_for(FailureCategory.RESOURCE_LIMIT) == "retry_with_backoff"

    def test_permission_failure_gets_escalate(self, db: Session) -> None:
        from app.external.recovery.mapping import strategy_for
        from app.recovery.taxonomy import FailureCategory

        assert strategy_for(FailureCategory.PERMISSION_FAILURE) == "escalate"

    def test_system_failure_gets_retry(self, db: Session) -> None:
        from app.external.recovery.mapping import strategy_for
        from app.recovery.taxonomy import FailureCategory

        assert strategy_for(FailureCategory.SYSTEM_FAILURE) == "retry_with_backoff"

    def test_validation_failure_gets_replan(self, db: Session) -> None:
        from app.external.recovery.mapping import strategy_for
        from app.recovery.taxonomy import FailureCategory

        assert strategy_for(FailureCategory.VALIDATION_FAILURE) == "replan"

    def test_timeout_gets_retry_with_backoff(self, db: Session) -> None:
        from app.external.recovery.mapping import strategy_for
        from app.recovery.taxonomy import FailureCategory

        assert strategy_for(FailureCategory.TIMEOUT) == "retry_with_backoff"

    def test_idempotent_retry_only_for_safe_capabilities(self, db: Session) -> None:
        from app.db.models.external import Reversibility
        from app.external.recovery.mapping import retryable

        # A transient failure + caller idempotency key → bounded auto-retry.
        ok, attempts = retryable(
            error_code="http_429",
            supports_idempotency=True,
            has_idempotency_key=True,
            reversibility=Reversibility.PARTIALLY_REVERSIBLE,
        )
        assert ok is True
        assert attempts >= 1

        # Without an idempotency key and irreversibly destructive → escalate.
        ok, attempts = retryable(
            error_code="http_429",
            supports_idempotency=True,
            has_idempotency_key=False,
            reversibility=Reversibility.IRREVERSIBLE,
        )
        assert ok is False
        assert attempts == 0

        # Non-transient classes never auto-retry.
        ok, attempts = retryable(
            error_code="validation_failed",
            supports_idempotency=True,
            has_idempotency_key=True,
            reversibility=Reversibility.REVERSIBLE,
        )
        assert ok is False


class TestIdempotentRetry:
    def test_duplicate_idempotency_key_on_succeeded_blocked(self, db: Session) -> None:
        from app.external.action import ExternalActionManager
        from app.external.result import ExternalActionError
        from app.startup.autonomy import AutonomyService

        _reset_mailbox()
        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        integration, connection = _email_setup(db, company.id)

        mgr = ExternalActionManager(db)
        # Use LOW-risk capability (search_messages) that auto-succeeds
        action = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="search_messages",
            payload={"query": "test"},
            connection_id=connection.id,
            idempotency_key="retry-test-1",
        )
        assert action.status.value == "succeeded"
        assert action.external_operation_id

        # Replay the same key after a terminal success → duplicate refused.
        try:
            mgr.create(
                company_id=company.id,
                integration_id=integration.id,
                capability="search_messages",
                payload={"query": "test"},
                connection_id=connection.id,
                idempotency_key="retry-test-1",
            )
            raise AssertionError("Duplicate idempotency key must be refused on retry")
        except ExternalActionError as exc:
            assert exc.code == "duplicate"

    def test_retry_after_failure_creates_new_attempt(self, db: Session, monkeypatch) -> None:
        from app.db.models.external import ExternalActionAttempt
        from app.external.action import ExternalActionManager
        from app.external.result import ExternalActionError
        from app.startup.autonomy import AutonomyService

        _reset_mailbox()
        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        integration, connection = _email_setup(db, company.id)

        mgr = ExternalActionManager(db)

        # Simulate a provider failure on the first attempt using search_messages (LOW risk).
        import app.external.providers.email as email_module

        original_execute = email_module.EmailProvider.execute

        def failing_execute(self, capability: str, payload: dict, *, auth, connection, context):
            if capability == "search_messages":
                raise RuntimeError("Simulated provider failure")
            return original_execute(
                self, capability, payload, auth=auth, connection=connection, context=context
            )

        monkeypatch.setattr(email_module.EmailProvider, "execute", failing_execute)

        try:
            mgr.create(
                company_id=company.id,
                integration_id=integration.id,
                capability="search_messages",
                payload={"query": "test"},
                connection_id=connection.id,
                idempotency_key="retry-fail-1",
            )
            raise AssertionError("Failed search must surface as ExternalActionError")
        except ExternalActionError as exc:
            assert exc.status == "failed"

        # Restore the provider — the same key may now run (prior status FAILED
        # is not a terminal-success duplicate) and should recover.
        monkeypatch.setattr(email_module.EmailProvider, "execute", original_execute)

        action = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="search_messages",
            payload={"query": "test"},
            connection_id=connection.id,
            idempotency_key="retry-fail-1",
        )
        assert action.status.value == "succeeded"

        attempts = (
            db.query(ExternalActionAttempt)
            .filter(ExternalActionAttempt.action_id == action.id)
            .all()
        )
        assert len(attempts) >= 1


class TestAttemptJournal:
    def test_success_journals_an_attempt(self, db: Session) -> None:
        from app.db.models.external import ExternalActionAttempt
        from app.external.action import ExternalActionManager
        from app.startup.autonomy import AutonomyService

        company = _company(db)
        AutonomyService(db).set_policy(company.id, allow_matrix={"external_action": "allow"})
        integration, connection = _email_setup(db, company.id)

        mgr = ExternalActionManager(db)
        action = mgr.create(
            company_id=company.id,
            integration_id=integration.id,
            capability="search_messages",
            payload={"query": "test"},
            connection_id=connection.id,
        )
        assert action.status.value == "succeeded"

        attempts = (
            db.query(ExternalActionAttempt)
            .filter(ExternalActionAttempt.action_id == action.id)
            .all()
        )
        assert len(attempts) == 1
        assert attempts[0].attempt_number == 1
        assert attempts[0].status == "succeeded"
