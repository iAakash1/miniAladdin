"""
Tiingo — quotes, daily history, news and (entitlement-permitting) fundamentals.

One adapter, four capabilities, because Tiingo is one rate limit and one key.
Splitting it per capability would give four token buckets over one quota and
the vendor would start 429-ing while every bucket believed it had headroom.

## What is taken from each endpoint

* **IEX** (`/iex/{ticker}`) is the only endpoint here with a *quote*: last
  sale, bid, ask, mid, session OHLC and volume, plus three separate
  timestamps. Most adapters in this codebase return a bare close; this one
  returns the spread and the size behind it, which is the difference between
  "the price" and "the price you could actually transact at".
* **Daily** (`/tiingo/daily/{ticker}/prices`) is split-and-dividend adjusted.
  `adjClose` is used rather than `close` — an unadjusted series shows a 4-for-1
  split as a 75% crash, and a portfolio value curve built on one would report
  a loss that never happened.
* **News** (`/tiingo/news`) carries tags and a ticker list, which the other
  news vendors in this codebase do not.
* **Fundamentals** is an add-on. Free keys get DOW 30 only, so the endpoint is
  *probed*, and a 403/404 is recorded as "not entitled" rather than treated as
  an outage — the difference matters to the health circuit, which would
  otherwise cool the whole vendor down over a permission boundary and take
  the working price and news endpoints with it.

Auth travels in the `Authorization: Token …` header, never in the query
string: query strings land in access logs and proxy caches.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.providers.base import VendorClient, VendorError
from src.providers.schemas import (
    CompanyProfile,
    Fundamentals,
    NewsHeadline,
    OHLCVBar,
    PriceQuote,
    PriceSeries,
)

logger = logging.getLogger(__name__)


def _f(value: Any) -> Optional[float]:
    """A float, or None. Zero is preserved for volume but rejected for a
    price: a zero last-sale is a data fault, not a security worth nothing."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and abs(out) != float("inf") else None


def _positive(value: Any) -> Optional[float]:
    out = _f(value)
    return out if out is not None and out > 0 else None


_PERIOD_DAYS = {
    "1d": 5, "5d": 10, "1mo": 32, "3mo": 95, "6mo": 190,
    "1y": 370, "2y": 740, "5y": 1830, "max": 7300,
}


