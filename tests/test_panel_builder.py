"""
Panel builder tests.

`test_appending_future_data_does_not_change_history` is the flagship. Every
other test in this repository checks that a computation is correct; that one
checks that a computation is *honest* — that a factor value for 2024-03-01
is identical whether or not the rest of 2024 has happened yet.

It is the only test that can fail because of a mistake nobody would notice
by reading the output. A look-ahead bug does not produce wrong-looking
numbers; it produces beautiful ones.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.panel.builder import PanelBuilder, _pit_window
from src.panel.schema import FACTOR_COLUMNS
from src.panel.storage import PanelStore
from src.panel.universe import Universe
from src.scoring.engine import MIN_BARS, detect_regimes

PRICE_FACTORS = ("r12_1", "r63", "r21", "vol_confirm", "high52_prox", "reversal")
UNAVAILABLE_FACTORS = (
    "target_upside", "earnings_yield", "pe_gap", "pead",
    "gross_profitability", "net_issuance", "asset_growth", "sentiment",
)


# ── synthetic market ─────────────────────────────────────────────────────────

def _prices(days: int, seed: int = 3, start: str = "2022-01-03") -> pd.DataFrame:
    """Deterministic OHLCV. Same seed and length ⇒ same bars, always."""
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(start, periods=days)
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.011, days)))
    return pd.DataFrame(
        {
            "Open": closes * 0.997,
            "High": closes * 1.008,
            "Low": closes * 0.992,
            "Close": closes,
            "Volume": rng.integers(1_000_000, 6_000_000, days).astype(float),
        },
        index=index,
    )


def _loader(frames: dict[str, pd.DataFrame]):
    """Injected price source — no network, fully deterministic."""
    return lambda symbol: frames.get(symbol)


def _as_known_on(frames: dict[str, pd.DataFrame], cutoff: date) -> dict[str, pd.DataFrame]:
    """The same market as it existed on `cutoff` — history with no future attached.

    Truncation, not regeneration: drawing a different number of randoms
    advances the RNG stream differently, which would produce a *different*
    market rather than an earlier view of the same one, and the look-ahead
    test would then be comparing two unrelated series.
    """
    return {
        symbol: frame[frame.index.date <= cutoff].copy()
        for symbol, frame in frames.items()
    }


@pytest.fixture
def market() -> dict[str, pd.DataFrame]:
    return {
        "AAPL": _prices(500, seed=1),
        "MSFT": _prices(500, seed=2),
        "SPY": _prices(500, seed=99),
    }


@pytest.fixture
def universe() -> Universe:
    return Universe.custom(["AAPL", "MSFT"], name="test")


# ── THE FLAGSHIP TEST ────────────────────────────────────────────────────────

def test_appending_future_data_does_not_change_history(universe: Universe):
    """Build, append a year of future bars, rebuild — history must not move.

    If any factor peeked forward, the extra bars would change a value for a
    date that already existed, and this comparison would fail. It is the
    difference between a backtest and a leak.
    """
    window_end = date(2023, 6, 30)

    with_future = {symbol: _prices(700, seed=seed)
                   for symbol, seed in (("AAPL", 1), ("MSFT", 2), ("SPY", 99))}
    known_then = _as_known_on(with_future, window_end)

    # Sanity: one is a strict prefix of the other, and the future is real.
    pd.testing.assert_frame_equal(
        known_then["AAPL"], with_future["AAPL"].iloc[: len(known_then["AAPL"])]
    )
    assert with_future["AAPL"].index.max().date() > window_end
    assert len(with_future["AAPL"]) > len(known_then["AAPL"]) + 250

    before, _ = PanelBuilder(fundamentals=False, load_prices=_loader(known_then)).build(
        universe, date(2023, 1, 1), window_end
    )
    after, _ = PanelBuilder(fundamentals=False, load_prices=_loader(with_future)).build(
        universe, date(2023, 1, 1), window_end
    )

    assert not before.empty
    pd.testing.assert_frame_equal(
        before.sort_values(["date", "symbol"]).reset_index(drop=True),
        after.sort_values(["date", "symbol"]).reset_index(drop=True),
    )


def test_appending_future_data_does_not_change_stored_bytes(
    universe: Universe, tmp_path
):
    """The same guarantee, one level down: identical history ⇒ identical hash."""
    with_future = {s: _prices(700, seed=k) for s, k in (("AAPL", 1), ("MSFT", 2), ("SPY", 99))}
    known_then = _as_known_on(with_future, date(2023, 6, 30))

    hashes = []
    for index, frames in enumerate((known_then, with_future)):
        frame, manifest = PanelBuilder(fundamentals=False, load_prices=_loader(frames)).build(
            universe, date(2023, 1, 1), date(2023, 6, 30)
        )
        store = PanelStore(tmp_path / f"store{index}")
        hashes.append(store.write(frame, manifest).content_hash)

    assert hashes[0] == hashes[1]


def test_rebuild_is_byte_identical(universe: Universe, market, tmp_path):
    """Determinism: the same build twice produces the same bytes."""
    hashes = []
    for index in range(2):
        frame, manifest = PanelBuilder(fundamentals=False, load_prices=_loader(market)).build(
            universe, date(2023, 1, 1), date(2023, 3, 31)
        )
        hashes.append(PanelStore(tmp_path / f"s{index}").write(frame, manifest).content_hash)
    assert hashes[0] == hashes[1]


# ── the mechanism ────────────────────────────────────────────────────────────

def test_pit_window_includes_the_observation_day(market):
    window = _pit_window(market["AAPL"], date(2022, 6, 15))
    assert window.index.max().date() == date(2022, 6, 15)


def test_pit_window_excludes_everything_after(market):
    window = _pit_window(market["AAPL"], date(2022, 6, 15))
    assert (window.index.date <= date(2022, 6, 15)).all()
    assert len(window) < len(market["AAPL"])


def test_pit_window_on_a_non_trading_day_takes_the_prior_close(market):
    """2022-06-18 is a Saturday; the window must end on Friday the 17th."""
    window = _pit_window(market["AAPL"], date(2022, 6, 18))
    assert window.index.max().date() == date(2022, 6, 17)


# ── shape and content ────────────────────────────────────────────────────────

def test_rows_stay_within_the_requested_range(universe: Universe, market):
    frame, _ = PanelBuilder(fundamentals=False, load_prices=_loader(market)).build(
        universe, date(2023, 2, 1), date(2023, 2, 28)
    )
    assert frame["date"].min() >= date(2023, 2, 1)
    assert frame["date"].max() <= date(2023, 2, 28)


def test_price_factors_are_populated(universe: Universe, market):
    frame, _ = PanelBuilder(fundamentals=False, load_prices=_loader(market)).build(
        universe, date(2023, 2, 1), date(2023, 2, 28)
    )
    for factor in PRICE_FACTORS:
        assert frame[factor].notna().any(), f"{factor} was never computed"


def test_unavailable_factors_are_null_not_zero(universe: Universe, market):
    """Fundamentals have no point-in-time source yet. Null says so; 0.0 would lie."""
    frame, _ = PanelBuilder(fundamentals=False, load_prices=_loader(market)).build(
        universe, date(2023, 2, 1), date(2023, 2, 28)
    )
    for factor in UNAVAILABLE_FACTORS:
        assert frame[factor].isna().all(), f"{factor} should be absent, not valued"


def test_as_of_equals_date_for_price_factors(universe: Universe, market):
    frame, _ = PanelBuilder(fundamentals=False, load_prices=_loader(market)).build(
        universe, date(2023, 2, 1), date(2023, 2, 28)
    )
    assert (frame["date"] == frame["as_of"]).all()


def test_dtypes_are_pinned(universe: Universe, market):
    frame, _ = PanelBuilder(fundamentals=False, load_prices=_loader(market)).build(
        universe, date(2023, 2, 1), date(2023, 2, 28)
    )
    for factor in FACTOR_COLUMNS:
        assert frame[factor].dtype == "float64", f"{factor} drifted to {frame[factor].dtype}"
    assert frame["bars"].dtype == "int32"


def test_data_completeness_reflects_populated_factors(universe: Universe, market):
    frame, _ = PanelBuilder(fundamentals=False, load_prices=_loader(market)).build(
        universe, date(2023, 2, 1), date(2023, 2, 28)
    )
    row = frame.iloc[0]
    computed = sum(1 for factor in FACTOR_COLUMNS if pd.notna(row[factor]))
    assert row["data_completeness"] == pytest.approx(computed / len(FACTOR_COLUMNS), abs=1e-4)


def test_bars_counts_only_visible_history(universe: Universe, market):
    """`bars` must grow monotonically — proof each row saw a longer window."""
    frame, _ = PanelBuilder(fundamentals=False, load_prices=_loader(market)).build(
        universe, date(2023, 2, 1), date(2023, 2, 28)
    )
    aapl = frame[frame["symbol"] == "AAPL"].sort_values("date")
    assert aapl["bars"].is_monotonic_increasing
    assert aapl["bars"].nunique() == len(aapl)


# ── trailing lookback ────────────────────────────────────────────────────────

def test_lookback_caps_the_window(universe: Universe, market):
    frame, _ = PanelBuilder(fundamentals=False, load_prices=_loader(market), lookback=200).build(
        universe, date(2023, 2, 1), date(2023, 2, 28)
    )
    assert frame["bars"].max() == 200


def test_lookback_makes_window_length_stationary(universe: Universe, market):
    """Every cell with enough history is normalized over the same sample size.

    Without this, an early cell is z-scored against 60 observations and a
    late one against thousands, and the two values are not comparable.
    """
    frame, _ = PanelBuilder(fundamentals=False, load_prices=_loader(market), lookback=200).build(
        universe, date(2023, 1, 3), date(2023, 6, 30)
    )
    assert frame["bars"].nunique() == 1


def test_lookback_does_not_reintroduce_look_ahead(universe: Universe, market):
    """A trailing bound must not weaken the upper bound."""
    window = _pit_window(market["AAPL"], date(2022, 6, 15), lookback=50)
    assert len(window) == 50
    assert window.index.max().date() == date(2022, 6, 15)


def test_default_lookback_exceeds_realistic_vendor_depth():
    """The lookback must stay ahead of how much history vendors return.

    This replaces a test that pinned the literal `1260`, which is precisely
    why the regression it was meant to guard went unnoticed: vendors grew to
    ~1830 bars for the same "5y" request, every symbol fell past the cap,
    `is_exact_for` refused the vectorized path, and a mega30 build went from
    1.9 s to 29.3 s — silently, because the constant still equalled the number
    the test asserted.

    Pinning the *property* catches that; pinning the value never could.
    """
    from src.panel.builder import LOOKBACK_BARS

    # Observed vendor depth for a "5y" request, with headroom for growth.
    assert LOOKBACK_BARS >= 2000, (
        f"lookback {LOOKBACK_BARS} is at or below observed vendor depth (~1830 "
        "bars); every symbol will fall back to the scalar path"
    )


def test_realistic_history_uses_the_vectorized_path(universe: Universe):
    """A vendor-sized history must not trigger the scalar cliff.

    The end-to-end version of the test above: build with a frame the size
    vendors actually return and assert the manifest reports zero symbols on
    the slow path.
    """
    frames = {symbol: _prices(1830, seed=seed)
              for symbol, seed in (("AAPL", 1), ("MSFT", 2), ("SPY", 99))}
    _, manifest = PanelBuilder(fundamentals=False, load_prices=_loader(frames)).build(
        universe, date(2025, 1, 2), date(2025, 6, 30)
    )
    assert "scalar:0" in manifest.notes, manifest.notes


# ── regimes are point-in-time too ────────────────────────────────────────────

@pytest.mark.parametrize("vectorized", [True, False])
def test_regimes_match_the_engine_at_the_observation_date(universe, market, vectorized):
    """Both engines must label regimes exactly as `detect_regimes` would.

    Asserted against the engine rather than by spying on a call, so it
    covers the vectorized path (which never calls `detect_regimes`) as well
    as the scalar one. It also pins the point-in-time property: a wall-clock
    implementation would put every row in the same FOMC bucket, which
    `test_fomc_flag_varies_across_history` shows is not the case.
    """
    frame, _ = PanelBuilder(
        fundamentals=False, load_prices=_loader(market), vectorized=vectorized
    ).build(universe, date(2023, 1, 3), date(2023, 6, 30))

    assert not frame.empty
    for row in frame.itertuples():
        history = market[row.symbol]
        window = history[history.index.date <= row.date].tail(1260)
        expected = ",".join(detect_regimes(window, None, row.date))
        assert row.regimes == expected, f"{row.symbol} {row.date}"


def test_regime_oracle_is_not_vacuous(universe, market):
    """Guards the test above from passing trivially.

    `high_volatility` must actually vary across the panel, or comparing
    against `detect_regimes` proves nothing. Note this checks volatility and
    not FOMC: the shipped calendar holds only the current year's meetings,
    so `fomc_window` is False for every historical row (docs/PANEL.md §5.4)
    and could never make this assertion meaningful.
    """
    frame, _ = PanelBuilder(fundamentals=False, load_prices=_loader(market)).build(
        universe, date(2023, 1, 3), date(2023, 6, 30)
    )
    flags = {"high_volatility" in regimes for regimes in frame["regimes"]}
    assert flags == {True, False}, "regime never changes — oracle test is vacuous"


def test_fomc_regime_is_never_labelled_for_history(universe, market):
    """Pins a known limitation so it is not mistaken for a bug.

    `FOMC_DECISION_DATES` covers only the current year, so
    `business_days_to_next_fomc` returns a large number for any past date and
    the regime never fires historically. When a full historical calendar is
    added, this test fails — which is the signal to update docs/PANEL.md.
    """
    frame, _ = PanelBuilder(fundamentals=False, load_prices=_loader(market)).build(
        universe, date(2023, 1, 3), date(2023, 6, 30)
    )
    assert not frame["regimes"].str.contains("fomc_window").any()


# ── the two engines agree ────────────────────────────────────────────────────

def _both_engines(universe, market):
    return [
        PanelBuilder(fundamentals=False, load_prices=_loader(market), vectorized=flag).build(
            universe, date(2023, 1, 3), date(2023, 6, 30)
        )
        for flag in (True, False)
    ]


def test_both_engines_agree_to_floating_point_round_off(universe, market):
    """End-to-end proof that the fast path changed speed and nothing else."""
    (fast, fast_manifest), (slow, slow_manifest) = _both_engines(universe, market)

    assert "vectorized:2/scalar:0" in fast_manifest.notes
    assert "vectorized:0/scalar:2" in slow_manifest.notes
    assert (fast["regimes"] == slow["regimes"]).all()
    pd.testing.assert_frame_equal(fast, slow, check_exact=False, rtol=0, atol=1e-15)


def test_engine_choice_moves_values_by_at_most_one_ulp(universe, market):
    """Bounds the disagreement rather than trusting a default tolerance.

    `assert_frame_equal` defaults to rtol=1e-5, which would hide a real
    divergence. Measured, the two paths differ by at most ~1.1e-16 — one
    unit in the last place, from floating-point operation order, not from
    different arithmetic.
    """
    (fast, _), (slow, _) = _both_engines(universe, market)

    worst = 0.0
    for name in PRICE_FACTORS + ("rel21_vs_spy",):
        left, right = fast[name].to_numpy(), slow[name].to_numpy()
        both = ~(np.isnan(left) | np.isnan(right))
        assert np.isnan(left).tolist() == np.isnan(right).tolist(), f"{name} nullity differs"
        if both.any():
            worst = max(worst, float(np.max(np.abs(left[both] - right[both]))))
    assert worst <= 2e-16, f"engines disagree by {worst:.3e}, more than round-off"


def test_content_hash_is_reproducible_per_engine_not_across_them(
    universe, market, tmp_path
):
    """Pins a reproducibility boundary that Phase 4 depends on.

    Byte-level equality holds for repeated builds on the *same* engine, and
    does not hold across engines: a 1-ULP value difference changes the
    Parquet bytes. The manifest therefore records which engine ran, and
    `omni verify` must rebuild with the engine named there.
    """
    hashes = []
    for index, vectorized in enumerate((True, False, True)):
        frame, manifest = PanelBuilder(
            load_prices=_loader(market), vectorized=vectorized
        ).build(universe, date(2023, 1, 3), date(2023, 6, 30))
        hashes.append(PanelStore(tmp_path / f"e{index}").write(frame, manifest).content_hash)

    assert hashes[0] == hashes[2], "same engine must reproduce byte-for-byte"
    assert hashes[0] != hashes[1], (
        "engines now agree bit-for-bit — remove the per-engine caveat from "
        "docs/PANEL.md and this test"
    )


def test_long_history_falls_back_to_the_scalar_engine(universe, market):
    """Outside the fast path's exactness domain, the builder must not use it."""
    _, manifest = PanelBuilder(
        fundamentals=False, load_prices=_loader(market), lookback=300
    ).build(universe, date(2023, 1, 3), date(2023, 6, 30))
    assert "vectorized:0/scalar:2" in manifest.notes


