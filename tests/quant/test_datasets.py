"""Dataset layer: the client's refusals, the store's immutability, the catalog's contract."""

from __future__ import annotations

import json
from datetime import date as Date

import pandas as pd
import pytest

from src.quant.datasets import catalog
from src.quant.datasets.dolthub import (
    ROW_LIMIT,
    DoltHubClient,
    QueryResult,
    RowLimitExceeded,
    _sql_date,
    _sql_literal,
    _sql_symbol_list,
)
from src.quant.datasets.ingest import normalise_rows
from src.quant.datasets.store import (
    DatasetExistsError,
    DatasetManifest,
    DatasetNotFoundError,
    RawStore,
)


# ── query-building safety ───────────────────────────────────────────────────


@pytest.mark.parametrize("bad", ["2024-1-2", "not-a-date", "2024/01/02", "'; drop table x--"])
def test_invalid_date_literals_are_refused(bad):
    with pytest.raises(ValueError):
        _sql_date(bad)


@pytest.mark.parametrize("bad", ["AAPL; drop table x", "A'B", "", "X" * 40, "a b"])
def test_invalid_symbols_are_refused(bad):
    with pytest.raises(ValueError):
        _sql_symbol_list([bad])


def test_valid_symbols_are_quoted_and_uppercased():
    assert _sql_symbol_list(["aapl", "brk.b"]) == "'AAPL','BRK.B'"


def test_keyset_cursor_escapes_quotes():
    assert _sql_literal("O'BRIEN") == "'O''BRIEN'"
    with pytest.raises(ValueError):
        _sql_literal(None)


# ── truncation is an error ──────────────────────────────────────────────────


def test_row_limit_truncation_raises_rather_than_returning_a_partial_answer(monkeypatch):
    """The API caps at 1000 rows with no continuation token.

    A client that returns the truncated set silently produces a dataset with
    holes that no downstream test can detect.
    """
    client = DoltHubClient()

    def fake(url, repository, query):
        return {
            "query_execution_status": "RowLimit",
            "query_execution_message": "",
            "schema": [{"columnName": "date"}],
            "rows": [{"date": "2024-01-02"}] * ROW_LIMIT,
            "_elapsed_ms": 1.0,
        }

    monkeypatch.setattr(client, "_get_with_retry", fake)
    with pytest.raises(RowLimitExceeded):
        client.execute("stocks", "select * from ohlcv")

    # Explicit opt-in returns the partial result and marks it.
    result = client.execute("stocks", "select * from ohlcv", allow_truncation=True)
    assert result.truncated


# ── normalisation ───────────────────────────────────────────────────────────


def test_normalisation_renames_and_types_without_inventing_zeros():
    rows = [
        {"date": "2024-01-02", "act_symbol": "aapl", "open": "187.1500",
         "high": "188.4400", "low": "183.8850", "close": "185.6400", "volume": "81964874"},
        {"date": "2024-01-03", "act_symbol": "aapl", "open": "bad",
         "high": "185.8800", "low": "183.4300", "close": "184.2500", "volume": "58414460"},
    ]
    frame = normalise_rows(catalog.STOCKS_OHLCV, rows)
    assert list(frame["symbol"]) == ["AAPL", "AAPL"]
    assert frame["date"].iloc[0] == Date(2024, 1, 2)
    assert frame["close"].iloc[0] == pytest.approx(185.64)
    # Unparseable becomes NULL, never 0.0 — zero is a price, null is its absence.
    assert pd.isna(frame["open"].iloc[1])


def test_ex_date_renames_to_date_without_colliding():
    rows = [{"act_symbol": "AAPL", "ex_date": "2024-02-09", "amount": "0.24"}]
    frame = normalise_rows(catalog.STOCKS_DIVIDEND, rows)
    assert "date" in frame.columns
    assert frame["date"].iloc[0] == Date(2024, 2, 9)


# ── store ───────────────────────────────────────────────────────────────────


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {"date": [Date(2024, 1, 2), Date(2024, 1, 3)], "symbol": ["AAPL", "AAPL"],
         "close": [185.64, 184.25]}
    )


def test_partitions_are_immutable(tmp_path):
    store = RawStore(tmp_path)
    store.write_partition("d", "2024", _frame())
    with pytest.raises(DatasetExistsError):
        store.write_partition("d", "2024", _frame())


def test_partition_write_is_deterministic_regardless_of_row_order(tmp_path):
    """Two ingestions of identical data must produce identical bytes."""
    a = RawStore(tmp_path / "a")
    b = RawStore(tmp_path / "b")
    forward = _frame()
    shuffled = forward.iloc[::-1].reset_index(drop=True)
    assert a.write_partition("d", "2024", forward).checksum == \
        b.write_partition("d", "2024", shuffled).checksum


