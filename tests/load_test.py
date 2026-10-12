"""Small, read-only HTTP load check for the local attendance API.

Start the API against the synthetic ``attendance_scale`` database first, e.g.:
    $env:MONGO_DB='attendance_scale'; py -3.11 -m uvicorn app.main:app --host 127.0.0.1 --port 8010

Then run:
    py -3.11 tests/load_test.py --base-url http://127.0.0.1:8010 --workers 5 --loops 4

Every request is GET-only. The script checks a short warm-up before sending
concurrent traffic and reports aggregate and per-route latency/error metrics.
This is a development baseline, not a production capacity certification.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROUTES = {
    "health": "/health",
    "employees": "/employees?page=1&page_size=50",
    "attendance_list": "/attendance?date_from=2026-01-01&date_to=2026-01-31&page=1&page_size=100",
    "employee_monthly": "/analytics/employees/EMP0000/monthly?month=2026-01",
    "department_summary": "/analytics/departments/summary?month=2026-01",
    "late_leaderboard": "/analytics/leaderboard/late?month=2026-01&limit=10",
    "department_trend": "/analytics/departments/Dept0/trend?from=2026-01-01&to=2026-01-07",
}


def request_once(base_url: str, route: str, timeout: float) -> tuple[float, int, str | None]:
    """Issue one GET and return elapsed seconds, HTTP status, and an optional error."""
    started = time.perf_counter()
    try:
        request = Request(base_url.rstrip("/") + route, method="GET")
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            # Ensure successful responses are valid JSON, not a proxy error page.
            json.loads(body)
            return time.perf_counter() - started, response.status, None
    except HTTPError as error:
        return time.perf_counter() - started, error.code, f"HTTP {error.code}"
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        return time.perf_counter() - started, 0, str(error)


def percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank percentile in milliseconds."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)] * 1000


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only concurrent API load check")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--loops", type=int, default=4, help="complete route passes per worker")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    if not 1 <= args.workers <= 32 or not 1 <= args.loops <= 100:
        parser.error("workers must be 1..32 and loops must be 1..100")

    # Warm-up proves the target and synthetic dataset respond before measuring.
    for name, route in ROUTES.items():
        _, status, error = request_once(args.base_url, route, args.timeout)
        if status != 200:
            print(f"Warm-up failed for {name}: {error or f'HTTP {status}'}")
            return 2

    results: list[tuple[str, float, int, str | None]] = []
    lock = threading.Lock()

    def worker() -> None:
        local: list[tuple[str, float, int, str | None]] = []
        for _ in range(args.loops):
            for name, route in ROUTES.items():
                elapsed, status, error = request_once(args.base_url, route, args.timeout)
                local.append((name, elapsed, status, error))
        with lock:
            results.extend(local)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(lambda _: worker(), range(args.workers)))
    duration = time.perf_counter() - started

    failures = [item for item in results if item[2] != 200]
    elapsed = [item[1] for item in results]
    print(f"target={args.base_url}")
    print(f"workers={args.workers} loops={args.loops} routes={len(ROUTES)} requests={len(results)}")
    print(f"duration_seconds={duration:.3f} throughput_rps={len(results) / duration:.2f}")
    print(f"overall_latency_ms p50={percentile(elapsed, .50):.1f} p95={percentile(elapsed, .95):.1f} p99={percentile(elapsed, .99):.1f} max={max(elapsed) * 1000:.1f}")
    print(f"http_200={len(results) - len(failures)} errors={len(failures)}")
    for name in ROUTES:
        group = [item for item in results if item[0] == name]
        timings = [item[1] for item in group]
        bad = sum(item[2] != 200 for item in group)
        print(f"{name}: requests={len(group)} errors={bad} p50_ms={statistics.median(timings) * 1000:.1f} p95_ms={percentile(timings, .95):.1f} max_ms={max(timings) * 1000:.1f}")
    if failures:
        for name, _, status, error in failures[:10]:
            print(f"failure: route={name} status={status} error={error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
