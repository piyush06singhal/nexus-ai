"""Seed the NEXUS Phase 10 external-operations demo (External Research §68,
Development Operations §69, Email Approval §70).

Three deterministic, governed scenarios, all through the real Phase 10
services and the mock providers (no network, no paid services):

  1. External Research — a market-research employee drives a bounded browser
     session through the fixture catalog (open page → extract links → visit
     competitor product pages → extract text). Every observation is labelled
     ``EXTERNAL_UNTRUSTED_CONTENT`` (prompt-injection boundary, §65/§66) and the
     extracted findings are stored as semantic memories. (§68)
  2. Development Operations — a developer employee creates an issue on the mock
     dev platform through ``ExternalActionManager``; the MEDIUM write is
     allow-listed by an integration policy, executes, and the built-in provider
     read-back verification confirms the created resource. (§69)
  3. Email Approval — a marketing employee drafts a campaign email (MEDIUM,
     allow-listed) then attempts to send it. ``send_message`` is HIGH and
     intrinsically approval-required, so the funnel parks it with an
     ``EXTERNAL_ACTION_APPROVAL`` gate; the operator approves; replaying with
     the approved gate id executes the send exactly once (Rule 12), and the
     read-back verification confirms the sent message. (§70)

Everything is journaled (``external_actions``) and audited (OrgEventLogger),
and each scenario stores memory candidates through the Phase 4 MemoryService.
Credentials are reference-only: a one-shot value supplied at connect time is
used transiently and never persisted.

Idempotent: re-running reuses the same company/integrations/connections and
skips already-completed actions (duplicate SUCCEEDED is refused by the funnel).

Run from ``apps/api``:
    .venv/bin/python -m scripts.seed_external_ops [--reset]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

sys.path.insert(0, ".")

import app.db.models  # noqa: E402,F401  (register every model on Base.metadata)
from app.db.session import Base, SessionLocal  # noqa: E402

DEMO_COMPANY_NAME = "NEXUS External Operations"

# One-shot secrets for the demo connections (never persisted — see credential.py).
EMAIL_SECRET = "demo-mail-secret-7f3a9c1e"
DEV_SECRET = "demo-dev-secret-0b5d8a4c"

FIXTURE_HOME = "https://discovery.nexus.test/"
FIXTURE_ALPHA = "https://discovery.nexus.test/products/alpha"
FIXTURE_BETA = "https://discovery.nexus.test/products/beta"
FIXTURE_COMPARE = "https://discovery.nexus.test/compare"

# Stable idempotency keys — once an action SUCCEEDED under one of these, re-runs
# skip it (IdempotencyGuard refuses a duplicate SUCCEEDED).
DEV_ISSUE_KEY = "demo2-dev-issue"
DRAFT_KEY = "demo3-campaign-draft"
SEND_KEY = "demo3-campaign-send"


def _slugify(name: str) -> str:
    return name.lower().replace(" ", "-")


def _loads(raw: Any) -> Any:
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


def _get_or_create_company(db: Session, name: str) -> Any:
    from app.company.manager import CompanyManager
    from app.db.models.company import Company

    existing = db.scalar(select(Company).where(Company.slug == _slugify(name)))
    if existing is not None:
        return existing
    return CompanyManager(db).create(name=name, description="Phase 10 external-ops demo.")


def _get_or_create_employee(
    db: Session, *, name: str, role: str, department: str, tools: list[str]
) -> Any:
    """Create an AI employee (backing agent auto-provisioned), reuse if present."""
    # Reuse by name; EmployeeManager has no list_, so query the model directly.
    from app.db.models.employee import AIEmployee
    from app.employee.manager import EmployeeManager

    row = db.scalar(select(AIEmployee).where(AIEmployee.name == name))
    if row is not None:
        return row
    return EmployeeManager(db).create(
        name=name,
        role=role,
        department=department,
        tools=tools,
        responsibilities=[f"{role} for the {department} team"],
    )


def _enable_external_actions(db: Session, company_id: UUID) -> None:
    """A governed company profile: low/medium-risk external actions auto-run,
    HIGH/irreversible ones stay behind an approval gate (autonomy decision)."""
    from app.startup.autonomy import AutonomyService

    AutonomyService(db).set_policy(
        company_id, allow_matrix={"external_action": "allow"}, actor="demo"
    )


def _get_or_create_integration(
    db: Session,
    *,
    company_id: UUID,
    provider: str,
    name: str,
    secret_value: str,
    env_hint: str,
) -> Any:
    """Reuse the company's existing integration+connection for *provider*."""
    from app.db.models.external import IntegrationConnection, IntegrationStatus
    from app.external.integration import IntegrationService

    svc = IntegrationService(db)
    for integration in svc.list_(company_id):
        if integration.provider == provider:
            connection = db.scalar(
                select(IntegrationConnection).where(
                    IntegrationConnection.company_id == company_id,
                    IntegrationConnection.integration_id == integration.id,
                    IntegrationConnection.status == IntegrationStatus.CONNECTED.value,
                )
            )
            if connection is None:
                raise RuntimeError(f"{provider} integration exists without a connection")
            return integration, connection
    integration = svc.create(company_id=company_id, provider=provider, name=name)
    connection = svc.connect(
        company_id=company_id,
        integration_id=integration.id,
        auth_method="api_key",
        secret_value=secret_value,
        env_var_hint=env_hint,
        scopes=["email:send"] if provider == "email" else ["repo:write", "repo:read"],
        permissions=["email:send"] if provider == "email" else ["dev:write", "dev:read"],
    )
    return integration, connection


