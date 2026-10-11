#!/usr/bin/env python3
"""Normalise, deduplicate and rank the raw search responses into the candidate set.

Reads data/research/literature_raw/{openalex,crossref,arxiv,nber,s2}/*.json (written by lit_search.py) and
writes, next to this protocol:

  data/candidates_all.jsonl.gz   every distinct work retrieved, with its full provenance (query ids, ranks)
  data/candidates_pool.jsonl     the deterministic screening pool (rule in POOL_RULE below)
  prisma_counts.json             the identification-stage numbers for the PRISMA-style flow

Deduplication is by normalised DOI, then arXiv id, then normalised title (which merges a working-paper version
and its published version; the published version becomes the primary record and the others are kept under
`versions`). Nothing is dropped silently: every exclusion at this stage has a counted reason.
"""

from __future__ import annotations

import gzip
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
REPO = HERE.parents[3]
RAW = REPO / "data" / "research" / "literature_raw"

POOL_RULE = (
    "Domain filter first: a work must mention a finance/economics/market term in its title, abstract or venue (cross-field family K: or a fusion/reliability/uncertainty term). Then a work enters the screening pool if it is retrieved by >=2 distinct queries, OR ranks in the top 8 of any "
    "query in any source, OR has >=150 citations, OR is a seed/known-anchor record, OR is a 2023-2026 arXiv/NBER/"
    "OpenAlex record in the top 15 of any query (recent work has had no time to accumulate citations). "
    "Works with no title, published before 1985, or of a type that is not a paper/preprint/report/chapter are "
    "excluded with a counted reason."
)

OK_TYPES = {"article", "journal-article", "preprint", "posted-content", "proceedings-article", "book-chapter",
            "report", "review", "working-paper", "paper", "dissertation", "book", "other", "proceedings", "conference-paper"}


def norm_doi(doi: str | None) -> str:
    if not doi:
        return ""
    d = doi.strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    return d


def norm_title(title: str | None) -> str:
    if not title:
        return ""
    t = re.sub(r"<[^>]+>", " ", title).lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def rebuild_abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in inv.items():
        words.extend((p, word) for p in positions)
    return " ".join(w for _, w in sorted(words))


