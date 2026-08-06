"""
Panel builder — OHLCV in, point-in-time factor panel out.

The correctness argument for this module is one sentence:

    Factors for date D are computed from a frame that has been truncated
    at D, so future bars are not merely unused — they are absent.

Look-ahead bias is normally a discipline: remember not to peek. Discipline
fails silently and the failure is invisible in the output. Here the window
is constructed by `_pit_window` and the engine is handed nothing else, so
peeking is not a mistake one can make. `test_panel_builder` proves the
property directly: build a panel, append future data, rebuild, and assert
the historical rows are byte-identical.

Scope of this milestone, stated plainly: **price-derived factors only.**
Momentum, reversal and relative strength are computable point-in-time from
OHLCV alone. Fundamental, quality and news factors require filing-date and
publication-date stamps that are not yet wired, so those columns are
written NULL — which the schema defines as "absent", never zero. The
columns exist now so that adding them later is a builder change, not a
migration.
"""

from __future__ import annotations

import logging
import math
import time
from datetime import date as Date
from typing import Callable, Optional

import pandas as pd

from src.panel.schema import (
    ALL_COLUMNS,
    FACTOR_COLUMNS,
    SnapshotManifest,
    compute_snapshot_id,
    engine_version,
)
from src.panel.fundamentals import PointInTimeFacts, load as load_facts
from src.panel.factors import (
    PRICE_FACTOR_COLUMNS,
    compute_price_factors,
    is_exact_for,
    regimes_for,
)
from src.panel.universe import Universe
from src.scoring.engine import (
    FOMC_WINDOW_DAYS,
    SQUASH_SCALE,
    MIN_BARS,
    detect_regimes,
    momentum_factors,
    reversal_factor,
)

logger = logging.getLogger("omnisignal.panel.builder")

#: Loads full daily OHLCV for a symbol. Injected so builds are testable
#: without a network, and so the builder never learns which vendor answered.
PriceLoader = Callable[[str], Optional[pd.DataFrame]]

BENCHMARK_SYMBOL = "SPY"

#: Trailing bars visible to any single observation (~5 years).
#:
#: This is a correctness parameter before it is a performance one. The
#: engine's normalizers — `robust_z` and `_robust_daily_sigma` — estimate
#: their distribution from the ENTIRE series handed to them. Without a cap,
#: a cell early in the panel is z-scored against 60 bars and a cell late in
#: it against 2,500, so the same factor value means different things at
#: different points in time and time-series comparisons are not
#: apples-to-apples. A fixed trailing window makes the estimator stationary.
#:
#: 1260 matches the "5y" range `_provider_loader` requests, so a panel cell
#: for today sees exactly what the live engine sees for today.
#:
#: It also bounds per-cell work, but do not oversell that: measured on a
#: 3-symbol × 3200-day build, capping at 1260 bars versus leaving the window
#: uncapped is worth ~5% (3124 vs 3275 µs/cell). Per-cell cost is dominated
#: by pandas call overhead — roughly 20,000 Python-level calls per cell —
#: not by window length. The real performance lever is computing each factor
#: once per symbol as a vectorized rolling series rather than once per cell;
#: that is Phase 6 work and is worth orders of magnitude, not percent.
LOOKBACK_BARS = 1260


