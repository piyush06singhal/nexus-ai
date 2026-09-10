"""Verification package (Phase 6).

Provides the shared verification abstraction used by Agent Runtime, Workflow
Engine, and Orchestrator. Verification strategies check whether a produced
result is *acceptable*.
"""

from app.verification.policy import DEFAULT_OFF, VerificationPolicy
from app.verification.service import VerificationService
from app.verification.types import (
    VerificationCriteria,
    VerificationResult,
    VerificationStatus,
)

__all__ = [
    "VerificationPolicy",
    "VerificationService",
    "VerificationResult",
    "VerificationCriteria",
    "VerificationStatus",
    "DEFAULT_OFF",
]