# ── degenerate inputs ────────────────────────────────────────────────────────

def test_symbol_with_too_little_history_is_skipped(market):
    frames = dict(market)
    frames["TINY"] = _prices(MIN_BARS - 1)
    universe = Universe.custom(["AAPL", "TINY"], name="test")

    frame, manifest = PanelBuilder(fundamentals=False, load_prices=_loader(frames)).build(
        universe, date(2023, 2, 1), date(2023, 2, 28)
    )

    assert manifest.symbols_skipped == ["TINY"]
    assert manifest.symbols_built == 1
    assert set(frame["symbol"]) == {"AAPL"}


def test_missing_symbol_is_skipped_not_fatal(market):
    universe = Universe.custom(["AAPL", "NOPE"], name="test")
    frame, manifest = PanelBuilder(fundamentals=False, load_prices=_loader(market)).build(
        universe, date(2023, 2, 1), date(2023, 2, 28)
    )
    assert manifest.symbols_skipped == ["NOPE"]
    assert not frame.empty


def test_loader_exception_does_not_fail_the_build(market):
    def flaky(symbol: str):
        if symbol == "BOOM":
            raise RuntimeError("vendor exploded")
        return market.get(symbol)

    universe = Universe.custom(["AAPL", "BOOM"], name="test")
    frame, manifest = PanelBuilder(fundamentals=False, load_prices=flaky).build(
        universe, date(2023, 2, 1), date(2023, 2, 28)
    )
    assert manifest.symbols_skipped == ["BOOM"]
    assert not frame.empty


