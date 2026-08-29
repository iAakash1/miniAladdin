"""
Research backfill driver.

Stages are ordered by dependency, not by size:

1. ``reference``  — security master, splits, Treasury curve, Fama-French factors.
2. ``monthly``    — whole-market month-end cross-sections (universe input).
3. ``universe``   — derive point-in-time membership from stage 2.
4. ``daily``      — daily OHLCV for the union of every historical member.
5. ``dividend``   — cash dividends for that same union.
6. ``volatility`` — implied/realised volatility snapshots for that union.

Every stage is resumable: partitions already on disk are skipped, so a run
interrupted at any point resumes at the granularity of a year rather than
restarting.

Usage::

    python -m scripts.quant.backfill --stage reference
    python -m scripts.quant.backfill --stage all --start 2011-01-03
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date as Date
from datetime import timedelta

from src.quant.datasets import catalog
from src.quant.datasets.dolthub import DoltHubClient
from src.quant.datasets.ingest import (
    ingest_by_symbol,
    ingest_date_partitioned,
    ingest_whole_table,
)
from src.quant.datasets.store import RawStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("backfill")


def month_end_candidates(start: Date, end: Date) -> list[Date]:
    """Last weekday of each month in range.

    One candidate per month, and the source decides whether it traded: a date
    that returns no rows is recorded as non-trading rather than guessed at.

    A month whose last weekday is a holiday therefore yields no snapshot, and
    the universe builder carries the previous month's membership forward rather
    than inventing one. That is the cheaper error: a full-market cross-section
    costs ~6 paginated requests, so emitting a second candidate per month would
    double the most expensive stage in the backfill to recover ~8% of months
    whose membership barely differs from their neighbours'.
    """
    out: list[Date] = []
    cursor = Date(start.year, start.month, 1)
    while cursor <= end:
        following = Date(cursor.year + (cursor.month // 12), (cursor.month % 12) + 1, 1)
        day = following - timedelta(days=1)
        while day >= cursor:
            if day.weekday() < 5:
                if start <= day <= end:
                    out.append(day)
                break
            day -= timedelta(days=1)
        cursor = following
    return sorted(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill research datasets")
    parser.add_argument("--stage", default="reference")
    parser.add_argument("--root", default="data/research")
    parser.add_argument("--start", default="2011-01-03")
    parser.add_argument("--end", default="")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--universe-size", type=int, default=180)
    args = parser.parse_args()

    store = RawStore(args.root)
    client = DoltHubClient()
    start = Date.fromisoformat(args.start)
    end = Date.fromisoformat(args.end) if args.end else Date.today()
    stages = (
        ["reference", "monthly", "universe", "daily", "dividend", "volatility"]
        if args.stage == "all"
        else [args.stage]
    )
    reports: dict[str, object] = {}

    for stage in stages:
        logger.info("=== stage %s ===", stage)

        if stage == "reference":
            for spec in (catalog.STOCKS_SYMBOL, catalog.STOCKS_SPLIT, catalog.RATES_TREASURY):
                report = ingest_whole_table(spec, store, client=client)
                reports[spec.dataset_id] = report.as_dict()
                logger.info("%s: %d rows", spec.dataset_id, report.rows)
            from src.quant.datasets.french import ingest_french_factors

            report = ingest_french_factors(store)
            reports[report.dataset_id] = report.as_dict()
            logger.info("%s: %d rows", report.dataset_id, report.rows)

        elif stage == "monthly":
            dates = month_end_candidates(start, end)
            report = ingest_date_partitioned(
                catalog.STOCKS_OHLCV_MONTHLY, store,
                start=start, end=end, symbols=None,
                client=client, workers=args.workers, dates=dates,
            )
            reports[report.dataset_id] = report.as_dict()
            logger.info("monthly: %d rows over %d dates", report.rows, report.dates_with_data)

        elif stage == "universe":
            from src.quant.pit.universe import build_pit_universe

            history = build_pit_universe(store, size=args.universe_size)
            history.save(store.root / "universe")
            reports["universe"] = history.summary()
            logger.info("universe: %s", json.dumps(history.summary(), default=str)[:400])

        elif stage in {"daily", "dividend", "volatility"}:
            from src.quant.pit.universe import UniverseHistory

            history = UniverseHistory.load(store.root / "universe")
            members = history.all_members()
            logger.info("stage %s over %d symbols", stage, len(members))

            if stage == "daily":
                report = ingest_date_partitioned(
                    catalog.STOCKS_OHLCV, store, start=start, end=end,
                    symbols=members, client=client, workers=args.workers,
                )
            elif stage == "dividend":
                report = ingest_by_symbol(
                    catalog.STOCKS_DIVIDEND, store, members,
                    client=client, workers=args.workers,
                )
            else:
                report = ingest_date_partitioned(
                    catalog.OPTIONS_VOLATILITY, store,
                    start=max(start, Date(2019, 2, 1)), end=end,
                    symbols=members, client=client, workers=args.workers,
                )
            reports[report.dataset_id] = report.as_dict()
            logger.info("%s: %d rows", report.dataset_id, report.rows)

        else:
            logger.error("unknown stage %s", stage)
            return 1

    print(json.dumps(reports, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
