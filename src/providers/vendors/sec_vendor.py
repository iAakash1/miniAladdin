"""
SEC vendor — official EDGAR data.

Primary transport is SEC's own public EDGAR JSON API (data.sec.gov), which
is free, requires no key, and is the authoritative source for filings and
XBRL company facts. It requires a descriptive User-Agent per SEC's fair-
access policy. When `SEC_API` is configured it is sent as an additional
credential header for services that proxy EDGAR, but the vendor never
*depends* on it: absent the key, everything here still works.

Rate limit: SEC asks for ≤10 req/s; we sit far below that by default.

Everything returns normalized schema objects — never raw EDGAR JSON.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

from src.providers.base import VendorClient
from src.services.confidence import for_provider as _confidence_for
from src.providers.research_schemas import (
    GraphEdge,
    GraphNode,
    KnowledgeBundle,
    ResearchEvidence,
    ResearchFinding,
    ResearchSource,
    TimelineEvent,
)

logger = logging.getLogger(__name__)

# Forms worth surfacing, with the plain-English meaning shown to users.
FORM_MEANING: dict[str, str] = {
    "10-K": "Annual report",
    "10-Q": "Quarterly report",
    "8-K": "Material event",
    "DEF 14A": "Proxy statement",
    "S-1": "Registration statement",
    "4": "Insider transaction",
    "13F-HR": "Institutional holdings",
    "SC 13D": "Activist stake",
    "SC 13G": "Passive stake",
}

# XBRL concepts we read from companyfacts, with display labels. US-GAAP
# taxonomy names are stable across filers, which is what makes this
# deterministic rather than best-effort text parsing.
XBRL_CONCEPTS: dict[str, str] = {
    "Revenues": "Revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "Revenue",
    "NetIncomeLoss": "Net income",
    "Assets": "Total assets",
    "Liabilities": "Total liabilities",
    "StockholdersEquity": "Shareholders’ equity",
    "CashAndCashEquivalentsAtCarryingValue": "Cash & equivalents",
    "LongTermDebtNoncurrent": "Long-term debt",
    "ResearchAndDevelopmentExpense": "R&D expense",
    "PaymentsForRepurchaseOfCommonStock": "Share repurchases",
    "PaymentsOfDividendsCommonStock": "Dividends paid",
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


class SECVendor(VendorClient):
    NAME = "sec"
    KEY_ENV = None  # keyless by design: EDGAR is public
    DEFAULT_RPM = 60

    DATA_BASE = "https://data.sec.gov"
    WWW_BASE = "https://www.sec.gov"

    def __init__(self, session=None):
        super().__init__(session)
        self._ticker_map: Optional[dict[str, dict[str, Any]]] = None

    def _headers(self) -> dict[str, str]:
        # SEC fair-access policy requires an identifying User-Agent.
        headers = {
            "User-Agent": os.getenv(
                "SEC_USER_AGENT", "OmniSignal Research (contact: research@omnisignal.app)"
            ),
            "Accept": "application/json",
        }
        api_key = os.getenv("SEC_API", "").strip()
        if api_key:
            headers["Authorization"] = api_key
        return headers

    # ── CIK resolution ───────────────────────────────────────────────────────
    def _ticker_index(self) -> dict[str, dict[str, Any]]:
        """company_tickers.json, cached for the process lifetime (it changes
        at most daily and is ~1MB)."""
        if self._ticker_map is None:
            data = self._get_json(f"{self.WWW_BASE}/files/company_tickers.json", headers=self._headers())
            index: dict[str, dict[str, Any]] = {}
            for row in (data or {}).values():
                ticker = str(row.get("ticker", "")).upper()
                if ticker:
                    index[ticker] = {
                        "cik": str(row.get("cik_str", "")).zfill(10),
                        "name": row.get("title", ""),
                    }
            self._ticker_map = index
        return self._ticker_map

    def resolve_cik(self, symbol: str) -> Optional[dict[str, Any]]:
        return self._ticker_index().get(symbol.upper())

    # ── filings ──────────────────────────────────────────────────────────────
    def get_filings(self, symbol: str, limit: int = 20) -> list[dict[str, Any]]:
        """Recent filings, newest first, normalized and URL-resolved."""
        entry = self.resolve_cik(symbol)
        if not entry:
            return []
        cik = entry["cik"]
        data = self._get_json(f"{self.DATA_BASE}/submissions/CIK{cik}.json", headers=self._headers())
        recent = ((data or {}).get("filings") or {}).get("recent") or {}
        forms = recent.get("form") or []
        out: list[dict[str, Any]] = []
        for i, form in enumerate(forms):
            if form not in FORM_MEANING:
                continue
            accession = (recent.get("accessionNumber") or [""] * len(forms))[i]
            document = (recent.get("primaryDocument") or [""] * len(forms))[i]
            naked = accession.replace("-", "")
            out.append({
                "form": form,
                "meaning": FORM_MEANING[form],
                "filed_at": (recent.get("filingDate") or [""] * len(forms))[i],
                "report_date": (recent.get("reportDate") or [""] * len(forms))[i] or None,
                "accession": accession,
                "url": (
                    f"{self.WWW_BASE}/Archives/edgar/data/{int(cik)}/{naked}/{document}"
                    if document else
                    f"{self.WWW_BASE}/Archives/edgar/data/{int(cik)}/{naked}"
                ),
                "items": (recent.get("items") or [""] * len(forms))[i] or None,
            })
            if len(out) >= limit:
                break
        return out

    # ── XBRL company facts ───────────────────────────────────────────────────
    def get_xbrl_facts(self, symbol: str) -> dict[str, list[dict[str, Any]]]:
        """Selected US-GAAP concepts as clean annual series, newest first.

        Returns {display_label: [{fiscal_year, value, unit, form, filed}]}.
        """
        entry = self.resolve_cik(symbol)
        if not entry:
            return {}
        data = self._get_json(
            f"{self.DATA_BASE}/api/xbrl/companyfacts/CIK{entry['cik']}.json", headers=self._headers()
        )
        gaap = ((data or {}).get("facts") or {}).get("us-gaap") or {}
        series: dict[str, list[dict[str, Any]]] = {}
        for concept, label in XBRL_CONCEPTS.items():
            node = gaap.get(concept)
            if not node:
                continue
            for unit, rows in (node.get("units") or {}).items():
                annual = [
                    {
                        "fiscal_year": row.get("fy"),
                        "value": row.get("val"),
                        "unit": unit,
                        "form": row.get("form"),
                        "filed": row.get("filed"),
                    }
                    for row in rows
                    if row.get("form") == "10-K" and row.get("fp") == "FY" and row.get("val") is not None
                ]
                if not annual:
                    continue
                # Dedupe by fiscal year, keeping the most recently filed value
                # (restatements supersede originals).
                by_year: dict[int, dict[str, Any]] = {}
                for row in annual:
                    year = row["fiscal_year"]
                    if year is None:
                        continue
                    if year not in by_year or str(row["filed"]) > str(by_year[year]["filed"]):
                        by_year[year] = row
                merged = sorted(by_year.values(), key=lambda r: r["fiscal_year"], reverse=True)[:6]
                # First unit with data wins; concepts alias to one label, so
                # don't let a later alias overwrite a populated series.
                if merged and not series.get(label):
                    series[label] = merged
                break
        return series

    # ── knowledge bundle ─────────────────────────────────────────────────────
    def get_knowledge(self, symbol: str) -> KnowledgeBundle:
        """Filings + XBRL → graph nodes, timeline events, deterministic findings."""
        entry = self.resolve_cik(symbol)
        if not entry:
            return KnowledgeBundle()
        symbol = symbol.upper()
        company_id = f"company:{symbol}"
        bundle = KnowledgeBundle(
            nodes=[GraphNode(
                id=company_id, type="company", label=entry["name"] or symbol,
                route=f"/company/{symbol}",
                metadata={"cik": entry["cik"], "source": "sec"},
            )],
        )

        filings = self.get_filings(symbol, limit=12)
        for filing in filings:
            source = ResearchSource(
                provider="sec", title=f"{filing['form']} — {filing['meaning']}",
                url=filing["url"], document_type=filing["form"],
                published_at=filing["filed_at"],
            )
            filing_id = f"filing:{symbol}:{filing['accession']}"
            bundle.nodes.append(GraphNode(
                id=filing_id, type="filing",
                label=f"{symbol} {filing['form']} ({filing['filed_at']})",
                description=filing["meaning"], route=filing["url"],
                metadata={"form": filing["form"], "filed_at": filing["filed_at"]},
            ))
            bundle.edges.append(GraphEdge(
                source_id=company_id, target_id=filing_id, type="mentions", provider="sec",
                confidence=_confidence_for("sec"), observed_at=filing["filed_at"] or "",
            ))
            bundle.events.append(TimelineEvent(
                id=f"event:{filing_id}", date=filing["filed_at"], kind="filing",
                title=f"{filing['form']} filed", detail=filing["meaning"],
                source=source,
            ))

        facts = self.get_xbrl_facts(symbol)
        for label, rows in facts.items():
            if len(rows) < 2:
                continue
            latest, prior = rows[0], rows[1]
            if not latest["value"] or not prior["value"] or prior["value"] == 0:
                continue
            change = (latest["value"] - prior["value"]) / abs(prior["value"])
            evidence = ResearchEvidence(
                id=f"evidence:sec:{symbol}:{_slug(label)}",
                source=ResearchSource(
                    provider="sec", title=f"{symbol} 10-K XBRL — {label}",
                    url=f"{self.WWW_BASE}/cgi-bin/browse-edgar?action=getcompany&CIK={entry['cik']}&type=10-K",
                    document_type="10-K", published_at=str(latest.get("filed") or ""),
                ),
                excerpt=(
                    f"{label} FY{latest['fiscal_year']}: {latest['value']:,.0f} {latest['unit']} "
                    f"vs FY{prior['fiscal_year']}: {prior['value']:,.0f} {prior['unit']}"
                ),
                doc_section="XBRL company facts",
            )
            # Tone is factual direction only for magnitudes where "up" is
            # unambiguous; balance-sheet items stay neutral.
            directional = label in {"Revenue", "Net income", "Shareholders’ equity", "Cash & equivalents"}
            tone = "neutral"
            if directional:
                tone = "pos" if change > 0.02 else "neg" if change < -0.02 else "neutral"
            bundle.findings.append(ResearchFinding(
                id=f"finding:sec:{symbol}:{_slug(label)}",
                label=label,
                text=(
                    f"{label} moved {change:+.1%} year over year "
                    f"(FY{prior['fiscal_year']} → FY{latest['fiscal_year']}), per the company’s own 10-K XBRL data."
                ),
                tone=tone, evidence=[evidence],
            ))
        return bundle
