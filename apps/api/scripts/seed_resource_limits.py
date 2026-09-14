#!/usr/bin/env python3
"""One-shot seeder: provision per-tenant governance limits from config defaults.

Idempotent — re-runs update existing rows instead of duplicating them. Run
before a public launch, or rely on the ``RESOURCE_LIMITS_PROVISION=true``
app lifespan bootstrap which does the same thing on every startup.

    cd apps/api
    .venv/bin/python -m scripts.seed_resource_limits [--company-id UUID ...]
"""

from __future__ import annotations

import argparse
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal
from app.security.resources import ResourceGovernanceService


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="Seed per-tenant resource limits from config defaults."
    )
    ap.add_argument(
        "--company-id",
        action="append",
        dest="company_ids",
        type=UUID,
        default=[],
        help="Seed limits for a specific tenant (repeatable). If omitted, limits "
        "are seeded for ALL existing tenants + a global-scope row.",
    )
    args = ap.parse_args(argv)

    db = SessionLocal()
    try:
        if not args.company_ids:
            from app.db.models.company import Company

            company_ids = list(db.execute(select(Company.id)).scalars().all())
        else:
            company_ids = args.company_ids

        created = ResourceGovernanceService(db).provision_default_limits(company_ids=company_ids)
        db.commit()

        print(f"Provisioned {len(created)} resource-limit rows for {len(company_ids)} tenant(s):")
        for lim in created:
            label = f"{lim.scope}/{lim.tenant_id or 'global'}"
            print(f"  {label:<40} {lim.category}: {lim.max_value} / {lim.period}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
