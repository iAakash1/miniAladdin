"""
Point-in-time universe — membership as it was, not as it turned out.

## The limitation this removes

`src/panel/universe.py` states the problem precisely and then, correctly,
declines to fake a solution::

    Universe returns CURRENT membership, not historical. A panel built over
    2016-2026 using today's mega-cap list contains only companies that survived
    to today ... Fixing this requires point-in-time index membership, which has
    no free source.

There is now a source. `dolthub_stocks_ohlcv_monthly` is a whole-market
cross-section at each month-end going back to 2011, so the names that were
liquid in March 2013 can be read off March 2013 — including the ones that
later failed. Membership is *selected from the past* rather than *filtered by
the present*, which is the entire distinction.

Verified rather than assumed: SIVB is in the March 2023 cross-section, trading
at 267.83 on the 8th and 106.04 on the 9th, and its bars stop when trading was
halted. A survivors-only universe silently omits that name and every statistic
computed over it is measuring a world in which regional banks did not fail.

## How membership is decided, and why each rule is there

At each rebalance date `d`, from the snapshot at or before `d`:

1. **Drop ETFs and test issues** (`symbol.is_etf`, `is_test_issue`). A fund's
   fundamentals are its holdings', and a test issue is not a security.
2. **Drop names priced below `MIN_PRICE`.** Sub-$5 quotes have tick sizes that
   are a large fraction of the price, so their returns are dominated by
   microstructure. This is a *liquidity* screen and it is applied on the
   snapshot's own close, so it is point-in-time.
3. **Rank by *smoothed* dollar volume and take the top `size`.** Dollar volume
   is the liquidity measure that survives splits without adjustment, but one
   month-end's reading is noisy: an earnings date or an index event can lift a
   name's single-day volume by an order of magnitude. Ranking on the raw value
   produced **47.5 entries per rebalance out of 180** — 26% monthly churn that
   is mostly measurement noise, and which a backtest pays real transaction
   costs for. The rank therefore uses a trailing median over
   `SMOOTHING_MONTHS` sampled month-ends, which is **backward-looking only** and
   so preserves the point-in-time property.
4. **Drop names past their `last_seen`.** A symbol cannot be a member after the
   security master stops seeing it.

Rule 4 has a stated hole: `symbol.last_seen` begins 2017-10-26, so exits before
then are not dated by it. For those years membership relies on rule 3 alone —
a delisted name simply stops appearing in the cross-section. That is why
`coverage_class` reports `PARTIAL` for pre-2017 windows instead of claiming a
completeness the data does not have.

## What this deliberately is not

Not index membership. This is a liquidity-ranked universe, not the S&P 500, and
a study over it should say so. It is survivorship-free, which is the property
that matters for measurement; it is not a reconstruction of any published
index, and calling it one would be a different kind of dishonesty.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date as Date
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd

from src.quant.datasets.store import RawStore

logger = logging.getLogger("omnisignal.quant.pit.universe")

#: Below this, tick size is a large fraction of price and returns are
#: microstructure rather than information.
MIN_PRICE = 5.0

#: A snapshot thinner than this is a data problem, not a quiet market.
MIN_SNAPSHOT_NAMES = 200

#: Month-end snapshots averaged into the liquidity rank. Three is enough to
#: damp a single earnings-driven volume spike and short enough that a genuine
#: liquidity change is reflected within a quarter. Strictly trailing — the
#: window ends at the rebalance date, never spans it.
SMOOTHING_MONTHS = 3

#: `symbol.last_seen` starts here; before it, delisting cannot be dated.
LAST_SEEN_COVERAGE_START = Date(2017, 10, 26)

UNIVERSE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class UniverseSnapshot:
    """Membership on one rebalance date, with the evidence for it."""

    as_of: Date
    symbols: tuple[str, ...]
    candidates: int
    dropped_etf: int
    dropped_price: int
    dropped_delisted: int
    min_dollar_volume: float
    coverage_class: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of.isoformat(),
            "symbols": list(self.symbols),
            "candidates": self.candidates,
            "dropped_etf": self.dropped_etf,
            "dropped_price": self.dropped_price,
            "dropped_delisted": self.dropped_delisted,
            "min_dollar_volume": self.min_dollar_volume,
            "coverage_class": self.coverage_class,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "UniverseSnapshot":
        return cls(
            as_of=Date.fromisoformat(payload["as_of"]),
            symbols=tuple(payload["symbols"]),
            candidates=payload["candidates"],
            dropped_etf=payload["dropped_etf"],
            dropped_price=payload["dropped_price"],
            dropped_delisted=payload["dropped_delisted"],
            min_dollar_volume=payload["min_dollar_volume"],
            coverage_class=payload["coverage_class"],
        )


@dataclass
class UniverseHistory:
    """Every rebalance date's membership, queryable as of any date."""

    name: str
    size: int
    snapshots: list[UniverseSnapshot] = field(default_factory=list)
    schema_version: int = UNIVERSE_SCHEMA_VERSION
    built_from: str = ""
    notes: list[str] = field(default_factory=list)

    #: True — this is the property the module exists to provide.
    point_in_time: bool = True

    def __post_init__(self) -> None:
        self.snapshots = sorted(self.snapshots, key=lambda snapshot: snapshot.as_of)

    # ── queries ──────────────────────────────────────────────────────────

    def members(self, as_of: Date) -> tuple[str, ...]:
        """Membership as it stood on `as_of`.

        **The point-in-time read.** Uses the latest snapshot at or before the
        date and never a later one, so a caller cannot accidentally receive
        membership that was decided after the date it is asking about.
        """
        snapshot = self.snapshot_for(as_of)
        return snapshot.symbols if snapshot else ()

    def snapshot_for(self, as_of: Date) -> Optional[UniverseSnapshot]:
        chosen: Optional[UniverseSnapshot] = None
        for snapshot in self.snapshots:
            if snapshot.as_of <= as_of:
                chosen = snapshot
            else:
                break
        return chosen

    def all_members(self) -> list[str]:
        """Union of every historical member — the ingestion target.

        Deliberately a union rather than the latest membership: the daily price
        ingestion has to cover every name that was *ever* eligible, or the
        survivorship-free universe silently degrades to survivors the moment a
        backtest asks for a delisted member's bars.
        """
        seen: set[str] = set()
        for snapshot in self.snapshots:
            seen.update(snapshot.symbols)
        return sorted(seen)

    def turnover(self) -> list[dict[str, Any]]:
        """Names entering and leaving at each rebalance."""
        out: list[dict[str, Any]] = []
        previous: set[str] = set()
        for snapshot in self.snapshots:
            current = set(snapshot.symbols)
            out.append(
                {
                    "as_of": snapshot.as_of.isoformat(),
                    "members": len(current),
                    "entered": sorted(current - previous),
                    "exited": sorted(previous - current),
                }
            )
            previous = current
        return out

    def summary(self) -> dict[str, Any]:
        if not self.snapshots:
            return {"name": self.name, "snapshots": 0}
        moves = self.turnover()
        exits = sorted({symbol for move in moves for symbol in move["exited"]})
        return {
            "name": self.name,
            "size": self.size,
            "snapshots": len(self.snapshots),
            "start": self.snapshots[0].as_of.isoformat(),
            "end": self.snapshots[-1].as_of.isoformat(),
            "unique_members": len(self.all_members()),
            "ever_exited": len(exits),
            "mean_entries_per_rebalance": round(
                sum(len(move["entered"]) for move in moves[1:]) / max(1, len(moves) - 1), 2
            ),
            "point_in_time": self.point_in_time,
            "coverage_classes": sorted({s.coverage_class for s in self.snapshots}),
            "notes": list(self.notes),
        }

    # ── persistence ──────────────────────────────────────────────────────

    def save(self, directory: Path | str) -> Path:
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        target = path / f"{self.name}.json"
        target.write_text(
            json.dumps(
                {
                    "name": self.name,
                    "size": self.size,
                    "schema_version": self.schema_version,
                    "built_from": self.built_from,
                    "point_in_time": self.point_in_time,
                    "notes": self.notes,
                    "snapshots": [snapshot.as_dict() for snapshot in self.snapshots],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return target

    @classmethod
    def load(cls, directory: Path | str, name: str = "liquid") -> "UniverseHistory":
        path = Path(directory) / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"no universe at {path} — run `backfill --stage universe` first"
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            name=payload["name"],
            size=payload["size"],
            schema_version=payload.get("schema_version", UNIVERSE_SCHEMA_VERSION),
            built_from=payload.get("built_from", ""),
            point_in_time=payload.get("point_in_time", True),
            notes=payload.get("notes", []),
            snapshots=[UniverseSnapshot.from_dict(item) for item in payload["snapshots"]],
        )


def build_pit_universe(
    store: RawStore,
    *,
    size: int = 180,
    name: str = "liquid",
    min_price: float = MIN_PRICE,
    monthly_dataset: str = "dolthub_stocks_ohlcv_monthly",
    symbol_dataset: str = "dolthub_stocks_symbol",
) -> UniverseHistory:
    """Derive point-in-time membership from whole-market month-end snapshots."""
    monthly = store.read(monthly_dataset, columns=["date", "symbol", "close", "volume"])
    if monthly.empty:
        raise ValueError(
            f"{monthly_dataset} is empty — run `backfill --stage monthly` before this"
        )

    master = _load_symbol_master(store, symbol_dataset)
    monthly = monthly.dropna(subset=["date", "symbol", "close", "volume"])
    monthly["dollar_volume"] = monthly["close"].astype(float) * monthly["volume"].astype(float)

    # Trailing median dollar volume per symbol, over the last SMOOTHING_MONTHS
    # sampled month-ends. `closed="left"` is wrong here and `min_periods=1` is
    # deliberate: the window ENDS at the current snapshot (that day's volume is
    # observable at that day's close, so including it is point-in-time correct),
    # and a name with only one observation is ranked on it rather than excluded.
    monthly = monthly.sort_values(["symbol", "date"], kind="mergesort")
    monthly["smoothed_dollar_volume"] = (
        monthly.groupby("symbol", sort=False)["dollar_volume"]
        .transform(lambda values: values.rolling(SMOOTHING_MONTHS, min_periods=1).median())
    )

    snapshots: list[UniverseSnapshot] = []
    for as_of, group in monthly.groupby("date", sort=True):
        if len(group) < MIN_SNAPSHOT_NAMES:
            logger.warning(
                "universe: skipping %s — only %d names in the cross-section", as_of, len(group)
            )
            continue

        candidates = len(group)
        eligible = group

        excluded = master["excluded"] if master is not None else set()
        before_etf = len(eligible)
        if excluded:
            eligible = eligible[~eligible["symbol"].isin(excluded)]
        dropped_etf = before_etf - len(eligible)

        before_price = len(eligible)
        eligible = eligible[eligible["close"].astype(float) >= min_price]
        dropped_price = before_price - len(eligible)

        before_delisted = len(eligible)
        if master is not None:
            last_seen = master["last_seen"]
            eligible = eligible[
                eligible["symbol"].map(lambda s: _still_listed(s, as_of, last_seen))
            ]
        dropped_delisted = before_delisted - len(eligible)

        ranked = eligible.sort_values("smoothed_dollar_volume", ascending=False).head(size)
        if ranked.empty:
            continue

        snapshots.append(
            UniverseSnapshot(
                as_of=as_of,
                symbols=tuple(sorted(ranked["symbol"].astype(str))),
                candidates=candidates,
                dropped_etf=dropped_etf,
                dropped_price=dropped_price,
                dropped_delisted=dropped_delisted,
                min_dollar_volume=float(ranked["smoothed_dollar_volume"].min()),
                coverage_class=(
                    "complete" if as_of >= LAST_SEEN_COVERAGE_START else "partial"
                ),
            )
        )

    history = UniverseHistory(
        name=name,
        size=size,
        snapshots=snapshots,
        built_from=f"{monthly_dataset} + {symbol_dataset}",
        notes=[
            "Liquidity-ranked, not index membership. Do not describe a study over "
            "this universe as an index backtest.",
            "Survivorship-free by construction: membership is selected from each "
            "month's whole-market cross-section, so names that later delisted are "
            "present in the months they were liquid.",
            f"Screens: non-ETF, non-test-issue, close >= {min_price}, top {size} by "
            f"{SMOOTHING_MONTHS}-month trailing-median dollar volume (trailing window "
            "only), dropped after symbol.last_seen.",
            "coverage_class is 'partial' before 2017-10-26, where symbol.last_seen "
            "has no data and delisting is inferred only from a name leaving the "
            "cross-section.",
        ],
    )
    logger.info("universe %s: %s", name, json.dumps(history.summary(), default=str)[:300])
    return history


def _load_symbol_master(store: RawStore, dataset_id: str) -> Optional[dict[str, Any]]:
    """Exclusion set and delisting dates from the security master.

    Returns None when the master is absent, and the caller then applies only
    the screens it can. Missing reference data degrades the screen explicitly;
    it does not silently pass everything through as though it had been checked.
    """
    try:
        frame = store.read(
            dataset_id, columns=["symbol", "is_etf", "is_test_issue", "date"]
        )
    except Exception:  # noqa: BLE001 — absence is a legitimate state, reported below
        logger.warning("universe: symbol master %s unavailable — ETF/delist screens skipped", dataset_id)
        return None
    if frame.empty:
        return None

    excluded = set(
        frame[
            (frame["is_etf"].fillna(0).astype(float) > 0)
            | (frame["is_test_issue"].fillna(0).astype(float) > 0)
        ]["symbol"].astype(str)
    )
    last_seen = {
        str(row.symbol): row.date
        for row in frame.dropna(subset=["date"]).itertuples(index=False)
    }
    return {"excluded": excluded, "last_seen": last_seen}


def _still_listed(symbol: str, as_of: Date, last_seen: dict[str, Date]) -> bool:
    """Whether a symbol was still listed on `as_of`.

    An unknown symbol is kept, not dropped. The master starts in 2017 and this
    is a *delisting* screen: absence of evidence that a name died is not
    evidence that it did, and dropping unknowns would quietly reintroduce
    survivorship by discarding exactly the names the master never saw.
    """
    seen = last_seen.get(str(symbol))
    return True if seen is None else as_of <= seen
