"""Text utility tool — string manipulation and analysis.

Provides common text operations without external dependencies.
"""

from __future__ import annotations

from typing import Any

from app.tools.base import BaseTool
from app.tools.types import (
    ToolDefinition,
    ToolParameter,
    ToolParameterType,
    ToolResult,
    ToolResultStatus,
)


class TextUtilityTool(BaseTool):
    """String manipulation: case conversion, counting, trimming, and more."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="text_utils",
            description=(
                "Manipulate and analyze text: case conversion, word count, trim, replace, and more."
            ),
            parameters=[
                ToolParameter(
                    name="action",
                    type=ToolParameterType.STRING,
                    description="Action: 'case', 'count', 'trim', 'replace', 'reverse', 'words'",
                    required=True,
                    enum=["case", "count", "trim", "replace", "reverse", "words"],
                ),
                ToolParameter(
                    name="text",
                    type=ToolParameterType.STRING,
                    description="Input text to operate on.",
                    required=True,
                ),
                ToolParameter(
                    name="case_type",
                    type=ToolParameterType.STRING,
                    description=(
                        "Target case for 'case' action: 'upper', 'lower', 'title', 'sentence'."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="substring",
                    type=ToolParameterType.STRING,
                    description="Substring to count or replace.",
                    required=False,
                ),
                ToolParameter(
                    name="replacement",
                    type=ToolParameterType.STRING,
                    description="Replacement string for 'replace' action.",
                    required=False,
                ),
            ],
            dangerous=False,
            timeout_seconds=5.0,
            tags=["text", "utility"],
        )

    def execute(self, *, action: str, text: str, **kwargs: Any) -> ToolResult:
        try:
            if action == "case":
                case_type = kwargs.get("case_type", "lower")
                result = self._case(text, case_type)
            elif action == "count":
                substring = kwargs.get("substring", "")
                result = self._count(text, substring)
            elif action == "trim":
                result = {"trimmed": text.strip(), "length": len(text.strip())}
            elif action == "replace":
                substring = kwargs.get("substring", "")
                replacement = kwargs.get("replacement", "")
                result = {
                    "original": text,
                    "result": text.replace(substring, replacement),
                    "count": text.count(substring),
                }
            elif action == "reverse":
                result = {"original": text, "reversed": text[::-1]}
            elif action == "words":
                words = text.split()
                result = {
                    "word_count": len(words),
                    "char_count": len(text),
                    "words": words,
                }
            else:
                return ToolResult(status=ToolResultStatus.ERROR, error=f"Unknown action: {action}")

            return ToolResult(status=ToolResultStatus.SUCCESS, data=result)
        except Exception as exc:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"Text operation failed: {exc}")

    @staticmethod
    def _case(text: str, case_type: str) -> dict[str, str]:
        mapping = {
            "upper": text.upper(),
            "lower": text.lower(),
            "title": text.title(),
            "sentence": text.capitalize(),
        }
        if case_type not in mapping:
            raise ValueError(f"Unknown case_type: {case_type}")
        return {"original": text, "result": mapping[case_type], "case": case_type}

    @staticmethod
    def _count(text: str, substring: str) -> dict[str, int]:
        return {
            "count": text.count(substring),
            "substring": substring,
            "total_length": len(text),
        }
