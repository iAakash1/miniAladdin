"""Logo.dev company identity provider.

OmniSignal treats imagery as evidence, not decoration. Company marks are
factual identity and remain available through Logo.dev; generic stock-photo
context is intentionally absent from the product and provider graph.

Logo.dev has two keys with different exposure rules. The publishable key is
designed for browser image URLs. The secret key authenticates server-side
lookup and never leaves this process.
"""

from __future__ import annotations

import os
from typing import Any, Optional
from urllib.parse import quote

from src.providers.base import VendorClient
from src.providers.schemas import BrandMark


class LogoDevVendor(VendorClient):
    """Company marks by ticker or domain."""

    NAME = "logo_dev"
    KEY_ENV = "LOGO_DEV_PUBLISHABLE_KEY"
    DEFAULT_RPM = 60

    IMG = "https://img.logo.dev"
    API = "https://api.logo.dev"

    @property
    def secret(self) -> str:
        """Server-side only. Never returned, logged, or serialised."""
        return os.getenv("LOGO_DEV_SECRET_KEY", "")

    def logo_url(self, *, ticker: str = "", domain: str = "", size: int = 128) -> str:
        """Build a browser-safe CDN URL using only the publishable key."""
        if not self.api_key:
            return ""
        key = ticker.strip().upper() or domain.strip().lower()
        if not key:
            return ""
        path = f"ticker/{quote(key)}" if ticker.strip() else quote(domain.strip().lower())
        return (
            f"{self.IMG}/{path}"
            f"?token={quote(self.api_key)}&size={size}&format=png&fallback=404"
        )

    def get_brand(self, symbol: str, domain: str = "") -> Optional[BrandMark]:
        """Resolve a company mark without making a network request."""
        if not self.api_key:
            return None
        ticker_url = self.logo_url(ticker=symbol)
        domain_url = self.logo_url(domain=domain) if domain else ""
        if not ticker_url and not domain_url:
            return None
        return BrandMark(
            symbol=symbol.upper(),
            domain=domain,
            logo_url=ticker_url or domain_url,
            alternate_url=domain_url if ticker_url and domain_url else "",
            resolved_by="ticker" if ticker_url else "domain",
            provider=self.NAME,
        )

    def search_brand(self, query: str) -> Optional[list[dict[str, Any]]]:
        """Recover a domain by name with the server-only secret key."""
        if not self.secret:
            return None
        data = self._get_json(
            f"{self.API}/search",
            params={"q": query},
            headers={"Authorization": f"Bearer {self.secret}"},
            operation="brand_search",
        )
        return data if isinstance(data, list) else None
