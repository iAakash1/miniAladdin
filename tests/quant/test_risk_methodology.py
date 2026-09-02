"""
Methodology, units and annualisation as structured data rather than prose.

Unit ambiguity is a standard way financial systems produce wrong answers
quietly: a ratio rendered with a percent sign, a per-period figure read as
annual, a loss magnitude read as a signed return. A consumer that is told the
unit cannot make those mistakes by accident.

The strongest test here is the coverage one — it fails when a metric is added to
`analyse` without an entry in the methodology table, which is the only way this
contract can rot.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.quant.risk import engine
from src.quant.risk.engine import Annualisation, Unit

PPY = 252.0


@pytest.fixture(scope="module")
def report():
    rng = np.random.default_rng(3)
    index = pd.bdate_range("2024-01-01", periods=400)
    returns = pd.Series(rng.normal(0.0004, 0.011, 400), index=index)
    benchmark = pd.Series(rng.normal(0.0003, 0.009, 400), index=index)
    return engine.analyse(returns, benchmark=benchmark,
                          periods_per_year=PPY, frequency="daily")


def test_every_served_metric_carries_structured_methodology(report):
    """Coverage. Fails when a metric is added without a table entry."""
    missing = [name for name, m in report.metrics.items() if m.methodology is None]
    assert missing == [], f"no methodology declared for: {missing}"


def test_the_table_declares_nothing_that_is_not_served(report):
    """The other direction: a stale entry for a removed metric."""
    stale = set(engine.METHODOLOGY) - set(report.metrics)
    assert stale == set(), f"methodology declared for metrics never served: {stale}"


def test_magnitudes_are_declared_as_magnitudes_and_are_non_negative(report):
    """Unit and sign must agree.

    A VaR declared RETURN_MAGNITUDE and returned negative would be rendered as a
    gain by any consumer that trusts the unit.
    """
    for name, metric in report.metrics.items():
        if metric.methodology.unit is Unit.RETURN_MAGNITUDE and metric.value is not None:
            assert metric.value >= 0, f"{name} is declared a magnitude but is negative"


def test_signed_drawdowns_are_declared_as_returns_and_are_non_positive(report):
    for name in ("max_drawdown", "average_drawdown"):
        metric = report.metrics[name]
        assert metric.methodology.unit is Unit.RETURN
        assert metric.value <= 0, f"{name} is a signed drawdown and must not be positive"


def test_unannualised_metrics_do_not_claim_a_periods_per_year(report):
    """A scaling factor on a number that was never scaled is decoration."""
    for name, metric in report.metrics.items():
        if metric.methodology.annualisation is Annualisation.NONE:
            assert metric.methodology.periods_per_year is None, name
        else:
            assert metric.methodology.periods_per_year == PPY, name


def test_dispersion_uses_sqrt_time_and_means_use_linear(report):
    assert report.metrics["volatility"].methodology.annualisation is Annualisation.SQRT_TIME
    assert report.metrics["tracking_error"].methodology.annualisation is Annualisation.SQRT_TIME
    assert report.metrics["capm_alpha"].methodology.annualisation is Annualisation.LINEAR
    # Calmar compares a growth rate against a decline, so it compounds.
    assert report.metrics["calmar"].methodology.annualisation is Annualisation.GEOMETRIC


def test_benchmark_relative_metrics_declare_both_inputs(report):
    for name in ("beta", "tracking_error", "information_ratio", "capm_alpha"):
        inputs = report.metrics[name].methodology.inputs
        assert "benchmark_return_series" in inputs, f"{name} must declare the benchmark"


def test_absolute_metrics_do_not_claim_a_benchmark(report):
    for name in ("volatility", "sharpe", "max_drawdown", "var_historical_95"):
        assert "benchmark_return_series" not in report.metrics[name].methodology.inputs


def test_methodology_survives_serialisation(report):
    payload = report.metrics["sharpe"].as_dict()
    assert payload["methodology"]["unit"] == "ratio"
    assert payload["methodology"]["frequency"] == "daily"
    assert payload["methodology"]["inputs"] == ["portfolio_return_series"]
    # The legacy field stays, because every existing consumer reads it.
    assert payload["method"] == "mean_over_std_annualised"


def test_a_metric_without_a_table_entry_is_passed_through_unchanged():
    """Attaching methodology must never drop a metric it does not recognise."""
    metric = engine.RiskMetric("unlisted", 1.0, "custom", 100)
    out = engine._with_methodology({"unlisted": metric},
                                   periods_per_year=PPY, frequency="daily")
    assert out["unlisted"].value == 1.0
    assert out["unlisted"].methodology is None


# ── series units ─────────────────────────────────────────────────────────────

def _rank_series(n: int = 300) -> pd.Series:
    rng = np.random.default_rng(9)
    return pd.Series(rng.uniform(-1, 1, n), index=pd.bdate_range("2024-01-01", periods=n))


def test_return_only_metrics_refuse_on_a_rank_series():
    """The defect this guard exists for.

    The portfolio surface builds a book-level series in cross-sectional rank
    units and it was producing a "Sharpe ratio" from it. The numerator is not a
    return, the denominator is not a volatility, and annualising asserts a
    period length the series does not have.
    """
    report = engine.analyse(_rank_series(), series_unit=engine.SeriesUnit.RANK)
    for name in engine.RETURN_ONLY_METRICS & set(report.metrics):
        metric = report.metrics[name]
        assert metric.value is None, f"{name} must not be computed on a rank series"
        assert "NOT APPLICABLE" in metric.caveat
        assert "rank series" in metric.caveat


def test_dispersion_and_drawdown_still_apply_to_a_rank_series():
    """Suppression must be surgical.

    A rank book genuinely has a dispersion and an underwater path. Blanking
    those too would throw away real measurements to avoid a naming problem.
    """
    report = engine.analyse(_rank_series(), series_unit=engine.SeriesUnit.RANK)
    for name in ("volatility", "max_drawdown", "ulcer_index",
                 "mean_absolute_deviation", "worst_realization"):
        assert report.metrics[name].value is not None, f"{name} was wrongly suppressed"


def test_a_return_series_is_unaffected():
    rng = np.random.default_rng(4)
    returns = pd.Series(rng.normal(0.0004, 0.01, 300),
                        index=pd.bdate_range("2024-01-01", periods=300))
    report = engine.analyse(returns, series_unit=engine.SeriesUnit.RETURN)
    assert report.metrics["sharpe"].value is not None


def test_the_default_is_return_so_existing_callers_are_unchanged():
    rng = np.random.default_rng(4)
    returns = pd.Series(rng.normal(0.0004, 0.01, 300),
                        index=pd.bdate_range("2024-01-01", periods=300))
    assert engine.analyse(returns).metrics["sharpe"].value is not None
