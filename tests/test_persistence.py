"""
Persistence layer tests — hermetic (no network, no real Supabase).

Covers: the repository layer against an in-memory fake of the supabase-py
fluent API, the REST endpoints through TestClient with a stubbed Clerk user,
per-user scoping, graceful 503 degradation, the deterministic comparison
math, and static validation of the schema migration.
"""

from __future__ import annotations

import itertools
import re
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient

import api.index as api_module
from src.services import database
from src.services.clerk_auth import require_clerk_user
from src.services.database.repositories import (
    AnalysisRepository,
    PortfolioRepository,
    PreferencesRepository,
    ProfilesRepository,
    WatchlistsRepository,
)
from src.services.database.repositories.analysis import _family_deltas, _factor_deltas

# ── In-memory fake of the supabase-py fluent client ──────────────────────────

_clock = itertools.count(1)


def _stamp() -> str:
    return f"2026-07-18T00:00:{next(_clock):02d}.000000+00:00"


class FakeQuery:
    def __init__(self, store: dict[str, list[dict]], table: str) -> None:
        self._store = store
        self._table = table
        self._action: tuple[str, Any, Any] = ("select", None, None)
        self._filters: list[tuple[str, str, Any]] = []
        self._or: Optional[str] = None
        self._orders: list[tuple[str, bool]] = []
        self._range: Optional[tuple[int, int]] = None
        self._limit: Optional[int] = None
        self._count: Optional[str] = None
        self._columns: Optional[list[str]] = None

    # actions
    def select(self, cols: str = "*", count: Optional[str] = None) -> "FakeQuery":
        self._action = ("select", None, None)
        self._columns = None if cols.strip() == "*" else [c.strip() for c in cols.split(",")]
        self._count = count
        return self

    def insert(self, payload: Any) -> "FakeQuery":
        self._action = ("insert", payload, None)
        return self

    def upsert(self, payload: dict, on_conflict: str = "") -> "FakeQuery":
        self._action = ("upsert", payload, on_conflict)
        return self

    def update(self, patch: dict) -> "FakeQuery":
        self._action = ("update", patch, None)
        return self

    def delete(self) -> "FakeQuery":
        self._action = ("delete", None, None)
        return self

    # filters / modifiers
    def eq(self, col: str, val: Any) -> "FakeQuery":
        self._filters.append(("eq", col, val))
        return self

    def in_(self, col: str, vals: list) -> "FakeQuery":
        self._filters.append(("in", col, list(vals)))
        return self

    def gte(self, col: str, val: Any) -> "FakeQuery":
        self._filters.append(("gte", col, val))
        return self

    def lte(self, col: str, val: Any) -> "FakeQuery":
        self._filters.append(("lte", col, val))
        return self

    def or_(self, expr: str) -> "FakeQuery":
        self._or = expr
        return self

    def order(self, col: str, desc: bool = False) -> "FakeQuery":
        self._orders.append((col, desc))
        return self

    def range(self, start: int, end: int) -> "FakeQuery":
        self._range = (start, end)
        return self

    def limit(self, n: int) -> "FakeQuery":
        self._limit = n
        return self

    # execution
    def _matches(self, row: dict) -> bool:
        for op, col, val in self._filters:
            have = row.get(col)
            if op == "eq" and have != val:
                return False
            if op == "in" and have not in val:
                return False
            if op == "gte" and not (have is not None and str(have) >= str(val)):
                return False
            if op == "lte" and not (have is not None and str(have) <= str(val)):
                return False
        if self._or:
            def clause_ok(clause: str) -> bool:
                col, op, pattern = clause.split(".", 2)
                if op != "ilike":
                    return False
                needle = pattern.strip("%").lower()
                return needle in str(row.get(col) or "").lower()

            if not any(clause_ok(c) for c in self._or.split(",")):
                return False
        return True

    def _defaults(self, row: dict) -> dict:
        out = dict(row)
        out.setdefault("id", uuid.uuid4().hex)
        now = _stamp()
        for col in ("created_at", "updated_at", "added_at", "saved_at"):
            out.setdefault(col, now)
        return out

    def execute(self) -> SimpleNamespace:
        rows = self._store.setdefault(self._table, [])
        action, payload, conflict = self._action

        if action == "insert":
            payloads = payload if isinstance(payload, list) else [payload]
            created = [self._defaults(p) for p in payloads]
            rows.extend(created)
            return SimpleNamespace(data=[dict(r) for r in created], count=None)

        if action == "upsert":
            keys = [k.strip() for k in (conflict or "").split(",") if k.strip()]
            target = None
            if keys:
                for row in rows:
                    if all(row.get(k) == payload.get(k) for k in keys):
                        target = row
                        break
            if target is not None:
                target.update({k: v for k, v in payload.items()})
                target["updated_at"] = _stamp()
                return SimpleNamespace(data=[dict(target)], count=None)
            created = self._defaults(payload)
            rows.append(created)
            return SimpleNamespace(data=[dict(created)], count=None)

        if action == "update":
            updated = []
            for row in rows:
                if self._matches(row):
                    row.update(payload)
                    row["updated_at"] = _stamp()
                    updated.append(dict(row))
            return SimpleNamespace(data=updated, count=None)

        if action == "delete":
            kept, removed = [], []
            for row in rows:
                (removed if self._matches(row) else kept).append(row)
            self._store[self._table] = kept
            # cascade: watchlist_items follow their watchlist
            if self._table == "watchlists" and removed:
                gone = {r["id"] for r in removed}
                self._store["watchlist_items"] = [
                    i for i in self._store.get("watchlist_items", [])
                    if i["watchlist_id"] not in gone
                ]
            if self._table == "analysis_history" and removed:
                gone = {r["id"] for r in removed}
                self._store["saved_reports"] = [
                    s for s in self._store.get("saved_reports", [])
                    if s["analysis_history_id"] not in gone
                ]
            return SimpleNamespace(data=[dict(r) for r in removed], count=None)

        # select
        result = [dict(r) for r in rows if self._matches(r)]
        for col, desc in reversed(self._orders):
            result.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
        total = len(result)
        if self._range is not None:
            start, end = self._range
            result = result[start : end + 1]
        elif self._limit is not None:
            result = result[: self._limit]
        if self._columns is not None:
            result = [{c: row.get(c) for c in self._columns} for row in result]
        return SimpleNamespace(
            data=result, count=total if self._count == "exact" else None
        )


