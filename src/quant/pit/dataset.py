"""
Point-in-time dataset builder — raw partitions in, a training matrix out.

## What this module is responsible for

Turning immutable raw data into a `(symbol, date)` matrix of features and
labels in which **every feature value was knowable on its row's date** and
every label describes what happened after it. It is the single place where the
point-in-time contract is assembled, and therefore the single place where it
can be broken.

The pipeline, in order, with the reason each stage is where it is:

    raw partitions
      -> per-symbol point-in-time returns          (adjust.py: split/dividend at ex-date)
      -> per-symbol features                        (backward windows only)
      -> per-symbol labels                          (forward windows, kept separate)
      -> cross-sectional normalisation              (against explicit PIT universe)
      -> macro join                                 (already lagged one session)
      -> availability lag applied                   (per feature declaration)
      -> guards                                     (leakage checks, then and only then)

Cross-sectional normalisation comes *after* per-symbol features because it
needs the whole date's cross-section, and *before* the macro join because macro
values are common to every name on a date and would standardise to exactly
zero — destroying the feature while appearing to work.

## The refusals

Three things this builder will not do, each because doing them quietly is how
a leak enters:

1. **Admit a source the catalog marks `NOT_POINT_IN_TIME`** as a feature
   input, without a named waiver recorded in the manifest.
2. **Admit a feature that has not declared `point_in_time_safe`.**
3. **Return a dataset whose guards failed.** `build()` runs the guards and
   raises; it does not return a matrix with a warning attached, because a
   warning is something a training script can ignore.

## Determinism

Row order is `(date, symbol)` with a stable sort, dtypes are pinned, and the
manifest records a content hash of the matrix. Two builds from the same raw
partitions produce the same bytes — the same property `src/panel/storage.py`
relies on, for the same reason: a dataset version that cannot be compared to
itself cannot anchor a reproducible experiment.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date as Date
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd

from src.quant.datasets import catalog as dataset_catalog
from src.quant.datasets.store import RawStore
from src.quant.features import cross_section as xs
from src.quant.features import macro as macro_features
from src.quant.features import price as price_features  # noqa: F401 - registers 16 features
from src.quant.features import earnings as earnings_features
from src.quant.features import options as option_features
from src.quant.features.registry import REGISTRY, FeatureGroup
from src.quant.labels import compute_symbol_labels, cross_sectional_rank_label
from src.quant.labels import get as get_label
from src.quant.pit import guards as guard_module
from src.quant.pit.adjust import point_in_time_returns
from src.quant.pit.calendar import TradingCalendar, require_chronological
from src.quant.pit.universe import UniverseHistory

logger = logging.getLogger("omnisignal.quant.pit.dataset")

DATASET_SCHEMA_VERSION = 1

#: A symbol needs at least this much history before any row of it is emitted.
#: Set from the registry's deepest lookback so that a row never contains a
#: feature computed from a partial window under a full window's name.
MIN_HISTORY_SESSIONS = 260

#: The first date on which corporate actions are covered.
#:
#: Measured, not assumed: the earliest `ex_date` anywhere in `stocks.split` is
#: 2014-03-28, while `stocks.ohlcv` begins 2011-01-03. Returns computed before
#: this date are split-contaminated — a 4:1 split with no split record reads as
#: a -75% single-session return, which is both the largest reversal signal and
#: the largest volatility observation any model would ever see, and it is
#: entirely fabricated.
#:
#: The builder REFUSES those years rather than emitting them with a caveat.
#: A caveat is something a training script ignores; a refusal is not. It costs
#: 3.2 years of the 15.6 available, which is the correct trade: a shorter clean
#: sample beats a longer contaminated one, and the contamination is
#: concentrated in exactly the features most sensitive to outliers.
CORPORATE_ACTION_COVERAGE_START = Date(2014, 4, 1)


@dataclass
class DatasetManifest:
    """Everything needed to reproduce and audit one training matrix."""

    dataset_version: str
    built_at: str
    universe: str
    start: str
    end: str
    step_sessions: int
    features: list[str]
    labels: list[str]
    rows: int
    symbols: int
    dates: int
    source_datasets: list[dict[str, Any]]
    content_hash: str
    guard_report: dict[str, Any]
    feature_coverage: dict[str, float]
    label_coverage: dict[str, float]
    schema_version: int = DATASET_SCHEMA_VERSION
    waivers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_version": self.dataset_version,
            "schema_version": self.schema_version,
            "built_at": self.built_at,
            "universe": self.universe,
            "start": self.start,
            "end": self.end,
            "step_sessions": self.step_sessions,
            "features": list(self.features),
            "labels": list(self.labels),
            "rows": self.rows,
            "symbols": self.symbols,
            "dates": self.dates,
            "source_datasets": list(self.source_datasets),
            "content_hash": self.content_hash,
            "guard_report": dict(self.guard_report),
            "feature_coverage": dict(self.feature_coverage),
            "label_coverage": dict(self.label_coverage),
            "waivers": list(self.waivers),
            "notes": list(self.notes),
        }


@dataclass
class TrainingDataset:
    """A built matrix and the manifest that describes it."""

    frame: pd.DataFrame
    manifest: DatasetManifest
    calendar: TradingCalendar
    universe: UniverseHistory

    @property
    def features(self) -> list[str]:
        return list(self.manifest.features)

    @property
    def labels(self) -> list[str]:
        return list(self.manifest.labels)

    def matrix(self, label: str, *, features: Optional[Sequence[str]] = None) -> pd.DataFrame:
        """Rows usable for one label: the label present and at least one feature."""
        chosen = list(features) if features else self.features
        subset = self.frame.dropna(subset=[label])
        return subset[subset[chosen].notna().any(axis=1)].reset_index(drop=True)


class DatasetBuilder:
    """Assembles point-in-time training matrices from the raw store."""

    def __init__(
        self,
        store: RawStore,
        universe: UniverseHistory,
        *,
        price_dataset: str = "dolthub_stocks_ohlcv",
        split_dataset: str = "dolthub_stocks_split",
        dividend_dataset: str = "dolthub_stocks_dividend",
        treasury_dataset: str = "dolthub_rates_us_treasury",
        volatility_dataset: str = "dolthub_options_volatility_history",
        chain_dataset: str = "dolthub_options_chain_daily",
        eps_history_dataset: str = "dolthub_earnings_eps_history",
        earnings_calendar_dataset: str = "dolthub_earnings_calendar",
        waivers: Optional[Sequence[str]] = None,
    ) -> None:
        self.store = store
        self.universe = universe
        self.price_dataset = price_dataset
        self.split_dataset = split_dataset
        self.dividend_dataset = dividend_dataset
        self.treasury_dataset = treasury_dataset
        self.volatility_dataset = volatility_dataset
        self.chain_dataset = chain_dataset
        self.eps_history_dataset = eps_history_dataset
        self.earnings_calendar_dataset = earnings_calendar_dataset
        self.waivers = list(waivers or [])
        self._sources: list[dict[str, Any]] = []

    # ── admission control ────────────────────────────────────────────────

    def _admit(self, dataset_id: str, *, role: str) -> Optional[pd.DataFrame]:
        """Read a raw dataset, refusing sources the catalog bars from training.

        The refusal is the point. A limitation recorded only in documentation is
        a limitation that gets violated by the next person in a hurry, including
        the person who wrote it down.
        """
        try:
            spec = dataset_catalog.get(dataset_id)
        except KeyError:
            spec = None

        if spec is not None and role == "feature" and not spec.historical_training_allowed:
            waiver = f"{dataset_id}:{role}"
            if waiver not in self.waivers:
                raise ValueError(
                    f"{dataset_id} is catalogued {spec.point_in_time.value} and may not be "
                    f"used as a {role} source. {spec.point_in_time_note} "
                    f"To override deliberately, pass waivers=['{waiver}'] — it is recorded "
                    "in the dataset manifest and reported in the UI."
                )
            logger.warning("dataset: WAIVER admitting %s as a %s source", dataset_id, role)

        try:
            frame = self.store.read(dataset_id)
        except Exception as error:  # noqa: BLE001 — absence is reported, never faked
            logger.warning("dataset: %s unavailable (%s)", dataset_id, error)
            return None

        manifest = self.store.manifest(dataset_id)
        self._sources.append(
            {
                "dataset_id": dataset_id,
                "role": role,
                "rows": manifest.rows,
                "min_date": manifest.min_date,
                "max_date": manifest.max_date,
                "point_in_time_status": manifest.point_in_time_status,
                "survivorship_status": manifest.survivorship_status,
                "retrieved_at": manifest.retrieved_at,
                "partitions": len(manifest.partitions),
            }
        )
        return frame

    # ── build ────────────────────────────────────────────────────────────

    def build(
        self,
        *,
        start: Date,
        end: Date,
        features: Optional[Sequence[str]] = None,
        labels: Optional[Sequence[str]] = None,
        step_sessions: int = 5,
        run_guards: bool = True,
        min_history: int = MIN_HISTORY_SESSIONS,
        allow_uncovered_corporate_actions: bool = False,
        workers: int = -1,
    ) -> TrainingDataset:
        began = time.perf_counter()
        self._sources = []
        coverage_notes: list[str] = []

        if start < CORPORATE_ACTION_COVERAGE_START and not allow_uncovered_corporate_actions:
            logger.warning(
                "dataset: start %s precedes corporate-action coverage (%s); "
                "clamping to keep split-contaminated returns out of training",
                start, CORPORATE_ACTION_COVERAGE_START,
            )
            coverage_notes.append(
                f"start clamped from {start} to {CORPORATE_ACTION_COVERAGE_START}: "
                "stocks.split has no ex_date before 2014-03-28, so earlier returns "
                "would carry fabricated split moves"
            )
            start = CORPORATE_ACTION_COVERAGE_START

        prices = self._admit(self.price_dataset, role="price")
        if prices is None or prices.empty:
            raise ValueError(
                f"{self.price_dataset} is empty — run `backfill --stage daily` before building"
            )
        splits = self._admit(self.split_dataset, role="corporate_action")
        dividends = self._admit(self.dividend_dataset, role="corporate_action")
        treasury = self._admit(self.treasury_dataset, role="feature")
        volatility = self._admit(self.volatility_dataset, role="feature")
        chain = self._admit(self.chain_dataset, role="feature")
        eps_history = self._admit(self.eps_history_dataset, role="feature")
        earnings_calendar = self._admit(self.earnings_calendar_dataset, role="feature")

        feature_names = list(features) if features else REGISTRY.per_symbol_names()
        macro_names = REGISTRY.names(group=FeatureGroup.MACRO)
        # Join-stage features: produced by an as-of merge against a dated source
        # rather than a per-symbol rolling window.
        option_names = REGISTRY.names(group=FeatureGroup.OPTIONS)
        earnings_names = REGISTRY.names(group=FeatureGroup.FUNDAMENTAL)
        label_names = list(labels) if labels else [
            "fwd_ret_1", "fwd_ret_5", "fwd_ret_21", "fwd_ret_63",
            "fwd_vol_21", "fwd_mae_21", "fwd_mfe_21", "fwd_dir_21",
        ]

        guard_report = guard_module.assert_features_declared_safe(REGISTRY, feature_names)
        guard_report.raise_for_status()

        prices = prices.dropna(subset=["date", "symbol", "close"])
        prices["date"] = pd.to_datetime(prices["date"]).dt.date
        calendar = TradingCalendar.from_dates(prices["date"].unique())

        # ── per-symbol stage ─────────────────────────────────────────────
        #
        # Embarrassingly parallel: each symbol's features depend only on that
        # symbol's own history, so there is no cross-symbol state to share. On a
        # 12-core machine this is the difference between a four-minute build and
        # a one-minute one, and it is where a 977-symbol build spends its time.
        #
        # Determinism is preserved because the results are re-sorted by
        # (date, symbol) before hashing — worker completion order never reaches
        # the output.
        eligible: list[tuple[str, pd.DataFrame]] = []
        skipped: list[str] = []
        for symbol, group in prices.groupby("symbol", sort=True):
            if len(group) < min_history:
                skipped.append(str(symbol))
            else:
                eligible.append((str(symbol), group))

        per_symbol: list[pd.DataFrame] = []
        if workers and workers != 1 and len(eligible) > 8:
            try:
                from joblib import Parallel, delayed

                blocks = Parallel(n_jobs=workers, prefer="processes", batch_size="auto")(
                    delayed(_symbol_block_worker)(
                        symbol, group, splits, dividends, feature_names, label_names
                    )
                    for symbol, group in eligible
                )
            except Exception as error:  # noqa: BLE001 — reported, then done serially
                logger.warning(
                    "dataset: parallel build unavailable (%s); falling back to serial. "
                    "The result is identical either way — only the wall clock differs.",
                    error,
                )
                blocks = [
                    self._symbol_block(symbol, group, splits, dividends, feature_names, label_names)
                    for symbol, group in eligible
                ]
        else:
            blocks = [
                self._symbol_block(symbol, group, splits, dividends, feature_names, label_names)
                for symbol, group in eligible
            ]
        per_symbol = [b for b in blocks if b is not None and not b.empty]

        if not per_symbol:
            raise ValueError(
                f"no symbol had at least {min_history} sessions — the price dataset is "
                f"too shallow to build features (deepest lookback is {REGISTRY.max_lookback()})"
            )
        panel = pd.concat(per_symbol, ignore_index=True)
        logger.info(
            "dataset: %d symbol blocks (%d skipped for < %d sessions), %d rows",
            len(per_symbol), len(skipped), min_history, len(panel),
        )

        # ── market aggregate, computed BEFORE the stride ─────────────────
        #
        # Market features are rolling windows counted in ROWS. Computing them
        # after the observation stride would make `market_mom_252` span 252
        # sampled rows — 1,260 trading sessions at stride 5, five years under a
        # one-year name. So the daily cross-sectional mean return is built here,
        # from every session, and joined to the strided rows afterwards.
        daily_market = (
            panel.groupby("date", sort=True)["total_return"].mean().reset_index()
        )
        market_block = (
            macro_features.compute_market_features(
                daily_market["total_return"], daily_market["date"]
            )
            if len(daily_market) >= 21
            else None
        )

        # ── observation stride ───────────────────────────────────────────
        #
        # Applied AFTER features, never before: a 252-session lookback computed
        # on every fifth bar would span five years of calendar time under a
        # one-year name. Striding the observations changes how often we look,
        # never what is visible — the same distinction `src/panel/builder.py`
        # draws for its `step`.
        sampled_dates = set(calendar.sample(step_sessions))
        panel = panel[panel["date"].isin(sampled_dates)].reset_index(drop=True)
        panel = panel[(panel["date"] >= start) & (panel["date"] <= end)].reset_index(drop=True)
        if panel.empty:
            raise ValueError(f"no observations between {start} and {end} at stride {step_sessions}")

        # ── universe membership ──────────────────────────────────────────
        dates = sorted(panel["date"].unique())
        members_by_date = xs.universe_map(self.universe, dates)
        panel["in_universe"] = [
            symbol in members_by_date.get(day, ()) for symbol, day in
            zip(panel["symbol"], panel["date"])
        ]

        # ── join-stage features ──────────────────────────────────────────
        #
        # After the stride and before cross-sectional ranking. After, because
        # each is an as-of merge that only needs the observation dates; before,
        # because these features should be ranked within the universe like any
        # other.
        attached_options: list[str] = []
        option_frame = option_features.build_option_features(volatility, chain)
        if not option_frame.empty:
            panel = option_features.attach_option_features(panel, option_frame)
            attached_options = [n for n in option_names if n in panel.columns]
        else:
            logger.warning("dataset: no option source — option features absent, not zeroed")

        attached_earnings: list[str] = []
        if eps_history is not None and earnings_calendar is not None:
            events = earnings_features.build_earnings_events(eps_history, earnings_calendar)
            if not events.empty:
                panel = earnings_features.attach_earnings_features(panel, events)
                attached_earnings = [n for n in earnings_names if n in panel.columns]
        if not attached_earnings:
            logger.warning("dataset: no earnings events — earnings features absent, not zeroed")

        joined_names = attached_options + attached_earnings

        # ── cross-sectional stage ────────────────────────────────────────
        rankable = feature_names + joined_names
        panel = xs.cross_sectional_frame(
            panel, rankable, universe_for=members_by_date, method="rank"
        )
        cross_names = [f"{name}_xs" for name in rankable]

        if "fwd_ret_21" in panel.columns:
            panel["fwd_rank_21"] = cross_sectional_rank_label(
                panel, "fwd_ret_21", universe_for=members_by_date
            )
            label_names = list(dict.fromkeys([*label_names, "fwd_rank_21"]))

        # ── macro join ───────────────────────────────────────────────────
        macro_frame = self._macro_block(market_block, treasury)
        if macro_frame is not None:
            panel = panel.merge(macro_frame, on="date", how="left")
            available_macro = [name for name in macro_names if name in panel.columns]
        else:
            available_macro = []
            logger.warning("dataset: no macro block — rates features absent, not zeroed")

        all_features = feature_names + joined_names + cross_names + available_macro
        panel = panel.sort_values(["date", "symbol"], kind="mergesort").reset_index(drop=True)

        # ── guards ───────────────────────────────────────────────────────
        if run_guards:
            guard_report = guard_module.assert_universe_is_point_in_time(
                self.universe, report=guard_report
            )
            guard_report = guard_module.assert_no_target_leakage(
                panel, all_features, label_names, report=guard_report
            )
            guard_report.raise_for_status()

        version = _dataset_version(
            universe=self.universe.name, start=start, end=end,
            step=step_sessions, features=all_features, labels=label_names,
            sources=self._sources,
        )
        manifest = DatasetManifest(
            dataset_version=version,
            built_at=datetime.now(timezone.utc).isoformat(),
            universe=self.universe.name,
            start=str(start),
            end=str(end),
            step_sessions=step_sessions,
            features=all_features,
            labels=label_names,
            rows=len(panel),
            symbols=int(panel["symbol"].nunique()),
            dates=int(panel["date"].nunique()),
            source_datasets=list(self._sources),
            content_hash=_frame_hash(panel, all_features + label_names),
            guard_report=guard_report.as_dict(),
            feature_coverage={
                name: round(float(panel[name].notna().mean()), 4)
                for name in all_features if name in panel.columns
            },
            label_coverage={
                name: round(float(panel[name].notna().mean()), 4)
                for name in label_names if name in panel.columns
            },
            waivers=list(self.waivers),
            notes=[
                *coverage_notes,
                f"observation stride {step_sessions} sessions, applied after feature "
                "computation so lookback windows remain in trading days",
                f"{len(skipped)} symbol(s) skipped for fewer than {min_history} sessions",
                "cross-sectional columns (_xs) normalised within point-in-time universe "
                "membership only; names outside the universe on a date carry NULL there",
                "macro features carry a one-session availability lag applied at source",
                (
                    f"{len(attached_options)} option feature(s) attached as-of "
                    "(latest snapshot at or before each date, 21-day staleness cap)"
                ),
                (
                    f"{len(attached_earnings)} earnings feature(s) attached from the "
                    "announcement's availability date, honouring before-open vs "
                    "after-close; periods with no matching announcement are dropped"
                ),
            ],
        )
        logger.info(
            "dataset %s: %d rows, %d symbols, %d dates in %.1fs",
            version, len(panel), manifest.symbols, manifest.dates,
            time.perf_counter() - began,
        )
        return TrainingDataset(
            frame=panel, manifest=manifest, calendar=calendar, universe=self.universe
        )

    # ── stages ───────────────────────────────────────────────────────────

    def _symbol_block(
        self,
        symbol: str,
        bars: pd.DataFrame,
        splits: Optional[pd.DataFrame],
        dividends: Optional[pd.DataFrame],
        feature_names: Sequence[str],
        label_names: Sequence[str],
    ) -> Optional[pd.DataFrame]:
        """Serial path — delegates to the same computation the workers run."""
        return self._compute_symbol_block(
            symbol, bars, splits, dividends, feature_names, label_names
        )

    @staticmethod
    def _compute_symbol_block(
        symbol: str,
        bars: pd.DataFrame,
        splits: Optional[pd.DataFrame],
        dividends: Optional[pd.DataFrame],
        feature_names: Sequence[str],
        label_names: Sequence[str],
    ) -> Optional[pd.DataFrame]:
        """Point-in-time returns, features and labels for one symbol."""
        adjusted = point_in_time_returns(
            bars, symbol=symbol, splits=splits, dividends=dividends
        )
        frame = adjusted.frame
        if frame.empty:
            return None

        # One check covering every feature computer and every label below. They
        # all read row order rather than dates, so this is the invariant they
        # silently depend on. `point_in_time_returns` already sorts and
        # de-duplicates; asserting it here means a future caller that does not
        # cannot fail quietly.
        require_chronological(frame, context=f"symbol block {symbol}")

        block = pd.DataFrame(
            {
                "symbol": symbol,
                "date": frame["date"].to_numpy(),
                "close": pd.to_numeric(frame["close"], errors="coerce").to_numpy(),
                "total_return": frame["total_return"].to_numpy(),
                "dollar_volume": frame["dollar_volume"].to_numpy(),
                "split_ratio": frame["split_ratio"].to_numpy(),
            }
        )
        for name in feature_names:
            block[name] = REGISTRY.computer(name)(frame).to_numpy()

        per_symbol_labels = [
            name for name in label_names if not get_label(name).cross_sectional
        ]
        if per_symbol_labels:
            computed = compute_symbol_labels(frame, labels=per_symbol_labels)
            for name in per_symbol_labels:
                block[name] = computed[name].to_numpy()
        return block

    def _macro_block(
        self, market_block: Optional[pd.DataFrame], treasury: Optional[pd.DataFrame]
    ) -> Optional[pd.DataFrame]:
        """Rates and market-regime features, one row per date.

        `market_block` arrives already computed on the full daily series — see
        the note at its construction. It is built from the aggregate of every
        symbol in the price panel, which includes the names that later failed,
        so its 2023 drawdown contains the regional banks. An index proxy
        reconstructed from current membership would not.
        """
        blocks: list[pd.DataFrame] = []

        if treasury is not None and not treasury.empty:
            curve = treasury.copy()
            curve["date"] = pd.to_datetime(curve["date"]).dt.date
            blocks.append(macro_features.compute_macro_features(curve))

        if market_block is not None and not market_block.empty:
            blocks.append(market_block)

        if not blocks:
            return None
        merged = blocks[0]
        for block in blocks[1:]:
            merged = merged.merge(block, on="date", how="outer")
        return merged.sort_values("date").reset_index(drop=True)


def _symbol_block_worker(
    symbol: str,
    bars: pd.DataFrame,
    splits: Optional[pd.DataFrame],
    dividends: Optional[pd.DataFrame],
    feature_names: Sequence[str],
    label_names: Sequence[str],
) -> Optional[pd.DataFrame]:
    """Module-level so a process pool can pickle it.

    A bound method carries its instance, and `DatasetBuilder` holds a `RawStore`
    — pickling that would ship a filesystem handle to every worker. This takes
    only the frames it needs.
    """
    return DatasetBuilder._compute_symbol_block(
        symbol, bars, splits, dividends, feature_names, label_names
    )


def _frame_hash(frame: pd.DataFrame, columns: Sequence[str]) -> str:
    """Stable content hash of the numeric payload.

    Hashing the values rather than the file: two builds that agree on every
    number should agree on this, whatever pandas decides about column order or
    dtype width.
    """
    present = [name for name in columns if name in frame.columns]
    ordered = frame[["symbol", "date", *present]].sort_values(
        ["date", "symbol"], kind="mergesort"
    )
    hashed = pd.util.hash_pandas_object(ordered, index=False).values.tobytes()
    return hashlib.sha256(hashed).hexdigest()[:32]


def _dataset_version(**payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "ds-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
