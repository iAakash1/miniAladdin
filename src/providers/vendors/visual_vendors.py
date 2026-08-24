"""
Visual providers — brand identity and contextual imagery.

Three vendors with three different jobs, deliberately not interchangeable:

* **Logo.dev** answers "what does this company's mark look like". It is keyed
  on a ticker or a domain and returns the company's *actual* logo. Nothing
  else here can do that, and nothing here substitutes for it — a stock photo
  where a logo should be is worse than no logo.
* **Pexels** and **Unsplash** answer a different question: "what does this
  *industry* look like". They are editorial context, never identity, and the
  schema marks them as such so a caller cannot accidentally present a stock
  photograph as a company's own image.

Pexels and Unsplash both search the same way and are queried **in parallel**,
not one as the other's fallback. Two libraries with different contributor
bases return genuinely different photographs for the same query; stopping at
the first success would halve the candidate pool for no latency gain, since
the calls run concurrently.

## Credential handling

Logo.dev has two keys with different exposure rules. The *publishable* key is
designed for browser image URLs and is served to the client; the *secret* key
authenticates the server-side lookup APIs and never leaves this process. The
brand-search method below uses the secret; the image URL builder uses only the
publishable one, which is why they are separate methods rather than one.

Pexels and Unsplash keys are server-side only — neither documents a
browser-safe key — so every call here is made from the backend and the client
receives resolved URLs, never credentials.
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Optional
from urllib.parse import quote

from src.providers.base import VendorClient
from src.providers.schemas import BrandMark, VisualAsset

logger = logging.getLogger(__name__)

# Pexels sizes: `large2x` is ~1880px and is the largest worth requesting for a
# terminal card. `original` can be 6000px, which is a several-megabyte
# download for a 400px slot.
_PEXELS_DISPLAY = "large2x"
_PEXELS_THUMB = "medium"


def _aspect(width: Optional[int], height: Optional[int]) -> Optional[float]:
    if not width or not height:
        return None
    return round(width / height, 3)


class LogoDevVendor(VendorClient):
    """Company marks by ticker or domain.

    Two capabilities with different credentials and different exposure:
    `logo_url` is a pure URL builder using the publishable key (safe to send
    to a browser), and `search_brand` is an authenticated server-side lookup
    using the secret key (never sent anywhere).
    """

    NAME = "logo_dev"
    # Availability is governed by the *publishable* key: without it no image
    # URL can be built, which is the capability everything else depends on.
    KEY_ENV = "LOGO_DEV_PUBLISHABLE_KEY"
    DEFAULT_RPM = 60

    IMG = "https://img.logo.dev"
    API = "https://api.logo.dev"

    @property
    def secret(self) -> str:
        """Server-side only. Never returned, logged, or serialised."""
        return os.getenv("LOGO_DEV_SECRET_KEY", "")

    def logo_url(self, *, ticker: str = "", domain: str = "", size: int = 128) -> str:
        """A CDN URL the browser can load directly.

        Returns "" rather than a keyless URL when unconfigured: an image
        request without a token 401s, and a broken image is worse than the
        monogram the UI already falls back to.

        `retina=false` and an explicit size are set because the default is a
        much larger asset than a 20px table mark needs, and `fallback=404`
        makes a miss a clean error the `onError` handler can act on rather
        than a generic grey square that looks like a real logo.
        """
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
        """A resolved mark for a company.

        Ticker first because it is what the product always has; domain is
        tried second because Logo.dev's ticker index does not cover every
        listed symbol, while a domain from the company profile usually
        resolves. Both are URL construction — no request is made here, so
        this costs nothing and cannot fail.
        """
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
            # The alternate is handed to the client so a 404 on the ticker
            # index can be retried against the domain without a round trip.
            alternate_url=domain_url if ticker_url and domain_url else "",
            resolved_by="ticker" if ticker_url else "domain",
            provider=self.NAME,
        )

    def search_brand(self, query: str) -> Optional[list[dict[str, Any]]]:
        """Brand lookup by name — server-side, secret-key authenticated.

        Used to recover a domain for a company whose profile did not carry a
        website. Kept separate from `get_brand` precisely because it needs the
        secret: mixing them would make it easy to call the secret path from a
        context that serialises its result to the browser.
        """
        if not self.secret:
            return None
        data = self._get_json(
            f"{self.API}/search",
            params={"q": query},
            headers={"Authorization": f"Bearer {self.secret}"},
            operation="brand_search",
        )
        return data if isinstance(data, list) else None


class PexelsVendor(VendorClient):
    NAME = "pexels"
    KEY_ENV = "PEXELS_API_KEY"
    # Free tier is 200/hour. 20/min stays inside it while allowing a burst.
    DEFAULT_RPM = 20

    BASE = "https://api.pexels.com/v1"

    def search_images(
        self, query: str, *, limit: int = 12, orientation: str = "landscape",
    ) -> Optional[list[VisualAsset]]:
        data = self._get_json(
            f"{self.BASE}/search",
            params={
                "query": query,
                "per_page": min(max(limit, 1), 80),
                "orientation": orientation,
                # Terminal cards are dark; a photograph that is mostly white
                # fights the surface it sits on.
                "size": "medium",
            },
            headers={"Authorization": self.api_key},
            operation="image_search",
        )
        if not isinstance(data, dict):
            return None
        photos = data.get("photos")
        if not isinstance(photos, list):
            return None

        out: list[VisualAsset] = []
        for item in photos:
            if not isinstance(item, dict):
                continue
            src = item.get("src") if isinstance(item.get("src"), dict) else {}
            display = src.get(_PEXELS_DISPLAY) or src.get("large") or src.get("original")
            if not display:
                continue
            width, height = item.get("width"), item.get("height")
            out.append(VisualAsset(
                provider=self.NAME,
                provider_asset_id=str(item.get("id") or ""),
                image_url=str(display),
                thumbnail_url=str(src.get(_PEXELS_THUMB) or display),
                source_url=str(item.get("url") or ""),
                width=int(width) if isinstance(width, int) else None,
                height=int(height) if isinstance(height, int) else None,
                aspect_ratio=_aspect(width if isinstance(width, int) else None,
                                     height if isinstance(height, int) else None),
                # Pexels' `alt` is a human description of the photograph and is
                # exactly what an alt attribute needs.
                alt_text=str(item.get("alt") or "")[:200],
                photographer=str(item.get("photographer") or ""),
                photographer_url=str(item.get("photographer_url") or ""),
                query=query,
                # Both libraries ask to be credited with a link back; the flag
                # travels with the asset so a renderer cannot omit it by
                # forgetting which provider it came from.
                attribution_required=True,
                provider_metadata={
                    "avg_color": item.get("avg_color"),
                    "liked": item.get("liked"),
                },
            ))
        return out or None


class UnsplashVendor(VendorClient):
    NAME = "unsplash"
    KEY_ENV = "UNSPLASH_ACCESS_KEY"
    # Demo apps are 50 requests/hour; production apps 5,000. The lower bound
    # is assumed until the app is promoted, because exceeding it 403s.
    DEFAULT_RPM = 10

    BASE = "https://api.unsplash.com"

    def _headers(self) -> dict[str, str]:
        # Client-ID auth, not the secret. The secret key is only for OAuth
        # user authorisation, which this integration does not use and does not
        # need — so it is never read here at all.
        return {
            "Authorization": f"Client-ID {self.api_key}",
            "Accept-Version": "v1",
        }

    def search_images(
        self, query: str, *, limit: int = 12, orientation: str = "landscape",
    ) -> Optional[list[VisualAsset]]:
        data = self._get_json(
            f"{self.BASE}/search/photos",
            params={
                "query": query,
                "per_page": min(max(limit, 1), 30),
                "orientation": orientation,
                "content_filter": "high",
            },
            headers=self._headers(),
            operation="image_search",
        )
        if not isinstance(data, dict):
            return None
        results = data.get("results")
        if not isinstance(results, list):
            return None

        out: list[VisualAsset] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            urls = item.get("urls") if isinstance(item.get("urls"), dict) else {}
            display = urls.get("regular") or urls.get("full")
            if not display:
                continue
            user = item.get("user") if isinstance(item.get("user"), dict) else {}
            links = item.get("links") if isinstance(item.get("links"), dict) else {}
            user_links = user.get("links") if isinstance(user.get("links"), dict) else {}
            width, height = item.get("width"), item.get("height")
            out.append(VisualAsset(
                provider=self.NAME,
                provider_asset_id=str(item.get("id") or ""),
                image_url=str(display),
                thumbnail_url=str(urls.get("small") or display),
                source_url=str(links.get("html") or ""),
                width=int(width) if isinstance(width, int) else None,
                height=int(height) if isinstance(height, int) else None,
                aspect_ratio=_aspect(width if isinstance(width, int) else None,
                                     height if isinstance(height, int) else None),
                alt_text=str(item.get("alt_description") or item.get("description") or "")[:200],
                photographer=str(user.get("name") or ""),
                photographer_url=str(user_links.get("html") or ""),
                query=query,
                attribution_required=True,
                provider_metadata={
                    "color": item.get("color"),
                    "likes": item.get("likes"),
                    # Unsplash asks that a download be registered when an image
                    # is actually used. The endpoint is carried here so the
                    # caller that *chooses* an asset can honour it, rather than
                    # this vendor firing it for all 30 search results.
                    "download_location": (
                        links.get("download_location") if isinstance(links, dict) else None
                    ),
                    "tags": [
                        t.get("title") for t in (item.get("tags") or [])
                        if isinstance(t, dict) and t.get("title")
                    ][:6],
                },
            ))
        return out or None

    def register_download(self, download_location: str) -> bool:
        """Honour Unsplash's download-tracking requirement for a chosen asset.

        Called once, for the single image actually displayed — not for every
        search result. Failure is non-fatal and deliberately silent to the
        caller: the image is already selected, and a tracking miss must not
        turn into a user-visible error.
        """
        if not download_location or not self.api_key:
            return False
        try:
            self._get_json(download_location, headers=self._headers(),
                           operation="download_track")
            return True
        except Exception:  # noqa: BLE001 — tracking is best-effort
            logger.debug("unsplash download tracking failed")
            return False


def stable_pick(assets: list[VisualAsset], seed: str) -> Optional[VisualAsset]:
    """Deterministically choose one asset for a given subject.

    Hash-indexed rather than "first result" so two companies in the same
    industry do not both render the same photograph, and rather than random so
    a company's image does not change on every page load — an image that
    reshuffles on refresh reads as decoration, not as part of the record.
    """
    if not assets:
        return None
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return assets[int.from_bytes(digest[:4], "big") % len(assets)]