class FakeSupabase:
    def __init__(self) -> None:
        self.store: dict[str, list[dict]] = {}

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self.store, name)


# ── fixtures ─────────────────────────────────────────────────────────────────

USER_A = "user_aaa"
USER_B = "user_bbb"


@pytest.fixture()
def fake() -> FakeSupabase:
    return FakeSupabase()


def _research_payload(
    ticker: str = "NVDA",
    verdict: str = "Buy",
    confidence: int = 70,
    momentum: float = 0.10,
    news: float = 0.02,
    srm: float = 1.0,
    risk_score: int = 40,
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "verdict": verdict,
        "confidence": confidence,
        "risk_level": "MEDIUM",
        "technicals": {"company_name": f"{ticker} Corp"},
        "macro": {"risk_multiplier": srm},
        "quant": {
            "raw_score": round(momentum + news, 4),
            "risk_score": risk_score,
            "macro_gate": 1.0,
            "factors": [
                {"name": "mom_12_1", "family": "momentum", "score": 1.0, "contribution": momentum},
                {"name": "news_sent", "family": "news", "score": 0.5, "contribution": news},
            ],
        },
        "ai": {"executive_summary": "Summary."},
    }


# ── repository tests ─────────────────────────────────────────────────────────

class TestProfiles:
    def test_sync_creates_then_updates(self, fake):
        repo = ProfilesRepository(fake)
        created = repo.sync(USER_A, email="a@x.com", full_name="A")
        assert created["clerk_user_id"] == USER_A
        repo.sync(USER_A, email="new@x.com")
        assert repo.get(USER_A)["email"] == "new@x.com"
        assert len(fake.store["profiles"]) == 1

    def test_get_missing(self, fake):
        assert ProfilesRepository(fake).get(USER_A) is None


