#!/usr/bin/env python3
"""Phase II continuation: merge the raw search responses, the citation chains and the lead records into one deduplicated candidate table, with keyword relevance scores, and print the coverage counts.

Inputs (all under `data/recent_lit/`, git-ignored because they carry publishers' abstracts): `raw/` (OpenAlex, Crossref, Crossref posted content, arXiv), `chains/` (works citing the seed restatement papers), `leads/`.
Outputs: `recent_lit_candidates.csv` (tracked; metadata only, no abstracts) and `data/recent_lit/abstracts.jsonl` (git-ignored). The score columns are keyword counts on title and abstract and decide only the order in which
I read candidates; every inclusion and exclusion is a recorded decision made on a read title or abstract (`recent_lit_screening.csv`), never on the score alone.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/merge_recent_lit.py
"""

from __future__ import annotations

import csv
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
DATA = HERE / "data/recent_lit"
OUT = HERE / "recent_lit_candidates.csv"
ABS = DATA / "abstracts.jsonl"
FROM_YEAR = 2022

KEYS = {
    # restatement / amendment / misstatement content
    "R": r"restat|10-k/a|amended (annual|10-k|filing|report)|amendments? to (the )?(annual|10-k|financial)|non-?reliance|item 4\.02|misstate|accounting error|correction of (prior|previously)|previously issued financial|stealth|little r|big r|revision restatement",
    # price / market response / predictability
    "M": r"return|market reaction|price reaction|abnormal|stock price|investor|predict|drift|underreaction|mispric|anomal|cross-section",
    # machine learning for equities
    "ML": r"machine learning|neural network|deep learning|gradient boost|random forest|lasso|elastic net|ensemble|xgboost|lightgbm|language model|transformer",
    # research design, inference, reproducibility
    "D": r"multiple testing|p-hack|nonstandard error|non-standard error|research design|replicat|reproducib|overfit|backtest|data snooping|data mining|false discover|t-stat|publication bias|specification (search|choice)|researcher degrees",
    # point-in-time, data provenance, freshness
    "P": r"point-in-time|look-?ahead|vintage|data revision|filing delay|late filing|timeliness|provenance|stale|survivorship|data leakage|information leakage|real-time data|as-reported|restated data|database discrepanc|vendor",
    # accounting information quality
    "Q": r"accounting quality|earnings quality|information quality|financial reporting quality|information risk|information uncertainty|disclosure quality|internal control|material weakness|auditor|sec enforcement|aaer|fraud",
    # text / news features
    "T": r"md&a|textual|text analysis|sentiment|news|10-k text|readability|tone",
}
KEYS = {k: re.compile(v, re.I) for k, v in KEYS.items()}
DOMAIN = re.compile(r"stock|equity|equities|return|financ|account|invest|market|firm|earnings|asset pric|portfolio|securit|audit|disclos", re.I)


def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", html.unescape(t or "").lower())


def clean(t: str) -> str:
    t = re.sub(r"<[^>]+>", " ", html.unescape(t or ""))
    return re.sub(r"\s+", " ", t).strip()


def norm_doi(d: str | None) -> str:
    d = (d or "").lower().strip()
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", d)


def abstract_of(inv: dict | None) -> str:
    if not inv:
        return ""
    return " ".join(w for _, w in sorted((p, w) for w, ps in inv.items() for p in ps))


def cr_year(item: dict) -> tuple[str, str, str]:
    def part(key: str) -> str:
        v = item.get(key)
        if v and v.get("date-parts") and v["date-parts"][0] and v["date-parts"][0][0]:
            return "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate(v["date-parts"][0]))
        return ""
    return part("published-online"), part("issued"), part("published-print")


