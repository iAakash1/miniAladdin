"""Point-in-time security master, version 3 - CIK-centred, evidence-graded, never back-dated.

Identity is a SEC CIK; a ticker is a label that a security wears for a dated window.  The window comes
from dated price data, the CIK link from the SEC current ticker map or, where that fails, from exact
normalised-name evidence in dated filings, and every link is then *tested* against the filings
themselves before it is graded.  The current ticker map may bootstrap a mapping; it never creates a
historical effective date.  OpenFIGI is not used as authority.

Evidence grades for a (ticker window, CIK) link:

* ``A_CONFIRMED``   - the CIK filed periodic reports near both ends of the window AND a filing-time name
  of that CIK (current, former, or dated ``formerNames``) equals the vendor security name after
  normalisation;
* ``B_CONSISTENT``  - filings span the window, no independent name confirmation;
* ``C_PARTIAL``     - filings cover only part of the window (an acquisition, a late registrant, or reuse);
* ``X_CONTRADICTED``- the CIK files periodic reports but only long after the window starts: a different
  issuer wore the ticker earlier (ticker reuse), or the issuer re-domiciled under a new CIK;
* ``D_NO_PERIODIC_FILINGS`` - the CIK has no 10-K/10-Q at all in the registry (a foreign private issuer or a
  fund): the link may be right but there is no periodic-filing evidence, so no fundamentals can be attached.

A window that the current CIK does not cover at its start is first offered to a *predecessor* CIK: exactly
one other CIK with the same normalised issuer name whose filings end within a year of the successor's first
filing.  That link is graded ``B_CONSISTENT`` with method ``SUCCESSOR_NAME_CONTINUITY`` and the early window
alone; the successor keeps the rest.  A different-name predecessor (Google -> Alphabet) is not guessed.

Only A and B count toward ``security_master_pit``; C, D and X are reported, never silently used.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.request
from dataclasses import dataclass
from datetime import date as Date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

SECURITY_MASTER_VERSION = "security-master-v3"
FRENCH_BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp"
FRENCH_FILES = {"ff12": "Siccodes12.zip", "ff17": "Siccodes17.zip", "ff48": "Siccodes48.zip"}
USER_AGENT = "miniAladdin-research aakashjawle101@gmail.com"
EVIDENCE_TOLERANCE_DAYS = 400
GAP_SPLIT_DAYS = 250

_SUFFIX = re.compile(
    r"\b(INCORPORATED|INC|CORPORATION|CORP|COMPANY|CO|LIMITED|LTD|PLC|LLC|LP|L P|NV|N V|SA|S A|AG|SE|HOLDINGS?|GROUP|THE|"
    r"NEW|DE|DEL|MD|PA|NY|NJ|OH|CA|TX|VA)\b")
_SHARE_WORDS = re.compile(
    r"\b(COMMON STOCK|COMMON SHARES?|ORDINARY SHARES?|CLASS [A-Z]|SERIES [A-Z]|DEPOSITARY SHARES?|ADS|ADR|"
    r"AMERICAN DEPOSITARY SHARES?|SHARES|STOCK|UNITS?|WARRANTS?|BENEFICIAL INTEREST)\b")


def normalize_ticker(ticker: str) -> str:
    """SEC writes share classes with a hyphen (BRK-B); the price vendor uses a dot (BRK.B)."""
    return re.sub(r"[./\s]", "-", str(ticker).strip().upper())


def normalize_name(name: Any) -> str:
    """Conservative issuer-name key: drop share-class words, state suffixes, punctuation, legal forms."""
    if name is None or (isinstance(name, float) and np.isnan(name)):
        return ""
    text = str(name).upper()
    text = re.sub(r"/[A-Z]{1,3}/?", " ", text)          # EDGAR state suffixes such as /DE/
    text = text.split(" - ")[0]
    text = re.sub(r"[^A-Z0-9& ]", " ", text.replace("&", " AND "))
    text = _SHARE_WORDS.sub(" ", text)
    text = _SUFFIX.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def security_id(cik: int, class_key: str = "") -> str:
    """Stable identity from the CIK (plus a share-class key only where one CIK has several listings)."""
    return "sec-" + hashlib.sha256(f"cik:{int(cik)}:{class_key}".encode()).hexdigest()[:20]


# ── industry classification ──────────────────────────────────────────────────

def parse_french_sic(text: str) -> list[dict[str, Any]]:
    """Parse a Kenneth French SIC-to-industry file into (industry index, code, name, sic range) rows."""
    rows, current = [], None
    for line in text.splitlines():
        header = re.match(r"^\s*(\d+)\s+(\S+)\s+(.*\S)?\s*$", line)
        span = re.match(r"^\s*(\d{4})-(\d{4})", line)
        if span and current:
            rows.append({**current, "sic_low": int(span.group(1)), "sic_high": int(span.group(2))})
        elif header and not span:
            current = {"index": int(header.group(1)), "code": header.group(2), "label": (header.group(3) or "").strip()}
    return rows


def french_residual(text: str) -> Optional[str]:
    """The residual industry ('Other') named in a French file's headers, even when it lists no ranges (FF12 does not)."""
    for line in text.splitlines():
        header = re.match(r"^\s*(\d+)\s+(\S+)\s+(.*\S)?\s*$", line)
        if header and not re.match(r"^\s*\d{4}-\d{4}", line) and header.group(2).lower() == "other":
            return header.group(2)
    return None


