/* ============================================================
   Methodology Center — factor library. Static, authored reference
   content for every factor the scoring engine actually computes
   (src/scoring/engine.py: momentum_factors, reversal_factor,
   fundamental_factors, quality_factors, news_factor).

   Deliberately excludes two labels that still exist in
   dashboard/src/lib/history.ts's FACTOR_LABELS (macd_hist, rsi_dev):
   MACD was removed from scoring entirely (engine.py comment: "IC≈0,
   redundant") and RSI is consumed only as an input to the merged
   `reversal` factor, not scored on its own — documenting them here as
   if they were independently scored would be inaccurate.

   This file computes nothing and carries no ticker data — it explains
   already-standard, published factor-investing concepts in plain
   English and cites the academic literature, the same way a
   methodology footnote in an institutional research report would.
   Reuses the MetricEntry shape from metricGlossary.ts (and its two
   factor-specific optional fields, limitations/entersScore) so this
   glossary renders through the same MetricExplainer component instead
   of a second bespoke one.
   ============================================================ */

import type { MetricEntry } from './metricGlossary'

export type FactorFamily = 'momentum' | 'reversal' | 'fundamental' | 'quality' | 'news'

export const FAMILY_TITLES: Record<FactorFamily, string> = {
  momentum: 'Momentum',
  reversal: 'Reversal',
  fundamental: 'Fundamental (Value & Earnings)',
  quality: 'Quality',
  news: 'News',
}

export type FactorKey =
  | 'r12_1' | 'r63' | 'r21' | 'vol_confirm' | 'high52_prox' | 'rel21_vs_spy'
  | 'reversal'
  | 'target_upside' | 'earnings_yield' | 'pe_gap' | 'pead'
  | 'gross_profitability' | 'net_issuance' | 'asset_growth'
  | 'sentiment'

export const FACTOR_FAMILY: Record<FactorKey, FactorFamily> = {
  r12_1: 'momentum', r63: 'momentum', r21: 'momentum',
  vol_confirm: 'momentum', high52_prox: 'momentum', rel21_vs_spy: 'momentum',
  reversal: 'reversal',
  target_upside: 'fundamental', earnings_yield: 'fundamental', pe_gap: 'fundamental', pead: 'fundamental',
  gross_profitability: 'quality', net_issuance: 'quality', asset_growth: 'quality',
  sentiment: 'news',
}

