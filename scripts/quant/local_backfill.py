"""
Local backfill — ingest from the cloned Dolt repositories.

Complements `scripts/quant/backfill.py`, which reads over HTTP. Same catalog,
same `RawStore`, same partitions; a manifest records which reader produced it
and the clone's resolved commit hash.

Usage::

    python -m scripts.quant.local_backfill --stage earnings
    python -m scripts.quant.local_backfill --stage options
    python -m scripts.quant.local_backfill --stage all
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from src.quant.datasets import catalog
from src.quant.datasets.local_dolt import LocalDoltClient
from src.quant.datasets.local_ingest import (
    ingest_aggregated_local,
    ingest_whole_table_local,
)
from src.quant.datasets.store import RawStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("local_backfill")

#: Per (date, symbol) option-chain aggregate.
#:
#: Every quantity is computed inside Dolt so that 116M raw rows never cross the
#: process boundary. The delta buckets are wide because listed strikes are
#: discrete: interpolating an exact 25-delta IV would imply a precision the
#: strike grid does not have.
OPTION_CHAIN_AGGREGATE = """
select
  `date`,
  act_symbol,
  count(*) as contracts,
  count(distinct expiration) as expirations,
  count(distinct strike) as strikes,
  avg(case when abs(delta) between 0.45 and 0.55 then vol end) as atm_iv,
  avg(case when call_put='Put'  and abs(delta) between 0.20 and 0.30 then vol end) as put_25_iv,
  avg(case when call_put='Call' and delta between 0.20 and 0.30 then vol end) as call_25_iv,
  avg(case when abs(delta) between 0.45 and 0.55 and datediff(expiration, `date`) <= 45 then vol end) as atm_iv_near,
  avg(case when abs(delta) between 0.45 and 0.55 and datediff(expiration, `date`) >  45 then vol end) as atm_iv_far,
  avg(case when ask > 0 and bid > 0 then (ask - bid) / ((ask + bid) / 2) end) as rel_spread
from option_chain
where `date` >= '{year}-01-01' and `date` <= '{year}-12-31'
group by `date`, act_symbol
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill from local Dolt clones")
    parser.add_argument("--stage", default="all")
    parser.add_argument("--root", default="data/research")
    parser.add_argument("--datasets", default="datasets")
    parser.add_argument("--start-year", type=int, default=2019)
    parser.add_argument("--end-year", type=int, default=2026)
    args = parser.parse_args()

    store = RawStore(args.root)
    client = LocalDoltClient(args.datasets)

    availability = client.availability()
    if not availability["cli"]:
        logger.error("dolt CLI not found — nothing to do")
        return 1
    missing = [n for n, i in availability["repositories"].items() if not i["present"]]
    if missing:
        logger.warning("clones absent: %s (those stages will be skipped)", missing)

    stages = (
        ["corporate_actions", "earnings", "options"] if args.stage == "all" else [args.stage]
    )
    reports: dict[str, object] = {}

    for stage in stages:
        logger.info("=== stage %s ===", stage)

        if stage == "corporate_actions":
            for spec in (catalog.STOCKS_DIVIDEND, catalog.STOCKS_SPLIT):
                report = ingest_whole_table_local(spec, store, client=client)
                reports[spec.dataset_id] = report.as_dict()
                logger.info("%s: %d rows", spec.dataset_id, report.rows)

        elif stage == "earnings":
            for spec in (catalog.EARNINGS_EPS_HISTORY, catalog.EARNINGS_CALENDAR):
                report = ingest_whole_table_local(spec, store, client=client)
                reports[spec.dataset_id] = report.as_dict()
                logger.info("%s: %d rows", spec.dataset_id, report.rows)

        elif stage == "options":
            report = ingest_aggregated_local(
                catalog.OPTIONS_CHAIN_DAILY, store,
                sql_template=OPTION_CHAIN_AGGREGATE,
                start_year=args.start_year, end_year=args.end_year, client=client,
                transformations=[
                    "aggregated per (date, symbol) inside Dolt; raw contracts never materialised",
                    "ATM = |delta| in [0.45, 0.55]; 25-delta = |delta| in [0.20, 0.30]",
                    "near/far split at 45 calendar days to expiry",
                    "rel_spread = mean (ask - bid) / mid over quotes with both sides positive",
                ],
                notes=[
                    "Delta buckets are wide because listed strikes are discrete; an "
                    "exact-delta interpolation would imply precision the grid lacks.",
                    "Snapshot dates do not always fall on trading days — consumers must "
                    "align as 'latest available on or before'.",
                ],
            )
            reports[report.dataset_id] = report.as_dict()
            logger.info("%s: %d aggregated rows", report.dataset_id, report.rows)

        else:
            logger.error("unknown stage %s", stage)
            return 1

    reports["_client"] = client.stats.as_dict()
    print(json.dumps(reports, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
