"""EXP-014 - does a restating amendment to a periodic report carry information beyond what is already priced? An independent-firm test.

Parent: EXP-012 and EXP-013, whose sample (the 250 most liquid names each month) is the DISCOVERY sample for everything below. The discovery sample showed that firms with a recent amendment to a periodic
report earn lower next-month return ranks, that the whole effect sits in amendments that change the reported numbers, and that it rests on about 60 firms (18 with a changing amendment). Nothing in this
study tunes that finding. It states one hypothesis in advance and tests it on firms the discovery never saw.

Samples (fixed before the data are touched)
    CONFIRMATORY  firms ranked 251 to 1,000 by liquidity in the month (not index members; delisted names included in the months they were liquid), excluding every company that was ever in the
                  discovery universe, identity-trusted rows only, decision dates 2014-04-01 to 2025-05-09.
    TIME-SEPARATE the discovery firms on dates 2014-04-01 to 2017-03-31, which EXP-011 to EXP-013 used only for training, never for evaluation.
    The holdout (2025-08-26 onward) is never read.

Primary hypothesis H1: in the confirmatory sample, with fixed effects for date x Fama-French 12 sector and 17 established controls, the indicator that the firm has a value-changing amendment (a periodic-report
amendment whose revenue, net income, assets, liabilities, equity or operating cash flow differs from the previous version by more than 1%) available in the trailing 730 days has a NEGATIVE coefficient on the
21-session forward return rank. H2 is the same with any amendment (the EXP-012 definition). Holm across H1 and H2; the p-value is the wild-cluster bootstrap over firms, null imposed, 9,999 draws.

What counts as a survival, a fragile result and a rejection is written in `DEFINITION["decision"]` and applied mechanically by `decide`. A machine-learning increment (does the information add to a conventional
ridge and boosted ranking on the same folds?) and a cost-aware portfolio are reported separately, and neither can rescue a failed H1.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd

from src.quant.pit import reliability as rel
from src.quant.pit.calendar import TradingCalendar
from src.quant.study import exp009b, exp011, exp012, prereg
from src.quant.study import exp014_inference as inf
from src.quant.study.firewall import FIREWALL

EXPERIMENT_ID = "EXP-014"
PARENT_EXPERIMENT = "EXP-012 / EXP-013"
OUTPUT_DIR = Path("experiments") / EXPERIMENT_ID
PREREG_DOC = Path("docs/EXP_014_PREREGISTRATION.md")
REGISTRATION_REF = "origin/research/market-signal-review-2026-10-11"
LABEL = "fwd_rank_21"

MID_PANEL = Path("data/research_mid/derived/rich_pit_panel_mid.parquet")
MID_MANIFEST = Path("data/manifests/rich_pit_panel_mid_manifest.json")
FROZEN_PANEL = Path("data/research/derived/rich_pit_panel.parquet")
FROZEN_IDENTITY = Path("data/curated/security_master_v3/security_identity_interval.parquet")
CLASSIFICATION = Path("data/research/derived/amendment_classification_v1.parquet")
EDGAR_FILINGS = Path("data/curated/edgar_filings_v1/filings.parquet")
CALENDAR = Path("data/research/derived/exp010b_calendar.json")
SAMPLE_START, SAMPLE_END = pd.Timestamp("2014-04-01"), pd.Timestamp("2025-05-09")
TIME_SEPARATE_END = pd.Timestamp("2017-03-31")
GRID_STEP = 5
WEBB_DRAWS, ROBUST_DRAWS, SEED = 9999, 4999, 20261014

CONTROLS = ["log_dollar_volume_21_xs", "amihud_21_xs", "mom_252_21_xs", "mom_21_xs", "reversal_5_xs", "vol_63_xs", "book_to_market_xs", "roa_xs", "gross_profitability_xs",
            "asset_growth_xs", "liabilities_to_assets_xs", "accruals_xs", "filing_lag_days_xs", "days_since_report_xs"]
REPORTING_CONTROLS = ["periodic_count_400_r", "lag_deterioration_r", "n_missing_sec_r"]
BASE_CONTROLS = CONTROLS + REPORTING_CONTROLS

CATEGORIES = ("core", "other_changed", "unchanged", "unclass")
# name -> (categories counted, lower offset, upper offset) in calendar days around the decision day; (lo, hi] with hi <= 0 is the past.
TREATMENTS: dict[str, tuple[tuple[str, ...], int, int]] = {
    "core_730": (("core",), -730, 0), "other_730": (("other_changed",), -730, 0), "unchanged_730": (("unchanged",), -730, 0), "unclass_730": (("unclass",), -730, 0),
    "any_730": (CATEGORIES, -730, 0), "core_365": (("core",), -365, 0), "core_1095": (("core",), -1095, 0), "any_365": (CATEGORIES, -365, 0), "any_1095": (CATEGORIES, -1095, 0),
    "core_prev365": (("core",), -365, 0), "core_prev730b": (("core",), -730, -365), "core_next365": (("core",), 0, 365), "core_next730b": (("core",), 365, 730), "core_old": (("core",), -1460, -730),
}
FORM_SPLIT = {"k_core_730": ("10-K", ("core",)), "q_core_730": ("10-Q", ("core",))}

DEFINITION: dict[str, Any] = {
    "experiment_id": EXPERIMENT_ID, "parent_experiment": PARENT_EXPERIMENT,
    "status": "CONFIRMATORY TEST ON AN INDEPENDENT FIRM SAMPLE - HOLDOUT SEALED - PROMOTION NOT ASSESSED",
    "question": "Do value-changing amendments to periodic reports predict lower next-month return ranks in firms the discovery never saw, beyond established characteristics and reporting controls?",
    "samples": {
        "confirmatory": "mid-liquidity universe (ranks 251-1,000 by 3-month median dollar volume, close >= 5, non-ETF), identity-trusted rows, company never in the frozen 250-name universe, 2014-04-01..2025-05-09",
        "time_separate": "frozen 250-name panel, identity-trusted rows, 2014-04-01..2017-03-31 (never evaluated before)",
        "holdout": {"start": "2025-08-26", "end": "2026-08-28", "touched": False},
    },
    "outcome": {"label": LABEL, "note": "centred cross-sectional rank of the 21-session forward return within the universe-date; identical construction to every earlier experiment"},
    "treatments": {k: {"categories": list(v[0]), "from_days": v[1], "to_days": v[2]} for k, v in TREATMENTS.items()},
    "categories": {"core": "classifiable amendment with revenue, net income, assets, liabilities, equity or operating cash flow differing by > 1% from the previous version",
                   "other_changed": "classifiable, not core, with some canonical key differing by > 0.1%", "unchanged": "classifiable with no canonical key differing by > 0.1%",
                   "unclass": "no previous version with comparable facts"},
    "availability": "first session whose close-based decision may use the amendment (accepted before 16:00 New York time: that session; otherwise the next); amendment forms are 10-K/A, 10-Q/A, 10-KT/A, 10-QT/A from the SEC Financial Statement Data Sets registry; NaN before the firm has any original periodic report",
    "controls": {"parsimonious": BASE_CONTROLS, "full": "all 76 point-in-time features of the rich panel (ranks) plus the three reporting controls", "missing": "0 after centring (neutral rank)"},
    "fixed_effects": "date x Fama-French 12 sector",
    "hypotheses": {"H1": "coefficient on core_730 < 0 (with other_730, unchanged_730 and unclass_730 as separate regressors)", "H2": "coefficient on any_730 < 0 (EXP-012 definition), alone",
                   "correction": "Holm across H1 and H2 on the wild-cluster bootstrap p-values (one-sided, negative)"},
    "inference": {"primary": "wild-cluster bootstrap over firms, null imposed, Webb six-point weights", "draws": WEBB_DRAWS, "robustness_draws": ROBUST_DRAWS, "seed": SEED,
                  "also_reported": "Cameron-Gelbach-Miller two-way (firm, date) t statistic and firm-clustered t, which are not used for decisions", "alpha": 0.05},
    "robustness_gates": {
        "R1_power": "at least 40 distinct treated firms and 150 treated firm-dates for core_730 in the confirmatory sample, else the result is INCONCLUSIVE and nothing is concluded",
        "R2_influence": "after removing the 5 treated firms whose deletion moves the coefficient most, the coefficient is still negative and at least 50% of the full-sample estimate",
        "R3_years": "the coefficient is negative in at least 9 of the 12 leave-one-calendar-year-out fits (2014 and 2025 are partial years)",
        "R4_full_controls": "with the full control set the coefficient is negative with wild-cluster one-sided p < 0.05",
        "R5_time_separate": "in the time-separate sample (label-free counts before registration: 9 treated firms for core_730, 58 for any_730) the coefficient on any_730 is negative with wild-cluster one-sided p < 0.10 and the coefficient on core_730 is negative",
        "R6_sector": "the coefficient is negative in at least 8 of the 12 leave-one-sector-out fits",
    },
    "interpretation_diagnostic": {"anticipation_ratio": "coef(core_next365) / coef(core_prev365) from one regression with the five event-time bins; below 0.5 the association is labelled TIME_SPECIFIC, otherwise MARKER_OF_PERSISTENT_TROUBLE (it is not an information event but a marker)"},
    "decision": {
        "SURVIVES": "H1 Holm-adjusted p < 0.05 with negative sign AND R1 to R6 all pass",
        "FRAGILE": "H1 Holm-adjusted p < 0.05 with negative sign AND R1 passes AND at least one of R2 to R6 fails",
        "NOT_REPLICATED": "H1 adjusted p >= 0.05 or the sign is positive, with R1 passed",
        "INCONCLUSIVE": "R1 fails: too few treated firms to conclude anything",
        "no_other_outcomes": True,
    },
    "machine_learning_increment": {
        "arms": {"M0": "ridge on the 76 point-in-time features (alpha 10, the pre-existing configuration)", "M1": "M0 plus the amendment block (core_730, other_730, unchanged_730, unclass_730 indicators and log1p count of any_730)",
                 "G0": "boosted trees on the 76 features, 3 seeds, frozen EXP-010A settings", "G1": "G0 plus the amendment block"},
        "placebos": {"permute": "the block permuted across firms within date (5 seeds)", "shift": "the block taken from 252 sessions earlier within firm"},
        "test": "paired mean Rank IC difference on identical dates, Newey-West HAC (4 lags), moving-block bootstrap (block 6, 4,000 draws), Holm across ridge and boosted contrasts; folds: the 8 recorded folds",
        "folds": "the recorded EXP-006 plan, unchanged", "search": "none: no hyperparameter is chosen on any data, so no selection correction is needed",
    },
    "economics": "the frozen EXP-010B 21-session portfolio (B1) at 10 bp for M0 and M1 on the mid-sample daily panel; reported at 10, 30 and 50 bp; not part of the decision",
    "acceptance_gates": ["every input file's sha256 equals the one recorded here", "no date after 2025-05-09", "label never shuffled outside rehearsal", "all predictions finite", "8 folds complete for every arm"],
    "trial_ledger": {"confirmatory_tests": 2, "robustness_gates": 6, "secondary_contrasts": 10, "ml_contrasts": 2, "model_fits": "24 ridge/boosted fits plus 5 placebo permutations x 2 arms"},
    "outputs": ["definition.json", "config.json", "results.json", "regressions.csv", "robustness.csv", "ml_paired_tests.csv", "ml_metrics.csv", "manifest.json", "model/*"],
}
METHOD_SOURCES = (
    "src/quant/study/exp014.py", "src/quant/study/exp014_inference.py", "src/quant/pit/reliability.py", "src/quant/pit/edgar_client.py", "scripts/quant/acquire_edgar_submissions.py",
    "scripts/quant/build_independent_sample.py", "scripts/quant/build_mid_security_master.py", "scripts/quant/build_mid_rich_panel.py",
    "docs/research/market-signal-review-2026-10-11/code/classify_amendments.py", "src/quant/study/exp011.py", "src/quant/study/exp012.py", "src/quant/validation/runner.py",
    "src/quant/models/linear.py", "src/quant/models/trees.py", "src/quant/models/base.py", "src/quant/pit/rich_panel.py",
)


def definition_fingerprint(root: Path = Path(".")) -> str:
    return prereg.fingerprint(DEFINITION, METHOD_SOURCES, root)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def prereg_gate(root: Path = Path("."), *, fetch: bool = True) -> dict[str, Any]:
    """Refuse unless the registration is committed, unchanged, embeds this definition's fingerprint, and is already an ancestor of the pushed research branch."""
    root = Path(root)
    doc = root / PREREG_DOC
    expected = definition_fingerprint(root)
    if not doc.exists():
        raise prereg.PreregistrationError(f"{PREREG_DOC} does not exist")
    if f"Definition fingerprint: `{expected}`" not in doc.read_text(encoding="utf-8"):
        raise prereg.PreregistrationError("the preregistration does not embed this definition's fingerprint; nothing is run")
    tracked = [str(PREREG_DOC), *METHOD_SOURCES]
    if _git(root, "status", "--porcelain", "--", *tracked).stdout.strip():
        raise prereg.PreregistrationError("registered files have uncommitted changes")
    commit = _git(root, "log", "-1", "--format=%H", "--", *tracked).stdout.strip()
    if fetch:
        _git(root, "fetch", "origin", "research/market-signal-review-2026-10-11", "--quiet")
    if _git(root, "merge-base", "--is-ancestor", commit, REGISTRATION_REF).returncode != 0:
        raise prereg.PreregistrationError(f"registration commit {commit[:12]} is not on {REGISTRATION_REF}: push it before running")
    return {"preregistration_document": str(PREREG_DOC), "preregistration_sha256": prereg.sha256_file(doc), "registration_commit": commit, "pushed_to": REGISTRATION_REF, "definition_fingerprint": expected}


