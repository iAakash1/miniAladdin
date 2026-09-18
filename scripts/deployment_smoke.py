"""Safe production smoke checks for routes that previously failed after deploy.

The script never submits or cancels an order. Set CLERK_SMOKE_TOKEN only when
authenticated Paper reads and preview should be checked; the token is used as
an Authorization header and is never printed or persisted.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Probe:
    label: str
    base: str
    path: str
    method: str = "GET"
    body: Optional[dict[str, Any]] = None
    authenticated: bool = False
    timeout_seconds: int = 60


def request(probe: Probe, token: Optional[str]) -> tuple[int, dict[str, Any] | str]:
    headers = {"Accept": "application/json"}
    data = None
    if probe.body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(probe.body).encode("utf-8")
    if probe.authenticated and token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(
        f"{probe.base.rstrip('/')}{probe.path}",
        data=data,
        headers=headers,
        method=probe.method,
    )
    try:
        with urlopen(req, timeout=probe.timeout_seconds) as response:
            raw = response.read().decode("utf-8")
            try:
                return response.status, json.loads(raw)
            except json.JSONDecodeError:
                return response.status, raw[:160]
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body: dict[str, Any] | str = json.loads(raw)
        except json.JSONDecodeError:
            body = raw[:160]
        return exc.code, body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default="https://minialaddin-d8oe.onrender.com")
    parser.add_argument("--frontend", default="https://mini-aladding.vercel.app")
    parser.add_argument(
        "--inference", default="https://minialaddin-quant-inference.onrender.com"
    )
    args = parser.parse_args()
    token = os.getenv("CLERK_SMOKE_TOKEN")

    probes = [
        Probe("backend health", args.backend, "/api/health"),
        Probe("quant status", args.backend, "/api/quant/status"),
        Probe("portfolio methods", args.backend, "/api/quant/portfolio/methods"),
        Probe("portfolio", args.backend, "/api/quant/portfolio?method=risk_parity"),
        Probe("paper status", args.backend, "/api/paper/status"),
        Probe(
            "recommendations",
            args.backend,
            "/api/recommendations",
            timeout_seconds=180,
        ),
        Probe(
            "explore",
            args.backend,
            "/api/explore?category=overall&limit=1",
            timeout_seconds=180,
        ),
        Probe("frontend build", args.frontend, "/api/build"),
        Probe("inference health", args.inference, "/health"),
    ]
    if token:
        probes.extend([
            Probe("paper access", args.backend, "/api/paper/access", authenticated=True),
            Probe("paper account", args.backend, "/api/paper/account", authenticated=True),
            Probe("paper positions", args.backend, "/api/paper/positions", authenticated=True),
            Probe("paper orders", args.backend, "/api/paper/orders", authenticated=True),
            Probe(
                "paper preview",
                args.backend,
                "/api/paper/orders/preview",
                method="POST",
                body={
                    "symbol": "AAPL",
                    "qty": 1,
                    "side": "buy",
                    "order_type": "market",
                    "time_in_force": "day",
                },
                authenticated=True,
            ),
        ])

    failed = False
    for probe in probes:
        try:
            status, body = request(probe, token)
        except (URLError, TimeoutError) as exc:
            print(f"FAIL {probe.label}: network unavailable ({type(exc).__name__})")
            failed = True
            continue
        state = body.get("status") if isinstance(body, dict) else None
        suffix = f" status={state}" if state else ""
        print(f"{'PASS' if status == 200 else 'FAIL'} {probe.label}: HTTP {status}{suffix}")
        if status != 200:
            failed = True

    if not token:
        print("SKIP authenticated paper reads/preview: CLERK_SMOKE_TOKEN is unset")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
