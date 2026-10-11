#!/usr/bin/env python3
"""Build signals.csv: the research registry (signals_core.csv) extended with the live product's scoring factors and the EXP-012 variables.

Weights and constants for the live rows are imported from `src/scoring/engine.py`, not retyped, so the table cannot drift from the code.
The live rows describe what the engine computes; whether a factor is *valid* is recorded in `empirical_status` and the audit page.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
REPO = BASE.parents[2]
sys.path.insert(0, str(REPO))

from src.quant.pit import reliability as rel          # noqa: E402
from src.quant.study import exp012                    # noqa: E402
from src.scoring import engine                        # noqa: E402

COLUMNS = ["signal_id", "name", "layer", "scope", "family", "definition", "hypothesis", "inputs", "source_datasets", "frequency", "timestamp_semantics", "expected_lag",
           "missing_semantics", "normalization", "known_failure_modes", "related_literature", "empirical_status", "experiments_used", "code_refs", "redundancy_notes", "verified", "confidence"]
LIVE_STATUS = ("literature-anchored constants, no fitting; mechanics unit-tested; audited only on synthetic worlds (docs/FACTOR-AUDIT.md); "
               "NOT evaluated on the point-in-time panel by any committed experiment (src/quant and scripts do not import src.scoring)")
LIVE_VERIFIED = "constants read from src/scoring/engine.py on 2026-10-12"
LIVE_SNAPSHOT = "provider snapshot at request time; no archived history, so it cannot be replayed point in time"
LIVE_PRICE = "daily bars from the provider fabric at request time; backward-looking window"


def live(signal_id, name, layer, family, definition, hypothesis, inputs, source, timestamp, missing, normalization, failure, literature, confidence="medium", redundancy=""):
    return {"signal_id": f"live.{signal_id}", "name": name, "layer": layer, "scope": "live_product", "family": family, "definition": definition, "hypothesis": hypothesis,
            "inputs": inputs, "source_datasets": source, "frequency": "on request (cached by cache policy)", "timestamp_semantics": timestamp, "expected_lag": "0 sessions for prices; vendor-dependent otherwise",
            "missing_semantics": missing, "normalization": normalization, "known_failure_modes": failure, "related_literature": literature, "empirical_status": LIVE_STATUS,
            "experiments_used": "none", "code_refs": "src/scoring/engine.py", "redundancy_notes": redundancy, "verified": LIVE_VERIFIED, "confidence": confidence}


def live_rows() -> list[dict]:
    w, m, r = engine.BASE_WEIGHTS, engine.MOMENTUM_MEMBER_WEIGHTS, engine.RISK_WEIGHTS
    rows = []
    price_norm = "robust z (MAD) or return t-statistic, winsorised at 3, squashed to [-1, 1]"
    for name, definition, lit in [
        ("r12_1", "t-statistic of the 231-day return skipping the latest 21 days", "Jegadeesh and Titman (1993)"),
        ("r63", "t-statistic of the 63-day return", "intermediate momentum"),
        ("r21", "t-statistic of the 21-day return; timing feature, demoted weight", "short-horizon trend"),
        ("vol_confirm", "21-day over 63-day mean volume, signed by the direction of the 21-day return", "Lee and Swaminathan (2000)"),
        ("high52_prox", "close divided by the trailing 252-day high (level prior)", "George and Hwang (2004)"),
        ("rel21_vs_spy", "t-statistic of the 21-day return relative to SPY", "relative strength"),
    ]:
        rows.append(live(f"momentum.{name}", name, "factor", "momentum", definition, "past winners keep winning over the next month", "daily Close (and Volume, SPY)", LIVE_PRICE,
                         "backward-looking; available at the close", "factor omitted, never imputed", price_norm, "momentum crashes in high-volatility rebounds; collinear with the other trend factors",
                         lit, redundancy="trend cluster: r12_1, r63, r21 and high52_prox are correlated (synthetic audit: up to 0.86)"))
        rows[-1]["definition"] += f" (member weight {m[name]})"
    rows.append(live("reversal", "reversal", "factor", "reversal", "mean of the contrarian readings of the 5-day return t-statistic and the RSI distribution z", "short-horizon losers rebound in high-volatility regimes",
                     "daily Close", LIVE_PRICE, "backward-looking", "factor omitted", price_norm, "destructive in trends (base weight 0.05; 0.20 only when volatility is in its top 20%)", "Nagel (2012)"))
    for name, definition, lit in [
        ("target_upside", "analyst consensus target over price minus 1, shrunk by analyst count", "analyst targets"),
        ("earnings_yield", "1 / trailing P/E against a prior centre", "value"),
        ("pe_gap", "(trailing P/E - forward P/E) / trailing P/E", "expected earnings growth"),
        ("pead", "earnings surprise percentage, linearly decayed over 60 days after the announcement", "Bernard and Thomas (1989)"),
    ]:
        rows.append(live(f"fundamental.{name}", name, "factor", "fundamental", definition, "cheaper, upgraded or positively surprising firms outperform", "provider fundamentals and analyst fields",
                         LIVE_SNAPSHOT, "value as of the request, not as of an archived date", "factor absent when the field is absent; never estimated from nothing", "prior centre and scale, squashed",
                         "vendor field definitions differ and are not archived; targets are level, not revision", lit, "low"))
    for name, definition, lit in [
        ("gross_profitability", "gross profit over assets against a prior centre of 0.33", "Novy-Marx (2013)"),
        ("net_issuance", "year-on-year share-count change, issuance is bearish", "Pontiff and Woodgate (2008)"),
        ("asset_growth", "year-on-year asset growth against a typical 8%, growth is bearish", "Cooper, Gulen and Schill (2008)"),
    ]:
        rows.append(live(f"quality.{name}", name, "factor", "quality", definition, "profitable, non-issuing, slowly growing firms outperform", "provider fundamentals", LIVE_SNAPSHOT,
                         "value as of the request", "factor absent when the field is absent", "prior centre and scale, squashed", "slow sleeve (0.15 cap); depends on vendor restatement behaviour", lit, "low"))
    rows.append(live("news.sentiment", "sentiment", "factor", "news", "effective news sentiment shrunk by n_eff / (n_eff + 6): repeats and stale items cannot inflate", "news tone leads returns",
                     "news provider items and a sentiment model", LIVE_SNAPSHOT, "item timestamps from the provider; not archived", "absent when no effective evidence", "shrinkage toward zero",
                     "availability depends on the news provider key (see the operational limitations in the audit); a sentiment model's training period can overlap an evaluation window", "financial NLP (family E)", "low"))
    for sleeve in ("momentum", "fundamental", "quality", "news", "reversal"):
        rows.append(live(f"sleeve.{sleeve}", f"{sleeve} sleeve", "sleeve", sleeve, f"base weight {w[sleeve]} in the composite" + (f"; {engine.REVERSAL_WEIGHT_HIGH_VOL} in high-volatility regimes, momentum cut by {engine.HIGH_VOL_MOMENTUM_MULT}" if sleeve == "reversal" else ""),
                         "information-ratio-based budget across sleeves", "member factors", "see members", "per member", "missing members drop out; weights renormalise", "weighted mean of member scores",
                         "weights are literature-anchored, never fit; the budget has not been tested against an equal-weight alternative on real data", "docs/SCORING.md", "low"))
    rows.append(live("gate.macro", "macro gate", "gate", "macro", f"stress probability from term spread, NFCI, credit spread and VIX percentile; momentum sleeve scaled by up to {engine.GATE_LAMBDA}", "momentum underperforms in macro stress",
                     "FRED series and VIX", "macro provider (see macro_freshness)", "latest available release; vintage not archived", "gate neutral when inputs are missing", "logistic-style probability", "macro series are revised; ALFRED vintages are not used live", "Daniel and Moskowitz (2016)", "low"))
    for name, weight in r.items():
        rows.append(live(f"risk.{name}", f"risk: {name}", "risk_component", "risk", f"percentile contribution with weight {weight}", "higher percentile means more risk", "daily Close, benchmarks", LIVE_PRICE,
                         "backward-looking", "component omitted and weights renormalised", "percentile against a reference distribution", "percentiles use a fixed reference, not the cross-section of the day", "risk literature (CVaR, semi-deviation)", "medium"))
    for name in ("u_disp", "u_data", "u_event", "u_fresh", "u_model", "u_stab", "u_macro"):
        rows.append(live(f"confidence.{name}", name, "confidence_deduction", "confidence", "multiplicative deduction from the confidence score, itemised on every scorecard", "confidence should fall when evidence is stale, thin, unstable or contested",
                         "scorecard internals", "computed", "as of the request", "see engine", "[0, 1] deduction", "the deductions are heuristic; confidence is a rule, not a calibrated probability", "-", "medium"))
    return rows


def exp012_rows() -> list[dict]:
    base = dict(scope="research_only", layer="raw_variable", verified="independent recomputation matched 16,000 of 16,000 values (validation/reliability_validation.json)",
                confidence="high for construction; the hypothesis is untested", code_refs="src/quant/pit/reliability.py; src/quant/study/exp012.py", experiments_used="EXP-012",
                source_datasets="data/curated/sec_v3/filings.parquet (SEC Financial Statement Data Sets registry)", frequency="every 5 sessions in the rich panel",
                timestamp_semantics="usable from the first session whose close-based decision may use the filing (sec_facts.available_session)", expected_lag="0 to 1 session after acceptance",
                missing_semantics="NaN, never zero, before any filing history; 8.2% of rows lack a mapped CIK", normalization="cross-sectional rank within the date for the model input",
                empirical_status="registered (EXP-012); result pending at the time of writing", redundancy_notes="rel_u_xs includes days_since_report and filing_lag_days, which are in the rich panel",
                related_literature="Bannouh, Geng, Peeters (2019); Zhang (2006); Palmrose, Richardson, Scholz (2001)", hypothesis="less reliable disclosure weakens fundamentals signals and may itself predict returns")
    defs = {
        "amended_730": ("count of amendments to periodic reports (10-K/A, 10-Q/A and transition forms) usable in the trailing 730 days", "amendments that are re-filed financial reports; Part III addenda are not in the data set"),
        "latest_report_amended": ("1 when the latest original periodic report has already been amended by the decision date", "uses the amendment's own acceptance time; prevrpt is never read"),
        "periodic_count_400": ("original periodic reports usable in the trailing 400 days (4 or 5 for a regular filer)", "a shortfall means a missed, late or absent filing"),
        "lag_deterioration": ("days from period end to acceptance for the latest original report minus the median of the previous four of the same kind", "positive means the firm files later than usual"),
    }
    out = []
    for var in rel.VARIABLES:
        d, f = defs[var]
        out.append({**base, "signal_id": f"exp012.{var}", "name": var, "family": "disclosure_process_reliability", "definition": d, "inputs": "filings.parquet: form, period, accepted_at, cik", "known_failure_modes": f})
    for col in exp012.NEW_BLOCK:
        out.append({**base, "signal_id": f"exp012.{col}", "name": col, "layer": "transformed_feature", "family": "disclosure_process_reliability",
                    "definition": "cross-sectional percentile rank within the date of the corresponding raw variable" if col != "rel_u_xs" else "composite: mean of the oriented ranks of days_since_report, filing_lag_days, amended_730, lag_deterioration and periodic_count_400 (at least 3 present), ranked again within the date",
                    "inputs": "raw reliability variables", "known_failure_modes": "rank transform discards level information; composite weights are equal by design, not fitted"})
    out.append({**base, "signal_id": "exp012.interactions", "name": "int_<fundamental>", "layer": "interaction", "family": "disclosure_process_reliability",
                "definition": "fundamentals feature (cross-sectional rank) multiplied by rel_u_xs, for each of the 48 fundamentals features", "inputs": "rich-panel fundamentals; rel_u_xs",
                "known_failure_modes": "130 ridge inputs; multicollinearity; tested against a placebo in which the composite is permuted or shifted and the interactions rebuilt"})
    return out


def main() -> None:
    core = list(csv.DictReader((BASE / "signals_core.csv").open()))
    rows = core + live_rows() + exp012_rows()
    with (BASE / "signals.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore", restval="", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    by_scope = {}
    for r in rows:
        by_scope[(r["scope"], r["layer"])] = by_scope.get((r["scope"], r["layer"]), 0) + 1
    print(len(rows), "signals")
    for k, v in sorted(by_scope.items()):
        print(" ", k, v)


if __name__ == "__main__":
    main()