# ── samples ──────────────────────────────────────────────────────────────────────────────────────────────

def read_calendar(root: Path) -> TradingCalendar:
    sessions = json.loads((Path(root) / CALENDAR).read_text())["sessions"]
    return TradingCalendar.from_dates(pd.to_datetime(sessions).date)


def confirmatory_sample(panel: pd.DataFrame, frozen_ciks: set[int]) -> pd.DataFrame:
    """Identity-trusted rows of the mid panel whose company was never in the discovery universe, inside the registered dates, with a label."""
    p = panel
    keep = (p["security_id"].notna() & p["cik"].notna() & ~p["cik"].fillna(-1).astype("int64").isin(frozen_ciks) & p[LABEL].notna()
            & (p["date"] >= SAMPLE_START) & (p["date"] <= SAMPLE_END) & p["in_universe"].astype(bool))
    return p[keep].reset_index(drop=True)


def time_separate_sample(panel: pd.DataFrame) -> pd.DataFrame:
    keep = (panel["security_id"].notna() & panel["cik"].notna() & panel[LABEL].notna() & (panel["date"] >= SAMPLE_START) & (panel["date"] <= TIME_SEPARATE_END) & panel["in_universe"].astype(bool))
    return panel[keep].reset_index(drop=True)


# ── point-in-time treatment variables ────────────────────────────────────────────────────────────────────────────

