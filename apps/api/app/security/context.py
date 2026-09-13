"""Context security: trust authorities & prompt-injection detection (Phase 11, §13).

Composes the Phase 10 :mod:`app.external.security.context` trust-label model
(``EXTERNAL_UNTRUSTED_CONTENT`` is data, never instruction) with a layered
prompt-injection detector. The detector's verdicts are *advisory hardening*:
they feed security events and recommend downstream gating, and are meant to
wrap the existing tool/browser/computer permission checks — never to replace
the explicit permission model.

Layers (in order of evaluation):
1. **Input classification** — static heuristics over the untrusted text.
2. **Isolation** — the untrusted text is tagged (Phase 10 contract), so model
   context explicitly marks it as data rather than instruction.
3. **Authority** — whether the source itself is trusted/registered.
4. **Escalation** — patterns that request a *change of posture* (ignore
   previous instructions / reveal secrets / change system policy / disable
   security / send data elsewhere / pretend to be system).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models.security import (
    ContextAuthority,
    ContextAuthorityRecord,
    SecurityEventCategory,
    Severity,
)

logger = get_logger(__name__)

# Rollup of the trusted-source labels (mirrors Phase 10 / the local enum).
TRUSTED_AUTHORITIES = (
    ContextAuthority.TRUSTED_SYSTEM.value,
    ContextAuthority.TRUSTED_POLICY.value,
    ContextAuthority.TRUSTED_USER.value,
    ContextAuthority.TOOL_RESULT.value,
)
UNTRUSTED_AUTHORITY = ContextAuthority.EXTERNAL_UNTRUSTED_CONTENT.value


@dataclass
class InjectionVerdict:
    is_injection: bool
    severity: str = "low"
    detected_patterns: list[str] = field(default_factory=list)
    source_authority: str | None = None
    recommended_action: str = "allow"


# Patterns that indicate an instruction-change attack. Broad, deliberate: a
# false positive here costs a human glance; a false negative costs the boundary.
_ESCAPE_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    (
        "ignore_previous",
        re.compile(
            r"ignore (all |any )?(previous|prior|earlier) (instructions|prompts|messages)", re.I
        ),
    ),
    (
        "forget_context",
        re.compile(r"forget (everything|the context|your previous instructions)", re.I),
    ),
    (
        "reveal_secrets",
        re.compile(
            r"(reveal|show|print|dump|expose|output) "
            r"(your )?(secret|password|api[_ -]?key|token|credentials)",
            re.I,
        ),
    ),
    (
        "change_policy",
        re.compile(
            r"(change|modify|override|bypass) (system|security|access|permission) "
            r"(policy|rules|settings|controls)",
            re.I,
        ),
    ),
    (
        "disable_security",
        re.compile(
            r"(disable|turn off|deactivate|shut down) "
            r"(the )?(security|safety|guardrail|verification|audit)",
            re.I,
        ),
    ),
    (
        "exfiltration",
        re.compile(
            r"(send|ship|post|email|transfer|upload) (this|the|all) "
            r".*(elsewhere|externally|to your)",
            re.I,
        ),
    ),
    (
        "impersonation",
        re.compile(r"(pretend|act|behave) (as|like) (the)?\s*(system|admin|operator|root)", re.I),
    ),
    (
        "no_quarantine",
        re.compile(
            r"(do not|don'?t) (warn|flag|mention|tell|say|report) "
            r".{0,40}(injection|attack|suspicious)",
            re.I,
        ),
    ),
    (
        "policy_change_request",
        re.compile(r"(grant|elevate|upgrade) (me|yourself) (permissions?|access|privileges)", re.I),
    ),
    (
        "secret_extraction",
        re.compile(r"(what('| i)s )?(your|the) .{0,20}(password|secret|key|token)", re.I),
    ),
)

# Phrase that directly pressures the model to disclose system configuration.
_SYSTEM_PROBE_PATTERN = re.compile(
    r"(what (are|is) (your|the) (instructions|system prompt|configuration))", re.I
)


class ContextAuthorityManager:
    """Register and query trust authorities (``context_authorities``)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def register(
        self,
        *,
        source_type: str,
        authority: str,
        resource_ref: str | None = None,
        qualified_by: str | None = None,
        company_id: UUID | None = None,
    ) -> ContextAuthorityRecord:
        row = self.db.execute(
            select(ContextAuthorityRecord).where(
                ContextAuthorityRecord.source_type == source_type,
                ContextAuthorityRecord.resource_ref == (resource_ref or None),
            )
        ).scalar_one_or_none()
        if row is None:
            row = ContextAuthorityRecord(
                source_type=source_type,
                resource_ref=resource_ref,
                company_id=company_id,
            )
            self.db.add(row)
        row.authority = authority
        row.qualified_by = qualified_by
        self.db.flush()
        return row

    def authority_of(self, source_type: str, resource_ref: str | None = None) -> str | None:
        row = self.db.execute(
            select(ContextAuthorityRecord).where(
                ContextAuthorityRecord.source_type == source_type,
                ContextAuthorityRecord.resource_ref == (resource_ref or None),
            )
        ).scalar_one_or_none()
        return row.authority if row is not None else None

    def is_trusted_source(self, source_type: str, resource_ref: str | None = None) -> bool:
        authority = self.authority_of(source_type, resource_ref)
        if authority is None:
            return False  # unregistered sources are never trusted by default
        return authority in TRUSTED_AUTHORITIES


