"""
Walk-forward validation — the only split that is valid for this data.

## Why not a random split

A random train/test split assumes the rows are exchangeable. Financial panel
rows are not, in two independent ways, and each one alone invalidates it:

**Time.** Training on 2022 and testing on 2018 asks whether a model fitted with
knowledge of the future predicts the past. It answers a question nobody has.

**Overlap.** With a 21-session label sampled every 5 sessions, consecutive
observations of the same name share 16 of their 21 days. A random split puts
rows that share 76% of their outcome on both sides of the boundary, so the
"test" set is substantially the training set. Measured effect: this is the
single largest source of illusory skill in an equity ML study, and it produces
results that look excellent and reproduce nowhere.

## Purge and embargo, which are two different things

    train ────────────┤ purge ├─ embargo ─┤ validation ──────

**Purge** removes `horizon` sessions after `train_end`. A label observed on the
last training day is realised `horizon` sessions later, so without it the
training set contains the validation period's outcomes.

**Embargo** removes a further margin. Purging handles the *label's* reach;
embargo handles *serial correlation* in features and returns, which persists
past the horizon. They are separate parameters because they answer separate
questions, and collapsing them into one number loses the ability to say which
one a result was sensitive to.

Both follow Lopez de Prado's treatment in *Advances in Financial Machine
Learning* (2018), ch. 7.

## The final holdout is not a fold

`WalkForwardPlan.holdout` is carved off before any fold is generated and is
returned by no iterator. Nothing in this package evaluates against it. It
exists so that after every model has been selected — and selection has
inevitably consumed the validation folds — there is one period no decision has
touched. Once it is used it is spent, and `docs/modeling-methodology.md`
records when that happened.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date as Date
from typing import Any, Iterator, Optional, Sequence

import numpy as np
import pandas as pd

from src.quant.pit.calendar import TradingCalendar

from src.quant.study.firewall import FIREWALL

logger = logging.getLogger("omnisignal.quant.validation.walkforward")

#: Additional sessions removed beyond the label horizon. One trading week:
#: enough to break the strongest short-horizon autocorrelation, small enough
#: that a 15-year sample does not lose a meaningful fraction of its folds.
DEFAULT_EMBARGO_SESSIONS = 5

#: A fold with fewer training rows than this cannot support a 30-feature model
#: — the coefficients would be fitted to noise and their instability across
#: folds would be read as market regime change.
MIN_TRAIN_ROWS = 500


@dataclass(frozen=True)
class Fold:
    """One train/validate pair with the gap between them made explicit."""

    index: int
    train_start: Date
    train_end: Date
    purge_end: Date
    validation_start: Date
    validation_end: Date
    label_horizon_sessions: int
    embargo_sessions: int
    gap_sessions: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "purge_end": self.purge_end.isoformat(),
            "validation_start": self.validation_start.isoformat(),
            "validation_end": self.validation_end.isoformat(),
            "label_horizon_sessions": self.label_horizon_sessions,
            "embargo_sessions": self.embargo_sessions,
            "gap_sessions": self.gap_sessions,
        }

    def split(
        self, frame: pd.DataFrame, *, date_column: str = "date"
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Rows for this fold. The gap belongs to neither side."""
        dates = frame[date_column]
        train = frame[(dates >= self.train_start) & (dates <= self.train_end)]
        validation = frame[
            (dates >= self.validation_start) & (dates <= self.validation_end)
        ]
        return train.reset_index(drop=True), validation.reset_index(drop=True)


@dataclass
class WalkForwardPlan:
    """Every fold, plus a holdout that no fold touches."""

    folds: list[Fold]
    holdout_start: Optional[Date]
    holdout_end: Optional[Date]
    scheme: str
    label_horizon_sessions: int
    embargo_sessions: int
    train_sessions: Optional[int]
    validation_sessions: int
    notes: list[str] = field(default_factory=list)

    def __iter__(self) -> Iterator[Fold]:
        return iter(self.folds)

    def __len__(self) -> int:
        return len(self.folds)

    def holdout(self, frame: pd.DataFrame, *, date_column: str = "date") -> pd.DataFrame:
        """The untouched period.

        Deliberately requires an explicit call. Nothing in the walk-forward
        driver reaches it, so using it is a decision someone made and can be
        found in the transcript.
        """
        if self.holdout_start is None or self.holdout_end is None:
            return frame.iloc[0:0]
        dates = frame[date_column]
        return frame[
            (dates >= self.holdout_start) & (dates <= self.holdout_end)
        ].reset_index(drop=True)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scheme": self.scheme,
            "folds": [fold.as_dict() for fold in self.folds],
            "fold_count": len(self.folds),
            "holdout_start": self.holdout_start.isoformat() if self.holdout_start else None,
            "holdout_end": self.holdout_end.isoformat() if self.holdout_end else None,
            "label_horizon_sessions": self.label_horizon_sessions,
            "embargo_sessions": self.embargo_sessions,
            "train_sessions": self.train_sessions,
            "validation_sessions": self.validation_sessions,
            "notes": list(self.notes),
        }


