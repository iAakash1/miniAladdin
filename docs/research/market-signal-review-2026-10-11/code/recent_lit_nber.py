#!/usr/bin/env python3
"""Phase II continuation: a direct pass over NBER working papers (the site's own search) for the themes of the 2022-2026 update, because OpenAlex and Crossref surfaced only one NBER record.

Eight queries, 20 results each, relevance order; works dated before 2022 are kept in the raw file but only 2022 or later enter the candidate table. Appends to `recent_search_log.csv`; raw JSON under
`data/recent_lit/raw/NBER_N*.json` (git-ignored). The titles of the 2022-2026 hits are printed so that they can be read.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/recent_lit_nber.py
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
from recent_lit_search import LOG, RAW, fetch  # noqa: E402

QUERIES = [("N1", "T1", "restatement"), ("N2", "T2", "amended filings 10-K/A"), ("N3", "T3", "look-ahead bias point-in-time"), ("N4", "T6", "machine learning cross-section of stock returns"),
           ("N5", "T8", "research design choices nonstandard errors asset pricing"), ("N6", "T5", "material weakness internal control stock returns"),
           ("N7", "T4", "accounting information quality return predictability"), ("N8", "T3", "filing delay late filing stock returns")]
MONTHS = "January February March April May June July August September October November December".split()


def year_of(display: str) -> int:
    for token in display.replace(",", " ").split():
        if token.isdigit() and len(token) == 4:
            return int(token)
    return 0


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    done = set()
    if LOG.exists():
        with LOG.open(newline="", encoding="utf-8") as fh:
            done = {r["query_id"] for r in csv.DictReader(fh) if r["source"] == "NBER" and r["http_status"] == "200"}
    with LOG.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        for qid, theme, text in QUERIES:
            if qid in done:
                continue
            url = "https://www.nber.org/api/v1/working_page_listing/contentType/working_paper/_/_/search?" + urllib.parse.urlencode({"page": 1, "perPage": 20, "q": text})
            status, body, _ = fetch(url)
            total, n, name, digest = "", 0, "", ""
            recent = []
            if status == 200:
                name = f"NBER_{qid}.json"
                (RAW / name).write_bytes(body)
                digest = hashlib.sha256(body).hexdigest()
                doc = json.loads(body)
                total, n = doc.get("totalResults", ""), len(doc.get("results", []))
                recent = [r for r in doc.get("results", []) if year_of(r.get("displaydate", "")) >= 2022]
            writer.writerow([date.today().isoformat(), "NBER", qid, theme, text, "NBER working-paper site search; perPage=20; relevance", status, total, n, f"data/recent_lit/raw/{name}" if name else "", digest, f"{len(recent)} dated 2022 or later"])
            fh.flush()
            print(f"NBER {qid} '{text}': status {status}, hits {total}, returned {n}, dated 2022+: {len(recent)}", flush=True)
            for r in recent:
                print(f"    {r.get('displaydate', '')[:14]:14s} {r['title'][:100]}  {r['url']}")
            time.sleep(1.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
