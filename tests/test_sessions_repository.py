"""Research sessions — state migration, scoping, bounds (hermetic)."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.services.database.repositories.sessions import (
    MAX_ACTIVITY,
    MAX_SNAPSHOTS,
    WORKSPACE_SCHEMA_VERSION,
    SessionsRepository,
    _migrate_state,
    empty_state,
)


class TestStateMigration:
    def test_empty_state_carries_the_current_version(self):
        assert empty_state()["schema_version"] == WORKSPACE_SCHEMA_VERSION

    def test_missing_keys_are_filled_so_old_sessions_still_open(self):
        # A session saved before "collections" existed must not crash.
        legacy = {"symbols": ["NVDA"], "pinned": ["company:NVDA"]}
        state = _migrate_state(legacy)
        assert state["symbols"] == ["NVDA"]          # preserved
        assert state["collections"] == []            # filled
        assert state["schema_version"] == WORKSPACE_SCHEMA_VERSION

    def test_nested_settings_merge_key_wise(self):
        # A new filter gains its default without discarding stored ones.
        state = _migrate_state({"filters": {"hops": 3}})
        assert state["filters"]["hops"] == 3
        assert "min_confidence" in state["filters"]

    def test_garbage_state_falls_back_to_empty(self):
        assert _migrate_state(None) == empty_state()
        assert _migrate_state("not-a-dict")["schema_version"] == WORKSPACE_SCHEMA_VERSION

    def test_append_only_collections_are_bounded_on_read(self):
        state = _migrate_state({
            "snapshots": [{"i": i} for i in range(MAX_SNAPSHOTS + 25)],
            "activity": [{"i": i} for i in range(MAX_ACTIVITY + 50)],
        })
        assert len(state["snapshots"]) == MAX_SNAPSHOTS
        assert len(state["activity"]) == MAX_ACTIVITY
        # The most RECENT entries survive, not the oldest.
        assert state["snapshots"][-1]["i"] == MAX_SNAPSHOTS + 24


class TestScoping:
    def _repo(self):
        client = MagicMock()
        return SessionsRepository(client), client

    def test_every_read_filters_by_the_clerk_user(self):
        repo, client = self._repo()
        client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        assert repo.get("user_abc", "session-1") is None
        # The user filter is present on the query chain.
        client.table.return_value.select.return_value.eq.assert_called_with("clerk_user_id", "user_abc")

    def test_delete_of_a_session_the_user_does_not_own_is_refused(self):
        repo, client = self._repo()
        client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        assert repo.delete("user_abc", "someone-elses-session") is False
        client.table.return_value.delete.assert_not_called()

    def test_note_cannot_be_added_to_a_session_the_user_does_not_own(self):
        repo, client = self._repo()
        client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        assert repo.add_note("user_abc", "foreign-session", "note") is None


class TestValidation:
    def _repo(self):
        client = MagicMock()
        return SessionsRepository(client), client

    def test_session_limit_is_enforced(self):
        repo, client = self._repo()
        client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": str(i)} for i in range(100)
        ]
        assert repo.create("user_abc", "One more") is None

    def test_titles_and_tags_are_bounded(self):
        repo, client = self._repo()
        client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        client.table.return_value.insert.return_value.execute.return_value.data = [{"id": "x"}]
        repo.create("user_abc", "T" * 500, tags=[f"tag{i}" for i in range(50)])
        row = client.table.return_value.insert.call_args[0][0]
        assert len(row["title"]) <= 120
        assert len(row["tags"]) <= 12

    def test_unknown_status_is_dropped_and_no_write_is_issued(self):
        # An invalid-only patch leaves nothing to write, so the repository
        # short-circuits rather than issuing an empty UPDATE.
        repo, client = self._repo()
        client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"id": "s1", "workspace_state": {}}
        ]
        repo.patch("user_abc", "s1", {"status": "nonsense"})
        client.table.return_value.update.assert_not_called()

    def test_valid_status_is_written(self):
        repo, client = self._repo()
        client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"id": "s1", "workspace_state": {}}
        ]
        client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "s1"}]
        repo.patch("user_abc", "s1", {"status": "archived"})
        assert client.table.return_value.update.call_args[0][0]["status"] == "archived"

    def test_empty_search_short_circuits(self):
        repo, client = self._repo()
        assert repo.search("user_abc", "   ") == {"sessions": [], "notes": []}
        client.table.assert_not_called()
