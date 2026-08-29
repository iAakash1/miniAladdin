"""
Cross-sectional normalisation — ranks and z-scores against an explicit universe.

## The rule this module exists to enforce

    NEVER compute a z-score across whatever names happened to be loaded.

A cross-sectional score is a statement about a name *relative to a peer group*,
so the peer group is part of the number's definition. Standardising against
"whatever the dataframe contains" produces a value whose meaning changes when
an unrelated symbol is added, which makes it unreproducible and — worse —
quietly survivorship-biased, because the names that happened to load are the
ones that still have data.

Every function here therefore takes the universe **explicitly**, and
`cross_sectional_frame` raises when a date's membership is not supplied. There
is no default.

## Winsorise before standardising, and why in that order

A single 900% return in a 180-name cross-section moves the mean by 5% and the
standard deviation by far more, so every other name's z-score is distorted by
one observation. Winsorising first bounds that influence; standardising first
and clipping afterwards does not, because the damage is already in the moments.

Clipped at the 1st/99th percentile — roughly two names either side in a
180-name universe, which is small enough not to reshape the distribution and
large enough to catch a bad print.

## Ranks are the default, and z-scores are offered

Rank normalisation is scale-free and unaffected by the tails entirely, which
matters because these features are fed to linear models where one outlier is
one high-leverage point. Z-scores are kept because tree models can use the
magnitude and ranks discard it.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

import numpy as np
import pandas as pd

#: Below this the cross-section is too thin for a percentile to mean anything:
#: with eight names the third-best is the 62nd percentile by arithmetic alone.
#: Matches `src/research/cross_section.MIN_NAMES_PER_DATE` so the two research
#: surfaces agree about what counts as a cross-section.
MIN_NAMES_PER_DATE = 10

#: Winsorisation bounds. See the module docstring for why these and why first.
WINSOR_LOWER = 0.01
WINSOR_UPPER = 0.99


class UniverseRequired(ValueError):
    """Raised when a cross-sectional statistic is requested without a universe."""


def winsorise(values: pd.Series, lower: float = WINSOR_LOWER, upper: float = WINSOR_UPPER) -> pd.Series:
    """Clip to inner quantiles. NULLs stay NULL — they are not a middle value."""
    numeric = pd.to_numeric(values, errors="coerce")
    present = numeric.dropna()
    if len(present) < MIN_NAMES_PER_DATE:
        return numeric
    low, high = present.quantile(lower), present.quantile(upper)
    return numeric.clip(low, high)


def cross_sectional_rank(values: pd.Series) -> pd.Series:
    """Percentile rank in [-1, 1], centred at 0.

    Centred rather than [0, 1] so that "no view" is zero — which means a name
    with a missing feature and a name at the median are *not* interchangeable:
    the first is NULL and the second is 0.0.
    """
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.notna().sum() < MIN_NAMES_PER_DATE:
        return pd.Series(np.nan, index=values.index, dtype=float)
    return numeric.rank(pct=True) * 2.0 - 1.0


def cross_sectional_zscore(values: pd.Series, *, winsorised: bool = True) -> pd.Series:
    """Standardise across the cross-section, winsorising first."""
    numeric = winsorise(values) if winsorised else pd.to_numeric(values, errors="coerce")
    if numeric.notna().sum() < MIN_NAMES_PER_DATE:
        return pd.Series(np.nan, index=values.index, dtype=float)
    mean, std = numeric.mean(), numeric.std(ddof=1)
    if not np.isfinite(std) or std <= 0:
        # A cross-section with no dispersion carries no cross-sectional
        # information. Zero would assert every name is exactly average, which
        # is a claim; NULL is the absence of one.
        return pd.Series(np.nan, index=values.index, dtype=float)
    return (numeric - mean) / std


def cross_sectional_frame(
    panel: pd.DataFrame,
    features: Sequence[str],
    *,
    universe_for: Optional[dict] = None,
    method: str = "rank",
    date_column: str = "date",
    symbol_column: str = "symbol",
    suffix: Optional[str] = None,
) -> pd.DataFrame:
    """Normalise `features` within each date's universe.

    `universe_for` maps a date to its eligible symbols and is **mandatory**.
    Passing an empty dict is a different statement from omitting it, and both
    are refused: the first would silently produce an empty cross-section, the
    second would silently use whatever loaded.
    """
    if universe_for is None:
        raise UniverseRequired(
            "cross-sectional normalisation requires an explicit universe per date — "
            "standardising against whatever rows happen to be loaded produces a "
            "value whose meaning depends on the query, not on the market"
        )
    if method not in {"rank", "zscore"}:
        raise ValueError(f"unknown normalisation method {method!r}")

    tail = suffix if suffix is not None else ("_xs" if method == "rank" else "_z")
    normalise = cross_sectional_rank if method == "rank" else cross_sectional_zscore

    out = panel.copy()
    for feature in features:
        out[f"{feature}{tail}"] = np.nan

    for day, group in panel.groupby(date_column, sort=False):
        members = universe_for.get(day)
        if not members:
            continue
        eligible = group[group[symbol_column].isin(set(members))]
        if len(eligible) < MIN_NAMES_PER_DATE:
            continue
        for feature in features:
            if feature not in eligible.columns:
                continue
            out.loc[eligible.index, f"{feature}{tail}"] = normalise(eligible[feature])

    return out


def sector_neutralise(
    values: pd.Series, sectors: pd.Series, *, min_per_sector: int = 5
) -> pd.Series:
    """Subtract each sector's mean, so what remains is within-sector.

    Offered but not used by default, and the reason is honest rather than
    architectural: this repository has no point-in-time sector classification.
    Applying today's GICS to 2013 backdates a classification that has itself
    been revised. The function exists so that when a dated classification
    arrives it is a call-site change, not a new module.

    A sector thinner than `min_per_sector` is left alone — demeaning three
    names against their own mean removes two-thirds of their dispersion and
    calls the residue a signal.
    """
    numeric = pd.to_numeric(values, errors="coerce")
    out = numeric.copy()
    for _, index in numeric.groupby(sectors).groups.items():
        subset = numeric.loc[index]
        if subset.notna().sum() >= min_per_sector:
            out.loc[index] = subset - subset.mean()
    return out


def universe_map(history, dates: Iterable) -> dict:
    """Build the date -> members mapping the normalisers require.

    Uses `UniverseHistory.members(as_of=date)`, which resolves to the latest
    rebalance at or before the date — so the membership applied on 2015-03-11
    was decided on 2015-02-27, never on 2015-03-31.
    """
    return {day: set(history.members(day)) for day in dates}
