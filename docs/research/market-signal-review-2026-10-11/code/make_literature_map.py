#!/usr/bin/env python3
"""Generate the counted tables for 02_LITERATURE_MAP.md from screening_log.csv.

Every number in the map comes from this script; the prose around the tables is written by hand in the document itself
(the script prints only the tables so they can be pasted and are reproducible).
"""

from __future__ import annotations

import collections
import csv
import html
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
NAMES = {
    "A": "Return predictability, anomalies, factors", "B": "Technical and price/volume signals", "C": "Machine learning and learning-to-rank",
    "D": "Time-series foundation models", "E": "Financial language models and text", "F": "Multimodal and alternative data",
    "G": "Data fusion, reliability, point-in-time data, uncertainty", "H": "Regimes, drift, signal decay", "I": "Costs, portfolios, decision quality",
    "J": "Research credibility and inference", "K": "Cross-field reliability and fusion methods", "L": "Datasets and benchmarks",
}


def main() -> None:
    rows = list(csv.DictReader((BASE / "screening_log.csv").open()))
    kept = [r for r in rows if r["decision"] in ("include", "maybe")]
    print("| Family | Topic | Included + maybe | Relevance 3 | Peer-reviewed journal | Empirical | Median year | Share 2023-2026 |")
    print("|---|---|---|---|---|---|---|---|")
    for fam, name in NAMES.items():
        sub = [r for r in kept if fam in (r["families"] or "")]
        years = sorted(int(r["year"]) for r in sub if r["year"])
        recent = sum(y >= 2023 for y in years) / max(1, len(years))
        print(f"| {fam} | {name} | {len(sub)} | {sum(r['relevance'] == '3' for r in sub)} | {sum(r['pub_status'] == 'peer_reviewed_journal' for r in sub)} "
              f"| {sum(r['evidence_type'] == 'empirical' for r in sub)} | {years[len(years) // 2]} | {recent:.0%} |")
    print()
    by_year = collections.Counter(int(r["year"]) for r in kept if r["year"])
    bins = [("1985-1999", 1985, 1999), ("2000-2009", 2000, 2009), ("2010-2019", 2010, 2019), ("2020-2022", 2020, 2022), ("2023-2026", 2023, 2026)]
    print("| Period | Included + maybe |\n|---|---|")
    for label, lo, hi in bins:
        print(f"| {label} | {sum(v for y, v in by_year.items() if lo <= y <= hi)} |")
    print()
    print("| Evidence type | Included + maybe |\n|---|---|")
    for k, v in collections.Counter(r["evidence_type"] for r in kept).most_common():
        print(f"| {k} | {v} |")
    print()
    print("| Publication status | Included + maybe |\n|---|---|")
    for k, v in collections.Counter(r["pub_status"] for r in kept).most_common():
        print(f"| {k.replace('_', ' ')} | {v} |")
    print()
    overlap = collections.Counter()
    for r in kept:
        for c in filter(None, (r["candidate_overlap"] or "").split(";")):
            overlap[c] += 1
    print("| Candidate direction | Records tagged as bearing on it |\n|---|---|")
    for k in sorted(overlap):
        print(f"| {k} | {overlap[k]} |")


if __name__ == "__main__":
    main()
