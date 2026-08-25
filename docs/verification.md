# Verification status

The distinction this file preserves: **code that compiles is not code that has
run.** Categories are kept separate because collapsing them would be the one
dishonest thing this system could do about itself.

| Level | Meaning |
|---|---|
| **Live — production** | Executed against the real API on `mini-aladding.vercel.app`; the parser has seen a genuine response |
| **Live — local** | Executed against the real API in local development |
| **Reachable, no usable data** | Vendor answered; the answer contained nothing the parser could use. **Not** the same as unconfigured |
| **Not entitled** | Vendor answered with a permission boundary (403). The capability exists; the plan does not cover it |
| **Rate limited** | Vendor answered 429 |
| **Fixture only** | Tested against payloads built from the documented contract. Never executed |

## Observed in production

Measured from one `/api/research/AAPL` call against
`minialaddin-d8oe.onrender.com`, reading the provenance ledger's per-vendor
roster. Production runs commit `61c732e`.

| Provider | Capabilities contributed | Status | Latency |
|---|---|---|---|
| Finnhub | quote, company, fundamentals | **Live — production**, 3/3 | 275–353 ms |
| Tiingo | quote, series, company, fundamentals | **Live — production**, 3/4 | 250–295 ms |
| Polygon | quote, company | **Live — production**, 2/2 | 276–915 ms |
| yfinance | quote, company | **Live — production**, 2/2 | 681–690 ms |
| Twelve Data | quote | **Live — production** | 1838 ms |
| SEC EDGAR | filings | **Live — production** | 469 ms |
| GNews | news | **Live — production** | 1582 ms |
| Tavily | news | **Live — production** | 1766 ms |
| Logo.dev | brand_mark | **Live — production** — resolved `apple.com` by ticker | — |
| Pexels | image_search | **Live — production** — returned a real asset with photographer attribution | — |
| Unsplash | image_search | **Live — production** — listed among contributing providers | — |
| Tiingo *(news)* | news | **Not entitled** — 403; news is a paid add-on | 3030 ms |
| Alpha Vantage | fundamentals, news_sentiment | **Reachable, no usable data** — answered in 243/366 ms with nothing parseable | 243–366 ms |
| NewsAPI | news | **Reachable, no usable data** | 1072 ms |
| Marketstack | quote | **Rate limited** — 429 | 3693 ms |
| Yahoo RSS | news | **Rate limited** — 429 | 905 ms |
| FMP | company | **Not entitled** — 403 on `/profile` | — |

### What this changed

Before this measurement, five providers were documented as fixture-only.
Production shows **Tiingo, Logo.dev, Pexels and Unsplash are genuinely live**;
Tiingo won the series chain outright and contributes to the 5/5 price
consensus.

**Alpha Vantage remains unproven.** It is configured and it answers — quickly —
but returns nothing the parser can use, on both fundamentals and
`NEWS_SENTIMENT`. The likeliest cause is the free tier's daily cap returning an
informational note rather than data. The consequence is concrete:
`news_stream.sentiment` is `null` in production, and the only sentiment-capable
vendor in the system has still never delivered a scored article.

## Frontend

| Surface | Status |
|---|---|
| All research panels | **Compile-verified** — typecheck, lint and production build pass |
| Local rendering | Verified for company overview, consensus, snapshot, statements, ratios, ownership, macro, filings, restatements, provenance, news |
| Production rendering | **Not verified.** Screenshot capture is blocked in this environment: headless Chrome hangs, and `screencapture` lacks screen-recording permission |

No screenshots are committed, because none could be captured. Placeholder
images would be worse than their absence.

## Architectural vs environmental limits

**Architectural** (would need design work): no covariance model, so no
portfolio volatility and no Sharpe ratio; no beta estimation, so benchmark
comparison is a return difference and is labelled as one.

**Environmental** (would resolve with credentials or quota): Alpha Vantage
quota; FMP profile entitlement; Marketstack and Yahoo RSS rate limits; NewsAPI
returning nothing in production.
