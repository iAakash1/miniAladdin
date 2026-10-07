"""Smoke-test a private Cloud Run URL over real HTTP.

    python scripts/smoke_cloud_run.py <base-url> <expected-commit-prefix> <expected-revision>

    # a tagged zero-traffic revision, before it takes traffic
    python scripts/smoke_cloud_run.py https://release-abc1234---omnisignal-api-poc-<hash>-el.a.run.app \
        abc1234def012 omnisignal-api-poc-release-abc1234
    # the canonical service URL, after the traffic move
    python scripts/smoke_cloud_run.py https://omnisignal-api-poc-<number>.asia-south1.run.app \
        abc1234def012 omnisignal-api-poc-release-abc1234

The service is private. Cloud Run's IAM check is satisfied with your own
identity token in `X-Serverless-Authorization`, which Cloud Run consumes; the
application still sees an anonymous caller, so its own 401 and 403 answers can
be tested too. No token is printed or stored. No order is ever submitted: the
paper-trading mutations are sent without credentials and must be refused.

JSON is parsed strictly (NaN / Infinity fail). Exit status is non-zero on any
failure. Requires `gcloud` authenticated as someone with run.invoker.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import time
import urllib.error
import urllib.request

if len(sys.argv) != 4:
    print(__doc__)
    sys.exit(2)

BASE, WANT_COMMIT, WANT_REVISION = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
TOKEN = subprocess.run(["gcloud", "auth", "print-identity-token"], capture_output=True, text=True).stdout.strip()
if not TOKEN:
    print("could not obtain an identity token from gcloud")
    sys.exit(2)

failures: list[str] = []
passed = 0


def call(method, path, body=None, extra=None, timeout=120):
    headers = {"X-Serverless-Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    headers.update(extra or {})
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw, code = response.read(), response.status
    except urllib.error.HTTPError as error:
        raw, code = error.read(), error.code
    return code, raw, (time.time() - started) * 1000


def strict(raw):
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
    code, raw, elapsed = call(method, path, **kwargs)
    problems, body = [], None
    if code not in (expect if isinstance(expect, tuple) else (expect,)):
        problems.append(f"status {code}, wanted {expect}: {raw[:100]!r}")
    try:
        body = strict(raw)
        if non_finite(body):
            problems.append(f"non-finite value at {non_finite(body)[:3]}")
    except Exception as error:  # noqa: BLE001
        if code < 400:
            problems.append(f"invalid JSON: {error}")
    if check and body is not None and not problems:
        try:
            message = check(body)
            if message:
                problems.append(message)
        except Exception as error:  # noqa: BLE001
            problems.append(f"check error {type(error).__name__}: {error}")
    if problems:
        failures.append(f"{label}: {'; '.join(problems)}")
    else:
        passed += 1
    print(f"{'FAIL' if problems else 'PASS'} {code:3d} {elapsed:7.0f}ms {method:6} {path[:62]:62} {'; '.join(problems)}")
    return body


def has(symbol):
    return lambda b: None if any(r["symbol"].upper() in (symbol, symbol.replace(".", "-")) for r in b["results"]) \
        else f"{symbol} not in {[r['symbol'] for r in b['results']][:6]}"


# identity: this is the build and revision we think we are testing
probe("identity", "GET", "/api/health", 200, lambda b: None if (
    b["commit"].startswith(WANT_COMMIT) and b["revision"] == WANT_REVISION and b["status"] == "ok")
    else f"commit={b['commit']} revision={b['revision']}, wanted {WANT_COMMIT}* / {WANT_REVISION}")
probe("configured, not a POC", "GET", "/api/health", 200, lambda b: None if (
    b["persistence"]["database_configured"] and b["persistence"]["auth_configured"]
    and not b["persistence"]["missing_env"] and b["data_sources"]["fred"]) else f"unconfigured {b['persistence']}")

probe("no production model", "GET", "/api/quant/registry", 200, lambda b: None if (
    (b["by_status"]["production"], b["by_status"]["production_candidate"], b["by_status"]["validated"]) == (0, 0, 0)
    ) else f"registry {b['by_status']}")
probe("EXP-007 NO PRODUCTION CANDIDATE, holdout untouched", "GET", "/api/quant/selection/EXP-007", 200, lambda b: None if (
    b["verdict"]["status"] == "NO PRODUCTION CANDIDATE" and b["verdict"]["passed"] is False
    and b["holdout"]["touched"] is False and b["selected"]["config_id"] == "9d1651c56782"
    and b["selected"]["family"] == "hist_gradient_boosting") else "EXP-007 is not as recorded")
probe("quant status", "GET", "/api/quant/status", 200)
probe("experiments", "GET", "/api/quant/experiments", 200)

for query, symbol in (("AAPL", "AAPL"), ("MSFT", "MSFT"), ("NVDA", "NVDA"), ("GOOGL", "GOOGL"),
                      ("BRK.B", "BRK.B"), ("BRK-B", "BRK.B"), ("BRK%20B", "BRK.B")):
    probe(f"search {query}", "GET", f"/api/screen?q={query}", 200, has(symbol))
probe("BRK B ranks Berkshire first", "GET", "/api/screen?q=BRK%20B", 200, lambda b: None if (
    b["results"] and b["results"][0]["symbol"].upper() in ("BRK.B", "BRK-B")) else f"first: {[r['symbol'] for r in b['results']][:4]}")
probe("unknown ticker is not invented", "GET", "/api/screen?q=QZXWQZXW", 200, lambda b: None if not any(
    r["symbol"].upper() == "QZXWQZXW" for r in b["results"]) else "invented a result")

probe("chart", "GET", "/api/chart/AAPL?period=1mo", 200, lambda b: None if b.get("prices") else f"no prices: {json.dumps(b)[:120]}")
probe("invalid period rejected", "GET", "/api/chart/AAPL?period=bogus", (400, 422))
probe("unknown ticker has no chart", "GET", "/api/chart/ZZZZNOTREAL?period=1mo", (200, 400, 404), lambda b: None if not b.get("prices") else "prices for an unknown ticker")
probe("quotes: real and unknown", "GET", "/api/quotes?symbols=AAPL,ZZZZNOTREAL", 200, lambda b: None if (
    isinstance(b["quotes"]["AAPL"].get("price"), (int, float)) and b["quotes"]["AAPL"]["price"] > 0
    and "error" in b["quotes"]["ZZZZNOTREAL"]) else f"quotes {json.dumps(b['quotes'])[:160]}")
probe("macro (FRED)", "GET", "/api/macro", 200, lambda b: None if (
    b["stats"].get("source") == "fred" and b["stats"].get("stale") is False and b["stats"].get("observation_dates"))
    else f"macro not live from FRED: {json.dumps(b['stats'])[:160]}")

probe("providers health", "GET", "/api/providers/health", 200)
probe("providers capabilities", "GET", "/api/providers/capabilities", 200)
probe("paper status", "GET", "/api/paper/status", 200, lambda b: None if (
    b["environment"] == "paper" and "paper-api.alpaca.markets" in b["endpoint"]) else "not the paper host")

order = {"symbol": "AAPL", "qty": 1, "side": "buy", "type": "market", "time_in_force": "day"}
for method, path, body in (("GET", "/api/paper/account", None), ("GET", "/api/paper/positions", None),
                           ("POST", "/api/paper/orders/preview", order), ("POST", "/api/paper/orders", order),
                           ("DELETE", "/api/paper/orders/x", None), ("GET", "/api/watchlists", None)):
    probe(f"{method} {path} anonymous -> 401", method, path, 401, body=body)
    probe(f"{method} {path} forged token -> 401", method, path, 401, body=body, extra={"Authorization": "Bearer forged"})
code, _, _ = call("POST", "/api/metrics/reset")
if code not in (404, 405):
    probe("metrics reset refuses anonymous", "POST", "/api/metrics/reset", (401, 403))

print(f"\nCLOUD RUN SMOKE {BASE}: {passed} passed, {len(failures)} failed")
for failure in failures:
    print("  FAIL:", failure)
sys.exit(1 if failures else 0)
