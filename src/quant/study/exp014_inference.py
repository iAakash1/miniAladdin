"""Inference tools for EXP-014: fixed-effects regression with firm and date dependence, wild-cluster bootstrap with few treated firms, influence, and event-time windows.

The question this module serves is whether a rare firm-level event (a restating amendment) is followed by lower cross-sectional return ranks, and how much of that is believable when the events sit in a few
dozen firms. Three facts shape the tools:

* A firm that is flagged stays flagged for two years and appears on many dates, and all firms share the same dates. Observations are therefore dependent along both dimensions, and the usual standard error
  is far too small. `cgm_two_way` clusters on firm and on date (Cameron, Gelbach and Miller) and repairs a covariance matrix that is not positive semi-definite.
* With few treated firms, asymptotic cluster-robust t statistics over-reject. `wild_cluster_bootstrap` imposes the null (no effect of the focus regressor), re-draws the residuals of each firm with
  mean-zero weights (Webb's six-point distribution by default), and compares the observed t statistic with the bootstrap distribution. It works on per-firm sums, so 10,000 draws cost seconds.
* A coefficient that rests on one or two firms is not evidence about firms in general. `influence_by_cluster` ranks the firms by how much deleting each moves the coefficient, and `refit_without` refits
  after removing the most influential ones.

Everything is exact linear algebra on data already stripped of fixed effects (`absorb`), so each function is checked against a brute-force computation in `tests/quant/test_exp014_inference.py`.
No function here reads a return or a label by itself; callers pass arrays.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
import pandas as pd
from scipy.stats import norm

WEBB = np.array([-np.sqrt(1.5), -1.0, -np.sqrt(0.5), np.sqrt(0.5), 1.0, np.sqrt(1.5)])


def absorb(frame: pd.DataFrame, columns: Sequence[str], groups: Sequence[pd.Series]) -> pd.DataFrame:
    """Subtract the mean within each group (the cells of the fixed effects) from every column. One pass is exact when the groups are a single cell variable."""
    key = pd.MultiIndex.from_arrays([g.to_numpy() for g in groups]) if len(groups) > 1 else groups[0]
    sub = frame[list(columns)]
    return sub - sub.groupby(key, sort=False).transform("mean")


@dataclass
class Fit:
    names: list[str]
    beta: np.ndarray
    resid: np.ndarray
    xtx_inv: np.ndarray
    n: int
    firms: int
    dates: int

    def coef(self, name: str) -> float:
        return float(self.beta[self.names.index(name)])


def ols(y: np.ndarray, X: np.ndarray, names: Sequence[str], firm: np.ndarray, date: np.ndarray) -> Fit:
    xtx_inv = np.linalg.inv(X.T @ X)
    beta = xtx_inv @ (X.T @ y)
    return Fit(list(names), beta, y - X @ beta, xtx_inv, int(len(y)), int(len(np.unique(firm))), int(len(np.unique(date))))


def _cluster_meat(X: np.ndarray, e: np.ndarray, codes: np.ndarray) -> np.ndarray:
    scores = np.zeros((int(codes.max()) + 1, X.shape[1]))
    np.add.at(scores, codes, X * e[:, None])
    g = int(len(np.unique(codes)))
    return (g / max(g - 1, 1)) * (scores.T @ scores)


def cgm_two_way(fit: Fit, X: np.ndarray, firm: np.ndarray, date: np.ndarray) -> np.ndarray:
    """Cameron-Gelbach-Miller covariance of the coefficients, clustered on firm and on date. `firm` and `date` are integer codes 0..G-1."""
    inter = np.unique(np.stack([firm, date], axis=1), axis=0, return_inverse=True)[1].ravel()
    meat = _cluster_meat(X, fit.resid, firm) + _cluster_meat(X, fit.resid, date) - _cluster_meat(X, fit.resid, inter)
    v = fit.xtx_inv @ meat @ fit.xtx_inv
    values, vectors = np.linalg.eigh((v + v.T) / 2)
    return (vectors * np.maximum(values, 0)) @ vectors.T


def one_way(fit: Fit, X: np.ndarray, codes: np.ndarray) -> np.ndarray:
    return fit.xtx_inv @ _cluster_meat(X, fit.resid, codes) @ fit.xtx_inv


def summary(fit: Fit, cov: np.ndarray, name: str) -> dict:
    b, se = fit.coef(name), float(np.sqrt(max(cov[fit.names.index(name), fit.names.index(name)], 0.0)))
    t = b / se if se > 0 else float("nan")
    return {"coef": b, "se": se, "t": t, "p_one_sided_negative": float(norm.cdf(t)), "p_two_sided": float(2 * norm.sf(abs(t)))}


# ── wild-cluster bootstrap, null imposed, on per-cluster sums ────────────────────────────────────────────────

@dataclass
class ClusterSums:
    """What the bootstrap needs, per cluster, for one focus regressor `d` and the other regressors `Z`. Everything is already free of the fixed effects."""
    g: int
    sxx: float
    t_obs: float
    gamma: float
    B: np.ndarray        # (G,)   sum_i d~_i e0_i      (restricted residual e0 = y - Z beta0)
    S: np.ndarray        # (G,)   sum_i d~_i^2
    C: np.ndarray        # (G,k)  sum_i d~_i Z_i
    D: np.ndarray        # (G,k)  sum_i Z_i e0_i
    zz_inv: np.ndarray   # (k,k)
    scores_obs: np.ndarray


def cluster_sums(y: np.ndarray, d: np.ndarray, Z: np.ndarray, codes: np.ndarray) -> ClusterSums:
    zz_inv = np.linalg.inv(Z.T @ Z)
    d_t = d - Z @ (zz_inv @ (Z.T @ d))                      # d residualised on Z
    beta0 = zz_inv @ (Z.T @ y)
    e0 = y - Z @ beta0
    g = int(codes.max()) + 1
    sxx = float(d_t @ d_t)
    gamma = float(d_t @ y) / sxx
    B = np.bincount(codes, weights=d_t * e0, minlength=g)
    S = np.bincount(codes, weights=d_t * d_t, minlength=g)
    C = np.zeros((g, Z.shape[1]))
    D = np.zeros((g, Z.shape[1]))
    np.add.at(C, codes, Z * d_t[:, None])
    np.add.at(D, codes, Z * e0[:, None])
    e_full = e0 - d_t * gamma                                  # full-model residual by Frisch-Waugh: M_Z y - d~ gamma, and M_Z y = e0
    scores = np.bincount(codes, weights=d_t * e_full, minlength=g)
    se = np.sqrt((g / max(g - 1, 1)) * float(scores @ scores)) / sxx
    return ClusterSums(g=g, sxx=sxx, t_obs=gamma / se, gamma=gamma, B=B, S=S, C=C, D=D, zz_inv=zz_inv, scores_obs=scores)


def bootstrap_t(cs: ClusterSums, weights: np.ndarray) -> np.ndarray:
    """t statistics of the focus coefficient for each row of `weights` (draws x G), null imposed. Exact; no refit."""
    num = weights @ cs.B
    gamma = num / cs.sxx
    theta = (weights @ cs.D) @ cs.zz_inv                      # (draws,k)  (Z'Z)^-1 sum_g w_g D_g
    scores = weights * cs.B[None, :] - theta @ cs.C.T - gamma[:, None] * cs.S[None, :]
    se = np.sqrt((cs.g / max(cs.g - 1, 1)) * np.sum(scores * scores, axis=1)) / cs.sxx
    return gamma / se


def webb_weights(rng: np.random.Generator, draws: int, g: int) -> np.ndarray:
    return WEBB[rng.integers(0, 6, size=(draws, g))]


def wild_cluster_bootstrap(y: np.ndarray, d: np.ndarray, Z: np.ndarray, codes: np.ndarray, *, draws: int = 9999, seed: int = 0, block: int = 1000) -> dict:
    """One-sided (negative) and two-sided wild-cluster bootstrap p-values of the focus coefficient, clustered on `codes` (firm)."""
    cs = cluster_sums(y, d, Z, codes)
    rng = np.random.default_rng(seed)
    t_star = np.concatenate([bootstrap_t(cs, webb_weights(rng, min(block, draws - i), cs.g)) for i in range(0, draws, block)])
    return {"gamma": cs.gamma, "t_obs": cs.t_obs, "draws": int(draws), "clusters": cs.g,
            "p_one_sided_negative": float((1 + np.sum(t_star <= cs.t_obs)) / (1 + draws)), "p_two_sided": float((1 + np.sum(np.abs(t_star) >= abs(cs.t_obs))) / (1 + draws)),
            "t_star_quantiles": {str(q): float(np.quantile(t_star, q)) for q in (0.01, 0.025, 0.05, 0.5, 0.95, 0.975, 0.99)}}


# ── influence and leave-out ────────────────────────────────────────────────────────────────────────────────

def influence_by_cluster(y: np.ndarray, X: np.ndarray, focus: int, codes: np.ndarray, only: Optional[np.ndarray] = None) -> pd.DataFrame:
    """Exact delete-one-cluster change of the focus coefficient (fixed effects held at their full-sample means), for the clusters in `only` (default all)."""
    xtx, xty = X.T @ X, X.T @ y
    beta = np.linalg.solve(xtx, xty)
    rows = []
    for c in (np.unique(codes) if only is None else only):
        m = codes == c
        Xg, yg = X[m], y[m]
        beta_minus = np.linalg.solve(xtx - Xg.T @ Xg, xty - Xg.T @ yg)
        rows.append((int(c), int(m.sum()), float(beta_minus[focus] - beta[focus])))
    return pd.DataFrame(rows, columns=["cluster", "rows", "delta"])


def refit_without(frame: pd.DataFrame, columns: Sequence[str], groups: Sequence[pd.Series], exclude: np.ndarray, firm_col: str, y_col: str, focus: str) -> dict:
    """Refit the regression on the rows whose firm code is not in `exclude`, re-absorbing the fixed effects. Returns the focus coefficient and the share of rows kept."""
    keep = ~frame[firm_col].isin(exclude).to_numpy()
    sub = frame[keep]
    z = absorb(sub, [y_col, *columns], [g[keep] for g in groups])
    X = z[list(columns)].to_numpy(float)
    names = list(columns)
    beta = np.linalg.lstsq(X, z[y_col].to_numpy(float), rcond=None)[0]
    return {"coef": float(beta[names.index(focus)]), "rows_kept": float(keep.mean()), "firms_removed": int(len(exclude))}


# ── event-time windows on a date axis ──────────────────────────────────────────────────────────────────────

def window_counts(decision_days: np.ndarray, event_days_sorted: np.ndarray, lo: int, hi: int) -> np.ndarray:
    """Number of events with day in (decision_day + lo, decision_day + hi]. Past windows use negative offsets, e.g. (-730, 0] is the trailing two years; positive offsets look into the future
    and exist only for placebo and anticipation diagnostics."""
    if not len(event_days_sorted):
        return np.zeros(len(decision_days))
    upper = np.searchsorted(event_days_sorted, decision_days + hi, side="right")
    lower = np.searchsorted(event_days_sorted, decision_days + lo, side="right")
    return (upper - lower).astype(float)