def build_plan(
    calendar: TradingCalendar,
    *,
    start: Date,
    end: Date,
    label_horizon_sessions: int,
    validation_sessions: int = 252,
    min_train_sessions: int = 756,
    train_sessions: Optional[int] = None,
    embargo_sessions: int = DEFAULT_EMBARGO_SESSIONS,
    holdout_sessions: int = 252,
    scheme: str = "expanding",
) -> WalkForwardPlan:
    """Generate folds over an observed trading calendar.

    `scheme="expanding"` grows the training window each fold, which is what a
    live system does — it retrains on everything it has. `scheme="rolling"`
    keeps it fixed, which tests whether older data still helps; when rolling
    beats expanding, the honest reading is that the relationship changed, not
    that the model improved.

    Everything is counted in **sessions from the observed calendar**, never in
    calendar days. A 21-session horizon spanning Christmas is still 21
    sessions, and converting to ~30 days would silently vary the purge width by
    season.
    """
    if scheme not in {"expanding", "rolling"}:
        raise ValueError(f"unknown scheme {scheme!r}")
    if scheme == "rolling" and train_sessions is None:
        raise ValueError("a rolling scheme needs train_sessions")

    sessions = list(calendar.sessions_between(start, end))
    if len(sessions) < min_train_sessions + validation_sessions:
        raise ValueError(
            f"{len(sessions)} sessions between {start} and {end} cannot support "
            f"{min_train_sessions} training + {validation_sessions} validation sessions"
        )

    notes: list[str] = []
    holdout_start: Optional[Date] = None
    holdout_end: Optional[Date] = None
    if holdout_sessions > 0 and len(sessions) > holdout_sessions:
        holdout = sessions[-holdout_sessions:]
        holdout_start, holdout_end = holdout[0], holdout[-1]
        sessions = sessions[:-holdout_sessions]
        notes.append(
            f"final {holdout_sessions} sessions ({holdout_start} to {holdout_end}) "
            "reserved as an untouched holdout; no fold reaches them"
        )
        # Declaring the window here is what makes the reservation enforceable
        # rather than advisory: from this point every guarded stage refuses
        # rows inside it. See src/quant/study/firewall.py.
        FIREWALL.arm_window(holdout_start, holdout_end)

    gap = int(label_horizon_sessions) + int(embargo_sessions)
    folds: list[Fold] = []
    cursor = min_train_sessions
    index = 0

    while True:
        train_end_position = cursor - 1
        validation_start_position = train_end_position + gap + 1
        validation_end_position = validation_start_position + validation_sessions - 1
        if validation_end_position >= len(sessions):
            break

        train_start_position = (
            0 if scheme == "expanding" else max(0, train_end_position - train_sessions + 1)
        )
        folds.append(
            Fold(
                index=index,
                train_start=sessions[train_start_position],
                train_end=sessions[train_end_position],
                purge_end=sessions[min(train_end_position + gap, len(sessions) - 1)],
                validation_start=sessions[validation_start_position],
                validation_end=sessions[validation_end_position],
                label_horizon_sessions=label_horizon_sessions,
                embargo_sessions=embargo_sessions,
                gap_sessions=gap,
            )
        )
        index += 1
        cursor += validation_sessions

    if not folds:
        raise ValueError(
            f"no folds fit: {len(sessions)} sessions, {min_train_sessions} minimum "
            f"training, {gap} session gap, {validation_sessions} validation"
        )

    notes.append(
        f"gap of {gap} sessions between every train_end and validation_start "
        f"(purge {label_horizon_sessions} for the label horizon + embargo "
        f"{embargo_sessions} for serial correlation)"
    )
    logger.info(
        "walk-forward: %d %s folds, %d-session validation, %d-session gap",
        len(folds), scheme, validation_sessions, gap,
    )
    return WalkForwardPlan(
        folds=folds,
        holdout_start=holdout_start,
        holdout_end=holdout_end,
        scheme=scheme,
        label_horizon_sessions=label_horizon_sessions,
        embargo_sessions=embargo_sessions,
        train_sessions=train_sessions,
        validation_sessions=validation_sessions,
        notes=notes,
    )


def verify_no_overlap(
    plan: WalkForwardPlan, frame: pd.DataFrame, *, date_column: str = "date"
) -> dict[str, Any]:
    """Assert every fold's train and validation row sets are disjoint.

    Belt and braces over the arithmetic in `build_plan`: an off-by-one in the
    gap calculation is invisible in the fold table and shows up only as
    inexplicably good validation scores.
    """
    problems: list[dict[str, Any]] = []
    for fold in plan.folds:
        train, validation = fold.split(frame, date_column=date_column)
        if train.empty or validation.empty:
            problems.append({"fold": fold.index, "issue": "empty side"})
            continue
        if train[date_column].max() >= validation[date_column].min():
            problems.append(
                {
                    "fold": fold.index,
                    "issue": "train and validation overlap",
                    "train_max": str(train[date_column].max()),
                    "validation_min": str(validation[date_column].min()),
                }
            )
        if len(train) < MIN_TRAIN_ROWS:
            problems.append(
                {"fold": fold.index, "issue": "thin training fold", "rows": len(train)}
            )
    return {"ok": not problems, "problems": problems, "folds": len(plan.folds)}


def fold_row_counts(
    plan: WalkForwardPlan, frame: pd.DataFrame, *, date_column: str = "date"
) -> list[dict[str, Any]]:
    """Row counts per fold — reported so a thin fold is visible, not inferred."""
    out: list[dict[str, Any]] = []
    for fold in plan.folds:
        train, validation = fold.split(frame, date_column=date_column)
        out.append(
            {
                **fold.as_dict(),
                "train_rows": len(train),
                "validation_rows": len(validation),
                "train_symbols": int(train["symbol"].nunique()) if "symbol" in train else None,
                "validation_symbols": (
                    int(validation["symbol"].nunique()) if "symbol" in validation else None
                ),
            }
        )
    return out
