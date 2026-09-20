"""ALFRED vintage series for the macro inputs the research already uses - and nothing else.

The existing macro features use the Treasury 3-month, 2-year and 10-year yields (`features/macro.py`).  Those are FRED series DGS3MO, DGS2 and
DGS10, which are published once and not revised, so the honest expectation is that vintage-aware values equal the values already in use.  This
module exists to *verify* that, not to add predictors: it builds a real-time-period table (`output_type=1`, every vintage of every observation)
and selects values by what was known on a date.  Without `FRED_API_KEY` the status is `BLOCKED_EXTERNAL_FRED_KEY`; revised or current-value FRED
data is never substituted.

Schema: series_id, observation_date, realtime_start, realtime_end, value, retrieved_at, source_sha256.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from datetime import date as Date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

import numpy as np
import pandas as pd

ALFRED_VERSION = "alfred-vintage-v1"
SERIES = {"DGS3MO": "3_month", "DGS2": "2_year", "DGS10": "10_year"}      # the curve columns the macro features actually read
API = "https://api.stlouisfed.org/fred/series/observations"
OPEN_END = Date(9999, 12, 31)
COLUMNS = ["series_id", "observation_date", "realtime_start", "realtime_end", "value", "retrieved_at", "source_sha256"]
Fetch = Callable[[str, Mapping[str, str]], bytes]


def status(env: Optional[Mapping[str, str]] = None) -> dict[str, Any]:
    """BLOCKED_EXTERNAL_FRED_KEY unless a key exists.  Never prints or stores the key."""
    key = (env if env is not None else os.environ).get("FRED_API_KEY")
    if not key:
        return {"status": "BLOCKED_EXTERNAL_FRED_KEY", "series": list(SERIES), "version": ALFRED_VERSION,
                "note": "no FRED_API_KEY in the environment; no vintage data exists; revised FRED data is not substituted",
                "adds_predictor_columns": False}
    return {"status": "KEY_PRESENT_NOT_BUILT", "series": list(SERIES), "version": ALFRED_VERSION, "adds_predictor_columns": False}


def _http(url: str, params: Mapping[str, str]) -> bytes:
    with urllib.request.urlopen(f"{url}?{urllib.parse.urlencode(params)}", timeout=120) as response:
        return response.read()


def fetch_series(series_id: str, *, api_key: str, realtime_start: str, realtime_end: str, fetch: Optional[Fetch] = None,
                 page: int = 100_000) -> pd.DataFrame:
    """Every vintage of every observation for one series, paged, with the SHA-256 of the raw responses on each row."""
    fetch = fetch or _http
    rows, digest, offset = [], hashlib.sha256(), 0
    while True:
        params = {"series_id": series_id, "api_key": api_key, "file_type": "json", "realtime_start": realtime_start, "realtime_end": realtime_end,
                  "output_type": "1", "limit": str(page), "offset": str(offset)}
        body = fetch(API, params)
        digest.update(body)
        payload = json.loads(body)
        batch = payload.get("observations", [])
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
    frame = pd.DataFrame(rows, columns=["date", "realtime_start", "realtime_end", "value"]) if rows else pd.DataFrame(columns=["date", "realtime_start", "realtime_end", "value"])
    frame = frame.rename(columns={"date": "observation_date"})
    frame["series_id"] = series_id
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")           # FRED's "." is missing, never zero
    frame["retrieved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    frame["source_sha256"] = digest.hexdigest()
    for column in ("observation_date", "realtime_start", "realtime_end"):
        frame[column] = [Date.fromisoformat(str(x)[:10]) for x in frame[column]]     # 9999-12-31 is out of range for pandas datetimes
    return frame[COLUMNS]


def build(raw_dir: Path, manifest_path: Path, *, env: Optional[Mapping[str, str]] = None, realtime_start: str = "2011-01-01",
          realtime_end: str = "2025-05-09", fetch: Optional[Fetch] = None) -> dict[str, Any]:
    """Build the vintage table for the used series, or record the blocked status.  The realtime window ends at the research cutoff."""
    state = status(env)
    if state["status"] == "BLOCKED_EXTERNAL_FRED_KEY":
        _write_json(Path(manifest_path), state)
        return state
    key = (env if env is not None else os.environ)["FRED_API_KEY"]
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for series_id in SERIES:
        table = fetch_series(series_id, api_key=key, realtime_start=realtime_start, realtime_end=realtime_end, fetch=fetch)
        table = table[table["realtime_start"] <= pd.Timestamp(realtime_end).date()]
        path = raw_dir / f"{series_id}.parquet"
        temporary = path.with_suffix(".parquet.tmp")
        table.to_parquet(temporary, compression="zstd", index=False)
        os.replace(temporary, path)
        records.append({"series_id": series_id, "rows": int(len(table)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "source_sha256": None if table.empty else table["source_sha256"].iloc[0]})
    manifest = {"status": "BUILT", "version": ALFRED_VERSION, "series": records, "realtime_window": [realtime_start, realtime_end], "adds_predictor_columns": False}
    _write_json(Path(manifest_path), manifest)
    return manifest


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    os.replace(temporary, path)


def as_of(table: pd.DataFrame, series_id: str, known_by: Date) -> pd.DataFrame:
    """One value per observation date: the vintage in force on `known_by` (realtime_start <= known_by <= realtime_end).  Missing stays missing."""
    frame = table[(table["series_id"] == series_id) & (table["realtime_start"] <= known_by) & (table["realtime_end"] >= known_by)]
    frame = frame.sort_values(["observation_date", "realtime_start"], kind="stable").drop_duplicates("observation_date", keep="last")
    return frame.reset_index(drop=True)


def latest_value(table: pd.DataFrame, series_id: str, decision_date: Date, calendar_sessions: list[Date], lag_sessions: int = 1) -> Optional[float]:
    """The newest observation known one session before `decision_date` (the existing macro lag), by the vintage then in force."""
    earlier = [d for d in calendar_sessions if d < decision_date]
    if len(earlier) < lag_sessions:
        return None
    known_by = earlier[-lag_sessions]
    frame = as_of(table, series_id, known_by)
    frame = frame[(frame["observation_date"] <= known_by) & frame["value"].notna()]
    return None if frame.empty else float(frame.sort_values("observation_date").iloc[-1]["value"])


def revision_report(table: pd.DataFrame) -> dict[str, Any]:
    """How many observations were ever revised, and by how much.  For the Treasury constant-maturity series this is expected to be zero."""
    out = {}
    for series_id, group in table.groupby("series_id"):
        counts = group.dropna(subset=["value"]).groupby("observation_date")["value"].nunique()
        revised = counts[counts > 1]
        out[series_id] = {"observations": int(len(counts)), "revised_observations": int(len(revised))}
    return out


def compare_with_current(table: pd.DataFrame, current_curve: pd.DataFrame, known_by: Date) -> dict[str, Any]:
    """Vintage-in-force values against the curve already used (columns 3_month, 2_year, 10_year, date), as the validation the gate asks for."""
    result = {}
    for series_id, column in SERIES.items():
        vintage = as_of(table, series_id, known_by).set_index("observation_date")["value"]
        current = current_curve.assign(date=lambda d: pd.to_datetime(d["date"]).dt.date).set_index("date")[column]
        joined = pd.concat([vintage.rename("vintage"), current.rename("current")], axis=1).dropna()
        result[series_id] = {"compared": int(len(joined)), "max_abs_difference": float((joined["vintage"] - joined["current"]).abs().max()) if len(joined) else None}
    return result