export const FACTOR_GLOSSARY: Record<FactorKey, MetricEntry> = {
  r12_1: {
    label: '12-1 Month Momentum',
    short: 'Price return over the past year, skipping the most recent month.',
    formula: 't-statistic of the price return from 231 to 21 trading days ago (skips the most recent ~month)',
    interpretation: 'Stocks that outperformed over the past year, excluding the most recent month, have historically kept outperforming over the following months — the classic momentum anomaly.',
    good: 'A strong, statistically significant positive reading — sustained outperformance over the lookback.',
    bad: 'A strong negative reading — sustained underperformance.',
    typicalRange: 'Z-scored and capped at roughly ±3; most stocks sit within ±1.5.',
    limitations: 'Momentum can reverse sharply in a regime change (a rate-cut pivot, a sector rotation) — the factor reacts to that once it shows in price, it cannot anticipate it.',
    entersScore: 'Momentum family',
    why: 'One of the most extensively documented and persistent equity anomalies; skipping the most recent month specifically removes the short-term reversal effect the model captures as its own separate factor.',
    references: ['Jegadeesh & Titman (1993), "Returns to Buying Winners and Selling Losers"'],
  },
  r63: {
    label: '3-Month Momentum',
    short: 'Price return over the trailing ~3 months (63 trading days).',
    formula: 't-statistic of the price return over the trailing 63 trading days',
    interpretation: 'A shorter-horizon read on the same momentum effect as the 12-1 factor, more responsive to recent shifts.',
    good: 'Positive and statistically significant — recent medium-term strength.',
    bad: 'Negative — recent medium-term weakness.',
    typicalRange: 'Z-scored, capped at roughly ±3.',
    limitations: 'Shorter windows are noisier and more prone to whipsaw than the 12-1 factor.',
    entersScore: 'Momentum family',
    why: 'Captures medium-term trend that the longer 12-1 window can lag.',
    references: ['Jegadeesh & Titman (1993)'],
  },
  r21: {
    label: '1-Month Momentum (timing)',
    short: 'Price return over the trailing 21 trading days — a timing feature, weighted down.',
    formula: 't-statistic of the price return over the trailing 21 trading days',
    interpretation: 'The most recent month of price action, included as a timing signal but weighted down relative to the longer windows since single-month returns are the noisiest and most reversal-prone.',
    good: 'Positive — recent short-term strength.',
    bad: 'Negative — recent short-term weakness.',
    typicalRange: 'Z-scored, capped at roughly ±3.',
    limitations: 'The noisiest of the three momentum windows; a single month of returns carries a lot of randomness.',
    entersScore: 'Momentum family, reduced weight',
    why: 'Adds a timing dimension without letting short-term noise dominate the longer-horizon momentum read.',
    references: ['Jegadeesh & Titman (1993)'],
  },
  vol_confirm: {
    label: 'Volume Confirmation',
    short: 'Whether trading volume is confirming the direction of the 1-month price move.',
    formula: 'Ratio of 21-day to 63-day average volume, signed by the direction of the 1-month return',
    interpretation: 'A price move on rising relative volume is read as more likely to reflect genuine participation than a thin, low-conviction drift.',
    good: 'Elevated relative volume moving in the same direction as the price trend.',
    bad: 'Elevated relative volume moving against the trend, or a trend on thinning volume.',
    typicalRange: 'Z-scored, capped at roughly ±3.',
    limitations: 'Volume data quality varies by vendor and by ticker liquidity; thinly traded names produce noisier ratios.',
    entersScore: 'Momentum family',
    why: 'Formalizes a standard technical-analysis confirmation heuristic as a factor rather than leaving it to visual chart-reading.',
    references: ['Standard volume-price technical analysis'],
  },
  high52_prox: {
    label: '52-Week-High Proximity',
    short: 'How close the current price is to its trailing 52-week high.',
    formula: 'Current price ÷ trailing 252-day high',
    interpretation: 'Stocks trading near their 52-week high have historically continued outperforming — an anchoring effect distinct from pure return momentum.',
    good: 'Trading close to or at the 52-week high.',
    bad: 'Trading well below the 52-week high.',
    typicalRange: 'A ratio from 0 to 1, scored against a level-based reference rather than a t-stat.',
    limitations: 'A pure level effect — it does not distinguish a stock that just made a new high from one that has been stuck near an old high for months.',
    entersScore: 'Momentum family',
    why: 'The 52-week-high anchoring effect is a separate, well-documented driver from time-series return momentum.',
    references: ['George & Hwang (2004), "The 52-Week High and Momentum Investing"'],
  },
  rel21_vs_spy: {
    label: 'Relative Strength vs. SPY',
    short: '1-month return relative to the S&P 500, not just in absolute terms.',
    formula: 't-statistic of the daily return spread (stock minus SPY) over the trailing 21 trading days',
    interpretation: 'Isolates stock-specific strength or weakness from broad market moves — a stock up 5% while the market is up 8% is actually underperforming, and this factor captures that.',
    good: 'Outperforming the broad market over the past month.',
    bad: 'Underperforming the broad market over the past month.',
    typicalRange: 'Z-scored, capped at roughly ±3.',
    limitations: 'Requires enough overlapping trading history with SPY; unavailable for very recently listed tickers.',
    entersScore: 'Momentum family',
    why: 'Separates genuine stock-specific momentum from the stock simply moving with a rising or falling market.',
    references: ['Standard relative-strength methodology (e.g. IBD Relative Strength Rating)'],
  },
  reversal: {
    label: 'Short-Term Reversal',
    short: 'A contrarian signal: extreme 5-day moves and an overbought/oversold RSI tend to partially revert.',
    formula: 'Average of the sign-flipped 5-day return t-statistic and the RSI distribution z-score',
    interpretation: 'Unlike the momentum factors, this one is contrarian by design: a sharp short-term move has historically partially reversed over the following days — a distinct effect from multi-month momentum.',
    good: 'A recent sharp decline (oversold) — read as bullish by this factor specifically.',
    bad: 'A recent sharp rally (overbought) — read as bearish by this factor specifically.',
    typicalRange: 'Z-scored, capped at roughly ±3.',
    limitations: 'Short-term reversal and momentum genuinely pull in opposite directions by design — this is why the composite score can show internal disagreement (see "Conflict" on the research report) rather than a mistake.',
    entersScore: 'Reversal family — its own sleeve, kept separate from Momentum',
    why: 'Short-term reversal and multi-month momentum are two distinct, separately documented effects with different-length lookback windows; merging them into one factor would blur both.',
    references: ['Jegadeesh (1990), "Evidence of Predictable Behavior of Security Returns"', 'Lehmann (1990), "Fads, Martingales, and Market Efficiency"'],
  },
  target_upside: {
    label: 'Analyst Target Upside',
    short: 'Implied upside to the average analyst price target, shrunk toward zero with thin coverage.',
    formula: '(average analyst target − price) ÷ price, shrunk toward zero as analyst-count coverage falls',
    interpretation: "Sell-side analysts' aggregate view of fair value. Shrinkage toward zero when coverage is thin prevents one or two analysts' targets from overweighting the score.",
    good: 'Meaningful implied upside, especially with broad analyst coverage.',
    bad: 'Price already above target, or negative implied upside.',
    typicalRange: 'Roughly -20% to +30% implied upside before shrinkage.',
    limitations: 'Analyst targets are forecasts, not facts, and are known to lag price moves and skew optimistic industry-wide; thin coverage produces a heavily shrunk, near-zero reading.',
    entersScore: 'Fundamental family',
    why: "A market-based consensus view of valuation, independent of the model's own price-derived factors.",
    references: ['Standard sell-side price-target methodology; shrinkage estimation is a standard technique for low-sample-size evidence'],
  },
  earnings_yield: {
    label: 'Earnings Yield',
    short: 'Trailing earnings divided by price — the inverse of the P/E ratio.',
    formula: '1 ÷ trailing P/E ratio',
    interpretation: 'A classic value signal: a higher earnings yield means more earnings per dollar of price paid.',
    good: 'High earnings yield (low P/E) relative to the reference level.',
    bad: 'Low or negative earnings yield (high or negative P/E).',
    typicalRange: 'Roughly 0%–8% for most large caps, centered against a reference level.',
    limitations: "Trailing earnings can be distorted by one-off items, and earnings yield alone doesn't capture growth — a cheap stock can be cheap for a structural reason, not a temporary mispricing.",
    entersScore: 'Fundamental family',
    why: 'One of the most extensively studied value factors in the academic literature.',
    references: ['Basu (1977), "Investment Performance of Common Stocks in Relation to Their P/E Ratios"', 'Fama & French (1992), "The Cross-Section of Expected Stock Returns"'],
  },
  pe_gap: {
    label: 'Forward vs. Trailing P/E Gap',
    short: 'How much cheaper (or more expensive) the stock looks on forward earnings vs. trailing earnings.',
    formula: '(trailing P/E − forward P/E) ÷ trailing P/E',
    interpretation: 'A positive gap means the market expects earnings to grow, since forward P/E sits below trailing P/E — a forward-looking valuation read, not just a backward-looking one.',
    good: 'Forward P/E meaningfully below trailing P/E — expected earnings growth.',
    bad: 'Forward P/E at or above trailing P/E — expected earnings to shrink or stagnate.',
    typicalRange: 'Clipped to ±100% gap; most names sit well inside that band.',
    limitations: 'Forward earnings estimates are themselves analyst forecasts, carrying the same optimism bias and revision risk as analyst price targets.',
    entersScore: 'Fundamental family',
    why: "Complements trailing earnings yield with a forward-looking growth expectation, without the model computing its own earnings forecast.",
    references: ['Standard forward-vs-trailing valuation methodology used across sell-side equity research'],
  },
  pead: {
    label: 'Post-Earnings-Announcement Drift (PEAD)',
    short: 'Stock prices tend to keep drifting in the direction of an earnings surprise for weeks afterward.',
    formula: 'Standardized earnings-surprise percentage, linearly decayed to zero over a fixed post-earnings window',
    interpretation: 'One of the most robust anomalies in the literature: after a large earnings surprise, the market underreacts initially and price keeps drifting in that direction for roughly one to two months.',
    good: 'A recent positive earnings surprise, still within the drift window.',
    bad: 'A recent negative earnings surprise, still within the drift window.',
    typicalRange: 'Decays linearly to zero by the end of the drift window; capped so a single earnings beat cannot dominate the composite score.',
    limitations: 'Only active for a limited number of days after an earnings report — absent outside that window by design, never estimated. Requires a surprise figure the data vendor may not always supply promptly.',
    entersScore: 'Fundamental family',
    why: 'One of the most persistent anomalies in the academic literature, decaying in a well-documented, predictable way — which is why the factor is deliberately time-decayed rather than a flat signal.',
    references: ['Bernard & Thomas (1989), "Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?"'],
  },
  gross_profitability: {
    label: 'Gross Profitability (GP/A)',
    short: 'Gross profit divided by total assets — how efficiently a company turns assets into profit.',
    formula: 'Gross profit ÷ total assets',
    interpretation: 'A quality signal distinct from pure valuation: profitable, asset-efficient companies have historically outperformed even controlling for how cheap they look.',
    good: 'High gross profitability relative to assets.',
    bad: 'Low or negative gross profitability.',
    typicalRange: 'Company- and sector-dependent, centered against a reference level.',
    limitations: 'Varies significantly by industry — an asset-light software company naturally scores differently than a capital-intensive manufacturer — so it is most meaningful cross-sectionally within a sector.',
    entersScore: 'Quality family',
    why: 'One of the strongest quality factors identified in modern factor research, complementing pure value with a profitability lens.',
    references: ['Novy-Marx (2013), "The Other Side of Value: The Gross Profitability Premium"'],
  },
  net_issuance: {
    label: 'Net Share Issuance',
    short: 'Whether the company has been issuing new shares (dilutive) or buying back stock (accretive).',
    formula: 'Year-over-year change in shares outstanding, sign-flipped (issuance reads bearish)',
    interpretation: "Companies that issue substantial new equity have historically underperformed those that buy back shares — issuance is often read as management signaling the stock is fairly or richly valued.",
    good: 'Share count flat or declining (buybacks).',
    bad: 'Meaningful share-count growth (dilutive issuance).',
    typicalRange: 'Most established large caps sit within a few percent year-over-year.',
    limitations: 'Issuance for a genuinely value-accretive acquisition or growth investment looks identical in this factor to issuance driven by weak fundamentals — it cannot distinguish the two.',
    entersScore: 'Quality family',
    why: "A well-documented corporate-finance anomaly, capturing information already embedded in management's own capital-allocation decisions.",
    references: ['Pontiff & Woodgate (2008), "Share Issuance and Cross-Sectional Returns"', 'Daniel & Titman (2006)'],
  },
  asset_growth: {
    label: 'Asset Growth',
    short: 'Year-over-year growth in total assets — rapid growth has historically preceded weaker returns.',
    formula: 'Year-over-year change in total assets, centered on a moderate-growth reference and sign-flipped (high growth reads bearish)',
    interpretation: 'Companies that grow their asset base very rapidly — often through aggressive acquisitions or capital spending — have on average underperformed more disciplined peers, an overinvestment effect.',
    good: 'Moderate, disciplined asset growth.',
    bad: 'Very rapid asset growth.',
    typicalRange: 'Centered around a moderate positive growth rate, not zero — some growth is normal and expected.',
    limitations: 'Does not distinguish good growth (funding genuinely high-return projects) from empire-building; one year of high growth off a low base can look identical to a mature company overexpanding.',
    entersScore: 'Quality family',
    why: 'One of the most robust anomalies in the investment/quality factor literature.',
    references: ['Cooper, Gulen & Schill (2008), "Asset Growth and the Cross-Section of Stock Returns"'],
  },
  sentiment: {
    label: 'News Sentiment',
    short: 'Aggregate tone of recent news headlines, shrunk toward neutral with limited coverage.',
    formula: 'Average headline sentiment, shrunk by effective-evidence weighting (more/fresher headlines carry more weight; duplicates and stale items are down-weighted)',
    interpretation: 'Captures whether recent news flow skews positive or negative — a fast-moving, qualitative complement to the slower-moving fundamental and quality factors.',
    good: 'Sustained positive sentiment across multiple independent sources.',
    bad: 'Sustained negative sentiment across multiple independent sources.',
    typicalRange: '-1 to +1 before shrinkage; pulled toward zero with limited or stale coverage.',
    limitations: "Only as good as the underlying news feed and its sentiment labeling; single sensational headlines are deliberately down-weighted so they can't dominate the score, which also means the factor reacts more slowly to genuinely fast-breaking news than a human reader would.",
    entersScore: 'News family',
    why: "A fast-moving signal the slower price- and fundamentals-based factors can't capture on their own.",
    references: ['Standard NLP sentiment scoring applied to financial headlines; shrinkage estimation is a standard technique for noisy, variable-count evidence'],
  },
}