class TestWatchlists:
    def test_create_normalizes_and_dedupes(self, fake):
        repo = WatchlistsRepository(fake)
        created = repo.create(USER_A, "  Tech  ", ["nvda", "NVDA", "aapl!", ""])
        assert created["name"] == "Tech"
        assert created["tickers"] == ["NVDA", "AAPL"]

    def test_list_scoped_to_user(self, fake):
        repo = WatchlistsRepository(fake)
        repo.create(USER_A, "Mine", ["NVDA"])
        repo.create(USER_B, "Theirs", ["TSLA"])
        mine = repo.list_with_items(USER_A)
        assert [w["name"] for w in mine] == ["Mine"]
        assert mine[0]["tickers"] == ["NVDA"]

    def test_mutations_require_ownership(self, fake):
        repo = WatchlistsRepository(fake)
        wl = repo.create(USER_A, "Mine")
        assert repo.rename(USER_B, wl["id"], "Stolen") is False
        assert repo.delete(USER_B, wl["id"]) is False
        assert repo.add_ticker(USER_B, wl["id"], "NVDA") is False
        assert repo.rename(USER_A, wl["id"], "Renamed") is True

    def test_add_ticker_idempotent(self, fake):
        repo = WatchlistsRepository(fake)
        wl = repo.create(USER_A, "Mine")
        assert repo.add_ticker(USER_A, wl["id"], "nvda") is True
        assert repo.add_ticker(USER_A, wl["id"], "NVDA") is True
        assert repo.list_with_items(USER_A)[0]["tickers"] == ["NVDA"]

    def test_delete_cascades_items(self, fake):
        repo = WatchlistsRepository(fake)
        wl = repo.create(USER_A, "Mine", ["NVDA", "AAPL"])
        assert repo.delete(USER_A, wl["id"]) is True
        assert fake.store.get("watchlist_items", []) == []


class TestAnalysisHistory:
    def test_record_and_list(self, fake):
        repo = AnalysisRepository(fake)
        for verdict in ("Buy", "Hold", "Sell"):
            repo.record(USER_A, _research_payload(verdict=verdict))
        repo.record(USER_B, _research_payload(verdict="Buy"))
        page = repo.list(USER_A)
        assert page["total"] == 3
        assert all("quant_payload" not in item for item in page["items"])

    def test_filters_and_pagination(self, fake):
        repo = AnalysisRepository(fake)
        repo.record(USER_A, _research_payload(ticker="NVDA", verdict="Buy"))
        repo.record(USER_A, _research_payload(ticker="AAPL", verdict="Sell"))
        assert repo.list(USER_A, ticker="nvda ")["total"] == 1
        assert repo.list(USER_A, verdict="Sell")["total"] == 1
        assert repo.list(USER_A, search="aapl")["total"] == 1
        page = repo.list(USER_A, page=2, page_size=1)
        assert page["total"] == 2 and len(page["items"]) == 1

    def test_get_and_delete_scoped(self, fake):
        repo = AnalysisRepository(fake)
        hid = repo.record(USER_A, _research_payload())
        assert repo.get(USER_B, hid) is None
        assert repo.delete(USER_B, hid) is False
        assert repo.delete(USER_A, hid) is True

    def test_compare_orders_and_deltas(self, fake):
        repo = AnalysisRepository(fake)
        first = repo.record(
            USER_A, _research_payload(verdict="Hold", confidence=50, momentum=0.02, srm=1.0)
        )
        second = repo.record(
            USER_A, _research_payload(verdict="Buy", confidence=70, momentum=0.12, srm=1.2)
        )
        # ids passed newest-first — compare() must reorder chronologically
        result = repo.compare(USER_A, second, first)
        assert result["before"]["verdict"] == "Hold"
        assert result["after"]["verdict"] == "Buy"
        momentum = next(f for f in result["families"] if f["family"] == "momentum")
        assert momentum["delta"] == pytest.approx(0.10)
        assert momentum["changed"] is True
        news = next(f for f in result["families"] if f["family"] == "news")
        assert news["changed"] is False
        assert result["macro"]["srm_delta"] == pytest.approx(0.2)

    def test_compare_missing_row(self, fake):
        repo = AnalysisRepository(fake)
        hid = repo.record(USER_A, _research_payload())
        assert repo.compare(USER_A, hid, "nonexistent") is None