def amendment_events(filings: pd.DataFrame, classification: pd.DataFrame, calendar: TradingCalendar, ciks: set[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Original periodic reports and amendments with their availability day, and for each amendment its category. Returns (originals, amendments)."""
    table = rel.filing_table(filings, calendar, ciks)
    cls = classification[["adsh", "classifiable", "core_changing_1pct", "unchanged_numbers"]]
    amend = table[table["is_amend"]].merge(cls, on="adsh", how="left")
    classifiable = amend["classifiable"].fillna(False).astype(bool)
    core = classifiable & amend["core_changing_1pct"].fillna(False).astype(bool)
    unchanged = classifiable & amend["unchanged_numbers"].fillna(False).astype(bool)
    amend["category"] = np.select([~classifiable, core, unchanged], ["unclass", "core", "unchanged"], default="other_changed")
    return table[~table["is_amend"]].copy(), amend


def treatment_frame(keys: pd.DataFrame, originals: pd.DataFrame, amendments: pd.DataFrame) -> pd.DataFrame:
    """Counts of amendments in each registered window, per row of `keys` (date, cik). NaN where the firm has no original periodic report available yet."""
    days = rel.epoch_days(keys["date"])
    out = {name: np.full(len(keys), np.nan) for name in [*TREATMENTS, *FORM_SPLIT]}
    out["has_history"] = np.zeros(len(keys))
    orig_by = {int(c): np.sort(g["avail_d"].to_numpy()) for c, g in originals.groupby("cik")}
    am_by = {int(c): g for c, g in amendments.groupby("cik")}
    positions = pd.Series(np.arange(len(keys))).groupby(keys["cik"].to_numpy()).indices
    for c, idx in positions.items():
        if pd.isna(c):
            continue
        o = orig_by.get(int(c))
        if o is None:
            continue
        d = days[idx]
        history = inf.window_counts(d, o, -10 ** 6, 0) > 0
        out["has_history"][idx] = history.astype(float)
        a = am_by.get(int(c))
        for name, (cats, lo, hi) in TREATMENTS.items():
            if a is None:
                values = np.zeros(len(idx))
            else:
                values = inf.window_counts(d, np.sort(a.loc[a["category"].isin(cats), "avail_d"].to_numpy()), lo, hi)
            out[name][idx] = np.where(history, values, np.nan)
        for name, (form, cats) in FORM_SPLIT.items():
            if a is None:
                values = np.zeros(len(idx))
            else:
                sel = a["category"].isin(cats) & a["form"].str.startswith(form)
                values = inf.window_counts(d, np.sort(a.loc[sel, "avail_d"].to_numpy()), -730, 0)
            out[name][idx] = np.where(history, values, np.nan)
    frame = pd.DataFrame(out, index=keys.index)
    for name in [*TREATMENTS, *FORM_SPLIT]:
        frame[f"D_{name}"] = (frame[name] > 0).astype(float).where(frame[name].notna())
    frame["n_any_730_log"] = np.log1p(frame["any_730"])
    return frame


def control_frame(panel: pd.DataFrame, filings: pd.DataFrame, calendar: TradingCalendar) -> pd.DataFrame:
    """The reporting controls: reliability variables ranked within date and centred, and the number of missing SEC characteristics ranked the same way."""
    keys = panel[["date", "symbol", "cik"]]
    reliability = rel.build_reliability(filings, keys, calendar)
    out = pd.DataFrame(index=panel.index)
    for col in ("periodic_count_400", "lag_deterioration"):
        out[f"{col}_r"] = 2 * (reliability[col].groupby(panel["date"]).rank(pct=True) - 0.5)
    sec_cols = [c for c in panel.columns if c.endswith("_xs") and c not in exp011.feature_list("baseline")]
    out["n_missing_sec_r"] = 2 * (panel[sec_cols].isna().sum(axis=1).groupby(panel["date"]).rank(pct=True) - 0.5)
    return out


def assemble(panel: pd.DataFrame, root: Path, calendar: TradingCalendar, filings: Optional[pd.DataFrame] = None, classification: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Sample rows with treatments and controls attached, missing controls set to the neutral 0."""
    root = Path(root)
    filings = pd.read_parquet(root / rel.FILINGS) if filings is None else filings
    classification = pd.read_parquet(root / CLASSIFICATION) if classification is None else classification
    ciks = {int(c) for c in panel["cik"].dropna().unique()}
    originals, amendments = amendment_events(filings, classification, calendar, ciks)
    treat = treatment_frame(panel[["date", "cik"]], originals, amendments)
    controls = control_frame(panel, filings, calendar)
    out = pd.concat([panel.reset_index(drop=True), treat.reset_index(drop=True), controls.reset_index(drop=True)], axis=1)
    out["firm"] = out["security_id"].astype(str)
    out["cell"] = out["ff12"].astype(str)
    for c in [*CONTROLS, *REPORTING_CONTROLS]:
        out[c] = out[c].fillna(0.0)
    return out


# ── regressions ──────────────────────────────────────────────────────────────────────────────────────────────────

def full_controls(frame: pd.DataFrame) -> list[str]:
    return [*[c for c in exp011.feature_list("rich") if c in frame.columns], *REPORTING_CONTROLS]


def regress(frame: pd.DataFrame, focus: str, regressors: Sequence[str], controls: Sequence[str], *, draws: int, seed: int, fe: bool = True, label: str = "") -> dict[str, Any]:
    """Fixed-effects regression of the label on `regressors` + `controls`, inference on `focus`: wild-cluster bootstrap (decisions), two-way and firm-cluster t (reported)."""
    cols = [*regressors, *controls]
    use = frame[[LABEL, *cols, "firm", "date", "cell"]].dropna(subset=[LABEL, *regressors])
    use = use.assign(**{c: use[c].fillna(0.0) for c in controls})
    groups = [use["date"], use["cell"]] if fe else [use["date"]]
    z = inf.absorb(use, [LABEL, *cols], groups)
    spread = z[cols].std()
    if not spread[list(regressors)].gt(1e-10).all():          # a treatment with no variation inside the fixed-effect cells cannot be estimated
        return {"label": label or focus, "focus": focus, "rows": int(len(use)), "firms": int(use["firm"].nunique()), "treated_firms": 0, "treated_rows": 0, "coef": float("nan"),
                "wcr_p_negative": 1.0, "wcr_p_two_sided": 1.0, "degenerate": True}
    cols = [c for c in cols if c in regressors or spread[c] > 1e-10]       # constant controls (all missing in this sample) would make the problem singular
    X, y = z[cols].to_numpy(float), z[LABEL].to_numpy(float)
    firm, date = pd.factorize(use["firm"])[0], pd.factorize(use["date"])[0]
    fit = inf.ols(y, X, cols, firm, date)
    two_way = inf.summary(fit, inf.cgm_two_way(fit, X, firm, date), focus)
    one_way = inf.summary(fit, inf.one_way(fit, X, firm), focus)
    j = cols.index(focus)
    boot = inf.wild_cluster_bootstrap(y, X[:, j], np.delete(X, j, axis=1), firm, draws=draws, seed=seed)
    treated = use.loc[use[focus] > 0, "firm"]
    return {"label": label or focus, "focus": focus, "rows": int(len(use)), "firms": int(use["firm"].nunique()), "dates": int(use["date"].nunique()), "treated_firms": int(treated.nunique()),
            "treated_rows": int(len(treated)), "coef": two_way["coef"], "t_two_way": two_way["t"], "t_firm": one_way["t"], "wcr_t": boot["t_obs"], "wcr_p_negative": boot["p_one_sided_negative"],
            "wcr_p_two_sided": boot["p_two_sided"], "draws": boot["draws"], "coefficients": {n: float(b) for n, b in zip(cols, fit.beta)}}


def influential_treated(frame: pd.DataFrame, focus: str, regressors: Sequence[str], controls: Sequence[str], k: int) -> list[str]:
    """The `k` treated firms whose deletion moves the focus coefficient furthest towards zero (exact delete-one-cluster)."""
    cols = [*regressors, *controls]
    use = frame[[LABEL, *cols, "firm", "date", "cell"]].dropna(subset=[LABEL, *regressors])
    use = use.assign(**{c: use[c].fillna(0.0) for c in controls}).reset_index(drop=True)
    z = inf.absorb(use, [LABEL, *cols], [use["date"], use["cell"]])
    codes, names = pd.factorize(use["firm"])
    treated_codes = np.unique(codes[(use[focus] > 0).to_numpy()])
    table = inf.influence_by_cluster(z[LABEL].to_numpy(float), z[cols].to_numpy(float), cols.index(focus), codes, only=treated_codes)
    coef = float(np.linalg.lstsq(z[cols].to_numpy(float), z[LABEL].to_numpy(float), rcond=None)[0][cols.index(focus)])
    table["toward_zero"] = np.sign(-coef) * table["delta"]
    top = table.sort_values("toward_zero", ascending=False).head(k)
    return [str(names[c]) for c in top["cluster"]]


def leave_out_fits(frame: pd.DataFrame, focus: str, regressors: Sequence[str], controls: Sequence[str], by: str) -> list[dict[str, Any]]:
    """Refit without each calendar year (by='year') or each sector (by='sector'); coefficient only, no bootstrap."""
    key = frame["date"].dt.year if by == "year" else frame["cell"]
    out = []
    for value in sorted(key.unique(), key=str):
        sub = frame[key != value]
        cols = [*regressors, *controls]
        use = sub[[LABEL, *cols, "date", "cell"]].dropna(subset=[LABEL, *regressors])
        use = use.assign(**{c: use[c].fillna(0.0) for c in controls})
        z = inf.absorb(use, [LABEL, *cols], [use["date"], use["cell"]])
        beta = np.linalg.lstsq(z[cols].to_numpy(float), z[LABEL].to_numpy(float), rcond=None)[0]
        out.append({"left_out": str(value), "coef": float(beta[cols.index(focus)]), "rows": int(len(use))})
    return out


def holm(p: dict[str, float]) -> dict[str, float]:
    return exp012.holm(p)


def confirmatory_regressions(conf: pd.DataFrame, time_sep: pd.DataFrame, *, draws: int = WEBB_DRAWS, robust_draws: int = ROBUST_DRAWS, seed: int = SEED) -> dict[str, Any]:
    """Everything in the registered regression protocol. Returns the numbers; `decide` turns them into a label."""
    h1_regs = ["D_core_730", "D_other_730", "D_unchanged_730", "D_unclass_730"]
    h2_regs = ["D_any_730"]
    res: dict[str, Any] = {}
    res["H1"] = regress(conf, "D_core_730", h1_regs, BASE_CONTROLS, draws=draws, seed=seed, label="H1 core-changing amendment, 730 days")
    res["H2"] = regress(conf, "D_any_730", h2_regs, BASE_CONTROLS, draws=draws, seed=seed + 1, label="H2 any amendment, 730 days")
    adjusted = holm({"H1": res["H1"]["wcr_p_negative"], "H2": res["H2"]["wcr_p_negative"]})
    res["holm_adjusted_p"] = adjusted
    # robustness
    full = full_controls(conf)
    res["R4_full_controls"] = regress(conf, "D_core_730", h1_regs, full, draws=robust_draws, seed=seed + 2, label="H1 with all 76 features as controls")
    top5 = influential_treated(conf, "D_core_730", h1_regs, BASE_CONTROLS, 5)
    res["R2_influence"] = {**regress(conf[~conf["firm"].isin(top5)], "D_core_730", h1_regs, BASE_CONTROLS, draws=robust_draws, seed=seed + 3, label="H1 without the 5 most influential treated firms"), "removed_firms": top5,
                           "share_of_full_estimate": None}
    res["R2_influence"]["share_of_full_estimate"] = float(res["R2_influence"]["coef"] / res["H1"]["coef"]) if res["H1"]["coef"] != 0 else None
    res["R3_years"] = leave_out_fits(conf, "D_core_730", h1_regs, BASE_CONTROLS, "year")
    res["R6_sector"] = leave_out_fits(conf, "D_core_730", h1_regs, BASE_CONTROLS, "sector")
    res["R5_time_separate"] = regress(time_sep, "D_core_730", h1_regs, BASE_CONTROLS, draws=robust_draws, seed=seed + 4, label="H1 in the time-separate sample (discovery firms, 2014-04..2017-03)")
    res["R5_time_separate_any"] = regress(time_sep, "D_any_730", h2_regs, BASE_CONTROLS, draws=robust_draws, seed=seed + 5, label="H2 in the time-separate sample")
    # secondary and interpretation
    sec = {}
    for name, regs, focus in (("S1_core_365", ["D_core_365", "D_unchanged_730", "D_unclass_730", "D_other_730"], "D_core_365"), ("S2_core_1095", ["D_core_1095", "D_unchanged_730", "D_unclass_730", "D_other_730"], "D_core_1095"),
                              ("S3_unchanged", h1_regs, "D_unchanged_730"), ("S4_unclass", h1_regs, "D_unclass_730"), ("S5_k_core", ["D_k_core_730", "D_q_core_730", "D_other_730", "D_unchanged_730", "D_unclass_730"], "D_k_core_730"),
                              ("S6_q_core", ["D_k_core_730", "D_q_core_730", "D_other_730", "D_unchanged_730", "D_unclass_730"], "D_q_core_730")):
        sec[name] = regress(conf, focus, regs, BASE_CONTROLS, draws=robust_draws, seed=seed + 10, label=name)
    res["secondary"] = sec
    res["placebo_events"] = placebo_event_calibration(conf, draws=200 if robust_draws >= 999 else 20, seed=seed + 30)
    bins = ["D_core_prev365", "D_core_prev730b", "D_core_next365", "D_core_next730b", "D_core_old", "D_other_730", "D_unchanged_730", "D_unclass_730"]
    event_time = {focus: regress(conf, focus, bins, BASE_CONTROLS, draws=robust_draws, seed=seed + 20, label=f"event-time bins, focus {focus}") for focus in ("D_core_prev365", "D_core_next365")}
    prev, nxt = event_time["D_core_prev365"]["coef"], event_time["D_core_next365"]["coef"]
    res["event_time"] = {"bins": {f: {"coef": r["coef"], "wcr_p_negative": r["wcr_p_negative"], "treated_firms": r["treated_firms"]} for f, r in event_time.items()},
                         "coefficients_all_bins": event_time["D_core_prev365"]["coefficients"], "anticipation_ratio": float(nxt / prev) if prev < 0 else None}
    return res


def placebo_event_calibration(frame: pd.DataFrame, *, draws: int = 200, seed: int = SEED, boot_draws: int = 399) -> dict[str, Any]:
    """Size of the whole inference on the real label structure: give the same number of randomly chosen firms one placebo amendment each (flagged for 730 days from a random date in the firm's own span),
    re-estimate the registered H1 regression, and count how often the wild-cluster bootstrap rejects at 5%. The placebo event is independent of the firm's returns by construction, so the share of
    rejections should not exceed 5%; labels keep their real firm-level persistence, which a label shuffle would destroy."""
    h1_regs = ["D_core_730", "D_other_730", "D_unchanged_730", "D_unclass_730"]
    others = [r for r in h1_regs if r != "D_core_730"]
    use = frame[[LABEL, *h1_regs, *BASE_CONTROLS, "firm", "date", "cell"]].dropna(subset=[LABEL, *h1_regs]).reset_index(drop=True)
    use = use.assign(**{c: use[c].fillna(0.0) for c in BASE_CONTROLS})
    z = inf.absorb(use, [LABEL, *others, *BASE_CONTROLS], [use["date"], use["cell"]])
    y = z[LABEL].to_numpy(float)
    keep = [c for c in [*others, *BASE_CONTROLS] if z[c].std() > 1e-10]            # a regressor constant inside the cells (no such amendments in this sample) would make the problem singular
    Z = z[keep].to_numpy(float)
    codes = pd.factorize(use["firm"])[0]
    n_firms = int(codes.max()) + 1
    k = int(use.loc[use["D_core_730"] > 0, "firm"].nunique())
    day = use["date"].to_numpy("datetime64[D]").astype("int64")
    order = np.argsort(codes, kind="stable")
    starts = np.searchsorted(codes[order], np.arange(n_firms))
    ends = np.searchsorted(codes[order], np.arange(n_firms), side="right")
    rng = np.random.default_rng(seed)
    p_values, coefs = [], []
    for _ in range(draws):
        d = np.zeros(len(use))
        for firm_code in rng.choice(n_firms, size=k, replace=False):
            rows = order[starts[firm_code]:ends[firm_code]]
            begin = day[rows[rng.integers(0, len(rows))]]
            d[rows[(day[rows] >= begin) & (day[rows] < begin + 730)]] = 1.0
        d_frame = pd.DataFrame({"d": d, "date": use["date"], "cell": use["cell"]})
        d_dm = inf.absorb(d_frame, ["d"], [d_frame["date"], d_frame["cell"]])["d"].to_numpy(float)
        if not np.any(np.abs(d_dm) > 1e-12):
            continue
        boot = inf.wild_cluster_bootstrap(y, d_dm, Z, codes, draws=boot_draws, seed=int(rng.integers(0, 2 ** 31 - 1)))
        p_values.append(boot["p_one_sided_negative"])
        coefs.append(boot["gamma"])
    ps = np.array(p_values)
    return {"placebo_draws": int(len(ps)), "treated_firms_per_draw": k, "rejection_rate_5pct_one_sided": float(np.mean(ps < 0.05)), "rejection_rate_1pct_one_sided": float(np.mean(ps < 0.01)),
            "mean_p": float(ps.mean()), "coef_mean": float(np.mean(coefs)), "coef_sd": float(np.std(coefs)), "bootstrap_draws_each": boot_draws}


def decide(res: dict[str, Any], alpha: float = 0.05) -> dict[str, Any]:
    """Apply `DEFINITION['decision']` mechanically."""
    h1 = res["H1"]
    gates = {
        "R1_power": h1["treated_firms"] >= 40 and h1["treated_rows"] >= 150,
        "R2_influence": res["R2_influence"]["coef"] < 0 and (res["R2_influence"]["share_of_full_estimate"] or 0.0) >= 0.5,
        "R3_years": sum(1 for r in res["R3_years"] if r["coef"] < 0) >= 9,
        "R4_full_controls": res["R4_full_controls"]["coef"] < 0 and res["R4_full_controls"]["wcr_p_negative"] < 0.05,
        "R5_time_separate": res["R5_time_separate"]["coef"] < 0 and res["R5_time_separate_any"]["coef"] < 0 and res["R5_time_separate_any"]["wcr_p_negative"] < 0.10,
        "R6_sector": sum(1 for r in res["R6_sector"] if r["coef"] < 0) >= 8,
    }
    significant = h1["coef"] < 0 and res["holm_adjusted_p"]["H1"] < alpha
    if not gates["R1_power"]:
        label = "INCONCLUSIVE"
    elif not significant:
        label = "NOT_REPLICATED"
    elif all(gates.values()):
        label = "SURVIVES"
    else:
        label = "FRAGILE"
    ratio = res["event_time"]["anticipation_ratio"]
    interpretation = None if label in ("INCONCLUSIVE", "NOT_REPLICATED") else ("TIME_SPECIFIC" if (ratio is not None and ratio < 0.5) else "MARKER_OF_PERSISTENT_TROUBLE")
    return {"label": label, "h1_significant": bool(significant), "gates": {k: bool(v) for k, v in gates.items()}, "failed_gates": [k for k, v in gates.items() if not v], "interpretation": interpretation,
            "h2_adjusted_p": res["holm_adjusted_p"]["H2"], "h1_adjusted_p": res["holm_adjusted_p"]["H1"]}


# ── machine-learning increment ───────────────────────────────────────────────────────────────────────────────────

AMEND_BLOCK = ["D_core_730", "D_other_730", "D_unchanged_730", "D_unclass_730", "n_any_730_log"]
RICH = list(exp011.feature_list("rich"))
SHIFT_ROWS = exp012.SHIFT_ROWS
ML_ARMS: dict[str, dict[str, Any]] = {
    "M0": {"model": "ridge", "features": RICH, "seeds": (0,)},
    "M1": {"model": "ridge", "features": [*RICH, *AMEND_BLOCK], "seeds": (0,)},
    "G0": {"model": "gradient_boosting", "features": RICH, "seeds": (0, 1, 2)},
    "G1": {"model": "gradient_boosting", "features": [*RICH, *AMEND_BLOCK], "seeds": (0, 1, 2)},
    "P1": {"model": "ridge", "features": [*RICH, *AMEND_BLOCK], "placebo": "permute", "seeds": (0, 1, 2, 3, 4)},
    "P1s": {"model": "ridge", "features": [*RICH, *AMEND_BLOCK], "placebo": "shift", "seeds": (0,)},
}
ML_CONTRASTS = {"T_ridge": ("M1", "M0", "the amendment block adds to the ridge ranking"), "T_boosted": ("G1", "G0", "the amendment block adds to the boosted ranking"),
                "C_permute": ("M1", "P1", "M1 beats the permuted-block placebo (mean of five permutations)"), "C_shift": ("M1", "P1s", "M1 beats the time-shifted placebo")}


def ml_frame(frame: pd.DataFrame, arm: str, seed: int) -> pd.DataFrame:
    """The arm's frame: the amendment block replaced by a placebo where the arm asks for one."""
    kind = ML_ARMS[arm].get("placebo")
    if kind is None:
        return frame
    out = frame.copy()
    if kind == "permute":
        out[AMEND_BLOCK] = exp012.permute_within_date(frame, AMEND_BLOCK, seed)[AMEND_BLOCK]
    elif kind == "shift":
        ordered = frame.sort_values(["firm", "date"], kind="mergesort")
        out[AMEND_BLOCK] = ordered.groupby("firm", sort=False)[AMEND_BLOCK].shift(SHIFT_ROWS).reindex(frame.index)
    else:
        raise ValueError(kind)
    return out


def ml_tasks() -> list[tuple[str, int]]:
    return [(arm, seed) for arm, spec in ML_ARMS.items() for seed in spec["seeds"]]


def fit_ml_arm(arm: str, seed: int, frame: pd.DataFrame, plan: Any):
    from src.quant.models.factory import ModelSpec
    from src.quant.validation.runner import run_walk_forward

    spec_arm = ML_ARMS[arm]
    params = exp012.RIDGE_PARAMS if spec_arm["model"] == "ridge" else exp012.GBR_PARAMS
    spec = ModelSpec(f"{spec_arm['model']}_{arm}_seed_{seed}", spec_arm["model"], tuple(params.items()), seed if spec_arm["model"] != "ridge" else 0)
    return run_walk_forward(spec.build, ml_frame(frame, arm, seed), plan, features=spec_arm["features"], label=LABEL, step_sessions=GRID_STEP)


_ML_WORKER: dict[str, Any] = {}


def _ml_init(frame_path: str, root: str) -> None:
    frame = pd.read_parquet(frame_path)
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    _ML_WORKER["frame"] = frame.reset_index(drop=True)
    _ML_WORKER["plan"] = exp009b.recorded_plan(Path(root))


def _ml_task(task: tuple[str, int]):
    arm, seed = task
    result = fit_ml_arm(arm, seed, _ML_WORKER["frame"], _ML_WORKER["plan"])
    if result.errors or result.predictions is None or len(result.folds) != 8:
        return arm, seed, pd.DataFrame(), 0.0, list(result.errors) or ["incomplete folds"]
    return arm, seed, result.predictions, float(result.seconds), []


def ml_checkpoint(output: Path, arm: str, seed: int) -> Path:
    return Path(output) / "checkpoints" / f"{arm}_{seed}.parquet"


def ml_paired_tests(series: dict[tuple[str, int], pd.Series], folds: dict[tuple[str, int], list[float]]) -> dict[str, Any]:
    def arm_series(arm: str) -> pd.Series:
        return exp012.mean_series([series[(arm, s)] for s in ML_ARMS[arm]["seeds"]])

    def arm_folds(arm: str) -> list[float]:
        return [float(v) for v in np.mean([folds[(arm, s)] for s in ML_ARMS[arm]["seeds"]], axis=0)]

    contrasts = {name: {"left": l, "right": r, "claim": claim, **exp012.paired(arm_series(l), arm_series(r), arm_folds(l), arm_folds(r))} for name, (l, r, claim) in ML_CONTRASTS.items()}
    adjusted = holm({k: contrasts[k]["p_one_sided"] for k in ("T_ridge", "T_boosted")})
    for k, v in adjusted.items():
        contrasts[k]["holm_adjusted_p"] = v
    return contrasts


def ml_label(contrasts: dict[str, Any]) -> dict[str, Any]:
    """Separate verdict for the predictive increment: positive and Holm-significant, at least 6 of 8 folds, and ahead of both placebos."""
    out = {}
    for name, placebos in (("T_ridge", ("C_permute", "C_shift")), ("T_boosted", ())):
        c = contrasts[name]
        significant = c["mean_diff"] > 0 and c["holm_adjusted_p"] < 0.05
        robust = c["positive_folds"] >= 6
        clear = all(contrasts[p]["mean_diff"] > 0 for p in placebos)
        out[name] = "SUPPORTED" if (significant and robust and clear) else ("FRAGILE" if significant else "NOT_SUPPORTED")
    return out


# ── economics on the mid sample ─────────────────────────────────────────────────────────────────────────────────────

MID_DAILY = Path("data/research_mid/derived/exp014_daily_panel.parquet")


def mid_daily_panel(root: Path) -> pd.DataFrame:
    """Daily forward returns and dollar volume for the mid universe, one-session step, capped at the last prediction date; cached. Mirrors `exp010b.build_daily_panel` for the second store."""
    from datetime import date as Date

    from src.quant.datasets.store import RawStore
    from src.quant.features.registry import REGISTRY
    from src.quant.pit.dataset import DatasetBuilder
    from src.quant.pit.universe import UniverseHistory
    from src.quant.study import exp010b

    root = Path(root)
    cache = root / MID_DAILY
    if not cache.exists():
        start, _ = exp009b.arm_firewall(root)
        if exp010b.LAST_PREDICTION_DATE >= start:
            raise RuntimeError("panel end is not before the holdout start")
        store = RawStore(root / "data/research_mid")
        universe = UniverseHistory.load(root / "data/research_mid/universe", name="mid")
        dataset = DatasetBuilder(store, universe).build(start=Date(2014, 4, 1), end=exp010b.LAST_PREDICTION_DATE, features=REGISTRY.per_symbol_names()[:3], labels=["fwd_ret_5", "fwd_ret_21"],
                                                       step_sessions=1, workers=6, run_guards=False)
        panel = dataset.frame[["date", "symbol", "dollar_volume", "fwd_ret_5", "fwd_ret_21", "in_universe"]]
        cache.parent.mkdir(parents=True, exist_ok=True)
        panel.to_parquet(cache, compression="zstd")
    panel = pd.read_parquet(cache)
    panel["date"] = pd.to_datetime(panel["date"])
    panel = panel[panel["date"].dt.date <= exp010b.LAST_PREDICTION_DATE].reset_index(drop=True)
    FIREWALL.assert_clear(panel, context="EXP-014 mid daily returns panel")
    return panel


# ── artifacts ─────────────────────────────────────────────────────────────────────────────────────────────────────

def train_artifact(frame: pd.DataFrame, arm: str, output: Path, *, fingerprint: str) -> Path:
    """Fit one ridge arm on every labelled confirmatory row and save a self-describing artifact (research use only)."""
    import joblib

    from src.quant.models.base import FoldImputer
    from src.quant.models.factory import ModelSpec
    from src.quant.models.registry import dependency_versions

    features = ML_ARMS[arm]["features"]
    usable = frame.dropna(subset=[LABEL])
    FIREWALL.assert_clear(usable.assign(date=pd.to_datetime(usable["date"]).dt.date), context=f"{EXPERIMENT_ID} final artifact training rows")
    spec = ModelSpec(f"ridge_{arm}_final", "ridge", tuple(exp012.RIDGE_PARAMS.items()), 0)
    model = spec.build()
    imputer = FoldImputer(standardise=model.requires_scaling)
    X = imputer.fit_transform(usable[features].to_numpy(dtype=float), feature_names=features)
    model.fit(X, usable[LABEL].to_numpy(dtype=float), feature_names=features)
    path = Path(output) / "model" / f"{arm}.joblib"
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"experiment": EXPERIMENT_ID, "arm": arm, "features": features, "label": LABEL, "imputer": imputer, "model": model, "trained_rows": int(len(usable)),
                 "trained_through": str(pd.to_datetime(usable["date"]).max().date()), "definition_fingerprint": fingerprint, "amend_block": AMEND_BLOCK,
                 "status": "RESEARCH ARTIFACT - NOT FOR PRODUCTION - PROMOTION NOT ASSESSED", "dependency_versions": dependency_versions()}, path)
    return path


