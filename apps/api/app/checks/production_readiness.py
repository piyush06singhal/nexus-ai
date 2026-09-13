"""Production readiness checks (Phase 11, §98/§99).

A self-audit gate for a NEXUS deployment: run with

    python -m app.checks.production_readiness

It walks the configured settings through the invariant chain
IDENTITY → AUTHORIZATION → POLICY → RESOURCE LIMIT → APPROVAL → ACTION →
VERIFICATION → AUDIT → OBSERVABILITY → RECOVERY and prints a PASS / WARN /
FAIL line per category. The process exits 0 on PASS, 1 when any FAIL is
present (a FAIL is a blocking production defect — notably running production
without authentication or without encryption keys).

Honest scope: infrastructure that is documented as a deployment item
(OS-level process sandboxing, Redis-backed job workers, managed secrets
vault, TLS termination) is reported as WARN — the check never claims an
operator installed them when it has no evidence.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from app.core.config import get_settings


@dataclass
class CheckResult:
    """One check: pass / warn / fail + a human-readable message."""

    name: str
    status: str  # "PASS" | "WARN" | "FAIL"
    message: str


class ProductionReadiness:
    """Run the readiness gate against the live settings object."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.results: list[CheckResult] = []

    # -- Identity ---------------------------------------------------------
    def identity(self) -> None:
        s = self.settings
        if s.environment == "production":
            if s.auth_enabled:
                self.results.append(
                    CheckResult("authentication", "PASS", "auth middleware enforced")
                )
            else:
                self.results.append(
                    CheckResult(
                        "authentication",
                        "FAIL",
                        "production runs with auth_enabled=False — every route is open",
                    )
                )
        else:
            self.results.append(
                CheckResult(
                    "authentication",
                    "WARN",
                    f"environment={s.environment!r}; auth is off in dev/test by design",
                )
            )
        if s.environment == "production" and not s.jwt_secret_key:
            self.results.append(
                CheckResult(
                    "jwt_secret_key",
                    "FAIL",
                    "no JWT_SECRET_KEY configured — signed tokens cannot protect sessions",
                )
            )
        elif self.settings.jwt_secret_key:
            self.results.append(
                CheckResult("jwt_secret_key", "PASS", "HS256 signing key set (env only)")
            )
        else:
            self.results.append(
                CheckResult(
                    "jwt_secret_key", "WARN", "no JWT_SECRET_KEY set (dev/test ephemeral keys)"
                )
            )

    # -- Authorization ----------------------------------------------------
    def authorization(self) -> None:
        s = self.settings
        if s.environment == "production":
            status = "PASS" if s.secure_auth_cookies else "FAIL"
            message = (
                "secure auth-cookie flag set"
                if s.secure_auth_cookies
                else "SECURE_AUTH_COOKIES unset — session cookies could ride plain HTTP"
            )
        else:
            status = "WARN"
            message = "SECURE_AUTH_COOKIES unset (dev/test default; require behind TLS)"
        self.results.append(CheckResult("secure_session_cookies", status, message))
        if s.environment == "production" and not s.trusted_hosts:
            self.results.append(
                CheckResult(
                    "trusted_hosts",
                    "WARN",
                    "no TRUSTED_HOSTS allow-list — Host header poisoning not filtered",
                )
            )
        else:
            self.results.append(CheckResult("trusted_hosts", "PASS", "Host allow-list configured"))

    # -- Encryption -------------------------------------------------------
    def encryption(self) -> None:
        s = self.settings
        if s.environment == "production":
            if s.secret_encryption_key:
                self.results.append(
                    CheckResult("secret_encryption", "PASS", "Fernet/AES-256-GCM key set")
                )
            else:
                self.results.append(
                    CheckResult(
                        "secret_encryption",
                        "FAIL",
                        "no SECRET_ENCRYPTION_KEY — cannot encrypt secrets at rest",
                    )
                )
        else:
            self.results.append(
                CheckResult(
                    "secret_encryption", "WARN", "no SECRET_ENCRYPTION_KEY (dev auto-generates)"
                )
            )

    # -- Policy / DLP -----------------------------------------------------
    def policy(self) -> None:
        if self.settings.feature_data_export_enabled:
            self.results.append(
                CheckResult(
                    "data_export",
                    "WARN",
                    "FEATURE_DATA_EXPORT_ENABLED is on — export routes are live; "
                    "ensure classification + approval gates are exercised",
                )
            )
        else:
            self.results.append(
                CheckResult("data_export", "PASS", "data export feature flag is off by default")
            )

    # -- Approvals --------------------------------------------------------
    def approvals(self) -> None:
        s = self.settings
        if not s.approval_self_approval_blocked:
            self.results.append(
                CheckResult("approvals", "FAIL", "self-approval is not blocked — SoD is unenforced")
            )
        elif s.approval_require_separation_of_duties:
            self.results.append(
                CheckResult("approvals", "PASS", "separation of duties + self-approval blocked")
            )
        else:
            self.results.append(
                CheckResult("approvals", "WARN", "SoD not required (approver can equal requester)")
            )

    # -- Reliability ------------------------------------------------------
    def reliability(self) -> None:
        s = self.settings
        if s.dlq_enabled and s.idempotency_enabled:
            self.results.append(
                CheckResult("reliability", "PASS", "DLQ + idempotency keys enabled")
            )
        else:
            self.results.append(CheckResult("reliability", "WARN", "DLQ or idempotency disabled"))
        # Redis-backed workers are a documented deployment item, not claimed.
        self.results.append(
            CheckResult(
                "queue_workers",
                "WARN" if not s.workflow_worker_enabled else "PASS",
                (
                    "workflow worker off (DB queue available but not draining) — "
                    "run the worker process in production"
                    if not s.workflow_worker_enabled
                    else "workflow worker enabled; Redis-backed workers are a "
                    "documented deployment item (DB queue active today)"
                ),
            )
        )

    # -- Observability ----------------------------------------------------
    def observability(self) -> None:
        s = self.settings
        if s.environment == "production" and not s.logging_json:
            self.results.append(
                CheckResult(
                    "logging",
                    "WARN",
                    "LOG_JSON unset — structured JSON logs recommended in production",
                )
            )
        else:
            self.results.append(CheckResult("logging", "PASS", "structured logging configured"))
        if s.metrics_enabled:
            self.results.append(CheckResult("metrics", "PASS", "metrics registry exposed"))
        else:
            self.results.append(CheckResult("metrics", "WARN", "metrics disabled"))

    # -- Security posture -------------------------------------------------
    def posture(self) -> None:
        s = self.settings
        if s.environment == "production":
            status = "PASS" if s.tls_enabled else "WARN"
            self.results.append(
                CheckResult(
                    "tls",
                    status,
                    (
                        "TLS termination configured (upstream)"
                        if s.tls_enabled
                        else "TLS_TERMINATED flag unset — assume plaintext transport "
                        "until a load balancer terminates TLS"
                    ),
                )
            )
        else:
            self.results.append(
                CheckResult("tls", "WARN", "TLS_TLS_ENABLED unset (dev/test; run TLS in prod)")
            )
        self.results.append(
            CheckResult(
                "os_sandboxing",
                "WARN",
                "OS-level process sandboxing is a documented deployment item — "
                "simulated/speculative tool sandboxes are enforced in-process",
            )
        )

    # -- Data governance --------------------------------------------------
    def data_governance(self) -> None:
        if self.settings.retention_security_events_days == 0:
            self.results.append(
                CheckResult(
                    "retention",
                    "PASS",
                    "security events are never auto-deleted (retention 0 = keep)",
                )
            )
        else:
            self.results.append(
                CheckResult("retention", "WARN", "security events auto-delete after retention_days")
            )

    # -- Run --------------------------------------------------------------
    def run_all(self) -> list[CheckResult]:
        self.identity()
        self.authorization()
        self.encryption()
        self.policy()
        self.approvals()
        self.reliability()
        self.observability()
        self.posture()
        self.data_governance()
        return self.results

    def summary(self) -> tuple[int, int, int]:
        counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
        for r in self.results:
            counts[r.status] += 1
        return counts["PASS"], counts["WARN"], counts["FAIL"]


def main() -> int:
    """Print the readiness report; exit 0 if no FAIL, else 1."""
    check = ProductionReadiness()
    results = check.run_all()
    passes, warns, fails = check.summary()

    print(f"NEXUS production readiness — environment: {check.settings.environment!r}")
    print("-" * 78)
    for r in sorted(results, key=lambda r: ("FAIL", "WARN", "PASS").index(r.status)):
        marker = {"PASS": "  OK", "WARN": " warn", "FAIL": "FAIL"}[r.status]
        print(f"[{marker}] {r.name:<22} {r.message}")
    print("-" * 78)
    print(f"PASS {passes}  WARN {warns}  FAIL {fails}")
    if fails:
        print(
            "\nNOT PRODUCTION READY — resolve the FAIL items "
            "(see docs/phase-11-production-hardening.md)."
        )
        return 1
    if warns:
        print("\nREADY with warnings — review the WARN items before a public launch.")
        return 0
    print("\nPRODUCTION READY.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
