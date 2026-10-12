#!/usr/bin/env python3
"""Phase II continuation: current literature search (2022 to 12 October 2026) across independent indexes, with a logged query bank.

Sources (all public, keyless, no contact address sent): OpenAlex (title/abstract search), Crossref (journal articles, and posted content for SSRN and NBER), arXiv (q-fin). A source that refuses or throttles is
dropped for the rest of the run and the refusal is logged; nothing is retried in a loop. Raw responses are saved under `data/recent_lit/raw/` (git-ignored: they carry publishers' abstracts); the log
`recent_search_log.csv` (tracked) records every request, its filters, hit counts and the SHA-256 of the raw file.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/recent_lit_search.py            # all queries
    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/recent_lit_search.py --only T1    # one theme

Large responses are truncated by the tool sandbox's network proxy: run with the sandbox off.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
RAW = HERE / "data/recent_lit/raw"
LOG = HERE / "recent_search_log.csv"
UA = "omnisignal-literature-review/1.0 (research use; no contact)"
FROM, TO = "2022-01-01", "2026-10-12"

# theme, id, text. Themes follow the owner's list; T0 is the direct leads and citation chains handled elsewhere.
QUERIES = [
    ("T1", "T1a", "financial restatement stock returns post-announcement"),
    ("T1", "T1b", "accounting restatement announcement long-run abnormal returns"),
    ("T1", "T1c", "earnings restatement market reaction investors"),
    ("T1", "T1d", "restatement disclosure information risk uncertainty returns"),
    ("T1", "T1e", "non-reliance Item 4.02 8-K restatement"),
    ("T1", "T1f", "restatement severity stock price reaction"),
    ("T1", "T1g", "restatements institutional investors trading short sellers"),
    ("T2", "T2a", "amended 10-K/A filings market reaction"),
    ("T2", "T2b", "10-K/A amendment stock returns"),
    ("T2", "T2c", "XBRL financial statement errors restatement"),
    ("T2", "T2d", "revision restatements little r stealth restatements"),
    ("T2", "T2e", "economic content of financial statement amendments"),
    ("T3", "T3a", "point-in-time fundamentals look-ahead bias accounting data"),
    ("T3", "T3b", "filing delay reporting lag stock returns"),
    ("T3", "T3c", "late filing NT 10-K stock return"),
    ("T3", "T3d", "data revisions backtest look-ahead bias"),
    ("T3", "T3e", "as-originally-reported versus restated financial data return predictability"),
    ("T4", "T4a", "accounting information quality stock return predictability"),
    ("T4", "T4b", "information uncertainty return predictability accounting"),
    ("T4", "T4c", "earnings quality anomaly cross-section"),
    ("T5", "T5a", "market reaction to corrections of previously issued financial statements"),
    ("T5", "T5b", "material weakness disclosure market reaction"),
    ("T5", "T5c", "SEC enforcement accounting misstatement returns"),
    ("T6", "T6a", "machine learning cross-sectional stock return prediction out-of-sample"),
    ("T6", "T6b", "empirical asset pricing machine learning replication"),
    ("T6", "T6c", "gradient boosting stock return prediction firm characteristics"),
    ("T6", "T6d", "research design choices machine learning asset pricing"),
    ("T6", "T6e", "simple linear model versus machine learning stock return prediction"),
    ("T7", "T7a", "backtest overfitting financial machine learning"),
    ("T7", "T7b", "look-ahead bias large language models finance"),
    ("T7", "T7c", "reproducibility data leakage financial machine learning"),
    ("T7", "T7d", "survivorship bias stock return predictability data"),
    ("T8", "T8a", "multiple testing factor zoo t-statistic threshold"),
    ("T8", "T8b", "anomalies replication p-hacking"),
    ("T8", "T8c", "economic significance transaction costs machine learning portfolio"),
    ("T8", "T8d", "variable importance machine learning asset pricing"),
    ("T9", "T9a", "MD&A tone predict restatements"),
    ("T9", "T9b", "10-K textual changes stock returns"),
    ("T9", "T9c", "financial news sentiment return prediction language model"),
    ("T10", "T10a", "data provenance source reliability financial data"),
    ("T10", "T10b", "stale information freshness stock returns"),
    ("T10", "T10c", "missing characteristics imputation asset pricing"),
    ("T10", "T10d", "financial data vendor discrepancies databases"),
]
ARXIV_IDS = {"T6a", "T6b", "T6c", "T6d", "T6e", "T7a", "T7b", "T7c", "T8a", "T8b", "T8c", "T8d", "T9c", "T10c"}
OA_FIELDS = ("id,doi,title,publication_year,publication_date,type,cited_by_count,primary_location,open_access,best_oa_location,authorships,abstract_inverted_index,biblio,language")
CR_FIELDS = "DOI,title,container-title,issued,published-online,published-print,volume,issue,page,author,type,abstract,is-referenced-by-count,publisher"


def fetch(url: str) -> tuple[int, bytes, dict]:
    """GET through curl with a hard overall limit: a plain urllib call can block for ever in name resolution or a trickling body."""
    import subprocess

    try:
        proc = subprocess.run(["curl", "-sS", "-m", "90", "--connect-timeout", "20", "-A", UA, "-H", "Accept-Encoding: identity", "-D", "-", "-o", "-", url],
                              capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:
        return 0, b"curl timeout", {}
    if proc.returncode != 0:
        return 0, proc.stderr[:300], {}
    head, _, body = proc.stdout.partition(b"\r\n\r\n")
    while head.startswith(b"HTTP/") and b" 100 " in head.split(b"\r\n")[0]:        # skip an interim response
        head, _, body = body.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    status = int(lines[0].split()[1])
    headers = {k.decode().strip(): v.decode().strip() for k, _, v in (line.partition(b":") for line in lines[1:]) if k}
    return status, body, headers


def done_pairs() -> set[tuple[str, str]]:
    """(source, query id) pairs already fetched with HTTP 200: a run interrupted by a sleep or a refusal resumes where it stopped."""
    if not LOG.exists():
        return set()
    with LOG.open(newline="", encoding="utf-8") as fh:
        return {(r["source"], r["query_id"]) for r in csv.DictReader(fh) if r["http_status"] == "200"}


def log_row(writer, **kw) -> None:
    writer.writerow([kw.get(k, "") for k in ("run_date", "source", "query_id", "theme", "query", "params", "http_status", "total_hits", "n_returned", "raw_file", "raw_sha256", "note")])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="run one theme (T1..T10)")
    parser.add_argument("--sleep", type=float, default=0.5)
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    new_log = not LOG.exists()
    already = done_pairs()
    dead: set[str] = set()
    with LOG.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if new_log:
            writer.writerow(["run_date", "source", "query_id", "theme", "query", "params", "http_status", "total_hits", "n_returned", "raw_file", "raw_sha256", "note"])
        for theme, qid, text in QUERIES:
            if args.only and theme != args.only:
                continue
            jobs = []
            q = urllib.parse.quote(text)
            jobs.append(("OpenAlex", f"https://api.openalex.org/works?search={q}&filter=from_publication_date:{FROM},to_publication_date:{TO},type:article%7Cpreprint&per-page=50&select={OA_FIELDS}",
                         f"search title+abstract; {FROM}..{TO}; article|preprint; per-page=50; relevance"))
            jobs.append(("Crossref", f"https://api.crossref.org/works?query={q}&filter=from-pub-date:{FROM},until-pub-date:{TO},type:journal-article&rows=40&select={CR_FIELDS}",
                         f"free-text; {FROM}..{TO}; journal-article; rows=40; relevance"))
            jobs.append(("Crossref-preprints", f"https://api.crossref.org/works?query={q}&filter=from-pub-date:{FROM},until-pub-date:{TO},type:posted-content&rows=30&select={CR_FIELDS}",
                         f"free-text; {FROM}..{TO}; posted-content (SSRN, NBER and others); rows=30; relevance"))
            if qid in ARXIV_IDS:
                terms = " AND ".join(f"all:{w}" for w in text.replace("-", " ").split() if len(w) > 3)[:300]
                aq = urllib.parse.quote(f"({terms}) AND (cat:q-fin.* OR cat:econ.EM OR cat:stat.ML) AND submittedDate:[202201010000 TO 202610122359]")
                jobs.append(("arXiv", f"https://export.arxiv.org/api/query?search_query={aq}&start=0&max_results=30&sortBy=relevance&sortOrder=descending",
                             "words AND-ed; q-fin/econ.EM/stat.ML; submitted 2022-01..2026-10-12; max_results=30; relevance"))
            for source, url, params in jobs:
                if source in dead or (source, qid) in already:
                    continue
                status, body, headers = fetch(url)
                if status == 429 or status == 403:
                    dead.add(source)
                    log_row(writer, run_date=date.today().isoformat(), source=source, query_id=qid, theme=theme, query=text, params=params, http_status=status, note=f"refused ({headers.get('Retry-After', 'no Retry-After')}); source dropped for this run")
                    fh.flush()
                    continue
                n, total = 0, ""
                raw_file, digest = "", ""
                if status == 200:
                    name = f"{source}_{qid}.{'xml' if source == 'arXiv' else 'json'}"
                    (RAW / name).write_bytes(body)
                    raw_file, digest = f"data/recent_lit/raw/{name}", hashlib.sha256(body).hexdigest()
                    try:
                        if source == "OpenAlex":
                            doc = json.loads(body)
                            n, total = len(doc["results"]), doc["meta"]["count"]
                        elif source.startswith("Crossref"):
                            doc = json.loads(body)["message"]
                            n, total = len(doc["items"]), doc["total-results"]
                        else:
                            ns = {"a": "http://www.w3.org/2005/Atom", "o": "http://a9.com/-/spec/opensearch/1.1/"}
                            root = ET.fromstring(body)
                            n, total = len(root.findall("a:entry", ns)), root.find("o:totalResults", ns).text
                    except Exception as error:  # truncated or malformed body: keep the file, log the fact
                        status = -1
                        n = 0
                        params += f"; PARSE FAILURE {error!r}"[:200]
                log_row(writer, run_date=date.today().isoformat(), source=source, query_id=qid, theme=theme, query=text, params=params, http_status=status, total_hits=total, n_returned=n, raw_file=raw_file, raw_sha256=digest)
                fh.flush()
                print(f"{source:20s} {qid:5s} status {status} hits {total} returned {n}", flush=True)
                time.sleep(args.sleep if source != "arXiv" else 3.2)
    print("dropped sources:", sorted(dead) or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