def french_lookup(rows: Sequence[Mapping[str, Any]], residual: Optional[str] = None) -> Callable[[Any], Optional[str]]:
    """First matching range wins, as in the published files; a SIC in no range is the residual industry where French defines one."""
    table = sorted(rows, key=lambda r: (r["sic_low"], r["sic_high"]))
    other = residual

    def lookup(sic: Any) -> Optional[str]:
        if sic is None or pd.isna(sic):
            return None
        value = int(sic)
        for row in table:
            if row["sic_low"] <= value <= row["sic_high"]:
                return row["code"]
        return other

    return lookup


def load_french_maps(directory: Path) -> tuple[dict[str, Callable[[Any], Optional[str]]], dict[str, str]]:
    import zipfile

    maps, hashes = {}, {}
    for name, filename in FRENCH_FILES.items():
        path = Path(directory) / filename
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        with zipfile.ZipFile(path) as archive:
            member = next(m for m in archive.namelist() if m.lower().endswith(".txt"))
            text = archive.read(member).decode("latin-1")
            maps[name] = french_lookup(parse_french_sic(text), french_residual(text))
    return maps, hashes


def download_french(directory: Path) -> dict[str, str]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, filename in FRENCH_FILES.items():
        target = directory / filename
        if not target.exists():
            request = urllib.request.Request(f"{FRENCH_BASE}/{filename}", headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                target.write_bytes(response.read())
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    return hashes


def classification_intervals(registry: pd.DataFrame, identities: pd.DataFrame,
                             maps: Mapping[str, Callable[[Any], Optional[str]]], *, version: str) -> pd.DataFrame:
    """SIC as of each filing (the SEC states it is the code in force at the filing date), as dated intervals.

    One row per change of SIC; the interval closes one microsecond before the next change.  A repeated
    identical SIC opens nothing.  The last interval is open-ended (effective_to null), not extended by
    assumption past the last filing that evidences it - `evidenced_until` records that filing.
    """
    filings = registry.dropna(subset=["sic"]).sort_values(["cik", "accepted_at", "adsh"], kind="stable").copy()
    filings["sic"] = filings["sic"].astype(int)
    changed = filings[filings.groupby("cik")["sic"].shift().ne(filings["sic"])].copy()
    last_seen = filings.groupby("cik")["accepted_at"].max()
    changed["effective_from"] = pd.to_datetime(changed["accepted_at"])
    changed["effective_to"] = changed.groupby("cik")["effective_from"].shift(-1) - pd.Timedelta(microseconds=1)
    changed["evidenced_until"] = changed["cik"].map(last_seen)
    for level in ("ff12", "ff17", "ff48"):
        changed[level] = changed["sic"].map(maps[level])
    merged = changed.merge(identities[["security_id", "cik"]].drop_duplicates(), on="cik", how="inner")
    merged["source_accession"] = merged["adsh"]
    merged["mapping_version"] = version
    return merged[["security_id", "cik", "sic", "ff12", "ff17", "ff48", "effective_from", "effective_to",
                   "evidenced_until", "source_accession", "mapping_version"]].reset_index(drop=True)


# ── SEC APIs with a polite, cached fetch ─────────────────────────────────────

def fetch_json(url: str, cache: Path, *, pause: float = 0.13, timeout: int = 60,
               opener: Optional[Callable[[str], bytes]] = None) -> Optional[dict[str, Any]]:
    """GET one SEC JSON document at <= ~7.5 requests/second with an on-disk cache.  None on 404."""
    cache = Path(cache)
    if cache.exists():
        return json.loads(cache.read_text())
    try:
        if opener:
            body = opener(url)
        else:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"_status": 404}))
            return {"_status": 404}
        raise
    finally:
        time.sleep(pause)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(body)
    return json.loads(body)