def _allowlist_capability(
    db: Session,
    *,
    company_id: UUID,
    integration_id: UUID,
    capability_pattern: str,
) -> None:
    """Add a company integration policy that lets a specific write auto-run.

    The classifier escalates MEDIUM write capabilities (e.g. ``create_draft``,
    ``create_issue``) to HIGH by intent; this explicit policy override returns
    the effective risk to LOW so the governed demo flows don't need a gate per
    write — HIGH/irreversible send_message stays gated regardless.
    """
    from app.db.models.external import IntegrationPolicy, RiskLevel, ScopeType

    existing = db.scalar(
        select(IntegrationPolicy).where(
            IntegrationPolicy.company_id == company_id,
            IntegrationPolicy.integration_id == integration_id,
            IntegrationPolicy.capability_pattern == capability_pattern,
            IntegrationPolicy.enabled.is_(True),
        )
    )
    if existing is not None:
        return
    db.add(
        IntegrationPolicy(
            company_id=company_id,
            integration_id=integration_id,
            scope_type=ScopeType.COMPANY,
            capability_pattern=capability_pattern,
            risk_level_override=RiskLevel.LOW,
            allowed=True,
            require_approval=False,
            enabled=True,
        )
    )
    db.commit()


def _already_succeeded(
    db: Session, *, company_id: UUID, integration_id: UUID, capability: str, key: str
) -> bool:
    from app.external.idempotency import IdempotencyGuard

    prior = IdempotencyGuard(db).find_terminal(
        company_id=company_id,
        integration_id=integration_id,
        capability=capability,
        idempotency_key=key,
    )
    return prior is not None and prior.status.value == "succeeded"


def _prior_result_id(
    db: Session, *, company_id: UUID, integration_id: UUID, capability: str, key: str
) -> str | None:
    """Re-read the created-resource id from a prior succeeded journal row."""
    from app.external.idempotency import IdempotencyGuard

    prior = IdempotencyGuard(db).find_terminal(
        company_id=company_id,
        integration_id=integration_id,
        capability=capability,
        idempotency_key=key,
    )
    if prior is None or not prior.result:
        return None
    result = _loads(prior.result) or {}
    # Result may be {capability: {...}} or the resource id directly.
    for value in result.values():
        if isinstance(value, dict) and value.get("id"):
            return str(value["id"])
    return None


def _store_memory(
    db: Session,
    *,
    namespace: str,
    content: str,
    summary: str,
    metadata_json: dict[str, Any] | None = None,
) -> Any:
    """Store a semantic memory candidate through the Phase 4 MemoryService."""
    from app.db.models.memory import MemoryOwnerType, MemorySourceType, MemoryType
    from app.schemas.memory import MemoryCreate
    from app.services.memory_service import MemoryService

    return MemoryService(db).create(
        MemoryCreate(
            namespace=namespace,
            type=MemoryType.SEMANTIC,
            content=content,
            summary=summary,
            owner_type=MemoryOwnerType.SYSTEM,
            source_type=MemorySourceType.TOOL_OUTPUT,
            importance=0.6,
            confidence=0.9,
            metadata_json=metadata_json,
        )
    )


