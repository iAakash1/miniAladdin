/* ============================================================
   Validation page glossary — static, authored reference content for
   every metric OmniSignal's walk-forward validation reports.

   This module contains NO ticker data and computes nothing: every
   number a user sees on the Validation page still comes from
   src/services/backtest_service.py. This file only explains, in
   plain English, what an already-standard statistical or finance
   concept means, why it's good or bad, and where it comes from in
   the literature — the same way a footnote in a research report
   would, not a live computation.
   ============================================================ */

export interface MetricEntry {
  label: string
  short: string // one line, for the quick-glance tooltip
  formula?: string
  interpretation: string
  good: string
  bad: string
  typicalRange: string
  why: string
  references: string[]
  /** Optional — used by factorGlossary.ts entries (Methodology Center),
   *  left blank for validation metrics. Kept on the shared type so both
   *  glossaries can reuse the same MetricEntry shape and MetricExplainer
   *  component instead of two near-duplicate ones. */
  limitations?: string
  entersScore?: string
}

export type MetricKey =
  | 'ic'
  | 'rollingIc'
  | 'hitRate'
  | 'winRate'
  | 'sharpe'
  | 'sortino'
  | 'calmar'
  | 'maxDrawdown'
  | 'annualReturn'
  | 'volatility'
  | 'confusionMatrix'
  | 'calibration'
  | 'scoreDistribution'
  | 'psi'
  | 'factorStability'
  | 'factorCorrelation'