def test_verify_detects_corruption(tmp_path):
    store = RawStore(tmp_path)
    record = store.write_partition("d", "2024", _frame())
    store.write_manifest(
        DatasetManifest(dataset_id="d", source="s", repository="r", table="t",
                        source_version="v", columns=["date", "symbol", "close"],
                        partitions=[record])
    )
    assert store.verify("d")["ok"]

    path = store.partition_path("d", "2024")
    path.write_bytes(path.read_bytes() + b"corrupted")
    report = store.verify("d")
    assert not report["ok"]
    assert report["corrupt"] == ["2024"]


def test_missing_dataset_raises(tmp_path):
    with pytest.raises(DatasetNotFoundError):
        RawStore(tmp_path).manifest("absent")


def test_manifest_round_trips(tmp_path):
    store = RawStore(tmp_path)
    record = store.write_partition("d", "2024", _frame())
    original = DatasetManifest(
        dataset_id="d", source="dolthub", repository="stocks", table="ohlcv",
        source_version="stocks@master", columns=["date", "symbol", "close"],
        partitions=[record], point_in_time_status="point_in_time",
        survivorship_status="complete",
    )
    store.write_manifest(original)
    loaded = store.manifest("d")
    assert loaded.rows == 2
    assert loaded.point_in_time_status == "point_in_time"
    assert loaded.min_date == "2024-01-02"


# ── catalog contract ────────────────────────────────────────────────────────


def test_period_keyed_statements_are_publication_lagged_not_point_in_time():
    """A fiscal-period key is never an availability date.

    These tables are keyed by period end, so they are admissible only behind an
    announcement gate. The class that says so is PUBLICATION_LAGGED; declaring
    any of them POINT_IN_TIME would let the builder read them as-dated and hand
    a model a month of hindsight on every quarterly figure.
    """
    period_keyed = [
        catalog.EARNINGS_INCOME_STATEMENT,
        catalog.EARNINGS_BALANCE_ASSETS,
        catalog.EARNINGS_BALANCE_LIABILITIES,
        catalog.EARNINGS_BALANCE_EQUITY,
        catalog.EARNINGS_CASH_FLOW,
        catalog.EARNINGS_EPS_HISTORY,
    ]
    for spec in period_keyed:
        assert spec.point_in_time is catalog.PointInTimeClass.PUBLICATION_LAGGED, spec.dataset_id
        assert "period" in spec.point_in_time_note.lower(), spec.dataset_id


def test_income_statement_reclassification_is_documented_with_its_caveat():
    """Weakening a BARRED label has to carry its reason and its residual risk."""
    spec = catalog.EARNINGS_INCOME_STATEMENT
    note = spec.point_in_time_note
    assert "RECLASSIFIED" in note
    assert "NOT_POINT_IN_TIME" in note
    assert "earnings_calendar" in note
    # The timing leak is closed; the restatement leak is not, and the note must
    # say so rather than let the reclassification imply the table is now clean.
    assert "RESTATEMENT" in note.upper()
    assert any("restatement" in limit.lower() for limit in spec.limitations)
    assert any("UNQUANTIFIED" in limit for limit in spec.limitations)


def test_estimate_vintages_need_no_announcement_gate():
    """The estimate tables are dated by OBSERVATION, which is why they are clean."""
    for spec in (catalog.EARNINGS_EPS_ESTIMATE, catalog.EARNINGS_SALES_ESTIMATE):
        assert spec.point_in_time is catalog.PointInTimeClass.POINT_IN_TIME
        # The note must locate the date on the OBSERVATION, however it words it —
        # that is the whole reason these two need no gate.
        note = spec.point_in_time_note.lower()
        assert "vintage" in note or "observation" in note, spec.dataset_id
        assert spec.historical_training_allowed


def test_ohlcv_is_declared_survivorship_complete_with_evidence():
    spec = catalog.STOCKS_OHLCV
    assert spec.survivorship is catalog.SurvivorshipClass.COMPLETE
    # The note must cite specific verified evidence, not assert the property.
    assert "SIVB" in spec.survivorship_note


def test_split_coverage_gap_is_recorded():
    """The 2011-2014 gap must be in the catalog, since the builder enforces it."""
    assert catalog.STOCKS_SPLIT.measured_start == "2014-03-28"
    assert any("2014-03-28" in note for note in catalog.STOCKS_SPLIT.limitations)


def test_every_spec_has_a_primary_key_and_serialises():
    for spec in catalog.CATALOG:
        assert spec.primary_key, f"{spec.dataset_id} has no primary key"
        json.dumps(spec.as_dict())


def test_french_factors_are_barred_from_features_by_classification():
    spec = catalog.FRENCH_FACTORS
    assert spec.point_in_time is catalog.PointInTimeClass.PUBLICATION_LAGGED
    assert "revis" in spec.point_in_time_note.lower()