class TiingoVendor(VendorClient):
    NAME = "tiingo"
    KEY_ENV = "TIINGO_API_KEY"
    # Free tier is 50 requests/hour and 500/day. 45/min would exhaust the
    # hourly allowance in a minute, so the bucket is set to the sustainable
    # rate rather than to the burst ceiling.
    DEFAULT_RPM = 8
    TIMEOUT_SECONDS = 6.0

    BASE = "https://api.tiingo.com"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Token {self.api_key}", "Content-Type": "application/json"}

    # ── quotes ───────────────────────────────────────────────────────────────

    def get_quote(self, symbol: str) -> Optional[PriceQuote]:
        """Full IEX quote — last sale, bid/ask, mid, session OHLC, volume.

        The pricing hierarchy is deliberate: `tngoLast` is Tiingo's own
        consolidated last sale and is the most reliable field; `last` is the
        raw IEX print; `mid` is derived from the book and exists even when
        nothing has traded recently; `prevClose` is the floor. Falling
        straight to `prevClose` when a live field is missing would silently
        report yesterday as today, so the earlier fields are tried first and
        the one actually used is recorded in `price_basis`.
        """
        rows = self._get_json(
            f"{self.BASE}/iex/{symbol}", headers=self._headers(), operation="quote",
        )
        if not isinstance(rows, list) or not rows:
            return None
        row = rows[0]

        bid = _positive(row.get("bidPrice"))
        ask = _positive(row.get("askPrice"))
        mid = _positive(row.get("mid"))
        if mid is None and bid is not None and ask is not None:
            mid = (bid + ask) / 2.0

        price = None
        basis = None
        for field, label in (
            ("tngoLast", "last sale"), ("last", "last sale"),
            ("mid", "bid/ask mid"), ("prevClose", "previous close"),
        ):
            candidate = _positive(row.get(field)) if field != "mid" else mid
            if candidate is not None:
                price, basis = candidate, label
                break
        if price is None:
            return None

        return PriceQuote(
            symbol=symbol,
            price=price,
            as_of=row.get("lastSaleTimeStamp") or row.get("timestamp") or None,
            bid=bid,
            ask=ask,
            mid=mid,
            bid_size=_f(row.get("bidSize")),
            ask_size=_f(row.get("askSize")),
            day_open=_positive(row.get("open")),
            day_high=_positive(row.get("high")),
            day_low=_positive(row.get("low")),
            previous_close=_positive(row.get("prevClose")),
            volume=_f(row.get("volume")),
            price_basis=basis,
        )

    # The chain calls `get_price`; the richer quote is the same fetch.
    def get_price(self, symbol: str) -> Optional[PriceQuote]:
        return self.get_quote(symbol)

    # ── history ──────────────────────────────────────────────────────────────

    def get_series(self, symbol: str, period: str) -> Optional[PriceSeries]:
        days = _PERIOD_DAYS.get(period, 95)
        start = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
        rows = self._get_json(
            f"{self.BASE}/tiingo/daily/{symbol}/prices",
            params={"startDate": start, "resampleFreq": "daily"},
            headers=self._headers(),
            operation="series",
        )
        if not isinstance(rows, list) or not rows:
            return None

        bars: list[OHLCVBar] = []
        for row in rows:
            # Adjusted close, not raw close: an unadjusted series renders a
            # 4-for-1 split as a 75% single-day crash, and a portfolio curve
            # built on that reports a loss that never happened.
            close = _positive(row.get("adjClose")) or _positive(row.get("close"))
            date = str(row.get("date") or "")[:10]
            if close is None or not date:
                continue
            bars.append(OHLCVBar(
                date=date,
                open=_positive(row.get("adjOpen")) or _positive(row.get("open")),
                high=_positive(row.get("adjHigh")) or _positive(row.get("high")),
                low=_positive(row.get("adjLow")) or _positive(row.get("low")),
                close=close,
                volume=int(row["adjVolume"]) if _f(row.get("adjVolume")) else (
                    int(row["volume"]) if _f(row.get("volume")) else None
                ),
            ))
        bars.sort(key=lambda b: b.date)
        return PriceSeries(symbol=symbol, bars=bars) if bars else None

    # ── reference ────────────────────────────────────────────────────────────

    def get_company(self, symbol: str) -> Optional[CompanyProfile]:
        data = self._get_json(
            f"{self.BASE}/tiingo/daily/{symbol}", headers=self._headers(), operation="company",
        )
        if not isinstance(data, dict) or not data.get("name"):
            return None
        return CompanyProfile(
            symbol=symbol,
            name=str(data.get("name") or ""),
            exchange=str(data.get("exchangeCode") or ""),
        )

    # ── news ─────────────────────────────────────────────────────────────────

    def get_news(self, symbol: str, limit: int = 12) -> Optional[list[NewsHeadline]]:
        rows = self._get_json(
            f"{self.BASE}/tiingo/news",
            params={"tickers": symbol.lower(), "limit": min(limit, 50), "sortBy": "publishedDate"},
            headers=self._headers(),
            operation="news",
        )
        if not isinstance(rows, list):
            return None
        out: list[NewsHeadline] = []
        for row in rows:
            title = str(row.get("title") or "").strip()
            if not title:
                continue
            out.append(NewsHeadline(
                title=title,
                source=str(row.get("source") or "tiingo"),
                url=str(row.get("url") or ""),
                published_at=str(row.get("publishedDate") or ""),
                summary=str(row.get("description") or "")[:400],
                tags=[str(t) for t in (row.get("tags") or [])][:8],
                tickers=[str(t).upper() for t in (row.get("tickers") or [])][:8],
            ))
        return out or None

    # ── fundamentals (add-on entitlement) ────────────────────────────────────

    def get_fundamentals(self, symbol: str) -> Optional[Fundamentals]:
        """Latest reported statement figures, when the key is entitled.

        Free keys cover the DOW 30 only. A 403 or 404 here is a *permission*
        answer, not an outage, so it is converted to `None` rather than
        allowed to reach the health circuit — three unentitled tickers would
        otherwise cool the vendor down and take its working quote and news
        endpoints with it.
        """
        try:
            rows = self._get_json(
                f"{self.BASE}/tiingo/fundamentals/{symbol}/statements",
                params={"asReported": "false"},
                headers=self._headers(),
                operation="fundamentals",
            )
        except VendorError as exc:
            message = str(exc).lower()
            if any(code in message for code in ("403", "404", "not permissioned", "not found")):
                logger.debug("tiingo fundamentals not entitled for %s", symbol)
                return None
            raise

        if not isinstance(rows, list) or not rows:
            return None

        # Newest statement first; quarterly preferred over annual because the
        # trend detection downstream compares consecutive periods.
        rows = sorted(rows, key=lambda r: str(r.get("date") or ""), reverse=True)
        latest = rows[0]
        flat = _flatten_statement(latest)
        if not flat:
            return None

        return Fundamentals(
            symbol=symbol,
            period=str(latest.get("date") or "")[:10],
            quarter=latest.get("quarter"),
            year=latest.get("year"),
            revenue=_f(flat.get("revenue")),
            gross_profit=_f(flat.get("grossProfit")),
            operating_income=_f(flat.get("opinc")),
            net_income=_f(flat.get("netinc")),
            eps=_f(flat.get("eps")),
            shares_diluted=_f(flat.get("shareswadil")) or _f(flat.get("sharesBasic")),
            total_assets=_f(flat.get("totalAssets")),
            total_liabilities=_f(flat.get("totalLiabilities")),
            equity=_f(flat.get("equity")),
            cash=_f(flat.get("cashAndEq")),
            debt=_f(flat.get("debt")),
            free_cash_flow=_f(flat.get("freeCashFlow")),
            operating_cash_flow=_f(flat.get("ncfo")),
            ebitda=_f(flat.get("ebitda")),
            # Prior periods travel with the latest so trend detection needs no
            # second round trip against a rate limit this tight.
            history=[
                {
                    "period": str(row.get("date") or "")[:10],
                    **{k: _f(v) for k, v in _flatten_statement(row).items()
                       if k in _TREND_FIELDS and _f(v) is not None},
                }
                for row in rows[1:9]
                if _flatten_statement(row)
            ],
        )


_TREND_FIELDS = {
    "revenue", "grossProfit", "opinc", "netinc", "eps",
    "freeCashFlow", "debt", "cashAndEq", "totalAssets", "equity", "ebitda",
}


def _flatten_statement(row: dict[str, Any]) -> dict[str, Any]:
    """Tiingo nests statements as {statementData: {incomeStatement: [{dataCode, value}]}}.

    Flattened to `{dataCode: value}` because every consumer downstream wants
    "revenue", not "the third entry of the income statement array".
    """
    block = row.get("statementData")
    if not isinstance(block, dict):
        return {}
    flat: dict[str, Any] = {}
    for statement in block.values():
        if not isinstance(statement, list):
            continue
        for item in statement:
            if isinstance(item, dict) and item.get("dataCode") is not None:
                flat[str(item["dataCode"])] = item.get("value")
    return flat