def _approve_gate(db: Session, company_id: UUID, gate_id: UUID) -> Any:
    from app.startup.gates import ApprovalGateManager

    return ApprovalGateManager(db).approve(company_id, gate_id, approver_id=None)


# ── Demo 1 — External Research (§68) ────────────────────────────────────────


def _demo_external_research(db: Session, *, company_id: UUID, employee: Any) -> dict:
    from app.db.models.external import BrowserActionType
    from app.external.browser.session import BrowserSessionManager

    print("\n=== Demo 1 — External Research (§68) ===")
    print(f"  employee    : {employee.name} ({employee.role})")
    sessions = BrowserSessionManager(db)
    session = sessions.create(
        company_id=company_id,
        employee_id=employee.id,
        allowed_domains=["discovery.nexus.test"],
    )
    sid = session.id
    print(f"  session     : {sid} (simulated browser)")

    def act(action_type: str, **kw: Any) -> dict:
        row = sessions.action(company_id, sid, action_type=action_type, **kw)
        return _loads(row.result) or {}

    # 1. Open the research homepage and survey the catalogue.
    home = act(BrowserActionType.OPEN_PAGE.value, target={"url": FIXTURE_HOME})
    print(f"  opened      : {home['title']} @ {home['url']}")
    links = act(BrowserActionType.EXTRACT_LINKS.value)
    print(f"  links       : {len(links.get('links', []))} found on this page")

    # 2. Visit the two competitor product pages and capture their positioning.
    findings: list[dict[str, str]] = []
    for product, page_url in (("AlphaSync", FIXTURE_ALPHA), ("BetaConnect", FIXTURE_BETA)):
        act(BrowserActionType.OPEN_PAGE.value, target={"url": page_url})
        text = act(BrowserActionType.EXTRACT_TEXT.value).get("text", "")
        first_line = text.split(".")[0] if text else ""
        findings.append({"product": product, "summary": first_line})
        print(f"  page        : {product}: {first_line}")

    # 3. The malformed/navigation capture ends on the comparison page.
    act(BrowserActionType.OPEN_PAGE.value, target={"url": FIXTURE_COMPARE})
    compare = act(BrowserActionType.EXTRACT_TEXT.value).get("text", "")
    print(f"  comparison  : {compare.split('.')[0]}.")

    # 4. Observations carry the untrusted-content marker (prompt-injection
    #    bounday — never treated as instruction, §65/§66).
    observations = sessions.observations(company_id, sid)
    labelled = observations[-1] if observations else None
    print(
        f"  observations: {len(observations)} recorded; content_type={labelled.content_type.value}"
    )  # noqa: E501

    # 5. Persist findings as semantic memories (Phase 4 MemoryService).
    for f in findings:
        _store_memory(
            db,
            namespace="external_research",
            content=f"{f['product']}: {f['summary']}",
            summary=f"{f['product']} competitive positioning note",
            metadata_json={"source": "browser", "employee_id": str(employee.id)},
        )
    _store_memory(
        db,
        namespace="external_research",
        content=f"Competitive comparison: {compare}",
        summary="Cross-vendor comparison note from external research",
        metadata_json={"source": "browser", "employee_id": str(employee.id)},
    )
    print(f"  memory      : {len(findings) + 1} semantic memories stored")

    # 6. Terminate the bounded session.
    sessions.terminate(company_id, sid)
    print("  ended       : session terminated (action budget respected)")
    return {
        "session_id": str(sid),
        "pages": [FIXTURE_HOME, FIXTURE_ALPHA, FIXTURE_BETA, FIXTURE_COMPARE],
        "findings": findings,
        "observations": len(observations),
    }


# ── Demo 2 — Development Operations (§69) ───────────────────────────────────


