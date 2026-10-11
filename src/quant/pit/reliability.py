"""Point-in-time disclosure-process reliability variables.

A fundamentals-based signal is only as good as the filing it was computed from. Four properties of the *disclosure
process* are observable the moment a decision is made, need no vendor, and are reconstructable from the SEC's own
filing registry (`data/curated/sec_v3/filings.parquet`, built from the Financial Statement Data Sets):

``amended_730``
    Number of amendments to periodic reports (10-K/A, 10-Q/A, 10-KT/A, 10-QT/A) usable in the trailing 730 days.
    The data sets contain only filings with financial statements, so an amendment here is a re-filed financial
    report, not a Part III addendum.
``latest_report_amended``
    1 when the most recent original periodic report has itself been amended by the decision date, else 0.
``periodic_count_400``
    Original periodic reports usable in the trailing 400 days (4 or 5 for a regular filer); a shortfall means a
    missed, late or absent filing.
``lag_deterioration``
    Days between period end and acceptance for the latest original report, minus the median of the same lag over the
    previous four originals of the same kind (annual or quarterly). Positive: the firm is filing later than usual.

Availability follows the repository's rule (`sec_facts.available_session`): a filing accepted before the close of a
session is usable in a close-based decision on that session, otherwise from the next session. A variable is NaN, never
zero, before a firm has any filing history.

`prevrpt`, the registry column that says a report was *later* amended, is deliberately never read: it describes the
future relative to the original filing and would leak. Amendments are counted from their own acceptance times.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.quant.pit.calendar import TradingCalendar
from src.quant.pit.sec_facts import available_session

VERSION = "reliability-v1"
PERIODIC = frozenset({"10-K", "10-Q", "10-KT", "10-QT"})
AMENDMENT = frozenset({"10-K/A", "10-Q/A", "10-KT/A", "10-QT/A"})
ANNUAL = frozenset({"10-K", "10-KT"})
VARIABLES = ("amended_730", "latest_report_amended", "periodic_count_400", "lag_deterioration")
FILINGS = Path("data/curated/sec_v3/filings.parquet")
OUTPUT = Path("data/research/derived/reliability_v1.parquet")
MANIFEST = Path("data/manifests/reliability_v1_manifest.json")
_EPOCH = np.datetime64("1970-01-01", "D")


def epoch_days(values: Any) -> np.ndarray:
    """Calendar dates as integer days since 1970-01-01."""
    return (pd.to_datetime(pd.Series(values)).dt.normalize().to_numpy("datetime64[D]") - _EPOCH).astype("int64")


def filing_table(filings: pd.DataFrame, calendar: TradingCalendar, ciks: Optional[set[int]] = None) -> pd.DataFrame:
    """Periodic reports and amendments with the session from which each is usable."""
    f = filings[filings["form"].isin(PERIODIC | AMENDMENT)]
    if ciks is not None:
        f = f[f["cik"].isin(ciks)]
    f = f[["adsh", "cik", "form", "period", "accepted_at"]].copy()
    f["accepted_at"] = pd.to_datetime(f["accepted_at"])
    f["period_end"] = pd.to_datetime(f["period"].astype(str).str[:8], format="%Y%m%d", errors="coerce")
    f["avail"] = [available_session(stamp, calendar) for stamp in f["accepted_at"]]
    f = f.dropna(subset=["avail", "period_end", "accepted_at"]).copy()
    f["avail_d"] = epoch_days(f["avail"])
    f["period_d"] = epoch_days(f["period_end"])
    f["lag_days"] = (f["accepted_at"].dt.normalize() - f["period_end"]).dt.days.astype(float)
    f["is_amend"] = f["form"].isin(AMENDMENT)
    f["annual"] = f["form"].isin(ANNUAL | {"10-K/A", "10-KT/A"})
    return f.sort_values(["cik", "avail_d", "adsh"], kind="mergesort").reset_index(drop=True)


def _prior_lag_median(lags: np.ndarray, annual: np.ndarray) -> np.ndarray:
    """For each original filing, the median lag of the previous (up to) four of the same kind; NaN with none."""
    out = np.full(len(lags), np.nan)
    seen: dict[bool, list[float]] = {True: [], False: []}
    for i, (lag, kind) in enumerate(zip(lags, annual)):
        history = seen[bool(kind)]
        if history:
            out[i] = float(np.median(history[-4:]))
        history.append(float(lag))
    return out


def variables_for_cik(group: pd.DataFrame, days: np.ndarray) -> dict[str, np.ndarray]:
    """The four variables for one firm at each decision day (epoch days). Only filings usable on/before the day count."""
    orig, amend = group[~group["is_amend"]], group[group["is_amend"]]
    o_av = orig["avail_d"].to_numpy()
    n = len(days)
    out = {name: np.full(n, np.nan) for name in VARIABLES}
    if not len(o_av):
        return out
    latest = np.searchsorted(o_av, days, side="right") - 1
    has = latest >= 0
    # regularity
    lo = np.searchsorted(o_av, days - 400, side="right")
    count = (np.searchsorted(o_av, days, side="right") - lo).astype(float)
    out["periodic_count_400"] = np.where(has, count, np.nan)
    # amendments in the trailing 730 days
    if len(amend):
        a_av = amend["avail_d"].to_numpy()
        amended = (np.searchsorted(a_av, days, side="right") - np.searchsorted(a_av, days - 730, side="right")).astype(float)
        first_by_period = amend.groupby("period_d")["avail_d"].min()
    else:
        amended = np.zeros(n)
        first_by_period = pd.Series(dtype="int64")
    out["amended_730"] = np.where(has, amended, np.nan)
    # is the latest original report already amended?
    periods = orig["period_d"].to_numpy()
    flag = np.zeros(n)
    if len(first_by_period):
        first = first_by_period.reindex(periods[np.where(has, latest, 0)]).to_numpy(dtype=float)
        flag = np.where(np.isfinite(first) & (first <= days), 1.0, 0.0)
    out["latest_report_amended"] = np.where(has, flag, np.nan)
    # timeliness against the firm's own recent history
    lags = orig["lag_days"].to_numpy()
    prior = _prior_lag_median(lags, orig["annual"].to_numpy())
    safe = np.where(has, latest, 0)
    out["lag_deterioration"] = np.where(has, lags[safe] - prior[safe], np.nan)
    return out


def build_reliability(filings: pd.DataFrame, keys: pd.DataFrame, calendar: TradingCalendar) -> pd.DataFrame:
    """`keys` has date, symbol, cik (NaN cik allowed). Returns the four variables, index-aligned to `keys`."""
    ciks = {int(c) for c in keys["cik"].dropna().unique()}
    table = filing_table(filings, calendar, ciks)
    days = epoch_days(keys["date"])
    out = pd.DataFrame(np.nan, index=keys.index, columns=list(VARIABLES))
    by_cik = {int(c): g for c, g in table.groupby("cik", sort=False)}
    positions = keys.reset_index(drop=True).groupby(keys["cik"].reset_index(drop=True), sort=False).indices
    for cik, rows in positions.items():
        if pd.isna(cik) or int(cik) not in by_cik:
            continue
        values = variables_for_cik(by_cik[int(cik)], days[rows])
        for name in VARIABLES:
            out.iloc[rows, out.columns.get_loc(name)] = values[name]
    return out


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_and_save(root: Path = Path(".")) -> dict[str, Any]:
    """Build the table for the rich panel's rows, write parquet and a manifest with hashes and coverage."""
    from src.quant.study import exp010b, exp011

    root = Path(root)
    panel, _ = exp011.load_rich_panel(root)
    calendar = exp010b.build_daily_panel(root)[1]
    filings = pd.read_parquet(root / FILINGS)
    keys = panel[["date", "symbol", "cik"]].copy()
    table = build_reliability(filings, keys, calendar)
    result = pd.concat([panel[["date", "symbol"]].reset_index(drop=True), table.reset_index(drop=True)], axis=1)
    target = root / OUTPUT
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".parquet.tmp")
    result.to_parquet(tmp, compression="zstd", index=False)
    tmp.replace(target)
    coverage = {name: float(result[name].notna().mean()) for name in VARIABLES}
    stats = {name: {q: float(result[name].quantile(p)) for q, p in (("p01", .01), ("p50", .5), ("p99", .99))} for name in VARIABLES}
    manifest = {
        "version": VERSION, "rows": int(len(result)), "dates": int(result["date"].nunique()), "symbols": int(result["symbol"].nunique()),
        "date_min": str(result["date"].min()), "date_max": str(result["date"].max()),
        "inputs": {"filings_parquet": str(FILINGS), "filings_sha256": sha256_file(root / FILINGS), "filings_rows": int(len(filings)),
                   "rich_panel_content_hash": exp011.RICH_CONTENT_HASH},
        "output": {"path": str(OUTPUT), "sha256": sha256_file(target), "bytes": target.stat().st_size},
        "coverage": coverage, "quantiles": stats, "rows_without_cik": int(panel["cik"].isna().sum()),
        "rule": "available_session(accepted_at) <= decision date; prevrpt never read; NaN (not 0) before any filing history",
        "license": "SEC filings are public records; derived counts only, no filing text redistributed",
    }
    (root / MANIFEST).write_text(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["build"]:
        print(json.dumps(build_and_save(), indent=2))
    else:
        print("usage: python -m src.quant.pit.reliability build")
