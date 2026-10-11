#!/usr/bin/env python3
"""Targeted prior-art search for the evidence-reliability hypothesis (decision-critical, not a second review).

The broad query bank was built before the hypothesis was narrowed to *disclosure-process reliability* (filing
timeliness, staleness, amendments, late-filing notices, restatement history, missing statements) as a moderator of
return predictability. These twelve queries target that mechanism directly. Sources: Crossref (journal articles),
arXiv (finance/ML categories) and the NBER API. Every request is logged to targeted_search_log.csv; the hit lists are
written to data/targeted_hits.json (git-ignored: titles, identifiers, abstracts where the API supplies them).
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
UA = "OmniSignalResearch/1.0 (academic literature review; contact withheld)"
RUN_DATE = "2026-10-12"

QUERIES = [
    "financial statement restatements predict stock returns cross-section",
    "late filing NT 10-K stock returns predictability",
    "filing lag timeliness earnings quality returns anomaly",
    "accounting quality conditions accrual anomaly mispricing strength",
    "information uncertainty moderates anomaly returns machine learning",
    "non-reliance restatement market reaction 8-K item 4.02",
    "stale accounting information fundamentals return predictability decay time since filing",
    "reporting quality signal reliability asset pricing machine learning",
    "data quality features machine learning stock selection missing financial statements",
    "reliability of earnings signals conditional predictability earnings quality post-earnings drift",
    "amended filings 10-K/A restatement return prediction",
    "XBRL financial data quality errors implications return prediction",
]


def curl(url: str) -> tuple[int, bytes]:
    out = subprocess.run(["curl", "-s", "-L", "--compressed", "-m", "60", "-A", UA, "-w", "\n__S__:%{http_code}", url], capture_output=True).stdout
    body, _, code = out.rpartition(b"\n__S__:")
    return int(code or 0), body


def strip(t: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t or "")).strip()


def main() -> int:
    hits, log = [], []
    for i, q in enumerate(QUERIES, 1):
        sources = {
            "Crossref": "https://api.crossref.org/works?" + urllib.parse.urlencode({
                "query.bibliographic": q, "rows": 12, "filter": "from-pub-date:1995,type:journal-article",
                "select": "DOI,title,author,issued,container-title,abstract,is-referenced-by-count"}),
            "arXiv": "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({
                "search_query": "(" + " AND ".join(f"all:{w}" for w in re.findall(r"[A-Za-z]{5,}", q)[:3]) + ") AND (cat:q-fin.* OR cat:econ.EM OR cat:stat.ML OR cat:cs.LG)",
                "max_results": 8, "sortBy": "relevance"}),
            "NBER": "https://www.nber.org/api/v1/working_page_listing/contentType/working_paper/_/_/search?" + urllib.parse.urlencode({"page": 1, "perPage": 8, "q": q}),
        }
        for name, url in sources.items():
            status, body = curl(url)
            n = 0
            if status == 200:
                if name == "Crossref":
                    for r, w in enumerate(json.loads(body)["message"]["items"], 1):
                        n += 1
                        hits.append({"q": i, "src": name, "rank": r, "title": strip((w.get("title") or [""])[0]), "year": ((w.get("issued") or {}).get("date-parts") or [[None]])[0][0],
                                     "venue": strip((w.get("container-title") or [""])[0]), "id": w.get("DOI"), "abstract": strip(w.get("abstract"))})
                elif name == "arXiv":
                    for r, e in enumerate(body.decode("utf-8", "replace").split("<entry>")[1:], 1):
                        n += 1
                        g = lambda t: re.sub(r"\s+", " ", (re.search(rf"<{t}[^>]*>(.*?)</{t}>", e, re.S) or [None, ""])[1]).strip()
                        hits.append({"q": i, "src": name, "rank": r, "title": g("title"), "year": int(g("published")[:4] or 0) or None, "venue": "arXiv",
                                     "id": re.sub(r"^.*abs/", "", g("id")), "abstract": g("summary")})
                else:
                    for r, w in enumerate(json.loads(body).get("results", []), 1):
                        n += 1
                        hits.append({"q": i, "src": name, "rank": r, "title": strip(w.get("title")), "year": int((re.search(r"(\d{4})", w.get("displaydate") or "") or [0, 0])[1] or 0) or None,
                                     "venue": "NBER Working Paper", "id": w.get("url"), "abstract": strip(w.get("abstract"))})
            log.append({"run_date": RUN_DATE, "query_no": i, "query": q, "source": name, "http_status": status, "n_returned": n,
                        "sha256": hashlib.sha256(body).hexdigest()[:16]})
            time.sleep(3.3 if name == "arXiv" else 0.6)
    with (BASE / "targeted_search_log.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(log[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(log)
    (BASE / "data").mkdir(exist_ok=True)
    (BASE / "data/targeted_hits.json").write_text(json.dumps(hits))
    print(len(hits), "hits;", sum(1 for l in log if l["http_status"] != 200), "failed requests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
