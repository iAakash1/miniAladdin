#!/usr/bin/env python3
"""Deterministic literature retrieval for the market-signal review (protocol 1.0).

Runs the query bank in queries.json against OpenAlex, Crossref, arXiv, the NBER
working-paper API and (best effort, it is rate limited without a key) Semantic
Scholar. Every request is logged to search_log.csv with the API's own reported
hit count, so every count in the review is the API's, not an estimate. Raw
responses are written under data/research/literature_raw/ (git-ignored, hashed
in the log) so the candidate set can be rebuilt without searching again.

SSRN's own search is behind bot protection (HTTP 403) and is not circumvented.
IDEAS/RePEc's search could not be parsed. Both are covered indirectly: SSRN,
NBER, CEPR and many RePEc series are DOI-registered or indexed in OpenAlex and
Crossref, and gap-filling web searches restricted to those domains are logged
separately by the screening stage.

Usage:  python3 lit_search.py [--only OPENALEX,CROSSREF,ARXIV,NBER,S2] [--limit N]
Resumable: a (source, query, page) whose raw file exists is not requested again.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]                      # docs/research/<dir> -> repository docs/
REPO = HERE.parents[3]
RAW = REPO / "data" / "research" / "literature_raw"
LOG = HERE.parent / "search_log.csv"
# No contact address is sent to any scholarly API: the "polite pool" convention is optional and the account
# owner's email is not shared with third-party services. APIs may therefore rate-limit more strictly.
UA = "OmniSignalResearch/1.0 (academic literature review; contact withheld)"
RUN_DATE = "2026-10-11"
FROM_YEAR = 1985

LOG_FIELDS = ["run_date", "source", "query_id", "family", "query", "params", "page", "http_status",
              "total_hits", "n_returned", "raw_file", "raw_sha256", "note"]


def get(url: str, *, timeout: int = 60, accept: str = "application/json", tries: int = 4) -> tuple[int, bytes]:
    """GET through curl. Python's urllib saw repeated truncated reads (IncompleteRead) from this
    network path; curl, with its own retries, does not. A 429 is returned to the caller, which
    decides whether to wait (Semantic Scholar) or log it; 5xx and transport errors are retried."""
    import subprocess
    marker = b"\n__HTTP_STATUS__:"
    last: tuple[int, bytes] = (0, b"")
    for attempt in range(tries):
        proc = subprocess.run(
            ["curl", "-s", "-L", "--compressed", "-m", str(timeout), "-A", UA, "-H", f"Accept: {accept}",
             "-w", "\n__HTTP_STATUS__:%{http_code}", url],
            capture_output=True)
        out = proc.stdout
        if marker in out:
            body, code = out.rsplit(marker, 1)
            status = int(code.decode() or 0)
        else:
            body, status = proc.stderr or b"curl failed", 0
        last = (status, body)
        if status and status < 500 and status != 408:
            return last
        time.sleep(2.0 * (attempt + 1))
    return last


def log_row(row: dict) -> None:
    new = not LOG.exists()
    with LOG.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=LOG_FIELDS, lineterminator="\n")
        if new:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in LOG_FIELDS})


def save_raw(source: str, qid: str, page: int, body: bytes, ok: bool = True) -> tuple[str, str]:
    """A failed response is kept as .err so that a rerun requests it again; only 200s become .json."""
    folder = RAW / source
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{qid}_p{page}.{'json' if ok else 'err'}"
    path.write_bytes(body)
    return str(path.relative_to(REPO)), hashlib.sha256(body).hexdigest()


def done(source: str, qid: str, page: int) -> bool:
    return (RAW / source / f"{qid}_p{page}.json").exists()


# --------------------------------------------------------------------------- OpenAlex
OPENALEX_SELECT = ("id,doi,title,publication_year,publication_date,type,cited_by_count,primary_location,"
                   "open_access,authorships,abstract_inverted_index,ids,language,referenced_works_count,biblio")


OPENALEX_EXHAUSTED = False


def openalex(q: dict, pages: int = 1) -> None:
    """Keyless OpenAlex has a small shared daily budget (10 credits per request against about 1,000 free
    credits a day, about 100 requests; resets 00:00 UTC). One page of 50 per query, and the run stops at the
    first 429 instead of burning the log with failures; rerun after the reset. A free API key would lift this
    but needs an account, which this study does not create."""
    global OPENALEX_EXHAUSTED
    for page in range(1, pages + 1):
        if OPENALEX_EXHAUSTED or done("openalex", q["id"], page):
            continue
        params = {
            "search": q["q"],
            "filter": f"from_publication_date:{FROM_YEAR}-01-01",
            "per-page": 50, "page": page, "select": OPENALEX_SELECT,
        }
        status, body = get("https://api.openalex.org/works?" + urllib.parse.urlencode(params))
        total = n = ""
        if status == 200:
            data = json.loads(body)
            total, n = data["meta"]["count"], len(data["results"])
        raw, sha = save_raw("openalex", q["id"], page, body, ok=(status == 200))
        if status == 429:
            OPENALEX_EXHAUSTED = True
        log_row({"run_date": RUN_DATE, "source": "OpenAlex", "query_id": q["id"], "family": q["f"], "query": q["q"],
                 "params": f"filter=from_publication_date:{FROM_YEAR}; per-page=50; relevance order", "page": page,
                 "http_status": status, "total_hits": total, "n_returned": n, "raw_file": raw, "raw_sha256": sha})
        time.sleep(0.25)


# --------------------------------------------------------------------------- Crossref
def crossref(q: dict) -> None:
    if done("crossref", q["id"], 1):
        return
    params = {
        "query.bibliographic": q["q"], "rows": 30,
        "filter": f"from-pub-date:{FROM_YEAR},type:journal-article",
        "select": "DOI,title,author,issued,container-title,type,abstract,is-referenced-by-count,publisher,URL",
    }
    status, body = get("https://api.crossref.org/works?" + urllib.parse.urlencode(params))
    total = n = ""
    if status == 200:
        data = json.loads(body)["message"]
        total, n = data.get("total-results", ""), len(data.get("items", []))
    raw, sha = save_raw("crossref", q["id"], 1, body, ok=(status == 200))
    log_row({"run_date": RUN_DATE, "source": "Crossref", "query_id": q["id"], "family": q["f"], "query": q["q"],
             "params": f"query.bibliographic; filter=from-pub-date:{FROM_YEAR},type:journal-article; rows=30",
             "page": 1, "http_status": status, "total_hits": total, "n_returned": n, "raw_file": raw, "raw_sha256": sha})
    time.sleep(0.4)


# --------------------------------------------------------------------------- arXiv
ARXIV_STOP = {"with", "from", "that", "this", "using", "based", "across", "return", "returns", "stock", "stocks", "model", "models", "financial", "finance"}
ARXIV_CATS = "(cat:q-fin.* OR cat:econ.EM OR cat:stat.ML OR cat:cs.LG OR cat:stat.AP OR cat:cs.CL)"


def arxiv(q: dict) -> None:
    """Up to three informative words AND-ed; if that is too narrow (<8 hits) the two most informative
    words are tried as well. Both attempts are logged (page 1 and page 2 denote attempt 1 and 2)."""
    words = [w for w in q["q"].replace('"', "").replace("-", " ").split() if len(w) > 3 and w.lower() not in ARXIV_STOP]
    for attempt, count in ((1, 3), (2, 2)):
        if done("arxiv", q["id"], attempt):
            continue
        terms = " AND ".join(f"all:{w}" for w in words[:count])
        query = terms if q["f"] == "K" else f"({terms}) AND {ARXIV_CATS}"
        params = {"search_query": query, "start": 0, "max_results": 30, "sortBy": "relevance", "sortOrder": "descending"}
        status, body = get("https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params), accept="application/atom+xml")
        text = body.decode("utf-8", "replace")
        total = ""
        n = text.count("<entry>")
        if "<opensearch:totalResults" in text:
            total = text.split("<opensearch:totalResults", 1)[1].split(">", 1)[1].split("<", 1)[0]
        raw, sha = save_raw("arxiv", q["id"], attempt, body, ok=(status == 200))
        log_row({"run_date": RUN_DATE, "source": "arXiv", "query_id": q["id"], "family": q["f"], "query": q["q"],
                 "params": (f"attempt {attempt}: first {count} informative words AND-ed; "
                            + ("no category filter" if q["f"] == "K" else "q-fin/econ.EM/stat.ML/cs.LG/stat.AP/cs.CL")
                            + "; max_results=30; relevance"), "page": attempt, "http_status": status,
                 "total_hits": total, "n_returned": n, "raw_file": raw, "raw_sha256": sha})
        time.sleep(3.3)                       # arXiv API etiquette: one request per three seconds
        if attempt == 1 and n >= 8:
            break


# --------------------------------------------------------------------------- NBER
def nber(q: dict) -> None:
    if done("nber", q["id"], 1):
        return
    params = {"page": 1, "perPage": 20, "q": q["q"]}
    status, body = get("https://www.nber.org/api/v1/working_page_listing/contentType/working_paper/_/_/search?"
                       + urllib.parse.urlencode(params))
    total = n = ""
    if status == 200:
        try:
            data = json.loads(body)
            total, n = data.get("totalResults", ""), len(data.get("results", []))
        except json.JSONDecodeError:
            pass
    raw, sha = save_raw("nber", q["id"], 1, body, ok=(status == 200))
    log_row({"run_date": RUN_DATE, "source": "NBER", "query_id": q["id"], "family": q["f"], "query": q["q"],
             "params": "working_paper listing search; perPage=20; site relevance order", "page": 1,
             "http_status": status, "total_hits": total, "n_returned": n, "raw_file": raw, "raw_sha256": sha})
    time.sleep(0.6)


# --------------------------------------------------------------------------- Semantic Scholar
def s2(q: dict) -> None:
    if done("s2", q["id"], 1):
        return
    params = {"query": q["q"], "limit": 25, "year": f"{FROM_YEAR}-",
              "fields": "title,year,venue,externalIds,citationCount,abstract,publicationTypes,openAccessPdf,authors"}
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(params)
    status, body, note = 0, b"", ""
    for attempt in range(3):
        status, body = get(url)
        if status != 429:
            break
        note = f"429 retried {attempt + 1}x"
        time.sleep(4 * (attempt + 1))
    total = n = ""
    if status == 200:
        data = json.loads(body)
        total, n = data.get("total", ""), len(data.get("data", []))
    raw, sha = save_raw("s2", q["id"], 1, body, ok=(status == 200))
    log_row({"run_date": RUN_DATE, "source": "SemanticScholar", "query_id": q["id"], "family": q["f"], "query": q["q"],
             "params": "paper/search; limit=25; unauthenticated shared pool", "page": 1, "http_status": status,
             "total_hits": total, "n_returned": n, "raw_file": raw, "raw_sha256": sha, "note": note})
    time.sleep(3.2)


SOURCES = {"OPENALEX": openalex, "CROSSREF": crossref, "ARXIV": arxiv, "NBER": nber, "S2": s2}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="OPENALEX,CROSSREF,ARXIV,NBER,S2")
    ap.add_argument("--limit", type=int, default=0, help="stop after N queries (smoke test)")
    ap.add_argument("--family", default="", help="restrict to families, e.g. AG")
    ap.add_argument("--qids", default="", help="comma-separated query ids (e.g. for the Semantic Scholar sample)")
    args = ap.parse_args()
    bank = json.loads((HERE / "queries.json").read_text())
    queries = [q for q in bank["queries"] if not args.family or q["f"] in args.family]
    if args.qids:
        wanted = set(args.qids.split(","))
        queries = [q for q in queries if q["id"] in wanted]
    if args.limit:
        queries = queries[: args.limit]
    for name in [s.strip().upper() for s in args.only.split(",") if s.strip()]:
        fn = SOURCES[name]
        for i, q in enumerate(queries, 1):
            fn(q)
            if i % 20 == 0:
                print(f"{name}: {i}/{len(queries)}", flush=True)
        print(f"{name}: finished {len(queries)} queries", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