def reload_check(artifact: Path, frame_path: Path, expected_path: Path) -> dict[str, Any]:
    """Run in a fresh process: load the saved artifact, score the saved rows and compare with the scores the study computed in memory."""
    bundle = exp012.load_artifact(Path(artifact))
    frame = pd.read_parquet(frame_path)
    scores = exp012.predict_with_artifact(bundle, frame)
    expected = pd.read_parquet(expected_path)["score"].to_numpy()
    difference = float(np.max(np.abs(scores.to_numpy() - expected)))
    return {"rows": int(len(frame)), "max_abs_difference": difference, "ok": bool(difference < 1e-9), "features": len(bundle["features"])}


# ── run ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

INPUTS_FILE = Path("docs/EXP_014_INPUTS.json")


def input_paths() -> dict[str, Path]:
    return {"mid_panel": MID_PANEL, "mid_panel_manifest": MID_MANIFEST, "frozen_panel": FROZEN_PANEL, "classification": CLASSIFICATION, "fsds_filings": rel.FILINGS,
            "edgar_filings": EDGAR_FILINGS, "frozen_identity": FROZEN_IDENTITY, "calendar": CALENDAR}


def verify_inputs(root: Path = Path(".")) -> dict[str, Any]:
    """Every input must hash to the value written down in the registration."""
    root = Path(root)
    expected = json.loads((root / INPUTS_FILE).read_text())["sha256"]
    actual = {name: prereg.sha256_file(root / path) for name, path in input_paths().items()}
    bad = {name: {"expected": expected.get(name), "actual": h} for name, h in actual.items() if expected.get(name) != h}
    if bad:
        raise RuntimeError(f"inputs differ from the registration: {bad}")
    return actual