def test_missing_benchmark_nulls_relative_strength_only(universe: Universe, market):
    """SPY down must not take the whole build down with it."""
    without_spy = {k: v for k, v in market.items() if k != "SPY"}
    frame, _ = PanelBuilder(fundamentals=False, load_prices=_loader(without_spy)).build(
        universe, date(2023, 2, 1), date(2023, 2, 28)
    )
    assert frame["rel21_vs_spy"].isna().all()
    assert frame["r63"].notna().any()


def test_empty_result_is_a_valid_empty_panel(universe: Universe):
    frame, manifest = PanelBuilder(fundamentals=False, load_prices=lambda s: None).build(
        universe, date(2023, 2, 1), date(2023, 2, 28)
    )
    assert frame.empty
    assert manifest.symbols_built == 0
    assert list(frame.columns)[:3] == ["symbol", "date", "as_of"]


def test_range_entirely_before_available_history(universe: Universe, market):
    frame, _ = PanelBuilder(fundamentals=False, load_prices=_loader(market)).build(
        universe, date(2010, 1, 1), date(2010, 12, 31)
    )
    assert frame.empty


# ── stride ───────────────────────────────────────────────────────────────────

def test_step_reduces_observations_without_changing_them(universe: Universe, market):
    """Stride changes how often we observe, never what is visible."""
    daily, _ = PanelBuilder(fundamentals=False, load_prices=_loader(market)).build(
        universe, date(2023, 1, 3), date(2023, 3, 31), step=1
    )
    weekly, _ = PanelBuilder(fundamentals=False, load_prices=_loader(market)).build(
        universe, date(2023, 1, 3), date(2023, 3, 31), step=5
    )

    assert 0 < len(weekly) < len(daily)

    # Every weekly row must equal the daily row for the same (symbol, date).
    merged = weekly.merge(daily, on=["symbol", "date"], suffixes=("_w", "_d"))
    assert len(merged) == len(weekly)
    for factor in PRICE_FACTORS:
        pd.testing.assert_series_equal(
            merged[f"{factor}_w"], merged[f"{factor}_d"], check_names=False
        )


