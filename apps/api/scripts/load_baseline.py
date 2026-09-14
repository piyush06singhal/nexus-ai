"""NEXUS concurrent HTTP load baseline.

Drives the running API stack from N concurrent clients over a mix of read and
write endpoints and reports p50 / p95 / p99 latency, throughput, and error
rate. Results are **development-environment measurements, not production SLAs**
(§42) — machine, DB, and concurrency dependent.

Design goals:
  * dependency-free — stdlib ``http.client`` and ``concurrent.futures`` only,
    like ``perf_baseline.py``;
  * endpoint mix covers the API tiers customers actually hit most: companies,
    agents, marketplace reads, a recommendation write, and the metrics +
    health endpoints that every probe and dashboard polls.

Usage (stack running, e.g. ``scripts/run_production.sh`` or the dev compose):
    .venv/bin/python -m scripts.load_baseline --clients 16 --requests 400
    .venv/bin/python -m scripts.load_baseline --clients 8 --base-url http://localhost:8000

Exit code 0 unless the error rate rises above ``--max-error-rate`` (default 5%).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

_DEFAULT_BASE = "http://127.0.0.1:8000"

#: (name, method, path, json_body|None) — body ``None`` = GET.
#: Weight repeats the slot in the mix to bias toward read-heavy real traffic.
_TARGETS: list[tuple[str, str, str, dict[str, Any] | None]] = [
    ("health", "GET", "/api/v1/health", None),
    ("companies:list", "GET", "/api/v1/companies", None),
    ("agents:list", "GET", "/api/v1/agents", None),
    ("companies:list", "GET", "/api/v1/companies", None),
    ("marketplace:agents", "GET", "/api/v1/marketplace/agents", None),
    ("metrics", "GET", "/api/v1/system/metrics", None),
    ("recommendations:create", "POST", "/api/v1/agent-recommendations", {"task_type": "research"}),
    ("companies:list", "GET", "/api/v1/companies", None),
]


def _request(
    base: str, target: tuple[str, str, str, dict[str, Any] | None]
) -> tuple[str, float, int]:
    name, method, path, body = target
    url = base + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json" if data else "text/plain",
            "User-Agent": "nexus-load-baseline/1.0",
        },
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except Exception as exc:  # network errors count as 5xx for the report
        status = 599
        name = f"{name}(err:{type(exc).__name__})"
    latency_ms = (time.perf_counter() - t0) * 1000
    return name, latency_ms, status


def _percentile(sorted_lat: list[float], q: float) -> float:
    if not sorted_lat:
        return 0.0
    idx = min(len(sorted_lat) - 1, int(q * len(sorted_lat)))
    return sorted_lat[idx]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Concurrent HTTP load baseline for NEXUS "
        "(dev-machine measurements, not SLAs - see --help for usage)."
    )
    parser.add_argument("--base-url", default=_DEFAULT_BASE, help="API base URL")
    parser.add_argument("--clients", type=int, default=8, help="concurrent clients")
    parser.add_argument("--requests", type=int, default=320, help="total requests")
    parser.add_argument("--max-error-rate", type=float, default=5.0, help="fatal-error threshold")
    args = parser.parse_args()

    mix = [t for _ in range(1) for t in _TARGETS]
    print(f"NEXUS load baseline — {datetime.now(UTC).isoformat(timespec='seconds')}")
    print(
        f"target={args.base_url}  clients={args.clients}  requests={args.requests} "
        f"(dev-machine measurements, not SLAs — §42)\n"
    )

    latencies: list[tuple[str, float]] = []
    statuses: list[int] = []

    def _assign(_i: int):
        # Deterministic-ish shuffle: every client sees all slots.
        target = mix[_i % len(mix)]
        return _request(args.base_url, target)

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.clients) as pool:
        results = pool.map(_assign, range(args.requests))
    wall = time.perf_counter() - t0

    for worker_name, lat_ms, status in results:
        latencies.append((worker_name, lat_ms))
        statuses.append(status)

    per_route: dict[str, list[float]] = {}
    for name, lat in latencies:
        per_route.setdefault(name.split("(")[0], []).append(lat)
    ok = sum(1 for s in statuses if 200 <= s < 500)
    err = len(statuses) - ok
    err_pct = 100.0 * err / len(statuses) if statuses else 0.0

    all_lat = sorted(lat for _, lat in latencies)
    print(f"| {'Route':<28} | {'Count':>5} | {'p50 (ms)':>9} | {'p95 (ms)':>9} | {'p99 (ms)':>9} |")
    print(f"|{'-' * 30}|{'':>7}|{'':>11}|{'':>11}|{'':>11}|")
    for name in sorted(per_route):
        s = sorted(per_route[name])
        print(
            f"| {name:<28} | {len(s):>5} | "
            f"{_percentile(s, 0.50):>9.1f} | {_percentile(s, 0.95):>9.1f} | "
            f"{_percentile(s, 0.99):>9.1f} |"
        )
    print(f"|{'-' * 30}|{'-' * 7}|{'-' * 11}|{'-' * 11}|{'-' * 11}|")
    print(
        f"| {'ALL':<28} | {len(all_lat):>5} | "
        f"{_percentile(all_lat, 0.50):>9.1f} | {_percentile(all_lat, 0.95):>9.1f} | "
        f"{_percentile(all_lat, 0.99):>9.1f} |"
    )
    print(f"\nThroughput: {len(all_lat) / wall:>7.1f} req/s   Wall: {wall:6.2f}s")
    status_buckets: dict[int, int] = {}
    for s in statuses:
        status_buckets[s] = status_buckets.get(s, 0) + 1
    dist = ", ".join(f"{code}:{n}" for code, n in sorted(status_buckets.items()))
    err_line = f"{dist}  |  Error rate: {err_pct:.2f}% (threshold {args.max_error_rate}%)"
    print(f"Status distribution: {err_line}")

    # 5xx + transport errors are the failure signal; 4xx (e.g. 404, 429 on an
    # intentionally rate-limited route) are recorded but not fatal.
    fatal = sum(1 for s in statuses if s >= 500)
    fatal_pct = 100.0 * fatal / len(statuses) if statuses else 0.0
    ok_profile = "PASS" if fatal_pct <= args.max_error_rate else "FAIL"
    print(f"Fatal (5xx/network) error rate: {fatal_pct:.2f}%  →  {ok_profile}")
    print("\nValues are development-environment measurements, not SLAs (§42).")
    return 0 if ok_profile == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
