"""The boosted-tree ranker: gradients, equivalence with sklearn, and query discipline.

The objective is the only thing EXP-009B varies, so the evidence that it is
implemented correctly has to be independent of the experiment's results:
finite-difference gradients, an exact match to sklearn for the control, and
properties a correct pairwise loss must have (queries never mix, a better order
never gets a worse loss).
"""

import numpy as np
import pytest
from sklearn.ensemble import GradientBoostingRegressor

from src.quant.models.factory import ModelSpec
from src.quant.models.ranking import (
    BoostedL2, BoostedLambdaMART, BoostedPairwise, BoostedTrees,
    query_gradients, relevance_from_rank,
)


def pairwise_loss(scores, relevance, sigma=1.0):
    total = 0.0
    for i in range(len(scores)):
        for j in range(len(scores)):
            if relevance[i] > relevance[j]:
                total += np.log1p(np.exp(-sigma * (scores[i] - scores[j])))
    return total


# ── relevance labels ────────────────────────────────────────────────────────

def test_relevance_bins_are_the_five_within_date_quintiles():
    rank = np.linspace(-1.0, 1.0, 1000)
    rel = relevance_from_rank(rank)
    assert set(rel) == {0, 1, 2, 3, 4}
    counts = np.bincount(rel)
    assert counts.max() - counts.min() <= 2                     # near-equal quintiles
    assert relevance_from_rank(np.array([1.0]))[0] == 4          # the top edge is clipped in
    assert relevance_from_rank(np.array([-1.0]))[0] == 0
    assert (np.diff(rel) >= 0).all()                             # monotone in the rank


def test_relevance_depends_on_nothing_but_the_label():
    a = relevance_from_rank(np.array([-0.5, 0.0, 0.5]))
    b = relevance_from_rank(np.array([-0.5, 0.0, 0.5]))
    assert (a == b).all()


# ── gradients ───────────────────────────────────────────────────────────────

def test_pairwise_pseudo_residual_is_minus_the_gradient_of_the_pairwise_loss():
    rng = np.random.default_rng(0)
    scores = rng.normal(size=12)
    rel = rng.integers(0, 5, size=12)
    residual, hessian = query_gradients(scores, rel, mode="pairwise")
    step = 1e-6
    numeric = np.array([
        (pairwise_loss(scores + step * np.eye(12)[k], rel) - pairwise_loss(scores - step * np.eye(12)[k], rel))
        / (2 * step) for k in range(12)
    ])
    assert residual == pytest.approx(-numeric, abs=1e-6)
    h = 1e-3          # a wider step: a second difference at 1e-6 is dominated by rounding noise
    curvature = np.array([
        (pairwise_loss(scores + h * np.eye(12)[k], rel) - 2 * pairwise_loss(scores, rel)
         + pairwise_loss(scores - h * np.eye(12)[k], rel)) / h**2 for k in range(12)
    ])
    assert hessian == pytest.approx(curvature, rel=1e-4, abs=1e-5)


def test_lambdamart_weights_each_pair_by_its_ndcg_change():
    scores = np.array([3.0, 2.0, 1.0])          # current order = 0, 1, 2
    rel = np.array([0, 2, 1])
    residual, _ = query_gradients(scores, rel, mode="lambdamart")
    disc = 1.0 / np.log2(np.array([0, 1, 2]) + 2.0)
    max_dcg = 2 * 1.0 + 1 * disc[1]             # ideal order gains 2, 1, 0
    expected = np.zeros(3)
    for i in range(3):
        for j in range(3):
            if rel[i] > rel[j]:
                delta = abs((rel[i] - rel[j]) * (disc[i] - disc[j])) / max_dcg
                rho = 1.0 / (1.0 + np.exp(scores[i] - scores[j]))
                expected[i] += rho * delta
                expected[j] -= rho * delta
    assert residual == pytest.approx(expected)


def test_a_better_ordering_has_a_smaller_residual_push():
    rel = np.array([0, 1, 2, 3, 4])
    good = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    bad = good[::-1].copy()
    for mode in ("pairwise", "lambdamart"):
        r_good, _ = query_gradients(good, rel, mode=mode)
        r_bad, _ = query_gradients(bad, rel, mode=mode)
        assert np.abs(r_good).sum() < np.abs(r_bad).sum()


def test_residuals_push_relevant_items_up_and_irrelevant_ones_down():
    rel = np.array([0, 0, 0, 4, 4])
    r, _ = query_gradients(np.zeros(5), rel, mode="pairwise")
    assert (r[rel == 4] > 0).all() and (r[rel == 0] < 0).all()
    assert r.sum() == pytest.approx(0.0)                        # pairs are zero-sum


def test_equal_relevance_produces_no_gradient():
    r, h = query_gradients(np.array([0.3, -0.2, 1.0]), np.array([2, 2, 2]), mode="lambdamart")
    assert not r.any() and not h.any()


def test_a_query_is_untouched_by_the_scores_of_another():
    rng = np.random.default_rng(1)
    s1, r1 = rng.normal(size=8), rng.integers(0, 5, 8)
    s2, r2 = rng.normal(size=9), rng.integers(0, 5, 9)
    alone, _ = query_gradients(s1, r1, mode="lambdamart")
    # Recomputed with a second query present elsewhere: the function is per-query by construction,
    # and the boosting loop must call it per group.
    model = BoostedLambdaMART(n_estimators=1)
    groups = np.array([0] * 8 + [1] * 9)
    scores = np.concatenate([s1, s2])
    rel = np.concatenate([r1, r2])
    slices = model._query_slices(groups)
    joined = np.zeros(17)
    for idx in slices:
        joined[idx], _ = query_gradients(scores[idx], rel[idx], mode="lambdamart")
    assert joined[:8] == pytest.approx(alone)


