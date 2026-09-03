"""The frontend must read fields the payloads actually carry.

Four bugs of one family shipped and were caught by looking at rendered pages,
not by any test:

  the timeline read `status` and `note` on a status-history row that records
  `from`, `to` and `reason` — every transition rendered "status → undefined"

  the market index table read `change` on a row that records `change_1d` and
  `change_1w` — every index showed an em dash where its move belongs

  the breadth chart read `value` on a series of `{date, score}` — ninety days
  of history were discarded and the panel said "no observations"

  the providers workspace treated a map of capability-to-vendor-list as a flat
  vendor map — its column headers became the payload's own top-level keys, its
  rows became array indices, and every cell an em dash

Each was well-formed TypeScript reading a field that was never there. The type
declaration was the bug, so the type system could not help; only the payload
can settle it.

These pin the field names for the surfaces whose payloads are cheap to fetch.
They are not exhaustive, and they are not meant to be — they hold the four that
broke, so the fifth has to be a new mistake.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.index import app

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "dashboard" / "src" / "components" / "terminal"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _keys(rows: object) -> set[str]:
    if isinstance(rows, dict):
        return set(rows)
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return set(rows[0])
    return set()


def test_provider_health_is_nested_by_capability(client: TestClient) -> None:
    """The shape the workspace was rewritten against."""
    payload = client.get("/api/providers/health").json()
    providers = payload.get("providers")
    assert isinstance(providers, dict), "provider health is no longer keyed by capability"
    assert providers, "no capabilities reported"

    for capability, vendors in providers.items():
        assert isinstance(vendors, list), (
            f"{capability} is not a list of vendors. The workspace iterates it as one; "
            f"treating a list as a vendor object is what produced array indices as row ids."
        )

    sample = next(iter(providers.values()))[0]
    for field in ("vendor", "configured", "cooling_down", "requests", "failures",
                  "rate_limited", "success_pct", "avg_latency_ms", "last_error"):
        assert field in sample, f"provider health no longer reports {field!r}"


def test_the_providers_workspace_reads_those_fields() -> None:
    source = (UI / "providers" / "ProviderMatrix.tsx").read_text()
    for field in ("vendor", "configured", "cooling_down", "requests", "failures",
                  "rate_limited", "avg_latency_ms", "last_error"):
        assert f"v.{field}" in source or f"{field}:" in source, (
            f"the providers workspace no longer reads {field!r}"
        )
    # The fields it used to invent.
    for ghost in ("e.healthy", "e.calls", "e.cooldown_seconds"):
        assert ghost not in source, f"{ghost} is not a field provider health carries"


def test_breadth_history_is_date_and_score(client: TestClient) -> None:
    payload = client.get("/api/dashboard").json()
    history = (payload.get("breadth") or {}).get("history")
    if not isinstance(history, list) or not history or not isinstance(history[0], dict):
        pytest.skip("breadth history is not a list of records in this environment")
    assert _keys(history) >= {"date", "score"}, (
        "breadth history no longer carries date and score; the market workspace "
        "reads both, and reading `value` there discarded the whole series once"
    )


def test_the_market_workspace_reads_score_not_value() -> None:
    source = (UI / "market" / "MarketWorkspace.tsx").read_text()
    assert "p.score" in source, "the breadth chart no longer reads `score`"
    assert "date: string; value: number" not in source, (
        "the breadth series is declared as {date, value} again, which is the "
        "declaration that discarded ninety days of history"
    )


def test_the_market_index_table_reads_the_recorded_change_fields() -> None:
    source = (UI / "market" / "MarketWorkspace.tsx").read_text()
    assert "i.change_1d" in source, "the index table no longer reads change_1d"
    assert "n(i.change)" not in source, (
        "the index table reads `change`, which the dashboard payload does not carry"
    )


def test_the_timeline_reads_transitions_not_a_status_field() -> None:
    source = (UI / "timeline" / "ResearchTimeline.tsx").read_text()
    assert "h.to" in source and "h.reason" in source, (
        "the timeline no longer reads the recorded transition fields"
    )
    assert "h.status" not in source and "h.note" not in source, (
        "the timeline reads `status`/`note`, which a status-history row does not "
        "carry — that rendered every transition as 'status → undefined'"
    )
