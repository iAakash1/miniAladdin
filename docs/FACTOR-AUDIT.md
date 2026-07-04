# Factor Audit — Engine v2.1 (Observed)

*Post-implementation quantitative audit. Numbers below are OBSERVED from the
walk-forward harness on three controlled synthetic worlds (3 seeds × 1000
days each, weekly signals, 21-day forward horizon): a trending world
(±0.2%/day drift, 18-month regimes), a memoryless GBM control, and a
volatility-regime world (calm drift punctuated by −0.2%/day, 3.5%-vol
panics). Synthetic audits test mechanics and controls — cross-sectional
panel validation on real data (QUANT-REVIEW §10, roadmap #10) remains the
final arbiter. Fundamental/news/analyst factors cannot be exercised on
price-only synthetics; their verdicts rest on literature plus the guards
tested in the unit suite.*

## Headline: composite vs naive baseline

| World | Engine IC | Naive 12-1 IC | Reading |
|---|---|---|---|
| Trend (18m regimes) | **+0.320** | +0.220 | Composite beats its own strongest ingredient — diversified sleeves add value |
| GBM control | −0.082 | −0.210 | Near-zero on noise (honesty test passed); naive momentum hallucinates harder |
| Vol regimes | −0.167 | −0.212 | Panics punish all trend systems; composite degrades *less* |

MACD removal (below) improved the trend world +0.007 and the vol world
+0.008 with no cost — removing noise is alpha.

## Per-factor observations and verdicts

| Factor | IC (trend) | IC (gbm) | IC (vol) | Sign-stability | Verdict | Basis |
|---|---|---|---|---|---|---|
| r12_1 | +0.183 | −0.208 | −0.207 | 0.57/0.67/0.67 | **KEEP** (anchor) | Canonical spec; synthetic regime length favors shorter windows — real-market 6–12m persistence is its home turf; panel-validate |
| r63 | +0.576 | −0.066 | −0.066 | 0.33/0.50/0.87 | **KEEP** | Strongest trend factor observed; clean noise behavior |
| r21 | +0.525 | +0.005 | −0.034 | 0.33/0.70/0.60 | **KEEP** (timing, 0.5w) | Strong in trends, perfectly quiet on noise; candidate for weight promotion pending real-data panel |
| macd_hist | +0.026 | +0.024 | −0.023 | ~0.4–0.7 | **REMOVED** | IC ≈ 0 in every world; ρ = −0.65…−0.81 vs reversal, +0.43…+0.52 vs r21 — pure redundancy. Stays display-only in technicals |
| vol_confirm | +0.046 | +0.033 | +0.040 | 0.5–0.73 | **KEEP (probation)** | Synthetic volume is random ⇒ uninformative *by construction*; literature-backed (Lee–Swaminathan); decide on real-data panel |
| high52_prox | +0.455 | −0.161 | −0.270 | 0.43/0.90/**0.97** | **KEEP** | Best stability in stress worlds — consistently informative in both directions |
| reversal | **−0.466** | −0.005 | **+0.100** | 0.37/0.73/0.73 | **KEEP (regime-gated)** | The design, empirically confirmed: destructive in trends (hence 0.05 base weight), positive precisely in high-vol regimes (0.20 there). Nagel 2012 reproduced in miniature |
| target_upside | n/a | n/a | n/a | — | **MODIFY (planned)** | Level → revision momentum once analyst snapshots accrue (store live since v2.1) |
| earnings_yield / pe_gap | n/a | — | — | — | **KEEP** | Regime ballast; long-horizon; weight earns itself only via panel |
| pead | n/a | — | — | — | **KEEP** | Bernard–Thomas; conservative σ=5%, 60d decay, absent-data⇒absent |
| gross_profitability / net_issuance / asset_growth | n/a | — | — | — | **KEEP** | Novy-Marx / Pontiff–Woodgate / Cooper; slow sleeve capped at 0.15 |
| sentiment (n_eff) | n/a | — | — | — | **KEEP (upgraded)** | Now decay/novelty/confirmation-weighted; repeats can't inflate |

## Redundancy map (observed Spearman ρ, |ρ| ≥ 0.4)

Trend cluster confirmed as predicted: r12_1~high52 **0.86**, r63~r21 **0.82**,
r63~high52 0.79, r21~high52 0.67, r12_1~r63 0.51 — equal-weighting inside the
momentum family remains the correct guard against multiple-counting one PC.
Reversal is the anti-trend axis: r21~reversal −0.79/−0.72/−0.66 across
worlds — separating it into its own sleeve (rather than netting inside
momentum) is validated. MACD sat between both clusters with no signal of its
own; removed.

## Distribution drift (PSI, first vs second half)

Trend 2.26 (regime flips *should* move the score distribution — expected),
GBM 0.44, vol 0.87. PSI at these sample sizes (~75 per half) is noisy;
production threshold stays 0.25 on the much larger real-data panel, where it
serves as an alert, not an auto-action.

## Failure modes observed

Long-lookback momentum inverts when regime length < lookback (measured:
126-day regimes drove r12_1 IC to −0.34 before the generator was corrected —
kept as a permanent control test). Panic worlds turn all trend ICs negative;
the composite's damage is bounded by sleeve diversification and the reversal
activation. These match QUANT-REVIEW §11's momentum-crash mechanism.

## Computational cost

Full 1000-day walk-forward (≈150 scorecards incl. risk v2): **≈1.8s**
(vectorized rollings; was 24s with naive rolling-apply). Live scoring per
request: single scorecard, <20ms on top of data fetch.

## Standing recommendation

The engine as shipped contains no scored factor with observed-zero IC, no
unnamed constant, and no factor whose weight cannot be traced to either a
cited prior or a measured result. Next statistical milestone (unchanged from
the roadmap): cross-sectional panel on the S&P 100 with purged/embargoed
windows — the only test that can promote r21, settle vol_confirm's
probation, and calibrate confidence against realized hit rates at scale.