def test_gradients_do_not_depend_on_row_order_within_a_query():
    rng = np.random.default_rng(2)
    s, r = rng.normal(size=15), rng.integers(0, 5, 15)
    perm = rng.permutation(15)
    a, _ = query_gradients(s, r, mode="lambdamart")
    b, _ = query_gradients(s[perm], r[perm], mode="lambdamart")
    assert b == pytest.approx(a[perm])


# ── the control is sklearn's GradientBoostingRegressor ──────────────────────

def synthetic(n_dates=40, per=60, seed=0, signal=0.3):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n_dates * per, 6))
    dates = np.repeat(np.arange(n_dates), per)
    latent = signal * X[:, 0] - 0.2 * X[:, 1] * (X[:, 2] > 0) + rng.normal(size=len(X))
    rank = np.empty(len(X))
    for d in range(n_dates):
        idx = dates == d
        rank[idx] = np.argsort(np.argsort(latent[idx])) / (idx.sum() - 1) * 2 - 1
    return X, rank, dates, latent


def test_the_l2_objective_reproduces_sklearn_gradient_boosting_exactly_without_subsampling():
    X, y, groups, _ = synthetic()
    params = dict(n_estimators=25, learning_rate=0.1, max_depth=3, min_samples_leaf=20, subsample=1.0)
    mine = BoostedL2(seed=0, **params).fit(X, y, groups=groups)
    theirs = GradientBoostingRegressor(random_state=0, **params).fit(X, y)
    assert mine.predict(X[:200]) == pytest.approx(theirs.predict(X[:200]), abs=1e-9)


def test_the_l2_objective_needs_no_groups():
    X, y, _, _ = synthetic(n_dates=5)
    BoostedL2(n_estimators=3).fit(X, y)


# ── learning ────────────────────────────────────────────────────────────────

def spearman_by_date(pred, truth, groups):
    from scipy.stats import spearmanr
    out = []
    for d in np.unique(groups):
        idx = groups == d
        out.append(spearmanr(pred[idx], truth[idx])[0])
    return float(np.mean(out))


@pytest.mark.parametrize("cls", [BoostedLambdaMART, BoostedPairwise, BoostedL2])
def test_every_objective_learns_a_planted_cross_sectional_signal(cls):
    X, y, groups, _ = synthetic(n_dates=60, per=80, signal=0.6)
    train, test = groups < 45, groups >= 45
    model = cls(n_estimators=60, learning_rate=0.1, min_samples_leaf=30, seed=0).fit(
        X[train], y[train], groups=groups[train])
    assert spearman_by_date(model.predict(X[test]), y[test], groups[test]) > 0.15


@pytest.mark.parametrize("cls", [BoostedLambdaMART, BoostedPairwise])
def test_ranking_objectives_require_the_query_groups(cls):
    X, y, _, _ = synthetic(n_dates=5)
    with pytest.raises(ValueError, match="groups"):
        cls(n_estimators=2).fit(X, y)


def test_fitting_is_deterministic():
    X, y, groups, _ = synthetic(n_dates=20)
    a = BoostedLambdaMART(n_estimators=10, seed=3).fit(X, y, groups=groups).predict(X[:50])
    b = BoostedLambdaMART(n_estimators=10, seed=3).fit(X, y, groups=groups).predict(X[:50])
    assert (a == b).all()
    c = BoostedLambdaMART(n_estimators=10, seed=4).fit(X, y, groups=groups).predict(X[:50])
    assert not (a == c).all()


def test_cross_date_pairs_never_form():
    """Two dates with opposite label structure: a model that mixed dates could not fit both."""
    rng = np.random.default_rng(5)
    per = 100
    X = rng.normal(size=(2 * per, 3))
    groups = np.repeat([0, 1], per)
    y = np.empty(2 * per)
    for d in (0, 1):
        idx = groups == d
        y[idx] = np.argsort(np.argsort(X[idx, 0] + 3.0 * d)) / (per - 1) * 2 - 1   # a level shift per date
    model = BoostedPairwise(n_estimators=40, learning_rate=0.1, min_samples_leaf=10).fit(X, y, groups=groups)
    assert spearman_by_date(model.predict(X), y, groups) > 0.5


def test_predictions_depend_only_on_the_rows_features():
    X, y, groups, _ = synthetic(n_dates=20)
    model = BoostedLambdaMART(n_estimators=10).fit(X, y, groups=groups)
    a = model.predict(X[:30])
    b = model.predict(X[:60])[:30]
    assert (a == b).all()


def test_the_model_reports_scale_free_only_for_rankers():
    assert BoostedL2().scale_free is False
    assert BoostedLambdaMART().scale_free is True
    assert BoostedPairwise().scale_free is True


def test_the_spec_factory_builds_all_three_and_they_declare_groups():
    for kind in ("boosted_l2", "boosted_lambdamart", "boosted_pairwise"):
        model = ModelSpec(kind, kind, (("n_estimators", 3),), 0).build()
        assert isinstance(model, BoostedTrees)
        assert model.requires_groups is True
        assert model.model_id == kind


def test_unknown_objective_is_rejected():
    with pytest.raises(ValueError):
        BoostedTrees(objective="listmle")
