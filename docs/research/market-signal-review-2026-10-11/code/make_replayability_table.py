#!/usr/bin/env python3
"""Which inputs of the live scorer could be replayed on past dates, and which could not?

Reads the live rows of `signals.csv` (built from `src/scoring/engine.py` by `make_signals_csv.py`) and classifies each by what its inputs are. The judgement is about the INPUTS, from the registry's
`inputs` and `timestamp_semantics` columns, not about the product's behaviour:

    REPLAYABLE_PRICE      computed from daily prices and benchmarks only; replayable from a point-in-time price store. Whether the live provider's adjusted closes equal the research store's is NOT established.
    RECOMPUTABLE_SEC      the concept exists in the research stack from SEC filings with acceptance times, but with different definitions and a different source than the live provider field.
    NOT_REPLAYABLE        a provider snapshot taken at request time and overwritten; no history was kept. Replayable only from the day an archive starts (see src/quant/pit/snapshot_archive.py).
    DEPENDS               a function of other inputs; replayable only if all of them are.

    python3 docs/research/market-signal-review-2026-10-11/code/make_replayability_table.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]

CLASSES = {
    "live.momentum": ("REPLAYABLE_PRICE", "daily Close and Volume of the stock and the benchmark", "none for the price series; provider equivalence unverified"),
    "live.reversal": ("REPLAYABLE_PRICE", "daily Close", "none for the price series; provider equivalence unverified"),
    "live.risk": ("REPLAYABLE_PRICE", "daily Close and benchmarks", "none for the price series; liquidity and macro components also need volume and the macro gate inputs"),
    "live.quality": ("RECOMPUTABLE_SEC", "provider fundamentals (gross profitability, issuance, asset growth)", "archive provider snapshots going forward; for the past use SEC facts with acceptance times, accepting a different definition"),
    "live.fundamental": ("NOT_REPLAYABLE", "provider fundamentals and analyst fields (targets, forward P/E, earnings surprise)", "archive provider snapshots going forward; analyst fields have no free historical source"),
    "live.news": ("NOT_REPLAYABLE", "news items with provider timestamps and a sentiment model", "archive items and model version going forward; a language-model sentiment also needs its training cutoff (Glasserman and Lin)"),
    "live.gate": ("NOT_REPLAYABLE", "FRED series and VIX at the latest available release", "ALFRED vintages for revised FRED series (blocked: no key); VIX as a dated market series"),
    "live.sleeve": ("DEPENDS", "member factors", "each sleeve inherits the weakest of its members"),
    "live.confidence": ("DEPENDS", "scorecard internals (dispersion, data freshness, events, model, stability, macro)", "inherits the weakest input; data-freshness terms need the archive's retrieval times"),
}


def classify(signal_id: str) -> tuple[str, str, str]:
    for prefix in sorted(CLASSES, key=len, reverse=True):
        if signal_id.startswith(prefix):
            return CLASSES[prefix]
    raise KeyError(signal_id)


def main() -> int:
    rows = [r for r in csv.DictReader((HERE / "signals.csv").open(encoding="utf-8")) if r["scope"].startswith("live")]
    out = []
    for r in rows:
        cls, source, needed = classify(r["signal_id"])
        out.append({"signal_id": r["signal_id"], "layer": r["layer"], "name": r["name"], "replayability": cls, "inputs_as_registered": r["inputs"], "timestamp_semantics": r["timestamp_semantics"],
                    "what_the_inputs_are": source, "what_would_make_it_replayable": needed})
    with (HERE / "live_scorer_replayability.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(out[0]))
        writer.writeheader()
        writer.writerows(out)
    counts = {}
    for r in out:
        counts[(r["layer"], r["replayability"])] = counts.get((r["layer"], r["replayability"]), 0) + 1
    summary = {f"{layer}:{cls}": n for (layer, cls), n in sorted(counts.items())}
    (HERE / "validation" / "live_scorer_replayability_summary.json").write_text(json.dumps({"rows": len(out), "by_layer_and_class": summary,
        "factors_replayable_from_prices": sum(1 for r in out if r["layer"] == "factor" and r["replayability"] == "REPLAYABLE_PRICE"), "factors_total": sum(1 for r in out if r["layer"] == "factor")}, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
