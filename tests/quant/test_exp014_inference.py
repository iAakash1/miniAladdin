"""EXP-014 inference tools: every fast formula is checked against an explicit refit or a brute-force loop; the bootstrap is checked for size with few treated firms."""

import numpy as np
import pandas as pd

from src.quant.study import exp014_inference as inf


def make(n_firms=40, dates=25, treated=(0, 1, 2), effect=0.0, seed=0, k=3):
    rng = np.random.default_rng(seed)
    firm = np.repeat(np.arange(n_firms), dates)
    date = np.tile(np.arange(dates), n_firms)
    Z = rng.normal(size=(len(firm), k))
    d = np.isin(firm, treated).astype(float) * (date >= 8)                       # a treated firm stays treated from date 8
    firm_shock = rng.normal(size=n_firms)[firm] * 0.7                           # firm-level persistence: the reason plain standard errors fail
    y = Z @ np.linspace(0.3, -0.2, k) + effect * d + firm_shock + rng.normal(size=len(firm))
    return y, d, Z, firm, date


def explicit_cluster_t(y, d, Z, firm, name_index=0):
    X = np.column_stack([d, Z])
    xtx_inv = np.linalg.inv(X.T @ X)
    beta = xtx_inv @ X.T @ y
    e = y - X @ beta
    meat = np.zeros((X.shape[1],) * 2)
    for g in np.unique(firm):
        s = X[firm == g].T @ e[firm == g]
        meat += np.outer(s, s)
    g = len(np.unique(firm))
    cov = xtx_inv @ ((g / (g - 1)) * meat) @ xtx_inv
    return beta[name_index], beta[name_index] / np.sqrt(cov[name_index, name_index])


def test_absorb_removes_cell_means():
    f = pd.DataFrame({"a": [1.0, 2, 3, 4], "b": [10.0, 20, 30, 50], "cell": ["x", "x", "y", "y"]})
    out = inf.absorb(f, ["a", "b"], [f["cell"]])
    assert out["a"].tolist() == [-0.5, 0.5, -0.5, 0.5] and out["b"].tolist() == [-5, 5, -10, 10]


def test_ols_and_two_way_covariance_match_brute_force():
    y, d, Z, firm, date = make(effect=0.4, seed=1)
    X = np.column_stack([d, Z])
    names = ["d", "z0", "z1", "z2"]
    fit = inf.ols(y, X, names, firm, date)
    assert np.allclose(fit.beta, np.linalg.lstsq(X, y, rcond=None)[0])
    cov = inf.cgm_two_way(fit, X, firm, date)
    # brute force: V = V_firm + V_date - V_firm_date with the G/(G-1) corrections
    def meat(codes):
        m = np.zeros((4, 4))
        for g in np.unique(codes):
            s = X[codes == g].T @ fit.resid[codes == g]
            m += np.outer(s, s)
        return (len(np.unique(codes)) / (len(np.unique(codes)) - 1)) * m
    inter = np.unique(np.stack([firm, date], axis=1), axis=0, return_inverse=True)[1].ravel()
    raw = fit.xtx_inv @ (meat(firm) + meat(date) - meat(inter)) @ fit.xtx_inv
    w, q = np.linalg.eigh((raw + raw.T) / 2)
    assert np.allclose(cov, (q * np.maximum(w, 0)) @ q.T)
    assert np.all(np.linalg.eigvalsh(cov) > -1e-12)                              # positive semi-definite after the repair
    assert inf.summary(fit, cov, "d")["se"] > 0


def test_fast_bootstrap_statistics_equal_an_explicit_refit():
    y, d, Z, firm, date = make(n_firms=30, dates=12, treated=(0, 1), effect=0.5, seed=2)
    cs = inf.cluster_sums(y, d, Z, firm)
    gamma, t = explicit_cluster_t(y, d, Z, firm)
    assert np.isclose(cs.gamma, gamma) and np.isclose(cs.t_obs, t)                # observed statistic
    # restricted fit (null imposed) and a few explicit bootstrap samples
    beta0 = np.linalg.lstsq(Z, y, rcond=None)[0]
    e0 = y - Z @ beta0
    rng = np.random.default_rng(5)
    weights = inf.webb_weights(rng, 6, cs.g)
    fast = inf.bootstrap_t(cs, weights)
    for w, value in zip(weights, fast):
        y_star = Z @ beta0 + w[firm] * e0
        assert np.isclose(explicit_cluster_t(y_star, d, Z, firm)[1], value, atol=1e-9)


