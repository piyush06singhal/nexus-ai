"""Live API smoke sweep (Phases 11/12+).

Walks the live ``/openapi.json`` and issues safe (GET, never-mutating)
requests against every route under the requested phase's prefixes, then
reports non-200 responses with body snippets.

This is the reusable endpoint matrix from Phase 11's verification — it
caught six 500s (schema/column contract drift) that unit tests could not
see because routers are wired through lazy ``_IncludedRouter`` proxies
that only materialize at runtime.

Usage:
    .venv/bin/python -m scripts.smoke_api --phase 11 [--base-url http://127.0.0.1:8000]
    .venv/bin/python -m scripts.smoke_api --phase 11 --all-methods
    .venv/bin/python -m scripts.smoke_api --phase 12        # after Phase 12 lands

Exit code 0 = no 5xx/4xx (other than expected not-found on id-less rows);
1 = at least one unexpected non-200.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from typing import Any

# Route prefixes owned by each phase. Phase 12 registers its own prefixes;
# a ``--phase 12`` run targets those (plus federally shared core endpoints).
_PHASE_PREFIXES: dict[int, tuple[str, ...]] = {
    11: (
        "/api/v1/access",
        "/api/v1/auth",
        "/api/v1/data",
        "/api/v1/governance",
        "/api/v1/security",
        "/api/v1/system",
        "/api/v1/roles",
    ),
    12: (
        "/api/v1/simulations",
        "/api/v1/optimization",
        "/api/v1/experiments",
        "/api/v1/benchmarks",
        "/api/v1/marketplace",
        "/api/v1/agent-recommendations",
        "/api/v1/optimization-cycles",
    ),
}

_DEFAULT_BASE = "http://127.0.0.1:8000"


def _request(base: str, path: str, token: str | None, timeout: float) -> tuple[int, str]:
    url = base + path
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            return resp.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return exc.code, body
    except urllib.error.URLError as exc:
        return 0, f"unreachable: {exc.reason}"


def _discover_company(base: str, token: str | None, timeout: float) -> str | None:
    """Return the first company id from /api/v1/companies, if any."""
    status, body = _request(base, "/api/v1/companies", token, timeout)
    if status != 200:
        return None
    try:
        rows: Any = json.loads(body)
    except json.JSONDecodeError:
        return None
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0].get("id")
    return None


def _path_with_params(path: str, company_id: str | None) -> str | None:
    """Resolve ``{param}`` segments; return None when unresolvable."""
    if "{" not in path:
        return path
    out: list[str] = []
    for seg in path.split("/"):
        if seg.startswith("{") and seg.endswith("}"):
            name = seg[1:-1]
            if name.endswith("company_id") or "company" in name:
                if not company_id:
                    return None
                out.append(company_id)
            else:
                # No sensible sample for arbitrary id params without a real
                # reference (incident_id, provider_id, secret_id, ...). Resolve
                # to the demo company id: not-found is classified as expected.
                if company_id:
                    out.append(company_id)
                    continue
                return None
        else:
            out.append(seg)
    return "/".join(out)


def _classify(status: int, has_params: bool) -> str:
    if 200 <= status < 400:
        return "ok"
    if status in (401, 403):
        return "auth"
    if status == 404 and has_params:
        return "not-found (id has no row)"
    if 500 <= status < 600:
        return "5xx"
    return "4xx"


def smoke(
    base: str,
    phase: int,
    *,
    company_id: str | None,
    token: str | None,
    all_methods: bool,
    timeout: float,
    verbose: bool,
) -> tuple[bool, Counter]:
    """Run the sweep. Returns (ok, status_counter)."""
    prefixes = _PHASE_PREFIXES.get(phase)
    if not prefixes:
        raise SystemExit(f"Unknown phase {phase!r}; known: {sorted(_PHASE_PREFIXES)}")

    status, body = _request(base, "/openapi.json", token, timeout)
    if status != 200:
        print(f"FATAL: openapi.json returned {status}")
        return False, Counter()
    spec = json.loads(body)
    paths = sorted(p for p in spec.get("paths", {}) if p.startswith(prefixes))

    if company_id is None:
        company_id = _discover_company(base, token, timeout)
    if company_id:
        print(f"Company: {company_id}")

    counts: Counter = Counter()
    problems: list[tuple[str, int, str]] = []
    skip = 0
    exercised = 0
    for path in paths:
        methods = spec["paths"][path]
        if not all_methods and "get" not in methods:
            continue
        resolved = _path_with_params(path, company_id)
        if resolved is None:
            skip += 1
            continue
        exercised += 1
        st, body = _request(base, resolved, token, timeout)
        has_params = "{" in path
        label = _classify(st, has_params)
        counts[label] += 1
        if label in ("5xx", "4xx", "auth"):
            problems.append((path, st, body[:180].replace("\n", " ")))
        if verbose:
            print(f"  {st:<4} {label:<24} {path}")

    print(
        f"\n{len(paths)} routes matched ({'all' if all_methods else 'GET-only'}); "
        f"{exercised} exercised; {skip} skipped (unresolvable params)"
    )
    for label, n in sorted(counts.items()):
        print(f"  {label}: {n}")
    if problems:
        print("\nNON-2xx/3xx endpoints:")
        for path, st, snippet in problems:
            print(f"  {st}  {path}\n      {snippet}")
        return False, counts
    return True, counts


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=_DEFAULT_BASE, help="live API base")
    parser.add_argument("--phase", type=int, default=11, help="phase prefix set (11, 12, ...)")
    parser.add_argument("--company-id", default=None, help="company scoping UUID (auto-discovered)")
    parser.add_argument("--token", default=None, help="bearer token when auth is enabled")
    parser.add_argument("--all-methods", action="store_true", help="include POST/PUT/DELETE routes")
    parser.add_argument("--timeout", type=float, default=15.0, help="per-request timeout (s)")
    parser.add_argument("--verbose", action="store_true", help="print every request line")
    args = parser.parse_args()

    started = time.monotonic()
    ok, _counts = smoke(
        args.base_url,
        args.phase,
        company_id=args.company_id,
        token=args.token,
        all_methods=args.all_methods,
        timeout=args.timeout,
        verbose=args.verbose,
    )
    print(f"(sweep finished in {time.monotonic() - started:.1f}s)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    _main()