def strip_tags(text: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def load(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def records_openalex():
    for path in sorted((RAW / "openalex").glob("*_p*.json")):
        qid, page = path.stem.split("_p")
        data = load(path)
        if not data:
            continue
        for i, w in enumerate(data.get("results", [])):
            loc = (w.get("primary_location") or {})
            src = (loc.get("source") or {})
            oa = w.get("open_access") or {}
            ids = w.get("ids") or {}
            arxiv = ""
            for key in ("arxiv",):
                if ids.get(key):
                    arxiv = re.sub(r"^.*arxiv\.org/(abs/)?", "", ids[key]).split("v")[0]
            yield {
                "source": "OpenAlex", "qid": qid, "rank": (int(page) - 1) * 50 + i + 1,
                "title": w.get("title") or "", "year": w.get("publication_year"),
                "doi": norm_doi(w.get("doi")), "arxiv": arxiv, "venue": src.get("display_name") or "",
                "venue_type": src.get("type") or "", "type": w.get("type") or "",
                "authors": [(a.get("author") or {}).get("display_name", "") for a in (w.get("authorships") or [])][:12],
                "cited_by": w.get("cited_by_count") or 0,
                "abstract": rebuild_abstract(w.get("abstract_inverted_index")),
                "oa": bool(oa.get("is_oa")), "oa_url": oa.get("oa_url") or "", "openalex_id": w.get("id") or "",
                "language": w.get("language") or "", "url": loc.get("landing_page_url") or "",
            }


def records_crossref():
    for path in sorted((RAW / "crossref").glob("*_p*.json")):
        qid = path.stem.split("_p")[0]
        data = load(path)
        if not data or data.get("status") != "ok":
            continue
        for i, w in enumerate(data["message"].get("items", [])):
            issued = (w.get("issued") or {}).get("date-parts") or [[None]]
            yield {
                "source": "Crossref", "qid": qid, "rank": i + 1,
                "title": strip_tags((w.get("title") or [""])[0]), "year": (issued[0] or [None])[0],
                "doi": norm_doi(w.get("DOI")), "arxiv": "", "venue": strip_tags((w.get("container-title") or [""])[0]),
                "venue_type": "journal", "type": w.get("type") or "",
                "authors": [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in (w.get("author") or [])][:12],
                "cited_by": w.get("is-referenced-by-count") or 0, "abstract": strip_tags(w.get("abstract")),
                "oa": False, "oa_url": "", "openalex_id": "", "language": "", "url": w.get("URL") or "",
            }


def records_arxiv():
    for path in sorted((RAW / "arxiv").glob("*_p*.json")):
        qid, attempt = path.stem.split("_p")
        text = path.read_text(errors="replace")
        for i, entry in enumerate(text.split("<entry>")[1:]):
            def tag(name):
                m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", entry, re.S)
                return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
            aid = re.sub(r"^.*arxiv\.org/abs/", "", tag("id")).split("v")[0]
            published = tag("published")[:4]
            doi_m = re.search(r'<arxiv:doi[^>]*>(.*?)</arxiv:doi>', entry, re.S)
            yield {
                "source": "arXiv", "qid": qid, "rank": i + 1, "title": tag("title"),
                "year": int(published) if published.isdigit() else None,
                "doi": norm_doi(doi_m.group(1) if doi_m else ""), "arxiv": aid, "venue": "arXiv", "venue_type": "repository",
                "type": "preprint", "authors": re.findall(r"<name>(.*?)</name>", entry)[:12], "cited_by": 0,
                "abstract": tag("summary"), "oa": True, "oa_url": f"https://arxiv.org/abs/{aid}", "openalex_id": "",
                "language": "en", "url": f"https://arxiv.org/abs/{aid}",
            }


def records_nber():
    for path in sorted((RAW / "nber").glob("*_p*.json")):
        qid = path.stem.split("_p")[0]
        data = load(path)
        if not data:
            continue
        for i, w in enumerate(data.get("results", [])):
            url = w.get("url") or ""
            m = re.search(r"/papers/(w\d+)", url)
            nid = m.group(1) if m else ""
            yield {
                "source": "NBER", "qid": qid, "rank": i + 1, "title": strip_tags(w.get("title")),
                "year": int((re.search(r"(\d{4})", w.get("displaydate") or "") or [None, 0])[1] or 0) or None,
                "doi": f"10.3386/{nid}" if nid else "", "arxiv": "", "venue": "NBER Working Paper", "venue_type": "repository",
                "type": "working-paper", "authors": [strip_tags(a) for a in (w.get("authors") or [])][:12], "cited_by": 0,
                "abstract": strip_tags(w.get("abstract")), "oa": False, "oa_url": "", "openalex_id": "", "language": "en",
                "url": ("https://www.nber.org" + url) if url.startswith("/") else url, "nber_id": nid,
            }


def records_s2():
    for path in sorted((RAW / "s2").glob("*_p*.json")):
        qid = path.stem.split("_p")[0]
        data = load(path)
        if not data or "data" not in data:
            continue
        for i, w in enumerate(data["data"]):
            ext = w.get("externalIds") or {}
            yield {
                "source": "SemanticScholar", "qid": qid, "rank": i + 1, "title": w.get("title") or "", "year": w.get("year"),
                "doi": norm_doi(ext.get("DOI")), "arxiv": (ext.get("ArXiv") or ""), "venue": w.get("venue") or "",
                "venue_type": "", "type": "article", "authors": [a.get("name", "") for a in (w.get("authors") or [])][:12],
                "cited_by": w.get("citationCount") or 0, "abstract": w.get("abstract") or "", "oa": bool(w.get("openAccessPdf")),
                "oa_url": (w.get("openAccessPdf") or {}).get("url", ""), "openalex_id": "", "language": "en", "url": "",
            }


FIN_TERMS = re.compile(
    r"\b(stock|stocks|equity|equities|share price|return|returns|asset pric|portfolio|invest|trading|trader|financ|market|"
    r"securit|anomal|factor|volatil|earnings|analyst|firm|bank|fund|capital|price|forecast|credit|bond|option|derivativ|"
    r"hedge|sharpe|backtest|liquidity|risk premi|sentiment|filing|10-k|sec |edgar|macroeconomic|inflation|interest rate|"
    r"economic|econometric|accounting|disclosure|ipo|dividend|momentum|cross-section|cross section)", re.I)
CROSS_TERMS = re.compile(
    r"\b(fusion|reliab|uncertaint|conformal|selective prediction|abstention|reject option|truth discovery|crowdsourc|missing data|"
    r"missingness|provenance|calibrat|ensemble|distribution shift|concept drift|sensor|evidence synthesis|meta-analys|robust)", re.I)
FINANCE_VENUES = re.compile(r"(financ|econom|accounting|portfolio|quantitative|trading|market|invest|risk|banking|review of|"
                            r"management science|econometric|business|expert systems|information fusion|decision support|"
                            r"knowledge-based|neurocomputing|applied soft|machine learning|artificial intelligence|computational|"
                            r"ieee|acm|arxiv|nber|ssrn|statistic)", re.I)


def on_domain(p: dict, families: list[str]) -> bool:
    blob = f"{p['title']} {p['abstract']} {p['venue']}"
    if FIN_TERMS.search(blob):
        return True
    if "K" in families and CROSS_TERMS.search(blob):
        return True
    return False


PUBLISHED_RANK = {"journal-article": 0, "article": 0, "proceedings-article": 1, "book-chapter": 2, "review": 0,
                  "report": 3, "dissertation": 3, "book": 3, "posted-content": 4, "preprint": 4, "working-paper": 4}


def main() -> int:
    bank = json.loads((HERE / "queries.json").read_text())
    fam = {q["id"]: q["f"] for q in bank["queries"]}
    raw_total = Counter()
    clusters: dict[str, dict] = {}
    key_of: dict[str, str] = {}               # alias key -> cluster key

    def keys_for(r):
        ks = []
        if r["doi"]:
            ks.append("doi:" + r["doi"])
        if r["arxiv"]:
            ks.append("arxiv:" + r["arxiv"])
        nt = norm_title(r["title"])
        if len(nt) >= 25:
            ks.append("title:" + nt)
        return ks

    for gen in (records_openalex, records_crossref, records_arxiv, records_nber, records_s2):
        for r in gen():
            raw_total[r["source"]] += 1
            if not r["title"]:
                raw_total["no_title"] += 1
                continue
            ks = keys_for(r)
            if not ks:
                ks = ["anon:" + str(len(clusters))]
            ck = next((key_of[k] for k in ks if k in key_of), ks[0])
            c = clusters.setdefault(ck, {"hits": [], "versions": [], "primary": None})
            for k in ks:
                key_of.setdefault(k, ck)
            c["hits"].append((r["source"], r["qid"], r["rank"]))
            c["versions"].append(r)

    out_all, pool, reasons = [], [], Counter()
    for ck, c in clusters.items():
        vers = sorted(c["versions"], key=lambda r: (PUBLISHED_RANK.get(r["type"], 5), -len(r["abstract"]), -r["cited_by"]))
        p = dict(vers[0])
        # fill gaps from other versions
        for v in vers[1:]:
            for f in ("abstract", "doi", "arxiv", "oa_url", "venue", "year", "authors"):
                if not p.get(f) and v.get(f):
                    p[f] = v[f]
        p["cited_by"] = max(v["cited_by"] for v in vers)
        qids = sorted({h[1] for h in c["hits"]})
        p["queries"] = qids
        p["families"] = sorted({fam[q] for q in qids if q in fam})
        p["sources"] = sorted({h[0] for h in c["hits"]})
        p["best_rank"] = min(h[2] for h in c["hits"])
        p["top8"] = any(h[2] <= 8 for h in c["hits"])
        p["top15"] = any(h[2] <= 15 for h in c["hits"])
        p["n_queries"] = len(qids)
        p["versions"] = [{"source": v["source"], "type": v["type"], "doi": v["doi"], "arxiv": v["arxiv"], "venue": v["venue"],
                          "year": v["year"]} for v in vers]
        p["cluster_key"] = ck
        out_all.append(p)

        if p["year"] is None or (p["year"] or 0) < 1985:
            reasons["year_missing_or_before_1985"] += 1
            continue
        if p["type"] and p["type"] not in OK_TYPES:
            reasons[f"type_excluded:{p['type']}"] += 1
            continue
        if not on_domain(p, p["families"]):
            reasons["off_domain_no_finance_or_fusion_term"] += 1
            continue
        recent_open = (p["year"] or 0) >= 2023 and p["top15"]
        if p["n_queries"] >= 2 or p["top8"] or p["cited_by"] >= 150 or recent_open:
            pool.append(p)
        else:
            reasons["below_pool_threshold"] += 1

    out_all.sort(key=lambda p: (-p["n_queries"], p["best_rank"]))
    pool.sort(key=lambda p: (-p["n_queries"], p["best_rank"], -p["cited_by"]))
    for i, p in enumerate(pool, 1):
        p["pool_id"] = f"W{i:05d}"
    data_dir = OUT / "data"
    data_dir.mkdir(exist_ok=True)
    with gzip.open(data_dir / "candidates_all.jsonl.gz", "wt") as fh:
        for p in out_all:
            fh.write(json.dumps(p) + "\n")
    with (data_dir / "candidates_pool.jsonl").open("w") as fh:
        for p in pool:
            fh.write(json.dumps(p) + "\n")
    counts = {
        "records_retrieved_by_source": {k: v for k, v in raw_total.items() if k != "no_title"},
        "records_without_title": raw_total["no_title"],
        "distinct_works_after_deduplication": len(out_all),
        "duplicates_removed": sum(raw_total[s] for s in ("OpenAlex", "Crossref", "arXiv", "NBER", "SemanticScholar")) - raw_total["no_title"] - len(out_all),
        "excluded_before_screening": dict(reasons),
        "screening_pool": len(pool),
        "pool_rule": POOL_RULE,
    }
    (OUT / "prisma_counts.json").write_text(json.dumps(counts, indent=2))
    print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