def test_wild_bootstrap_p_value_is_small_for_a_real_effect_and_uniform_for_none():
    y, d, Z, firm, _ = make(n_firms=60, dates=30, treated=tuple(range(8)), effect=1.2, seed=3)
    assert inf.wild_cluster_bootstrap(y, -d, Z, firm, draws=1999, seed=1)["p_one_sided_negative"] < 0.05     # the effect enters negatively
    ps = []
    for seed in range(120):
        y0, d0, Z0, f0, _ = make(n_firms=60, dates=20, treated=tuple(range(4)), effect=0.0, seed=100 + seed)
        ps.append(inf.wild_cluster_bootstrap(y0, d0, Z0, f0, draws=399, seed=seed)["p_two_sided"])
    rejection = float(np.mean(np.array(ps) < 0.05))
    assert 0.0 <= rejection <= 0.12                                               # near 5% with 4 treated firms of 60; a plain cluster t would over-reject here


def test_plain_cluster_t_over_rejects_with_few_treated_firms_and_the_bootstrap_does_not():
    plain, boot = [], []
    for seed in range(150):
        y, d, Z, firm, _ = make(n_firms=50, dates=20, treated=(0, 1, 2), effect=0.0, seed=300 + seed)
        _, t = explicit_cluster_t(y, d, Z, firm)
        plain.append(abs(t) > 1.96)
        boot.append(inf.wild_cluster_bootstrap(y, d, Z, firm, draws=399, seed=seed)["p_two_sided"] < 0.05)
    assert np.mean(plain) > np.mean(boot)
    assert np.mean(boot) < 0.12


def test_influence_equals_explicit_deletion():
    y, d, Z, firm, _ = make(n_firms=20, dates=15, treated=(0, 1), effect=0.6, seed=4)
    X = np.column_stack([d, Z])
    table = inf.influence_by_cluster(y, X, 0, firm, only=np.array([0, 1, 7]))
    full = np.linalg.lstsq(X, y, rcond=None)[0][0]
    for row in table.itertuples():
        keep = firm != row.cluster
        assert np.isclose(np.linalg.lstsq(X[keep], y[keep], rcond=None)[0][0] - full, row.delta)


def test_refit_without_reabsorbs_and_reports_kept_share():
    y, d, Z, firm, date = make(n_firms=20, dates=15, treated=(0, 1, 2), effect=-0.8, seed=6)
    frame = pd.DataFrame({"y": y, "d": d, "z0": Z[:, 0], "z1": Z[:, 1], "z2": Z[:, 2], "firm": firm, "date": date})
    full = inf.refit_without(frame, ["d", "z0", "z1", "z2"], [frame["date"]], np.array([], dtype=int), "firm", "y", "d")
    cut = inf.refit_without(frame, ["d", "z0", "z1", "z2"], [frame["date"]], np.array([0, 1]), "firm", "y", "d")
    assert full["rows_kept"] == 1.0 and np.isclose(cut["rows_kept"], 18 / 20)
    assert abs(cut["coef"] - full["coef"]) > 1e-6                                 # removing treated firms changes the estimate


def test_window_counts_past_and_future_windows():
    events = np.array([100, 200, 300, 900])
    days = np.array([150, 250, 1000, 50])
    assert inf.window_counts(days, events, -730, 0).tolist() == [1, 2, 2, 0]       # events in (day-730, day]
    assert inf.window_counts(days, events, 0, 365).tolist() == [2, 1, 0, 3]        # events in (day, day+365]
    assert inf.window_counts(days, events, -365, -1).tolist() == [1, 2, 1, 0]
    assert inf.window_counts(days, np.array([], dtype=int), -730, 0).tolist() == [0, 0, 0, 0]


def test_two_way_absorption_equals_regression_on_dummies():
    rng = np.random.default_rng(3)
    n = 400
    f = pd.DataFrame({"x": rng.normal(size=n), "cell": rng.integers(0, 12, n).astype(str), "firm": rng.integers(0, 25, n).astype(str)})
    f["y"] = 0.5 * f["x"] + rng.normal(size=n)
    z = inf.absorb_two_way(f, ["y", "x"], f["cell"], f["firm"], tol=1e-12)
    D = pd.get_dummies(f[["cell", "firm"]], dtype=float).to_numpy()
    for col in ("y", "x"):
        resid = f[col].to_numpy() - D @ np.linalg.lstsq(D, f[col].to_numpy(), rcond=None)[0]
        assert np.allclose(z[col].to_numpy(), resid, atol=1e-8)
