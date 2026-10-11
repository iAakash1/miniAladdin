#!/usr/bin/env python3
"""Generate papers.bib, papers.csv, papers.json and 03_ANNOTATED_BIBLIOGRAPHY.md for the works closest to the study.

Selection (deterministic): seed records; the canonical works listed in CANON (matched on normalised title); screened records of
relevance 3 in topic family G (data fusion, reliability, point-in-time data, uncertainty); screened relevance-3 records whose title
names look-ahead, point-in-time or revision problems; works found by the targeted searches (EXTRA); and the accounting-literature
works whose metadata was verified in verified_prior_art.csv. Duplicates (same normalised title) keep the peer-reviewed version.

Annotations are the screener's abstract-level notes unless a hand-written relation is supplied below. Nothing here claims a
full-text reading: `read_level` says what was actually read for each entry.
"""

from __future__ import annotations

import csv
import html
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

CANON_EXACT = {
    "empirical asset pricing via machine learning", "replicating anomalies", "is there a replication crisis in finance",
    "the virtue of complexity in return prediction", "machine forecast disagreement", "open source cross-sectional asset pricing",
    "a reality check for data snooping", "information uncertainty and stock returns",
    "differences of opinion and the cross section of stock returns", "the delisting bias in crsp data", "deep learning in asset pricing",
    "missing data in asset pricing panels", "information uncertainty and post earnings announcement drift",
    "cross firm return predictability and accounting quality", "the probability of backtest overfitting", "taming the factor zoo a test of new factors",
    "shrinking the cross section", "does academic research destroy stock return predictability", "analyst disagreement mispricing and liquidity",
    "data revisions and out of sample stock return predictability", "disagreement of disagreement", "can chatgpt forecast stock price movements",
}
CANON_PREFIX = ("the deflated sharpe ratio", "backtest overfitting in the machine learning era", "machine learning techniques and data for stock market forecasting",
                "empirical asset pricing via machine learning the role of research design choices", "when alpha breaks", "time series foundation models that understand data revisions",
                "information leakage from data revisions", "forecasting in the fog", "caution ahead", "assessing look ahead bias", "scaling point in time language models",
                "evaluating llms in finance requires explicit bias", "macrocast", "and the cross section of expected returns")
AUTHOR_FIX = {"Xue Chen": "Chen Xue"}      # the screening metadata inverts this author's name in some records
LOOKAHEAD = re.compile(r"look.?ahead|point.in.time|revision|vintage|survivorship|leakage", re.I)

EXTRA = [  # found by the targeted searches; abstract read where the index returned one
    {"pool_id": "T-BGP2019", "authors": ["Karim Bannouh", "Jie-Wei Geng", "Bas Peeters"], "year": 2019, "title": "Filing, Fast and Slow: Reporting Lag and Stock Returns",
     "venue": "SSRN Electronic Journal", "doi": "10.2139/ssrn.3432446", "pub_status": "working_paper_or_preprint", "read_level": "abstract (Semantic Scholar record, 2026-10-12)"},
    {"pool_id": "T-BCLY2023", "authors": ["Lisa Brooks", "Yun Cheng", "Linxiao Liu", "Michael D. Yu"], "year": 2023, "title": "The Timeliness of 10-K Filings, Financial Performance, and Stock Returns",
     "venue": "SSRN Electronic Journal", "doi": "10.2139/ssrn.4536648", "pub_status": "working_paper_or_preprint", "read_level": "abstract (Semantic Scholar record, 2026-10-12)"},
]
RELATION = {  # hand-written from the abstracts read on 2026-10-12; the keys are matched on the start of the normalised title
    "information uncertainty and stock returns": "Momentum-type continuation is stronger when information uncertainty is higher. Moderation of predictability by uncertainty is established, with firm-characteristic proxies (the idea behind contrast T2).",
    "information uncertainty and post": "Post-earnings drift is larger when information uncertainty is higher: moderation again, in an event-study setting.",
    "missing data in asset pricing panels": "Conditional-mean imputation with weighted least squares, cast in a GMM framework, for missing characteristics; improves out-of-sample predictability. EXP-012 keeps missingness as NaN and tests it as information.",
    "data revisions and out": "The consumption-wealth ratio forecasts less well when only information available at the time is used; the author attributes the gap to measurement error in unrevised data. Macro precedent for point-in-time discipline.",
    "machine forecast disagreement": "Dispersion of machine-learning forecasts as a return signal. Model disagreement, not source or filing reliability.",
    "when alpha breaks": "Two-level uncertainty for cross-sectional rankers and a decision of whether to trade. Closest abstention work (candidate E); not a reliability-of-evidence study.",
    "time series foundation models that understand data revisions": "Revision-aware forecasting for macro series with first-published targets. Macro vintages, not firm filings.",
    "information leakage from data revisions": "A forecasting gain disappears once data revisions are respected in retrospective evaluation. The mechanism the availability rule prevents here.",
    "forecasting in the fog": "Real-time versus revised data for machine-learning inflation forecasts: macro evidence that revised-data evaluation flatters ML.",
    "cross firm return predictability and accounting quality": "Returns of good-accounting-quality firms predict those of matched poor-quality firms through delayed information processing. The accounting-quality channel behind the reliability composite.",
    "filing fast and slow": "Firms that file faster earn a significant premium over slower filers; determinants include document similarity and sentiment change between reports. Direct precedent for the reporting-lag variable (filing_lag_days, lag_deterioration).",
    "the timeliness of 10 k filings": "Earlier 10-K filers have better future earnings and higher future returns; earlier filing goes with better earnings news. Second direct precedent for filing timeliness.",
    "earnings quality and stock returns": "Earnings quality and returns: whether reporting quality is priced.",
    "disagreement of disagreement": "The major investor-disagreement proxies are nearly uncorrelated with one another: a measurement-reliability finding about the proxies.",
    "can chatgpt forecast": "Language-model headline scores predict returns using post-cutoff news; addresses look-ahead and adoption decay.",
    "empirical asset pricing via machine learning the role of research design": "Research-design choices across 5,376 portfolios create nonstandard errors up to five times the standard errors in ML strategies; costs included.",
}


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", html.unescape(text).lower())).strip()


