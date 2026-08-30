"""
Contamination probes — and proof that each probe can fail.

Every test here is paired: a clean builder must pass, and a deliberately leaky
one must fail. A probe that cannot fail is decoration, and the defect that
voided EXP-002 slipped past a suite that had exactly that shape.
"""

from __future__ import annotations

from datetime import date as Date
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from src.quant.audit.contamination import (
    ABSURD_SCALE,
    adversarial_invariance,
    compare_overlapping,
    inject_absurd_future,
    ordering_invariance,
    summarise,
    truncation_invariance,
)


def _panel(symbols=("AAA", "BBB", "CCC"), days: int = 120) -> pd.DataFrame:
    """Symbol-major, the order the real builder receives."""
    rng = np.random.default_rng(11)
    rows = []
    for index, symbol in enumerate(symbols):
        price = 50.0 + 10 * index
        for offset in range(days):
            price *= 1.0 + rng.normal(0.0004, 0.015)
            rows.append({
                "date": Date(2024, 1, 1) + timedelta(days=offset),
                "symbol": symbol, "close": price, "volume": 1e6 * (index + 1),
            })
    return pd.DataFrame(rows)


# ── clean and leaky builders ────────────────────────────────────────────────


def _clean_builder(frame: pd.DataFrame) -> pd.DataFrame:
    """Backward-only rolling per symbol, joined by label."""
    out = frame.sort_values(["symbol", "date"], kind="mergesort").copy()
    out["feat"] = out.groupby("symbol")["close"].transform(
        lambda s: s.rolling(10, min_periods=10).mean()
    )
    return out.reset_index(drop=True)


def _global_scaler_builder(frame: pd.DataFrame) -> pd.DataFrame:
    """Standardised over the WHOLE sample — the classic normalisation leak."""
    out = frame.sort_values(["symbol", "date"], kind="mergesort").copy()
    values = out["close"]
    out["feat"] = (values - values.mean()) / values.std(ddof=1)
    return out.reset_index(drop=True)


def _positional_builder(frame: pd.DataFrame) -> pd.DataFrame:
    """The EXP-002 defect: compute in one order, assign back in another."""
    out = frame.copy()
    reordered = frame.sort_values("date", kind="mergesort")
    computed = reordered.groupby("symbol")["close"].transform(
        lambda s: s.rolling(10, min_periods=10).mean()
    )
    out["feat"] = computed.to_numpy()  # positional write into a different order
    return out.reset_index(drop=True)


# ── truncation invariance ───────────────────────────────────────────────────


def test_truncation_invariance_passes_for_a_backward_only_builder():
    source = _panel()
    cutoffs = [Date(2024, 2, 15), Date(2024, 3, 1), Date(2024, 3, 20)]

    def build(cutoff):
        data = source if cutoff is None else source[source["date"] <= cutoff]
        return _clean_builder(data)

    report = summarise(truncation_invariance(build, cutoffs, ["feat"]))
    assert report["clean"], report["failed"]
    assert report["comparisons"] == 3
    assert report["rows_compared"] > 0


def test_truncation_invariance_catches_a_globally_fitted_transform():
    source = _panel()

    def build(cutoff):
        data = source if cutoff is None else source[source["date"] <= cutoff]
        return _global_scaler_builder(data)

    report = summarise(truncation_invariance(build, [Date(2024, 3, 1)], ["feat"]))
    assert not report["clean"], "a whole-sample scaler must be detected"
    assert report["failed"][0]["differing"][0]["kind"] == "values"


def test_truncation_invariance_uses_several_cutoffs():
    """A leak with a bounded reach only shows at cutoffs inside its span."""
    source = _panel(days=200)

    def build(cutoff):
        data = source if cutoff is None else source[source["date"] <= cutoff]
        out = data.sort_values(["symbol", "date"], kind="mergesort").copy()
        # Backward-looking except for the LAST 5 rows of each symbol, which peek
        # forward. Only visible at a cutoff where those rows are interior.
        out["feat"] = out.groupby("symbol")["close"].transform(
            lambda s: s.rolling(10, min_periods=10).mean()
        )
        tail = out.groupby("symbol").tail(5).index
        out.loc[tail, "feat"] = np.nan
        return out.reset_index(drop=True)

    cutoffs = [Date(2024, 3, 1), Date(2024, 5, 1), Date(2024, 6, 15)]
    report = summarise(truncation_invariance(build, cutoffs, ["feat"]))
    assert not report["clean"], "an edge-dependent builder must be detected"


# ── ordering invariance ─────────────────────────────────────────────────────


def test_ordering_invariance_passes_for_a_label_joined_builder():
    source = _panel()
    report = summarise(ordering_invariance(_clean_builder, source, ["feat"]))
    assert report["clean"], report["failed"]
    assert report["comparisons"] == 4


