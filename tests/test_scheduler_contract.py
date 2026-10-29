"""The alert scheduler's contract, and the tracker migration's contract with the code.

Two things drifted apart once: a release note named a scheduler variable, a header
and a table that no source file contains. These tests pin the real names across the
backend, the documentation and the example environment, so a deployment instruction
written from any of them cannot disagree with the code that enforces it.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.index as api_module
from src.services import alert_engine, database
from test_persistence import FakeSupabase

ROOT = Path(__file__).resolve().parent.parent
TOKEN_ENV = "ALERTS_SCHEDULER_TOKEN"
HEADER = "X-Scheduler-Token"
ENDPOINT = "/api/internal/alerts/evaluate"
MIGRATION = ROOT / "supabase" / "migrations" / "20261025000000_tracker_alerts_paper.sql"
ROLLBACK = ROOT / "supabase" / "rollbacks" / "20261025000000_tracker_alerts_paper.down.sql"

# Names a release note once used that no source file defines. Assembled from parts so
# that this file is not itself a place they appear.
RETIRED = ("ALERT" + "_EVAL_TOKEN", "X-Alert-" + "Eval-Token", "paper_order" + "_audit")


def _tracked_text_files() -> list[Path]:
    names = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    suffixes = {".py", ".md", ".ts", ".tsx", ".sql", ".yaml", ".yml", ".json", ".toml", ".example", ".css"}
    return [ROOT / n for n in names if n and (ROOT / n).is_file() and Path(n).suffix in suffixes
            and not n.endswith("package-lock.json")]


def test_the_retired_names_appear_nowhere_in_the_repository():
    offenders = []
    for path in _tracked_text_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        offenders += [f"{path.relative_to(ROOT)}: {name}" for name in RETIRED if name in text]
    assert offenders == []


def test_the_backend_reads_the_documented_variable_and_header():
    source = (ROOT / "api" / "index.py").read_text()
    assert f'alias="{HEADER}"' in source and f'os.getenv("{TOKEN_ENV}"' in source
    assert f'@app.post("{ENDPOINT}"' in source
    assert "len(expected) < 24" in source, "the minimum length the docs state"


@pytest.mark.parametrize("doc", ["README.md", ".env.example", "docs/CLOUD_RUN_DEPLOYMENT.md"])
def test_every_deployment_document_uses_the_same_names(doc):
    text = (ROOT / doc).read_text()
    assert TOKEN_ENV in text and HEADER in text
    assert re.search(r"(≥ ?24|at least[ *]*24)", text, re.I), "the minimum token length is stated"


def test_the_website_proxy_refuses_internal_routes_whatever_the_caller_sends():
    proxy = (ROOT / "dashboard" / "src" / "lib" / "backend-proxy.ts").read_text()
    assert "=== 'internal'" in proxy
    test = (ROOT / "dashboard" / "tests" / "backend-proxy.test.ts").read_text()
    assert f"'{HEADER}'" in test and ENDPOINT in test


class TestTheEndpointGate:
    @pytest.fixture()
    def client(self, monkeypatch):
        fake = FakeSupabase()
        database.set_client_for_testing(fake)
        self.calls: list[object] = []
        monkeypatch.setattr(alert_engine, "run", lambda c: self.calls.append(c) or {"status": "ok"})
        try:
            yield TestClient(api_module.app)
        finally:
            database.set_client_for_testing(None)

    def test_a_token_below_the_minimum_length_disables_the_endpoint(self, client, monkeypatch):
        short = "t" * 23
        monkeypatch.setenv(TOKEN_ENV, short)
        assert client.post(ENDPOINT, headers={HEADER: short}).status_code == 503
        assert self.calls == []

    def test_the_minimum_length_token_is_accepted_and_a_near_miss_is_not(self, client, monkeypatch):
        good = "t" * 24
        monkeypatch.setenv(TOKEN_ENV, good)
        assert client.post(ENDPOINT, headers={HEADER: "t" * 23}).status_code == 403
        assert client.post(ENDPOINT, headers={HEADER: good + "x"}).status_code == 403
        assert client.post(ENDPOINT, headers={HEADER: good}).status_code == 200
        assert len(self.calls) == 1

    def test_the_retired_header_name_does_not_authenticate(self, client, monkeypatch):
        good = "t" * 40
        monkeypatch.setenv(TOKEN_ENV, good)
        assert client.post(ENDPOINT, headers={RETIRED[1]: good}).status_code == 403
        assert self.calls == []


# ── the migration against the code that depends on it ───────────────────────

def _created_tables(sql: str) -> list[str]:
    return re.findall(r"create table if not exists public\.(\w+)", sql)


def test_every_table_the_code_reads_is_created_by_a_migration():
    created = set()
    for path in (ROOT / "supabase" / "migrations").glob("*.sql"):
        created |= {m.lower() for m in re.findall(r"create table (?:if not exists )?public\.(\w+)", path.read_text(), re.I)}
    used = set()
    for folder in ("src", "api"):
        for path in (ROOT / folder).rglob("*.py"):
            used |= set(re.findall(r'\.table\("(\w+)"\)', path.read_text()))
    assert used - created == set()


def test_the_tracker_migration_creates_four_tables_and_closes_each_to_the_postgrest_roles():
    sql = MIGRATION.read_text()
    tables = _created_tables(sql)
    assert tables == ["price_alerts", "alert_events", "notifications", "paper_orders"]
    for table in tables:
        assert f"alter table public.{table}" in sql and "enable row level security" in sql
    revoke = re.search(r"revoke all on (.*?)\s+from anon, authenticated;", sql, re.S)
    assert revoke and all(f"public.{t}" in revoke.group(1) for t in tables)
    assert "create policy" not in sql.lower(), "default deny: RLS enabled with no policy"


def test_the_rollback_drops_exactly_what_the_migration_created():
    up, down = MIGRATION.read_text(), ROLLBACK.read_text()
    assert sorted(re.findall(r"drop table if exists public\.(\w+)", down)) == sorted(_created_tables(up))
    for column in re.findall(r"add column if not exists (\w+)", up):
        assert f"drop column if exists {column}" in down
