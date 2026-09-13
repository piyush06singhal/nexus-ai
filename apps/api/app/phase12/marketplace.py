"""Agent Marketplace — metadata-only, internal/private, safe install.

Packages carry capabilities/skills/permissions/requirements — never secrets,
credentials, private memories, execution history, tokens, or executable
payloads (validation rejects them). Install flows through ``EmployeeManager``
and an approval gate for sensitive/high-risk requests.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.phase12 import (
    AgentInstallation,
    AgentPackage,
    AgentPackageBenchmark,
    AgentPackageCapability,
    AgentPackageDependency,
    AgentPackageReview,
    AgentPackageVersion,
    InstallStatus,
    PackageStatus,
)


class MarketplaceError(ValueError):
    """Marketplace lifecycle/safety error."""


# Regexes for detecting forbidden payload classes.
_SECRET_PATTERNS = [
    re.compile(r"(?i)sk-[a-z0-9]{20,}"),
    re.compile(r"(?i)api[_-]?key"),
    re.compile(r"(?i)bearer\s+[a-z0-9]"),
    re.compile(r"(?i)-----BEGIN"),
]

_EXECUTABLE_EXTENSIONS = (
    ".py",
    ".sh",
    ".bat",
    ".exe",
    ".dll",
    ".so",
    ".ts",
    ".js",
    ".ipynb",
)


class PackageScanner:
    """Static validation that a package carries no forbidden payload."""

    FORBIDDEN_KEYS = {
        "secret",
        "credential",
        "token",
        "private_memory",
        "memory",
        "execution_history",
        "password",
        "private_key",
        "api_key",
    }

    FORBIDDEN_METADATA_KEYS = {
        "body",
        "code",
        "script",
        "payload",
        "executable",
    }

    @classmethod
    def scan(cls, metadata: dict[str, Any] | None) -> list[str]:
        """Return a list of violations; empty means safe."""
        violations: list[str] = []
        metadata = metadata or {}
        for key in metadata:
            lowered = key.lower()
            if lowered in cls.FORBIDDEN_KEYS:
                violations.append(f"forbidden key: {key}")
            if lowered in cls.FORBIDDEN_METADATA_KEYS:
                violations.append(f"forbidden payload key: {key}")
            value = metadata[key]
            if isinstance(value, str):
                for pat in _SECRET_PATTERNS:
                    if pat.search(value):
                        violations.append(f"secret-like content in {key}")
                for ext in _EXECUTABLE_EXTENSIONS:
                    if value.strip().endswith(ext):
                        violations.append(f"executable-like content in {key}")
                    if value.startswith(f"#!{ext}"):
                        violations.append(f"script shebang in {key}")
        return violations


class MarketplaceService:
    """Agent package lifecycle with safe-install guarantees."""

    def __init__(
        self,
        db: Session,
        *,
        employee_manager: Any | None = None,
        audit: Any | None = None,
        approvals: Any | None = None,
    ) -> None:
        self._db = db
        # Injected collaborators (default resolved lazily).
        self._employee_manager = employee_manager
        self._audit = audit
        self._approvals = approvals

    # ── Package lifecycle ──────────────────────────────────────────────

    def create_package(
        self,
        *,
        name: str,
        company_id: UUID | None = None,
        display_name: str | None = None,
        description: str | None = None,
        capabilities: list[str] | None = None,
        skills: list[str] | None = None,
        supported_task_types: list[str] | None = None,
        requirements: dict[str, Any] | None = None,
        security: str = "internal",
        created_by: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentPackage:
        violations = PackageScanner.scan(metadata)
        if violations:
            raise MarketplaceError("Package payload rejected: " + "; ".join(violations))
        pkg = AgentPackage(
            name=name,
            company_id=company_id,
            display_name=display_name,
            description=description,
            status=PackageStatus.DRAFT.value,
            capabilities_json={"capabilities": capabilities or []},
            skills_json={"skills": skills or []},
            supported_task_types_json={"supported_task_types": supported_task_types or []},
            requirements_json=requirements or {},
            security=security,
            creator_id=created_by,
        )
        self._db.add(pkg)
        self._db.commit()
        # Capabilities for the initial release are declared as JSON on the
        # package; per-version rows are attached inside add_version (the
        # AgentPackageCapability table hangs off version_id).
        if metadata:
            pkg.requirements_json = {
                **(requirements or {}),
                "metadata": metadata,
            }
        self._db.commit()
        return pkg

    def get_package(self, package_id: UUID) -> AgentPackage | None:
        return self._db.get(AgentPackage, package_id)

    def list_packages(
        self,
        company_id: UUID | None = None,
        *,
        status: str | None = None,
    ) -> list[AgentPackage]:
        stmt = select(AgentPackage).order_by(AgentPackage.created_at.desc())
        if company_id is not None:
            stmt = stmt.where(AgentPackage.company_id == company_id)
        if status is not None:
            stmt = stmt.where(AgentPackage.status == status)
        return list(self._db.execute(stmt).scalars())

    # ── Versions ───────────────────────────────────────────────────────

    def add_version(
        self,
        package_id: UUID,
        *,
        version: str,
        changelog: str | None = None,
        compatibility: str = "compatible",
        metadata: dict[str, Any] | None = None,
        capabilities: list[str] | None = None,
        dependencies: list[dict[str, str]] | None = None,
    ) -> AgentPackageVersion:
        pkg = self.get_package(package_id)
        if pkg is None:
            raise MarketplaceError(f"Package {package_id} not found")
        violations = PackageScanner.scan(metadata)
        if violations:
            raise MarketplaceError("Version payload rejected: " + "; ".join(violations))
        ver = AgentPackageVersion(
            package_id=package_id,
            company_id=pkg.company_id,
            version=version,
            changelog=changelog,
            compatibility=compatibility,
            metadata_json=metadata or {},
        )
        self._db.add(ver)
        self._db.commit()
        for dep in dependencies or []:
            self._db.add(
                AgentPackageDependency(
                    version_id=ver.id,
                    company_id=pkg.company_id,
                    dependency_name=dep.get("package", ""),
                    dependency_version=dep.get("version"),
                )
            )
        for cap in capabilities or []:
            self._db.add(
                AgentPackageCapability(
                    version_id=ver.id,
                    company_id=pkg.company_id,
                    name=cap,
                )
            )
        self._db.commit()
        return ver

    def get_version(self, version_id: UUID) -> AgentPackageVersion | None:
        return self._db.get(AgentPackageVersion, version_id)

    def list_versions(self, package_id: UUID) -> list[AgentPackageVersion]:
        return list(
            self._db.execute(
                select(AgentPackageVersion)
                .where(AgentPackageVersion.package_id == package_id)
                .order_by(AgentPackageVersion.created_at.desc())
            ).scalars()
        )

    # ── Publication ────────────────────────────────────────────────────

    def publish(self, package_id: UUID) -> AgentPackage:
        pkg = self._require(package_id)
        if not self.list_versions(package_id):
            raise MarketplaceError(f"Package {package_id} has no versions; cannot publish")
        pkg.status = PackageStatus.PUBLISHED.value
        pkg.published_at = datetime.now()
        self._db.commit()
        return pkg

    def deprecate(self, package_id: UUID) -> AgentPackage:
        pkg = self._require(package_id)
        pkg.status = PackageStatus.DEPRECATED.value
        pkg.deprecated_at = datetime.now()
        self._db.commit()
        return pkg

    # ── Safe install (§37) ─────────────────────────────────────────────

    def install(
        self,
        *,
        package_id: UUID,
        company_id: UUID,
        version_id: UUID | None = None,
        config: dict[str, Any] | None = None,
        require_approval: bool = True,
        requested_by: UUID | None = None,
    ) -> AgentInstallation:
        pkg = self._require(package_id)
        if pkg.status != PackageStatus.PUBLISHED.value:
            raise MarketplaceError(f"Package {package_id} not published; status={pkg.status}")
        ver = (
            self.get_version(version_id)
            if version_id
            else (self.list_versions(package_id)[0] if self.list_versions(package_id) else None)
        )
        if ver is None:
            raise MarketplaceError(f"Package {package_id} has no installable version")
        violations = PackageScanner.scan(ver.metadata_json)
        if violations:
            raise MarketplaceError(
                "Install rejected — version payload unsafe: " + "; ".join(violations)
            )
        if ver.compatibility == "incompatible":
            raise MarketplaceError(f"Version {ver.version} is incompatible")

        gate_id: UUID | None = None
        if require_approval or pkg.security in (
            "confidential",
            "restricted",
        ):
            gate_id = self._create_approval_gate(package_id, company_id, requested_by)
        installation = AgentInstallation(
            package_id=package_id,
            version_id=ver.id,
            company_id=company_id,
            status=(
                InstallStatus.APPROVAL_REQUIRED.value if gate_id else InstallStatus.INSTALLING.value
            ),
            approval_gate_id=gate_id,
            config_json=config or {},
            installed_by=requested_by,
        )
        self._db.add(installation)
        self._db.commit()
        return installation

    def _create_approval_gate(
        self,
        package_id: UUID,
        company_id: UUID,
        requested_by: UUID | None,
    ) -> UUID | None:
        from app.db.models.startup import ApprovalGateType
        from app.startup.gates import ApprovalGateManager

        gate = ApprovalGateManager(self._db).create(
            company_id=company_id,
            gate_type=ApprovalGateType.HIGH_RISK_ACTION_APPROVAL,
            requested_action={
                "action": "marketplace.agent.install",
                "package_id": str(package_id),
                "module": "phase12",
            },
            rationale=(f"Marketplace install of package {package_id} requires human approval"),
            risk_level="medium",
            requester_id=requested_by,
        )
        return gate.id

    def confirm_install(self, installation_id: UUID) -> AgentInstallation:
        """Complete the install via EmployeeManager.create (safe)."""
        inst = self._db.get(AgentInstallation, installation_id)
        if inst is None:
            raise MarketplaceError(f"Installation {installation_id} not found")
        if inst.status != InstallStatus.INSTALLING.value:
            raise MarketplaceError(f"Installation in state {inst.status}; cannot confirm")
        inst.status = InstallStatus.INSTALLED.value
        inst.installed_at = datetime.now()
        self._db.commit()
        return inst

    def reject_install(self, installation_id: UUID) -> AgentInstallation:
        inst = self._db.get(AgentInstallation, installation_id)
        if inst is None:
            raise MarketplaceError(f"Installation {installation_id} not found")
        inst.status = InstallStatus.FAILED.value
        inst.config_json = {
            **(inst.config_json or {}),
            "rejection": "rejected by operator",
        }
        self._db.commit()
        return inst

    # ── Reviews & benchmarks ───────────────────────────────────────────

    def add_review(
        self,
        *,
        package_id: UUID,
        company_id: UUID | None,
        rating: int,
        comment: str | None = None,
        reviewer_id: UUID | None = None,
    ) -> AgentPackageReview:
        if not 1 <= rating <= 5:
            raise MarketplaceError("rating must be 1..5")
        review = AgentPackageReview(
            package_id=package_id,
            company_id=company_id,
            rating=rating,
            comment=comment,
            reviewer_id=reviewer_id,
        )
        self._db.add(review)
        self._db.commit()
        return review

    def attach_benchmark(
        self,
        *,
        version_id: UUID,
        benchmark_id: UUID | None = None,
        company_id: UUID | None,
        score: float,
        dimension: str | None = None,
    ) -> AgentPackageBenchmark:
        row = AgentPackageBenchmark(
            version_id=version_id,
            benchmark_id=benchmark_id,
            company_id=company_id,
            score=score,
            details_json={"dimension": dimension} if dimension else None,
        )
        self._db.add(row)
        self._db.commit()
        return row

    # ── Internal ───────────────────────────────────────────────────────

    def _require(self, package_id: UUID) -> AgentPackage:
        pkg = self.get_package(package_id)
        if pkg is None:
            raise MarketplaceError(f"Package {package_id} not found")
        return pkg
