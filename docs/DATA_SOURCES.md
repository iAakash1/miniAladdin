# Data sources and their limits

## Scope

**US-listed common equities.** The macro gate is built from FRED, the Federal
Funds rate, US CPI, the US yield curve and SPY. Those are not global facts.
Applying this model to an NSE or BSE listing would price the US regime into an
Indian security; international support needs market adapters, not a longer
ticker list.

## Providers

| Capability | Chain |
|---|---|
| Market data | Massive → Tiingo → Polygon → Finnhub → TwelveData → FMP → MarketStack → yfinance |
| Fundamentals | Alpha Vantage → Finnhub → FMP |
| News | NewsAPI → GNews → Yahoo RSS → Tavily |
| Macro | FRED |
| Filings | SEC EDGAR |
| Options | Massive |

Every vendor self-disables without its key, and yfinance plus Yahoo RSS are
keyless anchors, so every chain resolves.

## Licensing caveats

- **yfinance** — its own documentation describes it as for research and
  education, and notes the Yahoo Finance API is intended for personal use. It
  is a legitimate development and fallback source. It is **not** a licensed
  basis for a commercial redistributed data product.
- **FRED** — the API terms require the notice below.
- **Twelve Data** — the free Basic tier is listed as internal, non-display
  use. Check entitlement before rendering its data publicly.
- **Alpha Vantage** — 25 requests/day on the standard free tier; verified
  educational and open-source projects may qualify for more. Real-time and
  15-minute-delayed US market data is premium because of exchange licensing,
  so this product is end-of-day and delayed by design.

### Required FRED notice

> This product uses the FRED® API but is not endorsed or certified by the
> Federal Reserve Bank of St. Louis.

## Freshness

Nothing here is a real-time feed. Prices are daily bars; Explore snapshots are
cached for ten minutes and carry `generated_at` and `data_as_of`. A stale
snapshot is served labelled `stale: true` with its reason rather than
presented as current.

## Positioning

Educational and research. Signals are model outputs under a stated method,
not investment advice, and the product says so on every surface that carries
one.
