"""Agent review foundation (spec §16).

:class:`AgentReviewService` manages agent-to-agent review requests and verdicts.
It is the *foundation* the orchestrator can call during a post-completion review
pass when configured; it enforces a maximum iteration count (via
:class:`ReviewPolicy`) so a rejected/request-revision loop cannot spin forever.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFoundError
from app.db.models.orchestration import AgentReview, ReviewVerdict
from app.orchestration.types import OrchestrationError


class ReviewError(OrchestrationError):
    """A review request or verdict could not be recorded."""


class ReviewLimitError(ReviewError):
    """The maximum review iteration count has been reached."""


@dataclass
class ReviewPolicy:
    """Limits governing the agent-review loop."""

    max_iterations: int = field(
        default_factory=lambda: settings.orchestration_max_review_iterations
    )


def reviewed_at_is_terminal(verdict: ReviewVerdict) -> bool:
    """Whether a verdict closes the review loop (no further revision pending)."""
    return verdict in (ReviewVerdict.APPROVED, ReviewVerdict.REJECTED)


def _as_verdict(value: ReviewVerdict | str) -> ReviewVerdict:
    if isinstance(value, str):
        try:
            return ReviewVerdict(value)
        except ValueError as exc:
            raise ReviewError(f"Invalid review verdict: {value!r}") from exc
    return value


class AgentReviewService:
    """Create, complete, and query agent reviews."""

    def __init__(self, db: Session, *, policy: ReviewPolicy | None = None) -> None:
        self._db = db
        self._policy = policy or ReviewPolicy()

    def request(
        self,
        orchestration_id: UUID,
        reviewer_agent_id: UUID,
        *,
        task_id: UUID | None = None,
        reviewee_agent_id: UUID | None = None,
        content: str | None = None,
    ) -> AgentReview:
        """Open a new review request for the coordinator/reviewee agent."""
        review = AgentReview(
            orchestration_id=orchestration_id,
            task_id=task_id,
            reviewer_agent_id=reviewer_agent_id,
            reviewee_agent_id=reviewee_agent_id,
            request_content=content,
            verdict=ReviewVerdict.PENDING,
            iteration=1,
        )
        self._db.add(review)
        self._db.commit()
        self._db.refresh(review)
        return review

    def complete(
        self,
        review_id: UUID,
        verdict: ReviewVerdict | str,
        response_content: str | None = None,
        *,
        outcome_override: bool = False,
    ) -> AgentReview:
        """Record a verdict for an open review, enforcing the iteration cap.

        Pass ``outcome_override=True`` (used by the orchestrator when closing a
        pending review at completion time) to bypass the cap-bounded revision
        loop — it does not create a new review, so it cannot grow unboundedly.
        """
        review = self._db.get(AgentReview, review_id)
        if review is None:
            raise NotFoundError(f"AgentReview {review_id} not found")

        resolved = _as_verdict(verdict)
        if resolved not in (
            ReviewVerdict.APPROVED,
            ReviewVerdict.REJECTED,
            ReviewVerdict.REQUEST_REVISION,
        ):
            raise ReviewError(f"Invalid review verdict: {verdict!r}")

        if (
            not outcome_override
            and resolved in (ReviewVerdict.REJECTED, ReviewVerdict.REQUEST_REVISION)
            and review.iteration >= self._policy.max_iterations
        ):
            # Max revisions reached: force-close as approved so the run can finish.
            resolved = ReviewVerdict.APPROVED
            response_content = (
                response_content or "Max review iterations reached; review closed as approved."
            )

        review.verdict = resolved
        review.response_content = response_content
        if reviewed_at_is_terminal(resolved):
            review.completed_at = datetime.now(UTC)
        self._db.commit()
        self._db.refresh(review)
        return review

    def request_revision(self, review_id: UUID, feedback: str | None = None) -> AgentReview:
        """Mark a review as requesting a revision (increments the iteration)."""
        review = self._db.get(AgentReview, review_id)
        if review is None:
            raise NotFoundError(f"AgentReview {review_id} not found")
        review.verdict = ReviewVerdict.REQUEST_REVISION
        review.response_content = feedback or "Revision requested."
        if review.iteration < self._policy.max_iterations:
            review.iteration += 1
        self._db.commit()
        self._db.refresh(review)
        return review

    def list(self, orchestration_id: UUID) -> list[AgentReview]:
        """Return all reviews for an orchestration."""
        return (
            self._db.query(AgentReview)
            .filter(AgentReview.orchestration_id == orchestration_id)
            .order_by(AgentReview.created_at)
            .all()
        )

    def get(self, review_id: UUID) -> AgentReview:
        review = self._db.get(AgentReview, review_id)
        if review is None:
            raise NotFoundError(f"AgentReview {review_id} not found")
        return review
