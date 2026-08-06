"""Factor redundancy tests."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src.research.redundancy import REDUNDANT_ABOVE, analyse


def _panel(dates: int, names: int, builder, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for step in range(dates):
        day = date(2024, 1, 1) + timedelta(days=7 * step)
        base = rng.normal(size=names)
        extra = rng.normal(size=names)
        for i in range(names):
            rows.append({"symbol": f"S{i:02d}", "date": day, **builder(base[i], extra[i])})
    return pd.DataFrame(rows)


def test_identical_factors_collapse_to_one():
    panel = _panel(30, 25, lambda b, e: {"a": b, "b": b, "c": b})
    result = analyse(panel, ("a", "b", "c"))
    assert result.effective_factors == pytest.approx(1.0, abs=0.05)
    assert "heavily overlapping" in result.assessment
    assert len(result.redundant_pairs) == 3


def test_independent_factors_stay_independent():
    rng = np.random.default_rng(5)
    rows = []
    for step in range(40):
        day = date(2024, 1, 1) + timedelta(days=7 * step)
        for i in range(30):
            rows.append({
                "symbol": f"S{i:02d}", "date": day,
                "a": rng.normal(), "b": rng.normal(), "c": rng.normal(),
            })
    result = analyse(pd.DataFrame(rows), ("a", "b", "c"))
    assert result.effective_factors > 2.6
    assert "largely independent" in result.assessment
    assert result.redundant_pairs == []


def test_partial_overlap_lands_between():
    panel = _panel(40, 30, lambda b, e: {"a": b, "b": 0.8 * b + 0.6 * e, "c": e})
    result = analyse(panel, ("a", "b", "c"))
    assert 1.5 < result.effective_factors < 3.0


def test_redundant_pairs_are_reported_strongest_first():
    panel = _panel(30, 25, lambda b, e: {"a": b, "b": b, "c": 0.2 * b + e})
    pairs = analyse(panel, ("a", "b", "c")).redundant_pairs
    assert pairs[0][:2] == ("a", "b")
    assert all(abs(p[2]) >= REDUNDANT_ABOVE for p in pairs)


def test_inverted_factors_are_flagged_as_redundant():
    """A perfectly inverted factor carries no new information either."""
    panel = _panel(30, 25, lambda b, e: {"a": b, "b": -b})
    pairs = analyse(panel, ("a", "b")).redundant_pairs
    assert pairs and pairs[0][2] == pytest.approx(-1.0, abs=0.05)


def test_matrix_is_symmetric_with_unit_diagonal():
    panel = _panel(30, 25, lambda b, e: {"a": b, "b": e})
    matrix = analyse(panel, ("a", "b")).matrix
    assert matrix[0][0] == 1.0 and matrix[1][1] == 1.0
    assert matrix[0][1] == pytest.approx(matrix[1][0])


def test_uses_rank_correlation_not_levels():
    """One outlier must not create apparent redundancy."""
    rng = np.random.default_rng(3)
    rows = []
    for step in range(30):
        day = date(2024, 1, 1) + timedelta(days=7 * step)
        for i in range(25):
            a = rng.normal()
            rows.append({"symbol": f"S{i:02d}", "date": day,
                         "a": a, "b": 1e9 if i == 0 else rng.normal()})
    result = analyse(pd.DataFrame(rows), ("a", "b"))
    assert abs(result.matrix[0][1]) < 0.5


def test_thin_dates_are_skipped():
    panel = _panel(20, 5, lambda b, e: {"a": b, "b": e})
    assert analyse(panel, ("a", "b")) is None


def test_fewer_than_two_factors_returns_none():
    panel = _panel(20, 25, lambda b, e: {"a": b})
    assert analyse(panel, ("a",)) is None
    assert analyse(panel, ("missing", "gone")) is None