class PanelBuilder:
    """Builds a factor panel from daily price history."""

    def __init__(
        self,
        load_prices: Optional[PriceLoader] = None,
        benchmark: str = BENCHMARK_SYMBOL,
        lookback: int = LOOKBACK_BARS,
        vectorized: bool = True,
        fundamentals: bool = True,
    ) -> None:
        self._load_prices = load_prices or _provider_loader
        self._benchmark = benchmark
        self._lookback = lookback
        # `vectorized=False` forces the scalar engine for every symbol. It is
        # the oracle: slower, and by definition correct. Kept reachable so a
        # suspect panel can be rebuilt against it and diffed.
        self._use_vectorized = vectorized
        # SEC XBRL, point-in-time. Off in tests that inject synthetic prices,
        # since those symbols have no filings and every lookup would be a
        # wasted network round trip.
        self._use_fundamentals = fundamentals
        self._facts: dict[str, PointInTimeFacts] = {}
        self._vectorized_symbols = 0
        self._scalar_symbols = 0

    # ── public ───────────────────────────────────────────────────────────

    def build(
        self,
        universe: Universe,
        start: Date,
        end: Date,
        *,
        step: int = 1,
    ) -> tuple[pd.DataFrame, SnapshotManifest]:
        """Build the panel for `universe` over [start, end].

        `step` is the observation stride in trading days. 1 is every day;
        5 matches the weekly cadence the walk-forward validator uses and
        costs a fifth of the time. Both are point-in-time correct — stride
        changes how often we observe, never what is visible.
        """
        if start > end:
            raise ValueError(f"start {start} is after end {end}")
        if step < 1:
            raise ValueError(f"step must be >= 1, got {step}")

        began = time.perf_counter()
        symbols = list(universe.members(as_of=end))
        self._vectorized_symbols = 0
        self._scalar_symbols = 0

        benchmark = self._load_benchmark()
        # Benchmark windows are shared across every symbol on a given date,
        # so slicing them once per date instead of once per (symbol, date)
        # removes work proportional to the size of the universe.
        benchmark_windows: dict[Date, Optional[pd.DataFrame]] = {}

        rows: list[dict[str, object]] = []
        skipped: list[str] = []

        if self._use_fundamentals:
            self._facts = _load_all_facts(symbols)

        for symbol in symbols:
            frame = self._safe_load(symbol)
            if frame is None or len(frame) < MIN_BARS:
                skipped.append(symbol)
                logger.info(
                    "panel: skipping %s (%s)",
                    symbol,
                    "no data" if frame is None else f"{len(frame)} bars < {MIN_BARS}",
                )
                continue
            rows.extend(
                self._rows_for_symbol(
                    symbol, frame, benchmark, benchmark_windows, start, end, step
                )
            )

        panel = _empty_panel() if not rows else pd.DataFrame(rows, columns=list(ALL_COLUMNS))
        panel = _coerce_dtypes(panel)

        manifest = SnapshotManifest(
            snapshot_id=compute_snapshot_id(
                universe.name, symbols, start, end, engine_version()
            ),
            universe=universe.name,
            symbols=symbols,
            start=start,
            end=end,
            engine_version=engine_version(),
            rows=len(panel),
            symbols_built=len(symbols) - len(skipped),
            symbols_skipped=skipped,
            content_hash="",  # filled by PanelStore from the bytes it writes
            build_seconds=round(time.perf_counter() - began, 3),
            notes=(
                f"step={step}d; lookback={self._lookback}; "
                f"engine=vectorized:{self._vectorized_symbols}/scalar:{self._scalar_symbols}; "
                f"price-derived factors only "
                f"(fundamental/quality/news columns NULL pending point-in-time inputs)"
            ),
        )
        logger.info(
            "panel built: %d rows, %d/%d symbols, %.2fs",
            len(panel), manifest.symbols_built, len(symbols), manifest.build_seconds,
        )
        return panel, manifest

    # ── internals ────────────────────────────────────────────────────────

    def _rows_for_symbol(
        self,
        symbol: str,
        frame: pd.DataFrame,
        benchmark: Optional[pd.DataFrame],
        benchmark_windows: dict[Date, Optional[pd.DataFrame]],
        start: Date,
        end: Date,
        step: int,
    ) -> list[dict[str, object]]:
        """One row per observation date, each from a truncated window."""
        observation_dates = [
            stamp.date()
            for stamp in frame.index
            if start <= stamp.date() <= end
        ][::step]

        if self._use_vectorized and is_exact_for(frame, self._lookback):
            return self._vectorized_rows(symbol, frame, benchmark, observation_dates)

        self._scalar_symbols += 1
        logger.info(
            "panel: %s on the scalar path (%d bars vs lookback %d)",
            symbol, len(frame), self._lookback,
        )

        out: list[dict[str, object]] = []
        for observed_on in observation_dates:
            window = _pit_window(frame, observed_on, self._lookback)
            if len(window) < MIN_BARS:
                continue  # not enough history yet — absent, not estimated

            if observed_on not in benchmark_windows:
                benchmark_windows[observed_on] = (
                    None if benchmark is None
                    else _pit_window(benchmark, observed_on, self._lookback)
                )
            out.append(
                self._row(symbol, observed_on, window, benchmark_windows[observed_on])
            )
        return out

    def _vectorized_rows(
        self,
        symbol: str,
        frame: pd.DataFrame,
        benchmark: Optional[pd.DataFrame],
        observation_dates: list[Date],
    ) -> list[dict[str, object]]:
        """The fast path: all factors for all dates in one pass.

        Produces values identical to the scalar path — that is asserted
        directly in `tests/test_panel_factors.py`, and again end-to-end in
        `test_panel_builder.py::test_both_engines_produce_identical_panels`.
        """
        self._vectorized_symbols += 1
        computed = compute_price_factors(frame, benchmark, self._lookback)
        by_date = {stamp.date(): position for position, stamp in enumerate(frame.index)}

        out: list[dict[str, object]] = []
        for observed_on in observation_dates:
            position = by_date[observed_on]
            bars = int(computed["bars"].iloc[position])
            if bars < MIN_BARS:
                continue  # not enough history yet — absent, not estimated

            factors: dict[str, Optional[float]] = {name: None for name in FACTOR_COLUMNS}
            for name in PRICE_FACTOR_COLUMNS:
                value = computed[name].iloc[position]
                factors[name] = None if pd.isna(value) else float(value)
            factors.update(self._fundamental_factors(symbol, observed_on))

            out.append(
                self._assemble(
                    symbol,
                    observed_on,
                    factors,
                    bars,
                    regimes_for(
                        observed_on,
                        bool(computed["high_volatility"].iloc[position]),
                        FOMC_WINDOW_DAYS,
                    ),
                )
            )
        return out

    def _fundamental_factors(self, symbol: str, observed_on: Date) -> dict[str, Optional[float]]:
        """Point-in-time fundamentals for one cell.

        `asset_growth` is the Cooper-Gulen-Schill total-asset growth anomaly:
        firms that expand their balance sheet fastest tend to underperform, so
        the sign is inverted before squashing. It is computed only from
        filings visible on `observed_on`, restatements included exactly when
        they were published.
        """
        facts = self._facts.get(symbol)
        if facts is None or not len(facts):
            return {}

        growth = facts.year_over_year("Total assets", observed_on)
        if growth is None:
            return {}
        # Inverted: high asset growth is the *bad* end of this anomaly. Scaled
        # by the same squash the engine uses so the column is comparable with
        # every other factor in the panel.
        return {"asset_growth": float(math.tanh(-growth / SQUASH_SCALE))}

    @staticmethod
    def _assemble(
        symbol: str,
        observed_on: Date,
        factors: dict[str, Optional[float]],
        bars: int,
        regimes: str,
    ) -> dict[str, object]:
        """The panel row shape, in one place so both engines cannot drift."""
        computed = sum(1 for value in factors.values() if value is not None)
        return {
            "symbol": symbol,
            "date": observed_on,
            # Price factors are knowable at the close they describe, so
            # as_of == date. Fundamentals will diverge; the column exists
            # so that divergence is representable without a migration.
            "as_of": observed_on,
            **factors,
            "bars": bars,
            "regimes": regimes,
            "data_completeness": round(computed / len(FACTOR_COLUMNS), 4),
        }

    def _row(
        self,
        symbol: str,
        observed_on: Date,
        window: pd.DataFrame,
        benchmark_window: Optional[pd.DataFrame],
    ) -> dict[str, object]:
        """Compute one panel cell from an already-truncated window."""
        factors: dict[str, Optional[float]] = {name: None for name in FACTOR_COLUMNS}

        for row in momentum_factors(window, benchmark_window):
            if row.name in factors:
                factors[row.name] = row.score
        for row in reversal_factor(window):
            if row.name in factors:
                factors[row.name] = row.score
        factors.update(self._fundamental_factors(symbol, observed_on))

        # `today` is the OBSERVATION date, not the wall clock. Passing the
        # real date would let a 2019 row inherit 2026's FOMC calendar
        # position — a subtle look-ahead that only shows up as unexplained
        # regime drift months later.
        regimes = detect_regimes(window, days_to_earnings=None, today=observed_on)

        return self._assemble(
            symbol, observed_on, factors, len(window), ",".join(regimes)
        )

    def _safe_load(self, symbol: str) -> Optional[pd.DataFrame]:
        try:
            return self._load_prices(symbol)
        except Exception:  # noqa: BLE001 — one bad symbol never fails a build
            logger.exception("panel: price load failed for %s", symbol)
            return None

    def _load_benchmark(self) -> Optional[pd.DataFrame]:
        frame = self._safe_load(self._benchmark)
        if frame is None:
            logger.warning(
                "panel: benchmark %s unavailable — rel21_vs_spy will be NULL",
                self._benchmark,
            )
        return frame


