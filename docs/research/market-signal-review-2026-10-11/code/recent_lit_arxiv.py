#!/usr/bin/env python3
"""Phase II continuation: nine curated arXiv queries (phrase and OR semantics) that supplement the strict AND-of-all-words arXiv calls of `recent_lit_search.py`, which returned few records.

Appends to `recent_search_log.csv`; raw Atom files go to `data/recent_lit/raw/arXiv_A*.xml` (git-ignored). arXiv asks for one request every three seconds.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/recent_lit_arxiv.py
"""

from __future__ import annotations

import csv
import hashlib
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from recent_lit_search import LOG, RAW, fetch  # noqa: E402

CATS = "(cat:q-fin.* OR cat:econ.EM OR cat:stat.ML OR cat:cs.LG OR cat:stat.AP)"
WINDOW = "submittedDate:[202201010000 TO 202610122359]"
QUERIES = [
    ("A1", "T6", '(all:"machine learning" AND (all:"cross-section" OR all:"stock returns" OR all:"asset pricing") AND (all:microcap OR all:"transaction costs" OR all:"out-of-sample"))'),
    ("A2", "T7", '(all:"look-ahead" AND (all:backtest OR all:"point-in-time" OR all:financial))'),
    ("A3", "T1", '(all:restatement OR all:restated OR all:"10-K/A" OR all:misstatement)'),
    ("A4", "T3", '(all:"point-in-time" AND (all:fundamental OR all:SEC OR all:EDGAR))'),
    ("A5", "T7", '(all:"data leakage" AND (all:finance OR all:stock OR all:equity))'),
    ("A6", "T7", '(all:reproducibility AND (all:finance OR all:"asset pricing"))'),
    ("A7", "T2", '(all:EDGAR AND (all:filings OR all:XBRL) AND (all:returns OR all:prediction))'),
    ("A8", "T8", '(all:"multiple testing" AND (all:factor OR all:anomalies))'),
    ("A9", "T8", '(all:"nonstandard errors" OR all:"non-standard errors")'),
]


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    done = set()
    if LOG.exists():
        with LOG.open(newline="", encoding="utf-8") as fh:
            done = {r["query_id"] for r in csv.DictReader(fh) if r["source"] == "arXiv" and r["http_status"] == "200"}
    with LOG.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        for qid, theme, expr in QUERIES:
            if qid in done:
                continue
            q = urllib.parse.quote(f"({expr}) AND {CATS} AND {WINDOW}")
            status, body, _ = fetch(f"https://export.arxiv.org/api/query?search_query={q}&start=0&max_results=50&sortBy=relevance&sortOrder=descending")
            total, n, name, digest = "", 0, "", ""
            if status == 200:
                name = f"arXiv_{qid}.xml"
                (RAW / name).write_bytes(body)
                digest = hashlib.sha256(body).hexdigest()
                root = ET.fromstring(body)
                ns = {"a": "http://www.w3.org/2005/Atom", "o": "http://a9.com/-/spec/opensearch/1.1/"}
                total, n = root.find("o:totalResults", ns).text, len(root.findall("a:entry", ns))
            writer.writerow([date.today().isoformat(), "arXiv", qid, theme, expr, f"curated phrase/OR query; q-fin, econ.EM, stat.ML, cs.LG, stat.AP; submitted 2022-01..2026-10-12; max_results=50; relevance", status, total, n, f"data/recent_lit/raw/{name}" if name else "", digest, ""])
            fh.flush()
            print(f"arXiv {qid}: status {status}, hits {total}, returned {n}", flush=True)
            time.sleep(3.3)
    return 0


if __name__ == "__main__":
    sys.exit(main())