class TestSavedReports:
    def test_save_list_update_delete(self, fake):
        repo = AnalysisRepository(fake)
        hid = repo.record(USER_A, _research_payload())
        saved = repo.save_report(USER_A, hid, custom_title="My NVDA take", notes="watch margins")
        assert saved is not None
        listed = repo.list_saved(USER_A)
        assert listed[0]["analysis"]["ticker"] == "NVDA"
        updated = repo.update_saved(USER_A, saved["id"], notes="updated")
        assert updated["notes"] == "updated"
        assert repo.delete_saved(USER_A, saved["id"]) is True

    def test_cannot_bookmark_foreign_history(self, fake):
        repo = AnalysisRepository(fake)
        hid = repo.record(USER_A, _research_payload())
        assert repo.save_report(USER_B, hid) is None


class TestPortfolio:
    def test_upsert_merges_same_ticker(self, fake):
        repo = PortfolioRepository(fake)
        repo.upsert(USER_A, "nvda", 10, 500.0)
        repo.upsert(USER_A, "NVDA", 15, 520.0)
        positions = repo.list(USER_A)
        assert len(positions) == 1
        assert positions[0]["shares"] == 15

    def test_validation_and_scoping(self, fake):
        repo = PortfolioRepository(fake)
        assert repo.upsert(USER_A, "NVDA", 0, 500.0) is None
        pos = repo.upsert(USER_A, "NVDA", 5, 500.0)
        assert repo.update(USER_B, pos["id"], shares=1) is None
        assert repo.delete(USER_B, pos["id"]) is False
        assert repo.update(USER_A, pos["id"], average_price=510.0)["average_price"] == 510.0


class TestPreferences:
    def test_patch_upserts_and_validates_theme(self, fake):
        repo = PreferencesRepository(fake)
        assert repo.get(USER_A) is None
        prefs = repo.patch(USER_A, {"theme": "dark", "bogus": "x"})
        assert prefs["theme"] == "dark"
        assert "bogus" not in prefs
        prefs = repo.patch(USER_A, {"theme": "neon"})
        assert prefs["theme"] == "dark"  # invalid theme ignored, row unchanged


# ── comparison helpers directly ──────────────────────────────────────────────

def test_factor_deltas_flags_appearing_factor():
    row_a = {"quant_payload": {"quant": {"factors": [
        {"name": "mom", "family": "momentum", "score": 1, "contribution": 0.05},
    ]}}}
    row_b = {"quant_payload": {"quant": {"factors": [
        {"name": "mom", "family": "momentum", "score": 1, "contribution": 0.05},
        {"name": "pead", "family": "fundamental", "score": 1, "contribution": 0.03},
    ]}}}
    deltas = _factor_deltas(row_a, row_b)
    pead = next(d for d in deltas if d["name"] == "pead")
    assert pead["changed"] is True and pead["before"] is None
    mom = next(d for d in deltas if d["name"] == "mom")
    assert mom["changed"] is False


def test_family_deltas_sum_by_family():
    def row(c1, c2):
        return {"quant_payload": {"quant": {"factors": [
            {"name": "a", "family": "momentum", "score": 1, "contribution": c1},
            {"name": "b", "family": "momentum", "score": 1, "contribution": c2},
        ]}}}
    families = _family_deltas(row(0.01, 0.02), row(0.05, 0.06))
    momentum = next(f for f in families if f["family"] == "momentum")
    assert momentum["before"] == pytest.approx(0.03)
    assert momentum["after"] == pytest.approx(0.11)


# ── REST API through the app ─────────────────────────────────────────────────

@pytest.fixture()
def client(fake):
    api_module.app.dependency_overrides[require_clerk_user] = lambda: USER_A
    database.set_client_for_testing(fake)
    try:
        yield TestClient(api_module.app)
    finally:
        api_module.app.dependency_overrides.pop(require_clerk_user, None)
        database.set_client_for_testing(None)