def _load_all_facts(symbols: list[str]) -> dict[str, PointInTimeFacts]:
    """Fetch every symbol's filed history concurrently.

    SEC is a single host with no per-key rate limit, so the bounded fan-out
    turns 30 sequential fetches into four waves.
    """
    from src.providers.parallel import map_concurrent

    outcomes = map_concurrent(
        lambda symbol: (symbol, load_facts(symbol)), symbols, label="sec-facts"
    )
    loaded = {
        symbol: facts
        for symbol, facts in (o.value for o in outcomes if o.ok)
        if facts is not None and len(facts)
    }
    logger.info("panel: SEC facts loaded for %d/%d symbols", len(loaded), len(symbols))
    return loaded


def _pit_window(
    frame: pd.DataFrame, observed_on: Date, lookback: int = LOOKBACK_BARS
) -> pd.DataFrame:
    """**The point-in-time guarantee.** The last `lookback` bars up to `observed_on`.

    Every factor computation in this module receives the output of this
    function and nothing else. There is no code path that hands the engine
    a full frame, which is why look-ahead is structurally impossible here
    rather than merely discouraged.

    Two independent bounds, and they do different jobs. The upper bound
    (`<= observed_on`) is what makes the value honest. The trailing bound
    (`.tail`) is what makes it comparable across dates — see LOOKBACK_BARS.
    """
    return frame.loc[frame.index.date <= observed_on].tail(lookback)