def tidy_name(name: str) -> str:
    return name.title() if name.isupper() else name


def bibkey(authors: list[str], year, title: str, taken: set[str]) -> str:
    last = re.sub(r"[^A-Za-z]", "", authors[0].split()[-1]) if authors else "Anon"
    word = next((w for w in re.findall(r"[A-Za-z]{4,}", title) if w.lower() not in {"with", "from", "that", "stock", "stocks", "returns", "return", "cross", "section"}), "Paper")
    base = f"{last}{year}{word.capitalize()}"
    key, n = base, 0
    while key in taken:
        n += 1
        key = base + chr(ord("a") + n - 1)
    taken.add(key)
    return key


def relation_for(title: str) -> str:
    n = norm(title)
    return next((v for k, v in RELATION.items() if n.startswith(k)), "")


def main() -> None:
    ledger = {r["pool_id"]: r for r in csv.DictReader((BASE / "screening_log.csv").open())}
    pool = {p["pool_id"]: p for p in map(json.loads, (BASE / "data/candidates_pool.jsonl").open())}
    chosen: dict[str, dict] = {}
    for pid, r in ledger.items():
        is_seed = str(pool[pid].get("seed")) == "True"
        if r["decision"] not in ("include", "maybe") and not (is_seed and r["decision"] == "not_screened"):
            continue          # seeds are anchors named in the brief: kept even when their batch was lost
        n = norm(r["title"])
        families = set(filter(None, (r["families"] or "").split(";"))) or set(re.findall(r"[A-L]", r["families"] or ""))
        rel3 = r["relevance"] == "3"
        if (is_seed or n in CANON_EXACT or n.startswith(CANON_PREFIX)
                or (rel3 and "G" in families) or (rel3 and LOOKAHEAD.search(r["title"]))):
            chosen[pid] = {**r, "authors": [tidy_name(a) for a in pool[pid]["authors"]], "venue": pool[pid]["venue"], "doi": pool[pid]["doi"], "arxiv": pool[pid]["arxiv"],
                           "read_level": "abstract" if r["abstract_used"] == "True" else "title and venue only"}
            if r["decision"] == "not_screened":
                chosen[pid]["read_level"] = "title and venue only (seed; its screening batch was lost)"
                chosen[pid]["relevance"] = "3"
    rows = list(chosen.values()) + [{**e, "decision": "include", "relevance": "3", "note": "", "arxiv": ""} for e in EXTRA]
    for v in csv.DictReader((BASE / "verified_prior_art.csv").open()):
        if v["matched"] == "True":
            preprint = v["type"] in ("posted-content", "report") or "SSRN" in v["venue"] or v["doi"].startswith(("10.2139/", "10.3386/"))
            rows.append({"pool_id": "V-" + v["doi"], "authors": [tidy_name(a) for a in v["authors"].split("; ")], "year": v["found_year"], "title": v["found_title"],
                         "venue": v["venue"] or "SSRN / NBER / publisher record", "doi": v["doi"], "arxiv": "",
                         "pub_status": "working_paper_or_preprint" if preprint else "peer_reviewed_journal",
                         "decision": "include", "relevance": "3", "note": f"{v['why']} (metadata verified in Crossref 2026-10-12; abstract not read)", "read_level": "metadata only"})
    # one entry per normalised title; prefer the peer-reviewed version, then the earliest
    best: dict[str, dict] = {}
    for r in rows:
        k = norm(r["title"])
        cur = best.get(k)
        rank = (r.get("pub_status") != "peer_reviewed_journal", int(r["year"] or 9999))
        if cur is None or rank < (cur.get("pub_status") != "peer_reviewed_journal", int(cur["year"] or 9999)):
            best[k] = r
    rows = sorted(best.values(), key=lambda r: (-int(r.get("relevance") or 0), -(int(r["year"] or 0)), norm(r["title"])))
    taken: set[str] = set()
    entries, table, flat = [], [], []
    for r in rows:
        authors = r["authors"] if isinstance(r["authors"], list) else str(r["authors"]).split("; ")
        title = html.unescape(r["title"]).replace("{", "").replace("}", "")
        title = title.title() if title.isupper() else title
        authors = [AUTHOR_FIX.get(a, a) for a in authors]
        key = bibkey(authors, r["year"], title, taken)
        kind = "article" if r.get("pub_status") == "peer_reviewed_journal" else "misc"
        venue = html.unescape(r.get("venue") or "")
        status = {"peer_reviewed_journal": "peer-reviewed journal article", "working_paper_or_preprint": "working paper or preprint (not peer reviewed)"}.get(r.get("pub_status"), "publication status unverified")
        lines = [f"@{kind}{{{key},", f"  title = {{{title}}},", f"  author = {{{' and '.join(authors[:12]) or 'Anonymous'}}},", f"  year = {{{r['year']}}},"]
        if venue:
            lines.append(f"  {'journal' if kind == 'article' else 'howpublished'} = {{{venue}}},")
        if r.get("doi"):
            lines.append(f"  doi = {{{r['doi']}}},")
        if r.get("arxiv"):
            lines += [f"  eprint = {{{r['arxiv']}}},", "  archivePrefix = {arXiv},"]
        lines += [f"  note = {{{status}; metadata from Crossref, arXiv, NBER or Semantic Scholar, 2026-10-11/12; read level: {r['read_level']}}},", "}"]
        entries.append("\n".join(lines))
        ident = r.get("doi") or (f"arXiv:{r['arxiv']}" if r.get("arxiv") else "")
        relation = relation_for(title) or (r.get("note") or "")
        table.append(f"| {key} | {', '.join(authors[:3])}{' et al.' if len(authors) > 3 else ''} ({r['year']}). {title[:115]} | {venue[:34]} | {ident} | {r.get('pub_status', '')} | {r['read_level']} | {relation} |")
        flat.append({"key": key, "title": title, "authors": "; ".join(authors), "year": r["year"], "venue": venue, "doi": r.get("doi") or "", "arxiv": r.get("arxiv") or "",
                     "pub_status": r.get("pub_status") or "", "read_level": r["read_level"], "relation": relation, "source_id": r["pool_id"]})
    (BASE / "papers.bib").write_text("\n\n".join(entries) + "\n")
    (BASE / "papers.json").write_text(json.dumps(flat, indent=1, ensure_ascii=False) + "\n")
    with (BASE / "papers.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(flat[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(flat)
    levels = {k: sum(1 for f in flat if f["read_level"].startswith(k)) for k in ("abstract", "title and venue", "metadata")}
    head = ("# Annotated bibliography: the works closest to the study\n\n"
            "Selection rule: `code/make_bibliography.py`. **No full text was read for any entry.** The `read level` column says what was read: the abstract "
            f"({levels['abstract']} entries), only the title and venue ({levels['title and venue']}, where the index returned no abstract), or only verified metadata "
            f"({levels['metadata']}, the accounting works whose existence and bibliographic details were confirmed in Crossref). A hand-written relation is given where the "
            "abstract was read closely for the novelty comparison; elsewhere the text is the automated screener's note. Publication status comes from the venue metadata "
            "(a preprint is not assumed to have been published). The complete screened ledger is `screening_log.csv`.\n\n"
            f"{len(flat)} works.\n\n| Key | Citation | Venue | Identifier | Status | Read level | Relation to the study / note |\n|---|---|---|---|---|---|---|\n")
    (BASE / "03_ANNOTATED_BIBLIOGRAPHY.md").write_text(head + "\n".join(table) + "\n")
    print(len(flat), "entries", levels)


if __name__ == "__main__":
    main()