def records() -> list[dict]:
    recs: list[dict] = []
    for f in sorted((DATA / "raw").glob("*")):
        source, _, rest = f.name.partition("_")
        qid = rest.rsplit(".", 1)[0]
        try:
            if source == "OpenAlex":
                for rank, w in enumerate(json.loads(f.read_bytes())["results"], 1):
                    loc = (w.get("primary_location") or {}).get("source") or {}
                    recs.append(dict(src=source, qid=qid, rank=rank, title=clean(w.get("title")), doi=norm_doi(w.get("doi")), year=str(w.get("publication_year") or ""), online=w.get("publication_date") or "", venue=loc.get("display_name") or "",
                                     authors="; ".join(a["author"]["display_name"] for a in (w.get("authorships") or [])[:6]), cited=w.get("cited_by_count") or 0, type=w.get("type") or "", oa=(w.get("open_access") or {}).get("oa_status") or "",
                                     oa_url=((w.get("best_oa_location") or {}).get("pdf_url") or (w.get("best_oa_location") or {}).get("landing_page_url") or ""), abstract=abstract_of(w.get("abstract_inverted_index")), oaid=w["id"].rsplit("/", 1)[-1], lang=w.get("language") or ""))
            elif source.startswith("Crossref"):
                for rank, it in enumerate(json.loads(f.read_bytes())["message"]["items"], 1):
                    online, issued, printed = cr_year(it)
                    recs.append(dict(src=source, qid=qid, rank=rank, title=clean((it.get("title") or [""])[0]), doi=norm_doi(it.get("DOI")), year=(issued or printed or online)[:4], online=online, venue=clean((it.get("container-title") or [""])[0]),
                                     authors="; ".join(f"{a.get('family', '')} {a.get('given', '')[:1]}".strip() for a in (it.get("author") or [])[:6]), cited=it.get("is-referenced-by-count") or 0, type=it.get("type") or "", oa="", oa_url="", abstract=clean(it.get("abstract")), oaid="", lang=""))
            elif source == "arXiv":
                ns = {"a": "http://www.w3.org/2005/Atom"}
                for rank, e in enumerate(ET.fromstring(f.read_bytes()).findall("a:entry", ns), 1):
                    pub = (e.findtext("a:published", "", ns) or "")[:10]
                    recs.append(dict(src=source, qid=qid, rank=rank, title=clean(e.findtext("a:title", "", ns)), doi="", year=pub[:4], online=pub, venue="arXiv", authors="; ".join((a.findtext("a:name", "", ns) or "") for a in e.findall("a:author", ns)[:6]),
                                     cited=0, type="preprint", oa="green", oa_url=(e.findtext("a:id", "", ns) or ""), abstract=clean(e.findtext("a:summary", "", ns)), oaid="", lang=""))
        except Exception as error:  # a truncated file is reported, never skipped silently
            print("PARSE FAILURE", f.name, repr(error)[:120], file=sys.stderr)
    for f in sorted((DATA / "chains").glob("cites_*.json")):
        d = json.loads(f.read_bytes())
        for rank, w in enumerate(d["results"], 1):
            loc = (w.get("primary_location") or {}).get("source") or {}
            recs.append(dict(src="OpenAlex-chain", qid=d["label"], rank=rank, title=clean(w.get("title")), doi=norm_doi(w.get("doi")), year=str(w.get("publication_year") or ""), online=w.get("publication_date") or "", venue=loc.get("display_name") or "",
                             authors="; ".join(a["author"]["display_name"] for a in (w.get("authorships") or [])[:6]), cited=w.get("cited_by_count") or 0, type=w.get("type") or "", oa=(w.get("open_access") or {}).get("oa_status") or "",
                             oa_url=((w.get("best_oa_location") or {}).get("pdf_url") or (w.get("best_oa_location") or {}).get("landing_page_url") or ""), abstract=abstract_of(w.get("abstract_inverted_index")), oaid=w["id"].rsplit("/", 1)[-1], lang=w.get("language") or ""))
    return recs


