"""Bounded, quota-free backend memory soak using local ASGI fixtures."""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import time

from scripts.profile_backend_memory import _install_research_fixture, peak_rss_mb, rss_mb


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cheap", type=int, default=500)
    parser.add_argument("--quant", type=int, default=200)
    parser.add_argument("--factors", type=int, default=100)
    parser.add_argument("--research-fixture", type=int, default=75)
    args = parser.parse_args()

    import api.index as api
    from fastapi.testclient import TestClient

    _install_research_fixture(api.app)
    paths = (
        ["/api/health"] * args.cheap
        + ["/api/quant/status"] * args.quant
        + ["/api/factors?universe=mega30"] * args.factors
        + ["/api/research/AAPL?fast=true"] * args.research_fixture
    )
    readings: list[float] = []
    latencies: list[float] = []
    started = time.perf_counter()
    with TestClient(api.app, raise_server_exceptions=False) as client:
        # Warm one call per route before defining the baseline. Lazy module
        # imports and Starlette startup allocations are not a leak; counting
        # them as per-request growth would make the curve misleading.
        for path in dict.fromkeys(paths):
            response = client.get(path)
            if response.status_code >= 500:
                raise RuntimeError(f"warmup {path} returned {response.status_code}")
        gc.collect()
        readings.append(rss_mb())
        for index, path in enumerate(paths, 1):
            tick = time.perf_counter()
            response = client.get(path)
            latencies.append((time.perf_counter() - tick) * 1000)
            if response.status_code >= 500:
                raise RuntimeError(f"{path} returned {response.status_code}")
            if index % 25 == 0:
                gc.collect()
                readings.append(rss_mb())
    gc.collect()
    readings.append(rss_mb())
    count = len(paths)
    initial, final = readings[0], readings[-1]
    print(json.dumps({
        "requests": count,
        "initial_rss_mb": initial,
        "median_sampled_rss_mb": round(statistics.median(readings), 2),
        "peak_sampled_rss_mb": max(readings),
        "process_peak_rss_mb": peak_rss_mb(),
        "final_rss_mb": final,
        "net_growth_mb": round(final - initial, 2),
        "growth_per_100_requests_mb": round((final - initial) * 100 / count, 3),
        "median_latency_ms": round(statistics.median(latencies), 2),
        "seconds": round(time.perf_counter() - started, 2),
        "external_provider_calls": 0,
    }, indent=2))


if __name__ == "__main__":
    main()