# ── argument validation ──────────────────────────────────────────────────────

def test_reversed_range_is_rejected(universe: Universe, market):
    with pytest.raises(ValueError, match="is after end"):
        PanelBuilder(fundamentals=False, load_prices=_loader(market)).build(
            universe, date(2023, 6, 1), date(2023, 1, 1)
        )


@pytest.mark.parametrize("step", [0, -1])
def test_non_positive_step_is_rejected(universe: Universe, market, step):
    with pytest.raises(ValueError, match="step must be"):
        PanelBuilder(fundamentals=False, load_prices=_loader(market)).build(
            universe, date(2023, 1, 1), date(2023, 3, 1), step=step
        )


# ── manifest provenance ──────────────────────────────────────────────────────

def test_manifest_records_reproducible_inputs(universe: Universe, market):
    _, manifest = PanelBuilder(fundamentals=False, load_prices=_loader(market)).build(
        universe, date(2023, 2, 1), date(2023, 2, 28)
    )
    assert manifest.universe == "test"
    assert manifest.symbols == ["AAPL", "MSFT"]
    assert manifest.start == date(2023, 2, 1)
    assert manifest.end == date(2023, 2, 28)
    assert manifest.engine_version.startswith("scoring-")
    assert manifest.step == 1
    assert manifest.lookback > 0
    assert manifest.benchmark == "SPY"
    assert manifest.fundamentals is False
    assert manifest.vectorized is True
    assert manifest.git_commit != ""
    assert set(manifest.raw_data_hashes) == {"price:AAPL", "price:MSFT", "price:SPY"}
    assert "raw observations are not archived" in manifest.reproducibility_status
    assert manifest.build_seconds > 0


def test_manifest_id_changes_with_stride_and_engine_path(universe: Universe, market):
    daily = PanelBuilder(fundamentals=False, load_prices=_loader(market)).build(
        universe, date(2023, 2, 1), date(2023, 2, 28), step=1
    )[1]
    weekly = PanelBuilder(fundamentals=False, load_prices=_loader(market)).build(
        universe, date(2023, 2, 1), date(2023, 2, 28), step=5
    )[1]
    scalar = PanelBuilder(
        fundamentals=False, load_prices=_loader(market), vectorized=False
    ).build(universe, date(2023, 2, 1), date(2023, 2, 28), step=1)[1]

    assert daily.snapshot_id != weekly.snapshot_id
    assert daily.snapshot_id != scalar.snapshot_id


def test_manifest_id_is_stable_across_rebuilds(universe: Universe, market):
    ids = {
        PanelBuilder(fundamentals=False, load_prices=_loader(market))
        .build(universe, date(2023, 2, 1), date(2023, 2, 28))[1]
        .snapshot_id
        for _ in range(2)
    }
    assert len(ids) == 1
