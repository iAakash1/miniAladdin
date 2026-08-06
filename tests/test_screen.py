"""Cross-sectional screen tests."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.research.screen import MIN_FACTORS, MIN_NAMES, dispersion, screen

FACTORS = ("a", "b", "c", "d")
DAY = date(2024, 6, 3)


def _panel(names: int, builder) -> pd.DataFrame:
    return pd.DataFrame([
        {"symbol": f"S{i:02d}", "date": DAY, **builder(i)} for i in range(names)
    ])


def test_composite_ranks_by_mean_percentile():
    rows = screen(_panel(20, lambda i: {f: float(i) for f in FACTORS}), FACTORS, DAY)
    assert rows[0].symbol == "S19"
    assert rows[0].rank == 1
    assert rows[0].composite == pytest.approx(100.0)


def test_agreement_is_maximal_when_every_factor_agrees():
    rows = screen(_panel(20, lambda i: {f: float(i) for f in FACTORS}), FACTORS, DAY)
    assert all(row.agreement == pytest.approx(1.0) for row in rows)
    assert rows[0].conviction == "aligned"


def test_agreement_is_low_when_factors_conflict():
    """Two factors love it, two hate it — the mean hides that; agreement must not."""
    def conflicted(i):
        return {"a": float(i), "b": float(i), "c": float(19 - i), "d": float(19 - i)}

    rows = screen(_panel(20, conflicted), FACTORS, DAY)
    by_symbol = {row.symbol: row for row in rows}

    # Every composite is identical — the mean cannot separate these names.
    assert all(row.composite == pytest.approx(rows[0].composite, abs=1e-6) for row in rows)

    # Agreement can. The extremes are genuinely torn; a name mid-pack on all
    # four factors is not conflicted, it is simply unremarkable, and reporting
    # it as conflicted would be wrong.
    assert by_symbol["S19"].agreement < 0.1
    assert by_symbol["S00"].agreement < 0.1
    assert by_symbol["S19"].conviction == "conflicted"
    assert by_symbol["S10"].agreement > 0.8


def test_strongest_and_weakest_are_identified():
    def mixed(i):
        return {"a": float(i), "b": 0.0, "c": float(i) / 2, "d": float(i) / 3}

    rows = screen(_panel(20, mixed), FACTORS, DAY)
    top = next(r for r in rows if r.symbol == "S19")
    assert top.strongest == "a"
    assert top.weakest == "b"


def test_percentiles_are_relative_to_the_date():
    rows = screen(_panel(20, lambda i: {f: float(i) * 1000 for f in FACTORS}), FACTORS, DAY)
    assert rows[0].percentiles["a"] == pytest.approx(100.0)
    assert rows[-1].percentiles["a"] == pytest.approx(5.0)


def test_names_with_too_few_factors_are_dropped():
    def sparse(i):
        row = {"a": float(i), "b": float(i), "c": float(i), "d": float(i)}
        if i == 0:
            row = {"a": float(i), "b": np.nan, "c": np.nan, "d": np.nan}
        return row

    rows = screen(_panel(20, sparse), FACTORS, DAY)
    assert "S00" not in {row.symbol for row in rows}
    assert all(row.factors_used >= MIN_FACTORS for row in rows)


def test_thin_universes_return_nothing():
    rows = screen(_panel(MIN_NAMES - 1, lambda i: {f: float(i) for f in FACTORS}), FACTORS, DAY)
    assert rows == []


def test_unknown_date_returns_nothing():
    panel = _panel(20, lambda i: {f: float(i) for f in FACTORS})
    assert screen(panel, FACTORS, date(1999, 1, 1)) == []


def test_limit_truncates_after_ranking():
    rows = screen(_panel(30, lambda i: {f: float(i) for f in FACTORS}), FACTORS, DAY, limit=5)
    assert len(rows) == 5
    assert rows[0].rank == 1 and rows[-1].rank == 5


def test_dispersion_reports_a_flat_day_as_flat():
    """A day where the engine has no opinion should say so."""
    rows = screen(_panel(20, lambda i: {f: 1.0 for f in FACTORS}), FACTORS, DAY)
    stats = dispersion(rows)
    assert stats["composite_spread"] == pytest.approx(0.0)


def test_dispersion_of_an_empty_screen_is_zero():
    assert dispersion([])["mean_agreement"] == 0.0
