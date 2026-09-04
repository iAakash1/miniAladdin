"""Massive — market data, on the Polygon wire format.

Massive's REST surface is Polygon-compatible: the same paths
(`/v2/aggs/ticker/...`, `/v3/reference/tickers/...`), the same abbreviated
bar fields (`o h l c v vw n t`), the same envelope (`status`, `request_id`,
`resultsCount`) and the same error shape. That was established against the
live service rather than assumed — an unauthenticated request returns
`{"status":"ERROR","error":"API Key was not provided"}`, and a wrong key
returns `"Unknown API Key"`, which is Polygon's wording exactly.

So this adapter is deliberately a near-twin of the Polygon one. The value is
not novelty: it is that a second vendor speaking a format the codebase
already parses can be added to the chain without a new dialect to maintain.

Two deliberate departures from the Polygon adapter:

  Authentication is a Bearer header, never `?apiKey=`. Massive accepts both —
  verified — and a key in a query string reaches access logs, proxy logs and
  browser history. The header is free and does not.

  Nothing here is reachable without `MASSIVE_API_KEY`. The base class treats a
  missing key as "not available" and the chain skips unavailable vendors, so
  an environment without the key behaves exactly as it did before this file
  existed. That is the whole configuration story: no flag, no fallback flag,
  no partially-initialised client.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ..base import VendorClient
from ..schemas import CompanyProfile, OHLCVBar, OptionChain, OptionContract, PriceQuote, PriceSeries
from .market_vendors import PERIOD_DAYS, _registrable_domain, _safe_float


class MassiveVendor(VendorClient):
    NAME = "massive"
    KEY_ENV = "MASSIVE_API_KEY"
    # The published free tier is five calls a minute; paid tiers raise it.
    # PROVIDER_MASSIVE_RPM overrides this without a code change, which is how
    # the base class already lets every other vendor be retuned per
    # deployment.
    DEFAULT_RPM = 5

    BASE = "https://api.massive.com"

    @property
    def _auth(self) -> dict[str, str]:
        """The key, in a header.

        Never returned to a caller and never placed in a URL. The only reason
        this is a property rather than a constant is that the base class reads
        the environment at call time, so a key added after boot works.
        """
        return {"Authorization": f"Bearer {self.api_key}"}

    # ── quotes ───────────────────────────────────────────────────────────────

    def get_price(self, symbol: str) -> Optional[PriceQuote]:
        data = self._get_json(
            f"{self.BASE}/v2/aggs/ticker/{symbol}/prev",
            params={"adjusted": "true"},
            headers=self._auth,
            operation="price",
        )
        results = (data or {}).get("results") or []
        if not results:
            return None
        row = results[0]
        close = _safe_float(row.get("c"))
        if close is None:
            return None

        stamp = _safe_float(row.get("t"))
        return PriceQuote(
            symbol=symbol,
            price=close,
            day_open=_safe_float(row.get("o")),
            day_high=_safe_float(row.get("h")),
            day_low=_safe_float(row.get("l")),
            volume=_safe_float(row.get("v")),
            vwap=_safe_float(row.get("vw")),
            trade_count=int(row["n"]) if isinstance(row.get("n"), (int, float)) else None,
            as_of=(
                datetime.fromtimestamp(stamp / 1000, tz=timezone.utc).isoformat()
                if stamp else None
            ),
            # The same caveat the Polygon adapter carries, for the same reason:
            # `/prev` is the previous session's aggregate, not a live tick, and
            # a consumer that reads it as current is reading it wrong.
            price_basis="previous session close",
        )

    # ── history ──────────────────────────────────────────────────────────────

    def get_series(self, symbol: str, period: str) -> Optional[PriceSeries]:
        days = PERIOD_DAYS.get(period, 92)
        end = datetime.now(tz=timezone.utc).date()
        start = end - timedelta(days=days)

        data = self._get_json(
            f"{self.BASE}/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}",
            # Adjusted for splits and dividends. An unadjusted five-year series
            # shows a split as a crash, which is the single most misleading
            # thing a price chart can do.
            params={"adjusted": "true", "sort": "asc", "limit": 50000},
            headers=self._auth,
            operation="series",
        )
        rows = (data or {}).get("results") or []
        if not rows:
            return None

        bars: list[OHLCVBar] = []
        for row in rows:
            close = _safe_float(row.get("c"))
            stamp = _safe_float(row.get("t"))
            if close is None or stamp is None:
                # A bar with no close is not a bar. PriceSeries validates on
                # construction and records what it dropped; skipping here keeps
                # the reason legible rather than handing it a null to reject.
                continue
            volume = _safe_float(row.get("v"))
            bars.append(OHLCVBar(
                date=datetime.fromtimestamp(stamp / 1000, tz=timezone.utc).date().isoformat(),
                open=_safe_float(row.get("o")),
                high=_safe_float(row.get("h")),
                low=_safe_float(row.get("l")),
                close=close,
                volume=int(volume) if volume is not None else None,
            ))

        return PriceSeries(symbol=symbol, bars=bars) if bars else None

    # ── reference ────────────────────────────────────────────────────────────

    def get_company(self, symbol: str) -> Optional[CompanyProfile]:
        data = self._get_json(
            f"{self.BASE}/v3/reference/tickers/{symbol}",
            headers=self._auth,
            operation="company",
        )
        result = (data or {}).get("results")
        if not isinstance(result, dict) or not result.get("name"):
            return None

        website = str(result.get("homepage_url") or "")
        employees = result.get("total_employees")
        return CompanyProfile(
            symbol=symbol,
            name=str(result.get("name") or ""),
            # SIC is a description, not a GICS sector, so it lands in
            # `industry` — which is what it actually is.
            industry=str(result.get("sic_description") or ""),
            market_cap=_safe_float(result.get("market_cap")),
            currency=str(result.get("currency_name") or "USD").upper(),
            exchange=str(result.get("primary_exchange") or ""),
            website=website,
            domain=_registrable_domain(website),
            description=str(result.get("description") or "")[:1200],
            employees=int(employees) if isinstance(employees, (int, float)) else None,
        )

    # ── options ──────────────────────────────────────────────────────────────

    def get_option_chain(self, symbol: str, expiration: Optional[str] = None) -> Optional[OptionChain]:
        """Every listed contract for one underlying.

        The endpoint and its response shape were established the same way the
        rest of this adapter was: by probing the live service. Both
        `/v3/snapshot/options/{underlying}` and
        `/v3/reference/options/contracts` answer 401 "API Key was not
        provided" rather than 404, so the routes exist and are the
        Polygon-compatible ones this adapter already speaks.

        **What has not been established** is whether the deployment's plan is
        entitled to options data. A 401 proves a route exists; it says nothing
        about entitlement, and the published tiers gate real-time data
        separately. So this may return contracts, an entitlement error, or
        delayed quotes, and there is no way to know which from an environment
        without the key. It is written to be truthful in all three cases and
        is not claimed to have been exercised against live data.

        The normalisation below never substitutes a zero for a field the
        provider omitted. An option chain is mostly holes — contracts that did
        not trade, contracts with no two-sided market, contracts the provider
        declined to model — and a zero bid is a statement about a market while
        a missing bid is the absence of one.
        """
        params: dict[str, Any] = {"limit": 250}
        if expiration:
            # Passed through as the provider's own filter rather than fetching
            # everything and discarding: a full chain is thousands of rows.
            params["expiration_date"] = expiration

        data = self._get_json(
            f"{self.BASE}/v3/snapshot/options/{symbol.upper()}",
            params=params,
            headers=self._auth,
            operation="options",
        )
        rows = (data or {}).get("results") or []
        if not rows:
            return None

        contracts: list[OptionContract] = []
        delayed: Optional[bool] = None

        for row in rows:
            details = row.get("details") or {}
            ticker = details.get("ticker")
            strike = _safe_float(details.get("strike_price"))
            expiry = details.get("expiration_date")
            kind = details.get("contract_type")

            # Identity is not optional. A contract missing any of these is not
            # a contract with holes, it is an unidentifiable row, and putting
            # it in a chain keyed on strike and expiry would corrupt the axes.
            if not ticker or strike is None or not expiry or not kind:
                continue

            quote = row.get("last_quote") or {}
            trade = row.get("last_trade") or {}
            day = row.get("day") or {}
            greeks = row.get("greeks") or {}

            timeframe = quote.get("timeframe")
            if isinstance(timeframe, str):
                # Any delayed quote makes the whole chain delayed; a chain is
                # only as current as its least current contract.
                delayed = True if timeframe.upper() != "REAL-TIME" else (delayed or False)

            contracts.append(OptionContract(
                contract=str(ticker),
                underlying=symbol.upper(),
                expiration=str(expiry),
                strike=strike,
                contract_type=str(kind).lower(),
                shares_per_contract=(
                    int(details["shares_per_contract"])
                    if isinstance(details.get("shares_per_contract"), (int, float)) else None
                ),
                exercise_style=details.get("exercise_style"),
                bid=_safe_float(quote.get("bid")),
                ask=_safe_float(quote.get("ask")),
                midpoint=_safe_float(quote.get("midpoint")),
                last_price=_safe_float(trade.get("price")),
                # Volume and open interest are the two places a literal zero is
                # the provider's own answer — a contract that did not trade —
                # so a present zero is kept and only an absent field is None.
                day_volume=(
                    int(day["volume"]) if isinstance(day.get("volume"), (int, float)) else None
                ),
                open_interest=(
                    int(row["open_interest"]) if isinstance(row.get("open_interest"), (int, float)) else None
                ),
                implied_volatility=_safe_float(row.get("implied_volatility")),
                delta=_safe_float(greeks.get("delta")),
                gamma=_safe_float(greeks.get("gamma")),
                theta=_safe_float(greeks.get("theta")),
                vega=_safe_float(greeks.get("vega")),
                quote_timeframe=timeframe if isinstance(timeframe, str) else None,
                source=self.NAME,
            ))

        if not contracts:
            return None

        return OptionChain(
            underlying=symbol.upper(),
            contracts=contracts,
            source=self.NAME,
            delayed=delayed,
        )
