"""Reproducible import and endpoint RSS profiler for the production backend."""

from __future__ import annotations

import argparse
import gc
import importlib
import json
import os
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

IMPORT_GROUPS = {
    "numpy": ("numpy",),
    "pandas": ("pandas",),
    "scipy": ("scipy",),
    "pyarrow": ("pyarrow",),
    "yfinance": ("yfinance",),
    "supabase": ("supabase",),
    "cryptography": ("cryptography",),
    "langgraph": ("langgraph",),
    "providers": ("src.providers",),
    "scoring": ("src.scoring",),
    "agents": ("src.agents.graph",),
    "quant_services": ("src.services.quant_service", "src.services.quant_portfolio_service"),
    "risk_engine": ("src.risk_analysis",),
    "news": ("src.news_api", "src.services.news_scoring"),
    "fundamentals": ("src.services.fundamentals_data",),
    "observability": ("src.observability",),
    "database": ("src.services.database",),
}

ENDPOINTS = {
    "health": "/api/health",
    "system_health": "/api/system/health",
    "quant_status": "/api/quant/status",
    "model_lab": "/api/quant/model-lab",
    "experiments": "/api/quant/experiments",
    "factors": "/api/factors?universe=mega30",
    "research_fixture": "/api/research/AAPL?fast=true",
}


def rss_mb() -> float:
    status = Path("/proc/self/status")
    if status.exists():
        for row in status.read_text(encoding="utf-8").splitlines():
            if row.startswith("VmRSS:"):
                return round(float(row.split()[1]) / 1024, 2)
    try:
        result = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(os.getpid())],
            capture_output=True, text=True, check=True, timeout=2,
        )
        return round(float(result.stdout.strip()) / 1024, 2)
    except Exception:  # noqa: BLE001
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024, 2)


def peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024, 2)


def child_import(name: str) -> None:
    before = rss_mb()
    started = time.perf_counter()
    for module in IMPORT_GROUPS[name]:
        importlib.import_module(module)
    gc.collect()
    after = rss_mb()
    print(json.dumps({
        "component": name, "rss_before_mb": before, "rss_after_mb": after,
        "delta_mb": round(after - before, 2), "peak_rss_mb": peak_rss_mb(),
        "seconds": round(time.perf_counter() - started, 4),
    }))


def _install_research_fixture(app) -> None:
    for route in app.routes:
        if getattr(route, "path", None) == "/api/research/{ticker}":
            def fixture(ticker: str, fast: bool = True, clerk_user=None):
                return {
                    "ticker": ticker, "verdict": "HOLD", "confidence": 50,
                    "risk_level": "MEDIUM", "evidence": [], "fixture": True,
                }
            route.dependant.call = fixture
            return
    raise RuntimeError("research route not found")


def child_endpoint(name: str, repetitions: int) -> None:
    before_import = rss_mb()
    started = time.perf_counter()
    import api.index as api
    from fastapi.testclient import TestClient

    after_import = rss_mb()
    if name == "research_fixture":
        _install_research_fixture(api.app)
    timings: list[float] = []
    sizes: list[int] = []
    with TestClient(api.app, raise_server_exceptions=False) as client:
        after_startup = rss_mb()
        before_request = rss_mb()
        for _ in range(repetitions):
            request_started = time.perf_counter()
            response = client.get(ENDPOINTS[name])
            timings.append((time.perf_counter() - request_started) * 1000)
            sizes.append(len(response.content))
            if response.status_code >= 500:
                raise RuntimeError(f"{name} returned {response.status_code}")
        gc.collect()
        after_request = rss_mb()
    print(json.dumps({
        "endpoint": name,
        "fresh_rss_mb": before_import,
        "after_api_import_mb": after_import,
        "after_startup_mb": after_startup,
        "before_request_mb": before_request,
        "after_request_mb": after_request,
        "request_delta_mb": round(after_request - before_request, 2),
        "peak_rss_mb": peak_rss_mb(),
        "median_latency_ms": round(statistics.median(timings), 2),
        "max_response_bytes": max(sizes),
        "total_seconds": round(time.perf_counter() - started, 3),
    }))


def _run_child(*arguments: str) -> dict:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), *arguments],
        cwd=ROOT, env=env, capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("imports")
    endpoints = commands.add_parser("endpoints")
    endpoints.add_argument("--repetitions", type=int, default=3)
    child_i = commands.add_parser("child-import")
    child_i.add_argument("name", choices=IMPORT_GROUPS)
    child_e = commands.add_parser("child-endpoint")
    child_e.add_argument("name", choices=ENDPOINTS)
    child_e.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()

    if args.command == "child-import":
        child_import(args.name)
    elif args.command == "child-endpoint":
        child_endpoint(args.name, args.repetitions)
    elif args.command == "imports":
        print(json.dumps([_run_child("child-import", name) for name in IMPORT_GROUPS], indent=2))
    else:
        print(json.dumps([
            _run_child("child-endpoint", name, "--repetitions", str(args.repetitions))
            for name in ENDPOINTS
        ], indent=2))


if __name__ == "__main__":
    main()