def _demo_development_ops(db: Session, *, company_id: UUID, employee: Any) -> dict:
    from app.db.models.external import ExternalActionStatus
    from app.external.action import ExternalActionManager

    integration, connection = _get_or_create_integration(
        db,
        company_id=company_id,
        provider="development",
        name="Development",
        secret_value=DEV_SECRET,
        env_hint="INTEGRATION_DEVELOPMENT_API_KEY",
    )
    _allowlist_capability(
        db, company_id=company_id, integration_id=integration.id, capability_pattern="create_issue"
    )

    print("\n=== Demo 2 — Development Operations (§69) ===")
    print(f"  employee    : {employee.name} ({employee.role})")
    print(f"  integration : {integration.provider} ({integration.id})")

    mgr = ExternalActionManager(db)
    if _already_succeeded(
        db,
        company_id=company_id,
        integration_id=integration.id,
        capability="create_issue",
        key=DEV_ISSUE_KEY,
    ):
        print("  create_issue: already succeeded — skipping (idempotent re-run)")
    else:
        action = mgr.create(
            company_id=company_id,
            integration_id=integration.id,
            capability="create_issue",
            payload={
                "repository": "nexus-core",
                "title": "Add rate limiting to the external HTTP client",
                "body": "Imported from the Phase 10 development-operations demo.",
                "labels": ["security", "phase-10"],
            },
            action_type="create_issue",
            connection_id=connection.id,
            employee_id=employee.id,
            idempotency_key=DEV_ISSUE_KEY,
        )
        assert action.status == ExternalActionStatus.SUCCEEDED
        issue = _loads(action.result).get("issue", {})
        verification = _loads(action.verification) or {}
        print(
            f"  create_issue: #{issue.get('number')} '{issue.get('title')[:52]}' "
            f"[{action.status.value}]"
        )
        print(
            f"  verification: {verification.get('confirmed_via')} "
            f"verified={verification.get('verified')}"
        )

        # Read-back verification of the persisted issue state.
        read_action = mgr.create(
            company_id=company_id,
            integration_id=integration.id,
            capability="get_issue",
            payload={"issue_id": issue.get("id")},
            action_type="get_issue",
            connection_id=connection.id,
            employee_id=employee.id,
        )
        got = _loads(read_action.result).get("issue", {})
        print(f"  get_issue   : read back state='{got.get('state')}' — matches")
        _store_memory(
            db,
            namespace="development_ops",
            content=f"Issue #{issue.get('number')} '{issue.get('title')}' created on "
            f"nexus-core and verified.",
            summary="Governed dev-platform issue created + verified",
            metadata_json={
                "integration": integration.provider,
                "issue_id": issue.get("id"),
                "repository": "nexus-core",
                "employee_id": str(employee.id),
            },
        )
        print("  memory      : project-state memory stored")

        # Project state update (journal already holds it).
        return {
            "issue_id": issue.get("id"),
            "number": issue.get("number"),
            "action_status": action.status.value,
        }

    return {"skipped": True}


# ── Demo 3 — Email Approval (§70) ───────────────────────────────────────────


