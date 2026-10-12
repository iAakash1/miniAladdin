#!/usr/bin/env python3
"""Phase II continuation: precise boolean sweeps of the 2022-2026 literature through OpenAlex.

The ranked searches in `recent_lit_search.py` return the best 50 per query. A sweep instead enumerates EVERY work in the window whose title or abstract satisfies a boolean expression (OpenAlex
`title_and_abstract.search` supports AND, OR, NOT and quoted phrases), paging with a cursor up to a stated cap. The sweep expressions are the ones that decide the novelty question (restatement or amendment
with a return outcome, late filings, point-in-time and data-revision problems, research-design sensitivity, linear against machine-learning models, microcaps and costs, accounting quality, internal-control drift, data
provenance). A sweep that hits its cap is reported as truncated and the cap is in the log.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/recent_lit_sweeps.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
import urllib.parse
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from recent_lit_search import FROM, LOG, OA_FIELDS, RAW, TO, fetch  # noqa: E402

CAP = 600  # works per sweep

SWEEPS = [
    ("S1", "T1", '(restatement OR restatements OR restated OR "10-K/A" OR "amended filings" OR "non-reliance" OR misstatement OR misstatements) AND ("abnormal returns" OR "stock returns" OR "excess returns" OR drift OR underreaction OR "return predictability" OR "cross-section of returns" OR "long-short" OR "trading strategy" OR anomaly OR mispricing OR alpha)'),
    ("S2", "T2", '("10-K/A" OR "amended 10-K" OR "10-K amendments" OR "amended annual report" OR "amendment filings" OR "filing amendments" OR "periodic report amendments" OR "10-Q/A" OR "amended financial statements" OR "amended filings")'),
    ("S3", "T3", '("late filing" OR "late filers" OR "NT 10-K" OR "Form NT" OR "filing delay" OR "reporting delay" OR "filing lag" OR "reporting lag") AND (returns OR "stock price" OR drift OR predictability OR "market reaction")'),
    ("S4", "T1", '("Item 4.02" OR "non-reliance" OR "8-K") AND (restatement OR misstatement OR restated)'),
    ("S5", "T3", '("point-in-time" OR "look-ahead bias" OR "lookahead bias" OR "data vintage" OR "real-time data" OR "as-originally-reported" OR "restated data" OR "Compustat restatements" OR "data revisions") AND (returns OR "financial data" OR fundamentals OR accounting OR "asset pricing" OR backtest)'),
    ("S6", "T8", '("research design" OR "design choices" OR "nonstandard errors" OR "non-standard errors" OR "researcher degrees of freedom" OR "specification search" OR "p-hacking") AND ("asset pricing" OR "stock returns" OR "cross-section" OR "return prediction" OR anomalies)'),
    ("S7", "T6", '("machine learning" OR "neural network" OR "gradient boosting" OR "random forest") AND (linear OR OLS OR "simple model" OR "does not outperform" OR "no better" OR overfitting OR "regression-based") AND ("stock returns" OR "cross-section" OR "return prediction" OR "equity returns")'),
    ("S8", "T8", '("machine learning") AND (microcaps OR "micro-caps" OR "transaction costs" OR "trading costs" OR "economic significance" OR turnover OR "implementable") AND ("stock returns" OR "cross-section" OR "equity")'),
    ("S9", "T4", '("accounting quality" OR "earnings quality" OR "financial reporting quality" OR "information quality" OR "information risk") AND ("cross-section of returns" OR "predict returns" OR "return predictability" OR anomaly OR mispricing OR "future returns")'),
    ("S10", "T5", '("material weakness" OR "internal control" OR "SEC enforcement" OR "AAER" OR "comment letters" OR "accounting fraud") AND (drift OR underreaction OR "long-run returns" OR "abnormal returns" OR "future returns")'),
    ("S11", "T10", '("data quality" OR "data errors" OR "database discrepancies" OR "data revisions" OR provenance OR "stale prices" OR staleness OR "missing data") AND ("asset pricing" OR "stock returns" OR "return predictability" OR "cross-section")'),
    ("S12", "T7", '(reproducibility OR replication OR "data leakage" OR "information leakage" OR "survivorship bias" OR "backtest overfitting") AND ("machine learning" OR "stock returns" OR "asset pricing" OR "trading strategies" OR "return prediction")'),
]


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    done: set[str] = set()
    if LOG.exists():
        with LOG.open(newline="", encoding="utf-8") as fh:
            done = {r["query_id"] for r in csv.DictReader(fh) if r["source"] == "OpenAlex" and r["http_status"] == "200"}
    with LOG.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        for sid, theme, expr in SWEEPS:
            if sid in done:
                continue
            q = urllib.parse.quote(f"{expr}", safe="")
            items, cursor, status, total, pages = [], "*", 0, 0, 0
            while cursor and len(items) < CAP:
                url = (f"https://api.openalex.org/works?filter=title_and_abstract.search:{q},from_publication_date:{FROM},to_publication_date:{TO},type:article%7Cpreprint"
                       f"&per-page=200&cursor={urllib.parse.quote(cursor)}&select={OA_FIELDS}")
                status, body, _ = fetch(url)
                if status == 429:
                    time.sleep(8)
                    status, body, _ = fetch(url)
                if status != 200:
                    print(sid, "request failed", status, body[:200])
                    break
                doc = json.loads(body)
                total = doc["meta"]["count"]
                items += doc["results"]
                cursor = doc["meta"].get("next_cursor")
                pages += 1
                time.sleep(0.5)
                if not doc["results"] or len(items) >= total:
                    break
            if status != 200 and not items:
                writer.writerow([date.today().isoformat(), "OpenAlex", sid, theme, expr[:200], "boolean sweep", status, "", 0, "", "", "request failed"])
                fh.flush()
                continue
            blob = json.dumps({"meta": {"count": total}, "results": items[:CAP]}).encode()
            name = f"OpenAlex_{sid}.json"
            (RAW / name).write_bytes(blob)
            note = "" if total <= CAP else f"TRUNCATED: {total} matches, first {CAP} by relevance kept"
            writer.writerow([date.today().isoformat(), "OpenAlex", sid, theme, expr, f"boolean sweep title_and_abstract.search; {FROM}..{TO}; article|preprint; cursor paging cap {CAP}", 200, total, min(len(items), CAP), f"data/recent_lit/raw/{name}", hashlib.sha256(blob).hexdigest(), note])
            fh.flush()
            print(f"{sid} {theme}: {total} matches, kept {min(len(items), CAP)} {note}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
