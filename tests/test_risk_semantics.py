"""The risk engine's semantic guards, which were enforced and untested.

Two of them exist because the product got it wrong before. The portfolio
surface builds a book-level outcome series in *cross-sectional rank* units —
correctly, since the primary target is a rank — and passed it to `analyse`,
which computed a "Sharpe ratio" from it. A Sharpe of a rank series is not a
Sharpe: the numerator is not a return, the denominator is not a volatility,
and annualising by 252 asserts a period length the series does not have.

The suppression and the ordering check were both in the engine with no test
behind either. A guard nobody exercises is a guard nobody can rely on.
"""

import numpy as np
import pandas as pd
import pytest

from src.quant.risk.engine import (
    RETURN_ONLY_METRICS,
    SeriesUnit,
    UnorderedSeries,
    analyse,
    max_drawdown,
    sharpe,
)


def _series(n: int = 300, seed: int = 7, scale: float = 0.01) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.Series(rng.normal(0.0005, scale, n), index=idx)


# ── return-only metrics on a rank series ────────────────────────────────────

def test_a_sharpe_is_not_computed_from_a_rank_series():
    """The exact defect this guard was written for."""
    ranks = _series(scale=0.3)
    report = analyse(ranks, series_unit=SeriesUnit.RANK)
    metric = report.metrics["sharpe"]
    assert metric.value is None, "a Sharpe was computed from a rank series"
    assert "NOT APPLICABLE" in (metric.caveat or ""), "the suppression gives no reason"
    assert "rank" in (metric.caveat or "")


@pytest.mark.parametrize("name", sorted(RETURN_ONLY_METRICS))
def test_every_return_only_metric_is_suppressed_on_a_rank_series(name):
    report = analyse(_series(scale=0.3), benchmark=_series(seed=9, scale=0.3),
                     series_unit=SeriesUnit.RANK)
    if name not in report.metrics:
        pytest.skip(f"{name} is not produced by this report shape")
    assert report.metrics[name].value is None, (
        f"{name} presupposes returns and was computed on a rank series anyway"
    )


def test_dispersion_and_drawdown_survive_on_a_rank_series():
    """Not everything is suppressed — a rank book has a dispersion and a path.

    Over-suppressing would be its own dishonesty: it would report an absence
    where a real measurement exists.
    """
    report = analyse(_series(scale=0.3), series_unit=SeriesUnit.RANK)
    for name in ("volatility", "max_drawdown"):
        if name in report.metrics:
            assert report.metrics[name].value is not None, (
                f"{name} is meaningful on a rank series and was suppressed"
            )


def test_a_return_series_suppresses_nothing():
    report = analyse(_series(), series_unit=SeriesUnit.RETURN)
    assert report.metrics["sharpe"].value is not None
    assert "NOT APPLICABLE" not in (report.metrics["sharpe"].caveat or "")


def test_the_default_series_unit_is_returns():
    """A caller that says nothing gets the return interpretation, as before."""
    assert analyse(_series()).metrics["sharpe"].value is not None


def test_suppression_clears_the_value_rather_than_dropping_the_metric():
    """The row stays, with its reason. A missing row reads as 'not measured'."""
    report = analyse(_series(scale=0.3), series_unit=SeriesUnit.RANK)
    assert "sharpe" in report.metrics, "the suppressed metric vanished from the report"
    assert report.metrics["sharpe"].caveat


# ── path-dependent metrics refuse an unordered series ───────────────────────

def test_a_drawdown_refuses_an_out_of_order_series():
    """Drawdown is a path. Shuffle the path and the answer is meaningless."""
    s = _series()
    shuffled = s.sample(frac=1.0, random_state=3)
    with pytest.raises(UnorderedSeries):
        max_drawdown(shuffled)


def test_the_refusal_names_the_metric_that_refused():
    s = _series()
    with pytest.raises(UnorderedSeries) as excinfo:
        max_drawdown(s.sample(frac=1.0, random_state=5))
    assert "max_drawdown" in str(excinfo.value)


def test_a_chronological_series_is_accepted():
    assert max_drawdown(_series()).value is not None


def test_a_non_path_metric_does_not_care_about_order():
    """Sharpe is order-independent. Refusing it would be superstition."""
    s = _series()
    a = sharpe(s).value
    b = sharpe(s.sample(frac=1.0, random_state=11)).value
    assert a is not None and b is not None
    assert a == pytest.approx(b), "a mean-over-dispersion metric changed under permutation"
