"""
Options features — implied volatility level, skew, term structure and the risk premium.

## Two sources, deliberately both

`volatility_history` is a dated snapshot carrying `iv_current`, `hv_current`
and 52-week IV/HV extremes. IV rank and the implied-minus-realised spread come
straight out of it at almost no cost.

`option_chain` is 116,487,570 rows and supplies the two things the snapshot
table cannot express: **skew** (25-delta put IV minus 25-delta call IV) and
**term structure** (near-expiry ATM IV against far). Those are aggregated
inside Dolt to ~278,000 rows per year, so the chain is paid for exactly once
and only for what it uniquely provides.

## The join is "latest on or before", never "nearest"

Both option sources have irregular cadence — 48 distinct dates in 2019, 259 in
2025 — and their snapshot dates do not always fall on trading days (2024-01-01
is a market holiday and carries 93,956 chain rows). So the attach is a
backward `merge_asof`: a panel row dated `d` sees the most recent option
snapshot at or before `d`.

`direction="nearest"` would be the natural-looking choice and is a leak: on a
Monday it would happily match Tuesday's snapshot.

## Staleness is bounded, not forward-filled forever

An IV reading from 40 days ago is not this week's volatility surface. Beyond
`MAX_STALENESS_DAYS` the feature becomes NULL rather than carrying an old value
indefinitely — a forward fill with no horizon turns a data gap into a confident
flat signal.

## The volatility risk premium

`iv_minus_hv` is the most durable documented effect in options data: implied
volatility exceeds subsequent realised volatility on average, and the gap
varies with risk appetite. It is a *level* feature about the underlying's
option market, not a directional forecast, and is included on that basis.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from src.quant.features.registry import (
    REGISTRY,
    Direction,
    FeatureDefinition,
    FeatureGroup,
)

logger = logging.getLogger("omnisignal.quant.features.options")

#: Beyond this many calendar days an option snapshot no longer describes the
#: current surface. Roughly three trading weeks: long enough to bridge the
#: 2019-2021 weekly cadence, short enough that a gap does not become a signal.
MAX_STALENESS_DAYS = 21

#: An IV outside this band is a data error, not a market state. Real equity
#: implied volatility spans roughly 5% to 400%; beyond that the row is dropped.
MIN_IV = 0.01
MAX_IV = 4.0


def _sanitise_iv(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return values.where((values >= MIN_IV) & (values <= MAX_IV))


def build_option_features(
    volatility_history: Optional[pd.DataFrame] = None,
    chain_daily: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Assemble per (date, symbol) option features from both sources.

    Either source may be absent; the columns it would have supplied are then
    simply not present, and the dataset builder reports reduced coverage rather
    than substituting zeros.
    """
    blocks: list[pd.DataFrame] = []

    if volatility_history is not None and not volatility_history.empty:
        frame = volatility_history.copy()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
        iv = _sanitise_iv(frame.get("iv_current"))
        hv = _sanitise_iv(frame.get("hv_current"))
        high = _sanitise_iv(frame.get("iv_year_high"))
        low = _sanitise_iv(frame.get("iv_year_low"))

        out = pd.DataFrame({"date": frame["date"], "symbol": frame["symbol"]})
        out["opt_iv"] = iv
        # The volatility risk premium, as a ratio rather than a difference so it
        # is comparable across a 15%-vol utility and a 90%-vol biotech.
        out["opt_iv_minus_hv"] = np.where(
            (hv > 0.01) & iv.notna(), iv / hv - 1.0, np.nan
        )
        # IV rank: where today's IV sits in its own trailing-year range. Both
        # bounds are 52-week LOOKBACK columns supplied by the source, so this is
        # point-in-time as published.
        span = high - low
        out["opt_iv_rank"] = np.where(
            (span > 1e-6) & iv.notna(), (iv - low) / span, np.nan
        )
        out["opt_iv_change_21"] = np.where(
            _sanitise_iv(frame.get("iv_month_ago")) > 0.01,
            iv / _sanitise_iv(frame.get("iv_month_ago")) - 1.0,
            np.nan,
        )
        blocks.append(out)

    if chain_daily is not None and not chain_daily.empty:
        frame = chain_daily.copy()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
        atm = _sanitise_iv(frame.get("atm_iv"))
        put25 = _sanitise_iv(frame.get("put_25_iv"))
        call25 = _sanitise_iv(frame.get("call_25_iv"))
        near = _sanitise_iv(frame.get("atm_iv_near"))
        far = _sanitise_iv(frame.get("atm_iv_far"))

        out = pd.DataFrame({"date": frame["date"], "symbol": frame["symbol"]})
        # Skew normalised by ATM so it is a shape of the surface rather than a
        # level: a 5-point skew on 20% IV is not a 5-point skew on 80% IV.
        out["opt_skew_25d"] = np.where(
            (atm > 0.01) & put25.notna() & call25.notna(), (put25 - call25) / atm, np.nan
        )
        out["opt_term_slope"] = np.where(
            (near > 0.01) & far.notna(), far / near - 1.0, np.nan
        )
        out["opt_rel_spread"] = pd.to_numeric(frame.get("rel_spread"), errors="coerce")
        out["opt_expirations"] = pd.to_numeric(frame.get("expirations"), errors="coerce")
        blocks.append(out)

    if not blocks:
        return pd.DataFrame()

    merged = blocks[0]
    for block in blocks[1:]:
        merged = merged.merge(block, on=["date", "symbol"], how="outer")
    return merged.sort_values(["date", "symbol"]).reset_index(drop=True)


