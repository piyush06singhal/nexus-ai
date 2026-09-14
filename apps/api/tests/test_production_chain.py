"""Production-mode chain test — auth + rate-limit + observability, end to end.

Everything hardened already exists but is *gated off by default* (dev/demo runs
open). This test flips the production switches on and proves the shipped chain
actually enforces: token gate (401), login minting a working token, RBAC
authorization deny/allow, rate-limit lockout (429), observability counters, and
security-event recording on a failed login.

These tests run with ``auth_enabled``/``rate_limit_enabled`` toggled *per-test*
(monkeypatch) so the Phase 0–10 suite (auth off) stays untouched — the same
convention as ``test_security_phase11.py``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session as SASession

from app.core.config import settings
from app.db.session import get_db


@pytest.fixture
def production(monkeypatch):
    """Production-mode settings: auth + rate limiting + metrics all on."""
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    return settings


@pytest.fixture
def prod_client(db_engine, production):
    """TestClient with auth+rate-limit on, bound to the SQLite engine.

    A dedicated app instance keeps the rate-limit deques private to this test
    so it neither contaminates nor inherits the shared app's middleware state
    (which other tests assume is empty within their measurement windows).
    """
    from app.main import create_app

    def override_get_db():
        with SASession(bind=db_engine, expire_on_commit=False) as session:
            yield session

    fresh_app = create_app()
    fresh_app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(fresh_app) as client:
            yield client, db_engine
    finally:
        fresh_app.dependency_overrides.clear()


def _make_user(db, email="ops@nexus.test", roles=("company_admin",)):
    """Create an identity + user + roles; return (identity, user)."""
    from app.security.authorization import RoleService
    from app.security.identity import UserAccountManager

    RoleService(db).seed_system_roles()
    manager = UserAccountManager(db)
    identity, user = manager.create_user(
        email=email,
        display_name=email.split("@")[0],
        password="sup3r-secret-test",
    )
    RoleService(db).assign_roles_to_identity(identity.id, list(roles))
    db.commit()
    return identity, user


LOGIN = {"email": "ops@nexus.test", "password": "sup3r-secret-test"}


def test_production_chain_end_to_end(prod_client):
    client, db_engine = prod_client

    with SASession(bind=db_engine) as db:
        _make_user(db)

    # 1. Unauthenticated request → 401 auth_required envelope.
    resp = client.get("/api/v1/companies")
    assert resp.status_code == 401, resp.text
    assert resp.json()["error"]["code"] == "auth_required"

    # 2. Login mints a working token (whitelisted, no token needed).
    resp = client.post("/api/v1/auth/login", json=LOGIN)
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    bearer = {"Authorization": f"Bearer {token}"}

    # 3. Authed request → 200; identity attached.
    resp = client.get("/api/v1/auth/session", headers=bearer)
    assert resp.status_code == 200, resp.text
    assert resp.json()["identity"]["kind"] == "user"

    authed = client.get("/api/v1/companies", headers=bearer)
    assert authed.status_code == 200, authed.text

    # 4. RBAC chain: employee lacks access.manage → DENY; platform_admin holds
    #    the wildcard (all permissions) → ALLOW.
    from app.core.errors import PermissionDeniedError
    from app.security.authorization import AuthorizationService

    with SASession(bind=db_engine) as db:
        employee, _ = _make_user(db, email="emp@nexus.test", roles=("employee",))
        admin, _ = _make_user(db, email="admin@nexus.test", roles=("platform_admin",))

        svc = AuthorizationService(db)
        with pytest.raises(PermissionDeniedError):
            svc.require(employee.id, "access.manage")
        # No exception = allowed.
        svc.require(admin.id, "access.manage")

    # 5. Wrong password → rejected + a recorded AUTH_FAILURE security event.
    #    The codebase maps failed login to 403 (invalid_credentials) to avoid
    #    distinguishing existing from unknown accounts — assert the real contract.
    from app.db.models.security import SecurityEvent, SecurityEventCategory

    with SASession(bind=db_engine) as db:
        before = len(list(db.scalars(select(SecurityEvent))))
    bad = client.post(
        "/api/v1/auth/login",
        json={"email": "ops@nexus.test", "password": "wrong-password"},
    )
    assert bad.status_code == 403, bad.text
    assert bad.json()["error"]["code"] == "invalid_credentials"
    with SASession(bind=db_engine) as db:
        events = list(
            db.scalars(
                select(SecurityEvent).where(
                    SecurityEvent.category == SecurityEventCategory.AUTH_FAILURE.value
                )
            )
        )
        assert len(events) == before + 1

    # 6. Observability: the metrics snapshot exposes request counters after all
    #    that traffic.
    resp = client.get("/api/v1/system/metrics", headers=bearer)
    assert resp.status_code == 200, resp.text
    counters = resp.json().get("counters", {})
    assert any(k.startswith("request.") and k.endswith(".total") for k in counters)
    assert any(".status.401" in k or ".status.403" in k or ".status.429" in k for k in counters)


def test_rate_limit_lockout(db_engine, production, monkeypatch):
    """Rate limiter enforces the tight /auth cap once enabled.

    A dedicated app instance (fresh middleware deque) keeps the bucket empty:
    exactly one login is allowed below the cap, and the next is locked out with
    a 429 ``rate_limited`` envelope.
    """
    from app.main import create_app

    def override_get_db():
        with SASession(bind=db_engine, expire_on_commit=False) as session:
            yield session

    fresh_app = create_app()
    fresh_app.dependency_overrides[get_db] = override_get_db
    with SASession(bind=db_engine) as db:
        _make_user(db)

    with TestClient(fresh_app) as client:
        # Within-cap request → allowed.
        ok = client.post("/api/v1/auth/login", json=LOGIN)
        assert ok.status_code == 200, ok.text

        # Tighten the auth cap below the current window usage → next is 429.
        from app.core.config import settings as cfg

        monkeypatch.setattr(cfg, "rate_limit_auth_per_minute", 1)
        blocked = client.post("/api/v1/auth/login", json=LOGIN)
        assert blocked.status_code == 429, blocked.text
        assert blocked.json()["error"]["code"] == "rate_limited"
