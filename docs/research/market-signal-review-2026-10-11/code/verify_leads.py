#!/usr/bin/env python3
"""Phase II continuation: verify the named leads against Crossref and OpenAlex (and a title/author search where no DOI was given).

For every lead the script fetches the Crossref record (`filter=doi:`; the single-DOI endpoint ignores `select`) and the OpenAlex record, saves both raw under `data/recent_lit/leads/` (git-ignored: publishers' abstracts)
and writes `lead_verification.csv` (tracked, no abstracts): identifiers, first-online date kept apart from the issue date, citation counts, open-access status. A lead is VERIFIED only when the DOI resolves to the
title and venue the brief gave; a lead whose DOI or record cannot be found stays UNVERIFIED and is said so.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/verify_leads.py
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
from recent_lit_search import fetch  # noqa: E402  (curl-based, hard timeouts)

RAW = HERE / "data/recent_lit/leads"
OUT = HERE / "lead_verification.csv"

# id, what the brief said, DOI if given, a bibliographic string for a search when the DOI is not known
LEADS = [
    ("L1", "Cheng, Jiang, Zhao & Zhao (2025), Journal of Empirical Finance 81:101598", "10.1016/j.jempfin.2025.101598", ""),
    ("L2", "Lalwani, Meshram & Jindal, Empirical Asset Pricing via Machine Learning: The Role of Research Design Choices", "10.1111/eufm.70033", ""),
    ("L3", "Accounting vs Technical Information: What Matters More for Stock Return Predictability? (J. Int. Fin. Markets, Inst. & Money 104, 2025, 102207)", "10.1016/j.intfin.2025.102207", ""),
    ("L4", "Jo & Kim (2026), Financial Analysts Journal, Rethinking Variable Importance in Machine Learning", "10.1080/0015198X.2026.2621646", ""),
    ("L5", "Kang, Ryu & Webb (2025), Financial Innovation 11:128", "", "Kang Ryu Webb 2025 Financial Innovation 11 128"),
    ("L6", "Du & Tu (2025), Accounting & Finance 65(3):2420-2453", "10.1111/acfi.70002", ""),
    ("L7", "Trading Behavior and Price Adjustment Following Earnings Restatement Disclosures by US Multinational Corporations (J. Corporate Accounting & Finance, Dec 2025)", "10.1002/jcaf.70021", ""),
    ("L8", "Mammadova (2026), SSRN 6564098 (working paper)", "10.2139/ssrn.6564098", ""),
]
UA = "omnisignal-literature-review/1.0"


def get_json(url: str) -> tuple[int, dict | None, bytes]:
    status, body, _ = fetch(url)
    if status != 200:
        return status, None, body
    try:
        return status, json.loads(body), body
    except ValueError:
        return -1, None, body


def date_of(part: dict | None) -> str:
    if not part or not part.get("date-parts") or not part["date-parts"][0] or part["date-parts"][0][0] is None:
        return ""
    return "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate(part["date-parts"][0]))


def abstract_of(inv: dict | None) -> str:
    if not inv:
        return ""
    words = sorted(((p, w) for w, ps in inv.items() for p in ps))
    return " ".join(w for _, w in words)


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    rows = []
    for lid, brief, doi, biblio in LEADS:
        print(f"\n=== {lid}: {brief}")
        cr_item, oa_item, notes = None, None, []
        if doi:
            q = urllib.parse.quote(doi, safe="")
            status, doc, body = get_json(f"https://api.crossref.org/works?filter=doi:{q}&rows=1")
            (RAW / f"{lid}_crossref.json").write_bytes(body)
            if doc and doc["message"]["items"]:
                cr_item = doc["message"]["items"][0]
            else:
                notes.append(f"Crossref filter=doi returned status {status}, no item")
            time.sleep(0.4)
            status, doc, body = get_json(f"https://api.openalex.org/works/doi:{q}")
            (RAW / f"{lid}_openalex.json").write_bytes(body)
            if doc and doc.get("id"):
                oa_item = doc
            else:
                notes.append(f"OpenAlex works/doi returned status {status}, no record")
            time.sleep(0.4)
        else:
            status, doc, body = get_json(f"https://api.crossref.org/works?query.bibliographic={urllib.parse.quote(biblio)}&rows=5")
            (RAW / f"{lid}_crossref_search.json").write_bytes(body)
            items = (doc or {}).get("message", {}).get("items", [])
            for it in items[:5]:
                print("   candidate:", (it.get("title") or [""])[0][:90], "|", (it.get("container-title") or [""])[0][:30], "|", it.get("volume"), it.get("page") or it.get("article-number"), "|", it.get("DOI"), "| score", round(it.get("score", 0), 1))
            time.sleep(0.4)
        title = ""
        if cr_item:
            title = (cr_item.get("title") or [""])[0]
            authors = "; ".join(f"{a.get('family', '')}, {a.get('given', '')}" for a in cr_item.get("author", []))
            print("   Crossref:", title)
            print("   authors:", authors)
            print("   venue:", (cr_item.get("container-title") or [""])[0], "| vol", cr_item.get("volume"), "| issue", cr_item.get("issue"), "| page", cr_item.get("page"), "| article-number", cr_item.get("article-number"))
            print("   dates: online", date_of(cr_item.get("published-online")), "| print", date_of(cr_item.get("published-print")), "| issued", date_of(cr_item.get("issued")), "| created", cr_item.get("created", {}).get("date-time"))
            print("   type:", cr_item.get("type"), "| publisher:", cr_item.get("publisher"), "| cited by (Crossref):", cr_item.get("is-referenced-by-count"), "| references deposited:", cr_item.get("references-count"))
            print("   license:", [(x.get("URL"), x.get("content-version")) for x in cr_item.get("license", [])][:3])
            ass = [(a.get("name"), a.get("value")) for a in cr_item.get("assertion", [])][:8]
            if ass:
                print("   assertions:", ass)
            ab = (cr_item.get("abstract") or "")
            if ab:
                print("   abstract (Crossref):", ab[:1200])
        if oa_item:
            loc = oa_item.get("primary_location") or {}
            best = oa_item.get("best_oa_location") or {}
            print("   OpenAlex:", oa_item["id"], "|", oa_item.get("title"), "| pub date", oa_item.get("publication_date"), "| year", oa_item.get("publication_year"), "| cited", oa_item.get("cited_by_count"), "| refs", len(oa_item.get("referenced_works", [])))
            print("   OA:", oa_item.get("open_access", {}).get("oa_status"), "| best:", best.get("landing_page_url"), best.get("pdf_url"), "| versions", [l.get("version") for l in oa_item.get("locations", [])])
            print("   source:", (loc.get("source") or {}).get("display_name"), "| type:", oa_item.get("type"))
            ab = abstract_of(oa_item.get("abstract_inverted_index"))
            if ab and not (cr_item and cr_item.get("abstract")):
                print("   abstract (OpenAlex):", ab[:1200])
        rows.append({
            "lead": lid,
            "brief": brief,
            "doi_given": doi,
            "crossref_found": bool(cr_item),
            "openalex_found": bool(oa_item),
            "title_found": title or ((oa_item or {}).get("title") or ""),
            "venue": ((cr_item or {}).get("container-title") or [""])[0] or (((oa_item or {}).get("primary_location") or {}).get("source") or {}).get("display_name", ""),
            "volume": (cr_item or {}).get("volume", ""),
            "issue": (cr_item or {}).get("issue", ""),
            "pages_or_article": (cr_item or {}).get("page") or (cr_item or {}).get("article-number", ""),
            "published_online": date_of((cr_item or {}).get("published-online")),
            "published_print": date_of((cr_item or {}).get("published-print")),
            "issued": date_of((cr_item or {}).get("issued")),
            "openalex_publication_date": (oa_item or {}).get("publication_date", ""),
            "crossref_cited_by": (cr_item or {}).get("is-referenced-by-count", ""),
            "openalex_cited_by": (oa_item or {}).get("cited_by_count", ""),
            "oa_status": ((oa_item or {}).get("open_access") or {}).get("oa_status", ""),
            "oa_landing_page": (((oa_item or {}).get("best_oa_location") or {}).get("landing_page_url")) or "",
            "retrieved": date.today().isoformat(),
            "notes": " | ".join(notes),
        })
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("\nwrote", OUT)
    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()
    print("sha256", digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
