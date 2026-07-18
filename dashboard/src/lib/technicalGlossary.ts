/* ============================================================
   Technical-indicator glossary — authored reference content for every
   indicator the Technical Intelligence engine reports. Same discipline as
   metricGlossary.ts: this file computes NOTHING and contains no ticker
   data. Every number the user sees comes from the deterministic engine
   (src/scoring/technical_intelligence.py); this file only explains what
   each standard indicator means, how it's built, when it helps, and where
   it fails. Keyed by the engine's indicator `key`.
   ============================================================ */

import type { MetricEntry } from './metricGlossary'

export const TECHNICAL_GLOSSARY: Record<string, MetricEntry> = {
  sma: {
    label: 'Moving averages (20/50/200)',
    short: 'The average closing price over the last 20, 50 and 200 trading days — the market’s short-, medium- and long-term trend lines.',
    formula: 'SMA(n) = mean of the last n closes.',
    interpretation:
      'Price above a rising average means buyers have been in control over that horizon; below a falling average, sellers. The 200-day is the classic institutional dividing line between long-term uptrends and downtrends.',
    good: 'Price above all three averages, with the averages stacked 20 > 50 > 200 and rising.',
    bad: 'Price below all three with the stack inverted — every holder since is underwater on average.',
    typicalRange: 'Not bounded — read the price’s position relative to each line, not the line’s level.',
    why: 'Trend context for every other signal: the same RSI reading means different things above and below the 200-day.',
    limitations:
      'Averages lag by construction — they confirm trends, they never anticipate them, and they whipsaw in sideways markets.',
    entersScore:
      'Not a scoring input. The engine’s momentum sleeve uses its own return-based factors; these lines are shown so the reader can verify the trend claim on any chart.',
    references: ['Edwards & Magee, Technical Analysis of Stock Trends'],
  },
  cross: {
    label: 'Golden / death cross',
    short: 'The 50-day average crossing above (golden) or below (death) the 200-day — the most-watched long-term trend change signal.',
    formula: 'Cross of SMA(50) through SMA(200).',
    interpretation:
      'A golden cross says the medium-term trend has overtaken the long-term one — historically associated with the early phase of durable uptrends. A death cross is the mirror image.',
    good: 'A recent golden cross with price holding above both averages.',
    bad: 'A recent death cross, especially with volume confirming the decline.',
    typicalRange: 'Binary event; the engine reports one only when it printed within the last 60 trading days.',
    why: 'It is the single most-followed trend signal in markets — when it prints, it moves positioning whether or not one believes in it.',
    limitations:
      'Extremely lagging: by the time a cross prints, a large part of the move has often happened. Frequent false signals in range-bound markets.',
    entersScore: 'Not a scoring input — reported for trend context only.',
    references: ['Brock, Lakonishok & LeBaron (1992), Journal of Finance'],
  },
  macd: {
    label: 'MACD (12, 26, 9)',
    short: 'Moving-average convergence/divergence — measures whether price momentum is building or fading.',
    formula: 'MACD line = EMA(12) − EMA(26); signal = EMA(9) of the line; histogram = line − signal.',
    interpretation:
      'A positive histogram means momentum is improving relative to its own recent pace; negative means fading. It measures the change in momentum, not its level.',
    good: 'Histogram positive and expanding while price makes new highs.',
    bad: 'Price making new highs while the histogram shrinks — momentum divergence.',
    typicalRange: 'Unbounded and price-scale dependent — compare the sign and direction, never the absolute value across stocks.',
    why: 'The fastest of the classic trend gauges — it turns before the moving averages themselves do.',
    limitations:
      'Price-scale dependent: on a falling stock the histogram mechanically contracts toward zero as the price shrinks, which can read as “improving” during a long decline. Whipsaws badly in flat markets.',
    entersScore:
      'A MACD state variant feeds the engine’s momentum sleeve as a low-weight (0.5) trend feature; the value here is recomputed from the same price history for display.',
    references: ['Appel (1979)'],
  },
  rsi: {
    label: 'RSI (14)',
    short: 'Relative Strength Index — how one-sided the last 14 days of gains vs losses have been, on a 0–100 scale.',
    formula: 'RSI = 100 − 100 / (1 + avg gain / avg loss), Wilder-smoothed over 14 days.',
    interpretation:
      'Above 70 the recent advance has been unusually one-sided (overbought); below 30, unusually one-sided selling (oversold). Between 40–60 it says little.',
    good: 'Oversold readings (<30) inside an intact uptrend often mark tactical entry points.',
    bad: 'Overbought readings (>70) after a long advance flag near-term pullback risk — they do not, alone, end trends.',
    typicalRange: '0–100; most of the time between 30 and 70.',
    why: 'The most widely used mean-reversion gauge; extremes are genuinely informative about short-term risk/reward.',
    limitations:
      'In strong trends RSI can stay pinned above 70 (or below 30) for weeks — “overbought” is not a sell signal by itself.',
    entersScore:
      'An RSI z-score is a display-adjacent input to the engine’s reversal sleeve, which only carries weight (0.20) in high-volatility regimes; elsewhere it is display-only.',
    references: ['Wilder (1978), New Concepts in Technical Trading Systems'],
  },
  adx: {
    label: 'ADX (14)',
    short: 'Average Directional Index — measures how strongly price is trending, regardless of direction.',
    formula: 'Wilder-smoothed ratio of directional movement (+DM/−DM) to true range; +DI/−DI give the direction, ADX the strength.',
    interpretation:
      'ADX above ~25 means a real trend is in force (read +DI vs −DI for its direction); below 20 the market is range-bound and trend-following signals degrade.',
    good: 'ADX > 25 with +DI leading — trend-following entries have the wind at their back.',
    bad: 'ADX > 25 with −DI leading, or trend signals taken while ADX < 20.',
    typicalRange: '0–100 in theory; readings above 40 are strong, above 60 rare.',
    why: 'It answers the first question of technical analysis — is there even a trend to follow? — before any directional signal is trusted.',
    limitations: 'Lags at turning points and says nothing about direction by itself.',
    entersScore: 'Not a scoring input — used to classify the trend regime shown above.',
    references: ['Wilder (1978)'],
  },
  atr: {
    label: 'ATR (14)',
    short: 'Average True Range — the stock’s typical daily trading range, shown as a percentage of price.',
    formula: 'Wilder-smoothed average of the true range (max of high−low, |high−prior close|, |low−prior close|).',
    interpretation:
      'A 3% ATR means a normal day moves the stock about 3%. The engine also reports where today’s ATR sits in the stock’s own one-year distribution — the volatility regime.',
    good: 'Compressed ATR (low percentile) — quiet ranges often precede larger directional moves.',
    bad: 'Elevated ATR (top percentile) — position sizing and stop distances must widen; risk per share is higher.',
    typicalRange: 'Large caps commonly 1–3% of price; high-beta names 4–8%.',
    why: 'Volatility is the denominator of every position-sizing decision; ignoring it is how correct ideas lose money.',
    limitations: 'Says nothing about direction; regime shifts can be abrupt.',
    entersScore:
      'Not this display value directly — but the engine’s risk score uses volatility percentiles of the same construction, and high-vol regimes rebalance the sleeve weights.',
    references: ['Wilder (1978)'],
  },
  bollinger: {
    label: 'Bollinger Bands (20, 2σ)',
    short: 'A ±2 standard-deviation envelope around the 20-day average; %B says where price sits inside it.',
    formula: '%B = (price − lower band) / (upper − lower); bandwidth = (upper − lower) / price.',
    interpretation:
      '%B near 1 means price is pressing the statistical ceiling of its recent range; near 0, the floor. Narrow bandwidth (a “squeeze”) marks unusually quiet markets that often precede expansion.',
    good: '%B near 0 in an uptrend (pullback to statistical support); a squeeze resolving upward.',
    bad: '%B pinned near 1 with fading volume — extension without sponsorship.',
    typicalRange: '%B mostly 0–1; excursions beyond happen in strong moves.',
    why: 'It normalizes “is this move stretched?” against the stock’s own recent volatility instead of a fixed rule.',
    limitations: 'Bands widen after volatility arrives — like all volatility tools, they describe, they don’t predict.',
    entersScore: 'Not a scoring input — presentation context for the range position.',
    references: ['Bollinger (2001), Bollinger on Bollinger Bands'],
  },
  stoch: {
    label: 'Stochastic (14, 3)',
    short: 'Where today’s close sits inside the last 14 days’ high-low range, 0–100.',
    formula: '%K = 100 × (close − 14d low) / (14d high − 14d low); %D = 3-day average of %K.',
    interpretation:
      'Above 80: closing near the top of the recent range (overbought). Below 20: near the bottom (oversold). Crosses of %K through %D are the classic timing trigger.',
    good: 'Oversold readings in an uptrend — the highest-quality mean-reversion setup.',
    bad: 'Overbought readings with momentum divergence.',
    typicalRange: '0–100.',
    why: 'Faster than RSI at flagging short-term extremes; useful for entry timing rather than thesis.',
    limitations: 'Very noisy; in trends it stays pinned just like RSI.',
    entersScore: 'Not a scoring input.',
    references: ['Lane (1950s), popularized in Technical Analysis of Stocks & Commodities'],
  },
  obv: {
    label: 'On-balance volume',
    short: 'A running total that adds volume on up days and subtracts it on down days — does volume back the price move?',
    formula: 'OBV += volume on up closes; OBV −= volume on down closes.',
    interpretation:
      'When OBV rises with price, real participation backs the move. When price rises but OBV falls, the advance is happening on thin conviction — a classic warning.',
    good: 'OBV confirming price direction over the last month.',
    bad: 'OBV diverging from price — moves without sponsorship reverse more often.',
    typicalRange: 'Unbounded running total — only its direction matters.',
    why: 'Volume is the only direct footprint of institutional participation available in free daily data.',
    limitations: 'One heavy day can distort it; gaps and index-rebalance days add noise.',
    entersScore: 'Not a scoring input — drives the volume-confirmation regime shown above.',
    references: ['Granville (1963), New Key to Stock Market Profits'],
  },
  mfi: {
    label: 'Money Flow Index (14)',
    short: 'A volume-weighted RSI: are dollars flowing in or out over the last 14 days?',
    formula: 'Like RSI but each day’s typical price × volume is what gets averaged.',
    interpretation: 'Above 80: heavy dollar inflow, stretched. Below 20: heavy outflow, washed out.',
    good: 'MFI < 20 while price holds support — selling pressure exhausting itself.',
    bad: 'MFI > 80 into resistance.',
    typicalRange: '0–100.',
    why: 'Adds the "how much money" dimension RSI lacks.',
    limitations: 'Inherits both RSI’s pinning problem and OBV’s sensitivity to single heavy days.',
    entersScore: 'Not a scoring input.',
    references: ['Quong & Soudack (1989)'],
  },
  cci: {
    label: 'CCI (20)',
    short: 'Commodity Channel Index — how far today’s price sits from its 20-day typical level, in units of normal deviation.',
    formula: 'CCI = (typical price − 20d SMA of typical) / (0.015 × mean absolute deviation).',
    interpretation: 'Beyond ±100 marks an unusually strong move in that direction; the zero line is the mean.',
    good: 'CCI recovering from below −100 — a washout reverting.',
    bad: 'CCI fading from above +100 while price stalls.',
    typicalRange: 'Roughly ±100 covers ~75% of readings.',
    why: 'A deviation-based complement to the range-based oscillators (RSI, stochastic).',
    limitations: 'The 0.015 scaling constant is arbitrary; noisy on quiet stocks.',
    entersScore: 'Not a scoring input.',
    references: ['Lambert (1980), Commodities magazine'],
  },
  roc: {
    label: 'Rate of change (63d)',
    short: 'The simple percentage move over the last quarter of trading — raw momentum.',
    formula: 'ROC = price today / price 63 trading days ago − 1.',
    interpretation: 'Positive quarterly momentum tends to persist over the following weeks — the base of the momentum literature.',
    good: 'Solidly positive alongside a trend the averages confirm.',
    bad: 'Deeply negative — catching falling knives fights the strongest documented anomaly in markets.',
    typicalRange: '±15% covers a typical large-cap quarter.',
    why: 'The most honest momentum number: no smoothing, no parameters, verifiable in two data points.',
    limitations: 'One quarter of history in a single number — reversals show up all at once.',
    entersScore:
      'A t-statistic version of short/medium return momentum is a core input to the engine’s momentum sleeve; this display value is the unnormalized cousin.',
    references: ['Jegadeesh & Titman (1993), Journal of Finance'],
  },
  aroon: {
    label: 'Aroon (25)',
    short: 'How recently the stock printed its 25-day high (Aroon up) and 25-day low (Aroon down).',
    formula: 'Aroon up = 100 × (25 − days since 25d high) / 25; down likewise for the low.',
    interpretation:
      'Up > 70 with down < 30: highs are fresh, lows are stale — an established uptrend. The reverse marks a downtrend.',
    good: 'Fresh highs (up > 70, down < 30).',
    bad: 'Fresh lows (down > 70, up < 30).',
    typicalRange: '0–100 each.',
    why: 'A time-based read of trend freshness that price-based tools miss.',
    limitations: 'Coarse; jumps in steps of 4 with a 25-day window.',
    entersScore: 'Not a scoring input.',
    references: ['Chande (1995)'],
  },
  vwap: {
    label: 'VWAP (20-day rolling)',
    short: 'The volume-weighted average price of the last 20 sessions — the average holder’s cost basis over the last month.',
    formula: 'Σ(typical price × volume) / Σ(volume) over 20 days.',
    interpretation:
      'Price above VWAP: the average recent buyer is in profit, which supports dips. Below: the average recent buyer is underwater, which feeds overhead supply.',
    good: 'Price holding above a rising VWAP.',
    bad: 'Repeated rejections at a falling VWAP.',
    typicalRange: 'Tracks price; read the relationship, not the level.',
    why: 'Institutions benchmark executions against VWAP — it is a level real money actually defends.',
    limitations: 'A daily-bar approximation of an intraday construct; the standard intraday VWAP resets each session.',
    entersScore: 'Not a scoring input.',
    references: ['Berkowitz, Logue & Noser (1988), Journal of Finance'],
  },
  levels: {
    label: 'Support & resistance (40d swings)',
    short: 'The lowest low and highest high of the last 40 sessions — the range’s floor and ceiling.',
    formula: 'Support = 40-day minimum low; resistance = 40-day maximum high.',
    interpretation:
      'Distance to each level frames the near-term risk/reward: little room below support means stops are cheap; little room to resistance means the easy part of the move is done.',
    good: 'Price just above well-tested support with several percent of room to resistance.',
    bad: 'Price pressed against resistance with support far below.',
    typicalRange: 'Ticker-specific price levels.',
    why: 'Objective, reproducible levels — no chart-reading subjectivity, anyone can verify them.',
    limitations:
      'Swing extremes are one definition of many; breakouts routinely pierce these levels before reversing (false breaks).',
    entersScore: 'Not a scoring input.',
    references: ['Edwards & Magee, Technical Analysis of Stock Trends'],
  },
}