class TestPersistenceApi:
    def test_watchlist_crud_flow(self, client):
        created = client.post("/api/watchlists", json={"name": "Tech", "tickers": ["nvda"]})
        assert created.status_code == 201
        wl = created.json()
        assert wl["tickers"] == ["NVDA"]

        assert client.post(f"/api/watchlists/{wl['id']}/tickers", json={"ticker": "aapl"}).status_code == 201
        listed = client.get("/api/watchlists").json()["watchlists"]
        assert listed[0]["tickers"] == ["NVDA", "AAPL"]

        assert client.patch(f"/api/watchlists/{wl['id']}", json={"name": "Semis"}).status_code == 200
        assert client.delete(f"/api/watchlists/{wl['id']}/tickers/NVDA").status_code == 200
        assert client.delete(f"/api/watchlists/{wl['id']}").status_code == 200
        assert client.get("/api/watchlists").json()["watchlists"] == []

    def test_portfolio_crud_flow(self, client):
        pos = client.post(
            "/api/portfolio", json={"ticker": "msft", "shares": 3, "average_price": 400}
        )
        assert pos.status_code == 201
        pid = pos.json()["id"]
        patched = client.patch(f"/api/portfolio/{pid}", json={"shares": 4})
        assert patched.json()["shares"] == 4
        assert client.delete(f"/api/portfolio/{pid}").status_code == 200

    def test_history_and_saved_flow(self, client, fake):
        hid = AnalysisRepository(fake).record(USER_A, _research_payload())
        AnalysisRepository(fake).record(USER_B, _research_payload(ticker="TSLA"))

        page = client.get("/api/history").json()
        assert page["total"] == 1  # scoped: USER_B's row invisible

        detail = client.get(f"/api/history/{hid}")
        assert detail.status_code == 200
        assert detail.json()["quant_payload"]["ticker"] == "NVDA"

        saved = client.post("/api/saved-reports", json={"analysis_history_id": hid, "notes": "n"})
        assert saved.status_code == 201
        assert client.get("/api/saved-reports").json()["saved"][0]["notes"] == "n"

    def test_compare_endpoint(self, client, fake):
        repo = AnalysisRepository(fake)
        a = repo.record(USER_A, _research_payload(verdict="Hold", confidence=50))
        b = repo.record(USER_A, _research_payload(verdict="Buy", confidence=72))
        result = client.get("/api/history/compare", params={"a": a, "b": b})
        assert result.status_code == 200
        body = result.json()
        assert body["before"]["verdict"] == "Hold"
        assert body["after"]["confidence"] == 72

    def test_preferences_roundtrip(self, client):
        assert client.get("/api/preferences").json() == {}
        patched = client.patch("/api/preferences", json={"theme": "dark"})
        assert patched.json()["theme"] == "dark"

    def test_profile_sync(self, client):
        synced = client.post("/api/profile/sync", json={"email": "a@x.com"})
        assert synced.status_code == 200
        assert client.get("/api/profile").json()["email"] == "a@x.com"

    def test_degrades_to_503_without_database(self, client, monkeypatch):
        import api.persistence as persistence_module

        monkeypatch.setattr(persistence_module.database, "get_client", lambda: None)
        response = client.get("/api/watchlists")
        assert response.status_code == 503
        assert "analysis still works" in response.json()["detail"]


# ── migration validation ─────────────────────────────────────────────────────

MIGRATION = Path(__file__).parent.parent / "supabase" / "migrations" / "20260718000000_persistence_layer.sql"
TABLES = [
    "profiles", "watchlists", "watchlist_items", "analysis_history",
    "saved_reports", "portfolio_positions", "user_preferences",
]


class TestMigration:
    def test_migration_file_exists(self):
        assert MIGRATION.exists()

    def test_all_tables_created_with_rls(self):
        sql = MIGRATION.read_text()
        for table in TABLES:
            assert f"create table public.{table}" in sql, table
            assert re.search(
                rf"alter table public\.{table}\s+enable row level security", sql
            ), f"RLS missing for {table}"

    def test_clerk_scoping_and_constraints(self):
        sql = MIGRATION.read_text()
        assert sql.count("clerk_user_id") >= 8
        assert "unique (watchlist_id, ticker)" in sql
        assert "unique (clerk_user_id, ticker)" in sql
        assert "on delete cascade" in sql
        assert "revoke all" in sql and "from anon, authenticated" in sql

    def test_required_indexes(self):
        sql = MIGRATION.read_text()
        for index in (
            "analysis_history_user_created_idx",
            "analysis_history_ticker_idx",
            "watchlists_clerk_user_id_idx",
            "watchlist_items_watchlist_id_idx",
        ):
            assert index in sql, index
