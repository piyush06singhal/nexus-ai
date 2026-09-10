"""Tests for AI Employee performance tracking (Phase 7)."""

from datetime import UTC, datetime

from app.employee.manager import EmployeeManager


def test_record_task_completion(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="perf-worker")

    mgr.performance.record_task_completion(
        emp.id, success=True, quality=0.9, latency_ms=100, cost=0.05, tokens=200
    )
    metrics = mgr.performance.get_metrics(emp.id)
    assert metrics.tasks_completed == 1
    assert metrics.tasks_failed == 0
    assert metrics.success_rate == 1.0
    assert metrics.total_cost == 0.05
    assert metrics.total_tokens == 200


def test_record_mixed_completions(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="mixed-worker")

    mgr.performance.record_task_completion(emp.id, success=True, quality=0.8)
    mgr.performance.record_task_completion(emp.id, success=False, quality=0.2)
    mgr.performance.record_task_completion(emp.id, success=True, quality=0.9)

    metrics = mgr.performance.get_metrics(emp.id)
    assert metrics.tasks_completed == 2
    assert metrics.tasks_failed == 1
    assert abs(metrics.success_rate - (2 / 3)) < 0.01


def test_generate_review(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="review-worker")

    # Generate several successful completions
    for _ in range(5):
        mgr.performance.record_task_completion(emp.id, success=True, quality=0.8, deadline_met=True)
    reviews = mgr.reviewer.generate_review(
        emp.id, period_start=datetime.now(UTC), period_end=datetime.now(UTC)
    )
    assert reviews.employee_id == emp.id
    # Should have strengths and recommendations
    import json

    strengths = json.loads(reviews.strengths)
    assert len(strengths) >= 1
    recs = json.loads(reviews.recommendations)
    assert len(recs) >= 1


def test_generate_review_low_performance(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="low-worker")

    for _ in range(5):
        mgr.performance.record_task_completion(
            emp.id, success=False, quality=0.1, deadline_met=False
        )
    reviews = mgr.reviewer.generate_review(
        emp.id, period_start=datetime.now(UTC), period_end=datetime.now(UTC)
    )
    import json

    weaknesses = json.loads(reviews.weaknesses)
    assert any("success rate" in w.lower() for w in weaknesses)


def test_get_reviews(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="multi-review")
    mgr.reviewer.generate_review(emp.id, period_start=datetime.now(UTC))
    mgr.reviewer.generate_review(emp.id, period_start=datetime.now(UTC))
    reviews = mgr.get_reviews(emp.id)
    assert len(reviews) == 2


def test_verification_pass_rate_tracks(db):
    mgr = EmployeeManager(db)
    emp = mgr.create(name="verify-worker")

    mgr.performance.record_task_completion(emp.id, success=True, verified=True)
    mgr.performance.record_task_completion(emp.id, success=True, verified=False)
    metrics = mgr.performance.get_metrics(emp.id)
    assert metrics.verification_pass_rate > 0.0