def _asof_aligned(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    left_on: str,
    right_on: str,
    by: str,
    columns: Sequence[str],
) -> pd.DataFrame:
    """Backward as-of merge that returns values aligned to `left`'s ORIGINAL index.

    `pandas.merge_asof` requires its left frame sorted by the merge key and
    returns a result carrying a fresh `RangeIndex` — the original index is
    discarded, not preserved. That makes the natural-looking

        merged = pd.merge_asof(left.sort_values(key), right, ...)
        out[name] = merged[name].sort_index().to_numpy()

    silently wrong: `sort_index()` sorts a RangeIndex that is already ordered,
    so the values are written back in DATE-SORTED order into a frame that is in
    SYMBOL-MAJOR order. Every value lands on the wrong row.

    This is not merely noise. The panel arrives symbol-major, so sorting by date
    permutes it globally, and a 2026 observation can be written onto a 2014 row —
    future information travelling backwards. It was found by
    `tests/quant/test_leakage.py::test_asof_joins_align_to_the_original_index`
    and by building the dataset with and without the holdout period and finding
    24 features whose NULL patterns differed.

    The fix carries the original index through the merge as an explicit column
    and reindexes on the way out, so alignment is by label rather than by
    position.
    """
    marker = "__origin_index__"
    staged = left.copy()
    staged[marker] = np.arange(len(staged))
    staged = staged.sort_values(left_on, kind="mergesort")

    merged = pd.merge_asof(
        staged,
        right,
        left_on=left_on,
        right_on=right_on,
        left_by=by,
        right_by=by,
        direction="backward",
    )
    # Restore the caller's row order by the marker, not by a reset RangeIndex.
    merged = merged.sort_values(marker, kind="mergesort").reset_index(drop=True)
    if len(merged) != len(left):
        raise ValueError(
            f"as-of merge changed the row count ({len(left)} -> {len(merged)}); "
            "a duplicate key on the right side would silently fan out rows"
        )
    return merged


def _match_key_dtype(left: pd.DataFrame, right: pd.DataFrame, column: str) -> None:
    """Force both merge keys to plain object dtype, in place.

    `RawStore` normalisation types symbols as pandas `string[python]` while a
    frame assembled in memory carries `object`. `merge_asof` refuses the pair
    with "incompatible merge keys" rather than coercing — which is the right
    behaviour, since a silent coercion could match different values. Both sides
    are pinned here so the comparison is defined.
    """
    for frame in (left, right):
        if column in frame.columns:
            frame[column] = frame[column].astype(str)


def attach_option_features(
    panel: pd.DataFrame,
    option_features: pd.DataFrame,
    *,
    date_column: str = "date",
    symbol_column: str = "symbol",
    max_staleness_days: int = MAX_STALENESS_DAYS,
) -> pd.DataFrame:
    """Attach the latest option snapshot at or before each panel row's date.

    Backward `merge_asof` per symbol. Anything older than `max_staleness_days`
    becomes NULL rather than being carried forward indefinitely.
    """
    feature_names = [c for c in option_features.columns if c.startswith("opt_")] if not option_features.empty else []
    out = panel.copy()
    for name in feature_names or OPTION_FEATURE_NAMES:
        out[name] = np.nan
    if option_features.empty:
        logger.warning("options: no source — option features remain NULL, not zero")
        return out

    # Drop the pre-initialised NULL columns before merging: leaving them would
    # collide with the incoming ones and pandas would silently suffix the
    # right-hand side to `opt_iv_y`, so the values written back would be the
    # NULLs we started with.
    left = out.drop(columns=[c for c in feature_names if c in out.columns], errors="ignore").copy()
    left["_date"] = pd.to_datetime(left[date_column])

    right = option_features.copy()
    right["_opt_date"] = pd.to_datetime(right["date"])
    right = right.sort_values("_opt_date", kind="mergesort")
    _match_key_dtype(left, right, symbol_column)
    _match_key_dtype(left, right, "symbol")
    if symbol_column != "symbol":
        left = left.rename(columns={symbol_column: "symbol"})

    merged = _asof_aligned(
        left,
        right[["symbol", "_opt_date", *feature_names]],
        left_on="_date", right_on="_opt_date", by="symbol", columns=feature_names,
    )
    staleness = (merged["_date"] - merged["_opt_date"]).dt.days
    fresh = staleness <= max_staleness_days

    for name in feature_names:
        out[name] = merged[name].where(fresh).to_numpy()
    coverage = float(np.mean([out[n].notna().mean() for n in feature_names])) if feature_names else 0.0
    logger.info(
        "options: attached %d feature(s), mean coverage %.3f (staleness cap %dd)",
        len(feature_names), coverage, max_staleness_days,
    )
    return out


