#!/usr/bin/env python3
"""Phase II continuation: citation chains from the older restatement literature into 2022-2026, through OpenAlex.

Step 1 resolves each seed paper by title (the top three hits are shown and one is chosen by first-author surname and year; an unresolved seed is listed, never skipped silently).
Step 2 fetches every work published 2022-01-01..2026-10-12 that cites the seed (`cites:` filter, cursor paging). Step 3 (`--backward`) reads the reference lists of the modern restatement papers that were
found and counts which works they cite most, which exposes anything the keyword searches missed.

Raw responses go to `data/recent_lit/chains/` (git-ignored); `citation_chain_log.csv` (tracked) records seeds, resolved identifiers and counts.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/citation_chains.py
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
from recent_lit_search import FROM, OA_FIELDS, TO, fetch  # noqa: E402

RAW = HERE / "data/recent_lit/chains"
LOG = HERE / "citation_chain_log.csv"

# label, title to search, first-author surname, year (the year of the version I mean; OpenAlex may carry the working paper under another year)
SEEDS = [
    ("FS2008", "After a Restatement: Long-Run Market and Investor Response", "Frieder", 2008),
    ("PRS2004", "Determinants of market reactions to restatement announcements", "Palmrose", 2004),
    ("HJ2004", "Incorrect accounting estimates, accounting restatements and the cost of capital", "Hribar", 2004),
    ("KS2010", "Accounting restatements and information risk", "Kravet", 2010),
    ("BGH2011", "Do investors see through mistakes in reported earnings?", "Bardos", 2011),
    ("FST2009", "Stealth disclosure of accounting restatements", "Files", 2009),
    ("GBRS2012", "Market reaction to restatements long-run performance", "Gondhalekar", 2012),
    ("KLM2008", "The cost to firms of cooking the books", "Karpoff", 2008),
    ("KKLM2017", "Proxies and databases in financial misconduct research", "Karpoff", 2017),
    ("HLM2008", "The importance of distinguishing errors from irregularities in restatement research", "Hennes", 2008),
    ("PY2010", "An analysis of the underlying causes attributed to restatements", "Plumlee", 2010),
    ("DHW2006", "The reputational penalty for aggressive accounting: earnings restatements and management turnover", "Desai", 2006),
    ("GJJ2008", "The contagion effects of accounting restatements", "Gleason", 2008),
    ("AZZ2015", "The economic consequences of financial restatements: evidence from the market for corporate control", "Amel-Zadeh", 2015),
    ("BK2006", "Do executive stock options generate incentives for earnings management? Evidence from accounting restatements", "Burns", 2006),
    ("CCNL2020", "Lazy prices", "Cohen", 2020),
    ("MENK2024", "Nonstandard errors", "Menkveld", 2024),
    ("HXZ2020", "Replicating anomalies", "Hou", 2020),
    ("BGPR2020", "Detecting accounting fraud in publicly traded US firms using a machine learning approach", "Bao", 2020),
    ("DGLS2011", "Predicting material accounting misstatements", "Dechow", 2011),
]


def get(url: str) -> tuple[int, dict | None, bytes]:
    for attempt in range(3):
        status, body, _ = fetch(url)
        if status == 200:
            try:
                return status, json.loads(body), body
            except ValueError:
                return -1, None, body
        if status == 429:
            time.sleep(5 * (attempt + 1))
            continue
        break
    return status, None, body


def main() -> int:
    backward = "--backward" in sys.argv
    RAW.mkdir(parents=True, exist_ok=True)
    new_log = not LOG.exists()
    with LOG.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if new_log:
            writer.writerow(["run_date", "seed", "title_searched", "resolved_openalex_id", "resolved_title", "resolved_year", "resolved_first_author", "seed_cited_by", "n_citing_2022_2026", "raw_file", "raw_sha256", "note"])
        if backward:
            return backward_pass()
        for label, title, surname, year in SEEDS:
            q = urllib.parse.quote(title)
            status, doc, body = get(f"https://api.openalex.org/works?search={q}&per-page=5&select=id,doi,title,publication_year,cited_by_count,authorships")
            time.sleep(0.4)
            picked = None
            print(f"\n[{label}] {title}")
            for w in (doc or {}).get("results", [])[:5]:
                first = (w["authorships"][0]["author"]["display_name"] if w.get("authorships") else "")
                print(f"    {w['id'].rsplit('/', 1)[-1]} | {w['publication_year']} | {first} | cited {w['cited_by_count']} | {w['title'][:80]}")
                if picked is None and surname.lower() in first.lower() and abs((w["publication_year"] or 0) - year) <= 3:
                    picked = w
            if picked is None:
                print("    UNRESOLVED")
                writer.writerow([date.today().isoformat(), label, title, "", "", "", "", "", "", "", "", "unresolved: no top-5 hit matches surname and year"])
                fh.flush()
                continue
            wid = picked["id"].rsplit("/", 1)[-1]
            items, cursor, pages = [], "*", 0
            while cursor and pages < 5:
                url = f"https://api.openalex.org/works?filter=cites:{wid},from_publication_date:{FROM},to_publication_date:{TO}&per-page=200&cursor={urllib.parse.quote(cursor)}&select={OA_FIELDS}"
                status, doc, body = get(url)
                time.sleep(0.4)
                if not doc:
                    print("    chain request failed", status)
                    break
                items += doc["results"]
                cursor = doc["meta"].get("next_cursor")
                pages += 1
                if len(items) >= doc["meta"]["count"]:
                    break
            blob = json.dumps({"seed": wid, "label": label, "results": items}).encode()
            name = f"cites_{label}_{wid}.json"
            (RAW / name).write_bytes(blob)
            print(f"    -> {wid}: {len(items)} citing works 2022-2026 (OpenAlex count {doc['meta']['count'] if doc else '?'})")
            writer.writerow([date.today().isoformat(), label, title, wid, picked["title"], picked["publication_year"], picked["authorships"][0]["author"]["display_name"] if picked.get("authorships") else "", picked["cited_by_count"], len(items), f"data/recent_lit/chains/{name}", hashlib.sha256(blob).hexdigest(), ""])
            fh.flush()
    return 0


def backward_pass() -> int:
    """Not used until the modern restatement papers are screened; see screen_candidates.py."""
    print("backward pass runs from screen_candidates.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
