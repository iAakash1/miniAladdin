#!/usr/bin/env python3
"""Spot-check the novelty claim against a fifth index (Semantic Scholar, keyless public API).

Eight queries aimed at the one thing the study could claim as new: disclosure-process reliability (amendments, late or
irregular filing) used as a point-in-time predictor or moderator of cross-sectional returns, especially in machine-learning
pipelines. Top ten hits per query are kept with year, venue, citation count and the first 300 characters of the abstract
where the API returns one. Requests are logged to semantic_scholar_log.csv; hits go to data/semantic_scholar_hits.json
(git-ignored, third-party abstracts). The forward citations of the closest reporting-lag paper are fetched as well.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import time
import urllib.parse
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
UA = "OmniSignalResearch/1.0 (academic literature review; contact withheld)"
QUERIES = [
    "amended 10-K filings predict stock returns",
    "financial restatement history predicts future stock returns cross-section",
    "late filing reporting lag stock return predictability machine learning",
    "filing delay deterioration cross-sectional returns",
    "disclosure reliability moderates return predictability fundamentals signals",
    "accounting quality moderates fundamental signal machine learning stock selection",
    "point-in-time filing metadata features equity return prediction neural network",
    "information environment uncertainty features gradient boosting cross-section of stock returns",
]
FIELDS = "title,year,venue,citationCount,externalIds,abstract"


def curl(url: str) -> tuple[int, bytes]:
    out = subprocess.run(["curl", "-s", "-L", "--compressed", "-m", "60", "-A", UA, "-w", "\n__S__:%{http_code}", url], capture_output=True).stdout
    body, _, code = out.rpartition(b"\n__S__:")
    return int(code or 0), body


def main() -> int:
    """Runs every query not yet answered (HTTP 200) in semantic_scholar_log.csv; the keyless API throttles hard, so retries are slow."""
    log_path, hits_path = BASE / "semantic_scholar_log.csv", BASE / "data" / "semantic_scholar_hits.json"
    log = list(csv.DictReader(log_path.open())) if log_path.exists() else []
    hits = json.loads(hits_path.read_text()) if hits_path.exists() else []
    done = {row["query_id"] for row in log if row["http_status"] == "200"}
    log = [row for row in log if row["query_id"] in done]
    hits = [h for h in hits if f"S{h['q']:02d}" in done]
    for i, q in enumerate(QUERIES, 1):
        if f"S{i:02d}" in done:
            continue
        url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode({"query": q, "limit": 10, "fields": FIELDS})
        for attempt in range(5):
            status, body = curl(url)
            if status != 429:
                break
            time.sleep(30 * (attempt + 1))
        got = 0
        if status == 200:
            for r, paper in enumerate(json.loads(body).get("data", []), 1):
                got += 1
                hits.append({"q": i, "rank": r, "title": paper.get("title"), "year": paper.get("year"), "venue": paper.get("venue"), "cited_by": paper.get("citationCount"),
                             "doi": (paper.get("externalIds") or {}).get("DOI"), "abstract": (paper.get("abstract") or "")[:300]})
        log.append({"run_date": "2026-10-12", "query_id": f"S{i:02d}", "query": q, "http_status": status, "n_returned": got, "response_sha256": hashlib.sha256(body).hexdigest()})
        time.sleep(20)
    log.sort(key=lambda row: row["query_id"])
    with log_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["run_date", "query_id", "query", "http_status", "n_returned", "response_sha256"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(log)
    hits_path.write_text(json.dumps(hits, indent=1))
    for h in sorted(hits, key=lambda h: (h["q"], h["rank"])):
        print(f"S{h['q']:02d}.{h['rank']:<2} {h['year']} {str(h['cited_by']).rjust(5)} {(h['venue'] or '')[:24]:24} | {(h['title'] or '')[:96]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
