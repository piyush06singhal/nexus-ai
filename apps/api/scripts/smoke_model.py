"""Model provider smoke test (key-gated).

Calls each requested provider with a minimal prompt and reports whether
the response came from a real model endpoint or the deterministic stub.

Keyless (no OPENAI_API_KEY / ANTHROPIC_API_KEY): always PASS (mock).
With a key: exercises the real endpoint — PASS (real) if the call succeeds.

Usage:
    .venv/bin/python -m scripts.smoke_model --provider both
    .venv/bin/python -m scripts.smoke_model --provider openai

Exit code 0 = all requested providers responded; 1 = at least one failed.
"""

from __future__ import annotations

import argparse
import sys

from app.ai.registry import get_provider
from app.ai.types import ChatMessage, GenerationOptions

_PROMPT = [ChatMessage(role="user", content="Say hello in exactly one word.")]


def _smoke_one(provider_name: str) -> bool:
    """Call a single provider and print the result. Returns True on success."""
    try:
        provider = get_provider(provider_name)
    except KeyError:
        print(f"  SKIP  {provider_name}: provider not registered")
        return True  # not a failure — just absent

    has_key = bool(getattr(provider, "api_key", None))
    stub = getattr(provider, "stub_enabled", False)

    try:
        response = provider.generate(
            _PROMPT,
            options=GenerationOptions(max_tokens=16, temperature=0.0),
        )
        content = (response.content or "").strip()
        model = response.model or "unknown"
        is_stub = content.startswith("[stub:") or stub or not has_key
        tag = "mock" if is_stub else "real"
        print(f"  PASS  {provider_name} ({tag}: {model}) — {content[:80]!r}")
        return True
    except Exception as exc:
        print(f"  FAIL  {provider_name}: {exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        choices=["openai", "anthropic", "both"],
        default="both",
        help="Which provider(s) to smoke-test (default: both)",
    )
    args = parser.parse_args()

    targets = ["openai", "anthropic"] if args.provider == "both" else [args.provider]

    print(f"NEXUS model smoke — providers: {', '.join(targets)}")
    print("-" * 60)

    ok = True
    for name in targets:
        if not _smoke_one(name):
            ok = False

    print("-" * 60)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