/* Street & insider readings (v4.5 P0-B) — same authored-reference discipline. */
export const STREET_GLOSSARY: Record<string, MetricEntry> = {
  recommendations: {
    label: 'Analyst recommendation trend',
    short: 'How many covering analysts rate the stock buy/hold/sell, and whether that mix has been improving or deteriorating month over month.',
    formula: 'Buy ratio = (strong buy + buy) / total ratings; trend compares the ratio across the last four monthly snapshots.',
    interpretation:
      'The level shows consensus; the trend shows where consensus is heading. Revisions move prices more than levels — a 60% buy ratio that was 45% three months ago is a stronger signal than a static 70%.',
    good: 'A rising buy ratio — upgrades outpacing downgrades.',
    bad: 'A falling ratio, especially from a high level: early distribution often shows up in ratings first.',
    typicalRange: 'Large caps average roughly 55–65% buy ratings — sell ratings are structurally rare.',
    why: 'Analyst revisions are one of the best-documented drivers of medium-term returns.',
    limitations:
      'Ratings herd and lag price; sell-side incentives skew the base rate optimistic. Read the trend, discount the level.',
    entersScore: 'Not a scoring input — analyst price targets feed the fundamental sleeve separately; this trend is context.',
    references: ['Womack (1996), Journal of Finance', 'Jegadeesh et al. (2004)'],
  },
  surprises: {
    label: 'EPS surprise history',
    short: 'Whether reported earnings beat or missed consensus estimates in recent quarters, and by how much.',
    formula: 'Surprise % = (actual EPS − estimated EPS) / |estimate|.',
    interpretation:
      'A consistent beat record means management guides conservatively and executes; repeated misses mean estimates are running ahead of the business. Post-earnings drift makes recent surprises predictive, not just descriptive.',
    good: 'Consistent beats with a positive average surprise.',
    bad: 'Consecutive misses — consensus is still too high, and further cuts usually follow.',
    typicalRange: 'S&P 500 companies beat roughly 70–75% of the time (managed expectations); the informative part is the magnitude and the exceptions.',
    why: 'Execution against expectations is the cleanest quarterly test of management credibility available for free.',
    limitations: 'EPS is manageable (buybacks, one-offs); a beat on collapsing revenue quality is not a beat.',
    entersScore: 'The most recent surprise feeds the engine\'s PEAD factor (drift window); this panel shows the fuller record.',
    references: ['Bernard & Thomas (1989) — post-earnings-announcement drift'],
  },
  insider: {
    label: 'Insider sentiment (MSPR)',
    short: 'Finnhub\'s monthly share purchase ratio: are the company\'s own officers and directors net buyers or net sellers, −100 to +100.',
    formula: 'MSPR aggregates insider buy vs sell transactions, weighted by size, over the month.',
    interpretation:
      'Insiders sell for many reasons (compensation, diversification) but buy for essentially one: they expect the stock to rise. Sustained readings beyond ±20 carry signal; small negatives are background noise.',
    good: 'MSPR above +20 — conviction buying by the people with the best information.',
    bad: 'MSPR below −20 — selling beyond routine compensation patterns.',
    typicalRange: 'Mildly negative most of the time (stock comp creates structural selling).',
    why: 'Insider trades are disclosed by law and are among the few genuinely non-public-information-adjacent signals a free platform can offer.',
    limitations: '10b5-1 scheduled plans blur intent; small caps have thin insider activity and noisy readings.',
    entersScore: 'Not a scoring input — surfaced as context alongside the deterministic verdict.',
    references: ['Cohen, Malloy & Pomorski (2012), Journal of Finance'],
  },
}