def _demo_email_approval(db: Session, *, company_id: UUID, employee: Any) -> dict:
    from app.db.models.external import ExternalActionStatus
    from app.external.action import ExternalActionManager

    integration, connection = _get_or_create_integration(
        db,
        company_id=company_id,
        provider="email",
        name="Email",
        secret_value=EMAIL_SECRET,
        env_hint="INTEGRATION_EMAIL_API_KEY",
    )
    _allowlist_capability(
        db, company_id=company_id, integration_id=integration.id, capability_pattern="create_draft"
    )

    print("\n=== Demo 3 — Email Approval (§70) ===")
    print(f"  employee    : {employee.name} ({employee.role})")
    print(f"  integration : {integration.provider} ({integration.id})")

    mgr = ExternalActionManager(db)

    # 1. Draft — MEDIUM write, allow-listed, auto-run (idempotent).
    if _already_succeeded(
        db,
        company_id=company_id,
        integration_id=integration.id,
        capability="create_draft",
        key=DRAFT_KEY,
    ):
        draft_id = _prior_result_id(
            db,
            company_id=company_id,
            integration_id=integration.id,
            capability="create_draft",
            key=DRAFT_KEY,
        )
        print(f"  draft       : {draft_id} already succeeded — skipping (idempotent re-run)")
    else:
        draft = mgr.create(
            company_id=company_id,
            integration_id=integration.id,
            capability="create_draft",
            payload={
                "to": ["customers@example.com", "prospects@example.com"],
                "subject": "Q4 campaign — early access",
                "body": "Early access to our governed mirror platform is now open.",
            },
            action_type="create_draft",
            connection_id=connection.id,
            employee_id=employee.id,
            idempotency_key=DRAFT_KEY,
        )
        draft_id = _loads(draft.result).get("draft", {}).get("id")
        print(f"  draft       : {draft_id} [{draft.status.value}] (MEDIUM write, auto-run)")

    # 2. Send — HIGH + intrinsically approval-required → parks for a human gate.
    if _already_succeeded(
        db,
        company_id=company_id,
        integration_id=integration.id,
        capability="send_message",
        key=SEND_KEY,
    ):
        print("  send        : already succeeded — skipping (idempotent re-run)")
        return {"skipped": True, "draft_id": draft_id}

    send = mgr.create(
        company_id=company_id,
        integration_id=integration.id,
        capability="send_message",
        payload={
            "to": ["customers@example.com", "prospects@example.com"],
            "subject": "Q4 campaign — early access",
            "body": "Early access to our governed mirror platform is now open.",
            "draft_id": draft_id,
        },
        action_type="send_message",
        connection_id=connection.id,
        employee_id=employee.id,
        idempotency_key=SEND_KEY,
    )
    if send.status == ExternalActionStatus.AWAITING_APPROVAL:
        gate_id = send.approval_gate_id
        print(f"  send        : parked [{send.status.value}] — HIGH + approval-required")
        print(f"  gate        : EXTERNAL_ACTION_APPROVAL {gate_id}")
        assert gate_id is not None

        # Human-in-the-loop: the operator reviews and approves the gate.
        _approve_gate(db, company_id, gate_id)
        print("  approval    : operator approved the gate")

        # Replay with the approved gate id → executes exactly once (§8).
        sent = mgr.create(
            company_id=company_id,
            integration_id=integration.id,
            capability="send_message",
            payload={
                "to": ["customers@example.com", "prospects@example.com"],
                "subject": "Q4 campaign — early access",
                "body": "Early access to our governed mirror platform is now open.",
                "draft_id": draft_id,
            },
            action_type="send_message",
            connection_id=connection.id,
            employee_id=employee.id,
            idempotency_key=SEND_KEY,
            approved_gate_id=gate_id,
        )
        assert sent.status == ExternalActionStatus.SUCCEEDED
        message = _loads(sent.result).get("message", {})
        verification = _loads(sent.verification) or {}
        print(f"  send        : {message.get('status')} — message {message.get('id')}")
        print(
            f"  verification: {verification.get('confirmed_via')} "
            f"verified={verification.get('verified')}"
        )
        print(f"  gate-used   : {sent.approval_gate_id == gate_id} — consumed (Rule 12)")

        # A second send with the same (now-consumed/duplicated) key is refused.
        try:
            mgr.create(
                company_id=company_id,
                integration_id=integration.id,
                capability="send_message",
                payload={
                    "to": ["customers@example.com"],
                    "subject": "Duplicate attempt",
                    "body": "Should never send.",
                },
                action_type="send_message",
                connection_id=connection.id,
                employee_id=employee.id,
                idempotency_key=SEND_KEY,
            )
            print("  dup         : UNEXPECTED — duplicate send was allowed")
        except Exception as exc:  # noqa: BLE001 - expected refusal
            reason = str(exc)
            print(f"  dup         : refused ({reason[:60]})")

        _store_memory(
            db,
            namespace="marketing_campaign",
            content=f"Q4 early-access campaign sent to 2 recipients under an approved gate "
            f"(draft {draft_id}).",
            summary="Email campaign deployed through governed approval",
            metadata_json={
                "integration": integration.provider,
                "draft_id": draft_id,
                "approval_gate_id": str(gate_id),
                "employee_id": str(employee.id),
            },
        )
        print("  memory      : campaign memory stored")
        return {
            "draft_id": draft_id,
            "gate_id": str(gate_id),
            "message": message.get("id"),
        }

    # Already completed on a previous run.
    print("  send        : already succeeded — skipping (idempotent re-run)")
    return {"skipped": True, "draft_id": draft_id}


