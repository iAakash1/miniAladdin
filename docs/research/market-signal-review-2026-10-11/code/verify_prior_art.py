#!/usr/bin/env python3
"""Verify the metadata of the accounting-literature works cited in the novelty audit (06_PRIOR_ART_AND_NOVELTY.md).

The broad query bank and the twelve targeted queries reached the finance literature well and the canonical accounting
papers on restatements, late filing and accrual reliability only partly. Rather than cite those from memory, each work
is looked up by title and first author in Crossref; the top hit is kept only when its title shares most words with the
requested title and its first author matches. Everything requested and everything returned is written to
verified_prior_art.csv, matched or not, so a reader can see what was and was not confirmed. Nothing here reads a full
text: a verified record means the work exists with this metadata, not that its findings were checked.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import time
import urllib.parse
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
UA = "OmniSignalResearch/1.0 (academic literature review; contact withheld)"

WANTED = [  # (title as remembered, first author surname, approximate year, why it matters to EXP-012)
    ("Determinants of market reactions to restatement announcements", "Palmrose", 2004, "restatements: market reaction"),
    ("The effect of accounting restatements on earnings revisions and the estimated cost of capital", "Hribar", 2004, "restatements and cost of capital"),
    ("Predicting material accounting misstatements", "Dechow", 2011, "F-score: predicting misstatements from public data"),
    ("Accrual reliability, earnings persistence and stock prices", "Richardson", 2005, "reliability of accounting information and pricing"),
    ("Do stock prices fully reflect information in accruals and cash flows about future earnings", "Sloan", 1996, "accruals anomaly"),
    ("Causes and consequences of earnings manipulation: an analysis of firms subject to enforcement actions by the SEC", "Dechow", 1996, "earnings manipulation"),
    ("Extensions and violations of the statutory SEC form 10-K filing requirements", "Alford", 1994, "late 10-K filing"),
    ("SEC filings, regulatory deadlines, and capital market consequences", "Bartov", 2017, "filing deadlines and market consequences"),
    ("Timeliness of annual earnings announcements: some empirical evidence", "Givoly", 1982, "reporting timeliness"),
    ("Characteristics of firms correcting previously reported quarterly earnings", "Kinney", 1989, "firms that correct earnings"),
    ("Incidence and circumstances of accounting errors", "DeFond", 1991, "accounting errors"),
    ("The cost to firms of cooking the books", "Karpoff", 2008, "cost of misreporting"),
    ("Lazy prices", "Cohen", 2020, "10-K changes predict returns"),
    ("Measuring readability in financial disclosures", "Loughran", 2014, "10-K readability"),
    ("Costs of equity and earnings attributes", "Francis", 2004, "earnings quality and cost of equity"),
    ("Information uncertainty and stock returns", "Zhang", 2006, "information uncertainty and continuation"),
    ("Earnings quality and stock returns", "Chan", 2006, "earnings quality and returns (published version)"),
    ("Cross-firm return predictability and accounting quality", "Chen", 2020, "accounting quality channel"),
]


def curl(url: str) -> tuple[int, bytes]:
    out = subprocess.run(["curl", "-s", "-L", "--compressed", "-m", "60", "-A", UA, "-w", "\n__S__:%{http_code}", url], capture_output=True).stdout
    body, _, code = out.rpartition(b"\n__S__:")
    return int(code or 0), body


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", text.lower())}


def main() -> int:
    rows = []
    for title, author, year, why in WANTED:
        url = "https://api.crossref.org/works?" + urllib.parse.urlencode({
            "query.bibliographic": f"{title} {author}", "rows": 5,
            "select": "DOI,title,author,issued,container-title,type,is-referenced-by-count"})
        status, body = curl(url)
        best = None
        if status == 200:
            for item in json.loads(body)["message"]["items"]:
                found = (item.get("title") or [""])[0]
                overlap = len(words(title) & words(found)) / max(1, len(words(title)))
                first = ((item.get("author") or [{}])[0].get("family") or "")
                names = "; ".join(f"{a.get('given', '')} {a.get('family', '')}".strip() for a in (item.get("author") or [])[:8])
                year_found = ((item.get("issued") or {}).get("date-parts") or [[None]])[0][0]
                score = overlap + (0.3 if author.lower() in first.lower() else 0.0)
                if best is None or score > best[0]:
                    best = (score, overlap, found, first, year_found, (item.get("container-title") or [""])[0], item.get("DOI"), item.get("type"), item.get("is-referenced-by-count"), names)
        matched = bool(best and best[1] >= 0.7 and author.lower() in (best[3] or "").lower())
        rows.append({
            "requested_title": title, "requested_author": author, "requested_year": year, "why": why, "http_status": status, "matched": matched,
            "found_title": best[2] if best else "", "found_first_author": best[3] if best else "", "found_year": best[4] if best else "",
            "venue": best[5] if best else "", "doi": best[6] if best else "", "type": best[7] if best else "", "cited_by": best[8] if best else "",
            "authors": best[9] if best else "", "title_word_overlap": round(best[1], 2) if best else "", "retrieved": "2026-10-12"})
        time.sleep(1.0)
    with (BASE / "verified_prior_art.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{sum(r['matched'] for r in rows)} of {len(rows)} verified")
    for r in rows:
        print(("OK  " if r["matched"] else "??  "), r["requested_author"], r["requested_year"], "->", r["found_first_author"], r["found_year"], r["doi"], "|", r["found_title"][:70])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