def main() -> int:
    recs = records()
    raw_counts = Counter(r["src"] for r in recs)
    groups: dict[str, dict] = {}
    by_title: dict[str, str] = {}
    for r in recs:
        if not r["title"]:
            continue
        nt = norm_title(r["title"])
        key = ("doi:" + r["doi"]) if r["doi"] else ""
        gk = by_title.get(nt) or (key if key in groups else "") or key or ("t:" + nt)
        g = groups.setdefault(gk, dict(r, queries=set(), sources=set(), dois=set(), ranks=[], oaids=set()))
        by_title.setdefault(nt, gk)
        g["queries"].add(f"{r['src']}:{r['qid']}")
        g["sources"].add(r["src"])
        if r["doi"]:
            g["dois"].add(r["doi"])
        if r["oaid"]:
            g["oaids"].add(r["oaid"])
        g["ranks"].append(r["rank"])
        for fld in ("abstract", "venue", "oa_url", "authors", "oa", "online"):
            if not g.get(fld) and r.get(fld):
                g[fld] = r[fld]
        if (r["cited"] or 0) > (g["cited"] or 0):
            g["cited"] = r["cited"]
        # prefer the journal record's year/venue over a working paper's
        if r["src"].startswith("Crossref") and r["type"] == "journal-article" and r["venue"]:
            g["venue"], g["year"] = r["venue"], r["year"] or g["year"]
    rows = []
    for gk, g in groups.items():
        text = f"{g['title']} {g['abstract']}"
        score = {k: len(rx.findall(text)) for k, rx in KEYS.items()}
        title_hit = {k: bool(rx.search(g["title"])) for k, rx in KEYS.items()}
        rows.append(dict(
            group=gk, title=g["title"], authors=g["authors"], year=g["year"], online_date=g["online"], venue=g["venue"], doi="|".join(sorted(g["dois"])), openalex_id="|".join(sorted(g["oaids"])), type=g["type"], oa_status=g["oa"], oa_url=g["oa_url"],
            cited_by=g["cited"], n_queries=len(g["queries"]), n_sources=len(g["sources"]), best_rank=min(g["ranks"]), queries=";".join(sorted(g["queries"]))[:300], has_abstract=int(bool(g["abstract"])),
            domain=int(bool(DOMAIN.search(text))), **{f"s_{k}": v for k, v in score.items()}, **{f"t_{k}": int(v) for k, v in title_hit.items()}, lang=g["lang"]))
        rows[-1]["_abstract"] = g["abstract"]
    # coverage numbers
    in_window = [r for r in rows if r["year"] and int(r["year"]) >= FROM_YEAR]
    DATA.mkdir(parents=True, exist_ok=True)
    with ABS.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({"group": r["group"], "title": r["title"], "abstract": r.pop("_abstract")}) + "\n")
    fields = [k for k in rows[0].keys()]
    rows.sort(key=lambda r: (-(r["t_R"] * 3 + r["s_R"]), -r["cited_by"]))
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    summary = {
        "raw_records_by_source": dict(raw_counts), "raw_records_total": len(recs), "distinct_works": len(rows), "distinct_works_published_2022_or_later": len(in_window),
        "works_without_abstract": sum(1 for r in rows if not r["has_abstract"]), "year_distribution": {y: n for y, n in sorted(Counter(r["year"] for r in rows).items()) if y},
        "works_in_more_than_one_source": sum(1 for r in rows if int(r["n_sources"]) > 1), "works_with_restatement_or_amendment_term_in_title": sum(1 for r in rows if r["t_R"]),
        "works_with_restatement_or_amendment_terms_in_title_or_abstract_twice_or_more": sum(1 for r in rows if r["s_R"] >= 2),
        "domain_term_present": sum(1 for r in rows if r["domain"]), "topical_keyword_present": sum(1 for r in rows if r["domain"] and (r["s_R"] or r["s_ML"] or r["s_D"] or r["s_P"] or r["s_Q"])),
    }
    (HERE / "recent_lit_merge_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print("raw records by source:", dict(raw_counts), "total", len(recs))
    print("distinct works after deduplication:", len(rows), "| published 2022 or later:", len(in_window), "| without abstract:", sum(1 for r in rows if not r["has_abstract"]))
    yc = Counter(r["year"] for r in rows)
    print("year distribution:", {y: yc[y] for y in sorted(yc) if y})
    print("restatement/amendment-specific in title:", sum(1 for r in rows if r["t_R"]), "| in title or abstract (>=2 hits):", sum(1 for r in rows if r["s_R"] >= 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