# ── main ────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the NEXUS Phase 10 external-ops demo.")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate the demo company")
    args = parser.parse_args()

    Base.metadata.create_all(bind=SessionLocal.kw["bind"])

    with SessionLocal() as db:
        if args.reset:
            from app.db.models.company import Company

            existing = db.scalar(select(Company).where(Company.slug == _slugify(DEMO_COMPANY_NAME)))
            if existing is not None:
                db.delete(existing)
                db.commit()

        company = _get_or_create_company(db, DEMO_COMPANY_NAME)
        company_id = company.id
        _enable_external_actions(db, company_id)

        researcher = _get_or_create_employee(
            db,
            name="Vera Williams",
            role="Market Research Analyst",
            department="Research",
            tools=["browser.session.action"],
        )
        developer = _get_or_create_employee(
            db,
            name="Theo Park",
            role="Developer",
            department="Development",
            tools=["development.create_issue", "development.get_issue"],
        )
        marketer = _get_or_create_employee(
            db,
            name="Maya Chen",
            role="Campaign Manager",
            department="Marketing",
            tools=["email.send_message"],
        )

        print("=== NEXUS Phase 10 external-operations demo ===")
        print(f"company     : {company.name} ({company.id})")

        research = _demo_external_research(db, company_id=company_id, employee=researcher)
        dev = _demo_development_ops(db, company_id=company_id, employee=developer)
        email = _demo_email_approval(db, company_id=company_id, employee=marketer)

        _print_final_summary(db, company_id, research, dev, email)


def _print_final_summary(
    db: Session, company_id: UUID, research: dict, dev: dict, email: dict
) -> None:
    from app.db.models.external import ExternalAction
    from app.external.action import ExternalActionManager
    from app.external.browser.session import BrowserSessionManager

    journal = ExternalActionManager(db).list_(company_id, limit=200)
    counts: dict[str, int] = {}
    for row in journal:
        counts[row.status.value] = counts.get(row.status.value, 0) + 1
    browser = BrowserSessionManager(db).list_(company_id)

    print("\n=== NEXUS Phase 10 external-operations demo seeded ===")
    print(f"company_id   : {company_id}")
    print(
        f"external actions: {len(journal)} -> "
        f"{', '.join(f'{k}:{v}' for k, v in sorted(counts.items()))}"
    )
    print(f"browser sessions: {len(browser)} -> {[s.status.value for s in browser]}")
    print(
        f"completed    : Research session={research.get('session_id')} "
        f"| Dev issue={dev.get('number')} | Email send={email.get('message')} "
        f"(gate {email.get('gate_id')})"
    )

    # Guard against leaks: assert the demo ever used one-shot secrets nowhere in
    # the payloads stored in the journal.
    for row in journal:
        stored = f"{row.input or ''} {row.result or ''}"
        assert EMAIL_SECRET not in stored, "email secret leaked into the journal"
        assert DEV_SECRET not in stored, "dev secret leaked into the journal"

    # Final audit snapshot.
    from app.db.models.company import OrgEvent

    events = db.scalar(select(OrgEvent).where(OrgEvent.company_id == company_id))
    action_rows = (
        db.execute(select(ExternalAction).where(ExternalAction.company_id == company_id))
        .scalars()
        .all()
    )
    print(
        f"audit        : {sum(1 for _ in [events] if events)} event row(s); "
        f"{len(action_rows)} journal row(s) persisted"
    )
    print(
        "Verify with:\n"
        f"  curl localhost:8000/api/v1/integrations/{company_id}\n"
        f"  curl localhost:8000/api/v1/external-actions/{company_id}/dashboard\n"
        f"  curl localhost:8000/api/v1/browser/sessions?company_id={company_id}\n"
        f"  curl localhost:8000/api/v1/autonomy/{company_id}/policy"
    )


if __name__ == "__main__":
    main()