def submissions(cik: int, raw_dir: Path, **kw: Any) -> Optional[dict[str, Any]]:
    return fetch_json(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json",
                      Path(raw_dir) / "submissions" / f"CIK{int(cik):010d}.json", **kw)


def dei_shares_concept(cik: int, raw_dir: Path, **kw: Any) -> Optional[dict[str, Any]]:
    return fetch_json(
        f"https://data.sec.gov/api/xbrl/companyconcept/CIK{int(cik):010d}/dei/EntityCommonStockSharesOutstanding.json",
        Path(raw_dir) / "dei_shares" / f"CIK{int(cik):010d}.json", **kw)


def name_history(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Dated names: the current name (open-ended) plus every `formerNames` entry with its dates."""
    rows = [{"name": payload.get("name"), "name_from": None, "name_to": None, "kind": "CURRENT"}]
    for item in payload.get("formerNames", []) or []:
        rows.append({"name": item.get("name"), "name_from": (item.get("from") or "")[:10] or None,
                     "name_to": (item.get("to") or "")[:10] or None, "kind": "FORMER"})
    return rows


EXIT_FORMS = {"25": "EXCHANGE_DELISTING_FORM_25", "25-NSE": "EXCHANGE_DELISTING_FORM_25", "15-12B": "DEREGISTRATION_FORM_15",
              "15-12G": "DEREGISTRATION_FORM_15", "15-15D": "DEREGISTRATION_FORM_15", "15F-12B": "FOREIGN_DEREGISTRATION",
              "15F-12G": "FOREIGN_DEREGISTRATION", "15F-15D": "FOREIGN_DEREGISTRATION"}
EXIT_8K_ITEMS = {"3.01": "8K_DELISTING_NOTICE", "2.01": "8K_ACQUISITION_COMPLETED", "1.03": "8K_BANKRUPTCY"}


def exit_evidence(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Dated exit-related filings from the recent-filings block of a submissions document."""
    recent = (payload.get("filings") or {}).get("recent") or {}
    forms, dates = recent.get("form", []), recent.get("filingDate", [])
    accessions, items = recent.get("accessionNumber", []), recent.get("items", [])
    out = []
    for i, form in enumerate(forms):
        if form in EXIT_FORMS:
            out.append({"form": form, "kind": EXIT_FORMS[form], "event_date": dates[i], "accession": accessions[i]})
        elif form == "8-K":
            for code in str(items[i] if i < len(items) else "").split(","):
                if code.strip() in EXIT_8K_ITEMS:
                    out.append({"form": form, "kind": EXIT_8K_ITEMS[code.strip()], "event_date": dates[i], "accession": accessions[i]})
    return out


# ── resolution ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PriceWindow:
    ticker: str
    first: Date
    last: Date
    segments: tuple[tuple[Date, Date], ...]


def price_windows(ohlcv: pd.DataFrame) -> dict[str, PriceWindow]:
    """Per-ticker first/last price date and contiguous segments (a gap > 250 days splits a window: possible reuse)."""
    out = {}
    for ticker, group in ohlcv.groupby("symbol"):
        days = sorted(pd.to_datetime(group["date"]).dt.date.unique())
        segments, start = [], days[0]
        for previous, current in zip(days[:-1], days[1:]):
            if (current - previous).days > GAP_SPLIT_DAYS:
                segments.append((start, previous))
                start = current
        segments.append((start, days[-1]))
        out[ticker] = PriceWindow(ticker, days[0], days[-1], tuple(segments))
    return out


def name_index(registry: pd.DataFrame, histories: Optional[Mapping[int, list[dict[str, Any]]]] = None) -> dict[str, set[int]]:
    """normalised filing-time / former name -> set of CIKs that carried it."""
    index: dict[str, set[int]] = {}
    for column in ("name", "former"):
        for cik, value in zip(registry["cik"], registry[column]):
            key = normalize_name(value)
            if key:
                index.setdefault(key, set()).add(int(cik))
    for cik, rows in (histories or {}).items():
        for row in rows:
            key = normalize_name(row["name"])
            if key:
                index.setdefault(key, set()).add(int(cik))
    return index


def filing_span(registry: pd.DataFrame) -> pd.DataFrame:
    grouped = registry.groupby("cik")["accepted_at"].agg(first_filing="min", last_filing="max", filings="size")
    return grouped


def grade_link(window: tuple[Date, Date], span: Optional[pd.Series], name_confirmed: bool,
               evidence_end: Date) -> tuple[str, str]:
    """Grade one (ticker segment, CIK) link against the filings themselves."""
    if span is None:
        return "D_NO_PERIODIC_FILINGS", "CIK has no 10-K/10-Q in the registry (foreign private issuer or fund)"
    start, end = window
    end = min(end, evidence_end)
    tolerance = pd.Timedelta(days=EVIDENCE_TOLERANCE_DAYS)
    first, last = span["first_filing"], span["last_filing"]
    if pd.Timestamp(start) < pd.Timestamp("2011-01-01") + tolerance:
        starts_ok = True   # registry begins 2011: a window that opens earlier cannot be tested at its start
    else:
        starts_ok = first <= pd.Timestamp(start) + tolerance
    ends_ok = last >= pd.Timestamp(end) - tolerance
    if not starts_ok and first > pd.Timestamp(end):
        return "X_CONTRADICTED", "first filing is after the ticker's window ended"
    if not starts_ok:
        return "X_CONTRADICTED" if (first - pd.Timestamp(start)) > pd.Timedelta(days=2 * EVIDENCE_TOLERANCE_DAYS) else "C_PARTIAL", \
            f"first filing {first.date()} is well after the window start {start}"
    if not ends_ok:
        return "C_PARTIAL", f"last filing {last.date()} precedes the window end {end}"
    return ("A_CONFIRMED", "filings span the window and a filing-time name matches") if name_confirmed else \
        ("B_CONSISTENT", "filings span the window; no independent name match")


def _predecessor(vendor_key: str, successor: int, window_start: Date, span: pd.DataFrame,
                 index: Mapping[str, set[int]]) -> Optional[int]:
    """The single other CIK carrying this issuer name whose filings end within a year of the successor's first filing."""
    first_successor = span.loc[successor, "first_filing"]
    matches = []
    for cik in sorted(index.get(vendor_key, set()) - {int(successor)}):
        if cik not in span.index:
            continue
        gap = (first_successor - span.loc[cik, "last_filing"]).days
        if -EVIDENCE_TOLERANCE_DAYS <= gap <= EVIDENCE_TOLERANCE_DAYS and span.loc[cik, "first_filing"] <= pd.Timestamp(window_start) + pd.Timedelta(days=EVIDENCE_TOLERANCE_DAYS):
            matches.append(cik)
    return matches[0] if len(matches) == 1 else None


def resolve_universe(symbols: Sequence[str], current: pd.DataFrame, vendor: pd.DataFrame, registry: pd.DataFrame,
                     windows: Mapping[str, PriceWindow], *, histories: Optional[Mapping[int, list[dict[str, Any]]]] = None,
                     evidence_end: Date = Date(2025, 5, 9)) -> pd.DataFrame:
    """Resolve each universe ticker to a CIK and grade the link.  One row per ticker segment."""
    by_ticker = {normalize_ticker(t): r for t, r in zip(current["ticker"], current.to_dict("records"))}
    vendor_names = dict(zip(vendor["symbol"].astype(str).str.upper(), vendor["security_name"]))
    index = name_index(registry, histories)
    span = filing_span(registry)
    names_by_cik: dict[int, set[str]] = {}
    for key, ciks in index.items():
        for cik in ciks:
            names_by_cik.setdefault(cik, set()).add(key)
    rows = []
    for symbol in sorted(set(map(str.upper, symbols))):
        window = windows.get(symbol)
        record = by_ticker.get(normalize_ticker(symbol))
        vendor_key = normalize_name(vendor_names.get(symbol))
        method, cik, exchange, sec_name = None, None, None, None
        if record is not None:
            method, cik, exchange, sec_name = "CURRENT_TICKER_MAP", int(record["cik"]), record.get("exchange"), record.get("name")
        elif vendor_key and window is not None:
            candidates = sorted(index.get(vendor_key, set()))
            live = [c for c in candidates if c in span.index and span.loc[c, "last_filing"] >= pd.Timestamp(window.first)
                    and span.loc[c, "first_filing"] <= pd.Timestamp(min(window.last, evidence_end)) + pd.Timedelta(days=EVIDENCE_TOLERANCE_DAYS)]
            if len(live) == 1:
                method, cik = "EXACT_NAME_EVIDENCE", live[0]
            elif len(live) > 1:
                rows.append({"ticker": symbol, "cik": pd.NA, "method": "AMBIGUOUS_NAME", "grade": "UNRESOLVED",
                             "reason": f"{len(live)} CIKs share the normalised name", "window_from": window.first, "window_to": window.last})
                continue
        if cik is None or window is None:
            rows.append({"ticker": symbol, "cik": pd.NA, "method": method or "NONE", "grade": "UNRESOLVED",
                         "reason": "no CIK from the current map or exact filing-name evidence" if window else "no price window",
                         "window_from": getattr(window, "first", None), "window_to": getattr(window, "last", None)})
            continue
        confirmed = bool(vendor_key) and vendor_key in names_by_cik.get(cik, set())
        for start, end in window.segments:
            grade, reason = grade_link((start, end), span.loc[cik] if cik in span.index else None, confirmed, evidence_end)
            base = {"ticker": symbol, "method": method, "exchange": exchange, "sec_name": sec_name,
                    "vendor_name": vendor_names.get(symbol), "segments": len(window.segments)}
            if grade in ("X_CONTRADICTED", "C_PARTIAL") and "well after the window start" in reason and vendor_key:
                predecessor = _predecessor(vendor_key, cik, start, span, index)
                if predecessor is not None:
                    split = span.loc[cik, "first_filing"].date()
                    early_end = min(end, split - pd.Timedelta(days=1))
                    p_grade, p_reason = grade_link((start, early_end), span.loc[predecessor], True, evidence_end)
                    if p_grade in ("A_CONFIRMED", "B_CONSISTENT"):
                        rows.append({**base, "cik": predecessor, "method": "SUCCESSOR_NAME_CONTINUITY", "grade": "B_CONSISTENT",
                                     "reason": f"predecessor CIK with the same issuer name; successor CIK {cik} first files {split}",
                                     "name_confirmed": True, "window_from": start, "window_to": early_end})
                        if end >= split:
                            s_grade, s_reason = grade_link((split, end), span.loc[cik], confirmed, evidence_end)
                            rows.append({**base, "cik": cik, "grade": s_grade, "reason": s_reason, "name_confirmed": confirmed,
                                         "window_from": split, "window_to": end})
                        continue
            rows.append({**base, "cik": cik, "grade": grade, "reason": reason, "name_confirmed": confirmed,
                         "window_from": start, "window_to": end})
    return pd.DataFrame(rows)


def identity_intervals(resolution: pd.DataFrame, *, retrieved_at: datetime, last_data_date: Date) -> pd.DataFrame:
    """`security_identity_interval` from graded links.  Ticker windows are dated by price data, not by the SEC snapshot."""
    linked = resolution[resolution["grade"].isin(["A_CONFIRMED", "B_CONSISTENT", "C_PARTIAL", "X_CONTRADICTED", "D_NO_PERIODIC_FILINGS"])].copy()
    multi = linked.groupby("cik")["ticker"].nunique()
    linked["class_key"] = [t if multi.loc[c] > 1 else "" for t, c in zip(linked["ticker"], linked["cik"])]
    linked["security_id"] = [security_id(c, k) for c, k in zip(linked["cik"], linked["class_key"])]
    linked["effective_from"] = pd.to_datetime(linked["window_from"])
    still_trading = pd.to_datetime(linked["window_to"]).dt.date >= last_data_date
    linked["effective_to"] = pd.to_datetime(linked["window_to"]).where(~still_trading, pd.NaT)
    linked["source"] = np.select([linked["method"] == "CURRENT_TICKER_MAP", linked["method"] == "SUCCESSOR_NAME_CONTINUITY"],
                                 ["PRICE_WINDOW+SEC_CURRENT_TICKER_MAP", "PRICE_WINDOW+SEC_SUCCESSOR_NAME_CONTINUITY"], "PRICE_WINDOW+SEC_FILING_NAME")
    linked["source_accession"] = pd.NA
    linked["retrieved_at"] = retrieved_at
    linked["status"] = linked["grade"]
    return linked[["security_id", "cik", "ticker", "exchange", "sec_name", "effective_from", "effective_to", "source",
                   "source_accession", "retrieved_at", "status", "reason", "class_key"]].rename(columns={"sec_name": "name"})


def check_no_overlap(intervals: pd.DataFrame) -> None:
    """A ticker never names two securities at once; one security never has two open intervals for one ticker."""
    for ticker, group in intervals.sort_values("effective_from").groupby("ticker"):
        end = None
        for row in group.itertuples(index=False):
            if end is not None and pd.Timestamp(row.effective_from) <= end and row.cik != previous_cik:
                raise ValueError(f"ticker {ticker} names two securities at once around {row.effective_from}")
            end = pd.Timestamp(row.effective_to) if pd.notna(row.effective_to) else pd.Timestamp.max
            previous_cik = row.cik


# ── exit events ──────────────────────────────────────────────────────────────

def exit_events(identities: pd.DataFrame, evidence_by_cik: Mapping[int, list[dict[str, Any]]],
                last_seen: Mapping[str, Date]) -> pd.DataFrame:
    """One record per identity that ceased trading in the price data; graded by the filings that surround it.

    EXACT: a Form 25 within 45 days of the last trade.  APPROXIMATED: Form 15, or an 8-K delisting /
    acquisition / bankruptcy item, or only the local last-seen date.  Return treatment is always
    UNKNOWN: no delisting return is invented.
    """
    rows = []
    closed = identities[identities["effective_to"].notna()]
    for row in closed.itertuples(index=False):
        last_trade = pd.Timestamp(row.effective_to)
        events = evidence_by_cik.get(int(row.cik), [])
        near = [e for e in events if abs((pd.Timestamp(e["event_date"]) - last_trade).days) <= 45]
        form25 = [e for e in near if e["kind"] == "EXCHANGE_DELISTING_FORM_25"]
        best = (form25 or near or [None])[0]
        quality = "EXACT" if form25 else ("APPROXIMATED" if best or row.ticker in last_seen else "UNKNOWN")
        rows.append({"security_id": row.security_id, "cik": row.cik, "ticker": row.ticker,
                     "event_date": pd.Timestamp(best["event_date"]) if best else last_trade,
                     "form": best["form"] if best else pd.NA, "reason": best["kind"] if best else "LOCAL_LAST_PRICE_DATE",
                     "last_trade_date": last_trade, "quality": quality,
                     "return_treatment": "UNKNOWN_NO_DELISTING_RETURN_INVENTED",
                     "source_accession": best["accession"] if best else pd.NA})
    return pd.DataFrame(rows)


# ── shares vintages and point-in-time market capitalisation ──────────────────

def dei_share_rows(concept: Mapping[str, Any], registry_by_accession: pd.DataFrame) -> pd.DataFrame:
    """dei cover-page shares, one row per reported value, dated by the filing's *acceptance* time.

    The companyconcept API states the accession and filing date of each value; the acceptance time
    comes from the FSDS registry.  A value whose accession is not a periodic filing in the registry is
    dropped - nothing is dated by `filed` alone.
    """
    rows = (concept.get("units") or {}).get("shares") or []
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame = frame.rename(columns={"accn": "accession", "end": "period_end", "val": "value"})
    group = frame.groupby(["accession", "period_end"], as_index=False).agg(value=("value", "sum"), n_values=("value", "size"))
    group = group.merge(registry_by_accession[["accepted_at", "form", "cik"]], left_on="accession", right_index=True, how="inner")
    group["tag"] = "EntityCommonStockSharesOutstanding"
    group["unit"] = "shares"
    group["basis"] = "DEI_COVER"
    group["multi_class_summed"] = group["n_values"] > 1
    return group


def split_adjust(value: float, splits: pd.DataFrame, symbol: str, after: pd.Timestamp, through: pd.Timestamp) -> float:
    """Restate a share count reported at `after` to `through` using only splits with ex-date in (after, through]."""
    if splits is None or splits.empty:
        return value
    rows = splits[(splits["symbol"] == symbol) & (splits["ex_date"] > after) & (splits["ex_date"] <= through)]
    ratio = 1.0
    for row in rows.itertuples(index=False):
        ratio *= float(row.to_factor) / float(row.for_factor)
    return value * ratio


def evidence_summary(resolution: pd.DataFrame) -> dict[str, Any]:
    grades = resolution["grade"].value_counts().to_dict()
    return {"links": int(len(resolution)), "grades": {k: int(v) for k, v in grades.items()},
            "tickers": int(resolution["ticker"].nunique()),
            "resolved_tickers": int(resolution.loc[resolution["grade"].isin(["A_CONFIRMED", "B_CONSISTENT"]), "ticker"].nunique()),
            "methods": {k: int(v) for k, v in resolution["method"].value_counts().items()}}
