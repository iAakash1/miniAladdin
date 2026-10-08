"""With every provider down, no route may answer as though it had data.

`test_provider_failure_matrix` proves each adapter reports its own failure.
This proves the surface above them keeps that promise: a route that cannot
reach any provider says so in a state a client can branch on, in strict JSON,
without a 500, and without a status that means "fine".

Every route here is driven with `offline_network` - each outbound HTTP call and
each native library call fails like a dead network - and the response is held to
three rules:

  1. **Answered.**  Never a 5xx. A dependency being down is an expected
     condition and the route's job is to describe it.
  2. **Strict JSON.**  `NaN` and `Infinity` are not JSON; a client that parses
     them leniently shows "NaN%", one that parses strictly drops the page.
  3. **Not a success.**  No `status`/`state` anywhere in the body reads as the
     system working (`ok`, `live`, `stable`, `current`, `healthy`, `available`)
     over data that cannot have come from a provider. Where a route legitimately
     reports a state of its own making, it is listed with the reason.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.index as api_module

#: States that mean "the thing worked". Under a total outage none of them may
#: describe provider-derived data.
SUCCESS_WORDS = {"ok", "live", "stable", "current", "healthy", "available", "fresh", "complete"}

#: (route, why a success word at the top level would be legitimate, if any).
#: Anything not annotated must be free of success words under outage.
ROUTES: list[tuple[str, str | None]] = [
    ("/api/chart/AAPL", None),
    ("/api/chart/AAPL?period=1y", None),
    ("/api/quotes?symbols=AAPL,MSFT,NVDA", None),
    ("/api/macro", None),
    ("/api/dashboard", None),
    ("/api/options/AAPL", None),
    ("/api/knowledge/AAPL", None),
    ("/api/graph/expand?node=company:AAPL", None),
    ("/api/graph/expand?node=product:iphone&label=iPhone", None),
    ("/api/graph/workspace?symbols=AAPL,MSFT", None),
    ("/api/company/AAPL/record", None),
    ("/api/screen?q=apple", None),
    ("/api/research/AAPL?fast=true", None),
]


@pytest.fixture
def client(offline_network, monkeypatch):
    api_module._macro_cache.clear()
    from src.services import company_intelligence, graph_service

    company_intelligence.reset_for_tests()
    graph_service.reset_for_tests()
    # Keyed vendors count as configured, so they are actually asked (and fail)
    # rather than being skipped as "not configured".
    for name in ("POLYGON_API_KEY", "FINNHUB_API_KEY", "TWELVEDATA_API_KEY", "FMP_API_KEY",
                 "MARKETSTACK_API_KEY", "TIINGO_API_KEY", "MASSIVE_API_KEY", "FRED_API_KEY",
                 "NEWSAPI_KEY", "GNEWS_API_KEY", "MARKETAUX_API_KEY", "TAVILY_API_KEY",
                 "EXA_API_KEY", "ALPHA_VANTAGE_KEY"):
        monkeypatch.setenv(name, "placeholder-credential-for-outage-tests")
    return TestClient(api_module.app, raise_server_exceptions=False)


def _strict(text: str) -> Any:
    def refuse(token: str):
        raise ValueError(f"non-JSON constant {token} in response")
    return json.loads(text, parse_constant=refuse)


def _walk(node: Any, path: str = ""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path}.{key}")
            if key in ("status", "state") and isinstance(value, str):
                yield f"{path}.{key}", value
    elif isinstance(node, list):
        for index, value in enumerate(node[:50]):
            yield from _walk(value, f"{path}[{index}]")


def _status_values(body: Any) -> list[tuple[str, str]]:
    return [item for item in _walk(body) if isinstance(item, tuple)]


@pytest.mark.parametrize("route,_why", ROUTES, ids=[r for r, _ in ROUTES])
def test_a_route_with_every_provider_down_answers_without_a_5xx(client, route, _why):
    response = client.get(route)
    assert response.status_code < 500, (
        f"{route} answered {response.status_code} under outage: {response.text[:300]}"
    )


@pytest.mark.parametrize("route,_why", ROUTES, ids=[r for r, _ in ROUTES])
def test_a_route_with_every_provider_down_answers_in_strict_json(client, route, _why):
    response = client.get(route)
    if response.status_code >= 500:
        pytest.skip("covered by the 5xx test")
    _strict(response.text)   # raises on NaN / Infinity / -Infinity


@pytest.mark.parametrize("route,why", ROUTES, ids=[r for r, _ in ROUTES])
def test_a_route_with_every_provider_down_never_reports_a_success_state(client, route, why):
    response = client.get(route)
    if response.status_code >= 400:
        return
    offenders = [
        (where, value) for where, value in _status_values(_strict(response.text))
        if value.strip().lower() in SUCCESS_WORDS
    ]
    if why:
        return
    assert not offenders, f"{route} reports success under total outage: {offenders[:5]}"