def build_samples(root: Path, calendar: TradingCalendar) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    root = Path(root)
    filings = pd.read_parquet(root / rel.FILINGS)
    classification = pd.read_parquet(root / CLASSIFICATION)
    frozen_ciks = {int(c) for c in pd.read_parquet(root / FROZEN_IDENTITY, columns=["cik"])["cik"].dropna()}
    mid = pd.read_parquet(root / MID_PANEL)
    mid["date"] = pd.to_datetime(mid["date"])
    conf_rows = confirmatory_sample(mid, frozen_ciks)
    frozen = pd.read_parquet(root / FROZEN_PANEL)
    frozen["date"] = pd.to_datetime(frozen["date"])
    sep_rows = time_separate_sample(frozen)
    conf = assemble(conf_rows, root, calendar, filings, classification)
    sep = assemble(sep_rows, root, calendar, filings, classification)
    counts = {"mid_panel_rows": int(len(mid)), "confirmatory_rows": int(len(conf)), "confirmatory_firms": int(conf["firm"].nunique()), "confirmatory_dates": int(conf["date"].nunique()),
              "time_separate_rows": int(len(sep)), "time_separate_firms": int(sep["firm"].nunique()), "discovery_ciks_excluded": len(frozen_ciks),
              "mid_rows_dropped_as_discovery_companies": int((mid["cik"].fillna(-1).astype("int64").isin(frozen_ciks)).sum())}
    return conf, sep, counts


