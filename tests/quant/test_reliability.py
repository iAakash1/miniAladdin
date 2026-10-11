"""Point-in-time guarantees of the disclosure-process reliability variables (src/quant/pit/reliability.py)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.quant.pit import reliability as rel
from src.quant.pit.calendar import TradingCalendar

DAYS = [d.date() for d in pd.bdate_range("2019-01-01", "2022-12-30")]
CAL = TradingCalendar.from_dates(DAYS)


def filings(rows):
    return pd.DataFrame(rows, columns=["adsh", "cik", "form", "period", "accepted_at"]).assign(
        accepted_at=lambda f: pd.to_datetime(f["accepted_at"]))


def at(f, decision_dates, cik=1):
    keys = pd.DataFrame({"date": pd.to_datetime(decision_dates), "symbol": "X", "cik": float(cik)})
    return rel.build_reliability(f, keys, CAL)


BASE = [
    ("a1", 1, "10-Q", "20190331", "2019-05-02 10:00"),   # lag 32
    ("a2", 1, "10-Q", "20190630", "2019-08-01 10:00"),   # lag 32
    ("a3", 1, "10-Q", "20190930", "2019-11-01 10:00"),   # lag 32
    ("a4", 1, "10-K", "20191231", "2020-02-14 10:00"),   # lag 45
    ("a5", 1, "10-Q", "20200331", "2020-06-30 10:00"),   # lag 91, late
]


def test_nothing_is_known_before_the_first_filing():
    out = at(filings(BASE), ["2019-03-01"])
    assert out.isna().all(axis=None)          # NaN, never 0


def test_a_filing_accepted_after_the_close_is_usable_only_from_the_next_session():
    f = filings([("a1", 1, "10-Q", "20190331", "2019-05-02 16:30")])    # Thursday, after the 16:00 close
    out = at(f, ["2019-05-02", "2019-05-03"])
    assert np.isnan(out["periodic_count_400"].iloc[0])
    assert out["periodic_count_400"].iloc[1] == 1


def test_amendments_count_only_after_their_own_acceptance_and_flag_the_report_they_amend():
    f = filings(BASE + [("b1", 1, "10-Q/A", "20190930", "2020-03-02 10:00")])
    out = at(f, ["2020-03-01", "2020-03-03"])
    assert out["amended_730"].tolist() == [0.0, 1.0]
    # the amended report (period 2019-09-30) is not the latest original on 2020-03-03 (the 10-K for 2019-12-31 is)
    assert out["latest_report_amended"].tolist() == [0.0, 0.0]
    g = filings(BASE + [("b2", 1, "10-K/A", "20191231", "2020-03-02 10:00")])
    assert at(g, ["2020-03-01", "2020-03-03"])["latest_report_amended"].tolist() == [0.0, 1.0]


def test_the_amendment_window_forgets():
    f = filings(BASE + [("b1", 1, "10-Q/A", "20190930", "2020-03-02 10:00")])
    out = at(f, ["2021-03-01", "2022-03-04"])
    assert out["amended_730"].tolist() == [1.0, 0.0]


def test_lag_deterioration_is_the_late_filer_signal():
    out = at(filings(BASE), ["2020-07-01", "2020-03-01"])
    assert out["lag_deterioration"].iloc[0] == pytest.approx(91 - 32)     # the 10-Q lags 32, 32, 32 before
    assert out["lag_deterioration"].iloc[1] != out["lag_deterioration"].iloc[0]


def test_regularity_counts_originals_in_the_trailing_400_days():
    out = at(filings(BASE), ["2020-07-01"])
    assert out["periodic_count_400"].iloc[0] == 4          # 2019-08-01, 2019-11-01, 2020-02-14, 2020-06-30


def test_future_filings_cannot_change_the_past():
    """Perturbing everything usable after day d must not move any variable at day d."""
    early = ["2019-12-02", "2020-03-02", "2020-07-01"]
    base = filings(BASE + [("b1", 1, "10-Q/A", "20190930", "2020-03-02 10:00")])
    more = filings(BASE + [("b1", 1, "10-Q/A", "20190930", "2020-03-02 10:00"),
                           ("c1", 1, "10-Q", "20200630", "2020-09-01 10:00"),
                           ("c2", 1, "10-K/A", "20191231", "2020-09-15 10:00")])
    pd.testing.assert_frame_equal(at(base, early), at(more, early))


def test_prevrpt_is_never_read():
    clean = filings(BASE)
    leaky = clean.assign(prevrpt=1)
    pd.testing.assert_frame_equal(at(clean, ["2020-07-01"]), at(leaky, ["2020-07-01"]))


def test_unmapped_firms_get_nan_not_zero():
    keys = pd.DataFrame({"date": pd.to_datetime(["2020-07-01"]), "symbol": "Y", "cik": [np.nan]})
    assert rel.build_reliability(filings(BASE), keys, CAL).isna().all(axis=None)
