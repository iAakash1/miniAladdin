"""
Labels — what the model is asked to predict, defined before anything is trained.

## Every label is a forward statement, and that is the danger

A feature that looks forward is a bug. A label that looks forward is the
*definition*. The two therefore have to be constructed by different code with
different rules, and the boundary between them has to be enforced rather than
remembered — which is why labels live in their own package and why
`src/quant/pit/dataset.py` refuses to place a label column into the feature
matrix.

The consequence that costs sample: a label with horizon `h` is **NULL for the
last `h` sessions** of every series. Filling it, or shortening the horizon at
the end, silently changes what the model was trained on exactly where the
newest data is — which is where a walk-forward's final window lives.

## Why several horizons and several formulations

The brief was explicit: do not arbitrarily pick one horizon, and do not force
classification if regression does better. So the library defines 1/5/21/63-day
returns, forward realised volatility, excursion labels and both absolute and
cross-sectional-rank targets, and `docs/modeling-methodology.md` records which
proved predictable rather than assuming in advance.

The **rank** label deserves its own note. Predicting a name's absolute return
means predicting the market's return plus the name's relative move, and the
first term dominates the variance while being nearly unpredictable at these
horizons. Predicting the cross-sectional *rank* removes it. A model can be
useless at the first and useful at the second, which is why both are built.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd

TRADING_DAYS = 252


class LabelKind(str, Enum):
    REGRESSION = "regression"
    CLASSIFICATION = "classification"
    RANKING = "ranking"


@dataclass(frozen=True)
class LabelDefinition:
    """One target: what it measures, over what horizon, and what it costs."""

    name: str
    kind: LabelKind
    horizon_sessions: int
    description: str
    rationale: str
    formula: str
    cross_sectional: bool = False
    version: str = "1.0"
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "horizon_sessions": self.horizon_sessions,
            "description": self.description,
            "rationale": self.rationale,
            "formula": self.formula,
            "cross_sectional": self.cross_sectional,
            "version": self.version,
            "notes": list(self.notes),
        }


def forward_return(returns: pd.Series, horizon: int) -> pd.Series:
    """Compounded return over the next `horizon` sessions, NULL where unobservable.

    The shift is `-horizon` — the *only* place in this codebase where a negative
    shift is correct, because this is the target. `min_periods=horizon` on the
    reversed window means the final `horizon` rows are NULL rather than a
    shorter-horizon return wearing this column's name.
    """
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    numeric = pd.to_numeric(returns, errors="coerce")
    log_returns = np.log1p(numeric)
    forward_sum = (
        log_returns.iloc[::-1].rolling(horizon, min_periods=horizon).sum().iloc[::-1]
    )
    return np.expm1(forward_sum.shift(-1))


def forward_volatility(returns: pd.Series, horizon: int) -> pd.Series:
    """Annualised realised volatility over the next `horizon` sessions.

    Volatility is materially more predictable than return — it clusters, and
    that is one of the oldest documented facts about financial series. Including
    it makes the comparison honest: a model that predicts returns poorly and
    volatility well has found something real, and reporting only the return
    result would hide it.
    """
    if horizon < 2:
        raise ValueError("volatility horizon must be >= 2")
    numeric = pd.to_numeric(returns, errors="coerce")
    reversed_std = (
        numeric.iloc[::-1].rolling(horizon, min_periods=horizon).std(ddof=1).iloc[::-1]
    )
    return reversed_std.shift(-1) * np.sqrt(TRADING_DAYS)


def forward_excursion(
    returns: pd.Series, horizon: int, *, favourable: bool
) -> pd.Series:
    """Best (or worst) cumulative move reached inside the next `horizon` sessions.

    Maximum favourable / adverse excursion. A path that ends flat after a 20%
    round trip is not the same experience as one that never moved, and a
    terminal return cannot tell them apart. This is the label a stop-loss or a
    risk limit actually responds to.

    Defined as the raw minimum (or maximum) of the cumulative path, **not**
    `min(0, worst)`. A name that rose every session has a *positive* adverse
    excursion, and that is the informative statement: it never traded below
    entry. Flooring it at zero would collapse "never went down" and "went down
    and recovered" into the same value. The invariant that holds by
    construction, and is asserted in the tests, is `MAE <= terminal <= MFE`.
    """
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    numeric = pd.to_numeric(returns, errors="coerce").to_numpy(dtype=float)
    n = len(numeric)
    out = np.full(n, np.nan)
    log_returns = np.log1p(numeric)

    for position in range(n - horizon):
        window = log_returns[position + 1 : position + 1 + horizon]
        if np.isnan(window).any():
            continue
        path = np.cumsum(window)
        out[position] = np.expm1(path.max() if favourable else path.min())
    return pd.Series(out, index=pd.RangeIndex(n))


def direction_label(
    forward: pd.Series, *, threshold: float = 0.0, neutral_band: Optional[float] = None
) -> pd.Series:
    """Sign of a forward return, optionally with an explicit neutral band.

    With `neutral_band`, returns -1/0/+1 and the middle class is *real* rather
    than a rounding artefact: a name expected to move 0.1% is not a directional
    view, and forcing it into up-or-down manufactures a decision the data does
    not support. Without it, returns 0/1 and ties resolve down (a flat outcome
    is not a win).
    """
    numeric = pd.to_numeric(forward, errors="coerce")
    if neutral_band is None:
        return (numeric > threshold).astype("float64").where(numeric.notna())
    labels = pd.Series(np.nan, index=numeric.index, dtype=float)
    labels[numeric > threshold + neutral_band] = 1.0
    labels[numeric < threshold - neutral_band] = -1.0
    labels[(numeric >= threshold - neutral_band) & (numeric <= threshold + neutral_band)] = 0.0
    return labels


def cross_sectional_rank_label(
    frame: pd.DataFrame,
    forward_column: str,
    *,
    universe_for: dict,
    date_column: str = "date",
    symbol_column: str = "symbol",
    min_names: int = 10,
) -> pd.Series:
    """Rank a forward return within its date's universe, mapped to [-1, 1].

    The universe is mandatory for the same reason it is mandatory on the feature
    side: a rank is a statement about a peer group. Ranking against whatever
    loaded would make the *target itself* depend on the query — and unlike a
    contaminated feature, a contaminated target cannot be detected by any
    downstream diagnostic.
    """
    out = pd.Series(np.nan, index=frame.index, dtype=float)
    for day, group in frame.groupby(date_column, sort=False):
        members = universe_for.get(day)
        if not members:
            continue
        eligible = group[group[symbol_column].isin(set(members))]
        values = pd.to_numeric(eligible[forward_column], errors="coerce")
        if values.notna().sum() < min_names:
            continue
        out.loc[eligible.index] = values.rank(pct=True) * 2.0 - 1.0
    return out


LABEL_DEFINITIONS: tuple[LabelDefinition, ...] = (
    LabelDefinition(
        name="fwd_ret_1",
        kind=LabelKind.REGRESSION,
        horizon_sessions=1,
        description="Next session's total return.",
        rationale=(
            "The hardest horizon and the honest control. Daily returns are close "
            "to unpredictable; a model that appears to predict them is far more "
            "likely to be leaking than to have found something."
        ),
        formula="prod(1 + r) over (T, T+1] - 1",
    ),
    LabelDefinition(
        name="fwd_ret_5",
        kind=LabelKind.REGRESSION,
        horizon_sessions=5,
        description="Total return over the next 5 sessions.",
        rationale="One week — short enough that reversal effects are still live.",
        formula="prod(1 + r) over (T, T+5] - 1",
    ),
    LabelDefinition(
        name="fwd_ret_21",
        kind=LabelKind.REGRESSION,
        horizon_sessions=21,
        description="Total return over the next 21 sessions.",
        rationale=(
            "One trading month; the horizon the existing scoring engine is "
            "designed around, which makes results directly comparable to it."
        ),
        formula="prod(1 + r) over (T, T+21] - 1",
        notes=("Overlaps at any sampling stride below 21 — the t-statistic must be Newey-West corrected.",),
    ),
    LabelDefinition(
        name="fwd_ret_63",
        kind=LabelKind.REGRESSION,
        horizon_sessions=63,
        description="Total return over the next 63 sessions.",
        rationale="One quarter — the horizon at which fundamental signals are usually claimed to act.",
        formula="prod(1 + r) over (T, T+63] - 1",
    ),
    LabelDefinition(
        name="fwd_vol_21",
        kind=LabelKind.REGRESSION,
        horizon_sessions=21,
        description="Annualised realised volatility over the next 21 sessions.",
        rationale=(
            "Volatility clusters, so this is the label most likely to carry real "
            "signal. Included so a null result on returns is reported alongside a "
            "positive one on risk rather than instead of it."
        ),
        formula="std(r over (T, T+21]) * sqrt(252)",
    ),
    LabelDefinition(
        name="fwd_mae_21",
        kind=LabelKind.REGRESSION,
        horizon_sessions=21,
        description="Maximum adverse excursion over the next 21 sessions.",
        rationale="What a stop-loss or risk limit responds to; invisible in a terminal return.",
        formula="min over k<=21 of (prod(1 + r) over (T, T+k] - 1)",
    ),
    LabelDefinition(
        name="fwd_mfe_21",
        kind=LabelKind.REGRESSION,
        horizon_sessions=21,
        description="Maximum favourable excursion over the next 21 sessions.",
        rationale="Paired with MAE, describes the path rather than only its end.",
        formula="max over k<=21 of (prod(1 + r) over (T, T+k] - 1)",
    ),
    LabelDefinition(
        name="fwd_dir_21",
        kind=LabelKind.CLASSIFICATION,
        horizon_sessions=21,
        description="Whether the 21-session forward return is positive.",
        rationale="Directional accuracy is interpretable, and calibration is measurable on it.",
        formula="1[fwd_ret_21 > 0]",
        notes=("Base rate is well above 50% in a rising sample — accuracy must be read against it, never against a coin.",),
    ),
    LabelDefinition(
        name="fwd_rank_21",
        kind=LabelKind.RANKING,
        horizon_sessions=21,
        description="Cross-sectional rank of the 21-session forward return, in [-1, 1].",
        rationale=(
            "Removes the market component, which dominates absolute-return "
            "variance and is close to unpredictable at this horizon. This is the "
            "target a long/short book actually needs."
        ),
        formula="2 * percentile_rank(fwd_ret_21 within the date's universe) - 1",
        cross_sectional=True,
    ),
)

_BY_NAME = {definition.name: definition for definition in LABEL_DEFINITIONS}


def get(name: str) -> LabelDefinition:
    if name not in _BY_NAME:
        raise KeyError(f"unknown label {name!r}; known: {sorted(_BY_NAME)}")
    return _BY_NAME[name]


def names() -> list[str]:
    return sorted(_BY_NAME)


def catalog() -> list[dict[str, Any]]:
    return [definition.as_dict() for definition in LABEL_DEFINITIONS]


def compute_symbol_labels(
    frame: pd.DataFrame, *, labels: Optional[Sequence[str]] = None
) -> pd.DataFrame:
    """Every per-symbol label for one symbol's history, sorted ascending by date.

    The ordering requirement is enforced, not documented. Forward labels are
    computed over row order, so an unsorted frame yields values that look
    plausible and are wrong.
    """
    from src.quant.pit.calendar import require_chronological

    require_chronological(frame, context="compute_symbol_labels")

    chosen = list(labels) if labels else [
        d.name for d in LABEL_DEFINITIONS if not d.cross_sectional
    ]
    returns = pd.to_numeric(frame["total_return"], errors="coerce").reset_index(drop=True)
    # A positional write needs a positional index on both sides. `frame.index`
    # may be anything the caller was carrying; the labels are produced against a
    # fresh RangeIndex, so the container is given one too.
    out = pd.DataFrame(index=pd.RangeIndex(len(frame)))

    for name in chosen:
        definition = get(name)
        horizon = definition.horizon_sessions
        if name.startswith("fwd_ret_"):
            values = forward_return(returns, horizon)
        elif name == "fwd_vol_21":
            values = forward_volatility(returns, horizon)
        elif name == "fwd_mae_21":
            values = forward_excursion(returns, horizon, favourable=False)
        elif name == "fwd_mfe_21":
            values = forward_excursion(returns, horizon, favourable=True)
        elif name == "fwd_dir_21":
            values = direction_label(forward_return(returns, horizon))
        else:
            raise KeyError(f"no per-symbol computer for label {name!r}")
        out[name] = values.to_numpy()

    return out
