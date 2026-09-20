"""Purged inner temporal splits contained wholly inside an outer train set."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import pandas as pd


@dataclass(frozen=True)
class InnerSplit:
    index: int
    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp

    def split(self, frame: pd.DataFrame, *, date_column: str = "date") -> tuple[pd.DataFrame, pd.DataFrame]:
        dates = pd.to_datetime(frame[date_column])
        train = frame[dates <= self.train_end]
        validation = frame[(dates >= self.validation_start) & (dates <= self.validation_end)]
        return train.reset_index(drop=True), validation.reset_index(drop=True)


@dataclass(frozen=True)
class InnerTemporalPlan:
    splits: tuple[InnerSplit, ...]
    gap_observation_dates: int
    scheme: str = "expanding-3-split-purged"

    def __iter__(self) -> Iterator[InnerSplit]:
        return iter(self.splits)


def build_inner_plan(
    outer_train: pd.DataFrame,
    *,
    splits: int = 3,
    validation_dates: int = 13,
    gap_observation_dates: int = 6,
    min_train_dates: int = 90,
    date_column: str = "date",
) -> InnerTemporalPlan:
    dates = pd.DatetimeIndex(sorted(pd.to_datetime(outer_train[date_column]).unique()))
    required = min_train_dates + gap_observation_dates + validation_dates
    if len(dates) < required:
        raise ValueError(f"{len(dates)} observation dates cannot support an inner temporal split requiring {required}")

    available = len(dates) - min_train_dates - gap_observation_dates
    actual = min(splits, available // validation_dates)
    if actual < 1:
        raise ValueError("no inner split fits inside the outer training window")

    rows: list[InnerSplit] = []
    first_validation = len(dates) - actual * validation_dates
    for index in range(actual):
        validation_start_position = first_validation + index * validation_dates
        train_end_position = validation_start_position - gap_observation_dates - 1
        validation_end_position = validation_start_position + validation_dates - 1
        rows.append(InnerSplit(
            index=index,
            train_end=dates[train_end_position],
            validation_start=dates[validation_start_position],
            validation_end=dates[validation_end_position],
        ))
    return InnerTemporalPlan(tuple(rows), gap_observation_dates)


def assert_outer_isolation(plan: InnerTemporalPlan, outer_validation: pd.DataFrame, *, date_column: str = "date") -> None:
    if outer_validation.empty:
        return
    outer_start = pd.to_datetime(outer_validation[date_column]).min()
    if any(split.validation_end >= outer_start for split in plan.splits):
        raise RuntimeError("inner validation overlaps the outer validation period")