class PromptInjectionDetector:
    """Layered prompt-injection assessment over untrusted model input."""

    def __init__(self, db: Session | None = None) -> None:
        self.db = db
        self._patterns = _ESCAPE_PATTERNS
        self._system_probe = _SYSTEM_PROBE_PATTERN

    def assess(
        self,
        text: str,
        *,
        source: str = "external",
        authority: str = UNTRUSTED_AUTHORITY,
        record: bool = True,
    ) -> InjectionVerdict:
        """Classify *text* and return an advisory verdict.

        Detects instruction-escape patterns; when ``record`` is true and a
        detection fires, a ``PROMPT_INJECTION`` security event is written
        (deduped per source + pattern).
        """
        detected: list[str] = []
        for name, pattern in self._patterns:
            if pattern.search(text):
                detected.append(name)
        if self._system_probe.search(text):
            detected.append("system_probe")

        is_injection = bool(detected)
        severity = "high" if is_injection else "low"
        if is_injection and self.db is not None and record:
            try:
                from app.security.detection import SecurityEventService

                SecurityEventService(self.db).record(
                    category=SecurityEventCategory.PROMPT_INJECTION,
                    severity=Severity.HIGH,
                    title=f"Prompt injection detected ({source})",
                    detail={
                        "source": source,
                        "patterns": detected,
                        "authority": authority,
                    },
                    observed_by="context_security",
                    fingerprint_parts=["prompt_injection", source, ",".join(detected)],
                )
            except Exception:  # pragma: no cover
                logger.debug("prompt-injection event not recorded")

        return InjectionVerdict(
            is_injection=is_injection,
            severity=severity,
            detected_patterns=detected,
            source_authority=authority,
            recommended_action=("quarantine" if is_injection else "allow"),
        )

    def assess_source(
        self, *, source_type: str, text: str, resource_ref: str | None = None
    ) -> InjectionVerdict:
        """Assess text from a *named source type*, weighing its registered
        authority: a verified trusted source gets a softer baseline than raw
        untrusted content (defense-in-depth — still scanned, never skipped)."""
        authority = UNTRUSTED_AUTHORITY
        if self.db is not None:
            manager = ContextAuthorityManager(self.db)
            authority = manager.authority_of(source_type, resource_ref) or UNTRUSTED_AUTHORITY
        result = self.assess(text, source=source_type, authority=authority)
        if authority in TRUSTED_AUTHORITIES and result.is_injection:
            # Trusted *sources* can still be compromised; keep the flag but
            # acknowledge the provenance in the verdict.
            result.recommended_action = "review"
        return result


def is_untrusted_observation(payload: dict) -> bool:
    """Whether a dict payload carries the Phase 10 untrusted-content marker."""
    content = payload.get("_content") or {}
    return content.get("trust") == UNTRUSTED_AUTHORITY
