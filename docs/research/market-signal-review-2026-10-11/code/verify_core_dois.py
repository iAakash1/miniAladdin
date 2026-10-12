#!/usr/bin/env python3
"""Phase II continuation: Crossref metadata for the core papers of the 2022-2026 matrix, so that the online-publication date is recorded apart from the issue year and a retraction notice is not missed.

One request per DOI (`filter=doi:`; sequential, with back-off on HTTP 429). Raw responses go under `data/recent_lit/core/` (git-ignored); `recent_core_crossref.csv` (tracked, no abstracts) holds the facts.
A DOI that Crossref does not know (arXiv, some SSRN and OSF records) is listed with `crossref_found=False`; nothing is guessed.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/verify_core_dois.py
"""

from __future__ import annotations

import csv
import json
import sys
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from recent_lit_search import fetch  # noqa: E402

RAW = HERE / "data/recent_lit/core"
OUT = HERE / "recent_core_crossref.csv"

DOIS = """10.1111/jbfa.70012 10.2308/tar-2018-0385 10.2308/tar-2019-0654 10.2139/ssrn.4571695 10.1111/acfi.70281 10.2139/ssrn.6564098 10.1002/jcaf.70021 10.1108/jaee-12-2024-0539
10.2308/horizons-2025-176 10.2139/ssrn.5118253 10.1016/j.adiac.2025.100832 10.2139/ssrn.7536681 10.2139/ssrn.6932478 10.2139/ssrn.6881278 10.2139/ssrn.6881038 10.2308/tar-2023-0073
10.1287/mnsc.2022.4627 10.17605/osf.io/5u9pf 10.1007/s11142-026-09979-8 10.2139/ssrn.7415198 10.1111/eufm.70033 10.1016/j.jempfin.2025.101598 10.1016/j.intfin.2025.102207
10.1080/0015198X.2026.2621646 10.1186/s40854-025-00870-0 10.1111/acfi.70002 10.1287/mnsc.2022.4449 10.1111/jofi.13337 10.1016/j.jempfin.2024.101517 10.1111/jofi.13249 10.1093/rfs/hhae029
10.1080/0015198x.2024.2388024 10.2139/ssrn.5185155 10.2139/ssrn.5031755 10.1111/1475-679x.70058 10.1016/j.jacceco.2022.101573 10.35631/aijbaf.824001 10.2139/ssrn.6908572
10.2308/accr.2008.83.1.83 10.2308/accr.2009.84.5.1495 10.1177/0148558X21989915 10.1108/MF-05-2019-0247 10.1002/jcaf.22665""".split()


def date_of(part: dict | None) -> str:
    if not part or not part.get("date-parts") or not part["date-parts"][0] or part["date-parts"][0][0] is None:
        return ""
    return "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate(part["date-parts"][0]))


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    rows = []
    for doi in DOIS:
        q = urllib.parse.quote(doi, safe="")
        item = None
        for attempt in range(4):
            status, body, _ = fetch(f"https://api.crossref.org/works?filter=doi:{q}&rows=1")
            if status == 429:
                time.sleep(6 * (attempt + 1))
                continue
            break
        if status == 200:
            (RAW / (doi.replace("/", "_") + ".json")).write_bytes(body)
            items = json.loads(body)["message"]["items"]
            item = items[0] if items else None
        a = {x.get("name"): x.get("value") for x in (item or {}).get("assertion", [])}
        rows.append({
            "doi": doi, "crossref_found": bool(item), "http_status": status,
            "title": " ".join(((item or {}).get("title") or [""])[0].split()), "venue": " ".join(((item or {}).get("container-title") or [""])[0].split()),
            "volume": (item or {}).get("volume", ""), "issue": (item or {}).get("issue", ""), "pages": (item or {}).get("page") or (item or {}).get("article-number", ""),
            "published_online": date_of((item or {}).get("published-online")), "published_print": date_of((item or {}).get("published-print")), "issued": date_of((item or {}).get("issued")),
            "created": ((item or {}).get("created") or {}).get("date-time", "")[:10], "received": a.get("received", ""), "accepted": a.get("accepted", ""),
            "type": (item or {}).get("type", ""), "publisher": (item or {}).get("publisher", ""), "cited_by_crossref": (item or {}).get("is-referenced-by-count", ""),
            "update_notices": json.dumps((item or {}).get("update-to") or (item or {}).get("relation", {}).get("is-retracted-by") or "", ensure_ascii=False)[:160],
        })
        print(f"{status} {doi:38s} online={rows[-1]['published_online'] or '-':10s} print={rows[-1]['published_print'] or '-':8s} issued={rows[-1]['issued'] or '-':10s} | {rows[-1]['title'][:60]}", flush=True)
        time.sleep(0.8)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("wrote", OUT, len(rows), "rows;", sum(1 for r in rows if not r["crossref_found"]), "not found in Crossref")
    return 0


if __name__ == "__main__":
    sys.exit(main())