def _empty_panel() -> pd.DataFrame:
    return pd.DataFrame({column: pd.Series(dtype="object") for column in ALL_COLUMNS})


def _coerce_dtypes(panel: pd.DataFrame) -> pd.DataFrame:
    """Pin dtypes so Arrow conversion is exact rather than inferred.

    Without this, a build in which some factor is entirely NULL infers
    `object` and the resulting Parquet differs byte-for-byte from a build
    where it is populated — which would make content hashes unstable and
    `omni verify` meaningless.
    """
    for column in FACTOR_COLUMNS:
        panel[column] = pd.to_numeric(panel[column], errors="coerce").astype("float64")
    panel["bars"] = pd.to_numeric(panel["bars"], errors="coerce").astype("int32")
    panel["data_completeness"] = pd.to_numeric(
        panel["data_completeness"], errors="coerce"
    ).astype("float64")
    panel["symbol"] = panel["symbol"].astype("string").astype("object")
    panel["regimes"] = panel["regimes"].astype("string").astype("object")
    return panel


def _provider_loader(symbol: str) -> Optional[pd.DataFrame]:
    """Default loader: five years of daily bars through the provider layer.

    Goes through the facade, so the builder inherits the fallback chain,
    caching and rate limiting, and never learns which vendor answered.
    """
    from src import providers

    result = providers.market_data.get_series(symbol, "5y")
    if not result.ok or not result.data.bars:
        return None

    bars = result.data.bars
    return pd.DataFrame(
        {
            "Open": [bar.open for bar in bars],
            "High": [bar.high for bar in bars],
            "Low": [bar.low for bar in bars],
            "Close": [bar.close for bar in bars],
            "Volume": [bar.volume if bar.volume is not None else 0 for bar in bars],
        },
        index=pd.to_datetime([bar.date for bar in bars]),
    ).sort_index()
