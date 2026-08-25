# Screenshots

Every image in this directory is a capture of the **live production
deployment**. None is a mockup, a local build, or a composite.

| | |
|---|---|
| **Environment** | Production |
| **Frontend** | `https://mini-aladding.vercel.app` (Vercel) |
| **Backend** | `https://minialaddin-d8oe.onrender.com` (Render) |
| **Deployed commit** | `61c732e` — reported by `/api/health` at capture time |
| **Symbol** | AAPL |
| **Captured** | 2026-08-25 |
| **Viewport** | 1360 × 1000 CSS px at DPR 2 (retina) |
| **Method** | Chrome DevTools Protocol against a signed-in browser, clipped per section |

## What each image shows

| File | Section | Demonstrates | Data |
|---|---|---|---|
| `01-company-overview.png` | `#overview` | Identity, last close, cross-vendor price consensus, risk-adjusted verdict | Live — Logo.dev mark, 3/3 vendors agreeing at 0.132% spread |
| `02-price-and-consensus.png` | `#price` | Adjusted daily history with volume, and single-asset risk metrics | Live — 3-month window, RSI, Sharpe, Sortino, drawdown |
| `03-quant-scorecard.png` | `#scorecard` | Factor sleeves and their contributions to the score | Live |
| `04-company-profile.png` | `#company` | Reconciled profile — the union of every vendor that answered | Live — 14 fields from 3 vendors, 1 disputed |
| `05-statement-union.png` | `#statements` | Reported statement lines merged across vendors | Live — degraded: Alpha Vantage returned nothing |
| `06-ratios.png` | `#ratios` | Valuation and quality ratios with their inputs | Live |
| `07-sec-filings.png` | `#filings` | Filing index straight from EDGAR — primary source | Live — SEC, 10 recent filings |
| `08-news-intelligence.png` | `#news` | Multi-vendor headlines, deterministic categories, per-article sentiment attribution | Live — 16 unique from GNews + Tavily |
| `09-street-intelligence.png` | `#street` | Analyst ratings, targets and insider activity | Live — Finnhub |
| `10-technical.png` | `#technical` | Deterministic technical read of the same OHLCV frame the engine scored | Live |
| `11-provenance.png` | `#provenance` | **The evidence ledger.** Every input, the vendor that answered, latency, status, and the confidence deductions | Live — 5 live · 4 degraded · 0 unavailable |
| `12-ecosystem.png` | `#ecosystem` | Related companies and sector context | Live |

## Provider behaviour visible in these captures

`11-provenance.png` is the one to read closely — it shows the failure
classification working on real vendors rather than in a fixture:

- `marketstack: rate_limited` on the consensus quote
- `fmp: not_entitled` on the company profile
- `alpha_vantage: unavailable` on reported statements
- `newsapi: unavailable; yahoo_rss: rate_limited; alpha_vantage: unavailable` on news
- `primary (tiingo) unavailable, fell back` on the price history

Four distinct failure modes, each named rather than collapsed into "no data",
and the run still produced a verdict.

## What these captures do *not* show

Production runs `61c732e`. Local `main` is ahead of it, so the following
panels exist in the repository but are **not** in these screenshots:

- ownership and short interest
- analyst positioning
- XBRL restatement detection
- the session strip
- macro context
- series integrity (cross-vendor history agreement)

There is no screenshot of them, because there is no production deployment of
them to photograph. They will be captured once production is redeployed.

## Reproducing

Headless Chrome cannot start in the development environment used here — macOS
denies its mach-port registration (`bootstrap_check_in … Permission denied`)
— so these were captured by driving a normal signed-in Chrome over the
DevTools Protocol:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --user-data-dir=/tmp/omni_shot_profile --remote-debugging-port=9222 \
  https://mini-aladding.vercel.app/company/AAPL
```

then `Page.captureScreenshot` with a clip rectangle taken from each
`.report-section` element's bounding box.