def run_study(root: Path = Path("."), *, output: Optional[Path] = None, workers: int = 6, rehearsal: bool = False, skip_ml: bool = False, skip_economics: bool = False,
              draws: int = WEBB_DRAWS, robust_draws: int = ROBUST_DRAWS) -> dict[str, Any]:
    """The registered study. `rehearsal=True` shuffles the label across firms within each date, writes outside the experiment directory and skips the registration gate: it exercises every code path
    and carries no information about the hypotheses."""
    from concurrent import futures

    from src.quant.models.registry import dependency_versions
    from src.quant.study import exp009a, exp010a, exp010b

    began = time.perf_counter()
    root = Path(root)
    output = Path(output) if output else root / OUTPUT_DIR
    if rehearsal:
        if (root / OUTPUT_DIR).resolve() in (output.resolve(), *output.resolve().parents):
            raise RuntimeError("a rehearsal must not write into the experiment directory")
        gate = {"rehearsal": True, "note": "label shuffled within date; no result about the hypotheses"}
    else:
        gate = prereg_gate(root)                                # before any data is read
    git_state = exp009a._git_state(root)
    guard = exp010b.holdout_guard(root)
    hashes = verify_inputs(root) if not rehearsal else {}
    fingerprint = definition_fingerprint(root) + ("-rehearsal" if rehearsal else "")
    calendar = read_calendar(root)
    conf, sep, counts = build_samples(root, calendar)
    if rehearsal:
        conf[LABEL] = exp012.permute_within_date(conf, [LABEL], seed=SEED)[LABEL]
        sep[LABEL] = exp012.permute_within_date(sep, [LABEL], seed=SEED + 1)[LABEL]
    if conf["date"].max() > SAMPLE_END:
        raise RuntimeError("the confirmatory sample extends past the registered end")
    FIREWALL.assert_clear(conf.assign(date=conf["date"].dt.date), context="EXP-014 confirmatory sample")
    output.mkdir(parents=True, exist_ok=True)
    (output / "checkpoints").mkdir(exist_ok=True)

    regression = confirmatory_regressions(conf, sep, draws=draws, robust_draws=robust_draws)
    decision = decide(regression)
    exp010a._atomic_json(output / "results.json", {"counts": counts, "regressions": regression, "decision": decision})
    rows = [{"name": k, **{kk: vv for kk, vv in v.items() if kk != "coefficients"}} for k, v in regression.items() if isinstance(v, dict) and "coef" in v]
    rows += [{"name": f"secondary:{k}", **{kk: vv for kk, vv in v.items() if kk != "coefficients"}} for k, v in regression["secondary"].items()]
    pd.DataFrame(rows).to_csv(output / "regressions.csv", index=False)
    pd.DataFrame([{"gate": g, "passed": ok} for g, ok in decision["gates"].items()]).to_csv(output / "robustness.csv", index=False)
    print(f"EXP-014 regression stage: {decision['label']} ({decision['failed_gates']})", flush=True)

    ml_block: dict[str, Any] = {"skipped": True}
    if not skip_ml:
        frame_path = output / "checkpoints" / "confirmatory_frame.parquet"
        conf.to_parquet(frame_path, index=False)
        pending = [t for t in ml_tasks() if not ml_checkpoint(output, *t).exists()]
        if pending:
            with futures.ProcessPoolExecutor(max_workers=workers, initializer=_ml_init, initargs=(str(frame_path), str(root))) as pool:
                for arm, seed, predictions, seconds, errors in pool.map(_ml_task, pending):
                    if errors:
                        raise RuntimeError(f"{arm} seed {seed} failed: {errors}")
                    predictions.to_parquet(ml_checkpoint(output, arm, seed), index=False)
                    print(f"fitted {arm} seed {seed}: {len(predictions):,} rows in {seconds:.1f}s", flush=True)
        predictions = {key: pd.read_parquet(ml_checkpoint(output, *key)) for key in ml_tasks()}
        bad = sorted(f"{a}:{s}" for (a, s), p in predictions.items() if not np.isfinite(p["prediction"].to_numpy(dtype=float)).all())
        if bad:
            raise RuntimeError(f"non-finite predictions in {bad}")
        series = {key: exp012.ic_series(p) for key, p in predictions.items()}
        fold_ic = {key: [float(g.pipe(lambda x: exp012.ic_series(x)).mean()) for _, g in p.groupby("fold")] for key, p in predictions.items()}
        contrasts = ml_paired_tests(series, fold_ic)
        labels = ml_label(contrasts)
        pd.DataFrame([{"contrast": k, **{kk: vv for kk, vv in v.items() if kk != "fold_diffs"}, "fold_diffs": json.dumps(v["fold_diffs"])} for k, v in contrasts.items()]).to_csv(output / "ml_paired_tests.csv", index=False)
        metrics = [{"arm": a, "seed": s, "rows": int(len(p)), "mean_rank_ic": float(series[(a, s)].mean()), "fold_ic": json.dumps(fold_ic[(a, s)])} for (a, s), p in predictions.items()]
        pd.DataFrame(metrics).to_csv(output / "ml_metrics.csv", index=False)
        ml_block = {"labels": labels, "contrasts": {k: {kk: vv for kk, vv in v.items() if kk != "fold_diffs"} for k, v in contrasts.items()}}
        if not skip_economics:
            from src.quant.study import exp011
            daily = mid_daily_panel(root)
            universe = daily[daily["in_universe"]]
            schedule = exp010b.rebalance_schedule(calendar, exp010b.ARMS[exp011.ECONOMICS_ARM]["step_sessions"])
            panel = conf.assign(date=conf["date"].dt.date)
            reports = {key: exp011.arm_seed_report(key[0], key[1], p, panel, universe, calendar, schedule) for key, p in predictions.items() if key[0] in ("M0", "M1", "G0", "G1")}
            pd.DataFrame([{k: v for k, v in r.items() if k not in ("costs", "fold_ic")} for r in reports.values()]).to_csv(output / "economics.csv", index=False)
            ml_block["economics"] = {f"{a}:{s}": {k: v for k, v in r.items() if k not in ("fold_ic",)} for (a, s), r in reports.items()}
        # the artifact, scored again in a fresh process
        artifact = train_artifact(conf, "M1", output, fingerprint=fingerprint)
        sample = conf.dropna(subset=[LABEL]).head(2000).reset_index(drop=True)
        bundle = exp012.load_artifact(artifact)
        sample_path, expected_path = output / "checkpoints" / "reload_rows.parquet", output / "checkpoints" / "reload_expected.parquet"
        sample.to_parquet(sample_path, index=False)
        exp012.predict_with_artifact(bundle, sample).to_frame("score").to_parquet(expected_path, index=False)
        import subprocess as sp
        import sys

        proc = sp.run([sys.executable, "-m", "src.quant.study.exp014", "reload-check", str(artifact), str(sample_path), str(expected_path)], cwd=root, capture_output=True, text=True)
        reload = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.returncode == 0 and proc.stdout.strip() else {"ok": False, "stderr": proc.stderr[-500:]}
        ml_block["artifact"] = {"path": str(artifact), "reload_check_in_fresh_process": reload}
        if not reload.get("ok"):
            raise RuntimeError(f"the saved artifact does not reproduce the in-memory scores: {reload}")
    exp010a._atomic_json(output / "definition.json", DEFINITION)
    exp010a._atomic_json(output / "config.json", {"ml_arms": {k: {"model": v["model"], "features": v["features"], "seeds": list(v["seeds"]), "placebo": v.get("placebo")} for k, v in ML_ARMS.items()},
                                                  "folds": [f.as_dict() for f in exp009b.recorded_plan(root).folds], "controls": BASE_CONTROLS, "amend_block": AMEND_BLOCK})
    manifest = {"experiment_id": EXPERIMENT_ID, "status": DEFINITION["status"], **gate, **git_state, "holdout": guard, "input_sha256": hashes, "counts": counts, "decision": decision,
                "machine_learning": ml_block, "dependency_versions": dependency_versions(),
                "compute": {"wall_seconds": round(time.perf_counter() - began, 1), "cpu_count": os.cpu_count(), "workers": workers, "platform": platform.platform(), "python": platform.python_version()},
                "completion": "REHEARSAL" if rehearsal else "COMPLETE", "promotion": "NOT ASSESSED"}
    manifest["output_sha256"] = {p.name: prereg.sha256_file(p) for p in sorted(output.glob("*")) if p.is_file() and p.name != "manifest.json"}
    exp010a._atomic_json(output / "manifest.json", manifest)
    print(f"EXP-014 {'REHEARSAL' if rehearsal else 'COMPLETE'}: {decision['label']}", flush=True)
    return {"manifest": manifest, "decision": decision, "regression": regression}


