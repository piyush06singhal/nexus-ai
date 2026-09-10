"""Verification strategies (Phase 6).

One module per strategy. Each exposes a verifier class implementing the
:class:`BaseVerifier` protocol. Strategies are composed and run by
:class:`~app.verification.service.VerificationService`.
"""

from app.verification.strategies.deterministic import DeterministicVerifier
from app.verification.strategies.independent_agent import IndependentAgentVerifier
from app.verification.strategies.model import ModelVerifier
from app.verification.strategies.rules import RuleVerifier
from app.verification.strategies.schema import SchemaVerifier
from app.verification.strategies.tool import ToolVerifier

__all__ = [
    "DeterministicVerifier",
    "SchemaVerifier",
    "RuleVerifier",
    "ToolVerifier",
    "ModelVerifier",
    "IndependentAgentVerifier",
]
