"""OpenFIGI instrument identity; never a source for price or scoring."""

from __future__ import annotations

import re

from src.providers.base import VendorClient
from src.providers.research_schemas import (
    GraphNode, KnowledgeBundle, ResearchClaim, ResearchEvidence, ResearchSource,
)
from src.services.confidence import for_provider as _confidence_for

_US_TICKER = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_FIGI = re.compile(r"^[A-Z0-9]{12}$")


class OpenFigiVendor(VendorClient):
    NAME = "openfigi"
    KEY_ENV = "OPENFIGI_API_KEY"
    DEFAULT_RPM = 20
    URL = "https://api.openfigi.com/v3/mapping"

    def get_instrument_identity(self, symbol: str) -> KnowledgeBundle:
        """Attach a FIGI only when the US ticker maps unambiguously."""
        ticker = symbol.strip().upper()
        if not _US_TICKER.fullmatch(ticker):
            return KnowledgeBundle()
        payload = self._post_json(
            self.URL,
            [{"idType": "TICKER", "idValue": ticker, "exchCode": "US"}],
            headers={"X-OPENFIGI-APIKEY": self.api_key},
            operation="instrument_identity",
            expect=list,
        )
        if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
            return KnowledgeBundle()
        rows = payload[0].get("data")
        if not isinstance(rows, list):
            return KnowledgeBundle()
        candidates = [row for row in rows if isinstance(row, dict)
                      and str(row.get("ticker") or "").upper() == ticker
                      and _FIGI.fullmatch(str(row.get("compositeFIGI") or ""))]
        composite = {row["compositeFIGI"] for row in candidates}
        if len(composite) != 1:
            # A ticker can denote several instruments. Guessing here would
            # contaminate every later claim that cites the identifier.
            return KnowledgeBundle()
        figi = next(iter(composite))
        source = ResearchSource(
            provider=self.NAME, title="OpenFIGI ticker mapping",
            url="https://www.openfigi.com/api/documentation",
            document_type="instrument mapping",
        )
        evidence = ResearchEvidence(
            id=f"openfigi:{ticker}:{figi}", source=source,
            excerpt=f"Ticker {ticker}; US exchange code; composite FIGI {figi}",
        )
        return KnowledgeBundle(
            nodes=[GraphNode(
                id=f"company:{ticker}", type="company", label=ticker,
                route=f"/company/{ticker}",
                metadata={"composite_figi": figi, "source": self.NAME},
            )],
            claims=[ResearchClaim(
                id=f"openfigi:{ticker}",
                statement=f"{ticker} maps to composite FIGI {figi} in OpenFIGI's US exchange mapping.",
                evidence=[evidence], confidence=_confidence_for(self.NAME),
            )],
        )