def label_free_counts(root: Path = Path(".")) -> dict[str, Any]:
    """Feasibility counts for the registration (power gate): how many companies and rows carry each treatment. Reads no label and computes no relation."""
    root = Path(root)
    calendar = read_calendar(root)
    conf, sep, counts = build_samples(root, calendar)
    out = {**counts}
    for name, frame in (("confirmatory", conf), ("time_separate", sep)):
        out[name] = {t: {"rows": int((frame[f"D_{t}"] > 0).sum()), "firms": int(frame.loc[frame[f"D_{t}"] > 0, "firm"].nunique())} for t in ("core_730", "other_730", "unchanged_730", "unclass_730", "any_730")}
        out[name]["rows_without_history"] = int(frame["D_core_730"].isna().sum())
    return out


if __name__ == "__main__":
    import sys

    if sys.argv[1:2] == ["reload-check"]:
        outcome = reload_check(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
        print(json.dumps(outcome), flush=True)
        sys.stderr.flush()
        # Interpreter teardown after scikit-learn/BLAS work hangs intermittently on this platform (the process has already printed its result and then never exits), so leave without it.
        os._exit(0 if outcome["ok"] else 1)
    elif sys.argv[1:2] == ["counts"]:
        print(json.dumps(label_free_counts(Path(".")), indent=1, default=str))
    else:
        print("usage: python -m src.quant.study.exp014 [reload-check ARTIFACT ROWS EXPECTED | counts]")
