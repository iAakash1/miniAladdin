"""Start the API with no credentials and no .env, and exercise it over ASGI.

    git archive HEAD | tar -x -C /tmp/clean && cd /tmp/clean
    env -i PATH="$PATH" HOME=/tmp PYTHONPATH=. python scripts/smoke_credential_free.py

Run it from a clean checkout with an empty environment, so nothing from a
developer's `.env` can make it pass. It proves four things:

  * the app imports and starts with no configuration at all;
  * research truth holds from the shipped artifacts (no production model,
    EXP-007 NO PRODUCTION CANDIDATE, holdout untouched);
  * a provider with no key reports unavailable rather than inventing a value;
  * every protected route is refused. With authentication unconfigured the
    answer is 503 — the server cannot verify anyone, so it admits no one — and
    never a 2xx.

JSON is parsed strictly, so NaN or Infinity in a body fails the probe.
No order is ever submitted. Exit status is non-zero on any failure.
"""

from __future__ import annotations

import json
import math
import sys
import time

from fastapi.testclient import TestClient

import api.index as api

client = TestClient(api.app, raise_server_exceptions=False)
failures: list[str] = []
passed = 0


def strict(raw: bytes):
    def reject(constant):
        raise ValueError(f"non-finite constant {constant}")

    return json.loads(raw, parse_constant=reject)


def non_finite(value, path="$"):
    found = []
    if isinstance(value, float) and not math.isfinite(value):
        found.append(path)
    elif isinstance(value, dict):
        for key, item in value.items():
            found += non_finite(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found += non_finite(item, f"{path}[{index}]")
    return found


def probe(label, method, path, expect, check=None, **kwargs):
    global passed
    started = time.time()
    response = client.request(method, path, **kwargs)
    elapsed = (time.time() - started) * 1000
    problems, body = [], None
    if response.status_code not in (expect if isinstance(expect, tuple) else (expect,)):
        problems.append(f"status {response.status_code}, wanted {expect}")
    try:
        body = strict(response.content)
        if non_finite(body):
            problems.append(f"non-finite value at {non_finite(body)[:3]}")
    except Exception as error:  # noqa: BLE001
        if response.status_code < 400:
            problems.append(f"invalid JSON: {error}")
    if check and body is not None and not problems:
        message = check(body)
        if message:
            problems.append(message)
    if problems:
        failures.append(f"{label}: {'; '.join(problems)}")
    else:
        passed += 1
    print(f"{'FAIL' if problems else 'PASS'} {response.status_code:3d} {elapsed:6.0f}ms {method:6} {path[:60]:60} {'; '.join(problems)}")


probe("health", "GET", "/api/health", 200, lambda b: None if (
    b.get("status") == "ok" and b["data_sources"]["fred"] is False
    and b["data_sources"]["news_api"] is False and b["persistence"]["database_configured"] is False
    and "commit" in b and "revision" in b) else f"unexpected health {b}")
probe("system health", "GET", "/api/system/health", 200)

probe("no production model", "GET", "/api/quant/registry", 200, lambda b: None if (
    b["by_status"].get("production") == 0 and b["by_status"].get("production_candidate") == 0
    and b["by_status"].get("validated") == 0) else f"registry {b['by_status']}")
probe("EXP-007 verdict", "GET", "/api/quant/selection/EXP-007", 200, lambda b: None if (
    b["verdict"]["status"] == "NO PRODUCTION CANDIDATE" and b["verdict"]["passed"] is False
    and b["holdout"]["touched"] is False and b["selected"]["config_id"] == "9d1651c56782")
    else "EXP-007 is not as recorded")
probe("quant status", "GET", "/api/quant/status", 200)
probe("experiments", "GET", "/api/quant/experiments", 200)

probe("macro without FRED is unavailable, not invented", "GET", "/api/macro", 200, lambda b: None if (
    b.get("risk_multiplier") in (None,) or b.get("stats", {}).get("status") in ("UNAVAILABLE", "unavailable")
    or b.get("stats", {}).get("stale")) else f"macro invented a regime without a key: {json.dumps(b)[:160]}")

for query, wanted in (("AAPL", "AAPL"), ("BRK B", "BRK.B"), ("BRK-B", None), ("NVDA", "NVDA")):
    probe(f"screen {query}", "GET", f"/api/screen?q={query}", 200, (lambda b, w=wanted: None if (
        w is None or any(r["symbol"].upper() == w for r in b.get("results", []))) else f"{w} missing"))
probe("empty query rejected", "GET", "/api/screen?q=", 422)
probe("invalid chart period rejected", "GET", "/api/chart/AAPL?period=bogus", (400, 422))
probe("unknown ticker has no chart", "GET", "/api/chart/ZZZZNOTREAL?period=1mo", (200, 400, 404, 422, 502, 503))
probe("quotes for an unknown symbol are errors", "GET", "/api/quotes?symbols=ZZZZNOTREAL", 200, lambda b: None if all(
    "error" in v for v in b["quotes"].values()) else "an unknown symbol got a price")

probe("providers health", "GET", "/api/providers/health", 200)
probe("providers capabilities", "GET", "/api/providers/capabilities", 200)
probe("paper status is public and holds no secret", "GET", "/api/paper/status", 200, lambda b: None if (
    b["configured"] is False and "paper-api.alpaca.markets" in b["endpoint"]
    and not any(word in json.dumps(b).lower() for word in ("secret", "key_id", "apca-api"))) else "paper status unsafe")

order = {"symbol": "AAPL", "qty": 1, "side": "buy", "type": "market", "time_in_force": "day"}
for method, path, body in (
    ("GET", "/api/paper/account", None), ("GET", "/api/paper/positions", None), ("GET", "/api/paper/orders", None),
    ("POST", "/api/paper/orders/preview", order), ("POST", "/api/paper/orders", order),
    ("DELETE", "/api/paper/orders/x", None), ("GET", "/api/watchlists", None), ("GET", "/api/portfolio", None),
    ("GET", "/api/history", None), ("POST", "/api/metrics/reset", None), ("GET", "/api/admin/diagnostics", None),
):
    probe(f"{method} {path} is refused", method, path, (401, 503), json=body)
    probe(f"{method} {path} refuses a forged token", method, path, (401, 503), json=body,
          headers={"Authorization": "Bearer forged"})

print(f"\nCREDENTIAL-FREE SMOKE: {passed} passed, {len(failures)} failed")
for failure in failures:
    print("  FAIL:", failure)
sys.exit(1 if failures else 0)