export const METRIC_GLOSSARY: Record<MetricKey, MetricEntry> = {
  ic: {
    label: 'Information Coefficient (IC)',
    short: 'Rank correlation between the signal and what actually happened next.',
    formula: 'IC = Spearman correlation( score_t , forward_return_{t→t+21} )',
    interpretation:
      'Measures whether higher scores actually preceded higher subsequent returns, using rank rather than raw values so outliers cannot dominate it.',
    good: 'Sustained |IC| above roughly 0.05 for a single name is considered meaningful in the factor-investing literature; above 0.10 is strong for any individual signal.',
    bad: 'IC near zero means the score carries no information about future returns; a consistently negative IC means the signal is backwards.',
    typicalRange: '-0.15 to +0.15 for most single-name equity signals; values near ±0.3 are rare and worth distrusting until re-checked out of sample.',
    why: 'IC is the standard way quant desks grade a signal before ever trading it, because it isolates predictive skill from luck in any one period.',
    references: ['Grinold & Kahn, "Active Portfolio Management" (the IC/IR framework)', 'Spearman (1904), rank correlation'],
  },
  rollingIc: {
    label: 'Rolling IC',
    short: 'The same IC recomputed on a moving window, to see if predictive skill is stable over time.',
    formula: 'Rolling IC_w = Spearman correlation over the most recent w signal dates',
    interpretation:
      'A single IC number hides whether a signal worked steadily or only during one lucky stretch. Plotting it over rolling windows shows whether skill is persistent, decaying, or regime-dependent.',
    good: 'A rolling IC that stays on the same side of zero across most windows, even if the magnitude wobbles.',
    bad: 'A rolling IC that flips sign repeatedly, or that was strong historically but has decayed to zero in the most recent windows.',
    typicalRange: 'Same scale as IC (roughly ±0.15); the useful signal here is the trend and sign-stability, not any single window\'s value.',
    why: 'A model whose average IC looks fine can still be quietly broken in the present — rolling IC is how that gets caught.',
    references: ['Grinold & Kahn, "Active Portfolio Management"'],
  },
  hitRate: {
    label: 'Hit Rate',
    short: 'Of the calls where the model actually took a directional view, the share that were right.',
    formula: 'Hit rate = correct directional calls / total non-Hold calls',
    interpretation:
      'Unlike IC, this only scores Buy/Sell-type calls (Holds are excluded), so it answers "when the model committed to a direction, how often was it right."',
    good: 'Above 55% on a reasonable sample size (dozens of calls) is a real edge for a single-name directional signal; above 60% is strong.',
    bad: 'At or below 50% means the directional calls are no better than a coin flip, regardless of how confident they looked.',
    typicalRange: '48%–58% is common for equity signals; anything above ~65% on a small sample is more likely noise than skill.',
    why: 'Confidence and risk framing mean little if the underlying directional calls aren\'t beating chance — hit rate is the plain-language check on that.',
    references: ['Standard classification accuracy, applied to directional trading signals'],
  },
  winRate: {
    label: 'Win Rate (invested days)',
    short: 'Share of the days the strategy was actually long that ended up positive.',
    formula: 'Win rate = positive-return invested days / total invested days',
    interpretation:
      'Different from hit rate: this looks at daily P&L while a position was held, not at whether the initiating call was directionally correct over the full 21-day horizon.',
    good: 'Above 50%, ideally with average wins at least as large as average losses (see Sharpe/Sortino for that balance).',
    bad: 'A win rate near or below 50% combined with a low Sharpe suggests small, frequent wins are being wiped out by occasional large losses.',
    typicalRange: '48%–54% is typical for daily equity returns even in a genuinely profitable strategy — win rate alone is a weak signal without magnitude context.',
    why: 'Shown alongside average holding period and time invested so a strategy that "wins often but small, loses rarely but big" doesn\'t look better than it is.',
    references: ['Standard trading-strategy diagnostics'],
  },
  sharpe: {
    label: 'Sharpe Ratio',
    short: 'Annualized return per unit of total volatility.',
    formula: 'Sharpe = mean(daily return) / std(daily return) × √252',
    interpretation: 'Higher means more return was earned for the risk (volatility) taken on, treating upside and downside swings symmetrically.',
    good: 'Above 1.0 is considered good for a single-name long/flat strategy; above 2.0 is excellent and worth double-checking for overfitting.',
    bad: 'Below 0 means the strategy lost money on a risk-adjusted basis over the period tested.',
    typicalRange: '0.3–1.2 for most realistic single-name signal strategies over a multi-year window.',
    why: 'The engine\'s own risk-adjusted verdict (raw score vs. risk-adjusted score) mirrors this idea — Sharpe is the industry-standard way to check that trade-off empirically.',
    references: ['Sharpe, W. F. (1966), "Mutual Fund Performance," Journal of Business'],
  },
  sortino: {
    label: 'Sortino Ratio',
    short: 'Like Sharpe, but only penalizes downside volatility, not upside swings.',
    formula: 'Sortino = mean(daily return) / std(negative daily returns) × √252',
    interpretation:
      'A strategy with big up days and small down days can have a mediocre Sharpe (both count as "risk") but a strong Sortino, since only the down days count against it.',
    good: 'Above 1.5 is good; a Sortino meaningfully higher than the Sharpe for the same strategy indicates upside-skewed returns, which is a desirable shape.',
    bad: 'A Sortino close to or below the Sharpe for the same series suggests the volatility is not particularly upside-skewed.',
    typicalRange: '0.4–1.8 for most single-name strategies; direct comparison to Sharpe is more informative than the absolute number.',
    why: 'Investors generally don\'t mind volatility that comes from gains — Sortino isolates the risk that actually matters (losses).',
    references: ['Sortino, F. & van der Meer, R. (1991), "Downside Risk," Journal of Portfolio Management'],
  },
  calmar: {
    label: 'Calmar Ratio',
    short: 'Annual return divided by the worst peak-to-trough loss endured to get it.',
    formula: 'Calmar = annualized return / |maximum drawdown|',
    interpretation: 'Answers "how much return did I get for the worst drawdown I had to sit through," which Sharpe and Sortino don\'t directly capture.',
    good: 'Above 1.0 means annual return exceeded the worst drawdown; above 2.0 is strong.',
    bad: 'Below 0.5 means even a modest annual return required tolerating a large drawdown to get it.',
    typicalRange: '0.3–1.5 for most single-name signal strategies over a multi-year backtest.',
    why: 'Drawdown is what actually drives investors to abandon a strategy at the worst time — Calmar keeps that front and center next to the headline return.',
    references: ['Young, T. (1991), the Calmar ratio, as used in managed-futures reporting'],
  },
  maxDrawdown: {
    label: 'Maximum Drawdown',
    short: 'The largest peak-to-trough decline the strategy experienced in the tested window.',
    formula: 'Max drawdown = min( equity_t / running_peak_equity_t − 1 )',
    interpretation: 'The single worst-case loss an investor following the signal would have had to sit through, from any prior peak.',
    good: 'Smaller in magnitude (closer to 0%) relative to the strategy\'s annual return.',
    bad: 'A drawdown deeper than the annualized return, or one that took a long time to recover from.',
    typicalRange: '-15% to -40% is common for single-name long/flat equity strategies over several years — equities are volatile even with a decent signal.',
    why: 'Confidence and risk scores mean little without knowing the worst case a holder actually lived through — this is that number.',
    references: ['Standard drawdown analysis, used throughout hedge fund and CTA reporting'],
  },
  annualReturn: {
    label: 'Annualized Return',
    short: 'The daily strategy returns, compounded and scaled to a one-year figure.',
    formula: 'Annual return = (1 + mean daily return)^252 − 1',
    interpretation: 'Makes strategies tested over different windows comparable by expressing them on the same one-year basis.',
    good: 'Meaningfully above the buy-and-hold return shown alongside it for the same ticker and window.',
    bad: 'Below the buy-and-hold return, or negative — meaning the signal would have been worse than doing nothing.',
    typicalRange: 'Highly ticker- and period-dependent; always read next to buy-and-hold and volatility, never in isolation.',
    why: 'Shown next to buy-and-hold specifically so a good-looking return that\'s just "the stock went up" isn\'t mistaken for signal skill.',
    references: ['Standard annualization of geometric daily returns'],
  },
  volatility: {
    label: 'Annualized Volatility',
    short: 'How much daily returns swing, scaled to an annual basis.',
    formula: 'Volatility = std(daily return) × √252',
    interpretation: 'The denominator behind Sharpe — higher volatility means a given return was earned (or lost) with bigger day-to-day swings.',
    good: 'Lower volatility for the same or better return is strictly preferable; the strategy\'s number is usually below buy-and-hold\'s if the signal is reducing time in market during rough patches.',
    bad: 'Volatility at or above buy-and-hold with a lower return means the signal added risk without adding return.',
    typicalRange: '15%–35% annualized for individual equities, versus roughly 15%–20% for a broad index like SPY.',
    why: 'Read together with time-invested — a signal that\'s only in the market part of the time should usually show lower volatility than buy-and-hold.',
    references: ['Standard annualized volatility, the basis of the Sharpe ratio'],
  },
  confusionMatrix: {
    label: 'Confusion Matrix',
    short: 'How each signal direction (long / flat / short) lined up with what actually happened.',
    interpretation:
      'Rows are what the signal said; columns are what the market did over the following 21 days. Mass on the diagonal is correct calls, mass off the diagonal is wrong-way calls.',
    good: 'Long calls concentrated in the "realized up" column, short calls concentrated in "realized down."',
    bad: 'A long row with more mass in "realized down" than "realized up" — the model\'s bullish calls are backwards.',
    typicalRange: 'No universal target range; judge it relative to hit rate and sample size (a matrix built on a handful of calls is not reliable).',
    why: 'Aggregate hit rate can hide a model that\'s good at "flat" but bad at picking direction — the matrix shows exactly where the errors concentrate.',
    references: ['Standard confusion matrix, applied to directional trading signals'],
  },
  calibration: {
    label: 'Confidence Calibration',
    short: 'Whether a signal shown with X% confidence was actually right about X% of the time.',
    formula: 'Per confidence bucket: realized hit rate vs. the bucket\'s expected (midpoint) confidence',
    interpretation:
      'A reliability diagram. If the 70% confidence bucket only won 55% of the time historically, the engine\'s confidence score is overstated for that bucket, and should be read with a discount.',
    good: 'Realized hit rate tracks close to the expected marker across most buckets.',
    bad: 'Realized hit rate sitting well below the marker in every bucket (systematic overconfidence), especially in high-confidence buckets.',
    typicalRange: 'A gap of a few percentage points between expected and realized is normal on modest sample sizes; a gap over ~15 points in a well-populated bucket is worth distrusting.',
    why: 'Confidence is only useful if it\'s honest — calibration is the direct test of whether the number can be taken at face value.',
    references: ['Reliability diagrams, standard in forecast verification (meteorology and ML both use this exact tool)'],
  },
  scoreDistribution: {
    label: 'Score Distribution',
    short: 'How the composite score was spread across all walk-forward samples.',
    interpretation:
      'A healthy signal should spend most of its time near zero (Hold) with occasional excursions to the action thresholds — not permanently pinned at an extreme.',
    good: 'A roughly bell-shaped distribution centered near zero, with meaningful but not dominant mass in the action tails.',
    bad: 'A distribution stuck at one extreme (the model is "always bullish" or "always bearish" regardless of conditions), or a distribution that never reaches the action thresholds at all (the model never actually calls anything).',
    typicalRange: 'Most mass within ±0.3 of zero is typical; the action thresholds sit further out by design.',
    why: 'A model that\'s always maximally confident in one direction is a red flag independent of its IC — this is the shape check.',
    references: ['Standard histogram diagnostics for model output distributions'],
  },
  psi: {
    label: 'Population Stability Index (PSI) — distribution drift',
    short: 'How much the shape of the score distribution changed between the first and second half of the test window.',
    formula: 'PSI = Σ (q_i − p_i) × ln(q_i / p_i), over score-histogram buckets i (p = first half, q = second half)',
    interpretation:
      'A model whose output distribution has drifted materially between two halves of the same backtest may be behaving differently now than when it was validated, even if the average IC over the full period still looks fine.',
    good: 'PSI below 0.10 — the score distribution is stable across the window.',
    bad: 'PSI above 0.25 is a standard industry threshold for meaningful drift, worth investigating before trusting the model\'s current behavior.',
    typicalRange: '0.00–0.10 stable, 0.10–0.25 moderate shift worth watching, above 0.25 significant drift.',
    why: 'IC and Sharpe are averages over the whole window and can hide a model that has quietly changed behavior partway through — PSI is the direct test for that.',
    references: ['PSI is standard in credit-risk model monitoring (e.g., Basel model-validation guidance) and is used the same way here for a scoring model'],
  },
  factorStability: {
    label: 'Factor Stability (sign stability)',
    short: 'The fraction of rolling windows where a factor\'s relationship with future returns kept the same sign as its overall average.',
    formula: 'Sign stability = (# rolling windows where sign(window IC) = sign(overall IC)) / (# rolling windows)',
    interpretation:
      'A factor with a positive average IC that flips negative in half its rolling windows is not a reliable contributor, even though its headline number looks fine.',
    good: '0.7 or higher — the factor points the same direction in most windows.',
    bad: 'Below 0.5 — the factor\'s relationship with returns is essentially a coin flip over time, so its average IC is likely noise rather than skill.',
    typicalRange: '0.5–0.9 across the engine\'s factor set; momentum factors tend to sit higher than fundamental factors given fewer point-in-time data points.',
    why: 'This is the per-factor version of rolling IC — it is what the engine\'s own KEEP / MODIFY / REMOVE factor audit is based on, so it\'s shown here rather than only in an internal doc.',
    references: ['Grinold & Kahn, "Active Portfolio Management" (factor stability and IC decay)'],
  },
  factorCorrelation: {
    label: 'Factor Correlation',
    short: 'How closely two factors move together in rank, across the same walk-forward samples.',
    formula: 'Correlation(A, B) = Spearman correlation of factor A and factor B scores over shared dates',
    interpretation:
      'Two highly correlated factors are not really adding two independent opinions to the composite score — they\'re one opinion counted twice, which understates true uncertainty.',
    good: 'Most pairs below about 0.5 in absolute value — the factor set is contributing largely independent information.',
    bad: 'A pair above 0.8 in absolute value signals near-duplicate factors; the composite\'s effective number of independent signals is lower than its factor count suggests.',
    typicalRange: '-0.3 to +0.5 for most factor pairs in a well-designed multi-factor model; momentum sub-factors (e.g. different lookback windows) are the most likely to run higher.',
    why: 'Directly informs whether the "factor count" backing a score is real diversification or partly redundant — relevant context for reading the factor-contribution breakdown on any research report.',
    references: ['Standard pairwise correlation analysis in factor-model construction'],
  },
}
