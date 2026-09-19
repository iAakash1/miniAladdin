"""Non-outcome validation of the boosted ranker, added after the EXP-009B run.

None of these tests touches a real prediction or a real return. They exist because the
repository implemented the ranking objective itself, so its correctness has to rest on
mathematics and controlled examples, not on how the experiment turned out.

The reference for the equations is Burges, *From RankNet to LambdaRank to LambdaMART:
An Overview*, Microsoft Research TR-2010-82, sections 2 and 7 (read from the PDF):

    lambda_ij = -sigma |dZ_ij| / (1 + exp(sigma (s_i - s_j)))          for U_i ranked above U_j
    dC/ds_i   = sum_j -sigma |dZ_ij| rho_ij,   rho_ij = 1 / (1 + exp(sigma (s_i - s_j)))
    d2C/ds_i2 = sum_j  sigma^2 |dZ_ij| rho_ij (1 - rho_ij)
    leaf step = (sum of lambdas) / (sum of second derivatives)          (sign flipped: maximising)

`dZ_ij` is the change in the utility (NDCG) from swapping the two items' positions. The paper's
NDCG uses gain 2^l - 1; EXP-009B preregistered LINEAR gains (gain = relevance) — a documented
variation of the utility, not of the equations.
"""

import numpy as np
import pytest

from src.quant.models import ranking
from src.quant.models.ranking import BoostedPairwise, BoostedLambdaMART, query_gradients


def test_hand_calculated_two_item_pairwise_example():
    """Tied scores, item 0 relevant. rho = 1/2, so residual = +-sigma*rho = +-0.5, hessian = 0.25."""
    residual, hessian = query_gradients(np.array([0.0, 0.0]), np.array([1, 0]), mode="pairwise")
    assert residual == pytest.approx([0.5, -0.5])
    assert hessian == pytest.approx([0.25, 0.25])


def test_hand_calculated_two_item_lambdamart_example():
    """Same pair with the NDCG weight. Items sit at positions 0 and 1 (stable order on the tie).

    gains (linear) = [1, 0]; discounts = [1/log2(2), 1/log2(3)] = [1, 0.6309297536];
    maxDCG = 1; |dZ| = |(1-0) * (1 - 0.6309297536)| / 1 = 0.3690702464.
    residual = sigma * rho * |dZ| = 0.5 * 0.3690702464 = 0.1845351232
    hessian  = sigma^2 * |dZ| * rho * (1 - rho) = 0.3690702464 * 0.25 = 0.0922675616
    """
    residual, hessian = query_gradients(np.array([0.0, 0.0]), np.array([1, 0]), mode="lambdamart")
    assert residual == pytest.approx([0.1845351232, -0.1845351232], abs=1e-9)
    assert hessian == pytest.approx([0.0922675616, 0.0922675616], abs=1e-9)


def test_signs_push_the_more_relevant_item_up_in_both_orders():
    for scores in ([0.0, 1.0], [1.0, 0.0]):
        residual, _ = query_gradients(np.array(scores), np.array([1, 0]), mode="lambdamart")
        assert residual[0] > 0 > residual[1]


def test_already_correct_order_pushes_less_than_a_wrong_one():
    right, _ = query_gradients(np.array([3.0, 0.0]), np.array([1, 0]), mode="pairwise")
    wrong, _ = query_gradients(np.array([0.0, 3.0]), np.array([1, 0]), mode="pairwise")
    assert abs(right[0]) < abs(wrong[0])


def test_the_newton_leaf_step_is_the_ratio_of_summed_residuals_to_summed_hessians():
    """A leaf holding both items of the tied pair: residuals cancel, so the step is zero — as it must be."""
    residual, hessian = query_gradients(np.array([0.0, 0.0]), np.array([1, 0]), mode="pairwise")
    assert residual.sum() / hessian.sum() == pytest.approx(0.0, abs=1e-12)
    # A leaf holding only the relevant item steps up by residual/hessian = 0.5/0.25 = 2 (= 1/sigma * 2).
    assert residual[0] / hessian[0] == pytest.approx(2.0)


# ── B. the pairwise loss falls as boosting proceeds, on a controlled ordering ────────

def _pairwise_loss(scores, relevance, groups):
    total = 0.0
    for g in np.unique(groups):
        idx = np.flatnonzero(groups == g)
        s, r = scores[idx], relevance[idx]
        diff = s[:, None] - s[None, :]
        mask = r[:, None] > r[None, :]
        total += float(np.log1p(np.exp(-diff[mask])).sum())
    return total


def _staged_scores(model, X, upto):
    out = np.full(len(X), model._init)
    for tree, values in list(zip(model._trees, model._leaf_values))[:upto]:
        out += model.params["learning_rate"] * values[tree.apply(X)]
    return out


def test_the_pairwise_training_loss_decreases_monotonically_on_a_controlled_ordering():
    rng = np.random.default_rng(0)
    n_dates, per = 12, 40
    X = rng.normal(size=(n_dates * per, 4))
    groups = np.repeat(np.arange(n_dates), per)
    rank = np.empty(len(X))
    for d in range(n_dates):
        idx = groups == d
        latent = 1.5 * X[idx, 0] + 0.5 * X[idx, 1] + 0.3 * rng.normal(size=idx.sum())
        rank[idx] = np.argsort(np.argsort(latent)) / (idx.sum() - 1) * 2 - 1
    relevance = ranking.relevance_from_rank(rank)
    model = BoostedPairwise(n_estimators=25, learning_rate=0.1, min_samples_leaf=20, subsample=1.0, seed=0)
    model.fit(X, rank, groups=groups)
    losses = [_pairwise_loss(_staged_scores(model, X, k), relevance, groups) for k in range(0, 26, 5)]
    assert all(b < a for a, b in zip(losses, losses[1:])), losses
    assert losses[-1] < 0.85 * losses[0]


# ── C. no pair ever crosses prediction dates ─────────────────────────────────────────

def test_every_gradient_call_sees_exactly_one_date(monkeypatch):
    rng = np.random.default_rng(1)
    sizes = {0: 30, 1: 45, 2: 38}
    groups = np.concatenate([[d] * n for d, n in sizes.items()])
    X = rng.normal(size=(len(groups), 3))
    y = rng.uniform(-1, 1, size=len(groups))
    seen = []
    real = ranking.query_gradients

    def spy(scores, relevance, **kw):
        seen.append(len(scores))
        return real(scores, relevance, **kw)

    monkeypatch.setattr(ranking, "query_gradients", spy)
    BoostedLambdaMART(n_estimators=3, min_samples_leaf=5, subsample=1.0).fit(X, y, groups=groups)
    assert set(seen) == set(sizes.values())                        # one call per date, never the union
    assert len(seen) == 3 * len(sizes)


# ── F. a deterministic seed reproduces predictions exactly; another does not ────────────

def test_the_seed_fixes_the_fit_exactly():
    rng = np.random.default_rng(2)
    X = rng.normal(size=(400, 5)); groups = np.repeat(np.arange(8), 50); y = rng.uniform(-1, 1, 400)
    fit = lambda seed: BoostedLambdaMART(n_estimators=8, min_samples_leaf=10, seed=seed).fit(X, y, groups=groups).predict(X)
    assert (fit(0) == fit(0)).all()
    assert not (fit(0) == fit(1)).all()