OPTION_FEATURE_NAMES: tuple[str, ...] = (
    "opt_iv", "opt_iv_minus_hv", "opt_iv_rank", "opt_iv_change_21",
    "opt_skew_25d", "opt_term_slope", "opt_rel_spread", "opt_expirations",
)


def _register() -> None:
    definitions = [
        FeatureDefinition(
            name="opt_iv",
            group=FeatureGroup.OPTIONS,
            description="Implied volatility of the underlying, latest snapshot at or before the date.",
            rationale="The option market's forward volatility expectation — information the price series does not contain.",
            formula="iv_current from volatility_history",
            lookback_sessions=1,
            required_columns=("iv_current",),
            direction=Direction.NEGATIVE,
            availability_lag_sessions=0,
            notes=("Vendor measurement under an unpublished model, not a reconstructible quantity.",),
        ),
        FeatureDefinition(
            name="opt_iv_minus_hv",
            group=FeatureGroup.OPTIONS,
            description="Implied over realised volatility, as a ratio minus one.",
            rationale=(
                "The volatility risk premium — the most durable documented effect in "
                "options data. A ratio, not a difference, so it compares across names "
                "with very different absolute volatility."
            ),
            formula="iv_current / hv_current - 1",
            lookback_sessions=1,
            required_columns=("iv_current", "hv_current"),
            direction=Direction.TWO_SIDED,
            availability_lag_sessions=0,
        ),
        FeatureDefinition(
            name="opt_iv_rank",
            group=FeatureGroup.OPTIONS,
            description="Position of current IV within its trailing 52-week range.",
            rationale="A percentile rather than a level, so 'expensive volatility' means the same thing across names and eras.",
            formula="(iv_current - iv_year_low) / (iv_year_high - iv_year_low)",
            lookback_sessions=1,
            required_columns=("iv_current", "iv_year_high", "iv_year_low"),
            direction=Direction.TWO_SIDED,
            availability_lag_sessions=0,
            notes=("Both bounds are 52-week LOOKBACK columns supplied by the source — point-in-time as published.",),
        ),
        FeatureDefinition(
            name="opt_iv_change_21",
            group=FeatureGroup.OPTIONS,
            description="Change in implied volatility over roughly one month.",
            rationale="Direction of the volatility repricing, not just its level.",
            formula="iv_current / iv_month_ago - 1",
            lookback_sessions=1,
            required_columns=("iv_current", "iv_month_ago"),
            direction=Direction.TWO_SIDED,
            availability_lag_sessions=0,
        ),
        FeatureDefinition(
            name="opt_skew_25d",
            group=FeatureGroup.OPTIONS,
            description="25-delta put IV minus 25-delta call IV, normalised by ATM IV.",
            rationale=(
                "The price of downside protection relative to upside. Steep skew is "
                "the option market paying up for crash insurance, which the underlying's "
                "own return series cannot express."
            ),
            formula="(put_25_iv - call_25_iv) / atm_iv",
            lookback_sessions=1,
            required_columns=("put_25_iv", "call_25_iv", "atm_iv"),
            direction=Direction.TWO_SIDED,
            availability_lag_sessions=0,
            notes=("Delta buckets are wide (0.20-0.30) because listed strikes are discrete.",),
        ),
        FeatureDefinition(
            name="opt_term_slope",
            group=FeatureGroup.OPTIONS,
            description="Far-expiry ATM IV over near-expiry ATM IV, minus one.",
            rationale=(
                "Term structure. Inversion — near above far — is the option market "
                "pricing an imminent event, and it is a distinct state from a high level."
            ),
            formula="atm_iv(>45d) / atm_iv(<=45d) - 1",
            lookback_sessions=1,
            required_columns=("atm_iv_near", "atm_iv_far"),
            direction=Direction.TWO_SIDED,
            availability_lag_sessions=0,
        ),
        FeatureDefinition(
            name="opt_rel_spread",
            group=FeatureGroup.OPTIONS,
            description="Mean relative bid-ask spread across the chain.",
            rationale="Option-market liquidity, which is a different measurement from equity dollar volume.",
            formula="mean (ask - bid) / mid over quotes with both sides positive",
            lookback_sessions=1,
            required_columns=("rel_spread",),
            direction=Direction.NEGATIVE,
            availability_lag_sessions=0,
        ),
        FeatureDefinition(
            name="opt_expirations",
            group=FeatureGroup.OPTIONS,
            description="Distinct expirations listed on the snapshot date.",
            rationale="Chain breadth — a proxy for institutional interest and option-market depth.",
            formula="count(distinct expiration)",
            lookback_sessions=1,
            required_columns=("expirations",),
            direction=Direction.DESCRIPTIVE,
            availability_lag_sessions=0,
        ),
    ]
    for definition in definitions:
        REGISTRY.register(definition)


_register()
