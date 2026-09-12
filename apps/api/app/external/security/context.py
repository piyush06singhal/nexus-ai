"""Model-context trust labels (Phase 10, §65 / Rule 9).

The model-context builder contract: every external-originated value that could
reach model context is labelled. The only label that flows from the external
layer for *web/browser/computer content* is ``EXTERNAL_UNTRUSTED_CONTENT`` —
that is the signal that this text is data and never instruction. The other
labels describe the sources the *system* trusts (policy, operator, internal
tool results); they are documented here so consumers assert the boundary.
"""

from __future__ import annotations

from typing import Any

# Trust labels for the model-context contract (documented, enforced at the
# observation marker in the ORM: ContentType.EXTERNAL_UNTRUSTED_CONTENT).
TRUSTED_SYSTEM = "trusted_system"
TRUSTED_POLICY = "trusted_policy"
TRUSTED_USER = "trusted_user"
EXTERNAL_UNTRUSTED_CONTENT = "external_untrusted_content"
TOOL_RESULT = "tool_result"


def label(external: bool, *, source: str = "") -> str:
    """Return the correct trust label for a value from a given source."""
    if external:
        return EXTERNAL_UNTRUSTED_CONTENT
    if source:
        return source
    return TOOL_RESULT


def annotate_observation(observation: dict[str, Any]) -> dict[str, Any]:
    """Stamp an observation dict with its trust label (idempotent)."""
    observation.setdefault(
        "_content",
        {"trust": EXTERNAL_UNTRUSTED_CONTENT, "instruction": False},
    )
    return observation


def is_trusted(value: dict[str, Any]) -> bool:
    """Whether a dict carries a trusted-system/trusted-policy label."""
    meta = value.get("_content") or {}
    return meta.get("trust") in {TRUSTED_SYSTEM, TRUSTED_POLICY}


def is_instruction(value: dict[str, Any]) -> bool:
    """External content is never an instruction — this only returns True for
    trusted content explicitly marked as a directive."""
    meta = value.get("_content") or {}
    return bool(meta.get("instruction")) and meta.get("trust") in {TRUSTED_SYSTEM, TRUSTED_POLICY}
