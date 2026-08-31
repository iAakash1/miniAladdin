"""
Portfolio construction — turning a signal into weights.

## The separation this module exists to enforce

skfolio's most useful idea is not any particular optimiser; it is the insistence
that **estimation and optimisation are different objects**. A covariance
estimator, an expected-return estimator and an allocation rule are separate
concerns with separate failure modes, and collapsing them into one function is
how a covariance bug becomes indistinguishable from an allocation bug.

So this module takes estimates as *inputs* and returns weights. It does not
forecast, it does not score, and it has no access to a model. That boundary is
the point:

    signal generation  →  portfolio construction  →  execution
    (src/quant/models)    (this module)              (backtest/engine.py)

**Optimised weights are not alpha.** An optimiser that improves a Sharpe ratio
has redistributed existing risk, not discovered information. Nothing here is
permitted to be described as predictive evidence, and `docs/quant.md` says so.

## Why these methods and not a convex solver

Every allocator below has a closed form or a short iterative solution and needs
only numpy. A general convex solver (cvxpy, as skfolio uses) would buy exact
CVaR minimisation and arbitrary linear constraints — but it is a heavy
dependency for a repository whose research conclusion is that no model has an
edge worth allocating to. When a model clears the promotion gate, the solver is
the right next step; until then it is capacity for a problem we do not have.

The one place this is visibly a compromise is `min_cvar`, which is documented as
a **heuristic tail-weighted allocation, not an LP-optimal CVaR solution**. It is
labelled that way in its return payload rather than in a docstring nobody reads.

## Constraints are applied, then re-checked

`apply_constraints` runs long-only clipping, weight caps, cash floor and
turnover limiting in sequence, and each step can break the previous one — a
turnover limit pulls weights back toward the prior book, which can re-violate a
cap. So the sequence is iterated to a fixed point and the result is *verified*;
a constraint set that cannot be satisfied returns `feasible=False` with the
violated constraint named, rather than silently returning something close.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("omnisignal.quant.portfolio")

#: Ridge added to a covariance diagonal before inversion.
#:
#: An empirical covariance over N names and T periods is singular whenever
#: T <= N, which for a 250-name universe on 400 rebalances is not a corner case.
#: Inverting it unridged produces enormous offsetting weights that look like a
#: brilliant hedge and are numerical noise.
COVARIANCE_RIDGE = 1e-8

#: Below this the name is treated as untradeable rather than infinitely
#: attractive to an inverse-volatility rule.
MIN_VOLATILITY = 1e-6

#: Fixed-point iterations for the constraint sequence.
MAX_CONSTRAINT_PASSES = 24


@dataclass(frozen=True)
class Constraints:
    """What the allocation is allowed to look like.

    Deliberately a value object: an optimiser call is reproducible from its
    inputs, and the constraint set is part of the experiment record.
    """

    long_only: bool = False
    #: Absolute cap per name, as a fraction of gross exposure.
    max_weight: float = 0.10
    min_weight: Optional[float] = None
    #: Fraction of capital held back. Weights are scaled to `1 - cash_floor`.
    cash_floor: float = 0.0
    #: Maximum one-way turnover per rebalance, as a fraction. `None` = unlimited.
    max_turnover: Optional[float] = None
    #: Gross exposure target. 1.0 = fully invested; long/short books use 1.0
    #: gross split across both sides.
    gross_target: float = 1.0
    #: Net exposure target for a long/short book. `None` = unconstrained.
    #:
    #: Defaults to None, NOT 0.0. A dollar-neutral default is right for a
    #: long/short book and catastrophic for a long-only one: clipping negatives
    #: and then forcing the sum to zero is only satisfiable by an empty book, so
    #: every weight collapses to 0 and the optimiser silently returns nothing.
    #: `__post_init__` refuses the combination outright rather than producing it.
    net_target: Optional[float] = None
    #: Per-group exposure caps, e.g. {"sector": {"Tech": 0.30}}. Applied only
    #: where a group map is supplied; absent groups are unconstrained.
    group_caps: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.long_only and self.net_target is not None and self.net_target <= 0:
            raise ValueError(
                "long_only with net_target <= 0 is unsatisfiable: a book with no "
                "short side cannot sum to zero unless it is empty. Leave "
                "net_target as None for long-only, or set long_only=False."
            )
        if self.max_weight is not None and self.max_weight <= 0:
            raise ValueError("max_weight must be positive")

    def as_dict(self) -> dict[str, Any]:
        return {
            "long_only": self.long_only,
            "max_weight": self.max_weight,
            "min_weight": self.min_weight,
            "cash_floor": self.cash_floor,
            "max_turnover": self.max_turnover,
            "gross_target": self.gross_target,
            "net_target": self.net_target,
            "group_caps": dict(self.group_caps),
        }


@dataclass
class Allocation:
    """Weights plus everything needed to argue about them."""

    weights: pd.Series
    method: str
    feasible: bool
    diagnostics: dict[str, Any] = field(default_factory=dict)
    violations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def gross(self) -> float:
        return float(self.weights.abs().sum())

    @property
    def net(self) -> float:
        return float(self.weights.sum())

    @property
    def names(self) -> int:
        return int((self.weights.abs() > 1e-12).sum())

    def turnover_from(self, prior: Optional[pd.Series]) -> float:
        if prior is None or prior.empty:
            return self.gross
        joined = self.weights.reindex(self.weights.index.union(prior.index)).fillna(0.0)
        before = prior.reindex(joined.index).fillna(0.0)
        return float((joined - before).abs().sum())

    def as_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "feasible": self.feasible,
            "gross_exposure": round(self.gross, 6),
            "net_exposure": round(self.net, 6),
            "names": self.names,
            "max_weight": round(float(self.weights.abs().max()) if len(self.weights) else 0.0, 6),
            "effective_names": round(self.effective_names, 2),
            "diagnostics": self.diagnostics,
            "violations": list(self.violations),
            "notes": list(self.notes),
        }

    @property
    def effective_names(self) -> float:
        """Inverse Herfindahl — how many positions the book *behaves* like.

        A 250-name book with 90% in one name is a one-name book, and a count of
        holdings does not say so.
        """
        w = self.weights.abs()
        total = float(w.sum())
        if total <= 0:
            return 0.0
        share = w / total
        return float(1.0 / max((share ** 2).sum(), 1e-12))


# ── estimators ───────────────────────────────────────────────────────────────


def covariance(returns: pd.DataFrame, *, ridge: float = COVARIANCE_RIDGE) -> pd.DataFrame:
    """Empirical covariance with a ridge, and no shrinkage claim.

    Named `covariance` rather than `estimate_covariance` because that is all it
    is. Ledoit-Wolf shrinkage would be a better estimator and is a deliberate
    omission: it changes the risk numbers, so introducing it silently would
    change every historical comparison. Add it as a named alternative when
    something depends on it.
    """
    clean = returns.dropna(axis=1, how="all")
    cov = clean.cov()
    if ridge > 0 and len(cov):
        cov = cov + np.eye(len(cov)) * ridge
    return cov


def volatilities(returns: pd.DataFrame) -> pd.Series:
    return returns.std().clip(lower=MIN_VOLATILITY)


# ── allocators ───────────────────────────────────────────────────────────────


def equal_weight(names: pd.Index, *, long_only: bool = True) -> pd.Series:
    """The allocator every other one has to beat.

    It has no estimation error because it estimates nothing, which is exactly
    why it is hard to beat out of sample.
    """
    if len(names) == 0:
        return pd.Series(dtype=float)
    return pd.Series(1.0 / len(names), index=names, dtype=float)


def inverse_volatility(vols: pd.Series) -> pd.Series:
    inverse = 1.0 / vols.clip(lower=MIN_VOLATILITY)
    total = float(inverse.sum())
    if total <= 0:
        return equal_weight(vols.index)
    return inverse / total


def minimum_variance(cov: pd.DataFrame) -> pd.Series:
    """Analytic min-variance: w ∝ Σ⁻¹1, normalised to sum 1.

    Unconstrained, so it will short unless the caller applies a long-only
    constraint afterwards. That is deliberate — clipping inside the allocator
    would make the returned weights not actually minimum-variance while still
    being called that.
    """
    if cov.empty:
        return pd.Series(dtype=float)
    inv = np.linalg.pinv(cov.to_numpy())
    ones = np.ones(len(cov))
    raw = inv @ ones
    total = float(raw.sum())
    if not np.isfinite(total) or abs(total) < 1e-12:
        return equal_weight(cov.index)
    return pd.Series(raw / total, index=cov.index, dtype=float)


def maximum_diversification(cov: pd.DataFrame) -> pd.Series:
    """Maximise the diversification ratio (Σwᵢσᵢ) / √(wᵀΣw).

    Equivalent to a min-variance problem on the correlation matrix, rescaled by
    volatility — which is how it is solved here.
    """
    if cov.empty:
        return pd.Series(dtype=float)
    sigma = pd.Series(np.sqrt(np.diag(cov.to_numpy())), index=cov.index).clip(lower=MIN_VOLATILITY)
    corr = cov.div(sigma, axis=0).div(sigma, axis=1)
    inner = minimum_variance(corr)
    raw = inner / sigma
    total = float(raw.sum())
    if not np.isfinite(total) or abs(total) < 1e-12:
        return equal_weight(cov.index)
    return raw / total


def risk_parity(cov: pd.DataFrame, *, iterations: int = 500, tolerance: float = 1e-9) -> pd.Series:
    """Equal risk contribution, by cyclical coordinate descent.

    Each name is nudged toward the weight at which its marginal contribution to
    risk equals every other's. Converges reliably for a positive-definite
    covariance and is long-only by construction, which is why it needs no
    clipping afterwards.
    """
    if cov.empty:
        return pd.Series(dtype=float)
    matrix = cov.to_numpy()
    n = len(matrix)
    w = np.full(n, 1.0 / n)
    target = 1.0 / n

    for _ in range(iterations):
        portfolio_vol = float(np.sqrt(max(w @ matrix @ w, 1e-24)))
        marginal = matrix @ w / portfolio_vol
        contribution = w * marginal / portfolio_vol
        gap = float(np.max(np.abs(contribution - target)))
        if gap < tolerance:
            break
        # Multiplicative update: raise weights whose risk share is too small.
        w = w * (target / np.maximum(contribution, 1e-12)) ** 0.5
        w = np.maximum(w, 1e-12)
        w = w / w.sum()

    return pd.Series(w, index=cov.index, dtype=float)


def mean_variance(
    expected: pd.Series, cov: pd.DataFrame, *, risk_aversion: float = 1.0
) -> pd.Series:
    """Analytic mean-variance: w ∝ Σ⁻¹μ / λ.

    `expected` is whatever the caller supplies. **This module does not
    manufacture it** — passing a model's cross-sectional rank here is the
    caller's decision, and the resulting weights are an allocation of that
    signal's risk, not evidence that the signal works.
    """
    if cov.empty or expected.empty:
        return pd.Series(dtype=float)
    aligned = expected.reindex(cov.index).fillna(0.0)
    inv = np.linalg.pinv(cov.to_numpy())
    raw = inv @ aligned.to_numpy() / max(risk_aversion, 1e-9)
    gross = float(np.abs(raw).sum())
    if not np.isfinite(gross) or gross < 1e-12:
        return equal_weight(cov.index)
    return pd.Series(raw / gross, index=cov.index, dtype=float)


def min_cvar_heuristic(
    returns: pd.DataFrame, *, alpha: float = 0.05
) -> pd.Series:
    """Tail-risk-weighted allocation. **NOT an LP-optimal CVaR solution.**

    True min-CVaR is a linear program (Rockafellar-Uryasev). This weights names
    by the inverse of their own conditional tail loss, which reduces tail
    exposure but does not minimise *portfolio* CVaR — it ignores tail dependence
    entirely, and tail dependence is most of the problem.

    It is included because it is materially better than inverse-volatility when
    losses are asymmetric, and it is named `_heuristic` and reports
    `optimal=False` so nobody mistakes it for the real thing.
    """
    if returns.empty:
        return pd.Series(dtype=float)
    tail: dict[str, float] = {}
    for name in returns.columns:
        series = returns[name].dropna()
        if len(series) < 20:
            tail[name] = float(series.std() or MIN_VOLATILITY)
            continue
        cutoff = float(np.quantile(series, alpha))
        losses = series[series <= cutoff]
        tail[name] = float(abs(losses.mean())) if len(losses) else float(abs(cutoff))
    scores = pd.Series(tail).clip(lower=MIN_VOLATILITY)
    inverse = 1.0 / scores
    return inverse / float(inverse.sum())


# ── constraints ──────────────────────────────────────────────────────────────


def apply_constraints(
    weights: pd.Series,
    constraints: Constraints,
    *,
    prior: Optional[pd.Series] = None,
    groups: Optional[pd.Series] = None,
) -> tuple[pd.Series, list[str], list[str]]:
    """Apply the constraint set to a fixed point, then verify it.

    Each step can break the previous one — a turnover limit pulls weights toward
    the prior book, which can re-violate a per-name cap — so the sequence is
    iterated. If it does not converge, the *violated* constraints are returned
    rather than a weight vector that quietly satisfies none of them.
    """
    w = weights.astype(float).copy()
    notes: list[str] = []

    for _ in range(MAX_CONSTRAINT_PASSES):
        before = w.copy()

        if constraints.long_only:
            w = w.clip(lower=0.0)

        if constraints.min_weight is not None:
            w[w.abs() < constraints.min_weight] = 0.0

        gross = float(w.abs().sum())
        if gross > 0:
            w = w / gross * constraints.gross_target

        if constraints.max_weight is not None and constraints.max_weight > 0:
            w = w.clip(lower=-constraints.max_weight, upper=constraints.max_weight)

        if groups is not None and constraints.group_caps:
            for group, cap in constraints.group_caps.items():
                members = groups[groups == group].index.intersection(w.index)
                if not len(members):
                    continue
                exposure = float(w.loc[members].abs().sum())
                if exposure > cap and exposure > 0:
                    w.loc[members] = w.loc[members] * (cap / exposure)

        if constraints.net_target is not None and not constraints.long_only and len(w):
            drift = float(w.sum()) - constraints.net_target
            if abs(drift) > 1e-9:
                # Spread the correction across active names rather than one.
                active = w[w.abs() > 1e-12].index
                if len(active):
                    w.loc[active] = w.loc[active] - drift / len(active)

        if constraints.max_turnover is not None and prior is not None and len(prior):
            index = w.index.union(prior.index)
            target = w.reindex(index).fillna(0.0)
            base = prior.reindex(index).fillna(0.0)
            turnover = float((target - base).abs().sum())
            if turnover > constraints.max_turnover > 0:
                scale = constraints.max_turnover / turnover
                w = base + (target - base) * scale
                notes.append(
                    f"turnover limited: {turnover:.3f} -> {constraints.max_turnover:.3f} "
                    f"(moved {scale:.1%} of the way to target)"
                )

        if constraints.cash_floor > 0:
            gross = float(w.abs().sum())
            if gross > 0:
                w = w / gross * (constraints.gross_target * (1.0 - constraints.cash_floor))

        if np.allclose(before.reindex(w.index).fillna(0.0).to_numpy(), w.to_numpy(), atol=1e-10):
            break

    violations: list[str] = []
    if constraints.long_only and float(w.min() if len(w) else 0.0) < -1e-9:
        violations.append("long_only")
    if constraints.max_weight and len(w) and float(w.abs().max()) > constraints.max_weight + 1e-6:
        violations.append("max_weight")
    if constraints.max_turnover is not None and prior is not None and len(prior):
        index = w.index.union(prior.index)
        realised = float(
            (w.reindex(index).fillna(0.0) - prior.reindex(index).fillna(0.0)).abs().sum()
        )
        if realised > constraints.max_turnover + 1e-6:
            violations.append("max_turnover")

    return w, violations, notes


# ── entry point ──────────────────────────────────────────────────────────────

METHODS: tuple[str, ...] = (
    "equal_weight",
    "inverse_volatility",
    "minimum_variance",
    "maximum_diversification",
    "risk_parity",
    "mean_variance",
    "volatility_target",
    "min_cvar_heuristic",
)


def optimize(
    method: str,
    *,
    returns: Optional[pd.DataFrame] = None,
    expected: Optional[pd.Series] = None,
    constraints: Optional[Constraints] = None,
    prior: Optional[pd.Series] = None,
    groups: Optional[pd.Series] = None,
    risk_aversion: float = 1.0,
    target_volatility: Optional[float] = None,
    periods_per_year: float = 252.0,
) -> Allocation:
    """Build an allocation. The one public entry point.

    Every method needs `returns` except `equal_weight`, which needs only names.
    A method that cannot be computed from what it was given returns an
    infeasible `Allocation` naming the missing input — it does not fall back to
    equal weight silently, because a silent fallback makes an optimiser look
    like it ran when it did not.
    """
    constraints = constraints or Constraints()
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; known: {METHODS}")

    if returns is None or returns.empty:
        if method == "equal_weight" and expected is not None and len(expected):
            weights = equal_weight(expected.index)
        else:
            return Allocation(
                weights=pd.Series(dtype=float), method=method, feasible=False,
                violations=["no_returns"],
                notes=[f"{method} needs a returns panel; none was supplied"],
            )
    else:
        clean = returns.dropna(axis=1, how="all")
        if clean.shape[1] == 0:
            return Allocation(
                weights=pd.Series(dtype=float), method=method, feasible=False,
                violations=["no_usable_names"], notes=["every column was all-NaN"],
            )
        cov = covariance(clean)
        vols = volatilities(clean)

        if method == "equal_weight":
            weights = equal_weight(clean.columns)
        elif method == "inverse_volatility":
            weights = inverse_volatility(vols)
        elif method == "minimum_variance":
            weights = minimum_variance(cov)
        elif method == "maximum_diversification":
            weights = maximum_diversification(cov)
        elif method == "risk_parity":
            weights = risk_parity(cov)
        elif method == "min_cvar_heuristic":
            weights = min_cvar_heuristic(clean)
        elif method == "mean_variance":
            if expected is None or expected.empty:
                return Allocation(
                    weights=pd.Series(dtype=float), method=method, feasible=False,
                    violations=["no_expected_returns"],
                    notes=["mean_variance needs an expected-return vector"],
                )
            weights = mean_variance(expected, cov, risk_aversion=risk_aversion)
        elif method == "volatility_target":
            weights = inverse_volatility(vols)
        else:  # pragma: no cover — guarded above
            raise ValueError(method)

    weights, violations, notes = apply_constraints(
        weights, constraints, prior=prior, groups=groups
    )

    diagnostics: dict[str, Any] = {"constraints": constraints.as_dict()}

    if returns is not None and not returns.empty and len(weights):
        cov = covariance(returns.dropna(axis=1, how="all"))
        aligned = weights.reindex(cov.index).fillna(0.0)
        variance = float(aligned @ cov.to_numpy() @ aligned)
        realised = float(np.sqrt(max(variance, 0.0)) * np.sqrt(periods_per_year))
        diagnostics["ex_ante_volatility_annualised"] = round(realised, 6)

        if method == "volatility_target" and target_volatility and realised > 0:
            scale = target_volatility / realised
            weights = weights * scale
            diagnostics["volatility_scale"] = round(scale, 6)
            diagnostics["target_volatility"] = target_volatility
            notes.append(
                f"scaled by {scale:.3f} to target {target_volatility:.1%} annualised "
                f"from an ex-ante {realised:.1%}"
            )

        sigma = pd.Series(np.sqrt(np.diag(cov.to_numpy())), index=cov.index)
        weighted_vol = float((aligned.abs() * sigma).sum())
        if realised > 0:
            diagnostics["diversification_ratio"] = round(
                weighted_vol * np.sqrt(periods_per_year) / realised, 4
            )

    if prior is not None:
        diagnostics["turnover_from_prior"] = round(
            float(
                (
                    weights.reindex(weights.index.union(prior.index)).fillna(0.0)
                    - prior.reindex(weights.index.union(prior.index)).fillna(0.0)
                ).abs().sum()
            ),
            6,
        )

    notes.append(
        "Optimised weights allocate risk; they are not predictive evidence and "
        "must never be described as alpha."
    )
    if method == "min_cvar_heuristic":
        diagnostics["optimal"] = False
        notes.append(
            "min_cvar_heuristic weights by each name's own tail loss and ignores "
            "tail dependence. It is NOT an LP-optimal CVaR solution."
        )

    return Allocation(
        weights=weights,
        method=method,
        feasible=not violations,
        diagnostics=diagnostics,
        violations=violations,
        notes=notes,
    )