def test_ordering_invariance_catches_the_positional_assignment_defect():
    """The exact shape of the bug that voided EXP-002."""
    source = _panel()
    results = ordering_invariance(_positional_builder, source, ["feat"])
    assert not summarise(results)["clean"]
    # Symbol-major is where it bites; date-major is where it hid.
    by_label = {r.label: r for r in results}
    assert not by_label["order:symbol_major"].clean or not by_label["order:shuffled"].clean


# ── adversarial injection ───────────────────────────────────────────────────


def test_injection_scales_only_the_future():
    source = _panel()
    cutoff = Date(2024, 3, 1)
    injected = inject_absurd_future(source, after=cutoff)

    before = source[source["date"] <= cutoff]["close"].to_numpy()
    after_injection = injected[injected["date"] <= cutoff]["close"].to_numpy()
    np.testing.assert_allclose(before, after_injection)

    future_original = source[source["date"] > cutoff]["close"].to_numpy()
    future_injected = injected[injected["date"] > cutoff]["close"].to_numpy()
    np.testing.assert_allclose(future_injected, future_original * ABSURD_SCALE)


def test_injection_refuses_when_there_is_no_future():
    source = _panel(days=10)
    with pytest.raises(ValueError, match="nothing after"):
        inject_absurd_future(source, after=Date(2030, 1, 1))


def test_adversarial_invariance_passes_for_a_clean_builder():
    source = _panel()
    result = adversarial_invariance(
        _clean_builder, source, ["feat"], cutoff=Date(2024, 3, 1)
    )
    assert result.clean, result.as_dict()


def test_adversarial_invariance_catches_a_global_leak():
    source = _panel()
    result = adversarial_invariance(
        _global_scaler_builder, source, ["feat"], cutoff=Date(2024, 3, 1)
    )
    assert not result.clean


def test_adversarial_probe_reports_when_it_cannot_detect_anything():
    """A probe that changes nothing anywhere must say so rather than pass."""
    def constant(frame: pd.DataFrame) -> pd.DataFrame:
        out = frame.copy()
        out["feat"] = 1.0
        return out

    result = adversarial_invariance(
        constant, _panel(), ["feat"], cutoff=Date(2024, 3, 1)
    )
    assert not result.clean
    kinds = {entry.get("kind") for entry in result.differing}
    assert "probe_not_live" in kinds


# ── comparison mechanics ────────────────────────────────────────────────────


def test_null_pattern_change_is_detected_even_when_values_agree():
    """The signature of the EXP-002 defect was a NULL-pattern change."""
    key = pd.DataFrame({"symbol": ["A"] * 4, "date": pd.date_range("2024-01-01", periods=4).date})
    a = key.assign(feat=[1.0, 2.0, np.nan, 4.0])
    b = key.assign(feat=[1.0, 2.0, 3.0, 4.0])
    result = compare_overlapping(a, b, ["feat"], label="t")
    assert not result.clean
    assert result.differing[0]["kind"] == "null_pattern"


def test_row_set_change_is_flagged():
    key = pd.DataFrame({"symbol": ["A"] * 3, "date": pd.date_range("2024-01-01", periods=3).date})
    result = compare_overlapping(
        key.assign(feat=1.0), key.iloc[:2].assign(feat=1.0), ["feat"], label="t"
    )
    assert result.row_set_changed
    assert not result.clean


# ── fold geometry must be shared between controls and models ────────────────


def test_a_strided_panel_cannot_supply_the_fold_calendar():
    """Guards a real bug: building the calendar from the strided panel.

    The panel carries every fifth session, so a calendar derived from it has
    roughly a fifth of the sessions the fold geometry is defined over. Passing
    it to `build_plan` must fail rather than silently produce a different fold
    layout — a negative control evaluated on different folds than the models is
    not a control for anything.
    """
    from datetime import timedelta

    from src.quant.pit.calendar import TradingCalendar
    from src.quant.validation.walkforward import build_plan

    full_sessions = []
    cursor = Date(2014, 4, 1)
    while len(full_sessions) < 3100:
        if cursor.weekday() < 5:
            full_sessions.append(cursor)
        cursor += timedelta(days=1)

    full = TradingCalendar.from_dates(full_sessions)
    strided = TradingCalendar.from_dates(full_sessions[::5])

    plan = build_plan(
        full, start=full.start, end=full.end, label_horizon_sessions=21,
        validation_sessions=252, min_train_sessions=756, holdout_sessions=252,
    )
    assert len(plan) > 0

    with pytest.raises(ValueError, match="cannot support"):
        build_plan(
            strided, start=strided.start, end=strided.end, label_horizon_sessions=21,
            validation_sessions=252, min_train_sessions=756, holdout_sessions=252,
        )
