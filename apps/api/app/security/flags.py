"""Feature flags (Phase 11, §71) — env default → global → company override.

``FeatureFlagService.is_enabled(name, company_id)`` resolves:
1. a company-scoped override row if present, else
2. a GLOBAL-scope override row if present, else
3. the setting default (``feature_<name>_enabled`` or ``False``).

Risky capabilities are off by default (feature_*_enabled=False in config) —
operators enable them deliberately. Overrides are audited.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.security import FeatureFlag, FeatureFlagScope

logger = get_logger(__name__)


class FeatureFlagService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def is_enabled(self, name: str, *, company_id: UUID | None = None) -> bool:
        # Explicit overrides beat config defaults.
        row = self._row(name, company_id)
        if row is not None:
            return bool(row.enabled)
        return self._setting_default(name)

    def set_override(
        self,
        *,
        name: str,
        enabled: bool,
        company_id: UUID | None = None,
        set_by: UUID | None = None,
        rationale: str | None = None,
    ) -> FeatureFlag | None:
        scope = (
            FeatureFlagScope.COMPANY.value
            if company_id is not None
            else FeatureFlagScope.GLOBAL.value
        )
        row = self._row(name, company_id)
        if row is None:
            row = FeatureFlag(
                scope=scope,
                company_id=company_id,
                name=name,
                enabled=enabled,
                rationale=rationale,
                changed_by=set_by,
            )
            self.db.add(row)
        else:
            row.enabled = enabled
            if rationale:
                row.rationale = rationale
            row.changed_by = set_by
        self.db.flush()
        self._audit(name, enabled, company_id, set_by, scope)
        return row

    def clear_override(self, *, name: str, company_id: UUID | None = None) -> bool:
        """Remove an override row so resolution falls back to the config default."""
        row = self._row(name, company_id)
        if row is None:
            return False
        self.db.delete(row)
        self.db.flush()
        return True

    def list(self, company_id: UUID | None = None) -> list[FeatureFlag]:
        stmt = select(FeatureFlag)
        if company_id is not None:
            stmt = stmt.where(
                (FeatureFlag.company_id == company_id)
                | (FeatureFlag.scope == FeatureFlagScope.GLOBAL.value)
            )
        return list(self.db.execute(stmt).scalars().all())

    def _row(self, name: str, company_id: UUID | None) -> FeatureFlag | None:
        if company_id is not None:
            stmt = select(FeatureFlag).where(
                FeatureFlag.name == name,
                FeatureFlag.company_id == company_id,
                FeatureFlag.scope == FeatureFlagScope.COMPANY.value,
            )
            row = self.db.execute(stmt).scalar_one_or_none()
            if row is not None:
                return row
        stmt = select(FeatureFlag).where(
            FeatureFlag.name == name,
            FeatureFlag.scope == FeatureFlagScope.GLOBAL.value,
            FeatureFlag.company_id.is_(None),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _setting_default(self, name: str) -> bool:
        attr = f"feature_{name.replace('-', '_')}_enabled"
        value = getattr(settings, attr, None)
        if value is None:
            logger.debug("No config default for feature flag %s (defaulting False)", name)
            return False
        return bool(value)

    def _audit(
        self, name: str, enabled: bool, company_id: UUID | None, set_by: UUID | None, scope: str
    ) -> None:
        try:
            from app.security.accountability import AuditService

            AuditService(self.db).record(
                actor_id=set_by,
                company_id=company_id,
                action="feature_flag.set",
                category="governance",
                resource_type="feature_flags",
                resource_id=name,
                outcome="success",
                detail={"enabled": enabled, "scope": scope},
                commit=False,
            )
        except Exception:  # pragma: no cover
            logger.debug("audit skip for feature flag %s", name)
