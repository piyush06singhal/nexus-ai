"""Phase 12 agent marketplace, benchmarking & recommendation tests (§60)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.company.manager import CompanyManager
from app.db.models.phase12 import AgentPackage
from app.phase12.benchmarking import BenchmarkEngine
from app.phase12.marketplace import MarketplaceError, MarketplaceService
from app.phase12.recommend import RecommendationEngine

# ── Package lifecycle ─────────────────────────────────────────────────────────


def test_package_draft_default(db):
    svc = MarketplaceService(db)
    pkg = svc.create_package(
        name="data-researcher",
        capabilities=["research", "analysis"],
        skills=["sql", "reporting"],
    )
    assert pkg.status == "draft"
    assert (pkg.capabilities_json or {}).get("capabilities") == [
        "research",
        "analysis",
    ]
    assert (pkg.skills_json or {}).get("skills") == ["sql", "reporting"]


def test_package_name_routing(db):
    svc = MarketplaceService(db)
    co_a = CompanyManager(db).create(name="Alpha Co")
    co_b = CompanyManager(db).create(name="Beta Co")
    svc.create_package(name="agent-a", company_id=co_a.id)
    svc.create_package(name="agent-b", company_id=co_b.id)

    assert [p.name for p in svc.list_packages(co_a.id)] == ["agent-a"]
    assert [p.name for p in svc.list_packages(co_b.id)] == ["agent-b"]


# ── Payload safety (PackageScanner / create_package) ──────────────────────────


def test_forbidden_secret_metadata_rejected(db):
    svc = MarketplaceService(db)
    # sk- + ≥20 alnum chars matches the sk-[a-z0-9]{20,} secret pattern.
    with pytest.raises(MarketplaceError):
        svc.create_package(
            name="leaky",
            metadata={"token": "sk-abcdefghijklmnopqrstuvwxyz0123456789"},
        )
    # api_key is a forbidden key outright (any value).
    with pytest.raises(MarketplaceError):
        svc.create_package(name="leaky-2", metadata={"api_key": "AKIAIOSFODNN7EXAMPLE"})


def test_forbidden_payload_keys_rejected(db):
    svc = MarketplaceService(db)
    for bad in (
        {"script": "print('hi')"},
        {"body": "def pwn(): pass"},
        {"code": "x = 1"},
        {"payload": "x"},
    ):
        with pytest.raises(MarketplaceError):
            svc.create_package(name="code-carrier", metadata=bad)


def test_credential_content_in_string_rejected(db):
    svc = MarketplaceService(db)
    with pytest.raises(MarketplaceError):
        svc.create_package(
            name="why-not-legal",
            metadata={"docs": "please use your api_key here"},
        )


def test_executable_extension_rejected(db):
    svc = MarketplaceService(db)
    with pytest.raises(MarketplaceError):
        svc.create_package(name="payload-file", metadata={"file": "exploit.py"})
    # Literal "#!<ext>" shebang forms are flagged by the scanner.
    with pytest.raises(MarketplaceError):
        svc.create_package(name="shebang-sh", metadata={"runner": "#!.sh"})
    with pytest.raises(MarketplaceError):
        svc.create_package(name="shebang-py", metadata={"runner": "#!.py"})


def test_safe_metadata_accepted(db):
    svc = MarketplaceService(db)
    pkg = svc.create_package(
        name="clean",
        metadata={"docs": "usage notes", "tags": ["analytics"]},
    )
    assert pkg.status == "draft"
    # Metadata is stored under requirements_json ("metadata" key), not a column.
    assert (pkg.requirements_json or {}).get("metadata") == {
        "docs": "usage notes",
        "tags": ["analytics"],
    }


# ── Versioning & publication ──────────────────────────────────────────────────


def test_versioning_semver_and_changelog(db):
    svc = MarketplaceService(db)
    pkg = svc.create_package(name="versioned")
    ver = svc.add_version(pkg.id, version="1.2.3", changelog="adds RAG")
    versions = svc.list_versions(pkg.id)
    assert len(versions) == 1
    assert versions[0].version == "1.2.3"
    assert versions[0].changelog == "adds RAG"
    assert svc.get_version(ver.id).version == "1.2.3"


def test_publish_requires_version(db):
    svc = MarketplaceService(db)
    pkg = svc.create_package(name="unpublished")
    with pytest.raises(MarketplaceError, match="no versions"):
        svc.publish(pkg.id)
    svc.add_version(pkg.id, version="1.0.0", changelog="initial")
    published = svc.publish(pkg.id)
    assert published.status == "published"
    assert published.published_at is not None


def test_deprecate(db):
    svc = MarketplaceService(db)
    pkg = svc.create_package(name="retire-me")
    svc.add_version(pkg.id, version="1.0.0")
    svc.publish(pkg.id)
    deprecated = svc.deprecate(pkg.id)
    assert deprecated.status == "deprecated"
    assert deprecated.deprecated_at is not None


# ── Safe install ──────────────────────────────────────────────────────────────


def test_install_unpublished_rejected(db):
    svc = MarketplaceService(db)
    company = CompanyManager(db).create(name="Needs Agents")
    pkg = svc.create_package(name="draft-only")
    with pytest.raises(MarketplaceError, match="not published"):
        svc.install(package_id=pkg.id, company_id=company.id)


def test_install_approval_required(db):
    svc = MarketplaceService(db)
    company = CompanyManager(db).create(name="Governed Co")
    pkg = svc.create_package(name="internal-tool", company_id=company.id, security="internal")
    svc.add_version(pkg.id, version="1.0.0")
    svc.publish(pkg.id)
    inst = svc.install(package_id=pkg.id, company_id=company.id, require_approval=True)
    assert inst.status == "approval_required"
    assert inst.approval_gate_id is not None


def test_install_no_approval_instant(db):
    svc = MarketplaceService(db)
    company = CompanyManager(db).create(name="Fast Co")
    pkg = svc.create_package(name="instant-tool", company_id=company.id, security="internal")
    svc.add_version(pkg.id, version="1.0.0")
    svc.publish(pkg.id)
    inst = svc.install(package_id=pkg.id, company_id=company.id, require_approval=False)
    assert inst.status == "installing"
    assert inst.approval_gate_id is None


def test_install_incompatible_version_rejected(db):
    svc = MarketplaceService(db)
    company = CompanyManager(db).create(name="Strict Co")
    pkg = svc.create_package(name="incompat", company_id=company.id)
    ver = svc.add_version(pkg.id, version="2.0.0", compatibility="incompatible")
    svc.publish(pkg.id)
    with pytest.raises(MarketplaceError, match="incompatible"):
        svc.install(
            package_id=pkg.id,
            company_id=company.id,
            version_id=ver.id,
            require_approval=False,
        )


def test_install_unsafe_version_rejected(db):
    """Install re-scans version metadata; an unsafe row can never slip through.

    ``add_version`` already rejects unsafe metadata, so to exercise the
    install-time rescan the unsafe version row is inserted directly via the
    ORM (bypassing the add_version guard) before calling ``install``.
    """
    from app.db.models.phase12 import AgentPackageVersion

    svc = MarketplaceService(db)
    company = CompanyManager(db).create(name="Audited Co")
    pkg = svc.create_package(name="poisoned", company_id=company.id)
    svc.add_version(pkg.id, version="1.0.0")
    svc.publish(pkg.id)
    db.add(
        AgentPackageVersion(
            package_id=pkg.id,
            company_id=pkg.company_id,
            version="0.9-unsafe",
            metadata_json={"token": "sk-abcdefghijklmnopqrstuvwxyz0123456789"},
        )
    )
    db.commit()
    unsafe = next(v for v in svc.list_versions(pkg.id) if v.version == "0.9-unsafe")
    with pytest.raises(MarketplaceError, match="version payload unsafe"):
        svc.install(
            package_id=pkg.id,
            company_id=company.id,
            version_id=unsafe.id,
            require_approval=False,
        )


def test_confirm_install_lifecycle(db):
    svc = MarketplaceService(db)
    company = CompanyManager(db).create(name="Complete Co")
    pkg = svc.create_package(name="rollout", company_id=company.id)
    svc.add_version(pkg.id, version="1.0.0")
    svc.publish(pkg.id)
    inst = svc.install(package_id=pkg.id, company_id=company.id, require_approval=False)
    assert inst.status == "installing"
    confirmed = svc.confirm_install(inst.id)
    assert confirmed.status == "installed"
    assert confirmed.installed_at is not None
    # Confirming again from "installed" is a lifecycle error.
    with pytest.raises(MarketplaceError):
        svc.confirm_install(inst.id)


def test_reject_install(db):
    svc = MarketplaceService(db)
    company = CompanyManager(db).create(name="Review Co")
    pkg = svc.create_package(name="rejected-tool", company_id=company.id)
    svc.add_version(pkg.id, version="1.0.0")
    svc.publish(pkg.id)
    inst = svc.install(package_id=pkg.id, company_id=company.id, require_approval=False)
    rejected = svc.reject_install(inst.id)
    assert rejected.status == "failed"
    assert (rejected.config_json or {}).get("rejection") == "rejected by operator"


def test_review_rating_bounds(db):
    svc = MarketplaceService(db)
    company = CompanyManager(db).create(name="Picky Co")
    pkg = svc.create_package(name="rated", company_id=company.id)
    with pytest.raises(MarketplaceError, match="1..5"):
        svc.add_review(package_id=pkg.id, company_id=company.id, rating=0)
    with pytest.raises(MarketplaceError, match="1..5"):
        svc.add_review(package_id=pkg.id, company_id=company.id, rating=6)
    review = svc.add_review(package_id=pkg.id, company_id=company.id, rating=4, comment="solid")
    assert review.rating == 4
    assert review.comment == "solid"


# ── Benchmarking ──────────────────────────────────────────────────────────────


def test_benchmark_dimensions_deterministic(db):
    be = BenchmarkEngine(db)
    company = CompanyManager(db).create(name="Bench Co")
    cases = [
        {"name": "case-a", "input": {"x": 1}, "expected_output": {"y": 2}, "weight": 1.0},
        {"name": "case-b", "input": {"x": 2}, "expected_output": {"y": 4}, "weight": 2.0},
    ]
    bench = be.create_benchmark(company_id=company.id, name="nv-bench", cases=cases)
    assert len(be.get_cases(bench.id)) == 2

    run1 = be.run_benchmark(bench.id, agent_id=uuid4(), agent_version="1.0", company_id=company.id)
    run2 = be.run_benchmark(bench.id, agent_id=uuid4(), agent_version="1.0", company_id=company.id)
    res1 = be.run_results(run1.id)
    res2 = be.run_results(run2.id)
    assert res1["aggregate"] == res2["aggregate"]
    assert len(res1["results"]) == 2

    # Running with explicit dimensions yields exactly those aggregate keys.
    run3 = be.run_benchmark(
        bench.id,
        dimensions=["correctness", "reliability"],
        company_id=company.id,
    )
    res3 = be.run_results(run3.id)
    assert sorted(res3["aggregate"].keys()) == ["correctness", "reliability"]
    for agg in res3["aggregate"].values():
        assert agg["count"] == 2


def test_benchmark_agent_scores_versioned(db):
    be = BenchmarkEngine(db)
    company = CompanyManager(db).create(name="Score Co")
    cases = [
        {"name": "c1", "input": {}, "expected_output": {}, "weight": 1.0},
        {"name": "c2", "input": {}, "expected_output": {}, "weight": 1.0},
    ]
    bench = be.create_benchmark(company_id=company.id, name="scored", cases=cases)
    agent_id = uuid4()

    be.run_benchmark(bench.id, agent_id=agent_id, agent_version="1.0", company_id=company.id)
    first = be.agent_scores(agent_id)
    assert first
    for row in first:
        assert row.dimension
        assert 0.0 <= row.score <= 1.0
        assert row.sample_cases == 2

    # A second run for the same agent (new version) adds more score rows.
    be.run_benchmark(bench.id, agent_id=agent_id, agent_version="1.1", company_id=company.id)
    second = be.agent_scores(agent_id)
    assert len(second) > len(first)


# ── Recommendations ───────────────────────────────────────────────────────────


def _published_package(db, company_id, *, name="rec-agent", capabilities=None, requirements=None):
    """Helper: create → version 1.0 → attach a real benchmark → publish."""
    svc = MarketplaceService(db)
    pkg = svc.create_package(
        name=name,
        company_id=company_id,
        capabilities=capabilities or ["research", "analysis"],
        supported_task_types=["research"],
        requirements=requirements,
    )
    ver = svc.add_version(pkg.id, version="1.0.0", changelog="initial")
    svc.attach_benchmark(
        version_id=ver.id, company_id=company_id, score=0.95, dimension="correctness"
    )
    svc.publish(pkg.id)
    return pkg


def test_recommendation_ranks_real_benchmarks(db):
    company = CompanyManager(db).create(name="Recs Co")
    _published_package(db, company.id)

    recs = RecommendationEngine(db).recommend(company_id=company.id, task_type="research")
    assert recs
    first = recs[0]
    assert first.rank == 1
    assert first.score > 0.0
    assert first.reasoning
    assert first.policy_status == "pending_approval"
    assert "benchmark=0.95" in first.reasoning


def test_recommendation_ignores_unpublished(db):
    company = CompanyManager(db).create(name="Draft Co")
    svc = MarketplaceService(db)
    svc.create_package(
        name="still-draft",
        company_id=company.id,
        capabilities=["research"],
    )  # no version, never published
    recs = RecommendationEngine(db).recommend(company_id=company.id, task_type="research")
    assert recs == []


def test_recommendation_excludes_orphaned_packages(db):
    """Packages orphaned by an ondelete=SET NULL company cascade are never candidates."""
    company = CompanyManager(db).create(name="Orphan Source Co")
    orphan = _published_package(db, company.id, name="orphan-rec-agent")
    # Simulate the Postgres ondelete=SET NULL cascade: FK drops to NULL.
    # (SQLite in tests ignores FK constraints, so we null the column explicitly.)
    orphan.company_id = None
    db.commit()
    assert db.get(AgentPackage, orphan.id).company_id is None  # orphaned

    # A fresh company must not see the orphan in recommendations.
    fresh = CompanyManager(db).create(name="Fresh Co")
    _published_package(db, fresh.id, name="fresh-rec-agent")
    recs = RecommendationEngine(db).recommend(company_id=fresh.id, task_type="research")
    names = [db.get(AgentPackage, r.package_id).name for r in recs]
    assert "fresh-rec-agent" in names
    assert "orphan-rec-agent" not in names
    assert {db.get(AgentPackage, r.package_id).company_id for r in recs} == {fresh.id}


def test_recommendation_company_isolated(db):
    """Two companies with identical packages still each rank only their own."""
    co_a = CompanyManager(db).create(name="Isol A")
    _published_package(db, co_a.id, name="iso-rec-agent", capabilities=["research"])
    co_b = CompanyManager(db).create(name="Isol B")
    _published_package(db, co_b.id, name="iso-rec-agent", capabilities=["research"])

    recs_a = RecommendationEngine(db).recommend(company_id=co_a.id, task_type="research")
    recs_b = RecommendationEngine(db).recommend(company_id=co_b.id, task_type="research")
    assert len(recs_a) == 1 and len(recs_b) == 1
    assert db.get(AgentPackage, recs_a[0].package_id).company_id == co_a.id
    assert db.get(AgentPackage, recs_b[0].package_id).company_id == co_b.id


def test_recommendation_tradeoffs_and_compat(db):
    company = CompanyManager(db).create(name="Tradeoff Co")
    _published_package(db, company.id)

    recs = RecommendationEngine(db).recommend(company_id=company.id, task_type="research")
    assert recs
    rec = recs[0]
    tradeoffs = rec.tradeoffs_json or {}
    assert isinstance(tradeoffs.get("pros"), list) and tradeoffs["pros"]
    assert isinstance(tradeoffs.get("cons"), list) and tradeoffs["cons"]
    assert isinstance(rec.compatibility, str) and rec.compatibility == "compatible"
    # Persisted recommendations are queryable via list().
    assert RecommendationEngine(db).list(company.id)


def test_recommendation_budget_and_latency_penalties(db):
    company = CompanyManager(db).create(name="Budget Co")
    _published_package(
        db,
        company.id,
        name="pricey",
        requirements={"estimated_cost": 500.0, "estimated_latency_ms": 50.0},
    )

    engine = RecommendationEngine(db)
    unpenalized = engine.recommend(company_id=company.id, task_type="research")
    assert unpenalized

    penalized = engine.recommend(company_id=company.id, task_type="research", budget_limit=100.0)
    assert penalized  # still created, but the score is penalized
    assert penalized[0].score < unpenalized[0].score

    latency_penalized = engine.recommend(
        company_id=company.id, task_type="research", latency_limit_ms=10.0
    )
    assert latency_penalized
    assert latency_penalized[0].score < unpenalized[0].score
