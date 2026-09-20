"""ALFRED vintages: blocked without a key, real-time selection, truncation invariance, revisions and no substitution."""

import json
from datetime import date

import pandas as pd
import pytest

from src.quant.pit import alfred_vintage as A


def payload(rows):
    return json.dumps({"observations": [{"date": d, "realtime_start": s, "realtime_end": e, "value": v} for d, s, e, v in rows]}).encode()


ROWS = {"DGS3MO": [("2020-03-02", "2020-03-03", "9999-12-31", "1.10"), ("2020-03-03", "2020-03-04", "2020-03-20", "1.00"),
                   ("2020-03-03", "2020-03-21", "9999-12-31", "0.95"), ("2020-03-04", "2020-03-05", "9999-12-31", ".")],
        "DGS2": [("2020-03-02", "2020-03-03", "9999-12-31", "0.90")], "DGS10": [("2020-03-02", "2020-03-03", "9999-12-31", "1.20")]}


def fake(params_seen=None):
    def fetch(url, params):
        if params_seen is not None:
            params_seen.append(dict(params))
        return payload(ROWS[params["series_id"]])
    return fetch


def build(tmp_path, **kw):
    return A.build(tmp_path / "raw", tmp_path / "manifest.json", env={"FRED_API_KEY": "test-key-not-real"}, fetch=fake(), **kw)


def test_without_a_key_the_status_is_blocked_and_nothing_is_substituted(tmp_path):
    out = A.build(tmp_path / "raw", tmp_path / "m.json", env={})
    assert out["status"] == "BLOCKED_EXTERNAL_FRED_KEY" and out["adds_predictor_columns"] is False
    assert not (tmp_path / "raw").exists()
    assert json.loads((tmp_path / "m.json").read_text())["status"] == "BLOCKED_EXTERNAL_FRED_KEY"


def test_the_key_is_never_written_to_the_manifest_or_the_table(tmp_path):
    build(tmp_path)
    text = (tmp_path / "manifest.json").read_text() + "".join(p.read_bytes().decode("latin-1") for p in (tmp_path / "raw").glob("*.parquet"))
    assert "test-key-not-real" not in text


def test_only_the_series_the_macro_features_use_are_requested_and_vintages_are_requested(tmp_path):
    seen = []
    A.build(tmp_path / "raw", tmp_path / "m.json", env={"FRED_API_KEY": "k"}, fetch=fake(seen))
    assert {p["series_id"] for p in seen} == {"DGS3MO", "DGS2", "DGS10"} and {p["output_type"] for p in seen} == {"1"}
    assert set(A.SERIES.values()) == {"3_month", "2_year", "10_year"}


def table(tmp_path):
    build(tmp_path)
    return pd.concat([pd.read_parquet(p) for p in sorted((tmp_path / "raw").glob("*.parquet"))], ignore_index=True)


def test_the_schema_and_missing_values(tmp_path):
    t = table(tmp_path)
    assert list(t.columns) == A.COLUMNS and t["source_sha256"].str.len().eq(64).all()
    assert t["value"].isna().sum() == 1                              # FRED's "." is missing, never zero


def test_the_vintage_in_force_on_a_date_is_selected_not_the_latest_revision(tmp_path):
    t = table(tmp_path)
    assert A.as_of(t, "DGS3MO", date(2020, 3, 10)).set_index("observation_date").loc[date(2020, 3, 3), "value"] == 1.00
    assert A.as_of(t, "DGS3MO", date(2020, 3, 25)).set_index("observation_date").loc[date(2020, 3, 3), "value"] == 0.95
    assert date(2020, 3, 2) in set(A.as_of(t, "DGS3MO", date(2020, 3, 3))["observation_date"])
    assert date(2020, 3, 3) not in set(A.as_of(t, "DGS3MO", date(2020, 3, 3))["observation_date"])   # not yet known


def test_the_latest_value_respects_the_one_session_publication_lag(tmp_path):
    t = table(tmp_path)
    sessions = [date(2020, 3, d) for d in (2, 3, 4, 5, 6)]
    assert A.latest_value(t, "DGS3MO", date(2020, 3, 4), sessions) == 1.10        # known by 03-03: only the 03-02 observation
    assert A.latest_value(t, "DGS3MO", date(2020, 3, 5), sessions) == 1.00        # 03-03's first-release vintage
    assert A.latest_value(t, "DGS3MO", date(2020, 3, 2), sessions) is None


def test_source_truncation_leaves_every_earlier_vintage_unchanged(tmp_path):
    t = table(tmp_path)
    cut = date(2020, 3, 10)
    truncated = t[t["realtime_start"] <= cut].copy()
    truncated.loc[truncated["realtime_end"] > cut, "realtime_end"] = A.OPEN_END      # a table built on the cut has only open ends after it
    for known_by in (date(2020, 3, 3), date(2020, 3, 5), cut):
        a = A.as_of(t, "DGS3MO", known_by)[["observation_date", "value"]]
        b = A.as_of(truncated, "DGS3MO", known_by)[["observation_date", "value"]]
        pd.testing.assert_frame_equal(a, b)


def test_revision_report_and_comparison_with_the_curve_in_use(tmp_path):
    t = table(tmp_path)
    report = A.revision_report(t)
    assert report["DGS3MO"]["revised_observations"] == 1 and report["DGS2"]["revised_observations"] == 0
    curve = pd.DataFrame({"date": ["2020-03-02"], "3_month": [1.10], "2_year": [0.90], "10_year": [1.25]})
    out = A.compare_with_current(t, curve, date(2020, 3, 10))
    assert out["DGS3MO"]["max_abs_difference"] == 0.0 and out["DGS10"]["max_abs_difference"] == pytest.approx(0.05)
