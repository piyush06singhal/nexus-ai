"""Regression detection (Phase 6, spec §37).

Detects performance regressions by comparing a current score against a
previous score with a configurable threshold. No auto-rollback — just
detection and reporting.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.evaluation.entities import RegressionReport


@dataclass
class RegressionDetector:
    """Detects performance regressions (§37).

    Usage::

        detector = RegressionDetector(threshold=0.05)
        report = detector.check(previous_score=0.95, current_score=0.88)
        if report.status == "regression_detected":
            # Alert / escalate
            ...
    """

    threshold: float = 0.05

    def check(
        self,
        previous_score: float,
        current_score: float,
        label: str | None = None,
    ) -> RegressionReport:
        """Check for regression between two scores.

        Args:
            previous_score: The baseline score (0-1).
            current_score: The current score (0-1).
            label: Optional label for the report.

        Returns:
            A :class:`RegressionReport` with the detection result.
        """
        delta = current_score - previous_score

        if delta < -self.threshold:
            message = (
                f"Regression detected: score dropped from {previous_score:.4f} "
                f"to {current_score:.4f} (delta: {delta:.4f}, threshold: {self.threshold})"
            )
            if label:
                message = f"[{label}] {message}"

            return RegressionReport(
                status="regression_detected",
                previous_score=previous_score,
                current_score=current_score,
                threshold=self.threshold,
                delta=round(delta, 4),
                message=message,
            )

        message = (
            f"No regression: score {previous_score:.4f} → {current_score:.4f} "
            f"(delta: {delta:.4f}, threshold: {self.threshold})"
        )
        if label:
            message = f"[{label}] {message}"

        return RegressionReport(
            status="ok",
            previous_score=previous_score,
            current_score=current_score,
            threshold=self.threshold,
            delta=round(delta, 4),
            message=message,
        )

    def check_metric_series(
        self,
        values: list[float],
        window: int = 3,
    ) -> RegressionReport:
        """Check for regression in a metric series (sliding window).

        Compares the last ``window`` values against the preceding ``window`` values.
        """
        if len(values) < window * 2:
            return RegressionReport(
                status="ok",
                message=f"Not enough data points ({len(values)}) for window-based regression check",
            )

        prev_avg = sum(values[-window * 2 : -window]) / window
        curr_avg = sum(values[-window:]) / window

        return self.check(prev_avg, curr_avg, label="window_regression")
